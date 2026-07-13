"""
Competitive ROUNDS Discord Bot
Environment: DISCORD_TOKEN, API_BASE_URL, LEADERBOARD_CHANNEL, SERIES_LOG_CHANNEL
"""
import os, asyncio, aiohttp, discord, json
from discord import app_commands
from discord.ext import commands, tasks
from datetime import datetime, timezone

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
# Bug reports auto-post here when players file via the F5 menu. ID gets a
# safe default so an unset env var doesn't crash the bot — 0 disables.
BUG_REPORTS_CHANNEL_ID = int(os.getenv("BUG_REPORTS_CHANNEL", "1501643180049960970"))

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

RANK_ROLES = [
    (2610, "Grand Master V 2610+"),
    (2540, "Grand Master IV 2540-2609"),
    (2470, "Grand Master III 2470-2539"),
    (2400, "Grand Master II 2400-2469"),
    (2330, "Grand Master 2330-2399"),
    (2270, "Master V 2270-2329"),
    (2210, "Master IV 2210-2269"),
    (2150, "Master III 2150-2209"),
    (2090, "Master II 2090-2149"),
    (2030, "Master 2030-2089"),
    (1980, "Advanced V 1980-2029"),
    (1930, "Advanced IV 1930-1979"),
    (1880, "Advanced III 1880-1929"),
    (1830, "Advanced II 1830-1879"),
    (1780, "Advanced 1780-1829"),
    (1740, "Intermediate V 1740-1779"),
    (1700, "Intermediate IV 1700-1739"),
    (1660, "Intermediate III 1660-1699"),
    (1620, "Intermediate II 1620-1659"),
    (1580, "Intermediate 1580-1619"),
    (1564, "Beginner V 1564-1579"),
    (1548, "Beginner IV 1548-1563"),
    (1532, "Beginner III 1532-1547"),
    (1516, "Beginner II 1516-1531"),
    (0,    "Beginner 1515>"),
]
ALL_RANK_ROLE_NAMES = [n for _, n in RANK_ROLES]

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

async def api_get(path):
    try:
        async with http_session.get(f"{API_BASE_URL}/api/v1{path}") as r:
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
            "Your Discord must be linked in-game first: F5 → My Stats → Get Link Code, then `!link YOUR_CODE` here."
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
                    "Make sure your Discord is linked in-game: F5 → My Stats → Get Link Code, then `!link YOUR_CODE` here."
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
    return "Beginner"

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
    remove = [r for r in member.roles if r.name in ALL_RANK_ROLE_NAMES]
    if remove: await member.remove_roles(*remove, reason="Rank update")
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
    if not poll_team_recent_series.is_running(): poll_team_recent_series.start()
    if not poll_anticheat_flags.is_running(): poll_anticheat_flags.start()
    if not poll_new_bans.is_running(): poll_new_bans.start()
    if not poll_github_releases.is_running(): poll_github_releases.start()
    if not poll_live_bets.is_running(): poll_live_bets.start()
    if not poll_team_live_bets.is_running(): poll_team_live_bets.start()
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
    print(f"Bot ready: {bot.user} (guilds: {len(bot.guilds)}, chat={CHAT_CHANNEL_ID}, admin={ADMIN_CHANNEL_ID})")


async def backfill_discord_usernames():
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

    ids = data.get("discord_ids", [])
    if not ids:
        print("[BACKFILL] No Discord usernames to backfill"); return
    print(f"[BACKFILL] Resolving {len(ids)} Discord usernames")
    resolved = 0
    for did in ids:
        try:
            user = bot.get_user(int(did)) or await bot.fetch_user(int(did))
            if user is None: continue
            username = getattr(user, "global_name", None) or user.name
            await http_session.post(
                f"{API_BASE_URL}/api/v1/admin/set-discord-username",
                json={"discord_id": str(did), "discord_username": username},
                headers={"X-Internal-Key": API_SECRET_KEY},
                timeout=aiohttp.ClientTimeout(total=5),
            )
            resolved += 1
        except discord.NotFound:
            continue
        except Exception as e:
            print(f"[BACKFILL] {did}: {e}")
        # Rate-limit: Discord is lenient on user fetches but 5/s keeps us polite.
        await asyncio.sleep(0.2)
    print(f"[BACKFILL] Resolved {resolved}/{len(ids)} Discord usernames")


@bot.event
async def on_message(message: discord.Message):
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
        await ctx.send("**How to link:**\n1. Open ROUNDS → Competitive menu → My Stats\n2. Click **Get Link Code**\n3. Type `!link YOUR_CODE` here"); return
    # Send Discord username alongside the ID so the in-game UI can display "Linked as @foo"
    # instead of raw ID. Prefer global_name (new display-name system), fall back to legacy name.
    discord_username = getattr(ctx.author, "global_name", None) or ctx.author.name
    result = await api_post("/players/link-discord", params={
        "code": code.upper(),
        "discord_id": str(ctx.author.id),
        "discord_username": discord_username,
    })
    if not result: await ctx.send("❌ API unreachable."); return
    if "error" in result:
        await ctx.send("❌ Invalid or expired code." if result.get("status") == 404 else f"❌ {result['error']}"); return
    await ctx.send(f"✅ Linked! **{ctx.author.display_name}** → Steam **{result.get('display_name')}** (`{result.get('steam_id')}`)")
    data = await api_get(f"/players/by-discord/{ctx.author.id}")
    if data and "rating" in data:
        rank = await update_member_role(ctx.author, data["rating"])
        await ctx.send(f"{rank_emoji(rank)} Rank: **{rank}** ({data['rating']:.0f})")

@bot.hybrid_command(name="rank", description="Check ranked stats for yourself or another player")
@app_commands.describe(member="Player to look up (defaults to yourself)")
async def cmd_rank(ctx, member: discord.Member = None):
    target = member or ctx.author
    link = await api_get(f"/players/by-discord/{target.id}")
    if not link:
        await ctx.send("❌ Not linked. Use `/link` first." if target == ctx.author else f"❌ {target.display_name} not linked."); return
    s = await api_get(f"/players/{link['steam_id']}")
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
    wl = f"{rw/rl:.2f}" if rl > 0 else f"{rw}:0"
    wr = f"{rw/total*100:.1f}%" if total > 0 else "—"
    series_lines = f"**{rw}**W / **{rl}**L  ({wr})\nW/L Ratio: **{wl}**"
    br = s.get("best_ranked_streak", 0)
    if br > 0: series_lines += f"\nBest Streak: **{br}W** 🔥"
    embed.add_field(name="🏆  Ranked Series", value=series_lines, inline=True)

    # Sweeps
    sg, st = s.get("sweeps_given", 0), s.get("sweeps_taken", 0)
    sweep_lines = f"5-0 Given: **{sg}** 🧹\n0-5 Taken: **{st}**"
    embed.add_field(name="💨  Sweeps", value=sweep_lines, inline=True)

    # Leave rate
    dc = s.get("ranked_dc_count", 0)
    if dc > 0:
        rt_total = rw + rl + dc
        pct = f"{dc/rt_total*100:.1f}%" if rt_total > 0 else "—"
        embed.add_field(name="🚪  Leave Rate", value=f"**{dc}** / {rt_total} ({pct})", inline=True)

    pos = await get_lb_position(link["steam_id"])
    embed.set_footer(text=f"Leaderboard: #{pos}  •  Steam: {s['steam_id']}")
    await ctx.send(embed=embed)

async def get_lb_position(steam_id):
    data = await api_get("/leaderboard?limit=200&min_matches=1")
    if not data or not data.get("entries"): return "?"
    for e in data["entries"]:
        if e["steam_id"] == steam_id: return str(e["rank"])
    return "Unranked"

@bot.hybrid_command(name="stats", description="View overall & casual stats")
@app_commands.describe(member="Player to look up (defaults to yourself)")
async def cmd_stats(ctx, member: discord.Member = None):
    target = member or ctx.author
    link = await api_get(f"/players/by-discord/{target.id}")
    if not link:
        await ctx.send("❌ Not linked." if target == ctx.author else f"❌ {target.display_name} not linked."); return
    s = await api_get(f"/players/{link['steam_id']}")
    if not s: await ctx.send("❌ Could not fetch stats."); return
    embed = discord.Embed(title=f"📋  {s['display_name']}  —  Overall Stats", color=discord.Color.blue())
    embed.set_thumbnail(url=target.display_avatar.url)

    # Overall record
    tw, tl = s.get("wins", 0), s.get("losses", 0)
    tt = s.get("total_matches", 0)
    twr = f"{tw/tt*100:.1f}%" if tt > 0 else "—"
    embed.add_field(name="📊  Total Record", value=f"**{tt}** matches  —  **{tw}**W / **{tl}**L  ({twr})", inline=False)

    # Casual record (from API)
    cw, cl = s.get("casual_wins", 0), s.get("casual_losses", 0)
    ct = cw + cl
    cwr = f"{cw/ct*100:.1f}%" if ct > 0 else "—"
    casual_str = f"**{cw}**W / **{cl}**L  ({cwr})" if ct > 0 else "—"
    embed.add_field(name="🎮  Casual", value=casual_str, inline=True)

    # Ranked series
    rw, rl = s.get("ranked_series_wins", 0), s.get("ranked_series_losses", 0)
    rt = rw + rl
    ranked_str = f"**{rw}**W / **{rl}**L" if rt > 0 else "—"
    embed.add_field(name="⚔️  Ranked Series", value=ranked_str, inline=True)

    # Sweeps
    sg, st = s.get("sweeps_given", 0), s.get("sweeps_taken", 0)
    if sg + st > 0:
        embed.add_field(name="💨  Sweeps", value=f"5-0: **{sg}** 🧹  ·  0-5: **{st}**", inline=True)

    # Leave rate
    dc = s.get("ranked_dc_count", 0)
    if dc > 0:
        rt_dc_total = rt + dc
        pct = f"{dc/rt_dc_total*100:.1f}%" if rt_dc_total > 0 else "—"
        embed.add_field(name="🚪  Leave Rate", value=f"**{dc}** / {rt_dc_total} ({pct})", inline=True)

    embed.add_field(name="\u200b", value="\u200b", inline=False)

    # Level & XP
    embed.add_field(name="⭐  Level", value=f"**{s.get('level', 0)}**", inline=True)
    embed.add_field(name="✨  XP", value=f"**{s.get('total_xp', 0):,}**", inline=True)

    # Streaks
    br = s.get("best_ranked_streak", 0)
    bc = s.get("best_casual_streak", 0)
    streaks = []
    if br > 0: streaks.append(f"Ranked: **{br}W** 🔥")
    if bc > 0: streaks.append(f"Casual: **{bc}W**")
    if streaks:
        embed.add_field(name="📈  Best Streaks", value="  ·  ".join(streaks), inline=True)

    # Top cards
    top = s.get("top_card_names", [])
    picks = s.get("top_card_picks", [])
    if top:
        cards_lines = "\n".join(f"**{top[i]}** ({picks[i]}x)" for i in range(min(5, len(top))) if i < len(picks))
        embed.add_field(name="🃏  Top Cards", value=cards_lines, inline=False)

    embed.set_footer(text=f"Steam: {s['steam_id']}")
    await ctx.send(embed=embed)

@bot.hybrid_command(name="lb", description="Show the ranked leaderboard")
@app_commands.describe(page="Page number (default: 1)")
async def cmd_leaderboard(ctx, page: int = 1):
    per_page = 20  # match the #scr-leaderboard channel board (was 10; Sid 07-11 item 8)
    page = max(1, page)
    offset = (page - 1) * per_page
    data = await api_get(f"/leaderboard?limit={per_page}&offset={offset}&min_matches=1")
    if not data or not data.get("entries"): await ctx.send("❌ No data."); return
    lines = []
    for e in data["entries"]:
        emoji = rank_emoji(get_rank_name(e["rating"]))
        lines.append(f"`#{e['rank']:>2}` {emoji} **{e['display_name']}** — {e['rating']} ({e['wins']}W/{e['losses']}L)")
    total = data.get("total_players", 0)
    total_pages = max(1, (total + per_page - 1) // per_page)
    embed = discord.Embed(title="🏆 Competitive ROUNDS Leaderboard", description="\n".join(lines), color=discord.Color.gold())
    embed.set_footer(text=f"Page {page}/{total_pages} • {total} ranked players" + (f" • /lb {page+1} for next page" if page < total_pages else ""))
    await ctx.send(embed=embed)

# ── Queue Beacon (15s) ───────────────────────────────────────────
seen_queue_joins = {}  # steam_id -> timestamp

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
                f"🔍 **{discord.utils.escape_markdown(str(name))}** ({rating}) is searching for a ranked match!",
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
                f"🎯 **{discord.utils.escape_markdown(str(name))}** ({rating}) is searching for **2v2** — **{qsize}/4** queued!",
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
                f"⚔️ **{discord.utils.escape_markdown(str(name))}** ({rating}) is searching for **1v2** — **{qsize}/3** in the lobby!",
                allowed_mentions=discord.AllowedMentions.none(),
            )
    except Exception as e:
        print(f"1v2 queue beacon error: {e}")


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
        if linked and linked.get("players"):
            rmap = {p["discord_id"]: p.get("rating", 0) for p in linked["players"] if p.get("discord_id")}
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
                try:
                    await update_member_role(member, rat)
                    await asyncio.sleep(0.3)   # rate-limit slack only for actual role work
                except Exception:
                    pass
    except Exception as e:
        print(f"[ROLE-SYNC] tick failed: {e}")

@sync_roles_periodic.before_loop
async def before_sync(): await bot.wait_until_ready()


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
                                "F5 → My Stats → Get Link Code, then `!link YOUR_CODE` here."
                            )
                        except Exception:
                            pass
            except Exception as ex:
                print(f"[BOOSTER] {member}: {ex}")
            await asyncio.sleep(0.3)


_booster_nudged = set()


@grant_booster_gold.before_loop
async def before_booster(): await bot.wait_until_ready()

LB_PAGE_SIZE = 20
LB_TOTAL_FETCH = 100  # we cache this many; pages of 20 ⇒ up to 5 pages


def _build_lb_embed(entries: list, total_players: int, page: int, total_pages: int) -> discord.Embed:
    """Render one page of the auto-posted leaderboard. Pure function so the
    paginator view + initial post share the rendering."""
    lines = []
    start = page * LB_PAGE_SIZE
    end = min(start + LB_PAGE_SIZE, len(entries))
    for e in entries[start:end]:
        emoji = rank_emoji(get_rank_name(e["rating"]))
        lines.append(f"`#{e['rank']:>3}` {emoji} **{e['display_name']}** — {e['rating']} ({e['wins']}W/{e['losses']}L)")
    # Live relative timestamp INSIDE the embed body ("Updated 3 minutes ago",
    # ticking client-side). The embed's footer timestamp was the only recency
    # signal before, and a silently-edited days-old message reads as a dead
    # board ("posts aren't updating") even when every 10-min edit lands.
    # now(timezone.utc), not utcnow(): .timestamp() on a naive datetime assumes
    # LOCAL time — correct only while the container happens to run UTC.
    updated = f"Updated <t:{int(datetime.now(timezone.utc).timestamp())}:R>\n\n"
    embed = discord.Embed(
        title="🏆 Ranked Leaderboard",
        description=updated + ("\n".join(lines) if lines else "(no players)"),
        color=discord.Color.gold(),
        timestamp=datetime.utcnow(),
    )
    embed.set_footer(text=f"Page {page+1}/{total_pages} • {total_players} ranked players • Auto-updated")
    return embed


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
            embed=_build_lb_embed(self.entries, self.total_players, self.page, self.total_pages),
            view=self,
        )

    @discord.ui.button(label="Next ▶", style=discord.ButtonStyle.secondary)
    async def nxt(self, interaction: discord.Interaction, _: discord.ui.Button):
        self.page = min(self.total_pages - 1, self.page + 1)
        self._update_buttons()
        await interaction.response.edit_message(
            embed=_build_lb_embed(self.entries, self.total_players, self.page, self.total_pages),
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
    embed = _build_lb_embed(entries, total_players, 0, total_pages)
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
                sent = await ch.send(embed=embed, view=view)
                _lb_message_ids[ch.id] = sent.id
                print(f"[LB] board was buried (last_message_id={ch.last_message_id}) — reposted at bottom as mid={sent.id}")
                return
            await msg.edit(embed=embed, view=view)
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
            sent = await ch.send(embed=embed, view=view)
            _lb_message_ids[ch.id] = sent.id
            print(f"[LB] re-anchored board was buried — reposted at bottom as mid={sent.id}")
            return
        _lb_message_ids[ch.id] = keeper.id
        try:
            await keeper.edit(embed=embed, view=view)
            print(f"[LB] re-anchored to board mid={keeper.id} and edited")
        except Exception as e:
            # Leave the id cached; the next tick retries via the fast path.
            print(f"[LB] re-anchor edit of mid={keeper.id} failed: {e}")
        return
    sent = await ch.send(embed=embed, view=view)
    _lb_message_ids[ch.id] = sent.id
    print(f"[LB] posted fresh leaderboard message in {ch.id}")

# ── Anti-cheat flag relay ────────────────────────────────────────
# Tracks the most-recently-posted flag ID so we don't repeat on bot restart.
# Persisted in-memory only — on cold start, anchor at "now" by pulling once and
# remembering the latest ID without posting (handled by the first poll tick).
_last_flag_id_posted: str | None = None
_flag_poller_initialized = False

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
            await ch.send(p["content"][:2000])
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
    if reason == "too_many_cards":          return (0xE74C3C, "🃏")  # red
    if reason == "short_duration_pattern":  return (0xE67E22, "⏱️")  # orange
    if reason == "inactive_player":         return (0xF1C40F, "💤")  # yellow (advisory)
    return (0x95A5A6, "🚩")


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
    global _last_flag_id_posted, _flag_poller_initialized
    if not http_session or not API_SECRET_KEY or not ADMIN_CHANNEL_ID:
        return
    try:
        params = {"limit": 50}
        if _last_flag_id_posted:
            params["since_id"] = _last_flag_id_posted
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

    # Cold-start: don't spam the channel with the entire history. Skip posting
    # on the very first tick, just memo the most-recent ID.
    if not _flag_poller_initialized:
        _flag_poller_initialized = True
        _last_flag_id_posted = flags[-1]["id"]
        print(f"[ANTICHEAT] cold start, anchored at {_last_flag_id_posted[:8]}")
        return

    channel = bot.get_channel(ADMIN_CHANNEL_ID) or await bot.fetch_channel(ADMIN_CHANNEL_ID)
    if channel is None:
        print(f"[ANTICHEAT] admin channel {ADMIN_CHANNEL_ID} not resolvable")
        return

    for f in flags:
        try:
            color, emoji = _flag_color_and_emoji(f["flag_reason"], f["auto_invalidated"])
            details = f.get("flag_details") or {}
            mode = "Ranked" if f.get("is_ranked") else "Casual"
            dur = f.get("duration_seconds")
            dur_str = f"{dur}s" if dur is not None else "—"
            verdict = "auto-invalidated" if f["auto_invalidated"] else "advisory (manual review)"
            embed = discord.Embed(
                title=f"{emoji} Match flagged: `{f['flag_reason']}`",
                description=(
                    f"**{f['p1_name']}** vs **{f['p2_name']}** ({mode}, {dur_str})\n"
                    f"Status: **{verdict}**\n"
                    f"Match ID: `{f['match_id']}`"
                ),
                color=color,
                timestamp=datetime.fromisoformat(f["created_at"].replace("Z", "+00:00")) if f.get("created_at") else None,
            )
            # Per-reason context fields.
            if f["flag_reason"] == "too_many_cards":
                embed.add_field(name="Cards picked", value=f"P1: {details.get('p1_cards')}  P2: {details.get('p2_cards')} (max {details.get('max_allowed')})", inline=False)
            elif f["flag_reason"] == "short_duration_pattern":
                prior = details.get("prior_match_ids") or []
                embed.add_field(name="Pattern", value=f"This + {len(prior)} prior match(es) under 60s in a 2hr window", inline=False)
                if details.get("retroactive"):
                    embed.add_field(name="Retroactive", value=f"Triggered by {details.get('triggered_by_match','')[:8]}…", inline=False)
            elif f["flag_reason"] == "inactive_player":
                embed.add_field(name="Reporter inputs", value=f"Shots: {details.get('shots',0)}  Blocks: {details.get('blocks',0)}  Duration: {details.get('duration_seconds')}s", inline=False)
                embed.add_field(name="Reporter", value=f"`{details.get('reporter_steam','?')}`", inline=False)
            embed.add_field(name="Steam IDs", value="`" + "`, `".join(f.get("player_steam_ids") or []) + "`", inline=False)
            await channel.send(embed=embed)
            _last_flag_id_posted = f["id"]
        except Exception as ex:
            print(f"[ANTICHEAT] post error for flag {f.get('id')}: {ex}")


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
                        f"The mod connects you to your opponent automatically each round. "
                        f"If ROUNDS isn't running within 5 minutes of your match, you forfeit that match.")
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
        # Any state: DM players whose match just became ready
        if status == "running":
            for m in t.get("matches", []):
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
            if m.get("status") not in ("ready", "active", "pending"):
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
    for s in items:
        if not isinstance(s, dict):
            continue
        sid = s.get("series_id") or s.get("id")
        if not sid:
            continue
        if s.get("bets_locked", False):
            continue
        open_now[str(sid)] = s
    # First pass after startup seeds the seen-set WITHOUT pinging, so a bot
    # restart doesn't mass-ping every match already in progress.
    if not _gambler_seeded:
        _gambler_seeded = True
        _gambler_pinged.update(open_now.keys())
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
    # Drop ids no longer open so memory stays bounded.
    for sid in list(_gambler_pinged):
        if sid not in open_now:
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
