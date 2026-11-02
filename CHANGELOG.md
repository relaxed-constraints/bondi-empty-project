# Changelog

## Unreleased

- Identify parsed batches and candidates with a nonnegative integer `batch_index`
  instead of a string `batch_id`.

- Accept optional find sort, skip, and limit fields with BONDI validation,
  preserving sort order and pagination through workload persistence.

- Add strict batched JSON parsing for MongoDB find and aggregation responses,
  with configured collection targets, native BONDI query objects, per-entry
  failures, original responses, and explicit batch count comparisons.
- Document the parsing contract and API; replace the obsolete greeting test with
  offline parser and BONDI workload interoperability tests.
