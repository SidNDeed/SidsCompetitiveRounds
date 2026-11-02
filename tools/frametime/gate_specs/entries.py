# entries.py: the census table, in id order: (const, INVENTORY.md id and target, component, shape). Only OUTERMOST
# live entries are listed: those live combat enters from outside the seven components (a tick in Plugin.Update, a
# Harmony patch, or a call from non-component code). An entry reached live only through another gated entry
# (HE-c5 HitEvidence.Drain under PT-c5; CE-c8 CombatEvidence.RpcSent under SE-p1; SeatEvidence's EnterRpc, RpcTop,
# DamageGate and the other hooks under the HitEvidence and CombatEvidence patches) is covered by its caller's gate;
# it keeps a plain gate read for defence but no census row, because VR5 (guarded calls at OFF points) could never
# be met by a gate its caller always reaches first. Predicates and clock reads (CombatLive, CombatState, SwMs, the
# Point getter) are not gated: the schedule itself reads CombatLive. Not gated, refused at arming instead (part 4):
# IC-p5, the post-boot test fixture. gen_entries.py writes plugin/FtEntries.cs from this table.
# The shape column: a patched entry is its own shape (its const), because FtCalib calibrates each patched
# entry with its own patch methods on a dummy of its target's signature (round-1 MEDIUM, FtCalib.cs:163);
# "call" is a direct call whose body opens with the census check.
ENTRIES = [
    ("HE_p1", "HE-p1 PhotonNetwork.ExecuteRpc", "Hit", "HE_p1"),
    ("HE_p2", "HE-p2 HealthHandler.RPCA_SendTakeDamage", "Hit", "HE_p2"),
    ("HE_p3", "HE-p3 HealthHandler.RPCA_SendTakeForce", "Hit", "HE_p3"),
    ("HE_p4", "HE-p4 HealthHandler.DoDamage", "Hit", "HE_p4"),
    ("HE_p5", "HE-p5 Block.RPCA_DoBlock", "Hit", "HE_p5"),
    ("HE_p6", "HE-p6 ProjectileInit.RPCA_Init", "Hit", "HE_p6"),
    ("HE_p7", "HE-p7 ProjectileInit.RPCA_Init_noAmmoUse", "Hit", "HE_p7"),
    ("HE_p8", "HE-p8 ProjectileInit.RPCA_Init_SeparateGun", "Hit", "HE_p8"),
    ("HE_p9", "HE-p9 ProjectileHit.RPCA_DoHit", "Hit", "HE_p9"),
    ("CE_c7", "CE-c7 CombatEvidence.Tick", "Combat", "call"),
    ("CE_p1", "CE-p1 Gun.Attack", "Combat", "CE_p1"),
    ("CE_p2", "CE-p2 ProjectileInit.RPCA_Init", "Combat", "CE_p2"),
    ("CE_p3", "CE-p3 ProjectileInit.RPCA_Init_noAmmoUse", "Combat", "CE_p3"),
    ("CE_p4", "CE-p4 ProjectileInit.RPCA_Init_SeparateGun", "Combat", "CE_p4"),
    ("CE_p5", "CE-p5 GunAmmo.ReloadAmmo", "Combat", "CE_p5"),
    ("CE_p6", "CE-p6 ProjectileHit.RPCA_DoHit", "Combat", "CE_p6"),
    ("CE_p7", "CE-p7 ProjectileHit.Hit", "Combat", "CE_p7"),
    ("CE_p8", "CE-p8 Block.RPCA_DoBlock", "Combat", "CE_p8"),
    ("CE_p9", "CE-p9 Block.TryBlock", "Combat", "CE_p9"),
    ("CE_p10", "CE-p10 CharacterStatModifiers.DealtDamage", "Combat", "CE_p10"),
    ("CE_p11", "CE-p11 BounceEffectRetarget.SetNewVel", "Combat", "CE_p11"),
    ("CE_p12", "CE-p12 ScreenEdgeBounce.DoHit", "Combat", "CE_p12"),
    ("CE_p13", "CE-p13 SyncProjectile.OnPhotonSerializeView", "Combat", "CE_p13"),
    ("CE_p14", "CE-p14 HealthHandler.RPCA_SendTakeForce", "Combat", "CE_p14"),
    ("CE_p15", "CE-p15 HealthHandler.RPCA_SendTakeDamage", "Combat", "CE_p15"),
    ("CE_p16", "CE-p16 HealthHandler.RPCA_Die", "Combat", "CE_p16"),
    ("CE_p17", "CE-p17 HealthHandler.RPCA_Die_Phoenix", "Combat", "CE_p17"),
    ("CE_p18", "CE-p18 BounceEffectRetarget.FindTarget", "Combat", "CE_p18"),
    ("CE_p19", "CE-p19 MoveTransform.Update", "Combat", "CE_p19"),
    ("SE_c50", "SE-c50 SeatEvidence.NoteView", "Seat", "call"),
    ("SE_c52", "SE-c52 SeatEvidence.CompatTick", "Seat", "call"),
    ("SE_c53", "SE-c53 SeatEvidence.Tick", "Seat", "call"),
    ("SE_p1", "SE-p1 PhotonNetwork.RPC", "Seat", "SE_p1"),
    ("SE_p2", "SE-p2 Block.DoBlock", "Seat", "SE_p2"),
    ("SE_p3", "SE-p3 Block.TryBlockMe", "Seat", "SE_p3"),
    ("PT_c5", "PT-c5 PointEvidence.Drain", "Point", "call"),
    ("PT_p1", "PT-p1 Saw.Update", "Point", "PT_p1"),
    ("IC_c6", "IC-c6 IdentityClockEvidence.Tick", "Identity", "call"),
    ("IC_p1", "IC-p1 PhotonNetwork.ExecuteRpc", "Identity", "IC_p1"),
    ("IC_p4", "IC-p4 SyncPlayerMovement.OnPhotonSerializeView", "Identity", "IC_p4"),
    ("CD_c6", "CD-c6 CardDrawEvidence.Tick", "CardDraw", "call"),
    ("CD_c7", "CD-c7 CardDrawEvidence.EnsureCensusDump", "CardDraw", "call"),
    ("PB_c2", "PB-c2 PeerBuild.StageBuildProp", "PeerBuild", "call"),
    ("PB_c3", "PB-c3 PeerBuild.Tick", "PeerBuild", "call"),
]
