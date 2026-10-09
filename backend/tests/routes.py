"""Walk the application's routes the same way on every FastAPI version.

FastAPI 0.143 stopped flattening included routers into ``app.routes``: it holds
lazy ``_IncludedRouter`` objects, and the routes inside are reached through
``fastapi.routing.iter_route_contexts``. A test that iterated ``app.routes``
directly saw only ``/api/health`` there, so every check generated from the route
table silently collapsed to nothing, and the suite still passed.
"""

from __future__ import annotations

from collections.abc import Iterator


def api_routes(app) -> Iterator[tuple[str, str, object]]:
    """(method, full path, route) for every routed endpoint, mounts excluded."""
    try:
        from fastapi.routing import iter_route_contexts
    except ImportError:  # FastAPI before 0.143: routes are already flat
        iter_route_contexts = None

    if iter_route_contexts is not None:
        # The context, not ctx.route: its dependant includes dependencies added at
        # include_router time (sign-in, ownership), which the bare route lacks.
        entries = ((ctx.path, ctx.methods, ctx) for ctx in iter_route_contexts(app.routes))
    else:
        entries = (
            (route.path, getattr(route, "methods", None), route) for route in app.routes
        )
    for path, methods, route in entries:
        if not methods or not hasattr(route, "dependant"):
            continue
        for method in sorted(set(methods) - {"HEAD", "OPTIONS"}):
            yield method, path, route


def mounted_paths(app) -> set[str]:
    """Paths of Starlette mounts (static files), which are never lazily included."""
    return {
        route.path
        for route in app.routes
        if type(route).__name__ == "Mount" and route.path not in ("", "/")
    }
