"""Read-only generation and execution analysis using native Yanex and BONDI objects."""

import hashlib
import json
from collections.abc import Sequence
from pathlib import Path

import pandas as pd
from bondi.execution import ExecutionResult
from bondi.mongodb import MongoFindQuery
from bondi.workload import Workload
from pymongo.errors import OperationFailure
from yanex.results import Experiment

from json_storm.execution import _validate_mongo_workload

_USAGE = (
    "input_tokens",
    "output_tokens",
    "total_tokens",
    "reasoning_tokens",
    "cached_input_tokens",
    "estimated_cost_usd",
)
_BATCH_COLUMNS = [
    "experiment_id",
    "batch_index",
    "artifact_available",
    "requested_count",
    "outcome",
    "error_type",
    "parse_error",
    "finish_reason",
    "elapsed_ms",
    *_USAGE,
]
_CANDIDATE_COLUMNS = [
    "experiment_id",
    "batch_index",
    "position",
    "raw",
    "error",
    "target_violation",
    "accepted",
    "persistence_error",
    "outcome",
    "workload_position",
    "fingerprint",
]


def _validate(experiment: Experiment) -> None:
    if experiment.script_path is None or Path(experiment.script_path).name != "generate.py":
        raise ValueError(f"{experiment.id}: expected an experiment using generate.py")


def _manifest(experiment: Experiment) -> dict | None:
    manifest = experiment.load_artifact("manifest.json")
    if manifest is not None and manifest.get("format_version") != 1:
        raise ValueError(f"{experiment.id}: unsupported generation manifest format")
    return manifest


def generation_batches_table(experiment: Experiment) -> pd.DataFrame:
    """One row per saved or manifest-listed batch, including missing batch artifacts.

    Supports both nested batch paths and Yanex's legacy flattened filenames.
    Missing manifests do not prevent discovery of already-written batch files.
    """
    _validate(experiment)
    manifest = _manifest(experiment)
    files = experiment.list_artifacts()
    names = list((manifest or {}).get("batches", []))
    known = {Path(name).name for name in names}
    names.extend(
        name
        for name in files
        if Path(name).stem.isdigit()
        and Path(name).suffix == ".json"
        and Path(name).name not in known
    )
    rows = []
    for name in sorted(names):
        record = experiment.load_artifact(name)
        if record is None and Path(name).name != name:
            record = experiment.load_artifact(Path(name).name)
        row = dict(
            experiment_id=experiment.id,
            batch_index=int(Path(name).stem),
            artifact_available=record is not None,
            outcome="missing_artifact",
        )
        if record is not None:
            response = record.get("response") or {}
            outcome = (
                "model_call_failed"
                if record.get("error_type")
                else "batch_parse_failed"
                if record.get("parse_error")
                else "decoded"
            )
            row.update(
                batch_index=record["batch_index"],
                requested_count=record["requested_count"],
                outcome=outcome,
                error_type=record.get("error_type"),
                parse_error=record.get("parse_error"),
                finish_reason=response.get("finish_reason"),
                elapsed_ms=response.get("elapsed_ms"),
            )
            row.update({field: response.get(field) for field in _USAGE})
        rows.append(row)
    table = pd.DataFrame(rows, columns=_BATCH_COLUMNS)
    table.attrs["manifest_available"] = manifest is not None
    return table


def generation_candidates_table(experiment: Experiment) -> pd.DataFrame:
    """One row per decoded candidate, retaining errors and accepted query fingerprints.

    No candidates are invented for undecodable batches. Missing candidate artifacts
    return an empty table with attrs['artifact_available'] false. Missing workload
    or mapping artifacts leave fingerprints unavailable; corrupt mappings raise.
    """
    _validate(experiment)
    _manifest(experiment)
    records = experiment.load_artifact("candidates.jsonl")
    if isinstance(records, str):
        records = [json.loads(line) for line in records.splitlines() if line.strip()]
    workload = experiment.load_artifact("workload.jsonl", loader=Workload.load)
    mapping = experiment.load_artifact("workload_mapping.json")
    mapped = {}
    if workload is not None and mapping is not None:
        entries = list(workload)
        if len(mapping) != len(entries):
            raise ValueError(f"{experiment.id}: workload/mapping length mismatch")
        positions = set()
        for item in mapping:
            key = (item["batch_index"], item["position"])
            position = item["workload_position"]
            if key in mapped or position in positions or not 0 <= position < len(entries):
                raise ValueError(f"{experiment.id}: invalid workload mapping")
            positions.add(position)
            mapped[key] = (position, entries[position].query.fingerprint())
    rows = []
    for record in records or []:
        outcome = (
            "parse_failed"
            if record.get("error")
            else "target_violation"
            if record.get("target_violation")
            else "persistence_failed"
            if record.get("persistence_error")
            else "accepted"
            if record.get("accepted")
            else "unknown"
        )
        position, fingerprint = mapped.get(
            (record["batch_index"], record["position"]), (None, None)
        )
        rows.append(
            dict(
                record,
                experiment_id=experiment.id,
                outcome=outcome,
                workload_position=position,
                fingerprint=fingerprint,
            )
        )
    table = pd.DataFrame(rows, columns=_CANDIDATE_COLUMNS)
    table.attrs["artifact_available"] = records is not None
    return table


def _ratio(numerator, denominator):
    return numerator / denominator if numerator is not None and denominator else None


def summarize_generation_run(experiment: Experiment) -> dict:
    """Summarize one run without excluding failed runs or filling missing metrics with zero.

    Recorded metrics use the latest logged step, falling back to checkpoint metrics
    only when no metrics were logged. Yields are fractions, not percentages.
    """
    _validate(experiment)
    params = experiment.get_params()
    model = params.get("model", {})
    manifest = _manifest(experiment)
    history = experiment.get_metrics(as_dataframe=False)
    metrics = history[-1] if history else (manifest or {}).get("metrics", {})
    row = {
        key: value
        for key, value in metrics.items()
        if key not in {"step", "timestamp", "last_updated"}
    }
    schema = experiment.load_artifact("schema.txt")
    row.update(
        experiment_id=experiment.id,
        name=experiment.name,
        status=experiment.status,
        manifest_status=(manifest or {}).get("status"),
        metrics_source="logged" if history else "manifest" if manifest else None,
        prompt_id=params.get("prompt_id"),
        model=model.get("name"),
        num_queries=params.get("num_queries"),
        batch_size=params.get("batch_size"),
        target_collection=params.get("target_collection"),
        examples_per_type=params.get("examples_per_type"),
        relationship_hints=params.get("relationship_hints"),
        system_instructions=model.get("system_instructions"),
        model_parameters=model.get("parameters", {}),
        reasoning_effort=model.get("parameters", {}).get("reasoning_effort"),
        schema_sha256=hashlib.sha256(schema.encode()).hexdigest() if schema is not None else None,
    )
    candidates = generation_candidates_table(experiment)
    accepted = candidates[candidates.accepted.eq(True)]
    complete = (
        candidates.attrs["artifact_available"]
        and len(accepted) == metrics.get("queries_accepted")
        and accepted.fingerprint.notna().all()
    )
    unique = accepted.fingerprint.nunique() if complete else None
    row.update(
        unique_queries=unique,
        exact_duplicate_queries=len(accepted) - unique if complete else None,
        accepted_yield=_ratio(metrics.get("queries_accepted"), params.get("num_queries")),
        distinct_yield=_ratio(unique, params.get("num_queries")),
        model_seconds=_ratio(metrics.get("model_elapsed_ms"), 1000),
        seconds_per_accepted=_ratio(
            metrics.get("model_elapsed_ms"), (metrics.get("queries_accepted") or 0) * 1000
        ),
    )
    for field in _USAGE:
        row[f"{field}_per_accepted"] = _ratio(metrics.get(field), metrics.get("queries_accepted"))
    batches = generation_batches_table(experiment)
    row["undecodable_batch_slots"] = (
        batches.loc[batches.outcome.eq("batch_parse_failed"), "requested_count"].sum()
        if manifest is not None
        and batches.artifact_available.all()
        and len(batches) == metrics.get("batches_attempted")
        else None
    )
    return row


def generation_runs_table(experiments: Sequence[Experiment]) -> pd.DataFrame:
    """Stack summaries in input order, retaining failed runs and repeated selections."""
    rows = [summarize_generation_run(experiment) for experiment in experiments]
    return pd.DataFrame(rows) if rows else pd.DataFrame(columns=["experiment_id", "name", "status"])


# Deliberately narrow: FailedToParse and an unrecognized aggregation stage.
# BadValue (2), for example, is too broad to label as syntax without more evidence.
_SYNTAX_CODES = {9, 40324}
_EXECUTION_COLUMNS = [
    "workload_position",
    "pattern_id",
    "database",
    "collection",
    "query_kind",
    "outcome",
    "elapsed_ms",
    "row_count",
    "error_type",
    "error_code",
    "error_code_name",
    "error_message",
    "warnings",
]


def _execution_table(workload, results, *, planning):
    _validate_mongo_workload(workload)
    if len(workload) != len(results):
        raise ValueError("Expected exactly one result per workload entry, in workload order")
    rows = []
    for position, (entry, result) in enumerate(zip(workload, results, strict=True)):
        if not isinstance(result, ExecutionResult):
            raise TypeError("results must contain native BONDI ExecutionResult objects")
        error = result.error
        details = error.details if isinstance(error, OperationFailure) and error.details else {}
        code = error.code if isinstance(error, OperationFailure) else None
        if result.status == "timeout":
            outcome = "timeout"
        elif error is not None:
            outcome = (
                ("syntax_error" if code in _SYNTAX_CODES else "other_error")
                if planning
                else "error"
            )
        elif planning:
            outcome = "passed"
        else:
            if type(result.row_count) is not int or result.row_count not in (0, 1):
                raise ValueError("Successful existence results must have row_count 0 or 1")
            outcome = "empty" if result.row_count == 0 else "nonempty"
        query = entry.query
        rows.append(
            dict(
                workload_position=position,
                pattern_id=entry.pattern_id,
                database=query.target.database,
                collection=query.target.collection,
                query_kind="find" if isinstance(query, MongoFindQuery) else "aggregate",
                outcome=outcome,
                elapsed_ms=result.elapsed_ms,
                row_count=result.row_count,
                error_type=type(error).__name__ if error is not None else None,
                error_code=code,
                error_code_name=details.get("codeName"),
                error_message=str(error) if error is not None else None,
                warnings=result.warnings,
            )
        )
    return pd.DataFrame(rows, columns=_EXECUTION_COLUMNS)


def execution_planning_table(
    workload: Workload, results: Sequence[ExecutionResult]
) -> pd.DataFrame:
    """Classify planning-only explain results in original workload order.

    Outcomes: passed, syntax_error (explicit recognized codes only), other_error,
    timeout. Passing does not prove runtime validity. Length mismatches raise.
    Original result objects and their backend diagnostic data remain unchanged.
    """
    return _execution_table(workload, results, planning=True)


def execution_existence_table(
    workload: Workload, results: Sequence[ExecutionResult]
) -> pd.DataFrame:
    """Classify results of a limit-one probe: empty, nonempty, error or timeout.

    Pass the original workload for identity and ordered results from its existence
    workload. Successful results must report exactly 0 or 1 rows; absent/invalid
    counts raise instead of being mistaken for empty. A nonempty result does not
    prove full-query completion. Error/timeout results never count as empty.
    """
    return _execution_table(workload, results, planning=False)
