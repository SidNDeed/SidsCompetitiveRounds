#if SCR_FRAMETIME
using System;
using System.IO;

namespace CompetitiveRounds
{
    /// <summary>FrameTime F18, the named switch (build brief section 5). Under reading A (the sentinel's f18=A,
    /// the default), each game over gets one answer_replay line: either a replay call, made from FtSchedule at a
    /// frame boundary that read the frame not live (or from FtSchedule.GameStart in a frame that started not live),
    /// or a skip line (Skip) where FtSchedule may make no call. A replay call feeds one recorded server answer to
    /// SeatEvidence's Answer path against a scratch copy of the queue file under BepInEx/frametime/replay/, and the answer's
    /// handling is timed in its own span of kind REPLAY, reported apart from the between-point figure (the
    /// answer_replay line and the census span rows). While Running, SeatEvidence's QueuePath names the scratch
    /// copy, its Load and Enqueue refusals let the scratch through, and PromoteSpool is held off, so the real
    /// queue file is only read (copied) and no closing file is touched. Under reading B there is no replay, and
    /// the settled and point lines carry answer=unmeasured.</summary>
    internal static class FtReplay
    {
        internal static bool Running;
        internal static string Dir => Path.Combine(FtConfig.Dir, "replay");
        internal static string QueuePath => Path.Combine(Dir, "CompetitiveRounds.seat-evidence.jsonl");

        /// <summary>The settled and point lines' answer field.</summary>
        internal static string AnswerField => FtConfig.F18 == "A" ? "replay" : "unmeasured";

        internal static void Run(int game)
        {
            if (FtConfig.F18 != "A" || !FtConfig.Present) return;
            string result;
            long ticks = 0;
            try
            {
                Directory.CreateDirectory(Dir);
                if (File.Exists(QueuePath)) File.Delete(QueuePath);
                if (File.Exists(QueuePath + ".tmp")) File.Delete(QueuePath + ".tmp");
                string real = SeatEvidence.FtRealQueuePath();
                if (File.Exists(real)) File.Copy(real, QueuePath);   // reads the real file; never writes it
                Running = true;
                result = SeatEvidence.FtReplayAnswer(game, out ticks);
            }
            catch (Exception ex) { result = "error_" + ex.GetType().Name; }
            finally { Running = false; }
            Plugin.Log.LogInfo("[FRAME-TIME] answer_replay g=" + game + " ticks=" + ticks + " result=" + result);
        }

        /// <summary>FtSchedule drains a game's owed replay where no replay call may run: GameStart or the settle cap in
        /// a frame that started live (result skipped_live), or the quit flush (skipped_quit). No call is made, and the
        /// game's line says why. As f18() reads it, a measured game's line (g at or above its first_game, 1 by
        /// default) whose result is not settled fails F18; a game-0 line counts only toward records_missing()'s one
        /// line per game.</summary>
        internal static void Skip(int game, string result)
        {
            if (FtConfig.F18 != "A" || !FtConfig.Present) return;
            Plugin.Log.LogInfo("[FRAME-TIME] answer_replay g=" + game + " ticks=0 result=" + result);
        }
    }
}
#endif
