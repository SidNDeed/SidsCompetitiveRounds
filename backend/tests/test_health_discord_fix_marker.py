"""The Discord fix's release discriminators (integrator addendum, round 2).

The release train must prove that the NEW api build answers on both boxes
and that the NEW bot runs. The fix's one new route, POST
/api/v1/internal/pc/packs/open, cannot tell the builds apart on the standby:
its replica gate answers 503 to every POST before any handler runs. So:

api -- the /health key `discord_fix`: 1 when the app routes the bot's pack
opener to internal_pc_open_pack AND the read a replay of a purchase key runs
(_pc_open_for's read of the pack row by player and nonce; round 2, M1) runs
on the box's database; 0 when either fails; absent on the build before the
fix. Each half is mutated here with its control beside it, and the
live-PostgreSQL rows run the real probe against a renamed column and a
renamed table, then against the mended schema.

bot -- the startup witness [DISCORD-FIX]: printed by on_ready just before
[BOT-READY] (only the dance cards' [BOT-FEATURE] line between), stamped with the process's gen, naming the purchase journal's
volume as the process finds it ("mounted" or "NOT mounted"), the journal's
unsettled count, the replay policy and the sync availability-check rule.
"""
import ast
import copy
import inspect
import json
import os
import sys
from types import SimpleNamespace

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.normpath(os.path.join(HERE, "..", "api")))

from test_player_cards_server import _run                        # noqa: E402
import discord_collection_harness as H                           # noqa: E402
import main                                                      # noqa: E402
import schemas                                                   # noqa: E402

DSN = os.environ.get("DISCORD_COLLECTION_TEST_PG_DSN")
OPTOUT = H.optout(os.environ.get("DISCORD_COLLECTION_TEST_PG_OPTOUT"))
OPEN_PATH = "/api/v1/internal/pc/packs/open"


class _PgError(Exception):
    """The driver's error, carrying its SQLSTATE."""

    def __init__(self, sqlstate):
        super().__init__(f"SQLSTATE {sqlstate}")
        self.sqlstate = sqlstate


class _Wrapped(Exception):
    """SQLAlchemy's wrapper: the driver's error on .orig."""

    def __init__(self, orig):
        super().__init__(f"wrapped: {orig}")
        self.orig = orig


class _Up:
    """A connected session: every statement runs; records what ran."""

    def __init__(self):
        self.ran, self.rollbacks = [], 0

    async def execute(self, stmt, params=None, *a, **k):
        self.ran.append((str(stmt), params))
        return None

    async def rollback(self):
        self.rollbacks += 1


class _Gap(_Up):
    """A connected session whose statements on pc_packs fail with `sqlstate`."""

    def __init__(self, sqlstate):
        super().__init__()
        self.sqlstate = sqlstate

    async def execute(self, stmt, params=None, *a, **k):
        await super().execute(stmt, params)
        if "FROM pc_packs" in str(stmt):
            raise _Wrapped(_PgError(self.sqlstate))
        return None


class _Down:
    async def execute(self, *a, **k):
        raise OSError("database unreachable")


def _health(db):
    return _run(main.health_check(db=db)).model_dump()


# -- api: the /health key ------------------------------------------------------------------------

def test_the_marker_reads_1_on_this_build_on_both_arms(monkeypatch):
    """The control for every mutation below: the route bound, the read found and run."""
    monkeypatch.setattr(main, "_DISCORD_FIX_LAST", 0)
    before = _health(_Down())
    assert (before["status"], before["discord_fix"]) == ("degraded", 0)   # no probe yet: not proven
    up = _Up()
    ok = _health(up)
    assert (ok["status"], ok["discord_fix"]) == ("ok", 1)
    assert (main._DISCORD_FIX_PROBE, dict(main._DISCORD_FIX_BINDS)) in up.ran
    after = _health(_Down())
    assert (after["status"], after["discord_fix"]) == ("degraded", 1)    # the last probe's value


def test_the_route_half_unbound_reads_0_and_its_control_reads_1(monkeypatch):
    routes = list(main.app.router.routes)
    assert sum(1 for r in routes if getattr(r, "path", None) == OPEN_PATH) == 1
    monkeypatch.setattr(main.app.router, "routes", [r for r in routes if getattr(r, "path", None) != OPEN_PATH])
    assert _health(_Up())["discord_fix"] == 0          # mutation: the route is not routed
    monkeypatch.setattr(main.app.router, "routes", routes)
    assert _health(_Up())["discord_fix"] == 1          # control: the same routes, whole
    rebound = copy.copy(next(r for r in routes if getattr(r, "path", None) == OPEN_PATH))
    rebound.endpoint = lambda *a, **k: None
    monkeypatch.setattr(main.app.router, "routes",
                        [rebound if getattr(r, "path", None) == OPEN_PATH else r for r in routes])
    assert _health(_Up())["discord_fix"] == 0          # mutation: routed to another handler


async def _no_read(db):
    await db.execute("SELECT id FROM pc_packs WHERE player_id = CAST(:pid AS uuid)")


async def _two_reads(db):
    await db.execute("SELECT id FROM pc_packs WHERE player_id = CAST(:pid AS uuid) AND nonce = CAST(:nonce AS text)")
    await db.execute("SELECT status FROM pc_packs WHERE player_id = CAST(:pid AS uuid) AND nonce = CAST(:nonce AS text)")


async def _one_read(db):
    await db.execute("SELECT id FROM pc_packs WHERE player_id = CAST(:pid AS uuid) AND nonce = CAST(:nonce AS text)")


def test_the_probe_is_the_replay_read_the_open_path_runs(monkeypatch):
    probe = main._DISCORD_FIX_PROBE
    assert probe and main._discord_fix_read(main._pc_open_for) == probe
    flat = " ".join(probe.split())
    assert flat == ("SELECT id, status, source, mode, kind, pay, price, reject_reason, created_at, opened_at "
                    "FROM pc_packs WHERE player_id = CAST(:pid AS uuid) AND nonce = CAST(:nonce AS text)")
    # The derivation, mutated: no such read, or two, finds nothing; one finds it.
    assert main._discord_fix_read(_no_read) == ""
    assert main._discord_fix_read(_two_reads) == ""
    assert main._discord_fix_read(_one_read) != ""
    monkeypatch.setattr(main, "_DISCORD_FIX_PROBE", "")
    assert _health(_Up())["discord_fix"] == 0          # mutation: the open path lost its replay read
    monkeypatch.setattr(main, "_DISCORD_FIX_PROBE", probe)
    assert _health(_Up())["discord_fix"] == 1          # control


def test_the_replay_answers_the_columns_the_first_answer_is_built_from():
    """The committing UPDATE's RETURNING list (the first answer's row) is
    the replay read's select list, so the probe names every column either
    answer reads from the pack row."""
    consts = [c for c in main._pc_open_for.__code__.co_consts if isinstance(c, str)]
    done = [" ".join(c.split()) for c in consts if " ".join(c.split()).startswith("UPDATE pc_packs SET status = 'done'")]
    assert len(done) == 1
    returning = done[0].partition(" RETURNING ")[2]
    selected = " ".join(main._DISCORD_FIX_PROBE.split())[len("SELECT "):].partition(" FROM pc_packs ")[0]
    assert returning == selected


@pytest.mark.parametrize("sqlstate", ["42703", "42P01"])
def test_the_schema_half_a_missing_column_or_table_reads_0_and_rolls_back(monkeypatch, sqlstate):
    gap = _Gap(sqlstate)
    broken = _health(gap)
    assert (broken["status"], broken["discord_fix"]) == ("ok", 0) and gap.rollbacks == 1
    assert _health(_Up())["discord_fix"] == 1          # control
    assert main._discord_fix_schema_missing(_Wrapped(_PgError(sqlstate)))
    assert main._discord_fix_schema_missing(_PgError(sqlstate))
    raised_from = RuntimeError("raised from the driver's error")
    raised_from.__cause__ = _PgError(sqlstate)
    assert main._discord_fix_schema_missing(raised_from)


def test_any_other_probe_error_is_a_database_fault_not_a_schema_answer(monkeypatch):
    assert _health(_Up())["discord_fix"] == 1
    fault = _health(_Gap("57P01"))
    assert (fault["status"], fault["discord_fix"]) == ("degraded", 1)
    assert not main._discord_fix_schema_missing(_Wrapped(_PgError("57P01")))
    # A driver error merely raised while another was handled is not read.
    outer = RuntimeError("later")
    outer.__context__ = _PgError("42703")
    assert not main._discord_fix_schema_missing(outer)


def test_the_key_is_declared_required_and_read_by_nothing_else():
    field = schemas.HealthResponse.model_fields["discord_fix"]
    assert field.is_required()
    assert "discord_fix_not_a_field" not in schemas.HealthResponse.model_fields
    src = inspect.getsource(main)
    assert src.count("_discord_fix_probe(") == 2       # its definition and the connected arm's call
    assert src.count("discord_fix=") == 2               # the two arms
    assert src.count("_DISCORD_FIX_LAST") == 6          # the cache, its global, its three writes, the degraded arm


def e2e(monkeypatch, tmp_path, fn):
    dsn = H.require_pg(DSN, OPTOUT)

    async def go():
        async with H.Env(monkeypatch, tmp_path, dsn) as env:
            return await fn(env)
    return H.run(go())


@pytest.mark.parametrize("break_sql, mend_sql", [
    ("ALTER TABLE pc_packs RENAME COLUMN reject_reason TO reject_reason_gone",
     "ALTER TABLE pc_packs RENAME COLUMN reject_reason_gone TO reject_reason"),
    ("ALTER TABLE pc_packs RENAME TO pc_packs_gone",
     "ALTER TABLE pc_packs_gone RENAME TO pc_packs"),
])
def test_pg_the_probe_reads_0_while_what_it_names_is_missing_and_1_once_mended(monkeypatch, tmp_path,
                                                                              break_sql, mend_sql):
    async def go(env):
        await env.ex(break_sql)
        try:
            broken = (await env.client.get("/api/v1/health", headers=env.ihead())).json()
        finally:
            await env.ex(mend_sql)
        mended = (await env.client.get("/api/v1/health", headers=env.ihead())).json()
        return broken, mended
    broken, mended = e2e(monkeypatch, tmp_path, go)
    assert (broken["status"], broken["discord_fix"]) == ("ok", 0)
    assert (mended["status"], mended["discord_fix"]) == ("ok", 1)


# -- bot: the startup witness --------------------------------------------------------------------

WITNESS_FUNCS = {"_pc_fix_ready_line", "_pc_buy_pending", "_pc_buy_settled_ok"}
WITNESS_ASSIGNS = {"_PC_OPEN_SENDS"}
TAIL = ("an unanswered open sends its key 3 times; every purchase names the player it was bought for; "
        "sync availability checks wait for a start time with min_players votes")


def witness(tmp_path, *, mounted, journal=None, ismount=None, source=None):
    path = tmp_path / "bot-state" / "pc_buy_pending.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    if journal is not None:
        path.write_text(journal, encoding="utf-8")
    folder = str(path.parent)
    fake_os = SimpleNamespace(path=SimpleNamespace(dirname=os.path.dirname,
                                                   ismount=ismount or (lambda p: mounted and p == folder)))

    async def no_http(call):
        raise AssertionError("the witness makes no request")
    rig = H.BotRig(no_http, funcs=WITNESS_FUNCS, assigns=WITNESS_ASSIGNS, source=source,
                   extra={"os": fake_os, "_PC_BUY_PENDING_FILE": str(path), "_BOT_GEN": "gen-test"})
    return rig.ns["_pc_fix_ready_line"](), str(path)


def test_the_witness_names_a_mounted_journal_and_its_unsettled_purchases(tmp_path):
    journal = json.dumps({H.discord_of(1): {"nonce": "nonce-aaaaaaaa", "pay": "gold", "player": H.steam_of(1)},
                          H.discord_of(2): {"nonce": "nonce-bbbbbbbb", "pay": "shards", "player": H.steam_of(2)}})
    line, path = witness(tmp_path, mounted=True, journal=journal)
    assert line == f"[DISCORD-FIX] gen=gen-test purchase journal {path}: mounted, 2 unsettled, 0 bought and awaiting their reveal; {TAIL}"


def test_the_witness_counts_bought_purchases_awaiting_their_reveal_apart(tmp_path):
    """Round 3, item 2: an entry marked settled is a bought pack whose reveal
    was not delivered, not an unsettled purchase."""
    journal = json.dumps({H.discord_of(1): {"nonce": "nonce-aaaaaaaa", "pay": "gold", "player": H.steam_of(1)},
                          H.discord_of(2): {"nonce": "nonce-bbbbbbbb", "pay": "gold", "player": H.steam_of(2),
                                            "settled": {"pack_id": "p" * 8, "pay": "gold", "price": 100}}})
    line, path = witness(tmp_path, mounted=True, journal=journal)
    assert line == (f"[DISCORD-FIX] gen=gen-test purchase journal {path}: mounted, 1 unsettled, "
                    f"1 bought and awaiting their reveal; {TAIL}")


def test_the_witness_says_not_mounted_when_the_volume_is_missing(tmp_path):
    line, path = witness(tmp_path, mounted=False)
    assert line == f"[DISCORD-FIX] gen=gen-test purchase journal {path}: NOT mounted, 0 unsettled, 0 bought and awaiting their reveal; {TAIL}"


def test_the_witness_says_unreadable_for_a_journal_it_cannot_read(tmp_path):
    line, path = witness(tmp_path, mounted=True, journal="not json")
    assert line == f"[DISCORD-FIX] gen=gen-test purchase journal {path}: mounted, unreadable; {TAIL}"


WITNESS_GUARD = ('    except Exception as ex:\n'
                 '        return f"[DISCORD-FIX] gen={_BOT_GEN} witness failed: {type(ex).__name__}: {ex}"\n')


def test_the_witness_never_raises_it_says_it_failed(tmp_path):
    """A witness that cannot be built says so in its own line, which the
    release train reads as not proven, and on_ready still reaches
    [BOT-READY]. Mutation: the guard catches nothing that can happen here."""
    def broken(path):
        raise OSError("volume probe failed")
    line, _ = witness(tmp_path, mounted=True, ismount=broken)
    assert line == "[DISCORD-FIX] gen=gen-test witness failed: OSError: volume probe failed"   # control
    source = H.bot_source()
    assert source.count(WITNESS_GUARD) == 1
    mutated = source.replace(WITNESS_GUARD, WITNESS_GUARD.replace("except Exception", "except ZeroDivisionError"))
    with pytest.raises(OSError, match="volume probe failed"):                                 # mutation
        witness(tmp_path, mounted=True, ismount=broken, source=mutated)


# The other whole-line signal on_ready prints between this witness and
# [BOT-READY]: the dance cards' [BOT-FEATURE] line, which its own test holds
# immediately before the ready line (test_pc_bot_card_gif_signal).
_SIBLING_SIGNALS = ("print(_pc_card_gif_signal(), flush=True)",)


def _witness_then_ready(source) -> bool:
    """on_ready's last statement is [BOT-READY], and the unconditional
    statements just before it are the witness print followed only by the
    sibling signal lines."""
    for node in ast.parse(source).body:
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "on_ready":
            *head, ready_stmt = node.body
            if not ast.unparse(ready_stmt).startswith("print('[BOT-READY] '"):
                return False
            while head and ast.unparse(head[-1]) in _SIBLING_SIGNALS:
                head.pop()
            return bool(head) and ast.unparse(head[-1]) == "print(_pc_fix_ready_line())"
    raise AssertionError("no on_ready")


def test_on_ready_prints_the_witness_just_before_bot_ready():
    source = H.bot_source()
    assert _witness_then_ready(source)                                   # control
    mutated = source.replace("    print(_pc_fix_ready_line())\n", "", 1)
    assert mutated != source
    assert not _witness_then_ready(mutated)                              # mutation: the witness is gone
