# Generation analysis

The executed `notebooks/analysis.ipynb` walks through all four helpers using the
recent Sol and Qwen sweeps, with visible tables and a model comparison chart.

Use native Yanex experiments directly; the helpers do not create another run class.
All four helpers validate that `experiment.script_path.name` is `generate.py` and
raise `ValueError` otherwise (including when the script path is missing).

```python
import yanex.results as yr
from json_storm.analysis import summarize_run, batch_table, candidate_table, runs_table

experiment = yr.get_experiment('af97d240')
summary = summarize_run(experiment)
batches = batch_table(experiment)
candidates = candidate_table(experiment)
failures = candidates[candidates['outcome'] != 'accepted']

experiments = yr.get_experiments(ids=['57d6f1c3', '28b9755c'])
runs = runs_table(experiments)
print(runs[['experiment_id', 'model', 'prompt_id', 'accepted_yield', 'distinct_yield']])
```

## Returned data

- `summarize_run`: dictionary containing ID, name, status, checkpoint status,
  model/prompt/batch configuration, schema SHA256, recorded metrics and derived values.
- `batch_table`: one row per saved or manifest-listed batch. Includes requested count,
  outcome, original parse error, finish reason, elapsed milliseconds and normalized
  token/cost fields. Outcomes are `decoded`, `batch_parse_failed`, `model_call_failed`
  or `missing_artifact`. Both nested and historical flattened paths are supported.
- `candidate_table`: one row per decoded candidate, retaining raw query, errors and
  target/persistence outcomes. Accepted queries receive native BONDI fingerprints
  and workload positions using the saved mapping. Outcomes are `accepted`,
  `parse_failed`, `target_violation`, `persistence_failed` or `unknown`.
- `runs_table`: stacks summaries in input order. Keeps failed experiments and repeated
  selections; does not aggregate repetitions. Empty input yields an empty table with
  experiment_id/name/status columns.

Yields are fractions: `accepted_yield = queries_accepted / num_queries` and
`distinct_yield = unique_queries / num_queries`. Uniqueness is per experiment and
uses native query fingerprints, not semantic similarity. `exact_duplicate_queries`
counts accepted entries beyond the first occurrence. `undecodable_batch_slots` sums
requested counts of unreadable batches; these are not recovered candidate counts.

`model_seconds` and `seconds_per_accepted` use recorded model-call time, not total
experiment duration. Each usage field has a `<field>_per_accepted` derivative.
Original `<field>_reported_calls` metrics remain available: ratios of partially
reported usage are partial too. Missing values and zero denominators produce None
(or pandas missing values), not zero costs/times. Token counts across providers
are not necessarily comparable because tokenizers and accounting differ.

## Partial runs and missing artifacts

The latest logged metric step is used as one snapshot; only when there are no
logged metrics do helpers fall back to manifest metrics. `metrics_source` identifies
that choice. Artifacts and metrics can disagree after interrupted checkpoints.
Distinct counts are unavailable unless candidate acceptance counts agree with the
metrics and every accepted candidate has a fingerprint. Missing or corrupt data is
never repaired. Invalid mapping positions and unsupported manifest versions raise.

An empty candidate table has `table.attrs['artifact_available']` to distinguish a
missing artifact from a saved empty list. Batch tables expose `manifest_available`
in attrs and `artifact_available` per row. These attrs are notebook conveniences;
they are not preserved by CSV exports. Summary missing values and manifest status
provide context for exported run tables. Batch files written before an interrupted
checkpoint are discovered even if the manifest is absent or older.

The helpers only read artifacts through Yanex and load workloads with `Workload.load`.
They never call models, execute MongoDB queries, modify experiments or save output.
Call `experiment.refresh()` yourself when reusing a live Yanex object after a run
changes. Plotting, automatic reports and further comparison helpers are separate
future steps.

## Field reference

### `summarize_run(experiment)`

Returns a dictionary for one experiment. Recorded metric keys are included only
when present in the selected metric snapshot; configuration and derived keys below
are always included, with `None` where unavailable. Additional recorded metrics
are passed through too, except Yanex's `step`, `timestamp` and `last_updated`.

| Key | Meaning |
| --- | --- |
| `experiment_id` | Yanex experiment ID. |
| `name` | Experiment name, if assigned. |
| `status` | Yanex run status, such as `completed`, `failed` or `running`. |
| `manifest_status` | Status recorded in the generation checkpoint; may differ from the run status after interruption. |
| `metrics_source` | `logged` for the latest logged step, `manifest` for checkpoint fallback, or `None` if neither exists. |
| `prompt_id` | Selected prompt template, such as `p1`. |
| `model` | Configured provider/model string. |
| `num_queries` | Total number of queries requested for the run. |
| `batch_size` | Requested queries per call; the final batch can be smaller. |
| `target_collection` | Required starting collection for generated queries. |
| `examples_per_type` | Configured number of example values per schema type. |
| `relationship_hints` | Configured relationship hints included in prompting, if any. |
| `system_instructions` | Configured system instruction text. |
| `model_parameters` | Dictionary of provider parameters, such as reasoning effort or thinking settings. |
| `reasoning_effort` | Convenience copy of `model_parameters.reasoning_effort`, if configured. |
| `schema_sha256` | Hash of the exact rendered schema text; equal hashes identify equal schema inputs. |
| `batches_attempted` | Number of model calls attempted. |
| `model_calls_failed` | Calls that raised an error. |
| `batches_parse_failed` | Responses that could not be decoded into the expected query envelope. |
| `batches_count_mismatch` | Decoded batches returning a different candidate count from the requested count. |
| `queries_returned` | Candidates extracted from decoded responses; excludes unknown contents of undecodable batches. |
| `queries_parsed` | Candidates successfully constructed as BONDI query objects. |
| `queries_parse_failed` | Extracted candidates that could not become BONDI query objects. |
| `queries_target_violations` | Parsed queries starting from a collection other than the configured target. |
| `queries_persistence_failed` | Parsed, target-compliant queries that failed serialization. |
| `queries_accepted` | Queries passing parsing, target and serialization checks and included in the workload. |
| `unique_queries` | Distinct fingerprints among accepted queries in this run; unavailable when artifact coverage is incomplete. |
| `exact_duplicate_queries` | Accepted entries beyond the first occurrence of each fingerprint. |
| `accepted_yield` | `queries_accepted / num_queries`, as a fraction. |
| `distinct_yield` | `unique_queries / num_queries`, as a fraction. |
| `undecodable_batch_slots` | Sum of requested counts for undecodable batches, when batch artifacts and attempt counts agree. Not a count of extracted candidates. |
| `model_elapsed_ms` | Recorded total model-call duration in milliseconds; failed calls without a response have no recorded duration. |
| `model_seconds` | `model_elapsed_ms / 1000`. |
| `seconds_per_accepted` | Recorded model-call seconds divided by accepted queries. |
| `input_tokens` | Sum of reported input tokens. |
| `output_tokens` | Sum of reported output tokens. |
| `total_tokens` | Sum of provider-reported total tokens. |
| `reasoning_tokens` | Sum of reported reasoning tokens; a usage detail, not an extra amount to add to total tokens. |
| `cached_input_tokens` | Sum of reported cached input tokens; a usage detail, not an extra amount to add to total tokens. |
| `estimated_cost_usd` | Sum of available cost estimates in US dollars; unavailable is not zero cost. |
| `input_tokens_reported_calls` | Calls reporting input-token usage. |
| `output_tokens_reported_calls` | Calls reporting output-token usage. |
| `total_tokens_reported_calls` | Calls reporting total-token usage. |
| `reasoning_tokens_reported_calls` | Calls reporting reasoning-token usage, including explicit zero values. |
| `cached_input_tokens_reported_calls` | Calls reporting cached-input usage, including explicit zero values. |
| `estimated_cost_usd_reported_calls` | Calls providing a cost estimate. |
| `input_tokens_per_accepted` | Reported input tokens divided by accepted queries. |
| `output_tokens_per_accepted` | Reported output tokens divided by accepted queries. |
| `total_tokens_per_accepted` | Reported total tokens divided by accepted queries. |
| `reasoning_tokens_per_accepted` | Reported reasoning tokens divided by accepted queries. |
| `cached_input_tokens_per_accepted` | Reported cached input tokens divided by accepted queries. |
| `estimated_cost_usd_per_accepted` | Available cost estimates divided by accepted queries. |

Ratios are `None` when their numerator is missing or denominator is zero. Usage
ratios can reflect partial reporting; check the corresponding reported-call counts.

### `batch_table(experiment)`

Returns a DataFrame with one row per saved or manifest-listed batch. These columns
exist even when the table is empty. Missing measurements use pandas missing values.

| Column | Meaning |
| --- | --- |
| `experiment_id` | Yanex experiment ID. |
| `batch_index` | Zero-based batch index within the run. |
| `artifact_available` | Whether the batch artifact could be found. |
| `requested_count` | Number of queries requested in this call; unavailable if its artifact is missing. |
| `outcome` | `decoded`: response envelope decoded; `batch_parse_failed`: envelope decoding failed; `model_call_failed`: call raised an error; `missing_artifact`: recorded batch file could not be found. |
| `error_type` | Model-call exception class name, if the call failed. |
| `parse_error` | Original batch decoding error dictionary (`status` and `message`), if present. |
| `finish_reason` | Model-reported reason generation ended, such as `stop`; not a statement about query validity. |
| `elapsed_ms` | Recorded duration of this model call in milliseconds, when a response exists. |
| `input_tokens` | Input tokens reported for this call. |
| `output_tokens` | Output tokens reported for this call. |
| `total_tokens` | Total tokens reported for this call. |
| `reasoning_tokens` | Reasoning-token usage detail reported for this call. |
| `cached_input_tokens` | Cached-input usage detail reported for this call. |
| `estimated_cost_usd` | Available cost estimate for this call in US dollars. |
| `table.attrs['manifest_available']` | DataFrame metadata, not a column: whether the generation manifest exists. |

`decoded` does not mean every candidate was accepted. Count mismatches are not a
separate batch outcome; their run-level count is available in `summarize_run`.

### `candidate_table(experiment)`

Returns a DataFrame with one row per extracted candidate. A candidate is one entry
from the decoded response's `queries` array, before acceptance checks. Undecodable
batches produce no candidate rows. These columns exist even for an empty table.

| Column | Meaning |
| --- | --- |
| `experiment_id` | Yanex experiment ID. |
| `batch_index` | Zero-based index of the batch containing this candidate. |
| `position` | Zero-based candidate position within that batch. |
| `raw` | Original decoded JSON entry, retained even if invalid; not a BONDI query object. |
| `error` | Candidate parsing error dictionary (`status` and `message`), if present. |
| `target_violation` | Whether the candidate violates the required starting collection. |
| `accepted` | Whether it passed parsing, target and persistence checks. |
| `persistence_error` | Serialization error dictionary (`type` and `message`), if present. |
| `outcome` | `parse_failed`, `target_violation`, `persistence_failed`, `accepted`, or `unknown` when the recorded fields establish none of those outcomes. |
| `workload_position` | Zero-based position in the accepted workload, when the workload and mapping are available. |
| `fingerprint` | Native BONDI query fingerprint from the mapped workload entry, for detecting exact repetitions. |
| `table.attrs['artifact_available']` | DataFrame metadata, not a column: distinguishes a missing candidate artifact from a saved empty list. |

Rejected candidates normally have no workload position or fingerprint. Missing
workload/mapping artifacts can also leave those fields missing for accepted entries.
When multiple failure flags exist, `outcome` takes the first in this order: parse
failure, target violation, persistence failure, acceptance, unknown.

### `runs_table(experiments)`

Returns a DataFrame with one `summarize_run` dictionary per input experiment.
Its columns are exactly the union of summary keys described above; no extra
comparison metrics or averages are calculated.

| Column or column group | Meaning |
| --- | --- |
| `experiment_id`, `name`, `status` | Identity and status of the experiment represented by this row. Also the only columns for empty input. |
| `manifest_status`, `metrics_source` | Checkpoint status and provenance of that row's metrics. |
| `prompt_id`, `model`, `num_queries`, `batch_size`, `target_collection` | Main configuration columns for selecting, grouping and comparing experiments. |
| `examples_per_type`, `relationship_hints`, `system_instructions`, `model_parameters`, `reasoning_effort`, `schema_sha256` | Remaining configuration and schema context, with the same meanings as in `summarize_run`. |
| Recorded metric columns | All metrics included by the individual summaries, including failure counts, usage and reporting coverage. A metric absent from a run becomes a missing value in that row. |
| `unique_queries`, `exact_duplicate_queries`, `accepted_yield`, `distinct_yield`, `undecodable_batch_slots` | Per-run diversity and yield measures; not calculated across the combined selection. |
| `model_seconds`, `seconds_per_accepted`, the six `*_per_accepted` usage columns | Per-run time and usage derivatives, as defined in the summary table. |

Input order and repeated selections are preserved. The DataFrame index is an
ordinary row index; `experiment_id` remains a column. Failed runs are not filtered
out. DataFrame attrs from batch/candidate tables are not copied into this table.
