#if SCR_FRAMETIME
namespace CompetitiveRounds
{
    /// <summary>FrameTime M3 census ids (METHOD-V4.md 3.12; VR5): one id per gated entry,
    /// named as tools/frametime/INVENTORY.md names it (component prefix, c = call site
    /// gated at its callee, p = patch), with the component and the patch shape. RegisterAll
    /// runs once at clock install, so every census line lists every gated entry, reached or
    /// not, and it warns on any id left unregistered or registered twice.</summary>
    internal static class FtE
    {
        // HitEvidence: the live entries of INVENTORY.md (yes and both).
        internal const int HE_c5 = 0, HE_p1 = 1, HE_p2 = 2, HE_p3 = 3, HE_p4 = 4, HE_p5 = 5, HE_p6 = 6, HE_p7 = 7,
                           HE_p8 = 8, HE_p9 = 9;

        // CombatEvidence: the live entries (yes and both).
        internal const int CE_c7 = 10, CE_c8 = 11, CE_p1 = 12, CE_p2 = 13, CE_p3 = 14, CE_p4 = 15, CE_p5 = 16, CE_p6 = 17,
                           CE_p7 = 18, CE_p8 = 19, CE_p9 = 20, CE_p10 = 21, CE_p11 = 22, CE_p12 = 23, CE_p13 = 24,
                           CE_p14 = 25, CE_p15 = 26, CE_p16 = 27, CE_p17 = 28, CE_p18 = 29, CE_p19 = 30;

        internal const int Count = 31;

        private static bool _done;

        internal static void RegisterAll()
        {
            if (_done) return;
            _done = true;
            R(HE_c5, "HE-c5 HitEvidence.Drain", FtSpan.Hit, "call");
            R(HE_p1, "HE-p1 PhotonNetwork.ExecuteRpc", FtSpan.Hit, "S7");
            R(HE_p2, "HE-p2 HealthHandler.RPCA_SendTakeDamage", FtSpan.Hit, "S6");
            R(HE_p3, "HE-p3 HealthHandler.RPCA_SendTakeForce", FtSpan.Hit, "S5");
            R(HE_p4, "HE-p4 HealthHandler.DoDamage", FtSpan.Hit, "S5");
            R(HE_p5, "HE-p5 Block.RPCA_DoBlock", FtSpan.Hit, "S6");
            R(HE_p6, "HE-p6 ProjectileInit.RPCA_Init", FtSpan.Hit, "S5");
            R(HE_p7, "HE-p7 ProjectileInit.RPCA_Init_noAmmoUse", FtSpan.Hit, "S5");
            R(HE_p8, "HE-p8 ProjectileInit.RPCA_Init_SeparateGun", FtSpan.Hit, "S5");
            R(HE_p9, "HE-p9 ProjectileHit.RPCA_DoHit", FtSpan.Hit, "S6");
            R(CE_c7, "CE-c7 CombatEvidence.Tick", FtSpan.Combat, "call");
            R(CE_c8, "CE-c8 CombatEvidence.RpcSent", FtSpan.Combat, "call");
            R(CE_p1, "CE-p1 Gun.Attack", FtSpan.Combat, "S9");
            R(CE_p2, "CE-p2 ProjectileInit.RPCA_Init", FtSpan.Combat, "S6");
            R(CE_p3, "CE-p3 ProjectileInit.RPCA_Init_noAmmoUse", FtSpan.Combat, "S1");
            R(CE_p4, "CE-p4 ProjectileInit.RPCA_Init_SeparateGun", FtSpan.Combat, "S1");
            R(CE_p5, "CE-p5 GunAmmo.ReloadAmmo", FtSpan.Combat, "S1");
            R(CE_p6, "CE-p6 ProjectileHit.RPCA_DoHit", FtSpan.Combat, "S6");
            R(CE_p7, "CE-p7 ProjectileHit.Hit", FtSpan.Combat, "S1");
            R(CE_p8, "CE-p8 Block.RPCA_DoBlock", FtSpan.Combat, "S5");
            R(CE_p9, "CE-p9 Block.TryBlock", FtSpan.Combat, "S8");
            R(CE_p10, "CE-p10 CharacterStatModifiers.DealtDamage", FtSpan.Combat, "S2");
            R(CE_p11, "CE-p11 BounceEffectRetarget.SetNewVel", FtSpan.Combat, "S1");
            R(CE_p12, "CE-p12 ScreenEdgeBounce.DoHit", FtSpan.Combat, "S6");
            R(CE_p13, "CE-p13 SyncProjectile.OnPhotonSerializeView", FtSpan.Combat, "S2");
            R(CE_p14, "CE-p14 HealthHandler.RPCA_SendTakeForce", FtSpan.Combat, "S6");
            R(CE_p15, "CE-p15 HealthHandler.RPCA_SendTakeDamage", FtSpan.Combat, "S6");
            R(CE_p16, "CE-p16 HealthHandler.RPCA_Die", FtSpan.Combat, "S1");
            R(CE_p17, "CE-p17 HealthHandler.RPCA_Die_Phoenix", FtSpan.Combat, "S1");
            R(CE_p18, "CE-p18 BounceEffectRetarget.FindTarget", FtSpan.Combat, "S4");
            R(CE_p19, "CE-p19 MoveTransform.Update", FtSpan.Combat, "S6");
            int missing = 0;
            for (int i = 0; i < Count; i++) if (FtCensus.Names[i] == null) missing++;
            Plugin.Log.LogInfo("[FRAME-TIME] census registered=" + FtCensus.Count + " expected=" + Count + " missing=" + missing
                + " duplicates=" + FtCensus.Duplicates);
        }

        private static void R(int id, string name, int component, string shape)
        {
            FtCensus.Set(id, name.Replace(' ', ':'), component, shape);
        }
    }
}
#endif
