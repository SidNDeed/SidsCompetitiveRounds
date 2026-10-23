using System;
using System.Collections.Generic;
using System.Globalization;
using System.Security.Cryptography;
using System.Text;

namespace CompetitiveRounds
{
    /// <summary>
    /// FFA mid-game readmission (design V3, P4): the client half's pure rules.
    /// Discovery and the poll belt (P4.2), the claim / bind / decline / entered
    /// client state machine and its refusal classes, the readmission token
    /// (cr_rdt) and its check at the master, kind r grants and epoch version 2
    /// entries (P4.3 step 1, P4.8), the roster-sized late tail and its digest
    /// (P4.3 steps 3 to 7), registration order (step 9), the latch release
    /// (P4.4), departure as death (P4.7) and the presence census cadence.
    /// Nothing here touches Unity, Photon or BepInEx, so
    /// tools/tests/rj-readmit-client RUNS these rules (#391).
    /// </summary>
    internal static class FfaReadmitEntryRules
    {
        private static string I(int v) { return v.ToString(CultureInfo.InvariantCulture); }

        private static bool TryInt(string s, out int v)
        {
            return int.TryParse(s, NumberStyles.Integer, CultureInfo.InvariantCulture, out v);
        }

        // ------------------------------------------------------------ epoch entries and kinds (P4.3 step 1, P4.8)

        /// <summary>One `kept` entry of an answer's epoch, as the server's
        /// _asm_epoch writes it: {slot, actor, kind, game, v, verifier}. An
        /// entry that is not version 2 (absent `v` included) is a version 1
        /// kind l entry: only its slot and actor are hashed.</summary>
        internal static FfaLateRules.EpochEntry EpochEntryOf(int slot, int actor, string kind, int game, int v, string verifier)
        {
            if (v != 2)
                return new FfaLateRules.EpochEntry(slot, actor);
            char k = string.IsNullOrEmpty(kind) ? 'l' : kind[0];
            return new FfaLateRules.EpochEntry(slot, actor, k, game < 0 ? -1 : game, 2,
                                              string.IsNullOrEmpty(verifier) ? null : verifier);
        }

        private static bool NamesKindR(IList<FfaLateRules.EpochEntry> entries, int slot, int actor)
        {
            if (entries == null) return false;
            for (int i = 0; i < entries.Count; i++)
            {
                var e = entries[i];
                if (e.Slot == slot && e.Actor == actor && e.Kind == 'r' && e.V == 2) return true;
            }
            return false;
        }

        /// <summary>A granted seat's kind on this client: 'r' when the server
        /// says r or a kind r epoch entry (the answer's own, or the record
        /// held) names this (slot, actor); in a readmission lobby also when the
        /// server says s for a slot whose grant this client already holds under
        /// another actor (a start-roster seat is rebound only by a readmission
        /// bind, so its new actor never inherits kind s, even from an answer
        /// whose epoch is late); else the server's s or l; '\0' for anything
        /// else (the entry is dropped, as today). Lowering a grant to r is the
        /// conservative direction: a kind r actor is never kept as start
        /// roster, only through its own late entry.</summary>
        internal static char GrantKind(string serverKind, int slot, int actor,
                                       IList<FfaLateRules.EpochEntry> answerEpoch, FfaLateRules.EpochRecord held,
                                       bool readmitLobby, bool slotHeldByOtherActor)
        {
            if (actor <= 0) return '\0';
            if (serverKind == "r" || NamesKindR(answerEpoch, slot, actor)
                || (held != null && NamesKindR(held.Entries, slot, actor))
                || (readmitLobby && serverKind == "s" && slotHeldByOtherActor))
                return 'r';
            if (serverKind == "s" || serverKind == "l") return serverKind[0];
            return '\0';
        }

        // ------------------------------------------------------------ the token (P4.2 identity)

        /// <summary>The pre-join property carrying the readmission number and
        /// token, "{n}:{T}". T is held in memory only and never logged.</summary>
        internal const string RdtProp = "cr_rdt";

        internal static string RdtValue(int n, string token)
        {
            return I(n) + ":" + (token ?? "");
        }

        internal static bool ParseRdt(string v, out int n, out string token)
        {
            n = 0; token = null;
            if (string.IsNullOrEmpty(v)) return false;
            int c = v.IndexOf(':');
            if (c <= 0 || c == v.Length - 1) return false;
            if (!TryInt(v.Substring(0, c), out n) || n < 1) return false;
            token = v.Substring(c + 1);
            return true;
        }

        /// <summary>Lower-case hex SHA-256 over the ASCII bytes of s: the
        /// server's hashlib.sha256(token.encode("ascii")).hexdigest().</summary>
        internal static string Sha256Hex(string s)
        {
            using (var sha = SHA256.Create())
            {
                var bytes = sha.ComputeHash(Encoding.ASCII.GetBytes(s ?? ""));
                var sb = new StringBuilder(64);
                foreach (var b in bytes) sb.Append(b.ToString("x2", CultureInfo.InvariantCulture));
                return sb.ToString();
            }
        }

        /// <summary>The master's token check: the requester's cr_rdt carries a
        /// T whose SHA-256 equals the verifier of the chained kind r entry.</summary>
        internal static bool TokenMatches(string rdt, FfaLateRules.EpochEntry kindR)
        {
            int n; string t;
            if (kindR.Kind != 'r' || string.IsNullOrEmpty(kindR.Verifier)) return false;
            if (!ParseRdt(rdt, out n, out t)) return false;
            return string.Equals(Sha256Hex(t), kindR.Verifier.ToLowerInvariant(), StringComparison.Ordinal);
        }

        internal enum LateReq { Ignore, Accept, RefuseToken }

        /// <summary>The master's late-request check (OnLateRequest, P4.3 step 1
        /// and P4.2 identity). Kind l: in the grant set, in the late list, u_id
        /// on the roster entry of its slot (today's rule). Kind r: in the grant
        /// set, the record's verified kind r entry of its slot names the
        /// requester, u_id on the roster entry of its slot, and the token
        /// check; a failed token check is RefuseToken. Anything else is
        /// ignored (today's outcome).</summary>
        internal static LateReq LateRequest(int sender, IList<FfaLateRules.GrantEntry> grants,
                                            IList<FfaLateRules.EpochEntry> lateList, FfaLateRules.EpochRecord record,
                                            int recordUpto, Func<int, bool> uidOnRosterSlot, string senderRdt)
        {
            char kind = '\0';
            int slot = -1;
            if (grants != null)
                foreach (var e in grants)
                    if (e.Actor == sender && (e.Kind == 'l' || e.Kind == 'r')) { kind = e.Kind; slot = e.Slot; }
            if (kind == '\0') return LateReq.Ignore;
            if (kind == 'l')
            {
                bool listed = false;
                if (lateList != null)
                    foreach (var e in lateList)
                        if (e.Actor == sender && e.Slot == slot) listed = true;
                if (!listed) return LateReq.Ignore;
                return uidOnRosterSlot != null && uidOnRosterSlot(slot) ? LateReq.Accept : LateReq.Ignore;
            }
            FfaLateRules.EpochEntry r;
            if (!FfaLateRules.KindREntry(record, slot, recordUpto, out r) || r.Actor != sender)
                return LateReq.Ignore;
            if (uidOnRosterSlot == null || !uidOnRosterSlot(slot)) return LateReq.Ignore;
            return TokenMatches(senderRdt, r) ? LateReq.Accept : LateReq.RefuseToken;
        }

        /// <summary>The kind r conjunct of RoomActors.IsUnauthorized (P4.2
        /// identity): an actor whose u_id names a seat that has a kind r entry
        /// is a fighter only if it is that entry's actor. Null when no kind r
        /// entry governs the slot (today's rules decide).</summary>
        internal static bool? KindRUnauthorized(int actor, int uidSlot, FfaLateRules.EpochRecord record)
        {
            if (uidSlot < 0) return null;
            FfaLateRules.EpochEntry r;
            if (!FfaLateRules.KindREntry(record, uidSlot, -1, out r)) return null;
            return r.Actor != actor;
        }

        // ------------------------------------------------------------ discovery and the belt (P4.2)

        /// <summary>Whether a discovery answer {readmissible, lobby_id, slot,
        /// n, hold_s} offers the bar. Anything else (0, absent, an error)
        /// runs today's probe.</summary>
        internal static bool DiscoveryOffers(int readmissible, string lobby, int n, int holdS)
        {
            return readmissible == 1 && !string.IsNullOrEmpty(lobby) && n >= 1 && holdS > 0;
        }

        internal enum BeltAct { Proceed, Refuse, Wait, Offer }

        /// <summary>The poll's ready_join refusal of a relaunched seat (the
        /// continued-without-you branch), narrowed, never deleted: a seat
        /// already in that room, an admissible seat, or the seat that claimed
        /// this lobby's readmission proceeds; a readmissible seat is offered
        /// the bar (neither joins nor leaves); every other seat is refused or
        /// waits exactly as today.</summary>
        internal static BeltAct Belt(bool inThatRoom, bool admissibleSeat, bool readmissibleSeat,
                                     bool claimedThisLobby, string gameInProgressRaw)
        {
            if (inThatRoom || admissibleSeat || claimedThisLobby) return BeltAct.Proceed;
            if (readmissibleSeat) return BeltAct.Offer;
            if (gameInProgressRaw == "true") return BeltAct.Refuse;
            if (gameInProgressRaw == "null") return BeltAct.Wait;
            return BeltAct.Proceed;
        }

        // ------------------------------------------------------------ the client state machine (P4.2)

        /// <summary>Explicit named states (no boolean flags).</summary>
        internal enum RdmState { None, Offered, Claiming, Claimed, Binding, Admitted, Entered, Refused, Declined, Lapsed, Abandoned }

        internal enum RefusalClass { Released, Ended, Departed, OtherQueue, Retrying, Identity, Other }

        /// <summary>Each server reason's toast class (V3 P4.5): one truthful
        /// text per reason; an unknown reason is "could not rejoin".</summary>
        internal static RefusalClass ClassOf(string reason)
        {
            switch (reason ?? "")
            {
                case "hold_lapsed": return RefusalClass.Released;
                case "lobby_closed": return RefusalClass.Ended;
                case "departed": return RefusalClass.Departed;
                case "other_mode":
                case "other_lobby": return RefusalClass.OtherQueue;
                case "uncorroborated": return RefusalClass.Retrying;
                case "actor_identity_mismatch":
                case "actor_conflict": return RefusalClass.Identity;
                default: return RefusalClass.Other;
            }
        }

        internal sealed class RdmClient
        {
            public RdmState State = RdmState.None;
            public string Lobby;
            public int Slot = -1;
            public int N;
            public float HoldUntil;     // client clock
            public string Token;        // memory only, never logged
            public string Room;
            public string Region;
            public int Game;
            public int Actor;
            public string LastReason;
        }

        /// <summary>The fields of one {"readmit": {...}} answer.</summary>
        internal sealed class RdmAnswer
        {
            public string Status;
            public string Reason;
            public int Retry;
            public string Token;
            public string Room;
            public string Region;
            public int Slot = -1;
            public int N;
            public int HoldS = -1;
            public int Game;
            public string Kind;
            public int Actor;
        }

        internal enum RdmNext
        {
            None,       // nothing to do
            JoinRoom,   // stage the pre-join properties and join (after claim)
            BindAgain,  // send bind again next census period
            ArmLate,    // admitted_late kind r: arm the late entry
            Leave,      // a refusal: toast from the reason, leave the room
            Probe,      // decline or lapse before claim: today's probe
            Done,       // entered: the token is spent
        }

        internal enum RdmOffer { Rejected, Accepted, Refreshed, Held }

        internal static RdmOffer Offer(RdmClient c, string lobby, int slot, int n, int holdS, float now)
        {
            bool sameOffer = c.Lobby == lobby && c.N == n;
            // An active claim keeps its record and token, including when a
            // discovery answer names another lobby or hold.
            if (c.State == RdmState.Claiming || c.State == RdmState.Claimed
                || c.State == RdmState.Binding || c.State == RdmState.Admitted)
                return sameOffer ? RdmOffer.Held : RdmOffer.Rejected;
            // Hold numbers are monotonic within a lobby, not across lobbies.
            if (c.State == RdmState.Entered && c.Lobby == lobby && n <= c.N)
                return RdmOffer.Rejected;
            if (c.State == RdmState.Abandoned && c.Lobby == lobby && n <= c.N)
                return RdmOffer.Rejected;
            if (c.State == RdmState.Offered && sameOffer)
            {
                c.HoldUntil = now + Math.Max(0, holdS);
                return RdmOffer.Refreshed;
            }
            c.State = RdmState.Offered;
            c.Lobby = lobby; c.Slot = slot; c.N = n;
            c.HoldUntil = now + Math.Max(0, holdS);
            c.Token = null; c.Room = null; c.Region = null; c.Game = 0; c.Actor = 0; c.LastReason = null;
            return RdmOffer.Accepted;
        }

        /// <summary>The bar's countdown, whole seconds, never negative.</summary>
        internal static int SecondsLeft(RdmClient c, float now)
        {
            return Math.Max(0, (int)Math.Ceiling(c.HoldUntil - now));
        }

        /// <summary>End only the active attempt of the released lobby or
        /// departed claimed room. Keep its lobby/hold terminal suppression;
        /// abandonment is not a successful entry.</summary>
        internal static bool Abandon(RdmClient c, string identity, bool byRoom)
        {
            if (string.IsNullOrEmpty(identity) || (byRoom ? c.Room : c.Lobby) != identity) return false;
            if (c.State != RdmState.Claiming && c.State != RdmState.Claimed
                && c.State != RdmState.Binding && c.State != RdmState.Admitted) return false;
            c.State = RdmState.Abandoned;
            c.Token = null;
            return true;
        }

        /// <summary>The hold ended on the client clock before a bind: the bar
        /// goes; a held claim is given up.</summary>
        internal static RdmNext Tick(RdmClient c, float now)
        {
            bool waiting = c.State == RdmState.Offered || c.State == RdmState.Claiming
                           || c.State == RdmState.Claimed || c.State == RdmState.Binding;
            if (!waiting || now < c.HoldUntil) return RdmNext.None;
            bool claimed = c.State != RdmState.Offered;
            c.State = RdmState.Lapsed;
            c.Token = null;
            c.LastReason = "hold_lapsed";
            return claimed ? RdmNext.Leave : RdmNext.Probe;
        }

        /// <summary>One answer of the readmit route for `step`. Every refusal
        /// moves to Refused (leave with the reason's toast) except a retried
        /// uncorroborated bind, which binds again; a refused claim or decline
        /// leaves nothing held.</summary>
        internal static RdmNext OnAnswer(RdmClient c, string step, RdmAnswer a, float now)
        {
            if (a == null) return RdmNext.None;
            if (a.N != 0 && c.N != 0 && a.N != c.N) return RdmNext.None;   // another readmission's late answer
            if (a.HoldS >= 0 && (a.Status == "claimed" || a.Status == "refused"))
                c.HoldUntil = now + a.HoldS;
            switch (a.Status)
            {
                case "claimed":
                    if (step != "claim" || c.State != RdmState.Claiming) return RdmNext.None;
                    if (string.IsNullOrEmpty(a.Token) || string.IsNullOrEmpty(a.Room)) return Refuse(c, "not_held");
                    c.State = RdmState.Claimed;
                    c.Token = a.Token; c.Room = a.Room; c.Region = a.Region;
                    if (a.Slot >= 0) c.Slot = a.Slot;
                    return RdmNext.JoinRoom;
                case "admitted_late":
                    if (step != "bind" || (c.State != RdmState.Binding && c.State != RdmState.Claimed)) return RdmNext.None;
                    if (a.Kind != "r" || a.Game <= 0) return Refuse(c, "not_held");
                    c.State = RdmState.Admitted;
                    c.Game = a.Game; c.Actor = a.Actor;
                    return RdmNext.ArmLate;
                case "entered":
                    if (step != "entered" || c.State != RdmState.Admitted) return RdmNext.None;
                    c.State = RdmState.Entered;
                    c.Token = null;
                    return RdmNext.Done;
                case "declined":
                    c.State = RdmState.Declined;
                    c.Token = null;
                    return RdmNext.Probe;
                case "refused":
                    if (step == "bind" && a.Reason == "uncorroborated" && a.Retry == 1
                        && (c.State == RdmState.Binding || c.State == RdmState.Claimed))
                    {
                        c.State = RdmState.Binding;
                        c.LastReason = a.Reason;
                        return RdmNext.BindAgain;
                    }
                    if (step == "entered")
                    {
                        // The entry itself stands (the seat is kept in the room);
                        // the server records the refusal. Nothing to undo here.
                        c.LastReason = a.Reason;
                        return RdmNext.None;
                    }
                    if (step == "decline")
                    {
                        c.State = RdmState.Declined;
                        c.Token = null;
                        return RdmNext.Probe;
                    }
                    return Refuse(c, a.Reason);
                default:
                    return RdmNext.None;
            }
        }

        private static RdmNext Refuse(RdmClient c, string reason)
        {
            bool held = c.State == RdmState.Claimed || c.State == RdmState.Binding || c.State == RdmState.Admitted;
            c.State = RdmState.Refused;
            c.LastReason = reason;
            c.Token = null;
            return held ? RdmNext.Leave : RdmNext.Probe;
        }

        // ------------------------------------------------------------ the positive ladder (P5)

        /// <summary>V3 P5, the client rungs of the positive ladder (#438): the
        /// rung one transition of this client's machine reaches, or null. A rung
        /// is named on the transition INTO its state only, so a refreshed offer,
        /// a repeated answer or a retried bind adds no line. `entered` is the
        /// self-kept moment of a kind r seat (selfKept), not the server's
        /// answer; `held` is the server's rung.</summary>
        internal static string LadderRung(RdmState before, RdmState after, bool selfKept)
        {
            if (selfKept) return after == RdmState.Admitted || after == RdmState.Entered ? "entered" : null;
            if (after == before) return null;
            switch (after)
            {
                case RdmState.Offered: return "offered";
                case RdmState.Claimed: return before == RdmState.Claiming ? "claimed" : null;
                case RdmState.Admitted: return "bound";
                default: return null;
            }
        }

        /// <summary>The line of a rung: the rung word, then the hold's lobby
        /// (8 characters), slot and n; bound and entered add the server g and
        /// the bound actor. Never the token. Null for no rung.</summary>
        internal static string LadderLine(string rung, string lobby8, RdmClient c)
        {
            if (rung == null || c == null) return null;
            var sb = new StringBuilder(96);
            sb.Append("[FFA-RDM] ").Append(rung).Append(" lobby=").Append(string.IsNullOrEmpty(lobby8) ? "-" : lobby8)
              .Append(" slot=").Append(I(c.Slot)).Append(" n=").Append(I(c.N));
            if (rung == "bound" || rung == "entered")
                sb.Append(" game=").Append(I(c.Game)).Append(" actor=").Append(I(c.Actor));
            return sb.ToString();
        }

        /// <summary>The body of one readmit POST (V3 P4.2), {steam_id, step,
        /// n, actor, region, game, client_ms}; the token is never in it.</summary>
        internal static string RequestBody(string steamIdEscaped, string step, int n, int actor, string regionEscaped,
                                           int game, int clientMs)
        {
            var sb = new StringBuilder(160);
            sb.Append("{\"steam_id\":\"").Append(steamIdEscaped ?? "").Append("\",\"step\":\"").Append(step)
              .Append("\",\"n\":").Append(I(Math.Max(1, n)));
            if (actor > 0) sb.Append(",\"actor\":").Append(I(actor));
            if (!string.IsNullOrEmpty(regionEscaped)) sb.Append(",\"region\":\"").Append(regionEscaped).Append('"');
            if (game > 0) sb.Append(",\"game\":").Append(I(Math.Min(999, game)));
            sb.Append(",\"client_ms\":").Append(I(Math.Max(0, Math.Min(600000, clientMs)))).Append('}');
            return sb.ToString();
        }

        // ------------------------------------------------------------ the survivors' hold texts (P4)

        /// <summary>The survivors' view of the seat holds between two answers
        /// that carry `holds` [{slot, hold_s}]: a slot newly held starts the
        /// "Seat held" text; a slot no longer held that was not bound in the
        /// meantime (a bound seat shows "is back" at its keep instead) gets
        /// the "did not return" text. An answer without `holds` (null) changes
        /// nothing, so nothing is ever shown that the server did not send.</summary>
        internal static void HoldsDiff(IDictionary<int, int> prev, IDictionary<int, int> now, ICollection<int> boundSlots,
                                       List<int> started, List<int> released)
        {
            if (now == null) return;
            foreach (var kv in now)
                if (prev == null || !prev.ContainsKey(kv.Key)) started.Add(kv.Key);
            if (prev != null)
                foreach (var kv in prev)
                    if (!now.ContainsKey(kv.Key) && (boundSlots == null || !boundSlots.Contains(kv.Key))) released.Add(kv.Key);
            started.Sort();
            released.Sort();
        }

        // ------------------------------------------------------------ the presence census (P4.1 anchor, P4.2 bind)

        internal const float PresencePeriodS = 5f;   // the server's ASM_PRESENCE_PERIOD_S

        /// <summary>In a readmission lobby every granted seat in its room
        /// censuses each period for the whole sitting: the hold's anchor is the
        /// latest census listing the seat (at most one period before a drop),
        /// and bind and entered are corroborated by another seat's fresh census.
        /// Ungated and flag-false rooms keep today's cadence.</summary>
        internal static bool PresenceDue(bool readmitLobby, bool inRoom, bool granted, float now, float lastSent)
        {
            return readmitLobby && inRoom && granted && now - lastSent >= PresencePeriodS;
        }

        // ------------------------------------------------------------ the roster-sized tail and digest (P4.3 steps 3 to 7)

        internal sealed class TailSlot
        {
            public int Slot;
            public int Rounds;
            public int Points;
            public int PointsTotal;
            public int Kills;
            public List<string> Deck = new List<string>();
            public List<string> History = new List<string>();   // HistoryEntry form, in pick order
            public int DrawIndex = -1;
        }

        internal sealed class Tail
        {
            public List<TailSlot> Slots = new List<TailSlot>();
            public List<string> Ledger = new List<string>();
            public int OfferGame;
            public int OfferCycle;

            public TailSlot SlotOf(int slot)
            {
                foreach (var s in Slots) if (s.Slot == slot) return s;
                return null;
            }
        }

        /// <summary>One pick-history entry of the tail and the digest:
        /// "{round}:{rolled 0|1}:{order}:{rarity}:{name}", the name last so a
        /// name is never cut by the separator.</summary>
        internal static string HistoryEntry(int round, bool rolled, int order, string rarity, string name)
        {
            return I(round) + ":" + (rolled ? "1" : "0") + ":" + I(order) + ":" + (rarity ?? "").Replace(":", "") + ":" + (name ?? "");
        }

        internal static bool ParseHistory(string h, out int round, out bool rolled, out int order, out string rarity, out string name)
        {
            round = 0; rolled = false; order = 0; rarity = ""; name = "";
            if (string.IsNullOrEmpty(h)) return false;
            var f = h.Split(new[] { ':' }, 5);
            if (f.Length != 5 || !TryInt(f[0], out round) || !TryInt(f[2], out order)) return false;
            if (f[1] != "0" && f[1] != "1") return false;
            rolled = f[1] == "1";
            rarity = f[3];
            name = f[4];
            return name.Length > 0;
        }

        /// <summary>The late tail's array size (step 3): in a readmission lobby
        /// the roster's size, so a bodiless highest slot is never cut off;
        /// elsewhere today's highest body team + 1 (at least 2).</summary>
        internal static int TailSize(bool readmitLobby, int rosterCount, IList<int> bodyTeams)
        {
            if (readmitLobby && rosterCount > 0) return rosterCount;
            int maxTeam = 1;
            if (bodyTeams != null) foreach (int t in bodyTeams) if (t > maxTeam) maxTeam = t;
            return maxTeam + 1;
        }

        /// <summary>The slots the tail carries and every kept peer digests
        /// (step 4): in a readmission lobby every roster slot, bodied or not, so
        /// a held seat's state is covered by the peers that hold it; elsewhere
        /// the kept bodies' slots (today's LocalSlots view).</summary>
        internal static List<int> DigestSlotSet(bool readmitLobby, int rosterCount, IList<int> keptBodySlots)
        {
            var o = new List<int>();
            if (readmitLobby && rosterCount > 0)
            {
                for (int s = 0; s < rosterCount; s++) o.Add(s);
                return o;
            }
            if (keptBodySlots != null) foreach (int s in keptBodySlots) if (s >= 0 && !o.Contains(s)) o.Add(s);
            o.Sort();
            return o;
        }

        /// <summary>The reserved picks field (tail index 23) of a readmission
        /// lobby: "s:{slot}:{rounds}:{points}", "c:{slot}:{card}" per deck card
        /// in order, "h:{slot}:{round}:{rolled}:{name}" per history entry in
        /// order, "d:{slot}:{k}", "l:{name}" per ledger entry in order, and
        /// "o:{game}:{cycle}" for the latest offer record. Points total and
        /// kills ride the tail's own arrays (19, 20), roster-sized.</summary>
        internal static string[] EncodePicks(Tail t)
        {
            var o = new List<string>();
            o.Add("v:1");
            foreach (var s in t.Slots)
            {
                o.Add("s:" + I(s.Slot) + ":" + I(s.Rounds) + ":" + I(s.Points));
                foreach (var c in s.Deck) o.Add("c:" + I(s.Slot) + ":" + c);
                foreach (var h in s.History) o.Add("h:" + I(s.Slot) + ":" + h);
                o.Add("d:" + I(s.Slot) + ":" + I(s.DrawIndex));
            }
            foreach (var l in t.Ledger) o.Add("l:" + l);
            o.Add("o:" + I(t.OfferGame) + ":" + I(t.OfferCycle));
            return o.ToArray();
        }

        /// <summary>The late seat's reading of a readmission tail: the picks
        /// field plus the roster-sized points-total and kills arrays. Null when
        /// the field is not this format (fails closed: no seed, no spawn).</summary>
        internal static Tail DecodePicks(string[] picks, int[] pointsTotal, int[] kills)
        {
            if (picks == null || picks.Length == 0 || picks[0] != "v:1") return null;
            var t = new Tail();
            for (int i = 1; i < picks.Length; i++)
            {
                string p = picks[i] ?? "";
                if (p.Length < 2 || p[1] != ':') return null;
                char tag = p[0];
                string rest = p.Substring(2);
                int slot;
                switch (tag)
                {
                    case 's':
                    {
                        var f = rest.Split(':');
                        int r, pt;
                        if (f.Length != 3 || !TryInt(f[0], out slot) || !TryInt(f[1], out r) || !TryInt(f[2], out pt)) return null;
                        if (t.SlotOf(slot) != null) return null;
                        t.Slots.Add(new TailSlot
                        {
                            Slot = slot, Rounds = r, Points = pt,
                            PointsTotal = pointsTotal != null && slot >= 0 && slot < pointsTotal.Length ? pointsTotal[slot] : 0,
                            Kills = kills != null && slot >= 0 && slot < kills.Length ? kills[slot] : 0,
                        });
                        break;
                    }
                    case 'c':
                    case 'h':
                    case 'd':
                    {
                        int c = rest.IndexOf(':');
                        if (c <= 0 || !TryInt(rest.Substring(0, c), out slot)) return null;
                        var s = t.SlotOf(slot);
                        if (s == null) return null;
                        string v = rest.Substring(c + 1);
                        if (tag == 'c') s.Deck.Add(v);
                        else if (tag == 'h') s.History.Add(v);
                        else { int k; if (!TryInt(v, out k)) return null; s.DrawIndex = k; }
                        break;
                    }
                    case 'l':
                        t.Ledger.Add(rest);
                        break;
                    case 'o':
                    {
                        var f = rest.Split(':');
                        int g, cy;
                        if (f.Length != 2 || !TryInt(f[0], out g) || !TryInt(f[1], out cy)) return null;
                        t.OfferGame = g; t.OfferCycle = cy;
                        break;
                    }
                    default:
                        return null;
                }
            }
            return t;
        }

        /// <summary>The readmission boundary digest (step 4): FNV-1a 64 over
        /// g, k, the boundary's levelId and, per roster slot in slot order, its
        /// rounds, points, points total, kills, deck names, history entries and
        /// draw index, then the ledger. Every kept peer and the returner use
        /// this format exactly when the lobby's pinned flag is on.</summary>
        internal static string ReadmitDigest(int g, int k, string levelId, Tail t)
        {
            var sb = new StringBuilder();
            sb.Append("rdm1|").Append(I(g)).Append('|').Append(I(k)).Append('|').Append(levelId ?? "");
            var slots = new List<TailSlot>(t != null ? t.Slots : new List<TailSlot>());
            slots.Sort((a, b) => a.Slot.CompareTo(b.Slot));
            foreach (var s in slots)
            {
                sb.Append('|').Append(I(s.Slot)).Append(':').Append(I(s.Rounds)).Append(':').Append(I(s.Points))
                  .Append(':').Append(I(s.PointsTotal)).Append(':').Append(I(s.Kills))
                  .Append(':').Append(string.Join(",", s.Deck))
                  .Append(':').Append(string.Join(";", s.History))
                  .Append(':').Append(I(s.DrawIndex));
            }
            sb.Append("|L:").Append(string.Join(",", t != null ? t.Ledger : new List<string>()));
            return FfaLateRules.Hex16(FfaLateRules.Fnv64(sb.ToString()));
        }

        /// <summary>Step 7: the tail's game, the server's g of the readmission
        /// and the game part of cr_ffa_cyc read at the boundary must agree, or
        /// the seat fails closed.</summary>
        internal static bool GameAgrees(int tailGame, int serverGame, int cycGame)
        {
            return tailGame > 0 && tailGame == serverGame && tailGame == cycGame;
        }

        /// <summary>Step 6: the roster-sized score arrays the late seed reads,
        /// by slot, from the tail (a slot the tail lacks reads zero).</summary>
        internal static void TailArrays(Tail t, int size, out int[] rounds, out int[] points, out int[] pointsTotal, out int[] kills)
        {
            int n = Math.Max(0, size);
            if (t != null) foreach (var s in t.Slots) if (s.Slot + 1 > n) n = s.Slot + 1;
            rounds = new int[n]; points = new int[n]; pointsTotal = new int[n]; kills = new int[n];
            if (t == null) return;
            foreach (var s in t.Slots)
            {
                if (s.Slot < 0) continue;
                rounds[s.Slot] = s.Rounds; points[s.Slot] = s.Points;
                pointsTotal[s.Slot] = s.PointsTotal; kills[s.Slot] = s.Kills;
            }
        }

        /// <summary>Step 8: the slot whose logical deck a client replays onto
        /// a body at that actor's keep transition, or -1. Only a kind r v2
        /// entry inside the stamped prefix names a replay; a kind l or start
        /// seat never does (its cards came by the pick protocol).</summary>
        internal static int ReplaySlotAtKeep(FfaLateRules.EpochRecord rec, int upto, int actor, ICollection<int> replayed)
        {
            if (rec == null || rec.Entries == null || (replayed != null && replayed.Contains(actor))) return -1;
            int lim = Math.Min(upto < 0 ? rec.Entries.Count : upto, rec.Entries.Count);
            int slot = -1;
            for (int i = 0; i < lim; i++)
            {
                var e = rec.Entries[i];
                if (e.Actor == actor) slot = e.Kind == 'r' && e.V == 2 ? e.Slot : -1;
            }
            return slot;
        }

        // ------------------------------------------------------------ registration (step 9)

        /// <summary>Where a readmission room's player list takes a new player:
        /// sorted by PlayerID with no holes, inserted at its sorted position,
        /// never over a live entry. -1 refuses a duplicate PlayerID.</summary>
        internal static int RegisterIndex(IList<int> playerIds, int newId)
        {
            int at = 0;
            if (playerIds != null)
                for (int i = 0; i < playerIds.Count; i++)
                {
                    if (playerIds[i] == newId) return -1;
                    if (playerIds[i] < newId) at = i + 1;
                }
            return at;
        }

        // ------------------------------------------------------------ the latch release (P4.4)

        /// <summary>Whether a change to the grant set re-evaluates the roster
        /// latches (V3 P4.4): in a readmission lobby, so a kind r grant
        /// releases an actor latched before its u_id was readable; elsewhere
        /// today's single trigger (a roster write) stays the only one.</summary>
        internal static bool GrantChangeReleasesLatches(bool readmitLobby)
        {
            return readmitLobby;
        }

        // ------------------------------------------------------------ departure as death (P4.7)

        internal sealed class DepartureView
        {
            public bool ReadmitLobby;
            public bool GameOver;
            public bool BattleOngoing;
            public bool VictimPresent;      // the body still exists
            public bool VictimDead;
            public bool VictimQuarantined;
            public bool VictimLagOut;
            public int VictimTeam;
            public int SourceTeam = -1;     // lastSourceOfDamage's team, -1 when none or gone
            public bool SourceQuarantined;
            public string Key;              // "{actor}:{game}:{point}"
        }

        /// <summary>The team a leave mid-point credits with a kill, or -1:
        /// exactly RecordKillFor's rule (a source that exists, is not the
        /// victim's own team and is not quarantined), applied only in a
        /// readmission lobby while the battle runs, to a present, alive,
        /// unquarantined, not-lagged victim, once per (actor, point).
        /// `done` records the key so a death at the same moment credits once.</summary>
        internal static int DepartureCredit(DepartureView v, ICollection<string> done)
        {
            if (v == null || !v.ReadmitLobby || v.GameOver || !v.BattleOngoing) return -1;
            if (!v.VictimPresent || v.VictimDead || v.VictimQuarantined || v.VictimLagOut) return -1;
            if (string.IsNullOrEmpty(v.Key) || done == null || done.Contains(v.Key)) return -1;
            done.Add(v.Key);
            if (v.SourceTeam < 0 || v.SourceTeam == v.VictimTeam || v.SourceQuarantined) return -1;
            return v.SourceTeam;
        }

        // ------------------------------------------------------------ the capability (P4.6)

        /// <summary>V3 P4.6: the readmission client's caps token. The server
        /// writes readmit_v1 at lock only when every locked member carries it.</summary>
        internal const string RdmCapsToken = "ffa_rdm1";

        /// <summary>The enroll call's caps, comma-joined ("" when there is no
        /// assembly): ffa_adm1 only together with ffa_rdm1, and ffa_rdm1 never
        /// without ffa_adm1, so every admission lobby this build joins is a
        /// readmission lobby (V3:252).</summary>
        internal static string CapsList(bool asm, bool adm, string asmToken, string admToken)
        {
            if (asm && adm) return asmToken + "," + admToken + "," + RdmCapsToken;
            if (asm) return asmToken;
            return "";
        }
    }
}
