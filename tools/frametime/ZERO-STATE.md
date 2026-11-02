# Zero-state inventory (METHOD-V4 3.3), for the check at each point's first live frame

Read-only inventory of the lane worktree at b2549f4c (line numbers include the SCR_FRAMETIME blocks, so they differ
from INVENTORY.md's 1c77f580 numbers; e.g. CombatLive is SeatEvidence.cs:695). Class iii is in INVENTORY.md.

**Where the check runs.** CombatEvidence resets at PointEnd (CombatEvidence.cs:1783, on the first non-live tick,
:1727) and PointStart (:1765, on the first live tick, :1726). Rows 2, 3 and 5 are zero only after PointStart, so the
check runs right after `PointStart(...)` at :1726, before RxSample (:1748).

`IsLiveProj(id)` = `(v = PhotonNetwork.GetPhotonView(id)) != null && v.GetComponent<ProjectileHit>() != null`.
Every field below is private; accessors: `CombatEvidence.ZeroStateCE()`, `HitEvidence.ZeroStateHE()`,
`SeatEvidence.ZeroStateSE()`, `IdentityClockEvidence.ZeroStateIC()`, `PointEvidence.ZeroStatePT()`, each an
`internal static int` bitmask of failing rows (0 = pass), all inside `#if SCR_FRAMETIME`.

| # | comp | field (decl) | cls | live write -> live read | reset | empty test |
|---|---|---|---|---|---|---|
| 1 | CE | `GunState.Ring/RingN` :182 | i | InitEnterBody :579 -> DrainVolleys :1917-1919 | PointEnd drains all :1795 | `g.Own.RingN + g.Opp.RingN == 0` |
| 2 | CE | `GunState.Win/WinN` :183 | i | DrainVolleys :1926-1927 -> :1928-1929 | PointReset :1802 (via PointStart :1777-1778) | `g.Own.WinN + g.Opp.WinN == 0` |
| 3 | CE | `HasVolley/LastVolley, Gmin, Vmax, Refreshes` :180-181 | i | :576-577, :1924, :1240 -> :575, :1924 | :1802 | both GunStates: `!s.HasVolley && s.Gmin == -1 && s.Vmax == 0 && s.Refreshes == 0` |
| 4 | CE | `InAttack, FirstPending, MsgPending, RlOpen` :174-178 | i | :489, :454, :500, :626 -> :486, :602, :608 | PointClose :1810-1814 (from PointEnd :1796-1797) | `!s.InAttack && !s.FirstPending && !s.MsgPending && !s.RlOpen` |
| 5 | CE | `RxRowS/RxRowO` :273 | i | RxSample :2083 -> RxVolley :2134 | :1773, :1787 | `g.RxRowS == -1 && g.RxRowO == -1` |
| 6 | CE | `OwnPid/OwnSInit/OwnCord/OwnDec(On)/BsOn` :287, :235, :247 (k = pid & 255) | ii | NoteAnchor :655 -> own-key probes :780, :879, :949, :1069, :1271, :1328, :1372 | only a new `Game` (:103) | each k: `g.OwnPid[k] == 0 or !IsLiveProj(g.OwnPid[k])` |
| 7 | CE | `SgOn/SgPid` :266 | ii | MoveBody :883, SegRebase :951 -> MoveExit :902, SegBreak :939 (own key) | slot reuse :654, Build :2349 | `!g.SgOn[k] or !IsLiveProj(g.SgPid[k])` |
| 8 | CE | anchors `Slot/APid/ALive/AObj` :278-284 | ii | NoteAnchor :639-648 -> `Slot.TryGetValue` :738, :1076, :1290, :1366, :1663; by slot :1949, :2158, :2208 | ALive never cleared (:645 its only write); ring eviction :642 | each i: `!g.ALive[i] or g.AObj[i] == null or !g.AObj[i].activeInHierarchy` |
| 9 | CE | `Mask`+`MaskObj`, `Pack`+`PackObj` :289, :292-294 | ii | :657-659, :1672 -> drained in order by DrainMasks :1934-1951, DrainPackages :2199-2210 (16 per frame) | tick drain only (:1758, :1762) | `g.Mask.N == 0 && g.Pack.N == 0` |
| 10 | HE | `_point` :38 | i | P() :70-72 (from :96, :115, :134) -> P() :69 | PointEnd :247-248 (from PoisonSync.cs:3270) | `_point.Count == 0` |
| 11 | HE | `_blockedThisPoint` :42 | i | NoteBlock :146 -> NoteDamage :102 | :251 | `!_blockedThisPoint` |
| 12 | HE | `_projAmmo` :40 (projectile ViewID, cap 8192) | ii | NoteSpawn :163 -> NoteImpact :183 (own key) | GameEnd :266 only | no key with `IsLiveProj(key)` (CappedMap enumerates, SeatEvidenceCore.cs:539) |
| 13 | SE | `_impDistinct` :143 (opponent projectile pids) | ii | HitEnter :490 (Add and Count only) | Handover :201 (per game) | no member with `IsLiveProj` |
| 14 | IC | `_anyDead` :133 | i | per-frame tick :536 -> :535 | PointStart :393 | `!_anyDead` |
| 15 | IC | `Book.CurO/CurS` (IdentityClockCore.cs:1097) | i | OtherShot :1135-1143 (from IdentityClockEvidence.cs:365), OwnShot (:368), PointPkg :1217 | ClosePoint :1124-1128; fresh records at PointStart :1103-1112 | `CurO == null or (CurO.ShotFirst < 0 && CurO.End < 0)`; `CurS == null or (!CurS.Closed && CurS.ShotFirst < 0)` |
| 16 | PT | `_sawLost` PoisonSync.cs:3139, `_sawFrames` :3141 | i | SawAfter :3207-3210 -> :3207 | PointEnd :3269 | `_sawLost.Count == 0 && _sawFrames == 0` |
| 17 | PT | `_before` :3140 | i (per Saw frame) | SawBefore :3183 -> SawAfter :3193-3203 | every Saw frame (:3176, :3211) | `_before.Count == 0` |

Notes. Row 15: CurO is a fresh record that may hold pre-combat package data, so only live-written fields are tested.
Rows 6 to 8: live paths probe their own key or slot only; the loops over these tables (Build :2349,
CountDistinctHoming :2429) run outside combat. Photon reuses view ids, so a stale key matching a live object at the
first frame counts as a failure (no projectile should exist yet). A gun or block hook can run in the first live frame
before the tick and legitimately set rows 1, 3, 4, 11 or 15: the check must run before any hook of that frame, or
read those rows from a snapshot taken at the tick's PointStart.

No class i/ii structure: SeatEvidence has no per-point state (its only reset is ResetGame :177-191 from BeginGame
:74); CardDrawEvidence runs only DrainNotes in combat (:864-878, from :893), which clears its notes; PeerBuild's
`_printed` (PeerBuild.cs:22) is per room (:123, :130).

**Outside i/ii and iii, survives the point:** CE `RhOwn/RhOpp`, `RfOwn/RfOpp` (:258, :261), rings of recent hits and
forces carrying projectile pids, cleared only at that player's death (DieBody :1611, :1614); the survivor's ring
carries into the next point and into that player's next death row (:1625-1640). INVENTORY.md's class iii list does
not cover them: a finding for the code round (the next point's death row of an ON point can include entries an OFF
point would not have written).

**No projectile alive:** `UnityEngine.Object.FindObjectsOfType<ProjectileHit>().Length == 0`, the call the stale
projectile sweep already uses (VanillaFixes.cs:4183; it despawns this seat's own bullets at RPCA_NextRound and
MovePlayers, :4103-4130). Only active objects return, so switched-off pooled carriers are left out. An unpatched peer
keeps its bullets alive (VanillaFixes.cs:4065-4069), so a mixed room can fail it (format M's room is two format M
seats).

**Game-0 mutant.** CE `GunState.Win` (row 2): under the mutant switch, PointReset skips `s.WinN = 0; s.WinHead = 0;`
(CombatEvidence.cs:1802). DrainVolleys keeps the newest stamp in the window, so after any point with a volley WinN
stays >= 1 and the check must void every later round of game 0; it also corrupts the next point's Vmax (:1930), so
the check catches a real evidence error.
