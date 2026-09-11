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
