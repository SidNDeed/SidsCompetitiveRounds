using System;
using UnityEngine;

namespace CompetitiveRounds
{
    /// <summary>The in-game explainer library backing the Info tab (Sid, Aug 23:
    /// "explain as much of the game/mod mechanics as possible").
    ///
    /// PATTERN (from ModeInfoText): every body is an expression-bodied PROPERTY
    /// whose literal sits directly inside I18n.Tr, so the extractor harvests it
    /// (#295a) and the lookup runs at render time, after I18nCatalogues.Install().
    /// This file is listed in tools/i18n_extract.py FILES (#357).
    ///
    /// SIZE RULE: each body literal stays under ~7,000 chars - the i18n
    /// pack/proposal cap is 8,000 (PackMaxStringLen, main.py) and translations
    /// run longer than English. Longer topics are split into part-properties
    /// joined in the registry with "\n\n" (whole self-contained SECTION blocks,
    /// each its own translation unit - #298c forbids splicing sentence
    /// fragments, not joining sections).
    ///
    /// CONTENT RULES (see the article style guide in the session notes):
    /// ASCII-only prose (#47), no double quotes inside the verbatim bodies
    /// (#295b), gold section headers, cyan cross-refs whose names must equal
    /// the Title of a registered article. EVERY factual claim in these bodies
    /// was verified against code/decompile/asset data before shipping and
    /// fact-checked by a cold review - do not edit wording without
    /// re-verifying (#351: this file is read by 2,500 players as
    /// authoritative). Editing English text re-keys its translations (#289).
    ///
    /// The three mode articles COMPOSE ModeInfoText's shipped popup docs with
    /// an extension so popup and wiki can never drift apart (#279).</summary>
    internal static class InfoLibrary
    {
        /// <summary>One reading-pane segment: EITHER a Tr'd rich-text block
        /// (one of the SAME literals Body joins — never a re-split of one,
        /// #289) OR an InfoViz visual key. Typed on design-review advice so
        /// no body text can ever collide with a marker syntax.</summary>
        internal struct Seg
        {
            public string Text;
            public string Viz;
            public static Seg T(string text) => new Seg { Text = text };
            public static Seg V(string vizKey) => new Seg { Viz = vizKey };
        }

        internal sealed class Article
        {
            public string Key;          // stable id (not player-visible)
            public Func<string> Title;  // Tr'd short title: nav label + page heading
            public Func<string> Body;   // Tr'd rich-text body
            /// <summary>Optional interleaved reading-pane layout (Aug 30 viz
            /// upgrade). Null = plain single-text article. Body stays
            /// authoritative for search and the no-viz fallback either way —
            /// it must join the exact text segments listed here.</summary>
            public Func<Seg[]> Segments;
        }

        internal sealed class Category
        {
            public Func<string> Title;
            public Color Color;         // nav header + article heading accent
            public Article[] Articles;
        }

        internal static Article Find(string key)
        {
            foreach (var c in Categories) foreach (var a in c.Articles) if (a.Key == key) return a;
            return null;
        }

        internal static Color ColorOf(string key)
        {
            foreach (var c in Categories) foreach (var a in c.Articles) if (a.Key == key) return c.Color;
            return Color.white;
        }

        // Category accents (distinct at nav-header size; readable on the dark panel).
        private static readonly Color CAT_START = new Color(0.92f, 0.92f, 0.95f);
        private static readonly Color CAT_GAME = new Color(1f, 0.85f, 0.30f);
        private static readonly Color CAT_MODES = new Color(0.50f, 0.83f, 1f);
        private static readonly Color CAT_TOURN = new Color(0.78f, 0.61f, 1f);
        private static readonly Color CAT_RATING = new Color(0.50f, 0.91f, 0.50f);
        private static readonly Color CAT_FAIR = new Color(1f, 0.72f, 0.30f);
        private static readonly Color CAT_VANILLA = new Color(0.40f, 0.88f, 0.80f);
        private static readonly Color CAT_COSM = new Color(1f, 0.61f, 0.82f);

        private static Category[] _cats;
        internal static Category[] Categories => _cats ?? (_cats = new[]
        {
            new Category { Title = () => I18n.Tr("Start Here"), Color = CAT_START, Articles = new[]
            {
                new Article { Key = "start-here",    Title = () => I18n.Tr("About this library"), Body = () => StartHere },
                new Article { Key = "controls",      Title = () => I18n.Tr("Controls & keys"),    Body = () => ControlsIntro + "\n\n" + ControlsOutro,
                              Segments = () => new[] { Seg.T(ControlsIntro), Seg.V("keyboard"), Seg.T(ControlsOutro) } },
                new Article { Key = "getting-better",Title = () => I18n.Tr("Getting better"),     Body = () => GettingBetter },
            }},
            new Category { Title = () => I18n.Tr("Game Mechanics"), Color = CAT_GAME, Articles = new[]
            {
                new Article { Key = "blocking",     Title = () => I18n.Tr("Blocking"),                 Body = () => Blocking,
                              Segments = () => new[] { Seg.V("block-window"), Seg.T(Blocking) } },
                new Article { Key = "poison",       Title = () => I18n.Tr("Poison & damage over time"),Body = () => Poison,
                              Segments = () => new[] { Seg.V("dot-timeline"), Seg.T(Poison) } },
                new Article { Key = "grow",         Title = () => I18n.Tr("Grow"),                     Body = () => Grow,
                              Segments = () => new[] { Seg.V("grow-curve"), Seg.T(Grow) } },
                // Community research: Spirit's 'On Damage Types and Buff
                // Activation' (Aug 23). ATTRIBUTED work presented as his
                // findings (byline in part 1) - the factual claims are his
                // sandbox research, faithfully reproduced from his PDF, not
                // re-derived from the decompile like the house articles.
                new Article { Key = "damage-buffs", Title = () => I18n.Tr("Damage types & buffs"),     Body = () => DamageBuffsP1 + "\n\n" + DamageBuffsP2 + "\n\n" + DamageBuffsP3,
                              Segments = () => new[] { Seg.V("refresh-flow"), Seg.T(DamageBuffsP1 + "\n\n" + DamageBuffsP2 + "\n\n" + DamageBuffsP3) } },
                new Article { Key = "movement-tech",Title = () => I18n.Tr("Movement & shield tech"),   Body = () => MovementTech,
                              Segments = () => new[] { Seg.V("movement-window"), Seg.T(MovementTech) } },
                new Article { Key = "netcode",      Title = () => I18n.Tr("Netcode & Photon"),         Body = () => Netcode,
                              Segments = () => new[] { Seg.V("netcode-map"), Seg.T(Netcode) } },
                new Article { Key = "vanilla-bugs", Title = () => I18n.Tr("Known vanilla bugs"),       Body = () => VanillaBugs },
            }},
            new Category { Title = () => I18n.Tr("Modes"), Color = CAT_MODES, Articles = new[]
            {
                new Article { Key = "ranked-1v1", Title = () => I18n.Tr("Ranked 1v1"), Body = () => Ranked1v1,
                              Segments = () => new[] { Seg.V("series-format"), Seg.T(Ranked1v1) } },
                new Article { Key = "mode-2v2",   Title = () => I18n.Tr("2v2"),        Body = () => ModeInfoText.Team + "\n\n" + Mode2v2Ext,
                              Segments = () => new[] { Seg.V("team-format"), Seg.T(ModeInfoText.Team + "\n\n" + Mode2v2Ext) } },
                new Article { Key = "mode-1v2",   Title = () => I18n.Tr("1v2"),        Body = () => ModeInfoText.Ovt + "\n\n" + Mode1v2Ext,
                              Segments = () => new[] { Seg.V("ovt-format"), Seg.T(ModeInfoText.Ovt + "\n\n" + Mode1v2Ext) } },
                new Article { Key = "mode-ffa",   Title = () => I18n.Tr("FFA"),        Body = () => ModeInfoText.Ffa + "\n\n" + ModeFfaExt,
                              Segments = () => new[] { Seg.V("ffa-scoring"), Seg.T(ModeInfoText.Ffa + "\n\n" + ModeFfaExt) } },
                new Article { Key = "spectating", Title = () => I18n.Tr("Spectating"), Body = () => Spectating },
            }},
            new Category { Title = () => I18n.Tr("Tournaments"), Color = CAT_TOURN, Articles = new[]
            {
                new Article { Key = "tourn-how",      Title = () => I18n.Tr("How tournaments run"), Body = () => TournHow,
                              Segments = () => new[] { Seg.V("bracket-flow"), Seg.T(TournHow) } },
                new Article { Key = "tourn-bot",      Title = () => I18n.Tr("The bot & check-ins"), Body = () => TournBot },
                new Article { Key = "tourn-forfeits", Title = () => I18n.Tr("Deadlines & forfeits"),Body = () => TournForfeits,
                              Segments = () => new[] { Seg.V("forfeit-clock"), Seg.T(TournForfeits) } },
            }},
            new Category { Title = () => I18n.Tr("Ratings & Rewards"), Color = CAT_RATING, Articles = new[]
            {
                new Article { Key = "rating",  Title = () => I18n.Tr("Ratings (Glicko-2)"), Body = () => Rating,
                              Segments = () => new[] { Seg.V("rank-ladder"), Seg.T(Rating), Seg.V("glicko-rd") } },
                new Article { Key = "rewards", Title = () => I18n.Tr("XP, Gold & levels"),  Body = () => Rewards,
                              Segments = () => new[] { Seg.V("gold-sources"), Seg.T(Rewards), Seg.V("xp-curve") } },
                new Article { Key = "betting", Title = () => I18n.Tr("Betting"),            Body = () => Betting,
                              Segments = () => new[] { Seg.V("bet-window"), Seg.T(Betting) } },
            }},
            new Category { Title = () => I18n.Tr("Tracking & Fair Play"), Color = CAT_FAIR, Articles = new[]
            {
                new Article { Key = "tracking",     Title = () => I18n.Tr("How games are tracked"), Body = () => Tracking,
                              Segments = () => new[] { Seg.V("report-pipeline"), Seg.T(Tracking) } },
                new Article { Key = "when-counts",  Title = () => I18n.Tr("When a game counts"),    Body = () => WhenCounts,
                              Segments = () => new[] { Seg.V("when-counts"), Seg.T(WhenCounts) } },
                new Article { Key = "anticheat",    Title = () => I18n.Tr("Anti-cheat"),            Body = () => Anticheat,
                              Segments = () => new[] { Seg.V("anticheat-pipeline"), Seg.T(Anticheat) } },
                new Article { Key = "stats-tracked",Title = () => I18n.Tr("How stats are tracked"), Body = () => NativeUI.StatsTrackingInfoBody },
            }},
            new Category { Title = () => I18n.Tr("The Mod & Vanilla"), Color = CAT_VANILLA, Articles = new[]
            {
                new Article { Key = "vanilla-safety", Title = () => I18n.Tr("Vanilla stays vanilla"),    Body = () => VanillaSafety },
                new Article { Key = "vanilla-fixes",  Title = () => I18n.Tr("Bug fixes the mod ships"),  Body = () => VanillaFixesP1 + "\n\n" + VanillaFixesP2 },
                new Article { Key = "visibility",     Title = () => I18n.Tr("What unmodded players see"),Body = () => Visibility,
                              Segments = () => new[] { Seg.V("visibility-seats"), Seg.T(Visibility) } },
            }},
            new Category { Title = () => I18n.Tr("Cosmetics & Identity"), Color = CAT_COSM, Articles = new[]
            {
                new Article { Key = "titles",       Title = () => I18n.Tr("Titles"),             Body = () => Titles },
                new Article { Key = "achievements", Title = () => I18n.Tr("Achievement guide"),  Body = () => AchievementsP1 + "\n\n" + AchievementsP2,
                              Segments = () => new[] { Seg.V("achievement-tiers"), Seg.T(AchievementsP1 + "\n\n" + AchievementsP2) } },
                new Article { Key = "cosmetics",    Title = () => I18n.Tr("Shop & cosmetics"),   Body = () => Cosmetics,
                              Segments = () => new[] { Seg.V("cosmetics-flow"), Seg.T(Cosmetics) } },
                new Article { Key = "colors",       Title = () => I18n.Tr("Team & body colors"), Body = () => TeamColors },
            }},
        });

        // ── Bodies ───────────────────────────────────────────────────────
        // GENERATED from the reviewed drafts (session scratchpad wiki/drafts).

        private static string StartHere => I18n.Tr(@"Sid's Competitive Rounds adds a full competitive layer to ROUNDS: ranked 1v1, 2v2 and free-for-all with their own Glicko-2 ratings (plus a 1v2 beta, recorded but unrated for now), an XP and Gold economy with a cosmetic shop, weekly tournaments, live betting on matches, achievements, and Discord integration. All of it is community-built and community-run.

<color=#FFD94D><b>THE TWO GUARANTEES</b></color>

Two rules hold everywhere, and the whole mod is designed around them:

- <color=#7FE87F>A non-modded player always gets pure vanilla gameplay.</color> Whole-room changes (Grow normalization, the FFA engine features) turn themselves off unless every fighter runs a current copy of the mod - one vanilla or outdated client means vanilla rules for everyone, identically - and the poison fix follows the poisoned player, so an unmodded victim keeps vanilla poison.
- <color=#7FE87F>The only things a non-modded opponent can ever see of the mod are nametag styling and the quick-chat phrases you choose to send</color> - quick chat goes out through the game's own chat bubble, like a typed message.

Two nuances, spelled out in <color=#7FD4FF>Vanilla stays vanilla</color>: crash-prevention guards are always on (they repair states vanilla never intended - a dead block, a frozen input - and change no rule), and between players who are ALL modded, current and Ranked-consenting, the poison and Grow fairness fixes apply even in quickplay and room codes.

<color=#FFD94D><b>HOW THIS LIBRARY WORKS</b></color>

The column on the left lists every article, grouped by category. Click a topic and it opens in this pane. Blue names like (see <color=#7FD4FF>Blocking</color>) point at other articles in the same list. <color=#8A8A93>This whole menu is F5. T opens in-game chat, and Esc closes the menu.</color>

<color=#FFD94D><b>WHERE TO GET HELP</b></color>

- <color=#7FD4FF>Discord</color> - the Discord button at the bottom of this menu opens the community server. Real people answer questions there, and so does the server bot - ask it things like 'how does ranked work' or 'how do I get gold' and it answers on its own.
- <color=#7FD4FF>Bug reports</color> - on the Settings tab, find 'Report a bug' and press Open Report Form. You can attach your game logs (a Preview button shows exactly what gets sent), you get up to 10 reports a day, and if your Discord account is linked, responses from the team arrive as DMs.

If something looks wrong mid-match, file the report right after that session - the attached log is usually what makes a bug findable.");

        private static string ControlsIntro => I18n.Tr(@"The mod never rebinds anything - every vanilla control works exactly as it always has, and the competitive keys are added AROUND them. The board below shows every key that does something during competitive play: gold keys belong to the mod, blue keys to the base game, purple to both.");

        private static string ControlsOutro => I18n.Tr(@"<color=#FFD94D><b>THE KEYS IN PRACTICE</b></color>
F5 works everywhere - menu, lobby, mid-game. While the menu is open your inputs stay out of the game: clicks do not fire your gun, Space does not ready you up, and Escape only closes the menu - it will not cancel a match that is connecting. Close it and everything flows again.

Chat has three doors. T types a message, holding Q opens the quick-chat wheel - point at a phrase and release to send it, or pick More... for the full list - and Enter still opens the vanilla box - the mod leaves it alone. M cycles the chat overlay display mode.

Holding E opens the emote wheel - even mid-battle: point at a dance you own and release to play it for everyone running the mod. Your own controls lock until the dance ends, and the dance stops if you get knocked around or fire. Dances are bought in the Shop's DANCES section, where Preview shows the exact moves.

Hold Tab during a match for the live scoreboard: score, cards, accuracy and connection info for everyone in the room, without opening the full menu.

Shift swaps between your equipped map color skins as a new round paints in. If you have none equipped, it does nothing.

Vanilla rebinding lives in the game options; the mod keys themselves are fixed. For what to practice with all of this, read <color=#7FD4FF>Getting better</color>.");

        private static string GettingBetter => I18n.Tr(@"Getting better at competitive ROUNDS is mechanical, not mystical: blocking discipline, netcode awareness, drafting, and reading the numbers the mod already keeps on you. Every tip below is tied to a real mechanic you can go test.

<color=#FFD94D><b>BLOCKING DISCIPLINE</b></color>

Blocking is the skill that decides close games, and it has a cost model worth respecting.

- A block that absorbs nothing still spends its full cooldown. <color=#FF6666>Panic-blocking at the sound of a trigger buys you nothing and hands your opponent a free window while it recharges.</color>
- React to the bullet, not the trigger: watch the opponent's gun and the shot itself, and drill on-reaction blocks until they're reflex.
- One activation can absorb several bullets. A block held for a burst or a bounced volley does far more work than one spent on a lone pellet.
- Block-effect cards multiply timing skill: Echo repeats and Shield Charge dashes all belong to the right-click that started them, so one well-timed block fires the whole chain.
- A poison or burn tick that lands inside your block is consumed - erased, not postponed - so blocking while poisoned is real damage prevention. <color=#8A8A93>(A room mixing current and outdated mod versions can fall back to poison ignoring blocks, for everyone equally - see <color=#7FD4FF>Vanilla stays vanilla</color>.)</color>

<color=#FFD94D><b>PLAY WITH THE NETCODE</b></color>

- ROUNDS is not peer-to-peer. Both players talk to a Photon relay server in the room's region; the orange player is not a host and has no host advantage. <color=#7FE87F>Your ping to the region is the number that matters.</color>
- Every client simulates every bullet, and damage is shooter-authoritative: what a shot takes off you is decided on the shooter's machine. Their screen sees your movement late, which is why you can die a step after reaching cover - and why the player who peeks first sees the other before being seen.
- Your block is the mirror image: it happens on your machine first and reaches the opponent's simulation a beat later. A block raised slightly early on reaction protects you in situations where a frame-perfect one does not, because your last frame is already the past on their screen.
- What reads as a broken hitbox is almost always this mismatch: ping, interpolation, size cards, and bounced shots. The mod never touches hitboxes (see <color=#7FD4FF>Netcode & Photon</color>).
- Frame rate is a hidden gameplay stat in vanilla ROUNDS. Vanilla Grow compounds its damage per frame: around x1.5 for a 60 FPS shooter against x1.07 at 400 FPS for a single copy, and stacking widens the gap fast. In mod rooms - and in private matches where everyone is modded, current, and has Ranked enabled - Grow is normalized so frame rate stops deciding the damage (a heavy stutter can still under-grow a little - the error only ever points down); against vanilla or outdated clients the vanilla rule stands. <color=#7FE87F>A stable frame rate is a real competitive edge</color> - the Settings tab has a performance section for exactly this.

<color=#FFD94D><b>DRAFT FOR A BUILD</b></color>

- Cards are a plan, not a stat sheet. Lifesteal heals off the damage-dealt chain, and damage-over-time ticks route through that same chain - lifesteal plus poison is an engine, not a coincidence. Echo and Shield Charge turn blocking skill into offense. Draft the second card for the first one.
- Read what a card actually does, then test it. Card text and card behavior are separate things: Chase displayed a '+30% Health' line for years that the vanilla card never actually granted (the mod removed the line). Sandbox games are never recorded, so experiment freely there.
- The FFA Same Cards rule is the best draft teacher in the mod: when it's on, everyone's Nth draw offers the same candidates in the same order, so a loss can't be blamed on draw luck - the difference was choices. The Recent FFAs list keeps every pick in pick order (hover a player's card line), so you can replay the winner's draft against yours.
- Your 1v1 match history stores both players' picks in order for every game. After a close loss, re-read the draft before you re-queue.

<color=#FFD94D><b>USE YOUR OWN NUMBERS</b></color>

My Stats tracks more about your play than you probably realize. What the headline stats mean:

- <color=#7FD4FF>Hit %</color> - counts bullets, not clicks: one Buckshot click counts every pellet, and only direct, unblocked hits on enemies count - poison and burn ticks, explosions and self-hits never do. A shotgun build reads low by construction. <color=#FF6666>Compare a build against itself over time, never against a sniper's number.</color>
- <color=#7FD4FF>Block success</color> - one off-cooldown right-click is one attempt, and at most one success per attempt no matter how many bullets it absorbed. Preemptive blocks that meet no bullet are normal, not a mistake - watch the trend across games, not one game.
- Timeline graphs sample every 3 to 5 seconds and always span the whole game. Use them to find where games turn: the score timeline shows when a lead slipped, and the hit and damage lines show what changed when it did.
- A 1v1 game records average and worst ping plus freeze events (frame stalls over half a second); team and FFA games carry lighter connection data. Before blaming your aim for one bad game, check whether the connection numbers already explain it (see <color=#7FD4FF>How stats are tracked</color>).

<color=#FFD94D><b>WATCH BETTER PLAYERS</b></color>

- Live games on the Leaderboard tab carry a WATCH button when they're spectatable. A spectator seat shows the real match from inside the room, and how a top player spends blocks and drafts under pressure teaches faster than queueing blind. FFA lobbies can be watched from the FFA tab the same way.
- The Discord bot answers mechanics questions with live data: ask it 'how does blocking work', or ask how much elo you'd gain against a named player and it computes the real Glicko preview for both sides, win probability included (both accounts need linked Discord).");

        private static string Blocking => I18n.Tr(@"Your shield absorbs for exactly 0.3 seconds per press, the absorb decision is made on the SHOOTER's machine, and a pile of cards ride the block event. This page covers all of it.

<color=#FFD94D><b>WHAT PRESSING BLOCK DOES</b></color>

An off-cooldown block press does three things at once, bullet or no bullet:

- Runs every card effect that rides your block. Shield Charge fires before everything else, then the main chain - Empower charges here, block-heal cards heal here, and block-spawn cards (Frost Slam, Supernova, Teleport) place their effects here.
- Starts the cooldown.
- Arms the absorb window: <color=#7FE87F>your shield absorbs for exactly 0.3 seconds after the press</color>.

Activating and absorbing are separate events. The press always happens; absorption only happens if a bullet reaches you inside the window.

<color=#FFD94D><b>WHAT AN ABSORBED BULLET DOES</b></color>

- It deals no damage, no knockback, no slow, and spawns none of its on-hit effects.
- Its velocity is reversed - it flies straight back the way it came.
- The shooter loses their immunity to it: <color=#7FE87F>a reflected bullet can hit its own shooter</color>.
- Your 'on successful block' card effects fire - unless the bullet you blocked was one of your own.
- A few special bullets are destroyed on block instead of reflected.

The same window negates almost everything else that can touch you: direct damage, knockback, bullet slow, explosion slow and silence, stun, and poison or burn ticks (see <color=#7FD4FF>Poison & damage over time</color>). A crate or saw that hits your shield is bounced away harder than it would be off your body. Even the arena edge respects it: flying off-screen while blocking costs no damage and launches you back in twice as hard (see <color=#7FD4FF>Movement & shield tech</color>).

<color=#FFD94D><b>COOLDOWN</b></color>

- Base cooldown is 4 seconds. Cards modify it by adding to it or multiplying it.
- The timer runs on game time, so slow-motion moments stretch it in real time.
- The recharge is announced: a reload particle and a sound play the moment your shield is ready again.
- <color=#FF6666>Presses during cooldown do nothing at all</color> - no window, no card effects.

<color=#FFD94D><b>ECHO BLOCKS</b></color>

Cards that grant additional blocks turn one press into a burst: the first block schedules the extras in quick succession, and each echo re-runs the full card chain and re-arms the 0.3 second absorb window <color=#7FE87F>without restarting the cooldown</color>. One press buys a longer stretch of near-continuous cover.

Two wrinkles: card effects can ignore specific block types, and Empower is the one that matters - it charges only from a real press, never from echoes or Shield Charge dashes, and the charge is spent on your next fired shot.

<color=#FFD94D><b>I BLOCKED ON TIME AND STILL GOT HIT</b></color>

The absorb decision is not made on your machine. Every bullet is simulated separately on every player's PC, and the copy that counts is the shooter's. When their copy of the bullet reaches you, their game checks their copy of YOUR shield - and that copy only turns on once your press has crossed the network, about half your ping plus half theirs after you pressed. A bullet that reached you on their screen inside that gap is ruled unblocked, the damage is sent as a final number, and nothing on your machine can refuse it. Your shield being visibly up on your screen never enters the decision.

The flip side is symmetric: your bullets are judged on YOUR screen. If your shot connected on your machine, it connects. The full mechanism and the numbers live one article over (see <color=#7FD4FF>Netcode & Photon</color>).

<color=#FFD94D><b>WHAT THE MOD REPAIRS</b></color>

Vanilla ROUNDS has a family of bugs where block dies silently between games: the rematch teardown can destroy card objects half-way, leaving dead 'zombie' hooks attached to your block. The next game your shield animates and starts its cooldown but absorbs nothing - or basic blocking works while a card effect like Shield Charge never fires again.

The mod sweeps those dead hooks out at every game start, on every rematch, and right before every block executes, and one broken card hook no longer cancels the rest of your block. These repairs run everywhere because they only remove provably dead leftovers - restoring the block vanilla meant you to have, never inventing a new rule. <color=#7FE87F>A non-modded player always gets pure vanilla gameplay</color> (see <color=#7FD4FF>Vanilla stays vanilla</color>). The complete repair list lives in <color=#7FD4FF>Bug fixes the mod ships</color>.");

        private static string Poison => I18n.Tr(@"Poison has no damage number of its own. The total a poison bullet deals over time equals that bullet's damage stat at the instant it hit you (Toxic Cloud's longer drip rounds a couple percent above it) - which is why the same green bullet sometimes tickles and sometimes one-shots.

<color=#FFD94D><b>WHAT A POISON HIT DOES</b></color>

- The impact itself deals just <color=#7FD4FF>1 damage</color> - but full knockback. Knockback scales with the bullet's damage stat even when that damage is converted to poison, which is why a big poison shot hurls you across the map while your health bar barely moves.
- Then the poison starts: the bullet's full damage, split into equal ticks spread evenly over the poison's duration. For the <color=#7FD4FF>Poison</color> card that is 10 ticks over 3 seconds - one every 0.3 seconds, 10% of the bullet's damage each, the first landing the instant the bullet connects. <color=#7FD4FF>Toxic Cloud</color>'s poison drips longer and thinner: about 17 ticks across 5 seconds. The cadence runs on game time (slow motion stretches the gaps).
- <color=#FF6666>Every tick is lethal on its own.</color> There is no 'poison cannot finish you' mercy rule.

<color=#FFD94D><b>WHY IT SOMETIMES ONE-SHOTS</b></color>

The total is the bullet's damage AFTER everything that pumped it: damage cards, bullet size, growth in flight (see <color=#7FD4FF>Grow</color>), an Empower charge. A bullet pumped to 500 damage becomes ten 50-damage ticks - 500 total into a 100 HP player, dead before the stream is half done. It is never the poison that one-shots you - it is the bullet underneath it, paid in installments.

<color=#FFD94D><b>BLOCKING TICKS - THE EXACT RULE</b></color>

First, the free win: block the poison BULLET itself and there is no poison at all - an absorbed bullet spawns none of its on-hit effects (see <color=#7FD4FF>Blocking</color>). The rest of this section is about the ticks after a bullet already got through.

Each tick is an ordinary blockable damage event, checked against your 0.3 second block window.

- <color=#7FE87F>A blocked tick is consumed, not delayed.</color> The poison marks that slice as dealt before it checks your shield, so a blocked slice is erased forever. The stream never extends, never pauses, and never comes back for it.
- Blocking does not cancel the stream. The remaining ticks still land on schedule.
- The survival math: every tick is an equal share of the total - 10% for Poison. If a poison's total is exactly enough to kill you, erasing one tick means it can no longer kill you - and each extra blocked tick is another full share you keep.
- The cadence is on your side: ticks arrive every 0.3 seconds and a block window lasts exactly 0.3 seconds, so <color=#7FE87F>one well-timed press erases one or two ticks - 10-20% of a Poison, 6-12% of a Toxic Cloud</color>. That is the entire mechanism behind 'block a tick or two and you survive'.
- Echo blocks re-arm the window without restarting the cooldown, so one press can cover more than one tick.
- <color=#FF6666>The tick sound plays even for blocked ticks.</color> Judge by the health bar, not by the click.

<color=#FFD94D><b>STACKING</b></color>

Every poison hit starts its own independent stream on its own timeline. Nothing merges and nothing refreshes: two poison bullets are two full streams, damage fully additive, each ticking on its own schedule. Getting tagged twice does not reset the first poison - it doubles the drip.

<color=#FFD94D><b>DEATH, REVIVES, DECAY, LIFESTEAL</b></color>

- Dying or being revived at a round transition cancels every running stream instantly. Poison never carries across a round.
- Decay-class cards convert EVERY direct hit the holder takes into a spread-out stream ticking every quarter second. The same rules apply: each tick is blockable, and blocked slices are erased.
- Every unblocked tick feeds the attacker's on-damage effects: a lifesteal build heals off you tick by tick.

<color=#FFD94D><b>THE MOD'S POISON SYNC</b></color>

Vanilla poison is broken online. Each machine runs its own private copy of your poison and checks it against its own copy of your shield; your block press reaches different machines at different times; health is never re-synchronized. The screens silently disagree about your HP ('ghost HP') until the next round - and the disagreement can decide a round, because a death fires from whichever machine's copy crosses zero first.

The mod replaces this with victim authority: <color=#7FE87F>your own client runs the only real tick loop for poison on you</color>, judges every tick against your true shield state, and announces each verdict. Every modded machine - yours included - applies only announced verdicts, so all of them agree on every tick, the totals and cadence follow vanilla's math, and blocking works exactly as written above.

Where it is active: any online room - queue rooms, private room codes, quickplay - whenever the poisoned player runs a current mod build. Mixed rooms fall back safely:

- In a mod queue room that contains a non-modded or outdated player, modded clients agree that poison ticks ignore blocking - consistency beats the ghost-HP split, but blocking will not reduce poison there.
- In a private room-code game with a non-modded player, a modded victim's blocks still count; a non-modded victim gets raw vanilla behavior, desync included.
- Offline and sandbox are pure vanilla - a single simulation has nothing to desync.");

        private static string Grow => I18n.Tr(@"Grow is the one card whose damage depends on the shooter's FRAME RATE. In vanilla, the same Grow bullet fired by a 60 FPS player hits far harder than one fired at 400 FPS - and the mod normalizes it in competitive play.

<color=#FFD94D><b>THE REAL MATH</b></color>

Grow multiplies the bullet's damage a little every rendered frame while it flies, through roughly the first 30 units of travel. Compounding a per-frame multiplier has a strange consequence: the bullet's speed cancels out of the total, and what actually sets the final multiplier is the length of the shooter's frames. Fewer, longer frames compound harder.

Un-stacked, over a full flight:

- 400 FPS shooter: about <color=#7FD4FF>x1.07</color>
- 60 FPS shooter: about <color=#7FD4FF>x1.53</color>
- 30 FPS shooter: about <color=#7FD4FF>x2.31</color>

Stacking multiplies the growth rate, so the gap explodes. At four stacks: about x1.29 at 400 FPS, <color=#FF6666>x5.47 at 60 FPS, and x28.5 at 30 FPS</color>.

Hitches are the worst case: <color=#FF6666>a single 200 ms freeze frame multiplies the bullet by about x2.16 on its own</color>. One stutter mid-flight can turn a normal shot into a one-shot.

<color=#FFD94D><b>WHY THEIR FPS BECOMES YOUR PROBLEM</b></color>

Damage in ROUNDS is shooter-authoritative: the shooter's machine computes what the victim takes, and everyone else applies that number (see <color=#7FD4FF>Netcode & Photon</color>). Grow's growth happens on the shooter's frames, so a low-FPS or stuttering opponent's Grow bullets genuinely hit harder. It is not lag, it is not your imagination, and in vanilla it is not cheating either - it is the card's math.

<color=#FFD94D><b>THE MOD'S NORMALIZATION</b></color>

In eligible rooms, the mod pins Grow's growth clock: <color=#7FE87F>every Grow bullet grows as if its shooter ran at 240 FPS, on every machine</color>. Against a very-high-FPS baseline that means about +11 percent over a full flight un-stacked, +23 percent at two stacks, +53 percent at four - the same for everybody, every game. The reference rate is compiled into the mod on purpose: if it were a setting, changing it would change your own damage.

Where it applies:

- Every fighter in the room must run a current mod build (spectators don't count). <color=#FF6666>One vanilla or outdated fighter means vanilla growth for the whole room</color>, the same on every screen - a mixed lobby is never half-normalized.
- Mod queue rooms (ranked 1v1, 2v2, 1v2, FFA, tournament rooms) normalize whenever everyone is current.
- Private room-code and quickplay games normalize only when, on top of that, every fighter had the Ranked toggle ON when they connected.
- The decision is locked per bullet at launch and never flips mid-flight. It is never active offline.

One honest residual: at very low frame rates a normalized bullet can grow slightly LESS than the target (a few percent stacked; more on a heavy hitch). The error always points down - never toward the one-shot.");

        // ── Damage types & buffs (Spirit) ────────────────────────────────
        // ATTRIBUTED community research: reproduced from Spirit's PDF 'On
        // Damage Types and Buff Activation' (Aug 23, via Sid). The claims are
        // HIS sandbox findings, kept faithful to the source document rather
        // than re-verified against the decompile - the byline in part 1 makes
        // the authorship explicit. Tables use <pos=NN%> columns (the body
        // font is proportional, so space-alignment cannot work); comparison
        // signs are written as words because a bare '<' can open a TMP tag.
        private static string DamageBuffsP1 => I18n.Tr(@"<color=#8A8A93>Research and write-up by Spirit - 'On Damage Types and Buff Activation', University of Rounds. Reproduced for this library with light reformatting; the testing, the findings and the voice are all his.</color>

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

Promising potential damage dealers, such as Chilling Presence, were excluded due to both their failure to trigger any cards or buffs and their failure to deal any damage. Every entry on the list deals damage in some form, and every unique way to deal damage has an entry. Thus, there are no methods to trigger any damage-dealing cards or buffs without dealing some amount of damage. That might seem obvious but, given the weirdness of the rest of the system, one can never be too sure.");

        private static string DamageBuffsP2 => I18n.Tr(@"<color=#FFD94D><b>SELF VS OPPONENT DAMAGE</b></color>

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

Sadly, this is not the end of the document, because the ROUNDS developers saw fit to introduce another mechanic. I do hope you, dear reader, appreciate the relative ease with which you get to possess this information as compared to the hours of madness I spent obtaining it.");

        private static string DamageBuffsP3 => I18n.Tr(@"<color=#FFD94D><b>THE 0.35 SECOND WINDOW</b></color>

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

<color=#8A8A93>Related reading: <color=#7FD4FF>Blocking</color> covers what a block actually does and which cards ride it; <color=#7FD4FF>Poison & damage over time</color> covers how tick damage lands and syncs.</color>");

        private static string MovementTech => I18n.Tr(@"Verified movement tech: the shield edge bounce, wall jumps, and the flying bounce. Every rule on this page comes straight from the game's code.

<color=#FFD94D><b>THE SHIELD EDGE BOUNCE</b></color>

The arena has a hard kill boundary just off-screen. While you are past it, the game checks you every 0.1 seconds:

- <color=#FF6666>Not blocking:</color> you take a 51-damage lethal hit and an impulse back toward the arena. At 100 HP, two unshielded edge hits kill you.
- <color=#7FE87F>Blocking:</color> no damage at all, and the return impulse is twice as strong. Your old velocity is zeroed first, so the bounce is clean and predictable no matter how fast you were flying out.

The block window is 0.3 seconds and the edge check ticks every 0.1 seconds, so the press can slightly TRAIL your exit and still count. Getting launched off-screen is survivable on demand: block as you cross the edge and you come back harder, for free. In a knockback war this is the difference between a lost point and a return volley.

<color=#FFD94D><b>WALL JUMPS AND JUMP REFRESH</b></color>

- Touching a wall in the air while holding movement INTO it counts as a wall grab. Unless you jumped within the last 0.15 seconds, <color=#7FE87F>a wall touch refreshes ALL of your jumps</color>.
- Pressing jump within 0.1 seconds of a wall touch performs a wall jump: up and away from the wall instead of straight up.
- Ground jumps add extra horizontal push proportional to how fast you were already moving sideways; wall jumps skip that bonus.
- Holding jump keeps adding upward force for a short moment after takeoff - tap for a short hop, hold for full height.
- While hanging close to a wall, your time-in-air counts more slowly for game systems that care about air time.

<color=#FFD94D><b>THE FLYING BOUNCE</b></color>

A hit big enough to set you 'flying' changes how walls treat you: while flying, hitting map geometry reflects your velocity off the surface, stuns you for 0.2 seconds, and deals a 5-damage self-hit. The reflected launch comes out after a quarter-second hold.

That self-hit is an ordinary blockable hit: <color=#7FE87F>blocking at the moment of wall impact negates the 5 damage</color>.

<color=#FFD94D><b>MYTHS THE CODE SAYS NO TO</b></color>

- <color=#8A8A93>Wall sliding is real, but not where you'd think: pressing into a wall damps your speed a little and keeps resetting the gravity ramp, so you do fall slower - while the stat actually named 'wall grab drag' does nothing at all.</color>
- <color=#8A8A93>Cards that advertise a self-push on block do nothing on a normal block press - the game's own block window suppresses the push before it can apply. Do not draft them for movement.</color>

<color=#FFD94D><b>SHIELD CHARGE IS THE REAL BLOCK MOVEMENT</b></color>

Shield Charge launches you along your AIM direction on any block press, and the launch works during your own block window. Hitting a player cancels the launch, damages and knocks them back, and grants a bonus block. It also combos with the wall rules above: charge into a wall, get your jumps refreshed, wall-jump out.");

        private static string Netcode => I18n.Tr(@"Nobody in a ROUNDS match is the host. Every game runs through Photon's cloud servers, every player simulates the fight locally, and each shooter is the referee of their own bullets. This page is how all of that fits together.

<color=#FFD94D><b>HOW A CONNECTION HAPPENS</b></color>

- Your client first talks to a Photon name server, pings the 15 regions (us, eu, asia, au and the rest), and picks the best one. The result is cached between launches.
- It then connects to that region's master server, which handles matchmaking. Joining or creating a room hands you off to a game server in that region, and the room lives THERE: all traffic is you, up to Photon, down to the other players. There is never a direct link between players' PCs.
- Quickplay only matches players in your current region. If you sit alone in a search for 15 seconds, the game hops regions on its own, trading a little ping for a bigger player pool.

<color=#FFD94D><b>ROOM CODES AND CROSS-REGION PLAY</b></color>

A private room code is 6 letters: the FIRST letter encodes the host's region, the other 5 are random. Joining by code reads that letter and moves you to the host's region before searching, which is why friends on different continents can always join each other. Steam invites carry the region the same way. Mod queue rooms skip all of this: the server names the room and picks ONE region for everyone it matched, so a queued pair can never split across regions.

<color=#FFD94D><b>THE MASTER CLIENT</b></color>

One player in every room is the master client - initially whoever created the room (in 1v1, the orange player). The master is not a host; their machine just gets the tie-breaking jobs:

- rolls the next map and announces it,
- announces every point and round result - every client applies the master's score verbatim, so the scoreboard cannot disagree between screens,
- owns and physically simulates the crates, saws and moving platforms; everyone else receives their positions as a stream, and your pushes on a crate are sent to the master as requests.

If the master leaves, Photon appoints a new one - though in vanilla 1v1 that hardly matters, because any player leaving ends the match for everyone.

<color=#FFD94D><b>WHAT TRAVELS THE WIRE, WHAT STAYS LOCAL</b></color>

- <color=#7FD4FF>Player movement</color> - streamed. Your machine sends your position, inputs and velocity up to 30 times a second, and the other players' copies of you replay that stream. A remote copy of a player never reads input.
- <color=#7FD4FF>Blocks</color> - instant on your own screen, relayed to everyone else as an event. Their copy of your shield turns on when the event arrives.
- <color=#7FD4FF>Bullets</color> - spawned once, then simulated separately on every machine, frame by frame, with no mid-flight correction (a few guided cards excepted). The bullet on your screen and the same bullet on theirs are two slowly diverging copies.
- <color=#7FD4FF>Damage</color> - computed once, on the shooter's machine, and sent as a final number. Health is never re-synchronized; screens agree only because everyone applies the same damage events. <color=#8A8A93>(The one exception is the mod's poison sync, where the VICTIM's client judges the ticks - see <color=#7FD4FF>Poison & damage over time</color>.)</color>

<color=#FFD94D><b>DAMAGE AUTHORITY</b></color>

Only a bullet's owner can declare a hit. When the shooter's copy of their bullet touches you, their machine checks its copy of your shield and your position, rules blocked or not, and broadcasts the result. Your machine applies it without a vote.

Everything defensive you do therefore counts only once it has ARRIVED on the shooter's screen. Press block, and it protects you there about half your ping plus half theirs later than it protected you at home. This one rule explains the classics: 'I blocked on time and still got hit' - your press had not reached them yet (see <color=#7FD4FF>Blocking</color>); and 'I got hit around the corner' - on their screen you were not behind the corner yet, because their copy of your position runs late by the same delay plus up to one 33 ms movement tick. The consolation is symmetry: your bullets are ruled on YOUR screen.

<color=#FFD94D><b>WHAT PING ACTUALLY MEASURES</b></color>

The ping number (the mod shows it in the corner overlay, next to your region) is the round trip between YOU and the Photon server - not between you and your opponent. The delay you feel against another player is roughly half your ping plus half theirs, plus up to one 33 ms movement tick. Two players at 40 ms each play a tighter game than a 20 ms player against a 150 ms player, even though that 20 looks beautiful.

<color=#FFD94D><b>WHAT FRAME RATE CHANGES</b></color>

- Bullets integrate their movement once per rendered frame, so different frame rates produce slightly different trajectories for the SAME bullet on different machines - a small but structural divergence.
- Player movement runs on a fixed physics step and is far less frame-rate sensitive.
- The extreme case is the Grow card, whose damage compounds per frame on the shooter's machine (see <color=#7FD4FF>Grow</color>).
- Below about 30 FPS your machine drains the incoming movement stream slower than it arrives, so enemy copies get visibly choppier.
- <color=#8A8A93>A game can feel awful while both FPS and ping graphs read flat - stutter in the replicated stream is invisible to both numbers.</color>");

        private static string VanillaBugs => I18n.Tr(@"ROUNDS ships with real bugs - some cosmetic, some that decide rounds. The catalogue: symptom, real cause, and whether the mod repairs it. Repair details: (see <color=#7FD4FF>Bug fixes the mod ships</color>).

<color=#FFD94D><b>INPUT AND LOBBY BUGS</b></color>

<color=#7FD4FF>Escape key permanently dead, or inputs frozen as a match is found</color> - the game toggles input across all players with no null checks; one half-spawned player crashes the loop. <color=#7FE87F>Fixed by the mod, always on.</color>

<color=#7FD4FF>'No space to ready up' - you cannot spawn into a lobby</color> - the game tries to spawn your character before you are actually in a room, crashes, and never recovers. <color=#7FE87F>Fixed by the mod, always on</color>; 30 seconds stuck returns you to the menu.

<color=#7FD4FF>Typing confirms a card pick, Enter opens the room-code box, Space readies you up mid-sentence</color> - three places read the raw keyboard without checking for an open text box. <color=#7FE87F>Fixed for the mod's own chat</color>; the vanilla chat box keeps its quirks.

<color=#FFD94D><b>COMBAT BUGS</b></color>

<color=#7FD4FF>After a rematch, your block goes on cooldown but absorbs nothing - or Shield Charge stops firing while basic block works</color> - the between-games teardown can destroy card objects half-way, stranding dead hooks on your block. <color=#7FE87F>Fixed by the mod everywhere</color> (see <color=#7FD4FF>Blocking</color>).

<color=#7FD4FF>Poison health bars disagree between screens, and blocking poison is a coin flip</color> - every machine ticks its own copy of the poison against its own copy of your shield; health is never re-synced. <color=#7FE87F>Replaced by the mod's victim-authoritative poison</color> when the victim runs the mod (see <color=#7FD4FF>Poison & damage over time</color>).

<color=#7FD4FF>A poison tick kills someone during the round-won animation, awarding a phantom round</color> - damage-over-time keeps landing after the round is decided. <color=#7FE87F>Fixed on every modded client, in any room</color> - full protection just needs the room's (usually modded) host seat patched too.

<color=#7FD4FF>A leftover bullet from the previous point hits you just after everyone respawns</color> - nothing in vanilla despawns mid-air bullets at the point boundary. <color=#7FE87F>Fixed: modded clients clear their own leftover bullets.</color>

<color=#7FD4FF>Shots visibly connect but do no damage on your screen, or a point-blank drill bullet turns invisible</color> - the bullet's special components can register in the wrong order on the receiving machine. <color=#7FE87F>Fixed by the mod in any room.</color>

<color=#7FD4FF>Grow one-shots you out of nowhere</color> - broken math more than a bug: Grow's damage compounds per frame on the shooter's machine, so low frame rates and hitches multiply it massively. <color=#7FE87F>Normalized by the mod in competitive play</color> (see <color=#7FD4FF>Grow</color>).

<color=#7FD4FF>After one game with Demonic Pact, hold-to-fire guns like Spray stop auto-firing all session</color> - the no-auto-fire flag is copied one way and never reset between games. <color=#7FE87F>Fixed by the mod in any game.</color>

<color=#7FD4FF>Radiance visibly sweeps through a crowd and hits one person</color> - the wave only ever checks the single closest target and stops after one hit. <color=#FF6666>Fixed in FFA only</color> - there it hits everyone it sweeps; other modes keep vanilla.

<color=#7FD4FF>Chase's card text lists a Health bonus</color> - dead data the game never applies; the card has never granted it. <color=#7FE87F>The mod fixes the label.</color>

<color=#7FD4FF>Being offered a card you already own</color> - not a bug; the second copy levels up the first.

<color=#FFD94D><b>MODE AND VISUAL BUGS</b></color>

<color=#7FD4FF>In 2v2 or 1v2, a card picker stands on an empty stage, or the wrong body is shown picking</color> - vanilla only ever presents one picker per round, using a team number as a player number. <color=#7FE87F>Fixed in 2v2 and 1v2 mod rooms.</color>

<color=#7FD4FF>Phoenix revives someone into thin air - invisible, unhittable, stuck</color> - the revive finds the player by list position, wrong once the list has changed (an FFA leaver), and the death flag is never set. <color=#7FE87F>Fixed by the mod everywhere.</color>

<color=#7FD4FF>Another player's name shows as the literal placeholder PlayerName</color> - a failed Steam name lookup is never retried. <color=#7FE87F>Fixed: the mod retries the lookup (up to 15 tries over half a minute) and repaints the name when it lands.</color>

<color=#7FD4FF>A saw's spinning loop plays forever, or audio goes muffled for the session</color> - looping sounds outlive their owner and starve the sound engine of voices. <color=#7FE87F>Fixed: leaked loops are swept after every round.</color>

<color=#7FD4FF>Harmless error spam in the log during map transitions</color> - the map-move animation holds references to pieces replaced mid-move. <color=#8A8A93>Not fixed - benign noise. (Anything that must touch the map mid-move, like the mod's own map skins, defers around that window instead.)</color>

<color=#FFD94D><b>WHERE THE FIXES RUN</b></color>

Crash guards and dead-state repairs run everywhere - they repair states vanilla never intended, without changing any rule. Rule changes are gated: mode logic needs its own mod-issued room, Grow normalization needs every fighter modded and consenting, and poison authority follows the poisoned player - an unmodded victim keeps vanilla poison. <color=#7FE87F>A non-modded player always gets pure vanilla gameplay</color> - and the only things they can ever see of the mod are nametag styling and quick-chat phrases you deliberately send through the game's own chat (see <color=#7FD4FF>Vanilla stays vanilla</color>).");

        private static string Ranked1v1 => I18n.Tr(@"Ranked 1v1 is the mod's core mode: best-of-3 series, one Glicko rating, and two ways to start a rated series - the queue, or a private room where both players run the mod. This page covers the queue from Search to room, how a private lobby becomes rated, and exactly what a disconnect does.

<color=#FFD94D><b>FINDING AN OPPONENT</b></color>

- Clicking Search is itself the ranked opt-in - joining the queue turns Ranked on for your account.
- Your search band starts at 100 rating in either direction and widens as you wait: 200 after 30 seconds, 400 after 60, 800 after 120. It never widens past 800.
- The overlap is <color=#7FD4FF>two-sided</color>: you must be inside your opponent's band AND they must be inside yours. A 2-minute waiter with a wide band can't grab a fresh joiner whose narrow band excludes them.
- Among valid candidates, the closest rating wins.
- Players you declined in the last 5 minutes, players you've blocked (in either direction) and banned accounts are never offered.
- Searching while playing casual is fine - vanilla quickplay and ordinary casual rooms never cancel your search. Joining any mod-issued room (a tournament, 2v2, 1v2 or FFA) does, immediately.
- After 30 minutes of searching you're removed from the queue. <color=#8A8A93>Rejoin if you're still there - the 1v1 client never rejoins for you.</color>

<color=#FFD94D><b>READY-UP, DECLINE AND THE ROOM</b></color>

- On a match you get a MATCH FOUND banner with your opponent's name and rating, a sound, and a taskbar flash. You must click Ready - there is no auto-ready.
- You have 90 seconds, and when either player clicks Ready the window resets to a fresh 90 for both - a slow alt-tabber always gets full time. If it runs out, both of you go back to searching.
- Decline puts both of you back in the queue and blocks the two of you from re-pairing for 5 minutes. Once the room has been issued, decline no longer works.
- When both are ready the server issues a private ranked room and picks the Photon region: if both clients report the same home region, that wins; otherwise it falls back through the players' live regions, then either home region, then US.
- Your client pins that region before joining, so both of you land in one room instead of two same-named rooms on two continents.
- If your opponent never arrives: a warning at 25 seconds, then an automatic return to the menu at 60. <color=#7FE87F>No penalty for either side.</color>

<color=#FFD94D><b>RANKED IN A PRIVATE ROOM</b></color>

- A room-code game is rated when three things are true: your Ranked toggle is on, your opponent has Ranked enabled, and your opponent runs the mod. An opponent who has never run the mod can never make a game rated. (One deliberate exception: a live unfinished series from an earlier sitting keeps its ranked status when you meet again.)
- The moment both mods see each other, the client registers the series with the server (the <color=#7FD4FF>preflight</color>) - so the series exists, and is bettable, during game 1.
- If either player has Ranked disabled, the server refuses the series and you get one toast: the match plays out as casual. Casual games are still recorded - they just never touch rating.
- Queue and tournament rooms skip these checks entirely: queueing was the consent.

<color=#FFD94D><b>THE SERIES</b></color>

- First to 2 game wins takes the series. <color=#7FE87F>Rating moves only when a series completes</color> - the whole series is one rating outcome, and individual games never move rating on their own.
- An undecided series - at least one game played, nobody at 2 wins - <color=#7FE87F>never expires</color>. Play the same opponent tomorrow or next week and game 1 still stands; your HUD picks up the standing score instead of restarting at 0-0.
- That no-expiry rule is deliberate: an expiry window let a player down 0-1 abandon the series and wait out the clock to dodge the loss.
- A non-tournament series where no game was ever finished is abandoned after 30 minutes; the next meeting starts fresh. Tournament series wait for their bracket instead.
- Bets on a series stalled for 60 minutes are refunded (tournament series excepted) - the series itself stays resumable.
- During round 1 of each game, the client reports live points to the server. Betting locks once 2 total points have been scored in game 1 (a 1-1 counts) - or the moment any game of the series is decided.

<color=#FFD94D><b>DISCONNECTS</b></color>

What a DC does depends on the score, and it is judged by the player who STAYED:

- You were at match point (4 rounds) when your opponent dropped: you win the game at the standing score.
- 4-4: you take the game, recorded as 5-4.
- Anywhere else - including an opponent who drops while AHEAD - the game is canceled. Nobody gets a win, nobody gets a loss.
- Leaving a game to join your own queued ranked match is announced in advance and never counted against you.

The anti-abuse rules:

- Only the player who stayed in the room and watched the other leave can claim a DC win. <color=#7FE87F>A leaver's own client can never award itself anything.</color>
- If the opponent reconnects before you leave, the claim is dropped.
- If BOTH players drop, nobody stayed to observe: no win, no leave mark. With a completed game on the board the series stays active and resumes whenever you next meet.
- <color=#FF6666>A canceled game doesn't wipe the series</color> - completed games stand, and the series resumes as above.

<color=#FFD94D><b>LEAVE PERCENT</b></color>

- A ranked DC with meaningful play behind it (2 or more points, or a completed round, in the CURRENT game), with neither side at match point, is recorded as a leave against the leaver - at most one per player per series.
- <color=#7FD4FF>Leave %</color> = ranked DCs divided by ranked series wins + losses + DCs. Under 5 percent shows green, 5 to under 15 amber, 15 and up red - visible to everyone on the leaderboard.
- A DC at match point becomes a DC win for the other player instead, not a leave mark.

For the full is-this-recorded decision tree, see <color=#7FD4FF>When a game counts</color>.");

        private static string Mode2v2Ext => I18n.Tr(@"<color=#FFD94D><b>HOW THE BALANCER RATES YOU</b></color>

- The balancer uses your 2v2 rating once it is trustworthy: 10 or more completed series, or earlier once the rating has settled (its uncertainty has dropped enough). Until then, your 1v1 rating stands in.
- Ratings are snapshotted when you join the queue - the balancer works from those values.
- The server tries all three ways to split the four of you into pairs and keeps the split with the smallest difference in total team rating.

<color=#FFD94D><b>THE MID-SERIES SWAP, PRECISELY</b></color>

- It only fires in auto-balanced series - manual lobbies never swap.
- The design: after a game with a point margin of 3 or more, the weakest winner trades places with the strongest loser for the next game, under the same 2v2-if-trusted, else-1v1 rating rule as above.
- <color=#FF6666>Not live yet:</color> the in-game team switch is still shipping, so for now the balancer only logs the swap it would have made and teams stay locked for the whole series.

<color=#FFD94D><b>WHO IS ORANGE, WHO IS BLUE</b></color>

- Team 1 is the in-game orange team; Team 2 is blue. Within a team, the lower Steam ID takes the first slot.
- In a manual lobby you can claim Team 1 or Team 2 before the lock. The auto queue always runs the balancer and ignores preferences.
- A team can also carry a member's equipped body color as its display identity, decided once when the series is created: a sole color holder names the team, two holders is a coin flip, none means vanilla. In a mirror match, Team 2 falls back to its other member's color. <color=#8A8A93>Display only - nobody's actual body color is changed.</color>

<color=#FFD94D><b>DISCONNECTS</b></color>

- <color=#FF6666>Lead forfeit:</color> if the other team DCs out of a game that had 2 or more total points while YOUR team is already up a series game, the whole series completes to you on the spot, with full rating and gold. You can't leave a 2v2 to dodge a loss once you're down a game.
- Any other DC carries NO automatic penalty: the series is set aside for manual admin resolution, and every game already reported stands.
- <color=#7FE87F>Sticky resume:</color> if the same four players re-queue within about 30 minutes, the matcher relocks you onto that series - original teams, score kept.

<color=#FFD94D><b>REWARDS, PER SLOT</b></color>

- XP and gold accrue per player slot inside the series, so the panel shows each player's own +g and +xp, and the lifetime Gold/XP columns count 2v2 play only.
- The tier multiplier uses the AVERAGE of the two opposing players' 2v2 ratings; a player with no 2v2 rating yet counts as 1500 - and 1500 already sits in the x1.5 Intermediate tier, so a fresh lobby pays above base.");

        private static string Mode1v2Ext => I18n.Tr(@"<color=#FFD94D><b>WHO GETS THE SOLO SEAT</b></color>

- You can queue with a preferred side. The lock takes the three longest-waiting live queuers; the solo seat goes to the earliest joiner who asked for solo, or to the earliest joiner outright if nobody did. The other two are the duo.
- The room's Photon region is the first region anyone in the queue actually reported, in queue order, with US as the fallback.

<color=#FFD94D><b>SPAWN SIDES</b></color>

- Every vanilla map ships exactly four spawn points, two per half. In 1v2 the solo takes the outer-left point and the duo gets the whole right half - a duo player never spawns on the solo's side.

<color=#FFD94D><b>SOLO EXTRA PICK, PRECISELY</b></color>

- In the random queue, any one player queueing with it enabled turns it on for the series; in a hosted lobby the host's setting decides.
- The extra draw applies to the OPENING pick only: the solo picks two cards before round 1, then one per pick after that, same as everyone.

<color=#FFD94D><b>PAY MULTIPLIERS</b></color>

The base XP and gold numbers above are multiplied by a difficulty multiplier:

- The solo seat always earns x1.5.
- A solo playing WITHOUT the extra pick earns a further x1.2; a duo facing an extra-pick solo earns x1.1.
- Your opponents' 1v1 rating tier multiplies too (up to x3.0), and facing a 1v2 podium player adds x1.35, win or lose.
- The difficulty product caps at x4.0, with the x1.5 win bonus applied on top of it. Series gold is scaled by the opponent tier only.

<color=#FFD94D><b>DISCONNECTS</b></color>

- While 1v2 is an unranked beta it has no DC pipeline: outcomes come from recorded games only, and no leave counter exists for 1v2.
- Leaving while locked with zero games played dissolves the lock - the series is canceled, queue survivors go back to searching, and a hosted lobby's survivors are simply released.
- A leave mid-game leaves the outcome to the normal match report.
- If a locked room never fills: a warning at 35 seconds, then an automatic return to the menu at 90. <color=#7FE87F>No penalty.</color>");

        private static string ModeFfaExt => I18n.Tr(@"<color=#FFD94D><b>HOW A PICK ACTUALLY LANDS</b></color>

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
- <color=#7FE87F>Early-leave grace:</color> leave a game before the field has scored 2 half points, while your own tally (points, half points, kills) is still zero, and that game is unrated for you - no rating change, no pay. Any later or scored leave counts in full: leaving early doesn't dodge the loss.
- Players who left in an EARLIER game ride along as absent ghosts - on the roster, excluded from rating and pay.
- A game that drops under 3 players before 2 half points were scored is cancelled; dropping under 3 after a game over ends the sitting.");

        private static string Spectating => I18n.Tr(@"Live competitive games in every mode can be watched from inside the mod - ranked 1v1, 2v2, 1v2 and FFA (ordinary casual 1v1 rooms aren't listed). You see the real game, live, from a seat that is built so it cannot touch the match.

<color=#FFD94D><b>HOW TO WATCH</b></color>

- <color=#7FD4FF>WATCH</color> buttons appear on live-game rows across the F5 menu: the Leaderboard's live series strip, the FFA tab's live lobbies, the 1v2 tab's live panel and the Home tab's live rows. You never see WATCH on your own game.
- Clicking one puts you into the real Photon room as a non-playing seat. You can't start spectating while you're in an online room or mid-queue.
- A game is joinable while its fighters are in live combat, a spectator seat is free, and every fighter allows spectators.

<color=#FFD94D><b>WHAT YOU SEE</b></color>

- The true live game - real movement and real projectiles, not a replay or a delayed feed.
- The screen stays black until the first clean round boundary, then the game appears in sync. If your client ever has to catch up mid-round, you see the live scene with a Syncing note instead of black.
- Card picks are visible, and every round boundary carries everyone's full decks. In FFA you see pick results and decks, not each picker's private hand of candidates.
- A minimal top bar shows the score and the fighters' names, titles and ratings. Hold Tab for the stats board. Chat works (and can be muted). Esc opens the leave menu.

<color=#FFD94D><b>WHY A SPECTATOR CAN'T TOUCH THE GAME</b></color>

The spectator seat is an observer by construction, not by politeness:

- <color=#7FE87F>It cannot deal damage or cause a death.</color> A seat-wide clamp makes the death branch unreachable from every damage path on that seat - the deaths you see happen on the fighters' clients and only render on yours.
- It cannot spawn a player, ready up, or take a slot - even the press-jump-to-join prompt is suppressed.
- It never answers or sends the sync-up requests fighters use to stay in lockstep, and never reports map loads, so it can't slow or desync the match.
- It cannot pick cards and runs none of the game lifecycle - it only applies the scores the master broadcasts.
- It is invisible to every fighter count: quorum checks, reporter election and match-start counts all exclude spectators.
- <color=#7FE87F>A spectator leaving never ends the fighters' match.</color>

<color=#FFD94D><b>PRIVACY, COUNTS AND LIMITS</b></color>

- Fighters always know: every seat in the room - fighters and spectators alike - sees a bottom-right Spectators line with names while anyone is watching, and the games list shows spectator counts publicly.
- <color=#7FD4FF>Allow Spectators</color> is a per-player toggle in F5 Settings, on by default. If any one fighter in a game has it off, that game can't be watched - and the reason shown is generic, never who opted out. Flipping it off mid-match removes seated spectators within moments.
- The one exception: sync tournament matches are always spectatable.
- Public spectator seats cap at 4 per game, and one extra seat is reserved for the official broadcast account that runs the community stream, so public spectators can never crowd it out. A full game answers 'spectator full'.

<color=#FFD94D><b>LEAVING, AND BEING RETURNED</b></color>

- Esc, then leave. Leaving never disturbs the match - your name just drops off the Spectators line.
- Your seat is a lease your client refreshes every few seconds. When the game ends or a fighter opts out, the lease ends and you're returned to the menu automatically. <color=#7FE87F>A network hiccup never kicks you</color> - only a definitive answer from the server does.

<color=#FFD94D><b>SPECTATING AND BETTING</b></color>

- Spectators can bet. The early bet-close windows are the information gate: 1v1 and 2v2 bets lock once 2 points are scored in game 1, and FFA bets lock once 2 half points are scored in the game being bet on (earlier in short lobbies) - so a lingering seat learns nothing useful before the window shuts.
- The only barred group is a lobby's own members: you can never bet on your own lobby.");

        private static string TournHow => I18n.Tr(@"Tournaments are 8-16 player double-elimination brackets of best-of-3 series, run end to end by the mod and the bot. There are two kinds: <color=#7FD4FF>Sync</color> (the whole bracket plays out in one sitting) and <color=#7FD4FF>Async</color> (each match has a week to happen). Both are ranked - every game moves your normal 1v1 rating.

<color=#FFD94D><b>THE TWO KINDS</b></color>

<color=#7FD4FF>Sync</color> - weekly. The default start is Saturday at noon Pacific time, but the field votes on the real time: signing up includes marking which start times you can make, from 8 slots at 6-hour steps around the default. The tournament locks 48 hours before the DEFAULT start - the voted time can sit up to a day to either side of it.

<color=#7FD4FF>Async</color> - a new one opens 2 days after the previous one finishes. Signups run for 7 days, then it locks and starts immediately. Every match has a 7-day deadline (check-ins can add a day), so a full bracket takes roughly 6-9 weeks depending on how fast people play.

<color=#FFD94D><b>SIGNING UP</b></color>

- Sign up on the F5 Tournaments tab. A linked Discord account is required - the bot runs everything by DM (see <color=#7FD4FF>The bot & check-ins</color>).

- Sync signups must mark at least one start time. Signing up again replaces your time votes.

- You can un-sign during voting or after lock, but <color=#FF6666>not once the tournament is running</color> - from there, not showing up is a forfeit and counts on your no-show %.

- The field caps at 16. Signups past the cap become <color=#7FD4FF>speculative</color>: they don't play, but they are the backfill pool - if a confirmed player leaves before the start, the most reliable speculative inherits their seat. Ordering into the 16 (and out of the pool) goes by no-show % first, then signup time.

- Your <color=#7FD4FF>no-show %</color> is a rolling 90-day measure of tournaments you signed up for and then missed. Old misses fade out over the 90 days.

<color=#FFD94D><b>HOW THE LOCK WORKS</b></color>

- Sync locks 48 hours before the default start. It needs at least 8 confirmed players AND one time slot at least 8 signups (speculatives included) can make; otherwise the whole tournament pushes back one week and your votes carry forward.

- The winning slot becomes the start time. <color=#FF6666>If you didn't mark the winning slot, your signup is removed</color> - no penalty, and the bot DMs you why. Speculatives promote into the freed seats.

- Sync can also start early: once at least 8 players are in, every confirmed player pressing <color=#7FD4FF>Force Start</color> on the tab within 10 minutes of each other starts the tournament 10 minutes later.

- Async has no time vote - after the 7-day signup window it locks on player count alone and starts right away.

- Locking snapshots the prize pool at the confirmed player count and clears any ranked blocks between participants - signing up opts you in to playing whoever else signed up.

<color=#FFD94D><b>SEEDING AND THE BRACKET</b></color>

- Your seed is your 1v1 rating snapshotted at lock; the highest rating is seed 1. Pairing is standard bracket placement, with seeds 1 and 2 starting in opposite halves. Seed numbers stay hidden until the tournament starts, so nobody can work out their round-1 opponent in advance.

- With 9 to 15 players the bracket is built for 16 and the top seeds get round-1 byes to fill the gap.

- Double elimination in plain terms: lose a winners-bracket match and you drop into the losers bracket; lose there and you're out. The losers-bracket champion meets the winners-bracket champion in the grand final - and if the losers-bracket champion wins it, one extra deciding match is played, because the winners-bracket champion hadn't lost a series yet.

- Every match is a best-of-3, played as a normal ranked series.

<color=#FFD94D><b>SYNC PLAY DAY</b></color>

The whole contract is: <color=#7FE87F>have ROUNDS open at the start time - sitting at the main menu is fine.</color> The mod does everything else.

- While ROUNDS runs, the mod pings the server every 20 seconds; you count as present while your last ping is under 2 minutes old. The F5 menu never needs to be open.

- From 15 minutes out you get a reminder DM and an in-game countdown banner; every match-ready moment gets its own DM too (see <color=#7FD4FF>The bot & check-ins</color>).

- When your match is ready and both players are present, the mod connects you automatically - green banner, match-found sound, taskbar flash. If you're mid-casual-game you get a red banner instead, and the mod pulls you out of that room with no disconnect penalty.

- Matches give a 10-minute show-up grace. If your opponent never joins your room, the mod warns you at 90 seconds and returns you to the menu after 6 minutes - you stay ready, and the server forfeits the match to you if they don't show.

- Between your matches there's a 7-minute breather with the next room already prepared. Both players pressing <color=#7FD4FF>Play Now</color> on the Tournaments tab starts it early.

- The server picks each match's connection region for both players, so you always land in the same room whatever your menu region is set to.

<color=#FFD94D><b>PLAYING AN ASYNC MATCH</b></color>

- When your match goes live the bot DMs both of you with the deadline. There's no start instant, no auto-connect, and no room code from the bracket.

- Agree a time with your opponent (use /dm-opponent in Discord, or just message them), then play a normal private lobby: main menu, Online, Host Room, and one of you sends the other the 6-character code.

- The result records automatically as long as you both have the mod running with <color=#7FD4FF>Ranked enabled</color> - the server binds the series to your bracket pairing from any room. The mod turns Ranked on for you when a tournament match is live (see <color=#7FD4FF>Deadlines & forfeits</color>).

- In the final 24 hours before the deadline the bot sends a check-in DM; answering that you plan to play today extends the deadline 24 hours, once per opponent.");

        private static string TournBot => I18n.Tr(@"Every tournament runs through Discord DMs from the SCR bot. None of them reach you unless your Discord is linked (F5, Discord Link tab). The big notices (lock, match live, results) are durable - if the bot is down when one fires, it retries until your DM lands. The play-day nudges (starts-in-15, next-up, waiting-on-you) are best-effort and can be missed across a bot restart.

<color=#FFD94D><b>BEFORE THE TOURNAMENT</b></color>

<color=#7FD4FF>Availability check</color> - sent 1 to 4 days before lock, once the tournament has enough players. Two buttons:
- 'Yes, I'm in' - edits the message to a confirmation. It changes nothing on the server; you were already signed up.
- 'No, remove me' - removes your signup, exactly like un-signing in game. No penalty.

<color=#7FD4FF>Lock DM</color> - you're in. Sync: your start time plus the contract (have ROUNDS open at that time). Async: how to coordinate and play. If the server last saw you on an old mod version, an update warning is appended - update before you play. No buttons.

<color=#7FD4FF>Removed at lock</color> (sync) - the field agreed on a time you didn't mark as available, so your signup was removed. No penalty; sign up again next week.

If the lock pushes back a week instead (too few players, or no time slot 8 players agree on), a fresh availability check goes out for the new date.

<color=#FFD94D><b>SYNC PLAY DAY</b></color>

<color=#7FD4FF>Starts in 15 minutes</color> - open ROUNDS now and sit at the main menu; the mod does the rest. Also posted in the tournament channel.

<color=#7FD4FF>Match ready</color> - your match vs X is ready, get in ROUNDS now. <color=#FF6666>A no-show forfeits in a few minutes.</color>

<color=#7FD4FF>Next up</color> (rounds 2 and later) - your next opponent and start time after a short breather, no rush. Want to play right away? You BOTH press Play Now on the F5 Tournaments tab.

<color=#7FD4FF>Waiting on you</color> - sent when your ready match is under 90 seconds from its no-show deadline, or sitting past it while you're marked present. It means: get to the ROUNDS main menu and leave any casual game. Repeats at most every 5 minutes.

<color=#FFD94D><b>ASYNC MATCHES</b></color>

<color=#7FD4FF>Match is live</color> - your opponent, the 7-day deadline, and how to play: agree a time, host a private lobby together, the result records automatically.

<color=#7FD4FF>Still pending</color> - once your match has sat ready for 3 days unplayed, a daily reminder with your deadline and how to coordinate. No buttons.

<color=#7FD4FF>Deadline check-in</color> - sent in the final 24 hours before your deadline. Three buttons, and your latest answer replaces earlier ones:
- 'Yes - we plan to play today' - recorded, and <color=#7FE87F>extends the deadline 24 hours</color> - once per opponent per tournament. Pressing it a second time records the answer but the deadline stays put.
- 'I reached out - no response / they quit' - recorded.
- 'Not yet - still coordinating' - recorded.

What an answer is worth: if the deadline passes with the match undecided and neither player ahead, <color=#7FE87F>a player who answered the check-in - any of the three answers - beats a player who stayed silent.</color> The full resolution order is in <color=#7FD4FF>Deadlines & forfeits</color>. Buttons re-check that your Discord is still linked to the same account before acting.

<color=#FFD94D><b>RESULTS</b></color>

After each match, both sides get a completion DM that's honest about how it ended: a played win says you won; a forfeit says 'You advance - your opponent forfeited'; a mutual no-show says 'You advance on the no-show tiebreak'. A forfeit is never dressed up as a played win.

When the bracket completes, the podium is announced in the tournament channel. Trophy roles are handed out only for brackets of 16 or more players; smaller brackets keep their prizes and achievements but hand out no Discord roles.

<color=#FFD94D><b>COMMANDS AND THE BOARD</b></color>

<color=#7FD4FF>/dm-opponent</color> followed by your message - the bot relays it to your current tournament opponent's DMs. Limited to 8 messages per minute.

<color=#7FD4FF>/opp-online</color> - checks whether your tournament opponent currently shows as online on Discord.

The tournament channel keeps a living board for both tournament kinds, refreshed every 2 minutes.");

        private static string TournForfeits => I18n.Tr(@"What happens when someone doesn't show up, quits, or leaves a tournament - and exactly how prizes are computed. Short version: <color=#7FE87F>a finished series always stands</color>, absence is what gets punished, and forfeit wins never pay podium prizes.

<color=#FFD94D><b>DEADLINES</b></color>

- Sync: matches give a 10-minute show-up grace from the moment they go ready. A match that follows a PLAYED match sits in a 7-minute breather first (a bye-fed match can go ready immediately), and a match still in its breather can never forfeit anyone. While both players are present the server waits - a sync match can run past its deadline.

- Async: every match, the grand-final reset included, has a 7-day deadline from the moment it goes live. The deadline check-in DM can extend it 24 hours, once per opponent. Presence doesn't spare an async match - only playing does.

<color=#FFD94D><b>WHEN THE DEADLINE HITS</b></color>

The server resolves an overdue match in this exact order - the first rule that applies decides it:

- 1. <color=#7FE87F>A finished series always stands</color> - nothing overrides a played result.
- 2. If exactly one seat is banned, the other player advances immediately.
- 3. A game reported in the last 45 minutes means a live series - the match is left alone.
- 4. Sync only: both players present - the server keeps waiting.
- 5. Exactly one player present - <color=#FF6666>the absent player forfeits</color> and the present one advances.
- 6. Otherwise: if the series was started and the score is uneven, the score leader advances. Failing that, if exactly one of you answered the async deadline check-in - any answer - that player advances over the silent one. Failing that too, the lower no-show % advances, and a dead tie falls to a fixed arbitrary tiebreak.

Only absent seats get the no-show mark (a banned seat forfeits regardless of presence, and a silent seat can lose the async tiebreaks while present). Your <color=#7FD4FF>no-show %</color> is a rolling 90-day rate that decides your priority into future tournaments, backfill order, and these tiebreaks.

<color=#FFD94D><b>WHAT A FORFEIT DOES - AND DOESN'T</b></color>

- The bracket advances exactly as if the match completed - the winner moves on, the loser drops or is out.

- <color=#FF6666>A forfeit mints nothing.</color> Podium placements only exist for played, completed series - a forfeit-decided podium spot pays no prize.

- No rating moves. Rating only changes when a series completes; a forfeited match's series is simply never completed or scored.

- Betting closes: a forfeited match's series can't be bet on.

<color=#FFD94D><b>LEAVING, AND WHO REPLACES YOU</b></color>

- During voting: un-sign freely.

- After lock, before the start: the backfill flow runs - the most reliable speculative signup takes your exact bracket slot (with their own rating); no speculative available means your would-be opponents get byes. Leaving this way carries no penalty.

- Once running: you can't un-sign. Not showing up forfeits your matches and counts on your no-show %.

- Quitting mid-game follows normal 1v1 disconnect rules: the DC lands on your leave %, and unless your opponent was at match point (then they take the game, which can finish the series) the series stays open at its score. The deadline sweep resolves an abandoned series: after the 45-minute grace a still-present opponent wins; if both walked away, the score leader advances.

<color=#FFD94D><b>THE RANKED OVERRIDE</b></color>

- When one of your tournament matches is live and your Ranked toggle is off, the mod flips it ON and tells you. Async matches happen in private lobbies, which only record as ranked when both players have Ranked enabled - the override guarantees your result records.

- <color=#FF6666>It stays ON after the match.</color> There is no auto-revert: turn it off in Settings if you don't want later games rated. Turning it off between tournament matches gets it flipped back on when your next match goes live.

<color=#FFD94D><b>PRIZES, TROPHIES AND BETTING</b></color>

- The pool scales with the player count snapshotted at lock. At 8 players: 1000 / 600 / 120 Gold and 5000 / 3000 / 150 XP for 1st / 2nd / 3rd. It grows linearly with the field, doubling at 16 players: 2000 / 1200 / 240 Gold and 10000 / 6000 / 300 XP.

- <color=#7FE87F>Prizes pay when the whole bracket completes</color>, not when your final match ends. A forfeit-decided rank is skipped rather than passed down.

- <color=#8A8A93>Prize XP behaves like any other XP: it converts to Gold at the usual 100 XP = 1 Gold, and a level boundary it crosses pays the normal level reward.</color>

- Trophies are Discord roles: SCR Tournament Winner, Runner Up, and 3rd Place; a second same placement upgrades the role to its (x2) version. Every confirmed participant gets the Participant role. Roles only go out for brackets of 16 or more players. Winning or taking 2nd in a tournament also unlocks a paying achievement (separate ones for sync and async), and playing a bracket through without ever forfeiting unlocks Iron Bracket.

- Every tournament game is a normal ranked best-of-3: it moves your regular 1v1 rating whether or not you reach the podium.

- Tournament matches are bettable on the same terms as any live ranked series: betting locks at 2 live points in game 1 or once any game is decided. An async pairing that waits days stays bettable the whole wait at 0-0.");

        private static string Rating => I18n.Tr(@"Every ranked mode scores you with Glicko-2: a rating, plus a measure of how sure the system is about it. This page explains what the numbers mean, why they move the way they do, when each mode updates, and the full rank ladder.

<color=#FFD94D><b>THE THREE NUMBERS</b></color>

<color=#7FD4FF>Rating</color> - the skill estimate. Everyone starts at 1500. There is no floor and no ceiling anywhere; your peak is tracked per mode.
<color=#7FD4FF>RD (rating deviation)</color> - how uncertain the estimate is. A brand-new account starts at 350. RD shrinks every time you play - the more you play, the surer the system gets.
<color=#7FD4FF>Volatility</color> - how erratic your results have been. Starts at 0.06 and adjusts on its own as results come in.

The size of a rating move scales with YOUR RD. That is why new accounts swing hard - their first results move them a lot - while a veteran's results move them a little at a time. Playing more games is the only thing that settles it.

<color=#FFD94D><b>WHY GAINS AND LOSSES AREN'T EQUAL</b></color>

Before scoring a result, the system computes your expected result from the rating gap. Your change is proportional to the difference between what happened and what was expected:

- Beat a much lower-rated player and you gain almost nothing - the win was expected. Lose to them and you pay heavily.
- Beat a higher-rated player and you take the big side of the same trade.
- The opponent's RD matters too: results against uncertain (high-RD) opponents are dampened. Beating a well-established account moves your rating more than beating a fresh unknown one.

<color=#FFD94D><b>WHEN RATINGS MOVE</b></color>

Each mode keeps its own fully separate Glicko rating. Nothing you do in one mode ever moves another mode's number.

- <color=#7FD4FF>1v1</color> - updates when the series completes (first to 2 game wins). The whole series counts as ONE win or loss observation: a 2-0 and a 2-1 move your rating identically.
- <color=#7FD4FF>2v2</color> - updates when the series completes. You are scored against BOTH opposing players. A series decided by a disconnect applies full ratings, the same as a played-out one.
- <color=#7FD4FF>FFA</color> - updates after every single game, when its report lands.
- <color=#7FD4FF>1v2</color> - <color=#FF6666>unrated beta. No rating moves at all.</color> Games are recorded and can count later when ranked 1v2 launches.

Casual games never touch any rating.

<color=#FFD94D><b>HOW FFA SCORES A LOBBY</b></color>

A 10-player game is not treated as 9 separate duels - that would swing your rating several times harder than a 3-player game. Instead:

- You are compared against at most 4 opponents: the ones placed NEAREST to you.
- One extra 'upset' comparison can join them: the biggest 250-plus rating gap that finished upside down outside those picks. One per game, however many upsets happened.
- Each comparison scores as a win if you placed above them, a loss if below, and <color=#7FE87F>a shared place counts as a draw</color>.
- Short games weigh less: a first-to-3 counts as half a game, the default first-to-5 counts fully, and longer targets never count as more than one game.

<color=#FFD94D><b>THE 2v2 TRUST RULE</b></color>

Your 2v2 rating starts as a guess, so the matchmaker doesn't trust it right away:

- Team balancing uses your 2v2 rating once you have 10 completed series, OR once its RD has converged to 110 or below.
- Until then, your 1v1 rating stands in.
- The leaderboard's Avg Mate Elo column trusts a teammate's 2v2 rating after 5 completed series; before that it uses their 1v1 rating, or 1500 if they have none.

<color=#FFD94D><b>THE RANK LADDER</b></color>

Five tiers, each split into rungs I to V - V is the top of its tier. The number is the floor: you hold a rung at or above that rating.

- <color=#7FD4FF>Grand Master</color> - I 2330, II 2400, III 2470, IV 2540, V 2610
- <color=#7FD4FF>Master</color> - I 1980, II 2050, III 2120, IV 2190, V 2260
- <color=#7FD4FF>Advanced</color> - I 1675, II 1725, III 1780, IV 1845, V 1910
- <color=#7FD4FF>Intermediate</color> - I 1500, II 1525, III 1555, IV 1590, V 1630
- <color=#7FD4FF>Beginner</color> - I 0, II 1140, III 1260, IV 1360, V 1440

Reaching 1980 (Master) or 2330 (Grand Master) in ranked 1v1 or 2v2 also grants the matching achievement - FFA rating does not trigger these. Discord rank roles follow your 1v1 rating, and the Current Rank shop title always renders your live rank name in its tier color. Your opponent's tier also multiplies your match rewards (see <color=#7FD4FF>XP, Gold & levels</color>).");

        private static string Rewards => I18n.Tr(@"Every finished game pays XP, XP converts to Gold at 100 XP = 1 Gold, and ranked play multiplies the base rewards below by your opponent's rank tier. This is the pay table - exact numbers, mode by mode. (Tournament podium prizes are separate; see <color=#7FD4FF>Deadlines & forfeits</color>.)

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
- Ghosts and graced early leavers are unpaid and unrated for that game: leaving before the field scored 2 half points, while your own tally (points, half points, kills) is still zero, takes you out of it entirely.

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

<color=#8A8A93>Outside matches: Discord server boosters are paid 2000g monthly, and community artists earn a 30% royalty (rounded down to whole Gold) when another player buys their item - gifts pay none.</color>");

        private static string Betting => I18n.Tr(@"Gold betting runs on live 1v1, 2v2 and FFA games. This page covers who can bet, how the odds are priced, exactly when windows open and close, and what happens to your stake.

<color=#FFD94D><b>WHO CAN BET</b></color>

- Any registered player, staking 1 to 2000 Gold per bet. The stake is taken the moment the bet is placed.
- You cannot bet on a match or lobby you are playing in, and banned players cannot bet.
- <color=#7FE87F>Spectators CAN bet.</color> That is safe by design: the windows below close on early scoring, so watching a game never gets you a bet on a result that is already decided.
- One bet per series in 1v1 and 2v2; one bet per game in FFA.
- If any participant runs a mod older than 1.38.1, betting on that game is refused. Older clients cannot report live points, so the scoring cutoff could never fire - <color=#FF6666>the system fails closed rather than leave a window open.</color>
- A linked Discord account can place the same bets through the bot's commands.

<color=#FFD94D><b>ODDS: 1v1 AND 2v2</b></color>

- Your multiplier is 1 divided by your side's win chance, computed from both sides' ratings AND their RD (see <color=#7FD4FF>Ratings (Glicko-2)</color>). Floor: 1.01x.
- Uncertainty caps the price. With both sides established (RD 100 or below) the multiplier can reach 3.0x; the cap slides down to 1.0x as the higher RD rises to 300. A fresh account at RD 350 caps the price below the 1.10x acceptance gate - <color=#FF6666>an unknown simply can't be bet on, so a smurf can't be farmed for Gold.</color>
- A side only accepts bets at 1.10x or better; below that it is locked.
- 2v2 prices off the pair's average rating. A player's own 2v2 rating counts once they have 10 completed series; before that their 1v1 rating stands in.

<color=#FFD94D><b>ODDS: FFA</b></color>

- The server races every player to the lobby's score target and computes your pick's true chance of banking it first. Your multiplier is half of the fair price - the house keeps the other half.
- Floors: 2.0x in lobbies of 5 or more, 1.4x at 3-4 players. For heavy favourites the floor gives way to 0.95 divided by their win chance, so a guaranteed-profit bet cannot exist.
- Cap: 5.0x, or half the lobby size if that is lower, and it shrinks when ratings are uncertain.
- A player with no FFA games yet is priced off their 1v1 rating at full uncertainty.

<color=#FFD94D><b>WHEN BETS OPEN AND CLOSE</b></color>

The cutoff is scored points, never a clock:

- <color=#7FD4FF>1v1 and 2v2</color> - open from the moment the series exists. Closed once 2 total points are scored in game 1, or the moment any game of the series is decided. Tournament series stay listed through the whole multi-day wait before the pair actually plays.
- <color=#7FD4FF>FFA</color> - each bet targets the lobby's NEXT game. The window closes when the field scores 2 points in that game (1 point if the lobby's score target is 3 or lower). A lobby is only listed while a next game is plausible: up to 15 minutes while assembling with no games yet, and up to 30 minutes after its last recorded game. <color=#FF6666>Casual lobbies are never bettable.</color> Departed members are not valid targets.
- <color=#7FD4FF>Lobby-phase bets</color> - hosted 2v2 and FFA lobbies take wagers while still FILLING. No odds are quoted yet; at Start the bet is priced from the final field and becomes a normal bet - provided your target is still there and the usual checks pass. Anything else (target left, odds too low, lobby never starts within 6 hours) refunds the stake.
- 1v2 has no betting at all.

<color=#FFD94D><b>PAYOUTS AND THE FIGHTER TAX</b></color>

- A winning payout includes your stake back. 1v1 and 2v2 pay stake x odds rounded to the nearest Gold; FFA rounds DOWN.
- If your winning bet's stored odds were 1.50x or below, 20% of the PROFIT goes to the fighter or team you backed - being worth betting on pays them too. The potential payout quoted when you place the bet already includes this tax.

<color=#FFD94D><b>REFUNDS, AND WHERE TO SEE IT ALL</b></color>

A refund returns exactly your stake:

- 1v1: a non-tournament series with no game reported in its first 30 minutes is abandoned and refunds its bets. A series stalled for 60 minutes mid-series refunds its bets too, while the series itself stays resumable - <color=#FF6666>a refunded bet stays refunded even if that series is finished later.</color>
- 2v2: refunds only when a series is cancelled. Disconnect-paused series wait for the admin ruling before anything settles.
- FFA: refunds only for a game that never produced a recorded result. Played games always settle as won or lost.
- At tiny stakes a WIN can pay exactly your stake (1g at 1.10x pays 1g). It is still a win: every bet's stored state - open, won, lost or refunded - is what displays, not the arithmetic.
- Your full bet history across all modes is the bets ledger in the F5 menu. Live bettable games are listed in-game and mirrored in the Discord live-bets channel and its bet commands.");

        private static string Tracking => I18n.Tr(@"Every game you play with the mod runs the same pipeline: every modded client watches the match, one of them files the report, and the server decides what it counts for. This page covers how a game gets classified and reported. For what each stat actually measures, see <color=#7FD4FF>How stats are tracked</color>.

<color=#FFD94D><b>WHAT MAKES A GAME COMPETITIVE</b></color>

- Rooms the mod creates itself are consented by definition - queueing up IS your consent. The ranked queue, 2v2 and tournaments play rated; ranked FFA lobbies rate their games while casual ones don't; 1v2 records without rating.
- A private room-code game is ranked only when three things are all true: <color=#7FE87F>your Ranked toggle is on, your opponent runs the mod, and their Ranked setting is on too</color>. The mod recognizes a modded opponent by the presence data their client publishes into the room; a vanilla player has none.
- Your client asks the server whether the opponent has Ranked enabled, and keeps re-checking for a while after they join - a player who launched their game seconds ago can briefly look unranked.
- As soon as a ranked pairing is confirmed, the client registers the series with the server, so the score HUD and the bets panel work from game 1.
- If either side has Ranked off, the server answers 'not ranked', your client flips the game to casual, and you get one toast per room saying so.
- The server re-checks everything again when the report lands. A mid-series toggle can't void a best-of-3 that's already running, and a game reported as casual gets upgraded to ranked when the server can see both players are modded, both consented, and the sitting is live. An opponent who has never run the mod can never be upgraded - genuine quickplay stays casual forever. (A live unfinished series from an earlier sitting is the one thing that keeps ranked status across a gap.)

<color=#FFD94D><b>WHO SENDS THE REPORT</b></color>

- One client reports each game: the player with the numerically LOWER Steam ID. Both clients apply the same rule, so they almost never race - and if a rare early-room edge makes both send, the server keeps exactly one. Against a vanilla opponent the modded player always reports - nobody else can.
- 2v2 elects the lowest Steam ID of the four, 1v2 the lowest of three, and FFA the lowest among players still PRESENT at game over (a leaver can't report).
- In 1v1, if the elected reporter crashes or leaves, the survivor takes over and the disconnect rules decide the result; FFA simply elects among whoever is still present (see <color=#7FD4FF>When a game counts</color>).
- The server enforces one-report-per-game on its side too: nothing ever records or pays twice, and a duplicate send is either answered with the already-recorded result or set aside.

<color=#FFD94D><b>WHAT IS IN A REPORT</b></color>

- The result: both sides' rounds and points, match duration, region, and a per-game room id.
- Cards: every pick with its round and pick order, plus - for the reporting player - what they were offered and passed on. Your offers only ever come from your own client, never your opponent's.
- Combat stats: bullets fired and hit, block attempts and successes, damage dealt, and (in 1v1) deaths with how they happened.
- Timelines for the graphs: FPS, ping, hit/block progress and damage, sampled every few seconds across the whole game. (1v2 carries a lighter set for now.)
- Connection health (fullest in 1v1): frame freezes, network silence gaps, and whether the opponent's live updates stalled.
- A snapshot of every player's final build, taken at game over before anything can wipe it.
- Input pacing: how many gameplay keys and clicks you pressed while alive in combat. Counting covers only the movement, fire and block keys, runs only during active combat, and stops while you're typing in any chat or have the menu open.
- <color=#7FE87F>The core result is SIGNED by the reporting client</color>, so it can't be altered in transit and a random program can't forge one. The stat telemetry rides outside the signature and is treated as advisory - useful data, never proof.

<color=#FFD94D><b>WHAT THE OTHER CLIENT DOES</b></color>

- The non-reporter runs the whole game-over pipeline too - achievements, session tallies, its own stat capture. It just doesn't send the match.
- During the match, both clients publish their live stats to each other through the room every few seconds. That's how the report carries YOUR fired/hit/block numbers when your opponent is the one filing it.
- Only the reporter's client sees the server's response, which is why the XP toast and the series score land on one screen first.

<color=#FFD94D><b>CASUAL GAMES ARE RECORDED TOO</b></color>

- A casual 1v1 writes the same full match row as a ranked one: score, cards, duration, all the telemetry.
- Both players earn XP - base 250, x1.5 for a win, +100 for a 5-0 sweep - and XP converts to gold at the usual 100 XP = 1 gold. Casual win-streak achievements count too.
- What casual never touches: no series, no rating change, no bets, no ranked leave %.
- A vanilla opponent gets a stats page auto-created from the report. <color=#7FE87F>They keep pure vanilla gameplay, and the only part of the mod they can ever see is nametag styling</color> (see <color=#7FD4FF>What unmodded players see</color>).");

        private static string WhenCounts => I18n.Tr(@"The rule book for what gets recorded and what gets thrown away: games, series, disconnects, bets. If a result looks missing, the reason is almost always on this page.

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
- A 2v2 game that ends without its series id retries the lookup and defers the send; if that also fails, the game is not recorded.");

        private static string Anticheat => I18n.Tr(@"Ranked only works if results can be trusted. The short version: every report is signed and identity-checked, both players' clients gather evidence about each other, detectors flag for human review rather than auto-punishing (one narrow farming pattern is the only exception), and a person makes the final call.

<color=#FFD94D><b>MACRO DETECTION</b></color>

- Your client samples gameplay input every frame - movement, fire, block - only while you're alive in active combat, never while typing or in menus.
- Sustained input far beyond any human's pace is recorded as suspect windows with exact per-second rates and per-match peaks.
- BOTH players hold the evidence. Each client publishes its counters to the other during the match, so the report carries the opponent's windows too - and in 1v1 a client with serious evidence also files it directly with the server, signed, so it survives even when the reporter's copy is stale or lost.
- Evidence merges can only strengthen: a later submission can never weaken peaks or windows already captured. If a flag has already been reviewed, new evidence opens a fresh review instead of editing the decided one.
- Flagged macro suspects are quietly excluded from the Compare tab's similar-players pool until cleared - a macro'd input profile would poison the matches for everyone.

<color=#FFD94D><b>AFK DETECTION</b></color>

- A 1v1 reporter with zero shots, zero blocks and zero card picks across a match longer than two minutes gets flagged. The card check is the load-bearing one: pacifist and melee builds legitimately finish games without firing a bullet, but nobody picks zero cards while at the keyboard.

<color=#FFD94D><b>IMPOSSIBLE PACING</b></color>

- Speedhacks speed up the client's own clock, so the server never trusts client-reported durations. It measures the wall time between report arrivals on its own clock; a series arriving faster than games can physically be played is flagged, with the exact intervals stored for review.
- The one automatic penalty in the whole system: a repeated pattern of implausibly short matches between the same two players is invalidated outright, earlier games in the pattern included - gold and XP reversed, series voided. Everything else on this page flags for human review.
- Chronic low FPS and rough connections are judged against YOUR OWN recent history, so a machine that always runs that way never flags; sudden convenient dips are judged against the same match's normal.

<color=#FFD94D><b>SIGNED, DEDUPED, QUARANTINED</b></color>

- Every match report is signed and identity-checked: the reporter must be a participant in the match and must hold that account's live Steam session. <color=#7FE87F>Nobody can report AS you</color> - and nothing anyone else reports can put a number on the records boards under your name.
- Each game can be recorded exactly once. Duplicates and replays are absorbed - the server hands back the already-recorded result and nothing pays twice.
- A team or FFA report that arrives for a closed lobby is quarantined for admin review, not trusted and not silently dropped.

<color=#FFD94D><b>NOBODY CAN PLANT DATA UNDER YOUR NAME</b></color>

- The records boards only ever show rows from a player's OWN reports, so an opponent's client can't put a number under your name no matter what it sends.
- Card-draw records work the same way: a report counts only for the reporter's own seat on the Luckiest board.
- The worst a modified client can do is lie about ITSELF - and self-reported numbers are exactly what the pattern detectors watch, stay advisory until a human reviews them, and are reversible afterward.

<color=#FFD94D><b>BETTING LOCKS</b></color>

- Betting closes the moment real information exists. In 1v1 and 2v2 that's 2 points scored in game 1, or any game of the series decided; in FFA it's 2 points across the field in the current game (1 in a first-to-3 lobby).
- The lock is enforced by the server when the bet is placed, not just hidden in the menu. You can't bet on your own match, and it's one bet per series (per game in FFA) per player.

<color=#FFD94D><b>HUMAN REVIEW</b></color>

- Every flag lands in front of an admin with its exact evidence - for a macro flag, the windows, the peaks and both sources.
- A verdict binds to the exact evidence the admin reviewed. If stronger evidence arrives mid-review, the review is redone against it - a stale read can't decide a flag.
- A false-positive verdict on anything auto-invalidated triggers a tracked repair of the affected gold and rating.
- A confirmed verdict doesn't fire an automatic penalty. Enforcement runs through separate, individually audited admin tools: bans and series reversal. A ban cuts live access immediately - sessions revoked, queues blocked, ranked refused - and if you ever match a banned player, your client leaves automatically with a notice.");

        private static string VanillaSafety => I18n.Tr(@"The mod changes vanilla gameplay only where every player agreed to it. This page explains exactly how it decides, and what is guaranteed when you play with non-modded people.

<color=#FFD94D><b>THE GUARANTEE</b></color>

<color=#7FE87F>A non-modded player always gets pure vanilla gameplay, and any gate that can't prove a change is safe leaves it off.</color> Whole-room changes fail closed for everyone identically. The one per-player feature is poison sync, which follows the poisoned player - an unmodded victim's poison stays vanilla.

If the mod can't prove a feature is safe to run, it runs vanilla.

<color=#FFD94D><b>HOW ROOMS ARE CLASSIFIED</b></color>

Mode-tied gameplay runs only in rooms the mod itself created, and the room's name says which mode issued it:

- <color=#7FD4FF>ranked_</color> - 1v1 ranked queue rooms
- <color=#7FD4FF>team_</color> (or the 2v2 room marker) - 2v2 rooms
- <color=#7FD4FF>sct-</color> - sync tournament rooms
- <color=#7FD4FF>ovt_</color> - 1v2 rooms
- <color=#7FD4FF>ffa_</color> - FFA rooms, and only while the FFA lobby engine is actually active

A public quickplay room or a normal 6-character room code matches none of these, so every mode-tied gameplay change stays off there.

<color=#FFD94D><b>CAPABILITY GATES</b></color>

Changes to the shared simulation go a step further: each player's mod advertises a capability tag BEFORE joining the room, so any client that can even see you has already received your tag. Then:

- <color=#7FD4FF>Grow normalization</color>, <color=#7FD4FF>FFA map-object scaling</color> and the <color=#7FD4FF>FFA same-card dealer</color> require EVERY fighter's tag. <color=#7FE87F>One vanilla player, one outdated mod, or one player whose mod disabled itself switches the feature off for the whole room - symmetrically, on every screen at once.</color> Nobody plays by a different rule than their opponent.
- <color=#7FD4FF>Poison sync</color> activates per victim, in any online room: a current victim's own client judges their poison; an unmodded victim's poison stays vanilla. The mixed-room details live in <color=#7FD4FF>Poison & damage over time</color>.
- Spectators never count toward or against these checks.
- If a feature's patch fails to install, that client never advertises the tag. If any other BepInEx mod is detected at startup, the whole mod disables itself and revokes its tags - full vanilla behavior.

<color=#FFD94D><b>TWO KINDS OF FIXES</b></color>

Not everything is gated, and the distinction matters:

<color=#7FD4FF>Crash prevention</color> - always on, everywhere, quickplay included. These guards stop vanilla bugs like the frozen-inputs-at-match-found crash, the permanently dead Escape key, and the Phoenix revive crash. They change no rule: each one replaces a crash or a broken state with what the game intended.

<color=#7FD4FF>Gameplay changes</color> - gated as above. Mode logic needs its mod-issued room; Grow and the FFA features need the full-room capability check; poison authority is per-victim as described.

Between the two sits a band of local repairs (re-registering vanilla's own broken bullet effects, clearing a stuck auto-fire flag between games) that run in any game - but these only repair your own screen's bookkeeping toward what the bullet's owner already decided. They never change a rule, and can't create a disagreement vanilla didn't already have. The full inventory is in <color=#7FD4FF>Bug fixes the mod ships</color>.

<color=#FFD94D><b>QUICKPLAY WITH THE MOD</b></color>

Playing quickplay or a room code with the mod installed, you get vanilla rules plus tracking: your casual results and stats still record, and achievements can still unlock. <color=#8A8A93>A recovery guard can also restart a dead quickplay search for you - that is connection plumbing, not gameplay.</color>

Two fairness fixes can reach quickplay and room-code games: <color=#7FD4FF>Grow normalization</color> (every fighter current, everyone's Ranked on at connect - both sides always agree on it) and the per-victim poison sync, which follows the poisoned player wherever they play (see <color=#7FD4FF>Poison & damage over time</color> for the mixed-room details).

<color=#7FE87F>And your opponent never has to know the mod is there unless you talk to them: the only things a non-modded player can ever see of it are nametag styling and quick-chat messages you send</color> (see <color=#7FD4FF>What unmodded players see</color>).");

        private static string VanillaFixesP1 => I18n.Tr(@"What each vanilla bug fix does and where it applies. Gating rules are in <color=#7FD4FF>Vanilla stays vanilla</color>: crash guards run everywhere, gameplay changes only where everyone is modded and agreed.

<color=#FFD94D><b>ALWAYS ON - CRASH AND STATE GUARDS</b></color>

These run in every game, quickplay included. None changes a rule: each replaces a crash or a broken state with what the game intended.

<color=#7FD4FF>Frozen inputs, dead Escape</color> - vanilla's input toggle crashes on a half-spawned player, freezing your keys at match found or permanently killing Escape. The mod skips the half-wired player and carries on.

<color=#7FD4FF>Can't ready up</color> - vanilla can try to spawn you before the connection has joined a room and leave you with no ready ring. The mod holds the spawn until the room is real; after 30 seconds it returns you to the menu.

<color=#7FD4FF>Dead blocks, silent Shield Charge, invisible Empower</color> - between games, vanilla can tear cards down in the wrong order and leave dead handlers on your block and gun: a block that does nothing, a Shield Charge that never triggers again, an invisible double-damage Empower. The mod scrubs them before every block and at every game and rematch start.

<color=#7FD4FF>Phoenix revive crash</color> - after an FFA leaver, vanilla's Phoenix looks its revive target up by list position, crashes, and leaves them invisible and unhittable on every screen, forever. The revive now resolves by player ID.

<color=#7FD4FF>One-screen health desync</color> - a sound-engine crash during lifesteal could abort your client's ENTIRE incoming hit, and ROUNDS never re-syncs health - the two screens then disagreed about your HP forever. The sound failure is swallowed so the damage still lands.

<color=#7FD4FF>Display and audio repairs</color> - a leaver emptying a team no longer freezes everyone on the victory screen; a failed Steam name lookup is retried (15 tries over half a minute) instead of naming you 'PlayerName' all room; Chase's card text drops its Health line (vanilla never applies that stat - the card itself is unchanged); leaked sound voices no longer muffle the session; looping sounds (map saws, Abyssal Countdown's charge) stop when their round ends; plus expiring a leaking radar visual, quieting crown errors, and silencing pure log-noise crashes.

<color=#FFD94D><b>ANY GAME - LOCAL REPAIRS</b></color>

These run in every online room too. Each repairs your screen's bookkeeping toward what the bullet's owner already decided - no rule changes, no new disagreements.

<color=#7FD4FF>Spray loses auto-fire</color> - one Demonic Pact poisons every later game in the room: vanilla copies its no-auto-fire flag onto the gun and never clears it, turning Spray click-per-shot. Cleared between games.

<color=#7FD4FF>Invisible Drill bullets</color> - a point-blank Drill bullet could go invisible on the other screen (its effect registered before the bullet finished initializing). The mod snaps it to its true position and re-registers the missing pieces.

<color=#7FD4FF>Poison that lands but does nothing</color> - the same race hit poison: the bullet visibly hits on your screen but no damage follows, because the poison never registered on the remote copy. Re-registered, with a dedupe so it can never register twice for double damage.

<color=#7FD4FF>Round-end phantom kills</color> - poison and burn ticks during the round-won animation could kill mid-transition and award a phantom round. Modded clients ignore damage-over-time and deaths during the transition window; full room-wide protection needs the room's (usually modded) host seat too.

<color=#7FD4FF>Leftover bullets after the point</color> - vanilla never clears mid-air bullets at a point boundary, so an end-of-round poison bullet could hit you AFTER respawn. Each client now despawns its own bullets at the boundary, via vanilla's own despawn call.");

        private static string VanillaFixesP2 => I18n.Tr(@"<color=#FFD94D><b>WHOLE-LOBBY GATED - REAL GAMEPLAY CHANGES</b></color>

These change the shared simulation. Grow, the crate rescale and the same-card dealer are whole-room gated: <color=#7FE87F>one vanilla or outdated fighter and everyone gets vanilla, symmetrically.</color> Poison sync is per-victim, with its own mixed-room fallbacks.

<color=#7FD4FF>Poison sync</color> - vanilla runs poison separately on every client, each judging your block by its own timing - screens permanently disagree about which ticks landed ('ghost HP'). Now the victim's own client decides every tick and publishes the verdict; every modded client applies exactly that set. An unmodded victim gets the pure vanilla loop instead. Works in any online room. <color=#8A8A93>In mod-issued rooms with an incapable client present, the modded clients instead agree blocking does not negate poison - agreement beats the ghost-HP split.</color>

<color=#7FD4FF>Grow normalization</color> - Grow's damage compounds per FRAME on the shooter's machine: about x1.07 over a full flight at 400 FPS, x1.53 at 60, x2.31 at 30 unstacked, worse stacked - which is how low-FPS players one-shot with Grow plus any explosive. Normalized bullets grow at one fixed rate. Gate: every fighter modded and current, AND a mod-issued room or everyone's Ranked ON at connect. Otherwise vanilla growth for everyone.

<color=#7FD4FF>Falling crates on big FFA maps</color> - on scaled FFA maps vanilla respawns networked crates and saws too small, ropes miss, and they drop at round start. Rescaled only when every fighter is capable; FFA queue rooms only.

<color=#7FD4FF>FFA same-card dealer</color> - the Same Cards rule deals identical draws; needs every member current, else each client rolls privately.

<color=#FFD94D><b>MODE ROOMS ONLY</b></color>

Vanilla ROUNDS is built for exactly two teams, so FFA rooms replace the round engine outright: round end, scoring, card targeting (vanilla aimed 'other team' cards at the first player), spawns, leaver tolerance. None of it can run outside FFA rooms.

<color=#7FD4FF>Radiance in FFA</color> - vanilla's wave hit its own caster the moment they moved, and stopped after ONE hit while visibly sweeping everyone else. The FFA version excludes the caster and hits each opponent the ring sweeps, once, ending when the ring ends.

<color=#7FD4FF>Crown in 2v2</color> - vanilla can't move the crown past the first two players; the leading TEAM wears it, both members.

<color=#7FD4FF>Card-pick stage in 2v2/1v2</color> - vanilla shows only ONE picker's body per round (sometimes the wrong one), leaving the second picker on an empty stage. Each picker is re-staged in turn; the 1v2 solo's extra pick also fixes a vanilla crash that hung the round.

<color=#7FD4FF>Auto-continue</color> - mod rooms auto-confirm the rematch prompt. Room-code games deliberately keep the vanilla prompt: after one side clicks Yes, vanilla starts a 10-second timer that kicks that side to the menu if the other never answers - one-sided auto-Yes kills the player it tries to help.");

        private static string Visibility => I18n.Tr(@"What other players can and cannot see of your mod. The short version is a guarantee: <color=#7FE87F>the only things a non-modded opponent can ever see of the mod are your nametag styling and the quick-chat phrases you choose to send.</color> Quick chat is chat, not a cosmetic - it goes out through the game's own chat bubble, exactly like a typed message. Everything else either needs the mod on the viewer's side or never leaves your machine.

<color=#FFD94D><b>WHAT A NON-MODDED OPPONENT SEES</b></color>

<color=#7FD4FF>Nametag styling - visible, with two exceptions below.</color> Formatting (bold, italic, underline, strikethrough, float), solid and neon colors, sizes, caps and spacing transforms, rainbow and the gradients all render on a completely unmodded client. The mechanism: the mod writes the style into your Photon nickname as rich text, and vanilla's own name labels already render rich text - players were putting raw style tags in their Steam names long before this mod existed. That's why this one class is allowed to cross.

Two nametag styles are the exception and render mod-side only:

- <color=#7FD4FF>Glows</color> - applied locally on modded screens. A vanilla opponent sees your name without the glow (any other styling you stacked still shows), and no leftover artifact.
- <color=#7FD4FF>Typefaces</color> - a local font swap. A vanilla opponent sees your name in the default font.

Everything else shows a non-modded player nothing:

- <color=#7FD4FF>Face cosmetics</color> - the item ID travels over vanilla's own face channel, but a vanilla client doesn't know the ID and renders an EMPTY slot instead. No crash, no fallback item - that slot is bare on their screen, and any vanilla face parts you wear still show normally.
- <color=#7FD4FF>Trails</color> - nothing.
- <color=#7FD4FF>Body colors</color> - they see the default team orange/blue.
- <color=#7FD4FF>Auras</color> - nothing.
- <color=#7FD4FF>Titles, chat styling, Hide Gold</color> - these only exist on mod surfaces (the F5 overlay, T-chat, Discord). Vanilla has no place to show them.

<color=#FFD94D><b>WHAT A MODDED OPPONENT SEES</b></color>

The whole catalog: your face cosmetics render fully (the art ships inside the mod), plus your trail, body color, aura, nametag glow and typeface, and your title on the boards and in chat.

Three caveats:

- Modded viewers can individually opt out of trails, body colors, and animated cosmetics in Settings - your cosmetic renders only for viewers who left those on.
- A body color also becomes your team identity on modded screens: point announcements, the round-counter dots, and the FFA score strip use it. A viewer with that setting off sees plain vanilla teams.
- Titles never appear over your head in-match, for anyone. They render on the F5 boards, in T-chat, and on Discord only.

<color=#FFD94D><b>WHAT NEVER LEAVES YOUR MACHINE</b></color>

- <color=#7FD4FF>Map skins</color> - never networked at all. Nobody sees your map skin, modded or not: every player sees their own equipped skin, or vanilla. Equipping one changes exactly one screen - yours.
- <color=#7FD4FF>Cursor color and shape</color> - your own cursor, on your own screen.

<color=#7FE87F>Your cosmetics never produce a broken visual, an empty rectangle, or a crash on a non-modded screen.</color> <color=#8A8A93>One early glow implementation did leak a visible rectangle to vanilla clients - it was removed for exactly that reason, and glows have rendered mod-side only ever since.</color>");

        private static string Titles => I18n.Tr(@"Titles are the short labels that render beside your name across the mod - leaderboard rows, Recent Series, Records, Compare, and every T-chat message you send. You can own any number of them, but only one is active at a time: pick it in the Shop tab with <color=#7FD4FF>Set Active</color>.

<color=#FFD94D><b>CURRENT RANK - FREE FOR EVERYONE</b></color>

<color=#7FD4FF>Current Rank</color> costs 0 gold and sits in the shop for every player. It's dynamic: wherever it renders, it shows your live 1v1 rank name in that rank's color, resolved fresh at render time. Rank up and the title upgrades itself; rank down and it follows you there too. The ladder behind it runs 25 rungs, from Beginner I at 0 rating to Grand Master V at 2610.

<color=#FFD94D><b>PODIUM TITLES</b></color>

There are three podium titles, one per ranked ladder: 1v1, 2v2 and FFA. Each is granted the moment you enter that board's visible top 3, and taken back the moment you fall out of it <color=#8A8A93>(the position check runs on a cached board, so both directions can trail the actual standings by a minute or two)</color>. A board only lists players who have at least one counted series - or, for FFA, one recorded game - so a fresh account can't hold a podium.

The rendering is the interesting part:

- While you hold a podium spot, the title renders live as <color=#FFD700>1st Place</color>, <color=#C0C0C0>2nd Place</color> or <color=#CD7F32>3rd Place</color> in gold, silver or bronze - always your CURRENT position, with a 1v1, 2v2 or FFA prefix everywhere except that ladder's own board.
- <color=#FF6666>Off the podium, the title leaves your inventory entirely</color> until you climb back into the top 3. You hold it exactly as long as you hold the spot.

Podium titles never rotate on a schedule and can never be bought. The only way in is the top 3.

<color=#FFD94D><b>SLAYER TITLES</b></color>

Two legendary trophies for beating the names on the door:

<color=#7FD4FF>Sid Slayer</color> - win a completed ranked 1v1 series where Sid is the loser. Renders <color=#FF4655>red</color>.
<color=#7FD4FF>Stan Slayer</color> - win a completed ranked 1v1 series where Stan is the loser. Renders <color=#00E5FF>cyan</color>.

Each arrives attached to its achievement, which also pays <color=#7FE87F>1000 gold</color> (see <color=#7FD4FF>Achievement guide</color>). Taking a single game off them isn't enough - the series has to complete with you as the winner.

<color=#FFD94D><b>TRANSLATOR TITLES</b></color>

Verified translation work through the translation portal earns three tiers. The unit is a live string: an approved translation where you were the proposer or the reviewer - doing both jobs on the same string still counts once.

<color=#7FD4FF>Rosetta</color> (rare) - 10 live strings. Pays 100 gold.
<color=#7FD4FF>Dragoman</color> (epic) - 100 live strings. Pays 300 gold.
<color=#7FD4FF>Babel</color> (legendary) - 1000 live strings. Pays 1000 gold.

<color=#FFD94D><b>PURCHASED TITLES</b></color>

Regular titles sit in the shop with a gold price and work like any other cosmetic: buy once, own forever, wear it whenever you feel like it.

<color=#FFD94D><b>EQUIPPING AND WHERE TITLES SHOW</b></color>

- Earned titles (podium, slayer, translator) are hidden from the public shop listing, but every one YOU own appears in your own shop view with its Set Active button. <color=#FF6666>Buying them is always refused</color> - earning the moment is the only currency they accept.
- Equipping a new title replaces the old one; titles never stack.
- Titles show on the mod's own surfaces: the leaderboard, Recent Series, Records, Compare, the stats panels, your T-chat messages (in the title's color), and the Discord chat bridge.
- Titles do NOT appear on the overhead in-game nametag, and players without the mod never see them - every title surface lives in the mod's UI or on Discord.");

        private static string AchievementsP1 => I18n.Tr(@"The mod ships 50 achievements. Each unlocks exactly once per account and pays gold on the spot - <color=#7FE87F>100 gold</color> by default, up to <color=#7FE87F>1000</color> for the hardest; every line below shows its payout. Browse them under <color=#7FD4FF>My Stats - Achievements</color> in the F5 menu: each row shows the condition, your unlock date, the percentage of known mod players who have it, and its gold. Click a row to see who has earned it (the first 500, in unlock order).

<color=#FFD94D><b>HOW THEY ARE CHECKED</b></color>

- Two checkers exist. 14 achievements are judged by your own game the moment a game ends; the other 36 are judged by the server - most when a match, series or rating update lands, the three translator tiers when translation work is approved. <color=#8A8A93>Server-side unlocks can pop a moment after the game - that's normal.</color>
- Client-checked achievements need a real online game. Sandbox, offline play and spectating never award anything.
- Every condition tracker is per-game and resets when a new game starts - a rematch is a clean slate, so damage taken in game 1 can't spoil Untouchable in game 2. (Streak counters, by design, are the exception: they span games.)
- The input trackers (Pacifist, Immovable Object, Grounded) only sample your keys while you are alive and fighting. Card picks, the pick phase and time spent dead never count against you, and neither does typing in the mod's chat or the F5 menu.
- Client-checked achievements run in 1v1, 2v2 and 1v2 games. They never fire from FFA games - FFA has its own six, checked by the server.
- A client-checked <color=#7FD4FF>sweep</color> means you win with the opponent on 0 rounds. In a room set to a shorter round target, a 3-0 still counts. <color=#FF6666>The server-checked 5-0 achievements demand the opponent on 0 with at least 5 rounds won.</color>

<color=#FFD94D><b>CLIENT-CHECKED: PRECISION RUNS</b></color>

- <color=#7FD4FF>Untouchable</color> - win a game in which your health never dropped, even once. <color=#7FE87F>100g</color>
- <color=#7FD4FF>Pacifist</color> - win without ever holding the fire button during live combat. <color=#7FE87F>100g</color>
- <color=#7FD4FF>Immovable Object</color> - win without ever holding a movement or jump key during live combat. <color=#7FE87F>100g</color>
- <color=#7FD4FF>Grounded</color> - win without ever holding a jump key (Space, W, Up). <color=#7FE87F>100g</color>
- <color=#7FD4FF>Instinct</color> - win with 3 or more card picks, taking the pre-highlighted left-most card on every pick without ever moving the selection. <color=#8A8A93>Only checked in queue and sync-tournament rooms - room-code games, async tournament matches included, skip it.</color> <color=#7FE87F>100g</color>

<color=#FFD94D><b>CLIENT-CHECKED: SWEEPS AND STUNTS</b></color>

- <color=#7FD4FF>Silent Assassin</color> - sweep with Sneaky (or Sneaky Bullets) in your build. <color=#7FE87F>100g</color>
- <color=#7FD4FF>Total Mayhem</color> - sweep with Mayhem in your build. <color=#7FE87F>100g</color>
- <color=#7FD4FF>Fragile Perfection</color> - sweep with Glass Cannon in your build. <color=#7FE87F>100g</color>
- <color=#7FD4FF>No Escape</color> - sweep with Chase in your build. <color=#7FE87F>100g</color>
- <color=#7FD4FF>Rise from the Ashes</color> - sweep with Phoenix in your build, without dying and without a Phoenix revive ever firing. <color=#7FE87F>500g</color>
- <color=#7FD4FF>The Comeback Kid</color> - win after the rounds ever stood at you 0, opponent 4 or more. <color=#7FE87F>100g</color>
- <color=#7FD4FF>Stacked Deck</color> - finish a game holding 5 or more copies of one card. No win required. <color=#7FE87F>300g</color>
- <color=#7FD4FF>God Build</color> - win with Shields Up in your build, ending the game on a gun with 1 ammo or less that reloads in 1 second or less. <color=#7FE87F>100g</color>
- <color=#7FD4FF>Into the Deep End</color> - take Abyssal Countdown as your FIRST pick of the game, trigger it in every round, and win. <color=#7FE87F>300g</color>

<color=#FFD94D><b>SERVER-CHECKED 1v1 BUILDS</b></color>

Judged from the reported match. You must be the game's winner unless a line says otherwise.

- <color=#7FD4FF>Bullet Hell</color> - win 5-0 with Barrage in your build. <color=#7FE87F>100g</color>
- <color=#7FD4FF>Spray and Pray</color> - win 5-0 with Spray. <color=#7FE87F>100g</color>
- <color=#7FD4FF>Demolitionist</color> - win 5-0 with Explosive Bullet. <color=#7FE87F>100g</color>
- <color=#7FD4FF>Controlled Burst</color> - win 5-0 with Burst. <color=#7FE87F>100g</color>
- <color=#7FD4FF>Field Medic</color> - win 5-0 with Healing Field. <color=#7FE87F>100g</color>
- <color=#7FD4FF>Double Nova</color> - win with 2 or more Supernovas. <color=#7FE87F>100g</color>
- <color=#7FD4FF>Lumberjack</color> - win with 2 or more Saws. <color=#7FE87F>100g</color>
- <color=#7FD4FF>Pristine Perfection</color> - win with 2 or more copies of Pristine Perseverance. <color=#7FE87F>100g</color>
- <color=#7FD4FF>Living on the Edge</color> - win with 2 or more Glass Cannons. <color=#7FE87F>100g</color>
- <color=#7FD4FF>Silly Drill</color> - win with Sneaky and Drill together. <color=#7FE87F>300g</color>
- <color=#7FD4FF>Sustained Power</color> - win with Empower and Healing Field together. <color=#7FE87F>100g</color>
- <color=#7FD4FF>Collector</color> - win with 4 or more copies of any one card. <color=#7FE87F>100g</color>
- <color=#7FD4FF>Clutch</color> - win after the score ever stood at 0 points for you against 6 or more for the opponent - that is, down 0-3 in rounds. <color=#7FE87F>100g</color>
- <color=#7FD4FF>Twins!</color> - both players finish with exactly 5 cards each and identical builds, copy counts included. Both unlock it; nobody needs to win. <color=#7FE87F>500g</color>");

        private static string AchievementsP2 => I18n.Tr(@"<color=#FFD94D><b>STREAKS</b></color>

All streaks are 1v1-only. Casual streaks count games; ranked streaks count completed series.

- <color=#7FD4FF>Flawless</color> - five 5-0 wins in a row. Ranked and casual both count; <color=#FF6666>any game that isn't a 5-0 win resets it</color>. <color=#7FE87F>300g</color>
- <color=#7FD4FF>Century Club</color> - 100 casual wins in a row. A casual loss resets it; ranked games don't touch the counter. <color=#7FE87F>300g</color>
- <color=#7FD4FF>Casual Conqueror</color> - 200 casual wins in a row. <color=#7FE87F>500g</color>
- <color=#7FD4FF>Touch Grass</color> - 500 casual wins in a row. <color=#7FE87F>1000g</color>
- <color=#7FD4FF>On Fire</color> - win 25 completed ranked series back to back. <color=#7FE87F>100g</color>
- <color=#7FD4FF>Unstoppable</color> - 50 ranked series in a row. <color=#7FE87F>300g</color>
- <color=#7FD4FF>Immortal</color> - 100 ranked series in a row. <color=#7FE87F>500g</color>

<color=#FFD94D><b>RATING, SLAYERS AND 2v2</b></color>

The rating milestones are checked whenever your 1v1 or 2v2 rating updates. FFA rating moves don't trigger them.

- <color=#7FD4FF>Rising Star</color> - reach 1700 rating. <color=#7FE87F>100g</color>
- <color=#7FD4FF>Master</color> - reach 1980 rating. <color=#7FE87F>500g</color>
- <color=#7FD4FF>Grand Master</color> - reach 2330 rating. <color=#7FE87F>1000g</color>
- <color=#7FD4FF>Sid Slayer</color> - win a completed ranked 1v1 series against Sid. Grants the equippable Sid Slayer title. <color=#7FE87F>1000g</color>
- <color=#7FD4FF>Stan Slayer</color> - win a completed ranked 1v1 series against Stan. Grants the Stan Slayer title. <color=#7FE87F>1000g</color>
- <color=#7FD4FF>Tag Team Sweep</color> - win a single 2v2 game 5-0. Both members of the winning team unlock it; it's per game, not per series. <color=#7FE87F>500g</color>

<color=#FFD94D><b>FFA AND TRANSLATOR</b></color>

The FFA six require a RANKED FFA lobby and are all server-checked.

- <color=#7FD4FF>Clean House</color> - win an FFA 5-0: all five points yours and nobody else converts a full point, in a lobby that seated 3 or more players. <color=#7FE87F>100g</color>
- <color=#7FD4FF>Party Crasher</color> - the same with 4 or more seated. <color=#7FE87F>300g</color>
- <color=#7FD4FF>Hostile Takeover</color> - the same with 5 or more seated. <color=#7FE87F>500g</color>
- <color=#7FD4FF>Rampage</color> - over 50 kills in one game. <color=#7FE87F>100g</color>
- <color=#7FD4FF>Bodycount</color> - over 100 kills in one game. <color=#7FE87F>500g</color>
- <color=#7FD4FF>Heartbreak</color> - lose a game holding 10 or more round wins that never became full points. <color=#7FE87F>300g</color>

The shutouts nest: <color=#7FE87F>one 5-player shutout unlocks all three at once, 900 gold total</color>. Seated means the roster when the lobby locked, not who stayed to the end - and losers holding leftover round wins don't break your shutout; only a converted full point does. <color=#8A8A93>Kill counts only register when the game was reported by an up-to-date mod version.</color>

The translator tiers come from the translation portal, not from matches. A live string is an approved translation you proposed or reviewed; doing both jobs on one string counts once. Each tier also grants its matching title (see <color=#7FD4FF>Titles</color>).

- <color=#7FD4FF>Rosetta</color> - 10 live strings. <color=#7FE87F>100g</color>
- <color=#7FD4FF>Dragoman</color> - 100 live strings. <color=#7FE87F>300g</color>
- <color=#7FD4FF>Babel</color> - 1000 live strings. <color=#7FE87F>1000g</color>");

        private static string Cosmetics => I18n.Tr(@"Cosmetics live in the F5 Shop tab and are bought with the gold you earn by playing. This page covers every kind, how each equips, how drops and stock work, and where the art comes from.

<color=#FFD94D><b>WHAT EACH KIND DOES</b></color>

<color=#7FD4FF>Titles</color> - the label beside your name on mod surfaces (see <color=#7FD4FF>Titles</color>).
<color=#7FD4FF>Trails</color> - a colored trail behind your body in matches. Length scales with price: 3,000 gold trails are short, 5,000 medium, 10,000 long.
<color=#7FD4FF>Map skins</color> - recolor the whole map and background. Equip as many as you like and cycle through them mid-game with Left Shift. The catalog holds recolors styled after the six vanilla arts, more than thirty original presets including the night pack, and three premium sparkle skins: Gilded, Platinum and Aurora. <color=#7FE87F>Map skins are yours alone</color> - they're never sent to other players, so every player sees their own pick.
<color=#7FD4FF>Name styling</color> - stackable styling on your display name. Formatting (bold, italic, underline, strike, float) stacks freely; glow, size, font transform and typeface allow one each, and the color effects (solids, neons, rainbow, per-letter gradients) share one slot.
<color=#7FD4FF>Player colors</color> - replace your team orange or blue with a color of your own, and become your team identity on modded screens (see <color=#7FD4FF>Team & body colors</color>).
<color=#7FD4FF>Cursor colors</color> - recolor your mouse cursor. The cursor SHAPE (default, arrow, dot, crosshair, circle) is a free preference. Nobody else ever sees your cursor.
<color=#7FD4FF>Player effects</color> - a particle aura that follows your body in matches.
<color=#7FD4FF>Faces</color> - custom eyes, mouths and accessories that slot into ROUNDS' own character editor next to the vanilla parts, and render everywhere a face renders. Some are animated; the Animated Cosmetics setting pins them to a still frame if you prefer.
<color=#7FD4FF>Hide Gold</color> - a utility toggle that masks your gold on leaderboard surfaces.

<color=#FFD94D><b>EQUIPPING</b></color>

- One at a time: titles, trails, player colors, cursor colors and player effects use <color=#7FD4FF>Set Active</color> / <color=#7FD4FF>Unequip</color>.
- Multi-equip: name styles and map skins use <color=#7FD4FF>Equip</color> / <color=#7FD4FF>Remove</color> - stack your name styles, hold a rotation of skins.
- Hide Gold is an on/off toggle.

<color=#FFD94D><b>WHO SEES WHAT</b></color>

- <color=#7FE87F>The only cosmetic a player WITHOUT the mod can ever see is name styling</color> - styled names ride the same name field vanilla already renders, and putting styling in a name has always been possible in vanilla ROUNDS. Even there, glow and typeface are mod-side extras a vanilla screen can't display.
- Everything else - trails, player colors, auras, faces, map skins - renders only for modded players. A vanilla opponent sees your default body color, no trail, no aura, and an empty slot where a custom face part would be. <color=#8A8A93>The game skips the unknown part cleanly: no crash, nothing substituted.</color>
- Modded viewers can individually turn off other players' trails, player colors and animated cosmetics in Settings.

<color=#FFD94D><b>STOCK, DROPS AND TEASERS</b></color>

- The shop lists everything by price and shows what you own, each item's artist, and stock.
- Community items can be limited: a drop shows N of M left and greys out once sold out.
- An item can exist before its sale opens - it shows as not for sale until the artist opens sales, and brand-new arrivals tease on the Home tab's newest-cosmetics panel first. <color=#FF6666>Seeing an item on Home doesn't mean you can buy it yet.</color>
- You can't buy an item twice, and a purchase you can't afford is refused - no debt, no partial buys.

<color=#FFD94D><b>THE ARTIST STUDIO</b></color>

Community artists make a large share of the catalog. The pipeline:

- An artist (a role granted in-game) submits art from the Artist tab: a PNG or animated frames, positioned on a live on-body preview with slot, scale and offset.
- The submission goes to review. Approval alone doesn't put it on sale: the art has to ship inside a mod release first, because cosmetics are bundled into the mod so every player's game can render them.
- Once shipped, the artist opens sales and controls the price, the stock cap, and who may buy - an artist can block specific players from buying their items.
- The artist earns <color=#7FE87F>a 30% royalty</color> (rounded down to whole Gold) when another player buys their item. No royalty on gifts.

<color=#FFD94D><b>GIFTS</b></color>

Only artists can gift, and only their own items: a free copy to any player who has used the mod, including before sales open. Gifts still consume stock on a limited drop. There is no player-to-player gifting, and no way to send gold to another player.");

        private static string TeamColors => I18n.Tr(@"Body colors in ROUNDS are team colors: the game holds four body skins and picks one by team number. Who gets which color follows from how each mode numbers its teams.

<color=#FFD94D><b>VANILLA 1v1</b></color>

In a 1v1 each player is their own team: the first seat is team 0 and plays <color=#7FD4FF>orange</color>, the second is team 1 and plays <color=#7FD4FF>blue</color>. Vanilla never uses more than these two teams online.

<color=#FFD94D><b>TEAM MODES: 2v2 AND 1v2</b></color>

- <color=#7FD4FF>2v2</color> - the server splits the four players into two pairs when the match locks. Teammates share one body color: orange for the first team, blue for the second.
- <color=#7FD4FF>1v2</color> - the solo player is one team (orange); the duo shares the other (blue).

<color=#FFD94D><b>FFA: TEN PLAYERS, FOUR SKINS</b></color>

In FFA every player is their own team, numbered by lobby slot. ROUNDS ships exactly four body skins, so <color=#FF6666>colors repeat every four players</color>: the 1st, 5th and 9th players share a color, the 2nd, 6th and 10th share the next, and so on. That's deliberate - the mod adds no new skins, and the overhead nametags are what keep same-colored players apart. In a big lobby, read the name, not just the body.

<color=#FFD94D><b>THE CARD-PICK SCREEN</b></color>

The body standing on the pick stage is a clone of the picker's skin. In team modes vanilla has two problems there: a load-order race can bake the WRONG team's color into that clone, and vanilla only ever presents one picker per round even when a losing team has two.

The mod fixes both. It re-checks the real team colors a few frames after the stage appears and retints the body if it came out wrong, and in 2v2 and 1v2 it re-runs the stage for each picker in turn - so every picker appears as themselves, in the right color. FFA doesn't use the vanilla stage at all: everyone picks at the same time on their own screen.

<color=#FFD94D><b>CUSTOM PLAYER COLORS</b></color>

A <color=#7FD4FF>player color</color> cosmetic from the shop (see <color=#7FD4FF>Shop & cosmetics</color>) replaces your team color on every modded player's screen; viewers can opt out with the Show Player Colors setting. Animated specials like Prismatic and Chrome cycle their color about 30 times a second. <color=#7FE87F>Players without the mod keep seeing standard orange and blue - to them your game looks untouched.</color>

On modded screens the color is also your team identity: point announcements call out your color's name (MUSTARD got a point, instead of ORANGE), the round-counter dots and the FFA score strip tint to match, and your in-game nametag tints too - unless a paid nametag color is equipped, which always wins. Identity is resolved from shared data, so everyone with the feature on sees the same names and dots; a player with it off sees vanilla bodies and tints (the custom team NAMES still show).");
    }
}
