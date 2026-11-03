"""Generation artifact records; Yanex owns storage and format dispatch."""

from collections.abc import Callable
from dataclasses import asdict
from importlib.metadata import version
from pathlib import Path

from bondi.workload import Workload, WorkloadEntry
from bson import json_util

from json_storm.generation import GeneratedBatch


def save_bson_jsonl(records: list[dict], path: Path) -> None:
    """Custom Yanex saver retaining BSON values in sampled documents."""
    with Path(path).open("w") as stream:
        for record in records:
            stream.write(
                json_util.dumps(record, json_options=json_util.CANONICAL_JSON_OPTIONS) + "\n"
            )


class GenerationArtifacts:
    """Checkpoint batch observations through a supplied Yanex save_artifact function.

    Batch files are written first. Each checkpoint then replaces cumulative
    candidates, mapping, workload, and manifest; a process crash can interrupt
    these writes, so only a completed manifest denotes finalized artifacts.
    Error messages are omitted to avoid persisting provider credential-bearing text.
    """

    def __init__(self, save_artifact: Callable):
        self.save = save_artifact
        self.entries = []
        self.mapping = []
        self.candidates = []
        self.metrics = dict(
            batches_attempted=0,
            model_calls_failed=0,
            batches_parse_failed=0,
            batches_count_mismatch=0,
            queries_returned=0,
            queries_parsed=0,
            queries_parse_failed=0,
            queries_target_violations=0,
            queries_accepted=0,
            queries_persistence_failed=0,
        )

    def add(self, batch: GeneratedBatch) -> None:
        """Save one batch and update cumulative metrics and accepted native queries."""
        self.metrics["batches_attempted"] += 1
        record = {
            "batch_index": batch.batch_index,
            "requested_count": batch.requested_count,
            "prompt": batch.prompt,
            "response": asdict(batch.response) if batch.response else None,
            "error_type": type(batch.error).__name__ if batch.error else None,
            "parse_error": asdict(batch.parsed.error)
            if batch.parsed and batch.parsed.error
            else None,
            "target_violations": list(batch.target_violations),
        }
        self.save(record, f"batches/{batch.batch_index:06d}.json")
        if batch.error is not None:
            self.metrics["model_calls_failed"] += 1
        if batch.response is not None:
            response = batch.response
            self.metrics["model_elapsed_ms"] = (
                self.metrics.get("model_elapsed_ms", 0) + response.elapsed_ms
            )
            for field in (
                "input_tokens",
                "output_tokens",
                "total_tokens",
                "reasoning_tokens",
                "cached_input_tokens",
                "estimated_cost_usd",
            ):
                value = getattr(response, field)
                if value is not None:
                    self.metrics[field] = self.metrics.get(field, 0) + value
                    coverage = f"{field}_reported_calls"
                    self.metrics[coverage] = self.metrics.get(coverage, 0) + 1
        if batch.parsed is not None:
            parsed = batch.parsed
            self.metrics["batches_parse_failed"] += int(parsed.error is not None)
            self.metrics["batches_count_mismatch"] += int(parsed.count_matches is False)
            for candidate in parsed.candidates:
                self.metrics["queries_returned"] += 1
                valid = candidate.query is not None
                violation = candidate.position in batch.target_violations
                self.metrics["queries_parsed"] += int(valid)
                self.metrics["queries_parse_failed"] += int(not valid)
                self.metrics["queries_target_violations"] += int(violation)
                persistence_error = None
                if valid and not violation:
                    try:
                        candidate.query.to_json()
                    except (TypeError, ValueError, OverflowError) as error:
                        persistence_error = {"type": type(error).__name__, "message": str(error)}
                        self.metrics["queries_persistence_failed"] += 1
                accepted = valid and not violation and persistence_error is None
                self.candidates.append(
                    {
                        "batch_index": batch.batch_index,
                        "position": candidate.position,
                        "raw": candidate.raw,
                        "error": asdict(candidate.error) if candidate.error else None,
                        "target_violation": violation,
                        "accepted": accepted,
                        "persistence_error": persistence_error,
                    }
                )
                if accepted:
                    self.mapping.append(
                        {
                            "workload_position": len(self.entries),
                            "batch_index": batch.batch_index,
                            "position": candidate.position,
                        }
                    )
                    self.entries.append(WorkloadEntry(candidate.query))
                    self.metrics["queries_accepted"] += 1

    def checkpoint(self, status: str) -> None:
        """Save current native workload and manifest, including the empty case."""
        self.save(self.candidates, "candidates.jsonl")
        self.save(self.mapping, "workload_mapping.json")
        self.save(Workload(self.entries), "workload.jsonl", saver=lambda obj, path: obj.save(path))
        self.save(
            {
                "format_version": 1,
                "status": status,
                "metrics": self.metrics.copy(),
                "versions": {name: version(name) for name in ("bondi", "yanex", "litellm")},
                "workload": "workload.jsonl",
                "mapping": "workload_mapping.json",
                "batches": [
                    f"batches/{i:06d}.json" for i in range(self.metrics["batches_attempted"])
                ],
            },
            "manifest.json",
        )
