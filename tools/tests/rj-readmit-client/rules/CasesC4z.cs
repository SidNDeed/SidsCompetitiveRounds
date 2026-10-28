// C4z: RJ readmission P4.6, the capability flip (V3:252). The enroll call's
// caps come from FfaReadmitEntryRules.CapsList: ffa_adm1 is advertised only
// together with ffa_rdm1, and ffa_rdm1 never without ffa_adm1, so every
// admission lobby a build of this lane joins is a readmission lobby.
namespace CompetitiveRounds
{
    internal static class CasesC4z
    {
        private static string L(bool asm, bool adm)
        {
            return FfaReadmitEntryRules.CapsList(asm, adm, "ffa_asm1", "ffa_adm1");
        }

        private static bool Has(string list, string token)
        {
            foreach (var t in list.Split(',')) if (t == token) return true;
            return false;
        }

        internal static void Register()
        {
            RulesProgram.Add("C4z.T4.6.adm_sends_all_three", () =>
            {
                Check.Eq("ffa_rdm1", FfaReadmitEntryRules.RdmCapsToken, "the readmission caps token");
                Check.Eq("ffa_asm1,ffa_adm1,ffa_rdm1", L(true, true), "an admission build advertises all three tokens");
            });

            RulesProgram.Add("C4z.T4.6.adm_and_rdm_travel_together", () =>
            {
                foreach (var asm in new[] { false, true })
                    foreach (var adm in new[] { false, true })
                    {
                        string l = L(asm, adm);
                        Check.True(Has(l, "ffa_adm1") == Has(l, "ffa_rdm1"),
                                   "ffa_adm1 and ffa_rdm1 travel together (asm=" + asm + " adm=" + adm + ")");
                    }
            });

            RulesProgram.Add("C4z.T4.6.asm_alone_no_rdm", () =>
            {
                Check.Eq("ffa_asm1", L(true, false), "an assembly build without admission advertises ffa_asm1 alone");
                Check.Eq("", L(false, true), "no assembly: nothing is advertised");
                Check.Eq("", L(false, false), "neither: nothing is advertised");
            });
        }
    }
}
