# combat.py: CombatEvidence's 21 live entries (INVENTORY.md: CE-c7, CE-c8, CE-p1 to CE-p19). Gated whole; the class
# iii state (Top/Ht, PingBin, the L-hat cache, the Pos ring, B5c) is capped or time-based (INVENTORY.md), recorded
# as the build decision in the hand-back. A prefix's __state is never read when skipped: its partner reads the same
# gate in the same frame and returns first. Finalizers return __exception, as every one of them does today.
F = "plugin/CombatEvidence.cs"
FIN = "if (FtGate.Off) return __exception;"
POST = "if (FtGate.Off) return;"


def c(cls):
    return "internal static class " + cls


def skip(e, tail="return;"):
    return "if (FtCensus.Skip(FtE.%s)) %s" % (e, tail)


PRE = "private static void Prefix("
FN = "private static Exception Finalizer("
PO = "private static void Postfix("
S0 = "{ __state = 0; return; }"
SPECS = [
    (F, c("CombatEvidence"), "internal static void Tick()", skip("CE_c7"), "Combat", "Gated"),
    (F, c("CombatEvidence"), "internal static void RpcSent(", skip("CE_c8"), "Combat", "Gated"),
    (F, c("CombatEvidence_AttackPatch"), PRE, skip("CE_p1", S0), "Combat", "Gated"),
    (F, c("CombatEvidence_AttackPatch"), PO, POST, "Combat", "Gated"),
    (F, c("CombatEvidence_InitAmmoPatch"), PRE, skip("CE_p2", S0), "Combat", "Gated"),
    (F, c("CombatEvidence_InitAmmoPatch"), FN, FIN, "Combat", "Gated"),
    (F, c("CombatEvidence_InitNoAmmoPatch"), PRE, skip("CE_p3"), "Combat", "Gated"),
    (F, c("CombatEvidence_InitSeparatePatch"), PRE, skip("CE_p4"), "Combat", "Gated"),
    (F, c("CombatEvidence_ReloadPatch"), PRE, skip("CE_p5"), "Combat", "Gated"),
    (F, c("CombatEvidence_HitPatch"), PRE, skip("CE_p6", S0), "Combat", "Gated"),
    (F, c("CombatEvidence_HitPatch"), FN, FIN, "Combat", "Gated"),
    (F, c("CombatEvidence_ContactPatch"), PRE, skip("CE_p7"), "Combat", "Gated"),
    (F, c("CombatEvidence_BlockPatch"), FN, skip("CE_p8", "return __exception;"), "Combat", "Gated"),
    (F, c("CombatEvidence_TryBlockPatch"), PRE, skip("CE_p9", S0), "Combat", "Gated"),
    (F, c("CombatEvidence_TryBlockPatch"), PO, POST, "Combat", "Gated"),
    (F, c("CombatEvidence_DealtPatch"), PO, skip("CE_p10"), "Combat", "Gated"),
    (F, c("CombatEvidence_TargetBouncePatch"), PRE, skip("CE_p11"), "Combat", "Gated"),
    (F, c("CombatEvidence_EdgeBouncePatch"), PRE, skip("CE_p12", S0), "Combat", "Gated"),
    (F, c("CombatEvidence_EdgeBouncePatch"), FN, FIN, "Combat", "Gated"),
    (F, c("CombatEvidence_SyncPatch"), PO, skip("CE_p13"), "Combat", "Gated"),
    (F, c("CombatEvidence_ForcePatch"), PRE, skip("CE_p14", S0), "Combat", "Gated"),
    (F, c("CombatEvidence_ForcePatch"), FN, FIN, "Combat", "Gated"),
    (F, c("CombatEvidence_DamagePatch"), PRE, skip("CE_p15", S0), "Combat", "Gated"),
    (F, c("CombatEvidence_DamagePatch"), FN, FIN, "Combat", "Gated"),
    (F, c("CombatEvidence_DiePatch"), PRE, skip("CE_p16"), "Combat", "Gated"),
    (F, c("CombatEvidence_DiePhoenixPatch"), PRE, skip("CE_p17"), "Combat", "Gated"),
    (F, c("CombatEvidence_FindTargetPatch"), PO, skip("CE_p18"), "Combat", "Gated"),
    (F, c("CombatEvidence_MovePatch"), PRE, skip("CE_p19", S0), "Combat", "Gated"),
    (F, c("CombatEvidence_MovePatch"), FN, FIN, "Combat", "Gated"),
]
