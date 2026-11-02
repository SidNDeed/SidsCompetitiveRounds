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

        internal const int Count = 10;

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
