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
      no match, series or rating table is touched;
  Q8  (fix pass 1, finding 1) every batch discard credits a print received
      by trade at the server's configured traded-discard value, exactly as
      the single discard does, and a batch whose traded-discard rule cannot
      be established writes nothing;
  Q9  (fix pass 1, finding 2) a retired batch-shard generation changes
      neither cached state nor the nonce or latch of a newer request
      (PcShardFlight, executed in the harness; gate q9 pins the call sites);
  Q10 (fix pass 1, finding 3) the pull tab's Shard dupes shards only the
      shown pack's live duplicates, one live copy of each exact face kept
      (PcQuickShardRules.DuplicateShardIds, executed in the harness; gate q10
      pins the call sites); the Shard pack keeps board row 25's set.
  Q11 (fix pass 2, finding 1) a read-back launched by a retired shard
      generation never overwrites cache state a newer shard confirmed: every
      /pc/me and /pc/collection read carries the answer fence's generation
      from its dispatch (PcCacheFence.Stamp), every confirmed cache write
      moves it, and a read lands only when it has not moved; a dropped read
      is owed and sent again once no shard or discard is out (the recovery
      model is EXECUTED by the harness, PcQuickShardRules.RecoveryCases;
      gate q11 pins the call sites).

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
    _batch, _batches, _discarded, _err, _flat, _key, _pc, _player, _print, _q, _scenario, _shards, _single,
    _val, env, main, pg_build,
)
from test_pc_shard_batch import _code as _py_code, _fn_src  # noqa: E402

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
    send = _at(q, "SendShard(id, key, ids, null, p.print_id);", "the strip card is not sent as a one-card shard")
    assert arm < send, "the strip card is sent before it is confirmed"
    assert "string set = PcQuickShardRules.ArmSet(p.print_id);" in q, "the arm is not the card's own set"


def gate_q2_the_key_is_kept_for_the_card_until_an_answer(s):
    ui = s["ui"]
    q = _code(_member(ui, "private static void OnQuickShardClick("))
    assert "string key = shardFlight.KeyFor(set, () => NewNonce());" in q, (
        "the strip card's nonce is not kept for that card")
    assert q.count("NewNonce()") == 1, "the strip card draws a fresh nonce on every click"
    rules = _code(s["rules"])
    keyfor = _member(rules, "internal string KeyFor(")
    assert "if (QuickKeyFor != set || string.IsNullOrEmpty(QuickKey)) { QuickKey = mint(); QuickKeyFor = set; }" in keyfor, (
        "the strip card's nonce is not kept for that card")
    settle = _member(rules, "internal bool Settle(")
    assert "if (quick && !PcQuickShardRules.KeepKeyAfter(code)) { QuickKey = null; QuickKeyFor = null; }" in settle, (
        "a refused strip shard drops its key outside the rule")
    for fn in ("private static void FailShard(", "private static void FinishShard("):
        assert "QuickKey" not in _code(_member(ui, fn)) and "quickKey" not in _code(_member(ui, fn)), (
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
    assert 'if (ok && epoch == _pcCacheEpoch && CachedPcMe != null && PcShardFlight.Admits(current))' in api, (
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


def gate_q9_a_retired_generation_touches_nothing(s):
    """Fix pass 1, finding 2: every batch request is stamped with a
    generation (PcShardFlight.Begin); the cache write and the callback both
    test it, the callback before its first state write; the give-up and the
    identity reset retire it. The decisions themselves are EXECUTED by the
    harness (PcQuickShardRules.FlightCases); this pins that the client calls
    them where the answer lands."""
    ui = s["ui"]
    send = _code(_member(ui, "private static void SendShard("))
    begin = _at(send, "int serial = shardFlight.Begin(Now, packId, quickPrintId, dupesOf);", "a batch request is not stamped with a generation")
    call = _at(send, "ApiClient.PcDiscardBatch(id, key, ids, () => ep == uiEpoch && shardFlight.IsCurrent(serial), (ok, resp) =>",
               "the cache write does not test the request's generation")
    cb = send[call:]
    epoch = _at(cb, "if (ep != uiEpoch) return;", "the answer's identity check moved")
    settle = _at(cb, "if (!shardFlight.Settle(serial, code))", "the answer is not checked against its own generation")
    drop = settle + _at(cb[settle:], "return;", "a retired answer is not dropped")
    first = min(_at(cb, "FinishShard(", "the answer no longer finishes"), _at(cb, "FailShard(", "the answer no longer fails"))
    assert begin < call and epoch < settle < drop < first, "a retired answer is not dropped before its first state write"
    assert cb.count("shardFlight.") == 2, "the answer touches the flight outside its generation check"
    api = _code(_member(s["api"], "public static void PcDiscardBatch("))
    write = _at(api, "CachedPcMe.shards = PcInt(sh);", "the batch no longer writes the balance it was sent")
    guard = _at(api, "&& PcShardFlight.Admits(current))", "the balance is written for a retired request")
    assert guard < write, "the balance is written for a retired request"
    tick = _code(_member(ui, "internal static void MaybeTick("))
    assert tick.count("shardFlight.GiveUp(Now, 25f, out quick)") == 1, "the give-up does not retire the generation"
    assert "shardFlight.Reset();" in ui, "an identity change does not retire the flight"
    for raw in (r"\bshardInFlight\s*=[^=>]", r"\bshardAt\b", r"\bquickKey\b", r"\bshardQuickId\s*=[^=>]", r"\bshardPackId\s*=[^=>]"):
        assert not re.search(raw, _code(ui)), "the latch or nonce has a second writer: " + raw
    settle_rule = _member(_code(s["rules"]), "internal bool Settle(")
    assert "if (!IsCurrent(serial)) return false;" in settle_rule, "the answer is not checked against its own generation"


def gate_q10_shard_dupes_sends_only_the_pack_s_duplicates(s):
    """Fix pass 1, finding 3: the pull tab's one confirmed action that shards
    only the shown pack's live duplicates, one live copy of each exact face
    kept, through the same batch route. The selection itself is EXECUTED by
    the harness (PcQuickShardRules.DupesCases, the A, A, A, B, C control);
    this pins that the button reaches it and nothing else. The Shard pack
    beside it keeps board row 25's set (every live print of the pack)."""
    ui = s["ui"]
    assert re.search(r'UIFactory\.CreateButton\("PcShardDupes", [^;]*?, OnShardDupesClick, sizeDelta', ui), (
        "Shard dupes is not a guarded button wired to its click")
    click = _code(_member(ui, "private static void OnShardDupesClick("))
    pick = _at(click, "var ids = PackDupeIds(shown, col, out ready);", "Shard dupes does not send the pack's duplicates")
    assert "PackShardIds(" not in click, "Shard dupes does not send the pack's duplicates"
    wait = _at(click, "if (!ready) {", "Shard dupes sends against a collection that does not count the pack")
    arm = _at(click, "if (!ShardConfirmed(set))", "Shard dupes does not ask first")
    send = _at(click, "SendShard(id, key, ids, null, null, shown.pack_id);", "Shard dupes is not one batch request")
    assert pick < wait < arm < send, "Shard dupes does not ask first"
    assert "string set = DupesShardSet(shown.pack_id, ids);" in click, "Shard dupes does not arm its exact set"
    assert click.count("SendShard(") == 1 and click.count("NewNonce()") == 1, "Shard dupes is not one batch request"
    for loop in ("for (", "foreach (var x", "while (", "StartCoroutine("):
        assert loop not in click, "Shard dupes is not one batch request"
    ids = _code(_member(ui, "private static List<string> PackDupeIds("))
    assert "bool live = p != null && !p.discarded && ShardToken(p.print_id) && !shardGone.Contains(p.print_id);" in ids, (
        "a print that is not live is counted")
    assert "faces.Add(live ? FaceKey(p) : null);" in ids, "a print that is not live is counted"
    assert "c.discarded || shardGone.Contains(c.print_id)" in ids, "a print that is not live is counted"
    assert "PcQuickShardRules.DuplicateShardIds(faces, pids, counts, held, out ready)" in ids, (
        "Shard dupes does not send the pack's duplicates")
    rule = _member(_code(s["rules"]), "internal static List<string> DuplicateShardIds(")
    assert "if (outside == 0 && kept.Add(k)) continue;" in rule, "the duplicate rule can take a last copy"
    refresh = _code(_member(ui, "private static void RefreshShardDupesButton("))
    assert "bool up = ready && ids.Count > 0 && ids.Count <= ApiClient.PC_DISCARD_BATCH_CAP;" in refresh, (
        "Shard dupes is offered without a duplicate")
    assert "RefreshShardDupesButton(shown);" in _member(ui, "private static void RefreshShardPackButton("), (
        "Shard dupes is never painted")
    pack = _code(_member(ui, "private static void OnShardPackClick("))
    assert "var ids = PackShardIds(shown);" in pack, "the Shard pack's set changed"


def _fenced_read(api, signature, write, owed, what):
    code = _code(_member(api, signature))
    stamp = _at(code, "int fence = PcAnswerFence.Stamp();", what)
    start = _at(code, "Plugin.Instance.StartCoroutine(GetRequest(url, (ok, resp) =>", what)
    check = _at(code, "if (ok && !PcAnswerFence.Admits(fence))", what)
    owe = check + _at(code[check:], owed, what)
    ret = owe + _at(code[owe:], "return;", what)
    land = _at(code, write, what)
    assert stamp < start < check < owe < ret < land, what
    assert code.count("PcAnswerFence.") == 2, what


def gate_q11_a_retired_shard_s_read_back_never_undoes_a_newer_shard(s):
    """Fix pass 2, finding 1: both reads carry the fence's generation from
    their dispatch and land only when no confirmed write moved it; every
    writer that applies a server confirmation moves it; a dropped read is
    owed and sent again only while no shard and no discard is out. The
    decisions are EXECUTED by the harness (PcQuickShardRules.RecoveryCases);
    this pins that the client calls them where the answers land."""
    api, ui = s["api"], s["ui"]
    _fenced_read(api, "public static void FetchPcMe(", "CachedPcMe = me;", "pcMeReadOwed = true;",
                 "the balance read lands without the fence")
    _fenced_read(api, "public static void FetchPcCollection(", "CachedPcCollection = col;", "pcCollReadOwed = true;",
                 "the collection read lands without the fence")
    for sig, what in (("public static void PcDiscardBatch(", "a confirmed batch balance does not move the fence"),
                      ("public static void PcDiscard(string steamId, string printId,", "a confirmed discard balance does not move the fence")):
        assert "if (sh != null) { CachedPcMe.shards = PcInt(sh); PcAnswerFence.Wrote(); }" in _code(_member(api, sig)), what
    finish = _code(_member(ui, "private static void FinishShard("))
    assert "if (results.Count > 0) ApiClient.PcAnswerFence.Wrote();" in finish, "the prints a shard removed do not move the fence"
    assert "ApiClient.PcAnswerFence.Wrote();" in _code(_member(ui, "private static void DrawReceived(")), (
        "the prints a trade accept drew do not move the fence")
    assert _code(ui).count("ApiClient.PcAnswerFence.Wrote();") == 3, "a confirmed removal does not move the fence"
    tick = _code(_member(ui, "internal static void MaybeTick("))
    assert tick.count("if (ApiClient.PcReadsOwed && !shardInFlight && !discardInFlight) ApiClient.PcSendOwedReads(id);") == 1, (
        "an owed read is sent while a shard or a discard is out")
    assert _code(ui).count("PcSendOwedReads(") == 1, "an owed read is sent while a shard or a discard is out"
    owed = _code(_member(api, "internal static void PcSendOwedReads("))
    assert owed.count("FetchPcMe(steamId, true, cb);") == 1 and owed.count("FetchPcCollection(steamId, true, cb);") == 1, (
        "an owed read is not sent once")
    for loop in ("for (", "foreach (", "while (", "StartCoroutine("):
        assert loop not in owed, "an owed read is not sent once"
    release = _code(_member(api, "private static void ReleasePcReadLatches("))
    assert "pcMeReadOwed = false; pcCollReadOwed = false;" in release, "a read owed to the previous identity is sent"
    admits = _member(_code(s["rules"]), "internal bool Admits(int stamp)")
    assert "return stamp == Writes;" in admits, "the fence admits a read dispatched before a write"


NEW_KEYS = ("Shard dupes (+{0})", "Click Shard dupes again to shard {0} duplicates for {1} shards")
_CAT_ENTRY = re.compile(r'^\s+\["((?:[^"\\]|\\.)*)"\] = "((?:[^"\\]|\\.)*)",$', re.M)


def _cs_unescape(lit):
    return re.sub(r"\\u([0-9a-fA-F]{4})", lambda m: chr(int(m.group(1), 16)), lit).replace('\\"', '"').replace("\\\\", "\\")


def test_q10_the_new_strings_are_translated_in_every_catalogue():
    """The two strings Shard dupes adds are client strings, in the extracted
    registry and the compiled key list, and in each of the four catalogues
    translated (not English) with the same placeholders."""
    ui = FILES["ui"].read_text(encoding="utf-8")
    reg = (ROOT / "tools" / "i18n_source.json").read_text(encoding="utf-8")
    gen = (PLUGIN / "I18nSourceKeys.g.cs").read_text(encoding="utf-8")
    cat = (PLUGIN / "I18nCatalogues.cs").read_text(encoding="utf-8")
    blocks = cat.split("private static readonly Dictionary<string, string> ")[1:]
    assert [b[:2] for b in blocks] == ["ES", "RU", "UK", "SV"]
    for key in NEW_KEYS:
        assert ('"%s"' % key) in ui, key
        assert ('"%s",' % key) in reg and ('"%s",' % key) in gen, key
        want = sorted(re.findall(r"\{\d+\}", key))
        for b in blocks:
            rows = dict((_cs_unescape(k), _cs_unescape(v)) for k, v in _CAT_ENTRY.findall(b[:b.index("\n        };")]))
            assert key in rows, (b[:2], key)
            assert rows[key] != key, (b[:2], key)
            assert sorted(re.findall(r"\{\d+\}", rows[key])) == want, (b[:2], key)


GATES = [gate_q1_the_strip_card_shards_in_place_on_a_confirmed_click,
         gate_q2_the_key_is_kept_for_the_card_until_an_answer,
         gate_q4_the_balance_and_the_stamp_come_only_from_an_answer,
         gate_q5_a_failure_reads_back_by_the_rule,
         gate_q6_one_request_per_shard,
         gate_q9_a_retired_generation_touches_nothing,
         gate_q10_shard_dupes_sends_only_the_pack_s_duplicates,
         gate_q11_a_retired_shard_s_read_back_never_undoes_a_newer_shard]


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
     "            SendShard(id, key, ids, null, p.print_id);",
     "            SendShard(id, NewNonce(), ids, null, p.print_id);",
     "            SendShard(id, key, ids, null, p.print_id);   // the kept key",
     "the strip card draws a fresh nonce on every click"),
    ("Q2b", gate_q2_the_key_is_kept_for_the_card_until_an_answer, "rules",
     "            if (quick && !PcQuickShardRules.KeepKeyAfter(code)) { QuickKey = null; QuickKeyFor = null; }\n"
     "            return true;\n        }\n\n        /// <summary>The give-up",
     "            QuickKey = null; QuickKeyFor = null;\n"
     "            return true;\n        }\n\n        /// <summary>The give-up",
     "            if (quick && !PcQuickShardRules.KeepKeyAfter(code)) { QuickKey = null; QuickKeyFor = null; }   // the rule\n"
     "            return true;\n        }\n\n        /// <summary>The give-up",
     "a refused strip shard drops its key outside the rule"),
    ("Q4a", gate_q4_the_balance_and_the_stamp_come_only_from_an_answer, "ui",
     "            string key = shardFlight.KeyFor(set, () => NewNonce());\n            SendShard(id, key, ids, null, p.print_id);",
     "            string key = shardFlight.KeyFor(set, () => NewNonce());\n"
     "            HistoryMarkDiscarded(p.print_id, value0);\n            SendShard(id, key, ids, null, p.print_id);",
     "            string key = shardFlight.KeyFor(set, () => NewNonce());   // kept\n            SendShard(id, key, ids, null, p.print_id);",
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
     "            SendShard(id, key, ids, null, p.print_id);",
     "            foreach (var x in ids) SendShard(id, key, new List<string> { x }, null, p.print_id);",
     "            SendShard(id, key, ids, null, p.print_id);   // one request",
     "the strip card's click loops or schedules"),
    ("Q6c", gate_q6_one_request_per_shard, "ui",
     "            SendShard(id, key, ids, null, p.print_id);",
     "            SendShard(id, key, ids, null, p.print_id);\n            SendShard(id, key, ids, null, p.print_id);",
     "            SendShard(id, key, ids, null, p.print_id);   // once",
     "a confirmed click sends more than once"),
    ("Q6b", gate_q6_one_request_per_shard, "ui",
     "                else FailShard(id, resp, packId, keyed);",
     "                else { FailShard(id, resp, packId, keyed); SendShard(id, key, ids, packId, quickPrintId); }",
     "                else FailShard(id, resp, packId, keyed);   // never sent again",
     "an answer sends again"),
    ("Q9a", gate_q9_a_retired_generation_touches_nothing, "ui",
     "                if (!shardFlight.Settle(serial, code))",
     "                if (!shardFlight.Settle(shardFlight.Serial, code))",
     "                if (!shardFlight.Settle(serial, code))   // its own generation",
     "the answer is not checked against its own generation"),
    ("Q9b", gate_q9_a_retired_generation_touches_nothing, "api",
     "if (ok && epoch == _pcCacheEpoch && CachedPcMe != null && PcShardFlight.Admits(current))",
     "if (ok && epoch == _pcCacheEpoch && CachedPcMe != null)",
     "if (ok && epoch == _pcCacheEpoch && CachedPcMe != null && PcShardFlight.Admits(current))   ",
     "the balance is written for a retired request"),
    ("Q9c", gate_q9_a_retired_generation_touches_nothing, "ui",
     "            if (shardFlight.GiveUp(Now, 25f, out quick))",
     "            quick = shardQuickId != null;\n            if (shardInFlight && quick)",
     "            if (shardFlight.GiveUp(Now, 25f, out quick))   // retires the generation",
     "the give-up does not retire the generation"),
    ("Q9d", gate_q9_a_retired_generation_touches_nothing, "rules",
     "            if (!IsCurrent(serial)) return false;\n            bool quick = Keyed;",
     "            bool quick = Keyed;",
     "            if (!IsCurrent(serial)) return false;   // retired: nothing\n            bool quick = Keyed;",
     "the answer is not checked against its own generation"),
    ("Q10a", gate_q10_shard_dupes_sends_only_the_pack_s_duplicates, "ui",
     "            var ids = PackDupeIds(shown, col, out ready);",
     "            var ids = PackShardIds(shown); ready = true;",
     "            var ids = PackDupeIds(shown, col, out ready);   // duplicates only",
     "Shard dupes does not send the pack's duplicates"),
    ("Q10b", gate_q10_shard_dupes_sends_only_the_pack_s_duplicates, "rules",
     "                if (outside == 0 && kept.Add(k)) continue;",
     "                if (false && kept.Add(k)) continue;",
     "                if (outside == 0 && kept.Add(k)) continue;   // one live copy kept",
     "the duplicate rule can take a last copy"),
    ("Q10c", gate_q10_shard_dupes_sends_only_the_pack_s_duplicates, "ui",
     "            string set = DupesShardSet(shown.pack_id, ids);\n            if (!ShardConfirmed(set))",
     "            string set = DupesShardSet(shown.pack_id, ids);\n            if (false)",
     "            string set = DupesShardSet(shown.pack_id, ids);\n            if (!ShardConfirmed(set))   // the first click asks",
     "Shard dupes does not ask first"),
    ("Q10d", gate_q10_shard_dupes_sends_only_the_pack_s_duplicates, "ui",
     "                faces.Add(live ? FaceKey(p) : null); pids.Add(p?.print_id);",
     "                faces.Add(FaceKey(p)); pids.Add(p?.print_id);",
     "                faces.Add(live ? FaceKey(p) : null); pids.Add(p?.print_id);   // live only",
     "a print that is not live is counted"),
    ("Q11a", gate_q11_a_retired_shard_s_read_back_never_undoes_a_newer_shard, "api",
     "                if (ok && !PcAnswerFence.Admits(fence))\n                {\n"
     "                    // Fix pass 2, finding 1: a confirmed write (a shard's or a",
     "                if (ok && false)\n                {\n"
     "                    // Fix pass 2, finding 1: a confirmed write (a shard's or a",
     "                if (ok && !PcAnswerFence.Admits(fence))   // the fence\n                {\n"
     "                    // Fix pass 2, finding 1: a confirmed write (a shard's or a",
     "the balance read lands without the fence"),
    ("Q11b", gate_q11_a_retired_shard_s_read_back_never_undoes_a_newer_shard, "api",
     "                if (ok && !PcAnswerFence.Admits(fence))\n                {\n"
     "                    // Fix pass 2, finding 1: a confirmed write (prints a shard,",
     "                if (ok && false)\n                {\n"
     "                    // Fix pass 2, finding 1: a confirmed write (prints a shard,",
     "                if (ok && !PcAnswerFence.Admits(fence))   // the fence\n                {\n"
     "                    // Fix pass 2, finding 1: a confirmed write (prints a shard,",
     "the collection read lands without the fence"),
    ("Q11c", gate_q11_a_retired_shard_s_read_back_never_undoes_a_newer_shard, "api",
     "                    if (sh != null) { CachedPcMe.shards = PcInt(sh); PcAnswerFence.Wrote(); }\n                }\n"
     "                try { callback?.Invoke(ok, resp); } catch (Exception cex) { Plugin.Log.LogWarning($\"[PC] discard-batch callback",
     "                    if (sh != null) { CachedPcMe.shards = PcInt(sh); }\n                }\n"
     "                try { callback?.Invoke(ok, resp); } catch (Exception cex) { Plugin.Log.LogWarning($\"[PC] discard-batch callback",
     "                    if (sh != null) { CachedPcMe.shards = PcInt(sh); PcAnswerFence.Wrote(); }   // moves it\n                }\n"
     "                try { callback?.Invoke(ok, resp); } catch (Exception cex) { Plugin.Log.LogWarning($\"[PC] discard-batch callback",
     "a confirmed batch balance does not move the fence"),
    ("Q11d", gate_q11_a_retired_shard_s_read_back_never_undoes_a_newer_shard, "rules",
     "            return stamp == Writes;",
     "            return true;",
     "            return stamp == Writes;   // no write since",
     "the fence admits a read dispatched before a write"),
    ("Q11e", gate_q11_a_retired_shard_s_read_back_never_undoes_a_newer_shard, "ui",
     "            if (results.Count > 0) ApiClient.PcAnswerFence.Wrote();",
     "            if (results.Count > 0) { }",
     "            if (results.Count > 0) ApiClient.PcAnswerFence.Wrote();   // a confirmed write",
     "the prints a shard removed do not move the fence"),
    ("Q11f", gate_q11_a_retired_shard_s_read_back_never_undoes_a_newer_shard, "ui",
     "            if (ApiClient.PcReadsOwed && !shardInFlight && !discardInFlight) ApiClient.PcSendOwedReads(id);",
     "            if (ApiClient.PcReadsOwed) ApiClient.PcSendOwedReads(id);",
     "            if (ApiClient.PcReadsOwed && !shardInFlight && !discardInFlight) ApiClient.PcSendOwedReads(id);   // after the run",
     "an owed read is sent while a shard or a discard is out"),
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


# ------------------------------- Q8: the traded-discard rule (fix pass 1, F1)

# A configured traded-discard value no rarity pays, so a print credited at its
# rarity can never pass for one credited at the traded rule.
_TRADED_VALUE = 7


async def _traded(print_id, to):
    """Move a print to `to` as received by trade, the accept's own move
    (main._PC_TRADE_MOVE_SQL: the owner and acquired_by_trade = true in one
    statement, the only change migration 353's trigger admits to the flag)."""
    await _q("UPDATE pc_prints SET owner_player_id = $2::uuid, acquired_by_trade = true "
             "WHERE id = $1::uuid AND discarded_at IS NULL", print_id, to.pid)


async def _rows(who):
    """Every row count a discard can move, for one player."""
    return (await _val("SELECT count(*) FROM pc_prints WHERE owner_player_id = $1::uuid AND discarded_at IS NOT NULL", who.pid),
            await _val("SELECT count(*) FROM pc_shard_batches WHERE player_id = $1::uuid", who.pid),
            await _val("SELECT count(*) FROM pc_delivery_leases"),
            await _shards(who))


def test_q8_a_batch_credits_a_traded_print_at_the_traded_value_and_an_untraded_one_at_its_rarity(env):
    """One batch holding a print received by trade and one that was not:
    the first is credited PC_TRADE['traded_discard_shards'] whatever its
    rarity, the second its rarity's value -- each print's row, the answer's
    results, the total, the key's row and the balance all agree, and the
    single discard pays the same traded print kind the same value."""
    env.monkeypatch.setitem(_pc.PC_TRADE, "traded_discard_shards", _TRADED_VALUE)
    assert _TRADED_VALUE not in _pc.PC_ECONOMY["shards"].values()

    async def body(ctx):
        me = await _player(1, shards=3)
        subject = await _player(2)
        giver = await _player(3)
        traded = await _print(giver, subject, "legendary")
        plain = await _print(me, subject, "epic")
        single = await _print(giver, subject, "legendary")
        await _traded(traded, me)
        await _traded(single, me)
        k = _key()
        status, ans = await _batch(ctx, "both", me, k, sorted([traded, plain]))
        assert status == 200, ans
        want = _TRADED_VALUE + _pc.shards_for("epic")
        assert (ans["prints"], ans["shards_gained"], ans["shards"]) == (2, want, 3 + want), ans
        paid = {r["print_id"]: r["shards_gained"] for r in ans["results"]}
        assert paid == {traded: _TRADED_VALUE, plain: _pc.shards_for("epic")}, paid
        rows = await _discarded([traded, plain])
        assert rows[traded] == (True, _TRADED_VALUE) and rows[plain] == (True, _pc.shards_for("epic")), rows
        assert await _batches(me) == [{"batch_key": k, "print_ids": ",".join(sorted([traded, plain])),
                                       "prints": 2, "shards_gained": want}]
        assert await _shards(me) == 3 + want
        # The single route, the rule the batch must match: the same kind of
        # print, the same value.
        s_status, s_ans = await _single(ctx, "single", me, single)
        assert s_status == 200 and s_ans["shards_gained"] == _TRADED_VALUE, s_ans
    _scenario(env, body)


@pytest.mark.parametrize("word", ["unknown", "partial", "broken"])
def test_q8_a_batch_whose_traded_rule_cannot_be_established_writes_nothing(env, word):
    """The trading schema's word is neither found (ready / off) nor a
    positively confirmed schema_missing: no traded-discard value is provably
    right, so the batch answers 503 trading_unavailable, exactly as the
    single discard does, and writes nothing -- every row count before equals
    after, both prints stay live, no key row, no credit statement."""
    async def word_is(_db):
        return word
    env.monkeypatch.setattr(main, "_pc_trading_word", word_is)

    async def body(ctx):
        me = await _player(1, shards=9)
        subject = await _player(2)
        giver = await _player(3)
        traded = await _print(giver, subject, "rare")
        plain = await _print(me, subject, "common")
        await _traded(traded, me)
        before = await _rows(me)
        answer = await _batch(ctx, "refused", me, _key(), sorted([traded, plain]))
        assert _err(answer) == (503, "trading_unavailable"), answer
        assert await _rows(me) == before, (before, await _rows(me))
        assert (await _discarded([traded, plain])) == {traded: (False, None), plain: (False, None)}
        assert not any(_flat(s).lower().startswith(("update", "insert", "delete")) for s in ctx.statements("refused")), (
            "the refused batch sent a write")
        single = await _single(ctx, "single", me, traded)
        assert _err(single) == (503, "trading_unavailable"), single
    _scenario(env, body)


def test_q8_both_routes_read_the_one_traded_rule_before_the_gate_and_any_write():
    """Structure, per FUNCTION (#279): each discard route calls
    _pc_traded_rule_governs exactly once, after its players-row lock, before
    its gate and before its first conditional discard; the batch's value
    reads PC_TRADE['traded_discard_shards'] for a traded print, as the
    single route's does."""
    for name in ("pc_discard_print", "pc_discard_batch"):
        code = _py_code(_fn_src(name))
        assert code.count("_pc_traded_rule_governs (") == 1, name
        lock = code.index("FOR NO KEY UPDATE")
        rule = code.index("_pc_traded_rule_governs (")
        gate = code.index("_pc_discard_gate (")
        disc = code.index("UPDATE pc_prints SET discarded_at = now()")
        assert lock < rule < gate < disc, name
        assert code.count("_pc . PC_TRADE [ \"traded_discard_shards\" ]") == 1, name
    rule = _py_code(_fn_src("_pc_traded_rule_governs"))
    assert rule.count("HTTPException (") == 2 and rule.count("await db . rollback ( )") == 2
