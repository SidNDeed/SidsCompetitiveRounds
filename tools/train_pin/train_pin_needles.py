#!/usr/bin/env python3
"""NEEDLES + PROVENANCE: the privacy census of the release-train lane's review pin.

Round 10 moved the privacy proof of a pin onto the two properties below. Round 11
(R10-H1) keeps them and counts the shape census (train_pin_scan.py) beside them:
it reads every file of every class, and a hit in any file counts in the PIN line.

1. NEEDLES -- every KNOWN sensitive value on this seat, derived at run time:
     seat        every string leaf of the seat configuration file;
     seat-part   the account handles and machine names inside those leaves (the
                 account of a remote URL, both sides of a user@host, the account
                 directory of a home path);
     guard       every pattern the pre-commit privacy guard checks -- the hook at
                 <git-common-dir>/hooks/pre-commit and every script it runs -- plus
                 the environment override that guard honours, when it is set. Round
                 12 (R11-H1) reads the hook's OWN text as the POSIX shell it is:
                 every word of every command is a unit, with the role its position
                 gives it. Each script the hook runs, and every hooks-dir module that
                 script imports, is walked WHOLE (round 11, R10-H2): every str and
                 bytes constant in any position, compositions (+, *, %, join,
                 f-strings) folded, and every import name and alias. A unit declared
                 in GUARD_DECLARED is an OCCURRENCE -- 16 hex digits of the sha256 of
                 its (file, role, kind, value), with the file, the role and a count
                 beside it; never the value -- and accounts for that occurrence only.
                 Every other unit is a pattern: the census refuses unless there are
                 exactly GUARD_PATTERNS of them and every declared occurrence is
                 found. Completeness against a NEW pattern is a CLOSED allow-list
                 plus refusal, never a list of constructors (R12-H1), in two
                 layers. At the sites where the guard turns an expression into an
                 active pattern (re.compile and the re-module pattern functions)
                 the pattern operand -- the first positional argument, or the
                 pattern= keyword when there is none -- is accepted only as a
                 folded string or bytes literal, a declared import unit, or a value
                 that resolves to one through the guard's single indirection; every
                 other operand, and an operand the call hides or leaves out,
                 refuses the census with the site named. And every Python module
                 walked for the guard is DECLARED by the shape of its code
                 (GUARD_SHAPE: one digest per top-level statement, with each text
                 constant reduced to a placeholder because GUARD_DECLARED accounts
                 for it), so every other change to the guard's code -- a site
                 reached through an alias or through another module, a matcher
                 that is not a regex, run-time text built anywhere -- refuses the
                 census with the statement's line named. Shell this reader does
                 not parse is refused;
     guard-held  the names the guard holds besides its pattern (every
                 parenthesised alternation in its comments and docstrings);
     user-path   this seat's user directory, spelled every way a path to it is
                 written: drive-rooted with either separator, rooted at the
                 shell's /<drive> form, and driveless with either separator (the
                 source never spells these forms: it composes them, so that it
                 carries no needle of its own);
     machine     this seat's machine name;
     identity    the repository's commit identity (user.name, user.email and the
                 email's local part);
     sidecar     the round-9 sidecar's typed classes, each pattern expanded to the
                 finite set of strings it matches (a pattern whose set is not finite
                 is counted and left to the shape census).
   A candidate is DROPPED, and counted by reason, when it is the maintainer's
   sanctioned name, a value train_pin_schema.SANCTIONED names, a public service
   host or account, the project's own public repository name, or shorter than
   three characters.
   Every needle is matched CASE-INSENSITIVELY, in raw bytes and in UTF-16LE at any
   offset (#157), and in its URL-encoded (single, path-safe, plus, double) and
   backslash-escaped (doubled, doubled twice, JSON, escaped solidus, unicode
   escape) forms. No needle is ever printed, logged or written: every scan prints
   `NEEDLES <n> sha256 <hex>` -- the count, and the sha256 of the sorted list of
   lower-cased needles joined by newlines.

2. PROVENANCE -- every pin file is EXACTLY ONE of
     TRACKED-COPY  byte-equal to the tracked blob its manifest entry names at the
                   pin commit;
     GENERATED     the exact output of a read-only git recipe over tracked commits,
                   re-run here and compared byte for byte; its producer (a tracked
                   file, equal to its blob at the pin commit), its run log and its
                   inputs are named;
     TYPED         everything else -- notes, briefs, reports, summaries, logs, and
                   the gitignored train.
   A file in no class, in two, or in a class whose check fails, FAILS the census.
   Tracked-ness and ignore proofs come from the PIN COMMIT'S OBJECTS alone (round
   11, R10-H4): tracked = membership in `git ls-tree -r <tip>`; ignored = the
   tip's own `.gitignore` blobs, materialised into an empty scratch repository and
   asked with `git check-ignore --no-index` there. No index or worktree query is a
   recipe, and every commit a recipe names is declared among its entry's inputs,
   with the pin commit the one it answers about.
   Every git process of these tools runs with replacement objects OFF, the option
   and the environment variable both (round 11, R10-H3): a `refs/replace/<id>`
   would otherwise answer another object's bytes under the original id.

THE BOUND (A5, restated in round 11 -- R10-H1): complete against every KNOWN
sensitive value -- every source above, in every form above, over every byte of every
pin file and of every object of the landing range. PROVENANCE proves where a file's
bytes came from and that they equal that source; it never proves that those bytes
hold no identifier nobody has named, so it is an ADDITIONAL proof and never a reason
to read a file less. Every file of the pin, whatever its class, is read whole by the
needle scan AND by the shape census (train_pin_scan.py), and a shape hit in any file
counts in the PIN line. An UNKNOWN value of a shape that census lists is found
wherever it sits; an unknown value of no listed shape is found by nothing here, and
this file claims nothing about it.

DECLARED COLLISIONS -- counted and printed, never filtered, never a finding:
  AS-SPELLED       a seat value that is a single all-lowercase word. Every spelling
                   is searched; the as-spelled occurrences are findings, the other
                   spellings (a capitalised product name in prose) are counted here.
  COMMIT-IDENTITY  an identity needle on the `author`/`committer` line of a commit
                   object, where git writes it on every commit. Anywhere else --
                   the message, a blob, a file name, a pin file -- it is a finding.
  EMBEDDED         a needle whose EVERY source pattern anchors it with a word
                   boundary (a sidecar pattern written `\\b...\\b`), found with a word
                   character on an anchored side: the characters of a short machine
                   name inside a longer, different word. Every other occurrence is a
                   finding. A needle from any unanchored source (seat, guard, user
                   path, machine, identity) is matched as a bare substring.

    python train_pin_needles.py describe  [--seat F] [--sidecar F] [--repo D]
    python train_pin_needles.py files     PATH... [--seat F] [--sidecar F] [--repo D]
    python train_pin_needles.py objects   --tip REV --not REV [--repo D] ...
    python train_pin_needles.py pin       PIN --tip REV --not REV --scratch DIR [--write] ...
    python train_pin_needles.py self-test --scratch DIR --tip REV --not REV [--pin PIN] ...

`--sidecar` defaults to SCR_PIN_NEEDLES; without it every command refuses, so
that every scan of a round uses the same needle set. Exit 0 = clean, 1 = a finding
or a failed control, 2 = refused (nothing was judged).
"""
import argparse
import ast
import collections
import hashlib
import importlib.util
import io
import itertools
import json
import os
import re
import secrets
import shutil
import stat
import socket
import subprocess
import sys
import tokenize
import urllib.parse
import zipfile
from pathlib import Path

try:                                        # Python 3.11 and later
    from re import _constants as _sre_c
    from re import _parser as _sre_parse
except ImportError:                         # pragma: no cover -- older interpreters
    import sre_constants as _sre_c
    import sre_parse as _sre_parse

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SEAT_DEFAULT = ROOT / "scripts" / "deploy" / "release_train.conf.json"
CHUNK = 1 << 20
EXPAND_CAP = 4096
MIN_LEN = 3
MAINTAINER = "sid"                          # the maintainer's sanctioned public name
PUBLIC_SERVICE = ("github.com", "gitlab.com", "bitbucket.org", "git")
CLASSES = ("TRACKED-COPY", "GENERATED", "TYPED")
# R10-H4 (round 11): a recipe asks about OBJECTS -- a commit range, a tree -- or,
# for the two ref-state recipes, about which refs exist now. An index or worktree
# query (`ls-files`, `check-ignore`, `status`) is never one: its answer moves with
# a staged removal or a dirty ignore rule while the pin commit stays where it is.
RECIPE_VERBS = ("diff", "log", "ls-tree", "for-each-ref", "branch")
RECIPE_FORBIDDEN = ("output", "exec", "ext-diff", "textconv", "upload", "receive", "--no-index")
DERIVATIONS = ("ignore-proof",)
SCOPE_PATHS = ("scripts/deploy/release_train.py", "scripts/deploy/release_train.conf.json")
MANIFEST = "provenance.json"
BOUND = ("complete against every KNOWN sensitive value (every source, every form, every "
         "byte of every file of every provenance class); an UNKNOWN value is found only "
         "when it has a shape the shape census lists, in any file of any class. "
         "Provenance proves origin and equality, never absence")
_FULL_SHA = re.compile(r"\A[0-9a-f]{40}\Z")
_FULL_RANGE = re.compile(r"\A([0-9a-f]{40})\.\.([0-9a-f]{40})\Z")
# R10-H3 (round 11): replacement objects OFF for every git process, twice over --
# the option on the command line and the variable in the environment -- as the
# train's own door does. Neither depends on the other being honoured.
NO_REPLACE_ENV = {"GIT_NO_REPLACE_OBJECTS": "1"}


class Refusal(Exception):
    """The census cannot run honestly; nothing it would print could be trusted."""


def _sibling(name):
    spec = importlib.util.spec_from_file_location("train_pin_needles_" + name,
                                                  str(HERE / (name + ".py")))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def git_env(env=None):
    """The environment of every git process here: the caller's, replacement OFF on top."""
    out = dict(os.environ if env is None else env)
    out.update(NO_REPLACE_ENV)
    return out


def git_argv(repo, args):
    """The command line of every git process here: `--no-replace-objects` before all else."""
    return (["git", "--no-replace-objects", "-C", str(repo), "-c", "core.quotepath=off",
             "-c", "color.ui=never"] + list(args))


def _git(repo, args, binary=False, stdin=None, env=None, check=True):
    p = subprocess.run(git_argv(repo, args), input=stdin, capture_output=True,
                       env=git_env(env))
    if check and p.returncode != 0:
        raise Refusal("git %s exited %d" % (args[0], p.returncode))
    return p.stdout if binary else p.stdout.decode("utf-8", "replace")


def recipe_problem(recipe, tip_sha, inputs):
    """Why a GENERATED file's recipe is not one this census re-runs, or None (R10-H4).

    Every commit a recipe names is spelled in full and DECLARED among the entry's
    inputs, and a diff, a log or a tree listing answers about the PIN COMMIT: a
    recipe cannot quietly answer about another commit, and it cannot ask an index
    or a worktree at all. The two ref-state recipes (`for-each-ref`, `branch -r
    --contains`) are the only questions about the present rather than about
    objects; their fixed forms below are all this census runs of them."""
    declared = {i.get("commit") for i in (inputs or []) if isinstance(i, dict)}
    if isinstance(recipe, dict):
        if recipe.get("derive") not in DERIVATIONS:
            return "a derivation this census does not know"
        if recipe.get("tip") != tip_sha:
            return "a derivation bound to another commit than the pin commit"
        if tip_sha not in declared:
            return "a derivation's commit is not declared among its inputs"
        paths = recipe.get("paths")
        if not (isinstance(paths, list) and paths
                and all(isinstance(p, str) and p and not p.startswith("-") for p in paths)):
            return "a derivation that names no paths"
        return None
    if not (isinstance(recipe, list) and recipe and all(isinstance(a, str) for a in recipe)):
        return "a recipe is a non-empty list of strings"
    verb, args = recipe[0], recipe[1:]
    if verb not in RECIPE_VERBS:
        return ("a recipe's verb must be one of %s; an index or worktree query is never a "
                "recipe" % ", ".join(RECIPE_VERBS))
    if any(any(bad in a for bad in RECIPE_FORBIDDEN) for a in args):
        return "a recipe argument names an option this census does not run"
    if "--" in args:
        head, paths = args[:args.index("--")], args[args.index("--") + 1:]
    else:
        head, paths = list(args), []
    for a in args:
        if _FULL_SHA.match(a) and a not in declared:
            return "a recipe names a commit its entry does not declare"
    operands = [a for a in head if not a.startswith("-")]
    if verb in ("diff", "log"):
        rng = _FULL_RANGE.match(operands[0]) if len(operands) == 1 else None
        if not rng:
            return "a %s recipe names exactly one range of two full commit ids" % verb
        if rng.group(1) not in declared or rng.group(2) not in declared:
            return "a recipe's range names a commit its entry does not declare"
        if rng.group(2) != tip_sha:
            return "a recipe's range does not end at the pin commit"
        return None
    if verb == "ls-tree":
        if operands != [tip_sha] or tip_sha not in declared:
            return "a tree listing names the pin commit, in full and declared, and nothing else"
        return None
    if verb == "for-each-ref":
        rest = list(head)
        if rest[:1] != ["--format=%(refname)"]:
            return "a ref listing prints ref names and nothing else"
        rest = rest[1:]
        if rest[:1] == ["--contains"]:
            if len(rest) < 2 or rest[1] not in declared:
                return "a ref listing's --contains names a declared commit"
            rest = rest[2:]
        if paths or not rest or not all(r.startswith("refs/") for r in rest):
            return "a ref listing names ref patterns and nothing else"
        return None
    if verb == "branch":
        if head[:2] != ["-r", "--contains"] or len(head) != 3 or head[2] not in declared \
                or paths:
            return "a branch recipe is `branch -r --contains <declared commit>` and nothing else"
        return None
    return "a recipe this census does not run"


def run_recipe(repo, recipe, tip_sha=None, inputs=None, scratch=None):
    """The bytes a GENERATED file must equal. Checked first; never an index or worktree read."""
    problem = recipe_problem(recipe, tip_sha, inputs)
    if problem:
        raise Refusal(problem)
    if isinstance(recipe, dict):
        return ignore_proof(repo, recipe["tip"], recipe["paths"], scratch)
    return _git(repo, recipe, binary=True)


def tip_paths(repo, tip_sha):
    """Every path the pin commit's TREE holds -- `ls-tree -r` of the commit, never the index."""
    out = _git(repo, ["ls-tree", "-r", "-z", "--name-only", tip_sha], binary=True)
    return [p.decode("utf-8") for p in out.split(b"\0") if p]


def ignore_verdicts(repo, tip_sha, paths, scratch):
    """([(path, tracked, ignored, rule or None)], .gitignore count) from the pin commit's OBJECTS.

    R10-H4. tracked = membership in `git ls-tree -r <tip>`. ignored = the answer of
    `git check-ignore --no-index -v` in a FRESH scratch repository that holds the
    tip's own `.gitignore` blobs -- every one its tree lists, at its own path --
    and nothing else: no template (so no exclude file), no system or global
    configuration, and an excludes file that does not exist. No index and no
    worktree of any repository is read, so a staged removal or a dirty ignore
    rule cannot move the answer; only a commit can.

    `-v` reports a path matched by a NEGATED rule too, with exit status 0; such a
    path is re-included, not ignored, and is reported as what it is."""
    if not scratch:
        raise Refusal("the ignore proof is derived in a scratch directory and none was named "
                      "(--scratch)")
    tree = tip_paths(repo, tip_sha)
    members = set(tree)
    rules = sorted(p for p in tree if p == ".gitignore" or p.endswith("/.gitignore"))
    root = Path(scratch)
    work = root / ("ignore-proof-" + secrets.token_hex(6))
    cfg = root / ("ignore-proof-cfg-" + secrets.token_hex(6))
    try:
        (cfg / "template").mkdir(parents=True)
        (cfg / "config").write_bytes(b"")
        env = git_env(dict(os.environ, GIT_CONFIG_NOSYSTEM="1",
                           GIT_CONFIG_GLOBAL=str(cfg / "config")))
        made = subprocess.run(["git", "--no-replace-objects", "init", "--quiet",
                               "--template=" + str(cfg / "template"), str(work)],
                              capture_output=True, env=env)
        if made.returncode != 0:
            raise Refusal("the scratch repository of the ignore proof could not be made "
                          "(rc=%d)" % made.returncode)
        for rule in rules:
            target = work.joinpath(*rule.split("/"))
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(_git(repo, ["cat-file", "blob", "%s:%s" % (tip_sha, rule)],
                                    binary=True))
        out = []
        for path in paths:
            p = subprocess.run(["git", "--no-replace-objects", "-C", str(work), "-c",
                                "core.excludesFile=" + str(cfg / "no-excludes"),
                                "check-ignore", "--no-index", "-v", "--", path],
                               capture_output=True, env=env)
            if p.returncode == 0:
                rule = p.stdout.decode("utf-8", "replace").rstrip("\r\n").split("\t", 1)[0]
                pattern = rule.split(":", 2)[2] if rule.count(":") >= 2 else ""
                out.append((path, path in members, not pattern.startswith("!"), rule))
            elif p.returncode == 1:
                out.append((path, path in members, False, None))
            else:
                raise Refusal("check-ignore answered rc=%d inside the ignore proof"
                              % p.returncode)
        return out, len(rules)
    finally:
        _rmtree(work)
        _rmtree(cfg)


def ignore_proof(repo, tip_sha, paths, scratch):
    """The bytes of the GENERATED ignore proof: `ignore_verdicts`, rendered."""
    verdicts, n = ignore_verdicts(repo, tip_sha, paths, scratch)
    lines = ["# derived from the objects of the pin commit %s alone: its tree listing and "
             "its %d .gitignore blob(s), asked with check-ignore --no-index in an empty "
             "scratch repository; no index and no worktree was read" % (tip_sha, n)]
    for path, tracked, ignored, rule in verdicts:
        lines.append("%s: tracked=%s ignored=%s rule=%s" % (
            path, "yes" if tracked else "no", "yes" if ignored else "no", rule or "none"))
    return ("\n".join(lines) + "\n").encode("utf-8")


def scope_problems(repo, tip_sha, scratch):
    """The lane's scope rule, asked of the pin commit's objects: the train and its seat file
    are neither tracked nor left unignored by the pin commit's own rules."""
    verdicts, _n = ignore_verdicts(repo, tip_sha, SCOPE_PATHS, scratch)
    out = []
    for path, tracked, ignored, _rule in verdicts:
        if tracked:
            out.append("%s is TRACKED at the pin commit" % path)
        if not ignored:
            out.append("%s is not ignored by the pin commit's own rules" % path)
    return out


# ---------------------------------------------------------------------------
# Finite expansion of a regular expression: every string it can match, or None.

class _Infinite(Exception):
    pass


def _product(a, b):
    if len(a) * len(b) > EXPAND_CAP:
        raise _Infinite()
    return {x + y for x in a for y in b}


def _seq(items):
    acc = {""}
    for op, av in items:
        acc = _product(acc, _item(op, av))
    return acc


def _item(op, av):
    name = str(op)
    if name == "LITERAL":
        return {chr(av)}
    if name in ("AT", "ASSERT", "ASSERT_NOT"):
        return {""}                          # zero width: dropping it only widens the match
    if name == "IN":
        chars = set()
        for iop, iav in av:
            iname = str(iop)
            if iname == "LITERAL":
                chars.add(chr(iav))
            elif iname == "RANGE" and iav[1] - iav[0] <= 64:
                chars.update(chr(c) for c in range(iav[0], iav[1] + 1))
            else:
                raise _Infinite()            # a negated class or a category
        return chars
    if name == "BRANCH":
        out = set()
        for branch in av[1]:
            out |= _seq(list(branch))
            if len(out) > EXPAND_CAP:
                raise _Infinite()
        return out
    if name == "SUBPATTERN":
        return _seq(list(av[-1]))
    if name in ("MAX_REPEAT", "MIN_REPEAT", "POSSESSIVE_REPEAT"):
        lo, hi, sub = av
        if hi == _sre_c.MAXREPEAT or hi > 8:
            raise _Infinite()
        one, out = _seq(list(sub)), set()
        for k in range(lo, hi + 1):
            acc = {""}
            for _ in range(k):
                acc = _product(acc, one)
            out |= acc
        return out
    raise _Infinite()                        # ANY, NOT_LITERAL, GROUPREF, CATEGORY ...


def expand(pattern):
    """Every string `pattern` matches, when that set is finite and small; else None."""
    try:
        parsed = _sre_parse.parse(pattern)
        return sorted(_seq(list(parsed)))
    except (_Infinite, re.error, OverflowError, RecursionError):
        return None


# ---------------------------------------------------------------------------
# The needle set.

class NeedleSet:
    def __init__(self, project=""):
        self.project = project.lower()
        self.cands = []                          # (literal, source)
        self.spelled_keys = set()                # seat sources whose value is one lowercase word
        self.drops = collections.Counter()       # (source family, reason) -> n
        self.nonfinite = collections.Counter()   # source family -> patterns not expandable
        self.read = collections.Counter()        # what was read, by kind
        self.items = []

    @staticmethod
    def family(source):
        return source.split(":", 1)[0]

    def add(self, literal, source, bounds=(False, False)):
        lit = (literal or "").strip()
        if not lit:
            return
        low = lit.lower()
        if len(low) < MIN_LEN:
            reason = "shorter than %d characters" % MIN_LEN
        elif low == MAINTAINER:
            reason = "the maintainer's sanctioned name"
        elif low in self.sanctioned:
            reason = "a value train_pin_schema.SANCTIONED names"
        elif low in PUBLIC_SERVICE:
            reason = "a public service host or account"
        elif self.project and low == self.project:
            reason = "the project's own public repository name"
        else:
            self.cands.append((lit, source, tuple(bounds)))
            return
        self.drops[(self.family(source), reason)] += 1

    def finish(self):
        merged = collections.OrderedDict()
        for lit, source, bounds in self.cands:
            key = lit.lower()
            entry = merged.setdefault(key, {"literal": lit, "lower": key, "sources": set(),
                                            "bounds": [True, True]})
            entry["sources"].add(source)
            # a side is anchored only when EVERY source anchors it
            entry["bounds"] = [entry["bounds"][0] and bounds[0],
                               entry["bounds"][1] and bounds[1]]
        identity = {k for k, e in merged.items()
                    if any(self.family(s) == "identity" for s in e["sources"])}
        items = []
        for key in sorted(merged):
            e = merged[key]
            rules = set()
            if (all(s in self.spelled_keys for s in e["sources"])
                    and re.fullmatch(r"[a-z]+", e["literal"])):
                rules.add("as-spelled")
            if key in identity:
                rules.add("identity")
            srcs = sorted(e["sources"])
            e["bounds"] = tuple(e["bounds"])
            e.update(sources=srcs, rules=rules,
                     label=srcs[0] + (" (+%d)" % (len(srcs) - 1) if len(srcs) > 1 else ""))
            items.append(e)
        self.items = items
        return self

    def digest(self):
        blob = "".join(i["lower"] + "\n" for i in self.items).encode("utf-8")
        return hashlib.sha256(blob).hexdigest()

    def line(self):
        return "NEEDLES %d sha256 %s" % (len(self.items), self.digest())

    def describe(self):
        per = collections.Counter()
        for i in self.items:
            for fam in sorted({self.family(s) for s in i["sources"]}):
                per[fam] += 1
        out = [self.line(), "BOUND " + BOUND]
        for fam in ("seat", "seat-part", "guard", "guard-held", "user-path", "machine",
                    "identity", "sidecar"):
            extra = []
            if fam == "seat":
                extra.append("string leaves read: %d" % self.read["seat-leaf"])
            if fam == "guard":
                extra.append("hook words read: %d, scripts read: %d, occurrences: %d, "
                             "declared: %d, patterns: %d (exactly %d declared), override: %s"
                             % (self.read["guard-hook-unit"], self.read["guard-script"],
                                self.read["guard-unit"], self.read["guard-declared"],
                                self.read["guard-pattern"], GUARD_PATTERNS,
                                "SET" if self.read["guard-override"] else "unset"))
            if fam == "guard-held":
                extra.append("alternations read: %d" % self.read["guard-alternation"])
            if fam == "sidecar":
                extra.append("patterns read: %d, not a finite set: %d (left to the shape "
                             "census)" % (self.read["sidecar-pattern"],
                                          self.nonfinite["sidecar"]))
            out.append("SOURCE %-10s %3d needle(s)%s" % (fam, per[fam],
                                                         ("  -- " + "; ".join(extra))
                                                         if extra else ""))
        spelled = sorted({s for i in self.items if "as-spelled" in i["rules"]
                          for s in i["sources"]})
        out.append("RULE   as-spelled %3d needle(s)  -- %s" % (
            sum(1 for i in self.items if "as-spelled" in i["rules"]),
            ", ".join(spelled) or "none"))
        out.append("RULE   identity   %3d needle(s)" %
                   sum(1 for i in self.items if "identity" in i["rules"]))
        out.append("RULE   anchored   %3d needle(s)  -- a word boundary on at least one side, "
                   "from the sidecar's own \\b...\\b patterns" %
                   sum(1 for i in self.items if any(i["bounds"])))
        if self.drops:
            for (fam, reason), n in sorted(self.drops.items()):
                out.append("DROPPED %-10s %3d  -- %s" % (fam, n, reason))
        else:
            out.append("DROPPED none")
        table = Table(self.items)
        out.append("FORMS  raw, URL-encoded x4, backslash-escaped x5; each in UTF-8 and "
                   "UTF-16LE; case-insensitive -> %d distinct byte pattern(s)"
                   % len(table.patterns))
        return out


def _walk_strings(node, path):
    if isinstance(node, dict):
        for k in sorted(node):
            yield from _walk_strings(node[k], "%s.%s" % (path, k) if path else str(k))
    elif isinstance(node, list):
        for n, v in enumerate(node):
            yield from _walk_strings(v, "%s[%d]" % (path, n))
    elif isinstance(node, str):
        yield path, node


def _parts(value):
    """(kind, text) for the account handles and machine names inside one seat value."""
    v = value.strip()
    out = []
    m = re.match(r"^[A-Za-z][A-Za-z0-9+.-]*://(?:([^@/]+)@)?([^/:]+)(?::\d+)?(/.*)?$", v)
    if m:
        userinfo, host, path = m.groups()
        if userinfo:
            out.append(("account", userinfo.split(":", 1)[0]))
        out.append(("host", host))
        segs = [s for s in (path or "").split("/") if s]
        if segs:
            out.append(("account", segs[0]))
        if len(segs) > 1:
            out.append(("project", re.sub(r"\.git$", "", segs[1])))
        return out
    m = re.match(r"^([^@\s/:]+)@([^:\s/]+)(?::(.*))?$", v)
    if m:
        user, host, path = m.groups()
        out += [("account", user), ("host", host)]
        segs = [s for s in (path or "").split("/") if s]
        if segs:
            out.append(("account", segs[0]))
        if len(segs) > 1:
            out.append(("project", re.sub(r"\.git$", "", segs[1])))
        return out
    segs = [s for s in re.split(r"[\\/]", v) if s]
    for n, s in enumerate(segs[:-1]):
        if s.lower() in ("home", "users"):
            out.append(("account", segs[n + 1]))
    return out


def _hooks_dir(repo):
    configured = _git(repo, ["config", "--get", "core.hooksPath"], check=False).strip()
    if configured:
        p = Path(configured)
        return p if p.is_absolute() else Path(_git(repo, ["rev-parse", "--show-toplevel"])
                                              .strip()) / p
    return Path(_git(repo, ["rev-parse", "--path-format=absolute", "--git-path",
                            "hooks"]).strip())


_ALT = re.compile(r"\(([^()]*\|[^()]*)\)")


def _alternatives(group):
    got = expand("(?:%s)" % group)
    if got is not None:
        return got
    # not a pattern this parser reads: take each alternative's word characters
    return [re.sub(r"\\[bBAZ]|[^A-Za-z0-9._@-]", "", alt) for alt in group.split("|")]


# ---------------------------------------------------------------------------
# The guard's constants (R10-H2, round 11; R11-H1, round 12).
#
# The pre-commit guard is a needle SOURCE: whatever it checks for is, by
# construction, something that must not travel. Round 10 read it narrowly -- an
# assignment whose target named PATTERN, and an `environ.get` inside one -- so a
# pattern held anywhere else (a list, a compiled expression, a call argument, an
# annotation, a default, an import alias, a composition) was silently not a
# needle, and the only refusal was "no pattern at all".
#
# The WHOLE syntax tree of the guard, and of every module beside it that it
# imports, is walked, and every string and bytes constant in any position is a
# UNIT: a composition that folds to one constant value (`+`, `%`, `*` by a
# number, `str.join`, an f-string with no field, and `.encode()`/`.decode()`/
# case and strip methods of a folded value) is ONE unit with the composed value,
# and an f-string with fields contributes each literal part. An import's module
# and alias names are units too. The number of patterns is declared EXACTLY
# (GUARD_PATTERNS): any other number refuses, so a pattern deleted, a pattern
# added anywhere, and a declared constant whose value changed all stop the
# census until a person looks. A pattern MOVED -- into a list, a call argument,
# a compiled expression -- is still one pattern and the count holds.
#
# Round 12 (R11-H1) closes the two gaps that enumeration still had.
#
# 1. The hook's OWN text. Round 11 read the hook only for the name of the script
#    it runs, so a `grep` or an `export` written into the hook itself -- a second
#    place a pattern can be checked, with the same Python child still run after
#    it -- was never a unit, and the count still read one. The hook is now read
#    as the POSIX shell it is (hook_units): every word of every command is a
#    unit -- the shebang, the command, each argument, each redirection target,
#    each assignment's value, and every word of a command substitution -- with
#    the role its position gives it. What this reader does not parse (a
#    backquote, a here-document, an arithmetic expansion, a parameter expansion
#    with an operator, a subshell, group or function body) is refused.
#
# 2. The declaration's KEY. Round 11 declared a constant by sha256(kind:value),
#    so ANY occurrence carrying a declared value was declared: a message the
#    guard prints, written again as the argument of a matcher, was satisfied by
#    the message's declaration and the count held. A declaration is now an
#    OCCURRENCE -- (file, role, kind, value) -- keyed by sixteen hex digits of
#    the sha256 of the four, with the file, the role and the number of times
#    that exact occurrence is declared written beside the key; never the value.
#    The role is DERIVED from the syntax tree, never typed: the enclosing
#    definitions and the path of positions from the statement down to the unit
#    (the callee and argument position of a call, a keyword's name, a
#    comparison's operators and side, an assignment's target names, a
#    docstring, an element, a dict key or value, a parameter's default). The
#    same value in another position, another function or another file is
#    another occurrence, and one occurrence too many at the same position is
#    one too many. Every declared occurrence must also be FOUND: a declared
#    constant deleted or changed refuses as well.
#
# What a walk of constants cannot see is a value the guard COMPUTES at run time
# from something that is not a constant. The constructs that turn numbers or
# bytes into text, evaluate code, or import by name are refused outright
# (GUARD_REFUSED_CALLS, GUARD_REFUSED_MODULES), and an environment key that is
# not a constant is refused; the one run-time source that stays is the
# environment override the guard is written to honour, whose value is read
# here, at census time, and is a needle when it is set. A pattern the guard
# would read out of a file or a process it runs is data this census does not
# see; that is its bound, stated rather than claimed away.

GUARD_PATTERNS = 1
GUARD_FOLD_METHODS = frozenset(("encode", "decode", "lower", "upper", "casefold", "strip",
                                "lstrip", "rstrip"))
GUARD_REFUSED_CALLS = frozenset(("chr", "eval", "exec", "compile", "__import__", "getattr",
                                 "open", "bytes", "bytearray", "vars", "globals", "locals"))
GUARD_REFUSED_ATTRS = frozenset(("fromhex", "to_bytes", "read_text", "read_bytes", "getenv",
                                 "import_module", "b64decode", "b32decode", "b16decode",
                                 "a85decode", "b85decode", "unhexlify", "decompress",
                                 "loads", "frombytes"))
GUARD_REFUSED_MODULES = frozenset(("codecs", "base64", "binascii", "importlib", "pickle",
                                   "marshal", "zlib", "gzip", "bz2", "lzma", "ctypes"))
GUARD_HOOK = "pre-commit"


class GuardUnit(collections.namedtuple("GuardUnit", "file role kind value pos")):
    """One OCCURRENCE of text in the guard: the file it is in, the role its position gives
    it, its kind (str, bytes, import, sh) and its value. `pos` (line, column, end line, end
    column) locates a Python unit for the self-test's edits and is not part of the key."""
    __slots__ = ()

    def key(self):
        """16 hex digits of sha256(file NUL role NUL kind NUL value). Never the value."""
        text = self.value.decode("latin-1") if isinstance(self.value, bytes) else self.value
        return hashlib.sha256("\0".join((self.file, self.role, self.kind, text))
                              .encode("utf-8")).hexdigest()[:16]


def _fold(node):
    """The one constant value an expression composes, or None when it composes none."""
    if isinstance(node, ast.Constant) and isinstance(node.value, (str, bytes)):
        return node.value
    if isinstance(node, ast.BinOp):
        if isinstance(node.op, ast.Add):
            a, b = _fold(node.left), _fold(node.right)
            if a is not None and b is not None and type(a) is type(b):
                return a + b
        if isinstance(node.op, ast.Mult):
            for s, n in ((node.left, node.right), (node.right, node.left)):
                v = _fold(s)
                if (v is not None and isinstance(n, ast.Constant) and type(n.value) is int
                        and 0 <= n.value <= 4096):
                    return v * n.value
        if isinstance(node.op, ast.Mod):
            v = _fold(node.left)
            right = node.right.elts if isinstance(node.right, ast.Tuple) else [node.right]
            args = [a.value if isinstance(a, ast.Constant) else _fold(a) for a in right]
            if v is not None and all(a is not None for a in args):
                try:
                    return v % tuple(args)
                except (TypeError, ValueError):
                    return None
    if isinstance(node, ast.JoinedStr):
        parts = [_fold(v) for v in node.values]
        if all(isinstance(p, str) for p in parts):
            return "".join(parts)
    if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
            and not node.keywords):
        base = _fold(node.func.value)
        if base is None:
            return None
        if (node.func.attr == "join" and len(node.args) == 1
                and isinstance(node.args[0], (ast.List, ast.Tuple))):
            items = [_fold(e) for e in node.args[0].elts]
            if all(i is not None and type(i) is type(base) for i in items):
                return base.join(items)
        if (node.func.attr in GUARD_FOLD_METHODS
                and all(isinstance(a, ast.Constant) for a in node.args)):
            try:
                return getattr(base, node.func.attr)(*[a.value for a in node.args])
            except (TypeError, ValueError, LookupError, UnicodeError):
                return None
    return None


def _environ_key(node):
    """For `os.environ.get(K, ...)` / `environ.get(K)` / `os.environ[K]`: (True, K or None)."""
    target = None
    if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
            and node.func.attr == "get"):
        target, key = node.func.value, (node.args[0] if node.args else None)
    elif isinstance(node, ast.Subscript):
        target, key = node.value, node.slice
    else:
        return False, None
    named = ((isinstance(target, ast.Attribute) and target.attr == "environ")
             or (isinstance(target, ast.Name) and target.id == "environ"))
    if not named:
        return False, None
    return True, (key.value if isinstance(key, ast.Constant) and isinstance(key.value, str)
                  else None)


def _dotted(node):
    """The dotted spelling of a callee or target, naming no constant value."""
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        return ".".join(reversed(parts))
    if isinstance(node, ast.Subscript):
        return ".".join([_dotted(node.value) + "[]"] + list(reversed(parts)))
    if isinstance(node, (ast.Tuple, ast.List)):
        return "(" + ",".join(_dotted(e) for e in node.elts) + ")"
    if isinstance(node, ast.Starred):
        return "*" + _dotted(node.value)
    head = "<%s>" % type(node).__name__.lower()
    return ".".join([head] + list(reversed(parts)))


def _step(parent, field, index):
    """The position a child holds under `parent`, in words that carry no constant value.

    No index of a statement list or a container enters it, so an inserted statement or
    element moves no other unit's role; a call's positional argument keeps its index,
    because which argument a value is decides what the call does with it."""
    if isinstance(parent, ast.Module):
        return None
    if isinstance(parent, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return "def %s" % parent.name if field == "body" else "def %s %s" % (parent.name, field)
    if isinstance(parent, ast.ClassDef):
        return ("class %s" % parent.name if field == "body"
                else "class %s %s" % (parent.name, field))
    if isinstance(parent, ast.arguments):
        if field == "defaults":
            params = (list(parent.posonlyargs) + list(parent.args))[-len(parent.defaults):]
            return "default of %s" % params[index].arg
        if field == "kw_defaults":
            return "default of %s" % parent.kwonlyargs[index].arg
        return "parameters %s" % field
    if isinstance(parent, ast.arg):
        return "annotation of %s" % parent.arg
    if isinstance(parent, ast.Call):
        name = _dotted(parent.func)
        if field == "args":
            return "call %s arg%d" % (name, index)
        if field == "keywords":
            return "call %s" % name
        return "callee %s" % name
    if isinstance(parent, ast.keyword):
        return "keyword %s" % (parent.arg or "**")
    if isinstance(parent, ast.Assign):
        return ("assign %s" % ",".join(_dotted(t) for t in parent.targets)
                if field == "value" else "assign target")
    if isinstance(parent, ast.AnnAssign):
        return "assign %s %s" % (_dotted(parent.target), field)
    if isinstance(parent, ast.AugAssign):
        return "augassign %s %s" % (_dotted(parent.target), type(parent.op).__name__)
    if isinstance(parent, ast.Compare):
        ops = ",".join(type(o).__name__ for o in parent.ops)
        return "compare %s %s" % (ops, "left" if field == "left" else "right%d" % index)
    if isinstance(parent, ast.Attribute):
        return "receiver of .%s" % parent.attr
    if isinstance(parent, ast.Subscript):
        return "subscript %s" % field
    if isinstance(parent, (ast.List, ast.Tuple, ast.Set)):
        return "element of %s" % type(parent).__name__.lower()
    if isinstance(parent, ast.Dict):
        return "dict key" if field == "keys" else "dict value"
    if isinstance(parent, ast.BoolOp):
        return "boolop %s" % type(parent.op).__name__
    if isinstance(parent, ast.BinOp):
        return "binop %s %s" % (type(parent.op).__name__, field)
    if isinstance(parent, ast.UnaryOp):
        return "unaryop %s" % type(parent.op).__name__
    if isinstance(parent, ast.JoinedStr):
        return "fstring part"
    if isinstance(parent, ast.FormattedValue):
        return "fstring field %s" % field
    if isinstance(parent, ast.Expr):
        return "statement"
    return "%s %s" % (type(parent).__name__, field)


# -- the pattern-construction sites: a CLOSED allow-list, fail-closed (R12-H1) -
# Rounds 10, 11 and 12 each raised the same HIGH from the other direction:
# R10-H2 a guard walk that read only some positions, R11-H1 a declaration keyed
# so an unrelated occurrence satisfied it, R12-H1 a numeric constant fed through
# str()/.encode() that the run-time-constructor DENY-LIST did not name. A deny
# -list of constructors is open-ended: the next round finds the next constructor
# (a decoder, a format, a join, a byte table) it does not list. Round 13 states
# completeness the other way round -- as a CLOSED ALLOW-LIST at the only places
# where the guard turns an expression into an active pattern: re.compile and the
# re-module functions that take a pattern as their first argument. The pattern
# operand is ACCEPTED only when it is a folded string or bytes literal, a
# declared import unit, or resolves -- through the one indirection the guard is
# built on (a name bound exactly once at module top level, .encode()/.decode()
# of such a value, or os.environ.get(<string literal>, <accepted>)) -- to one of
# those. EVERY other operand refuses the census with the site named: a numeric
# or other non-text constant, any call (str, chr, bytes, a decoder, a file read,
# eval), an attribute, an f-string, a non-folding composition, a name this
# resolver does not follow, anything not foldable. The resolver is TOTAL and
# returns False by default, so a constructor nobody has named is refused because
# it is not on the allow-list -- not because a deny-list grew to name it. The
# deny-list above (GUARD_REFUSED_*) is kept only as a redundant earlier refusal;
# completeness rests on this allow-list, never on that enumeration.

_RE_PATTERN_FUNCS = frozenset(("compile", "search", "match", "fullmatch", "findall",
                               "finditer", "sub", "subn", "split"))
_AMBIGUOUS = object()


def _re_callees(tree):
    """(names of the `re` module, {name: re-function} bound directly) in THIS module, however
    re was imported: `import re`, `import re as X`, `from re import compile [as c]`."""
    re_names, direct = set(), {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.name == "re":
                    re_names.add(a.asname or "re")
        elif isinstance(node, ast.ImportFrom) and node.module == "re":
            for a in node.names:
                if a.name in _RE_PATTERN_FUNCS:
                    direct[a.asname or a.name] = "re." + a.name
    return re_names, direct


def _imported_names(tree):
    """Every name this module binds by import -- a declared import unit is an accepted
    pattern text source (the census records it as a needle among the units)."""
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                names.add((a.asname or a.name).split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            for a in node.names:
                names.add(a.asname or a.name)
    return names


def _name_bindings(tree):
    """name -> the expression bound to it, ONLY when the name is stored exactly once in the
    whole module and that one store is a top-level `NAME = expr` or `NAME: ann = expr`. Any
    other name is absent (the resolver then refuses): a second binding, an augmented assign,
    a loop/with/comprehension target, a walrus, tuple unpacking, or an attribute/subscript
    store all leave the name out, so the resolver never trusts a value it cannot pin down."""
    stores = collections.Counter()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            stores[node.id] += 1
    once = {}
    for stmt in tree.body:
        if (isinstance(stmt, ast.Assign) and len(stmt.targets) == 1
                and isinstance(stmt.targets[0], ast.Name)):
            once[stmt.targets[0].id] = stmt.value
        elif (isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name)
              and stmt.value is not None):
            once[stmt.target.id] = stmt.value
    return {n: v for n, v in once.items() if stores[n] == 1}


def _accepts_pattern(node, binds, imported, seen=None):
    """True when this expression is an ACCEPTED pattern text source; False otherwise. Total
    and fail-closed: it never raises and refuses (returns False) on anything it cannot reduce
    to a folded literal or a declared import through the one indirection the guard uses."""
    seen = set() if seen is None else seen
    if _fold(node) is not None:                          # a folded str/bytes literal
        return True
    if isinstance(node, ast.Name):
        if node.id in imported:                          # a declared import unit
            return True
        if node.id in binds and node.id not in seen:     # bound once at module top level
            return _accepts_pattern(binds[node.id], binds, imported, seen | {node.id})
        return False
    if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
            and node.func.attr in ("encode", "decode") and not node.keywords
            and all(isinstance(a, ast.Constant) for a in node.args)):
        return _accepts_pattern(node.func.value, binds, imported, seen)  # .encode()/.decode()
    env, _key = _environ_key(node)
    if (env and isinstance(node, ast.Call) and len(node.args) >= 2
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)):    # os.environ.get(<literal>, <default>)
        return _accepts_pattern(node.args[1], binds, imported, seen)
    return False


def _pattern_operand(call):
    """(the expression a re call takes as its pattern, None), or (None, why the census cannot
    see one). Every re-module pattern function names its first parameter `pattern`, so the
    operand is the first positional argument, or the `pattern=` keyword when no positional
    argument is given. A starred first argument or a ** mapping hides it, and a call with
    neither has none to judge: each of those is refused by the caller, never skipped."""
    if call.args:
        if isinstance(call.args[0], ast.Starred):
            return None, "a starred first argument"
        return call.args[0], None
    for k in call.keywords:
        if k.arg == "pattern":
            return k.value, None
    if any(k.arg is None for k in call.keywords):
        return None, "a ** mapping"
    return None, "no pattern argument"


def pattern_site_refusals(tree, label):
    """Refuse every re.compile / re-module pattern call in this module whose pattern operand
    (the first positional argument, or the `pattern=` keyword) is not an ACCEPTED text source,
    or is hidden or absent. Names the site by file and line and the function; never the
    operand's value. A pattern reached by any other route than a call this layer recognises is
    a change to the guard's code, which the declared shape refuses (shape_refusals)."""
    re_names, direct = _re_callees(tree)
    binds = _name_bindings(tree)
    imported = _imported_names(tree)
    out = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        f = node.func
        fn = None
        if (isinstance(f, ast.Attribute) and f.attr in _RE_PATTERN_FUNCS
                and isinstance(f.value, ast.Name) and f.value.id in re_names):
            fn = "re." + f.attr
        elif isinstance(f, ast.Name) and f.id in direct:
            fn = direct[f.id]
        if fn is None:
            continue
        operand, hidden = _pattern_operand(node)
        if operand is None:
            out.append("a pattern site at %s:%s (%s) whose pattern operand this census cannot "
                       "see: %s" % (label, getattr(node, "lineno", "?"), fn, hidden))
        elif not _accepts_pattern(operand, binds, imported):
            out.append("a pattern built at %s:%s by %s from an operand that is not a folded "
                       "string or bytes literal or a declared import unit"
                       % (label, getattr(node, "lineno", "?"), fn))
    return out


# -- the guard's code, declared by its shape (R12-H1, the second layer) -------
# The site layer above judges the pattern calls it recognises, and recognising a
# call is itself a list: an alias of re.compile, a module reached through another
# module, a matcher that is not a regex at all. Completeness therefore does not
# rest on it. Every Python module the census walks for the guard is DECLARED by
# the shape of its code in GUARD_SHAPE -- one digest per top-level statement, in
# order -- and the census refuses a module whose shape is not the declared one,
# naming the first statement that differs. The shape is the syntax tree with every
# expression that folds to a str or bytes constant reduced to one placeholder
# (GUARD_DECLARED accounts for each of those by its occurrence, and the pattern
# is the one it leaves undeclared), and every other constant -- a number, None,
# True, False -- kept by its value. So any change to the code that is not a
# change of a text constant's value moves a digest: a new constructor of
# run-time text, a new site, an alias, a new matcher, a statement added, removed
# or reordered. A comment, a blank line, a line break inside brackets or a
# docstring's wording moves none. Nothing of any value is written here: a digest
# is 16 hex digits of the sha256 of the shape.
_SHAPE_SKIP = frozenset(("ctx", "type_comment", "kind", "type_ignores", "type_params"))


def _shape(node):
    """The canonical text of a node's shape (see above)."""
    if isinstance(node, list):
        return "[" + ",".join(_shape(x) for x in node) + "]"
    if not isinstance(node, ast.AST):
        return repr(node)
    if isinstance(node, ast.expr) and _fold(node) is not None:
        return "<text>"
    if isinstance(node, ast.Constant):
        return "(Constant %s %r)" % (type(node.value).__name__, node.value)
    return "(%s %s)" % (type(node).__name__, " ".join(
        "%s=%s" % (f, _shape(getattr(node, f, None))) for f in node._fields
        if f not in _SHAPE_SKIP))


def guard_shape(tree):
    """A module's declared-shape form: one digest per top-level statement, in order."""
    return tuple(hashlib.sha256(_shape(stmt).encode("utf-8")).hexdigest()[:16]
                 for stmt in tree.body)


def shape_refusals(tree, label, shapes=None):
    """Refuse a guard module whose shape is not the one GUARD_SHAPE (or `shapes`) declares
    for its file, naming the first statement that differs; never any value."""
    shapes = GUARD_SHAPE if shapes is None else shapes
    want, got = shapes.get(label), guard_shape(tree)
    if want is None:
        return ["the code of %s has no declared shape" % label]
    want = tuple(want)
    if want == got:
        return []
    for i, (w, g) in enumerate(zip(want, got)):
        if w != g:
            return ["the code of %s is not its declared shape at the statement on line %s"
                    % (label, getattr(tree.body[i], "lineno", "?"))]
    if len(got) > len(want):
        return ["the code of %s is not its declared shape: a statement added at line %s"
                % (label, getattr(tree.body[len(want)], "lineno", "?"))]
    return ["the code of %s is not its declared shape: %d declared statement(s) missing at "
            "its end" % (label, len(want) - len(got))]


def guard_units(script, hooks, seen=None, shapes=None):
    """(units, overrides, texts, refusals) of ONE guard script and every hooks-dir module it imports.

    units      [GuardUnit] -- every constant, folded, and every import name, each with
               its file (the name beside the hook) and the role its position gives it
    overrides  [environment variable NAME] -- the keys the guard reads at run time
    texts      [comment or docstring text] -- where held names are written
    refusals   [what] -- a construct that computes text this walk cannot see"""
    seen = set() if seen is None else seen
    script = Path(script)
    if script.resolve() in seen:
        return [], [], [], []
    seen.add(script.resolve())
    label = script.name
    src = script.read_text(encoding="utf-8")
    tree = ast.parse(src)
    units, overrides, refusals = [], [], []
    texts = [tok.string for tok in tokenize.generate_tokens(io.StringIO(src).readline)
             if tok.type == tokenize.COMMENT]
    siblings = []

    def at(node):
        return (getattr(node, "lineno", None), getattr(node, "col_offset", None),
                getattr(node, "end_lineno", None), getattr(node, "end_col_offset", None))

    def visit(node, path, docstring=False):
        env, key = _environ_key(node)
        if env:
            if key is None:
                refusals.append("an environment key that is not a constant")
            else:
                overrides.append(key)
        if isinstance(node, ast.Call):
            f = node.func
            if isinstance(f, ast.Name) and f.id in GUARD_REFUSED_CALLS:
                refusals.append("a call of %s" % f.id)
            if isinstance(f, ast.Attribute) and f.attr in GUARD_REFUSED_ATTRS:
                refusals.append("a call of .%s" % f.attr)
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            mods = [a.name for a in node.names] if isinstance(node, ast.Import) else \
                [node.module or ""]
            for m in mods:
                if m.split(".")[0] in GUARD_REFUSED_MODULES:
                    refusals.append("an import of %s" % m.split(".")[0])
                if m and (hooks / (m.split(".")[0] + ".py")).is_file():
                    siblings.append(hooks / (m.split(".")[0] + ".py"))
            where = " / ".join(path)
            if isinstance(node, ast.ImportFrom) and node.module:
                units.append(GuardUnit(label, (where + " / " if where else "")
                                       + "import module", "import", node.module, at(node)))
            for a in node.names:
                units.append(GuardUnit(label, (where + " / " if where else "") + "import name",
                                       "import", a.name, at(node)))
                if a.asname:
                    units.append(GuardUnit(label, (where + " / " if where else "")
                                           + "import alias", "import", a.asname, at(node)))
                if (isinstance(node, ast.ImportFrom) and node.module is None
                        and (hooks / (a.name + ".py")).is_file()):
                    siblings.append(hooks / (a.name + ".py"))
        folded = _fold(node)
        if folded is not None:
            role = " / ".join(path + (["docstring"] if docstring else [])) or "module"
            units.append(GuardUnit(label, role, "bytes" if isinstance(folded, bytes) else "str",
                                   folded, at(node)))
            return
        for field, value in ast.iter_fields(node):
            for index, child in enumerate(value if isinstance(value, list) else [value]):
                if not isinstance(child, ast.AST):
                    continue
                step = _step(node, field, index)
                sub = path + ([step] if step else [])
                if (field == "body" and index == 0 and isinstance(
                        node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
                        and isinstance(child, ast.Expr) and isinstance(child.value, ast.Constant)
                        and isinstance(child.value.value, str)):
                    visit(child.value, sub, docstring=True)
                    continue
                visit(child, sub)

    visit(tree, [])
    refusals += pattern_site_refusals(tree, label)      # R12-H1: the closed allow-list
    refusals += shape_refusals(tree, label, shapes)     # R12-H1: the declared shape
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            doc = ast.get_docstring(node, clean=False)
            if doc:
                texts.append(doc)
    for sib in siblings:
        u, o, t, r = guard_units(sib, hooks, seen, shapes)
        units += u
        overrides += o
        texts += t
        refusals += r
    return units, overrides, texts, refusals


# -- the hook, read as the POSIX shell it is (R11-H1) --------------------------
_SH_KEYWORDS = frozenset(("if", "then", "else", "elif", "fi", "do", "done", "while", "until",
                          "for", "in", "case", "esac", "!", "{", "}"))
_SH_REDIRECT = re.compile(r"[0-9]*(?:>>|>&|<&|<>|>\||&>>|&>|>|<)")
_SH_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")
_SH_PARAM = re.compile(r"\$(?:[A-Za-z_][A-Za-z0-9_]*|[0-9]|[@*#?$!-])")
_SH_BRACED = re.compile(r"\$\{(?:[A-Za-z_][A-Za-z0-9_]*|[0-9]+|[@*#?$!-])\}")


def _sh_closing(s, i):
    """The index of the `)` that closes a `$(` whose body starts at s[i], or -1."""
    depth, n = 1, len(s)
    while i < n:
        c = s[i]
        if c == "\\":
            i += 2
            continue
        if c == "'":
            j = s.find("'", i + 1)
            if j < 0:
                return -1
            i = j + 1
            continue
        if c == '"':
            i += 1
            while i < n and s[i] != '"':
                i += 2 if s[i] == "\\" else 1
            i += 1
            continue
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return -1


def _sh_dollar(s, i, out, subs, refusals):
    """Read the `$` expansion at s[i] into `out` (its literal spelling); the next index."""
    n = len(s)
    if s.startswith("$((", i):
        refusals.append("an arithmetic expansion")
        return n
    if s.startswith("$(", i):
        j = _sh_closing(s, i + 2)
        if j < 0:
            refusals.append("an unterminated command substitution")
            return n
        subs.append(s[i + 2:j])
        out.append("$(...)")
        return j + 1
    if s.startswith("${", i):
        m = _SH_BRACED.match(s, i)
        if not m:
            refusals.append("a parameter expansion with an operator")
            return n
        out.append(m.group(0))
        return m.end()
    m = _SH_PARAM.match(s, i)
    if m:
        out.append(m.group(0))
        return m.end()
    out.append("$")
    return i + 1


def _sh_word(s, i, refusals):
    """(text with its quotes removed, [each command substitution's text], next index)."""
    out, subs, n = [], [], len(s)
    while i < n:
        c = s[i]
        if c in " \t\n;&|<>()":
            break
        if c == "'":
            j = s.find("'", i + 1)
            if j < 0:
                refusals.append("an unterminated quote")
                return "".join(out), subs, n
            out.append(s[i + 1:j])
            i = j + 1
        elif c == '"':
            i += 1
            while i < n and s[i] != '"':
                if s[i] == "\\" and i + 1 < n and s[i + 1] in '$`"\\\n':
                    if s[i + 1] != "\n":
                        out.append(s[i + 1])
                    i += 2
                elif s[i] == "$":
                    i = _sh_dollar(s, i, out, subs, refusals)
                elif s[i] == "`":
                    refusals.append("a backquoted command")
                    return "".join(out), subs, n
                else:
                    out.append(s[i])
                    i += 1
            if i >= n:
                refusals.append("an unterminated quote")
                return "".join(out), subs, n
            i += 1
        elif c == "\\":
            if i + 1 < n and s[i + 1] != "\n":
                out.append(s[i + 1])
            i += 2
        elif c == "$":
            i = _sh_dollar(s, i, out, subs, refusals)
        elif c == "`":
            refusals.append("a backquoted command")
            return "".join(out), subs, n
        else:
            out.append(c)
            i += 1
    return "".join(out), subs, i


def _sh_tokens(s, comments, refusals):
    """[("word", text, subs) | ("redirect", op) | ("end", op)] -- comments collected aside."""
    toks, i, n = [], 0, len(s)
    while i < n:
        c = s[i]
        if c in " \t\r":
            i += 1
        elif s.startswith("\\\n", i):
            i += 2
        elif c == "\n":
            toks.append(("end", "\n"))
            i += 1
        elif c == "#":
            j = s.find("\n", i)
            j = n if j < 0 else j
            comments.append(s[i:j])
            i = j
        elif s.startswith(("&&", "||", ";;"), i):
            toks.append(("end", s[i:i + 2]))
            i += 2
        elif c in ";|" or (c == "&" and not s.startswith("&>", i)):
            toks.append(("end", c))
            i += 1
        elif c in "()":
            refusals.append("a subshell, group or function body")
            toks.append(("end", c))
            i += 1
        else:
            m = _SH_REDIRECT.match(s, i)
            if m:
                if m.group(0).endswith("<") and s.startswith("<", m.end()):
                    refusals.append("a here-document")
                toks.append(("redirect", m.group(0)))
                i = m.end()
            else:
                word, subs, i = _sh_word(s, i, refusals)
                toks.append(("word", word, subs))
    return toks


def _sh_units(toks, label, prefix, units, comments, refusals, depth=0):
    """Give every word of a command list its role: the position it holds in its command."""
    cmd, argn, redirect = None, 0, None
    for t in toks:
        if t[0] == "end":
            cmd, argn, redirect = None, 0, None
            continue
        if t[0] == "redirect":
            redirect = t[1]
            continue
        word, subs = t[1], t[2]
        if redirect is not None:
            role, value = "redirect %s of %s" % (redirect, cmd or "(no command)"), word
            redirect = None
        elif cmd is None and word in _SH_KEYWORDS and not subs:
            role, value = "keyword", word
        elif cmd is None and "=" in word and _SH_NAME.match(word.split("=", 1)[0]):
            name, value = word.split("=", 1)
            role = "assign %s" % name
        elif cmd is None:
            cmd, argn, role, value = word, 0, "command", word
        else:
            argn += 1
            role, value = "argument %d of %s" % (argn, cmd), word
        units.append(GuardUnit(label, prefix + role, "sh", value, None))
        for inner in subs:
            if depth >= 8:
                refusals.append("command substitutions nested deeper than this reader follows")
                continue
            _sh_units(_sh_tokens(inner, comments, refusals), label,
                      prefix + role + " / in $(): ", units, comments, refusals, depth + 1)


def hook_units(path):
    """(units, comments, refusals, called) of the pre-commit hook, read as the shell it is.

    Every word is a unit with the role its position gives it; `called` names every
    `.py` file a word of it runs -- the scripts whose syntax trees are walked next."""
    text = Path(path).read_text(encoding="utf-8")
    units, comments, refusals = [], [], []
    body = text
    if text.startswith("#!"):
        first, _nl, body = text.partition("\n")
        units.append(GuardUnit(GUARD_HOOK, "shebang", "sh", first[2:].strip(), None))
    _sh_units(_sh_tokens(body, comments, refusals), GUARD_HOOK, "", units, comments, refusals)
    called = sorted({m for u in units for m in re.findall(r"[A-Za-z0-9_.-]+\.py", u.value)})
    return units, comments, refusals, called


# The declared occurrences of the installed hook and guard: sixteen hex digits of
# sha256(file NUL role NUL kind NUL value) -> (file, role, how many times). The role
# is the one the walk derives; the value is never written here.
GUARD_DECLARED = {
    "5ea39d57873d3b54": ("pre-commit", "shebang", 1),
    "82b6e435ea6927c6": ("pre-commit", "assign DIR", 1),
    "081c2b78fdfc6afe": ("pre-commit", "assign DIR / in $(): command", 1),
    "cb5491f156b8320f": ("pre-commit", "assign DIR / in $(): argument 1 of dirname", 1),
    "bb70177ab558ae48": ("pre-commit", "keyword", 1),
    "a5d70bbd8cef4842": ("pre-commit", "command", 1),
    "f23cfd47ba665bd7": ("pre-commit", "argument 1 of command", 1),
    "45b6e79b598605f0": ("pre-commit", "argument 2 of command", 1),
    "0956d11edbb832af": ("pre-commit", "redirect > of command", 1),
    "530ae1985f1d1116": ("pre-commit", "redirect 2>& of command", 1),
    "1012766b81b4a285": ("pre-commit", "keyword", 1),
    "390a34b3ab766c42": ("pre-commit", "assign PY", 1),
    "7c022b116e5df0a1": ("pre-commit", "keyword", 1),
    "0647bb44ff2d7610": ("pre-commit", "assign PY", 1),
    "8e1419b3f1107669": ("pre-commit", "keyword", 1),
    "1d4fe723a2e47ec1": ("pre-commit", "command", 1),
    "28b681cd70a8eb36": ("pre-commit", "argument 1 of exec", 1),
    "08fb3e4b7b44c17a": ("pre-commit", "argument 2 of exec", 1),
    "493d53bc54b8b7c8": ("pre-commit", "argument 3 of exec", 1),
    "9b206dfdcf7b74c9": ("privacy-guard.py", "docstring", 1),
    "c1ea8194e1f2bd11": ("privacy-guard.py", "import name", 1),
    "e88247cca0f19f6c": ("privacy-guard.py", "import name", 1),
    "67bc78a0aa8ed505": ("privacy-guard.py", "import name", 1),
    "460ec00caa901f74": ("privacy-guard.py", "import name", 1),
    "ac16eb767560738f": ("privacy-guard.py", "import name", 1),
    "498806ba77348ddb": ("privacy-guard.py", "assign PATTERN / call os.environ.get arg0", 1),
    "1671ff5f4e7fd33c": ("privacy-guard.py", "assign RX / call re.compile arg0 / call PATTERN.encode arg0", 1),
    "e592fd51aeb67a2f": ("privacy-guard.py", "assign RX / call re.compile arg0 / call PATTERN.encode arg1", 1),
    "33a60de10f96d307": ("privacy-guard.py", "assign BINARY_EXT / element of tuple", 1),
    "2f3686c5f2539871": ("privacy-guard.py", "assign BINARY_EXT / element of tuple", 1),
    "4c35f4b6f0003f9f": ("privacy-guard.py", "assign BINARY_EXT / element of tuple", 1),
    "da24130fd22057e9": ("privacy-guard.py", "assign BINARY_EXT / element of tuple", 1),
    "9ef49b092299c294": ("privacy-guard.py", "assign BINARY_EXT / element of tuple", 1),
    "ef7b740d696fc85e": ("privacy-guard.py", "assign BINARY_EXT / element of tuple", 1),
    "dde34c1bdae8b958": ("privacy-guard.py", "assign BINARY_EXT / element of tuple", 1),
    "ed49dc324511bef7": ("privacy-guard.py", "assign BINARY_EXT / element of tuple", 1),
    "2e0b737bdac8de5f": ("privacy-guard.py", "assign ZERO", 1),
    "e3c86d0895fa1f66": ("privacy-guard.py", "def run / Return value / receiver of .stdout / call subprocess.run arg0 / binop Add left / element of list", 1),
    "18b20ef0e387163a": ("privacy-guard.py", "def hits_in / docstring", 1),
    "9c09606c426899d9": ("privacy-guard.py", "def hits_in / If test / boolop And / compare In left", 1),
    "f9f12198b6ceb8fa": ("privacy-guard.py", "def hits_in / If test / boolop And / call RX.search arg0 / call data.replace arg0", 1),
    "39f1d4c1804fa818": ("privacy-guard.py", "def hits_in / If test / boolop And / call RX.search arg0 / call data.replace arg1", 1),
    "ef54edc61b5e6990": ("privacy-guard.py", "def hits_in / If test / compare Eq right0", 1),
    "7a7cf5a37821044c": ("privacy-guard.py", "def hits_in / If body / Try body / With body / For body / If test / call RX.search arg0 / call name.encode arg0", 1),
    "4d957dbf2535469a": ("privacy-guard.py", "def hits_in / If body / Try body / With body / For body / If test / call RX.search arg0 / call name.encode arg1", 1),
    "072b86fd0e009d3d": ("privacy-guard.py", "def io_bytes / import name", 1),
    "fe638bec525eef78": ("privacy-guard.py", "def blob_bytes / Return value / call run arg0 / element of list", 1),
    "a4dacba6b9276322": ("privacy-guard.py", "def blob_bytes / Return value / call run arg0 / element of list", 1),
    "b9af3e0df0fad2f8": ("privacy-guard.py", "def batch_blobs / docstring", 1),
    "7f472d99c386d3dc": ("privacy-guard.py", "def batch_blobs / import name", 1),
    "422ffe0f5270e42f": ("privacy-guard.py", "def batch_blobs / assign p / call subprocess.Popen arg0 / element of list", 1),
    "bb720622329fa209": ("privacy-guard.py", "def batch_blobs / assign p / call subprocess.Popen arg0 / element of list", 1),
    "5b791d9d76c478d9": ("privacy-guard.py", "def batch_blobs / assign p / call subprocess.Popen arg0 / element of list", 1),
    "51e16fd1235f80d8": ("privacy-guard.py", "def batch_blobs / def feed / Try body / For body / statement / call p.stdin.write arg0 / callee <binop>.encode / receiver of .encode / binop Add right", 1),
    "730722c07892e3c2": ("privacy-guard.py", "def batch_blobs / For body / statement / Yield value / element of tuple / call parts[].decode arg0", 1),
    "91f5fc80a1bd484e": ("privacy-guard.py", "def batch_blobs / For body / statement / Yield value / element of tuple / call parts[].decode arg1", 1),
    "4cca6bd21011221a": ("privacy-guard.py", "def fail / statement / call print arg0 / binop Add left", 1),
    "fbd02ca71b61f696": ("privacy-guard.py", "def fail / For body / statement / call print arg0 / binop Add left", 1),
    "2ecc18b2f8e2b27c": ("privacy-guard.py", "def fail / statement / call print arg0", 1),
    "0356db20d2f888ba": ("privacy-guard.py", "def fail / statement / call print arg0", 1),
    "c3e51ca774e9184d": ("privacy-guard.py", "def fail / statement / call print arg0", 1),
    "800f7c6fae00bc94": ("privacy-guard.py", "def staged_mode / assign diff / call run arg0 / element of list", 1),
    "8d474cb455015e38": ("privacy-guard.py", "def staged_mode / assign diff / call run arg0 / element of list", 1),
    "e5863f3baf0bbab8": ("privacy-guard.py", "def staged_mode / assign diff / call run arg0 / element of list", 1),
    "1e9674c073423b37": ("privacy-guard.py", "def staged_mode / assign diff / call run arg0 / element of list", 1),
    "3da055ada52f7bcb": ("privacy-guard.py", "def staged_mode / assign diff / call run arg0 / element of list", 1),
    "a3615662bbc0d805": ("privacy-guard.py", "def staged_mode / assign path", 1),
    "c9a8dc78f7d4e96a": ("privacy-guard.py", "def staged_mode / For iter / call diff.split arg0", 1),
    "9cc48deb475a3f58": ("privacy-guard.py", "def staged_mode / For body / If test / call line.startswith arg0", 1),
    "7405962a09886944": ("privacy-guard.py", "def staged_mode / For body / If orelse / If test / boolop And / call line.startswith arg0", 1),
    "cd2a092baa5dfc92": ("privacy-guard.py", "def staged_mode / For body / If orelse / If test / boolop And / unaryop Not / call line.startswith arg0", 1),
    "e36b9b1fef2c65f9": ("privacy-guard.py", "def staged_mode / For body / If orelse / If body / If body / statement / call bad.append arg0 / binop Add left", 1),
    "9dc7f5e2730dc2c4": ("privacy-guard.py", "def staged_mode / For body / If orelse / If body / If body / statement / call bad.append arg0 / binop Add right / call path.decode arg0", 1),
    "8dab785c9f380c51": ("privacy-guard.py", "def staged_mode / For body / If orelse / If body / If body / statement / call bad.append arg0 / binop Add right / call path.decode arg1", 1),
    "84dfd20961658845": ("privacy-guard.py", "def staged_mode / assign raw / call run arg0 / element of list", 1),
    "f2fd55af67bace18": ("privacy-guard.py", "def staged_mode / assign raw / call run arg0 / element of list", 1),
    "71a5b6ec90d4c23d": ("privacy-guard.py", "def staged_mode / assign raw / call run arg0 / element of list", 1),
    "8eeaa51520313cc8": ("privacy-guard.py", "def staged_mode / assign raw / call run arg0 / element of list", 1),
    "47ccc4a671af11e9": ("privacy-guard.py", "def staged_mode / assign raw / call run arg0 / element of list", 1),
    "2cfd8abde4dfab00": ("privacy-guard.py", "def staged_mode / assign fields / call raw.split arg0", 1),
    "3e89cfa36538b320": ("privacy-guard.py", "def staged_mode / While body / assign meta / call fields[].decode arg0", 1),
    "fbfab37f761b542d": ("privacy-guard.py", "def staged_mode / While body / assign meta / call fields[].decode arg1", 1),
    "612ec5ff8a1b3076": ("privacy-guard.py", "def staged_mode / While body / assign name / call fields[].decode arg0", 1),
    "5cdb0cf4bdc61ee5": ("privacy-guard.py", "def staged_mode / While body / assign name / call fields[].decode arg1", 1),
    "ca2ec0bd4d2eb180": ("privacy-guard.py", "def staged_mode / While body / If test / unaryop Not / call meta.startswith arg0", 1),
    "c63448748d261601": ("privacy-guard.py", "def staged_mode / While body / If test / compare Eq left / call dst_oid.strip arg0", 1),
    "31cfd31c879cb320": ("privacy-guard.py", "def staged_mode / While body / If test / compare Eq right0", 1),
    "27c94d0546fcf60c": ("privacy-guard.py", "def staged_mode / While body / If body / statement / call bad.append arg0 / binop Mod left", 1),
    "2faf8dbdb1393965": ("privacy-guard.py", "def staged_mode / While body / If orelse / If body / statement / call bad.append arg0 / binop Mod left", 1),
    "dd5dff266235ad96": ("privacy-guard.py", "def staged_mode / If body / statement / call fail arg0", 1),
    "f8cba847d80b8625": ("privacy-guard.py", "def commit_range / If test / compare Eq left / call remote_sha.strip arg0", 1),
    "81a8e15b0827f803": ("privacy-guard.py", "def commit_range / If test / compare Eq right0", 1),
    "898de5bb0a1f49ae": ("privacy-guard.py", "def commit_range / If body / Return value / element of list", 1),
    "baf4b242154d5744": ("privacy-guard.py", "def commit_range / If body / Return value / element of list", 1),
    "d271c2654925e20e": ("privacy-guard.py", "def commit_range / Return value / element of list / binop Mod left", 1),
    "ea13cdc8326bedcb": ("privacy-guard.py", "def outgoing_mode / For iter / call <call>.split arg0", 1),
    "a84fa7c177cf6bd5": ("privacy-guard.py", "def outgoing_mode / For body / If test / compare Eq left / call local_sha.strip arg0", 1),
    "cbf46d7ebe1a81b9": ("privacy-guard.py", "def outgoing_mode / For body / If test / compare Eq right0", 1),
    "e0c25e7ee859d29e": ("privacy-guard.py", "def outgoing_mode / For body / assign commits / callee <call>.split / receiver of .split / callee <call>.decode / receiver of .decode / call run arg0 / binop Add left / element of list", 1),
    "cd090aef7544d0bc": ("privacy-guard.py", "def outgoing_mode / For body / For body / assign meta / call run arg0 / element of list", 1),
    "9e26dedc513cf9f4": ("privacy-guard.py", "def outgoing_mode / For body / For body / assign meta / call run arg0 / element of list", 1),
    "177b3547b7cca21e": ("privacy-guard.py", "def outgoing_mode / For body / For body / assign meta / call run arg0 / element of list", 1),
    "e7a4d42d9c749fed": ("privacy-guard.py", "def outgoing_mode / For body / For body / If body / statement / call bad.append arg0 / binop Mod left", 1),
    "d369aee0a7a060ed": ("privacy-guard.py", "def outgoing_mode / For body / assign objs / callee <call>.decode / receiver of .decode / call run arg0 / binop Add left / element of list", 1),
    "1d2fb96b1c31aca0": ("privacy-guard.py", "def outgoing_mode / For body / assign objs / callee <call>.decode / receiver of .decode / call run arg0 / binop Add left / element of list", 1),
    "e44aaefeb1436918": ("privacy-guard.py", "def outgoing_mode / For body / assign objs / call <call>.decode arg0", 1),
    "36fe21d5ca84a0c7": ("privacy-guard.py", "def outgoing_mode / For body / assign objs / call <call>.decode arg1", 1),
    "4af19207830538e9": ("privacy-guard.py", "def outgoing_mode / For body / For iter / call objs.split arg0", 1),
    "1ee6769da22527ef": ("privacy-guard.py", "def outgoing_mode / For body / For body / assign bits / call o.split arg0", 1),
    "d8ef2bb3d680f03b": ("privacy-guard.py", "def outgoing_mode / For body / If body / assign check_in / binop Add left / callee <constant>.join / receiver of .join", 1),
    "6e0a248dda50e51f": ("privacy-guard.py", "def outgoing_mode / For body / If body / assign check_in / binop Add right", 1),
    "7f5935f476a9c57f": ("privacy-guard.py", "def outgoing_mode / For body / If body / assign info / callee <call>.stdout.decode / receiver of .decode / receiver of .stdout / call subprocess.run arg0 / element of list", 1),
    "f6040155626f2127": ("privacy-guard.py", "def outgoing_mode / For body / If body / assign info / callee <call>.stdout.decode / receiver of .decode / receiver of .stdout / call subprocess.run arg0 / element of list", 1),
    "cc54d5590eee64cb": ("privacy-guard.py", "def outgoing_mode / For body / If body / assign info / callee <call>.stdout.decode / receiver of .decode / receiver of .stdout / call subprocess.run arg0 / element of list", 1),
    "23614e28b130b9e0": ("privacy-guard.py", "def outgoing_mode / For body / If body / assign info / call <call>.stdout.decode arg0", 1),
    "46c95e34d23387f0": ("privacy-guard.py", "def outgoing_mode / For body / If body / assign info / call <call>.stdout.decode arg1", 1),
    "1a7c4fa7cabb2904": ("privacy-guard.py", "def outgoing_mode / For body / If body / For iter / call info.split arg0", 1),
    "aa45e84ff1ef5460": ("privacy-guard.py", "def outgoing_mode / For body / If body / For body / assign (kind,size) / call types.get arg1 / element of tuple", 1),
    "841deaad0fe7af82": ("privacy-guard.py", "def outgoing_mode / For body / If body / For body / If test / compare NotEq right0", 1),
    "6b0798f0049d82a2": ("privacy-guard.py", "def outgoing_mode / For body / If body / For body / If test / call RX.search arg0 / call name.encode arg0", 1),
    "4a11a5faad4a6d2c": ("privacy-guard.py", "def outgoing_mode / For body / If body / For body / If test / call RX.search arg0 / call name.encode arg1", 1),
    "a54101b58fbb4f37": ("privacy-guard.py", "def outgoing_mode / For body / If body / For body / If body / statement / call bad.append arg0 / binop Mod left", 1),
    "5c90610755a2034b": ("privacy-guard.py", "def outgoing_mode / For body / If body / For body / If body / statement / call bad.append arg0 / binop Mod left", 1),
    "dba80d2bfc237ca0": ("privacy-guard.py", "def outgoing_mode / For body / If body / For body / If body / statement / call bad.append arg0 / binop Mod left", 1),
    "b33d5a5d5e1a8c7a": ("privacy-guard.py", "def outgoing_mode / For body / If body / For body / If body / statement / call bad.append arg0 / binop Mod right / element of tuple / call where.get arg1", 1),
    "df3b42cc4e2d5c29": ("privacy-guard.py", "def outgoing_mode / If body / statement / call fail arg0", 1),
    "99f4a240a9be2ce6": ("privacy-guard.py", "def outgoing_mode / If body / statement / call print arg0 / binop Mod left", 1),
    "7bcfbefd2550b2a6": ("privacy-guard.py", "def main / assign mode / IfExp orelse", 1),
    "cd6a4da6b73e67c3": ("privacy-guard.py", "def main / If test / compare Eq right0", 1),
    "521f58bb44bb3d0e": ("privacy-guard.py", "If test / compare Eq right0", 1),
}

# The declared shape of every Python module the census walks for the guard (round 13,
# R12-H1): the module's file, and one digest per top-level statement in order -- 16 hex
# digits of the sha256 of the statement's shape (_shape: every text constant reduced to
# a placeholder, every other constant kept). No value and no line of the guard is
# written here; a change to the guard's code moves a digest and the census refuses.
GUARD_SHAPE = {
    "privacy-guard.py": (  # 23 top-level statement(s)
        "c96ba478b3fe2347",
        "b6a330acd0a74b79",
        "09eaf62eaa8d68c0",
        "af12a0120935a390",
        "4edc1f5835d8bae7",
        "1f072fe1d4829cdd",
        "ea1a6755c2f03383",
        "1d0dbcf5cb65ce42",
        "a6ba25c6038c7c8b",
        "3c3b10f9354ce85c",
        "43bceb3dfc6dfdfb",
        "0fc8fbadf8560723",
        "526cae3073a792e7",
        "72b3684d6eaf7bfa",
        "48cc008bb84895e2",
        "ce271c23709c032f",
        "bf7f63e36696c1c0",
        "86f144f66c11d4b8",
        "7dded0ca41b359cc",
        "3e86938ddbeb23bf",
        "5c92214a729a72d9",
        "0abd26c35da986e7",
        "5327fd554608f8a1",
    ),
}


def guard_inventory(hooks, declared=None, shapes=None):
    """Everything the pre-commit hook and the scripts it runs hold, matched OCCURRENCE by
    occurrence against the declarations.

    A dict: units (every GuardUnit), patterns (the units no declaration accounts for),
    absent (declared occurrences that were not found), overrides, texts, refusals and
    scripts (how many were walked). Refuses when the hook, or a script it runs, is not
    there to be read."""
    declared = GUARD_DECLARED if declared is None else declared
    hooks = Path(hooks)
    pre = hooks / GUARD_HOOK
    if not pre.is_file():
        raise Refusal("the repository has no pre-commit hook; the guard's patterns are a "
                      "needle source and cannot be read")
    units, texts, refusals, called = hook_units(pre)
    if not called:
        raise Refusal("the pre-commit hook runs no script this census can read")
    overrides, seen = [], set()
    for name in called:
        script = hooks / name
        if not script.is_file():
            raise Refusal("the pre-commit hook runs a script that is not beside it")
        u, o, t, r = guard_units(script, hooks, seen, shapes)
        units += u
        overrides += o
        texts += t
        refusals += r
    left = {k: v[2] for k, v in declared.items()}
    patterns = []
    for u in units:
        k = u.key()
        entry = declared.get(k)
        if entry and left[k] > 0 and entry[0] == u.file and entry[1] == u.role:
            left[k] -= 1
        else:
            patterns.append(u)
    return {"units": units, "patterns": patterns,
            "absent": sum(n for n in left.values() if n > 0), "overrides": overrides,
            "texts": texts, "refusals": refusals, "scripts": len(called)}


def guard_judgement(inv, expected=None):
    """None when an inventory holds exactly `expected` (default GUARD_PATTERNS) undeclared
    occurrences, every declared occurrence and nothing refused; otherwise why not."""
    expected = GUARD_PATTERNS if expected is None else expected
    if inv["refusals"]:
        return ("the hook or the guard computes text this census cannot enumerate, or the "
                "guard's code is not its declared shape (%s)"
                % ", ".join(sorted(set(inv["refusals"]))))
    if len(inv["patterns"]) != expected or inv["absent"]:
        return ("the hook and the guard hold %d undeclared occurrence(s), and %d declared "
                "occurrence(s) were not found; this census declares exactly %d pattern(s) "
                "and every declared occurrence: a pattern was added or deleted, or a "
                "declared occurrence moved, changed or went"
                % (len(inv["patterns"]), inv["absent"], expected))
    return None


def _guard(ns, repo):
    inv = guard_inventory(_hooks_dir(repo))
    problem = guard_judgement(inv)
    if problem:
        raise Refusal(problem + ". Nothing has been judged.")
    ns.read["guard-script"] += inv["scripts"]
    ns.read["guard-unit"] += len(inv["units"])
    ns.read["guard-hook-unit"] += sum(1 for u in inv["units"] if u.file == GUARD_HOOK)
    ns.read["guard-declared"] += len(inv["units"]) - len(inv["patterns"])
    for u in inv["patterns"]:
        ns.read["guard-pattern"] += 1
        text = u.value.decode("latin-1") if isinstance(u.value, bytes) else u.value
        got = [text] if u.kind == "import" else expand(text)
        if got is None:
            ns.nonfinite["guard"] += 1
            continue
        for lit in got:
            ns.add(lit, "guard:pattern")
    for key in inv["overrides"]:
        override = os.environ.get(key)
        if override:
            ns.read["guard-override"] += 1
            got = expand(override)
            if got is None:
                ns.nonfinite["guard"] += 1
                continue
            for lit in got:
                ns.add(lit, "guard:pattern")
    for text in inv["texts"]:
        for group in _ALT.findall(text):
            ns.read["guard-alternation"] += 1
            for lit in _alternatives(group):
                ns.add(lit, "guard-held:alternation")


def derive(seat=None, repo=None, sidecar=None):
    """The needle set of this seat. Refuses rather than returning a partial set."""
    repo = Path(repo or ROOT)
    seat = Path(seat or SEAT_DEFAULT)
    schema = _sibling("train_pin_schema")
    common = Path(_git(repo, ["rev-parse", "--path-format=absolute",
                              "--git-common-dir"]).strip())
    project = common.parent.name if common.name == ".git" else ""
    ns = NeedleSet(project)
    ns.sanctioned = {s.lower() for s in getattr(schema, "SANCTIONED", ())}

    # 1. every string leaf of the seat configuration, and what is inside each
    if not seat.is_file():
        raise Refusal("the seat configuration file is not where this census reads it; "
                      "without it the needle set would silently lose its first source")
    conf = json.loads(seat.read_bytes().decode("utf-8"))
    for path, value in _walk_strings(conf, ""):
        ns.read["seat-leaf"] += 1
        source = "seat:" + path
        if re.fullmatch(r"[a-z]+", value.strip()):
            ns.spelled_keys.add(source)
        ns.add(value, source)
        for kind, text in _parts(value):
            ns.add(text, "seat-part:%s:%s" % (path, kind))
    if not ns.read["seat-leaf"]:
        raise Refusal("the seat configuration holds no string leaf")

    # 2. the pre-commit guard
    _guard(ns, repo)

    # 3. this seat's user-path forms
    users = []
    for raw in (os.environ.get("USERNAME"), os.environ.get("USER"),
                os.path.basename((os.environ.get("USERPROFILE") or "").rstrip("\\/")),
                os.path.basename((os.environ.get("HOME") or "").rstrip("\\/")),
                os.path.basename(os.path.expanduser("~").rstrip("\\/"))):
        if raw and raw.lower() not in [u.lower() for u in users]:
            users.append(raw)
    drives = []
    for raw in (os.environ.get("SystemDrive"), str(ROOT)[:2], str(repo)[:2]):
        if raw and re.fullmatch(r"[A-Za-z]:", raw) and raw.upper() not in drives:
            drives.append(raw.upper())
    root = "Users"
    for user in users:
        for sep in ("\\", "/"):
            for drive in drives:
                ns.add(sep.join((drive, root, user)), "user-path")
            ns.add(sep + sep.join((root, user)), "user-path")
        for drive in drives:
            ns.add("/" + "/".join((drive[0].lower(), root, user)), "user-path")

    # 4. this seat's machine name
    for raw in (os.environ.get("COMPUTERNAME"), socket.gethostname()):
        if raw:
            ns.add(raw, "machine")
            ns.add(raw.split(".")[0], "machine")

    # 5. the repository's commit identity
    for key in ("user.name", "user.email"):
        value = _git(repo, ["config", "--get", key], check=False).strip()
        if value:
            ns.add(value, "identity:" + key)
            if key == "user.email" and "@" in value:
                ns.add(value.split("@", 1)[0], "identity:user.email-local")

    # 6. the round-9 sidecar's typed classes
    if not sidecar:
        raise Refusal("no sidecar was named (--sidecar or SCR_PIN_NEEDLES); every scan of "
                      "a round must use the same needle set")
    doc = json.loads(Path(sidecar).read_bytes().decode("utf-8"))
    for klass, patterns in doc.get("fixed") or []:
        for pat in patterns:
            ns.read["sidecar-pattern"] += 1
            got = expand("(?i)" + pat)
            if got is None:
                ns.nonfinite["sidecar"] += 1
                continue
            bare = pat[4:] if pat.startswith("(?i)") else pat
            bounds = (bare.startswith("\\b"),
                      bare.endswith("\\b") and not bare.endswith("\\\\b"))
            for lit in got:
                ns.add(lit, "sidecar:" + klass, bounds)

    ns.finish()
    fams = {NeedleSet.family(s) for i in ns.items for s in i["sources"]}
    for required in ("seat", "guard", "user-path"):
        if required not in fams:
            raise Refusal("the %s source contributed no needle; the set is not the one this "
                          "census claims" % required)
    return ns


# ---------------------------------------------------------------------------
# Forms, the byte-pattern table, and the scanner.

def forms_of(lit):
    cands = [
        ("raw", lit),
        ("url", urllib.parse.quote(lit, safe="")),
        ("url", urllib.parse.quote(lit)),
        ("url", urllib.parse.quote_plus(lit)),
        ("url", urllib.parse.quote(urllib.parse.quote(lit, safe=""), safe="")),
        ("escaped", lit.replace("\\", "\\\\")),
        ("escaped", lit.replace("\\", "\\\\\\\\")),
        ("escaped", json.dumps(lit)[1:-1]),
        ("escaped", lit.replace("/", "\\/")),
        ("escaped", json.dumps(lit)[1:-1].replace("/", "\\/")),
        ("escaped", lit.encode("unicode_escape").decode("ascii")),
    ]
    seen, out = set(), []
    for kind, text in cands:
        if text.lower() not in seen:
            seen.add(text.lower())
            out.append((kind, text))
    return out


class Table:
    def __init__(self, items):
        self.items = items
        pats = {}
        for idx, item in enumerate(items):
            for kind, text in forms_of(item["literal"]):
                for enc in ("utf-8", "utf-16-le"):
                    variants = {text.lower().encode(enc)}
                    if not text.isascii():
                        variants.add(text.encode(enc))
                    for key in variants:
                        pats.setdefault(key, []).append((idx, kind, enc, text.encode(enc)))
        self.patterns = [(k, b"\x00" in k, v) for k, v in sorted(pats.items())]
        self.maxlen = max([len(k) for k in pats] or [1])


class Tally:
    def __init__(self):
        self.findings = collections.OrderedDict()     # target -> Counter(label)
        self.forms = collections.Counter()            # (kind, enc) of the findings
        self.declared = collections.Counter()         # class -> occurrences
        self.declared_in = collections.defaultdict(set)
        self.targets = 0
        self.bytes = 0

    def finding(self, target, label, kind, enc):
        self.findings.setdefault(target, collections.Counter())[label] += 1
        self.forms[(kind, enc)] += 1

    def declare(self, klass, target):
        self.declared[klass] += 1
        self.declared_in[klass].add(target)

    @property
    def total(self):
        return sum(sum(c.values()) for c in self.findings.values())


def _identity_header(buf, i):
    end = buf.find(b"\n\n")
    if end != -1 and i >= end:
        return False
    start = buf.rfind(b"\n", 0, i) + 1
    return buf.startswith(b"author ", start) or buf.startswith(b"committer ", start)


_WORD = frozenset(b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_")
_PAD = 2                                     # context bytes kept on each side of a hit


def _word_at(buf, i, enc):
    """Is there a word character at byte i (a UTF-16LE code unit starting at i)?"""
    if i < 0 or i >= len(buf):
        return False
    if enc == "utf-16-le":
        return i + 1 < len(buf) and buf[i + 1] == 0 and buf[i] in _WORD
    return buf[i] in _WORD


def _embedded(buf, i, n, enc, bounds):
    step = 2 if enc == "utf-16-le" else 1
    return ((bounds[0] and _word_at(buf, i - step, enc))
            or (bounds[1] and _word_at(buf, i + n, enc)))


def scan_chunks(chunks, table, tally, target, commit=False):
    """Every occurrence of every pattern, counted ONCE, across chunk boundaries.

    A round counts the occurrences that start before `cut`; they end at least _PAD
    bytes before the end of the buffer, so their right-hand context is present. The
    carry keeps _PAD bytes before `cut` as left-hand context and the next round
    counts only from `skip`, so an occurrence is neither lost nor counted twice."""
    keep = table.maxlen - 1 + _PAD
    carry, skip = b"", 0
    it = iter(chunks)
    cur = next(it, None)
    tally.targets += 1
    while cur is not None:
        nxt = next(it, None)
        tally.bytes += len(cur)
        buf = carry + cur
        low = buf.lower()
        has_nul = b"\x00" in buf
        cut = len(buf) if nxt is None else max(skip, len(buf) - keep)
        for pat, needs_nul, metas in table.patterns:
            if needs_nul and not has_nul:
                continue
            i = low.find(pat, skip)
            while 0 <= i < cut:
                for idx, kind, enc, spelled in metas:
                    item = table.items[idx]
                    declared = classify(buf, i, len(pat), item, enc, spelled, commit)
                    if declared:
                        tally.declare(declared, target)
                    else:
                        tally.finding(target, item["label"], kind, enc)
                i = low.find(pat, i + 1)
        start = max(0, cut - _PAD)
        carry, skip = buf[start:], cut - start
        cur = nxt


def classify(buf, i, n, item, enc, spelled, commit=False):
    """The declared class an occurrence belongs to, or None when it is a finding."""
    if "as-spelled" in item["rules"] and buf[i:i + n] != spelled:
        return "AS-SPELLED"
    if any(item["bounds"]) and _embedded(buf, i, n, enc, item["bounds"]):
        return "EMBEDDED"
    if "identity" in item["rules"] and commit and _identity_header(buf, i):
        return "COMMIT-IDENTITY"
    return None


def finding_spans(data, table):
    """[(start, end, item)] for every FINDING occurrence in `data` (bytes, one piece)."""
    low = data.lower()
    has_nul = b"\x00" in data
    spans = []
    for pat, needs_nul, metas in table.patterns:
        if needs_nul and not has_nul:
            continue
        i = low.find(pat)
        while i != -1:
            for idx, _kind, enc, spelled in metas:
                item = table.items[idx]
                if not classify(data, i, len(pat), item, enc, spelled):
                    spans.append((i, i + len(pat), item))
            i = low.find(pat, i + 1)
    return sorted(spans, key=lambda s: (s[0], -s[1]))


def text_hits(text, table):
    t = Tally()
    scan_chunks([text.encode("utf-8")], table, t, "text")
    return t.total


def _zip_members(data, table, tally, target):
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            for n, info in enumerate(z.infolist()):
                scan_chunks([info.filename.encode("utf-8")], table, tally,
                            "%s!member-%d-name" % (target, n))
                scan_chunks([z.read(info)], table, tally, "%s!member-%d" % (target, n))
    except (zipfile.BadZipFile, RuntimeError, NotImplementedError, OSError):
        tally.finding(target, "an archive this census could not open", "raw", "utf-8")


def scan_stream(chunks, table, tally, target):
    it = iter(chunks)
    first = next(it, b"")
    if first.startswith(b"PK\x03\x04"):
        data = first + b"".join(it)
        scan_chunks([data], table, tally, target)
        _zip_members(data, table, tally, target)
    else:
        scan_chunks(itertools.chain([first], it), table, tally, target)


def _file_chunks(path):
    with open(path, "rb") as f:
        while True:
            b = f.read(CHUNK)
            if not b:
                return
            yield b


def _show(name, table):
    return name if not text_hits(name, table) else "<a name withheld: it holds a needle>"


def _report(tally, table, out, what):
    for target, labels in tally.findings.items():
        out.append("FINDING %s : %d occurrence(s) -- %s" % (
            _show(target, table), sum(labels.values()),
            ", ".join("%s x%d" % (l, n) for l, n in sorted(labels.items()))))
    for (kind, enc), n in sorted(tally.forms.items()):
        out.append("  in form %s/%s: %d" % (kind, enc, n))
    for klass in ("AS-SPELLED", "COMMIT-IDENTITY", "EMBEDDED"):
        out.append("DECLARED %-15s %d occurrence(s) in %d %s" % (
            klass, tally.declared[klass], len(tally.declared_in[klass]), what))
    out.append("NEEDLE FINDINGS %d across %d target(s), %d byte(s) read"
               % (tally.total, tally.targets, tally.bytes))


# ---------------------------------------------------------------------------
# Object mode: every commit, tree and blob of the landing range, whole.

def _read_exact(stream, n):
    parts, left = [], n
    while left:
        b = stream.read(min(CHUNK, left))
        if not b:
            raise Refusal("git cat-file ended inside an object")
        parts.append(b)
        left -= len(b)
    return b"".join(parts)


def _pipe_chunks(stream, n):
    left = n
    while left:
        b = stream.read(min(CHUNK, left))
        if not b:
            raise Refusal("git cat-file ended inside an object")
        left -= len(b)
        yield b


def scan_objects(repo, tips, excludes, table, tally):
    listing = _git(repo, ["rev-list", "--objects"] + list(tips) + ["--not"] + list(excludes))
    ids = [line.split(" ", 1)[0] for line in listing.splitlines() if line.strip()]
    if not ids:
        raise Refusal("the range reaches no object; a census over nothing means nothing "
                      "(#441)")
    stats = collections.Counter()
    largest = 0
    p = subprocess.Popen(git_argv(repo, ["cat-file", "--batch"]),
                         stdin=subprocess.PIPE, stdout=subprocess.PIPE, env=git_env())
    try:
        for sha in ids:
            p.stdin.write(sha.encode("ascii") + b"\n")
            p.stdin.flush()
            head = p.stdout.readline().split()
            if len(head) != 3 or head[1] == b"missing":
                raise Refusal("git cat-file answered no object for an id of the range")
            kind, size = head[1].decode("ascii"), int(head[2])
            stats[kind] += 1
            stats["bytes"] += size
            largest = max(largest, size)
            target = "%s %s" % (kind, sha[:12])
            if kind == "blob":
                scan_stream(_pipe_chunks(p.stdout, size), table, tally, target)
            else:
                scan_chunks([_read_exact(p.stdout, size)], table, tally, target,
                            commit=(kind == "commit"))
            if p.stdout.read(1) != b"\n":
                raise Refusal("git cat-file's framing was not what this census reads")
    finally:
        p.stdin.close()
        p.stdout.close()
        p.wait()
    return stats, largest


def object_census(repo, tips, excludes, ns, table=None):
    table = table or Table(ns.items)
    tally = Tally()
    stats, largest = scan_objects(repo, tips, excludes, table, tally)
    out = [ns.line(),
           "OBJECTS %s --not %s: %d commit(s), %d tree(s), %d blob(s), %d tag(s); %d byte(s), "
           "the largest %d -- every byte of every object read, no size cap" % (
               " ".join(t[:12] for t in tips), " ".join(e[:12] for e in excludes),
               stats["commit"], stats["tree"], stats["blob"], stats["tag"], stats["bytes"],
               largest),
           "  (a commit object is its headers -- tree, parent, author, committer -- and its "
           "message; a tree object holds every file name)"]
    _report(tally, table, out, "object(s)")
    out.append("TOTAL %d" % tally.total)
    return out, tally


# ---------------------------------------------------------------------------
# A4: every rendered field of a summary, before it enters a pin.

def field_findings(doc, table):
    found = []

    def walk(node, where):
        if isinstance(node, dict):
            for n, (k, v) in enumerate(node.items()):
                if text_hits(str(k), table):
                    found.append(where + "{key %d}" % n)
                    walk(v, where + "{key %d}" % n)
                else:
                    walk(v, "%s.%s" % (where, k))
        elif isinstance(node, list):
            for n, v in enumerate(node):
                walk(v, "%s[%d]" % (where, n))
        else:
            text = node if isinstance(node, str) else json.dumps(node)
            if text_hits(text, table):
                found.append(where)

    walk(doc, "$")
    return found


# ---------------------------------------------------------------------------
# A2: provenance.

def _files_under(root):
    out = []
    for dirpath, _dirs, names in os.walk(root):
        for name in names:
            full = os.path.join(dirpath, name)
            out.append(os.path.relpath(full, root).replace("\\", "/"))
    return sorted(out)


def _sha(data):
    return hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------------------
# The snapshot wrapper's gated copy (R11-L1, round 12).
#
# The snapshot wrapper (scripts/cc-snapshot-wrapper.sh) answers the train's listing
# verb, so the pin carries it as a TRACKED-COPY. Its repository copy sits under an
# ignored directory and holds infra detail no tracked file holds -- the container id
# and the host's log file -- and the snapshot host's address, a shape the shape census
# lists. By the public-repository convention, a file that discloses such detail is not
# tracked as it is; what is tracked instead is its GATED copy (WRAPPER_GATED): the
# repository copy with exactly those values replaced by a token and every other byte
# unchanged. The gate is wrapper_gate, and each replacement must match an exact number
# of times, so a wrapper that changed shape refuses rather than gating something no one
# reviewed. The census proves the relation -- gate(repository copy) == the tracked copy,
# byte for byte -- whenever the repository copy is readable, and counts a provenance
# problem when it is not, when the pin carries no gated copy, or when the copy's entry
# does not name what it was gated from. The copy INSTALLED on the snapshot host is not
# readable from this seat; that stays a recorded residual.

WRAPPER_GATED = "tools/train_pin/cc-snapshot-wrapper.gated.sh"
WRAPPER_SOURCE = "scripts/cc-snapshot-wrapper.sh"
WRAPPER_GATES = (
    ("the container id", re.compile(r"(?m)^CTID=[0-9]+$"), "CTID=<container id>", 1),
    ("a container named in a comment", re.compile(r"\bCT [0-9]+\b"), "CT <container id>", 2),
    ("the host's log file", re.compile(r'(?m)^LOG="[^"\n]*"$'), 'LOG="<log file>"', 1),
    ("the snapshot host's address", re.compile(r"(?<![0-9.])(?:[0-9]{1,3}\.){3}[0-9]{1,3}"
                                               r"(?![0-9.])"), "<snapshot host>", 3),
)


def wrapper_gate(data):
    """The gated copy of the snapshot wrapper's repository copy: bytes -> bytes.

    Refuses when any replacement matches other than its exact count."""
    text = data.decode("utf-8")
    for what, rx, token, want in WRAPPER_GATES:
        text, got = rx.subn(token, text)
        if got != want:
            raise Refusal("the snapshot wrapper holds %d occurrence(s) of %s and its gate "
                          "replaces exactly %d: the wrapper changed shape, and its gated copy "
                          "must be re-derived and reviewed" % (got, what, want))
    return text.encode("utf-8")


def wrapper_source(repo, override=None):
    """The wrapper's repository copy: `override`, else this checkout's, else the main
    checkout's (its directory is ignored, so a linked worktree does not hold it); None
    when none is readable."""
    if override:
        return Path(override) if Path(override).is_file() else None
    common = Path(_git(repo, ["rev-parse", "--path-format=absolute", "--git-common-dir"])
                  .strip())
    for base in (Path(repo), common.parent):
        p = base / WRAPPER_SOURCE
        if p.is_file():
            return p
    return None


def wrapper_problems(entries, pin, repo, wrapper=None, required=False):
    """Provenance problems of the pin's gated wrapper copy (R11-L1).

    `required`: the pin must carry exactly one -- true of the release-train pin the
    census is run on, and of the self-test's copies of it; a synthetic pin a control
    builds carries none and is not asked for one."""
    pin = Path(pin)
    found = [e for e in entries if isinstance(e, dict) and e.get("path") == WRAPPER_GATED]
    if not found and not required:
        return []
    if len(found) != 1:
        return ["the pin carries %d gated copies of the snapshot wrapper; exactly one is "
                "required" % len(found)]
    e = found[0]
    if e.get("class") != "TRACKED-COPY" or e.get("gated_from") != WRAPPER_SOURCE:
        return ["%s: the snapshot wrapper's copy must be a TRACKED-COPY naming the repository "
                "copy it was gated from" % e.get("file")]
    path = pin / str(e.get("file"))
    if not path.is_file():
        return []
    src = wrapper_source(repo, wrapper)
    if src is None:
        return ["%s: the repository copy it is gated from is not readable here, so the gate "
                "cannot be proven" % e.get("file")]
    try:
        if _sha(wrapper_gate(src.read_bytes())) != _sha(path.read_bytes()):
            return ["%s: not the gate of the repository copy it names" % e.get("file")]
    except Refusal as r:
        return ["%s: %s" % (e.get("file"), r)]
    return []


def provenance(pin, repo, tip, scratch=None, wrapper=None, require_wrapper=False):
    """(problems, {file: class}, per-class counts and bytes). Never raises on a bad pin.

    R10-H4: a GENERATED file is re-derived from the pin commit's objects -- its
    recipe is checked by `recipe_problem` before it runs -- and the one derivation
    (the ignore proof) needs a scratch directory. R10-H3: every read goes through
    the door, replacement objects off."""
    pin = Path(pin)
    problems, classes = [], {}
    size = collections.Counter()
    count = collections.Counter()
    mpath = pin / MANIFEST
    if not mpath.is_file():
        return ["the pin has no %s: no file can be classified" % MANIFEST], {}, count, size
    try:
        doc = json.loads(mpath.read_bytes().decode("utf-8"))
    except ValueError:
        return ["%s is not JSON" % MANIFEST], {}, count, size
    tip_sha = _git(repo, ["rev-parse", "--verify", tip + "^{commit}"]).strip()
    if doc.get("tip") != tip_sha:
        problems.append("the manifest names another pin commit")
    entries = doc.get("files")
    if not isinstance(entries, list):
        return problems + ["the manifest has no file list"], {}, count, size
    on_disk = _files_under(pin)
    seen = collections.Counter(e.get("file") for e in entries if isinstance(e, dict))
    for name, n in sorted(seen.items(), key=lambda kv: str(kv[0])):
        if n > 1:
            problems.append("%s is classified %d times; a file is exactly one class" % (name, n))
    for rel in on_disk:
        if rel not in seen:
            problems.append("%s is in no class" % rel)
    for name in seen:
        if name not in on_disk:
            problems.append("the manifest classifies %s, which the pin does not hold" % name)
    for e in entries:
        if not isinstance(e, dict):
            problems.append("a manifest entry is not an object")
            continue
        name, cls = e.get("file"), e.get("class")
        if cls not in CLASSES:
            problems.append("%s: class %r is none of %s" % (name, cls, ", ".join(CLASSES)))
            continue
        classes[name] = cls
        path = pin / str(name)
        if not path.is_file():
            continue
        data = path.read_bytes()
        count[cls] += 1
        size[cls] += len(data)
        if cls == "TRACKED-COPY":
            blob = subprocess.run(git_argv(repo, ["cat-file", "blob",
                                                  "%s:%s" % (tip_sha, e.get("path"))]),
                                  capture_output=True, env=git_env())
            if blob.returncode != 0:
                problems.append("%s: its path is not tracked at the pin commit" % name)
            elif _sha(blob.stdout) != _sha(data):
                problems.append("%s: not byte-equal to its tracked blob at the pin commit" % name)
        elif cls == "GENERATED":
            producer = e.get("producer") or ""
            pblob = subprocess.run(git_argv(repo, ["cat-file", "blob",
                                                   "%s:%s" % (tip_sha, producer)]),
                                   capture_output=True, env=git_env())
            local = ROOT / producer
            if not producer or pblob.returncode != 0:
                problems.append("%s: its producer is not a tracked file at the pin commit" % name)
            elif not local.is_file() or _sha(local.read_bytes()) != _sha(pblob.stdout):
                problems.append("%s: its producer differs from its tracked blob" % name)
            if not e.get("inputs"):
                problems.append("%s: its inputs are not named" % name)
            if not e.get("run_log") or not (pin / str(e.get("run_log"))).is_file():
                problems.append("%s: its run log is not in the pin" % name)
            try:
                if _sha(run_recipe(repo, e.get("recipe"), tip_sha, e.get("inputs"),
                                   scratch)) != _sha(data):
                    problems.append("%s: not what its recipe produces" % name)
            except Refusal as r:
                problems.append("%s: %s" % (name, r))
    problems += wrapper_problems(entries, pin, repo, wrapper, require_wrapper)
    return problems, classes, count, size


# ---------------------------------------------------------------------------
# The pin census.

def files_census(pin, repo, tip, ns, sidecar, scratch, table=None, wrapper=None,
                 require_wrapper=False):
    """(lines, counts, shape report): provenance, scope, needles, fields and shapes over
    EVERY file of the pin, whatever its provenance class (R10-H1).

    Provenance says where a file came from and that it equals that source. It does
    not say what the bytes do not contain, so a TRACKED-COPY and a GENERATED file
    are needle-scanned and shape-scanned exactly as a TYPED one is, and a hit in
    any of them counts."""
    pin = Path(pin)
    table = table or Table(ns.items)
    out = []
    problems, classes, count, size = provenance(pin, repo, tip, scratch, wrapper,
                                                require_wrapper)
    out.append("PROVENANCE %d file(s): %s; %d problem(s)" % (
        len(_files_under(pin)),
        ", ".join("%s %d (%d bytes)" % (c, count[c], size[c]) for c in CLASSES),
        len(problems)))
    out += ["  PROBLEM %s" % p for p in problems]
    tip_sha = _git(repo, ["rev-parse", "--verify", tip + "^{commit}"]).strip()
    try:
        scope = scope_problems(repo, tip_sha, scratch)
    except Refusal as r:
        scope = ["the scope could not be derived from the pin commit's objects: %s" % r]
    out.append("SCOPE %d problem(s) -- from the pin commit's objects alone: the train and its "
               "seat file are neither tracked nor unignored (%s)" % (
                   len(scope), ", ".join(SCOPE_PATHS)))
    out += ["  PROBLEM %s" % p for p in scope]
    tally = Tally()
    for rel in _files_under(pin):
        if text_hits(rel, table):
            tally.finding("<a file name withheld: it holds a needle>", "file name", "raw",
                          "utf-8")
        scan_stream(_file_chunks(pin / rel), table, tally, rel)
    _report(tally, table, out, "file(s)")
    fields = 0
    for rel in _files_under(pin):
        if rel.startswith(("summary-", "run1-summary-")) and rel.endswith(".json"):
            found = field_findings(json.loads((pin / rel).read_bytes().decode("utf-8")), table)
            fields += len(found)
            out += ["FIELD FINDING %s %s" % (rel, w) for w in found]
    out.append("FIELD FINDINGS %d (every rendered field of every summary-*.json, the "
               "first harness run's run1-summary-*.json included)" % fields)
    shape = _sibling("train_pin_scan")
    needles = shape.load_needles(str(sidecar), str(pin))
    # The one digest this census adds to the shape census's own derived rule
    # (a 64-hex run equal to the sha256 of a file of the pin): its own needle
    # list digest, which the NEEDLES line prints. Nothing else is declared here.
    own = {ns.digest(): "the sha256 of this seat's sorted needle list, as the NEEDLES "
                        "line prints it"}
    result = shape.scan(str(pin), needles, str(repo), digests=own)
    by = collections.Counter()
    for _klass, where in result[1]:
        for f, n in where:
            by[classes.get(shape.file_of(f), "UNCLASSIFIED")] += n
    shaped = sum(by.values())
    out.append("SHAPE CENSUS over EVERY file, whatever its class (train_pin_scan.py): %d "
               "hit(s) -- %s" % (shaped, ", ".join("%s %d" % (c, by[c]) for c in
                                                   CLASSES + ("UNCLASSIFIED",))))
    counts = {"provenance": len(problems), "scope": len(scope), "needle": tally.total,
              "field": fields, "shape": shaped}
    return out, counts, shape.report(str(pin), needles, str(repo), digests=own)[0]


def pin_census(pin, repo, tip, excludes, ns, sidecar, scratch, wrapper=None):
    pin = Path(pin)
    table = Table(ns.items)
    out = ["# NEEDLES + PROVENANCE + SHAPES census of this pin (rounds 11-12: every file,",
           "# every class). No needle is printed: a finding names the file, the needle's SOURCE",
           "# and the count. Every file is read whole, this log included: it is rewritten until",
           "# a pass reproduces it and pin-path-scan.log byte for byte.",
           ns.line(),
           "BOUND " + BOUND]
    lines, c, shape_text = files_census(pin, repo, tip, ns, sidecar, scratch, table, wrapper,
                                        require_wrapper=True)
    out += lines
    obj_lines, obj_tally = object_census(repo, [tip], excludes, ns, table)
    out += ["", "# The landing range, object by object."] + obj_lines[1:]
    pin_total = c["provenance"] + c["scope"] + c["needle"] + c["field"] + c["shape"]
    total = pin_total + obj_tally.total
    out += ["", "PIN %d  (provenance %d + scope %d + needle %d + field %d + shape %d) -- the "
                "files of this pin, before the landing range" % (
                    pin_total, c["provenance"], c["scope"], c["needle"], c["field"],
                    c["shape"]),
            "TOTAL %d  (provenance %d + scope %d + needle %d + field %d + shape %d + objects "
            "%d)" % (total, c["provenance"], c["scope"], c["needle"], c["field"], c["shape"],
                     obj_tally.total)]
    return out, total, shape_text, pin_total


# ---------------------------------------------------------------------------
# The controls.

class _Controls:
    def __init__(self):
        self.rows = []
        self.info = []

    def check(self, cid, what, want_red, n, detail=""):
        got = "RED" if n else "GREEN"
        want = "RED" if want_red else "GREEN"
        self.rows.append((cid, what, got, want, "PASS" if got == want else "FAIL", n, detail))

    def lines(self):
        out = list(self.info)
        for cid, what, got, want, verdict, n, detail in self.rows:
            out.append("CONTROL %-22s got %-5s want %-5s %s  (%d)  %s%s" % (
                cid, got, want, verdict, n, what, ("  [" + detail + "]") if detail else ""))
        failed = sum(1 for r in self.rows if r[4] == "FAIL")
        red = sum(1 for r in self.rows if r[3] == "RED")
        out.append("CONTROLS %d: %d want RED, %d want GREEN; %d PASS, %d FAIL" % (
            len(self.rows), red, len(self.rows) - red, len(self.rows) - failed, failed))
        return out, failed


def _synthetic(ns):
    """Control needles: random, generated per run, never a real value, never printed."""
    word = "scrctl" + secrets.token_hex(5)
    # path-shaped, so that every escaped and encoded form differs from the raw one;
    # built from parts that hold no real needle, so that a negative stays clean
    path_like = "\\".join(("Q:", "CtlRoot" + secrets.token_hex(2), "Ctl" + secrets.token_hex(4)))
    number = str(7 * 10 ** 8 + secrets.randbelow(10 ** 8))
    hexish = secrets.token_hex(6)
    node = "zq" + secrets.token_hex(4)
    ident = "ctlident" + secrets.token_hex(4)
    spelled = "ctlspelled" + "".join(secrets.choice("abcdefghijklmnopqrstuvwxyz")
                                     for _ in range(6))
    anchored = "ctl-" + secrets.token_hex(2)
    extra = [{"literal": v, "lower": v.lower(), "sources": ["control"], "rules": set(r),
              "label": "control:" + name, "bounds": b}
             for name, v, r, b in (
                 ("word", word, (), (False, False)), ("path", path_like, (), (False, False)),
                 ("number", number, (), (False, False)), ("hex", hexish, (), (False, False)),
                 ("node", node, (), (False, False)),
                 ("identity", ident, ("identity",), (False, False)),
                 ("spelled", spelled, ("as-spelled",), (False, False)),
                 ("anchored", anchored, (), (True, True)))]
    return dict(word=word, path=path_like, number=number, hexish=hexish, node=node,
                ident=ident, spelled=spelled, anchored=anchored), \
        Table(list(ns.items) + extra)


def _rmtree(path):
    """Remove a scratch tree, read-only git objects included (they are read-only on Windows)."""

    def again(func, target, _exc):
        os.chmod(target, stat.S_IWRITE)
        func(target)

    if Path(path).exists():
        shutil.rmtree(str(path), onerror=again)


def _count(data, table, chunks=None, commit=False):
    t = Tally()
    if chunks:
        pieces = [data[i:i + chunks] for i in range(0, len(data), chunks)] or [b""]
        scan_chunks(pieces, table, t, "control", commit=commit)
    else:
        scan_chunks([data], table, t, "control", commit=commit)
    return t


def _shape_hits(shape, bundle, sidecar, repo, digests):
    """Every hit the shape census counts over `bundle`, summed over its classes."""
    needles = shape.load_needles(str(sidecar), str(bundle))
    result = shape.scan(str(bundle), needles, str(repo), digests=digests)
    return sum(n for _klass, where in result[1] for _f, n in where)


def self_test(scratch, repo, tip, excludes, ns, pin=None, sidecar=None):
    c = _Controls()
    v, table = _synthetic(ns)
    other, _t2 = _synthetic(ns)                 # values the table does not hold
    real = Table(ns.items)

    # -- A1: every real needle, in every form, found in memory (nothing written)
    whole = 0
    for item in ns.items:
        ok = True
        for _kind, text in forms_of(item["literal"]):
            for enc in ("utf-8", "utf-16-le"):
                t = Tally()
                scan_chunks([b"<" + text.encode(enc) + b">"], real, t, "self")
                ok = ok and t.total > 0
        whole += 1 if ok else 0
    c.check("A1-SELF", "each real needle found in each of its forms, in memory", False,
            len(ns.items) - whole, "%d/%d needles" % (whole, len(ns.items)))
    for fam in ("seat", "guard", "user-path"):
        n = sum(1 for i in ns.items if any(s.split(":")[0] == fam for s in i["sources"]))
        c.check("A1-SOURCE-" + fam.upper(), "the %s source contributes a needle" % fam,
                False, 0 if n else 1, "%d needle(s)" % n)
    upper = ("...%s..." % v["word"].upper()).encode("utf-8")
    c.check("A1-CASE", "a control needle in capitals", True, _count(upper, table).total)
    c.check("A1-CASE-NEG", "negative: another value in capitals", False,
            _count(("...%s..." % other["word"].upper()).encode(), table).total)
    odd = b"x" + ("..%s.." % v["path"]).encode("utf-16-le")
    c.check("A1-UTF16LE-ODD", "a path-like control needle in UTF-16LE at an odd offset",
            True, _count(odd, table).total)
    c.check("A1-UTF16LE-NEG", "negative: another path in UTF-16LE at an odd offset", False,
            _count(b"x" + ("..%s.." % other["path"]).encode("utf-16-le"), table).total)
    for cid, text in (("A1-URL", urllib.parse.quote(v["path"], safe="")),
                      ("A1-URL-PATH", urllib.parse.quote(v["path"])),
                      ("A1-URL-PLUS", urllib.parse.quote_plus(v["path"])),
                      ("A1-URL-TWICE", urllib.parse.quote(urllib.parse.quote(v["path"], safe=""),
                                                          safe="")),
                      ("A1-ESCAPED", v["path"].replace("\\", "\\\\")),
                      ("A1-ESCAPED-TWICE", v["path"].replace("\\", "\\\\\\\\")),
                      ("A1-JSON", json.dumps(v["path"]))):
        c.check(cid, "the path-like control needle, %s form" % cid[3:].lower(), True,
                _count(("a=%s;" % text).encode("utf-8"), table).total)
    c.check("A1-FORMS-NEG", "negative: another path in every one of those forms", False,
            sum(_count(("a=%s;" % f).encode("utf-8"), table).total
                for _k, f in forms_of(other["path"])))
    blob = bytearray(b"." * (2 * CHUNK))
    at = CHUNK - 3
    blob[at:at + len(v["word"])] = v["word"].encode()
    t = _count(bytes(blob), table, chunks=CHUNK)
    c.check("A1-STRADDLE", "a control needle across a chunk boundary, counted once", True,
            t.total, "exactly one: %s" % ("yes" if t.total == 1 else "NO"))
    if t.total != 1:
        c.check("A1-STRADDLE-ONCE", "the straddling needle counted exactly once", False, 1)
    three = ("%s|%s|%s" % (v["word"], v["word"].upper(), v["word"])).encode()
    t = _count(three, table)
    c.check("A1-COUNT", "three occurrences counted as three", False, abs(t.total - 3),
            "%d counted" % t.total)
    t = _count(("x %s x" % v["spelled"].capitalize()).encode(), table)
    c.check("A1-AS-SPELLED-DECLARED", "an as-spelled needle capitalised: declared, not a "
            "finding", False, t.total, "declared %d" % t.declared["AS-SPELLED"])
    if not t.declared["AS-SPELLED"]:
        c.check("A1-AS-SPELLED-COUNTED", "the declared occurrence is counted", False, 1)
    c.check("A1-AS-SPELLED", "an as-spelled needle as spelled", True,
            _count(("x %s x" % v["spelled"]).encode(), table).total)
    for cid, what, text, enc, want in (
            ("A1-ANCHORED", "an anchored needle as a whole word", "a %s b", "utf-8", True),
            ("A1-ANCHORED-PUNCT", "an anchored needle between punctuation", "a=\"%s\";",
             "utf-8", True),
            ("A1-ANCHORED-UTF16", "an anchored needle as a whole word in UTF-16LE", "a %s b",
             "utf-16-le", True),
            ("A1-EMBEDDED", "an anchored needle inside a longer word: declared", "a %sx b",
             "utf-8", False),
            ("A1-EMBEDDED-UTF16", "the same inside a longer word in UTF-16LE: declared",
             "a x%s b", "utf-16-le", False)):
        t = _count((text % v["anchored"]).encode(enc), table)
        c.check(cid, what, want, t.total, "declared embedded %d" % t.declared["EMBEDDED"])
        if not want and not t.declared["EMBEDDED"]:
            c.check(cid + "-COUNTED", "the declared occurrence is counted", False, 1)

    # -- A4: every rendered field of a summary
    for cid, doc, neg in (
            ("A4-NUMERIC", {"passed": int(v["number"])}, {"passed": int(other["number"])}),
            ("A4-NODE-NAME", {"tests": [{"node": "test_r10_%s_gate" % v["node"]}]},
             {"tests": [{"node": "test_r10_%s_gate" % other["node"]}]}),
            ("A4-HEX", {"tip": secrets.token_hex(7) + v["hexish"] + secrets.token_hex(7)},
             {"tip": secrets.token_hex(20)})):
        c.check(cid, "a control needle rendered as %s" % cid[3:].lower().replace("-", " "),
                True, len(field_findings(doc, table)))
        c.check(cid + "-NEG", "negative: the same field without it", False,
                len(field_findings(neg, table)))

    # -- A3: objects, in a scratch clone under the session's scratch directory
    scratch = Path(scratch)
    clone = scratch / "a3-clone"
    if clone.exists():
        _rmtree(clone)
    common = _git(repo, ["rev-parse", "--path-format=absolute", "--git-common-dir"]).strip()
    p = subprocess.run(["git", "--no-replace-objects", "clone", "--quiet", "--no-checkout",
                        "--shared", common, str(clone)], capture_output=True, env=git_env())
    if p.returncode != 0:
        raise Refusal("the scratch clone could not be made (rc=%d)" % p.returncode)
    tip_sha = _git(repo, ["rev-parse", "--verify", tip + "^{commit}"]).strip()
    ex = [_git(repo, ["rev-parse", "--verify", e + "^{commit}"]).strip() for e in excludes]
    env = dict(os.environ, GIT_AUTHOR_NAME="control", GIT_AUTHOR_EMAIL="control@example.invalid",
               GIT_COMMITTER_NAME="control", GIT_COMMITTER_EMAIL="control@example.invalid",
               GIT_INDEX_FILE=str(scratch / "a3.index"))
    ref = "refs/heads/control"

    def objects(tipsha):
        t = Tally()
        scan_objects(clone, [tipsha], ex, table, t)
        return t

    def commit_with(path=None, data=None, author=None, message="a planted control"):
        cenv = dict(env)
        if author:
            cenv["GIT_AUTHOR_NAME"] = author
        _git(clone, ["read-tree", tip_sha], env=cenv)
        if path is not None:
            blob_id = _git(clone, ["hash-object", "-w", "--stdin"], stdin=data,
                           env=cenv).strip()
            _git(clone, ["update-index", "--add", "--cacheinfo",
                         "100644,%s,%s" % (blob_id, path)], env=cenv)
        tree = _git(clone, ["write-tree"], env=cenv).strip()
        return _git(clone, ["commit-tree", tree, "-p", tip_sha, "-m", message],
                    env=cenv).strip()

    def commit_changes(changes, removals=(), message="a planted control"):
        _git(clone, ["read-tree", tip_sha], env=env)
        for path, data in sorted(changes.items()):
            blob_id = _git(clone, ["hash-object", "-w", "--stdin"], stdin=data,
                           env=env).strip()
            _git(clone, ["update-index", "--add", "--cacheinfo",
                         "100644,%s,%s" % (blob_id, path)], env=env)
        for path in removals:
            _git(clone, ["update-index", "--force-remove", path], env=env)
        tree = _git(clone, ["write-tree"], env=env).strip()
        return _git(clone, ["commit-tree", tree, "-p", tip_sha, "-m", message],
                    env=env).strip()

    try:
        _git(clone, ["update-ref", ref, tip_sha])
        base = objects(ref)
        c.info.append("RANGE %s --not %s: %d needle finding(s); declared: as-spelled %d, "
                      "commit-identity %d, embedded %d -- the range's verdict is the census's "
                      "(pin-census.log); every A3 arm below is measured against this count"
                      % (tip_sha[:12], " ".join(e[:12] for e in ex), base.total,
                         base.declared["AS-SPELLED"], base.declared["COMMIT-IDENTITY"],
                         base.declared["EMBEDDED"]))
        # Every arm below is measured AGAINST that base: a plant must add findings, and
        # restoring the ref or planting the needle-free twin must add none. A3-RANGE
        # above is the range's own verdict; these arms prove the mechanism either way.
        big = bytearray(b"." * (9 * CHUNK))
        at = 8 * CHUNK + 4099
        big[at:at + len(v["word"])] = v["word"].encode()
        big_neg = bytearray(b"." * (9 * CHUNK))
        big_neg[at:at + len(other["word"])] = other["word"].encode()
        plants = (
            ("A3-FILENAME", "a control needle in a file name, in a nested tree",
             dict(path="ctl/%s.txt" % v["word"], data=b"control\n"),
             dict(path="ctl/%s.txt" % other["word"], data=b"control\n")),
            ("A3-COMMIT-HEADER", "a control needle as the author of a commit",
             dict(author=v["word"]), dict(author=other["word"])),
            ("A3-PAST-8MIB", "a control needle 8 MiB + 4099 bytes into a 9 MiB blob",
             dict(path="ctl/big.bin", data=bytes(big)),
             dict(path="ctl/big.bin", data=bytes(big_neg))),
            ("A3-MESSAGE", "a control identity needle in a commit message",
             dict(message="a planted control naming %s" % v["ident"]),
             dict(message="a planted control naming %s" % other["ident"])))
        for cid, what, plant, negative in plants:
            _git(clone, ["update-ref", ref, commit_with(**plant)])
            c.check(cid, what, True, objects(ref).total - base.total, "over the range's own")
            _git(clone, ["update-ref", ref, tip_sha])
            c.check(cid + "-RESTORED", "the same range with the plant removed", False,
                    abs(objects(ref).total - base.total), "over the range's own")
            _git(clone, ["update-ref", ref, commit_with(**negative)])
            c.check(cid + "-NEG", "negative: the same structure without the needle", False,
                    abs(objects(ref).total - base.total), "over the range's own")
            _git(clone, ["update-ref", ref, tip_sha])
        _git(clone, ["update-ref", ref, commit_with(author=v["ident"])])
        t = objects(ref)
        c.check("A3-IDENTITY-HEADER", "a control identity needle as the author: declared",
                False, abs(t.total - base.total), "declared commit-identity %d (the range's "
                "own %d)" % (t.declared["COMMIT-IDENTITY"], base.declared["COMMIT-IDENTITY"]))
        if t.declared["COMMIT-IDENTITY"] <= base.declared["COMMIT-IDENTITY"]:
            c.check("A3-IDENTITY-COUNTED", "the declared header occurrence is counted",
                    False, 1)
        _git(clone, ["update-ref", ref, tip_sha])

        # -- H1 (round 11): the census reads EVERY file, whatever its class. A
        # UUID-shaped value in a TRACKED-COPY -- byte-equal to its blob at a twin
        # commit, so provenance passes -- reddens the census; the same groups
        # joined by underscores, which is no UUID, do not.
        if sidecar is None:
            c.check("H1-SIDECAR", "the shape census's sidecar is named, so H1 can run", False, 1)
        else:
            h1_path = "tools/train_pin/train_pin_cite.py"
            h1_orig = _git(clone, ["cat-file", "blob", "%s:%s" % (tip_sha, h1_path)],
                           binary=True)
            groups = [secrets.token_hex(n // 2) for n in (8, 4, 4, 4, 12)]
            h1_dir = scratch / "h1-pin"

            def h1_counts(commit, data):
                _rmtree(h1_dir)
                h1_dir.mkdir(parents=True)
                (h1_dir / "train_pin_cite.py").write_bytes(data)
                blob = _git(clone, ["rev-parse", "%s:%s" % (commit, h1_path)]).strip()
                (h1_dir / MANIFEST).write_bytes(json.dumps({
                    "schema": "SCR_TRAIN_PIN_PROVENANCE", "version": 1, "tip": commit,
                    "files": [{"class": "TRACKED-COPY", "file": "train_pin_cite.py",
                               "path": h1_path, "blob": blob},
                              {"class": "TYPED", "file": MANIFEST, "what": "this manifest"}]},
                    indent=1).encode("utf-8"))
                try:
                    return files_census(h1_dir, clone, commit, ns, sidecar, scratch)[1]
                finally:
                    _rmtree(h1_dir)

            h1_base = h1_counts(tip_sha, h1_orig)
            for cid, what, want, joiner in (
                    ("H1-UUID-TRACKED-COPY", "a UUID-shaped value in a TRACKED-COPY twin, "
                     "byte-equal to its blob at a twin commit", True, "-"),
                    ("H1-UUID-TRACKED-COPY-NEG", "negative: the same groups joined by "
                     "underscores, which is no UUID", False, "_")):
                data = h1_orig + ("# %s\n" % joiner.join(groups)).encode("ascii")
                counts = h1_counts(commit_with(path=h1_path, data=data), data)
                diff = sum(counts.values()) - sum(h1_base.values())
                c.check(cid, what, want, max(diff, 0) if want else abs(diff),
                        "provenance %d; shape %d over the twin's own %d"
                        % (counts["provenance"], counts["shape"], h1_base["shape"]))
                if counts["provenance"]:
                    c.check(cid + "-PROVENANCE", "the twin passes provenance, so the hit is "
                            "the scan's", False, counts["provenance"])

        # -- H3 (round 11): every git read with replacement objects OFF. A blob
        # holding a control needle is replaced, in the clone, by a clean twin.
        h3_path = "tools/train_pin/train_pin_schema.py"
        h3_orig = _git(clone, ["cat-file", "blob", "%s:%s" % (tip_sha, h3_path)], binary=True)
        dirty = h3_orig + ("# %s\n" % v["word"]).encode("ascii")
        clean = h3_orig + ("# %s\n" % other["word"]).encode("ascii")
        dirty_commit = commit_with(path=h3_path, data=dirty)
        dirty_blob = _git(clone, ["rev-parse", "%s:%s" % (dirty_commit, h3_path)]).strip()
        clean_blob = _git(clone, ["hash-object", "-w", "--stdin"], stdin=clean).strip()
        _git(clone, ["replace", dirty_blob, clean_blob])
        h3_dir = scratch / "h3-pin"

        def h3_problems(data):
            _rmtree(h3_dir)
            h3_dir.mkdir(parents=True)
            (h3_dir / "copy.py").write_bytes(data)
            (h3_dir / MANIFEST).write_bytes(json.dumps({
                "schema": "SCR_TRAIN_PIN_PROVENANCE", "version": 1, "tip": dirty_commit,
                "files": [{"class": "TRACKED-COPY", "file": "copy.py", "path": h3_path,
                           "blob": dirty_blob},
                          {"class": "TYPED", "file": MANIFEST, "what": "this manifest"}]},
                indent=1).encode("utf-8"))
            try:
                return len(provenance(h3_dir, clone, dirty_commit, scratch)[0])
            finally:
                _rmtree(h3_dir)

        try:
            plain = {k: val for k, val in os.environ.items() if k != "GIT_NO_REPLACE_OBJECTS"}
            raw = subprocess.run(["git", "-C", str(clone), "cat-file", "blob", dirty_blob],
                                 capture_output=True, env=plain).stdout
            c.check("H3-REPLACE-LIVE", "WITHOUT the flag, git answers the clean twin's bytes "
                    "under the planted blob's id: the replacement is live", True,
                    0 if raw == dirty else 1)
            c.check("H3-DOOR-ORIGINAL", "WITH it -- this census's door -- the same id answers "
                    "the original bytes", False,
                    0 if _git(clone, ["cat-file", "blob", dirty_blob], binary=True) == dirty
                    else 1)
            t = Tally()
            scan_chunks([raw], table, t, "raw")
            c.check("H3-RAW-READ-MISSES", "negative: the bytes a read without the flag gets "
                    "hold no control needle -- a census reading them would pass", False, t.total)
            _git(clone, ["update-ref", ref, dirty_commit])
            c.check("H3-OBJECTS", "the object census over a range holding the replaced blob "
                    "reads the ORIGINAL and finds the needle", True,
                    max(objects(ref).total - base.total, 0), "over the range's own")
            _git(clone, ["update-ref", ref, tip_sha])
            c.check("H3-PROVENANCE-SUBSTITUTE", "a TRACKED-COPY holding the substitute's bytes "
                    "-- what an assembly reading replacements copies -- fails provenance", True,
                    h3_problems(clean))
            c.check("H3-PROVENANCE-ORIGINAL", "negative: the same pin holding the original "
                    "bytes passes", False, h3_problems(dirty))
        finally:
            _git(clone, ["replace", "-d", dirty_blob], check=False)
            _git(clone, ["update-ref", ref, tip_sha])

        # -- H4 (round 11): tracked-ness and ignore proofs from the pin commit's
        # OBJECTS. The clone's own index and worktree are made to mirror a checkout
        # of the tip, then edited as the round-10 finding describes.
        lane = ["tools/train_pin", "backend/tests/test_pc_steam_server.py", "scripts/deploy"]

        def derived(commit):
            return (_git(clone, ["ls-tree", "-r", "--name-only", commit, "--"] + lane,
                         binary=True) + ignore_proof(clone, commit, SCOPE_PATHS, scratch))

        def old_recipes():
            a = subprocess.run(git_argv(clone, ["ls-files", "--"] + lane),
                               capture_output=True, env=git_env()).stdout
            b = subprocess.run(git_argv(clone, ["check-ignore", "-v"] + list(SCOPE_PATHS)),
                               capture_output=True, env=git_env()).stdout
            return a + b

        for rule in [p for p in tip_paths(clone, tip_sha)
                     if p == ".gitignore" or p.endswith("/.gitignore")]:
            target = clone.joinpath(*rule.split("/"))
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(_git(clone, ["cat-file", "blob", "%s:%s" % (tip_sha, rule)],
                                    binary=True))
        _git(clone, ["read-tree", tip_sha])
        pristine_new, pristine_old = derived(tip_sha), old_recipes()
        victim = "tools/train_pin/train_pin_cite.py"
        top_rules = _git(clone, ["cat-file", "blob", "%s:.gitignore" % tip_sha], binary=True)
        dirty_rules = ("\n/%s\n!/%s\n" % (victim, SCOPE_PATHS[0])).encode("ascii")
        _git(clone, ["update-index", "--force-remove", victim])
        (clone / ".gitignore").write_bytes(top_rules + dirty_rules)
        c.check("H4-WORKTREE-EDITS-INERT", "a staged removal and a dirty ignore rule change "
                "nothing the census derives from the pin commit", False,
                0 if derived(tip_sha) == pristine_new else 1)
        c.check("H4-WORKTREE-EDITS-LIVE", "...and the same edits DO move the index and "
                "worktree recipes round 10 re-ran", True,
                0 if old_recipes() == pristine_old else 1)
        twin = commit_changes({".gitignore": top_rules + dirty_rules}, [victim])
        c.check("H4-TWIN-TIP", "the same edits COMMITTED at a twin tip do change what the "
                "census derives", True, 0 if derived(twin) == pristine_new else 1)
        c.check("H4-SCOPE-TIP", "negative: at the pin commit the train and its seat file are "
                "untracked and ignored", False, len(scope_problems(clone, tip_sha, scratch)))
        tracked_twin = commit_changes({SCOPE_PATHS[0]: b"# a placeholder train\n"})
        _git(clone, ["read-tree", tracked_twin])
        _git(clone, ["update-index", "--force-remove", SCOPE_PATHS[0]])
        (clone / ".gitignore").write_bytes(top_rules + ("\n/%s\n" % SCOPE_PATHS[0])
                                           .encode("ascii"))
        listed = subprocess.run(git_argv(clone, ["ls-files", "--", SCOPE_PATHS[0]]),
                                capture_output=True, env=git_env()).stdout
        ignored = subprocess.run(git_argv(clone, ["check-ignore", "-q", SCOPE_PATHS[0]]),
                                 capture_output=True, env=git_env()).returncode
        c.check("H4-HIDDEN-TRAIN-OLD", "a twin tip that TRACKS the train, hidden by a staged "
                "removal and a dirty ignore rule: the round-10 recipes read it untracked and "
                "ignored", True, 1 if (not listed.strip() and ignored == 0) else 0)
        c.check("H4-HIDDEN-TRAIN", "...and the scope check, asking that twin tip's objects, "
                "reports it tracked", True, len(scope_problems(clone, tracked_twin, scratch)))
    finally:
        _rmtree(clone)
        try:
            os.remove(str(scratch / "a3.index"))
        except OSError:
            pass
    c.check("A3-CLONE-REMOVED", "the scratch clone is removed afterwards", False,
            1 if clone.exists() else 0)

    # -- H2 (round 11) and H1 (round 12): the hook and the guard, judged EXACTLY by the
    # census's own inventory and judgement (guard_inventory, guard_judgement) over
    # scratch copies of both in a scratch hooks directory. Nothing of either is printed:
    # a copy is edited at the syntax-tree position of one occurrence, or by one line
    # added, and only counts are shown.
    hooks = _hooks_dir(repo)
    hook_text = (hooks / GUARD_HOOK).read_bytes().decode("utf-8")
    base = guard_inventory(hooks)
    called = hook_units(hooks / GUARD_HOOK)[3]
    gname = called[0] if called else None
    gsrc = (hooks / gname).read_bytes().decode("utf-8") if gname else ""
    gtree = ast.parse(gsrc)
    pattern_units = [u for u in base["patterns"] if u.file == gname and u.pos]
    declared_strs = [u for u in base["units"] if u.file == gname and u.kind == "str"
                     and u.pos and u not in base["patterns"] and len(u.value) >= 4
                     and not u.role.endswith("docstring")]
    imported = [a.name.split(".")[0] for n in ast.walk(gtree) if isinstance(n, ast.Import)
                for a in n.names]
    top_imports = [n for n in gtree.body if isinstance(n, ast.Import)]
    h2dir = scratch / "h2-hooks"
    c.check("H1-HOOK-READ", "the installed hook is read as shell: every word a unit, every "
            "unit declared, no refusal", False,
            (0 if base["units"] and not base["refusals"]
             and not [u for u in base["patterns"] if u.file == GUARD_HOOK] else 1),
            "%d hook unit(s), %d refusal(s)"
            % (sum(1 for u in base["units"] if u.file == GUARD_HOOK), len(base["refusals"])))

    def h2(cid, what, want_red, text, extra=None, hook=None, expected=None, shapes=None):
        _rmtree(h2dir)
        h2dir.mkdir(parents=True)
        (h2dir / GUARD_HOOK).write_bytes((hook_text if hook is None else hook).encode("utf-8"))
        (h2dir / gname).write_bytes(text.encode("utf-8"))
        for name, body in (extra or {}).items():
            (h2dir / name).write_bytes(body.encode("utf-8"))
        want = GUARD_PATTERNS if expected is None else expected
        try:
            inv = guard_inventory(h2dir, shapes=shapes)
            problem = guard_judgement(inv, want)
            refs = inv["refusals"]
            at_site = sum(1 for r in refs if r.startswith(("a pattern built at ",
                                                           "a pattern site at ")))
            of_shape = sum(1 for r in refs if r.startswith("the code of "))
            detail = ("%d undeclared occurrence(s), %d declared occurrence(s) absent, %d "
                      "refusal(s) (%d at a pattern site, %d of the declared shape); declared "
                      "exactly %d" % (len(inv["patterns"]), inv["absent"], len(refs), at_site,
                                      of_shape, want))
        except (SyntaxError, Refusal) as e:
            problem = True
            detail = "the copy is refused before it is counted (%s)" % type(e).__name__
        finally:
            _rmtree(h2dir)
        c.check(cid, what, want_red, 1 if problem else 0, detail)

    def at_pos(pos, new, src=None):
        raw = (gsrc if src is None else src).encode("utf-8")
        starts = [0]
        for line in raw.splitlines(keepends=True):
            starts.append(starts[-1] + len(line))
        a = starts[pos[0] - 1] + pos[1]
        b = starts[pos[2] - 1] + pos[3]
        return (raw[:a] + new(raw[a:b].decode("utf-8")).encode("utf-8") + raw[b:]).decode(
            "utf-8")

    def after_shebang(line):
        first, nl, rest = hook_text.partition("\n")
        return first + nl + line + "\n" + rest

    def rnd():
        return "scrctl" + secrets.token_hex(5)

    if not gname or len(pattern_units) != GUARD_PATTERNS or not declared_strs \
            or not top_imports:
        c.check("H2-POSITIONED", "the guard's undeclared occurrence is found at exactly one "
                "position, and a declared constant and a top-level import exist, so the "
                "controls can move them", False, 1,
                "%d position(s), %d declared constant(s), %d top-level import(s)"
                % (len(pattern_units), len(declared_strs), len(top_imports)))
    else:
        value = pattern_units[0].value
        pos = pattern_units[0].pos
        half = len(value) // 2
        lit = declared_strs[0]
        h2("H2-EXACT", "the installed hook and guard: exactly the declared number of patterns "
           "and every declared occurrence", False, gsrc)
        # RE-ANCHORED in round 13 (R12-H1): the closed allow-list accepts a pattern operand
        # ONLY as a folded string or bytes literal or a declared import. A pattern reachable
        # from the site only through a list index or a compiled-regex `.pattern` attribute
        # does NOT fold, so the site refuses it -- even though the walk still records the
        # constant (the count stays one). Completeness no longer rests on the walk finding a
        # constant somewhere inside; these two arms therefore now redden, where round 12 held
        # them green under the looser walk-enumeration that R10-H2/R11-H1/R12-H1 kept reopening.
        h2("H2-MOVED-LIST", "the pattern reachable from the site only through a list index: "
           "not a folded literal, so the site refuses it", True,
           at_pos(pos, lambda seg: "[%s][0]" % seg))
        h2("H2-MOVED-COMPILE", "the pattern reachable from the site only through a compiled "
           "-regex .pattern attribute: not a folded literal, so the site refuses it", True,
           at_pos(pos, lambda seg: "re.compile(%s).pattern" % seg))
        h2("H2-MOVED-COMPOSED", "the pattern split in two and joined by +: it folds back into "
           "one literal, so the site accepts it (count still one)", False,
           at_pos(pos, lambda seg: "%r + %r" % (value[:half], value[half:])))
        h2("H2-DELETED", "the pattern deleted", True, at_pos(pos, lambda seg: "str()"))
        for label, line in (
                ("LIST", "_SCR_CTL = [%r]\n" % rnd()),
                ("TUPLE", "_SCR_CTL = (%r,)\n" % rnd()),
                ("DICT", "_SCR_CTL = {%r: 1}\n" % rnd()),
                ("CALL-ARGUMENT", "print(%r)\n" % rnd()),
                ("COMPILED", "_SCR_CTL = re.compile(%r)\n" % rnd()),
                ("ANNOTATION", "_SCR_CTL: %r = 1\n" % rnd()),
                ("DEFAULT", "def _scr_ctl(x=%r):\n    return x\n" % rnd()),
                ("IMPORT-ALIAS", "import os as %s\n" % rnd()),
                ("COMPOSED", "_SCR_CTL = %r + %r\n" % (rnd(), "x")),
                ("FSTRING", "_SCR_CTL = f'%s{_SCR_X}'\n" % rnd()),
                ("BYTES", "_SCR_CTL = %r\n" % rnd().encode("ascii"))):
            h2("H2-ADDED-" + label, "an undeclared constant added as %s"
               % label.lower().replace("-", " "), True, gsrc + "\n" + line)
        if imported:
            sibling = imported[0] + ".py"
            h2("H2-SIBLING", "an undeclared constant in a module beside the guard, under a "
               "name the guard already imports", True, gsrc, {sibling: "X = %r\n" % rnd()})
            # Round 13 (R12-H1): a module beside the guard that the guard imports is guard
            # code, so the declared shape refuses it unless its own shape is declared. The
            # negative arm declares it, and so still judges what it always did -- a module
            # holding no text adds no pattern; H1-SHAPE-SIBLING judges it undeclared.
            beside = dict(GUARD_SHAPE)
            beside[sibling] = guard_shape(ast.parse("X = 1\n"))
            h2("H2-SIBLING-NEG", "negative: the same module beside the guard, holding no "
               "text, its shape declared", False, gsrc, {sibling: "X = 1\n"}, shapes=beside)
            h2("H1-SHAPE-SIBLING", "the same module beside the guard, holding no text, its "
               "shape NOT declared: refused by the declared shape", True, gsrc,
               {sibling: "X = 1\n"})
        else:
            c.check("H2-SIBLING", "a sibling module (the guard imports nothing, so the arm "
                    "cannot run)", True, 0)
        h2("H2-RUNTIME-CHR", "text composed at run time from numbers (chr): refused", True,
           gsrc + "\n_SCR_CTL = chr(115) + chr(99)\n")
        h2("H2-RUNTIME-ENV-KEY", "an environment key that is not a constant: refused", True,
           gsrc + "\n_SCR_CTL = os.environ.get(_SCR_KEY)\n")
        # R11-H1: the hook's own text. Each arm keeps the hook's Python child exactly as
        # installed; only a line after the shebang differs.
        h2("H1-HOOK-GREP", "a grep written into the hook, the same Python child still run "
           "after it", True, gsrc, hook=after_shebang("grep -qs '%s' /dev/null && exit 1"
                                                       % rnd()))
        h2("H1-HOOK-EXPORT", "an export written into the hook, the same Python child still "
           "run after it", True, gsrc, hook=after_shebang("export SCR_CTL='%s'" % rnd()))
        h2("H1-HOOK-ASSIGN", "an assignment written into the hook, the same Python child "
           "still run after it", True, gsrc, hook=after_shebang("SCR_CTL='%s'" % rnd()))
        h2("H1-HOOK-SUBSTITUTION", "a command substitution written into the hook", True, gsrc,
           hook=after_shebang("SCR_CTL=$(printf %%s '%s')" % rnd()))
        h2("H1-HOOK-BACKQUOTE", "a backquoted command in the hook: refused", True, gsrc,
           hook=after_shebang("SCR_CTL=`printf x`"))
        h2("H1-HOOK-HEREDOC", "a here-document in the hook: refused", True, gsrc,
           hook=after_shebang("cat <<SCR\nscrctl\nSCR"))
        h2("H1-HOOK-COMMENT-NEG", "negative: the same grep as an inert comment in the hook",
           False, gsrc, hook=after_shebang("# grep -qs '%s' /dev/null && exit 1" % rnd()))
        requoted = re.sub(r'"(\$[A-Za-z_][A-Za-z0-9_]*)/([^"$`\\]+)"', r"\1/'\2'", hook_text)
        if requoted == hook_text:
            c.check("H1-HOOK-REQUOTED-NEG", "negative: the hook requoted, the same words "
                    "(the requote found nothing to change, so the arm cannot run)", False, 1)
        else:
            h2("H1-HOOK-REQUOTED-NEG", "negative: the hook's script path requoted, the same "
               "words the shell reads", False, gsrc, hook=requoted)
        # R11-H1: a declaration is an OCCURRENCE, keyed by (file, role, kind, value).
        h2("H1-REUSED-MATCHER", "a declared constant written again as the argument of a "
           "matcher", True, gsrc + "\n_SCR_CTL = re.search(%r, _SCR_X)\n" % lit.value)
        h2("H1-REUSED-COMMENT-NEG", "negative: the same matcher as an inert comment", False,
           gsrc + "\n# _SCR_CTL = re.search(%r, _SCR_X)\n" % lit.value)
        h2("H1-DUPLICATE", "a declared occurrence written a second time at the same role",
           True, gsrc + "\n" + ast.get_source_segment(gsrc, top_imports[0]) + "\n")
        h2("H1-DECLARED-MOVED", "a declared constant moved to another role", True,
           at_pos(lit.pos, lambda seg: "[%s][0]" % seg))
        h2("H1-DECLARED-ABSENT", "a declared constant deleted, the pattern count unchanged",
           True, at_pos(lit.pos, lambda seg: "0"))
        h2("H1-COUNT-ABOVE", "the installed hook and guard judged against a declared count "
           "one above", True, gsrc, expected=GUARD_PATTERNS + 1)
        h2("H1-COUNT-BELOW", "the installed hook and guard judged against a declared count "
           "one below", True, gsrc, expected=GUARD_PATTERNS - 1)
        # R12-H1, the first layer: the pattern-construction sites, judged by the CLOSED
        # allow-list. One RED arm per refused class, each adding an active pattern the way the
        # round-12 report's `RX2 = re.compile(str(31415).encode())` does: no string, bytes or
        # import unit is added. H1-SITE-* judge the WHOLE census (guard_judgement); H1-ALLOW-*
        # judge the site layer ALONE (pattern_site_refusals), so every class is proven refused
        # by the allow-list itself. NUMERIC, STR, ENCODE, JOIN and KEYWORD use nothing the
        # deny-list names; CHR and BYTES are also refused by that earlier, redundant list. The
        # twin adds a folded composition at the same site, and the site layer does NOT refuse
        # it. Nothing of any value is printed: only whether a layer refused, and how often.
        site_classes = (
            ("NUMERIC", "a numeric constant compiled as a pattern", "31415"),
            ("STR", "str() of a number, encoded, compiled as a pattern", "str(31415).encode()"),
            ("ENCODE", ".encode() of a non-folded value compiled as a pattern",
             "_SCR_X.encode()"),
            ("CHR", "chr() composition compiled as a pattern", "chr(115) + chr(99)"),
            ("BYTES", "bytes() of a byte table compiled as a pattern", "bytes((115, 99))"),
            ("JOIN", "join() over a non-literal compiled as a pattern", '"".join(_SCR_L)'),
            ("KEYWORD", "str() of a number, encoded, passed as the pattern= keyword",
             "pattern=str(31415).encode()"))
        for cls, what, arg in site_classes:
            h2("H1-SITE-" + cls, what + ": refused", True,
               gsrc + "\n_SCR_RX = re.compile(%s)\n" % arg)

        def psite(cid, what, want_red, arg):
            src = gsrc + "\n_SCR_RX = re.compile(%s)\n" % arg
            try:
                refs = pattern_site_refusals(ast.parse(src), gname)
                got, detail = (1 if refs else 0), "%d site refusal(s)" % len(refs)
            except SyntaxError:
                got, detail = 1, "the source did not parse"
            c.check(cid, what, want_red, got, detail)

        for cls, what, arg in site_classes:
            psite("H1-ALLOW-" + cls, what + ": the site layer alone refuses it", True, arg)
        psite("H1-ALLOW-STARRED", "a starred first argument hides the pattern operand: the "
              "site layer refuses it", True, "*_SCR_L")
        psite("H1-ALLOW-MAPPING", "a ** mapping and no positional pattern: the site layer "
              "refuses it", True, "**_SCR_K")
        psite("H1-SITE-FOLDED-NEG", "negative: a folded composition of literal pieces at a "
              "pattern site is not refused", False, '"sc" + "rc" * 2')

        # R12-H1, the second layer: the guard's code declared by its shape (GUARD_SHAPE). Each
        # RED arm builds run-time text from numbers at NO site the first layer recognises and
        # adds no text unit, so neither the site layer, the deny-list nor the pattern count can
        # see it. Its -UNSHAPED-NEG counterfactual judges the same copy with that copy's own
        # shape declared and stays GREEN: no other layer refuses it, so the declared shape is
        # what does. The layout twin adds a comment and blank lines only: the shape holds.
        def own(text):
            return {gname: guard_shape(ast.parse(text))}

        for cls, what, tail in (
                ("SUBSTRING", "run-time text from numbers used in a substring test",
                 "\n_SCR_T = str(31415) in str(27182)\n"),
                ("ALIAS", "re.compile bound to another name and called on run-time text",
                 "\n_SCR_C = re.compile\n_SCR_P = _SCR_C(str(31415).encode())\n")):
            h2("H1-SHAPE-" + cls, what + ": refused by the declared shape", True, gsrc + tail)
            h2("H1-SHAPE-%s-UNSHAPED-NEG" % cls, "negative: the same copy with its own shape "
               "declared -- no other layer refuses it", False, gsrc + tail,
               shapes=own(gsrc + tail))
        h2("H1-SHAPE-LAYOUT-NEG", "negative: a comment line and blank lines added, the code "
           "unchanged: the declared shape holds", False, gsrc + "\n\n# a comment, not code\n\n")

    # -- L1 (round 12): the snapshot wrapper's gated copy. Nothing of the wrapper is
    # printed; only whether the gate reproduces the tracked copy.
    wsrc = wrapper_source(repo)
    wblob = subprocess.run(git_argv(repo, ["cat-file", "blob", "%s:%s" % (tip_sha,
                                                                           WRAPPER_GATED)]),
                           capture_output=True, env=git_env())
    if wsrc is None or wblob.returncode != 0:
        c.check("L1-GATE-EXACT", "the gate of the repository copy is the tracked copy at the "
                "pin commit (the repository copy or the tracked copy is not there)", False, 1)
    else:
        wraw = wsrc.read_bytes()

        def gate_arm(cid, what, want_red, data):
            try:
                got = 0 if _sha(wrapper_gate(data)) == _sha(wblob.stdout) else 1
                detail = "the gate %s the tracked copy" % ("reproduces" if not got
                                                           else "does not reproduce")
            except Refusal:
                got, detail = 1, "the gate refuses"
            c.check(cid, what, want_red, got, detail)

        gate_arm("L1-GATE-EXACT", "the gate of the repository copy is the tracked copy at the "
                 "pin commit, byte for byte", False, wraw)
        gate_arm("L1-GATE-SHAPE", "the repository copy with one more address: the gate "
                 "refuses", True,
                 wraw + ("# %s\n" % ".".join(["10"] + ["0"] * 2 + ["1"])).encode("ascii"))
        gate_arm("L1-GATE-DRIFT", "the repository copy with one inert line added: gated, but "
                 "not the tracked copy", True, wraw + b"# scrctl\n")
        c.check("L1-GATE-NEEDLE-FREE", "the tracked copy holds no needle", False,
                len(finding_spans(wblob.stdout, real)))

    # -- L5 (round 12): the census's logs are a fixed point. A synthetic pass whose
    # report counts the bytes of every file in a scratch directory, its own logs
    # included, exactly as the census's byte totals do.
    fp = scratch / "l5-pin"

    def fresh():
        _rmtree(fp)
        fp.mkdir(parents=True)
        (fp / "a.txt").write_bytes(b"x" * 997)

    def sized():
        rels = _files_under(fp)
        n = sum((fp / r).stat().st_size for r in rels)
        return (["FILES %d, %d byte(s)" % (len(rels), n)], 0, "shape over %d byte(s)\n" % n)

    fresh()
    _lines, _t, passes = census_fixed_point(fp, sized, sized())
    c.check("L5-FIXED-POINT", "the logs as written are reproduced byte for byte by one more "
            "pass", False, 0 if census_reproduced(fp, sized, 0) else 1,
            "fixed point after %d pass(es)" % passes)
    fresh()
    first = sized()
    (fp / CENSUS_LOGS[0]).write_bytes(census_log(first[0], 0, 0))
    (fp / CENSUS_LOGS[1]).write_bytes(first[2].encode("utf-8"))
    second = sized()
    (fp / CENSUS_LOGS[0]).write_bytes(census_log(second[0], 0, 0))
    (fp / CENSUS_LOGS[1]).write_bytes(second[2].encode("utf-8"))
    c.check("L5-ROUND11-DISCARD", "the round-11 order (the second pass written, the third "
            "discarded): its totals are not reproduced", True,
            0 if census_reproduced(fp, sized, 0) else 1)
    fresh()
    tick = itertools.count()
    _lines, t_moving, passes = census_fixed_point(
        fp, lambda: (["PASS %d" % next(tick)], 0, ""), (["PASS start"], 0, ""))
    c.check("L5-NO-FIXED-POINT", "a pass that never reproduces its log: refused", True,
            1 if t_moving else 0, "%d pass(es), capped at %d" % (passes, CENSUS_PASSES))
    _rmtree(fp)

    # -- A2: provenance, on a scratch copy of the pin
    if pin:
        copy = scratch / "a2-pin"
        if copy.exists():
            _rmtree(copy)
        shutil.copytree(str(pin), str(copy))
        problems, classes, _n, _s = provenance(copy, repo, tip, scratch, require_wrapper=True)
        c.check("A2-PIN", "the pin as assembled", False, len(problems))
        manifest = json.loads((copy / MANIFEST).read_bytes().decode("utf-8"))

        def arm(cid, what, mutate):
            _rmtree(copy)
            shutil.copytree(str(pin), str(copy))
            mutate(copy, json.loads(json.dumps(manifest)))
            c.check(cid, what, True, len(provenance(copy, repo, tip, scratch,
                                                    require_wrapper=True)[0]))

        def extra_file(d, m):
            (d / "unexplained.txt").write_bytes(b"nothing\n")

        def first_of(m, cls):
            return next(e for e in m["files"] if e["class"] == cls)

        def sized(m, cls, empty):
            # the first entry of the class whose file in the pin is (empty=True) or is not
            # (empty=False) empty, else None
            for e in m["files"]:
                if e["class"] == cls and ((Path(pin) / e["file"]).stat().st_size == 0) == empty:
                    return e
            return None

        def alter(d, m, cls):
            # R13: one bit of the first file of the class that HAS a byte to move. A round
            # that changes no test file pins an EMPTY tests patch as the first GENERATED
            # file, which has no middle byte; an empty file is grow()'s case.
            f = d / sized(m, cls, False)["file"]
            data = bytearray(f.read_bytes())
            data[len(data) // 2] ^= 0x01
            f.write_bytes(bytes(data))

        def grow(d, m, cls):
            # R13: the first EMPTY file of the class given one byte -- its recipe produced
            # nothing, and the census must still compare the file with that nothing
            (d / sized(m, cls, True)["file"]).write_bytes(b"x")

        def sized_arm(cid, what, cls, empty, mutate):
            # an arm whose file the pin does not hold records a FAIL instead of raising,
            # so one missing file cannot take the rest of the block's controls with it
            if sized(manifest, cls, empty) is None:
                c.check(cid, what + " (the pin holds no such file, so the arm cannot run)",
                        True, 0)
            else:
                arm(cid, what, lambda d, m: mutate(d, m, cls))

        def write_manifest(d, m):
            (d / MANIFEST).write_bytes(json.dumps(m, indent=1).encode("utf-8"))

        def duplicate(d, m):
            m["files"].append(dict(first_of(m, "TYPED")))
            write_manifest(d, m)

        def unknown(d, m):
            first_of(m, "TYPED")["class"] = "TRUSTED"
            write_manifest(d, m)

        def drop_entry(d, m):
            m["files"].remove(first_of(m, "TYPED"))
            write_manifest(d, m)

        arm("A2-UNCLASSIFIED", "a file the manifest does not classify", extra_file)
        sized_arm("A2-TRACKED-ALTERED", "a TRACKED-COPY one bit away from its blob",
                  "TRACKED-COPY", False, alter)
        sized_arm("A2-GENERATED-ALTERED", "a GENERATED file one bit away from its recipe",
                  "GENERATED", False, alter)
        sized_arm("A2-GENERATED-EMPTY-ALTERED", "an empty GENERATED file given one byte",
                  "GENERATED", True, grow)
        arm("A2-TWO-CLASSES", "a file classified twice", duplicate)
        arm("A2-UNKNOWN-CLASS", "a class that is none of the three", unknown)
        arm("A2-NO-ENTRY", "a manifest entry removed", drop_entry)

        # R11-L1: the snapshot wrapper's gated copy
        def wrapper_entry(m):
            return next((e for e in m["files"] if e.get("path") == WRAPPER_GATED), None)

        def ungate(d, m):
            e = wrapper_entry(m)
            if e:
                e.pop("gated_from", None)
                write_manifest(d, m)

        def drop_wrapper(d, m):
            e = wrapper_entry(m)
            if e:
                m["files"].remove(e)
                (d / e["file"]).unlink()
                write_manifest(d, m)

        arm("A2-WRAPPER-UNGATED", "the wrapper's copy no longer names what it was gated from",
            ungate)
        arm("A2-WRAPPER-ABSENT", "the wrapper's gated copy removed with its entry",
            drop_wrapper)
        wsrc2 = wrapper_source(repo)
        if wsrc2 is None:
            c.check("A2-WRAPPER-DRIFT", "the repository copy one inert line away from what was "
                    "gated (the repository copy is not there, so the arm cannot run)", True, 0)
        else:
            drift = scratch / "a2-wrapper-drift"
            drift.write_bytes(wsrc2.read_bytes() + b"# scrctl\n")
            _rmtree(copy)
            shutil.copytree(str(pin), str(copy))
            c.check("A2-WRAPPER-DRIFT", "the repository copy one inert line away from what was "
                    "gated", True, len(provenance(copy, repo, tip, scratch, wrapper=str(drift),
                                                  require_wrapper=True)[0]))
            drift.unlink()

        # R10-H4: a recipe asks the pin commit's objects, bound to declared commits
        parent = _git(repo, ["rev-parse", "--verify", tip_sha + "^1"]).strip()

        def generated(m, kind):
            for e in m["files"]:
                r = e.get("recipe")
                if e.get("class") == "GENERATED" and (
                        (kind == "list" and isinstance(r, list)) or
                        (kind == "ls-tree" and isinstance(r, list) and r[:1] == ["ls-tree"]) or
                        (kind == "derive" and isinstance(r, dict))):
                    return e
            return None

        def recipe_arm(cid, what, kind, change):
            if generated(manifest, kind) is None:
                c.check(cid, what + " (the pin holds no such entry, so the arm cannot run)",
                        True, 0)
                return

            def mutate(d, m):
                change(generated(m, kind))
                write_manifest(d, m)
            arm(cid, what, mutate)

        recipe_arm("H4-RECIPE-INDEX", "a GENERATED file whose recipe asks the index (ls-files)",
                   "list", lambda e: e.update(recipe=["ls-files", "--", "tools/train_pin"]))
        recipe_arm("H4-RECIPE-OTHER-COMMIT", "a tree listing that answers about another "
                   "commit than the pin commit, declared as its input", "ls-tree",
                   lambda e: e.update(recipe=[parent if a == tip_sha else a
                                              for a in e["recipe"]],
                                      inputs=[{"commit": parent}]))
        recipe_arm("H4-DERIVATION-OTHER-COMMIT", "an ignore proof bound to another commit than "
                   "the pin commit", "derive",
                   lambda e: e.update(recipe=dict(e["recipe"], tip=parent),
                                      inputs=[{"commit": parent}]))
        _rmtree(copy)
        shutil.copytree(str(pin), str(copy))
        c.check("A2-RESTORED", "the copy restored from the pin", False,
                len(provenance(copy, repo, tip, scratch, require_wrapper=True)[0]))
        (copy / "planted.txt").write_bytes(("x %s x" % v["word"]).encode("utf-16-le"))
        t = Tally()
        for rel in _files_under(copy):
            scan_stream(_file_chunks(copy / rel), table, t, rel)
        c.check("A2-PLANTED-FILE", "a control needle in UTF-16LE in a file added to a copy",
                True, t.total)
        _rmtree(copy)

    # -- A2, the shape census -- over every file of every class since round 11
    # (R10-H1). The two round-10 rules that explain a shape are each controlled
    # in a small bundle of their own, beside a value the rule must not explain.
    if sidecar is not None:
        shape = _sibling("train_pin_scan")
        tiny = Path(scratch) / "shape-bundle"
        _rmtree(tiny)
        tiny.mkdir(parents=True)
        (tiny / "a.txt").write_bytes(b"a file whose sha256 the next file quotes\n")
        file_digest = _sha((tiny / "a.txt").read_bytes())
        own = {ns.digest(): "the census's own needle-list digest"}

        def shape_arm(cid, what, want_red, text):
            (tiny / "b.txt").write_bytes(text.encode("utf-8"))
            c.check(cid, what, want_red, _shape_hits(shape, tiny, sidecar, repo, own))

        shape_arm("A2-SHAPE-HEX", "a 64-hex value that is no file's sha256 and no declared "
                  "digest", True, "x %s x\n" % secrets.token_hex(32))
        shape_arm("A2-SHAPE-HEX-FILE-NEG", "negative: the sha256 of a file of the bundle",
                  False, "x %s x\n" % file_digest)
        shape_arm("A2-SHAPE-HEX-NEEDLES-NEG", "negative: the census's own needle-list digest",
                  False, "x %s x\n" % ns.digest())
        shape_arm("A2-SHAPE-HOST", "a resolvable dotted name nothing declares", True,
                  "see ctl" + secrets.token_hex(3) + ".io here\n")
        shape_arm("A2-SHAPE-HOST-NEG", "negative: a lane document name declared by value",
                  False, "see TRAIN-BUG392-MERGE-R10-NOTES" + ".md here\n")
        _rmtree(tiny)
    lines, failed = c.lines()
    return [ns.line(), "BOUND " + BOUND,
            "# Control needles are random values generated for this run; none is a real",
            "# value and none is printed. A3 plants only in a scratch clone that shares the",
            "# repository's objects read-only and is removed afterwards."] + lines, failed


# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# The census's own logs, written to a fixed point (R11-L5, round 12).
#
# The census reads every file of the pin, its own two logs included, so the log a
# pass writes changes what the next pass reads -- its byte totals first of all. Round
# 11 wrote the second pass's report and discarded the third, so the totals printed
# described files that no longer existed once the second report was written. The
# logs are now rewritten until a pass reproduces BOTH byte for byte: then every count
# the census log prints describes the files as they are, the two logs included. No
# pass number enters a log (it would change every pass); the command prints it.

CENSUS_PASSES = 8
CENSUS_LOGS = ("pin-census.log", "pin-path-scan.log")


def census_log(report, first_total, total):
    """The census log's bytes: the report, then the one line that names the fixed point."""
    return ("\n".join(list(report) + [
        "re-scanned with pin-census.log and pin-path-scan.log in place until a pass "
        "reproduced both byte for byte (every count above describes the files as they are, "
        "these two logs included): TOTAL %d -> %d" % (first_total, total)]) + "\n"
    ).encode("utf-8")


def census_fixed_point(pin, scan, first, cap=CENSUS_PASSES):
    """(log lines as written, total, passes). `scan()` is one census pass over the pin AS
    IT IS NOW: (report lines, total, shape text). `first` is the pass already run.

    Writes both logs, re-scans, and stops when a pass reproduces both byte for byte.
    When no pass within `cap` does, the last report is written with a REFUSED line and
    the total is at least 1."""
    pin = Path(pin)
    report, total, shape = first
    first_total = total
    body, shape_b = census_log(report, first_total, total), shape.encode("utf-8")
    passes = 1
    while True:
        (pin / CENSUS_LOGS[0]).write_bytes(body)
        (pin / CENSUS_LOGS[1]).write_bytes(shape_b)
        if passes >= cap:
            text = body.decode("utf-8").rstrip("\n").split("\n") + [
                "REFUSED: no pass within %d reproduced both logs; the counts above describe "
                "the files as the pass before the last write found them" % cap]
            (pin / CENSUS_LOGS[0]).write_bytes(("\n".join(text) + "\n").encode("utf-8"))
            return text, max(total, 1), passes
        report, total, shape = scan()
        passes += 1
        nb, ns_b = census_log(report, first_total, total), shape.encode("utf-8")
        if nb == body and ns_b == shape_b:
            return body.decode("utf-8").rstrip("\n").split("\n"), total, passes
        body, shape_b = nb, ns_b


def census_reproduced(pin, scan, first_total):
    """True when one more pass reproduces both written logs byte for byte."""
    pin = Path(pin)
    report, total, shape = scan()
    return (census_log(report, first_total, total) == (pin / CENSUS_LOGS[0]).read_bytes()
            and shape.encode("utf-8") == (pin / CENSUS_LOGS[1]).read_bytes())


def main(argv=None):
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument("command", choices=("describe", "files", "objects", "pin", "self-test"))
    ap.add_argument("paths", nargs="*")
    ap.add_argument("--seat")
    ap.add_argument("--sidecar", default=os.environ.get("SCR_PIN_NEEDLES"))
    ap.add_argument("--repo", default=str(ROOT))
    ap.add_argument("--tip")
    ap.add_argument("--not", dest="excludes", action="append", default=[])
    ap.add_argument("--scratch")
    ap.add_argument("--pin")
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--wrapper", help="the snapshot wrapper's repository copy (default: this "
                    "checkout's, else the main checkout's)")
    a = ap.parse_args(argv)
    try:
        ns = derive(a.seat, a.repo, a.sidecar)
        if a.command == "describe":
            print("\n".join(ns.describe()))
            return 0
        if a.command == "files":
            table = Table(ns.items)
            tally = Tally()
            for n, arg in enumerate(a.paths, 1):
                p = Path(arg)
                files = [p] if p.is_file() else [p / r for r in _files_under(p)]
                for f in files:
                    shown = "#%d:%s" % (n, f.name if p.is_file() else
                                        f.relative_to(p).as_posix())
                    if text_hits(f.name, table):
                        tally.finding("#%d:<a file name withheld>" % n, "file name", "raw",
                                      "utf-8")
                    scan_stream(_file_chunks(f), table, tally, shown)
            out = [ns.line()]
            _report(tally, table, out, "file(s)")
            out.append("TOTAL %d" % tally.total)
            print("\n".join(out))
            return 1 if tally.total else 0
        if not a.tip or not a.excludes:
            raise Refusal("--tip and at least one --not are required")
        if a.command == "objects":
            out, tally = object_census(a.repo, [a.tip], a.excludes, ns)
            print("\n".join(out))
            return 1 if tally.total else 0
        if a.command == "pin":
            pin = Path(a.paths[0]) if a.paths else None
            if not pin or not pin.is_dir():
                raise Refusal("name the pin directory")
            if not a.scratch:
                raise Refusal("--scratch names the directory the ignore proof is derived in")
            def scan():
                return pin_census(pin, a.repo, a.tip, a.excludes, ns, a.sidecar, a.scratch,
                                  a.wrapper)[:3]

            out, total, shape_text = scan()
            passes = 0
            if a.write:
                out, total, passes = census_fixed_point(pin, scan, (out, total, shape_text))
            print("\n".join(out))
            if a.write:
                print("CENSUS PASSES %d: %s" % (passes, "no fixed point" if out[-1].startswith(
                    "REFUSED") else "the last pass reproduced both logs byte for byte"))
            return 1 if total else 0
        if a.command == "self-test":
            if not a.scratch:
                raise Refusal("--scratch names the directory the controls may write in")
            lines, failed = self_test(a.scratch, a.repo, a.tip, a.excludes, ns, a.pin,
                                      a.sidecar)
            print("\n".join(lines))
            return 1 if failed else 0
    except Refusal as r:
        print("REFUSED: %s" % r)
        return 2
    return 2


if __name__ == "__main__":
    sys.exit(main())
