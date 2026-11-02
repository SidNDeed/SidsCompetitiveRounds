# upkeep.py: spans (kind Upkeep, never gated) on the boundary and not-live entries of INVENTORY.md, for placement
# (B3) and the between-point costs (V4 3.9). These entries run in both arms, so they carry no census row and no
# gate; the guard line is a comment. Outermost only (FtSpan's depth): a nested entry (SeatEvidence.RoomExit inside
# HitEvidence.ResetForRoomExit, Enqueue* inside a record build) opens nothing and its time is its caller's.
# No iterator method is spanned (a span would close when the enumerator is created, not when it runs).

GUARD = "// boundary or not-live entry: spanned, never gated (upkeep.py)"


def c(cls):
    return "internal static class " + cls


CD, CE, HE, IC, PB, PS, SE = ("plugin/CardDrawEvidence.cs", "plugin/CombatEvidence.cs", "plugin/HitEvidence.cs",
                              "plugin/IdentityClockEvidence.cs", "plugin/PeerBuild.cs", "plugin/PoisonSync.cs",
                              "plugin/SeatEvidence.cs")
_M = [
    (CD, "CardDrawEvidence", "CardDraw", ["internal static void RoomExit()", "internal static void FreezeRoomFacts()",
                                          "internal static void Dispatch(", "internal static void FlushOnQuit()",
                                          "internal static void BootLine()"]),
    (CD, "CardDrawEvidence_StartPickPatch", "CardDraw", ["private static void Postfix("]),
    (CD, "CardDrawEvidence_CardAwakePatch", "CardDraw", ["private static void Postfix("]),
    (CD, "CardDrawEvidence_EndPickPatch", "CardDraw", ["private static void Prefix("]),
    (CD, "CardDrawEvidence_DonePickingPatch", "CardDraw", ["private static void Prefix("]),
    (CD, "CardDrawEvidence_PickPatch", "CardDraw", ["private static void Postfix(", "private static Exception Finalizer("]),
    (CD, "CardDrawEvidence_OfflinePickPatch", "CardDraw", ["private static void Postfix(",
                                                          "private static Exception Finalizer("]),
    (CE, "CombatEvidence", "Combat", ["internal static void BeginGame(bool oneVOne)", "internal static void RoomExit()",
                                      "private static void PointEnd(Game g, int now)", "internal static void Dispatch(",
                                      "internal static void FlushOnQuit()", "internal static void BootLine()"]),
    (HE, "HitEvidence", "Hit", ["internal static void PointEnd(int point)", "internal static void GameEnd(int point)",
                                "internal static void ResetForRoomExit(int point)"]),
    (HE, "HitEvidence_StartGamePatch", "Hit", ["private static Exception Finalizer("]),
    (HE, "HitEvidence_FfaDoStartGamePatch", "Hit", ["private static Exception Finalizer("]),
    (IC, "IdentityClockEvidence", "Identity", ["internal static void BootCheck(", "internal static void BeginGame(",
                                               "internal static void Dispatch(", "internal static void FlushOnQuit()",
                                               "internal static string ClockHeaderNow()", "internal static void BootLine()"]),
    (IC, "IdentityClock_PointStartPatch", "Identity", ["private static void Prefix("]),
    (IC, "IdentityClock_MovePlayersPatch", "Identity", ["private static void Prefix("]),
    (PB, "PeerBuild", "PeerBuild", ["internal static string BuildValue()"]),
    (PS, "PointEvidence", "Point", ["internal static void ResetForRoomExit()", "internal static void GameOverCheck(",
                                    "internal static void PointEnd()"]),
    (PS, "PointEndEvidencePatch", "Point", ["private static void Snap(", "private static void After("]),
    (SE, "SeatEvidence", "Seat", ["internal static void BeginGame(", "internal static void RoomExit()",
                                  "internal static void NoteEnd(string kind)", "internal static void ClearEnd()",
                                  "internal static void StartHashing()", "internal static void CompleteIdentityNow()",
                                  "internal static void NoteCompat(", "internal static void Dispatch(",
                                  "internal static void FlushOnQuit()", "internal static string StableOf(",
                                  "internal static bool SpoolClosing(", "internal static bool EnqueueCard(",
                                  "internal static bool EnqueueCombat(", "internal static bool EnqueueIdentity("]),
]
SPECS = [(f, c(cls), sig, GUARD, comp, "Upkeep") for f, cls, comp, sigs in _M for sig in sigs]
