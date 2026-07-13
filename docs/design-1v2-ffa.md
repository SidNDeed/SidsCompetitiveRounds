# 1v2 + FFA — groundwork design (July 13)

Status: 1v2 SERVER BUILT + DEPLOYED + curl-tested; 1v2 CLIENT built (first
playtest pending). FFA still design-only (deliberately — see below).

## 1v2 build status (July 13 round 4)

DONE & DEPLOYED (server, migration 120, all curl-verified with test accounts):
- `glicko_ratings_1v2`, `ovt_queue`, `ovt_series`, `ovt_matches`, `ovt_match_cards`.
- Endpoints: `/ovt/queue/join|leave|poll` (poll locks 3 → 1 solo + 2 duo by
  preference, creates series+room), `/ovt/matches` (report, gold+xp, NO rating,
  full replay recording, FOR UPDATE + status re-check per #78, dedup on
  room+players), `/ovt/series/continuation` (recording-gap fix from day one),
  `/ovt/series/active`, `/ovt/leaderboard` (unranked, by games then win%).
- HMAC canonical (10 fields): `solo:duo_a:duo_b:sr:dr:is_ranked:reporter:room:winner_side:series`.

DONE (client, built, compiles):
- `ovt_` rooms are competitive rooms; `playersNeededToStart=3` forced.
- 1v2 tab: queue controls, side preference, solo-extra-pick toggle, live lobby
  status, room auto-join on lock, unranked leaderboard.
- Match-end report routing (`TryReportOvtMatch`) — solo/duo from team sizes.

FIXED after adversarial review (workflow, 16 confirmed findings triaged):
- CRITICAL: ovt_ rooms were created MaxPlayers=2 → 3rd player could never join.
  Now 3 (Plugin.cs QueueJoiner room-options).
- HIGH: queue lock elected the decider from ALL searching rows but locked only
  the 3 earliest — a low-Steam-ID 4th joiner stranded itself. Decider is now
  elected from the same 3 rows it locks (curl-verified with the stranding case).
- HIGH: an ovt_ room with != 3 players at report time fell through to the 1v1
  report path (phantom 1v1 match). The 1v1 fallback is now banned for ANY ovt_
  room regardless of count.
- HIGH: completed 1v2 games polluted the 1v1 session W/L, the 1v1 BO3 "Series:
  X-Y" HUD, and the 1v1 ranked session counters. All 1v1-specific mutations now
  skip ovt_ rooms.
- MEDIUM: a DC in an ovt_ room fired a phantom 1v1 leave-% report against an
  arbitrary opponent. The 1v1 leave-% path now skips multi-player mod rooms
  (team_ and ovt_).
- CONFIRMED: the continuation endpoint had NO client caller (games 2+ of a
  sitting wouldn't record). Now wired (TryRequestOvtContinuationSeries at game
  start, mirroring 2v2).
- Server hardening: reporter-first score on both idempotent early-returns (#121);
  reject empty photon_room_id (NULL bypassed the dedup UNIQUE → double-credit);
  atomic `total_xp = total_xp + delta` (was a lost-update read-modify-write);
  verify the reported trio matches the series players.

THE #1 REMAINING IN-GAME GAP (must wire during first playtest):
- **1v2 does not yet FORCE the 3-player team split (1 solo vs 2 duo).** 2v2
  publishes `p_id`/`t_id` Photon props pre-join and a PlayerAssigner.CreatePlayer
  override reads them so the 4 players land on the right 2 teams. 1v2 has NO
  equivalent yet, so vanilla PlayerAssigner assigns teams by join order — the 3
  players may end up mis-split (or FFA-style on 3 teams) rather than a clean
  1-vs-2. The report LOGIC is correct regardless (it derives solo from whichever
  team has 1 player, and rounds follow the in-game teams), but WHO is solo may
  not match the queue's side preference, and a 3-different-teams split would
  break the game entirely. Wiring: publish side as t_id pre-join (solo→team 0,
  duo→team 1) + an ovt-gated CreatePlayer team override, exactly as 2v2 does.
  This is the first thing to build+test next pass.

FIRST PLAYTEST PENDING (can't validate without playing, like 2v2 was):
- The 3-player join → spawn → play → report loop end to end, once the team-split
  forcing above is wired.

## Why FFA is NOT in this pass (deliberate)

The rolling 5-card bar is untested card-REMOVAL netcode. This doc's own risk
ranking puts "card rebuild correctness" as risk #1 — it's the zombie-delegate
minefield (#92/#103) in a new, harder form (removing + reapplying cards every
pick). Shipping it without the prescribed Sandbox test matrix (Empower, Shield
Charge, Phoenix, Abyssal, Brainwash) would be reckless. 1v2 proved the
parallel-mode plumbing; FFA gets its own focused pass with the card-bar tested
in Sandbox FIRST, then the scoring loop, then public lobbies.

## Sid's decisions (July 13)

1. **1v2 balance**: none by default — 1v2 IS the balance (a strong player
   challenges two weaker ones). Ship one OPTION: the solo may take one extra
   card pick in the INITIAL draw only (lobby toggle, off by default). No
   ongoing handicap — "beyond that makes the 1 player incredibly powerful".
2. **Ranked**: both modes launch unscored, but build full leaderboards/stats
   surfaces AND record everything needed to compute ratings retroactively
   (store per-match results + timestamps + participants from day one; a
   later Glicko replay over the stored history brings ranked up without data
   loss — same pattern as the 2v2 rebuild in learning #76).
3. **FFA series**: single games only. Make that explicit in the UI (queue
   panel + post-game text: "FFA is single games — no series").
4. **FFA player count**: 4 max initially, but ACCEPT 3 (see feasibility below);
   5-6 is a stretch goal — build everything count-parameterized so unlocking
   it is config + testing, not rework.
5. **Rolling card bar**: FFA-only.
6. **Tabs**: separate 1v2 and FFA tabs (not one Multiplayer tab).

## FFA player-count feasibility (answering #4)

Verified against the decompile:
- Vanilla's core loops are `players.Count`-driven (`MovePlayers`, revives,
  spawn sounds even wrap their array) — no hard 4 in the game loop itself.
- `PlayerAssigner.maxPlayers` and `playersNeededToStart` are plain ints we
  already force for 2v2 — 3 or 6 is config.
- **The real 5+ blockers**: (a) `MovePlayers` indexes `spawnPoints[i]` and
  vanilla maps ship 4 SpawnPoints — 5+ players = index-out-of-range, so we'd
  synthesize extra spawn points (clone + offset midpoints; we already own a
  spawn-point sorting patch on that exact array); (b) `PlayerSkinBank` has 4
  skins — slots 5+ reuse colors via our existing GetPlayerSkinColors mapping
  (mitigated visually by body-color cosmetics); (c) our own 4-hardcoded bits
  (CardBars clone count, slot tables, queue lock size) get parameterized;
  (d) gameplay reality: ROUNDS maps are tight for 6 balls — needs playtest
  judgement more than code.
- **Verdict**: launch FFA accepting 3 OR 4 (queue locks at 4 if it can fill,
  else offers a 3-player start after a wait threshold); keep every count as
  a parameter; revisit 5-6 after a tester session on the biggest maps.

---

## What carries over from 2v2 (proven pieces)

| Piece | 2v2 form | Reuse verdict |
|---|---|---|
| Room identity | `cr_ff` Photon room prop + `team_` room-name prefix | New prefixes `ovt_` (1v2) / `ffa_`; keep a shared "mod team room" prop so all the cr_ff-gated client patches fire. Add a `cr_mode` prop = `2v2 \| 1v2 \| ffa` so mode-specific code branches cleanly instead of inferring from player count. |
| Slot identity | `p_id`/`t_id`/`u_id` published PRE-join (no race) | Reuse verbatim. Slot→team comes from a per-mode table, not `slot/2` (see below). |
| Forced start | `playersNeededToStart` forced to 4 | Parameterize: 3 for 1v2, 4 for FFA. |
| Queue + lock | `team_queue` + balancer + `SELECT FOR UPDATE SKIP LOCKED` | Reuse the machinery; new queue types (`1v2`, `ffa`) in the same table. Manual (consent) queues skip rating bands — same rule (learning #127). |
| Reporter election | lowest Steam ID of the room reports | Reuse verbatim. |
| Report dedup | UNIQUE (room, players...) + per-game room suffix | Reuse pattern on the new tables. |
| Series continuation | `/team/series/continuation` (find-or-create rematch series) | Same endpoint shape per mode from day 1 — don't re-learn bug #70. |
| Match-end self-heal | continuation retry + deferred report at match end | Reuse verbatim. |
| Card pick visuals | slot→team skin mapping, face apply, retint | Reuse; FFA maps each slot to a DISTINCT vanilla team skin (0..3 — the bank has 4), which un-does the 2v2 "both teammates same color" mapping for this mode. 1v2: solo=skin0, duo=skin1. |
| Block/delegate sweep | StartGame + ResetCharacters + RPCA_DoBlock scrubs | Reuse verbatim — and the FFA rolling bar DEPENDS on it (below). |
| Tab scoreboard, chat, crown | generic per-player reads | Tab board is already per-player ✓. Crown needs an FFA branch (single leader, not team pair). |

## The hard architectural fact: vanilla scoring is two-team

`GM_ArmsRace` holds exactly `p1Rounds/p2Rounds/p1Points/p2Points` and every
round/game-over path, the round counter UI, and `PointVisualizer` are built on
"team 0 vs team 1".

- **1v2 fits vanilla scoring as-is** (two teams: solo=team0, duo=team1). The
  entire poll/report pipeline works unchanged — 1v2 is honestly ~80% config.
- **FFA does not fit.** Four independent scores can't live in p1/p2. Proposal:
  a mod-owned `FfaScoreTracker` (per-player rounds won, updated from a
  `RoundOver` Postfix reading the surviving player), a Prefix on the
  round/game-over decision that replaces "team X reached N rounds" with "any
  player reached 5 rounds", and an IMGUI score strip (same overlay stack as
  the Tab board) instead of bending `PointVisualizer`. Vanilla's 2-team round
  counter gets hidden in FFA rooms.

## FFA round flow (proposed)

- 4 players, every player their own team (vanilla teamIDs 0–3 — spawn points,
  skins, and damage rules all already handle 4 distinct teams; that's what
  vanilla local 4-player FFA is).
- Round = last player standing wins the round (+1 round tally).
- Game = first to 5 round wins. Reported like a match with 4 per-player round
  tallies.
- Pick phase after each round: **the 3 non-winners pick** (winner doesn't),
  sequential picks using the existing 4-slot syncup flow.

## The rolling 5-card bar (FFA's signature)

Cap every player at 5 cards. When a player with 5 cards picks a 6th, their
OLDEST card is removed first — build identity rotates instead of stacking.

**Mechanism** (no vanilla RemoveCard exists — this is the risky core):

1. Removal = **stat rebuild**: `Player.FullReset()` (new gun + stats + block —
   the exact reset vanilla runs on rematch) followed by re-applying the kept
   cards in order via the same apply path a real pick uses
   (`ApplyCardStats.Pick` on an instantiated `sourceCard`, by reflection),
   with `currentCards` rebuilt to match.
2. Immediately after every rebuild, run the existing zombie-delegate sweep +
   ChildRPC stale-key scrub (learnings #92/#103) — teardown-created zombies
   are THE failure mode of card removal, and we already own the repair tool.
3. **Determinism instead of new netcode**: every client already knows every
   player's card list and pick order (vanilla pick RPCs + `cr_cards` props).
   "Drop the oldest, reapply the rest" is a pure function of that shared
   state, so all 4 clients rebuild identically at the same barrier — the
   existing `WaitForSyncUp` between picks — with zero new RPCs. (Same trust
   model as everything else in the pick pipeline.)
4. Rebuilds happen ONLY during pick phase (players inert, no combat state),
   never mid-round.

**Known edge cases to handle in implementation:**
- Cards that grant extra picks or modify pick counts — the FIFO applies per
  completed pick, order preserved from `currentCards`.
- `objectsAddedToPlayer` is destroyed by `ResetStats` ✓; MaxHealth/respawn
  counters re-derive from the reapplied set ✓; Photon-owned spawned objects
  (turrets etc.) don't exist in vanilla card set — ignore until a card proves
  otherwise.
- A DC during pick phase: rebuild is per-client deterministic, so a rejoin
  resyncs from `cr_cards` (already the 2v2 recovery model).
- Card-stats reporting: `match_cards`-equivalent rows record PICK EVENTS (all
  picks, including rotated-out cards) — the rotation is gameplay, not history.

## 1v2 specifics

- Slot map: slot 0 = solo (team 0), slots 1–2 = duo (team 1). The `slot/2`
  formula from 2v2 is replaced by a per-mode lookup.
- **Balance lever [SID]** — options:
  - (a) none (duo should win; for fun/testing only),
  - (b) **solo picks 2 cards every pick phase** (recommended — pure existing
    machinery, no stat hacks, scales naturally over a game),
  - (c) solo stat handicap (+HP/+damage — tunable but arbitrary),
  - (d) duo shares one combined pick (harshest).
- Queue shapes: solo joins as "the 1", duo joins as a party of 2 (the 2v2
  manual-lobby party flow already pairs friends). Auto-matching random solos
  into the duo side works with the same balancer.

## Server / data model

New tables (mirroring the team_* shapes; FKs to players):

- `ovt_series` / `ovt_matches` — 3 player slots (solo, duo_a, duo_b), same
  status machine, DC grace, continuation, per-slot gold/xp accumulators.
- `ffa_matches` — 4 player slots + per-player rounds won + winner; `ffa_series`
  only if FFA gets series (proposal: **FFA is single-game, no series** — a
  4-player BO3 makes queue-again friction worse than it's worth).
- Ratings **[SID]**: proposal — both modes launch **unranked** (gold/XP only,
  like the 2v2 beta) and get rating pools only after the mechanics settle.
  If/when ranked: 1v2 needs an asymmetric model (solo's rating vs duo avg,
  double K-factor for the solo?) — genuinely new Glicko territory, not a
  copy-paste; FFA fits standard Glicko (each player vs 3 opponents, placement
  as score 1.0/0.0 or graded 1.0/0.66/0.33/0.0).
- HMAC: new canonical strings per endpoint (`ovt:` / `ffa:` prefixed field
  lists). The 1v1 7-field and 2v2 11-field formats stay untouched (rule #5).

## Critical questions — ANSWERED July 13 (see "Sid's decisions" at top)

Resolved: ① no handicap; optional solo extra INITIAL pick only (lobby toggle,
default off). ② unscored launch + full stat recording for retroactive ranked.
③ FFA single games, made explicit in UI. ④ 3-or-4 players at launch,
count-parameterized for 5-6 later. ⑤ rolling bar FFA-only. ⑥ separate tabs.

Implementation notes derived from ①: the "extra initial pick" hooks the
initial-draw pick loop only (GM start pick sequence), never round picks — a
literal +1 iteration for the solo slot when the lobby toggle is on, carried
as a room custom property so all three clients agree.
From ②: `ovt_matches` / `ffa_matches` store per-player rounds, points,
cached ratings-at-time, duration, cards — the full replay surface — plus
leaderboard endpoints (games played, win rate, avg placement for FFA, solo-vs
duo splits for 1v2) reading straight from match rows so no counters need
backfilling when ranked lands.

## Biggest risks, ranked

1. **Card rebuild correctness** (FFA rolling bar) — the zombie-delegate
   minefield. Mitigated by reusing the sweep + pick-phase-only rebuilds, but
   this needs a dedicated Sandbox test matrix (Empower, Shield Charge, Phoenix,
   Abyssal, Brainwash — every card from the #92/#103 incident list) before any
   public lobby sees it.
2. **FFA game-over patching** — replacing two-team win detection without
   destabilizing 1v1/2v2 paths (all patches `cr_mode`-gated, always-on code
   untouched).
3. **UI surface area** — FFA score strip + 4-player pick flow + crown; all
   have 2v2 precedents but each needs an FFA branch.
4. **1v2 is low-risk** — it's config + queue shapes + one balance rule.

## Suggested build order (next pass)

1. 1v2 end-to-end unranked (config-level reuse, fastest win, proves the
   per-mode plumbing: `cr_mode`, slot tables, ovt_* tables, queue type).
2. FFA scoring loop + 4-team rooms, WITHOUT the rolling bar (hard cap at 5
   cards: at 5, a player simply skips pick phase — Sid's fallback idea).
3. Rolling bar as its own tested layer on top (Sandbox matrix first).
