# Config Separation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将项目配置改成严格前后端分离：后端只读 `backend/.env`，前端只读 `frontend/.env`。

**Architecture:** 后端通过 `Settings` 统一读取 `backend/.env`，并把 dotenv 优先级放在 shell 环境变量之前；前端继续使用 Vite 的 `frontend/.env`；容器和文档全部指向同一套路径，避免第三份根目录配置继续存在。

**Tech Stack:** FastAPI, Pydantic Settings, Docker Compose, Vue/Vite

---

### Task 1: 收口后端配置源

**Files:**
- Modify: `backend/app/core/config.py`
- Test: `backend/tests/test_settings.py`

- [ ] 调整 `env_file` 到 `backend/.env`
- [ ] 调整 settings source 顺序，让 dotenv 先于 shell env
- [ ] 增加测试，验证 `backend/.env` 覆盖外层同名环境变量

### Task 2: 收口模板与容器配置

**Files:**
- Create: `backend/.env.example`
- Delete: `.env.example`
- Modify: `docker-compose.yml`
- Modify: `.gitignore`

- [ ] 新建后端模板到 `backend/.env.example`
- [ ] 删除根目录 `.env.example`，避免重复配置入口
- [ ] 将 backend 容器 `env_file` 改为 `./backend/.env`
- [ ] 补齐 `backend/.env` / `frontend/.env` 的忽略规则

### Task 3: 同步所有启动文档

**Files:**
- Modify: `README.md`
- Modify: `docs/开发手册.md`
- Modify: `docs/后端启动手册.md`

- [ ] 把所有后端配置说明统一改为 `backend/.env`
- [ ] 把所有复制模板命令统一改为 `cp backend/.env.example backend/.env`
- [ ] 在文档里明确前后端分离职责，解释为什么不再使用根目录 `.env`

### Task 4: 运行验证

**Files:**
- Test: `backend/tests/test_settings.py`

- [ ] 运行 `PYTHONPATH=backend pytest backend/tests/test_settings.py -q`
- [ ] 再跑一次 `PYTHONPATH=backend pytest backend/tests -q`，确认没有被配置切换带崩
