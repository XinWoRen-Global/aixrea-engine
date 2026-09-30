"""
能力推荐API接口（Capability Recommendation API）
=================================================

提供能力推荐的REST API接口，包括：
1. Agent创建时推荐能力
2. 任务执行时推荐能力
3. 能力组合推荐
4. 个性化推荐
5. 依赖图谱查询
"""

import logging

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from deerflow.capability.recommendation.dependency_graph import (
    DependencyType,
    get_global_dependency_graph,
)
from deerflow.capability.recommendation.service import (
    get_global_recommendation_service,
)
from deerflow.capability.registry import CapabilityType

logger = logging.getLogger(__name__)


# 请求模型
class AgentCreationRecommendationRequest(BaseModel):
    """Agent创建推荐请求"""

    agent_name: str = Field(..., description="Agent名称")
    agent_description: str = Field(..., description="Agent描述")
    domain: str | None = Field(None, description="业务域")
    existing_capabilities: list[str] = Field(default_factory=list, description="已有的能力列表")
    user_id: str | None = Field(None, description="用户ID")
    max_results: int = Field(10, ge=1, le=50, description="最大推荐数量")


class TaskExecutionRecommendationRequest(BaseModel):
    """任务执行推荐请求"""

    task_description: str = Field(..., description="任务描述")
    domain: str | None = Field(None, description="业务域")
    available_capabilities: list[str] = Field(default_factory=list, description="可用的能力列表")
    user_id: str | None = Field(None, description="用户ID")
    max_results: int = Field(5, ge=1, le=20, description="最大推荐数量")


class CapabilityComboRecommendationRequest(BaseModel):
    """能力组合推荐请求"""

    capability_name: str = Field(..., description="能力名称")
    capability_type: str = Field(..., description="能力类型")
    domain: str | None = Field(None, description="业务域")
    max_results: int = Field(5, ge=1, le=20, description="最大推荐数量")


class PersonalizedRecommendationRequest(BaseModel):
    """个性化推荐请求"""

    user_id: str = Field(..., description="用户ID")
    domain: str | None = Field(None, description="业务域")
    max_results: int = Field(10, ge=1, le=50, description="最大推荐数量")


class RecordUsageRequest(BaseModel):
    """记录使用请求"""

    user_id: str = Field(..., description="用户ID")
    capability_name: str = Field(..., description="能力名称")


def create_recommendation_router() -> APIRouter:
    """
    创建推荐API路由

    Returns:
        FastAPI APIRouter
    """
    router = APIRouter(prefix="/api/capabilities/recommendations", tags=["能力推荐"])

    recommendation_service = get_global_recommendation_service()
    dependency_graph = get_global_dependency_graph()

    @router.post("/agent-creation", summary="Agent创建时推荐能力")
    async def recommend_for_agent_creation(request: AgentCreationRecommendationRequest):
        """
        Agent创建时推荐可复用的能力

        - 根据Agent名称和描述进行语义匹配
        - 基于业务域推荐同域能力
        - 排除已有的能力
        - 支持个性化推荐
        """
        try:
            result = recommendation_service.recommend_for_agent_creation(
                agent_name=request.agent_name,
                agent_description=request.agent_description,
                domain=request.domain,
                existing_capabilities=request.existing_capabilities,
                user_id=request.user_id,
                max_results=request.max_results,
            )
            return result.to_dict()
        except Exception as e:
            logger.error("Failed to get agent creation recommendations: %s", e, exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))

    @router.post("/task-execution", summary="任务执行时推荐能力")
    async def recommend_for_task_execution(request: TaskExecutionRecommendationRequest):
        """
        任务执行时推荐匹配的能力

        - 根据任务描述进行语义匹配
        - 只推荐可用的能力
        - 支持个性化推荐
        """
        try:
            result = recommendation_service.recommend_for_task_execution(
                task_description=request.task_description,
                domain=request.domain,
                available_capabilities=request.available_capabilities,
                user_id=request.user_id,
                max_results=request.max_results,
            )
            return result.to_dict()
        except Exception as e:
            logger.error("Failed to get task execution recommendations: %s", e, exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))

    @router.post("/capability-combo", summary="推荐能力组合")
    async def recommend_capability_combo(request: CapabilityComboRecommendationRequest):
        """
        推荐与指定能力配合使用的其他能力

        - 基于预定义的组合规则
        - 基于依赖图谱的互补能力
        - 基于业务域的相关能力
        """
        try:
            # 解析能力类型
            try:
                cap_type = CapabilityType(request.capability_type)
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Invalid capability type: {request.capability_type}")

            result = recommendation_service.recommend_capability_combo(
                capability_name=request.capability_name,
                capability_type=cap_type,
                domain=request.domain,
                max_results=request.max_results,
            )
            return result.to_dict()
        except HTTPException:
            raise
        except Exception as e:
            logger.error("Failed to get capability combo recommendations: %s", e, exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))

    @router.post("/personalized", summary="个性化推荐")
    async def get_personalized_recommendations(request: PersonalizedRecommendationRequest):
        """
        基于用户历史的个性化推荐

        - 基于用户使用历史推荐相似能力
        - 新用户推荐热门能力
        - 支持业务域过滤
        """
        try:
            result = recommendation_service.get_personalized_recommendations(
                user_id=request.user_id,
                domain=request.domain,
                max_results=request.max_results,
            )
            return result.to_dict()
        except Exception as e:
            logger.error("Failed to get personalized recommendations: %s", e, exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))

    @router.post("/record-usage", summary="记录能力使用")
    async def record_usage(request: RecordUsageRequest):
        """
        记录用户使用能力的历史

        - 用于个性化推荐
        - 用于热门能力统计
        """
        try:
            recommendation_service.record_usage(request.user_id, request.capability_name)
            return {"success": True, "message": "Usage recorded"}
        except Exception as e:
            logger.error("Failed to record usage: %s", e, exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/dependency-graph", summary="获取依赖图谱")
    async def get_dependency_graph(
        capability_name: str | None = Query(None, description="能力名称（不填则返回全图）"),
        dep_type: str | None = Query(None, description="依赖类型过滤"),
    ):
        """
        获取能力依赖图谱

        - 支持查询单个能力的依赖
        - 支持查询全图
        - 支持按依赖类型过滤
        """
        try:
            if capability_name:
                # 查询单个能力的依赖
                dep_type_enum = None
                if dep_type:
                    try:
                        dep_type_enum = DependencyType(dep_type)
                    except ValueError:
                        raise HTTPException(status_code=400, detail=f"Invalid dependency type: {dep_type}")

                dependencies = dependency_graph.get_dependencies(capability_name, dep_type_enum)
                dependents = dependency_graph.get_dependents(capability_name, dep_type_enum)

                return {
                    "capability": capability_name,
                    "dependencies": [e.to_dict() for e in dependencies],
                    "dependents": [e.to_dict() for e in dependents],
                }
            else:
                # 返回全图统计
                return dependency_graph.get_statistics()
        except HTTPException:
            raise
        except Exception as e:
            logger.error("Failed to get dependency graph: %s", e, exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))

    @router.post("/dependency-graph/build", summary="从注册中心构建依赖图谱")
    async def build_dependency_graph():
        """
        从注册中心自动构建依赖图谱

        - 基于业务域建立互补关系
        - 基于标签建立相似关系
        - 自动检测依赖环
        """
        try:
            dependency_graph.build_from_registry()
            return {
                "success": True,
                "statistics": dependency_graph.get_statistics(),
            }
        except Exception as e:
            logger.error("Failed to build dependency graph: %s", e, exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/status", summary="获取推荐服务状态")
    async def get_status():
        """获取推荐服务状态"""
        return {
            "service": "capability_recommendation",
            "status": "running",
            "registry_statistics": recommendation_service.registry.get_statistics(),
            "dependency_graph_statistics": dependency_graph.get_statistics(),
        }

    return router
