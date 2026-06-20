import os
import unittest
from unittest.mock import patch

from runtime.node.mcp_stdio import LOCAL_SESSION_ID, resolve_mcp_actor_context


class McpActorContextTest(unittest.TestCase):
    def test_session_override_from_environment(self) -> None:
        with patch.dict(os.environ, {"CAPIFORGE_SESSION_ID": "sess-test-override"}, clear=False):
            context = resolve_mcp_actor_context(client_info={"name": "cursor", "version": "1.0"})
        self.assertEqual(context.session_id, "sess-test-override")

    def test_session_derived_from_client_info(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("CAPIFORGE_SESSION_ID", None)
            first = resolve_mcp_actor_context(client_info={"name": "cursor", "version": "1.0"})
            second = resolve_mcp_actor_context(client_info={"name": "opencode", "version": "2.0"})
            fallback = resolve_mcp_actor_context(client_info=None)
        self.assertTrue(first.session_id.startswith("mcp-cursor-"))
        self.assertTrue(second.session_id.startswith("mcp-opencode-"))
        self.assertNotEqual(first.session_id, second.session_id)
        self.assertEqual(fallback.session_id, LOCAL_SESSION_ID)

    def test_agent_id_defaults_and_override(self) -> None:
        default = resolve_mcp_actor_context()
        with patch.dict(os.environ, {"CAPIFORGE_AGENT_ID": "agent-custom"}, clear=False):
            overridden = resolve_mcp_actor_context()
        self.assertNotEqual(default.agent_id, "")
        self.assertEqual(overridden.agent_id, "agent-custom")


if __name__ == "__main__":
    unittest.main()
