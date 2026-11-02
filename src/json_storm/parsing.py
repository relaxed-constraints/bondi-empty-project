"""Parse batched model responses into native BONDI queries, without execution."""

import json
from collections.abc import Collection
from dataclasses import dataclass
from typing import Any, Literal

from bondi.mongodb import MongoAggregateQuery, MongoCollectionRef, MongoFindQuery

QueryKind = Literal["find", "aggregate"]
MongoQuery = MongoFindQuery | MongoAggregateQuery


@dataclass(frozen=True)
class ParseError:
    """A response failure; its location is the batch or containing candidate."""

    status: Literal["invalid_json", "invalid_query_shape"]
    message: str


@dataclass(frozen=True)
class ParsedCandidate:
    """One returned entry, identified by its zero-based batch index and position.

    Exactly one of query and error is populated by parse_batch. The decoded raw
    entry is retained even on failure. BONDI queries and raw values remain mutable.
    """

    batch_index: int
    position: int
    raw: Any
    query: MongoQuery | None = None
    error: ParseError | None = None


@dataclass(frozen=True)
class ParsedBatch:
    """One response, retaining malformed entries, duplicates and excess queries.

    error describes a whole-response failure. Otherwise candidates contains every
    returned entry, including invalid ones. A count mismatch is independent of
    entry validity; an unreadable envelope has unknown actual_count.
    """

    batch_index: int
    raw_response: str
    expected_count: int
    candidates: tuple[ParsedCandidate, ...] = ()
    error: ParseError | None = None

    @property
    def actual_count(self) -> int | None:
        """Number of returned entries, or None when the envelope is unreadable."""
        return len(self.candidates) if self.error is None else None

    @property
    def count_matches(self) -> bool | None:
        """Whether the returned count matches the request; None if unknown."""
        return None if self.actual_count is None else self.actual_count == self.expected_count


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key!r}")
        result[key] = value
    return result


def _constant(value):
    raise ValueError(f"Nonstandard JSON numeric literal: {value}")


def _query(entry: Any, kind: QueryKind, database: str, collections: Collection[str]) -> MongoQuery:
    if not isinstance(entry, dict):
        raise ValueError("Each query must be an object")
    required = {"collection", "filter"} if kind == "find" else {"collection", "pipeline"}
    allowed = required | {"projection", "sort", "skip", "limit"} if kind == "find" else required
    if not required <= entry.keys() or entry.keys() - allowed:
        raise ValueError(
            f"Expected required keys {sorted(required)}; allowed keys {sorted(allowed)}"
        )
    collection = entry["collection"]
    if not isinstance(collection, str) or collection not in collections:
        raise ValueError("collection must name a configured collection")
    target = MongoCollectionRef(database, collection)
    if kind == "find":
        sort = entry.get("sort", [])
        if not isinstance(sort, list) or any(not isinstance(pair, list) for pair in sort):
            raise ValueError("sort must be an array of [field, direction] arrays")
        return MongoFindQuery(
            target,
            entry["filter"],
            projection=entry.get("projection"),
            sort=tuple(tuple(pair) for pair in sort),
            skip=entry.get("skip", 0),
            limit=entry.get("limit"),
        )
    return MongoAggregateQuery(target, entry["pipeline"])


def parse_batch(
    response: str,
    *,
    batch_index: int,
    query_kind: QueryKind,
    database: str,
    collections: Collection[str],
    expected_count: int,
) -> ParsedBatch:
    """Parse a strict JSON {"queries": [...]} response without repairs or I/O.

    Find entries require collection and filter, with optional projection (object
    or null), sort (ordered field/direction arrays), skip (nonnegative integer),
    and limit (positive integer or null). Aggregation entries require collection and pipeline. Extra envelope
    and entry keys are rejected, rather than silently dropping query options.
    The configured database is never selected by the model. Collection names are
    checked only for the starting target, not inside native pipeline expressions.

    Invalid model output becomes result records. Invalid caller configuration
    raises TypeError or ValueError. expected_count is this call's requested count,
    including a possibly smaller final batch, rather than the experiment total.
    Plain JSON values are preserved; Extended JSON is not converted to BSON types.
    Successful parsing does not establish semantic validity or read-only safety.
    """
    if not isinstance(response, str):
        raise TypeError("response must be a string")
    if type(batch_index) is not int or batch_index < 0:
        raise ValueError("batch_index must be a nonnegative integer")
    if query_kind not in ("find", "aggregate"):
        raise ValueError("query_kind must be 'find' or 'aggregate'")
    if type(expected_count) is not int or expected_count <= 0:
        raise ValueError("expected_count must be a positive integer")
    if isinstance(collections, str) or not isinstance(collections, Collection) or not collections:
        raise ValueError("collections must be a nonempty collection of names")
    for name in collections:
        MongoCollectionRef(database, name)  # Validate configuration before parsing model output.
    names = frozenset(collections)
    try:
        payload = json.loads(response, object_pairs_hook=_object, parse_constant=_constant)
    except (ValueError, RecursionError) as exc:
        return ParsedBatch(
            batch_index, response, expected_count, error=ParseError("invalid_json", str(exc))
        )
    if (
        not isinstance(payload, dict)
        or set(payload) != {"queries"}
        or not isinstance(payload["queries"], list)
    ):
        return ParsedBatch(
            batch_index,
            response,
            expected_count,
            error=ParseError(
                "invalid_query_shape", 'Expected an object with only a "queries" array'
            ),
        )
    candidates = []
    for position, entry in enumerate(payload["queries"]):
        try:
            query = _query(entry, query_kind, database, names)
        except (TypeError, ValueError, RecursionError) as exc:
            candidates.append(
                ParsedCandidate(
                    batch_index, position, entry, error=ParseError("invalid_query_shape", str(exc))
                )
            )
        else:
            candidates.append(ParsedCandidate(batch_index, position, entry, query=query))
    return ParsedBatch(batch_index, response, expected_count, tuple(candidates))
