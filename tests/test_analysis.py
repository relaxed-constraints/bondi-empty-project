"""Small native Yanex Experiment fixtures, with isolated storage."""

from unittest.mock import MagicMock

import pytest
from bondi.mongodb import MongoCollectionRef, MongoFindQuery
from bondi.workload import Workload, WorkloadEntry
from yanex.results import Experiment

from json_storm.analysis import (
    generation_batches_table,
    generation_candidates_table,
    generation_runs_table,
    summarize_generation_run,
)


@pytest.fixture
def run():
    manager = MagicMock()
    manager.storage.load_metadata.return_value = {
        "script_path": "/project/experiments/generate.py",
        "status": "failed",
        "name": "test",
    }
    exp = Experiment("test1234", manager=manager)
    exp.get_params = lambda: {"num_queries": 4, "batch_size": 2, "model": {"name": "test"}}
    exp.get_metrics = lambda **kwargs: []
    query = MongoFindQuery(MongoCollectionRef("db", "posts"), {})
    artifacts = {
        "manifest.json": {
            "format_version": 1,
            "status": "failed",
            "metrics": {"queries_accepted": 2, "batches_attempted": 2},
            "batches": ["batches/000000.json", "batches/000001.json"],
        },
        "000000.json": {
            "batch_index": 0,
            "requested_count": 2,
            "response": {"finish_reason": "stop", "output_tokens": 10},
        },
        "000001.json": {
            "batch_index": 1,
            "requested_count": 2,
            "parse_error": {"status": "invalid_json", "message": "bad JSON"},
        },
        "candidates.jsonl": [{"batch_index": 0, "position": i, "accepted": True} for i in range(2)],
        "workload.jsonl": Workload([WorkloadEntry(query), WorkloadEntry(query)]),
        "workload_mapping.json": [
            {"batch_index": 0, "position": i, "workload_position": i} for i in range(2)
        ],
        "schema.txt": "posts: object",
    }
    exp.load_artifact = lambda name, loader=None: artifacts.get(name)
    exp.list_artifacts = lambda: list(artifacts)
    return exp, artifacts


def test_summary_duplicates_and_failed_batches(run):
    exp, _ = run
    row = summarize_generation_run(exp)
    assert row["status"] == "failed"
    assert row["accepted_yield"] == 0.5
    assert row["distinct_yield"] == 0.25
    assert row["unique_queries"] == 1
    assert row["exact_duplicate_queries"] == 1
    assert row["undecodable_batch_slots"] == 2
    assert row["output_tokens_per_accepted"] is None
    assert row["metrics_source"] == "manifest"
    assert generation_batches_table(exp).output_tokens.iloc[0] == 10
    assert generation_candidates_table(exp).fingerprint.nunique() == 1


def test_missing_not_zero(run):
    exp, artifacts = run
    artifacts.clear()
    row = summarize_generation_run(exp)
    assert row["accepted_yield"] is None
    assert row["unique_queries"] is None
    assert row["undecodable_batch_slots"] is None
    assert not generation_candidates_table(exp).attrs["artifact_available"]
    assert generation_batches_table(exp).empty


def test_missing_batch_and_mapping(run):
    exp, artifacts = run
    del artifacts["000001.json"]
    del artifacts["workload_mapping.json"]
    assert generation_batches_table(exp).outcome.tolist() == ["decoded", "missing_artifact"]
    assert summarize_generation_run(exp)["unique_queries"] is None
    assert summarize_generation_run(exp)["undecodable_batch_slots"] is None


def test_logged_latest_and_coverage(run):
    exp, _ = run
    exp.get_metrics = lambda **kwargs: [
        {"queries_accepted": 1},
        {"queries_accepted": 2, "output_tokens": 10, "output_tokens_reported_calls": 1},
    ]
    row = summarize_generation_run(exp)
    assert row["queries_accepted"] == 2
    assert row["output_tokens_reported_calls"] == 1
    assert row["output_tokens_per_accepted"] == 5
    assert row["metrics_source"] == "logged"


@pytest.mark.parametrize(
    "helper", [summarize_generation_run, generation_batches_table, generation_candidates_table]
)
@pytest.mark.parametrize("script", [None, "schema.py", "not_generate.py"])
def test_script_validation(run, helper, script):
    exp, _ = run
    exp._cached_metadata["script_path"] = script
    with pytest.raises(ValueError, match="generate.py"):
        helper(exp)


def test_candidates_keep_failures(run):
    exp, artifacts = run
    artifacts["candidates.jsonl"] += [
        {
            "batch_index": 2,
            "position": 0,
            "accepted": False,
            "persistence_error": {"message": "Regex serialization"},
        },
        {"batch_index": 2, "position": 1, "accepted": False, "error": {"status": "bad"}},
        {"batch_index": 2, "position": 2, "accepted": False, "target_violation": True},
    ]
    assert generation_candidates_table(exp).outcome.tolist()[-3:] == [
        "persistence_failed",
        "parse_failed",
        "target_violation",
    ]


def test_versions_mapping_and_selection(run):
    exp, artifacts = run
    assert generation_runs_table([exp, exp]).experiment_id.tolist() == ["test1234", "test1234"]
    assert generation_runs_table([]).empty
    artifacts["workload_mapping.json"][1]["workload_position"] = 0
    with pytest.raises(ValueError, match="mapping"):
        generation_candidates_table(exp)
    artifacts["manifest.json"]["format_version"] = 99
    with pytest.raises(ValueError, match="format"):
        generation_batches_table(exp)
