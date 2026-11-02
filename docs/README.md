# BONDI JSON-Storm

The core implementation is being built incrementally. The first component parses
batched LLM responses into native BONDI find or aggregation queries without I/O.

- [Batch parsing contract and examples](parsing.md)
- [Parser API reference](api.md)

## Development checks

```sh
uv run --locked pytest
uv run --locked ruff check src/json_storm/parsing.py tests/test_parsing.py
uv run --locked ruff format --check src/json_storm/parsing.py tests/test_parsing.py
uvx --from 'mkdocs==1.6.1' mkdocs build --strict --site-dir /tmp/bondi-json-storm-docs
```

MkDocs is only a documentation build tool; no runtime dependency is added.
