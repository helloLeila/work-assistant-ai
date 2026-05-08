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
    settings = get_settings()
    configure_logging()

    application = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        lifespan=app_lifespan,
        description="面向企业员工的智能办公助手后端服务。",
    )

    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    application.add_middleware(RequestLoggingMiddleware)
    application.add_exception_handler(Exception, global_exception_handler)
    application.include_router(api_router, prefix=settings.api_prefix)
    return application


app = create_app()
