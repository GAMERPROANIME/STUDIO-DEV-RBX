"""Browser extension bridge (asyncio).

The MV3 extension long-polls /bridge/poll for commands queued by browser_*
tools and posts results to /bridge/result. If no extension is connected,
tools fail honestly — they never fabricate page content.
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from typing import Any

from ..core.logger import log


class BrowserBridge:
    def __init__(self) -> None:
        self._clients: dict[str, dict[str, Any]] = {}
        self._queue: asyncio.Queue = asyncio.Queue()
        self._pending: dict[str, asyncio.Future] = {}

    def register(self, client_id: str, info: dict[str, Any]) -> None:
        self._clients[client_id] = {"info": info, "connectedAt": datetime.now(timezone.utc).isoformat()}
        log.info("browser extension connected", extra={"clientId": client_id})

    def status(self) -> dict[str, Any]:
        return {"connected": len(self._clients) > 0,
                "clients": [{"clientId": k, **v} for k, v in self._clients.items()]}

    async def poll(self, client_id: str, timeout_s: float = 25.0) -> dict[str, Any] | None:
        try:
            return await asyncio.wait_for(self._queue.get(), timeout=timeout_s)
        except asyncio.TimeoutError:
            return None

    def submit_result(self, request_id: str, ok: bool, data: Any) -> bool:
        fut = self._pending.pop(request_id, None)
        if fut is None or fut.done():
            return False
        if ok:
            fut.set_result(data)
        else:
            fut.set_exception(RuntimeError(str(data)))
        return True

    async def command(self, cmd_type: str, args: dict[str, Any], timeout_s: float = 15.0) -> Any:
        if not self._clients:
            raise RuntimeError(
                "Browser extension not connected. Load the extension from the extension/ folder "
                "(chrome://extensions → Developer mode → Load unpacked) and open a page. "
                "See docs/EXTENSION.md."
            )
        request_id = str(uuid.uuid4())
        fut: asyncio.Future = asyncio.get_running_loop().create_future()
        self._pending[request_id] = fut
        await self._queue.put({"requestId": request_id, "type": cmd_type, "args": args})
        try:
            return await asyncio.wait_for(fut, timeout=timeout_s)
        except asyncio.TimeoutError:
            self._pending.pop(request_id, None)
            raise RuntimeError(f"Browser command '{cmd_type}' timed out after {timeout_s}s") from None
