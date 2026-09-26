using System;
using System.Collections.Generic;
using System.Globalization;

namespace CompetitiveRounds
{
    /// <summary>The game a 2v2 live-points post names (v1.41.0 beta review
    /// round 3, finding 1: the client half, round 4).
    ///
    /// The server files an ATTESTED post, one that carries game_number and
    /// photon_room_id signed with its pair, only under exactly the game it
    /// names, and it names a game by its own count: the games recorded on the
    /// series plus one, in the room the series row stores (main.py,
    /// _team_game_identity and _record_team_game_points). So a post naming the
    /// game the server is in is evidence for that game, and a post the server
    /// processes after it has moved on is filed nowhere, however late it
    /// lands. That holds only while the number a post carries is never AHEAD
    /// of the server's count: a post from game N naming N+1 is filed under
    /// N+1 as soon as the server gets there, which is review finding 1's false
    /// positive over again.
    ///
    /// So the number is the server's own count, never a free-running one. At
    /// every game start in a cr_ff room (GameStateWatcher.OnMatchStarted, the
    /// event that also resets the pair the post carries) it is frozen as the
    /// recorded games of THIS series, the highest any read of
    /// team/series/{id}/state has shown, plus one. Every read counted was
    /// answered before this game started, and the server only ever adds to
    /// that count (main.py's two writers of t1_series_wins/t2_series_wins each
    /// add one game), so the frozen number is at most the game the server was
    /// in when this game started, and a post naming it is filed only if the
    /// server is still in that game when the post is processed. A stale read
    /// names a LOWER number, and then this game's posts are filed nowhere,
    /// which after the first game of a sitting settles exactly as a post
    /// without the pair does (neither counts). After every 2v2 game over
    /// ApiClient.RefreshTeamGameRecord reads the count again, so the next
    /// game starts from a fresh one.
    ///
    /// The client's own count, in FFA's gameNumber shape (advanced at each
    /// game start, restarted when the series or the room changes, cleared
    /// when the room is left), is kept for two things only: the drift note
    /// logged at every game start, and the one case where a number is safe
    /// without any read: a series' FIRST game start in a room is named 1. No
    /// game number is lower, so 1 is never ahead of the server; in a sitting
    /// resumed at a later game it is behind, and that game's posts are filed
    /// nowhere. With no read and a later game start the post goes without the
    /// pair. An unverified count is exactly the one that runs ahead of the
    /// server, after the first game the server does not record.
    ///
    /// Nothing here touches Photon or Unity. The sentinel below runs the same
    /// Tracker class the game runs, in the game through the [Broadcast]
    /// TestTeamGameNumberSentinel lever and outside it from this file.</summary>
    internal static class TeamGameNumber
    {
        internal const string SentinelTag = "[TEAM-GAME-NUMBER-SENTINEL]";
        internal const string LogTag = "[2V2-GAME]";

        /// <summary>The server's bounds on the pair (update_team_live_points:
        /// game_number Query(ge=1, le=99), photon_room_id Query(max_length=128)).
        /// A value outside them would get the whole request refused, the points
        /// included, so such a post goes without the pair instead.</summary>
        internal const int MaxGameNumber = 99;
        internal const int MaxRoomLength = 128;

        /// <summary>The seat's own tracker, fed by GameStateWatcher and
        /// ApiClient. The sentinel builds its own and never touches this one.</summary>
        internal static readonly Tracker Live = new Tracker();

        private static string Num(int v) { return v.ToString(CultureInfo.InvariantCulture); }

        /// <summary>What a post WITHOUT the pair signs (update_team_live_points).</summary>
        internal static string LegacyCanonical(string seriesId, string reporterSteamId, int t1Points, int t2Points)
        {
            return "team-live-points:" + seriesId + ":" + reporterSteamId + ":" + Num(t1Points) + ":" + Num(t2Points);
        }

        /// <summary>What a post WITH the pair signs, exactly as the server builds
        /// it: series, reporter, t1, t2, game number, room, the room unescaped.</summary>
        internal static string AttestedCanonical(string seriesId, string reporterSteamId, int t1Points, int t2Points,
                                                 int gameNumber, string photonRoomId)
        {
            return "team-live-points-game:" + seriesId + ":" + reporterSteamId + ":" + Num(t1Points) + ":" + Num(t2Points)
                   + ":" + Num(gameNumber) + ":" + photonRoomId;
        }

        /// <summary>The two query parameters, both or neither: the caller passes
        /// the room already URL-escaped.</summary>
        internal static string QueryPair(int gameNumber, string escapedRoom)
        {
            return "&game_number=" + Num(gameNumber) + "&photon_room_id=" + escapedRoom;
        }

        /// <summary>A room this client names: non-empty, within the server's
        /// length bound, and without outer white space (the server signs the
        /// room as sent but compares it stripped).</summary>
        internal static bool RoomSendable(string photonRoomId)
        {
            if (string.IsNullOrEmpty(photonRoomId) || photonRoomId.Length > MaxRoomLength) return false;
            return photonRoomId.Trim().Length == photonRoomId.Length;
        }

        /// <summary>Whether a post can carry the pair: a number the server
        /// accepts and a room it accepts. Otherwise it goes without the pair.</summary>
        internal static bool Sendable(int gameNumber, string photonRoomId)
        {
            return gameNumber >= 1 && gameNumber <= MaxGameNumber && RoomSendable(photonRoomId);
        }

        // The contract pin. backend/tests/test_team_series_report_dc.py reads
        // these four literals, signs PinExpected and asks the server's own
        // signature check to accept it for these inputs (t1 2, t2 1, game 3);
        // the sentinel checks that AttestedCanonical builds PinExpected.
        internal const string PinSeries = "5b0c7e1a-2d3f-4a5b-8c6d-7e8f9a0b1c2d";
        internal const string PinReporter = "90000000000700009";
        internal const string PinRoom = "team_pin_room";
        internal const string PinExpected =
            "team-live-points-game:5b0c7e1a-2d3f-4a5b-8c6d-7e8f9a0b1c2d:90000000000700009:2:1:3:team_pin_room";

        internal sealed class Tracker
        {
            // Recorded games per series: the highest any read showed. A seat
            // plays one series at a time; a few entries cover a late answer for
            // the one before, and a full map is simply dropped (a lost read costs
            // a number, never a wrong one).
            private const int MaxSeries = 8;
            private readonly Dictionary<string, int> recorded = new Dictionary<string, int>(StringComparer.Ordinal);
            // Series whose server refused the attested form (ApiClient's 403
            // fallback): their posts go without the pair from then on.
            private readonly HashSet<string> refused = new HashSet<string>(StringComparer.Ordinal);
            // The game frozen at the last game start; 0 = no number.
            private string gameSeries = "", gameRoom = "";
            private int gameNumber;
            // The own count: game starts seen for (countSeries, countRoom).
            private string countSeries = "", countRoom = "";
            private int countStarts;

            /// <summary>A read of team/series/{id}/state for `seriesId`.
            /// `hasWins`: the answer carried both win counts (the canceled and
            /// dc_incomplete answers carry neither, and a missing field parses as
            /// 0, which is not a read). Never lowers what an earlier read showed.</summary>
            internal void ObserveRead(string seriesId, bool hasWins, int t1Wins, int t2Wins)
            {
                if (string.IsNullOrEmpty(seriesId) || !hasWins || t1Wins < 0 || t2Wins < 0) return;
                int n = t1Wins + t2Wins;
                int had;
                if (recorded.TryGetValue(seriesId, out had))
                {
                    if (n > had) recorded[seriesId] = n;
                    return;
                }
                if (recorded.Count >= MaxSeries) recorded.Clear();
                recorded[seriesId] = n;
            }

            /// <summary>A game starts in a cr_ff room: freeze the number its posts
            /// carry. Returns it, 0 = its posts go without the pair; `log` is
            /// the line to write.</summary>
            internal int OnGameStart(string seriesId, string room, out string log)
            {
                seriesId = seriesId ?? "";
                room = room ?? "";
                string sid8 = seriesId.Length > 8 ? seriesId.Substring(0, 8) : seriesId;
                if (seriesId.Length == 0 || room.Length == 0)
                {
                    Freeze("", "", 0);
                    log = LogTag + " game start with no " + (seriesId.Length == 0 ? "series" : "room")
                          + ": its posts go without the pair";
                    return 0;
                }
                string restarted = "";
                if (seriesId != countSeries || room != countRoom)
                {
                    if (countStarts > 0) restarted = " (the own count restarted: the series or the room changed)";
                    countSeries = seriesId;
                    countRoom = room;
                    countStarts = 0;
                }
                countStarts++;
                int had;
                bool read = recorded.TryGetValue(seriesId, out had);
                int n = read ? had + 1 : (countStarts == 1 ? 1 : 0);
                if (n > MaxGameNumber || !RoomSendable(room))
                {
                    Freeze(seriesId, room, 0);
                    log = LogTag + " series=" + sid8 + " game number " + Num(n) + " or the room is outside what the"
                          + " server accepts: its posts go without the pair" + restarted;
                    return 0;
                }
                Freeze(seriesId, room, n);
                if (read)
                {
                    log = LogTag + " series=" + sid8 + " game " + Num(n) + " (" + Num(had) + " recorded as last read;"
                          + " game start " + Num(countStarts) + " of this series in this room"
                          + (n != countStarts ? ", which differs: the server's count is the one named" : "") + ")"
                          + restarted;
                }
                else if (n == 1)
                {
                    log = LogTag + " series=" + sid8 + " game 1 (the series' first game start in this room, no read"
                          + " of its recorded games yet)" + restarted;
                }
                else
                {
                    log = LogTag + " series=" + sid8 + " no game number (game start " + Num(countStarts)
                          + " in this room and no read of the series' recorded games): its posts go without the pair"
                          + restarted;
                }
                return n;
            }

            private void Freeze(string seriesId, string room, int n)
            {
                gameSeries = seriesId;
                gameRoom = room;
                gameNumber = n;
            }

            /// <summary>The number a post sent now carries: the frozen one while
            /// the series and the room are the ones it was frozen for, else 0.</summary>
            internal int For(string seriesId, string room)
            {
                if (gameNumber <= 0) return 0;
                if (!string.Equals(seriesId ?? "", gameSeries, StringComparison.Ordinal)) return 0;
                if (!string.Equals(room ?? "", gameRoom, StringComparison.Ordinal)) return 0;
                return gameNumber;
            }

            /// <summary>Whether a read has shown the frozen game recorded: the
            /// after-game refresh has what the next game start needs.</summary>
            internal bool ReadShowsGameRecorded(string seriesId)
            {
                int had;
                return gameNumber > 0
                       && string.Equals(seriesId ?? "", gameSeries, StringComparison.Ordinal)
                       && recorded.TryGetValue(gameSeries, out had) && had >= gameNumber;
            }

            /// <summary>The room was left: nothing frozen, the own count restarts.
            /// Reads are kept (the count they show belongs to the series, not the
            /// room, and a resumed sitting needs it).</summary>
            internal void Clear()
            {
                Freeze("", "", 0);
                countSeries = "";
                countRoom = "";
                countStarts = 0;
            }

            internal void NoteAttestationRefused(string seriesId)
            {
                if (string.IsNullOrEmpty(seriesId)) return;
                if (refused.Count >= MaxSeries) refused.Clear();
                refused.Add(seriesId);
            }

            internal bool AttestationRefused(string seriesId)
            {
                return !string.IsNullOrEmpty(seriesId) && refused.Contains(seriesId);
            }
        }

        // ---- The sentinel ----------------------------------------------------
        //
        // A model of one series, three real games, and the server's filing
        // rule, run under four numbering rules: the Tracker above, and three
        // kept copies of rules this round did not build. The invariant: an
        // attested post the server files is filed under the game the server
        // was in when the post's own game started, in that game's sitting
        // (never under a later game: finding 1's false positive). The
        // liveness check: when every game is recorded before the next one
        // starts, every after-game read sees it and no game start fires twice,
        // every post a game sends at its start is filed.

        private abstract class Rule
        {
            internal abstract void Read(string series, int recordedGames);
            internal abstract void Start(string series, string room);
            internal abstract void Leave();
            internal abstract int Name(string series, string room);
        }

        private sealed class TrackerRule : Rule
        {
            private readonly Tracker t = new Tracker();
            internal override void Read(string series, int recordedGames) { t.ObserveRead(series, true, recordedGames, 0); }
            internal override void Start(string series, string room) { string line; t.OnGameStart(series, room, out line); }
            internal override void Leave() { t.Clear(); }
            internal override int Name(string series, string room) { return t.For(series, room); }
        }

        // Kept copy: a free-running count of game starts, restarted when the
        // room changes: FFA's shape without its correction from the server.
        private sealed class OwnCountRule : Rule
        {
            private string room = "";
            private int starts;
            internal override void Read(string series, int recordedGames) { }
            internal override void Start(string series, string r) { if (r != room) { room = r; starts = 0; } starts++; }
            internal override void Leave() { room = ""; starts = 0; }
            internal override int Name(string series, string r) { return r == room ? starts : 0; }
        }

        // Kept copy: the server's count read when a post is SENT, not frozen at
        // its game's start.
        private sealed class SendTimeRule : Rule
        {
            private string room = "";
            private int last = -1;
            internal override void Read(string series, int recordedGames) { if (recordedGames > last) last = recordedGames; }
            internal override void Start(string series, string r) { room = r; }
            internal override void Leave() { room = ""; }
            internal override int Name(string series, string r) { return (r == room && last >= 0) ? last + 1 : 0; }
        }

        // Kept copy: never name a game (every post goes without the pair).
        private sealed class NeverRule : Rule
        {
            internal override void Read(string series, int recordedGames) { }
            internal override void Start(string series, string r) { }
            internal override void Leave() { }
            internal override int Name(string series, string r) { return 0; }
        }

        private sealed class Tally
        {
            public int Timelines, Posts, Filed, Wrong, CleanFirst, CleanFirstFiled;
        }

        private struct SentPost
        {
            public int Named;
            public string Room;
            public int GameAtStart;       // the server's game when this post's own game started
            public string SittingAtStart; // and the room it had stored then
            public bool First;            // sent at its game's start, processed at once
        }

        private const int RecBefore = 0, RecLate = 1, RecNever = 2;

        private sealed class Sim
        {
            public int Recorded;          // the server's recorded games
            public string Stored;         // the server's sitting room
            public bool Clean;
            public Tally Tally;

            public void Process(SentPost p)
            {
                Tally.Posts++;
                // _record_team_game_points: filed only under exactly the game in
                // progress, in the stored sitting.
                bool filed = p.Named >= 1 && p.Named == Recorded + 1 && p.Room == Stored;
                if (filed)
                {
                    Tally.Filed++;
                    if (Recorded + 1 != p.GameAtStart || Stored != p.SittingAtStart) Tally.Wrong++;
                }
                if (p.First && Clean)
                {
                    Tally.CleanFirst++;
                    if (filed) Tally.CleanFirstFiled++;
                }
            }
        }

        // One timeline. rec[k]: game k+1 is recorded before the next game
        // starts, during it (late), or never. fresh[k]: a read after game k+1's
        // end sees what the server has then. initRead: a read before game 1.
        // doubleAt: that game's start fires twice. relockAfter: after that game
        // the series moves to a new sitting in a new room. midRead: a read in
        // the middle of every game. lagRead: a read after a game's record that
        // a seat still in that game takes before its last post.
        private static void Simulate(Rule rule, int[] rec, bool[] fresh, bool initRead, int doubleAt,
                                     int relockAfter, bool midRead, bool lagRead, Tally tally)
        {
            const string S = "series-a", R1 = "room-a", R2 = "room-b";
            var sim = new Sim { Recorded = 0, Stored = R1, Tally = tally };
            sim.Clean = doubleAt == 0;
            for (int k = 0; k < 3; k++) sim.Clean &= rec[k] == RecBefore && fresh[k];
            tally.Timelines++;
            string room = R1;
            var carried = new List<SentPost>();
            if (initRead) rule.Read(S, sim.Recorded);
            for (int k = 0; k < 3; k++)
            {
                rule.Start(S, room);
                if (doubleAt == k + 1) rule.Start(S, room);
                int gameAtStart = sim.Recorded + 1;
                string sittingAtStart = sim.Stored;
                // The first post of the game, processed at once.
                sim.Process(new SentPost { Named = rule.Name(S, room), Room = room, GameAtStart = gameAtStart,
                                           SittingAtStart = sittingAtStart, First = true });
                // The previous game's posts still in flight.
                foreach (var p in carried) sim.Process(p);
                carried.Clear();
                // The previous game's record, landing late.
                if (k > 0 && rec[k - 1] == RecLate) sim.Recorded++;
                if (midRead) rule.Read(S, sim.Recorded);
                sim.Process(new SentPost { Named = rule.Name(S, room), Room = room, GameAtStart = gameAtStart,
                                           SittingAtStart = sittingAtStart });
                var afterItsRecord = new SentPost { Named = rule.Name(S, room), Room = room, GameAtStart = gameAtStart,
                                                    SittingAtStart = sittingAtStart };
                var intoNextGame = new SentPost { Named = rule.Name(S, room), Room = room, GameAtStart = gameAtStart,
                                                  SittingAtStart = sittingAtStart };
                // Game over, and its report.
                if (rec[k] == RecBefore) sim.Recorded++;
                sim.Process(afterItsRecord);
                // A seat whose own game over has not fired yet reads, then posts.
                if (lagRead) rule.Read(S, sim.Recorded);
                var lagging = new SentPost { Named = rule.Name(S, room), Room = room, GameAtStart = gameAtStart,
                                             SittingAtStart = sittingAtStart };
                carried.Add(intoNextGame);
                carried.Add(lagging);
                if (fresh[k]) rule.Read(S, sim.Recorded);
                if (relockAfter == k + 1)
                {
                    sim.Stored = R2;
                    room = R2;
                    rule.Leave();
                }
            }
            if (rec[2] == RecLate) sim.Recorded++;
            foreach (var p in carried) sim.Process(p);
        }

        private static Tally Sweep(Func<Rule> make)
        {
            var tally = new Tally();
            var rec = new int[3];
            var fresh = new bool[3];
            for (int r = 0; r < 27; r++)
            for (int f = 0; f < 8; f++)
            for (int init = 0; init < 2; init++)
            for (int dbl = 0; dbl < 4; dbl++)
            for (int relock = 0; relock < 3; relock++)
            for (int mid = 0; mid < 2; mid++)
            for (int lag = 0; lag < 2; lag++)
            {
                int rr = r;
                for (int k = 0; k < 3; k++) { rec[k] = rr % 3; rr /= 3; fresh[k] = ((f >> k) & 1) != 0; }
                Simulate(make(), rec, fresh, init != 0, dbl, relock, mid != 0, lag != 0, tally);
            }
            return tally;
        }

        /// <summary>Returns the log line; `pass` is its verdict.</summary>
        internal static string RunSentinel(out bool pass)
        {
            pass = true;
            int checks = 0;
            string detail = "";

            // The sweep: the Tracker files nothing under another game and loses
            // nothing in a clean series; each kept copy fails where it should,
            // or the sweep could not tell them apart.
            Tally cur = Sweep(() => new TrackerRule());
            Tally own = Sweep(() => new OwnCountRule());
            Tally send = Sweep(() => new SendTimeRule());
            Tally never = Sweep(() => new NeverRule());
            checks++;
            if (cur.Wrong != 0) { pass = false; detail += " tracker:" + cur.Wrong + "-filed-under-another-game"; }
            checks++;
            if (cur.CleanFirst == 0 || cur.CleanFirstFiled != cur.CleanFirst)
            { pass = false; detail += " tracker:clean-first-posts-filed=" + cur.CleanFirstFiled + "/" + cur.CleanFirst; }
            checks++;
            if (own.Wrong == 0) { pass = false; detail += " own-count:none-filed-under-another-game(the-sweep-proves-nothing)"; }
            checks++;
            if (send.Wrong == 0) { pass = false; detail += " send-time:none-filed-under-another-game(the-sweep-proves-nothing)"; }
            checks++;
            if (never.CleanFirstFiled == never.CleanFirst) { pass = false; detail += " never:liveness-check-proves-nothing"; }

            // Direct checks on one Tracker.
            var t = new Tracker();
            string line;
            checks++;
            if (t.OnGameStart("S", "R", out line) != 1 || t.For("S", "R") != 1) { pass = false; detail += " first-start-no-read"; }
            checks++;
            if (t.For("S2", "R") != 0 || t.For("S", "R2") != 0 || t.For(null, null) != 0) { pass = false; detail += " for:mismatch"; }
            checks++;
            if (t.OnGameStart("S", "R", out line) != 0 || t.For("S", "R") != 0) { pass = false; detail += " second-start-no-read"; }
            t.ObserveRead("S", true, 1, 0);
            checks++;
            if (t.OnGameStart("S", "R", out line) != 2) { pass = false; detail += " read:1-recorded"; }
            checks++;
            if (t.ReadShowsGameRecorded("S")) { pass = false; detail += " recorded:too-early"; }
            t.ObserveRead("S", true, 0, 0);
            checks++;
            if (t.OnGameStart("S", "R", out line) != 2) { pass = false; detail += " read:a-lower-late-answer-lowered-it"; }
            t.ObserveRead("S", false, 5, 5);
            checks++;
            if (t.OnGameStart("S", "R", out line) != 2) { pass = false; detail += " read:an-answer-without-wins-counted"; }
            t.ObserveRead("S", true, 1, 1);
            checks++;
            if (!t.ReadShowsGameRecorded("S") || t.ReadShowsGameRecorded("S2")) { pass = false; detail += " recorded:after"; }
            t.Clear();
            checks++;
            if (t.For("S", "R") != 0) { pass = false; detail += " clear"; }
            checks++;
            if (t.OnGameStart("S", "R", out line) != 3) { pass = false; detail += " clear:reads-kept"; }
            t.ObserveRead("S", true, 99, 0);
            checks++;
            if (t.OnGameStart("S", "R", out line) != 0) { pass = false; detail += " bound:game-100"; }
            var tr = new Tracker();
            tr.ObserveRead("S", true, 0, 0);
            checks++;
            if (tr.OnGameStart("S", new string('r', MaxRoomLength + 1), out line) != 0
                || tr.OnGameStart("S", " r", out line) != 0
                || tr.OnGameStart("S", new string('r', MaxRoomLength), out line) != 1)
            { pass = false; detail += " bound:room"; }
            checks++;
            if (tr.OnGameStart("", "R", out line) != 0 || tr.OnGameStart("S", "", out line) != 0) { pass = false; detail += " empty"; }
            tr.NoteAttestationRefused("S");
            checks++;
            if (!tr.AttestationRefused("S") || tr.AttestationRefused("S2") || tr.AttestationRefused(null)) { pass = false; detail += " refused"; }

            // The wire: bounds, both canonicals, the query pair, the pin.
            checks++;
            if (Sendable(0, "r") || Sendable(MaxGameNumber + 1, "r") || Sendable(1, "") || Sendable(1, null)
                || !Sendable(1, "r") || !Sendable(MaxGameNumber, "r"))
            { pass = false; detail += " sendable"; }
            checks++;
            if (LegacyCanonical("S", "P", 1, 2) != "team-live-points:S:P:1:2") { pass = false; detail += " legacy-canonical"; }
            checks++;
            if (AttestedCanonical("S", "P", 1, 2, 3, "room_x") != "team-live-points-game:S:P:1:2:3:room_x")
            { pass = false; detail += " attested-canonical"; }
            checks++;
            if (QueryPair(3, "room_x") != "&game_number=3&photon_room_id=room_x") { pass = false; detail += " query-pair"; }
            checks++;
            if (AttestedCanonical(PinSeries, PinReporter, 2, 1, 3, PinRoom) != PinExpected) { pass = false; detail += " pin"; }

            string sweep = " (sweep: " + cur.Timelines + " timelines per rule; tracker: " + cur.Posts + " posts, "
                + cur.Filed + " filed, " + cur.Wrong + " under another game, " + cur.CleanFirstFiled + " of "
                + cur.CleanFirst + " clean first posts filed; own count: " + own.Wrong + " under another game; "
                + "send-time read: " + send.Wrong + "; never naming: " + never.CleanFirstFiled + " of "
                + never.CleanFirst + " clean first posts filed)";
            return SentinelTag + " " + (pass ? "PASS" : "FAIL") + ": " + checks + " checks" + sweep + detail;
        }
    }
}
