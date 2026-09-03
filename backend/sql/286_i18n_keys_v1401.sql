-- 286: i18n client keys for v1.40.1 (20 NEW keys): the queue-poll
-- session notices (item 3) and Release A's diagnostics/Info/music-preparation
-- strings that were never deployed (track and album names render as authored raw text and
-- are deliberately NOT keys). This is the additive half of what
-- POST /admin/i18n/sync-keys does, written
-- through the migration channel because this seat's tooling cannot sign the
-- admin HMAC (learning #443). Verified against the live table before writing:
-- the extractor manifest (2434 client keys) retires NOTHING here
-- (additive-only, per 248/266/282 precedent; the 13 live non-retired keys
-- not in the manifest — the pre-1.40.1 "at the main menu" strings among them —
-- are left for the real sync tool's retire pass) and changes no English (key_id derives
-- from the source string, so a shared key_id cannot carry a moved source_hash).
-- key_id = sha1("client\0" + English)[:16], source_hash = sha1(English),
-- sensitive per tools/i18n_sync_keys.py's SENSITIVE_MARKERS (imported, not
-- copied). Idempotent AND contract-convergent (r10 LOW 14): the conflict arm
-- is the sync endpoint's own full update (msgctxt / source_hash / sensitive /
-- un-retire, max_px/context), and the post-check RAISES if any expected key
-- is missing, retired, or carries a different source_hash / a stray
-- max_px or context — a rerun can never commit a drifted portal source.
-- Explicit transaction (#340). The game namespace is unchanged this release.

BEGIN;

INSERT INTO i18n_keys (key_id, namespace, msgctxt, source_hash, sensitive, max_px, context, updated_at)
SELECT v.key_id, v.namespace, v.msgctxt, v.source_hash, v.sensitive, NULL, NULL, NOW()
  FROM (VALUES
('026895816ca81541', 'client', $k286$Prepare music$k286$, '63875116f2ee4417e5c12602487c90ca1b164316', FALSE),
('069c8407ea855a90', 'client', $k286$Music download failed ({0}) — retry at the main menu$k286$, '9a1308c44dd5750fa100dea7417797cb51cfbc39', FALSE),
('45519a9c66bf124f', 'client', $k286$Music download failed ({0}) — retry in a moment$k286$, '4a5b515bd8c2b611e3faaad3e935ef5dce18e772', FALSE),
('4eaef20c9ab4733a', 'client', $k286$Match dissolved — searching again...$k286$, '2f68bce432d93decf76a67e3a6754234cb64338a', FALSE),
('5cac3a042aae22dc', 'client', $k286$Previous track is not prepared — open the Music tab at the main menu$k286$, '3bd719d42af3ba081416d3db52d6239b3f40d9b0', FALSE),
('6622cee2e563697d', 'client', $k286$The rule book for what gets recorded and what gets thrown away: games, series, disconnects, bets. If a result looks missing, the reason is almost always on this page.

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
- FFA early-leave grace: a leaver who left before the field had scored 2 half points, with a zero tally of their own, is unrated for that game - nothing was decided yet.
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
- A 2v2 game that ends without its series id retries the lookup and defers the send; if that also fails, the game is not recorded.$k286$, 'af4a8124e218a23a2a121f02808d4f208422fbca', TRUE),
('7892abd1235fd20e', 'client', $k286$recent: worst frame {0} ms  resends {1}  discards {2}$k286$, '740920adaadc3217938c2e81699d3c4c0e24b1da', FALSE),
('7d16ba4f6795d66f', 'client', $k286$Preparing music ({0} of {1} ready)$k286$, '7ff90e9f9fe56917617d1a367ab8da0e47747a4d', FALSE),
('8055b783c194bf26', 'client', $k286$Previews load at the main menu$k286$, '68ff624947dbd4c2bc6b458b91702676564de96d', FALSE),
('8509b908ebcf9771', 'client', $k286$opp n/a$k286$, 'a964374df27d3749238d57fd9b59327ce6ca8e34', FALSE),
('8caa809b3c7db6a3', 'client', $k286$Music download failed ({0}) — click to retry$k286$, '4c293bc3b6fbdc8cbfc812bd518f315ebc498804', FALSE),
('946752e2bbe0465c', 'client', $k286$Prepare music at the main menu ({0} of {1} ready)$k286$, 'a5f54ab3eaf64c8e49794cb1c41a199572abc375', FALSE),
('96c5ee2343e8fc4e', 'client', $k286$replica age est. n/a$k286$, 'b44615b80638caec6d833652c893406c8cbe5c0f', FALSE),
('a7d29267d8478a44', 'client', $k286${0}ms opp (peer-reported)$k286$, '90cee0472af31ee422a8e8c8e0b8659d1a4d26d5', FALSE),
('b55dc4db63a0f2c7', 'client', $k286$Prepare music ({0} of {1} ready)$k286$, 'f8cb6f0365711bf41026d9cbb4391f86d9df0eca', FALSE),
('b6b5460f14b428cd', 'client', $k286$replica age est. {0} ms one-way (peer-reported input)$k286$, '8629cbea57d01e40915bde78c4729afbd6e559fe', FALSE),
('c8d858341a3c9115', 'client', $k286$Downloading music ({0} of {1} ready)$k286$, 'd6240d7eb78128764d3d2695566420d9f218a523', FALSE),
('d394aadc9cd5c7d0', 'client', $k286$Custom music is not prepared — open F5 > Music at the main menu$k286$, '3620d45ca4e7274bfb9a0adf93dce1e944e9fff4', FALSE),
('dc79fdee9d137363', 'client', $k286$Steam session not accepted — queue polling stopped; the server will clear your seat shortly. Try again in a moment.$k286$, '7056fc9bb25b0ccd48b0b3fc496d5ac15cbf52d8', FALSE),
('e9834861b94e35e3', 'client', $k286$replica age est. {0} ms (peer-reported)$k286$, '477da4a1c3d47897491ace8151802482af4d7b30', FALSE)
  ) AS v(key_id, namespace, msgctxt, source_hash, sensitive)
ON CONFLICT (key_id) DO UPDATE
   SET namespace = EXCLUDED.namespace, msgctxt = EXCLUDED.msgctxt,
       source_hash = EXCLUDED.source_hash, sensitive = EXCLUDED.sensitive,
       max_px = EXCLUDED.max_px, context = EXCLUDED.context,
       retired_at = NULL, updated_at = NOW();

-- Post-check (enforcing): every expected key live with the expected source_hash.
DO $$
DECLARE
    v_expected INT := 20;
    v_ok INT;
BEGIN
    SELECT COUNT(*) INTO v_ok
      FROM i18n_keys k
      JOIN (VALUES

        ('026895816ca81541', '63875116f2ee4417e5c12602487c90ca1b164316'),
        ('069c8407ea855a90', '9a1308c44dd5750fa100dea7417797cb51cfbc39'),
        ('45519a9c66bf124f', '4a5b515bd8c2b611e3faaad3e935ef5dce18e772'),
        ('4eaef20c9ab4733a', '2f68bce432d93decf76a67e3a6754234cb64338a'),
        ('5cac3a042aae22dc', '3bd719d42af3ba081416d3db52d6239b3f40d9b0'),
        ('6622cee2e563697d', 'af4a8124e218a23a2a121f02808d4f208422fbca'),
        ('7892abd1235fd20e', '740920adaadc3217938c2e81699d3c4c0e24b1da'),
        ('7d16ba4f6795d66f', '7ff90e9f9fe56917617d1a367ab8da0e47747a4d'),
        ('8055b783c194bf26', '68ff624947dbd4c2bc6b458b91702676564de96d'),
        ('8509b908ebcf9771', 'a964374df27d3749238d57fd9b59327ce6ca8e34'),
        ('8caa809b3c7db6a3', '4c293bc3b6fbdc8cbfc812bd518f315ebc498804'),
        ('946752e2bbe0465c', 'a5f54ab3eaf64c8e49794cb1c41a199572abc375'),
        ('96c5ee2343e8fc4e', 'b44615b80638caec6d833652c893406c8cbe5c0f'),
        ('a7d29267d8478a44', '90cee0472af31ee422a8e8c8e0b8659d1a4d26d5'),
        ('b55dc4db63a0f2c7', 'f8cb6f0365711bf41026d9cbb4391f86d9df0eca'),
        ('b6b5460f14b428cd', '8629cbea57d01e40915bde78c4729afbd6e559fe'),
        ('c8d858341a3c9115', 'd6240d7eb78128764d3d2695566420d9f218a523'),
        ('d394aadc9cd5c7d0', '3620d45ca4e7274bfb9a0adf93dce1e944e9fff4'),
        ('dc79fdee9d137363', '7056fc9bb25b0ccd48b0b3fc496d5ac15cbf52d8'),
        ('e9834861b94e35e3', '477da4a1c3d47897491ace8151802482af4d7b30')
      ) AS e(key_id, source_hash) ON e.key_id = k.key_id
     WHERE k.namespace = 'client' AND k.retired_at IS NULL
       AND k.source_hash = e.source_hash
       AND k.max_px IS NULL AND k.context IS NULL;
    IF v_ok <> v_expected THEN
        RAISE EXCEPTION 'post-check FAILED: % of % expected v1.40.1 client keys are live with the expected source_hash', v_ok, v_expected;
    END IF;
    RAISE NOTICE 'post-check OK: % v1.40.1 client keys live', v_ok;
END $$;

COMMIT;
