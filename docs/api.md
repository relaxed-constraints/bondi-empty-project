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
