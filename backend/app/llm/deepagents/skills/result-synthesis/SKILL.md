---
name: result-synthesis
description: Summarize retrieved graph or table results into a clear Korean answer, and decide when table summary or chart recommendation tools add value.
---

# Result Synthesis Skill

## Workflow

1. Check whether the retrieved data directly answers the question.
2. If rows are complex, use `table_summary_tool` to compress them.
3. If the user is asking for visualization or trend comparison, use `chart_recommendation_tool`.
4. Answer in Korean with confirmed findings first.

## Rules

- Do not claim patterns that are not visible in the data.
- If the result is empty, say that no rows were returned.
- If the answer comes from aggregated rows, mention the aggregation scope.
- Prefer short, concrete summaries over long speculative explanations.
