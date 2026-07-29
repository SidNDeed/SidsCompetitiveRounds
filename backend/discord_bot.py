"""
Competitive ROUNDS Discord Bot
Environment: DISCORD_TOKEN, API_BASE_URL, LEADERBOARD_CHANNEL, SERIES_LOG_CHANNEL
"""
import os, asyncio, aiohttp, discord, json, io, threading
from typing import Literal
from discord import app_commands
from discord.ext import commands, tasks
from datetime import datetime, timezone, timedelta

# Chart rendering (/compare) — Agg backend (headless container, must be set
# BEFORE pyplot is imported). Guarded so the bot still boots on an image built
# before matplotlib landed in Dockerfile.bot; chart commands then reply with a
# friendly error instead of the whole bot crash-looping.
try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    _MPL_AVAILABLE = True
except Exception as _mpl_ex:
    _MPL_AVAILABLE = False
    print(f"[CHART] matplotlib unavailable ({_mpl_ex}) — chart commands disabled")

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "")
API_BASE_URL = os.getenv("API_BASE_URL", "http://api:8000")
LEADERBOARD_CHANNEL_ID = int(os.getenv("LEADERBOARD_CHANNEL", "0"))
SERIES_LOG_CHANNEL_ID = int(os.getenv("SERIES_LOG_CHANNEL", "0"))
QUEUE_BEACON_CHANNEL_ID = int(os.getenv("QUEUE_BEACON_CHANNEL", "0"))
CHAT_CHANNEL_ID = int(os.getenv("CHAT_CHANNEL", "1492022404829020230"))
ADMIN_CHANNEL_ID = int(os.getenv("ADMIN_CHANNEL", "1495392567687250061"))  # #scr-admin — anti-cheat flags
TOURNAMENT_CHANNEL_ID = int(os.getenv("TOURNAMENT_CHANNEL", "0"))  # set to enable #tournaments announcements
# Channel for new mod-release announcements. Bot polls the public GitHub
# releases API every 5 min; any new tag is posted here AND mirrored into
# the chat/discussions channel so people who don't watch #releases still
# see it. See poll_github_releases() below.
RELEASES_CHANNEL_ID = int(os.getenv("RELEASES_CHANNEL", "1498731888813277294"))
GITHUB_RELEASES_REPO = os.getenv("GITHUB_RELEASES_REPO", "SidNDeed/SidsCompetitiveRounds")
API_SECRET_KEY = os.getenv("API_SECRET_KEY", "")
# Live ranked-games channel — bot posts/updates an embed per active series with
# bet buttons (100/500/2000g per player). Bets fire via /api/v1/discord-bets
# which requires the user to have linked their Discord account in-game first.
LIVE_BETS_CHANNEL_ID = int(os.getenv("LIVE_BETS_CHANNEL", "1456460424831701074"))
# ── Gambler role: ping on every new open bet + self-serve opt-in/out ──────
# Sid created a "Gambler" role in the guild. Members opt in to get pinged
# whenever a new ranked match opens for betting. Opt-in/out is available BOTH
# via the /gambler slash command (toggle) AND by reacting (🎲) to a pinned
# signup message the bot maintains in the signup channel.
GAMBLER_ROLE_NAME = os.getenv("GAMBLER_ROLE", "Gambler")
# Where the 🎲 reaction-role signup message lives. Defaults to the live-bets
# channel so opt-in sits right next to the bets; override via env.
GAMBLER_SIGNUP_CHANNEL_ID = int(os.getenv("GAMBLER_SIGNUP_CHANNEL", str(LIVE_BETS_CHANNEL_ID)))
GAMBLER_EMOJI = "🎲"
# Marker stashed in the signup embed footer so the bot re-finds its own message
# after a restart instead of posting duplicates.
GAMBLER_SIGNUP_MARKER = "scr-gambler-signup-v1"
# ── LFP role ping (July 21): the in-game "LFP Ping" button queues a row in
# lfp_pings; poll_lfp_pings drains it into the queue-beacon channel with a
# ping to this role. Resolved by NAME at runtime — a missing role degrades to
# non-pinging plain text (gambler pattern); override via env on rename.
LFP_ROLE_NAME = os.getenv("LFP_ROLE", "Ranked Looking For Player")
# Bug reports auto-post here when players file via the F5 menu. ID gets a
# safe default so an unset env var doesn't crash the bot — 0 disables.
BUG_REPORTS_CHANNEL_ID = int(os.getenv("BUG_REPORTS_CHANNEL", "1501643180049960970"))
# Tournament board channel (#scr-tournaments) — one living message with the
# current sync + async tournament state, refreshed every 2 minutes.
SCR_TOURNAMENTS_CHANNEL = int(os.getenv("SCR_TOURNAMENTS_CHANNEL", "1158182455065452574"))

# Tournament trophy role names (set via env if they exist in the guild).
# Multi-win tracking uses an "(x2)" suffix variant of each role: a player with 1 win
# has "SCR Tournament Winner"; on their 2nd win we swap them to "SCR Tournament Winner (x2)".
# Participant uses its own "2" variant ("SCR Tournament Participant" -> "... Participant 2")
# rather than an (x2) suffix, per the Discord roles already configured in the guild.
TROPHY_ROLE_1 = os.getenv("TROPHY_ROLE_CHAMPION", "SCR Tournament Winner")
TROPHY_ROLE_2 = os.getenv("TROPHY_ROLE_RUNNER_UP", "SCR Tournament Runner Up")
TROPHY_ROLE_3 = os.getenv("TROPHY_ROLE_THIRD_PLACE", "SCR Tournament 3rd Place")
TROPHY_ROLE_PART = os.getenv("TROPHY_ROLE_PARTICIPANT", "SCR Tournament Participant")
TROPHY_ROLE_PART2 = os.getenv("TROPHY_ROLE_PARTICIPANT2", "SCR Tournament Participant 2")
TROPHY_X2_SUFFIX = " (x2)"

# July 28 rank reorganization (Stan's proposal): base-tier floors move to
# Intermediate 1500 / Advanced 1675 / Master 1980 (GM stays 2330), sub-tiers
# widen toward the bottom, and tier I is spelled out on every rank. Must stay
# in lockstep with main.py's RANK_TIERS (which strips the range suffix).
RANK_ROLES = [
    (2610, "Grand Master V 2610+"),
    (2540, "Grand Master IV 2540-2609"),
    (2470, "Grand Master III 2470-2539"),
    (2400, "Grand Master II 2400-2469"),
    (2330, "Grand Master I 2330-2399"),
    (2260, "Master V 2260-2329"),
    (2190, "Master IV 2190-2259"),
    (2120, "Master III 2120-2189"),
    (2050, "Master II 2050-2119"),
    (1980, "Master I 1980-2049"),
    (1910, "Advanced V 1910-1979"),
    (1845, "Advanced IV 1845-1909"),
    (1780, "Advanced III 1780-1844"),
    (1725, "Advanced II 1725-1779"),
    (1675, "Advanced I 1675-1724"),
    (1630, "Intermediate V 1630-1674"),
    (1590, "Intermediate IV 1590-1629"),
    (1555, "Intermediate III 1555-1589"),
    (1525, "Intermediate II 1525-1554"),
    (1500, "Intermediate I 1500-1524"),
    (1440, "Beginner V 1440-1499"),
    (1360, "Beginner IV 1360-1439"),
    (1260, "Beginner III 1260-1359"),
    (1140, "Beginner II 1140-1259"),
    (0,    "Beginner I 0-1139"),
]
ALL_RANK_ROLE_NAMES = [n for _, n in RANK_ROLES]

# Old guild role name -> new name, positionally (both ladders are the same
# 25 rungs top-to-bottom). Drives !setup_rank_roles: RENAME existing roles in
# place (keeps color, position, and members — the sync loop re-sorts members
# onto their new rungs afterwards), create only what's missing. The GM tiers
# II-V keep their exact old names, so their entries are identity mappings.
_OLD_RANK_ROLE_NAMES = [
    "Grand Master V 2610+",
    "Grand Master IV 2540-2609",
    "Grand Master III 2470-2539",
    "Grand Master II 2400-2469",
    "Grand Master 2330-2399",
    "Master V 2270-2329",
    "Master IV 2210-2269",
    "Master III 2150-2209",
    "Master II 2090-2149",
    "Master 2030-2089",
    "Advanced V 1980-2029",
    "Advanced IV 1930-1979",
    "Advanced III 1880-1929",
    "Advanced II 1830-1879",
    "Advanced 1780-1829",
    "Intermediate V 1740-1779",
    "Intermediate IV 1700-1739",
    "Intermediate III 1660-1699",
    "Intermediate II 1620-1659",
    "Intermediate 1580-1619",
    "Beginner V 1564-1579",
    "Beginner IV 1548-1563",
    "Beginner III 1532-1547",
    "Beginner II 1516-1531",
    "Beginner 1515>",
]
RANK_ROLE_RENAMES = list(zip(_OLD_RANK_ROLE_NAMES, ALL_RANK_ROLE_NAMES))

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
# Presence intent is privileged — must be enabled at https://discord.com/developers/applications/
# under Bot -> Privileged Gateway Intents -> PRESENCE INTENT.
# Controlled by env var so bot can start even without the intent granted.
# When False, /opp-online returns a friendly "presence tracking not enabled"
# message instead of trying to read member.status.
_PRESENCE_ENABLED = os.getenv("DISCORD_PRESENCE_INTENT", "false").lower() in ("true", "1", "yes")
intents.presences = _PRESENCE_ENABLED
bot = commands.Bot(command_prefix="!", intents=intents, chunk_guilds_at_startup=False)
http_session = None
seen_series = set()

async def api_get(path, timeout=8.0):
    try:
        # Every caller needs a bounded failure mode.  The FAQ Elo calculator
        # makes several reads before it can reply; aiohttp's default timeout is
        # minutes, which left Discord interactions "thinking" indefinitely
        # whenever the API or one DB query stalled. 8s suits the fast reads
        # every caller does today; a heavier endpoint can pass a larger timeout
        # rather than inheriting an unbounded wait.
        async with http_session.get(
            f"{API_BASE_URL}/api/v1{path}",
            timeout=aiohttp.ClientTimeout(total=timeout),
        ) as r:
            if r.status == 200:
                return await r.json()
            # A non-200 used to return None with no trace — consumers like the
            # leaderboard publisher then skip their tick SILENTLY, so a broken
            # endpoint reads as "the bot stopped updating" with empty logs.
            print(f"API GET {path.split('?')[0]} -> HTTP {r.status}")
            return None
    except Exception as e:
        print(f"API GET error: {e}"); return None

async def api_post(path, params=None):
    try:
        async with http_session.post(f"{API_BASE_URL}/api/v1{path}", params=params) as r:
            if r.status == 200: return await r.json()
            return {"error": await r.text(), "status": r.status}
    except Exception as e:
        print(f"API POST error: {e}"); return None


async def _handle_ticket_dm(message):
    """A user DMed the bot (not a command). Parse '#N <text>' / 'ticket N <text>'
    and post it as a comment on bug report N. The API verifies the DMer actually
    owns ticket N (their linked Discord must match the report's reporter)."""
    import re
    content = (message.content or "").strip()
    m = re.match(r'^(?:ticket\s*)?#?\s*(\d+)\s*[:.\-]?\s+(.+)$', content, re.IGNORECASE | re.DOTALL)
    if not m:
        await message.channel.send(
            "💬 To add to one of your bug reports, DM me like:\n"
            "`#12 it still happens after relaunching`\n"
            "(use your report number — shown when you submit, and in the F5 bug list). "
            "Your Discord must be linked in-game first: F5 → Home tab → Get Link Code, then `!link YOUR_CODE` here."
        )
        return
    num = int(m.group(1))
    body = m.group(2).strip()
    if not body:
        await message.channel.send(f"Add a message after the number, e.g. `#{num} more detail here`.")
        return
    if http_session is None or not API_SECRET_KEY:
        await message.channel.send("⚠️ The report system is temporarily unreachable — try again shortly.")
        return
    try:
        async with http_session.post(
            f"{API_BASE_URL}/api/v1/internal/bug-reports/by-number/{num}/user-comment",
            json={"discord_id": str(message.author.id), "comment": body},
            headers={"X-Internal-Key": API_SECRET_KEY},
            timeout=aiohttp.ClientTimeout(total=8),
        ) as resp:
            status = resp.status
            if status == 200:
                await message.channel.send(
                    f"✅ Added your note to bug report **#{num}** — it's on the ticket; "
                    "the team reviews reports regularly."
                )
            elif status == 403:
                await message.channel.send(
                    f"❌ Bug report **#{num}** isn't linked to your account (or it isn't yours). "
                    "Make sure your Discord is linked in-game: F5 → Home tab → Get Link Code, then `!link YOUR_CODE` here."
                )
            elif status == 404:
                await message.channel.send(f"❌ I couldn't find bug report **#{num}** — double-check the number.")
            else:
                t = await resp.text()
                print(f"[TICKET-DM] #{num} unexpected {status}: {t[:120]}")
                await message.channel.send("⚠️ Couldn't add that right now — try again in a moment.")
    except Exception as ex:
        print(f"[TICKET-DM] post error: {ex}")
        await message.channel.send("⚠️ Couldn't reach the report system — try again shortly.")

def get_rank_name(rating):
    for threshold, name in RANK_ROLES:
        if rating >= threshold: return name
    return RANK_ROLES[-1][1]

def rank_emoji(name):
    if "Grand Master" in name: return "🏆"
    if "Master" in name: return "⭐"
    if "Advanced" in name: return "🔷"
    if "Intermediate" in name: return "🔶"
    return "⚪"

def streak_str(streak):
    if streak > 0: return f"🔥 {streak}W streak"
    if streak < 0: return f"❄️ {-streak}L streak"
    return ""

async def update_member_role(member, rating):
    target = get_rank_name(rating)
    current = [r for r in member.roles if r.name in ALL_RANK_ROLE_NAMES]
    # Already exactly right -> zero API calls. The old remove+re-add on every
    # tick was 2 role edits per linked member per 30-min sync for members
    # whose rank never changed.
    if len(current) == 1 and current[0].name == target:
        return target
    if current: await member.remove_roles(*current, reason="Rank update")
    role = discord.utils.get(member.guild.roles, name=target)
    if role: await member.add_roles(role, reason=f"Rated {rating:.0f}")
    return target

async def find_member(guild, discord_id):
    try: return guild.get_member(int(discord_id)) or await guild.fetch_member(int(discord_id))
    except: return None

@bot.event
async def on_ready():
    global http_session
    # Default the X-Internal-Key header on every request so the API's version-gate middleware
    # bypasses the bot. (The mod sends X-Mod-Version; the bot sends X-Internal-Key. Either
    # is sufficient.) Per-call headers can still override or add to this default.
    default_headers = {"X-Internal-Key": API_SECRET_KEY} if API_SECRET_KEY else {}
    http_session = aiohttp.ClientSession(headers=default_headers)
    try: await bot.tree.sync()
    except Exception as e: print(f"Tree sync error: {e}")
    if not poll_recent_series.is_running(): poll_recent_series.start()
    if not sync_roles_periodic.is_running(): sync_roles_periodic.start()
    if not poll_queue_beacon.is_running(): poll_queue_beacon.start()
    if not poll_team_queue_beacon.is_running(): poll_team_queue_beacon.start()
    if not poll_ovt_queue_beacon.is_running(): poll_ovt_queue_beacon.start()
    if not poll_ffa_queue_beacon.is_running(): poll_ffa_queue_beacon.start()
    if not poll_ffa_recent_matches.is_running(): poll_ffa_recent_matches.start()
    if not poll_team_recent_series.is_running(): poll_team_recent_series.start()
    if not poll_anticheat_flags.is_running(): poll_anticheat_flags.start()
    if not poll_new_bans.is_running(): poll_new_bans.start()
    if not poll_github_releases.is_running(): poll_github_releases.start()
    if not poll_live_bets.is_running(): poll_live_bets.start()
    if not poll_team_live_bets.is_running(): poll_team_live_bets.start()
    if not poll_ffa_live_bets.is_running(): poll_ffa_live_bets.start()
    if not poll_gambler_pings.is_running(): poll_gambler_pings.start()
    if not poll_chat_catchup.is_running(): poll_chat_catchup.start()
    if not poll_tournaments.is_running(): poll_tournaments.start()
    if not nag_pending_async_matches.is_running(): nag_pending_async_matches.start()
    if not poll_bug_reports.is_running(): poll_bug_reports.start()
    if not poll_bug_report_events.is_running(): poll_bug_report_events.start()
    if not push_rank_role_colors.is_running(): push_rank_role_colors.start()
    if not grant_booster_gold.is_running(): grant_booster_gold.start()
    if not poll_channel_posts.is_running(): poll_channel_posts.start()
    if not publish_lb_loop.is_running(): publish_lb_loop.start()
    if not poll_tournament_notices.is_running(): poll_tournament_notices.start()
    if not publish_tournament_board.is_running(): publish_tournament_board.start()
    if not poll_pending_dms.is_running(): poll_pending_dms.start()
    if not poll_lfp_pings.is_running(): poll_lfp_pings.start()
    # Chat bridge: subscribe to the WS firehose so we can forward in-game
    # messages to the Discord channel. Discord -> in-game goes the other way
    # via on_message below. The poll_chat_catchup task above is a belt-and-
    # suspenders backfill in case any WS broadcast gets silently dropped (e.g.
    # the chat_manager broadcast loop skipped a subscriber due to a transient
    # send failure that didn't propagate as an exception).
    asyncio.create_task(chat_ws_listener())
    # One-shot backfill — resolve Discord usernames for any player that was
    # linked before the discord_username column existed.
    asyncio.create_task(backfill_discord_usernames())
    # One-shot mirror of the last few #scr-releases posts (v1.33 Home tab).
    asyncio.create_task(backfill_release_posts())
    print(f"Bot ready: {bot.user} (guilds: {len(bot.guilds)}, chat={CHAT_CHANNEL_ID}, admin={ADMIN_CHANNEL_ID})")


async def backfill_discord_usernames():
    """July 22 (items 8+9): the players table now splits Discord identity into
    discord_username (the unique @handle, user.name — Home tab shows this) and
    discord_display_name (global display name — leaderboard opt-in shows this).
    Legacy rows held DISPLAY names in discord_username, so this sweep now
    re-resolves EVERY linked row (endpoint returns stored values so unchanged
    rows are skipped — no N no-op POSTs on every restart)."""
    if not http_session or not API_SECRET_KEY:
        return
    await asyncio.sleep(5)  # give the API a moment to settle after bot restart
    try:
        async with http_session.get(
            f"{API_BASE_URL}/api/v1/admin/missing-discord-usernames",
            headers={"X-Internal-Key": API_SECRET_KEY},
            timeout=aiohttp.ClientTimeout(total=10),
        ) as resp:
            if resp.status != 200:
                print(f"[BACKFILL] missing-discord-usernames returned {resp.status}"); return
            data = await resp.json()
    except Exception as e:
        print(f"[BACKFILL] failed to fetch list: {e}"); return

    rows = data.get("players") or [{"discord_id": d} for d in data.get("discord_ids", [])]
    if not rows:
        print("[BACKFILL] No Discord usernames to backfill"); return
    print(f"[BACKFILL] Checking {len(rows)} linked Discord identities")
    resolved = 0
    for row in rows:
        did = row.get("discord_id")
        if not did:
            continue
        try:
            # Review [10]: fetch_user is an HTTP call for every UNCACHED user —
            # pace the fetch itself, not just the update path, or the sweep
            # bursts the whole linked set at Discord in one go.
            user = bot.get_user(int(did))
            if user is None:
                await asyncio.sleep(0.15)
                user = await bot.fetch_user(int(did))
            if user is None: continue
            username = user.name                                        # the unique @handle
            display = getattr(user, "global_name", None) or user.name   # what people see
            if (row.get("discord_username") == username
                    and row.get("discord_display_name") == display):
                continue  # already correct — skip the POST entirely
            await http_session.post(
                f"{API_BASE_URL}/api/v1/admin/set-discord-username",
                json={"discord_id": str(did), "discord_username": username,
                      "discord_display_name": display},
                headers={"X-Internal-Key": API_SECRET_KEY},
                timeout=aiohttp.ClientTimeout(total=5),
            )
            resolved += 1
            await asyncio.sleep(0.2)
        except discord.NotFound:
            continue
        except Exception as e:
            print(f"[BACKFILL] {did}: {e}")
    print(f"[BACKFILL] Updated {resolved}/{len(rows)} Discord identities")


# ══ FAQ auto-responder (v1.33) ═══════════════════════════════════════════
# Answers common questions automatically, in Discord AND in the in-game chat
# bridge. Matching is two-layer: tolerant keyword regexes (strong signal),
# then difflib fuzzy match against canonical example questions (catches
# rephrasings). Cooldowns keep it from spamming: one answer per topic per
# channel per 3 min, one answer per user per 20s.
import re as _faq_re
import time as _faq_time
import difflib as _faq_difflib

FAQ_INFO_CHANNEL = "<#1159243585309384805>"       # #ranked-information
FAQ_INSTALL_CHANNEL = "<#1491701002267791401>"    # #scr-competitive-rounds-how-to-install
FAQ_GENERAL_MODS_CHANNEL = "<#1137267505673547846>" # #how-to-install-mods
FAQ_MODPACKS_CHANNEL = "<#1137271024132571156>"    # #mod-packs
FAQ_MODPACK_CODE = "019f642f-9c88-f5f7-5199-41b4b7d30ebf"
FAQ_THUNDERSTORE_URL = "https://thunderstore.io/c/rounds/p/Team_Sid/SidsCompetitiveRounds/"
FAQ_HELPER_NAME = "SCR Helper"

_FAQ_KEY_COOLDOWN = 180.0   # same topic, same channel/scope
_FAQ_USER_COOLDOWN = 20.0   # any topic, same asker
_faq_key_at: dict = {}
_faq_user_at: dict = {}


def _faq_rate_ok(scope, key, user_key) -> bool:
    """Check + stamp both cooldowns atomically (synchronous, no awaits)."""
    now = _faq_time.monotonic()
    if now - _faq_key_at.get((scope, key), 0.0) < _FAQ_KEY_COOLDOWN:
        return False
    if user_key is not None and now - _faq_user_at.get(user_key, 0.0) < _FAQ_USER_COOLDOWN:
        return False
    _faq_key_at[(scope, key)] = now
    if user_key is not None:
        _faq_user_at[user_key] = now
    return True


def _faq_norm(text: str) -> str:
    """Lowercase, strip mention/emoji tokens and curly quotes, collapse spaces."""
    t = (text or "").lower()
    t = _faq_re.sub(r"<[@#:][^>]{0,40}>", " ", t)   # <@id> <#id> <:emoji:id>
    t = t.replace("’", "'").replace("‘", "'")
    t = _faq_re.sub(r"\s+", " ", t).strip()
    return t


_FAQ_QUESTION_RE = _faq_re.compile(
    r"(\?|^(how|what|whats|what's|where|when|who|whos|who's|why|can|could|does|do|is|are|any|which|help|"
    r"explain|list|show|fastest)\b"
    r"|\b(how do i|how to|what is|where is|can i|does the|is there|anyone know))")


def _faq_question_like(norm: str) -> bool:
    return bool(_FAQ_QUESTION_RE.search(norm))


_FAQ_FUZZY_STOPWORDS = frozenset({
    "a", "about", "an", "and", "any", "are", "can", "could", "do", "does",
    "file", "for", "here", "how", "i", "in", "install", "installer", "is",
    "it", "me", "my", "of", "on", "please", "safe", "series", "some",
    "system", "the", "there", "this", "to", "we", "what",
    "whats", "where", "which", "who", "why", "with", "work", "works", "you",
})


def _faq_topic_tokens(text: str) -> set:
    """Meaning-bearing tokens for the fuzzy layer.

    Whole-sentence similarity alone treats short questions such as
    "how does grow work" and "how does ranked work" as near-duplicates.
    Requiring one exact or typo-close topic token preserves useful typo
    matching without allowing question scaffolding to choose the topic.
    """
    return {
        token for token in _faq_re.findall(r"[a-z0-9]+", text or "")
        if len(token) >= 3 and token not in _FAQ_FUZZY_STOPWORDS
    }


def _faq_topics_overlap(left: set, right: set) -> bool:
    if not left or not right:
        return False
    for a in left:
        for b in right:
            if a == b or _faq_difflib.SequenceMatcher(None, a, b).ratio() >= 0.84:
                return True
    return False


def _faq_plainify(text: str, cap: int = 420) -> str:
    """Discord-markdown answer -> ASCII-safe in-game chat text. ROUNDS' SDF
    font renders em-dash/bullets/multiplication-sign as squares (learning
    #47), and channel mentions are meaningless in-game."""
    t = _faq_re.sub(r"<#\d+>", "the Discord server", text)
    t = _faq_re.sub(r"<@!?\d+>", "them", t)
    t = t.replace("**", "").replace("__", "").replace("`", "")
    for bad, good in (("—", "-"), ("–", "-"), ("×", "x"), ("•", "-"),
                      ("→", "->"), ("’", "'"), ("“", '"'), ("”", '"'),
                      ("·", "-"), ("✅", ""), ("❌", "")):
        t = t.replace(bad, good)
    t = "".join(ch if ord(ch) < 128 else " " for ch in t)
    t = _faq_re.sub(r"[ \t]+", " ", t)
    t = _faq_re.sub(r"\n{2,}", "  ", t).replace("\n", "  ").strip()
    if len(t) > cap:
        t = t[:cap - 3].rstrip() + "..."
    return t


def _rank_roles_faq_answer() -> str:
    lines = "\n".join(f"• {name}" for _, name in RANK_ROLES)
    return ("Discord rank roles track your live 1v1 rating (synced every ~30 min, "
            "needs a linked account — ask me *how do I link my account*). "
            "Everyone starts at **1500**.\n" + lines)


_FAQ_ACHIEVEMENTS_TEXT = (
    "**40 achievements**, each a one-time challenge paying **100g** "
    "(the two *Slayer* trophies pay **1000g**; some unlock exclusive titles). "
    "Track your progress in-game: **F5 → Achievements**.\n"
    "• **Untouchable** — win a game without taking damage\n"
    "• **Pacifist** — win a game without firing a shot\n"
    "• **Immovable Object** — win without moving or jumping\n"
    "• **Grounded** — win without ever jumping\n"
    "• **Instinct** — win taking only the left-most card on every pick\n"
    "• **Silent Assassin / Total Mayhem / Fragile Perfection / No Escape** — 5-0 someone with Sneaky / Mayhem / Glass Cannon / Chase\n"
    "• **Rise from the Ashes** — win 5-0 with Phoenix without losing a life\n"
    "• **Bullet Hell / Spray and Pray / Demolitionist / Controlled Burst / Field Medic** — win 5-0 with Barrage / Spray / Explosive Bullet / Burst / Healing Field in your build\n"
    "• **The Comeback Kid** — win after being down 0-4 · **Clutch** — win from 0-3\n"
    "• **Stacked Deck** — 5 copies of one card · **Collector** — 4 copies\n"
    "• **Double Nova / Lumberjack / Pristine Perfection / Living on the Edge** — win with two+ Supernovas / Saws / Pristines / Glass Cannons\n"
    "• **Silly Drill** — win with Sneaky + Drill · **Sustained Power** — win with Empower + Healing Field\n"
    "• **God Build** — win with Shields Up, exactly 1 ammo, and a lightning-fast reload\n"
    "• **Into the Deep End** — win with Abyssal Countdown as your FIRST pick, activating it every round\n"
    "• **Flawless** — five 5-0 wins in a row\n"
    "• **Rising Star / Master / Grand Master** — reach 1700 / 1980 / 2330 rating (1v1 or 2v2)\n"
    "• **Tag Team Sweep** — win a 2v2 game 5-0\n"
    "• **On Fire / Unstoppable / Immortal** — win 25 / 50 / 100 ranked series in a row\n"
    "• **Century Club / Casual Conqueror / Touch Grass** — win 100 / 200 / 500 casual games in a row\n"
    "• **Sid Slayer / Stan Slayer** — beat Sid / Stan in a ranked series (**1000g**)"
)


async def _faq_top_player(message):
    """Dynamic: read the live leaderboard and name the top player(s)."""
    data = await api_get("/leaderboard?limit=3&min_matches=1")
    entries = (data or {}).get("entries") or []
    if not entries:
        return "Couldn't reach the leaderboard right now — try `/lb` in a minute."
    top = entries[0]
    line = (f"Right now the top-rated player is **{top['display_name']}** at "
            f"**{top['rating']}** ({top['wins']}W/{top['losses']}L).")
    if len(entries) >= 3:
        line += (f"\nPodium: 🥇 {entries[0]['display_name']} ({entries[0]['rating']}) · "
                 f"🥈 {entries[1]['display_name']} ({entries[1]['rating']}) · "
                 f"🥉 {entries[2]['display_name']} ({entries[2]['rating']})")
    line += "\nFull board: `/lb`, the #scr-leaderboard channel, or F5 → Leaderboard in-game."
    return line


async def _faq_discord_link(discord_id):
    """Return (state, payload): state is ok, unlinked, or error.

    The shared api_get intentionally collapses non-200 and transport failure to
    None for simple pollers. The Elo calculator must distinguish a real 404
    from an API timeout or it falsely tells linked players to link again.
    """
    try:
        async with http_session.get(
            f"{API_BASE_URL}/api/v1/players/by-discord/{discord_id}",
            timeout=aiohttp.ClientTimeout(total=8),
        ) as r:
            if r.status == 200:
                return "ok", await r.json()
            if r.status == 404:
                return "unlinked", None
            print(f"API GET /players/by-discord/{{id}} -> HTTP {r.status}")
            return "error", None
    except Exception as ex:
        print(f"API GET /players/by-discord/{{id}} error: {ex}")
        return "error", None


async def _faq_elo_delta(message):
    """Dynamic: Glicko preview between the asker and a mentioned player (or
    between the first two mentioned players). Mentions are taken from the
    message CONTENT in text order — Message.mentions is unordered and also
    includes the replied-to author on ping-replies, which would silently
    compute the wrong pair. A dict request is used by the slash-command form,
    where discord.py has no backing Message object."""
    if message is None:
        return None
    if isinstance(message, dict):
        content = message.get("content") or ""
        author = message.get("author")
        guild = message.get("guild")
        known_mentions = message.get("mentions") or []
    else:
        content = message.content or ""
        author = message.author
        guild = message.guild
        known_mentions = message.mentions

    by_id = {str(m.id): m for m in known_mentions}
    mentions, seen_ids = [], set()
    for mid in _faq_re.findall(r"<@!?(\d+)>", content):
        m = by_id.get(mid)
        if m is None and guild is not None:
            m = guild.get_member(int(mid))
        if m is None:
            m = bot.get_user(int(mid))
        if m is None:
            try:
                m = await bot.fetch_user(int(mid))
            except Exception:
                m = None
        if m is None or m.bot or m.id in seen_ids:
            continue
        seen_ids.add(m.id)
        mentions.append(m)
    if not mentions:
        return ("Mention the opponent and I'll calculate it, e.g. "
                "*how much elo would I gain against @player?* "
                "(both accounts need to be linked — `/link`).")
    if len(mentions) >= 2:
        user_a, user_b = mentions[0], mentions[1]
    else:
        user_a, user_b = author, mentions[0]
    if user_a is None:
        return "Couldn't identify the first player — mention both players and try again."

    # These lookups are independent. Running them together halves normal
    # latency and, paired with api_get's timeout, guarantees this interaction
    # reaches either a result or a friendly failure instead of hanging.
    result_a, result_b = await asyncio.gather(
        _faq_discord_link(user_a.id),
        _faq_discord_link(user_b.id),
    )
    state_a, link_a = result_a
    state_b, link_b = result_b
    if state_a == "error" or state_b == "error":
        return "Couldn't reach the player database right now — try again in a minute."
    if state_a == "unlinked":
        return f"❌ {user_a.display_name} isn't linked yet — they need `/link` first."
    if state_b == "unlinked":
        return f"❌ {user_b.display_name} isn't linked yet — they need `/link` first."
    prev = await api_get(f"/players/{link_a['steam_id']}/rating-preview"
                         f"?opponent_steam_id={link_b['steam_id']}")
    if not prev:
        return "Couldn't compute that right now — try again in a minute."
    pa, pb = prev["player"], prev["opponent"]
    prob = prev.get("win_probability", 0.5)
    return (f"**{pa['display_name']}** ({pa['rating']:.0f}) vs **{pb['display_name']}** ({pb['rating']:.0f}) — "
            f"if {pa['display_name']} wins the ranked series: **+{pa['win_delta']:.1f}**, "
            f"if they lose: **{pa['loss_delta']:.1f}**.\n"
            f"{pb['display_name']}'s side: win **+{pb['win_delta']:.1f}** / loss **{pb['loss_delta']:.1f}**. "
            f"Win probability for {pa['display_name']}: **{prob * 100:.0f}%**.\n"
            f"*(Glicko-2 — ratings move per completed BO3 series, and swings shrink "
            f"as your rating settles.)*"
)


# Entry fields: key, title (embed title), patterns (tolerant regexes over the
# normalized message — a hit is a strong signal), examples (canonical question
# phrasings for the fuzzy layer), answer (markdown str) OR handler (async,
# returns markdown str/None), short (optional explicit in-game text; default
# is _faq_plainify(answer)), require_question (default True — fuzzy/regex only
# fires on question-shaped messages; False for statement-shaped complaints),
# discord_only (default False — True when the answer needs Discord features
# like mentions). ORDER MATTERS: first regex hit wins, so specific entries
# sit above general ones.
FAQ_ENTRIES = [
    {
        "key": "elo_delta",
        "title": "Elo gain/loss calculator",
        "patterns": [
            r"how (much|many) (elo|rating|points?).{0,40}(gain|lose|get|win|drop)",
            r"(gain|lose|win|get|drop).{0,25}(elo|rating|points?).{0,30}(against|vs|playing|if i (beat|play|lose))",
            r"(elo|rating).{0,20}(gain|lose|change).{0,30}(against|vs)",
        ],
        "examples": ["how much elo will i gain if i play against @player",
                     "how much rating do i lose against @player"],
        "handler": _faq_elo_delta,
        "error_answer": "Couldn't compute that right now — the calculator timed out. Try again in a minute.",
        "discord_only": True,
    },
    {
        "key": "top_player",
        "title": "Who's the top player?",
        "patterns": [
            r"who('?s| is|s)\b.{0,20}(best|top|highest|number ?(one|1)|#? ?1)",
            r"(best|top|highest.rated) player",
            r"who'?s?\b.{0,25}rank(ed)? ?(1|one|first)\b",
        ],
        "examples": ["who is the best player", "who is the top player here"],
        "handler": _faq_top_player,
    },
    {
        "key": "community_modpacks",
        "title": "Community mod packs",
        "patterns": [
            r"(cool|good|balanced|fun|recommended|recommend|best).{0,30}mod ?packs?",
            r"mod ?packs?.{0,25}(cool|good|balanced|fun|recommended|recommend|best)",
            r"where.{0,25}(find|get|see).{0,20}mod ?packs?",
        ],
        "examples": ["is there a cool balanced mod pack", "where can i find community mod packs"],
        "answer": (f"Yes — browse {FAQ_MODPACKS_CHANNEL}. That channel is for community ROUNDS mod packs "
                   "and balance packs.\n"
                   "If you meant the clean **SCR-only** r2modman profile instead, ask for the "
                   "*SCR modpack code*."),
    },
    {
        "key": "modpack_code",
        "title": "SCR modpack code",
        "patterns": [
            r"mod ?pack.{0,20}code",
            r"(r2modman|thunderstore).{0,20}(profile|import).{0,10}code",
            r"(scr|competitive).{0,20}(profile|mod ?pack)",
            r"profile (import )?code",
        ],
        "examples": ["what is the modpack code", "is there a modpack code"],
        "answer": (f"Yes — modpack code: `{FAQ_MODPACK_CODE}`\n"
                   "In **r2modman** (or the Thunderstore app): **Profiles → Import new profile → "
                   "Import profile using code**, paste the code, and it builds the exact profile for you. "
                   "Then **launch ROUNDS through the mod manager**, not plain Steam."),
        "short": ("Modpack code: " + FAQ_MODPACK_CODE + " - in r2modman: Profiles -> Import new "
                  "profile -> Import using code, then launch ROUNDS through the mod manager."),
    },
    {
        "key": "mods_not_working",
        "title": "SCR mod not working — checklist",
        "patterns": [
            r"(scr|competitive rounds|sid'?s competitive rounds|the scr mod|this mod|the mod).{0,40}(not|isn'?t|won'?t|wont|stopped|broken|doesn'?t|dont|don'?t).{0,20}(work|load|show|start|open|run)",
            r"(not|isn'?t|won'?t|wont|stopped|broken|doesn'?t).{0,20}(scr|competitive rounds|the scr mod|this mod|the mod).{0,15}(work|load|show|start|open|run)",
            r"(scr|the scr mod|the mod|this mod) (is )?disabled",
            r"f5 (does nothing|not work|doesn'?t work|wont work|won'?t work)",
        ],
        "examples": ["the scr mod isn't working", "the mod won't load", "scr not working"],
        "require_question": False,
        "answer": ("Quick checklist:\n"
                   "1. **ROUNDS version** — SCR needs the **current** ROUNDS (v1.1.2) on the **default** Steam branch. "
                   "The `old-rounds-for-mods` beta branch is for every *other* ROUNDS mod — SCR won't run there "
                   "(and other mods won't run on current ROUNDS).\n"
                   "2. **No other mods** — SCR disables itself if it detects any other BepInEx plugin. "
                   "Use a clean r2modman profile with only SCR.\n"
                   "3. **Thunderstore installs must launch through the mod manager**, not plain Steam.\n"
                   "4. Restart ROUNDS and press **F5** — if the menu opens, you're good.\n"
                   "5. Still broken? Reinstall with `CompetitiveRoundsInstaller.exe` from the #releases pins, "
                   "and file a bug report (**F5 → Settings → Report a Bug**, tick *attach log*).\n"
                   f"Full install walkthrough: {FAQ_INSTALL_CHANNEL}"),
    },
    {
        "key": "general_mods_not_working",
        "title": "ROUNDS mods not working",
        "patterns": [
            r"\bmy mods?\b.{0,35}(not|isn'?t|aren'?t|won'?t|wont|stopped|broken|doesn'?t|dont|don'?t).{0,20}(work|load|show|start|open|run)",
            r"\bmods\b.{0,30}(not|aren'?t|won'?t|wont|stopped|broken|dont|don'?t).{0,20}(work|load|show|start|open|run)",
            r"help.{0,20}(my )?mods?\b",
        ],
        "examples": ["my mods aren't working", "help my rounds mods won't load"],
        "require_question": False,
        "answer": (f"Use the **Mods not working checklist** in {FAQ_GENERAL_MODS_CHANNEL}. That channel covers "
                   "normal modded ROUNDS profiles.\n"
                   "If you specifically mean **Sid's Competitive Rounds**, say *the SCR mod isn't working* "
                   "and I'll give you SCR's separate checklist."),
    },
    {
        "key": "vanilla_lobbies",
        "title": "Vanilla lobbies & normal matchmaking",
        "patterns": [
            r"(can|could|will|do|does).{0,35}(play|join|use).{0,25}(vanilla|normal|regular|unmodded|casual).{0,20}(lobby|lobbies|lobbys|matchmaking|quick ?match|players?)",
            r"(does|is).{0,15}(normal|regular|vanilla).{0,15}matchmaking.{0,15}(work|still)",
            r"play with.{0,25}(friends|people|players).{0,20}without.{0,15}mod",
            r"(still )?play.{0,15}(against|with).{0,15}(vanilla|unmodded|normal) players?",
            r"play.{0,15}(randos|randoms|random people|random players).{0,35}(scr|competitive|mod)",
            # Bare phrasing without a play/join/use verb, e.g. "do vanilla
            # lobbies still work?" — deliberately NOT matching "casual
            # matchmaking" (that was the false positive), so this requires
            # vanilla/unmodded/regular/normal paired with an actual lobby word.
            r"(vanilla|unmodded|regular|normal) (lobby|lobbies|lobbys)",
        ],
        "examples": ["can i still play in vanilla lobbies", "does normal matchmaking still work",
                     "do vanilla lobbies still work", "can i play random people with the scr mod"],
        "answer": ("**Yes.** Normal Photon matchmaking and vanilla lobbies work exactly as before with the mod "
                   "installed — Sid was given permission by Landfall to publish the mod with normal matchmaking "
                   "enabled, as long as it doesn't change gameplay or inhibit unmodded players.\n"
                   "Games against vanilla (unmodded) players simply record as **casual** — they can never be ranked."),
    },
    {
        "key": "other_mods",
        "title": "Compatibility with other mods",
        "patterns": [
            r"(work|compatible|compatibility|use|run).{0,25}other mods",
            r"other mods.{0,25}(work|compatible|allowed|ok)",
            r"can i (use|run|add|install).{0,20}(another|other|more) mods?",
            r"(willow|pykess|unbound|moddingutils).{0,20}(work|compatible)",
        ],
        "examples": ["does the mod work with other mods", "can i use other mods with this"],
        "answer": ("**No** — there are no compatible mods, and all other mods are blacklisted. SCR is a competitive "
                   "mod: it **disables itself at launch** if it detects any other BepInEx plugin, to keep matches fair.\n"
                   "Use a clean r2modman profile with only SCR. (Other ROUNDS mods target the `old-rounds-for-mods` "
                   "beta branch anyway, so they wouldn't run alongside SCR's current-version requirement.)"),
    },
    {
        # Sits ABOVE the ranked/2v2 cluster: "how does 2v2 betting work" must
        # land here, not on how_2v2's looser '2v2 ... work' pattern.
        "key": "gambling",
        "title": "How betting works",
        "patterns": [
            r"how.{0,25}(gambling|betting|bets?|gamble|wager).{0,15}(work|works)",
            r"(explain|what is).{0,15}(the )?(gambling|betting|bets? system)",
            r"how (do|can) i (bet|gamble|wager)",
        ],
        "examples": ["how does the gambling system work", "how do i bet on games"],
        "answer": ("You bet **gold** on other players' **live ranked series**:\n"
                   "• **In-game**: F5 → Leaderboard tab → the live-series panel. **Discord**: the live-bet buttons "
                   "the bot posts in the bets channel (needs a linked account — `/link`).\n"
                   "• Stake **1–2000g**, one bet per series, and you can't bet on your own match.\n"
                   "• **Odds** come from Glicko win-probability: 1.01×–3.0× payout. The cap shrinks when either "
                   "player's rating is still uncertain (no farming fresh accounts), and bets under 1.10× are "
                   "rejected as no-profit.\n"
                   "• Bets **lock** once game 1 reaches 2 points (3 in private rooms) or any game is decided.\n"
                   "• Payout = stake × odds. If a series never finishes, stakes **auto-refund** (~1 hour).\n"
                   "• Want a ping when betting opens? Grab the **Gambler** role — react 🎲 on the signup message "
                   "in the bets channel."),
    },
    {
        "key": "game_not_counted",
        "title": "Why didn't my game count as ranked?",
        "patterns": [
            r"(game|match|series|win).{0,30}(didn'?t|didnt|not|never|no).{0,15}(count|record|show|track|register)",
            r"missing (game|match|elo|rating|series)",
            r"(didn'?t|didnt|not) (get|gain|lose) (any )?(elo|rating)",
            r"why.{0,15}(casual|unranked).{0,25}(instead|not ranked)",
        ],
        "examples": ["why didn't my game count as ranked", "my match didn't record"],
        "require_question": False,
        "answer": ("A match records as **ranked** only when **both** players have the mod running **and** ranked "
                   "enabled (F5 → Ranked tab). Everything else records as casual — still tracked, no rating change.\n"
                   "• Games vs vanilla players can never be ranked.\n"
                   "• Queue matches are always ranked (queueing is consent).\n"
                   "• Ranked is a **best-of-3 series** — rating applies when the series **completes**, not per game.\n"
                   "• Interrupted series (crash/DC) **resume where they left off** — just rematch the same player, "
                   "no matter how much later. Unfinished series never expire.\n"
                   "If a game is genuinely missing, file a bug report: F5 → Settings → Report a Bug (attach log)."),
    },
    {
        "key": "grow_card",
        "title": "How Grow works",
        "patterns": [
            r"how.{0,15}\bgrow\b.{0,12}(work|works)",
            r"\bgrow\b.{0,25}(fps|frame ?rate|frames?|frame based)",
            r"(fps|frame ?rate|frames?|frame based).{0,25}\bgrow\b",
        ],
        "examples": ["how does grow work", "is grow fps based"],
        "answer": ("**Grow** makes a bullet gain damage the longer it stays in flight, so long-distance and "
                   "slow-projectile shots benefit most.\n"
                   "**Yes, vanilla Grow is frame-rate dependent.** Its growth is not fully normalized to elapsed "
                   "time, so the result can vary with FPS. SCR currently records and organizes matches but does "
                   "not alter Grow's gameplay code."),
    },
    {
        "key": "ranked_explained",
        "title": "How ranked works",
        "patterns": [
            r"how (does|do) (the )?(ranked|ranks|rank|rating|elo( system)?|ranking|glicko|series) (system )?work",
            r"(explain|what is) (ranked|the ranked system|ranks|elo|the elo system|glicko)",
            r"what.{0,10}(bo3|best of (3|three))",
        ],
        "examples": ["how does ranked work", "how do ranks work", "explain the ranked system",
                     "how does the elo system work"],
        "answer": ("• Ranked plays as a **best-of-3 series** vs the same opponent — first to 2 game wins. Your "
                   "**Glicko-2** rating updates when the series completes (that's elo with an uncertainty value: "
                   "new/returning players swing harder, established ratings move less).\n"
                   "• Both players need the mod + ranked enabled; queue matches are always ranked.\n"
                   "• Interrupted series resume on rematch — they never expire, so leaving can't save your rating.\n"
                   "• Leaving mid-series counts as a DC on your leave %, which is visible on the leaderboard.\n"
                   "• Your rating drives the **rank roles on the Discord sidebar** (Beginner → Intermediate → "
                   "Advanced → Master → Grand Master) — ask me *what are the elo requirements for each rank* for "
                   "the full table.\n"
                   f"More detail: {FAQ_INFO_CHANNEL}"),
    },
    {
        "key": "what_is_series",
        "title": "What is a ranked series?",
        "patterns": [
            r"what('?s| is) (a |the )?(ranked )?series",
            r"ranked series.{0,15}(mean|work|works)",
            r"how (does|do) (a |the )?(ranked )?series work",
            r"what('?s| is) (a )?(bo3|best of (3|three))",
        ],
        "examples": ["what is a series", "what does ranked series mean"],
        "answer": ("A **series** is a best-of-3 set of full ROUNDS games against the same opponent. The first "
                   "player to win **2 games** wins the series, and Glicko rating changes once at that point — "
                   "not after every game.\n"
                   "If someone disconnects before it is decided, the series stays open and resumes at the same "
                   "score when those players meet again."),
    },
    {
        "key": "turn_off_ranked",
        "title": "Playing casual only",
        "patterns": [
            r"(turn|switch|toggle).{0,10}(off|disable).{0,10}ranked",
            r"ranked off\b",
            r"play (only )?casuals? only",
            r"(disable|opt out of) ranked",
        ],
        "examples": ["how do i turn ranked off", "can i play casual only"],
        "answer": ("F5 → Ranked tab → the **Enable/Disable** button. With ranked off, your games record as casual "
                   "(stats tracked, no rating change) — and none of your opponents' games vs you can be ranked "
                   "either, since ranked needs **both** players opted in."),
    },
    {
        "key": "how_2v2",
        "title": "How 2v2 works",
        "patterns": [
            r"how.{0,25}(play|do|start|queue|join).{0,10}2 ?v ?2",
            r"2 ?v ?2.{0,20}(work|works|queue|ranked|rating)",
            r"(team|duo) (ranked|queue)",
        ],
        "examples": ["how do i play 2v2s", "how does 2v2 ranked work"],
        "answer": ("**F5 → Multiplayer → 2v2.** Two queues:\n"
                   "• **Search Random** — solo/duo queue, teams auto-balanced by rating.\n"
                   "• **Find Custom Lobby** — you pick your team: grab 3 friends, everyone joins the lobby queue, "
                   "it locks as soon as 4 are in (no rating filter — playing with your friends is the point).\n"
                   "2v2 has its **own Glicko rating and leaderboard**, plus its own gold/XP (600 XP base per game, "
                   "~900 on a win; 50g series win / 25g loss — both scaled up to ×3 by the opposing team's rank "
                   "tier). Series are BO3 like 1v1; the crown renders on both members of the leading team.\n"
                   "Known issues: the big recording bugs were fixed in v1.31 — if a series looks unrecorded, "
                   "file a bug report (F5 → Settings → Report a Bug) so it can be chased down."),
    },
    {
        "key": "questions_channel",
        "title": "Questions & ranked information",
        "patterns": [
            r"(is there|where('?s| is)).{0,20}(a )?(questions?|help|information|info).{0,12}channel",
            r"(questions?|ask questions?).{0,20}(channel|where)",
        ],
        "examples": ["is there a questions channel", "where should i ask ranked questions"],
        "answer": (f"Start with {FAQ_INFO_CHANNEL}. It has the ranked overview and is the right place to find "
                   "answers or ask SCR/ranked questions."),
    },
    {
        "key": "room_codes",
        "title": "Joining with a room code",
        "patterns": [
            r"(join|enter|input|type|use).{0,20}(a )?room ?codes?",
            r"room ?codes?.{0,25}(join|enter|input|type|use|work|works)",
            r"what (do|should) i do with.{0,15}(the )?room ?code",
            r"(special way|how).{0,25}(meet up|play together).{0,35}(mod|online|room|code)",
            r"(meet up|connect).{0,35}(type|enter).{0,20}(online|room|code)",
        ],
        "examples": ["how do i join room codes", "what do i do with the room code",
                     "do i type the room code into online like before"],
        "answer": ("For a private match, use ROUNDS' normal flow: **Online → Private → Join**, then enter the "
                   "**6-letter room code** exactly as the host sent it. Both players should use the same Photon "
                   "region.\n"
                   "SCR's ranked queue needs no manual code — click **Ready** and the mod auto-connects you. "
                   "Private-room games still count as ranked when both players have SCR running and ranked enabled."),
    },
    {
        "key": "play_ranked",
        "title": "How to play ranked",
        "patterns": [
            r"how.{0,30}\b(play|start|queue|join|get into)\b.{0,15}ranked",
            r"how.{0,20}(play|join|start).{0,20}(here|competitive|comp|scr)",
            r"where.{0,20}(ranked )?queue",
        ],
        "examples": ["how do i play ranked here", "how do I queue for ranked"],
        "answer": (f"Start here: {FAQ_INFO_CHANNEL} — then install the mod: {FAQ_INSTALL_CHANNEL}\n"
                   "The short version:\n"
                   "1. Install **Sid's Competitive Rounds** (installer from the #releases pins, or Thunderstore).\n"
                   "2. Launch ROUNDS, accept the consent prompt, press **F5** → Ranked tab → **Search Ranked**.\n"
                   "3. When a match is found you have 90s to click **Ready** — the mod auto-connects both players.\n"
                   "Private-room games between two modded, ranked-enabled players also count as ranked."),
        "short": ("Install the mod (see the how-to-install channel on Discord), then in ROUNDS press F5 -> "
                  "Ranked tab -> Search Ranked. When matched, click Ready within 90s and it auto-connects."),
    },
    {
        "key": "tournaments",
        "title": "How tournaments work",
        "patterns": [
            r"how.{0,20}tournaments?.{0,15}work",
            r"(next|when|upcoming).{0,20}tournament",
            r"(sign ?up|join|enter).{0,20}tournament",
            r"tournament.{0,20}(sign ?up|signups?|join|enter|schedule)",
        ],
        "examples": ["how do tournaments work", "how do i sign up for the tournament"],
        "answer": ("Two kinds, both signed up from **F5 → Tournaments**:\n"
                   "• **Sync** (runs weekly): played in one sitting (~2 hours). When you sign up you pick every "
                   "start time you can make; it locks once **8+ players agree on one time** and at that time you "
                   "just **have ROUNDS open** — the mod auto-connects every bracket match, with a short "
                   "skippable breather between your matches.\n"
                   "• **Async** (~every 6 weeks): one week per round with a 7-day deadline per match — you schedule "
                   "each match with your opponent on Discord whenever suits you both.\n"
                   "**Prizes scale with signups**: at 8 players 1st gets 1000g/5000xp, growing to double at 16. "
                   "The final sync time locks in **2 days before the default start** (so you always get 24h+ "
                   "notice), and you'll get an availability-check DM 1-4 days before that lock (link your "
                   "account with `/link` to receive it). Live status board: the #scr-tournaments channel."),
    },
    {
        "key": "more_gold",
        "title": "Getting more gold",
        "patterns": [
            r"how (do|can) (i|you) (get|earn|make|farm).{0,10}(more )?gold",
            r"(need|want).{0,10}more gold",
            r"(earn|farm|grind).{0,10}gold (fast|quick)",
        ],
        "examples": ["how do i get more gold", "fastest way to earn gold"],
        "answer": ("Best gold sources:\n"
                   "• **Boost the Discord server** — 2000g/month, auto-granted (link your account).\n"
                   "• **Play 2v2s** — 50g per series win (25g even on a loss, both scaled by the opposing "
                   "team's tier) on top of match XP.\n"
                   "• **Play up in ranked** — gold and XP scale by your opponent's tier (up to ×3 vs a "
                   "Grand Master), win or lose; series wins pay 10-30g and even series losses pay 5-15g.\n"
                   "• **Earn achievements** — 100g each, the Sid/Stan Slayer trophies pay 1000g.\n"
                   "• **Win tournaments** — trophy payouts.\n"
                   "• **Make and sell cosmetics** — artists earn a 30% royalty on every sale "
                   "(ask me *how do I become an artist*).\n"
                   "• Plus the steady drip: every 100 XP = 1g, series bonuses, level-up rewards "
                   "(+100g every 5 levels, +500g per 5 past level 50), and smart bets."),
    },
    {
        "key": "xp_gold",
        "title": "XP & gold system",
        "patterns": [
            r"how.{0,20}(xp|gold|economy|level(ing|s)?).{0,20}(work|works|system)",
            r"(explain|what is).{0,20}(the )?(xp|gold|economy|level)",
            r"how (much|many) xp",
        ],
        "examples": ["how does the xp gold system work", "explain the economy"],
        "answer": ("**XP per game** (multipliers stack):\n"
                   "• Base **250 XP** · win **×1.5** · ranked **×1.5**\n"
                   "• Ranked games also scale by your **opponent's rank tier**, win or lose: "
                   "Beginner ×1 · Intermediate ×1.5 · Advanced ×2 · Master ×2.5 · Grand Master ×3\n"
                   "• 5-0 sweep: **+100**\n"
                   "• 2v2: base **600** (~900 on a win), scaled by the opposing team's average tier · 1v2: base **500**\n"
                   "**Gold**:\n"
                   "• Every **100 XP = 1 gold**, automatic — so the tier multiplier boosts gold too.\n"
                   "• Series bonuses: 1v1 BO3 winner **10-30g** by opponent tier, **doubled again** if they're a "
                   "current top-3 player (+2 on a 2-0 sweep) · the **loser** now gets **5-15g** by opponent tier · "
                   "2v2 **50g/25g** win/loss × the opposing team's tier · 1v2 **40g/20g**.\n"
                   "• Levels: **+100g** every 5 levels (to 50), **+500g** per 5 levels after (max 100).\n"
                   "• Achievements **100g** (Slayers **1000g**) · Boosters **2000g/month** · bets pay stake × odds."),
    },
    {
        "key": "artist",
        "title": "Making cosmetics / becoming an artist",
        "patterns": [
            r"(make|create|submit|upload|add).{0,20}(a )?cosmetics?",
            r"(become|be) an? artist",
            r"how.{0,25}(cosmetics?|skins?|faces?).{0,20}(made|submit|created|into the (game|shop))",
            r"my (art|drawing|design).{0,25}(game|mod|shop)",
        ],
        "examples": ["how do i make cosmetics", "how do i become an artist"],
        "answer": ("**DM Sid** with some art you'd like to upload — that's the whole application.\n"
                   "Format: **512×512 PNG** with real transparency, drawn for a character slot (eyes, mouth, or "
                   "detail/accessory).\n"
                   "The in-game uploader currently submits **one static PNG** and lets you preview its true size "
                   "against the player body before review. It does **not** bundle animation frames yet.\n"
                   "For an animated submission, upload frame 1 for review and send the remaining frames plus the "
                   "intended FPS to Sid separately. Shipped files use `myitem.png`, then `myitem__f2.png`, "
                   "`myitem__f3.png`, …\n"
                   "Approved artists get the in-game **Artist tab** (F5): upload cosmetics, set price and stock "
                   "after the art ships, gift copies, and earn a **30% royalty** on every sale."),
    },
    {
        "key": "bug_report",
        "title": "Filing a bug report",
        "patterns": [
            r"(submit|file|report|make|send).{0,15}(a )?bug",
            r"bug report",
            r"report.{0,15}(a )?(bug|issue|glitch|problem)",
            r"where.{0,20}report.{0,15}(bugs?|issues?)",
        ],
        "examples": ["how do i submit a bug report", "where do i report bugs"],
        "answer": ("**F5 → Settings → Report a Bug.** Describe what happened and **tick the \"attach log\" box** — "
                   "the log is what makes bugs fixable. Up to 10 reports/day.\n"
                   "If your Discord is linked (`/link`), you get a DM whenever your report gets a response. "
                   "Reports are triaged regularly and fixes are called out in #releases notes.\n"
                   "If the game is in a state a report can't capture, ping @Sid in #bug-reports with a screenshot."),
    },
    {
        "key": "rank_roles",
        "title": "Elo requirements for rank roles",
        "patterns": [
            r"(elo|rating).{0,30}(requirement|threshold|needed|need|for).{0,20}(each )?(rank|role|tier)",
            r"what (elo|rating).{0,20}(is|for|do you need).{0,20}(master|grand ?master|advanced|intermediate|beginner)",
            r"(rank|discord) roles?.{0,15}(elo|rating|requirement|threshold)",
            r"how.{0,15}(get|earn).{0,20}(master|grand ?master|advanced) role",
        ],
        "examples": ["what are the elo requirements for each discord rank role",
                     "what rating do i need for master"],
        "answer": _rank_roles_faq_answer(),
    },
    {
        "key": "thunderstore",
        "title": "Thunderstore page",
        "patterns": [
            r"thunderstore",
            r"r2modman.{0,25}(download|install|get|find)",
            r"mod manager.{0,20}(install|download|find)",
        ],
        "examples": ["can i get the mod on thunderstore", "is it on thunderstore"],
        "answer": (f"Yes: {FAQ_THUNDERSTORE_URL}\n"
                   "Install it through r2modman or the Thunderstore app (BepInEx comes along automatically) and "
                   "**launch ROUNDS through the mod manager**. Updates come from the manager — the Thunderstore "
                   "build doesn't self-update.\n"
                   f"Or import the ready-made profile — ask me *what's the modpack code*."),
    },
    {
        "key": "achievements",
        "title": "Achievements",
        "patterns": [
            r"(what|list|which|show).{0,15}(are )?(the )?achievements",
            r"achievements?.{0,20}(list|are there|exist|available)",
            r"how.{0,15}(do )?achievements.{0,10}work",
        ],
        "examples": ["what are the achievements", "list the achievements"],
        "answer": _FAQ_ACHIEVEMENTS_TEXT,
        "short": ("40 achievements, each paying 100g (the Sid/Stan Slayer trophies pay 1000g; some unlock "
                  "exclusive titles). Full list + your progress: F5 -> Achievements."),
    },
    {
        "key": "discord_steam_lookup",
        "title": "Finding a linked Steam name",
        "patterns": [
            r"(find|see|check|look ?up).{0,30}(steam|rounds).{0,20}(name|account).{0,30}(discord|linked)",
            r"(steam|rounds).{0,20}(name|account).{0,25}(linked|connected).{0,15}discord",
            r"discord.{0,20}(linked|connected).{0,20}(steam|rounds).{0,15}(name|account)",
        ],
        "examples": ["how do i find the steam name linked to discord",
                     "can i look up a discord user's rounds name"],
        "answer": ("Yes — use `/rank @person`, `/stats @person`, or `/mystats @person`. If that Discord user "
                   "linked their account, the result is headed by their linked ROUNDS/Steam display name. "
                   "If the bot says *not linked*, there is no Discord-to-Steam lookup available for them."),
        "discord_only": True,
    },
    {
        "key": "link_account",
        "title": "Linking your account",
        "patterns": [
            r"how.{0,20}link.{0,25}(account|discord|steam)",
            r"link my (account|discord|steam)",
            r"(connect|sync).{0,20}(discord|steam|account)",
            r"link code",
        ],
        "examples": ["how do i link my account", "how do i connect discord to the mod"],
        "answer": ("1. In ROUNDS, press **F5** and find the **Discord Link** panel → click **Get Link Code**.\n"
                   "2. Type `!link YOURCODE` (or use `/link`) here in the Discord server. Codes last 10 minutes.\n"
                   "Linking gets you: your **rank role**, Discord **bet buttons**, **bug-report DMs**, tournament "
                   "reminder DMs, and **server-booster gold** (2000g/month)."),
    },
    {
        "key": "install_safety",
        "title": "Is SCR safe to install?",
        "patterns": [
            r"(is|are).{0,15}(the )?(scr|mod|installer|competitive rounds).{0,20}(safe|legit|virus|malware)",
            r"(safe|legit).{0,20}(install|download|run).{0,15}(scr|the mod|installer|competitive rounds)",
            r"(installer|scr).{0,15}(virus|malware)",
        ],
        "examples": ["is the mod safe to install", "is the installer safe"],
        "answer": ("**Yes, when you get it from the official SCR release pins or official Thunderstore page.** "
                   "The project source is public; the installer only sets up BepInEx/SCR in your ROUNDS install, "
                   "and SCR does not change gameplay.\n"
                   "The standalone Windows installer is not code-signed, so Windows or antivirus software may "
                   "show a reputation warning. Do not use reuploads or files sent by strangers. Official install "
                   f"instructions: {FAQ_INSTALL_CHANNEL}"),
    },
    {
        "key": "install",
        "title": "Installing the mod",
        "patterns": [
            r"how.{0,20}(install|download|get|set ?up).{0,25}(the )?(mod|scr|competitive)",
            r"where.{0,20}(download|get).{0,20}(the )?mod",
        ],
        "examples": ["how do i install the mod", "where do i download this"],
        "answer": (f"Full walkthrough: {FAQ_INSTALL_CHANNEL}\n"
                   "**Option A — installer (recommended):** grab `CompetitiveRoundsInstaller.exe` from the pinned "
                   "post in #releases, close ROUNDS, run it. It finds your Steam install and sets up everything. "
                   "This version self-updates.\n"
                   f"**Option B — Thunderstore:** install *SidsCompetitiveRounds* via r2modman "
                   f"(modpack code: `{FAQ_MODPACK_CODE}`) and **launch through the mod manager**.\n"
                   "**Requirements:** ROUNDS v1.1.2 on Steam (default branch), Windows, and **no other mods**.\n"
                   "Then press **F5** in-game — that's the competitive hub."),
    },
    {
        "key": "rounds_version",
        "title": "Which ROUNDS version?",
        "patterns": [
            r"(what|which).{0,15}version.{0,20}(of )?rounds",
            r"old.?rounds.?for.?mods",
            r"(beta|branch).{0,20}(rounds|steam).{0,15}(mod|scr)",
        ],
        "examples": ["what version of rounds do i need", "do i need old rounds for mods"],
        "answer": ("**SCR runs on the current ROUNDS (v1.1.2), default Steam branch** — no beta needed.\n"
                   "The `old-rounds-for-mods` Steam beta branch is for every **other** ROUNDS mod (they target the "
                   "old game version). SCR and those mods can't run together — pick one:\n"
                   "• SCR → default branch, no other plugins.\n"
                   "• Other mods → `old-rounds-for-mods` branch, without SCR.\n"
                   "(Steam → ROUNDS → Properties → Betas to switch.)"),
    },
    {
        "key": "disconnect",
        "title": "Disconnects & leavers",
        "patterns": [
            r"(what happens?|happens?).{0,25}(disconnect|dc\b|rage ?quit|leaver?|leaves)",
            r"opponent.{0,15}(left|dc'?d|dc\b|disconnected|quit)",
            r"rage ?quit",
            r"(dc|disconnect|leave).{0,20}(penalty|count|percent)",
            r"(resolv(?:e|ing)|finish|settle|complete).{0,30}(ranked )?(game|match|series).{0,30}(left|leave|dc|disconnect)",
            r"(ranked )?(game|match|series).{0,30}(someone|player|opponent).{0,20}(left|leave|dc|disconnect)",
            r"(count|counts).{0,15}(as )?(a )?(loss|lose).{0,20}(if|when).{0,12}(i )?(dc|disconnect|leave)",
            r"(dc|disconnect|leave).{0,20}(count|counts).{0,15}(as )?(a )?(loss|lose)",
        ],
        "examples": ["what happens if someone disconnects", "my opponent rage quit",
                     "does it count as a loss if i disconnect"],
        "require_question": False,
        "answer": ("• In 1v1, a disconnect does **not automatically become a series loss**. It counts as a "
                   "**DC on the leaver's record** — leave % is visible on the leaderboard — and the open series "
                   "keeps its score.\n"
                   "• The series isn't lost: **rematch the same player and it resumes** where it left off, no "
                   "matter how much later — unfinished series never expire.\n"
                   "• In 2v2, leaving can immediately forfeit the series when the other team was already up a "
                   "game and the abandoned game had meaningful play. Other 2v2 DCs are marked incomplete for "
                   "an admin to award or void; they do not silently become a loss.\n"
                   "• If a series never finishes, any bets on it auto-refund (~1 hour).\n"
                   "• Game crashed mid-match? Relaunch and rejoin your opponent — the series picks back up."),
    },
    {
        "key": "open_menu",
        "title": "Opening the competitive menu",
        "patterns": [
            r"(open|show|access).{0,20}(competitive |mod )?(menu|overlay|hub)",
            r"what (does|is) f ?5",
            r"where.{0,20}(my )?(stats|leaderboard|shop).{0,10}in ?.?game",
        ],
        "examples": ["how do i open the competitive menu", "where do i see my stats in game"],
        "answer": ("**F5** toggles the competitive menu in ROUNDS — queue, stats, leaderboard, shop, achievements, "
                   "tournaments, settings, everything. **T** opens the in-game chat; **Esc** closes the menu.\n"
                   "If F5 does nothing: restart ROUNDS; if it keeps happening, file a bug report."),
    },
    {
        "key": "chat",
        "title": "In-game chat",
        "patterns": [
            r"(in ?.?game|t) ?chat",
            r"how.{0,20}chat.{0,20}(work|in ?game)",
            r"(mute|block).{0,20}(chat|someone|player|him|her|them)",
        ],
        "examples": ["how does the in-game chat work", "how do i mute someone in chat"],
        "answer": ("Press **T** in-game to chat. Messages bridge both ways with the in-game-chat channel on this "
                   "Discord, so in-game and Discord folks see each other.\n"
                   "Moderation is local: `/mute name`, `/unmute name`, `/muted` (list) — typed in the in-game chat box."),
    },
    {
        "key": "platforms",
        "title": "Platform support",
        "patterns": [
            r"(work|play|run).{0,15}on.{0,10}(mac|linux|steam ?deck|proton)",
            r"(mac|linux|steam ?deck|proton).{0,15}(support|work)",
        ],
        "examples": ["does it work on steam deck", "mac support?"],
        "answer": ("Officially **Windows only** (ROUNDS on Steam, current version). Mac isn't supported. "
                   "Linux/Steam Deck via Proton is untested and unsupported — if you get it running, neat, but "
                   "you're on your own."),
    },
    {
        "key": "booster",
        "title": "Server booster perks",
        "patterns": [
            r"(boost|booster).{0,25}(perk|get|reward|gold|benefit)",
            r"(what|anything).{0,15}(for|from).{0,15}boost(ing)?",
            r"server boost",
        ],
        "examples": ["what do boosters get", "booster perks?"],
        "answer": ("Server boosters get **2000 gold/month**, granted automatically (one grant per member per month). "
                   "Your Discord needs to be linked (`/link`) so the gold has somewhere to land."),
    },
    {
        "key": "titles",
        "title": "Titles",
        "patterns": [
            r"(get|earn|equip|unlock).{0,15}titles?",
            r"what (are|is).{0,10}titles?",
            r"titles?.{0,15}(work|list|available)",
        ],
        "examples": ["how do i get titles", "what are titles"],
        "answer": ("Titles render next to your name (leaderboard, chat, match history). Sources:\n"
                   "• **Shop** (F5 → Shop → Titles) — bought with gold, equip there too.\n"
                   "• **Achievements** — exclusive ones like *Sid Slayer* / *Stan Slayer*.\n"
                   "• **Dynamic titles**: *Current Rank* always shows your live tier; *Podium* shows 1st/2nd/3rd "
                   "Place (in gold/silver/bronze) while you hold a leaderboard top-3 spot — it's auto-granted when "
                   "you get there."),
    },
    {
        "key": "leaderboard_where",
        "title": "Where's the leaderboard?",
        "patterns": [
            r"(where|how).{0,20}(see|view|check|find).{0,20}(the )?(leaderboard|rankings?|standings)",
            r"leaderboard.{0,10}(link|channel|where)",
        ],
        "examples": ["where can i see the leaderboard"],
        "answer": ("• In-game: **F5 → Leaderboard** (with live series + betting panel).\n"
                   "• Discord: the **#scr-leaderboard** channel (living board, updates every 10 min) or `/lb`.\n"
                   "Boards need 1+ recorded match to show a player."),
    },
    {
        "key": "bullet_hitboxes",
        "title": "Why a bullet can look far from you",
        "patterns": [
            r"(hit|damage|killed).{0,35}bullet.{0,35}(nowhere|far|close|near|miss|touch)",
            r"bullet.{0,35}(nowhere|far|not|wasn'?t|wasnt).{0,25}(near|close|touch|hit).{0,20}(me|player)",
            r"(weird|bad|wrong).{0,15}(bullet )?(hitbox|hitboxes|hits|collision)",
            r"(desync|lag).{0,20}(bullet|hitbox|hit)",
        ],
        "examples": ["why do bullets hit me when they look nowhere close",
                     "why are the bullet hitboxes weird"],
        "answer": ("SCR does not change bullet hitboxes or damage. Vanilla ROUNDS simulates projectiles over "
                   "Photon, and the visible sprite/trail is not a perfect picture of the collision at the instant "
                   "the hit was confirmed. Ping, interpolation, frame-time spikes, bullet-size cards, homing, and "
                   "bounces can widen that visual mismatch.\n"
                   "If it is repeatable with low ping, record a clip with the F5 FPS/ping display visible and file "
                   "an attached-log bug report so it can be separated from ordinary network desync."),
    },
    {
        "key": "hosting",
        "title": "Hosting & netcode",
        "patterns": [
            r"(is|does).{0,12}orange.{0,15}host",
            r"peer.{0,3}to.{0,3}peer|\bp2p\b",
            r"who('?s| is|s)?\b.{0,12}(the )?host(ing)?\b",
            r"(matter|advantage|difference).{0,20}\bhost",
            r"host.{0,15}(matter|advantage)",
        ],
        "examples": ["is orange the host", "is the game peer to peer",
                     "does it matter who hosts", "is there a host advantage"],
        "answer": ("ROUNDS is **not peer-to-peer** — every online game runs through Photon's relay servers "
                   "in your region, so nobody's PC is 'hosting' the match.\n"
                   "• **Orange** is just the first player slot in the room (usually whoever's client created "
                   "it). That client is the *master client* and coordinates room-level stuff like map sync, "
                   "but it doesn't run the game for the other player.\n"
                   "• **No host advantage** — each client simulates its own character and bullets and relays "
                   "them. What matters is each player's ping to the Photon region, not who created the room."),
    },
    {
        "key": "what_is_scr",
        "title": "What is this mod?",
        "patterns": [
            r"(what|who).{0,15}(is|made|created|runs).{0,15}(scr|this mod|competitive rounds|sid'?s)",
            r"what.{0,10}(does )?(the|this) mod (do|add)",
            r"how('?s| does| do)?.{0,12}(comp(etitive)?|scr|ranked|this|the) ?mod.{0,10}work",
        ],
        "examples": ["what is this mod", "who made this mod", "how does the comp mod work"],
        "answer": ("**Sid's Competitive Rounds** — a full competitive layer for ROUNDS, built and run by **Sid**: "
                   "ranked BO3 series with Glicko-2 ratings, matchmaking queues (1v1, 2v2, 1v2 beta), tournaments, "
                   "a leaderboard, betting, an XP/gold economy with a cosmetics shop, achievements, and this "
                   "Discord integration. It doesn't change gameplay — vanilla ROUNDS, plus everything around it.\n"
                   f"Get started: {FAQ_INFO_CHANNEL}"),
    },
    {
        "key": "blocking",
        "title": "Blocking better",
        "patterns": [
            r"(learn|get better|improve|git gud|better).{0,20}block",
            r"block(ing)?.{0,15}(tips|better|guide|timing)",
            r"how.{0,20}block (better|well|good)",
        ],
        "examples": ["how can i learn to block better", "any tips for blocking"],
        "answer": ("1. **React to the bullet, not the trigger** — block just before the shot reaches you, "
                   "not when they fire. Whiffed panic blocks are the #1 leak: every miss leaves you exposed "
                   "for the whole cooldown.\n"
                   "2. **Watch their gun, not your own player** — reloads and burst patterns telegraph when "
                   "the next shot comes, and that's your blocking window.\n"
                   "3. **Drill it deliberately** — play some casual games where you only allow yourself "
                   "on-reaction blocks, and pick block-effect cards (Shield Charge, Empower) so a good block "
                   "wins you the trade instead of just surviving it."),
    },
    {
        "key": "get_better",
        "title": "Getting better",
        "patterns": [
            r"how.{0,20}(get|be(come)?|git).{0,10}(better|gud|good)",
            r"how.{0,15}(do|can) i improve",
            r"(any )?tips.{0,20}(for )?(improv|better|new|beginner)",
        ],
        "examples": ["how can i get better", "any tips for improving"],
        "answer": ("1. **Fix your setup first** — FPS drops and monitor refresh issues cost more games than bad "
                   "card picks. Check the perf toggles in F5 → Settings and make sure ROUNDS runs at your "
                   "monitor's refresh rate.\n"
                   "2. **Play a lot of good players** — queue ranked and don't dodge high elo. Losses against "
                   "better players teach faster than wins against worse ones.\n"
                   "3. **Play outside your comfort zone** — learn everything there is to know about cards, "
                   "blocking, and angling shots. Force yourself onto builds you'd normally pass on; every card "
                   "you understand is a matchup you stop losing to."),
    },
    # ── Bug #122: "How does FFA work" / "How does 1v2 work" were unanswerable.
    # These two replace the old combined `modes_1v2_ffa` entry, which could only
    # be reached through a handful of hard-coded phrasings.
    # THESE TWO SIT LAST ON PURPOSE. The file's convention is "first regex hit
    # wins, so specific entries sit above general ones" (see the header comment
    # on FAQ_ENTRIES). The \bffa\b patterns below are deliberately broad; placed
    # mid-table they would steal "how do i report a bug in ffa" from bug_report
    # and "how do tournaments work in ffa" from tournaments.
    {
        "key": "how_ffa",
        "title": "How FFA works",
        "patterns": [
            r"(what|how|hows|where|when|why|can|does|do|is|explain|tell).{0,40}\bffa\b",
            r"\bffa\b.{0,30}(work|works|mode|rules?|scor(e|ing)|rating|ranked|rank|queue|lobby|placement|points?|cards?|xp|gold|leaderboard|players?)",
            r"(what|how|explain).{0,25}\bfree ?-? ?for ?-? ?alls?\b",
            r"\bfree ?-? ?for ?-? ?alls?\b.{0,30}(work|works|mode|rules?|scor(e|ing)|rating|ranked|queue|lobby|match)",
        ],
        "examples": ["how does ffa work", "how does free for all work", "what is ffa",
                     "how do i play ffa", "how does ffa scoring work", "is ffa ranked"],
        "answer": (
            "**Free-for-all, 3-10 players, and it's fully RANKED.** Queue from "
            "**F5 → Multiplayer → FFA → Join FFA Queue**.\n"
            "• **Getting in** — no Elo band and no ready-up: joining *is* consent. Once 3 players are "
            "searching a **25s gather window** opens, each new joiner adds ~20s (2 min hard cap), and a "
            "full 10 locks instantly. The mod auto-connects everyone into the lobby.\n"
            "• **Scoring** — everyone is their own team. Last player alive takes a **half point**; "
            "**2 halves = a point**; **first to 5 points** wins the game. The lobby keeps playing "
            "rematches until people leave.\n"
            "• **Cards** — after each point, everyone *except* the point winner picks **at the same "
            "time**. Nothing is ever picked for you: the window stays open at least **45s** and extends "
            "as picks land (90s max) — miss it and you get no card that round. You hold **5 cards**; "
            "picking a 6th removes your oldest.\n"
            "• **Rating** — FFA has its **own Glicko rating and leaderboard**; your 1v1 elo is untouched. "
            "Placement is points, then total half points earned, then kills, and ties share a place "
            "(1, 2, 2, 4). You're rated against the **4 players placed nearest you**, so a 10-player "
            "lobby doesn't swing your rating harder than a 3-player one.\n"
            "• **Rewards** — **600 XP** plus **90 per player you finish above**, all multiplied by how "
            "much of the field you outplaced (up to **×1.5** in a 3-player lobby and **×5** in a full "
            "10) and by the usual opponent-tier bonus. On top of that every player banks **placement "
            "gold** — 1st down to last, scaled by lobby size. 100 XP = 1 extra gold.\n"
            "• The map and its out-of-bounds edge **grow with the lobby**.\n"
            "• Spectators can **bet gold** on who wins the next game, from the FFA tab.\n"
            "Full rules in-game: **F5 → Multiplayer → FFA → Info**."),
        "short": ("FFA is a RANKED 3-10 player free-for-all. F5 -> Multiplayer -> FFA -> Join FFA Queue: "
                  "no elo band, no ready-up, the lobby locks ~25s after 3 are searching (instantly at 10). "
                  "Last player alive takes a half point, 2 halves make a point, first to 5 points wins. "
                  "After each point everyone but the point winner picks a card at the same time; you hold "
                  "5 cards, a 6th drops your oldest. Own rating and leaderboard."),
    },
    {
        "key": "how_1v2",
        "title": "How 1v2 works",
        "patterns": [
            r"(what|how|where|when|can|is|does|do|explain).{0,25}\b(1 ?v ?2|2 ?v ?1)\b",
            r"\b(1 ?v ?2|2 ?v ?1)\b.{0,25}(work|works|play|queue|ranked|rating|available|live|beta|mode|rules?|scor(e|ing)|xp|gold)",
            r"(what|how|where|when|can|is).{0,20}solo (vs|versus|v|against) duo",
            r"(what|how|explain).{0,20}\bone (v|vs|versus) two\b",
        ],
        "examples": ["how does 1v2 work", "what is 1v2", "how do i play 1v2",
                     "how does solo vs duo work", "how does 2v1 work"],
        "answer": (
            "**Solo vs duo — one player against a team of two, best-of-3** (first side to 2 game wins). "
            "Queue from **F5 → Multiplayer → 1v2 → Join 1v2 Lobby**.\n"
            "• **Getting in** — consent queue: no Elo band, no ready-up. It locks the moment **3 players** "
            "are searching and the mod auto-connects you.\n"
            "• **Sides** — the **Side: Any / Solo / Duo** button sets your preference. The first player who "
            "asked for solo gets it, otherwise the earliest joiner does; the other two are the duo.\n"
            "• **Solo Extra Initial Pick** — optional handicap: if **any** of the three turns it on, the "
            "solo draws **2 cards on the opening pick only**.\n"
            "• **Rating** — 1v2 is still an **unranked beta**, so no rating is applied yet. Every game is "
            "fully recorded so the mode can be rated retroactively when it graduates.\n"
            "• **Rewards** — **500 XP** per game (**750** for a win), plus **40g** each to the series "
            "winners and **20g** to the losers. 100 XP = 1 gold.\n"
            "• **Boards** — the tab has separate **Solo** and **Duo** activity boards (W-L / win rate in "
            "that role); you appear only on boards for roles you've actually played.\n"
            "Full rules in-game: **F5 → Multiplayer → 1v2 → Info**."),
        "short": ("1v2 is solo vs duo, best-of-3 (first side to 2 wins). F5 -> Multiplayer -> 1v2 -> "
                  "Join 1v2 Lobby: consent queue, no elo band, no ready-up, it locks once 3 are searching. "
                  "Side: Any/Solo/Duo picks your role; Solo Extra Initial Pick gives the solo 2 cards on the "
                  "FIRST draw if any of the three turn it on. UNRANKED beta - no rating yet, but every game "
                  "is recorded. 500 XP a game (750 on a win), 40g/20g series."),
    },
]

for _e in FAQ_ENTRIES:
    _e["compiled"] = [_faq_re.compile(p) for p in _e["patterns"]]
    _e["examples_norm"] = [_faq_norm(x) for x in _e.get("examples", [])]
    _e["example_topics"] = [_faq_topic_tokens(x) for x in _e["examples_norm"]]


def _faq_find_match(content: str):
    """Return the best FAQ entry for a message, or None. Regex layer first
    (ordered, first hit wins), then fuzzy vs canonical examples."""
    norm = _faq_norm(content)
    if not (8 <= len(norm) <= 400):
        return None
    question_like = _faq_question_like(norm)
    for e in FAQ_ENTRIES:
        if not question_like and e.get("require_question", True):
            continue
        for rx in e["compiled"]:
            if rx.search(norm):
                return e
    if question_like:
        best, best_ratio = None, 0.0
        norm_topics = _faq_topic_tokens(norm)
        for e in FAQ_ENTRIES:
            for ex, ex_topics in zip(e["examples_norm"], e["example_topics"]):
                if not _faq_topics_overlap(norm_topics, ex_topics):
                    continue
                r = _faq_difflib.SequenceMatcher(None, norm, ex).ratio()
                if r > best_ratio:
                    best, best_ratio = e, r
        if best is not None and best_ratio >= 0.78:
            return best
    return None


_ROOM_CODE_CANDIDATE_RE = _faq_re.compile(
    r"(?<![A-Z0-9])(-[A-Z]{5}|[A-Z]{5})(?![A-Z0-9])"
)
# These are the ordinary all-caps chat words most likely to satisfy the
# deliberately conservative "looks randomly generated" fallback below.
_ROOM_CODE_WORDS = frozenset("""
ABOUT ABOVE ABUSE ACTOR ACUTE ADMIT ADOPT ADULT AFTER AGAIN AGENT AGREE AHEAD
ALARM ALBUM ALERT ALICE ALIKE ALIVE ALLOW ALONE ALONG ALTER AMONG ANGER ANGLE
ANGRY APART APPLE APPLY ARGUE ARISE ARRAY ASIDE ASSET AUDIO AUDIT AVOID AWARD
AWARE BADLY BAKER BASED BASIC BASIS BEACH BEGAN BEGIN BEGUN BEING BELOW BENCH
BILLY BIRTH BLACK BLAME BLIND BLOCK BLOOD BOARD BOOST BOOTH BOUND BRAIN BRAND
BREAD BREAK BREED BRIEF BRING BROAD BROKE BROWN BUILD BUILT BUYER CABLE CARRY
CARDS CATCH CAUSE CHAIN CHAIR CHART CHASE CHEAP CHECK CHEST CHIEF CHILD CHOSE
CIVIL CLAIM CLASS CLEAN CLEAR CLICK CLIMB CLOCK CLOSE COACH COAST COULD COUNT
COURT COVER CRAFT CRASH CREAM CRIME CROSS CROWD CROWN CURVE CYCLE DAILY DANCE
DEALT DEATH DEBUT DELAY DEPTH DOING DOUBT DOZEN DRAFT DRAMA DRAWN DREAM DRESS
DRILL DRINK DRIVE DROVE DODGE DYING EAGER EARLY EARTH EIGHT ELITE EMAIL EMPTY ENEMY ENJOY
ENTER ENTRY EQUAL ERROR EVENT EVERY EXACT EXIST EXTRA FAITH FALSE FAULT FIBER
FIELD FIFTH FIFTY FIGHT FINAL FIRST FIXED FLASH FLEET FLOOR FLUID FOCUS FORCE
FORTH FORTY FORUM FOUND FRAME FRANK FRAUD FRESH FRONT FRUIT FULLY FUNNY GAMES
GIANT GIVEN GLASS GLOBE GOING GRACE GRADE GRAND GRANT GRASS GREAT GREEN GROSS
GROUP GROWN GUARD GUESS GUEST GUIDE HAPPY HEART HEAVY HELLO HENCE HENRY HORSE
HOTEL HOUSE HUMAN IDEAL IMAGE INDEX INNER INPUT ISSUE JACKS JAMES JERKS JERKY
JIMMY JOINT JONES JUDGE JUMPS KNOWN LABEL LARGE LASER LATER LAUGH LAYER LEARN
LEAST LEAVE LEGAL LEVEL LEWIS LIGHT LIMIT LINKS LIVES LOCAL LOGIC LOOSE LOWER
LUCKY LUNCH LYING MAGIC MAJOR MAKER MARCH MARIA MATCH MAYBE MAYOR MEANT MEDIA
METAL MIGHT MINOR MODEL MONEY MONTH MORAL MOTOR MOUNT MOUSE MOUTH MOVIE MUSIC
NEEDS NEVER NEWLY NIGHT NOISE NORTH NOTED NOVEL NURSE OCCUR OCEAN OFFER OFTEN
ORDER OTHER OUGHT PAINT PANEL PAPER PARTY PAUSE PEACE PETER PHASE PHONE PHOTO PIECE
PILOT PITCH PLACE PLAIN PLANE PLANT PLATE PLAYS POINT POUND POWER PRESS PRICE
PRIDE PRIME PRINT PRIOR PRIZE PROOF PROUD PROVE QUEEN QUEUE QUICK QUIET QUITE
RADIO RAISE RANGE RAPID RATIO REACH READY REFER RESET RETRY RIGHT RIVAL RIVER ROBIN ROGER
ROMAN ROOMS ROUGH ROUND ROUTE ROYAL RURAL SCALE SCARY SCENE SCOPE SCORE SENSE SERVE
SEVEN SHALL SHAPE SHARE SHARP SHEET SHELF SHELL SHIFT SHIRT SHOCK SHOOT SHORT
SHOWN SIGHT SINCE SIXTH SIXTY SIZED SKILL SLEEP SLIDE SMALL SMART SMILE SMITH
SMOKE SOLID SOLVE SORRY SOUND SOUTH SPACE SPEAK SPEED SPEND SPENT SPLIT SPOKE
SPORT STAFF STAGE STAKE STAND START STATE STEAM STEEL STICK STILL STOCK STONE
STOOD STORE STORM STORY STRIP STUCK STUDY STUFF STYLE SUGAR SUITE SUPER SWEET
TABLE TAKEN TASTE TAXES TEACH TEAMS THANK THEIR THEME THERE THESE THICK THING
THINK THIRD THOSE THREE THROW TIGHT TIMES TITLE TODAY TOPIC TOTAL TOUCH TOUGH
TOWER TRACK TRADE TRAIN TREAT TREND TRIAL TRIED TRUCK TRULY TRUST TRUTH TWICE
UNDER UNION UNITY UNTIL UPPER UPSET URBAN USAGE USUAL VALID VALUE VIDEO VIRUS
VISIT VITAL VOICE WASTE WATCH WATER WHEEL WHERE WHICH WHILE WHITE WHOLE WHOSE
WOMAN WOMEN WORLD WORRY WORSE WORST WORTH WOULD WOUND WRITE WRONG WROTE YIELD
YOUNG YOUTH WALTZ ZILCH ZINGS ZONKS
""".split())

# A five-letter token is "word-shaped" only when its first two letters and all
# adjacent letter pairs occur in ordinary five-letter English words. This
# compact shape veto avoids pretending that a finite hand-written word list is
# exhaustive: ambiguous English-looking tokens stay silent unless the message
# explicitly identifies them as a room code.
_ROOM_CODE_WORD_START_SECONDS = (
    "abcdefghiklmnoprstuvwxyz",  # a
    "aeijloruy",                 # b
    "aehiloruyz",                # c
    "adehioruvwy",               # d
    "abcdefgijlmnpqrstuvwxy",     # e
    "aeijlorsu",                  # f
    "aehilnoruy",                 # g
    "adeimouy",                   # h
    "abcdglmnoqrstvz",            # i
    "aeiouy",                     # j
    "aehilmnoruy",                # k
    "aehilouy",                   # l
    "abcefiouy",                  # m
    "aeioruy",                    # n
    "abcdfghiklmnprstuvwxz",      # o
    "aehilorsuy",                 # p
    "au",                         # q
    "aehiosuy",                   # r
    "acehiklmnopqtuvwy",          # s
    "aehioruwy",                  # t
    "dgklmnprstvz",               # u
    "aeiouy",                     # v
    "aehioruy",                   # w
    "ehitvy",                     # x
    "aeiopu",                     # y
    "aeilou",                     # z
)
_ROOM_CODE_WORD_PAIR_SECONDS = (
    "abcdefghijklmnopqrstuvwxyz",  # a
    "abdehijklnorstuy",            # b
    "aceghikloprstuyz",            # c
    "adeghiklmnoqrstuvwyz",        # d
    "abcdefghijklmnopqrstuvwxyz",  # e
    "aefijklorstuy",               # f
    "abdeghilmnorstuy",            # g
    "abdeilmnorstuwy",             # h
    "abcdefghijklmnopqrstuvxyz",   # i
    "aeijouy",                     # j
    "abehiklmnorsuy",              # k
    "abcdefghiklmnoprstuvwy",      # l
    "abcdefiklmoprstuwy",          # m
    "abcdefghijklnoprstuvwxyz",    # n
    "abcdefghijklmnopqrstuvwxyz",  # o
    "acefhikloprstuy",              # p
    "abiru",                        # q
    "abcdefghijklmnoprstuvwyz",    # r
    "abcdefhiklmnopqrstuvwyz",     # s
    "acdeghiklmnorstuwyz",         # t
    "abcdefghijklmnopqrstvxyz",    # u
    "aeilorsuvy",                  # v
    "adefhiklnorsuy",              # w
    "abcehioptuvxy",               # x
    "abcdegiklmnoprstuvwx",        # y
    "abcdeilmotuyz",               # z
)
_room_code_warning_at: dict = {}


def _room_code_member_names(message) -> set:
    """Five-letter words that are names of cached guild members.

    The bot intentionally does not chunk all ~2,500 members at startup, so the
    cache is not proof that a token is not a name. It is still a useful veto;
    the structural fallback below supplies the second, conservative veto.
    """
    names = set()
    members = [getattr(message, "author", None)]
    members.extend(getattr(message, "mentions", None) or [])
    guild = getattr(message, "guild", None)
    if guild is not None:
        members.extend(getattr(guild, "members", None) or [])
    for member in members:
        if member is None:
            continue
        for attr in ("name", "display_name", "global_name", "nick"):
            value = getattr(member, attr, None)
            if not value:
                continue
            joined = "".join(_faq_re.findall(r"[A-Za-z]", str(value))).upper()
            if len(joined) == 5:
                names.add(joined)
            for word in _faq_re.findall(r"[A-Za-z]{5}", str(value)):
                names.add(word.upper())
    return names


def _room_code_looks_generated(token: str) -> bool:
    """High-precision fallback for a bare five-letter post.

    We would rather miss an ambiguous typo than tell someone their ordinary
    word/name is a room code. Reject only a token with a first pair or internal
    pair that does not occur in ordinary five-letter English words.
    """
    lower = token.lower()
    if len(lower) != 5 or not lower.isalpha():
        return False
    first_index = ord(lower[0]) - ord("a")
    if not 0 <= first_index < 26:
        return False
    if lower[1] not in _ROOM_CODE_WORD_START_SECONDS[first_index]:
        return True
    for left, right in zip(lower, lower[1:]):
        left_index = ord(left) - ord("a")
        if not 0 <= left_index < 26:
            return False
        if right not in _ROOM_CODE_WORD_PAIR_SECONDS[left_index]:
            return True
    return False


# A bare five-letter token is treated as an ATTEMPTED room code only when a
# room-code keyword IMMEDIATELY precedes it ("join QRDDO", "room code QRDDO",
# "my code is QRDDO"). This is the gate that stops all-caps chat slang from
# being called a room code: "LMFAO join us" never has a keyword right BEFORE
# the LMFAO token, so it is never flagged. Dash-prefixed tokens need no keyword.
_ROOM_CODE_LEADIN_RE = _faq_re.compile(
    r"(?:room ?code|game ?code|the ?code|my ?code|room|lobby|invite|join(?:ing)?|host(?:ing)?|"
    r"private (?:match|game|lobby|room)|come play|play (?:with|together))"
    r"(?:\s+(?:is|the|my|it|code|here|are|to))*\s*[:=\-]?\s*$",
    _faq_re.IGNORECASE,
)
# Common exactly-five-letter all-caps interjections/acronyms — vetoed on the
# lone-message path so a solo "LMFAO"/"BRUHH" is never called a room code. Only
# consulted when the whole message is the token (contextual matches skip it).
_ROOM_CODE_SLANG = frozenset("""
LMFAO LMAOO ROFLL BRUHH BRUUH YOOOO OMGGG WTFFF WTHHH AYYYY POGGG EZPZZ GGWPP
HAHAH HEHEH WELPP DAMNN WOOSH YEEET YEETT NOOOO NOOBS SMHHH OOFFF UGHHH AWWWW
GRRRR RIPPP NICEE COOLL LOLLL LOLOL SIMPP ONGGG FRRRR TBHHH MMMMM HMMMM PFFFT
SHEEE NGLLL WOMPP BOOOO WOOOO HYPEE GYATT RAWRR EEEEE AAAAA OOOOO
""".split())


def _find_invalid_room_code(message):
    """Return a safely identified malformed room code, otherwise None.

    A valid ROUNDS room code is six capital letters. We warn only about a
    five-letter (or dash + five-letter) capital token, and only when confident
    it is an ATTEMPTED room code rather than ordinary chat:
      * a dash-prefixed token ("-KCMON") is unambiguous — words, names and
        slang don't start with a dash — so it stands on its own;
      * a bare five-letter token ("QRDDO") is flagged only when a room-code
        keyword immediately precedes it, or when the whole message is just that
        token and it is not common slang.
    Known words, Discord member names and word-shaped tokens always veto a
    warning — this ordering is what keeps all-caps slang (LMFAO, BRUHH, ...)
    silent.
    """
    content = (getattr(message, "content", None) or "").strip()
    if not content or content.startswith(("!", "/", ".")):
        return None
    member_names = None
    for match in _ROOM_CODE_CANDIDATE_RE.finditer(content):
        raw = match.group(1)
        is_dash = raw.startswith("-")
        token = raw[1:] if is_dash else raw
        if token in _ROOM_CODE_WORDS:
            continue
        if not _room_code_looks_generated(token):
            continue
        if member_names is None:
            member_names = _room_code_member_names(message)
        if token in member_names:
            continue
        if is_dash:
            return raw
        # Bare token: require room-code context so chat slang stays silent.
        if _ROOM_CODE_LEADIN_RE.search(content[:match.start()]):
            return raw
        if content == raw and token not in _ROOM_CODE_SLANG:
            return raw
    return None


async def _room_code_is_member_name(message, token: str) -> bool:
    """Check cached names, then Discord's member search for uncached names.

    This bot deliberately does not cache the full guild at startup. A targeted
    REST query prevents a five-letter username/nickname from being called an
    invalid room code without bringing back the old multi-thousand-member
    startup chunk.
    """
    if token in _room_code_member_names(message):
        return True
    guild = getattr(message, "guild", None)
    query = getattr(guild, "query_members", None) if guild is not None else None
    if query is None:
        return False
    try:
        members = await query(query=token, limit=20, cache=False)
    except Exception as ex:
        # On lookup failure, favor silence over falsely correcting a person's
        # name. A later post can retry normally.
        print(f"[ROOM-CODE] member-name check failed: {ex}")
        return True
    for member in members or []:
        for attr in ("name", "display_name", "global_name", "nick"):
            value = getattr(member, attr, None)
            if not value:
                continue
            joined = "".join(_faq_re.findall(r"[A-Za-z]", str(value))).upper()
            words = {w.upper() for w in _faq_re.findall(r"[A-Za-z]{5}", str(value))}
            if joined == token or token in words:
                return True
    return False


def _room_code_warning_rate_ok(message, candidate: str) -> bool:
    now = _faq_time.monotonic()
    key = (
        getattr(getattr(message, "channel", None), "id", 0),
        getattr(getattr(message, "author", None), "id", 0),
        candidate,
    )
    if now - _room_code_warning_at.get(key, 0.0) < 120.0:
        return False
    if len(_room_code_warning_at) >= 500:
        cutoff = now - 600.0
        for old_key, stamped_at in list(_room_code_warning_at.items()):
            if stamped_at < cutoff:
                _room_code_warning_at.pop(old_key, None)
    _room_code_warning_at[key] = now
    return True


async def _maybe_warn_invalid_room_code(message) -> None:
    if getattr(message, "guild", None) is None:
        return
    candidate = _find_invalid_room_code(message)
    if candidate is None:
        return
    # Run the async member-name veto BEFORE consuming the rate-limit slot, so a
    # token that turns out to be someone's name doesn't burn the 120s dedup
    # window that a genuine code posted right after would need.
    token = candidate[1:] if candidate.startswith("-") else candidate
    if await _room_code_is_member_name(message, token):
        return
    if not _room_code_warning_rate_ok(message, candidate):
        return
    reason = ("it starts with a dash" if candidate.startswith("-")
              else "it has only five letters")
    try:
        await message.reply(
            f"⚠️ `{candidate}` is not a valid ROUNDS room code because {reason}. "
            "**Room codes are exactly six capital letters with no dash.** "
            "ROUNDS reports the host/player as offline for a malformed code, so ask them to resend the full code.",
            mention_author=False,
        )
        print(f"[ROOM-CODE] warned for malformed code {candidate}")
    except Exception as ex:
        print(f"[ROOM-CODE] warning reply failed: {ex}")


async def _room_code_warning_task(message) -> None:
    try:
        await _maybe_warn_invalid_room_code(message)
    except Exception as ex:
        print(f"[ROOM-CODE] handler error: {ex}")


async def _faq_resolve_answer(entry, message=None):
    """Static text or dynamic handler result. None means 'no answer' (handler
    declined, e.g. in-game context for a Discord-only entry)."""
    handler = entry.get("handler")
    if handler is None:
        return entry.get("answer")
    try:
        return await handler(message)
    except Exception as ex:
        print(f"[FAQ] handler {entry['key']} failed: {ex}")
        return entry.get("error_answer")


def _faq_embed(entry, answer_text: str) -> discord.Embed:
    embed = discord.Embed(title=f"💡 {entry.get('title', 'FAQ')}",
                          description=answer_text[:4096], color=0x5865F2)
    embed.set_footer(text="Automated answer • if this missed the mark, just ask again in your own words")
    return embed


async def _post_ingame_chat(text_msg: str) -> bool:
    """Send a line into the in-game chat as the helper bot (via /chat/post —
    same path the Discord relay uses; broadcasts to all connected mod clients
    and persists to scrollback)."""
    if http_session is None or not API_SECRET_KEY:
        return False
    try:
        async with http_session.post(
            f"{API_BASE_URL}/api/v1/chat/post",
            json={
                "discord_id": str(bot.user.id) if bot.user else "0",
                "display_name": FAQ_HELPER_NAME,
                "message": text_msg[:490],
            },
            headers={"X-Internal-Key": API_SECRET_KEY},
            timeout=aiohttp.ClientTimeout(total=5),
        ) as resp:
            return resp.status == 200
    except Exception as e:
        print(f"[FAQ] in-game post failed: {e}")
        return False


def _faq_short_text(entry, answer_text: str) -> str:
    return entry.get("short") or _faq_plainify(answer_text)


async def _maybe_answer_faq_discord(message: discord.Message) -> None:
    """FAQ pass for guild messages. Called from on_message AFTER the chat
    relay so an in-game audience sees the question before the answer."""
    content = (message.content or "").strip()
    if not content or content.startswith(("!", "/", ".")):
        return
    if message.guild is None:
        return  # DMs are the bug-report follow-up flow
    entry = _faq_find_match(content)
    if entry is None:
        return
    if not _faq_rate_ok(message.channel.id, entry["key"], message.author.id):
        return
    answer = await _faq_resolve_answer(entry, message)
    if not answer:
        return
    try:
        await message.reply(embed=_faq_embed(entry, answer), mention_author=False)
        print(f"[FAQ] answered '{entry['key']}' for {message.author.name} in #{getattr(message.channel, 'name', message.channel.id)}")
    except Exception as ex:
        print(f"[FAQ] discord reply failed: {ex}")
        return
    # Question asked in the chat-bridge channel: the question was relayed
    # in-game, so deliver a short ASCII answer there too.
    if CHAT_CHANNEL_ID and message.channel.id == CHAT_CHANNEL_ID:
        await _post_ingame_chat(_faq_short_text(entry, answer))


async def _maybe_answer_faq_ingame(data: dict) -> None:
    """FAQ pass for live in-game chat messages (WS stream only — the catchup
    replay path never calls this, so old messages can't trigger answers)."""
    content = (data.get("message") or "").strip()
    if not content:
        return
    # Freshness guard: never answer anything older than 2 minutes even if it
    # somehow arrives on the live stream.
    ts = data.get("timestamp")
    if ts:
        try:
            age = (datetime.now(timezone.utc)
                   - datetime.fromisoformat(str(ts).replace("Z", "+00:00"))).total_seconds()
            if age > 120:
                return
        except Exception:
            pass
    entry = _faq_find_match(content)
    if entry is None or entry.get("discord_only"):
        return
    user_key = f"ig:{data.get('steam_id') or data.get('display_name') or ''}"
    if not _faq_rate_ok("ingame", entry["key"], user_key):
        return
    answer = await _faq_resolve_answer(entry, None)
    if not answer:
        return
    sent = await _post_ingame_chat(_faq_short_text(entry, answer))
    if sent:
        print(f"[FAQ] answered '{entry['key']}' in-game for {data.get('display_name')}")
    # Mirror the full answer into the Discord bridge channel so both sides of
    # the conversation see it (the in-game question itself was just relayed).
    if CHAT_CHANNEL_ID:
        try:
            channel = bot.get_channel(CHAT_CHANNEL_ID) or await bot.fetch_channel(CHAT_CHANNEL_ID)
            if channel is not None:
                asker = discord.utils.escape_markdown(data.get("display_name") or "player")
                await channel.send(content=f"-# answering **{asker}** (in-game):",
                                   embed=_faq_embed(entry, answer))
        except Exception as ex:
            print(f"[FAQ] discord mirror failed: {ex}")


# ── #scr-releases mirror (v1.33) ──────────────────────────────────────────
# Every message in the releases channel (bot-posted GitHub announcements AND
# manual posts) is pushed to the server's release_posts table so the in-game
# Home tab shows update notes as they're posted. Upsert by message id, so the
# startup backfill and edit re-pushes are safe to repeat.

async def _push_release_posts(msgs) -> None:
    if http_session is None or not API_SECRET_KEY:
        return
    posts = []
    for m in msgs:
        content = (m.content or "").strip()
        if not content:
            continue  # embed/attachment-only posts have nothing to mirror
        posts.append({
            "discord_message_id": str(m.id),
            "author": getattr(m.author, "display_name", None) or m.author.name,
            "content": content[:4000],
            "posted_at": m.created_at.isoformat(),
        })
    if not posts:
        return
    try:
        async with http_session.post(
            f"{API_BASE_URL}/api/v1/internal/release-posts",
            json={"posts": posts},
            headers={"X-Internal-Key": API_SECRET_KEY},
            timeout=aiohttp.ClientTimeout(total=10),
        ) as resp:
            if resp.status != 200:
                print(f"[RELEASES] mirror push status={resp.status}")
    except Exception as e:
        print(f"[RELEASES] mirror push failed: {e}")


async def backfill_release_posts():
    """On startup, mirror the last 10 releases-channel messages so the Home
    tab has content immediately after this feature deploys (and so edits made
    while the bot was down get picked up)."""
    if not RELEASES_CHANNEL_ID:
        return
    try:
        channel = bot.get_channel(RELEASES_CHANNEL_ID) or await bot.fetch_channel(RELEASES_CHANNEL_ID)
        if channel is None:
            return
        msgs = [m async for m in channel.history(limit=10)]
        await _push_release_posts(msgs)
        print(f"[RELEASES] backfilled {len(msgs)} channel messages to release_posts")
    except Exception as e:
        print(f"[RELEASES] backfill failed: {e}")


@bot.event
async def on_raw_message_edit(payload: discord.RawMessageUpdateEvent):
    """Edits to releases-channel posts re-push so the Home tab shows the
    corrected text (upsert by message id server-side)."""
    if not RELEASES_CHANNEL_ID or payload.channel_id != RELEASES_CHANNEL_ID:
        return
    try:
        channel = bot.get_channel(RELEASES_CHANNEL_ID) or await bot.fetch_channel(RELEASES_CHANNEL_ID)
        msg = await channel.fetch_message(payload.message_id)
        await _push_release_posts([msg])
    except Exception as e:
        print(f"[RELEASES] edit re-push failed: {e}")


async def _faq_discord_task(message: discord.Message) -> None:
    """Task wrapper: keeps FAQ latency out of on_message's command dispatch."""
    try:
        await _maybe_answer_faq_discord(message)
    except Exception as ex:
        print(f"[FAQ] discord handler error: {ex}")


async def _faq_ingame_task(data: dict) -> None:
    """Task wrapper: keeps FAQ API lookups out of the chat WS receive loop —
    a stalled API call inside the async-for body would starve the WS
    heartbeat and drop the whole in-game<->Discord bridge."""
    try:
        await _maybe_answer_faq_ingame(data)
    except Exception as ex:
        print(f"[FAQ] ingame handler error: {ex}")


@bot.hybrid_command(name="faq", description="Look up an FAQ answer (or list all topics)")
@app_commands.describe(topic="Your question, or leave empty to list topics")
async def cmd_faq(ctx, *, topic: str = ""):
    """Manual FAQ trigger - title-first, then the auto-responder matcher."""
    title_matches = []

    def _faq_find_by_title(text):
        """Resolve exact or uniquely partial FAQ titles for the manual command."""
        def normalize_title(value):
            collapsed = _faq_re.sub(r"\s+", " ", (value or "").casefold()).strip()
            return _faq_re.sub(r"^[\W_]+|[\W_]+$", "", collapsed)

        title_matches.clear()
        query = normalize_title(text)
        if not query:
            return None

        normalized = [
            (entry, normalize_title(entry.get("title") or ""))
            for entry in FAQ_ENTRIES
        ]
        for entry, title in normalized:
            if title == query:
                title_matches.append(entry)
                return entry

        title_matches.extend(
            entry for entry, title in normalized
            if title and (query in title or title in query)
        )
        return title_matches[0] if len(title_matches) == 1 else None

    if not topic.strip():
        lines = "\n".join(f"• **{e.get('title')}**" for e in FAQ_ENTRIES)
        embed = discord.Embed(title="💡 FAQ topics",
                              description=("Ask any of these in your own words (I answer automatically), "
                                           "or `/faq <question>`:\n" + lines)[:4096],
                              color=0x5865F2)
        await ctx.send(embed=embed)
        return
    entry = _faq_find_by_title(topic) or _faq_find_match(topic) or _faq_find_match(topic + "?")
    if entry is None:
        if len(title_matches) > 1:
            suggestions = ", ".join(
                f"**{_faq_plainify(e.get('title') or '', cap=200)}**"
                for e in title_matches
            )
            await ctx.send(f"Did you mean: {suggestions}")
        else:
            await ctx.send("No FAQ matches that - try `/faq` for the topic list.")
        return
    await _maybe_defer(ctx)
    # Hybrid slash contexts can expose a truthy synthetic Message whose
    # content/mentions are empty. Always carry the explicit command argument;
    # prefix-command mentions are still supplied as a resolution cache.
    request = {
        "content": topic,
        "author": ctx.author,
        "guild": ctx.guild,
        "mentions": (getattr(ctx.message, "mentions", None) or []),
    }
    answer = await _faq_resolve_answer(entry, request)
    if not answer:
        await ctx.send("Couldn't build that answer right now.")
        return
    await ctx.send(embed=_faq_embed(entry, answer))


@bot.event
async def on_message(message: discord.Message):
    # Releases-channel mirror (v1.33) — BEFORE the bot early-return, because
    # the channel's GitHub announcements are posted by this bot itself.
    if RELEASES_CHANNEL_ID and message.channel and getattr(message.channel, "id", 0) == RELEASES_CHANNEL_ID:
        try:
            await _push_release_posts([message])
        except Exception as ex:
            print(f"[RELEASES] on_message mirror failed: {ex}")
    # Must not block command dispatch.
    if message.author.bot:
        await bot.process_commands(message)
        return
    if CHAT_CHANNEL_ID and message.channel and message.channel.id == CHAT_CHANNEL_ID:
        content = (message.content or "").strip()
        display = getattr(message.author, "global_name", None) or message.author.name
        print(f"[CHAT] Discord msg from {display}: {content[:60]} (session={http_session is not None}, key={'set' if API_SECRET_KEY else 'MISSING'})")
        if content and http_session is not None and API_SECRET_KEY:
            try:
                async with http_session.post(
                    f"{API_BASE_URL}/api/v1/chat/post",
                    json={
                        "discord_id": str(message.author.id),
                        "display_name": display,
                        "message": content,
                    },
                    headers={"X-Internal-Key": API_SECRET_KEY},
                    timeout=aiohttp.ClientTimeout(total=5),
                ) as resp:
                    body = await resp.text()
                    print(f"[CHAT] Relay Discord→API: status={resp.status} body={body[:100]}")
            except Exception as e:
                print(f"[CHAT] Failed to relay Discord -> API: {e}")
    # A plain (non-command) DM to the bot is treated as a follow-up on one of
    # the sender's own bug reports (e.g. "#12 still happens after relaunch").
    if isinstance(message.channel, discord.DMChannel) and message.content \
            and not message.content.startswith("!"):
        try:
            await _handle_ticket_dm(message)
        except Exception as ex:
            print(f"[TICKET-DM] handler error: {ex}")
        return
    # Malformed native room-code warning. Kept in its own task so a Discord
    # send cannot delay prefix/slash command dispatch.
    try:
        asyncio.create_task(_room_code_warning_task(message))
    except Exception as ex:
        print(f"[ROOM-CODE] task spawn error: {ex}")
    # FAQ auto-responder (v1.33) — after the chat relay so in-game viewers see
    # the question before the answer. Spawned as a task so a slow API lookup
    # (dynamic answers hit /leaderboard, /rating-preview) can never delay
    # command dispatch; the match + cooldown stamp run synchronously inside
    # the task before its first await, so duplicates can't double-answer.
    try:
        asyncio.create_task(_faq_discord_task(message))
    except Exception as ex:
        print(f"[FAQ] discord task spawn error: {ex}")
    await bot.process_commands(message)


# Highest message timestamp the bot has ever forwarded to Discord. Used to
# dedupe between catch-up (HTTP /chat/recent on WS reconnect) and the live WS
# stream. Initialized to bot-start time on first connect so we don't spam the
# Discord channel with the entire backlog when the bot first comes online.
_last_relayed_ts: str | None = None

# Synchronous-set dedup of recently-posted message IDs. The _last_relayed_ts gate
# alone races: WS path and catchup poll can BOTH check ts<=last_relayed before
# either updates it (because the update happens AFTER channel.send awaits). Using
# this set BEFORE any await ensures only one task wins per message.
import collections
_RECENT_IDS_CAP = 300
_recent_ids_q = collections.deque(maxlen=_RECENT_IDS_CAP)
_recent_ids_set: set = set()
def _claim_msg_id(msg_id: str) -> bool:
    """Return False if msg_id was already seen (caller should drop the message);
    True if we're the first to see it (caller should post). Synchronous — safe
    for asyncio because no awaits between the check and the add."""
    if msg_id in _recent_ids_set:
        return False
    if len(_recent_ids_q) == _RECENT_IDS_CAP:
        _recent_ids_set.discard(_recent_ids_q[0])
    _recent_ids_q.append(msg_id)
    _recent_ids_set.add(msg_id)
    return True


def _entry_msg_id(data: dict) -> str:
    """Canonical dedup key for a chat entry. The server stamps every message
    with its DB row id and sends THE SAME id via both the WS broadcast and
    /chat/recent, so the live path and the catchup poll agree on identity.
    (The old composite key embedded the timestamp — and the WS broadcast carried
    a broadcast-time stamp while /chat/recent carried the row's created_at: same
    message, two keys, so every WS-relayed message was eligible for a second
    post from the poll. Bug #34.) Id-less entries (persist failure / older API)
    fall back to the legacy composite."""
    mid = data.get("id")
    if mid is not None:
        return f"db:{mid}"
    content = (data.get("message") or "").strip()
    return f"{data.get('steam_id') or data.get('discord_id') or ''}|{data.get('timestamp') or ''}|{content[:80]}"


async def _forward_ingame_to_discord(data: dict) -> bool:
    """Render one ingame chat entry into the Discord channel. Returns True on
    success. Dedup layers:
      1. Synchronous _claim_msg_id on the DB-id key — wins the race between the
         WS path and the catchup poll AND matches across them (same id on both).
      2. _last_relayed_ts — coarse "don't bother with old messages" filter for
         id-LESS (legacy/persist-failed) entries only. Id-bearing entries rely
         on the claim set + startup priming instead — the WS stamp and the DB
         created_at were never comparable values."""
    global _last_relayed_ts
    if (data.get("source") or "") != "ingame":
        return False
    content = (data.get("message") or "").strip()
    if not content:
        return False
    ts = data.get("timestamp")
    if data.get("id") is None and ts and _last_relayed_ts and ts <= _last_relayed_ts:
        return False
    # Claim the message id BEFORE any await — synchronous so the second concurrent
    # caller sees the first's add and bails.
    if not _claim_msg_id(_entry_msg_id(data)):
        return False
    name = data.get("display_name") or "player"
    rating = data.get("rating")
    rating_str = f" ({rating:.0f})" if isinstance(rating, (int, float)) else ""
    title = data.get("title")
    title_str = f" [{title}]" if title else ""
    channel = bot.get_channel(CHAT_CHANNEL_ID) or await bot.fetch_channel(CHAT_CHANNEL_ID)
    if channel is None:
        print(f"[CHAT] Channel {CHAT_CHANNEL_ID} not resolvable")
        return False
    try:
        await channel.send(
            f"**{discord.utils.escape_markdown(name)}"
            f"{discord.utils.escape_markdown(title_str)}"
            f"{rating_str}** (in-game): "
            f"{discord.utils.escape_markdown(content)[:1900]}"
        )
        if ts:
            _last_relayed_ts = ts
        print(f"[CHAT] Posted to Discord: {name}{title_str}: {content[:60]}")
        return True
    except Exception as e:
        print(f"[CHAT] Post to Discord failed: {e}")
        return False


_catchup_primed = False


async def _catchup_ingame_since():
    """On WS (re)connect, pull /chat/recent and forward any ingame entries we
    haven't relayed. Closes the gap where the bot's WS was down and the server
    broadcast had no subscriber.

    First call after bot boot PRIMES instead of posting: it claims every entry
    currently in /chat/recent without sending. The claim set is in-memory, so
    after a restart it's empty — without priming, the first catchup would
    re-post up to 50 messages the previous bot process already relayed."""
    global _catchup_primed
    if http_session is None:
        return
    try:
        async with http_session.get(
            f"{API_BASE_URL}/api/v1/chat/recent",
            params={"limit": 50},
            timeout=aiohttp.ClientTimeout(total=5),
        ) as resp:
            if resp.status != 200:
                print(f"[CHAT] catchup fetch status={resp.status}")
                return
            payload = await resp.json()
    except Exception as e:
        print(f"[CHAT] catchup fetch failed: {e}")
        return
    msgs = payload.get("messages") or []
    if not _catchup_primed:
        for m in msgs:
            _claim_msg_id(_entry_msg_id(m))
        _catchup_primed = True
        print(f"[CHAT] catchup primed {len(msgs)} pre-boot entries (not re-posted)")
        return
    forwarded = 0
    for m in msgs:  # already chronological (oldest first)
        if await _forward_ingame_to_discord(m):
            forwarded += 1
    if forwarded:
        print(f"[CHAT] catchup forwarded {forwarded} missed in-game messages")


async def chat_ws_listener():
    """Long-lived WS subscription. Reconnects with backoff on drop."""
    global _last_relayed_ts
    if _last_relayed_ts is None:
        # First-ever start: don't backfill the entire history. Anchor at boot time.
        _last_relayed_ts = datetime.now(timezone.utc).isoformat()
    url = API_BASE_URL.replace("http://", "ws://").replace("https://", "wss://") + "/api/v1/ws/chat"
    backoff = 2
    while True:
        try:
            if http_session is None:
                await asyncio.sleep(1); continue
            async with http_session.ws_connect(url, heartbeat=30) as ws:
                print(f"[CHAT] WS connected: {url}")
                backoff = 2
                # Close the gap where the bot's WS was down: replay any ingame
                # messages from /chat/recent that are newer than what we last
                # relayed. _forward_ingame_to_discord dedupes via timestamp so
                # the live stream below won't re-post these.
                await _catchup_ingame_since()
                async for msg in ws:
                    if msg.type != aiohttp.WSMsgType.TEXT:
                        print(f"[CHAT] WS non-text: {msg.type}")
                        continue
                    try:
                        data = msg.json()
                    except Exception as e:
                        print(f"[CHAT] WS parse error: {e}")
                        continue
                    src = data.get("source")
                    content = (data.get("message") or "").strip()
                    name = data.get("display_name") or "player"
                    print(f"[CHAT] WS <- source={src} name={name} msg={content[:60]}")
                    if src != "ingame":
                        continue  # Discord originals already live there
                    await _forward_ingame_to_discord(data)
                    # FAQ auto-responder (v1.33) — live stream only, so the
                    # catchup replay can never answer stale questions. Spawned
                    # as a task so its API lookups never block this receive
                    # loop (heartbeat starvation would drop the bridge).
                    try:
                        asyncio.create_task(_faq_ingame_task(data))
                    except Exception as ex:
                        print(f"[FAQ] ingame task spawn error: {ex}")
        except Exception as e:
            print(f"[CHAT] WS dropped: {e} (reconnect in {backoff}s)")
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 60)

@bot.event
async def on_close():
    if http_session: await http_session.close()

@bot.hybrid_command(name="link", description="Link your Discord to your ROUNDS Steam account")
@app_commands.describe(code="6-character code from the in-game Competitive menu")
async def cmd_link(ctx, code: str = None):
    if not code:
        await ctx.send("**How to link:**\n1. Open ROUNDS → press F5 → Home tab (Discord Link panel)\n2. Click **Get Link Code**\n3. Type `!link YOUR_CODE` here"); return
    # July 22 (items 8+9): identity split — discord_username is the unique
    # @handle (user.name; Home tab "Linked as @foo"), discord_display_name is
    # the global display name (leaderboard opt-in surface).
    result = await api_post("/players/link-discord", params={
        "code": code.upper(),
        "discord_id": str(ctx.author.id),
        "discord_username": ctx.author.name,
        "discord_display_name": getattr(ctx.author, "global_name", None) or ctx.author.name,
    })
    if not result: await ctx.send("❌ API unreachable."); return
    if "error" in result:
        await ctx.send("❌ Invalid or expired code." if result.get("status") == 404 else f"❌ {result['error']}"); return
    await ctx.send(f"✅ Linked! **{ctx.author.display_name}** → Steam **{result.get('display_name')}** (`{result.get('steam_id')}`)")
    data = await api_get(f"/players/by-discord/{ctx.author.id}")
    if data and "rating" in data:
        rank = await update_member_role(ctx.author, data["rating"])
        await ctx.send(f"{rank_emoji(rank)} Rank: **{rank}** ({data['rating']:.0f})")

@bot.hybrid_command(name="rank", description="Ranked stats: rating, tier, streaks, leaderboard position")
@app_commands.describe(member="Player to look up (defaults to yourself)")
async def cmd_rank(ctx, member: discord.Member = None):
    """RANKED-ONLY view (v1.32 rework): rating/RD/peak + tier, ranked series
    record + best/current streak, lb position, leave rate, sweeps. Casual and
    general clutter lives in /stats."""
    target = member or ctx.author
    link = await api_get(f"/players/by-discord/{target.id}")
    if not link:
        await ctx.send("❌ Not linked. Use `/link` first." if target == ctx.author else f"❌ {target.display_name} not linked."); return
    steam_id = link["steam_id"]
    await _maybe_defer(ctx)
    s = await api_get(f"/players/{steam_id}")
    if not s: await ctx.send("❌ Could not fetch stats."); return
    rank = get_rank_name(s["rating"])
    peak = s.get("peak_rating", s["rating"])
    embed = discord.Embed(title=f"{rank_emoji(rank)}  {s['display_name']}  —  {rank}", color=discord.Color.gold())
    embed.set_thumbnail(url=target.display_avatar.url)

    # Elo block
    elo_lines = f"**{s['rating']:.0f}** Elo  ·  Peak: **{peak:.0f}**  ·  RD: {s['rating_deviation']:.0f}"
    embed.add_field(name="📊  Rating", value=elo_lines, inline=False)

    # Ranked series
    rw, rl = s.get("ranked_series_wins", 0), s.get("ranked_series_losses", 0)
    total = rw + rl
    wr = f"{rw/total*100:.1f}%" if total > 0 else "—"
    series_lines = f"**{rw}**W / **{rl}**L  ({wr})"
    br = s.get("best_ranked_streak", 0)
    if br > 0: series_lines += f"\nBest Streak: **{br}W** 🔥"
    embed.add_field(name="🏆  Ranked Series", value=series_lines, inline=True)

    # Current ranked streak — not a server field; recompute from recent match
    # history exactly like the client's CalcStreak (NativeUI.cs:6681):
    # newest-first consecutive same-result among ranked entries.
    cur = await _current_streak(steam_id, ranked=True)
    embed.add_field(name="📈  Current Streak", value=(streak_str(cur) or "—"), inline=True)

    # Sweeps (ranked 5-0s)
    sg, st = s.get("sweeps_given", 0), s.get("sweeps_taken", 0)
    sweep_lines = f"5-0 Given: **{sg}** 🧹\n0-5 Taken: **{st}**"
    embed.add_field(name="💨  Sweeps", value=sweep_lines, inline=True)

    # Leave rate
    dc = s.get("ranked_dc_count", 0)
    if dc > 0:
        rt_total = rw + rl + dc
        pct = f"{dc/rt_total*100:.1f}%" if rt_total > 0 else "—"
        embed.add_field(name="🚪  Leave Rate", value=f"**{dc}** / {rt_total} ({pct})", inline=True)

    pos = await get_lb_position(steam_id)
    embed.set_footer(text=f"Leaderboard: #{pos}  •  Steam: {s['steam_id']}")
    await ctx.send(embed=embed)

async def get_lb_position(steam_id):
    data = await api_get("/leaderboard?limit=200&min_matches=1")
    if not data or not data.get("entries"): return "?"
    for e in data["entries"]:
        if e["steam_id"] == steam_id: return str(e["rank"])
    return "Unranked"


async def _maybe_defer(ctx):
    """Defer a hybrid invocation (typing indicator for !prefix, deferred
    response for slash). Commands below stack 2-4 API calls — a slash
    interaction hard-fails past 3s without this."""
    try:
        await ctx.defer()
    except Exception:
        pass  # already deferred / prefix edge — never block the command


def _calc_streak(entries, ranked=None):
    """Mirror the client's CalcStreak (NativeUI.cs:6681): walk a newest-first
    match list, count consecutive same-result games. +N = win streak,
    -N = loss streak. ranked=True filters to ranked entries, False to casual,
    None counts all modes."""
    if not isinstance(entries, list) or not entries:
        return 0
    if ranked is not None:
        entries = [m for m in entries if isinstance(m, dict) and bool(m.get("is_ranked")) == ranked]
    if not entries:
        return 0
    first = bool(entries[0].get("won"))
    c = 0
    for m in entries:
        if bool(m.get("won")) == first:
            c += 1
        else:
            break
    return c if first else -c


async def _current_streak(steam_id, ranked=None):
    """Current win/loss streak from the 50 most recent matches (the /matches
    endpoint returns newest-first — ORDER BY m.ended_at DESC, main.py:2652)."""
    hist = await api_get(f"/players/{steam_id}/matches?limit=50")
    return _calc_streak(hist, ranked)


def _top_cards_lines(s, limit=5):
    """Top-cards lines from /players/{steam}. top_cards is a list of dicts
    ({card_name, times_picked, ...} — main.py:2086); tolerate the legacy
    parallel-list shape too."""
    lines = []
    for c in (s.get("top_cards") or [])[:limit]:
        if isinstance(c, dict) and c.get("card_name"):
            lines.append(f"**{c['card_name']}** ({c.get('times_picked', 0)}x)")
    if not lines:
        names = s.get("top_card_names") or []
        picks = s.get("top_card_picks") or []
        for i in range(min(limit, len(names))):
            p = f" ({picks[i]}x)" if i < len(picks) else ""
            lines.append(f"**{names[i]}**{p}")
    return lines


def _hit_block_str(s):
    """Lifetime hit% / block% from the raw counters on /players/{steam}."""
    parts = []
    bf, bh = s.get("bullets_fired", 0) or 0, s.get("bullets_hit", 0) or 0
    ba, bs = s.get("blocks_activated", 0) or 0, s.get("blocks_successful", 0) or 0
    if bf > 0:
        parts.append(f"Hit: **{bh / bf * 100:.1f}%**")
    if ba > 0:
        parts.append(f"Block: **{bs / ba * 100:.1f}%**")
    return "  ·  ".join(parts)

@bot.hybrid_command(name="stats", description="General stats: record, casual, level, gold, accuracy, cards")
@app_commands.describe(member="Player to look up (defaults to yourself)")
async def cmd_stats(ctx, member: discord.Member = None):
    """GENERAL view (v1.32 rework): all-modes record, casual record + best
    casual streak, level/XP, gold (hidden when the player toggled hide_gold),
    hit%/block%, top cards, 2v2 line, avg FPS. Ranked detail lives in /rank."""
    target = member or ctx.author
    link = await api_get(f"/players/by-discord/{target.id}")
    if not link:
        await ctx.send("❌ Not linked." if target == ctx.author else f"❌ {target.display_name} not linked."); return
    steam_id = link["steam_id"]
    await _maybe_defer(ctx)
    s = await api_get(f"/players/{steam_id}")
    if not s: await ctx.send("❌ Could not fetch stats."); return
    embed = discord.Embed(title=f"📋  {s['display_name']}  —  Overall Stats", color=discord.Color.blue())
    embed.set_thumbnail(url=target.display_avatar.url)

    # Overall record — every mode combined.
    tw, tl = s.get("wins", 0), s.get("losses", 0)
    tt = s.get("total_matches", 0)
    twr = f"{tw/tt*100:.1f}%" if tt > 0 else "—"
    embed.add_field(name="📊  Total Record", value=f"**{tt}** matches  —  **{tw}**W / **{tl}**L  ({twr})", inline=False)

    # Casual record + best casual streak.
    cw, cl = s.get("casual_wins", 0), s.get("casual_losses", 0)
    ct = cw + cl
    cwr = f"{cw/ct*100:.1f}%" if ct > 0 else "—"
    casual_str = f"**{cw}**W / **{cl}**L  ({cwr})" if ct > 0 else "—"
    bc = s.get("best_casual_streak", 0)
    if bc > 0:
        casual_str += f"\nBest Streak: **{bc}W**"
    embed.add_field(name="🎮  Casual", value=casual_str, inline=True)

    # Level & XP
    embed.add_field(name="⭐  Level", value=f"**{s.get('level', 0)}**  ·  {s.get('total_xp', 0):,} XP", inline=True)

    # Gold — respect the player's hide_gold toggle (same rule as the in-game
    # leaderboard): if they hid it there, the bot doesn't out it here.
    if not s.get("hide_gold"):
        net_gold = (s.get("gold_earned", 0) or 0) - (s.get("gold_spent", 0) or 0)
        embed.add_field(name="💰  Gold", value=f"**{net_gold:,}**g", inline=True)

    # Lifetime accuracy (hit%) + block success.
    acc = _hit_block_str(s)
    if acc:
        embed.add_field(name="🎯  Accuracy", value=acc, inline=True)

    # 2v2 line — only when the player actually has a 2v2 rating.
    if (s.get("team_rating") or 0) > 0:
        team = await api_get(f"/team/players/{steam_id}/team-stats")
        if team and (team.get("rating") or 0) > 0:
            embed.add_field(
                name="👥  2v2",
                value=f"**{team['rating']:.0f}**  ·  {team.get('series_wins', 0)}W / {team.get('series_losses', 0)}L series",
                inline=True,
            )

    # Avg FPS (from per-match telemetry).
    if (s.get("avg_fps") or 0) > 0:
        embed.add_field(name="🖥️  Avg FPS", value=f"**{s['avg_fps']}**", inline=True)

    # Top cards
    cards_lines = _top_cards_lines(s, limit=5)
    if cards_lines:
        embed.add_field(name="🃏  Top Cards", value="\n".join(cards_lines), inline=False)

    embed.set_footer(text=f"Steam: {s['steam_id']}")
    await ctx.send(embed=embed)

def _lb_line(e, rank=None):
    """One short leaderboard row. Kept terse — a 50-row page must fit inside
    Discord's 6000-chars-across-all-embeds message budget.

    rank: pass the POSITION-derived rank (offset + index + 1) instead of
    trusting e["rank"] on offset pages. The server's GET /leaderboard does
    `rank=row["rank"] + offset` (main.py:2034) on top of a SQL ROW_NUMBER()
    that Postgres evaluates BEFORE LIMIT/OFFSET — i.e. ROW_NUMBER is already
    absolute, so the entry rank arrives double-offset whenever offset > 0
    (offset 100 page rendered as #201+, Sid's /lb 2 report). Position-derived
    ranks are correct regardless; None falls back to e["rank"] (fine at
    offset 0, where the server's +offset adds nothing)."""
    if rank is None:
        rank = e["rank"]
    emoji = rank_emoji(get_rank_name(e["rating"]))
    name = str(e["display_name"])[:24]
    return f"`#{rank:>3}` {emoji} **{name}** — {e['rating']} ({e['wins']}W/{e['losses']}L)"


def _split_lb_descriptions(lines, first_header=""):
    """Split leaderboard rows into up to 3 embed descriptions. Discord caps a
    single embed description at 4096 chars and the TOTAL across all embeds in
    one message at 6000 — a worst-case page can exceed both, so we chunk at a
    safe per-embed budget and truncate with an '…and N more' tail when even
    the whole message budget runs out. At 50 rows/page (v1.32.1) a typical
    page is ~3.1k chars = one embed; this stays as the safety net."""
    PER_EMBED = 3900   # under the 4096 hard cap
    TOTAL = 5700       # under the 6000 hard cap (leaves room for title/footer)
    MAX_EMBEDS = 3
    if not lines:
        return [(first_header + "(no players)")]
    chunks, cur, total_chars = [], first_header, len(first_header)
    truncated_from = None
    for i, ln in enumerate(lines):
        need = len(ln) + 1
        if total_chars + need > TOTAL:
            truncated_from = i
            break
        if len(cur) + need > PER_EMBED:
            if len(chunks) >= MAX_EMBEDS - 1:
                truncated_from = i
                break
            chunks.append(cur.rstrip("\n"))
            cur = ""
        cur += ln + "\n"
        total_chars += need
    if truncated_from is not None:
        cur += f"…and {len(lines) - truncated_from} more"
    if cur.strip():
        chunks.append(cur.rstrip("\n"))
    if not chunks:
        chunks = [(first_header + "(no players)").strip()]
    return chunks


@bot.hybrid_command(name="lb", description="Show the ranked leaderboard (50 per page)")
@app_commands.describe(page="Page number (default: 1)")
async def cmd_leaderboard(ctx, page: int = 1):
    # 50/page (Sid, v1.32.1): 100 real rows (rank + emoji + bold names +
    # ratings + W/L) blew the splitter's 5700-char whole-message budget around
    # row ~66 and the tail truncated — the "cuts off at #67" report. 50 rows
    # fit comfortably (worst case ~3.1k chars) while still usually being one
    # embed; the splitter stays as a safety net.
    per_page = 50  # match the #scr-leaderboard channel board (LB_PAGE_SIZE)
    page = max(1, page)
    offset = (page - 1) * per_page
    data = await api_get(f"/leaderboard?limit={per_page}&offset={offset}&min_matches=1")
    if not data or not data.get("entries"): await ctx.send("❌ No data."); return
    # Rank is derived from offset + position, NOT from entry["rank"] — the
    # server double-adds offset to an already-absolute ROW_NUMBER (see
    # _lb_line docstring), which made /lb 2 start at #201 instead of #101.
    # Position math gives page 2 @ offset 50 → first rank 51. Always correct.
    lines = [_lb_line(e, rank=offset + i + 1) for i, e in enumerate(data["entries"])]
    total = data.get("total_players", 0)
    total_pages = max(1, (total + per_page - 1) // per_page)
    # 50 rows can still exceed one embed's 4096-char description in the worst
    # case — split across up to 3 embeds in ONE message.
    descs = _split_lb_descriptions(lines)
    embeds = []
    for ci, desc in enumerate(descs):
        em = discord.Embed(
            title="🏆 Competitive ROUNDS Leaderboard" if ci == 0 else None,
            description=desc,
            color=discord.Color.gold(),
        )
        if ci == len(descs) - 1:
            em.set_footer(text=f"Page {page}/{total_pages} • {total} ranked players"
                          + (f" • /lb {page+1} for next page" if page < total_pages else ""))
        embeds.append(em)
    await ctx.send(embeds=embeds)


# ── Stats commands: /compare, /graph, /mystats, /cards ───────────────────
# /compare (v1.32.1 rework, per Sid) is a HEAD-TO-HEAD between exactly two
# players: overall record between them + their recent mutual games with the
# cards each picked. /graph carries ALL the in-game Compare-tab charts as
# matplotlib PNGs — elo history line, grouped/simple bars, top-cards hbars,
# region pies — for 2-4 players. /mystats is the F5 "My Stats" page as one
# embed. /cards mirrors the Card Stats tab (per-player with a member arg,
# community-wide without).

_COMPARE_COLORS = ["#5865F2", "#ED4245", "#57F287", "#FEE75C"]  # blurple/red/green/yellow

# pyplot's global figure state is NOT thread-safe — two /compare invocations
# racing inside asyncio.to_thread can cross their figures (adversarial review).
# One render at a time; charts take ~100ms so serialization is invisible.
_mpl_render_lock = threading.Lock()


def _render_rating_history_png(series):
    """Render the overlay rating-history line chart to a PNG BytesIO.
    series = [{"name": str, "points": [(datetime, rating), ...]}], each list
    oldest-first. Runs inside asyncio.to_thread — matplotlib is CPU-bound and
    must never block the event loop (heartbeat/WS would starve)."""
    with _mpl_render_lock:
        return _render_rating_history_png_locked(series)


def _render_rating_history_png_locked(series):
    bg = "#2b2d31"  # Discord embed grey — the chart reads as part of the embed
    fig, ax = plt.subplots(figsize=(10, 5.5), dpi=110)
    try:
        fig.patch.set_facecolor(bg)
        ax.set_facecolor(bg)
        for i, sr in enumerate(series):
            xs = [p[0] for p in sr["points"]]
            ys = [p[1] for p in sr["points"]]
            ax.plot(xs, ys, color=_COMPARE_COLORS[i % len(_COMPARE_COLORS)],
                    linewidth=2.2, marker="o", markersize=2.5, label=str(sr["name"])[:24])
        ax.set_title("Ranked Rating History", color="#ffffff", fontsize=14, pad=12)
        ax.tick_params(colors="#b5bac1", labelsize=9)
        for spine in ax.spines.values():
            spine.set_color("#4a4d55")
        ax.grid(True, color="#4a4d55", linewidth=0.6, alpha=0.5)
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
        fig.autofmt_xdate()
        ax.legend(facecolor="#232428", edgecolor="#4a4d55", labelcolor="#dbdee1", fontsize=9)
        fig.tight_layout()
        buf = io.BytesIO()
        fig.savefig(buf, format="png", facecolor=bg)
        buf.seek(0)
        return buf
    finally:
        plt.close(fig)


async def _fetch_rating_history(steam_id):
    """History points for one player, newest endpoint first: the lean
    /rating-history endpoint (v1.32 server contract), falling back to the
    heavy /players/{steam} recent_rating_history when it isn't there yet.
    Returns (history_list, stats_or_none) — stats is reused for rating/peak."""
    hist = None
    lean = await api_get(f"/players/{steam_id}/rating-history?limit=500")
    if isinstance(lean, dict):
        hist = lean.get("history")
    stats = await api_get(f"/players/{steam_id}")
    if hist is None and isinstance(stats, dict):
        hist = stats.get("recent_rating_history") or []
    return (hist or []), stats


def _history_to_points(hist):
    """[{rating, rd, date}] -> sorted [(datetime, rating)], with the client's
    synthetic 1500 baseline prepended one day before the first snapshot
    (ApiClient.cs:3187 convention) so lines start from the shared origin."""
    pts = []
    for h in hist:
        if not isinstance(h, dict):
            continue
        try:
            d = datetime.fromisoformat(str(h.get("date")).replace("Z", "+00:00"))
            r = float(h.get("rating"))
        except Exception:
            continue
        pts.append((d, r))
    pts.sort(key=lambda x: x[0])
    if pts and pts[0][1] != 1500.0:
        pts.insert(0, (pts[0][0] - timedelta(days=1), 1500.0))
    return pts


# Wider palette for pie slices / >4-color needs (first 4 = _COMPARE_COLORS so
# player colors stay consistent across chart kinds).
_PIE_COLORS = ["#5865F2", "#ED4245", "#57F287", "#FEE75C", "#EB459E",
               "#3BA55D", "#FAA61A", "#00B0F4", "#9B59B6", "#95A5A6"]

_CHART_BG = "#2b2d31"      # Discord embed grey — charts read as part of the embed
_CHART_FG = "#dbdee1"
_CHART_MUTED = "#b5bac1"
_CHART_GRID = "#4a4d55"


def _pct(n, d):
    """Safe percentage — 0.0 on a zero/None denominator (hit% for a player
    with no recorded shots must render as 0, not ZeroDivisionError)."""
    n, d = (n or 0), (d or 0)
    return (n / d * 100.0) if d else 0.0


def _style_axes(ax):
    ax.set_facecolor(_CHART_BG)
    ax.tick_params(colors=_CHART_MUTED, labelsize=9)
    for spine in ax.spines.values():
        spine.set_color(_CHART_GRID)


def _render_bar_chart_png(title, player_names, groups, ylabel=None, value_fmt="{:.0f}"):
    """THE generic bar renderer for /graph (one function, not 15 bespoke ones).
    groups = [(series_label, [value_per_player])]. One group → simple bars in
    per-player colors, no legend; 2+ groups → grouped bars in per-series
    colors + legend. Values are annotated above each bar with value_fmt.
    Runs inside the render lock — pyplot global state is not thread-safe."""
    with _mpl_render_lock:
        fig, ax = plt.subplots(figsize=(10, 5.5), dpi=110)
        try:
            fig.patch.set_facecolor(_CHART_BG)
            _style_axes(ax)
            n = len(player_names)
            g = max(1, len(groups))
            width = 0.8 / g
            peak = 0.0
            for gi, (label, vals) in enumerate(groups):
                xs = [x - 0.4 + width * (gi + 0.5) for x in range(n)]
                if g == 1:
                    colors = [_COMPARE_COLORS[i % len(_COMPARE_COLORS)] for i in range(n)]
                    bars = ax.bar(xs, vals, width=width * 0.9, color=colors)
                else:
                    bars = ax.bar(xs, vals, width=width * 0.9,
                                  color=_COMPARE_COLORS[gi % len(_COMPARE_COLORS)], label=label)
                for b, v in zip(bars, vals):
                    peak = max(peak, float(v))
                    ax.text(b.get_x() + b.get_width() / 2, b.get_height(),
                            value_fmt.format(v), ha="center", va="bottom",
                            color=_CHART_FG, fontsize=9)
            ax.set_xticks(range(n))
            ax.set_xticklabels([str(nm)[:16] for nm in player_names],
                               color=_CHART_FG, fontsize=10)
            # Headroom so the value annotations never clip on the tallest bar;
            # floor of 1 keeps an all-zero chart from degenerating.
            ax.set_ylim(0, max(peak * 1.18, 1.0))
            if ylabel:
                ax.set_ylabel(ylabel, color=_CHART_MUTED, fontsize=10)
            ax.set_title(title, color="#ffffff", fontsize=14, pad=12)
            ax.grid(True, axis="y", color=_CHART_GRID, linewidth=0.6, alpha=0.5)
            ax.set_axisbelow(True)
            if g > 1:
                ax.legend(facecolor="#232428", edgecolor=_CHART_GRID,
                          labelcolor=_CHART_FG, fontsize=9)
            fig.tight_layout()
            buf = io.BytesIO()
            fig.savefig(buf, format="png", facecolor=_CHART_BG)
            buf.seek(0)
            return buf
        finally:
            plt.close(fig)


def _render_top_cards_png(players):
    """Per-player horizontal bar of top-card pick counts, WR% on each bar.
    players = [{"name": str, "cards": [(card_name, times_picked, wr_pct)]}]."""
    with _mpl_render_lock:
        n = len(players)
        fig, axes = plt.subplots(1, n, figsize=(max(5.2 * n, 7), 5.6), dpi=110, squeeze=False)
        try:
            fig.patch.set_facecolor(_CHART_BG)
            for i, p in enumerate(players):
                ax = axes[0][i]
                _style_axes(ax)
                cards = p["cards"]
                # barh plots bottom-up; reverse so the top pick sits on top.
                names = [str(c[0])[:18] for c in cards][::-1]
                picks = [c[1] for c in cards][::-1]
                wrs = [c[2] for c in cards][::-1]
                bars = ax.barh(range(len(names)), picks,
                               color=_COMPARE_COLORS[i % len(_COMPARE_COLORS)])
                ax.set_yticks(range(len(names)))
                ax.set_yticklabels(names, color=_CHART_FG, fontsize=9)
                for b, wr in zip(bars, wrs):
                    ax.text(b.get_width(), b.get_y() + b.get_height() / 2,
                            f" {wr:.0f}% WR", va="center", color=_CHART_FG, fontsize=8)
                ax.set_title(str(p["name"])[:20], color="#ffffff", fontsize=12)
                ax.margins(x=0.25)  # room for the WR labels past the bar tips
                ax.grid(True, axis="x", color=_CHART_GRID, linewidth=0.6, alpha=0.5)
                ax.set_axisbelow(True)
            fig.suptitle("Top Cards — bar = picks, label = win rate",
                         color="#ffffff", fontsize=14)
            fig.tight_layout(rect=(0, 0, 1, 0.94))
            buf = io.BytesIO()
            fig.savefig(buf, format="png", facecolor=_CHART_BG)
            buf.seek(0)
            return buf
        finally:
            plt.close(fig)


def _render_region_pies_png(players):
    """Side-by-side region pies, one per player.
    players = [{"name": str, "labels": [str], "values": [int]}]."""
    with _mpl_render_lock:
        n = len(players)
        fig, axes = plt.subplots(1, n, figsize=(max(5.0 * n, 7), 5.2), dpi=110, squeeze=False)
        try:
            fig.patch.set_facecolor(_CHART_BG)
            for i, p in enumerate(players):
                ax = axes[0][i]
                ax.set_facecolor(_CHART_BG)
                ax.pie(p["values"], labels=p["labels"], autopct="%1.0f%%",
                       colors=_PIE_COLORS[:len(p["values"])],
                       textprops={"color": _CHART_FG, "fontsize": 9},
                       wedgeprops={"edgecolor": _CHART_BG, "linewidth": 1.0})
                ax.set_title(str(p["name"])[:20], color="#ffffff", fontsize=12)
            fig.suptitle("Region Time — matches per Photon region",
                         color="#ffffff", fontsize=14)
            fig.tight_layout(rect=(0, 0, 1, 0.94))
            buf = io.BytesIO()
            fig.savefig(buf, format="png", facecolor=_CHART_BG)
            buf.seek(0)
            return buf
        finally:
            plt.close(fig)


# ── /graph metric table ───────────────────────────────────────────────────
# Every bar-style Compare-tab metric, mapped to /players/{steam_id} fields
# (all verified against backend/api/schemas.py PlayerStatsResponse — learning
# #46: never guess schema fields).
#   title/ylabel/fmt: chart cosmetics.
#   series: [(label, fn(stats)->float)] — 1 series = simple bar, 2 = grouped.
#   need:   raw response fields whose ALL-falsy state means "no data recorded"
#           for that player (rendered as 0 + called out in the footnote).
#           Empty = a zero is a real zero (e.g. 0 achievements).
_GRAPH_BAR_METRICS = {
    "hit-block": {
        "title": "Hit % vs Block %", "ylabel": "%", "fmt": "{:.1f}",
        "series": [("Hit %", lambda s: _pct(s.get("bullets_hit"), s.get("bullets_fired"))),
                   ("Block %", lambda s: _pct(s.get("blocks_successful"), s.get("blocks_activated")))],
        "need": ["bullets_fired", "blocks_activated"],
    },
    "cards-per-game": {
        "title": "Avg Cards per Game", "ylabel": "cards", "fmt": "{:.2f}",
        "series": [("Cards/game", lambda s: float(s.get("avg_cards_per_game") or 0))],
        "need": ["avg_cards_per_game"],
    },
    "fps": {
        "title": "Average FPS", "ylabel": "FPS", "fmt": "{:.0f}",
        "series": [("Avg FPS", lambda s: float(s.get("avg_fps") or 0))],
        "need": ["avg_fps"],
    },
    "peak-elo": {
        "title": "Peak Elo", "ylabel": "Elo", "fmt": "{:.0f}",
        "series": [("Peak", lambda s: float(s.get("peak_rating") or 0))],
        "need": [],
    },
    "xp": {
        "title": "Total XP", "ylabel": "XP", "fmt": "{:,.0f}",
        "series": [("Total XP", lambda s: float(s.get("total_xp") or 0))],
        "need": [],
    },
    "achievements": {
        "title": "Achievements Unlocked", "ylabel": "unlocked", "fmt": "{:.0f}",
        "series": [("Achievements", lambda s: float(s.get("achievements_unlocked") or 0))],
        "need": [],
    },
    "streaks": {
        "title": "Best Win Streaks", "ylabel": "wins", "fmt": "{:.0f}",
        "series": [("Ranked", lambda s: float(s.get("best_ranked_streak") or 0)),
                   ("Casual", lambda s: float(s.get("best_casual_streak") or 0))],
        "need": [],
    },
    "sweeps": {
        "title": "5-0 Sweeps", "ylabel": "sweeps", "fmt": "{:.0f}",
        "series": [("Given", lambda s: float(s.get("sweeps_given") or 0)),
                   ("Taken", lambda s: float(s.get("sweeps_taken") or 0))],
        "need": [],
    },
    "bets": {
        "title": "Betting Record", "ylabel": "bets", "fmt": "{:.0f}",
        "series": [("Won", lambda s: float(s.get("bets_won") or 0)),
                   ("Lost", lambda s: float(s.get("bets_lost") or 0))],
        "need": [],
    },
    "keys-per-sec": {
        "title": "Avg Keys per Second", "ylabel": "keys/s", "fmt": "{:.2f}",
        "series": [("Keys/s", lambda s: float(s.get("avg_keys_per_sec") or 0))],
        "need": ["avg_keys_per_sec"],
    },
    "keys-per-game": {
        "title": "Avg Keys per Game", "ylabel": "keys", "fmt": "{:,.0f}",
        "series": [("Keys/game", lambda s: float(s.get("avg_keys_per_game") or 0))],
        "need": ["avg_keys_per_game"],
    },
    "game-length": {
        "title": "Avg Game Length", "ylabel": "minutes", "fmt": "{:.1f}",
        "series": [("Minutes", lambda s: (s.get("avg_game_seconds") or 0) / 60.0)],
        "need": ["avg_game_seconds"],
    },
    "2v2": {
        "title": "2v2 Rating", "ylabel": "Elo", "fmt": "{:.0f}",
        "series": [("2v2 rating", lambda s: float(s.get("team_rating") or 0))],
        "need": [],  # zero-rated players are DROPPED (special-cased), not zeroed
    },
}

_GraphMetric = Literal["elo", "hit-block", "cards-per-game", "fps", "peak-elo",
                       "xp", "achievements", "streaks", "sweeps", "bets",
                       "keys-per-sec", "keys-per-game", "game-length", "2v2",
                       "top-cards", "region"]


def _cards_str(cards, cap=8):
    """Join a match row's cards_picked/opponent_cards_picked (list of
    {card_name, pick_order, ...} dicts) into 'Card, Card, Card +N more' in
    pick order. '—' when the row has no card data (pre-card-tracking games)."""
    names = []
    for c in sorted([c for c in (cards or []) if isinstance(c, dict)],
                    key=lambda c: c.get("pick_order") or 0):
        nm = c.get("card_name")
        if nm:
            names.append(str(nm))
    if not names:
        return "—"
    out = ", ".join(names[:cap])
    if len(names) > cap:
        out += f" +{len(names) - cap} more"
    return out


def _match_date_str(m):
    try:
        d = datetime.fromisoformat(str(m.get("ended_at")).replace("Z", "+00:00"))
        return d.strftime("%b %d")
    except Exception:
        return "?"


COMPARE_PAGE_SIZE = 5


class ComparePaginator(discord.ui.View):
    """First/Prev/Next/Last pager over a pair's mutual games (v1.33 — /compare
    previously hard-capped at 6 games with no buttons at all). Caches the
    filtered games list so page flips never re-hit the API. 15-min timeout,
    after which the buttons grey out so the message doesn't look live."""

    def __init__(self, name_a: str, name_b: str, rec_val: str,
                 cards_val: str | None, games: list):
        super().__init__(timeout=900)
        self.name_a, self.name_b = name_a, name_b
        self.rec_val, self.cards_val = rec_val, cards_val
        self.games = games
        self.page = 0
        self.total_pages = max(1, (len(games) + COMPARE_PAGE_SIZE - 1) // COMPARE_PAGE_SIZE)
        self.message = None
        self._update_buttons()

    def build_embed(self) -> discord.Embed:
        embed = discord.Embed(title=f"⚔️ {self.name_a} vs {self.name_b}", color=0xE67E22)
        embed.add_field(name="📊  Overall head-to-head", value=self.rec_val[:1024], inline=False)
        if self.cards_val:
            embed.add_field(name="🃏  Most-picked cards vs each other",
                            value=self.cards_val[:1024], inline=False)
        # One field per game (field values carry their own 1024 cap; cards
        # would blow a single shared field). Budget-guard the whole embed
        # under Discord's 6000-char message total.
        start = self.page * COMPARE_PAGE_SIZE
        budget = 4200
        shown = 0
        for m in self.games[start:start + COMPARE_PAGE_SIZE]:
            wl = "✅ W" if m.get("won") else "❌ L"
            score = f"{m.get('player_rounds_won', 0)}-{m.get('opponent_rounds_won', 0)}"
            tag = "Ranked" if m.get("is_ranked") else "Casual"
            fname = f"{_match_date_str(m)} — {wl} {score} · {tag}"
            fval = (f"{self.name_a[:14]}: {_cards_str(m.get('cards_picked'))} | "
                    f"{self.name_b[:14]}: {_cards_str(m.get('opponent_cards_picked'))}")[:1024]
            if len(fname) + len(fval) > budget:
                break
            budget -= len(fname) + len(fval)
            embed.add_field(name=fname[:256], value=fval, inline=False)
            shown += 1
        if self.games and shown == 0:
            embed.add_field(name="Recent games", value="(too much card data to show)", inline=False)
        embed.set_footer(text=f"Page {self.page + 1}/{self.total_pages} • "
                              f"{len(self.games)} recent mutual games • record is lifetime")
        return embed

    def _update_buttons(self):
        at_first = self.page <= 0
        at_last = self.page >= self.total_pages - 1
        self.btn_first.disabled = at_first
        self.btn_prev.disabled = at_first
        self.btn_next.disabled = at_last
        self.btn_last.disabled = at_last

    async def _flip(self, interaction: discord.Interaction, page: int):
        self.page = max(0, min(self.total_pages - 1, page))
        self._update_buttons()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    @discord.ui.button(label="⏮ First", style=discord.ButtonStyle.secondary)
    async def btn_first(self, interaction: discord.Interaction, _: discord.ui.Button):
        await self._flip(interaction, 0)

    @discord.ui.button(label="◀ Prev", style=discord.ButtonStyle.secondary)
    async def btn_prev(self, interaction: discord.Interaction, _: discord.ui.Button):
        await self._flip(interaction, self.page - 1)

    @discord.ui.button(label="Next ▶", style=discord.ButtonStyle.secondary)
    async def btn_next(self, interaction: discord.Interaction, _: discord.ui.Button):
        await self._flip(interaction, self.page + 1)

    @discord.ui.button(label="Last ⏭", style=discord.ButtonStyle.secondary)
    async def btn_last(self, interaction: discord.Interaction, _: discord.ui.Button):
        await self._flip(interaction, self.total_pages - 1)

    async def on_timeout(self):
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                child.disabled = True
        # Slash-invoked sends return a webhook-bound message whose .edit dies
        # with 401 once the interaction token expires (~15 min) — i.e. exactly
        # when on_timeout fires. Route the edit through the bot token via a
        # partial message instead; fall back to the direct edit for contexts
        # without a resolvable channel.
        try:
            if self.message is None:
                return
            ch = getattr(self.message, "channel", None)
            if ch is not None and hasattr(ch, "get_partial_message"):
                await ch.get_partial_message(self.message.id).edit(view=self)
            else:
                await self.message.edit(view=self)
        except Exception:
            pass


@bot.hybrid_command(name="compare",
                    description="Head-to-head between two players: record, recent games, cards picked")
@app_commands.describe(player1="First player (record shown from their perspective)",
                       player2="Second player")
async def cmd_compare(ctx, player1: discord.Member, player2: discord.Member):
    """v1.32.1 rework (Sid): head-to-head, not a rating graph — the graphs all
    moved to /graph. Shows the pair's lifetime record (server-computed H2H)
    plus their recent mutual games with the cards each player picked."""
    if player1.id == player2.id:
        await ctx.send("❌ Pick two different players.")
        return
    await _maybe_defer(ctx)
    link_a = await api_get(f"/players/by-discord/{player1.id}")
    if not link_a:
        await ctx.send(f"❌ {player1.display_name} not linked. They need `/link` first.")
        return
    link_b = await api_get(f"/players/by-discord/{player2.id}")
    if not link_b:
        await ctx.send(f"❌ {player2.display_name} not linked. They need `/link` first.")
        return
    steam_a, steam_b = link_a["steam_id"], link_b["steam_id"]
    name_a = link_a.get("display_name") or player1.display_name
    name_b = link_b.get("display_name") or player2.display_name

    # H2H orientation (verified in main.py:2529-2574): h2h_*_wins count games
    # where winner_id == the VIEWER (?viewer_steam_id). We view B's profile AS
    # A, so every h2h_*_wins below is an A win — matching the "A vs B" title.
    stats_b = await api_get(f"/players/{steam_b}?viewer_steam_id={steam_a}")
    if not stats_b:
        await ctx.send("❌ Could not fetch stats.")
        return
    rw, rl = stats_b.get("h2h_ranked_wins", 0), stats_b.get("h2h_ranked_losses", 0)
    cw, cl = stats_b.get("h2h_casual_wins", 0), stats_b.get("h2h_casual_losses", 0)
    sw, sl = stats_b.get("h2h_series_wins", 0), stats_b.get("h2h_series_losses", 0)
    tw, tl = rw + cw, rl + cl

    # A's match history, filtered to games against B. Rows are viewer(A)-
    # relative (won / player_rounds_won / cards_picked are all A's side) and
    # newest-first (ORDER BY ended_at DESC, main.py:2652).
    hist = await api_get(f"/players/{steam_a}/matches?limit=2000")
    games = [m for m in (hist or [])
             if isinstance(m, dict) and m.get("opponent_steam_id") == steam_b]

    if tw + tl == 0 and sw + sl == 0 and not games:
        await ctx.send(f"**{name_a}** and **{name_b}** haven't played each other yet.")
        return

    rec_val = (f"**{tw}W – {tl}L** for {name_a}\n"
               f"Ranked: **{rw}–{rl}**  ·  Casual: **{cw}–{cl}**\n"
               f"Completed series (BO3): **{sw}–{sl}**")

    # Lifetime top cards each picked against the other (v1.33 — server-side
    # aggregate over match_cards, so it covers games beyond the history window).
    cards_val = None
    h2h_cards = await api_get(f"/players/{steam_a}/vs/{steam_b}/top-cards?limit=6")
    if h2h_cards and (h2h_cards.get("player_cards") or h2h_cards.get("opponent_cards")):
        def _fmt_top(cl):
            return ", ".join(f"{c['card_name']} ×{c['picks']}" for c in (cl or [])[:6]) or "—"
        cards_val = (f"**{name_a[:14]}:** {_fmt_top(h2h_cards.get('player_cards'))}\n"
                     f"**{name_b[:14]}:** {_fmt_top(h2h_cards.get('opponent_cards'))}")

    if games:
        view = ComparePaginator(name_a, name_b, rec_val, cards_val, games)
        msg = await ctx.send(embed=view.build_embed(), view=view)
        view.message = msg
    else:
        # H2H counters exist but the games predate A's 2000-row history window.
        embed = discord.Embed(title=f"⚔️ {name_a} vs {name_b}", color=0xE67E22)
        embed.add_field(name="📊  Overall head-to-head", value=rec_val[:1024], inline=False)
        if cards_val:
            embed.add_field(name="🃏  Most-picked cards vs each other",
                            value=cards_val[:1024], inline=False)
        embed.add_field(name="Recent games",
                        value=f"No games between them in {name_a}'s recent history window.",
                        inline=False)
        embed.set_footer(text="Record is lifetime")
        await ctx.send(embed=embed)


@bot.hybrid_command(name="graph",
                    description="Chart a Compare-tab metric for 2-4 players (elo history, hit/block %, top cards, ...)")
@app_commands.describe(player1="First player", player2="Second player",
                       metric="Which Compare-tab metric to chart (default: elo history)",
                       player3="Optional third player", player4="Optional fourth player")
async def cmd_graph(ctx, player1: discord.Member, player2: discord.Member,
                    metric: _GraphMetric = "elo",
                    player3: discord.Member = None, player4: discord.Member = None):
    """All the in-game Compare-tab graphs as PNGs: 'elo' = the rating-history
    overlay line chart (the old /compare); everything else maps to a
    /players/{steam} stats field (see _GRAPH_BAR_METRICS) plus the two
    specials — 'top-cards' (per-player hbar) and 'region' (per-player pie)."""
    if not _MPL_AVAILABLE:
        await ctx.send("❌ Chart rendering isn't available on this bot build — redeploy with matplotlib installed.")
        return
    members, seen_ids = [], set()
    for m in (player1, player2, player3, player4):
        if m is not None and m.id not in seen_ids:
            seen_ids.add(m.id)
            members.append(m)
    if len(members) < 2:
        await ctx.send("❌ Pick at least two different players.")
        return
    await _maybe_defer(ctx)
    resolved, not_linked = [], []
    for m in members:
        link = await api_get(f"/players/by-discord/{m.id}")
        if not link:
            not_linked.append(m.display_name)
            continue
        resolved.append((m, link["steam_id"], link.get("display_name") or m.display_name))
    if not_linked:
        await ctx.send("❌ Not linked: " + ", ".join(not_linked) + ". They need `/link` first.")
        return

    # ── elo: the rating-history overlay line chart (moved from old /compare) ──
    if metric == "elo":
        players = []
        for m, sid, nm in resolved:
            hist, stats = await _fetch_rating_history(sid)
            players.append({
                "name": (stats or {}).get("display_name") or nm,
                "points": _history_to_points(hist),
                "rating": (stats or {}).get("rating"),
                "peak": (stats or {}).get("peak_rating"),
            })
        drawable = [p for p in players if len(p["points"]) >= 2]
        if not drawable:
            await ctx.send("❌ None of those players have ranked rating history to plot yet.")
            return
        buf = await asyncio.to_thread(_render_rating_history_png, drawable)
        file = discord.File(buf, filename="graph.png")
        embed = discord.Embed(title="Ranked Rating History", color=0x5865F2)
        for p in players:
            if p["rating"] is not None:
                val = f"**{p['rating']:.0f}** Elo · Peak **{(p['peak'] or p['rating']):.0f}**"
                if len(p["points"]) < 2:
                    val += " · (no history — not plotted)"
            else:
                val = "(no data)"
            embed.add_field(name=str(p["name"])[:256], value=val, inline=True)
        embed.set_image(url="attachment://graph.png")
        await ctx.send(embed=embed, file=file)
        return

    # Every other metric reads the full stats payload once per player.
    stats_list = []   # (name, stats_dict)
    fetch_failed = []
    for m, sid, nm in resolved:
        s = await api_get(f"/players/{sid}")
        if not isinstance(s, dict):
            fetch_failed.append(nm)
            s = {}
        stats_list.append((s.get("display_name") or nm, s))
    if len(fetch_failed) == len(stats_list):
        await ctx.send("❌ Could not fetch stats for any of those players.")
        return

    footnotes = []
    if fetch_failed:
        footnotes.append("stats unavailable: " + ", ".join(fetch_failed))

    # ── top-cards: per-player horizontal bars ──
    if metric == "top-cards":
        chart_players, no_cards = [], []
        for nm, s in stats_list:
            cards = [(c.get("card_name", "?"), int(c.get("times_picked") or 0),
                      float(c.get("win_rate") or 0) * 100)  # server win_rate is 0-1
                     for c in (s.get("top_cards") or []) if isinstance(c, dict)][:8]
            if cards:
                chart_players.append({"name": nm, "cards": cards})
            else:
                no_cards.append(nm)
        if not chart_players:
            await ctx.send("❌ No card data for any of those players.")
            return
        if no_cards:
            footnotes.append("no card data: " + ", ".join(no_cards))
        buf = await asyncio.to_thread(_render_top_cards_png, chart_players)
        embed = discord.Embed(title="🃏 Top Cards", color=0x5865F2)

    # ── region: per-player pie charts ──
    elif metric == "region":
        chart_players, no_regions = [], []
        for nm, s in stats_list:
            # Server field is region_breakdown = [{region, matches}]
            # (schemas.py:184); region_names/region_matches are the CLIENT's
            # parsed mirror of it, not wire fields.
            rows = sorted([r for r in (s.get("region_breakdown") or [])
                           if isinstance(r, dict) and (r.get("matches") or 0) > 0],
                          key=lambda r: r.get("matches") or 0, reverse=True)
            if not rows:
                no_regions.append(nm)
                continue
            top, rest = rows[:7], rows[7:]
            labels = [str(r.get("region", "?")) for r in top]
            values = [int(r.get("matches") or 0) for r in top]
            if rest:
                labels.append("other")
                values.append(sum(int(r.get("matches") or 0) for r in rest))
            chart_players.append({"name": nm, "labels": labels, "values": values})
        if not chart_players:
            await ctx.send("❌ No region data for any of those players.")
            return
        if no_regions:
            footnotes.append("no region data: " + ", ".join(no_regions))
        buf = await asyncio.to_thread(_render_region_pies_png, chart_players)
        embed = discord.Embed(title="🌍 Region Time", color=0x5865F2)

    # ── everything else: the generic (grouped) bar chart ──
    else:
        spec = _GRAPH_BAR_METRICS.get(metric)
        if spec is None:  # unreachable via the Literal, defensive for !prefix edge
            await ctx.send("❌ Unknown metric.")
            return
        rows = stats_list
        if metric == "2v2":
            # Players without a completed 2v2 series have team_rating 0 — omit
            # them from the chart (a 0-Elo bar reads as terrible, not absent).
            dropped = [nm for nm, s in rows if (s.get("team_rating") or 0) <= 0]
            rows = [(nm, s) for nm, s in rows if (s.get("team_rating") or 0) > 0]
            if not rows:
                await ctx.send("❌ None of those players have a 2v2 rating yet (no completed 2v2 series).")
                return
            if dropped:
                footnotes.append("no 2v2 rating (omitted): " + ", ".join(dropped))
        elif spec["need"]:
            missing = [nm for nm, s in rows
                       if not any(s.get(k) for k in spec["need"])]
            if missing:
                footnotes.append("no data recorded (shown as 0): " + ", ".join(missing))
        names = [nm for nm, _ in rows]
        groups = [(label, [fn(s) for _, s in rows]) for label, fn in spec["series"]]
        buf = await asyncio.to_thread(_render_bar_chart_png, spec["title"], names,
                                      groups, spec["ylabel"], spec["fmt"])
        embed = discord.Embed(title=f"📊 {spec['title']}", color=0x5865F2)

    file = discord.File(buf, filename="graph.png")
    embed.set_image(url="attachment://graph.png")
    if footnotes:
        embed.set_footer(text=(" • ".join(footnotes))[:2048])
    await ctx.send(embed=embed, file=file)


# ── /game — one recorded game by its short code (July 22 item 6) ─────────

def _csv_ints(s):
    out = []
    for tok in (s or "").split(","):
        try:
            v = int(tok)
            if v >= 0:
                out.append(v)
        except ValueError:
            pass
    return out


def _pair_series(s):
    """'a:b,a:b,...' cumulative pairs → ([a...], [b...]); ([], []) when absent."""
    aa, bb = [], []
    for tok in (s or "").split(","):
        if ":" not in tok:
            continue
        l, _, r = tok.partition(":")
        try:
            aa.append(int(l)); bb.append(int(r))
        except ValueError:
            pass
    return aa, bb


def _ffa_point_series(timeline, players):
    """Port of ParseFfaTimeline (plugin/NativeUI.cs) for the /game PNG.

    The FFA timeline is one comma-separated token per HALF POINT, shaped
    `slot[R][G]` — leading digits are the winning slot, an `R` means that half
    converted into a full point (which resets everyone's live halves), `G`
    means it also won the game. Score at any instant is
    `full_points + live_halves * 0.5`, exactly as the in-game hover graph
    draws it. Returns [(name, values, linestyle, palette_index), ...] with the
    palette index taken from the player's SLOT so the colour matches the
    in-game graph and the score dots.
    """
    if not timeline or not players:
        return []
    tokens = [t for t in str(timeline).split(",") if t.strip()]
    if not tokens:
        return []
    n = len(players)
    slot_to_line = {}
    for i, p in enumerate(players):
        s = p.get("slot")
        slot_to_line[i if s is None else int(s)] = i
    full = [0] * n
    live = [0] * n
    values = [[0.0] for _ in range(n)]
    events = 0
    for tok in tokens:
        # Match ParseFfaTimeline byte for byte: it skips only SPACE and TAB
        # (not \n or \r), and it accumulates only ASCII digits. `.strip()` plus
        # `str.isdigit()` would both be more permissive, so a token like
        # "\n0R" would score a point here and be discarded in-game — the two
        # graphs would disagree. Our own writer never emits whitespace, so this
        # is defensive, but the two parsers must not be allowed to drift.
        t = tok.lstrip(" \t")
        digits = ""
        for ch in t:
            if "0" <= ch <= "9":
                digits += ch
            else:
                break
        if not digits:
            continue
        line = slot_to_line.get(int(digits))
        if line is None:
            continue
        live[line] += 1
        if "R" in t[len(digits):]:
            full[line] += 1
            live = [0] * n
        events += 1
        for i in range(n):
            values[i].append(full[i] + live[i] * 0.5)
    if events == 0:
        return []
    out = []
    for i, p in enumerate(players):
        s = p.get("slot")
        out.append((str(p.get("name") or "?")[:14], values[i], "-",
                    i if s is None else int(s)))
    return out


def _render_game_detail_png_locked(game):
    """Stacked panels for whatever series the game actually recorded:
    score progression, FPS, ping, shots fired-vs-hit, dmg-vs-blocks.
    1v1 = two players; 2v2 = up to four (from telemetry_by_player fields the
    by-code endpoint flattens onto each player). Returns BytesIO or None."""
    players = game.get("players") or []
    # 10 wide because an FFA game has up to 10 series (bug #118 — the in-game
    # graph used the 4-entry vanilla skin bank and wrapped, so slot 0 and slot
    # 4 drew in the IDENTICAL colour). MUST stay in sync with
    # FFA_SLOT_PALETTE in plugin/NativeUI.cs — same order, same hexes, so the
    # Discord PNG and the in-game hover graph key a player to the same colour.
    palette = ["#FFC43D", "#4FA8FF", "#FF5C7A", "#DCE3EC", "#46E07C",
               "#C48CFF", "#26D8D2", "#FF7BE0", "#FF8A3D", "#C8FF66"]
    panels = []

    # Series tuples carry an EXPLICIT palette index (review [11]) — the color
    # is the player's position, never sniffed from the label text (a player
    # literally named "hit" must not recolor the chart).
    tl = game.get("point_timeline")
    if tl and game.get("mode") == "1v1":
        a, b = _pair_series(tl)
        if len(a) >= 2:
            n1 = players[0]["name"][:14] if players else "P1"
            n2 = players[1]["name"][:14] if len(players) > 1 else "P2"
            # Stored totals are POINTS (rounds*2+points); every in-game surface
            # shows ROUNDS, so halve (feedback item 3: "10 points" on a 5-round
            # game). Half-steps = a point inside an unfinished round.
            panels.append(("Score progression (rounds)",
                           [(n1, [v / 2.0 for v in [0] + a], "-", 0),
                            (n2, [v / 2.0 for v in [0] + b], "-", 1)], None))
    elif game.get("mode") == "ffa" and game.get("timeline"):
        ffa_series = _ffa_point_series(game["timeline"], players)
        if ffa_series:
            panels.append(("Score progression (points)", ffa_series, None))
    fps_series = [(p["name"][:14], _csv_ints(p.get("fps_timeline")), "-", pi)
                  for pi, p in enumerate(players) if _csv_ints(p.get("fps_timeline"))]
    if fps_series:
        panels.append(("FPS", fps_series, None))
    ping_series = [(p["name"][:14], _csv_ints(p.get("ping_timeline")), "-", pi)
                   for pi, p in enumerate(players) if _csv_ints(p.get("ping_timeline"))]
    if ping_series:
        panels.append(("Ping (ms)", ping_series, None))
    hit_series = []
    for pi, p in enumerate(players):
        fa, fb = _pair_series(p.get("hit_timeline"))
        if len(fa) >= 2:
            hit_series.append((f"{p['name'][:12]} fired", fa, "--", pi))
            hit_series.append((f"{p['name'][:12]} hit", fb, "-", pi))
    if hit_series:
        panels.append(("Shots fired (dashed) vs hits (solid)", hit_series, None))
    blk_series = []
    for pi, p in enumerate(players):
        ba, bb = _pair_series(p.get("block_timeline"))
        if len(ba) >= 2:
            blk_series.append((f"{p['name'][:12]} dmg", ba, "--", pi))
            blk_series.append((f"{p['name'][:12]} blocks", bb, "-", pi))
    if blk_series:
        panels.append(("Damage taken (dashed, left) vs successful blocks (solid, right)", blk_series, "dual"))

    if not panels:
        return None
    with _mpl_render_lock:
        fig, axes = plt.subplots(len(panels), 1, figsize=(10, 2.7 * len(panels)), dpi=110)
        try:
            if len(panels) == 1:
                axes = [axes]
            fig.patch.set_facecolor(_CHART_BG)
            for ax, (title, series, special) in zip(axes, panels):
                _style_axes(ax)
                ax.set_title(title, color="#ffffff", fontsize=11, pad=6, loc="left")
                ax.grid(True, axis="y", color=_CHART_GRID, linewidth=0.6, alpha=0.5)
                ax.set_axisbelow(True)
                if special == "dual":
                    ax2 = ax.twinx()
                    ax2.tick_params(colors=_CHART_MUTED, labelsize=9)
                    for spine in ax2.spines.values():
                        spine.set_color(_CHART_GRID)
                    for label, vals, style, color_idx in series:
                        col = palette[color_idx % len(palette)]
                        target = ax if style == "--" else ax2
                        target.plot(range(len(vals)), vals, style, color=col,
                                    linewidth=1.8, label=label)
                    h1, l1 = ax.get_legend_handles_labels()
                    h2, l2 = ax2.get_legend_handles_labels()
                    ax.legend(h1 + h2, l1 + l2, loc="upper left", fontsize=8,
                              facecolor=_CHART_BG, labelcolor=_CHART_FG, edgecolor=_CHART_GRID)
                else:
                    for label, vals, style, color_idx in series:
                        col = palette[color_idx % len(palette)]
                        ax.plot(range(len(vals)), vals, style, color=col,
                                linewidth=1.8, label=label)
                    ax.legend(loc="upper left", fontsize=8, facecolor=_CHART_BG,
                              labelcolor=_CHART_FG, edgecolor=_CHART_GRID)
                ax.set_xlabel("time (samples every ~3-5s)", color=_CHART_MUTED, fontsize=8)
            fig.tight_layout()
            buf = io.BytesIO()
            fig.savefig(buf, format="png", facecolor=_CHART_BG)
            buf.seek(0)
            return buf
        finally:
            plt.close(fig)


@bot.hybrid_command(name="game", description="Look up one recorded game by its ID (copy it from the F5 menu)")
@app_commands.describe(code="12-character game code — click the ID button next to any game in the F5 menu")
async def cmd_game(ctx, code: str):
    """July 22 item 6: full per-game breakdown for any recorded game — score
    history, hit/block, FPS/ping graphs, cards, rewards — for all players in
    it. Works for 1v1 (full telemetry), 2v2 (per-player telemetry rows),
    1v2 (score + cards + rewards) and FFA (placements + full telemetry)."""
    norm = "".join(c for c in (code or "").lower() if c in "0123456789abcdef")
    if len(norm) not in (12, 32):
        await ctx.send("❌ That doesn't look like a game code — copy it with the ID button next to a game in the F5 menu.")
        return
    await _maybe_defer(ctx)
    game = await api_get(f"/matches/by-code/{norm[:12]}")
    if not game:
        await ctx.send(f"❌ No game found for `{norm[:12].upper()}`.")
        return

    mode = game.get("mode", "1v1")
    label = {"1v1": "1v1 " + ("Ranked" if game.get("is_ranked") else "Casual"),
             "2v2": "2v2 Ranked", "1v2": "1v2 (unranked beta)",
             "ffa": f"FFA {'Ranked' if game.get('is_ranked') else 'Casual'} "
                    f"({game.get('player_count') or len(game.get('players') or [])} players)",
             }.get(mode, mode)
    when = (game.get("ended_at") or "")[:10]
    dur = game.get("duration_seconds") or 0
    players = game.get("players") or []

    if mode == "1v1":
        score = f"{players[0]['rounds_won']}-{players[1]['rounds_won']}" if len(players) == 2 else "?"
    elif mode == "2v2":
        score = f"{game.get('t1_rounds_won', '?')}-{game.get('t2_rounds_won', '?')}"
    elif mode == "ffa":
        # An FFA result is a placement list, not a scoreline — the per-player
        # fields below carry it. (Explicit branch so a future mode can't
        # inherit the 1v2 "solo ? - duo ?" fallback.)
        score = None
    elif mode == "1v2":
        score = f"solo {game.get('solo_rounds_won', '?')} - duo {game.get('duo_rounds_won', '?')}"
    else:
        score = None

    desc = f"**{label}** · {when}" + (f" · score **{score}**" if score else "")
    if dur:
        desc += f" · {dur // 60}:{dur % 60:02d}"
    if game.get("series_status"):
        desc += f" · series {game['series_status']}"
    if game.get("invalidated"):
        desc += f"\n⚠ invalidated: {game.get('invalidation_reason') or 'admin'}"
    embed = discord.Embed(title=f"🎮 Game {game.get('code', norm[:12].upper())}",
                          description=desc, color=0x5865F2)

    for p in players:
        won = p.get("won")
        if mode == "ffa":
            # Mirror log_ffa_match_result's rendering so the /game embed and
            # the series-log channel post describe a placement the same way.
            pl = p.get("placement") or 0
            medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(pl, f"#{pl}")
            head = f"{medal} {p['name']}"
            if p.get("left_early"):
                head += "  *(left)*"
        else:
            head = f"{'🏆 ' if won else ''}{p['name']}"
        if mode == "2v2":
            head += f"  (team {p.get('team')})"
        elif mode == "1v2":
            head += f"  ({p.get('side')})"
        lines = []
        if mode == "ffa":
            lines.append(f"{p.get('rounds_won', 0)} pts · {p.get('points_total', 0)} half-pts"
                         f" · {p.get('kills', 0)} kills")
        bf, bh = p.get("bullets_fired"), p.get("bullets_hit")
        ba, bs = p.get("blocks_activated"), p.get("blocks_successful")
        if bf or ba:
            lines.append(f"Hit {_pct(bh, bf):.0f}% ({bh or 0}/{bf or 0}) · Block {_pct(bs, ba):.0f}% ({bs or 0}/{ba or 0})")
        perf = []
        if p.get("fps_avg"):
            perf.append(f"{p['fps_avg']} fps")
        if p.get("ping_avg"):
            perf.append(f"{p['ping_avg']} ms" + (f" (max {p['ping_max']})" if p.get("ping_max") else ""))
        if perf:
            lines.append(" · ".join(perf))
        rewards = []
        if p.get("xp_gained"):
            rewards.append(f"+{p['xp_gained']} xp")
        if p.get("xp_earned"):
            rewards.append(f"+{p['xp_earned']} xp (series)")
        if p.get("gold_gained"):
            rewards.append(f"+{p['gold_gained']} g")
        if p.get("gold_earned"):
            rewards.append(f"+{p['gold_earned']} g (series)")
        rc = p.get("rating_change")
        if rc is not None:
            # FFA rates every game individually; the other modes only move
            # rating on series completion.
            rewards.append(f"{'+' if rc >= 0 else ''}{rc:.1f} elo"
                           + ("" if mode == "ffa" else " (series)"))
        if rewards:
            lines.append(" · ".join(rewards))
        cards = p.get("cards") or []
        if cards:
            cl = ", ".join(cards)
            if len(cl) > 300:
                cl = cl[:297] + "..."
            lines.append(f"Cards: {cl}")
        else:
            # Feedback item 2: absence must be legible — older games (and some
            # unmodded-opponent games) never recorded this side's picks.
            lines.append("Cards: *(not recorded for this game)*")
        embed.add_field(name=head[:256], value=("\n".join(lines) or "—")[:1024], inline=False)

    buf = None
    if _MPL_AVAILABLE:
        try:
            buf = await asyncio.to_thread(_render_game_detail_png_locked, game)
        except Exception as e:
            print(f"[GAME] graph render failed: {e}")
    if buf:
        file = discord.File(buf, filename="graph.png")
        embed.set_image(url="attachment://graph.png")
        await ctx.send(embed=embed, file=file)
    else:
        if mode != "1v1":
            embed.set_footer(text="Timeline graphs need telemetry recorded by v1.34.1+ clients in this mode.")
        await ctx.send(embed=embed)


@bot.hybrid_command(name="mystats", description="Full My Stats page — everything the F5 menu shows")
@app_commands.describe(member="Player to look up (defaults to yourself)")
async def cmd_mystats(ctx, member: discord.Member = None):
    """The F5 'My Stats' page as one embed: rating box, level/XP, all records
    + current streaks, accuracy, sweeps, best streaks, top cards, net gold,
    2v2 line. /stats stays the lean general view; this is the full dump."""
    target = member or ctx.author
    link = await api_get(f"/players/by-discord/{target.id}")
    if not link:
        await ctx.send("❌ Not linked. Use `/link` first." if target == ctx.author else f"❌ {target.display_name} not linked."); return
    steam_id = link["steam_id"]
    await _maybe_defer(ctx)
    s = await api_get(f"/players/{steam_id}")
    if not s: await ctx.send("❌ Could not fetch stats."); return
    hist = await api_get(f"/players/{steam_id}/matches?limit=50")
    rank = s.get("rank_name") or get_rank_name(s["rating"])
    embed = discord.Embed(title=f"{rank_emoji(rank)}  {s['display_name']}  —  My Stats", color=0x9B59B6)
    # v1.34.1: surface the Discord @display name (opt-out honored — the API
    # nulls discord_display_name when show_discord is off). No real mention.
    _dname = s.get("discord_display_name")
    if _dname:
        embed.description = f"Discord: **@{discord.utils.escape_markdown(str(_dname))}**"
    embed.set_thumbnail(url=target.display_avatar.url)

    # Rating box
    peak = s.get("peak_rating", s["rating"])
    embed.add_field(
        name="📊  Rating",
        value=(f"**{s['rating']:.0f}** Elo  ·  Peak: **{peak:.0f}**  ·  RD: {s['rating_deviation']:.0f}\n"
               f"Rank: **{rank}**"),
        inline=False,
    )

    # Level / XP box
    embed.add_field(
        name="⭐  Level",
        value=(f"**{s.get('level', 0)}**  ·  {s.get('total_xp', 0):,} XP total\n"
               f"{s.get('xp_into_level', 0):,} / {s.get('xp_for_next_level', 0):,} into next level"),
        inline=False,
    )

    # Records box — total + ranked + casual, with live streaks from history.
    tw, tl, tt = s.get("wins", 0), s.get("losses", 0), s.get("total_matches", 0)
    twr = f"{tw/tt*100:.1f}%" if tt > 0 else "—"
    rw, rl = s.get("ranked_series_wins", 0), s.get("ranked_series_losses", 0)
    rt = rw + rl
    rwr = f"{rw/rt*100:.1f}%" if rt > 0 else "—"
    cw, cl = s.get("casual_wins", 0), s.get("casual_losses", 0)
    ct = cw + cl
    cwr = f"{cw/ct*100:.1f}%" if ct > 0 else "—"
    r_streak = streak_str(_calc_streak(hist, ranked=True))
    c_streak = streak_str(_calc_streak(hist, ranked=False))
    rec_lines = [
        f"Total: **{tt}** — **{tw}**W / **{tl}**L ({twr})",
        f"Ranked series: **{rw}**W / **{rl}**L ({rwr})" + (f"  ·  {r_streak}" if r_streak else ""),
        f"Casual: **{cw}**W / **{cl}**L ({cwr})" + (f"  ·  {c_streak}" if c_streak else ""),
    ]
    embed.add_field(name="⚔️  Records", value="\n".join(rec_lines), inline=False)

    # Accuracy
    acc = _hit_block_str(s)
    if acc:
        embed.add_field(name="🎯  Accuracy", value=acc, inline=True)

    # Sweeps
    sg, st_ = s.get("sweeps_given", 0), s.get("sweeps_taken", 0)
    embed.add_field(name="💨  Sweeps", value=f"5-0 Given: **{sg}** 🧹  ·  0-5 Taken: **{st_}**", inline=True)

    # Best streaks
    br, bcs = s.get("best_ranked_streak", 0), s.get("best_casual_streak", 0)
    streaks = []
    if br > 0: streaks.append(f"Ranked: **{br}W** 🔥")
    if bcs > 0: streaks.append(f"Casual: **{bcs}W**")
    if streaks:
        embed.add_field(name="📈  Best Streaks", value="  ·  ".join(streaks), inline=True)

    # Net gold — respect hide_gold.
    if not s.get("hide_gold"):
        net_gold = (s.get("gold_earned", 0) or 0) - (s.get("gold_spent", 0) or 0)
        embed.add_field(name="💰  Net Gold", value=f"**{net_gold:,}**g", inline=True)

    # 2v2 line
    if (s.get("team_rating") or 0) > 0:
        team = await api_get(f"/team/players/{steam_id}/team-stats")
        if team and (team.get("rating") or 0) > 0:
            t_streak = streak_str(team.get("current_streak", 0))
            embed.add_field(
                name="👥  2v2",
                value=(f"**{team['rating']:.0f}**  ·  {team.get('series_wins', 0)}W / "
                       f"{team.get('series_losses', 0)}L series"
                       + (f"  ·  {t_streak}" if t_streak else "")),
                inline=True,
            )

    # Top cards
    cards_lines = _top_cards_lines(s, limit=5)
    if cards_lines:
        embed.add_field(name="🃏  Top Cards", value="\n".join(cards_lines), inline=False)

    embed.set_footer(text=f"Steam: {s['steam_id']}")
    await ctx.send(embed=embed)


@bot.hybrid_command(name="cards", description="Card stats — a player's (with member) or community-wide")
@app_commands.describe(member="Player to look up (omit for community-wide stats)",
                       filter="Which matches to count (default: all)")
async def cmd_cards(ctx, member: discord.Member = None,
                    filter: Literal["ranked", "casual", "all"] = "all"):
    """Mirror of the in-game Card Stats tab (GET /api/v1/cards). With a member
    the table is that player's picks; without one it's community-wide (the
    tab itself always passes the local steam_id — the community view is
    bot-only)."""
    q = "/cards?limit=15&sort_by=times_picked&min_picks=1"
    scope = "Community"
    if member is not None:
        link = await api_get(f"/players/by-discord/{member.id}")
        if not link:
            await ctx.send(f"❌ {member.display_name} not linked.")
            return
        q += f"&steam_id={link['steam_id']}"
        scope = member.display_name
    if filter in ("ranked", "casual"):
        q += f"&is_ranked={'true' if filter == 'ranked' else 'false'}"
    await _maybe_defer(ctx)
    data = await api_get(q)
    if not isinstance(data, list) or not data:
        await ctx.send("❌ No card data for that selection.")
        return
    lines = []
    for c in data:
        if not isinstance(c, dict):
            continue
        wr = float(c.get("win_rate") or 0) * 100  # server win_rate is 0-1
        ln = f"**{c.get('card_name', '?')}** — {c.get('times_picked', 0)} picks · {wr:.0f}% WR"
        if (c.get("times_offered") or 0) > 0:
            ln += f" · {float(c.get('pass_rate') or 0) * 100:.0f}% passed"
        lines.append(ln)
    embed = discord.Embed(
        title=f"🃏 Card Stats — {scope} ({filter})",
        description="\n".join(lines)[:4000],
        color=discord.Color.teal(),
    )
    embed.set_footer(text="picks = times taken • WR = win rate of matches where it was picked • passed = offered but skipped")
    await ctx.send(embed=embed)

# ── Queue Beacon (15s) ───────────────────────────────────────────
seen_queue_joins = {}  # steam_id -> timestamp


def _beacon_discord_suffix(j):
    """v1.34.1: append the searcher's Discord @display name to a queue beacon
    so people know who to @ — PLAIN TEXT only (not a <@id> mention), and every
    beacon send already passes allowed_mentions=none, so this can never ping
    (Sid's ask: name yes, ping no). Empty when the player opted out or isn't
    linked (the API nulls discord_display_name via the show_discord gate)."""
    dname = (j or {}).get("discord_display_name")
    if not dname:
        return ""
    return f"  ·  Discord: @{discord.utils.escape_markdown(str(dname))}"


@tasks.loop(seconds=15)
async def poll_queue_beacon():
    if not QUEUE_BEACON_CHANNEL_ID:
        return
    try:
        # Expire entries older than 5 minutes
        now = datetime.utcnow()
        expired = [k for k, v in seen_queue_joins.items() if (now - v).total_seconds() > 300]
        for k in expired:
            del seen_queue_joins[k]

        data = await api_get("/queue/recent-joins?seconds=20")
        if not data or not data.get("joins"):
            return
        for j in data["joins"]:
            sid = j["steam_id"]
            if sid in seen_queue_joins:
                continue
            seen_queue_joins[sid] = now

            name = j["display_name"] or sid
            rating = j.get("rating", 1500)

            channel = bot.get_channel(QUEUE_BEACON_CHANNEL_ID)
            if not channel:
                try:
                    channel = await bot.fetch_channel(QUEUE_BEACON_CHANNEL_ID)
                except:
                    continue

            await channel.send(
                f"🔍 **{discord.utils.escape_markdown(str(name))}** ({rating}) is searching for a ranked match!"
                + _beacon_discord_suffix(j),
                allowed_mentions=discord.AllowedMentions.none(),
            )
    except Exception as e:
        print(f"Queue beacon error: {e}")


# ── 2v2 Queue Beacon ─────────────────────────────────────────────
# Posts in the same channel as the 1v1 beacon. Different emoji + " for 2v2!"
# wording so it's distinguishable in a glance. Includes the running queue size
# (X/4) so people can see if joining now will fill the lobby.
seen_team_queue_joins = {}  # steam_id -> timestamp

@tasks.loop(seconds=15)
async def poll_team_queue_beacon():
    if not QUEUE_BEACON_CHANNEL_ID:
        return
    try:
        now = datetime.utcnow()
        expired = [k for k, v in seen_team_queue_joins.items() if (now - v).total_seconds() > 300]
        for k in expired:
            del seen_team_queue_joins[k]

        data = await api_get("/team/queue/recent-joins?seconds=20")
        if not data or not data.get("joins"):
            return
        qsize = data.get("queue_size", 0)
        for j in data["joins"]:
            sid = j["steam_id"]
            if sid in seen_team_queue_joins:
                continue
            seen_team_queue_joins[sid] = now
            name = j["display_name"] or sid
            rating = j.get("rating", 1500)
            channel = bot.get_channel(QUEUE_BEACON_CHANNEL_ID)
            if not channel:
                try:
                    channel = await bot.fetch_channel(QUEUE_BEACON_CHANNEL_ID)
                except:
                    continue
            await channel.send(
                f"🎯 **{discord.utils.escape_markdown(str(name))}** ({rating}) is searching for **2v2** — **{qsize}/4** queued!"
                + _beacon_discord_suffix(j),
                allowed_mentions=discord.AllowedMentions.none(),
            )
    except Exception as e:
        print(f"Team queue beacon error: {e}")


# ── 1v2 Queue Beacon ─────────────────────────────────────────────
# Same channel as the 1v1/2v2 beacons; distinct emoji + "for 1v2" wording.
# Own fully-guarded loop (learning #129 — never chain outputs onto another
# loop's tail). Shows the live lobby fill (X/3) so people can see whether
# joining now completes the trio.
seen_ovt_queue_joins = {}  # steam_id -> timestamp

@tasks.loop(seconds=15)
async def poll_ovt_queue_beacon():
    if not QUEUE_BEACON_CHANNEL_ID:
        return
    try:
        now = datetime.utcnow()
        expired = [k for k, v in seen_ovt_queue_joins.items() if (now - v).total_seconds() > 300]
        for k in expired:
            del seen_ovt_queue_joins[k]

        data = await api_get("/ovt/queue/recent-joins?seconds=20")
        if not data or not data.get("joins"):
            return
        qsize = data.get("queue_size", 0)
        for j in data["joins"]:
            sid = j["steam_id"]
            if sid in seen_ovt_queue_joins:
                continue
            seen_ovt_queue_joins[sid] = now
            name = j["display_name"] or sid
            rating = j.get("rating", 1500)
            channel = bot.get_channel(QUEUE_BEACON_CHANNEL_ID)
            if not channel:
                try:
                    channel = await bot.fetch_channel(QUEUE_BEACON_CHANNEL_ID)
                except:
                    continue
            await channel.send(
                f"⚔️ **{discord.utils.escape_markdown(str(name))}** ({rating}) is searching for **1v2** — **{qsize}/3** in the lobby!"
                + _beacon_discord_suffix(j),
                allowed_mentions=discord.AllowedMentions.none(),
            )
    except Exception as e:
        print(f"1v2 queue beacon error: {e}")


# ── FFA queue beacon + result posting (Sid round-2 item 4: FFA had no bot
# coverage at all). Same shapes as the 1v2 beacon and the 2v2 series log. ──
seen_ffa_queue_joins = {}  # steam_id -> timestamp

@tasks.loop(seconds=15)
async def poll_ffa_queue_beacon():
    if not QUEUE_BEACON_CHANNEL_ID:
        return
    try:
        now = datetime.utcnow()
        expired = [k for k, v in seen_ffa_queue_joins.items() if (now - v).total_seconds() > 300]
        for k in expired:
            del seen_ffa_queue_joins[k]

        data = await api_get("/ffa/queue/recent-joins?seconds=20")
        if not data or not data.get("joins"):
            return
        qsize = data.get("queue_size", 0)
        for j in data["joins"]:
            sid = j["steam_id"]
            if sid in seen_ffa_queue_joins:
                continue
            name = j["display_name"] or sid
            rating = j.get("rating", 1500)
            channel = bot.get_channel(QUEUE_BEACON_CHANNEL_ID)
            if not channel:
                try:
                    channel = await bot.fetch_channel(QUEUE_BEACON_CHANNEL_ID)
                except:
                    continue
            await channel.send(
                f"🎯 **{discord.utils.escape_markdown(str(name))}** ({rating}) is searching for **FFA** — "
                f"**{qsize}** in the queue (starts at 3, up to 10)!"
                + _beacon_discord_suffix(j),
                allowed_mentions=discord.AllowedMentions.none(),
            )
            # Marked seen only AFTER a successful send (round-2 review find
            # 17): a transient Discord error must retry on the next poll.
            seen_ffa_queue_joins[sid] = now
    except Exception as e:
        print(f"FFA queue beacon error: {e}")


seen_ffa_matches = set()

@tasks.loop(seconds=30)
async def poll_ffa_recent_matches():
    """Posts an embed in SERIES_LOG_CHANNEL for each completed ranked FFA.
    In-memory de-dupe via seen_ffa_matches, pre-loaded in before_loop so a
    restart doesn't spam history (same pattern as the 2v2 series log)."""
    try:
        data = await api_get("/ffa/recent?page=0&page_size=5")
        if not data or not data.get("matches"):
            return
        for m in data["matches"]:
            mid = m["match_id"]
            if mid in seen_ffa_matches:
                continue
            posted_any = False
            failed_any = False
            for guild in bot.guilds:
                try:
                    await log_ffa_match_result(guild, m)
                    posted_any = True
                except Exception as e:
                    failed_any = True
                    print(f"FFA match log error: {e}")
            # Round-2 review find 17: only mark seen once delivery succeeded
            # somewhere (a transient error retries next poll). Find 18: on
            # overflow, rebuild the set from the current page instead of
            # clearing (a bare clear immediately reposted the other four).
            if posted_any and not failed_any:
                seen_ffa_matches.add(mid)
                if len(seen_ffa_matches) > 500:
                    seen_ffa_matches.clear()
                    for m2 in data["matches"]:
                        seen_ffa_matches.add(m2["match_id"])
    except Exception as ex:
        print(f"poll_ffa_recent_matches error: {ex}")


@poll_ffa_recent_matches.before_loop
async def before_ffa_matches_poll():
    await bot.wait_until_ready()
    data = await api_get("/ffa/recent?page=0&page_size=10")
    if data and data.get("matches"):
        for m in data["matches"]:
            seen_ffa_matches.add(m["match_id"])
    print(f"Pre-loaded {len(seen_ffa_matches)} recent FFA matches")


async def log_ffa_match_result(guild, m):
    if SERIES_LOG_CHANNEL_ID <= 0:
        return
    ch = guild.get_channel(SERIES_LOG_CHANNEL_ID)
    if not ch:
        return
    players = m.get("players") or []
    n = m.get("player_count", len(players))
    dur = m.get("duration_seconds") or 0
    lines = []
    for p in sorted(players, key=lambda q: q.get("placement", 99)):
        rc = p.get("rating_change")
        rc_s = "" if rc is None else (f" (+{rc:.1f})" if rc > 0 else f" ({rc:.1f})")
        left = " *(left)*" if p.get("left_early") else ""
        medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(p.get("placement", 0), f"#{p.get('placement', '?')}")
        nm = discord.utils.escape_markdown(str(p.get("display_name") or p.get("steam_id")))
        lines.append(f"{medal} **{nm}** — {p.get('rounds_won', 0)}pt "
                     f"{p.get('kills', 0)}k{rc_s}{left}")
    embed = discord.Embed(title=f"🎯 Ranked FFA Complete — {n} players",
                          color=discord.Color.purple())
    embed.description = "\n".join(lines[:12]) or "(no players?)"
    if dur:
        embed.set_footer(text=f"{dur // 60}m{dur % 60:02d}s")
    try:
        if m.get("ended_at"):
            embed.timestamp = datetime.fromisoformat(m["ended_at"].replace("Z", "+00:00"))
    except Exception:
        pass
    await ch.send(embed=embed)


# ── Bug Report Posting ────────────────────────────────────────────
# Polls /bug-reports/recent every 30s, posts new ones to BUG_REPORTS_CHANNEL.
# Only metadata + description — no log content and no triage comments (per
# Sid: keep the public-ish channel free of attached game logs).
#
# v1.29 (#30/#38): ack-based delivery. The API returns reports whose
# channel_posted_at is NULL; after a successful post we ack. A bot restart
# mid-window can no longer swallow a report. Each report also gets its own
# THREAD under the feed message — comments/status changes are posted into
# the thread, which gives the "organized bug category" Sid asked for.
seen_bug_reports = set()


async def _bug_thread_for(channel, bug_num: int):
    """Find the existing thread for bug #N in the feed channel (active or
    archived). Returns None when there isn't one."""
    prefix = f"#{bug_num} "
    try:
        for th in channel.threads:
            if th.name.startswith(prefix) or th.name == f"#{bug_num}":
                return th
        async for th in channel.archived_threads(limit=100):
            if th.name.startswith(prefix) or th.name == f"#{bug_num}":
                return th
    except Exception as ex:
        print(f"[BUG-THREAD] lookup for #{bug_num} failed: {ex}")
    return None


@tasks.loop(seconds=30)
async def poll_bug_reports():
    if not BUG_REPORTS_CHANNEL_ID:
        return
    try:
        data = await api_get("/bug-reports/recent?unposted=true")
        if not data or not data.get("reports"):
            return
        channel = bot.get_channel(BUG_REPORTS_CHANNEL_ID)
        if not channel:
            try:
                channel = await bot.fetch_channel(BUG_REPORTS_CHANNEL_ID)
            except Exception as ex:
                print(f"[BUG-REPORT-POST] channel fetch failed: {ex}")
                return
        for r in data["reports"]:
            rid = r.get("id")
            if not rid or rid in seen_bug_reports:
                continue
            seen_bug_reports.add(rid)
            if len(seen_bug_reports) > 1000:
                seen_bug_reports.clear()
            sev = (r.get("severity") or "medium").lower()
            cat = (r.get("category") or "other").lower()
            sev_color = {
                "crash":  0xCC2222,
                "high":   0xCC7733,
                "medium": 0xCCAA33,
                "low":    0x6688AA,
            }.get(sev, 0xCCAA33)
            bug_num = r.get("bug_number") or 0
            who = r.get("display_name") or r.get("steam_id") or "Unknown"
            mod = r.get("mod_version") or "?"
            desc = (r.get("description") or "").strip()
            if len(desc) > 1500:
                desc = desc[:1500] + "... (truncated — full text in F5 admin viewer)"
            embed = discord.Embed(
                title=f"#{bug_num} — [{sev.upper()} / {cat.upper()}]",
                description=desc or "(no description)",
                color=sev_color,
            )
            embed.add_field(name="Reporter", value=f"`{who}` (mod v{mod})", inline=False)
            embed.set_footer(text=f"Triage in-game (F5 -> Admin -> Bug Reports) or quote as #{bug_num}.")
            try:
                msg = await channel.send(embed=embed)
                # One thread per bug — replies/status changes land in it.
                try:
                    await msg.create_thread(
                        name=f"#{bug_num} {who[:40]} — {cat}"[:100],
                        auto_archive_duration=10080,  # 7 days
                    )
                except Exception as tex:
                    print(f"[BUG-THREAD] create for #{bug_num} failed: {tex}")
                # Ack only after the channel post succeeded.
                await api_post(f"/internal/bug-reports/{rid}/channel-posted")
            except Exception as ex:
                print(f"[BUG-REPORT-POST] send failed for #{bug_num}: {ex}")
    except Exception as e:
        print(f"Bug-report post error: {e}")


# ── Bug Report Event DMs ──────────────────────────────────────────
# DMs the bug-report's REPORTER when a status change or comment lands on
# their report, provided their Discord is linked. Skips:
#   - 'created' events (they just submitted; no useful DM)
#   - events where actor_steam_id == reporter_steam_id (don't DM yourself)
#   - reporters with no discord_id linked (can't DM)
#
# v1.29 (#38): ack-based delivery — the API serves events whose notified_at
# is NULL; we ack each one after handling it (DM sent, posted to the bug's
# thread, or permanently undeliverable). Previously a 90s rolling window +
# in-memory dedup dropped every event that landed while the bot was
# restarting/deploying — which is exactly when comment sweeps happen.
seen_bug_events = set()


async def _ack_bug_events(event_ids):
    if not event_ids or http_session is None or not API_SECRET_KEY:
        return
    try:
        async with http_session.post(
            f"{API_BASE_URL}/api/v1/internal/bug-reports/events/ack",
            json={"event_ids": list(event_ids)},
            headers={"X-Internal-Key": API_SECRET_KEY},
            timeout=aiohttp.ClientTimeout(total=8),
        ) as resp:
            if resp.status != 200:
                print(f"[BUG-DM] ack failed: {resp.status} {(await resp.text())[:120]}")
    except Exception as ex:
        print(f"[BUG-DM] ack error: {ex}")


@tasks.loop(seconds=30)
async def poll_bug_report_events():
    try:
        data = await api_get("/bug-reports/events/recent?unnotified=true")
        if not data or not data.get("events"):
            return
        to_ack = []
        for e in data["events"]:
            eid = e.get("event_id")
            if not eid:
                continue
            if eid in seen_bug_events:
                # Already handled this process-lifetime — the earlier ack must
                # have failed (or raced); just re-ack, don't re-send.
                to_ack.append(eid)
                continue

            etype = e.get("event_type")
            bug_num = e.get("bug_number") or 0
            # Mirror comments + status changes into the bug's feed-channel
            # thread (v1.29, #30) regardless of DM deliverability.
            if etype in ("comment", "status_change"):
                try:
                    await _post_bug_event_to_thread(e)
                except Exception as tex:
                    print(f"[BUG-THREAD] event post for #{bug_num} failed: {tex}")

            reporter_discord = e.get("reporter_discord_id")
            if not reporter_discord:
                # Nothing to DM — reporter unlinked. Delivered as far as
                # possible; ack so it stops coming back.
                seen_bug_events.add(eid)
                to_ack.append(eid)
                continue
            reporter_steam = e.get("reporter_steam_id")
            # Don't DM someone about their OWN action (their own comment or
            # status change) — but DO send the 'created' confirmation, which
            # carries the how-to-reply hint.
            if etype != "created" and e.get("actor_steam_id") and reporter_steam and \
               e["actor_steam_id"] == reporter_steam:
                seen_bug_events.add(eid)
                to_ack.append(eid)
                continue  # self-attributed; no point pinging yourself

            # Resolve the Discord user. fetch_user falls back to a REST call
            # if the user isn't in any shared guild cache. Transient failure →
            # DON'T ack; the next poll retries.
            try:
                user = bot.get_user(int(reporter_discord))
                if not user:
                    user = await bot.fetch_user(int(reporter_discord))
            except discord.NotFound:
                seen_bug_events.add(eid)
                to_ack.append(eid)
                continue
            except Exception as ex:
                print(f"[BUG-DM] fetch_user({reporter_discord}) failed: {ex}")
                continue
            if not user:
                continue

            bug_num = e.get("bug_number") or 0
            actor = e.get("actor_name") or "Someone"
            snippet = (e.get("description_snippet") or "").strip()
            if len(snippet) > 100:
                snippet = snippet[:100] + "..."
            if etype == "created":
                embed = discord.Embed(
                    title=f"✅ Bug report #{bug_num} received",
                    description=("Thanks — the team can see it now. I'll DM you "
                                 "here when there's a reply or a status change."),
                    color=0x44CC44,
                )
                if snippet:
                    embed.add_field(name="Your report", value=snippet, inline=False)
            elif etype == "status_change":
                old_s = (e.get("old_status") or "?").upper()
                new_s = (e.get("new_status") or "?").upper()
                # Color-code by destination status.
                status_color = {
                    "RESOLVED": 0x44CC44,
                    "TRIAGED":  0xCCAA33,
                    "WONTFIX":  0x888888,
                    "DUPE":     0x888888,
                    "OPEN":     0xCC6688,
                }.get(new_s, 0x6688AA)
                embed = discord.Embed(
                    title=f"Bug report #{bug_num} — status change",
                    description=(f"**{actor}** moved your report from "
                                 f"**{old_s}** → **{new_s}**."),
                    color=status_color,
                )
                if snippet:
                    embed.add_field(name="Your report", value=snippet, inline=False)
                if e.get("comment"):
                    embed.add_field(name="Note from " + actor, value=e["comment"][:1024], inline=False)
            elif etype == "comment":
                comment_text = (e.get("comment") or "").strip()
                if not comment_text:
                    continue  # nothing to relay
                embed = discord.Embed(
                    title=f"Bug report #{bug_num} — new comment",
                    description=f"**{actor}** commented on your report.",
                    color=0x6688CC,
                )
                if snippet:
                    embed.add_field(name="Your report", value=snippet, inline=False)
                embed.add_field(name=f"{actor} says", value=comment_text[:1024], inline=False)
            else:
                # Unknown event type — nothing to send; ack so it doesn't loop.
                seen_bug_events.add(eid)
                to_ack.append(eid)
                continue

            embed.add_field(
                name="Reply",
                value=f"DM me `#{bug_num} your message` to add to this report.",
                inline=False,
            )
            embed.set_footer(text=f"Or open the F5 menu in-game and look up #{bug_num} for the full thread.")
            try:
                await user.send(embed=embed)
                print(f"[BUG-DM] #{bug_num} → {user} ({reporter_discord}): {etype}")
                seen_bug_events.add(eid)
                to_ack.append(eid)
            except discord.Forbidden:
                # DMs closed — permanently undeliverable; ack.
                print(f"[BUG-DM] #{bug_num} → {reporter_discord} forbidden (DMs closed)")
                seen_bug_events.add(eid)
                to_ack.append(eid)
            except Exception as ex:
                # Transient (rate limit / gateway blip) — no ack, retried next poll.
                print(f"[BUG-DM] #{bug_num} → {reporter_discord} failed: {ex}")
        if len(seen_bug_events) > 2000:
            seen_bug_events.clear()
        await _ack_bug_events(to_ack)
    except Exception as ex:
        print(f"poll_bug_report_events error: {ex}")


async def _post_bug_event_to_thread(e):
    """Mirror a comment / status change into the bug's feed-channel thread."""
    if not BUG_REPORTS_CHANNEL_ID:
        return
    channel = bot.get_channel(BUG_REPORTS_CHANNEL_ID)
    if channel is None:
        return
    bug_num = e.get("bug_number") or 0
    thread = await _bug_thread_for(channel, bug_num)
    if thread is None:
        return
    actor = e.get("actor_name") or "Someone"
    if e.get("event_type") == "status_change":
        new_s = (e.get("new_status") or "?").upper()
        text_out = f"**{actor}** → **{new_s}**"
        if e.get("comment"):
            text_out += f"\n{e['comment'][:1500]}"
    else:
        text_out = f"**{actor}:** {(e.get('comment') or '')[:1800]}"
    try:
        if getattr(thread, "archived", False):
            await thread.edit(archived=False)
        await thread.send(text_out)
    except Exception as ex:
        print(f"[BUG-THREAD] send to #{bug_num} thread failed: {ex}")


# ── 2v2 Series Result Posting ─────────────────────────────────────
seen_team_series = set()

@tasks.loop(seconds=30)
async def poll_team_recent_series():
    """Posts an embed in SERIES_LOG_CHANNEL when a 2v2 BO3 series completes.
    Mirrors the 1v1 series log path. De-dupes via in-memory seen_team_series
    set; capped at 500 entries (older ones aren't relevant after 24h)."""
    try:
        data = await api_get("/team/series/recent?minutes=2")
        if not data or not data.get("series"):
            return
        for s in data["series"]:
            sid = s["series_id"]
            if sid in seen_team_series:
                continue
            seen_team_series.add(sid)
            if len(seen_team_series) > 500:
                seen_team_series.clear()
            for guild in bot.guilds:
                try:
                    await log_team_series_result(guild, s)
                except Exception as e:
                    print(f"Team series log error: {e}")
    except Exception as e:
        print(f"poll_team_recent_series error: {e}")


@poll_team_recent_series.before_loop
async def before_team_series_poll():
    await bot.wait_until_ready()
    data = await api_get("/team/series/recent?minutes=10")
    if data and data.get("series"):
        for s in data["series"]:
            seen_team_series.add(s["series_id"])
    print(f"Pre-loaded {len(seen_team_series)} recent 2v2 series")


async def log_team_series_result(guild, s):
    if SERIES_LOG_CHANNEL_ID <= 0:
        return
    ch = guild.get_channel(SERIES_LOG_CHANNEL_ID)
    if not ch:
        return

    winner = s["winner_team"]
    if winner == 1:
        winners = (s["t1a"], s["t1b"]); losers = (s["t2a"], s["t2b"])
        score = f"{s['t1_series_wins']}-{s['t2_series_wins']}"
    else:
        winners = (s["t2a"], s["t2b"]); losers = (s["t1a"], s["t1b"])
        score = f"{s['t2_series_wins']}-{s['t1_series_wins']}"

    def fmt_player(p):
        rc = p.get("rating_change", 0) or 0
        # 1 decimal — sub-1.0 changes were rounding to "0" (same as bug #18, 1v1 side).
        rc_s = f"+{rc:.1f}" if rc > 0 else f"{rc:.1f}"
        return f"**{p['name']}** {p['rating']:.0f} ({rc_s})"

    embed = discord.Embed(title="⚔️ 2v2 Series Complete", color=discord.Color.gold())
    embed.description = (
        f"👑 **{winners[0]['name']} + {winners[1]['name']}** "
        f"def. **{losers[0]['name']} + {losers[1]['name']}** "
        f"`{score}`"
    )
    embed.add_field(name="Winners",
                    value=f"{fmt_player(winners[0])}\n{fmt_player(winners[1])}",
                    inline=True)
    embed.add_field(name="Losers",
                    value=f"{fmt_player(losers[0])}\n{fmt_player(losers[1])}",
                    inline=True)
    try:
        if s.get("completed_at"):
            embed.timestamp = datetime.fromisoformat(s["completed_at"].replace("Z", "+00:00"))
    except Exception:
        pass
    await ch.send(embed=embed)

# ── Series Polling (30s) ─────────────────────────────────────────

@tasks.loop(seconds=30)
async def poll_recent_series():
    data = await api_get("/series/recent?minutes=2")
    if not data or not data.get("series"): return
    for s in data["series"]:
        sid = s["series_id"]
        if sid in seen_series: continue
        seen_series.add(sid)
        if len(seen_series) > 500: seen_series.clear()
        for guild in bot.guilds:
            try: await log_series_result(guild, s)
            except Exception as e: print(f"Series log error: {e}")
            try: await update_series_roles(guild, s)
            except Exception as e: print(f"Series role error: {e}")
        # Item 9 (Sid 07-11): after a series completes, tell the gambler
        # channel who bet on it and how it went. /series/recent already
        # carries the settled (non-refunded) bets per series.
        try: await post_bet_outcomes(s)
        except Exception as e: print(f"Bet outcome post error: {e}")

@poll_recent_series.before_loop
async def before_poll():
    await bot.wait_until_ready()
    data = await api_get("/series/recent?minutes=5")
    if data and data.get("series"):
        for s in data["series"]: seen_series.add(s["series_id"])
    print(f"Pre-loaded {len(seen_series)} recent series")

async def post_bet_outcomes(s):
    """Post settled bet outcomes for a completed series to the gambler channel
    (same channel the live-bet buttons live in). Mirrors the in-game Recent
    Ranked Series bet rows. Skips series nobody bet on."""
    bets = s.get("bets") or []
    if not bets or LIVE_BETS_CHANNEL_ID <= 0:
        return
    ch = bot.get_channel(LIVE_BETS_CHANNEL_ID)
    if ch is None:
        return
    p1_won = s["winner_steam_id"] == s["p1_steam_id"]
    score = f"{s['p1_series_wins']}-{s['p2_series_wins']}" if p1_won else f"{s['p2_series_wins']}-{s['p1_series_wins']}"
    lines = []
    for b in bets:
        if b.get("won"):
            profit = (b.get("payout") or 0) - b["amount"]
            lines.append(f"🟢 **{b['bettor_name']}** bet {b['amount']:,}g on **{b['bet_on_name']}** → won **+{profit:,}g** (x{b.get('odds_multiplier', 1.0)})")
        else:
            lines.append(f"🔴 **{b['bettor_name']}** bet {b['amount']:,}g on **{b['bet_on_name']}** → lost")
    em = discord.Embed(
        title=f"💰 Bets settled: {s['winner_name']} wins {score} vs {s['p2_name'] if p1_won else s['p1_name']}",
        description="\n".join(lines[:15]),
        color=0x33AA55,
    )
    em.set_footer(text=f"series {s['series_id'][:8]}")
    await ch.send(embed=em)


async def log_series_result(guild, s):
    if SERIES_LOG_CHANNEL_ID <= 0: return
    ch = guild.get_channel(SERIES_LOG_CHANNEL_ID)
    if not ch: return
    p1_won = s["winner_steam_id"] == s["p1_steam_id"]
    score = f"{s['p1_series_wins']}-{s['p2_series_wins']}" if p1_won else f"{s['p2_series_wins']}-{s['p1_series_wins']}"
    embed = discord.Embed(title="⚔️ Ranked Series Complete", color=discord.Color.green())
    embed.description = f"**{s['winner_name']}** wins {score}!"
    # 1 decimal: Glicko changes for converged players are routinely sub-1.0, and :.0f
    # rounded a real +0.4 win to "0" — the series log read as "no rating change" for a
    # ranked win (bug #18). One decimal shows the actual movement.
    rc1 = s["p1_rating_change"]; rc1s = f"+{rc1:.1f}" if rc1 > 0 else f"{rc1:.1f}"
    rc2 = s["p2_rating_change"]; rc2s = f"+{rc2:.1f}" if rc2 > 0 else f"{rc2:.1f}"
    r1, r2 = get_rank_name(s["p1_rating"]), get_rank_name(s["p2_rating"])
    s1, s2 = streak_str(s.get("p1_streak",0)), streak_str(s.get("p2_streak",0))
    embed.add_field(name=f"{rank_emoji(r1)} {s['p1_name']}" + (" 👑" if p1_won else ""),
                    value=f"**{s['p1_rating']:.0f}** ({rc1s}) — {r1}\n{s1}", inline=True)
    embed.add_field(name=f"{rank_emoji(r2)} {s['p2_name']}" + (" 👑" if not p1_won else ""),
                    value=f"**{s['p2_rating']:.0f}** ({rc2s}) — {r2}\n{s2}", inline=True)
    try:
        dt = datetime.fromisoformat(s["completed_at"].replace("Z", "+00:00"))
        embed.timestamp = dt
    except: pass
    await ch.send(embed=embed)

async def update_series_roles(guild, s):
    for pfx in ["p1", "p2"]:
        did, rat = s.get(f"{pfx}_discord_id"), s.get(f"{pfx}_rating")
        if not did or not rat: continue
        m = await find_member(guild, did)
        if not m: continue
        try: await update_member_role(m, rat)
        except Exception as e: print(f"Role error: {e}")

# ── Periodic Full Sync (30 min backup) ───────────────────────────

@tasks.loop(minutes=30)
async def sync_roles_periodic():
    """Rank-role sync. Item 8 rework (Sid 07-11): the old loop made one
    /players/by-discord API call PER GUILD MEMBER with a 0.5s sleep — ~2,500
    members meant ~21 minutes per tick and thousands of requests, and the
    leaderboard publish (which used to live at the end of this loop) only ran
    after all of it. One unhandled exception also killed the whole tasks.loop
    permanently (discord.py stops a loop on error) — the likely cause of
    "scr-leaderboard hasn't been updating". Now: one batched /internal/linked-
    players call, only linked members are touched, the whole body is guarded,
    and the leaderboard has its own dedicated loop below."""
    try:
        linked = await api_get("/internal/linked-players")
        rmap = {}
        umap = {}
        if linked and linked.get("players"):
            rmap = {p["discord_id"]: p.get("rating", 0) for p in linked["players"] if p.get("discord_id")}
            umap = {p["discord_id"]: (p.get("discord_username"), p.get("discord_display_name"))
                    for p in linked["players"] if p.get("discord_id")}
        if not rmap:
            return
        for guild in bot.guilds:
            try:
                await guild.chunk()
            except Exception as e:
                print(f"Guild chunk error: {e}")
                continue
            for member in guild.members:
                if member.bot: continue
                rat = rmap.get(str(member.id))
                if rat is None: continue
                # July 22 (items 8+9): rename tracking rides the same tick —
                # only CHANGED names post (no extra traffic in steady state).
                try:
                    stored = umap.get(str(member.id))
                    if stored is not None:
                        cur_user = member.name
                        cur_disp = getattr(member, "global_name", None) or member.name
                        if stored[0] != cur_user or stored[1] != cur_disp:
                            await http_session.post(
                                f"{API_BASE_URL}/api/v1/admin/set-discord-username",
                                json={"discord_id": str(member.id),
                                      "discord_username": cur_user,
                                      "discord_display_name": cur_disp},
                                headers={"X-Internal-Key": API_SECRET_KEY},
                                timeout=aiohttp.ClientTimeout(total=5),
                            )
                except Exception:
                    pass
                try:
                    await update_member_role(member, rat)
                    await asyncio.sleep(0.3)   # rate-limit slack only for actual role work
                except Exception:
                    pass
    except Exception as e:
        print(f"[ROLE-SYNC] tick failed: {e}")

@sync_roles_periodic.before_loop
async def before_sync(): await bot.wait_until_ready()


@bot.hybrid_command(name="setup-rank-roles",
                    description="One-time: rename/create the Discord rank roles for the July 28 rank reorganization")
async def setup_rank_roles(ctx):
    """Applies RANK_ROLE_RENAMES to the guild: renames existing rank roles in
    place (keeps color, position, members), creates any that are missing
    entirely. Members get re-sorted onto their new rungs by the regular
    30-minute role sync. Requires the CALLER to have Manage Roles; the BOT
    needs Manage Roles too, with its top role above the rank roles."""
    perms = getattr(ctx.author, "guild_permissions", None)
    if not perms or not perms.manage_roles:
        await ctx.reply("This command requires Manage Roles.", ephemeral=True)
        return
    if ctx.guild is None:
        await ctx.reply("Run this in the server, not a DM.", ephemeral=True)
        return
    await ctx.defer()
    # Base-family colors for roles we have to create from scratch (renames
    # keep whatever color the role already had). Mirrors main.py's fallback
    # palette so a created role isn't colorless.
    family_colors = [
        ("Grand Master", 0xF1C40F),
        ("Master",       0x2ECC71),
        ("Advanced",     0x3498DB),
        ("Intermediate", 0xE67E22),
        ("Beginner",     0x95A5A6),
    ]
    def _color_for(name):
        for prefix, val in family_colors:
            if name.startswith(prefix):
                return discord.Colour(val)
        return discord.Colour(0x95A5A6)
    renamed, created, kept, retired, failed = [], [], [], [], []
    for old_name, new_name in RANK_ROLE_RENAMES:
        try:
            existing_new = discord.utils.get(ctx.guild.roles, name=new_name)
            if existing_new is not None:
                kept.append(new_name)
                # Codex round-3 find 4: if the OLD-named role also survives
                # (partial earlier run, manual creation), members keep it
                # forever — the sync loop only strips names on the NEW
                # ladder, and the skip-if-correct branch never revisits.
                # Retire the obsolete role outright; identity mappings
                # (GM II-V) are excluded by the name check.
                if old_name != new_name:
                    existing_old = discord.utils.get(ctx.guild.roles, name=old_name)
                    if existing_old is not None:
                        await existing_old.delete(reason="July 28 rank reorganization — superseded")
                        retired.append(old_name)
                        await asyncio.sleep(0.3)
                continue
            existing_old = discord.utils.get(ctx.guild.roles, name=old_name)
            if existing_old is not None:
                await existing_old.edit(name=new_name, reason="July 28 rank reorganization")
                renamed.append(new_name)
            else:
                await ctx.guild.create_role(name=new_name, colour=_color_for(new_name),
                                            hoist=False, mentionable=False,
                                            reason="July 28 rank reorganization")
                created.append(new_name)
            await asyncio.sleep(0.3)
        except discord.Forbidden:
            failed.append(f"{new_name} (missing permission — is the bot's top role above the rank roles?)")
        except Exception as ex:
            failed.append(f"{new_name} ({ex})")
    # Push the (possibly recolored-by-rename) roles into rank_role_colors
    # right away so in-game rank titles pick up the new names without
    # waiting for the 6-hour color loop.
    try:
        await push_rank_role_colors.coro()
    except Exception as ex:
        print(f"[RANK-SETUP] color push failed: {ex}")
    lines = [f"Renamed **{len(renamed)}**, created **{len(created)}**, already-correct **{len(kept)}**"
             + (f", retired **{len(retired)}** obsolete" if retired else "") + "."]
    if created:
        lines.append("Created roles land at the bottom of the role list — drag them into "
                     "position if sidebar ordering matters.")
    if failed:
        lines.append("**Failed:** " + "; ".join(failed[:8]))
    lines.append("Members re-sort onto their new rungs on the next role sync (within ~30 min).")
    await ctx.reply("\n".join(lines))


@tasks.loop(minutes=10)
async def publish_lb_loop():
    """Dedicated leaderboard-channel refresh (item 8). Was piggybacked on the
    end of the 30-min role sync — any role-sync failure or slowness starved
    it. Fully guarded so one bad tick can never stop the loop."""
    for guild in bot.guilds:
        try:
            await publish_lb(guild)
        except Exception as e:
            print(f"Leaderboard publish error: {e}")

@publish_lb_loop.before_loop
async def before_publish_lb(): await bot.wait_until_ready()


# ── Rank role color push (v1.29) ──────────────────────────────────
# Sends the guild's ACTUAL rank-role colors to the API so in-game rank
# displays (leaderboard rank column, 'Current Rank' title) match Discord
# exactly. Runs every 6h + on startup; cheap (one POST).

def _clean_rank_name(role_name: str) -> str:
    """'Master V 2270-2329' -> 'Master V'; 'Beginner 1515>' -> 'Beginner'."""
    parts = [p for p in role_name.split() if not any(ch.isdigit() for ch in p)]
    return " ".join(parts).strip()


@tasks.loop(hours=6)
async def push_rank_role_colors():
    if http_session is None or not API_SECRET_KEY:
        return
    payload = []
    for guild in bot.guilds:
        for role in guild.roles:
            if role.name in ALL_RANK_ROLE_NAMES and role.color.value:
                payload.append({
                    "name": _clean_rank_name(role.name),
                    "color": f"#{role.color.value:06X}",
                })
        if payload:
            break  # one guild is the source of truth
    if not payload:
        return
    try:
        async with http_session.post(
            f"{API_BASE_URL}/api/v1/internal/rank-role-colors",
            json=payload,
            headers={"X-Internal-Key": API_SECRET_KEY},
            timeout=aiohttp.ClientTimeout(total=8),
        ) as resp:
            body = await resp.text()
            print(f"[RANK-COLORS] pushed {len(payload)} colors: {resp.status} {body[:80]}")
    except Exception as ex:
        print(f"[RANK-COLORS] push failed: {ex}")


@push_rank_role_colors.before_loop
async def before_rank_colors(): await bot.wait_until_ready()


# ── Discord booster monthly gold (v1.29) ──────────────────────────
# Every boosting member with a linked account gets 2000 gold per calendar
# month. Idempotent server-side (unique on discord_id+month), so this daily
# sweep just re-asserts the current month. Note: Discord's API doesn't expose
# HOW MANY boosts a single member has — a double-booster still gets one
# monthly grant.

@tasks.loop(hours=12)
async def grant_booster_gold():
    if http_session is None or not API_SECRET_KEY:
        return
    month = datetime.now(timezone.utc).strftime("%Y-%m")
    for guild in bot.guilds:
        boosters = list(guild.premium_subscribers or [])
        if not boosters:
            continue
        for member in boosters:
            try:
                async with http_session.post(
                    f"{API_BASE_URL}/api/v1/internal/booster-grant",
                    params={"discord_id": str(member.id), "month": month},
                    headers={"X-Internal-Key": API_SECRET_KEY},
                    timeout=aiohttp.ClientTimeout(total=8),
                ) as resp:
                    if resp.status != 200:
                        print(f"[BOOSTER] grant for {member} failed: {resp.status}")
                        continue
                    data = await resp.json()
                status = data.get("status")
                if status == "granted":
                    print(f"[BOOSTER] {member} granted {data.get('amount')}g for {month}")
                    try:
                        await member.send(
                            f"💜 Thanks for boosting the server! **{data.get('amount', 2000)} gold** "
                            f"has been added to your Competitive ROUNDS account for {month}."
                        )
                    except Exception:
                        pass  # DMs closed — gold still granted
                elif status == "not_linked":
                    # Nudge once per process lifetime so we don't nag monthly.
                    if member.id not in _booster_nudged:
                        _booster_nudged.add(member.id)
                        try:
                            await member.send(
                                "💜 You're boosting the server — boosters get **2000 gold/month** "
                                "in Competitive ROUNDS! Link your account to claim it: in-game "
                                "F5 → Home tab → Get Link Code, then `!link YOUR_CODE` here."
                            )
                        except Exception:
                            pass
            except Exception as ex:
                print(f"[BOOSTER] {member}: {ex}")
            await asyncio.sleep(0.3)


_booster_nudged = set()


@grant_booster_gold.before_loop
async def before_booster(): await bot.wait_until_ready()

# 50/page (Sid, v1.32.1): 100-row pages truncated around row ~66 — real rows
# overflow the splitter's whole-message budget. Same size as /lb.
LB_PAGE_SIZE = 50
# Cache the server max (le=500) so the paginator's Next button covers the
# WHOLE board (the ranked population outgrew 100 in v1.29 — a 100-row cache
# silently hid everyone past #100). One fetch per 10-min tick either way.
LB_TOTAL_FETCH = 500


def _build_lb_embeds(entries: list, total_players: int, page: int, total_pages: int) -> list:
    """Render one page of the auto-posted leaderboard as a LIST of embeds
    (a worst-case 50-row page can exceed a single embed's 4096-char
    description; up to 3 embeds travel in one message). Pure function so the
    paginator view + initial post share the rendering."""
    start = page * LB_PAGE_SIZE
    end = min(start + LB_PAGE_SIZE, len(entries))
    # Rank from list position (entries are one offset-0 fetch, so position
    # IS the rank) — entry["rank"] is double-offset on offset pages server-side
    # (see _lb_line docstring); deriving locally keeps this correct even if
    # the fetch ever grows an offset.
    lines = [_lb_line(e, rank=start + i + 1) for i, e in enumerate(entries[start:end])]
    # Live relative timestamp INSIDE the embed body ("Updated 3 minutes ago",
    # ticking client-side). The embed's footer timestamp was the only recency
    # signal before, and a silently-edited days-old message reads as a dead
    # board ("posts aren't updating") even when every 10-min edit lands.
    # now(timezone.utc), not utcnow(): .timestamp() on a naive datetime assumes
    # LOCAL time — correct only while the container happens to run UTC.
    updated = f"Updated <t:{int(datetime.now(timezone.utc).timestamp())}:R>\n\n"
    descs = _split_lb_descriptions(lines, first_header=updated)
    embeds = []
    for ci, desc in enumerate(descs):
        em = discord.Embed(
            # Title on the FIRST embed only — publish_lb's duplicate rescan
            # identifies the board by this title on embeds[0].
            title="🏆 Ranked Leaderboard" if ci == 0 else None,
            description=desc,
            color=discord.Color.gold(),
            timestamp=datetime.utcnow() if ci == len(descs) - 1 else None,
        )
        if ci == len(descs) - 1:
            em.set_footer(text=f"Page {page+1}/{total_pages} • {total_players} ranked players • Auto-updated")
        embeds.append(em)
    return embeds


class LeaderboardPaginator(discord.ui.View):
    """Prev/Next buttons for the auto-posted leaderboard. Caches the entries list
    so page flips don't re-hit the API. Long timeout (24h) — refreshed on every
    publish_lb tick (sync_roles_periodic loop, every 30 min) so users always have
    a working set of buttons within an hour of clicking."""
    def __init__(self, entries: list, total_players: int):
        super().__init__(timeout=86400)
        self.entries = entries
        self.total_players = total_players
        self.total_pages = max(1, (len(entries) + LB_PAGE_SIZE - 1) // LB_PAGE_SIZE)
        self.page = 0

    def _update_buttons(self):
        # Disable Prev on first page, Next on last page. Children list order = button order.
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                if child.label and child.label.startswith("◀"):
                    child.disabled = (self.page <= 0)
                elif child.label and child.label.startswith("Next"):
                    child.disabled = (self.page >= self.total_pages - 1)

    @discord.ui.button(label="◀ Prev", style=discord.ButtonStyle.secondary)
    async def prev(self, interaction: discord.Interaction, _: discord.ui.Button):
        self.page = max(0, self.page - 1)
        self._update_buttons()
        await interaction.response.edit_message(
            embeds=_build_lb_embeds(self.entries, self.total_players, self.page, self.total_pages),
            view=self,
        )

    @discord.ui.button(label="Next ▶", style=discord.ButtonStyle.secondary)
    async def nxt(self, interaction: discord.Interaction, _: discord.ui.Button):
        self.page = min(self.total_pages - 1, self.page + 1)
        self._update_buttons()
        await interaction.response.edit_message(
            embeds=_build_lb_embeds(self.entries, self.total_players, self.page, self.total_pages),
            view=self,
        )


# Remembered per-channel leaderboard message id — direct edits instead of a
# history scan. If the message got deleted we fall back to a (wider) scan and
# finally post a fresh one. The old 5-message scan silently posted duplicates
# (or found nothing to edit) once a few chat messages buried the board (item 8).
_lb_message_ids: dict = {}

async def publish_lb(guild):
    if LEADERBOARD_CHANNEL_ID <= 0: return
    ch = guild.get_channel(LEADERBOARD_CHANNEL_ID)
    if not ch:
        try: ch = await bot.fetch_channel(LEADERBOARD_CHANNEL_ID)
        except Exception as e:
            print(f"[LB] channel {LEADERBOARD_CHANNEL_ID} unreachable: {e}")
            return
    if not ch: return
    data = await api_get(f"/leaderboard?limit={LB_TOTAL_FETCH}&min_matches=1")
    if not data or not data.get("entries"):
        # api_get already logged the status on non-200; this covers empty payloads.
        print("[LB] no leaderboard data this tick — skipping")
        return
    entries = data["entries"]
    total_players = data.get("total_players", 0)
    total_pages = max(1, (len(entries) + LB_PAGE_SIZE - 1) // LB_PAGE_SIZE)
    embeds = _build_lb_embeds(entries, total_players, 0, total_pages)
    view = LeaderboardPaginator(entries, total_players)
    view._update_buttons()
    # Fast path: edit the message we already know about. Logged on success too —
    # a silently-successful loop is indistinguishable from a dead one in the logs
    # (learning #83), and "is the board actually being edited?" is exactly the
    # question this bug keeps asking. 6 lines/hour.
    #
    # Bottom-anchor: an EDIT never moves a Discord message and never changes its
    # "posted" date, so a days-old board being edited every 10 minutes still
    # reads as dead ("posts aren't posting/updating") to anyone scrolled to the
    # channel bottom. If anything was posted after our board, delete it and
    # repost at the bottom — in a dedicated board channel this triggers rarely
    # (restarts, someone chatting), at most once per tick, and pings no one.
    mid = _lb_message_ids.get(ch.id)
    if mid:
        try:
            msg = await ch.fetch_message(mid)
            if getattr(ch, "last_message_id", None) not in (None, mid):
                try:
                    await msg.delete()
                except Exception:
                    pass
                sent = await ch.send(embeds=embeds, view=view)
                _lb_message_ids[ch.id] = sent.id
                print(f"[LB] board was buried (last_message_id={ch.last_message_id}) — reposted at bottom as mid={sent.id}")
                return
            await msg.edit(embeds=embeds, view=view)
            print(f"[LB] edited board mid={mid}")
            return
        except Exception as e:
            print(f"[LB] fast-path edit of mid={mid} failed ({e}) — rescanning")
            _lb_message_ids.pop(ch.id, None)  # deleted/unreachable — rediscover
    # Rescan: adopt the NEWEST board message and DELETE any older duplicates.
    # Restart-era re-anchors and the pre-v1.30 5-message scan left duplicate
    # boards behind in some channels; whichever one a viewer (or a pin) is
    # looking at may not be the one we edit — a permanently "stale" board that
    # no log line ever explained. Sweeping duplicates makes the visible board
    # unambiguous, and every outcome now logs.
    keeper = None
    dupes = 0
    async for msg in ch.history(limit=50):
        if msg.author == bot.user and msg.embeds and "Ranked Leaderboard" in (msg.embeds[0].title or ""):
            if keeper is None:
                keeper = msg
            else:
                try:
                    await msg.delete()
                    dupes += 1
                except Exception as e:
                    print(f"[LB] couldn't delete duplicate board mid={msg.id}: {e}")
    if dupes:
        print(f"[LB] deleted {dupes} duplicate stale board message(s)")
    if keeper is not None:
        if getattr(ch, "last_message_id", None) not in (None, keeper.id):
            # Same bottom-anchor rule as the fast path.
            try:
                await keeper.delete()
            except Exception:
                pass
            sent = await ch.send(embeds=embeds, view=view)
            _lb_message_ids[ch.id] = sent.id
            print(f"[LB] re-anchored board was buried — reposted at bottom as mid={sent.id}")
            return
        _lb_message_ids[ch.id] = keeper.id
        try:
            await keeper.edit(embeds=embeds, view=view)
            print(f"[LB] re-anchored to board mid={keeper.id} and edited")
        except Exception as e:
            # Leave the id cached; the next tick retries via the fast path.
            print(f"[LB] re-anchor edit of mid={keeper.id} failed: {e}")
        return
    sent = await ch.send(embeds=embeds, view=view)
    _lb_message_ids[ch.id] = sent.id
    print(f"[LB] posted fresh leaderboard message in {ch.id}")

# ── Anti-cheat flag relay ────────────────────────────────────────
# IDs whose Discord send succeeded but durable API acknowledgement failed.
# Retrying the ack without reposting gives process-lifetime exactly-once
# behavior; a crash in that tiny window may duplicate once, never lose a flag.
_flag_posts_pending_ack: dict[str, int] = {}

_last_ban_id_posted: str | None = None
_ban_poller_initialized = False


@tasks.loop(seconds=60)
async def poll_new_bans():
    """Poll new mod-wide player bans and post them to #scr-admin (item 4)."""
    global _last_ban_id_posted, _ban_poller_initialized
    if not http_session or not API_SECRET_KEY or not ADMIN_CHANNEL_ID:
        return
    try:
        params = {"limit": 50}
        if _last_ban_id_posted:
            params["since_id"] = _last_ban_id_posted
        async with http_session.get(
            f"{API_BASE_URL}/api/v1/internal/recent-bans",
            params=params, headers={"X-Internal-Key": API_SECRET_KEY},
            timeout=aiohttp.ClientTimeout(total=10),
        ) as resp:
            if resp.status != 200:
                print(f"[BANS] feed status={resp.status}")
                return
            payload = await resp.json()
    except Exception as e:
        print(f"[BANS] feed error: {e}")
        return
    bans = payload.get("bans") or []
    if not bans:
        return
    # Cold start: anchor at newest, don't replay the whole ban history.
    if not _ban_poller_initialized:
        _ban_poller_initialized = True
        _last_ban_id_posted = bans[-1]["id"]
        print(f"[BANS] cold start, anchored at {_last_ban_id_posted[:8]}")
        return
    channel = bot.get_channel(ADMIN_CHANNEL_ID) or await bot.fetch_channel(ADMIN_CHANNEL_ID)
    if channel is None:
        print(f"[BANS] admin channel {ADMIN_CHANNEL_ID} not resolvable")
        return
    for b in bans:
        try:
            name = b.get("display_name") or b["steam_id"]
            embed = discord.Embed(
                title="🔨 Player banned (mod-wide)",
                description=(
                    f"**{discord.utils.escape_markdown(str(name))}** (`{b['steam_id']}`)\n"
                    f"Reason: **{b.get('reason') or 'violation'}**\n"
                    f"By: `{b.get('banned_by_steam_id') or '—'}`"
                ),
                color=0xCC2222,
                timestamp=datetime.fromisoformat(b["banned_at"].replace("Z", "+00:00")) if b.get("banned_at") else None,
            )
            await channel.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
            _last_ban_id_posted = b["id"]
            print(f"[BANS] posted ban {b['steam_id']}")
        except Exception as ex:
            print(f"[BANS] post error: {ex}")


@tasks.loop(seconds=30)
async def poll_channel_posts():
    """Generic announce queue (v1.30): the API's pending_channel_posts table
    holds messages destined for arbitrary channels (first use: the #scr-faq
    sheet, migration 110). Ack-after-send (learning #105) so a bot restart
    can't drop a queued post; a failed send just retries next tick. Posts are
    delivered in (sort_order, id) order, one batch per tick."""
    if http_session is None or not API_SECRET_KEY:
        return
    data = await api_get("/internal/channel-posts/pending")
    if not data or not data.get("posts"):
        return
    for p in data["posts"]:
        try:
            ch = bot.get_channel(int(p["channel_id"]))
            if ch is None:
                ch = await bot.fetch_channel(int(p["channel_id"]))
            if ch is None:
                print(f"[CHANNEL-POST] channel {p['channel_id']} not found — leaving post {p['id']} queued")
                return  # bail — order matters, don't skip ahead
            # Explicit allowed_mentions: server-queued posts (tournament
            # signup/leave/pushback etc.) carry <@id> mentions that MUST ping
            # the user — but never let queued content ping @everyone/roles.
            await ch.send(
                p["content"][:2000],
                allowed_mentions=discord.AllowedMentions(users=True, everyone=False, roles=False),
            )
            await api_post("/internal/channel-posts/ack", params={"post_id": p["id"]})
            print(f"[CHANNEL-POST] posted {p['id']} to {p['channel_id']}")
        except discord.Forbidden:
            print(f"[CHANNEL-POST] forbidden in channel {p['channel_id']} — leaving post {p['id']} queued")
            return
        except Exception as e:
            print(f"[CHANNEL-POST] send failed for {p['id']}: {e} — will retry")
            return  # keep strict ordering; retry from this post next tick


@poll_channel_posts.before_loop
async def before_channel_posts():
    await bot.wait_until_ready()


def _flag_color_and_emoji(reason: str, auto_inv: bool):
    if reason == "suspected_macro":         return (0xC0392B, "M")
    if reason == "fps_dip_pattern":         return (0x9B59B6, "F")
    if reason == "low_fps_outlier":         return (0x8E44AD, "F")
    if reason == "freeze_events":           return (0x3498DB, "Z")
    if reason == "ping_gap_cluster":        return (0x2980B9, "N")
    if reason == "suspected_speedhack":     return (0xD35400, "S")
    if reason == "too_many_cards":          return (0xE74C3C, "🃏")  # red
    if reason == "short_duration_pattern":  return (0xE67E22, "⏱️")  # orange
    if reason == "inactive_player":         return (0xF1C40F, "💤")  # yellow (advisory)
    return (0x95A5A6, "🚩")


def _flag_embed_text(value, limit=850):
    rendered = discord.utils.escape_markdown(str(value or "not recorded"))
    return rendered if len(rendered) <= limit else rendered[:limit - 3] + "..."


async def _ack_anticheat_flag(flag_id: str, evidence_revision: int) -> bool:
    try:
        async with http_session.post(
            f"{API_BASE_URL}/api/v1/internal/recent-flags/ack",
            params={
                "flag_id": flag_id,
                "evidence_revision": evidence_revision,
            },
            headers={"X-Internal-Key": API_SECRET_KEY},
            timeout=aiohttp.ClientTimeout(total=10),
        ) as resp:
            if resp.status == 200:
                return True
            print(f"[ANTICHEAT] ack status={resp.status} flag={flag_id}")
    except Exception as ex:
        print(f"[ANTICHEAT] ack error flag={flag_id}: {ex}")
    return False


@tasks.loop(seconds=30)
async def poll_chat_catchup():
    """Backfill any ingame chat messages the WS broadcast missed.

    Background: lopidav reported that his ingame messages persisted to the DB
    (so the server received them on the WS) but never reached Discord — the
    bot's WS subscription appeared healthy yet only some senders' messages
    came through. Rather than chase the broadcast bug, we poll /chat/recent
    every 30s and replay anything newer than _last_relayed_ts. The same
    timestamp dedup that already protects WS reconnect catchup also protects
    this path, so live WS messages won't double-post."""
    if not http_session:
        return
    await _catchup_ingame_since()


@tasks.loop(seconds=60)
async def poll_anticheat_flags():
    """Poll the API for new flagged_matches entries and post them to #scr-admin."""
    if not http_session or not API_SECRET_KEY or not ADMIN_CHANNEL_ID:
        return
    try:
        params = {"limit": 50}
        async with http_session.get(
            f"{API_BASE_URL}/api/v1/internal/recent-flags",
            params=params,
            headers={"X-Internal-Key": API_SECRET_KEY},
            timeout=aiohttp.ClientTimeout(total=10),
        ) as resp:
            if resp.status != 200:
                print(f"[ANTICHEAT] feed status={resp.status}")
                return
            payload = await resp.json()
    except Exception as e:
        print(f"[ANTICHEAT] feed error: {e}")
        return

    flags = payload.get("flags") or []
    if not flags:
        return

    try:
        channel = bot.get_channel(ADMIN_CHANNEL_ID) or await bot.fetch_channel(ADMIN_CHANNEL_ID)
    except (discord.Forbidden, discord.NotFound, discord.HTTPException) as ex:
        # Keep the loop alive and leave every row unacknowledged for retry.
        print(f"[ANTICHEAT] admin channel resolution failed: {ex}")
        return
    except Exception as ex:
        print(f"[ANTICHEAT] unexpected channel resolution error: {ex}")
        return
    if channel is None:
        print(f"[ANTICHEAT] admin channel {ADMIN_CHANNEL_ID} not resolvable")
        return

    for f in flags:
        flag_id = str(f.get("id") or "")
        if not flag_id:
            continue
        evidence_revision = int(f.get("discord_evidence_revision") or 1)
        if flag_id in _flag_posts_pending_ack:
            pending_revision = _flag_posts_pending_ack[flag_id]
            if pending_revision != evidence_revision:
                # The evidence changed after the prior embed was accepted.
                # Post the new revision instead of acknowledging it unseen.
                _flag_posts_pending_ack.pop(flag_id, None)
            elif await _ack_anticheat_flag(flag_id, pending_revision):
                _flag_posts_pending_ack.pop(flag_id, None)
                continue
            else:
                return
        try:
            color, emoji = _flag_color_and_emoji(f["flag_reason"], f["auto_invalidated"])
            mode = "Ranked" if f.get("is_ranked") else "Casual"
            dur = f.get("duration_seconds")
            dur_str = f"{dur}s" if dur is not None else "—"
            verdict = "auto-invalidated" if f["auto_invalidated"] else "advisory (manual review)"
            match_state = "currently valid"
            if f.get("match_invalidated"):
                match_state = "currently invalidated"
                if f.get("match_invalidation_reason"):
                    match_state += f" ({f['match_invalidation_reason']})"
            embed = discord.Embed(
                title=f"{emoji} Match flagged: `{f['flag_reason']}`",
                description=(
                    f"**{discord.utils.escape_markdown(str(f['p1_name']))}** vs "
                    f"**{discord.utils.escape_markdown(str(f['p2_name']))}** ({mode}, {dur_str})\n"
                    f"Status: **{verdict}**; {_flag_embed_text(match_state, 180)}\n"
                    f"Game code: `{f.get('game_code') or 'not recorded'}` | Match ID: `{f['match_id']}`"
                ),
                color=color,
                timestamp=datetime.fromisoformat(f["created_at"].replace("Z", "+00:00")) if f.get("created_at") else None,
            )
            ids = (
                f"{f.get('p1_name')}: {f.get('p1_steam_id')}\n"
                f"{f.get('p2_name')}: {f.get('p2_steam_id')}\n"
                f"Suspect(s): {f.get('suspect_steam_text') or 'not attributable'}"
            )
            embed.add_field(name="Steam IDs / suspect", value=_flag_embed_text(ids, 500), inline=False)
            embed.add_field(name="Detector evidence", value=_flag_embed_text(f.get("evidence_summary"), 700), inline=False)
            progress = f"{f.get('score_summary')}\nPoints: {f.get('point_progress')}"
            embed.add_field(name="Score / point progress", value=_flag_embed_text(progress, 650), inline=False)
            embed.add_field(name="Cards picked", value=_flag_embed_text(f.get("cards_summary"), 650), inline=False)
            embed.add_field(name="Combat / input / FPS", value=_flag_embed_text(f.get("telemetry_summary"), 750), inline=False)
            embed.add_field(name="Connection evidence", value=_flag_embed_text(f.get("connection_summary"), 750), inline=False)
            embed.add_field(name="Reporter context", value=_flag_embed_text(f.get("match_context"), 400), inline=False)
            await channel.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
            _flag_posts_pending_ack[flag_id] = evidence_revision
            if not await _ack_anticheat_flag(flag_id, evidence_revision):
                return
            _flag_posts_pending_ack.pop(flag_id, None)
        except Exception as ex:
            print(f"[ANTICHEAT] post error for flag {f.get('id')}: {ex}")
            return


# ── GitHub release announcements ───────────────────────────────────────────

# In-memory tag of the most recent release we've already announced. Bot
# rebuilds reset this to None — the cold-start branch in the loop anchors
# to whatever the latest tag is on first tick (no post) so a rebuild
# doesn't re-spam the channel. The downside: a release that lands DURING
# a rebuild window won't be auto-announced and needs /announce-release.
_last_release_tag = None
_release_poller_initialized = False


def _format_release_message(release_json):
    """Build the Discord-flavored release message. Trim body to fit Discord's
    2000-char message limit, with a 'see full notes' link footer that always
    fits regardless of how long the body is."""
    tag = release_json.get("tag_name") or "v?"
    name = release_json.get("name") or tag
    url = release_json.get("html_url") or f"https://github.com/{GITHUB_RELEASES_REPO}/releases/tag/{tag}"
    body = release_json.get("body") or ""
    # Strip GitHub-specific markdown that Discord renders weirdly. Keep the
    # rest mostly intact since both platforms support similar markdown.
    body = body.replace("\r\n", "\n").strip()
    header = f"**🚀 New release: {name}**\n{url}\n\n"
    footer = f"\n\n— Full notes: {url}"
    # Discord per-message limit is 2000 chars. Reserve room for header + footer.
    budget = 2000 - len(header) - len(footer) - 20  # 20 for safety/ellipsis
    if len(body) > budget:
        body = body[:budget].rstrip() + "…"
    return header + body + footer


@tasks.loop(minutes=5)
async def poll_github_releases():
    """Watch the public GitHub releases endpoint for the mod repo. When a new
    tag appears (different from `_last_release_tag`), post the formatted
    release notes to #releases and mirror to the discussions/chat channel."""
    global _last_release_tag, _release_poller_initialized
    if not http_session:
        return
    if not RELEASES_CHANNEL_ID and not CHAT_CHANNEL_ID:
        return
    try:
        # Public endpoint, no auth needed for unauthenticated requests (60/hr/IP).
        # Don't send our X-Internal-Key header — it's invalid for github.com.
        async with aiohttp.ClientSession() as s:  # fresh session, no shared headers
            async with s.get(
                f"https://api.github.com/repos/{GITHUB_RELEASES_REPO}/releases/latest",
                headers={"Accept": "application/vnd.github+json", "User-Agent": "comp-rounds-bot"},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status != 200:
                    print(f"[RELEASES] GitHub status={resp.status}")
                    return
                payload = await resp.json()
    except Exception as e:
        print(f"[RELEASES] fetch error: {e}")
        return

    tag = payload.get("tag_name")
    if not tag:
        return

    # Cold-start: don't repost on bot restart. Anchor to the current latest
    # tag and skip posting on the first tick.
    if not _release_poller_initialized:
        _release_poller_initialized = True
        _last_release_tag = tag
        print(f"[RELEASES] cold start, anchored at {tag}")
        return

    if tag == _last_release_tag:
        return

    # New release — post to #releases only (chat mirror dropped per user
    # request: "only post new releases in the Releases channel instead of both").
    msg = _format_release_message(payload)
    posted = 0
    if RELEASES_CHANNEL_ID:
        try:
            ch = bot.get_channel(RELEASES_CHANNEL_ID) or await bot.fetch_channel(RELEASES_CHANNEL_ID)
            if ch is None:
                print(f"[RELEASES] channel {RELEASES_CHANNEL_ID} not resolvable")
            else:
                await ch.send(msg)
                posted = 1
        except Exception as e:
            print(f"[RELEASES] post error: {e}")
    _last_release_tag = tag
    print(f"[RELEASES] announced {tag} to {posted} channel(s)")


@bot.hybrid_command(
    name="announce-release",
    description="Post the latest GitHub release notes to #releases + discussions (admins only)",
)
async def announce_release(ctx):
    """One-shot manual announcement. Used to bootstrap the system (e.g. announce
    v1.25.14 right after deploying this code, since cold-start anchor would
    otherwise skip the very first detected release). Requires Manage Messages
    in the channel where the command is invoked."""
    global _last_release_tag, _release_poller_initialized
    perms = getattr(ctx.author, "guild_permissions", None)
    if not perms or not perms.manage_messages:
        await ctx.reply("This command requires Manage Messages.", ephemeral=True)
        return
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(
                f"https://api.github.com/repos/{GITHUB_RELEASES_REPO}/releases/latest",
                headers={"Accept": "application/vnd.github+json", "User-Agent": "comp-rounds-bot"},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status != 200:
                    await ctx.reply(f"GitHub returned {resp.status}.", ephemeral=True)
                    return
                payload = await resp.json()
    except Exception as e:
        await ctx.reply(f"Fetch failed: {e}", ephemeral=True)
        return

    tag = payload.get("tag_name") or "?"
    msg = _format_release_message(payload)
    posted = []
    if RELEASES_CHANNEL_ID:
        try:
            ch = bot.get_channel(RELEASES_CHANNEL_ID) or await bot.fetch_channel(RELEASES_CHANNEL_ID)
            if ch is not None:
                await ch.send(msg)
                posted.append("#releases")
        except Exception as e:
            print(f"[RELEASES] manual post error: {e}")
    # Update the anchor so the polling loop doesn't re-announce this tag.
    _last_release_tag = tag
    _release_poller_initialized = True
    if posted:
        await ctx.reply(f"Posted {tag} to {', '.join(posted)}.", ephemeral=True)
    else:
        await ctx.reply("No channels resolvable.", ephemeral=True)


# ── Tournaments ────────────────────────────────────────────────────────────
#
# Polls /api/v1/tournaments/internal/watch and DMs players on state
# transitions. All state is in-memory (_tournament_state) — on bot restart we
# re-establish the snapshot and skip notifications for events already past.
# This prevents a restart from spamming old events but means a transition
# happening DURING restart won't be announced; the /tournaments tab in-game
# still shows the correct state.
#
# /dm-opponent: rate-limited (8/min per caller) message relay to your
# current tournament opponent's DM.

import collections as _coll
from datetime import timedelta as _td

_tournament_state = {}          # tournament_id -> last seen status
_notified_match_ready = set()   # match_ids we've already DM'd "match ready" for
_notified_match_scheduled = set()  # match_ids we've already DM'd the break/next-opponent notice for
_notified_completed = set()     # tournament_ids we've already paid trophies for
_notified_deadline_warn = set() # match_ids we've already DM'd a 24h-deadline warning for (async only)
_notified_prestart = set()      # tournament_ids we've sent the T-15min "get in ROUNDS" reminder for (item 3)
_match_nag_at = {}              # match_id -> monotonic ts of the last sync last-call/stall nag (item 3)
_notified_nag_date = {}         # match_id -> YYYY-MM-DD last day we sent a "still pending" nag
_dm_opponent_history = _coll.defaultdict(_coll.deque)  # discord_id -> deque[datetime]
_DM_OPPONENT_LIMIT = 8
_DM_OPPONENT_WINDOW_SECS = 60
_watch_cache = {"tournaments": []}  # most recent /internal/watch payload

def _resolve_trophy_role(guild: discord.Guild, name: str):
    return discord.utils.get(guild.roles, name=name)

async def _dm_user(discord_id, text_content):
    if not discord_id:
        return False
    try:
        user = bot.get_user(int(discord_id)) or await bot.fetch_user(int(discord_id))
        if user is None:
            return False
        await user.send(text_content)
        return True
    except discord.Forbidden:
        print(f"[TOURNAMENT-DM] {discord_id} has DMs closed")
        return False
    except Exception as e:
        print(f"[TOURNAMENT-DM] {discord_id}: {e}")
        return False


async def _dm_all_signups(t, body):
    count = 0
    for s in t.get("signups", []):
        if s.get("is_speculative"):
            continue
        if await _dm_user(s.get("discord_id"), body):
            count += 1
        await asyncio.sleep(0.15)  # gentle rate-limit — ~6/sec
    print(f"[TOURNAMENT-DM] Sent '{body[:40]}...' to {count} players")


async def _announce_in_channel(text_content):
    if not TOURNAMENT_CHANNEL_ID:
        return
    try:
        ch = bot.get_channel(TOURNAMENT_CHANNEL_ID) or await bot.fetch_channel(TOURNAMENT_CHANNEL_ID)
        if ch:
            await ch.send(text_content)
    except Exception as e:
        print(f"[TOURNAMENT-ANNOUNCE] {e}")


def _fmt_pt(iso_str):
    """Format a UTC ISO timestamp as human-readable 'Sat 12:00 PT'."""
    if not iso_str:
        return "(TBD)"
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        return f"<t:{int(dt.timestamp())}:F>"  # Discord native timestamp
    except Exception:
        return iso_str


async def _promote_role(member, base_name, x2_name):
    """Grant base_name on first placement; on repeat placements, swap base -> x2.
    Idempotent: if member already has x2_name, nothing changes."""
    guild = member.guild
    base = _resolve_trophy_role(guild, base_name)
    x2 = _resolve_trophy_role(guild, x2_name)
    if not base:
        print(f"[TOURNAMENT-TROPHY] role '{base_name}' not in guild {guild.name}")
        return
    has_base = any(r.name == base_name for r in member.roles)
    has_x2 = x2 is not None and any(r.name == x2_name for r in member.roles)
    try:
        if has_x2:
            return  # already at the x2 tier; no further promotion in Phase 1
        if has_base and x2:
            await member.remove_roles(base, reason="Tournament x2 promotion")
            await member.add_roles(x2, reason="Tournament x2 promotion")
            print(f"[TOURNAMENT-TROPHY] {member.display_name} promoted to {x2_name}")
        elif not has_base:
            await member.add_roles(base, reason="Tournament placement")
            print(f"[TOURNAMENT-TROPHY] {member.display_name} granted {base_name}")
    except Exception as e:
        print(f"[TOURNAMENT-TROPHY] {member.display_name} ({base_name}): {e}")


async def _grant_trophy(tournament, signup_id, base_role_name):
    if not signup_id or not base_role_name:
        return
    did = None
    for s in tournament.get("signups", []):
        if s.get("signup_id") == signup_id:
            did = s.get("discord_id")
            break
    if not did:
        return
    x2_name = base_role_name + TROPHY_X2_SUFFIX
    for guild in bot.guilds:
        member = await find_member(guild, did)
        if not member:
            continue
        await _promote_role(member, base_role_name, x2_name)


async def _grant_participant(tournament):
    """Grant SCR Tournament Participant on first-ever participation; promote to
    Participant 2 on the second+ participation. Applied to confirmed signups
    only (is_speculative=False) at tournament completion time."""
    for s in tournament.get("signups", []):
        if s.get("is_speculative"):
            continue
        did = s.get("discord_id")
        if not did:
            continue
        for guild in bot.guilds:
            member = await find_member(guild, did)
            if not member:
                continue
            await _promote_role(member, TROPHY_ROLE_PART, TROPHY_ROLE_PART2)
            await asyncio.sleep(0.1)


@tasks.loop(seconds=30)
async def poll_tournaments():
    """Poll the internal watch endpoint, detect state transitions, DM+announce."""
    global _watch_cache
    if not http_session or not API_SECRET_KEY:
        return
    try:
        async with http_session.get(
            f"{API_BASE_URL}/api/v1/tournaments/internal/watch",
            headers={"X-Internal-Key": API_SECRET_KEY},
            timeout=aiohttp.ClientTimeout(total=10),
        ) as resp:
            if resp.status != 200:
                return
            payload = await resp.json()
    except Exception as e:
        print(f"[TOURNAMENT-POLL] {e}")
        return

    _watch_cache = payload
    for t in payload.get("tournaments", []):
        tid = t["tournament_id"]
        status = t["status"]
        kind = t.get("kind") or "sync"
        prev = _tournament_state.get(tid)
        _tournament_state[tid] = status

        # Transition: new tournament in voting state -> channel announce
        if prev is None and status == "voting":
            if kind == "async":
                await _announce_in_channel(
                    f"**Async tournament signups open.** Double-elim BO3, 7-day match deadlines, self-paced. "
                    f"Signups close {_fmt_pt(t['lock_at'])}. Sign up in-game via the Tournaments → ASYNC tab."
                )
            else:
                await _announce_in_channel(
                    f"**Tournament signups open.** Default start: {_fmt_pt(t['default_start_ts'])}. "
                    f"Vote on alternate times or sign up in-game via the Tournaments tab. "
                    f"Signups close {_fmt_pt(t['lock_at'])}."
                )
        # voting -> locked -> DM every signup their seed + scheduled start
        if prev == "voting" and status == "locked":
            scheduled = _fmt_pt(t.get("scheduled_start_ts"))
            latest_ver = payload.get("latest_mod_version")
            await _announce_in_channel(
                f"**Tournament locked.** {len([s for s in t['signups'] if not s['is_speculative']])} players confirmed. "
                f"Starts {scheduled}. Bracket visible in-game."
            )
            # Individual DMs. Wording matters (item 3): since v1.24 the mod
            # heartbeats automatically while ROUNDS is running — players do NOT
            # need to sit in the Tournaments tab. What actually matters is
            # having the game open at start time. Outdated clients get an
            # explicit extra warning: an old mod is version-gated by the API,
            # can't heartbeat, and would silently no-show-forfeit.
            for s in t.get("signups", []):
                if s.get("is_speculative"):
                    continue
                body = (f"Tournament locked — you're in! It starts **{scheduled}**.\n"
                        f"**All you need to do: have ROUNDS open (main menu) at that time.** "
                        f"The mod connects you to your opponent automatically each round, with a "
                        f"short breather between your matches (skippable when both players press "
                        f"Play Now). Plan to be around for **a couple of hours** — double-elim "
                        f"BO3s take a while. If ROUNDS isn't running when a match of yours starts "
                        f"(10 min grace), you forfeit that match.")
                sv = s.get("mod_version")
                if latest_ver and sv and sv != latest_ver:
                    body += (f"\n⚠️ **Your mod is v{sv}, latest is v{latest_ver}.** "
                             f"Update before the tournament (launch ROUNDS, quit, launch again) — "
                             f"an outdated mod may not be able to connect.")
                await _dm_user(s.get("discord_id"), body)
                await asyncio.sleep(0.1)
        # locked: pre-start reminder DM ~15 min out (item 3 — "players not
        # knowing they have a tournament"). Once per tournament.
        if status == "locked" and tid not in _notified_prestart and t.get("scheduled_start_ts"):
            try:
                from datetime import datetime as _dt
                st = _dt.fromisoformat(t["scheduled_start_ts"].replace("Z", "+00:00"))
                mins_out = (st - _dt.now(st.tzinfo)).total_seconds() / 60.0
                if 0 < mins_out <= 15:
                    _notified_prestart.add(tid)
                    await _announce_in_channel(f"**Tournament starts in {int(mins_out)} minutes.** Signed-up players: get ROUNDS open to the main menu!")
                    for s in t.get("signups", []):
                        if s.get("is_speculative") or s.get("forfeited"):
                            continue
                        await _dm_user(s.get("discord_id"),
                                       f"⏰ **Your tournament starts in ~{int(mins_out)} minutes.** "
                                       f"Open ROUNDS now and sit at the main menu — the mod does the rest.")
                        await asyncio.sleep(0.1)
            except Exception as e:
                print(f"[TOURNAMENT-POLL] prestart parse: {e}")
        # locked -> running -> channel announce
        if prev == "locked" and status == "running":
            await _announce_in_channel("**Tournament started.** Round 1 is live.")
        # Any state: DM players whose match just became scheduled/ready
        if status == "running":
            for m in t.get("matches", []):
                # Break state (item 2, July 17 round 2): sync rounds 2+ sit in
                # 'scheduled' for a ~7 min breather. DM both players who's
                # next + a live Discord countdown, and how to skip the break.
                if m.get("status") == "scheduled" and kind != "async":
                    mid_s = m["match_id"]
                    if mid_s not in _notified_match_scheduled:
                        _notified_match_scheduled.add(mid_s)
                        sr_unix = _unix_ts(m.get("scheduled_ready_at"))
                        when = f"<t:{sr_unix}:R>" if sr_unix else "in a few minutes"
                        rd = m.get("round") or "?"
                        sp1d = m.get("p1_discord_id"); sp2d = m.get("p2_discord_id")
                        sp1n = m.get("p1_name") or "opponent"
                        sp2n = m.get("p2_name") or "opponent"
                        await _dm_user(sp1d,
                                       f"🕐 **Next up: vs {sp2n}** (round {rd}). Your match starts {when} — "
                                       f"short breather, no rush. Want to play right away? You BOTH press "
                                       f"**Play Now** in F5 → Tournaments and it starts immediately.")
                        await _dm_user(sp2d,
                                       f"🕐 **Next up: vs {sp1n}** (round {rd}). Your match starts {when} — "
                                       f"short breather, no rush. Want to play right away? You BOTH press "
                                       f"**Play Now** in F5 → Tournaments and it starts immediately.")
                    continue
                if m.get("status") != "ready":
                    continue
                mid = m["match_id"]
                p1d = m.get("p1_discord_id"); p2d = m.get("p2_discord_id")
                p1n = m.get("p1_name") or "opponent"
                p2n = m.get("p2_name") or "opponent"
                # Initial match-ready DM (once per match).
                if mid not in _notified_match_ready:
                    _notified_match_ready.add(mid)
                    if kind == "async":
                        dl_str = _fmt_pt(m.get("deadline_at"))
                        await _dm_user(p1d, f"Your async tournament match vs **{p2n}** is live. Deadline to play: {dl_str}. "
                                             f"Coordinate via `/dm-opponent` or Discord. Use the Tournaments → ASYNC tab in-game to see the bracket + room code.")
                        await _dm_user(p2d, f"Your async tournament match vs **{p1n}** is live. Deadline to play: {dl_str}. "
                                             f"Coordinate via `/dm-opponent` or Discord. Use the Tournaments → ASYNC tab in-game to see the bracket + room code.")
                    else:
                        await _dm_user(p1d, f"🎮 Your tournament match vs **{p2n}** is ready — **get in ROUNDS now**. The mod auto-connects you from the main menu. No-show forfeits in a few minutes.")
                        await _dm_user(p2d, f"🎮 Your tournament match vs **{p1n}** is ready — **get in ROUNDS now**. The mod auto-connects you from the main menu. No-show forfeits in a few minutes.")
                # Sync last-call + stall nag (item 3): if a ready match is
                # about to hit its no-show deadline (<90s) — or sat past it
                # for 5+ minutes because both players heartbeat but neither
                # joined the room — DM both sides again. Repeats at most
                # every 5 minutes per match.
                if kind != "async" and m.get("ready_deadline_at"):
                    try:
                        from datetime import datetime as _dt
                        dl = _dt.fromisoformat(m["ready_deadline_at"].replace("Z", "+00:00"))
                        secs_left = (dl - _dt.now(dl.tzinfo)).total_seconds()
                        now_mono = asyncio.get_event_loop().time()
                        last = _match_nag_at.get(mid, 0.0)
                        if secs_left <= 90 and (now_mono - last) >= 300:
                            _match_nag_at[mid] = now_mono
                            if secs_left > 0:
                                msg = (f"⚠️ **{int(secs_left)} seconds left** to show up for your tournament match "
                                       f"— open ROUNDS immediately or you forfeit!")
                            else:
                                msg = ("⚠️ Your tournament match is **waiting on you** — you're marked present "
                                       "but the game hasn't started. Get to the ROUNDS main menu (leave any "
                                       "casual game) so the mod can connect you.")
                            await _dm_user(p1d, msg)
                            await _dm_user(p2d, msg)
                    except Exception as e:
                        print(f"[TOURNAMENT-POLL] nag parse: {e}")
                # Async 24h deadline warning (once per match).
                if kind == "async" and mid not in _notified_deadline_warn and m.get("deadline_at"):
                    try:
                        from datetime import datetime as _dt
                        dl = _dt.fromisoformat(m["deadline_at"].replace("Z", "+00:00"))
                        remaining = (dl - _dt.now(dl.tzinfo)).total_seconds()
                        if 0 < remaining <= 24 * 3600:
                            _notified_deadline_warn.add(mid)
                            await _dm_user(p1d, f"**24h deadline reminder**: your async match vs **{p2n}** must be played within {int(remaining/3600)}h or you forfeit.")
                            await _dm_user(p2d, f"**24h deadline reminder**: your async match vs **{p1n}** must be played within {int(remaining/3600)}h or you forfeit.")
                    except Exception as e:
                        print(f"[TOURNAMENT-POLL] deadline parse: {e}")
        # Completion: grant trophies + announce
        if status == "completed" and tid not in _notified_completed:
            _notified_completed.add(tid)
            await _grant_trophy(t, t.get("winner_signup_id"), TROPHY_ROLE_1)
            await _grant_trophy(t, t.get("runner_up_signup_id"), TROPHY_ROLE_2)
            await _grant_trophy(t, t.get("third_place_signup_id"), TROPHY_ROLE_3)
            await _grant_participant(t)
            # Build podium announcement
            name_for = {s["signup_id"]: s["display_name"] for s in t.get("signups", [])}
            winner = name_for.get(t.get("winner_signup_id"), "?")
            runner = name_for.get(t.get("runner_up_signup_id"), "?")
            third = name_for.get(t.get("third_place_signup_id"), "?")
            # Prize numbers come computed from the server (/internal/watch,
            # single source of truth — prizes scale with locked player count);
            # legacy tier text only as a fallback for a stale API.
            pg = t.get("prize_gold") or []
            px = t.get("prize_xp") or []
            pp = t.get("prize_players") or 0
            if len(pg) == 3 and len(px) == 3:
                prize_txt = (f"{pg[0]}g/{px[0]}xp · {pg[1]}g/{px[1]}xp · {pg[2]}g/{px[2]}xp "
                             f"at {pp} players + trophy roles")
            else:
                tier = t.get("prize_tier") or "none"
                prize_txt = {
                    "full": "500g / 300g / 60g + trophy roles",
                    "sixty": "300g / 180g / 36g + trophy roles",
                    "thirty": "150g / 90g / 18g + trophy roles",
                    "none": "(cancelled)",
                }.get(tier, tier)
            await _announce_in_channel(
                f"**Tournament complete.**  1st: **{winner}** · 2nd: {runner} · 3rd: {third}  ({prize_txt})"
            )


def _dm_opponent_rate_ok(discord_id):
    now = datetime.now(timezone.utc)
    window_start = now - _td(seconds=_DM_OPPONENT_WINDOW_SECS)
    q = _dm_opponent_history[discord_id]
    while q and q[0] < window_start:
        q.popleft()
    if len(q) >= _DM_OPPONENT_LIMIT:
        return False
    q.append(now)
    return True


def _find_active_opponent_discord_id(caller_discord_id):
    """Walk the cached watch payload, find the match where caller is p1 or p2
    with status 'ready' or 'active', return the opponent's discord_id + name."""
    cid = str(caller_discord_id)
    for t in _watch_cache.get("tournaments", []):
        if t.get("status") not in ("locked", "running"):
            continue
        for m in t.get("matches", []):
            # 'scheduled' included (July 17 round 2): the break window is
            # exactly when players use /dm-opponent to coordinate Play Now.
            if m.get("status") not in ("ready", "active", "pending", "scheduled"):
                continue
            p1d = str(m.get("p1_discord_id") or "")
            p2d = str(m.get("p2_discord_id") or "")
            if cid == p1d and p2d:
                return p2d, m.get("p2_name") or "opponent"
            if cid == p2d and p1d:
                return p1d, m.get("p1_name") or "opponent"
    return None, None


@bot.hybrid_command(name="opp-online", description="Check if your tournament opponent is online in Discord right now")
async def opp_online(ctx):
    opp_id, opp_name = _find_active_opponent_discord_id(str(ctx.author.id))
    if not opp_id:
        await ctx.reply("You're not in an active tournament match.", ephemeral=True)
        return
    if not _PRESENCE_ENABLED:
        await ctx.reply("Presence tracking isn't enabled on this bot — enable the Presence Intent in the "
                        "Discord dev portal and set `DISCORD_PRESENCE_INTENT=true` to use this command.",
                        ephemeral=True)
        return
    try:
        member = None
        for guild in bot.guilds:
            member = guild.get_member(int(opp_id))
            if member:
                break
        if member is None:
            await ctx.reply(f"{opp_name}: Discord presence unknown (not in guild cache).", ephemeral=True)
            return
        status = str(member.status)  # online|idle|dnd|offline
        icon = {"online": "🟢", "idle": "🟡", "dnd": "🔴"}.get(status, "⚫")
        label = {"online": "online", "idle": "idle", "dnd": "do not disturb"}.get(status, "offline")
        await ctx.reply(f"{icon} **{opp_name}** is currently **{label}** in Discord.", ephemeral=True)
    except Exception as e:
        await ctx.reply(f"Couldn't resolve presence: {e}", ephemeral=True)


@bot.hybrid_command(name="dm-opponent", description="DM your current tournament opponent (8/min)")
@app_commands.describe(message="Message to forward to your tournament opponent")
async def dm_opponent(ctx, *, message: str):
    caller_id = str(ctx.author.id)
    opp_id, opp_name = _find_active_opponent_discord_id(caller_id)
    if not opp_id:
        await ctx.reply("You're not in an active tournament match, or your opponent doesn't have Discord linked.", ephemeral=True)
        return
    if not _dm_opponent_rate_ok(caller_id):
        await ctx.reply(f"Rate limit: {_DM_OPPONENT_LIMIT} messages per {_DM_OPPONENT_WINDOW_SECS}s. Wait a moment.", ephemeral=True)
        return
    sender = getattr(ctx.author, "global_name", None) or ctx.author.name
    body = f"**[Tournament Relay from {sender}]** {message[:1500]}"
    ok = await _dm_user(opp_id, body)
    if ok:
        await ctx.reply(f"Relayed to {opp_name}.", ephemeral=True)
    else:
        await ctx.reply(f"Couldn't DM {opp_name} — they may have DMs closed.", ephemeral=True)


@tasks.loop(hours=24)
async def nag_pending_async_matches():
    """Once a day, DM players whose async tournament match has been 'ready'
    for more than 3 days without completing. Deduped by match_id + date so
    if the bot restarts on the same day, the same nag doesn't fire twice.
    Runs 24h cadence so players get at most a couple of nags over the 7-day
    deadline before the auto-forfeit fires."""
    if not _watch_cache:
        return
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    now = datetime.now(timezone.utc)
    nagged = 0
    for t in _watch_cache.get("tournaments", []):
        if t.get("kind") != "async" or t.get("status") != "running":
            continue
        for m in t.get("matches", []):
            if m.get("status") != "ready":
                continue
            mid = m["match_id"]
            # Only nag matches that have been ready > 3 days.
            started_ready = m.get("started_at") or m.get("ready_deadline_at")
            if not started_ready:
                continue
            try:
                ready_since = datetime.fromisoformat(started_ready.replace("Z", "+00:00"))
            except Exception:
                continue
            if (now - ready_since).total_seconds() < 3 * 86400:
                continue
            # Dedup per day
            if _notified_nag_date.get(mid) == today:
                continue
            _notified_nag_date[mid] = today
            p1d, p2d = m.get("p1_discord_id"), m.get("p2_discord_id")
            p1n = m.get("p1_name") or "opponent"
            p2n = m.get("p2_name") or "opponent"
            dl_str = _fmt_pt(m.get("deadline_at"))
            await _dm_user(p1d, f"**Async match still pending**: vs **{p2n}**. Deadline: {dl_str}. "
                                 f"Use `/dm-opponent` to coordinate a time.")
            await _dm_user(p2d, f"**Async match still pending**: vs **{p1n}**. Deadline: {dl_str}. "
                                 f"Use `/dm-opponent` to coordinate a time.")
            nagged += 1
            await asyncio.sleep(0.2)
    if nagged:
        print(f"[TOURNAMENT-NAG] Sent {nagged} pending-match reminders")


# ── Tournament availability-check DMs (v1.32) ─────────────────────────────
# The server queues availability_check notices (tournament_notices table) for
# signed-up players; this loop DMs each one a Yes/No prompt. Ack-after-
# delivery (learning #105): only successfully-DMed or permanently-
# undeliverable notices get acked, so a bot restart can't swallow one.
#
# The Yes/No buttons must survive bot restarts, so they are handled by the
# raw on_interaction listener below (matched by custom_id prefix "tavail:"),
# NOT by live View callbacks — a View object dies with the process, the
# custom_id in the message does not.

_tavail_seen_notice_ids = set()  # process-lifetime re-ack guard


def _unix_ts(v):
    """Coerce an epoch int/float, numeric string, or ISO-8601 string to unix
    seconds. None on anything unparseable — callers render '(time TBD)'."""
    if v is None:
        return None
    try:
        if isinstance(v, (int, float)):
            return int(v)
        s = str(v).strip()
        if not s:
            return None
        if s.replace(".", "", 1).isdigit():
            return int(float(s))
        return int(datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp())
    except Exception:
        return None


def _tavail_view(tournament_id, steam_id):
    """Buttons carry all state in the custom_id — no live callbacks, so the
    prompt keeps working after any number of bot restarts."""
    view = discord.ui.View(timeout=None)
    view.add_item(discord.ui.Button(style=discord.ButtonStyle.success, label="Yes, I'm in",
                                    custom_id=f"tavail:{tournament_id}:{steam_id}:yes"))
    view.add_item(discord.ui.Button(style=discord.ButtonStyle.danger, label="No, remove me",
                                    custom_id=f"tavail:{tournament_id}:{steam_id}:no"))
    return view


def _tavail_embed(kind, start_unix, lock_unix):
    if kind == "async":
        lock_str = f"<t:{lock_unix}:F>" if lock_unix else "(time TBD)"
        desc = (f"Signups close {lock_str}.\n\n"
                "Async matches are NOT played at a fixed time — each match has a "
                "7-day deadline and you schedule each game with your opponent "
                "whenever suits you both (use `/dm-opponent` to coordinate). "
                "No specific availability is required.")
        return discord.Embed(title="🌀 Async tournament — availability check", description=desc, color=0x5865F2)
    start_str = f"<t:{start_unix}:F>" if start_unix else "(time TBD)"
    lock_str = f"<t:{lock_unix}:F>" if lock_unix else "(time TBD)"
    # Wording contract (learning #130): "have ROUNDS open", never "be in the
    # tab". July 17 round 3: the DEFAULT time shown is provisional — the
    # final time is vote-decided at lock (>= 24h before play), so say so and
    # point at the vote.
    desc = (f"Default start: {start_str}\n"
            f"⏰ The FINAL time locks in {lock_str} — it'll be whichever voted "
            f"slot 8+ players agree on, always at least a day before play. "
            f"Make sure your available times are picked in F5 → Tournaments!\n\n"
            "All matches are played back-to-back in one sitting (~2 hours, "
            "short skippable breaks between your matches). You only need "
            "ROUNDS open at the main menu at the start time — the mod "
            "auto-connects you to each match.")
    return discord.Embed(title="🏆 Synchronized tournament — availability check", description=desc, color=0xFAA61A)


async def _ack_tournament_notices(notice_ids):
    if not notice_ids or http_session is None or not API_SECRET_KEY:
        return
    try:
        async with http_session.post(
            f"{API_BASE_URL}/api/v1/internal/tournament-notices/ack",
            json={"notice_ids": list(notice_ids)},
            headers={"X-Internal-Key": API_SECRET_KEY},
            timeout=aiohttp.ClientTimeout(total=8),
        ) as resp:
            if resp.status != 200:
                print(f"[TAVAIL] ack failed: {resp.status} {(await resp.text())[:120]}")
    except Exception as ex:
        print(f"[TAVAIL] ack error: {ex}")


@tasks.loop(seconds=30)
async def poll_tournament_notices():
    """Own fully-guarded loop (learning #129 — never chained onto
    poll_tournaments' tail)."""
    try:
        data = await api_get("/internal/tournament-notices?unnotified=true")
        if not data or not data.get("notices"):
            return
        to_ack = []
        for n in data["notices"]:
            if not isinstance(n, dict):
                continue
            # Server serializes the pk as "notice_id" (main.py tournament-notices
            # endpoint); tolerate "id" too in case the shape ever changes.
            nid = n.get("notice_id") or n.get("id")
            if nid is None:
                continue
            if nid in _tavail_seen_notice_ids:
                # Handled this process-lifetime — earlier ack must have failed;
                # re-ack, don't re-DM.
                to_ack.append(nid)
                continue
            if (n.get("notice_type") or "") != "availability_check":
                # Unknown notice type — nothing this bot build can send; ack so
                # it doesn't come back every 30s forever.
                _tavail_seen_notice_ids.add(nid)
                to_ack.append(nid)
                continue
            did = n.get("discord_id")
            tid = n.get("tournament_id")
            steam = n.get("steam_id")
            if not did or not tid or not steam:
                # Unlinked player / malformed row — permanently undeliverable.
                _tavail_seen_notice_ids.add(nid)
                to_ack.append(nid)
                continue
            # payload is a JSON string per the contract; tolerate a dict too.
            payload = {}
            raw = n.get("payload")
            try:
                if isinstance(raw, str) and raw:
                    payload = json.loads(raw)
                elif isinstance(raw, dict):
                    payload = raw
            except Exception:
                payload = {}
            kind = (n.get("kind") or payload.get("kind") or "sync").lower()
            start_unix = (_unix_ts(payload.get("start_ts"))
                          or _unix_ts(n.get("scheduled_start_ts"))
                          or _unix_ts(n.get("default_start_ts")))
            lock_unix = _unix_ts(payload.get("lock_ts")) or _unix_ts(n.get("lock_at"))
            if kind == "async":
                content = "Are you still in for the **Async tournament**?"
            else:
                content = "Are you still available to play in the **Synchronized tournament**?"
            embed = _tavail_embed(kind, start_unix, lock_unix)
            view = _tavail_view(tid, steam)
            # Resolve + DM. Transient resolution failure → no ack (retried).
            try:
                user = bot.get_user(int(did)) or await bot.fetch_user(int(did))
            except discord.NotFound:
                _tavail_seen_notice_ids.add(nid)
                to_ack.append(nid)
                continue
            except Exception as ex:
                print(f"[TAVAIL] fetch_user({did}) failed: {ex}")
                continue
            if user is None:
                continue
            try:
                await user.send(content=content, embed=embed, view=view)
                print(f"[TAVAIL] availability check ({kind}) → {user} for tournament {str(tid)[:8]}")
                _tavail_seen_notice_ids.add(nid)
                to_ack.append(nid)
            except discord.Forbidden:
                # DMs closed — permanently undeliverable; ack.
                print(f"[TAVAIL] {did} has DMs closed — acking")
                _tavail_seen_notice_ids.add(nid)
                to_ack.append(nid)
            except Exception as ex:
                # Transient (rate limit / gateway blip) — no ack, retried next poll.
                print(f"[TAVAIL] DM to {did} failed: {ex}")
            await asyncio.sleep(0.15)
        if len(_tavail_seen_notice_ids) > 2000:
            _tavail_seen_notice_ids.clear()
        await _ack_tournament_notices(to_ack)
    except Exception as ex:
        print(f"poll_tournament_notices error: {ex}")


@poll_tournament_notices.before_loop
async def before_tournament_notices():
    await bot.wait_until_ready()


# ── Generic one-off DM queue (pending_dms, migration 129) ──────────────────
# Rows are inserted by migrations/admin SQL; this loop DMs the linked player.
# Durable ack pattern (learning #105); the server serializes the pk as
# "dm_id" and this reads the same key (learning #152).
_pdm_seen_ids: set = set()


async def _ack_pending_dms(dm_ids, undeliverable=False):
    if not dm_ids or http_session is None or not API_SECRET_KEY:
        return
    try:
        async with http_session.post(
            f"{API_BASE_URL}/api/v1/internal/pending-dms/ack",
            json={"dm_ids": list(dm_ids), "undeliverable": bool(undeliverable)},
            headers={"X-Internal-Key": API_SECRET_KEY},
            timeout=aiohttp.ClientTimeout(total=8),
        ) as resp:
            if resp.status != 200:
                print(f"[PDM] ack failed: {resp.status} {(await resp.text())[:120]}")
    except Exception as ex:
        print(f"[PDM] ack error: {ex}")


@tasks.loop(seconds=60)
async def poll_pending_dms():
    """Own fully-guarded loop (learning #129)."""
    try:
        data = await api_get("/internal/pending-dms")
        if not data or not data.get("dms"):
            return
        delivered, dead = [], []
        for d in data["dms"]:
            if not isinstance(d, dict):
                continue
            did_key = d.get("dm_id")
            if did_key is None:
                continue
            if did_key in _pdm_seen_ids:
                # Handled this process-lifetime — earlier ack must have
                # failed; re-ack, don't re-DM.
                delivered.append(did_key)
                continue
            discord_id = d.get("discord_id")
            content = (d.get("content") or "").strip()
            if not discord_id or not content:
                # Unlinked player / empty row — permanently undeliverable.
                _pdm_seen_ids.add(did_key)
                dead.append(did_key)
                continue
            # Unparseable discord_id = permanently undeliverable — without
            # this, one bad row at the head of the created_at ASC LIMIT 20
            # window would starve the whole queue forever (the poll would
            # refetch it every 60s and never ack).
            try:
                did_int = int(discord_id)
            except (TypeError, ValueError):
                print(f"[PDM] bad discord_id {discord_id!r} — flagging undeliverable")
                _pdm_seen_ids.add(did_key)
                dead.append(did_key)
                continue
            try:
                user = bot.get_user(did_int) or await bot.fetch_user(did_int)
            except discord.NotFound:
                _pdm_seen_ids.add(did_key)
                dead.append(did_key)
                continue
            except Exception as ex:
                print(f"[PDM] fetch_user({discord_id}) failed: {ex}")
                continue
            if user is None:
                continue
            try:
                await user.send(content[:2000])
                print(f"[PDM] dm {did_key} → {user} ({d.get('display_name') or d.get('steam_id')})")
                _pdm_seen_ids.add(did_key)
                delivered.append(did_key)
            except discord.Forbidden:
                print(f"[PDM] {discord_id} has DMs closed — flagging undeliverable")
                _pdm_seen_ids.add(did_key)
                dead.append(did_key)
            except Exception as ex:
                # Transient (rate limit / gateway blip) — no ack, retried next poll.
                print(f"[PDM] DM to {discord_id} failed: {ex}")
            await asyncio.sleep(0.15)
        if len(_pdm_seen_ids) > 2000:
            _pdm_seen_ids.clear()
        await _ack_pending_dms(delivered, undeliverable=False)
        await _ack_pending_dms(dead, undeliverable=True)
    except Exception as ex:
        print(f"poll_pending_dms error: {ex}")


# ── LFP role pings (lfp_pings, July 21) ─────────────────────────────────────
# The in-game "LFP Ping" button POSTs /lfp-ping; this loop posts the queued
# rows to the queue-beacon channel with a ping to the LFP role. Durable ack
# pattern (learning #105); the server serializes the pk as "ping_id" and a
# precomputed "expires_unix" — this reads the exact same keys (learning
# #152). Own fully-guarded loop (learning #129): one bad row / one Discord
# hiccup can never kill the loop or another output.
_lfp_seen_ids: set = set()


async def _ack_lfp_pings(ping_ids, undeliverable=False):
    if not ping_ids or http_session is None or not API_SECRET_KEY:
        return
    try:
        async with http_session.post(
            f"{API_BASE_URL}/api/v1/internal/lfp-pings/ack",
            json={"ping_ids": list(ping_ids), "undeliverable": bool(undeliverable)},
            headers={"X-Internal-Key": API_SECRET_KEY},
            timeout=aiohttp.ClientTimeout(total=8),
        ) as resp:
            if resp.status != 200:
                print(f"[LFP] ack failed: {resp.status} {(await resp.text())[:120]}")
    except Exception as ex:
        print(f"[LFP] ack error: {ex}")


@tasks.loop(seconds=30)
async def poll_lfp_pings():
    """Own fully-guarded loop (learning #129)."""
    try:
        if not QUEUE_BEACON_CHANNEL_ID:
            return
        data = await api_get("/internal/lfp-pings")
        if not data or not data.get("pings"):
            return
        posted, dead = [], []
        channel = None
        for ping in data["pings"]:
            if not isinstance(ping, dict):
                continue
            ping_id = ping.get("ping_id")
            if ping_id is None:
                continue
            if ping_id in _lfp_seen_ids:
                # Handled this process-lifetime — an earlier ack must have
                # failed; re-ack, don't re-post.
                posted.append(ping_id)
                continue
            discord_id = ping.get("discord_id")
            if not discord_id:
                # Unlinked player (the POST gate normally blocks this) —
                # permanently undeliverable so the LIMIT-20 window can't starve.
                _lfp_seen_ids.add(ping_id)
                dead.append(ping_id)
                continue
            if channel is None:
                channel = bot.get_channel(QUEUE_BEACON_CHANNEL_ID)
                if not channel:
                    try:
                        channel = await bot.fetch_channel(QUEUE_BEACON_CHANNEL_ID)
                    except Exception as ex:
                        # Channel unavailable — leave everything queued; the
                        # server's expires_at filter self-heals stale rows.
                        print(f"[LFP] channel {QUEUE_BEACON_CHANNEL_ID} unavailable: {ex}")
                        break
            role = discord.utils.get(channel.guild.roles, name=LFP_ROLE_NAME) if channel.guild else None
            mention = role.mention if role else f"@{LFP_ROLE_NAME}"
            display_name = ping.get("display_name") or ping.get("steam_id") or "Player"
            message = (ping.get("message") or "").strip()
            expires_unix = int(ping.get("expires_unix") or 0)
            content = (f"{mention} \N{LEFT-POINTING MAGNIFYING GLASS} "
                       f"**{discord.utils.escape_markdown(str(display_name))}** "
                       f"(<@{discord_id}>) is looking for a ranked match!")
            if message:
                content += f"\n> {discord.utils.escape_markdown(message)}"
            content += f"\nExpires <t:{expires_unix}:R>"
            try:
                # allowed_mentions is the real anti-injection gate: ONLY the
                # LFP role pings; the requester's <@id> renders clickable
                # without pinging; injected mention text in the message is
                # inert. suppress_embeds keeps any link-shaped text that
                # survives the server-side sanitizer from unfurling a rich
                # embed under the trusted bot account.
                await channel.send(
                    content[:2000],
                    suppress_embeds=True,
                    allowed_mentions=discord.AllowedMentions(
                        everyone=False, roles=[role] if role else False, users=False),
                )
                _lfp_seen_ids.add(ping_id)
                posted.append(ping_id)
                print(f"[LFP] posted ping {ping_id} for {display_name}")
            except discord.Forbidden:
                # No send permission — log and leave queued (retried next
                # tick; expires_at filter self-heals).
                print(f"[LFP] Forbidden posting ping {ping_id} to {QUEUE_BEACON_CHANNEL_ID} — leaving queued")
            except Exception as ex:
                # Transient (rate limit / gateway blip) — no ack, retried.
                print(f"[LFP] post failed for ping {ping_id}: {ex}")
            await asyncio.sleep(0.2)
        if len(_lfp_seen_ids) > 2000:
            # Overflow prune must RETAIN this tick's ids: an unconditional
            # clear() drops posted-but-unacked ids, so if the ack below then
            # fails the server re-serves them next tick and they'd re-post as
            # duplicate role pings. Every re-servable id is in this tick's
            # posted/dead lists (a prior-tick failed ack is re-served and
            # re-appended to posted above), so intersecting bounds the set
            # without evicting anything at risk.
            _lfp_seen_ids.intersection_update(set(posted) | set(dead))
        await _ack_lfp_pings(posted, undeliverable=False)
        await _ack_lfp_pings(dead, undeliverable=True)
    except Exception as ex:
        print(f"poll_lfp_pings error: {ex}")


@poll_lfp_pings.before_loop
async def before_lfp_pings():
    await bot.wait_until_ready()


@poll_pending_dms.before_loop
async def before_pending_dms():
    await bot.wait_until_ready()


async def _tournament_unsignup(tournament_id, steam_id):
    """POST the same public unsignup endpoint the game client uses
    (tournaments.py:1289; TournamentSignupRequest = {steam_id}). JSON body —
    api_post sends query params, wrong for this endpoint. Returns (ok, detail)."""
    if http_session is None:
        return False, "backend unreachable"
    try:
        async with http_session.post(
            f"{API_BASE_URL}/api/v1/tournaments/{tournament_id}/unsignup",
            json={"steam_id": str(steam_id)},
            timeout=aiohttp.ClientTimeout(total=10),
        ) as resp:
            if resp.status == 200:
                return True, ""
            txt = await resp.text()
            try:
                detail = json.loads(txt).get("detail") or txt
            except Exception:
                detail = txt
            return False, str(detail)[:300]
    except Exception as ex:
        return False, f"request failed: {ex}"


@bot.event
async def on_interaction(interaction: discord.Interaction):
    """Raw component listener for the availability-check Yes/No buttons.
    Deliberately NOT a View callback: the DM can be answered days later,
    across any number of bot restarts — only the custom_id persists. All
    other component interactions (live bets, paginator) are handled by their
    own Views and fall through the prefix check untouched."""
    try:
        if interaction.type != discord.InteractionType.component:
            return
        cid = (interaction.data or {}).get("custom_id", "")
        if not cid.startswith("tavail:"):
            return
        parts = cid.split(":")
        if len(parts) != 4:
            await interaction.response.send_message("⚠️ Unrecognized button.", ephemeral=True)
            return
        _, tournament_id, steam_id, answer = parts
        if answer == "yes":
            # Acknowledge within 3s by editing the prompt in place.
            await interaction.response.edit_message(content="Confirmed — see you there! ✅", view=None)
            print(f"[TAVAIL] {interaction.user} confirmed for tournament {tournament_id[:8]}")
            return
        # "no": the unsignup POST can take a moment — defer first (must ack
        # the interaction within 3s), then edit/follow-up.
        await interaction.response.defer()
        ok, detail = await _tournament_unsignup(tournament_id, steam_id)
        if ok:
            print(f"[TAVAIL] {interaction.user} withdrew from tournament {tournament_id[:8]}")
            try:
                await interaction.message.edit(content="You've been removed from the tournament. ✅", view=None)
            except Exception:
                await interaction.followup.send("You've been removed from the tournament. ✅")
        else:
            # e.g. tournament already running — leave the buttons so they can
            # see the prompt; surface the server's reason.
            await interaction.followup.send(f"❌ Couldn't remove you: {detail}")
    except Exception as ex:
        print(f"[TAVAIL] interaction error: {ex}")


# ── Tournament board in #scr-tournaments (v1.32) ──────────────────────────
# ONE living message with up to two embeds (sync + async), mirroring the
# in-game Tournaments tab pages. Living-board pattern per learning #140:
# remembered message id, fast-path edit, bottom-anchor delete+repost when
# buried, duplicate rescan by embed title, live `Updated <t:R>` in the body.
# Fed from _watch_cache (poll_tournaments refreshes it every 30s); falls back
# to a direct /internal/watch fetch when the cache is cold (e.g. right after
# a restart, before poll_tournaments' first tick).

_tournament_board_ids: dict = {}  # channel_id -> message_id

_BRACKET_SIDE_LABEL = {"W": "WB", "L": "LB", "GF": "Grand Final", "GF_RESET": "GF Reset", "TP": "3rd Place"}
_BRACKET_SIDE_ORDER = {"W": 0, "L": 1, "GF": 2, "GF_RESET": 3, "TP": 4}


def _bracket_progress_lines(t, max_lines=28):
    """Per-round match lines for a running tournament. The watch payload has
    names + winner + status; per-match series SCORES aren't in it today —
    render 'Alice 2-1 Bob' when a p1_score/p2_score pair is present
    (defensive .get), else fall back to 'Alice def. Bob' / 'Alice vs Bob'."""
    out = []
    matches = t.get("matches") or []

    def keyf(m):
        return (_BRACKET_SIDE_ORDER.get(m.get("bracket_side"), 9),
                m.get("round") or 0, m.get("slot_idx") or 0)

    for m in sorted([m for m in matches if isinstance(m, dict)], key=keyf):
        side_raw = m.get("bracket_side")
        side = _BRACKET_SIDE_LABEL.get(side_raw, side_raw or "?")
        hdr = f"{side} R{m.get('round')}" if side_raw in ("W", "L") else side
        p1 = m.get("p1_name") or "TBD"
        p2 = m.get("p2_name") or "TBD"
        st = m.get("status")
        s1, s2 = m.get("p1_score"), m.get("p2_score")
        if st in ("completed", "forfeit", "double_forfeit", "bye_auto"):
            win_id = m.get("winner_signup_id")
            if win_id and win_id == m.get("p1_signup_id"):
                w, l, ws, ls = p1, p2, s1, s2
            elif win_id and win_id == m.get("p2_signup_id"):
                w, l, ws, ls = p2, p1, s2, s1
            else:
                w = l = ws = ls = None
            if w is None:
                body = f"{p1} vs {p2} — {st.replace('_', ' ')}"
            elif ws is not None and ls is not None:
                body = f"**{w}** {ws}-{ls} {l}"
            elif st == "bye_auto":
                body = f"**{w}** — bye"
            elif st in ("forfeit", "double_forfeit"):
                body = f"**{w}** def. {l} (forfeit)"
            else:
                body = f"**{w}** def. {l}"
        elif st == "active":
            body = f"{p1} vs {p2} — 🎮 in progress"
        elif st == "ready":
            body = f"{p1} vs {p2} — ⏳ waiting to start"
        else:
            if p1 == "TBD" and p2 == "TBD":
                continue  # fully-unresolved future match — noise
            body = f"{p1} vs {p2} — upcoming"
        out.append(f"`{hdr}` {body}")
    if len(out) > max_lines:
        out = out[:max_lines] + [f"…and {len(out) - max_lines} more matches"]
    return out


# "How it works" blurb per tournament kind (Sid: board postings must explain
# sync vs async). Rendered as an embed FIELD on every board embed — field
# values have their own 1024-char cap and don't eat the description's 2600
# budget, so live status always stays on top. They DO count against the
# 6000-char whole-message total, which is why the description cap below is
# 2600 and not 2900.
_TOURNEY_HOW_IT_WORKS = {
    "sync": (
        "Weekly bracket played in ONE sitting. Sign up in-game "
        "(F5 → Tournaments), vote on the start time, then just have ROUNDS "
        "open at the main menu when it starts — the mod auto-connects you to "
        "each match. Miss your ready window and you forfeit that match."
    ),
    "async": (
        "No fixed play time. Sign up in-game (F5 → Tournaments); when signups "
        "close the bracket starts and each match gets a 7-DAY deadline — you "
        "schedule each game with your opponent whenever suits you both "
        "(use `/dm-opponent`). No specific availability needed."
    ),
}


def _build_tournament_board_embed(t, kind: str) -> discord.Embed:
    """One embed per tournament kind, mirroring the in-game Sync/Async page."""
    kind_label = "Sync" if kind == "sync" else "Async"
    emoji = "🏆" if kind == "sync" else "🌀"
    title = f"{emoji} {kind_label} Tournament"
    updated = f"Updated <t:{int(datetime.now(timezone.utc).timestamp())}:R>\n\n"
    if not t:
        em = discord.Embed(
            title=title,
            description=updated + f"No active {kind_label.lower()} tournament — next one is created automatically.",
            color=0x36393F,
        )
        em.add_field(name="ℹ️ How it works", value=_TOURNEY_HOW_IT_WORKS[kind], inline=False)
        return em
    status = t.get("status") or "?"
    all_signups = [s for s in (t.get("signups") or []) if isinstance(s, dict)]
    signups = [s for s in all_signups if not s.get("is_speculative")]
    spec_count = len(all_signups) - len(signups)
    lines = []
    if status == "voting":
        lines.append("**Status: Signups open**")
        min_p = t.get("min_players") or 8
        max_p = t.get("max_players") or 16
        lines.append(f"Signed up: **{len(signups)}** (min {min_p}, max {max_p})"
                     + (f" · +{spec_count} waitlist" if spec_count else ""))
        if kind == "sync":
            lines.append(f"Default start: {_fmt_pt(t.get('scheduled_start_ts') or t.get('default_start_ts'))}")
            lines.append(f"Signups + time voting close: {_fmt_pt(t.get('lock_at'))}")
            lines.append("_Start-time voting is open in-game (F5 → Tournaments)._")
        else:
            lines.append(f"Signups close: {_fmt_pt(t.get('lock_at'))} — the bracket starts then; "
                         f"each match has a 7-day deadline.")
    elif status == "locked":
        lines.append(f"**Status: Locked** — starts {_fmt_pt(t.get('scheduled_start_ts'))}")
        lines.append(f"Players: **{len(signups)}**")
    elif status == "running":
        lines.append("**Status: Running**")
        lines.extend(_bracket_progress_lines(t))
    elif status == "completed":
        lines.append("**Status: Completed**")
        name_for = {s.get("signup_id"): s.get("display_name") for s in all_signups}
        podium = [("🥇", name_for.get(t.get("winner_signup_id"))),
                  ("🥈", name_for.get(t.get("runner_up_signup_id"))),
                  ("🥉", name_for.get(t.get("third_place_signup_id")))]
        for medal, nm in podium:
            if nm:
                lines.append(f"{medal} **{nm}**" if medal == "🥇" else f"{medal} {nm}")
    else:
        lines.append(f"**Status: {status}**")
    # Prize line (item 2, July 17 round 2): prizes scale with player count —
    # server-computed numbers, plus the growth hook while signups are open.
    _pg = t.get("prize_gold") or []
    _px = t.get("prize_xp") or []
    # Amounts are already floored at the 8-player base server-side; floor the
    # DISPLAYED count too so early voting never reads "Prizes at 2 players".
    _pp = max(8, t.get("prize_players") or 0)
    if status in ("voting", "locked", "running") and len(_pg) == 3 and len(_px) == 3:
        lines.append(f"💰 **Prizes at {_pp} players:** "
                     f"🥇 {_pg[0]}g/{_px[0]}xp · 🥈 {_pg[1]}g/{_px[1]}xp · 🥉 {_pg[2]}g/{_px[2]}xp")
        if status == "voting":
            lines.append("Every signup past 8 grows the pot — 16 players doubles it!")
    # Roster (skip on completed — the podium tells the story). Seeds when
    # locked/running (the watch payload doesn't carry them today — defensive
    # .get so they appear the moment the server adds them), ready ✓ likewise.
    if status in ("voting", "locked", "running") and signups:
        roster = []
        for s in signups:
            nm = s.get("display_name") or "?"
            bits = ""
            if status != "voting" and s.get("seed"):
                bits += f" (seed {s['seed']})"
            if s.get("ready"):
                bits += " ✓"
            if s.get("forfeited"):
                bits += " ✗ forfeited"
            roster.append(f"• {nm}{bits}")
        shown = roster[:24]
        if len(roster) > 24:
            shown.append(f"…and {len(roster) - 24} more")
        lines.append("")
        lines.append("**Players**")
        lines.extend(shown)
    desc = updated + "\n".join(lines)
    # Two embeds share ONE message's 6000-char total budget (Discord counts
    # across all embeds, fields included), so each description gets 2600 —
    # not the 4096 single-embed cap. 2×2600 desc + 2×(~290-char "How it
    # works" field + name) + titles ≈ 5.8k, safely under 6000; at 2900 the
    # fields would have pushed a worst-case edit over the cap and the board
    # would silently freeze on a 400.
    if len(desc) > 2600:
        desc = desc[:2580] + "\n…"
    color = {"voting": 0x3BA55D, "locked": 0xFAA61A,
             "running": 0x5865F2, "completed": 0x9B59B6}.get(status, 0x36393F)
    em = discord.Embed(title=title, description=desc, color=color)
    em.add_field(name="ℹ️ How it works", value=_TOURNEY_HOW_IT_WORKS[kind], inline=False)
    return em


async def _publish_tournament_board():
    if not SCR_TOURNAMENTS_CHANNEL:
        return
    ch = bot.get_channel(SCR_TOURNAMENTS_CHANNEL)
    if not ch:
        try:
            ch = await bot.fetch_channel(SCR_TOURNAMENTS_CHANNEL)
        except Exception as e:
            print(f"[TBOARD] channel {SCR_TOURNAMENTS_CHANNEL} unreachable: {e}")
            return
    tournaments = (_watch_cache or {}).get("tournaments") or []
    if not tournaments and http_session is not None and API_SECRET_KEY:
        # Cold cache (fresh restart, before poll_tournaments' first tick) is
        # indistinguishable from "no tournaments" — fetch directly to be sure.
        try:
            async with http_session.get(
                f"{API_BASE_URL}/api/v1/tournaments/internal/watch",
                headers={"X-Internal-Key": API_SECRET_KEY},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status == 200:
                    tournaments = (await resp.json()).get("tournaments") or []
        except Exception as e:
            print(f"[TBOARD] direct watch fetch failed: {e}")

    def pick(kind):
        # At most one active tournament per kind exists; prefer it, else show
        # the most recent completed one (watch keeps them 24h).
        active = [t for t in tournaments
                  if t.get("kind") == kind and t.get("status") in ("voting", "locked", "running")]
        if active:
            return active[0]
        done = [t for t in tournaments if t.get("kind") == kind and t.get("status") == "completed"]
        return done[-1] if done else None

    embeds = [
        _build_tournament_board_embed(pick("sync"), "sync"),
        _build_tournament_board_embed(pick("async"), "async"),
    ]
    # Living-message management — same shape as publish_lb.
    mid = _tournament_board_ids.get(ch.id)
    if mid:
        try:
            msg = await ch.fetch_message(mid)
            if getattr(ch, "last_message_id", None) not in (None, mid):
                try:
                    await msg.delete()
                except Exception:
                    pass
                sent = await ch.send(embeds=embeds)
                _tournament_board_ids[ch.id] = sent.id
                print(f"[TBOARD] board was buried — reposted at bottom as mid={sent.id}")
                return
            await msg.edit(embeds=embeds)
            print(f"[TBOARD] edited board mid={mid}")
            return
        except Exception as e:
            print(f"[TBOARD] fast-path edit of mid={mid} failed ({e}) — rescanning")
            _tournament_board_ids.pop(ch.id, None)
    # Rescan: adopt the newest board message, delete older duplicates.
    keeper = None
    dupes = 0
    async for msg in ch.history(limit=50):
        if msg.author == bot.user and msg.embeds and (msg.embeds[0].title or "").endswith("Tournament"):
            if keeper is None:
                keeper = msg
            else:
                try:
                    await msg.delete()
                    dupes += 1
                except Exception as e:
                    print(f"[TBOARD] couldn't delete duplicate board mid={msg.id}: {e}")
    if dupes:
        print(f"[TBOARD] deleted {dupes} duplicate board message(s)")
    if keeper is not None:
        if getattr(ch, "last_message_id", None) not in (None, keeper.id):
            try:
                await keeper.delete()
            except Exception:
                pass
            sent = await ch.send(embeds=embeds)
            _tournament_board_ids[ch.id] = sent.id
            print(f"[TBOARD] re-anchored board was buried — reposted at bottom as mid={sent.id}")
            return
        _tournament_board_ids[ch.id] = keeper.id
        try:
            await keeper.edit(embeds=embeds)
            print(f"[TBOARD] re-anchored to board mid={keeper.id} and edited")
        except Exception as e:
            print(f"[TBOARD] re-anchor edit of mid={keeper.id} failed: {e}")
        return
    sent = await ch.send(embeds=embeds)
    _tournament_board_ids[ch.id] = sent.id
    print(f"[TBOARD] posted fresh tournament board in {ch.id}")


@tasks.loop(seconds=120)
async def publish_tournament_board():
    """Own fully-guarded loop (learning #129) — one bad tick never kills it."""
    try:
        await _publish_tournament_board()
    except Exception as e:
        print(f"[TBOARD] publish error: {e}")


@publish_tournament_board.before_loop
async def before_tournament_board():
    await bot.wait_until_ready()


# ── Live Ranked Games + Discord betting ─────────────────────────────
# Posts/updates a message per active 1v1 ranked series in LIVE_BETS_CHANNEL.
# Bet buttons fire /api/v1/discord-bets which requires the user's Discord
# account to be linked via !link first. Mirrors the in-game live-bets panel
# but visible to anyone in the Discord (no mod required to bet).
live_bet_messages = {}  # series_id -> message_id (in LIVE_BETS_CHANNEL)
LIVE_BET_AMOUNTS = (100, 500, 2000)

class LiveBetView(discord.ui.View):
    def __init__(self, series_id: str, p1_steam: str, p1_name: str,
                 p2_steam: str, p2_name: str):
        super().__init__(timeout=None)
        self.series_id = series_id
        self.p1_steam = p1_steam
        self.p1_name = p1_name
        self.p2_steam = p2_steam
        self.p2_name = p2_name
        # 8 buttons: (3 preset amounts + custom) × 2 players, in three rows.
        for amt in LIVE_BET_AMOUNTS:
            self.add_item(LiveBetButton(self, amt, on_p1=True))
        for amt in LIVE_BET_AMOUNTS:
            self.add_item(LiveBetButton(self, amt, on_p1=False))
        self.add_item(LiveBetCustomButton(self, on_p1=True))
        self.add_item(LiveBetCustomButton(self, on_p1=False))

class LiveBetButton(discord.ui.Button):
    def __init__(self, parent: LiveBetView, amount: int, on_p1: bool):
        side_label = parent.p1_name if on_p1 else parent.p2_name
        # Truncate aggressive — Discord buttons cap at 80 chars but rendering
        # gets cramped above ~24.
        label = f"{amount:,}g {side_label[:14]}"
        style = discord.ButtonStyle.primary if on_p1 else discord.ButtonStyle.success
        row = 0 if on_p1 else 1
        super().__init__(label=label, style=style, row=row,
                         custom_id=f"livebet:{parent.series_id}:{amount}:{'p1' if on_p1 else 'p2'}")
        self.parent_view = parent
        self.amount = amount
        self.on_p1 = on_p1

    async def callback(self, interaction: discord.Interaction):
        bet_on_steam = self.parent_view.p1_steam if self.on_p1 else self.parent_view.p2_steam
        side_name = self.parent_view.p1_name if self.on_p1 else self.parent_view.p2_name
        vs_name = self.parent_view.p2_name if self.on_p1 else self.parent_view.p1_name
        try:
            result = await api_post(
                "/discord-bets",
                params={
                    "discord_user_id": str(interaction.user.id),
                    "series_id": self.parent_view.series_id,
                    "bet_on_steam_id": bet_on_steam,
                    "amount": self.amount,
                },
            )
        except Exception as e:
            await interaction.response.send_message(f"Bet failed: {e}", ephemeral=True)
            return
        if not result:
            await interaction.response.send_message("Bet failed: backend unreachable.", ephemeral=True)
            return
        if isinstance(result, dict) and "error" in result:
            err = result.get("error", "")
            # Surface the server's reason verbatim (e.g. "not linked", "insufficient gold",
            # "bets locked", "already bet on this series").
            try:
                err_obj = json.loads(err)
                msg = err_obj.get("detail") or err
            except Exception:
                msg = err
            await interaction.response.send_message(f"❌ {msg}", ephemeral=True)
            return
        # Name the MATCHUP, not just the side — a player can have two live
        # series (a stalled one + the one everyone's watching) and bettors
        # need to know which pairing their gold landed on (bug #53).
        await interaction.response.send_message(
            f"✅ Bet placed: **{self.amount:,}g** on **{side_name}** (vs {vs_name}, series `{self.parent_view.series_id[:8]}`).",
            ephemeral=True,
        )


async def _place_discord_bet(interaction: discord.Interaction, series_id: str,
                             bet_on_steam: str, side_name: str, amount: int,
                             vs_name: str = ""):
    """Shared bet-placement path for preset buttons + the custom modal."""
    try:
        result = await api_post(
            "/discord-bets",
            params={
                "discord_user_id": str(interaction.user.id),
                "series_id": series_id,
                "bet_on_steam_id": bet_on_steam,
                "amount": amount,
            },
        )
    except Exception as e:
        await interaction.response.send_message(f"Bet failed: {e}", ephemeral=True)
        return
    if not result:
        await interaction.response.send_message("Bet failed: backend unreachable.", ephemeral=True)
        return
    if isinstance(result, dict) and "error" in result:
        err = result.get("error", "")
        try:
            err_obj = json.loads(err)
            msg = err_obj.get("detail") or err
        except Exception:
            msg = err
        await interaction.response.send_message(f"❌ {msg}", ephemeral=True)
        return
    vs_part = f" (vs {vs_name}, series `{series_id[:8]}`)" if vs_name else f" (series `{series_id[:8]}`)"
    await interaction.response.send_message(
        f"✅ Bet placed: **{amount:,}g** on **{side_name}**{vs_part}.",
        ephemeral=True,
    )


class LiveBetCustomButton(discord.ui.Button):
    """v1.29: opens a modal for an arbitrary bet amount (1 – 100,000g)."""
    def __init__(self, parent: LiveBetView, on_p1: bool):
        side_label = parent.p1_name if on_p1 else parent.p2_name
        style = discord.ButtonStyle.primary if on_p1 else discord.ButtonStyle.success
        super().__init__(label=f"Custom on {side_label[:12]}...", style=style, row=2,
                         custom_id=f"livebetc:{parent.series_id}:{'p1' if on_p1 else 'p2'}")
        self.parent_view = parent
        self.on_p1 = on_p1

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(LiveBetModal(self.parent_view, self.on_p1))


class LiveBetModal(discord.ui.Modal):
    def __init__(self, parent: LiveBetView, on_p1: bool):
        side = parent.p1_name if on_p1 else parent.p2_name
        super().__init__(title=f"Bet on {side[:38]}")
        self.parent_view = parent
        self.on_p1 = on_p1
        self.amount_input = discord.ui.TextInput(
            label="Gold amount (1 - 2,000)",
            placeholder="e.g. 1250",
            min_length=1, max_length=5, required=True,
        )
        self.add_item(self.amount_input)

    async def on_submit(self, interaction: discord.Interaction):
        raw = (self.amount_input.value or "").replace(",", "").replace(".", "").strip()
        try:
            amount = int(raw)
        except ValueError:
            await interaction.response.send_message("❌ Enter a whole number of gold, e.g. `1250`.", ephemeral=True)
            return
        if amount < 1 or amount > 2000:
            await interaction.response.send_message("❌ Bet must be between 1 and 2,000 gold.", ephemeral=True)
            return
        bet_on_steam = self.parent_view.p1_steam if self.on_p1 else self.parent_view.p2_steam
        side_name = self.parent_view.p1_name if self.on_p1 else self.parent_view.p2_name
        vs_name = self.parent_view.p2_name if self.on_p1 else self.parent_view.p1_name
        await _place_discord_bet(interaction, self.parent_view.series_id, bet_on_steam, side_name, amount, vs_name)


def _format_live_bet_embed(s: dict) -> discord.Embed:
    p1n = s.get("p1_name", "?"); p2n = s.get("p2_name", "?")
    p1r = s.get("p1_rating", 1500); p2r = s.get("p2_rating", 1500)
    p1o = s.get("p1_odds", 1.01);   p2o = s.get("p2_odds", 1.01)
    p1w = s.get("p1_wins", 0);      p2w = s.get("p2_wins", 0)
    locked = s.get("bets_locked", False)
    reason = s.get("lock_reason")
    is_tournament = s.get("is_tournament", False)
    tournament_kind = s.get("tournament_kind") or ""
    phase = s.get("phase") or ""
    # Tournament series get a 🏆 prefix and a kind suffix ("[Async]" /
    # "[Sync]") so the channel makes it obvious which bracket the match
    # belongs to without having to dig into the F5 menu. Pre-match
    # tournament series get an additional "PRE-MATCH" callout — bets are
    # still open but the game hasn't started in-game yet, so people
    # know they're betting on an upcoming bracket fixture rather than
    # a live ranked queue match.
    if is_tournament:
        kind_label = f" [{tournament_kind.title()}]" if tournament_kind else ""
        if phase == "pre_match":
            title = f"🏆 Tournament{kind_label} PRE-MATCH: {p1n} ({p1r}) vs {p2n} ({p2r})"
        else:
            title = f"🏆 Tournament{kind_label}: {p1n} ({p1r}) vs {p2n} ({p2r})"
    else:
        title = f"🎮 {p1n} ({p1r}) vs {p2n} ({p2r})"
    desc_lines = [
        f"Series: **{p1w} - {p2w}**",
        f"Odds: **{p1o}x** {p1n} / **{p2o}x** {p2n}",
    ]
    if locked:
        if reason == "game_in_progress":
            desc_lines.append("🔒 Game in progress — bets locked")
        elif reason == "no_meaningful_odds":
            desc_lines.append("🔒 No meaningful odds — bets disabled")
        else:
            desc_lines.append("🔒 Bets locked")
    # Tournament gets a distinct gold tint so it's instantly visually different.
    if is_tournament:
        embed_color = 0xFFD94D
    elif locked:
        embed_color = 0x666666
    else:
        embed_color = 0xFF6688
    em = discord.Embed(title=title, description="\n".join(desc_lines), color=embed_color)
    em.set_footer(text=f"series {s['series_id'][:8]}")
    return em

def _format_team_live_bet_embed(s: dict) -> discord.Embed:
    """2v2 live-series embed for the gambler channel. Read-only (no Discord bet
    buttons yet — in-game 2v2 betting already works; this just makes 2v2 series
    VISIBLE in the gambler chat, which they weren't before: poll_live_bets only
    polled the 1v1 /series/active, so every 2v2 series was silently absent)."""
    t1a = s.get("t1a_name", "?"); t1b = s.get("t1b_name", "?")
    t2a = s.get("t2a_name", "?"); t2b = s.get("t2b_name", "?")
    # Per-player 2v2 ratings (not the team average).
    t1ar = s.get("t1a_rating", 1500); t1br = s.get("t1b_rating", 1500)
    t2ar = s.get("t2a_rating", 1500); t2br = s.get("t2b_rating", 1500)
    t1o = s.get("t1_odds", 1.01); t2o = s.get("t2_odds", 1.01)
    t1w = s.get("t1_wins", 0); t2w = s.get("t2_wins", 0)
    locked = s.get("bets_locked", False)
    reason = s.get("lock_reason")
    title = f"👥 2v2: {t1a}+{t1b} vs {t2a}+{t2b}"
    desc_lines = [
        f"Team 1: **{t1a}** ({t1ar}) + **{t1b}** ({t1br})",
        f"Team 2: **{t2a}** ({t2ar}) + **{t2b}** ({t2br})",
        f"Series: **{t1w} - {t2w}**",
        f"Odds: **{t1o}x** Team 1 / **{t2o}x** Team 2",
        "_Bet in-game via the F5 → Leaderboard panel._",
    ]
    if locked:
        if reason == "game_in_progress":
            desc_lines.append("🔒 Game in progress — bets locked")
        elif reason == "no_meaningful_odds":
            desc_lines.append("🔒 No meaningful odds — bets disabled")
        else:
            desc_lines.append("🔒 Bets locked")
    em = discord.Embed(title=title, description="\n".join(desc_lines),
                       color=(0x666666 if locked else 0xFFB347))
    em.set_footer(text=f"2v2 series {s['series_id'][:8]}")
    return em


# series_id -> message_id for the 2v2 live-bets posts (separate map from 1v1).
team_live_bet_messages = {}


ffa_live_bet_messages = {}


def _format_ffa_live_bet_embed(lobby):
    """Read-only live-odds embed for one FFA lobby, keyed per GAME.

    Deliberately not a bet-placement UI: 10 players x 3 presets would blow past
    Discord's 25-component cap, so placing an FFA bet from Discord needs a
    select+modal flow that is its own piece of work. This is the visibility half
    Sid asked for ("make FFA bets show up in the discord gambler chat").
    """
    n = lobby.get("player_count") or len(lobby.get("players") or [])
    game_no = lobby.get("game_number") or 1
    locked = False
    open_ = bool(lobby.get("bets_open"))
    lines = []
    for p in lobby.get("players") or []:
        odds = p.get("odds_multiplier") or 0
        # escape_markdown: a display name is user-authored, and without it a
        # name carrying bold markers plus a newline can break out of its span
        # and forge a convincing state line inside this embed (Codex F7).
        nm = discord.utils.escape_markdown(str(p.get("display_name") or "?"))
        lines.append(f"**{nm}** ({p.get('rating')}) — x{odds:.2f}")
    if locked:
        state = "🔒 **Bets closed** for this game"
    elif not open_:
        state = "⏳ Betting for this game has closed"
    else:
        state = "🟢 **Bets open** — in game, F5 → Leaderboard"
    embed = discord.Embed(
        title=f"🎯 FFA Game {game_no} — {n} players",
        description=state + "\n\n" + "\n".join(lines),
        color=0x8E44AD if not locked else 0x555555,
    )
    embed.set_footer(text="Bet in-game: F5 -> Leaderboard")
    return embed


@tasks.loop(seconds=10)
async def poll_ffa_live_bets():
    """Post/update one embed per live FFA lobby GAME in the gambler channel.

    Keyed on (lobby_id, game_number) rather than lobby alone, because the bet
    window genuinely re-opens for every game of a sitting — a new game deserves
    a new post, not an edit of the finished one. Own guarded loop: a tasks.loop
    dies permanently on an unhandled exception (#129), so this must not share
    one with the 1v1/2v2 pollers.
    """
    if not LIVE_BETS_CHANNEL_ID:
        return
    data = await api_get("/ffa/bettable")
    if not data:
        return
    lobbies = data.get("lobbies") or []
    channel = bot.get_channel(LIVE_BETS_CHANNEL_ID)
    if channel is None:
        try: channel = await bot.fetch_channel(LIVE_BETS_CHANNEL_ID)
        except Exception: return
    seen_now = set()
    for l in lobbies:
        lid = l.get("lobby_id")
        if not lid:
            continue
        key = (lid, int(l.get("game_number") or 1))
        seen_now.add(key)
        embed = _format_ffa_live_bet_embed(l)
        msg_id = ffa_live_bet_messages.get(key)
        try:
            if msg_id is None:
                msg = await channel.send(embed=embed)
                ffa_live_bet_messages[key] = msg.id
            else:
                msg = await channel.fetch_message(msg_id)
                await msg.edit(embed=embed)
        except discord.NotFound:
            try:
                msg = await channel.send(embed=embed)
                ffa_live_bet_messages[key] = msg.id
            except Exception as e:
                print(f"[FFA-LIVE-BETS] re-post failed for {lid}: {e}")
        except Exception as e:
            print(f"[FFA-LIVE-BETS] update failed for {lid}: {e}")
    for key in [k for k in list(ffa_live_bet_messages.keys()) if k not in seen_now]:
        del ffa_live_bet_messages[key]


@tasks.loop(seconds=10)
async def poll_team_live_bets():
    """Mirror of poll_live_bets for 2v2. Posts/updates a read-only embed per
    active team_series so 2v2 games appear in the gambler channel (they were
    structurally absent before — no loop polled /team/series/active)."""
    if not LIVE_BETS_CHANNEL_ID:
        return
    data = await api_get("/team/series/active")
    if not data:
        return
    series_list = data.get("series") or []
    channel = bot.get_channel(LIVE_BETS_CHANNEL_ID)
    if channel is None:
        try: channel = await bot.fetch_channel(LIVE_BETS_CHANNEL_ID)
        except Exception: return
    seen_now = set()
    for s in series_list:
        sid = s.get("series_id")
        if not sid: continue
        seen_now.add(sid)
        embed = _format_team_live_bet_embed(s)
        msg_id = team_live_bet_messages.get(sid)
        try:
            if msg_id is None:
                msg = await channel.send(embed=embed)
                team_live_bet_messages[sid] = msg.id
            else:
                msg = await channel.fetch_message(msg_id)
                await msg.edit(embed=embed)
        except discord.NotFound:
            try:
                msg = await channel.send(embed=embed)
                team_live_bet_messages[sid] = msg.id
            except Exception as e:
                print(f"[TEAM-LIVE-BETS] re-post failed for {sid}: {e}")
        except Exception as e:
            print(f"[TEAM-LIVE-BETS] update failed for {sid}: {e}")
    stale = [sid for sid in list(team_live_bet_messages.keys()) if sid not in seen_now]
    for sid in stale:
        del team_live_bet_messages[sid]


@tasks.loop(seconds=10)
async def poll_live_bets():
    if not LIVE_BETS_CHANNEL_ID:
        return
    data = await api_get("/series/active")
    if not data:
        return
    series_list = data.get("series") or []
    channel = bot.get_channel(LIVE_BETS_CHANNEL_ID)
    if channel is None:
        try: channel = await bot.fetch_channel(LIVE_BETS_CHANNEL_ID)
        except Exception: return
    seen_now = set()
    for s in series_list:
        sid = s.get("series_id")
        if not sid: continue
        seen_now.add(sid)
        embed = _format_live_bet_embed(s)
        view = None
        if not s.get("bets_locked", False):
            view = LiveBetView(
                series_id=sid,
                p1_steam=s.get("p1_steam_id", ""),
                p1_name=s.get("p1_name", "?"),
                p2_steam=s.get("p2_steam_id", ""),
                p2_name=s.get("p2_name", "?"),
            )
        msg_id = live_bet_messages.get(sid)
        try:
            if msg_id is None:
                msg = await channel.send(embed=embed, view=view)
                live_bet_messages[sid] = msg.id
            else:
                msg = await channel.fetch_message(msg_id)
                await msg.edit(embed=embed, view=view)
        except discord.NotFound:
            # Message was deleted by hand — repost.
            try:
                msg = await channel.send(embed=embed, view=view)
                live_bet_messages[sid] = msg.id
            except Exception as e:
                print(f"[LIVE-BETS] re-post failed for {sid}: {e}")
        except Exception as e:
            print(f"[LIVE-BETS] update failed for {sid}: {e}")
    # Series no longer active — leave the message in the channel as history,
    # but drop our tracking so we don't keep editing it. (A separate cleanup
    # could mark it as "Final: X-Y" but that needs a /series/{id} fetch we
    # don't have yet; cheap enough to leave as-is.)
    stale = [sid for sid in list(live_bet_messages.keys()) if sid not in seen_now]
    for sid in stale:
        del live_bet_messages[sid]


# ── Gambler role: ping on open bets + self-serve opt-in/out ──────────────
# Reaction-role signup message + /gambler slash toggle + a ping in the live
# bets channel whenever a new ranked match opens for betting. Additive: does
# not touch poll_live_bets — it independently polls /series/active.
_gambler_pinged = set()
_gambler_seeded = False
_gambler_signup_checked = False
_gambler_msg_id = None


async def _ensure_gambler_signup_message():
    """Find (after a restart) or post the 🎲 reaction-role signup message."""
    global _gambler_msg_id
    if not GAMBLER_SIGNUP_CHANNEL_ID:
        return
    channel = bot.get_channel(GAMBLER_SIGNUP_CHANNEL_ID)
    if channel is None:
        try:
            channel = await bot.fetch_channel(GAMBLER_SIGNUP_CHANNEL_ID)
        except Exception as e:
            print(f"[GAMBLER] signup channel unavailable: {e}")
            return
    # Re-find our own message so we don't post duplicates every restart.
    try:
        async for msg in channel.history(limit=50):
            if msg.author.id == bot.user.id and msg.embeds:
                ft = msg.embeds[0].footer.text if msg.embeds[0].footer else None
                if ft and GAMBLER_SIGNUP_MARKER in ft:
                    _gambler_msg_id = msg.id
                    try:
                        await msg.add_reaction(GAMBLER_EMOJI)
                    except Exception:
                        pass
                    print(f"[GAMBLER] re-using signup message {msg.id}")
                    return
    except Exception as e:
        print(f"[GAMBLER] history scan failed: {e}")
    embed = discord.Embed(
        title="🎲 Gambler Role",
        description=(
            f"React with {GAMBLER_EMOJI} to get pinged whenever a new ranked match "
            f"opens for betting.\nRemove your reaction (or use `/gambler`) to opt back out."
        ),
        color=0xF1C40F,
    )
    embed.set_footer(text=GAMBLER_SIGNUP_MARKER)
    try:
        msg = await channel.send(embed=embed)
        await msg.add_reaction(GAMBLER_EMOJI)
        _gambler_msg_id = msg.id
        print(f"[GAMBLER] posted signup message {msg.id} in {GAMBLER_SIGNUP_CHANNEL_ID}")
    except Exception as e:
        print(f"[GAMBLER] failed to post signup message: {e}")


@tasks.loop(seconds=10)
async def poll_gambler_pings():
    """Ping the Gambler role when a new match opens for betting."""
    global _gambler_seeded, _gambler_signup_checked
    if not _gambler_signup_checked:
        _gambler_signup_checked = True
        await _ensure_gambler_signup_message()
    data = await api_get("/series/active")
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        items = data.get("series", []) or data.get("active", [])
    else:
        items = []
    open_now = {}
    # Every series still live, INCLUDING ones whose bets are momentarily locked
    # while a game is being played. Used only for pruning the pinged-set below.
    live_now = set()
    for s in items:
        if not isinstance(s, dict):
            continue
        sid = s.get("series_id") or s.get("id")
        if not sid:
            continue
        live_now.add(str(sid))
        if s.get("bets_locked", False):
            continue
        open_now[str(sid)] = s
    # First pass after startup seeds the seen-set WITHOUT pinging, so a bot
    # restart doesn't mass-ping every match already in progress.
    if not _gambler_seeded:
        _gambler_seeded = True
        # Seed with every LIVE series, not just the currently-bettable ones:
        # restarting mid-game (bets locked) would otherwise leave the series
        # unseeded and ping it the moment betting re-opened.
        _gambler_pinged.update(live_now)
        return
    channel = bot.get_channel(LIVE_BETS_CHANNEL_ID)
    if channel is None:
        try:
            channel = await bot.fetch_channel(LIVE_BETS_CHANNEL_ID)
        except Exception:
            channel = None
    for sid, s in open_now.items():
        if sid in _gambler_pinged:
            continue
        _gambler_pinged.add(sid)
        if channel is None:
            continue
        guild = getattr(channel, "guild", None)
        role = discord.utils.get(guild.roles, name=GAMBLER_ROLE_NAME) if guild else None
        p1 = s.get("p1_name") or s.get("player1_name") or s.get("p1_display_name") or "Player 1"
        p2 = s.get("p2_name") or s.get("player2_name") or s.get("p2_display_name") or "Player 2"
        mention = role.mention if role else f"@{GAMBLER_ROLE_NAME}"
        try:
            await channel.send(
                f"{mention} 🎲 Bets are open — **{p1}** vs **{p2}**! Place yours below.",
                allowed_mentions=discord.AllowedMentions(roles=True),
            )
        except Exception as e:
            print(f"[GAMBLER] ping failed for {sid}: {e}")
    # Drop ids once the series is GONE, not merely because betting is locked.
    # Bets lock for the duration of each game and re-open between games, so
    # pruning against open_now made the bot forget a live series at every game
    # boundary and ping it again on the next one — the same series id was
    # announced twice hours apart (TechTara vs NotNic, 1:38 PM and 3:46 PM).
    # Pruning against live_now keeps one ping per series for its whole life.
    for sid in list(_gambler_pinged):
        if sid not in live_now:
            _gambler_pinged.discard(sid)


@bot.event
async def on_raw_reaction_add(payload):
    if _gambler_msg_id is None or payload.message_id != _gambler_msg_id:
        return
    if str(payload.emoji) != GAMBLER_EMOJI:
        return
    if bot.user and payload.user_id == bot.user.id:
        return
    guild = bot.get_guild(payload.guild_id) if payload.guild_id else None
    if guild is None:
        return
    role = discord.utils.get(guild.roles, name=GAMBLER_ROLE_NAME)
    if role is None:
        return
    member = payload.member or guild.get_member(payload.user_id)
    if member is None:
        try:
            member = await guild.fetch_member(payload.user_id)
        except Exception:
            return
    try:
        await member.add_roles(role, reason="Gambler opt-in via reaction")
    except Exception as e:
        print(f"[GAMBLER] add_roles failed: {e}")


@bot.event
async def on_raw_reaction_remove(payload):
    if _gambler_msg_id is None or payload.message_id != _gambler_msg_id:
        return
    if str(payload.emoji) != GAMBLER_EMOJI:
        return
    guild = bot.get_guild(payload.guild_id) if payload.guild_id else None
    if guild is None:
        return
    role = discord.utils.get(guild.roles, name=GAMBLER_ROLE_NAME)
    if role is None:
        return
    member = guild.get_member(payload.user_id)
    if member is None:
        try:
            member = await guild.fetch_member(payload.user_id)
        except Exception:
            return
    try:
        await member.remove_roles(role, reason="Gambler opt-out via reaction")
    except Exception as e:
        print(f"[GAMBLER] remove_roles failed: {e}")


@bot.hybrid_command(name="gambler", description="Toggle the Gambler role — get pinged when a new bet opens")
async def cmd_gambler(ctx):
    guild = ctx.guild
    if guild is None:
        await ctx.send("Use this in the server.", ephemeral=True)
        return
    role = discord.utils.get(guild.roles, name=GAMBLER_ROLE_NAME)
    if role is None:
        await ctx.send(f"The '{GAMBLER_ROLE_NAME}' role doesn't exist in this server yet.", ephemeral=True)
        return
    member = ctx.author if isinstance(ctx.author, discord.Member) else guild.get_member(ctx.author.id)
    if member is None:
        await ctx.send("Couldn't resolve your membership.", ephemeral=True)
        return
    try:
        if role in member.roles:
            await member.remove_roles(role, reason="Gambler opt-out via /gambler")
            await ctx.send(f"🎲 Removed **{GAMBLER_ROLE_NAME}** — you won't be pinged on new bets.", ephemeral=True)
        else:
            await member.add_roles(role, reason="Gambler opt-in via /gambler")
            await ctx.send(f"🎲 You now have **{GAMBLER_ROLE_NAME}** — you'll be pinged when a bet opens.", ephemeral=True)
    except discord.Forbidden:
        await ctx.send("I can't manage that role — make sure my bot role is above the Gambler role.", ephemeral=True)


if __name__ == "__main__":
    if not DISCORD_TOKEN: print("ERROR: Set DISCORD_TOKEN"); exit(1)
    bot.run(DISCORD_TOKEN)
