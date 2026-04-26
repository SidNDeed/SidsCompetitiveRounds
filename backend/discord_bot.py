"""
Competitive ROUNDS Discord Bot
Environment: DISCORD_TOKEN, API_BASE_URL, LEADERBOARD_CHANNEL, SERIES_LOG_CHANNEL
"""
import os, asyncio, aiohttp, discord
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
API_SECRET_KEY = os.getenv("API_SECRET_KEY", "")

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
            return await r.json() if r.status == 200 else None
    except Exception as e:
        print(f"API GET error: {e}"); return None

async def api_post(path, params=None):
    try:
        async with http_session.post(f"{API_BASE_URL}/api/v1{path}", params=params) as r:
            if r.status == 200: return await r.json()
            return {"error": await r.text(), "status": r.status}
    except Exception as e:
        print(f"API POST error: {e}"); return None

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
    if not poll_team_recent_series.is_running(): poll_team_recent_series.start()
    if not poll_anticheat_flags.is_running(): poll_anticheat_flags.start()
    if not poll_chat_catchup.is_running(): poll_chat_catchup.start()
    if not poll_tournaments.is_running(): poll_tournaments.start()
    if not nag_pending_async_matches.is_running(): nag_pending_async_matches.start()
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


async def _forward_ingame_to_discord(data: dict) -> bool:
    """Render one ingame chat entry into the Discord channel. Returns True on
    success. Two-layer dedup:
      1. Synchronous _claim_msg_id — wins the race between WS path and catchup
         poll (which both run concurrently and can both pass the ts check).
      2. _last_relayed_ts — kept as a coarse "don't bother with old messages"
         filter so cold-start catchup doesn't iterate hundreds of historical rows."""
    global _last_relayed_ts
    if (data.get("source") or "") != "ingame":
        return False
    content = (data.get("message") or "").strip()
    if not content:
        return False
    ts = data.get("timestamp")
    if ts and _last_relayed_ts and ts <= _last_relayed_ts:
        return False
    # Claim the message id BEFORE any await — synchronous so the second concurrent
    # caller sees the first's add and bails. ts + steam_id + first 80 chars of msg
    # is unique enough for chat (collisions are vanishingly unlikely).
    msg_id = f"{data.get('steam_id') or data.get('discord_id') or ''}|{ts or ''}|{content[:80]}"
    if not _claim_msg_id(msg_id):
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


async def _catchup_ingame_since():
    """On WS (re)connect, pull /chat/recent and forward any ingame entries
    newer than _last_relayed_ts. Closes the gap where the bot's WS was down
    and the server broadcast had no subscriber."""
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
    per_page = 10
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

            await channel.send(f"🔍 **{name}** ({rating}) is searching for a ranked match!")
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
                f"🎯 **{name}** ({rating}) is searching for **2v2** — **{qsize}/4** queued!"
            )
    except Exception as e:
        print(f"Team queue beacon error: {e}")


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
        rc_s = f"+{rc:.0f}" if rc > 0 else f"{rc:.0f}"
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

@poll_recent_series.before_loop
async def before_poll():
    await bot.wait_until_ready()
    data = await api_get("/series/recent?minutes=5")
    if data and data.get("series"):
        for s in data["series"]: seen_series.add(s["series_id"])
    print(f"Pre-loaded {len(seen_series)} recent series")

async def log_series_result(guild, s):
    if SERIES_LOG_CHANNEL_ID <= 0: return
    ch = guild.get_channel(SERIES_LOG_CHANNEL_ID)
    if not ch: return
    p1_won = s["winner_steam_id"] == s["p1_steam_id"]
    score = f"{s['p1_series_wins']}-{s['p2_series_wins']}" if p1_won else f"{s['p2_series_wins']}-{s['p1_series_wins']}"
    embed = discord.Embed(title="⚔️ Ranked Series Complete", color=discord.Color.green())
    embed.description = f"**{s['winner_name']}** wins {score}!"
    rc1 = s["p1_rating_change"]; rc1s = f"+{rc1:.0f}" if rc1 > 0 else f"{rc1:.0f}"
    rc2 = s["p2_rating_change"]; rc2s = f"+{rc2:.0f}" if rc2 > 0 else f"{rc2:.0f}"
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
    for guild in bot.guilds:
        # Fetch all members since we disabled auto-chunking
        try:
            await guild.chunk()
        except Exception as e:
            print(f"Guild chunk error: {e}")
            continue
        data = await api_get("/leaderboard?limit=200&min_matches=1")
        if not data or not data.get("entries"): continue
        rmap = {e["steam_id"]: e["rating"] for e in data["entries"]}
        for member in guild.members:
            if member.bot: continue
            link = await api_get(f"/players/by-discord/{member.id}")
            if not link: continue
            rat = rmap.get(link.get("steam_id"), link.get("rating", 0))
            try: await update_member_role(member, rat)
            except: pass
            await asyncio.sleep(0.5)
    for guild in bot.guilds:
        try:
            await publish_lb(guild)
        except Exception as e:
            print(f"Leaderboard publish error: {e}")

@sync_roles_periodic.before_loop
async def before_sync(): await bot.wait_until_ready()

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
    embed = discord.Embed(
        title="🏆 Ranked Leaderboard",
        description="\n".join(lines) if lines else "(no players)",
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


async def publish_lb(guild):
    if LEADERBOARD_CHANNEL_ID <= 0: return
    ch = guild.get_channel(LEADERBOARD_CHANNEL_ID)
    if not ch: return
    data = await api_get(f"/leaderboard?limit={LB_TOTAL_FETCH}&min_matches=1")
    if not data or not data.get("entries"): return
    entries = data["entries"]
    total_players = data.get("total_players", 0)
    total_pages = max(1, (len(entries) + LB_PAGE_SIZE - 1) // LB_PAGE_SIZE)
    embed = _build_lb_embed(entries, total_players, 0, total_pages)
    view = LeaderboardPaginator(entries, total_players)
    view._update_buttons()
    async for msg in ch.history(limit=5):
        if msg.author == bot.user and msg.embeds and "Ranked Leaderboard" in (msg.embeds[0].title or ""):
            await msg.edit(embed=embed, view=view); return
    await ch.send(embed=embed, view=view)

# ── Anti-cheat flag relay ────────────────────────────────────────
# Tracks the most-recently-posted flag ID so we don't repeat on bot restart.
# Persisted in-memory only — on cold start, anchor at "now" by pulling once and
# remembering the latest ID without posting (handled by the first poll tick).
_last_flag_id_posted: str | None = None
_flag_poller_initialized = False


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
            await _announce_in_channel(
                f"**Tournament locked.** {len([s for s in t['signups'] if not s['is_speculative']])} players confirmed. "
                f"Starts {scheduled}. Bracket visible in-game."
            )
            # Individual DMs with seed.
            for s in t.get("signups", []):
                if s.get("is_speculative"):
                    continue
                body = (f"Tournament locked. You're in — match starts {scheduled}. "
                        f"Open the Tournaments tab in-game to see your bracket. "
                        f"You must be ready in the tab within 5 minutes of each match starting or you forfeit.")
                await _dm_user(s.get("discord_id"), body)
                await asyncio.sleep(0.1)
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
                        await _dm_user(p1d, f"Your tournament match vs **{p2n}** is ready. Open the Tournaments tab and ready up within 5 minutes or you forfeit.")
                        await _dm_user(p2d, f"Your tournament match vs **{p1n}** is ready. Open the Tournaments tab and ready up within 5 minutes or you forfeit.")
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


if __name__ == "__main__":
    if not DISCORD_TOKEN: print("ERROR: Set DISCORD_TOKEN"); exit(1)
    bot.run(DISCORD_TOKEN)
