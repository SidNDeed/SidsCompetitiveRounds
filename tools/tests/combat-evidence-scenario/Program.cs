using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Reflection;
using System.Security.Cryptography;
using System.Text;
using ExitGames.Client.Photon;
using HarmonyLib;
using Photon.Pun;
using UnityEngine;

namespace CompetitiveRounds
{
    /// <summary>The scripted 1v1, from ONE seat's point of view (args: seat 1|2,
    /// output path, options). Every patch part is invoked by reflection exactly
    /// as Harmony would (prefix, the original's effect, postfix on a normal
    /// return, finalizer with the exception), arguments matched by parameter
    /// name, the shared RPC frame pushed around every received or locally
    /// executed RPC. Both seats' runs replay the same world events, each seen
    /// from its own side, so the two records pair as two real seats' would.
    ///
    /// Output lines: DIGEST (the game witness: every game value a hook could
    /// reach, hashed after every patched call and every tick), COST row calls
    /// faults, ENV (each queued envelope), LOG (the plug-in log), DROPIX (the
    /// drop counters against the layout's names), ERR (a hook let an exception
    /// out, or the driver could not bind an argument).
    ///
    /// Options: --a1 (A1Live), --plant ROW (the throwing build's row),
    /// --drop CLASS (leave a patch class out of the registry the boot census
    /// reads), --unkeyed (a hit on this seat by a projectile it never saw
    /// initialised), --perf (the A14 menu measurement instead of a game).</summary>
    internal static class ScenarioProgram
    {
        private const BindingFlags All = BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Static | BindingFlags.Instance;
        private static readonly CultureInfo Inv = CultureInfo.InvariantCulture;
        private static int Local, Other, Clock;
        private static readonly List<string> Out = new List<string>();
        private static readonly StringBuilder Witness = new StringBuilder();
        private static readonly HashSet<string> Dropped = new HashSet<string>();

        private sealed class Seat
        {
            internal int Actor; internal GameObject Root, Body, GunGo; internal Player P; internal CharacterData D; internal PhotonView V;
            internal PlayerVelocity Vel; internal Block B; internal HealthHandler H; internal CharacterStatModifiers S; internal GeneralInput In;
            internal Gun G; internal GunAmmo A;
        }

        private sealed class Proj
        {
            internal int Owner, Pid; internal GameObject Go; internal PhotonView V; internal ProjectileInit Init; internal ProjectileHit Hit;
            internal MoveTransform Move; internal BounceEffectRetarget Rt; internal ScreenEdgeBounce Edge; internal SyncProjectile Sync;
        }

        private static readonly Seat[] Seats = new Seat[3];
        private static readonly List<Proj> Projs = new List<Proj>();

        // -- the combat file, by reflection (the red run compiles an older file) --------------------

        private static readonly Type CE = typeof(CombatEvidence);

        private static object CallCE(string name, params object[] a)
        {
            var m = CE.GetMethod(name, All);
            if (m == null) return null;
            return m.Invoke(null, a);
        }

        private static void SetCE(string field, object v)
        {
            var f = CE.GetField(field, All);
            if (f != null) f.SetValue(null, v);
        }

        // -- the mini-Harmony ---------------------------------------------------------------------

        private static Type PatchClass(string n)
        {
            if (Dropped.Contains(n)) return null;
            return CE.Assembly.GetType("CompetitiveRounds." + n);
        }

        private static MethodInfo Part(Type t, string attr)
        {
            foreach (var m in t.GetMethods(All))
                foreach (var a in m.GetCustomAttributes(false))
                    if (a.GetType().Name == attr) return m;
            return null;
        }

        private static Dictionary<string, object> Args(params object[] kv)
        {
            var d = new Dictionary<string, object>();
            for (int i = 0; i + 1 < kv.Length; i += 2) d[(string)kv[i]] = kv[i + 1];
            return d;
        }

        private static object InvokePart(MethodInfo m, object inst, Dictionary<string, object> args, object result, object state, out object stateOut)
        {
            var ps = m.GetParameters();
            var a = new object[ps.Length];
            int si = -1;
            for (int i = 0; i < ps.Length; i++)
            {
                string n = ps[i].Name;
                if (n == "__instance") a[i] = inst;
                else if (n == "__result") a[i] = result;
                else if (n == "__state") { a[i] = state; si = i; }
                else if (n == "__exception") a[i] = null;
                else if (args.ContainsKey(n)) a[i] = args[n];
                else throw new InvalidOperationException("no argument " + n + " for " + m.DeclaringType.Name + "." + m.Name);
            }
            object r;
            try { r = m.Invoke(null, a); }
            catch (TargetInvocationException ex)
            {
                Out.Add("ERR hook let an exception out: " + m.DeclaringType.Name + "." + m.Name + ": " + ex.InnerException.GetType().Name);
                r = null;
            }
            stateOut = si >= 0 ? a[si] : state;
            return r;
        }

        /// <summary>One patched call: prefix, the original's effect, postfix (normal return), finalizer.</summary>
        private static object Call(string patch, object inst, Dictionary<string, object> args, Func<object> original)
        {
            var t = PatchClass(patch);
            object state = null, result;
            try
            {
                if (t != null)
                {
                    var pre = Part(t, "HarmonyPrefix");
                    if (pre != null) InvokePart(pre, inst, args, null, null, out state);
                }
                result = original();
                if (t != null)
                {
                    var post = Part(t, "HarmonyPostfix");
                    object ignored;
                    if (post != null) InvokePart(post, inst, args, result, state, out ignored);
                    var fin = Part(t, "HarmonyFinalizer");
                    if (fin != null && InvokePart(fin, inst, args, result, state, out ignored) != null)
                        Out.Add("ERR finalizer of " + patch + " returned an exception for a normal return");
                }
            }
            catch (InvalidOperationException ex) { Out.Add("ERR " + ex.Message); result = null; }
            Snapshot("call " + patch);
            return result;
        }

        private static void Push(int stamp, int sender, int view, string method)
        {
            SeatEvidence.Frames.Add(new SeatEvidence.Frame { Stamp = stamp, Sender = sender, View = view, Method = method });
        }

        private static void Pop() { SeatEvidence.Frames.RemoveAt(SeatEvidence.Frames.Count - 1); }

        // -- the clock, the tick, the witness -------------------------------------------------------

        private static void At(int t)
        {
            if (t < Clock) Out.Add("ERR clock went back: " + t + " < " + Clock);
            Clock = t; PhotonNetwork.ServerTimestamp = t; SeatEvidence.Sw = t;
        }

        private const float DT = 1f / 60f;

        private static void Tick()
        {
            Time.frameCount++;
            for (int a = 1; a <= 2; a++)
            {
                var s = Seats[a];
                if (!s.D.dead) s.Vel.position = s.Vel.position + s.Vel.velocity * DT;
                s.Vel.velocity = s.Vel.velocity * 0.9f;
                s.B.sinceBlock += DT; s.B.counter += DT;
            }
            foreach (var p in Projs) p.Go.transform.position = p.Go.transform.position + p.Move.velocity * DT;
            try { CallCE("Tick"); }
            catch (TargetInvocationException ex) { Out.Add("ERR the tick let an exception out: " + ex.InnerException.GetType().Name); }
            Snapshot("tick");
        }

        private static void RunUntil(int t)
        {
            while (Clock + 16 <= t) { At(Clock + 16); Tick(); }
            if (Clock < t) At(t);
        }

        private static string F(float v) { return v.ToString("R", Inv); }

        /// <summary>Every game value a hook could reach, appended after each call and tick.</summary>
        private static void Snapshot(string what)
        {
            Witness.Append(what).Append('|');
            for (int a = 1; a <= 2; a++)
            {
                var s = Seats[a];
                Witness.Append(F(s.D.health)).Append(',').Append(s.D.dead).Append(',').Append(s.D.isPlaying).Append(',')
                       .Append(F(s.Vel.position.x)).Append(',').Append(F(s.Vel.position.y)).Append(',')
                       .Append(F(s.Vel.velocity.x)).Append(',').Append(F(s.Vel.velocity.y)).Append(',').Append(F(s.Vel.mass)).Append(',')
                       .Append(F(s.B.sinceBlock)).Append(',').Append(F(s.B.counter)).Append(',').Append(s.B.delayOtherActions).Append(',')
                       .Append(s.A.currentAmmo).Append(',').Append(s.A.maxAmmo).Append(',').Append(F(s.A.reloadCounter)).Append(',')
                       .Append(s.G.isReloading).Append(',').Append(F(s.G.spread)).Append(',').Append(s.G.lockGunToDefault).Append(',')
                       .Append(F(s.In.aimDirection.x)).Append(',').Append(F(s.In.aimDirection.y)).Append(';');
            }
            foreach (var p in Projs)
                Witness.Append(p.Pid).Append(':').Append(F(p.Move.velocity.x)).Append(',').Append(F(p.Move.velocity.y)).Append(',')
                       .Append(F(p.Go.transform.position.x)).Append(',').Append(F(p.Go.transform.position.y)).Append(',')
                       .Append(PhotonNetwork.Views.ContainsKey(p.Pid)).Append(';');
            Witness.Append(TimeHandler.timeScale.ToString("R", Inv)).Append('\n');
        }

        // -- the world -----------------------------------------------------------------------------

        private static Seat MakeSeat(int actor, float x, float y)
        {
            var s = new Seat { Actor = actor };
            s.Root = new GameObject("player" + actor);
            s.P = s.Root.Add<Player>(); s.D = s.Root.Add<CharacterData>(); s.V = s.Root.Add<PhotonView>(); s.B = s.Root.Add<Block>();
            s.H = s.Root.Add<HealthHandler>(); s.S = s.Root.Add<CharacterStatModifiers>(); s.In = s.Root.Add<GeneralInput>();
            var col = s.Root.Add<Collider2D>(); col.bounds = new Bounds { extents = new Vector3(1f, 1f, 0f) };
            // M2: the body the game moves is a child whose position differs from the root transform's
            s.Body = new GameObject("body" + actor) { Parent = s.Root }; s.Root.Children.Add(s.Body);
            s.Vel = s.Body.Add<PlayerVelocity>();
            s.Root.transform.position = new Vector3(5000f + actor, -5000f, 0f);
            s.Vel.position = new Vector2(x, y);
            s.GunGo = new GameObject("gun" + actor) { Parent = s.Root }; s.Root.Children.Add(s.GunGo);
            s.G = s.GunGo.Add<Gun>(); s.A = s.GunGo.Add<GunAmmo>();
            s.G.gunAmmo = s.A; s.A.gun = s.G; s.G.player = s.P; s.G.shootPosition = s.GunGo.transform;
            s.GunGo.transform.position = new Vector3(x, y, 0f);
            var wh = s.Root.Add<WeaponHandler>(); wh.gun = s.G;
            s.D.view = s.V; s.D.playerVel = s.Vel; s.D.weaponHandler = wh; s.D.block = s.B; s.D.stats = s.S; s.D.input = s.In; s.D.mainCol = col; s.D.player = s.P;
            s.P.data = s.D; s.P.PlayerID = actor - 1;
            s.V.ViewID = actor * 1000 + 1; s.V.OwnerActorNr = actor; s.V.IsMine = actor == Local;
            PhotonNetwork.Views[s.V.ViewID] = s.V;
            PlayerManager.instance.players.Add(s.P);
            return s;
        }

        private static Proj MakeProj(int owner, int pid, Vector2 dir, bool retarget, bool edge)
        {
            var at = Seats[owner].Vel.position;
            var p = new Proj { Owner = owner, Pid = pid };
            p.Go = new GameObject("bullet" + pid);
            p.V = p.Go.Add<PhotonView>(); p.V.ViewID = pid; p.V.OwnerActorNr = owner; p.V.IsMine = owner == Local;
            p.Init = p.Go.Add<ProjectileInit>(); p.Hit = p.Go.Add<ProjectileHit>(); p.Move = p.Go.Add<MoveTransform>(); p.Hit.move = p.Move;
            p.Go.Add<SpawnedAttack>();
            if (retarget) { p.Rt = p.Go.Add<BounceEffectRetarget>(); p.Rt.view = p.V; p.Rt.move = p.Move; }
            if (edge) { p.Edge = p.Go.Add<ScreenEdgeBounce>(); p.Edge.projHit = p.Hit; }
            p.Sync = p.Go.Add<SyncProjectile>(); p.Sync.photonView = p.V;
            p.Go.transform.position = new Vector3(at.x, at.y, 0f);
            p.Go.transform.forward = new Vector3(dir.x, dir.y, 0f);
            p.Move.velocity = new Vector3(dir.x * 50f, dir.y * 50f, 0f);
            PhotonNetwork.Views[pid] = p.V;
            Projs.Add(p);
            return p;
        }

        private static Vector2 Dir(Seat from, Seat to)
        {
            var d = to.Vel.position - from.Vel.position;
            return d.normalized;
        }

        // -- the events, each seen from this seat ---------------------------------------------------

        private static void RpcSent(PhotonView v, string method)
        {
            // the plug-in's send hook (SeatEvidence_RpcSendPatch) calls this contained
            try { CallCE("RpcSent", v, method, RpcTarget.Others); }
            catch (TargetInvocationException ex) { Out.Add("ERR RpcSent let an exception out: " + ex.InnerException.GetType().Name); }
            Snapshot("sent " + method);
        }

        private static void Init(Seat s, Proj p, int t)
        {
            Push(t, s.Actor, p.Pid, "RPCA_Init");
            Call("CombatEvidence_InitAmmoPatch", p.Init, Args("senderID", s.Actor, "nrOfProj", 1, "dmgM", 1f, "randomSeed", 0f),
                 () => { s.A.currentAmmo--; return null; });
            Pop();
        }

        private static Dictionary<string, object> AttackArgs(bool forced)
        {
            return Args("charge", 0f, "forceAttack", forced, "damageM", 1f, "recoilMultiplier", 1f, "useAmmo", true);
        }

        /// <summary>One emission of the shooter's gun: the send and the init on the
        /// owner; the attack message and the init on the other seat.</summary>
        private static void Emission(Seat s, Proj p, int t)
        {
            if (s.Actor == Local)
            {
                At(t);
                RpcSent(s.V, "Shoot");
                Init(s, p, t);
                return;
            }
            At(t + 40);
            Push(t, s.Actor, s.V.ViewID, "Shoot");
            Call("CombatEvidence_AttackPatch", s.G, AttackArgs(true), () => true);
            Pop();
            Init(s, p, t);
        }

        /// <summary>M4: an accepted attack of three emissions (the first inside the call,
        /// two from the coroutine) with a refused press between the last two.</summary>
        private static void Attack(Seat s, Proj[] ps, int t)
        {
            if (s.Actor == Local)
            {
                At(t);
                Call("CombatEvidence_AttackPatch", s.G, AttackArgs(false), () => { Emission(s, ps[0], t); return true; });
                for (int i = 1; i < ps.Length; i++)
                {
                    if (i == ps.Length - 1) { At(t + 100 * i - 50); Call("CombatEvidence_AttackPatch", s.G, AttackArgs(false), () => false); }
                    Emission(s, ps[i], t + 100 * i);
                }
                return;
            }
            for (int i = 0; i < ps.Length; i++) Emission(s, ps[i], t + 100 * i);
        }

        private static void Contact(Proj p, Seat victim)
        {
            var hit = new HitInfo { transform = victim.Root.transform, normal = new Vector2(-1f, 0f), point = victim.Vel.position };
            Call("CombatEvidence_ContactPatch", p.Hit, Args("hit", hit, "forceCall", false), () => null);
        }

        private static void Damage(Seat v, int stamp, int sender, float dmg, bool oob)
        {
            Push(stamp, sender, v.V.ViewID, "RPCA_SendTakeDamage");
            Call("CombatEvidence_DamagePatch", v.H, Args("damage", new Vector2(0f, -dmg), "position", v.Vel.position, "lethal", true, "playerID", -1,
                 "damageSource", oob ? HealthHandler.DamageSource.OutOfBounds : HealthHandler.DamageSource.Player),
                 () => { v.D.health -= dmg; return null; });
            Pop();
        }

        private static void Force(Seat v, int stamp, int sender, Vector2 force)
        {
            Push(stamp, sender, v.V.ViewID, "RPCA_SendTakeForce");
            Call("CombatEvidence_ForcePatch", v.H, Args("force", force, "forceMode", 0, "forceIgnoreMass", false, "ignoreBlock", false, "setFlying", 0f),
                 () => { v.Vel.velocity = v.Vel.velocity + force / v.Vel.mass; return null; });
            Pop();
        }

        private static void Die(Seat v, int stamp, int sender, bool phoenix)
        {
            Push(stamp, sender, v.V.ViewID, phoenix ? "RPCA_Die_Phoenix" : "RPCA_Die");
            Call(phoenix ? "CombatEvidence_DiePhoenixPatch" : "CombatEvidence_DiePatch", v.H, Args("deathDirection", new Vector2(1f, 0f)),
                 () => { if (v.D.isPlaying && !v.D.dead) v.D.dead = true; return null; });
            Pop();
        }

        private static Dictionary<string, object> HitArgs(Vector2 point, Vector2 vel, int viewID, bool blocked)
        {
            return Args("hitPoint", point, "hitNormal", new Vector2(-1f, 0f), "vel", vel, "viewID", viewID, "colliderID", -1, "wasBlocked", blocked);
        }

        /// <summary>A projectile's hit on the other player: the shooter's copy decides
        /// (contact), its hit message executes locally with the damage and the force
        /// it creates inside; the victim's seat sees its own copy's contact, then the
        /// message, the damage and the force arrive in send order.</summary>
        private static void PlayerHit(Proj p, Seat victim, int t, float dmg, Vector2 force, bool blocked, Vector2 newVel, bool lethal)
        {
            var shooter = Seats[p.Owner];
            if (p.Owner == Local)
            {
                At(t - 10); Contact(p, victim);
                At(t);
                Push(t, Local, p.Pid, "RPCA_DoHit");
                Call("CombatEvidence_HitPatch", p.Hit, HitArgs(victim.Vel.position, newVel, victim.V.ViewID, blocked), () =>
                {
                    p.Move.velocity = newVel;
                    if (blocked) return null;
                    Damage(victim, t + 1, Local, dmg, false);
                    Force(victim, t + 2, Local, force);
                    return null;
                });
                Pop();
                if (lethal && !blocked)
                {
                    Die(victim, t + 3, Local, false);                         // this seat's own death message
                    At(t + 44); Die(victim, t + 4, victim.Actor, false);      // the victim's, a second time: the game's guard refuses it
                }
                return;
            }
            At(t - 5); Contact(p, victim);
            At(t + 40);
            Push(t, p.Owner, p.Pid, "RPCA_DoHit");
            Call("CombatEvidence_HitPatch", p.Hit, HitArgs(victim.Vel.position, newVel, victim.V.ViewID, blocked), () => { p.Move.velocity = newVel; return null; });
            Pop();
            if (blocked) return;
            At(t + 41); Damage(victim, t + 1, p.Owner, dmg, false);
            At(t + 42); Force(victim, t + 2, p.Owner, force);
            if (lethal)
            {
                Die(victim, t + 4, Local, false);
                At(t + 43); Die(victim, t + 3, p.Owner, false);
            }
        }

        /// <summary>M6: two contacts of one projectile on this seat's player before
        /// either hit message arrives (the messages arrive in contact order).</summary>
        private static void DoubleContact(Proj p, Seat victim, int t)
        {
            if (p.Owner == Local)
            {
                for (int i = 0; i < 2; i++)
                {
                    At(t + 50 * i - 10); Contact(p, victim);
                    At(t + 50 * i);
                    Push(t + 50 * i, Local, p.Pid, "RPCA_DoHit");
                    Call("CombatEvidence_HitPatch", p.Hit, HitArgs(victim.Vel.position, p.Move.velocity, victim.V.ViewID, true), () => null);
                    Pop();
                }
                return;
            }
            At(t - 5); Contact(p, victim);
            At(t + 45); Contact(p, victim);
            for (int i = 0; i < 2; i++)
            {
                At(t + 50 * i + 60);
                Push(t + 50 * i, p.Owner, p.Pid, "RPCA_DoHit");
                Call("CombatEvidence_HitPatch", p.Hit, HitArgs(victim.Vel.position, p.Move.velocity, victim.V.ViewID, true), () => null);
                Pop();
            }
        }

        /// <summary>A projectile's hit on a surface (no player view); `destroy` removes it inside the message.</summary>
        private static void WallHit(Proj p, int t, Vector2 newVel, bool destroy)
        {
            At(p.Owner == Local ? t : t + 40);
            Push(t, p.Owner, p.Pid, "RPCA_DoHit");
            Call("CombatEvidence_HitPatch", p.Hit, HitArgs((Vector2)p.Go.transform.position, newVel, -1, false), () =>
            {
                p.Move.velocity = newVel;
                if (destroy) PhotonNetwork.Views.Remove(p.Pid);
                return null;
            });
            Pop();
        }

        private static Dictionary<string, object> BlockArgs()
        {
            return Args("firstBlock", true, "dontSetCD", false, "blockTriggerType", 0, "useBlockPos", Vector3.zero, "onlyBlockEffects", false);
        }

        private static void SendBlock(Seat s, int t)
        {
            At(t);
            PhotonNetwork.rpcEvent = new Hashtable();
            PhotonNetwork.rpcEvent[(byte)0] = s.V.ViewID; PhotonNetwork.rpcEvent[(byte)2] = t;
            RpcSent(s.V, "RPCAO_DoBlock");
            PhotonNetwork.rpcEvent = null;
        }

        /// <summary>M5: a block press. The owner's TryBlock runs the block locally and
        /// sends it (inside, or 0.2 s later with delayOtherActions); the other seat
        /// receives the block message.</summary>
        private static void Press(Seat s, int t, bool delayed)
        {
            s.B.delayOtherActions = delayed;
            if (s.Actor == Local)
            {
                At(t);
                bool sent = false;
                Call("CombatEvidence_TryBlockPatch", s.B, Args(), () =>
                {
                    if (s.B.counter < s.B.Cooldown()) return null;
                    s.B.counter = 0f;
                    Call("CombatEvidence_BlockPatch", s.B, BlockArgs(), () => { s.B.sinceBlock = 0f; return null; });
                    if (!delayed) { SendBlock(s, t); sent = true; }
                    return null;
                });
                if (delayed && s.B.counter == 0f && !sent) SendBlock(s, t + 200);
                return;
            }
            if (s.B.counter < s.B.Cooldown()) return;           // a refused press sends nothing
            int st = delayed ? t + 200 : t;
            At(st + 40);
            s.B.counter = 0f;
            Push(st, s.Actor, s.V.ViewID, "RPCAO_DoBlock");
            Call("CombatEvidence_BlockPatch", s.B, BlockArgs(), () => { s.B.sinceBlock = 0f; return null; });
            Pop();
        }

        private static void Retarget(Proj p, Seat target, int t, Vector2 newVel)
        {
            At(t - 100);
            var hit = new HitInfo { normal = new Vector2(0f, 1f), point = (Vector2)p.Go.transform.position };
            // FindTarget runs on every seat (DelayMove); the result as the game computed it
            Call("CombatEvidence_FindTargetPatch", p.Rt, Args("hit", hit), () => target.P);
            At(p.Owner == Local ? t : t + 40);
            Push(t, p.Owner, p.Pid, "RPCA_RecieveFunction");
            Call("CombatEvidence_TargetBouncePatch", p.Rt, Args("newVel", newVel), () => { p.Move.velocity = newVel; return null; });
            Pop();
        }

        private static void Edge(Proj p, int t)
        {
            At(p.Owner == Local ? t : t + 40);
            Push(t, p.Owner, p.Pid, "RPCA_RecieveFunction");
            Call("CombatEvidence_EdgeBouncePatch", p.Edge, Args(), () =>
            {
                p.Move.velocity = new Vector3(-p.Move.velocity.x, p.Move.velocity.y, 0f);
                return null;
            });
            Pop();
        }

        private static void Sync(Proj p, int t)
        {
            At(t);
            var st = new PhotonStream { IsWriting = p.Owner == Local };
            p.Sync.syncPackages.Add(new ProjectileSyncPackage { vel = p.Move.velocity, timeDelta = 0.05f });
            Call("CombatEvidence_SyncPatch", p.Sync, Args("stream", st, "info", null), () => null);
        }

        private static void Reload(Seat s, int t)
        {
            At(t);
            s.G.isReloading = true; s.A.reloadCounter = -0.01f;
            Call("CombatEvidence_ReloadPatch", s.A, Args("playSound", true), () =>
            {
                s.A.currentAmmo = s.A.maxAmmo; s.G.isReloading = false; s.A.reloadCounter = 0f;
                return null;
            });
        }

        private static void Dealt(Seat s, int t)
        {
            At(t);
            s.S.refreshOnDamage = true;
            Call("CombatEvidence_DealtPatch", s.S, Args("damage", new Vector2(0f, -10f), "selfDamage", false, "damagedPlayer", null), () => null);
        }

        /// <summary>R5: an out-of-bounds death. The body is past the right edge; its
        /// owner applies the force and the damage (source out of bounds), and the
        /// death follows, all three sent by the owner.</summary>
        private static void OobDeath(Seat v, int t)
        {
            v.Vel.position = new Vector2(40f, 0f);
            int d = v.Actor == Local ? 0 : 40;
            At(t + d); Force(v, t, v.Actor, new Vector2(-500f, 0f));
            At(t + d + 1); Damage(v, t + 1, v.Actor, 200f, true);
            At(t + d + 2); Die(v, t + 2, v.Actor, false);
        }

        private static void Revive()
        {
            for (int a = 1; a <= 2; a++)
            {
                var s = Seats[a];
                s.D.health = 100f; s.D.dead = false; s.Vel.velocity = Vector2.zero;
                s.Vel.position = new Vector2(a == 1 ? -10f : 10f, 0f);
                s.GunGo.transform.position = new Vector3(s.Vel.position.x, 0f, 0f);
                s.A.currentAmmo = s.A.maxAmmo;
            }
        }

        // -- the script -----------------------------------------------------------------------------

        private static void Script(bool unkeyed)
        {
            var A = Seats[1]; var B = Seats[2];
            // aim: each player aims at the other's body (the game's upward aim term added, as GeneralInput does)
            A.In.aimDirection = new Vector3(1f, 0.13f / Mathf.Clamp(A.G.projectileSpeed, 1f, 100f), 0f);
            B.In.aimDirection = new Vector3(-1f, 0.13f / Mathf.Clamp(B.G.projectileSpeed, 1f, 100f), 0f);
            A.G.lockGunToDefault = true;                                           // M3: the locked gun
            A.GunGo.transform.forward = new Vector3(1f, 0f, 0f); B.GunGo.transform.forward = new Vector3(-1f, 0f, 0f);

            At(100000); SeatEvidence.Combat = true; Tick();                         // point 1 starts
            // the reaction sampler's onset: sight blocked, then clear
            Physics2D.Blockers.Add(new GameObject("wall").transform);
            RunUntil(100300);
            Physics2D.Blockers.Clear();
            RunUntil(100990);

            var pa = new[] { MakeProj(1, 1101, Dir(A, B), false, false), MakeProj(1, 1102, Dir(A, B), true, false), MakeProj(1, 1103, Dir(A, B), false, true) };
            Attack(A, pa, 101000);                                                  // M4
            RunUntil(101490);
            var pb1 = MakeProj(2, 2101, Dir(B, A), false, false);
            Attack(B, new[] { pb1 }, 101500);
            RunUntil(101990);
            Press(A, 102000, false);                                                // M5: sent inside TryBlock
            RunUntil(102050);
            PlayerHit(pb1, A, 102100, 10f, new Vector2(-200f, 0f), true, new Vector2(50f, 0f), false);    // a blocked hit
            RunUntil(102990);
            Press(A, 103000, false);                                                // refused (cooldown)
            RunUntil(103980);
            PlayerHit(pa[0], B, 104000, 20f, new Vector2(300f, 50f), false, new Vector2(-30f, 10f), false); // R1 push, R3 chain
            RunUntil(104490);
            Sync(pa[1], 104500);
            RunUntil(104990);
            var pb2 = MakeProj(2, 2102, Dir(B, A), false, false);
            Attack(B, new[] { pb2 }, 105000);
            RunUntil(105090);
            DoubleContact(pb2, A, 105100);                                          // M6
            RunUntil(105890);
            Retarget(pa[1], B, 106000, new Vector2(40f, -5f));                      // R2 selection (its choice at 105900)
            RunUntil(106490);
            Edge(pa[2], 106500);                                                    // R2 surface, F4
            RunUntil(106790);
            WallHit(pa[1], 106800, new Vector2(-40f, 5f), true);                    // R2 surface + destruction
            RunUntil(106990);
            Press(A, 107000, true);                                                 // M5: sent 0.2 s later
            RunUntil(107990);
            PlayerHit(pa[2], B, 108000, 15f, new Vector2(250f, 0f), false, new Vector2(-20f, 0f), false);  // a hit after an edge bounce
            RunUntil(108990);
            if (unkeyed)
            {
                var stray = new Proj { Owner = 2, Pid = 2199 };
                stray.Go = new GameObject("stray"); stray.V = stray.Go.Add<PhotonView>(); stray.V.ViewID = 2199; stray.V.OwnerActorNr = 2; stray.V.IsMine = Local == 2;
                stray.Hit = stray.Go.Add<ProjectileHit>(); stray.Move = stray.Go.Add<MoveTransform>(); stray.Hit.move = stray.Move;
                stray.Init = stray.Go.Add<ProjectileInit>(); stray.Sync = stray.Go.Add<SyncProjectile>(); stray.Sync.photonView = stray.V;
                PhotonNetwork.Views[2199] = stray.V; Projs.Add(stray);
                PlayerHit(stray, A, 109000, 5f, new Vector2(-100f, 0f), false, new Vector2(10f, 0f), false);
                RunUntil(109090);
            }
            Reload(A, 109100); Reload(B, 109110);
            Dealt(A, 109200);
            RunUntil(109990);
            OobDeath(B, 110000);                                                    // R5: out of bounds, right edge
            RunUntil(110490);
            At(110500); SeatEvidence.Combat = false; Tick();                        // point 1 ends
            RunUntil(119990);

            Revive();
            At(120000); SeatEvidence.Combat = true; Tick();                         // point 2
            RunUntil(120490);
            var pb3 = MakeProj(2, 2103, Dir(B, A), false, false);
            Attack(B, new[] { pb3 }, 120500);
            RunUntil(120990);
            PlayerHit(pb3, A, 121000, 150f, new Vector2(-400f, 20f), false, new Vector2(30f, 0f), true);   // R5: a death by damage
            RunUntil(121490);
            At(121500); SeatEvidence.Combat = false; Tick();
            RunUntil(121990);
        }

        private static void Registry()
        {
            Harmony.Registry.Clear();
            foreach (var t in CE.Assembly.GetTypes())
            {
                if (t.Namespace != "CompetitiveRounds" || Dropped.Contains(t.Name)) continue;
                foreach (var a in t.GetCustomAttributes(false))
                {
                    var hp = a as HarmonyPatch;
                    if (hp == null) continue;
                    MethodBase target = null;
                    foreach (var m in hp.Target.GetMethods(All)) if (m.Name == hp.Method) { target = m; break; }
                    if (target == null) { Out.Add("ERR no target " + hp.Target.Name + "." + hp.Method); continue; }
                    Patches ps;
                    if (!Harmony.Registry.TryGetValue(target, out ps)) Harmony.Registry[target] = ps = new Patches();
                    var pre = Part(t, "HarmonyPrefix"); if (pre != null) ps.Prefixes.Add(new Patch { PatchMethod = pre });
                    var post = Part(t, "HarmonyPostfix"); if (post != null) ps.Postfixes.Add(new Patch { PatchMethod = post });
                    var fin = Part(t, "HarmonyFinalizer"); if (fin != null) ps.Finalizers.Add(new Patch { PatchMethod = fin });
                }
            }
            // the shared frame's own patches live in other evidence files of the plug-in
            foreach (var pair in new[] { Tuple.Create(typeof(PhotonNetwork).GetMethod("ExecuteRpc"), typeof(HitEvidence_ExecuteRpcPatch).GetMethod("Prefix", All), "p"),
                                         Tuple.Create(typeof(PhotonNetwork).GetMethod("RPC"), typeof(SeatEvidence_RpcSendPatch).GetMethod("Postfix", All), "o") })
            {
                if (Dropped.Contains(pair.Item2.DeclaringType.Name)) continue;
                var ps = new Patches();
                (pair.Item3 == "p" ? ps.Prefixes : ps.Postfixes).Add(new Patch { PatchMethod = pair.Item2 });
                Harmony.Registry[pair.Item1] = ps;
            }
        }

        private static void Perf()
        {
            Plugin.ConfigFileForLevers.Values["Debug.CombatEvidencePerfProbe"] = "menu";
            PhotonNetwork.InRoom = false;
            long last = System.Diagnostics.Stopwatch.GetTimestamp();
            for (int i = 0; i < 2400; i++)
            {
                long now = System.Diagnostics.Stopwatch.GetTimestamp();
                double realUs = (now - last) * 1e6 / System.Diagnostics.Stopwatch.Frequency;
                last = now;
                // the engine's frame time: a 60 Hz frame plus whatever the previous frame's work cost
                Time.unscaledDeltaTime = (float)((16667.0 + realUs) / 1e6);
                CallCE("Tick");
            }
        }

        private static int Main(string[] args)
        {
            Local = int.Parse(args[0], Inv); Other = 3 - Local;
            string path = args[1];
            bool a1 = false, unkeyed = false, perf = false;
            for (int i = 2; i < args.Length; i++)
            {
                if (args[i] == "--a1") a1 = true;
                else if (args[i] == "--unkeyed") unkeyed = true;
                else if (args[i] == "--perf") perf = true;
                else if (args[i] == "--plant") ScenarioPlant.Row = int.Parse(args[++i], Inv);
                else if (args[i] == "--drop") Dropped.Add(args[++i]);
            }
            Out.Add("SEAT " + Local);
            PhotonNetwork.LocalPlayer.ActorNumber = Local;
            PhotonNetwork.CurrentRoom.Name = "scrroom1";
            RoomActors.Others = new[] { new Photon.Realtime.Player { ActorNumber = Other } };
            Seats[1] = MakeSeat(1, -10f, 0f); Seats[2] = MakeSeat(2, 10f, 0f);
            Snapshot("world");
            if (perf) Perf();
            else
            {
                Registry();
                CallCE("BootLine");
                SetCE("A1Live", a1);
                CallCE("BeginGame", true);
                Script(unkeyed);
                CallCE("Dispatch", Local == 1 ? "76561190000000001" : "76561190000000002", Local == 1 ? "76561190000000002" : "76561190000000001",
                       "scrroom1_g1_r1", true);
                At(Clock + 16); Tick();
                CallCE("RoomExit");
            }
            // the drop counters' constants against the layout's names (A1)
            var names = typeof(CombatEvidenceCore).GetField("DROP_FIELDS", All);
            if (names != null)
            {
                var dn = (string[])names.GetValue(null);
                int ok = 0, bad = 0;
                foreach (var f in CE.GetFields(All))
                {
                    if (!f.Name.StartsWith("D_", StringComparison.Ordinal) || !f.IsLiteral) continue;
                    int v = (int)f.GetRawConstantValue();
                    string want = f.Name.Substring(2).ToLowerInvariant();
                    if (v >= 0 && v < dn.Length && dn[v] == want) ok++;
                    else { bad++; Out.Add("ERR drop constant " + f.Name + " = " + v + " is not " + want); }
                }
                Out.Add("DROPIX " + ok + " " + bad + " " + dn.Length);
            }
            var calls = CE.GetField("_calls", All); var faults = CE.GetField("_faults", All);
            if (calls != null && faults != null)
            {
                var c = (long[])calls.GetValue(null); var fl = (long[])faults.GetValue(null);
                for (int i = 0; i < c.Length; i++) Out.Add("COST " + i + " " + c[i] + " " + fl[i]);
            }
            foreach (var e in SeatEvidence.Queued) Out.Add("ENV " + e);
            foreach (var l in Plugin.Log.Lines) Out.Add("LOG " + l);
            using (var sha = SHA256.Create())
                Out.Add("DIGEST " + BitConverter.ToString(sha.ComputeHash(Encoding.UTF8.GetBytes(Witness.ToString()))).Replace("-", "").ToLowerInvariant());
            File.WriteAllLines(path, Out);
            return 0;
        }
    }
}
