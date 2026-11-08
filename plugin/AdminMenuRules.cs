using System;
using System.Collections.Generic;

namespace CompetitiveRounds
{
    /// <summary>Ask 15: the admin menu's layout rules, Unity-free so the client
    /// harness can run them over every locale. What a button is for (its kind),
    /// where it sits (its group and page), who sees it, how wide its label makes
    /// it and how a group's buttons pack into rows are all decided here; NativeUI
    /// only draws the answer. Design: ai-collab/seat-b/ASK15-DESIGN.md.</summary>
    internal static partial class AdminMenuRules
    {
        /// <summary>What a click does. Colour follows the kind, never the thing
        /// (design section 4): a launcher opens a view, picker or prompt and
        /// commits nothing; a verdict commits in place after its confirm.</summary>
        internal enum Kind { Nav, Launcher, Positive, Negative }

        /// <summary>The colour slot a button wears; NativeUI maps each to one
        /// constant. Exactly four slots are button colours (Launcher, Positive,
        /// Negative, Disabled); Nav and NavActive are the page bar's.</summary>
        internal enum Tone { Nav, NavActive, Launcher, Positive, Negative, Disabled }

        internal enum Group { Chat, Players, Server, Queues }
        internal enum Page { Actions, Queues }

        internal sealed class Launcher
        {
            internal readonly string Id;      // the GameObject name, unchanged from main
            internal readonly string Label;   // the I18n key, as CreateButton translates it
            internal readonly Group Group;
            internal readonly bool ModeratorVisible;
            internal Launcher(string id, string label, Group group, bool moderatorVisible)
            { Id = id; Label = label; Group = group; ModeratorVisible = moderatorVisible; }
        }

        internal sealed class Verdict
        {
            internal readonly string Label;
            internal readonly Kind Kind;
            internal Verdict(string label, Kind kind) { Label = label; Kind = kind; }
        }

        // ---- geometry -----------------------------------------------------

        /// <summary>The Admin panel's row budget: the ~1828 px an HLG gets at the
        /// 1920-unit canvas (NativeUI's own figure) minus the panel's 8+8 padding.</summary>
        internal const int ContentWidth = 1812;
        internal const int RowSpacing = 8;
        internal const int LauncherPt = 13;
        internal const int VerdictPt = 11;
        internal const int LauncherFloor = 90;
        internal const int VerdictFloor = 70;
        internal const int HPad = 10;          // each side, inside the button
        internal const int VerdictColumnPad = 4;
        /// <summary>The page bar's two buttons: half an outer sub-tab button (360).</summary>
        internal const int PageTabWidth = 180;
        internal const int PageTabPt = 14;

        /// <summary>A page label fits its fixed tab when its text and padding do.</summary>
        internal static bool PageLabelFits(string label) { return TextWidth(label, PageTabPt) + 2 * HPad <= PageTabWidth; }

        /// <summary>The launcher of a set whose translated label is widest, for the
        /// harness to name per locale and page; null for an empty set.</summary>
        internal static string WidestLabel(IList<string> labels, int pt, out double width)
        {
            width = 0; string best = null;
            if (labels == null) return null;
            for (int i = 0; i < labels.Count; i++)
            {
                double w = TextWidth(labels[i], pt);
                if (best == null || w > width) { best = labels[i]; width = w; }
            }
            return best;
        }

        /// <summary>A glyph's advance at 13 pt for the BOLD face, which every text
        /// this mod draws defaults to: the code's own ~8 px average for Gravity at
        /// that size plus headroom; Cyrillic wider, periods and spaces narrower.
        /// Scaled linearly for other sizes. A rule of thumb, not font metrics:
        /// the in-game check in every locale is the proof.</summary>
        internal static double Advance(char c, int pt)
        {
            double at13;
            if (c == '.' || c == ' ') at13 = 4.5;
            else if (c >= 'Ѐ' && c <= 'ӿ') at13 = 9.5;
            else at13 = 8.5;
            return at13 * pt / 13.0;
        }

        internal static double TextWidth(string label, int pt)
        {
            if (string.IsNullOrEmpty(label)) return 0;
            double w = 0;
            for (int i = 0; i < label.Length; i++) w += Advance(label[i], pt);
            return w;
        }

        /// <summary>The width a label needs: its text plus the padding, rounded up
        /// to 5 px, never below the floor.</summary>
        internal static int ButtonWidth(string label, int pt, int floor)
        {
            double need = TextWidth(label, pt) + 2 * HPad;
            int w = (int)Math.Ceiling(need / 5.0) * 5;
            return w < floor ? floor : w;
        }

        internal static int LauncherWidth(string label) { return ButtonWidth(label, LauncherPt, LauncherFloor); }
        internal static int VerdictWidth(string label) { return ButtonWidth(label, VerdictPt, VerdictFloor); }

        /// <summary>Verdicts that sit together share the widest of their widths,
        /// so a stacked or side-by-side pair stays even.</summary>
        internal static int SharedVerdictWidth(IList<string> labels)
        {
            int w = VerdictFloor;
            if (labels == null) return w;
            for (int i = 0; i < labels.Count; i++) { int v = VerdictWidth(labels[i]); if (v > w) w = v; }
            return w;
        }

        /// <summary>Greedy left-to-right packing: a button goes on the current row
        /// while the row, with the spacing, stays within the budget; otherwise it
        /// starts the next row. Returns each button's row index. A button wider
        /// than the budget gets a row of its own and Fits() reports it.</summary>
        internal static int[] PackRows(IList<int> widths, int spacing, int budget)
        {
            var rows = new int[widths == null ? 0 : widths.Count];
            int row = 0, used = 0;
            for (int i = 0; i < rows.Length; i++)
            {
                int w = widths[i];
                if (used > 0 && used + spacing + w > budget) { row++; used = 0; }
                used = used == 0 ? w : used + spacing + w;
                rows[i] = row;
            }
            return rows;
        }

        internal static int RowCount(int[] rows) { return rows == null || rows.Length == 0 ? 0 : rows[rows.Length - 1] + 1; }

        internal static int WidestRow(IList<int> widths, int[] rows, int spacing)
        {
            int best = 0, used = 0, cur = -1;
            for (int i = 0; i < rows.Length; i++)
            {
                if (rows[i] != cur) { cur = rows[i]; used = widths[i]; }
                else used += spacing + widths[i];
                if (used > best) best = used;
            }
            return best;
        }

        internal static bool Fits(IList<int> widths, int spacing, int budget)
        {
            return WidestRow(widths, PackRows(widths, spacing, budget), spacing) <= budget;
        }

        // ---- the table --------------------------------------------------------

        /// <summary>Every launcher on the two pages, in display order. Ids and the
        /// calls behind them are main's; only group, order and colour are new.
        /// Refresh (header row), Full Log (the log header) and Find &amp; Unban (the
        /// Banned tab's header) are launchers too but sit on header rows, so they
        /// are not packed here.</summary>
        internal static readonly Launcher[] Launchers = new[]
        {
            new Launcher("AMuteNew",  "Mute Player...",            Group.Chat,    true),
            new Launcher("AMuteMsg",  "Mute From Message...",      Group.Chat,    true),
            new Launcher("AChatDel",  "Delete Chat Message...",    Group.Chat,    true),
            new Launcher("AMutes",    "Unmute Player...",          Group.Chat,    true),
            new Launcher("ALockdown", "Chat Lockdown...",          Group.Chat,    false),
            new Launcher("ABan",      "Ban Steam ID...",           Group.Players, false),
            new Launcher("AGrant",    "Grant Achievement...",      Group.Players, false),
            new Launcher("AArtG",     "Grant Artist...",           Group.Players, false),
            new Launcher("AArtR",     "Revoke Artist...",          Group.Players, false),
            new Launcher("ATrG",      "Grant Translator...",       Group.Players, false),
            new Launcher("ATrR",      "Revoke Translator...",      Group.Players, false),
            new Launcher("AAlertNew", "Server Alert...",           Group.Server,  false),
            new Launcher("AAlertEnd", "End Alert...",              Group.Server,  false),
            new Launcher("AAdmins",   "Admin Roster...",           Group.Server,  false),
            new Launcher("AActions",  "Action Log...",             Group.Server,  false),
            new Launcher("ABugRpt",   "Bug Reports...",            Group.Queues,  false),
            new Launcher("ACosR",     "Cosmetic Reviews...",       Group.Queues,  false),
            new Launcher("ACosQ",     "Approved Update Queue...",  Group.Queues,  false),
        };

        /// <summary>The header-row launchers: the same kind and width rule, placed
        /// by their headers rather than packed.</summary>
        internal static readonly string[] HeaderLaunchers = { "Refresh", "Reverse Series...", "Full Log...", "Find and Unban..." };

        /// <summary>The per-row verdict buttons and their kinds.</summary>
        internal static readonly Verdict[] Verdicts = new[]
        {
            new Verdict("Accept",  Kind.Positive),
            new Verdict("Discard", Kind.Negative),
            new Verdict("Details", Kind.Launcher),
            new Verdict("Unban",   Kind.Positive),
            new Verdict("Win T1",  Kind.Positive),
            new Verdict("Win T2",  Kind.Positive),
            new Verdict("Void Series", Kind.Negative),
            new Verdict("Reverse", Kind.Negative),
        };

        internal static readonly string[] QuarantineVerdicts = { "Accept", "Discard" };
        internal static readonly string[] SeriesVerdicts = { "Win T1", "Win T2", "Void Series", "Reverse" };

        /// <summary>The Actions page's groups in display order; Queues is the
        /// second page's only group.</summary>
        internal static readonly Group[] ActionsGroups = { Group.Chat, Group.Players, Group.Server };

        internal static readonly string[] PageLabels = { "Actions", "Queues" };
        internal static readonly string[] GroupCaptions = { "Chat", "Players", "Server" };

        internal static Page PageOf(Group g) { return g == Group.Queues ? Page.Queues : Page.Actions; }

        // ---- who sees what ----------------------------------------------------

        /// <summary>A launcher is visible to an admin always and to a moderator
        /// only when the table says so: the moderator's set is main's four chat
        /// buttons, unchanged.</summary>
        internal static bool Visible(Launcher l, bool isAdmin) { return isAdmin || l.ModeratorVisible; }

        /// <summary>The Queues page and the Players and Server groups are admin
        /// scope, so a moderator has one visible page.</summary>
        internal static int VisiblePages(bool isAdmin) { return isAdmin ? 2 : 1; }

        /// <summary>The page bar shows only when there is a choice, the outer
        /// sub-tab bar's own rule.</summary>
        internal static bool PageBarShown(bool isAdmin) { return VisiblePages(isAdmin) >= 2; }

        /// <summary>The page a role may be on: a moderator is always on Actions.</summary>
        internal static int ClampPage(int page, bool isAdmin) { return isAdmin && page == 1 ? 1 : 0; }

        internal static Launcher[] GroupLaunchers(Group g, bool isAdmin)
        {
            var list = new List<Launcher>();
            for (int i = 0; i < Launchers.Length; i++)
                if (Launchers[i].Group == g && Visible(Launchers[i], isAdmin)) list.Add(Launchers[i]);
            return list.ToArray();
        }

        /// <summary>The table row NativeUI builds a button from, by the GameObject
        /// id main gave it; null for an id the table does not know.</summary>
        internal static Launcher LauncherById(string id)
        {
            for (int i = 0; i < Launchers.Length; i++) if (Launchers[i].Id == id) return Launchers[i];
            return null;
        }

        /// <summary>A group every launcher of which is admin scope hides as one
        /// block; Chat is the exception, hiding Chat Lockdown alone among the
        /// moderator's four.</summary>
        internal static bool GroupIsAdminOnly(Group g)
        {
            for (int i = 0; i < Launchers.Length; i++) if (Launchers[i].Group == g && Launchers[i].ModeratorVisible) return false;
            return true;
        }

        // ---- colour -----------------------------------------------------------

        /// <summary>Kind and state to colour slot: the shop's rule (one hue per
        /// kind, a state recolours it) applied to the admin menu.</summary>
        internal static Tone ToneFor(Kind kind, bool enabled)
        {
            if (!enabled) return Tone.Disabled;
            switch (kind)
            {
                case Kind.Positive: return Tone.Positive;
                case Kind.Negative: return Tone.Negative;
                case Kind.Nav: return Tone.Nav;
                default: return Tone.Launcher;
            }
        }

        internal static Tone NavTone(bool active) { return active ? Tone.NavActive : Tone.Nav; }

        internal static Kind KindOfVerdict(string label)
        {
            for (int i = 0; i < Verdicts.Length; i++) if (Verdicts[i].Label == label) return Verdicts[i].Kind;
            return Kind.Launcher;
        }
    }
}
