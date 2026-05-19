## ADDED Requirements

### Requirement: 文档与 chunk 元数据必须支持状态、版本与可见范围

知识库系统 SHALL 为每份文档记录完整的治理字段，至少包括：`doc_id`、`title`、`source_file`、`department`、`visibility_scope`、`status`、`version`、`is_latest`、`effective_at`、`expires_at`、`upload_time`。每个 chunk SHALL 镜像其中与检索过滤直接相关的字段，包括 `status`、`version`、`is_latest`、`visibility_scope` 与 `department`。

#### Scenario: 新上传文档默认进入 active 最新版本
- **WHEN** 管理员上传一份新的制度文档，且未显式指定状态和版本
- **THEN** 系统默认将其写为 `status=active`
- **AND** 为其分配默认版本值 `v1.0`
- **AND** 将该文档标记为 `is_latest=true`
- **AND** 若未传 `effective_at`，则默认立即生效

#### Scenario: 已停用文档不会作为默认候选
- **WHEN** 文档被标记为 `status=deprecated` 或已过 `expires_at`
- **THEN** 该文档对应的 chunk 不得进入默认检索候选集

#### Scenario: 旧数据默认按最保守可用规则迁移
- **WHEN** 系统迁移旧 metadata 数据
- **THEN** 若历史文档已存在 `department`
- **AND** 系统默认将其迁移为 `visibility_scope=department`
- **AND** 仅在缺失部门信息时才降级为 `public`

### Requirement: Ingestion 必须拆分为可独立调试的子步骤

知识库接入流程 SHALL 明确拆分为“保存原文档”“解析文本”“生成 metadata”“切分 chunk”“写入索引”几个步骤。系统 MUST 能在调试日志中区分是哪一步失败。

#### Scenario: 文档解析失败
- **WHEN** 用户上传一份格式损坏的文档
- **THEN** 系统记录失败步骤为 `parse_document`
- **AND** 不得写入半成品 chunk 数据

### Requirement: 上传流程必须支持失败回滚与单步重试

知识库接入流程 SHALL 在多步骤失败时保持一致性。系统 MUST 不发布半成品 chunk 到正式检索集合。解析失败、索引失败等中间态 MUST 支持从失败步骤重试，而不强制用户重复上传原文件。

#### Scenario: 解析失败后无需重传文件
- **WHEN** 原始文件保存成功，但文本解析失败
- **THEN** 系统保留原文件
- **AND** 将 ingestion 状态记为 `parse_failed`
- **AND** 允许管理员只重试解析步骤

### Requirement: 首版默认 chunking 必须固定为 512 tokens + 128 overlap

系统 SHALL 将首版默认切分策略固定为 `512 tokens + 128 overlap`。该默认值是本项目的一期工程标准，而不是声称为所有 RAG 系统通用的唯一行业标准。只有在特定文档类型确有必要时，才允许通过策略解析器覆盖。

#### Scenario: 默认文本切分采用统一标准
- **WHEN** 系统处理一份普通制度文档
- **THEN** 默认按 `512 tokens + 128 overlap` 切分

### Requirement: token 计数工具必须统一

系统 SHALL 统一使用同一套 token 计数工具来决定 chunk 边界。首版 MUST 使用 `tiktoken`，以避免开发、测试和重建索引时统计口径不一致。

#### Scenario: 同一文档在不同环境切分结果一致
- **WHEN** 两个开发环境分别对同一份文档执行切分
- **THEN** 在相同配置下应得到一致的 chunk 边界

### Requirement: 只有特定文档类型允许覆盖默认切分

系统 SHALL 限制可覆盖默认 `512/128` 切分策略的文档范围。首版仅允许合同/协议、表格附件、流程表单、超短通知这几类文档使用特化切分。

#### Scenario: 普通制度文档不得随意放大 chunk
- **WHEN** 开发者处理一份普通制度正文
- **THEN** 不得因为主观偏好改用其他 chunk 默认值

### Requirement: section_path 必须依赖解析器显式提取或安全回退

系统 SHALL 在解析器能够提取标题层级时写入 `section_path`。如果解析器无法稳定提取标题层级，系统 MUST 回退到 `source_file + chunk_index/page_num` 的引用方式，而不是伪造标题路径。

#### Scenario: 标题层级不可得时回退引用
- **WHEN** 系统处理一份无法提取标题结构的扫描文档
- **THEN** `section_path` 可以为空
- **AND** 最终引用仍然能定位到文件和 chunk 顺序

### Requirement: 旧数据迁移必须采用一次性后台迁移

系统 SHALL 通过一次性后台迁移脚本补齐旧 metadata，而不是在用户查询时临时补字段。未迁移完成的数据 MUST 标记为 `migration_pending`，且默认不进入新检索链路。

#### Scenario: 未迁移文档不混入新链路
- **WHEN** 某份旧文档尚未完成迁移
- **THEN** 该文档不得参与新检索流程

### Requirement: 旧文档 metadata 必须可迁移

系统 SHALL 支持从当前简化 metadata 结构迁移到新结构。迁移后旧文档至少应获得可用的默认字段值，而不能因为缺字段直接失效。

#### Scenario: 旧知识库文档升级后仍可搜索
- **WHEN** 系统中存在只包含 `doc_id/source_file/department/upload_time/doc_type` 的旧文档 metadata
- **THEN** 迁移逻辑为其补齐默认的 `status/version/is_latest/visibility_scope`
- **AND** 旧文档仍可参与检索
