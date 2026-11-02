"""Schema descriptions retain structural meaning and are reproducible."""

import pytest
from bondi.schema import Schema

from json_storm.schema import render_schema_catalog


def test_nested_paths_arrays_missing_and_null():
    schema = Schema.from_documents(
        [
            {
                "address": {"city": "Sydney"},
                "reviews": [{"rating": 4}, {}],
                "tags": [],
                "stars": None,
            },
            {"address": {}, "reviews": [], "stars": 4.5},
            {},
        ]
    )
    text = render_schema_catalog({"businesses": schema})
    assert "Documents inspected: 3" in text
    assert "- address.city: string; missing in 1/2 parent objects" in text
    assert "- reviews[]: object\n" in text
    assert "- reviews[].rating: integer; missing in 1/2 parent objects" in text
    assert "- stars: float | null; missing in 1/3 parent objects" in text
    assert "- tags[]: unknown (no elements observed)" in text
    assert "examples {" not in text


def test_literal_names_do_not_collide_with_structural_paths():
    schema = Schema.from_documents(
        [
            {
                "address.city": 1,
                "address": {"city": 2},
                "items[]": 3,
                "items": [[1]],
                "": 4,
                'a"b\nc': 5,
            }
        ]
    )
    text = render_schema_catalog({"test": schema})
    for path in [
        '["address.city"]',
        "address.city",
        '["items[]"]',
        "items[][]",
        '[""]',
        '["a\\"b\\nc"]',
    ]:
        assert f"- {path}: integer" in text


def test_order_is_independent_of_document_field_and_collection_insertion():
    first = {"b": 1, "a": "z"}
    second = {"a": 2, "b": None}
    a = Schema.from_documents([first, second], values="distinct")
    b = Schema.from_documents([second, first], values="distinct")
    assert render_schema_catalog({"z": a, "a": b}, examples_per_type=2) == (
        render_schema_catalog({"a": a, "z": b}, examples_per_type=2)
    )


@pytest.mark.parametrize("mode", ["distinct", "full"])
def test_examples_are_bounded_per_type_and_do_not_change_schema(mode):
    schema = Schema.from_documents([{"x": x} for x in [3, 1, 2, "b", "a"]], values=mode)
    text = render_schema_catalog({"test": schema}, examples_per_type=2)
    assert "examples {integer: [1, 2]; string: ['a', 'b']}" in text
    assert schema["x"].types["int"].values == frozenset({1, 2, 3})
    assert "examples {" not in render_schema_catalog({"test": schema})


def test_empty_catalog_and_empty_collection():
    assert "No collections supplied." in render_schema_catalog({})
    assert "Documents inspected: 0\nFields:\n- No fields observed." in (
        render_schema_catalog({"empty": Schema()})
    )


def test_examples_require_retention():
    with pytest.raises(ValueError, match="not retained"):
        render_schema_catalog({"test": Schema()}, examples_per_type=1)


@pytest.mark.parametrize("count", [-1, True, 1.5, "1"])
def test_invalid_example_count(count):
    with pytest.raises(ValueError):
        render_schema_catalog({}, examples_per_type=count)


@pytest.mark.parametrize("schemas", [[], {1: Schema()}, {"x": {}}, {"": Schema()}])
def test_invalid_catalog(schemas):
    with pytest.raises((TypeError, ValueError)):
        render_schema_catalog(schemas)
