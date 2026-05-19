## ADDED Requirements

### Requirement: Query rewrite 必须发生在检索前

知识库检索 SHALL 在正式召回前执行 query rewrite。系统 MUST 保留原始 query，并生成一个更适合检索的 rewritten query。轻量 rewrite SHALL 默认启用。

#### Scenario: 口语化报销问题被改写成制度语言
- **WHEN** 用户输入“出差打车能不能报”
- **THEN** 系统生成类似“差旅报销制度中市内交通费是否可以报销”的 rewritten query
- **AND** 保留原 query 供调试与审计

#### Scenario: 精确版本号不被误改写
- **WHEN** 用户输入“差旅制度 v2.1”
- **THEN** rewrite 过程不得删除或改坏 `v2.1` 这类精确信息

#### Scenario: 用户主动查历史版本时保留历史意图
- **WHEN** 用户输入“查 2024 年旧版差旅制度”或“看 v1.0 版本”
- **THEN** rewrite 过程不得把“旧版 / 历史 / v1.0”这类历史查询意图消掉

#### Scenario: rewrite 失败直接回退原始问句
- **WHEN** rewrite 服务超时或报错
- **THEN** 系统直接使用用户原始 query 继续检索

### Requirement: 关键词提取必须有统一规范

系统 SHALL 对 rewrite 产出的关键词数量和剔除规则给出统一标准。首版 MUST 满足：

- 每次最多提取 5 个关键词
- 必须剔除礼貌词、虚词、空泛动作词
- 不得误删制度名、编号、实体名和固定编码

#### Scenario: 礼貌词不会进入关键词
- **WHEN** 用户输入“请帮我查一下差旅报销制度”
- **THEN** `请`、`帮我`、`查一下` 不应作为最终关键词

### Requirement: rewrite 产出的关键词必须服务于 sparse 检索

系统 SHALL 将 rewrite 产出的 `keywords` 用于增强 sparse/BM25 检索，但 MUST 做去停用词和去噪处理。系统 MUST NOT 把所有 rewrite 词无条件拼接进最终查询。

#### Scenario: rewrite keywords 强化术语召回
- **WHEN** rewrite 结果提取出“差旅”“报销”“市内交通费”
- **THEN** sparse 检索使用这些关键词提升对应术语的命中率

#### Scenario: keywords 不替换原 query
- **WHEN** 系统提取出关键词数组
- **THEN** 这些关键词只作为 sparse 检索补充输入
- **AND** 不替换 dense 检索所使用的原 query / rewritten query

### Requirement: 检索必须采用 dense + sparse 的 hybrid 模式

系统 SHALL 同时执行 dense retrieval 与 sparse retrieval，并在 ACL、状态、版本过滤之后再进行候选融合。系统 MUST 不再只依赖单一路径 dense 检索或简单词法回退作为默认标准方案。

#### Scenario: 语义表达通过 dense 命中
- **WHEN** 用户问题与文档用词不同，但语义相近
- **THEN** dense retrieval 可以召回相关 chunk

#### Scenario: 术语和编号通过 sparse 命中
- **WHEN** 用户问题包含术语、编号、模板名或版本号
- **THEN** sparse retrieval 可以召回对应 chunk

### Requirement: 系统必须提供 dense / sparse 全局偏向开关

系统 SHALL 提供一个可配置的全局偏向模式，用于整体调节 dense 与 sparse 的相对权重。首版至少支持：

- `balanced`
- `semantic_bias`
- `keyword_bias`

#### Scenario: 运营临时提高关键词权重
- **WHEN** 系统切换到 `keyword_bias`
- **THEN** sparse 检索的整体权重高于默认平衡模式

### Requirement: Hybrid merge 必须使用明确可配置的 RRF

系统 SHALL 使用 Reciprocal Rank Fusion 合并 dense 与 sparse 候选。RRF 的算法常数 MUST 与候选数量分开配置。默认 `rank_constant` SHOULD 使用行业常见值（如 `60`），而不是把 `10` 这类候选数量误当作 RRF 常数。

#### Scenario: RRF 常数与候选数量分离
- **WHEN** 系统使用 `rank_constant=60` 且 dense/sparse 各召回 30 条
- **THEN** 系统把 `60` 作为 `1 / (rank + k)` 的算法常数
- **AND** 不得把它解释为“只融合前 60 条”

### Requirement: Rerank 必须在融合后执行

系统 SHALL 在 RRF 合并之后对候选结果进行 rerank。Rerank 输入 SHOULD 控制在配置范围内，默认只对前 `30~50` 条候选做二次排序。

#### Scenario: 噪声候选被 rerank 压下
- **WHEN** dense 或 sparse 候选中混入只沾了一个关键词的噪声 chunk
- **THEN** rerank 后更能回答问题的制度片段排在前面

#### Scenario: high_recall 模式有明确上限
- **WHEN** 系统进入 `high_recall` profile
- **THEN** rerank 默认只读取前 50 条融合候选
- **AND** 最大输入不得超过 80 条

### Requirement: 低召回时必须有兜底策略

系统 SHALL 在检索候选过少、分数过低或融合后结果质量不足时执行一次受控兜底。兜底可以是 rewrite retry、放宽 retrieval profile 或保守拒答，但 MUST 不得无依据硬答。

#### Scenario: 第一次召回为空
- **WHEN** 初次 hybrid retrieval 未返回足够候选
- **THEN** 系统执行一次轻量 rewrite retry 或按 `faq_low_cost -> standard -> high_recall` 顺序只升级一档 profile
- **AND** 若仍然为空，则返回保守回答而不是编造制度

### Requirement: 兜底动作顺序必须固定

系统 SHALL 固定多重兜底动作的执行顺序。首版顺序 MUST 为：

1. `light_rewrite + 当前默认 profile`
2. rewrite retry 一次
3. retrieval profile 升档一次
4. 命中白名单时再执行一次 HyDE
5. 仍失败则保守回答

#### Scenario: HyDE 不会先于 rewrite retry 执行
- **WHEN** 系统首次召回不足
- **THEN** 必须先进行 rewrite retry
- **AND** 不得直接跳到 HyDE

### Requirement: 用户显式查询历史制度时允许放宽默认过滤

系统 SHALL 在用户明确表达“旧版本 / 历史版本 / 作废制度 / 指定旧版号”时允许进入 `history_lookup` 模式。在该模式下，系统可以放宽 `is_latest=true` 与默认状态过滤，但 MUST 在回答中标记“历史版本 / 非现行制度”。

#### Scenario: 用户查 v1.0 时允许命中旧版本
- **WHEN** 用户明确要求查看 `v1.0` 制度
- **THEN** 检索流程允许命中该旧版本文档
- **AND** 回答中明确提示这不是当前现行版本

#### Scenario: 用户查作废制度时允许命中停用文档
- **WHEN** 用户明确要求查看作废制度或停用文档
- **THEN** history lookup 可以放开 `deprecated` / 过期文档过滤

### Requirement: profile 升级必须是单请求内的临时升级

系统 SHALL 将 profile 升级限制在当前请求生命周期内。请求结束后，后续请求 MUST 回到默认 profile，而不是沿用上次的高召回模式。

#### Scenario: 高召回不会粘住整个会话
- **WHEN** 某次请求临时升级到了 `high_recall`
- **THEN** 下一次新请求仍从默认 profile 开始

### Requirement: HyDE 只允许在白名单场景受控触发

系统 SHALL 将 HyDE 作为受控增强模式，而不是默认路径。首版 SHOULD 只在人事、财务、合规、制度、合同类高价值问题，且初次召回为空或质量过低时触发。

#### Scenario: 普通 FAQ 不触发 HyDE
- **WHEN** 用户查询一个普通短 FAQ
- **THEN** 系统不得默认启动 HyDE

### Requirement: 回答必须附带可追溯引用

知识库回答 SHALL 只基于最终 rerank 后的候选生成，并附带可追溯到 `doc_id` 与 `chunk_id` 的引用信息。

#### Scenario: 回答引用可定位到原文档
- **WHEN** 系统给出关于报销制度的回答
- **THEN** 返回结果中包含 `doc_id`、`chunk_id`、`source_file` 和版本信息
