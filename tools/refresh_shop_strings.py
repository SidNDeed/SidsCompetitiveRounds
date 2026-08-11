#!/usr/bin/env python3
"""Refresh tools/shop_strings.json from the live shop_items table.

The snapshot feeds tools/i18n_extract.py (shop/cosmetic names + descriptions
are portal-moderatable keys — see the ingest block there). It has NO staleness
detection: items shipped after the last refresh are silently absent from the
key set until this runs. Run it whenever shop items ship, BEFORE the extractor.

Reads prod over ssh through the deploy host's read-only SQL verb (no secrets
involved). Both halves of that invocation are environment-specific and are
supplied by the operator — this file carries neither:
    SCR_DEPLOY_SSH  ssh destination for the deploy host  (or --ssh-target)
    SCR_SQL_VERB    its read-only SQL forced-command prefix, separator
                    included, which this tool prepends to the query below
                    (or --sql-verb)

    python tools/refresh_shop_strings.py            # ssh + rewrite snapshot
    python tools/refresh_shop_strings.py --dry-run  # report the diff only

The strings list is sorted + de-duplicated (names and non-empty descriptions,
CRLF-normalized) so reruns are byte-stable and diffs are honest.
"""
import argparse
import io
import json
import os
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SNAP = os.path.join(REPO, "tools", "shop_strings.json")
QUERY = ("SELECT json_agg(json_build_object("
         "'n', name, 'd', COALESCE(description,''))) FROM shop_items;")


def lf(s):
    return s.replace("\r\n", "\n").replace("\r", "\n")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    # No defaults: the deploy destination and its read-only SQL verb are
    # environment-specific and belong to the operator's runbook, not to this
    # file (code review find 16).
    ap.add_argument("--ssh-target", default=os.environ.get("SCR_DEPLOY_SSH", ""),
                    help="ssh destination for the deploy host (env SCR_DEPLOY_SSH)")
    ap.add_argument("--sql-verb", default=os.environ.get("SCR_SQL_VERB", ""),
                    help="read-only SQL forced-command prefix, separator "
                         "included (env SCR_SQL_VERB)")
    args = ap.parse_args()

    if not args.ssh_target or not args.sql_verb:
        print("set SCR_DEPLOY_SSH and SCR_SQL_VERB (or pass --ssh-target / "
              "--sql-verb): the deploy destination and its read-only SQL verb "
              "are environment-specific and are not carried in this file",
              file=sys.stderr)
        return 2

    out = subprocess.run(["ssh", args.ssh_target, args.sql_verb + QUERY],
                         capture_output=True, text=True, encoding="utf-8",
                         timeout=60)
    if out.returncode != 0:
        print(f"ssh failed ({out.returncode}): {out.stderr[:400]}",
              file=sys.stderr)
        return 1
    raw = out.stdout
    try:
        items = json.loads(raw[raw.index("["):raw.rindex("]") + 1])
        if not isinstance(items, list) or not items:
            raise ValueError("empty item list")
    except Exception as ex:  # noqa: BLE001
        # FAIL LOUD (the i18n_extract.py rule): a malformed dump must never
        # rewrite the snapshot to something the extractor then trusts.
        print(f"could not parse prod dump ({ex}); first 200 chars: "
              f"{raw[:200]!r}", file=sys.stderr)
        return 1

    strings = set()
    for it in items:
        for v in (it.get("n"), it.get("d")):
            if v and v.strip():
                strings.add(lf(v))
    new = sorted(strings)

    old = []
    if os.path.exists(SNAP):
        old = [lf(s) for s in json.load(
            io.open(SNAP, encoding="utf-8"))["strings"]]
    added = sorted(set(new) - set(old))
    removed = sorted(set(old) - set(new))
    print(f"prod strings: {len(new)}  snapshot: {len(old)}  "
          f"added: {len(added)}  removed: {len(removed)}")
    for s in added:
        print(f"  + {s[:90]!r}")
    for s in removed:
        # A removal RETIRES the key at the next extractor+sync run, orphaning
        # any approved translations for it (#289's key model) — deliberate,
        # but worth seeing before it happens.
        print(f"  - {s[:90]!r}")
    if args.dry_run:
        return 0
    with io.open(SNAP, "w", encoding="utf-8", newline="\n") as f:
        json.dump({"format": 1,
                   "comment": ("Live shop catalog display strings (names + "
                               "descriptions) - regenerate from prod "
                               "shop_items when items ship (tools/"
                               "refresh_shop_strings.py). Consumed by "
                               "tools/i18n_extract.py."),
                   "strings": new}, f, ensure_ascii=False, indent=1)
    print(f"wrote {os.path.relpath(SNAP, REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
