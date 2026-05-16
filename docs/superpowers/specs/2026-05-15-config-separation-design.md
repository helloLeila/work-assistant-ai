# 严格前后端分离配置设计

## 目标

把项目配置收口成两份正式来源：

- `backend/.env`：后端运行时配置
- `frontend/.env`：前端 Vite 构建配置

根目录不再承载后端正式配置，避免出现第三份来源。

## 设计决策

### 1. 后端唯一读取 `backend/.env`

后端 `Settings` 的 `env_file` 改到 `backend/.env`。这样配置位置和代码位置一致，开发者进入 `backend/` 目录就能找到后端需要的全部变量。

### 2. `backend/.env` 优先于外层 shell 环境变量

本地开发里最容易踩坑的是 shell 残留的 `OPENAI_*`、`ANTHROPIC_*`、`BOCHA_*`。这会让“明明改了文件但程序没生效”变成常态。为避免这一点，`Settings` 改为优先读取 `backend/.env`，shell 环境变量只做缺省兜底。

### 3. 容器与手册同步到同一来源

`docker-compose.yml` 中 backend 服务的 `env_file` 改为 `./backend/.env`。README、开发手册、后端启动手册全部统一为：

- 后端模板：`backend/.env.example`
- 后端正式配置：`backend/.env`
- 前端模板：`frontend/.env.example`
- 前端正式配置：`frontend/.env`

### 4. 删除根目录后端模板，避免重复来源

根目录 `.env.example` 删除，防止“模板还在根目录、实际配置却在 backend/”的双路径歧义。

## 影响范围

- 后端配置加载：`backend/app/core/config.py`
- 本地启动命令说明：`README.md`、`docs/开发手册.md`、`docs/后端启动手册.md`
- 容器运行：`docker-compose.yml`
- 配置模板：新增 `backend/.env.example`
- 测试：补充配置优先级测试

## 验证标准

1. `Settings` 默认配置文件路径为 `backend/.env`
2. 当 `backend/.env` 与 shell 环境变量冲突时，以 `backend/.env` 为准
3. `docker compose` 启动 backend 时读取 `backend/.env`
4. 所有启动手册只再出现 `backend/.env` 与 `frontend/.env`
