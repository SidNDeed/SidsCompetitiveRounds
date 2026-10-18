-- 386_ffa_leave_grace_texts.sql
-- Restate the FFA early-leave grace after the server moves its boundary from
-- two field half points to two full points and stops requiring an empty tally.
-- The four client rows are additive and inert until a client ships the same
-- English byte for byte; the sync-keys retire pass owns the superseded keys.
-- key_id = sha1("client\0" + English)[:16], source_hash = sha1(English),
-- sensitive per tools/i18n_sync_keys.py SENSITIVE_MARKERS.
-- Idempotent; explicit transaction (learning #340).
-- DEPLOY ORDER: THIS FILE FIRST, then the API, as two SHAs (learning #477).

BEGIN;

COMMENT ON COLUMN ffa_match_players.game_points_at_leave IS
    'Total half points scored by the whole field at the moment this seat left, '
    'reported by a surviving client. Only ever set for left_early rows. '
    'NULL = not reported (pre-v1.39 client, or a carried roster ghost). '
    'A field total below two full points, measured in half points against the '
    'helper-derived threshold, leaves the seat unrated for the game.';

INSERT INTO i18n_keys (key_id, namespace, msgctxt, source_hash, sensitive, max_px, context, updated_at)
SELECT v.key_id, v.namespace, v.msgctxt, v.source_hash, v.sensitive, NULL, NULL, NOW()
  FROM (VALUES
('79023ff50ab9d08e', 'client', $k386$<color=#FFD94D><b>HOW A PICK ACTUALLY LANDS</b></color>

- Confirming a card applies nothing - not even on your own screen. Every picker publishes their choice, the room master collects them and publishes one accepted list, and every client applies exactly that list in the same order. That is why all 3-10 screens always agree on who got what.
- The numbers: 45 seconds base, plus 20 more each time a pick lands near the end, capped at 90.
- The on-screen 0 is exactly the auto-confirm moment - the client confirms slightly early, so a slow connection can't eat your pick.
- <color=#FF6666>Two rare cases still yield no card:</color> a pick published in the final instant can miss the cutoff (you get a toast saying so), and a crashed seat is finalized without one.

<color=#FFD94D><b>WHAT REPLACING A CARD REALLY DOES</b></color>

- ROUNDS has no way to subtract one card's stats. When your oldest card rolls off, the mod fully resets your character and silently replays your surviving cards in their original order. A toast on every screen names what you lost.

<color=#FFD94D><b>MAP SCALING</b></color>

- With 5 or more players the map grows 6 percent per player above 4, capped at x1.40: five players play at x1.06, ten at x1.36. 3-4 player games are unscaled.
- The camera, the kill boundary and spawn positions all scale with it.
- Vanilla maps ship only four spawn points, so on scaled maps the mod scans the freshly loaded map for solid static ground and gives players 5-10 their own spawns instead of shared coordinates.

<color=#FFD94D><b>TEN PLAYERS, FOUR COLORS</b></color>

- ROUNDS ships exactly four body colors, so colors repeat every 4 players. Nametags keep duplicates apart, and equipped body-color cosmetics still show.
- To help you find yourself, the screen dims around your own player for the first second after each spawn - the same second in which nobody can fire or block (<color=#7FD4FF>spawn grace</color>).

<color=#FFD94D><b>DOUBLE KO</b></color>

- If the last players alive kill each other in one exchange, nobody scores and the round just ends - announced on every screen.
- The winner is decided at the very end of the frame, so a mutual kill can't hand the round to whoever died a split second later.

<color=#FFD94D><b>LEAVERS, PRECISELY</b></color>

- A leaver's points, half points and kills freeze at the moment they leave and still count for placement in every later report of the sitting.
- If a leaver was one of the last two standing, the survivor takes the half point.
- <color=#7FE87F>Early-leave grace:</color> leave a game before the field has scored two full points, and that game is unrated for you - no rating change, no game Gold or XP. Achievements and other earning ways are unaffected. Any later leave counts in full: leaving early doesn't dodge the loss.
- Players who left in an EARLIER game ride along as absent ghosts - on the roster, excluded from rating and pay.
- A game that drops under 3 players before 2 half points were scored is cancelled; dropping under 3 after a game over ends the sitting.$k386$, '9c01f76278701de0cc2e02938f1f2a9367765962', TRUE),
('3bb08fc59139b367', 'client', $k386$Every finished game pays XP, XP converts to Gold at 100 XP = 1 Gold, and ranked play multiplies the base rewards below by your opponent's rank tier. This is the pay table - exact numbers, mode by mode. (Tournament podium prizes are separate; see <color=#7FD4FF>Deadlines & forfeits</color>.)

<color=#FFD94D><b>THE TIER MULTIPLIER</b></color>

In ranked play, base rewards are multiplied by the OPPONENT'S rank tier - <color=#7FE87F>win or lose. Playing up always pays.</color>

<color=#7FD4FF>Beginner</color> (under 1500) - x1.0
<color=#7FD4FF>Intermediate</color> (1500 or more) - x1.5
<color=#7FD4FF>Advanced</color> (1675 or more) - x2.0
<color=#7FD4FF>Master</color> (1980 or more) - x2.5
<color=#7FD4FF>Grand Master</color> (2330 or more) - x3.0

It applies to XP and to series Gold, and an opponent with no rating on record counts as 1500 (x1.5). Which rating is 'the opponent's': their 1v1 rating in 1v1, the opposing team's average 2v2 rating in 2v2, the opposing seat's average 1v1 rating in 1v2, and your opponents' average FFA rating in FFA.

<color=#FFD94D><b>1v1</b></color>

Per game, multipliers stack, then the total truncates to a whole number:

- Base <color=#7FE87F>250 XP</color> per finished game, casual included.
- Game win: x1.5. Ranked: x1.5. Opponent tier: x1.0 to x3.0 (ranked only).
- A shutout win (opponent on 0 rounds) adds +100 XP flat, after the multipliers.

Exact examples: casual loss 250, casual win 375; ranked loss vs a Beginner 375; ranked win vs a Beginner 562, vs an Intermediate 843, vs a Grand Master 1687 (+100 more if 5-0).

Series Gold, ranked BO3 only - casual play creates no series and pays none:

- Loser: 5 x opponent tier, truncated. Winner: double that.
- Winner doubles AGAIN if the beaten player currently sits in the leaderboard top 3.
- +2 flat on top for a 2-0 sweep.
- Winner/loser by opponent tier, before podium and sweep: Beginner 10/5, Intermediate 14/7, Advanced 20/10, Master 24/12, Grand Master 30/15.

<color=#FFD94D><b>2v2</b></color>

- Per game: 600 XP x the opposing team's tier, then x1.5 if your team won the game.
- Default all-1500 lobby: 900 XP for a loss, 1350 for a win.
- Series Gold: 50 (each winner) or 25 (each loser), x the opposing team's tier. Default lobby: 75/37.

<color=#FFD94D><b>1v2</b></color>

Base 500 XP per game, x1.5 on a win, then a per-seat difficulty multiplier:

- Solo seat: x1.5.
- Solo playing WITHOUT the extra-pick handicap: another x1.20.
- Duo seats facing a buffed solo (extra pick on): x1.10.
- Opponent tier, read from the opposing seat's average 1v1 rating - 1v2 has no rating of its own.
- Opponent currently in the 1v2 leaderboard top 3: x1.35, win or lose.
- The whole product is capped at x4.0; the x1.5 win bonus applies on top of the cap.

Defaults with extra pick on: the solo earns 1125 XP for a loss and 1687 for a win; each duo member 825/1237.

Series Gold: 40 (winning side) or 20 (losing side), x opponent tier only - the seat, handicap and podium factors live on XP. Default: 60/30.

<color=#FFD94D><b>FFA - THE METER</b></color>

FFA pays for FIGHTING, not for time in the lobby. The formula, in readable form:

- The work unit is <color=#7FD4FF>battles</color>: every decisive round scored by anyone in the game. <color=#FF6666>Camping adds nothing to the pool</color>, and the last-place cut it earns is the smallest share of what everyone else generated.
- A pace ceiling caps how fast battles cash in. For a lobby of P players, one battle is expected about every 3.08 + 6.54 x P seconds (P counted as at least 3 and at most 6 here), and the game pays at most TWICE that pace across the game's elapsed time on the server's clock - stalling or point-farming cannot outrun it.
- The base rate is 3.5 Gold per player-minute, +5% for every player above 4. A 10-player FFA is the best Gold rate in the game.
- Placement shapes your cut of the pool: 1st place earns 1.666x the lobby average, last place 0.334x - about a 5x spread. Players sharing a place share the same cut.
- A stronger field multiplies the pot: your opponents' average tier divided by 1.5, so a default 1500 field is exactly x1.0. Casual lobbies take the bottom factor (about x0.667) and never touch ratings.
- The pool is a Gold amount. 55% pays directly as Placement Gold (minimum 1). The other 45% pays as XP at 100 XP per point of pool (minimum 50 XP), which drips back as Gold through the normal conversion.
- Placement itself sorts by points, then all round wins earned (spent ones included), then kills where the lobby's kill tiebreak is active; remaining ties share a place.
- Ghosts and graced early leavers are unrated and receive no game Gold or XP from that game: leaving before the field scored two full points takes you out of those results. Achievements and other earning ways are unaffected.

<color=#FFD94D><b>LEVELS AND THE XP-TO-GOLD DRIP</b></color>

- XP converts at <color=#7FE87F>100 XP = 1 Gold</color>, paid every time your running total crosses a hundred mark. Every mode's XP - tournament prizes included - feeds the same total.
- Climbing into level L costs 100 x L^1.5 XP, truncated: level 2 costs 282, level 5 costs 1118, level 10 costs 3162, level 50 costs 35355, level 100 costs 100000. Max level is 100.
- Entering a multiple-of-5 level pays bonus Gold: <color=#7FE87F>100g for levels 5 through 50, 500g for 55 through 100</color> - 6000g lifetime if you reach the cap. It lands the moment any XP award dings the level - any mode, tournament prizes included; a ding during an FFA game shows up inside that game's +g number.

<color=#FFD94D><b>ACHIEVEMENT GOLD</b></color>

Every achievement pays <color=#7FE87F>100g</color> unless listed here:

- <color=#7FD4FF>1000g</color> - Sid Slayer, Stan Slayer, Grand Master (reach 2330), Touch Grass, Babel.
- <color=#7FD4FF>500g</color> - Master (reach 1980), Tag Team Sweep, Rise from the Ashes, Casual Conqueror, Twins!, Immortal, Hostile Takeover, Bodycount.
- <color=#7FD4FF>300g</color> - Stacked Deck, Flawless, Silly Drill, Into the Deep End, Century Club, Unstoppable, Party Crasher, Heartbreak, Dragoman.

The FFA shutouts nest: one 5-0 win in a 5-player lobby pays Clean House (100g) + Party Crasher (300g) + Hostile Takeover (500g) in a single game. The translator achievements (Rosetta, Dragoman, Babel) trigger at 10, 100 and 1000 approved live strings.

<color=#8A8A93>Outside matches: Discord server boosters are paid 2000g monthly, and community artists earn a 30% royalty (rounded down to whole Gold) when another player buys their item - gifts pay none.</color>$k386$, 'd13c59cc1eeb7562aebe74a3b1c62945002d84ce', TRUE),
('3988c8d80e42f69d', 'client', $k386$Free-for-all for 3-10 players. Every player is their own team.
Standard ROUNDS scoring - first to {0} points takes the game.

<color=#FFD94D><b>HOW TO PLAY</b></color>

- There is no Elo band. Joining a lobby is consent to play.

- Create a lobby, or join an open one from the browser.
  The HOST presses Start once at least 3 players are in
  (up to 10). Several lobbies can be open at once.

- If the host leaves, the longest-waiting member becomes
  the new host automatically.

- After each point, everyone except the point winner
  picks a card at the same time.

- The pick timer is shown on screen. A pick landing
  near the end grants everyone a little extra time.
  When your timer hits zero, your highlighted card is
  picked for you automatically - walking away never
  skips your pick. Only a pick that misses the window
  entirely (a freeze, a crash, or the final split
  second) yields no card, with a toast saying so.

- You hold up to {1} cards.
  Picking one more replaces your oldest card.

<color=#FFD94D><b>HOST SETTINGS</b></color>

- The host can tune the lobby before starting: score
  target (3-10), opening draws, cards offered per
  draw (1-5), max cards held (3-5 ranked, up to 6
  casual), the Same Cards rule, and ranked/casual.

- Same Cards rule: everyone's Nth card draw offers the
  SAME candidates, in the same order - if you and a rival
  were offered identical cards all game, no result can be
  blamed on draw luck. One-copy cards (like Phoenix)
  appear at most once per game for everyone.

- After a settings change the lobby cannot start for 60
  seconds (and briefly after someone new joins), so
  everyone can read what changed. Casual lobbies pay
  reduced rewards and never touch ratings.

<color=#FFD94D><b>RATING</b></color>

- FFA is ranked with its own Glicko rating.

- Placement uses points, then all round wins earned
  (spent ones included), then kills.
  Remaining ties share a place using competition
  order: 1, 2, 2, 4.

- Your rating is scored against the players placed
  nearest to you (up to 4 of them), so one game can't
  swing your rating several times harder in a 10-player
  lobby than in a 3-player one. One extra comparison
  can join those four: the biggest 250+ rating gap
  that finished upside down outside them.

- A tied placement counts as a draw. New ratings move
  fast and settle down as you play more.

<color=#FFD94D><b>REWARDS</b></color>

- Pay is metered on the FIGHTING, not on flat per-game
  numbers: decisive rounds are the work unit, and
  elapsed time caps how fast they cash in - stall
  tactics are held to a bounded edge, and longer,
  bigger games pay more.

- Bigger lobbies pay a better rate per minute, and a
  10-player FFA is the best gold rate in the game.

- Your placement shapes your share: 1st earns about
  five times last place's cut. Part pays as XP, part as
  Placement Gold, and a stronger opposing field
  multiplies the pot (the usual tier bonus).

- XP converts to Gold at 100 XP = 1 Gold, and level-ups
  pay their usual bonus Gold. A level-up landing during
  a game shows up inside that game's +g number - that is
  how a last place can occasionally out-earn the winner.

- Spectators can bet Gold on FFA lobbies from this tab.

<color=#FFD94D><b>READING THE RECENT FFAS LIST</b></color>

<color=#7FD4FF>Dots + N(P)</color> - Full points won.
<color=#7FD4FF>Half dots + N(H)</color> - Round wins that
  did not become one of that player's full points.
<color=#7FD4FF>Nk</color> - Kills.
<color=#7FD4FF>+xp +g</color> - That game's XP and Gold
  (including any level-up bonus).
<color=#7FD4FF>Green/red number</color> - FFA rating change.
<color=#7FD4FF>Cards</color> - The hand held at game end.
  <color=#FF6666>+N replaced</color> counts picks that were
  pushed out by the card cap - hover the line to see
  every pick in order.

<color=#FFD94D><b>LEADERBOARD COLUMNS</b></color>

<color=#7FD4FF>Rank</color> - Position in the currently selected sort.
<color=#7FD4FF>Player</color> - The player's display name.
<color=#7FD4FF>Rating</color> - The player's separate FFA Glicko rating.
<color=#7FD4FF>Games</color> - Recorded FFA games played.
<color=#7FD4FF>Wins</color> - Games finished in 1st place.
<color=#7FD4FF>Top3</color> - Games finished in 1st, 2nd, or 3rd.
<color=#7FD4FF>AvgPl</color> - Average finishing place. Lower is
  better - 1.0 means winning every game.
<color=#7FD4FF>WR</color> - Share of games won outright.

<color=#FFD94D><b>GOTCHAS</b></color>

- Leaving mid-game is recorded. A leaver keeps their
  tallies and is placed and rated for the game they
  left - unless they left before the field had scored
  two full points, in which case that game does not rate
  them or pay them game Gold or XP. Achievements and other
  earning ways are unaffected.$k386$, 'd610fb87bd635bfe908b9169f6bf3cc9b3be131c', TRUE),
('439cd5d90ee1b6d3', 'client', $k386$The rule book for what gets recorded and what gets thrown away: games, series, disconnects, bets. If a result looks missing, the reason is almost always on this page.

<color=#FFD94D><b>NEVER RECORDED AT ALL</b></color>

- Data consent off: the mod runs fully offline. Nothing is ever sent except a version check.
- Offline, practice and sandbox games: never reported by the client, and refused by the server as a backstop.
- Spectator seats submit no match record and no persistent stats. (The mod keeps local diagnostics in its own log — frames, connection facts — and sends nothing automatically; they leave your PC only inside a bug report you choose to attach logs to.)

<color=#FFD94D><b>RANKED OR CASUAL</b></color>

- Either player's Ranked toggle off in a room-code game - it plays as CASUAL. Still fully recorded with stats and XP; it never touches rating (see <color=#7FD4FF>How games are tracked</color>).
- Opponent has never run the mod - always casual, never upgraded. (A live unfinished series from an earlier sitting is the one thing that keeps ranked status across a gap.)
- Toggling Ranked off MID-SERIES does not void the series. The running best-of-3 is your consent record; its games stay ranked.
- A game reported as casual is UPGRADED to ranked when the server can see both players are modded, both have Ranked on, and the sitting is live.
- A ranked-banned participant forces a 1v1 casual at report time - even in a queue room, even mid-series. (The other modes shut banned players out at the door instead.)
- Mod-issued rooms are consented by definition; queueing is consent. The ranked queue, 2v2 and tournaments rate; ranked FFA lobbies rate while casual ones don't; 1v2 records without rating.

<color=#FFD94D><b>DISCONNECTS - 1V1</b></color>

- You leave a game to join a queued ranked match - the game you left is canceled: nothing recorded, no leave logged.
- Opponent DCs at 4-4 - you get the win, recorded 5-4.
- Opponent DCs while you hold 4 rounds - you get the win at the standing score.
- Any other DC - <color=#FF6666>the game is canceled and no result is recorded</color>, even when the leaver was ahead. Nobody gets a free win and nobody eats an unfair loss (the leave itself can still be logged - see below).
- Ranked leave %: a DC is logged against the leaver when the CURRENT game had meaningful play (2 or more points scored, or a completed round) and neither side was at 4 rounds. One DC per player per series. The stat is your DCs divided by your ranked series played plus your DCs.
- Casual rage quits: ANY mid-game leave in a casual 1v1 is logged, even at 4-0. It feeds the Rage Quit % stat (how often opponents walk out on you) - never rating. (A survivor already at 4 rounds still takes the casual win and its XP.)

<color=#FFD94D><b>DISCONNECTS - 2V2 AND FFA</b></color>

- 2v2: a team DCs while the other team leads the series and the abandoned game had 2 or more points - the leading team takes the whole series, with full ratings and rewards.
- Any other 2v2 DC - the series PAUSES for manual admin resolution instead of auto-deciding. If the same four re-queue within about 30 minutes, the matcher puts them back on the same series with the score kept.
- FFA keeps playing when someone leaves, as long as 2 or more remain (a game that drops under 3 players before the field scored 2 half points is cancelled instead). The leaver's tallies are frozen, and they are still placed and rated for the game they left during - <color=#FF6666>leaving at 0 points does not dodge the loss</color>.
- FFA early-leave grace: a leaver who left before the field had scored two full points is unrated for that game and receives no game Gold or XP from it. Achievements and other earning ways are unaffected.
- An FFA player who left in an EARLIER game rides later reports as absent, excluded from those games' ratings and rewards.

<color=#FFD94D><b>SERIES: RESUME, STALL, EXPIRE</b></color>

- <color=#7FE87F>An undecided best-of-3 resumes with no time limit.</color> Meet the same opponent tomorrow or next week and game 1 still stands. An expiry existed once - leavers waited it out to bank rating, so it was removed.
- Rating moves ONLY when a series completes (first to 2 game wins). Games of a series that never completes keep their match rows, XP and gold; the rating change just never happens.
- A series with no game recorded 30 minutes after it was created is abandoned and its bets are refunded.
- A mid-series stall of an hour refunds the bets, but the series itself stays active and resumable.
- Tournament series are exempt from this pruning - the bracket owns their lifecycle. A tournament match decided by forfeit can't be bet on.

<color=#FFD94D><b>THROWN OUT AFTER THE FACT</b></color>

- The one AUTOMATIC invalidation in the whole mod: a repeated pattern of implausibly short matches between the same two players inside a short window. The current match AND the earlier short ones are invalidated together, their gold and XP reversed, their series voided.
- Admin reversal: an admin can void a series - rating changes subtracted, gold clawed back, every match in it invalidated, unsettled bets refunded. Invalidated matches disappear from every board and stat.
- Quarantine (2v2 and FFA): a report that arrives for a lobby that's no longer active isn't deleted - it's held for admin review, and an admin can still accept it into the record or discard it.

<color=#FFD94D><b>IF THE REPORT CAN'T SEND</b></color>

- A failed report goes to a persistent outbox: retried in the background and saved to disk, so it's re-sent on your next launch even if you quit right after the game. You'll see 'Couldn't record the match - retrying in the background', then 'Match recorded' when it lands.
- 1v1 reporter crashes before the report exists - the surviving opponent's disconnect path usually records the result instead.
- FFA elects its reporter among the players still present, so a crashed reporter is never elected. A winner who quits before the report is still recorded from their frozen tallies.
- A 2v2 game that ends without its series id retries the lookup and defers the send; if that also fails, the game is not recorded.$k386$, 'fe8ddfc37b2ffc17fd1d4916b8207a345b34eb36', TRUE)
  ) AS v(key_id, namespace, msgctxt, source_hash, sensitive)
ON CONFLICT (key_id) DO UPDATE SET retired_at = NULL, updated_at = NOW()
  WHERE i18n_keys.source_hash = EXCLUDED.source_hash;

-- Enforcing post-check: all four new client keys are live and exact.
DO $$
DECLARE
    v_expected INT := 4;
    v_ok INT;
BEGIN
    SELECT COUNT(*) INTO v_ok
      FROM i18n_keys k
      JOIN (VALUES
        ('79023ff50ab9d08e', '9c01f76278701de0cc2e02938f1f2a9367765962'),
        ('3bb08fc59139b367', 'd13c59cc1eeb7562aebe74a3b1c62945002d84ce'),
        ('3988c8d80e42f69d', 'd610fb87bd635bfe908b9169f6bf3cc9b3be131c'),
        ('439cd5d90ee1b6d3', 'fe8ddfc37b2ffc17fd1d4916b8207a345b34eb36')
      ) AS e(key_id, source_hash) ON e.key_id = k.key_id
     WHERE k.namespace = 'client'
       AND k.retired_at IS NULL
       AND k.source_hash = e.source_hash
       AND k.sensitive IS TRUE
       AND k.max_px IS NULL
       AND k.context IS NULL;
    IF v_ok <> v_expected THEN
        RAISE EXCEPTION
            'post-check FAILED: % of % expected FFA grace client keys are live and exact',
            v_ok, v_expected;
    END IF;
    RAISE NOTICE 'post-check OK: % FFA grace client keys live and exact', v_ok;
END $$;

COMMIT;

