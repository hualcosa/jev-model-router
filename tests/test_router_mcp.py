import io
import json
import unittest

from router_core.mcp import MCPServer, TOOL


class Service:
    def __init__(self):
        self.calls = []

    def prepare(self, **arguments):
        self.calls.append(arguments)
        return {"ok": True, "task_name": "router_" + "a"*48, "task_binding": "orchestrator_attested"}


class MCPTests(unittest.TestCase):
    def setUp(self):
        self.service = Service()
        self.server = MCPServer(self.service)

    def call(self, method, **params):
        return self.server.dispatch({"jsonrpc": "2.0", "id": 1, "method": method, "params": params})

    def test_initialize_before_tools_and_no_execute_tools_or_encrypted_task_schema(self):
        self.assertIn("error", self.call("tools/list"))
        init = self.call("initialize", protocolVersion="2025-11-25")
        self.assertEqual(init["result"]["protocolVersion"], "2025-11-25")
        tools = self.call("tools/list")["result"]["tools"]
        self.assertEqual([t["name"] for t in tools], ["prepare_task"])
        self.assertNotIn("encrypted", json.dumps(TOOL))
        self.assertFalse(TOOL["annotations"]["readOnlyHint"])
        self.assertTrue(TOOL["annotations"]["openWorldHint"])

    def test_task_id_is_explicit_stable_assignment_key_not_transport_id(self):
        self.call("initialize")
        reply = self.call("tools/call", name="prepare_task", arguments={"session_id": "s1", "task_id": "stable_assignment", "task_text": "synthetic text"})
        self.assertFalse(reply["result"]["isError"])
        self.assertEqual(self.service.calls, [{"session_id": "s1", "request_id": "stable_assignment", "task_text": "synthetic text"}])

    def test_override_or_extra_arguments_cannot_reach_service(self):
        self.call("initialize")
        for args in ({"task_text": "private"}, {"session_id": "s", "task_id": "t", "task_text": "x", "model": "override"},
                     {"session_id": "s", "task_id": "t", "task_text": 1}):
            self.assertIn("error", self.call("tools/call", name="prepare_task", arguments=args))
        self.assertEqual(self.service.calls, [])

    def test_notifications_and_unknown_methods(self):
        self.assertIsNone(self.server.dispatch({"jsonrpc": "2.0", "method": "notifications/initialized"}))
        self.call("initialize")
        self.assertEqual(self.call("run_command")["error"]["code"], -32601)

    def test_stdio_is_bounded_duplicate_keys_and_errors_do_not_echo_payload(self):
        output = io.StringIO()
        self.server.serve(io.BytesIO(b'{"private-secret":\n{"jsonrpc":"2.0","id":1,"id":2,"method":"initialize"}\n'), output)
        lines = [json.loads(line) for line in output.getvalue().splitlines()]
        self.assertEqual(len(lines), 2)
        self.assertTrue(all("error" in line for line in lines))
        self.assertNotIn("private-secret", output.getvalue())
        output = io.StringIO()
        self.server.serve(io.BytesIO(b"x"*262145), output)
        self.assertEqual(output.getvalue(), "")


if __name__ == "__main__":
    unittest.main()
