-- 134_series_resume_forever.sql  (July 20)
--
-- Item 4: unfinished ranked series now carry over FOREVER (the 7-day resume
-- window let leavers wait it out and bank the elo). Code change removes the
-- expiry prune; this migration resurrects the undecided series that were
-- already abandoned so they reattach the next time their pair plays.
--
-- Part A — resurrect clean candidates: abandoned, undecided (nobody at 2
-- wins), at least one real match, NOT the pre-v1.26.5 zombie-cleanup era
-- (those rows were purged for being buggy, not stale), pair has no
-- currently-active series, and the pair has NOT played again since (pairs
-- that replayed already got fresh completed series with Glicko applied —
-- merging would rewrite rating history; their old partials stay abandoned
-- as audit trail). Newest row per pair only.
--
-- Part B — bug #78 cleanup: the Sid/SpineOfGlass phantom series created by
-- the casual→ranked upgrade while SpineOfGlass wasn't running the mod
-- (proven in the bug-78 log bundle: hasMod=False). Abandon the series and
-- restore its match to casual. Runs BEFORE Part A textually but is excluded
-- from resurrection by its invalidation_reason either way.
--
-- Part C — publish the corrected RANKED section to the FAQ channel (the
-- posted copy still says "up to 7 days"). New pending_channel_posts row per
-- the 110_faq_channel_post.sql mechanism (the bot can't edit old posts; the
-- superseded message needs a manual delete).
--
-- Idempotent: Part A's WHERE re-matches nothing once resurrected (status
-- flips to 'active'), Part B is guarded on current values, Part C on the
-- (channel_id, sort_order) existence check.

-- ── Part B: bug #78 phantom (before Part A so it can't be resurrected) ──
UPDATE matches
   SET is_ranked = false,
       series_id = NULL
 WHERE id = '60331607-7ae0-4d65-95a9-b24d16685a82'
   AND is_ranked = true;

UPDATE ranked_series
   SET status = 'abandoned',
       invalidated_at = NOW(),
       invalidation_reason = 'phantom_casual_upgrade'
 WHERE id = '93e66cb1-e8d4-41eb-a5d7-0f57d2fcd5f1'
   AND status = 'active';

-- ── Part A: resurrect expired/stalled undecided series ──
WITH cand AS (
    SELECT rs.id,
           rs.player1_id,
           rs.player2_id,
           LEAST(rs.player1_id::text, rs.player2_id::text)    AS pa,
           GREATEST(rs.player1_id::text, rs.player2_id::text) AS pb,
           COALESCE((SELECT MAX(m.ended_at) FROM matches m WHERE m.series_id = rs.id),
                    rs.created_at) AS last_activity
    FROM ranked_series rs
    WHERE rs.status = 'abandoned'
      AND rs.is_tournament = FALSE
      AND rs.p1_series_wins < 2
      AND rs.p2_series_wins < 2
      AND COALESCE(rs.invalidation_reason, '') NOT IN
          ('zombie_pre_v1.26.5_cleanup', 'phantom_casual_upgrade')
      AND EXISTS (SELECT 1 FROM matches m WHERE m.series_id = rs.id)
),
eligible AS (
    SELECT DISTINCT ON (c.pa, c.pb) c.id
    FROM cand c
    WHERE NOT EXISTS (              -- pair never played again after this partial
            SELECT 1 FROM matches m2
            WHERE ((m2.player1_id = c.player1_id AND m2.player2_id = c.player2_id)
                OR (m2.player1_id = c.player2_id AND m2.player2_id = c.player1_id))
              AND m2.ended_at > c.last_activity + INTERVAL '30 minutes'
          )
      AND NOT EXISTS (              -- pair has no live series to collide with
            SELECT 1 FROM ranked_series ra
            WHERE ra.status = 'active'
              AND ((ra.player1_id = c.player1_id AND ra.player2_id = c.player2_id)
                OR (ra.player1_id = c.player2_id AND ra.player2_id = c.player1_id))
          )
      AND NOT EXISTS (              -- pair never got a LATER completed series
            -- (independent of the 30-min match buffer: a replacement series
            -- forked AFTER the partial and finished within that grace window
            -- already applied Glicko — resurrecting the partial would
            -- double-rate the pair; catches SlopsOn1/Toast57 June 4,
            -- verified the only such row of the 53)
            SELECT 1 FROM ranked_series r2
            WHERE r2.id <> c.id
              AND r2.status = 'completed'
              AND ((r2.player1_id = c.player1_id AND r2.player2_id = c.player2_id)
                OR (r2.player1_id = c.player2_id AND r2.player2_id = c.player1_id))
              AND r2.created_at > c.last_activity
          )
    ORDER BY c.pa, c.pb, c.last_activity DESC
)
UPDATE ranked_series rs
   SET status = 'active',
       invalidated_at = NULL,
       invalidation_reason = NULL
 WHERE rs.id IN (SELECT id FROM eligible);

-- ── Part C: corrected FAQ RANKED section (posts at channel bottom) ──
INSERT INTO pending_channel_posts (channel_id, content, sort_order)
SELECT '1159243585309384805', $faq$**RANKED — HOW A GAME QUALIFIES** *(updated)*

A match records as **ranked** only when **both** players:
1. Have the mod installed and running, and
2. Have ranked enabled (F5 → Ranked tab → the Enable/Disable button).

Everything else records as **casual** (still tracked, no rating change). The mod shows a notice at match start when your opponent isn't ranked-capable, so you know before you invest 10 minutes.

- Games vs vanilla (unmodded) players can never be ranked.
- Ranked queue matches (F5 → Search Ranked) are always ranked — queueing is consent.
- Ranked plays as a **best-of-3 series** vs the same opponent. Ratings (Glicko-2) apply when the series completes.
- If a series gets interrupted (crash, disconnect), just rematch the same player — the series **resumes where it left off**, no matter how much later. **Unfinished series never expire**, so leaving mid-series can't save your rating.
- Leaving mid-series counts as a DC on your record; your leave % is visible on the leaderboard. Occasional crashes won't tank it, rage-quits will.$faq$, 7
WHERE NOT EXISTS (SELECT 1 FROM pending_channel_posts WHERE channel_id = '1159243585309384805' AND sort_order = 7);
