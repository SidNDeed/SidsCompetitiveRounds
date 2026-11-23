"""MDPL-GATE-REREAD-1 F2 (round mdplg-r1, finding 2): tournaments.signup
reads its player through _get_player_by_steam, then waits at the player's
EXCLUSIVE identity key (the key delete_player_data takes first), and wrote
the signup row and the time votes from that early read. It now reads the
row again by id directly after its key statement
(main._reread_player_or_404) and answers 404 when the row is gone or its
deleted_at is set, before the ban check and before either signup branch.

The form of part (a) (test_mdpl_gate_reread_pg.py's _scene, _spy, _row and
_naming). Each scene: a second connection H takes P's identity key
exclusive; signup starts, reads P and waits at its key; H tombstones P's row
as delete_player_data does and commits. Then, in this order: signup answers
404 "Player not found"; at the read again nothing was pending in its session;
P's row equals, in every column, the row H left; and no row of the case
schema that names P (the signup row and the time votes among them) was
added, changed or removed after H's commit. Two scenes: an async tournament
(no time votes) and a sync one (the request carries one offered slot).

The mutant (the read again taken out of signup) was run on a copy of the
tree and is not part of this file. The control runs both scenes without the
deletion: signup answers 200, with the read run once and nothing pending,
and the signup row and the sync scene's time vote stand.

F4 (the same round, finding 4), the last row: upload_auto_log's 404 arm with
the blob's removal failing. The answer and the database are as on the arm's
ordinary path; the blob stays on the volume with its orphan marker, for the
retention loop's orphan sweep, and the refusal's line says so.
"""

import os
import sys
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "api"))
sys.path.insert(0, HERE)

from inv_pg import Req, case  # noqa: E402

import schemas  # noqa: E402
import tournaments  # noqa: E402
from test_mdpl_gate_reread_pg import (  # noqa: E402
    NOT_FOUND, WORLDS, World, _armed, _changed, _did, _naming, _player, _row, _scene, _spy, _uid,
    _volume, auto_logs)


async def _signup_worlds(env, tmp_path):
    """Two scenes, one per tournament kind, each with its own P (linked to a
    Discord id, as signup requires) and its own tournament in voting."""
    worlds = []
    for n, kind in ((210, "async"), (220, "sync")):
        did = _did(n)
        p = await _player(env, n, "Reread signup P %s" % kind, did)
        tid = _uid(n + 9)
        dst = (datetime.now(timezone.utc) + timedelta(days=3)).replace(second=0, microsecond=0)
        await env.conn.execute(
            "INSERT INTO tournaments (id, kind, status, format, default_start_ts, lock_at, min_players,"
            " max_players, created_at, created_by)"
            " VALUES ($1, $2, 'voting', 'single_elim_bo3', $3, $4, 8, 16, NOW(), 'cron')",
            tid, kind, dst, dst - timedelta(hours=48))
        slots = [dst] if kind == "sync" else []
        req = schemas.TournamentSignupRequest(steam_id=p.sid, slot_ts=slots)
        worlds.append(World("signup", p, _signup_call(tid, req, p), kind, did=did))
    return worlds


def _signup_call(tid, req, p):
    return lambda db: tournaments.signup(tournament_id=tid, req=req, request=Req(p.sid), db=db)


def test_signup_refuses_a_player_deleted_while_it_waited(monkeypatch, capsys, tmp_path):
    """Read through _get_player_by_steam before its exclusive identity key.
    Without the read again it stores a signup row (and, for a sync
    tournament, the time votes) for P's tombstone, from the early object's
    Discord link."""
    async def body(env):
        _armed(env, tmp_path)
        seen = _spy(env)
        for world in await _signup_worlds(env, tmp_path):
            del seen[:]
            ans, left, named = await _scene(env, world, delete=True)
            assert (ans.status, ans.body) == NOT_FOUND, ("answer", world.route, ans)
            assert seen == [(str(world.p.id), 0, 0, 0)], ("the read again", world.route, seen)
            row = await _row(env.conn, world.p)
            assert row == left, ("P's row", world.route, _changed(left, row))
            now = await _naming(env.conn, world)
            assert now == named, ("rows naming P", world.route, sorted(set(now) ^ set(named))[:4])
    case(monkeypatch, body, prefix="mdplrc")


def test_control_signup_without_the_deletion_answers_as_before(monkeypatch, capsys, tmp_path):
    """Both scenes, H holding P's key and committing nothing: signup answers
    200, the read again ran once with nothing pending, and the signup row and
    the sync scene's one time vote stand."""
    async def body(env):
        _armed(env, tmp_path)
        seen = _spy(env)
        for world in await _signup_worlds(env, tmp_path):
            del seen[:]
            ans, _left, _named = await _scene(env, world, delete=False)
            assert ans.status == 200, ("control", world.route, ans)
            assert seen == [(str(world.p.id), 0, 0, 0)], ("the read again", world.route, seen)
            signups = await env.conn.fetchval(
                "SELECT count(*) FROM tournament_signups WHERE player_id = $1", world.p.id)
            votes = await env.conn.fetchval(
                "SELECT count(*) FROM tournament_time_votes WHERE player_id = $1", world.p.id)
            want = (1, 1 if world.want == "sync" else 0)
            assert (signups, votes) == want, ("stored", world.want, signups, votes)
    case(monkeypatch, body, prefix="mdplrc")


# -- F4 (round mdplg-r1, finding 4): the upload's 404 arm when the blob's removal fails ---------

def test_upload_auto_log_404_with_a_failed_removal_leaves_the_blob_to_the_sweep(monkeypatch, capsys, tmp_path):
    """upload_auto_log's 404 arm (part (a)'s scene, the deletion committing
    while T2 waits at its gate) with the blob's removal made to fail
    (auto_logs._release_marked_blob answers that the blob is still there).
    In this order: the route answers 404 "Player not found"; P's row is the
    row H left and no row naming P was stored (nothing of the upload is in
    the database); the refusal's one line carries _discard_for_refusal's
    sentence for a blob that survives; and the blob stays on the volume with
    its orphan marker, for the retention loop's orphan sweep."""
    async def body(env):
        _armed(env, tmp_path)
        _spy(env)
        env.mp.setattr(auto_logs, "_release_marked_blob", lambda own: False)
        (world,) = await WORLDS["upload_auto_log"](env, tmp_path)
        capsys.readouterr()
        ans, left, named = await _scene(env, world, delete=True)
        out = capsys.readouterr().out
        assert (ans.status, ans.body) == NOT_FOUND, ("answer", ans)
        row = await _row(env.conn, world.p)
        assert row == left, ("P's row", _changed(left, row))
        now = await _naming(env.conn, world)
        assert now == named, ("rows naming P", sorted(set(now) ^ set(named))[:4])
        lines = [ln for ln in out.splitlines() if "refused 404 for" in ln]
        assert len(lines) == 1 and "could NOT be removed and SURVIVES as" in lines[0] \
            and auto_logs._ORPHAN_MARKER + "=" in lines[0], ("the line", lines, out[-2000:])
        blobs, marks = _volume(tmp_path)
        assert len(blobs) == 1 and marks == [blobs[0] + auto_logs._ORPHAN_MARKER_SUFFIX], ("the volume", blobs, marks)
    case(monkeypatch, body, prefix="mdplrc")
