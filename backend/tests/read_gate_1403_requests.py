"""Verified reads, bar BV-A: the per-call request list of the RELEASED v1.40.3
client, derived from the tag's own source (`git show v1.40.3:plugin/*.cs`),
with the headers each call really carries.

Exhaustiveness is proved by two closures, both computed here and pinned by
test_read_gate_trunk_oracle.test_1403_request_list_is_exhaustive:

  (1) every request SITE (a call of a transport function or of one of the
      three wrappers, or a request constructor) is resolved to an /api/v1 URL
      expression, or is one of the pinned non-API sites below (the transports'
      own internals, the GitHub/off-API fetches, a Photon event);
  (2) every code line of the tag that contains "/api/v1" is consumed by a
      resolved site, or is one of the pinned non-request lines (URL
      predicates, a self-test's literal URLs) or the chat socket.

The only request constructors in the tag are UnityWebRequest.Get/Delete and
`new UnityWebRequest(` (counted by `constructor_counts`); every API call goes
through the eight functions that hold them. Other HTTP mechanisms in the tag
(WebClient, HttpWebRequest) fetch GitHub release assets only; the chat socket
is a ClientWebSocket.

Headers, from the tag's transports: every call through GetRequest,
PostRequest, PostRequestWithRetry, SendRequest and DoDelete is stamped by
StampVersionHeader with `X-Mod-Version: 1.40.3` and, when a session is held,
`X-Session-Token`; PostRequest and PostRequestWithRetry always send
`Content-Type: application/json`, SendRequest only with a body; the 1v1 queue
poll adds `X-Region-Pings`. The boot probe stamps the same pair; the version
check (DoCheckModVersion) sends NO version header; the release-notes overlay
sends `X-Mod-Version` alone. The client sends no X-Locale.
"""
from __future__ import annotations

import re
import subprocess

TAG = "v1.40.3"
VERSION = "1.40.3"

# Transport functions and wrappers: (name, method, index of the URL argument)
TRANSPORTS = {
    "GetRequest": ("GET", 0), "SessionGet": ("GET", 0),
    "PostRequest": ("POST", 0), "PostRequestWithRetry": ("POST", 0), "SessionPost": ("POST", 0),
    "SendRequest": (None, 1), "SessionSend": (None, 1), "DoDelete": ("DELETE", 0),
    # wrappers whose own URL parameter reaches PostRequest / GetRequest
    "SendLivePoints": ("POST", 1), "FetchCompareBoard": ("GET", 1),
    "EnqueueFailedReport": ("POST", 0),
}
_CALL = re.compile(r"\b(" + "|".join(sorted(TRANSPORTS, key=len, reverse=True)) + r")\s*\(")
_CTOR = re.compile(r"UnityWebRequest\.(Get|Delete|Post|Put|Head)\s*\(|new UnityWebRequest\s*\(")
_DEF = re.compile(r"\b(private|public|internal)\s+static\s+[\w<>\[\], ]+\s+(\w+)\s*\(")

# Sites that are not API calls, by (file, enclosing function, called
# function). Each is a transport's or wrapper's own call on its URL
# parameter, an off-API fetch, or a Photon event that shares a name. Every
# key must match at least one site (test_1403_request_list_is_exhaustive).
NON_API_SITES = {
    ("plugin/ApiClient.cs", "OutboxPass", "PostRequest"):
        "the outbox replays a queued (url, json) pair; the queue is filled only by EnqueueFailedReport",
    ("plugin/ApiClient.cs", "SendLivePointsOnce", "PostRequest"): "posts the URL SendLivePoints stored",
    ("plugin/ApiClient.cs", "FetchCompareBoard", "GetRequest"): "its own GET of its url parameter",
    ("plugin/ApiClient.cs", "SessionGet", "GetRequest"): "its own GET of its url parameter",
    ("plugin/ApiClient.cs", "SessionPost", "PostRequest"): "its own POST of its url parameter",
    ("plugin/ApiClient.cs", "SessionSend", "SendRequest"): "its own send of its url parameter",
    ("plugin/ApiClient.cs", "DoDelete", "ctor"): "DoDelete's constructor",
    ("plugin/ApiClient.cs", "GetRequest", "ctor"): "GetRequest's constructor",
    ("plugin/ApiClient.cs", "PostRequest", "ctor"): "PostRequest's constructor",
    ("plugin/ApiClient.cs", "PostRequestWithRetry", "ctor"): "PostRequestWithRetry's constructor",
    ("plugin/ApiClient.cs", "SendRequest", "ctor"): "SendRequest's constructor",
    ("plugin/ApiClient.cs", "DoAutoUpdate", "ctor"): "GitHub release metadata and the update download (off-API)",
    ("plugin/ApiClient.cs", "DoFetchReleaseNotes", "ctor"): "GitHub release list (off-API)",
    ("plugin/SpectatorSync.cs", "*", "SendRequest"): "a Photon RaiseEvent named SendRequest, not HTTP",
}
# Code lines carrying "/api/v1" that send nothing.
NON_REQUEST_LINES = {
    ("plugin/ApiClient.cs", '&& url.EndsWith("/api/v1/matches/macro-evidence", StringComparison.Ordinal);'): "URL predicate",
    ("plugin/ApiClient.cs", '&& url.IndexOf("/api/v1/report-disconnect?", StringComparison.Ordinal) >= 0;'): "URL predicate",
    ("plugin/ApiClient.cs", 'return url.Contains("/api/v1/mod-version");'): "URL predicate",
    ("plugin/ApiClient.cs", 'const string seg = "/api/v1/mail";'): "URL predicate",
    ("plugin/MailClient.cs", 'Case("mail_routes_are_sensitive", ApiClient.IsMailRoute("http://x/api/v1/mail") && ApiClient.IsMailRoute("https://x/api/v1/mail/abc/report")'): "self-test literal",
    ("plugin/ApiClient.cs", 'return $"{baseUrl}/api/v1/ffa/lobbies/{Escape(lobbyId)}/live-points" +'):
        "the FFA live-points refusal rewrite: the same POST template as the SendLivePoints FFA call, "
        "with the server's game number",
    ("plugin/MailClient.cs", '&& ApiClient.IsMailRoute("http://x/api/v1/mail/inbox?limit=25") && ApiClient.IsMailRoute("http://x/api/v1/mail/status")'): "self-test literal",
    ("plugin/MailClient.cs", '&& !ApiClient.IsMailRoute("http://x/api/v1/mailbox") && !ApiClient.IsMailRoute("http://x/api/v1/leaderboard") && !ApiClient.IsMailRoute(null), false);'): "self-test literal",
}
SOCKET_LINE = ("plugin/ChatClient.cs",
               'string wsUrl = baseHttp.Replace("https://", "wss://").Replace("http://", "ws://") + "/api/v1/ws/chat";')

# The three direct GETs of /api/v1 outside the transports, by their call line.
DIRECT_HEADERS = {
    "using (var probe = UnityWebRequest.Get($\"{baseUrl}/api/v1/mod-version\"))": "stamped",
    "var req = UnityWebRequest.Get($\"{baseUrl}/api/v1/mod-version\");": "none",
    "var req = UnityEngine.Networking.UnityWebRequest.Get(": "version-only",
}


def tag_sources(repo: str) -> dict[str, list[str]]:
    names = subprocess.run(["git", "-C", repo, "ls-tree", "-r", "--name-only", TAG, "plugin"],
                           capture_output=True, text=True, check=True).stdout.split()
    out = {}
    for f in names:
        if f.endswith(".cs"):
            out[f] = subprocess.run(["git", "-C", repo, "show", TAG + ":" + f], capture_output=True,
                                    text=True, encoding="utf-8", check=True).stdout.splitlines()
    return out


def constructor_counts(src) -> dict[str, int]:
    out: dict[str, int] = {}
    for lines in src.values():
        for line in lines:
            if line.strip().startswith("//"):
                continue
            for m in _CTOR.finditer(line):
                k = re.sub(r"\s+", "", m.group(0))
                out[k] = out.get(k, 0) + 1
    return out


def _args(text: str) -> list[str]:
    depth, cur, args, quote = 0, "", [], False
    for i, ch in enumerate(text):
        if ch == '"' and (i == 0 or text[i - 1] != "\\"):
            quote = not quote
        if not quote:
            if ch in "([{":
                depth += 1
            elif ch in ")]}":
                if depth == 0:
                    args.append(cur)
                    return args
                depth -= 1
            elif ch == "," and depth == 0:
                args.append(cur)
                cur = ""
                continue
        cur += ch
    args.append(cur)
    return args


def _expression(lines, start):
    """The URL expression beginning on line `start` (1-based) up to the end
    of its statement or argument, joined; and the line numbers it spans."""
    parts, used = [], []
    for k in range(start, min(start + 8, len(lines) + 1)):
        t = lines[k - 1].strip()
        parts.append(t)
        used.append(k)
        nxt = lines[k].strip() if k < len(lines) else ""
        if t.endswith(";") or not (t.endswith("+") or nxt.startswith("+")):
            break
    return " ".join(parts), used


def _region_call(rest: str, lines, ln) -> bool:
    """Whether this call's own argument list (balanced across lines, block
    comments and string literals skipped) names the X-Region-Pings header."""
    text = rest + "\n" + "\n".join(lines[ln:ln + 250])
    text = re.sub(r"/\*.*?\*/", " ", text, flags=re.S)
    text = "\n".join(x for x in text.split("\n") if not x.strip().startswith("//"))
    args, _ = _balanced(text, 0, "(", ")")
    return '"X-Region-Pings"' in args


def _enclosing_def(lines, ln):
    for j in range(ln, 0, -1):
        m = _DEF.search(lines[j - 1])
        if m:
            return m.group(2), j
    return None, 0


def extract(repo: str, src: dict | None = None):
    """Returns (calls, residue) where calls is a list of dicts
    {site, fn, method, expr, headers_kind, has_body, region_pings} and
    residue names everything the
    two closures could not account for."""
    src = tag_sources(repo) if src is None else src
    calls, consumed, unresolved, matched_non_api = [], set(), [], set()
    for f, lines in src.items():
        for ln, line in enumerate(lines, 1):
            s = line.strip()
            if s.startswith("//"):
                continue
            hits = [(m.start(), m.group(1), m.end()) for m in _CALL.finditer(line)]
            hits += [(m.start(), "ctor", m.end()) for m in _CTOR.finditer(line)]
            for pos, fn, end in sorted(hits):
                d = _DEF.search(line)
                if d and d.group(2) == fn:
                    continue        # the definition itself
                encl, _ = _enclosing_def(lines, ln)
                key = (f, encl, fn) if (f, encl, fn) in NON_API_SITES else (f, "*", fn)
                if key in NON_API_SITES:
                    matched_non_api.add(key)
                    continue
                window = line[end:] + " " + " ".join(x.strip() for x in lines[ln:ln + 6])
                window = re.sub(r"/\*.*?\*/", " ", window)
                if fn == "ctor":
                    method = "DELETE" if "Delete" in line[pos:end] else "GET"
                    idx = 0
                else:
                    method, idx = TRANSPORTS[fn]
                args = _args(window)
                arg = args[idx].strip() if len(args) > idx else ""
                if method is None:
                    method = args[0].strip().strip('"') if args else "?"
                if "/api/v1" in arg:
                    expr = arg
                    k0 = next(k for k in range(ln, ln + 7) if "/api/v1" in lines[k - 1])
                    for k in _expression(lines, k0)[1]:
                        if "/api/v1" in lines[k - 1]:
                            consumed.add((f, k))
                else:
                    var = arg[:-len(".ToString()")] if arg.endswith(".ToString()") else arg
                    expr, expr_lines = None, []
                    if re.fullmatch(r"[A-Za-z_]\w*", var or ""):
                        fname, fstart = _enclosing_def(lines, ln)
                        for j in range(ln - 1, max(fstart, ln - 90) - 1, -1):
                            t = lines[j - 1]
                            if re.search(r"\b" + re.escape(var) + r"\s*=[^=]", t) or \
                               re.search(r"\b" + re.escape(var) + r"\.Append\(", t):
                                if "/api/v1" in t or (j < len(lines) and "/api/v1" in lines[j]):
                                    k0 = j if "/api/v1" in t else j + 1
                                    e, used = _expression(lines, k0)
                                    expr = e if expr is None else expr
                                    expr_lines += used
                    if expr is None:
                        unresolved.append((f, ln, s))
                        continue
                    for k in expr_lines:
                        if "/api/v1" in lines[k - 1]:
                            consumed.add((f, k))
                kind = "transport"
                for key, hk in DIRECT_HEADERS.items():
                    if s.startswith(key):
                        kind = hk
                jidx = {"PostRequest": 1, "PostRequestWithRetry": 1, "SessionPost": 1,
                        "EnqueueFailedReport": 1, "SendRequest": 2, "SessionSend": 2}.get(fn)
                jarg = args[jidx].strip() if jidx is not None and len(args) > jidx else '""'
                calls.append({"site": f"{f}:{ln}", "fn": fn, "method": method, "expr": expr,
                              "headers_kind": kind,
                              # the client's JSON body is replaced by "{}" (the
                              # lane changes no write handler); an empty body
                              # stays empty
                              "has_body": jarg not in ('""', "null", ""),
                              # the one caller that names the extra header
                              "region_pings": fn == "GetRequest" and _region_call(line[end:], lines, ln)})
    orphans = []
    for f, lines in src.items():
        for ln, line in enumerate(lines, 1):
            s = line.strip()
            if "/api/v1" not in line or s.startswith("//") or s.startswith("*"):
                continue
            if (f, ln) in consumed or (f, s) in NON_REQUEST_LINES or (f, s) == SOCKET_LINE:
                continue
            # a line inside a multi-line literal already consumed by its head
            if (f, ln - 1) in consumed and not re.search(r"\b(string|var)\s+\w+\s*=", s):
                consumed.add((f, ln))
                continue
            orphans.append((f, ln, s))
    return calls, {"unresolved_sites": unresolved, "orphan_lines": orphans,
                   "unmatched_non_api": sorted(set(NON_API_SITES) - matched_non_api),
                   "constructors": constructor_counts(src), "files": len(src)}


_SYN = [
    (r"series|lobby|parsed|room", "{UUID}"),
    (r"^\w+q$", ""),
    (r"bettorsteam|reportersteam|reporter_steam|leaversteam|mysteam|participant", "{ME}"),
    (r"target|opp|betonsteam|disconnected|artiststeam|other", "{ME2}"),
    (r"steam|sid\b|^sid$|admin", "{ME}"),
    (r"sig|signature", "00"),
    (r"locale|^loc$|want", "en"),
    (r"^mode$", "team"),
    (r"which", "inbox"),
    (r"board", "elo"),
    (r"sortby", "times_picked"),
    (r"selector", "series_id"),
    (r"filter", "all"),
    (r"joinedkey", "{ME}"),
    (r"query|value|cardname|^q$|sku|reason|note|text", "x"),
    (r"team$|betonteam", "1"),
]


# Interpolations whose value set the tag names: each value is its own call.
EXPAND = {"mode": ("team", "ovt"),          # the lobby flow serves both lobby modes
          "which": ("inbox", "sent")}       # MailClient.FetchInbox / FetchSent
_OVERRIDE: dict[str, str] = {}


def concrete_urls(expr: str, me: str, me2: str, uuid_: str) -> list[str]:
    """Every URL one call site sends: one per value of an EXPAND name it
    interpolates."""
    names = [k for k in EXPAND if "{" + k + "}" in expr]
    if not names:
        return [concrete_url(expr, me, me2, uuid_)]
    out = []
    for v in EXPAND[names[0]]:
        _OVERRIDE[names[0]] = v
        try:
            out.append(concrete_url(expr, me, me2, uuid_))
        finally:
            _OVERRIDE.clear()
    return out


def _value(expr_inner: str) -> str:
    inner = expr_inner.strip()
    if inner in _OVERRIDE:
        return _OVERRIDE[inner]
    ternary = re.search(r'[^?]\?\s*"([^"]*)"\s*:', inner)
    if ternary:
        return ternary.group(1)
    ident = re.findall(r"[A-Za-z_]\w*", inner)
    ident = [i for i in ident if i not in ("Escape", "UnityWebRequest", "EscapeURL", "Uri",
                                           "EscapeDataString", "ToString", "D")]
    name = (ident[-1] if ident else "").lower()
    if name in ("baseurl", "base"):
        return ""
    for pat, val in _SYN:
        if re.search(pat, name):
            return val
    return "1"


def _plain_literal_end(expr: str, i: int) -> int:
    """Index just past the regular string literal opening at expr[i]."""
    k = i + 1
    while k < len(expr) and expr[k] != '"':
        k += 2 if expr[k] == "\\" else 1
    return k + 1


def _balanced(expr: str, j: int, open_ch: str, close_ch: str) -> tuple[str, int]:
    """The text up to the close matching an already-consumed opener, and the
    index after the close; nested string literals are skipped whole."""
    depth, inner = 1, ""
    while j < len(expr):
        c = expr[j]
        if c == '"':
            k = _plain_literal_end(expr, j)
            inner += expr[j:k]
            j = k
            continue
        if c == open_ch:
            depth += 1
        elif c == close_ch:
            depth -= 1
            if depth == 0:
                return inner, j + 1
        inner += c
        j += 1
    return inner, j


def concrete_url(expr: str, me: str, me2: str, uuid_: str) -> str:
    """The URL a call sends, with synthetic values for its interpolations.
    A C# scanner: interpolated literals ($"..{expr}.."), plain literals and
    StringBuilder .Append(...) pieces, in order."""
    out, i, n = "", 0, len(expr)
    while i < n:
        if expr.startswith('$"', i):
            i += 2
            while i < n and expr[i] != '"':
                if expr[i] == "\\":
                    out += expr[i + 1]
                    i += 2
                elif expr.startswith("{{", i):
                    out += "{"
                    i += 2
                elif expr[i] == "{":
                    inner, i = _balanced(expr, i + 1, "{", "}")
                    out += _value(inner)
                else:
                    out += expr[i]
                    i += 1
            i += 1
        elif expr[i] == '"':
            k = _plain_literal_end(expr, i)
            out += expr[i + 1:k - 1]
            i = k
        elif expr.startswith(".Append(", i):
            inner, i = _balanced(expr, i + len(".Append("), "(", ")")
            inner = inner.strip()
            out += inner[1:-1] if inner.startswith('"') else _value(inner)
        else:
            i += 1
    out = out.replace("{ME}", me).replace("{ME2}", me2).replace("{UUID}", uuid_)
    if not out.startswith("/api/v1"):
        out = out[out.index("/api/v1"):] if "/api/v1" in out else out
    return out


def headers_for(call: dict, session: str | None) -> dict:
    h = {"User-Agent": "UnityPlayer/2019.4.40f1 (UnityWebRequest/1.0, libcurl/7.80.0-DEV)"}
    kind = call["headers_kind"]
    if kind in ("transport", "stamped", "version-only"):
        h["X-Mod-Version"] = VERSION
    if kind in ("transport", "stamped") and session:
        h["X-Session-Token"] = session
    if call["method"] == "POST" and call["fn"] in ("PostRequest", "PostRequestWithRetry", "SessionPost",
                                                  "SendLivePoints", "EnqueueFailedReport"):
        h["Content-Type"] = "application/json"
    if call["fn"] in ("SendRequest", "SessionSend") and call.get("has_body"):
        h["Content-Type"] = "application/json"
    if call.get("region_pings"):
        h["X-Region-Pings"] = "{}"
    return h


def request_list(repo: str, me: str, me2: str, uuid_: str, session: str) -> list[dict]:
    """The replay: every call of the tag, each URL it can send, once without
    a session and once with one where the call can carry it, then the chat
    socket's connect."""
    calls, _ = extract(repo)
    out = []
    for c in calls:
        for url in concrete_urls(c["expr"], me, me2, uuid_):
            variants = [None, session] if c["headers_kind"] in ("transport", "stamped") else [None]
            for tok in variants:
                out.append({"site": c["site"], "method": c["method"], "url": url,
                            "headers": headers_for(c, tok),
                            "body": "{}" if c["has_body"] else None,
                            "session": tok is not None})
    out.append({"site": SOCKET_LINE[0], "method": "WS", "url": "/api/v1/ws/chat",
                "headers": {"X-Mod-Version": VERSION}, "body": None, "session": False})
    return out
