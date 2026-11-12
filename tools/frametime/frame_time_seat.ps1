<#
frame_time_seat.ps1: the FrameTime sitting on the laptop seat (FORMAT-M-PLAN.md V2 part e; BUILD-BRIEF.md section 4).

The laptop runner starts it with no arguments (laptop_job.sh <job> frame_time_seat.ps1 7200). The laptop's session
stages it once into the runner's script folder and writes its sha256 to scr-seat/runner/frame_time_seat.sha256; the
script refuses when that file is missing or names another digest. Six steps:
  1. pre-image: the sha256 and a copy of the cfg and of the five log files (LogOutput.log, LogOutput-prev.log,
     output_log.txt, Player.log, Player-prev.log, in the folders the mod's log bundle resolves), VR6's first listing
     (BepInEx/config: the seat-evidence queue, its .tmp, every closing file and its .unverified set-aside, the
     pending and refused report files, the cfg), and the installed DLL's sha256, which must equal one staged FrameTime
     lane's digest (scr-seat/incoming/frametime-*/sha256.txt);
  2. the sentinel BepInEx/frametime/arm (seed, f18, and a third line force=ON only under -ArmForce ON, sitting V;
     -ArmForce none, the default, writes the two lines of sitting C) and the launch; the game's pid is captured;
  3. a wait for "[FRAME-TIME] sitting complete" until its own deadline (TimeoutS minus 600 s), then a graceful quit,
     and a kill by the captured pid only when the game still runs 60 s later;
  4. in every outcome the sentinel removed, then printed in this order: the runs/<stamp> token (UTC), "=== log lines"
     (the [FRAME-TIME] lines, the window lines included, under the export rule), "=== saved slice" (the slice's class
     headers, METHOD-V4.md 3.11; the slice itself is saved whole in the run folder with its line count and sha256),
     "=== component slice" (the saved-slice lines that carry no [FRAME-TIME] tag, under the export rule: queue
     writes, builds, refusals, the component tags, the BepInEx banner; it sits after "=== log lines", so
     pull_result.py keeps it in log-lines.txt), "=== VR6" (VR6's second listing), then "=== restored" (step 5).
     The export rule (ruling R6-A3.11.112 F2, function SliceExport): a selected line is printed only when the whole
     line matches one form of $FormText, the text of one log call of plugin/*.cs whose variable fields are closed
     sets (digits, hex, the ft_ room form, actor numbers, fixed tokens, the generated sets); a cfg-derived field
     leaves only as a token of a closed set the form names. Any other selected line is withheld: never printed,
     counted as one "withheld <class> <n>" line per class with n > 0 at the end of its section;
  5. the sitting's logs moved into runs/<stamp>/sitting/, the pre-image copies put back, their sha256s printed and
     compared; LogOutput-prev.log must not change during the sitting (this build makes no prev copy); a cfg that
     differs from its pre-image is first copied to runs/<stamp>/sitting/ and "kept cfg <sha256>" printed, which
     equals VR6's after digest. The kept copy stays on the laptop: no cfg value leaves it (the cfg carries
     AdminSecret). The by-kind verdict is made here, by CfgKind, a port of ft_cfg_compare.py's rule (every line that
     is not a comment line, with its line ending, and the BOM byte-identical and in the same order), and printed as
     exactly one line, "kept cfg kind RESTORED-KIND" or "kept cfg kind NOT-RESTORED-KIND" (a refusal of the rule,
     a line not UTF-8 or of no kind of the file's grammar, prints NOT-RESTORED-KIND); the line carries no value, and
     it is what the VM reads. The keep sits in a try of its own, so a failed keep prints "kept cfg error: ..." and
     no kind line, and the cfg is still put back. The keep changes no verdict and no exit code: VR6 still fails on
     the changed cfg (exit 4). After step 5 the sitting prints exactly one line: "RESTORE-PROOF ok <n>" (n = the
     "restored ... equal" lines, one per log and one for the cfg) when Step5 proved every log and the cfg equal to
     their pre-image, else "RESTORE-PROOF FAILED";
  6. not here: the Release DLL goes back by `laptop_push.sh release-restore-<sha8>` (or the backup install_remote.sh
     made), and the sitting counts as complete only when the installed sha256 equals the pre-sitting one.
The cleanups are independent (function Sitting): the shutdown runs in its own finally around the launch and the wait,
the sentinel removal in a finally around that, and step 5 in a finally around step 4; an error in any of them is
caught after its cleanup ran, printed, and mapped to an exit code, so a wait error still shuts the game down and
restores, and a step-4 error still runs step 5.
-SelfTest runs steps 1, 4 and 5 and function Sitting (with a simulated launch, wait and shutdown) against a scratch
folder of fixtures (no launch, no game file touched), once clean and once for each mutant: keep_prev_copy (the sitting
writes LogOutput-prev.log) and closing_file (the sitting writes a closing file) must fail VR6; no_component_slice
(step 4 drops "=== component slice") must fail the component check; throw_in_wait (the wait throws) and
throw_in_step4 (step 4 throws) must still print the shutdown marker, remove the sentinel, print "=== restored" with
every sha256 equal, and end with exit code 3 and 4. The cfg mutants ($CfgCases) each rewrite the cfg during the
sitting and must fail VR6 with exit code 4 and still restore the cfg equal: cfg_comment (a comment line appended)
must print one "kept cfg <sha256>" equal to VR6's after digest and to the copy left in sitting/, a copy that differs
from pre/ in comment lines only, and "kept cfg kind RESTORED-KIND"; cfg_value, cfg_key_added, cfg_key_removed,
cfg_keys_swapped, cfg_blank_added, cfg_crlf_lf, cfg_bom_removed, cfg_section_renamed and cfg_non_grammar must print
one kept line and "kept cfg kind NOT-RESTORED-KIND"; cfg_keep_fails (a comment line appended, and the keep's
destination held open by the self-test) must print "kept cfg error" and no kind line, and end with exit code 4, not
5; the clean run must print no "kept cfg" line and leave no cfg in sitting/. Every run but the three below must print
one "RESTORE-PROOF ok 6" and no FAILED line. The restore failures, each with VR6 failing too ($RestoreFailCases):
cfg_restore_locked (the cfg rewritten, then held by a handle that permits reading and hashing it but refuses the copy
of the pre-image back), log_restore_fails (a closing file, and a log's pre-image copy gone) and wait_restore_fails (the
same, and the wait throws) must print "RESTORE-PROOF FAILED", no ok line, and end with exit code 5. The simulated log
($SimFt, $SimForm, $SimNoForm, $SimPlant) holds lines in the mod's forms, lines of formless classes, and planted
cfg-like values holding each class word (the BaseUrl's startup line, the COMBAT-PERF probe mode, a route host): in
every run that prints both sections no planted value may be printed, every form line must be exported in its section,
and the withheld lines must be exactly the fixture's counts; export_all (every selected line exported, the old
selection) is that check's negative control and must fail it. The window lines ($SimWindow, as many as the point
line's windows=) must be exported under "=== log lines", and ft_parse.py's window-count rule (records_missing, through
ft_slice_identity.py --wcount) run on that section must find no miss; drop_w (the window lines skipped again, as before
ruling R6-A3.11.133 (2)) must make that rule refuse on the windows= count. The window form of B11 (SHARED.md "The
window line"; function WindowKeysRefused): the case table $WFormCases holds each refused form (the earlier appended
plant= and partial=, a key twice at the top level or as a writer type inside wu= or tok=, a tok whose writer types
differ from wu's, a writer type outside $FormSets.wtype) beside its negative control, the same line without the
defect, which must be exported; no_wkeys (the key check skipped) must export the cases only that check refuses and
still refuse the ones the form refuses, and in the simulated sitting must move the withheld counts. It prints
SELFTEST PASS only when the clean run passes and every mutant behaves as wanted. -ArmForce in both values: every run
arms with none except arm_force_on, the clean run under -ArmForce ON, and each run's sentinel bytes read at the
simulated launch must be exactly seed and f18 (CRLF lines) plus force=ON only in arm_force_on, with one "sentinel
written" line naming force=ON only there.
-SliceOf <log> prints step 4's two exported sections for a log file ("=== log lines", "=== component slice") and
exits 0 (2 when unreadable); it reads only, and is how ft_slice_identity.py proves the parse identity of the rule.
-CfgKindList <file> prints CfgKind's verdict (RESTORED-KIND, NOT-RESTORED-KIND or REFUSED) as "CFG-KIND <n> <verdict>"
for each line "<pre-image cfg><TAB><sitting cfg>" of the file, and exits 0 (2 when the file is unreadable); it reads
only, and is how ft_cfg_kind_agree.py proves the port agrees with ft_cfg_compare.py on its corpus.
Exit codes: 0 pass, 2 refused before the launch (a step-1 error included), 3 the sitting did not complete (a launch,
wait or shutdown error included), 4 VR6 failed (a step-4 error included), 5 the restore is not proven (a mismatch or
a step-5 error; ruling R6-A3.11.112 F1), 6 the self-test failed. 5 overrides 3 and 4: the job ends 0 or 4 only with
"RESTORE-PROOF ok <n>", and 3 only when the restore is proven too.
#>
[CmdletBinding()]
param(
    [switch]$SelfTest,
    [string]$CfgKindList = '',
    [string]$SliceOf = '',
    [int]$TimeoutS = 7200,
    [int]$Seed = 1,
    [ValidateSet('A', 'B')][string]$F18 = 'A',
    [string]$GameRoot = 'C:\Program Files (x86)\Steam\steamapps\common\ROUNDS',
    [string]$SeatRoot = (Join-Path $env:USERPROFILE 'scr-seat'),
    [string]$LocalLow = (Join-Path $env:USERPROFILE 'AppData\LocalLow'),
    [ValidateSet('ON', 'none')][string]$ArmForce = 'none'
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 2

$SliceClasses = @('[FRAME-TIME]', '[FPSCAP]', '[COMBAT-PERF]', '[HIT-EVIDENCE]', '[SEAT-EV]', '[HP-POINT-END]',
    '[SAW-POINT]', '[IDENTITY-CLOCK]', '[CARD-EV]', '[COMBAT-EV]', '[PEER-BUILD]', '[BUILD-PROP]', 'record queued',
    'record kept for the next launch', 'refused', 'voided', 'Failed to patch', 'BepInEx 5.')
$Vr6Named = @('CompetitiveRounds.seat-evidence.jsonl', 'CompetitiveRounds.seat-evidence.jsonl.tmp',
    'CompetitiveRounds.pending-reports.jsonl', 'CompetitiveRounds.pending-reports.jsonl.tmp',
    'CompetitiveRounds.refused-reports.jsonl', 'com.competitiverounds.mod.cfg')
$Vr6Patterns = @('CompetitiveRounds.seat-evidence.*', 'CompetitiveRounds.pending-reports.*', 'CompetitiveRounds.refused-reports.*')
# the self-test's mutant; only -SelfTest sets anything but 'none'
$script:Mutant = 'none'
$script:RestoredEqual = 0

# ---- the export rule of the slice (ruling R6-A3.11.112 F2; it refines R6-A3.11.105: no cfg file and no free cfg
# value leaves the laptop). $SliceClasses still SELECTS: a line holding a class word goes to slice.log, which stays on
# the laptop, and is counted in its class header. A selected line is EXPORTED (printed under "=== log lines" or
# "=== component slice", and so part of the job's result) only when the WHOLE line matches one form below. Each form
# is the BepInEx line prefix and the text of one log call in plugin/*.cs, its variable fields written as closed
# placeholders: digits, hex, the ft_ room form, actor numbers, fixed tokens and the named closed sets ($FormSets); a
# cfg-derived field is a closed token set the form names (the route host, the COMBAT-PERF probe mode). Exception
# messages, peer-chosen text and every other free field have no placeholder, so a line carrying one matches no form.
# Every other selected line is WITHHELD: never printed, only counted, as one "withheld <class> <n>" line per class
# with n > 0 at the end of the section that would have printed it (a line holding two class words counts in both).
# The FrameTime window lines ("[FRAME-TIME] w ") are exported under the same rule, by their own form (ruling
# R6-A3.11.133 (2): the laptop's window widths are unidentifiable without them); a window line that matches no form is
# withheld and counted like any other.
$FormSets = [ordered]@{
    # generated from the source tables (ft_slice_identity.py --sets prints these lines, and its identity run refuses a
    # difference): gate_specs/entries.py (entry, shape), gate_specs/a3.py (a3k), every class named *Patch in
    # plugin/*.cs (patch) and every path segment of an /api/v1/ url there (seg)
    entry  = 'HE-p1:PhotonNetwork.ExecuteRpc HE-p2:HealthHandler.RPCA_SendTakeDamage HE-p3:HealthHandler.RPCA_SendTakeForce HE-p4:HealthHandler.DoDamage HE-p5:Block.RPCA_DoBlock HE-p6:ProjectileInit.RPCA_Init HE-p7:ProjectileInit.RPCA_Init_noAmmoUse HE-p8:ProjectileInit.RPCA_Init_SeparateGun HE-p9:ProjectileHit.RPCA_DoHit CE-c7:CombatEvidence.Tick CE-p1:Gun.Attack CE-p2:ProjectileInit.RPCA_Init CE-p3:ProjectileInit.RPCA_Init_noAmmoUse CE-p4:ProjectileInit.RPCA_Init_SeparateGun CE-p5:GunAmmo.ReloadAmmo CE-p6:ProjectileHit.RPCA_DoHit CE-p7:ProjectileHit.Hit CE-p8:Block.RPCA_DoBlock CE-p9:Block.TryBlock CE-p10:CharacterStatModifiers.DealtDamage CE-p11:BounceEffectRetarget.SetNewVel CE-p12:ScreenEdgeBounce.DoHit CE-p13:SyncProjectile.OnPhotonSerializeView CE-p14:HealthHandler.RPCA_SendTakeForce CE-p15:HealthHandler.RPCA_SendTakeDamage CE-p16:HealthHandler.RPCA_Die CE-p17:HealthHandler.RPCA_Die_Phoenix CE-p18:BounceEffectRetarget.FindTarget CE-p19:MoveTransform.Update SE-c50:SeatEvidence.NoteView SE-c52:SeatEvidence.CompatTick SE-c53:SeatEvidence.Tick SE-p1:PhotonNetwork.RPC SE-p2:Block.DoBlock SE-p3:Block.TryBlockMe PT-c5:PointEvidence.Drain PT-p1:Saw.Update IC-c6:IdentityClockEvidence.Tick IC-p1:PhotonNetwork.ExecuteRpc IC-p4:SyncPlayerMovement.OnPhotonSerializeView CD-c6:CardDrawEvidence.Tick CD-c7:CardDrawEvidence.EnsureCensusDump PB-c2:PeerBuild.StageBuildProp PB-c3:PeerBuild.Tick'
    shape  = 'CE_p1 CE_p10 CE_p11 CE_p12 CE_p13 CE_p14 CE_p15 CE_p16 CE_p17 CE_p18 CE_p19 CE_p2 CE_p3 CE_p4 CE_p5 CE_p6 CE_p7 CE_p8 CE_p9 HE_p1 HE_p2 HE_p3 HE_p4 HE_p5 HE_p6 HE_p7 HE_p8 HE_p9 IC_p1 IC_p4 PT_p1 SE_p1 SE_p2 SE_p3 call span.empty'
    a3k    = 'CE_Top CE_Ht CE_Ping CE_lhat_cache CE_Pos CE_Recent CE_Wait CE_Rings CE_anchor CE_Gun CE_B5c CE_counters CE_scratch CE_gun_scalars CE_gun_account CE_aimset CE_capture CE_perf_probe SE_Hw SE_Logs SE_ordinals SE_frames SE_scalars HE_Flush HE_game HE_point HE_sender PE_Rec PE_map IC_Rpc IC_Clock IC_scalars IC_point IC_game CD_notes PB_printed HE_hitset'
    patch  = 'AbyssalCountdown_Activate_DeepEnd_Patch Arm_DancePatch ArtHandlerAwakePatch ArtHandlerNextArtPatch AvatarCreatePlayerPatch AvatarLoadFacesPatch AvatarSelectFacePatch BlockDoBlockCounterPatch BlockRpcaDoBlockChainClassifierPatch BlockRpcaDoBlockZombieScrubPatch BlockTriggerDoBlockNullSafetyPatch BlockTryBlockCounterPatch BlockTryBlockOnF5Patch Block_FfaSpawnGrace_Patch Broadcast_BlockPress_Patch Broadcast_ShotActivation_Patch BulletPoolReleaseGuardPatch CardBarHandler_AddCard_Ffa_Patch CardChoiceEndPickPatch CardChoicePickPatch CardChoiceStaleSpawnedCardsPatch CardChoiceVisuals_Hide_PopupCarrier_Patch CardChoiceVisuals_SetSelected_Instinct_Patch CardChoiceVisuals_Show_Competitive_Patch CardChoice_DoPick_SameCards_Patch CardChoice_ReplaceCards_SameCards_Patch CardChoice_SpawnUniqueCard_SameCards_Patch CardDrawEvidenceTestDealer_SpawnPatch CardDrawEvidence_CardAwakePatch CardDrawEvidence_DonePickingPatch CardDrawEvidence_EndPickPatch CardDrawEvidence_OfflinePickPatch CardDrawEvidence_PickPatch CardDrawEvidence_StartPickPatch CardPickChatInputGuardPatch CharacterReadyPatch CharacterSelectionMenu_PlayerJoined_2v2_Patch ChaseCardTextPatch CodeAnimStartRestorePatch CombatEvidence_AttackPatch CombatEvidence_BlockPatch CombatEvidence_ContactPatch CombatEvidence_DamagePatch CombatEvidence_DealtPatch CombatEvidence_DiePatch CombatEvidence_DiePhoenixPatch CombatEvidence_EdgeBouncePatch CombatEvidence_FindTargetPatch CombatEvidence_ForcePatch CombatEvidence_HitPatch CombatEvidence_InitAmmoPatch CombatEvidence_InitNoAmmoPatch CombatEvidence_InitSeparatePatch CombatEvidence_MovePatch CombatEvidence_ReloadPatch CombatEvidence_SyncPatch CombatEvidence_TargetBouncePatch CombatEvidence_TryBlockPatch CosmeticButtonSpawnerPatch CosmeticGetItemIdPatch CosmeticGetItemPatch CosmeticSelectButtonPatch DamageDealtLocalTrackerPatch DamageStampPatch Dance_BlockTryBlock_Patch Dance_GeneralInput_Patch Dance_GunAttack_Patch Dance_ProjectileInit_Patch DeadPlayerForcePatch DeadPlayerForcePointPatch DealDamageToPlayerFreshVictimPatch DealtDamageGuardPatch DeathClassifierPatch DemonicPactSprayPatch DevConsoleToggleGuardPatch DrillVisibilityPatch EndScreenKillPatch EscToggleDiagPatch ExplosionPerColliderIsolationPatch FfaAssembly_LoadGate_Patch FfaDamageDealtTrackerPatch FfaLate_CallInHold_Patch FfaLate_ForceQuarantine_Patch FfaLate_NoMapReport_Patch FfaLate_NoSyncReply_Patch FfaLate_PickQuarantine_Patch FfaLate_Register_Patch FfaLate_Simulated_Patch FfaLate_Visible_Patch FfaReadmit_RegisterOrder_Patch FtChurnFreezePatch FtDrive_InputPatch FtDrive_PickPatch FtRoomGateNchRoutinePatch FtRoomGateNchVoidPatch FtRoomGatePunPatch FtRoute_SendPatch GMArmsRaceAwakePatch GMArmsRaceOnEnable_4Player_Patch GMArmsRaceStartGameBlockResetPatch GMArmsRace_DoStartGame_Ffa_Patch GMArmsRace_DoStartGame_PopupCarrier_Patch GMArmsRace_DoStartGame_SameCards_Patch GMArmsRace_NextRound_Ffa_Patch GMArmsRace_PlayerDied_Ffa_Patch GMArmsRace_PlayerJoined_Diag_Patch GMArmsRace_StartGame_Diag_Patch GameCrownHandler2v2Patch GameLocaleOptionsInitPatch GameOverTextTeamColorPatch GeneralInput_FfaSpawnGrace_Patch GetColorFromTeamEmptyTeamPatch GetFirstPlayerInTeamEmptyTeamPatch GrowFpsNormalizePatch GrowPreJoinSyncPatch GunApplyPlayerStuffProvenancePatch GunAttackBlockOnF5Patch GunAttackIntentCapturePatch GunDoAttacksIntentPatch GunFireBurstProvenancePatch HealSoundGuardPatch HealthBar_AttachHealOverlay_Patch HealthHandlerTakeDamageCounterPatch HealthHandler_HealOverlayReviveReset_Patch HitEvidence_BlockPatch HitEvidence_DamagePatch HitEvidence_DotPatch HitEvidence_ExecuteRpcPatch HitEvidence_FfaDoStartGamePatch HitEvidence_ForcePatch HitEvidence_ImpactPatch HitEvidence_SpawnAmmoPatch HitEvidence_SpawnNoAmmoPatch HitEvidence_SpawnSeparatePatch HitEvidence_StartGamePatch HostRoomCodeClipboardPatch IdentityClock_ExecuteRpcPatch IdentityClock_MovePlayersPatch IdentityClock_MovementPatch IdentityClock_PointStartPatch InRangeIndicatorRadiusPatch InactiveVisualsHidePatch JumpDustTeamColorPatch KeyboardFactoryPatch LandDustTeamColorPatch LineRangeEffect_FfaOwnerExclusion_Patch LobbyReadyPatch LobbyRedirectPatch LocalPlayerIdPublishPatch LocalTookDamageTrackerPatch MapArtPatch MapManager_GetSpawnPoints_2v2_Patch MapManager_GetSpawnPoints_FfaShuffle_Patch MapManager_UnloadAfterSeconds_Diag_Patch MapPhysicalColorPatch MapTransition_SetStartPos_FfaScale_Patch ModRoomChurnFreezePatch MultiPickerShowVisualsPatch MusicAdmission_SteamLobbyLatchPatch MusicSuppressionPatch NCHConnectToRegionDiagPatch NCH_OnPlayerLeftRoom_Ffa_Patch NCH_OnPlayerLeftRoom_Hold_Patch NetworkConnectionHandler_NetworkRestart_Diag_Patch NetworkConnectionHandler_OnJoinedRoom_RestyleNick_Patch NetworkReplicaSerializationObserverPatch NetworkReplicaSpectatorActivationPatch NetworkReplicaSpectatorBoundaryPatch NetworkReplicaSpectatorFfaTerminalPatch NetworkReplicaSpectatorGmTerminalPatch NetworkReplicaSpectatorRoundEndPatch NetworkReplicaSpectatorSnapshotPatch NetworkSeat_DispatchDepthPatch NetworkSeat_LifecycleDiePatch NetworkSeat_LifecyclePhoenixPatch NetworkSeat_LifecycleRevivePatch NetworkSeat_MovementCapturePatch NetworkSeat_OnSerializeWritePatch NetworkSeat_RaiseEventInternalPatch NetworkSeat_RunViewUpdatePatch NetworkSeat_SendOutgoingDepthPatch OnEnablePatch OutOfBoundsHandler_FfaScale_Patch OverlayGate_ArmsRaceDebugKeys_Patch OverlayGate_ArtHandler_Patch OverlayGate_ButtonJoinRoom_Patch OverlayGate_CharacterSelect_Patch OverlayGate_CreatorDragging_Patch OverlayGate_CreatorNavigation_Patch OverlayGate_CreatorPortrait_Patch OverlayGate_DevConsoleDialog_Patch OverlayGate_EscapeMenu_Patch OverlayGate_FriendInvite_Patch OverlayGate_GeneralInput_Patch OverlayGate_GoBack_Patch OverlayGate_MultiOptions_Patch OverlayGate_PlayerAssigner_Patch OverlayGate_PopUp_Patch OverlayGate_RemoteControl_Patch OverlayGate_UIBlockList_Patch OverlayGate_UIBlockPlayer_Patch OverpowerNonPlayerTargetPatch OvtExtraPickPatch OvtExtraPickRestorePickerPatch PhoenixRespawnPatch PhotonMapObject_Start_FfaScale_Patch PhotonNetwork_LeaveRoom_Diag_Patch PlayerAssigner_CreatePlayer_2v2_Patch PlayerManagerResetCharactersBlockResetPatch PlayerManagerRevivePlayersWeaponCooldownPatch PlayerManager_GetClosestPlayerInTeam_Ffa_Patch PlayerManager_GetOtherPlayer_Ffa_Patch PlayerManager_MovePlayers_FfaScale_Patch PlayerManager_PlayerDied_Ffa_Patch PlayerNameTeamColorPatch PlayerNicknameLabelRefreshPatch PlayerNicknameRepairPatch PlayerSkinBank_GetPlayerSkinColors_2v2_Patch PlayerVelocity_TeardownDrive_Patch Player_FullReset_CardBaseline_Patch Player_Start_Diag_Patch PointEndEvidencePatch PointVisualizerTeamColorPatch PoisonArmPatch PoisonDeathFlushPatch PoisonDotSchedulerPatch PoisonEffectRegistrationPatch PoisonGhostPatch PoisonHitBracketPatch PoisonPhoenixBoundaryPatch PoisonPointBoundaryPatch PoisonReviveFencePatch PoisonRpcStampPatch PopUpHandler_StartPicking_Competitive_Patch ProjectileHit_DirectHitCounter_Patch QuickplayChurnAbandonGuardPatch QuickplayChurnFreezePatch RadarVisualLifetimePatch ReadyUpPatch RematchTextTeamColorPatch RemotePlayerIdOrderPatch ResetMenuPatch RosterCensus_MapBoundary_Patch RoundCounterTeamColorPatch RpcDispatchGuardPatch RpcLocalSendDepthPatch SawDeadTargetPatch SawLiveTargetPatch SawPointEvidencePatch ScreenshakerDisablePatch SeatEvidence_DoBlockPatch SeatEvidence_RpcSendPatch SeatEvidence_TryBlockMePatch ShotProvenanceEpochPatch SilenceDisableCapturePatch SilenceStartPatch SilenceStartRewirePatch SonigonPlayGuardPatch SonigonVoiceUpdateGuardPatch SpawnOnImpactFieldDiagPatch Spectator_BoundaryObserver_Patch Spectator_EntryIsNotMatchFound_Patch Spectator_LeaveIsInvisible_Patch Spectator_MapLoadCompleted_Patch Spectator_MapLoadGate_Patch Spectator_NoAssignerPoll_Patch Spectator_NoCardPickRpc_Patch Spectator_NoCreatePlayer_Patch Spectator_NoDoStartGame_Patch Spectator_NoGameOverTransition_Patch Spectator_NoGmPlayerDied_Patch Spectator_NoGmPlayerJoined_Patch Spectator_NoGmTest_Patch Spectator_NoInboundMapReports_Patch Spectator_NoJoinPrompt_Patch Spectator_NoMapAuthority_CallInBare_Patch Spectator_NoMapAuthority_CallIn_Patch Spectator_NoMapAuthority_Load_Patch Spectator_NoMapObjectAuthority_Patch Spectator_NoMapReport_Patch Spectator_NoPlatformProgress_Patch Spectator_NoPlatformUnlock_Patch Spectator_NoStartGame_Patch Spectator_NoSyncReply_Patch Spectator_NoVanillaEscMenu_Patch Spectator_NonLethalDamage_Patch Spectator_ObserveNextRound_Patch Spectator_OrphanSerializationMute_Patch Spectator_PreActivationPickQuarantine_Patch Spectator_RegistrationFirewall_Patch Spectator_ReplayQuarantine_Patch Spectator_ReplayTag_Patch Spectator_SyncUpNoWait_Patch StaleProjectileSweepPatch StartPickingPatch StunDisableCapturePatch StunPlayerFreshVictimPatch StunStartPatch TeamGameLifecycle_DoStartGame_Patch TeamGameLifecycle_GameOverTransition_Patch TeamHold_DoPickPatch TeamHold_GameOverPatch TeamHold_GameStartPatch TeamHold_OfflinePickPatch TeamHold_PhoenixClaimPatch TeamHold_PickSeamPatch TeamHold_PointTransitionPatch TeamHold_RematchFencePatch TeamHold_RoundTransitionPatch TeleportToOpponentFreshVictimPatch WeaponCooldownPhoenixDiagPatch WeaponHandlerAttackIntentPatch WeaponHandler_FfaSpawnGrace_Patch Wobble_DancePatch'
    seg    = 'abc achievements actions active active-color active-cursor-color active-player-color active-player-effect active-title active-trail admin admins alerts all-series-paged allow-spectators api appear-offline artist artists auth auto ban banned-users beat bets bettable block blocks bracket-detail bridge-unmute broadcast bug-reports build-type by-room cancel card-evidence card-tiers cards casual-dc catalog-cosmetic-placement chat check check-status client close color-toggle combat-evidence comment compare compat-outcome continuation cosmetic-frames cosmetic-placement cosmetic-preview cosmetic-release-candidates cosmetic-review cosmetic-submissions count create current data decline delete earners escape exclude ffa ffa-history flagged-matches force-start-vote forfeit full game games gift gold-sources grant grant-achievement grants health heartbeat hide-gold history history-detail hold identity-clock-evidence inbox inventory items join kick leaderboard leaders-summary leave lfp-ping link-code list live-points lobbies lobby lobby-bets lockdown logs macro-evidence mail mailbox maintenance manual-pick-toggle match matches mine mod mod-version moderate motion music mute mute-by-message mutes my-active-matches my-submissions nametag-toggle nemesis newest offer online open ovt ovt-history pack participant-attest pc pc-face ping play-now player-nemesis players poll portal-session pref-same-cards preferred-team preflight prefs presence purchase quarantine queue queues rank-tiers ranked-friends rate ratings read readmit ready recent recent-multimode recent-series records release-notes releases reply report report-dc report-disconnect report-status resolve resolve-flag-restoration reverse-series review-flag revoke sales sales-board search seat-evidence series set set-artist set-desc set-name set-price set-stock settings shop show-discord signup similar spawn-confirm spectate start state status steam submit-cosmetic submit-cosmetic-finalize submit-cosmetic-frame submit-cosmetic-gif summary target team team-bets team-history team-matches team-stats time-vote title-ladders toggle-ranked top-pickers tournaments unban unblock unlock unmute unsignup validate ws'
    comp     = 'CombatEvidence HitEvidence SeatEvidence IdentityClockEvidence CardDrawEvidence PointEvidence PeerBuild Cal'
    op       = 'ce_build se_build cd_build ic_build enqueue spool pump answer hash_start hash_now'
    # the writer types of the window line's wu= and tok= (B11 D5): this ONE constant is the whole set the form admits.
    # PROVISIONAL until P1 names the set; today it is P1's FtLedger.TypeNames (FtUpload.cs, branch claude/ft-b11-p1)
    wtype    = 'log hash'
    input    = 'none sentinel sentinel_changed sentinel_problems clock perf_probe ic_fixture in_room game_started complete escape rematch_timeout menu_mode room own_sha room_name region fighters peer matchIsRanked'
    problem  = 'stat bad-line bad-seed bad-force bad-f18 bad-plant_us bad-menu bad-menu_segments'
    region   = 'asia au cae cn eu hk in jp kr ru rue sa tr uae us usw ussc za'
    roomop   = 'JoinRoom JoinOrCreateRoom JoinRandomRoom JoinRandomOrCreateRoom CreateRoom RejoinRoom ReconnectAndRejoin JoinLobby'
    gateex   = 'JoinLobby LoadOrCreateSettings'
    method   = 'GET POST PUT DELETE PATCH HEAD ?'
    # the route's host is cfg-derived for the mod's own server (the cfg's BaseUrl): it leaves only as one of these
    host     = 'competitive-rounds.duckdns.org 192.168.72.102 192.168.72.199 192.168.72.90 rounds-serversettings.s3.eu-central-1.amazonaws.com player-auth.services.api.unity.com'
    segx     = '{n} translate rounds-serversettings.txt authentication external-token steampowered.com'
    cardhook = 'CardChoice.StartPick CardInfo.Awake CardChoice.RPCA_DoEndPick CardChoice.RPCA_DonePicking ApplyCardStats.RPCA_Pick ApplyCardStats.OFFLINE_Pick'
    combhook = 'Gun.Attack ProjectileInit.RPCA_Init ProjectileInit.RPCA_Init_noAmmoUse ProjectileInit.RPCA_Init_SeparateGun GunAmmo.ReloadAmmo ProjectileHit.RPCA_DoHit ProjectileHit.Hit Block.RPCA_DoBlock Block.TryBlock CharacterStatModifiers.DealtDamage BounceEffectRetarget.SetNewVel ScreenEdgeBounce.DoHit SyncProjectile.OnPhotonSerializeView HealthHandler.RPCA_SendTakeForce HealthHandler.RPCA_SendTakeDamage HealthHandler.RPCA_Die HealthHandler.RPCA_Die_Phoenix BounceEffectRetarget.FindTarget MoveTransform.Update'
    producer = 'push vchg chain death'
    ichook   = 'IdentityClock_ExecuteRpcPatch IdentityClock_PointStartPatch IdentityClock_MovePlayersPatch IdentityClock_MovementPatch'
    pstate   = 'PeerCreated Authenticating Authenticated JoiningLobby JoinedLobby DisconnectingFromMasterServer ConnectingToGameServer ConnectedToGameServer Joining Joined Leaving DisconnectingFromGameServer ConnectingToMasterServer Disconnecting Disconnected ConnectedToMasterServer ConnectingToNameServer ConnectedToNameServer DisconnectingFromNameServer ConnectWithFallbackProtocol'
    pkey     = 'cr_build cr_cmute cr_dc2 cr_dc3 cr_effect_sku cr_ffa_gw cr_ffa_pe cr_ffa_pk cr_ffacfg cr_game_token_v cr_grow2 cr_grow_rnk cr_msv2 cr_nametag_glow cr_nametag_typeface cr_pcolor_color cr_pcolor_sku cr_pois2 cr_pois3 cr_prox1 cr_saw1 cr_trail_color cr_trail_price cr_trail_sku cr_wcd1 ft_dll ft_rm'
}
$FormPh = @{
    n = '-?[0-9]{1,19}'; u = '[0-9]{1,19}'; b = '[01]'; nl = '-?[0-9]{1,19}(?:,-?[0-9]{1,19})*'; x8 = '[0-9a-f]{8}'; x = '[0-9a-f]{1,64}'
    room = 'ft_[0-9a-f]{8}'; actor = '[0-9]{1,4}'; pt = '-?[0-9]{1,6}\.-?[0-9]{1,6}\.-?[0-9]{1,6}'; bool = '(?:True|False)'
    spins = '[0-9]{1,19}/[0-9]{1,19}(?:,[0-9]{1,19}/[0-9]{1,19})*'; f2 = '-?[0-9]{1,9}\.[0-9]{2}'
    why = '(?:start|patches|game[0-9]{1,6}|menu[0-9]{1,6})'
    build = '[0-9]{1,4}(?:\.[0-9]{1,4}){1,3}\|(?:standalone|thunderstore)\|(?:nosha|[0-9a-f]{12})'
}
function FormSet([string]$name) { return '(?:' + ((@($FormSets[$name] -split ' ') | ForEach-Object { [regex]::Escape($_) }) -join '|') + ')' }
$FormPh.shape = '(?:' + (FormSet 'shape').Substring(3).TrimEnd(')') + '|entry[0-9]{1,3})'
$FormPh.input = FormSet 'input'
$FormPh.region = FormSet 'region'
$FormPh.roomname = '(?:' + $FormPh.room + '|\(none\)|\(empty\))'
$FormPh.route = '(?:' + (FormSet 'method') + '_(?:local|other|cosmetics-zip|emoji-sheet|music-asset|' + (FormSet 'host') +
    '(?:/(?:' + (FormSet 'seg') + '|' + (FormSet 'segx') + '))*/?)|unparsed)'
# FtUpload's count keys (what:route): one closed alternation per what, the routes of FtRoute and of each Refuse site
$FormPairs = [ordered]@{
    route = $FormPh.route; sent = $FormPh.route; dispatched = $FormPh.route; outbox = '(?:enqueue|persist|load)'
    autolog = 'room-left'; chat = 'connect'; log = 'prev-copy'; closing = '[ekcxi]'; queue = '[ekcxi]'; load = '-'
}
$FormPh.pair = '(?:' + ((@($FormPairs.Keys) | ForEach-Object { $_ + ':' + $FormPairs[$_] }) -join '|') + ')'
$FormPh.refpair = '(?:' + ((@($FormPairs.Keys) | ForEach-Object { 'what=' + $_ + ' route=' + $FormPairs[$_] }) -join '|') + ')'
$FormPh.capwhy = '(?:unfocused cap|broadcast seat render cap \([0-9]{1,4} fps\)|deep idle \(broadcast seat 16min\+ idle\)|deep idle \(60s\+ unfocused, out of room\))'
$FormPh.pkeys = '(?:-|' + (FormSet 'pkey') + '(?:,' + (FormSet 'pkey') + ')*)'
$FormPh.pvals = ((@('cr_build', 'cr_dc2', 'cr_dc3', 'cr_ffacfg', 'cr_game_token_v', 'cr_grow2', 'cr_msv2', 'cr_pois2', 'cr_pois3',
    'cr_prox1', 'cr_saw1', 'cr_wcd1') | ForEach-Object { $_ + '=(?:-|[0-9]{1,9}|' + $FormPh.build + '|' + $FormPh.room + ':[0-9]{1,9})' }) -join ' ')
# the forms; "<x>" is placeholder x of $FormPh, "<@x>" the closed set x of $FormSets, "<=a|b>" a fixed choice; a form
# starting "^" has no BepInEx prefix (BepInEx's own banner; a log call's continuation line)
$FormText = @(
    '[FRAME-TIME] a3rows registered=<u> expected=<u> missing=<u> duplicates=<u>'
    '[FRAME-TIME] a3drain g=<n> k=<@a3k> starts=<n> nonempty=<n> faults=<n>'
    '[FRAME-TIME] a3 g=<n> k=<@a3k> cap=<n> steady=<b> reads_on=<n> reads_win=<n> writes_on=<n>'
    '[FRAME-TIME] cal i=<n> why=game<u> kind=a3 k=<@a3k> live=1 reads=<n> scopes=<n> ticks=<n> tmax=<n> unscoped=<n> depth_err=<n>'
    '[FRAME-TIME] cal i=<n> why=<why> kind=a3 k=<@a3k> withheld=1'
    '[FRAME-TIME] cal i=<n> why=<why> kind=a3 k=<@a3k> failed: no calibration'
    '[FRAME-TIME] cal i=<n> why=<why> kind=a3 k=<@a3k> n=<n> u=<nl> p=<nl>'
    '[FRAME-TIME] cal i=<n> why=<why> kind=fhat f_hat=<n> spins=<spins>'
    '[FRAME-TIME] cal i=<n> why=<why> kind=<=span|disp> shape=<shape> n=<n> u=<nl> p=<nl>'
    '[FRAME-TIME] cal i=<n> why=<why> kind=entries built=0 own_patches=not-applied'
    # the FrameTimeRef build (B11 D3): its boot line, its entries line and the patch classes it skipped
    '[FRAME-TIME] cal i=<n> why=<why> kind=entries reference=1 built=0'
    '[FRAME-TIME] reference collectors not installed: patch classes skipped=<u> listed=<u>'
    '[FRAME-TIME] build variant=FrameTime'
    '[FRAME-TIME] build variant=FrameTimeRef SCR_FT_REF=NOCOLLECTORS'
    '[FRAME-TIME] cal i=<n> why=<why> kind=entries failed: the built table holds no patched entry'
    '[FRAME-TIME] cal i=<n> why=<why> kind=disp shape=<shape> failed: InvalidOperationException: <@patch> is not attached: no target patched by com.competitiverounds.mod (lesson #83)'
    '[FRAME-TIME] cal i=<n> why=<why> kind=disp shape=<shape> failed: InvalidOperationException: <@patch> has a transpiler'
    # the text of the same failure in the lane's builds before c8e0dfed (their VM-seat logs are the identity corpus)
    '[FRAME-TIME] cal i=<n> why=<why> kind=disp shape=<shape> failed: InvalidOperationException: no patched target for <@patch>'
    '[FRAME-TIME] cal i=-1 why=patches kind=entries built=1 own_owner=com.competitiverounds.mod own_targets=<u> entries=<u> errors=<u>'
    '[FRAME-TIME] settled g=<n> seed=<n> c_plant=<n> W=120 vsync=<n> target=<n> freq=<n> hires=<b> f_hat=<n> gc_incremental=<b> gc_slice_ns=<n> f18=<=A|B> answer=<=replay|unmeasured> armfile=<b> force=<=ON|OFF|none><problems> clock=<b> frames=<n> missing_end=<n> cycle_failures=<n> span_depth_violations=<n>'
    '[FRAME-TIME] census g=<n> entry=<@entry> comp=<@comp> shape=<shape> on=<n> guarded=<n> outside=<n>'
    '[FRAME-TIME] spans g=<n> comp=<@comp><spans>'
    '[FRAME-TIME] clock refused: player-loop phase missing (EarlyUpdate <bool>, PreLateUpdate <bool>, Update <bool>)'
    '[FRAME-TIME] clock installed freq=<n> hires=<b> cycles=<b>'
    '[FRAME-TIME] self-drive armed: inputs are automated'
    '[FRAME-TIME] self-drive disarmed: <=escape|sitting complete|rematch timeout>'
    '[FRAME-TIME] self-drive disarmed: input=<input>'
    '[FRAME-TIME] self-drive join room=<room> region=us'
    '[FRAME-TIME] self-drive spawn try=<n> master=<b> actors=<n>'
    '[FRAME-TIME] self-drive spawn result created=<b> players=<n>'
    '[FRAME-TIME] self-drive spawn waiting why=peer'
    '[FRAME-TIME] self-drive spawn waiting why=<=assigner|actors|full|game-manager|join-closed|playing> actors=<n>'
    '[FRAME-TIME] self-drive spawn refused why=spectator'
    '[FRAME-TIME] self-drive spawn gave up tries=<n>'
    '[FRAME-TIME] self-drive pick index=<n>'
    '[FRAME-TIME] sitting complete g=<n>'
    '[FRAME-TIME] census registered=<u> expected=<u> missing=<u> duplicates=<u>'
    '[FRAME-TIME] between g=<n> after=<=ON|OFF|> ticks=<n> calls=<n>'
    '[FRAME-TIME] p pt=<pt> arm=<=ON|OFF> gate=<b> pred=<=none|ON|OFF> n=<n> sF=<n> sS=<n> sC=<n> maxF=<n> pn=<n> psF=<n> psS=<n> psC=<n> sP=<n> psP=<n> excl=<n> plant_mixed=<n> windows=<n> live_frames=<n> missing_end=<n> span_g=<n> span_gn=<n> span_u=<n> span_un=<n> on_calls=<n> guarded=<n> zs=<n> zl=<n> t0=<n> t1=<n> answer=<=replay|unmeasured>'
    # the window line (B11 SHARED.md "The window line"): the fields the line printed before, in place, then the
    # per-window record in the contract's order. prun= is the plant-run flag (the line's own plant= stays the planted
    # flag) and the line's own partial= is its only partial flag: no key is appended twice. Exportable also refuses a
    # matched window line that carries a key twice, or whose tok= writer types differ from its wu= ones (WindowKeysRefused)
    '[FRAME-TIME] w pt=<pt> arm=<=ON|OFF> plant=<b> partial=<b> n=<n> sF=<n> sS=<n> sC=<n> sP=<n> maxF=<n><wfull> gc=<n> run=<u> pos=<=1|2|3|4> unit=<=P13|P24> coin=<b> wi=<u> f0=<n> pred=<=ON|OFF|none> prun=<b> res=<b> gcn=<u> cG=<cg> cW=<n> cR=<n> cS=<n> cE=<n> q=<n10> r=<n10> qn=<u10> wu=<wu> tok=<tok> nm=<u>'
    # the boot line that gives the cost of one class transition (FtSpan mark), once per boot
    '[FRAME-TIME] mark cost cyc=<n> p90=<n> n=<u>'
    # the window line of the lane's earlier builds (the identity corpus), which ended at gc=
    '[FRAME-TIME] w pt=<pt> arm=<=ON|OFF> plant=<b> partial=<b> n=<n> sF=<n> sS=<n> sC=<n> sP=<n> maxF=<n><wfull> gc=<n>'
    '[FRAME-TIME] heavy g=<n> op=<@op> live=<n> between=<n> pick=<n> over=<n> menu=<n> at_call=<n> edge=<n> off=<n>'
    '[FRAME-TIME] offthread g=<n> span_off=<n> hash_t0=<n> hash_t1=<n>'
    '[FRAME-TIME] menu_wait input=<input>'
    '[FRAME-TIME] menu_armed segments=<n> seg_s=10 settle_s=20 force=<=ON|OFF|none> seed=<n>'
    '[FRAME-TIME] menu seg=<n> pair=<n> arm=<=ON|OFF> gate=<b> level=<=0|3|5> c_plant=<n> base_us=<n>'
    # the menu line of the lane's earlier builds, whose level was a percentage with a decimal point
    '[FRAME-TIME] menu seg=<n> pair=<n> arm=<=ON|OFF> gate=<b> level=<u>.<u> c_plant=<n> base_us=<n>'
    '[FRAME-TIME] menu_base base_us=<n> seg=<n>'
    '[FRAME-TIME] menu_done why=<input> segs=<n> of=<n> base_us=<n> cycles=<n>'
    '[FRAME-TIME] game start failed: menu=1 process'
    '[FRAME-TIME] counters g=<n> frames=<n> missing_end=<n> cycle_failures=<n> span_depth_violations=<n>'
    '[FRAME-TIME] flushed g=<n> why=<=next_game|settle|quit>'
    '[FRAME-TIME] opened g=<n> se=<b> ce=<b> ic=<b>'
    '[FRAME-TIME] staged ft_dll=<x8> <=in-room|pre-join>'
    '[FRAME-TIME] room name=<room> region=<region> cloud_region=<region><cloudtail>'
    '[FRAME-TIME] ended why=complete pt=<pt>'
    '[FRAME-TIME] disarmed input=<input> pt=<pt>'
    '[FRAME-TIME] armed room=<room> region=<region>'
    '[FRAME-TIME] not armed input=<input>'
    '[FRAME-TIME] peer unknown actor=<actor> (no matching ft_dll)'
    '[FRAME-TIME] peer known actor=<actor> ft_dll=<x8>'
    '[FRAME-TIME] room call refused op=<@roomop> name=<roomname> n=<u>'
    '[FRAME-TIME] FT-GATE patched <u> entry points expected=<u> excluded=<gateex>'
    '[FRAME-TIME] FT-ROOM joined offline=<b> name=<roomname>'
    '[FRAME-TIME] churn timer frozen room=<room>'
    '[FRAME-TIME] rematch mutant: answered Yes at once'
    '[FRAME-TIME] rematch not answered (sitting over)'
    '[FRAME-TIME] rematch held: published ft_rm=<n>'
    '[FRAME-TIME] rematch yes g=<n> after <u> ms'
    '[FRAME-TIME] rematch timeout g=<n> own=<n> peer=<n>'
    '[FRAME-TIME] ft room options max=2 visible=0 room=<room>'
    '[FRAME-TIME] ranked-check skipped'
    '[FRAME-TIME] ranked-check test hook answered true'
    '[FRAME-TIME] steam ticket withheld route=<route>'
    '[FRAME-TIME] refused <refpair> n=<u>'
    '[FRAME-TIME] refusals why=<rwhy> pairs=<u><pairs>'
    '[FRAME-TIME] plant c_plant=<n> ticks=<n> from=<pt>'
    '[FRAME-TIME] answer_replay g=<n> ticks=<n> result=<=settled|kept|enqueue_failed|not_running|e>'
    '[FPSCAP] held by frame-time calibration'
    '[FPSCAP] hold released'
    '[FPSCAP] released (restored target=<n> vsync=<n>, focused=<bool>)'
    '[FPSCAP] engaged <capwhy>: target=<n> (baseline target=<n> vsync=<n>)'
    '[FPSCAP] re-asserted <capwhy> over an external change (target=<n> vsync=<n>)'
    '[FPSCAP] released (external video-settings change adopted: target=<n> vsync=<n>)'
    '[FPSCAP] <capwhy>: target=<n>'
    '[COMBAT-PERF] probe on, mode <=menu|match>, windows of <u> frames'
    '[COMBAT-PERF] window <u> <=AA1|AA2|PLANT|A|B> frames=<n> p50_us=<n> p99_us=<n> max_us=<n>'
    '[COMBAT-PERF] A/A: |d p50|=<n>us |d p99|=<n>us; longest hitch <n>us'
    '[COMBAT-PERF] planted control: <n>us per frame, p50 rise <n>us, detected=<=yes|no>'
    '[COMBAT-PERF] menu run complete (collectors idle outside a game; the A/B in a ranked match remains)'
    '[HIT-EVIDENCE] <u> flushes not logged: every slot was waiting'
    '[HIT-EVIDENCE] keys refused at the caps: <u> point tally actor(s), <u> game tally actor(s) (cap <u>), <u> projectile(s) (cap <u>)'
    '[HP-POINT-END] point=<n> spectator=<b><hprows>'
    '[HP-POINT-END] <u> point ends not logged: every slot was waiting'
    '[SAW-POINT] point=<n> frames=<n> lost<sawrows>'
    '[SAW-POINT] <u> player id(s) not kept: the saw maps hold <u> / <u>'
    '[CARD-EV] card draw evidence patches attached <u>/<u>: <cardhooks>'
    '[CARD-EV] census: <u> cards, digest <x>, pool class <=DefaultPool|unset><=|, CATEGORY NAME COLLISION (records read pool state collision)>'
    '[SEAT-EV] <=record|identity-clock record|compat outcome|card record|combat record> settled: <=recorded|already_recorded> (HTTP <u>, attempt <u>)'
    '[SEAT-EV] session ready: queued requests send while the mod stays disabled'
    '[SEAT-EV] no session within <u> s: queued requests kept for the next launch'
    '[SEAT-EV] queued requests not sent: no data consent'
    '[SEAT-EV] <u> closing file(s) moved into the queue'
    '[SEAT-EV] queue full: the oldest queued request was dropped'
    '[COMBAT-EV] combat evidence patches attached <u>/<u>: <combhooks>; frame <u>/<u>; producers<producers>'
    '[IDENTITY-CLOCK] patches attached <u>/<u>: <ichooks>'
    '[IDENTITY-CLOCK] quit flush ran: <u> capture(s), <u> kept for the next launch'
    '[BUILD-PROP] staged cr_build=<build> pre-join (tick, state=<@pstate>)'
    '[BUILD-PROP] not staged: the build tuple is outside its limits (<u> chars)'
    '[PEER-BUILD] actor=<actor> keys=<u> ours=<=none|><ours> list=<pkeys><plines> <pvals>'
    '^[PEER-BUILD] actor=<actor> list(<u>/<u>)=<pkeys>'
    '^[Message:   BepInEx] BepInEx <ver> - ROUNDS (<date>)'
)
function FormList([string]$set, [string]$sep) { $s = FormSet $set; return '(?:' + $s + '(?:' + [regex]::Escape($sep) + $s + ')*)' }
$FormPh.problems = '(?: problems=' + (FormList 'problem' ',') + ')?'
$FormPh.spans = '(?: (?:live|between|pick|over|menu)\.(?:in|out)\.(?:gated|upkeep|replay)=[0-9]{1,19}/[0-9]{1,19})*'
$FormPh.cloudtail = '(?:/\*)?'
$FormPh.gateex = '(?:' + (FormList 'gateex' ',') + ')?'
$FormPh.rwhy = '(?:quit|game-?[0-9]{1,6})'
$FormPh.pairs = '(?: ' + $FormPh.pair + '=[0-9]{1,19})*'
$FormPh.hprows = '(?: p[0-9]{1,4}\(team -?[0-9]{1,4}\)=' + $FormPh.f2 + '/' + $FormPh.f2 + '(?: dead)?)*'
$FormPh.sawrows = '(?: p[0-9]{1,4}=' + $FormPh.f2 + ')*'
$FormPh.cardhooks = '(?:C[0-9]{1,2} ' + (FormSet 'cardhook') + '(?:, C[0-9]{1,2} ' + (FormSet 'cardhook') + ')*)?'
$FormPh.combhooks = '(?:' + (FormList 'combhook' ', ') + ')?'
$FormPh.producers = '(?: ' + (FormSet 'producer') + ')*'
$FormPh.ichooks = '(?:' + (FormList 'ichook' ', ') + ')?'
$FormPh.ours = '(?:[0-9]{1,4})?'
$FormPh.plines = '(?: lines=[0-9]{1,4})?'
$FormPh.wfull = '(?: medF=-?[0-9]{1,19} e4=-?[0-9]{1,19},-?[0-9]{1,19} e8=-?[0-9]{1,19},-?[0-9]{1,19} e16=-?[0-9]{1,19},-?[0-9]{1,19})?'
$FormPh.cg = '(?:-?[0-9]{1,19}|NA)'
$FormPh.n10 = '(?:-?[0-9]{1,19},){9}-?[0-9]{1,19}'
$FormPh.u10 = '(?:[0-9]{1,19},){9}[0-9]{1,19}'
# wu: type:units:cycles per writer type, ";"-joined (cycles NA while a scope's cycles are not measured, B11 D5); tok:
# type:open0,enqON,enqOFF,doneON,doneOFF,disc,open1 per writer type, ";"-joined. The type of both is a token of the
# one closed set wtype; an empty wu (and tok) is a window with no writer type
$FormPh.wu = '(?:' + (FormSet 'wtype') + ':[0-9]{1,19}:(?:-?[0-9]{1,19}|NA)(?:;' + (FormSet 'wtype') + ':[0-9]{1,19}:(?:-?[0-9]{1,19}|NA))*)?'
$FormPh.tok = '(?:' + (FormSet 'wtype') + ':(?:-?[0-9]{1,19},){6}-?[0-9]{1,19}(?:;' + (FormSet 'wtype') + ':(?:-?[0-9]{1,19},){6}-?[0-9]{1,19})*)?'
$FormPh.ver = '[0-9]{1,4}(?:\.[0-9]{1,4}){1,3}'
$FormPh.date = '[0-9]{1,4}[/.-][0-9]{1,4}[/.-][0-9]{1,4} [0-9]{1,2}:[0-9]{2}:[0-9]{2}(?: [AP]M)?'
$FormPrefix = '\[(?:Info   |Message|Warning|Error  |Debug  |Fatal  ):(?:Competitive ROUNDS|CompetitiveRounds)\] '

function FormRegex([string]$t) {
    # one form's text to its anchored regex: literal text escaped, each placeholder replaced by its closed pattern
    $bare = $t.StartsWith('^')
    if ($bare) { $t = $t.Substring(1) }
    $sb = New-Object System.Text.StringBuilder
    $pos = 0
    foreach ($m in [regex]::Matches($t, '<(@?)([a-z0-9]+)>|<=([^>]*)>')) {
        [void]$sb.Append([regex]::Escape($t.Substring($pos, $m.Index - $pos)))
        if ($m.Groups[3].Success) { [void]$sb.Append('(?:' + ((@($m.Groups[3].Value -split '\|', -1) | ForEach-Object { [regex]::Escape($_) }) -join '|') + ')') }
        elseif ($m.Groups[1].Value -eq '@') { [void]$sb.Append((FormSet $m.Groups[2].Value)) }
        else {
            if (-not $FormPh.ContainsKey($m.Groups[2].Value)) { throw "form placeholder <$($m.Groups[2].Value)> is not defined" }
            [void]$sb.Append($FormPh[$m.Groups[2].Value])
        }
        $pos = $m.Index + $m.Length
    }
    [void]$sb.Append([regex]::Escape($t.Substring($pos)))
    return New-Object System.Text.RegularExpressions.Regex(('^' + $(if ($bare) { '' } else { $FormPrefix }) + $sb.ToString() + '$'),
        [System.Text.RegularExpressions.RegexOptions]::CultureInvariant)
}
$Forms = @($FormText | ForEach-Object { FormRegex $_ })

function WriterTypes([string]$v) {
    # the writer types of a wu= or tok= value ("type:...;type:..."), sorted and ";"-joined; $null when one is there twice
    $seen = New-Object 'System.Collections.Generic.HashSet[string]' ([System.StringComparer]::Ordinal)
    if ($v -ne '') {
        foreach ($e in $v.Split(';')) { if (-not $seen.Add($e.Split(':')[0])) { return $null } }
    }
    $k = [string[]]@($seen)
    [System.Array]::Sort($k, [System.StringComparer]::Ordinal)
    return ($k -join ';')
}

function WindowKeysRefused([string]$ln) {
    # B11 SHARED.md "The window line": a window line that carries any key twice is refused, a top-level key or a
    # writer type inside wu= or tok=, and so is one whose tok= writer types are not exactly its wu= ones. The window
    # form's fixed order admits no top-level key twice already; this check holds that apart from the form text, and
    # it is the only check of the writer types (a regex does not compare two lists). The self-test's no_wkeys mutant
    # skips it (the negative control of $WFormCases)
    if ($script:Mutant -eq 'no_wkeys') { return $false }
    $i = $ln.IndexOf('[FRAME-TIME] w ')
    if ($i -lt 0) { return $false }
    $seen = New-Object 'System.Collections.Generic.HashSet[string]' ([System.StringComparer]::Ordinal)
    $wu = ''; $tok = ''
    foreach ($t in $ln.Substring($i + 15).Split(' ')) {
        $e = $t.IndexOf('=')
        if ($e -lt 1) { return $true }
        $k = $t.Substring(0, $e)
        if (-not $seen.Add($k)) { return $true }
        if ($k -ceq 'wu') { $wu = $t.Substring($e + 1) } elseif ($k -ceq 'tok') { $tok = $t.Substring($e + 1) }
    }
    $a = WriterTypes $wu; $b = WriterTypes $tok
    return ($null -eq $a) -or ($null -eq $b) -or ($a -cne $b)
}

function Exportable([string]$ln) {
    # the export rule: true only when the whole line matches one form, and a window line also passes
    # WindowKeysRefused (the self-test's export_all mutant is the negative control: it exports every selected line,
    # as the substring selection did)
    if ($script:Mutant -eq 'export_all') { return $true }
    foreach ($f in $Forms) { if ($f.IsMatch($ln)) { return -not (WindowKeysRefused $ln) } }
    return $false
}

function SliceExport([string[]]$lines) {
    # the selection and the export of step 4, on the log's lines: Slice (every selected line, for slice.log), Count
    # (per class), Log (the "=== log lines" section's lines: exported [FRAME-TIME] lines, window lines included, then its
    # withheld counts), Comp (the component slice's exported lines, then its withheld counts) and CompAll (the number
    # of selected lines without [FRAME-TIME])
    $r = @{ Slice = New-Object System.Collections.Generic.List[string]; Count = [ordered]@{}
        Log = New-Object System.Collections.Generic.List[string]; Comp = New-Object System.Collections.Generic.List[string]; CompAll = 0 }
    $wLog = [ordered]@{}; $wComp = [ordered]@{}
    foreach ($cls in $SliceClasses) { $r.Count[$cls] = 0; $wLog[$cls] = 0; $wComp[$cls] = 0 }
    foreach ($ln in $lines) {
        $hit = @($SliceClasses | Where-Object { $ln.Contains($_) })
        if ($hit.Count -eq 0) { continue }
        foreach ($cls in $hit) { $r.Count[$cls]++ }
        $r.Slice.Add($ln)
        $ft = $ln.Contains('[FRAME-TIME]')
        # the self-test's drop_w mutant restores the skip the window lines had before ruling R6-A3.11.133 (2)
        if ($script:Mutant -eq 'drop_w' -and $ft -and $ln.Contains('[FRAME-TIME] w ')) { continue }
        if (-not $ft) { $r.CompAll++ }
        if (Exportable $ln) { if ($ft) { $r.Log.Add($ln) } else { $r.Comp.Add($ln) } }
        else { foreach ($cls in $hit) { if ($ft) { $wLog[$cls]++ } else { $wComp[$cls]++ } } }
    }
    foreach ($cls in $SliceClasses) {
        if ($wLog[$cls] -gt 0) { $r.Log.Add(("withheld {0} {1}" -f $cls.Trim('[', ']'), $wLog[$cls])) }
        if ($wComp[$cls] -gt 0) { $r.Comp.Add(("withheld {0} {1}" -f $cls.Trim('[', ']'), $wComp[$cls])) }
    }
    return $r
}

$script:Out = New-Object System.Collections.Generic.List[string]
# Console.Out, never the output stream: a function's output-stream writes would become part of its return value
function Say([string]$s) { $script:Out.Add($s); [Console]::Out.WriteLine($s) }
function Print([string]$s) { [Console]::Out.WriteLine($s) }

function Sha([string]$p) {
    if (Test-Path -LiteralPath $p -PathType Leaf) { return (Get-FileHash -Algorithm SHA256 -LiteralPath $p).Hash.ToLowerInvariant() }
    return 'absent'
}

# ---- the cfg's restored kind: a port of ft_cfg_compare.py's rule (ruling R6-A3.11.105 (3)). The lines are cut as
# that file cuts them (at CR LF, at LF and at a lone CR, each keeping its terminator; a last line without one is a
# line); each is decoded as strict UTF-8 (the first line's U+FEFF dropped) and trimmed of what Python's str.strip()
# trims (an explicit set: .NET's Trim() leaves U+001C to U+001F); its kind is blank, comment ("#"), section ("[" and
# "]") or key (holds "="), and any other line is REFUSED. RESTORED-KIND when the two files differ, their lines that are
# not comment lines are byte-identical and in the same order, and both or neither start with the BOM;
# NOT-RESTORED-KIND otherwise (the two files byte-identical included)
$CfgSpace = [char[]](@(9, 10, 11, 12, 13, 28, 29, 30, 31, 32, 0x85, 0xA0, 0x1680) + @(0x2000..0x200A) + @(0x2028, 0x2029, 0x202F, 0x205F, 0x3000))
$CfgUtf8 = New-Object System.Text.UTF8Encoding($false, $true)

function CfgShape([byte[]]$raw) {
    # $null when a line is not UTF-8 or of no kind (REFUSED); else "L:" and the hex of every line that is not a
    # comment line, its terminator included, joined by "|"
    $kept = New-Object System.Collections.Generic.List[string]
    $start = 0
    $n = $raw.Length
    for ($i = 0; $i -lt $n; $i++) {
        $end = -1
        if ($raw[$i] -eq 13) { if ($i + 1 -lt $n -and $raw[$i + 1] -eq 10) { $i++ }; $end = $i }
        elseif ($raw[$i] -eq 10) { $end = $i }
        elseif ($i -eq $n - 1) { $end = $i }
        if ($end -lt 0) { continue }
        $len = $end - $start + 1
        try { $t = $CfgUtf8.GetString($raw, $start, $len) } catch { return $null }
        if ($start -eq 0 -and $t.Length -gt 0 -and [int]$t[0] -eq 0xFEFF) { $t = $t.Substring(1) }
        $s = $t.Trim($CfgSpace)
        $k = ''
        if ($s.Length -eq 0) { $k = 'blank' }
        elseif ([int]$s[0] -eq 35) { $k = 'comment' }
        elseif ([int]$s[0] -eq 91 -and [int]$s[$s.Length - 1] -eq 93) { $k = 'section' }
        elseif ($s.IndexOf([char]61) -ge 0) { $k = 'key' }
        if ($k -eq '') { return $null }
        if ($k -ne 'comment') { $kept.Add([BitConverter]::ToString($raw, $start, $len)) }
        $start = $end + 1
    }
    return 'L:' + ($kept -join '|')
}

function HasBom([byte[]]$r) { return $r.Length -ge 3 -and $r[0] -eq 0xEF -and $r[1] -eq 0xBB -and $r[2] -eq 0xBF }

function CfgKind([string]$a, [string]$b) {
    # <pre-image cfg> <sitting cfg>: RESTORED-KIND, NOT-RESTORED-KIND or REFUSED; never throws
    try {
        $ra = [System.IO.File]::ReadAllBytes($a)
        $rb = [System.IO.File]::ReadAllBytes($b)
        $sa = CfgShape $ra
        $sb = CfgShape $rb
        if ($null -eq $sa -or $null -eq $sb) { return 'REFUSED' }
        if ([Convert]::ToBase64String($ra) -ceq [Convert]::ToBase64String($rb)) { return 'NOT-RESTORED-KIND' }
        if ($sa -ceq $sb -and (HasBom $ra) -eq (HasBom $rb)) { return 'RESTORED-KIND' }
        return 'NOT-RESTORED-KIND'
    }
    catch { return 'REFUSED' }
}

function ReadShared([string]$p) {
    # the game holds LogOutput.log open: read it with ReadWrite sharing
    if (-not (Test-Path -LiteralPath $p -PathType Leaf)) { return @() }
    $fs = [System.IO.File]::Open($p, 'Open', 'Read', 'ReadWrite')
    try { $sr = New-Object System.IO.StreamReader($fs); $t = $sr.ReadToEnd() } finally { $fs.Dispose() }
    return $t -split "`r?`n"
}

function NewCtx([string]$game, [string]$seat, [string]$low) {
    $bep = Join-Path $game 'BepInEx'
    $pl = Join-Path $low 'Landfall Games\ROUNDS'
    foreach ($pub in @('Landfall Games', 'Landfall')) {
        $d = Join-Path $low ($pub + '\ROUNDS')
        if (Test-Path -LiteralPath (Join-Path $d 'Player.log')) { $pl = $d; break }
    }
    $logs = [ordered]@{
        'LogOutput.log'      = (Join-Path $bep 'LogOutput.log')
        'LogOutput-prev.log' = (Join-Path $bep 'LogOutput-prev.log')
        'output_log.txt'     = (Join-Path $game 'output_log.txt')
        'Player.log'         = (Join-Path $pl 'Player.log')
        'Player-prev.log'    = (Join-Path $pl 'Player-prev.log')
    }
    return @{
        Game = $game; Seat = $seat; Bep = $bep; Config = (Join-Path $bep 'config')
        Cfg = (Join-Path $bep 'config\com.competitiverounds.mod.cfg')
        Dll = (Join-Path $bep 'plugins\CompetitiveRounds\CompetitiveRounds.dll')
        Arm = (Join-Path $bep 'frametime\arm'); Logs = $logs
    }
}

function Vr6Listing($C) {
    if (-not (Test-Path -LiteralPath $C.Config -PathType Container)) { throw "config folder missing: $($C.Config)" }
    $l = [ordered]@{}
    foreach ($n in $Vr6Named) { $l[$n] = Sha (Join-Path $C.Config $n) }
    foreach ($pat in $Vr6Patterns) {
        foreach ($f in @(Get-ChildItem -LiteralPath $C.Config -Filter $pat -File | Sort-Object Name)) { $l[$f.Name] = Sha $f.FullName }
    }
    return $l
}

# ---- step 1
function Step1($C, [string]$run) {
    $pre = Join-Path $run 'pre'
    New-Item -ItemType Directory -Force -Path $pre | Out-Null
    $p = @{ Logs = [ordered]@{}; Cfg = (Sha $C.Cfg); Vr6 = (Vr6Listing $C); Run = $run }
    if ($p.Cfg -eq 'absent') { throw "the cfg is missing: $($C.Cfg)" }
    Copy-Item -LiteralPath $C.Cfg -Destination (Join-Path $pre 'com.competitiverounds.mod.cfg')
    foreach ($k in $C.Logs.Keys) {
        $s = Sha $C.Logs[$k]
        $p.Logs[$k] = $s
        if ($s -ne 'absent') { Copy-Item -LiteralPath $C.Logs[$k] -Destination (Join-Path $pre $k) }
        if ($s -ne 'absent' -and (Sha (Join-Path $pre $k)) -ne $s) { throw "the pre-image copy of $k differs from its source" }
        Say ("pre-image {0} {1} {2}" -f $k, $s, $C.Logs[$k])
    }
    Say ("pre-image cfg {0}" -f $p.Cfg)
    foreach ($k in $p.Vr6.Keys) { Say ("vr6 first {0} {1}" -f $k, $p.Vr6[$k]) }
    $dll = Sha $C.Dll
    $lanes = @()
    $inc = Join-Path $C.Seat 'incoming'
    if (Test-Path -LiteralPath $inc) {
        foreach ($d in @(Get-ChildItem -LiteralPath $inc -Directory -Filter 'frametime-*')) {
            $f = Join-Path $d.FullName 'sha256.txt'
            if (-not (Test-Path -LiteralPath $f)) { continue }
            $m = [regex]::Match((Get-Content -LiteralPath $f -TotalCount 1), '^[0-9a-fA-F]{64}')
            if ($m.Success -and $m.Value.ToLowerInvariant() -eq $dll) { $lanes += $d.Name }
        }
    }
    Say ("installed dll {0}; staged FrameTime lanes with that digest: {1}" -f $dll, ($(if ($lanes.Count) { $lanes -join ',' } else { 'none' })))
    $p.Dll = $dll
    $p.LaneOk = $lanes.Count -ge 1
    return $p
}

# ---- step 4
function Step4($C, $p) {
    $lines = ReadShared $C.Logs['LogOutput.log']
    $sel = SliceExport $lines
    Say '=== log lines'
    foreach ($ln in $sel.Log) { Say $ln }
    if ($script:Mutant -eq 'throw_in_step4') { throw 'mutant throw_in_step4: an error inside step 4' }
    $slice = $sel.Slice
    $count = $sel.Count
    $sp = Join-Path $p.Run 'slice.log'
    [System.IO.File]::WriteAllLines($sp, $slice)
    Say '=== saved slice'
    foreach ($cls in $SliceClasses) { Say ("slice class {0}: {1} lines" -f $cls.Trim('[', ']'), $count[$cls]) }
    Say ("slice saved: {0} lines, sha256 {1}" -f $slice.Count, (Sha $sp))
    # the component evidence itself (3.11): the saved-slice lines without [FRAME-TIME] that the export rule admits
    # (the [FRAME-TIME] lines, the window lines among them, are under "=== log lines" already)
    if ($script:Mutant -ne 'no_component_slice') {
        Say '=== component slice'
        $nw = @($sel.Comp | Where-Object { $_.StartsWith('withheld ') }).Count
        Say ("component slice: {0} of {1} saved-slice lines without [FRAME-TIME] exported, the rest withheld by class" -f ($sel.Comp.Count - $nw), $sel.CompAll)
        foreach ($ln in $sel.Comp) { Say $ln }
    }
    Say '=== VR6'
    $after = Vr6Listing $C
    $bad = @()
    foreach ($k in (@($p.Vr6.Keys) + @($after.Keys) | Sort-Object -Unique)) {
        $a = if ($p.Vr6.Contains($k)) { $p.Vr6[$k] } else { 'absent' }
        $b = if ($after.Contains($k)) { $after[$k] } else { 'absent' }
        Say ("vr6 {0} {1} -> {2}{3}" -f $k, $a, $b, $(if ($a -ne $b) { ' CHANGED' } else { '' }))
        if ($a -ne $b) { $bad += $k }
    }
    $prev = Sha $C.Logs['LogOutput-prev.log']
    if ($prev -ne $p.Logs['LogOutput-prev.log']) { $bad += 'LogOutput-prev.log (changed during the sitting)' }
    Say ("vr6 LogOutput-prev.log during the sitting {0} -> {1}" -f $p.Logs['LogOutput-prev.log'], $prev)
    if ($bad.Count) { Say ('VR6 files FAIL: ' + ($bad -join '; ')) } else { Say 'VR6 files PASS (route counts: the parser reads the refusals lines above)' }
    return $bad.Count -eq 0
}

# ---- step 5
function Step5($C, $p) {
    $pre = Join-Path $p.Run 'pre'
    $sit = Join-Path $p.Run 'sitting'
    Say '=== restored'
    $ok = $true
    $script:RestoredEqual = 0
    try {
        New-Item -ItemType Directory -Force -Path $sit | Out-Null
        foreach ($k in $C.Logs.Keys) {
            # each log on its own: one log's error leaves the others' restore and comparison standing
            try {
                $path = $C.Logs[$k]
                if (Test-Path -LiteralPath $path -PathType Leaf) { Move-Item -LiteralPath $path -Destination (Join-Path $sit $k) -Force }
                if ($p.Logs[$k] -ne 'absent') { Copy-Item -LiteralPath (Join-Path $pre $k) -Destination $path }
                $r = Sha $path
                $eq = $r -eq $p.Logs[$k]
                if (-not $eq) { $ok = $false } else { $script:RestoredEqual++ }
                Say ("restored {0} {1} pre {2} {3}" -f $k, $r, $p.Logs[$k], $(if ($eq) { 'equal' } else { 'DIFFERENT' }))
            }
            catch { $ok = $false; Say ("restored {0} error: {1} DIFFERENT" -f $k, $_.Exception.Message) }
        }
    }
    finally {
        # the cfg goes back whatever happened to the logs
        try {
            if ((Sha $C.Cfg) -ne $p.Cfg) {
                # keep the in-sitting cfg for a by-kind comparison; a failed keep must not stop the restore below
                try {
                    New-Item -ItemType Directory -Force -Path $sit | Out-Null
                    Copy-Item -LiteralPath $C.Cfg -Destination (Join-Path $sit 'com.competitiverounds.mod.cfg') -Force
                    Say ("kept cfg {0}" -f (Sha (Join-Path $sit 'com.competitiverounds.mod.cfg')))
                    # the by-kind verdict, made here: the kept copy and its values stay on the laptop
                    $kind = CfgKind (Join-Path $pre 'com.competitiverounds.mod.cfg') (Join-Path $sit 'com.competitiverounds.mod.cfg')
                    Say ("kept cfg kind {0}" -f $(if ($kind -ceq 'RESTORED-KIND') { 'RESTORED-KIND' } else { 'NOT-RESTORED-KIND' }))
                }
                catch { Say ("kept cfg error: {0}" -f $_.Exception.Message) }
                Copy-Item -LiteralPath (Join-Path $pre 'com.competitiverounds.mod.cfg') -Destination $C.Cfg -Force
            }
            $rc = Sha $C.Cfg
            if ($rc -ne $p.Cfg) { $ok = $false } else { $script:RestoredEqual++ }
            Say ("restored cfg {0} pre {1} {2}" -f $rc, $p.Cfg, $(if ($rc -eq $p.Cfg) { 'equal' } else { 'DIFFERENT' }))
        }
        catch { $ok = $false; Say ("restored cfg error: {0} DIFFERENT" -f $_.Exception.Message) }
    }
    # the positive proof: no failure seen AND one "equal" line for every log and for the cfg
    return $ok -and $script:RestoredEqual -eq ($C.Logs.Count + 1)
}

function NewRun([string]$seat) {
    $stamp = (Get-Date).ToUniversalTime().ToString('yyyyMMdd-HHmmss')
    $run = Join-Path $seat ('runs\' + $stamp)
    if (Test-Path -LiteralPath $run) { throw "run folder exists: $run" }
    New-Item -ItemType Directory -Force -Path $run | Out-Null
    Say ('runs/' + $stamp)
    return $run
}

# ---- steps 2 to 5, one structure for the sitting and the self-test. $Launch ($C) returns the game process or
# nothing; $Wait ($C, $proc) returns whether the sitting completed; $Shutdown ($proc) prints a line starting
# "shutdown:". Every cleanup sits in its own finally; errors are caught after their cleanup ran and become exit codes.
function Sitting($C, $p, [scriptblock]$Launch, [scriptblock]$Wait, [scriptblock]$Shutdown) {
    $st = @{ Code = 0; Proc = $null; V = $false; R = $false }
    try {
        try {
            try {
                New-Item -ItemType Directory -Force -Path (Split-Path $C.Arm) | Out-Null
                # -ArmForce ON (sitting V) adds a third line force=ON; none keeps the two lines of sitting C
                $armLines = @("seed=$Seed", "f18=$F18")
                if ($ArmForce -eq 'ON') { $armLines += 'force=ON' }
                Set-Content -LiteralPath $C.Arm -Value $armLines -Encoding ascii
                Say ("sentinel written: seed={0} f18={1}{2}" -f $Seed, $F18, $(if ($ArmForce -eq 'ON') { ' force=ON' } else { '' }))
                $st.Proc = & $Launch $C
                if (-not $st.Proc) { Say 'launch: no ROUNDS process within 120 s'; $st.Code = 3 }
                else {
                    Say ("launched pid {0}" -f $st.Proc.Id)
                    if (-not (& $Wait $C $st.Proc)) { $st.Code = 3 }
                }
            }
            finally {
                try { & $Shutdown $st.Proc }
                catch { Say ('shutdown error: ' + $_.Exception.Message); $st.Code = 3 }
            }
        }
        finally {
            if (Test-Path -LiteralPath $C.Arm) { Remove-Item -LiteralPath $C.Arm -Force }
            Say ("sentinel removed: {0}" -f (-not (Test-Path -LiteralPath $C.Arm)))
        }
    }
    catch { Say ('sitting error (launch, wait or sentinel): ' + $_.Exception.Message); $st.Code = 3 }
    try {
        try { $st.V = Step4 $C $p }
        catch { Say ('step 4 error: ' + $_.Exception.Message); $st.V = $false }
    }
    finally {
        try { $st.R = Step5 $C $p }
        catch { Say ('step 5 error: ' + $_.Exception.Message); $st.R = $false }
    }
    # the restore proof (ruling R6-A3.11.112 F1): one line, printed whatever step 5 did. Step5 returns true only when
    # every log and the cfg printed a "restored ... equal" line and nothing failed, so exit 4 (and 0) need that
    # positive proof; a failed or unproven restore is exit 5, which also replaces 3 (no reader of the job's result
    # tells 3 from 5: both are refused, and 5 names the state that needs action, files not put back)
    if ($st.R) { Say ("RESTORE-PROOF ok {0}" -f $script:RestoredEqual) } else { Say 'RESTORE-PROOF FAILED' }
    if (-not $st.R) { $st.Code = 5 }
    elseif ($st.Code -eq 0 -and -not $st.V) { $st.Code = 4 }
    return $st
}

# ---- the self-test
# the self-test's own reading of the kept copy: it differs from the pre-image, and their lines that are not comment
# lines (trimmed, starting with "#") are equal and in the same order. It is not the binding comparison (that is
# CfgKind, whose agreement with ft_cfg_compare.py ft_cfg_kind_agree.py proves); this reading only proves the
# self-test's fixture
function CommentOnlyDiff([string]$a, [string]$b) {
    if ((Sha $a) -eq 'absent' -or (Sha $b) -eq 'absent' -or (Sha $a) -eq (Sha $b)) { return $false }
    $x = @([System.IO.File]::ReadAllLines($a) | Where-Object { -not $_.Trim().StartsWith('#') })
    $y = @([System.IO.File]::ReadAllLines($b) | Where-Object { -not $_.Trim().StartsWith('#') })
    if ($x.Count -ne $y.Count) { return $false }
    for ($i = 0; $i -lt $x.Count; $i++) { if ($x[$i] -cne $y[$i]) { return $false } }
    return $true
}

# the self-test's cfg: its bytes from a BOM flag and lines that carry their own terminators
function CfgFixture([bool]$bom, [string[]]$lines) {
    $b = [System.Text.Encoding]::UTF8.GetBytes((-join $lines))
    if ($bom) { $b = [byte[]](@(0xEF, 0xBB, 0xBF) + $b) }
    return , $b
}
$CfgBase = @("## Settings file was created by plugin Competitive Rounds`r`n", "## Plugin GUID: com.competitiverounds.mod`r`n",
    "`r`n", "[Data]`r`n", "`r`n", "AutoLogUpload = true`r`n", "KeyA = 1`r`n", "KeyB = 2`r`n", "`r`n", "[Other]`r`n", "`r`n", "KeyC = 3`r`n")
function CfgEdit([int]$at, [int]$drop, [string[]]$add) {
    # $CfgBase with $drop lines from index $at replaced by $add
    $r = @()
    if ($at -gt 0) { $r += $CfgBase[0..($at - 1)] }
    $r += $add
    if ($at + $drop -lt $CfgBase.Count) { $r += $CfgBase[($at + $drop)..($CfgBase.Count - 1)] }
    return , $r
}
# the cfg mutants: the in-sitting cfg each writes, and the kind line wanted ('' = no kind line: the keep fails)
$CfgCases = [ordered]@{
    cfg_comment         = @{ Bom = $true; Lines = (CfgEdit 12 0 @("## a comment line the sitting wrote`r`n")); Want = 'RESTORED-KIND' }
    cfg_keep_fails      = @{ Bom = $true; Lines = (CfgEdit 12 0 @("## a comment line the sitting wrote`r`n")); Want = '' }
    cfg_value           = @{ Bom = $true; Lines = (CfgEdit 6 1 @("KeyA = 9`r`n")); Want = 'NOT-RESTORED-KIND' }
    cfg_key_added       = @{ Bom = $true; Lines = (CfgEdit 8 0 @("KeyD = 4`r`n")); Want = 'NOT-RESTORED-KIND' }
    cfg_key_removed     = @{ Bom = $true; Lines = (CfgEdit 7 1 @()); Want = 'NOT-RESTORED-KIND' }
    cfg_keys_swapped    = @{ Bom = $true; Lines = (CfgEdit 6 2 @("KeyB = 2`r`n", "KeyA = 1`r`n")); Want = 'NOT-RESTORED-KIND' }
    cfg_blank_added     = @{ Bom = $true; Lines = (CfgEdit 8 0 @("`r`n")); Want = 'NOT-RESTORED-KIND' }
    cfg_crlf_lf         = @{ Bom = $true; Lines = (CfgEdit 6 1 @("KeyA = 1`n")); Want = 'NOT-RESTORED-KIND' }
    cfg_bom_removed     = @{ Bom = $false; Lines = $CfgBase; Want = 'NOT-RESTORED-KIND' }
    cfg_section_renamed = @{ Bom = $true; Lines = (CfgEdit 9 1 @("[Renamed]`r`n")); Want = 'NOT-RESTORED-KIND' }
    cfg_non_grammar     = @{ Bom = $true; Lines = (CfgEdit 8 0 @("a line of no kind`r`n")); Want = 'NOT-RESTORED-KIND' }
}

# the self-test's LogOutput.log of the sitting (F2): [FRAME-TIME] lines and one line per other class in the forms the
# mod writes (each must be exported in its section), the point's window lines (exported), lines of the classes no form
# admits (each withheld), and planted cfg-like values holding each class word, the BaseUrl's startup line, the
# COMBAT-PERF probe mode and a route host among them (each withheld: no ".example" may be printed anywhere)
$SimPre = '[Info   :CompetitiveRounds] '
$SimFt = @(
    ($SimPre + '[FRAME-TIME] build variant=FrameTime'),
    ($SimPre + '[FRAME-TIME] cal i=0 why=start kind=entries reference=1 built=0'),
    ($SimPre + '[FRAME-TIME] mark cost cyc=41 p90=57 n=4096'),
    ($SimPre + '[FRAME-TIME] settled g=-1 seed=1 c_plant=-1 W=120 vsync=0 target=-1 freq=10000000 hires=1 f_hat=2978789260 gc_incremental=1 gc_slice_ns=3000000 f18=A answer=replay armfile=1 force=none clock=1 frames=0 missing_end=0 cycle_failures=0 span_depth_violations=0'),
    ($SimPre + '[FRAME-TIME] p pt=1.1.1 arm=ON gate=0 pred=none n=500 sF=1 sS=1 sC=1 maxF=1 pn=0 psF=0 psS=0 psC=0 sP=1 psP=0 excl=0 plant_mixed=0 windows=4 live_frames=501 missing_end=0 span_g=0 span_gn=0 span_u=0 span_un=0 on_calls=0 guarded=0 zs=0 zl=1 t0=1 t1=2 answer=replay'),
    ($SimPre + '[FRAME-TIME] refusals why=quit pairs=2 closing:e=1 route:GET_192.168.72.102/api/{n}/mod-version=1'))
# the point's four window lines (its p line counts windows=4), each exported: full and partial, planted and not, a
# plant run and not, cG measured and NA, wu cycles measured and NA, both writer types in either order, one type, and an
# empty wu with its empty tok
$SimWTail = ' q=5,-1,0,0,0,0,0,0,0,7 r=1,0,0,0,0,0,0,0,0,2 qn=12,12,12,12,12,12,12,12,12,12'
$SimWindow = @(
    ($SimPre + '[FRAME-TIME] w pt=1.1.1 arm=ON plant=0 partial=0 n=120 sF=9 sS=1 sC=11 sP=0 maxF=4 medF=1 e4=0,1 e8=0,0 e16=0,0 gc=0 run=0 pos=1 unit=P13 coin=1 wi=0 f0=12 pred=none prun=0 res=0 gcn=0 cG=NA cW=0 cR=3 cS=0 cE=0' + $SimWTail + ' wu=log:2:340;hash:1:NA tok=log:0,1,0,1,0,0,0;hash:1,0,1,0,1,0,1 nm=4'),
    ($SimPre + '[FRAME-TIME] w pt=1.1.1 arm=OFF plant=1 partial=0 n=120 sF=9 sS=1 sC=11 sP=0 maxF=4 medF=1 e4=0,1 e8=0,0 e16=0,0 gc=1 run=0 pos=2 unit=P24 coin=0 wi=1 f0=132 pred=ON prun=1 res=0 gcn=1 cG=812 cW=0 cR=3 cS=0 cE=0' + $SimWTail + ' wu= tok= nm=0'),
    ($SimPre + '[FRAME-TIME] w pt=1.1.1 arm=OFF plant=0 partial=0 n=120 sF=9 sS=1 sC=11 sP=0 maxF=4 medF=1 e4=0,1 e8=0,0 e16=0,0 gc=0 run=0 pos=3 unit=P13 coin=1 wi=2 f0=252 pred=OFF prun=1 res=0 gcn=0 cG=0 cW=0 cR=3 cS=0 cE=0' + $SimWTail + ' wu=hash:1:12;log:3:96 tok=log:1,2,1,2,1,0,1;hash:0,1,0,1,0,0,0 nm=2'),
    ($SimPre + '[FRAME-TIME] w pt=1.1.1 arm=ON plant=0 partial=1 n=30 sF=3 sS=1 sC=4 sP=0 maxF=4 gc=0 run=0 pos=4 unit=P24 coin=0 wi=3 f0=372 pred=OFF prun=0 res=1 gcn=0 cG=NA cW=0 cR=1 cS=0 cE=0 q=2,1,0,0,0,0,0,0,0,0 r=1,0,0,0,0,0,0,0,0,0 qn=12,12,6,0,0,0,0,0,0,0 wu=log:1:30 tok=log:0,1,0,1,0,0,0 nm=1'))
# the window form's case table (B11 SHARED.md "The window line"): Name, Line, Form (the form itself refuses it) and
# Keys (only WindowKeysRefused refuses it); each refused case sits beside its negative control (Form and Keys both
# false: exported), the same line without the defect. Run with the key check (mutant none) every refused case must
# be withheld and every control exported; with no_wkeys (the key check skipped) the Keys cases must be exported, the
# Form cases still withheld and the controls still exported
$WHead = $SimPre + '[FRAME-TIME] w pt=1.1.9 arm=ON plant=0 partial=0 n=120 sF=9 sS=1 sC=11 sP=0 maxF=4 medF=1 e4=0,1 e8=0,0 e16=0,0 gc=0 run=2 pos=1 unit=P13 coin=1 wi=8 f0=12 pred=none'
$WMid = ' gcn=0 cG=NA cW=0 cR=3 cS=0 cE=0' + $SimWTail
$WTokL = 'log:0,1,0,1,0,0,0'; $WTokH = 'hash:1,0,1,0,1,0,1'
$WFormCases = @(
    @{ Name = 'control'; Form = $false; Keys = $false; Line = $WHead + ' prun=0 res=0' + $WMid + ' wu=log:2:340;hash:1:NA tok=' + $WTokL + ';' + $WTokH + ' nm=4' }
    # the earlier form: the appended plant= (now prun=) and the appended partial=, together and each alone
    @{ Name = 'old_plant_partial'; Form = $true; Keys = $false; Line = $WHead + ' plant=0 res=0 partial=0' + $WMid + ' wu=log:2:340;hash:1:NA tok=' + $WTokL + ';' + $WTokH + ' nm=4' }
    @{ Name = 'old_plant'; Form = $true; Keys = $false; Line = $WHead + ' plant=0 res=0' + $WMid + ' wu=log:2:340;hash:1:NA tok=' + $WTokL + ';' + $WTokH + ' nm=4' }
    @{ Name = 'old_partial'; Form = $true; Keys = $false; Line = $WHead + ' prun=0 res=0 partial=0' + $WMid + ' wu=log:2:340;hash:1:NA tok=' + $WTokL + ';' + $WTokH + ' nm=4' }
    # the earlier tok, one list for the window, and no nm=
    @{ Name = 'old_tok'; Form = $true; Keys = $false; Line = $WHead + ' prun=0 res=0' + $WMid + ' wu=log:2:340 tok=0,1,0,1,0,0,0 nm=4' }
    @{ Name = 'no_nm'; Form = $true; Keys = $false; Line = $WHead + ' prun=0 res=0' + $WMid + ' wu=log:2:340;hash:1:NA tok=' + $WTokL + ';' + $WTokH }
    # a top-level key twice
    @{ Name = 'dup_top'; Form = $true; Keys = $false; Line = $WHead + ' prun=0 res=0' + $WMid + ' wu=log:2:340;hash:1:NA tok=' + $WTokL + ';' + $WTokH + ' nm=4 nm=4' }
    # a writer type twice, in wu and in tok (the type sets still equal), and its control in the other order
    @{ Name = 'dup_wu_type'; Form = $false; Keys = $true; Line = $WHead + ' prun=0 res=0' + $WMid + ' wu=log:2:340;hash:1:NA;log:1:5 tok=' + $WTokL + ';' + $WTokH + ' nm=4' }
    @{ Name = 'dup_tok_type'; Form = $false; Keys = $true; Line = $WHead + ' prun=0 res=0' + $WMid + ' wu=log:2:340;hash:1:NA tok=' + $WTokL + ';' + $WTokH + ';' + $WTokL + ' nm=4' }
    @{ Name = 'control_order'; Form = $false; Keys = $false; Line = $WHead + ' prun=0 res=0' + $WMid + ' wu=hash:1:NA;log:2:340 tok=' + $WTokL + ';' + $WTokH + ' nm=4' }
    # tok's writer types differ from wu's: one fewer, one more, the other one, and empty against a wu
    @{ Name = 'tok_fewer'; Form = $false; Keys = $true; Line = $WHead + ' prun=0 res=0' + $WMid + ' wu=log:2:340;hash:1:NA tok=' + $WTokL + ' nm=4' }
    @{ Name = 'tok_more'; Form = $false; Keys = $true; Line = $WHead + ' prun=0 res=0' + $WMid + ' wu=log:2:340 tok=' + $WTokL + ';' + $WTokH + ' nm=4' }
    @{ Name = 'tok_other'; Form = $false; Keys = $true; Line = $WHead + ' prun=0 res=0' + $WMid + ' wu=log:2:340 tok=' + $WTokH + ' nm=4' }
    @{ Name = 'tok_empty'; Form = $false; Keys = $true; Line = $WHead + ' prun=0 res=0' + $WMid + ' wu=log:2:340 tok= nm=4' }
    @{ Name = 'control_one'; Form = $false; Keys = $false; Line = $WHead + ' prun=0 res=0' + $WMid + ' wu=log:2:340 tok=' + $WTokL + ' nm=4' }
    @{ Name = 'control_empty'; Form = $false; Keys = $false; Line = $WHead + ' prun=0 res=0' + $WMid + ' wu= tok= nm=0' }
    # a writer type outside the one constant wtype
    @{ Name = 'type_outside'; Form = $true; Keys = $false; Line = $WHead + ' prun=0 res=0' + $WMid + ' wu=spool:2:340 tok=spool:0,1,0,1,0,0,0 nm=4' }
    # the mark-cost boot line and a defect of it
    @{ Name = 'control_mark'; Form = $false; Keys = $false; Line = $SimPre + '[FRAME-TIME] mark cost cyc=41 p90=57 n=4096' }
    @{ Name = 'mark_na'; Form = $true; Keys = $false; Line = $SimPre + '[FRAME-TIME] mark cost cyc=NA p90=57 n=4096' })
$SimForm = @(
    '[Message:   BepInEx] BepInEx 5.4.22.0 - ROUNDS (11/10/2026 7:38:18 AM)',
    ($SimPre + '[FPSCAP] held by frame-time calibration'),
    ($SimPre + '[COMBAT-PERF] probe on, mode menu, windows of 600 frames'),
    ($SimPre + '[HIT-EVIDENCE] keys refused at the caps: 1 point tally actor(s), 2 game tally actor(s) (cap 8), 3 projectile(s) (cap 64)'),
    ($SimPre + '[SEAT-EV] session ready: queued requests send while the mod stays disabled'),
    ($SimPre + '[HP-POINT-END] point=3 spectator=0 p1(team 0)=100.00/100.00 p2(team 1)=0.00/100.00 dead'),
    ($SimPre + '[SAW-POINT] point=3 frames=120 lost p1=0.50'),
    ($SimPre + '[IDENTITY-CLOCK] quit flush ran: 0 capture(s), 0 kept for the next launch'),
    ($SimPre + '[CARD-EV] census: 312 cards, digest 0123456789abcdef0123456789abcdef, pool class DefaultPool'),
    ($SimPre + '[COMBAT-EV] combat evidence patches attached 2/19: Gun.Attack, Block.TryBlock; frame 2/2; producers push death'),
    ($SimPre + '[PEER-BUILD] actor=2 keys=2 ours=2 list=cr_build,ft_dll cr_build=1.41.0|standalone|nosha cr_dc2=- cr_dc3=- cr_ffacfg=- cr_game_token_v=ft_a974aac8:1 cr_grow2=1 cr_msv2=- cr_pois2=1 cr_pois3=1 cr_prox1=- cr_saw1=1 cr_wcd1=1'),
    ($SimPre + '[BUILD-PROP] staged cr_build=1.41.0|standalone|nosha pre-join (tick, state=PeerCreated)'))
$SimNoForm = @(
    ($SimPre + '[SEAT-EV] record queued: 812 bytes, lists 1/2/3/4, unpaired 0/0, t0 m, end game_over'),
    ($SimPre + '[IDENTITY-CLOCK] record kept for the next launch: 3 captures'),
    ($SimPre + '[HARMONY] Failed to patch SomePatch: the target method is missing'),
    ($SimPre + 'series state: physical game 1 of this series was voided'))
$SimPlant = @($SliceClasses | ForEach-Object { $SimPre + 'API client initialized: https://' + $_ + '.example:8444' }) + @(
    ($SimPre + '[COMBAT-PERF] probe on, mode https://refused.example, windows of 600 frames'),
    ($SimPre + '[FRAME-TIME] refused what=route route=GET_refused.example/api/{n}/mod-version n=1'),
    ($SimPre + '[FRAME-TIME] refusals why=quit pairs=1 route:GET_voided.example/api/{n}/mod-version=1'),
    # window lines of another point (so no window count moves), each withheld: a writer type that is no token of the
    # closed set, the earlier form's appended plant= and partial=, a writer type twice, and a tok whose writer types
    # differ from wu's (the last two withheld by WindowKeysRefused alone: no_wkeys exports them)
    ($SimPre + '[FRAME-TIME] w pt=1.1.2 arm=ON plant=0 partial=1 n=30 sF=3 sS=1 sC=4 sP=0 maxF=4 gc=0 run=1 pos=1 unit=P13 coin=1 wi=4 f0=0 pred=none prun=0 res=0 gcn=0 cG=NA cW=0 cR=1 cS=0 cE=0 q=2,1,0,0,0,0,0,0,0,0 r=1,0,0,0,0,0,0,0,0,0 qn=12,12,6,0,0,0,0,0,0,0 wu=planted.example:1:1 tok=planted.example:0,0,0,0,0,0,0 nm=0'),
    ($SimPre + '[FRAME-TIME] w pt=1.1.2 arm=ON plant=0 partial=1 n=30 sF=3 sS=1 sC=4 sP=0 maxF=4 gc=0 run=1 pos=1 unit=P13 coin=1 wi=4 f0=0 pred=none plant=0 res=0 partial=1 gcn=0 cG=NA cW=0 cR=1 cS=0 cE=0 q=2,1,0,0,0,0,0,0,0,0 r=1,0,0,0,0,0,0,0,0,0 qn=12,12,6,0,0,0,0,0,0,0 wu=log:1:30 tok=log:0,1,0,1,0,0,0 nm=1'),
    ($SimPre + '[FRAME-TIME] w pt=1.1.2 arm=ON plant=0 partial=1 n=30 sF=3 sS=1 sC=4 sP=0 maxF=4 gc=0 run=1 pos=1 unit=P13 coin=1 wi=4 f0=0 pred=none prun=0 res=0 gcn=0 cG=NA cW=0 cR=1 cS=0 cE=0 q=2,1,0,0,0,0,0,0,0,0 r=1,0,0,0,0,0,0,0,0,0 qn=12,12,6,0,0,0,0,0,0,0 wu=log:1:30;log:1:30 tok=log:0,1,0,1,0,0,0;log:0,1,0,1,0,0,0 nm=1'),
    ($SimPre + '[FRAME-TIME] w pt=1.1.2 arm=ON plant=0 partial=1 n=30 sF=3 sS=1 sC=4 sP=0 maxF=4 gc=0 run=1 pos=1 unit=P13 coin=1 wi=4 f0=0 pred=none prun=0 res=0 gcn=0 cG=NA cW=0 cR=1 cS=0 cE=0 q=2,1,0,0,0,0,0,0,0,0 r=1,0,0,0,0,0,0,0,0,0 qn=12,12,6,0,0,0,0,0,0,0 wu=log:1:30 tok=hash:0,1,0,1,0,0,0 nm=1'))
# of $SimPlant, the lines only WindowKeysRefused withholds (the no_wkeys run exports exactly these)
$SimKeysOnly = 2
# F1's combined cases: VR6 fails and the restore fails; each must end exit 5 with "RESTORE-PROOF FAILED"
$RestoreFailCases = @('cfg_restore_locked', 'log_restore_fails', 'wait_restore_fails')
$CfgLocked = @{ Bom = $true; Lines = (CfgEdit 12 0 @("## a comment line the sitting wrote`r`n")); Want = 'RESTORED-KIND' }

function SelfTestOne([string]$root, [string]$mutant) {
    $script:Out = New-Object System.Collections.Generic.List[string]
    $game = Join-Path $root 'game'; $seat = Join-Path $root 'seat'; $low = Join-Path $root 'LocalLow'
    foreach ($d in @("$game\BepInEx\config", "$game\BepInEx\plugins\CompetitiveRounds", "$low\Landfall Games\ROUNDS",
            "$seat\incoming\frametime-0badc0de", "$seat\runs")) { New-Item -ItemType Directory -Force -Path $d | Out-Null }
    $C = NewCtx $game $seat $low
    [System.IO.File]::WriteAllBytes($C.Cfg, (CfgFixture $true $CfgBase))
    Set-Content -LiteralPath $C.Logs['LogOutput.log'] -Value 'previous session' -Encoding ascii
    Set-Content -LiteralPath $C.Logs['LogOutput-prev.log'] -Value 'session before that' -Encoding ascii
    Set-Content -LiteralPath $C.Logs['Player.log'] -Value 'unity log' -Encoding ascii
    Set-Content -LiteralPath $C.Logs['Player-prev.log'] -Value 'unity log before' -Encoding ascii
    Set-Content -LiteralPath (Join-Path $C.Config 'CompetitiveRounds.seat-evidence.jsonl') -Value '{"q":1}' -Encoding ascii
    [System.IO.File]::WriteAllBytes($C.Dll, [byte[]](1..64))
    Set-Content -LiteralPath "$seat\incoming\frametime-0badc0de\sha256.txt" -Value (Sha $C.Dll) -Encoding ascii
    $run = NewRun $seat
    $p = Step1 $C $run
    # the simulated sitting: Unity's rotation, the game's own log, and the mutant's write
    $launch = {
        param($C)
        # the sentinel as the game would read it at its start: its bytes, read back here (the -ArmForce check)
        $script:ArmSeen = [System.Text.Encoding]::ASCII.GetString([System.IO.File]::ReadAllBytes($C.Arm))
        Move-Item -LiteralPath $C.Logs['Player.log'] -Destination $C.Logs['Player-prev.log'] -Force
        Set-Content -LiteralPath $C.Logs['Player.log'] -Value 'unity log of the sitting' -Encoding ascii
        $sim = @($SimFt) + @($SimWindow) + @($SimForm) + @($SimNoForm) + @($SimPlant)
        Set-Content -LiteralPath $C.Logs['LogOutput.log'] -Value $sim -Encoding ascii
        if ($script:Mutant -eq 'keep_prev_copy') { Copy-Item -LiteralPath $C.Logs['LogOutput.log'] -Destination $C.Logs['LogOutput-prev.log'] -Force }
        if ($script:Mutant -in @('closing_file', 'log_restore_fails', 'wait_restore_fails')) { Set-Content -LiteralPath (Join-Path $C.Config 'CompetitiveRounds.seat-evidence.closing-1') -Value 'x' -Encoding ascii }
        # F1's restore failures: a log's pre-image copy gone (its copy back throws), or the cfg held by a handle that
        # lets VR6 and the keep read and hash it but refuses the copy of the pre-image back onto it
        if ($script:Mutant -in @('log_restore_fails', 'wait_restore_fails')) { Remove-Item -LiteralPath (Join-Path (Join-Path $run 'pre') 'Player.log') -Force }
        if ($CfgCases.Contains($script:Mutant)) {
            $cc = $CfgCases[$script:Mutant]
            [System.IO.File]::WriteAllBytes($C.Cfg, (CfgFixture $cc.Bom $cc.Lines))
        }
        if ($script:Mutant -eq 'cfg_restore_locked') {
            [System.IO.File]::WriteAllBytes($C.Cfg, (CfgFixture $CfgLocked.Bom $CfgLocked.Lines))
            $script:Hold = [System.IO.File]::Open($C.Cfg, 'Open', 'Read', 'Read')
        }
        return [pscustomobject]@{ Id = 0; HasExited = $false }
    }
    $wait = {
        param($C, $proc)
        if ($script:Mutant -in @('throw_in_wait', 'wait_restore_fails')) { throw 'mutant throw_in_wait: an error inside the wait' }
        Say 'wait ended: complete True, exited False'
        return $true
    }
    $shutdown = { param($proc) Say ("shutdown: simulated pid {0}" -f $(if ($proc) { $proc.Id } else { 'none' })) }
    $keep = Join-Path (Join-Path $run 'sitting') 'com.competitiverounds.mod.cfg'
    $hold = $null
    if ($mutant -eq 'cfg_keep_fails') {
        # the keep made to fail: its destination is held open with no sharing, so the copy onto it is refused
        New-Item -ItemType Directory -Force -Path (Split-Path $keep) | Out-Null
        $hold = [System.IO.File]::Open($keep, 'CreateNew', 'ReadWrite', 'None')
    }
    $script:Mutant = $mutant
    $script:Hold = $null
    $script:ArmSeen = ''
    $threw = ''
    $st = $null
    try { $st = Sitting $C $p $launch $wait $shutdown }
    catch { $threw = $_.Exception.Message }
    finally { $script:Mutant = 'none'; if ($hold) { $hold.Dispose() }; if ($script:Hold) { $script:Hold.Dispose(); $script:Hold = $null } }
    $o = @($script:Out)
    # the restore proof (F1): its lines, and the count named by an ok line
    $proofOk = @($o | Where-Object { $_ -match '^RESTORE-PROOF ok [0-9]+$' })
    $proofFailed = @($o | Where-Object { $_ -ceq 'RESTORE-PROOF FAILED' }).Count
    $proofN = if ($proofOk.Count -eq 1) { [int]($proofOk[0].Substring(17)) } else { -1 }
    $restoredEqualLines = @($o | Where-Object { $_ -like 'restored * equal' }).Count
    # the export rule (F2): no planted value printed anywhere; every form fixture line printed in its section; the
    # withheld lines of each section exactly the counts the fixture's withheld lines give
    $secLog = @(); $secComp = @()
    $iL = [array]::IndexOf($o, '=== log lines'); $iS = [array]::IndexOf($o, '=== saved slice')
    $iC = [array]::IndexOf($o, '=== component slice'); $iV = [array]::IndexOf($o, '=== VR6')
    if ($iL -ge 0 -and $iS -gt $iL + 1) { $secLog = @($o[($iL + 1)..($iS - 1)]) }
    if ($iC -ge 0 -and $iV -gt $iC + 1) { $secComp = @($o[($iC + 1)..($iV - 1)] | Where-Object { $_ -notlike 'component slice: *' }) }
    $planted = @($o | Where-Object { $_.Contains('.example') }).Count
    $formOut = @(@($SimFt) + @($SimWindow) + @($SimForm) | Where-Object { $sec = if ($_.Contains('[FRAME-TIME]')) { $secLog } else { $secComp }; -not ($sec -ccontains $_) }).Count
    $wantW = @()
    foreach ($sec in @('log', 'comp')) {
        foreach ($cls in $SliceClasses) {
            $nw = @(@($SimNoForm) + @($SimPlant) | Where-Object { $_.Contains($cls) -and ($_.Contains('[FRAME-TIME]') -eq ($sec -eq 'log')) }).Count
            if ($nw -gt 0) { $wantW += ("{0} withheld {1} {2}" -f $sec, $cls.Trim('[', ']'), $nw) }
        }
    }
    $haveWs = @(@($secLog | Where-Object { $_ -like 'withheld *' } | ForEach-Object { 'log ' + $_ }) + @($secComp | Where-Object { $_ -like 'withheld *' } | ForEach-Object { 'comp ' + $_ }))
    $withheldOk = ($wantW -join '|') -ceq ($haveWs -join '|')
    $iTok = [array]::IndexOf($o, ($o | Where-Object { $_ -like 'runs/*' } | Select-Object -First 1))
    $iLog = [array]::IndexOf($o, '=== log lines'); $iVr6 = [array]::IndexOf($o, '=== VR6'); $iRes = [array]::IndexOf($o, '=== restored')
    $iSav = [array]::IndexOf($o, '=== saved slice'); $iComp = [array]::IndexOf($o, '=== component slice')
    $order = $iTok -eq 0 -and $iTok -lt $iLog -and $iLog -lt $iSav -and $iSav -lt $iVr6 -and $iVr6 -lt $iRes
    $headers = @($o | Where-Object { $_ -like 'slice class *' }).Count -eq $SliceClasses.Count
    $allSeen = @($o | Where-Object { $_ -like 'slice class *: 0 lines' }).Count -eq 0
    # the window lines: exactly the fixture's, in "=== log lines" only, as many as the point line's windows=
    $wIn = @($secLog | Where-Object { $_.Contains('[FRAME-TIME] w ') })
    $wAll = @($o | Where-Object { $_.Contains('[FRAME-TIME] w ') })
    $windowsOk = $wIn.Count -eq $SimWindow.Count -and $wAll.Count -eq $wIn.Count -and
        @($SimWindow | Where-Object { -not ($wIn -ccontains $_) }).Count -eq 0
    # the planted window lines that left (0 but in the no_wkeys and export_all runs)
    $wPlantOut = @($SimPlant | Where-Object { $_.Contains('[FRAME-TIME] w ') -and ($secLog -ccontains $_) }).Count
    # the parse's window-count rule (ft_parse.py records_missing, through ft_slice_identity.py --wcount) on the
    # exported log section: the "point <pt>: <n> window lines, the point line counts <k>" misses; -1 when it did not run
    $wMiss = -1; $wLines = ''
    if ($secLog.Count) {
        $lf = Join-Path $root 'log-lines.txt'
        [System.IO.File]::WriteAllLines($lf, [string[]]$secLog, (New-Object System.Text.UTF8Encoding($false)))
        try {
            $wo = @(& python -I -B (Join-Path $PSScriptRoot 'ft_slice_identity.py') --wcount $lf | ForEach-Object { [string]$_ })
            $hd = @($wo | Where-Object { $_ -match '^WCOUNT misses [0-9]+$' })
            if ($LASTEXITCODE -eq 0 -and $hd.Count -eq 1) { $wMiss = [int]($hd[0].Substring(14)) }
            $wLines = (@($wo | Where-Object { $_ -notmatch '^WCOUNT misses ' }) -join ' | ')
        }
        catch { $wLines = 'wcount error: ' + $_.Exception.Message }
    }
    # the component section: after the class headers, before VR6, non-empty, one line at least per non-FRAME-TIME
    # class, and no [FRAME-TIME] line in it
    $compLines = @()
    if ($iComp -ge 0 -and $iVr6 -gt $iComp + 1) { $compLines = @($o[($iComp + 1)..($iVr6 - 1)] | Where-Object { $_ -notlike 'component slice: *' }) }
    $component = $iComp -gt $iSav -and $iComp -lt $iVr6 -and $compLines.Count -gt 0 -and
        @($compLines | Where-Object { $_.Contains('[FRAME-TIME]') }).Count -eq 0
    foreach ($cls in $SliceClasses) {
        if ($cls -eq '[FRAME-TIME]') { continue }
        if (@($compLines | Where-Object { $_.Contains($cls) }).Count -eq 0) { $component = $false }
    }
    $shut = @($o | Where-Object { $_ -like 'shutdown:*' }).Count -ge 1
    $sentinelGone = (-not (Test-Path -LiteralPath $C.Arm)) -and @($o | Where-Object { $_ -eq 'sentinel removed: True' }).Count -eq 1
    $restoredLines = @($o | Where-Object { $_ -like 'restored *' })
    $restoredAll = $iRes -ge 0 -and $restoredLines.Count -eq ($C.Logs.Count + 1) -and
        @($restoredLines | Where-Object { $_ -notlike '* equal' }).Count -eq 0
    # the cfg keep: the "kept cfg <sha256>" lines, VR6's after digest of the cfg, the "kept cfg error" lines, the copy
    # left in sitting/, and the cfg's own restore (its line and the file on disk)
    $keptShas = @($o | ForEach-Object { $mm = [regex]::Match($_, '^kept cfg ([0-9a-f]{64})$'); if ($mm.Success) { $mm.Groups[1].Value } })
    $vr6Cfg = @($o | ForEach-Object { $mm = [regex]::Match($_, '^vr6 com\.competitiverounds\.mod\.cfg \S+ -> (\S+)'); if ($mm.Success) { $mm.Groups[1].Value } })
    $keptErr = @($o | Where-Object { $_ -like 'kept cfg error: *' }).Count
    $kinds = @($o | Where-Object { $_ -like 'kept cfg kind *' } | ForEach-Object { $_.Substring(14) })
    $cfgRestored = (Sha $C.Cfg) -eq $p.Cfg -and @($o | Where-Object { $_ -like 'restored cfg * equal' }).Count -eq 1
    return @{ Vr6 = $(if ($st) { $st.V } else { $false }); Restored = $(if ($st) { $st.R } else { $false }) -and $restoredAll
        Order = $order; Headers = $headers; AllSeen = $allSeen; Windows = $windowsOk; WIn = $wIn.Count; WMiss = $wMiss
        WPlantOut = $wPlantOut
        WLines = $wLines; Lane = $p.LaneOk; Component = $component
        Shutdown = $shut; SentinelGone = $sentinelGone; Threw = $threw; Code = $(if ($st) { $st.Code } else { 'none' })
        KeptLines = $keptShas.Count; KeptSha = $(if ($keptShas.Count) { $keptShas[0] } else { '' })
        Vr6CfgAfter = $(if ($vr6Cfg.Count) { $vr6Cfg[0] } else { '' }); KeptErr = $keptErr; KeptFile = (Sha $keep)
        ByKind = (CommentOnlyDiff (Join-Path (Join-Path $run 'pre') 'com.competitiverounds.mod.cfg') $keep); CfgRestored = $cfgRestored
        KindLines = $kinds.Count; Kind = $(if ($kinds.Count) { $kinds -join ',' } else { '' })
        ProofOk = $proofOk.Count; ProofN = $proofN; ProofFailed = $proofFailed; EqualLines = $restoredEqualLines
        Planted = $planted; FormMissing = $formOut; WithheldOk = $withheldOk; Withheld = ($haveWs -join ';')
        ArmText = $script:ArmSeen; ArmSaid = @($o | Where-Object { $_ -like 'sentinel written: *' })
    }
}

if ($SliceOf -ne '') {
    # step 4's two exported sections for a log file, as the sitting prints them; reads only
    [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
    try { $sl = ReadShared $SliceOf } catch { Print ('SLICE-OF REFUSED: the log is unreadable: ' + $_.Exception.Message); exit 2 }
    $sel = SliceExport $sl
    Print '=== log lines'
    foreach ($ln in $sel.Log) { Print $ln }
    Print '=== component slice'
    foreach ($ln in $sel.Comp) { Print $ln }
    exit 0
}

if ($CfgKindList -ne '') {
    try { $pairs = [System.IO.File]::ReadAllLines($CfgKindList) }
    catch { Print ('CFG-KIND REFUSED: the list is unreadable: ' + $_.Exception.Message); exit 2 }
    for ($i = 0; $i -lt $pairs.Count; $i++) {
        $ab = $pairs[$i].Split([char]9)
        if ($ab.Count -ne 2) { Print ("CFG-KIND {0} REFUSED" -f $i); continue }
        Print ("CFG-KIND {0} {1}" -f $i, (CfgKind $ab[0] $ab[1]))
    }
    exit 0
}

if ($SelfTest) {
    $base = Join-Path ([System.IO.Path]::GetTempPath()) ('ft-seat-selftest-' + (Get-Date).ToUniversalTime().ToString('yyyyMMddHHmmss'))
    $fail = @()
    # the window form's case table: with the key check (none) and without it (no_wkeys, the negative control)
    foreach ($m in @('none', 'no_wkeys')) {
        $script:Mutant = $m
        try {
            foreach ($c in $WFormCases) {
                $got = Exportable $c.Line
                $want = -not ($c.Form -or ($c.Keys -and $m -eq 'none'))
                Print ("self-test window form {0} {1}: exported {2}, wanted {3}" -f $m, $c.Name, $got, $want)
                if ($got -ne $want) { $fail += "window form ${m} $($c.Name): exported $got, wanted $want" }
            }
        }
        finally { $script:Mutant = 'none' }
    }
    $nForm = @($WFormCases | Where-Object { $_.Form }).Count; $nKeys = @($WFormCases | Where-Object { $_.Keys }).Count
    $nCtl = @($WFormCases | Where-Object { -not ($_.Form -or $_.Keys) }).Count
    Print ("self-test window form cases: {0} refused by the form, {1} by the key check alone, {2} controls" -f $nForm, $nKeys, $nCtl)
    if ($nForm -lt 1 -or $nKeys -lt 1 -or $nCtl -lt 1) { $fail += 'window form: the case table lacks a form case, a key case or a control' }
    # -ArmForce in both values: every run arms with none but arm_force_on, the clean run under -ArmForce ON
    $armForceGiven = $ArmForce
    foreach ($m in (@('none', 'arm_force_on', 'keep_prev_copy', 'closing_file', 'no_component_slice', 'throw_in_wait', 'throw_in_step4', 'export_all', 'drop_w', 'no_wkeys') +
            @($CfgCases.Keys) + @($RestoreFailCases))) {
        Print "=== self-test run: mutant $m"
        $ArmForce = $(if ($m -eq 'arm_force_on') { 'ON' } else { 'none' })
        try { $r = SelfTestOne (Join-Path $base $m) $m }
        finally { $ArmForce = $armForceGiven }
        # the sentinel's bytes at the launch: seed and f18, each line CRLF-ended, and force=ON as a third line only
        # under -ArmForce ON; the "sentinel written" line names force=ON only then
        $armOn = $m -eq 'arm_force_on'
        $armWant = "seed=$Seed`r`nf18=$F18`r`n" + $(if ($armOn) { "force=ON`r`n" } else { '' })
        $saidWant = "sentinel written: seed=$Seed f18=$F18" + $(if ($armOn) { ' force=ON' } else { '' })
        Print ("self-test {0} sentinel: -ArmForce {1}, bytes '{2}', written line '{3}'" -f $m, $(if ($armOn) { 'ON' } else { 'none' }),
            ($r.ArmText -replace "`r", '\r' -replace "`n", '\n'), ($r.ArmSaid -join '|'))
        if ($r.ArmText -cne $armWant) { $fail += "mutant ${m}: the sentinel's bytes at the launch are not the -ArmForce $(if ($armOn) { 'ON' } else { 'none' }) text" }
        if ($r.ArmSaid.Count -ne 1 -or $r.ArmSaid[0] -cne $saidWant) { $fail += "mutant ${m}: the 'sentinel written' line is not '$saidWant'" }
        Print ("self-test {0}: order {1}, slice headers {2}, every class seen {3}, window lines exported {4}, lane {5}, VR6 {6}, component slice {7}, shutdown {8}, sentinel removed {9}, restored {10}, exit code {11}, threw '{12}'" -f
            $m, $r.Order, $r.Headers, $r.AllSeen, $r.Windows, $r.Lane, $r.Vr6, $r.Component, $r.Shutdown, $r.SentinelGone,
            $r.Restored, $r.Code, $r.Threw)
        Print ("self-test {0} windows: {1} window lines under '=== log lines' ({2} of them planted), the parse's window-count misses {3} ({4})" -f
            $m, $r.WIn, $r.WPlantOut, $r.WMiss, $r.WLines)
        Print ("self-test {0} cfg: kept cfg lines {1} ({2}), VR6 after {3}, kept cfg errors {4}, sitting cfg {5}, comment lines only {6}, cfg restored {7}, kind lines {8} ({9})" -f
            $m, $r.KeptLines, $r.KeptSha, $r.Vr6CfgAfter, $r.KeptErr, $r.KeptFile, $r.ByKind, $r.CfgRestored, $r.KindLines, $r.Kind)
        Print ("self-test {0} restore proof: ok lines {1} (n {2}), FAILED lines {3}, equal lines {4}; export: planted values printed {5}, form lines missing {6}, withheld as wanted {7} ({8})" -f
            $m, $r.ProofOk, $r.ProofN, $r.ProofFailed, $r.EqualLines, $r.Planted, $r.FormMissing, $r.WithheldOk, $r.Withheld)
        $restoreFails = $m -in $RestoreFailCases
        # every run, the mutants that throw included: no error escapes, the game is shut down, the sentinel is removed;
        # the restore runs with every sha256 equal and its one proof line names them all, except in the cases that make
        # the restore fail, which must print "RESTORE-PROOF FAILED", no ok line, and end exit 5 whatever VR6 said (F1)
        $cleanup = $r.Threw -eq '' -and $r.Shutdown -and $r.SentinelGone -and $r.Lane
        if (-not $cleanup) { $fail += "$m (an error escaped, or the shutdown or sentinel removal did not happen)" }
        if ($restoreFails) {
            if ($r.Restored) { $fail += "mutant ${m}: the restore passed (control FAILED)" }
            if ($r.ProofFailed -ne 1 -or $r.ProofOk -ne 0) { $fail += "mutant ${m}: $($r.ProofFailed) RESTORE-PROOF FAILED and $($r.ProofOk) ok lines, not 1 and 0" }
            if ($r.Code -ne 5) { $fail += "mutant ${m}: exit code $($r.Code), not 5" }
            if ($r.Vr6) { $fail += "mutant ${m}: VR6 passed, so the case does not combine a VR6 failure with the restore failure" }
        }
        else {
            if (-not $r.Restored) { $fail += "$m (the restore did not happen with every sha256 equal)" }
            if ($r.ProofOk -ne 1 -or $r.ProofFailed -ne 0 -or $r.ProofN -ne $r.EqualLines -or $r.ProofN -ne 6) { $fail += "mutant ${m}: restore proof $($r.ProofOk) ok lines (n $($r.ProofN)) and $($r.ProofFailed) FAILED lines, not one 'RESTORE-PROOF ok 6' for $($r.EqualLines) equal lines" }
        }
        # the export rule (F2), in every run whose step 4 prints both sections: nothing planted printed, every form line
        # exported, and the withheld counts exactly the fixture's
        if ($m -notin @('throw_in_step4', 'no_component_slice', 'export_all', 'drop_w', 'no_wkeys')) {
            if ($r.Planted -ne 0) { $fail += "mutant ${m}: $($r.Planted) printed lines carry a planted value" }
            if ($r.FormMissing -ne 0) { $fail += "mutant ${m}: $($r.FormMissing) form lines not exported" }
            if (-not $r.WithheldOk) { $fail += "mutant ${m}: the withheld counts are not the fixture's ($($r.Withheld))" }
        }
        # every run whose step 4 prints the log section, export_all included (its window lines are the same): the
        # parse's window-count rule finds no miss
        if ($m -notin @('throw_in_step4', 'drop_w') -and $r.WMiss -ne 0) { $fail += "mutant ${m}: the parse's window-count rule gave $($r.WMiss) misses, not 0 ($($r.WLines))" }
        $full = $r.Order -and $r.Headers -and $r.AllSeen -and $r.Windows
        switch ($m) {
            'export_all' {
                # the negative control of the export rule: every selected line exported, as the substring selection did
                if ($r.Planted -eq 0) { $fail += 'mutant export_all: no planted value printed (control FAILED)' }
                if ($r.WithheldOk) { $fail += 'mutant export_all: the withheld counts still match (control FAILED)' }
            }
            'drop_w' {
                # the negative control of the window export: the skip restored, so no window line leaves and the parse
                # refuses on the point line's windows= count; the rest of the run is the clean one's
                if ($r.WIn -ne 0) { $fail += "mutant drop_w: $($r.WIn) window lines exported (control FAILED)" }
                if ($r.WMiss -ne 1 -or $r.WLines -notmatch '^point 1\.1\.1: 0 window lines, the point line counts 4$') { $fail += "mutant drop_w: the parse's window-count misses $($r.WMiss) ($($r.WLines)), not the one refusal on windows=4 (control FAILED)" }
                if (-not ($r.Order -and $r.Headers -and $r.AllSeen -and $r.Vr6 -and $r.Component) -or $r.Code -ne 0) { $fail += 'mutant drop_w: order, headers, VR6, component slice or exit code differ from the clean run' }
            }
            'no_wkeys' {
                # the negative control of WindowKeysRefused in the sitting: the key check skipped, exactly the
                # $SimKeysOnly planted window lines leave under "=== log lines" and the withheld counts move; the
                # rest of the run is the clean one's
                if ($r.WithheldOk) { $fail += 'mutant no_wkeys: the withheld counts still match (control FAILED)' }
                if ($r.WPlantOut -ne $SimKeysOnly -or $r.WIn -ne $SimWindow.Count + $SimKeysOnly) { $fail += "mutant no_wkeys: $($r.WPlantOut) planted window lines exported ($($r.WIn) in all), not $SimKeysOnly (control FAILED)" }
                if ($r.Planted -ne 0 -or $r.FormMissing -ne 0) { $fail += "mutant no_wkeys: $($r.Planted) planted values printed and $($r.FormMissing) form lines missing, not 0 and 0" }
                if (-not ($r.Order -and $r.Headers -and $r.AllSeen -and $r.Vr6 -and $r.Component) -or $r.Code -ne 0) { $fail += 'mutant no_wkeys: order, headers, VR6, component slice or exit code differ from the clean run' }
            }
            { $_ -in $RestoreFailCases } { }
            { $_ -in @('none', 'arm_force_on') } {
                if (-not $full) { $fail += 'clean run: order, headers or window lines' }
                if (-not $r.Vr6) { $fail += 'clean run: VR6 failed' }
                if (-not $r.Component) { $fail += 'clean run: the component slice is missing or incomplete' }
                if ($r.Code -ne 0) { $fail += "clean run: exit code $($r.Code)" }
                if ($r.KeptLines -ne 0 -or $r.KeptErr -ne 0 -or $r.KeptFile -ne 'absent' -or $r.KindLines -ne 0) { $fail += 'clean run: a kept cfg line, or a cfg in sitting/, with the cfg unchanged' }
            }
            { $CfgCases.Contains($_) } {
                $want = $CfgCases[$m].Want
                if (-not ($full -and $r.Component)) { $fail += "$m (order, headers, window lines or component slice)" }
                if ($r.Vr6) { $fail += "mutant ${m}: VR6 passed (control FAILED)" }
                if ($r.Code -ne 4) { $fail += "mutant ${m}: exit code $($r.Code), not 4" }
                if ($want -eq '') {
                    if ($r.KeptErr -ne 1 -or $r.KeptLines -ne 0) { $fail += "mutant ${m}: $($r.KeptErr) kept cfg errors and $($r.KeptLines) kept cfg lines, not 1 and 0" }
                    if ($r.KindLines -ne 0) { $fail += "mutant ${m}: $($r.KindLines) kept cfg kind lines after the failed keep, not 0" }
                    if (-not $r.CfgRestored) { $fail += "mutant ${m}: the cfg is not restored equal after the failed keep" }
                }
                else {
                    if ($r.KeptLines -ne 1 -or $r.KeptErr -ne 0) { $fail += "mutant ${m}: $($r.KeptLines) kept cfg lines and $($r.KeptErr) kept cfg errors, not 1 and 0" }
                    if ($r.KeptSha -eq '' -or $r.KeptSha -ne $r.Vr6CfgAfter -or $r.KeptFile -ne $r.KeptSha) { $fail += "mutant ${m}: the kept cfg '$($r.KeptSha)' is not VR6's after digest '$($r.Vr6CfgAfter)' and the sitting copy '$($r.KeptFile)'" }
                    if ($r.KindLines -ne 1 -or $r.Kind -cne $want) { $fail += "mutant ${m}: kept cfg kind '$($r.Kind)' in $($r.KindLines) lines, not one $want" }
                    if (-not $r.CfgRestored) { $fail += "mutant ${m}: the cfg is not restored equal" }
                }
                if ($m -eq 'cfg_comment' -and -not $r.ByKind) { $fail += "mutant ${m}: the sitting copy does not differ from pre/ in comment lines only" }
            }
            { $_ -in @('keep_prev_copy', 'closing_file') } {
                if (-not ($full -and $r.Component)) { $fail += "$m (order, headers, window lines or component slice)" }
                if ($r.Vr6) { $fail += "mutant ${m}: VR6 passed (control FAILED)" }
                if ($r.Code -ne 4) { $fail += "mutant ${m}: exit code $($r.Code), not 4" }
            }
            'no_component_slice' {
                if (-not ($full -and $r.Vr6)) { $fail += "$m (order, headers, window lines or VR6)" }
                if ($r.Component) { $fail += "mutant ${m}: the component check passed (control FAILED)" }
            }
            'throw_in_wait' { if ($r.Code -ne 3) { $fail += "mutant ${m}: exit code $($r.Code), not 3" } }            'throw_in_step4' { if ($r.Code -ne 4) { $fail += "mutant ${m}: exit code $($r.Code), not 4" } }
        }
    }
    Print "self-test scratch: $base"
    if ($fail.Count) { Print ('SELFTEST FAIL: ' + ($fail -join '; ')); exit 6 }
    Print 'SELFTEST PASS'
    exit 0
}

# ---- the sitting
$C = NewCtx $GameRoot $SeatRoot $LocalLow
$run = NewRun $SeatRoot
$own = Sha $PSCommandPath
$want = Join-Path $SeatRoot 'runner\frame_time_seat.sha256'
$rec = if (Test-Path -LiteralPath $want) { ([regex]::Match([string](Get-Content -LiteralPath $want -TotalCount 1), '(?<![0-9a-fA-F])[0-9a-fA-F]{64}(?![0-9a-fA-F])')).Value.ToLowerInvariant() } else { 'absent' }
Say ("script sha256 {0}; recorded at staging {1}" -f $own, $rec)
if ($rec -ne $own) { Say 'REFUSED: the script is not the staged one (step 0)'; exit 2 }
if (@(Get-Process -Name 'Rounds' -ErrorAction SilentlyContinue).Count) { Say 'REFUSED: ROUNDS is running'; exit 2 }
if (Test-Path -LiteralPath $C.Arm) { Say 'REFUSED: a sentinel is already present'; exit 2 }
try { $p = Step1 $C $run }
catch { Say ('REFUSED: step 1 failed: ' + $_.Exception.Message); exit 2 }
if (-not $p.LaneOk) { Say 'REFUSED: the installed DLL is no staged FrameTime lane (push the lane first)'; exit 2 }
$launch = {
    param($C)
    Start-Process 'steam://rungameid/1557740'
    $pr = $null
    for ($i = 0; $i -lt 60 -and -not $pr; $i++) {
        Start-Sleep -Seconds 2
        $pr = Get-Process -Name 'Rounds' -ErrorAction SilentlyContinue | Select-Object -First 1
    }
    return $pr
}
$wait = {
    param($C, $proc)
    $deadline = (Get-Date).AddSeconds($TimeoutS - 600)
    $done = $false
    for ($i = 0; $i -lt [int](($TimeoutS - 600) / 15) + 1 -and -not $done; $i++) {
        if ((Get-Date) -gt $deadline -or $proc.HasExited) { break }
        Start-Sleep -Seconds 15
        $done = @((ReadShared $C.Logs['LogOutput.log']) | Where-Object { $_.Contains('[FRAME-TIME] sitting complete') }).Count -gt 0
    }
    Say ("wait ended: complete {0}, exited {1}" -f $done, $proc.HasExited)
    return $done
}
$shutdown = {
    param($proc)
    if (-not $proc) {
        Say ("shutdown: no pid captured (a kill only by a captured pid); ROUNDS processes now {0}" -f @(Get-Process -Name 'Rounds' -ErrorAction SilentlyContinue).Count)
        return
    }
    if (-not $proc.HasExited) {
        [void]$proc.CloseMainWindow()
        if (-not $proc.WaitForExit(60000)) { Say ("kill pid {0} after 60 s" -f $proc.Id); Stop-Process -Id $proc.Id -Force; [void]$proc.WaitForExit(30000) }
    }
    Say ("shutdown: pid {0} exited {1}" -f $proc.Id, $proc.HasExited)
    Start-Sleep -Seconds 5
}
$code = 3
try { $code = (Sitting $C $p $launch $wait $shutdown).Code }
catch { Say ('sitting error outside the steps: ' + $_.Exception.Message) }
finally {
    $bk = Get-ChildItem -LiteralPath (Join-Path $SeatRoot 'backups') -Filter 'CompetitiveRounds-*.dll' -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending | Select-Object -First 1
    Say ("step 6 (not here): restore the Release DLL; newest backup {0}; installed now {1}" -f $(if ($bk) { $bk.Name } else { 'none' }), (Sha $C.Dll))
    Say ("SEAT EXIT {0}" -f $code)
}
exit $code
