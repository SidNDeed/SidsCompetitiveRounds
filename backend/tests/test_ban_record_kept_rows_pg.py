"""BAN-RECORD-1 R7 (ORDER ADD2), bar V10, for the KEPT id rows of main.py and
the bot whose owner turns out to read the row and its ban in ONE statement
already. Each later statement reads, beside its ban word, the deletion's own
mark on the same row: delete_player_data rewrites the steam id and sets
deleted_at in one UPDATE (one commit; _tombstone mirrors it from the
deletion's source), and each owner answers a row so marked as it answers no
row: refused or left out. So an account removed between the two statements
is never answered as a live account without a ban, and no line of these
owners changes (ADD2: answered in the hand-back with the lines, and the
table corrected).

On PostgreSQL (a case schema of inv_pg, CF_TEST_PG_DSN), each owner's own
statement (main's constant, or the text in the owner's source evaluated in
main's namespace; never retyped) is handed a kept id. The gap between the
two statements is not opened by a hook: the test hands the owner a kept id
whose row was removed beforehand (ADD2's second form):
  (a) the row removed in the deletion's own shape (_tombstone, under the
      account's identity key, as the deletion holds it);
  (b) the same, with an active ban under the steam id the earlier statement
      knew;
  (c) the unchanged row under an active ban;
  (d) the unchanged row with no ban;
and, as the yardstick, an id with no row. (a) and (b) answer as no row
does; (c) and (d) answer as today (the code is today's). The owner's
decision on the row it read is its own function where it has one
(_pc_trade_party_refusal, _pc_motion_check); where the decision is a line of
a route, that line is pinned by its text below.
"""
import ast
import inspect
import os
import sys
import textwrap
import uuid
from types import SimpleNamespace

HERE = os.path.dirname(os.path.abspath(__file__))
API = os.path.normpath(os.path.join(HERE, "..", "api"))
for _p in (API, HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pytest  # noqa: E402
from sqlalchemy import text  # noqa: E402

import main  # noqa: E402

INDIVIDUAL = 76561198042900100   # inside the public individual SteamID64 interval (the pool's id clause)
KEY_SQL = "SELECT pg_advisory_xact_lock(hashtext($1))"
BAN_SQL = ("INSERT INTO player_bans (steam_id, reason, banned_by_steam_id, banned_at, expires_at)"
           " VALUES ($1, 'r7', $2, NOW() - INTERVAL '1 hour', NOW() + INTERVAL '1 day')")


def _owner_text(fn, needle):
    """The SQL of the one text(...) call in fn's source whose argument holds
    needle, evaluated in main's namespace (the statement as the owner runs it)."""
    tree = ast.parse(textwrap.dedent(inspect.getsource(inspect.unwrap(fn))))
    hits = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and ast.unparse(n.func) == "text"
            and n.args and needle in ast.unparse(n.args[0])]
    assert len(hits) == 1, (fn.__name__, needle, len(hits))
    return eval(compile(ast.Expression(hits[0].args[0]), "<%s>" % fn.__name__, "eval"), dict(vars(main)))


LEASE_SQL = _owner_text(main.internal_pc_lease, "_PC_PORTRAIT_RESOLVE_COLS")
STEAM_WRITE_SQL = _owner_text(main._pc_steam_write, "AS eligible")
PORTRAIT_SQL = _owner_text(main.pc_portrait_upload, "AS banned")


async def _pool(db, q):
    r = (await db.execute(text("SELECT p.id FROM players p WHERE p.id = CAST(:pid AS uuid) AND "
                               + main._PC_POOL_MEMBER_SQL), {"pid": str(q.id)})).first()
    return "member" if r else "out"


async def _trade(db, q):
    parties = await main._pc_trade_parties(db, [str(q.id)])
    return main._pc_trade_party_refusal(parties.get(str(q.id)), True)


async def _lease(db, q):
    sub = (await db.execute(text(LEASE_SQL), {"pid": str(q.id)})).mappings().first()
    if sub is None or sub["subject_deleted"]:
        return (404, "not_found")
    return ("goes on", "subject_banned" if sub["subject_banned"] else "no ban")


async def _steam_write(db, q):
    row = (await db.execute(text(STEAM_WRITE_SQL), {"pid": str(q.id)})).mappings().first()
    if row is None or row["deleted"]:
        return "gone"
    return "eligible" if row["eligible"] else "ineligible"


async def _steam_claim(db, q):
    r = (await db.execute(text("SELECT p.id FROM players p WHERE p.id = CAST(:pid AS uuid) AND "
                               + main._PC_STEAM_ELIGIBLE_SQL), {"pid": str(q.id)})).first()
    return "claimable" if r else "out"


async def _portrait(db, q):
    row = (await db.execute(text(PORTRAIT_SQL), {"pid": str(q.id)})).mappings().first()
    return (403, "portrait_refused") if row is None or row["banned"] else ("goes on",)


async def _motion(db, q):
    row = (await db.execute(text(main._PC_MOTION_ROW_SQL), {"pid": str(q.id)})).mappings().first()
    return main._pc_motion_check(row, q.sid, {"static": None, "dance": None}, None)


OWNERS = {
    "_PC_POOL_MEMBER_SQL (internal_pc_card, the bot's cmd_pc_card, _pc_roll_prints, _pc_preview_read)": _pool,
    "_PC_TRADE_PARTY_SQL (_pc_trade_parties, _pc_trade_party_refusal)": _trade,
    "_pc_portrait_resolve_cols (internal_pc_lease)": _lease,
    "_PC_STEAM_ELIGIBLE_SQL (_pc_steam_write)": _steam_write,
    "_PC_STEAM_ELIGIBLE_SQL (_pc_steam_claim with ids)": _steam_claim,
    "pc_portrait_upload": _portrait,
    "_PC_MOTION_ROW_SQL (_pc_motion_check, pc_motion_upload phase C)": _motion,
}
STEPS = ("a", "b", "c", "d", "none")


@pytest.fixture(scope="module")
def answers():
    from inv_pg import case
    from test_mdpl_gate_reread_pg import _tombstone
    got = {}

    async def body(env):
        admin = (await env.player("R7 Admin")).sid
        await env.conn.execute("INSERT INTO admin_users (steam_id) VALUES ($1)", admin)
        kept = {}
        for n, step in enumerate("abcd"):
            p = await env.player("R7 Row %s" % step.upper())
            q = SimpleNamespace(id=p.id, sid=str(INDIVIDUAL + n))
            await env.conn.execute(
                "UPDATE players SET steam_id = $2, pc_trades_open = TRUE, mod_seen_at = NOW() - INTERVAL '400 days'"
                " WHERE id = $1", q.id, q.sid)
            if step in "ab":
                side = await env.side()
                await side.execute("BEGIN")
                await side.execute(KEY_SQL, q.sid)
                await _tombstone(side, q)
                await side.execute("COMMIT")
            if step in "bc":
                await env.conn.execute(BAN_SQL, q.sid, admin)
            kept[step] = q
        kept["none"] = SimpleNamespace(id=uuid.uuid4(), sid=str(INDIVIDUAL + 9))
        got["rows"] = {s: dict(await env.conn.fetchrow(
            "SELECT steam_id, deleted_at IS NOT NULL AS removed FROM players WHERE id = $1", q.id) or {})
            for s, q in kept.items()}
        for step in STEPS:
            got[step] = {}
            for name, fn in OWNERS.items():
                async with env.sm() as db:
                    got[step][name] = await fn(db, kept[step])
                    await db.rollback()
    with pytest.MonkeyPatch.context() as mp:
        case(mp, body, prefix="r7kept")
    for step in STEPS:
        for name in OWNERS:
            print("[V10] %-4s %-100s %r" % (step, name, got[step][name]))
    return got


def test_v10_the_rows_are_as_the_steps_say(answers):
    rows = answers["rows"]
    assert rows["a"]["removed"] and rows["b"]["removed"] and rows["a"]["steam_id"].startswith("deleted_"), rows
    assert not rows["c"]["removed"] and not rows["d"]["removed"] and rows["none"] == {}, rows


@pytest.mark.parametrize("name", list(OWNERS))
def test_v10_a_and_b_a_removed_row_is_answered_as_no_row(answers, name):
    assert answers["a"][name] == answers["none"][name], (name, answers["a"][name], answers["none"][name])
    assert answers["b"][name] == answers["none"][name], (name, answers["b"][name], answers["none"][name])


TODAY = {   # (c) the unchanged row under an active ban, (d) with none: today's answers, the code unchanged
    "_PC_POOL_MEMBER_SQL (internal_pc_card, the bot's cmd_pc_card, _pc_roll_prints, _pc_preview_read)": (
        "out", "member"),
    "_pc_portrait_resolve_cols (internal_pc_lease)": (("goes on", "subject_banned"), ("goes on", "no ban")),
    "_PC_STEAM_ELIGIBLE_SQL (_pc_steam_write)": ("ineligible", "eligible"),
    "_PC_STEAM_ELIGIBLE_SQL (_pc_steam_claim with ids)": ("out", "claimable"),
    "pc_portrait_upload": ((403, "portrait_refused"), ("goes on",)),
    "_PC_MOTION_ROW_SQL (_pc_motion_check, pc_motion_upload phase C)": (
        (403, {"error": "portrait_refused"}), (409, {"error": "motion_unbound"})),
}


@pytest.mark.parametrize("name", list(OWNERS))
def test_v10_c_and_d_an_unchanged_row_is_answered_as_today(answers, name):
    c, d = answers["c"][name], answers["d"][name]
    if name in TODAY:
        assert (c, d) == TODAY[name], (name, c, d)
    else:   # the trade party: banned is the permanent refusal no row gets; no ban is not that refusal
        assert c == ("not_eligible", True) == answers["none"][name] and d != c, (name, c, d)
    # a removed row is never answered as the unchanged row with no ban is
    assert answers["a"][name] != d, (name, answers["a"][name], d)


def test_v10_each_owner_reads_the_deletion_mark_beside_its_ban_word():
    """The reason the rows are one statement already, by their text: each
    statement names the deletion's mark on the row it reads the ban of, and
    each owner's decision refuses or leaves out the marked row."""
    ban = "player_bans b WHERE b.steam_id = p.steam_id AND " + main.player_ban_active_sql("b")
    assert "p.deleted_at IS NULL" in main._PC_POOL_MEMBER_SQL and ban in main._PC_POOL_MEMBER_SQL
    assert "(p.deleted_at IS NULL) AS live" in main._PC_TRADE_PARTY_SQL and ban in main._PC_TRADE_PARTY_SQL
    assert 'if row is None or not row["live"] or not row["not_banned"]:' in inspect.getsource(
        main._pc_trade_party_refusal)
    cols = main._pc_portrait_resolve_cols("p")
    assert "(p.deleted_at IS NOT NULL) AS subject_deleted" in cols and ban in cols and cols in LEASE_SQL
    assert 'if sub is None or sub["subject_deleted"]:' in inspect.getsource(main.internal_pc_lease)
    assert "(p.deleted_at IS NOT NULL) AS deleted" in STEAM_WRITE_SQL and main._PC_STEAM_ELIGIBLE_SQL in STEAM_WRITE_SQL
    write_src = inspect.getsource(main._pc_steam_write)
    assert 'if row is None or row["deleted"]:\n        return "gone"' in write_src.replace("\r\n", "\n")
    assert "p.deleted_at IS NULL" in main._PC_STEAM_ELIGIBLE_SQL and ban in main._PC_STEAM_ELIGIBLE_SQL
    assert "where = _PC_STEAM_ELIGIBLE_SQL + " in inspect.getsource(main._pc_steam_claim)
    assert "WHERE p.id = CAST(:pid AS uuid) AND p.deleted_at IS NULL" in PORTRAIT_SQL and ban in PORTRAIT_SQL
    assert 'if row is None or row["banned"]:' in inspect.getsource(main.pc_portrait_upload)
    assert "WHERE p.id = CAST(:pid AS uuid) AND p.deleted_at IS NULL" in main._PC_MOTION_ROW_SQL
    assert ban in main._PC_MOTION_ROW_SQL
    assert 'if row is None or row["banned"]:' in inspect.getsource(main._pc_motion_check)
    card = inspect.getsource(main.internal_pc_card).replace("\r\n", "\n")
    assert 'AND """ + _PC_POOL_MEMBER_SQL + """' in card and 'detail={"error": "not_in_pool"}' in card
    with open(os.path.join(HERE, "..", "discord_bot.py"), encoding="utf-8") as fh:
        bot = fh.read()
    start = bot.index("async def cmd_pc_card(")
    body = bot[start:bot.index("\n\n\n", start)]
    assert 'status == 404 and d.get("error") == "not_linked"' in body and "not in the current card pool" in body
