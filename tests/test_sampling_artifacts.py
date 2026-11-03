"""Native sampling and generation artifact contracts."""

import json
from dataclasses import replace
from types import SimpleNamespace

import pytest
from bondi.workload import Workload
from bson import ObjectId, json_util

from json_storm.artifacts import GenerationArtifacts, save_bson_jsonl
from json_storm.generation import GeneratedBatch
from json_storm.models import ModelResponse
from json_storm.parsing import parse_batch
from json_storm.sampling import collection_targets, sample_schemas


@pytest.mark.parametrize("names", [[], "db.x", ["x"], ["a.x", "b.y"], ["a.x", "a.x"]])
def test_invalid_namespaces(names):
    with pytest.raises(ValueError):
        collection_targets(names)


def test_native_sampling_and_dotted_collection():
    calls = []

    class Executor:
        def run(self, query, **kwargs):
            calls.append((query, kwargs))
            return SimpleNamespace(documents=[{"_id": ObjectId(), "value": 1}])

    schemas, records = sample_schemas(Executor(), ["db.a.b", "db.users"], sample_size=3)
    assert list(schemas) == ["a.b", "users"]
    assert calls[0][0].target.collection == "a.b"
    assert calls[0][0].pipeline == [{"$sample": {"size": 3}}]
    assert calls[0][1] == {"collect_results": True}
    assert records[0]["namespace"] == "db.a.b"
    assert schemas["users"].value_mode == "none"


def test_empty_sample_is_explicit_failure():
    executor = SimpleNamespace(run=lambda *a, **k: SimpleNamespace(documents=[]))
    with pytest.raises(ValueError, match="No sample"):
        sample_schemas(executor, ["db.users"])


def test_bson_sample_roundtrip(tmp_path):
    rows = [{"namespace": "db.x", "document": {"_id": ObjectId()}}]
    path = tmp_path / "sample.jsonl"
    save_bson_jsonl(rows, path)
    assert [json_util.loads(line) for line in path.read_text().splitlines()] == rows


def model_response(text):
    return ModelResponse(
        text=text,
        requested_model="fake",
        returned_model="fake",
        response_id="id",
        finish_reason="stop",
        elapsed_ms=1,
        parameters={},
        usage=None,
        input_tokens=None,
        output_tokens=None,
        total_tokens=None,
        reasoning_tokens=None,
        cached_input_tokens=None,
        estimated_cost_usd=None,
        cost_status="unavailable",
        billing_mode="provider",
    )


def test_artifacts_native_workload_mapping_metrics_and_failures(tmp_path):
    saved = {}

    def save(obj, name, saver=None):
        saved[name] = obj
        if saver:
            saver(obj, tmp_path / name)

    writer = GenerationArtifacts(save)
    writer.checkpoint("running")
    assert len(Workload.load(tmp_path / "workload.jsonl")) == 0
    text = (
        '{"queries":[{"collection":"users","filter":{}},null,{"collection":"posts","filter":{}}]}'
    )
    parsed = parse_batch(
        text,
        batch_index=0,
        query_kind="find",
        database="db",
        collections=["users", "posts"],
        expected_count=2,
    )
    writer.add(GeneratedBatch(0, 2, "prompt", model_response(text), parsed, (2,)))
    writer.checkpoint("running")
    assert len(Workload.load(tmp_path / "workload.jsonl")) == 1
    assert saved["workload_mapping.json"] == [
        {"workload_position": 0, "batch_index": 0, "position": 0}
    ]
    assert writer.metrics["queries_parsed"] == 2
    assert writer.metrics["queries_parse_failed"] == 1
    assert writer.metrics["queries_target_violations"] == 1
    assert writer.metrics["queries_accepted"] == 1
    assert "input_tokens" not in writer.metrics
    writer.add(GeneratedBatch(1, 2, "prompt", error=RuntimeError("secret error text")))
    writer.checkpoint("failed")
    assert saved["manifest.json"]["status"] == "failed"
    assert writer.metrics["model_calls_failed"] == 1
    assert "secret" not in json.dumps(saved["batches/000001.json"])


def test_unreadable_batch_not_counted_as_zero_returned_queries():
    writer = GenerationArtifacts(lambda *a, **k: None)
    text = "bad"
    parsed = parse_batch(
        text,
        batch_index=0,
        query_kind="find",
        database="db",
        collections=["users"],
        expected_count=2,
    )
    response = replace(model_response(text), input_tokens=10)
    writer.add(GeneratedBatch(0, 2, "prompt", response, parsed))
    assert writer.metrics["batches_parse_failed"] == 1
    assert writer.metrics["batches_count_mismatch"] == 0
    assert writer.metrics["input_tokens"] == 10
    assert writer.metrics["input_tokens_reported_calls"] == 1


@pytest.mark.parametrize(
    "kind,entry",
    [
        (
            "find",
            {
                "collection": "posts",
                "filter": {"$or": [{"title": {"$exists": True}}, {"body": {"$regex": "^[^\\s]"}}]},
            },
        ),
        ("aggregate", {"collection": "posts", "pipeline": [{"$match": {"body": {"$regex": "a"}}}]}),
    ],
)
def test_regex_persistence_failure_preserves_raw_and_valid_siblings(tmp_path, kind, entry):
    saved = {}

    def save(obj, name, saver=None):
        saved[name] = obj
        if saver:
            saver(obj, tmp_path / name)

    good = (
        {"collection": "posts", "filter": {}}
        if kind == "find"
        else {"collection": "posts", "pipeline": []}
    )
    text = json.dumps({"queries": [good, entry, good]})
    parsed = parse_batch(
        text,
        batch_index=0,
        query_kind=kind,
        database="mathexchange",
        collections=["posts"],
        expected_count=3,
    )
    # Direct native callers can still supply ambiguous dictionaries; retain the guard.
    if kind == "find":
        parsed.candidates[1].query.filter = entry["filter"]
    else:
        parsed.candidates[1].query.pipeline = entry["pipeline"]
    writer = GenerationArtifacts(save)
    writer.add(GeneratedBatch(0, 3, "prompt", model_response(text), parsed))
    writer.checkpoint("completed")
    assert len(Workload.load(tmp_path / "workload.jsonl")) == 2
    assert writer.metrics["queries_parsed"] == 3
    assert writer.metrics["queries_parse_failed"] == 0
    assert writer.metrics["queries_persistence_failed"] == 1
    assert writer.metrics["queries_accepted"] == 2
    rejected = saved["candidates.jsonl"][1]
    assert rejected["raw"] == entry and rejected["error"] is None
    assert rejected["persistence_error"]["type"] == "ValueError"
    assert [row["position"] for row in saved["workload_mapping.json"]] == [0, 2]


def test_failure_checkpoint_does_not_mask_original_error(monkeypatch):
    import runpy
    from pathlib import Path

    script = runpy.run_path(str(Path(__file__).parents[1] / "experiments/generate.py"))
    main = script["main"]
    original = RuntimeError("original generation failure")

    class Recorder:
        metrics = {}

        def __init__(self, save):
            pass

        def checkpoint(self, status):
            if status == "failed":
                raise OSError("checkpoint failure")

    def fail(*args, **kwargs):
        raise original

    monkeypatch.setitem(main.__globals__, "GenerationArtifacts", Recorder)
    monkeypatch.setitem(main.__globals__, "generate_queries", fail)
    monkeypatch.setitem(main.__globals__, "validate_schema_artifact", lambda *args: "db")
    monkeypatch.setitem(main.__globals__, "render_schema_catalog", lambda *args, **kwargs: "schema")
    monkeypatch.setattr(
        main.__globals__["yanex"], "assert_dependency", lambda *args, **kwargs: None
    )
    monkeypatch.setattr(
        main.__globals__["yanex"],
        "get_dependency",
        lambda *args: SimpleNamespace(status="completed"),
    )
    monkeypatch.setattr(main.__globals__["yanex"], "load_artifact", lambda *args: {})
    monkeypatch.setattr(main.__globals__["yanex"], "save_artifact", lambda *args, **kwargs: None)
    monkeypatch.setitem(main.__globals__, "load_credentials", lambda path: None)
    monkeypatch.setattr(
        main.__globals__["yanex"],
        "get_param",
        lambda key, default=None: {"name": "fake/model"} if key == "model" else default,
    )
    monkeypatch.setattr(main.__globals__["yanex"], "log_metrics", lambda metrics: None)
    with pytest.raises(RuntimeError) as caught:
        main()
    assert caught.value is original
    assert "Failure checkpoint also failed: OSError" in original.__notes__


def test_schema_snapshot_pickle_and_validation():
    import pickle
    from importlib.metadata import version

    from bondi.schema import Schema

    from json_storm.sampling import validate_schema_artifact
    from json_storm.schema import render_schema_catalog

    schemas = {
        "posts": Schema.from_documents([{"nested": {"x": 1}, "tags": ["a"]}], values="distinct")
    }
    manifest = {
        "format_version": 1,
        "status": "completed",
        "bondi_version": version("bondi"),
        "database": "db",
        "namespaces": ["db.posts"],
        "collections": ["posts"],
    }
    restored = pickle.loads(pickle.dumps(schemas))
    assert validate_schema_artifact(restored, manifest) == "db"
    assert render_schema_catalog(restored, examples_per_type=2) == render_schema_catalog(
        schemas, examples_per_type=2
    )
    for changes in [
        {"status": "failed"},
        {"bondi_version": "wrong"},
        {"collections": ["other"]},
        {"database": "other"},
        {"format_version": 2},
    ]:
        with pytest.raises(ValueError):
            validate_schema_artifact(restored, {**manifest, **changes})
    with pytest.raises(ValueError):
        validate_schema_artifact(None, manifest)


def test_generation_requires_schema_dependency_before_model_access(monkeypatch):
    import runpy
    from pathlib import Path

    main = runpy.run_path(str(Path(__file__).parents[1] / "experiments/generate.py"))["main"]

    def missing(*args, **kwargs):
        assert kwargs["slot"] == "schema"
        raise ValueError("missing schema dependency")

    monkeypatch.setattr(main.__globals__["yanex"], "assert_dependency", missing)
    monkeypatch.setitem(main.__globals__, "load_credentials", lambda path: None)
    monkeypatch.setitem(
        main.__globals__, "LiteLLMModel", lambda *args, **kwargs: pytest.fail("model accessed")
    )
    with pytest.raises(ValueError, match="missing schema"):
        main()
