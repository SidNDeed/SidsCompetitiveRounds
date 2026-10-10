-- 338_faq_channel_post_revisions.sql  (v1.41.0, item 11 — FAQ refresh)
--
-- WHAT THIS CHANGES
-- pending_channel_posts (109_artists_and_channel_posts.sql) is a fire-once
-- bus: the bot sends a row and the row is done. It has no message_id, so a
-- correction could only ever be a NEW message queued under the wrong text —
-- which is what 134_series_resume_forever.sql Part C did, adding a second
-- RANKED section as sort_order 7 and saying so in its own header. This
-- migration gives the table the revision-acked shape
-- 226_stream_channel_posts.sql already uses, so a correction edits the posted
-- message in place.
--
-- ADOPTING THE ALREADY-POSTED MESSAGES
-- message_id is deliberately left NULL for the six rows posted before this
-- migration existed: the bot that sent them discarded the id, so there is
-- nothing to backfill from.
-- Instead each already-delivered row keeps adopt_fingerprint: the text its
-- message carries, i.e. LEFT(content, 2000), because discord_bot.py sends
-- content[:2000]. (A moderation-case row is excluded — see section 1 — since
-- its marker is stripped before sending, so that equality would not hold.)
-- The bot adopts a live message ONLY on an exact match of
-- that fingerprint, records the id it found, and edits from then on. When no
-- message matches, the row stays pending and nothing is posted: the failure
-- direction is "the old text stays up", never "a duplicate appears" (#276).
--
-- The column is seeded here and MAINTAINED by the api from then on: the ack
-- that finishes a row — the one that holds the claim and names the row's
-- current revision — rewrites it to the text it just rendered. It has a second
-- reader besides the adoption scan, the hand-out's ambiguity test, which asks
-- whether any other row in the channel would scan for the same text; a value
-- frozen at delivery makes an already-corrected twin block its sibling for
-- ever over text its own message no longer carries. It lags for one window,
-- between a stale ack and the ack that finishes the row, on a row that by then
-- carries its message id and is therefore never found by text again.
--
-- The capture below covers every row delivered before this file runs. A row an
-- OLDER bot delivers AFTERWARDS is covered by handed_revision /
-- handed_fingerprint instead: the api records what it SERVED at the moment it
-- served it, and a revisionless ack — the only call shape a pre-338 bot can
-- make — persists exactly that pair. What an old bot displayed is what it was
-- handed in that poll, so a correction committed between the hand-out and the
-- ack leaves posted_revision behind revision WITH an exact fingerprint for the
-- text that is on Discord, and the upgraded bot adopts that message, binds its
-- id and edits forward. No hand-supplied message id is needed for that state.
--
-- The one state neither capture reaches: a row the PRE-338 api handed out (so
-- no handed_* was recorded), an old bot delivered, and a correction rewrote
-- before the new api was ever deployed. Its sent text is unrecoverable, it
-- stays pending, it is never re-sent, and its old message stays up. In this
-- release that state is unreachable — the only writer of a correction is
-- section 2 of this file, which runs in one transaction before the api deploy
-- — but it is stated rather than assumed away (#276).
--
-- MIGRATION NUMBER
-- 338 is item 11's reservation for the v1.41.0 batch: 339 belongs to the
-- Discord-collection item, 340/341 to this item's i18n keys/seed pair, 342 to
-- the ladder flip. Recorded here the way 233_ffa_early_leave_grace.sql:31-32
-- records the 231 race, because parallel branches otherwise each take "the
-- next number" from their own base (#553). The batch's own register of numbers
-- is a scratch file that does not exist outside the seat that wrote it, so
-- this comment is the tracked copy of the part that concerns 338 — a header
-- citing that file would send every other checkout somewhere empty, which is
-- the defect the touched-file sweep in test_faq_surfaces.py exists for
-- (test_no_file_this_item_touches_names_a_person_a_local_path_or_the_scratch_tree),
-- and which that sweep did not catch here until round 7 widened it.
--
-- RUN ORDER
--   1. this file          — the api's pending SELECT names the new columns
--   2. api, both boxes    — primary then standby
--   3. bot, primary only
-- The bot tolerates the old payload (no "revision" key => behave exactly as
-- before), so a bot that reaches production first cannot mis-ack; the api
-- cannot run before the columns exist, which is why step 1 is strict.
--
-- Explicit BEGIN/COMMIT: the deploy wrapper runs psql -f, which autocommits
-- statement by statement otherwise (#340). Every statement is idempotent, so
-- the wrapper's retry re-runs the whole file safely (#243).

BEGIN;

-- ── 1. The revision-acked columns ────────────────────────────────────────
ALTER TABLE pending_channel_posts ADD COLUMN IF NOT EXISTS message_id        TEXT;
ALTER TABLE pending_channel_posts ADD COLUMN IF NOT EXISTS revision          INTEGER NOT NULL DEFAULT 1;
ALTER TABLE pending_channel_posts ADD COLUMN IF NOT EXISTS posted_revision   INTEGER;
ALTER TABLE pending_channel_posts ADD COLUMN IF NOT EXISTS adopt_fingerprint TEXT;
-- The poller's claim, and WHO holds it. This bus had none: the pending SELECT
-- was a plain read, so two pollers could each receive the same never-posted
-- row and each send it, with the ack — which happens AFTER the send — as the
-- only thing between them and two copies in the channel. The api now hands out
-- and claims in one statement.
--
-- claimed_at alone was not enough, and the reason is worth the column. Round
-- three released the claim on the FIRST ack of any kind, including the "stale"
-- one that exists to say "keep going, you are mid-render" — so a second poller
-- could take the row while the first was still rendering it, and two renderers
-- then wrote two revisions to one message in an order nobody controls. The
-- claim is now the UNIT OF EXCLUSIVE RENDERING: claimed_token identifies the
-- holder, every ack that records a revision or moves the fingerprint must
-- present it, an ack from a non-claimant does neither, and a stale answer
-- keeps the claim so the SAME poller renders forward. A non-claimant's ack is
-- not discarded whole, though: a DELIVERY it reports is recorded, because the
-- bot's sent-memory is in-process and a delivery the database never heard
-- about is re-sent at the next restart (#105).
--
-- The claim is released when the row is fully current (acked revision =
-- revision), when the caller asks for release at the two-render cap, when the
-- revisionless poller the row was handed to acks (it can render nothing
-- further), or by lease expiry — the only route a crash takes, which is why it
-- expires rather than needing a cleanup that might never run (#276/#430). Each
-- of the first three is refused to a caller that is neither the holder nor
-- that poller, so none of them is a way to take a claim off somebody else.
-- bind_only never releases: that row is mid-render.
ALTER TABLE pending_channel_posts ADD COLUMN IF NOT EXISTS claimed_at        TIMESTAMPTZ;
ALTER TABLE pending_channel_posts ADD COLUMN IF NOT EXISTS claimed_token     UUID;

-- What the last hand-out SERVED, and WHO it served, recorded by the hand-out
-- itself. The first two are not delivery facts — nothing here says anything is
-- on Discord — they are the api's record of what it put on the wire, which is
-- the only thing a caller that cannot name a revision could possibly have
-- rendered. The revisionless ack (a pre-338 bot) persists this pair as
-- posted_revision / adopt_fingerprint, so a correction committed between
-- hand-out and ack leaves the row locatable by an EXACT fingerprint instead of
-- by a derivation. handed_fingerprint is LEFT(content, 2000) because the bot
-- sends content[:2000]; a moderation-case row gets NULL, because the bot strips
-- that row's marker before sending and the stored string is therefore not what
-- goes to Discord.
--
-- handed_revisionless is what makes reading that pair back safe. It is TRUE
-- when the poll that took the row did NOT ask for revisions — i.e. the caller
-- can neither name a revision nor present a token, which is the pre-338 shape
-- and nothing else. The pair always describes the LAST hand-out, so without
-- this flag a tokenless ack arriving after a revision-capable poller had taken
-- the row would read that poller's record as its own and clear its claim
-- mid-render. FALSE is the safe default: a row nobody has been handed since
-- this file ran authorizes no revisionless ack, and the first poll of either
-- kind sets the flag to what is true of that poll.
ALTER TABLE pending_channel_posts ADD COLUMN IF NOT EXISTS handed_revision   INTEGER;
ALTER TABLE pending_channel_posts ADD COLUMN IF NOT EXISTS handed_fingerprint TEXT;
ALTER TABLE pending_channel_posts ADD COLUMN IF NOT EXISTS handed_revisionless BOOLEAN NOT NULL DEFAULT FALSE;

-- Everything already delivered rendered revision 1. Without this backfill
-- every historical row would read as "revision 1 never rendered" and the bot
-- would re-post the entire archive.
UPDATE pending_channel_posts
   SET posted_revision = 1
 WHERE posted_at IS NOT NULL
   AND posted_revision IS NULL;

-- The fingerprint is captured BEFORE section 3 rewrites any content, so it
-- describes what is on Discord right now rather than what we want there.
--
-- A moderation-case row is EXCLUDED, and the exclusion is what makes the
-- column's promise true. Such a row's content opens with the api's
-- [MODCASE:<uuid>] marker, which the bot strips before sending, so
-- LEFT(content, 2000) is NOT what was posted for it and an adoption keyed on
-- that string could never match. A moderation post is fire-once and is never
-- corrected, so it needs no fingerprint at all; leaving it NULL says that,
-- where a wrong value would have read as a capability the row does not have.
--
-- handed_* is filled from the SAME capture, and the claim it makes is checked
-- rather than assumed: the pre-338 api's pending SELECT served `content` and
-- the pre-338 bot sent content[:2000], so for a row delivered before this file
-- runs, LEFT(content, 2000) IS what was handed to the bot that delivered it.
-- That holds only because nothing ever rewrote a row's content: 110 and 134
-- INSERT, and no other migration in backend/sql touches this table's content
-- at all (section 2 below is the first, and it runs after this statement).
-- handed_revision is 1 because the column did not exist before this file and
-- every delivered row is at the seed revision until section 2 moves it.
--
-- handed_revisionless is deliberately NOT set here, and keeps its FALSE
-- default. These rows have already been delivered and acked; the flag exists
-- to authorize the NEXT tokenless ack, so claiming one on a row no bot is
-- holding would be an authorization backdated to a hand-out this file never
-- made. The first poll of either kind sets it to what is true of that poll,
-- and for a row the pre-338 api handed out and an old bot acks afterwards the
-- pair is NULL anyway, so the ack records the delivery and nothing else —
-- which is exactly what that ack could prove.
UPDATE pending_channel_posts
   SET adopt_fingerprint   = LEFT(content, 2000),
       handed_fingerprint  = LEFT(content, 2000),
       handed_revision     = 1
 WHERE posted_at IS NOT NULL
   AND adopt_fingerprint IS NULL
   AND content NOT LIKE '[MODCASE:%';

-- The bot polls for rows whose rendered revision lags the desired one. A
-- never-posted row has posted_revision NULL, which IS DISTINCT FROM 1, so
-- the original fire-once behaviour still falls out of this one predicate.
CREATE INDEX IF NOT EXISTS idx_pending_channel_posts_unrendered
    ON pending_channel_posts (sort_order, id)
 WHERE posted_revision IS DISTINCT FROM revision;

-- ── 2. The corrected #scr-faq sheet ──────────────────────────────────────
-- Bodies are docs/FAQ.md's six "## Message N" sections verbatim;
-- backend/tests/test_faq_surfaces.py re-derives them and fails on any drift.
-- Corrected against the code this release ships. Anchored by SYMBOL rather
-- than by line: a line number written into a comment is stale the next time
-- anything above it moves (#432). The executable version of this list is
-- backend/tests/fixtures/faq_claims.json, which re-reads the code itself.
--   msg 4  async tournaments follow the BRACKET, not a 6-week calendar:
--          tournaments.ASYNC_POST_COMPLETION_DAYS (2), applied to a COMPLETED
--          bracket's ended_at in _ensure_next_tournament; a cancelled bracket
--          is held only by the 24h safety net above it. ASYNC_CADENCE_DAYS is
--          legacy and drives nothing. The FFA target a game actually plays to
--          is the LOBBY ROW's score_target (ffa_lobbies.score_target, DEFAULT
--          5 since 176, mirrored by FFA_CONFIG_DEFAULTS and read through
--          _ffa_lobby_config); FFA_ROUNDS_TO_WIN is the validation fallback
--          for a row that predates the column. The host may set 3-10, bounded
--          by ck_ffa_lobby_score_target server-side and clamped by
--          FfaMode.SetPendingConfig client-side.
--   msg 5  achievements pay ACHIEVEMENT_GOLD (100) by default and 300/500/
--          1000 for the keys listed in ACHIEVEMENT_GOLD_OVERRIDES. Bet
--          refunds are _prune_stale_series' cutoff_min (30 min, no game ever
--          reported) and stalled_min (60 min, stalled mid-series) — two
--          windows, where the sheet quoted one "~1 hour". Both of those
--          modes select `rs.is_tournament = FALSE`, so a tournament series is
--          in NEITHER clock; its stakes are settled by mode 3 off the
--          bracket's own terminal row, which the sheet now says.
--   msg 6  the lone-room return is per mode, not a flat 60s: GameStateWatcher
--          bails at 60 / 90 / 120 / 360 s for a 1v1 / 2v2-or-1v2 / FFA /
--          tournament room.
-- The content guard makes this convergent, not just idempotent: a re-run
-- after the text already landed matches nothing and bumps no revision.
--
-- NO CONTACT LINE IS INTRODUCED HERE. These bodies REPLACE the content of the
-- six rows 110_faq_channel_post.sql seeded (matched on channel_id +
-- sort_order), so there is one row per message before and after. The single
-- contact sentence, in msg 6, is carried through byte-for-byte from
-- 110_faq_channel_post.sql:88 rather than re-authored; that line is the one
-- entry that owns it. test_no_new_contact_line_is_introduced in
-- backend/tests/test_faq_surfaces.py extracts every line of these bodies that
-- routes a reader to a person — an @handle, or a DM/ping/contact/reach-out
-- verb — and compares the MULTISET against 110's own bodies, so a genuinely
-- new routing sentence fails, and so does a SECOND copy of this one in
-- another message. What it does not do is judge wording it cannot recognise
-- as routing; that bound is stated in the test rather than implied here.
WITH want (sort_order, content) AS (
    VALUES
    (1, $faq1$**INSTALLING THE MOD**

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

Press **F5** in-game to open the competitive menu. That's the hub for everything: queue, stats, leaderboard, shop, settings.$faq1$)
  , (2, $faq2$**UPDATING**

- **Installer version:** the mod checks for updates when ROUNDS starts and applies them when the game **closes**. So if a new version just dropped: launch → quit → launch again and you're on it. The F5 menu shows your version + the latest in the top corner.
- **Thunderstore version:** update through r2modman/Thunderstore like any other mod.
- If your version is too old, the server refuses to talk to it and the mod tells you to update — nothing counts until you do.
- Not sure what version you're on? F5 — it's in the header. Compare with the pinned #releases post.$faq2$)
  , (3, $faq3$**RANKED — HOW A GAME QUALIFIES**

A match records as **ranked** only when **both** players:
1. Have the mod installed and running, and
2. Have ranked enabled (F5 → Ranked tab → the Enable/Disable button).

Everything else records as **casual** (still tracked, no rating change). The mod shows a notice at match start when your opponent isn't ranked-capable, so you know before you invest 10 minutes.

- Games vs vanilla (unmodded) players can never be ranked.
- Ranked queue matches (F5 → Search Ranked) are always ranked — queueing is consent.
- Ranked plays as a **best-of-3 series** vs the same opponent. Ratings (Glicko-2) apply when the series completes.
- If a series gets interrupted (crash, disconnect), just rematch the same player — the series **resumes where it left off**, no matter how much later. Unfinished series never expire, so leaving mid-series can't save your rating.
- Leaving mid-series counts as a DC on your record; your leave % is visible on the leaderboard. Occasional crashes won't tank it, rage-quits will.$faq3$)
  , (4, $faq4$**FINDING GAMES**

- **1v1 ranked queue:** F5 → Ranked tab → Search Ranked. When a match is found, both players have 90 seconds to click Ready — then the mod auto-connects you into a private room. Don't press Escape while it's loading; that cancels the connection (the mod recovers, but it costs time).
- **2v2:** F5 → 2v2 tab. Two queues: **Search Random** (auto-balanced teams by rating) and **Find Custom Lobby** (you pick your team — grab 3 friends). 2v2 has its own rating and leaderboard.
- **1v2:** F5 → 1v2 tab. One solo against a duo — separate Solo and Duo leaderboards, and the solo can take an extra starting pick if the lobby enables it.
- **FFA:** F5 → FFA tab. 3-10 players, everyone for themselves — last one standing scores, first to **5** points wins by default (the host can set that target anywhere from 3 to 10), everyone picks cards at the same time. Own rating and leaderboard.
- Queue searches cap at **30 minutes** in every mode — you'll get an in-game notice if you hit it; just rejoin if you're still around.
- **Tournaments:** F5 → Tournaments. A sync (same-time) tournament runs weekly — sign up, vote a time, the bracket auto-connects your matches. An async tournament follows the bracket, not a calendar: the next one opens **2 days after the previous one finishes**, and if that one was cancelled (or never recorded a finish) only **24 hours** after it was created, so a bracket that failed to fill doesn't cost everyone a wait. Each round has a **7-day** deadline; coordinate with your opponent on Discord.
- **Playing a friend directly?** Private-room games between two modded, ranked-enabled players count as ranked automatically.$faq4$)
  , (5, $faq5$**ECONOMY & COSMETICS**

- You earn **gold + XP** from every recorded match; ranked pays roughly double, winning pays more.
- **Shop (F5):** titles, trails, map color skins, nametag styles, body colors, cursors, effects — and community-made **character cosmetics** (faces, accessories), equipped in ROUNDS' own character editor (F8 or main-menu Characters).
- **Achievements (F5):** one-time challenges paying **100g** by default — the hardest pay 300g, 500g or 1000g; some unlock exclusive titles.
- **Betting:** you can bet gold on other players' live ranked series — in-game from the Leaderboard tab's live panel, or from Discord via the live-bet buttons the bot posts. Bets lock once game 1 reaches 2 points. If a series never finishes, stakes are refunded automatically: after 30 minutes when no game was ever reported, after 60 minutes when it stalls mid-series. Tournament series sit outside both clocks — a tournament bet settles on the bracket instead, and a forfeited or bye'd match refunds its stakes.
- **Link your Discord** with `/link` in the Discord server — connects your accounts for bet buttons, bug-report DMs, and server-booster gold perks.
- In-game chat: press **T** during a game. It bridges both ways with the #in-game-chat channel.$faq5$)
  , (6, $faq6$**WHEN SOMETHING BREAKS**

- **"Mod disabled: other mods detected"** — remove every other BepInEx plugin. Vanilla ROUNDS + this mod only.
- **F5 does nothing / menu button gone** — restart ROUNDS. If it keeps happening, file a bug report.
- **Queue found a match but nothing happened** — usually the other player didn't ready in time; you're re-queued automatically. If you get stuck alone in a room the mod warns you, then returns you to the menu on its own — 60s in 1v1, 90s in 2v2 and 1v2, 2 min in FFA, 6 min in a tournament room (the server gives your tournament opponent a longer grace). No penalty either way.
- **Leaderboard/stats look frozen** — the server may be restarting; check #announcements, give it a minute.
- **Game froze or crashed?** Relaunch and rejoin your opponent — the series resumes.

**Filing a bug report (please do!):**
F5 → Settings → **Report a Bug**. Describe what happened and **tick the "attach log" box** — the log is what makes bugs fixable. You can file up to 10/day. If your Discord is linked, you'll get a DM when your report gets a response. Reports are triaged regularly and fixes are called out in #releases notes.

If the game is in a weird state a report can't capture, ping @Sid in #bug-reports with a screenshot.$faq6$)
)
UPDATE pending_channel_posts p
   SET content  = w.content,
       revision = p.revision + 1
  FROM want w
 WHERE p.channel_id = '1159243585309384805'
   AND p.sort_order = w.sort_order
   AND p.content IS DISTINCT FROM w.content;

-- ── 3. Post-check ────────────────────────────────────────────────────────
DO $chk$
DECLARE
  cols    INTEGER;
  idx     INTEGER;
  pending INTEGER;
BEGIN
  SELECT COUNT(*) INTO cols
    FROM information_schema.columns
   WHERE table_name = 'pending_channel_posts'
     AND column_name IN ('message_id', 'revision', 'posted_revision',
                         'adopt_fingerprint', 'claimed_at', 'claimed_token',
                         'handed_revision', 'handed_fingerprint',
                         'handed_revisionless');
  IF cols <> 9 THEN
    RAISE EXCEPTION 'migration 338: expected 9 revision columns on pending_channel_posts, found % - nothing committed', cols;
  END IF;

  SELECT COUNT(*) INTO idx
    FROM pg_indexes
   WHERE tablename = 'pending_channel_posts'
     AND indexname = 'idx_pending_channel_posts_unrendered';
  IF idx <> 1 THEN
    RAISE EXCEPTION 'migration 338: partial index idx_pending_channel_posts_unrendered missing - nothing committed';
  END IF;

  -- Not an assertion: a database that never ran 110 legitimately has no FAQ
  -- rows, and the local test database is exactly that. The count is printed
  -- so a production run that silently corrected nothing is visible in the
  -- deploy log instead of inferable from it (#342).
  SELECT COUNT(*) INTO pending
    FROM pending_channel_posts
   WHERE channel_id = '1159243585309384805'
     AND posted_revision IS DISTINCT FROM revision;
  RAISE NOTICE 'migration 338: % FAQ row(s) queued for an in-place correction', pending;
END $chk$;

COMMIT;
