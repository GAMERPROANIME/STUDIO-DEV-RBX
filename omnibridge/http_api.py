"""HTTP surface: FastAPI REST API + dashboard + MCP Streamable HTTP (mounted) + bridge endpoints."""
from __future__ import annotations

import asyncio
import json
import secrets
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Body, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.middleware.base import BaseHTTPMiddleware

from .config import Config
from .core.app import OmniBridge
from .core.logger import log
from .core.permissions import PermissionDenied
from .mcp_server import build_mcp_server
from .openapi_actions import build_actions_openapi
from .setup_page import build_setup_page, should_reveal_token
from .webai import build_prompt, check_remote_mcp, openai_tools, run_calls

EXEMPT_PATHS = {"/", "/api/health", "/favicon.ico", "/index.html", "/style.css", "/app.js", "/docs",
                "/openapi.json", "/openapi/actions.json", "/demarrer"}


class CallRequest(BaseModel):
    name: str = Field(min_length=1)
    args: dict[str, Any] = Field(default_factory=dict)
    confirm: bool = False


class BridgeRegister(BaseModel):
    clientId: str = Field(min_length=1)
    info: dict[str, Any] = Field(default_factory=dict)


class BridgePoll(BaseModel):
    clientId: str = Field(min_length=1)
    timeoutMs: int = Field(default=25000, ge=1000, le=60000)


class BridgeResult(BaseModel):
    requestId: str
    ok: bool = True
    data: Any = None


class IndexRequest(BaseModel):
    source: str
    title: str
    text: str
    version: str = ""
    reliability: str = "project"


def _token_from_request(request: Request) -> str:
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    header = request.headers.get("x-omnibridge-token")
    if header:
        return header.strip()
    return request.query_params.get("token", "")


class AuthMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, cfg: Config):
        super().__init__(app)
        self._cfg = cfg

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if not self._cfg.require_token or path in EXEMPT_PATHS or path.startswith("/static"):
            return await call_next(request)
        provided = _token_from_request(request)
        if not provided or not secrets.compare_digest(provided, self._cfg.token):
            return JSONResponse(
                {"error": "unauthorized",
                 "message": "Missing or invalid token. Send 'Authorization: Bearer <token>' "
                            "(token: ~/.omnibridge/token.txt)."},
                status_code=401, headers={"WWW-Authenticate": "Bearer"})
        return await call_next(request)


def _error(exc: Exception) -> HTTPException:
    if isinstance(exc, PermissionDenied):
        return HTTPException(403, detail={"error": "permission_denied", "message": str(exc)})
    if isinstance(exc, (ValueError, KeyError)):
        return HTTPException(400, detail={"error": "bad_request", "message": str(exc)})
    return HTTPException(500, detail={"error": type(exc).__name__, "message": str(exc)})


def create_http_app(bridge: OmniBridge, cfg: Config | None = None):
    cfg = cfg or bridge.cfg
    mcp = build_mcp_server(bridge, cfg)
    mcp_app = mcp.streamable_http_app(streamable_http_path="/mcp", json_response=False, stateless_http=False)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        cfg.ensure_token()
        log.info("http server starting", extra={"host": cfg.http_host, "port": cfg.http_port,
                                                "tools": bridge.registry.size,
                                                "permissionLevel": cfg.permission_level})
        async with mcp.session_manager.run():
            yield
        await bridge.close()

    app = FastAPI(title="OMNIBRIDGE AI", version="1.0.0",
                  description="Universal MCP orchestrator — Python core.", lifespan=lifespan)
    app.add_middleware(AuthMiddleware, cfg=cfg)
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=r"^(chrome-extension://.*|moz-extension://.*|http://localhost(:\d+)?|http://127\.0\.0\.1(:\d+)?)$",
        allow_credentials=False, allow_methods=["*"], allow_headers=["*"],
    )

    # ---- MCP Streamable HTTP: same app routes, same session manager ----
    app.router.routes.extend(mcp_app.routes)

    # ---- dashboard ----
    if cfg.dashboard_dir.exists():
        app.mount("/static", StaticFiles(directory=str(cfg.dashboard_dir)), name="static")

    @app.get("/", include_in_schema=False)
    async def dashboard():
        index = cfg.dashboard_dir / "index.html"
        if not index.exists():
            return JSONResponse({"name": "OMNIBRIDGE AI", "message": "Dashboard not found",
                                 "expected": str(index), "api": "/api/health"}, status_code=200)
        return FileResponse(str(index))

    # ---- REST API ----
    @app.get("/api/health", tags=["system"])
    async def health():
        return await bridge.call_tool("system_health", {})

    @app.get("/api/tools", tags=["system"])
    async def tools(category: str | None = None):
        catalogue = bridge.tool_catalogue()
        if category:
            catalogue = [t for t in catalogue if t["category"] == category]
        return {"count": len(catalogue), "categories": bridge.registry.categories(), "tools": catalogue}

    @app.post("/api/tools/call", tags=["tools"])
    async def call(req: CallRequest):
        try:
            result = await bridge.call_tool(req.name, req.args, confirmed=req.confirm)
            return {"ok": True, "tool": req.name, "result": result}
        except Exception as e:  # noqa: BLE001
            raise _error(e) from e

    @app.post("/api/diagnostics", tags=["system"])
    async def diagnostics():
        return await bridge.call_tool("system_diagnostics", {})

    @app.get("/api/audit", tags=["system"])
    async def audit(limit: int = 50):
        return {"entries": bridge.db.audit_recent(max(1, min(limit, 500)))}

    @app.get("/api/tasks", tags=["agent"])
    async def tasks(limit: int = 50):
        return {"tasks": bridge.executor.list_tasks(limit)}

    @app.get("/api/tasks/{task_id}", tags=["agent"])
    async def task(task_id: str):
        try:
            return await bridge.call_tool("agent_get_task_status", {"taskId": task_id})
        except Exception as e:  # noqa: BLE001
            raise _error(e) from e

    @app.post("/api/tasks/{task_id}/cancel", tags=["agent"])
    async def cancel_task(task_id: str):
        return {"ok": bridge.executor.cancel(task_id), "taskId": task_id}

    @app.get("/api/knowledge/stats", tags=["knowledge"])
    async def knowledge_stats():
        return bridge.knowledge.stats()

    @app.post("/api/knowledge/retrieve", tags=["knowledge"])
    async def knowledge_retrieve(body: dict = Body(...)):
        query = str(body.get("query", ""))
        if not query:
            raise HTTPException(400, "query is required")
        hits = bridge.knowledge.retrieve(query, int(body.get("limit", 8)))
        return {"query": query, "hits": [h.to_dict() for h in hits]}

    @app.post("/api/knowledge/index", tags=["knowledge"])
    async def knowledge_index(req: IndexRequest):
        return bridge.knowledge.index_document(req.source, req.title, req.text, req.version, req.reliability)

    @app.get("/api/roblox", tags=["roblox"])
    async def roblox():
        return await bridge.roblox.info()

    @app.get("/demarrer", include_in_schema=False)
    async def demarrer(request: Request):
        """Guided setup page (French) for the in-page panel: no command line needed."""
        info: dict[str, Any] = {}
        try:
            info = await asyncio.wait_for(bridge.roblox.info(), timeout=10)
        except Exception as exc:  # noqa: BLE001 - a slow Studio must not break the page
            info = {"available": False, "error": f"{type(exc).__name__}: {exc}", "tools": []}
        available = bool(info.get("available"))
        error = str(info.get("error") or "")
        if available:
            studio_state = "ready"
        elif "not found" in error.lower() or "not_configured" in error.lower():
            studio_state = "studio_closed"
        else:
            studio_state = "mcp_unreachable"
        page = build_setup_page(
            server_url=f"http://{request.url.hostname}:{request.url.port or 80}",
            token=cfg.token if should_reveal_token(
                request.headers.get("origin"),
                request.headers.get("sec-fetch-mode"),
                request.headers.get("sec-fetch-site"),
            ) else None,
            studio_state=studio_state,
            studio_detail=error,
            tool_count=len(info.get("tools") or []),
            reveal=should_reveal_token(
                request.headers.get("origin"),
                request.headers.get("sec-fetch-mode"),
                request.headers.get("sec-fetch-site"),
            ),
            page_url=str(request.url).split("?")[0],
        )
        return HTMLResponse(page, headers={
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "Referrer-Policy": "no-referrer",
            "Content-Security-Policy": (
                "default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; "
                "img-src data:; connect-src 'self'; base-uri 'none'; form-action 'none'"),
        })

    @app.get("/api/browser/status", tags=["browser"])
    async def browser_status():
        return bridge.browser.status()

    # ---- OpenAPI actions: ChatGPT Custom GPT Actions, Copilot Studio, any OpenAPI agent ----
    @app.get("/openapi/actions.json", include_in_schema=False)
    async def actions_openapi(request: Request):
        base = cfg.public_url or str(request.base_url).rstrip("/")
        return build_actions_openapi(bridge, base)

    @app.post("/api/actions/{tool_name}", tags=["actions"])
    async def run_action(tool_name: str, body: dict[str, Any] = Body(default_factory=dict)):
        tool = bridge.registry.get(tool_name)
        if tool is None:
            raise HTTPException(404, detail={"error": "unknown_tool", "message":
                                f"Unknown tool '{tool_name}'. GET /api/tools for the catalogue."})
        try:
            confirm = bool(body.pop("confirm", False))
            result = await bridge.call_tool(tool_name, body, confirmed=confirm)
            return {"ok": True, "tool": tool_name, "result": result}
        except Exception as e:  # noqa: BLE001
            raise _error(e) from e

    @app.get("/api/webai/prompt", tags=["webai"])
    async def webai_prompt(budgetChars: int = 7000, categories: str = ""):
        cats = [c.strip() for c in categories.split(",") if c.strip()] or None
        return build_prompt(bridge, max(1500, min(budgetChars, 40000)), cats)

    @app.post("/api/webai/run", tags=["webai"])
    async def webai_run(body: dict = Body(...)):
        reply = str(body.get("reply", ""))
        if not reply.strip():
            raise HTTPException(400, "reply is required")
        return await run_calls(bridge, reply, confirm=bool(body.get("confirm", False)))

    @app.get("/api/tools/openai", tags=["webai"])
    async def tools_openai():
        tools = openai_tools(bridge)
        return {"count": len(tools), "format": "openai-chat-completions", "tools": tools}

    @app.get("/api/webai/providers", tags=["webai"])
    async def webai_providers():
        from .openai_agent import PROVIDERS

        return {"providers": [{"name": k, "baseUrl": v[0], "apiKeyEnv": v[1],
                               "defaultModel": v[2], "needsKey": bool(v[1])}
                              for k, v in PROVIDERS.items()]}

    @app.post("/api/webai/check", tags=["webai"])
    async def webai_check(body: dict = Body(...)):
        url = str(body.get("url", "")).strip()
        if not url:
            raise HTTPException(400, "url is required")
        return await check_remote_mcp(url, str(body.get("token", "")))

    @app.get("/api/agents/roles", tags=["agent"])
    async def roles():
        return await bridge.call_tool("agent_list_roles", {})

    @app.get("/api/info", tags=["system"])
    async def info():
        return {"name": "OMNIBRIDGE AI", "version": "1.0.0", "python": True,
                "toolCount": bridge.registry.size, "categories": bridge.registry.categories(),
                "permissionLevel": cfg.permission_level, "workspace": str(cfg.workspace_root),
                "transports": {"stdio": "python -m omnibridge --stdio",
                               "http": f"http://{cfg.http_host}:{cfg.http_port}",
                               "mcp": f"http://{cfg.http_host}:{cfg.http_port}/mcp"}}

    # ---- browser extension bridge ----
    @app.post("/bridge/register", tags=["bridge"])
    async def bridge_register(req: BridgeRegister):
        bridge.browser.register(req.clientId, req.info)
        return {"ok": True, "clients": len(bridge.browser.status()["clients"])}

    @app.post("/bridge/poll", tags=["bridge"])
    async def bridge_poll(req: BridgePoll):
        if req.clientId not in bridge.browser.status()["clients"]:
            bridge.browser.register(req.clientId, {"via": "poll"})
        cmd = await bridge.browser.poll(req.clientId, req.timeoutMs / 1000.0)
        return {"command": cmd}

    @app.post("/bridge/result", tags=["bridge"])
    async def bridge_result(req: BridgeResult):
        ok = bridge.browser.submit_result(req.requestId, req.ok, req.data)
        if not ok:
            return JSONResponse({"ok": False, "message": "Unknown or expired requestId"}, status_code=404)
        return {"ok": True}

    @app.get("/bridge/status", tags=["bridge"])
    async def bridge_status():
        return bridge.browser.status()

    return app


__all__ = ["create_http_app", "CallRequest", "AuthMiddleware", "json"]
