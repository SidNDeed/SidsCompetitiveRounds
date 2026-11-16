"""QDIG-1 fixtures: held game reports shaped like the six live rows of
16 Nov 2026, with invented names and ids only.

Numbers by slot (rounds/points/kills), from the work order:
  recorded game A 5/14/31 4/10/18 4/11/24 3/8/13, held twice as
                  5/14/31 4/10/19 4/11/23 3/8/13            (FOR THE RECORD)
  recorded game B 4/16/49 4/14/34 5/11/19 3/11/13, held twice as
                  4/16/49 4/14/33 5/11/19 3/11/13           (FOR THE RECORD)
  unrecorded C2   0/2/8 0/2/7 0/2/13 5/11/31 2/5/20 0/0/10   (lobby_completed)
  unrecorded C3   1/2/12 0/3/20 1/4/10 5/11/34 0/4/10 0/0/3  (lobby_completed)

Shared by the pure tests (facts built here) and the live-PostgreSQL tests
(rows seeded from the same numbers).
"""

import json
import uuid
from datetime import datetime, timedelta, timezone

import schemas

T_LIVE = datetime(2026, 11, 15, 20, 0, 0, tzinfo=timezone.utc)   # games A and B
T_OCT = datetime(2026, 10, 4, 1, 30, 0, tzinfo=timezone.utc)     # games C2 and C3


def steam(n: int) -> str:
    """Synthetic 17-digit ids, outside every real account range."""
    return f"9000000000017{n:04d}"


NAMES = {1: "Gale", 2: "Heron", 3: "Iris", 4: "Juniper",
         11: "Ash", 12: "Birch", 13: "Cedar", 14: "Dune", 15: "Elm", 16: "Fern"}

LOBBY_AB = uuid.UUID("0a0a0a0a-0000-4000-8000-00000000a0b0")
LOBBY_C = uuid.UUID("0c0c0c0c-0000-4000-8000-00000000c000")
MATCH_A = uuid.UUID("b8ffc875-f9d8-4000-8000-00000000000a")
MATCH_B = uuid.UUID("5e1f00d2-77aa-4000-8000-00000000000b")

GAMES = {
    "A": {"lobby": LOBBY_AB, "room": "QDIGROOMAB_200000_r1", "seats": [1, 2, 3, 4], "match": MATCH_A,
          "recorded": [(5, 14, 31), (4, 10, 18), (4, 11, 24), (3, 8, 13)],
          "held": [(5, 14, 31), (4, 10, 19), (4, 11, 23), (3, 8, 13)],
          "reporters": (2, 3), "at": T_LIVE, "reason": "ffa_game_contradiction"},
    "B": {"lobby": LOBBY_AB, "room": "QDIGROOMAB_203000_r2", "seats": [1, 2, 3, 4], "match": MATCH_B,
          "recorded": [(4, 16, 49), (4, 14, 34), (5, 11, 19), (3, 11, 13)],
          "held": [(4, 16, 49), (4, 14, 33), (5, 11, 19), (3, 11, 13)],
          "reporters": (2, 4), "at": T_LIVE + timedelta(minutes=30), "reason": "ffa_game_contradiction"},
    "C2": {"lobby": LOBBY_C, "room": "QDIGROOMC_013000_r2", "seats": [11, 12, 13, 14, 15, 16], "match": None,
           "recorded": None,
           "held": [(0, 2, 8), (0, 2, 7), (0, 2, 13), (5, 11, 31), (2, 5, 20), (0, 0, 10)],
           "reporters": (11,), "at": T_OCT, "reason": "lobby_completed"},
    "C3": {"lobby": LOBBY_C, "room": "QDIGROOMC_014500_r3", "seats": [11, 12, 13, 14, 15, 16], "match": None,
           "recorded": None,
           "held": [(1, 2, 12), (0, 3, 20), (1, 4, 10), (5, 11, 34), (0, 4, 10), (0, 0, 3)],
           "reporters": (11,), "at": T_OCT + timedelta(minutes=15), "reason": "lobby_completed"},
}


def winner_of(numbers, seats):
    best = max(n[0] for n in numbers)
    (seat,) = [s for s, n in zip(seats, numbers) if n[0] == best]
    return seat


def payload(game: str, numbers=None, *, reporter=None, winner=None, flags=None, started=True) -> dict:
    """A held report body as the capture stores it (model_dump, then JSON).
    flags: {seat: (left_early, absent)}."""
    g = GAMES[game]
    numbers = numbers or g["held"]
    flags = flags or {}
    rep = schemas.FfaMatchReport(
        lobby_id=str(g["lobby"]), photon_room_id=g["room"],
        reported_by_steam_id=steam(reporter or g["reporters"][0]),
        winner_steam_id=steam(winner or winner_of(numbers, g["seats"])),
        started_at=g["at"] if started else None,
        players=[{"steam_id": steam(s), "display_name": NAMES[s], "slot": i,
                  "rounds_won": r, "points_total": p, "kills": k,
                  "left_early": flags.get(s, (False, False))[0], "absent": flags.get(s, (False, False))[1],
                  "game_points_at_leave": 0 if flags.get(s, (False, False))[0] else None}
                 for i, (s, (r, p, k)) in enumerate(zip(g["seats"], numbers))])
    return json.loads(json.dumps(rep.model_dump(), default=str))


def row(game: str, *, keyed=True, reason=None, body=None, qid=None, created=None, posted=None,
        reminded=None) -> dict:
    """A pending held row as _qdig_classify and the feed read it."""
    g = GAMES[game]
    return {"id": qid or uuid.uuid4(), "mode": "ffa", "reason": reason or g["reason"],
            "group_id": g["lobby"], "photon_room_id": g["room"] if keyed else None,
            "player_ids": [], "payload": body if body is not None else payload(game),
            "created_at": created or (g["at"] + timedelta(minutes=12)),
            "digest_posted_at": posted, "digest_reminded_at": reminded}


def facts(*games, recorded=None, kills_tiebreak=False, voided=False, readmit=False, ranked=True,
          names=True) -> dict:
    """What _qdig_load would read for these games: the recorded game (when
    the game has one, numbers `recorded` or the fixture's), its per-player
    rows, the lobbies and the players' names."""
    out = {"matches": {}, "vectors": {}, "lobbies": {}, "names": {}}
    for game in games:
        g = GAMES[game]
        out["lobbies"][str(g["lobby"])] = {"id": g["lobby"], "is_ranked": ranked,
                                           "kills_tiebreak": kills_tiebreak, "readmit_v1": readmit,
                                           "player_count": len(g["seats"])}
        if names:
            for s in g["seats"]:
                out["names"][steam(s)] = {"steam_id": steam(s), "display_name": NAMES[s], "deleted_at": None}
        nums = recorded or g["recorded"]
        if g["match"] is None or nums is None:
            continue
        pids = {s: uuid.UUID(int=0x9000 + s) for s in g["seats"]}
        win = winner_of(nums, g["seats"])
        out["matches"][g["room"]] = {"id": g["match"], "photon_room_id": g["room"], "lobby_id": g["lobby"],
                                     "winner_id": pids[win],
                                     "invalidated_at": (g["at"] + timedelta(hours=1)) if voided else None}
        out["vectors"][str(g["match"])] = [
            {"match_id": g["match"], "player_id": pids[s], "steam_id": steam(s), "rounds_won": r,
             "points_total": p, "kills": k, "left_early": False, "absent": False, "exclusion_reasons": []}
            for s, (r, p, k) in zip(g["seats"], nums)]
    return out


def live_rows() -> list:
    """The six live rows: A and B each held twice (a keyed row and a variant
    row, two different reporters), C2 and C3 once each."""
    out = []
    for game in ("A", "B"):
        g = GAMES[game]
        for i, rep in enumerate(g["reporters"]):
            out.append(row(game, keyed=(i == 0), body=payload(game, reporter=rep),
                           qid=uuid.UUID(f"{0xa0 + i + (0 if game == 'A' else 2):08x}-0000-4000-8000-0000000000{0xa0 + i:02x}")))
    out.append(row("C2", qid=uuid.UUID("c2c2c2c2-0000-4000-8000-0000000000c2")))
    out.append(row("C3", qid=uuid.UUID("c3c3c3c3-0000-4000-8000-0000000000c3")))
    return out
