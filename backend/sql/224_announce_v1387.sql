-- 224: queue the v1.38.7 release announcement for the #releases channel.
-- Delivered by the bot's poll_channel_posts loop (ack-after-send, #105).
-- Idempotent: the WHERE NOT EXISTS guard keys on the version marker, so the
-- deploy wrapper's ||-retry (#243) cannot double-post.
BEGIN;

INSERT INTO pending_channel_posts (channel_id, content, sort_order)
SELECT '1498731888813277294', content, 0
FROM (VALUES (
'**Sid''s Competitive Rounds v1.38.7 is out!** :trophy:

**Tournaments, front and center:**
- A gold TOURNAMENT banner in-game shows your exact bracket position, and every Discord surface (results, live bets, gambler pings) tags bracket matches with a trophy.
- **The missing tournament DMs are here** — after every bracket match, both players get told exactly what''s next: who you face (with the deadline), what you''re waiting on, "You''re not out!" on a first loss, your placement on elimination, and a champion''s DM. A separate DM lands the moment your next match goes live, retried until it reaches you.
- Tournament matches are always spectatable — including sync tournament rooms, which couldn''t be spectated at all before.
- The tournament bets popup is clickable again.

**Also in this release:**
- Same-region 1v1 pairs now land in their home region (no more two Europeans meeting in a US room).
- New **Poison** body color in the shop — the exact green from the card itself. 3000g.
- Post-match disconnect diagnostics for code rooms (the real fix is coming as its own patch — we found the mechanism).
- More Ukrainian/Swedish translations.

Update: the mod auto-updates on launch, or grab it from Thunderstore / GitHub.
<https://github.com/SidNDeed/SidsCompetitiveRounds/releases/tag/v1.38.7>'
)) AS v(content)
WHERE NOT EXISTS (
    SELECT 1 FROM pending_channel_posts
    WHERE content LIKE '%v1.38.7 is out!%'
);

DO $$
DECLARE n int;
BEGIN
    SELECT COUNT(*) INTO n FROM pending_channel_posts
     WHERE content LIKE '%v1.38.7 is out!%';
    IF n <> 1 THEN
        RAISE EXCEPTION 'announce post-check: expected exactly 1 v1.38.7 announcement row, found %', n;
    END IF;
    RAISE NOTICE 'announce post-check OK (1 row queued)';
END $$;

COMMIT;
