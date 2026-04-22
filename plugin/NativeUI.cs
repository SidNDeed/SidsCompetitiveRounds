using System;
using System.Collections.Generic;
using System.Reflection;
using UnityEngine;

namespace CompetitiveRounds
{
    // Frame-based debounce — prevents ClickHandler + standard Button from both firing
    internal static class ClickGuard
    {
        private static float lastTime = -1f;
        public static bool Claim()
        {
            if (Time.unscaledTime - lastTime < 0.2f) return false;
            lastTime = Time.unscaledTime;
            return true;
        }
    }

    internal static class UIFactory
    {
        internal static Type tImage, tButton, tCanvas, tLE;
        internal static Type tScrollRect;internal static Type tMask;private static Type tVLG, tHLG, tCSF;
        internal static Type tGR, tCanvasScaler;
        private static Type tTMP;
        private static bool typesReady = false;
        private static object tmpFont; private static bool fontReady = false;
        public static Type tListMenu, tListMenuPage, tGoBack;
        private static PropertyInfo pTmpText, pTmpFontSize, pTmpColor, pTmpAlignment, pTmpFont, pTmpOverflow, pTmpRichText, pTmpFontStyle, pTmpRaycastTarget, pTmpCharSpacing;
        private static PropertyInfo pImgColor, pImgRaycastTarget;
        private static PropertyInfo pBtnOnClick; private static MethodInfo mOnClickAdd;
        private static PropertyInfo pSRContent, pSRViewport, pSRVertical, pSRHorizontal, pSRMovementType, pSRScrollSensitivity;
        private static PropertyInfo pVLGSpacing, pVLGPadding, pVLGChildForceW, pVLGChildForceH, pVLGChildControlW, pVLGChildControlH;
        private static PropertyInfo pHLGSpacing, pHLGPadding, pHLGChildForceW, pHLGChildForceH, pHLGChildControlW, pHLGChildControlH;
        private static PropertyInfo pCSFFit;
        private static PropertyInfo pLEMinW, pLEMinH, pLEPrefW, pLEPrefH, pLEFlexW, pLEFlexH, pLEIgnore;
        public static bool Ready => typesReady && fontReady;

        public static bool InitTypes()
        {
            if (typesReady) return true;
            foreach (var asm in AppDomain.CurrentDomain.GetAssemblies())
            {
                if(tImage==null)tImage=asm.GetType("UnityEngine.UI.Image"); if(tButton==null)tButton=asm.GetType("UnityEngine.UI.Button");
                if(tScrollRect==null)tScrollRect=asm.GetType("UnityEngine.UI.ScrollRect"); if(tMask==null)tMask=asm.GetType("UnityEngine.UI.Mask");
                if(tVLG==null)tVLG=asm.GetType("UnityEngine.UI.VerticalLayoutGroup"); if(tHLG==null)tHLG=asm.GetType("UnityEngine.UI.HorizontalLayoutGroup");
                if(tCSF==null)tCSF=asm.GetType("UnityEngine.UI.ContentSizeFitter"); if(tLE==null)tLE=asm.GetType("UnityEngine.UI.LayoutElement");
                if(tGR==null)tGR=asm.GetType("UnityEngine.UI.GraphicRaycaster"); if(tTMP==null)tTMP=asm.GetType("TMPro.TextMeshProUGUI");
                if(tCanvas==null)tCanvas=asm.GetType("UnityEngine.Canvas"); if(tCanvasScaler==null)tCanvasScaler=asm.GetType("UnityEngine.UI.CanvasScaler");
                if(tListMenu==null)tListMenu=asm.GetType("ListMenu"); if(tListMenuPage==null)tListMenuPage=asm.GetType("ListMenuPage"); if(tGoBack==null)tGoBack=asm.GetType("GoBack");
            }
            if(tImage==null||tTMP==null||tButton==null){Plugin.Log.LogWarning("[UI] Missing UI types");return false;}
            if(tListMenu==null||tListMenuPage==null){Plugin.Log.LogWarning("[UI] Missing ROUNDS types");return false;}
            var bf=BindingFlags.Public|BindingFlags.Instance;
            pTmpText=tTMP.GetProperty("text",bf);pTmpFontSize=tTMP.GetProperty("fontSize",bf);pTmpColor=tTMP.GetProperty("color",bf);
            pTmpAlignment=tTMP.GetProperty("alignment",bf);pTmpFont=tTMP.GetProperty("font",bf);pTmpOverflow=tTMP.GetProperty("overflowMode",bf);
            pTmpRichText=tTMP.GetProperty("richText",bf);pTmpFontStyle=tTMP.GetProperty("fontStyle",bf);pTmpRaycastTarget=tTMP.GetProperty("raycastTarget",bf);pTmpCharSpacing=tTMP.GetProperty("characterSpacing",bf);
            pImgColor=tImage.GetProperty("color",bf);pImgRaycastTarget=tImage.GetProperty("raycastTarget",bf);
            pBtnOnClick=tButton.GetProperty("onClick",bf); if(pBtnOnClick!=null)mOnClickAdd=pBtnOnClick.PropertyType.GetMethod("AddListener",new Type[]{typeof(UnityEngine.Events.UnityAction)});
            pSRContent=tScrollRect?.GetProperty("content",bf);pSRViewport=tScrollRect?.GetProperty("viewport",bf);pSRVertical=tScrollRect?.GetProperty("vertical",bf);pSRHorizontal=tScrollRect?.GetProperty("horizontal",bf);pSRMovementType=tScrollRect?.GetProperty("movementType",bf);pSRScrollSensitivity=tScrollRect?.GetProperty("scrollSensitivity",bf);
            if(tVLG!=null){pVLGSpacing=tVLG.GetProperty("spacing",bf);pVLGPadding=tVLG.GetProperty("padding",bf);pVLGChildForceW=tVLG.GetProperty("childForceExpandWidth",bf);pVLGChildForceH=tVLG.GetProperty("childForceExpandHeight",bf);pVLGChildControlW=tVLG.GetProperty("childControlWidth",bf);pVLGChildControlH=tVLG.GetProperty("childControlHeight",bf);}
            if(tHLG!=null){pHLGSpacing=tHLG.GetProperty("spacing",bf);pHLGPadding=tHLG.GetProperty("padding",bf);pHLGChildForceW=tHLG.GetProperty("childForceExpandWidth",bf);pHLGChildForceH=tHLG.GetProperty("childForceExpandHeight",bf);pHLGChildControlW=tHLG.GetProperty("childControlWidth",bf);pHLGChildControlH=tHLG.GetProperty("childControlHeight",bf);}
            if(tCSF!=null)pCSFFit=tCSF.GetProperty("verticalFit",bf);
            if(tLE!=null){pLEMinW=tLE.GetProperty("minWidth",bf);pLEMinH=tLE.GetProperty("minHeight",bf);pLEPrefW=tLE.GetProperty("preferredWidth",bf);pLEPrefH=tLE.GetProperty("preferredHeight",bf);pLEFlexW=tLE.GetProperty("flexibleWidth",bf);pLEFlexH=tLE.GetProperty("flexibleHeight",bf);pLEIgnore=tLE.GetProperty("ignoreLayout",bf);}
            typesReady=true;return true;
        }

        public static bool InitFont()
        {
            if(fontReady)return true;if(!typesReady)return false;
            foreach(var tmp in UnityEngine.Object.FindObjectsOfType(tTMP)){try{var f=pTmpFont?.GetValue(tmp);if(f!=null){tmpFont=f;fontReady=true;return true;}}catch{}}
            return false;
        }

        public static GameObject CreatePanel(string name,Transform parent,Color bgColor,Vector2? sizeDelta=null)
        {var go=new GameObject(name);go.transform.SetParent(parent,false);var rt=go.AddComponent<RectTransform>();rt.anchorMin=Vector2.zero;rt.anchorMax=Vector2.one;rt.offsetMin=Vector2.zero;rt.offsetMax=Vector2.zero;if(sizeDelta.HasValue)rt.sizeDelta=sizeDelta.Value;if(bgColor.a>0){var img=go.AddComponent(tImage);pImgColor?.SetValue(img,bgColor);pImgRaycastTarget?.SetValue(img,true);}return go;}

        public static object CreateText(string name,Transform parent,string text,float fontSize,Color color,int alignment=AlignTopLeft,Vector2? sizeDelta=null,bool richText=true,bool raycastTarget=false)
        {var go=new GameObject(name);go.transform.SetParent(parent,false);var rt=go.AddComponent<RectTransform>();Vector2 sz=sizeDelta??new Vector2(200,24);rt.sizeDelta=sz;if(sz.x>0&&sz.y>0)AddLE(go,prefW:sz.x,prefH:sz.y);var tmp=go.AddComponent(tTMP);pTmpText?.SetValue(tmp,text);pTmpFontSize?.SetValue(tmp,fontSize);pTmpColor?.SetValue(tmp,color);pTmpRichText?.SetValue(tmp,richText);pTmpRaycastTarget?.SetValue(tmp,raycastTarget);if(tmpFont!=null)pTmpFont?.SetValue(tmp,tmpFont);pTmpCharSpacing?.SetValue(tmp,1.0f);try{pTmpFontStyle?.SetValue(tmp,Enum.ToObject(pTmpFontStyle.PropertyType,1));}catch{}try{var at=pTmpAlignment?.PropertyType;if(at!=null)pTmpAlignment.SetValue(tmp,Enum.ToObject(at,alignment));}catch{}return tmp;}

        public static GameObject CreateButton(string name,Transform parent,string label,float fontSize,Color textColor,Color bgColor,UnityEngine.Events.UnityAction onClick,Vector2? sizeDelta=null)
        {
            var sz=sizeDelta??new Vector2(100,28);var go=CreatePanel(name,parent,bgColor,sizeDelta:sz);var rt=go.GetComponent<RectTransform>();rt.anchorMin=rt.anchorMax=new Vector2(0.5f,0.5f);rt.sizeDelta=sz;AddLE(go,prefW:sz.x,prefH:sz.y);
            CreateText(name+"_Txt",go.transform,label,fontSize,textColor,AlignMidCenter,sizeDelta:Vector2.zero);
            var txtRT=go.transform.GetChild(0).GetComponent<RectTransform>();txtRT.anchorMin=Vector2.zero;txtRT.anchorMax=Vector2.one;txtRT.offsetMin=Vector2.zero;txtRT.offsetMax=Vector2.zero;
            var innerLE=go.transform.GetChild(0).GetComponent(tLE);if(innerLE!=null)UnityEngine.Object.Destroy(innerLE as UnityEngine.Object);
            var btn=go.AddComponent(tButton);try{var tgt=tButton.GetProperty("targetGraphic",BindingFlags.Public|BindingFlags.Instance);var img=go.GetComponent(tImage);if(tgt!=null&&img!=null)tgt.SetValue(btn,img);}catch{}
            if(pBtnOnClick!=null&&mOnClickAdd!=null&&onClick!=null){var guarded=new UnityEngine.Events.UnityAction(()=>{if(ClickGuard.Claim())onClick();});mOnClickAdd.Invoke(pBtnOnClick.GetValue(btn),new object[]{guarded});}
            if(onClick!=null){var ch=go.AddComponent<ClickHandler>();ch.onClick=()=>{if(ClickGuard.Claim())onClick();};}
            return go;
        }

        public static ScrollViewRefs CreateScrollView(string name,Transform parent,float spacing=2f)
        {var refs=new ScrollViewRefs();var sGO=new GameObject(name);sGO.transform.SetParent(parent,false);var sRT=sGO.AddComponent<RectTransform>();sRT.anchorMin=Vector2.zero;sRT.anchorMax=Vector2.one;sRT.offsetMin=Vector2.zero;sRT.offsetMax=Vector2.zero;var vp=new GameObject("Viewport");vp.transform.SetParent(sGO.transform,false);var vpRT=vp.AddComponent<RectTransform>();vpRT.anchorMin=Vector2.zero;vpRT.anchorMax=Vector2.one;vpRT.offsetMin=Vector2.zero;vpRT.offsetMax=Vector2.zero;var vpImg=vp.AddComponent(tImage);pImgColor?.SetValue(vpImg,new Color(0,0,0,0.01f));if(tMask!=null){var m=vp.AddComponent(tMask);tMask.GetProperty("showMaskGraphic",BindingFlags.Public|BindingFlags.Instance)?.SetValue(m,false);}var cnt=new GameObject("Content");cnt.transform.SetParent(vp.transform,false);var cRT=cnt.AddComponent<RectTransform>();cRT.anchorMin=new Vector2(0,1);cRT.anchorMax=new Vector2(1,1);cRT.pivot=new Vector2(0.5f,1f);cRT.sizeDelta=Vector2.zero;if(tVLG!=null){var v=cnt.AddComponent(tVLG);pVLGSpacing?.SetValue(v,spacing);pVLGChildForceW?.SetValue(v,true);pVLGChildForceH?.SetValue(v,false);pVLGChildControlW?.SetValue(v,true);pVLGChildControlH?.SetValue(v,true);}if(tCSF!=null){var csf=cnt.AddComponent(tCSF);var ft=pCSFFit?.PropertyType;if(ft!=null)pCSFFit.SetValue(csf,Enum.ToObject(ft,2));}var sr=sGO.AddComponent(tScrollRect);pSRContent?.SetValue(sr,cRT);pSRViewport?.SetValue(sr,vpRT);pSRVertical?.SetValue(sr,true);pSRHorizontal?.SetValue(sr,false);pSRScrollSensitivity?.SetValue(sr,25f);var mt=pSRMovementType?.PropertyType;if(mt!=null)pSRMovementType.SetValue(sr,Enum.ToObject(mt,1));refs.scrollGO=sGO;refs.content=cnt;refs.contentRT=cRT;return refs;}
        public struct ScrollViewRefs{public GameObject scrollGO,content;public RectTransform contentRT;}

        public static void AddVLG(GameObject go,float spacing=2,int padL=0,int padR=0,int padT=0,int padB=0,bool forceExpandW=true,bool forceExpandH=false){if(tVLG==null)return;var v=go.AddComponent(tVLG);pVLGSpacing?.SetValue(v,spacing);pVLGPadding?.SetValue(v,new RectOffset(padL,padR,padT,padB));pVLGChildForceW?.SetValue(v,forceExpandW);pVLGChildForceH?.SetValue(v,forceExpandH);pVLGChildControlW?.SetValue(v,true);pVLGChildControlH?.SetValue(v,true);}
        public static void AddHLG(GameObject go,float spacing=4,int padL=0,int padR=0,int padT=0,int padB=0,bool forceExpandW=false,bool forceExpandH=true){if(tHLG==null)return;var h=go.AddComponent(tHLG);pHLGSpacing?.SetValue(h,spacing);pHLGPadding?.SetValue(h,new RectOffset(padL,padR,padT,padB));pHLGChildForceW?.SetValue(h,forceExpandW);pHLGChildForceH?.SetValue(h,forceExpandH);pHLGChildControlW?.SetValue(h,true);pHLGChildControlH?.SetValue(h,true);}
        public static void AddLE(GameObject go,float minW=-1,float minH=-1,float prefW=-1,float prefH=-1,float flexW=-1,float flexH=-1){if(tLE==null)return;var le=go.AddComponent(tLE);if(minW>=0)pLEMinW?.SetValue(le,minW);if(minH>=0)pLEMinH?.SetValue(le,minH);if(prefW>=0)pLEPrefW?.SetValue(le,prefW);if(prefH>=0)pLEPrefH?.SetValue(le,prefH);if(flexW>=0)pLEFlexW?.SetValue(le,flexW);if(flexH>=0)pLEFlexH?.SetValue(le,flexH);}
        public static Component CreateFillBar(string name,Transform parent,Color bgColor,Color fillColor,float height=8f){var bgGO=new GameObject(name+"_BG");bgGO.transform.SetParent(parent,false);bgGO.AddComponent<RectTransform>();AddLE(bgGO,prefH:height,flexH:0);bgGO.AddComponent(tImage);pImgColor?.SetValue(bgGO.GetComponent(tImage),bgColor);var fGO=new GameObject(name+"_Fill");fGO.transform.SetParent(bgGO.transform,false);var fRT=fGO.AddComponent<RectTransform>();fRT.anchorMin=Vector2.zero;fRT.anchorMax=new Vector2(0f,1f);fRT.offsetMin=Vector2.zero;fRT.offsetMax=Vector2.zero;fGO.AddComponent(tImage);pImgColor?.SetValue(fGO.GetComponent(tImage),fillColor);return fRT;}
        public static void SetFill(Component f,float a){if(f==null)return;var rt=f as RectTransform;if(rt!=null)rt.anchorMax=new Vector2(Mathf.Clamp01(a),1f);}
        public static void SetText(object t,string s){if(t!=null)pTmpText?.SetValue(t,s??"");}
        public static void SetColor(object t,Color c){if(t!=null)pTmpColor?.SetValue(t,c);}
        public static void SetBold(object t,bool b){if(t==null)return;try{var tp=pTmpFontStyle?.PropertyType;if(tp!=null)pTmpFontStyle.SetValue(t,Enum.ToObject(tp,b?1:0));}catch{}}
        public static void SetWordWrap(object t,bool on){if(t==null||tTMP==null)return;try{var p=tTMP.GetProperty("enableWordWrapping",BindingFlags.Public|BindingFlags.Instance);p?.SetValue(t,on);}catch{}}
        public static void SetOverflowMode(object t,int mode){if(t==null||pTmpOverflow==null)return;try{pTmpOverflow.SetValue(t,Enum.ToObject(pTmpOverflow.PropertyType,mode));}catch{}}
        public static void SetCharSpacing(object t,float spacing){if(t!=null)pTmpCharSpacing?.SetValue(t,spacing);}
        public static void SetImageColor(GameObject go,Color c){if(go==null)return;var img=go.GetComponent(tImage);if(img!=null)pImgColor?.SetValue(img,c);}
        public static object GetButtonText(GameObject btn){if(btn==null)return null;foreach(Transform ch in btn.transform)foreach(var co in ch.GetComponents<Component>())if(co.GetType().Name=="TextMeshProUGUI")return co;return null;}
        public const int AlignTopLeft=257,AlignTopCenter=258,AlignTopRight=260,AlignMidLeft=513,AlignMidCenter=514,AlignMidRight=516;
    }

    // ClickHandler — camera-aware click detection for ROUNDS' ScreenSpaceCamera Canvas
    public class ClickHandler : MonoBehaviour
    {
        public System.Action onClick;
        private RectTransform rt;
        private Camera canvasCamera;
        private bool cameraResolved;
        private void Awake(){rt=GetComponent<RectTransform>();}
        private void ResolveCamera()
        {
            cameraResolved=true;canvasCamera=null;Transform t=transform;
            while(t!=null){var cc=t.GetComponent(UIFactory.tCanvas);if(cc!=null){try{var bf=BindingFlags.Public|BindingFlags.Instance;int rm=(int)UIFactory.tCanvas.GetProperty("renderMode",bf).GetValue(cc);if(rm!=0){canvasCamera=UIFactory.tCanvas.GetProperty("worldCamera",bf)?.GetValue(cc) as Camera;if(canvasCamera==null)canvasCamera=Camera.main;}}catch{}break;}t=t.parent;}
        }
        private void Update()
        {
            if(rt==null||onClick==null||!gameObject.activeInHierarchy)return;
            if(!Input.GetMouseButtonDown(0))return;
            if(!cameraResolved)ResolveCamera();
            Vector3[] corners=new Vector3[4];rt.GetWorldCorners(corners);
            if(canvasCamera!=null)for(int i=0;i<4;i++)corners[i]=canvasCamera.WorldToScreenPoint(corners[i]);
            Vector3 mp=Input.mousePosition;
            if(mp.x>=corners[0].x&&mp.x<=corners[2].x&&mp.y>=corners[0].y&&mp.y<=corners[2].y)onClick.Invoke();
        }
    }

    public static class NativeUI
    {
        private static readonly Color C_BG=new Color(0.06f,0.07f,0.09f,0.96f),C_PANEL=new Color(0.10f,0.11f,0.14f,0.92f);
        private static readonly Color C_WHITE=Color.white,C_SUB=new Color(0.8f,0.85f,1f),C_LABEL=new Color(0.7f,0.7f,0.75f);
        private static readonly Color C_GOLD=new Color(1f,0.85f,0.3f),C_BLUE=new Color(0.4f,0.8f,1f),C_GREEN=Color.green,C_RED=new Color(1f,0.4f,0.4f),C_DIM=new Color(0.5f,0.5f,0.55f);
        private static readonly Color C_TAB=new Color(0.16f,0.17f,0.22f,0.90f),C_TABACT=new Color(0.22f,0.38f,0.65f,0.95f),C_BTN=new Color(0.18f,0.20f,0.26f,0.92f);
        private static readonly Color C_COMMON=new Color(0.9f,0.9f,0.9f),C_UNCOMMON=new Color(0.3f,0.6f,1f),C_RARE=new Color(0.95f,0.35f,0.65f);

        private static GameObject pageGO,overlayCanvasGO,mainMenuGroup;
        private static bool isOpen,pageBuilt,dirty=true,inGameMode;
        private static int currentTab;
        private static Component listMenu;
        private static GameObject[] tabPanels,tabButtons;private static object[] tabTexts;
        private static object txtRating,txtRD,txtLevel,txtXPProg,txtTotalXP;private static Component xpFill;
        private static object txtRankedRec,txtRankedStrk,txtCasualRec,txtCasualStrk,txtSweeps,txtTotalRec,txtAccuracy,txtSessionSum,txtSessionSplit,txtSessionSweeps,txtOppSummary,txtSessionOppLifetime;
        private static GameObject sessionOppContainer;private static List<object> sessionOppTexts=new List<object>();
        private static object txtLinkCode;private static GameObject linkCodeBtn;
        // Discord ID/username click-to-reveal. Starts hidden for streamer safety.
        private static bool discordRevealed = false;
        // Chat log panel (under Discord Link in My Stats). Shows last N messages.
        private static object txtChatLog;
        // ScrollRect on the chat panel — held so RefreshChatLog can pin to the bottom on new messages.
        private static Component chatScrollRect;
        // Per-message length cap on the local renderer. The server already truncates at 500 on receive,
        // but the local echo and any paste from outside the IMGUI input box can be much longer (a 9000-char
        // changelog paste was overflowing the chat panel and trapping the scroll position). Capping here
        // keeps a single line from blowing past TMP's reported preferred height.
        private const int CHAT_LINE_MAX_CHARS = 500;
        // Live series + bet panel (top of Leaderboard tab, left column).
        private static object txtLiveSeries;
        // Header label + pulse state. Pulse cadence is decoupled from the 10s server fetch:
        // the dot flips every ~2.5s regardless of fetch timing so the "is this alive?" signal
        // reads as a gentle blink instead of a once-every-10s blip.
        private static object txtLiveHeader;
        private static bool liveHeaderPulseFilled = true;
        private static float liveHeaderNextPulseAt;
        private const float LIVE_HEADER_PULSE_INTERVAL = 2.5f;
        private static GameObject liveBetsContainer;
        private static List<GameObject> liveBetRowPool = new List<GameObject>();
        // Live-series pagination: 5 series per page, each consumes 3 rows (header + 2 bet rows).
        private static GameObject liveBetsPager, liveBetsPrev, liveBetsNext;
        private static object txtLiveBetsPage;
        private static int liveSeriesPage = 0;
        private const int LIVE_SERIES_PER_PAGE = 5;
        // Server-down banner (in-menu only, replaces the in-game IMGUI version).
        private static GameObject srvStatusRow;
        private static object txtServerStatus;
        // Auto-refresh of /series/active when Leaderboard tab is open. Throttled to every 10s.
        private static float liveSeriesAutoRefreshAt;
        public static void MaybeRefreshLiveSeries()
        {
            if (currentTab != 1) return;
            // Pulse tick (every ~2.5s): flip the header dot so it blinks visibly.
            // Decoupled from the server fetch so it doesn't have to wait 10s between blinks.
            if (Time.unscaledTime >= liveHeaderNextPulseAt)
            {
                liveHeaderNextPulseAt = Time.unscaledTime + LIVE_HEADER_PULSE_INTERVAL;
                liveHeaderPulseFilled = !liveHeaderPulseFilled;
                dirty = true;
            }
            // Fetch tick (every 5s): do the actual network poll for live series + bets.
            // Halved from 10s because the bet window between series-create and first-2-points
            // is tight (~30-60s) and spectators were missing half their chance to bet before
            // the series locked. 5s is still cheap on the server (single indexed query).
            if (Time.unscaledTime < liveSeriesAutoRefreshAt) return;
            liveSeriesAutoRefreshAt = Time.unscaledTime + 5f;
            ApiClient.FetchActiveSeries();
            var sid = MatchTracker.LocalSteamId;
            if (!string.IsNullOrEmpty(sid) && sid != "unknown") ApiClient.FetchMyBets(sid);
        }
        public struct ChatEntry { public string Line; public DateTime AddedUtc; }
        private static List<ChatEntry> chatLines = new List<ChatEntry>();
        private static readonly object chatLinesLock = new object();
        private const int CHAT_LOG_MAX = 60;

        /// <summary>Thread-safe snapshot of the most recent chat lines for the in-game overlay.</summary>
        public static ChatEntry[] SnapshotChat(int tail)
        {
            lock (chatLinesLock)
            {
                int start = Math.Max(0, chatLines.Count - tail);
                var arr = new ChatEntry[chatLines.Count - start];
                for (int i = 0; i < arr.Length; i++) arr[i] = chatLines[start + i];
                return arr;
            }
        }
        private static GameObject rankedContainer,casualContainer;
        private static List<HistoryRow> rankedRows=new List<HistoryRow>(),casualRows=new List<HistoryRow>();
        private static object txtRankedPage,txtCasualPage;private static GameObject rPrev,rNext,cPrev,cNext;private static int rankedPage,casualPage;
        private class HistoryRow{public GameObject root,seriesGO;public object txtResult,txtOpp,txtXP,txtDate,txtCards,txtOppCards,txtSeriesHead,txtSeriesElo;}
        private static List<LBRow> lbRows=new List<LBRow>();private static object txtLBCount,txtLBDetail;
        private static string selectedSteamId="";private static ApiClient.PlayerStatsData selectedStats;
        private static string lbSort="rating";private static bool lbSortDesc=true;private static object[] lbSortTexts;private static GameObject[] lbSortBtns;
        private static int lbPage=0;private static object txtLBPage;private static GameObject lbPrev,lbNext,lbBlockBtn,lbBlockRow;private static object lbBlockTxt;
        private static GameObject lbGraphPanel;
        private static object txtRecentSeries;
        private static int recentSeriesPage=0;private static object txtSeriesPage;private static GameObject seriesPrev,seriesNext;
        private class LBRow{public GameObject root,hlWrap;public object txtRank,txtLv,txtName,txtRating,txtW,txtL,txtWL,txtGold;public string steamId;}
        private static List<CardRow> cardRows=new List<CardRow>();private static int cardFilter;private static string cardSort="times_picked";private static bool cardSortDesc=true;
        private static object[] cardSortTexts;private static GameObject[] cardSortBtns,cardFilterBtns;private static object[] cardFilterTexts;
        private class CardRow{public GameObject root;public object txtName,txtRarity,txtPicks,txtWins,txtWR,txtPass;}
        private static List<AchRow> achRows=new List<AchRow>();
        private class AchRow{public GameObject root;public object txtIcon,txtName,txtDesc,txtDate;}
        private static object txtRankedStatus,txtQueueInfo,txtMatchFound,txtConnectLabel;
        private static object txtVersionStatus;
        private static GameObject updateBtn;
        private static GameObject qSearchBtn,qCancelBtn,qMatchPanel,readyBtn,declineBtn,connectLabel,rankOnBtn,rankOffBtn;
        // Column widths (scaled)
        private static readonly float[] LB_COL_W={40,40,250,88,56,56,69,76};
        private static readonly float[] CS_COL_W={350,125,69,69,69,72};
        // UI scale — apply to font sizes and row heights for readability
        private const float S = 1.25f;

        public static bool IsOpen=>isOpen;
        public static void Toggle(){if(isOpen)Close();else Open();}
        public static void MarkDirty()=>dirty=true;
        public static void SetLinkCode(string code){if(txtLinkCode!=null)UIFactory.SetText(txtLinkCode,$"<color=#00FFFF>{code}</color>  — type <color=#FFFFFF>!link {code}</color> in Discord");}

        public static void Open()
        {
            if(!UIFactory.Ready){UIFactory.InitTypes();UIFactory.InitFont();}if(!UIFactory.Ready)return;
            bool inRoom=GameStateWatcher.IsInRoom;
            inGameMode=inRoom;
            // Always use our own overlay canvas — guarantees we render on top of all ROUNDS UI
            EnsureOverlayCanvas();
            if(!pageBuilt||pageGO==null||pageGO.transform.parent!=overlayCanvasGO.transform){if(pageGO!=null)UnityEngine.Object.Destroy(pageGO);pageBuilt=false;BuildPage(overlayCanvasGO.transform);if(!pageBuilt)return;}
            pageGO.SetActive(true);
            try{UIFactory.tCanvas?.GetMethod("ForceUpdateCanvases",BindingFlags.Public|BindingFlags.Static)?.Invoke(null,null);}catch{}
            isOpen=true;dirty=true;RefreshData();ApiClient.ResetQueueCountTimer();Plugin.Log.LogInfo($"[NATIVE] Opened competitive page (inGame={inGameMode})");
        }

        public static void Close(){if(pageGO!=null)pageGO.SetActive(false);isOpen=false;try{TrailPreview.Stop();}catch{}Plugin.Log.LogInfo("[NATIVE] Closed competitive page");}

        private static float dataCheckTimer;private static int lastMatchCount=-1,lastLBCount=-1,lastCardCount=-1;
        public static void Tick()
        {
            if(!isOpen||!pageBuilt)return;if(pageGO==null){isOpen=false;pageBuilt=false;return;}
            if(Input.GetKeyDown(KeyCode.Escape)){Close();return;}
            dataCheckTimer+=Time.deltaTime;if(dataCheckTimer>=0.3f){dataCheckTimer=0f;int mc=ApiClient.CachedMatchHistory?.Count??0,lc=ApiClient.CachedLeaderboard?.entries?.Length??0,cc=ApiClient.CachedCardStats?.Count??0;if(mc!=lastMatchCount||lc!=lastLBCount||cc!=lastCardCount){lastMatchCount=mc;lastLBCount=lc;lastCardCount=cc;dirty=true;}}
            if(dirty){dirty=false;RefreshCurrentTab();}
        }

        private static void FindMainMenuGroup(){var all=UnityEngine.Object.FindObjectsOfType<ListMenuButton>();Type tt=null;PropertyInfo tp=null;foreach(var a in AppDomain.CurrentDomain.GetAssemblies()){tt=a.GetType("TMPro.TMP_Text");if(tt!=null)break;}if(tt!=null)tp=tt.GetProperty("text",BindingFlags.Public|BindingFlags.Instance);foreach(var b in all){if(tp==null)break;try{var tc=b.GetComponentInChildren(tt,true);if(tc==null)continue;if((tp.GetValue(tc)as string??"").Trim().ToUpper()=="QUIT"){mainMenuGroup=b.transform.parent.gameObject;Plugin.Log.LogInfo($"[NATIVE] Found main menu group: {mainMenuGroup.name}");return;}}catch{}}Plugin.Log.LogWarning("[NATIVE] Could not find QUIT button");}
        private static Transform FindCanvasAbove(Transform from){Transform c=from;while(c!=null){if(UIFactory.tCanvas!=null&&c.GetComponent(UIFactory.tCanvas)!=null){Plugin.Log.LogInfo($"[NATIVE] Found Canvas: {c.gameObject.name}");return c;}c=c.parent;}return from.parent??from;}
        private static void EnsureOverlayCanvas(){if(overlayCanvasGO!=null)return;overlayCanvasGO=new GameObject("CR_OverlayCanvas");overlayCanvasGO.hideFlags=HideFlags.HideAndDontSave;UnityEngine.Object.DontDestroyOnLoad(overlayCanvasGO);if(UIFactory.tCanvas!=null){var cv=overlayCanvasGO.AddComponent(UIFactory.tCanvas);var bf=BindingFlags.Public|BindingFlags.Instance;UIFactory.tCanvas.GetProperty("renderMode",bf)?.SetValue(cv,Enum.ToObject(UIFactory.tCanvas.GetProperty("renderMode",bf).PropertyType,0));UIFactory.tCanvas.GetProperty("sortingOrder",bf)?.SetValue(cv,30000);}if(UIFactory.tCanvasScaler!=null){var sc=overlayCanvasGO.AddComponent(UIFactory.tCanvasScaler);var bf=BindingFlags.Public|BindingFlags.Instance;var smp=UIFactory.tCanvasScaler.GetProperty("uiScaleMode",bf);if(smp!=null)smp.SetValue(sc,Enum.ToObject(smp.PropertyType,1));UIFactory.tCanvasScaler.GetProperty("referenceResolution",bf)?.SetValue(sc,new Vector2(1920,1080));}if(UIFactory.tGR!=null)overlayCanvasGO.AddComponent(UIFactory.tGR);Plugin.Log.LogInfo("[NATIVE] Created persistent overlay Canvas");}

        private static void BuildPage(Transform canvasParent)
        {
            try{rankedRows.Clear();casualRows.Clear();lbRows.Clear();cardRows.Clear();sessionOppTexts.Clear();
            pageGO=new GameObject("CompetitiveRoundsPage");pageGO.transform.SetParent(canvasParent,false);var rt=pageGO.AddComponent<RectTransform>();rt.anchorMin=Vector2.zero;rt.anchorMax=Vector2.one;rt.offsetMin=Vector2.zero;rt.offsetMax=Vector2.zero;pageGO.SetActive(false);
            var bgGO=UIFactory.CreatePanel("BG",pageGO.transform,C_BG);var bgImg=bgGO.GetComponent(UIFactory.tImage);if(bgImg!=null)UIFactory.tImage.GetProperty("raycastTarget",BindingFlags.Public|BindingFlags.Instance)?.SetValue(bgImg,true);
            var content=new GameObject("Content");content.transform.SetParent(pageGO.transform,false);var crt=content.AddComponent<RectTransform>();crt.anchorMin=Vector2.zero;crt.anchorMax=Vector2.one;crt.offsetMin=new Vector2(30,10);crt.offsetMax=new Vector2(-30,-10);UIFactory.AddVLG(content,spacing:4,padL:8,padR:8,padT:8,padB:8);

            var titleRow=new GameObject("TitleRow");titleRow.transform.SetParent(content.transform,false);titleRow.AddComponent<RectTransform>();UIFactory.AddHLG(titleRow,spacing:8,forceExpandH:true);UIFactory.AddLE(titleRow,prefH:42,minH:42,flexH:0);
            UIFactory.CreateText("Title",titleRow.transform,"SID'S COMPETITIVE ROUNDS",35f,C_WHITE,UIFactory.AlignMidCenter,sizeDelta:new Vector2(0,42));
            var titleTxtGO=titleRow.transform.GetChild(0).gameObject;if(UIFactory.tLE!=null){var tle=titleTxtGO.GetComponent(UIFactory.tLE);if(tle!=null)UnityEngine.Object.Destroy(tle as UnityEngine.Object);}UIFactory.AddLE(titleTxtGO,flexW:1,prefH:42);
            UIFactory.CreateButton("BackBtn",titleRow.transform,"< BACK",16f,C_LABEL,C_BTN,()=>Close(),sizeDelta:new Vector2(85,34));
            // Server-status indicator row, just below the title. Hidden when the API looks fine.
            // Replaces the old in-game IMGUI banner, which was firing during quiet periods even
            // when the server was healthy (no recent attempts → no recent successes either).
            var srvRow=new GameObject("SrvRow");srvRow.transform.SetParent(content.transform,false);srvRow.AddComponent<RectTransform>();UIFactory.AddHLG(srvRow,spacing:6,forceExpandH:true);UIFactory.AddLE(srvRow,prefH:22,minH:22,flexH:0);
            txtServerStatus=UIFactory.CreateText("SrvSt",srvRow.transform,"",14f,new Color(1f,0.7f,0.6f),UIFactory.AlignMidCenter,sizeDelta:new Vector2(0,22));
            var srvTxtGO=(txtServerStatus as Component)?.gameObject;if(srvTxtGO!=null&&UIFactory.tLE!=null){var tle=srvTxtGO.GetComponent(UIFactory.tLE);if(tle!=null)UnityEngine.Object.Destroy(tle as UnityEngine.Object);}if(srvTxtGO!=null)UIFactory.AddLE(srvTxtGO,flexW:1,prefH:22);
            UIFactory.SetBold(txtServerStatus,true);
            srvRow.SetActive(false);  // off until ApiLooksDown
            srvStatusRow=srvRow;

            BuildRankedRow(content.transform);BuildTabBar(content.transform);
            tabPanels=new GameObject[7];tabPanels[0]=BuildMyStatsTab(content.transform);tabPanels[1]=BuildLeaderboardTab(content.transform);tabPanels[2]=BuildCardStatsTab(content.transform);tabPanels[3]=BuildAchievementsTab(content.transform);tabPanels[4]=BuildShopTab(content.transform);tabPanels[5]=BuildSettingsTab(content.transform);tabPanels[6]=BuildAdminTab(content.transform);

            var bottom=new GameObject("Bottom");bottom.transform.SetParent(content.transform,false);bottom.AddComponent<RectTransform>();UIFactory.AddHLG(bottom,spacing:8,forceExpandH:true);UIFactory.AddLE(bottom,prefH:26,minH:26,flexH:0);
            UIFactory.CreateText("Ver",bottom.transform,$"<b>v{Plugin.ModVersion}</b>",13f,C_DIM,UIFactory.AlignMidLeft,sizeDelta:new Vector2(90,22));
            txtVersionStatus=UIFactory.CreateText("VerStatus",bottom.transform,"",12f,C_DIM,UIFactory.AlignMidLeft,sizeDelta:new Vector2(130,22));
            updateBtn=UIFactory.CreateButton("UpdateBtn",bottom.transform,"Update",14f,C_WHITE,new Color(0.6f,0.4f,0.1f,0.9f),()=>{ApiClient.StartAutoUpdate();},sizeDelta:new Vector2(75,26));updateBtn.SetActive(false);
            UIFactory.CreateButton("Discord",bottom.transform,"Discord",14f,Color.white,new Color(0.345f,0.396f,0.949f,0.9f),()=>{Application.OpenURL("https://discord.gg/comp-rounds");},sizeDelta:new Vector2(80,26));
            UIFactory.CreateButton("GitHub",bottom.transform,"GitHub",14f,Color.white,new Color(0.2f,0.2f,0.2f,0.9f),()=>{Application.OpenURL("https://github.com/SidNDeed/SidsCompetitiveRounds");},sizeDelta:new Vector2(75,26));
            var bSp=new GameObject("S");bSp.transform.SetParent(bottom.transform,false);bSp.AddComponent<RectTransform>();UIFactory.AddLE(bSp,flexW:1);
            UIFactory.CreateButton("RefreshBtn",bottom.transform,"Refresh",15f,C_WHITE,C_BTN,()=>{RefreshData();dirty=true;},sizeDelta:new Vector2(85,26));
            SwitchTab(0);pageBuilt=true;Plugin.Log.LogInfo("[NATIVE] Competitive page built");
            }catch(Exception ex){Plugin.Log.LogError($"[NATIVE] BuildPage failed: {ex}");pageBuilt=false;}
        }

        private static void BuildRankedRow(Transform parent)
        {
            var row=new GameObject("RankedRow");row.transform.SetParent(parent,false);row.AddComponent<RectTransform>();UIFactory.AddHLG(row,spacing:10,padL:4,padR:4,forceExpandH:true);UIFactory.AddLE(row,prefH:26,minH:26,flexH:0);
            var pn=UIFactory.CreateText("PName",row.transform,ApiClient.CachedPlayerStats?.display_name??MatchTracker.LocalDisplayName??"",20f,C_SUB,UIFactory.AlignMidLeft,sizeDelta:new Vector2(110,28));UIFactory.SetBold(pn,true);
            txtRankedStatus=UIFactory.CreateText("RS",row.transform,"RANKED: OFF",18f,Color.gray,UIFactory.AlignMidLeft,sizeDelta:new Vector2(140,28));UIFactory.SetBold(txtRankedStatus,true);
            qSearchBtn=UIFactory.CreateButton("Search",row.transform,"Search Ranked",15f,C_WHITE,C_BTN,()=>{var id=MatchTracker.LocalSteamId;if(!string.IsNullOrEmpty(id)&&id!="unknown")ApiClient.JoinQueue(id,MatchTracker.LocalDisplayName,null,false);},sizeDelta:new Vector2(130,26));
            qCancelBtn=UIFactory.CreateButton("Cancel",row.transform,"Cancel",15f,C_WHITE,C_BTN,()=>ApiClient.LeaveQueue(MatchTracker.LocalSteamId),sizeDelta:new Vector2(70,26));
            rankOnBtn=UIFactory.CreateButton("RankOn",row.transform,"Enable",15f,C_GREEN,C_BTN,()=>{Plugin.RankedEnabled.Value=true;var id=MatchTracker.LocalSteamId;if(!string.IsNullOrEmpty(id)&&id!="unknown")ApiClient.ToggleRanked(id,true);dirty=true;},sizeDelta:new Vector2(70,26));
            rankOffBtn=UIFactory.CreateButton("RankOff",row.transform,"Disable",15f,C_RED,C_BTN,()=>{Plugin.RankedEnabled.Value=false;var id=MatchTracker.LocalSteamId;if(!string.IsNullOrEmpty(id)&&id!="unknown"){ApiClient.ToggleRanked(id,false);if(ApiClient.CurrentQueueState!=ApiClient.QueueState.Idle)ApiClient.LeaveQueue(id);}dirty=true;},sizeDelta:new Vector2(70,26));
            txtQueueInfo=UIFactory.CreateText("QI",row.transform,"",18f,C_BLUE,UIFactory.AlignMidLeft,sizeDelta:new Vector2(340,28));UIFactory.SetBold(txtQueueInfo,true);
            var sp=new GameObject("S");sp.transform.SetParent(row.transform,false);sp.AddComponent<RectTransform>();UIFactory.AddLE(sp,flexW:1);
            qMatchPanel=new GameObject("MatchPanel");qMatchPanel.transform.SetParent(parent,false);qMatchPanel.AddComponent<RectTransform>();UIFactory.AddVLG(qMatchPanel,spacing:4,padL:8);UIFactory.AddLE(qMatchPanel,prefH:50,minH:50,flexH:0);
            txtMatchFound=UIFactory.CreateText("MF",qMatchPanel.transform,"MATCH FOUND!",18f,C_GREEN,UIFactory.AlignMidLeft,sizeDelta:new Vector2(700,24));UIFactory.SetBold(txtMatchFound,true);
            var matchBtnRow=new GameObject("MBR");matchBtnRow.transform.SetParent(qMatchPanel.transform,false);matchBtnRow.AddComponent<RectTransform>();UIFactory.AddHLG(matchBtnRow,spacing:8,forceExpandH:false);UIFactory.AddLE(matchBtnRow,prefH:26,minH:26,flexH:0);
            readyBtn=UIFactory.CreateButton("Ready",matchBtnRow.transform,"Ready Up",15f,C_WHITE,new Color(0.2f,0.5f,0.2f,0.9f),()=>{var id=MatchTracker.LocalSteamId;if(!string.IsNullOrEmpty(id)&&id!="unknown")ApiClient.ReadyUp(id);},sizeDelta:new Vector2(90,24));
            /* The "Waiting for opponent..." label sits in the match-found HLG between the Ready and
             * Decline buttons. Previously the wrapper had no LayoutElement → HLG collapsed it to 0
             * width, which meant the child text (center-anchored by default, sizeDelta 350) drew 175
             * units left of that collapsed point and ran off-screen. Create the text directly in
             * matchBtnRow with MidLeft alignment; CreateText bakes its own LE from sizeDelta so HLG
             * reserves the correct width. */
            txtConnectLabel=UIFactory.CreateText("CT",matchBtnRow.transform,"Waiting for opponent...",15f,C_BLUE,UIFactory.AlignMidLeft,sizeDelta:new Vector2(320,24));
            connectLabel=(txtConnectLabel as Component)?.gameObject;
            if(connectLabel!=null)connectLabel.SetActive(false);
            declineBtn=UIFactory.CreateButton("Decline",matchBtnRow.transform,"Decline",15f,C_WHITE,C_BTN,()=>{ApiClient.DeclineMatch(MatchTracker.LocalSteamId);},sizeDelta:new Vector2(70,24));qMatchPanel.SetActive(false);
        }

        private static void BuildTabBar(Transform parent){var bar=new GameObject("TabBar");bar.transform.SetParent(parent,false);bar.AddComponent<RectTransform>();UIFactory.AddHLG(bar,spacing:4);UIFactory.AddLE(bar,prefH:28,minH:28,flexH:0);tabButtons=new GameObject[7];tabTexts=new object[7];for(int i=0;i<7;i++){int idx=i;var btn=UIFactory.CreateButton($"Tab{i}",bar.transform,TAB_NAMES[i],13f,C_LABEL,C_TAB,()=>SwitchTab(idx),sizeDelta:new Vector2(0,26));if(UIFactory.tLE!=null){var el=btn.GetComponent(UIFactory.tLE);if(el!=null)UnityEngine.Object.Destroy(el as UnityEngine.Object);}UIFactory.AddLE(btn,prefH:26,minH:26,flexW:1,flexH:0);tabButtons[i]=btn;tabTexts[i]=UIFactory.GetButtonText(btn);}/* Admin tab visibility flips on as soon as IsAdmin resolves true (poll-driven update from RefreshCurrentTab). */tabButtons[6].SetActive(ApiClient.IsAdmin);}
        private static readonly string[] TAB_NAMES={"My Stats","Leaderboard","Card Stats","Achievements","Shop","Settings","Admin"};
        private static void SwitchTab(int idx){currentTab=idx;for(int i=0;i<7;i++){if(tabPanels[i]!=null)tabPanels[i].SetActive(i==idx);UIFactory.SetImageColor(tabButtons[i],i==idx?C_TABACT:C_TAB);if(tabTexts[i]!=null){UIFactory.SetColor(tabTexts[i],i==idx?C_WHITE:C_LABEL);UIFactory.SetBold(tabTexts[i],i==idx);}}if(idx==1){if(ApiClient.CachedLeaderboard==null){ApiClient.FetchLeaderboard();ApiClient.FetchRecentSeries();}ApiClient.FetchActiveSeries();var sid=MatchTracker.LocalSteamId;if(!string.IsNullOrEmpty(sid)&&sid!="unknown")ApiClient.FetchMyBets(sid);}if(idx==2&&ApiClient.CachedCardStats==null)ApiClient.FetchCardStats(200,MatchTracker.LocalSteamId);if(idx==3&&ApiClient.CachedAchievements==null){var id=MatchTracker.LocalSteamId;if(!string.IsNullOrEmpty(id)&&id!="unknown")ApiClient.FetchAchievements(id);}if(idx==4){var id=MatchTracker.LocalSteamId;if(!string.IsNullOrEmpty(id)&&id!="unknown"){ApiClient.FetchShopItems(id);ApiClient.FetchInventory(id);}else ApiClient.FetchShopItems();}if(idx==6){var id=MatchTracker.LocalSteamId;if(!string.IsNullOrEmpty(id)&&ApiClient.IsAdmin){ApiClient.FetchFlaggedMatches(id);ApiClient.FetchBannedUsers(id);}}dirty=true;}

        private static GameObject BuildMyStatsTab(Transform parent){var panel=new GameObject("MyStats");panel.transform.SetParent(parent,false);panel.AddComponent<RectTransform>();UIFactory.AddHLG(panel,spacing:8);UIFactory.AddLE(panel,flexH:1);var left=new GameObject("Left");left.transform.SetParent(panel.transform,false);left.AddComponent<RectTransform>();UIFactory.AddVLG(left,spacing:4);UIFactory.AddLE(left,prefW:380);var rBox=UIFactory.CreatePanel("RB",left.transform,C_PANEL);UIFactory.AddVLG(rBox,spacing:2,padL:10,padR:10,padT:6,padB:6);UIFactory.AddLE(rBox,flexH:0);var glHdr=UIFactory.CreateText("RL",rBox.transform,"Glicko-2 Rating",19f,C_SUB,sizeDelta:new Vector2(250,28));UIFactory.SetCharSpacing(glHdr,1f);var rRow=new GameObject("RR");rRow.transform.SetParent(rBox.transform,false);rRow.AddComponent<RectTransform>();UIFactory.AddHLG(rRow,spacing:12);UIFactory.AddLE(rRow,prefH:38);txtRating=UIFactory.CreateText("Rat",rRow.transform,"1500",30f,C_WHITE,UIFactory.AlignMidLeft,sizeDelta:new Vector2(110,38));UIFactory.SetBold(txtRating,true);txtRD=UIFactory.CreateText("RD",rRow.transform,"RD: 350",18f,C_LABEL,UIFactory.AlignMidLeft,sizeDelta:new Vector2(240,38));var xBox=UIFactory.CreatePanel("XB",left.transform,C_PANEL);UIFactory.AddVLG(xBox,spacing:2,padL:10,padR:10,padT:6,padB:6);UIFactory.AddLE(xBox,flexH:0);var lvRow=new GameObject("LR");lvRow.transform.SetParent(xBox.transform,false);lvRow.AddComponent<RectTransform>();UIFactory.AddHLG(lvRow,spacing:8);UIFactory.AddLE(lvRow,prefH:28);txtLevel=UIFactory.CreateText("Lv",lvRow.transform,"Level 1",19f,C_BLUE,UIFactory.AlignMidLeft,sizeDelta:new Vector2(100,28));UIFactory.SetBold(txtLevel,true);txtXPProg=UIFactory.CreateText("XPP",lvRow.transform,"",16f,C_LABEL,UIFactory.AlignMidLeft,sizeDelta:new Vector2(130,28));var xSp=new GameObject("S");xSp.transform.SetParent(lvRow.transform,false);xSp.AddComponent<RectTransform>();UIFactory.AddLE(xSp,flexW:1);txtTotalXP=UIFactory.CreateText("TXP",lvRow.transform,"0 XP",16f,C_LABEL,UIFactory.AlignMidRight,sizeDelta:new Vector2(110,28));xpFill=UIFactory.CreateFillBar("XP",xBox.transform,new Color(0.2f,0.2f,0.25f,0.8f),new Color(0.3f,0.7f,1f,0.9f),10f);var recBox=UIFactory.CreatePanel("RecB",left.transform,C_PANEL);UIFactory.AddVLG(recBox,spacing:1,padL:10,padR:10,padT:6,padB:6);UIFactory.AddLE(recBox,flexH:0);UIFactory.CreateText("RecL",recBox.transform,"Record",19f,C_SUB,sizeDelta:new Vector2(340,28));txtRankedRec=UIFactory.CreateText("RR",recBox.transform,"",16f,C_WHITE,sizeDelta:new Vector2(340,24));txtRankedStrk=UIFactory.CreateText("RS",recBox.transform,"",15f,C_LABEL,sizeDelta:new Vector2(340,22));txtCasualRec=UIFactory.CreateText("CR",recBox.transform,"",16f,C_WHITE,sizeDelta:new Vector2(340,24));txtCasualStrk=UIFactory.CreateText("CS",recBox.transform,"",15f,C_LABEL,sizeDelta:new Vector2(340,22));txtSweeps=UIFactory.CreateText("SW",recBox.transform,"",16f,C_WHITE,sizeDelta:new Vector2(340,24));txtTotalRec=UIFactory.CreateText("TR",recBox.transform,"",15f,C_LABEL,sizeDelta:new Vector2(340,22));txtAccuracy=UIFactory.CreateText("AC",recBox.transform,"",15f,C_LABEL,sizeDelta:new Vector2(340,44));var sesBox=UIFactory.CreatePanel("SB",left.transform,C_PANEL);UIFactory.AddVLG(sesBox,spacing:3,padL:10,padR:10,padT:8,padB:8);UIFactory.AddLE(sesBox,flexH:0);UIFactory.CreateText("SL",sesBox.transform,"Session Info",19f,new Color(0.7f,0.8f,1f),sizeDelta:new Vector2(340,28));txtSessionSum=UIFactory.CreateText("SS",sesBox.transform,"No games this session",17f,C_DIM,sizeDelta:new Vector2(340,26));txtSessionSplit=UIFactory.CreateText("SSp",sesBox.transform,"",16f,C_LABEL,sizeDelta:new Vector2(340,24));txtSessionSweeps=UIFactory.CreateText("SSw",sesBox.transform,"",16f,C_WHITE,sizeDelta:new Vector2(340,24));txtSessionOppLifetime=UIFactory.CreateText("SOL",sesBox.transform,"",15f,new Color(0.6f,0.75f,1f),sizeDelta:new Vector2(340,22));sessionOppContainer=new GameObject("SOC");sessionOppContainer.transform.SetParent(sesBox.transform,false);sessionOppContainer.AddComponent<RectTransform>();UIFactory.AddVLG(sessionOppContainer,spacing:1);
        var linkBox=UIFactory.CreatePanel("LkB",left.transform,C_PANEL);UIFactory.AddVLG(linkBox,spacing:4,padL:10,padR:10,padT:6,padB:6);UIFactory.AddLE(linkBox,flexH:0);UIFactory.CreateText("LkL",linkBox.transform,"Discord Link",19f,new Color(0.55f,0.55f,0.95f),sizeDelta:new Vector2(340,28));var lkRow=new GameObject("LkR");lkRow.transform.SetParent(linkBox.transform,false);lkRow.AddComponent<RectTransform>();UIFactory.AddHLG(lkRow,spacing:8);UIFactory.AddLE(lkRow,prefH:28);linkCodeBtn=UIFactory.CreateButton("LkBtn",lkRow.transform,"Get Link Code",15f,C_WHITE,C_BTN,()=>{var id=MatchTracker.LocalSteamId;if(!string.IsNullOrEmpty(id)&&id!="unknown")ApiClient.GenerateLinkCode(id);},sizeDelta:new Vector2(130,26));/* Click-to-reveal on the link text — Discord ID/username defaults hidden for streamers.
 * TMP text IS already a Graphic; adding an Image to the same GO throws. Just enable its own raycastTarget. */
txtLinkCode=UIFactory.CreateText("LkC",lkRow.transform,"Type !link CODE in Discord",15f,C_DIM,sizeDelta:new Vector2(240,26),raycastTarget:true);{var lkTextComp=txtLinkCode as Component;if(lkTextComp!=null){var ch=lkTextComp.gameObject.AddComponent<ClickHandler>();ch.onClick=()=>{if(ClickGuard.Claim()){discordRevealed=!discordRevealed;dirty=true;}};}}
        /* In-game <-> Discord chat panel. Scrollable log fills the box; users send via hotkey T (IMGUI overlay). */
        var chatBox=UIFactory.CreatePanel("CB",left.transform,C_PANEL);UIFactory.AddVLG(chatBox,spacing:4,padL:10,padR:10,padT:6,padB:6);UIFactory.AddLE(chatBox,flexH:0);UIFactory.CreateText("CH",chatBox.transform,"Chat  <color=#888>(press T to send)</color>",17f,new Color(0.7f,0.85f,1f),sizeDelta:new Vector2(340,26));var chSV=UIFactory.CreateScrollView("ChSV",chatBox.transform,spacing:0);UIFactory.AddLE(chSV.scrollGO,prefH:160,minH:160,flexH:0);chatScrollRect=chSV.scrollGO.GetComponent(UIFactory.tScrollRect);txtChatLog=UIFactory.CreateText("ChLog",chSV.content.transform,"<color=#888><i>No messages yet. Anyone chatting here or in #scr-discussion on Discord will appear.</i></color>",14f,C_WHITE,UIFactory.AlignTopLeft,sizeDelta:new Vector2(360,400));UIFactory.SetWordWrap(txtChatLog,true);
/* CreateText baked a LayoutElement with prefH=400 onto the chat-log GO. With the parent VLG/CSF reading
 * that, a single very long message (e.g. a 9000-char changelog paste) renders as TMP overflow but the
 * scroll content stays clamped at 400px → unreachable bottom. Zero out the prefH so TMP's own
 * ILayoutElement.preferredHeight (its actual rendered height) drives the content size instead. */
{var chatLE=(txtChatLog as Component)?.gameObject.GetComponent(UIFactory.tLE);if(chatLE!=null){var prefHProp=UIFactory.tLE.GetProperty("preferredHeight",BindingFlags.Public|BindingFlags.Instance);prefHProp?.SetValue(chatLE,-1f);}}
        var right=new GameObject("Right");right.transform.SetParent(panel.transform,false);right.AddComponent<RectTransform>();UIFactory.AddVLG(right,spacing:4);UIFactory.AddLE(right,flexW:1,flexH:1);var rkBox=UIFactory.CreatePanel("RkB",right.transform,C_PANEL);UIFactory.AddVLG(rkBox,spacing:1,padL:8,padR:8,padT:6,padB:6);UIFactory.AddLE(rkBox,flexH:1);UIFactory.CreateText("RkH",rkBox.transform,"Ranked History",21f,C_GOLD,sizeDelta:new Vector2(250,30));txtOppSummary=UIFactory.CreateText("OS",rkBox.transform,"",15f,new Color(0.7f,0.8f,1f),sizeDelta:new Vector2(500,22));var rkSV=UIFactory.CreateScrollView("RkSV",rkBox.transform,spacing:1);UIFactory.AddLE(rkSV.scrollGO,flexH:1);rankedContainer=rkSV.content;for(int i=0;i<15;i++)rankedRows.Add(CreateHistoryRow(rankedContainer.transform,$"rr{i}"));var rPg=new GameObject("RPg");rPg.transform.SetParent(rkBox.transform,false);rPg.AddComponent<RectTransform>();UIFactory.AddHLG(rPg,spacing:6,forceExpandH:true);UIFactory.AddLE(rPg,prefH:20,flexH:0);var rS1=new GameObject("S");rS1.transform.SetParent(rPg.transform,false);rS1.AddComponent<RectTransform>();UIFactory.AddLE(rS1,flexW:1);rPrev=UIFactory.CreateButton("rP",rPg.transform,"< Prev",10f,C_LABEL,C_BTN,()=>{if(rankedPage>0){rankedPage--;dirty=true;}},sizeDelta:new Vector2(50,18));txtRankedPage=UIFactory.CreateText("rPI",rPg.transform,"",10f,C_LABEL,UIFactory.AlignMidCenter,sizeDelta:new Vector2(35,18));rNext=UIFactory.CreateButton("rN",rPg.transform,"Next >",10f,C_LABEL,C_BTN,()=>{rankedPage++;dirty=true;},sizeDelta:new Vector2(50,18));var rS2=new GameObject("S");rS2.transform.SetParent(rPg.transform,false);rS2.AddComponent<RectTransform>();UIFactory.AddLE(rS2,flexW:1);
        var csBox=UIFactory.CreatePanel("CsB",right.transform,C_PANEL);UIFactory.AddVLG(csBox,spacing:1,padL:8,padR:8,padT:6,padB:6);UIFactory.AddLE(csBox,flexH:1);UIFactory.CreateText("CsH",csBox.transform,"Casual History",21f,C_SUB,sizeDelta:new Vector2(250,30));var csSV=UIFactory.CreateScrollView("CsSV",csBox.transform,spacing:1);UIFactory.AddLE(csSV.scrollGO,flexH:1);casualContainer=csSV.content;for(int i=0;i<12;i++)casualRows.Add(CreateHistoryRow(casualContainer.transform,$"cr{i}"));var cPg=new GameObject("CPg");cPg.transform.SetParent(csBox.transform,false);cPg.AddComponent<RectTransform>();UIFactory.AddHLG(cPg,spacing:6,forceExpandH:true);UIFactory.AddLE(cPg,prefH:20,flexH:0);var cS1=new GameObject("S");cS1.transform.SetParent(cPg.transform,false);cS1.AddComponent<RectTransform>();UIFactory.AddLE(cS1,flexW:1);cPrev=UIFactory.CreateButton("cP",cPg.transform,"< Prev",10f,C_LABEL,C_BTN,()=>{if(casualPage>0){casualPage--;dirty=true;}},sizeDelta:new Vector2(50,18));txtCasualPage=UIFactory.CreateText("cPI",cPg.transform,"",10f,C_LABEL,UIFactory.AlignMidCenter,sizeDelta:new Vector2(35,18));cNext=UIFactory.CreateButton("cN",cPg.transform,"Next >",10f,C_LABEL,C_BTN,()=>{casualPage++;dirty=true;},sizeDelta:new Vector2(50,18));var cS2=new GameObject("S");cS2.transform.SetParent(cPg.transform,false);cS2.AddComponent<RectTransform>();UIFactory.AddLE(cS2,flexW:1);return panel;}

        private static HistoryRow CreateHistoryRow(Transform parent,string name){var row=new HistoryRow();row.seriesGO=new GameObject(name+"s");row.seriesGO.transform.SetParent(parent,false);row.seriesGO.AddComponent<RectTransform>();UIFactory.AddHLG(row.seriesGO,spacing:4,padL:4);UIFactory.AddLE(row.seriesGO,prefH:25);row.txtSeriesHead=UIFactory.CreateText("sh",row.seriesGO.transform,"",19f,C_GREEN,sizeDelta:new Vector2(500,25));row.txtSeriesElo=UIFactory.CreateText("se",row.seriesGO.transform,"",19f,C_GREEN,UIFactory.AlignMidRight,sizeDelta:new Vector2(160,25));row.seriesGO.SetActive(false);row.root=new GameObject(name);row.root.transform.SetParent(parent,false);row.root.AddComponent<RectTransform>();UIFactory.AddVLG(row.root,spacing:0,padL:4);var main=new GameObject("m");main.transform.SetParent(row.root.transform,false);main.AddComponent<RectTransform>();UIFactory.AddHLG(main,spacing:4);UIFactory.AddLE(main,prefH:25);row.txtResult=UIFactory.CreateText("r",main.transform,"",19f,C_GREEN,UIFactory.AlignMidLeft,sizeDelta:new Vector2(200,25));row.txtOpp=UIFactory.CreateText("o",main.transform,"",18f,C_WHITE,UIFactory.AlignMidLeft,sizeDelta:new Vector2(180,25));var sp=new GameObject("S");sp.transform.SetParent(main.transform,false);sp.AddComponent<RectTransform>();UIFactory.AddLE(sp,flexW:1);row.txtXP=UIFactory.CreateText("x",main.transform,"",16f,C_BLUE,UIFactory.AlignMidRight,sizeDelta:new Vector2(65,25));row.txtDate=UIFactory.CreateText("d",main.transform,"",15f,C_DIM,UIFactory.AlignMidRight,sizeDelta:new Vector2(45,25));row.txtCards=UIFactory.CreateText("c",row.root.transform,"",19f,new Color(0.6f,0.7f,0.9f),sizeDelta:new Vector2(900,25));UIFactory.SetCharSpacing(row.txtCards,1.5f);row.txtOppCards=UIFactory.CreateText("oc",row.root.transform,"",19f,new Color(0.9f,0.6f,0.5f),sizeDelta:new Vector2(900,25));UIFactory.SetCharSpacing(row.txtOppCards,1.5f);row.root.SetActive(false);return row;}

        private static object txtLBPlayerName;
        private static GameObject BuildLeaderboardTab(Transform parent){var panel=new GameObject("Leaderboard");panel.transform.SetParent(parent,false);panel.AddComponent<RectTransform>();UIFactory.AddHLG(panel,spacing:6);UIFactory.AddLE(panel,flexH:1);/* === LEFT: Recent Ranked Series === */var seriesCol=UIFactory.CreatePanel("LBSeries",panel.transform,C_PANEL);UIFactory.AddVLG(seriesCol,spacing:2,padL:8,padR:8,padT:6,padB:6);UIFactory.AddLE(seriesCol,prefW:400,minW:340,flexH:1);txtLiveHeader=UIFactory.CreateText("RSL",seriesCol.transform,"<color=#FF6688>● Live Ranked Games</color>",17f,C_WHITE,UIFactory.AlignMidLeft,sizeDelta:new Vector2(280,26));txtLiveSeries=UIFactory.CreateText("LIVE",seriesCol.transform,"<color=#666><i>No live games right now.</i></color>",13f,C_WHITE,UIFactory.AlignTopLeft,sizeDelta:new Vector2(280,24));UIFactory.SetWordWrap(txtLiveSeries,true);liveBetsContainer=new GameObject("LiveBets");liveBetsContainer.transform.SetParent(seriesCol.transform,false);liveBetsContainer.AddComponent<RectTransform>();UIFactory.AddVLG(liveBetsContainer,spacing:2);/* No LayoutElement: VLG on this container already sums child preferred heights with priority 0 and reports that as its preferred height, so the parent VLG sizes us correctly. Previously an LE with prefH:0 priority:1 was overriding that sum to 0, collapsing the live series into the recent series list below. */
/* Live-series pagination header row — shows "X live (page N/M) < >" when >5 series. */
liveBetsPager=new GameObject("LivePg");liveBetsPager.transform.SetParent(seriesCol.transform,false);liveBetsPager.AddComponent<RectTransform>();UIFactory.AddHLG(liveBetsPager,spacing:4,forceExpandH:true);UIFactory.AddLE(liveBetsPager,prefH:18,flexH:0);
liveBetsPrev=UIFactory.CreateButton("lvP",liveBetsPager.transform,"< Prev",10f,C_LABEL,C_BTN,()=>{if(liveSeriesPage>0){liveSeriesPage--;dirty=true;}},sizeDelta:new Vector2(50,18));
txtLiveBetsPage=UIFactory.CreateText("lvPI",liveBetsPager.transform,"",10f,C_LABEL,UIFactory.AlignMidCenter,sizeDelta:new Vector2(80,18));
liveBetsNext=UIFactory.CreateButton("lvN",liveBetsPager.transform,"Next >",10f,C_LABEL,C_BTN,()=>{liveSeriesPage++;dirty=true;},sizeDelta:new Vector2(50,18));
liveBetsPager.SetActive(false);
/* Visual spacer between Live and Recent panels — was visually jammed previously. */
{var liveRecentSpacer=new GameObject("LRSp");liveRecentSpacer.transform.SetParent(seriesCol.transform,false);liveRecentSpacer.AddComponent<RectTransform>();UIFactory.AddLE(liveRecentSpacer,prefH:18,minH:18,flexH:0);}
UIFactory.CreateText("RSL",seriesCol.transform,"<color=#99AAEE>Recent Ranked Series</color>",17f,C_WHITE,UIFactory.AlignMidLeft,sizeDelta:new Vector2(280,26));var rsSV=UIFactory.CreateScrollView("RSSV",seriesCol.transform,spacing:1);UIFactory.AddLE(rsSV.scrollGO,flexH:1);txtRecentSeries=UIFactory.CreateText("RST",rsSV.content.transform,"Loading...",16f,C_DIM,sizeDelta:new Vector2(280,20));var sPg=new GameObject("SPg");sPg.transform.SetParent(seriesCol.transform,false);sPg.AddComponent<RectTransform>();UIFactory.AddHLG(sPg,spacing:4,forceExpandH:true);UIFactory.AddLE(sPg,prefH:20,flexH:0);var sS1=new GameObject("S");sS1.transform.SetParent(sPg.transform,false);sS1.AddComponent<RectTransform>();UIFactory.AddLE(sS1,flexW:1);seriesPrev=UIFactory.CreateButton("sP",sPg.transform,"< Prev",10f,C_LABEL,C_BTN,()=>{if(recentSeriesPage>0){recentSeriesPage--;dirty=true;}},sizeDelta:new Vector2(50,18));txtSeriesPage=UIFactory.CreateText("sPI",sPg.transform,"",10f,C_LABEL,UIFactory.AlignMidCenter,sizeDelta:new Vector2(35,18));seriesNext=UIFactory.CreateButton("sN",sPg.transform,"Next >",10f,C_LABEL,C_BTN,()=>{recentSeriesPage++;dirty=true;},sizeDelta:new Vector2(50,18));var sS2=new GameObject("S");sS2.transform.SetParent(sPg.transform,false);sS2.AddComponent<RectTransform>();UIFactory.AddLE(sS2,flexW:1);/* === MIDDLE: Leaderboard list === */var mid=new GameObject("LBMid");mid.transform.SetParent(panel.transform,false);mid.AddComponent<RectTransform>();UIFactory.AddVLG(mid,spacing:2);UIFactory.AddLE(mid,prefW:560,minW:500,flexH:1);string[]hL={"#","Lv","Player","Rating","W","L","W/L","Gold"};string[]hK={"rank","level","display_name","rating","wins","losses","wl_ratio","gold"};var hRow=new GameObject("LBH");hRow.transform.SetParent(mid.transform,false);hRow.AddComponent<RectTransform>();UIFactory.AddHLG(hRow,spacing:2,forceExpandH:true);UIFactory.AddLE(hRow,prefH:28,minH:28,flexH:0);lbSortTexts=new object[hL.Length];lbSortBtns=new GameObject[hL.Length];var lbHSp1=new GameObject("S");lbHSp1.transform.SetParent(hRow.transform,false);lbHSp1.AddComponent<RectTransform>();UIFactory.AddLE(lbHSp1,flexW:1);for(int hi=0;hi<hL.Length;hi++){int idx=hi;string arrow=lbSort==hK[hi]?(lbSortDesc?" v":" ^"):"";var hBtn=UIFactory.CreateButton($"LH{hi}",hRow.transform,hL[hi]+arrow,14f,lbSort==hK[hi]?C_WHITE:C_LABEL,lbSort==hK[hi]?C_TABACT:C_TAB,()=>{if(lbSort==hK[idx])lbSortDesc=!lbSortDesc;else{lbSort=hK[idx];lbSortDesc=(idx>=3);}dirty=true;},sizeDelta:new Vector2(LB_COL_W[hi],22));if(UIFactory.tLE!=null){var el=hBtn.GetComponent(UIFactory.tLE);if(el!=null)UnityEngine.Object.Destroy(el as UnityEngine.Object);}UIFactory.AddLE(hBtn,prefW:LB_COL_W[hi],prefH:22,flexH:0);lbSortBtns[hi]=hBtn;lbSortTexts[hi]=UIFactory.GetButtonText(hBtn);}var lbHSp2=new GameObject("S");lbHSp2.transform.SetParent(hRow.transform,false);lbHSp2.AddComponent<RectTransform>();UIFactory.AddLE(lbHSp2,flexW:1);var sv=UIFactory.CreateScrollView("LBSV",mid.transform);UIFactory.AddLE(sv.scrollGO,flexH:1);for(int i=0;i<50;i++)lbRows.Add(CreateLBRow(sv.content.transform,$"lb{i}",i));var lbPg=new GameObject("LBPg");lbPg.transform.SetParent(mid.transform,false);lbPg.AddComponent<RectTransform>();UIFactory.AddHLG(lbPg,spacing:6,forceExpandH:true);UIFactory.AddLE(lbPg,prefH:24,flexH:0);txtLBCount=UIFactory.CreateText("LBC",lbPg.transform,"",15f,C_LABEL,sizeDelta:new Vector2(160,22));var lbS1=new GameObject("S");lbS1.transform.SetParent(lbPg.transform,false);lbS1.AddComponent<RectTransform>();UIFactory.AddLE(lbS1,flexW:1);lbPrev=UIFactory.CreateButton("lbP",lbPg.transform,"< Prev",13f,C_LABEL,C_BTN,()=>{if(lbPage>0){lbPage--;dirty=true;}},sizeDelta:new Vector2(60,22));txtLBPage=UIFactory.CreateText("lbPI",lbPg.transform,"",13f,C_LABEL,UIFactory.AlignMidCenter,sizeDelta:new Vector2(40,22));lbNext=UIFactory.CreateButton("lbN",lbPg.transform,"Next >",13f,C_LABEL,C_BTN,()=>{lbPage++;dirty=true;},sizeDelta:new Vector2(60,22));/* === RIGHT: Player detail === */var right=UIFactory.CreatePanel("LBR",panel.transform,C_PANEL);UIFactory.AddVLG(right,spacing:4,padL:12,padR:12,padT:8,padB:8);UIFactory.AddLE(right,flexW:1,flexH:1);txtLBPlayerName=UIFactory.CreateText("LBName",right.transform,"Click a player",20f,C_WHITE,UIFactory.AlignMidLeft,sizeDelta:new Vector2(340,26));UIFactory.SetBold(txtLBPlayerName,true);lbGraphPanel=new GameObject("Graph");lbGraphPanel.transform.SetParent(right.transform,false);var grt=lbGraphPanel.AddComponent<RectTransform>();UIFactory.AddLE(lbGraphPanel,prefH:80,minH:80,flexH:0);/* Add mask to clip graph bars within bounds */var gMaskImg=lbGraphPanel.AddComponent(UIFactory.tImage);UIFactory.tImage.GetProperty("color",BindingFlags.Public|BindingFlags.Instance)?.SetValue(gMaskImg,new Color(0,0,0,0.01f));if(UIFactory.tMask!=null){var gMask=lbGraphPanel.AddComponent(UIFactory.tMask);try{UIFactory.tMask.GetProperty("showMaskGraphic",BindingFlags.Public|BindingFlags.Instance)?.SetValue(gMask,false);}catch{}}lbGraphPanel.SetActive(false);var lbDetailSV=UIFactory.CreateScrollView("LBDSV",right.transform,spacing:0);UIFactory.AddLE(lbDetailSV.scrollGO,flexH:1);txtLBDetail=UIFactory.CreateText("LBD",lbDetailSV.content.transform,"",16f,C_DIM,sizeDelta:new Vector2(340,24));lbBlockRow=new GameObject("BlockRow");lbBlockRow.transform.SetParent(right.transform,false);lbBlockRow.AddComponent<RectTransform>();UIFactory.AddHLG(lbBlockRow,spacing:0);UIFactory.AddLE(lbBlockRow,prefH:28,minH:28,flexH:0);lbBlockBtn=UIFactory.CreateButton("LBBlock",lbBlockRow.transform,"Block from Ranked",14f,C_WHITE,new Color(0.5f,0.15f,0.15f,0.9f),()=>{if(string.IsNullOrEmpty(selectedSteamId)||selectedSteamId==MatchTracker.LocalSteamId)return;string myId=MatchTracker.LocalSteamId;if(ApiClient.IsPlayerBlocked(selectedSteamId))ApiClient.UnblockPlayer(myId,selectedSteamId);else ApiClient.BlockPlayer(myId,selectedSteamId);},sizeDelta:new Vector2(160,24));var lbBlockSpacer=new GameObject("S");lbBlockSpacer.transform.SetParent(lbBlockRow.transform,false);lbBlockSpacer.AddComponent<RectTransform>();UIFactory.AddLE(lbBlockSpacer,flexW:1);lbBlockBtn.SetActive(true);lbBlockRow.SetActive(false);lbBlockTxt=UIFactory.GetButtonText(lbBlockBtn);return panel;}

        private static LBRow CreateLBRow(Transform parent,string name,int rowIndex){var row=new LBRow();row.root=new GameObject(name);row.root.transform.SetParent(parent,false);row.root.AddComponent<RectTransform>();UIFactory.AddHLG(row.root,spacing:0,forceExpandH:true);UIFactory.AddLE(row.root,prefH:28);var lsp=new GameObject("S");lsp.transform.SetParent(row.root.transform,false);lsp.AddComponent<RectTransform>();UIFactory.AddLE(lsp,flexW:1);row.hlWrap=new GameObject("W");row.hlWrap.transform.SetParent(row.root.transform,false);row.hlWrap.AddComponent<RectTransform>();UIFactory.AddHLG(row.hlWrap,spacing:2,forceExpandH:true);if(UIFactory.tImage!=null){var img=row.hlWrap.AddComponent(UIFactory.tImage);UIFactory.tImage.GetProperty("color",BindingFlags.Public|BindingFlags.Instance)?.SetValue(img,new Color(0.15f,0.15f,0.2f,0.01f));UIFactory.tImage.GetProperty("raycastTarget",BindingFlags.Public|BindingFlags.Instance)?.SetValue(img,true);}row.txtRank=UIFactory.CreateText("r",row.hlWrap.transform,"",15f,C_GOLD,UIFactory.AlignMidCenter,sizeDelta:new Vector2(LB_COL_W[0],25));row.txtLv=UIFactory.CreateText("l",row.hlWrap.transform,"",15f,C_BLUE,UIFactory.AlignMidCenter,sizeDelta:new Vector2(LB_COL_W[1],25));row.txtName=UIFactory.CreateText("n",row.hlWrap.transform,"",16f,C_WHITE,UIFactory.AlignMidLeft,sizeDelta:new Vector2(LB_COL_W[2],25));row.txtRating=UIFactory.CreateText("rt",row.hlWrap.transform,"",16f,C_WHITE,UIFactory.AlignMidCenter,sizeDelta:new Vector2(LB_COL_W[3],25));UIFactory.SetBold(row.txtRating,true);row.txtW=UIFactory.CreateText("w",row.hlWrap.transform,"",15f,C_GREEN,UIFactory.AlignMidCenter,sizeDelta:new Vector2(LB_COL_W[4],25));row.txtL=UIFactory.CreateText("ls",row.hlWrap.transform,"",15f,C_RED,UIFactory.AlignMidCenter,sizeDelta:new Vector2(LB_COL_W[5],25));row.txtWL=UIFactory.CreateText("wl",row.hlWrap.transform,"",15f,C_LABEL,UIFactory.AlignMidCenter,sizeDelta:new Vector2(LB_COL_W[6],25));row.txtGold=UIFactory.CreateText("gd",row.hlWrap.transform,"",15f,C_GOLD,UIFactory.AlignMidCenter,sizeDelta:new Vector2(LB_COL_W[7],25));UIFactory.SetBold(row.txtGold,true);var rsp=new GameObject("S");rsp.transform.SetParent(row.root.transform,false);rsp.AddComponent<RectTransform>();UIFactory.AddLE(rsp,flexW:1);int idx=rowIndex;var ch=row.root.AddComponent<ClickHandler>();ch.onClick=()=>{if(ClickGuard.Claim()&&idx>=0&&idx<lbRows.Count&&!string.IsNullOrEmpty(lbRows[idx].steamId)){string sid=lbRows[idx].steamId;if(selectedSteamId==sid){selectedSteamId="";selectedStats=null;}else{selectedSteamId=sid;selectedStats=null;ApiClient.FetchPlayerStatsForView(sid,(d)=>{selectedStats=d;dirty=true;});ApiClient.FetchAchievementsForView(sid);}dirty=true;}};row.root.SetActive(false);return row;}

        private static GameObject BuildCardStatsTab(Transform parent){var panel=new GameObject("CardStats");panel.transform.SetParent(parent,false);panel.AddComponent<RectTransform>();UIFactory.AddVLG(panel,spacing:4);UIFactory.AddLE(panel,flexH:1);var fBar=new GameObject("Filt");fBar.transform.SetParent(panel.transform,false);fBar.AddComponent<RectTransform>();UIFactory.AddHLG(fBar,spacing:4,forceExpandH:true);UIFactory.AddLE(fBar,prefH:32,minH:32,flexH:0);var fSp1=new GameObject("S");fSp1.transform.SetParent(fBar.transform,false);fSp1.AddComponent<RectTransform>();UIFactory.AddLE(fSp1,flexW:2);string[]fN={"All","Ranked","Casual"};cardFilterBtns=new GameObject[3];cardFilterTexts=new object[3];for(int i=0;i<3;i++){int idx=i;var btn=UIFactory.CreateButton($"F{i}",fBar.transform,fN[i],16f,C_LABEL,i==0?C_TABACT:C_TAB,()=>{cardFilter=idx;string r=idx==1?"true":idx==2?"false":null;ApiClient.FetchCardStats(200,MatchTracker.LocalSteamId,"times_picked",r);for(int fi=0;fi<3;fi++){UIFactory.SetImageColor(cardFilterBtns[fi],fi==idx?C_TABACT:C_TAB);if(cardFilterTexts[fi]!=null){UIFactory.SetColor(cardFilterTexts[fi],fi==idx?C_WHITE:C_LABEL);UIFactory.SetBold(cardFilterTexts[fi],fi==idx);}}dirty=true;},sizeDelta:new Vector2(95,28));if(UIFactory.tLE!=null){var el=btn.GetComponent(UIFactory.tLE);if(el!=null)UnityEngine.Object.Destroy(el as UnityEngine.Object);}UIFactory.AddLE(btn,flexW:1,prefH:28,minH:28,flexH:0);cardFilterBtns[i]=btn;cardFilterTexts[i]=UIFactory.GetButtonText(btn);}var fSp2=new GameObject("S");fSp2.transform.SetParent(fBar.transform,false);fSp2.AddComponent<RectTransform>();UIFactory.AddLE(fSp2,flexW:2);string[]hL={"Card","Rarity","Picks","Wins","WR%","Pass%"};string[]hK={"card_name","card_rarity","times_picked","wins_with_card","win_rate","pass_rate"};var hRow=new GameObject("CHR");hRow.transform.SetParent(panel.transform,false);hRow.AddComponent<RectTransform>();UIFactory.AddHLG(hRow,spacing:2,forceExpandH:true);UIFactory.AddLE(hRow,prefH:28,minH:28,flexH:0);cardSortTexts=new object[6];cardSortBtns=new GameObject[6];var csHSp1=new GameObject("S");csHSp1.transform.SetParent(hRow.transform,false);csHSp1.AddComponent<RectTransform>();UIFactory.AddLE(csHSp1,flexW:1);for(int hi=0;hi<6;hi++){int idx=hi;string arrow=cardSort==hK[hi]?(cardSortDesc?" v":" ^"):"";var hBtn=UIFactory.CreateButton($"CS{hi}",hRow.transform,hL[hi]+arrow,15f,cardSort==hK[hi]?C_WHITE:C_LABEL,cardSort==hK[hi]?C_TABACT:C_TAB,()=>{if(cardSort==hK[idx])cardSortDesc=!cardSortDesc;else{cardSort=hK[idx];cardSortDesc=true;}dirty=true;},sizeDelta:new Vector2(CS_COL_W[hi],22));if(UIFactory.tLE!=null){var el=hBtn.GetComponent(UIFactory.tLE);if(el!=null)UnityEngine.Object.Destroy(el as UnityEngine.Object);}UIFactory.AddLE(hBtn,prefW:CS_COL_W[hi],prefH:22,flexH:0);cardSortBtns[hi]=hBtn;cardSortTexts[hi]=UIFactory.GetButtonText(hBtn);}var hSp=new GameObject("S");hSp.transform.SetParent(hRow.transform,false);hSp.AddComponent<RectTransform>();UIFactory.AddLE(hSp,flexW:1);var sv=UIFactory.CreateScrollView("CSV",panel.transform);UIFactory.AddLE(sv.scrollGO,flexH:1);for(int i=0;i<100;i++)cardRows.Add(CreateCardRow(sv.content.transform,$"cd{i}"));return panel;}

        private static CardRow CreateCardRow(Transform parent,string name){var row=new CardRow();row.root=new GameObject(name);row.root.transform.SetParent(parent,false);row.root.AddComponent<RectTransform>();UIFactory.AddHLG(row.root,spacing:2,forceExpandH:true);UIFactory.AddLE(row.root,prefH:25);var cls=new GameObject("S");cls.transform.SetParent(row.root.transform,false);cls.AddComponent<RectTransform>();UIFactory.AddLE(cls,flexW:1);row.txtName=UIFactory.CreateText("t",row.root.transform,"",16f,C_WHITE,UIFactory.AlignMidLeft,sizeDelta:new Vector2(CS_COL_W[0],25));row.txtRarity=UIFactory.CreateText("tr",row.root.transform,"",15f,C_LABEL,UIFactory.AlignMidCenter,sizeDelta:new Vector2(CS_COL_W[1],25));row.txtPicks=UIFactory.CreateText("tp",row.root.transform,"",16f,C_WHITE,UIFactory.AlignMidCenter,sizeDelta:new Vector2(CS_COL_W[2],25));row.txtWins=UIFactory.CreateText("tw",row.root.transform,"",16f,C_WHITE,UIFactory.AlignMidCenter,sizeDelta:new Vector2(CS_COL_W[3],25));row.txtWR=UIFactory.CreateText("wr",row.root.transform,"",16f,C_WHITE,UIFactory.AlignMidCenter,sizeDelta:new Vector2(CS_COL_W[4],25));row.txtPass=UIFactory.CreateText("pr",row.root.transform,"",16f,C_LABEL,UIFactory.AlignMidCenter,sizeDelta:new Vector2(CS_COL_W[5],25));var sp=new GameObject("S");sp.transform.SetParent(row.root.transform,false);sp.AddComponent<RectTransform>();UIFactory.AddLE(sp,flexW:1);row.root.SetActive(false);return row;}

        // ── Achievements Tab ────────────────────────────────────
        private static GameObject BuildAchievementsTab(Transform parent){var panel=new GameObject("Achievements");panel.transform.SetParent(parent,false);panel.AddComponent<RectTransform>();UIFactory.AddVLG(panel,spacing:6,padL:20,padR:20,padT:10);UIFactory.AddLE(panel,flexH:1);UIFactory.CreateText("AchH",panel.transform,"Achievements",22f,C_GOLD,UIFactory.AlignTopCenter,sizeDelta:new Vector2(600,30));var countRow=new GameObject("AchCnt");countRow.transform.SetParent(panel.transform,false);countRow.AddComponent<RectTransform>();UIFactory.AddLE(countRow,prefH:22);txtAchCount=UIFactory.CreateText("AC",countRow.transform,"",15f,C_DIM,UIFactory.AlignMidCenter,sizeDelta:new Vector2(400,22));var sv=UIFactory.CreateScrollView("AchSV",panel.transform,spacing:4);UIFactory.AddLE(sv.scrollGO,flexH:1);achRows.Clear();foreach(var kvp in ApiClient.AchievementDefs){var row=new AchRow();string key=kvp.Key;string[]def=kvp.Value;row.root=new GameObject($"ach_{key}");row.root.transform.SetParent(sv.content.transform,false);row.root.AddComponent<RectTransform>();UIFactory.AddHLG(row.root,spacing:10,padL:8,padR:8,padT:6,padB:6,forceExpandH:true);UIFactory.AddLE(row.root,prefH:50);if(UIFactory.tImage!=null){var img=row.root.AddComponent(UIFactory.tImage);UIFactory.tImage.GetProperty("color",BindingFlags.Public|BindingFlags.Instance)?.SetValue(img,C_PANEL);}row.txtIcon=UIFactory.CreateText("ic",row.root.transform,"",24f,C_DIM,UIFactory.AlignMidCenter,sizeDelta:new Vector2(36,40));var infoCol=new GameObject("Info");infoCol.transform.SetParent(row.root.transform,false);infoCol.AddComponent<RectTransform>();UIFactory.AddVLG(infoCol,spacing:1);UIFactory.AddLE(infoCol,flexW:1);row.txtName=UIFactory.CreateText("nm",infoCol.transform,def[0],17f,C_WHITE,UIFactory.AlignMidLeft,sizeDelta:new Vector2(500,22));row.txtDesc=UIFactory.CreateText("ds",infoCol.transform,def[1],14f,C_LABEL,UIFactory.AlignMidLeft,sizeDelta:new Vector2(500,20));row.txtDate=UIFactory.CreateText("dt",row.root.transform,"",13f,C_DIM,UIFactory.AlignMidRight,sizeDelta:new Vector2(180,40));row.root.SetActive(true);achRows.Add(row);}return panel;}

        private static object txtAchCount;
        private static void RefreshAchievements(){var ach=ApiClient.CachedAchievements;int unlocked=0,total=ApiClient.AchievementDefs.Count;int i=0;foreach(var kvp in ApiClient.AchievementDefs){if(i>=achRows.Count)break;var row=achRows[i];bool got=ach!=null&&ach.ContainsKey(kvp.Key)&&ach[kvp.Key].unlocked;if(got)unlocked++;UIFactory.SetText(row.txtIcon,got?"[X]":"[ ]");UIFactory.SetColor(row.txtIcon,got?C_GOLD:new Color(0.3f,0.3f,0.35f));UIFactory.SetColor(row.txtName,got?C_WHITE:C_DIM);UIFactory.SetColor(row.txtDesc,got?C_LABEL:new Color(0.4f,0.4f,0.45f));string dt="";if(got&&ach!=null&&ach.ContainsKey(kvp.Key)){string ua=ach[kvp.Key].unlocked_at;if(!string.IsNullOrEmpty(ua)&&ua!="null"){try{dt=DateTime.Parse(ua).ToString("M/d/yyyy");}catch{}}}/* Append "+100g" gold-awarded tag inline with the date so users see the per-trophy reward without opening the gold ledger. Per-achievement gold is uniform (ACHIEVEMENT_GOLD on the server, currently 100). */if(got&&!string.IsNullOrEmpty(dt))dt=$"{dt}  <color=#FFD94D>+100g</color>";UIFactory.SetText(row.txtDate,dt);UIFactory.SetColor(row.txtDate,got?C_GREEN:C_DIM);i++;}UIFactory.SetText(txtAchCount,$"{unlocked} / {total} unlocked");UIFactory.SetColor(txtAchCount,unlocked==total?C_GOLD:C_LABEL);}

        private static void RefreshData(){string id=MatchTracker.LocalSteamId;if(!string.IsNullOrEmpty(id)&&id!="unknown"){ApiClient.FetchPlayerStats(id);ApiClient.FetchMatchHistory(id);ApiClient.FetchAchievements(id);}if(currentTab==1){ApiClient.FetchLeaderboard();ApiClient.FetchRecentSeries();}if(currentTab==2)ApiClient.FetchCardStats(200,MatchTracker.LocalSteamId);}
        private static void RefreshCurrentTab(){RefreshQueueUI();RefreshVersionStatus();RefreshServerBanner();/* Admin tab button visibility — IsAdmin can flip on after the async check completes. */if(tabButtons!=null&&tabButtons.Length>=7&&tabButtons[6]!=null)tabButtons[6].SetActive(ApiClient.IsAdmin);switch(currentTab){case 0:RefreshMyStats();break;case 1:RefreshLeaderboard();RefreshRecentSeries();RefreshLiveSeries();break;case 2:RefreshCardStats();break;case 3:RefreshAchievements();break;case 4:RefreshShop();break;case 5:RefreshSettings();break;case 6:RefreshAdmin();break;}}

        // Hide the row entirely unless the API actually looks down — see ApiClient.ApiLooksDown.
        // Fires from RefreshCurrentTab so it stays in sync with the rest of the UI.
        private static void RefreshServerBanner()
        {
            if (srvStatusRow == null) return;
            bool down = ApiClient.ApiLooksDown;
            srvStatusRow.SetActive(down);
            if (down)
            {
                string msg = ApiClient.LastResponseWasMaintenance
                    ? "<color=#FFB060>● Server in maintenance — back in a moment</color>"
                    : "<color=#FF8866>● Server reconnecting…</color>";
                UIFactory.SetText(txtServerStatus, msg);
            }
        }

        // Active-series fetch hook — fire on leaderboard tab open in SwitchTab.
        private static void RefreshLiveSeries()
        {
            if (txtLiveSeries == null) return;
            // Redraw the header each refresh with an alternating bright/dim dot color. The
            // filled/empty state is flipped in MaybeRefreshLiveSeries so it ticks exactly once
            // per real server poll. We alternate COLOR instead of glyph because the Gravity
            // SDF font ROUNDS ships with doesn't contain ● (U+25CF) or ○ (U+25CB) — both
            // render as the same missing-glyph □, which masks any glyph-swap as stationary.
            // Color change applies to the dot only; the "Live Ranked Games" label stays
            // consistent so the pulse is focal, not distracting.
            if (txtLiveHeader != null)
            {
                string dotColor = liveHeaderPulseFilled ? "#FF6688" : "#552233";
                UIFactory.SetText(txtLiveHeader, $"<color={dotColor}>●</color> <color=#FF6688>Live Ranked Games</color>");
            }
            var list = ApiClient.CachedActiveSeries;
            // Clear pool first, then rebuild.
            foreach (var g in liveBetRowPool) g.SetActive(false);
            if (list == null || list.Count == 0)
            {
                UIFactory.SetText(txtLiveSeries, "<color=#666><i>No live games right now.</i></color>");
                if (liveBetsPager != null) liveBetsPager.SetActive(false);
                return;
            }
            UIFactory.SetText(txtLiveSeries, "");

            int totalPages = Math.Max(1, (list.Count + LIVE_SERIES_PER_PAGE - 1) / LIVE_SERIES_PER_PAGE);
            liveSeriesPage = Math.Max(0, Math.Min(liveSeriesPage, totalPages - 1));
            int start = liveSeriesPage * LIVE_SERIES_PER_PAGE;
            int end = Math.Min(start + LIVE_SERIES_PER_PAGE, list.Count);

            int poolIdx = 0;
            for (int i = start; i < end; i++)
            {
                var s = list[i];
                // Each series uses 3 rows: header, bet-on-p1 row, bet-on-p2 row.
                var hdr = GetOrCreateLiveRow(poolIdx++);
                ApplyHeaderRow(hdr, s);
                var betP1 = GetOrCreateLiveRow(poolIdx++);
                ApplyBetRow(betP1, s, true);
                var betP2 = GetOrCreateLiveRow(poolIdx++);
                ApplyBetRow(betP2, s, false);
            }

            // Pagination controls: only visible when > one page's worth of series.
            if (liveBetsPager != null)
            {
                bool show = totalPages > 1;
                liveBetsPager.SetActive(show);
                if (show)
                {
                    UIFactory.SetText(txtLiveBetsPage, $"{list.Count} live — {liveSeriesPage + 1}/{totalPages}");
                    liveBetsPrev.SetActive(liveSeriesPage > 0);
                    liveBetsNext.SetActive(liveSeriesPage < totalPages - 1);
                }
            }
        }

        private static GameObject GetOrCreateLiveRow(int idx)
        {
            while (liveBetRowPool.Count <= idx)
            {
                var go = new GameObject($"lb{liveBetRowPool.Count}");
                go.transform.SetParent(liveBetsContainer.transform, false);
                go.AddComponent<RectTransform>();
                UIFactory.AddHLG(go, spacing: 4, forceExpandH: true);
                UIFactory.AddLE(go, prefH: 26, flexH: 0);
                liveBetRowPool.Add(go);
            }
            var row = liveBetRowPool[idx];
            // Clear children (builders will recreate).
            for (int i = row.transform.childCount - 1; i >= 0; i--)
                UnityEngine.Object.Destroy(row.transform.GetChild(i).gameObject);
            row.SetActive(true);
            return row;
        }

        private static void ApplyHeaderRow(GameObject row, ApiClient.ActiveSeriesEntry s)
        {
            // Names truncated to 12 chars to leave room for the rating in parens. Wrap explicitly
            // disabled so a long name doesn't push elo onto a second visual line — the column is
            // 400 wide and fonts are bold 16f, but TMP word-wrapping would still split the line on
            // narrow screens.
            string line = $"<color=#AAF>{Trunc(s.p1_name, 12)}</color> ({s.p1_rating})  " +
                          $"<b>{s.p1_wins}-{s.p2_wins}</b>  " +
                          $"<color=#FAA>{Trunc(s.p2_name, 12)}</color> ({s.p2_rating})";
            var t = UIFactory.CreateText("h", row.transform, line, 15f, C_WHITE,
                UIFactory.AlignMidLeft, sizeDelta: new Vector2(384, 24));
            UIFactory.SetBold(t, true);
            UIFactory.SetWordWrap(t, false);
        }

        private static void ApplyBetRow(GameObject row, ApiClient.ActiveSeriesEntry s, bool betOnP1)
        {
            string name = betOnP1 ? s.p1_name : s.p2_name;
            string steamId = betOnP1 ? s.p1_steam_id : s.p2_steam_id;
            float odds = betOnP1 ? s.p1_odds : s.p2_odds;

            string myId = MatchTracker.LocalSteamId;
            bool localIsParticipant = !string.IsNullOrEmpty(myId)
                && (myId == s.p1_steam_id || myId == s.p2_steam_id);

            // Three exclusive states for the right side of the row:
            //   1. The user already bet on this series — show the bet status, hide buttons.
            //   2. Bets are locked (game past 2 points or game 1 finished) — show locked tag.
            //   3. User is a participant — "your match" tag.
            //   4. Otherwise: show the wager buttons.
            var existing = ApiClient.GetMyBetForSeries(s.series_id);

            // Wider text element + disable wrap; truncate name to 10 so "Bet on <name> @1.0x:"
            // fits even with the longest names. Was 180w with 12-char truncation → wrapped on
            // "bobbyjoe122333" rows.
            var betLabel = UIFactory.CreateText("bl", row.transform,
                $"Bet on <b>{Trunc(name, 10)}</b> @{odds:F1}x:",
                13f, C_LABEL, UIFactory.AlignMidLeft, sizeDelta: new Vector2(220, 22));
            UIFactory.SetWordWrap(betLabel, false);

            if (existing != null)
            {
                // Only display on the "side" the user actually bet on — the other side stays
                // showing odds (so they can still see the live odds change as scores update).
                bool betOnThisSide = existing.bet_on_steam_id == steamId;
                if (betOnThisSide)
                {
                    var t = UIFactory.CreateText("mybet", row.transform,
                        $"<color=#FFD94D>You bet {existing.amount}g</color>",
                        14f, C_GOLD, UIFactory.AlignMidLeft, sizeDelta: new Vector2(170, 22));
                    UIFactory.SetBold(t, true);
                }
                else
                {
                    UIFactory.CreateText("notbet", row.transform,
                        "<color=#666>—</color>",
                        14f, C_DIM, UIFactory.AlignMidLeft, sizeDelta: new Vector2(170, 22));
                }
                return;
            }

            if (s.bets_locked)
            {
                string lockMsg = s.lock_reason == "no_meaningful_odds"
                    ? "<color=#A07744><i>odds too uncertain</i></color>"
                    : "<color=#A07744><i>betting period over</i></color>";
                UIFactory.CreateText("locked", row.transform, lockMsg,
                    13f, C_DIM, UIFactory.AlignMidLeft, sizeDelta: new Vector2(220, 22));
                return;
            }

            if (localIsParticipant)
            {
                UIFactory.CreateText("self", row.transform,
                    "<color=#AA9955><i>your match</i></color>",
                    13f, C_DIM, UIFactory.AlignMidLeft, sizeDelta: new Vector2(140, 22));
                return;
            }

            AddBetButton(row.transform, s.series_id, steamId, 100);
            AddBetButton(row.transform, s.series_id, steamId, 500);
            AddBetButton(row.transform, s.series_id, steamId, 2000);
        }

        private static void AddBetButton(Transform parent, string seriesId, string betOnSteamId, int amount)
        {
            // CreateButton already wraps onClick in ClickGuard.Claim() at both the Button.onClick
            // listener AND the auxiliary ClickHandler. A second Claim() inside the body always
            // returned false (the first Claim consumed the budget), so every bet click was
            // silently dropped — Sid clicked many times and only saw "[BET]" log lines never appear.
            var btn = UIFactory.CreateButton($"b{amount}", parent,
                $"{amount}g", 11f, C_WHITE, new Color(0.35f, 0.28f, 0.1f, 0.9f),
                () =>
                {
                    string id = MatchTracker.LocalSteamId;
                    if (string.IsNullOrEmpty(id) || id == "unknown") return;
                    Plugin.Log.LogInfo($"[BET] Placing {amount}g on {betOnSteamId} (series {seriesId})");
                    ApiClient.PlaceBet(id, seriesId, betOnSteamId, amount, (ok, resp) =>
                    {
                        var col = ok ? new Color(0.4f, 1f, 0.4f) : new Color(1f, 0.5f, 0.5f);
                        CompetitiveUI.ShowNotification(ok ? $"Bet placed: {amount}g" : $"Bet failed: {resp}", col, 3f);
                        // Refresh active series so the row replaces buttons with the placed-bet status
                        // (a follow-up fetch also brings the user's gold balance back in sync).
                        if (ok) { ApiClient.FetchActiveSeries(); ApiClient.FetchPlayerStats(id); ApiClient.FetchMyBets(id); }
                    });
                },
                sizeDelta: new Vector2(44, 22));
            UIFactory.AddLE(btn, prefW: 44, prefH: 22, flexW: 0, flexH: 0);
        }

        // ── Shop Tab ───────────────────────────────────────────
        private static object txtShopBalance, txtShopStatus;
        private static GameObject shopRowsContainer, shopTitlesHeader, shopTrailsHeader, shopColorsHeader, shopNametagsHeader;
        // Shop category filter: 0=All, 1=Titles, 2=Trails, 3=Map Colors, 4=Name Styles.
        // Clicking a tab narrows the scroll view to that category so users don't have to
        // scroll through 90+ items to find one kind. Each tab has a description shown
        // under the tab bar so the category's purpose is discoverable.
        private static int shopCategoryFilter = 0;
        private static GameObject[] shopTabBtns;
        private static object[] shopTabTexts;
        private static object txtShopCategoryDesc;
        private static readonly string[] SHOP_TAB_NAMES = { "All", "Titles", "Trails", "Maps", "Name Styles" };
        private static readonly string[] SHOP_TAB_DESCS = {
            "All cosmetics — everything available, grouped by category.",
            "Flair text shown next to your name on the leaderboard, match history, and in chat.",
            "A glowing trail that follows your character body during combat. Only visible to modded players; the shop preview shows it following your cursor.",
            "Map color schemes. Equip as many as you like and cycle between your owned colors with Left Shift in-game.",
            "Bold, italic, underline, strikethrough, and color/size modifiers applied to your player nametag in lobbies and matches. Visible to every player, modded or not.",
        };
        private static List<GameObject> shopRowPool = new List<GameObject>();
        // Per-row glow-preview state. NametagGlowRenderer.ApplyGlowToLabel caches the unmodified
        // material when it first swaps a label; we keep a shared cache keyed by glow sku so the
        // expensive material clone only happens once per sku regardless of how many rows reuse it.
        private static readonly Dictionary<object, Material> shopPreviewOriginalMats = new Dictionary<object, Material>();
        private static readonly Dictionary<string, Material> shopPreviewGlowMatCache = new Dictionary<string, Material>();
        // Per-row typeface-preview state — parallel to the glow state. Stores the label's
        // original TMP_FontAsset so swapping back to non-typeface rows (or to a different
        // typeface) picks the correct baseline font.
        private static readonly Dictionary<object, object> shopPreviewOriginalFonts = new Dictionary<object, object>();
        private class ShopRow
        {
            public GameObject root;
            public object txtName, txtDesc, txtPrice;
            public GameObject buyBtn, setActiveBtn, previewBtn;
            public object buyBtnTxt, previewBtnTxt;
            public long itemId;
            public string sku;
            public string previewColor;
            public int previewPrice;
        }
        private static List<ShopRow> shopRows = new List<ShopRow>();

        private static GameObject BuildShopTab(Transform parent)
        {
            var panel = new GameObject("Shop");
            panel.transform.SetParent(parent, false);
            panel.AddComponent<RectTransform>();
            UIFactory.AddVLG(panel, spacing: 6, padL: 20, padR: 20, padT: 10, padB: 10);
            UIFactory.AddLE(panel, flexH: 1);

            var header = new GameObject("SHHdr");
            header.transform.SetParent(panel.transform, false);
            header.AddComponent<RectTransform>();
            UIFactory.AddHLG(header, spacing: 14, forceExpandH: true);
            UIFactory.AddLE(header, prefH: 32, flexH: 0);

            UIFactory.CreateText("SHTitle", header.transform, "Shop",
                22f, C_GOLD, UIFactory.AlignMidLeft, sizeDelta: new Vector2(300, 30));

            var sp = new GameObject("SHSp");
            sp.transform.SetParent(header.transform, false);
            sp.AddComponent<RectTransform>();
            UIFactory.AddLE(sp, flexW: 1);

            txtShopBalance = UIFactory.CreateText("SHBal", header.transform,
                "Balance: —", 18f, C_GOLD, UIFactory.AlignMidRight, sizeDelta: new Vector2(320, 30));
            UIFactory.SetBold(txtShopBalance, true);

            txtShopStatus = UIFactory.CreateText("SHStatus", panel.transform,
                "", 14f, C_LABEL, sizeDelta: new Vector2(900, 22));

            // Category tab bar — 5 buttons, filters the scroll view below.
            var tabBar = new GameObject("SHTabs");
            tabBar.transform.SetParent(panel.transform, false);
            tabBar.AddComponent<RectTransform>();
            UIFactory.AddHLG(tabBar, spacing: 6, forceExpandH: true);
            UIFactory.AddLE(tabBar, prefH: 30, minH: 30, flexH: 0);
            shopTabBtns = new GameObject[SHOP_TAB_NAMES.Length];
            shopTabTexts = new object[SHOP_TAB_NAMES.Length];
            for (int i = 0; i < SHOP_TAB_NAMES.Length; i++)
            {
                int idx = i;
                var tb = UIFactory.CreateButton($"ShTab{i}", tabBar.transform, SHOP_TAB_NAMES[i], 14f,
                    C_LABEL, C_TAB,
                    () => { shopCategoryFilter = idx; dirty = true; },
                    sizeDelta: new Vector2(0, 26));
                if (UIFactory.tLE != null)
                {
                    var el = tb.GetComponent(UIFactory.tLE);
                    if (el != null) UnityEngine.Object.Destroy(el as UnityEngine.Object);
                }
                UIFactory.AddLE(tb, prefH: 26, minH: 26, flexW: 1, flexH: 0);
                shopTabBtns[i] = tb;
                shopTabTexts[i] = UIFactory.GetButtonText(tb);
            }

            // Description of the active tab — updated on each RefreshShop.
            txtShopCategoryDesc = UIFactory.CreateText("SHDesc", panel.transform,
                SHOP_TAB_DESCS[0], 13f, C_LABEL, UIFactory.AlignMidLeft, sizeDelta: new Vector2(900, 22));

            var sv = UIFactory.CreateScrollView("SHSV", panel.transform, spacing: 4);
            UIFactory.AddLE(sv.scrollGO, flexH: 1);
            shopRowsContainer = sv.content;

            // Section headers — persistent; re-ordered in RefreshShop via SetSiblingIndex.
            shopTitlesHeader = CreateSectionHeader(shopRowsContainer.transform, "SHHT",
                "<color=#FFD94D>━  TITLES  ━</color>");
            shopTrailsHeader = CreateSectionHeader(shopRowsContainer.transform, "SHHTr",
                "<color=#A0D4FF>━  TRAILS  ━</color>");
            shopColorsHeader = CreateSectionHeader(shopRowsContainer.transform, "SHHC",
                "<color=#B0FFB0>━  MAP COLORS  ━</color>");
            shopNametagsHeader = CreateSectionHeader(shopRowsContainer.transform, "SHHN",
                "<color=#FFB0E0>━  NAME STYLES  ━</color>");

            // Pre-allocate 80 item rows; reused on refresh. v1.22.x nametag expansion pushes
            // total shop items past 65 (16 titles + 12 trails + 22 colors + 17 nametags = 67),
            // so 80 leaves comfortable headroom for more cosmetics.
            // Row pool must exceed total shop_items count or trailing items silently stop
            // rendering — users reported "maps disappearing from shop" when we passed 80.
            // Current catalogue: 16 titles + 12 trails + 22 colors + ~40 nametags = ~90. Bump
            // to 200 to cover the catalogue with comfortable headroom for future cosmetics.
            for (int i = 0; i < 200; i++)
                shopRows.Add(CreateShopRow(shopRowsContainer.transform, i));

            return panel;
        }

        private static GameObject CreateSectionHeader(Transform parent, string name, string label)
        {
            var go = new GameObject(name);
            go.transform.SetParent(parent, false);
            go.AddComponent<RectTransform>();
            UIFactory.AddHLG(go, spacing: 0, padL: 4, padR: 4, padT: 6, padB: 2);
            UIFactory.AddLE(go, prefH: 30, flexH: 0);
            UIFactory.CreateText(name + "_txt", go.transform, label, 18f, C_WHITE,
                UIFactory.AlignMidLeft, sizeDelta: new Vector2(600, 28));
            return go;
        }

        private static ShopRow CreateShopRow(Transform parent, int idx)
        {
            var row = new ShopRow();
            row.root = UIFactory.CreatePanel($"sr{idx}", parent, C_PANEL);
            UIFactory.AddHLG(row.root, spacing: 10, padL: 10, padR: 10, padT: 6, padB: 6, forceExpandH: true);
            UIFactory.AddLE(row.root, prefH: 44, flexH: 0);

            var info = new GameObject("info");
            info.transform.SetParent(row.root.transform, false);
            info.AddComponent<RectTransform>();
            UIFactory.AddVLG(info, spacing: 0);
            UIFactory.AddLE(info, flexW: 1);
            row.txtName = UIFactory.CreateText($"sn{idx}", info.transform, "", 17f, C_WHITE,
                UIFactory.AlignMidLeft, sizeDelta: new Vector2(500, 22));
            UIFactory.SetBold(row.txtName, true);
            row.txtDesc = UIFactory.CreateText($"sd{idx}", info.transform, "", 13f, C_DIM,
                UIFactory.AlignMidLeft, sizeDelta: new Vector2(500, 18));

            row.txtPrice = UIFactory.CreateText($"sp{idx}", row.root.transform, "", 17f, C_GOLD,
                UIFactory.AlignMidRight, sizeDelta: new Vector2(120, 30));
            UIFactory.SetBold(row.txtPrice, true);

            int captured = idx;
            row.buyBtn = UIFactory.CreateButton($"sb{idx}", row.root.transform,
                "Buy", 14f, C_WHITE, new Color(0.25f, 0.45f, 0.18f, 0.9f),
                () =>
                {
                    // ClickGuard removed — server is idempotent (returns "already_owned" on dup).
                    // Fine-grained logs so we can see exactly where things die.
                    try
                    {
                        Plugin.Log.LogInfo($"[SHOP] onClick ENTRY captured={captured}");
                        var r = shopRows[captured];
                        if (r == null) { Plugin.Log.LogWarning("[SHOP] row is null"); return; }
                        Plugin.Log.LogInfo($"[SHOP] row got sku={r.sku}");
                        if (string.IsNullOrEmpty(r.sku)) { Plugin.Log.LogWarning("[SHOP] empty sku — abort"); return; }
                        string id = MatchTracker.LocalSteamId;
                        Plugin.Log.LogInfo($"[SHOP] steam id={id}");
                        if (string.IsNullOrEmpty(id) || id == "unknown") { Plugin.Log.LogWarning("[SHOP] no steam id yet — abort"); return; }
                        Plugin.Log.LogInfo("[SHOP] setting status");
                        UIFactory.SetText(txtShopStatus, $"Buying {r.sku}...");
                        Plugin.Log.LogInfo("[SHOP] calling PurchaseItem");
                        ApiClient.PurchaseItem(id, r.sku, (ok, resp) =>
                        {
                            Plugin.Log.LogInfo($"[SHOP] purchase complete ok={ok}");
                            UIFactory.SetText(txtShopStatus, ok
                                ? $"<color=#88FF88>Purchased!</color>"
                                : $"<color=#FF8888>Purchase failed: {resp}</color>");
                            dirty = true;
                        });
                        Plugin.Log.LogInfo("[SHOP] onClick EXIT normally");
                    }
                    catch (Exception ex)
                    {
                        Plugin.Log.LogError($"[SHOP] onClick threw: {ex}");
                    }
                },
                sizeDelta: new Vector2(80, 28));
            UIFactory.AddLE(row.buyBtn, prefW: 80, prefH: 28, flexW: 0, flexH: 0);
            row.buyBtnTxt = UIFactory.GetButtonText(row.buyBtn);

            // Preview button — visible on trail rows only. Spawns a cursor-following trail
            // locally (never published via Photon, so other mod players don't see it). Toggling
            // off, switching trails, or closing F5 all stop it.
            row.previewBtn = UIFactory.CreateButton($"spv{idx}", row.root.transform,
                "Preview", 13f, C_WHITE, new Color(0.25f, 0.4f, 0.55f, 0.9f),
                () =>
                {
                    try
                    {
                        var rr = shopRows[captured];
                        if (rr == null || string.IsNullOrEmpty(rr.sku)) return;
                        TrailPreview.Toggle(rr.sku, rr.previewColor, rr.previewPrice);
                        dirty = true;  // refresh button label (Preview ↔ Stop)
                    }
                    catch (Exception ex) { Plugin.Log.LogWarning($"[SHOP-PREVIEW] {ex.Message}"); }
                },
                sizeDelta: new Vector2(80, 28));
            UIFactory.AddLE(row.previewBtn, prefW: 80, prefH: 28, flexW: 0, flexH: 0);
            row.previewBtnTxt = UIFactory.GetButtonText(row.previewBtn);

            row.setActiveBtn = UIFactory.CreateButton($"sa{idx}", row.root.transform,
                "Set Active", 13f, C_WHITE, new Color(0.3f, 0.3f, 0.5f, 0.9f),
                () =>
                {
                    try
                    {
                        var r = shopRows[captured];
                        string id = MatchTracker.LocalSteamId;
                        if (string.IsNullOrEmpty(id) || id == "unknown") return;
                        // Resolve kind before logging so the message actually reflects reality.
                        var cachedItems = ApiClient.CachedShopItems;
                        string kind = "";
                        string itemName = "";
                        string itemSku = r.sku;
                        string itemColor = "";
                        if (cachedItems != null)
                            foreach (var it in cachedItems)
                                if (it.id == r.itemId) { kind = it.kind; itemName = it.name; itemColor = it.preview_color; break; }
                        Plugin.Log.LogInfo($"[SHOP] Set Active clicked sku={r.sku} kind={kind}");

                        // Optimistic UI update — flip the cached stats IMMEDIATELY so Refresh
                        // reflects the equip without waiting for the server round-trip + FetchPlayerStats.
                        var cached = ApiClient.CachedPlayerStats;
                        if (cached != null)
                        {
                            if (kind == "title")
                            {
                                cached.active_title = itemName;
                                cached.active_title_color = itemColor;
                            }
                            else if (kind == "trail")
                            {
                                cached.active_trail_sku = itemSku;
                                cached.active_trail_color = itemColor;
                            }
                            else if (kind == "color")
                            {
                                // Multi-equip colors: toggle in/out of the active list.
                                if (cached.active_color_skus == null)
                                    cached.active_color_skus = new List<string>();
                                if (cached.active_color_skus.Contains(itemSku))
                                    cached.active_color_skus.Remove(itemSku);
                                else
                                    cached.active_color_skus.Add(itemSku);
                                // Keep the legacy single-field in sync with the first entry
                                // so callers reading active_color_sku see something sensible.
                                cached.active_color_sku = cached.active_color_skus.Count > 0
                                    ? cached.active_color_skus[0] : null;
                            }
                            else if (kind == "nametag")
                            {
                                if (cached.active_nametag_skus == null)
                                    cached.active_nametag_skus = new List<string>();
                                if (cached.active_nametag_skus.Contains(itemSku))
                                {
                                    cached.active_nametag_skus.Remove(itemSku);
                                }
                                else
                                {
                                    // Single-active subgroups: remove any existing same-subgroup
                                    // sku before adding ours. Mirrors server enforcement so the
                                    // optimistic preview lines up with what the server will do.
                                    string sub = NametagStyler.GetSubgroup(itemSku);
                                    if (sub != null)
                                        cached.active_nametag_skus.RemoveAll(
                                            s => NametagStyler.GetSubgroup(s) == sub);
                                    cached.active_nametag_skus.Add(itemSku);
                                }
                            }
                            dirty = true;
                        }

                        Action<bool, string> cb = (ok, resp) =>
                        {
                            UIFactory.SetText(txtShopStatus, ok
                                ? $"<color=#88FF88>Equipped.</color>"
                                : $"<color=#FF8888>Failed: {resp}</color>");
                            dirty = true;
                            // Nametag styles change how our Photon NickName reads — republish so
                            // opponents (modded or not) see the update mid-room without needing
                            // a full reconnect.
                            if (ok && kind == "nametag") NametagStyler.PublishToPhoton();
                        };
                        if (kind == "trail") ApiClient.SetActiveTrail(id, r.itemId, cb);
                        else if (kind == "color") ApiClient.ToggleMapColor(id, r.itemId, cb);
                        else if (kind == "nametag") ApiClient.ToggleNametagStyle(id, r.itemId, cb);
                        else ApiClient.SetActiveTitle(id, r.itemId, cb);
                    }
                    catch (Exception ex) { Plugin.Log.LogError($"[SHOP] setActive threw: {ex}"); }
                },
                sizeDelta: new Vector2(100, 28));
            UIFactory.AddLE(row.setActiveBtn, prefW: 100, prefH: 28, flexW: 0, flexH: 0);

            row.root.SetActive(false);
            return row;
        }

        private static void RefreshShop()
        {
            var s = ApiClient.CachedPlayerStats;
            int balance = s != null ? ((s.gold_earned) - (s.gold_spent)) : 0;
            if (txtShopBalance != null)
                UIFactory.SetText(txtShopBalance, $"Balance: <color=#FFD94D>{balance}</color> gold");

            // Update tab bar visual state + description.
            if (shopTabBtns != null)
            {
                for (int i = 0; i < shopTabBtns.Length; i++)
                {
                    if (shopTabBtns[i] == null) continue;
                    bool active = i == shopCategoryFilter;
                    UIFactory.SetImageColor(shopTabBtns[i], active ? C_TABACT : C_TAB);
                    if (shopTabTexts != null && i < shopTabTexts.Length && shopTabTexts[i] != null)
                    {
                        UIFactory.SetColor(shopTabTexts[i], active ? C_WHITE : C_LABEL);
                        UIFactory.SetBold(shopTabTexts[i], active);
                    }
                }
            }
            if (txtShopCategoryDesc != null)
            {
                int di = Math.Max(0, Math.Min(shopCategoryFilter, SHOP_TAB_DESCS.Length - 1));
                UIFactory.SetText(txtShopCategoryDesc, SHOP_TAB_DESCS[di]);
            }

            var rawItems = ApiClient.CachedShopItems;
            // Partition + sort: titles → trails → colors → nametags. Cheapest first within each kind.
            var titles = new List<ApiClient.ShopItemData>();
            var trails = new List<ApiClient.ShopItemData>();
            var colors = new List<ApiClient.ShopItemData>();
            var nametags = new List<ApiClient.ShopItemData>();
            if (rawItems != null)
            {
                foreach (var it in rawItems)
                {
                    if (it.kind == "trail") trails.Add(it);
                    else if (it.kind == "color") colors.Add(it);
                    else if (it.kind == "nametag") nametags.Add(it);
                    else titles.Add(it);
                }
                titles.Sort((a, b) => a.price.CompareTo(b.price));
                trails.Sort((a, b) => a.price.CompareTo(b.price));
                // Colors sort: price first, then alphabetical within tier — keeps the long
                // 75g list predictable so users can find a specific color at a glance.
                colors.Sort((a, b) => {
                    int p = a.price.CompareTo(b.price);
                    if (p != 0) return p;
                    return string.Compare(a.name, b.name, StringComparison.OrdinalIgnoreCase);
                });
                // Sort nametag items so the shop reads top-to-bottom: stackable formatting
                // first (bold/italic/etc), then colors, highlights, sizes, fonts. Within
                // each subgroup fall back to alphabetical.
                nametags.Sort((a, b) =>
                {
                    int rank(string sku) {
                        string sub = NametagStyler.GetSubgroup(sku);
                        if (sub == null)   return 0;  // bold/italic/underline/strike
                        if (sub == "color") return 1;
                        if (sub == "glow")  return 2;  // highlights (kept the "glow" subgroup name internally)
                        if (sub == "size")  return 3;
                        return 4;  // font
                    }
                    int r = rank(a.sku).CompareTo(rank(b.sku));
                    if (r != 0) return r;
                    return string.Compare(a.name, b.name, StringComparison.OrdinalIgnoreCase);
                });
            }
            var sorted = new List<ApiClient.ShopItemData>();
            // Apply tab filter: keep only items matching the active category. Tab 0=All
            // keeps every list; 1..4 zero out the non-matching lists so the render loop
            // skips them and their section headers hide via the if(count>0) gate below.
            switch (shopCategoryFilter)
            {
                case 1: trails.Clear(); colors.Clear(); nametags.Clear(); break;  // Titles only
                case 2: titles.Clear(); colors.Clear(); nametags.Clear(); break;  // Trails only
                case 3: titles.Clear(); trails.Clear(); nametags.Clear(); break;  // Maps only
                case 4: titles.Clear(); trails.Clear(); colors.Clear();   break;  // Name Styles only
                default: break;  // 0 = All, no filter
            }

            sorted.AddRange(titles);
            sorted.AddRange(trails);
            sorted.AddRange(colors);
            sorted.AddRange(nametags);

            // Slot ordering inside the container (VLG renders in sibling order):
            //   [Titles header][title rows...][Trails header][trail rows...][Colors header][color rows...]
            int sibling = 0;
            if (titles.Count > 0 && shopTitlesHeader != null)
            {
                shopTitlesHeader.SetActive(true);
                shopTitlesHeader.transform.SetSiblingIndex(sibling++);
            }
            else if (shopTitlesHeader != null) shopTitlesHeader.SetActive(false);
            int rowIdx = 0;
            for (int i = 0; i < titles.Count && rowIdx < shopRows.Count; i++, rowIdx++)
            {
                ApplyShopRow(shopRows[rowIdx], titles[i], balance, s);
                shopRows[rowIdx].root.transform.SetSiblingIndex(sibling++);
            }

            if (trails.Count > 0 && shopTrailsHeader != null)
            {
                shopTrailsHeader.SetActive(true);
                shopTrailsHeader.transform.SetSiblingIndex(sibling++);
            }
            else if (shopTrailsHeader != null) shopTrailsHeader.SetActive(false);
            for (int i = 0; i < trails.Count && rowIdx < shopRows.Count; i++, rowIdx++)
            {
                ApplyShopRow(shopRows[rowIdx], trails[i], balance, s);
                shopRows[rowIdx].root.transform.SetSiblingIndex(sibling++);
            }

            if (colors.Count > 0 && shopColorsHeader != null)
            {
                shopColorsHeader.SetActive(true);
                shopColorsHeader.transform.SetSiblingIndex(sibling++);
            }
            else if (shopColorsHeader != null) shopColorsHeader.SetActive(false);
            for (int i = 0; i < colors.Count && rowIdx < shopRows.Count; i++, rowIdx++)
            {
                ApplyShopRow(shopRows[rowIdx], colors[i], balance, s);
                shopRows[rowIdx].root.transform.SetSiblingIndex(sibling++);
            }

            if (nametags.Count > 0 && shopNametagsHeader != null)
            {
                shopNametagsHeader.SetActive(true);
                shopNametagsHeader.transform.SetSiblingIndex(sibling++);
            }
            else if (shopNametagsHeader != null) shopNametagsHeader.SetActive(false);
            for (int i = 0; i < nametags.Count && rowIdx < shopRows.Count; i++, rowIdx++)
            {
                ApplyShopRow(shopRows[rowIdx], nametags[i], balance, s);
                shopRows[rowIdx].root.transform.SetSiblingIndex(sibling++);
            }

            // Hide leftovers.
            for (int i = sorted.Count; i < shopRows.Count; i++)
                shopRows[i].root.SetActive(false);
        }

        private static void ApplyShopRow(ShopRow r, ApiClient.ShopItemData it, int balance, ApiClient.PlayerStatsData s)
        {
            r.itemId = it.id;
            r.sku = it.sku;
            string col = string.IsNullOrEmpty(it.preview_color) ? "#FFFFFF" : it.preview_color;
            UIFactory.SetText(r.txtName, $"<color={col}>{it.name}</color>  <color=#888>({it.rarity})</color>");
            // Nametag kind shows a live rich-text preview of the buyer's own display name. The
            // descriptions are bold (matches the rest of the shop subtext for readability), but
            // since the description is already bold the inline <b> tag is visually a no-op. We
            // compensate for the bold preview specifically by upsizing it AND brightening it,
            // so it pops against the surrounding bold-grey label text.
            UIFactory.SetBold(r.txtDesc, true);
            if (it.kind == "nametag")
            {
                string previewName = s?.display_name;
                if (string.IsNullOrEmpty(previewName)) previewName = MatchTracker.LocalDisplayName;
                if (string.IsNullOrEmpty(previewName)) previewName = "Sid";
                string wrapped = NametagStyler.WrapForSku(previewName, it.sku);
                // Bold-specific emphasis: extra-large + pure white so the bold preview reads
                // as visually heavier than the surrounding bold-grey description text.
                string previewWrap = it.sku == "nametag_bold"
                    ? $"<size=145%><color=#FFFFFF>{wrapped}</color></size>"
                    : $"<size=130%>{wrapped}</size>";
                // Subgroup hint — "stackable" only applies to bold/italic/underline/strike.
                string sub = NametagStyler.GetSubgroup(it.sku);
                string hint = sub == null ? "stackable"
                    : sub == "color" ? "one color at a time"
                    : sub == "glow"  ? "one glow at a time — modded players only"
                    : sub == "size"  ? "one size at a time"
                    : sub == "typeface" ? "one typeface at a time — modded players only"
                    : "one font at a time";
                UIFactory.SetText(r.txtDesc, $"Preview: {previewWrap}  <color=#888>({hint})</color>");
                // ORDER IS LOAD-BEARING: typeface first, glow second. Setting TMP_Text.font
                // resets fontMaterial to the new font asset's default — if we applied glow
                // first, that swap would wipe the glow material. Apply font first, THEN layer
                // the glow material on top of whatever font-material TMP just assigned.
                string typefaceSku = sub == "typeface" ? it.sku : "";
                NametagFontRenderer.ApplyFontToLabel(r.txtDesc, typefaceSku, shopPreviewOriginalFonts);
                string glowSku = sub == "glow" ? it.sku : "";
                NametagGlowRenderer.ApplyGlowToLabel(r.txtDesc, glowSku, shopPreviewOriginalMats, shopPreviewGlowMatCache);
            }
            else
            {
                UIFactory.SetText(r.txtDesc, it.description ?? "");
                // Recycled row — if it was previously showing a glow / typeface preview,
                // restore the originals in the same order as apply (font first, glow second).
                NametagFontRenderer.ApplyFontToLabel(r.txtDesc, "", shopPreviewOriginalFonts);
                NametagGlowRenderer.ApplyGlowToLabel(r.txtDesc, "", shopPreviewOriginalMats, shopPreviewGlowMatCache);
            }
            UIFactory.SetText(r.txtPrice, $"{it.price}g");

            bool ownsThis = it.owned;
            bool canAfford = balance >= it.price;
            if (ownsThis) UIFactory.SetColor(r.txtPrice, C_GREEN);
            else if (canAfford) UIFactory.SetColor(r.txtPrice, C_GOLD);
            else UIFactory.SetColor(r.txtPrice, C_DIM);

            r.buyBtn.SetActive(!ownsThis);
            if (r.buyBtnTxt != null)
            {
                UIFactory.SetText(r.buyBtnTxt, "Buy");
                UIFactory.SetColor(r.buyBtnTxt, canAfford ? C_WHITE : new Color(0.55f, 0.55f, 0.6f));
                UIFactory.SetImageColor(r.buyBtn, canAfford
                    ? new Color(0.25f, 0.45f, 0.18f, 0.9f)
                    : new Color(0.25f, 0.25f, 0.28f, 0.8f));
            }
            r.setActiveBtn.SetActive(ownsThis && (it.kind == "title" || it.kind == "trail" || it.kind == "color" || it.kind == "nametag"));
            bool isActiveTitle = s != null && it.kind == "title" && s.active_title == it.name;
            bool isActiveTrail = s != null && it.kind == "trail" && s.active_trail_sku == it.sku;
            bool isActiveColor = s != null && it.kind == "color"
                && s.active_color_skus != null && s.active_color_skus.Contains(it.sku);
            bool isActiveNametag = s != null && it.kind == "nametag" && s.active_nametag_skus != null
                && s.active_nametag_skus.Contains(it.sku);
            bool isActive = isActiveTitle || isActiveTrail || isActiveColor || isActiveNametag;
            if (r.setActiveBtn != null)
            {
                UIFactory.SetImageColor(r.setActiveBtn, isActive
                    ? new Color(0.2f, 0.55f, 0.2f, 0.95f)   // active = green
                    : new Color(0.3f, 0.3f, 0.5f, 0.9f));   // inactive = default
                var txtComp = UIFactory.GetButtonText(r.setActiveBtn);
                // Colors are multi-equip (cycle via Shift) and nametags are stackable, so
                // their "active" label is "Remove" — clicking removes from the equipped set.
                // Titles/trails are single-active so their label stays "Equipped" (visual
                // indicator only; clicking switches to this one from a different equipped).
                bool isMultiEquip = it.kind == "nametag" || it.kind == "color";
                if (txtComp != null) UIFactory.SetText(txtComp,
                    isActive
                        ? (isMultiEquip ? "Remove" : "Equipped")
                        : (isMultiEquip ? "Equip" : "Set Active"));
            }

            // Preview button — trails only. Stash the color + price on the row so the click
            // handler has everything it needs without re-looking up the item.
            if (r.previewBtn != null)
            {
                bool isTrail = it.kind == "trail";
                r.previewBtn.SetActive(isTrail);
                if (isTrail)
                {
                    r.previewColor = it.preview_color ?? "";
                    r.previewPrice = it.price;
                    bool previewingThis = TrailPreview.IsActive && TrailPreview.ActiveSku == it.sku;
                    if (r.previewBtnTxt != null)
                        UIFactory.SetText(r.previewBtnTxt, previewingThis ? "Stop" : "Preview");
                    UIFactory.SetImageColor(r.previewBtn, previewingThis
                        ? new Color(0.5f, 0.3f, 0.25f, 0.9f)    // active preview = warm red
                        : new Color(0.25f, 0.4f, 0.55f, 0.9f));
                }
            }

            r.root.SetActive(true);
        }

        // ── Settings Tab ────────────────────────────────────────
        private static object txtConsentStatus, txtDeleteStatus;
        private static GameObject consentToggleBtn, deleteBtn, confirmDeleteBtn, cancelDelBtn, notifToggleBtn;
        private static GameObject fpsToggleBtn, pingToggleBtn, ingameChatToggleBtn, trailToggleBtn;
        private static object consentToggleTxt, notifToggleTxt, fpsToggleTxt, pingToggleTxt, ingameChatToggleTxt, trailToggleTxt;
        private static bool deleteArmed = false;

        // Helper: makes a left-aligned fixed-width button. Wraps in an HLG with a flex
        // spacer so the button keeps its sizeDelta when the outer panel uses VLG
        // (which otherwise stretches children to full width).
        private static GameObject SettingsButton(Transform parent, string name, string label,
            Color textColor, Color bgColor, Vector2 size, UnityEngine.Events.UnityAction onClick)
        {
            var row = new GameObject(name + "_row");
            row.transform.SetParent(parent, false);
            row.AddComponent<RectTransform>();
            UIFactory.AddHLG(row, spacing: 6, forceExpandH: true);
            UIFactory.AddLE(row, prefH: size.y + 2, flexH: 0);
            var btn = UIFactory.CreateButton(name, row.transform, label, 14f, textColor, bgColor, onClick, sizeDelta: size);
            UIFactory.AddLE(btn, prefW: size.x, prefH: size.y, flexW: 0, flexH: 0);
            var spacer = new GameObject("S");
            spacer.transform.SetParent(row.transform, false);
            spacer.AddComponent<RectTransform>();
            UIFactory.AddLE(spacer, flexW: 1);
            return btn;
        }

        private static GameObject BuildSettingsTab(Transform parent)
        {
            var panel = new GameObject("Settings");
            panel.transform.SetParent(parent, false);
            panel.AddComponent<RectTransform>();
            UIFactory.AddVLG(panel, spacing: 10, padL: 20, padR: 20, padT: 10, padB: 10);
            UIFactory.AddLE(panel, flexH: 1);

            UIFactory.CreateText("SH", panel.transform, "Settings", 22f, C_GOLD,
                UIFactory.AlignTopCenter, sizeDelta: new Vector2(600, 30));

            // ── Data consent (top) ──
            var consentBox = UIFactory.CreatePanel("SCB", panel.transform, C_PANEL);
            UIFactory.AddVLG(consentBox, spacing: 4, padL: 12, padR: 12, padT: 8, padB: 8);
            UIFactory.AddLE(consentBox, flexH: 0);
            UIFactory.CreateText("SCL", consentBox.transform,
                "Data Consent", 17f, new Color(0.7f, 0.85f, 1f),
                sizeDelta: new Vector2(700, 24));
            txtConsentStatus = UIFactory.CreateText("SCS", consentBox.transform, "",
                15f, C_LABEL, sizeDelta: new Vector2(700, 22));
            consentToggleBtn = SettingsButton(consentBox.transform, "SCT", "Revoke consent",
                C_WHITE, C_BTN, new Vector2(220, 28),
                () =>
                {
                    Plugin.Log.LogInfo("[SETTINGS] Consent toggle clicked");
                    if (Plugin.DataConsentGranted)
                    {
                        Plugin.DataConsent.Value = "denied";
                    }
                    else
                    {
                        Plugin.DataConsent.Value = "granted";
                    }
                    ApiClient.OnConsentChanged();
                    dirty = true;
                });
            consentToggleTxt = UIFactory.GetButtonText(consentToggleBtn);

            // ── Display toggles ──
            var dispBox = UIFactory.CreatePanel("SDispB", panel.transform, C_PANEL);
            UIFactory.AddVLG(dispBox, spacing: 4, padL: 12, padR: 12, padT: 8, padB: 8);
            UIFactory.AddLE(dispBox, flexH: 0);
            UIFactory.CreateText("SDispL", dispBox.transform,
                "Display", 17f, new Color(0.7f, 0.85f, 1f),
                sizeDelta: new Vector2(700, 24));
            fpsToggleBtn = SettingsButton(dispBox.transform, "SFPS", "",
                C_WHITE, C_BTN, new Vector2(260, 28),
                () =>
                {
                    Plugin.Log.LogInfo("[SETTINGS] FPS toggled");
                    Plugin.ShowFps.Value = !Plugin.ShowFps.Value;
                    dirty = true;
                });
            fpsToggleTxt = UIFactory.GetButtonText(fpsToggleBtn);
            pingToggleBtn = SettingsButton(dispBox.transform, "SPing", "",
                C_WHITE, C_BTN, new Vector2(260, 28),
                () =>
                {
                    Plugin.Log.LogInfo("[SETTINGS] Ping/region toggled");
                    Plugin.ShowRegionPing.Value = !Plugin.ShowRegionPing.Value;
                    dirty = true;
                });
            pingToggleTxt = UIFactory.GetButtonText(pingToggleBtn);
            ingameChatToggleBtn = SettingsButton(dispBox.transform, "SIgChat", "",
                C_WHITE, C_BTN, new Vector2(260, 28),
                () =>
                {
                    Plugin.Log.LogInfo("[SETTINGS] In-game chat overlay toggled");
                    Plugin.ShowIngameChat.Value = !Plugin.ShowIngameChat.Value;
                    dirty = true;
                });
            ingameChatToggleTxt = UIFactory.GetButtonText(ingameChatToggleBtn);
            trailToggleBtn = SettingsButton(dispBox.transform, "STrail", "",
                C_WHITE, C_BTN, new Vector2(260, 28),
                () =>
                {
                    Plugin.Log.LogInfo("[SETTINGS] Trails toggled");
                    Plugin.ShowTrails.Value = !Plugin.ShowTrails.Value;
                    // Live effect mid-match: ON → re-attach for everyone, OFF → detach.
                    if (Plugin.ShowTrails.Value)
                    {
                        if (GameStateWatcher.IsInMatch) TrailCosmetic.OnMatchStart();
                    }
                    else
                    {
                        TrailCosmetic.OnMatchEnd();
                    }
                    dirty = true;
                });
            trailToggleTxt = UIFactory.GetButtonText(trailToggleBtn);

            // ── Chat pop-up notifications ──
            var notifBox = UIFactory.CreatePanel("SNB", panel.transform, C_PANEL);
            UIFactory.AddVLG(notifBox, spacing: 4, padL: 12, padR: 12, padT: 8, padB: 8);
            UIFactory.AddLE(notifBox, flexH: 0);
            UIFactory.CreateText("SNL", notifBox.transform,
                "Chat log notifications", 17f, new Color(0.7f, 0.85f, 1f),
                sizeDelta: new Vector2(700, 24));
            UIFactory.CreateText("SND", notifBox.transform,
                "On-screen pop-ups for incoming chat + XP / level notifications. Chat log in My Stats still updates either way.",
                13f, C_DIM, sizeDelta: new Vector2(700, 34));
            notifToggleBtn = SettingsButton(notifBox.transform, "SNT", "",
                C_WHITE, C_BTN, new Vector2(260, 28),
                () =>
                {
                    Plugin.Log.LogInfo("[SETTINGS] Notifications toggled");
                    Plugin.ShowNotifications.Value = !Plugin.ShowNotifications.Value;
                    dirty = true;
                });
            notifToggleTxt = UIFactory.GetButtonText(notifToggleBtn);

            // ── Filler spacer so Delete sits at the bottom ──
            var mid = new GameObject("SMid");
            mid.transform.SetParent(panel.transform, false);
            mid.AddComponent<RectTransform>();
            UIFactory.AddLE(mid, flexH: 1);

            // ── Delete my data (last, so it's hard to click accidentally) ──
            var delBox = UIFactory.CreatePanel("SDB", panel.transform, C_PANEL);
            UIFactory.AddVLG(delBox, spacing: 4, padL: 12, padR: 12, padT: 8, padB: 8);
            UIFactory.AddLE(delBox, flexH: 0);
            UIFactory.CreateText("SDL", delBox.transform,
                "Delete My Data", 17f, new Color(1f, 0.6f, 0.6f),
                sizeDelta: new Vector2(700, 24));
            UIFactory.CreateText("SDD", delBox.transform,
                "Anonymizes your Steam ID, display name, and Discord link. Matches stay so other players' " +
                "Elo and histories aren't affected. You will no longer appear on leaderboards.\n" +
                "<b><color=#FF8888>IRREVERSIBLE:</color></b> this Steam ID can never re-register. Future matches " +
                "from this account will show as [Deleted User] and won't count toward stats.",
                13f, C_DIM, sizeDelta: new Vector2(700, 68));
            var delRow = new GameObject("SDR");
            delRow.transform.SetParent(delBox.transform, false);
            delRow.AddComponent<RectTransform>();
            UIFactory.AddHLG(delRow, spacing: 8, forceExpandH: true);
            UIFactory.AddLE(delRow, prefH: 30, flexH: 0);
            deleteBtn = UIFactory.CreateButton("SDBtn", delRow.transform,
                "Delete my data…", 14f, C_WHITE, new Color(0.45f, 0.18f, 0.18f, 0.9f),
                () =>
                {
                    if (!ClickGuard.Claim()) return;
                    deleteArmed = true;
                    dirty = true;
                },
                sizeDelta: new Vector2(200, 28));
            UIFactory.AddLE(deleteBtn, prefW: 200, prefH: 28, flexW: 0, flexH: 0);
            confirmDeleteBtn = UIFactory.CreateButton("SDCBtn", delRow.transform,
                "Confirm — really delete", 14f, C_WHITE, new Color(0.7f, 0.15f, 0.15f, 0.95f),
                () =>
                {
                    if (!ClickGuard.Claim()) return;
                    var id = MatchTracker.LocalSteamId;
                    if (string.IsNullOrEmpty(id) || id == "unknown") return;
                    deleteArmed = false;
                    ApiClient.DeletePlayerData(id, (ok, msg) =>
                    {
                        Plugin.Log.LogInfo($"[PRIVACY] Delete result: ok={ok} msg={msg}");
                        if (ok)
                        {
                            Plugin.DataConsent.Value = "denied";
                            ApiClient.OnConsentChanged();
                            if (txtDeleteStatus != null)
                                UIFactory.SetText(txtDeleteStatus, "<color=#88FF88>Your data has been anonymized. Consent is now Denied.</color>");
                        }
                        else
                        {
                            if (txtDeleteStatus != null)
                                UIFactory.SetText(txtDeleteStatus, $"<color=#FF6666>Deletion failed: {msg}</color>");
                        }
                        dirty = true;
                    });
                },
                sizeDelta: new Vector2(220, 28));
            UIFactory.AddLE(confirmDeleteBtn, prefW: 220, prefH: 28, flexW: 0, flexH: 0);
            confirmDeleteBtn.SetActive(false);
            cancelDelBtn = UIFactory.CreateButton("SDXBtn", delRow.transform,
                "Cancel", 14f, C_LABEL, C_BTN,
                () =>
                {
                    if (!ClickGuard.Claim()) return;
                    deleteArmed = false;
                    dirty = true;
                },
                sizeDelta: new Vector2(90, 28));
            UIFactory.AddLE(cancelDelBtn, prefW: 90, prefH: 28, flexW: 0, flexH: 0);
            cancelDelBtn.SetActive(false);
            var delSpacer = new GameObject("SDSp");
            delSpacer.transform.SetParent(delRow.transform, false);
            delSpacer.AddComponent<RectTransform>();
            UIFactory.AddLE(delSpacer, flexW: 1);
            txtDeleteStatus = UIFactory.CreateText("SDS", delBox.transform, "",
                14f, C_LABEL, sizeDelta: new Vector2(700, 22));

            return panel;
        }

        private static void RefreshSettings()
        {
            if (txtConsentStatus != null)
            {
                string status;
                if (Plugin.DataConsentGranted)
                    status = "Status: <color=#88FF88>Allowed</color> — match data and linking are active.";
                else if (Plugin.DataConsentAsked)
                    status = "Status: <color=#FF9966>Denied</color> — mod runs offline. No data leaves your machine.";
                else
                    status = "Status: <color=#DDDD66>Unset</color> — the consent prompt will appear on next launch.";
                UIFactory.SetText(txtConsentStatus, status);
            }
            if (consentToggleTxt != null)
                UIFactory.SetText(consentToggleTxt, Plugin.DataConsentGranted ? "Revoke consent" : "Allow data reporting");

            if (deleteBtn != null) deleteBtn.SetActive(!deleteArmed);
            if (confirmDeleteBtn != null) confirmDeleteBtn.SetActive(deleteArmed);
            if (cancelDelBtn != null) cancelDelBtn.SetActive(deleteArmed);

            if (notifToggleTxt != null)
                UIFactory.SetText(notifToggleTxt,
                    Plugin.ShowNotifications.Value
                        ? "Chat notifications: <color=#88FF88>ON</color>"
                        : "Chat notifications: <color=#FF9966>OFF</color>");
            if (fpsToggleTxt != null && Plugin.ShowFps != null)
                UIFactory.SetText(fpsToggleTxt,
                    Plugin.ShowFps.Value
                        ? "FPS counter: <color=#88FF88>ON</color>"
                        : "FPS counter: <color=#FF9966>OFF</color>");
            if (pingToggleTxt != null && Plugin.ShowRegionPing != null)
                UIFactory.SetText(pingToggleTxt,
                    Plugin.ShowRegionPing.Value
                        ? "Ping / region display: <color=#88FF88>ON</color>"
                        : "Ping / region display: <color=#FF9966>OFF</color>");
            if (ingameChatToggleTxt != null && Plugin.ShowIngameChat != null)
                UIFactory.SetText(ingameChatToggleTxt,
                    Plugin.ShowIngameChat.Value
                        ? "In-game chat overlay: <color=#88FF88>ON</color>"
                        : "In-game chat overlay: <color=#FF9966>OFF</color>");
            if (trailToggleTxt != null && Plugin.ShowTrails != null)
                UIFactory.SetText(trailToggleTxt,
                    Plugin.ShowTrails.Value
                        ? "Cosmetic trails: <color=#88FF88>ON</color>"
                        : "Cosmetic trails: <color=#FF9966>OFF</color>");
        }

        private static void RefreshRecentSeries()
        {
            if(txtRecentSeries==null)return;
            var series=ApiClient.CachedRecentSeries;
            if(series==null||series.Count==0){UIFactory.SetText(txtRecentSeries,"No recent series");if(seriesPrev!=null)seriesPrev.SetActive(false);if(seriesNext!=null)seriesNext.SetActive(false);if(txtSeriesPage!=null)UIFactory.SetText(txtSeriesPage,"");return;}
            // 20 series per page (was 8). Server returns up to 100 — see FetchRecentSeries.
            int perPage=20,totalPages=(series.Count+perPage-1)/perPage;
            recentSeriesPage=Math.Max(0,Math.Min(recentSeriesPage,totalPages-1));
            int start=recentSeriesPage*perPage,end=Math.Min(start+perPage,series.Count);
            string txt="";
            string myName=ApiClient.CachedPlayerStats?.display_name??"";
            for(int i=start;i<end;i++)
            {
                var s=series[i];
                bool p1Won=s.p1_wins>s.p2_wins;
                string wName=p1Won?s.p1_name:s.p2_name;
                string lName=p1Won?s.p2_name:s.p1_name;
                int wScore=p1Won?s.p1_wins:s.p2_wins;
                int lScore=p1Won?s.p2_wins:s.p1_wins;
                int wRating=p1Won?s.p1_rating:s.p2_rating;
                int lRating=p1Won?s.p2_rating:s.p1_rating;
                float wRC=p1Won?s.p1_rating_change:s.p2_rating_change;
                float lRC=p1Won?s.p2_rating_change:s.p1_rating_change;
                bool iAmWinner=wName==myName;
                bool iAmLoser=lName==myName;
                string wCol=iAmWinner?"#00FF00":"#FFFFFF";
                string lCol=iAmLoser?"#FF6666":"#AAAAAA";
                string wElo=wRC!=0?$" <color=#00FF00>+{wRC:F0}</color>":"";
                string lElo=lRC!=0?$" <color=#FF6666>{lRC:F0}</color>":"";
                // Inline ratings: "<name> (1842) +12 ELO  2-0  (1755) <opp>"
                string wRatingTag=wRating>0?$" <color=#888>({wRating})</color>":"";
                string lRatingTag=lRating>0?$" <color=#888>({lRating})</color>":"";
                txt+=$"<color={wCol}>{Trunc(wName,12)}</color>{wRatingTag}{wElo}  <b>{wScore}-{lScore}</b>  <color={lCol}>{Trunc(lName,12)}</color>{lRatingTag}{lElo}\n";
                // Bet sub-rows under each series. Indent + smaller font + green for winners,
                // dim grey for losers. Show "AsteRiA bet 500g on Sid → +505g" style.
                if (s.bets != null && s.bets.Count > 0)
                {
                    foreach (var b in s.bets)
                    {
                        string bettorTag = b.bettor_name == myName ? "<b>You</b>" : Trunc(b.bettor_name ?? "?", 14);
                        if (b.won)
                            txt += $"    <color=#88CC88>↳ {bettorTag} bet {b.amount}g on {Trunc(b.bet_on_name ?? "?", 12)} → <b>+{b.payout}g</b></color>\n";
                        else
                            txt += $"    <color=#664444>↳ {bettorTag} bet {b.amount}g on {Trunc(b.bet_on_name ?? "?", 12)} — lost</color>\n";
                    }
                }
            }
            UIFactory.SetText(txtRecentSeries,txt);
            if(seriesPrev!=null)seriesPrev.SetActive(recentSeriesPage>0);
            if(seriesNext!=null)seriesNext.SetActive(recentSeriesPage<totalPages-1);
            if(txtSeriesPage!=null)UIFactory.SetText(txtSeriesPage,totalPages>1?$"{recentSeriesPage+1}/{totalPages}":"");
        }

        private static void RefreshVersionStatus(){if(txtVersionStatus==null)return;if(ApiClient.ForceUpdateRequired){UIFactory.SetText(txtVersionStatus,"<color=#FF4444>UPDATE REQUIRED — server is rejecting this mod version</color>");if(updateBtn!=null)updateBtn.SetActive(true);return;}if(ApiClient.UpdateReady){UIFactory.SetText(txtVersionStatus,"<color=#44FF44>Close ROUNDS to apply update</color>");if(updateBtn!=null)updateBtn.SetActive(false);return;}if(ApiClient.IsUpdating){UIFactory.SetText(txtVersionStatus,"<color=#66CCFF>Downloading...</color>");if(updateBtn!=null)updateBtn.SetActive(false);return;}string latest=ApiClient.LatestModVersion;if(latest==null){UIFactory.SetText(txtVersionStatus,"");if(updateBtn!=null)updateBtn.SetActive(false);return;}if(latest==Plugin.ModVersion){UIFactory.SetText(txtVersionStatus,"<color=#44AA44>up to date</color>");if(updateBtn!=null)updateBtn.SetActive(false);}else{UIFactory.SetText(txtVersionStatus,$"<color=#FFAA33>v{latest} available!</color>");if(updateBtn!=null)updateBtn.SetActive(true);}}

        private static void RefreshMyStats(){var s=ApiClient.CachedPlayerStats;if(s==null){UIFactory.SetText(txtRating,"—");return;}UIFactory.SetText(txtRating,$"{s.rating:F0}");UIFactory.SetText(txtRD,$"RD: {s.rating_deviation:F0}    Peak: {s.peak_rating:F0}");UIFactory.SetText(txtLevel,$"Level {s.level}");if(s.level<100&&s.xp_for_next_level>0){UIFactory.SetText(txtXPProg,$"{s.xp_into_level}/{s.xp_for_next_level} XP");UIFactory.SetFill(xpFill,(float)s.xp_into_level/s.xp_for_next_level);}else{UIFactory.SetText(txtXPProg,"MAX");UIFactory.SetFill(xpFill,1f);}UIFactory.SetText(txtTotalXP,$"{s.total_xp:N0} XP");var history=ApiClient.CachedMatchHistory;var sR=history?.FindAll(m=>m.is_ranked)??new List<ApiClient.MatchHistoryEntry>();var sC=history?.FindAll(m=>!m.is_ranked)??new List<ApiClient.MatchHistoryEntry>();int cW=0,cL=0,sweepG=0,sweepT=0;foreach(var m in sC){if(m.won)cW++;else cL++;}if(history!=null)foreach(var m in history){if(m.won&&m.opponent_rounds_won==0)sweepG++;if(!m.won&&m.player_rounds_won==0)sweepT++;}int rW=s.ranked_series_wins,rL=s.ranked_series_losses;UIFactory.SetText(txtRankedRec,rW+rL>0?$"<color=#FFD94D>Ranked:</color> {rW}W / {rL}L ({(rL>0?$"{(float)rW/rL:F1}":$"{rW}:0")})":"<color=#FFD94D>Ranked:</color> —");if(sR.Count>0){int st=CalcStreak(sR);string c=st>0?"#00FF00":"#FF6666";UIFactory.SetText(txtRankedStrk,$"  <color={c}>Streak: {(st>0?$"{st}W":$"{-st}L")}</color>"+(s.best_ranked_streak>0?$"  Best: {s.best_ranked_streak}W":""));}else UIFactory.SetText(txtRankedStrk,"");UIFactory.SetText(txtCasualRec,sC.Count>0?$"Casual: {cW}W / {cL}L ({(cL>0?$"{(float)cW/cL:F1}":cW>0?$"{cW}:0":"")})":"Casual: —");if(sC.Count>0){int st=CalcStreak(sC);string c=st>0?"#00FF00":"#FF6666";UIFactory.SetText(txtCasualStrk,$"  <color={c}>Streak: {(st>0?$"{st}W":$"{-st}L")}</color>"+(s.best_casual_streak>0?$"  Best: {s.best_casual_streak}W":""));}else UIFactory.SetText(txtCasualStrk,"");UIFactory.SetText(txtSweeps,$"Sweeps: <color=#00FF00>5-0 x{sweepG}</color>  <color=#FF6666>0-5 x{sweepT}</color>");UIFactory.SetText(txtTotalRec,$"Total: {s.total_matches} ({s.wins}W / {s.losses}L)  <color=#FFD94D>Gold: {(s.gold_earned - s.gold_spent)}</color>");/* Hit% / Block% lifetime — one-sided totals (only the reporter-side's client has these
 * counters). Split across two lines in the 44px-tall txtAccuracy field because the
 * combined string overflows 340px at 15pt and TMP wordwrap clips the second line
 * when the field is only 22px tall. Newline gives TMP a proper 2-line render. */
{string hitLine=s.bullets_fired>0?$"<color=#FF9988>Hit:</color> {(float)s.bullets_hit*100f/s.bullets_fired:F1}% ({s.bullets_hit}/{s.bullets_fired})":"<color=#FF9988>Hit:</color> —";string blkLine=s.blocks_activated>0?$"<color=#99CCFF>Block:</color> {(float)s.blocks_successful*100f/s.blocks_activated:F1}% ({s.blocks_successful}/{s.blocks_activated})":"<color=#99CCFF>Block:</color> —";UIFactory.SetText(txtAccuracy,$"{hitLine}\n{blkLine}");}RefreshHistory(sR,sC);RefreshSession();if(linkCodeBtn!=null&&txtLinkCode!=null){bool linked=!string.IsNullOrEmpty(s.discord_id);linkCodeBtn.SetActive(!linked);if(linked){string raw=!string.IsNullOrEmpty(s.discord_username)?$"@{s.discord_username}":$"ID {s.discord_id}";string who=discordRevealed?raw:"<color=#888>••••• (click to show)</color>";UIFactory.SetText(txtLinkCode,$"<color=#00FF00>Linked to Discord</color> ({who})");}}RefreshChatLog();}
        private static void RefreshHistory(List<ApiClient.MatchHistoryEntry> ranked,List<ApiClient.MatchHistoryEntry> casual){foreach(var r in rankedRows){r.root.SetActive(false);r.seriesGO.SetActive(false);}if(ranked.Count>0){var groups=GroupBySeries(ranked);int gpp=3,totalP=(groups.Count+gpp-1)/gpp;rankedPage=Math.Max(0,Math.Min(rankedPage,totalP-1));int start=rankedPage*gpp,end=Math.Min(start+gpp,groups.Count);int ri=0;for(int g=start;g<end&&ri<rankedRows.Count;g++){var grp=groups[g];if(grp.matches.Count==0)continue;var first=grp.matches[0];if(grp.series_id!=null&&ri<rankedRows.Count){var row=rankedRows[ri];string score=first.series_score??"?-?",opp=FormatOpponentForRow(first,18);bool complete=false,won=false;try{var p=score.Split('-');int mw=int.Parse(p[0]),tw=int.Parse(p[1]);complete=mw>=2||tw>=2;won=mw>tw;}catch{}UIFactory.SetText(row.txtSeriesHead,complete?$"Series {(won?"W":"L")} {score}  vs {opp}":$"Series {score}  vs {opp}  (in progress)");UIFactory.SetColor(row.txtSeriesHead,complete?(won?C_GREEN:C_RED):C_GOLD);/* The per-match row shows XP→gold (typically 4-5g/match); the series-win bonus (10-12g) was invisible because the history row never referenced series_gold_gained. Find the populated value across matches in this group (server sets it on the last-match-of-series row) and append to the elo line. */int grpSeriesGold=0;foreach(var mm in grp.matches)if(mm.series_gold_gained>grpSeriesGold)grpSeriesGold=mm.series_gold_gained;if(complete&&first.series_rating_change!=0f){float rc=first.series_rating_change;string goldStr=grpSeriesGold>0?$" <color=#FFD94D>+{grpSeriesGold}g</color>":"";UIFactory.SetText(row.txtSeriesElo,$"{(rc>0?"+":"")}{rc:F0} elo{goldStr}");UIFactory.SetColor(row.txtSeriesElo,rc>0?C_GREEN:C_RED);}else UIFactory.SetText(row.txtSeriesElo,"");row.seriesGO.SetActive(true);foreach(var m in grp.matches){if(ri>=rankedRows.Count)break;FillRow(rankedRows[ri],m,true);ri++;}}else{FillRow(rankedRows[ri],first,false);ri++;}}rPrev.SetActive(rankedPage>0);rNext.SetActive(rankedPage<totalP-1);UIFactory.SetText(txtRankedPage,totalP>1?$"{rankedPage+1}/{totalP}":"");}else{rPrev.SetActive(false);rNext.SetActive(false);UIFactory.SetText(txtRankedPage,"");}foreach(var r in casualRows)r.root.SetActive(false);if(casual.Count>0){int mpp=6,totalP=(casual.Count+mpp-1)/mpp;casualPage=Math.Max(0,Math.Min(casualPage,totalP-1));int start=casualPage*mpp,end=Math.Min(start+mpp,casual.Count);for(int i=start;i<end;i++){int ri=i-start;if(ri<casualRows.Count)FillRow(casualRows[ri],casual[i],false);}cPrev.SetActive(casualPage>0);cNext.SetActive(casualPage<totalP-1);UIFactory.SetText(txtCasualPage,totalP>1?$"{casualPage+1}/{totalP}":"");}else{cPrev.SetActive(false);cNext.SetActive(false);UIFactory.SetText(txtCasualPage,"");}}

        private static void FillRow(HistoryRow row,ApiClient.MatchHistoryEntry m,bool indent){string r=m.won?"W":"L";Color c=m.won?C_GREEN:C_RED;string pts=(m.player_points+m.opponent_points>0)?$" <color=#{(m.won?"88AA88":"AA8888")}>{m.player_points}-{m.opponent_points}p</color>":"";UIFactory.SetText(row.txtResult,$"{(indent?"    ":"  ")}{r}  {m.player_rounds_won}-{m.opponent_rounds_won}{pts}");UIFactory.SetColor(row.txtResult,c);UIFactory.SetText(row.txtOpp,indent?"":$"vs {FormatOpponentForRow(m,20)}");UIFactory.SetText(row.txtXP,m.xp_gained>0?(m.gold_gained>0?$"+{m.xp_gained}xp <color=#FFD94D>+{m.gold_gained}g</color>":$"+{m.xp_gained}xp"):"");string dt="";try{if(!string.IsNullOrEmpty(m.ended_at)&&m.ended_at.Length>=10)dt=DateTime.Parse(m.ended_at).ToString("M/d");}catch{}UIFactory.SetText(row.txtDate,dt);UIFactory.SetText(row.txtCards,!string.IsNullOrEmpty(m.cards_display)?$"        Cards: {m.cards_display}":"");UIFactory.SetText(row.txtOppCards,!string.IsNullOrEmpty(m.opp_cards_display)?$"        Opp:   {m.opp_cards_display}":"");row.root.SetActive(true);}

        // Renders the opponent name + colored title tag for match-history rows. Title is the
        // opponent's CURRENT active title (view-time, not snapshot-at-match) — cheap join in the
        // history endpoint, good enough to answer "who am I looking at right now."
        private static string FormatOpponentForRow(ApiClient.MatchHistoryEntry m,int nameMax)
        {
            string nm = Trunc(m?.opponent_name ?? "", nameMax);
            if (m == null || string.IsNullOrEmpty(m.opponent_title)) return nm;
            string col = string.IsNullOrEmpty(m.opponent_title_color) ? "#CCCCCC" : m.opponent_title_color;
            return $"{nm} <b><color={col}>[{m.opponent_title}]</color></b>";
        }

        private static void RefreshSession(){int games=GameStateWatcher.SessionMatchCount;bool inRoom=GameStateWatcher.IsInRoom;string oppSteamId=GameStateWatcher.OpponentSteamId;string oppName=GameStateWatcher.OpponentDisplayName;var history=ApiClient.CachedMatchHistory;/* Show opponent lifetime record when in room */if(inRoom&&!string.IsNullOrEmpty(oppSteamId)&&!oppSteamId.StartsWith("photon_")&&history!=null){int ltW=0,ltL=0;string lastPlayed="";foreach(var m in history){if(m.opponent_steam_id==oppSteamId){if(m.won)ltW++;else ltL++;if(string.IsNullOrEmpty(lastPlayed)){try{lastPlayed=DateTime.Parse(m.ended_at).ToString("M/d/yyyy");}catch{}}}}if(ltW+ltL>0){string col=ltW>ltL?"#00FF00":ltW<ltL?"#FF6666":"#AAAAAA";UIFactory.SetText(txtSessionOppLifetime,$"  vs {oppName}:  <color={col}>{ltW}W-{ltL}L lifetime</color>  (last: {lastPlayed})");}else{UIFactory.SetText(txtSessionOppLifetime,$"  vs {oppName}:  First time playing!");}UIFactory.SetColor(txtSessionOppLifetime,new Color(0.6f,0.75f,1f));}else if(inRoom&&!string.IsNullOrEmpty(oppName)&&oppName!="Opponent"){UIFactory.SetText(txtSessionOppLifetime,$"  In room with {oppName}");UIFactory.SetColor(txtSessionOppLifetime,C_DIM);}else{UIFactory.SetText(txtSessionOppLifetime,"");}if(games<=0){UIFactory.SetText(txtSessionSum,inRoom?"In game — no results yet":"No games this session");UIFactory.SetColor(txtSessionSum,C_DIM);UIFactory.SetText(txtSessionSplit,"");UIFactory.SetText(txtSessionSweeps,"");return;}int mins=(int)(DateTime.UtcNow-GameStateWatcher.SessionStartTime).TotalMinutes;string time=mins>=60?$"{mins/60}h {mins%60}m":$"{mins}m";int rw=GameStateWatcher.SessionRankedWins,rl=GameStateWatcher.SessionRankedLosses,cw=GameStateWatcher.SessionCasualWins,cl=GameStateWatcher.SessionCasualLosses;int sesSweepG=0,sesSweepT=0;if(history!=null){var sesStart=GameStateWatcher.SessionStartTime;foreach(var m in history){DateTime mTime=DateTime.UtcNow;try{if(!string.IsNullOrEmpty(m.ended_at))mTime=DateTime.Parse(m.ended_at).ToUniversalTime();}catch{}if(mTime<sesStart)continue;if(m.won&&m.opponent_rounds_won==0)sesSweepG++;if(!m.won&&m.player_rounds_won==0)sesSweepT++;}}UIFactory.SetText(txtSessionSum,$"{games} games    {rw+cw}W - {rl+cl}L    {time}");UIFactory.SetColor(txtSessionSum,C_WHITE);string splitLine="";if(rw+rl>0&&cw+cl>0)splitLine=$"  Ranked: {rw}W/{rl}L    Casual: {cw}W/{cl}L";UIFactory.SetText(txtSessionSplit,splitLine);if(sesSweepG+sesSweepT>0)UIFactory.SetText(txtSessionSweeps,$"  Sweeps: <color=#00FF00>5-0 x{sesSweepG}</color>  <color=#FF6666>0-5 x{sesSweepT}</color>");else UIFactory.SetText(txtSessionSweeps,"");var wl=GameStateWatcher.SessionWLByOpponent;var st=GameStateWatcher.SessionTimeByOpponent;int idx=0;if(wl!=null)foreach(var kvp in wl){int[]a=kvp.Value;if(a==null||a.Length<4)continue;int ow=a[0]+a[2],ol=a[1]+a[3];string line=$"  vs {kvp.Key}:  {ow}W-{ol}L";if(a[0]+a[1]>0&&a[2]+a[3]>0)line+=$"  (R:{a[0]}-{a[1]} C:{a[2]}-{a[3]})";if(st!=null&&st.ContainsKey(kvp.Key)){int m=(int)st[kvp.Key];line+=m>=60?$"   {m/60}h {m%60}m":$"   {m}m";}while(sessionOppTexts.Count<=idx)sessionOppTexts.Add(UIFactory.CreateText($"so{sessionOppTexts.Count}",sessionOppContainer.transform,"",15f,C_LABEL,sizeDelta:new Vector2(340,22)));UIFactory.SetText(sessionOppTexts[idx],line);UIFactory.SetColor(sessionOppTexts[idx],ow>ol?C_GREEN:ow<ol?C_RED:C_DIM);var go=(sessionOppTexts[idx]as Component)?.gameObject;if(go)go.SetActive(true);idx++;}for(int i=idx;i<sessionOppTexts.Count;i++){var go=(sessionOppTexts[i]as Component)?.gameObject;if(go)go.SetActive(false);}}

        private static void RefreshLeaderboard(){string[]hL={"#","Lv","Player","Rating","W","L","W/L","Gold"};string[]hK={"rank","level","display_name","rating","wins","losses","wl_ratio","gold"};if(lbSortTexts!=null)for(int i=0;i<hK.Length&&i<lbSortTexts.Length;i++){if(lbSortTexts[i]==null)continue;string arrow=lbSort==hK[i]?(lbSortDesc?" v":" ^"):"";UIFactory.SetText(lbSortTexts[i],hL[i]+arrow);UIFactory.SetColor(lbSortTexts[i],lbSort==hK[i]?C_WHITE:C_LABEL);if(lbSortBtns!=null&&i<lbSortBtns.Length)UIFactory.SetImageColor(lbSortBtns[i],lbSort==hK[i]?C_TABACT:C_TAB);}var board=ApiClient.CachedLeaderboard;foreach(var r in lbRows)r.root.SetActive(false);if(board==null||board.entries==null||board.entries.Length==0){UIFactory.SetText(txtLBDetail,"No leaderboard data");UIFactory.SetText(txtLBCount,"");return;}var entries=new List<ApiClient.LeaderboardEntry>(board.entries);switch(lbSort){case "rank":entries.Sort((a,b)=>lbSortDesc?b.rank.CompareTo(a.rank):a.rank.CompareTo(b.rank));break;case "level":entries.Sort((a,b)=>lbSortDesc?b.level.CompareTo(a.level):a.level.CompareTo(b.level));break;case "display_name":entries.Sort((a,b)=>lbSortDesc?string.Compare(b.display_name,a.display_name,StringComparison.OrdinalIgnoreCase):string.Compare(a.display_name,b.display_name,StringComparison.OrdinalIgnoreCase));break;case "rating":entries.Sort((a,b)=>lbSortDesc?b.rating.CompareTo(a.rating):a.rating.CompareTo(b.rating));break;case "wins":entries.Sort((a,b)=>lbSortDesc?b.wins.CompareTo(a.wins):a.wins.CompareTo(b.wins));break;case "losses":entries.Sort((a,b)=>lbSortDesc?b.losses.CompareTo(a.losses):a.losses.CompareTo(b.losses));break;case "wl_ratio":entries.Sort((a,b)=>{float ra=a.losses>0?(float)a.wins/a.losses:a.wins*100f;float rb=b.losses>0?(float)b.wins/b.losses:b.wins*100f;return lbSortDesc?rb.CompareTo(ra):ra.CompareTo(rb);});break;case "gold":entries.Sort((a,b)=>lbSortDesc?b.gold.CompareTo(a.gold):a.gold.CompareTo(b.gold));break;}int lbPP=50,lbTotalP=(entries.Count+lbPP-1)/lbPP;lbPage=Math.Max(0,Math.Min(lbPage,lbTotalP-1));int lbStart=lbPage*lbPP,lbEnd=Math.Min(lbStart+lbPP,entries.Count);for(int i=lbStart;i<lbEnd&&(i-lbStart)<lbRows.Count;i++){var e=entries[i];var row=lbRows[i-lbStart];row.steamId=e.steam_id;bool local=e.steam_id==MatchTracker.LocalSteamId;string ratio=e.losses>0?$"{(float)e.wins/e.losses:F1}":e.wins>0?$"{e.wins}:0":"0:0";UIFactory.SetText(row.txtRank,$"{e.rank}");UIFactory.SetColor(row.txtRank,e.rank==1?new Color(1f,0.84f,0f):e.rank==2?new Color(0.75f,0.75f,0.75f):e.rank==3?new Color(0.8f,0.5f,0.2f):C_GOLD);UIFactory.SetText(row.txtLv,$"{e.level}");string _lbName=Trunc(e.display_name,14);if(!string.IsNullOrEmpty(e.title)){string _tc=string.IsNullOrEmpty(e.title_color)?"#FFFFFF":e.title_color;_lbName=$"{_lbName} <b><color={_tc}>[{e.title}]</color></b>";}UIFactory.SetText(row.txtName,_lbName);UIFactory.SetColor(row.txtName,local?C_GREEN:C_WHITE);UIFactory.SetText(row.txtRating,$"{e.rating}");UIFactory.SetText(row.txtW,$"{e.wins}");UIFactory.SetText(row.txtL,$"{e.losses}");UIFactory.SetText(row.txtWL,ratio);UIFactory.SetText(row.txtGold,e.gold>0?$"{e.gold}":"0");bool sel=e.steam_id==selectedSteamId;UIFactory.SetImageColor(row.hlWrap,sel?new Color(0.2f,0.25f,0.4f,0.4f):new Color(0.15f,0.15f,0.2f,0.01f));row.root.SetActive(true);}UIFactory.SetText(txtLBCount,$"{board.total_players} players ranked");lbPrev.SetActive(lbPage>0);lbNext.SetActive(lbPage<lbTotalP-1);UIFactory.SetText(txtLBPage,lbTotalP>1?$"{lbPage+1}/{lbTotalP}":"");if(!string.IsNullOrEmpty(selectedSteamId)&&selectedStats!=null){var ps=selectedStats;UIFactory.SetText(txtLBPlayerName,$"{ps.display_name}   <color=#66CCFF>Level {ps.level}</color>");string detail=$"\nRating: {ps.rating:F0}   RD: {ps.rating_deviation:F0}   Peak: {ps.peak_rating:F0}\n{ps.total_matches} matches ({ps.wins}W / {ps.losses}L)  WR: {(ps.total_matches>0?ps.wins*100f/ps.total_matches:0):F0}%\n";if(ps.ranked_series_wins+ps.ranked_series_losses>0)detail+=$"<color=#FFD94D>Ranked: {ps.ranked_series_wins}W / {ps.ranked_series_losses}L</color>\n";/* Leave % — denominator includes DCs as their own events */if(ps.ranked_dc_count>0||ps.ranked_series_wins+ps.ranked_series_losses>0){int totalRanked=ps.ranked_series_wins+ps.ranked_series_losses+ps.ranked_dc_count;int dc=ps.ranked_dc_count;if(totalRanked>0){float pct=(float)dc/totalRanked*100f;string dcCol=pct<5f?"#44AA44":pct<15f?"#DDAA33":"#FF4444";detail+=$"<color={dcCol}>Leave: {dc}/{totalRanked} ({pct:F0}%)</color>\n";}}/* Hit% / Block% — lifetime counters driven by Harmony patches (Gun.Attack / HealthHandler.TakeDamage / Block.TryBlock / Block.DoBlock). Accumulates only when this player reported a match. Show a dash for players who haven't reported yet so the rows stay consistent with the My Stats Record section (instead of silently disappearing). */{string hitLine=ps.bullets_fired>0?$"<color=#FF9988>Hit:</color> {(float)ps.bullets_hit*100f/ps.bullets_fired:F1}% <color=#888>({ps.bullets_hit}/{ps.bullets_fired})</color>":"<color=#FF9988>Hit:</color> —";string blkLine=ps.blocks_activated>0?$"<color=#99CCFF>Block:</color> {(float)ps.blocks_successful*100f/ps.blocks_activated:F1}% <color=#888>({ps.blocks_successful}/{ps.blocks_activated})</color>":"<color=#99CCFF>Block:</color> —";detail+=$"{hitLine}\n{blkLine}\n";}/* Head to head */var history=ApiClient.CachedMatchHistory;if(history!=null&&selectedSteamId!=MatchTracker.LocalSteamId){int h2hW=0,h2hL=0,h2hCW=0,h2hCL=0,h2hSW=0,h2hSL=0;var seenSeries=new HashSet<string>();foreach(var m in history){if(m.opponent_steam_id==selectedSteamId){if(m.is_ranked){/* Count individual ranked for overall */if(m.won)h2hW++;else h2hL++;/* Count series wins/losses (deduplicate by series_id) */if(!string.IsNullOrEmpty(m.series_id)&&m.series_id!="null"&&!seenSeries.Contains(m.series_id)){string ss=m.series_score;if(!string.IsNullOrEmpty(ss)&&ss.Contains("-")){try{var sp=ss.Split('-');int sw=int.Parse(sp[0]),sl=int.Parse(sp[1]);if(sw>=2||sl>=2){seenSeries.Add(m.series_id);if(sw>sl)h2hSW++;else h2hSL++;}}catch{}}}}else{if(m.won)h2hCW++;else h2hCL++;}}}int h2hAll=h2hW+h2hCW,h2hAllL=h2hL+h2hCL;if(h2hAll+h2hAllL>0){string h2hColor=h2hAll>h2hAllL?"#00FF00":h2hAll<h2hAllL?"#FF6666":"#AAAAAA";detail+=$"\n<b>vs You:</b> <color={h2hColor}>{h2hAll}W - {h2hAllL}L ({h2hAll+h2hAllL} games)</color>\n";if(h2hSW+h2hSL>0)detail+=$"  Ranked Series: {h2hSW}W / {h2hSL}L\n";if(h2hCW+h2hCL>0)detail+=$"  Casual: {h2hCW}W / {h2hCL}L\n";}}/* Top cards with win rates */if(ps.top_card_names!=null&&ps.top_card_names.Count>0){detail+="\n<color=#99AAEE>Top Cards:</color>\n";for(int ci=0;ci<ps.top_card_names.Count&&ci<8;ci++){string picks=ps.top_card_picks.Count>ci?$" ({ps.top_card_picks[ci]}x)":"";float wr=ps.top_card_win_rates!=null&&ps.top_card_win_rates.Count>ci?ps.top_card_win_rates[ci]*100f:0f;string wrCol=wr>=55?"#00FF00":wr<=45?"#FF6666":"#AAAAAA";detail+=$"  {ps.top_card_names[ci]}{picks}  <color={wrCol}>{wr:F0}%</color>\n";}}UIFactory.SetText(txtLBDetail,detail+GetAchievementText());/* Rating line graph — use elo history if available, fall back to form */BuildFormGraph(ps.rating_history,ps.recent_form);/* Block row — always show but hide button for self to prevent layout shift */if(lbBlockRow!=null){lbBlockRow.SetActive(true);bool notSelf=selectedSteamId!=MatchTracker.LocalSteamId;lbBlockBtn.SetActive(notSelf);if(notSelf&&lbBlockTxt!=null){bool blocked=ApiClient.IsPlayerBlocked(selectedSteamId);UIFactory.SetText(lbBlockTxt,blocked?"Unblock from Ranked":"Block from Ranked");UIFactory.SetImageColor(lbBlockBtn,blocked?new Color(0.15f,0.3f,0.15f,0.9f):new Color(0.5f,0.15f,0.15f,0.9f));}}}else{UIFactory.SetText(txtLBPlayerName,"Click a player");UIFactory.SetText(txtLBDetail,"");BuildFormGraph(null,null);if(lbBlockRow!=null)lbBlockRow.SetActive(false);}}

        private static void BuildFormGraph(List<float> ratingHistory, List<string> form)
        {
            if(lbGraphPanel==null)return;
            for(int c=lbGraphPanel.transform.childCount-1;c>=0;c--)
                UnityEngine.Object.Destroy(lbGraphPanel.transform.GetChild(c).gameObject);

            // Determine data source: prefer rating_history (Elo over time), fall back to form (running score)
            bool useElo = ratingHistory != null && ratingHistory.Count >= 2;
            bool useForm = !useElo && form != null && form.Count >= 2;
            if(!useElo && !useForm){lbGraphPanel.SetActive(false);return;}
            lbGraphPanel.SetActive(true);

            // Build data points array
            float[] pts;
            string graphLabel;
            if(useElo)
            {
                pts = ratingHistory.ToArray();
                graphLabel = $"Rating History  ({pts[pts.Length-1]:F0} Elo)";
            }
            else
            {
                // Form → running score line (reversed: oldest left)
                var fList = new List<string>(form);
                fList.Reverse();
                pts = new float[fList.Count];
                int sc = 0;
                int fW=0,fL=0;
                for(int i=0;i<fList.Count;i++){sc+=fList[i]=="W"?1:-1;pts[i]=sc;if(fList[i]=="W")fW++;else fL++;}
                string sumCol=fW>fL?"#00FF00":fW<fL?"#FF6666":"#AAAAAA";
                graphLabel=$"Ranked Form  <color={sumCol}>{fW}W-{fL}L</color>";
            }

            int n = pts.Length;
            float graphH = 80f;
            float padL = 6f, padR = 6f, padT = 18f, padB = 6f;
            float plotW = 310f - padL - padR;
            float plotH = graphH - padT - padB;

            // Background
            var bg=UIFactory.CreatePanel("GBG",lbGraphPanel.transform,new Color(0.08f,0.09f,0.12f,0.8f));
            var bgRT=bg.GetComponent<RectTransform>();bgRT.anchorMin=Vector2.zero;bgRT.anchorMax=Vector2.one;bgRT.offsetMin=Vector2.zero;bgRT.offsetMax=Vector2.zero;

            // Title label (above the plot area, not overlapping)
            var lbl=UIFactory.CreateText("GL",lbGraphPanel.transform,graphLabel,11f,C_DIM,UIFactory.AlignTopLeft,sizeDelta:new Vector2(300,14));
            try{var lGO=(lbl as Component)?.gameObject;if(lGO!=null){var lrt=lGO.GetComponent<RectTransform>();lrt.anchorMin=new Vector2(0,1);lrt.anchorMax=new Vector2(1,1);lrt.pivot=new Vector2(0,1);lrt.anchoredPosition=new Vector2(padL,-1f);lrt.sizeDelta=new Vector2(300,14);
            // Remove LayoutElement so it doesn't affect VLG
            var le=lGO.GetComponent(UIFactory.tLE);if(le!=null)UnityEngine.Object.Destroy(le as UnityEngine.Object);}}catch{}

            // Find Y range
            float minV=pts[0],maxV=pts[0];
            for(int i=1;i<n;i++){if(pts[i]<minV)minV=pts[i];if(pts[i]>maxV)maxV=pts[i];}
            float range=maxV-minV;
            if(range<1f){float mid=(minV+maxV)*0.5f;minV=mid-0.5f;maxV=mid+0.5f;range=1f;}
            // Add 10% padding to Y range
            float yPad=range*0.1f;minV-=yPad;maxV+=yPad;range=maxV-minV;

            // Y-axis labels
            string maxLabel=useElo?$"{maxV:F0}":$"+{maxV:F0}";
            string minLabel=useElo?$"{minV:F0}":$"{minV:F0}";
            var topLbl=UIFactory.CreateText("YMax",lbGraphPanel.transform,maxLabel,9f,new Color(0.5f,0.7f,0.5f,0.7f),UIFactory.AlignTopRight,sizeDelta:new Vector2(40,10));
            try{var tGO=(topLbl as Component)?.gameObject;if(tGO!=null){var trt=tGO.GetComponent<RectTransform>();trt.anchorMin=new Vector2(1,1);trt.anchorMax=new Vector2(1,1);trt.pivot=new Vector2(1,1);trt.anchoredPosition=new Vector2(-2f,-padT+2f);
            var le=tGO.GetComponent(UIFactory.tLE);if(le!=null)UnityEngine.Object.Destroy(le as UnityEngine.Object);}}catch{}
            var botLbl=UIFactory.CreateText("YMin",lbGraphPanel.transform,minLabel,9f,new Color(0.7f,0.5f,0.5f,0.7f),UIFactory.AlignMidRight,sizeDelta:new Vector2(40,10));
            try{var bGO=(botLbl as Component)?.gameObject;if(bGO!=null){var brt=bGO.GetComponent<RectTransform>();brt.anchorMin=new Vector2(1,0);brt.anchorMax=new Vector2(1,0);brt.pivot=new Vector2(1,0);brt.anchoredPosition=new Vector2(-2f,padB-2f);
            var le=bGO.GetComponent(UIFactory.tLE);if(le!=null)UnityEngine.Object.Destroy(le as UnityEngine.Object);}}catch{}

            // Draw line segments connecting data points
            Color lineCol = useElo ? new Color(0.3f,0.7f,1f,0.9f) : new Color(0.5f,0.85f,0.5f,0.9f);
            Color dotCol = useElo ? new Color(0.4f,0.8f,1f,1f) : new Color(0.6f,1f,0.6f,1f);
            float lineThick = 2f;

            for(int i=0;i<n-1;i++)
            {
                float x1 = padL + (n>1 ? (float)i/(n-1)*plotW : 0);
                float y1 = padB + (pts[i]-minV)/range*plotH;
                float x2 = padL + (float)(i+1)/(n-1)*plotW;
                float y2 = padB + (pts[i+1]-minV)/range*plotH;

                // Line segment as a rotated thin rect
                float dx=x2-x1, dy=y2-y1;
                float len=Mathf.Sqrt(dx*dx+dy*dy);
                float angle=Mathf.Atan2(dy,dx)*Mathf.Rad2Deg;

                var seg=new GameObject($"L{i}");seg.transform.SetParent(lbGraphPanel.transform,false);
                var srt=seg.AddComponent<RectTransform>();
                srt.anchorMin=Vector2.zero;srt.anchorMax=Vector2.zero;
                srt.pivot=new Vector2(0f,0.5f);
                srt.anchoredPosition=new Vector2(x1,y1);
                srt.sizeDelta=new Vector2(len,lineThick);
                srt.localRotation=Quaternion.Euler(0,0,angle);
                var simg=seg.AddComponent(UIFactory.tImage);
                UIFactory.tImage.GetProperty("color",BindingFlags.Public|BindingFlags.Instance)?.SetValue(simg,lineCol);
            }

            // Draw dots at each data point
            float dotSize = n > 15 ? 3f : 4f;
            for(int i=0;i<n;i++)
            {
                float x = padL + (n>1 ? (float)i/(n-1)*plotW : 0);
                float y = padB + (pts[i]-minV)/range*plotH;
                var dot=new GameObject($"D{i}");dot.transform.SetParent(lbGraphPanel.transform,false);
                var drt=dot.AddComponent<RectTransform>();
                drt.anchorMin=Vector2.zero;drt.anchorMax=Vector2.zero;
                drt.pivot=new Vector2(0.5f,0.5f);
                drt.anchoredPosition=new Vector2(x,y);
                drt.sizeDelta=new Vector2(dotSize,dotSize);
                var dimg=dot.AddComponent(UIFactory.tImage);
                UIFactory.tImage.GetProperty("color",BindingFlags.Public|BindingFlags.Instance)?.SetValue(dimg,dotCol);
            }

            // Current value label at the end
            float lastX = padL + plotW + 2f;
            float lastY = padB + (pts[n-1]-minV)/range*plotH;
            string valTxt = useElo ? $"{pts[n-1]:F0}" : $"{(pts[n-1]>0?"+":"")}{pts[n-1]:F0}";
            string valCol = useElo ? "#66CCFF" : (pts[n-1]>0?"#00FF00":pts[n-1]<0?"#FF6666":"#AAAAAA");
            // (skip end label if it would overlap Y-axis labels)
        }

        private static string GetAchievementText()
        {
            var ach=ApiClient.SelectedPlayerAchievements;
            if(ach==null)return "";
            int unlocked=0;
            string achText="\n<color=#99AAEE>Achievements:</color>\n";
            foreach(var kvp in ApiClient.AchievementDefs)
            {
                bool got=ach.ContainsKey(kvp.Key)&&ach[kvp.Key].unlocked;
                if(got)unlocked++;
                string icon=got?"<color=#FFD94D>[X]</color>":"<color=#444444>[ ]</color>";
                string nameCol=got?"#FFFFFF":"#666666";
                achText+=$"  {icon} <color={nameCol}>{kvp.Value[0]}</color>\n";
            }
            achText+=$"\n  {unlocked} / {ApiClient.AchievementDefs.Count} unlocked";
            return achText;
        }

        private static void RefreshCardStats(){string[]hL={"Card","Rarity","Picks","Wins","WR%","Pass%"};string[]hK={"card_name","card_rarity","times_picked","wins_with_card","win_rate","pass_rate"};if(cardSortTexts!=null)for(int i=0;i<6&&i<cardSortTexts.Length;i++){if(cardSortTexts[i]==null)continue;string arrow=cardSort==hK[i]?(cardSortDesc?" v":" ^"):"";UIFactory.SetText(cardSortTexts[i],hL[i]+arrow);UIFactory.SetColor(cardSortTexts[i],cardSort==hK[i]?C_WHITE:C_LABEL);if(cardSortBtns!=null&&i<cardSortBtns.Length)UIFactory.SetImageColor(cardSortBtns[i],cardSort==hK[i]?C_TABACT:C_TAB);}var cards=ApiClient.CachedCardStats;foreach(var r in cardRows)r.root.SetActive(false);if(cards==null||cards.Count==0)return;var merged=new List<ApiClient.CardStatData>();var seen=new Dictionary<string,int>(StringComparer.OrdinalIgnoreCase);foreach(var c in cards){string key=(c.card_name??"?").ToLower().Replace(" ","");if(seen.ContainsKey(key)){var e=merged[seen[key]];e.times_picked+=c.times_picked;e.wins_with_card+=c.wins_with_card;e.win_rate=e.times_picked>0?(float)e.wins_with_card/e.times_picked:0;e.times_offered=Math.Max(e.times_offered,c.times_offered);if(c.times_offered>0)e.pass_rate=c.pass_rate;if((e.card_rarity==null||e.card_rarity=="Unknown")&&c.card_rarity!=null&&c.card_rarity!="Unknown")e.card_rarity=c.card_rarity;}else{seen[key]=merged.Count;merged.Add(new ApiClient.CardStatData{card_name=c.card_name,card_rarity=c.card_rarity,times_picked=c.times_picked,wins_with_card=c.wins_with_card,win_rate=c.win_rate,times_offered=c.times_offered,pass_rate=c.pass_rate});}}switch(cardSort){case "card_name":merged.Sort((a,b)=>cardSortDesc?string.Compare(b.card_name,a.card_name,StringComparison.OrdinalIgnoreCase):string.Compare(a.card_name,b.card_name,StringComparison.OrdinalIgnoreCase));break;case "card_rarity":merged.Sort((a,b)=>cardSortDesc?string.Compare(b.card_rarity,a.card_rarity,StringComparison.OrdinalIgnoreCase):string.Compare(a.card_rarity,b.card_rarity,StringComparison.OrdinalIgnoreCase));break;case "times_picked":merged.Sort((a,b)=>cardSortDesc?b.times_picked.CompareTo(a.times_picked):a.times_picked.CompareTo(b.times_picked));break;case "wins_with_card":merged.Sort((a,b)=>cardSortDesc?b.wins_with_card.CompareTo(a.wins_with_card):a.wins_with_card.CompareTo(b.wins_with_card));break;case "win_rate":merged.Sort((a,b)=>cardSortDesc?b.win_rate.CompareTo(a.win_rate):a.win_rate.CompareTo(b.win_rate));break;case "pass_rate":merged.Sort((a,b)=>cardSortDesc?b.pass_rate.CompareTo(a.pass_rate):a.pass_rate.CompareTo(b.pass_rate));break;default:merged.Sort((a,b)=>cardSortDesc?b.times_picked.CompareTo(a.times_picked):a.times_picked.CompareTo(b.times_picked));break;}for(int i=0;i<merged.Count&&i<cardRows.Count;i++){var c=merged[i];var row=cardRows[i];float wr=c.win_rate*100;Color wrColor=wr>=55?C_GREEN:wr<=45?C_RED:C_WHITE;UIFactory.SetText(row.txtName,c.card_name??"?");string rarity=c.card_rarity??"Unknown";UIFactory.SetText(row.txtRarity,rarity);UIFactory.SetColor(row.txtRarity,GetRarityColor(rarity));UIFactory.SetText(row.txtPicks,$"{c.times_picked}");UIFactory.SetText(row.txtWins,$"{c.wins_with_card}");UIFactory.SetText(row.txtWR,$"{wr:F0}%");UIFactory.SetColor(row.txtWR,wrColor);if(c.times_offered>0){float pr=c.pass_rate*100;UIFactory.SetText(row.txtPass,$"{pr:F0}%");UIFactory.SetColor(row.txtPass,pr>=70?C_RED:pr<=30?C_GREEN:C_LABEL);}else{UIFactory.SetText(row.txtPass,"—");UIFactory.SetColor(row.txtPass,C_DIM);}row.root.SetActive(true);}}
        private static Color GetRarityColor(string r){if(string.IsNullOrEmpty(r))return C_LABEL;switch(r.ToLower()){case "common":return C_COMMON;case "uncommon":return C_UNCOMMON;case "rare":return C_RARE;default:return C_LABEL;}}

        // ── Chat ──────────────────────────────────────────────────
        /// <summary>Called from the background ChatClient thread. Appends a formatted
        /// line to the log with thread-safety.</summary>
        public static void OnChatMessage(string json)
        {
            try
            {
                string source = ExtractChatField(json, "source");
                string name = ExtractChatField(json, "display_name");
                string message = ExtractChatField(json, "message");
                int rating = ExtractChatIntField(json, "rating");
                string title = ExtractChatField(json, "title");
                string titleColor = ExtractChatField(json, "title_color");
                if (string.IsNullOrEmpty(message)) return;
                // Local mute filter. Hides messages from any name in MutedChatNames.
                // Case-insensitive comparison so /mute Sid matches "sid" too.
                if (IsMuted(name))
                {
                    Plugin.Log.LogInfo($"[CHAT] muted msg from {name} dropped locally");
                    return;
                }
                // Bound any single message so a giant paste can't overflow the scroll content
                // and trap the scroll position past TMP's reachable bottom.
                if (message.Length > CHAT_LINE_MAX_CHARS)
                    message = message.Substring(0, CHAT_LINE_MAX_CHARS - 3) + "...";
                string prefix = source == "discord" ? "<color=#A0B4FF>[D]</color>" : "<color=#B0FFB0>[game]</color>";
                string ratingTag = rating > 0 ? $" <color=#CCCCCC>({rating})</color>" : "";
                string titleTag = "";
                if (!string.IsNullOrEmpty(title))
                {
                    string col = string.IsNullOrEmpty(titleColor) ? "#CCCCCC" : titleColor;
                    titleTag = $" <color={col}>[{Escape(title)}]</color>";
                }
                string line = $"{prefix} <b>{Escape(name)}</b>{titleTag}{ratingTag}: {Escape(message)}";
                lock (chatLinesLock)
                {
                    chatLines.Add(new ChatEntry { Line = line, AddedUtc = DateTime.UtcNow });
                    while (chatLines.Count > CHAT_LOG_MAX) chatLines.RemoveAt(0);
                }
                MarkDirty();
            }
            catch { }
        }

        // ── Local chat mute (per-display-name) ─────────────────
        // Stored as a pipe-delimited list in Plugin.MutedChatNames (BepInEx config).
        // Command syntax: "/mute name", "/unmute name", "/muted".
        // Filter applied in OnChatMessage; commands handled in CompetitiveUI's chat input submit.

        private static HashSet<string> _mutedCache;

        private static HashSet<string> GetMutedSet()
        {
            // Rebuild on each access — config writes are infrequent and the list is small.
            string raw = Plugin.MutedChatNames?.Value ?? "";
            var set = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            foreach (var part in raw.Split('|'))
            {
                var t = (part ?? "").Trim();
                if (!string.IsNullOrEmpty(t)) set.Add(t);
            }
            _mutedCache = set;
            return set;
        }

        private static bool IsMuted(string name)
        {
            if (string.IsNullOrEmpty(name)) return false;
            var s = _mutedCache ?? GetMutedSet();
            return s.Contains(name);
        }

        private static void SaveMutedSet(HashSet<string> set)
        {
            if (Plugin.MutedChatNames == null) return;
            Plugin.MutedChatNames.Value = string.Join("|", set);
            _mutedCache = set;
        }

        public static void HandleMuteCommand(string text)
        {
            try
            {
                if (text.Equals("/muted", StringComparison.OrdinalIgnoreCase))
                {
                    var s = GetMutedSet();
                    string list = s.Count == 0 ? "(none)" : string.Join(", ", s);
                    AppendSystemChatLine($"Muted: {list}");
                    return;
                }
                int sp = text.IndexOf(' ');
                if (sp < 0) return;
                string cmd = text.Substring(0, sp).ToLowerInvariant();
                string target = text.Substring(sp + 1).Trim();
                if (string.IsNullOrEmpty(target)) return;
                var set = GetMutedSet();
                if (cmd == "/mute")
                {
                    if (set.Add(target)) { SaveMutedSet(set); AppendSystemChatLine($"Muted <b>{Escape(target)}</b>"); }
                    else AppendSystemChatLine($"<b>{Escape(target)}</b> is already muted");
                }
                else if (cmd == "/unmute")
                {
                    if (set.Remove(target)) { SaveMutedSet(set); AppendSystemChatLine($"Unmuted <b>{Escape(target)}</b>"); }
                    else AppendSystemChatLine($"<b>{Escape(target)}</b> isn't muted");
                }
            }
            catch (Exception ex) { Plugin.Log.LogWarning($"[MUTE] {ex.Message}"); }
        }

        // Adds a local-only system line to the chat log (gold-tinted, no broadcast).
        private static void AppendSystemChatLine(string body)
        {
            string line = $"<color=#FFD94D>[system]</color> {body}";
            lock (chatLinesLock)
            {
                chatLines.Add(new ChatEntry { Line = line, AddedUtc = DateTime.UtcNow });
                while (chatLines.Count > CHAT_LOG_MAX) chatLines.RemoveAt(0);
            }
            MarkDirty();
        }

        private static void RefreshChatLog()
        {
            if (txtChatLog == null) return;
            string text;
            lock (chatLinesLock)
            {
                if (chatLines.Count == 0) return;  // keep the placeholder from BuildMyStatsTab
                var sb = new System.Text.StringBuilder();
                for (int i = 0; i < chatLines.Count; i++)
                {
                    if (i > 0) sb.Append('\n');
                    sb.Append(chatLines[i].Line);
                }
                text = sb.ToString();
            }
            UIFactory.SetText(txtChatLog, text);
            // Pin to the bottom so the newest message is visible. Defer one frame so the
            // ContentSizeFitter has actually recomputed against the new TMP-reported height.
            Plugin.Instance?.StartCoroutine(ScrollChatToBottomNextFrame());
        }

        private static System.Collections.IEnumerator ScrollChatToBottomNextFrame()
        {
            yield return null;
            if (chatScrollRect == null) yield break;
            try
            {
                // ScrollRect.verticalNormalizedPosition: 0 = bottom, 1 = top.
                var p = UIFactory.tScrollRect.GetProperty("verticalNormalizedPosition", BindingFlags.Public | BindingFlags.Instance);
                p?.SetValue(chatScrollRect, 0f);
            }
            catch { }
        }

        private static string Escape(string s)
        {
            if (string.IsNullOrEmpty(s)) return "";
            // Strip TMP rich-text payloads that could break our own coloring or impersonate system lines.
            return s.Replace("<", "〈").Replace(">", "〉");
        }

        /// <summary>Numeric field parser — tolerates nulls, whitespace, integers and floats.</summary>
        private static int ExtractChatIntField(string json, string key)
        {
            if (string.IsNullOrEmpty(json)) return 0;
            string needle = "\"" + key + "\"";
            int idx = json.IndexOf(needle);
            if (idx < 0) return 0;
            int p = idx + needle.Length;
            while (p < json.Length && (json[p] == ' ' || json[p] == '\t')) p++;
            if (p >= json.Length || json[p] != ':') return 0;
            p++;
            while (p < json.Length && (json[p] == ' ' || json[p] == '\t')) p++;
            int end = p;
            while (end < json.Length && (char.IsDigit(json[end]) || json[end] == '-' || json[end] == '.')) end++;
            if (end == p) return 0;
            try
            {
                float f = float.Parse(json.Substring(p, end - p), System.Globalization.CultureInfo.InvariantCulture);
                return (int)Math.Round(f);
            }
            catch { return 0; }
        }

        private static string ExtractChatField(string json, string key)
        {
            // Tolerates any JSON formatting: "key":"val", "key": "val", "key":  "val".
            if (string.IsNullOrEmpty(json)) return "";
            string needle = "\"" + key + "\"";
            int idx = json.IndexOf(needle);
            if (idx < 0) return "";
            int p = idx + needle.Length;
            while (p < json.Length && (json[p] == ' ' || json[p] == '\t')) p++;
            if (p >= json.Length || json[p] != ':') return "";
            p++;
            while (p < json.Length && (json[p] == ' ' || json[p] == '\t')) p++;
            if (p >= json.Length || json[p] != '"') return "";
            p++;
            var sb = new System.Text.StringBuilder();
            while (p < json.Length)
            {
                char c = json[p];
                if (c == '\\' && p + 1 < json.Length)
                {
                    char n = json[p + 1];
                    if (n == 'n') sb.Append('\n');
                    else if (n == 't') sb.Append('\t');
                    else sb.Append(n);
                    p += 2;
                }
                else if (c == '"') break;
                else { sb.Append(c); p++; }
            }
            return sb.ToString();
        }

        private static void RefreshQueueUI(){if(txtRankedStatus==null)return;bool ranked=Plugin.RankedEnabled.Value;var qs=ApiClient.CurrentQueueState;UIFactory.SetText(txtRankedStatus,ranked?"RANKED: ON":"RANKED: OFF");UIFactory.SetColor(txtRankedStatus,ranked?C_GREEN:Color.gray);rankOnBtn.SetActive(!ranked);rankOffBtn.SetActive(ranked&&!inGameMode);bool inRankedMatch=GameStateWatcher.IsInMatch&&GameStateWatcher.MatchIsRanked;qSearchBtn.SetActive(ranked&&qs==ApiClient.QueueState.Idle&&!inRankedMatch);qCancelBtn.SetActive(ranked&&qs==ApiClient.QueueState.Searching);if(qs==ApiClient.QueueState.Searching){var poll=ApiClient.LastPollData;string line="Searching...";if(poll!=null&&poll.status=="searching"){int m=poll.wait_time/60,sec=poll.wait_time%60;line=$"Searching... {(m>0?$"{m}m ":"")}{sec}s  ±{poll.elo_range}"+(poll.queue_size>1?$"  ({poll.queue_size} in queue)":"");}UIFactory.SetText(txtQueueInfo,line);UIFactory.SetColor(txtQueueInfo,C_BLUE);((txtQueueInfo as Component)?.gameObject)?.SetActive(true);}else if(qs==ApiClient.QueueState.Idle&&ranked){int qc=ApiClient.CachedQueueSearching;if(qc>0){UIFactory.SetText(txtQueueInfo,$"{qc} searching");UIFactory.SetColor(txtQueueInfo,C_GREEN);}else{UIFactory.SetText(txtQueueInfo,"0 in queue");UIFactory.SetColor(txtQueueInfo,C_DIM);}((txtQueueInfo as Component)?.gameObject)?.SetActive(true);}else{UIFactory.SetText(txtQueueInfo,"");((txtQueueInfo as Component)?.gameObject)?.SetActive(false);}if(qs==ApiClient.QueueState.Matched||qs==ApiClient.QueueState.ReadySent){qMatchPanel.SetActive(true);var poll=ApiClient.LastPollData;if(poll!=null){string oppInfo=$"MATCH FOUND!  vs {poll.opponent_name} ({poll.opponent_rating:F0})";if(qs==ApiClient.QueueState.ReadySent&&poll.opponent_ready)oppInfo+="  [Opponent Ready]";UIFactory.SetText(txtMatchFound,oppInfo);}bool readySent=qs==ApiClient.QueueState.ReadySent;readyBtn.SetActive(!readySent);connectLabel.SetActive(readySent);if(readySent&&txtConnectLabel!=null&&poll!=null){string waitTxt=!string.IsNullOrEmpty(poll.opponent_name)?$"Waiting for {poll.opponent_name} ({poll.opponent_rating:F0})...":"Waiting for opponent...";if(poll.opponent_ready)waitTxt=$"{poll.opponent_name} ready! Joining...";UIFactory.SetText(txtConnectLabel,waitTxt);}declineBtn.SetActive(true);}else qMatchPanel.SetActive(false);}

        private static int CalcStreak(List<ApiClient.MatchHistoryEntry> m){if(m==null||m.Count==0)return 0;bool t=m[0].won;int c=0;for(int i=0;i<m.Count;i++){if(m[i].won==t)c++;else break;}return t?c:-c;}
        private static string Trunc(string s,int max){if(string.IsNullOrEmpty(s))return "";return s.Length<=max?s:s.Substring(0,max-2)+"..";}
        private struct SGroup{public string series_id;public List<ApiClient.MatchHistoryEntry> matches;}
        private static List<SGroup> GroupBySeries(List<ApiClient.MatchHistoryEntry> ranked){var groups=new List<SGroup>();SGroup cur=new SGroup{series_id=null,matches=null};foreach(var m in ranked){string sid=m.series_id;bool has=!string.IsNullOrEmpty(sid)&&sid!="null";if(has&&cur.matches!=null&&cur.series_id==sid)cur.matches.Add(m);else{if(cur.matches!=null&&cur.matches.Count>0)groups.Add(cur);cur=new SGroup{series_id=has?sid:null,matches=new List<ApiClient.MatchHistoryEntry>{m}};}}if(cur.matches!=null&&cur.matches.Count>0)groups.Add(cur);return groups;}
        internal static Type TImage=>UIFactory.tImage;internal static Type TButton=>UIFactory.tButton;

        // ── Admin tab ──────────────────────────────────────────
        // Visible only when ApiClient.IsAdmin == true (gated in BuildTabBar / RefreshCurrentTab).
        // Shows: flagged matches with [Confirm Cheat]/[False Positive] buttons; banned users with
        // [Unban] button; three buttons opening an IMGUI prompt for Ban / Grant Achievement / Reverse Series.
        private static GameObject adminFlagsContainer;
        private static GameObject adminBansContainer;
        private static object txtAdminFlagsHdr, txtAdminBansHdr;
        private static List<GameObject> adminFlagRowPool = new List<GameObject>();
        private static List<GameObject> adminBanRowPool = new List<GameObject>();

        private static GameObject BuildAdminTab(Transform parent)
        {
            var panel = new GameObject("AdminPanel");
            panel.transform.SetParent(parent, false);
            panel.AddComponent<RectTransform>();
            UIFactory.AddVLG(panel, spacing: 6, padL: 8, padR: 8, padT: 6, padB: 6);
            UIFactory.AddLE(panel, flexH: 1);

            var hdrRow = new GameObject("AHdr"); hdrRow.transform.SetParent(panel.transform, false); hdrRow.AddComponent<RectTransform>();
            UIFactory.AddHLG(hdrRow, spacing: 8); UIFactory.AddLE(hdrRow, prefH: 32, flexH: 0);
            UIFactory.CreateText("AT", hdrRow.transform, "<b>Admin Panel</b>  <color=#888>(visible only to whitelisted Steam IDs)</color>", 18f, new Color(1f, 0.7f, 0.3f), UIFactory.AlignMidLeft, sizeDelta: new Vector2(600, 28));
            UIFactory.CreateButton("ARefresh", hdrRow.transform, "Refresh", 13f, C_WHITE, C_BTN, () =>
            {
                var sid = MatchTracker.LocalSteamId;
                if (!string.IsNullOrEmpty(sid)) { ApiClient.FetchFlaggedMatches(sid); ApiClient.FetchBannedUsers(sid); }
            }, sizeDelta: new Vector2(90, 26));

            var actionRow = new GameObject("AAct"); actionRow.transform.SetParent(panel.transform, false); actionRow.AddComponent<RectTransform>();
            UIFactory.AddHLG(actionRow, spacing: 8); UIFactory.AddLE(actionRow, prefH: 30, flexH: 0);
            UIFactory.CreateButton("ABan", actionRow.transform, "Ban Steam ID...", 13f, C_WHITE, new Color(0.55f, 0.15f, 0.15f, 0.9f), () =>
                CompetitiveUI.OpenAdminPrompt("ban"), sizeDelta: new Vector2(140, 26));
            UIFactory.CreateButton("AGrant", actionRow.transform, "Grant Achievement...", 13f, C_WHITE, new Color(0.2f, 0.45f, 0.2f, 0.9f), () =>
                CompetitiveUI.OpenAdminPrompt("grant"), sizeDelta: new Vector2(170, 26));
            UIFactory.CreateButton("ARev", actionRow.transform, "Reverse Series...", 13f, C_WHITE, new Color(0.45f, 0.3f, 0.55f, 0.9f), () =>
                CompetitiveUI.OpenAdminPrompt("reverse"), sizeDelta: new Vector2(150, 26));

            var split = new GameObject("ASplit"); split.transform.SetParent(panel.transform, false); split.AddComponent<RectTransform>();
            UIFactory.AddHLG(split, spacing: 8); UIFactory.AddLE(split, flexH: 1);

            // Left column: flagged matches.
            var leftCol = new GameObject("AFLeft"); leftCol.transform.SetParent(split.transform, false); leftCol.AddComponent<RectTransform>();
            UIFactory.AddVLG(leftCol, spacing: 4); UIFactory.AddLE(leftCol, flexW: 1, flexH: 1);
            txtAdminFlagsHdr = UIFactory.CreateText("AFH", leftCol.transform, "Flagged Matches", 16f, new Color(1f, 0.55f, 0.3f), sizeDelta: new Vector2(500, 24));
            UIFactory.SetBold(txtAdminFlagsHdr, true);
            var flagSV = UIFactory.CreateScrollView("AFSV", leftCol.transform, spacing: 2);
            UIFactory.AddLE(flagSV.scrollGO, flexH: 1);
            adminFlagsContainer = flagSV.content;

            // Right column: banned users.
            var rightCol = new GameObject("AFRight"); rightCol.transform.SetParent(split.transform, false); rightCol.AddComponent<RectTransform>();
            UIFactory.AddVLG(rightCol, spacing: 4); UIFactory.AddLE(rightCol, prefW: 360, flexH: 1);
            txtAdminBansHdr = UIFactory.CreateText("ABH", rightCol.transform, "Banned Users", 16f, new Color(1f, 0.45f, 0.45f), sizeDelta: new Vector2(340, 24));
            UIFactory.SetBold(txtAdminBansHdr, true);
            var banSV = UIFactory.CreateScrollView("ABSV", rightCol.transform, spacing: 2);
            UIFactory.AddLE(banSV.scrollGO, flexH: 1);
            adminBansContainer = banSV.content;

            return panel;
        }

        private static void RefreshAdmin()
        {
            // Flag rows
            var flags = ApiClient.CachedFlaggedMatches ?? new List<ApiClient.FlaggedMatchEntry>();
            UIFactory.SetText(txtAdminFlagsHdr, $"Flagged Matches ({flags.Count} unreviewed)");
            // Hide pooled rows past current count
            for (int i = flags.Count; i < adminFlagRowPool.Count; i++) adminFlagRowPool[i].SetActive(false);
            for (int i = 0; i < flags.Count; i++)
            {
                if (i >= adminFlagRowPool.Count) adminFlagRowPool.Add(BuildAdminFlagRow(adminFlagsContainer.transform, i));
                FillAdminFlagRow(adminFlagRowPool[i], flags[i]);
            }

            // Ban rows
            var bans = ApiClient.CachedBannedUsers ?? new List<ApiClient.BannedUserEntry>();
            UIFactory.SetText(txtAdminBansHdr, $"Banned Users ({bans.Count})");
            for (int i = bans.Count; i < adminBanRowPool.Count; i++) adminBanRowPool[i].SetActive(false);
            for (int i = 0; i < bans.Count; i++)
            {
                if (i >= adminBanRowPool.Count) adminBanRowPool.Add(BuildAdminBanRow(adminBansContainer.transform, i));
                FillAdminBanRow(adminBanRowPool[i], bans[i]);
            }
        }

        private static GameObject BuildAdminFlagRow(Transform parent, int idx)
        {
            var row = UIFactory.CreatePanel($"AF{idx}", parent, new Color(0.18f, 0.13f, 0.13f, 0.85f));
            UIFactory.AddHLG(row, spacing: 6, padL: 6, padR: 6, padT: 4, padB: 4);
            UIFactory.AddLE(row, prefH: 38, flexH: 0);
            var txt = UIFactory.CreateText("AFT", row.transform, "", 13f, C_WHITE, UIFactory.AlignMidLeft, sizeDelta: new Vector2(420, 30));
            UIFactory.SetWordWrap(txt, false);
            row.transform.GetChild(0).gameObject.AddComponent<RectTransform>(); // ensure
            // The two action buttons; their onClick is rebuilt per-row in FillAdminFlagRow.
            var btnConfirm = UIFactory.CreateButton($"AFOK{idx}", row.transform, "Cheat", 11f, C_WHITE, new Color(0.5f, 0.15f, 0.15f, 0.9f), () => { }, sizeDelta: new Vector2(70, 26));
            var btnFalse   = UIFactory.CreateButton($"AFNO{idx}", row.transform, "False+", 11f, C_WHITE, new Color(0.15f, 0.4f, 0.15f, 0.9f), () => { }, sizeDelta: new Vector2(70, 26));
            row.SetActive(false);
            return row;
        }

        private static void FillAdminFlagRow(GameObject row, ApiClient.FlaggedMatchEntry e)
        {
            row.SetActive(true);
            // First child = text. The button onClicks are set below.
            var txt = row.transform.Find("AFT");
            if (txt != null)
            {
                string when = "";
                try { if (!string.IsNullOrEmpty(e.created_at)) when = DateTime.Parse(e.created_at).ToString("HH:mm"); } catch { }
                string verdict = e.auto_invalidated ? "<color=#FF6666>auto-inv</color>" : "<color=#DDAA44>advisory</color>";
                string mode = e.is_ranked ? "R" : "C";
                string line = $"[{when}] <b>{e.flag_reason}</b> {verdict}  {Trunc(e.p1_name, 12)} vs {Trunc(e.p2_name, 12)}  {mode}/{e.duration_seconds}s";
                // tTMP isn't accessible outside UIFactory. Iterate child components by reflected name.
                foreach (var c in txt.GetComponents<Component>())
                    if (c.GetType().Name == "TextMeshProUGUI") { UIFactory.SetText(c, line); break; }
            }
            // Rebuild button click handlers — capture this entry's id.
            var ok = row.transform.Find("AFOK" + row.name.Substring(2));
            var no = row.transform.Find("AFNO" + row.name.Substring(2));
            if (ok != null) WireButton(ok.gameObject, () => SubmitFlagReview(e.id, "confirmed_cheat"));
            if (no != null) WireButton(no.gameObject, () => SubmitFlagReview(e.id, "false_positive"));
        }

        private static void SubmitFlagReview(string flagId, string action)
        {
            var sid = MatchTracker.LocalSteamId;
            if (string.IsNullOrEmpty(sid)) return;
            ApiClient.AdminReviewFlag(sid, flagId, action, (ok, resp) =>
            {
                Plugin.Log.LogInfo($"[ADMIN] review {action} on {flagId}: {(ok?"OK":"FAIL")} {resp}");
                if (ok) ApiClient.FetchFlaggedMatches(sid);
            });
        }

        private static GameObject BuildAdminBanRow(Transform parent, int idx)
        {
            var row = UIFactory.CreatePanel($"AB{idx}", parent, new Color(0.2f, 0.13f, 0.13f, 0.85f));
            UIFactory.AddHLG(row, spacing: 6, padL: 6, padR: 6, padT: 4, padB: 4);
            UIFactory.AddLE(row, prefH: 32, flexH: 0);
            UIFactory.CreateText("ABT", row.transform, "", 13f, C_WHITE, UIFactory.AlignMidLeft, sizeDelta: new Vector2(220, 26));
            UIFactory.CreateButton($"ABU{idx}", row.transform, "Unban", 11f, C_WHITE, new Color(0.2f, 0.45f, 0.2f, 0.9f), () => { }, sizeDelta: new Vector2(70, 24));
            row.SetActive(false);
            return row;
        }

        private static void FillAdminBanRow(GameObject row, ApiClient.BannedUserEntry e)
        {
            row.SetActive(true);
            var txt = row.transform.Find("ABT");
            if (txt != null)
            {
                string line = $"<b>{Trunc(e.display_name ?? e.steam_id, 16)}</b>  <color=#999>{Trunc(e.reason, 28)}</color>";
                foreach (var c in txt.GetComponents<Component>()) if (c.GetType().Name == "TextMeshProUGUI") { UIFactory.SetText(c, line); break; }
            }
            var unbanBtn = row.transform.Find("ABU" + row.name.Substring(2));
            if (unbanBtn != null) WireButton(unbanBtn.gameObject, () =>
            {
                var sid = MatchTracker.LocalSteamId;
                if (string.IsNullOrEmpty(sid)) return;
                ApiClient.AdminUnban(sid, e.steam_id, (ok, resp) =>
                {
                    Plugin.Log.LogInfo($"[ADMIN] unban {e.steam_id}: {(ok?"OK":"FAIL")} {resp}");
                    if (ok) { ApiClient.FetchBannedUsers(sid); ApiClient.FetchFlaggedMatches(sid); }
                });
            });
        }

        // Replace a Button's onClick listeners — clears via Button.onClick.RemoveAllListeners then re-adds.
        // Avoids stacking handlers when we re-fill a pooled row with a new entry.
        private static void WireButton(GameObject btn, Action onClick)
        {
            try
            {
                var btnComp = btn.GetComponent(UIFactory.tButton);
                if (btnComp == null) return;
                var onClickProp = UIFactory.tButton.GetProperty("onClick", BindingFlags.Public | BindingFlags.Instance);
                var ev = onClickProp?.GetValue(btnComp);
                if (ev != null)
                {
                    var removeAll = ev.GetType().GetMethod("RemoveAllListeners");
                    removeAll?.Invoke(ev, null);
                    var add = ev.GetType().GetMethod("AddListener");
                    if (add != null)
                    {
                        UnityEngine.Events.UnityAction guarded = () => { if (ClickGuard.Claim()) onClick(); };
                        add.Invoke(ev, new object[] { guarded });
                    }
                }
                // Also rewire the secondary ClickHandler attached by CreateButton.
                var ch = btn.GetComponent<ClickHandler>();
                if (ch != null) ch.onClick = () => { if (ClickGuard.Claim()) onClick(); };
            }
            catch (Exception ex) { Plugin.Log.LogWarning($"[ADMIN] WireButton failed: {ex.Message}"); }
        }
    }
}
