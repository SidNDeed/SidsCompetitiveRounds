using System;
using UnityEngine;

namespace CompetitiveRounds
{
    /// <summary>
    /// Stage 2 S2, the banner: a non-modal strip in the top-centre column
    /// (CompetitiveUI.ClaimTopStrip), drawn from the persistent host's OnGUI.
    /// It never takes input: Esc still opens the menu, whose leave runs the
    /// expiry first. Texts are TrF literals (KX7 regenerates the key pair).
    /// </summary>
    internal static class TeamHoldBanner
    {
        internal const double EndedShowS = 6;

        private static GUIStyle _style;
        private static string _text;
        private static float _width;

        /// <summary>The line for this frame, or null.</summary>
        internal static string Line(double now)
        {
            var cut = TeamHold.Cut;
            char state = TeamHoldLoop.Shown;
            if (cut == null)
            {
                if (now - TeamHoldLoop.EndedAt > EndedShowS) return null;
                string name = TeamHoldLoop.EndedName ?? "";
                if (state == 'e') return I18n.TrF("{0} is back", name);
                if (TeamHoldLoop.EndedBySecond) return I18n.Tr("Another player left. The match ends as a disconnect.");
                return I18n.TrF("{0} did not return. The match ends as a disconnect.", name);
            }
            string who = cut.Name ?? "";
            switch (state)
            {
                case 'p': return I18n.TrF("Checking whether {0} can rejoin", who);
                case 'o':
                {
                    int left = Math.Max(0, (int)Math.Ceiling(TeamHoldLoop.DeadlineAt - now));
                    return I18n.TrF("Seat held for {0}: {1}", who, left) + "  " + I18n.Tr("Press Esc to leave. The match then ends as a disconnect.");
                }
                case 'c':
                case 'b': return I18n.TrF("{0} is rejoining", who);
                default: return null;
            }
        }

        /// <summary>From the host's OnGUI, after CompetitiveUI.DrawUI.</summary>
        internal static void Draw()
        {
            try
            {
                if (Event.current == null) return;
                string text = Line(Time.unscaledTime);
                if (string.IsNullOrEmpty(text)) return;
                if (_style == null)
                {
                    _style = new GUIStyle(GUI.skin.label) { alignment = TextAnchor.MiddleCenter, fontStyle = FontStyle.Bold, fontSize = 15 };
                    _style.normal.textColor = Color.white;
                }
                // CalcSize on change only, never per Repaint (#162).
                if (!string.Equals(text, _text, StringComparison.Ordinal))
                {
                    _text = text;
                    _width = _style.CalcSize(new GUIContent(text)).x + 30f;
                }
                const float barH = 26f;
                float w = Mathf.Min(_width, Screen.width - 8f);
                float x = (Screen.width - w) / 2f;
                float y = CompetitiveUI.ClaimTopStrip(barH);
                var prev = GUI.color;
                try
                {
                    GUI.color = new Color(0.30f, 0.22f, 0.06f, 0.85f);
                    GUI.DrawTexture(new Rect(x, y, w, barH), Texture2D.whiteTexture, ScaleMode.StretchToFill);
                    GUI.color = Color.white;
                    GUI.Label(new Rect(x, y, w, barH), text, _style);
                }
                finally { GUI.color = prev; }
            }
            catch { }
        }
    }
}
