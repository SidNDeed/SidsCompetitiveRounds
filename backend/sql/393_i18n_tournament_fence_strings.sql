-- 393: i18n client keys and machine-translation seeds for the tournament fence
-- re-author (the Aug 31 fence batch, whose migration 269 is a different file on main).
-- Four client keys, from the regenerated tools/i18n_source.json:
--   * "Couldn't leave the tournament - it may have locked or started" - the toast
--     ApiClient.TournamentUnsignup shows when the server refuses a leave; it replaces
--     the bare "Failed" literal, which leaves the source registry;
--   * "Tournament info is refreshing - try again in a moment" - the toast the
--     painted-snapshot click fence (NativeUI.TFencedTournament) shows when a click
--     lands on a snapshot the panel has not finished painting;
--   * the two tournament rulebook bodies (InfoLibrary TournHow and TournForfeits),
--     re-keyed because one bullet in each now says that after lock the way out is the
--     No answer on the bot's availability-check DM.
-- KEYS: the additive half of what POST /admin/i18n/sync-keys does, written through the
-- migration channel (learning #443). Same contract as 379 and 384: key_id =
-- sha1("client\0" + English)[:16], source_hash = sha1(English), sensitive and context
-- exactly as tools/i18n_sync_keys.build_client_keys derives them, so this file and the
-- next sync write the same row. The keys this edit supersedes ("Failed" and the two
-- previous bodies) are NOT retired here: retirement by absence belongs to the key sync
-- that ships with the client (learning #1032), and the shipped client still shows them.
-- KEY HASH GUARD (the source migration 269's refusal, restored by the Codex FENCE-R1
-- H1). A client key_id is derived from its English, so an existing row at one of these
-- four ids whose source_hash is not the one written here cannot be a re-key of this
-- text: it is a damaged row or an id collision. The guard RAISES on such a row, live or
-- retired, before any write, and the key arm's ON CONFLICT updates only a row whose
-- source_hash already matches, so a different-hash row that appears after the guard
-- has read is left as it is and fails the post-check. The exception is a re-keyed
-- body, and it never shares an id: the edited TournHow and TournForfeits bodies arrive
-- under NEW key_ids, while the superseded body rows keep their own ids, hashes, entries
-- and proposals, live or retired, and this file neither compares nor writes them. The
-- one retired row it does change is a SAME-hash row at one of its own ids (an earlier
-- landing of this exact text that a later key sync retired), which it makes live again.
-- SEEDS: PENDING proposals for the two toasts only (2 keys x es/ru/uk/sv = 8 pairs),
-- same contract as 385: sentinel proposer 'claude-mt', license_assent TRUE at the
-- machine-v1 terms revision; the same text as the bundled plugin/I18nCatalogues.cs
-- drafts. The body translations ride the bundled catalogue only.
-- Every literal is a single-line E'' string, so the stored text never depends on the
-- line endings of the checkout that applies this file.
-- IDEMPOTENT: the key arm updates a row only WHERE it differs from the value written
-- here (IS DISTINCT FROM over every column the arm sets, retired_at included), and a
-- seed pair is skipped while any pending proposal exists for it, while a claude-mt
-- draft of the same text exists in any status, and while a CURRENT approved
-- translation exists (approved against this source_hash: approving a machine draft
-- queued over it would overwrite it; the source migration 269's rule, restored by the
-- Codex FENCE-R1 H2), so a second run writes no row. Both post-checks RAISE, and
-- nothing is committed, unless all four keys are live with the expected metadata and
-- all eight seed pairs are covered by a pending proposal or an approved translation of
-- the CURRENT source text (the seed post-check; the source migration 269's rule,
-- restored by the Codex FENCE-R1 H3). So a pair whose claude-mt draft of this text was
-- rejected, or whose only pending proposal is of another text, stops the file: it does
-- not re-propose a rejected machine text, and it does not commit an uncovered pair.
-- Explicit transaction (#340).
-- DEPLOY ORDER: this file first, then the api and the bot. No api or bot code names
-- these four keys or their proposals: both builds read them only through the same
-- generic i18n routes, so neither order breaks the code, and applying this file
-- first lets any refusal described here stop a landing before any code deploys.
-- BOUNDS, set right after BEGIN: lock_timeout ends any single lock WAIT at 5 s (it
-- applies per acquisition, learning #689, so it bounds each wait, not their sum);
-- statement_timeout gives EACH top-level statement its own 25 s; and
-- idle_in_transaction_session_timeout ends the session, and the server rolls the
-- transaction back, when the runner stops for 5 s between statements. The statement
-- and idle budgets are separate and PostgreSQL 16 has no transaction_timeout, so the
-- longest this file can hold i18n locks before its COMMIT is their SUM: up to 25 s in
-- the statement that takes them plus up to 5 s waiting for COMMIT, 30 s in all. The
-- sum holds only because ALL the work below is ONE statement, a single DO block whose
-- inner statements share its 25 s: every further top-level statement would bring a
-- 25 s budget of its own. Any timeout that fires aborts the whole file with nothing
-- committed.
-- THE COMMIT. PostgreSQL disables the statement timer before it commits, so the
-- COMMIT's own work is outside every timeout above, and the locks are held until it
-- ends. The fourth line, synchronous_commit = local, keeps that work LOCAL: it never
-- waits for a standby's confirmation, whatever synchronous_standby_names says now or
-- later (read on the primary 2026-10-30: empty, synchronous_commit on, server 16.15).
-- BOUNDED: everything before COMMIT -- each lock wait (5 s, and every one sits inside
-- the DO block's 25 s) and the hold up to COMMIT (statement 25 s + idle 5 s = 30 s).
-- NOT BOUNDED: the COMMIT's local completion -- the WAL flush and the
-- transaction-status (pg_xact) write, which can read an evicted page -- I/O that no
-- PostgreSQL setting bounds, for this or any transaction. The hold is therefore 30 s
-- plus the COMMIT's local completion.
-- ROLLBACK: rollback_393_i18n_tournament_fence_strings.sql.

BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL idle_in_transaction_session_timeout = '5s';
SET LOCAL statement_timeout = '25s';
SET LOCAL synchronous_commit = local;

-- ALL the work is this one statement (see BOUNDS): 1. the key hash guard, 2. the four
-- keys and their post-check, 3. the seeds, 4. the seed coverage post-check.
DO $m393$
DECLARE
    clash      TEXT;
    v_expected INT := 4;
    v_ok       INT;
    uncovered  INT;
    sample     TEXT;
BEGIN
    -- 1. Key hash guard (see the header): before any write, refuse an existing row at
    --    one of the four ids whose source_hash is not the one this file writes.
    SELECT string_agg(k.key_id || CASE WHEN k.retired_at IS NULL THEN ' (live)' ELSE ' (retired)' END,
                      ', ' ORDER BY k.key_id)
      INTO clash
      FROM i18n_keys k
      JOIN (VALUES
        (E'c4d5526dfaef7312', E'0d891dd93ff117f9cb982affdfdf2659f6fec53e'),
        (E'8b0f70cb42c1cda3', E'e3303e8feef02cd0711fbca17db104b380e423c2'),
        (E'f76648a14f012b93', E'dde2afe15d21de6b5ce4e0a459c84f911313a441'),
        (E'fc5b6244bdd13c72', E'3960e8a1336364cf16f4a14fde90e1b691431c08')
      ) AS x(key_id, source_hash) ON x.key_id = k.key_id
     WHERE k.source_hash IS DISTINCT FROM x.source_hash;
    IF clash IS NOT NULL THEN
        RAISE EXCEPTION 'migration 393: key % already present with a different source_hash; a client key_id is derived from its English, so this is a damaged row or an id collision, never a re-key; nothing committed', clash;
    END IF;

    -- 2. The four keys: inserted, or a same-hash row brought to exactly these values.
    INSERT INTO i18n_keys (key_id, namespace, msgctxt, source_hash, sensitive, max_px, context, updated_at)
    SELECT v.key_id, v.namespace, v.msgctxt, v.source_hash, v.sensitive, NULL, v.context, clock_timestamp()
      FROM (VALUES
(E'c4d5526dfaef7312', 'client', E'Couldn\'t leave the tournament - it may have locked or started', E'0d891dd93ff117f9cb982affdfdf2659f6fec53e', FALSE, CAST(E'ApiClient · TournamentUnsignup' AS VARCHAR(160))),
(E'8b0f70cb42c1cda3', 'client', E'Tournament info is refreshing - try again in a moment', E'e3303e8feef02cd0711fbca17db104b380e423c2', FALSE, CAST(E'NativeUI · TFencedTournament' AS VARCHAR(160))),
(E'f76648a14f012b93', 'client', E'Tournaments are 8-16 player double-elimination brackets of best-of-3 series, run end to end by the mod and the bot. There are two kinds: <color=#7FD4FF>Sync</color> (the whole bracket plays out in one sitting) and <color=#7FD4FF>Async</color> (each match has a week to happen). Both are ranked - every game moves your normal 1v1 rating.\n\n<color=#FFD94D><b>THE TWO KINDS</b></color>\n\n<color=#7FD4FF>Sync</color> - weekly. The default start is Saturday at noon Pacific time, but the field votes on the real time: signing up includes marking which start times you can make, from 8 slots at 6-hour steps around the default. The tournament locks 48 hours before the DEFAULT start - the voted time can sit up to a day to either side of it.\n\n<color=#7FD4FF>Async</color> - a new one opens 2 days after the previous one finishes. Signups run for 7 days, then it locks and starts immediately. Every match has a 7-day deadline (check-ins can add a day), so a full bracket takes roughly 6-9 weeks depending on how fast people play.\n\n<color=#FFD94D><b>SIGNING UP</b></color>\n\n- Sign up on the F5 Tournaments tab. A linked Discord account is required - the bot runs everything by DM (see <color=#7FD4FF>The bot & check-ins</color>).\n\n- Sync signups must mark at least one start time. Signing up again replaces your time votes.\n\n- You can un-sign freely during voting. After lock the in-game button closes - withdrawing then happens by answering <b>No</b> on the bot\'s availability-check DM. <color=#FF6666>Once the tournament is running you can\'t un-sign at all</color> - from there, not showing up is a forfeit and counts on your no-show %.\n\n- The field caps at 16. Signups past the cap become <color=#7FD4FF>speculative</color>: they don\'t play, but they are the backfill pool - if a confirmed player leaves before the start, the most reliable speculative inherits their seat. Ordering into the 16 (and out of the pool) goes by no-show % first, then signup time.\n\n- Your <color=#7FD4FF>no-show %</color> is a rolling 90-day measure of tournaments you signed up for and then missed. Old misses fade out over the 90 days.\n\n<color=#FFD94D><b>HOW THE LOCK WORKS</b></color>\n\n- Sync locks 48 hours before the default start. It needs at least 8 confirmed players AND one time slot at least 8 signups (speculatives included) can make; otherwise the whole tournament pushes back one week and your votes carry forward.\n\n- The winning slot becomes the start time. <color=#FF6666>If you didn\'t mark the winning slot, your signup is removed</color> - no penalty, and the bot DMs you why. Speculatives promote into the freed seats.\n\n- Sync can also start early: once at least 8 players are in, every confirmed player pressing <color=#7FD4FF>Force Start</color> on the tab within 10 minutes of each other starts the tournament 10 minutes later.\n\n- Async has no time vote - after the 7-day signup window it locks on player count alone and starts right away.\n\n- Locking snapshots the prize pool at the confirmed player count and clears any ranked blocks between participants - signing up opts you in to playing whoever else signed up.\n\n<color=#FFD94D><b>SEEDING AND THE BRACKET</b></color>\n\n- Your seed is your 1v1 rating snapshotted at lock; the highest rating is seed 1. Pairing is standard bracket placement, with seeds 1 and 2 starting in opposite halves. Seed numbers stay hidden until the tournament starts, so nobody can work out their round-1 opponent in advance.\n\n- With 9 to 15 players the bracket is built for 16 and the top seeds get round-1 byes to fill the gap.\n\n- Double elimination in plain terms: lose a winners-bracket match and you drop into the losers bracket; lose there and you\'re out. The losers-bracket champion meets the winners-bracket champion in the grand final - and if the losers-bracket champion wins it, one extra deciding match is played, because the winners-bracket champion hadn\'t lost a series yet.\n\n- Every match is a best-of-3, played as a normal ranked series.\n\n<color=#FFD94D><b>SYNC PLAY DAY</b></color>\n\nThe whole contract is: <color=#7FE87F>have ROUNDS open at the start time - sitting at the main menu is fine.</color> The mod does everything else.\n\n- While ROUNDS runs, the mod pings the server every 20 seconds; you count as present while your last ping is under 2 minutes old. The F5 menu never needs to be open.\n\n- From 15 minutes out you get a reminder DM and an in-game countdown banner; every match-ready moment gets its own DM too (see <color=#7FD4FF>The bot & check-ins</color>).\n\n- When your match is ready and both players are present, the mod connects you automatically - green banner, match-found sound, taskbar flash. If you\'re mid-casual-game you get a red banner instead, and the mod pulls you out of that room with no disconnect penalty.\n\n- Matches give a 10-minute show-up grace. If your opponent never joins your room, the mod warns you at 90 seconds and returns you to the menu after 6 minutes - you stay ready, and the server forfeits the match to you if they don\'t show.\n\n- Between your matches there\'s a 7-minute breather with the next room already prepared. Both players pressing <color=#7FD4FF>Play Now</color> on the Tournaments tab starts it early.\n\n- The server picks each match\'s connection region for both players, so you always land in the same room whatever your menu region is set to.\n\n<color=#FFD94D><b>PLAYING AN ASYNC MATCH</b></color>\n\n- When your match goes live the bot DMs both of you with the deadline. There\'s no start instant, no auto-connect, and no room code from the bracket.\n\n- Agree a time with your opponent (use /dm-opponent in Discord, or just message them), then play a normal private lobby: main menu, Online, Host Room, and one of you sends the other the 6-character code.\n\n- The result records automatically as long as you both have the mod running with <color=#7FD4FF>Ranked enabled</color> - the server binds the series to your bracket pairing from any room. The mod turns Ranked on for you when a tournament match is live (see <color=#7FD4FF>Deadlines & forfeits</color>).\n\n- In the final 24 hours before the deadline the bot sends a check-in DM; answering that you plan to play today extends the deadline 24 hours, once per opponent.', E'dde2afe15d21de6b5ce4e0a459c84f911313a441', TRUE, CAST(E'InfoLibrary · (file scope)' AS VARCHAR(160))),
(E'fc5b6244bdd13c72', 'client', E'What happens when someone doesn\'t show up, quits, or leaves a tournament - and exactly how prizes are computed. Short version: <color=#7FE87F>a finished series always stands</color>, absence is what gets punished, and forfeit wins never pay podium prizes.\n\n<color=#FFD94D><b>DEADLINES</b></color>\n\n- Sync: matches give a 10-minute show-up grace from the moment they go ready. A match that follows a PLAYED match sits in a 7-minute breather first (a bye-fed match can go ready immediately), and a match still in its breather can never forfeit anyone. While both players are present the server waits - a sync match can run past its deadline.\n\n- Async: every match, the grand-final reset included, has a 7-day deadline from the moment it goes live. The deadline check-in DM can extend it 24 hours, once per opponent. Presence doesn\'t spare an async match - only playing does.\n\n<color=#FFD94D><b>WHEN THE DEADLINE HITS</b></color>\n\nThe server resolves an overdue match in this exact order - the first rule that applies decides it:\n\n- 1. <color=#7FE87F>A finished series always stands</color> - nothing overrides a played result.\n- 2. If exactly one seat is banned, the other player advances immediately.\n- 3. A game reported in the last 45 minutes means a live series - the match is left alone.\n- 4. Sync only: both players present - the server keeps waiting.\n- 5. Exactly one player present - <color=#FF6666>the absent player forfeits</color> and the present one advances.\n- 6. Otherwise: if the series was started and the score is uneven, the score leader advances. Failing that, if exactly one of you answered the async deadline check-in - any answer - that player advances over the silent one. Failing that too, the lower no-show % advances, and a dead tie falls to a fixed arbitrary tiebreak.\n\nOnly absent seats get the no-show mark (a banned seat forfeits regardless of presence, and a silent seat can lose the async tiebreaks while present). Your <color=#7FD4FF>no-show %</color> is a rolling 90-day rate that decides your priority into future tournaments, backfill order, and these tiebreaks.\n\n<color=#FFD94D><b>WHAT A FORFEIT DOES - AND DOESN\'T</b></color>\n\n- The bracket advances exactly as if the match completed - the winner moves on, the loser drops or is out.\n\n- <color=#FF6666>A forfeit mints nothing.</color> Podium placements only exist for played, completed series - a forfeit-decided podium spot pays no prize.\n\n- No rating moves. Rating only changes when a series completes; a forfeited match\'s series is simply never completed or scored.\n\n- Betting closes: a forfeited match\'s series can\'t be bet on.\n\n<color=#FFD94D><b>LEAVING, AND WHO REPLACES YOU</b></color>\n\n- During voting: un-sign freely.\n\n- After lock, before the start: answering <b>No</b> on the bot\'s availability-check DM withdraws you and runs the backfill flow - the most reliable speculative signup takes your exact bracket slot (with their own rating); no speculative available means your would-be opponents get byes. Leaving this way carries no penalty. If you have no answerable DM left, you\'re expected to show - a no-show forfeits and counts on your no-show %.\n\n- Once running: you can\'t un-sign. Not showing up forfeits your matches and counts on your no-show %.\n\n- Quitting mid-game follows normal 1v1 disconnect rules: the DC lands on your leave %, and unless your opponent was at match point (then they take the game, which can finish the series) the series stays open at its score. The deadline sweep resolves an abandoned series: after the 45-minute grace a still-present opponent wins; if both walked away, the score leader advances.\n\n<color=#FFD94D><b>THE RANKED OVERRIDE</b></color>\n\n- When one of your tournament matches is live and your Ranked toggle is off, the mod flips it ON and tells you. Async matches happen in private lobbies, which only record as ranked when both players have Ranked enabled - the override guarantees your result records.\n\n- <color=#FF6666>It stays ON after the match.</color> There is no auto-revert: turn it off in Settings if you don\'t want later games rated. Turning it off between tournament matches gets it flipped back on when your next match goes live.\n\n<color=#FFD94D><b>PRIZES, TROPHIES AND BETTING</b></color>\n\n- The pool scales with the player count snapshotted at lock. At 8 players: 1000 / 600 / 120 Gold and 5000 / 3000 / 150 XP for 1st / 2nd / 3rd. It grows linearly with the field, doubling at 16 players: 2000 / 1200 / 240 Gold and 10000 / 6000 / 300 XP.\n\n- <color=#7FE87F>Prizes pay when the whole bracket completes</color>, not when your final match ends. A forfeit-decided rank is skipped rather than passed down.\n\n- <color=#8A8A93>Prize XP behaves like any other XP: it converts to Gold at the usual 100 XP = 1 Gold, and a level boundary it crosses pays the normal level reward.</color>\n\n- Trophies are Discord roles: SCR Tournament Winner, Runner Up, and 3rd Place; a second same placement upgrades the role to its (x2) version. Every confirmed participant gets the Participant role. Roles only go out for brackets of 16 or more players. Winning or taking 2nd in a tournament also unlocks a paying achievement (separate ones for sync and async), and playing a bracket through without ever forfeiting unlocks Iron Bracket.\n\n- Every tournament game is a normal ranked best-of-3: it moves your regular 1v1 rating whether or not you reach the podium.\n\n- Tournament matches are bettable on the same terms as any live ranked series: betting locks at 2 live points in game 1 or once any game is decided. An async pairing that waits days stays bettable the whole wait at 0-0.', E'3960e8a1336364cf16f4a14fde90e1b691431c08', TRUE, CAST(E'InfoLibrary · (file scope)' AS VARCHAR(160)))
      ) AS v(key_id, namespace, msgctxt, source_hash, sensitive, context)
    ON CONFLICT (key_id) DO UPDATE
       SET namespace = EXCLUDED.namespace, msgctxt = EXCLUDED.msgctxt,
           sensitive = EXCLUDED.sensitive, max_px = EXCLUDED.max_px,
           context = EXCLUDED.context, retired_at = NULL, updated_at = clock_timestamp()
     -- never a different-hash row (the key hash guard): it stays as found and fails the post-check
     WHERE i18n_keys.source_hash = EXCLUDED.source_hash
       AND (i18n_keys.namespace, i18n_keys.msgctxt, i18n_keys.sensitive,
            i18n_keys.max_px, i18n_keys.context, i18n_keys.retired_at)
           IS DISTINCT FROM
           (EXCLUDED.namespace, EXCLUDED.msgctxt, EXCLUDED.sensitive,
            EXCLUDED.max_px, EXCLUDED.context, CAST(NULL AS TIMESTAMPTZ));

    -- Key post-check (enforcing): every expected key live with the expected source
    -- text, hash, sensitivity and context, and no max_px.
    SELECT COUNT(*) INTO v_ok
      FROM i18n_keys k
      JOIN (VALUES
        (E'c4d5526dfaef7312', E'0d891dd93ff117f9cb982affdfdf2659f6fec53e', E'Couldn\'t leave the tournament - it may have locked or started', FALSE, E'ApiClient · TournamentUnsignup'),
        (E'8b0f70cb42c1cda3', E'e3303e8feef02cd0711fbca17db104b380e423c2', E'Tournament info is refreshing - try again in a moment', FALSE, E'NativeUI · TFencedTournament'),
        (E'f76648a14f012b93', E'dde2afe15d21de6b5ce4e0a459c84f911313a441', E'Tournaments are 8-16 player double-elimination brackets of best-of-3 series, run end to end by the mod and the bot. There are two kinds: <color=#7FD4FF>Sync</color> (the whole bracket plays out in one sitting) and <color=#7FD4FF>Async</color> (each match has a week to happen). Both are ranked - every game moves your normal 1v1 rating.\n\n<color=#FFD94D><b>THE TWO KINDS</b></color>\n\n<color=#7FD4FF>Sync</color> - weekly. The default start is Saturday at noon Pacific time, but the field votes on the real time: signing up includes marking which start times you can make, from 8 slots at 6-hour steps around the default. The tournament locks 48 hours before the DEFAULT start - the voted time can sit up to a day to either side of it.\n\n<color=#7FD4FF>Async</color> - a new one opens 2 days after the previous one finishes. Signups run for 7 days, then it locks and starts immediately. Every match has a 7-day deadline (check-ins can add a day), so a full bracket takes roughly 6-9 weeks depending on how fast people play.\n\n<color=#FFD94D><b>SIGNING UP</b></color>\n\n- Sign up on the F5 Tournaments tab. A linked Discord account is required - the bot runs everything by DM (see <color=#7FD4FF>The bot & check-ins</color>).\n\n- Sync signups must mark at least one start time. Signing up again replaces your time votes.\n\n- You can un-sign freely during voting. After lock the in-game button closes - withdrawing then happens by answering <b>No</b> on the bot\'s availability-check DM. <color=#FF6666>Once the tournament is running you can\'t un-sign at all</color> - from there, not showing up is a forfeit and counts on your no-show %.\n\n- The field caps at 16. Signups past the cap become <color=#7FD4FF>speculative</color>: they don\'t play, but they are the backfill pool - if a confirmed player leaves before the start, the most reliable speculative inherits their seat. Ordering into the 16 (and out of the pool) goes by no-show % first, then signup time.\n\n- Your <color=#7FD4FF>no-show %</color> is a rolling 90-day measure of tournaments you signed up for and then missed. Old misses fade out over the 90 days.\n\n<color=#FFD94D><b>HOW THE LOCK WORKS</b></color>\n\n- Sync locks 48 hours before the default start. It needs at least 8 confirmed players AND one time slot at least 8 signups (speculatives included) can make; otherwise the whole tournament pushes back one week and your votes carry forward.\n\n- The winning slot becomes the start time. <color=#FF6666>If you didn\'t mark the winning slot, your signup is removed</color> - no penalty, and the bot DMs you why. Speculatives promote into the freed seats.\n\n- Sync can also start early: once at least 8 players are in, every confirmed player pressing <color=#7FD4FF>Force Start</color> on the tab within 10 minutes of each other starts the tournament 10 minutes later.\n\n- Async has no time vote - after the 7-day signup window it locks on player count alone and starts right away.\n\n- Locking snapshots the prize pool at the confirmed player count and clears any ranked blocks between participants - signing up opts you in to playing whoever else signed up.\n\n<color=#FFD94D><b>SEEDING AND THE BRACKET</b></color>\n\n- Your seed is your 1v1 rating snapshotted at lock; the highest rating is seed 1. Pairing is standard bracket placement, with seeds 1 and 2 starting in opposite halves. Seed numbers stay hidden until the tournament starts, so nobody can work out their round-1 opponent in advance.\n\n- With 9 to 15 players the bracket is built for 16 and the top seeds get round-1 byes to fill the gap.\n\n- Double elimination in plain terms: lose a winners-bracket match and you drop into the losers bracket; lose there and you\'re out. The losers-bracket champion meets the winners-bracket champion in the grand final - and if the losers-bracket champion wins it, one extra deciding match is played, because the winners-bracket champion hadn\'t lost a series yet.\n\n- Every match is a best-of-3, played as a normal ranked series.\n\n<color=#FFD94D><b>SYNC PLAY DAY</b></color>\n\nThe whole contract is: <color=#7FE87F>have ROUNDS open at the start time - sitting at the main menu is fine.</color> The mod does everything else.\n\n- While ROUNDS runs, the mod pings the server every 20 seconds; you count as present while your last ping is under 2 minutes old. The F5 menu never needs to be open.\n\n- From 15 minutes out you get a reminder DM and an in-game countdown banner; every match-ready moment gets its own DM too (see <color=#7FD4FF>The bot & check-ins</color>).\n\n- When your match is ready and both players are present, the mod connects you automatically - green banner, match-found sound, taskbar flash. If you\'re mid-casual-game you get a red banner instead, and the mod pulls you out of that room with no disconnect penalty.\n\n- Matches give a 10-minute show-up grace. If your opponent never joins your room, the mod warns you at 90 seconds and returns you to the menu after 6 minutes - you stay ready, and the server forfeits the match to you if they don\'t show.\n\n- Between your matches there\'s a 7-minute breather with the next room already prepared. Both players pressing <color=#7FD4FF>Play Now</color> on the Tournaments tab starts it early.\n\n- The server picks each match\'s connection region for both players, so you always land in the same room whatever your menu region is set to.\n\n<color=#FFD94D><b>PLAYING AN ASYNC MATCH</b></color>\n\n- When your match goes live the bot DMs both of you with the deadline. There\'s no start instant, no auto-connect, and no room code from the bracket.\n\n- Agree a time with your opponent (use /dm-opponent in Discord, or just message them), then play a normal private lobby: main menu, Online, Host Room, and one of you sends the other the 6-character code.\n\n- The result records automatically as long as you both have the mod running with <color=#7FD4FF>Ranked enabled</color> - the server binds the series to your bracket pairing from any room. The mod turns Ranked on for you when a tournament match is live (see <color=#7FD4FF>Deadlines & forfeits</color>).\n\n- In the final 24 hours before the deadline the bot sends a check-in DM; answering that you plan to play today extends the deadline 24 hours, once per opponent.', TRUE, E'InfoLibrary · (file scope)'),
        (E'fc5b6244bdd13c72', E'3960e8a1336364cf16f4a14fde90e1b691431c08', E'What happens when someone doesn\'t show up, quits, or leaves a tournament - and exactly how prizes are computed. Short version: <color=#7FE87F>a finished series always stands</color>, absence is what gets punished, and forfeit wins never pay podium prizes.\n\n<color=#FFD94D><b>DEADLINES</b></color>\n\n- Sync: matches give a 10-minute show-up grace from the moment they go ready. A match that follows a PLAYED match sits in a 7-minute breather first (a bye-fed match can go ready immediately), and a match still in its breather can never forfeit anyone. While both players are present the server waits - a sync match can run past its deadline.\n\n- Async: every match, the grand-final reset included, has a 7-day deadline from the moment it goes live. The deadline check-in DM can extend it 24 hours, once per opponent. Presence doesn\'t spare an async match - only playing does.\n\n<color=#FFD94D><b>WHEN THE DEADLINE HITS</b></color>\n\nThe server resolves an overdue match in this exact order - the first rule that applies decides it:\n\n- 1. <color=#7FE87F>A finished series always stands</color> - nothing overrides a played result.\n- 2. If exactly one seat is banned, the other player advances immediately.\n- 3. A game reported in the last 45 minutes means a live series - the match is left alone.\n- 4. Sync only: both players present - the server keeps waiting.\n- 5. Exactly one player present - <color=#FF6666>the absent player forfeits</color> and the present one advances.\n- 6. Otherwise: if the series was started and the score is uneven, the score leader advances. Failing that, if exactly one of you answered the async deadline check-in - any answer - that player advances over the silent one. Failing that too, the lower no-show % advances, and a dead tie falls to a fixed arbitrary tiebreak.\n\nOnly absent seats get the no-show mark (a banned seat forfeits regardless of presence, and a silent seat can lose the async tiebreaks while present). Your <color=#7FD4FF>no-show %</color> is a rolling 90-day rate that decides your priority into future tournaments, backfill order, and these tiebreaks.\n\n<color=#FFD94D><b>WHAT A FORFEIT DOES - AND DOESN\'T</b></color>\n\n- The bracket advances exactly as if the match completed - the winner moves on, the loser drops or is out.\n\n- <color=#FF6666>A forfeit mints nothing.</color> Podium placements only exist for played, completed series - a forfeit-decided podium spot pays no prize.\n\n- No rating moves. Rating only changes when a series completes; a forfeited match\'s series is simply never completed or scored.\n\n- Betting closes: a forfeited match\'s series can\'t be bet on.\n\n<color=#FFD94D><b>LEAVING, AND WHO REPLACES YOU</b></color>\n\n- During voting: un-sign freely.\n\n- After lock, before the start: answering <b>No</b> on the bot\'s availability-check DM withdraws you and runs the backfill flow - the most reliable speculative signup takes your exact bracket slot (with their own rating); no speculative available means your would-be opponents get byes. Leaving this way carries no penalty. If you have no answerable DM left, you\'re expected to show - a no-show forfeits and counts on your no-show %.\n\n- Once running: you can\'t un-sign. Not showing up forfeits your matches and counts on your no-show %.\n\n- Quitting mid-game follows normal 1v1 disconnect rules: the DC lands on your leave %, and unless your opponent was at match point (then they take the game, which can finish the series) the series stays open at its score. The deadline sweep resolves an abandoned series: after the 45-minute grace a still-present opponent wins; if both walked away, the score leader advances.\n\n<color=#FFD94D><b>THE RANKED OVERRIDE</b></color>\n\n- When one of your tournament matches is live and your Ranked toggle is off, the mod flips it ON and tells you. Async matches happen in private lobbies, which only record as ranked when both players have Ranked enabled - the override guarantees your result records.\n\n- <color=#FF6666>It stays ON after the match.</color> There is no auto-revert: turn it off in Settings if you don\'t want later games rated. Turning it off between tournament matches gets it flipped back on when your next match goes live.\n\n<color=#FFD94D><b>PRIZES, TROPHIES AND BETTING</b></color>\n\n- The pool scales with the player count snapshotted at lock. At 8 players: 1000 / 600 / 120 Gold and 5000 / 3000 / 150 XP for 1st / 2nd / 3rd. It grows linearly with the field, doubling at 16 players: 2000 / 1200 / 240 Gold and 10000 / 6000 / 300 XP.\n\n- <color=#7FE87F>Prizes pay when the whole bracket completes</color>, not when your final match ends. A forfeit-decided rank is skipped rather than passed down.\n\n- <color=#8A8A93>Prize XP behaves like any other XP: it converts to Gold at the usual 100 XP = 1 Gold, and a level boundary it crosses pays the normal level reward.</color>\n\n- Trophies are Discord roles: SCR Tournament Winner, Runner Up, and 3rd Place; a second same placement upgrades the role to its (x2) version. Every confirmed participant gets the Participant role. Roles only go out for brackets of 16 or more players. Winning or taking 2nd in a tournament also unlocks a paying achievement (separate ones for sync and async), and playing a bracket through without ever forfeiting unlocks Iron Bracket.\n\n- Every tournament game is a normal ranked best-of-3: it moves your regular 1v1 rating whether or not you reach the podium.\n\n- Tournament matches are bettable on the same terms as any live ranked series: betting locks at 2 live points in game 1 or once any game is decided. An async pairing that waits days stays bettable the whole wait at 0-0.', TRUE, E'InfoLibrary · (file scope)')
      ) AS x(key_id, source_hash, msgctxt, sensitive, context) ON x.key_id = k.key_id
     WHERE k.namespace = 'client' AND k.retired_at IS NULL
       AND k.source_hash = x.source_hash AND k.msgctxt = x.msgctxt
       AND k.sensitive = x.sensitive AND k.max_px IS NULL
       AND k.context IS NOT DISTINCT FROM x.context;
    IF v_ok <> v_expected THEN
        RAISE EXCEPTION 'migration 393: % of % tournament fence client keys are live with the expected source, hash, sensitivity and context; nothing committed', v_ok, v_expected;
    END IF;

    -- 3. The seeds: a PENDING claude-mt draft per toast pair, except where IDEMPOTENT
    --    in the header says a pair gets none.
    CREATE TEMP TABLE _seed393 (
      key_id      VARCHAR(16) NOT NULL,
      lang        VARCHAR(8)  NOT NULL,
      source_hash VARCHAR(40) NOT NULL,
      target      TEXT        NOT NULL
    ) ON COMMIT DROP;

    INSERT INTO _seed393 (key_id, lang, source_hash, target) VALUES
      -- "Couldn't leave the tournament - it may have locked or started"
         (E'c4d5526dfaef7312', 'es', E'0d891dd93ff117f9cb982affdfdf2659f6fec53e', E'No se pudo abandonar el torneo - puede que las inscripciones ya estén cerradas o que haya empezado')
      ,  (E'c4d5526dfaef7312', 'ru', E'0d891dd93ff117f9cb982affdfdf2659f6fec53e', E'Не удалось покинуть турнир - возможно, запись уже закрыта или он начался')
      ,  (E'c4d5526dfaef7312', 'uk', E'0d891dd93ff117f9cb982affdfdf2659f6fec53e', E'Не вдалося покинути турнір - можливо, запис уже закрито або він розпочався')
      ,  (E'c4d5526dfaef7312', 'sv', E'0d891dd93ff117f9cb982affdfdf2659f6fec53e', E'Det gick inte att lämna turneringen - anmälan kan ha låsts eller så har den startat')
      -- "Tournament info is refreshing - try again in a moment"
      ,  (E'8b0f70cb42c1cda3', 'es', E'e3303e8feef02cd0711fbca17db104b380e423c2', E'La información del torneo se está actualizando - vuelve a intentarlo en un momento')
      ,  (E'8b0f70cb42c1cda3', 'ru', E'e3303e8feef02cd0711fbca17db104b380e423c2', E'Информация о турнире обновляется - попробуйте ещё раз через пару секунд')
      ,  (E'8b0f70cb42c1cda3', 'uk', E'e3303e8feef02cd0711fbca17db104b380e423c2', E'Інформація про турнір оновлюється - спробуйте ще раз за кілька секунд')
      ,  (E'8b0f70cb42c1cda3', 'sv', E'e3303e8feef02cd0711fbca17db104b380e423c2', E'Turneringsinformationen uppdateras - försök igen om en stund')
    ;

    INSERT INTO i18n_proposals
      (key_id, language_code, source_hash, proposed_target, proposer_steam_id,
       license_assent, license_terms_rev, assented_at, status, created_at)
    SELECT v.key_id, v.lang, v.source_hash, v.target, 'claude-mt',
           TRUE, 'machine-v1', clock_timestamp(), 'pending', clock_timestamp()
      FROM _seed393 v
      JOIN i18n_keys k ON k.key_id = v.key_id AND k.retired_at IS NULL
                      AND k.source_hash = v.source_hash
     WHERE NOT EXISTS (
       SELECT 1 FROM i18n_proposals p
        WHERE p.key_id = v.key_id AND p.language_code = v.lang
          AND p.status = 'pending')
       AND NOT EXISTS (
       SELECT 1 FROM i18n_proposals p2
        WHERE p2.key_id = v.key_id AND p2.language_code = v.lang
          AND p2.proposer_steam_id = 'claude-mt'
          AND p2.source_hash = v.source_hash)
       -- A CURRENT approved translation (approved against this source_hash) needs no
       -- machine draft: approving a draft queued over it would overwrite it.
       AND NOT EXISTS (
       SELECT 1 FROM i18n_entries e
        WHERE e.key_id = v.key_id AND e.language_code = v.lang
          AND e.state = 'approved'
          AND e.approved_source_hash = v.source_hash);

    -- 4. Seed coverage post-check (enforcing): a pair is covered only by a PENDING
    --    proposal at this source_hash or an entry APPROVED against it. A rejected or
    --    superseded draft, or a proposal or approval of another text, leaves it uncovered.
    SELECT COUNT(*) INTO uncovered
      FROM _seed393 v
     WHERE NOT EXISTS (
             SELECT 1 FROM i18n_proposals p
              WHERE p.key_id = v.key_id AND p.language_code = v.lang
                AND p.source_hash = v.source_hash
                AND p.status = 'pending')
       AND NOT EXISTS (
             SELECT 1 FROM i18n_entries e
              WHERE e.key_id = v.key_id AND e.language_code = v.lang
                AND e.state = 'approved'
                AND e.approved_source_hash = v.source_hash);
    IF uncovered <> 0 THEN
        SELECT string_agg(x.key_id || '/' || x.lang, ', ')
          INTO sample
          FROM (SELECT v.key_id, v.lang FROM _seed393 v
                 WHERE NOT EXISTS (
                         SELECT 1 FROM i18n_proposals p
                          WHERE p.key_id = v.key_id AND p.language_code = v.lang
                            AND p.source_hash = v.source_hash
                            AND p.status = 'pending')
                   AND NOT EXISTS (
                         SELECT 1 FROM i18n_entries e
                          WHERE e.key_id = v.key_id AND e.language_code = v.lang
                            AND e.state = 'approved'
                            AND e.approved_source_hash = v.source_hash)
                 LIMIT 5) x;
        RAISE EXCEPTION 'migration 393: % of 8 seed pairs have neither a pending proposal nor an approved translation of the current source text (e.g. %); nothing committed', uncovered, sample;
    END IF;
    RAISE NOTICE 'migration 393: 4 keys live, all 8 toast seed pairs covered at the current source text (2 keys x es/ru/uk/sv)';
END $m393$;

COMMIT;
