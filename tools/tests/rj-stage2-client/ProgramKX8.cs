using System;
using System.Collections.Generic;
using System.Linq;

namespace CompetitiveRounds.Stage2Harness
{
    using R = TeamHoldRules;

    internal static partial class Program
    {
        // ── KX8: the capability token (V3 S0 step 4) ─────────────────────────

        private static void RegisterKX8()
        {
            // The rjs1 field rides the join and lobby bodies only when every
            // Stage 2 patch attached; a partial attach sends today's body, so
            // the server never opens a hold for a client that cannot run it.
            Add("tx8_caps", () =>
            {
                string body = "{\"steam_id\":\"1001\",\"queue_type\":\"auto\"" + R.CapsField(true) + "}";
                return All(Expect("attached", R.CapsField(true), ",\"caps\":\"rjs1\""),
                           Expect("partial", R.CapsField(false), ""),
                           Expect("body", body, "{\"steam_id\":\"1001\",\"queue_type\":\"auto\",\"caps\":\"rjs1\"}"));
            });
        }
    }
}
