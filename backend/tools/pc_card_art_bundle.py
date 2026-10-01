"""The top-card art bundle tool (Discord card render parity, board row 33).

The bundle is private and never committed: this file carries no art. It
builds, validates and synthesises bundles in the one format pc_face reads
(index.json + one PNG per canonical name + BUNDLE-DIGEST), through pc_face's
own writer and per-entry checks, so a PASS here is exactly what the renderer
accepts. The art is the game's own card art, harvested on the seat by the
seat-only harvest plugin.

  validate <bundle_dir> [--harvest <harvest_dir>]
      One line per index entry, PASS or FAIL with the reason; the provenance
      verdict; the name set against the server's card table; then the
      renderer's whole-bundle verdict, the entry count and BUNDLE-DIGEST.
      With --harvest, every patch is also re-composed from that harvest and
      must be byte-identical. Exit 0 only when every check passes.
  build <harvest_dir> <out_root>
      Admit a harvest (harvest format 2: harvest.tsv + raw thumbnail PNGs +
      DONE, written by the harvest plugin) and compose it into a bundle. The
      harvest must be complete and English, carry the game and mod build and
      the MEASURED backing colour, and every row must be unique and bound to
      its own file. Each thumbnail must pass the content floors. The bundle
      lands in <out_root>/pc-cards-<digest[:12]>/ and is re-validated before
      it is named. Prints every refusal; exit 2 on any.
  synth <dest_dir>
      A synthetic bundle for every expected name (procedural pixels, no art).

Runs from a checkout (pc_face is found at ../api) or inside the api image
(/app), and also when piped to `python - <args>` there.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path


def _here():
    try:
        return Path(__file__).resolve().parent
    except NameError:
        return None


def _import_pc_face():
    here = _here()
    for candidate in ([here.parent / "api"] if here else []) + [Path("/app")]:
        if (candidate / "pc_face.py").is_file():
            sys.path.insert(0, str(candidate))
            break
    import pc_face  # noqa: E402
    return pc_face


pc_face = _import_pc_face()
from PIL import Image  # noqa: E402

HARVEST_FORMAT = 2
TSV_COLUMNS = ("index", "name", "file", "w", "h", "rect_x", "rect_y", "tex_w", "tex_h", "readable",
               "sha256", "name_bind", "language", "rounds_locale", "game_build", "mod_build")

# The server's own card table: pc_card_themes, seeded by migration 333. Parsed
# from the migration file itself (the same row pattern as the tests' reader).
_MIGRATION_333 = "333_pc_card_themes.sql"
_ROW = re.compile(r"\(\s*'((?:[^']|'')*)'\s*,\s*'((?:[^']|'')*)'\s*,"
                  r"\s*'(#[0-9A-Fa-f]{6})'\s*,\s*'(#[0-9A-Fa-f]{6})'\s*\)")


def server_card_names(sql_dir: Path | None = None):
    """The canonical names of the server's card table (migration 333), or
    None when the migration file is not reachable (inside the api image)."""
    here = _here()
    path = (sql_dir or (here.parent / "sql" if here else Path("/nonexistent"))) / _MIGRATION_333
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8")
    body = text.split("VALUES", 1)[1].split("ON CONFLICT", 1)[0]
    names = [m.group(1).replace("''", "'") for m in _ROW.finditer(body)]
    return tuple(sorted(names)) if names else ()


def is_english(code) -> bool:
    return isinstance(code, str) and (code == "en" or code.startswith("en-"))


def compose(thumb: Image.Image, backing=None) -> Image.Image:
    """One opaque patch of pc_face.card_art_size(): the backing colour, and the thumbnail fitted
    into the art box with its aspect kept and centred (Unity preserveAspect),
    at pc_face.card_art_fit_box."""
    back = tuple(backing or pc_face.card_art_backing_rgb()) + (255,)
    patch = Image.new("RGBA", pc_face.card_art_size(), back)
    thumb = thumb.convert("RGBA")
    x0, y0, x1, y1 = pc_face.card_art_fit_box(thumb.width, thumb.height)
    fitted = thumb.resize((x1 - x0, y1 - y0), Image.Resampling.LANCZOS)
    layer = Image.new("RGBA", patch.size, (0, 0, 0, 0))
    layer.paste(fitted, (x0, y0))
    patch.alpha_composite(layer)
    patch.putalpha(255)
    return patch


def _facts(text: str) -> dict:
    out = {}
    for line in text.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            out.setdefault(key, []).append(value)
    return out


def _one(facts: dict, key: str):
    values = facts.get(key) or []
    return values[0] if len(values) == 1 else None


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def admit_harvest(harvest_dir: Path, sql_dir: Path | None = None):
    """(refusals, admitted) for a harvest directory. `admitted` carries the
    provenance block, the per-name rows and the decoded thumbnails, and is
    usable only when `refusals` is empty."""
    harvest_dir = Path(harvest_dir)
    refusals: list[str] = []
    admitted = {"rows": {}, "thumbs": {}, "provenance": None}

    if (harvest_dir / "REFUSED").exists():
        refusals.append("the harvest wrote REFUSED: "
                        + "; ".join(_facts((harvest_dir / "REFUSED").read_text(encoding="utf-8")).get("refused", [])))
    if not (harvest_dir / "DONE").is_file():
        refusals.append("no DONE marker (the harvest did not finish as a complete run)")
        return refusals, admitted
    facts = _facts((harvest_dir / "DONE").read_text(encoding="utf-8"))
    fmt = _one(facts, "harvest_format")
    if fmt is None or not fmt.isdigit() or int(fmt) < HARVEST_FORMAT:
        refusals.append(f"harvest_format {fmt!r} is older than {HARVEST_FORMAT} (no provenance)")
        return refusals, admitted
    if _one(facts, "complete") != "1" or facts.get("refused") or facts.get("missing"):
        refusals.append("DONE does not record a complete run (complete=%r, %d missing, %d refused)"
                        % (_one(facts, "complete"), len(facts.get("missing", [])), len(facts.get("refused", []))))
    language, rounds_locale = _one(facts, "language"), _one(facts, "rounds_locale")
    if not is_english(language):
        refusals.append(f"the harvest's mod language is {language!r}, not English")
    if not is_english(rounds_locale):
        refusals.append(f"the harvest's ROUNDS locale is {rounds_locale!r}, not English")
    game_build, mod_build = _one(facts, "game_build"), _one(facts, "mod_build")
    for key, value in (("game_build", game_build), ("mod_build", mod_build)):
        if not value or not value.strip() or value.strip() == "unknown":
            refusals.append(f"DONE lacks {key}")
    backing = None
    measured = _one(facts, "backing_measured")
    try:
        backing = tuple(int(v) for v in (measured or "").split(","))
        if len(backing) != 3 or not all(0 <= v <= 255 for v in backing):
            raise ValueError
    except ValueError:
        refusals.append(f"DONE lacks a measured backing colour ({measured!r})")
        backing = None
    if backing is not None and backing != pc_face.card_art_backing_rgb():
        refusals.append(f"the measured backing {backing} is not face_layout_v1.json colours.badge_art_back "
                        f"{pc_face.card_art_backing_rgb()}: the layout must carry the measured value")
    method = _one(facts, "backing_method")
    if not method:
        refusals.append("DONE lacks backing_method")

    expected = pc_face.card_art_names()
    server = server_card_names(sql_dir)
    if server is None:
        refusals.append("the server's card table (migration 333) is not reachable from this checkout")
    elif server != expected:
        refusals.append(f"card_art_names.json differs from the server's card table: "
                        f"{len(set(server) - set(expected))} only in the table, "
                        f"{len(set(expected) - set(server))} only in the names file")
    slugs = [pc_face.card_art_slug(n) for n in expected]
    if len(set(slugs)) != len(slugs) or not all(slugs):
        refusals.append("two canonical names share one slug (or a slug is empty)")

    tsv_path = harvest_dir / "harvest.tsv"
    if not tsv_path.is_file():
        refusals.append("no harvest.tsv")
        return refusals, admitted
    lines = tsv_path.read_text(encoding="utf-8").splitlines()
    header = tuple(lines[0].split("\t")) if lines else ()
    if header != TSV_COLUMNS:
        refusals.append(f"harvest.tsv header is not format {HARVEST_FORMAT}: {list(header)}")
        return refusals, admitted
    seen_names, seen_files, seen_shas = {}, {}, {}
    rows = {}
    for number, line in enumerate(lines[1:], start=2):
        if not line.strip():
            continue
        cells = line.split("\t")
        if len(cells) != len(TSV_COLUMNS):
            refusals.append(f"harvest.tsv line {number}: {len(cells)} cells")
            continue
        rec = dict(zip(TSV_COLUMNS, cells))
        name = rec["name"]
        for seen, key, what in ((seen_names, name, "name"), (seen_files, rec["file"], "file"),
                                (seen_shas, rec["sha256"], "thumbnail sha256")):
            if key in seen:
                shown = key[:12] if what == "thumbnail sha256" else repr(key)
                refusals.append(f"duplicate source row: {what} {shown} on lines {seen[key]} and {number}")
            seen[key] = number
        rows.setdefault(name, rec)
    missing = [n for n in expected if n not in rows]
    extra = [n for n in rows if n not in expected]
    for n in missing:
        refusals.append(f"missing row: {n!r}")
    for n in extra:
        refusals.append(f"extra row: {n!r} is not a card of the server's table")
    on_disk = sorted(p.name for p in harvest_dir.glob("*.png"))
    named = sorted({rec["file"] for rec in rows.values()})
    for f in sorted(set(named) - set(on_disk)):
        refusals.append(f"missing file: {f}")
    for f in sorted(set(on_disk) - set(named)):
        refusals.append(f"extra file: {f} (no row names it)")

    for name in sorted(set(rows) & set(expected)):
        rec = rows[name]
        where = f"{name!r} ({rec['file']})"
        if not is_english(rec["language"]) or not is_english(rec["rounds_locale"]):
            refusals.append(f"{where}: captured in {rec['language']}/{rec['rounds_locale']}, not English")
        if rec["game_build"] != game_build or rec["mod_build"] != mod_build:
            refusals.append(f"{where}: game/mod build differs from DONE's")
        path = harvest_dir / rec["file"]
        if not path.is_file():
            continue
        data = path.read_bytes()
        if _sha(data) != rec["sha256"]:
            refusals.append(f"{where}: the file is not the thumbnail captured for this row (sha256 differs)")
            continue
        if _sha((name + "\n" + rec["sha256"]).encode("utf-8")) != rec["name_bind"]:
            refusals.append(f"{where}: the row's name is not the name the thumbnail was captured for (name_bind)")
            continue
        try:
            with Image.open(path) as raw:
                raw.load()
                thumb = raw.convert("RGBA")
        except Exception as exc:                     # noqa: BLE001 -- any decode failure refuses
            refusals.append(f"{where}: does not decode ({type(exc).__name__})")
            continue
        try:
            width, height = int(rec["w"]), int(rec["h"])
            rect = [int(rec["rect_x"]), int(rec["rect_y"]), width, height]
        except ValueError:
            refusals.append(f"{where}: source rect is not numeric")
            continue
        if thumb.size != (width, height):
            refusals.append(f"{where}: image {thumb.size} is not its recorded rect {width}x{height}")
            continue
        try:
            pc_face.card_art_content_check(thumb)
        except ValueError as exc:
            refusals.append(f"{where}: {exc}")
            continue
        admitted["rows"][name] = {"source_sha256": rec["sha256"], "source_rect": rect}
        admitted["thumbs"][name] = thumb
    admitted["provenance"] = {
        "language": language, "rounds_locale": rounds_locale,
        "game_build": game_build, "mod_build": mod_build, "harvest": harvest_dir.name,
        "backing_rgb": list(backing) if backing else None, "backing_method": method}
    return refusals, admitted


def build(harvest_dir: Path, out_root: Path, sql_dir: Path | None = None) -> int:
    refusals, admitted = admit_harvest(harvest_dir, sql_dir)
    prov = admitted.get("provenance") or {}
    print(f"harvest {Path(harvest_dir).name}: language={prov.get('language')} rounds_locale={prov.get('rounds_locale')} "
          f"game_build={prov.get('game_build')!r} mod_build={prov.get('mod_build')!r} backing={prov.get('backing_rgb')}")
    if refusals:
        print(f"REFUSED: {len(refusals)} check(s) failed; nothing written")
        for r in refusals:
            print(f"  {r}")
        return 2
    names = pc_face.card_art_names()
    patches = {n: compose(admitted["thumbs"][n], prov["backing_rgb"]) for n in names}
    out_root = Path(out_root)
    out_root.mkdir(parents=True, exist_ok=True)
    staging = out_root / ("pc-cards-building-" + _sha(repr(sorted(admitted["rows"].items())).encode())[:8])
    digest = pc_face.card_art_write_bundle(staging, patches, admitted["rows"], prov)
    if validate(staging, harvest_dir=harvest_dir, sql_dir=sql_dir, quiet=True) != 0:
        print(f"REFUSED: the written bundle does not validate; left at {staging.name}")
        return 4
    final = out_root / f"pc-cards-{digest[:12]}"
    if final.exists():
        print(f"REFUSED: {final.name} exists already (bundles are immutable); the new copy stays at {staging.name}")
        return 3
    staging.rename(final)
    sizes = sorted({tuple(admitted["thumbs"][n].size) for n in names})
    print(f"thumbnail sizes: {sizes}")
    print(f"bundle: {final.name} entries={len(patches)} tool_version={pc_face.CARD_ART_TOOL_VERSION} "
          f"BUNDLE-DIGEST={digest}")
    return 0


def validate(bundle_dir: Path, harvest_dir: Path | None = None, sql_dir: Path | None = None,
             quiet: bool = False) -> int:
    say = (lambda *_a, **_k: None) if quiet else print
    bundle_dir = Path(bundle_dir)
    names = pc_face.card_art_names()
    fails = 0
    index = {}
    try:
        index = json.loads((bundle_dir / pc_face.CARD_ART_INDEX).read_text(encoding="utf-8"))
        cards = index.get("cards", {}) if isinstance(index, dict) else {}
    except (OSError, ValueError) as exc:
        say(f"FAIL index.json: {type(exc).__name__}")
        cards = {}
        fails += 1
    try:
        if not isinstance(index, dict) or index.get("format") != pc_face.CARD_ART_FORMAT:
            raise ValueError(f"format {index.get('format') if isinstance(index, dict) else None!r} "
                             f"is not {pc_face.CARD_ART_FORMAT}")
        pc_face.card_art_check_provenance(index)
        say(f"PASS provenance: tool_version={index['tool_version']} {json.dumps(index['provenance'], sort_keys=True)}")
    except ValueError as exc:
        say(f"FAIL provenance: {exc}")
        fails += 1
    want_geometry = pc_face.card_art_geometry_record()
    if isinstance(index, dict) and index.get("geometry") == want_geometry:
        say(f"PASS geometry: {json.dumps(want_geometry, sort_keys=True)}")
    else:
        got = index.get("geometry") if isinstance(index, dict) else None
        say(f"FAIL geometry: the bundle was cut for {got!r}, the layout is {want_geometry!r}")
        fails += 1
    server = server_card_names(sql_dir)
    if server is None:
        say("NOTE server card table: migration 333 is not reachable here; card_art_names.json stands for it")
    elif server != names:
        say("FAIL server card table: card_art_names.json differs from migration 333")
        fails += 1
    else:
        say(f"PASS server card table: {len(server)} names, equal to card_art_names.json")
    sources = {}
    for name in sorted(set(cards) | set(names)):
        if name not in cards:
            say(f"FAIL {name}: not in the index")
            fails += 1
            continue
        if name not in names:
            say(f"FAIL {name}: not an expected name")
            fails += 1
            continue
        try:
            pc_face.card_art_check_entry_shape(name, cards[name])
            pc_face.card_art_check_entry(bundle_dir, cards[name])
            sources.setdefault(cards[name]["source_sha256"], []).append(name)
            say(f"PASS {name}")
        except (ValueError, KeyError, TypeError) as exc:
            say(f"FAIL {name}: {exc}")
            fails += 1
    for sha, owners in sorted(sources.items()):
        if len(owners) > 1:
            say(f"FAIL source thumbnail {sha[:12]} is shared by {owners}")
            fails += 1
    if harvest_dir is not None:
        refusals, admitted = admit_harvest(Path(harvest_dir), sql_dir)
        if refusals:
            say(f"FAIL harvest {Path(harvest_dir).name}: {len(refusals)} refusal(s): {refusals[:3]}")
            fails += 1
        else:
            prov = admitted["provenance"]
            if index.get("provenance") != prov:
                say("FAIL harvest: the bundle's provenance is not this harvest's")
                fails += 1
            differ = []
            for name in names:
                entry = cards.get(name) or {}
                want = pc_face._encode_rgba(compose(admitted["thumbs"][name], prov["backing_rgb"]))
                if (entry.get("sha256") != _sha(want)
                        or entry.get("source_sha256") != admitted["rows"][name]["source_sha256"]
                        or entry.get("source_rect") != admitted["rows"][name]["source_rect"]):
                    differ.append(name)
            if differ:
                say(f"FAIL harvest: {len(differ)} patch(es) are not the composition of this harvest: {differ[:5]}")
                fails += 1
            else:
                say(f"PASS harvest {Path(harvest_dir).name}: every patch re-composes byte-identically")
    stamps = pc_face._card_art_stamps(bundle_dir)
    verdict = pc_face._card_art_bundle_at(str(bundle_dir), names, pc_face.card_art_geometry(), stamps)
    digest_file = bundle_dir / pc_face.CARD_ART_DIGEST_FILE
    recorded = digest_file.read_text(encoding="ascii").strip() if digest_file.is_file() else "<none>"
    say(f"entries={len(cards)} expected={len(names)} entry_fails={fails}")
    say(f"BUNDLE-DIGEST={recorded}")
    say(f"renderer verdict: {verdict.status}" + (f" ({verdict.reason})" if verdict.reason else ""))
    return 0 if verdict.status == "accepted" and fails == 0 else 1


def synth(dest: Path) -> int:
    patches, sources = {}, {}
    for name in pc_face.card_art_names():
        seed = hashlib.sha256(name.encode("utf-8")).digest()
        thumb = Image.new("RGBA", (60, 80), (64 + seed[0] % 192, 64 + seed[1] % 192, 64 + seed[2] % 192, 255))
        for y in range(0, 80, 8):
            thumb.paste((seed[3] % 64, seed[4] % 64, seed[5] % 64, 255), (0, y, 60, y + 4))
        patches[name] = compose(thumb)
        sources[name] = {"source_sha256": _sha(b"synthetic-source\n" + name.encode("utf-8")),
                         "source_rect": [0, 0, 60, 80]}
    prov = {"language": "en", "rounds_locale": "en", "game_build": "synthetic bundle (no art)",
            "mod_build": "synthetic bundle (no art)", "harvest": "synthetic",
            "backing_rgb": list(pc_face.card_art_backing_rgb()),
            "backing_method": "synthetic: the layout constant"}
    digest = pc_face.card_art_write_bundle(dest, patches, sources, prov)
    print(f"synthetic bundle: entries={len(patches)} BUNDLE-DIGEST={digest}")
    return 0


def main(argv) -> int:
    if len(argv) >= 3 and argv[1] == "validate":
        harvest = None
        if len(argv) == 5 and argv[3] == "--harvest":
            harvest = Path(argv[4])
        elif len(argv) != 3:
            print(__doc__)
            return 64
        return validate(Path(argv[2]), harvest_dir=harvest)
    if len(argv) == 4 and argv[1] == "build":
        return build(Path(argv[2]), Path(argv[3]))
    if len(argv) == 3 and argv[1] == "synth":
        return synth(Path(argv[2]))
    print(__doc__)
    return 64


if __name__ == "__main__":
    sys.exit(main(sys.argv))
