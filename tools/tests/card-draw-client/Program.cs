using System;
using System.Collections.Generic;
using System.IO;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using K = CompetitiveRounds.CardDrawEvidenceCore;
using S = CompetitiveRounds.SeatEvidenceCore;

/// <summary>Card draw evidence, client half: cases over the REAL core. Every
/// expected value below is written out by hand from the design and the
/// findings, not read back from the code under test.
///   dotnet CardDrawTests.dll                 run every case
///   dotnet CardDrawTests.dll &lt;case&gt;          run one case (exit 1 on failure)
///   dotnet CardDrawTests.dll fixtures &lt;dir&gt;  write the canonical fixtures</summary>
internal static class Program
{
    private const string KEY = "fixture-key-not-a-secret";
    private const string SEAT = "76500000000000001", OTHER = "76500000000000002";
    private const string STABLE = "ranked_fixture_123456", ATTACH = "ranked_fixture_123456_r5";
    private static readonly string DIGEST = new string('a', 64);
    private static int _fails;

    private static void Eq(string what, object got, object want)
    {
        string g = Str(got), w = Str(want);
        if (g != w) { _fails++; Console.WriteLine("  FAIL " + what + ": got " + g + " want " + w); }
    }

    private static void True(string what, bool v)
    {
        if (!v) { _fails++; Console.WriteLine("  FAIL " + what); }
    }

    private static string Str(object o)
    {
        if (o == null) return "null";
        if (o is string) return (string)o;
        if (o is bool) return (bool)o ? "true" : "false";
        if (o is int || o is long) return Convert.ToString(o, System.Globalization.CultureInfo.InvariantCulture);
        return S.Json(o);
    }

    private static string[] Canon(int n, int pad = 0)
    {
        var a = new string[n];
        for (int i = 0; i < n; i++) a[i] = "Card" + i + (pad > 0 ? new string('x', pad) : "");
        return a;
    }

    private static int[] Rar(int n)
    {
        var a = new int[n];
        for (int i = 0; i < n; i++) a[i] = i % 3;
        return a;
    }

    private static K.CardGame NewGame(int poolN = 10, IList<int>[] held = null, IList<int> po = null, int g = 1, int pad = 0)
    {
        return new K.CardGame(g, 5, 1, poolN, DIGEST, Canon(poolN, pad), Rar(poolN), po ?? new List<int> { 0, 1 },
                              held ?? new IList<int>[] { new List<int>(), new List<int>() });
    }

    private static readonly K.DealFacts F0 = new K.DealFacts(0, 0, -1);

    private static void Spawns(K.CardGame g, int[] ixs, int creator, int[] shared, K.DealFacts f)
    {
        for (int i = 0; i < ixs.Length; i++) g.Spawn(ixs[i], creator, f, shared != null ? shared[i] : 0);
    }

    private static List<long> L(params long[] a) { return new List<long>(a); }

    private static string Field(S.JObj rec, string key) { return S.Json(rec.Get(key)); }

    private static string Rec(K.CardGame g, string end = null)
    {
        return S.Json(g.Record(end, new string('b', 64), "ok", 0, 0, null));
    }

    // -- cases ------------------------------------------------------------------------------------

    private static void Census()
    {
        var cards = new List<K.CensusCard>
        {
            new K.CensusCard { Name = "Alpha", Rarity = 0, AllowMultiple = true, Categories = new[] { "x", null }, Blacklisted = new string[0], Lock = false },
            new K.CensusCard { Name = "Beta\"q", Rarity = 2, AllowMultiple = false, Categories = null, Blacklisted = new[] { "y" }, Lock = true },
            new K.CensusCard { Name = "Gaé", Rarity = 5, AllowMultiple = true, Categories = new string[0], Blacklisted = new string[0], Lock = false },
        };
        string text = K.CensusText(cards);
        Eq("census text", text,
           "{\"census\":1,\"cards\":[[\"Alpha\",0,1,[\"x\",null],[],0],[\"Beta\\\"q\",2,0,null,[\"y\"],1],[\"Ga\\u00e9\",5,1,[],[],0]]}");
        string d = K.CensusDigest(text);
        string want = Convert.ToHexString(SHA256.HashData(Encoding.ASCII.GetBytes(text))).ToLowerInvariant();
        Eq("digest is the full sha256", d, want);
        Eq("digest length", d.Length, 64);
        // M4: arrays preserved, null distinct from "-", null array distinct from empty, order matters
        Func<string[], string> one = cats => K.CensusDigest(K.CensusText(new List<K.CensusCard> { new K.CensusCard { Name = "n", Categories = cats } }));
        True("[a,b] differs from [\"a,b\"]", one(new[] { "a", "b" }) != one(new[] { "a,b" }));
        True("null category differs from \"-\"", one(new string[] { null }) != one(new[] { "-" }));
        True("null array differs from empty", one(null) != one(new string[0]));
        True("order matters", one(new[] { "a", "b" }) != one(new[] { "b", "a" }));
        var swapped = new List<K.CensusCard> { cards[1], cards[0], cards[2] };
        True("pool order matters", K.CensusDigest(K.CensusText(swapped)) != d);
        // the duplicate-name check of the dump
        True("two objects, one name: collision", K.CategoryNameCollision(new List<KeyValuePair<int, string>>
            { new KeyValuePair<int, string>(1, "Gun"), new KeyValuePair<int, string>(2, "Gun") }));
        True("one object twice: no collision", !K.CategoryNameCollision(new List<KeyValuePair<int, string>>
            { new KeyValuePair<int, string>(1, "Gun"), new KeyValuePair<int, string>(1, "Gun"), new KeyValuePair<int, string>(3, "Block") }));
    }

    private static void Opening()
    {
        var g = NewGame();
        g.OpenPhase(0, 1, 0, 0, 0);
        Spawns(g, new[] { 3, 1, 4, 7, 5 }, 1, new[] { 0, 1, 2, 3, 4 }, new K.DealFacts(0, 0, 1));
        g.Apply(0, 4, 0, 1003, 0);
        g.EndPick(L(3, 1, 4, 7, 5), 2, 1003, 2, 0, 1, F0, 5);
        g.DonePicking(5);
        g.OpenPhase(1, 1, 0, 0, 5);
        Spawns(g, new[] { 2, 8, 0, 9, 6 }, 1, new[] { 5, 5, 5, 5, 5 }, new K.DealFacts(0, 0, 4));
        g.Apply(1, 9, 0, 2004, 0);
        g.EndPick(L(2, 8, 0, 9, 6), 3, 2004, 3, 1, 1, F0, 5);
        g.DonePicking(5);
        var rec = g.Record(null, new string('b', 64), "ok", 1, 1, null);
        Eq("hd", rec.Get("hd"), "[[0,0,0,0,0,5,[3,1,4,7,5],5,[],2,2,1,31,1,1003,0,1,0],[1,0,1,1,0,5,[2,8,0,9,6],5,[],3,3,1,-1,-1,2004,0,-1,0]]");
        Eq("ph", rec.Get("ph"), "[[0,0,1,0,0,1,1],[1,1,1,0,0,1,1]]");
        Eq("ap", rec.Get("ap"), "[[0,4,0,1003],[1,9,0,2004]]");
        Eq("apx", rec.Get("apx"), "[0,0]");
        Eq("tot", rec.Get("tot"), "[[1,1,5,1,1,0,0],[1,1,5,1,1,0,0]]");
        Eq("cards", rec.Get("cards"), "[[0,\"Card0\",0],[1,\"Card1\",1],[2,\"Card2\",2],[3,\"Card3\",0],[4,\"Card4\",1],[5,\"Card5\",2],[6,\"Card6\",0],[7,\"Card7\",1],[8,\"Card8\",2],[9,\"Card9\",0]]");
        Eq("pool", rec.Get("pool"), "[10,\"" + DIGEST + "\",\"ok\"]");
        Eq("prof", rec.Get("prof"), "[\"" + new string('b', 64) + "\",\"ok\",\"\",\"no_location\",\"\",\"\",\"\",\"cd-sem:2\",\"\"]");
        Eq("sc", rec.Get("sc"), "[1,1]");
        Eq("inc", rec.Get("inc"), 0L);
        Eq("held0", rec.Get("held0"), "[[],[]]");
        Eq("omit", rec.Get("omit"), "{\"cards\":0,\"held0\":[0,0],\"ph\":0,\"hd\":0,\"ap\":0,\"sl\":0,\"sp\":0}");
        Eq("keys", string.Join(",", rec.Keys), string.Join(",", K.RECORD_KEYS));
        Eq("keys spelled out", string.Join(",", K.RECORD_KEYS), "schema,g,ns,pool,prof,po,sc,inc,cards,held0,ph,hd,ap,apx,tot,cost,omit");
        var noSha = g.Record(null, "abc", "ok", 0, 0, null);
        Eq("prof refuses a short sha", noSha.Get("prof"), "[\"\",\"no_location\",\"\",\"no_location\",\"\",\"\",\"\",\"cd-sem:2\",\"\"]");
    }

    private static void NoPick()
    {
        var g = NewGame();
        g.OpenPhase(0, 1, 0, 0, 0);
        Spawns(g, new[] { 2, 3 }, 1, new[] { 0, 0 }, F0);
        g.DonePicking(0);
        g.OpenPhase(1, 1, 0, 0, 0);
        Spawns(g, new[] { 5 }, 1, new[] { 0 }, F0);
        g.OpenPhase(0, 1, 1, 0, 0);
        Spawns(g, new[] { 6 }, 1, new[] { 0 }, F0);
        g.Close(0);
        var rec = g.Record(null, "", "no_location", 0, 0, null);
        Eq("hd", rec.Get("hd"), "[[0,0,0,-1,0,2,[2,3],2,[],-2,-1,-1,0,-1,-1,0,0,0],[1,0,1,-1,0,1,[5],1,[],-2,-1,-1,-1,-1,-1,0,-1,0],[2,0,0,-1,0,1,[6],1,[],-2,-1,-1,0,-1,-1,0,0,0]]");
        Eq("ph", rec.Get("ph"), "[[0,0,1,0,0,1,1],[1,1,1,0,0,1,0],[2,0,1,1,0,1,0]]");
        Eq("tot picks 0", rec.Get("tot"), "[[2,2,3,0,0,0,0],[1,1,1,0,0,0,0]]");
        g.Spawn(7, 1, F0, 0);
        Eq("no spawn recorded after the game closed", g.Hd.Count, 3);
    }

    private static void EndPickOnly()
    {
        var g = NewGame();
        g.OpenPhase(1, 1, 0, 0, 0);
        g.EndPick(L(4, 5, 6, 7, 8), 0, 900, 0, 1, 1, new K.DealFacts(1, 2, -1), 0);
        Eq("hd", g.Hd[0], "[0,0,1,1,0,5,[4,5,6,7,8],0,[],0,0,1,-1,-1,900,1,-1,2]");
        Eq("tot", g.Tot[1], "[1,1,0,1,0,0,0]");
    }

    private static void SpawnOrder()
    {
        var g = NewGame();
        g.OpenPhase(1, 1, 0, 0, 0);
        Spawns(g, new[] { 4, 5, 6 }, 1, null, F0);
        g.EndPick(L(5, 4, 6), 1, 77, 1, 1, 1, F0, 0);
        Eq("hd", g.Hd[0], "[0,0,1,1,0,3,[5,4,6],3,[4,5,6],1,1,1,-1,-1,77,0,-1,0]");
        Eq("tot spawn-order differences", g.Tot[1][6], 1);
        g.OpenPhase(0, 1, 0, 0, 0);
        Spawns(g, new[] { 1, 2 }, 1, null, F0);
        g.EndPick(L(1, 3), 0, 78, 0, 0, 1, F0, 0);
        // a card only spawned (2) and a card only in the end-pick (3) are both named
        Eq("cards from sl and sp", Field(g.Record(null, "", "", 0, 0, null), "cards"),
           "[[1,\"Card1\",1],[2,\"Card2\",2],[3,\"Card3\",0],[4,\"Card4\",1],[5,\"Card5\",2],[6,\"Card6\",0]]");
    }

    private static void Foreign()
    {
        var g = NewGame();
        g.OpenPhase(1, 1, 0, 0, 0);
        g.Spawn(4, 1, F0, 0); g.Spawn(9, 0, F0, 0); g.Spawn(5, 1, F0, 0);
        g.EndPick(L(4, 5), 0, 11, 0, 1, 1, F0, 0);
        Eq("foreign spawn: not in sp_n, ds 0", g.Hd[0], "[0,0,1,1,0,2,[4,5],2,[],0,0,0,-1,-1,11,0,-1,0]");
    }

    private static void Sender()
    {
        var g = NewGame();
        g.OpenPhase(1, 1, 0, 0, 0);
        g.Spawn(4, 1, F0, 0);
        g.EndPick(L(4), 0, 1, 0, 1, 0, F0, 0);
        g.OpenPhase(1, 1, 0, 0, 0);
        g.Spawn(4, 1, F0, 0);
        g.EndPick(L(4), 0, 1, 0, 1, -1, F0, 0);
        g.OpenPhase(1, 1, 0, 0, 0);
        g.Spawn(4, -1, F0, 0);
        g.EndPick(L(4), 0, 1, 0, 1, 1, F0, 0);
        g.OpenPhase(1, 1, 0, 0, 0);
        g.Spawn(4, -1, F0, 0);
        g.EndPick(L(4), 0, 1, 0, 1, 0, F0, 0);
        Eq("ds: sender not the picker", ((List<object>)g.Hd[0])[11], 0L);
        Eq("ds: sender unknown", ((List<object>)g.Hd[1])[11], -1L);
        Eq("ds: creator unknown", ((List<object>)g.Hd[2])[11], -1L);
        Eq("ds: a known mismatch wins over unknown", ((List<object>)g.Hd[3])[11], 0L);
        Eq("wp from pickId", ((List<object>)g.Hd[0])[3], 1L);
    }

    private static void Unresolved()
    {
        var g = NewGame();
        g.OpenPhase(0, 1, 0, 0, 0);
        g.Spawn(-1, 1, F0, 0); g.Spawn(3, 1, F0, 0);
        g.EndPick(L(12, 3), 1, 5, 1, 0, 1, F0, 0);
        // L2: a spawn with no local source card is still a spawn; an index outside the pool is -1
        Eq("hd", g.Hd[0], "[0,0,0,0,0,2,[-1,3],2,[],1,1,1,0,-1,5,0,0,0]");
        Eq("tot unresolved", g.Tot[0][5], 1);
    }

    private static void Held()
    {
        var g = NewGame(10, new IList<int>[] { new List<int> { 1, 2 }, new List<int> { 3 } });
        g.Apply(0, 5, 0, 300, 0);
        g.OpenPhase(0, 1, 0, 0, 0);
        Spawns(g, new[] { 6, 7 }, 1, new[] { 0, 0 }, new K.DealFacts(1, 3, -1));
        g.Apply(0, 6, 0, 400, 0);
        g.EndPick(L(6, 7), 0, 400, 0, 0, 1, F0, 0);
        // M1 gl, M3 an and hn: an counts the applications before the first spawn only
        Eq("hd", g.Hd[0], "[0,0,0,0,1,2,[6,7],2,[],0,0,1,0,-1,400,1,0,3]");
        Eq("held0", Field(g.Record(null, "", "", 0, 0, null), "held0"), "[[1,2],[3]]");
        var unread = NewGame(10, new IList<int>[] { null, new List<int> { 3 } });
        Eq("unread held list is null", Field(unread.Record(null, "", "", 0, 0, null), "held0"), "[null,[3]]");
        var many = new List<int>();
        for (int i = 0; i < 65; i++) many.Add(i % 10);
        var big = NewGame(10, new IList<int>[] { many, new List<int>() });
        var rec = big.Record(null, "", "", 0, 0, null);
        Eq("held0 capped at 64", ((List<long>)((List<object>)rec.Get("held0"))[0]).Count, 64);
        Eq("held0 cap counted", Field(rec, "omit"), "{\"cards\":0,\"held0\":[1,0],\"ph\":0,\"hd\":0,\"ap\":0,\"sl\":0,\"sp\":0}");
    }

    private static void SrcGen()
    {
        Eq("all served", K.SrcMask(new[] { 0, 1, 2, 3, 4 }, 5), 31L);
        Eq("slots 0, 2, 4 served", K.SrcMask(new[] { 0, 1, 1, 2, 2 }, 3), 21L);
        Eq("none served", K.SrcMask(new[] { 0, 0 }, 0), 0L);
        Eq("missing reading", K.SrcMask(new[] { 0, -1 }, 1), -1L);
        Eq("counter jumped", K.SrcMask(new[] { 0, 2 }, 2), -1L);
        Eq("too many slots", K.SrcMask(new int[31], 0), -1L);
        Eq("gen vanilla", K.Gen(0, -1, 1), 0);
        Eq("gen opening", K.Gen(31, 1, 1), 1);
        Eq("gen later", K.Gen(31, 2, 1), 2);
        Eq("gen unknown index", K.Gen(5, 0, 1), -1);
        Eq("gen unknown src", K.Gen(-1, 3, 1), -1);
        var g = NewGame();
        g.OpenPhase(0, 1, 2, 0, 3);
        Spawns(g, new[] { 1, 2, 3, 4, 5 }, 1, new[] { 3, 4, 5, 6, 7 }, new K.DealFacts(0, 4, 2));
        g.EndPick(L(1, 2, 3, 4, 5), 0, 10, 0, 0, 1, F0, 8);
        Eq("own later draw", g.Hd[0], "[0,0,0,0,0,5,[1,2,3,4,5],5,[],0,0,1,31,2,10,0,2,4]");
        g.OpenPhase(1, 1, 2, 1, 8);
        Spawns(g, new[] { 1, 2 }, 1, new[] { 8, 9 }, new K.DealFacts(0, 4, 5));
        g.EndPick(L(1, 2), 0, 11, 0, 1, 1, F0, 10);
        Eq("other seat's hand: src, sq, gen unknown", g.Hd[1], "[1,0,1,1,0,2,[1,2],2,[],0,0,1,-1,-1,11,0,-1,4]");
    }

    private static void Po()
    {
        Eq("po", Field(NewGame(10, null, new List<int> { 1, 0 }).Record(null, "", "", 0, 0, null), "po"), "[1,0]");
        Eq("po capped", Field(NewGame(10, null, new List<int> { 0, 1, 0, 1, 0, 1, 0, 1, 0 }).Record(null, "", "", 0, 0, null), "po"), "[0,1,0,1,0,1,0,1]");
    }

    private static void Caps()
    {
        var g = NewGame(20);
        g.OpenPhase(1, 1, 0, 0, 0);
        var ix = new int[17];
        for (int i = 0; i < 16; i++) ix[i] = i;
        ix[16] = 0;    // the M3 failing input: slot 16 repeats slot 0
        Spawns(g, ix, 1, null, F0);
        var sl = new List<long>(); foreach (var v in ix) sl.Add(v);
        g.EndPick(sl, 0, 1, 0, 1, 1, F0, 0);
        var h = (List<object>)g.Hd[0];
        Eq("n keeps the true slot count", h[5], 17L);
        Eq("sl capped at 16", ((List<long>)h[6]).Count, 16);
        Eq("sp_n keeps the true spawn count", h[7], 17L);
        var rec = g.Record(null, "", "", 0, 0, null);
        Eq("omit sl", Field(rec, "omit"), "{\"cards\":0,\"held0\":[0,0],\"ph\":0,\"hd\":0,\"ap\":0,\"sl\":1,\"sp\":0}");
        var g2 = NewGame();
        for (int p = 0; p < 41; p++)
        {
            g2.OpenPhase(0, 1, 0, 0, 0);
            g2.EndPick(L(1, 2), 0, p, 0, 0, 1, F0, 0);
            g2.DonePicking(0);
        }
        for (int a = 0; a < 65; a++) g2.Apply(0, 1, 0, a, 0);
        var r2 = g2.Record(null, "", "", 0, 0, null);
        Eq("ph capped", ((List<object>)r2.Get("ph")).Count, 40);
        Eq("hd capped", ((List<object>)r2.Get("hd")).Count, 40);
        Eq("ap capped", ((List<object>)r2.Get("ap")).Count, 64);
        Eq("caps counted", Field(r2, "omit"), "{\"cards\":0,\"held0\":[0,0],\"ph\":1,\"hd\":1,\"ap\":1,\"sl\":0,\"sp\":0}");
        Eq("tot whole game", Field(r2, "tot"), "[[41,41,0,41,65,0,0],[0,0,0,0,0,0,0]]");
        var g3 = NewGame(2, null, null, 1, 70);
        g3.Apply(0, 1, 0, 1, 0);
        Eq("card name capped at 64", Field(g3.Record(null, "", "", 0, 0, null), "cards"), "[[1,\"Card1" + new string('x', 59) + "\",1]]");
    }

    private static void Apps()
    {
        var g = NewGame();
        // CD-M1: only an application whose original ran and completed is one
        g.Apply(-1, 3, 1, 0, K.APPLY_SKIPPED);
        g.Apply(0, 2, 0, 50, K.APPLY_SKIPPED);
        g.Apply(0, 5, 0, 7, K.APPLY_FAULTED);
        g.Apply(1, 2, 1, -5, K.APPLY_DONE);
        g.Apply(-1, 4, 0, 9, K.APPLY_DONE);
        var rec = g.Record(null, "", "", 0, 0, null);
        Eq("ap", Field(rec, "ap"), "[[1,2,1,-1],[-1,4,0,9]]");
        Eq("apx: skipped, faulted", Field(rec, "apx"), "[2,1]");
        Eq("applications per role", g.AppsTo, new long[] { 0, 1 });
        Eq("tot applications", Field(rec, "tot"), "[[0,0,0,0,0,0,0],[0,0,0,0,1,0,0]]");
        Eq("cards named by completed applications only", Field(rec, "cards"), "[[2,\"Card2\",2],[4,\"Card4\",1]]");
    }

    /// <summary>CD-M1: after the dispatch seals the game no collector report
    /// changes it.</summary>
    private static void Seal()
    {
        var g = NewGame();
        g.OpenPhase(0, 1, 0, 0, 0);
        Spawns(g, new[] { 1, 2 }, 1, null, F0);
        g.EndPick(L(1, 2), 0, 5, 0, 0, 1, F0, 0);
        g.Apply(0, 1, 0, 5, K.APPLY_DONE);
        g.Close(0);
        g.Seal();
        string before = Rec(g);
        g.OpenPhase(1, 1, 0, 0, 0);
        g.Spawn(3, 1, F0, 0);
        g.EndPick(L(3), 0, 6, 0, 1, 1, F0, 0);
        g.DonePicking(0);
        g.Apply(1, 3, 0, 6, K.APPLY_DONE);
        g.Apply(1, 3, 0, 6, K.APPLY_SKIPPED);
        g.Close(0);
        True("sealed", g.Sealed);
        Eq("nothing after the seal changes the record", Rec(g), before);
    }

    /// <summary>CD-M3: a first phase not captured whole emits no player order
    /// and no held cards (and no held-card omissions); the other bits ride as
    /// they are.</summary>
    private static void IncFirst()
    {
        var many = new List<int>();
        for (int i = 0; i < 70; i++) many.Add(i % 10);
        var g = NewGame(10, new IList<int>[] { many, new List<int> { 3 } }, new List<int> { 0, 1 });
        g.Inc = K.INC_FIRST | K.INC_FAULT;
        var rec = g.Record(null, "", "", 0, 0, null);
        Eq("inc", rec.Get("inc"), 5L);
        Eq("po not emitted", Field(rec, "po"), "[]");
        Eq("held0 not emitted", Field(rec, "held0"), "[null,null]");
        Eq("no held omissions", Field(rec, "omit"), "{\"cards\":0,\"held0\":[0,0],\"ph\":0,\"hd\":0,\"ap\":0,\"sl\":0,\"sp\":0}");
        Eq("no cards from held", Field(rec, "cards"), "[]");
        var h = NewGame(10, new IList<int>[] { new List<int> { 1 }, null }, new List<int> { 1, 0 });
        h.Inc = K.INC_LOST | 8;
        var r2 = h.Record(null, "", "", 0, 0, null);
        Eq("only the defined bits", r2.Get("inc"), 2L);
        Eq("po kept when the first phase was whole", Field(r2, "po"), "[1,0]");
        Eq("held0 kept", Field(r2, "held0"), "[[1],null]");
    }

    /// <summary>CD-M4: the pool state rides beside the census digest.</summary>
    private static void PoolStates()
    {
        var g = NewGame();
        Eq("ok", Field(g.Record(null, "", "", 0, 0, null), "pool"), "[10,\"" + DIGEST + "\",\"ok\"]");
        g.PoolState = K.POOL_COLLISION;
        Eq("collision", Field(g.Record(null, "", "", 0, 0, null), "pool"), "[10,\"" + DIGEST + "\",\"collision\"]");
        g.PoolState = K.POOL_CHANGED;
        Eq("changed", Field(g.Record(null, "", "", 0, 0, null), "pool"), "[10,\"" + DIGEST + "\",\"changed\"]");
        g.PoolState = "other";
        Eq("an unknown state reads not_run", Field(g.Record(null, "", "", 0, 0, null), "pool"), "[10,\"" + DIGEST + "\",\"not_run\"]");
        var none = new K.CardGame(1, 5, 1, 10, "", Canon(10), Rar(10), null, null);
        Eq("no census: not_run", Field(none.Record(null, "", "", 0, 0, null), "pool"), "[10,\"\",\"not_run\"]");
        none.PoolState = K.POOL_OK;
        Eq("no digest is never ok", Field(none.Record(null, "", "", 0, 0, null), "pool"), "[10,\"\",\"not_run\"]");
    }

    /// <summary>CD-M5: the immutable identity the record carries.</summary>
    private static void Prof()
    {
        var g = NewGame();
        var p = new K.Profile { GameSha = new string('c', 64), GameState = "ok", ModSha = new string('d', 64), ModState = "ok",
                                Build = new[] { "1.41.0", "STANDALONE", "abc1234" }, Rules = "ff=1;sc=1" };
        Eq("full", Field(g.Record(null, p, 0, 0, null), "prof"),
           "[\"" + new string('c', 64) + "\",\"ok\",\"" + new string('d', 64) + "\",\"ok\",\"1.41.0\",\"STANDALONE\",\"abc1234\",\"cd-sem:2\",\"ff=1;sc=1\"]");
        p.ModSha = "short"; p.GameState = "read_failed"; p.Build = new[] { "1 41", "x", "c0mmit\"" }; p.Rules = "a\"b";
        Eq("refused parts", Field(g.Record(null, p, 0, 0, null), "prof"),
           "[\"\",\"read_failed\",\"\",\"no_location\",\"\",\"x\",\"\",\"cd-sem:2\",\"\"]");
        p.Rules = new string('r', 33);
        Eq("rules over 32 refused", ((List<object>)g.Record(null, p, 0, 0, null).Get("prof"))[8], "");
        p.Rules = new string('r', 32); p.Build = null;
        Eq("rules at 32 kept, no build", Field(g.Record(null, p, 0, 0, null), "prof"),
           "[\"\",\"read_failed\",\"\",\"no_location\",\"\",\"\",\"\",\"cd-sem:2\",\"" + new string('r', 32) + "\"]");
        Eq("semantics revision", K.SEMANTICS, "cd-sem:2");
    }

    /// <summary>CD-M2: a rule or verdict that was not read is -1 (NOT-RUN);
    /// a value outside its set reads -1 too.</summary>
    private static void ScNotRun()
    {
        var g = NewGame();
        Eq("not read", Field(g.Record(null, "", "", -1, -1, null), "sc"), "[-1,-1]");
        Eq("outside the set", Field(g.Record(null, "", "", 5, 7, null), "sc"), "[-1,-1]");
        Eq("rule on, engine fell back", Field(g.Record(null, "", "", 1, 2, null), "sc"), "[1,2]");
        Eq("rule off", Field(g.Record(null, "", "", 0, 0, null), "sc"), "[0,0]");
    }

    /// <summary>CD-L3, the record side of bar A8: a hand whose second slot
    /// repeats its first (the test-only dealer's deal) is recorded as dealt,
    /// slot by slot, and the repeated card is named once in cards.</summary>
    private static void RepeatedSlot()
    {
        var g = NewGame();
        g.OpenPhase(0, 1, 0, 0, 0);
        Spawns(g, new[] { 3, 3, 5, 7, 8 }, 1, null, F0);
        g.EndPick(L(3, 3, 5, 7, 8), 1, 41, 1, 0, 1, F0, 0);
        var rec = g.Record(null, "", "", 0, 0, null);
        Eq("the repeated slot as dealt", ((List<object>)g.Hd[0])[6], "[3,3,5,7,8]");
        Eq("same spawn order: no sp", ((List<object>)g.Hd[0])[8], "[]");
        Eq("the card named once", Field(rec, "cards"), "[[3,\"Card3\",0],[5,\"Card5\",2],[7,\"Card7\",1],[8,\"Card8\",2]]");
    }

    /// <summary>F4: the hook keeps at most 16 slots of an end-pick; the true
    /// slot count rides in n, the slots it did not keep count as unresolved
    /// and in omit sl.</summary>
    private static void TrueN()
    {
        var g = NewGame(30);
        g.OpenPhase(0, 1, 0, 0, 0);
        var kept = new List<long>();
        for (int i = 0; i < 16; i++) kept.Add(i);
        g.EndPick(kept, 20L, 0, 9, 0, 0, 1, F0, 0);
        var h = (List<object>)g.Hd[0];
        Eq("n is the true count", h[5], 20L);
        Eq("16 kept", ((List<long>)h[6]).Count, 16);
        Eq("the 4 not kept are unresolved", g.Tot[0][5], 4L);
        Eq("and omitted", Field(g.Record(null, "", "", 0, 0, null), "omit"), "{\"cards\":0,\"held0\":[0,0],\"ph\":0,\"hd\":0,\"ap\":0,\"sl\":4,\"sp\":0}");
    }

    /// <summary>A16: an over-cap game is at most 8192 bytes, omit is non-zero,
    /// every referenced cards entry is present, tot reflects the whole game.</summary>
    private static void Budget()
    {
        var g = BigGame();
        var rec = g.Record(null, new string('b', 64), "ok", 0, 0, null);
        string full = S.Json(rec);
        True("the untrimmed record is over the limit", full.Length > K.RECORD_MAX_BYTES);
        string text = K.Budget(rec);
        True("at most 8192 bytes", text.Length <= K.RECORD_MAX_BYTES);
        using (var doc = JsonDocument.Parse(text))
        {
            var root = doc.RootElement;
            long omitted = 0;
            foreach (var p in root.GetProperty("omit").EnumerateObject())
                if (p.Value.ValueKind == JsonValueKind.Array) foreach (var v in p.Value.EnumerateArray()) omitted += v.GetInt64();
                else omitted += p.Value.GetInt64();
            True("omit non-zero", omitted > 0);
            True("every referenced card present", RefsPresent(root));
            Eq("tot unchanged", root.GetProperty("tot").GetRawText(), Field(rec, "tot"));
        }
    }

    private static void BudgetTies()
    {
        var g = NewGame();
        g.Apply(0, 1, 0, 1, 0); g.Apply(0, 2, 0, 2, 0);
        g.OpenPhase(0, 1, 0, 0, 0); g.EndPick(L(1), 0, 1, 0, 0, 1, F0, 0); g.DonePicking(0);
        g.OpenPhase(1, 1, 0, 0, 0); g.EndPick(L(2), 0, 2, 0, 1, 1, F0, 0); g.DonePicking(0);
        var rec = g.Record(null, "", "", 0, 0, null);
        string full = S.Json(rec);
        string text = K.Budget(rec, full.Length - 1);
        using (var doc = JsonDocument.Parse(text))
            Eq("a tie trims the earliest list (ap)", doc.RootElement.GetProperty("omit").GetRawText(),
               "{\"cards\":0,\"held0\":[0,0],\"ph\":0,\"hd\":0,\"ap\":1,\"sl\":0,\"sp\":0}");
        Eq("under the limit nothing is trimmed", K.Budget(rec), full);
    }

    private static void BudgetCards()
    {
        // ten cards named only by applications: a card entry goes only once
        // no remaining entry names it
        var g = NewGame(10, null, null, 1, 40);
        // descending, so the last application trimmed frees the FIRST card entry, not the last
        for (int i = 0; i < 10; i++) g.Apply(0, 9 - i, 0, i, 0);
        var rec = g.Record(null, "", "", 0, 0, null);
        string full = S.Json(rec);
        string text = K.Budget(rec, full.Length - 200);
        using (var doc = JsonDocument.Parse(text))
        {
            True("every referenced card present", RefsPresent(doc.RootElement));
            True("an unreferenced card was trimmed", doc.RootElement.GetProperty("omit").GetProperty("cards").GetInt64() > 0);
        }
    }

    private static bool RefsPresent(JsonElement root)
    {
        var have = new HashSet<long>();
        foreach (var c in root.GetProperty("cards").EnumerateArray()) have.Add(c[0].GetInt64());
        var need = new List<long>();
        foreach (var h in root.GetProperty("hd").EnumerateArray()) { foreach (var s in h[6].EnumerateArray()) need.Add(s.GetInt64()); foreach (var s in h[8].EnumerateArray()) need.Add(s.GetInt64()); }
        foreach (var l in root.GetProperty("held0").EnumerateArray()) if (l.ValueKind == JsonValueKind.Array) foreach (var s in l.EnumerateArray()) need.Add(s.GetInt64());
        foreach (var a in root.GetProperty("ap").EnumerateArray()) need.Add(a[1].GetInt64());
        foreach (var n in need) if (n >= 0 && !have.Contains(n)) return false;
        return true;
    }

    private static void End()
    {
        var g = NewGame();
        g.OpenPhase(0, 1, 0, 0, 0);
        g.Spawn(1, 1, F0, 0);
        var rec = g.Record("left", "", "", 0, 0, null);
        Eq("end follows g", string.Join(",", rec.Keys), "schema,g,end,ns,pool,prof,po,sc,inc,cards,held0,ph,hd,ap,apx,tot,cost,omit");
        Eq("an unknown end kind is not emitted", string.Join(",", g.Record("quit", "", "", 0, 0, null).Keys), string.Join(",", K.RECORD_KEYS));
        string text = K.Budget(rec);
        string env = K.Envelope(SEAT, OTHER, STABLE, ATTACH, text, S.Hmac(Encoding.UTF8.GetBytes(KEY), K.Canonical(SEAT, OTHER, STABLE, ATTACH, text)));
        True("envelope built", env != null);
        var cut = new S.Pending { Route = "k", Body = env, FirstUnix = 1000 };
        True("a cut card record is recognised", S.IsCutRecord(cut));
        string full = K.Budget(g.Record(null, "", "", 0, 0, null));
        var whole = new S.Pending { Route = "k", Body = K.Envelope(SEAT, OTHER, STABLE, ATTACH, full, new string('0', 64)), FirstUnix = 1000 };
        True("a full-game card record is not cut", !S.IsCutRecord(whole));
        True("route e never reads a card body as cut", !S.IsCutRecord(new S.Pending { Route = "e", Body = env, FirstUnix = 1000 }));
        long d; string reason;
        cut.Attempts = 1;
        Eq("422 on a cut card record: kept for the next launch", S.Decide(cut, 422, "{\"detail\":\"end\"}", 0, 2000, out d, out reason).ToString(), "RetryNextLaunch");
        whole.Attempts = 1;
        Eq("422 on a full card record: dropped", S.Decide(whole, 422, "{\"detail\":\"g\"}", 0, 2000, out d, out reason).ToString(), "Drop");
        var back = S.ParseLine(S.Line(cut));
        True("the queue line keeps route k", back != null && back.Route == "k" && back.Body == env && back.Attempts == 1);
    }

    private static void Envelope()
    {
        string text = K.Budget(NewGame().Record(null, "", "", 0, 0, null));
        string canon = K.Canonical(SEAT, OTHER, STABLE, ATTACH, text);
        True("canonical prefix", canon.StartsWith("card-evidence:v1:" + SEAT + ":" + OTHER + ":", StringComparison.Ordinal));
        string sig = S.Hmac(Encoding.UTF8.GetBytes(KEY), canon);
        string env = K.Envelope(SEAT, OTHER, STABLE, ATTACH, text, sig);
        True("envelope", env != null && env.StartsWith("{\"contract\":2,\"seat_steam_id\":\"" + SEAT + "\"", StringComparison.Ordinal));
        True("same seat refused", K.Envelope(SEAT, SEAT, STABLE, ATTACH, text, sig) == null);
        True("bad attach refused", K.Envelope(SEAT, OTHER, STABLE, STABLE + "_x1", text, sig) == null);
        True("8192 bytes accepted", K.Envelope(SEAT, OTHER, STABLE, ATTACH, new string('a', 8192), sig) != null);
        True("8193 bytes refused", K.Envelope(SEAT, OTHER, STABLE, ATTACH, new string('a', 8193), sig) == null);
        True("non-ASCII refused", K.Envelope(SEAT, OTHER, STABLE, ATTACH, "{\"x\":\"é\"}", sig) == null);
        True("short sig refused", K.Envelope(SEAT, OTHER, STABLE, ATTACH, text, "ab") == null);
        True("control character refused", K.Envelope(SEAT, OTHER, STABLE, ATTACH, "{\"x\":1}\n", sig) == null);
        True("empty record refused", K.Envelope(SEAT, OTHER, STABLE, ATTACH, "", sig) == null);
    }

    // -- fixtures ---------------------------------------------------------------------------------

    private static K.CardGame FullGame()
    {
        var g = NewGame(12, null, new List<int> { 0, 1 });
        g.OpenPhase(0, 1, 0, 0, 0);
        Spawns(g, new[] { 0, 1, 2, 3, 4 }, 1, null, new K.DealFacts(0, 0, -1));
        g.Apply(0, 2, 0, 1002, 0);
        g.EndPick(L(0, 1, 2, 3, 4), 2, 1002, 2, 0, 1, F0, 0);
        g.DonePicking(0);
        g.OpenPhase(1, 1, 0, 0, 0);
        Spawns(g, new[] { 5, 6, 7, 8, 9 }, 1, null, new K.DealFacts(0, 0, -1));
        g.Apply(1, 9, 0, 2009, 0);
        g.EndPick(L(5, 6, 7, 8, 9), 4, 2009, 4, 1, 1, F0, 0);
        g.DonePicking(0);
        g.OpenPhase(1, 1, 1, 0, 0);
        Spawns(g, new[] { 10, 11, 0, 1, 3 }, 1, null, new K.DealFacts(0, 1, -1));
        g.Apply(1, 11, 0, 2011, 0);
        g.EndPick(L(10, 11, 0, 1, 3), 1, 2011, 1, 1, 1, F0, 0);
        g.DonePicking(0);
        g.OpenPhase(0, 1, 1, 1, 0);
        Spawns(g, new[] { 4, 6, 8, 10, 2 }, 1, null, new K.DealFacts(0, 1, -1));
        g.Apply(0, 4, 0, 1104, 0);
        g.EndPick(L(4, 6, 8, 10, 2), 0, 1104, 0, 0, 1, F0, 0);
        g.DonePicking(0);
        return g;
    }

    private static K.CardGame Game2HeldSameCards()
    {
        var g = NewGame(12, new IList<int>[] { new List<int> { 3, 5 }, new List<int> { 7 } }, new List<int> { 1, 0 }, 2);
        g.OpenPhase(1, 1, 0, 0, 0);
        Spawns(g, new[] { 1, 2, 3, 4, 6 }, 1, new[] { 0, 0, 0, 0, 0 }, new K.DealFacts(0, 1, -1));
        g.Apply(1, 6, 0, 2006, 0);
        g.EndPick(L(1, 2, 3, 4, 6), 4, 2006, 4, 1, 1, F0, 0);
        g.DonePicking(0);
        g.OpenPhase(0, 1, 0, 0, 0);
        Spawns(g, new[] { 1, 2, 3, 4, 6 }, 1, new[] { 0, 1, 2, 3, 4 }, new K.DealFacts(1, 2, 1));
        g.Apply(0, 1, 0, 1001, 0);
        g.EndPick(L(1, 2, 3, 4, 6), 0, 1001, 0, 0, 1, F0, 5);
        g.DonePicking(5);
        g.OpenPhase(0, 1, 0, 1, 5);
        Spawns(g, new[] { 8, 9, 10, 11, 0 }, 1, new[] { 5, 6, 6, 7, 8 }, new K.DealFacts(1, 3, 2));
        g.Apply(0, 10, 0, 1110, 1);
        g.EndPick(L(8, 9, 10, 11, 0), 2, 1110, 2, 0, 1, F0, 8);
        g.DonePicking(8);
        return g;
    }

    private static K.CardGame CutLeft()
    {
        var g = NewGame(12);
        g.OpenPhase(0, 1, 0, 0, 0);
        Spawns(g, new[] { 0, 1, 2, 3, 4 }, 1, null, F0);
        g.EndPick(L(0, 1, 2, 3, 4), 1, 1001, 1, 0, 1, F0, 0);
        g.DonePicking(0);
        g.OpenPhase(1, 1, 0, 0, 0);
        Spawns(g, new[] { 5, 6, 7 }, 1, null, F0);
        g.Close(0);
        return g;
    }

    private static K.CardGame BigGame()
    {
        int n = 120;
        var held0 = new List<int>(); var held1 = new List<int>();
        for (int i = 0; i < 64; i++) { held0.Add(i); held1.Add(119 - i); }
        var g = NewGame(n, new IList<int>[] { held0, held1 }, new List<int> { 0, 1 }, 3, 50);
        for (int p = 0; p < 42; p++)
        {
            int w = p % 2;
            g.OpenPhase(w, 1, p / 4, p / 5, 0);
            var ix = new int[18];
            for (int i = 0; i < 18; i++) ix[i] = (p * 7 + i * 13) % n;
            Spawns(g, ix, 1, null, new K.DealFacts(0, p, -1));
            var sl = new List<long>(); for (int i = 17; i >= 0; i--) sl.Add(ix[i]);
            g.Apply(w, ix[3], 0, 5000 + p, p % 7 == 0 ? 1 : 0);
            g.EndPick(sl, 14, 5000 + p, 3, w, 1, F0, 0);
            g.DonePicking(0);
        }
        for (int a = 0; a < 30; a++) g.Apply(a % 2, (a * 11) % n, 1, 0, 0);
        return g;
    }

    private static K.Profile FullProf(string rules = "ff=1;sc=0")
    {
        return new K.Profile { GameSha = new string('c', 64), GameState = "ok", ModSha = new string('d', 64), ModState = "ok",
                               Build = new[] { "1.41.0", "STANDALONE", "abc1234" }, Rules = rules };
    }

    /// <summary>A game whose first phase was not captured whole (CD-M3), a
    /// collector fault, a category name collision (CD-M4), an application
    /// skipped and one that threw (CD-M1), the room facts not read (CD-M2).</summary>
    private static K.CardGame FirstPhaseLost()
    {
        var g = NewGame(12, new IList<int>[] { new List<int> { 1 }, new List<int> { 2 } }, new List<int> { 0, 1 }, 4);
        g.Inc = K.INC_FIRST | K.INC_FAULT;
        g.PoolState = K.POOL_COLLISION;
        g.OpenPhase(1, 1, 2, 1, 0);
        Spawns(g, new[] { 3, 4, 5 }, 1, null, F0);
        g.Apply(1, 4, 0, 2004, K.APPLY_SKIPPED);
        g.Apply(1, 4, 0, 2004, K.APPLY_FAULTED);
        g.EndPick(L(3, 4, 5), 1, 2004, 1, 1, 1, F0, 0);
        g.Close(0);
        g.Seal();
        return g;
    }

    private static int Fixtures(string dir)
    {
        Directory.CreateDirectory(dir);
        var all = new List<KeyValuePair<string, S.JObj>>
        {
            new KeyValuePair<string, S.JObj>("full_game", FullGame().Record(null, FullProf(), 0, 0, Cost())),
            new KeyValuePair<string, S.JObj>("game2_held_samecards", Game2HeldSameCards().Record(null, FullProf("ff=1;sc=1"), 1, 1, Cost())),
            new KeyValuePair<string, S.JObj>("cut_left", CutLeft().Record("left", "", "read_failed", 0, 0, Cost())),
            new KeyValuePair<string, S.JObj>("over_cap", BigGame().Record("other_left", FullProf("ff=1;sc=1"), 1, 2, Cost())),
            new KeyValuePair<string, S.JObj>("first_phase_lost", FirstPhaseLost().Record("left", FullProf(), -1, -1, Cost())),
        };
        var names = new List<string>();
        foreach (var kv in all)
        {
            string input = S.Json(kv.Value);
            string text = K.Budget(kv.Value);
            string canon = K.Canonical(SEAT, OTHER, STABLE, ATTACH, text);
            string sig = S.Hmac(Encoding.UTF8.GetBytes(KEY), canon);
            string env = K.Envelope(SEAT, OTHER, STABLE, ATTACH, text, sig);
            if (env == null) { Console.WriteLine("fixture " + kv.Key + ": envelope refused"); return 1; }
            File.WriteAllBytes(Path.Combine(dir, kv.Key + ".input.json"), Encoding.ASCII.GetBytes(input));
            File.WriteAllBytes(Path.Combine(dir, kv.Key + ".record.txt"), Encoding.ASCII.GetBytes(text));
            File.WriteAllBytes(Path.Combine(dir, kv.Key + ".envelope.json"), Encoding.ASCII.GetBytes(env));
            names.Add(kv.Key);
        }
        File.WriteAllText(Path.Combine(dir, "cases.txt"), string.Join("\n", names) + "\n", Encoding.ASCII);
        return 0;
    }

    private static long[][] Cost()
    {
        return new[]
        {
            new long[] { 4, 120, 60, 0, 0 }, new long[] { 20, 80, 9, 0, 0 }, new long[] { 4, 40, 15, 0, 0 },
            new long[] { 4, 8, 3, 0, 0 }, new long[] { 4, 30, 12, 0, 0 }, new long[] { 0, 0, 0, 0, 0 },
        };
    }

    // -- runner -----------------------------------------------------------------------------------

    private static readonly List<KeyValuePair<string, Action>> CASES = new List<KeyValuePair<string, Action>>
    {
        new KeyValuePair<string, Action>("census", Census),
        new KeyValuePair<string, Action>("opening", Opening),
        new KeyValuePair<string, Action>("nopick", NoPick),
        new KeyValuePair<string, Action>("endpick_only", EndPickOnly),
        new KeyValuePair<string, Action>("spawn_order", SpawnOrder),
        new KeyValuePair<string, Action>("foreign", Foreign),
        new KeyValuePair<string, Action>("sender", Sender),
        new KeyValuePair<string, Action>("unresolved", Unresolved),
        new KeyValuePair<string, Action>("held", Held),
        new KeyValuePair<string, Action>("src_gen", SrcGen),
        new KeyValuePair<string, Action>("po", Po),
        new KeyValuePair<string, Action>("caps", Caps),
        new KeyValuePair<string, Action>("apps", Apps),
        new KeyValuePair<string, Action>("budget", Budget),
        new KeyValuePair<string, Action>("budget_ties", BudgetTies),
        new KeyValuePair<string, Action>("budget_cards", BudgetCards),
        new KeyValuePair<string, Action>("end", End),
        new KeyValuePair<string, Action>("envelope", Envelope),
        // fix pass 2
        new KeyValuePair<string, Action>("seal", Seal),
        new KeyValuePair<string, Action>("inc_first", IncFirst),
        new KeyValuePair<string, Action>("pool_states", PoolStates),
        new KeyValuePair<string, Action>("prof", Prof),
        new KeyValuePair<string, Action>("sc_not_run", ScNotRun),
        new KeyValuePair<string, Action>("true_n", TrueN),
        new KeyValuePair<string, Action>("repeated_slot", RepeatedSlot),
    };

    private static int Main(string[] args)
    {
        if (args.Length == 2 && args[0] == "fixtures") return Fixtures(args[1]);
        int failed = 0, ran = 0;
        foreach (var c in CASES)
        {
            if (args.Length == 1 && args[0] != c.Key) continue;
            ran++;
            _fails = 0;
            try { c.Value(); }
            catch (Exception ex) { _fails++; Console.WriteLine("  FAIL " + c.Key + " threw " + ex.GetType().Name + ": " + ex.Message); }
            Console.WriteLine((_fails == 0 ? "PASS " : "FAIL ") + c.Key);
            if (_fails > 0) failed++;
        }
        if (ran == 0) { Console.WriteLine("no such case"); return 2; }
        if (args.Length == 0) Console.WriteLine(failed == 0 ? "ALL PASS (" + ran + " cases)" : failed + " of " + ran + " cases FAILED");
        return failed == 0 ? 0 : 1;
    }
}
