"""Wire protocol between the browser extension and the Python bridge (JSON text frames).

Client → bridge
    {"id":"1","type":"hello","token":"<pairing token>"}            (mandatory first frame)
    {"id":"2","action":"status"}
    {"id":"3","action":"ping"}
    {"id":"4","action":"list_tools","refresh":true}
    {"id":"5","action":"call_tool","tool":"<name>","arguments":{…},"timeout":90}
    {"id":"6","action":"studio_status"}
    {"id":"7","action":"restart_mcp"}
    {"id":"8","action":"stop_task","task":"<id of a call_tool>"}
    {"id":"9","action":"audit_tail","limit":20}

Bridge → client
    {"id":"1","type":"hello_ok","protocol":1,"bridge":{…},"tools":[…]}
    {"id":"5","ok":true,"action":"call_tool","result":{…}}
    {"id":"5","ok":false,"action":"call_tool","error":{"code":…,"message":…,"detail":…}}
    {"type":"event","event":"mcp_state","data":{…}}                 (server push)
    {"type":"event","event":"heartbeat","data":{"ts":…}}
"""
from __future__ import annotations

PROTOCOL_VERSION = 1

ACTIONS = ("status", "ping", "list_tools", "call_tool", "studio_status", "restart_mcp",
           "stop_task", "audit_tail", "tools_prompt")

CLOSE_UNAUTHORIZED = 4001
CLOSE_BAD_PROTOCOL = 4002
CLOSE_TOO_SLOW = 4003
