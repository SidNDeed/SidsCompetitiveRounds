"""Frozen match-HMAC golden vectors, including W1 advisory-field invariance."""

from __future__ import annotations

import hashlib
import hmac
from types import SimpleNamespace

import pytest

import main
from net_seat_contract import REQUEST_FIELDS


SECRET = "golden-test-secret"

ONE_V_ONE_CANONICAL = (
    "76561198000000001:76561198000000002:5:3:true:"
    "76561198000000001:ranked_abcd_r1"
)
TEAM_CANONICAL = (
    "76561198000000001:76561198000000002:76561198000000003:"
    "76561198000000004:5:2:true:76561198000000001:team_abcd_r1:"
    "1:11111111-2222-3333-4444-555555555555"
)
OVT_CANONICAL = (
    "76561198000000001:76561198000000002:76561198000000003:5:4:"
    "false:76561198000000002:ovt_abcd_r1:2:"
    "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
)

ONE_V_ONE_SIGNATURE = "f5c1b31cd4c6fed62c2f2809673c29dd02051013496f7c460e01b501f2ecd556"
TEAM_SIGNATURE = "a24aa3b6decb407b6f5e771a77e24c46a48b2bdaebc66ff042a663ff7be98985"
OVT_SIGNATURE = "876dc1147cffcbcd3d07225da48e203dc1e5d0cbe5f7fcd4463c0b98ad4303b9"


def _digest(canonical: str) -> str:
    return hmac.new(SECRET.encode(), canonical.encode(), hashlib.sha256).hexdigest()


def _with_advisory_fields(**values):
    report = SimpleNamespace(**values)
    for name in REQUEST_FIELDS:
        setattr(report, name, None)
    return report


def _one_v_one_report():
    return _with_advisory_fields(
        player1=SimpleNamespace(steam_id="76561198000000001"),
        player2=SimpleNamespace(steam_id="76561198000000002"),
        p1_rounds_won=5,
        p2_rounds_won=3,
        is_ranked=True,
        reported_by_steam_id="76561198000000001",
        photon_room_id="ranked_abcd_r1",
        hmac_signature=ONE_V_ONE_SIGNATURE,
    )


def _team_report():
    return _with_advisory_fields(
        t1a=SimpleNamespace(steam_id="76561198000000001"),
        t1b=SimpleNamespace(steam_id="76561198000000002"),
        t2a=SimpleNamespace(steam_id="76561198000000003"),
        t2b=SimpleNamespace(steam_id="76561198000000004"),
        t1_rounds_won=5,
        t2_rounds_won=2,
        is_ranked=True,
        reported_by_steam_id="76561198000000001",
        photon_room_id="team_abcd_r1",
        winner_team=1,
        series_id="11111111-2222-3333-4444-555555555555",
        hmac_signature=TEAM_SIGNATURE,
    )


def _ovt_report():
    return _with_advisory_fields(
        solo=SimpleNamespace(steam_id="76561198000000001"),
        duo_a=SimpleNamespace(steam_id="76561198000000002"),
        duo_b=SimpleNamespace(steam_id="76561198000000003"),
        solo_rounds_won=5,
        duo_rounds_won=4,
        is_ranked=False,
        reported_by_steam_id="76561198000000002",
        photon_room_id="ovt_abcd_r1",
        winner_side=2,
        series_id="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        hmac_signature=OVT_SIGNATURE,
    )


@pytest.mark.parametrize(
    "canonical,field_count,signature",
    (
        (ONE_V_ONE_CANONICAL, 7, ONE_V_ONE_SIGNATURE),
        (TEAM_CANONICAL, 11, TEAM_SIGNATURE),
        (OVT_CANONICAL, 10, OVT_SIGNATURE),
    ),
)
def test_golden_hmac_canonical_bytes(canonical, field_count, signature):
    assert len(canonical.split(":")) == field_count
    assert _digest(canonical) == signature


@pytest.mark.parametrize(
    "factory,verify",
    (
        (_one_v_one_report, main.verify_hmac),
        (_team_report, main._verify_team_hmac),
        (_ovt_report, main._verify_ovt_hmac),
    ),
)
def test_golden_hmac_ignores_every_net_seat_advisory(
    monkeypatch, factory, verify,
):
    monkeypatch.setattr(main, "MATCH_HMAC_SECRET", SECRET)
    report = factory()
    assert verify(report)

    for index, field_name in enumerate(REQUEST_FIELDS):
        setattr(
            report,
            field_name,
            f"tag-change-{index}" if field_name.endswith("_tags") else 1000 + index,
        )
        assert verify(report), field_name
