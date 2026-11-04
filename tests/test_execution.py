import pytest
from bondi.execution import ExecutionResult
from bondi.mongodb import MongoAggregateQuery, MongoCollectionRef, MongoFindQuery
from bondi.workload import Workload, WorkloadEntry
from bson import Regex
from pymongo.errors import ExecutionTimeout, OperationFailure

from json_storm.analysis import execution_existence_table, execution_planning_table
from json_storm.execution import make_existence_workload

TARGET = MongoCollectionRef("db", "posts")


def workload(query=None):
    return Workload([WorkloadEntry(query or MongoFindQuery(TARGET, {}), pattern_id=7)])


def test_find_copy_preserves_bson_projection_and_pagination():
    query = MongoFindQuery(
        TARGET, {"x": {"$gt": 1}}, projection={"x": Regex("a")}, sort=(("x", -1),), skip=3, limit=10
    )
    original = Workload([WorkloadEntry(query, 7), WorkloadEntry(query, 8)])
    probe = make_existence_workload(original)
    assert probe[0].query.limit == 1
    assert probe[0].query.skip == 3
    assert probe[0].query.sort == query.sort
    assert probe[0].query.projection == query.projection
    assert [e.pattern_id for e in probe] == [7, 8]
    probe[0].query.filter["x"]["$gt"] = 99
    assert query.filter["x"]["$gt"] == probe[1].query.filter["x"]["$gt"] == 1
    assert query.limit == 10


def test_aggregate_copy_preserves_existing_limit():
    query = MongoAggregateQuery(TARGET, [{"$limit": 10}, {"$skip": 2}])
    probe = make_existence_workload(workload(query))
    assert probe[0].query.pipeline == [{"$limit": 10}, {"$skip": 2}, {"$limit": 1}]
    assert query.pipeline == [{"$limit": 10}, {"$skip": 2}]


@pytest.mark.parametrize(
    "pipeline",
    [
        [{"$out": "other"}],
        [{"$merge": "other"}],
        [{"$facet": {"a": [{"$out": "other"}]}}],
        [{"$lookup": {"from": "other", "pipeline": [{"$merge": "other"}], "as": "x"}}],
        [{"$unionWith": {"coll": "other", "pipeline": [{"$out": "other"}]}}],
    ],
)
def test_write_stages_rejected(pipeline):
    with pytest.raises(ValueError, match="write stages"):
        make_existence_workload(workload(MongoAggregateQuery(TARGET, pipeline)))


def test_literal_out_key_not_a_write_stage():
    query = MongoAggregateQuery(TARGET, [{"$project": {"x": {"$literal": {"$out": "x"}}}}])
    assert len(make_existence_workload(workload(query))) == 1


@pytest.mark.parametrize(
    "error,outcome",
    [
        (None, "passed"),
        (OperationFailure("bad", 9, {"codeName": "FailedToParse"}), "syntax_error"),
        (OperationFailure("stage", 40324), "syntax_error"),
        (OperationFailure("bad value", 2), "other_error"),
        (OperationFailure("unauthorized", 13), "other_error"),
        (OperationFailure("unknown", 123456), "other_error"),
        (ExecutionTimeout("late", 50), "timeout"),
        (TimeoutError(), "timeout"),
    ],
)
def test_planning_classification(error, outcome):
    result = ExecutionResult(12, error=error)
    row = execution_planning_table(workload(), [result]).iloc[0]
    assert row.outcome == outcome
    assert row.pattern_id == 7
    assert row.collection == "posts"
    assert row.elapsed_ms == 12
    if isinstance(error, OperationFailure):
        assert row.error_code == error.code
        assert row.error_message == str(error)


@pytest.mark.parametrize("count,outcome", [(0, "empty"), (1, "nonempty")])
def test_existence(count, outcome):
    assert (
        execution_existence_table(workload(), [ExecutionResult(1, row_count=count)]).iloc[0].outcome
        == outcome
    )


@pytest.mark.parametrize("count", [None, -1, 2, True])
def test_invalid_success_count(count):
    with pytest.raises(ValueError, match="row_count"):
        execution_existence_table(workload(), [ExecutionResult(1, row_count=count)])


def test_timeout_and_errors_not_empty():
    for error, expected in [(TimeoutError(), "timeout"), (OperationFailure("bad", 9), "error")]:
        assert (
            execution_existence_table(workload(), [ExecutionResult(1, error=error)]).iloc[0].outcome
            == expected
        )


@pytest.mark.parametrize("helper", [execution_planning_table, execution_existence_table])
def test_alignment_empty_and_invalid_results(helper):
    assert helper(Workload([]), []).empty
    with pytest.raises(ValueError, match="one result"):
        helper(workload(), [])
    with pytest.raises(TypeError, match="ExecutionResult"):
        helper(workload(), [None])


def test_empty_probe():
    assert len(make_existence_workload(Workload([]))) == 0
