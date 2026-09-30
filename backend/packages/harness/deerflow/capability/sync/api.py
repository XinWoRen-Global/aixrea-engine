"""
能力同步API接口（Capability Sync API）
=======================================

提供能力同步的REST API接口，包括：
1. 触发同步（全量/增量）
2. 查询同步状态
3. 查询同步历史
4. 获取外部能力列表
"""

import logging

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from deerflow.capability.sync.service import (
    SyncDirection,
    SyncMode,
    get_global_sync_service,
)

logger = logging.getLogger(__name__)


class SyncRequest(BaseModel):
    """同步请求"""

    direction: str = Field("bidirectional", description="同步方向: to_external, from_external, bidirectional")
    mode: str = Field("full", description="同步模式: full, incremental")


def create_sync_router() -> APIRouter:
    """
    创建同步API路由

    Returns:
        FastAPI APIRouter
    """
    router = APIRouter(prefix="/api/capabilities/sync", tags=["能力同步"])

    sync_service = get_global_sync_service()

    @router.post("/trigger", summary="触发同步")
    async def trigger_sync(request: SyncRequest):
        """
        触发能力同步

        - 支持全量同步和增量同步
        - 支持单向同步和双向同步
        - 返回同步结果
        """
        try:
            # 解析方向
            try:
                direction = SyncDirection(request.direction)
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Invalid direction: {request.direction}")

            # 解析模式
            try:
                mode = SyncMode(request.mode)
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Invalid mode: {request.mode}")

            # 执行同步
            if direction == SyncDirection.TO_EXTERNAL:
                result = sync_service.sync_to_external(mode)
            elif direction == SyncDirection.FROM_EXTERNAL:
                result = sync_service.sync_from_external(mode)
            else:  # BIDIRECTIONAL
                to_result, from_result = sync_service.sync_bidirectional(mode)
                return {
                    "success": to_result.success and from_result.success,
                    "to_external": to_result.to_dict(),
                    "from_external": from_result.to_dict(),
                }

            return result.to_dict()

        except HTTPException:
            raise
        except Exception as e:
            logger.error("Failed to trigger sync: %s", e, exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/status", summary="获取同步状态")
    async def get_sync_status():
        """获取同步状态"""
        try:
            return sync_service.get_sync_status()
        except Exception as e:
            logger.error("Failed to get sync status: %s", e, exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/history", summary="获取同步历史")
    async def get_sync_history(
        limit: int = Query(10, ge=1, le=100, description="返回数量"),
    ):
        """获取同步历史"""
        try:
            return {
                "history": sync_service.get_sync_history(limit),
            }
        except Exception as e:
            logger.error("Failed to get sync history: %s", e, exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/external-capabilities", summary="获取外部能力列表")
    async def get_external_capabilities(
        limit: int = Query(50, ge=1, le=200, description="返回数量"),
    ):
        """获取外部系统的能力列表"""
        try:
            # 从适配器获取外部能力
            adapter = sync_service.adapter
            capabilities = adapter.get_all_capabilities()

            return {
                "total": len(capabilities),
                "capabilities": [
                    {
                        "external_id": c.external_id,
                        "name": c.name,
                        "display_name": c.display_name,
                        "description": c.description,
                        "type": c.type,
                        "category": c.category,
                        "status": c.status,
                        "price_type": c.price_type,
                        "rating": c.rating,
                        "installs": c.installs,
                    }
                    for c in capabilities[:limit]
                ],
            }
        except Exception as e:
            logger.error("Failed to get external capabilities: %s", e, exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))

    return router
