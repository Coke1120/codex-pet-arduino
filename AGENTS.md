<!-- codebase-memory-mcp:start -->

## Codebase Knowledge Graph

Prefer `codebase-memory-mcp` for structural code discovery when available. It is a helper, not a blocking gate.

Before structural discovery, check graph availability and freshness with `list_projects` and `index_status`. Run `index_repository` only when the project is missing, stale, or recent file changes may affect the query.

Priority:

1. `list_projects` - confirm the project exists in the graph.
2. `index_status` - check whether the index is fresh enough for the task.
3. `index_repository` - refresh only when missing, stale, or materially affected by recent changes.
4. `get_graph_schema` - inspect available labels, edges, and properties when doing non-trivial graph work.
5. `search_graph` - find functions, classes, routes, variables, and qualified names.
6. `get_code_snippet` - read exact source after discovering a qualified name.
7. `get_architecture` - get a high-level project overview when needed.
8. `detect_changes` - check impact before commits or impact-sensitive edits when exposed and current.

Use `search_graph` filters, relationships, pagination, and schema-guided searches for caller/dependency exploration when dedicated trace/query tools are unavailable.

Fall back to `rg` and direct file reads for strings, config, docs, generated files, or when MCP tools are unavailable, incomplete, or stale.

<!-- codebase-memory-mcp:end -->
