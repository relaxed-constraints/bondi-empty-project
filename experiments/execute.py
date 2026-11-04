"""Plan and probe a workload from a required generation dependency."""

import os
from importlib.metadata import version
from pathlib import Path

import yanex
from bondi.mongodb import MongoExecutor
from bondi.workload import Workload

from json_storm.analysis import execution_existence_table, execution_planning_table
from json_storm.execution import make_existence_workload
from json_storm.models import load_credentials


def main():
    root = Path(__file__).resolve().parents[1]
    if (root / ".env").is_file():
        load_credentials(root / ".env")

    yanex.assert_dependency("generate.py", slot="generate")
    workload = yanex.load_artifact("workload.jsonl", loader=Workload.load)
    if workload is None:
        raise ValueError("Generation dependency has no workload.jsonl artifact")
    # Reject unsupported write stages before opening a connection or issuing explains.
    probe = make_existence_workload(workload)
    manifest = {
        "format_version": 1,
        "generation_experiment_id": yanex.get_dependency("generate").id,
        "workload_size": len(workload),
        "versions": {name: version(name) for name in ("bondi", "yanex")},
        "status": "running",
        "completed_phases": [],
        "probe_strategy": "find limit=1; append aggregate $limit:1",
    }
    yanex.save_artifact(manifest, "execution_manifest.json")
    uri = os.environ.get("JSON_STORM_MONGODB_URI") or yanex.get_param(
        "mongodb.uri", "mongodb://localhost:27018"
    )
    try:
        with MongoExecutor.from_uri(
            uri,
            timeout_seconds=yanex.get_param("mongodb.timeout_seconds", 10),
            concurrency=yanex.get_param("mongodb.concurrency", 1),
            continue_on_error=True,
        ) as executor:
            for phase, operation, target, classify, outcomes in (
                (
                    "planning",
                    executor.explain_workload,
                    workload,
                    execution_planning_table,
                    ("passed", "syntax_error", "other_error", "timeout"),
                ),
                (
                    "existence",
                    executor.run_workload,
                    probe,
                    execution_existence_table,
                    ("empty", "nonempty", "error", "timeout"),
                ),
            ):
                results = operation(target)
                # Native objects retain raw explain documents, warnings and exceptions.
                yanex.save_artifact(results, f"{phase}_results.pkl")
                table = classify(workload, results)
                yanex.save_artifact(table, f"{phase}.csv")
                yanex.log_metrics(
                    {
                        f"{phase}_{outcome}": int(table.outcome.eq(outcome).sum())
                        for outcome in outcomes
                    },
                    step=0,
                )
                manifest["completed_phases"].append(phase)
                yanex.save_artifact(manifest, "execution_manifest.json")
                print(f"{phase}: {table.outcome.value_counts().to_dict()}", flush=True)
        manifest["status"] = "completed"
        yanex.save_artifact(manifest, "execution_manifest.json")
    except BaseException as original:
        manifest["status"] = "failed"
        try:
            yanex.save_artifact(manifest, "execution_manifest.json")
        except Exception as checkpoint_error:
            original.add_note(f"Failure checkpoint also failed: {type(checkpoint_error).__name__}")
        raise


if __name__ == "__main__":
    main()
