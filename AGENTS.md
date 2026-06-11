Before coding, identify the domain model, invariants, abstractions and design principles. Minimize special-case handling

When you need to find code in this repository:
1. Use the ast-index MCP tools BEFORE grep or bulk Read.
2. Before reading any file longer than 500 lines, call `outline` on it first,
   then Read only the line range you actually need.
3. For "who uses X" questions use `usages`; for "who calls X" use `callers`;
   for "what implements X" use `implementations`.
4. If ast-index returns empty, fall back to grep — don't bulk-read files.