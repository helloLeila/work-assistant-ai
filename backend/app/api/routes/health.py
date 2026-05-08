"""系统级路由。"""

from __future__ import annotations

from fastapi import APIRouter

from app.agents.office_assistant_graph import build_graph_blueprint
from app.core.config import get_settings
from app.models.common import HealthResponse, ModuleCard, ProjectOverviewResponse
from app.services.knowledge_service import get_knowledge_module_snapshot
from app.services.payroll_service import get_payroll_module_snapshot
from app.services.personal_info_service import get_personal_module_snapshot
from app.services.travel_service import get_travel_module_snapshot

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """返回健康状态。"""
    return HealthResponse(
        status="ok",
        project="企业智能办公助手",
        version=get_settings().app_version,
    )


@router.get("/overview", response_model=ProjectOverviewResponse)
async def overview() -> ProjectOverviewResponse:
    """返回项目总览信息。"""
    modules = [
        ModuleCard(**get_knowledge_module_snapshot()),
        ModuleCard(**get_payroll_module_snapshot()),
        ModuleCard(**get_personal_module_snapshot()),
        ModuleCard(**get_travel_module_snapshot()),
    ]

    return ProjectOverviewResponse(
        project_name="企业智能办公助手",
        architecture="前后端分离、LangGraph 业务编排、LangChain 节点能力、Milvus 检索与 PostgreSQL/Redis 业务数据协同",
        graph_blueprint=build_graph_blueprint(),
        modules=modules,
    )
