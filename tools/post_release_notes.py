#!/usr/bin/env python3
"""post_release_notes.py — push translated release notes for one tag.

Ship step 11 requires the release body in every language in I18N_LANGS, because
the client pulls release text straight from the GitHub API and GitHub only has
the English. Without this, non-English players read the Home tab update text in
English.

Usage (Sid's PC, needs the admin secret in the environment):
    set ADMIN_HMAC_SECRET=...          (never in the repo / never in argv)
    python tools/post_release_notes.py --admin <steam64> --tag v1.37.0 \\
        --notes-dir dist/release-notes-v1.37.0

The notes dir holds one file per language, named <lang>.md (en.md, es.md, ru.md).
Aug 7 item 6: ENGLISH IS POSTED TOO — the Home tab's primary source is now the
server's own uncut store (/api/v1/release-notes/full/{locale}); the Discord
mirror only ever carried what one 2000-char message could, and GitHub is the
last-resort fallback. English rows are marked source=human.

For es/ru, `source` is left at the server default `machine`, which makes the
client append a "machine translation" note. That is deliberate: Sid cannot
read these, so players must know a human did not write them.

The HMAC canonical mirrors the server's _admin_canonical exactly:
    admin:{steam_id}:release_notes:{tag}:{lang}
A mismatch is a 403 "Bad admin signature", not a silent no-op.
"""
import argparse
import hmac
import hashlib
import json
import os
import sys
import urllib.error
import urllib.request

BASE = os.environ.get("SCR_API_BASE", "http://192.168.72.90:8443")
LANGS = ("en", "es", "ru")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--admin", required=True, help="admin steam64")
    ap.add_argument("--tag", required=True, help="release tag, e.g. v1.37.0")
    ap.add_argument("--notes-dir", required=True)
    ap.add_argument("--langs", default=",".join(LANGS))
    args = ap.parse_args()

    secret = os.environ.get("ADMIN_HMAC_SECRET", "")
    if not secret:
        print("ADMIN_HMAC_SECRET not set", file=sys.stderr)
        return 2

    rc = 0
    for lang in [x.strip() for x in args.langs.split(",") if x.strip()]:
        path = os.path.join(args.notes_dir, f"{lang}.md")
        if not os.path.exists(path):
            print(f"{lang}: {path} missing — SKIPPED (client keeps English)")
            rc = 1
            continue
        body = open(path, encoding="utf-8").read()
        if len(body) > 8000:
            # Server clamps to 8000; a silent truncation would cut a note
            # mid-sentence in one language only.
            print(f"{lang}: body is {len(body)} chars, server clamps at 8000 "
                  f"— shorten it", file=sys.stderr)
            rc = 1
            continue

        canonical = f"admin:{args.admin}:release_notes:{args.tag}:{lang}"
        sig = hmac.new(secret.encode(), canonical.encode(), hashlib.sha256).hexdigest()
        payload = json.dumps({
            "admin_steam_id": args.admin,
            "tag": args.tag,
            "language_code": lang,
            "body": body,
            # English is the canonical text Sid can read — mark it human so
            # the client never appends the machine-translation footer to it.
            **({"source": "human"} if lang == "en" else {}),
            # The handler reads "signature", NOT "hmac_signature" (main.py:11325).
            # Sending the wrong key is a 403 "Bad admin signature" that looks
            # exactly like a wrong secret — verified against the handler.
            "signature": sig,
        }).encode("utf-8")

        req = urllib.request.Request(
            f"{BASE}/api/v1/admin/release-notes",
            data=payload,
            headers={"Content-Type": "application/json", "X-Mod-Version": "99.0.0"},
            method="POST")
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                print(f"{lang}: {resp.status} {resp.read().decode('utf-8', 'replace')[:160]}")
        except urllib.error.HTTPError as e:
            # 403 "Bad admin signature" -> secret mismatch or a canonical drift.
            # 403 "Not an admin"        -> that steam id has no live admin row.
            print(f"{lang}: HTTP {e.code} {e.read().decode('utf-8', 'replace')[:200]}",
                  file=sys.stderr)
            rc = 1
        except Exception as e:  # noqa: BLE001
            print(f"{lang}: {e}", file=sys.stderr)
            rc = 1

    print()
    print("Verify:  curl -sS -H \"X-Mod-Version: 1.37.0\" "
          f"{BASE}/api/v1/release-notes/ru   (expect the new tag)")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
