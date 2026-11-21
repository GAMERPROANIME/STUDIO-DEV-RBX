"""Local WebSocket server (127.0.0.1 only) speaking the bridge protocol.

Security layers, in order:
  1. bind 127.0.0.1 (never 0.0.0.0) — unreachable from the network;
  2. HTTP upgrade filter: a browser page Origin is refused, only extension origins pass;
  3. mandatory `hello` frame with the pairing token (constant-time compare, 5 s timeout);
  4. strict JSON objects, byte-size cap, action allow-list;
  5. tool validation/permissions/rate limits delegated to ConnectionManager.
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from http import HTTPStatus
from typing import Any
from urllib.parse import parse_qs

from websockets.asyncio.server import ServerConnection, serve
from websockets.datastructures import Headers
from websockets.exceptions import ConnectionClosed
from websockets.http11 import Response

from .config import BridgeConfig
from .connection_manager import BridgeError, ConnectionManager
from .protocol import (ACTIONS, CLOSE_BAD_PROTOCOL, CLOSE_TOO_SLOW, CLOSE_UNAUTHORIZED,
                       PROTOCOL_VERSION)
from .security import AuditLog, check_token, origin_allowed
from .status_page import build_page, should_reveal_token, status_payload

log = logging.getLogger("omnibridge.studio_bridge")

ACCEPTED_PATHS = ("/", "/studio-bridge", "/omnibridge")


class BridgeServer:
    def __init__(self, cfg: BridgeConfig, manager: ConnectionManager, audit: AuditLog):
        self.cfg = cfg
        self.manager = manager
        self.audit = audit
        self.clients: set[ServerConnection] = set()
        self._tasks: dict[str, asyncio.Task] = {}
        self._server = None

    # ------------------------------------------------------------ handshake filters
    async def _process_request(self, connection: ServerConnection, request):
        path, _, query = request.path.partition("?")
        if (request.headers.get("Upgrade") or "").lower() != "websocket":
            return await self._http(request, path, parse_qs(query))
        if path not in ACCEPTED_PATHS:
            return connection.respond(HTTPStatus.NOT_FOUND, "unknown path\n")
        ok, reason = origin_allowed(request.headers.get("Origin"), self.cfg.allowed_origin_prefixes)
        if not ok:
            self.audit.write("origin_rejected", origin=request.headers.get("Origin"), reason=reason)
            return connection.respond(HTTPStatus.FORBIDDEN, reason + "\n")
        return None

    # ------------------------------------------------------------ human-facing HTTP
    async def _http(self, request, path: str, query: dict[str, list[str]]):
        """Setup page + JSON status. No token is ever handed to another origin."""
        allowed_paths = ("/", "/index.html", "/setup", "/status.json", "/health")
        if path not in allowed_paths:
            return _response(HTTPStatus.NOT_FOUND, b"unknown path\n", "text/plain; charset=utf-8")
        if path == "/health":
            body = json.dumps({"ok": True, "bridge": "studio_bridge", "protocol": PROTOCOL_VERSION})
            return _response(HTTPStatus.OK, body.encode(), "application/json",
                             extra={"Access-Control-Allow-Origin": "*"})
        if query.get("refresh"):
            try:
                await self.manager.connector.connect(force=True)
                await self.manager.list_tools(refresh=True)
            except Exception:  # noqa: BLE001 - the page must still render
                pass
            self.broadcast_state()
        if path == "/status.json":
            payload = status_payload({**self.manager.status(),
                                      "studio": self.manager.connector.status()},
                                     self.manager.registry.manifest())
            return _response(HTTPStatus.OK, json.dumps(payload, default=str).encode(),
                             "application/json")
        origin = request.headers.get("Origin")
        reveal = should_reveal_token(
            origin,
            request.headers.get("Sec-Fetch-Mode"),
            request.headers.get("Sec-Fetch-Site"),
            request.headers.get("User-Agent") or "",
        )
        body = build_page({**self.manager.status(), "studio": self.manager.connector.status()},
                          self.manager.registry.manifest(),
                          self.cfg.token if reveal else None, self.cfg.uri)
        return _response(HTTPStatus.OK, body, "text/html; charset=utf-8")

    async def _handshake(self, ws: ServerConnection) -> bool:
        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=self.cfg.auth_timeout_s)
        except (asyncio.TimeoutError, TimeoutError):
            await self._reject(ws, CLOSE_TOO_SLOW, "no hello frame within "
                               f"{self.cfg.auth_timeout_s:.0f}s")
            return False
        except ConnectionClosed:
            return False
        message = _parse_message(raw, self.cfg.max_message_bytes)
        request_id = str(message.get("id") or "") if isinstance(message, dict) else ""
        if not isinstance(message, dict) or message.get("type") != "hello":
            await self._reject(ws, CLOSE_BAD_PROTOCOL, "first frame must be a hello", request_id)
            return False
        if not check_token(str(message.get("token") or ""), self.cfg.token):
            self.audit.write("auth_failed", origin=_origin(ws))
            await self._reject(ws, CLOSE_UNAUTHORIZED, "invalid pairing token", request_id)
            return False
        await ws.send(json.dumps({
            "id": message.get("id"),
            "type": "hello_ok",
            "protocol": PROTOCOL_VERSION,
            "bridge": self.manager.status(),
            "tools": self.manager.registry.manifest(),
            "permissionLevel": self.cfg.permission_level,
        }))
        self.audit.write("client_connected", origin=_origin(ws), client=str(message.get("client") or ""))
        return True

    async def _reject(self, ws: ServerConnection, code: int, reason: str,
                      request_id: str = "") -> None:
        with contextlib.suppress(Exception):
            await ws.send(json.dumps({"id": request_id, "type": "error", "ok": False,
                                      "action": "hello",
                                      "error": {"code": "unauthorized" if code == CLOSE_UNAUTHORIZED
                                                else "bad_request", "message": reason}}))
            await ws.close(code=code, reason=reason[:120])

    # ------------------------------------------------------------ per client
    async def _handler(self, ws: ServerConnection) -> None:
        if not await self._handshake(ws):
            return
        self.clients.add(ws)
        self.broadcast_state()
        try:
            async for raw in ws:
                message = _parse_message(raw, self.cfg.max_message_bytes)
                if message is None:
                    await ws.send(json.dumps({"ok": False, "action": "unknown", "error": {
                        "code": "bad_request", "message": "frame must be a JSON object"}}))
                    continue
                await self._dispatch(ws, message)
        except ConnectionClosed:
            pass
        finally:
            self.clients.discard(ws)
            self.audit.write("client_disconnected", origin=_origin(ws))

    async def _dispatch(self, ws: ServerConnection, message: dict[str, Any]) -> None:
        request_id = str(message.get("id") or "")
        action = str(message.get("action") or "")
        if action not in ACTIONS:
            await _reply(ws, request_id, action, ok=False, error={
                "code": "unknown_action", "message": f"unsupported action '{action}'",
                "detail": f"allowed: {', '.join(ACTIONS)}"})
            return
        if message.get("type") == "hello":
            await _reply(ws, request_id, "hello", ok=True, result={"type": "hello_ok",
                                                                  "protocol": PROTOCOL_VERSION})
            return
        task = asyncio.create_task(self._run_action(ws, request_id, action, message),
                                   name=f"bridge-action-{action}-{request_id}")
        if request_id:
            self._tasks[request_id] = task
            task.add_done_callback(lambda _t, rid=request_id: self._tasks.pop(rid, None))

    async def _run_action(self, ws: ServerConnection, request_id: str, action: str,
                          message: dict[str, Any]) -> None:
        manager = self.manager
        try:
            if action == "ping":
                result: Any = {"pong": True, "ts": _now(), "protocol": PROTOCOL_VERSION}
            elif action == "status":
                result = {**manager.status(), "studio": manager.connector.status()}
            elif action == "list_tools":
                result = {"tools": await manager.list_tools(refresh=bool(message.get("refresh")))}
            elif action == "tools_prompt":
                if message.get("refresh"):
                    await manager.list_tools(refresh=True)
                result = {"prompt": manager.registry.prompt_block(), "count": len(manager.registry)}
            elif action == "call_tool":
                tool = str(message.get("tool") or "")
                arguments = message.get("arguments") or {}
                if not isinstance(arguments, dict):
                    raise BridgeError("invalid_arguments", "arguments must be a JSON object")
                timeout = message.get("timeout")
                result = await manager.call_tool(
                    tool, arguments,
                    timeout=float(timeout) if isinstance(timeout, (int, float)) else None,
                    source=str(message.get("source") or "extension"))
                self.broadcast_state()
            elif action == "studio_status":
                result = manager.connector.status()
                if message.get("refresh") or result.get("state") in ("studio_closed", "mcp_unreachable"):
                    await manager.connector.connect()
                    await manager.list_tools(refresh=True)
                    result = manager.connector.status()
            elif action == "restart_mcp":
                state = await manager.connector.restart()
                tools = await manager.list_tools(refresh=True) if state == "ready" else []
                result = {"state": state, "status": manager.connector.status(),
                          "toolCount": len(tools)}
                self.broadcast_state()
            elif action == "stop_task":
                target = str(message.get("task") or "")
                pending = self._tasks.get(target)
                if pending and not pending.done():
                    pending.cancel()
                    result = {"cancelled": True, "task": target}
                else:
                    result = {"cancelled": False, "task": target,
                              "note": "no in-flight task with this id"}
            elif action == "audit_tail":
                limit = message.get("limit")
                result = {"entries": self.audit.tail(int(limit) if isinstance(limit, int) else 20)}
            else:  # pragma: no cover - guarded by ACTIONS
                raise BridgeError("unknown_action", action)
        except BridgeError as exc:
            await _reply(ws, request_id, action, ok=False, error=exc.to_dict())
        except asyncio.CancelledError:
            await _reply(ws, request_id, action, ok=False,
                         error={"code": "cancelled", "message": "task cancelled by client "})
            raise
        except Exception as exc:  # noqa: BLE001 - never leak a traceback to the AI
            log.exception("bridge action failed")
            await _reply(ws, request_id, action, ok=False,
                         error={"code": "internal_error",
                                "message": f"{type(exc).__name__}: {exc}"})
        else:
            await _reply(ws, request_id, action, ok=True, result=result)

    # ------------------------------------------------------------ push events
    def broadcast_state(self) -> None:
        self.broadcast({"type": "event", "event": "mcp_state",
                        "data": {**self.manager.status(), "studio": self.manager.connector.status()}})

    def broadcast(self, payload: dict[str, Any]) -> None:
        if not self.clients:
            return
        data = json.dumps(payload)
        for client in list(self.clients):
            asyncio.create_task(_safe_send(client, data))

    # ------------------------------------------------------------ lifecycle
    async def start(self) -> None:
        self._server = await serve(
            self._handler,
            self.cfg.host,
            self.cfg.port,
            process_request=self._process_request,
            max_size=self.cfg.max_message_bytes,
            ping_interval=self.cfg.heartbeat_s,
            ping_timeout=self.cfg.heartbeat_s,
            close_timeout=5,
        )
        # Defensive: confirm the real bound address is loopback, not merely requested to be.
        sockets = getattr(self._server, "sockets", None) or []
        if sockets:
            bound = sockets[0].getsockname()[0]
            if bound not in ("127.0.0.1", "::1"):
                self._server.close()
                await self._server.wait_closed()
                self._server = None
                raise RuntimeError(f"refusing to serve on non-loopback address {bound}")
        self.audit.write("server_started", host=self.cfg.host, port=self.cfg.port,
                         protocol=PROTOCOL_VERSION)

    async def stop(self) -> None:
        for task in list(self._tasks.values()):
            task.cancel()
        for client in list(self.clients):
            with contextlib.suppress(Exception):
                await client.close(code=1001, reason="bridge shutting down")
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None
        self.audit.write("server_stopped")

    async def serve_forever(self) -> None:
        await self.start()
        await self._stop_event.wait()

    @property
    def _stop_event(self) -> asyncio.Event:
        if not hasattr(self, "_stop_evt"):
            self._stop_evt = asyncio.Event()
        return self._stop_evt


def _response(status: HTTPStatus, body: bytes, content_type: str,
              extra: dict[str, str] | None = None) -> Response:
    headers = Headers()
    headers["Content-Type"] = content_type
    headers["Content-Length"] = str(len(body))
    headers["Cache-Control"] = "no-store"
    headers["X-Content-Type-Options"] = "nosniff"
    headers["X-Frame-Options"] = "DENY"
    headers["Referrer-Policy"] = "no-referrer"
    headers["Content-Security-Policy"] = (
        "default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; "
        "img-src data:; connect-src 'self'; base-uri 'none'; form-action 'none'")
    for key, value in (extra or {}).items():
        headers[key] = value
    return Response(status.value, status.phrase, headers, body)


async def _reply(ws: ServerConnection, request_id: str, action: str, ok: bool,
                 result: Any = None, error: dict[str, Any] | None = None) -> None:
    payload: dict[str, Any] = {"id": request_id, "ok": ok, "action": action}
    if ok:
        payload["result"] = result
    else:
        payload["error"] = error or {"code": "internal_error", "message": "unknown error"}
    with contextlib.suppress(ConnectionClosed):
        await ws.send(json.dumps(payload, default=str))


async def _safe_send(ws: ServerConnection, data: str) -> None:
    with contextlib.suppress(Exception):
        await ws.send(data)


def _parse_message(raw: Any, max_bytes: int) -> dict[str, Any] | None:
    if isinstance(raw, (bytes, bytearray)):
        if len(raw) > max_bytes:
            return None
        try:
            raw = raw.decode("utf-8")
        except UnicodeDecodeError:
            return None
    if not isinstance(raw, str) or len(raw.encode("utf-8", "ignore")) > max_bytes:
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _origin(ws: ServerConnection) -> str:
    try:
        return ws.request.headers.get("Origin") or ""
    except Exception:  # noqa: BLE001
        return ""


def _now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()
