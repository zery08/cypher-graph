---
name: schema-exploration
description: Inspect Neo4j labels, relationship types, and properties before writing Cypher. Use when the question is ambiguous, the first query failed, the schema is unclear, or the user asks how entities are related.
---

# Schema Exploration Skill

## Workflow

1. Use `graph_schema_tool` to inspect available node labels, relationship types, and properties.
2. Identify the most likely path for the user's question.
3. Only after the path is clear, write a focused read-only Cypher for `graph_query_tool` or fall back to `graph_cypher_qa_tool` for a simpler end-to-end run.

## What to look for

- Which label contains the entity the user named
- Which property can filter that entity
- Which relationship type connects the relevant labels
- Whether the result needs raw rows, graph structure, or both

## Recovery

- If a previous query returned zero rows, verify that the property names and labels actually exist.
- If the previous query was too narrow, broaden the filter after checking the schema.
- If multiple labels look similar, prefer the one whose properties best match the user's wording.
