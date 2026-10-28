using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;

namespace CompetitiveRounds.Stage2Harness
{
    using N = TeamHoldNet;

    internal static partial class Program
    {
        // ── KX9 Part A: the request side against the server request models ──

        /// <summary>A fixture copy of the server request models at the Stage 2
        /// server lane's fix 1 author tip (backend/api/match_hold.py): the
        /// required fields (Field(...) with no default, plus the team open's
        /// M7 points, refused as missing_points at line 749) and the optional
        /// ones. Keyed by route; the "?" routes are GET queries.</summary>
        private static readonly Dictionary<string, string[][]> ServerModels = new Dictionary<string, string[][]>
        {
            // GameStartReq, lines 306-311
            { "game_start", new[] { new[] { "steam_id", "mode", "series_id", "room" }, new[] { "prev_game" } } },
            // BeatReq, lines 527-534
            { "beat", new[] { new[] { "steam_id", "mode", "series_id", "room" }, new[] { "actor", "seen", "boundary_digest" } } },
            // HoldOpenReq, lines 584-595 (t1_points/t2_points required for a team hold, line 749)
            { "open", new[] { new[] { "request_id", "opener_steam_id", "mode", "room", "game_id", "held_steam_id", "slot", "team", "t1_points", "t2_points" },
                              new[] { "hmac" } } },
            // HoldEndReq, lines 885-887
            { "end", new[] { new[] { "steam_id", "reason" }, new string[0] } },
            // HoldClaimReq, lines 1040-1041
            { "claim", new[] { new[] { "steam_id" }, new string[0] } },
            // HoldBindReq, lines 1125-1128
            { "bind", new[] { new[] { "steam_id", "actor" }, new[] { "region" } } },
            // HoldEnteredReq, lines 1233-1236
            { "entered", new[] { new[] { "steam_id", "game_id", "actor" }, new string[0] } },
            // GET /hold/{id}/state (line 849), /hold/by-room (line 866), /hold/mine (line 1001)
            { "state?", new[] { new[] { "steam_id" }, new string[0] } },
            { "by-room?", new[] { new[] { "room", "game_id", "steam_id" }, new string[0] } },
            { "mine?", new[] { new[] { "steam_id" }, new string[0] } },
        };

        /// <summary>The top-level keys of a flat JSON object and whether each
        /// value is the literal null.</summary>
        private static Dictionary<string, bool> TopKeys(string json)
        {
            var keys = new Dictionary<string, bool>(StringComparer.Ordinal);
            int depth = 0;
            for (int i = 0; i < json.Length; i++)
            {
                char c = json[i];
                if (c == '"')
                {
                    int j = i + 1;
                    var sb = new StringBuilder();
                    while (j < json.Length && json[j] != '"') { if (json[j] == '\\') j++; if (j < json.Length) sb.Append(json[j]); j++; }
                    int k = j + 1;
                    if (depth == 1 && k < json.Length && json[k] == ':')
                        keys[sb.ToString()] = string.CompareOrdinal(json, k + 1, "null", 0, 4) == 0;
                    i = j;
                    continue;
                }
                if (c == '{' || c == '[') depth++;
                else if (c == '}' || c == ']') depth--;
            }
            return keys;
        }

        private static Dictionary<string, bool> QueryKeys(string path)
        {
            var keys = new Dictionary<string, bool>(StringComparer.Ordinal);
            int q = path.IndexOf('?');
            if (q < 0) return keys;
            foreach (var kv in path.Substring(q + 1).Split('&'))
            {
                int e = kv.IndexOf('=');
                if (e > 0) keys[kv.Substring(0, e)] = kv.Length == e + 1;
            }
            return keys;
        }

        /// <summary>Null when the keys meet the model: every required field
        /// present and not null, no field the model does not read.</summary>
        private static string MeetsModel(string route, Dictionary<string, bool> keys)
        {
            var m = ServerModels[route];
            foreach (var r in m[0])
            {
                bool isNull;
                if (!keys.TryGetValue(r, out isNull)) return route + " omits required " + r;
                if (isNull) return route + " sends required " + r + " as null";
            }
            foreach (var k in keys.Keys)
                if (!m[0].Contains(k) && !m[1].Contains(k)) return route + " sends " + k + ", which the model does not read";
            return null;
        }

        private static void RegisterKX9()
        {
            // T1.6 extended: every hold request body and query the client
            // builds is its server request model, field for field.
            Add("t16_server_model_fields", () =>
            {
                const string me = "1001", sid = "5b1f8e2a-1c3d-4e5f-8a9b-0c1d2e3f4a5b", g = "7c2e9d1a-2b3c-4d5e-9f8a-1b2c3d4e5f6a";
                var seen = new List<KeyValuePair<int, string>> { new KeyValuePair<int, string>(2, "1002") };
                var checks = new List<string>
                {
                    MeetsModel("game_start", TopKeys(N.GameStartBody(me, "team", sid, "team_ab12", null))),
                    MeetsModel("beat", TopKeys(N.BeatBody(me, "team", sid, "team_ab12", 1, seen, null))),
                    MeetsModel("open", TopKeys(N.OpenBody("0123456789abcdef", "team", "team_ab12", g, "1002", 1, 1, me, 1, 0, "ab12"))),
                    MeetsModel("end", TopKeys(N.EndBody(me, "no_answer"))),
                    MeetsModel("claim", TopKeys(N.ClaimBody(me))),
                    MeetsModel("bind", TopKeys(N.BindBody(me, 9, "eu"))),
                    MeetsModel("entered", TopKeys(N.EnteredBody(me, g, 9))),
                    MeetsModel("state?", QueryKeys(N.PathState("h1", me))),
                    MeetsModel("by-room?", QueryKeys(N.PathByRoom("team_ab12", g, me))),
                    MeetsModel("mine?", QueryKeys(N.PathMineFor(me))),
                };
                var bad = checks.Where(c => c != null).ToList();
                return bad.Count == 0 ? null : string.Join("; ", bad);
            });
            // Every reason the client posts to /end is one of the server's
            // END_REASONS (match_hold.py lines 403-407; any other is a 400).
            Add("t16_end_reasons_server_set", () =>
            {
                var server = new HashSet<string> { "refused", "no_answer", "second_departure", "ceiling", "survivor_leave",
                    "token_refused", "snapshot_failed", "registration_refused", "activation_timeout", "entry_refused", "bind_timeout" };
                var local = new[] { "refused:not_member", "no_answer", "second_departure", "ceiling", "survivor_leave",
                                    "token_refused", "entry bound", "something new" };
                var stages = new[] { "Claim", "Join", "Bind", "Token", "Latch", "Snapshot", "Register", "Activate", "Entered", "Ended" };
                foreach (var l in local)
                {
                    string r = N.EndReasonFor(l);
                    if (!server.Contains(r)) return "local " + l + " posts " + r;
                }
                foreach (var s in stages)
                {
                    string r = N.ReturnEndReason(s, "x");
                    if (!server.Contains(r)) return "stage " + s + " posts " + r;
                }
                return All(Expect("refused prefix", N.EndReasonFor("refused:not_member"), "refused"),
                           Expect("kept", N.EndReasonFor("ceiling"), "ceiling"),
                           Expect("token stage", N.ReturnEndReason("Token", "x"), "token_refused"));
            });
            // H2 / K3: the state answer carries the stored hand-over verifier
            // while claimed or bound (match_hold.py line 473, "verifier"); the
            // master's token check reads it, and a state without it refuses.
            Add("tx9_verifier_k3", () =>
            {
                string token = "9f8e7d6c5b4a39281706f5e4d3c2b1a0";
                string hex;
                using (var sha = System.Security.Cryptography.SHA256.Create())
                    hex = string.Concat(sha.ComputeHash(Encoding.UTF8.GetBytes(token)).Select(b => b.ToString("x2")));
                string bound = "{\"hold_id\":\"h1\",\"game_id\":\"g-8\",\"mode\":\"team\",\"room_name\":\"team_ab12\",\"slot\":1,\"team\":1,\"n\":1,"
                               + "\"state\":\"bound\",\"seq\":4,\"deadline_s\":50,\"hold_s\":50,\"bound_actor\":9,\"verifier\":\"" + hex + "\","
                               + "\"closed_at\":null,\"closed_reason\":null}";
                string opened = bound.Replace("\"bound\"", "\"opened\"").Replace("\"" + hex + "\"", "null");
                N.StateAnswer b, o;
                bool pb = N.TryParseState(200, bound, out b), po = N.TryParseState(200, opened, out o);
                return All(Expect("parsed", pb && po, true), Expect("verifier", b.Verifier, hex),
                           Expect("token ok", TeamHoldRules.TokenOk("h1:" + token, "h1", b.Verifier), true),
                           Expect("wrong token", TeamHoldRules.TokenOk("h1:other", "h1", b.Verifier), false),
                           Expect("no verifier", TeamHoldRules.TokenOk("h1:" + token, "h1", o.Verifier), false));
            });
        }
    }
}
