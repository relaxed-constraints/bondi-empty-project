# Yanex generation experiment

First create a schema snapshot, then reuse its ID across generation runs:

```sh
uv run yanex run experiments/schema.py -c experiments/configs/schema.yaml -n mathexchange-schema
# Substitute the schema experiment ID printed above:
uv run yanex run experiments/generate.py -c experiments/configs/generate.yaml -D schema=<schema-exp-id> --dry-run
uv run yanex run experiments/generate.py -c experiments/configs/generate.yaml -D schema=<schema-exp-id>
# All seven prompts use the same parsed schemas:
uv run yanex run experiments/generate.py -c experiments/configs/generate.yaml -D schema=<schema-exp-id> -p 'prompt_id=p1,p2,p3,p4,p5,p6,p7'
```

`schema.yaml` owns MongoDB URI, namespaces, sample size and value retention.
`generate.yaml` owns prompt/model settings, query counts and example rendering.
Generation requires a completed `schema.py` run in the `schema` dependency slot.
It loads `schema_manifest.json` and `schemas.pkl` with `yanex.load_artifact()`,
which searches the dependency chain. Ambiguous artifact matches raise rather than
silently choosing a snapshot. Dependencies do not rerun schema sampling.

The schema experiment samples `mongodb://localhost:27018` and the three
`mathexchange` namespaces (`users`, `posts`, `postHistory`). `sample_size` is a
per-collection maximum. It uses BONDI `MongoExecutor` with native `$sample` and
`collect_results=True`, followed by `Schema.from_documents`. It writes nothing
to MongoDB. Empty/missing collection samples fail explicitly. Namespaces must be
distinct and belong to one database; collection-name dots are preserved.
Authenticated URIs can use `JSON_STORM_MONGODB_URI` in `.env`, overriding the config
without putting credentials into Yanex parameters.

Schema-run artifacts:

- `schemas.pkl`: parsed BONDI schemas, saved with Yanex's native pickle support.
- `schema_manifest.json`: format/BONDI version, database, namespaces, sample counts,
  value modes, and completion status.
- `schema_samples.jsonl`: sampled documents as canonical BSON Extended JSON.
- `schema_preview.txt`: baseline rendering without example values.

BONDI 0.1.4 has no native schema persistence API. Pickle is an interim format for
trusted local artifacts only, and generation rejects a different BONDI version.
Keep the BSON samples for reconstruction after upgrades. Native schema persistence
is tracked in [BONDI issue #2](https://github.com/relaxed-constraints/bondi/issues/2).
Distinct values are retained by default so generation can vary `examples_per_type`
without resampling; examples remain disabled by default. Retention uses memory
proportional to distinct values in the sample.

Generation makes no database connection. Its `schema.txt` records the exact
rendering used, which can differ intentionally if example settings change.

Calls are sequential, and model-call failures stop the run after preserving
partial artifacts. Parse errors and count mismatches are research observations;
a run can complete even if no queries are accepted. Inspect metrics, not just
process status. Generated queries are not executed or certified read-only.

## Artifact contract (format version 1)

| Artifact | Contents |
| --- | --- |
| `schema.txt` | Exact rendered schema catalogue |
| `batches/000000.json`, etc. | Exact prompt, full normalized model response, usage, system instructions, errors |
| `candidates.jsonl` | Decoded entries, parser errors, target violations and acceptance |
| `workload.jsonl` | Accepted native BONDI queries, preserving order and duplicates |
| `workload_mapping.json` | Workload position to batch index and candidate position |
| `manifest.json` | Format version, running/completed/failed status, counts and library versions |

The schema dependency retains all sampled inputs. Its `$sample` call is unseeded,
but all generation runs referencing the same snapshot use the same observations.
Generation does not copy the pickle into its own artifacts, avoiding duplicate
matches during dependency-chain lookup.

Each checkpoint saves the workload through the requested native custom saver:

```python
yanex.save_artifact(workload, "workload.jsonl", saver=lambda obj, path: obj.save(path))
```

The evaluation experiment will attach the generation run as a dependency and use:

```python
workload = yanex.load_artifact("workload.jsonl", loader=Workload.load)
```

An empty workload is valid and is still saved. Batch artifacts are written first;
cumulative files and the manifest are then replaced. This is not a transactional
multi-file write: after an interrupted process, a running manifest must not be
treated as completed. Provider failure records retain exception type, not possibly
credential-bearing error text. Inference response text is preserved unchanged.

## Metrics

`yanex.log_metrics` records outcome counts: attempted batches, failed model calls,
whole-response parse failures, count mismatches, returned entries, parsed queries,
entry parse failures, target violations, persistence failures, and accepted queries. `queries_parsed`
includes target violations and persistence failures; `queries_accepted` excludes both. Whole-response parse
failures have unknown candidate counts and are counted at batch level.

Observed token/cost sums and `model_elapsed_ms` are included. Each token/cost
sum has a corresponding `*_reported_calls` count; absent usage is not zero-filled.
No configuration parameters are repeated as metrics. The final metric record is
written on both success and caught failure.

`schema.py` can also run standalone with defaults and saves to `./artifacts/`.
`generate.py` requires Yanex tracking because its schema dependency is mandatory;
it no longer samples from MongoDB or supports standalone generation. The reusable
`generate_queries` function and generation notebook remain usable without Yanex.

## Verified smoke run

On 2026-11-03, generation run `85f1df85` sampled five documents from each of the
three configured collections (15 total), then generated and accepted two find
queries with local Qwen. The run persisted its parameters, outcome metrics,
samples, batch response, mapping, and native workload. A separate dependency run
`a962b25d` successfully restored both queries using
`yanex.load_artifact("workload.jsonl", loader=Workload.load)` and verified the mapping.
These checks did not execute generated queries against MongoDB. The source was
uncommitted during validation; Yanex's Git snapshot does not capture untracked
files, so these IDs are development smoke evidence, not release provenance.


### Persistence failures are not query syntax errors

Before accepting a candidate into the saved workload, the recorder calls BONDI's
`to_json()` to verify persistence. BONDI 0.1.4 rejects some structurally valid native
queries whose dictionaries resemble Extended JSON wrappers, including `{"$regex":
"pattern"}`. For directly supplied native dictionaries, such candidates retain their raw content and get a separate
`persistence_error` in `candidates.jsonl`; `queries_persistence_failed` counts them.
They remain counted as parsed, but are excluded from the persisted workload.
This is a toolkit serialization limitation, not proof of invalid MongoDB syntax.
Do not use the accepted rate as a model-validity rate without accounting for it.
Lossless persistence of these forms requires a separate BONDI serialization change.

Failure-checkpoint errors are attached as notes to the original exception rather
than replacing it. Previously failed run artifacts are not rewritten by this fix.

The model-output parser now decodes Extended JSON with PyMongo, so model-generated
regex wrappers become BSON Regex values before BONDI persistence and avoid this
particular failure. The persistence guard remains for other unsupported inputs.


## Schema dependency smoke validation

Schema run `5d44c25c` saved three parsed schemas from 15 sampled documents.
Generation run `6b015a08` used `-D schema=5d44c25c` and generated one accepted query
without database access. Both runs completed. These are development smoke tests;
use a full sample snapshot for the next controlled comparison.
