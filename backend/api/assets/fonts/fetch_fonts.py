#!/usr/bin/env python3
"""Fetch the Player Cards renderer fonts from commit-pinned URLs.

The font FILES are not committed (gitignored, ~30 MB); this script fetches
them for the Docker build and for local tests, and `fonts.lock.json` pins
the SHA-256 of every file so two builds of one ref use identical bytes.

    python fetch_fonts.py            # fetch + verify against the lock
    python fetch_fonts.py --record   # first fetch: write the lock

All fonts are OFL-licensed (Noto, Kalam).
"""
import hashlib
import json
import os
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
LOCK = os.path.join(HERE, "fonts.lock.json")

# name -> commit-pinned raw URL (never a moving branch)
FONTS = {
    "NotoSans-Bold.ttf":
        "https://raw.githubusercontent.com/notofonts/notofonts.github.io/"
        "92d2ea744479d3379927f1fb5f8b0945dd0349b7/fonts/NotoSans/unhinted/ttf/NotoSans-Bold.ttf",
    "NotoSans-Black.ttf":
        "https://raw.githubusercontent.com/notofonts/notofonts.github.io/"
        "92d2ea744479d3379927f1fb5f8b0945dd0349b7/fonts/NotoSans/unhinted/ttf/NotoSans-Black.ttf",
    "NotoSansCJKsc-Bold.otf":
        "https://raw.githubusercontent.com/notofonts/noto-cjk/"
        "f8d157532fbfaeda587e826d4cd5b21a49186f7c/Sans/OTF/SimplifiedChinese/NotoSansCJKsc-Bold.otf",
    "NotoColorEmoji.ttf":
        "https://raw.githubusercontent.com/googlefonts/noto-emoji/"
        "8998f5dd683424a73e2314a8c1f1e359c19e8742/fonts/NotoColorEmoji.ttf",
    "Kalam-Bold.ttf":
        "https://raw.githubusercontent.com/google/fonts/"
        "809e4d8b8d7e9364a914909bb777679606c178b8/ofl/kalam/Kalam-Bold.ttf",
    "NotoSansSymbols2-Regular.ttf":
        "https://raw.githubusercontent.com/google/fonts/"
        "809e4d8b8d7e9364a914909bb777679606c178b8/ofl/notosanssymbols2/NotoSansSymbols2-Regular.ttf",
    # The scripts players' names are actually written in (§1.3). Without these
    # the coverage projection of §2.4 removes an entire Arabic or Hebrew name
    # and the card falls back to the neutral label — the renderer decides what
    # a name may contain, so its font set is a product decision, not packaging.
    "NotoSansArabic-Bold.ttf":
        "https://raw.githubusercontent.com/notofonts/notofonts.github.io/92d2ea744479d3379927f1fb5f8b0945dd0349b7/fonts/"
        "NotoSansArabic/unhinted/ttf/NotoSansArabic-Bold.ttf",
    "NotoSansHebrew-Bold.ttf":
        "https://raw.githubusercontent.com/notofonts/notofonts.github.io/92d2ea744479d3379927f1fb5f8b0945dd0349b7/fonts/"
        "NotoSansHebrew/unhinted/ttf/NotoSansHebrew-Bold.ttf",
    "NotoSansThai-Bold.ttf":
        "https://raw.githubusercontent.com/notofonts/notofonts.github.io/92d2ea744479d3379927f1fb5f8b0945dd0349b7/fonts/"
        "NotoSansThai/unhinted/ttf/NotoSansThai-Bold.ttf",
    "NotoSansDevanagari-Bold.ttf":
        "https://raw.githubusercontent.com/notofonts/notofonts.github.io/92d2ea744479d3379927f1fb5f8b0945dd0349b7/fonts/"
        "NotoSansDevanagari/unhinted/ttf/NotoSansDevanagari-Bold.ttf",
    "NotoSansBengali-Bold.ttf":
        "https://raw.githubusercontent.com/notofonts/notofonts.github.io/92d2ea744479d3379927f1fb5f8b0945dd0349b7/fonts/"
        "NotoSansBengali/unhinted/ttf/NotoSansBengali-Bold.ttf",
    "NotoSansTamil-Bold.ttf":
        "https://raw.githubusercontent.com/notofonts/notofonts.github.io/92d2ea744479d3379927f1fb5f8b0945dd0349b7/fonts/"
        "NotoSansTamil/unhinted/ttf/NotoSansTamil-Bold.ttf",
    "NotoSansGeorgian-Bold.ttf":
        "https://raw.githubusercontent.com/notofonts/notofonts.github.io/92d2ea744479d3379927f1fb5f8b0945dd0349b7/fonts/"
        "NotoSansGeorgian/unhinted/ttf/NotoSansGeorgian-Bold.ttf",
    "NotoSansArmenian-Bold.ttf":
        "https://raw.githubusercontent.com/notofonts/notofonts.github.io/92d2ea744479d3379927f1fb5f8b0945dd0349b7/fonts/"
        "NotoSansArmenian/unhinted/ttf/NotoSansArmenian-Bold.ttf",
    "NotoSansSymbols-Bold.ttf":
        "https://raw.githubusercontent.com/notofonts/notofonts.github.io/92d2ea744479d3379927f1fb5f8b0945dd0349b7/fonts/"
        "NotoSansSymbols/unhinted/ttf/NotoSansSymbols-Bold.ttf",
}


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main(argv):
    record = "--record" in argv
    lock = {}
    if os.path.exists(LOCK):
        with open(LOCK, "r", encoding="utf-8") as f:
            lock = json.load(f)
    if not record and set(lock) != set(FONTS):
        print("fonts.lock.json does not list exactly the fonts of FONTS; run --record", file=sys.stderr)
        return 2
    out = {}
    for name, url in FONTS.items():
        path = os.path.join(HERE, name)
        if not os.path.exists(path) or (not record and sha256_of(path) != lock[name]["sha256"]):
            tmp = path + ".part"
            req = urllib.request.Request(url, headers={"User-Agent": "scr-fetch-fonts/1"})
            with urllib.request.urlopen(req, timeout=120) as r, open(tmp, "wb") as f:
                while True:
                    chunk = r.read(1 << 20)
                    if not chunk:
                        break
                    f.write(chunk)
            os.replace(tmp, path)
        digest = sha256_of(path)
        size = os.path.getsize(path)
        if not record and digest != lock[name]["sha256"]:
            print("%s: sha256 %s != locked %s" % (name, digest, lock[name]["sha256"]), file=sys.stderr)
            return 1
        out[name] = {"sha256": digest, "bytes": size, "url": url}
        print("%-32s %10d  %s" % (name, size, digest))
    if record:
        with open(LOCK, "w", encoding="utf-8") as f:
            json.dump(out, f, indent=2, sort_keys=True)
            f.write("\n")
        print("wrote", LOCK)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
