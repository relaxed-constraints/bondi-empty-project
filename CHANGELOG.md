# Changelog

## Unreleased

- Add an executed educational analysis notebook covering the four generation
  helpers, candidate failures, duplicates and prompt/model comparisons.

- Add read-only generation analysis helpers using native Yanex experiments, with
  script validation, batch/candidate tables, yield and fingerprint diversity summaries.

- Split schema sampling into a reusable Yanex experiment; generation now requires
  a completed schema dependency and loads parsed BONDI schemas without MongoDB access.

- Decode model responses with PyMongo Extended JSON semantics while retaining raw
  JSON and strict duplicate-key checks; add BSON prompt examples and round-trip tests.

- Preserve per-candidate BONDI persistence failures without aborting workload saving;
  keep original experiment exceptions when failure checkpointing also fails.

- Add a Yanex generation experiment sampling configured MongoDB namespaces through
  BONDI, checkpointing native workloads and provenance, and logging outcome metrics.

- Add an educational generation notebook covering schemas, prompts, model calls,
  batch inspection, usage metadata, and offline workload construction.

- Add lazy sequential batch generation with exact prompt/response provenance,
  partial-result preservation, target violation records, and stop-on-call-failure behavior.

- Use configurable, recorded system instructions with the same MongoDB default
  across API and subscription routes.

- Replace subscription-route Codex instructions with an explicit MongoDB query
  generation instruction and record it in model responses.

- Support ChatGPT subscription routes with explicit billing metadata, OAuth setup
  instructions, and rejection of unsupported token-limit settings.

- Add explicit dotenv credential loading and a synchronous LiteLLM adapter with
  configurable reasoning, usage breakdowns, cost estimates, and response metadata.

- Add batch-aware prompt templates with optional target collections and relationship
  hints; adapt p1–p7 to the shared parser-compatible response contract.

- Add offline schema catalogue rendering with explicit nested/array paths, literal
  name quoting, missing/null observations, and optional deterministic examples.

- Identify parsed batches and candidates with a nonnegative integer `batch_index`
  instead of a string `batch_id`.

- Accept optional find sort, skip, and limit fields with BONDI validation,
  preserving sort order and pagination through workload persistence.

- Add strict batched JSON parsing for MongoDB find and aggregation responses,
  with configured collection targets, native BONDI query objects, per-entry
  failures, original responses, and explicit batch count comparisons.
- Document the parsing contract and API; replace the obsolete greeting test with
  offline parser and BONDI workload interoperability tests.
