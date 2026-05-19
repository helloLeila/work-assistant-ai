## ADDED Requirements

### Requirement: 权限过滤必须发生在检索前

知识库系统 SHALL 在执行任何 dense、sparse 或本地回退检索之前完成 ACL 决策。无权限的 chunk MUST 不得进入候选集、融合阶段或 rerank 阶段。

#### Scenario: 跨部门私有文档不可进入候选集
- **WHEN** 普通员工查询其他部门的私有制度
- **THEN** 该文档对应 chunk 不得出现在任何候选结果中
- **AND** 系统不得依赖生成模型“少说一点”来规避越权

### Requirement: 一期 ACL 必须支持 public、department、private、project、admin_all_access

系统 SHALL 至少支持以下可见范围：

- `public`
- `department`
- `private`
- `project`
- `admin_all_access`

#### Scenario: public 文档所有登录用户可读
- **WHEN** 文档 `visibility_scope=public`
- **THEN** 任意已登录用户都可检索到该文档

#### Scenario: department 文档仅本部门可读
- **WHEN** 文档 `visibility_scope=department` 且文档部门为 `finance`
- **THEN** 非 `finance` 用户不得检索到该文档

#### Scenario: private 文档仅所有者可读
- **WHEN** 文档 `visibility_scope=private`
- **THEN** 只有 `owner_user_id` 对应的用户可检索到该文档

#### Scenario: 管理员可查看 private 文档
- **WHEN** 当前用户角色为 `knowledge_admin` 或 `hr_admin`
- **AND** 文档 `visibility_scope=private`
- **THEN** 系统允许管理员检索到该文档

#### Scenario: project 文档仅项目成员可读
- **WHEN** 文档 `visibility_scope=project` 且 `project_ids=["p-001"]`
- **THEN** 只有属于 `p-001` 的用户可检索到该文档

#### Scenario: 管理员可跨域查看
- **WHEN** 当前用户角色为 `knowledge_admin` 或 `hr_admin`
- **THEN** 系统允许其跨部门读取所有文档

### Requirement: 权限拒绝与检索为空必须区分原因

系统 SHALL 区分“因为无权限而为空”和“因为没有相关资料而为空”两类结果，以支持后续审计和用户提示。

#### Scenario: 权限过滤后为空
- **WHEN** 用户问题本可命中文档，但该文档全被 ACL 过滤掉
- **THEN** 系统记录 `deny_reason=acl_filtered`
- **AND** 用户提示为“暂无可见资料或没有权限”

### Requirement: 三条检索链路必须复用同一套 ACL 结果

系统 SHALL 保证 dense 检索、sparse/BM25 检索和本地词法兜底检索都复用同一个 `AccessPolicyResolver` 结果。系统 MUST NOT 为三条链路分别手写权限判断逻辑。

#### Scenario: Milvus 不可用时权限仍然一致
- **WHEN** 系统从 Milvus 主路径降级到本地回退检索
- **THEN** 回退路径的权限过滤结果与主路径保持一致

### Requirement: 文档权限字段变更后必须同步所有 chunk 镜像字段

当文档级 `visibility_scope`、`department`、`owner_user_id`、`status`、`version` 或 `is_latest` 发生变化时，系统 SHALL 自动同步所有关联 chunk 的镜像字段。对于大批量更新，系统 SHOULD 使用异步任务；同步完成前文档可标记为 `sync_pending` 并默认不参与检索。

#### Scenario: 文档从 public 改为 private 后 chunk 不再可见
- **WHEN** 管理员把一份文档从 `public` 改成 `private`
- **THEN** 所有关联 chunk 的镜像权限字段都被同步更新
- **AND** 在同步完成前，该文档默认不参与检索

### Requirement: 权限继承与临时授权必须进入 TODO，但不强制一期实现

系统文档 SHALL 明确记录 ACL 权限继承、临时授权与审批流驱动的授权变化作为后续 TODO。它们可以在数据模型中预留字段，但 MUST NOT 作为一期交付承诺。

#### Scenario: TODO 已被正式记录
- **WHEN** 开发者阅读一期设计和任务文档
- **THEN** 能明确看到“权限继承”和“临时授权”属于后续项而不是本轮必做
