#!/usr/bin/env python3
"""Release-time key sync: push tools/i18n_source.json (the extractor output)
to POST /api/v1/admin/i18n/sync-keys so the portal and pack serve the current
key set.

Usage (Sid's PC, needs the admin secret in the environment):
    set ADMIN_HMAC_SECRET=...          (never in the repo / never in argv)
    python tools/i18n_sync_keys.py [--base https://competitive-rounds.duckdns.org:8444] \
                                   [--admin 76561198040410653]

key_id/source_hash follow localization-design §2.3:
    key_id      = sha1(namespace + "\\0" + msgctxt)[:16]
    source_hash = sha1(source_text)
The HMAC canonical mirrors the server's _verify_admin_hmac for action
'i18n_sync' with target 'n=<count>'.
"""
import argparse
import hashlib
import hmac
import io
import json
import os
import sys
import urllib.error
import urllib.request

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "tools", "i18n_source.json")

# Strings whose approval is admin-only (§2.5 'sensitive' class): penalty and
# forfeit warnings, gold-spend confirmations, consent, bans. Substring match
# against the English source keeps this list short and future-tolerant.
# Wave-2 find 6: consent-adjacent TOGGLES belong here too — a moderator
# translating "Allow data reporting" as its opposite would invert what
# clicking the button appears to do, so those strings need an admin's eyes.
SENSITIVE_MARKERS = (
    "penalt", "forfeit", "gold", "consent", "ban", "will be recorded",
    "counts as a loss", "purchase",
    "data reporting", "offline", "delete", "reset", "ranked",
    # Round-3 find N4: the live consent-enabling prose ("Allow the mod to
    # report your match results and stats to the community server.") matched
    # nothing above — cover permission-granting language generally.
    "allow the mod", "match results", "community server", "revoke",
)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="https://competitive-rounds.duckdns.org:8444")
    ap.add_argument("--admin", default="76561198040410653")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    secret = os.environ.get("ADMIN_HMAC_SECRET", "")
    if not secret and not args.dry_run:
        print("ADMIN_HMAC_SECRET not set", file=sys.stderr)
        return 2

    data = json.load(io.open(SRC, encoding="utf-8"))
    keys = []
    for s in data["strings"]:
        kid = hashlib.sha1(("client\0" + s).encode("utf-8")).hexdigest()[:16]
        low = s.lower()
        keys.append({
            "key_id": kid,
            "namespace": "client",
            "msgctxt": s,
            "source_hash": hashlib.sha1(s.encode("utf-8")).hexdigest(),
            "sensitive": any(m in low for m in SENSITIVE_MARKERS),
        })

    print(f"{len(keys)} keys ({sum(1 for k in keys if k['sensitive'])} sensitive)")
    if args.dry_run:
        return 0

    # Server canonical: _admin_canonical = f"admin:{steam_id}:{action}:{target}"
    target = f"n={len(keys)}"
    sig = hmac.new(secret.encode(), f"admin:{args.admin}:i18n_sync:{target}".encode(),
                   hashlib.sha256).hexdigest()
    body = json.dumps({"admin_steam_id": args.admin, "keys": keys,
                       "signature": sig}).encode("utf-8")
    req = urllib.request.Request(
        args.base + "/api/v1/admin/i18n/sync-keys", data=body,
        headers={"Content-Type": "application/json", "X-Mod-Version": "tools"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            print(resp.status, resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        # Print the server's OWN explanation. Without this an admin 403 is
        # opaque, and the three gates behind it need different fixes:
        #   "Not an admin"             -> steam id missing from admin_users
        #   "Bad admin signature"      -> ADMIN_HMAC_SECRET mismatch, or the
        #                                 server's copy is unset (fails CLOSED)
        #   "admin identity not live"  -> players row deleted/missing
        body = e.read().decode("utf-8", "replace")[:500]
        print(f"HTTP {e.code}: {body}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
