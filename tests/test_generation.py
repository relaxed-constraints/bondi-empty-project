"""Pipeline behavior using fake models and real rendering/parsing."""

from types import SimpleNamespace

import pytest
from bondi.schema import Schema

from json_storm.generation import generate_queries
from json_storm.prompts import PROMPTS


class FakeModel:
    def __init__(self, outputs):
        self.outputs = iter(outputs)
        self.prompts = []

    def generate(self, prompt):
        self.prompts.append(prompt)
        item = next(self.outputs)
        if isinstance(item, BaseException):
            raise item
        return item


def response(text):
    return SimpleNamespace(text=text, usage={"prompt_tokens": 10})


def generate(model, **kwargs):
    args = dict(database="research", num_queries=5, batch_size=2)
    args.update(kwargs)
    return generate_queries(
        model, PROMPTS["p3"], {"businesses": Schema(), "reviews": Schema()}, **args
    )


def test_lazy_independent_batches_and_partial_final_count():
    responses = [response('{"queries": []}') for _ in range(3)]
    model = FakeModel(responses)
    iterator = generate(model)
    assert model.prompts == []
    first = next(iterator)
    assert len(model.prompts) == 1
    records = [first, *iterator]
    assert [b.requested_count for b in records] == [2, 2, 1]
    assert [b.batch_index for b in records] == [0, 1, 2]
    for record, original in zip(records, responses):
        assert record.response is original
        assert record.parsed.count_matches is False
        assert f"Generate exactly {record.requested_count} queries." in record.prompt
    assert model.prompts[0] == model.prompts[1]


def test_model_failure_is_retained_then_stops():
    error = RuntimeError("unavailable")
    model = FakeModel([response('{"queries": []}'), error, response("unused")])
    records = list(generate(model))
    assert len(records) == 2 and len(model.prompts) == 2
    assert records[1].error is error
    assert records[1].response is None and records[1].parsed is None
    assert records[0].response is not None


def test_no_text_and_invalid_json_do_not_stop_later_batches():
    model = FakeModel([response(None), response("bad json"), response('{"queries": []}')])
    records = list(generate(model))
    assert records[0].response.text is None
    assert records[0].parsed.error.status == "invalid_json"
    assert records[1].parsed.error.status == "invalid_json"
    assert records[2].parsed.error is None


def test_target_violations_are_separate_from_parse_errors():
    model = FakeModel(
        [
            response(
                '{"queries":[{"collection":"reviews","filter":{}},'
                '{"collection":"businesses","filter":{}}, null]}'
            )
        ]
    )
    record = next(generate(model, num_queries=1, target_collection="businesses"))
    assert record.target_violations == (0,)
    assert record.parsed.candidates[0].query is not None
    assert record.parsed.candidates[2].error is not None
    assert record.parsed.actual_count == 3  # no truncation


@pytest.mark.parametrize(
    "kwargs",
    [
        {"num_queries": 0},
        {"batch_size": 0},
        {"num_queries": True},
        {"batch_size": 1.5},
        {"target_collection": "missing"},
        {"database": ""},
        {"relationship_hints": ""},
    ],
)
def test_configuration_rejected_before_iteration(kwargs):
    model = FakeModel([])
    with pytest.raises((ValueError, TypeError)):
        generate(model, **kwargs)
    assert model.prompts == []


def test_keyboard_interrupt_is_not_captured():
    with pytest.raises(KeyboardInterrupt):
        next(generate(FakeModel([KeyboardInterrupt()])))


def test_schema_snapshot_is_stable_after_creation():
    schema = Schema.from_documents([{"a": 1}])
    model = FakeModel([response('{"queries": []}')])
    records = generate_queries(
        model,
        PROMPTS["p4"],
        {"businesses": schema},
        database="research",
        num_queries=1,
        batch_size=8,
    )
    schema.update([{"later": 1}])
    record = next(records)
    assert "later" not in record.prompt
    assert record.requested_count == 1
