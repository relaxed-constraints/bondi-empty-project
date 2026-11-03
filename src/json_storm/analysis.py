"""Read-only generation analysis using native Yanex experiments and BONDI workloads."""

import hashlib
import json
from collections.abc import Sequence
from pathlib import Path

import pandas as pd
from bondi.workload import Workload
from yanex.results import Experiment

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


def batch_table(experiment: Experiment) -> pd.DataFrame:
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


def candidate_table(experiment: Experiment) -> pd.DataFrame:
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


def summarize_run(experiment: Experiment) -> dict:
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
    candidates = candidate_table(experiment)
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
    batches = batch_table(experiment)
    row["undecodable_batch_slots"] = (
        batches.loc[batches.outcome.eq("batch_parse_failed"), "requested_count"].sum()
        if manifest is not None
        and batches.artifact_available.all()
        and len(batches) == metrics.get("batches_attempted")
        else None
    )
    return row


def runs_table(experiments: Sequence[Experiment]) -> pd.DataFrame:
    """Stack summaries in input order, retaining failed runs and repeated selections."""
    rows = [summarize_run(experiment) for experiment in experiments]
    return pd.DataFrame(rows) if rows else pd.DataFrame(columns=["experiment_id", "name", "status"])
