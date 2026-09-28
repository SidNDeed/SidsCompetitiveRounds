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
    asks the exchange's own question before it requests a ticket and spends no
    attempt when refused; PostSteamAuth asks the same one; the notice both
    show lives in one place and stays once per session."""
    refresh = code_of(STEAMAUTH, "public static void MaybeRefresh()")
    gate = "if (!ApiClient.TicketExchangeAllowed())"
    assert refresh.count(gate) == 1, refresh
    at = refresh.index(gate)
    assert at < refresh.index("_lastAttemptAt = Time.realtimeSinceStartup;"), refresh
    assert at < refresh.index('SteamUser.GetAuthTicketForWebApi("competitive-rounds");'), refresh
    branch = refresh[at:refresh.index("}", at)]
    assert "ApiClient.NoteTicketExchangeRefused();" in branch and "return;" in branch, branch
    whole = code_of(API)
    assert whole.count(
        "internal static bool TicketExchangeAllowed() => CredentialedTransportAllowed(baseUrl);") == 1
    post = code_of(API, "public static void PostSteamAuth(string ticketHex)")
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
    mints at once, as it always did."""
    press = code_of(API, "public static void OpenTranslatePortal()")
    cond = "if (route != null && route.Restored)"
    assert press.count(cond) == 1, press
    at = press.index(cond)
    block = press[at:press.index("}", at)]
    assert "Plugin.Instance.StartCoroutine(OpenPortalWhenSessionReady());" in block and "return;" in block, block
    assert press.index('if (!baseUrl.StartsWith("https://", StringComparison.OrdinalIgnoreCase))') < at, press
    assert press.count("MintPortalSessionAndOpen();") == 1 and press.index("MintPortalSessionAndOpen();") > at, press
    wait = code_of(API, "private static IEnumerator OpenPortalWhenSessionReady()")
    assert "while (string.IsNullOrEmpty(SteamAuth.SessionToken) && Time.realtimeSinceStartup < until)" in wait, wait
    assert wait.index("MintPortalSessionAndOpen();") > wait.index("while ("), wait
    finish = code_of(API, "private static void FinishPortalPress(SecureRouteRules.Conclusion c)")
    assert "host.StartCoroutine(OpenPortalWhenSessionReady());" in finish, finish
