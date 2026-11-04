"""Prepare independent read-only query probes for native BONDI execution."""

from copy import deepcopy

from bondi.mongodb import MongoAggregateQuery, MongoFindQuery
from bondi.workload import Workload, WorkloadEntry


def _validate_mongo_workload(workload: Workload) -> None:
    workload.validate()
    for entry in workload:
        if not isinstance(entry.query, (MongoFindQuery, MongoAggregateQuery)):
            raise TypeError(
                "Execution analysis supports only native MongoDB find/aggregate queries"
            )


def _check_pipeline(pipeline: list) -> None:
    """Inspect stage positions, not literal document keys that happen to start with $."""
    for stage in pipeline:
        if "$out" in stage or "$merge" in stage:
            raise ValueError("Existence probes do not support write stages $out or $merge")
        lookup = stage.get("$lookup")
        if isinstance(lookup, dict) and isinstance(lookup.get("pipeline"), list):
            _check_pipeline(lookup["pipeline"])
        union = stage.get("$unionWith")
        if isinstance(union, dict) and isinstance(union.get("pipeline"), list):
            _check_pipeline(union["pipeline"])
        facet = stage.get("$facet")
        if isinstance(facet, dict):
            for branch in facet.values():
                if isinstance(branch, list):
                    _check_pipeline(branch)


def make_existence_workload(workload: Workload) -> Workload:
    """Copy a MongoDB workload, limiting each query's output to at most one row.

    Find limits are replaced with 1; aggregation pipelines gain a final $limit: 1.
    All other query fields, entry order and pattern IDs are preserved. Copies are
    independent even when original entries share a query. Write stages, including
    those inside known nested pipelines, raise ValueError before any execution.
    This function performs no database I/O and never serializes queries.
    """
    _validate_mongo_workload(workload)
    entries = []
    for entry in workload:
        query = deepcopy(entry.query)
        if isinstance(query, MongoFindQuery):
            query.limit = 1
        else:
            _check_pipeline(query.pipeline)
            query.pipeline.append({"$limit": 1})
        entries.append(WorkloadEntry(query, pattern_id=entry.pattern_id))
    return Workload(entries)
