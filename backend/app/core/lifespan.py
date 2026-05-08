"""应用生命周期钩子。"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI

from app.core.config import get_settings
from app.core.database import ensure_business_database
from app.services.business_db_service import get_business_database_service
from app.services.knowledge_service import get_knowledge_service

logger = logging.getLogger(__name__)


@asynccontextmanager
async def app_lifespan(_: FastAPI) -> AsyncIterator[None]:
    """在启动和关闭时记录关键信息。"""
    settings = get_settings()
    ensure_business_database()
    get_business_database_service()
    get_knowledge_service().rebuild_index()
    logger.info("应用启动：%s，环境=%s", settings.app_name, settings.app_env)
    yield
    logger.info("应用关闭：%s", settings.app_name)
