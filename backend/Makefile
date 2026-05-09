# backend/Makefile —— 转发到根 Makefile，方便在 backend/ 目录下直接执行 make 命令
# 设计原则：单一来源（Single Source of Truth），所有真正的规则都写在根 Makefile，
# 这里只做透传，避免规则重复带来的不一致。

ROOT := $(abspath $(dir $(lastword $(MAKEFILE_LIST)))/..)

.PHONY: dev kill test install help

# 默认目标：在 backend/ 下直接 `make` 等价于 `make dev`
dev:
	$(MAKE) -C $(ROOT) dev-backend

kill:
	$(MAKE) -C $(ROOT) kill-backend

test:
	$(MAKE) -C $(ROOT) test

install:
	$(MAKE) -C $(ROOT) backend-install

help:
	@echo "backend/ 目录下可用命令（均转发到根 Makefile）："
	@echo "  make dev      启动后端开发服务  -> 根: dev-backend"
	@echo "  make kill     释放 8000 端口    -> 根: kill-backend"
	@echo "  make test     运行后端测试      -> 根: test"
	@echo "  make install  安装后端依赖      -> 根: backend-install"
