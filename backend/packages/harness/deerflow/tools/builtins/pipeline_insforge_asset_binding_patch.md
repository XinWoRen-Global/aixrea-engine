# pipeline_insforge.py 资产绑定修复补丁
# 问题：insert_asset() 写入 r2_assets 时缺少 project_id 字段
# 导致资产出现在公共内容广场，而非绑定到项目
# 修复：从 album_id 反向查询 project_id 并写入 r2_assets

# ──────────────────────────────────────────────────────────────
# 修改位置：insert_asset() 函数（约第 208-255 行）
# ──────────────────────────────────────────────────────────────

# 1. 在函数体开头（约第 231 行 asset_id = str(_uuid.uuid4()) 之前）添加：
#    查询 album 的 project_id
async def insert_asset(
    user_id: str,
    album_id: str,
    node_id: str,
    node_type: str,
    name: str,
    file_url: str,
    asset_type: str = "image",
    file_size: int | None = None,
    mime_type: str | None = None,
    bucket_name: str | None = None,
    object_key: str | None = None,
    metadata: dict | None = None,
) -> str | None:
    """插入资产记录到 r2_assets 表..."""
    import uuid as _uuid

    asset_id = str(_uuid.uuid4())
    now = datetime.now(UTC).isoformat()

    # ── 新增：查询 album 的 project_id ──
    project_id = None
    try:
        albums = await _request(
            "GET",
            "studio_albums",
            query={"id": f"eq.{album_id}", "select": "project_id"},
        )
        if albums:
            project_id = albums[0].get("project_id")
    except Exception:
        logger.warning("Failed to fetch project_id for album %s", album_id)
    # ── 结束新增 ──

    # 2. 在 body 字典中（约第 236 行）添加 project_id 字段：
    body = {
        "id": asset_id,
        "user_id": user_id,
        "album_id": album_id,
        "project_id": project_id,  # ← 新增：绑定资产到项目
        "file_name": name,
        # ... 其余字段不变
    }

# 3. 同时，在 insert_asset 上方的 update_album 函数中也应确保：
#    创建 album 时 project_id 不为 null（如果 album 由项目创建）
#    这个逻辑在 album 创建时已经处理（前端 /api/studio/albums 路由）