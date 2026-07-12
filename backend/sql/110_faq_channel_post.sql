-- 110_faq_channel_post.sql  (v1.30)
--
-- Queues the #scr-faq sheet (6 messages) for the bot's channel-post loop.
-- Canonical copy lives at docs/FAQ.md — keep both in sync. Idempotent: each
-- insert is guarded on (channel_id, sort_order) already having a row, so
-- re-running the migration never double-posts. To publish an EDITED section
-- later, write a new migration inserting a fresh row (new sort_order).
--
-- Target channel: FAQ channel = 1159243585309384805 (retargeted from scr-faq per Sid 07-11)

INSERT INTO pending_channel_posts (channel_id, content, sort_order)
SELECT '1159243585309384805', $faq$**INSTALLING THE MOD**

**Option A — the installer (recommended)**
1. Grab `CompetitiveRoundsInstaller.exe` from the pinned post in #releases.
2. Close ROUNDS, run the installer. It finds your Steam ROUNDS install automatically and sets up BepInEx + the mod.
3. Launch ROUNDS. You'll see a consent prompt on first launch — the mod is online-only, so it needs a yes to track your matches.

**Option B — Thunderstore / r2modman**
1. Install "SidsCompetitiveRounds" through r2modman or the Thunderstore app (it pulls BepInEx automatically).
2. **Launch through the mod manager**, not plain Steam.
3. Updates come from the mod manager — it will NOT self-update like the installer version.

**Requirements**
- ROUNDS on Steam (current version 1.1.2), Windows. Mac isn't supported.
- **No other mods.** This is a competitive mod — if it detects any other plugin at launch it disables itself to keep matches fair. Uninstall other mods (or use a clean r2modman profile with only this mod).

Press **F5** in-game to open the competitive menu. That's the hub for everything: queue, stats, leaderboard, shop, settings.$faq$, 1
WHERE NOT EXISTS (SELECT 1 FROM pending_channel_posts WHERE channel_id = '1159243585309384805' AND sort_order = 1);

INSERT INTO pending_channel_posts (channel_id, content, sort_order)
SELECT '1159243585309384805', $faq$**UPDATING**

- **Installer version:** the mod checks for updates when ROUNDS starts and applies them when the game **closes**. So if a new version just dropped: launch → quit → launch again and you're on it. The F5 menu shows your version + the latest in the top corner.
- **Thunderstore version:** update through r2modman/Thunderstore like any other mod.
- If your version is too old, the server refuses to talk to it and the mod tells you to update — nothing counts until you do.
- Not sure what version you're on? F5 — it's in the header. Compare with the pinned #releases post.$faq$, 2
WHERE NOT EXISTS (SELECT 1 FROM pending_channel_posts WHERE channel_id = '1159243585309384805' AND sort_order = 2);

INSERT INTO pending_channel_posts (channel_id, content, sort_order)
SELECT '1159243585309384805', $faq$**RANKED — HOW A GAME QUALIFIES**

A match records as **ranked** only when **both** players:
1. Have the mod installed and running, and
2. Have ranked enabled (F5 → Ranked tab → the Enable/Disable button).

Everything else records as **casual** (still tracked, no rating change). The mod shows a notice at match start when your opponent isn't ranked-capable, so you know before you invest 10 minutes.

- Games vs vanilla (unmodded) players can never be ranked.
- Ranked queue matches (F5 → Search Ranked) are always ranked — queueing is consent.
- Ranked plays as a **best-of-3 series** vs the same opponent. Ratings (Glicko-2) apply when the series completes.
- If a series gets interrupted (crash, disconnect), just rematch the same player — the series **resumes where it left off**, even days later (up to 7 days).
- Leaving mid-series counts as a DC on your record; your leave % is visible on the leaderboard. Occasional crashes won't tank it, rage-quits will.$faq$, 3
WHERE NOT EXISTS (SELECT 1 FROM pending_channel_posts WHERE channel_id = '1159243585309384805' AND sort_order = 3);

INSERT INTO pending_channel_posts (channel_id, content, sort_order)
SELECT '1159243585309384805', $faq$**FINDING GAMES**

- **1v1 ranked queue:** F5 → Ranked tab → Search Ranked. When a match is found, both players have 90 seconds to click Ready — then the mod auto-connects you into a private room. Don't press Escape while it's loading; that cancels the connection (the mod recovers, but it costs time).
- **2v2:** F5 → 2v2 tab. Two queues: **Search Random** (auto-balanced teams by rating) and **Find Custom Lobby** (you pick your team — grab 3 friends). 2v2 has its own rating and leaderboard.
- **Tournaments:** F5 → Tournaments. A sync (same-time) tournament runs weekly — sign up, vote a time, the bracket auto-connects your matches. An async tournament runs every ~6 weeks with a week per round; coordinate with your opponent on Discord.
- **Playing a friend directly?** Private-room games between two modded, ranked-enabled players count as ranked automatically.$faq$, 4
WHERE NOT EXISTS (SELECT 1 FROM pending_channel_posts WHERE channel_id = '1159243585309384805' AND sort_order = 4);

INSERT INTO pending_channel_posts (channel_id, content, sort_order)
SELECT '1159243585309384805', $faq$**ECONOMY & COSMETICS**

- You earn **gold + XP** from every recorded match; ranked pays roughly double, winning pays more.
- **Shop (F5):** titles, trails, map color skins, nametag styles, body colors, cursors, effects — and community-made **character cosmetics** (faces, accessories), equipped in ROUNDS' own character editor (F8 or main-menu Characters).
- **Achievements (F5):** one-time challenges paying 100g each; some unlock exclusive titles.
- **Betting:** you can bet gold on other players' live ranked series — in-game from the Leaderboard tab's live panel, or from Discord via the live-bet buttons the bot posts. Bets lock once game 1 reaches 2 points. If a series never finishes, stakes are refunded automatically (~1 hour).
- **Link your Discord** with `/link` in the Discord server — connects your accounts for bet buttons, bug-report DMs, and server-booster gold perks.
- In-game chat: press **T** during a game. It bridges both ways with the #in-game-chat channel.$faq$, 5
WHERE NOT EXISTS (SELECT 1 FROM pending_channel_posts WHERE channel_id = '1159243585309384805' AND sort_order = 5);

INSERT INTO pending_channel_posts (channel_id, content, sort_order)
SELECT '1159243585309384805', $faq$**WHEN SOMETHING BREAKS**

- **"Mod disabled: other mods detected"** — remove every other BepInEx plugin. Vanilla ROUNDS + this mod only.
- **F5 does nothing / menu button gone** — restart ROUNDS. If it keeps happening, file a bug report.
- **Queue found a match but nothing happened** — usually the other player didn't ready in time; you're re-queued automatically. If you get stuck alone in a room, the mod returns you to the menu after ~60s, penalty-free.
- **Leaderboard/stats look frozen** — the server may be restarting; check #announcements, give it a minute.
- **Game froze or crashed?** Relaunch and rejoin your opponent — the series resumes.

**Filing a bug report (please do!):**
F5 → Settings → **Report a Bug**. Describe what happened and **tick the "attach log" box** — the log is what makes bugs fixable. You can file up to 10/day. If your Discord is linked, you'll get a DM when your report gets a response. Reports are triaged regularly and fixes are called out in #releases notes.

If the game is in a weird state a report can't capture, ping @Sid in #bug-reports with a screenshot.$faq$, 6
WHERE NOT EXISTS (SELECT 1 FROM pending_channel_posts WHERE channel_id = '1159243585309384805' AND sort_order = 6);
