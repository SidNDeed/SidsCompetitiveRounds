"""The Collection tab's "Get packs" text quotes the economy (odds, bands,
shard values). Those numbers live in backend/api/player_cards.py's PC_ECONOMY;
the client cannot fetch them today, so this test pins the client text to the
server constants — a retune of either side without the other fails here.
Prices are NOT pinned: the client renders them from /pc/me."""
import importlib.util
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[2]
CLIENT = ROOT / "plugin" / "PlayerCardsUI.cs"
RULES = ROOT / "backend" / "api" / "player_cards.py"


def _economy():
    spec = importlib.util.spec_from_file_location("player_cards_rules", RULES)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.PC_ECONOMY


def _pct(v):
    return f"{v:g}%"


def _expected_fragments(eco):
    win1, sweep1 = eco["earned_pct"]["1v1"]
    others = {eco["earned_pct"][m] for m in ("team", "ovt", "ffa")}
    assert len(others) == 1, "the client text states one odds pair for 2v2 / 1v2 / FFA"
    win2, sweep2 = next(iter(others))
    t = eco["tier_pct"]
    s = eco["shards"]
    b = eco["band_max_rank"]
    return [
        f"rolls a {_pct(win1)} chance of a pack (a 2-0 sweep: {_pct(sweep1)})",
        f"2v2, 1v2 and FFA wins roll {_pct(win2)} (a sweep: {_pct(sweep2)})",
        f"Odds per card: Common {_pct(t['common'])}, Uncommon {_pct(t['uncommon'])}, Rare {_pct(t['rare'])}, "
        f"Epic {_pct(t['epic'])}, Legendary {_pct(t['legendary'])}.",
        f"Foil (1 in {round(100 / eco['foil_pct'])}) and Signed (1 in {round(100 / eco['signed_pct'])})",
        f"Common {s['common']}, Uncommon {s['uncommon']}, Rare {s['rare']}, Epic {s['epic']}, Legendary {s['legendary']}.",
        f"Legendary = #{b['legendary']}, Epic #{b['legendary'] + 1}-{b['epic']}, Rare #{b['epic'] + 1}-{b['rare']}, "
        f"Uncommon #{b['rare'] + 1}-{b['uncommon']}, Common #{b['uncommon'] + 1} and below",
    ]


def test_client_get_packs_text_matches_pc_economy():
    src = CLIENT.read_text(encoding="utf-8")
    for frag in _expected_fragments(_economy()):
        assert frag in src, f"client text no longer states the server's economy: {frag!r}"


def test_client_text_pin_can_fail():
    """Negative control (#391): a retuned tier percentage must be caught."""
    eco = _economy()
    mutated = {**eco, "tier_pct": {**eco["tier_pct"], "common": eco["tier_pct"]["common"] + 1}}
    src = CLIENT.read_text(encoding="utf-8")
    assert any(frag not in src for frag in _expected_fragments(mutated))


def test_client_prints_per_pack_and_prices_come_from_the_server():
    """The numbers the server can change at runtime are rendered from the
    /pc/me answer, never typed into the text."""
    src = CLIENT.read_text(encoding="utf-8")
    body = src[src.index("private static void RefreshInfo"):src.index("// ── actions")]
    assert re.search(r"TrF\(\"- Buy one for \{0\} gold or \{1\} shards, up to \{2\} paid packs a day\.\", gold, shards, cap\)", body)
    assert re.search(r"TrF\(\"Each pack holds \{0\} cards\.", body)


def test_the_pre_answer_fallbacks_are_the_servers_economy():
    """Before /pc/me answers, RefreshInfo renders fixed fallbacks; they must
    equal PC_ECONOMY too, or a retune shows stale numbers on a failed fetch
    (c4 LOW)."""
    eco = _economy()
    src = CLIENT.read_text(encoding="utf-8")
    body = src[src.index("private static void RefreshInfo"):src.index("// ── actions")]
    m = re.search(r"me\.price_gold : (\d+), shards = me != null \? me\.price_shards : (\d+);", body)
    assert m and (int(m.group(1)), int(m.group(2))) == (int(eco["pack_price_gold"]), int(eco["pack_price_shards"]))
    m = re.search(r"me\.paid_packs_per_day : (\d+), per = me != null \? me\.prints_per_pack : (\d+);", body)
    assert m and (int(m.group(1)), int(m.group(2))) == (int(eco["paid_packs_per_day"]), int(eco["prints_per_pack"]))


def test_the_intent_and_answer_rules_are_pinned_in_the_client():
    """Source-shape pins for the c4/c5/c6 client rules (a repair without a
    reverting test is decoration)."""
    src = CLIENT.read_text(encoding="utf-8")
    api = (ROOT / "plugin" / "ApiClient.cs").read_text(encoding="utf-8")
    # a verified, owner-keyed journal entry gates every purchase and pack open
    assert "private const char INTENT_SEP = '~';" in src and "INTENT_MAX_ENTRIES = 8" in src
    assert "if (string.IsNullOrEmpty(owner)) return false;" in src
    assert "return Plugin.PcOpenIntent.Value == v;" in src
    assert src.count("if (!WriteIntent(") == 2
    # one entry per owner: another account's entry is neither read, cleared nor overwritten
    assert "list.RemoveAll(p => p[5] == owner);" in src and "if (p[5] != owner) continue;" in src
    assert "int n = list.RemoveAll(p => owner != null && p[5] == owner);" in src
    assert "HasForeignIntent" not in src and "ForeignIntentText" not in src and "INTENT_FOREIGN_EXPIRE_S" not in src
    # a malformed or unowned entry (bad timestamp included) is nobody's
    assert "long.TryParse(parts[4], out unix)" in src and "malformed or unowned intent discarded" in src
    assert "INTENT_HARD_RETIRE_S" not in src
    # only a committed answer, the not-found rule, the deleted account or three
    # unreadable 2xx answers retire it
    assert 'PcErrorStr(resp, "status")' in src and "if (http == 404)" in src and "if (http == 410)" in src
    assert "UNPARSEABLE_RETIRE_STRIKES = 3" in src and "unparseableStrikes >= UNPARSEABLE_RETIRE_STRIKES" in src
    assert "if (a != null) unparseableStrikes = 0;" in src and "meRefreshAt = 0f; unparseableStrikes = 0;" in src
    assert 'return "http";   // a plain-string detail' in api
    # the price gate keys on when the /pc/me that produced the cache LEFT
    assert "ApiClient.PcMeDispatchedAt <= priceChangedAt" in src
    assert "PcMeDispatchedAt = dispatched;" in api and "PcMeDispatchedAt = -1f;" in api
    assert api.count("int epoch = _pcCacheEpoch;") == 4
    # an empty binder after an identity edge is refetched
    assert "if (view == View.Binder && ApiClient.CachedPcCollection == null && ApiClient.PcCollectionError == null)" in src
    # tiles clip (TMP Masking), never paint over the neighbour; catalogue titles are translated
    assert "UIFactory.SetOverflowMode(o, 2); UIFactory.SetWordWrap(o, false);" in src
    assert "lines.Add(I18n.Tr(title));" in src and 'title.Length > 0 ? I18n.Tr(title) : ""' in src
    # the i18n source follows the client text (c6 L)
    blob = (ROOT / "tools" / "i18n_source.json").read_text(encoding="utf-8")
    for key in ("The pack answer could not be read - checking again shortly",
                "Your pack was opened but its answer could not be read - check your binder",
                "This account was deleted - there is no pack to recover"):
        assert key in blob, key
    assert "Another account's pack is still being resolved" not in blob
    assert '"kind|ref|pay|price|unix|owner"' in (ROOT / "plugin" / "Plugin.cs").read_text(encoding="utf-8")
