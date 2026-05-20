"""FastAPI 应用入口。"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import get_settings
from app.core.lifespan import app_lifespan
from app.core.logging import configure_logging
from app.core.middleware import RequestLoggingMiddleware, global_exception_handler


def create_app() -> FastAPI:
    """创建 FastAPI 应用实例。"""
    # 1. 加载项目配置
    settings = get_settings()
    # 2. 初始化日志系统
    configure_logging()

    # 3. 创建 FastAPI 应用实例
    application = FastAPI(
        title=settings.app_name,        # 应用名称（来自配置）
        version=settings.app_version,   # 应用版本（来自配置）
        lifespan=app_lifespan,          # 绑定应用生命周期
        description="面向企业员工的智能办公助手后端服务。",  # 接口文档描述
    )

    # 4. 注册跨域中间件
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,  # 允许的前端域名（配置文件管理）
        allow_credentials=True,               # 允许携带Cookie/凭证
        allow_methods=["*"],                  # 允许所有请求方法（GET/POST/PUT等）
        allow_headers=["*"],                  # 允许所有请求头
    )
    
    # 5. 注册自定义请求日志中间件
    application.add_middleware(RequestLoggingMiddleware)
    
    # 6. 注册全局异常处理器
    application.add_exception_handler(Exception, global_exception_handler)
    
    # 7. 注册API路由
    application.include_router(api_router, prefix=settings.api_prefix)
    
    # 返回配置完成的应用
    return application

#创建应用实例
app = create_app()
