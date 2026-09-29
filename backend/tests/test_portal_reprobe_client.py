"""Board rows 27 and 33a (the portal re-probe lane): the source-level half.

The secure-route decisions and every sentence they show a player are EXECUTED
by tools/client-rules-harness (suite "secureroute", wrapped by
test_client_rules_harness.py). This module holds what only the source can
show: where the scrmod.com button sits in the F5 footer row and how it opens,
that its label and the new sentence keys are in every catalogue, that the
witness lever reaches the boot check on the broadcast account only, and how a
session back from the backup signs in again (no ticket spent on the backup, a
401 clearing only a token the request carried, a press after a restore
waiting for the first secure session).
"""
import io
import json
import os
import re
from pathlib import Path

from _cs_structure import code_of

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
NATIVE = os.path.join(ROOT, "plugin", "NativeUI.cs")
API = Path(ROOT) / "plugin" / "ApiClient.cs"
BROADCAST = Path(ROOT) / "plugin" / "BroadcastMode.cs"
PLUGIN_CS = Path(ROOT) / "plugin" / "Plugin.cs"
STEAMAUTH = Path(ROOT) / "plugin" / "SteamAuth.cs"
CATALOGUES = os.path.join(ROOT, "plugin", "I18nCatalogues.cs")
SOURCE = os.path.join(ROOT, "tools", "i18n_source.json")
LOCALES = ("ES", "RU", "UK", "SV")
LINKS = ["Discord", "GitHub", "YouTube", "Twitch", "Thunderstore", "ScrMod"]
HOLE = re.compile(r"\{\d+\}")


def _read(path):
    with io.open(path, encoding="utf-8-sig") as fh:
        return fh.read().replace("\r\n", "\n")


def _footer():
    """The F5 footer row as BuildPage builds it: from the "Bottom" row's
    creation to the page-built flag, and the CreateButton calls parented to
    that row, in build order, as (object name, label, call text)."""
    src = _read(NATIVE)
    start = src.index('var bottom=new GameObject("Bottom")')
    end = src.index("pageBuilt=true;", start)
    body = src[start:end]
    calls = []
    for m in re.finditer(r'UIFactory\.CreateButton\("([^"]+)",bottom\.transform,"([^"]*)"', body):
        line_end = body.index("\n", m.start())
        calls.append((m.group(1), m.group(2), body[m.start():line_end]))
    return calls


def _dictionary(src, locale):
    """One catalogue's body, from its declaration to its closing brace."""
    head = "private static readonly Dictionary<string, string> %s = " % locale
    at = src.index(head)
    end = src.index("\n        };", at)
    return src[at:end]


def _cs_unescape(lit):
    out, i = [], 0
    while i < len(lit):
        c = lit[i]
        if c != "\\":
            out.append(c)
            i += 1
            continue
        n = lit[i + 1]
        if n == "u":
            out.append(chr(int(lit[i + 2:i + 6], 16)))
            i += 6
            continue
        out.append({"n": "\n", "r": "\r", "t": "\t", "\\": "\\", '"': '"', "0": "\0"}.get(n, n))
        i += 2
    return "".join(out)


def _entry(body, key):
    """Every value the dictionary body gives `key` (a plain ASCII key with no
    escapes), decoded from its C# literal."""
    needle = '["%s"] = "' % key
    values, at = [], body.find(needle)
    while at >= 0:
        i = at + len(needle)
        j = i
        while body[j] != '"':
            j += 2 if body[j] == "\\" else 1
        values.append(_cs_unescape(body[i:j]))
        at = body.find(needle, j)
    return values


def test_the_scrmod_button_is_built_once_directly_after_thunderstore():
    calls = _footer()
    names = [n for n, _, _ in calls]
    assert names.count("ScrMod") == 1, names
    first = names.index("Discord")
    assert names[first:first + len(LINKS)] == LINKS, (
        "the footer links must read %s, in that order; found %s" % (LINKS, names))


def test_the_scrmod_button_opens_the_site_the_way_its_siblings_open_theirs():
    by_name = {n: (label, text) for n, label, text in _footer()}
    label, text = by_name["ScrMod"]
    assert label == "scrmod.com"
    # The same factory call as its siblings: CreateButton wraps the handler in
    # the per-control ClickGuard debounce, and these buttons are the mod's own,
    # so there is no cloned ROUNDS component (QuitButton) to strip.
    assert 'Application.OpenURL("https://scrmod.com/")' in text, text
    sibling = by_name["Thunderstore"][1]
    assert "Application.OpenURL(" in sibling and "14f,Color.white," in sibling and "14f,Color.white," in text
    assert _read(NATIVE).count("https://scrmod.com/") == 1


def test_the_scrmod_label_reads_the_same_in_every_catalogue():
    src = _read(CATALOGUES)
    for locale in LOCALES:
        values = _entry(_dictionary(src, locale), "scrmod.com")
        assert values == ["scrmod.com"], "%s: %r" % (locale, values)
    assert "scrmod.com" in json.load(io.open(SOURCE, encoding="utf-8"))["strings"]


def test_every_secure_route_sentence_is_a_key_in_every_catalogue():
    contexts = json.load(io.open(SOURCE, encoding="utf-8"))["contexts"]
    keys = sorted(k for k, v in contexts.items() if "SecureRouteText" in v.get("surface", ""))
    # The ten sentences of plugin/SecureRouteText.cs, plus the sign-in toast
    # whose "until it is back" the checks made true
    # (ApiClient.NoteTicketExchangeRefused).
    keys.append("Secure connection unavailable - signed-in features are off until it is back.")
    assert len(keys) == 11, keys
    src = _read(CATALOGUES)
    for locale in LOCALES:
        body = _dictionary(src, locale)
        for key in keys:
            values = _entry(body, key)
            assert len(values) == 1, "%s: %d entries for %r" % (locale, len(values), key)
            value = values[0]
            assert value.strip() and value != key, "%s: %r is not translated" % (locale, key)
            assert sorted(HOLE.findall(value)) == sorted(HOLE.findall(key)), (
                "%s: the holes of %r moved: %r" % (locale, key, value))


def test_the_witness_lever_reaches_the_boot_check_on_the_broadcast_account_only():
    """[Broadcast] TestSecureUrl steers a secure check only on the broadcast
    account, and it has to steer the BOOT check as well: a failed boot check
    is the only way a session reaches the backup, which is what witnesses W2
    and W3 start from. The boot check begins in ApiClient.Initialize, which
    DoInitialize calls before GameStateWatcher.Initialize resolves the local
    id, so the plain identity property still reads false there (the first
    witness run on the broadcast seat showed exactly that). The gate is the
    boot-safe form, which reads Steamworks when the resolved id is missing and
    admits only the listed broadcast accounts."""
    init = code_of(PLUGIN_CS, "private void DoInitialize()")
    api_at = init.index("ApiClient.Initialize(Plugin.ApiBaseUrl.Value);")
    assert api_at < init.index("GameStateWatcher.Initialize();"), (
        "DoInitialize no longer starts the api before the watcher; the boot-safe "
        "identity and its comments describe an order that is gone")
    probe = code_of(API, "private static string SecureProbeBase()")
    assert probe.count("BroadcastMode.IsBroadcastIdentityAtBoot()") == 1, probe
    assert not re.search(r"IsBroadcastIdentity(?!AtBoot)", probe), probe
    assert probe.index("IsBroadcastIdentityAtBoot()") < probe.index("return lever;"), probe
    boot = code_of(BROADCAST, "internal static bool IsBroadcastIdentityAtBoot()")
    assert "Steamworks.SteamUser.GetSteamID()" in boot, boot
    assert "BroadcastAccounts" in boot and "_identityLatched" not in boot, boot
    assert not re.search(r'"\d{17}"', boot), "an account id belongs in BroadcastAccounts, not in the check"


SIGN_IN_TOAST = 'I18n.Tr("Secure connection unavailable - signed-in features are off until it is back.")'


def test_no_steam_ticket_is_requested_while_the_api_would_refuse_to_exchange_it():
    """On the backup the api refuses every ticket exchange (F1), yet SteamAuth
    kept requesting a ticket every few seconds. On the broadcast seat twenty
    unexchanged tickets were followed by no further ticket for the rest of the
    session, so after the secure route came back (witness W3) the session could
    not sign in and the portal button met the sign-in refusal. SteamAuth now
    asks the exchange's own question before its session checks (so the notice
    also reaches a session that is held but withheld on the backup, as it did
    when a withheld 401 still cleared it) and spends no attempt when refused;
    PostSteamAuth asks the same one; the notice both show lives in one place
    and stays once per session."""
    refresh = code_of(STEAMAUTH, "public static void MaybeRefresh()")
    gate = "if (!ApiClient.TicketExchangeAllowed())"
    assert refresh.count(gate) == 1, refresh
    at = refresh.index(gate)
    assert at < refresh.index("if (HasFreshToken || _ticketHeld) return;"), refresh
    assert at < refresh.index("_lastAttemptAt = Time.realtimeSinceStartup;"), refresh
    assert at < refresh.index('_ticket = SteamUser.GetAuthTicketForWebApi("competitive-rounds");'), refresh
    branch = refresh[at:refresh.index("}", at)]
    assert "ApiClient.NoteTicketExchangeRefused();" in branch and "return;" in branch, branch
    whole = code_of(API)
    assert whole.count(
        "internal static bool TicketExchangeAllowed() => CredentialedTransportAllowed(baseUrl);") == 1
    post = code_of(API, "public static void PostSteamAuth(string ticketHex, Action<string> onEnded)")
    refuse = "if (!TicketExchangeAllowed())"
    assert post.count(refuse) == 1, post
    assert "CredentialedTransportAllowed(" not in post, "PostSteamAuth asks a second rule"
    refused = post[post.index(refuse):post.index("}", post.index(refuse))]
    assert "NoteTicketExchangeRefused();" in refused and "return;" in refused, refused
    assert post.index(refuse) < post.index("/api/v1/auth/steam"), post
    note = code_of(API, "internal static void NoteTicketExchangeRefused()")
    first = note.index("if (_insecureAuthNotified) return;")
    assert first < note.index("_insecureAuthNotified = true;") < note.index(SIGN_IN_TOAST), note
    assert "[STEAM-AUTH] refusing ticket exchange over plaintext public endpoint" in note, note
    assert whole.count(SIGN_IN_TOAST) == 1, "the sign-in notice is shown from more than one place"



def test_every_steam_ticket_is_cancelled_when_its_exchange_ends_and_one_is_held_at_a_time():
    """The no-token residual (board row 27 round 2): while ticket exchanges
    timed out, SteamAuth released its latch at the ticket CALLBACK, so a new
    ticket was requested every 4 s beside exchanges still running for 20 s,
    and no ticket was ever cancelled. Twenty such tickets were followed by no
    further ticket for the rest of the session (the 2026-09-28 note in
    MaybeRefresh; witness S4 again), so a session back on the secure route
    could not sign in. Now one ticket is held from its request until its
    exchange ends; every end (answered, failed or timed out, not sent, a failed
    callback, a handling error, abandonment) cancels it with Steam; and only
    the held ticket's own end can release the latch."""
    auth = code_of(STEAMAUTH)
    assert "_requestInFlight" not in auth, "the callback-time latch is back"
    refresh = code_of(STEAMAUTH, "public static void MaybeRefresh()")
    gate = "if (HasFreshToken || _ticketHeld) return;"
    mint = '_ticket = SteamUser.GetAuthTicketForWebApi("competitive-rounds");'
    assert refresh.count(gate) == 1 and refresh.count(mint) == 1, refresh
    assert refresh.index(gate) < refresh.index(mint) < refresh.index("_ticketHeld = true;"), refresh
    assert refresh.index(mint) < refresh.index("_ticketSerial++;"), refresh
    abandon = "if (_ticketHeld && Time.realtimeSinceStartup - _ticketSince > TicketAbandonSeconds)"
    assert refresh.count(abandon) == 1 and refresh.index(abandon) < refresh.index(gate), refresh
    after = refresh[refresh.index(abandon) + len(abandon):]
    assert after.lstrip().startswith("EndTicket(_ticketSerial,"), "abandonment does not end (cancel) the ticket"
    # Abandonment only for an end that never arrives: past the exchange's own timeout.
    limit = float(re.search(r"const float TicketAbandonSeconds = ([0-9.]+)f;", auth).group(1))
    raw = code_of(API, "private static IEnumerator PostRequestRaw(")
    timeout = int(re.search(r"request\.timeout = (\d+);", raw).group(1))
    assert limit > timeout + 10, (limit, timeout)
    # The only release of the latch is EndTicket, which cancels, and a stale serial changes nothing.
    assert auth.count("_ticketHeld = false;") == 1, "the latch is released somewhere other than EndTicket"
    end = code_of(STEAMAUTH, "internal static void EndTicket(int serial, string outcome)")
    guard = "if (!_ticketHeld || serial != _ticketSerial) return;"
    assert end.count(guard) == 1 and "_ticketHeld = false;" in end, end
    assert end.index(guard) < end.index("_ticketHeld = false;") < end.index("SteamUser.CancelAuthTicket(_ticket);"), end
    # The callback: only the held ticket, and every path ends it.
    cb = code_of(STEAMAUTH, "private static void OnWebTicket(GetTicketForWebApiResponse_t cb)")
    held = "if (!_ticketHeld || cb.m_hAuthTicket.m_HAuthTicket != _ticket.m_HAuthTicket) return;"
    assert cb.count(held) == 1 and cb.index(held) < cb.index("int serial = _ticketSerial;"), cb
    failed = cb[cb.index("ticket callback failed"):]
    assert failed.index('EndTicket(serial, "callback failed");') < failed.index("return;"), cb
    assert "ApiClient.PostSteamAuth(hex, outcome => EndTicket(serial, outcome));" in cb, cb
    assert 'EndTicket(serial, "handling error");' in cb[cb.index("catch (Exception ex)"):], cb
    # The exchange reports its end exactly once on every path.
    post = code_of(API, "public static void PostSteamAuth(string ticketHex, Action<string> onEnded)")
    assert "if (ended) return;" in post and post.index("if (ended) return;") < post.index("ended = true;"), post
    assert '{ end("not sent: no identity"); return; }' in post, post
    refused = post[post.index("if (!TicketExchangeAllowed())"):]
    assert refused.index('end("not sent: plaintext base");') < refused.index("return;"), post
    fin = post[post.index("finally"):]
    assert fin.index('end(success ? "answered" : "failed");') < fin.index("}"), post
    assert 'end("not started");' in post[post.index("catch (Exception ex)"):], post
    assert post.count("return;") == 4, "a new early return in PostSteamAuth must end the ticket first"

def test_a_401_clears_only_a_session_token_the_request_carried():
    """StampVersionHeader withholds the session token on plaintext-to-public
    transport (the backup), and a 401 to such a request said nothing about the
    session yet cleared it: W3's session lost the good token it held before the
    fallback that way, and after a restore a request still bound for the
    backup (one built before the restore, or a queued report, which keeps its
    URL) would clear the new one. The reject handler asks the stamping rule of
    the same URL before it clears anything."""
    reject = code_of(API, "private static void HandleSessionReject(UnityWebRequest req, string sentToken)")
    guard = "if (!CredentialedTransportAllowed(req.url)) return;"
    assert reject.count(guard) == 1, reject
    assert reject.index("if (req.responseCode != 401) return;") < reject.index(guard), reject
    assert reject.index(guard) < reject.index("SteamAuth.InvalidateSessionIf(sentToken);"), reject
    stamp = code_of(API, "private static void StampVersionHeader(UnityWebRequest req)")
    rule = "if (CredentialedTransportAllowed(req.url))"
    carry = 'req.SetRequestHeader("X-Session-Token", SteamAuth.SessionToken);'
    assert stamp.count(rule) == 1 and stamp.count(carry) == 1, stamp
    between = stamp[stamp.index(rule) + len(rule):stamp.index(carry)]
    assert between.strip() == "", "the token is no longer stamped by that rule alone: %r" % between


def test_a_press_after_a_restore_waits_for_the_first_secure_session():
    """After a restore the session may hold no token yet: no ticket was
    requested on the backup, and SteamAuth requests the first secure one on
    its own loop. The press that restores the route already waited for it
    (FinishPortalPress); a press after a restore took the OpenNow branch and
    minted at once, which the server refuses without a session (W3's press got
    401 session_required and the sign-in message). Once the route has been
    restored the OpenNow branch waits the same way; before any restore it
    mints at once, as it always did.

    Round 2: the order is SecureRouteRules.PortalPressAction's (harness cases
    K1, K2, K3 and K3c), and this checks the press hands it the restored flag
    and acts on its answer."""
    press = code_of(API, "public static void OpenTranslatePortal()")
    call = "var action = SecureRouteRules.PortalPressAction("
    assert press.count(call) == 1, press
    args = press[press.index(call):press.index(";", press.index(call))]
    assert "route != null && route.Restored" in args, args
    assert 'baseUrl.StartsWith("https://", StringComparison.OrdinalIgnoreCase)' in args, args
    case = "case SecureRouteRules.PressAction.WaitThenMint:"
    assert press.count(case) == 1, press
    block = press[press.index(case):press.index("return;", press.index(case))]
    assert "Plugin.Instance.StartCoroutine(OpenPortalWhenSessionReady());" in block, block
    assert press.count("MintPortalSessionAndOpen(true);") == 1, press
    assert press.index("MintPortalSessionAndOpen(true);") > press.index(call), press
    wait = code_of(API, "private static IEnumerator OpenPortalWhenSessionReady()")
    assert "while (!PortalSessionReady() && Time.realtimeSinceStartup < until)" in wait, wait
    assert wait.index("MintPortalSessionAndOpen(true);") > wait.index("while ("), wait
    finish = code_of(API, "private static void FinishPortalPress(SecureRouteRules.Conclusion c)")
    assert "host.StartCoroutine(OpenPortalWhenSessionReady());" in finish, finish


# -- Round 2 (Codex round 1: HIGH 1, MEDIUM 1, LOW 1, LOW 2) ------------------
# The decisions are executed by the harness (secureroute J, O, R, K, H cases);
# these check that ApiClient asks them where the finding said it must.

def test_a_queued_report_is_sent_where_the_route_is_at_the_send():
    """HIGH 1: a report queued on the backup kept the backup's URL after a
    restore, every retry went out without the session token, the enforced
    sink answered 401 and the outbox deleted the report at attempt 94. The
    pass now resolves the address once per send (OutboxSendUrl over the route's
    bases), keeps it in a local for the whole request, and asks the spend rule
    with what the request could carry and whether the route could still return,
    both captured before the network yield."""
    body = code_of(API, "private static IEnumerator OutboxPass()")
    resolve = "string target = OutboxSendUrl(p.url);"
    send = "yield return PostRequest(target, p.json,"
    assert body.count(resolve) == 1 and body.count(send) == 1, body
    assert body.count("PostRequest(") == 1, "a second send in the pass: %s" % body
    spend = "if (!SecureRouteRules.OutboxAttemptSpent(carried))"
    assert body.count(spend) == 1, body
    assert body.index(spend) < body.index("bool permanent ="), body
    assert body.index(spend) < body.index("p.attempts >= OUTBOX_MAX_ATTEMPTS"), body
    given_back = body[body.index(spend):body.index("continue;", body.index(spend))]
    assert "p.attempts--;" in given_back, given_back
    target = code_of(API, "private static string OutboxSendUrl(string storedUrl)")
    assert "if (route == null || string.IsNullOrEmpty(storedUrl)) return storedUrl;" in target, target
    assert "return SecureRouteRules.OutboxTarget(storedUrl, baseUrl, bases);" in target, target
    compiled = target[target.index("if (_routeHarnessBackup == null)"):]
    assert "Plugin.DefaultApiUrl" in compiled and "Plugin.LegacyApiUrl" in compiled, target
    whole = code_of(API)
    for sig in ("private static bool OutboxAlreadyQueued(string url, string json)",
                "public static void EnqueueFailedReport(string url, string json)",
                "private static void RemovePendingReport(string url, string json)",
                "private static OutboxGeneration Union(OutboxGeneration newer, OutboxGeneration older)"):
        fn = code_of(API, sig)
        assert "SameQueuedReport(" in fn, "%s compares reports without the route: %s" % (sig, fn)
    assert not re.search(r"\.url\s*==\s*\w+\.url\s*&&|\.url\s*==\s*url\s*&&|\.url\s*!=\s*url\s*\|\|", whole), (
        "a report identity compares raw URLs somewhere")
    restored = code_of(API, "private static void OnSecureRouteRestored(SecureRouteRules.Route route, SecureRouteRules.Conclusion c)")
    assert "OutboxRouteRestored();" in restored, restored


def test_a_restored_retry_goes_out_only_with_the_session_and_a_tokenless_one_spends_nothing():
    """Codex round 2 HIGH 1: after a restore the outbox made every queued
    report due within 20 s without waiting for a session, recorded "could carry
    the session" from the address alone, and spent an attempt on the enforcing
    sink's 401 once the route could no longer return, so attempt 94 deleted the
    report while the Steam exchange was still unavailable. Now, over a
    transport that carries the token, the pass sends only with a fresh session
    (SecureRouteRules.OutboxSendGate; harness O4b, O7) and otherwise waits
    without spending; whether a request carried the token is read from the
    header PostRequestRaw actually stamped; and only an attempt that carried it
    is spent (OutboxAttemptSpent; harness O4, O8), so the drop rule is reached
    by authenticated attempts only."""
    body = code_of(API, "private static IEnumerator OutboxPass()")
    gate = ("if (SecureRouteRules.OutboxSendGate(CredentialedTransportAllowed(target), SteamAuth.HasFreshToken)\n"
            "                    == SecureRouteRules.OutboxGate.WaitForSession)")
    assert body.count(gate) == 1, body
    resolve = body.index("string target = OutboxSendUrl(p.url);")
    spend_attempt = body.index("p.attempts++;")
    send = body.index("yield return PostRequest(target, p.json,")
    assert resolve < body.index(gate) < spend_attempt < send, body
    waiting = body[body.index(gate):body.index("continue;", body.index(gate))]
    assert "p.nextAt = Time.realtimeSinceStartup + (float)SecureRouteRules.OutboxSessionPollSeconds;" in waiting, waiting
    assert not re.search(r"p\.attempts\s*(\+\+|--|[-+]?=)", waiting), "the wait spends or sets attempts: " + waiting
    assert "PostRequest(" not in waiting and "Remove(" not in waiting, waiting
    assert "stamped => carried = stamped);" in body[send:send + 200], body[send:send + 200]
    assert "CredentialedTransportAllowed(" not in body[spend_attempt:], "the spend rule reads the address again"
    spend = body.index("if (!SecureRouteRules.OutboxAttemptSpent(carried))")
    given_back = body[spend:body.index("continue;", spend)]
    assert "p.attempts--;" in given_back and "Remove(" not in given_back, given_back
    assert spend < body.index("bool permanent =") < body.index("p.attempts >= OUTBOX_MAX_ATTEMPTS"), body
    raw = code_of(API, "private static IEnumerator PostRequestRaw(")
    stamp = raw.index("StampVersionHeader(request);")
    read = raw.index('request.GetRequestHeader("X-Session-Token")')
    told = raw.index("onTokenStamped(stamped);")
    assert stamp < read < told < raw.index("request.SendWebRequest()"), raw
    post = code_of(API, "private static IEnumerator PostRequest(string url, string json, Action<bool, string> callback,")
    assert "callback, json, null, onTokenStamped);" in post, post
    rules = code_of(Path(ROOT) / "plugin" / "SecureRouteRules.cs", "internal static bool OutboxAttemptSpent(bool requestCarriedToken)")
    assert "return requestCarriedToken;" in rules, rules


def test_a_give_back_after_a_restore_never_cancels_the_restore_s_promise():
    """Codex round 2 LOW 1: a tokenless retry in flight on the backup when the
    route is restored answers 401 after the flip, and its give-back overwrote
    the due time the restore had just set (within 20 s) with now plus 240 s.
    The restore records its promise on every entry, a send that begins clears
    it, and the give-back takes the earlier of the capped interval and the
    promise (SecureRouteRules.OutboxGiveBackDue; harness O9)."""
    restored = code_of(API, "private static void OutboxRouteRestored()")
    loop = restored[restored.index("foreach (var p in _pendingReports)"):]
    assert loop.index("p.restoreDueAt = soon;") < loop.index("if (p.nextAt > soon)"), restored
    body = code_of(API, "private static IEnumerator OutboxPass()")
    clear = body.index("p.restoreDueAt = -1f;")
    assert body.count("p.restoreDueAt = -1f;") == 1, body
    assert body.index("== SecureRouteRules.OutboxGate.WaitForSession)") < clear < body.index("p.attempts++;"), body
    spend = body.index("if (!SecureRouteRules.OutboxAttemptSpent(carried))")
    given_back = body[spend:body.index("continue;", spend)]
    assert "p.nextAt = (float)SecureRouteRules.OutboxGiveBackDue(" in given_back, given_back
    assert "p.restoreDueAt);" in given_back, given_back
    assert given_back.count("p.nextAt =") == 1, given_back


def test_the_probe_reads_the_whole_body_strictly():
    """MEDIUM 1: the probe called a body usable when the compact substring
    "version":" appeared, so a body cut off inside the string restored the
    route and one with a space after the colon did not. It asks the strict
    parser (harness J1-J6) and nothing else."""
    probe = code_of(API, "private static IEnumerator ProbeSecureRoute(string url, int timeoutSeconds, Action<SecureRouteRules.Reading> done)")
    assert "reading.VersionParsed = SecureRouteRules.IsModVersionBody(body);" in probe, probe
    assert "ExtractJsonString" not in probe, probe


def test_the_portal_press_asks_for_the_identity_only_before_a_mint():
    """LOW 2: the press returned at once while the local identity was unknown
    (the startup race), before it could start the secure check or show the
    plaintext refusal, so the press did nothing. The route's press and the
    rule's decision come first; the identity is an argument of the decision."""
    press = code_of(API, "public static void OpenTranslatePortal()")
    call = press.index("var action = SecureRouteRules.PortalPressAction(")
    head = press[:call]
    assert "return;" not in head.replace("if (Plugin.Instance == null) return;", ""), head
    assert "route.PressPortal(" in head, head
    args = press[call:press.index(";", call)]
    assert '!string.IsNullOrEmpty(sid) && sid != "unknown"' in args, args
    checking = press[press.index("case SecureRouteRules.PressAction.ShowChecking:"):]
    checking = checking[:checking.index("return;")]
    assert "SecureRouteText.Checking()" in checking and "RunSecureCheck(route, gen);" in checking, checking
    refuse = press[press.index("case SecureRouteRules.PressAction.RefusePlaintext:"):]
    refuse = refuse[:refuse.index("return;")]
    assert "SecureRouteText.PlaintextOverride(baseUrl)" in refuse, refuse


def test_a_refused_portal_session_is_dropped_and_minted_again_once():
    """LOW 1: the wait after a restore accepted any nonempty token, and the
    portal mint's refusal ("steam session required") did not match the
    client's invalidation literal, so a stale token stayed and the press failed.
    The wait asks for a fresh session and a known identity; the reject handler
    reads both wordings; the mint re-mints once on a session refusal, and the
    re-mint passes false so a second refusal is reported, not looped."""
    reject = code_of(API, "private static void HandleSessionReject(UnityWebRequest req, string sentToken)")
    assert "if (!SecureRouteRules.IsSessionRefusal(body)) return;" in reject, reject
    assert 'body.Contains("session_required")' not in reject, reject
    ready = code_of(API, "private static bool PortalSessionReady()")
    assert "return SteamAuth.HasFreshToken;" in ready and '"unknown"' in ready, ready
    mint = code_of(API, "private static void MintPortalSessionAndOpen(bool remintOnRefusal)")
    assert "SecureRouteRules.PortalMintAction(success, token, response, remintOnRefusal)" in mint, mint
    remint = mint[mint.index("if (act == SecureRouteRules.MintAction.RemintOnce"):]
    remint = remint[:remint.index("return;")]
    assert "StartCoroutine(RemintThenOpenPortal());" in remint, remint
    assert mint.index("act != SecureRouteRules.MintAction.Open") < mint.index("Application.OpenURL("), mint
    again = code_of(API, "private static IEnumerator RemintThenOpenPortal()")
    assert "while (!PortalSessionReady() && Time.realtimeSinceStartup < until)" in again, again
    assert "MintPortalSessionAndOpen(false);" in again and "MintPortalSessionAndOpen(true);" not in again, again
    whole = code_of(API)
    assert whole.count("MintPortalSessionAndOpen(false);") == 1, "a second no-retry mint site"
    assert "MintPortalSessionAndOpen();" not in whole, "a mint site that says nothing about the retry"



def test_every_portal_mint_that_opens_nothing_says_why_in_the_log():
    """Witness S5's press r5 (a valid session after a restore) opened no
    portal and left no log line: the mint's failure branch showed only a 5 s
    toast, so whether the request timed out or was refused could not be read
    afterwards. Every return of the mint that opens nothing now writes one
    line before it returns, and the failure line carries the answer's own
    text (bounded) and never a token."""
    mint = code_of(API, "private static void MintPortalSessionAndOpen(bool remintOnRefusal)")
    body = mint[mint.index("{") + 1:]
    returns = [m.start() for m in re.finditer(r"\breturn;", body)]
    assert len(returns) == 5, "a new return in the mint must be looked at: %d" % len(returns)
    first = body.index("if (Plugin.Instance == null) return;")
    for at in returns:
        if at == first + len("if (Plugin.Instance == null) ") or "RemintThenOpenPortal" in body[max(0, at - 160):at]:
            continue   # no plugin host at all; the re-mint hand-off logs its own line above
        before = body[max(0, at - 700):at]
        seg = before[before.rfind("if ("):]
        assert "Plugin.Log.Log" in seg, "a mint return that opens nothing and logs nothing: " + seg
    fail = body[body.index("if (act != SecureRouteRules.MintAction.Open)"):]
    fail = fail[:fail.index("return;")]
    assert 'string why = success ? "answered without a token" : PortalMintFailureText(response);' in fail, fail
    assert "[I18N] portal mint failed over {portalBase}: {why}" in fail, fail
    assert "token}" not in fail.replace("{portalBase}", ""), "the failure line prints the token"
    text = code_of(API, "internal static string PortalMintFailureText(string response)")
    assert "160" in text and 'Replace("\\n", " ")' in text, text

def test_the_round_2_witness_levers_act_on_the_broadcast_account_only():
    """The local harness (TestBackupUrl, TestQueueReport) and the stale-token
    lever change nothing for a player: the harness is armed only when the
    boot-safe broadcast identity holds, the report lever does nothing unless
    the harness is armed, all three are ticked only from the broadcast lever
    tick, and a harness session never sends a report queued under the
    compiled addresses (OutboxSendUrl adds them only outside the harness)."""
    arm = code_of(API, "private static string RouteHarnessBackup()")
    assert arm.index("BroadcastMode.IsBroadcastIdentityAtBoot()") < arm.index("return lever;"), arm
    queue = code_of(API, "internal static void TickTestQueueReport()")
    assert "if (_routeHarnessBackup == null || Plugin.Instance == null)" in queue, queue
    assert queue.index("_routeHarnessBackup == null") < queue.index("PostRequestWithRetry("), queue
    tick = code_of(PLUGIN_CS, "private void TickTestOpenTab()")
    gate = "if (Plugin.BroadcastTestOpenTab == null || !BroadcastMode.IsBroadcastIdentity) return;"
    assert tick.count(gate) == 1, tick
    for lever in ("ApiClient.TickTestQueueReport();", "ApiClient.TickTestStaleToken();"):
        assert tick.count(lever) == 1 and tick.index(gate) < tick.index(lever), tick
    plugin = code_of(PLUGIN_CS)
    for lever in ("TickTestQueueReport()", "TickTestStaleToken()"):
        assert plugin.count(lever) == 1, "%s is called from somewhere else too" % lever
    init = code_of(API, "public static void Initialize(string url)")
    assert init.index("_routeHarnessBackup = RouteHarnessBackup();") < init.index("StartBootProbe();"), init
    for key in ("\"TestBackupUrl\", \"\"", "\"TestQueueReport\", \"\"", "\"TestStaleToken\", \"\""):
        assert key in plugin, "%s is not empty by default" % key
