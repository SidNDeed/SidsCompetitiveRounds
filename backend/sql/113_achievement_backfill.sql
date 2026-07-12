-- 113_achievement_backfill.sql — Bug batch item 2 (July 12)
--
-- Retroactively grant every achievement whose criteria can be replayed from
-- stored data. Grants mirror _grant_achievement_inline exactly:
--   * player_achievements row (unlocked_at = when it was actually earned,
--     NOW() for rating peaks where no event timestamp exists)
--   * +100g each: gold_transactions (reason='achievement', reference_id=key)
--     + players.gold_earned bump — paid ONLY for rows newly inserted here
--   * slayer titles (title_sid_slayer / title_stan_slayer) become owned
--
-- Idempotent: re-running inserts nothing (ON CONFLICT DO NOTHING) and
-- therefore pays nothing.
--
-- NOT backfillable (client-only signals that were never persisted):
--   untouchable, pacifist, immovable_object, grounded, instinct, god_build,
--   deep_end, rise_from_the_ashes, the_comeback_kid.
-- clutch is only computable where point_timeline exists (post-mig-111), and
-- the inline server check has covered that whole window — nothing to replay.
-- team_sweep was already backfilled by migrations 084/088.
--
-- Card-name spellings verified against prod match_cards (July 12):
-- PRISTINEPERSEVERANCE and DRILLAMMO are the real normalized names (the bare
-- PRISTINE/DRILL keys in the original server check never matched — fixed in
-- main.py the same day); SNEAKYBULLETS is a rare variant of SNEAKY.

BEGIN;

-- ── Working tables ─────────────────────────────────────────────────────────

CREATE TEMP TABLE _ach_grants (
    player_id   UUID        NOT NULL,
    key         VARCHAR(64) NOT NULL,
    unlocked_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (player_id, key)
) ON COMMIT DROP;

-- Valid 1v1 matches (2v2 rows live in team_matches; phantom rows created in
-- team_ rooms are excluded the same way the history endpoint excludes them).
CREATE TEMP TABLE _mres ON COMMIT DROP AS
SELECT m.id AS match_id,
       m.winner_id,
       m.ended_at,
       COALESCE(m.is_ranked, false) AS is_ranked,
       m.player1_id, m.player2_id,
       CASE WHEN m.winner_id = m.player1_id THEN COALESCE(m.p1_rounds_won, 0)
            ELSE COALESCE(m.p2_rounds_won, 0) END AS w_rounds,
       CASE WHEN m.winner_id = m.player1_id THEN COALESCE(m.p2_rounds_won, 0)
            ELSE COALESCE(m.p1_rounds_won, 0) END AS l_rounds
FROM matches m
WHERE m.invalidated_at IS NULL
  AND m.winner_id IS NOT NULL
  AND m.ended_at IS NOT NULL
  AND (m.photon_room_id IS NULL OR LEFT(m.photon_room_id, 5) != 'team_');

-- Both sides of every match, for streak replays.
CREATE TEMP TABLE _msides ON COMMIT DROP AS
SELECT r.match_id, r.ended_at, r.is_ranked, r.winner_id, r.w_rounds, r.l_rounds,
       r.player1_id AS pid FROM _mres r
UNION ALL
SELECT r.match_id, r.ended_at, r.is_ranked, r.winner_id, r.w_rounds, r.l_rounds,
       r.player2_id FROM _mres r;

-- Per-(match, player) card multiset, normalized like _norm_card().
CREATE TEMP TABLE _decks ON COMMIT DROP AS
SELECT mc.match_id, mc.player_id,
       UPPER(REGEXP_REPLACE(mc.card_name, '[^a-zA-Z0-9]', '', 'g')) AS n,
       COUNT(*) AS cnt
FROM match_cards mc
JOIN _mres r ON r.match_id = mc.match_id
GROUP BY 1, 2, 3;

CREATE TEMP TABLE _deckq ON COMMIT DROP AS
SELECT d.match_id, d.player_id,
       bool_or(d.n = 'BARRAGE')                                  AS has_barrage,
       bool_or(d.n = 'SPRAY')                                    AS has_spray,
       bool_or(d.n = 'EXPLOSIVEBULLET')                          AS has_explosive,
       bool_or(d.n = 'BURST')                                    AS has_burst,
       bool_or(d.n = 'HEALINGFIELD')                             AS has_healing,
       bool_or(d.n IN ('SNEAKY', 'SNEAKYBULLETS'))               AS has_sneaky,
       bool_or(d.n IN ('DRILL', 'DRILLAMMO'))                    AS has_drill,
       bool_or(d.n = 'EMPOWER')                                  AS has_empower,
       bool_or(d.n = 'MAYHEM')                                   AS has_mayhem,
       bool_or(d.n = 'CHASE')                                    AS has_chase,
       COALESCE(SUM(d.cnt) FILTER (WHERE d.n = 'SUPERNOVA'), 0)  AS nova_cnt,
       COALESCE(SUM(d.cnt) FILTER (WHERE d.n = 'SAW'), 0)        AS saw_cnt,
       COALESCE(SUM(d.cnt) FILTER (WHERE d.n IN ('PRISTINE', 'PRISTINEPERSEVERANCE')), 0) AS pristine_cnt,
       COALESCE(SUM(d.cnt) FILTER (WHERE d.n = 'GLASSCANNON'), 0) AS glass_cnt,
       MAX(d.cnt)                                                AS max_cnt
FROM _decks d
GROUP BY 1, 2;

-- ── 1. Card-based, per-match ───────────────────────────────────────────────
-- Sweep set + win-gated combos mirror _check_combo_achievements (winner only).
-- silent_assassin/total_mayhem/fragile_perfection/no_escape mirror the CLIENT
-- checks (5-0 sweep + card in the winner's build). stacked_deck mirrors the
-- client too: 5+ copies, NO win requirement.

INSERT INTO _ach_grants
SELECT player_id, key, MIN(ended_at) FROM (
    -- 5-0 sweep + card in build (winner)
    SELECT q.player_id, 'bullet_hell'::varchar(64) AS key, r.ended_at
      FROM _deckq q JOIN _mres r ON r.match_id = q.match_id
     WHERE q.player_id = r.winner_id AND r.w_rounds >= 5 AND r.l_rounds = 0 AND q.has_barrage
    UNION ALL
    SELECT q.player_id, 'spray_and_pray', r.ended_at
      FROM _deckq q JOIN _mres r ON r.match_id = q.match_id
     WHERE q.player_id = r.winner_id AND r.w_rounds >= 5 AND r.l_rounds = 0 AND q.has_spray
    UNION ALL
    SELECT q.player_id, 'demolitionist', r.ended_at
      FROM _deckq q JOIN _mres r ON r.match_id = q.match_id
     WHERE q.player_id = r.winner_id AND r.w_rounds >= 5 AND r.l_rounds = 0 AND q.has_explosive
    UNION ALL
    SELECT q.player_id, 'controlled_burst', r.ended_at
      FROM _deckq q JOIN _mres r ON r.match_id = q.match_id
     WHERE q.player_id = r.winner_id AND r.w_rounds >= 5 AND r.l_rounds = 0 AND q.has_burst
    UNION ALL
    SELECT q.player_id, 'field_medic', r.ended_at
      FROM _deckq q JOIN _mres r ON r.match_id = q.match_id
     WHERE q.player_id = r.winner_id AND r.w_rounds >= 5 AND r.l_rounds = 0 AND q.has_healing
    UNION ALL
    SELECT q.player_id, 'silent_assassin', r.ended_at
      FROM _deckq q JOIN _mres r ON r.match_id = q.match_id
     WHERE q.player_id = r.winner_id AND r.w_rounds >= 5 AND r.l_rounds = 0 AND q.has_sneaky
    UNION ALL
    SELECT q.player_id, 'total_mayhem', r.ended_at
      FROM _deckq q JOIN _mres r ON r.match_id = q.match_id
     WHERE q.player_id = r.winner_id AND r.w_rounds >= 5 AND r.l_rounds = 0 AND q.has_mayhem
    UNION ALL
    SELECT q.player_id, 'fragile_perfection', r.ended_at
      FROM _deckq q JOIN _mres r ON r.match_id = q.match_id
     WHERE q.player_id = r.winner_id AND r.w_rounds >= 5 AND r.l_rounds = 0 AND q.glass_cnt >= 1
    UNION ALL
    SELECT q.player_id, 'no_escape', r.ended_at
      FROM _deckq q JOIN _mres r ON r.match_id = q.match_id
     WHERE q.player_id = r.winner_id AND r.w_rounds >= 5 AND r.l_rounds = 0 AND q.has_chase
    -- win + build combos (winner, any score)
    UNION ALL
    SELECT q.player_id, 'double_nova', r.ended_at
      FROM _deckq q JOIN _mres r ON r.match_id = q.match_id
     WHERE q.player_id = r.winner_id AND q.nova_cnt >= 2
    UNION ALL
    SELECT q.player_id, 'lumberjack', r.ended_at
      FROM _deckq q JOIN _mres r ON r.match_id = q.match_id
     WHERE q.player_id = r.winner_id AND q.saw_cnt >= 2
    UNION ALL
    SELECT q.player_id, 'pristine_perfection', r.ended_at
      FROM _deckq q JOIN _mres r ON r.match_id = q.match_id
     WHERE q.player_id = r.winner_id AND q.pristine_cnt >= 2
    UNION ALL
    SELECT q.player_id, 'double_glass', r.ended_at
      FROM _deckq q JOIN _mres r ON r.match_id = q.match_id
     WHERE q.player_id = r.winner_id AND q.glass_cnt >= 2
    UNION ALL
    SELECT q.player_id, 'silent_drill', r.ended_at
      FROM _deckq q JOIN _mres r ON r.match_id = q.match_id
     WHERE q.player_id = r.winner_id AND q.has_sneaky AND q.has_drill
    UNION ALL
    SELECT q.player_id, 'sustained_power', r.ended_at
      FROM _deckq q JOIN _mres r ON r.match_id = q.match_id
     WHERE q.player_id = r.winner_id AND q.has_empower AND q.has_healing
    UNION ALL
    SELECT q.player_id, 'collector', r.ended_at
      FROM _deckq q JOIN _mres r ON r.match_id = q.match_id
     WHERE q.player_id = r.winner_id AND q.max_cnt >= 4
    -- 5 copies of one card, win NOT required (client semantics)
    UNION ALL
    SELECT q.player_id, 'stacked_deck', r.ended_at
      FROM _deckq q JOIN _mres r ON r.match_id = q.match_id
     WHERE q.max_cnt >= 5
) t
GROUP BY 1, 2
ON CONFLICT (player_id, key) DO NOTHING;

-- ── 2. flawless — 5 consecutive 5-0 wins over the player's full sequence ───
-- Gaps-and-islands; unlocked_at = the 5th sweep of the first qualifying run.

INSERT INTO _ach_grants
SELECT pid, 'flawless', MIN(ended_at) FROM (
    SELECT pid, ended_at,
           ROW_NUMBER() OVER (PARTITION BY pid, grp ORDER BY ended_at) AS n
    FROM (
        SELECT pid, ended_at, sweep,
               ROW_NUMBER() OVER (PARTITION BY pid ORDER BY ended_at)
             - ROW_NUMBER() OVER (PARTITION BY pid, sweep ORDER BY ended_at) AS grp
        FROM (
            SELECT pid, ended_at,
                   (winner_id = pid AND w_rounds >= 5 AND l_rounds = 0) AS sweep
            FROM _msides
        ) s
    ) g
    WHERE sweep
) runs
WHERE n = 5
GROUP BY 1
ON CONFLICT (player_id, key) DO NOTHING;

-- ── 3. Casual win streaks (sequence = casual games only) ───────────────────

INSERT INTO _ach_grants
SELECT pid, t.key, MIN(ended_at) FROM (
    SELECT pid, ended_at,
           ROW_NUMBER() OVER (PARTITION BY pid, grp ORDER BY ended_at) AS n
    FROM (
        SELECT pid, ended_at, won,
               ROW_NUMBER() OVER (PARTITION BY pid ORDER BY ended_at)
             - ROW_NUMBER() OVER (PARTITION BY pid, won ORDER BY ended_at) AS grp
        FROM (
            SELECT pid, ended_at, (winner_id = pid) AS won
            FROM _msides
            WHERE NOT is_ranked
        ) s
    ) g
    WHERE won
) runs
CROSS JOIN (VALUES (100, 'casual_century'), (200, 'casual_conqueror'), (500, 'touch_grass')) t(thr, key)
WHERE runs.n = t.thr
GROUP BY 1, 2
ON CONFLICT (player_id, key) DO NOTHING;

-- ── 4. Ranked-series win streaks ───────────────────────────────────────────

INSERT INTO _ach_grants
SELECT pid, t.key, MIN(completed_at) FROM (
    SELECT pid, completed_at,
           ROW_NUMBER() OVER (PARTITION BY pid, grp ORDER BY completed_at) AS n
    FROM (
        SELECT pid, completed_at, won,
               ROW_NUMBER() OVER (PARTITION BY pid ORDER BY completed_at)
             - ROW_NUMBER() OVER (PARTITION BY pid, won ORDER BY completed_at) AS grp
        FROM (
            SELECT rs.player1_id AS pid, rs.completed_at, (rs.winner_id = rs.player1_id) AS won
            FROM ranked_series rs
            WHERE rs.status = 'completed' AND rs.invalidated_at IS NULL
              AND rs.winner_id IS NOT NULL AND rs.completed_at IS NOT NULL
            UNION ALL
            SELECT rs.player2_id, rs.completed_at, (rs.winner_id = rs.player2_id)
            FROM ranked_series rs
            WHERE rs.status = 'completed' AND rs.invalidated_at IS NULL
              AND rs.winner_id IS NOT NULL AND rs.completed_at IS NOT NULL
        ) s
    ) g
    WHERE won
) runs
CROSS JOIN (VALUES (25, 'on_fire'), (50, 'unstoppable'), (100, 'immortal')) t(thr, key)
WHERE runs.n = t.thr
GROUP BY 1, 2
ON CONFLICT (player_id, key) DO NOTHING;

-- ── 5. Slayers — won a completed ranked series against Sid / Stan ──────────

INSERT INTO _ach_grants
SELECT rs.winner_id, st.key, MIN(rs.completed_at)
FROM ranked_series rs
JOIN players tgt ON tgt.id IN (rs.player1_id, rs.player2_id)
JOIN (VALUES ('76561198040410653', 'regicide'),
             ('76561198983423367', 'stan_slayer')) st(sid, key)
  ON st.sid = tgt.steam_id
WHERE rs.status = 'completed' AND rs.invalidated_at IS NULL
  AND rs.winner_id IS NOT NULL AND rs.winner_id <> tgt.id
  AND rs.completed_at IS NOT NULL
GROUP BY 1, 2
ON CONFLICT (player_id, key) DO NOTHING;

-- ── 6. Rating peaks (1v1 or 2v2, matching _grant_rating_achievements) ──────
-- peak_rating, not current — "reach" semantics survive later decay.

INSERT INTO _ach_grants
SELECT p.player_id, t.key, NOW()
FROM (
    SELECT COALESCE(gr.player_id, g2.player_id) AS player_id,
           GREATEST(COALESCE(gr.peak_rating, 0), COALESCE(g2.peak_rating, 0)) AS peak
    FROM glicko_ratings gr
    FULL OUTER JOIN glicko_ratings_2v2 g2 ON g2.player_id = gr.player_id
) p
CROSS JOIN (VALUES (1700.0, 'rising_star'), (2030.0, 'master_rank'), (2330.0, 'grand_master')) t(thr, key)
WHERE p.peak >= t.thr
ON CONFLICT (player_id, key) DO NOTHING;

-- ── Apply: insert, pay gold for NEW rows only, grant slayer titles ──────────

CREATE TEMP TABLE _ach_new (player_id UUID, key VARCHAR(64)) ON COMMIT DROP;

WITH ins AS (
    INSERT INTO player_achievements (player_id, achievement_key, unlocked_at)
    SELECT g.player_id, g.key, g.unlocked_at
    FROM _ach_grants g
    JOIN players p ON p.id = g.player_id
    ON CONFLICT (player_id, achievement_key) DO NOTHING
    RETURNING player_id, achievement_key
)
INSERT INTO _ach_new SELECT player_id, achievement_key FROM ins;

INSERT INTO gold_transactions (player_id, amount, reason, reference_id, created_at)
SELECT player_id, 100, 'achievement', key, NOW() FROM _ach_new;

UPDATE players p
SET gold_earned = COALESCE(p.gold_earned, 0) + s.total
FROM (SELECT player_id, COUNT(*) * 100 AS total FROM _ach_new GROUP BY 1) s
WHERE p.id = s.player_id;

INSERT INTO player_items (player_id, item_id, purchase_price, purchased_at)
SELECT n.player_id, si.id, 0, NOW()
FROM _ach_new n
JOIN shop_items si ON si.sku = CASE n.key WHEN 'regicide'    THEN 'title_sid_slayer'
                                          WHEN 'stan_slayer' THEN 'title_stan_slayer' END
WHERE n.key IN ('regicide', 'stan_slayer')
ON CONFLICT (player_id, item_id) DO NOTHING;

-- ── Summary (visible in /migrate output) ───────────────────────────────────

SELECT key, COUNT(*) AS newly_granted
FROM _ach_new
GROUP BY 1
ORDER BY 2 DESC, 1;

SELECT COUNT(*) AS total_new_grants,
       COUNT(DISTINCT player_id) AS players_affected,
       COUNT(*) * 100 AS gold_paid
FROM _ach_new;

COMMIT;
