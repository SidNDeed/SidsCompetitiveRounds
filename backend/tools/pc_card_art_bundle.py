"""The top-card art bundle tool (Discord card render parity, board row 33).

The bundle is private and never committed: this file carries no art. It
builds, validates and synthesises bundles in the one format pc_face reads
(index.json + one PNG per canonical name + BUNDLE-DIGEST), through pc_face's
own writer and per-entry check, so a PASS here is exactly what the renderer
accepts.

  validate <bundle_dir>
      One line per index entry, PASS or FAIL with the reason; then the
      renderer's whole-bundle verdict, the entry count and BUNDLE-DIGEST.
      Exit 0 only when the renderer would accept the bundle.
  build <harvest_dir> <out_root>
      Compose a harvest (harvest.tsv + raw thumbnail PNGs + DONE, written by
      the seat-only harvest plugin) into a bundle: each thumbnail fitted,
      aspect kept, into the art rect (columns 2..80 of the 80x104 backing,
      the client's preserveAspect box) over the badge backing colour. The
      bundle lands in <out_root>/pc-cards-<digest[:12]>/. Prints the digest.
  synth <dest_dir>
      A synthetic bundle for every expected name (procedural pixels, no art).

Runs from a checkout (pc_face is found at ../api) or inside the api image
(/app), and also when piped to `python - <args>` there.
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path


def _import_pc_face():
    here = None
    try:
        here = Path(__file__).resolve().parent
    except NameError:
        pass
    for candidate in ([here.parent / "api"] if here else []) + [Path("/app")]:
        if (candidate / "pc_face.py").is_file():
            sys.path.insert(0, str(candidate))
            break
    import pc_face  # noqa: E402
    return pc_face


pc_face = _import_pc_face()
from PIL import Image  # noqa: E402


def _art_box():
    back = pc_face.LAYOUT["rects"]["badge_art_back"]
    art = pc_face.LAYOUT["rects"]["badge_art"]
    return (art[0] - back[0], art[1] - back[1], art[2] - back[0], art[3] - back[1])


def compose(thumb: Image.Image) -> Image.Image:
    """One 80x104 opaque patch: the backing colour, and the thumbnail fitted
    into the art box with its aspect kept and centred (Unity preserveAspect)."""
    back = tuple(pc_face.LAYOUT["colours"]["badge_art_back"]) + (255,)
    patch = Image.new("RGBA", (pc_face.CARD_ART_W, pc_face.CARD_ART_H), back)
    x0, y0, x1, y1 = _art_box()
    bw, bh = x1 - x0, y1 - y0
    thumb = thumb.convert("RGBA")
    scale = min(bw / thumb.width, bh / thumb.height)
    w, h = max(1, round(thumb.width * scale)), max(1, round(thumb.height * scale))
    fitted = thumb.resize((w, h), Image.Resampling.LANCZOS)
    layer = Image.new("RGBA", patch.size, (0, 0, 0, 0))
    layer.paste(fitted, (x0 + (bw - w) // 2, y0 + (bh - h) // 2))
    patch.alpha_composite(layer)
    patch.putalpha(255)
    return patch


def _read_harvest(harvest_dir: Path):
    done = (harvest_dir / "DONE").read_text(encoding="utf-8")
    facts = dict(line.split("=", 1) for line in done.splitlines() if "=" in line and not line.startswith("missing="))
    rows = (harvest_dir / "harvest.tsv").read_text(encoding="utf-8").splitlines()
    header = rows[0].split("\t")
    out = {}
    for line in rows[1:]:
        if not line.strip():
            continue
        rec = dict(zip(header, line.split("\t")))
        out[rec["name"]] = rec
    return facts, out


def build(harvest_dir: Path, out_root: Path) -> int:
    facts, rows = _read_harvest(harvest_dir)
    names = pc_face.card_art_names()
    missing = [n for n in names if n not in rows]
    extra = [n for n in rows if n not in names]
    print(f"harvest: names={facts.get('names')} saved={facts.get('saved')} failed={facts.get('failed')} "
          f"color_space={facts.get('color_space')}")
    if missing or extra:
        print(f"REFUSED: harvest lacks {len(missing)} expected name(s), carries {len(extra)} unexpected")
        for n in missing:
            print(f"  missing {n}")
        return 2
    patches = {}
    sizes = set()
    for name in names:
        with Image.open(harvest_dir / rows[name]["file"]) as raw:
            raw.load()
            sizes.add(raw.size)
            patches[name] = compose(raw)
    out_root.mkdir(parents=True, exist_ok=True)
    staging = out_root / ("pc-cards-building-" + hashlib.sha256(repr(sorted(rows)).encode()).hexdigest()[:8])
    digest = pc_face.card_art_write_bundle(staging, patches)
    final = out_root / f"pc-cards-{digest[:12]}"
    if final.exists():
        print(f"REFUSED: {final.name} exists already (bundles are immutable); the new copy stays at {staging.name}")
        return 3
    staging.rename(final)
    print(f"thumbnail sizes: {sorted(sizes)}")
    print(f"bundle: {final.name} entries={len(patches)} BUNDLE-DIGEST={digest}")
    return 0


def validate(bundle_dir: Path) -> int:
    import json
    names = pc_face.card_art_names()
    fails = 0
    try:
        index = json.loads((bundle_dir / pc_face.CARD_ART_INDEX).read_text(encoding="utf-8"))
        cards = index.get("cards", {}) if isinstance(index, dict) else {}
    except (OSError, ValueError) as exc:
        print(f"FAIL index.json: {type(exc).__name__}")
        cards = {}
        fails += 1
    for name in sorted(set(cards) | set(names)):
        if name not in cards:
            print(f"FAIL {name}: not in the index")
            fails += 1
            continue
        if name not in names:
            print(f"FAIL {name}: not an expected name")
            fails += 1
            continue
        try:
            pc_face.card_art_check_entry(bundle_dir, cards[name])
            print(f"PASS {name}")
        except (ValueError, KeyError, TypeError) as exc:
            print(f"FAIL {name}: {exc}")
            fails += 1
    stamps = pc_face._card_art_stamps(bundle_dir)
    verdict = pc_face._card_art_bundle_at(str(bundle_dir), names, stamps)
    digest_file = bundle_dir / pc_face.CARD_ART_DIGEST_FILE
    recorded = digest_file.read_text(encoding="ascii").strip() if digest_file.is_file() else "<none>"
    print(f"entries={len(cards)} expected={len(names)} entry_fails={fails}")
    print(f"BUNDLE-DIGEST={recorded}")
    print(f"renderer verdict: {verdict.status}" + (f" ({verdict.reason})" if verdict.reason else ""))
    return 0 if verdict.status == "accepted" and fails == 0 else 1


def synth(dest: Path) -> int:
    patches = {}
    for name in pc_face.card_art_names():
        seed = hashlib.sha256(name.encode("utf-8")).digest()
        thumb = Image.new("RGBA", (60, 80), (seed[0], seed[1], seed[2], 255))
        for y in range(0, 80, 8):
            thumb.paste((seed[3], seed[4], seed[5], 255), (0, y, 60, y + 4))
        patches[name] = compose(thumb)
    digest = pc_face.card_art_write_bundle(dest, patches)
    print(f"synthetic bundle: entries={len(patches)} BUNDLE-DIGEST={digest}")
    return 0


def main(argv) -> int:
    if len(argv) >= 3 and argv[1] == "validate":
        return validate(Path(argv[2]))
    if len(argv) >= 4 and argv[1] == "build":
        return build(Path(argv[2]), Path(argv[3]))
    if len(argv) >= 3 and argv[1] == "synth":
        return synth(Path(argv[2]))
    print(__doc__)
    return 64


if __name__ == "__main__":
    sys.exit(main(sys.argv))
