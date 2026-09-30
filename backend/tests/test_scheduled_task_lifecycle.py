from app.gateway.app import create_app


def _collect_paths(routes):
    paths = set()
    for route in routes:
        path = getattr(route, "path", None)
        if path:
            paths.add(path)
        # _IncludedRouter wraps an original_router
        original = getattr(route, "original_router", None)
        if original and hasattr(original, "routes"):
            paths |= _collect_paths(original.routes)
        # plain Router
        sub = getattr(route, "routes", None)
        if sub and not original:
            paths |= _collect_paths(sub)
    return paths


def test_gateway_app_includes_scheduled_task_router():
    app = create_app()
    paths = _collect_paths(app.routes)
    assert "/api/scheduled-tasks" in paths
