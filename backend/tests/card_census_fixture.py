"""Census dump fixtures in the format the client writes.

plugin/CardDrawEvidence.cs EnsureCensusDump writes
BepInEx/config/CompetitiveRounds.card-census.json as SeatEvidenceCore.Json of
an object with the keys census_version, digest, card_count, slot_count,
game_dll ([sha, state]) and census_text, in that order, UTF-8 without a byte
order mark. SeatEvidenceCore.Json is byte-identical to the server's
json.dumps(separators=(",", ":"), ensure_ascii=True) (SeatEvidenceCore.cs
header), which is card_measures.dumps; census_text is K.CensusText, the
canonical census {"census":1,"cards":[[name, rarity, allowMultiple,
categories|null, blacklisted|null, lock], ...]} that check_census_text holds
to its own canonical form.

VALID are dumps the server registers; REFUSED are dumps (or raw bodies) the
census route answers with anything but a registration, each with the route's
answer: (status, detail).
"""

import hashlib
import json

GAME_SHA = hashlib.sha256(b"census fixture game build").hexdigest()
OTHER_GAME_SHA = hashlib.sha256(b"census fixture other game build").hexdigest()


def dumps(obj):
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=True)


def cards(extra=()):
    """A pool as the client reads it: GameObject names, rarity 0..2, allowMultiple,
    category names or null, blacklisted category names or null, the gun lock;
    a null card slot is the empty name. `extra` appends entries."""
    out = [
        ["BombsAway", 1, 1, ["CardCategory_Bombs"], None, 0],
        ["Leach", 0, 1, None, None, 0],
        ["Huge", 0, 1, ["CardCategory_Size"], ["CardCategory_Size"], 0],
        ["Shotgun", 1, 0, ["CardCategory_Gun", "CardCategory_Spread"], ["CardCategory_Gun"], 1],
        ["", -1, 0, None, None, 0],
        ["Rock'n'Roll", 2, 0, [], None, 0],
        ['Quote"Card', 2, 1, None, [], 0],
    ]
    return out + [list(e) for e in extra]


def census_text(pool):
    return dumps({"census": 1, "cards": pool})


def dump(pool=None, slots=5, game_sha=GAME_SHA, state="ok", **override):
    pool = cards() if pool is None else pool
    text = census_text(pool)
    d = {"census_version": 1, "digest": hashlib.sha256(text.encode("ascii")).hexdigest(),
         "card_count": len(pool), "slot_count": slots,
         "game_dll": [game_sha if state == "ok" else "", state], "census_text": text}
    d.update(override)
    return d


def client_bytes(d):
    """The file the client writes for dump `d`."""
    return dumps(d).encode("utf-8")


def _reordered():
    d = dump()
    return {k: d[k] for k in ("digest", "census_version", "card_count", "slot_count", "game_dll", "census_text")}


def _spaced():
    text = json.dumps({"census": 1, "cards": cards()}, ensure_ascii=True)
    return dump(census_text=text, digest=hashlib.sha256(text.encode("ascii")).hexdigest())


def _non_ascii():
    text = census_text(cards()).replace("Leach", "Leäch")
    return dump(census_text=text, digest=hashlib.sha256(text.encode("utf-8")).hexdigest())


def _bad_card(entry):
    pool = cards(extra=[entry])
    return dump(pool=pool)


VALID = {
    "client_file": client_bytes(dump()),
    "client_file_bom": b"\xef\xbb\xbf" + client_bytes(dump()),
    "pretty_printed_outer": json.dumps(dump(), indent=2).encode("utf-8"),
    "zero_slots_one_card": client_bytes(dump(pool=[["Leach", 0, 1, None, None, 0]], slots=0)),
}

# name -> (body bytes, the route's answer (status, detail) when signed over the dump's digest)
REFUSED = {
    "not_json": (b"{not json", (400, "body")),
    "bad_utf8": (b'{"digest":"\xff"}', (400, "body")),
    "empty_body": (b"", (400, "body")),
    "a_json_array": (b"[]", (422, "digest")),
    "no_digest": (client_bytes({k: v for k, v in dump().items() if k != "digest"}), (422, "digest")),
    "digest_not_a_string": (client_bytes(dump(digest=12345)), (422, "digest")),
    "digest_over_64": (client_bytes(dump(digest="a" * 65)), (422, None)),
    "keys_reordered": (client_bytes(_reordered()), (422, "dump_keys")),
    "extra_key": (client_bytes(dict(dump(), extra=1)), (422, "dump_keys")),
    "census_version_2": (client_bytes(dump(census_version=2)), (422, "census_version")),
    "census_text_not_canonical": (client_bytes(_spaced()), (422, "census_canonical")),
    "census_text_non_ascii": (client_bytes(_non_ascii()), (422, "census_text")),
    "digest_of_other_text": (client_bytes(dump(digest=hashlib.sha256(b"other").hexdigest())), (422, "digest")),
    "card_count_off_by_one": (client_bytes(dump(card_count=len(cards()) - 1)), (422, "card_count")),
    "card_count_float": (json.dumps(dump()).replace('"card_count": %d' % len(cards()),
                                                     '"card_count": %d.0' % len(cards())).encode(),
                         (422, "card_count")),
    "slot_count_100": (client_bytes(dump(slots=100)), (422, "slot_count")),
    "game_dll_read_failed": (client_bytes(dump(state="read_failed")), (422, "game_dll")),
    "game_dll_upper_hex": (client_bytes(dump(game_dll=[GAME_SHA.upper(), "ok"])), (422, "game_dll")),
    "card_rarity_bool": (client_bytes(_bad_card(["Bool", True, 1, None, None, 0])), (422, "census_card")),
    "card_width_5": (client_bytes(_bad_card(["Short", 0, 1, None, None])), (422, "census_card")),
    # census_text nested past the json module's recursion limit: check_census_text's json.loads raises
    # RecursionError, which no handler on the route catches, so the route answers 500 and stores nothing
    "census_text_deep_nesting": (client_bytes(dump(census_text="[" * 100000 + "]" * 100000)), (500, None)),
}
