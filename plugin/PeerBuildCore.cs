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
        /// <summary>Key names per printed line (merge pass 6, R-L2): every key
        /// the seat published is listed, the first KEYS_PER_LINE on the line
        /// itself and the rest on continuation lines of the same tag, so no key
        /// name is left out.</summary>
        internal const int KEYS_PER_LINE = 32;
        /// <summary>Every printed value is cut to this many characters.</summary>
        internal const int MAX_TOKEN = 40;
        /// <summary>A key name is printed whole up to this many characters
        /// (merge pass 6, R-L2); a longer one prints its first KEY_HEAD
        /// characters, its length and a hash of the whole name (KeyToken).</summary>
        internal const int MAX_KEY = 64;
        internal const int KEY_HEAD = 48;

        /// <summary>The keys whose values are printed: the build statement and
        /// every capability key the plugin declares (PoisonSync v2 and v3,
        /// ProximityVictim, DcReportSync x2, SawTargetSync, GrowNormalize,
        /// WeaponCooldownReset, FfaMapScale, FfaCardSequence, the shared game
        /// token's version). test_peer_build_and_evidence_gates_client.py holds
        /// this list equal to the plugin's cr_ constants whose name says
        /// capability (Capability or CAP).</summary>
        internal static readonly string[] ValueKeys =
        {
            BuildProp, "cr_dc2", "cr_dc3", "cr_ffacfg", "cr_game_token_v", "cr_grow2", "cr_msv2",
            "cr_pois2", "cr_pois3", "cr_prox1", "cr_saw1", "cr_wcd1",
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

        /// <summary>A key name as printed: characters outside [A-Za-z0-9_.|+:-]
        /// become '?'. A name with such a character, or longer than MAX_KEY,
        /// also carries '#' and the FNV-1a hash of the whole name (8 hex
        /// digits), and a long one is cut to KEY_HEAD characters plus '~' and
        /// its length first, so two published names that differ anywhere print
        /// differently except on a 32-bit hash collision.</summary>
        internal static string KeyToken(string s)
        {
            if (s == null) return "null";
            var sb = new StringBuilder(Math.Min(s.Length, MAX_KEY) + 16);
            bool masked = false;
            int take = s.Length > MAX_KEY ? KEY_HEAD : s.Length;
            for (int i = 0; i < s.Length; i++)
            {
                char c = s[i];
                bool ok = (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9')
                          || c == '_' || c == '.' || c == '|' || c == '+' || c == ':' || c == '-';
                if (!ok) masked = true;
                if (i < take) sb.Append(ok ? c : '?');
            }
            if (s.Length > MAX_KEY)
                sb.Append('~').Append(s.Length.ToString(System.Globalization.CultureInfo.InvariantCulture));
            if (masked || s.Length > MAX_KEY)
            {
                uint h = 2166136261;
                for (int i = 0; i < s.Length; i++) { h ^= s[i]; h *= 16777619; }
                sb.Append('#').Append(h.ToString("x8", System.Globalization.CultureInfo.InvariantCulture));
            }
            return sb.ToString();
        }

        /// <summary>The line for one remote seat. props maps each published
        /// key (as text) to its value (as text); only ValueKeys values are
        /// read. More than KEYS_PER_LINE keys continue on further lines
        /// ("[PEER-BUILD] actor=N list(2/3)=..."), joined by '\n' into the one
        /// string the caller logs.</summary>
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
            int lines = keys.Count == 0 ? 1 : (keys.Count + KEYS_PER_LINE - 1) / KEYS_PER_LINE;
            for (int i = 0; i < keys.Count && i < KEYS_PER_LINE; i++)
            {
                if (i > 0) sb.Append(',');
                sb.Append(KeyToken(keys[i]));
            }
            if (keys.Count == 0) sb.Append('-');
            if (lines > 1) sb.Append(" lines=").Append(lines);
            sb.Append(' ').Append(Values(props));
            for (int l = 1; l < lines; l++)
            {
                sb.Append("\n[PEER-BUILD] actor=").Append(actor)
                  .Append(" list(").Append(l + 1).Append('/').Append(lines).Append(")=");
                for (int i = l * KEYS_PER_LINE; i < keys.Count && i < (l + 1) * KEYS_PER_LINE; i++)
                {
                    if (i > l * KEYS_PER_LINE) sb.Append(',');
                    sb.Append(KeyToken(keys[i]));
                }
            }
            return sb.ToString();
        }
    }
}
