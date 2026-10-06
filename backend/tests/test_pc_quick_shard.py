"""Item 18, shard on the fly in the card pull tab.

The pull strip's five tiles carry the binder's action row, and their Discard
shards that ONE card through the batch shard's route (board row 25,
POST /api/v1/pc/prints/discard-batch) with a one-print body, keyed by a nonce
kept for that card until an answer arrives. No new route, no new migration:
the route serves the single-card case as it is, which the database half below
proves against a real PostgreSQL with the batch shard's own harness.

Required behaviour, each a named test:
  Q1  a card in the pull tab can be sharded in place with one confirmed
      action: the strip's Discard is wired to the one-card shard, which asks
      first (ShardConfirmed) and sends on the second click;
  Q2  the server performs it as one transaction with the credit as a delta,
      and a repeated request with the same key pays nothing (the client keeps
      the key until an answer arrives, so its retry IS that request);
  Q3  it refuses a card the player does not own or has already sharded,
      changing nothing;
  Q4  the client never shows a balance the server did not send: the balance
      is written only from an answer's top-level "shards", the stamp only
      from a success;
  Q5  a failed or unanswered request changes nothing on screen and reads the
      collection and balance back (PcQuickShardRules.ReadBackAfter, executed
      in the client rules harness), the given-up latch included;
  Q6  one shard is ONE request: the route is called once per confirmed click,
      never in a loop, never retried by itself;
  Q7  the shard writes only card rows, the shard balance and the key's row:
      no match, series or rating table is touched.

Each client gate runs on the real sources and, with its mutation and control,
on edited copies (#391). The database tests use test_pc_shard_batch's harness
(PC_SHARD_TEST_PG_DSN; without it they FAIL by name, see that module).

    PC_SHARD_TEST_PG_DSN="postgresql://postgres@127.0.0.1:55432/asksb_cards" \\
        python -m pytest backend/tests/test_pc_quick_shard.py -q
"""
import re
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from test_pc_shard_batch import (  # noqa: E402,F401  (pg_build and env are fixtures)
    _batch, _batches, _discarded, _err, _flat, _key, _pc, _player, _print, _scenario, _shards, _single,
    env, pg_build,
)

ROOT = Path(__file__).resolve().parents[2]
PLUGIN = ROOT / "plugin"
FILES = {
    "ui": PLUGIN / "PlayerCardsUI.cs",
    "api": PLUGIN / "ApiClient.cs",
    "rules": PLUGIN / "PcQuickShardRules.cs",
}
_CACHE = {}


def _sources():
    if not _CACHE:
        for k, p in FILES.items():
            _CACHE[k] = p.read_text(encoding="utf-8")
    return dict(_CACHE)


_MEMBER = re.compile(r"\n        (?:///|\[|(?:private|internal|public|protected)\s)")


def _member(src, signature):
    n = src.count(signature)
    assert n == 1, "%r occurs %d times" % (signature, n)
    i = src.index(signature)
    m = _MEMBER.search(src, i + len(signature))
    return src[i:m.start() if m else len(src)]


def _at(text, needle, what):
    assert needle in text, what
    return text.index(needle)


def _code(cs):
    """C# text without // comments, so prose never satisfies a gate."""
    return "\n".join(re.sub(r"//.*$", "", line) for line in cs.splitlines())


# ---------------------------------------------------------------- the gates

def gate_q1_the_strip_card_shards_in_place_on_a_confirmed_click(s):
    ui = s["ui"]
    build = _code(_member(ui, "private static void BuildOpenView("))
    assert build.count("CreateTile(lastStrip.transform,") == 1, "the strip's tiles are built more than once"
    assert 'CreateTile(lastStrip.transform, "PcRv" + i, true, true)' in build, (
        "the strip's tiles are not built with the action row on the quick surface")
    binder = _code(_member(ui, "private static void BuildBinderView("))
    assert 'CreateTile(row.transform, $"PcB{r}_{k}", true);' in binder, "the binder's tiles changed surface"
    tile = _code(_member(ui, "private static Tile CreateTile("))
    assert "t.quickSurface = quickSurface;" in tile, "the tile does not carry its surface"
    assert "quickSurface ? (UnityEngine.Events.UnityAction)(() => OnQuickShardClick(tile)) : () => OnDiscardClick(tile, false)" in tile, (
        "the strip's Discard is not the one-card shard")
    q = _code(_member(ui, "private static void OnQuickShardClick("))
    arm = _at(q, "if (!ShardConfirmed(set))", "the strip card no longer asks first")
    send = _at(q, "SendShard(id, quickKey, ids, null, p.print_id);", "the strip card is not sent as a one-card shard")
    assert arm < send, "the strip card is sent before it is confirmed"
    assert "string set = PcQuickShardRules.ArmSet(p.print_id);" in q, "the arm is not the card's own set"


def gate_q2_the_key_is_kept_for_the_card_until_an_answer(s):
    ui = s["ui"]
    q = _code(_member(ui, "private static void OnQuickShardClick("))
    assert "if (quickKeyFor != set || string.IsNullOrEmpty(quickKey)) { quickKey = NewNonce(); quickKeyFor = set; }" in q, (
        "the strip card's nonce is not kept for that card")
    assert q.count("NewNonce()") == 1, "the strip card draws a fresh nonce on every click"
    fail = _code(_member(ui, "private static void FailShard("))
    assert "if (!PcQuickShardRules.KeepKeyAfter(code)) { quickKey = null; quickKeyFor = null; }" in fail, (
        "a refused strip shard drops its key outside the rule")
    send = _code(_member(ui, "private static void SendShard("))
    assert "ApiClient.PcDiscardBatch(id, key, ids," in send, "the one-card shard is not the batch route"


def gate_q4_the_balance_and_the_stamp_come_only_from_an_answer(s):
    ui = s["ui"]
    q = _code(_member(ui, "private static void OnQuickShardClick("))
    for forbidden in ("CachedPcMe", "HistoryMarkDiscarded(", "RemoveAll(", ".discarded =", "discard_shards"):
        assert forbidden not in q, "the click changes the screen before the server answers (%s)" % forbidden
    fail = _code(_member(ui, "private static void FailShard("))
    quick = fail[:_at(fail, "switch (code)", "FailShard lost its switch")]
    for forbidden in ("CachedPcMe", "HistoryMarkDiscarded(", "prints.RemoveAll("):
        assert forbidden not in quick, "a refused strip shard changes the screen (%s)" % forbidden
    api = _code(_member(s["api"], "public static void PcDiscardBatch("))
    assert 'if (ok && epoch == _pcCacheEpoch && CachedPcMe != null)' in api, (
        "the balance is written from an answer that is not a success")
    assert 'string sh = PcTopLevel(resp, "shards");' in api, "the balance is not the answer's top-level shards"


def gate_q5_a_failure_reads_back_by_the_rule(s):
    ui = s["ui"]
    fail = _code(_member(ui, "private static void FailShard("))
    quick = fail[:_at(fail, "switch (code)", "FailShard lost its switch")]
    assert ("if (PcQuickShardRules.ReadBackAfter(code) && id != null) "
            "{ ApiClient.FetchPcCollection(id, true); ApiClient.FetchPcMe(id, true); }") in quick, (
        "a refused strip shard does not read back by the rule")
    assert quick.rstrip().endswith("return;\n            }"), "a refused strip shard falls through to the batch path"
    tick = _code(_member(ui, "internal static void MaybeTick("))
    assert 'if (PcQuickShardRules.ReadBackAfter("given_up")) { ApiClient.FetchPcCollection(id, true); ApiClient.FetchPcMe(id, true); }' in tick, (
        "a strip shard given up does not read back")


def gate_q6_one_request_per_shard(s):
    ui = s["ui"]
    q = _code(_member(ui, "private static void OnQuickShardClick("))
    assert q.count("SendShard(") == 1, "a confirmed click sends more than once"
    for loop in ("for (", "foreach (", "while (", "StartCoroutine("):
        assert loop not in q, "the strip card's click loops or schedules (%s)" % loop
    assert "PcDiscard(" not in q and "OnDiscardClick(" not in q, "the strip card reaches the one-request-per-copy loop"
    send = _code(_member(ui, "private static void SendShard("))
    assert send.count("ApiClient.PcDiscardBatch(") == 1, "one shard sends more than one request"
    assert "SendShard(" not in send.split("ApiClient.PcDiscardBatch(", 1)[1], "an answer sends again"
    rules = _code(s["rules"])
    assert 'case "rate_limited":' in rules, "the rate limit is not named by the read-back rule"


GATES = [gate_q1_the_strip_card_shards_in_place_on_a_confirmed_click,
         gate_q2_the_key_is_kept_for_the_card_until_an_answer,
         gate_q4_the_balance_and_the_stamp_come_only_from_an_answer,
         gate_q5_a_failure_reads_back_by_the_rule,
         gate_q6_one_request_per_shard]


@pytest.mark.parametrize("gate", GATES, ids=[g.__name__ for g in GATES])
def test_the_gate_holds_on_the_real_sources(gate):
    gate(_sources())


# (id, gate, source key, search text, mutant, control, the named assertion the
# mutant must turn red). Every control is an edit at the same site that
# changes no behaviour.
MUTATIONS = [
    ("Q1a", gate_q1_the_strip_card_shards_in_place_on_a_confirmed_click, "ui",
     'CreateTile(lastStrip.transform, "PcRv" + i, true, true)',
     'CreateTile(lastStrip.transform, "PcRv" + i, false)',
     'CreateTile(lastStrip.transform, "PcRv" + i, true, true) ',
     "the strip's tiles are not built with the action row on the quick surface"),
    ("Q1b", gate_q1_the_strip_card_shards_in_place_on_a_confirmed_click, "ui",
     "            if (!ShardConfirmed(set))\n            {\n                int traded;",
     "            if (false)\n            {\n                int traded;",
     "            if (!ShardConfirmed(set))   // the first click asks\n            {\n                int traded;",
     "the strip card no longer asks first"),
    ("Q2a", gate_q2_the_key_is_kept_for_the_card_until_an_answer, "ui",
     "            SendShard(id, quickKey, ids, null, p.print_id);",
     "            SendShard(id, quickKey = NewNonce(), ids, null, p.print_id);",
     "            SendShard(id, quickKey, ids, null, p.print_id);   // the kept key",
     "the strip card draws a fresh nonce on every click"),
    ("Q4a", gate_q4_the_balance_and_the_stamp_come_only_from_an_answer, "ui",
     "            if (quickKeyFor != set || string.IsNullOrEmpty(quickKey)) { quickKey = NewNonce(); quickKeyFor = set; }\n",
     "            if (quickKeyFor != set || string.IsNullOrEmpty(quickKey)) { quickKey = NewNonce(); quickKeyFor = set; }\n"
     "            HistoryMarkDiscarded(p.print_id, value0);\n",
     "            if (quickKeyFor != set || string.IsNullOrEmpty(quickKey)) { quickKey = NewNonce(); quickKeyFor = set; }   // kept\n",
     "the click changes the screen before the server answers"),
    ("Q5a", gate_q5_a_failure_reads_back_by_the_rule, "ui",
     "if (PcQuickShardRules.ReadBackAfter(code) && id != null) { ApiClient.FetchPcCollection(id, true); ApiClient.FetchPcMe(id, true); }",
     "if (false && id != null) { ApiClient.FetchPcCollection(id, true); ApiClient.FetchPcMe(id, true); }",
     "if (PcQuickShardRules.ReadBackAfter(code) && id != null) { ApiClient.FetchPcCollection(id, true); ApiClient.FetchPcMe(id, true); }  ",
     "a refused strip shard does not read back by the rule"),
    ("Q5b", gate_q5_a_failure_reads_back_by_the_rule, "ui",
     'if (PcQuickShardRules.ReadBackAfter("given_up")) { ApiClient.FetchPcCollection(id, true); ApiClient.FetchPcMe(id, true); }',
     "{ }",
     'if (PcQuickShardRules.ReadBackAfter("given_up")) { ApiClient.FetchPcCollection(id, true); ApiClient.FetchPcMe(id, true); }  ',
     "a strip shard given up does not read back"),
    ("Q6a", gate_q6_one_request_per_shard, "ui",
     "            SendShard(id, quickKey, ids, null, p.print_id);",
     "            foreach (var x in ids) SendShard(id, quickKey, new List<string> { x }, null, p.print_id);",
     "            SendShard(id, quickKey, ids, null, p.print_id);   // one request",
     "the strip card's click loops or schedules"),
    ("Q6c", gate_q6_one_request_per_shard, "ui",
     "            SendShard(id, quickKey, ids, null, p.print_id);",
     "            SendShard(id, quickKey, ids, null, p.print_id);\n            SendShard(id, quickKey, ids, null, p.print_id);",
     "            SendShard(id, quickKey, ids, null, p.print_id);   // once",
     "a confirmed click sends more than once"),
    ("Q6b", gate_q6_one_request_per_shard, "ui",
     "                else FailShard(id, resp, packId, quickPrintId != null);",
     "                else { FailShard(id, resp, packId, quickPrintId != null); SendShard(id, key, ids, packId, quickPrintId); }",
     "                else FailShard(id, resp, packId, quickPrintId != null);   // never sent again",
     "an answer sends again"),
]


def _edited(src, old, new):
    n = src.count(old)
    assert n == 1, "the search text occurs %d times: %r" % (n, old[:80])
    return src.replace(old, new)


@pytest.mark.parametrize("mid,gate,key,old,mutant,control,named", MUTATIONS, ids=[m[0] for m in MUTATIONS])
def test_each_gate_is_red_under_its_mutation_and_green_under_its_control(mid, gate, key, old, mutant, control, named):
    s = _sources()
    red = dict(s, **{key: _edited(s[key], old, mutant)})
    assert red[key] != s[key], mid + ": the mutation did not apply"
    with pytest.raises(AssertionError, match=re.escape(named)):
        gate(red)
    green = dict(s, **{key: _edited(s[key], old, control)})
    assert green[key] != s[key], mid + ": the control did not apply"
    gate(green)


# ============================================== the server half (live database)

_NOT_TOUCHED = ("ranked_series", "matches", "rating_history", "glicko", "current_rating",
                "rating_deviation", "gold", "series")


def test_q2_one_card_is_one_transaction_with_the_credit_as_one_delta(env):
    """One print, as the strip sends it: paid at its rarity, the balance and
    the answer carry the credit, the key's row records it, and the credit is
    ONE delta statement (#326)."""
    async def body(ctx):
        me = await _player(1, shards=11)
        subject = await _player(2)
        card = await _print(me, subject, "epic")
        k = _key()
        status, ans = await _batch(ctx, "one", me, k, [card])
        assert status == 200, ans
        assert (ans["prints"], ans["shards_gained"], ans["shards"], ans["replayed"]) == (1, 150, 161, False)
        assert await _shards(me) == 161
        assert (await _discarded([card]))[card] == (True, 150)
        assert await _batches(me) == [{"batch_key": k, "print_ids": card, "prints": 1, "shards_gained": 150}]
        credits = [s for s in ctx.statements("one") if "UPDATE players SET pc_shards" in _flat(s)]
        assert len(credits) == 1 and "pc_shards = pc_shards + CAST(" in _flat(credits[0]), credits
        # Q7: nothing but card rows, leases, the shard balance and the key's row.
        for s in ctx.statements("one"):
            low = _flat(s).lower()
            if low.startswith(("update", "insert", "delete")):
                assert not any(t in low for t in _NOT_TOUCHED), "the shard wrote outside the card tables: " + low
    _scenario(env, body)


def test_q2_the_card_asked_again_with_its_key_pays_nothing(env):
    """The client keeps the card's key until an answer arrives, so its retry
    after a lost answer is the same request: answered replayed, the same
    figure, the balance and the card untouched, still one row."""
    async def body(ctx):
        me = await _player(1, shards=0)
        subject = await _player(2)
        card = await _print(me, subject, "rare")
        k = _key()
        first = await _batch(ctx, "a", me, k, [card])
        assert first[0] == 200 and first[1]["shards_gained"] == 40, first
        again = await _batch(ctx, "b", me, k, [card])
        assert again[0] == 200, again
        assert (again[1]["replayed"], again[1]["shards_gained"], again[1]["shards"]) == (True, 40, 40)
        assert await _shards(me) == 40
        assert len(await _batches(me)) == 1
        assert not any("UPDATE players SET pc_shards" in _flat(s) for s in ctx.statements("b"))
    _scenario(env, body)


def test_q3_a_card_already_sharded_is_refused_under_a_new_key_and_pays_nothing(env):
    """The card sharded once (by the strip under one key, or by the binder's
    single Discard), then asked under a NEW key: 404 not_owned naming it, the
    balance unchanged, no row for the new key."""
    async def body(ctx):
        me = await _player(1, shards=5)
        subject = await _player(2)
        by_strip, by_binder = await _print(me, subject, "common"), await _print(me, subject, "uncommon")
        assert (await _batch(ctx, "a", me, _key(), [by_strip]))[0] == 200
        assert (await _single(ctx, "b", me, by_binder))[0] == 200
        balance = await _shards(me)
        assert balance == 5 + 5 + 15
        rows = len(await _batches(me))
        for card in (by_strip, by_binder):
            status, detail = await _batch(ctx, "x" + card[:4], me, _key(), [card])
            assert (status, detail.get("error"), detail.get("print_ids")) == (404, "not_owned", [card]), detail
        assert await _shards(me) == balance
        assert len(await _batches(me)) == rows
    _scenario(env, body)


def test_q3_a_card_the_player_does_not_own_is_refused_and_changes_nothing(env):
    """Another player's card: 404 not_owned, neither balance moves, the card
    stays live with its owner."""
    async def body(ctx):
        me = await _player(1, shards=2)
        other = await _player(3, shards=9)
        subject = await _player(2)
        theirs = await _print(other, subject, "legendary")
        status, detail = await _batch(ctx, "a", me, _key(), [theirs])
        assert (status, detail.get("error"), detail.get("print_ids")) == (404, "not_owned", [theirs]), detail
        assert (await _shards(me), await _shards(other)) == (2, 9)
        assert (await _discarded([theirs]))[theirs] == (False, None)
        assert await _batches(me) == []
    _scenario(env, body)


def test_q2_the_card_s_key_sent_for_another_card_is_refused(env):
    """The strip draws one key per card; a key that already shard card a and
    is sent for card b is 409 key_reused (the client then drops the key,
    PcQuickShardRules.KeepKeyAfter), b stays live, the balance unchanged."""
    async def body(ctx):
        me = await _player(1, shards=0)
        subject = await _player(2)
        a, b = await _print(me, subject, "rare"), await _print(me, subject, "rare")
        k = _key()
        assert (await _batch(ctx, "a", me, k, [a]))[0] == 200
        assert _err(await _batch(ctx, "b", me, k, [b])) == (409, "key_reused")
        assert await _shards(me) == 40
        assert (await _discarded([b]))[b] == (False, None)
    _scenario(env, body)
