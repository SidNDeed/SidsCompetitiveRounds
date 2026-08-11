#!/usr/bin/env python3
"""Release-time key sync: push tools/i18n_source.json (the extractor output,
'client' namespace) AND tools/game_strings.json (the base-game table dump,
'game' namespace) to POST /api/v1/admin/i18n/sync-keys so the portal and pack
serve the current key set.

Usage (Sid's PC, needs the admin secret in the environment):
    set ADMIN_HMAC_SECRET=...          (never in the repo / never in argv)
    python tools/i18n_sync_keys.py [--base https://competitive-rounds.duckdns.org:8444] \
                                   [--admin 76561198040410653]

Key identity (localization-design §2.3 / §6.3):
    client: key_id = sha1("client\\0" + source_string)[:16]
    game:   key_id = sha1("game\\0" + Table/ENTRY_KEY)[:16]   (identity is the
            TABLE ENTRY, not the English — the four PS/Xbox pairs whose
            English coincides stay separately correctable)
    source_hash = sha1(english_source_text) in both namespaces.

Both namespaces ride ONE request (code review find 13). The server upserts,
supersedes, retires and audits inside a single transaction, so either both
manifests land or neither does — split across two requests, the client half
can commit and the game half then fail, leaving a half-updated production
corpus with nothing to roll back. The payload declares
namespaces=["client","game"] plus per-namespace expected_counts (and per-key
context for the game keys); the server's retirement sweep only ever covers
the DECLARED namespaces, so an older client-only copy of this tool (no
"namespaces" field -> server default ['client']) still cannot reach the game
keys. One HMAC covers the request (canonical action 'i18n_sync', target
'n=<total keys>').
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
GAME_SRC = os.path.join(REPO, "tools", "game_strings.json")

# REVIEWED FIXED TOTALS for the base-game corpus (code review find 13). The
# game namespace is not extractor churn — it is ROUNDS' OWN shipped string
# tables, so its size is a constant until the GAME updates. Declaring the
# count from the file we just read is self-consistent with a TRUNCATED file:
# a 232-key dump declares 232, clears the server's 10%-shrink guard, and
# retires ten live production keys reporting success. These numbers are the
# independent check, so a game update moves them through a REVIEWED edit here
# (re-run tools/dump_base_game_tables.py first) and never at runtime.
GAME_TABLE_KEYS = {"StringTableDefault": 95, "StringTableCards": 147}
GAME_KEY_TOTAL = 242
# The client namespace has no equivalent constant on purpose: its key set is
# extractor output and legitimately churns every release. Its truncation
# guard is the server's 10%-shrink rule plus expected_counts.

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
    client_keys = []
    for s in data["strings"]:
        kid = hashlib.sha1(("client\0" + s).encode("utf-8")).hexdigest()[:16]
        low = s.lower()
        client_keys.append({
            "key_id": kid,
            "namespace": "client",
            "msgctxt": s,
            "source_hash": hashlib.sha1(s.encode("utf-8")).hexdigest(),
            "sensitive": any(m in low for m in SENSITIVE_MARKERS),
        })

    # Game namespace: FAIL LOUD if the dump is missing (the same rule the
    # extractor applies to shop_strings.json) — a missing file here would
    # silently retire every game key through the namespace-scoped sweep.
    game = json.load(io.open(GAME_SRC, encoding="utf-8"))["tables"]
    game_keys = []
    for tname in sorted(game):
        for key in sorted(game[tname]):
            row = game[tname][key]
            ident = f"{tname}/{key}"
            ctx = ident + (f" — {row['comment']}" if row.get("comment") else "")
            game_keys.append({
                "key_id": hashlib.sha1(("game\0" + ident).encode("utf-8")).hexdigest()[:16],
                "namespace": "game",
                "msgctxt": row["en"],
                "source_hash": hashlib.sha1(row["en"].encode("utf-8")).hexdigest(),
                "sensitive": False,
                "context": ctx[:160],
            })

    # FIXED-TOTAL GATE — runs BEFORE any network activity, and before the
    # dry-run returns, so a damaged dump is reported by every invocation.
    bad = []
    if sum(GAME_TABLE_KEYS.values()) != GAME_KEY_TOTAL:
        bad.append(f"the reviewed constants disagree: "
                   f"{sum(GAME_TABLE_KEYS.values())} != {GAME_KEY_TOTAL}")
    if sorted(game) != sorted(GAME_TABLE_KEYS):
        bad.append(f"tables {sorted(game)}, expected {sorted(GAME_TABLE_KEYS)}")
    for tname in sorted(GAME_TABLE_KEYS):
        got = len(game.get(tname, {}))
        if got != GAME_TABLE_KEYS[tname]:
            bad.append(f"{tname}: {got} keys, expected {GAME_TABLE_KEYS[tname]}")
    if len(game_keys) != GAME_KEY_TOTAL:
        bad.append(f"game manifest: {len(game_keys)} keys, expected {GAME_KEY_TOTAL}")
    if bad:
        print("game key set does not match the reviewed corpus — REFUSING to "
              "sync (a short manifest retires the difference):", file=sys.stderr)
        for b in bad:
            print(f"  {b}", file=sys.stderr)
        print("re-run tools/dump_base_game_tables.py; if the GAME genuinely "
              "changed, update GAME_TABLE_KEYS/GAME_KEY_TOTAL in this file as "
              "a reviewed change.", file=sys.stderr)
        return 2

    print(f"{len(client_keys)} client keys "
          f"({sum(1 for k in client_keys if k['sensitive'])} sensitive), "
          f"{len(game_keys)} game keys")
    if args.dry_run:
        return 0

    def post(payload_extra, keys, label):
        # Server canonical: _admin_canonical = f"admin:{steam_id}:{action}:{target}"
        target = f"n={len(keys)}"
        sig = hmac.new(secret.encode(),
                       f"admin:{args.admin}:i18n_sync:{target}".encode(),
                       hashlib.sha256).hexdigest()
        body = json.dumps({"admin_steam_id": args.admin, "keys": keys,
                           "signature": sig, **payload_extra}).encode("utf-8")
        req = urllib.request.Request(
            args.base + "/api/v1/admin/i18n/sync-keys", data=body,
            headers={"Content-Type": "application/json", "X-Mod-Version": "tools"})
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                print(f"{label}: {resp.status} {resp.read().decode('utf-8')}")
                return True
        except urllib.error.HTTPError as e:
            # Print the server's OWN explanation. Without this an admin 403 is
            # opaque, and the gates behind it need different fixes:
            #   "Not an admin"             -> steam id missing from admin_users
            #   "Bad admin signature"      -> ADMIN_HMAC_SECRET mismatch, or the
            #                                 server's copy is unset (fails CLOSED)
            #   "admin identity not live"  -> players row deleted/missing
            #   400 count/shrink errors    -> damaged manifest, nothing retired
            print(f"{label}: HTTP {e.code}: "
                  f"{e.read().decode('utf-8', 'replace')[:500]}", file=sys.stderr)
            return False

    # ONE request = one server transaction = all-or-nothing across both
    # namespaces (find 13). expected_counts stays PER-NAMESPACE so a manifest
    # damaged on one side still fails its own count check rather than
    # retiring the difference.
    ok = post({"namespaces": ["client", "game"],
               "expected_counts": {"client": len(client_keys),
                                   "game": len(game_keys)}},
              client_keys + game_keys, "sync")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
