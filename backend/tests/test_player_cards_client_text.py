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
API = ROOT / "plugin" / "ApiClient.cs"
INFO = ROOT / "plugin" / "InfoLibrary.cs"
FACES = ROOT / "plugin" / "PlayerCardFaces.cs"
RULES = ROOT / "backend" / "api" / "player_cards.py"


def _economy():
    spec = importlib.util.spec_from_file_location("player_cards_rules", RULES)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.PC_ECONOMY


def _pct(v):
    return f"{v:g}%"


def _span(src, start, end):
    """The source between two anchors, so a pin is asserted inside the
    function it belongs to and not anywhere in the file."""
    a = src.index(start)
    return src[a:src.index(end, a)]


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
    api = API.read_text(encoding="utf-8")
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
    assert api.count("int epoch = _pcCacheEpoch;") == 5   # + FetchPcPacks, the pack history pager (Sept 12)
    # an empty binder after an identity edge is refetched
    assert "if (view == View.Binder && ApiClient.CachedPcCollection == null && ApiClient.PcCollectionError == null)" in src
    # the title line is the translated rank tier plus the SEPARATELY translated
    # shop title (Sept 12: the RANK slot never shows the shop title, a rank
    # name is never a subtitle, and a shop title goes through the same runtime
    # lookup the Shop list uses for catalogue names)
    assert "string title = TitleLine(p);" in src and "if (title.Length > 0) lines.Add(title);" in src
    assert "UIFactory.SetTextRaw(t.txtTitle, TitleLine(p));" in src
    assert 'string tier = string.IsNullOrEmpty(p.rank_name) ? "" : I18n.Tr(p.rank_name);' in src
    assert 'string shop = string.IsNullOrEmpty(p.title) ? "" : I18n.Tr(p.title);' in src
    assert 'string shop = p.title ?? "";' not in src
    assert 'return tier.Length > 0 ? tier + "  ·  " + shop : shop;' in src
    # the i18n source follows the client text (c6 L)
    blob = (ROOT / "tools" / "i18n_source.json").read_text(encoding="utf-8")
    for key in ("The pack answer could not be read - checking again shortly",
                "Your pack was opened but its answer could not be read - check your binder",
                "This account was deleted - there is no pack to recover"):
        assert key in blob, key
    assert "Another account's pack is still being resolved" not in blob
    assert '"kind|ref|pay|price|unix|owner"' in (ROOT / "plugin" / "Plugin.cs").read_text(encoding="utf-8")


def test_the_binder_tile_layout_repairs_are_pinned_one_by_one():
    """The three repairs behind the 2026-09-12 binder screenshot, each on its
    own so deleting any one of them fails here: the face slot asks for no
    preferred size (a 375x525 sprite used to claim 525 px and crush the
    action row), the action row keeps a minimum height, and the action
    labels clip (TMP Masking) rather than blank under Truncate. Since
    2026-09-13 there is no View button: the face and the text block open the
    card on click (through the same-frame guard), and a hint line under the
    grid says so."""
    src = CLIENT.read_text(encoding="utf-8")
    tile = _span(src, 't.face = UIFactory.CreatePanel(name + "_f"', "private static string RatingLine")
    assert "UIFactory.AddLE(t.face, prefW: 0, prefH: 0, flexH: 1, flexW: 1);" in tile
    assert "UIFactory.AddLE(t.actions, prefH: 22, minH: 22, flexH: 0);" in tile
    assert "foreach (var o in new[] { t.btnDiscardTxt, t.btnDupesTxt })" in tile
    assert "if (o != null) { UIFactory.SetOverflowMode(o, 2); UIFactory.SetWordWrap(o, false); }" in tile
    assert "btnView" not in src
    assert "foreach (var go in new[] { t.face, t.textBlock })" in tile
    assert "ch.onClick = () => OnTileClick(tile);" in tile
    assert "if (t == null || t.print == null || Time.frameCount == cardPopupFrame) return;" in src
    assert 'UIFactory.CreateText("PcBHint", binderRoot.transform, "Click a card to view it"' in src


def test_the_pack_history_keeps_the_servers_order_and_follows_its_signals():
    """Sept 12 review items 2-4 and the second round's findings on them: the
    strip's pager keeps the server's (opened_at, id) DESC order on EVERY
    insertion path, keeps its first page's total for the life of the anchored
    chain and counts a head insert once against that page's head, drops its
    pages on a language change, and asks a page again when a face it holds
    answers 404 -- spending the key only once the page came back carrying
    the print, dropping the chain when it did not. Signals, never a timer."""
    src = CLIENT.read_text(encoding="utf-8")
    api = API.read_text(encoding="utf-8")
    hist = _span(src, "// ── pack history (the strip's pager)", "private static void HistoryMarkDiscarded")
    notfound = _span(hist, "private static void OnHistoryFaceNotFound", "private static bool FaceRefetchWaiting")
    refetch = _span(hist, "private static void RefetchHistoryPage", "private static void SettleFaceRefetches")
    settle = _span(hist, "private static void SettleFaceRefetches", "private static bool AnswerHoldsPrint")
    merge = _span(hist, "private static void MergeHistoryPage", "private static void HistoryInsertHead")
    head = _span(hist, "private static void HistoryInsertHead(", "private static void HistoryReset()")
    reset = _span(hist, "private static void HistoryReset()", "private static void EnsureHistory")
    # item 3: the server's keyset pair, never the timestamp alone, on BOTH
    # insertion paths -- a merged page is sorted, a head insert walks past
    # every pack that sorts before it instead of taking index 0
    assert 'int c = string.CompareOrdinal(y.opened_at ?? "", x.opened_at ?? "");' in hist
    assert 'return c != 0 ? c : string.CompareOrdinal(y.pack_id ?? "", x.pack_id ?? "");' in hist
    assert merge.count("packHistory.Sort(ServerOrder);") == 1
    assert "packHistory.Sort((x, y) =>" not in src
    assert "while (at < packHistory.Count && ServerOrder(packHistory[at], a) < 0) at++;" in head
    assert "packHistory.Insert(at, a);" in head and "historyIndex = at;" in head
    assert "packHistory.Insert(0, a);" not in hist and "historyIndex = 0;" not in head
    # the total: the first page's is the chain's, adopted exactly once and
    # never replaced by a later page's (a pack opened elsewhere since is one
    # the anchored chain cannot reach)
    assert merge.count("historyTotal = h.total;") == 1
    assert _span(merge, "if (!historyAnchored)", "lastPack =").count("historyTotal = h.total;") == 1
    assert "historyTotal = Math.Max(h.total, packHistory.Count);" not in src
    assert "historyAnchored = false; historyAnchor = null;" in reset
    # item 4: a head insert is one more only when the list did not hold it
    # AND it is newer than the anchored page's head -- a delayed answer for a
    # pack older than that head was already in the first page's total
    assert "bool absent = packHistory.RemoveAll(x => x.pack_id == a.pack_id) == 0;" in head
    assert "if (absent && historyAnchored && (historyAnchor == null || ServerOrder(a, historyAnchor) < 0)) historyTotal++;" in head
    assert head.count("historyTotal++") == 1 and hist.count("historyTotal++") == 1
    assert "if (absent && historyTotal > 0) historyTotal++;" not in hist
    # item 2a: a language change drops the loaded pages (the server keys face
    # revisions under the answer's locale); an answer from before the reset
    # is dropped on landing
    assert "HookHistorySignals();" in _span(src, "internal static void BuildInto(Transform parent)", 'var header = new GameObject("PcHdr");')
    assert "I18n.LocaleChanged += OnHistoryLocaleChanged;" in hist
    assert _span(hist, "private static void OnHistoryLocaleChanged()", "private static string FaceRefetchKey").count("HistoryReset();") == 1
    assert "historyGen++;" in reset
    assert "if (ep != uiEpoch || gen != historyGen) return;" in refetch
    # item 2b: a 404 for a face the history holds asks that page again, older
    # pages included -- the cursor of the page that brought each pack is
    # remembered for exactly this
    assert "internal static event Action<string, string, string> PcFaceNotFound;" in api
    assert "if (!ok && code == 404) NotePcFaceNotFound(url);" in api
    assert 'private const string PC_FACE_ROUTE = "/api/v1/pc-face/";' in api
    assert "ApiClient.PcFaceNotFound += OnHistoryFaceNotFound;" in hist
    assert "if (!historyRefetching.Add(cursor)) return;" in refetch
    assert 'historyPageOf[a.pack_id] = cursor ?? "";' in merge
    assert 'historyPageOf.TryGetValue(a.pack_id ?? "", out cursor);' in notfound
    assert "if (p.print_id != printId || p.face_rev != faceRev || p.discarded) continue;" in notfound
    assert "if (at >= 0) packHistory[at] = a; else packHistory.Add(a);" in merge
    # ...and the key is spent by the ANSWER, never at the ask: the ask records
    # the wait (a key already waiting is not asked twice); the answer spends
    # the key when the page carries the print, and drops the chain -- the
    # reset clears the key with the rest -- when the print moved past the
    # page's end, so the fresh chain refreshes it
    assert "if (faceRefetched.Contains(key) || FaceRefetchWaiting(key)) return;" in notfound
    assert 'faceRefetchPending.Add(new FaceRefetch { key = key, printId = printId, cursor = cursor ?? "" });' in notfound
    assert notfound.count("faceRefetched.Add(") == 0 and hist.count("faceRefetched.Add(") == 1
    assert "if (AnswerHoldsPrint(h, r.printId)) faceRefetched.Add(r.key); else moved = true;" in settle
    assert settle.count("HistoryReset();") == 1 and "SettleFaceRefetches(h, cursor);" in refetch
    assert "faceRefetchPending.Clear();" in reset
    # a failed refetch leaves its keys unspent and the next ask waits out the
    # pager's own 30 s
    assert "historyFailedAt = Now;" in refetch and "faceRefetchPending.RemoveAll(r => r.cursor == cursor);" in refetch
    assert "if (Now - historyFailedAt < 30f) return;" in notfound
    # no polling: the block reads no clock beyond the paint-time retry throttle
    assert "Time.unscaledTime" not in hist and "Time.realtimeSinceStartup" not in hist


def test_the_dev_face_cache_writer_disposes_of_what_it_replaces():
    """The broadcast lever seeds binder-faces again and again in one process.
    Each seeding overwrote the same ten cache entries and left every earlier
    Sprite/Texture2D alive on the GPU until teardown. The writer now puts the
    replacement in place first, moves any tile still showing the old sprite
    onto it, and only then destroys the old sprite and its texture -- never a
    texture the new sprite shares."""
    faces = FACES.read_text(encoding="utf-8")
    put = _span(faces, "internal static void DevPut(", "internal static Sprite Cached(")
    replace = put.index("cache[key] = new Entry { tex = spr.texture, spr = spr, bytes = bytes, lastUse = Time.realtimeSinceStartup };")
    rebind = put.index("foreach (var go in showing) SetFace(go, spr);")
    destroy = put.index("UnityEngine.Object.Destroy(old.spr)")
    assert replace < rebind < destroy
    assert put.count("UnityEngine.Object.Destroy(old.spr)") == 1
    assert put.count("if (old.tex != null && old.tex != spr.texture) UnityEngine.Object.Destroy(old.tex);") == 1
    assert "if (old.spr == spr) return;" in put
    assert "if (bindings[i].spr == old.spr && bindings[i].go != null) showing.Add(bindings[i].go);" in put
    # the byte ledger still moves exactly once each way per replacement
    assert put.count("cacheBytes -= old.bytes;") == 1 and put.count("cacheBytes += bytes;") == 1


def test_the_paid_cap_copy_is_not_universal():
    """Five paid packs a day holds for most accounts; the server exempts one.
    The Get packs text reads /pc/me's paid_cap_exempt (absent = false) and
    says so for that account; the Info library qualifies its own sentence."""
    src = CLIENT.read_text(encoding="utf-8")
    api = API.read_text(encoding="utf-8")
    info = INFO.read_text(encoding="utf-8")
    assert 'me.paid_cap_exempt = PcBool(PcTopLevel(json, "paid_cap_exempt"));' in api
    assert 'internal static bool PcBool(string raw) => raw == "true";' in api   # absent reads false
    body = _span(src, "private static void RefreshInfo", "// ── actions")
    assert "me != null && me.paid_cap_exempt" in body
    assert 'I18n.TrF("- Buy one for {0} gold or {1} shards. No daily limit on this account.", gold, shards)' in body
    assert "Up to 5 paid packs a day for most accounts" in info
    assert "Up to 5 paid packs a day." not in info


def test_the_info_library_states_what_the_cards_settings_actually_do():
    """The Player Cards category registers its three articles, and their text
    states the server's behaviour: opting out stops new cards and announcements
    and plates existing cards (it hides no binder and deletes nothing); Public
    collection is what hides a binder; deletion is what removes cards; a card's
    stats, tier and title are frozen while its name and picture stay live;
    self, Foil and Signed pulls are announced at any rarity."""
    src = INFO.read_text(encoding="utf-8")
    start = src.index("Color = CAT_CARDS, Articles")
    nxt = src.find("new Category {", start + 1)
    cat = src[start:nxt if nxt >= 0 else len(src)]
    assert re.search(r'Key = "cards",\s+Title = \(\) => I18n\.Tr\("Player Cards"\),\s+Body = \(\) => CardsIntro \+ "\\n\\n" \+ CardsPacks', cat)
    assert re.search(r'Key = "cards-face",\s+Title = \(\) => I18n\.Tr\("Reading a card"\),\s+Body = \(\) => CardsFace', cat)
    assert re.search(r'Key = "cards-pictures",\s+Title = \(\) => I18n\.Tr\("Card pictures & settings"\),\s+Body = \(\) => CardsPictures', cat)
    # frozen vs live
    assert "rating, record, rank tier, top card and title as they were that day" in src
    assert "Two things on a card stay live: the player's name (a rename follows) and their picture" in src
    assert "A card's rating, record, rank tier and shop title are frozen at the snapshot it was minted from." in src
    assert "The name and the picture are live: a card of a renamed player shows the new name" in src
    assert "The player's current name - a rename follows onto every card of them" in src
    assert "and it never changes afterwards" not in src and "Everything on a card is frozen" not in src
    # no opt-out and no picture setting (2026-09-13) vs Public collection vs deletion
    assert "There is no opt-out: every registered player who is not banned is in the pool, and cards of you stay in the binders that hold them." in src
    assert "The picture is not a setting: every card of you shows your Steam picture until your PC has sent the character, then the character - including cards pulled before it was sent." in src
    assert "<b>Public collection</b> is the setting that shows or hides your binder from others" in src
    assert "Deleting your data is what removes cards: your binder is emptied, and every card of you is removed from every other player's binder." in src
    assert "If the player deletes their data, every card of them is removed from every binder." in src
    assert "Click a binder tile to see the card full size." in src
    assert "Opt out</b>" not in src and "If the player opts out" not in src and "Deleting your account" not in src
    assert "and hides your binder" not in src
    # announcements: Epic-or-better, plus self / Foil / Signed at any rarity
    assert "and so is a pull of your own card, a Foil or a Signed print at any rarity" in src
    assert "A Rare or lower pull that is none of those is not announced." in src
    assert "Rares and below are never announced." not in src
    # the cap
    assert "Up to 5 paid packs a day for most accounts" in src
