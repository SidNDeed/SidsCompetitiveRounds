<!-- Hit/Block card-skew analysis, July 20 2026 — sample: Sid, Stan, DrunkenWiLL, Levity, galaxy ice.
     Companion to the counting fixes shipped with bugs #77/#80 (kill-blow Prefix, __result/forceAttack gates,
     burst multiplication). Data covers 2026-07-06 → 07-20 (stats columns only exist since 07-06). -->

# Hit% / Block% card-skew analysis — Sid, Stan, DrunkenWiLL, Levity, galaxy ice

## 0. TL;DR

- **EMP is the single biggest hit% destroyer** (-15.9 pts pooled): its block-ring is implemented as forced attacks of the player's *own gun* — every ring projectile counts as a "bullet fired" (245.9 fired/min in EMP matches vs ~30 baseline; one Sid match hit 510/min).
- **Ricochet** matches show the same fired-inflation + hit% collapse (-14.3 raw, **-18.8 after removing EMP matches**; Sid: 4.89% over 8,181 shots) — mechanism only partially resolved (see §4.2).
- **Burst inflates hit% by ~+18-22 pts within-player** — a true counting bug: the `bursts` field multiplies real bullets ×3 but the fired counter only credits `numberOfProjectiles`.
- **Bug #77 is NOT fully fixed**: post-v1.33.0 matches (July 19-20) show players **winning 5 rounds with 0 counted hits** in builds that can only kill via direct bullets (Careful Planning alone: 1/54; CP+Fastball: 0/32). Kill-blow hits are still dropped — almost certainly because the counting Postfix on `ProjectileHit.RPCA_DoHit` never runs when the vanilla body throws during round-end teardown. Recommend moving the count to a **Prefix or Finalizer**.
- **Block% skew has a structural asymmetry**: activations are counted at `Block.TryBlock` (user/ready blocks only) but successes at `Block.DoBlock` (any absorb, any trigger type) — so auto-block cards (**Abyssal Countdown +19.1, Echo +5.2, Shield Charge +2.9**) get free successes with uncounted activations. Proven by a real row with 16 successes / 12 activations whose owner held exactly one card: Abyssal Countdown.
- **Empower (-5.3) and Refresh (-3.6) deflate block%** behaviorally — players block *offensively* (6.5 and 8.8 activations/min vs ~5.1 baseline).

## 1. Dataset and methodology

Per-side stat columns (`p1_/p2_bullets_fired/hit`, `blocks_activated/successful`) are **populated only from 2026-07-06 through 2026-07-20** — 387 player-sides with `bullets_fired > 0` across the five players. All queries: `matches` joined to the five `players.id`s on either side, `invalidated_at IS NULL`, card sets from `DISTINCT match_cards(match_id, player_id, card_name)`. All rates are **pooled weighted** (Σhits/Σfired, Σsucc/Σact), never averages of ratios. "With vs without" = that card's matches vs all other matches in the same pool. Minimum n=5 for the main tables; lower-n suggestive findings listed separately.

| Player | matches (all) | sides with fired>0 | Σfired | hit% | Σblocks act | block% |
|---|---|---|---|---|---|---|
| Sid | 2,030 | 190 | 38,713 | 13.44 | 4,916 | 19.49 |
| Stan | 1,293 | 119 | 10,419 | 34.67 | 2,176 | 16.73 |
| galaxy ice | 471 | 59 | 9,952 | 18.08 | 1,237 | 14.15 |
| DrunkenWiLL | 354 | 10 | 1,552 | 10.70 | 345 | 13.04 |
| Levity | 594 | 9 | 1,206 | 12.85 | 181 | 18.23 |

Clean baselines (EMP/Ricochet matches excluded): Sid 21.37% (169 sides), Stan 37.32% (115), galaxy ice 25.26% (54), pooled ≈ 25.4%. **DrunkenWiLL and Levity are too thin (n=10/9) for per-player card conclusions.**

Sanity checks: **0** rows with hit>fired (the client's `_hitsRemaining` budget enforces hit ≤ fired, GameStateWatcher.cs:232-268); **0** rows fired=0-with-hits; **1** row succ>act (see §5.1 — it's evidence, not noise); one Stan row `blocks_successful=16 > blocks_activated=12` (match `1b52ad60-b9db-40be-95f3-204781c8f8b2`, 2026-07-13).

Card-name vocabulary pulled first (88 distinct): includes a **"Fastball" (1,284 picks) vs "Fast Ball" (158) split** and a family of Turkish dotless-ı duplicates ("Wınd Up" 11, "Poıson" 6, "Combıne" 5, …, ~55 rows total) — canonicalization gaps, negligible for this analysis but worth a cleanup pass.

## 2. Counting mechanics (verified in code — this is what "fired/hit/act/succ" actually mean)

- **fired** = `max(1, Gun.numberOfProjectiles)` per `Gun.Attack` **call** where the gun's player PhotonView `IsMine` — Harmony Postfix in plugin/Plugin.cs:3921-3961. Three consequences:
  1. **The Postfix ignores `__result`.** `Gun.Attack` returns `false` while reloading (decompiled Gun.cs:358-361), and the input consumer gates on `IsReady()` (cooldown only, not reload — decompile `-Module-.cs`:38705, call at 38738) — so **every click during a reload is counted as fired bullets with no projectile spawned**.
  2. **`bursts`, charge-`attacks`, and `chargeNumberOfProjectilesTo` are invisible to it** (Gun.cs:363, 423-437): one Attack call can spawn `attacks × bursts × numberOfProjectiles(+charge)` real bullets but only `numberOfProjectiles` are counted → **denominator undercount → hit% inflation** for Burst/charge builds (hits draw from the shared budget).
  3. **Card-forced attacks of the player's own gun are counted**: `SpawnObjectEffect.DoEffect` fires `holding.holdable`'s Gun with `forceAttack:true` (`-Module-.cs`:31975-32008), `RadarShot.ShootAttacks` fires `wh.gun` (27426-27435); GeneralShooter/RotatingShooter (12822-12838, 28641-28660) drive spawned guns. This is EMP's ring.
- **hit** = Postfix on `ProjectileHit.RPCA_DoHit` (Plugin.cs:4122-4142): unblocked, viewID≠-1, owner-side, enemy team, budget-capped. **A Postfix does not run if the vanilla body throws** — the kill-blow drop mechanism (§4.3).
- **blocks_activated** = `Block.TryBlock` Postfix gated on off-cooldown (Plugin.cs:4151-4235). Only counts blocks that go through TryBlock.
- **blocks_successful** = Postfix on the most-params `Block.DoBlock` = the 3-arg absorb path (decompiled Block.cs:359-364, reached from `ProjectileHit.RPCA_DoHit` wasBlocked branch), ANY trigger type, 1.0s dedup (GameStateWatcher.cs:340-359). **Auto-blocks (Echo `DelayBlock`→`RPCA_DoBlock` Block.cs:299-304; ShieldCharge.cs:126/132/147; Abyssal Countdown's no-cooldown block state) bypass TryBlock entirely** → their absorbs are successes with no matching activation.

## 3. Hit% skew tables

### 3.1 Raw pooled (all 387 sides), sorted by delta — the two inflators dominate

| Card | n | fired(with) | hit% with | hit% without | Δ | fired/min |
|---|---|---|---|---|---|---|
| **Emp** | 17 | 21,399 | 7.31 | 23.17 | **-15.86** | **245.9** |
| **Ricochet** | 14 | 9,331 | 5.52 | 19.84 | **-14.32** | **133.8** |
| Decay | 7 | 5,248 | 6.78 | 18.69 | -11.91 | 138.3 |
| Implode | 5 | 1,132 | 7.69 | 17.87 | -10.18 | 47.0 |
| Refresh | 6 | 1,546 | 8.93 | 17.91 | -8.98 | 52.5 |
| … | | | | | | |
| Static Field | 16 | 1,919 | 31.37 | 17.24 | +14.13 | 23.4 |
| Quick Shot | 25 | 2,951 | 32.80 | 16.92 | +15.88 | 26.5 |
| Demonic Pact | 6 | 1,047 | 34.38 | 17.39 | +16.99 | 32.9 |
| **Target Bounce** | 11 | 980 | 40.71 | 17.31 | **+23.40** | 19.8 |

**Contamination check**: EMP matches carry 84.9% of Decay's fired volume, 75.3% of Echo's, 69.7% of Implode's, 65.4% of Brawler's, 47.7% of Ricochet's — the negative tail below EMP/Ricochet is mostly co-occurrence, not card effects. Every match >100 fired/min contains EMP and/or Ricochet (19 matches listed; max 510/min = Sid 7/20 with Decay+Emp+Poison+Ricochet, 4,454 fired / 4.3% hit).

### 3.2 Clean pooled (EMP and Ricochet matches removed; baseline 25.4%)

Top positive:

| Card | n | fired | hit% with | hit% without | Δ |
|---|---|---|---|---|---|
| **Quick Shot** | 23 | 1,861 | 48.04 | 24.19 | **+23.85** |
| **Burst** | 16 | 1,522 | 42.44 | 24.68 | **+17.76** |
| **Target Bounce** | 11 | 980 | 40.71 | 25.01 | **+15.71** |
| Demonic Pact | 6 | 1,047 | 34.38 | 25.17 | +9.22 |
| Homing | 16 | 1,862 | 34.16 | 24.96 | +9.20 |
| Big Bullet | 30 | 2,927 | 32.80 | 24.78 | +8.02 |
| Dazzle | 5 | 757 | 32.50 | 25.29 | +7.21 |
| Static Field | 16 | 1,919 | 31.37 | 25.10 | +6.27 |
| Cold Bullets | 16 | 2,001 | 30.98 | 25.11 | +5.88 |
| Leech | 40 | 5,475 | 30.10 | 24.59 | +5.51 |
| Empower | 22 | 1,907 | 30.20 | 25.17 | +5.03 |
| Steady Shot | 35 | 3,592 | 29.73 | 24.96 | +4.77 |

Top negative (clean): Shield Charge -10.67 (n=13), Teleport -10.61 (n=6), Trickster -8.27, Overpower -8.24, Quick Reload -8.17, Radar Shot -8.04, Supernova -7.65, Shields Up -7.39, Huge -6.10. **These are almost all Sid-heavy utility/defense picks and largely reflect player mix** (Sid's clean baseline 21.4% vs Stan's 37.3%); Radar Shot is the proof case — pooled -8.04, but **within-player it's positive for both pickers** (Sid +2.98, galaxy ice +0.76), and its mechanic (aim-compensated auto-shots at the target, `-Module-.cs`:27426) should help accuracy.

### 3.3 Within-player deltas (clean set, n≥3) — the de-confounded view

| Card | Player | n | fired | with | without (same player) | Δ |
|---|---|---|---|---|---|---|
| Burst | galaxy ice | 10 | 943 | 43.69 | 21.56 | **+22.13** |
| Burst | Sid | 4 | 396 | 36.62 | 21.03 | **+15.59** |
| Quick Shot | Stan | 22 | 1,797 | 48.47 | 34.68 | +13.79 |
| Homing | Sid | 8 | 903 | 28.79 | 20.98 | +7.82 |
| Homing | Stan | 6 | 769 | 43.69 | 36.75 | +6.94 |
| Big Bullet | Sid | 10 | 987 | 32.62 | 20.71 | +11.91 |
| Static Field | Sid | 12 | 1,549 | 26.34 | 20.90 | +5.44 |
| Target Bounce | Stan | 10 | 843 | 42.47 | 36.81 | +5.65 |
| Demonic Pact | Stan | 3 | 426 | 73.71 | 35.59 | +38.12 (tiny n) |
| Empower | Stan | 5 | 473 | 61.73 | 36.02 | +25.71 (vs Sid n=17: -1.71) |
| Cold Bullets | Stan | 5 | 675 | 54.81 | 35.96 | +18.85 (vs galaxy n=3: -14.47 — inconsistent) |
| Glass Cannon | Stan | 10 | 503 | 28.83 | 37.80 | **-8.98** |
| Wind Up | Stan | 16 | 1,403 | 27.44 | 39.06 | -11.62 (vs Sid/galaxy ≈ +1.3) |

Reading: **Burst and Homing replicate across players** (Burst = counting bug, Homing = genuine homing). Quick Shot/Static Field/Big Bullet/Target Bounce are consistent-direction genuine accuracy aids (faster/bigger/homing-after-bounce bullets, slowed enemies). Empower/Cold Bullets/Steady Shot flip sign between players → build-context noise, not card effects. Glass Cannon's within-Stan -9.0 fits the kill-blow-drop family (§4.3): +75% damage → more hits are round-enders → more dropped.

## 4. Anomaly classes

### 4.1 Class (a) — shot-count inflation

**EMP** (n=17, a third of ALL pooled shots): "blocking spawns a ring of very low damage slowing projectiles". The ring is forced own-gun attacks (§2.3) → each block adds a full ring to `bullets_fired`; ring projectiles almost never land a counted enemy hit. 245.9 fired/min pooled; galaxy ice with EMP as his ONLY card: 1,349 fired in 235s (344/min, 10.3% hit). Sid 13 matches, 17,202 fired, 6.94%. **EMP's hit% is not the player's aim — exclude EMP matches from any accuracy stat, or stop counting `forceAttack` calls.**

**Ricochet** (n=14 raw / 13 clean): -18.8 clean delta, 6.60% over 4,877 fired; matches at 182-224 fired/min with NO EMP present ("Ricochet, Wind Up" 780 fired/257s at 2.9%; "Fast Forward, Homing, Radiance, Refresh, Ricochet" 975/261s at 2.5%). Mechanism *partially* resolved: bounces don't re-invoke Gun.Attack (decompiled ScreenEdgeBounce.cs has no Attack call), so candidates are (i) the reload phantom-click count (§2.1 — wall-bounce spray play means constant clicking through reloads), and (ii) genuinely spray-oriented play (firing at walls lowers direct-hit rate legitimately). **Recommend a result-aware diagnostic** ([GUN-POST] logging `__result=false` counts per match) before trusting any Ricochet-match accuracy.

Systemic: **clicks during reload are counted as fired for every player and every gun** — the Postfix (Plugin.cs:3928-3958) should capture `bool __result` and return when false. That single change kills the phantom class outright.

### 4.2 Class (b) — hit undercount

The decisive query: matches with fired ≥ 25, hit% < 6, and NORMAL fire rate (< 60/min), with rounds won:

| Player | Date | fired | hit | rounds won | cards |
|---|---|---|---|---|---|
| Sid | 07-15 | 49 | **0** | **5** | Careful Planning, Fastball, Huge |
| Sid | 07-19 | 54 | **1** | **5** | Careful Planning (only card) |
| Sid | 07-20 | 32 | **0** | **5** | Careful Planning, Fastball |
| Sid | 07-19 | 41 | **0** | **5** | Combine, Remote, Sneaky, Thruster, Radiance |
| Stan | 07-19 | 26 | **0** | **5** | Frost Slam, Sneaky |
| Sid | 07-19 | 31 | 0 | 5 | Leech, Toxic Cloud (DOT kills — plausible by design) |
| DrunkenWiLL | 07-14 | 318 | 12 | 3 | Poison, Quick Reload, Timed Detonation, … (DOT/explosion — by design) |

**A Careful Planning-only build (+100% damage, no DOT, no spawned damage) cannot win 5 rounds without landing direct bullet hits.** Three of these matches are July 19-20 — *after* the v1.33.0 (2026-07-17) fix for bug #77 (the pick-phase-gate removal in `OnLocalBulletHit`, GameStateWatcher.cs:249-271). So kill blows are still being lost. The remaining mechanism that fits: the hit counter is a **Postfix** on `ProjectileHit.RPCA_DoHit` — a Harmony Postfix is skipped when the vanilla body throws, and the kill-blow invocation runs death → round-over teardown inside that body. High-damage builds (CP +100%, Glass Cannon +75%, Huge/Combine stacks) make MOST hits kill blows → their hit% craters (CP+Fastball repeated exact-0s). **Fix: count in a Prefix (or Finalizer) on RPCA_DoHit instead.** Note CP's pooled delta looks harmless (-1.5 clean) because the drops hide behind its many normal matches — pooled deltas cannot catch this class; the zero-hit-with-rounds-won query can (worth making a permanent audit query).

Suggestive (n<5): **Sneaky** — only 2 stat-era matches, both 0 hits with rounds won ("bullets avoid the ground" — possibly a distinct un-counted path; needs more data). **Fastball** — clean delta +0.20 overall, but it appears in 2 of the 3 exact-zero CP matches; +250% bullet speed with one-shot damage is the worst case for the kill-blow drop.

### 4.3 Class (c) — block skew

Baseline 17.8% success, ~5.1 activations/min. Sorted by delta:

| Card | n | act | succ | blk% with | blk% without | Δ | act/min |
|---|---|---|---|---|---|---|---|
| **Abyssal Countdown** | 6 | 142 | 52 | 36.62 | 17.48 | **+19.14** | 4.60 |
| **Shields Up** | 13 | 379 | 93 | 24.54 | 17.48 | **+7.05** | 5.38 |
| Decay | 7 | 212 | 50 | 23.58 | 17.64 | +5.94 | 5.59 |
| Dazzle | 6 | 164 | 38 | 23.17 | 17.68 | +5.49 | 4.56 |
| **Echo** | 15 | 423 | 96 | 22.70 | 17.54 | **+5.15** | 5.67 |
| Radiance | 10 | 255 | 58 | 22.75 | 17.64 | +5.11 | 5.32 |
| Defender | 8 | 191 | 43 | 22.51 | 17.68 | +4.83 | 4.64 |
| Radar Shot | 21 | 544 | 119 | 21.88 | 17.52 | +4.36 | 5.50 |
| **Shield Charge** | 14 | 448 | 92 | 20.54 | 17.64 | +2.90 | 5.57 |
| … | | | | | | | |
| Supernova | 10 | 345 | 48 | 13.91 | 17.94 | -4.03 | 6.33 |
| Silence | 5 | 152 | 21 | 13.82 | 17.86 | -4.04 | 5.72 |
| Shockwave | 27 | 687 | 92 | 13.39 | 18.16 | -4.76 | 5.14 |
| Lifestealer | 5 | 170 | 22 | 12.94 | 17.88 | -4.94 | 5.60 |
| **Empower** | 23 | 681 | 88 | 12.92 | 18.19 | **-5.27** | **6.54** |
| (dishonorable mention) **Refresh** | 6 | 259 | 37 | 14.29 | 17.89 | -3.61 | **8.79** |

**Inflation (counting asymmetry, §2)**: Abyssal Countdown's standing-still state produces repeated no-cooldown blocks that absorb bullets — DoBlock successes with no TryBlock activations. Hard proof: the only succ>act row in the dataset (Stan, 16/12, 2026-07-13) belongs to a player whose entire deck was **Abyssal Countdown** (match `1b52ad60…`). Echo's delayed auto-re-block (Block.cs:303) and Shield Charge's charge blocks (ShieldCharge.cs:126/132/147) are the same class, smaller magnitude. Shields Up (+1 block charge) rides partly on extra real chances, partly on rapid double-absorbs deduped less than double-activations.

**Deflation (behavioral, real activations)**: Empower (block to empower your next shot) and Refresh (block returns on damage dealt) turn block into an offensive resource — activation rates 28% and 73% above baseline with nothing to absorb. Supernova/Shockwave/Lifestealer/Silence (block-effect casts) same pattern. These are genuine "your block% stat will look bad if you play these cards" skews, not bugs — but worth a UI footnote if players compare block% on the leaderboard.

## 5. Per-player quick profiles

- **Sid** — clean 21.4% hit (17,784 shots, 169 sides), 19.5% block. Biggest personal distortions: EMP (6.94% over 17,202 shots) and Ricochet (4.89% over 8,181) — over half his raw shot volume is inflator matches, which is why his raw 13.4% badly understates his aim. Genuine positives: Big Bullet +11.9, Homing +7.8, Static Field +5.4. His CP/Fastball matches carry the kill-blow zero-hit anomaly.
- **Stan** — clean 37.3% (9,378 shots, 115 sides), best aim in the pool; block 16.7%. Quick Shot (+13.8, n=22) and Leech (+11.2) builds; Glass Cannon -9.0 (kill-blow drops); Wind Up -11.6 (charge-gun style mismatch). Owner of the Abyssal Countdown succ>act proof row.
- **galaxy ice** — clean 25.3% (5,646 shots, 54 sides); block 14.2%. Burst +22.1 (counting bug beneficiary); two EMP matches at 344 and 312 fired/min.
- **DrunkenWiLL** — 10 sides only. His 318-fired 58/min 3.8%-hit match is a Poison/Timed Detonation DOT build (undercount-by-design: DOT and explosion damage intentionally don't count as bullet hits).
- **Levity** — 9 sides only; nothing card-attributable at this n.

## 6. Recommended fixes (ranked)

1. **Capture `__result` in the Gun.Attack fired Postfix; don't count `false` returns** (Plugin.cs:3921) — kills reload phantom clicks.
2. **Move hit counting to a Prefix/Finalizer on `ProjectileHit.RPCA_DoHit`** (Plugin.cs:4122) — kills the remaining #77 kill-blow drops (CP/GC/one-shot builds).
3. **Don't count `forceAttack` invocations as fired** — needs the `forceAttack` arg in the Postfix signature; fixes EMP/RadarShot-class ring/auto shots. Alternatively count `bursts × numberOfProjectiles` to fix Burst's denominator at the same time.
4. **Either count auto-block activations (patch `RPCA_DoBlock` for non-Default triggers) or exclude auto-block successes** — closes the Abyssal/Echo/ShieldCharge block% inflation and makes succ ≤ act an invariant.
5. Data hygiene: canonicalize "Fast Ball"→"Fastball" and the Turkish dotless-ı card names in match_cards.

## 7. Caveats

- **Confounding by player**: Stan's 37% baseline vs Sid's 21% means pooled deltas partly measure *who* picks a card (Radar Shot: pooled -8, within-player positive for both pickers). Within-player deltas (§3.3) are the trustworthy column; pooled tables are ranked-entry points only.
- **Skill/meta confound**: good players pick winning cards; winners also play longer matches with more picks. A positive delta ≠ the card improves aim (Demonic Pact +38 is 3 Stan matches).
- **Partial-match exposure**: a card picked in round 4 of 5 is credited with the whole match's shots — dilutes true effects toward zero.
- **Small window**: stats exist only for 2026-07-06 → 07-20 (387 sides); DrunkenWiLL/Levity effectively unmeasurable per-card. Ranked and casual matches are pooled (not split).
- **Both sides' stats come from the reporter's client**, so opponent-side numbers exist only when the opponent had the mod publishing `cr_` stat props; the five players' own sides are well-covered.
- Card effect descriptions sourced from community references: [GameFAQs card list](https://gamefaqs.gamespot.com/pc/317272-rounds/faqs/81303), [Rounds Wiki — All Cards](https://rounds.fandom.com/wiki/All_Cards), [Rounds Wiki — Abyssal Countdown](https://rounds.fandom.com/wiki/Abyssal_Countdown), [Steam guide: All Cards A-Z](https://steamcommunity.com/sharedfiles/filedetails/?id=2445921586).