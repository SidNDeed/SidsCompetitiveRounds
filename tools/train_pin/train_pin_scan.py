"""R4-H2/R5-H1/R6-H1/R7-H1/R8-H1/R8-H6: scan a review bundle -- and a commit range -- for every class of identifier that may not travel with it.

WHAT THIS FILE IS NOW, AND WHAT IT IS NOT
-----------------------------------------
Round 10 moved the privacy PROOF of a pin off this file. The proof is NEEDLES
plus PROVENANCE (`train_pin_needles.py`): every known sensitive value of the seat,
in every form, over every byte of the pin and of the landing range, and every pin
file classified TRACKED-COPY, GENERATED or TYPED. A finite list of SHAPES cannot
establish that no identifier of any shape is present, so this census is never
the claim. Round 11 (R10-H1): it reads EVERY file of the pin whatever its
provenance class -- a tracked copy or a generated file can carry an unknown
identifier as well as a typed file can, because provenance proves where bytes
came from and that they are equal, never what they do not contain -- in UTF-8,
and in UTF-16LE wherever a file holds text in that encoding; the needle census
counts every hit in its PIN line. Its object mode below
(blob bodies to 8 MiB and commit messages) is SUPERSEDED by the needle census's
object mode, which reads every commit, tree and blob whole; the round-10 assembly
does not run it. Round 9's change stands: no raw transcript of a live run enters
a pin, and the live evidence is schema-rendered documents.

WHERE THIS FILE LIVES, AND WHY IT IS IN THE BUNDLE
--------------------------------------------------
A census is only judgeable if its rules are, so this file is IN the bundle.
That is only safe because the file holds no identifier. The literal needles --
the machine names, the backup host, this seat's configuration path -- AND the
values its own controls plant for those classes are in a SIDECAR that stays
outside every bundle, named with `--needles` or `SCR_PIN_NEEDLES`. Without it
this scanner REFUSES to run: a needle set that quietly became empty is a check
that cannot fail (#342, #441). It also refuses when the sidecar is inside the
bundle, because that is the same leak by another route. Every other planted
value a control uses is either documentation space (RFC 5737 / 3849 / 2606),
the seat's own value read at run time, or COMPOSED at run time from parts that
are not themselves an address or a hostname -- so no control value of a
prohibited class is written in this file.

WHAT IS SEARCHED FOR
--------------------
1. EVERY value in the seat configuration file, under the class its key names.
2. The sidecar's typed classes, for the identifiers no seat key holds.
   The case rule is the resolver's: the sidecar's classes, the controller, the
   remote URL and the account handle are matched case-insensitively (a host
   name with a capital is the same host); an inventory group and a path are
   matched as spelled, because that is how they are resolved.
3. EVERY ADDRESS, HOSTNAME, DIGEST AND UUID SHAPE in the bundle, whatever its
   range: every IPv4 quad (parsed, not pattern-matched), every IPv6 literal,
   every dotted name of any case, every hex run of 32 characters or more, and
   every 8-4-4-4-12 hex UUID (round 11: the nil and max UUIDs of RFC 9562 are
   reserved -- counted, never hits; every other one is a hit, because a UUID is
   how a machine, an installation or a session is named).

HOW A SHAPE IS PLACED (R8-H1)
-----------------------------
* The four sanctioned values are compared by WHOLE-TOKEN EQUALITY, hostnames
  case-insensitively. A quad that is a substring of a sanctioned one is not
  sanctioned -- it is a hit.
* The TLD is judged FIRST. A dotted name whose final label could resolve --
  every two-letter label, and every generic TLD in the list below -- is a HIT
  unless it is sanctioned, reserved for documentation, a seat value (counted
  under its seat class), or DECLARED here by exact spelling with the reason
  (DECLARED_PUBLIC, DECLARED_CODE). No rule DERIVED from the bundle can set
  aside a name that could resolve: a name ending in a real TLD is a hit even
  when the bundle also assigns its first label. Only a name that cannot
  resolve anywhere is placed by the derived rules, each counted.
* A 40-hex run is set aside only when it names an object in the repository
  named with `--repo` (asked of git, not of its shape) or is DECLARED below.
  Every other hex run of 32 characters or more is a hit: a machine
  fingerprint is a persistent machine identifier.

THE CLASS LIST IS FIXED
-----------------------
Every class this file can report is reported, with zero when nothing is
found, and `--self-test` runs one control and one inert twin PER REPORTED
CLASS -- and prints the two counts, which must agree.

    python train_pin_scan.py <bundle-dir> --needles <sidecar> [--repo <repo>] [--write]
        [--objects <base>..<tip>]
    python train_pin_scan.py <repo> --needles <sidecar> --objects <base>..<tip>
    python train_pin_scan.py <any-dir> --needles <sidecar> --self-test [--repo <repo>]
    python train_pin_scan.py <repo> --needles <sidecar> --objects-self-test <base>..<tip>

`--write` puts `pin-path-scan.log` in the bundle -- the file census and, with
`--objects`, the object-range census of the same run -- and then RE-SCANS with
the log in place: a log that introduced a hit of its own is caught, never
excluded.
"""
import hashlib
import io
import ipaddress
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

OPEN_MARK = "<!-- IDENTIFIER-STATEMENT -->"
CLOSE_MARK = "<!-- /IDENTIFIER-STATEMENT -->"
NL = chr(10)

# Which class each seat key's VALUE belongs to. A key this map does not know
# still becomes a needle, under the catch-all class: a new seat key must be a
# deliberate decision about its class, never a silent exemption from the scan.
SEAT_KEY_CLASS = {
    "controller": "controller identifier",
    "pve_group": "inventory group identifier",
    "primary_limit": "inventory group identifier",
    "standby_limit": "inventory group identifier",
    "origin_url": "seat remote URL",
    # R9: the absolute playbook directory on the controller. A path on
    # somebody's controller names an account.
    "play_dir": "play directory",
}
UNCLASSED_SEAT_KEY = "seat configuration value"
ACCOUNT_HANDLE = "account handle"
SEAT_CLASSES = ("controller identifier", "inventory group identifier", "seat remote URL",
                "play directory", ACCOUNT_HANDLE, UNCLASSED_SEAT_KEY)
CASE_INSENSITIVE_SEAT_CLASSES = ("controller identifier", "seat remote URL", ACCOUNT_HANDLE)

# Sanctioned by the integrator, 2026-09-22: the public service hostname and the
# LAN addresses of the two backend boxes and the edge. The basis was CHECKED
# with `git grep -n`, one value at a time, rather than asserted:
#   competitive-rounds.duckdns.org -> backend/nginx/app.conf, plugin/Plugin.cs
#   192.168.72.90  (the standby)   -> plugin/ApiClient.cs
#   192.168.72.102 (the edge)      -> backend/docker-compose.tls.yml
#   192.168.72.199 (the primary)   -> NO TRACKED FILE CARRIES IT; it rests on
#                                     the ruling alone, which is said rather
#                                     than dressed up as a published basis.
DISCLOSED = [
    "192.168.72.199",
    "192.168.72.90",
    "192.168.72.102",
    "competitive-rounds.duckdns.org",
]

# Public hosts that name no machine of this deployment. DECLARED and COUNTED in
# their own census block rather than filtered out: a name that is merely
# dropped is a name nobody can object to.
DECLARED_PUBLIC = {
    "github.com": "the code host this batch pins `origin` to; in the public repo",
    "api.steampowered.com": "the Steam Web API, which the backend calls; in the public repo",
    "openssh.com": "the OpenSSH project's domain, in the URL of an ssh client warning the "
                   "train recognises and drops",
    "anthropic.com": "the domain of the commit trailer's no-reply address",
    "steamcommunity.com": "Steam's public community site, which the backend links to; in "
                          "the public repo",
    "avatars.steamstatic.com": "Steam's public avatar host, which the backend reads; in the "
                               "public repo",
    # R9: a suffix written with its leading dot is now read as the name after
    # the dot, so the public service domain that this scan names as a class,
    # and under which the sanctioned service hostname lives, is declared.
    "duckdns.org": "the public dynamic-DNS service's own domain: the suffix of the "
                   "sanctioned service hostname, and one of this scan's classes",
    # R10: the public code hosts the needle census drops from its set as public
    # service hosts (train_pin_needles.py names them to drop them).
    "gitlab.com": "a public code host the needle census names in order to drop it",
    "bitbucket.org": "a public code host the needle census names in order to drop it",
}

# R9 (H1). Dotted tokens whose final label COULD resolve and which are not
# hosts. They used to be set aside by rules derived from the bundle -- and a
# derived rule is exactly what could silence a real host. Each is declared
# here by its exact spelling, with what it is, so a reviewer reads the list;
# a resolvable token not on it is a hit.
DECLARED_CODE = {
    "subprocess.run": "a Python standard-library call",
    "args.go": "an attribute of the train's parsed arguments",
    "m.group": "a regular-expression match method",
    "found.group": "a regular-expression match method",
    "last.group": "a regular-expression match method",
    "said.group": "a regular-expression match method",
    "stamp.group": "a regular-expression match method",
    "last.re": "a regular-expression match attribute",
    "rt.os": "the train module's `os`, as the tests patch it",
    "rt.os.link": "the train module's hard-link call, as the tests patch it",
    "rt.run": "the train module's `run`, as the tests patch it",
    "s.id": "an attribute access in a test",
    "ApiClient.cs": "a file of the public repository (plugin/)",
    "Plugin.cs": "a file of the public repository (plugin/)",
    "main.py": "a file of the public repository (backend/api/)",
    "changelog-archive.md": "a file of the public repository (docs/)",
    "deploy-reference.md": "the name of a local documentation file the briefs cite",
    "cc-snapshot-wrapper.sh": "the snapshot wrapper script the train invokes by its path",
    "cc-snapshot-wrapper.gated.sh": "the snapshot wrapper's gated copy, tracked beside the pin "
                                    "tools (R11-L1)",
    # R11-H1 / R11-L1 (round 12), found by the shape census of the round's own tool
    # and test changes BEFORE they were committed (R11-L4 names the round that found
    # them only after): each declared by its exact spelling.
    "privacy-guard.py": "the file name of the guard script the pre-commit hook runs, written "
                        "beside each of the census's guard declarations (R11-H1); a file "
                        "name the public repository's tests already carry",
    "node.id": "an attribute access in the needle census (a Name node's identifier)",
    "parent.name": "an attribute access in the needle census (a definition's name)",
    "parent.op": "an attribute access in the needle census (an operator node)",
    "script.name": "a path attribute in the needle census",
    "read.group": "a regular-expression match method",
    "shape.group": "a regular-expression match method",
    "scratch.py": "a file name a test stages as a fixture",
    "asyncio.run": "a Python standard-library call",
    "ast.Name": "a Python standard-library class",
    "blob.group": "a regular-expression match method",
    "ref.group": "a regular-expression match method",
    "opened.group": "a regular-expression match method",
    "f.name": "an attribute access in a test",
    "p.name": "an attribute access in a test",
    "due.id": "an attribute access in a test",
    "e.id": "an attribute access in a test",
    "n.id": "an attribute access in a test",
    "named.id": "an attribute access in a test",
    "p.id": "an attribute access in a test",
    "pl.id": "an attribute access in a test",
    "pr.id": "an attribute access in a test",
    "su.id": "an attribute access in a test",
    # R9, found by the first scan of the finished pin: `.md` and `.py` are
    # country TLDs, so a document name the pin itself is made of is a
    # resolvable name until it is declared.
    "CODEX-BUG392-MERGE-R1-REPORT.md": "the bug392-merge lane's review report, which the "
                                       "train's batch comment cites by name",
    "BUG392-MERGE-NOTES.md": "the bug392-merge lane's notes, which the train's batch "
                             "comment cites by name",
    "code.py": "a file name the citation checker's self-test plants",
    "notes.md": "a file name the citation checker's self-test plants",
    "other.py": "a file name the citation checker's self-test plants",
    "statement-document.md": "the file name a round-7 statement control wrote, as the "
                             "round-7 notes quote it",
    # ...and this lane's own documents, by the names the pin carries them
    # under. Written out whole: a name GENERATED from a format string left
    # its own fragments in this file for the census to find.
    "CODEX-TRAIN-BUG392-MERGE-R1-BRIEF.md": "a review brief of this lane",
    "CODEX-TRAIN-BUG392-MERGE-R1-REPORT.md": "a review report of this lane",
    "CODEX-TRAIN-BUG392-MERGE-R2-BRIEF.md": "a review brief of this lane",
    "CODEX-TRAIN-BUG392-MERGE-R2-REPORT.md": "a review report of this lane",
    "CODEX-TRAIN-BUG392-MERGE-R3-BRIEF.md": "a review brief of this lane",
    "CODEX-TRAIN-BUG392-MERGE-R3-REPORT.md": "a review report of this lane",
    "CODEX-TRAIN-BUG392-MERGE-R4-BRIEF.md": "a review brief of this lane",
    "CODEX-TRAIN-BUG392-MERGE-R4-REPORT.md": "a review report of this lane",
    "CODEX-TRAIN-BUG392-MERGE-R5-BRIEF.md": "a review brief of this lane",
    "CODEX-TRAIN-BUG392-MERGE-R5-REPORT.md": "a review report of this lane",
    "CODEX-TRAIN-BUG392-MERGE-R6-BRIEF.md": "a review brief of this lane",
    "CODEX-TRAIN-BUG392-MERGE-R6-REPORT.md": "a review report of this lane",
    "CODEX-TRAIN-BUG392-MERGE-R7-BRIEF.md": "a review brief of this lane",
    "CODEX-TRAIN-BUG392-MERGE-R7-REPORT.md": "a review report of this lane",
    "CODEX-TRAIN-BUG392-MERGE-R8-BRIEF.md": "a review brief of this lane",
    "CODEX-TRAIN-BUG392-MERGE-R8-REPORT.md": "a review report of this lane",
    "TRAIN-BUG392-MERGE-R2-NOTES.md": "the build notes of round 2 of this lane",
    "TRAIN-BUG392-MERGE-R3-NOTES.md": "the build notes of round 3 of this lane",
    "TRAIN-BUG392-MERGE-R4-NOTES.md": "the build notes of round 4 of this lane",
    "TRAIN-BUG392-MERGE-R5-NOTES.md": "the build notes of round 5 of this lane",
    "TRAIN-BUG392-MERGE-R6-NOTES.md": "the build notes of round 6 of this lane",
    "TRAIN-BUG392-MERGE-R7-NOTES.md": "the build notes of round 7 of this lane",
    "TRAIN-BUG392-MERGE-R8-NOTES.md": "the build notes of round 8 of this lane",
    "TRAIN-BUG392-MERGE-R9-NOTES.md": "the build notes of round 9 of this lane",
    # R10: this round's documents and the ones it cites, whole, and the two
    # local scripts its brief names.
    "CODEX-TRAIN-BUG392-MERGE-R9-BRIEF.md": "a review brief of this lane",
    "CODEX-TRAIN-BUG392-MERGE-R9-REPORT.md": "a review report of this lane",
    "TRAIN-BUG392-MERGE-R9-BUILD-BRIEF.md": "the build brief of round 9 of this lane",
    "TRAIN-BUG392-MERGE-R10-BUILD-BRIEF.md": "the build brief of round 10 of this lane",
    "TRAIN-BUG392-MERGE-R10-NOTES.md": "the build notes of round 10 of this lane",
    "lore.py": "the project's lessons-retrieval script, which a brief names",
    # R11: this round's documents and the review round they answer, whole.
    "CODEX-TRAIN-BUG392-MERGE-R10-BRIEF.md": "a review brief of this lane",
    "CODEX-TRAIN-BUG392-MERGE-R10-REPORT.md": "a review report of this lane",
    "TRAIN-BUG392-MERGE-R11-BUILD-BRIEF.md": "the build brief of round 11 of this lane",
    "TRAIN-BUG392-MERGE-R11-NOTES.md": "the build notes of round 11 of this lane",
    "pickup.py": "the integrator's pickup script, which a brief names",
    # R12: this round's documents and the review round they answer, whole. The
    # `.md` suffix is a country-code TLD, so each name is declared by its exact
    # spelling before the pin that carries it is assembled.
    "CODEX-TRAIN-BUG392-MERGE-R11-BRIEF.md": "a review brief of this lane",
    "CODEX-TRAIN-BUG392-MERGE-R11-REPORT.md": "a review report of this lane",
    "TRAIN-BUG392-MERGE-R12-BUILD-BRIEF.md": "the build brief of round 12 of this lane",
    "TRAIN-BUG392-MERGE-R12-NOTES.md": "the build notes of round 12 of this lane",
    # R13: this round's documents and the review round they answer, whole. Declared
    # by exact spelling in the same commit that lands the round-13 tools, before the
    # pin that carries them is assembled (R12-L2) -- the lane pre-commit shape gate
    # (train_pin_scan.py --staged) refuses a lane commit that would carry an
    # undeclared one.
    "CODEX-TRAIN-BUG392-MERGE-R12-BRIEF.md": "a review brief of this lane",
    "CODEX-TRAIN-BUG392-MERGE-R12-REPORT.md": "a review report of this lane",
    "TRAIN-BUG392-MERGE-R13-BUILD-BRIEF.md": "the build brief of round 13 of this lane",
    "TRAIN-BUG392-MERGE-R13-NOTES.md": "the build notes of round 13 of this lane",
    # R10: attribute accesses in the round-10 tools and tests whose final
    # label is a TLD.
    "a.id": "an attribute access in the needle census",
    "t.id": "an attribute access in the needle census",
    "self.info": "an attribute of the needle census's control table",
    "self.ns": "an attribute of the assembler's pin writer",
    "common.name": "a path attribute in the needle census",
    "common.parent.name": "a path attribute in the needle census",
    "color.ui": "a git configuration key the census's git calls set",
    "user.name": "a git configuration key the needle census reads",
    "user.email": "a git configuration key the needle census reads",
    "ast.Is": "a Python standard-library class",
    "gate.group": "a regular-expression match method",
    "wanted.group": "a regular-expression match method",
    "node.name": "an attribute access in a test",
    "target.id": "an attribute access in a test",
    "up.func.id": "an attribute access in a test",
    # R11: attribute accesses and a planted file name in the round-11 needle
    # census -- the guard enumeration's AST walk, the tip-bound recipe check and
    # the replace-object self-test -- whose final label is a TLD.
    "a.name": "an attribute access in the needle census (the module an import names)",
    "f.id": "an attribute access in the needle census (the name a call is made through)",
    "node.op": "an attribute access in the needle census (an arithmetic node's operator)",
    "rng.group": "a regular-expression match method",
    "copy.py": "a file name the needle census's self-test plants",
    # R13: attribute accesses in the round-13 pattern-site allow-list of the needle
    # census (the closed allow-list at re.compile sites, R12-H1) whose final label
    # is a TLD.
    "ast.Store": "a Python standard-library class (the store context of a name node)",
    "f.value.id": "an attribute access in the needle census (a re.<func> receiver's name)",
    "stmt.target.id": "an attribute access in the needle census (an annotated assign's name)",
}

# Hex runs of 32 or more characters that are not objects of the repository
# and are declared by exact value. Each is a test fixture, a public constant,
# or a value a pinned document carries for the reason stated beside it.
DECLARED_DIGESTS = {
    "00000000000000000000000000000000": "the constant nonce mutation R8-M2b plants in "
                                        "place of the invocation's own",
    "990cd4390c6bcc5f9e01be752d5e4c7c388340": "commit 990cd43 of this repository, cut to "
                                              "38 characters by the ellipsis of a test "
                                              "message the round-8 notes quote",
    "0123456789abcdef0123456789abcdef01234567": "a synthetic object id the tests use",
    "fedcba9876543210fedcba9876543210fedcba98": "a synthetic object id the tests use",
    "fef49e7fa7e1997310d705b2a6158ff8dc1cdfeb": "the public Steam default-avatar hash "
                                                "the tests use",
}

# RFC 2606 / RFC 6761 reserved names: counted in their own block.
RESERVED_TLDS = ("invalid", "test", "example", "localhost")
RESERVED_NAMES = ("example.com", "example.net", "example.org")

# RFC 5737 (v4) and RFC 3849 (v6) documentation addresses: counted, never hits.
RESERVED_NETS = ("192.0.2.0/24", "198.51.100.0/24", "203.0.113.0/24",
                 "2001:db8::/32")

# The suffixes that make a token a hostname whatever else it looks like.
ALWAYS_HOST_SUFFIXES = (".local", ".lan", ".home", ".internal", ".duckdns.org")

# The fixed list of SHAPE classes. Every one is reported, with zero when
# nothing of it is found, and every one has a control.
IPV4_CLASSES = (
    "undeclared IPv4 address (loopback)",
    "undeclared IPv4 address (link-local)",
    "undeclared IPv4 address (private 10/8)",
    "undeclared IPv4 address (private 172.16/12)",
    "undeclared IPv4 address (private 192.168/16)",
    "undeclared IPv4 address (private, other range)",
    "undeclared IPv4 address (public)",
)
IPV6_CLASSES = (
    "undeclared IPv6 address (loopback)",
    "undeclared IPv6 address (link-local)",
    "undeclared IPv6 address (unique-local)",
    "undeclared IPv6 address (global)",
)
HOST_CLASSES = tuple("undeclared hostname (%s)" % s for s in ALWAYS_HOST_SUFFIXES) + (
    "undeclared hostname",)
DIGEST_CLASSES = (
    "undeclared 32-character hex digest",
    "undeclared 40-character hex digest",
    "undeclared 64-character hex digest",
    "undeclared hex run of another length (32 or more)",
)
UUID_CLASSES = ("undeclared UUID",)
SHAPE_CLASSES = IPV4_CLASSES + IPV6_CLASSES + HOST_CLASSES + DIGEST_CLASSES + UUID_CLASSES

# What a final label has to be for the token to be able to name a machine at
# all. EVERY two-letter label is a country code, so that space is covered
# without listing one; these are the generic suffixes beside it.
GTLDS = (
    "com", "net", "org", "edu", "gov", "mil", "int", "info", "biz", "name",
    "pro", "aero", "coop", "museum", "app", "dev", "page", "blog", "wiki",
    "cloud", "host", "hosting", "network", "site", "online", "store", "tech",
    "systems", "solutions", "services", "software", "tools", "works", "team",
    "group", "digital", "zone", "link", "live", "life", "world", "email",
    "codes", "computer", "support", "run", "space", "xyz", "top", "click",
    "download", "stream", "video", "media", "news", "press", "agency",
    "company", "center", "training", "academy", "institute", "foundation",
    "community", "social", "chat", "games", "game", "fun", "party", "rocks",
    "ninja", "guru", "expert", "consulting", "capital", "finance", "fund",
    "bank", "insurance", "legal", "law", "health", "care", "clinic",
    "hospital", "school", "university", "college", "studio", "design",
    "gallery", "photos", "pictures", "graphics", "audio", "music", "band",
    "film", "show", "theater", "tickets", "travel", "tours", "vacations",
    "flights", "hotel", "restaurant", "cafe", "bar", "pub", "beer", "wine",
    "coffee", "pizza", "kitchen", "recipes", "farm", "garden", "house",
    "estate", "properties", "rentals", "realty", "builders", "construction",
    "engineering", "energy", "solar", "green", "eco", "earth", "water",
    "air", "auto", "cars", "bike", "boats", "yachts", "jet", "taxi",
    "delivery", "shipping", "logistics", "supply", "trade", "market",
    "shop", "shopping", "deals", "sale", "discount", "cheap", "gratis",
)

# ---------------------------------------------------------------------------
# Token shapes. Each is a CANDIDATE that is then parsed or placed.
# R9, found by the first scan of the finished pin: where a token begins and
# ends is decided ONCE, by _left() and _right(), and extraction and counting
# both use it. The old rules disagreed with prose and with each other: a name
# or a quad that ENDED A SENTENCE was never extracted (the full stop read as
# the start of another label), one after a colon was extracted and then
# counted zero times, and one after an ellipsis was neither -- so each read as
# no hit at all. A dot belongs to a token only when a label continues after
# it; before a token, a dot is punctuation unless a label stands before it.
_NAME_CH = r"0-9A-Za-z_\-"          # a dotted name's label characters
_ADDR_CH = r"0-9A-Za-z"             # what may not touch a quad
_V6_CH = r"0-9A-Za-z:"              # what may not touch a bare IPv6 address


def _left(ch):
    return r"(?<![%s])(?<![%s]\.)" % (ch, ch)


def _right(ch):
    return r"(?![%s]|\.[0-9A-Za-z])" % ch


_IPV4 = re.compile(_left(_ADDR_CH) + r"[0-9]{1,3}(?:\.[0-9]{1,3}){3}" + _right(_ADDR_CH))
_IPV4_SHAPE = re.compile(r"\A[0-9]{1,3}(?:\.[0-9]{1,3}){3}\Z")
_IPV6_BARE = re.compile(_left(_V6_CH) + r"[0-9A-Fa-f:]*:[0-9A-Fa-f:]*:[0-9A-Fa-f:]*"
                        + _right(_V6_CH))
_IPV6_BRACKETED = re.compile(r"\[[0-9A-Fa-f:]+\](?::[0-9]{1,5})?")
# A dotted name of ANY case (R8-H1): two or more labels of [A-Za-z0-9-].
_FQDN = re.compile(_left(_NAME_CH) + r"[A-Za-z0-9](?:[A-Za-z0-9\-]*[A-Za-z0-9])?"
                   r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9\-]*[A-Za-z0-9])?)+" + _right(_NAME_CH))
# R9: every MAXIMAL hex run of 32 characters or more, of either case, whatever
# stands beside it -- `0x<digest>` and `id<digest>` included.
_HEXRUN = re.compile(r"(?<![0-9A-Fa-f])[0-9A-Fa-f]{32,}(?![0-9A-Fa-f])")
_SHA40 = re.compile(r"\A[0-9a-f]{40}\Z")
# Round 11 (R10-H1): an 8-4-4-4-12 hex UUID of either case, whatever stands
# beside it, except more hex: a machine GUID, an installation id, a session id.
_UUID = re.compile(r"(?<![0-9A-Fa-f])[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-"
                   r"[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}(?![0-9A-Fa-f])")
# The two UUIDs RFC 9562 reserves (nil and max): they name nothing.
_UUID_RESERVED = re.compile(r"\A(?:[0-]{36}|[fF-]{36})\Z")
# A file that holds UTF-16LE text: every run of four or more printable ASCII
# characters, each followed by a zero byte, at either alignment.
_WIDE_RUN = re.compile(rb"(?:[\x09\x0a\x0d\x20-\x7e]\x00){4,}")
WIDE_SUFFIX = " (read as UTF-16LE)"
NO_REPLACE_ENV = {"GIT_NO_REPLACE_OBJECTS": "1"}

# What the bundle itself says a dotted token is, when it cannot resolve.
_DEF = re.compile(r"^[+\-]?\s*(?:def|class)\s+([A-Za-z_][A-Za-z0-9_]*)", re.M)
_ASSIGN = re.compile(r"(?<![A-Za-z0-9_.])([a-z][a-z0-9_]*)\s*=(?!=)")
_JSON_KEY = re.compile(r'"([a-z][a-z0-9_]*)"\s*:')
_TUPLE_ASSIGN = re.compile(r"^[+\-]?\s*([a-z_][a-z0-9_]*(?:\s*,\s*[a-z_][a-z0-9_]*)+)"
                           r"\s*=(?!=)", re.M)
_IMPORT = re.compile(r"^[+\-]?\s*(?:import|from)\s+([A-Za-z_][A-Za-z0-9_.]*)", re.M)
_FROM_NAMES = re.compile(r"^[+\-]?\s*from\s+[A-Za-z_][A-Za-z0-9_.]*\s+import\s+([^\n#]+)",
                         re.M)
_PARAM = re.compile(r"^[+\-]?\s*def\s+[A-Za-z_][A-Za-z0-9_]*\s*\(([^)]*)\)", re.M)
_ALIAS = re.compile(r"(?<![A-Za-z0-9_])as\s+([A-Za-z_][A-Za-z0-9_]*)")
_SEP_EXT = re.compile(r"[\\/][A-Za-z0-9_.\-]+\.([A-Za-z0-9]{1,5})(?![A-Za-z0-9])")


class Refusal(Exception):
    pass


def load_needles(path, bundle):
    """The sidecar, or a refusal. Never a default, and never from inside the bundle."""
    if not path:
        raise Refusal(
            "this scanner has no needle file. The literal needles -- the machine names, the "
            "backup host, the seat's configuration path -- are deliberately NOT in this file, "
            "because this file travels inside the bundle it certifies. Pass --needles <path> "
            "or set SCR_PIN_NEEDLES. Nothing has been scanned: a scan with no needles reports "
            "zero hits and means nothing.")
    real_bundle = os.path.realpath(bundle)
    real_needles = os.path.realpath(path)
    if os.path.commonprefix([real_needles, real_bundle + os.sep]) == real_bundle + os.sep:
        raise Refusal(
            "the needle file is INSIDE the bundle. That is the same leak this arrangement "
            "exists to prevent, by another route. Nothing has been scanned.")
    try:
        conf = json.load(io.open(real_needles, encoding="utf-8"))
    except (IOError, OSError, ValueError) as e:
        raise Refusal("the needle file could not be read as JSON (%s). Nothing has been "
                      "scanned." % type(e).__name__)
    fixed = [(name, list(pats)) for name, pats in (conf.get("fixed") or [])]
    if not fixed or not any(pats for _n, pats in fixed):
        raise Refusal("the needle file carries no typed needle classes. An empty needle set "
                      "makes every bundle read clean. Nothing has been scanned.")
    return {"seat_conf": conf.get("seat_conf") or "", "fixed": fixed,
            "samples": conf.get("samples") or {}}


def seat_conf(path):
    try:
        return json.load(io.open(path, encoding="utf-8")) or {}
    except (IOError, OSError, ValueError):
        return {}


def literal_classes(needles):
    """[(class, [regex])] -- the sidecar's typed lists plus every seat value, by class.

    The CASE rule is the resolver's. A host name, a remote URL and an account
    handle resolve the same whatever their case, so the sidecar's classes, the
    controller, the remote URL and the handle are matched case-insensitively.
    An inventory group and a path are resolved as spelled, so they are matched
    as spelled."""
    by_class, order = {}, []
    for name, patterns in needles["fixed"]:
        if name not in by_class:
            order.append(name)
        by_class.setdefault(name, []).extend("(?i)" + p for p in patterns)
    # Every seat class is reported whether or not the seat holds a value for it.
    for name in SEAT_CLASSES:
        if name not in by_class:
            order.append(name)
            by_class[name] = []

    conf = seat_conf(needles["seat_conf"])
    for key in sorted(conf):
        # `_`-prefixed keys are the example file's prose, never a value.
        if key.startswith("_"):
            continue
        value = conf[key]
        if not isinstance(value, str) or not value.strip():
            continue
        name = SEAT_KEY_CLASS.get(key, UNCLASSED_SEAT_KEY)
        flag = "(?i)" if name in CASE_INSENSITIVE_SEAT_CLASSES else ""
        by_class[name].append(flag + re.escape(value.strip()))

    # The account handle is a SEGMENT of a seat value rather than a value.
    url = conf.get("origin_url") or ""
    parts = [p for p in url.split("/") if p]
    if len(parts) >= 3:
        by_class[ACCOUNT_HANDLE].append(r"(?i)(?<![A-Za-z0-9_-])%s(?![A-Za-z0-9_-])"
                                        % re.escape(parts[-2]))
    return [(n, by_class[n]) for n in order]


def seat_values(needles):
    return [v.strip() for k, v in seat_conf(needles["seat_conf"]).items()
            if not k.startswith("_") and isinstance(v, str) and v.strip()]


def wide_text(data):
    """The UTF-16LE text a file's bytes hold, as one string; '' when they hold none."""
    return NL.join(m.group(0).decode("utf-16-le") for m in _WIDE_RUN.finditer(data))


def file_of(name):
    """The bundle file a scanned text belongs to (a UTF-16LE reading names its file)."""
    return name[:-len(WIDE_SUFFIX)] if name.endswith(WIDE_SUFFIX) else name


def bundle_texts(bundle):
    """{relative path: text} for EVERY file in the bundle, none excluded.

    Round 11: the file is read as BYTES, decoded as UTF-8 (newlines normalised as
    text mode would) -- and, when those bytes hold UTF-16LE text, that text is a
    second reading of the same file, named `<file> (read as UTF-16LE)`, so a shape
    written in either encoding is found."""
    texts = {}
    for root, _dirs, names in os.walk(bundle):
        for name in sorted(names):
            full = os.path.join(root, name)
            rel = os.path.relpath(full, bundle).replace("\\", "/")
            with open(full, "rb") as fh:
                data = fh.read()
            texts[rel] = (data.decode("utf-8", errors="replace")
                          .replace("\r\n", "\n").replace("\r", "\n"))
            wide = wide_text(data)
            if wide:
                texts[rel + WIDE_SUFFIX] = wide
    return dict(sorted(texts.items()))


# ---------------------------------------------------------------------------
# The shape census.

def _ip_class(addr):
    """The class name an address belongs to, from the parsed address itself."""
    if addr.is_unspecified:
        return "the unspecified address, which names no machine"
    for net in RESERVED_NETS:
        if addr in ipaddress.ip_network(net):
            return "RESERVED"
    if addr.version == 4:
        if addr.is_loopback:
            return IPV4_CLASSES[0]
        if addr.is_link_local:
            return IPV4_CLASSES[1]
        if addr.is_private:
            for net, klass in (("10.0.0.0/8", IPV4_CLASSES[2]),
                               ("172.16.0.0/12", IPV4_CLASSES[3]),
                               ("192.168.0.0/16", IPV4_CLASSES[4])):
                if addr in ipaddress.ip_network(net):
                    return klass
            return IPV4_CLASSES[5]
        return IPV4_CLASSES[6]
    if addr.is_loopback:
        return IPV6_CLASSES[0]
    if addr.is_link_local:
        return IPV6_CLASSES[1]
    if addr.is_private:
        return IPV6_CLASSES[2]
    return IPV6_CLASSES[3]


def address_tokens(texts):
    """Every token in the bundle that parses as an address: {token: (where, what)}."""
    corpus = "\n".join(texts.values())
    found = {}
    for text in texts.values():
        candidates = set(_IPV4.findall(text)) | set(_IPV6_BARE.findall(text))
        for m in _IPV6_BRACKETED.finditer(text):
            candidates.add(m.group(0))
        for raw in candidates:
            token = raw
            bare = raw
            if bare.startswith("["):
                bare = bare[1:].split("]", 1)[0]
            try:
                addr = ipaddress.ip_address(bare)
            except ValueError:
                continue
            klass = _ip_class(addr)
            if klass == "RESERVED":
                found[token] = ("reserved", token)
            elif addr.is_unspecified:
                found[token] = ("aside", klass)
            elif _every_occurrence_is_a_range(token, corpus):
                found[token] = ("aside", "written with a prefix length everywhere it"
                                         " appears -- a CIDR range, not a host")
            else:
                found[token] = ("hit", klass)
    return found


def _every_occurrence_is_a_range(token, corpus):
    occ = _count(token, corpus)
    ranged = len(re.findall(_left(_token_ch(token)) + re.escape(token)
                            + r"/[0-9]{1,3}(?![0-9])", corpus))
    return bool(occ) and ranged >= occ


def _derived_non_hosts(texts):
    """What the BUNDLE says about dotted tokens that are not hostnames.

    Asked ONLY of a token that cannot resolve anywhere (R8-H1): the answer
    then decides which counted line of the census it lands on, never whether a
    name that could resolve is a hit."""
    extensions, labels, modules = set(), set(), set()
    for name, text in texts.items():
        ext = name.rsplit(".", 1)[-1].lower() if "." in name.rsplit("/", 1)[-1] else ""
        if ext:
            extensions.add(ext)
        labels.update(m.group(1) for m in _DEF.finditer(text))
        labels.update(m.group(1) for m in _ASSIGN.finditer(text))
        labels.update(m.group(1) for m in _JSON_KEY.finditer(text))
        labels.update(m.group(1) for m in _ALIAS.finditer(text))
        for m in _TUPLE_ASSIGN.finditer(text):
            for part in m.group(1).split(","):
                label = part.strip()
                if label.isidentifier():
                    labels.add(label)
        for m in _PARAM.finditer(text):
            for part in m.group(1).split(","):
                label = part.split("=")[0].split(":")[0].strip().lstrip("*")
                if label.isidentifier():
                    labels.add(label)
        for m in _IMPORT.finditer(text):
            modules.add(m.group(1).split(".")[0])
        for m in _FROM_NAMES.finditer(text):
            for part in m.group(1).split(","):
                label = part.split(" as ")[-1].strip().strip("()")
                if label.isidentifier():
                    modules.add(label)
        extensions.update(m.group(1).lower() for m in _SEP_EXT.finditer(text))
    return extensions, labels, modules


def host_tokens(texts, disclosed, declared, seat):
    """{token: (placement, class-or-reason)} for every dotted token.

    `placement` is one of: disclosed, declared, code, reserved, seat, aside, hit."""
    derived = _derived_non_hosts(texts)
    corpus = "\n".join(texts.values())
    found = {}
    for _name, text in texts.items():
        for token in set(_FQDN.findall(text)):
            if token in found:
                continue
            found[token] = _place_host(token, derived, disclosed, declared, seat, corpus)
    return found


def _is_disclosed(token, disclosed):
    """R8-H1: WHOLE-TOKEN equality, case-insensitively, and nothing weaker."""
    low = token.lower()
    return any(low == d.lower() for d in disclosed)


def _tld_verdict(last):
    """Whether a final label could be a real machine's, or why it could not."""
    if len(last) < 2:
        return (False, "final label shorter than any TLD (`e.g.`-shaped)")
    if not re.search(r"[A-Za-z]", last):
        return (False, "final label has no letter -- no TLD is numeric (`v4.13`)")
    if (len(last) == 2 and last.isalpha()) or last in GTLDS:
        return (True, None)
    return (False, "final label is neither a two-letter country code nor a"
                   " known generic TLD -- it cannot resolve anywhere")


def _place_host(token, derived, disclosed, declared, seat, corpus):
    """Where one dotted token lands. The TLD is judged before ANY derived rule."""
    extensions, labels, modules = derived
    parts = token.split(".")
    last = parts[-1].lower()
    low = token.lower()
    # A suffix that makes it a hostname whatever else it looks like.
    for suffix in ALWAYS_HOST_SUFFIXES:
        if low.endswith(suffix):
            if _is_disclosed(token, disclosed):
                return ("disclosed", token)
            return ("hit", "undeclared hostname (%s)" % suffix)
    if _is_disclosed(token, disclosed):
        return ("disclosed", token)
    if low in {d.lower() for d in declared}:
        return ("declared", token)
    if token in DECLARED_CODE:
        return ("code", token)
    # RFC 2606 reserves `example.com/net/org` AND everything under them.
    if (last in RESERVED_TLDS or low in RESERVED_NAMES
            or any(low.endswith("." + r) for r in RESERVED_NAMES)):
        return ("reserved", token)
    if any(low == v.lower() for v in seat):
        return ("seat", token)
    # R8-H1: the TLD question FIRST. A name that could resolve is a hit, and no
    # rule derived from the bundle is asked about it at all.
    resolvable, why_not = _tld_verdict(last)
    if resolvable:
        return ("hit", "undeclared hostname")
    # ...and a name that cannot resolve anywhere lands on a counted line.
    if last in extensions:
        return ("aside", "final label is a file extension present in this bundle (.%s)" % last)
    if re.search(r"[\\/]%s|%s[\\/]" % (re.escape(token), re.escape(token)), corpus):
        return ("aside", "the token is adjacent to a path separator in this bundle")
    if parts[0] in modules:
        return ("aside", "first label is a module this bundle's Python imports")
    if parts[0] in labels:
        return ("aside", "first label is a name this bundle defines, assigns, aliases or"
                         " takes as a parameter -- an attribute access")
    if _every_occurrence_is_a_call(token, corpus):
        return ("aside", "every occurrence is immediately followed by `(` -- a call")
    if last in labels:
        return ("aside", "final label is a name this bundle defines, assigns or keys on")
    if re.match(r"^[0-9]+\.[0-9]+[a-z]{1,2}$", token):
        return ("aside", "a number with a unit (`3.37s`), not a hostname")
    return ("aside", why_not)


def _every_occurrence_is_a_call(token, corpus):
    occ = _count(token, corpus)
    calls = len(re.findall(_left(_token_ch(token)) + re.escape(token) + r"\s*\(", corpus))
    return bool(occ) and calls >= occ


def _token_ch(token):
    """What may not touch this token: the rule the shape that extracts it uses."""
    if ":" in token:
        return _V6_CH
    if _IPV4_SHAPE.match(token):
        return _ADDR_CH
    return _NAME_CH


def _count(token, text):
    ch = _token_ch(token)
    return len(re.findall(_left(ch) + re.escape(token) + _right(ch), text))


def _count_hex(token, text):
    return len(re.findall(r"(?<![0-9A-Fa-f])%s(?![0-9A-Fa-f])" % re.escape(token), text))


def repository_objects(repo, candidates):
    """The subset of `candidates` that name an object in `repo`, asked of git itself."""
    if not repo or not candidates:
        return set()
    wanted = sorted(candidates)
    p = subprocess.run(["git", "--no-replace-objects", "-C", repo, "cat-file", "--batch-check"],
                       input="\n".join(wanted) + "\n", capture_output=True, text=True,
                       env=dict(os.environ, **NO_REPLACE_ENV))
    if p.returncode != 0:
        raise Refusal("git could not be asked which object ids name objects (rc=%d). Nothing "
                      "has been scanned." % p.returncode)
    present = set()
    for line in p.stdout.splitlines():
        parts = line.split()
        if len(parts) == 3 and parts[1] in ("commit", "tree", "blob", "tag"):
            present.add(parts[0])
    return present


def fingerprint_tokens(texts, repo=None, digests=None):
    """Every hex run of 32 or more characters, placed: {token: (where, what)}.

    A 40-hex run that names an object in the repository is a git object id,
    which a review bundle is made of; one DECLARED here by value is a fixture
    or a public constant. Every other run is a hit: the one such value this
    tool handles is a machine's boot fingerprint.

    R10: `digests` maps a value to what it is, for values DERIVED at scan time
    from bytes the scan can see -- the sha256 of a file of the bundle, or the
    needle census's own list digest. A value is placed there only by being
    exactly that; a fingerprint is none of them."""
    runs = set()
    for text in texts.values():
        runs.update(_HEXRUN.findall(text))
    objects = repository_objects(repo, {r for r in runs if _SHA40.match(r)})
    found = {}
    for token in runs:
        if _SHA40.match(token) and token in objects:
            found[token] = ("object", "a 40-character id of an object in the repository")
        elif token in DECLARED_DIGESTS:
            found[token] = ("digest", DECLARED_DIGESTS[token])
        elif digests and token in digests:
            found[token] = ("digest", digests[token])
        elif len(token) == 32:
            found[token] = ("hit", DIGEST_CLASSES[0])
        elif len(token) == 40:
            found[token] = ("hit", DIGEST_CLASSES[1])
        elif len(token) == 64:
            found[token] = ("hit", DIGEST_CLASSES[2])
        else:
            found[token] = ("hit", DIGEST_CLASSES[3])
    return found


# ---------------------------------------------------------------------------

def bundle_digests(bundle):
    """{sha256 of a file's bytes: what it is} for every file of the bundle (R10)."""
    out = {}
    for root, _dirs, names in os.walk(bundle):
        for name in sorted(names):
            full = os.path.join(root, name)
            rel = os.path.relpath(full, bundle).replace(os.sep, "/")
            with open(full, "rb") as fh:
                out.setdefault(hashlib.sha256(fh.read()).hexdigest(),
                               "the sha256 of the bundle file %s" % rel)
    return out


def scan(bundle, needles, repo=None, digests=None):
    """The census over a directory of files.

    R10: a 64-hex run equal to the sha256 of a file of this bundle is that
    file's digest (a manifest records them), and `digests` adds values the
    caller derived itself; each is reported by what it is, never dropped."""
    known = bundle_digests(bundle)
    known.update(digests or {})
    return _scan_texts(bundle_texts(bundle), needles, repo, known)


def _scan_texts(texts, needles, repo=None, digests=None):
    """The census over any {name: text} corpus -- a bundle's files, or a range's blobs."""
    files = list(texts)
    seat = seat_values(needles)

    hits = []                                   # [(class, [(file, n)])]
    for name, patterns in literal_classes(needles):
        where = [(f, sum(len(re.findall(p, texts[f])) for p in patterns))
                 for f in files]
        hits.append((name, [(f, n) for f, n in where if n]))

    by_class = {k: [] for k in SHAPE_CLASSES}
    by_class_hex = {k: [] for k in DIGEST_CLASSES}
    aside, declared_seen, code_seen, reserved_seen = {}, {}, {}, {}
    objects_seen, digests_seen = {}, {}
    for token, (placement, what) in sorted(address_tokens(texts).items()):
        if _is_disclosed(token, DISCLOSED):
            continue                            # counted in the DISCLOSED census
        if any(token.lower() == v.lower() for v in seat):
            continue                            # counted under that seat key's class
        if placement == "hit":
            by_class.setdefault(what, []).append(token)
        elif placement == "reserved":
            reserved_seen.setdefault(token, 0)
        else:
            aside.setdefault(what, []).append(token)

    for token, (placement, what) in sorted(fingerprint_tokens(texts, repo, digests).items()):
        if placement == "hit":
            by_class_hex[what].append(token)
        elif placement == "object":
            objects_seen[token] = 1
        else:
            digests_seen[token] = what

    for token in sorted({t for text in texts.values() for t in _UUID.findall(text)}):
        if _UUID_RESERVED.match(token):
            reserved_seen.setdefault(token, 0)
        else:
            by_class.setdefault(UUID_CLASSES[0], []).append(token)

    for token, (placement, what) in sorted(host_tokens(
            texts, DISCLOSED, DECLARED_PUBLIC, seat).items()):
        if placement == "hit":
            by_class.setdefault(what, []).append(token)
        elif placement == "aside":
            aside.setdefault(what, []).append(token)
        elif placement == "declared":
            declared_seen.setdefault(token, 0)
        elif placement == "code":
            code_seen.setdefault(token, 0)
        elif placement == "reserved":
            reserved_seen.setdefault(token, 0)

    for klass in SHAPE_CLASSES:
        if klass in DIGEST_CLASSES:
            tokens = by_class_hex[klass]
            where = [(f, sum(_count_hex(t, texts[f]) for t in tokens)) for f in files]
        elif klass in UUID_CLASSES:
            tokens = by_class.get(klass, [])
            where = [(f, sum(_count_hex(t, texts[f]) for t in tokens)) for f in files]
        else:
            tokens = by_class.get(klass, [])
            where = [(f, sum(_count(t, texts[f]) for t in tokens)) for f in files]
        hits.append((klass, [(f, n) for f, n in where if n]))
    # A class this file did not foresee is still a class: reported, never dropped.
    for klass in sorted(set(by_class) - set(SHAPE_CLASSES)):
        where = [(f, sum(_count(t, texts[f]) for t in by_class[klass])) for f in files]
        hits.append((klass, [(f, n) for f, n in where if n]))

    aside_rows = []
    for reason, tokens in sorted(aside.items()):
        total = sum(sum(_count(t, texts[f]) for t in tokens) for f in files)
        aside_rows.append((reason, len(set(tokens)), total))

    disclosed = [(needle, [(f, _count_ci(needle, texts[f])) for f in files
                           if _count_ci(needle, texts[f])]) for needle in DISCLOSED]
    declared = [(t, DECLARED_PUBLIC.get(t.lower(), DECLARED_PUBLIC.get(t, "")),
                 sum(1 for f in files if _count(t, texts[f])))
                for t in sorted(declared_seen)]
    code = [(t, DECLARED_CODE[t], sum(1 for f in files if _count(t, texts[f])))
            for t in sorted(code_seen)]
    reserved = [(t, sum(1 for f in files if (_count_hex(t, texts[f]) if _UUID.match(t)
                                             else _count(t, texts[f]))))
                for t in sorted(reserved_seen)]
    digests = {"objects": len(objects_seen),
               "declared": [(t[:7], why, sum(1 for f in files if _count_hex(t, texts[f])))
                            for t, why in sorted(digests_seen.items())]}
    return files, hits, disclosed, declared, reserved, aside_rows, code, digests


def _count_ci(needle, text):
    ch = _token_ch(needle)
    return len(re.findall(_left(ch) + re.escape(needle) + _right(ch), text, re.I))


def render_statement(files, hits, disclosed, declared, reserved, aside_rows, code, digests):
    """The identifier statement, PRODUCED by the scan and never typed."""
    total = sum(sum(n for _f, n in where) for _c, where in hits)
    lines = [
        "Identifier statement -- RENDERED by train_pin_scan.py (in this bundle) from a scan",
        "of all %d file(s) in it, none excluded, the scanner and this log included." % len(files),
        "No line below is typed prose.",
        "",
        "PROHIBITED -- every class this scanner reports, 0 required:",
    ]
    for name, where in hits:
        lines.append("  %-50s : %d hit(s)%s"
                     % (name, sum(n for _f, n in where),
                        ("  IN " + ", ".join(f for f, _n in where)) if where else ""))
    lines += [
        "",
        "  TOTAL %d hit(s) across %d classes." % (total, len(hits)),
        "",
        "SANCTIONED -- counted, not removed. Present in:",
    ]
    for needle, where in disclosed:
        lines.append("  %-32s : %d file(s)" % (needle, len(where)))
    if declared:
        lines += ["", "DECLARED public hosts -- they name no machine of this deployment:"]
        for token, why, n in declared:
            lines.append("  %-32s : %d file(s)  -- %s" % (token, n, why))
    if code:
        lines += ["", "DECLARED dotted names that could resolve and are not hosts (by exact "
                      "spelling):"]
        for token, why, n in code:
            lines.append("  %-32s : %d file(s)  -- %s" % (token, n, why))
    lines += ["", "HEX RUNS of 32+ characters that are not hits: %d distinct object id(s) of "
                  "the repository, and by declaration:" % digests["objects"]]
    for short, why, n in digests["declared"]:
        lines.append("  %s...  : %d file(s)  -- %s" % (short, n, why))
    if reserved:
        lines += ["", "RESERVED documentation names and addresses (RFC 2606/6761/5737/3849):"]
        for token, n in reserved:
            lines.append("  %-32s : %d file(s)" % (token, n))
    lines += [
        "",
        "SET ASIDE by rules derived FROM THIS BUNDLE -- dotted tokens that CANNOT RESOLVE,",
        "each counted under the rule that placed it:",
    ]
    for reason, distinct, occurrences in aside_rows:
        lines.append("  %-4d distinct, %5d occurrence(s)  %s" % (distinct, occurrences, reason))
    return "\n".join(lines) + "\n"


def statement_in(path):
    text = io.open(path, encoding="utf-8", errors="replace").read()
    if OPEN_MARK not in text or CLOSE_MARK not in text:
        return None
    body = text.split(OPEN_MARK, 1)[1].split(CLOSE_MARK, 1)[0]
    return body.strip("\n").replace("\r\n", "\n") + "\n"


def check_statement(bundle, needles, path, repo=None):
    """Red when a document's statement is not what a fresh scan renders."""
    rendered = render_statement(*scan(bundle, needles, repo))
    carried = statement_in(path)
    if carried is None:
        print("REFUSED: %s carries no statement block between %s and %s"
              % (os.path.basename(path), OPEN_MARK, CLOSE_MARK))
        return 1
    if carried == rendered:
        print("OK: the statement in %s is exactly what a fresh scan renders (%d lines)."
              % (os.path.basename(path), len(rendered.splitlines())))
        return 0
    print("REFUSED: the statement in %s is not what a fresh scan renders."
          % os.path.basename(path))
    return 1


HEADER = [
    "# The SHAPE census -- counted in the PIN line since round 11 (R10-H1). Every file",
    "# in this bundle, this log and the scanner that wrote it included, searched for",
    "# every class of identifier SHAPE. Only the CLASS and the count are printed: a log",
    "# that names the needle carries the identifier (#441).",
    "#",
    "# pin-census.log (train_pin_needles.py) proves every KNOWN sensitive value absent",
    "# and classifies every file. This census reads EVERY file, whatever its class, for",
    "# the shapes an unknown value would have -- a tracked copy or a generated file can",
    "# carry one as well as a typed file -- and every hit counts in the PIN line. The",
    "# list of shapes is finite: a value of no listed shape is found by nothing here.",
    "#",
    "# The scanner is IN this bundle (train_pin_scan.py); its literal needles, and the",
    "# values its controls plant for those classes, are NOT: they live in a sidecar",
    "# outside every bundle, and the scanner refuses to run without it.",
    "#",
    "# The class list is FIXED: every class is printed, with zero when nothing is found.",
    "# A dotted name whose final label could resolve is a hit unless it is sanctioned,",
    "# reserved, a seat value or DECLARED here by exact spelling; the rules derived from",
    "# the bundle place only names that cannot resolve. A 40-hex run is set aside only",
    "# when git names it an object of the repository, or it is declared by value.",
    "",
]


def report(bundle, needles, repo=None, digests=None):
    result = scan(bundle, needles, repo, digests)
    files, hits, disclosed, declared, reserved, aside_rows, code, digests = result
    statement = render_statement(*result)
    total = sum(sum(n for _f, n in where) for _c, where in hits)
    out = list(HEADER)
    wide = sum(1 for f in files if f.endswith(WIDE_SUFFIX))
    out += ["%d file(s) scanned, none excluded, %d of them also read as the UTF-16LE text "
            "they hold. A repository was %s for the object-id question."
            % (len(files) - wide, wide, "named" if repo else "NOT named -- so every 40-hex "
                                                            "run that is not declared is a hit"),
            ""]
    for name, where in hits:
        line = "CLASS %-50s : %d hit(s)" % (name, sum(n for _f, n in where))
        if where:
            line += "  IN %s" % ", ".join("%s (%d)" % (f, n) for f, n in where)
        out.append(line)
    out += ["", "TOTAL: %d hit(s) across %d classes" % (total, len(hits)), ""]
    out += [
        "# DISCLOSED, not removed: the public service hostname and the LAN addresses of the",
        "# two backend boxes and the edge -- what the tool probes and deploys to. The",
        "# integrator sanctioned them; the BASIS was checked with `git grep -n`:",
        "#   competitive-rounds.duckdns.org -> backend/nginx/app.conf, plugin/Plugin.cs",
        "#   192.168.72.90  (the standby)   -> plugin/ApiClient.cs",
        "#   192.168.72.102 (the edge)      -> backend/docker-compose.tls.yml",
        "#   192.168.72.199 (the primary)   -> NO TRACKED FILE CARRIES IT; it rests on the",
        "#                                     ruling alone.",
        "",
    ]
    for needle, where in disclosed:
        out.append("%-32s : %d file(s)%s"
                   % (needle, len(where),
                      ("  " + ", ".join(f for f, _n in where)) if where else ""))
    out += ["", "# DECLARED public hosts, DECLARED non-host names, declared digests and",
            "# RESERVED documentation names: counted, never filtered out.", ""]
    for token, why, n in declared:
        out.append("PUBLIC %-32s : %d file(s)  -- %s" % (token, n, why))
    for token, why, n in code:
        out.append("CODE   %-32s : %d file(s)  -- %s" % (token, n, why))
    out.append("OBJECT %d distinct 40-hex run(s) that git names objects of the repository"
               % digests["objects"])
    for short, why, n in digests["declared"]:
        out.append("DIGEST %s... : %d file(s)  -- %s" % (short, n, why))
    for token, n in reserved:
        out.append("RESERVED %-30s : %d file(s)  -- reserved for documentation"
                   " (RFC 2606/6761/5737/3849), or the nil or max UUID (RFC 9562)"
                   % (token if not _UUID.match(token) else "a reserved UUID", n))
    out += ["", "# SET ASIDE, by rules DERIVED from this bundle -- names that cannot resolve.",
            "# Each line is a rule, the number of distinct tokens it placed and their total",
            "# occurrences.", ""]
    for reason, distinct, occurrences in aside_rows:
        out.append("ASIDE %-4d distinct, %6d occurrence(s)  %s" % (distinct, occurrences, reason))
    out += ["", "# The statement, rendered from the scan above.", ""]
    out += [OPEN_MARK] + statement.splitlines() + [CLOSE_MARK]
    return "\n".join(out) + "\n", total, statement


# ---------------------------------------------------------------------------
# R8-H6: the same census, over every REACHABLE GIT OBJECT of a commit range.

def _git(repo, args, stdin=None, env=None):
    """Every git process of this census: replacement objects OFF, option and environment."""
    out = subprocess.run(["git", "--no-replace-objects", "-C", repo] + list(args),
                         capture_output=True, text=True, encoding="utf-8", errors="replace",
                         input=stdin, env=dict(os.environ if env is None else env,
                                               **NO_REPLACE_ENV))
    if out.returncode != 0:
        raise Refusal("git %s failed in this repository (rc=%d). Nothing has been scanned."
                      % (" ".join(args[:2]), out.returncode))
    return out.stdout


def object_texts(repo, rng, limit_bytes=8 * 1024 * 1024):
    """{'<sha7> <path>': text} for every blob reachable in `rng` and not before it."""
    listing = _git(repo, ["rev-list", "--objects", rng])
    texts = {}
    for line in listing.splitlines():
        parts = line.split(None, 1)
        if len(parts) != 2:
            continue                             # a commit or a tree root
        sha, path = parts[0], parts[1]
        kind = _git(repo, ["cat-file", "-t", sha]).strip()
        if kind != "blob":
            continue
        size = int(_git(repo, ["cat-file", "-s", sha]).strip() or 0)
        body = _git(repo, ["cat-file", "blob", sha])
        if size > limit_bytes:
            texts["%s %s (first %d bytes of %d)" % (sha[:7], path, limit_bytes, size)] = \
                body[:limit_bytes]
            continue
        texts["%s %s" % (sha[:7], path)] = body
    # ...and every COMMIT message in the range: a message is pushed as surely as a blob.
    for sha in _git(repo, ["rev-list", rng]).split():
        texts["%s (commit message)" % sha[:7]] = _git(repo, ["log", "-1", "--format=%B", sha])
    return dict(sorted(texts.items()))


def scan_objects(repo, rng, needles):
    """The census over a commit range's objects. Answers (text, total hits, per-class)."""
    texts = object_texts(repo, rng)
    if not texts:
        raise Refusal("the range %s reaches no blob at all. A census over nothing reports "
                      "zero and means nothing (#441)." % rng)
    files, hits, disclosed, declared, reserved, aside_rows, code, digests = _scan_texts(
        texts, needles, repo)
    total = sum(sum(n for _f, n in where) for _c, where in hits)
    blobs = len([f for f in files if not f.endswith("(commit message)")])
    out = [
        "# OBJECT-RANGE CENSUS (R8-H6). Every blob reachable from the new commits of",
        "#   %s" % rng,
        "# and not from its base, read with `git cat-file`, and every commit message of",
        "# the range, placed by the same rules the file census uses. A file scan sees the",
        "# TIP; a push sends the RANGE.",
        "",
        "%d blob(s) and %d commit message(s) in this range, none excluded."
        % (blobs, len(files) - blobs),
        "",
    ]
    for name, where in hits:
        line = "CLASS %-50s : %d hit(s)" % (name, sum(n for _f, n in where))
        if where:
            line += "  IN %s" % ", ".join("%s (%d)" % (f, n) for f, n in where)
        out.append(line)
    out += ["", "OBJECT-RANGE TOTAL: %d hit(s) across %d classes" % (total, len(hits)), ""]
    for needle, where in disclosed:
        out.append("%-32s : %d object(s)  -- sanctioned, counted" % (needle, len(where)))
    for token, why, n in declared:
        out.append("PUBLIC %-32s : %d object(s)  -- %s" % (token, n, why))
    for token, why, n in code:
        out.append("CODE   %-32s : %d object(s)  -- %s" % (token, n, why))
    out.append("OBJECT %d distinct 40-hex run(s) that git names objects of the repository"
               % digests["objects"])
    for short, why, n in digests["declared"]:
        out.append("DIGEST %s... : %d object(s)  -- %s" % (short, n, why))
    for token, n in reserved:
        out.append("RESERVED %-30s : %d object(s)  -- reserved for documentation" % (token, n))
    out += ["", "# SET ASIDE, by rules derived from the range's own objects.", ""]
    for reason, distinct, occurrences in aside_rows:
        out.append("ASIDE %-4d distinct, %6d occurrence(s)  %s" % (distinct, occurrences, reason))
    return "\n".join(out) + "\n", total, hits


# ---------------------------------------------------------------------------
# R12-L2: the pre-commit self-check IN THE LANE. D11 recurred through round 12 --
# two committed tips (a5d17d7, 88c7c02) carried undeclared document-name hits
# until 54d398b declared them, so a pin assembled from either could not support
# its zero-shape claim. The fix is process, not another enumeration: before a
# lane commit, run THIS shape census against the STAGED tree and REFUSE the commit
# outright when the shape count is non-zero, naming the undeclared site. A commit
# like a5d17d7/88c7c02 then cannot land: the gate stops it until every new shape
# is declared in the tables above, in the same commit or an earlier one. It is
# forward-looking; it cannot clean committed history, so those commits stay a
# recorded residual.

LANE_PREFIXES = ("tools/train_pin/", "backend/tests/test_pc_steam_server.py")


def staged_texts(repo, prefixes=LANE_PREFIXES):
    """{path: text} for every ACM-staged lane file, read from its STAGED blob (`git show
    :path`) -- exactly what the commit will carry, not the worktree."""
    raw = _git(repo, ["diff", "--cached", "--name-only", "--diff-filter=ACM", "-z"])
    texts = {}
    for path in (p for p in raw.split("\x00") if p):
        if any(path == pre or path.startswith(pre) for pre in prefixes):
            texts[path] = _git(repo, ["show", ":" + path])
    return texts


def staged_gate(texts, needles, repo=None, digests=None):
    """The gate's core: the shape census over a {path: text} corpus, and the refuse decision.
    Returns (total, lines): the shape-hit count and one line per hit class naming the class,
    its count and the files -- never a token's value. The gate refuses when total is non-zero."""
    hits = _scan_texts(texts, needles, repo, digests)[1]
    total = sum(sum(n for _f, n in where) for _c, where in hits)
    lines = ["CLASS %-50s : %d hit(s)  IN %s"
             % (name, sum(n for _f, n in where), ", ".join("%s (%d)" % (f, n) for f, n in where))
             for name, where in hits if where]
    return total, lines


def staged_check(repo, needles):
    """Run the gate against the staged tree. 0 clean (the commit may proceed), 1 refused."""
    texts = staged_texts(repo)
    if not texts:
        print("[train-pin-precommit] no staged lane file; nothing to check.")
        return 0
    total, lines = staged_gate(texts, needles, repo)
    if total:
        print("REFUSED by the lane pre-commit shape gate: %d undeclared shape hit(s) in the "
              "staged tree. Declare each in train_pin_scan.py before committing (R12-L2):"
              % total)
        for line in lines:
            print("  " + line)
        return 1
    print("[train-pin-precommit] %d staged lane file(s): 0 undeclared shape hit(s)."
          % len(texts))
    return 0


# ---------------------------------------------------------------------------
# The controls. One per REPORTED class, each planting a value OF THAT CLASS into
# a throwaway bundle and requiring a hit IN THAT CLASS, and an inert twin of the
# same shape that must leave that class at zero. No value of a prohibited class
# is written in this file: a planted value is documentation space, the seat's
# own value read at run time, a value the sidecar supplies, or composed here at
# run time from parts that are not themselves one.

def _v4(*octets):
    return str(ipaddress.IPv4Address(sum(o << (8 * (3 - i)) for i, o in enumerate(octets))))


def _v6(*groups):
    value = 0
    for g in groups[:-1]:
        value = (value << 16) | g
    value = (value << (16 * (8 - len(groups) + 1))) | groups[-1]
    return str(ipaddress.IPv6Address(value))


def _composed(*parts):
    return "".join(parts)


def _digest(n, salt):
    return (hashlib.sha512(salt.encode()).hexdigest() * 2)[:n]


def class_controls(needles, repo):
    """[(class, planted text, twin text, extra seat entries or None)] -- one per class."""
    conf = seat_conf(needles["seat_conf"])
    samples = needles.get("samples") or {}
    rows = []
    for name, _patterns in needles["fixed"]:
        sample = samples.get(name)
        if not sample or not sample.get("planted") or not sample.get("twin"):
            raise Refusal("the sidecar supplies no planted value and twin for the class %r. A "
                          "class without a control is a list of names (#441)." % name)
        rows.append((name, sample["planted"], sample["twin"], None))
    url = conf.get("origin_url") or ""
    parts = [p for p in url.split("/") if p]
    seat_rows = {
        "controller identifier": (conf.get("controller"), "a-controller"),
        "inventory group identifier": (conf.get("pve_group"), "a-group"),
        "seat remote URL": (url, "https://github.com/ACCOUNT/SidsCompetitiveRounds.git"),
        "play directory": (conf.get("play_dir"), "/srv/a-play-dir/playbooks"),
        ACCOUNT_HANDLE: (parts[-2] if len(parts) >= 3 else None, "a-handle"),
    }
    for name in SEAT_CLASSES:
        if name == UNCLASSED_SEAT_KEY:
            planted = _composed("a-new-seat-value-", str(len(SEAT_CLASSES)))
            rows.append((name, "configured " + planted, "configured a-other-value",
                         {"zz_unclassed_control": planted}))
            continue
        value, twin = seat_rows[name]
        if not value:
            raise Refusal("the seat holds no value for the class %r, so its control cannot be "
                          "planted. Nothing has been judged." % name)
        rows.append((name, "configured " + value, "configured " + twin, None))
    shape = {
        IPV4_CLASSES[0]: (_v4(127, 0, 0, 2), "192.0.2.2"),
        IPV4_CLASSES[1]: (_v4(169, 254, 1, 1), "192.0.2.1"),
        IPV4_CLASSES[2]: (_v4(10, 9, 8, 7), "198.51.100.7"),
        IPV4_CLASSES[3]: (_v4(172, 16, 5, 4), "198.51.100.4"),
        # The substring case of R8-H1: a quad one digit short of a sanctioned one.
        IPV4_CLASSES[4]: (DISCLOSED[1][:-1], DISCLOSED[1]),
        IPV4_CLASSES[5]: (_v4(198, 18, 0, 1), "203.0.113.1"),
        IPV4_CLASSES[6]: (_v4(11, 22, 33, 44), "203.0.113.44"),
        IPV6_CLASSES[0]: (_v6(0, 1), "2001:db8::2"),
        IPV6_CLASSES[1]: (_v6(0xfe80, 1), "2001:db8::3"),
        IPV6_CLASSES[2]: (_v6(0xfd00, 1), "2001:db8::4"),
        IPV6_CLASSES[3]: (_v6(0x2a00, 1, 1), "2001:db8::1"),
        "undeclared hostname": (_composed("A-Planted-Box", ".", "COM"),
                                "a-planted-box.example"),
        DIGEST_CLASSES[0]: (_digest(32, "a"), _digest(31, "a")),
        DIGEST_CLASSES[1]: (_digest(40, "b"), None),
        DIGEST_CLASSES[2]: (_digest(64, "c"), _digest(31, "c")),
        DIGEST_CLASSES[3]: (_composed("0x", _digest(48, "d")), _digest(30, "d")),
        # composed at run time, so this file holds no UUID of its own; the twin
        # is the nil UUID, which is reserved and never a hit
        UUID_CLASSES[0]: ("-".join(_digest(n, "u%d" % i) for i, n in
                                   enumerate((8, 4, 4, 4, 12))),
                          "-".join("0" * n for n in (8, 4, 4, 4, 12))),
    }
    for suffix in ALWAYS_HOST_SUFFIXES:
        klass = "undeclared hostname (%s)" % suffix
        if suffix == ".duckdns.org":
            shape[klass] = (_composed("a-planted-name", suffix),
                            DISCLOSED[3].upper())
        else:
            shape[klass] = (_composed("a-machine", suffix), "a-machine.invalid")
    # The 40-hex twin is an object the repository holds, when one is named, and
    # a declared value otherwise: the same shape, set aside for a stated reason.
    base_object = None
    if repo:
        base_object = _git(repo, ["rev-parse", "HEAD"]).strip()
    shape[DIGEST_CLASSES[1]] = (shape[DIGEST_CLASSES[1]][0],
                                base_object or sorted(DECLARED_DIGESTS)[0])
    for klass in SHAPE_CLASSES:
        planted, twin = shape[klass]
        rows.append((klass, "probe " + planted, "probe " + twin, None))
    return rows


def behaviour_controls():
    """The R8-H1 behaviours, each as a class the planted text must (or must not) reach.

    Every dotted name below is COMPOSED at run time: written whole in this
    file, a name ending in a real TLD would be a hit of this file's own census."""
    host = "undeclared hostname"
    dot = "."

    def name(first, last):
        return first + dot + last

    def lines(*parts):
        return "".join(p + NL for p in parts)

    return [
        ("a resolvable name whose first label the bundle assigns", host,
         lines("abox = 1", "print(%s)" % name("abox", "com")),
         lines("abox = 1", "print(%s)" % name("abox", "frob"))),
        ("a resolvable name adjacent to a path separator", host,
         lines("see /x/%s" % name("a-box", "sh")), lines("see /x/%s" % name("a-box", "frob"))),
        ("a resolvable name whose every occurrence is a call", host,
         lines("%s()" % name("abox", "io")), lines("%s()" % name("abox", "frob"))),
        ("a resolvable name whose final label the bundle defines", host,
         lines("com = 1", "print(%s)" % name("abox", "com")),
         lines("frob = 1", "print(%s)" % name("abox", "frob"))),
        ("a resolvable name whose extension the bundle uses", host,
         lines(name("a-box", "py"), "run /x/%s" % name("y", "py")),
         lines(name("a-box", "frob"), "run /x/%s" % name("y", "frob"))),
        ("a sanctioned hostname in capitals is still the sanctioned one", host,
         lines("reach %s" % name("a-planted-box", "org")),
         lines("reach %s" % DISCLOSED[3].upper())),
        ("a quad that is a substring of a sanctioned one is not sanctioned",
         IPV4_CLASSES[4], lines("probe %s" % DISCLOSED[0][:-1]),
         lines("probe %s" % DISCLOSED[0])),
        ("a declared non-host name is not a hit", host,
         lines("run %s()" % name("a-planted-box", "net")),
         lines("run %s()" % name("subprocess", "run"))),
        # R9: where a token begins and ends. Each context is planted around a
        # hit, and its twin is the same context around a reserved name or a
        # documentation quad -- or, for the last two, the same hit continued
        # by one more label, which makes it part of a longer token.
        ("a resolvable name that ends a sentence", host,
         lines("the box is %s." % name("a-planted-box", "com")),
         lines("the box is %s." % name("a-planted-box", "example"))),
        ("a resolvable name after a colon", host,
         lines("key:%s and" % name("a-planted-box", "com")),
         lines("key:%s and" % name("a-planted-box", "example"))),
        ("a resolvable name after an ellipsis", host,
         lines("see ...%s and" % name("a-planted-box", "com")),
         lines("see ...%s and" % name("a-planted-box", "example"))),
        ("a quad that ends a sentence", IPV4_CLASSES[2],
         lines("it answered from %s." % _v4(10, 9, 8, 7)),
         lines("it answered from %s." % "198.51.100.7")),
        ("a quad after a colon", IPV4_CLASSES[2],
         lines("addr:%s then" % _v4(10, 9, 8, 7)),
         lines("addr:%s then" % "198.51.100.7")),
        ("a quad after an ellipsis", IPV4_CLASSES[2],
         lines("see ...%s then" % _v4(10, 9, 8, 7)),
         lines("see ...%s then" % "198.51.100.7")),
        ("a name continued by another label is not its head", host,
         lines("see %s and" % name("a-planted-box", "com")),
         lines("see %s and" % name(name("a-planted-box", "com"), "frob"))),
        ("a quad continued by another number is not an address", IPV4_CLASSES[2],
         lines("version %s then" % _v4(10, 9, 8, 7)),
         lines("version %s.5 then" % _v4(10, 9, 8, 7))),
    ]


def _control_scan(text, needles, repo, extra_seat=None, wide=False):
    """Hits per class for one planted text, in a throwaway bundle (as UTF-16LE when `wide`)."""
    tmp = tempfile.mkdtemp(prefix="scr-scan-control-")
    # The modified seat file lives OUTSIDE the throwaway bundle: inside it, it
    # would be scanned, and it carries every real seat value.
    seat_dir = tempfile.mkdtemp(prefix="scr-scan-seat-")
    try:
        if wide:
            with open(os.path.join(tmp, "planted.bin"), "wb") as fh:
                fh.write(b"\xff\xfe" + (text + "\n").encode("utf-16-le"))
        else:
            io.open(os.path.join(tmp, "planted.txt"), "w", encoding="utf-8",
                    newline="").write(text + "\n")
        use = needles
        if extra_seat:
            conf = dict(seat_conf(needles["seat_conf"]))
            conf.update(extra_seat)
            conf_path = os.path.join(seat_dir, "seat.json")
            io.open(conf_path, "w", encoding="utf-8").write(json.dumps(conf))
            use = dict(needles, seat_conf=conf_path)
        result = _scan_texts(bundle_texts(tmp), use, repo)
        return {name: sum(n for _f, n in where) for name, where in result[1]}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        shutil.rmtree(seat_dir, ignore_errors=True)


def self_test(needles, repo=None):
    """Every class control and its twin, then the H1 behaviours; 0 when all pass."""
    rows = []
    controls = class_controls(needles, repo)
    for klass, planted, twin, extra in controls:
        for kind, body, expect_red in (("mutant", planted, True), ("twin", twin, False)):
            got = _control_scan(body, needles, repo, extra).get(klass, 0)
            red = got > 0
            rows.append((klass, kind, "RED" if red else "GREEN",
                         "RED" if expect_red else "GREEN",
                         "PASS" if red == expect_red else "FAIL", got))
    behaviours = []
    for what, klass, planted, twin in behaviour_controls():
        for kind, body, expect_red in (("mutant", planted, True), ("twin", twin, False)):
            got = _control_scan(body, needles, repo).get(klass, 0)
            red = got > 0
            behaviours.append((what, kind, "RED" if red else "GREEN",
                               "RED" if expect_red else "GREEN",
                               "PASS" if red == expect_red else "FAIL", got))
    # Round 11: a file written as UTF-16LE is read as the text it holds.
    uuid_row = [r for r in controls if r[0] == UUID_CLASSES[0]][0]
    for what, klass, planted, twin in (
            ("a UUID in a file written as UTF-16LE", UUID_CLASSES[0], uuid_row[1], uuid_row[2]),
            ("a private quad in a file written as UTF-16LE", IPV4_CLASSES[2],
             "probe %s" % _v4(10, 9, 8, 7), "probe 198.51.100.7")):
        for kind, body, expect_red in (("mutant", planted, True), ("twin", twin, False)):
            got = _control_scan(body, needles, repo, wide=True).get(klass, 0)
            red = got > 0
            behaviours.append((what, kind, "RED" if red else "GREEN",
                               "RED" if expect_red else "GREEN",
                               "PASS" if red == expect_red else "FAIL", got))
    # R12-L2: the pre-commit shape gate's decision -- refuse iff the staged tree carries a
    # shape hit. Exercised on an in-memory {path: text} corpus in both directions. The host
    # token is composed at run time, so this file holds no host literal of its own.
    host = _composed("a-staged-box", ".", "com")
    stub = _composed("tools/train_pin/staged-control", ".", "py")   # composed: no .py literal here
    for what, corpus, expect_red in (
            ("L2 the gate refuses a staged file with an undeclared host-shaped token",
             {stub: "H = '%s'\n" % host}, True),
            ("L2 negative: the gate passes a staged file with only the sanctioned public host",
             {stub: "H = '%s'\n" % DISCLOSED[3]}, False)):
        total, _lines = staged_gate(corpus, needles, repo)
        red = total > 0
        behaviours.append((what, "gate", "RED" if red else "GREEN",
                           "RED" if expect_red else "GREEN",
                           "PASS" if red == expect_red else "FAIL", total))
    reported = [name for name, _w in _scan_texts({"empty.txt": ""}, needles, repo)[1]]
    width = max(len(r[0]) for r in rows + behaviours)
    print("CLASS CONTROLS -- one planted value and one inert twin per reported class:")
    for klass, kind, got, want, verdict, n in rows:
        print("  %-*s  %-6s got %-5s want %-5s  %s (%d hit(s) in this class)"
              % (width, klass, kind, got, want, verdict, n))
    print("\nR8-H1 BEHAVIOURS -- the placement rules themselves:")
    for what, kind, got, want, verdict, n in behaviours:
        print("  %-*s  %-6s got %-5s want %-5s  %s" % (width, what, kind, got, want, verdict))
    failed = [r for r in rows + behaviours if r[4] == "FAIL"]
    covered = sorted({r[0] for r in rows})
    missing = [c for c in reported if c not in covered]
    print("\n  classes reported by a scan: %d   classes with a control: %d   without one: %d"
          % (len(reported), len(covered), len(missing)))
    for c in missing:
        print("  !! no control for the reported class %r" % c)
    print("  %d class arm(s) + %d behaviour arm(s), %d failed"
          % (len(rows), len(behaviours), len(failed)))
    return 1 if failed or missing else 0


def objects_self_test(repo, rng, needles):
    """R8-H6's control: a planted blob in a SCRATCH CLONE reddens the range census.

    The clone shares the repository's objects read-only (`--shared`) and every
    object the control writes lands in the clone's own store, which is deleted
    afterwards: the repository itself gains no object, ref or file."""
    base, _sep, tip = rng.partition("..")
    tip = tip or "HEAD"
    tmp = tempfile.mkdtemp(prefix="scr-objects-control-")
    rows = []
    try:
        clone = os.path.join(tmp, "clone")
        p = subprocess.run(["git", "--no-replace-objects", "clone", "--quiet", "--no-checkout",
                            "--shared", repo, clone], capture_output=True, text=True,
                           env=dict(os.environ, **NO_REPLACE_ENV))
        if p.returncode != 0:
            raise Refusal("the scratch clone could not be made (rc=%d)" % p.returncode)
        tip_sha = _git(repo, ["rev-parse", tip]).strip()
        base_sha = _git(repo, ["rev-parse", base]).strip()
        env = dict(os.environ, GIT_AUTHOR_NAME="control", GIT_AUTHOR_EMAIL="control@example.invalid",
                   GIT_COMMITTER_NAME="control", GIT_COMMITTER_EMAIL="control@example.invalid")
        klass = IPV4_CLASSES[4]
        for kind, text, expect_red in (
                ("mutant", "probe %s\n" % DISCLOSED[0][:-1], True),
                ("twin", "probe 192.0.2.19\n", False)):
            blob = _git(clone, ["hash-object", "-w", "--stdin"], stdin=text).strip()
            tree = _git(clone, ["ls-tree", tip_sha])
            tree += "100644 blob %s\tplanted-control.txt\n" % blob
            new_tree = _git(clone, ["mktree"], stdin=tree).strip()
            commit = _git(clone, ["commit-tree", new_tree, "-p", tip_sha, "-m",
                                  "a planted control"], env=env).strip()
            _text, total, hits = scan_objects(clone, "%s..%s" % (base_sha, commit), needles)
            got = sum(n for name, where in hits if name == klass for _f, n in where)
            red = got > 0
            rows.append((kind, "RED" if red else "GREEN", "RED" if expect_red else "GREEN",
                         "PASS" if red == expect_red else "FAIL", got, total))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    for kind, got, want, verdict, n, total in rows:
        print("  a blob planted in a scratch clone (%s): got %s want %s  %s  (%d hit(s) in "
              "%r, %d in the range)" % (kind, got, want, verdict, n, IPV4_CLASSES[4], total))
    failed = [r for r in rows if r[3] == "FAIL"]
    print("  %d arm(s), %d failed; the scratch clone is removed" % (len(rows), len(failed)))
    return 1 if failed else 0


def _arg(argv, flag):
    return argv[argv.index(flag) + 1] if flag in argv else None


def main():
    argv = sys.argv[1:]
    # R12-L2: the pre-commit shape gate. `--staged` reads the repo, never a bundle, so the
    # needle file is loaded with no bundle to be inside of.
    if argv and argv[0] == "--staged":
        repo = _arg(argv, "--repo") or os.environ.get("SCR_PIN_REPO") or "."
        needle_path = _arg(argv, "--needles") or os.environ.get("SCR_PIN_NEEDLES")
        try:
            needles = load_needles(needle_path, os.path.join(repo, "scr-no-bundle-staged-gate"))
            return staged_check(repo, needles)
        except Refusal as e:
            print("REFUSED: %s" % e)
            return 2
    if not argv or argv[0].startswith("--"):
        print(__doc__)
        return 2
    bundle = argv[0]
    needle_path = _arg(argv, "--needles") or os.environ.get("SCR_PIN_NEEDLES")
    repo = _arg(argv, "--repo") or os.environ.get("SCR_PIN_REPO")
    try:
        needles = load_needles(needle_path, bundle)
    except Refusal as e:
        print("REFUSED: %s" % e)
        return 2
    try:
        if "--check-statement" in argv:
            return check_statement(bundle, needles, _arg(argv, "--check-statement"), repo)
        if "--self-test" in argv:
            return self_test(needles, repo)
        if "--objects-self-test" in argv:
            return objects_self_test(bundle, _arg(argv, "--objects-self-test"), needles)
        rng = _arg(argv, "--objects")
        if rng and "--write" not in argv:
            text, total, _h = scan_objects(bundle, rng, needles)
            print(text)
            return 1 if total else 0
        text, total, statement = report(bundle, needles, repo)
        if "--statement" in argv:
            sys.stdout.write(statement)
            return 0
        if "--write" in argv:
            objects_text, objects_total = "", 0
            if rng:
                if not repo:
                    print("REFUSED: --objects with --write reads the range from --repo, and "
                          "none was named.")
                    return 2
                objects_text, objects_total, _h = scan_objects(repo, rng, needles)
            log = os.path.join(bundle, "pin-path-scan.log")
            io.open(log, "w", encoding="utf-8", newline="").write(
                text + ("\n" + objects_text if objects_text else ""))
            # ...and scan AGAIN with the log in place.
            again, total_again, _s = report(bundle, needles, repo)
            print(again)
            if objects_text:
                print(objects_text)
            if total_again != total:
                print("REFUSED: the log this scan wrote changed the census (%d -> %d hits). "
                      "The log itself carries something the bundle did not."
                      % (total, total_again))
                return 1
            print("re-scanned with pin-path-scan.log in place: %d hit(s), unchanged."
                  % total_again)
            if rng:
                print("object range %s: %d hit(s)" % (rng, objects_total))
            return 1 if total_again or objects_total else 0
        print(text)
        return 1 if total else 0
    except Refusal as e:
        print("REFUSED: %s" % e)
        return 2


if __name__ == "__main__":
    sys.exit(main())
