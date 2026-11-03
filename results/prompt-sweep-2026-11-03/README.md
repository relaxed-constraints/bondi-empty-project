# Seven-prompt generation sweep analysis

Reproduce from the repository root:

```sh
uv run python results/prompt-sweep-2026-11-03/analyze.py
```

Uses explicit Yanex IDs and no model or MongoDB calls. Source runs are unchanged.
Outputs: summary.csv, batches.csv, failures.json, yield.png/svg, efficiency.png/svg.

## Findings

- Accepted: p1 51, p2 99, p3 87, p4 90, p5 0 (incomplete), p6 98, p7 61.
- p1: five batch decode failures: one duplicate creationDate key and four malformed
  JSON responses. One decoded batch contains 11 entries rather than 10.
- p2: one candidate rejected for skip=null.
- p3: one whole batch rejected for ObjectId(...) shell syntax; three candidates
  rejected for skip=null.
- p4: one whole batch rejected for duplicate creationDate keys.
- p5: first model call recorded Timeout; configured deadline 120 seconds. Nine
  batches unattempted. No response, usage or model latency retained for failed call.
- p6: two candidates rejected for skip=null; no regex persistence errors.
- p7: four malformed JSON batches, including a bare {"$now"} object, misplaced
  brackets, a trailing comma, and a malformed $divide object. One decoded batch
  contains 11 entries rather than 10.
- All 60 returned model responses report finish_reason=stop: no reported output
  truncation. Stop is not a guarantee of well-formed JSON.
- Twelve rejected batches affect 120 requested query slots; six individual entries
  fail structural validation. Two extra returned entries produce 486 accepted
  queries across the six completed runs. Unreadable batches have unknown actual
  candidate counts; 120 is requested slots, not measured invalid queries.
- p1/p7 require approximately 12.0/11.4 minutes and 1097/824 output tokens per
  accepted query. p2/p3/p4/p6 require approximately 1.9–3.2 minutes and 101–151
  output tokens per accepted query. Token efficiency includes discarded responses.
- Exact serialized-query duplicate counts: p3 five, p4 two, others zero among
  persisted workloads. This does not measure semantic diversity or query shapes.

## Interpretation limits and next experiments

All model/configuration settings match except prompt_id, but the saved schema text
hash differs for every run because samples were drawn afresh. One run per prompt
is descriptive evidence, not a significance test. Find and aggregation prompts
also ask for fundamentally different work. Accepted means parsed and persisted,
not MongoDB semantic validity, nonempty results, safe execution, or performance.

Priorities: reuse one schema/sample snapshot across comparisons; test batch sizes
1/2/5/10 especially for long aggregation prompts; rerun p5 under an explicitly
recorded longer deadline or smaller batch; strengthen skip/date/ObjectId/duplicate
key examples without silently repairing responses; compare JSON/structured-output
mode as a separate treatment; evaluate persisted queries before ranking quality.

The current artifacts omit elapsed time and usage on model failures, so p5's
missing entries must not be interpreted as zero. Yanex also stored batch artifacts
as flat 000000.json names despite manifest entries saying batches/000000.json;
this analysis reads the actual artifact names. That naming mismatch deserves a
small persistence cleanup before relying on manifest-based discovery.
