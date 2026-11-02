# BONDI JSON-Storm

The core implementation is being built incrementally. The first component parses
batched LLM responses into native BONDI find or aggregation queries without I/O.

- [Batch parsing contract and examples](parsing.md)
- [Schema catalogue rendering](schema.md)
- [Prompt rendering](prompts.md)
- [Model access](models.md)
- [API reference](api.md)

## Development checks

```sh
uv run --locked pytest
uv run --locked ruff check src/json_storm/parsing.py src/json_storm/schema.py src/json_storm/prompts.py tests
uv run --locked ruff format --check src/json_storm/parsing.py src/json_storm/schema.py src/json_storm/prompts.py tests
uvx --from 'mkdocs==1.6.1' mkdocs build --strict --site-dir /tmp/bondi-json-storm-docs
```

MkDocs is only a documentation build tool; no runtime dependency is added.
