using System;
using System.Collections.Generic;
using System.Globalization;
using System.Text;

namespace CompetitiveRounds
{
    /// <summary>Ask 15: the admin menu's layout rules executed by the client
    /// harness as suite "adminmenu". Every case prints its measurement in got=,
    /// so a wrong width, a row over budget, a missing translation or a wrong
    /// colour slot is red by its value, not only by PASS/FAIL. The catalogues
    /// come from I18nCatalogues.cs through the harness's I18n stub, so the width
    /// and packing cases run over English and the four locales.</summary>
    internal static partial class AdminMenuRules
    {
        internal sealed class SelfTestResult
        {
            internal int Passed;
            internal int Failed;
            internal readonly StringBuilder Report = new StringBuilder();
        }

        private static readonly string[] Locales = { "en", "es", "ru", "uk", "sv" };

        /// <summary>Translations that legitimately equal the English key.</summary>
        private static bool SameAsEnglishAllowed(string locale, string key)
        {
            return (locale == "es" && key == "Chat") || (locale == "sv" && key == "Server");
        }

        internal static SelfTestResult SelfTest()
        {
            var r = new SelfTestResult();
            I18nCatalogues.Install();
            string savedLocale = I18n.HarnessLocale;
            try
            {
                I18n.HarnessLocale = "en";

                // 1. Advances: the rule of thumb and its scaling.
                string adv = F(Advance('A', 13)) + "," + F(Advance('Ж', 13)) + "," + F(Advance('.', 13)) + "," + F(Advance(' ', 13)) + "," + F(Advance('A', 11));
                Check(r, "width: a Latin glyph is 8.5 px at 13 pt, Cyrillic 9.5, a period or space 4.5, and 11 pt scales by 11/13",
                    adv == "8.5,9.5,4.5,4.5,7.19", adv);

                // 2. Button widths: text plus 2 x 10 px padding, rounded up to 5, floored.
                string widths = LauncherWidth("Refresh") + "," + LauncherWidth("Ban Steam ID...") + "," + LauncherWidth("Delete Chat Message...") + "," + VerdictWidth("Accept") + "," + VerdictWidth("Discard") + "," + VerdictWidth("Отклонить");
                Check(r, "width: Refresh floors at 90, Ban Steam ID... is 130, Delete Chat Message... 190; at the 12 pt a verdict is drawn at, Accept is 70, Discard 75, a nine-letter Cyrillic verdict 100",
                    widths == "90,130,190,70,75,100", widths);

                // 3. Shared verdict widths: the widest of the set, never below the floor.
                string shared = SharedVerdictWidth(new[] { "Accept", "Discard" }) + "," + SharedVerdictWidth(new[] { "Void" }) + "," + SharedVerdictWidth(new string[0]);
                Check(r, "width: verdicts that sit together share the widest width (Accept+Discard 75), a lone short one floors at 70, an empty set floors at 70",
                    shared == "75,70,70", shared);

                // 4. Packing: the budget boundary, inclusive.
                string pack = Rows(PackRows(new[] { 600, 600, 600, 100 }, 8, 1812)) + "|" + Rows(PackRows(new[] { 900, 904 }, 8, 1812)) + "|" + Rows(PackRows(new[] { 900, 905 }, 8, 1812)) + "|" + Rows(PackRows(new int[0], 8, 1812));
                Check(r, "pack: 600+8+600+8+600 overruns 1812 so the third starts row 2; 900+8+904 is exactly 1812 and stays; 900+8+905 wraps; an empty set has no rows",
                    pack == "0,0,1,1|0,0|0,1|", pack);

                // 5. Widest row and Fits.
                int[] w5 = { 600, 600, 600, 100 };
                string fit = WidestRow(w5, PackRows(w5, 8, 1812), 8) + "," + RowCount(PackRows(w5, 8, 1812)) + "," + Fits(w5, 8, 1812) + "," + Fits(new[] { 2000 }, 8, 1812) + "," + WidestRow(new[] { 2000 }, PackRows(new[] { 2000 }, 8, 1812), 8);
                Check(r, "pack: the widest packed row is 1208 over 2 rows and fits; a 2000 px button has its own row, is 2000 wide and does not fit",
                    fit == "1208,2,True,False,2000", fit);

                // 6. The table: ids are main's, each id once, labels end in the launcher's ellipsis.
                var ids = new HashSet<string>(StringComparer.Ordinal);
                bool dupId = false, badEllipsis = false;
                for (int i = 0; i < Launchers.Length; i++)
                {
                    if (!ids.Add(Launchers[i].Id)) dupId = true;
                    if (!Launchers[i].Label.EndsWith("...", StringComparison.Ordinal)) badEllipsis = true;
                }
                Check(r, "table: 19 packed launchers with distinct ids and every label ending in ..., plus 4 header launchers and 8 verdicts",
                    Launchers.Length == 19 && !dupId && !badEllipsis && HeaderLaunchers.Length == 4 && Verdicts.Length == 8,
                    "launchers=" + Launchers.Length + " dupId=" + dupId + " badEllipsis=" + badEllipsis + " header=" + HeaderLaunchers.Length + " verdicts=" + Verdicts.Length);

                // 6b. The lookups NativeUI builds from: a launcher by its id, a group's scope.
                var byId = LauncherById("AMutes");
                string lookups = (byId == null ? "null" : byId.Label) + "," + (LauncherById("nope") == null)
                    + "," + GroupIsAdminOnly(Group.Chat) + "," + GroupIsAdminOnly(Group.Accounts) + "," + GroupIsAdminOnly(Group.Server) + "," + GroupIsAdminOnly(Group.Queues);
                Check(r, "table: AMutes looks up to Unmute Player... and an unknown id to null; Chat is the one group a moderator shares, Players, Server and Queues hide whole",
                    lookups == "Unmute Player...,True,False,True,True,True", lookups);

                // 7. Groups and pages in display order.
                string groups = string.Join(",", GroupNames(ActionsGroups)) + "=" + string.Join(",", GroupCaptions) + "|" + PageOf(Group.Chat) + "," + PageOf(Group.Accounts) + "," + PageOf(Group.Server) + "," + PageOf(Group.Queues);
                Check(r, "layout: the Actions page is Chat, Players, Server in that order and Queues is the second page's only group",
                    groups == "Chat,Accounts,Server=Chat,Players,Server|Actions,Actions,Actions,Queues", groups);
                string chat = Labels(GroupLaunchers(Group.Chat, true));
                string players = Labels(GroupLaunchers(Group.Accounts, true));
                string server = Labels(GroupLaunchers(Group.Server, true));
                string queues = Labels(GroupLaunchers(Group.Queues, true));
                Check(r, "layout: Chat is Mute Player, Mute From Message, Delete Chat Message, Unmute Player, Chat Lockdown",
                    chat == "Mute Player...;Mute From Message...;Delete Chat Message...;Unmute Player...;Chat Lockdown...", chat);
                Check(r, "layout: Players is Ban Steam ID, Grant Achievement, Grant Artist, Revoke Artist, Grant Translator, Revoke Translator",
                    players == "Ban Steam ID...;Grant Achievement...;Grant Artist...;Revoke Artist...;Grant Translator...;Revoke Translator...", players);
                Check(r, "layout: Server is Server Alert, End Alert, Admin Roster, Action Log; Queues is Bug Reports, Player Reports, Cosmetic Reviews, Approved Update Queue",
                    server == "Server Alert...;End Alert...;Admin Roster...;Action Log..." && queues == "Bug Reports...;Player Reports...;Cosmetic Reviews...;Approved Update Queue...",
                    server + " | " + queues);

                // 8. Who sees what: a moderator keeps main's four chat buttons and no bar.
                string modChat = Labels(GroupLaunchers(Group.Chat, false));
                int modOthers = GroupLaunchers(Group.Accounts, false).Length + GroupLaunchers(Group.Server, false).Length + GroupLaunchers(Group.Queues, false).Length;
                Check(r, "scope: a moderator sees Mute Player, Mute From Message, Delete Chat Message and Unmute Player, nothing else, one page and no bar; an admin sees two pages and the bar",
                    modChat == "Mute Player...;Mute From Message...;Delete Chat Message...;Unmute Player..." && modOthers == 0
                    && VisiblePages(false) == 1 && !PageBarShown(false) && VisiblePages(true) == 2 && PageBarShown(true),
                    "moderator=" + modChat + " others=" + modOthers + " pages=" + VisiblePages(false) + "/" + VisiblePages(true) + " bar=" + PageBarShown(false) + "/" + PageBarShown(true));
                string clamp = ClampPage(1, false) + "," + ClampPage(1, true) + "," + ClampPage(0, true) + "," + ClampPage(7, true);
                Check(r, "scope: a moderator is always on page 0; an admin keeps page 1 and any other value is page 0",
                    clamp == "0,1,0,0", clamp);

                // 9. Colour slots: kind and state, four button colours.
                string tones = ToneFor(Kind.Launcher, true) + "," + ToneFor(Kind.Positive, true) + "," + ToneFor(Kind.Negative, true) + "," + ToneFor(Kind.Positive, false) + "," + ToneFor(Kind.Launcher, false) + "," + ToneFor(Kind.Nav, true) + "," + NavTone(true) + "," + NavTone(false);
                Check(r, "colour: a launcher is Launcher, a positive verdict Positive, a negative one Negative, any disabled button Disabled, navigation Nav or NavActive",
                    tones == "Launcher,Positive,Negative,Disabled,Disabled,Nav,NavActive,Nav", tones);
                string kinds = KindOfVerdict("Accept") + "," + KindOfVerdict("Discard") + "," + KindOfVerdict("Details") + "," + KindOfVerdict("Unban") + "," + KindOfVerdict("Win T1") + "," + KindOfVerdict("Win T2") + "," + KindOfVerdict("Void Series") + "," + KindOfVerdict("Reverse") + "," + KindOfVerdict("nothing");
                Check(r, "colour: Accept, Unban, Win T1 and Win T2 are Positive; Discard, Void Series and Reverse Negative; Details and an unknown label Launcher",
                    kinds == "Positive,Negative,Launcher,Positive,Positive,Positive,Negative,Negative,Launcher", kinds);

                // 10. Every locale: each group packs within the budget in at most two rows.
                var over = new StringBuilder();
                var widest = new StringBuilder();
                foreach (var loc in Locales)
                {
                    I18n.HarnessLocale = loc;
                    foreach (var g in new[] { Group.Chat, Group.Accounts, Group.Server, Group.Queues })
                    {
                        var ls = GroupLaunchers(g, true);
                        var ws = new int[ls.Length];
                        for (int i = 0; i < ls.Length; i++) ws[i] = LauncherWidth(I18n.Tr(ls[i].Label));
                        var rows = PackRows(ws, RowSpacing, ContentWidth);
                        int wr = WidestRow(ws, rows, RowSpacing);
                        if (wr > ContentWidth || RowCount(rows) > 2) over.Append(loc).Append(':').Append(g).Append(' ');
                        if (g == Group.Accounts) widest.Append(loc).Append('=').Append(wr).Append(' ');
                    }
                }
                Check(r, "fit: in every locale each group packs within 1812 px in at most two rows (the Players row's width per locale printed)",
                    over.Length == 0, over.Length == 0 ? widest.ToString().TrimEnd() : "over: " + over.ToString().TrimEnd());

                // 10b. Every locale and page: the widest translated label, named with its width.
                var longest = new StringBuilder();
                bool longOk = true;
                foreach (var loc in Locales)
                {
                    I18n.HarnessLocale = loc;
                    foreach (var pg in new[] { Page.Actions, Page.Queues })
                    {
                        var labels = new List<string>();
                        for (int i = 0; i < Launchers.Length; i++)
                            if (PageOf(Launchers[i].Group) == pg) labels.Add(I18n.Tr(Launchers[i].Label));
                        double tw; string lab = WidestLabel(labels, LauncherPt, out tw);
                        int bw = LauncherWidth(lab);
                        if (bw < tw + 2 * HPad || bw > 400) longOk = false;
                        longest.Append(loc).Append('/').Append(pg).Append(": \"").Append(lab).Append("\" ").Append(F(tw)).Append("->").Append(bw).Append("; ");
                    }
                }
                Check(r, "fit: on each page in each locale the widest translated label gets a button at least its text plus padding and at most 400 px (each named with text width -> button width)",
                    longOk, longest.ToString().TrimEnd());

                // 10c. The page labels fit their fixed 180 px tabs in every locale.
                var tabs = new StringBuilder();
                bool tabsOk = true;
                foreach (var loc in Locales)
                {
                    I18n.HarnessLocale = loc;
                    foreach (var pl in PageLabels)
                    {
                        string t = I18n.Tr(pl);
                        if (!PageLabelFits(t)) tabsOk = false;
                        tabs.Append(loc).Append(':').Append(t).Append('=').Append(F(TextWidth(t, PageTabPt) + 2 * HPad)).Append(' ');
                    }
                }
                Check(r, "fit: Actions and Queues fit their 180 px page tabs at 14 pt in every locale (text plus padding per locale printed)",
                    tabsOk, tabs.ToString().TrimEnd());

                // 11. Every locale: the verdict columns stay narrow enough for their rows.
                var vw = new StringBuilder();
                bool vOk = true;
                foreach (var loc in Locales)
                {
                    I18n.HarnessLocale = loc;
                    var q = new List<string>(); foreach (var v in QuarantineVerdicts) q.Add(I18n.Tr(v));
                    var s = new List<string>(); foreach (var v in SeriesVerdicts) s.Add(I18n.Tr(v));
                    int qw = SharedVerdictWidth(q), sw = SharedVerdictWidth(s);
                    if (qw > 140 || sw > 140) vOk = false;
                    vw.Append(loc).Append('=').Append(qw).Append('/').Append(sw).Append(' ');
                }
                Check(r, "fit: in every locale the quarantine and series verdict widths stay at or under 140 px (quarantine/series per locale printed)",
                    vOk, vw.ToString().TrimEnd());

                // 12. Every key is in every catalogue.
                var missing = new StringBuilder();
                int sameCount = 0;
                foreach (var loc in Locales)
                {
                    if (loc == "en") continue;
                    I18n.HarnessLocale = loc;
                    foreach (var key in AllKeys())
                    {
                        string t = I18n.Tr(key);
                        if (string.IsNullOrEmpty(t) || (t == key && !SameAsEnglishAllowed(loc, key))) missing.Append(loc).Append(':').Append(key).Append("; ");
                        else if (t == key) sameCount++;
                    }
                }
                Check(r, "i18n: every launcher, header-launcher, verdict, page and caption key has a translation in es, ru, uk and sv (allowed to equal English: es Chat, sv Server)",
                    missing.Length == 0, missing.Length == 0 ? "keys=" + AllKeys().Count + " sameAsEnglish=" + sameCount : missing.ToString().TrimEnd());
            }
            finally { I18n.HarnessLocale = savedLocale; }
            return r;
        }

        internal static List<string> AllKeys()
        {
            var keys = new List<string>();
            for (int i = 0; i < Launchers.Length; i++) keys.Add(Launchers[i].Label);
            keys.AddRange(HeaderLaunchers);
            for (int i = 0; i < Verdicts.Length; i++) keys.Add(Verdicts[i].Label);
            keys.AddRange(PageLabels);
            keys.AddRange(GroupCaptions);
            return keys;
        }

        private static string F(double v) { return Math.Round(v, 2).ToString(CultureInfo.InvariantCulture); }
        private static string Rows(int[] rows) { var sb = new StringBuilder(); for (int i = 0; i < rows.Length; i++) { if (i > 0) sb.Append(','); sb.Append(rows[i]); } return sb.ToString(); }
        private static string Labels(Launcher[] ls) { var sb = new StringBuilder(); for (int i = 0; i < ls.Length; i++) { if (i > 0) sb.Append(';'); sb.Append(ls[i].Label); } return sb.ToString(); }
        private static string[] GroupNames(Group[] gs) { var a = new string[gs.Length]; for (int i = 0; i < gs.Length; i++) a[i] = gs[i].ToString(); return a; }

        private static void Check(SelfTestResult r, string name, bool ok, string got)
        {
            if (ok) r.Passed++; else r.Failed++;
            r.Report.Append(ok ? "PASS" : "FAIL").Append(" | case=").Append(name).Append(" | got=").Append(got).Append('\n');
        }
    }
}
