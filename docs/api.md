# Parser API reference

Import these names from `json_storm.parsing`.

## parse_batch

```python
parse_batch(
    response: str,
    *,
    batch_index: int,
    query_kind: Literal["find", "aggregate"],
    database: str,
    collections: Collection[str],
    expected_count: int,
) -> ParsedBatch
```

Parses one response using the [batch contract](parsing.md). `batch_index` must be a
nonnegative integer (not a boolean), `collections` a nonempty collection of valid collection names,
and `expected_count` a positive integer (not a boolean). BONDI validates database
and collection names. Configuration errors raise `TypeError` or `ValueError`.
Model output errors are returned as records.

Find entries accept optional `projection`, `sort`, `skip`, and `limit`.
`sort` is a JSON array of `[field, direction]` pairs, converted to an ordered tuple
of tuples for BONDI. Defaults are `projection=None`, `sort=()`, `skip=0`, and
`limit=None`. BONDI validates field names, integer directions (`1`/`-1`),
nonnegative skip, and positive-or-null limit. Invalid options produce a
candidate-level `invalid_query_shape` error. See the batch contract for examples.

## ParsedBatch

A frozen dataclass with fields:

| Field | Type | Meaning |
| --- | --- | --- |
| `batch_index` | `int` | Caller-supplied zero-based batch index |
| `raw_response` | `str` | Original response, unchanged |
| `expected_count` | `int` | Queries requested in this call |
| `candidates` | `tuple[ParsedCandidate, ...]` | All entries in response order; defaults to empty |
| `error` | `ParseError \| None` | Whole-response failure; defaults to `None` |

Properties: `actual_count: int | None` and `count_matches: bool | None`.
A candidate-level failure does not populate the batch's `error`.

## ParsedCandidate

A frozen dataclass with fields:

| Field | Type | Meaning |
| --- | --- | --- |
| `batch_index` | `int` | Parent batch index |
| `position` | `int` | Zero-based position in the response array |
| `raw` | `Any` | Original decoded entry, including invalid entries |
| `query` | `MongoFindQuery \| MongoAggregateQuery \| None` | Constructed query; defaults to `None` |
| `error` | `ParseError \| None` | Entry failure; defaults to `None` |

The parser populates exactly one of `query` and `error`. Frozen records prevent
field reassignment, but nested raw values and BONDI queries remain mutable.
BONDI copies query payloads, so edits to `raw` do not modify the query.

## ParseError

A frozen dataclass with `status: Literal["invalid_json", "invalid_query_shape"]`
and `message: str`. Location is determined by the containing batch or candidate.
Messages are explanatory diagnostics, not stable machine-readable error codes.

## Type aliases

- `QueryKind = Literal["find", "aggregate"]`
- `MongoQuery = MongoFindQuery | MongoAggregateQuery`

# Schema rendering API

Import `render_schema_catalog` from `json_storm.schema`.

```python
render_schema_catalog(
    schemas: Mapping[str, Schema],
    *,
    examples_per_type: int = 0,
) -> str
```

Returns a deterministic text catalogue with explicit paths, observed types,
missing-field counts, and optional examples. The result ends with a newline.
An empty mapping is supported. Collection names must be nonempty strings without
null characters; values must be BONDI `Schema` instances. `examples_per_type`
must be a nonnegative integer, excluding booleans. Positive values require value
retention on every schema, including empty schemas.

Invalid argument types raise `TypeError`; invalid names, example counts, or
missing value retention raise `ValueError`. See the
[schema rendering guide](schema.md) for notation and example-selection rules.

# Prompt rendering API

Import `PromptTemplate` and `PROMPTS` from `json_storm.prompts`.

`PromptTemplate` is a frozen dataclass with `instructions: str` and
`query_kind: Literal["find", "aggregate"]`. Empty/whitespace instructions and
unsupported kinds raise `ValueError` at construction.

```python
PromptTemplate.render(
    schema_text: str,
    *,
    num_queries: int,
    relationship_hints: str | None = None,
    target_collection: str | None = None,
) -> str
```

Returns a deterministic prompt ending with a newline. `schema_text` must be a
nonblank string; `num_queries` a positive integer excluding booleans. Relationship
hints must be `None` or a nonblank string. The optional target must be a nonempty
string without null characters. Invalid arguments raise `ValueError`.
Target membership in the supplied schema text is the caller's responsibility.

`PROMPTS: dict[str, PromptTemplate]` holds `p1`–`p7`. See the
[prompt guide](prompts.md) for query kinds, adaptation details, and usage.

# Model API

Import from `json_storm.models`:

- `load_credentials(path: str | Path) -> bool`: explicitly load dotenv without
  overwriting environment variables; missing paths raise `FileNotFoundError`.
- `Model`: structural protocol with `generate(prompt: str) -> ModelResponse`.
- `LiteLLMModel(model, *, timeout_seconds=120, api_base=None, parameters=None, system_instructions=DEFAULT_SYSTEM_INSTRUCTIONS)`:
  synchronous adapter; `generate` accepts a nonblank string and propagates provider
  exceptions. Invalid configuration raises `TypeError` or `ValueError`.
- `ModelResponse`: frozen observation record. Fields are `text`, `requested_model`,
  `returned_model`, `response_id`, `finish_reason`, `elapsed_ms`, `parameters`,
  `usage`, `input_tokens`, `output_tokens`, `total_tokens`, `reasoning_tokens`,
  `cached_input_tokens`, `estimated_cost_usd`, `cost_status`, `billing_mode`, `system_instructions`, and `reasoning_content`.

See the [model guide](models.md) for metadata meanings, missing-value handling,
reasoning settings, reserved parameters, and credential loading.
