# rest.py: the outermost live entries of SeatEvidence, PointEvidence, IdentityClockEvidence, CardDrawEvidence and
# PeerBuild (entries.py says which and why). Saw.Update's one-line prefix has no brace line of its own and is done
# by an #if SCR_FRAMETIME / #else pair in edit_part2e.py instead. IC-p1 and IC-p4 leave __state -1, the value their
# partners already treat as "nothing entered" (IdentityClockEvidence.cs:376 and the postfix's __state < 0 return).


def c(cls):
    return "internal static class " + cls


def skip(e, tail="return;"):
    return "if (FtCensus.Skip(FtE.%s)) %s" % (e, tail)


FIN = "if (FtGate.Off) return __exception;"
SE, PS, IC, CD, PB = ("plugin/SeatEvidence.cs", "plugin/PoisonSync.cs", "plugin/IdentityClockEvidence.cs",
                      "plugin/CardDrawEvidence.cs", "plugin/PeerBuild.cs")
SPECS = [
    (SE, c("SeatEvidence"), "internal static void NoteView(int actor, int stamp)", skip("SE_c50"), "Seat", "Gated"),
    (SE, c("SeatEvidence"), "internal static void CompatTick()", skip("SE_c52"), "Seat", "Gated"),
    (SE, c("SeatEvidence"), "internal static void Tick()", skip("SE_c53"), "Seat", "Gated"),
    (SE, c("SeatEvidence_RpcSendPatch"), "private static void Postfix(", skip("SE_p1"), "Seat", "Gated"),
    (SE, c("SeatEvidence_DoBlockPatch"), "private static Exception Finalizer(", skip("SE_p2", "return __exception;"),
     "Seat", "Gated"),
    (SE, c("SeatEvidence_TryBlockMePatch"), "private static Exception Finalizer(", skip("SE_p3", "return __exception;"),
     "Seat", "Gated"),
    (PS, c("PointEvidence"), "internal static void Drain()", skip("PT_c5"), "Point", "Gated"),
    (PS, c("SawPointEvidencePatch"), "private static Exception After(", FIN, "Point", "Gated"),
    (IC, c("IdentityClockEvidence"), "internal static void Tick()", skip("IC_c6"), "Identity", "Gated"),
    (IC, c("IdentityClock_ExecuteRpcPatch"), "private static void Prefix(", skip("IC_p1", "{ __state = -1; return; }"),
     "Identity", "Gated"),
    (IC, c("IdentityClock_ExecuteRpcPatch"), "private static Exception Finalizer(", FIN, "Identity", "Gated"),
    (IC, c("IdentityClock_MovementPatch"), "private static void Prefix(", skip("IC_p4", "{ __state = -1; return; }"),
     "Identity", "Gated"),
    (IC, c("IdentityClock_MovementPatch"), "private static void Postfix(", "if (FtGate.Off) return;", "Identity", "Gated"),
    (CD, c("CardDrawEvidence"), "internal static void Tick()", skip("CD_c6"), "CardDraw", "Gated"),
    (CD, c("CardDrawEvidence"), "internal static void EnsureCensusDump()", skip("CD_c7"), "CardDraw", "Gated"),
    (PB, c("PeerBuild"), "internal static void StageBuildProp(string source)", skip("PB_c2"), "PeerBuild", "Gated"),
    (PB, c("PeerBuild"), "internal static void Tick()", skip("PB_c3"), "PeerBuild", "Gated"),
]
