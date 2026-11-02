"""Offline contract tests against real BONDI query constructors."""

import json

import pytest
from bondi.mongodb import MongoAggregateQuery, MongoFindQuery
from bondi.workload import Workload, WorkloadEntry

from json_storm.parsing import parse_batch


def parse(response, **kwargs):
    options = dict(
        batch_index=0,
        query_kind="find",
        database="research",
        collections=["businesses", "reviews", "users"],
        expected_count=1,
    )
    options.update(kwargs)
    return parse_batch(response, **options)


def batch(*entries):
    return json.dumps({"queries": entries})


def find(collection="businesses", **kwargs):
    return {"collection": collection, "filter": {}, **kwargs}


def test_find_targets_and_workload_round_trip(tmp_path):
    result = parse(batch(find(), find("reviews"), find("users")), expected_count=3)
    assert result.error is None and result.count_matches
    queries = [candidate.query for candidate in result.candidates]
    assert all(isinstance(query, MongoFindQuery) for query in queries)
    assert [query.target.collection for query in queries] == ["businesses", "reviews", "users"]
    assert all(query.target.database == "research" for query in queries)
    path = tmp_path / "workload.jsonl"
    Workload([WorkloadEntry(query) for query in queries]).save(path)
    restored = Workload.load(path)
    assert len(restored) == 3


def test_aggregate_preserves_foreign_collection_pipeline():
    pipeline = [
        {
            "$lookup": {
                "from": "reviews",
                "localField": "_id",
                "foreignField": "business_id",
                "as": "reviews",
            }
        }
    ]
    result = parse(
        batch({"collection": "businesses", "pipeline": pipeline}), query_kind="aggregate"
    )
    query = result.candidates[0].query
    assert isinstance(query, MongoAggregateQuery)
    assert query.pipeline == pipeline


@pytest.mark.parametrize(
    "response",
    [
        '{"queries":',
        '```json\n{"queries": []}\n```',
        '{"queries": [], "queries": []}',
        '{"queries": [NaN]}',
        '{"queries": [Infinity]}',
        '{"queries":[{"collection":"users","filter":{"x":1,"x":2}}]}',
    ],
)
def test_invalid_json(response):
    result = parse(response)
    assert result.error.status == "invalid_json"
    assert result.raw_response == response
    assert result.actual_count is None and result.count_matches is None
    assert result.candidates == ()


@pytest.mark.parametrize("payload", [None, [], {}, {"queries": {}}, {"queries": [], "extra": 1}])
def test_invalid_envelope(payload):
    result = parse(json.dumps(payload))
    assert result.error.status == "invalid_query_shape"
    assert result.actual_count is None


@pytest.mark.parametrize(
    "entry",
    [
        None,
        [],
        {},
        find(collection="unknown"),
        find(collection=[]),
        find(filter="x > 4"),
        find(projection=[]),
        find(unrecognized_option=1),
        {"collection": "users", "pipeline": []},
    ],
)
def test_invalid_sibling_does_not_discard_valid_queries(entry):
    result = parse(batch(find(), entry, find("reviews")), expected_count=3)
    assert result.error is None and result.count_matches
    assert [c.position for c in result.candidates] == [0, 1, 2]
    assert all(c.batch_index == 0 for c in result.candidates)
    assert result.candidates[0].query is not None
    assert result.candidates[2].query is not None
    failed = result.candidates[1]
    assert failed.query is None and failed.raw == entry
    assert failed.error.status == "invalid_query_shape"


@pytest.mark.parametrize(
    "pipeline", [{"$match": {}}, [1], [{"match": {}}], [{"$match": {}, "$limit": 1}]]
)
def test_invalid_aggregate_shape(pipeline):
    result = parse(batch({"collection": "users", "pipeline": pipeline}), query_kind="aggregate")
    assert result.candidates[0].error.status == "invalid_query_shape"


@pytest.mark.parametrize("count", [0, 1, 3])
def test_count_mismatch_preserves_all_entries_and_duplicates(count):
    result = parse(batch(*[find()] * count), expected_count=2)
    assert result.actual_count == count and result.count_matches is False
    assert len(result.candidates) == count


def test_semantics_and_write_policy_are_not_parser_responsibilities():
    result = parse(batch(find(filter={"x": {"$madeUp": 1}})))
    assert result.candidates[0].error is None
    result = parse(
        batch({"collection": "users", "pipeline": [{"$out": "copy"}]}), query_kind="aggregate"
    )
    assert result.candidates[0].error is None


def test_plain_json_values_and_defensive_query_copy():
    entry = find(filter={"date": {"$date": "2026-01-01"}}, projection={"name": 1})
    candidate = parse(batch(entry)).candidates[0]
    assert candidate.query.filter == entry["filter"]
    candidate.raw["filter"].clear()
    assert candidate.query.filter == entry["filter"]


@pytest.mark.parametrize(
    "options",
    [
        {"expected_count": 0},
        {"expected_count": True},
        {"expected_count": 1.5},
        {"batch_index": -1},
        {"batch_index": True},
        {"batch_index": 1.0},
        {"batch_index": "0"},
        {"batch_index": None},
        {"query_kind": "sql"},
        {"collections": []},
        {"collections": "users"},
        {"collections": [""]},
        {"database": ""},
    ],
)
def test_bad_caller_configuration_raises(options):
    with pytest.raises((TypeError, ValueError)):
        parse("not json", **options)


@pytest.mark.parametrize("options", [{}, {"sort": [], "skip": 0, "limit": None}])
def test_find_option_defaults(options):
    query = parse(batch(find(**options))).candidates[0].query
    assert query.sort == ()
    assert query.skip == 0
    assert query.limit is None


def test_find_options_preserve_order_and_survive_persistence(tmp_path):
    candidate = parse(batch(find(sort=[["stars", -1], ["name", 1]], skip=10, limit=20))).candidates[
        0
    ]
    query = candidate.query
    assert query.sort == (("stars", -1), ("name", 1))
    assert query.skip == 10 and query.limit == 20
    candidate.raw["sort"][0][1] = 1
    assert query.sort[0] == ("stars", -1)
    path = tmp_path / "options.jsonl"
    Workload([WorkloadEntry(query)]).save(path)
    restored = Workload.load(path)
    assert next(iter(restored)).query.to_json() == query.to_json()


@pytest.mark.parametrize(
    "options",
    [
        {"sort": None},
        {"sort": {"stars": -1}},
        {"sort": ["ab"]},
        {"sort": [[]]},
        {"sort": [["stars"]]},
        {"sort": [["stars", 1, 2]]},
        {"sort": [["", 1]]},
        {"sort": [["a\0b", 1]]},
        {"sort": [[1, 1]]},
        {"sort": [["stars", 0]]},
        {"sort": [["stars", True]]},
        {"sort": [["stars", 1.0]]},
        {"sort": [["stars", "desc"]]},
        {"skip": -1},
        {"skip": True},
        {"skip": 1.5},
        {"skip": None},
        {"skip": "1"},
        {"limit": 0},
        {"limit": -1},
        {"limit": True},
        {"limit": 1.5},
        {"limit": "1"},
    ],
)
def test_invalid_find_options_only_reject_their_candidate(options):
    result = parse(batch(find(**options), find()), expected_count=2)
    assert result.error is None and result.count_matches
    assert result.candidates[0].error.status == "invalid_query_shape"
    assert result.candidates[1].query is not None


@pytest.mark.parametrize("option", [{"sort": []}, {"skip": 0}, {"limit": 1}])
def test_find_options_are_not_accepted_on_aggregate_entries(option):
    result = parse(batch({"collection": "users", "pipeline": [], **option}), query_kind="aggregate")
    assert result.candidates[0].error.status == "invalid_query_shape"


@pytest.mark.parametrize("batch_index", [0, 7])
def test_batch_index_is_preserved_on_batches_candidates_and_failures(batch_index):
    result = parse(batch(find(), None), batch_index=batch_index, expected_count=2)
    assert result.batch_index == batch_index
    assert [(c.batch_index, c.position) for c in result.candidates] == [
        (batch_index, 0),
        (batch_index, 1),
    ]
    for response in ["not json", "{}"]:
        failed = parse(response, batch_index=batch_index)
        assert failed.batch_index == batch_index
        assert failed.error is not None
