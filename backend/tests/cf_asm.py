"""Fixture machinery for the connect-failure server controls (DESIGN V11,
evidence sec8.1), used by test_ffa_assembly_pg.py.

One Env per case schema (cf_pg.case). It freezes the assembly clock
(main._asm_clock) and the monotonic clock main reads, so every threshold is
exact: "time t" means the frozen clock reads created_at + t, and Env.at()
shifts the lobby's own timestamps so that instant is the database's real now
(the closers' record fragment and the notice window compare with SQL NOW(),
so the two clocks must agree). The session check is a no-op unless a test
patches it.

Every route runs on its own session from Env.sm, a sessionmaker whose
sessions record, for the inert-twin comparison of cf_controls.py, each
statement's shape (verb, table, the columns it writes, its lock clause and
the transaction it commits in) and the relation locks held before each
COMMIT. Env.trace() writes those, the answers, the [FFA-ASM] lines and the
fixture's rows, normalised, to CF_TRACE_DIR when that is set.

Steam ids are fixture values from STEAM_BASE (765611900355xxxxx). As a
SteamID64 each decodes to high word 0x010FFFFF: account type 0, not type 1
(the individual type), so none is an individual account id by construction.
test_cf_fixture_steam_ids.py asserts that decode.
"""

import contextvars
import copy
import datetime as _dt
import functools
import decimal as _decimal
import io
import json
import os
import re
import sys
import time as _time
import types
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "api"))
sys.path.insert(0, HERE)

import main  # noqa: E402
from fastapi import HTTPException  # noqa: E402
from sqlalchemy import event, text  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker  # noqa: E402

STEAM_BASE = 76561190035500000
UTC = _dt.timezone.utc

# Fixture ids are derived, never random: a query that orders by a player
# or lobby id (the bet settlement orders by player_id::text) then walks the
# fixture's rows in the same order in every run, so two runs of the same
# code write the same trace (the twin rule).
_ID_NS = uuid.UUID("5c0f5e1e-2b1d-4c55-9a55-000000000355")


def fixture_uuid(kind, key):
    return uuid.uuid5(_ID_NS, "%s:%s" % (kind, key))


# The process memory main keeps between requests (TTL caches, last-seen
# and last-run memos), captured at import. Every case starts from it, so
# no statement depends on which cases ran earlier in the process or how
# long ago: the region volumes (a 600 s cache) and the service-account
# UUIDs (an hourly cache) each issue their query only when cold. A name
# that reads as a constant (upper case, a number) is configuration, not
# state, and is left alone. "state" covers the janitor arms' cadence
# dicts: the mail retention arm runs when time.monotonic() passes
# _MAIL_RETENTION_STATE["next"], so without it the arm ran in whichever
# case reached the janitor first in a process, and S36's statements
# depended on which rows shared the process. The rule adds exactly five
# names over the old one: that dict, _PC_STEAM_RENDER_STATE,
# _PC_STEAM_SWEEP_STATE, _triage_gc_state (a balanced depth counter) and
# the constant _ASM_SQLSTATE_STAGE, whose restore changes nothing.
_STATE_RE = re.compile(r"(?i)cache|seen|last|mono|prune|state")
_MAIN_STATE = {}
for _name, _val in list(vars(main).items()):
    if _name.startswith("__") or not _STATE_RE.search(_name):
        continue
    if isinstance(_val, bool) or not isinstance(_val, (dict, set, list, float, int, type(None))):
        continue
    if _name.lstrip("_").isupper() and not isinstance(_val, (dict, set, list)):
        continue
    _MAIN_STATE[_name] = copy.deepcopy(_val)

_LOCKS_SQL = (
    "SELECT l.locktype, COALESCE(c.relname, ''), l.mode FROM pg_locks l"
    "  LEFT JOIN pg_class c ON c.oid = l.relation"
    " WHERE l.pid = pg_backend_pid() AND l.granted"
    "   AND l.locktype IN ('relation', 'tuple', 'advisory')"
    "   AND COALESCE(c.relname, '') NOT LIKE 'pg\\_%'"
    # An index's AccessShareLock depends on the plan the planner chose,
    # which two runs of the same code need not share; tables, tuples and
    # advisory locks are what a twin must keep.
    "   AND COALESCE(c.relkind, 'r') NOT IN ('i', 'I')"
    " ORDER BY 1, 2, 3")

_REC = {"on": None}

# The lock probe's mark (A7-R4-A1, FIX-A7-R5-PROV): RecSession.commit sets it
# in the connection's info while the probe runs and removes it after, and the
# Recorder leaves out a statement only while its connection carries it. What
# identifies the probe is where it runs, never what its SQL says.
_PROBE_MARK = "cf_lock_probe"

# The buffer of the route call running in the current task (Env._call).
_OUT = contextvars.ContextVar("cf_out", default=None)


class _TaskStdout:
    """sys.stdout while an Env lives: a route call's prints go to the buffer
    its own task set, so two calls running at once (S63 (iv)) never swap each
    other's redirection, which contextlib.redirect_stdout would when they
    exit out of order; every other write goes to the stream it wraps."""

    def __init__(self, base):
        self.base = base

    def write(self, s):
        return (_OUT.get() or self.base).write(s)

    def flush(self):
        (_OUT.get() or self.base).flush()

    def __getattr__(self, k):
        return getattr(self.base, k)


class RecSession(AsyncSession):
    """A session that records the relation locks it holds before each
    COMMIT (the twin comparison's lock set)."""

    async def commit(self):
        rec = _REC["on"]
        if rec is not None and self.in_transaction():
            info = (await self.connection()).sync_connection.info
            info[_PROBE_MARK] = True
            try:
                rows = (await self.execute(text(_LOCKS_SQL))).all()
                rec.locks.append(sorted({(r[0], r[1], r[2]) for r in rows}))
            except Exception as exc:                   # pragma: no cover
                rec.locks.append([("error", type(exc).__name__, "")])
            finally:
                info.pop(_PROBE_MARK, None)
        await super().commit()


# -- The one SQL lexer (A7-R3, rule set completed under A7-R4-A1) ------------
#
# THE SCANNER REGION begins here and ends at the marker "end of the scanner
# region" below (A7-R5-A1 (2)(a)): it is the only code of this lane's test
# files that reads a statement's text. Everything after it reads the token
# model (code_tokens, statements, mentions, insert_parts, find_all, shape),
# and the generated sweep (cf_controls.py sweep, run by
# test_the_only_raw_sql_reader_is_the_scanner) proves it by operation.
#
# sql_tokens is PostgreSQL's own scanner, src/backend/parser/scan.l of
# REL_16_STABLE (the seats' and production's server is PostgreSQL 16), rule
# for rule, with flex's choice between rules: the longest match wins, and of
# two matches of one length the rule scan.l writes first. The number beside
# each rule is its line in scan.l (REL_16_STABLE, md5 1d86a8c3). NOTES.md
# "Round 5" lists every token class with its anchor and its disposition.
#
# scan.l's [\200-\377] admits every byte of a non-ASCII character in UTF-8
# (the server encoding), so in a str every character from U+0080 up is an
# identifier and dollar-tag character here.
_HI = "\u0080-\U0010ffff"
_ID = "[A-Za-z_%s][A-Za-z0-9_$%s]*" % (_HI, _HI)          # identifier       :346-349
_DQ = "[A-Za-z_%s][A-Za-z0-9_%s]*" % (_HI, _HI)           # dolq_start/_cont :299-300
_OPC = r"~!@#^&|`?+\-*/%<>="                              # op_chars         :381
_SPACE = " \t\n\r\f"                                      # space            :222
_HSPACE = " \t\f"                                         # horiz_space      :223
_NEWLINE = "\n\r"                                         # newline          :224
_DEC = r"[0-9](?:_?[0-9])*"                               # decinteger       :400
_NUM = r"(?:%s\.(?:%s)?|\.%s)" % (_DEC, _DEC, _DEC)       # numeric          :409
_REAL = r"(?:%s|%s)[Ee][-+]?%s" % (_DEC, _NUM, _DEC)      # real             :412

# The INITIAL state's rules, in scan.l's order (the tie-break).
_RULES = [(name, re.compile(pat)) for name, pat in (
    ("whitespace", r"[ \t\n\r\f]+|--[^\n\r]*"),           # :457, {space}+|{comment} :227-229
    ("xcstart", r"/\*[%s]*" % _OPC),                      # :461, :342
    ("xbstart", r"[bB]'"),                                # :501, :264
    ("xhstart", r"[xX]'"),                                # :519, :268
    ("xnstart", r"[nN]'"),                                # :533, :272
    ("xqstart", r"'"),                                    # :559, :286
    ("xestart", r"[eE]'"),                                # :569, :275
    ("xusstart", r"[uU]&'"),                              # :576, :318
    ("dolqdelim", r"\$(?:%s)?\$" % _DQ),                  # :758, :301
    ("dolqfailed", r"\$%s" % _DQ),                        # :764, :302
    ("xdstart", r'"'),                                    # :803, :309
    ("xuistart", r'[uU]&"'),                              # :808, :315
    ("xufailed", r"[uU]&"),                               # :841, :321
    ("typecast", r"::"),                                  # :853
    ("dot_dot", r"\.\."),                                 # :858
    ("colon_equals", r":="),                              # :863
    ("equals_greater", r"=>"),                            # :868
    ("less_equals", r"<="),                               # :873
    ("greater_equals", r">="),                            # :878
    ("less_greater", r"<>"),                              # :883
    ("not_equals", r"!="),                                # :889
    ("self", r"[,()\[\].;:+\-*/%^<>=]"),                  # :895, :380
    ("operator", r"[%s]+" % _OPC),                        # :900, :382
    ("param", r"\$[0-9]+"),                               # :1008, :416
    ("param_junk", r"\$[0-9]+" + _ID),                    # :1013, :438
    ("decinteger", _DEC),                                 # :1018
    ("hexinteger", r"0[xX](?:_?[0-9A-Fa-f])+"),           # :1022, :401
    ("octinteger", r"0[oO](?:_?[0-7])+"),                 # :1026, :402
    ("bininteger", r"0[bB](?:_?[01])+"),                  # :1030, :403
    ("hexfail", r"0[xX]_?"),                              # :1034, :405
    ("octfail", r"0[oO]_?"),                              # :1038, :406
    ("binfail", r"0[bB]_?"),                              # :1042, :407
    ("numeric", _NUM),                                    # :1046
    ("numericfail", _DEC + r"\.\."),                      # :1051, :410
    ("real", _REAL),                                      # :1057
    ("realfail", r"(?:%s|%s)[Ee][-+]" % (_DEC, _NUM)),    # :1062, :413
    ("integer_junk", _DEC + _ID),                         # :1066, :435
    ("numeric_junk", _NUM + _ID),                         # :1070, :436
    ("real_junk", _REAL + _ID),                           # :1074, :437
    ("identifier", _ID),                                  # :1080
    ("other", r"."),                                      # :1105 (flex's . : not \n)
)]
_KIND = {"typecast": "op", "dot_dot": "op", "colon_equals": "op", "equals_greater": "op",
         "less_equals": "op", "greater_equals": "op", "less_greater": "op",
         "not_equals": "op", "self": "op", "param": "param", "identifier": "ident",
         "other": "other"}
_DOLQ = re.compile(r"\$(?:%s)?\$" % _DQ)
_DOLQFAILED = re.compile(r"\$%s" % _DQ)


def _string_end(sql, i, state):
    """The end of a string constant whose opening quote is at sql[i - 1]
    (scan.l :588-756), in exclusive state xb, xh, xq, xe or xus, and its
    segments. A closing quote enters xqs (:588); there {quotecontinue}
    (:244, :600), a newline among horizontal whitespace and comments and then
    a quote, returns to the SAME state (so an E'' string keeps its escapes),
    and anything else ends the constant at the closing quote (:608-645).
    xqdouble (:287, :647) is a quote inside xq, xe and xus only: in xb and xh
    a second quote ends the constant. In xe a backslash and the character
    after it are one unit (xeescape :277, :720 and the longer escapes
    :278-281, whose extra characters are digits, never a quote)."""
    n = len(sql)
    segs, seg0, j = [], i - 1, i
    while True:
        while j < n:
            c = sql[j]
            if c == "\\" and state == "xe":
                j += 2
                continue
            if c == "'":
                if state in ("xq", "xe", "xus") and sql.startswith("''", j):
                    j += 2
                    continue
                break
            j += 1
        if j >= n:                       # unterminated (:756): the server refuses it
            segs.append(sql[seg0:n])
            return n, segs, False
        j += 1
        segs.append(sql[seg0:j])
        # xqs: {whitespace_with_newline}{quote} (:238-244)
        k = j
        while k < n:
            if sql[k] in _HSPACE:
                k += 1
            elif sql.startswith("--", k):
                k = _line_end(sql, k)
            else:
                break
        if k >= n or sql[k] not in _NEWLINE:
            return j, segs, True
        k += 1
        while k < n:                     # {special_whitespace}* (:238)
            if sql[k] in _SPACE:
                k += 1
            elif sql.startswith("--", k):
                e = _line_end(sql, k)
                if e >= n:
                    break
                k = e + 1
            else:
                break
        if k >= n or sql[k] != "'":
            return j, segs, True
        seg0, j = k, k + 1


def _line_end(sql, i):
    """The end of a `--` comment at i: the first CR or LF, or the end
    ({comment} is "--"{non_newline}*, :227, :225)."""
    ends = [e for e in (sql.find("\n", i), sql.find("\r", i)) if e >= 0]
    return min(ends) if ends else len(sql)


def _block_end(sql, i):
    """The end of a /* */ comment opened at i (:461-499), and whether it
    closed: nested openers count, `*`-runs followed by `/` close, an
    unterminated comment runs to the end (:470, the server refuses it)."""
    n, depth, j = len(sql), 0, i + 2
    while j < n:
        if sql.startswith("/*", j):
            depth += 1
            j += 2
        elif sql[j] == "*":
            k = j
            while k < n and sql[k] == "*":
                k += 1
            if k < n and sql[k] == "/":
                j = k + 1
                if depth <= 0:
                    return j, True
                depth -= 1
            else:
                j = k
        else:
            j += 1
    return n, False


def _operator_len(text):
    """{operator}'s action (:900-1006): stop before an embedded /* or --,
    then drop trailing + and - unless the operator holds one of ~!@#^&|`?%."""
    cut = [p for p in (text.find("/*"), text.find("--")) if p >= 0]
    n = min(cut) if cut else len(text)
    if n > 1 and text[n - 1] in "+-":
        if not any(c in "~!@#^&|`?%" for c in text[:n - 1]):
            while n > 1 and text[n - 1] in "+-":
                n -= 1
    return n


@functools.lru_cache(maxsize=None)
def sql_tokens(sql):
    """The one SQL tokenizer of these tests: PostgreSQL 16's scanner (see the
    table above). A tuple of (kind, text): "space" and "comment" (`--` to CR
    or LF, nested /* */), "string" (every string constant: '', E'', B'', X'',
    U&''; text is its segments byte for byte, a continued constant's segments
    joined by one newline, the separator PostgreSQL requires, so the text
    lexes again as the same constant), "dollar" (a $tag$ body, byte for byte),
    "qident" (a double-quoted or U&"" identifier), "ident", "number",
    "param", "op" and "other"; a string, dollar body, quoted identifier or
    block comment that reaches the end of the input unclosed is
    "unterminated string", "unterminated dollar", "unterminated qident" or
    "unterminated comment" (A7-R5-A1 (1)(b): the server refuses it, and the
    token model names it)."""
    out, i, n = [], 0, len(sql)
    while i < n:
        best, name = 0, None
        for rule, rx in _RULES:
            m = rx.match(sql, i)
            if m and m.end() - i > best:
                best, name = m.end() - i, rule
        text = sql[i:i + best]
        if name == "whitespace":
            out.append(("comment" if text.startswith("--") else "space", text))
            i += best
        elif name == "xcstart":
            e, closed = _block_end(sql, i)
            out.append(("comment" if closed else "unterminated comment", sql[i:e]))
            i = e
        elif name in ("xbstart", "xhstart", "xqstart", "xestart", "xusstart"):
            state = {"xbstart": "xb", "xhstart": "xh", "xqstart": "xq",
                     "xestart": "xe", "xusstart": "xus"}[name]
            q = i + best - 1                               # the opening quote
            e, segs, closed = _string_end(sql, q + 1, state)
            out.append(("string" if closed else "unterminated string", sql[i:q] + "\n".join(segs)))
            i = e
        elif name in ("xnstart", "xufailed", "dolqfailed"):
            out.append(("ident" if name != "dolqfailed" else "other", sql[i]))  # yyless(1)
            i += 1
        elif name == "dolqdelim":
            closed, j = False, i + best
            while j < n:
                k = sql.find("$", j)
                if k < 0:
                    j = n
                    break
                m = _DOLQ.match(sql, k)
                if m and m.group(0) == text:
                    j, closed = m.end(), True
                    break
                if m:
                    j = m.end() - 1                        # :788, the final $ again
                else:
                    m = _DOLQFAILED.match(sql, k)
                    j = m.end() if m else k + 1
            out.append(("dollar" if closed else "unterminated dollar", sql[i:j]))
            i = j
        elif name in ("xdstart", "xuistart"):
            j, closed = i + best, False
            while j < n:
                k = sql.find('"', j)
                if k < 0:
                    j = n
                    break
                if sql.startswith('""', k):
                    j = k + 2
                    continue
                j, closed = k + 1, True
                break
            out.append(("qident" if closed else "unterminated qident", sql[i:j]))
            i = j
        elif name == "operator":
            k = _operator_len(text)
            out.append(("op", text[:k]))
            i += k
        elif name == "numericfail":
            out.append(("number", text[:-2]))              # :1053, yyless(yyleng - 2)
            i += best - 2
        else:
            out.append((_KIND.get(name, "number"), text))
            i += best
    return tuple(out)


def sql_code(sql, *, mask_literals=False):
    """A statement as the server parses it, from sql_tokens: each run of
    whitespace and comments one space, the ends trimmed, every other token
    byte for byte. mask_literals=True writes each string constant and
    dollar-quoted body as '' (a quoted identifier stays), so a reader of the
    result never reads a literal's contents."""
    parts = []
    for kind, text in sql_tokens(sql):
        if kind in ("space", "comment"):
            if parts and parts[-1] != " ":
                parts.append(" ")
        elif mask_literals and kind in ("string", "dollar"):
            parts.append("''")
        else:
            parts.append(text)
    return "".join(parts).strip(" ")


def sql_split_top(code, sep=","):
    """sql_code output split at the token `sep` where parentheses are
    balanced (through sql_tokens, so a quoted comma or parenthesis never
    splits), each part stripped."""
    parts, cur, depth = [], [], 0
    for kind, text in sql_tokens(code):
        if kind == "op" and text == "(":
            depth += 1
        elif kind == "op" and text == ")":
            depth -= 1
        if kind == "op" and text == sep and depth == 0:
            parts.append("".join(cur).strip(" "))
            cur = []
        else:
            cur.append(" " if kind == "comment" else text)
    parts.append("".join(cur).strip(" "))
    return parts


# -- shape(): the recorder's reading of a statement, on the tokens -----------

def _truncate(name):
    """NAMEDATALEN - 1 = 63 bytes, cut at a character boundary
    (truncate_identifier, pg_mbcliplen)."""
    b = name.encode("utf-8", "surrogatepass")
    if len(b) <= 63:
        return name
    return b[:63].decode("utf-8", "ignore")


_ASCII_LOWER = str.maketrans("ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz")


# -- The token model (A7-R5-A1 (2)): what every reader consumes --------------
#
# A reader of SQL takes its decision from (kind, value) tokens of the one
# scanner, never from a statement's text. The value of an identifier is the
# name PostgreSQL resolves (A-Z folded to a-z only, as downcase_identifier
# does for UTF-8, cut to 63 bytes); of a quoted identifier its body with
# doubled quotes undoubled, cut to 63 bytes; of a string constant or dollar
# body its exact source text; of every other token its text. Comments and
# whitespace are not tokens of the model.
#
# THE BOUND (A7-R5-A1 (2)(b)): a form the model does not read exactly is
# never resolved approximately. The model raises Unmodelled naming it, and
# the assertion that reads the statement fails with that name: any U& token
# (identifier or string: no UESCAPE decoding, no surrogate pairs, no next
# form), the "other" token, an unterminated string, dollar body, quoted
# identifier or block comment, and a second statement after a `;` where one
# statement is read. The Recorder counts what it met (Recorder.unmodelled)
# and run_env asserts the count is 0 in the test itself.

class Unmodelled(Exception):
    """A form the token model does not read exactly: `form` names it."""

    def __init__(self, form, text=""):
        Exception.__init__(self, form, text[:120])
        self.form = form


def _model(sql):
    """The significant tokens of sql as (kind, value), checked against the
    bound (see above); `;` tokens included."""
    out = []
    for kind, text in sql_tokens(sql):
        if kind in ("space", "comment"):
            continue
        if kind.startswith("unterminated "):
            raise Unmodelled(kind, text)
        if kind == "other":
            raise Unmodelled("other", text)
        if kind in ("qident", "string") and text[:2] in ("U&", "u&"):
            raise Unmodelled("U& identifier" if kind == "qident" else "U& string", text)
        if kind == "ident":
            name = _truncate(text.translate(_ASCII_LOWER))
        elif kind == "qident":
            name = _truncate(text[1:-1].replace('""', '"'))
        else:
            name = text
        out.append((kind, name))
    return out


def statements(sql):
    """A script's statements, each a tuple of (kind, value) tokens, split at
    every `;` token (scan.l's self `;`); empty statements are dropped."""
    out, cur = [], []
    for tok in _model(sql):
        if tok == ("op", ";"):
            if cur:
                out.append(tuple(cur))
            cur = []
        else:
            cur.append(tok)
    if cur:
        out.append(tuple(cur))
    return out


def code_tokens(sql):
    """One statement's (kind, value) tokens: Unmodelled("multiple
    statements") when a `;` is followed by more code."""
    st = statements(sql)
    if len(st) > 1:
        raise Unmodelled("multiple statements", sql)
    return st[0] if st else ()


def name_of(tok):
    """A token's name: the value of an identifier or quoted identifier."""
    return tok[1] if tok[0] in ("ident", "qident") else None


def find_all(toks, pattern):
    """Every contiguous match of `pattern` in `toks`, as (start, captured):
    a pattern item (kind, value) matches a token of that kind and value; a
    value None matches any value of that kind (and is captured), a kind
    None any token."""
    out, m = [], len(pattern)
    for i in range(len(toks) - m + 1):
        cap = []
        for (pk, pv), tok in zip(pattern, toks[i:i + m]):
            if (pk is not None and tok[0] != pk) or (pv is not None and tok[1] != pv):
                break
            if pv is None:
                cap.append(tok)
        else:
            out.append((i, cap))
    return out


def split_depth0(toks, sep=("op", ",")):
    """toks split at `sep` where parentheses and brackets are balanced."""
    parts, cur, depth = [], [], 0
    for tok in toks:
        if tok in (("op", "("), ("op", "[")):
            depth += 1
        elif tok in (("op", ")"), ("op", "]")):
            depth -= 1
        if tok == sep and depth == 0:
            parts.append(tuple(cur))
            cur = []
        else:
            cur.append(tok)
    parts.append(tuple(cur))
    return parts


def _paren_end(toks, k):
    """The index of the `)` closing the `(` at toks[k]."""
    depth = 0
    for j in range(k, len(toks)):
        if toks[j] == ("op", "("):
            depth += 1
        elif toks[j] == ("op", ")"):
            depth -= 1
            if depth == 0:
                return j
    raise Unmodelled("unbalanced parentheses")


def insert_parts(toks):
    """INSERT INTO t [AS a] (columns) VALUES (row), ... read from code
    tokens: (table, [column names], [[value token tuples] per row]). Any
    other form (no column list, a SELECT or DEFAULT VALUES source, a column
    that is no single name) raises Unmodelled naming it."""
    if [t for t in toks[:2]] != [("ident", "insert"), ("ident", "into")]:
        raise Unmodelled("not INSERT INTO")
    table, k = _qualified([(t[0], t[1], name_of(t)) for t in toks], 2)
    if not table:
        raise Unmodelled("INSERT target")
    if k + 1 < len(toks) and toks[k] == ("ident", "as") and name_of(toks[k + 1]):
        k += 2
    if k >= len(toks) or toks[k] != ("op", "("):
        raise Unmodelled("INSERT without a column list")
    e = _paren_end(toks, k)
    cols = []
    for part in split_depth0(toks[k + 1:e]):
        if len(part) != 1 or name_of(part[0]) is None:
            raise Unmodelled("INSERT column", repr(part))
        cols.append(name_of(part[0]))
    k = e + 1
    if k >= len(toks) or toks[k] != ("ident", "values"):
        raise Unmodelled("INSERT source other than VALUES")
    rows, k = [], k + 1
    while k < len(toks) and toks[k] == ("op", "("):
        e = _paren_end(toks, k)
        rows.append(split_depth0(toks[k + 1:e]))
        k = e + 1
        if k < len(toks) and toks[k] == ("op", ","):
            k += 1
            continue
        break
    if not rows:
        raise Unmodelled("INSERT VALUES without a row")
    return table, cols, rows


def mentions(sql, name):
    """Whether sql (a statement, a script or a fragment) names `name`,
    read conservatively for a check that it must NOT: an identifier or
    quoted identifier whose value is `name`, or `name` inside any string
    constant, dollar body or comment, compared case-insensitively. Under the
    bound (above) plus one more form: an E'' string holding a backslash
    escape raises Unmodelled, since an escape can spell any character.
    A text holding neither `name` in any letter case, nor U& in any case,
    nor a backslash is False without being read: every token value of the
    model is a part of the text (an identifier folded A-Z only, a quoted
    identifier undoubled, strings, dollar bodies and comments exact), so
    only a U& or backslash escape can spell `name` without its letters; a
    route path or message is then no refusal (the S49 constants)."""
    low = name.lower()
    t = sql.lower()
    if low not in t and "u&" not in t and "\\" not in sql:
        return False
    statements(sql)                                 # the bound, by name
    for kind, text in sql_tokens(sql):
        if kind in ("ident", "qident") and name_of(_model(text)[0]) == name:
            return True
        if kind == "string" and text[:1] in "eE" and "\\" in text:
            raise Unmodelled("E'' escape", text)
        if kind in ("string", "dollar", "comment") and low in text.lower():
            return True
    return False


def _words(sql):
    """shape()'s words, from the token model: (kind, value, name)."""
    return [(k, v, name_of((k, v))) for k, v in code_tokens(sql)]


def _kw(w, *names):
    return w[0] == "ident" and w[2] in names


def _is_op(w, text):
    return w[0] == "op" and w[1] == text


def _qualified(ws, k):
    """The (possibly schema-qualified) relation name starting at ws[k], and
    the index after it; ("", k) when ws[k] is no name."""
    if k >= len(ws) or ws[k][2] is None:
        return "", k
    parts, k = [ws[k][2]], k + 1
    while k + 1 < len(ws) and _is_op(ws[k], ".") and ws[k + 1][2] is not None:
        parts.append(ws[k + 1][2])
        k += 2
    return ".".join(parts), k


def _first_from(ws):
    """The first name after an unquoted FROM anywhere in the statement (ONLY
    skipped), the table a SELECT's shape names."""
    for k, w in enumerate(ws):
        if _kw(w, "from"):
            j = k + 1
            if j < len(ws) and _kw(ws[j], "only"):
                j += 1
            name, _ = _qualified(ws, j)
            if name:
                return name
    return ""


def _depth0(ws, k, stop):
    """Indices from k up to the first unquoted keyword in `stop` at
    parenthesis depth 0 (or the end), with each index's depth."""
    out, depth = [], 0
    while k < len(ws):
        w = ws[k]
        if depth == 0 and w[0] == "ident" and w[2] in stop:
            break
        if _is_op(w, "(") or _is_op(w, "["):
            depth += 1
        elif _is_op(w, ")") or _is_op(w, "]"):
            depth -= 1
        out.append((k, depth))
        k += 1
    return out


def _set_columns(ws, k):
    """The column names an UPDATE's SET list assigns (`col = ...`,
    `col[i] = ...`, `col.f = ...` and `(a, b) = ...`), the list ending at
    FROM, WHERE or RETURNING at depth 0."""
    span = _depth0(ws, k, ("from", "where", "returning"))
    items, cur = [], []
    for idx, depth in span:
        if depth == 0 and _is_op(ws[idx], ","):
            items.append(cur)
            cur = []
        else:
            cur.append(idx)
    items.append(cur)
    cols = []
    for item in items:
        if not item:
            continue
        w = ws[item[0]]
        if _is_op(w, "("):
            for idx in item[1:]:
                if _is_op(ws[idx], ")"):
                    break
                if ws[idx][2] is not None:
                    cols.append(ws[idx][2])
        elif w[2] is not None:
            cols.append(w[2])
    return sorted(cols)


def shape(sql):
    """verb, table, written columns, lock clause: a statement's shape, read
    from the token model (comments are whitespace, literals are never read, a
    quoted identifier is a name and never a keyword; a form outside the model
    raises Unmodelled). A statement wrapped in
    a WITH list has the shape of the statement the list prefixes (the first
    SELECT, INSERT, UPDATE or DELETE at depth 0 after WITH), so a twin that
    moves a predicate into a named CTE "inside the same statement" (evidence
    section 8) leaves the shape unchanged. UPDATE [ONLY] t, INSERT INTO t and
    DELETE FROM [ONLY] t name t (schema-qualified names whole); any other
    verb names the first name after a FROM anywhere in the statement. The
    lock clause is the first FOR [NO KEY] UPDATE | FOR [KEY] SHARE, with a
    NOWAIT or SKIP LOCKED after it or after its OF list."""
    ws = _words(sql)
    main_k = 0
    if ws and _kw(ws[0], "with"):
        depth = 0
        for k in range(1, len(ws)):
            if _is_op(ws[k], "("):
                depth += 1
            elif _is_op(ws[k], ")"):
                depth -= 1
            elif depth == 0 and _kw(ws[k], "select", "insert", "update", "delete"):
                main_k = k
                break
    verb = ws[main_k][1].upper() if ws and ws[main_k][0] == "ident" else "?"
    table, cols = "", []
    k = main_k + 1
    if verb == "UPDATE":
        if k < len(ws) and _kw(ws[k], "only"):
            k += 1
        table, k = _qualified(ws, k)
        while k < len(ws) and not _kw(ws[k], "set"):
            k += 1
        cols = _set_columns(ws, k + 1) if k < len(ws) else []
    elif verb == "INSERT" and k < len(ws) and _kw(ws[k], "into"):
        table, k = _qualified(ws, k + 1)
        if k + 1 < len(ws) and _kw(ws[k], "as") and ws[k + 1][2] is not None:
            k += 2
        if (k + 1 < len(ws) and _is_op(ws[k], "(")
                and not _kw(ws[k + 1], "select", "values", "with", "table")):
            for idx in range(k + 1, len(ws)):
                if _is_op(ws[idx], ")"):
                    break
                if (ws[idx][2] is not None and idx + 1 < len(ws)
                        and (_is_op(ws[idx + 1], ",") or _is_op(ws[idx + 1], ")"))):
                    cols.append(ws[idx][2])
            cols = sorted(cols)
    elif verb == "DELETE" and k < len(ws) and _kw(ws[k], "from"):
        k += 1
        if k < len(ws) and _kw(ws[k], "only"):
            k += 1
        table, _ = _qualified(ws, k)
    else:
        table = _first_from(ws)
    lock = ""
    for k, w in enumerate(ws):
        if not _kw(w, "for"):
            continue
        rest = [x[2] if x[0] == "ident" else None for x in ws[k + 1:k + 4]]
        if rest[:1] == ["update"] or rest[:1] == ["share"]:
            words, j = ["FOR", rest[0].upper()], k + 2
        elif rest[:3] == ["no", "key", "update"]:
            words, j = ["FOR", "NO", "KEY", "UPDATE"], k + 4
        elif rest[:2] == ["key", "share"]:
            words, j = ["FOR", "KEY", "SHARE"], k + 3
        else:
            continue
        if j < len(ws) and _kw(ws[j], "of"):
            j += 1
            while j < len(ws):
                _, j2 = _qualified(ws, j)
                j = j2 if j2 > j else j + 1
                if j < len(ws) and _is_op(ws[j], ","):
                    j += 1
                    continue
                break
        if j < len(ws) and _kw(ws[j], "nowait"):
            words.append("NOWAIT")
        elif j + 1 < len(ws) and _kw(ws[j], "skip") and _kw(ws[j + 1], "locked"):
            words += ["SKIP", "LOCKED"]
        lock = " ".join(words)
        break
    return [verb, table, cols, lock]


# -- end of the scanner region ------------------------------------------------


class Recorder:
    def __init__(self):
        self.stmts = []
        self.locks = []
        self.txn = 0
        # A7-R5-A1 (2)(b): the forms of the recorded statements the token
        # model refused, by name; run_env asserts it stays empty.
        self.unmodelled = []

    def before(self, conn, cursor, statement, parameters, context, executemany):
        if conn.info.get(_PROBE_MARK):
            return
        try:
            row = shape(statement)
        except Unmodelled as exc:
            self.unmodelled.append(exc.form)
            row = ["UNMODELLED", exc.form, [], ""]
        self.stmts.append(row + [self.txn])

    def on_commit(self, conn):
        self.txn += 1
        self.stmts.append(["COMMIT", "", [], "", self.txn])

    def on_rollback(self, conn):
        self.txn += 1
        self.stmts.append(["ROLLBACK", "", [], "", self.txn])


class Answer:
    """A route's outcome as (status, body)."""

    def __init__(self, status, body):
        self.status = status
        self.body = body

    def __getitem__(self, k):
        # A body that is not a dict or a list (an error's detail string)
        # has no fields: None, so the test's own named assertion fails on
        # it instead of a TypeError inside the subscript.
        return self.body[k] if isinstance(self.body, (dict, list)) else None

    def get(self, k, d=None):
        return self.body.get(k, d) if isinstance(self.body, dict) else d

    def __repr__(self):
        return "Answer(%r, %r)" % (self.status, self.body)


class _NoHeaders(dict):
    def get(self, k, d=None):
        return d


class FakeRequest:
    """Only what the handlers read off a request once the session check is
    replaced (the ladder suite's own shape)."""
    headers = _NoHeaders()
    client = None
    url = "http://cf.test/"

    def __init__(self):
        self.state = types.SimpleNamespace()


class Lob:
    def __init__(self, lid, sids, pids, region, admission, gated):
        self.lid = lid
        self.sids = sids
        self.pids = pids
        self.region = region
        self.admission = admission
        self.gated = gated
        self.n = len(sids)

    def slot_of(self, pid):
        return self.pids.index(pid)


class Env:
    """The case's frozen clocks, route callers and second-session readers."""

    def __init__(self, c, sm, mp):
        self.c = c
        self.conn = c.conn
        self.engine = sm.kw["bind"]
        self.sm = async_sessionmaker(self.engine, expire_on_commit=False, class_=RecSession)
        self.mp = mp
        # Decision A7 made ADM_PRODUCTION_ENABLED True in main.py. Every case
        # here was written for the False position (its queue rows carry
        # ffa_adm1 by default, so the switch would turn every lock and re-form
        # into an admission lobby); the case pins it, never the module default
        # deciding. S57 sets each position itself.
        mp.setattr(main, "ADM_PRODUCTION_ENABLED", False)
        self.now = None
        # Far past process start, so _in_match_evidence_trustworthy() holds and
        # no young-process veto depends on when the test runs.
        self.mono = _time.monotonic() + 1000000.0
        self.lines = []
        self.answers = []
        self.serial = 0
        self.lobbies = []
        self.rec = Recorder()
        _REC["on"] = self.rec
        event.listen(self.engine.sync_engine, "before_cursor_execute", self.rec.before)
        event.listen(self.engine.sync_engine, "commit", self.rec.on_commit)
        event.listen(self.engine.sync_engine, "rollback", self.rec.on_rollback)
        mp.setattr(main, "_asm_clock", self._clock)
        proxy = types.SimpleNamespace(**{k: getattr(_time, k) for k in dir(_time)
                                         if not k.startswith("__")})
        proxy.monotonic = lambda: self.mono
        mp.setattr(main, "time", proxy)

        async def _no_session(request, steam_id, db):
            return None
        mp.setattr(main, "_check_steam_session", _no_session)
        # Reports are submitted unsigned (the ladder suite's `opened`): the
        # HMAC is not what these controls test.
        mp.setattr(main, "MATCH_HMAC_SECRET", "")
        # Presence is process memory keyed by steam id, and every case reuses
        # the same synthetic ids: each case starts with nobody online.
        mp.setattr(main, "_presence_seen", {})
        for name, val in _MAIN_STATE.items():
            mp.setattr(main, name, copy.deepcopy(val))
        mp.setattr(sys, "stdout", _TaskStdout(sys.stdout))

    def close(self):
        _REC["on"] = None
        for name, fn in (("before_cursor_execute", self.rec.before),
                         ("commit", self.rec.on_commit), ("rollback", self.rec.on_rollback)):
            try:
                event.remove(self.engine.sync_engine, name, fn)
            except Exception:                          # pragma: no cover
                pass

    async def _clock(self, db):
        if self.now is None:
            row = (await db.execute(text("SELECT clock_timestamp()"))).scalar()
            return row, self.mono
        return self.now, self.mono

    # -- the clock ------------------------------------------------------------

    async def _shift(self, lid, delta):
        """Move every timestamp of the lobby, its seat rows and its kept
        epochs by `delta` (the lobby's own history moves; nothing else)."""
        for table, key in (("ffa_lobbies", "id"), ("ffa_assembly_seats", "lobby_id"),
                           ("ffa_kept_epochs", "lobby_id"),
                           # The readmission tables (migration 378) are the
                           # lobby's history too; absent before it, skipped.
                           ("ffa_seat_readmissions", "lobby_id"),
                           ("ffa_readmit_attempts", "lobby_id"),
                           ("ffa_report_windows", "lobby_id"),
                           ("ffa_report_journal", "lobby_id")):
            cols = [r[0] for r in await self.conn.fetch(
                "SELECT column_name FROM information_schema.columns"
                " WHERE table_schema = current_schema() AND table_name = $1"
                "   AND data_type = 'timestamp with time zone' ORDER BY 1", table)]
            if not cols:
                continue
            sets = ", ".join("%s = %s + $2" % (c, c) for c in cols)
            await self.conn.execute("UPDATE %s SET %s WHERE %s = $1" % (table, sets, key),
                                    lid, delta)

    async def at(self, lob, t):
        """Freeze the clock at created_at + t, with that instant the real now."""
        real = await self.conn.fetchval("SELECT clock_timestamp()")
        old = await self.conn.fetchval("SELECT created_at FROM ffa_lobbies WHERE id = $1",
                                       lob.lid)
        new = real - _dt.timedelta(seconds=t)
        await self._shift(lob.lid, new - old)
        self.now = new + _dt.timedelta(seconds=t)
        return self.now

    async def ts(self, lob, t):
        """The absolute instant created_at + t (for seeding stamps)."""
        created = await self.conn.fetchval("SELECT created_at FROM ffa_lobbies WHERE id = $1",
                                           lob.lid)
        return created + _dt.timedelta(seconds=t)

    # -- fixtures -------------------------------------------------------------

    async def lobby(self, n=5, *, admission=False, gated=True, ranked=True, region="eu",
                    offered=None, t=0.0, joined=None, caps=None, host_slot=0,
                    queue=True, lease=True, games_played=0, player_count=None, lid=None):
        """An active locked lobby of n seats at lobby age t: players, the
        lobby row, ready_join queue rows (joined_at in `joined` order, default
        slot order), ffa leases, and one seat row per member with
        lock_offered_at set for the slots in `offered` (default every slot)."""
        self.serial += 1
        base = STEAM_BASE + self.serial * 20
        sids = [str(base + i) for i in range(n)]
        pids = []
        for i, sid in enumerate(sids):
            pids.append(await self.conn.fetchval(
                "INSERT INTO players (id, steam_id, display_name, mod_version)"
                " VALUES ($3, $1, $2, '1.41.0') RETURNING id", sid, "cf s%d-%d" % (self.serial, i),
                fixture_uuid("player", sid)))
        lid = lid if lid is not None else fixture_uuid("lobby", self.serial)
        room = "ffa_cf%06d" % self.serial
        await self.conn.execute(
            "INSERT INTO ffa_lobbies (id, status, photon_room_id, region, player_count,"
            "  member_ids, created_at, host_player_id, is_ranked, assembly_v1, admission_v1,"
            "  games_played)"
            " VALUES ($1, 'active', $2, $3, $4, $5, clock_timestamp() - make_interval(secs => $6),"
            "         $7, $8, $9, $10, $11)",
            lid, room, region, player_count if player_count is not None else n, pids, float(t),
            pids[host_slot], ranked, gated, admission and gated, games_played)
        order = joined if joined is not None else list(range(n))
        caps = caps if caps is not None else (["ffa_asm1,ffa_adm1"] * n)
        if queue:
            for rank, slot in enumerate(order):
                await self.conn.execute(
                    "INSERT INTO ffa_queue (player_id, steam_id, display_name, status, series_id,"
                    "  slot, room_name, room_region, matched_at, joined_at, last_polled, caps,"
                    "  mod_version)"
                    " VALUES ($1, $2, $3, 'ready_join', $4, $5, $6, $7, clock_timestamp(),"
                    "         clock_timestamp() - make_interval(secs => $8), clock_timestamp(),"
                    "         $9, '1.41.0')",
                    pids[slot], sids[slot], "cf s%d-%d" % (self.serial, slot), lid, slot, room,
                    region, float(600 - rank), caps[slot])
        if lease:
            async with self.sm() as db:
                await main._lease_acquire_many(db, list(pids), "ffa", lid,
                                               main.LEASE_TTL_ASSEMBLY)
                await db.commit()
        offered = set(range(n)) if offered is None else set(offered)
        for slot in range(n):
            await self.conn.execute(
                "INSERT INTO ffa_assembly_seats (lobby_id, player_id, slot, locked_at,"
                "  lock_offered_at)"
                " VALUES ($1, $2, $3, (SELECT created_at FROM ffa_lobbies WHERE id = $1),"
                "         CASE WHEN $4 THEN (SELECT created_at FROM ffa_lobbies WHERE id = $1)"
                "         END)", lid, pids[slot], slot, slot in offered)
        lob = Lob(lid, sids, pids, region, admission and gated, gated)
        self.lobbies.append(lob)
        await self.at(lob, t)
        return lob

    async def census_row(self, lob, slot, entries, *, t_at=None, seen=None, region=None,
                         game=0, anon=0, claim=None, bind=False):
        """Write a seat's census columns directly (a fixture's stored census):
        entries are (slot, actor, b, k). t_at is the lobby age of census_at
        (default now); seen that of census_seen_at (default t_at). claim is
        the seat's own actor claim; bind=True also binds it."""
        now_t = (self.now - await self.ts(lob, 0)).total_seconds()
        t_at = now_t if t_at is None else t_at
        seen = t_at if seen is None else seen
        region = region or lob.region
        cs = [e[0] for e in entries]
        ca = [e[1] for e in entries]
        cn = sorted({e[0] for e in entries if e[2] == 0})
        cu = sorted({e[0] for e in entries if e[3] == 0})
        await self.conn.execute(
            "UPDATE ffa_assembly_seats SET census_slots = $3, census_actors = $4,"
            "  census_nobody = $5, census_unkept = $6, census_anon = $7, census_region = $8,"
            "  census_game = $9, census_at = $10, census_seen_at = $11"
            " WHERE lobby_id = $1 AND slot = $2",
            lob.lid, slot, cs, ca, cn, cu, anon, region, game,
            await self.ts(lob, t_at), await self.ts(lob, seen))
        if claim is not None:
            await self.conn.execute(
                "UPDATE ffa_assembly_seats SET actor_claim = $3, claim_region = $4"
                " WHERE lobby_id = $1 AND slot = $2", lob.lid, slot, claim, region)
            if bind:
                await self.conn.execute(
                    "UPDATE ffa_assembly_seats SET actor_nr = $3, actor_region = $4"
                    " WHERE lobby_id = $1 AND slot = $2", lob.lid, slot, claim, region)

    async def ready_all(self, lob, slots, *, actor0=1, bodied=True, t_at=None):
        """Make `slots` READY: each bound to actor actor0 + slot with a fresh
        census listing every seat of `slots` (bodied unless bodied=False)."""
        entries = [(s, actor0 + s, 1 if bodied else 0, 1) for s in slots]
        for s in slots:
            await self.census_row(lob, s, entries, t_at=t_at, claim=actor0 + s, bind=True)
        if bodied:
            await self.conn.execute(
                "UPDATE ffa_assembly_seats SET body_seen_at = $3"
                " WHERE lobby_id = $1 AND slot = ANY($2::smallint[])",
                lob.lid, list(slots), self.now)

    async def set_seat(self, lob, slot, **cols):
        """Set seat columns; a float value for a *_at column is a lobby age."""
        sets, args = [], [lob.lid, slot]
        for k, v in cols.items():
            if k.endswith("_at") and isinstance(v, (int, float)) and not isinstance(v, bool):
                v = await self.ts(lob, v)
            args.append(v)
            sets.append("%s = $%d" % (k, len(args)))
        await self.conn.execute("UPDATE ffa_assembly_seats SET %s WHERE lobby_id = $1 AND slot = $2"
                                % ", ".join(sets), *args)

    async def set_lobby(self, lob, **cols):
        sets, args = [], [lob.lid]
        for k, v in cols.items():
            if k.endswith("_at") and isinstance(v, (int, float)) and not isinstance(v, bool):
                v = await self.ts(lob, v)
            args.append(v)
            sets.append("%s = $%d" % (k, len(args)))
        await self.conn.execute("UPDATE ffa_lobbies SET %s WHERE id = $1" % ", ".join(sets), *args)

    # -- readers (a second session) -------------------------------------------

    async def seat(self, lob, slot):
        r = await self.conn.fetchrow(
            "SELECT * FROM ffa_assembly_seats WHERE lobby_id = $1 AND slot = $2", lob.lid, slot)
        return dict(r) if r is not None else None

    async def seats(self, lob):
        return [dict(r) for r in await self.conn.fetch(
            "SELECT * FROM ffa_assembly_seats WHERE lobby_id = $1 ORDER BY slot", lob.lid)]

    async def lobby_row(self, lid):
        lid = lid.lid if isinstance(lid, Lob) else lid
        r = await self.conn.fetchrow("SELECT * FROM ffa_lobbies WHERE id = $1", lid)
        return dict(r) if r is not None else None

    async def queue_row(self, lob, slot):
        r = await self.conn.fetchrow("SELECT * FROM ffa_queue WHERE player_id = $1",
                                     lob.pids[slot])
        return dict(r) if r is not None else None

    async def lease(self, lob, slot):
        r = await self.conn.fetchrow("SELECT * FROM queue_leases WHERE player_id = $1",
                                     lob.pids[slot])
        return dict(r) if r is not None else None

    # -- route callers --------------------------------------------------------

    async def _call(self, coro_fn):
        buf = io.StringIO()
        tok = _OUT.set(buf)
        try:
            try:
                out = await coro_fn()
            except HTTPException as exc:
                out = Answer(exc.status_code, exc.detail)
        finally:
            _OUT.reset(tok)
            for line in buf.getvalue().splitlines():
                self.lines.append(line)
        if isinstance(out, Answer):
            ans = out
        elif hasattr(out, "status_code") and hasattr(out, "body"):
            ans = Answer(out.status_code, json.loads(bytes(out.body).decode("utf-8")))
        else:
            ans = Answer(200, out)
        self.answers.append(ans)
        return ans

    async def connect(self, lob, slot, step, **kw):
        kw.setdefault("client_ms", 100)
        req = main._AsmConnectReq(steam_id=lob.sids[slot], step=step, **kw)

        async def go():
            async with self.sm() as db:
                return await main.ffa_lobby_connect(lob.lid, req, None, db=db)
        return await self._call(go)

    def entry(self, lob, slot, actor, b=1, k=1, anon=False):
        return {"a": actor, "s": "" if anon else lob.sids[slot], "b": b, "k": k}

    async def assembly(self, lob, slot, actor, census, *, region=None, game=0,
                       seen_age_ms=None, epoch_seen=0, lobby_id=None):
        """census: a list of entry() dicts. seen_age_ms defaults to the
        server's age at receipt (the frozen clock)."""
        if seen_age_ms is None:
            seen_age_ms = int(round((self.now - await self.ts(lob, 0)).total_seconds() * 1000))
        req = main._AsmAssemblyReq(steam_id=lob.sids[slot], actor=actor,
                                   region=region or lob.region, game=game,
                                   seen_age_ms=seen_age_ms, epoch_seen=epoch_seen,
                                   census=census, client_ms=100)

        async def go():
            async with self.sm() as db:
                return await main.ffa_lobby_assembly(lobby_id or lob.lid, req, None, db=db)
        return await self._call(go)

    async def census_of(self, lob, slot, present, *, actor0=1, b=1, k=1, region=None,
                        game=0, seen_age_ms=None, actor=None):
        """An assembly POST from `slot` listing the seats of `present` with
        actor actor0 + seat (the ready_all numbering)."""
        entries = [self.entry(lob, s, actor0 + s, b=b, k=k) for s in present]
        return await self.assembly(lob, slot, actor if actor is not None else actor0 + slot,
                                   entries, region=region, game=game, seen_age_ms=seen_age_ms)

    async def release(self, lob, slot, why, *, lobby_id=None, steam_id=None):
        req = main._AsmReleaseReq(steam_id=steam_id or lob.sids[slot], why=why)

        async def go():
            async with self.sm() as db:
                return await main.ffa_lobby_release(lobby_id or lob.lid, req, None, db=db)
        return await self._call(go)

    async def leave(self, lob, slot, *, cause="", label="", expected=None, steam_id=None):
        exp = str(lob.lid) if expected is None else expected

        async def go():
            async with self.sm() as db:
                return await main.ffa_queue_leave(None, steam_id=steam_id or lob.sids[slot],
                                                  expected_lobby_id=exp, cause=cause,
                                                  label=label, db=db)
        return await self._call(go)

    async def poll(self, lob, slot, *, steam_id=None):
        async def go():
            async with self.sm() as db:
                return await main.ffa_queue_poll(steam_id or lob.sids[slot], None, db=db)
        return await self._call(go)

    async def verdict_direct(self, lob, trigger="assembly"):
        """_ffa_assembly_verdict called directly, in its own transaction under
        the lobby lock (deviation 12's function-level fixtures)."""
        async def go():
            async with self.sm() as db:
                ctx = await main._asm_ctx_slot(db, lob.lid, route=trigger, trigger=trigger)
                out = await main._ffa_assembly_verdict(ctx, trigger)
                await db.commit()
                ctx.emit()
                return out
        return await self._call(go)

    def asm_lines(self, needle=""):
        return [ln for ln in self.lines if ln.startswith("[FFA-ASM]") and needle in ln]

    # -- reports, bettors, wagers ---------------------------------------------

    async def report(self, lid, g, results, *, reporter=None, room=None, left=(),
                     absent=(), gp_leave=None, omit=()):
        """Submit game g of lobby `lid` unsigned. `results` maps steam id to
        (rounds, points) for the members it names (others 0, 0); slots are the
        lobby's member_ids order. `left`/`absent` name steam ids reported as
        early leavers / absent; gp_leave maps steam id to game_points_at_leave;
        `omit` names steam ids whose rows the report leaves out."""
        rep = await self.report_req(lid, g, results, reporter=reporter, room=room, left=left,
                                    absent=absent, gp_leave=gp_leave, omit=omit)
        return await self.submit(rep)

    async def report_req(self, lid, g, results, *, reporter=None, room=None, left=(),
                         absent=(), gp_leave=None, omit=()):
        """The report body report() submits, built from the second session;
        a caller that submits it from a concurrent task builds it first."""
        import schemas
        lid = lid.lid if isinstance(lid, Lob) else lid
        row = await self.lobby_row(lid)
        members = list(row["member_ids"])
        sid_of = {r["id"]: r["steam_id"] for r in await self.conn.fetch(
            "SELECT id, steam_id FROM players WHERE id = ANY($1::uuid[])", members)}
        gp_leave = gp_leave or {}
        entries = []
        for slot, pid in enumerate(members):
            sid = sid_of[pid]
            if sid in omit:
                continue
            rounds, points = results.get(sid, (0, 0))
            entries.append(schemas.FfaPlayerEntry(
                steam_id=sid, slot=slot, rounds_won=rounds, points_total=points,
                left_early=sid in left, absent=sid in absent,
                game_points_at_leave=gp_leave.get(sid)))
        winner = max(results, key=lambda s: (results[s][0], results[s][1]))
        return schemas.FfaMatchReport(
            lobby_id=str(lid), photon_room_id=room or "%s_r%d" % (row["photon_room_id"], g),
            winner_steam_id=winner, reported_by_steam_id=reporter or winner,
            is_ranked=bool(row["is_ranked"]), players=entries)

    async def submit(self, rep):
        """Submit a report body; touches only its own session."""
        async def go():
            async with self.sm() as db:
                out = await main.submit_ffa_match(rep, FakeRequest(), db)
                return out.model_dump() if hasattr(out, "model_dump") else out
        return await self._call(go)

    async def bettor(self, gold=5000):
        """A player outside every fixture lobby, holding `gold`."""
        self.serial += 1
        sid = str(STEAM_BASE + self.serial * 20 + 19)
        pid = await self.conn.fetchval(
            "INSERT INTO players (id, steam_id, display_name, mod_version, gold_earned)"
            " VALUES ($4, $1, $2, '1.41.0', $3) RETURNING id", sid, "cf bettor %d" % self.serial, gold,
            fixture_uuid("player", sid))
        return pid, sid

    async def wager(self, lid, bettor_pid, on_pid, *, game=1, amount=100, odds=2.5):
        """An unsettled ffa_bets row, inserted directly, with the stake moved
        the way the bet POST moves it (gold_spent and the ledger row), so a
        later refund finds the balance it returns."""
        lid = lid.lid if isinstance(lid, Lob) else lid
        await self.conn.execute(
            "UPDATE players SET gold_spent = COALESCE(gold_spent, 0) + $2 WHERE id = $1",
            bettor_pid, amount)
        await self.conn.execute(
            "INSERT INTO gold_transactions (player_id, amount, reason, reference_id, created_at)"
            " VALUES ($1, $2, 'ffa_bet_stake', $3, now())", bettor_pid, -amount, str(lid))
        return await self.conn.fetchval(
            "INSERT INTO ffa_bets (lobby_id, game_number, player_id, bet_on_player_id, amount,"
            "  odds_multiplier) VALUES ($1, $2, $3, $4, $5, $6) RETURNING id",
            lid, game, bettor_pid, on_pid, amount, odds)

    async def bets(self, lid):
        lid = lid.lid if isinstance(lid, Lob) else lid
        return [dict(r) for r in await self.conn.fetch(
            "SELECT * FROM ffa_bets WHERE lobby_id = $1 ORDER BY id", lid)]

    async def refunds(self, lid):
        lid = lid.lid if isinstance(lid, Lob) else lid
        return await self.conn.fetchval(
            "SELECT count(*) FROM gold_transactions WHERE reason = 'ffa_bet_refund'"
            "   AND reference_id = $1", str(lid))

    # -- the twin comparison's trace -------------------------------------------

    async def snapshot(self):
        """Every row of the fixture's lobbies (and lobbies re-formed from them),
        their seats, epochs, queue rows, leases and wagers."""
        lids = [lob.lid for lob in self.lobbies]
        lids += [r[0] for r in await self.conn.fetch(
            "SELECT id FROM ffa_lobbies WHERE reformed_from = ANY($1::uuid[])", lids)]
        pids = [p for lob in self.lobbies for p in lob.pids]
        out = {}
        for name, sql, arg in (
                ("lobbies", "SELECT * FROM ffa_lobbies WHERE id = ANY($1::uuid[])"
                            " ORDER BY created_at, id", lids),
                ("seats", "SELECT * FROM ffa_assembly_seats WHERE lobby_id = ANY($1::uuid[])"
                          " ORDER BY lobby_id, slot", lids),
                ("epochs", "SELECT * FROM ffa_kept_epochs WHERE lobby_id = ANY($1::uuid[])"
                           " ORDER BY lobby_id, epoch_no", lids),
                ("queue", "SELECT * FROM ffa_queue WHERE player_id = ANY($1::uuid[])"
                          " ORDER BY steam_id", pids),
                ("leases", "SELECT player_id, mode, group_id FROM queue_leases"
                           " WHERE player_id = ANY($1::uuid[]) ORDER BY player_id", pids),
                ("bets", "SELECT * FROM ffa_bets WHERE lobby_id = ANY($1::uuid[])"
                         " ORDER BY created_at, id", lids)):
            try:
                out[name] = [dict(r) for r in await self.conn.fetch(sql, arg)]
            except Exception as exc:                   # pragma: no cover
                out[name] = "error %s" % type(exc).__name__
        return out

    async def trace(self, name):
        """Write the normalised trace for cf_controls.py (CF_TRACE_DIR)."""
        d = os.environ.get("CF_TRACE_DIR")
        if not d:
            return None
        rows = await self.snapshot()
        # Names seeded from the fixture (lobby i is L{i}, its seat j L{i}P{j}),
        # so two runs name the same row the same way however the random
        # UUIDs happen to sort.
        seed = []
        for i, lob in enumerate(self.lobbies):
            seed.append((lob.lid, "L%d" % i))
            for j, p in enumerate(lob.pids):
                seed.append((p, "L%dP%d" % (i, j)))
        body = normalise({"statements": self.rec.stmts, "locks": self.rec.locks,
                          "answers": [[a.status, a.body] for a in self.answers],
                          "lines": _sort_runs([ln for ln in self.lines if ln.startswith("[FFA")]),
                          "rows": rows}, seed=seed)
        path = os.path.join(d, re.sub(r"[^A-Za-z0-9_.-]", "_", name) + ".json")
        with io.open(path, "w", encoding="ascii", newline="\n") as fh:
            fh.write(json.dumps(body, sort_keys=True, indent=1))
        return path


_UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
# No \b before the token: between a space and '-' there is no word boundary,
# so "\b->" never matched and every "-> {id8}" stayed raw.
_ID8_RE = re.compile(r"(?<![0-9A-Za-z_])(lobby|->) ([0-9a-f]{8})(?![0-9A-Za-z_])")
_ROOM_RE = re.compile(r"\bffa_[0-9a-f]{12}\b")
# Columns whose value is read from the real clock (SQL NOW()) rather than the
# frozen one. Compared to the second, they still split at a second's edge
# (dissolve_after_ms read 3703 and 3702 in two runs of one code), so they
# compare by presence, like the answer ages below.
_REAL_CLOCK_INTS = set()
# Answer fields computed from the route's monotonic clock at build time: two
# runs of the same code differ by scheduling, so a twin compares presence.
# xp_gained and gold_gained are the report's pay, metered by the pace
# ceiling against elapsed = clock_timestamp() - the lobby's anchor (the
# report handler's economy meter): a real-clock value against a fixture
# lobby created in the past, so the same code pays 11 or 12 by scheduling.
_REAL_CLOCK_MASK = {"server_age_ms", "admit_left_ms", "dissolve_after_ms",
                    "xp_gained", "gold_gained"}
# The erasure's random placeholder name (deleted_ + 8 hex): named by first
# appearance, like a UUID.
_PLACEHOLDER_RE = re.compile(r"\bdeleted_[0-9a-f]{8}\b")
# A timestamp a route formats into a string (an answer's expires_at, a
# log line's expires=) is SQL NOW() plus an interval, a real-clock value:
# compared by presence, like every datetime.
_ISO_TS_RE = re.compile(r"\b\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:[+-]\d{2}:\d{2}|Z)?")
# The deadline and slow-commit lines print the route's real elapsed time
# (_asm_elapsed_ms against the wall clock), which scheduling moves: the
# number compares by presence; the route, the stage and the line stay.
_ELAPSED_RE = re.compile(r"(?<![0-9A-Za-z_])(ms|pre_ms)=\d+")
_ELAPSED_LINE_RE = re.compile(r"^\[FFA-ASM\] lobby \S+ (?:deadline|slow_commit) route=")


def _line_template(ln):
    return re.sub(r"[0-9a-f]{8,}|[0-9]+", "#", _UUID_RE.sub("U", ln))


def _sort_runs(lines):
    """Each run of consecutive lines of one template (the same text once
    ids and numbers are masked) in a fixed order: one loop's lines over an
    unordered result (a DELETE ... RETURNING) keep their set, not the
    order the rows came back in."""
    out, i = [], 0
    while i < len(lines):
        t = _line_template(lines[i])
        j = i + 1
        while j < len(lines) and _line_template(lines[j]) == t:
            j += 1
        out.extend(sorted(lines[i:j], key=lambda s: _UUID_RE.sub("U", s)))
        i = j
    return out


def normalise(obj, seed=()):
    """UUIDs by the fixture's seeded names (seed: (uuid, name) pairs), any
    other UUID by first appearance; an 8-hex lobby prefix by the name of the
    seeded UUID it prefixes, else by first appearance; room names masked;
    timestamps to presence; real-clock integers to seconds, and the answer's
    real-clock ages to presence. A row table is walked in the order of its
    rows' masked form, never in the order the random ids sorted it."""
    names = {}
    for u, n in seed:
        names.setdefault(str(u), n)
    seeded = list(names.items())

    def uname(u):
        u = str(u)
        if u not in names:
            names[u] = "U%d" % len(names)
        return names[u]

    def id8name(h):
        for u, n in seeded:
            if u.startswith(h):
                return "I" + n
        return "I" + uname(h)

    def masked(o, key=None):
        """The sort key's form: seeded names kept, every other UUID blank."""
        if isinstance(o, dict):
            return {str(k): masked(v, k) for k, v in o.items()}
        if isinstance(o, (list, tuple)):
            return [masked(v) for v in o]
        if isinstance(o, uuid.UUID):
            return dict(seeded).get(str(o), "U?")
        if isinstance(o, (_dt.datetime, _dt.date)):
            return "ts"
        if isinstance(o, str):
            sd = dict(seeded)
            return _ISO_TS_RE.sub("ts", _PLACEHOLDER_RE.sub(
                "deleted_?", _UUID_RE.sub(lambda m: sd.get(m.group(0), "U?"), o)))
        if key in _REAL_CLOCK_MASK or key in _REAL_CLOCK_INTS:
            return "rt"
        if isinstance(o, (bytes, bytearray, _decimal.Decimal, float)):
            return str(o)
        return o

    def walk(o, key=None):
        if isinstance(o, dict):
            if key == "rows":
                return {str(k): walk(sorted(v, key=lambda r: json.dumps(
                    masked(r), sort_keys=True, default=str)) if isinstance(v, list) else v, k)
                    for k, v in sorted(o.items(), key=lambda kv: str(kv[0]))}
            return {str(k): walk(v, k) for k, v in sorted(o.items(), key=lambda kv: str(kv[0]))}
        if isinstance(o, (list, tuple)):
            return [walk(v) for v in o]
        if isinstance(o, uuid.UUID):
            return uname(o)
        if isinstance(o, (_dt.datetime, _dt.date)):
            return "ts"
        if isinstance(o, str):
            s = _UUID_RE.sub(lambda m: uname(m.group(0)), o)
            s = _ID8_RE.sub(lambda m: "%s %s" % (m.group(1), id8name(m.group(2))), s)
            s = _ROOM_RE.sub("ffa_ROOM", s)
            s = _PLACEHOLDER_RE.sub(lambda m: "deleted_" + uname("ph:" + m.group(0)), s)
            s = _ISO_TS_RE.sub("ts", s)
            if _ELAPSED_LINE_RE.match(s):
                s = _ELAPSED_RE.sub(lambda m: m.group(1) + "=rt", s)
            return s
        if key in _REAL_CLOCK_MASK and isinstance(o, int):
            return "rt"
        if key in _REAL_CLOCK_INTS and isinstance(o, int):
            return round(o / 1000.0)
        if isinstance(o, float):
            return round(o, 6)
        if isinstance(o, _decimal.Decimal):
            return "dec %s" % o
        if isinstance(o, (bytes, bytearray)):
            return "bytes"
        return o
    return walk(obj)
