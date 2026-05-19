## 1. Metadata 与存储模型

- [ ] 1.1 为文档 metadata 新增字段：`title`、`status`、`version`、`is_latest`、`effective_at`、`expires_at`、`visibility_scope`、`owner_user_id`、`project_ids`、`maintainer`、`checksum`
- [ ] 1.2 为 chunk metadata 新增字段：`chunk_id`、`chunk_index`、`section_path`、`token_count`，并镜像 `status/version/is_latest/visibility_scope/department`
- [ ] 1.3 设计旧 metadata 的迁移策略，保证现有种子文档和上传接口不直接报错
- [ ] 1.4 明确 status 默认值、version 默认值和“最新版本”判定规则
- [ ] 1.5 明确 `checksum` 用于重复上传检测、内容变更检测和索引失效判断
- [ ] 1.6 将默认赋值规则定死：新文档 `version=v1.0`、`effective_at=立即生效`、旧数据优先迁成 `visibility_scope=department`

## 2. Ingestion 重构

- [ ] 2.1 从 `KnowledgeService` 中拆出 `KnowledgeIngestionService`
- [ ] 2.2 把“上传、解析、切分、元数据落盘、索引构建”拆成清晰子步骤
- [ ] 2.3 将首版默认切分定为 `512 tokens + 128 overlap`
- [ ] 2.4 为不同文档类型预留 `ChunkingStrategyResolver`，只有确有必要时才能覆盖默认切分
- [ ] 2.5 明确标题层级提取规则：能提取标题时写 `section_path`，否则安全回退到 `source_file + chunk_index/page_num`
- [ ] 2.6 为重建索引增加详细调试日志，方便定位是哪份文档出错
- [ ] 2.7 统一 token 统计工具为 `tiktoken`
- [ ] 2.8 明确允许覆盖默认切分的文档类型：合同/协议、表格附件、流程表单、超短通知
- [ ] 2.9 为上传流程补齐失败回滚和单步重试机制：`parse_failed`、`index_failed`

## 3. ACL 与访问策略

- [ ] 3.1 扩展用户上下文字段，至少保证 `user_id/department/roles/project_ids` 可用于 ACL 决策
- [ ] 3.2 新增 `AccessPolicyResolver`，输入用户上下文，输出统一 ACL 过滤结果
- [ ] 3.3 一期实现 `public / department / private / project / admin_all_access`
- [ ] 3.4 明确 `knowledge_admin/hr_admin` 默认可查看全员 `private` 文档
- [ ] 3.5 若 `project_ids` 未就绪，则显式禁用 `project` scope，不允许假装生效
- [ ] 3.6 确保 Milvus dense、sparse/BM25、本地回退三条检索路径都复用同一个 ACL 过滤结果
- [ ] 3.7 对“权限过滤后为空”和“检索为空”返回不同失败原因
- [ ] 3.8 文档级权限字段变更后，同步更新所有关联 chunk 镜像字段；大批量更新走异步任务并在期间标记 `sync_pending`

## 4. Query Rewrite

- [ ] 4.1 新增 `QueryRewriteService`
- [ ] 4.2 默认启用轻量 rewrite，并保留原 query
- [ ] 4.3 对包含精确编号、版本号、岗位级别的 query 增加保护规则，避免误改写
- [ ] 4.4 实现低召回时的一次性 rewrite retry
- [ ] 4.5 将 rewrite 产出的 `keywords` 接入 sparse/BM25 检索，但必须做去停用词和去噪
- [ ] 4.6 把 HyDE / 多路 rewrite 写成受配置控制的增强模式，不在首版默认全开
- [ ] 4.7 首版只对人事、财务、合规、制度、合同类高价值问题开放 HyDE
- [ ] 4.8 将关键词提取规则定死：最多 5 个，必须剔除礼貌词/虚词/空泛动作词
- [ ] 4.9 明确 `keywords` 只作为 sparse/BM25 的补充输入，不替换原 query
- [ ] 4.10 写死 rewrite 失败兜底：超时或报错时直接使用原始问句
- [ ] 4.11 建立禁止改写名单：工号、项目编码、合同编号、制度编号、版本号等固定编码
- [ ] 4.12 将 `rewrite_retry_max` 定死为 `1`

## 5. Hybrid Retrieval

- [ ] 5.1 扩展 Milvus collection schema，支持 dense 向量、sparse/BM25 字段和所需 scalar metadata
- [ ] 5.2 新增 dense 与 sparse 双路检索能力
- [ ] 5.3 将 ACL + status + version filter 前置到检索请求中
- [ ] 5.4 定义三档 retrieval profile：`faq_low_cost`、`standard`、`high_recall`
- [ ] 5.5 为制度/模板类问题提高 sparse 权重，为口语流程类问题提高 dense 权重
- [ ] 5.6 将“放宽 profile”的升级顺序固定为 `faq_low_cost -> standard -> high_recall`
- [ ] 5.7 确保本地回退搜索也执行 ACL、状态、版本和有效期过滤
- [ ] 5.8 增加 `history_lookup` 模式，用于用户显式查询旧版本、历史制度或作废文件
- [ ] 5.9 为 dense / sparse 增加全局偏向开关：`balanced / semantic_bias / keyword_bias`
- [ ] 5.10 定义自动升档后的自动降级规则：每次请求结束后恢复默认 profile

## 6. Merge 与 Rerank

- [ ] 6.1 新增 RRF merge 逻辑，明确 `rank_constant` 与候选数量分离
- [ ] 6.2 默认使用 `rank_constant=60`，并将其暴露为配置项
- [ ] 6.3 新增 rerank 服务，只对 merge 后的候选做二次排序
- [ ] 6.4 首版将 rerank 输入控制在 30~50 条，避免无上限扩张
- [ ] 6.5 `high_recall` 模式下 rerank 输入默认 50、最大不超过 80
- [ ] 6.6 输出最终 Top 3~5 片段供生成使用

## 7. 回答与引用

- [ ] 7.1 重写 `run_rag_chain` 的输入输出结构，不再只返回简单 `documents/sources`
- [ ] 7.2 生成统一的 citation payload，至少包含 `doc_id/chunk_id/source_file/section_path/version`
- [ ] 7.3 在回答 prompt 中强调“只基于最终候选回答，不得拼接候选外内容”
- [ ] 7.4 对低置信度或候选不足场景返回保守回答，而不是强答
- [ ] 7.5 `section_path` 为空时，前端统一显示 `source_file · 第N片段/页片段`

## 8. 观测性与审计

- [ ] 8.1 新增 `retrieval_debug_trace` 结构，记录 rewrite、ACL、dense、sparse、RRF、rerank 全过程
- [ ] 8.2 新增访问审计日志服务，记录 user/query/docs/deny_reason/timestamp
- [ ] 8.3 对越权尝试、权限过滤为空、版本过滤为空分别打不同事件
- [ ] 8.4 为后续前端调试面板预留稳定字段名
- [ ] 8.5 为 rewrite、dense、sparse、merge、rerank 分别记录耗时，支持后续 `p50/p95` benchmark
- [ ] 8.6 在 benchmark 文档里写明语料规模、硬件条件和模型版本，避免误读性能目标
- [ ] 8.7 为 chunk 权限同步任务记录批量更新耗时和失败重试日志
- [ ] 8.8 将日志拆分为 `retrieval_debug_trace / access_audit_log / user_behavior_log` 三类，禁止混存
- [ ] 8.9 增加环境开关：`dev/staging` 全量 debug，`prod` 默认精简或采样
- [ ] 8.10 在 debug trace 中记录 dense/sparse/RRF/rerank 分数
- [ ] 8.11 在 audit log 中补齐 `user_roles/client_ip/request_start/request_end/blocked_doc_ids`
- [ ] 8.12 写死首版阈值：`rewrite_retry_max=1`、merge 候选 `<5` 为低召回、rerank 候选 `<3` 为低置信度
- [ ] 8.13 定义日志访问权限，确保普通员工无法查看内部 debug trace
- [ ] 8.14 增加敏感查询脱敏规则，生产日志不得直接落完整薪资/隐私/涉密正文
- [ ] 8.15 为三类日志分别定义默认保留时长与可配置项
- [ ] 8.16 为 dense/sparse/rerank 低分判定补齐配置项与 benchmark 校准流程

## 9. 测试

- [ ] 9.1 新增 ingestion 测试：metadata 完整性、版本默认值、状态过滤
- [ ] 9.2 新增 ACL 测试：部门、公有、私有、项目组、管理员
- [ ] 9.3 新增 rewrite 测试：口语化 query、精确编号 query、低召回 retry
- [ ] 9.4 新增 hybrid retrieval 测试：dense 命中、sparse 命中、混合命中
- [ ] 9.5 新增 rerank 测试：制度片段排序优于噪声片段
- [ ] 9.6 新增引用测试：回答必须带正确 doc/chunk 追溯信息
- [ ] 9.7 新增审计日志测试：正常访问、越权访问、空结果访问
- [ ] 9.8 新增回归测试：现有上传/删除/列表接口继续可用

## 10. 验收

- [ ] 10.1 手动：普通员工检索本部门制度，能返回最新有效版本
- [ ] 10.2 手动：普通员工检索其他部门私有制度，不能返回任何候选正文
- [ ] 10.3 手动：问“出差打车能不能报”，能命中“市内交通费报销标准”
- [ ] 10.4 手动：问带版本号问题，如“差旅制度 v2.1”，不会被 rewrite 改坏
- [ ] 10.5 手动：查看 debug trace，能看到 rewrite -> ACL -> dense/sparse -> merge -> rerank 全链路

## 11. 后续 TODO（写进文档，但不在本次实现范围）

- [ ] 11.1 ACL 权限继承
- [ ] 11.2 临时授权
- [ ] 11.3 审批流驱动权限变更
- [ ] 11.4 自动化索引重建调度
- [ ] 11.5 检索效果离线评测面板
- [ ] 11.6 FAQ / semantic cache
- [ ] 11.7 heading-aware / table-aware / attachment-aware chunking
- [ ] 11.8 反馈学习型 query rewrite
