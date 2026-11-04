# Query execution probes

Use `notebooks/execution_analysis.ipynb` to inspect saved results and compare
runs. Fill in its empty `execution_ids` list with new `execute.py` experiment IDs.
It reads artifacts only and includes both classification helpers and cross-run plots.

`json_storm.execution` prepares probe workloads; `json_storm.analysis` classifies
results into tables. These helpers use native BONDI workloads and results. They do not connect to
MongoDB or execute queries themselves. Use the executor directly, with a timeout
and `continue_on_error=True` so every query receives a result.

```python
from bondi.mongodb import MongoExecutor
from json_storm.execution import make_existence_workload
from json_storm.analysis import execution_planning_table, execution_existence_table

# workload is an already-loaded native BONDI Workload.
# Validate read-only scope and create independent query copies before any execution.
probe = make_existence_workload(workload)
with MongoExecutor.from_uri(
    "mongodb://localhost:27018",
    timeout_seconds=10,
    continue_on_error=True,
) as executor:
    planning_results = executor.explain_workload(workload)
    existence_results = executor.run_workload(probe)

planning = execution_planning_table(workload, planning_results)
existence = execution_existence_table(workload, existence_results)
print(planning["outcome"].value_counts())
print(existence["outcome"].value_counts())
```

BONDI consumes the output cursor and records row counts without retaining documents
by default. Its planning-only explain uses the real namespace and index context.
See the [BONDI execution guide](https://relaxed-constraints.github.io/bondi/executor/).

## `make_existence_workload(workload) -> Workload`

Returns a new workload in the same order with the same pattern IDs. Each query is
an independent deep copy, including BSON values. Find limits become 1; filter,
projection, sort and skip stay unchanged. Aggregations gain a final `{$limit: 1}`;
existing stages and limits remain. The original workload is never mutated or
serialized. Empty workloads are supported; other database backends raise TypeError.

`$out` and `$merge` stage positions are rejected with ValueError, also inside
`$lookup`, `$unionWith` and `$facet` pipelines. Literal document keys are not treated
as stages. This is a read-query scope check, not a substitute for database access
permissions. Unsupported workloads are rejected as a whole, not silently filtered.

A final limit bounds output, not upstream work: grouping, sorting and joins may
still be expensive. Timeout results are unknown, not empty. Nonempty means one
output document, even if it contains an empty array or zero count. A successful
probe does not prove the original full query will complete or avoid later errors.

## Classification tables

Both helpers accept the original workload and its ordered sequence of native
`ExecutionResult` objects. They validate equal lengths; callers must preserve
ordering because a result does not itself identify its query. They do not mutate
results or discard their raw diagnostic data: retain the original result list.
BONDI's unstarted `None` entries are rejected with TypeError; use
`continue_on_error=True` to collect results for every entry.

`execution_planning_table` outcomes:

| Outcome | Meaning |
| --- | --- |
| `passed` | Explain succeeded; not proof of runtime validity. |
| `syntax_error` | MongoDB OperationFailure code 9 (FailedToParse) or 40324 (unrecognized pipeline stage). |
| `other_error` | Any other error, including missing indexes, permissions and unrecognized syntax codes. |
| `timeout` | BONDI identifies a timeout; takes precedence over error classification. |

The syntax-code set is intentionally narrow and does not infer categories from
message text. Thus syntax_error counts are conservative, not exhaustive. Broad
codes such as BadValue (2) are left as other_error for inspection.

`execution_existence_table` outcomes:

| Outcome | Meaning |
| --- | --- |
| `empty` | Successful limit-one execution returned zero rows. |
| `nonempty` | Successful limit-one execution returned one row. |
| `error` | Execution failed for any non-timeout reason. |
| `timeout` | Execution timed out; result existence remains unknown. |

Successful results with missing, negative or greater-than-one row counts raise
ValueError. The tables cannot verify that a count of zero/one actually came from
the correct probe; supply results from `make_existence_workload` as shown above.

Both tables contain these columns, including for empty input:

| Column | Meaning |
| --- | --- |
| `workload_position` | Zero-based original workload position, for joining generation mappings. |
| `pattern_id` | Original optional BONDI pattern membership. |
| `database`, `collection` | Original query namespace. |
| `query_kind` | `find` or `aggregate`. |
| `outcome` | Phase-specific classification listed above. |
| `elapsed_ms` | BONDI client-observed duration; probe time is not full-query runtime. |
| `row_count` | Native result count, normally missing for planning and failures. |
| `error_type` | Original exception class name, if any. |
| `error_code` | MongoDB OperationFailure code, when available. |
| `error_code_name` | Code name from the exception details, when available. |
| `error_message` | Original exception text, when present. |
| `warnings` | Original BONDI warning tuple. |

There is no fingerprint dependency: classification still works for BSON queries
that the installed BONDI serializer cannot persist. The classification helpers do not create Yanex runs or automatic reports.

## Yanex execution experiment

Run from the repository root, passing a generation experiment in the `generate` slot:

```sh
uv run yanex run experiments/execute.py \
  -c experiments/configs/execute.yaml \
  -D generate=af97d240 -n execute-sol-p6
```

`execute.py` validates the dependency script with
`yanex.assert_dependency('generate.py', slot='generate')` and loads the workload
through `yanex.load_artifact('workload.jsonl', loader=Workload.load)`. Yanex searches
the dependency chain. This requires a tracked run, not standalone invocation.
A saved partial workload from a failed generation run can also be evaluated: this
experiment evaluates the available accepted workload, not the requested query count.
Missing workloads fail explicitly. An empty saved workload yields zero counts.

Configuration controls MongoDB URI, operation timeout and concurrency.
`JSON_STORM_MONGODB_URI` (including from the repository `.env`) overrides the URI.
Parameters are tracked by Yanex and are not repeated as metrics. Namespace targets
come from the workload. Both phases run over every entry, regardless of planning
outcome, using `continue_on_error=True`. Write-stage rejection happens before the
connection is opened. A completed experiment can contain individual query errors
and timeouts; those are measured outcomes rather than orchestration failures.

Metrics (all eight are logged, including zeros):

| Planning | Existence |
| --- | --- |
| `planning_passed` | `existence_empty` |
| `planning_syntax_error` | `existence_nonempty` |
| `planning_other_error` | `existence_error` |
| `planning_timeout` | `existence_timeout` |

Both phases log into step 0 so the final metric snapshot contains both sets.

| Artifact | Contents |
| --- | --- |
| `planning_results.pkl` | Native ordered BONDI ExecutionResults, including raw explain output and exceptions. |
| `existence_results.pkl` | Native ordered probe results, including row counts, timings, warnings and exceptions. Documents are not collected. |
| `planning.csv` | Planning classification table. |
| `existence.csv` | Existence classification table. |
| `execution_manifest.json` | Format version, generation ID, workload size, library versions, probe strategy, status and completed phases. |

Each phase saves raw results before classification, then its table and metrics.
If a later phase fails unexpectedly, earlier artifacts and metrics remain available;
the manifest is marked failed. A hard process interruption can leave a running
manifest or partially written phase artifacts. No per-query streaming checkpoint
is implemented: results are saved when each BONDI workload call returns.

Load native results through the Yanex Results API:

```python
import yanex.results as yr

experiment = yr.get_experiment("YOUR_EXECUTION_ID")
results = experiment.load_artifact("planning_results.pkl")
table = experiment.load_artifact("planning.csv")
```

Pickle preserves native exceptions and BSON values but is Python/library-version
specific: load only trusted experiment artifacts. The manifest records BONDI and
Yanex versions. CSV is the portable classification view; native raw output stays
in the pickle artifacts.
