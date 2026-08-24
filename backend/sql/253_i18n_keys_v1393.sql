-- 253: i18n client keys for v1.39.3 (Aug 23-24 batch). 8 NEW keys:
-- the mute-when-tabbed toggle pair (2f77738, staged for this release), the
-- Info-library search additions, and Spirit's 'Damage types & buffs' article
-- (title + 3 body parts + byline). The additive half of POST
-- /admin/i18n/sync-keys, written as a migration because this seat's
-- AdminSecret does not verify (403, #406/#421) - same shape as 248/251.
-- Live keys absent from the local catalogue are orphans and deliberately NOT
-- swept here (248/251 precedent - the next real sync-keys run owns
-- retirement).
-- key_id = sha1("client\0" + English)[:16], source_hash = sha1(English),
-- sensitive per tools/i18n_sync_keys.py SENSITIVE_MARKERS (imported, not
-- copied). Idempotent; explicit transaction (#340).
-- APPLY WITH (or after) the v1.39.3 release - portal-facing only, harmless
-- earlier, pointless before it.

BEGIN;

INSERT INTO i18n_keys (key_id, namespace, msgctxt, source_hash, sensitive, max_px, context, updated_at)
SELECT v.key_id, v.namespace, v.msgctxt, v.source_hash, v.sensitive, NULL, NULL, NOW()
  FROM (VALUES
('292ca68628bacd23', 'client', $k253$Mutes game audio while the window is unfocused during online play. The menu stays audible; sound returns the moment you tab back in.$k253$, 'd8eb5564ef93ac1a12635ff57f715edc227be02e', FALSE),
('39b640c135d8a2c3', 'client', $k253$No articles match your search.$k253$, 'a56da30dfbe68320419ddfbcbf5fb5a103ff4de5', FALSE),
('6b5fb58c52c8a481', 'client', $k253$<color=#FFD94D><b>THE 0.35 SECOND WINDOW</b></color>

To prepare you for this knowledge, I must first admit that I lied in the table. Where it states that Bullet Damage triggers a Refresh with a plain Yes, it should carry an asterisk: it does most of the time, but not all of the time. Presumably to help balance cards like Burst and Spray, the developers put a system in place that turns quickly repeated non-Conditional damage into Conditional damage. Shoot an opponent once and you get non-Conditional damage; shoot them again within a window of around 0.35 seconds and that second shot is Conditional. The window resets after every shot. Below, quick secondary (and tertiary) shots are denoted QShoot:

<color=#FFD94D>RefreshValid</color><pos=30%>False<pos=44%>False<pos=58%>True<pos=72%>False<pos=86%>True
<color=#FFD94D>Action</color><pos=30%>Shoot<pos=44%>QShoot<pos=58%>Silence<pos=72%>QShoot<pos=86%>Silence
<color=#FFD94D>Refresh?</color><pos=30%>Yes<pos=44%>No<pos=58%>Yes<pos=72%>No<pos=86%>Yes

<color=#FFD94D>RefreshValid</color><pos=30%>False<pos=44%>False<pos=58%>True<pos=72%>False<pos=86%>True
<color=#FFD94D>Action</color><pos=30%>Shoot<pos=44%>Silence<pos=58%>QShoot<pos=72%>Silence<pos=86%>QShoot
<color=#FFD94D>Refresh?</color><pos=30%>Yes<pos=44%>No<pos=58%>Yes<pos=72%>No<pos=86%>Yes

<color=#FFD94D><b>THERE ARE NO DAMAGE TYPES</b></color>

Now that you understand this, I must admit that I lied a second time. I misled you, cajoled you, into believing that Conditional and non-Conditional damage are two separate damage types, individually bestowed upon certain attacks by the developers. This is incorrect. Damage is treated the same regardless of its source. In reality there are no damage types at all. So how is damage decided to be Conditional or not? The damage decides it. Literally. How many points of damage you are trying to deal determines whether Refresh will not activate at all, activate Conditionally, or activate always (unless it lands inside the 0.35 second window, in which case it becomes Conditional).

I discovered this when stacking Silence. While a regular Silence has a max damage of around 9, stacking two Silences can reach as high as 17, likely more. I say 'reach' because Silence deals AoE damage - the further you are from the target, the less damage you deal. Regardless: with Silence's damage over 10, it becomes non-Conditional. Stack two Silences and a Refresh and you can loop Silences infinitely - provided you land every Silence in the over-10 damage range. Fall into the 5-to-10 range and it becomes Conditional again; fall under 5 damage and no Refresh is ever triggered. You also cannot cycle Silences too fast, or the 0.35 second window triggers and turns your non-Conditional damage Conditional again. (See why this was such a nightmare to figure out.)

The magical thing is that this range applies to every single damage source. Stack enough Frost Slams or Shockwaves and you can produce the same result. The same holds for AoE explosion damage from Timed Detonation or Explosive Bullet. Regular bullets have a minimum damage of 14, so you cannot reach Conditional with damage reduction alone - but if your opponent gets Decay, the individual ticks each carry such low damage that you get no Refreshes back. Or at least you should not: due to tick inconsistency you might occasionally get one or two, at a vastly reduced rate. Conversely, stack enough damage and even when it is divided between ticks you still have enough for constant Refreshes. For cards like EMP and Bombs Away, which cannot change their damage, this revelation means nothing. It also means little for Demonic Pact, Frost Slam and Shockwave, as the stacking needed to raise their damage to the next band is not realistic within a normal game.

<color=#FFD94D><b>THE FULL DECISION, AS A FLOW</b></color>

Deal damage:
- Under 5 damage: nothing happens.
- Between 5 and 10 damage (Conditional):
   If RefreshValid is true - a Refresh triggers, and RefreshValid flips to false.
   If RefreshValid is false - no Refresh, and RefreshValid flips to true.
- Over 10 damage:
   Inside the 0.35 second window - the window resets and the hit is treated like the 5-to-10 case above.
   Outside the window - a Refresh always triggers, the window begins, and RefreshValid is set to false.

That amounts to all my current understanding of Conditional damage. My model of what is going on behind the scenes is entirely a construction (I have not seen the source code), but it correctly predicts all currently tested behaviour, and I have been thorough. Still, there are limits: I do not know whether the RefreshValid bool is held by the attacker or the target - that is, whether every player has a cap on the Refreshes they can trigger for themselves, or every target has a cap on the Refreshes they can trigger for others. In a 1v1 this makes no difference, but in an FFA it would. If only there was a free-to-play type gamemode I could use to test this feature out!

<color=#FFD94D><b>CONCLUSION</b></color>

Now, as beautifully complex as this system is, I do have to ask how on earth the developers thought it would be a good idea. What is it supposed to be balancing? Why does the amount of damage dictate Refreshes? How was anyone supposed to know any of this? Questions only the warped mind who dreamt up this system can answer.

I do appreciate the subtleties of the system, but from a gameplay perspective it is abominable. No real human is going to accurately calculate their RefreshValid state in the middle of a fight - that is, if you ever actually get a build where this information matters. The chances that my findings here will affect your next 30 matches range from low to non-existent. At the end of the day, the player experience this system produces is one of confusion, frustration, and randomness. Yet, all of that said, I would not want it changed. Why? Because if it was, the last week of my life would have been wasted.

Thank you for reading my ramblings. I hope you will at least find the table useful.

<color=#8A8A93>Related reading: <color=#7FD4FF>Blocking</color> covers what a block actually does and which cards ride it; <color=#7FD4FF>Poison & damage over time</color> covers how tick damage lands and syncs.</color>$k253$, '25f8ec2ccd6de665d397ed4d11c7720be30e0c93', TRUE),
('89f91f91fd4ef06f', 'client', $k253$<color=#FFD94D><b>SELF VS OPPONENT DAMAGE</b></color>

From the table it is pretty clear that most damage falls into two categories: damage dealt to your opponent and damage dealt to yourself. Damage dealt to your opponent will almost always trigger all cards and buffs, whereas damage dealt to yourself will only ever trigger Scavenger. This fundamental remains true whether it be damage directly from bullets, AoE effects, or even niche effects like Demonic Pact's life drain.

<color=#FFD94D><b>ODDITIES</b></color>

- <color=#7FE87F>Abyssal Countdown</color> - despite dealing direct AoE damage to an opponent, it will never trigger any cards or buffs. Not even Scavenger. It is unique in this.
- <color=#7FE87F>Brawler</color> - for whatever reason, the particle effect attached to Brawler is activated upon self-damage, despite Brawler not truly activating. Potentially something that would appreciate a fix from Sid.
- <color=#7FE87F>Demonic Pact</color> - uniquely, its AoE does not affect the user. To balance this and prevent damage stacking, the AoE has terrible, though not completely non-existent, damage and knockback scaling. Its drain damage is applied pre-fire, not post-fire, meaning the player is always missing one bullet despite not being able to run out of ammo (unless Combine stacking reduces them to a single bullet in the clip - impossible without exceeding the card maximum, and thus irrelevant). And Scavenger still activates even when the player does not actually lose any health due to death prevention.
- <color=#7FE87F>Life Stealer</color> - similarly to Demonic Pact, all appropriate cards and buffs activate even if no health is actually drained due to death prevention. This includes lifesteal: it seems lifesteal is calculated from the maximum damage that could be applied, not the actual decrease in health. Further testing with overkill bullet damage and Leech affirms this. Tick damage like Parasite, however, will not give the maximum lifesteal return upon death. Something to be aware of in FFA or when against Phoenix.

<color=#FFD94D><b>REFRESH AND CONDITIONAL DAMAGE</b></color>

Now we come to Conditional damage. To put it simply, Conditional damage 'balances' Refresh, such that you can never trigger two Refreshes in a row using Conditional damage. From my research it has become clear that every player holds an invisible boolean value which I will call RefreshValid. As a boolean it can occupy two states, true or false. When RefreshValid is true, the next time you deal Conditional damage you get a successful Refresh, but RefreshValid then flips to false. If you deal Conditional damage while RefreshValid is false, you do not receive a Refresh - but RefreshValid flips back to true, so your next instance of Conditional damage will trigger one. Already having a block ready, and so not needing a Refresh, has no impact on this flipping.

The gameplay ramifications are best illustrated through Silence. Beginning a game, RefreshValid is set to false, so your first Silence fails to trigger a Refresh. (I have not been able to test whether the bool resets between rounds - it does not reset on death, resurrection or new card picks, so I suspect it does not.) After your first failed Refresh, RefreshValid is set to true. Thus your next Silence triggers a Refresh but resets RefreshValid to false. So it continues in an endless loop where every other Silence triggers a successful Refresh. Each column below is one action; the top row is the RefreshValid state BEFORE it:

<color=#FFD94D>RefreshValid</color><pos=30%>False<pos=44%>True<pos=58%>False<pos=72%>True<pos=86%>False
<color=#FFD94D>Action</color><pos=30%>Silence<pos=44%>Silence<pos=58%>Silence<pos=72%>Silence<pos=86%>Silence
<color=#FFD94D>Refresh?</color><pos=30%>No<pos=44%>Yes<pos=58%>No<pos=72%>Yes<pos=86%>No

However, this is if you only use Silence. Other Refresh activators can disrupt the every-other pattern: hit your opponent with a bullet (non-Conditional damage) and you receive a successful Refresh AND reset RefreshValid to false. Depending on where in the pattern you put your shot, you can snag an extra Refresh:

<color=#FFD94D>RefreshValid</color><pos=30%>False<pos=44%>True<pos=58%>False<pos=72%>True<pos=86%>False
<color=#FFD94D>Action</color><pos=30%>Silence<pos=44%>Shoot<pos=58%>Silence<pos=72%>Silence<pos=86%>Silence
<color=#FFD94D>Refresh?</color><pos=30%>No<pos=44%>Yes<pos=58%>No<pos=72%>Yes<pos=86%>No

<color=#FFD94D>RefreshValid</color><pos=30%>False<pos=44%>True<pos=58%>False<pos=72%>False<pos=86%>True
<color=#FFD94D>Action</color><pos=30%>Silence<pos=44%>Silence<pos=58%>Shoot<pos=72%>Silence<pos=86%>Silence
<color=#FFD94D>Refresh?</color><pos=30%>No<pos=44%>Yes<pos=58%>Yes<pos=72%>No<pos=86%>Yes

Sadly, this is not the end of the document, because the ROUNDS developers saw fit to introduce another mechanic. I do hope you, dear reader, appreciate the relative ease with which you get to possess this information as compared to the hours of madness I spent obtaining it.$k253$, 'b2548c95d5dfdc947754eb8e7d9bd831b3c9f3e1', TRUE),
('a802c5f027c63d99', 'client', $k253$Mute audio when tabbed out: <color=#88FF88>ON</color>$k253$, '8f74390c71443cd9546ba57bc48e3ca3fe9fa0fe', FALSE),
('b866b3bb57469add', 'client', $k253$<color=#8A8A93>Research and write-up by Spirit - 'On Damage Types and Buff Activation', University of Rounds. Reproduced for this library with light reformatting; the testing, the findings and the voice are all his.</color>

Via thorough testing in the sandbox game mode with an additional controller player, I have catalogued which types of damage trigger which cards and buffs. The main cards in question are Scavenger, Refresh, Brawler, and Taste of Blood. Lifesteal as a character stat bestowed by numerous cards has also been considered. My results split damage into three main categories: opponent damage, self-damage, and Conditional damage. Damage to your opponent via nearly any means will trigger all cards and buffs, with the exception of specific types of Conditional damage. For various reasons, some Conditional damage, typically from block cards, will not consistently trigger Refresh but will still trigger all other buffs. Finally, any form of self-damage will always activate Scavenger, but nothing else. There are, of course, numerous oddities and exceptions.

<color=#FFD94D><b>THE TABLE OF DAMAGE INTERACTIONS</b></color>

Columns: Scav = Scavenger, Brawl = Brawler, ToB = Taste of Blood, Steal = lifesteal, Refr = Refresh. Cond = triggers conditionally (explained below).

<color=#FFD94D>Damage source<pos=34%>Scav<pos=45%>Brawl<pos=56%>ToB<pos=67%>Steal<pos=78%>Refr</color>
Bullet damage<pos=34%>Yes<pos=45%>Yes<pos=56%>Yes<pos=67%>Yes<pos=78%>Yes
Bullet damage (self)<pos=34%>Yes<pos=45%>No<pos=56%>No<pos=67%>No<pos=78%>No
Abyssal Countdown<pos=34%>No<pos=45%>No<pos=56%>No<pos=67%>No<pos=78%>No
Bombs Away<pos=34%>Yes<pos=45%>Yes<pos=56%>Yes<pos=67%>Yes<pos=78%>Cond
Bombs Away (self)<pos=34%>Yes<pos=45%>No<pos=56%>No<pos=67%>No<pos=78%>No
Decay<pos=34%>Yes<pos=45%>Yes<pos=56%>Yes<pos=67%>Yes<pos=78%>Cond
Decay (self)<pos=34%>Yes<pos=45%>No<pos=56%>No<pos=67%>No<pos=78%>No
Demonic Pact (self)<pos=34%>Yes<pos=45%>No<pos=56%>No<pos=67%>No<pos=78%>No
Demonic Pact (AoE)<pos=34%>Yes<pos=45%>Yes<pos=56%>Yes<pos=67%>Yes<pos=78%>Cond
EMP<pos=34%>Yes<pos=45%>Yes<pos=56%>Yes<pos=67%>Yes<pos=78%>Cond
EMP (self)<pos=34%>Yes<pos=45%>No<pos=56%>No<pos=67%>No<pos=78%>No
Explosive Bullet<pos=34%>Yes<pos=45%>Yes<pos=56%>Yes<pos=67%>Yes<pos=78%>Cond
Explosive Bullet (self)<pos=34%>Yes<pos=45%>No<pos=56%>No<pos=67%>No<pos=78%>No
Frost Slam<pos=34%>Yes<pos=45%>Yes<pos=56%>Yes<pos=67%>Yes<pos=78%>No
Lifestealer<pos=34%>Yes<pos=45%>Yes<pos=56%>Yes<pos=67%>Yes<pos=78%>Cond
Overpower<pos=34%>Yes<pos=45%>Yes<pos=56%>Yes<pos=67%>Yes<pos=78%>Yes
Parasite<pos=34%>Yes<pos=45%>Yes<pos=56%>Yes<pos=67%>Yes<pos=78%>Cond
Parasite (self)<pos=34%>Yes<pos=45%>No<pos=56%>No<pos=67%>No<pos=78%>No
Poison<pos=34%>Yes<pos=45%>Yes<pos=56%>Yes<pos=67%>Yes<pos=78%>Cond
Poison (self)<pos=34%>Yes<pos=45%>No<pos=56%>No<pos=67%>No<pos=78%>No
Radiance<pos=34%>Yes<pos=45%>Yes<pos=56%>Yes<pos=67%>Yes<pos=78%>Cond
Saw<pos=34%>Yes<pos=45%>Yes<pos=56%>Yes<pos=67%>Yes<pos=78%>Cond
Shield Charge<pos=34%>Yes<pos=45%>Yes<pos=56%>Yes<pos=67%>Yes<pos=78%>Yes
Silence<pos=34%>Yes<pos=45%>Yes<pos=56%>Yes<pos=67%>Yes<pos=78%>Cond
Shockwave<pos=34%>Yes<pos=45%>Yes<pos=56%>Yes<pos=67%>Yes<pos=78%>No
Static Field<pos=34%>Yes<pos=45%>Yes<pos=56%>Yes<pos=67%>Yes<pos=78%>Cond
Supernova<pos=34%>Yes<pos=45%>Yes<pos=56%>Yes<pos=67%>Yes<pos=78%>Yes
Timed Detonation<pos=34%>Yes<pos=45%>Yes<pos=56%>Yes<pos=67%>Yes<pos=78%>Cond
Timed Detonation (self)<pos=34%>Yes<pos=45%>No<pos=56%>No<pos=67%>No<pos=78%>No
Toxic Cloud<pos=34%>Yes<pos=45%>Yes<pos=56%>Yes<pos=67%>Yes<pos=78%>Cond
Toxic Cloud (self)<pos=34%>Yes<pos=45%>No<pos=56%>No<pos=67%>No<pos=78%>No

All of these tests were carried out in the sandbox gamemode using two players, one on keyboard, the other on controller. Each test was repeated multiple times to ensure the results were consistent, or at least consistently inconsistent. No distinction was made between Timed Detonation AoE damage latched onto a player vs latched onto a surface.

Promising potential damage dealers, such as Chilling Presence, were excluded due to both their failure to trigger any cards or buffs and their failure to deal any damage. Every entry on the list deals damage in some form, and every unique way to deal damage has an entry. Thus, there are no methods to trigger any damage-dealing cards or buffs without dealing some amount of damage. That might seem obvious but, given the weirdness of the rest of the system, one can never be too sure.$k253$, '34e1da105396b008eb570bdf67a78f97037f438e', FALSE),
('cb80aaef215f676c', 'client', $k253$Damage types & buffs$k253$, '10d9adc648f4c2f08f64a863676777cec2bce624', FALSE),
('edf4af82b6d6ea0e', 'client', $k253$Mute audio when tabbed out: <color=#FF9966>OFF</color>$k253$, '83faee2755ec624629eae20327b5e665067401b3', FALSE)
) AS v(key_id, namespace, msgctxt, source_hash, sensitive)
ON CONFLICT (key_id) DO UPDATE SET retired_at = NULL, updated_at = NOW();

-- Post-check: exactly the inserted id-set must be live. Id-set equality, not
-- a table-total equality - concurrent sync runs may move totals (#168 rerun
-- safety; the id-set check is the actual invariant and is order-independent).
DO $$
DECLARE v_ok INTEGER;
BEGIN
    SELECT COUNT(*) INTO v_ok FROM i18n_keys
     WHERE retired_at IS NULL AND key_id IN ('292ca68628bacd23','39b640c135d8a2c3','6b5fb58c52c8a481','89f91f91fd4ef06f','a802c5f027c63d99','b866b3bb57469add','cb80aaef215f676c','edf4af82b6d6ea0e');
    IF v_ok <> 8 THEN
        RAISE EXCEPTION 'post-check FAILED: % of 8 v1.39.3 keys live', v_ok;
    END IF;
    RAISE NOTICE 'post-check OK: all 8 v1.39.3 keys live';
END $$;

COMMIT;
