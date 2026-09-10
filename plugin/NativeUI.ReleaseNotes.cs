using UnityEngine;

namespace CompetitiveRounds
{
    public static partial class NativeUI
    {
        private static GameObject releaseNotesRoot;
        private static string releaseNotesFingerprint;
        internal static bool ReleaseNotesOpen => releaseNotesRoot != null && releaseNotesRoot.activeSelf;

        private static string ReleaseNotesPreferenceKey => "CompetitiveRounds.ReleaseNotesDismissed." + MatchTracker.LocalSteamId;

        private static void BuildReleaseNotesModal()
        {
            releaseNotesFingerprint = null;
            releaseNotesRoot = UIFactory.CreatePanel("ReleaseNotesModal", pageGO.transform, new Color(0, 0, 0, 0.75f));
            var box = UIFactory.CreatePanel("ReleaseNotesBox", releaseNotesRoot.transform, C_PANEL);
            var rt = box.GetComponent<RectTransform>();
            rt.anchorMin = new Vector2(0.18f, 0.12f); rt.anchorMax = new Vector2(0.82f, 0.88f);
            rt.offsetMin = rt.offsetMax = Vector2.zero;
            UIFactory.AddVLG(box, spacing: 12, padL: 20, padR: 20, padT: 16, padB: 16);
            var header = LayoutRow("ReleaseNotesHeader", box.transform, 36);
            var title = UIFactory.CreateText("ReleaseNotesTitle", header.transform, "Latest release notes", 22, C_GOLD,
                sizeDelta: new Vector2(0, 34));
            SetSectionWidth((title as Component).gameObject, 0, 0, 1);
            UIFactory.CreateButton("HideReleaseNotes", header.transform, "Hide", 16, C_WHITE, C_BTN,
                DismissReleaseNotes, new Vector2(100, 32));
            var scroll = UIFactory.CreateScrollView("ReleaseNotesScroll", box.transform, spacing: 0);
            UIFactory.AddLE(scroll.scrollGO, flexH: 1);
            txtHomeReleases = UIFactory.CreateText("ReleaseNotesText", scroll.content.transform,
                "Loading release notes...", 16, C_WHITE, UIFactory.AlignTopLeft, sizeDelta: new Vector2(0, 24));
            UIFactory.SetWordWrap(txtHomeReleases, true);
            UIFactory.SetTextAutoHeight(txtHomeReleases);
            var textRT = (txtHomeReleases as Component).GetComponent<RectTransform>();
            textRT.anchorMin = new Vector2(0, textRT.anchorMin.y);
            textRT.anchorMax = new Vector2(1, textRT.anchorMax.y);
            textRT.offsetMin = new Vector2(0, textRT.offsetMin.y);
            textRT.offsetMax = new Vector2(0, textRT.offsetMax.y);
            var backdrop = releaseNotesRoot.AddComponent<ClickHandler>();
            backdrop.bypassModalBlock = true;
            backdrop.onClick = () =>
            {
                if (!PointerInsideRect(rt) && ClickGuard.Claim(releaseNotesRoot)) DismissReleaseNotes();
            };
            MarkPopupChildrenInteractive(releaseNotesRoot);
            releaseNotesRoot.SetActive(false);
        }

        private static void OpenReleaseNotes()
        {
            if (releaseNotesRoot == null || CompetitiveUI.OtherModalOwnsInput || UtilityPopupOpen) return;
            releaseNotesRoot.SetActive(true);
            releaseNotesRoot.transform.SetAsLastSibling();
        }

        private static void MaybeOpenReleaseNotes()
        {
            // Loading/failure placeholders are never treated as a new release.
            var sid = MatchTracker.LocalSteamId;
            if (!isOpen || currentTab != TAB_HOME || ReleaseNotesOpen || string.IsNullOrEmpty(releaseNotesFingerprint)
                || string.IsNullOrEmpty(sid) || sid == "unknown" || CompetitiveUI.MenuNavigationBlocked) return;
            if (PlayerPrefs.GetString(ReleaseNotesPreferenceKey, "") != releaseNotesFingerprint) OpenReleaseNotes();
        }

        private static void DismissReleaseNotes()
        {
            var sid = MatchTracker.LocalSteamId;
            if (!string.IsNullOrEmpty(releaseNotesFingerprint) && !string.IsNullOrEmpty(sid) && sid != "unknown")
            {
                PlayerPrefs.SetString(ReleaseNotesPreferenceKey, releaseNotesFingerprint);
                PlayerPrefs.Save();
            }
            HideReleaseNotes();
        }

        // Closing the whole page does not acknowledge unread notes.
        private static void HideReleaseNotes()
        {
            if (releaseNotesRoot != null) releaseNotesRoot.SetActive(false);
        }
    }
}
