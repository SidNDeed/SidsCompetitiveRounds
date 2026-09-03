"""Release A W1 request, storage, migration, and seat-orientation contract."""

from __future__ import annotations

import inspect
from pathlib import Path
import re

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import Integer, String

import main
from models import Match
from schemas import MatchReport
from net_seat_contract import (
    REQUEST_FIELDS,
    REQUEST_NUMERIC_MAX,
    REQUEST_TAG,
    STORAGE_FIELDS,
    SUFFIX_TO_REQUEST,
    old_match_body,
    request_sentinels,
)


_validation_app = FastAPI()


@_validation_app.post("/match-report")
def _accept_match_report(_report: MatchReport):
    return {"accepted": True}


_client = TestClient(_validation_app)


def test_net_seat_request_cardinality_defaults_and_old_body():
    assert len(REQUEST_FIELDS) == 25
    assert len(REQUEST_NUMERIC_MAX) == 24
    actual_w1_fields = {
        name
        for name in MatchReport.model_fields
        if name.startswith(("local_net_", "local_obs_"))
    }
    assert actual_w1_fields == set(REQUEST_FIELDS)

    for name in REQUEST_FIELDS:
        field = MatchReport.model_fields[name]
        assert not field.is_required(), name
        assert field.default is None, name

    report = MatchReport.model_validate(old_match_body())
    assert all(getattr(report, name) is None for name in REQUEST_FIELDS)

    values = main._match_net_seat_values(report, reporter_is_p1=True)
    assert set(values) == set(STORAGE_FIELDS)
    assert all(value is None for value in values.values())

    # The ORM constructor is the same explicit value path used by submit_match.
    match = Match(**values)
    assert all(getattr(match, name) is None for name in STORAGE_FIELDS)


@pytest.mark.parametrize("field_name,maximum", REQUEST_NUMERIC_MAX.items())
def test_net_seat_numeric_bounds_are_422(field_name: str, maximum: int):
    for valid in (0, maximum):
        body = old_match_body()
        body[field_name] = valid
        response = _client.post("/match-report", json=body)
        assert response.status_code == 200, (field_name, valid, response.text)

    for invalid in (-1, maximum + 1, 2**31):
        body = old_match_body()
        body[field_name] = invalid
        response = _client.post("/match-report", json=body)
        assert response.status_code == 422, (field_name, invalid, response.text)


def test_net_seat_tag_length_is_422_at_49():
    body = old_match_body()
    body[REQUEST_TAG] = "t" * 48
    assert _client.post("/match-report", json=body).status_code == 200

    body[REQUEST_TAG] = "t" * 49
    assert _client.post("/match-report", json=body).status_code == 422


def test_net_seat_model_has_exactly_50_nullable_no_default_columns():
    columns = {
        column.name: column
        for column in Match.__table__.columns
        if re.fullmatch(r"p[12]_(?:net|obs)_.+", column.name)
    }
    assert set(columns) == set(STORAGE_FIELDS)
    assert len(columns) == 50

    for name, column in columns.items():
        assert column.nullable is True, name
        assert column.default is None, name
        assert column.server_default is None, name
        if name.endswith("_tags"):
            assert isinstance(column.type, String), name
            assert column.type.length == 48, name
        else:
            assert isinstance(column.type, Integer), name


@pytest.mark.parametrize("reporter_is_p1", (True, False))
def test_net_seat_orientation_populates_only_authenticated_reporter(
    reporter_is_p1: bool,
):
    request_values = request_sentinels()
    report = MatchReport.model_validate({**old_match_body(), **request_values})
    oriented = main._match_net_seat_values(report, reporter_is_p1)
    reporter_seat = "p1" if reporter_is_p1 else "p2"
    other_seat = "p2" if reporter_is_p1 else "p1"

    for suffix, request_name in SUFFIX_TO_REQUEST.items():
        assert oriented[f"{reporter_seat}_{suffix}"] == request_values[request_name]
        assert oriented[f"{other_seat}_{suffix}"] is None

    match = Match(**oriented)
    for suffix, request_name in SUFFIX_TO_REQUEST.items():
        assert getattr(match, f"{reporter_seat}_{suffix}") == request_values[request_name]
        assert getattr(match, f"{other_seat}_{suffix}") is None


def test_submit_match_binds_net_seat_values_to_existing_reporter_orientation():
    source = inspect.getsource(main.submit_match)
    assert "reporter_is_p1 = reporter.id == p1.id" in source
    assert "**_match_net_seat_values(report, reporter_is_p1)" in source


def test_migration_284_matches_the_orm_contract_and_has_no_defaults():
    migration = (
        Path(__file__).resolve().parents[1] / "sql" / "284_match_net_seat.sql"
    ).read_text(encoding="utf-8")
    statements = re.findall(
        r"^ALTER TABLE matches ADD COLUMN IF NOT EXISTS (\w+) ([A-Z]+(?:\(\d+\))?);$",
        migration,
        flags=re.MULTILINE,
    )

    assert re.search(r"^BEGIN;$", migration, flags=re.MULTILINE)
    assert re.search(r"^COMMIT;$", migration, flags=re.MULTILINE)
    assert len(statements) == 50
    # r6 LOW 7: columns-only — every executable line is BEGIN, one of the 50
    # ALTERs, or COMMIT; any other DDL/DML (a leftover table, an index) fails.
    executable = [
        line.strip()
        for line in migration.splitlines()
        if line.strip() and not line.strip().startswith("--")
    ]
    assert executable[0] == "BEGIN;"
    assert executable[-1] == "COMMIT;"
    assert len(executable) == 52
    assert all(
        line.startswith("ALTER TABLE matches ADD COLUMN IF NOT EXISTS ")
        for line in executable[1:-1]
    )
    assert {name for name, _kind in statements} == set(STORAGE_FIELDS)

    for name, sql_type in statements:
        assert sql_type == ("VARCHAR(48)" if name.endswith("_tags") else "INTEGER")
        line = next(line for line in migration.splitlines() if f" {name} " in line)
        assert " DEFAULT " not in line.upper()
