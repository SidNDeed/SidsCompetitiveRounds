using System;
using System.Collections.Generic;
using System.Text;

namespace CompetitiveRounds
{
    /// <summary>EVIDENCE ONLY: the pure half of the [PEER-BUILD] line, which
    /// states what one remote seat in the room published, so a review of a
    /// player report can say which build the other seat ran. No Unity, no
    /// Photon: tools/tests/hit-evidence-client compiles this file as it ships.
    ///
    /// The line carries the seat's Photon actor number, every custom property
    /// KEY the seat published, and the VALUE of only the keys in ValueKeys:
    /// those that state a mod version, a build variant or a capability. No
    /// other value is printed, so an account id or a display name carried in
    /// some other key never reaches the log. A seat that published no key of
    /// ours (none starting with OurPrefix) gets the line with ours=none.</summary>
    internal static class PeerBuildCore
    {
        /// <summary>This build's own statement of itself, staged pre-join by
        /// PeerBuild.StageBuildProp: "version|variant|commit".</summary>
        internal const string BuildProp = "cr_build";
        internal const string OurPrefix = "cr_";
        /// <summary>At most this many key names are listed; the rest are
        /// counted ("+N").</summary>
        internal const int MAX_KEYS = 64;
        /// <summary>Every printed key or value is cut to this many characters.</summary>
        internal const int MAX_TOKEN = 40;

        /// <summary>The keys whose values are printed: the build statement and
        /// every capability key the plugin declares (PoisonSync, ProximityVictim,
        /// DcReportSync x2, SawTargetSync, GrowNormalize, WeaponCooldownReset,
        /// FfaMapScale, FfaCardSequence).
        /// test_peer_build_and_evidence_gates_client.py holds this list equal to
        /// the plugin's *CapabilityProp constants.</summary>
        internal static readonly string[] ValueKeys =
        {
            BuildProp, "cr_dc2", "cr_dc3", "cr_ffacfg", "cr_grow2", "cr_msv2",
            "cr_pois2", "cr_prox1", "cr_saw1", "cr_wcd1",
        };

        /// <summary>A printable token: characters outside [A-Za-z0-9_.|+:-] become
        /// '?', and anything longer than MAX_TOKEN is cut and marked '~'. Null
        /// prints as "null".</summary>
        internal static string Token(string s)
        {
            if (s == null) return "null";
            var sb = new StringBuilder(Math.Min(s.Length, MAX_TOKEN + 1));
            for (int i = 0; i < s.Length; i++)
            {
                if (sb.Length >= MAX_TOKEN) { sb.Append('~'); break; }
                char c = s[i];
                bool ok = (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9')
                          || c == '_' || c == '.' || c == '|' || c == '+' || c == ':' || c == '-';
                sb.Append(ok ? c : '?');
            }
            return sb.ToString();
        }

        /// <summary>The value part of the line, which is also what decides
        /// whether the line is printed again in the same room: every ValueKeys
        /// entry in order, its value or '-' when the seat did not publish it.</summary>
        internal static string Values(IDictionary<string, string> props)
        {
            var sb = new StringBuilder();
            for (int i = 0; i < ValueKeys.Length; i++)
            {
                string v;
                if (i > 0) sb.Append(' ');
                sb.Append(ValueKeys[i]).Append('=');
                sb.Append(props != null && props.TryGetValue(ValueKeys[i], out v) ? Token(v) : "-");
            }
            return sb.ToString();
        }

        /// <summary>The whole line for one remote seat. props maps each
        /// published key (as text) to its value (as text); only ValueKeys
        /// values are read.</summary>
        internal static string Line(int actor, IDictionary<string, string> props)
        {
            var keys = new List<string>();
            int ours = 0;
            if (props != null)
                foreach (var k in props.Keys)
                {
                    if (k == null) continue;
                    keys.Add(k);
                    if (k.StartsWith(OurPrefix, StringComparison.Ordinal)) ours++;
                }
            keys.Sort(StringComparer.Ordinal);
            var sb = new StringBuilder("[PEER-BUILD] actor=");
            sb.Append(actor).Append(" keys=").Append(keys.Count)
              .Append(" ours=").Append(ours > 0 ? ours.ToString(System.Globalization.CultureInfo.InvariantCulture) : "none")
              .Append(" list=");
            int shown = Math.Min(keys.Count, MAX_KEYS);
            for (int i = 0; i < shown; i++)
            {
                if (i > 0) sb.Append(',');
                sb.Append(Token(keys[i]));
            }
            if (keys.Count == 0) sb.Append('-');
            if (keys.Count > shown) sb.Append(",+").Append(keys.Count - shown);
            sb.Append(' ').Append(Values(props));
            return sb.ToString();
        }
    }
}
