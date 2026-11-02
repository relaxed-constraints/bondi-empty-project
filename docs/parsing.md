# Parsing generated query batches

A model call requests `batch_size` queries. The parser's `expected_count` is the
number requested for that particular call: for 100 queries at batch size 8, it is
8 for the first twelve calls and 4 for the last. Call scheduling belongs to the
future generation layer.

## Response contract

Every response is a JSON object containing exactly one `queries` array, even for
a single query. The prompt selects one query kind for the entire batch.

Find response:

```json
{"queries": [
  {"collection": "businesses", "filter": {"stars": {"$gte": 4}}, "projection": {"name": 1}, "sort": [["stars", -1], ["name", 1]], "skip": 10, "limit": 20},
  {"collection": "reviews", "filter": {"stars": 5}}
]}
```

Find entries require `collection` and `filter`; `projection` may be omitted or
null. The following find options are also accepted:

| Field | JSON value | Default |
| --- | --- | --- |
| `sort` | Ordered array of `[field, direction]` pairs; direction is integer `1` or `-1` | `[]` (no sorting) |
| `skip` | Nonnegative integer | `0` |
| `limit` | Positive integer or `null` | `null` (unlimited) |

Sort arrays are converted to BONDI tuples without changing field order. Field
names must be nonempty strings without null characters. Booleans are not accepted
as integers; `limit=0` is invalid, and `sort=null` is invalid. Invalid options are
candidate-level `invalid_query_shape` errors. Unknown keys are still rejected.

These options are part of the generated query: skip can make output empty, and
limit affects returned counts and execution time. They are preserved when saving
the query in a BONDI workload. Aggregation entries do not accept these fields;
aggregation sorting and pagination belong in pipeline stages.

Aggregation response:

```json
{"queries": [{"collection": "businesses", "pipeline": [
  {"$lookup": {"from": "reviews", "localField": "_id", "foreignField": "business_id", "as": "reviews"}}
]}]}
```

Aggregation entries require exactly `collection` and `pipeline`. Each starting
collection must appear in the configured catalogue; the database comes from the
caller. Foreign collection references remain native pipeline content and are not
validated by this parser.

## Example

```python
from json_storm.parsing import parse_batch

result = parse_batch(
    '{"queries": [{"collection": "businesses", "filter": {}}]}',
    batch_index=0,
    query_kind="find",
    database="research",
    collections=["businesses", "reviews", "users"],
    expected_count=1,
)
assert result.count_matches is True
query = result.candidates[0].query
assert query.target.collection == "businesses"
```

The parser performs no model calls, database operations, or workload execution.
Accepted queries can later become BONDI `WorkloadEntry` objects. Preserve the
candidate's `(batch_index, position)` alongside each workload entry: invalid entries
are absent from workloads, so workload positions alone cannot identify candidates.
Batch indices must be unique within the caller's experiment. Across experiments,
identify a candidate by `(experiment_id, batch_index, position)`. The parser
does not allocate indices or check uniqueness across calls. Provider request IDs
belong in separate generation metadata.

## Failure and counting rules

- `invalid_json`: undecodable JSON, duplicate object keys, or nonstandard numeric
  literals such as `NaN` and `Infinity`. Markdown fences are not stripped.
- Batch-level `invalid_query_shape`: the outer object is not exactly a `queries`
  array. No candidates can be extracted reliably.
- Candidate-level `invalid_query_shape`: an entry violates the response contract,
  selects an unknown starting collection, or fails BONDI structural validation.
  Other entries remain available.
- Invalid caller configuration raises an exception rather than being recorded as
  a model failure.

`actual_count` counts all returned entries, including invalid ones. Missing or
extra entries produce `count_matches=False`; duplicates and excess entries are
preserved. An empty array has count zero. For whole-response failures the count
and comparison are unknown (`None`), rather than zero. There is no repair,
truncation, replacement generation, or deduplication.

Plain JSON is decoded with Python's standard numeric representation. Extended
JSON markers such as `$date` remain dictionaries; BSON conversion is not part of
this contract. Numeric BSON encodability and MongoDB semantic validity are not
established here.

Parsing success does not authorize execution. Unknown operators and write stages
such as `$out` can be represented by BONDI. A later evaluator must enforce the
read-only execution policy before running queries.
