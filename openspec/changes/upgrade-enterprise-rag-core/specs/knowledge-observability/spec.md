## ADDED Requirements

### Requirement: 系统必须记录完整的 retrieval debug trace

知识库检索 SHALL 为每次请求生成结构化 debug trace，至少记录：

- 原始 query
- rewritten query
- ACL 过滤表达式
- dense 候选及其分数
- sparse 候选及其分数
- RRF 合并结果及其分数
- rerank 结果及其分数
- 最终引用
- rewrite retry 次数
- low-confidence 判定结果

#### Scenario: 开发者可定位“为什么没召回”
- **WHEN** 用户反馈“文档里明明有但没答出来”
- **THEN** 开发者可以通过 debug trace 判断问题发生在 rewrite、ACL、dense、sparse、merge 或 rerank 的哪一步

### Requirement: 日志必须区分开发调试、业务审计和用户行为三类

系统 SHALL 将日志拆分为 `retrieval_debug_trace`、`access_audit_log` 和 `user_behavior_log` 三类。系统 MUST NOT 将三类日志混存在同一结构中。

#### Scenario: 生产环境关闭全量 debug 但保留审计
- **WHEN** 系统运行在生产环境
- **THEN** 可以关闭全量详细 debug trace
- **AND** 审计日志仍然必须保留

### Requirement: 系统必须记录访问审计日志

知识库系统 SHALL 记录访问审计日志，用于合规、排障与越权调查。日志至少包含：

- `user_id`
- `user_roles`
- `client_ip`
- `query`
- `matched_doc_ids`
- `blocked_doc_ids`
- `deny_reason`
- `request_started_at`
- `request_finished_at`
- `timestamp`

#### Scenario: 越权访问尝试被审计
- **WHEN** 用户尝试查询其无权限查看的文档
- **THEN** 系统记录该次访问尝试和对应拒绝原因

### Requirement: 日志保存策略必须区分环境与类型

系统 SHALL 为不同日志类型定义不同的默认保留时长和环境开关。首版项目默认值如下：

- `retrieval_debug_trace`：`dev/staging` 全量开启，`prod` 精简或采样，默认保留 7 天
- `access_audit_log`：所有环境可开，`prod` 全量保留，默认保留 180 天
- `user_behavior_log`：默认保留 30 天

以上值是项目默认值，SHOULD 可通过配置覆盖。

#### Scenario: 生产环境不落全量长时 debug
- **WHEN** 系统运行在生产环境
- **THEN** 不应无限期保存全量详细 debug trace

### Requirement: 低置信度和重试上限必须有首版标准

系统 SHALL 为低召回、低置信度和 rewrite 重试上限定义首版标准：

- `rewrite_retry_max = 1`
- merge 后候选数 `< 5` 视为低召回
- 最终 rerank 可用候选数 `< 3` 视为低置信度

分数阈值 SHOULD 通过 benchmark 校准，并作为模型配置项注入，而不是硬编码成跨模型通用常量。

#### Scenario: 低召回触发受控兜底
- **WHEN** merge 后候选数小于 5
- **THEN** 系统按既定规则进入低召回处理分支

### Requirement: 系统必须提供低召回与失败原因标记

当检索质量不足时，系统 SHALL 把失败原因结构化记录下来，例如：

- `acl_filtered_empty`
- `status_filtered_empty`
- `rewrite_retry_exhausted`
- `retrieval_low_confidence`

#### Scenario: 版本过滤导致空结果
- **WHEN** 文档只存在过期版本且默认过滤掉了全部候选
- **THEN** 系统记录 `status_filtered_empty` 或等价原因

### Requirement: 观测数据必须为后续前端调试面板预留稳定字段

系统输出的 debug trace 与 audit payload SHALL 使用稳定字段名，供未来前端调试面板直接消费，而不依赖临时字符串拼接。

#### Scenario: 前端调试面板复用结构化数据
- **WHEN** 前端需要展示“改写后 query”“召回条数”“最终引用”
- **THEN** 可直接读取结构化字段，而不是重新解析文本日志

### Requirement: 日志访问权限必须受控

系统 SHALL 对日志查看能力做权限隔离。普通员工 MUST NOT 查看 `retrieval_debug_trace` 或 `access_audit_log` 的原始内容。

#### Scenario: 普通员工无法查看内部检索分数
- **WHEN** 普通员工在前端使用知识库
- **THEN** 只能看到面向用户的简化 trace
- **AND** 看不到内部检索分数、ACL 表达式和原始调试日志

### Requirement: 敏感查询内容必须脱敏

当 query 或命中文档涉及薪资、隐私或涉密信息时，系统 SHALL 对日志内容做脱敏或摘要化处理。生产环境 MUST NOT 直接落完整敏感正文。

#### Scenario: 薪资类查询不落完整正文
- **WHEN** 用户查询薪资或个人隐私信息
- **THEN** 生产日志只保留必要审计字段和脱敏摘要
