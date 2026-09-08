-- 288: i18n client keys for the Sept 4 batch (Spirit's charts) (49 NEW keys): the redrawn
-- damage/Refresh charts (labels, headers, flow nodes, the split article
-- paragraphs). This is the additive half of
-- what POST /admin/i18n/sync-keys does, written through the migration channel
-- because this seat's tooling cannot sign the admin HMAC (learning #443).
-- Additive-only (per 248/266/282/286 precedent): the article paragraphs that
-- were split or reworded get NEW key_ids (key_id derives from the source
-- string); their predecessors are left for the real sync tool's retire pass.
-- key_id = sha1("client\0" + English)[:16], source_hash = sha1(English),
-- sensitive per tools/i18n_sync_keys.py's SENSITIVE_MARKERS (imported, not
-- copied). Idempotent AND contract-convergent: the conflict arm is the sync
-- endpoint's own full update, and the post-check RAISES if any expected key is
-- missing, retired, or carries a different source_hash / a stray max_px or
-- context. Explicit transaction (#340). The game namespace is unchanged.
-- Run order: deploy API -> apply this file -> apply 289.

BEGIN;

INSERT INTO i18n_keys (key_id, namespace, msgctxt, source_hash, sensitive, max_px, context, updated_at)
SELECT v.key_id, v.namespace, v.msgctxt, v.source_hash, v.sensitive, NULL, NULL, NOW()
  FROM (VALUES
('00cf7aaf51815456', 'client', $k288$Deal Conditional damage$k288$, 'd6c04483c4b6c4688aeb80a462e1889c65799c35', FALSE),
('03743368bfc09bcf', 'client', $k288$Redrawn from Spirit's diagram: Conditional damage never Refreshes twice in a row.$k288$, '17cf3ff04e9a66a27d2ad22466075f8965e34735', FALSE),
('060ce37e54f9db7d', 'client', $k288$A shot placed second: the shot Refreshes and resets the flag$k288$, '61fc1f50fb545395d209750161092562acaa7e35', TRUE),
('09f590ed72875261', 'client', $k288$The gameplay ramifications are best illustrated through Silence. Beginning a game, RefreshValid is set to false, so your first Silence fails to trigger a Refresh. (I have not been able to test whether the bool resets between rounds - it does not reset on death, resurrection or new card picks, so I suspect it does not.) After your first failed Refresh, RefreshValid is set to true. Thus your next Silence triggers a Refresh but resets RefreshValid to false. So it continues in an endless loop where every other Silence triggers a successful Refresh. Each column below is one action; the top row is the RefreshValid state BEFORE it:$k288$, '80444cd6246036481a041786b427412a711aca7e', TRUE),
('0afe97716e208ec8', 'client', $k288$<color=#FFD94D><b>THERE ARE NO DAMAGE TYPES</b></color>

Now that you understand this, I must admit that I lied a second time. I misled you, cajoled you, into believing that Conditional and non-Conditional damage are two separate damage types, individually bestowed upon certain attacks by the developers. This is incorrect. Damage is treated the same regardless of its source. In reality there are no damage types at all. So how is damage decided to be Conditional or not? The damage decides it. Literally. How many points of damage you are trying to deal determines whether Refresh will not activate at all, activate Conditionally, or activate always (unless it lands inside the 0.35 second window, in which case it becomes Conditional).

I discovered this when stacking Silence. While a regular Silence has a max damage of around 9, stacking two Silences can reach as high as 17, likely more. I say 'reach' because Silence deals AoE damage - the further you are from the target, the less damage you deal. Regardless: with Silence's damage over 10, it becomes non-Conditional. Stack two Silences and a Refresh and you can loop Silences infinitely - provided you land every Silence in the over-10 damage range. Fall into the 5-to-10 range and it becomes Conditional again; fall under 5 damage and no Refresh is ever triggered. You also cannot cycle Silences too fast, or the 0.35 second window triggers and turns your non-Conditional damage Conditional again. (See why this was such a nightmare to figure out.)

The magical thing is that this range applies to every single damage source. Stack enough Frost Slams or Shockwaves and you can produce the same result. The same holds for AoE explosion damage from Timed Detonation or Explosive Bullet. Regular bullets have a minimum damage of 14, so you cannot reach Conditional with damage reduction alone - but if your opponent gets Decay, the individual ticks each carry such low damage that you get no Refreshes back. Or at least you should not: due to tick inconsistency you might occasionally get one or two, at a vastly reduced rate. Conversely, stack enough damage and even when it is divided between ticks you still have enough for constant Refreshes. For cards like EMP and Bombs Away, which cannot change their damage, this revelation means nothing. It also means little for Demonic Pact, Frost Slam and Shockwave, as the stacking needed to raise their damage to the next band is not realistic within a normal game.

Below is a flow chart of all damage possibilities:$k288$, 'c79e55ef850157b7d4923353bba21f93d994478e', TRUE),
('14a19ff455d8ab87', 'client', $k288$More than 10$k288$, 'd5e82416a4a915e30ac4f2873b98cfb88c71bd55', FALSE),
('168a24e7a15c6676', 'client', $k288$Bullet damage$k288$, 'a0e4252cefdd47139828d4b0e4a36f5d513a193a', FALSE),
('1c210f8ba97a1f77', 'client', $k288$All of these tests were carried out in the sandbox gamemode using two players, one on keyboard, the other on controller. Each test was repeated multiple times to ensure the results were consistent, or at least consistently inconsistent. No distinction was made between Timed Detonation AoE damage latched onto a player vs latched onto a surface.

Promising potential damage dealers, such as Chilling Presence, were excluded due to both their failure to trigger any cards or buffs and their failure to deal any damage. Every entry on the list deals damage in some form, and every unique way to deal damage has an entry. Thus, there are no methods to trigger any damage-dealing cards or buffs without dealing some amount of damage. That might seem obvious but, given the weirdness of the rest of the system, one can never be too sure.$k288$, 'e358740b825518d127f9d3b4cffac22635cab524', FALSE),
('2028fedb1737cd34', 'client', $k288$False$k288$, '97cdbdc7feff827efb082a6b6dd2727237cd49fd', FALSE),
('2090d7454716f5e8', 'client', $k288$Set RefreshValid to false$k288$, 'c8ceb506bd0b1b2298c6c72fac7245477473ad3b', FALSE),
('20e9a5200e2bf039', 'client', $k288$(self)$k288$, 'fd48c1054b759ba859d59283ab89f4320a518966', FALSE),
('26c9ea0e87954040', 'client', $k288$Do nothing$k288$, 'd268ba5209c487d727e01c5fd074cb9328ec5243', FALSE),
('2c0e445629c0ccdc', 'client', $k288$Yes$k288$, '5397e0583f14f6c88de06b1ef28f460a1fb5b0ae', FALSE),
('35b7a88c8c43fe2a', 'client', $k288$Is RefreshValid true?$k288$, 'ecf52fe8e70265b69484ec079d7c35e89da2ae77', FALSE),
('3d4e2b0f54660b94', 'client', $k288$ONE CONDITIONAL HIT$k288$, '311b3d10cac9612a322228cd36c80acd4c559724', FALSE),
('4ba89801eabb9fb6', 'client', $k288$<color=#8A8A93>Research and write-up by Spirit - 'On Damage Types and Buff Activation', University of Rounds. Reproduced for this library with light reformatting; the testing, the findings and the voice are all his.</color>

Via thorough testing in the sandbox game mode with an additional controller player, I have catalogued which types of damage trigger which cards and buffs. The main cards in question are Scavenger, Refresh, Brawler, and Taste of Blood. Lifesteal as a character stat bestowed by numerous cards has also been considered. My results split damage into three main categories: opponent damage, self-damage, and Conditional damage. Damage to your opponent via nearly any means will trigger all cards and buffs, with the exception of specific types of Conditional damage. For various reasons, some Conditional damage, typically from block cards, will not consistently trigger Refresh but will still trigger all other buffs. Finally, any form of self-damage will always activate Scavenger, but nothing else. There are, of course, numerous oddities and exceptions.$k288$, '990d4ad856fdff5f16c07c5e047ed0c57a39649d', FALSE),
('4d5cf30764f3830b', 'client', $k288$The same actions in a different order$k288$, '8a37ccdd1183d3dc18cee74c21b8c9c97139c260', FALSE),
('5103660e4f7c993a', 'client', $k288$Between 5 and 10$k288$, '39032d9f6eb0d1bec0ff412b7d9f5b695ce04489', FALSE),
('570c2cdd778837a4', 'client', $k288$True$k288$, '88b33e4e12f75ac8bf792aebde41f1a090f3a612', FALSE),
('61b604ec28fa4123', 'client', $k288$Action$k288$, '97c89a4d6630adeb18fa12ba9976a31413fe293e', FALSE),
('6458681422d8fc26', 'client', $k288$A shot placed third: an extra Refresh$k288$, 'd34adb2bd4ee36ed20f7b9c4217cec2ddfe6e5bd', FALSE),
('681c635979858bca', 'client', $k288$Refresh?$k288$, '036f463fe254002c12fdad59af1d8f79d7072375', FALSE),
('6b363055e82afd04', 'client', $k288$Begin the window$k288$, 'bda1ea7b9ee1096821ac8c0b1b0f26915e087856', FALSE),
('6b44e02890ead855', 'client', $k288$does not trigger$k288$, 'fdeeaaea73befff1c3f2418cccbbd1dc09d4f6e3', FALSE),
('76c6d1804fba8e34', 'client', $k288$Trigger Refresh$k288$, '073d3d4eea1bed0f0b419a090e46c35cfc72e826', FALSE),
('78cb639cb4f609ad', 'client', $k288$Shoot$k288$, 'b301c10b3d0a20c4d34f04d383741c386814b593', FALSE),
('83c65095e784da2a', 'client', $k288$Silence only: every other Silence produces a Refresh$k288$, 'de77b3dd6519ebefbf5f00e9abd750b224069c1f', FALSE),
('8b9e4aa59ba78dec', 'client', $k288$No Refresh$k288$, '285c37a543ee155f487cdff094d9ff12e2cfbdaf', FALSE),
('92833989dbaa8f01', 'client', $k288$EVERY DAMAGE OUTCOME$k288$, 'f92fb4e35825d078ed1fa5f36d7802937cb12b13', FALSE),
('9a8b2e9d295e11ba', 'client', $k288$However, this is if you only use Silence. Other Refresh activators can disrupt the every-other pattern: hit your opponent with a bullet (non-Conditional damage) and you receive a successful Refresh AND reset RefreshValid to false. Depending on where in the pattern you put your shot, you can snag an extra Refresh (the second and third sequences above).

Sadly, this is not the end of the document, because the ROUNDS developers saw fit to introduce another mechanic. I do hope you, dear reader, appreciate the relative ease with which you get to possess this information as compared to the hours of madness I spent obtaining it.$k288$, '24efe03f2c19ba6f6259f895e296d62212b2d870', TRUE),
('a2327401bb098f1b', 'client', $k288$Deal damage$k288$, 'c16670c41d27246a616f267b82eb2db03f8babfa', FALSE),
('a5f7e903662e54ee', 'client', $k288$REFRESHVALID IN PLAY: SILENCE SEQUENCES$k288$, 'bdb859db4ccb3214abc9455d467c163130cc8fe0', FALSE),
('aa1c7cc71ae730dc', 'client', $k288$(AoE)$k288$, 'bc253868db188d01445892d8d79d9b9dd1d64f84', FALSE),
('b0769d6c1aeb4cb0', 'client', $k288$QShoot$k288$, '9c38e7ed34d17340df42ee8a7adf514aae97fe9e', FALSE),
('b1cc8f5df71d3d5e', 'client', $k288$<color=#FFD94D><b>SELF VS OPPONENT DAMAGE</b></color>

From the table it is pretty clear that most damage falls into two categories: damage dealt to your opponent and damage dealt to yourself. Damage dealt to your opponent will almost always trigger all cards and buffs, whereas damage dealt to yourself will only ever trigger Scavenger. This fundamental remains true whether it be damage directly from bullets, AoE effects, or even niche effects like Demonic Pact's life drain.

<color=#FFD94D><b>ODDITIES</b></color>

- <color=#7FE87F>Abyssal Countdown</color> - despite dealing direct AoE damage to an opponent, it will never trigger any cards or buffs. Not even Scavenger. It is unique in this.
- <color=#7FE87F>Brawler</color> - for whatever reason, the particle effect attached to Brawler is activated upon self-damage, despite Brawler not truly activating. Potentially something that would appreciate a fix from Sid.
- <color=#7FE87F>Demonic Pact</color> - uniquely, its AoE does not affect the user. To balance this and prevent damage stacking, the AoE has terrible, though not completely non-existent, damage and knockback scaling. Its drain damage is applied pre-fire, not post-fire, meaning the player is always missing one bullet despite not being able to run out of ammo (unless Combine stacking reduces them to a single bullet in the clip - impossible without exceeding the card maximum, and thus irrelevant). And Scavenger still activates even when the player does not actually lose any health due to death prevention.
- <color=#7FE87F>Life Stealer</color> - similarly to Demonic Pact, all appropriate cards and buffs activate even if no health is actually drained due to death prevention. This includes lifesteal: it seems lifesteal is calculated from the maximum damage that could be applied, not the actual decrease in health. Further testing with overkill bullet damage and Leech affirms this. Tick damage like Parasite, however, will not give the maximum lifesteal return upon death. Something to be aware of in FFA or when against Phoenix.

<color=#FFD94D><b>REFRESH AND CONDITIONAL DAMAGE</b></color>

Now we come to Conditional damage. To put it simply, Conditional damage 'balances' Refresh, such that you can never trigger two Refreshes in a row using Conditional damage. From my research it has become clear that every player holds an invisible boolean value which I will call RefreshValid. As a boolean it can occupy two states, true or false. When RefreshValid is true, the next time you deal Conditional damage you get a successful Refresh, but RefreshValid then flips to false. If you deal Conditional damage while RefreshValid is false, you do not receive a Refresh - but RefreshValid flips back to true, so your next instance of Conditional damage will trigger one. Already having a block ready, and so not needing a Refresh, has no impact on this flipping.$k288$, '196139ffad4d0160ccf4577a8ea90b0011638d78', FALSE),
('b80da06170bb95d3', 'client', $k288$How much damage?$k288$, 'ac5d996d8fe5ffdedebdfe952c24578b1018a362', FALSE),
('c7acaba68380efc4', 'client', $k288$Less than 5$k288$, '9a1e0ba477c9917763fccc9703a1615fc7825a19', FALSE),
('d434848c2300cbae', 'client', $k288$Set RefreshValid to true$k288$, '1d97ecb0b3bc6756d3846d46c2f23a482c695549', FALSE),
('d4723ed96203417e', 'client', $k288$A quick follow-up shot (QShoot) counts as Conditional damage$k288$, '9954788202428cecdadff2a0a65362345ce8612f', FALSE),
('d7cf4979f9ad74e4', 'client', $k288$Conditional - every other time; see RefreshValid below$k288$, '696b63f21cd0801ccf923c12444a40196f9febb0', FALSE),
('d9d65e5bcdfa2dac', 'client', $k288$Lifesteal$k288$, '57239ad99b94977b15b6bb55498ff295eb205f8a', FALSE),
('de84355ebcd60fa2', 'client', $k288$Inside the 0.35 s window?$k288$, '70f1507a50aa1affe9be3d1d4a9a831047950cd9', FALSE),
('dfab60f0e9799dbb', 'client', $k288$That amounts to all my current understanding of Conditional damage. My model of what is going on behind the scenes is entirely a construction (I have not seen the source code), but it correctly predicts all currently tested behaviour, and I have been thorough. Still, there are limits: I do not know whether the RefreshValid bool is held by the attacker or the target - that is, whether every player has a cap on the Refreshes they can trigger for themselves, or every target has a cap on the Refreshes they can trigger for others. In a 1v1 this makes no difference, but in an FFA it would. If only there was a free-to-play type gamemode I could use to test this feature out!

<color=#FFD94D><b>CONCLUSION</b></color>

Now, as beautifully complex as this system is, I do have to ask how on earth the developers thought it would be a good idea. What is it supposed to be balancing? Why does the amount of damage dictate Refreshes? How was anyone supposed to know any of this? Questions only the warped mind who dreamt up this system can answer.

I do appreciate the subtleties of the system, but from a gameplay perspective it is abominable. No real human is going to accurately calculate their RefreshValid state in the middle of a fight - that is, if you ever actually get a build where this information matters. The chances that my findings here will affect your next 30 matches range from low to non-existent. At the end of the day, the player experience this system produces is one of confusion, frustration, and randomness. Yet, all of that said, I would not want it changed. Why? Because if it was, the last week of my life would have been wasted.

Thank you for reading my ramblings. I hope you will at least find the table useful.

<color=#8A8A93>Related reading: <color=#7FD4FF>Blocking</color> covers what a block actually does and which cards ride it; <color=#7FD4FF>Poison & damage over time</color> covers how tick damage lands and syncs.</color>$k288$, 'd9077ef0f07dec9c41db819f4ac30d7295177eb9', FALSE),
('ebc8ae2d4c714ddc', 'client', $k288$Conditional$k288$, 'c3accb895f001e39bb983a80902ba897c94294bd', FALSE),
('efd9786032f9577c', 'client', $k288$QUICK SHOTS INSIDE THE 0.35 SECOND WINDOW$k288$, 'b7d4d9f0f1bf5f98f36ab7bf5a6e1ac3cc32c17e', FALSE),
('f725fffe65b21b6f', 'client', $k288$<color=#FFD94D><b>THE 0.35 SECOND WINDOW</b></color>

To prepare you for this knowledge, I must first admit that I lied in the table. Where it states that Bullet Damage triggers a Refresh with a plain Yes, it should carry an asterisk: it does most of the time, but not all of the time. Presumably to help balance cards like Burst and Spray, the developers put a system in place that turns quickly repeated non-Conditional damage into Conditional damage. Shoot an opponent once and you get non-Conditional damage; shoot them again within a window of around 0.35 seconds and that second shot is Conditional. The window resets after every shot. Below, quick secondary (and tertiary) shots are denoted QShoot:$k288$, '0d145cbc5195fb34ea7021bd4ccb82e1bb473306', TRUE),
('f851a9aad9ea6141', 'client', $k288$TABLE OF DAMAGE INTERACTIONS$k288$, '704ef77f6c313746fb6ba54dd99fce50481d19b1', FALSE),
('fdf90a6e35fd8343', 'client', $k288$triggers$k288$, '0d850d1fb8c4564a96bca7874d3015c0176cbdd0', FALSE),
('ffe4136002328f40', 'client', $k288$Reset the window$k288$, '71bf6674aaabb4f9885c20f994c05de35197d594', TRUE)
  ) AS v(key_id, namespace, msgctxt, source_hash, sensitive)
ON CONFLICT (key_id) DO UPDATE
   SET namespace = EXCLUDED.namespace, msgctxt = EXCLUDED.msgctxt,
       source_hash = EXCLUDED.source_hash, sensitive = EXCLUDED.sensitive,
       max_px = EXCLUDED.max_px, context = EXCLUDED.context,
       retired_at = NULL, updated_at = NOW();

-- Post-check (enforcing): every expected key live with the expected source_hash.
DO $$
DECLARE
    v_expected INT := 49;
    v_ok INT;
BEGIN
    SELECT COUNT(*) INTO v_ok
      FROM i18n_keys k
      JOIN (VALUES
        ('00cf7aaf51815456', 'd6c04483c4b6c4688aeb80a462e1889c65799c35'),
        ('03743368bfc09bcf', '17cf3ff04e9a66a27d2ad22466075f8965e34735'),
        ('060ce37e54f9db7d', '61fc1f50fb545395d209750161092562acaa7e35'),
        ('09f590ed72875261', '80444cd6246036481a041786b427412a711aca7e'),
        ('0afe97716e208ec8', 'c79e55ef850157b7d4923353bba21f93d994478e'),
        ('14a19ff455d8ab87', 'd5e82416a4a915e30ac4f2873b98cfb88c71bd55'),
        ('168a24e7a15c6676', 'a0e4252cefdd47139828d4b0e4a36f5d513a193a'),
        ('1c210f8ba97a1f77', 'e358740b825518d127f9d3b4cffac22635cab524'),
        ('2028fedb1737cd34', '97cdbdc7feff827efb082a6b6dd2727237cd49fd'),
        ('2090d7454716f5e8', 'c8ceb506bd0b1b2298c6c72fac7245477473ad3b'),
        ('20e9a5200e2bf039', 'fd48c1054b759ba859d59283ab89f4320a518966'),
        ('26c9ea0e87954040', 'd268ba5209c487d727e01c5fd074cb9328ec5243'),
        ('2c0e445629c0ccdc', '5397e0583f14f6c88de06b1ef28f460a1fb5b0ae'),
        ('35b7a88c8c43fe2a', 'ecf52fe8e70265b69484ec079d7c35e89da2ae77'),
        ('3d4e2b0f54660b94', '311b3d10cac9612a322228cd36c80acd4c559724'),
        ('4ba89801eabb9fb6', '990d4ad856fdff5f16c07c5e047ed0c57a39649d'),
        ('4d5cf30764f3830b', '8a37ccdd1183d3dc18cee74c21b8c9c97139c260'),
        ('5103660e4f7c993a', '39032d9f6eb0d1bec0ff412b7d9f5b695ce04489'),
        ('570c2cdd778837a4', '88b33e4e12f75ac8bf792aebde41f1a090f3a612'),
        ('61b604ec28fa4123', '97c89a4d6630adeb18fa12ba9976a31413fe293e'),
        ('6458681422d8fc26', 'd34adb2bd4ee36ed20f7b9c4217cec2ddfe6e5bd'),
        ('681c635979858bca', '036f463fe254002c12fdad59af1d8f79d7072375'),
        ('6b363055e82afd04', 'bda1ea7b9ee1096821ac8c0b1b0f26915e087856'),
        ('6b44e02890ead855', 'fdeeaaea73befff1c3f2418cccbbd1dc09d4f6e3'),
        ('76c6d1804fba8e34', '073d3d4eea1bed0f0b419a090e46c35cfc72e826'),
        ('78cb639cb4f609ad', 'b301c10b3d0a20c4d34f04d383741c386814b593'),
        ('83c65095e784da2a', 'de77b3dd6519ebefbf5f00e9abd750b224069c1f'),
        ('8b9e4aa59ba78dec', '285c37a543ee155f487cdff094d9ff12e2cfbdaf'),
        ('92833989dbaa8f01', 'f92fb4e35825d078ed1fa5f36d7802937cb12b13'),
        ('9a8b2e9d295e11ba', '24efe03f2c19ba6f6259f895e296d62212b2d870'),
        ('a2327401bb098f1b', 'c16670c41d27246a616f267b82eb2db03f8babfa'),
        ('a5f7e903662e54ee', 'bdb859db4ccb3214abc9455d467c163130cc8fe0'),
        ('aa1c7cc71ae730dc', 'bc253868db188d01445892d8d79d9b9dd1d64f84'),
        ('b0769d6c1aeb4cb0', '9c38e7ed34d17340df42ee8a7adf514aae97fe9e'),
        ('b1cc8f5df71d3d5e', '196139ffad4d0160ccf4577a8ea90b0011638d78'),
        ('b80da06170bb95d3', 'ac5d996d8fe5ffdedebdfe952c24578b1018a362'),
        ('c7acaba68380efc4', '9a1e0ba477c9917763fccc9703a1615fc7825a19'),
        ('d434848c2300cbae', '1d97ecb0b3bc6756d3846d46c2f23a482c695549'),
        ('d4723ed96203417e', '9954788202428cecdadff2a0a65362345ce8612f'),
        ('d7cf4979f9ad74e4', '696b63f21cd0801ccf923c12444a40196f9febb0'),
        ('d9d65e5bcdfa2dac', '57239ad99b94977b15b6bb55498ff295eb205f8a'),
        ('de84355ebcd60fa2', '70f1507a50aa1affe9be3d1d4a9a831047950cd9'),
        ('dfab60f0e9799dbb', 'd9077ef0f07dec9c41db819f4ac30d7295177eb9'),
        ('ebc8ae2d4c714ddc', 'c3accb895f001e39bb983a80902ba897c94294bd'),
        ('efd9786032f9577c', 'b7d4d9f0f1bf5f98f36ab7bf5a6e1ac3cc32c17e'),
        ('f725fffe65b21b6f', '0d145cbc5195fb34ea7021bd4ccb82e1bb473306'),
        ('f851a9aad9ea6141', '704ef77f6c313746fb6ba54dd99fce50481d19b1'),
        ('fdf90a6e35fd8343', '0d850d1fb8c4564a96bca7874d3015c0176cbdd0'),
        ('ffe4136002328f40', '71bf6674aaabb4f9885c20f994c05de35197d594')
      ) AS e(key_id, source_hash) ON e.key_id = k.key_id
     WHERE k.namespace = 'client' AND k.retired_at IS NULL
       AND k.source_hash = e.source_hash
       AND k.max_px IS NULL AND k.context IS NULL;
    IF v_ok <> v_expected THEN
        RAISE EXCEPTION 'post-check FAILED: % of % expected sept4 client keys are live with the expected source_hash', v_ok, v_expected;
    END IF;
    RAISE NOTICE 'post-check OK: % sept4 client keys live', v_ok;
END $$;

COMMIT;
