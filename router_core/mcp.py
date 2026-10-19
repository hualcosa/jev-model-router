"""Small stdio MCP facade for local task preparation. No task execution tools."""
import json
import sys

PROTOCOLS = ("2024-11-05", "2025-03-26", "2025-06-18", "2025-11-25")
TOOL = {
    "name": "prepare_task",
    "description": "Prepare one generic Codex assignment using configured consent and policy. Reuse task_id on retry. Never select model/effort yourself. Not for explicit pins or custom agents.",
    "inputSchema": {"type": "object", "properties": {
        "session_id": {"type": "string", "minLength": 1, "maxLength": 256},
        "task_id": {"type": "string", "pattern": "^[A-Za-z0-9_-]{1,80}$"},
        "task_text": {"type": "string", "minLength": 1, "maxLength": 100000}},
        "required": ["session_id", "task_id", "task_text"], "additionalProperties": False},
    "annotations": {"readOnlyHint": False, "destructiveHint": False,
                    "idempotentHint": True, "openWorldHint": True},
}


class MCPServer:
    def __init__(self, service):
        self.service = service
        self.initialized = False

    def dispatch(self, request):
        raw_ident = request.get("id") if isinstance(request, dict) else None
        ident = raw_ident if type(raw_ident) in (int, str) else None
        def error(code, message):
            return {"jsonrpc": "2.0", "id": ident, "error": {"code": code, "message": message}}
        if not isinstance(request, dict) or request.get("jsonrpc") != "2.0" or not isinstance(request.get("method"), str):
            return error(-32600, "Invalid Request")
        method, params = request["method"], request.get("params", {})
        if "id" not in request:
            return None
        if not isinstance(params, dict) or ident is None:
            return error(-32602, "Invalid params")
        if method == "initialize":
            self.initialized = True
            version = params.get("protocolVersion")
            result = {"protocolVersion": version if version in PROTOCOLS else PROTOCOLS[-1],
                      "serverInfo": {"name": "intelligent_router", "version": "1.0.0"},
                      "capabilities": {"tools": {}}}
        elif not self.initialized:
            return error(-32002, "Server not initialized")
        elif method == "tools/list":
            result = {"tools": [TOOL]}
        elif method == "ping":
            result = {}
        elif method == "tools/call":
            args = params.get("arguments")
            if (params.get("name") != "prepare_task" or not isinstance(args, dict) or
                    set(args) != {"session_id", "task_id", "task_text"} or
                    any(not isinstance(v, str) for v in args.values())):
                return error(-32602, "Invalid params")
            answer = self.service.prepare(session_id=args["session_id"], task_text=args["task_text"], request_id=args["task_id"])
            result = {"content": [{"type": "text", "text": json.dumps(answer, separators=(",", ":"))}],
                      "isError": not answer["ok"]}
        else:
            return error(-32601, "Method not found")
        return {"jsonrpc": "2.0", "id": ident, "result": result}

    def serve(self, source=None, destination=None):
        source = source or sys.stdin.buffer
        destination = destination or sys.stdout
        while True:
            line = source.readline(262145)
            if not line:
                return
            if len(line) > 262144:
                return
            try:
                from .classifier import _unique
                request = json.loads(line, object_pairs_hook=_unique)
                response = self.dispatch(request)
            except Exception:
                response = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Invalid request"}}
            if response is not None:
                destination.write(json.dumps(response, allow_nan=False, separators=(",", ":")) + "\n")
                destination.flush()
