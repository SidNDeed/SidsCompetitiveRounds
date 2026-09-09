using System;
using UnityEngine;

namespace CompetitiveRounds
{
    public static partial class NativeUI
    {
        private static int historyKind, unifiedBoard, unifiedRecent, multiplayerSection, randomQueueMode;
        private static GameObject historyKindButton, historyRankedBody, historyRankedPager, historyCasualBody, historyCasualPager;
        private static GameObject[] unifiedBoards, unifiedRecents;
        private static GameObject unifiedDetail, boardSelector;
        private static GameObject lobbyListBody, randomQueueBody, randomSoloBody, randomTeamBody;
        private static GameObject lobbySectionButton, queueSectionButton, queueFilterButton;
        private static object randomSoloStatus;
        private static GameObject randomSoloJoin, randomSoloLeave;
        private static GameObject multiplayerActivity, teamQueueStatus;
        private static Transform teamQueueIdleParent;
        private static GameObject lobbyOptionsRoot, lobbyOptionsBox;
        private static GameObject[] lobbyOptionBodies;
        private static GameObject lobbyModeButton;
        private static int lobbyOptionsMode;
        internal static bool LobbyOptionsOpen => lobbyOptionsRoot != null && lobbyOptionsRoot.activeSelf;
        internal static bool RankedLeaderboardVisible => unifiedBoards != null && unifiedBoards[0] != null && unifiedBoards[0].activeInHierarchy;

        // Build once from the existing mode sections. Their rows, callbacks, and
        // server-owned state stay attached to the same objects when moved.
        private static GameObject LayoutColumn(string name, Transform parent, bool card = false)
        {
            var go = card ? UIFactory.CreatePanel(name, parent, C_PANEL) : new GameObject(name);
            if (!card) { go.transform.SetParent(parent, false); go.AddComponent<RectTransform>(); }
            UIFactory.AddVLG(go, spacing: 6, padL: card ? 10 : 0, padR: card ? 10 : 0,
                padT: card ? 8 : 0, padB: card ? 8 : 0);
            UIFactory.AddLE(go, flexH: 1, flexW: 1);
            return go;
        }

        private static GameObject LayoutRow(string name, Transform parent, float height = 34)
        {
            var go = new GameObject(name);
            go.transform.SetParent(parent, false); go.AddComponent<RectTransform>();
            UIFactory.AddHLG(go, spacing: 8);
            UIFactory.AddLE(go, prefH: height, minH: height, flexH: 0);
            return go;
        }

        private static GameObject Section(GameObject root, string name)
        {
            foreach (var rt in root.GetComponentsInChildren<RectTransform>(true))
                if (rt.name == name) return rt.gameObject;
            throw new InvalidOperationException("Missing menu section: " + name);
        }

        private static void MoveSection(GameObject go, Transform parent)
        {
            go.transform.SetParent(parent, false);
        }

        private static void FlexibleSection(GameObject go)
        {
            UIFactory.SetPrefH(go, -1);
            UIFactory.SetMinH(go, 0);
            SetLayoutFlexHeight(go, 1);
        }

        private static void SetSectionWidth(GameObject go, float width, float min, float flex)
        {
            var le = go.GetComponent(UIFactory.tLE);
            if (le == null) { UIFactory.AddLE(go, prefW: width, minW: min, flexW: flex); return; }
            UIFactory.tLE.GetProperty("preferredWidth")?.SetValue(le, width);
            UIFactory.tLE.GetProperty("minWidth")?.SetValue(le, min);
            UIFactory.tLE.GetProperty("flexibleWidth")?.SetValue(le, flex);
        }

        private static void ConfigureHistoryCard(GameObject card, GameObject oldCasualCard,
            GameObject rankedBody, GameObject rankedPager, GameObject casualBody, GameObject casualPager,
            GameObject record, GameObject leftCol)
        {
            historyRankedBody = rankedBody; historyRankedPager = rankedPager;
            historyCasualBody = casualBody; historyCasualPager = casualPager;
            Section(card, "RkH").SetActive(false);
            historyKindButton = UIFactory.CreateButton("HistoryKind", card.transform, "", 18, C_GOLD, C_BTN,
                () => { historyKind = 1 - historyKind; RefreshHistoryKind(); }, new Vector2(280, 32));
            historyKindButton.transform.SetSiblingIndex(0);
            MoveSection(casualBody, card.transform); MoveSection(casualPager, card.transform);
            oldCasualCard.SetActive(false);
            UIFactory.SetMinH(card, 200);
            /* Win/Loss record pins to the BOTTOM of the LEFT column (as a static
             * sibling under the scroll view, which is flexH:1 and absorbs the
             * slack) instead of a fixed-height box under the history card — so
             * the history card now fills the right column's full height. */
            MoveSection(record, leftCol.transform);
            RefreshHistoryKind();
        }

        private static void RefreshHistoryKind()
        {
            historyRankedBody.SetActive(historyKind == 0); historyRankedPager.SetActive(historyKind == 0);
            historyCasualBody.SetActive(historyKind == 1); historyCasualPager.SetActive(historyKind == 1);
            UIFactory.SetText(UIFactory.GetButtonText(historyKindButton), historyKind == 0
                ? I18n.Tr("History: Ranked  v") : I18n.Tr("History: Casual  v"));
            CompetitiveUI.ClearCardHoverRegions();
            dirty = true;
        }

        private static string[] BoardChoices => new[] { I18n.Tr("1v1"), I18n.Tr("2v2"), I18n.Tr("FFA"), I18n.Tr("1v2 - Solo"), I18n.Tr("1v2 - Duo") };

        private static void PickLayoutChoice(string title, string[] choices, Action<int> selected)
        {
            var keys = new string[choices.Length];
            for (int i = 0; i < keys.Length; i++) keys[i] = i.ToString();
            CompetitiveUI.OpenArtistPicker(title, choices, keys, key =>
            {
                if (int.TryParse(key, out int value) && value >= 0 && value < choices.Length) selected(value);
            });
        }

        private static void AssembleUnifiedPages(Transform parent)
        {
            var oldLeaderboard = tabPanels[1];
            var team = tabPanels[8]; var ovt = tabPanels[11]; var ffa = tabPanels[12];
            int pagePosition = oldLeaderboard.transform.GetSiblingIndex();
            var leaderboard = LayoutColumn("LeaderboardsPage", parent);
            leaderboard.transform.SetSiblingIndex(pagePosition);
            MakeSubTabAnchor(1, leaderboard.transform, true);
            var columns = new GameObject("LeaderboardColumns");
            columns.transform.SetParent(leaderboard.transform, false); columns.AddComponent<RectTransform>();
            UIFactory.AddHLG(columns, spacing: 8); UIFactory.AddLE(columns, flexH: 1);
            var boardCard = LayoutColumn("LeaderboardCard", columns.transform, true);
            SetSectionWidth(boardCard, 810, 800, 0);
            boardSelector = UIFactory.CreateButton("BoardSelector", boardCard.transform, "", 18, C_GOLD, C_BTN,
                () => { unifiedBoard = (unifiedBoard + 1) % BoardChoices.Length; unifiedRecent = RecentForBoard(unifiedBoard); ApplyBoardSelection(); FetchSelectedBoard(); FetchSelectedRecent(); }, new Vector2(360, 34));
            var ranked = Section(oldLeaderboard, "LBMid");
            // The group navigation now belongs to the shared page, above both columns.
            foreach (Transform child in ranked.transform)
                if (child.name.StartsWith("SubTabAnchor", StringComparison.Ordinal)) child.gameObject.SetActive(false);
            unifiedBoards = new[] { ranked, Section(team, "TLBCol"), Section(ffa, "FfaLBCol"),
                LayoutColumn("SoloBoard", boardCard.transform), LayoutColumn("DuoBoard", boardCard.transform) };
            MoveSection(Section(ovt, "O1SLH"), unifiedBoards[3].transform);
            var soloList = Section(ovt, "O1SLSV"); MoveSection(soloList, unifiedBoards[3].transform); FlexibleSection(soloList);
            MoveSection(Section(ovt, "O1DLH"), unifiedBoards[4].transform);
            var duoList = Section(ovt, "O1DLSV"); MoveSection(duoList, unifiedBoards[4].transform); FlexibleSection(duoList);
            foreach (var board in unifiedBoards) { MoveSection(board, boardCard.transform); FlexibleSection(board); SetSectionWidth(board, 0, 0, 1); }

            unifiedDetail = Section(oldLeaderboard, "LBR");
            MoveSection(unifiedDetail, boardCard.transform); SetSectionWidth(unifiedDetail, 0, 0, 1);
            UIFactory.SetPrefH(unifiedDetail, 280); UIFactory.SetMinH(unifiedDetail, 160); SetLayoutFlexHeight(unifiedDetail, 0);
            var recentCard = LayoutColumn("RecentGamesCard", columns.transform, true);
            SetSectionWidth(recentCard, 600, 430, 1);
            unifiedRecents = new[] { Section(oldLeaderboard, "LBSeries"), Section(team, "TH2Col"), Section(ovt, "O1RCol"),
                LayoutColumn("RankedFfaRecent", recentCard.transform), LayoutColumn("CasualFfaRecent", recentCard.transform) };
            MoveSection(Section(ffa, "FfaRHR"), unifiedRecents[3].transform);
            var ffaRanked = Section(ffa, "FfaRSV"); MoveSection(ffaRanked, unifiedRecents[3].transform); FlexibleSection(ffaRanked);
            MoveSection(Section(ffa, "FfaCHR"), unifiedRecents[4].transform);
            var ffaCasual = Section(ffa, "FfaCSV"); MoveSection(ffaCasual, unifiedRecents[4].transform); FlexibleSection(ffaCasual);
            foreach (var recent in unifiedRecents) { MoveSection(recent, recentCard.transform); FlexibleSection(recent); SetSectionWidth(recent, 0, 0, 1); }
            // Headers share the width with pagination; let the title take the remainder.
            foreach (var label in new[] { txtTeamHistHeader, txtOvtRecentHeader, txtFfaRecentHeader, txtFfaRecentCasHeader })
            { var go = (label as Component)?.gameObject; if (go != null) SetSectionWidth(go, 0, 0, 1); }
            ffaTabOuterViewport = recentCard.GetComponent<RectTransform>();
            ovtTabOuterViewport = recentCard.GetComponent<RectTransform>();
            leaderboard.AddComponent<FfaRecentGraphDrawer>(); leaderboard.AddComponent<OneVTwoHoverDrawer>();
            tabPanels[1] = leaderboard;
            BuildUnifiedMultiplayer(Section(tabPanels[TAB_HOME], "HRight").transform, team, ovt, ffa);
            // Keep unused construction hosts inactive; moved controls have one live owner.
            oldLeaderboard.SetActive(false); team.SetActive(false); ovt.SetActive(false); ffa.SetActive(false);
            tabPanels[11] = null; tabPanels[12] = null;
            ApplyBoardSelection();
        }

        private static int RecentForBoard(int board)
        {
            switch (board)
            {
                case 1: return 1;
                case 2: return 3;
                case 3:
                case 4: return 2;
                default: return 0;
            }
        }

        private static void ApplyBoardSelection()
        {
            if (unifiedBoards == null) return;
            for (int i = 0; i < unifiedBoards.Length; i++) unifiedBoards[i].SetActive(i == unifiedBoard);
            for (int i = 0; i < unifiedRecents.Length; i++) unifiedRecents[i].SetActive(i == unifiedRecent);
            unifiedDetail.SetActive(unifiedBoard == 0 && !string.IsNullOrEmpty(selectedSteamId));
            UIFactory.SetText(UIFactory.GetButtonText(boardSelector), I18n.TrF("Mode: {0}  v", BoardChoices[unifiedBoard]));
            PageGeneration++; CompetitiveUI.ClearCardHoverRegions(); ProfileCard.ClearHoverTargets(); dirty = true;
        }

        private static void FetchSelectedBoard()
        {
            switch (unifiedBoard)
            {
                case 0: ApiClient.FetchLeaderboard(); break;
                case 1: ApiClient.FetchTeamLeaderboard(200, ApiClient.CachedTeamLeaderboardSort ?? "rating"); break;
                case 2: ApiClient.FetchFfaLeaderboard(200, ffaLbSortReq); break;
                case 3: ApiClient.FetchOvtLeaderboard(200, "solo"); break;
                case 4: ApiClient.FetchOvtLeaderboard(200, "duo"); break;
            }
        }

        private static void FetchSelectedRecent()
        {
            switch (unifiedRecent)
            {
                case 0: ApiClient.FetchRecentSeries(); ApiClient.FetchActiveSeries(); break;
                case 1: ApiClient.FetchAllSeriesPaged(teamSeriesPageReq, 10); break;
                case 2: ApiClient.FetchOvtRecent(ovtRecentPageReq); break;
                case 3: ApiClient.FetchFfaRecent(ffaRecentPageReq, 5); break;
                case 4: ApiClient.FetchFfaRecent(ffaRecentCasPageReq, 5, false); break;
            }
        }

        private static void RefreshUnifiedLeaderboards()
        {
            if (unifiedBoard == 0) RefreshLeaderboard();
            unifiedDetail.SetActive(unifiedBoard == 0 && !string.IsNullOrEmpty(selectedSteamId));
            if (unifiedBoard == 1) RefreshTeamTab();
            if (unifiedBoard == 2) RefreshFfaTab();
            if (unifiedBoard == 3 || unifiedBoard == 4) RefreshOneVTwoTab();
            // Recent-row renderers replace the hover registry. The visible recent
            // list must render last when its mode differs from the selected board.
            if (unifiedRecent == 0) { RefreshRecentSeries(); RefreshLiveSeries(); }
            else if (unifiedRecent == 1 && unifiedBoard != 1) RefreshTeamTab();
            else if (unifiedRecent == 2 && unifiedBoard != 3 && unifiedBoard != 4) RefreshOneVTwoTab();
            else if (unifiedRecent >= 3 && unifiedBoard != 2) RefreshFfaTab();
        }

        private static void BuildUnifiedMultiplayer(Transform parent, GameObject team, GameObject ovt, GameObject ffa)
        {
            var page = LayoutColumn("MultiplayerPage", parent);
            page.transform.SetAsFirstSibling();
            var toolbar = LayoutRow("MultiplayerToolbar", page.transform, 36);
            lobbySectionButton = UIFactory.CreateButton("Lobbies", toolbar.transform, I18n.Tr("Active lobbies"), 17, C_WHITE, C_BTN,
                () => { multiplayerSection = 0; RefreshMultiplayerSelection(); }, new Vector2(180, 34));
            queueSectionButton = UIFactory.CreateButton("Random", toolbar.transform, I18n.Tr("Random queue"), 17, C_WHITE, C_BTN,
                () => { multiplayerSection = 1; RefreshMultiplayerSelection(); }, new Vector2(180, 34));
            UIFactory.CreateButton("LobbyOptions", toolbar.transform, I18n.Tr("Create lobby / Options"), 17, C_WHITE, C_QUEUE_BUTTON,
                OpenLobbyOptions, new Vector2(250, 34));
            multiplayerActivity = LayoutColumn("CurrentQueueActivity", page.transform);
            SetLayoutFlexHeight(multiplayerActivity, 0);
            multiplayerActivity.SetActive(false);
            /* The lobby/queue CONTROLS are static — parked above the scroll view
             * so they can never scroll away (Sid: "make the multiplayer options
             * static so you can't scroll on them"). Only the lobby browser and
             * the live/bet panels (real lists) live in the scroll. */
            var staticOpts = LayoutColumn("StaticLobbyOptions", page.transform);
            SetLayoutFlexHeight(staticOpts, 0);
            MoveSection(Section(team, "THostLobby"), staticOpts.transform);
            MoveSection(Section(ovt, "O1St"), staticOpts.transform); MoveSection(Section(ovt, "O1Host"), staticOpts.transform);
            MoveSection(Section(ffa, "FfaCtl"), staticOpts.transform); MoveSection(Section(ffa, "FfaSt"), staticOpts.transform);
            var lobbyScroll = UIFactory.CreateScrollView("ActiveLobbyScroll", page.transform, spacing: 8);
            UIFactory.AddLE(lobbyScroll.scrollGO, flexH: 1); lobbyListBody = lobbyScroll.scrollGO;
            var host = lobbyScroll.content.transform;
            MoveSection(Section(ffa, "FfaQL"), host);
            MoveSection(teamLivePanel, host); MoveSection(ovtLivePanel, host); MoveSection(ffaBetPanel, host);
            randomQueueBody = LayoutColumn("RandomQueue", page.transform, true);
            queueFilterButton = UIFactory.CreateButton("QueueFilter", randomQueueBody.transform, "", 17, C_GOLD, C_BTN,
                () => PickLayoutChoice(I18n.Tr("Queue mode"), new[] { I18n.Tr("1v1"), I18n.Tr("2v2") }, value =>
                { randomQueueMode = value; RefreshMultiplayerSelection(); }), new Vector2(260, 34));
            randomSoloBody = LayoutColumn("SoloQueue", randomQueueBody.transform);
            randomSoloStatus = UIFactory.CreateText("SoloQueueStatus", randomSoloBody.transform, "", 18, C_LABEL,
                sizeDelta: new Vector2(800, 32));
            var soloButtons = LayoutRow("SoloQueueButtons", randomSoloBody.transform);
            randomSoloJoin = UIFactory.CreateButton("SoloQueueJoin", soloButtons.transform, I18n.Tr("Queue Ranked"), 17, C_WHITE, C_QUEUE_BUTTON,
                () => { var id = MatchTracker.LocalSteamId; if (!string.IsNullOrEmpty(id) && id != "unknown") ApiClient.JoinQueue(id, MatchTracker.LocalDisplayName, null, false); }, new Vector2(180, 32));
            randomSoloLeave = UIFactory.CreateButton("SoloQueueLeave", soloButtons.transform, I18n.Tr("Leave Queue"), 17, C_WHITE, C_BTN,
                () => ApiClient.LeaveQueue(MatchTracker.LocalSteamId), new Vector2(180, 32));
            var teamScroll = UIFactory.CreateScrollView("RandomTeamScroll", randomQueueBody.transform, spacing: 6);
            UIFactory.AddLE(teamScroll.scrollGO, flexH: 1); randomTeamBody = teamScroll.scrollGO;
            teamQueueStatus = Section(team, "TStat");
            teamQueueIdleParent = teamScroll.content.transform;
            MoveSection(teamQueueStatus, teamQueueIdleParent);
            MoveSection(Section(team, "TQR"), teamScroll.content.transform);
            tabPanels[8] = null; // Historical mode routes now resolve to Home.
            BuildLobbyOptions();
            RefreshMultiplayerSelection();
        }

        private static void RefreshMultiplayerSelection()
        {
            lobbyListBody.SetActive(multiplayerSection == 0); randomQueueBody.SetActive(multiplayerSection == 1);
            randomSoloBody.SetActive(randomQueueMode == 0); randomTeamBody.SetActive(randomQueueMode == 1);
            UIFactory.SetImageColor(lobbySectionButton, multiplayerSection == 0 ? C_TABACT : C_BTN);
            UIFactory.SetImageColor(queueSectionButton, multiplayerSection == 1 ? C_TABACT : C_BTN);
            UIFactory.SetText(UIFactory.GetButtonText(queueFilterButton), randomQueueMode == 0 ? I18n.Tr("Mode: 1v1  v") : I18n.Tr("Mode: 2v2  v"));
            dirty = true;
        }

        private static void RefreshUnifiedMultiplayer()
        {
            RefreshTeamTab(); RefreshOneVTwoTab(); RefreshFfaTab();
            // Ready/leave actions stay reachable even if the mode filter changes
            // or a hosted 2v2 lobby has handed its seats off to the queue.
            bool teamActive = ApiClient.CurrentTeamQueueState != ApiClient.TeamQueueState.Idle;
            var statusParent = teamActive ? multiplayerActivity.transform : teamQueueIdleParent;
            if (teamQueueStatus.transform.parent != statusParent) MoveSection(teamQueueStatus, statusParent);
            multiplayerActivity.SetActive(teamActive);
            bool ranked = Plugin.RankedEnabled.Value;
            var state = ApiClient.CurrentQueueState;
            UIFactory.SetText(randomSoloStatus, !ranked ? I18n.Tr("Turn on Ranked above to queue.")
                : state == ApiClient.QueueState.Idle ? I18n.TrF("{0} searching for 1v1", ApiClient.CachedQueueSearching)
                : state == ApiClient.QueueState.Searching ? I18n.Tr("Searching for a ranked 1v1...")
                : I18n.Tr("Check the match controls at the top of the menu."));
            randomSoloJoin.SetActive(ranked && state == ApiClient.QueueState.Idle && !(GameStateWatcher.IsInMatch && GameStateWatcher.MatchIsRanked));
            randomSoloLeave.SetActive(state == ApiClient.QueueState.Searching);
        }

        private static void BuildLobbyOptions()
        {
            lobbyOptionsRoot = UIFactory.CreatePanel("LobbyOptionsModal", pageGO.transform, new Color(0, 0, 0, 0.75f));
            lobbyOptionsBox = UIFactory.CreatePanel("LobbyOptionsBox", lobbyOptionsRoot.transform, C_PANEL);
            var rt = lobbyOptionsBox.GetComponent<RectTransform>();
            rt.anchorMin = new Vector2(0.1f, 0.12f); rt.anchorMax = new Vector2(0.9f, 0.88f);
            rt.offsetMin = rt.offsetMax = Vector2.zero;
            UIFactory.AddVLG(lobbyOptionsBox, spacing: 12, padL: 20, padR: 20, padT: 16, padB: 16);
            var header = LayoutRow("LobbyOptionsHeader", lobbyOptionsBox.transform, 36);
            var title = UIFactory.CreateText("LobbyOptionsTitle", header.transform, I18n.Tr("Lobby creator & options"), 22, C_GOLD,
                sizeDelta: new Vector2(600, 34));
            SetSectionWidth((title as Component).gameObject, 0, 0, 1);
            UIFactory.CreateButton("CloseLobbyOptions", header.transform, I18n.Tr("Close"), 16, C_WHITE, C_BTN, CloseLobbyOptions, new Vector2(100, 32));
            lobbyModeButton = UIFactory.CreateButton("LobbyMode", lobbyOptionsBox.transform, "", 18, C_WHITE, C_BTN,
                () => PickLayoutChoice(I18n.Tr("Lobby mode"), new[] { I18n.Tr("2v2"), I18n.Tr("1v2"), I18n.Tr("FFA") }, value =>
                { lobbyOptionsMode = value; RefreshLobbyOptions(); }), new Vector2(300, 34));
            var scroll = UIFactory.CreateScrollView("LobbyOptionsScroll", lobbyOptionsBox.transform, spacing: 10);
            UIFactory.AddLE(scroll.scrollGO, flexH: 1);
            lobbyOptionBodies = new GameObject[3];
            for (int i = 0; i < 3; i++)
            { lobbyOptionBodies[i] = LayoutColumn("LobbyOptions" + i, scroll.content.transform); SetLayoutFlexHeight(lobbyOptionBodies[i], 0); }
            var teamRow = LayoutRow("CreateTeamLobby", lobbyOptionBodies[0].transform);
            MoveSection(teamLobbyCreateBtn, teamRow.transform); MoveSection(teamLobbyCreatePrivBtn, teamRow.transform);
            MoveSection(teamLobbyPrefBtn, lobbyOptionBodies[0].transform);
            var ovtRow = LayoutRow("CreateOvtLobby", lobbyOptionBodies[1].transform);
            MoveSection(ovtLobbyCreateBtn, ovtRow.transform); MoveSection(ovtLobbyCreatePrivBtn, ovtRow.transform);
            MoveSection(ovtSideBtn, lobbyOptionBodies[1].transform); MoveSection(ovtExtraBtn, lobbyOptionBodies[1].transform);
            var ffaRow = LayoutRow("CreateFfaLobby", lobbyOptionBodies[2].transform);
            MoveSection(ffaJoinBtn, ffaRow.transform); MoveSection(ffaCreatePrivBtn, ffaRow.transform);
            UIFactory.CreateText("FfaConfigHelp", lobbyOptionBodies[2].transform,
                I18n.Tr("Create an FFA lobby to configure its rules below. Only the host can change rules."), 16, C_LABEL,
                sizeDelta: new Vector2(900, 28));
            MoveSection(ffaSettingsRow, lobbyOptionBodies[2].transform);
            // Replace the wide inline settings strip with one row per setting.
            var oldLayout = ffaSettingsRow.GetComponent("HorizontalLayoutGroup");
            if (oldLayout != null) UnityEngine.Object.DestroyImmediate(oldLayout);
            UIFactory.AddVLG(ffaSettingsRow, spacing: 8); UIFactory.SetPrefH(ffaSettingsRow, -1); UIFactory.SetMinH(ffaSettingsRow, 0);
            foreach (var field in new[] { "score_target", "card_candidates", "initial_picks", "card_cap" })
            {
                var row = LayoutRow("Setting_" + field, ffaSettingsRow.transform, 32);
                foreach (var prefix in new[] { "L_", "M_", "V_", "P_" }) MoveSection(Section(ffaSettingsRow, prefix + field), row.transform);
            }
            Section(ffaSettingsRow, "FfaCfgSp").SetActive(false);
            var backdrop = lobbyOptionsRoot.AddComponent<ClickHandler>(); backdrop.bypassModalBlock = true;
            backdrop.onClick = () => { if (!PointerInsideRect(rt) && !CompetitiveUI.PromptOpen && ClickGuard.Claim(lobbyOptionsRoot)) CloseLobbyOptions(); };
            MarkPopupChildrenInteractive(lobbyOptionsRoot);
            lobbyOptionsRoot.SetActive(false);
        }

        private static void OpenLobbyOptions()
        {
            if (CompetitiveUI.OtherModalOwnsInput || UtilityPopupOpen) return;
            lobbyOptionsRoot.SetActive(true); lobbyOptionsRoot.transform.SetAsLastSibling();
            RefreshUnifiedMultiplayer(); RefreshLobbyOptions();
        }

        private static void RefreshLobbyOptions()
        {
            for (int i = 0; i < lobbyOptionBodies.Length; i++) lobbyOptionBodies[i].SetActive(i == lobbyOptionsMode);
            UIFactory.SetText(UIFactory.GetButtonText(lobbyModeButton), I18n.TrF("Mode: {0}  v", new[] { "2v2", "1v2", "FFA" }[lobbyOptionsMode]));
        }

        private static void CloseLobbyOptions()
        {
            if (lobbyOptionsRoot != null) lobbyOptionsRoot.SetActive(false);
        }
    }
}
