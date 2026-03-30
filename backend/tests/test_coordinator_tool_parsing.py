import json
import unittest

from app.llm.coordinator_v2 import _parse_tool_result


class ParseToolResultTests(unittest.TestCase):
    def test_graph_query_tool_returns_actions_and_summary(self) -> None:
        output = json.dumps(
            {
                "cypher": "MATCH (w:Wafer) RETURN w LIMIT 5",
                "nodes": [{"id": "1", "labels": ["Wafer"], "properties": {"wafer_id": "W1"}}],
                "edges": [],
                "result": [{"w": {"wafer_id": "W1"}}],
                "row_count": 1,
                "execution_time_ms": 12.5,
            },
            ensure_ascii=False,
        )

        tool_result, actions, summary = _parse_tool_result("graph_query_tool", output)

        self.assertIsNotNone(tool_result)
        self.assertEqual(tool_result.cypher, "MATCH (w:Wafer) RETURN w LIMIT 5")
        self.assertEqual(len(actions), 2)
        self.assertEqual(actions[0].type, "apply_query")
        self.assertEqual(actions[1].type, "open_tab")
        self.assertIn("1건 반환", summary)
        self.assertIn("```cypher", summary)

    def test_graph_schema_tool_returns_summary(self) -> None:
        output = json.dumps(
            {
                "node_labels": ["Wafer", "Recipe"],
                "relationship_types": ["HAS_METROLOGY"],
                "properties": {"Wafer": ["wafer_id"]},
                "summary": "라벨 2개, 관계 1개 확인",
            },
            ensure_ascii=False,
        )

        tool_result, actions, summary = _parse_tool_result("graph_schema_tool", output)

        self.assertIsNotNone(tool_result)
        self.assertEqual(tool_result.summary, "라벨 2개, 관계 1개 확인")
        self.assertEqual(actions, [])
        self.assertEqual(summary, "라벨 2개, 관계 1개 확인")
