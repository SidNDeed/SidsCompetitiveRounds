#if SCR_FRAMETIME
using System;
using System.Collections;
using System.Collections.Generic;
using System.Reflection;
using HarmonyLib;

namespace CompetitiveRounds
{
    /// <summary>Ruling R6-A3.11.151 (3), the attach line, printed once by Plugin.Awake after its patch loop:
    /// `[FRAME-TIME] attach n=&lt;a&gt; of=&lt;b&gt; missing=&lt;none|Name,...&gt; names=&lt;Name:got/want,...&gt;`.
    /// The entries are found by reflection over this assembly, never from a table: every type that carries a
    /// class-level [HarmonyPatch] (the patch loop's own selector) and whose own name, or the name of a class it is
    /// nested in, starts with "Ft" (the prefix every patch class in plugin/Ft*.cs carries). A patch class added under
    /// that prefix is therefore an entry in the next build's line with no list here to update; a patch class named
    /// otherwise is no entry. Each build prints the classes it compiles: at this file's writing ten in FrameTime and
    /// nine in the reference build (SCR_FT_NOCOLLECTORS), which does not compile FtSockPatch.
    /// want = the class's patch methods times its distinct targets, both read from the class's own declaration:
    /// its methods named Prefix, Postfix, Transpiler or Finalizer or marked with that kind's attribute, and its targets
    /// from TargetMethods, else TargetMethod, else its class-level [HarmonyPatch] attributes (the order the patch
    /// loop's class processor uses). Harmony's patch table is not read for want. got = the (target, patch method)
    /// pairs that Harmony's patch table lists in that patch method's own kind, under this plugin's Harmony id
    /// (Plugin.ModId), matched by module and metadata token (the test of FtPhoton.Count). A class whose targets do not
    /// resolve, or whose declaration this reader does not count (see Uncounted), is printed as got 0 and want 0, so it
    /// lands in missing. n counts the entries with got equal to want and want above zero; names stand in ordinal
    /// order. A printed name is the type's name, prefixed by the names of the classes it is nested in and an
    /// underscore each, with every character other than a letter, a digit or the underscore written as an underscore.</summary>
    internal static class FtAttach
    {
        private const BindingFlags All = BindingFlags.Static | BindingFlags.Instance | BindingFlags.Public
            | BindingFlags.NonPublic | BindingFlags.DeclaredOnly;

        /// <summary>The patch kinds counted, in the order Harmony assigns a kind to a method (name or attribute, the
        /// first kind that matches), and each kind's attribute.</summary>
        private static readonly string[] Kinds = { "Prefix", "Postfix", "Transpiler", "Finalizer" };
        private static readonly Type[] KindAttrs = { typeof(HarmonyPrefix), typeof(HarmonyPostfix), typeof(HarmonyTranspiler), typeof(HarmonyFinalizer) };

        internal static void Report()
        {
            var types = new List<KeyValuePair<string, Type>>();
            foreach (Type t in Assembly.GetExecutingAssembly().GetTypes())
            {
                if (!Measuring(t)) continue;
                object[] attrs = t.GetCustomAttributes(typeof(HarmonyPatch), true);
                if (attrs == null || attrs.Length == 0) continue;
                types.Add(new KeyValuePair<string, Type>(NameOf(t), t));
            }
            types.Sort((a, b) => string.CompareOrdinal(a.Key, b.Key));
            int n = 0;
            var missing = new List<string>();
            var names = new List<string>();
            foreach (var kv in types)
            {
                int got, want;
                try { Measure(kv.Value, out got, out want); }
                catch { got = 0; want = 0; }
                names.Add(kv.Key + ":" + got + "/" + want);
                if (want > 0 && got == want) n++; else missing.Add(kv.Key);
            }
            Plugin.Log.LogInfo("[FRAME-TIME] attach n=" + n + " of=" + types.Count + " missing="
                + (missing.Count == 0 ? "none" : string.Join(",", missing.ToArray())) + " names=" + string.Join(",", names.ToArray()));
        }

        private static bool Measuring(Type t)
        {
            for (Type x = t; x != null; x = x.DeclaringType)
                if (x.Name.StartsWith("Ft", StringComparison.Ordinal)) return true;
            return false;
        }

        private static string NameOf(Type t)
        {
            string s = t.Name;
            for (Type d = t.DeclaringType; d != null; d = d.DeclaringType) s = d.Name + "_" + s;
            var c = s.ToCharArray();
            for (int i = 0; i < c.Length; i++)
            {
                char ch = c[i];
                bool ok = (ch >= 'A' && ch <= 'Z') || (ch >= 'a' && ch <= 'z') || (ch >= '0' && ch <= '9') || ch == '_';
                if (!ok) c[i] = '_';
            }
            return new string(c);
        }

        /// <summary>want from the declaration; got from Harmony's patch table. Both 0 when the targets do not resolve
        /// or the declaration is uncounted.</summary>
        private static void Measure(Type t, out int got, out int want)
        {
            got = 0;
            want = 0;
            if (Uncounted(t)) return;
            var methods = new List<KeyValuePair<int, MethodInfo>>();
            foreach (MethodInfo m in t.GetMethods(All))
            {
                int k = KindOf(m);
                if (k >= 0) methods.Add(new KeyValuePair<int, MethodInfo>(k, m));
            }
            List<MethodBase> targets = Targets(t);
            if (targets == null) return;
            want = methods.Count * targets.Count;
            foreach (MethodBase target in targets)
            {
                HarmonyLib.Patches info = null;
                try { info = Harmony.GetPatchInfo(target); }
                catch { info = null; }
                if (info == null) continue;
                foreach (var pm in methods)
                    if (Listed(Group(info, pm.Key), pm.Value)) got++;
            }
        }

        private static int KindOf(MethodInfo m)
        {
            for (int i = 0; i < Kinds.Length; i++)
                if (m.Name == Kinds[i] || m.IsDefined(KindAttrs[i], true)) return i;
            return -1;
        }

        private static IEnumerable<Patch> Group(HarmonyLib.Patches info, int kind)
        {
            switch (kind)
            {
                case 0: return info.Prefixes;
                case 1: return info.Postfixes;
                case 2: return info.Transpilers;
                default: return info.Finalizers;
            }
        }

        private static bool Listed(IEnumerable<Patch> group, MethodInfo m)
        {
            if (group == null) return false;
            foreach (Patch p in group)
                if (p != null && p.owner == Plugin.ModId && p.PatchMethod != null && p.PatchMethod.Module == m.Module
                    && p.PatchMethod.MetadataToken == m.MetadataToken) return true;
            return false;
        }

        /// <summary>Declarations this reader does not count, each of which would make want differ from what the
        /// class processor attaches: a class-level HarmonyPatchAll, a patch method with its own [HarmonyPatch]
        /// (a per-method target), and a reverse patch or an IL manipulator (kinds outside Kinds).</summary>
        private static bool Uncounted(Type t)
        {
            if (HasAttr(t.GetCustomAttributes(true), "HarmonyLib.HarmonyPatchAll")) return true;
            foreach (MethodInfo m in t.GetMethods(All))
            {
                if (m.Name == "ReversePatch" || m.Name == "ILManipulator") return true;
                object[] a = m.GetCustomAttributes(true);
                if (HasAttr(a, "HarmonyLib.HarmonyReversePatch") || HasAttr(a, "HarmonyLib.HarmonyILManipulator")) return true;
                if (KindOf(m) >= 0 && m.GetCustomAttributes(typeof(HarmonyPatch), true).Length > 0) return true;
            }
            return false;
        }

        private static bool HasAttr(object[] attrs, string fullName)
        {
            if (attrs == null) return false;
            foreach (object a in attrs)
                if (a != null && a.GetType().FullName == fullName) return true;
            return false;
        }

        /// <summary>The class's distinct targets, or null when they do not resolve: TargetMethods (an aux method
        /// found by its attribute, else by its name), else TargetMethod, else the class-level attributes merged in
        /// order, a later value over an earlier one. An aux method that takes parameters, returns null, returns a
        /// null element or throws is a target set that does not resolve.</summary>
        private static List<MethodBase> Targets(Type t)
        {
            var list = new List<MethodBase>();
            MethodInfo many = Aux(t, "TargetMethods");
            if (many != null)
            {
                if (many.GetParameters().Length != 0) return null;
                var r = many.Invoke(null, null) as IEnumerable;
                if (r == null) return null;
                foreach (object o in r)
                {
                    var mb = o as MethodBase;
                    if (mb == null) return null;
                    if (!list.Contains(mb)) list.Add(mb);
                }
                return list;
            }
            MethodInfo one = Aux(t, "TargetMethod");
            if (one != null)
            {
                if (one.GetParameters().Length != 0) return null;
                var mb = one.Invoke(null, null) as MethodBase;
                if (mb == null) return null;
                list.Add(mb);
                return list;
            }
            Type dt = null;
            string name = null;
            Type[] args = null;
            MethodType? kind = null;
            foreach (object a in t.GetCustomAttributes(typeof(HarmonyPatch), true))
            {
                var info = ((HarmonyPatch)a).info;
                if (info == null) continue;
                if (info.declaringType != null) dt = info.declaringType;
                if (info.methodName != null) name = info.methodName;
                if (info.argumentTypes != null) args = info.argumentTypes;
                if (info.methodType != null) kind = info.methodType;
            }
            if (dt == null) return null;
            MethodBase target = null;
            switch (kind ?? MethodType.Normal)
            {
                case MethodType.Normal:
                    if (name == null) return null;
                    target = AccessTools.DeclaredMethod(dt, name, args) ?? AccessTools.Method(dt, name, args);
                    break;
                case MethodType.Getter:
                    if (name == null) return null;
                    target = AccessTools.DeclaredPropertyGetter(dt, name) ?? AccessTools.PropertyGetter(dt, name);
                    break;
                case MethodType.Setter:
                    if (name == null) return null;
                    target = AccessTools.DeclaredPropertySetter(dt, name) ?? AccessTools.PropertySetter(dt, name);
                    break;
                case MethodType.Constructor:
                    target = AccessTools.DeclaredConstructor(dt, args);
                    break;
                default:
                    return null;
            }
            if (target == null) return null;
            list.Add(target);
            return list;
        }

        /// <summary>An aux method: the first method carrying HarmonyLib.Harmony&lt;name&gt;, else the one named name.</summary>
        private static MethodInfo Aux(Type t, string name)
        {
            string attr = "HarmonyLib.Harmony" + name;
            foreach (MethodInfo m in t.GetMethods(All))
                if (HasAttr(m.GetCustomAttributes(true), attr)) return m;
            foreach (MethodInfo m in t.GetMethods(All))
                if (m.Name == name) return m;
            return null;
        }
    }
}
#endif
