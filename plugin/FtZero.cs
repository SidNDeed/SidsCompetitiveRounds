#if SCR_FRAMETIME
using Photon.Pun;

namespace CompetitiveRounds
{
    /// <summary>FrameTime washout validation (METHOD-V4.md 3.3; tools/frametime/ZERO-STATE.md):
    /// the zero-state check of each point. Early, at the point's first frame boundary
    /// (FtSchedule.StartPoint, before any hook of that frame): no projectile object alive
    /// (bit 0) and the rows the components can be read for before their own point start
    /// (CombatEvidence 1, 4, 6 to 9; HitEvidence 10 to 12; SeatEvidence 13;
    /// IdentityClockEvidence 14 and 15; PointEvidence 16 and 17). Late, right after
    /// CombatEvidence's own PointStart, which resets rows 2, 3 and 5 (it runs only at
    /// points where CombatEvidence runs, so zl=1 marks a point whose late rows were read).
    /// Bit 30: a check threw. The point line carries zs (the failing rows) and zl; the
    /// parser voids every round holding a point with zs != 0 (VR8).
    /// The game-0 mutant (sentinel key zs_mutant, default 1): in game 0 only, CombatEvidence's
    /// PointReset leaves one volley-window entry (row 2) alive across every point boundary,
    /// and the check must void every round of game 0.</summary>
    internal static class FtZero
    {
        internal static int Mask;
        internal static int LateSeen;
        private static int _pendingLate;
        private static long _pendingFrame = long.MinValue;

        internal static bool MutantNow => FtSchedule.Game == 0 && FtConfig.Get("zs_mutant", "1") != "0";

        /// <summary>A projectile whose view is alive and active (ZERO-STATE.md IsLiveProj, with the active test
        /// that leaves switched-off pooled carriers out).</summary>
        internal static bool IsLiveProj(int id)
        {
            if (id == 0) return false;
            PhotonView v = PhotonNetwork.GetPhotonView(id);
            return v != null && v.gameObject.activeInHierarchy && v.GetComponent<ProjectileHit>() != null;
        }

        internal static void Early()
        {
            int m = 0;
            try { if (UnityEngine.Object.FindObjectsOfType<ProjectileHit>().Length != 0) m |= 1; } catch { m |= 1 << 30; }
            try { m |= CombatEvidence.FtZeroState(false); } catch { m |= 1 << 30; }
            try { m |= HitEvidence.FtZeroState(); } catch { m |= 1 << 30; }
            try { m |= SeatEvidence.FtZeroState(); } catch { m |= 1 << 30; }
            try { m |= IdentityClockEvidence.FtZeroState(); } catch { m |= 1 << 30; }
            try { m |= PointEvidence.FtZeroState(); } catch { m |= 1 << 30; }
            LateSeen = 0;
            // CombatEvidence reads the live predicate in Update, FtSchedule in EarlyUpdate: a late result from
            // the frame just before this boundary belongs to this point.
            if (_pendingFrame >= FtClock.Frames - 1) { m |= _pendingLate; LateSeen = 1; }
            _pendingLate = 0;
            _pendingFrame = long.MinValue;
            Mask = m;
        }

        /// <summary>From CombatEvidence right after its PointStart: rows 2, 3 and 5.</summary>
        internal static void Late(int m)
        {
            if (FtSchedule.Live)
            {
                Mask |= m;
                LateSeen = 1;
            }
            else
            {
                _pendingLate |= m;
                _pendingFrame = FtClock.Frames;
            }
        }
    }
}
#endif
