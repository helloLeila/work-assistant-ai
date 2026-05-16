# 安装后端依赖
backend-install:
	python3 -m pip install -r requirements.txt

# 启动后端开发服务（直接用 venv 里的 uvicorn，无需手动 source 激活）
# 后端正式配置统一放在 backend/.env；这里顺手清掉常见代理变量，避免国内兼容网关误走代理。
dev-backend:
	@unset ALL_PROXY HTTP_PROXY HTTPS_PROXY all_proxy http_proxy https_proxy; \
	NO_PROXY="api.minimaxi.com,.minimaxi.com,localhost,127.0.0.1" \
	.venv/bin/uvicorn app.main:app --reload --app-dir backend

# 强杀占用 8000 端口的后端进程（撞到 Address already in use 时使用）
kill-backend:
	@lsof -nP -iTCP:8000 -t | xargs -r kill -9 2>/dev/null || true
	@pkill -9 -f 'uvicorn app.main:app' 2>/dev/null || true
	@echo "8000 端口已释放"

# 运行后端测试
test:
	PYTHONPATH=backend pytest backend/tests -q

# 安装前端依赖
frontend-install:
	cd frontend && npm install

# 启动前端开发服务
dev-frontend:
	cd frontend && npm run dev

# 校验前端构建
build-frontend:
	cd frontend && npm run build

# 启动基础设施
compose-up:
	docker compose up -d

# 查看基础设施状态
compose-ps:
	docker compose ps
