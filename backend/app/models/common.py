"""通用响应模型。"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.models.domain import GraphBlueprint


class HealthResponse(BaseModel):
    """健康检查响应。"""

    status: str = Field(description="服务状态")
    project: str = Field(description="项目名称")
    version: str = Field(description="当前应用版本")


class ModuleCard(BaseModel):
    """前端展示用的模块卡片。"""

    name: str
    status: str
    highlight: str
    capability: str


class ProjectOverviewResponse(BaseModel):
    """项目概览响应。"""

    project_name: str
    architecture: str
    graph_blueprint: GraphBlueprint
    modules: list[ModuleCard]
