"""The FAQ's FFA early-leave entry: what the game says, what the server does,
and the keys migration 396 registers for it.

Four places in the client explained the FFA early-leave grace by the rule as
it stood before migration 386's server change: a leaver was graced only
while the field had scored fewer than 2 half points AND the leaver's own
tally was still zero. The server now graces a seat that leaves before the
field has scored FFA_LEAVE_GRACE_FULL_POINTS x FFA_POINTS_TO_WIN_ROUND half
points in total (backend/api/main.py, _ffa_leave_grace_half_points), whatever
its own tally (in _ffa_leave_decision own points only bound the claim: at or
above the threshold, or above the claimed field total, they refute it). Such
a seat joins `unrated` (rating, game XP and game Gold), while the FFA
achievement evaluation reads `excluded`, which grace does not enter. The four
sites now say so:

  * InfoLibrary ModeFfaExt (the FFA article),
  * InfoLibrary Rewards (the economy article),
  * InfoLibrary WhenCounts (the rule book),
  * ModeInfoText Ffa (the FFA mode text).

Each is a translation key (the catalogue key IS the English), so each new
English is held here to the registry, the generated allowlist and all four
bundled locales; each locale's text to its own words for the threshold; and
migration 396 to the same strings: its key rows to what
tools/i18n_sync_keys.build_client_keys derives from the registry, its seeds to
the bundled catalogue values, and the four keys it retires to the ones 386
registered, derived from 386's own text (an earlier wording of the grace, as
"two full points"). Source-reading only:
no database, no game, no dotnet; test_migration_reruns.py runs 396.
"""
import hashlib
import importlib.util
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import test_faq_client_ladder as ladder  # noqa: E402  (its readers and catalogue parser)

ROOT = Path(__file__).resolve().parents[2]
PLUGIN = ROOT / "plugin"
INFO = PLUGIN / "InfoLibrary.cs"
MODE = PLUGIN / "ModeInfoText.cs"
FFA_MODE = PLUGIN / "FfaMode.cs"
REGISTRY = ROOT / "tools" / "i18n_source.json"
SOURCE_KEYS = PLUGIN / "I18nSourceKeys.g.cs"
MAIN = ROOT / "backend" / "api" / "main.py"
SQL = ROOT / "backend" / "sql"
M386 = SQL / "386_ffa_leave_grace_texts.sql"
M396 = SQL / "396_faq_early_leave_keys.sql"
R396 = SQL / "rollback_396_faq_early_leave_keys.sql"

# site: (source file, the declaration the string opens with, the rule as that
# string states it). The three articles state it on one whole line; the mode
# text wraps it inside its verbatim literal, so it is matched as written.
SITES = {
    "FFA article": (INFO, 'private static string ModeFfaExt => I18n.Tr(@"',
                    "- <color=#7FE87F>Early-leave grace:</color> leave a game before the field has "
                    "scored four half points in total, whether or not any became a full point, and "
                    "that game is unrated for you - no rating change, no game Gold or XP. "
                    "Achievements can still be earned and pay as usual, but an unrated game earns no "
                    "title-ladder progress. Any later leave counts in full: leaving early doesn't dodge "
                    "the loss."),
    "economy article": (INFO, 'private static string Rewards => I18n.Tr(@"',
                        "- Ghosts and graced early leavers are unrated and receive no game Gold or XP "
                        "from that game: leaving before the field scored four half points in total, "
                        "whether or not any became a full point, takes you out of those results. A "
                        "graced leaver can still earn achievements, which pay as usual, but an unrated "
                        "game earns no title-ladder progress."),
    "rule book": (INFO, 'private static string WhenCounts => I18n.Tr(@"',
                  "- FFA early-leave grace: a leaver who left before the field had scored four half "
                  "points in total, whether or not any became a full point, is unrated for that game "
                  "and receives no game Gold or XP from it. Achievements can still be earned and pay "
                  "as usual, but an unrated game earns no title-ladder progress."),
    "FFA mode text": (MODE, 'public static string Ffa => I18n.TrF(@"',
                      "  left - unless they left before the field had scored\n"
                      "  four half points in total, whether or not any became\n"
                      "  a full point, in which case that game does not rate\n"
                      "  them or pay them game Gold or XP. Achievements can\n"
                      "  still be earned and pay as usual, but an unrated game\n"
                      "  earns no title-ladder progress."),
}
WHOLE_LINE = ("FFA article", "economy article", "rule book")

# The threshold in each language's own words, as each site states it once.
THRESHOLD_WORDS = {4: "four"}
LOCALE_THRESHOLD = {"ES": "cuatro medios puntos", "RU": "четыре полуочка",
                    "UK": "чотири половинки", "SV": "fyra halvpoäng"}

# The pre-386 rule's own-tally condition, as each language stated it at one
# or more of the four sites before this change: it may survive nowhere.
PREDECESSORS = {
    "EN": ("while your own tally (points, half points, kills) is still zero",
           "with a zero tally of their own",
           "while their own tally was still zero"),
    "ES": ("con tu propio recuento (puntos, medios puntos, kills) aún a cero",
           "con su propio recuento aún a",
           "con recuento propio a cero"),
    "RU": ("пока твой собственный счёт (очки, полуочки, убийства) ещё нулевой",
           "при собственном нулевом счёте",
           "при собственном нулевом"),
    "UK": ("поки ваш власний рахунок (очки, половинки, вбивства) ще нульовий",
           "поки власний рахунок був ще",
           "з власним нульовим рахунком"),
    "SV": ("medan din egen räkning (poäng, halvpoäng, kills) fortfarande är noll",
           "medan deras egen räkning fortfarande",
           "med en egen nollräkning"),
}

LANGS = ("es", "ru", "sv", "uk")


def _load_tool(name):
    spec = importlib.util.spec_from_file_location("scr_tools_%s" % name, ROOT / "tools" / ("%s.py" % name))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def site_sources():
    """{site: English} read out of each site's own verbatim literal."""
    out = {}
    for site, (path, decl, _rule) in SITES.items():
        src = ladder._read(path)
        assert src.count(decl) == 1, "%s: %r occurs %d times in %s" % (
            site, decl, src.count(decl), path.name)
        out[site] = ladder._verbatim_after(src, src.index(decl) + len(decl))
    return out


def _registry():
    return json.loads(ladder._read(REGISTRY))


def _allowlist():
    allow = [ladder._cs_literal(m) for m in re.findall(
        r'^\s*"((?:[^"\\]|\\.)*)",\s*$', ladder._read(SOURCE_KEYS), re.M)]
    assert len(allow) > 1000, "only %d allowlist keys parsed" % len(allow)
    return allow


_SQL_PART = re.compile(r"'((?:[^']|'')*)'|chr\((\d+)\)")
_SQL_JOIN = re.compile(r"\s*\|\|\s*")


def _sql_literals(line):
    """The string values of one VALUES row, in order and decoded. 396 writes
    each as ONE plain '' literal (quotes doubled), joined only by
    || chr(10) || for a line break and || chr(183) || for a middle dot: no
    E'' string and no two literals side by side (the land tool's data-only
    check refuses both)."""
    out, i = [], 0
    while True:
        m = _SQL_PART.search(line, i)
        if m is None:
            return out
        assert line[m.start() - 1:m.start()] not in ("E", "e"), "an E'' literal: %s" % line[:80]
        buf = []
        while True:
            if m.group(1) is not None:
                buf.append(m.group(1).replace("''", "'"))
            else:
                assert m.group(2) in ("10", "183"), "chr(%s) joined into a text" % m.group(2)
                buf.append(chr(int(m.group(2))))
            j = _SQL_JOIN.match(line, m.end())
            nxt = _SQL_PART.match(line, j.end()) if j else None
            if nxt is None:
                break
            m = nxt
        assert not re.match(r"\s*'", line[m.end():]), "two literals side by side: %s" % line[:80]
        out.append("".join(buf))
        i = m.end()


def _block(lines, start, end):
    """The lines strictly between the one line equal to `start` and the next
    line equal to `end` (both compared stripped)."""
    at = [i for i, line in enumerate(lines) if line.strip() == start]
    assert len(at) == 1, (start, at)
    stop = next(i for i in range(at[0] + 1, len(lines)) if lines[i].strip() == end)
    return lines[at[0] + 1:stop]


def m396_rows():
    """396's four key rows {key_id: (namespace, msgctxt, source_hash,
    context)} with each row's sensitive flag, and its sixteen seeds
    {(key_id, lang): (source_hash, target)}."""
    lines = ladder._read(M396).split("\n")
    keys, sensitive = {}, {}
    for line in _block(lines, "FROM (VALUES", ") AS v(key_id, namespace, msgctxt, source_hash, sensitive, context)"):
        lit = _sql_literals(line)
        assert len(lit) == 5, (len(lit), line[:80])
        flag = re.search(r"', (TRUE|FALSE), CAST\('", line)
        assert flag, line[:80]
        keys[lit[0]] = (lit[1], lit[2], lit[3], lit[4])
        sensitive[lit[0]] = flag.group(1) == "TRUE"
    seeds = {}
    for line in _block(lines, "INSERT INTO _seed396 (key_id, lang, source_hash, target) VALUES", ";"):
        if line.strip().startswith("--"):
            continue
        lit = _sql_literals(line)
        assert len(lit) == 4, (len(lit), line[:80])
        assert (lit[0], lit[1]) not in seeds, line[:80]
        seeds[(lit[0], lit[1])] = (lit[2], lit[3])
    return keys, sensitive, seeds


def m386_texts():
    """{key_id: English} for the four client keys 386 registers, read from
    its dollar-quoted VALUES, each with the hash 386 writes for it."""
    body = ladder._read(M386)
    rows = re.findall(r"\('([0-9a-f]{16})', 'client', \$k386\$(.*?)\$k386\$, '([0-9a-f]{40})', (?:TRUE|FALSE)\)",
                      body, re.S)
    assert len(rows) == 4, len(rows)
    out = {}
    for key_id, text, source_hash in rows:
        assert hashlib.sha1(text.encode("utf-8")).hexdigest() == source_hash, key_id
        out[key_id] = text
    return out


def _client_key_id(english):
    return hashlib.sha1(("client\0" + english).encode("utf-8")).hexdigest()[:16]


def _ids_in(text):
    return set(re.findall(r"'([0-9a-f]{16})'", text))


def test_the_rule_the_sites_state_is_the_rule_the_server_applies():
    """The threshold the sites state is the one the server computes, in the
    unit the client reports: FFA_LEAVE_GRACE_FULL_POINTS full points of
    FFA_POINTS_TO_WIN_ROUND half points each, and the client's own
    FfaMode.PointsToWinRound is the server's. A graced seat joins `unrated`,
    which the rating and the game XP and Gold read, while the achievement
    candidates are every reported seat outside `excluded`, which grace does
    not enter: what "can still be earned" says."""
    main = ladder._read(MAIN)
    full = re.findall(r"^FFA_LEAVE_GRACE_FULL_POINTS = (\d+)$", main, re.M)
    per = re.findall(r"^FFA_POINTS_TO_WIN_ROUND = (\d+)$", main, re.M)
    assert len(full) == 1 and len(per) == 1, (full, per)
    assert main.count("    return FFA_LEAVE_GRACE_FULL_POINTS * points_to_win_round\n") == 1
    client = re.findall(r"public const int PointsToWinRound = (\d+);", ladder._read(FFA_MODE))
    assert client == per, "FfaMode.PointsToWinRound %s, the server's %s" % (client, per)
    threshold = int(full[0]) * int(per[0])
    assert threshold in THRESHOLD_WORDS, (
        "the server's grace threshold is %d half points; the four sites say %s"
        % (threshold, " or ".join(THRESHOLD_WORDS.values())))
    phrase = "%s half points in total, whether or not any became" % THRESHOLD_WORDS[threshold]
    for site, (_path, _decl, rule) in SITES.items():
        assert " ".join(rule.split()).count(phrase) == 1, (site, phrase)
    assert main.count("    unrated = excluded | graced\n") == 1
    assert len(re.findall(r"_ach_players = sorted\(\s*\(p for p in report\.players "
                          r"if p\.steam_id not in excluded\)", main)) == 1


def test_the_grace_set_is_read_only_by_unrated_and_the_reasons():
    """What "achievements can still be earned and pay as usual" rests on in
    the route: inside submit_ffa_match the code lines naming `graced` are
    exactly three, the decision that returns it, the exclusion reasons that
    record it, and `unrated = excluded | graced`; no other line of the route
    reads it."""
    src = ladder._read(MAIN)
    start = src.index("async def submit_ffa_match(")
    nxt = re.compile(r"^(?:@|async def |def |class )", re.M).search(src, start + 10)
    body = src[start:nxt.start()]
    lines = [line.strip() for line in body.split("\n")
             if re.search(r"\bgraced\b", line) and not line.strip().startswith("#")]
    assert lines == [
        "ghosts, graced, _leave_log = _ffa_leave_decision(",
        '| ({"grace"} if p.steam_id in graced else set())',
        "unrated = excluded | graced",
    ], lines


def test_each_site_states_the_rule_exactly_once():
    """Each site carries its sentence once: the three articles as one whole
    line, the mode text as its wrapped lines."""
    sources = site_sources()
    for site, (_path, _decl, rule) in SITES.items():
        assert sources[site].count(rule) == 1, "%s carries its rule %d times" % (
            site, sources[site].count(rule))
        if site in WHOLE_LINE:
            assert sources[site].split("\n").count(rule) == 1, "not a whole line of the %s" % site


def test_no_predecessor_survives_in_any_artifact_the_game_renders_from():
    """The pre-386 own-tally condition, in English or any bundled locale,
    survives in no plugin source outside the catalogue, no registry string,
    no allowlist key, and no catalogue entry under a registered key, in its
    key or its value. The catalogue also keeps entries under English no
    source passes to I18n any more (earlier revisions of articles, among
    them the rule book's 304838dece8548b7, which still carries the old
    rule); those sit under no registered key, and the check reads
    registered keys only, so it leaves them out."""
    plugin = {p.name: ladder._read(p) for p in sorted(PLUGIN.glob("*.cs"))
              if p.name != ladder.CATS.name}
    assert len(plugin) > 50, sorted(plugin)
    registry = _registry()["strings"]
    registered = set(registry)
    allow = _allowlist()
    cats = ladder.catalogues()
    for fragment in PREDECESSORS["EN"]:
        assert not [n for n, src in plugin.items() if fragment in src], fragment
        assert not [s for s in registry if fragment in s], fragment
        assert not [s for s in allow if fragment in s], fragment
    for lang, (table, _counts) in cats.items():
        for fragment in PREDECESSORS["EN"] + PREDECESSORS[lang]:
            live = [k for k, v in table.items()
                    if k in registered and (fragment in k or fragment in v)]
            assert not live, (lang, fragment, [k[:60] for k in live])
    for key_id, english in m386_texts().items():
        assert english not in registry and english not in allow, key_id
        assert not [n for n, src in plugin.items() if english in src.replace("\r\n", "\n")], key_id
        for lang, (table, _counts) in cats.items():
            assert english not in table, (lang, key_id)


def test_each_site_is_the_registered_key_in_every_bundled_locale():
    """One registry string, one allowlist entry, and one translated entry
    under exactly that English in ES, RU, UK and SV, which states the
    threshold in that language's own words as often as the English does."""
    sources = site_sources()
    registry = _registry()["strings"]
    allow = _allowlist()
    cats = ladder.catalogues()
    for site, english in sources.items():
        assert registry.count(english) == 1, (site, registry.count(english))
        assert allow.count(english) == 1, (site, allow.count(english))
        times = " ".join(english.split()).count("four half points in total")
        assert times == 1, (site, times)
        for lang, (table, counts) in cats.items():
            assert counts.get(english, 0) == 1, (site, lang, counts.get(english, 0))
            value = table[english]
            assert value.strip() and value != english, (site, lang)
            flat = " ".join(value.split())
            assert flat.count(LOCALE_THRESHOLD[lang]) == times, (
                "%s: the %s entry states %r %d times; the English states the threshold %d times"
                % (site, lang, LOCALE_THRESHOLD[lang], flat.count(LOCALE_THRESHOLD[lang]), times))


def test_396_registers_exactly_the_keys_the_next_sync_derives():
    """396's four key rows are what tools/i18n_sync_keys.build_client_keys
    derives from the regenerated registry for the four sites' English: the
    same key_id, namespace, source text, hash, sensitivity and context, so
    the migration and the next key sync write the same row. Its post-check
    expects the md5 of exactly that text."""
    sources = site_sources()
    keys, sensitive, _seeds = m396_rows()
    synced = {r["msgctxt"]: r for r in _load_tool("i18n_sync_keys").build_client_keys(_registry())}
    assert sorted(keys[k][1] for k in keys) == sorted(sources.values()), sorted(keys)
    for key_id, (namespace, english, source_hash, context) in keys.items():
        rec = synced[english]
        assert (rec["key_id"], rec["namespace"], rec["source_hash"], rec["sensitive"], rec.get("context")) == (
            key_id, namespace, source_hash, sensitive[key_id], context), (key_id, rec)
        assert key_id == _client_key_id(english)
    sql = ladder._read(M396)
    for key_id, (_ns, english, source_hash, _ctx) in keys.items():
        md5 = hashlib.md5(english.encode("utf-8")).hexdigest()
        assert sql.count("('%s', '%s', '%s', " % (key_id, source_hash, md5)) == 1, key_id


def test_396_header_maps_each_new_key_to_the_386_key_of_its_site():
    """396's header lists each new key with its site, as "<file stem>
    <member>" in full, and the 386 key it replaces. The four labels are
    exactly the four sites' labels, each new id is the one derived from that
    site's English, and each 386 id is the 386 key whose English is the
    closest of the four to that site's (the earlier wording of the same
    string), one to one."""
    import difflib
    header = ladder._read(M396).split("BEGIN;")[0]
    rows = re.findall(r"^--   ([0-9a-f]{16}) ([A-Za-z ]+?), replacing 386's ([0-9a-f]{16})[;.]$", header, re.M)
    assert len(rows) == 4, rows
    labels = {}
    for s, (path, decl, _r) in SITES.items():
        member = re.findall(r" (\w+) => ", decl)
        assert len(member) == 1, (s, decl)
        labels["%s %s" % (Path(path).stem, member[0])] = s
    assert len(labels) == 4 and sorted(label for _n, label, _o in rows) == sorted(labels), (rows, sorted(labels))
    sources, old = site_sources(), m386_texts()
    assert len({o for _n, _s, o in rows}) == 4 and {o for _n, _s, o in rows} == set(old), rows
    for new_id, label, old_id in rows:
        english = sources[labels[label]]
        assert new_id == _client_key_id(english), (label, new_id)
        closest = max(old, key=lambda k: difflib.SequenceMatcher(None, old[k], english).ratio())
        assert closest == old_id, (label, old_id, closest)


def test_396_seeds_are_the_bundled_drafts():
    """The sixteen seeds are the four keys in es, ru, sv and uk, each at its
    key's source hash and each the text the bundled catalogue renders for
    that English, and the post-check expects the md5 of exactly that text."""
    keys, _sensitive, seeds = m396_rows()
    cats = ladder.catalogues()
    assert sorted(seeds) == sorted((k, lang) for k in keys for lang in LANGS), sorted(seeds)
    sql = ladder._read(M396)
    for (key_id, lang), (source_hash, target) in seeds.items():
        english = keys[key_id][1]
        assert source_hash == keys[key_id][2], (key_id, lang)
        assert target == cats[lang.upper()][0][english], (
            "the %s seed of %s is not the bundled %s draft" % (lang, key_id, lang.upper()))
        md5 = hashlib.md5(target.encode("utf-8")).hexdigest()
        assert sql.count("('%s', '%s', '%s')" % (key_id, lang, md5)) == 1, (key_id, lang)


def test_396_and_its_rollback_retire_and_revive_exactly_386s_keys():
    """The keys 396 retires and its rollback makes live again are the four
    386 registered, whose ids derive from 386's own English; every other id
    either file names is one of 396's four, which derive from the sites'
    English."""
    old = m386_texts()
    for key_id, english in old.items():
        assert key_id == _client_key_id(english), key_id
    new = {_client_key_id(english) for english in site_sources().values()}
    assert len(new) == 4 and not new & set(old)
    for path in (M396, R396):
        assert _ids_in(ladder._read(path)) == new | set(old), (
            path.name, sorted(_ids_in(ladder._read(path)) ^ (new | set(old))))
    rollback = ladder._read(R396)
    retire_new = re.search(r"SET retired_at = NOW\(\), updated_at = NOW\(\)\s+"
                           r"WHERE namespace = 'client'\s+AND key_id IN \(([^)]*)\)", rollback)
    revive_old = re.search(r"SET retired_at = NULL, updated_at = NOW\(\)\s+"
                           r"WHERE namespace = 'client'\s+AND key_id IN \(([^)]*)\)", rollback)
    assert retire_new and _ids_in(retire_new.group(1)) == new, retire_new
    assert revive_old and _ids_in(revive_old.group(1)) == set(old), revive_old


_TOKEN = re.compile(r"""
    (?P<ws>[ \t\n]+)
  | (?P<comment>--[^\n]*)
  | (?P<lit>'(?:''|[^'])*')
  | (?P<tag>\$m396\$)
  | (?P<ident>[A-Za-z_][A-Za-z0-9_]*)
  | (?P<int>[0-9]+)
  | (?P<op>\|\||<>|>=|<=|[=<>*.,;()])
""", re.X)
# The five VALUES lists of 396, by the alias (or table) and the columns that name them, and the production each
# column's cell takes: "lit" a plain literal; "text" a value (a literal or a composed value); "bool" TRUE or FALSE;
# "cast" the context cast.
_VALUES_SHAPES = {
    ("x", ("key_id", "source_hash")): ("lit", "lit"),
    ("v", ("key_id", "namespace", "msgctxt", "source_hash", "sensitive", "context")):
        ("lit", "lit", "text", "lit", "bool", "cast"),
    ("x", ("key_id", "source_hash", "text_md5", "sensitive", "context")): ("lit", "lit", "lit", "bool", "text"),
    ("_seed396", ("key_id", "lang", "source_hash", "target")): ("lit", "lit", "lit", "text"),
    ("x", ("key_id", "lang", "text_md5")): ("lit", "lit", "lit"),
}
_JOINS = (["chr", "(", "10", ")"], ["chr", "(", "183", ")"])
# The reviewed text of 396 outside its VALUES rows: the file with line ends normalised to LF and each row, from its
# opening to its closing parenthesis, replaced by "(ROW)" (_outside_rows). Reviewed in FAQ-R13.
_OUTSIDE_SHA256 = "582c3991e3dfb30d31a11843c6d23f3052f4f33551c214aa8ebee7d5460a4421"
_OUTSIDE_LINES = 272


def _line(sql, pos):
    """'396 line N', N the 1-based line of 396 that holds offset `pos`."""
    return "396 line %d" % (sql.count("\n", 0, pos) + 1)


def _tokens(sql):
    """The (kind, text, offset) tokens of `sql` (396) other than whitespace
    and comments. Fails on a byte that no _TOKEN rule admits, on a literal
    that opens after anything but whitespace, "(" or "," (so a literal
    carries no E, U&, N, B or X prefix), and on a literal holding a
    backslash or a character below U+0020; each message opens with
    "396 line N: ", N the line of the failing byte or literal (_line), and
    the two literal failures also quote the literal."""
    out, i = [], 0
    while i < len(sql):
        m = _TOKEN.match(sql, i)
        assert m, "%s: a byte no token rule admits: %r" % (_line(sql, i), sql[max(0, i - 20):i + 20])
        kind, text = m.lastgroup, m.group()
        if kind == "lit":
            assert i > 0 and sql[i - 1] in " \t\n(,", "%s: a literal opens after %r: %r" % (_line(sql, i), sql[i - 1], text[:60])
            body = text[1:-1]
            assert all(ch >= " " and ch != "\\" for ch in body), (
                "%s: a literal holds a control character or a backslash: %r" % (_line(sql, i), text[:60]))
        if kind not in ("ws", "comment"):
            out.append((kind, text, i))
        i = m.end()
    return out


class _M396Parse:
    """396's VALUES lists parsed by these productions:
        literal  := a _tokens literal (plain, single-quoted, the doubled quote its only escape, no backslash and no
                    character below U+0020)
        value    := literal | composed
        composed := literal ( "||" join ( "||" join )* "||" literal )+
        join     := chr "(" ( 10 | 183 ) ")"
        cast     := CAST "(" value AS VARCHAR "(" 160 ")" ")"
        row      := "(" cell ( "," cell )* ")"   each cell the production its column takes (_VALUES_SHAPES)
    parse() fails on a cell no production admits, on a list whose alias
    and columns _VALUES_SHAPES does not name, and on a row whose cells do
    not match that shape. Every failure of parse() and of the _tokens call
    it makes opens with "396 line N: ", N the 1-based line of the failing
    token, byte or literal; a literal _tokens refuses is also quoted.
    `spans` holds each row's offsets, from its opening to its closing
    parenthesis."""

    def __init__(self, sql):
        self.sql, self.toks = sql, _tokens(sql)
        self.lists, self.spans = [], []

    def t(self, n):
        return self.toks[n][1] if 0 <= n < len(self.toks) else ""

    def k(self, n):
        return self.toks[n][0] if 0 <= n < len(self.toks) else ""

    def at(self, n):
        return _line(self.sql, self.toks[n][2] if 0 <= n < len(self.toks) else len(self.sql))

    def expect(self, n, *texts):
        bad = [k for k, want in enumerate(texts) if self.t(n + k) != want]
        assert not bad, "%s: %r stands where %r must" % (self.at(n + bad[0]), self.t(n + bad[0]), texts[bad[0]])
        return n + len(texts)

    def value(self, n):
        assert self.k(n) == "lit", "%s: a value opens with %r, not a literal" % (self.at(n), self.t(n))
        n, kind = n + 1, "lit"
        while self.t(n) == "||":
            joins = 0
            while self.t(n) == "||" and [self.t(k) for k in range(n + 1, n + 5)] in _JOINS:
                n, joins = n + 5, joins + 1
            assert joins, "%s: %r stands after || where chr(10) or chr(183) must" % (self.at(n + 1), self.t(n + 1))
            bad = n if self.t(n) != "||" else n + 1
            assert self.t(n) == "||" and self.k(n + 1) == "lit", (
                "%s: a composed value continues with %r, not || and a literal" % (self.at(bad), self.t(bad)))
            n, kind = n + 2, "text"
        return kind, n

    def cell(self, n):
        if self.k(n) == "lit":
            return self.value(n)
        if self.t(n) in ("TRUE", "FALSE"):
            return "bool", n + 1
        if self.t(n) == "CAST":
            _kind, n = self.value(self.expect(n, "CAST", "("))
            return "cast", self.expect(n, "AS", "VARCHAR", "(", "160", ")", ")")
        raise AssertionError("%s: %r stands where a value, TRUE, FALSE or the context cast must" % (self.at(n), self.t(n)))

    def header(self, alias_at, col_at, close_at):
        """The shape the list header names (the alias token, the column tokens, the token closing the column list).
        Fails at the first header token no _VALUES_SHAPES key admits: the alias, the first column no named list has
        at that place, a column beyond every named list's last, or the closing parenthesis where a column is missing."""
        alias, cols = self.t(alias_at), [self.t(k) for k in col_at]
        keys = [key for key in _VALUES_SHAPES if key[0] == alias]
        assert keys, "%s: %r is the alias of no named VALUES list" % (self.at(alias_at), alias)
        for i, col in enumerate(cols):
            keys = [key for key in keys if len(key[1]) > i and key[1][i] == col]
            assert keys, "%s: column %r stands where no named %s list has it" % (self.at(col_at[i]), col, alias)
        keys = [key for key in keys if len(key[1]) == len(cols)]
        assert keys, "%s: the %s column list closes before its last column" % (self.at(close_at), alias)
        return keys[0], _VALUES_SHAPES[keys[0]]

    def values(self, v):
        n, rows = v + 1, []
        while True:
            row, n, cells = n, self.expect(n, "("), []
            while True:
                at = n
                kind, n = self.cell(n)
                cells.append((kind, at))
                if self.t(n) != ",":
                    break
                n += 1
            n = self.expect(n, ")")
            rows.append((cells, n - 1))
            self.spans.append((self.toks[row][2], self.toks[n - 1][2] + 1))
            if self.t(n) != ",":
                break
            n += 1
        if self.t(v - 1) == "(":
            n = self.expect(n, ")", "AS")
            alias_at, n = n, self.expect(n + 1, "(")
            col_at = []
            while self.t(n) != ")":
                assert n < len(self.toks), "%s: a VALUES alias's column list does not close" % self.at(n)
                col_at.append(n)
                n += 2 if self.t(n + 1) == "," else 1
            close_at = n
        else:
            self.expect(n, ";")
            close = v - 1
            assert self.t(close) == ")", "%s: VALUES follows %r" % (self.at(close), self.t(close))
            opens = [k for k in range(close) if self.t(k) == "("]
            assert opens, "%s: no column list opens before VALUES" % self.at(close)
            opn = opens[-1]
            want = ["INSERT", "INTO", "_seed396"]
            bad = [k for k in range(3) if self.t(opn - 3 + k) != want[k]]
            assert not bad, "%s: %r stands where INSERT INTO _seed396 must open the column list" % (
                self.at(opn - 3 + bad[0]), self.t(opn - 3 + bad[0]))
            alias_at, col_at, close_at = opn - 1, list(range(opn + 1, close, 2)), close
        key, shape = self.header(alias_at, col_at, close_at)
        for cells, close_row in rows:
            for i, (got, at) in enumerate(cells[:len(shape)]):
                want = shape[i]
                assert got == want or (want == "text" and got == "lit"), (
                    "%s: column %s of %r takes %s, not %s" % (self.at(at), key[1][i], key, want, got))
            assert len(cells) <= len(shape), "%s: a cell beyond the %d of %r" % (self.at(cells[len(shape)][1]), len(shape), key)
            assert len(cells) == len(shape), "%s: a row of %d cells closes under %r" % (self.at(close_row), len(cells), key)
        self.lists.append((key, len(rows)))

    def parse(self):
        for n in range(len(self.toks)):
            if self.t(n) == "VALUES":
                self.values(n)
        return self


def _m396_parse():
    sql = M396.read_bytes().decode("utf-8").replace("\r\n", "\n")
    return _M396Parse(sql).parse()


def _outside_rows(p):
    """396's text with each VALUES row (p.spans) replaced by "(ROW)"."""
    out, at = [], 0
    for a, b in p.spans:
        out.append(p.sql[at:a])
        out.append("(ROW)")
        at = b
    out.append(p.sql[at:])
    return "".join(out)


def test_396_rows_parse_by_the_productions_and_the_text_outside_them_is_the_reviewed_text():
    """Two of 396's format guarantees. (1) Each of its five VALUES lists
    parses by the productions of _M396Parse. (2) Its text outside the VALUES
    rows, line ends normalised, is the reviewed text: its sha256 and line
    count equal the pins above, so a change outside the rows fails this
    test. The third, what 396 stores, is
    test_migration_reruns.py::test_396_stores_the_texts_its_values_read_and_the_client_bundles."""
    p = _m396_parse()
    assert sorted(key for key, _rows in p.lists) == sorted(_VALUES_SHAPES), p.lists
    outside = _outside_rows(p)
    assert (hashlib.sha256(outside.encode("utf-8")).hexdigest(), outside.count("\n") + 1) == (
        _OUTSIDE_SHA256, _OUTSIDE_LINES), "396 changed outside its VALUES rows"


def _g14_cases(sql):
    """(name, text, line): 396 with one planted change, and the line of the
    token, byte or literal it plants, which parse() must name; then 396 cut
    at offsets across the file, whose line is that of the literal the cut
    opens (when it falls inside one) or of the cut itself."""
    lines = sql.split("\n")

    def plant(line, old, new):
        assert lines[line - 1].count(old) == 1, (line, old)
        out = list(lines)
        out[line - 1] = out[line - 1].replace(old, new)
        return "\n".join(out)

    seed = [i + 1 for i, l in enumerate(lines) if re.match(r"\s+INSERT INTO _seed396 ", l)][0]
    k71 = "' || chr(10) || chr(10) || '- Confirming"
    cases = [
        ("byte", plant(71, k71, "' || chr(10) || chr(10) ` || '- Confirming"), 71),
        ("literal prefix", plant(71, k71, "' || E'x' || '- Confirming"), 71),
        ("literal control", plant(71, k71, "\n\n- Confirming"), 71),
        ("cell kind", plant(57, "('892845f20501fbc0',", "(x,"), 57),
        ("join", plant(71, k71, "' || repeat('-', 2) || '- Confirming"), 71),
        ("composed continues", plant(71, k71, "' || chr(10) || chr(10) ||\nCAST '- Confirming"), 72),
        ("cell", plant(57, "'84324a21d4105a936ec63ce3a5d72bdf7e5986b8'", "TRUE"), 57),
        ("cast split", plant(71, "AS VARCHAR(160))", "AS VARCHAR(\n161))"), 72),
        ("cell beyond", plant(57, "'84324a21d4105a936ec63ce3a5d72bdf7e5986b8')", "'84324a21d4105a936ec63ce3a5d72bdf7e5986b8', 'x')"), 57),
        ("cell missing", plant(57, ", '84324a21d4105a936ec63ce3a5d72bdf7e5986b8')", "\n)"), 58),
        ("alias", plant(61, "AS x(key_id, source_hash)", "AS y(key_id, source_hash)"), 61),
        ("column", plant(61, "AS x(key_id, source_hash)", "AS x(key_id,\nhash)"), 62),
        ("columns close", plant(61, "AS x(key_id, source_hash)", "AS x(key_id\n)"), 62),
        ("insert header", plant(seed, "INSERT INTO _seed396 ", "INSERT INTO _seedx "), seed),
        ("values follows", plant(seed, ") VALUES", ") x VALUES"), seed),
        ("cast value", plant(71, "CAST('InfoLibrary ' || chr(183)", "CAST(x || chr(183)"), 71),
    ]
    spans = [(o, o + len(x)) for k, x, o in _tokens(sql) if k == "lit"]
    for cut in range(2500, len(sql), 1700):
        inside = [o for o, e in spans if o < cut < e]
        cases.append(("cut %d" % cut, sql[:cut], sql.count("\n", 0, inside[0] if inside else cut) + 1))
    return cases


def test_396_parse_failures_name_the_planted_line():
    """G14's enforcement: for each _g14_cases case, parse() fails with an
    AssertionError whose message opens with "396 line N: ", N the case's
    line; a cut may instead pass (one that leaves each VALUES list it
    reaches whole), a planted case may not."""
    sql = M396.read_bytes().decode("utf-8").replace("\r\n", "\n")
    bad = []
    for name, text, line in _g14_cases(sql):
        try:
            _M396Parse(text).parse()
            if not name.startswith("cut "):
                bad.append((name, "passed"))
        except AssertionError as e:
            if not str(e).startswith("396 line %d: " % line):
                bad.append((name, line, str(e)[:80]))
    assert not bad, bad


def test_396_writes_no_middle_dot_and_eight_chr_183_joins():
    """No middle-dot character is in 396, and its tokens hold exactly eight
    runs of chr ( 183 )."""
    sql = M396.read_bytes().decode("utf-8").replace("\r\n", "\n")
    assert "·" not in sql
    toks = [x for _k, x, _o in _tokens(sql)]
    assert sum(1 for n in range(len(toks) - 3) if toks[n:n + 4] == ["chr", "(", "183", ")"]) == 8
