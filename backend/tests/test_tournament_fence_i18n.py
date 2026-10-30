"""The tournament fence re-author's i18n delta: migration 393 and the bundled
catalogue (plugin/I18nCatalogues.cs).

Four client strings change with the fence: two new toasts ("Tournament info
is refreshing - try again in a moment" from the painted-snapshot click fence,
"Couldn't leave the tournament - it may have locked or started" from a
refused leave, replacing the bare "Failed") and the two tournament rulebook
bodies, re-keyed because one bullet in each now names the availability-check
DM as the post-lock way out.

What is pinned here:
  * 393's four key rows are exactly what tools/i18n_sync_keys.build_client_keys
    derives from the regenerated tools/i18n_source.json (id, source, hash,
    sensitivity, context), so the migration and the next key sync write the
    same row;
  * 393 is one explicit transaction whose literals are single-line E''
    strings (the stored text cannot depend on the applying checkout's line
    endings);
  * 393 seeds exactly the two toasts in es/ru/uk/sv, with the bundled
    catalogue's own drafts;
  * the bundled catalogue - what players see (#583) - covers all four keys in
    every locale, ANCHORED on the exact key with a short-key control and a
    positive control (#680), and no superseded body key survives;
  * every new or changed catalogue entry passes main._i18n_validate, the
    server's submit/approve validator (with a negative control);
  * 393 and rollback_393 set lock_timeout, idle_in_transaction_session_timeout
    and statement_timeout as the three statements right after BEGIN, before
    anything reads, locks or writes (FENCE-R1 H4);
  * on PostgreSQL (SCR_MIGRATION_TEST_PG_DSN, fail-not-skip like
    test_migration_reruns.py): 393 applied twice on the real i18n tables
    (181 + 212) writes no row on its second run, measured by value AND xmin,
    and each post-check RAISES with nothing committed when its condition
    fails; a transaction holding one fence key row makes 393 fail with
    lock_not_available at its 5 s bound instead of waiting for the holder;
    rollback_393 retires the four keys, supersedes their pending proposals
    and writes nothing on a second run.
"""
import asyncio
import hashlib
import io
import json
import os
import re
import sys
import time
import uuid

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(REPO, "tools"))
sys.path.insert(0, os.path.join(REPO, "backend", "api"))
sys.path.insert(0, HERE)

import i18n_sync_keys  # noqa: E402

try:
    import asyncpg
except ImportError:                                    # pragma: no cover
    asyncpg = None

SQL_DIR = os.path.join(REPO, "backend", "sql")
M393 = os.path.join(SQL_DIR, "393_i18n_tournament_fence_strings.sql")
R393 = os.path.join(SQL_DIR, "rollback_393_i18n_tournament_fence_strings.sql")
M181 = os.path.join(SQL_DIR, "181_i18n_infrastructure.sql")
M212 = os.path.join(SQL_DIR, "212_i18n_key_context.sql")
CATALOGUE = os.path.join(REPO, "plugin", "I18nCatalogues.cs")
SOURCE = os.path.join(REPO, "tools", "i18n_source.json")

TOAST_REFRESH = "Tournament info is refreshing - try again in a moment"
TOAST_LEAVE = "Couldn't leave the tournament - it may have locked or started"
BODY_HOW = "Tournaments are 8-16 player double-elimination brackets"
BODY_FORF = "What happens when someone doesn't show up, quits, or leaves a tournament"
LOCALES = {"ES": "es", "RU": "ru", "UK": "uk", "SV": "sv"}

DSN_VAR = "SCR_MIGRATION_TEST_PG_DSN"
OPTOUT_VAR = "SCR_MIGRATION_TEST_PG_OPTOUT"
DSN = (os.environ.get(DSN_VAR) or "").replace("postgresql+asyncpg://", "postgresql://")
OPTOUT = os.environ.get(OPTOUT_VAR) == "1"


def _read(p):
    return io.open(p, encoding="utf-8").read()


def _source_strings():
    return json.load(io.open(SOURCE, encoding="utf-8"))["strings"]


def _fence_keys():
    """The four fence strings as the key sync derives them, by source text."""
    rows = {r["msgctxt"]: r for r in i18n_sync_keys.build_client_keys(
        json.load(io.open(SOURCE, encoding="utf-8")))}
    out = {}
    for name, prefix, exact in (("leave", TOAST_LEAVE, True), ("refresh", TOAST_REFRESH, True),
                                ("how", BODY_HOW, False), ("forf", BODY_FORF, False)):
        hits = [k for k in rows if (k == prefix if exact else k.startswith(prefix))]
        assert len(hits) == 1, (name, len(hits))
        out[name] = rows[hits[0]]
    return out


# -- SQL literal parsing --------------------------------------------------------

_E = r"E'((?:[^'\\]|\\.)*)'"
_KEY_ROW = re.compile(r"^\(E'([0-9a-f]{16})', 'client', " + _E + r", E'([0-9a-f]{40})', (TRUE|FALSE), "
                      r"CAST\(" + _E + r" AS VARCHAR\(160\)\)\),?$", re.M)
_SEED_ROW = re.compile(r"\(E'([0-9a-f]{16})', '(es|ru|uk|sv)', E'([0-9a-f]{40})', " + _E + r"\)")


def _e_unescape(s):
    out, i = [], 0
    while i < len(s):
        if s[i] == "\\":
            out.append({"n": "\n", "r": "\r", "t": "\t", "\\": "\\", "'": "'"}[s[i + 1]])
            i += 2
        else:
            out.append(s[i])
            i += 1
    return "".join(out)


# -- C# catalogue parsing ---------------------------------------------------------

_LIT = r'"((?:[^"\\]|\\.)*)"'
_ENTRY = re.compile(r'^\s*\[' + _LIT + r'\]\s*=\s*' + _LIT + r',\s*$')


def _cs_unescape(s):
    out, i = [], 0
    while i < len(s):
        if s[i] == "\\":
            n = s[i + 1]
            if n == "u":
                out.append(chr(int(s[i + 2:i + 6], 16)))
                i += 6
                continue
            out.append({"n": "\n", "r": "\r", "t": "\t", "\\": "\\", '"': '"', "'": "'", "0": "\0"}[n])
            i += 2
        else:
            out.append(s[i])
            i += 1
    return "".join(out)


def _catalogue():
    dicts, cur = {}, None
    for ln in _read(CATALOGUE).splitlines():
        m = re.search(r"Dictionary<string, string> (ES|RU|UK|SV) =", ln)
        if m:
            cur = m.group(1)
            dicts[cur] = {}
            continue
        if cur and ln.strip() == "};":
            cur = None
            continue
        if cur:
            e = _ENTRY.match(ln)
            if e:
                dicts[cur][_cs_unescape(e.group(1))] = _cs_unescape(e.group(2))
    assert sorted(dicts) == sorted(LOCALES), sorted(dicts)
    return dicts


# -- static checks ------------------------------------------------------------------

def test_393_keys_are_the_extracted_source_keys():
    keys = _fence_keys()
    rows = _KEY_ROW.findall(_read(M393))
    assert len(rows) == 4, len(rows)
    got = {}
    for key_id, src, h, sensitive, ctx in rows:
        src = _e_unescape(src)
        assert hashlib.sha1(("client\0" + src).encode("utf-8")).hexdigest()[:16] == key_id, src[:40]
        assert hashlib.sha1(src.encode("utf-8")).hexdigest() == h, src[:40]
        got[key_id] = (src, h, sensitive == "TRUE", _e_unescape(ctx))
    want = {r["key_id"]: (r["msgctxt"], r["source_hash"], r["sensitive"], r["context"])
            for r in keys.values()}
    assert got == want
    # The re-keyed bodies carry the corrected bullets.
    assert "answering <b>No</b> on the bot's availability-check DM" in keys["how"]["msgctxt"]
    assert "you can't un-sign at all" in keys["how"]["msgctxt"]
    assert "If you have no answerable DM left, you're expected to show" in keys["forf"]["msgctxt"]
    assert "Failed" not in _source_strings()


def test_393_is_one_transaction_with_single_line_literals():
    sql = _read(M393)
    body = [ln for ln in sql.splitlines() if ln.strip() and not ln.lstrip().startswith("--")]
    assert body[0] == "BEGIN;" and body[-1] == "COMMIT;"
    assert sql.count("BEGIN;") == 1 and sql.count("COMMIT;") == 1
    assert "NOW()" not in sql.upper().replace(" ", "")
    assert "$k" not in sql, "dollar-quoted multi-line literals carry the checkout's line endings"
    for ln in body:
        # every E'' literal opens and closes on its own line
        stripped = re.sub(_E, "", ln)
        stripped = re.sub(r"'[^'\n]*'", "", stripped)
        assert "'" not in stripped, ln[:120]


BOUNDS = ("SET LOCAL lock_timeout = '5s';",
          "SET LOCAL idle_in_transaction_session_timeout = '5s';",
          "SET LOCAL statement_timeout = '30s';")


@pytest.mark.parametrize("path", [M393, R393], ids=["393", "rollback_393"])
def test_393_and_its_rollback_set_their_bounds_before_anything_runs(path):
    """FENCE-R1 H4: the three bounds are the three statements right after
    BEGIN, so no read, lock or write precedes them; each is set once and
    nothing later names the same settings; the file is one transaction."""
    body = [ln.strip() for ln in _read(path).splitlines()
            if ln.strip() and not ln.lstrip().startswith("--")]
    assert body[0] == "BEGIN;" and body[-1] == "COMMIT;", (body[0], body[-1])
    assert body.count("BEGIN;") == 1 and body.count("COMMIT;") == 1
    assert tuple(body[1:4]) == BOUNDS, body[1:4]
    later = [ln for ln in body[4:] if re.search(
        r"(?i)\b(lock_timeout|idle_in_transaction_session_timeout|statement_timeout)\b", ln)]
    assert later == [], later


def test_393_seeds_are_the_bundled_toast_drafts():
    keys = _fence_keys()
    cat = _catalogue()
    seeds = _SEED_ROW.findall(_read(M393))
    assert len(seeds) == 8
    pairs = set()
    for key_id, lang, h, target in seeds:
        row = next(r for r in keys.values() if r["key_id"] == key_id)
        assert row["msgctxt"] in (TOAST_LEAVE, TOAST_REFRESH), row["msgctxt"][:40]
        assert h == row["source_hash"]
        loc = next(k for k, v in LOCALES.items() if v == lang)
        assert _e_unescape(target) == cat[loc][row["msgctxt"]], (lang, row["msgctxt"])
        pairs.add((key_id, lang))
    assert pairs == {(keys[n]["key_id"], lang) for n in ("leave", "refresh") for lang in LOCALES.values()}


def test_catalogue_covers_the_fence_keys_in_every_locale():
    strings = set(_source_strings())
    fence = [r["msgctxt"] for r in _fence_keys().values()]
    cat = _catalogue()
    for loc, d in cat.items():
        for src in fence:
            assert src in d, (loc, src[:50])
        stale = [k for k in d if k.startswith((BODY_HOW, BODY_FORF)) and k not in strings]
        assert not stale, (loc, "a superseded tournament body key survived")
        # positive control: an existing short key is found by the same lookup
        assert "Not now" in d, loc
        # short-key control: a prefix of a new key is NOT reported as covered
        assert "Tournament info" not in d, loc


def test_catalogue_entries_pass_the_server_validator():
    import main
    cat = _catalogue()
    checked = 0
    for loc, lang in LOCALES.items():
        for row in _fence_keys().values():
            errs = main._i18n_validate(row["msgctxt"], cat[loc][row["msgctxt"]], lang)
            assert errs == [], (loc, row["msgctxt"][:40], errs)
            checked += 1
    assert checked == 16
    # negative control: the same validator refuses a dropped tag
    assert main._i18n_validate("answering <b>No</b> on the DM", "respondiendo No en el DM", "es")


# -- PostgreSQL: applied twice, and each post-check refuses ----------------------------

@pytest.fixture
def live_pg():
    if DSN and asyncpg is not None:
        return DSN
    if OPTOUT:
        pytest.skip("%s is unset and %s=1: 393's live coverage deliberately waived." % (DSN_VAR, OPTOUT_VAR))
    pytest.fail("%s is unset (or asyncpg is missing), so migration 393 was never applied. Point it at "
                "a throwaway cluster, or set %s=1 to waive the coverage deliberately." % (DSN_VAR, OPTOUT_VAR))


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def test_393_applied_twice_writes_nothing_and_its_post_checks_raise(live_pg):
    from test_migration_reruns import _changed, _fingerprint
    keys = _fence_keys()
    key_ids = sorted(r["key_id"] for r in keys.values())
    sql = _read(M393)
    tables = ("i18n_keys", "i18n_proposals")

    async def live_keys(conn):
        return await conn.fetch(
            "SELECT key_id, msgctxt, source_hash, sensitive, context FROM i18n_keys"
            " WHERE key_id = ANY($1::text[]) AND retired_at IS NULL AND max_px IS NULL"
            "   AND namespace = 'client' ORDER BY key_id", key_ids)

    async def pending(conn):
        return await conn.fetchval(
            "SELECT count(*) FROM i18n_proposals WHERE key_id = ANY($1::text[])"
            "   AND proposer_steam_id = 'claude-mt' AND status = 'pending'", key_ids)

    async def go():
        schema = "f393_" + uuid.uuid4().hex[:10]
        conn = await asyncpg.connect(live_pg)
        try:
            await conn.execute('CREATE SCHEMA "%s"' % schema)
            await conn.execute('SET search_path TO "%s"' % schema)
            await conn.execute(_read(M181))
            await conn.execute(_read(M212))

            await conn.execute(sql)
            rows = await live_keys(conn)
            assert len(rows) == 4
            for r in rows:
                want = next(k for k in keys.values() if k["key_id"] == r["key_id"])
                assert r["msgctxt"] == want["msgctxt"] and "\r" not in r["msgctxt"]
                assert hashlib.sha1(r["msgctxt"].encode("utf-8")).hexdigest() == r["source_hash"]
                assert (r["sensitive"], r["context"]) == (want["sensitive"], want["context"])
            assert await pending(conn) == 8

            first = await _fingerprint(conn, tables)
            await conn.execute(sql)
            second = await _fingerprint(conn, tables)
            assert _changed(first, second) == 0, "a second run of 393 wrote a row"
            assert first == second

            # Key post-check: retire one key and run a copy whose INSERT omits
            # it - the post-check RAISES "3 of 4" and nothing is committed;
            # the real file then revives the key.
            leave = keys["leave"]["key_id"]
            line = next(ln for ln in sql.splitlines(True) if ln.startswith("(E'%s', 'client'" % leave))
            gap = sql.replace(line, "", 1)
            assert gap.count(leave) == sql.count(leave) - 1
            # the removed row may have been the last in the VALUES list; keep
            # the list well-formed either way
            gap = re.sub(r",\n(\s*\) AS v\(key_id)", r"\n\1", gap)
            await conn.execute("UPDATE i18n_keys SET retired_at = clock_timestamp() WHERE key_id = $1", leave)
            with pytest.raises(asyncpg.exceptions.RaiseError, match="3 of 4"):
                await conn.execute(gap)
            await conn.execute("ROLLBACK")
            assert len(await live_keys(conn)) == 3
            await conn.execute(sql)
            assert len(await live_keys(conn)) == 4

            # Seed post-check: with the proposals gone, a copy without the
            # proposal INSERT RAISES "8 of 8"; the real file re-seeds all 8.
            await conn.execute("DELETE FROM i18n_proposals WHERE key_id = ANY($1::text[])", key_ids)
            head, sep, tail = sql.partition("INSERT INTO i18n_proposals")
            assert sep
            no_seed = head + tail.split(";", 1)[1]
            with pytest.raises(asyncpg.exceptions.RaiseError, match="8 of 8 seed pairs"):
                await conn.execute(no_seed)
            await conn.execute("ROLLBACK")
            assert await pending(conn) == 0
            await conn.execute(sql)
            assert await pending(conn) == 8
        finally:
            try:
                await conn.execute('DROP SCHEMA IF EXISTS "%s" CASCADE' % schema)
            finally:
                await conn.close()
    _run(go())


async def _fresh_i18n(dsn):
    """A connection whose search_path is a new throwaway schema holding the
    real i18n tables (181 + 212). Returns (conn, schema)."""
    schema = "f393_" + uuid.uuid4().hex[:10]
    conn = await asyncpg.connect(dsn)
    try:
        await conn.execute('CREATE SCHEMA "%s"' % schema)
        await conn.execute('SET search_path TO "%s"' % schema)
        await conn.execute(_read(M181))
        await conn.execute(_read(M212))
    except BaseException:
        await _drop(dsn, schema, conn)
        raise
    return conn, schema


async def _drop(dsn, schema, *conns):
    """Close every connection first (terminate: one may sit in an aborted
    transaction that would block the DROP), then drop the schema from a fresh one."""
    for c in conns:
        if c is not None and not c.is_closed():
            c.terminate()
    conn = await asyncpg.connect(dsn)
    try:
        await conn.execute('DROP SCHEMA IF EXISTS "%s" CASCADE' % schema)
    finally:
        await conn.close()


def test_393_gives_up_on_a_held_key_row_at_its_lock_bound(live_pg):
    """FENCE-R1 H4, live: another transaction holds one fence key row FOR
    UPDATE, so 393's key upsert has to wait for it. With the bounds the run
    fails with lock_not_available (55P03, the lock_timeout's own SQLSTATE,
    not statement_timeout's 57014) after about 5 s, and nothing is committed.
    Without them it waits for as long as the holder holds, and this test's own
    20 s cap fails it. This is one held row, so it proves the bound on a single
    wait - the claim the file makes - not a bound on the sum of waits (#689)."""
    leave = _fence_keys()["leave"]["key_id"]
    sql = _read(M393)

    async def go():
        runner, schema = await _fresh_i18n(live_pg)
        holder = None
        try:
            await runner.execute(sql)
            # a run that got past the held row would re-seed these four
            refresh = _fence_keys()["refresh"]["key_id"]
            await runner.execute("DELETE FROM i18n_proposals WHERE key_id = $1", refresh)
            holder = await asyncpg.connect(live_pg)
            await holder.execute('SET search_path TO "%s"' % schema)
            await holder.execute("BEGIN")
            await holder.execute("SELECT 1 FROM i18n_keys WHERE key_id = $1 FOR UPDATE", leave)
            t0 = time.monotonic()
            with pytest.raises(asyncpg.exceptions.LockNotAvailableError):
                await asyncio.wait_for(runner.execute(sql), timeout=20)
            waited = time.monotonic() - t0
            assert 4.0 <= waited < 15.0, waited
            await runner.execute("ROLLBACK")
            await holder.execute("ROLLBACK")
            assert await runner.fetchval(
                "SELECT count(*) FROM i18n_proposals WHERE key_id = $1", refresh) == 0
        finally:
            await _drop(live_pg, schema, runner, holder)
    _run(go())


def test_rollback_393_retires_the_keys_supersedes_their_pending_and_reruns_clean(live_pg):
    """rollback_393 retires exactly the four fence keys (never deletes them),
    decides every pending proposal on them 'superseded', leaves an unrelated
    key and its pending proposal alone, and writes no row on a second run."""
    from test_migration_reruns import _changed, _fingerprint
    keys = _fence_keys()
    key_ids = sorted(r["key_id"] for r in keys.values())

    async def go():
        conn, schema = await _fresh_i18n(live_pg)
        try:
            await conn.execute(_read(M393))
            other = "0123456789abcdef"
            await conn.execute(
                "INSERT INTO i18n_keys (key_id, namespace, msgctxt, source_hash, sensitive, updated_at)"
                " VALUES ($1, 'client', 'An unrelated string', $2, FALSE, clock_timestamp())",
                other, hashlib.sha1(b"An unrelated string").hexdigest())
            await conn.execute(
                "INSERT INTO i18n_proposals (key_id, language_code, source_hash, proposed_target,"
                " proposer_steam_id, status) VALUES ($1, 'es', $2, 'Una cadena', 'reviewer-test', 'pending')",
                other, hashlib.sha1(b"An unrelated string").hexdigest())
            assert await conn.fetchval(
                "SELECT count(*) FROM i18n_proposals WHERE key_id = ANY($1::text[]) AND status = 'pending'",
                key_ids) == 8

            await conn.execute(_read(R393))
            rows = await conn.fetch("SELECT key_id, retired_at FROM i18n_keys ORDER BY key_id")
            assert {r["key_id"] for r in rows} == set(key_ids) | {other}
            assert all((r["retired_at"] is not None) == (r["key_id"] in key_ids) for r in rows)
            assert await conn.fetchval(
                "SELECT count(*) FROM i18n_proposals WHERE key_id = ANY($1::text[])"
                "   AND status = 'superseded' AND review_note = 'key retired by rollback_393'",
                key_ids) == 8
            assert await conn.fetchval(
                "SELECT status FROM i18n_proposals WHERE key_id = $1", other) == "pending"

            first = await _fingerprint(conn, ("i18n_keys", "i18n_proposals"))
            await conn.execute(_read(R393))
            second = await _fingerprint(conn, ("i18n_keys", "i18n_proposals"))
            assert _changed(first, second) == 0, "a second run of rollback_393 wrote a row"
        finally:
            await _drop(live_pg, schema, conn)
    _run(go())
