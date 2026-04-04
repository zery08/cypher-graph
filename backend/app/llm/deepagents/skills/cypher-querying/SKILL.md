---
name: cypher-querying
description: Write and execute read-only Neo4j Cypher for semiconductor graph analysis. Use when you need precise control over filters, relationships, aggregation, or when the high-level graph QA tool did not produce a satisfactory result.
---

# Cypher Querying Skill

## Workflow for simple questions

1. Identify the primary label and property filter.
2. Write a short read-only Cypher with `LIMIT`.
3. Execute it with `graph_query_tool`.
4. If the raw rows are dense, optionally call `table_summary_tool`.

## Workflow for complex questions

1. Make a short plan for the labels, relationships, and aggregations you need.
2. If the schema is not obvious, use `graph_schema_tool` first.
3. Write Cypher with explicit relationship paths and minimal selected fields.
4. Execute with `graph_query_tool`.
5. If the query succeeds but the answer still needs a concise narrative, synthesize from the returned rows and graph data.

## Quality rules

- Keep queries read-only.
- Always include `LIMIT`.
- Prefer returning node variables for graph exploration when the question is about relationships or connected entities.
- For aggregates, return only the identifier columns and aggregate outputs you need.
- Do not guess property names. Check the schema first if unsure.

## Recovery

- Zero rows: verify labels, properties, and exact-value filters.
- Too many rows: add a tighter filter or aggregate.
- Missing relationships in the graph view: return the relationship variable along with the nodes.
