import unittest

from app.llm.tools.graph_cypher_tool import _followup_hint


class GraphCypherToolHelperTests(unittest.TestCase):
    def test_followup_hint_prefers_chain_error(self) -> None:
        hint = _followup_hint(
            chain_error="boom",
            query_guard_error=None,
            execution_error=None,
            cypher="",
        )

        self.assertIsNotNone(hint)
        self.assertIn("graph_schema_tool", hint)
        self.assertIn("graph_query_tool", hint)

    def test_followup_hint_absent_for_successful_query(self) -> None:
        hint = _followup_hint(
            chain_error=None,
            query_guard_error=None,
            execution_error=None,
            cypher="MATCH (w) RETURN w LIMIT 5",
        )

        self.assertIsNone(hint)
