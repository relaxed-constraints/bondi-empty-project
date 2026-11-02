"""Prompt format, target selection, and parser interoperability."""

import json

import pytest
from bondi.schema import Schema

from json_storm.parsing import parse_batch
from json_storm.prompts import PROMPTS, PromptTemplate
from json_storm.schema import render_schema_catalog


@pytest.mark.parametrize("key", list(PROMPTS))
def test_registry_examples_parse_and_old_output_instructions_are_removed(key):
    template = PROMPTS[key]
    text = template.render("schema", num_queries=8, target_collection="businesses")
    example = text.splitlines()[-1]
    result = parse_batch(
        example,
        batch_index=0,
        query_kind=template.query_kind,
        database="research",
        collections=["businesses"],
        expected_count=1,
    )
    assert result.candidates[0].error is None
    assert "Generate exactly 8 queries." in text
    assert "Return only the aggregation pipeline" not in text
    assert "Return a JSON object with two keys" not in text
    assert template.query_kind == ("find" if key in {"p2", "p3", "p6"} else "aggregate")


def test_schema_and_hints_preserved_in_section_order_and_all_collections_retained():
    schema = render_schema_catalog({"businesses": Schema(), "reviews": Schema()})
    text = PROMPTS["p1"].render(
        schema,
        num_queries=4,
        target_collection="businesses",
        relationship_hints="reviews.business_id references businesses._id",
    )
    assert schema in text
    headings = [
        "Task\n",
        "Schema catalogue\n",
        "Relationship hints (caller supplied)\n",
        "Batch request\n",
        "Response format\n",
    ]
    assert [text.index(h) for h in headings] == sorted(text.index(h) for h in headings)
    assert 'Every query must use "businesses" as its starting collection.' in text
    assert 'Collection: "reviews"' in text
    assert "Do not use write stages such as $out or $merge" in text


def test_default_selection_and_repeatability():
    template = PromptTemplate("Explore predicates.", "find")
    text = template.render("schema", num_queries=1)
    assert text == template.render("schema", num_queries=1)
    assert "Choose each query's starting collection from the schema catalogue." in text
    assert "Relationship hints" not in text
    assert '"sort"' in text and '"skip"' in text and '"limit"' in text


def test_target_name_is_json_escaped():
    target = 'a"b\nc'
    text = PROMPTS["p3"].render("schema", num_queries=1, target_collection=target)
    assert json.dumps(target) in text
    assert json.loads(text.splitlines()[-1])["queries"][0]["collection"] == target


@pytest.mark.parametrize(
    "kwargs",
    [
        {"num_queries": 0},
        {"num_queries": True},
        {"num_queries": 1.5},
        {"schema_text": ""},
        {"schema_text": None},
        {"relationship_hints": " "},
        {"relationship_hints": 3},
        {"target_collection": ""},
        {"target_collection": 1},
        {"target_collection": "a\0b"},
    ],
)
def test_invalid_render_arguments(kwargs):
    args = {"schema_text": "schema", "num_queries": 1, **kwargs}
    with pytest.raises(ValueError):
        PROMPTS["p1"].render(**args)


@pytest.mark.parametrize("instructions,kind", [("", "find"), (None, "find"), ("x", "sql")])
def test_invalid_template(instructions, kind):
    with pytest.raises(ValueError):
        PromptTemplate(instructions, kind)
