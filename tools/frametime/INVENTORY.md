# FRAME-TIME entry inventory (METHOD-V4 section 3.12, found by operation)

Source: `git grep` over `1c77f580 -- plugin/` in the lane worktree (plugin/Ft*.cs ignored). Every line number is a line of
the 1c77f580 blob. Target signatures were read by reflection from the installed game's
`ROUNDS_Data/Managed/Assembly-CSharp.dll` and `PhotonUnityNetworking.dll` (metadata only; nothing run). Read-only throughout.

## Method and units

- Call sites: every non-comment line outside a component's own files that names `HitEvidence.`, `SeatEvidence.`,
  `PointEvidence.`, `IdentityClockEvidence.`, `CardDrawEvidence.`, `CombatEvidence.` or `PeerBuild.`. One row per line.
  Plugin.cs:3509 is split into two rows because it holds two entries (StageBuildProp, Tick). Doc-comment hits are
  excluded: CombatEvidence.cs:85/117/2246, CombatEvidencePerf.cs:18/56, FfaMode.cs:267, HitEvidence.cs:241/269,
  IdentityClockEvidence.cs:31/689, PeerBuildCore.cs:21, PoisonSync.cs:850, SeatEvidence.cs:610.
- Own files: HitEvidence.cs + HitEvidenceCore.cs; SeatEvidence.cs + SeatEvidenceCore.cs; IdentityClockEvidence.cs +
  IdentityClockCore.cs; CardDrawEvidence.cs + CardDrawEvidenceCore.cs + CardDrawEvidenceTestDealer.cs; CombatEvidence.cs +
  CombatEvidenceCore.cs + CombatEvidencePerf.cs + CombatEvidenceWire.g.cs; PeerBuild.cs + PeerBuildCore.cs.
  PointEvidence has no file of its own: it is the class at PoisonSync.cs:3133-3324 plus its two patch classes at
  PoisonSync.cs:3330-3392. That region counts as its own; the rest of PoisonSync.cs does not (see Excluded).
- No `using` alias or `using static` names any of the seven classes; no `typeof`/`nameof` reference outside their own files.
- Patches: every `[HarmonyPatch]` class in the own files (all are applied by Plugin.cs:1403-1416, one
  `CreateClassProcessor(type).Patch()` per attributed type) plus the one manual `Harmony.Patch` call (IdentityClockEvidence.cs:317).
  No Core/Perf/Wire file carries a patch.
- Live predicate: `SeatEvidence.CombatLive()` (SeatEvidence.cs:675) = `CombatRead.Live(CombatState())`, CombatState
  (SeatEvidence.cs:665-668) reads `GameManager.instance.battleOngoing` and `NetworkReplicaDiagnostics.BattleActive`.

Reach legend:
- **yes**: fires on combat events (damage, shots, hits, blocks, deaths, projectile frames).
- **both**: runs every frame, or on events that occur in and out of combat (RPC traffic, serialize streams).
- **no**: boot, quit, pick phase, or a build/send path that sits behind an existing CombatLive return.
- **boundary**: fires at an edge (combat start, point end, game over, room exit, opponent leave). The CombatLive value at that
  instant is NOT established from repo code; each is one-shot per edge. Counted separately.

Gate column: for yes/both, the first statement of the entry body (where a gate check would go), and any existing guard.

## The ticks (confirmed)

Host: `CompetitiveRoundsBehaviour.Update()` (Plugin.cs:3470; class at Plugin.cs:2471), every frame, all seven ABOVE
`if (Plugin.modDisabled) return;` (Plugin.cs:3530).

| Plugin.cs line | call | in-combat behaviour today |
|---|---|---|
| 3509 | `PeerBuild.StageBuildProp("tick"); PeerBuild.Tick();` | StageBuildProp returns at PeerBuild.cs:68 (staged) or :69 (in a room). Tick has NO combat check: 1 Hz scan in a room (PeerBuild.cs:110-112), a new Dictionary and ToString of every custom property per remote player (:117-129) |
| 3515 | `SeatEvidence.CompatTick();` | returns at SeatEvidence.cs:916 |
| 3524 | `PointEvidence.Drain();` | no check: DrainOwn (PoisonSync.cs:3288, cheap when no record), HitEvidence.Drain (HitEvidence.cs:272), PoisonSync.DrainLateSilences |
| 3525 | `SeatEvidence.Tick();` | `_open` block runs first (SeatEvidence.cs:640-650: ReadOffset reflection each frame, SamplePing every 3 s), then returns at :651 |
| 3526 | `CardDrawEvidence.Tick();` | DrainNotes (CardDrawEvidence.cs:887) runs, then returns at :888 |
| 3527 | `CombatEvidence.Tick();` | CombatEvidencePerf.Frame (CombatEvidence.cs:1681) and TickBody (:1682-1687, the collectors, by design) run, then returns at :1690 |
| 3528 | `IdentityClockEvidence.Tick();` | Slice (IdentityClockEvidence.cs:470; a foreach over all players :509) and a zero-budget survey step (:472) run, then returns at :472 |

## HitEvidence (16)

Call sites:

| ID | entry | site | reach | evidence | gate |
|---|---|---|---|---|---|
| HE-c1 | `HitEvidence.RpcSender` (field read) | CardDrawEvidence.cs:328 | no | in C3 (:320) from EndPick (:240), from the RPCA_DoEndPick prefix: pick phase | - |
| HE-c2 | `ResetForRoomExit(int)` | PoisonSync.cs:3154 | boundary | PointEvidence.ResetForRoomExit, from PoisonSync.ResetForRoomExit (PoisonSync.cs:965) on a room change (:519/:530) | - |
| HE-c3 | `GameEnd(int)` | PoisonSync.cs:3167 | boundary | PointEvidence.GameOverCheck, from the RPCA_NextRound postfix (point end) | - |
| HE-c4 | `PointEnd(int)` | PoisonSync.cs:3270 | boundary | PointEvidence.PointEnd, same postfix | - |
| HE-c5 | `Drain()` | PoisonSync.cs:3284 | both | PointEvidence.Drain, every frame (Plugin.cs:3524) | HitEvidence.cs:274 |

Patches (all applied by attribute; target signature from reflection):

| ID | target, parts | patch at | target shape | patch shape | reach | gate |
|---|---|---|---|---|---|---|
| HE-p1 | `PhotonNetwork.ExecuteRpc` prefix + finalizer (TargetMethod, :359) | HitEvidence.cs:357 | static, 2 args (Hashtable, Player), void | S7: `void Prefix(Hashtable __0, Player __1, out long __state)` + `Exception Finalizer(long __state, Exception __exception)`; no __instance | both (every incoming RPC) | prefix :370 AND finalizer :380. The finalizer restores `RpcSender` and calls `SeatEvidence.ExitRpc(depth)` unconditionally from __state; a prefix-only skip leaving __state 0 would set the RPC context depth to 0 (SeatEvidence.cs:246). CombatEvidence reads that stack (see SE-c CE:322) |
| HE-p2 | `HealthHandler.RPCA_SendTakeDamage` prefix + finalizer | HitEvidence.cs:389 | instance, 5 args (Vector2, Vector2, bool, int, DamageSource), void | S6: `void Prefix(__instance, Vector2 damage, out bool __state)` + `Exception Finalizer(__instance, damage, bool __state, __exception)` | yes | prefix :396, finalizer :405 (finalizer's NoteDamage is unconditional) |
| HE-p3 | `HealthHandler.RPCA_SendTakeForce` finalizer | HitEvidence.cs:413 | instance, 5 args, void | S5: `Exception Finalizer(__instance, Vector2 force, __exception)` | yes | :418 |
| HE-p4 | `HealthHandler.DoDamage` finalizer | HitEvidence.cs:425 | instance, 9 args, void | S5: `Exception Finalizer(__instance, damage, damagingPlayer, healthRemoval, __exception)` | yes | :430 |
| HE-p5 | `Block.RPCA_DoBlock` prefix + finalizer | HitEvidence.cs:440 | instance, 5 args (bool, bool, BlockTriggerType, Vector3, bool), void | S6: `void Prefix(__instance, bool __0, BlockTriggerType __2, bool __4, out int __state)` + `Exception Finalizer(__instance, int __state, __exception)` | yes | prefix :445, finalizer :452 (NoteBlock unconditional) |
| HE-p6 | `ProjectileInit.RPCA_Init` finalizer | HitEvidence.cs:461 | instance, 4 args, void | S5: `Exception Finalizer(__instance, __exception)` | yes | :466 |
| HE-p7 | `ProjectileInit.RPCA_Init_noAmmoUse` finalizer | HitEvidence.cs:473 | instance, 4 args, void | S5 | yes | :478 |
| HE-p8 | `ProjectileInit.RPCA_Init_SeparateGun` finalizer | HitEvidence.cs:485 | instance, 5 args, void | S5 | yes | :490 |
| HE-p9 | `ProjectileHit.RPCA_DoHit` prefix + finalizer | HitEvidence.cs:503 | instance, 6 args (Vector2 x3, int, int, bool), void | S6: `void Prefix(__instance, int __3, bool __5, out long __state)` + `Exception Finalizer(long __state, int viewID, bool wasBlocked, __exception)` (finalizer takes no __instance) | yes | prefix :508, finalizer :517 (NoteImpact unconditional) |
| HE-p10 | `GM_ArmsRace.StartGame` finalizer | HitEvidence.cs:526 | instance, 0 args, void | S5: `Exception Finalizer(Exception __exception)` | boundary (game start) | - |
| HE-p11 | `GM_ArmsRace.DoStartGame` finalizer | HitEvidence.cs:546 | instance, 0 args, returns IEnumerator | S5 on an iterator: runs when the coroutine object is created, not when it ends | boundary (game start, FFA engine only) | - |

## SeatEvidence (60)

Call sites (57 lines):

| ID | entry | site | reach | evidence | gate |
|---|---|---|---|---|---|
| SE-c1 | `NotedEnd` (get) | CardDrawEvidence.cs:603 | no | CardDrawEvidence.Dispatch (:591) | - |
| SE-c2 | `CombatLive()` | CardDrawEvidence.cs:888 | both | CardDrawEvidence.Tick, every frame; it IS the gate | n/a (predicate) |
| SE-c3 | `IdentityReady` | CardDrawEvidence.cs:912 | no | IdentityReadyOrStart (:909) from BuildPending (behind :888) or FlushOnQuit | - |
| SE-c4 | `CompleteIdentityNow()` | CardDrawEvidence.cs:916 | no | same | - |
| SE-c5 | `StartHashing()` | CardDrawEvidence.cs:919 | no | same | - |
| SE-c6 | `StableOf(string)` | CardDrawEvidence.cs:945 | no | BuildPending (:931) | - |
| SE-c7 | `GameDllSha`, `GameDllState` | CardDrawEvidence.cs:963 | no | BuildPending | - |
| SE-c8 | `OwnDllSha`, `OwnDllState` | CardDrawEvidence.cs:964 | no | BuildPending | - |
| SE-c9 | `SpoolClosing("k",..)` or `EnqueueCard(..)` | CardDrawEvidence.cs:979 | no | BuildPending | - |
| SE-c10 | `GameDllState`, `GameDllSha` | CardDrawEvidence.cs:1088 | no | EnsureCensusDump (:1071), behind its returns at :1075/:1076 (never in a room) | - |
| SE-c11 | `ID_PENDING` (const) | CardDrawEvidence.cs:1089 | no | same | - |
| SE-c12 | `CompleteIdentityNow()` | CardDrawEvidence.cs:1094 | no | same | - |
| SE-c13 | `GameDllState`, `GameDllSha` | CardDrawEvidence.cs:1095 | no | same | - |
| SE-c14 | `SwMs` (get) | CombatEvidence.cs:81 | both | CombatEvidence's clock wrapper, read by every CombatEvidence hook and the tick | n/a (clock read, SeatEvidence.cs:42) |
| SE-c15 | `RpcTop(out x4)` | CombatEvidence.cs:322 | yes | CombatEvidence.RpcTop wrapper (:320), called from hook bodies :487 :560 :722 :1101 :1258 :1279 :1360 :1418 :1532; reads the stack HE-p1 maintains | SeatEvidence.cs:253; the CombatEvidence hooks are already guarded (see CE patches) |
| SE-c16 | `CombatLive()` | CombatEvidence.cs:1690 | both | CombatEvidence.Tick, every frame; the gate | n/a (predicate) |
| SE-c17 | `CombatLive()` | CombatEvidence.cs:1703 | both | TickBody, every frame while `_open && !PerfSuspend` | n/a (predicate) |
| SE-c18 | `FROZEN_MS` (const, compiled to a literal) | CombatEvidence.cs:2255 | no | CombatEvidence.Dispatch (:2250) | - |
| SE-c19 | `IdentityReady` | CombatEvidence.cs:2440 | no | BuildCaptures (:2435), from Tick behind :1690 or FlushOnQuit | - |
| SE-c20 | `CompleteIdentityNow()` | CombatEvidence.cs:2443 | no | same | - |
| SE-c21 | `StartHashing()` | CombatEvidence.cs:2444 | no | same | - |
| SE-c22 | `StableOf(string)` | CombatEvidence.cs:2452 | no | same | - |
| SE-c23 | `SpoolClosing("x",..)` or `EnqueueCombat(..)` | CombatEvidence.cs:2480 | no | same | - |
| SE-c24 | `CombatLive()` | CombatEvidencePerf.cs:142 | both | MatchFrame, every frame via CombatEvidence.Tick :1681 | n/a (predicate) |
| SE-c25 | `NoteEnd(string)` | GameStateWatcher.cs:3851 | boundary | PollRoomState (:3413), local room-left branch | - |
| SE-c26 | `ClearEnd()` | GameStateWatcher.cs:4389 | boundary | PollRoomState, opponent returned to the room | - |
| SE-c27 | `NoteEnd("other_left")` | GameStateWatcher.cs:4396 | boundary | PollRoomState, opponent left; can be mid-point | (one-shot) SeatEvidence.cs:108 |
| SE-c28 | `BeginGame(bool, bool)` | GameStateWatcher.cs:5873 | boundary | OnMatchStarted (:5697), fired at "MOVE PLAYERS END" = combat start (:8800-8810) or by the score fallback (:5088-5090) | (one-shot; gating it would skip the window open) SeatEvidence.cs:72 |
| SE-c29 | `Dispatch(..)` | GameStateWatcher.cs:6873 | boundary | OnGameOver (:6070) | - |
| SE-c30 | `Dispatch(..)` | GameStateWatcher.cs:9399 | boundary | SeatEvidenceCut (:9392): room left with the game cut short (:3945) or quit (:9419) | - |
| SE-c31 | `NoteEnd("closing")` | GameStateWatcher.cs:9418 | no | SeatEvidenceOnQuit (:9413), Application.quitting | - |
| SE-c32 | `AddPush(..)` | HitEvidence.cs:331 | both | PushToSeatEvidence from HitEvidence.Drain (per frame); runs only while a point/game flush is held (set at point end) | SeatEvidence.cs:614 |
| SE-c33 | `RoomExit()` | HitEvidence.cs:344 | boundary | HitEvidence.ResetForRoomExit | - |
| SE-c34 | `EnterRpc(Hashtable, Player)` | HitEvidence.cs:372 | both | HE-p1 prefix, every incoming RPC; maintains the RPC context stack before any `_open` check (struct Ctx, :221) | SeatEvidence.cs:218 (see HE-p1: must stay paired with SE-c35) |
| SE-c35 | `ExitRpc(int)` | HitEvidence.cs:381 | both | HE-p1 finalizer | SeatEvidence.cs:246 |
| SE-c36 | `DamageGate(..)` | HitEvidence.cs:397 | yes | HE-p2 prefix | SeatEvidence.cs:533 |
| SE-c37 | `DamageArrived(..)` | HitEvidence.cs:406 | yes | HE-p2 finalizer | SeatEvidence.cs:550 |
| SE-c38 | `BlockEnter(..)` | HitEvidence.cs:446 | yes | HE-p5 prefix | SeatEvidence.cs:325 (existing `_open` check :327) |
| SE-c39 | `BlockExit(int)` | HitEvidence.cs:453 | yes | HE-p5 finalizer | SeatEvidence.cs:376 |
| SE-c40 | `ShotArrived(.., 0)` | HitEvidence.cs:467 | yes | HE-p6 | SeatEvidence.cs:583 (existing :585) |
| SE-c41 | `ShotArrived(.., 1)` | HitEvidence.cs:479 | yes | HE-p7 | same |
| SE-c42 | `ShotArrived(.., 2)` | HitEvidence.cs:491 | yes | HE-p8 | same |
| SE-c43 | `HitEnter(..)` | HitEvidence.cs:510 | yes | HE-p9 prefix | SeatEvidence.cs:465 (existing :467) |
| SE-c44 | `HitExit(int)` | HitEvidence.cs:518 | yes | HE-p9 finalizer | SeatEvidence.cs:510 |
| SE-c45 | `CombatState()` | IdentityClockEvidence.cs:467 | both | IdentityClockEvidence.Tick, every frame | n/a (predicate) |
| SE-c46 | `CombatState` (method group) | IdentityClockEvidence.cs:569 | no | RequestSurvey (:558), only when picking and not combat (:496). The delegate goes to WitnessFs; survey steps run in combat with a zero budget (:472) | - |
| SE-c47 | `EnqueueIdentity(string)` | IdentityClockEvidence.cs:663 | no | BuildCaptures (:645), behind :472 | - |
| SE-c48 | `SpoolClosing("i", env)` (lambda) | IdentityClockEvidence.cs:699 | no | FlushOnQuit (:695) | - |
| SE-c49 | `StableOf(string)` | IdentityClockEvidence.cs:725 | no | BuildEnv (:720), build path | - |
| SE-c50 | `NoteView(int, int)` | NetworkReplicaDiagnostics.cs:146 | both | CommitTiming, from RecordMovementSample (:313, :339) and Observe (:781, :858): every remote movement sample | SeatEvidence.cs:288 (existing `_open` check :290) |
| SE-c51 | `FlushOnQuit()` | Plugin.cs:539 | no | Application.quitting | - |
| SE-c52 | `CompatTick()` | Plugin.cs:3515 | both | the tick | SeatEvidence.cs:914 (existing return :916) |
| SE-c53 | `Tick()` | Plugin.cs:3525 | both | the tick | SeatEvidence.cs:637 (existing return :651 sits after the `_open` block :640-650) |
| SE-c54 | `StartHashing()` | Plugin.cs:3786 | no | DoInitialize (:3781), boot | - |
| SE-c55 | `NoteCompat("finding", ..)` | Plugin.cs:3810 | no | DoInitialize | - |
| SE-c56 | `NoteCompat("pass", null)` | Plugin.cs:3860 | no | DoInitialize | - |
| SE-c57 | `NoteCompat("not_run", null)` | Plugin.cs:3867 | no | DoInitialize | - |

Patches:

| ID | target, parts | patch at | target shape | patch shape | reach | gate |
|---|---|---|---|---|---|---|
| SE-p1 | `PhotonNetwork.RPC` postfix (TargetMethod :1825, the 6-arg overload; two 5-arg overloads also exist) | SeatEvidence.cs:1823 | static, 6 args (PhotonView, string, RpcTarget, Player, bool, object[]), void | S3: `void Postfix(PhotonView __0, string __1, RpcTarget __2)`; no __instance | both (every outgoing RPC); also carries CE-c8 | :1836 |
| SE-p2 | `Block.DoBlock` finalizer | SeatEvidence.cs:1843 | instance, 3 args, void | S5: `Exception Finalizer(__instance, __exception)` | yes | :1848 (UnkeyedReset already returns on `!_open`, SeatEvidence.cs:430) |
| SE-p3 | `Block.TryBlockMe` finalizer | SeatEvidence.cs:1854 | instance, 3 args, returns bool (__result not used) | S5 | yes | :1859 |

## PointEvidence (9)

Call sites:

| ID | entry | site | reach | evidence | gate |
|---|---|---|---|---|---|
| PT-c1 | `Point` (get) | CombatEvidence.cs:1749 | yes | CombatEvidence.PointStart, from TickBody :1706 on the first live frame of each point | n/a (field read, PoisonSync.cs:3149) |
| PT-c2 | `Point` (get) | HitEvidence.cs:531 | boundary | HE-p10 (game start) | - |
| PT-c3 | `Point` (get) | HitEvidence.cs:551 | boundary | HE-p11 (game start, FFA) | - |
| PT-c4 | `Drain()` | Plugin.cs:537 | no | Application.quitting | - |
| PT-c5 | `Drain()` | Plugin.cs:3524 | both | the tick | PoisonSync.cs:3283 |
| PT-c6 | `ResetForRoomExit()` | PoisonSync.cs:965 | boundary | PoisonSync.ResetForRoomExit (:955) on a room change (:519/:530) | - |
| PT-c7 | `ObservedRounds++` (field write) | SpectatorPatches.cs:269 | boundary | Spectator_ObserveNextRound_Patch prefix on RPCA_NextRound, spectator seats only (fighters return at :247) | - |

Patches:

| ID | target, parts | patch at | target shape | patch shape | reach | gate |
|---|---|---|---|---|---|---|
| PT-p1 | `Saw.Update` prefix + finalizer | PoisonSync.cs:3331 | instance, 0 args, void | S11: `void Before()` + `Exception After(Exception __exception)`; no __state, no __instance | both (every saw, every frame; scans up to 64 players twice) | prefix :3334 (one-line body), finalizer :3339 |
| PT-p2 | `GM_ArmsRace.RPCA_NextRound(int x6)` prefix (Priority.First + 1) + postfix | PoisonSync.cs:3354 | instance, 6 int args, void | S10: `void Snap(__instance, out Before __state)` (struct state) + `void After(__instance, Before __state, bool __runOriginal)` | boundary (point end) | - |

## IdentityClockEvidence (15)

Call sites:

| ID | entry | site | reach | evidence | gate |
|---|---|---|---|---|---|
| IC-c1 | `BeginGame(bool, bool)` | GameStateWatcher.cs:5877 | boundary | OnMatchStarted, as SE-c28; also runs `PostBoot.ArmFromFile()` (:148: a File.Exists each game) | (one-shot) IdentityClockEvidence.cs:140 |
| IC-c2 | `Dispatch(..)` | GameStateWatcher.cs:6883 | boundary | OnGameOver | - |
| IC-c3 | `Dispatch(..)` | GameStateWatcher.cs:9405 | boundary | SeatEvidenceCut | - |
| IC-c4 | `FlushOnQuit()` | Plugin.cs:542 | no | quitting | - |
| IC-c5 | `BootLine()` | Plugin.cs:1426 | no | Awake, after the patch loop | - |
| IC-c6 | `Tick()` | Plugin.cs:3528 | both | the tick | IdentityClockEvidence.cs:461 (existing combat return :472 sits after Slice :470) |
| IC-c7 | `BootCheck("finding", ..)` | Plugin.cs:3812 | no | DoInitialize | - |
| IC-c8 | `BootCheck("pass", null)` | Plugin.cs:3861 | no | DoInitialize | - |
| IC-c9 | `BootCheck("not_run", null)` | Plugin.cs:3868 | no | DoInitialize | - |
| IC-c10 | `ClockHeaderNow` (method group) | SeatEvidence.cs:1649 | no | Pump (:1629), behind SeatEvidence.cs:651 | - |

Patches:

| ID | target, parts | patch at | target shape | patch shape | reach | gate |
|---|---|---|---|---|---|---|
| IC-p1 | `PhotonNetwork.ExecuteRpc` prefix + finalizer (TargetMethod :801) | IdentityClockEvidence.cs:799 | static, 2 args, void | S7: `void Prefix(Hashtable __0, Player __1, out int __state)` + `Exception Finalizer(int __state, __exception)` | both | prefix :812, finalizer :819 (__state -1 makes ExitRpc a no-op, :376) |
| IC-p2 | `MapManager.RPCA_CallInNewMapAndMovePlayers` prefix | IdentityClockEvidence.cs:826 | instance, 1 arg (int), void | S1: `void Prefix()` | boundary (point start) | - |
| IC-p3 | `PlayerManager.MovePlayers` prefix | IdentityClockEvidence.cs:837 | instance, 1 arg (SpawnPoint[]), void | S1: `void Prefix(SpawnPoint[] __0)` | boundary (point start, before "MOVE PLAYERS END") | - |
| IC-p4 | `SyncPlayerMovement.OnPhotonSerializeView` prefix + postfix | IdentityClockEvidence.cs:848 | instance, 2 args (PhotonStream, PhotonMessageInfo by value), void | S8: `void Prefix(__instance, PhotonStream __0, out int __state)` + `void Postfix(__instance, PhotonMessageInfo __1, int __state)` | both (every player serialize) | prefix :853, postfix :866 (already returns on __state < 0) |
| IC-p5 | manual `new Harmony("scr.ic.postboot").Patch(target, postfix: Noop)` | IdentityClockEvidence.cs:317 | any DEPENDENCY target (:231-237; includes MoveTransform.Update, GeneralInput.Update, PhotonHandler.FixedUpdate) | S14: `static void Noop()` | both, ONLY if `BepInEx/config/scr-ic-postboot.txt` exists (test fixture; armed from BeginGame, so a Harmony.Patch at combat start) | n/a (test seam) |

## CardDrawEvidence (16)

Call sites:

| ID | entry | site | reach | evidence | gate |
|---|---|---|---|---|---|
| CD-c1 | `Dispatch(..)` | GameStateWatcher.cs:6879 | boundary | OnGameOver | - |
| CD-c2 | `Dispatch(..)` | GameStateWatcher.cs:9402 | boundary | SeatEvidenceCut | - |
| CD-c3 | `RoomExit()` | HitEvidence.cs:345 | boundary | HitEvidence.ResetForRoomExit | - |
| CD-c4 | `FlushOnQuit()` | Plugin.cs:540 | no | quitting | - |
| CD-c5 | `BootLine()` | Plugin.cs:1422 | no | Awake | - |
| CD-c6 | `Tick()` | Plugin.cs:3526 | both | the tick | CardDrawEvidence.cs:885 (DrainNotes :887 runs before the existing return :888) |
| CD-c7 | `EnsureCensusDump()` | Plugin.cs:3643 | both | Update, every frame | CardDrawEvidence.cs:1073 (already returns at :1075 once done, :1076 in a room) |
| CD-c8 | `FreezeRoomFacts()` | Plugin.cs:5704 | boundary | OnDisconnected (:5632) | - |
| CD-c9 | `FreezeRoomFacts()` | Plugin.cs:6431 | boundary | OnLeftRoom (:6411) | - |

Patches:

| ID | target, parts | patch at | target shape | patch shape | reach | gate |
|---|---|---|---|---|---|---|
| CD-p1 | `CardChoice.StartPick` postfix (Priority.Last) | CardDrawEvidence.cs:1157 | instance, 2 args, void | S2: `void Postfix(__instance)` | no (pick phase) | - |
| CD-p2 | `CardInfo.Awake` postfix | CardDrawEvidence.cs:1169 | instance, 0 args, void | S2: `void Postfix(__instance)` | no (expected: card objects spawn in the pick phase; if a card visual is ever instantiated mid-point, CardAwake returns at :233 unless a pick hook is open) | - |
| CD-p3 | `CardChoice.RPCA_DoEndPick` prefix | CardDrawEvidence.cs:1180 | instance, 4 args (int[], int, int, int), void | S1: `void Prefix(int[] __0, int __1, int __2, int __3)` | no | - |
| CD-p4 | `CardChoice.RPCA_DonePicking` prefix | CardDrawEvidence.cs:1191 | instance, 0 args, void | S1: `void Prefix()` | no | - |
| CD-p5 | `ApplyCardStats.RPCA_Pick` postfix + finalizer (Priority.Last) | CardDrawEvidence.cs:1207 | instance, 1 arg (int[]), void | S12: `void Postfix(__instance, int[] __0, bool __runOriginal)` + `Exception Finalizer(__instance, int[] __0, __exception)` | no | - |
| CD-p6 | `ApplyCardStats.OFFLINE_Pick` postfix + finalizer (Priority.Last) | CardDrawEvidence.cs:1227 | instance, 1 arg (Player[]), void | S12 | no | - |
| CD-p7 | `CardChoice.SpawnUniqueCard` prefix (Priority.Last) | CardDrawEvidenceTestDealer.cs:51 | instance, 2 args (Vector3, Quaternion), returns GameObject | S13: `bool Prefix(__instance, pos, rot, ref GameObject __result, bool __runOriginal)` (skipping prefix) | no; NOT COMPILED: the file is `#if SCR_CARD_EVIDENCE_TEST_DEALER`, which no configuration defines | - |

## CombatEvidence (27)

Call sites:

| ID | entry | site | reach | evidence | gate |
|---|---|---|---|---|---|
| CE-c1 | `BeginGame(bool)` | GameStateWatcher.cs:5875 | boundary | OnMatchStarted, as SE-c28; allocates the per-game `Game` (CombatEvidence.cs:103) | (one-shot) CombatEvidence.cs:90 |
| CE-c2 | `Dispatch(..)` | GameStateWatcher.cs:6881 | boundary | OnGameOver | - |
| CE-c3 | `Dispatch(..)` | GameStateWatcher.cs:9403 | boundary | SeatEvidenceCut | - |
| CE-c4 | `RoomExit()` | HitEvidence.cs:346 | boundary | HitEvidence.ResetForRoomExit | - |
| CE-c5 | `FlushOnQuit()` | Plugin.cs:541 | no | quitting | - |
| CE-c6 | `BootLine()` | Plugin.cs:1425 | no | Awake | - |
| CE-c7 | `Tick()` | Plugin.cs:3527 | both | the tick | CombatEvidence.cs:1681 (Perf.Frame :1681 and TickBody :1682-1687 run in combat; existing return :1690) |
| CE-c8 | `RpcSent(PhotonView, string, RpcTarget)` | SeatEvidence.cs:1837 | both | SE-p1 postfix, every outgoing RPC | CombatEvidence.cs:424 (existing `if (!_open or PerfSuspend) return;`) |

Patches. Every CombatEvidence enter method already starts with `if (!_open || PerfSuspend) return` (CombatEvidence.cs:424 464 543 656 695 856 1040 1080 1133 1222 1242 1307 1340 1403 1514 1580 1640) and every exit method returns on `!_open` or a zero state (498 608 820 886 1172 1373 1456 1551), so a gate placed beside the PerfSuspend guard also silences the exits.

| ID | target, parts | patch at | target shape | patch shape | reach | gate (patch body; existing guard) |
|---|---|---|---|---|---|---|
| CE-p1 | `Gun.Attack` prefix + postfix | CombatEvidence.cs:2636 | instance, 5 args, returns bool | S9: `void Prefix(__instance, bool forceAttack, bool useAmmo, out long __state)` + `void Postfix(__instance, bool __result, bool forceAttack, long __state)` | yes | :2641 / :2648; guard :464, exit :498 |
| CE-p2 | `ProjectileInit.RPCA_Init` prefix + finalizer | CombatEvidence.cs:2654 | instance, 4 args, void | S6 (`out int __state`) | yes | :2659 / :2666; guard :543, exit :608 |
| CE-p3 | `ProjectileInit.RPCA_Init_noAmmoUse` prefix | CombatEvidence.cs:2672 | instance, 4 args, void | S1: `void Prefix(__instance, int senderID)` | yes | :2677; guard :543 |
| CE-p4 | `ProjectileInit.RPCA_Init_SeparateGun` prefix | CombatEvidence.cs:2682 | instance, 5 args, void | S1 | yes | :2687; guard :543 |
| CE-p5 | `GunAmmo.ReloadAmmo` prefix | CombatEvidence.cs:2693 | instance, 1 arg (bool), void | S1: `void Prefix(__instance, bool playSound)` | yes | :2698; guard :656 |
| CE-p6 | `ProjectileHit.RPCA_DoHit` prefix + finalizer | CombatEvidence.cs:2705 | instance, 6 args, void | S6 (`out long __state`; prefix takes hitPoint, vel, viewID, wasBlocked by name) | yes | :2710 / :2717; guard :695, exit :820 |
| CE-p7 | `ProjectileHit.Hit` prefix | CombatEvidence.cs:2724 | instance, 2 args (HitInfo, bool), void | S1: `void Prefix(__instance, HitInfo hit)` | yes | :2729; guard :1040 |
| CE-p8 | `Block.RPCA_DoBlock` finalizer | CombatEvidence.cs:2735 | instance, 5 args, void | S5: `Exception Finalizer(__instance, __exception)` | yes | :2740; guard :1080 |
| CE-p9 | `Block.TryBlock` prefix + postfix | CombatEvidence.cs:2747 | instance, 0 args, void | S8: `void Prefix(__instance, out long __state)` + `void Postfix(__instance, long __state)` | yes | :2752 / :2759; guard :1133, exit :1172 |
| CE-p10 | `CharacterStatModifiers.DealtDamage` postfix | CombatEvidence.cs:2765 | instance, 3 args, void | S2: `void Postfix(__instance)` | yes | :2770; guard :1222 |
| CE-p11 | `BounceEffectRetarget.SetNewVel` prefix | CombatEvidence.cs:2776 | instance, 1 arg (Vector2), void | S1: `void Prefix(__instance, Vector2 newVel)` | yes | :2781; guard :1242 |
| CE-p12 | `ScreenEdgeBounce.DoHit` prefix + finalizer | CombatEvidence.cs:2787 | instance, 4 args, void | S6 (`out long __state`) | yes | :2792 / :2799; guard :1340, exit :1373 |
| CE-p13 | `SyncProjectile.OnPhotonSerializeView` postfix | CombatEvidence.cs:2806 | instance, 2 args (PhotonStream, PhotonMessageInfo), void | S2: `void Postfix(__instance, PhotonStream stream)` | yes | :2811; guard :1640 |
| CE-p14 | `HealthHandler.RPCA_SendTakeForce` prefix + finalizer | CombatEvidence.cs:2817 | instance, 5 args, void | S6 (`out long __state`) | yes | :2822 / :2829; guard :1403, exit :1456 |
| CE-p15 | `HealthHandler.RPCA_SendTakeDamage` prefix + finalizer | CombatEvidence.cs:2836 | instance, 5 args, void | S6 (`out long __state`; prefix takes damage and damageSource by name) | yes | :2841 / :2848; guard :1514, exit :1551 |
| CE-p16 | `HealthHandler.RPCA_Die` prefix | CombatEvidence.cs:2855 | instance, 1 arg (Vector2), void | S1: `void Prefix(__instance)` | yes | :2860; guard :1580 |
| CE-p17 | `HealthHandler.RPCA_Die_Phoenix` prefix | CombatEvidence.cs:2866 | instance, 1 arg, void | S1 | yes | :2871; guard :1580 |
| CE-p18 | `BounceEffectRetarget.FindTarget` postfix | CombatEvidence.cs:2877 | instance, 1 arg (HitInfo), returns Player | S4: `void Postfix(__instance, HitInfo hit, Player __result)` | yes | :2882; guard :1307 |
| CE-p19 | `MoveTransform.Update` prefix + finalizer | CombatEvidence.cs:2889 | instance, 0 args, void | S6 (`out long __state`) | yes (every projectile, every frame: the hottest entry) | :2894 / :2901; guard :856, exit :886 |

## PeerBuild (4)

| ID | entry | site | reach | evidence | gate |
|---|---|---|---|---|---|
| PB-c1 | `BuildValue()` | CardDrawEvidence.cs:966 | no | BuildPending | - |
| PB-c2 | `StageBuildProp(string)` | Plugin.cs:3509 | both | the tick | PeerBuild.cs:66 (already returns at :68 once staged, :69 in a room) |
| PB-c3 | `Tick()` | Plugin.cs:3509 | both | the tick; no combat check at all | PeerBuild.cs:103 (before the try; first test :105) |
| PB-c4 | `BuildValue()` | SeatEvidence.cs:1163 | no | Aggregate (:1155) from BuildCaptures, behind SeatEvidence.cs:651 | - |

No PeerBuild patch exists.

## Coupling the gate must respect (found while tracing)

1. CombatEvidence's hooks key on SeatEvidence's RPC context stack (CombatEvidence.cs:322 into SeatEvidence.RpcTop :251), and that
   stack is pushed and popped only by HitEvidence's ExecuteRpc patch (HitEvidence.cs:372/381). Gating HitEvidence in combat while
   CombatEvidence collects would silently unkey every CombatEvidence hook.
2. CombatEvidence.RpcSent rides SeatEvidence's PhotonNetwork.RPC postfix (SeatEvidence.cs:1837).
3. HE-p1's finalizer writes `RpcSender` and the stack depth back from __state unconditionally (HitEvidence.cs:380-381); a skipped
   prefix must leave a sentinel (depth -1), not 0.
4. Two patches decode every incoming RPC hashtable independently: HE-p1 (through SeatEvidence.EnterRpc) and IC-p1.
5. The live predicate is evaluated up to seven times per frame (SeatEvidence.cs:651, :916; CardDrawEvidence.cs:888;
   CombatEvidence.cs:1690, :1703; CombatEvidencePerf.cs:142; IdentityClockEvidence.cs:467), so ticks can disagree inside one
   frame. CardDrawEvidence keeps a separate battleOngoing-only read for cost attribution (CardDrawEvidence.cs:160-164).

## Class iii: per-game state that survives a point reset and is read by live loops

| # | state | defined | reset | live loop that reads it | bound per call |
|---|---|---|---|---|---|
| 1 | CombatEvidence `Game.Top` / `TopN` (and `P3topSeen`) | CombatEvidence.cs:208 (:207) | only by a new `Game` at BeginGame (:103); PointStart/PointEnd/PointReset (:1745-1785) never touch it | TopInsert (:2168) loops :2171 and :2174, from DrainResiduals (:2124, insert at :2162), from TickBody :1741 every frame while `_open && !PerfSuspend` | up to 32 compares + 32 `Array.Copy` of 8 longs per residual row, up to 16 rows per frame (TOP_CAP = ROWS_CAP = 32, TICK_ROWS_CAP = 16) |
| 2 | CombatEvidence `Game.Ht` / `HtN` | CombatEvidence.cs:209 | same | HtUpsert (:2213) loops :2215 and :2219, from DrainPackages (:2179, call :2206), TickBody :1742 | up to 16 + 16 `Array.Copy` per package, up to 16 packages per frame (HT_CAP 16) |
| 3 | CombatEvidence `Game.PingBin` / `PingN` | Game class (filled at :1731-1735) | per game only | LHatMs (:1880) loop :1884 over 2001 bins (PING_BIN_CAP 2000), from DrainAim :1956 every 5 s, TickBody :1740 | 2001 iterations per refresh |
| 4 | CombatEvidence static `_lHatCache` / `_lHatAtMs` | CombatEvidence.cs:1892 | never reset, not even at BeginGame: survives games | DrainAim :1956-1957 every frame | the previous game's L^ is used for up to 5 s into the next game |
| 5 | CombatEvidence `Game.PosN` / `PosHead` / `PosT` / `PosX` / `PosY` ring | filled at :1721-1726 | per game only (PointStart does not clear it) | DrainAim loop :1978 for each own-aim row | up to 64 per row, up to 16 rows per frame (POS_CAP 64) |
| 6 | CombatEvidence `Game.B5c` rows (`Count`) | Game class (:202) | per game only | FillContact (:1011) loops :1016 and :1021, from HitBody :759 in the RPCA_DoHit prefix | up to 8 + 64 rows per hit (PAIR_CAP, OUTSIDE_SCAN_CAP) |
| 7 | SeatEvidence `_winRecv` / `_winSent` (HitWindow `Pending`, `RecentBlocks`) | SeatEvidence.cs:141 | only ResetGame :183 (BeginGame :74) | HitWindow.Offer loop SeatEvidenceCore.cs:584 (from SeatEvidence.cs:483, :495, :519) and HitWindow.Block loop SeatEvidenceCore.cs:605 (from SeatEvidence.cs:342, :394, :419 via Admit :442); `Pending.RemoveAt(0)` at the cap (SeatEvidenceCore.cs:590) shifts the list; Block allocates a new List per call (:601) | up to 8 (Offer) and 64 (Block) per hook |
| 8 | IdentityClockEvidence `Game.Rpc` (RpcNames) | IdentityClockEvidence.cs:125 | per game only | `RpcNames.Add` does `_names.IndexOf` (IdentityClockCore.cs:1383) on every opponent RPC, from EnterRpc :364 (IC-p1 prefix) | linear over up to 128 strings (KEEP) per RPC |
| 9 | IdentityClockEvidence `Game.Book` (ClockBook cadence state `_bucket`, `_gapHist`, `_tdHist`, `CadB`) | IdentityClockCore.cs:1077-1098 | per game only | ClockBook.Package (:1146) from IC-p4 postfix: Cadence (:1171) calls FlushBucket (:1198) on each 10 s bucket change, which runs Median (:1213) over 1001 + 101 bins and two Array.Clear | a periodic spike every 10 s inside a serialize hook (BUCKET_MS 10000, TD_CEIL_MS 100) |

Considered and not class iii: CombatEvidence `GunState.Ring` (not cleared by PointReset :1780-1785, but drained at PointEnd :1775);
HitEvidence `_game` and `_projAmmo` (per game, cleared in GameEnd HitEvidence.cs:266; read in live hooks by O(1) lookup, no loop);
SeatEvidence `_hitRecv` / `_hitSent` EventLists (append-only, O(1), SeatEvidenceCore.cs:488); IdentityClock `PtO` / `PtS` (appended
only at point start); PointEvidence `_sawLost` / `_before` (cleared each point and each Saw frame).

## Excluded from the inventory (and why)

- PoisonSync's own patches in PointEvidence's host file: PoisonReviveFencePatch (PoisonSync.cs:2970), PoisonDotSchedulerPatch
  (:3030), PoisonPointBoundaryPatch (:3395), PoisonRpcStampPatch (:3432), PoisonPhoenixBoundaryPatch (:3490), PoisonDeathFlushPatch
  (:3526), PoisonHitBracketPatch (:3553), PoisonArmPatch (:3582). They are gameplay sync, not evidence, and none of them names any
  of the seven classes. Include them only if section 3.12 means "every patch in the file" literally.
- Doc-comment mentions (listed under Method).

## Patch shapes (by signature form)

No target takes a by-ref argument (reflection shows none). By-ref appears only in the patches: `out __state` (S6 to S10) and
`ref GameObject __result` (S13). Static targets: PhotonNetwork.ExecuteRpc and PhotonNetwork.RPC (6-arg); every other target is an
instance method. Non-void targets: Gun.Attack (bool), Block.TryBlockMe (bool), BounceEffectRetarget.FindTarget (Player),
GM_ArmsRace.DoStartGame (IEnumerator), CardChoice.SpawnUniqueCard (GameObject).

| shape | signature form | target | members | n |
|---|---|---|---|---|
| S1 | `static void Prefix(args)`, no __state | instance, void | IC-p2, IC-p3, CD-p3, CD-p4, CE-p3, CE-p4, CE-p5, CE-p7, CE-p11, CE-p16, CE-p17 | 11 |
| S2 | `static void Postfix(__instance[, args])` | instance, void | CD-p1, CD-p2, CE-p10, CE-p13 | 4 |
| S3 | `static void Postfix(__0, __1, __2)`, no __instance | static, void | SE-p1 | 1 |
| S4 | `static void Postfix(__instance, args, R __result)` | instance, non-void | CE-p18 | 1 |
| S5 | `static Exception Finalizer([__instance, args,] Exception __exception)` alone | instance (void, bool, IEnumerator) | HE-p3, HE-p4, HE-p6, HE-p7, HE-p8, HE-p10, HE-p11, SE-p2, SE-p3, CE-p8 | 10 |
| S6 | `static void Prefix(args, out T __state)` + `static Exception Finalizer(args, T __state, Exception __exception)` | instance, void | HE-p2, HE-p5, HE-p9, CE-p2, CE-p6, CE-p12, CE-p14, CE-p15, CE-p19 | 9 |
| S7 | S6 with positional `__0, __1` and no __instance | static, void | HE-p1, IC-p1 | 2 |
| S8 | `static void Prefix(args, out T __state)` + `static void Postfix(args, T __state)` | instance, void | IC-p4, CE-p9 | 2 |
| S9 | S8 with `R __result` in the postfix | instance, bool | CE-p1 | 1 |
| S10 | S8 with a struct __state, `bool __runOriginal` in the postfix, prefix at Priority.First + 1 | instance, void | PT-p2 | 1 |
| S11 | `static void Prefix()` + `static Exception Finalizer(Exception __exception)`, no state | instance, void | PT-p1 | 1 |
| S12 | `static void Postfix(__instance, args, bool __runOriginal)` + `static Exception Finalizer(__instance, args, Exception __exception)` | instance, void | CD-p5, CD-p6 | 2 |
| S13 | `static bool Prefix(__instance, args, ref R __result, bool __runOriginal)` (skipping prefix) | instance, GameObject | CD-p7 (not compiled) | 1 |
| S14 | manual `Harmony.Patch(target, postfix: static void Noop())` | any | IC-p5 (test fixture) | 1 |

## Counts

Entries per component (call sites + patches):

| component | call sites | patches | total |
|---|---|---|---|
| HitEvidence | 5 | 11 | 16 |
| SeatEvidence | 57 | 3 | 60 |
| PointEvidence | 7 | 2 | 9 |
| IdentityClockEvidence | 10 | 5 (4 attribute + 1 manual) | 15 |
| CardDrawEvidence | 9 | 7 (6 + 1 not compiled) | 16 |
| CombatEvidence | 8 | 19 | 27 |
| PeerBuild | 4 | 0 | 4 |
| total | 100 | 47 | 147 |

Reach:

| component | yes | both | no | boundary |
|---|---|---|---|---|
| HitEvidence | 8 | 2 | 3 | 3 |
| SeatEvidence | 12 | 13 | 28 | 7 |
| PointEvidence | 1 | 2 | 1 | 5 |
| IdentityClockEvidence | 0 | 4 (IC-p5 only if armed) | 6 | 5 |
| CardDrawEvidence | 0 | 2 | 9 | 5 |
| CombatEvidence | 19 | 2 | 2 | 4 |
| PeerBuild | 0 | 2 | 2 | 0 |
| total | 40 | 27 | 51 | 29 |

- Entries reached in live combat (yes + both): **67** (66 without the armed-only IC-p5). A further 29 boundary entries fire at an
  edge whose live-predicate value is not established from repo code.
- Patches reached in live combat: 35 of 47 (HE 9, SE 3, PT 1, IC 3 incl. IC-p5, CD 0, CE 19). Of the 67, the per-frame ticks are
  8 rows (PB-c2, PB-c3, SE-c52, PT-c5, SE-c53, CD-c6, CE-c7, IC-c6) plus CD-c7.
- Distinct patch shapes: **14** (S1 to S14); 12 in the shipped build (S13 is not compiled, S14 is a test seam).
