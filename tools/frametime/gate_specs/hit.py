# spec_hit.py: HitEvidence's ten live entries (INVENTORY.md: HE-c5 and HE-p1 to HE-p9). A prefix counts the call
# and leaves its __state at a value its finalizer never needs (the finalizer reads the same gate in the same frame
# and returns first); HE-p1's state is the inventory's sentinel anyway (depth -1: ExitRpc ignores it; the sender
# restored is the current one). Finalizers return __exception, the value every one of them returns today.
F = "plugin/HitEvidence.cs"
FIN = "if (FtGate.Off) return __exception;"
SPECS = [
    (F, "internal static class HitEvidence", "internal static void Drain()",
     "if (FtCensus.Skip(FtE.HE_c5)) return;", "Hit", "Gated"),
    (F, "internal static class HitEvidence_ExecuteRpcPatch", "private static void Prefix(",
     "if (FtCensus.Skip(FtE.HE_p1)) { __state = (long)(uint)HitEvidence.RpcSender | ((long)-1 << 32); return; }",
     "Hit", "Gated"),
    (F, "internal static class HitEvidence_ExecuteRpcPatch", "private static Exception Finalizer(", FIN, "Hit", "Gated"),
    (F, "internal static class HitEvidence_DamagePatch", "private static void Prefix(",
     "if (FtCensus.Skip(FtE.HE_p2)) { __state = false; return; }", "Hit", "Gated"),
    (F, "internal static class HitEvidence_DamagePatch", "private static Exception Finalizer(", FIN, "Hit", "Gated"),
    (F, "internal static class HitEvidence_ForcePatch", "private static Exception Finalizer(",
     "if (FtCensus.Skip(FtE.HE_p3)) return __exception;", "Hit", "Gated"),
    (F, "internal static class HitEvidence_DotPatch", "private static Exception Finalizer(",
     "if (FtCensus.Skip(FtE.HE_p4)) return __exception;", "Hit", "Gated"),
    (F, "internal static class HitEvidence_BlockPatch", "private static void Prefix(",
     "if (FtCensus.Skip(FtE.HE_p5)) { __state = 0; return; }", "Hit", "Gated"),
    (F, "internal static class HitEvidence_BlockPatch", "private static Exception Finalizer(", FIN, "Hit", "Gated"),
    (F, "internal static class HitEvidence_SpawnAmmoPatch", "private static Exception Finalizer(",
     "if (FtCensus.Skip(FtE.HE_p6)) return __exception;", "Hit", "Gated"),
    (F, "internal static class HitEvidence_SpawnNoAmmoPatch", "private static Exception Finalizer(",
     "if (FtCensus.Skip(FtE.HE_p7)) return __exception;", "Hit", "Gated"),
    (F, "internal static class HitEvidence_SpawnSeparatePatch", "private static Exception Finalizer(",
     "if (FtCensus.Skip(FtE.HE_p8)) return __exception;", "Hit", "Gated"),
    (F, "internal static class HitEvidence_ImpactPatch", "private static void Prefix(",
     "if (FtCensus.Skip(FtE.HE_p9)) { __state = 0; return; }", "Hit", "Gated"),
    (F, "internal static class HitEvidence_ImpactPatch", "private static Exception Finalizer(", FIN, "Hit", "Gated"),
]
