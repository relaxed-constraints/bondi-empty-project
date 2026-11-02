"""Deterministic, offline descriptions of BONDI schema observations."""

import json
import re
from collections.abc import Mapping

from bondi.schema import ARRAY_ELEMENT, Schema

_LABELS = {"str": "string", "int": "integer", "bool": "boolean"}


def _path(parts) -> str:
    text = ""
    for part in parts:
        if part is ARRAY_ELEMENT:
            text += "[]"
        elif re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*", part):
            text += ("." if text else "") + part
        else:
            text += "[" + json.dumps(part, ensure_ascii=True) + "]"
    return text


def render_schema_catalog(schemas: Mapping[str, Schema], *, examples_per_type: int = 0) -> str:
    """Render named schemas as sorted bullet lists with explicit structural paths.

    Counts describe inspected documents and immediate parent objects, not the
    full collection. Array-element locations have no missing-field count.
    Examples are sorted by their Python representation and capped per field/type;
    they require value retention on every schema. All retained values are inspected
    to select examples; this setting limits output, not schema memory usage.
    No sampling, database access, or schema mutation is performed.

    Raises:
        TypeError: schemas or one of its entries has the wrong type.
        ValueError: examples_per_type is not a nonnegative integer, a collection
            name is empty, or requested examples were not retained.
    """
    if type(examples_per_type) is not int or examples_per_type < 0:
        raise ValueError("examples_per_type must be a nonnegative integer")
    if not isinstance(schemas, Mapping):
        raise TypeError("schemas must be a mapping of collection names to Schema objects")
    for name, schema in schemas.items():
        if not isinstance(name, str) or not isinstance(schema, Schema):
            raise TypeError("schemas must map string names to Schema objects")
        if not name or "\0" in name:
            raise ValueError("collection names must be nonempty without null characters")
        if examples_per_type and schema.value_mode == "none":
            raise ValueError(f"Examples requested but values were not retained for {name!r}")
    lines = [
        "Schema observations from inspected documents; not full-collection guarantees.",
        "Notation: . denotes nested fields; [] denotes array elements (not MongoDB query syntax).",
        'Bracket-quoted names denote literal field names, e.g. ["address.city"].',
        "Missing counts refer to immediate parent objects; null is a present value.",
    ]
    if examples_per_type:
        lines.append("Examples use Python literal representations; they are not query syntax.")
    if not schemas:
        lines.append("No collections supplied.")
    for name, schema in sorted(schemas.items()):
        lines.extend(
            [
                "",
                f"Collection: {json.dumps(name)}",
                f"Documents inspected: {schema.document_count}",
                "Fields:",
            ]
        )
        fields = sorted(schema.flat_fields.values(), key=lambda field: _path(field.path))
        if not fields:
            lines.append("- No fields observed.")
        for field in fields:
            types = sorted(field.types.values(), key=lambda kind: _LABELS.get(kind.name, kind.name))
            labels = " | ".join(_LABELS.get(kind.name, kind.name) for kind in types)
            line = f"- {_path(field.path)}: {labels or 'unknown (no elements observed)'}"
            if field.parent_count is not None:
                line += f"; missing in {field.missing_count}/{field.parent_count} parent objects"
            if examples_per_type:
                examples = []
                for kind in types:
                    values = kind.values
                    if values:
                        selected = sorted(repr(value) for value in values)[:examples_per_type]
                        examples.append(
                            f"{_LABELS.get(kind.name, kind.name)}: [{', '.join(selected)}]"
                        )
                if examples:
                    line += "; examples {" + "; ".join(examples) + "}"
            lines.append(line)
    return "\n".join(lines) + "\n"
