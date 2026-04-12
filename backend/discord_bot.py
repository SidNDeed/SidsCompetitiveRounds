"""
Competitive ROUNDS Discord Bot
Environment: DISCORD_TOKEN, API_BASE_URL, LEADERBOARD_CHANNEL, SERIES_LOG_CHANNEL
"""
import os, asyncio, aiohttp, discord
from discord import app_commands
from discord.ext import commands, tasks
from datetime import datetime

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "")
API_BASE_URL = os.getenv("API_BASE_URL", "http://api:8000")
LEADERBOARD_CHANNEL_ID = int(os.getenv("LEADERBOARD_CHANNEL", "0"))
SERIES_LOG_CHANNEL_ID = int(os.getenv("SERIES_LOG_CHANNEL", "0"))
QUEUE_BEACON_CHANNEL_ID = int(os.getenv("QUEUE_BEACON_CHANNEL", "0"))

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
    http_session = aiohttp.ClientSession()
    try: await bot.tree.sync()
    except Exception as e: print(f"Tree sync error: {e}")
    if not poll_recent_series.is_running(): poll_recent_series.start()
    if not sync_roles_periodic.is_running(): sync_roles_periodic.start()
    if not poll_queue_beacon.is_running(): poll_queue_beacon.start()
    print(f"Bot ready: {bot.user} (guilds: {len(bot.guilds)})")

@bot.event
async def on_close():
    if http_session: await http_session.close()

@bot.hybrid_command(name="link", description="Link your Discord to your ROUNDS Steam account")
@app_commands.describe(code="6-character code from the in-game Competitive menu")
async def cmd_link(ctx, code: str = None):
    if not code:
        await ctx.send("**How to link:**\n1. Open ROUNDS → Competitive menu → My Stats\n2. Click **Get Link Code**\n3. Type `!link YOUR_CODE` here"); return
    result = await api_post("/players/link-discord", params={"code": code.upper(), "discord_id": str(ctx.author.id)})
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

async def publish_lb(guild):
    if LEADERBOARD_CHANNEL_ID <= 0: return
    ch = guild.get_channel(LEADERBOARD_CHANNEL_ID)
    if not ch: return
    data = await api_get("/leaderboard?limit=20&min_matches=1")
    if not data or not data.get("entries"): return
    lines = []
    for e in data["entries"]:
        emoji = rank_emoji(get_rank_name(e["rating"]))
        lines.append(f"`#{e['rank']:>2}` {emoji} **{e['display_name']}** — {e['rating']} ({e['wins']}W/{e['losses']}L)")
    embed = discord.Embed(title="🏆 Ranked Leaderboard", description="\n".join(lines),
                          color=discord.Color.gold(), timestamp=datetime.utcnow())
    embed.set_footer(text=f"{data.get('total_players',0)} ranked players • Auto-updated")
    async for msg in ch.history(limit=5):
        if msg.author == bot.user and msg.embeds and "Ranked Leaderboard" in (msg.embeds[0].title or ""):
            await msg.edit(embed=embed); return
    await ch.send(embed=embed)

if __name__ == "__main__":
    if not DISCORD_TOKEN: print("ERROR: Set DISCORD_TOKEN"); exit(1)
    bot.run(DISCORD_TOKEN)
