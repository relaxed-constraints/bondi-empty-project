import pickle
import runpy
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from bondi.execution import ExecutionResult
from bondi.mongodb import MongoCollectionRef, MongoFindQuery
from bondi.workload import Workload, WorkloadEntry
from pymongo.errors import OperationFailure

SCRIPT = Path(__file__).resolve().parents[1] / "experiments" / "execute.py"


@pytest.fixture
def harness(monkeypatch):
    import yanex
    from bondi.mongodb import MongoExecutor

    workload = Workload([WorkloadEntry(MongoFindQuery(MongoCollectionRef("db", "posts"), {}))])
    saved, metrics = {}, {}
    dependency_check = MagicMock()
    monkeypatch.setattr(yanex, "assert_dependency", dependency_check)
    monkeypatch.setattr(yanex, "get_dependency", lambda slot: SimpleNamespace(id="generation-id"))
    loader = MagicMock(return_value=workload)
    monkeypatch.setattr(yanex, "load_artifact", loader)
    monkeypatch.setattr(yanex, "get_param", lambda key, default: default)
    monkeypatch.setattr(
        yanex, "save_artifact", lambda obj, name: saved.update({name: deepcopy(obj)})
    )
    monkeypatch.setattr(yanex, "log_metrics", lambda values, step: metrics.update(values))
    executor = MagicMock()
    executor.__enter__.return_value = executor
    executor.explain_workload.return_value = [ExecutionResult(1, raw={"queryPlanner": {}})]
    executor.run_workload.return_value = [ExecutionResult(2, row_count=0)]
    connect = MagicMock(return_value=executor)
    monkeypatch.setattr(MongoExecutor, "from_uri", connect)
    return SimpleNamespace(
        saved=saved,
        metrics=metrics,
        executor=executor,
        workload=workload,
        loader=loader,
        connect=connect,
        dependency_check=dependency_check,
    )


def test_full_workflow(harness):
    h = harness
    runpy.run_path(str(SCRIPT), run_name="__main__")
    h.dependency_check.assert_called_once_with("generate.py", slot="generate")
    assert h.loader.call_args.kwargs["loader"] == Workload.load
    assert h.connect.call_args.kwargs["continue_on_error"] is True
    assert h.workload[0].query.limit is None
    assert h.executor.run_workload.call_args.args[0][0].query.limit == 1
    assert h.metrics == dict(
        planning_passed=1,
        planning_syntax_error=0,
        planning_other_error=0,
        planning_timeout=0,
        existence_empty=1,
        existence_nonempty=0,
        existence_error=0,
        existence_timeout=0,
    )
    assert h.saved["execution_manifest.json"]["status"] == "completed"
    assert h.saved["planning_results.pkl"][0].raw == {"queryPlanner": {}}


def test_failure_retains_planning(harness):
    h = harness
    h.executor.run_workload.side_effect = RuntimeError("broken")
    with pytest.raises(RuntimeError, match="broken"):
        runpy.run_path(str(SCRIPT), run_name="__main__")
    assert "planning.csv" in h.saved
    assert h.metrics["planning_passed"] == 1
    assert "existence_empty" not in h.metrics
    assert h.saved["execution_manifest.json"]["status"] == "failed"
    assert h.saved["execution_manifest.json"]["completed_phases"] == ["planning"]


def test_native_error_pickle_roundtrip():
    error = OperationFailure("bad", 9, {"codeName": "FailedToParse", "code": 9})
    results = [ExecutionResult(1, error=error, raw={"evidence": True})]
    restored = pickle.loads(pickle.dumps(results))
    assert restored[0].error.code == 9
    assert restored[0].error.details == error.details
    assert restored[0].raw == results[0].raw


def test_missing_workload(harness):
    harness.loader.return_value = None
    with pytest.raises(ValueError, match="workload.jsonl"):
        runpy.run_path(str(SCRIPT), run_name="__main__")
    harness.connect.assert_not_called()
