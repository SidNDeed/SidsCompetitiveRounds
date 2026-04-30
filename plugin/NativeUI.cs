using System;
using System.Collections;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using System.Text;
using Photon.Pun;
using UnityEngine;

namespace CompetitiveRounds
{
    // Frame-based debounce - prevents ClickHandler + standard Button from both firing
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

        // Wraps text in <b>...</b> when richText is on. Belt-and-suspenders with
        // the fontStyle=Bold call below: on some TMP builds fontStyle=Bold silently
        // no-ops if the SDF atlas lacks a bold variant, and the rich-text wrapper
        // is the only reliable way to force bold rendering. Skip if the text is
        // already fully-wrapped to avoid <b><b>...</b></b> in re-used calls.
        private static string _BoldWrap(string s)
        {
            if (string.IsNullOrEmpty(s)) return s;
            if (s.StartsWith("<b>") && s.EndsWith("</b>")) return s;
            return $"<b>{s}</b>";
        }

        public static object CreateText(string name,Transform parent,string text,float fontSize,Color color,int alignment=AlignTopLeft,Vector2? sizeDelta=null,bool richText=true,bool raycastTarget=false)
        {var go=new GameObject(name);go.transform.SetParent(parent,false);var rt=go.AddComponent<RectTransform>();Vector2 sz=sizeDelta??new Vector2(200,24);rt.sizeDelta=sz;if(sz.x>0&&sz.y>0)AddLE(go,prefW:sz.x,prefH:sz.y);var tmp=go.AddComponent(tTMP);pTmpText?.SetValue(tmp,richText?_BoldWrap(text):text);pTmpFontSize?.SetValue(tmp,fontSize);pTmpColor?.SetValue(tmp,color);pTmpRichText?.SetValue(tmp,richText);pTmpRaycastTarget?.SetValue(tmp,raycastTarget);if(tmpFont!=null)pTmpFont?.SetValue(tmp,tmpFont);pTmpCharSpacing?.SetValue(tmp,1.0f);try{pTmpFontStyle?.SetValue(tmp,Enum.ToObject(pTmpFontStyle.PropertyType,1));}catch{}try{var at=pTmpAlignment?.PropertyType;if(at!=null)pTmpAlignment.SetValue(tmp,Enum.ToObject(at,alignment));}catch{}return tmp;}

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
        public static void SetText(object t,string s){if(t!=null)pTmpText?.SetValue(t,_BoldWrap(s??""));}
        public static void SetColor(object t,Color c){if(t!=null)pTmpColor?.SetValue(t,c);}
        public static void SetBold(object t,bool b){if(t==null)return;try{var tp=pTmpFontStyle?.PropertyType;if(tp!=null)pTmpFontStyle.SetValue(t,Enum.ToObject(tp,b?1:0));}catch{}}
        public static void SetWordWrap(object t,bool on){if(t==null||tTMP==null)return;try{var p=tTMP.GetProperty("enableWordWrapping",BindingFlags.Public|BindingFlags.Instance);p?.SetValue(t,on);}catch{}}
        public static void SetOverflowMode(object t,int mode){if(t==null||pTmpOverflow==null)return;try{pTmpOverflow.SetValue(t,Enum.ToObject(pTmpOverflow.PropertyType,mode));}catch{}}
        public static void SetCharSpacing(object t,float spacing){if(t!=null)pTmpCharSpacing?.SetValue(t,spacing);}
        public static void SetImageColor(GameObject go,Color c){if(go==null)return;var img=go.GetComponent(tImage);if(img!=null)pImgColor?.SetValue(img,c);}
        public static object GetButtonText(GameObject btn){if(btn==null)return null;foreach(Transform ch in btn.transform)foreach(var co in ch.GetComponents<Component>())if(co.GetType().Name=="TextMeshProUGUI")return co;return null;}
        public const int AlignTopLeft=257,AlignTopCenter=258,AlignTopRight=260,AlignMidLeft=513,AlignMidCenter=514,AlignMidRight=516;
    }

    // ClickHandler - camera-aware click detection for ROUNDS' ScreenSpaceCamera Canvas
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
        private static object txtRating,txtRD,txtLevel,txtXPProg,txtTotalXP,txtTopLeftName;private static Component xpFill;
        private static object txtRankedRec,txtRankedStrk,txtCasualRec,txtCasualStrk,txtSweeps,txtTotalRec,txtAccuracy,txtSessionSum,txtSessionSplit,txtSessionSweeps,txtOppSummary,txtSessionOppLifetime,txtTeam2v2Rec,txtTeam2v2Strk;
        private static GameObject sessionOppContainer;private static List<object> sessionOppTexts=new List<object>();
        private static object txtLinkCode;private static GameObject linkCodeBtn;
        // Discord ID/username click-to-reveal. Starts hidden for streamer safety.
        private static bool discordRevealed = false;
        // Chat log panel (under Discord Link in My Stats). Shows last N messages.
        private static object txtChatLog;
        // ScrollRect on the chat panel - held so RefreshChatLog can pin to the bottom on new messages.
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
            ApiClient.FetchActiveTeamSeries();
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
        private class HistoryRow{public GameObject root,seriesGO;public object txtResult,txtOpp,txtFps,txtXP,txtDate,txtCards,txtOppCards,txtSeriesHead,txtSeriesElo;}
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
        private class CardRow{public GameObject root;public GameObject hl;public object txtName,txtRarity,txtPicks,txtWins,txtWR,txtPass,txtTier;public GameObject tierBtn;public string cardName;}
        private static List<AchRow> achRows=new List<AchRow>();
        private class AchRow{public GameObject root;public object txtIcon,txtName,txtDesc,txtDate;}
        private static object txtRankedStatus,txtQueueInfo,txtMatchFound,txtConnectLabel;
        private static object txtVersionStatus;
        private static GameObject updateBtn;
        private static GameObject qSearchBtn,qCancelBtn,qMatchPanel,readyBtn,declineBtn,connectLabel,rankOnBtn,rankOffBtn;
        // TOURNAMENT GAME indicator - row below RankedRow, shows yellow text when
        // the local player is in a Photon room with someone who's an active
        // tournament opponent (sync or async).
        private static object txtTournamentGame;
        private static GameObject tournamentIndRow;
        // Column widths (scaled)
        private static readonly float[] LB_COL_W={40,40,250,88,56,56,69,76};
        // Leading column = Tier (S/A/B/C/D/E/F) for the per-player tier list.
        // Cycle on click; saves to /api/v1/players/{sid}/card-tiers. Order:
        // Tier, Card, Rarity, Picks, Wins, WR%, Pass%. Widened ~20% to match
        // the bumped font size + bold per tester ask.
        private static readonly float[] CS_COL_W={60,360,130,76,76,76,76};
        private static readonly string[] TIER_CYCLE = new[] { "", "S", "A", "B", "C", "D", "E", "F" };
        // (filter, card_name) -> tier letter (or "" = unset). Loaded from server
        // when filter changes; written through on click.
        private static Dictionary<string, string> cardTierMap = new Dictionary<string, string>();
        private static string CardTierKey(int filterIdx, string cardName)
            => $"{filterIdx}|{(cardName ?? "").ToLower()}";
        // UI scale - apply to font sizes and row heights for readability
        private const float S = 1.25f;

        public static bool IsOpen=>isOpen;
        public static void Toggle(){if(isOpen)Close();else Open();}
        public static void MarkDirty()=>dirty=true;
        public static void SetLinkCode(string code){if(txtLinkCode!=null)UIFactory.SetText(txtLinkCode,$"<color=#00FFFF>{code}</color>  - type <color=#FFFFFF>!link {code}</color> in Discord");}

        public static void Open()
        {
            if(!UIFactory.Ready){UIFactory.InitTypes();UIFactory.InitFont();}if(!UIFactory.Ready)return;
            bool inRoom=GameStateWatcher.IsInRoom;
            inGameMode=inRoom;
            // Always use our own overlay canvas - guarantees we render on top of all ROUNDS UI
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
            MaybeRefreshTournament();
            MaybeRefreshTeamTab();
        }

        // Pulled out of RefreshTeamTab so the queue lists keep updating while
        // the tab is open even when nothing else flips the dirty bit. Without
        // this the Random Queue / Custom Lobbies panels stay frozen until the
        // user navigates away and back. Throttled to 2s to match the existing
        // /team/queue/list cadence in ApiClient.
        private static float teamTabRefreshAt;
        private static float teamSeriesRefreshAt;
        public static int teamSeriesPageReq = 0;
        public static void MaybeRefreshTeamTab()
        {
            if (currentTab != 8) return;
            if (Time.unscaledTime < teamTabRefreshAt) return;
            teamTabRefreshAt = Time.unscaledTime + 2f;
            ApiClient.UpdateTeamQueueList(force: true);
            // Header count auto-refreshes via its own internal 10s timer.
            ApiClient.UpdateTeamQueueCount();
            // Recent 2v2 Series (paged) — refresh every 10s. Page state lives
            // in teamSeriesPageReq so prev/next buttons can change it.
            if (Time.unscaledTime >= teamSeriesRefreshAt)
            {
                teamSeriesRefreshAt = Time.unscaledTime + 10f;
                ApiClient.FetchAllSeriesPaged(teamSeriesPageReq, 3);
            }
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
            // when the server was healthy (no recent attempts -> no recent successes either).
            var srvRow=new GameObject("SrvRow");srvRow.transform.SetParent(content.transform,false);srvRow.AddComponent<RectTransform>();UIFactory.AddHLG(srvRow,spacing:6,forceExpandH:true);UIFactory.AddLE(srvRow,prefH:22,minH:22,flexH:0);
            txtServerStatus=UIFactory.CreateText("SrvSt",srvRow.transform,"",14f,new Color(1f,0.7f,0.6f),UIFactory.AlignMidCenter,sizeDelta:new Vector2(0,22));
            var srvTxtGO=(txtServerStatus as Component)?.gameObject;if(srvTxtGO!=null&&UIFactory.tLE!=null){var tle=srvTxtGO.GetComponent(UIFactory.tLE);if(tle!=null)UnityEngine.Object.Destroy(tle as UnityEngine.Object);}if(srvTxtGO!=null)UIFactory.AddLE(srvTxtGO,flexW:1,prefH:22);
            UIFactory.SetBold(txtServerStatus,true);
            srvRow.SetActive(false);  // off until ApiLooksDown
            srvStatusRow=srvRow;

            BuildRankedRow(content.transform);
            // TOURNAMENT GAME indicator row - lights up yellow when the local
            // player is in a Photon room with a known tournament opponent.
            var tIndRow = new GameObject("TournIndRow");
            tIndRow.transform.SetParent(content.transform, false);
            tIndRow.AddComponent<RectTransform>();
            UIFactory.AddHLG(tIndRow, spacing: 6, padL: 4);
            UIFactory.AddLE(tIndRow, prefH: 22, minH: 22, flexH: 0);
            txtTournamentGame = UIFactory.CreateText("TGame", tIndRow.transform, "", 15f, new Color(1f, 0.85f, 0.3f), UIFactory.AlignMidLeft, sizeDelta: new Vector2(700, 22));
            UIFactory.SetBold(txtTournamentGame, true);
            tIndRow.SetActive(false);
            tournamentIndRow = tIndRow;
            BuildTabBar(content.transform);
            tabPanels=new GameObject[9];tabPanels[0]=BuildMyStatsTab(content.transform);tabPanels[1]=BuildLeaderboardTab(content.transform);tabPanels[2]=BuildCardStatsTab(content.transform);tabPanels[3]=BuildAchievementsTab(content.transform);tabPanels[4]=BuildShopTab(content.transform);tabPanels[5]=BuildSettingsTab(content.transform);tabPanels[6]=BuildAdminTab(content.transform);tabPanels[7]=BuildTournamentsTab(content.transform);tabPanels[8]=BuildTeamTab(content.transform);

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
            var pn=UIFactory.CreateText("PName",row.transform,ApiClient.CachedPlayerStats?.display_name??MatchTracker.LocalDisplayName??"",20f,C_SUB,UIFactory.AlignMidLeft,sizeDelta:new Vector2(110,28));UIFactory.SetBold(pn,true);txtTopLeftName=pn;
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
             * Decline buttons. Previously the wrapper had no LayoutElement -> HLG collapsed it to 0
             * width, which meant the child text (center-anchored by default, sizeDelta 350) drew 175
             * units left of that collapsed point and ran off-screen. Create the text directly in
             * matchBtnRow with MidLeft alignment; CreateText bakes its own LE from sizeDelta so HLG
             * reserves the correct width. */
            txtConnectLabel=UIFactory.CreateText("CT",matchBtnRow.transform,"Waiting for opponent...",15f,C_BLUE,UIFactory.AlignMidLeft,sizeDelta:new Vector2(320,24));
            connectLabel=(txtConnectLabel as Component)?.gameObject;
            if(connectLabel!=null)connectLabel.SetActive(false);
            declineBtn=UIFactory.CreateButton("Decline",matchBtnRow.transform,"Decline",15f,C_WHITE,C_BTN,()=>{ApiClient.DeclineMatch(MatchTracker.LocalSteamId);},sizeDelta:new Vector2(70,24));qMatchPanel.SetActive(false);
        }

        private static void BuildTabBar(Transform parent){var bar=new GameObject("TabBar");bar.transform.SetParent(parent,false);bar.AddComponent<RectTransform>();UIFactory.AddHLG(bar,spacing:4);UIFactory.AddLE(bar,prefH:28,minH:28,flexH:0);tabButtons=new GameObject[9];tabTexts=new object[9];for(int i=0;i<9;i++){int idx=i;var btn=UIFactory.CreateButton($"Tab{i}",bar.transform,TAB_NAMES[i],13f,C_LABEL,C_TAB,()=>SwitchTab(idx),sizeDelta:new Vector2(0,26));if(UIFactory.tLE!=null){var el=btn.GetComponent(UIFactory.tLE);if(el!=null)UnityEngine.Object.Destroy(el as UnityEngine.Object);}UIFactory.AddLE(btn,prefH:26,minH:26,flexW:1,flexH:0);tabButtons[i]=btn;tabTexts[i]=UIFactory.GetButtonText(btn);}/* Admin tab visibility flips on as soon as IsAdmin resolves true (poll-driven update from RefreshCurrentTab). */tabButtons[6].SetActive(ApiClient.IsAdmin);}
        private static readonly string[] TAB_NAMES={"My Stats","Leaderboard","Card Stats","Achievements","Shop","Settings","Admin","Tournaments","2v2"};
        private static void SwitchTab(int idx){currentTab=idx;for(int i=0;i<9;i++){if(tabPanels[i]!=null)tabPanels[i].SetActive(i==idx);UIFactory.SetImageColor(tabButtons[i],i==idx?C_TABACT:C_TAB);if(tabTexts[i]!=null){UIFactory.SetColor(tabTexts[i],i==idx?C_WHITE:C_LABEL);UIFactory.SetBold(tabTexts[i],i==idx);}}if(idx==1){if(ApiClient.CachedLeaderboard==null){ApiClient.FetchLeaderboard();ApiClient.FetchRecentSeries();}ApiClient.FetchActiveSeries();var sid=MatchTracker.LocalSteamId;if(!string.IsNullOrEmpty(sid)&&sid!="unknown")ApiClient.FetchMyBets(sid);}if(idx==2&&ApiClient.CachedCardStats==null)ApiClient.FetchCardStats(200,MatchTracker.LocalSteamId);if(idx==3&&ApiClient.CachedAchievements==null){var id=MatchTracker.LocalSteamId;if(!string.IsNullOrEmpty(id)&&id!="unknown")ApiClient.FetchAchievements(id);}if(idx==4){var id=MatchTracker.LocalSteamId;if(!string.IsNullOrEmpty(id)&&id!="unknown"){ApiClient.FetchShopItems(id);ApiClient.FetchInventory(id);}else ApiClient.FetchShopItems();}if(idx==6){var id=MatchTracker.LocalSteamId;if(!string.IsNullOrEmpty(id)&&ApiClient.IsAdmin){ApiClient.FetchFlaggedMatches(id);ApiClient.FetchBannedUsers(id);}}if(idx==7){ApiClient.FetchTournamentCurrent(MatchTracker.LocalSteamId,force:true);ApiClient.FetchSiteTournamentHistory();var _msid=MatchTracker.LocalSteamId;if(!string.IsNullOrEmpty(_msid)&&_msid!="unknown")ApiClient.FetchPlayerTournaments(_msid);}if(idx==8){if(ApiClient.CachedTeamLeaderboard==null||ApiClient.CachedTeamLeaderboard.Count==0)ApiClient.FetchTeamLeaderboard();var _msid=MatchTracker.LocalSteamId;if(!string.IsNullOrEmpty(_msid)&&_msid!="unknown")ApiClient.FetchTeamMatchHistory(_msid);}dirty=true;}

        private static GameObject BuildMyStatsTab(Transform parent){var panel=new GameObject("MyStats");panel.transform.SetParent(parent,false);panel.AddComponent<RectTransform>();UIFactory.AddHLG(panel,spacing:8);UIFactory.AddLE(panel,flexH:1);var left=new GameObject("Left");left.transform.SetParent(panel.transform,false);left.AddComponent<RectTransform>();UIFactory.AddVLG(left,spacing:4);UIFactory.AddLE(left,prefW:380);var rBox=UIFactory.CreatePanel("RB",left.transform,C_PANEL);UIFactory.AddVLG(rBox,spacing:2,padL:10,padR:10,padT:6,padB:6);UIFactory.AddLE(rBox,flexH:0);var glHdr=UIFactory.CreateText("RL",rBox.transform,"Glicko-2 Rating",19f,C_SUB,sizeDelta:new Vector2(250,28));UIFactory.SetCharSpacing(glHdr,1f);var rRow=new GameObject("RR");rRow.transform.SetParent(rBox.transform,false);rRow.AddComponent<RectTransform>();UIFactory.AddHLG(rRow,spacing:12);UIFactory.AddLE(rRow,prefH:38);txtRating=UIFactory.CreateText("Rat",rRow.transform,"1500",30f,C_WHITE,UIFactory.AlignMidLeft,sizeDelta:new Vector2(110,38));UIFactory.SetBold(txtRating,true);txtRD=UIFactory.CreateText("RD",rRow.transform,"RD: 350",18f,C_LABEL,UIFactory.AlignMidLeft,sizeDelta:new Vector2(240,38));var xBox=UIFactory.CreatePanel("XB",left.transform,C_PANEL);UIFactory.AddVLG(xBox,spacing:2,padL:10,padR:10,padT:6,padB:6);UIFactory.AddLE(xBox,flexH:0);var lvRow=new GameObject("LR");lvRow.transform.SetParent(xBox.transform,false);lvRow.AddComponent<RectTransform>();UIFactory.AddHLG(lvRow,spacing:8);UIFactory.AddLE(lvRow,prefH:28);txtLevel=UIFactory.CreateText("Lv",lvRow.transform,"Level 1",19f,C_BLUE,UIFactory.AlignMidLeft,sizeDelta:new Vector2(100,28));UIFactory.SetBold(txtLevel,true);txtXPProg=UIFactory.CreateText("XPP",lvRow.transform,"",16f,C_LABEL,UIFactory.AlignMidLeft,sizeDelta:new Vector2(130,28));var xSp=new GameObject("S");xSp.transform.SetParent(lvRow.transform,false);xSp.AddComponent<RectTransform>();UIFactory.AddLE(xSp,flexW:1);txtTotalXP=UIFactory.CreateText("TXP",lvRow.transform,"0 XP",16f,C_LABEL,UIFactory.AlignMidRight,sizeDelta:new Vector2(110,28));xpFill=UIFactory.CreateFillBar("XP",xBox.transform,new Color(0.2f,0.2f,0.25f,0.8f),new Color(0.3f,0.7f,1f,0.9f),10f);var recBox=UIFactory.CreatePanel("RecB",left.transform,C_PANEL);UIFactory.AddVLG(recBox,spacing:1,padL:10,padR:10,padT:6,padB:6);UIFactory.AddLE(recBox,flexH:0);UIFactory.CreateText("RecL",recBox.transform,"Record",19f,C_SUB,sizeDelta:new Vector2(340,28));txtRankedRec=UIFactory.CreateText("RR",recBox.transform,"",16f,C_WHITE,sizeDelta:new Vector2(340,24));txtRankedStrk=UIFactory.CreateText("RS",recBox.transform,"",15f,C_LABEL,sizeDelta:new Vector2(340,22));txtTeam2v2Rec=UIFactory.CreateText("T2",recBox.transform,"",16f,C_WHITE,sizeDelta:new Vector2(340,24));txtTeam2v2Strk=UIFactory.CreateText("T2S",recBox.transform,"",15f,C_LABEL,sizeDelta:new Vector2(340,22));txtCasualRec=UIFactory.CreateText("CR",recBox.transform,"",16f,C_WHITE,sizeDelta:new Vector2(340,24));txtCasualStrk=UIFactory.CreateText("CS",recBox.transform,"",15f,C_LABEL,sizeDelta:new Vector2(340,22));txtSweeps=UIFactory.CreateText("SW",recBox.transform,"",16f,C_WHITE,sizeDelta:new Vector2(340,24));txtTotalRec=UIFactory.CreateText("TR",recBox.transform,"",15f,C_LABEL,sizeDelta:new Vector2(340,22));txtAccuracy=UIFactory.CreateText("AC",recBox.transform,"",15f,C_LABEL,sizeDelta:new Vector2(340,44));var sesBox=UIFactory.CreatePanel("SB",left.transform,C_PANEL);UIFactory.AddVLG(sesBox,spacing:3,padL:10,padR:10,padT:8,padB:8);UIFactory.AddLE(sesBox,flexH:0);UIFactory.CreateText("SL",sesBox.transform,"Session Info",19f,new Color(0.7f,0.8f,1f),sizeDelta:new Vector2(340,28));txtSessionSum=UIFactory.CreateText("SS",sesBox.transform,"No games this session",17f,C_DIM,sizeDelta:new Vector2(340,26));txtSessionSplit=UIFactory.CreateText("SSp",sesBox.transform,"",16f,C_LABEL,sizeDelta:new Vector2(340,24));txtSessionSweeps=UIFactory.CreateText("SSw",sesBox.transform,"",16f,C_WHITE,sizeDelta:new Vector2(340,24));txtSessionOppLifetime=UIFactory.CreateText("SOL",sesBox.transform,"",15f,new Color(0.6f,0.75f,1f),sizeDelta:new Vector2(340,22));sessionOppContainer=new GameObject("SOC");sessionOppContainer.transform.SetParent(sesBox.transform,false);sessionOppContainer.AddComponent<RectTransform>();UIFactory.AddVLG(sessionOppContainer,spacing:1);
        var linkBox=UIFactory.CreatePanel("LkB",left.transform,C_PANEL);UIFactory.AddVLG(linkBox,spacing:4,padL:10,padR:10,padT:6,padB:6);UIFactory.AddLE(linkBox,flexH:0);UIFactory.CreateText("LkL",linkBox.transform,"Discord Link",19f,new Color(0.55f,0.55f,0.95f),sizeDelta:new Vector2(340,28));var lkRow=new GameObject("LkR");lkRow.transform.SetParent(linkBox.transform,false);lkRow.AddComponent<RectTransform>();UIFactory.AddHLG(lkRow,spacing:8);UIFactory.AddLE(lkRow,prefH:28);linkCodeBtn=UIFactory.CreateButton("LkBtn",lkRow.transform,"Get Link Code",15f,C_WHITE,C_BTN,()=>{var id=MatchTracker.LocalSteamId;if(!string.IsNullOrEmpty(id)&&id!="unknown")ApiClient.GenerateLinkCode(id);},sizeDelta:new Vector2(130,26));/* Click-to-reveal on the link text - Discord ID/username defaults hidden for streamers.
 * TMP text IS already a Graphic; adding an Image to the same GO throws. Just enable its own raycastTarget. */
txtLinkCode=UIFactory.CreateText("LkC",lkRow.transform,"Type !link CODE in Discord",15f,C_DIM,sizeDelta:new Vector2(240,26),raycastTarget:true);{var lkTextComp=txtLinkCode as Component;if(lkTextComp!=null){var ch=lkTextComp.gameObject.AddComponent<ClickHandler>();ch.onClick=()=>{if(ClickGuard.Claim()){discordRevealed=!discordRevealed;dirty=true;}};}}
        /* In-game <-> Discord chat panel. Scrollable log fills the box; users send via hotkey T (IMGUI overlay). */
        var chatBox=UIFactory.CreatePanel("CB",left.transform,C_PANEL);UIFactory.AddVLG(chatBox,spacing:4,padL:10,padR:10,padT:6,padB:6);UIFactory.AddLE(chatBox,flexH:0);UIFactory.CreateText("CH",chatBox.transform,"Chat  <color=#888>(press T to send)</color>",17f,new Color(0.7f,0.85f,1f),sizeDelta:new Vector2(340,26));var chSV=UIFactory.CreateScrollView("ChSV",chatBox.transform,spacing:0);UIFactory.AddLE(chSV.scrollGO,prefH:160,minH:160,flexH:0);chatScrollRect=chSV.scrollGO.GetComponent(UIFactory.tScrollRect);txtChatLog=UIFactory.CreateText("ChLog",chSV.content.transform,"<color=#888><i>No messages yet. Anyone chatting here or in #scr-discussion on Discord will appear.</i></color>",14f,C_WHITE,UIFactory.AlignTopLeft,sizeDelta:new Vector2(360,400));UIFactory.SetWordWrap(txtChatLog,true);
/* CreateText baked a LayoutElement with prefH=400 onto the chat-log GO. With the parent VLG/CSF reading
 * that, a single very long message (e.g. a 9000-char changelog paste) renders as TMP overflow but the
 * scroll content stays clamped at 400px -> unreachable bottom. Zero out the prefH so TMP's own
 * ILayoutElement.preferredHeight (its actual rendered height) drives the content size instead. */
{var chatLE=(txtChatLog as Component)?.gameObject.GetComponent(UIFactory.tLE);if(chatLE!=null){var prefHProp=UIFactory.tLE.GetProperty("preferredHeight",BindingFlags.Public|BindingFlags.Instance);prefHProp?.SetValue(chatLE,-1f);}}
        var right=new GameObject("Right");right.transform.SetParent(panel.transform,false);right.AddComponent<RectTransform>();UIFactory.AddVLG(right,spacing:4);UIFactory.AddLE(right,flexW:1,flexH:1);var rkBox=UIFactory.CreatePanel("RkB",right.transform,C_PANEL);UIFactory.AddVLG(rkBox,spacing:1,padL:8,padR:8,padT:6,padB:6);UIFactory.AddLE(rkBox,flexH:1);UIFactory.CreateText("RkH",rkBox.transform,"Ranked History",21f,C_GOLD,sizeDelta:new Vector2(250,30));txtOppSummary=UIFactory.CreateText("OS",rkBox.transform,"",15f,new Color(0.7f,0.8f,1f),sizeDelta:new Vector2(500,22));var rkSV=UIFactory.CreateScrollView("RkSV",rkBox.transform,spacing:1);UIFactory.AddLE(rkSV.scrollGO,flexH:1);rankedContainer=rkSV.content;for(int i=0;i<15;i++)rankedRows.Add(CreateHistoryRow(rankedContainer.transform,$"rr{i}"));var rPg=new GameObject("RPg");rPg.transform.SetParent(rkBox.transform,false);rPg.AddComponent<RectTransform>();UIFactory.AddHLG(rPg,spacing:6,forceExpandH:true);UIFactory.AddLE(rPg,prefH:20,flexH:0);var rS1=new GameObject("S");rS1.transform.SetParent(rPg.transform,false);rS1.AddComponent<RectTransform>();UIFactory.AddLE(rS1,flexW:1);rPrev=UIFactory.CreateButton("rP",rPg.transform,"< Prev",10f,C_LABEL,C_BTN,()=>{if(rankedPage>0){rankedPage--;dirty=true;}},sizeDelta:new Vector2(50,18));txtRankedPage=UIFactory.CreateText("rPI",rPg.transform,"",10f,C_LABEL,UIFactory.AlignMidCenter,sizeDelta:new Vector2(35,18));rNext=UIFactory.CreateButton("rN",rPg.transform,"Next >",10f,C_LABEL,C_BTN,()=>{rankedPage++;dirty=true;},sizeDelta:new Vector2(50,18));var rS2=new GameObject("S");rS2.transform.SetParent(rPg.transform,false);rS2.AddComponent<RectTransform>();UIFactory.AddLE(rS2,flexW:1);
        var csBox=UIFactory.CreatePanel("CsB",right.transform,C_PANEL);UIFactory.AddVLG(csBox,spacing:1,padL:8,padR:8,padT:6,padB:6);UIFactory.AddLE(csBox,flexH:1);UIFactory.CreateText("CsH",csBox.transform,"Casual History",21f,C_SUB,sizeDelta:new Vector2(250,30));var csSV=UIFactory.CreateScrollView("CsSV",csBox.transform,spacing:1);UIFactory.AddLE(csSV.scrollGO,flexH:1);casualContainer=csSV.content;for(int i=0;i<12;i++)casualRows.Add(CreateHistoryRow(casualContainer.transform,$"cr{i}"));var cPg=new GameObject("CPg");cPg.transform.SetParent(csBox.transform,false);cPg.AddComponent<RectTransform>();UIFactory.AddHLG(cPg,spacing:6,forceExpandH:true);UIFactory.AddLE(cPg,prefH:20,flexH:0);var cS1=new GameObject("S");cS1.transform.SetParent(cPg.transform,false);cS1.AddComponent<RectTransform>();UIFactory.AddLE(cS1,flexW:1);cPrev=UIFactory.CreateButton("cP",cPg.transform,"< Prev",10f,C_LABEL,C_BTN,()=>{if(casualPage>0){casualPage--;dirty=true;}},sizeDelta:new Vector2(50,18));txtCasualPage=UIFactory.CreateText("cPI",cPg.transform,"",10f,C_LABEL,UIFactory.AlignMidCenter,sizeDelta:new Vector2(35,18));cNext=UIFactory.CreateButton("cN",cPg.transform,"Next >",10f,C_LABEL,C_BTN,()=>{casualPage++;dirty=true;},sizeDelta:new Vector2(50,18));var cS2=new GameObject("S");cS2.transform.SetParent(cPg.transform,false);cS2.AddComponent<RectTransform>();UIFactory.AddLE(cS2,flexW:1);return panel;}

        private static HistoryRow CreateHistoryRow(Transform parent,string name){var row=new HistoryRow();row.seriesGO=new GameObject(name+"s");row.seriesGO.transform.SetParent(parent,false);row.seriesGO.AddComponent<RectTransform>();UIFactory.AddHLG(row.seriesGO,spacing:4,padL:4);UIFactory.AddLE(row.seriesGO,prefH:25);row.txtSeriesHead=UIFactory.CreateText("sh",row.seriesGO.transform,"",19f,C_GREEN,sizeDelta:new Vector2(500,25));row.txtSeriesElo=UIFactory.CreateText("se",row.seriesGO.transform,"",19f,C_GREEN,UIFactory.AlignMidRight,sizeDelta:new Vector2(160,25));row.seriesGO.SetActive(false);row.root=new GameObject(name);row.root.transform.SetParent(parent,false);row.root.AddComponent<RectTransform>();UIFactory.AddVLG(row.root,spacing:0,padL:4);var main=new GameObject("m");main.transform.SetParent(row.root.transform,false);main.AddComponent<RectTransform>();UIFactory.AddHLG(main,spacing:4);UIFactory.AddLE(main,prefH:25);row.txtResult=UIFactory.CreateText("r",main.transform,"",19f,C_GREEN,UIFactory.AlignMidLeft,sizeDelta:new Vector2(200,25));row.txtOpp=UIFactory.CreateText("o",main.transform,"",18f,C_WHITE,UIFactory.AlignMidLeft,sizeDelta:new Vector2(240,25));row.txtFps=UIFactory.CreateText("fp",main.transform,"",14f,C_LABEL,UIFactory.AlignMidLeft,sizeDelta:new Vector2(140,25));var sp=new GameObject("S");sp.transform.SetParent(main.transform,false);sp.AddComponent<RectTransform>();UIFactory.AddLE(sp,flexW:1);row.txtXP=UIFactory.CreateText("x",main.transform,"",16f,C_BLUE,UIFactory.AlignMidRight,sizeDelta:new Vector2(65,25));row.txtDate=UIFactory.CreateText("d",main.transform,"",15f,C_DIM,UIFactory.AlignMidRight,sizeDelta:new Vector2(45,25));row.txtCards=UIFactory.CreateText("c",row.root.transform,"",19f,new Color(0.6f,0.7f,0.9f),sizeDelta:new Vector2(900,25));UIFactory.SetCharSpacing(row.txtCards,1.5f);row.txtOppCards=UIFactory.CreateText("oc",row.root.transform,"",19f,new Color(0.9f,0.6f,0.5f),sizeDelta:new Vector2(900,25));UIFactory.SetCharSpacing(row.txtOppCards,1.5f);row.root.SetActive(false);return row;}

        private static object txtLBPlayerName;
        private static GameObject BuildLeaderboardTab(Transform parent){var panel=new GameObject("Leaderboard");panel.transform.SetParent(parent,false);panel.AddComponent<RectTransform>();UIFactory.AddHLG(panel,spacing:6);UIFactory.AddLE(panel,flexH:1);/* === LEFT: Recent Ranked Series === */var seriesCol=UIFactory.CreatePanel("LBSeries",panel.transform,C_PANEL);UIFactory.AddVLG(seriesCol,spacing:2,padL:8,padR:8,padT:6,padB:6);UIFactory.AddLE(seriesCol,prefW:400,minW:340,flexH:1);txtLiveHeader=UIFactory.CreateText("RSL",seriesCol.transform,"<color=#FF6688>* Live Ranked Games</color>",17f,C_WHITE,UIFactory.AlignMidLeft,sizeDelta:new Vector2(280,26));txtLiveSeries=UIFactory.CreateText("LIVE",seriesCol.transform,"<color=#666><i>No live games right now.</i></color>",13f,C_WHITE,UIFactory.AlignTopLeft,sizeDelta:new Vector2(280,24));UIFactory.SetWordWrap(txtLiveSeries,true);liveBetsContainer=new GameObject("LiveBets");liveBetsContainer.transform.SetParent(seriesCol.transform,false);liveBetsContainer.AddComponent<RectTransform>();UIFactory.AddVLG(liveBetsContainer,spacing:2);/* No LayoutElement: VLG on this container already sums child preferred heights with priority 0 and reports that as its preferred height, so the parent VLG sizes us correctly. Previously an LE with prefH:0 priority:1 was overriding that sum to 0, collapsing the live series into the recent series list below. */
/* Live-series pagination header row - shows "X live (page N/M) < >" when >5 series. */
liveBetsPager=new GameObject("LivePg");liveBetsPager.transform.SetParent(seriesCol.transform,false);liveBetsPager.AddComponent<RectTransform>();UIFactory.AddHLG(liveBetsPager,spacing:4,forceExpandH:true);UIFactory.AddLE(liveBetsPager,prefH:18,flexH:0);
liveBetsPrev=UIFactory.CreateButton("lvP",liveBetsPager.transform,"< Prev",10f,C_LABEL,C_BTN,()=>{if(liveSeriesPage>0){liveSeriesPage--;dirty=true;}},sizeDelta:new Vector2(50,18));
txtLiveBetsPage=UIFactory.CreateText("lvPI",liveBetsPager.transform,"",10f,C_LABEL,UIFactory.AlignMidCenter,sizeDelta:new Vector2(80,18));
liveBetsNext=UIFactory.CreateButton("lvN",liveBetsPager.transform,"Next >",10f,C_LABEL,C_BTN,()=>{liveSeriesPage++;dirty=true;},sizeDelta:new Vector2(50,18));
liveBetsPager.SetActive(false);
/* Visual spacer between Live and Recent panels - was visually jammed previously. */
{var liveRecentSpacer=new GameObject("LRSp");liveRecentSpacer.transform.SetParent(seriesCol.transform,false);liveRecentSpacer.AddComponent<RectTransform>();UIFactory.AddLE(liveRecentSpacer,prefH:18,minH:18,flexH:0);}
UIFactory.CreateText("RSL",seriesCol.transform,"<color=#99AAEE>Recent Ranked Series</color>",17f,C_WHITE,UIFactory.AlignMidLeft,sizeDelta:new Vector2(280,26));var rsSV=UIFactory.CreateScrollView("RSSV",seriesCol.transform,spacing:1);UIFactory.AddLE(rsSV.scrollGO,flexH:1);txtRecentSeries=UIFactory.CreateText("RST",rsSV.content.transform,"Loading...",16f,C_DIM,sizeDelta:new Vector2(280,20));var sPg=new GameObject("SPg");sPg.transform.SetParent(seriesCol.transform,false);sPg.AddComponent<RectTransform>();UIFactory.AddHLG(sPg,spacing:4,forceExpandH:true);UIFactory.AddLE(sPg,prefH:20,flexH:0);var sS1=new GameObject("S");sS1.transform.SetParent(sPg.transform,false);sS1.AddComponent<RectTransform>();UIFactory.AddLE(sS1,flexW:1);seriesPrev=UIFactory.CreateButton("sP",sPg.transform,"< Prev",10f,C_LABEL,C_BTN,()=>{if(recentSeriesPage>0){recentSeriesPage--;dirty=true;}},sizeDelta:new Vector2(50,18));txtSeriesPage=UIFactory.CreateText("sPI",sPg.transform,"",10f,C_LABEL,UIFactory.AlignMidCenter,sizeDelta:new Vector2(35,18));seriesNext=UIFactory.CreateButton("sN",sPg.transform,"Next >",10f,C_LABEL,C_BTN,()=>{recentSeriesPage++;dirty=true;},sizeDelta:new Vector2(50,18));var sS2=new GameObject("S");sS2.transform.SetParent(sPg.transform,false);sS2.AddComponent<RectTransform>();UIFactory.AddLE(sS2,flexW:1);/* === MIDDLE: Leaderboard list === */var mid=new GameObject("LBMid");mid.transform.SetParent(panel.transform,false);mid.AddComponent<RectTransform>();UIFactory.AddVLG(mid,spacing:2);UIFactory.AddLE(mid,prefW:560,minW:500,flexH:1);string[]hL={"#","Lv","Player","Rating","W","L","W/L","Gold"};string[]hK={"rank","level","display_name","rating","wins","losses","wl_ratio","gold"};var hRow=new GameObject("LBH");hRow.transform.SetParent(mid.transform,false);hRow.AddComponent<RectTransform>();UIFactory.AddHLG(hRow,spacing:2,forceExpandH:true);UIFactory.AddLE(hRow,prefH:28,minH:28,flexH:0);lbSortTexts=new object[hL.Length];lbSortBtns=new GameObject[hL.Length];var lbHSp1=new GameObject("S");lbHSp1.transform.SetParent(hRow.transform,false);lbHSp1.AddComponent<RectTransform>();UIFactory.AddLE(lbHSp1,flexW:1);for(int hi=0;hi<hL.Length;hi++){int idx=hi;string arrow=lbSort==hK[hi]?(lbSortDesc?" v":" ^"):"";var hBtn=UIFactory.CreateButton($"LH{hi}",hRow.transform,hL[hi]+arrow,14f,lbSort==hK[hi]?C_WHITE:C_LABEL,lbSort==hK[hi]?C_TABACT:C_TAB,()=>{if(lbSort==hK[idx])lbSortDesc=!lbSortDesc;else{lbSort=hK[idx];lbSortDesc=(idx>=3);}dirty=true;},sizeDelta:new Vector2(LB_COL_W[hi],22));if(UIFactory.tLE!=null){var el=hBtn.GetComponent(UIFactory.tLE);if(el!=null)UnityEngine.Object.Destroy(el as UnityEngine.Object);}UIFactory.AddLE(hBtn,prefW:LB_COL_W[hi],prefH:22,flexH:0);lbSortBtns[hi]=hBtn;lbSortTexts[hi]=UIFactory.GetButtonText(hBtn);}var lbHSp2=new GameObject("S");lbHSp2.transform.SetParent(hRow.transform,false);lbHSp2.AddComponent<RectTransform>();UIFactory.AddLE(lbHSp2,flexW:1);var sv=UIFactory.CreateScrollView("LBSV",mid.transform);UIFactory.AddLE(sv.scrollGO,flexH:1);for(int i=0;i<100;i++)lbRows.Add(CreateLBRow(sv.content.transform,$"lb{i}",i));var lbPg=new GameObject("LBPg");lbPg.transform.SetParent(mid.transform,false);lbPg.AddComponent<RectTransform>();UIFactory.AddHLG(lbPg,spacing:6,forceExpandH:true);UIFactory.AddLE(lbPg,prefH:24,flexH:0);txtLBCount=UIFactory.CreateText("LBC",lbPg.transform,"",15f,C_LABEL,sizeDelta:new Vector2(160,22));var lbS1=new GameObject("S");lbS1.transform.SetParent(lbPg.transform,false);lbS1.AddComponent<RectTransform>();UIFactory.AddLE(lbS1,flexW:1);lbPrev=UIFactory.CreateButton("lbP",lbPg.transform,"< Prev",13f,C_LABEL,C_BTN,()=>{if(lbPage>0){lbPage--;dirty=true;}},sizeDelta:new Vector2(60,22));txtLBPage=UIFactory.CreateText("lbPI",lbPg.transform,"",13f,C_LABEL,UIFactory.AlignMidCenter,sizeDelta:new Vector2(40,22));lbNext=UIFactory.CreateButton("lbN",lbPg.transform,"Next >",13f,C_LABEL,C_BTN,()=>{lbPage++;dirty=true;},sizeDelta:new Vector2(60,22));/* === RIGHT: Player detail === */var right=UIFactory.CreatePanel("LBR",panel.transform,C_PANEL);UIFactory.AddVLG(right,spacing:4,padL:12,padR:12,padT:8,padB:8);UIFactory.AddLE(right,flexW:1,flexH:1);txtLBPlayerName=UIFactory.CreateText("LBName",right.transform,"Click a player",20f,C_WHITE,UIFactory.AlignMidLeft,sizeDelta:new Vector2(340,26));UIFactory.SetBold(txtLBPlayerName,true);lbGraphPanel=new GameObject("Graph");lbGraphPanel.transform.SetParent(right.transform,false);var grt=lbGraphPanel.AddComponent<RectTransform>();UIFactory.AddLE(lbGraphPanel,prefH:80,minH:80,flexH:0);/* Add mask to clip graph bars within bounds */var gMaskImg=lbGraphPanel.AddComponent(UIFactory.tImage);UIFactory.tImage.GetProperty("color",BindingFlags.Public|BindingFlags.Instance)?.SetValue(gMaskImg,new Color(0,0,0,0.01f));if(UIFactory.tMask!=null){var gMask=lbGraphPanel.AddComponent(UIFactory.tMask);try{UIFactory.tMask.GetProperty("showMaskGraphic",BindingFlags.Public|BindingFlags.Instance)?.SetValue(gMask,false);}catch{}}lbGraphPanel.SetActive(false);var lbDetailSV=UIFactory.CreateScrollView("LBDSV",right.transform,spacing:0);UIFactory.AddLE(lbDetailSV.scrollGO,flexH:1);txtLBDetail=UIFactory.CreateText("LBD",lbDetailSV.content.transform,"",16f,C_DIM,sizeDelta:new Vector2(340,24));lbBlockRow=new GameObject("BlockRow");lbBlockRow.transform.SetParent(right.transform,false);lbBlockRow.AddComponent<RectTransform>();UIFactory.AddHLG(lbBlockRow,spacing:0);UIFactory.AddLE(lbBlockRow,prefH:28,minH:28,flexH:0);lbBlockBtn=UIFactory.CreateButton("LBBlock",lbBlockRow.transform,"Block from Ranked",14f,C_WHITE,new Color(0.5f,0.15f,0.15f,0.9f),()=>{if(string.IsNullOrEmpty(selectedSteamId)||selectedSteamId==MatchTracker.LocalSteamId)return;string myId=MatchTracker.LocalSteamId;if(ApiClient.IsPlayerBlocked(selectedSteamId))ApiClient.UnblockPlayer(myId,selectedSteamId);else ApiClient.BlockPlayer(myId,selectedSteamId);},sizeDelta:new Vector2(160,24));var lbBlockSpacer=new GameObject("S");lbBlockSpacer.transform.SetParent(lbBlockRow.transform,false);lbBlockSpacer.AddComponent<RectTransform>();UIFactory.AddLE(lbBlockSpacer,flexW:1);lbBlockBtn.SetActive(true);lbBlockRow.SetActive(false);lbBlockTxt=UIFactory.GetButtonText(lbBlockBtn);return panel;}

        private static LBRow CreateLBRow(Transform parent,string name,int rowIndex){var row=new LBRow();row.root=new GameObject(name);row.root.transform.SetParent(parent,false);row.root.AddComponent<RectTransform>();UIFactory.AddHLG(row.root,spacing:0,forceExpandH:true);UIFactory.AddLE(row.root,prefH:28);var lsp=new GameObject("S");lsp.transform.SetParent(row.root.transform,false);lsp.AddComponent<RectTransform>();UIFactory.AddLE(lsp,flexW:1);row.hlWrap=new GameObject("W");row.hlWrap.transform.SetParent(row.root.transform,false);row.hlWrap.AddComponent<RectTransform>();UIFactory.AddHLG(row.hlWrap,spacing:2,forceExpandH:true);if(UIFactory.tImage!=null){var img=row.hlWrap.AddComponent(UIFactory.tImage);UIFactory.tImage.GetProperty("color",BindingFlags.Public|BindingFlags.Instance)?.SetValue(img,new Color(0.15f,0.15f,0.2f,0.01f));UIFactory.tImage.GetProperty("raycastTarget",BindingFlags.Public|BindingFlags.Instance)?.SetValue(img,true);}row.txtRank=UIFactory.CreateText("r",row.hlWrap.transform,"",15f,C_GOLD,UIFactory.AlignMidCenter,sizeDelta:new Vector2(LB_COL_W[0],25));row.txtLv=UIFactory.CreateText("l",row.hlWrap.transform,"",15f,C_BLUE,UIFactory.AlignMidCenter,sizeDelta:new Vector2(LB_COL_W[1],25));row.txtName=UIFactory.CreateText("n",row.hlWrap.transform,"",16f,C_WHITE,UIFactory.AlignMidLeft,sizeDelta:new Vector2(LB_COL_W[2],25));row.txtRating=UIFactory.CreateText("rt",row.hlWrap.transform,"",16f,C_WHITE,UIFactory.AlignMidCenter,sizeDelta:new Vector2(LB_COL_W[3],25));UIFactory.SetBold(row.txtRating,true);row.txtW=UIFactory.CreateText("w",row.hlWrap.transform,"",15f,C_GREEN,UIFactory.AlignMidCenter,sizeDelta:new Vector2(LB_COL_W[4],25));row.txtL=UIFactory.CreateText("ls",row.hlWrap.transform,"",15f,C_RED,UIFactory.AlignMidCenter,sizeDelta:new Vector2(LB_COL_W[5],25));row.txtWL=UIFactory.CreateText("wl",row.hlWrap.transform,"",15f,C_LABEL,UIFactory.AlignMidCenter,sizeDelta:new Vector2(LB_COL_W[6],25));row.txtGold=UIFactory.CreateText("gd",row.hlWrap.transform,"",15f,C_GOLD,UIFactory.AlignMidCenter,sizeDelta:new Vector2(LB_COL_W[7],25));UIFactory.SetBold(row.txtGold,true);var rsp=new GameObject("S");rsp.transform.SetParent(row.root.transform,false);rsp.AddComponent<RectTransform>();UIFactory.AddLE(rsp,flexW:1);int idx=rowIndex;var ch=row.root.AddComponent<ClickHandler>();ch.onClick=()=>{if(ClickGuard.Claim()&&idx>=0&&idx<lbRows.Count&&!string.IsNullOrEmpty(lbRows[idx].steamId)){string sid=lbRows[idx].steamId;if(selectedSteamId==sid){selectedSteamId="";selectedStats=null;}else{selectedSteamId=sid;selectedStats=null;ApiClient.FetchPlayerStatsForView(sid,(d)=>{selectedStats=d;dirty=true;});ApiClient.FetchAchievementsForView(sid);ApiClient.FetchPlayerTournaments(sid);}dirty=true;}};row.root.SetActive(false);return row;}

        private static GameObject BuildCardStatsTab(Transform parent){var panel=new GameObject("CardStats");panel.transform.SetParent(parent,false);panel.AddComponent<RectTransform>();UIFactory.AddVLG(panel,spacing:4);UIFactory.AddLE(panel,flexH:1);var fBar=new GameObject("Filt");fBar.transform.SetParent(panel.transform,false);fBar.AddComponent<RectTransform>();UIFactory.AddHLG(fBar,spacing:4,padL:12,forceExpandH:true);UIFactory.AddLE(fBar,prefH:34,minH:34,flexH:0);
        // Export Tier List button on the LEFT of the filter row (was its own
        // row — tester asked to move card list up). Filter buttons still
        // center under the data columns via flex spacers.
        var expBtnInline=UIFactory.CreateButton("ExpBtn",fBar.transform,"Export Tier List",16f,C_WHITE,new Color(0.20f,0.55f,0.30f,0.95f),
            ()=>{ ExportCardTierList(); }, sizeDelta:new Vector2(180,30));
        UIFactory.SetBold(UIFactory.GetButtonText(expBtnInline),true);
        if(UIFactory.tLE!=null){var el=expBtnInline.GetComponent(UIFactory.tLE);if(el!=null)UnityEngine.Object.Destroy(el as UnityEngine.Object);}
        UIFactory.AddLE(expBtnInline,prefW:180,minW:180,prefH:30,minH:30,flexH:0,flexW:0);
        var fSp1=new GameObject("S");fSp1.transform.SetParent(fBar.transform,false);fSp1.AddComponent<RectTransform>();UIFactory.AddLE(fSp1,flexW:1);string[]fN={"All","Ranked","Casual"};cardFilterBtns=new GameObject[3];cardFilterTexts=new object[3];
        // Filter buttons sized to share the same total span as the data
        // columns below them (Tier→Pass% sum from CS_COL_W). 3 buttons, no
        // flex, fixed prefW each. Mirrors the data row's flex-spacer pattern
        // so they line up visually.
        float CS_TOTAL_W=0f; for(int ci=0;ci<CS_COL_W.Length;ci++) CS_TOTAL_W+=CS_COL_W[ci];
        float perFilterW=Mathf.Floor((CS_TOTAL_W-2f*2f)/3f); // 2 = HLG spacing
        for(int i=0;i<3;i++){int idx=i;var btn=UIFactory.CreateButton($"F{i}",fBar.transform,fN[i],18f,C_LABEL,i==0?C_TABACT:C_TAB,()=>{cardFilter=idx;string r=idx==1?"true":idx==2?"false":null;ApiClient.FetchCardStats(200,MatchTracker.LocalSteamId,"times_picked",r);LoadCardTiersForCurrentFilter();for(int fi=0;fi<3;fi++){UIFactory.SetImageColor(cardFilterBtns[fi],fi==idx?C_TABACT:C_TAB);if(cardFilterTexts[fi]!=null){UIFactory.SetColor(cardFilterTexts[fi],fi==idx?C_WHITE:C_LABEL);UIFactory.SetBold(cardFilterTexts[fi],fi==idx);}}dirty=true;},sizeDelta:new Vector2(perFilterW,30));if(UIFactory.tLE!=null){var el=btn.GetComponent(UIFactory.tLE);if(el!=null)UnityEngine.Object.Destroy(el as UnityEngine.Object);}UIFactory.AddLE(btn,prefW:perFilterW,minW:perFilterW,prefH:30,minH:30,flexH:0,flexW:0);UIFactory.SetBold(UIFactory.GetButtonText(btn),true);cardFilterBtns[i]=btn;cardFilterTexts[i]=UIFactory.GetButtonText(btn);}var fSp2=new GameObject("S");fSp2.transform.SetParent(fBar.transform,false);fSp2.AddComponent<RectTransform>();UIFactory.AddLE(fSp2,flexW:1);
        // Right-side balance spacer matches the Export button's width (180px)
        // so the 3 filter buttons stay centered above the data columns even
        // with the Export button squatting on the left of this row.
        var fBalance=new GameObject("FBal");fBalance.transform.SetParent(fBar.transform,false);fBalance.AddComponent<RectTransform>();UIFactory.AddLE(fBalance,prefW:180,minW:180,flexW:0);
        // Header — Tier first (matches the data row's column order). All 7 are
        // sortable by clicking the column header. Sizes bumped 20% with bold
        // labels (matches the bumped data rows).
        string[]hL={"Tier","Card","Rarity","Picks","Wins","WR%","Pass%"};string[]hK={"tier","card_name","card_rarity","times_picked","wins_with_card","win_rate","pass_rate"};var hRow=new GameObject("CHR");hRow.transform.SetParent(panel.transform,false);hRow.AddComponent<RectTransform>();UIFactory.AddHLG(hRow,spacing:2,forceExpandH:true);UIFactory.AddLE(hRow,prefH:32,minH:32,flexH:0);cardSortTexts=new object[7];cardSortBtns=new GameObject[7];var csHSp1=new GameObject("S");csHSp1.transform.SetParent(hRow.transform,false);csHSp1.AddComponent<RectTransform>();UIFactory.AddLE(csHSp1,flexW:1);for(int hi=0;hi<7;hi++){int idx=hi;string arrow=cardSort==hK[hi]?(cardSortDesc?" v":" ^"):"";var hBtn=UIFactory.CreateButton($"CS{hi}",hRow.transform,hL[hi]+arrow,18f,cardSort==hK[hi]?C_WHITE:C_LABEL,cardSort==hK[hi]?C_TABACT:C_TAB,()=>{if(cardSort==hK[idx])cardSortDesc=!cardSortDesc;else{cardSort=hK[idx];cardSortDesc=true;}dirty=true;},sizeDelta:new Vector2(CS_COL_W[hi],26));if(UIFactory.tLE!=null){var el=hBtn.GetComponent(UIFactory.tLE);if(el!=null)UnityEngine.Object.Destroy(el as UnityEngine.Object);}UIFactory.AddLE(hBtn,prefW:CS_COL_W[hi],prefH:26,flexH:0);UIFactory.SetBold(UIFactory.GetButtonText(hBtn),true);cardSortBtns[hi]=hBtn;cardSortTexts[hi]=UIFactory.GetButtonText(hBtn);}
        var hSp=new GameObject("S");hSp.transform.SetParent(hRow.transform,false);hSp.AddComponent<RectTransform>();UIFactory.AddLE(hSp,flexW:1);var sv=UIFactory.CreateScrollView("CSV",panel.transform);UIFactory.AddLE(sv.scrollGO,flexH:1);for(int i=0;i<100;i++)cardRows.Add(CreateCardRow(sv.content.transform,$"cd{i}"));return panel;}

        private static CardRow CreateCardRow(Transform parent,string name){var row=new CardRow();row.root=new GameObject(name);row.root.transform.SetParent(parent,false);row.root.AddComponent<RectTransform>();
            UIFactory.AddHLG(row.root,spacing:0,forceExpandH:true);UIFactory.AddLE(row.root,prefH:30);
            // Leading flex spacer — leaves the data columns centered horizontally.
            var cls=new GameObject("S");cls.transform.SetParent(row.root.transform,false);cls.AddComponent<RectTransform>();UIFactory.AddLE(cls,flexW:1);
            // Highlight wrapper — Image on this GO is repainted in RefreshCardStats
            // with a translucent tier tint. Sized to span ONLY Tier→Pass% so
            // the highlight stops at the data-column boundaries (tester report:
            // "change its width to the boundaries of the columns").
            row.hl=new GameObject("hl");row.hl.transform.SetParent(row.root.transform,false);row.hl.AddComponent<RectTransform>();
            var bgImg=row.hl.AddComponent(UIFactory.tImage);
            UIFactory.tImage.GetProperty("color",BindingFlags.Public|BindingFlags.Instance)?.SetValue(bgImg,new Color(0,0,0,0));
            UIFactory.tImage.GetProperty("raycastTarget",BindingFlags.Public|BindingFlags.Instance)?.SetValue(bgImg,false);
            UIFactory.AddHLG(row.hl,spacing:2,forceExpandH:true);UIFactory.AddLE(row.hl,prefH:30,minH:30,flexH:0);
            // Tier (LEFT-side leading column). Clickable button cycles
            // S/A/B/C/D/E/F/clear. Text rendered black + bold for max contrast
            // on the saturated tier-color backgrounds.
            row.tierBtn=UIFactory.CreateButton("tb",row.hl.transform,"-",18f,Color.black,new Color(0.18f,0.20f,0.24f,0.85f),
                ()=>{ if(string.IsNullOrEmpty(row.cardName))return; CycleCardTierInPlace(row,row.cardName); },
                sizeDelta:new Vector2(CS_COL_W[0],30));
            row.txtTier=UIFactory.GetButtonText(row.tierBtn);
            UIFactory.SetBold(row.txtTier,true);
            // Card Stats text bumped 20% larger + bold (tester ask).
            row.txtName=UIFactory.CreateText("t",row.hl.transform,"",19f,C_WHITE,UIFactory.AlignMidLeft,sizeDelta:new Vector2(CS_COL_W[1],30),raycastTarget:true);UIFactory.SetBold(row.txtName,true);
            row.txtRarity=UIFactory.CreateText("tr",row.hl.transform,"",18f,C_LABEL,UIFactory.AlignMidCenter,sizeDelta:new Vector2(CS_COL_W[2],30));UIFactory.SetBold(row.txtRarity,true);
            row.txtPicks=UIFactory.CreateText("tp",row.hl.transform,"",19f,C_WHITE,UIFactory.AlignMidCenter,sizeDelta:new Vector2(CS_COL_W[3],30));UIFactory.SetBold(row.txtPicks,true);
            row.txtWins=UIFactory.CreateText("tw",row.hl.transform,"",19f,C_WHITE,UIFactory.AlignMidCenter,sizeDelta:new Vector2(CS_COL_W[4],30));UIFactory.SetBold(row.txtWins,true);
            row.txtWR=UIFactory.CreateText("wr",row.hl.transform,"",19f,C_WHITE,UIFactory.AlignMidCenter,sizeDelta:new Vector2(CS_COL_W[5],30));UIFactory.SetBold(row.txtWR,true);
            row.txtPass=UIFactory.CreateText("pr",row.hl.transform,"",19f,C_LABEL,UIFactory.AlignMidCenter,sizeDelta:new Vector2(CS_COL_W[6],30));UIFactory.SetBold(row.txtPass,true);
            // Click on the card name = popup with the card visual + description.
            try
            {
                var nm=row.txtName as Component;
                if(nm!=null){var ch=nm.gameObject.AddComponent<ClickHandler>();ch.onClick=()=>{ if(ClickGuard.Claim() && !string.IsNullOrEmpty(row.cardName)) ShowCardPreview(row.cardName); };}
            }catch{}
            var sp=new GameObject("S");sp.transform.SetParent(row.root.transform,false);sp.AddComponent<RectTransform>();UIFactory.AddLE(sp,flexW:1);row.root.SetActive(false);return row;}

        // Static description fallback for cards whose CardInfo.cardDestription
        // is empty (some cards bake the description into the prefab UI text
        // only, others rely entirely on the stat block). Sourced from the
        // user-provided full card list (mirrors the ROUNDS wiki). Keyed by
        // both spaced + unspaced lowercase variants so "Wind Up" / "Windup"
        // / "windup" all resolve. Skipped: cards whose Description column
        // was N/A — their stat block speaks for itself.
        private static readonly Dictionary<string, string> CARD_DESC_FALLBACK = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase)
        {
            { "abyssalcountdown",   "Stand still to summon dark powers." },
            { "barrage",            "Fire many bullets at the same time." },
            { "bigbullet",          "Bigger bullets." },
            { "bigbullets",         "Bigger bullets." },
            { "bombsaway",          "Spawn a bunch of small bombs around you when you block." },
            { "brawler",            "+200% HP for 3s after dealing damage." },
            { "buckshot",           "Adds a shotgun vibe to your attack." },
            { "burst",              "Multiple bullets are fired in a sequence." },
            { "chase",              "+60% movement when moving towards the opponent." },
            { "chillingpresence",   "Slightly slow nearby enemies." },
            { "dazzle",             "Bullets stun the opponent multiple times." },
            { "decay",              "Damage done to you is dealt over 4 seconds." },
            { "demonicpact",        "Shooting costs 10HP. Removes shooting cooldown." },
            { "drillammo",          "Bullets drill through walls." },
            { "echo",               "Blocking triggers another, delayed block." },
            { "emp",                "Blocking spawns a ring of slowing projectiles." },
            { "empower",            "Blocking increases the damage and speed of your next shot. The shot triggers any on-block abilities where it lands." },
            { "explosivebullet",    "Bullet explodes on impact." },
            { "fastforward",        "Bullets keep the default trajectory." },
            { "frostslam",          "Slows enemies around you when you block." },
            { "grow",               "Bullets get more damage over time when travelling." },
            { "healingfield",       "Blocking creates a healing field." },
            { "homing",             "Bullets home towards visible targets." },
            { "implode",            "Blocking pulls enemies towards you." },
            { "lifestealer",        "Steal HP from your opponent when near." },
            { "overpower",          "Deal 15% of your max HP to enemies around you when you block." },
            { "parasite",           "Bullets deal damage over 5 seconds." },
            { "phoenix",            "Respawn once on death." },
            { "poison",             "Bullets deal damage over 3 seconds." },
            { "pristineperseverance", "+400% HP when above 90% HP." },
            { "pristineperseverence", "+400% HP when above 90% HP." },
            { "radarshot",          "Blocking scans the area for enemies. You automatically shoot any enemy found." },
            { "radiance",           "Spawn damaging sun waves when reloading. The rate increases during the reload sequence." },
            { "refresh",            "You get block back when dealing damage." },
            { "remote",             "Steer bullet with right stick / mouse." },
            { "ricochet",           "Bullets lose half of their speed when they bounce." },
            { "saw",                "Blocking spawns a saw around you for a short while." },
            { "scavenger",          "Dealing damage reloads your weapon." },
            { "shieldcharge",       "Blocking launches you forward and gives you a second automatic block upon ending the charge." },
            { "shieldsup",          "Firing your last bullet triggers a block. Disables continuous reloading." },
            { "shockwave",          "Blocking pushes enemies away." },
            { "silence",            "Blocking silences enemies nearby." },
            { "sneaky",             "Bullets avoid the ground." },
            { "staticfield",        "Blocking creates a field that slows and deals damage." },
            { "supernova",          "Spawns a field that pulls enemies in and stuns after a while." },
            { "tacticalreload",     "Blocking reloads your weapon." },
            { "targetbounce",       "Bullets aim for visible targets when bouncing." },
            { "tasteofblood",       "+50% movement speed for 3s after dealing damage." },
            { "teleport",           "Blocking teleports you forward." },
            { "thruster",           "Bullets have thrusters that push targets." },
            { "timeddetonation",    "Bullets spawn bombs that explode after half a second." },
            { "toxiccloud",         "Bullets spawn a poison cloud on impact. Clouds deal damage and slow." },
            { "trickster",          "Bullets deal 80% more DMG per bounce (capped to your bounce count)." },
            // Cards whose Description column was N/A on the wiki — keep these
            // out of the fallback so the stat block alone shows. Listed for
            // reference: bouncy, careful planning, cold bullets, combine,
            // defender, fastball, glass cannon, huge, leech, mayhem,
            // quick reload, quick shot, spray, steady shot, tank, wind up.
        };

        // Static stat-block fallback for cards where reflection couldn't pull
        // the CardInfoStat[] (some cards bake their stats into the prefab in
        // a way our Resources scan misses). Sourced from the user-provided
        // 67-card list. Keys are space-stripped lowercase. Each entry:
        // (positive: bool, amount: string, stat: string).
        private struct CardStatTuple { public bool positive; public string amount; public string stat; }
        private static readonly Dictionary<string, CardStatTuple[]> CARD_STATS_FALLBACK = new Dictionary<string, CardStatTuple[]>(StringComparer.OrdinalIgnoreCase)
        {
            { "barrage",         new[] { CST(true,"+4","BULLETS"), CST(true,"+5","AMMO"), CST(false,"-70%","DAMAGE"), CST(false,"+0.25s","RELOAD") } },
            { "bigbullet",       new[] { CST(false,"+0.25s","RELOAD") } },
            { "bigbullets",      new[] { CST(false,"+0.25s","RELOAD") } },
            { "bombsaway",       new[] { CST(true,"+30%","HP"), CST(false,"+0.25s","BLOCK CD") } },
            { "bouncy",          new[] { CST(true,"+2","BULLET BOUNCES"), CST(true,"+25%","DAMAGE"), CST(false,"+0.25s","RELOAD") } },
            { "buckshot",        new[] { CST(true,"+4","BULLETS"), CST(true,"+5","AMMO"), CST(false,"-60%","DAMAGE"), CST(false,"+0.25s","RELOAD") } },
            { "burst",           new[] { CST(true,"+2","BULLETS"), CST(true,"+3","AMMO"), CST(false,"-60%","DAMAGE"), CST(false,"+0.25s","RELOAD") } },
            { "carefulplanning", new[] { CST(true,"+100%","DAMAGE"), CST(false,"-150%","ATKSPD"), CST(false,"+0.5s","RELOAD") } },
            { "chase",           new[] { CST(true,"+30%","HEALTH") } },
            { "chillingpresence",new[] { CST(true,"+25%","HP") } },
            { "coldbullets",     new[] { CST(true,"+70%","BULLET SLOW"), CST(false,"+0.25s","RELOAD") } },
            { "combine",         new[] { CST(true,"+100%","DAMAGE"), CST(false,"-2","AMMO"), CST(false,"+0.5s","RELOAD") } },
            { "dazzle",          new[] { CST(false,"+0.25s","RELOAD") } },
            { "decay",           new[] { CST(true,"+50%","HP") } },
            { "defender",        new[] { CST(true,"-30%","BLOCK CD"), CST(true,"+30%","HP") } },
            { "demonicpact",     new[] { CST(true,"+9","BULLETS"), CST(true,"+2","SPLASH DMG"), CST(false,"+0.25s","RELOAD") } },
            { "drillammo",       new[] { CST(true,"+7m","DRILL"), CST(false,"+0.25s","RELOAD") } },
            { "echo",            new[] { CST(true,"+30%","HP"), CST(false,"+0.25s","BLOCK CD") } },
            { "emp",             new[] { CST(true,"+30%","HP"), CST(false,"+0.25s","BLOCK CD") } },
            { "empower",         new[] { CST(false,"+0.25s","BLOCK CD") } },
            { "explosivebullet", new[] { CST(false,"-100%","ATKSPD"), CST(false,"+0.25s","RELOAD") } },
            { "fastball",        new[] { CST(true,"+250%","BULLET SPEED"), CST(false,"-50%","ATKSPD"), CST(false,"+0.25s","RELOAD") } },
            { "fastforward",     new[] { CST(true,"+100%","PROJ SPEED"), CST(true,"+30%","RELOAD SPD") } },
            { "frostslam",       new[] { CST(true,"+30%","HP"), CST(false,"+0.25s","BLOCK CD") } },
            { "glasscannon",     new[] { CST(true,"+100%","DAMAGE"), CST(false,"-100%","HP"), CST(false,"+0.25s","RELOAD") } },
            { "grow",            new[] { CST(false,"+0.25s","RELOAD") } },
            { "healingfield",    new[] { CST(true,"+30%","HP"), CST(false,"+0.25s","BLOCK CD") } },
            { "homing",          new[] { CST(false,"-25%","DAMAGE"), CST(false,"-50%","ATKSPD"), CST(false,"+0.25s","RELOAD") } },
            { "huge",            new[] { CST(true,"+80%","HP") } },
            { "implode",         new[] { CST(true,"+50%","HP"), CST(false,"+0.25s","BLOCK CD") } },
            { "leech",           new[] { CST(true,"+75%","LIFE STEAL"), CST(true,"+30%","HP") } },
            { "lifestealer",     new[] { CST(true,"+25%","HP") } },
            { "mayhem",          new[] { CST(true,"+5","BULLET BOUNCES"), CST(false,"-15%","DAMAGE"), CST(false,"+0.5s","RELOAD") } },
            { "overpower",       new[] { CST(true,"+30%","HP"), CST(false,"+0.25s","BLOCK CD") } },
            { "parasite",        new[] { CST(true,"+50%","LIFE STEAL"), CST(true,"+25%","HP"), CST(true,"+25%","DAMAGE"), CST(false,"+0.25s","RELOAD") } },
            { "phoenix",         new[] { CST(false,"-35%","HP") } },
            { "poison",          new[] { CST(true,"+70%","DAMAGE"), CST(true,"+30%","RELOAD SPD"), CST(false,"-1","BULLET") } },
            { "quickreload",     new[] { CST(true,"-70%","RELOAD") } },
            { "quickshot",       new[] { CST(true,"+150%","BULLET SPEED"), CST(false,"+0.25s","RELOAD") } },
            { "radarshot",       new[] { CST(true,"+30%","HP"), CST(false,"+0.25s","BLOCK CD") } },
            { "radiance",        new[] { CST(true,"+30%","HP") } },
            { "remote",          new[] { CST(false,"-40%","BULLET SPEED"), CST(false,"+0.25s","RELOAD") } },
            { "ricochet",        new[] { CST(true,"+2","BULLET BOUNCES"), CST(true,"+25%","ATKSPD"), CST(false,"+0.25s","RELOAD") } },
            { "riccochet",       new[] { CST(true,"+2","BULLET BOUNCES"), CST(true,"+25%","ATKSPD"), CST(false,"+0.25s","RELOAD") } },
            { "saw",             new[] { CST(true,"+30%","HP"), CST(false,"+0.25s","BLOCK CD") } },
            { "scavenger",       new[] { CST(false,"+0.5s","RELOAD") } },
            { "shieldcharge",    new[] { CST(false,"+0.25s","BLOCK CD") } },
            { "shieldsup",       new[] { CST(false,"+0.5s","RELOAD"), CST(false,"+0.5s","BLOCK CD") } },
            { "shockwave",       new[] { CST(true,"+50%","HP"), CST(false,"+0.25s","BLOCK CD") } },
            { "silence",         new[] { CST(true,"+25%","HP"), CST(false,"+0.25s","BLOCK CD") } },
            { "sneaky",          new[] { CST(false,"+0.25s","RELOAD") } },
            { "spray",           new[] { CST(true,"+1000%","ATKSPD"), CST(true,"+12","AMMO"), CST(false,"-75%","DAMAGE"), CST(false,"+0.25s","RELOAD") } },
            { "staticfield",     new[] { CST(false,"+0.25s","BLOCK CD") } },
            { "steadyshot",      new[] { CST(true,"+40%","HP"), CST(true,"+100%","BULLET SPEED"), CST(false,"+0.25s","RELOAD") } },
            { "supernova",       new[] { CST(true,"+50%","HP"), CST(false,"+0.5s","BLOCK CD") } },
            { "tacticalreload",  new[] { CST(false,"+0.25s","BLOCK CD") } },
            { "tank",            new[] { CST(true,"+100%","HP"), CST(false,"-25%","ATKSPD"), CST(false,"+0.5s","RELOAD") } },
            { "targetbounce",    new[] { CST(true,"+1","BULLET BOUNCE"), CST(false,"-20%","DAMAGE"), CST(false,"+0.25s","RELOAD") } },
            { "tasteofblood",    new[] { CST(true,"+30%","LIFE STEAL") } },
            { "teleport",        new[] { CST(true,"-30%","BLOCK CD") } },
            { "thruster",        new[] { CST(false,"+0.25s","RELOAD") } },
            { "timeddetonation", new[] { CST(false,"-15%","DAMAGE"), CST(false,"+0.25s","RELOAD") } },
            { "toxiccloud",      new[] { CST(false,"-20%","ATKSPD"), CST(false,"+0.5s","RELOAD") } },
            { "trickster",       new[] { CST(true,"+2","BULLET BOUNCES"), CST(false,"-20%","DAMAGE"), CST(false,"+0.5s","RELOAD") } },
            { "windup",          new[] { CST(true,"+100%","BULLET SPEED"), CST(true,"+60%","DAMAGE"), CST(false,"-100%","ATKSPD"), CST(false,"+0.5s","RELOAD") } },
        };
        private static CardStatTuple CST(bool p, string a, string s) => new CardStatTuple { positive = p, amount = a, stat = s };

        // Normalize stat labels so the image / popup don't mix "DMG" + "DAMAGE",
        // "ATKSPD" + "ATTACK SPEED", etc. Picks the SHORTER variant since cell
        // space is limited.
        private static string NormalizeStatLabel(string raw)
        {
            if (string.IsNullOrEmpty(raw)) return raw;
            string s = raw.Trim().ToUpperInvariant();
            // Strip a trailing colon some prefab labels include.
            if (s.EndsWith(":")) s = s.Substring(0, s.Length - 1).TrimEnd();
            switch (s)
            {
                case "DAMAGE": case "DMG": case "DAMAGE:": return "DMG";
                case "ATTACK SPEED": case "ATKSPD": case "ATK SPEED": case "ATK SPD": return "ATK SPD";
                case "BULLET SPEED": case "BULLET SPD": case "PROJ SPEED": case "PROJECTILE SPEED": return "BULLET SPD";
                case "RELOAD": case "RELOAD TIME": case "RELOAD SPEED": case "RELOAD SPD": return "RELOAD";
                case "BLOCK CD": case "BLOCK COOLDOWN": case "BLOCK COOLDOWN TIME": return "BLOCK CD";
                case "HP": case "HEALTH": return "HP";
                case "AMMO": case "MAGAZINE": case "MAG": return "AMMO";
                case "BULLETS": case "BULLET COUNT": return "BULLETS";
                case "BULLET": case "BULLET LOSS": return "BULLET";
                case "LIFESTEAL": case "LIFE STEAL": return "LIFESTEAL";
                case "BULLET BOUNCES": case "BOUNCES": return "BULLET BOUNCES";
                case "BULLET BOUNCE": case "BOUNCE": return "BULLET BOUNCE";
                case "BULLET SLOW": return "BULLET SLOW";
                case "DRILL": case "WALL DRILL": case "DRILL THROUGH WALLS": return "DRILL";
                case "SPLASH DMG": case "SPLASH DAMAGE": return "SPLASH DMG";
            }
            return s;
        }

        // Build a stat block string from the fallback tuples for a given card.
        // Returns "" if the canonical name isn't in the dict.
        private static string BuildStatBlockFromFallback(string cardName, int max)
        {
            if (string.IsNullOrEmpty(cardName)) return "";
            string canonical = CardRarityLookup.GetCanonicalName(cardName) ?? cardName;
            string[] keys = new[] { (canonical ?? "").ToLowerInvariant().Replace(" ", ""),
                                    (cardName  ?? "").ToLowerInvariant().Replace(" ", "") };
            CardStatTuple[] arr = null;
            foreach (var k in keys) { if (!string.IsNullOrEmpty(k) && CARD_STATS_FALLBACK.TryGetValue(k, out arr)) break; }
            if (arr == null || arr.Length == 0) return "";
            var sb = new StringBuilder();
            int shown = 0;
            for (int i = 0; i < arr.Length && shown < max; i++)
            {
                var t = arr[i];
                string col = t.positive ? "#88FF88" : "#FF8888";
                if (sb.Length > 0) sb.Append("\n");
                sb.Append("<color=").Append(col).Append("><b>").Append(t.amount).Append("</b></color> ").Append(t.stat);
                shown++;
            }
            return sb.ToString();
        }

        // ── Card preview popup ─────────────────────────────────
        // Text-based modal showing the card's name + rarity + description +
        // stat block (numerical buffs/debuffs reflected off CardInfo). The
        // earlier prefab-clone approach left the screen grey because vanilla
        // CardInfo prefabs render in world space, not under our screen-space
        // overlay canvas. Text rendering avoids that rabbit hole entirely.
        private static GameObject cardPreviewGO;
        public static void ShowCardPreview(string cardName)
        {
            if (string.IsNullOrEmpty(cardName)) return;
            HideCardPreview();
            try
            {
                Component ci = null;
                string realName = cardName, rarity = "Unknown", description = "";
                Array statsList = null;
                // Resolve CardInfo by name. Try CardChoice.instance.cards FIRST
                // (always-loaded global registry; covers most cards including
                // ones renamed since release). Fall back to
                // Resources.FindObjectsOfTypeAll<CardInfo> if the global list
                // doesn't have it (some mod cards may not be registered there).
                // Match against (a) the canonical name from CardRarityLookup,
                // (b) GO name (clone-suffix stripped), (c) cardName field —
                // all case-insensitive + space-stripped.
                string lcTarget = (cardName ?? "").ToLowerInvariant().Replace(" ", "");
                string canonical = CardRarityLookup.GetCanonicalName(cardName) ?? cardName;
                string lcCanonical = canonical.ToLowerInvariant().Replace(" ", "");
                bool Matches(string s)
                {
                    if (string.IsNullOrEmpty(s)) return false;
                    string lc = s.ToLowerInvariant().Replace(" ", "");
                    return lc == lcTarget || lc == lcCanonical;
                }
                Component MatchInArray(IEnumerable arr)
                {
                    if (arr == null) return null;
                    foreach (var c in arr)
                    {
                        var comp = c as Component;
                        if (comp == null) continue;
                        string goName = comp.gameObject.name?.Replace("(Clone)", "").Trim() ?? "";
                        string display = comp.GetType().GetField("cardName", BindingFlags.Public | BindingFlags.Instance)?.GetValue(comp) as string ?? "";
                        if (Matches(goName) || Matches(display)) return comp;
                    }
                    return null;
                }
                try
                {
                    // Path 1: CardChoice.instance.cards
                    var ccType = AppDomain.CurrentDomain.GetAssemblies()
                        .Select(a => a.GetType("CardChoice")).FirstOrDefault(t => t != null);
                    if (ccType != null)
                    {
                        object cc = ccType.GetField("instance", BindingFlags.Public | BindingFlags.Static)?.GetValue(null);
                        var cardsArr = ccType.GetField("cards", BindingFlags.Public | BindingFlags.Instance)?.GetValue(cc) as Array;
                        ci = MatchInArray(cardsArr);
                    }
                    // Path 2: Resources fallback
                    if (ci == null)
                    {
                        var allCards = Resources.FindObjectsOfTypeAll<CardInfo>();
                        ci = MatchInArray(allCards);
                    }
                    if (ci == null)
                        Plugin.Log.LogInfo($"[CARD-PREVIEW] CardInfo not found for '{cardName}' (canonical='{canonical}') — falling back to dict");
                }
                catch (Exception sx) { Plugin.Log.LogWarning($"[CARD-PREVIEW] lookup: {sx.Message}"); }
                if (ci != null)
                {
                    var ciT = ci.GetType();
                    var nField = ciT.GetField("cardName", BindingFlags.Public | BindingFlags.Instance);
                    var rField = ciT.GetField("rarity", BindingFlags.Public | BindingFlags.Instance);
                    // Vanilla typoed `cardDestription` for years; current builds
                    // also have `cardDescription` and a few more fields. Try
                    // each in priority order.
                    var dField = ciT.GetField("cardDestription", BindingFlags.Public | BindingFlags.Instance)
                              ?? ciT.GetField("cardDescription", BindingFlags.Public | BindingFlags.Instance)
                              ?? ciT.GetField("description", BindingFlags.Public | BindingFlags.Instance);
                    // CardInfoStat is [Serializable] but NOT a Component, so the
                    // earlier Component[] cast returned null and the popup never
                    // rendered the stat block. Read as Array (object[]) and
                    // reflect each element's fields.
                    var sField = ciT.GetField("cardStats", BindingFlags.Public | BindingFlags.Instance)
                              ?? ciT.GetField("stats", BindingFlags.Public | BindingFlags.Instance);
                    realName = (nField?.GetValue(ci) as string) ?? cardName;
                    var rv = rField?.GetValue(ci); rarity = rv != null ? rv.ToString() : "Unknown";
                    description = (dField?.GetValue(ci) as string) ?? "";
                    statsList = sField?.GetValue(ci) as Array;

                    // Hardcoded fallback dictionary — covers cards whose
                    // description lives outside CardInfo (poison/leech/quick
                    // reload/remote, etc). Source: ROUNDS wiki + community
                    // knowledge. Keyed by canonical name lowercased + spaces
                    // stripped so "Quick Reload" and "QuickReload" both hit.
                    if (string.IsNullOrEmpty(description))
                    {
                        string fbKey = (canonical ?? cardName ?? "").ToLowerInvariant().Replace(" ", "");
                        if (!string.IsNullOrEmpty(fbKey) && CARD_DESC_FALLBACK.TryGetValue(fbKey, out var fbDesc))
                            description = fbDesc;
                    }
                    // Fallback: if the card's mechanic text lives only in the
                    // prefab's UI hierarchy (some cards have an empty
                    // cardDestription field but show description text via a
                    // baked-in TMP component), scan children for any
                    // non-trivial text and use that as a secondary description.
                    if (string.IsNullOrEmpty(description))
                    {
                        try
                        {
                            string lcReal = (realName ?? "").ToLowerInvariant().Replace(" ", "");
                            string lcRare = (rarity ?? "").ToLowerInvariant();
                            var sb = new StringBuilder();
                            // TMPro types are loaded by ROUNDS — find by name.
                            Type tmpType = null;
                            foreach (var asm in AppDomain.CurrentDomain.GetAssemblies())
                            {
                                tmpType = asm.GetType("TMPro.TMP_Text") ?? asm.GetType("TMPro.TextMeshProUGUI");
                                if (tmpType != null) break;
                            }
                            if (tmpType != null)
                            {
                                var textProp = tmpType.GetProperty("text", BindingFlags.Public | BindingFlags.Instance);
                                var components = ci.gameObject.GetComponentsInChildren(tmpType, true);
                                foreach (var t in components)
                                {
                                    if (t == null || textProp == null) continue;
                                    string s = textProp.GetValue(t) as string ?? "";
                                    s = s.Trim();
                                    if (string.IsNullOrEmpty(s)) continue;
                                    string lc = s.ToLowerInvariant().Replace(" ", "");
                                    if (lc == lcReal || lc == lcRare) continue;
                                    if (s.Length < 4 || s.Length > 200) continue;
                                    if (sb.Length > 0) sb.Append("\n");
                                    sb.Append(s);
                                    if (sb.Length > 240) break;
                                }
                            }
                            if (sb.Length > 0) description = sb.ToString();
                        }
                        catch { }
                    }
                }

                // Final fallback if BOTH the CardInfo lookup failed AND the
                // hardcoded dict didn't fire inside the ci-null branch above:
                // try the dict here too so the popup always tries every source.
                if (string.IsNullOrEmpty(description))
                {
                    string fbKey = (canonical ?? cardName ?? "").ToLowerInvariant().Replace(" ", "");
                    if (!string.IsNullOrEmpty(fbKey) && CARD_DESC_FALLBACK.TryGetValue(fbKey, out var fbDesc))
                        description = fbDesc;
                }

                EnsureOverlayCanvas();
                cardPreviewGO = new GameObject("CR_CardPreview");
                cardPreviewGO.hideFlags = HideFlags.HideAndDontSave;
                cardPreviewGO.transform.SetParent(overlayCanvasGO.transform, false);
                var prRT = cardPreviewGO.AddComponent<RectTransform>();
                prRT.anchorMin = Vector2.zero; prRT.anchorMax = Vector2.one;
                prRT.offsetMin = Vector2.zero; prRT.offsetMax = Vector2.zero;
                // Backdrop (click to dismiss) — keep alpha low so the F5 menu
                // behind stays visible. Earlier 0.55 alpha + grey result was
                // because the prefab clone rendered behind the alpha layer.
                var bd = UIFactory.CreatePanel("BD", cardPreviewGO.transform, new Color(0f, 0f, 0f, 0.45f));
                var bdRT = bd.GetComponent<RectTransform>();
                bdRT.anchorMin = Vector2.zero; bdRT.anchorMax = Vector2.one;
                bdRT.offsetMin = Vector2.zero; bdRT.offsetMax = Vector2.zero;
                var bdImg = bd.GetComponent(UIFactory.tImage);
                if (bdImg != null) UIFactory.tImage.GetProperty("raycastTarget", BindingFlags.Public | BindingFlags.Instance)?.SetValue(bdImg, true);
                var bdClick = bd.AddComponent<ClickHandler>();
                bdClick.onClick = () => { if (ClickGuard.Claim()) HideCardPreview(); };

                // Image-first popup: if we have card art on disk, show
                // the image as the popup body. The art already contains
                // the card's name + description + stats baked in, so we
                // skip the text rendering paths entirely.
                Sprite cardSprite = CardImageLoader.GetSprite(cardName);

                // Centered card panel.
                var card = UIFactory.CreatePanel("Card", cardPreviewGO.transform, new Color(0.10f, 0.12f, 0.16f, 0.97f));
                var cardRT = card.GetComponent<RectTransform>();
                cardRT.anchorMin = new Vector2(0.5f, 0.5f);
                cardRT.anchorMax = new Vector2(0.5f, 0.5f);
                cardRT.pivot = new Vector2(0.5f, 0.5f);

                if (cardSprite != null)
                {
                    // 360 wide × 540 tall image at native ~2:3 ratio,
                    // plus a 24px hint row underneath.
                    cardRT.sizeDelta = new Vector2(380, 600);
                    UIFactory.AddVLG(card, spacing: 6, padL: 10, padR: 10, padT: 10, padB: 10);

                    var imgGO = new GameObject("CardImg");
                    imgGO.transform.SetParent(card.transform, false);
                    imgGO.AddComponent<RectTransform>();
                    var imgComp = imgGO.AddComponent(UIFactory.tImage);
                    var pSprite = UIFactory.tImage.GetProperty("sprite", BindingFlags.Public | BindingFlags.Instance);
                    var pPreserve = UIFactory.tImage.GetProperty("preserveAspect", BindingFlags.Public | BindingFlags.Instance);
                    var pColor = UIFactory.tImage.GetProperty("color", BindingFlags.Public | BindingFlags.Instance);
                    pSprite?.SetValue(imgComp, cardSprite);
                    pPreserve?.SetValue(imgComp, true);
                    pColor?.SetValue(imgComp, Color.white);
                    UIFactory.AddLE(imgGO, prefW: 360, minW: 360, prefH: 545, minH: 545, flexH: 0, flexW: 0);

                    UIFactory.CreateText("CPHint", card.transform, "<color=#888>click anywhere to close</color>",
                        13f, C_DIM, UIFactory.AlignMidCenter, sizeDelta: new Vector2(360, 20));

                    Plugin.Log.LogInfo($"[CARD-PREVIEW] showing image for '{realName}'");
                }
                else
                {
                    // Fallback text-only layout for cards with no art on
                    // disk. Existing code path preserved.
                    cardRT.sizeDelta = new Vector2(440, 360);
                    UIFactory.AddVLG(card, spacing: 6, padL: 18, padR: 18, padT: 14, padB: 14);

                    UIFactory.CreateText("CPName", card.transform, $"<b>{realName}</b>",
                        24f, C_WHITE, UIFactory.AlignMidCenter, sizeDelta: new Vector2(400, 32));
                    Color rColor = GetRarityColor(rarity);
                    UIFactory.CreateText("CPRar", card.transform, rarity ?? "Unknown",
                        16f, rColor, UIFactory.AlignMidCenter, sizeDelta: new Vector2(400, 22));

                    if (!string.IsNullOrEmpty(description))
                    {
                        var dt = UIFactory.CreateText("CPDesc", card.transform, $"<i>{description}</i>",
                            15f, new Color(0.85f, 0.88f, 0.95f), UIFactory.AlignMidCenter,
                            sizeDelta: new Vector2(400, 60));
                        UIFactory.SetWordWrap(dt, true);
                    }

                    string fallbackStatText = null;
                    if (statsList == null || statsList.Length == 0)
                        fallbackStatText = BuildStatBlockFromFallback(cardName, 8);
                    if (!string.IsNullOrEmpty(fallbackStatText))
                    {
                        var stTxt = UIFactory.CreateText("CPStats", card.transform, fallbackStatText,
                            15f, C_LABEL, UIFactory.AlignTopLeft, sizeDelta: new Vector2(400, 160));
                        UIFactory.SetWordWrap(stTxt, true);
                    }
                    else if (statsList != null && statsList.Length > 0)
                    {
                        var sb = new StringBuilder();
                        for (int i = 0; i < statsList.Length; i++)
                        {
                            var s = statsList.GetValue(i);
                            if (s == null) continue;
                            var st = s.GetType();
                            string statName = st.GetField("stat", BindingFlags.Public | BindingFlags.Instance)?.GetValue(s) as string ?? "";
                            string amount = st.GetField("amount", BindingFlags.Public | BindingFlags.Instance)?.GetValue(s) as string ?? "";
                            var posObj = st.GetField("positive", BindingFlags.Public | BindingFlags.Instance)?.GetValue(s);
                            bool positive = posObj is bool pb ? pb : true;
                            if (string.IsNullOrEmpty(statName) && string.IsNullOrEmpty(amount)) continue;
                            string color = positive ? "#88FF88" : "#FF6666";
                            sb.Append("  <color=").Append(color).Append("><b>").Append(amount).Append("</b></color>  ").Append(NormalizeStatLabel(statName)).Append("\n");
                        }
                        string statBlock = sb.ToString().TrimEnd('\n');
                        if (!string.IsNullOrEmpty(statBlock))
                        {
                            var stTxt = UIFactory.CreateText("CPStats", card.transform, statBlock,
                                15f, C_LABEL, UIFactory.AlignTopLeft, sizeDelta: new Vector2(400, 160));
                            UIFactory.SetWordWrap(stTxt, true);
                        }
                        else
                        {
                            UIFactory.CreateText("CPStatsEmpty", card.transform,
                                "<color=#888><i>(Mechanic isn't expressed as numerical stats — check the card description above or pick it in-game.)</i></color>",
                                13f, C_DIM, UIFactory.AlignMidCenter, sizeDelta: new Vector2(400, 60));
                        }
                    }
                    else
                    {
                        UIFactory.CreateText("CPNoStats", card.transform,
                            "<color=#888><i>No stat data available for this card.</i></color>",
                            13f, C_DIM, UIFactory.AlignMidCenter, sizeDelta: new Vector2(400, 28));
                    }

                    UIFactory.CreateText("CPHint", card.transform, "<color=#888>click anywhere to close</color>",
                        13f, C_DIM, UIFactory.AlignMidCenter, sizeDelta: new Vector2(400, 18));
                    Plugin.Log.LogInfo($"[CARD-PREVIEW] showing text fallback for '{realName}' (rarity={rarity})");
                }
            }
            catch (Exception ex) { Plugin.Log.LogWarning($"[CARD-PREVIEW] failed: {ex.Message}"); }
        }

        public static void HideCardPreview()
        {
            try
            {
                if (cardPreviewGO != null)
                {
                    UnityEngine.Object.Destroy(cardPreviewGO);
                    cardPreviewGO = null;
                }
            }
            catch (Exception ex) { Plugin.Log.LogWarning($"[CARD-PREVIEW] destroy: {ex.Message}"); }
        }

        // Load the player's saved tiers for the active filter, repopulate
        // cardTierMap, mark dirty so the rows re-render.
        public static void LoadCardTiersForCurrentFilter()
        {
            string filterStr = cardFilter == 1 ? "ranked" : cardFilter == 2 ? "casual" : "all";
            int filterIdx = cardFilter;
            ApiClient.FetchCardTiers(MatchTracker.LocalSteamId, filterStr, (loaded) =>
            {
                // Drop the existing entries for this filter, replace with loaded.
                var keep = new Dictionary<string, string>();
                foreach (var kv in cardTierMap)
                {
                    if (!kv.Key.StartsWith($"{filterIdx}|")) keep[kv.Key] = kv.Value;
                }
                cardTierMap = keep;
                foreach (var kv in loaded)
                {
                    cardTierMap[CardTierKey(filterIdx, kv.Key)] = kv.Value;
                }
                dirty = true;
            });
        }

        // Cycle one card's tier and write through to the server. Filter is
        // tied to the current cardFilter index (0=All,1=Ranked,2=Casual).
        // -- Achievements Tab ------------------------------------
        private static GameObject BuildAchievementsTab(Transform parent){var panel=new GameObject("Achievements");panel.transform.SetParent(parent,false);panel.AddComponent<RectTransform>();UIFactory.AddVLG(panel,spacing:6,padL:20,padR:20,padT:10);UIFactory.AddLE(panel,flexH:1);UIFactory.CreateText("AchH",panel.transform,"Achievements",22f,C_GOLD,UIFactory.AlignTopCenter,sizeDelta:new Vector2(600,30));var countRow=new GameObject("AchCnt");countRow.transform.SetParent(panel.transform,false);countRow.AddComponent<RectTransform>();UIFactory.AddLE(countRow,prefH:22);txtAchCount=UIFactory.CreateText("AC",countRow.transform,"",15f,C_DIM,UIFactory.AlignMidCenter,sizeDelta:new Vector2(400,22));var sv=UIFactory.CreateScrollView("AchSV",panel.transform,spacing:4);UIFactory.AddLE(sv.scrollGO,flexH:1);achRows.Clear();foreach(var kvp in ApiClient.AchievementDefs){var row=new AchRow();string key=kvp.Key;string[]def=kvp.Value;row.root=new GameObject($"ach_{key}");row.root.transform.SetParent(sv.content.transform,false);row.root.AddComponent<RectTransform>();UIFactory.AddHLG(row.root,spacing:10,padL:8,padR:8,padT:6,padB:6,forceExpandH:true);UIFactory.AddLE(row.root,prefH:50);if(UIFactory.tImage!=null){var img=row.root.AddComponent(UIFactory.tImage);UIFactory.tImage.GetProperty("color",BindingFlags.Public|BindingFlags.Instance)?.SetValue(img,C_PANEL);}row.txtIcon=UIFactory.CreateText("ic",row.root.transform,"",24f,C_DIM,UIFactory.AlignMidCenter,sizeDelta:new Vector2(36,40));var infoCol=new GameObject("Info");infoCol.transform.SetParent(row.root.transform,false);infoCol.AddComponent<RectTransform>();UIFactory.AddVLG(infoCol,spacing:1);UIFactory.AddLE(infoCol,flexW:1);row.txtName=UIFactory.CreateText("nm",infoCol.transform,def[0],17f,C_WHITE,UIFactory.AlignMidLeft,sizeDelta:new Vector2(500,22));row.txtDesc=UIFactory.CreateText("ds",infoCol.transform,def[1],14f,C_LABEL,UIFactory.AlignMidLeft,sizeDelta:new Vector2(500,20));row.txtDate=UIFactory.CreateText("dt",row.root.transform,"",13f,C_DIM,UIFactory.AlignMidRight,sizeDelta:new Vector2(180,40));row.root.SetActive(true);achRows.Add(row);}return panel;}

        private static object txtAchCount;
        private static void RefreshAchievements(){var ach=ApiClient.CachedAchievements;int unlocked=0,total=ApiClient.AchievementDefs.Count;int i=0;foreach(var kvp in ApiClient.AchievementDefs){if(i>=achRows.Count)break;var row=achRows[i];bool got=ach!=null&&ach.ContainsKey(kvp.Key)&&ach[kvp.Key].unlocked;if(got)unlocked++;UIFactory.SetText(row.txtIcon,got?"[X]":"[ ]");UIFactory.SetColor(row.txtIcon,got?C_GOLD:new Color(0.3f,0.3f,0.35f));UIFactory.SetColor(row.txtName,got?C_WHITE:C_DIM);UIFactory.SetColor(row.txtDesc,got?C_LABEL:new Color(0.4f,0.4f,0.45f));string dt="";if(got&&ach!=null&&ach.ContainsKey(kvp.Key)){string ua=ach[kvp.Key].unlocked_at;if(!string.IsNullOrEmpty(ua)&&ua!="null"){try{dt=DateTime.Parse(ua).ToString("M/d/yyyy");}catch{}}}/* Append "+100g" gold-awarded tag inline with the date so users see the per-trophy reward without opening the gold ledger. Per-achievement gold is uniform (ACHIEVEMENT_GOLD on the server, currently 100). */if(got&&!string.IsNullOrEmpty(dt))dt=$"{dt}  <color=#FFD94D>+100g</color>";UIFactory.SetText(row.txtDate,dt);UIFactory.SetColor(row.txtDate,got?C_GREEN:C_DIM);i++;}UIFactory.SetText(txtAchCount,$"{unlocked} / {total} unlocked");UIFactory.SetColor(txtAchCount,unlocked==total?C_GOLD:C_LABEL);}

        private static void RefreshData(){string id=MatchTracker.LocalSteamId;if(!string.IsNullOrEmpty(id)&&id!="unknown"){ApiClient.FetchPlayerStats(id);ApiClient.FetchMatchHistory(id);ApiClient.FetchAchievements(id);ApiClient.FetchTeamStats(id);}if(currentTab==1){ApiClient.FetchLeaderboard();ApiClient.FetchRecentSeries();}if(currentTab==2){ApiClient.FetchCardStats(200,MatchTracker.LocalSteamId);LoadCardTiersForCurrentFilter();}}
        private static void RefreshCurrentTab(){RefreshQueueUI();RefreshVersionStatus();RefreshServerBanner();RefreshTournamentGameIndicator();/* Admin tab button visibility - IsAdmin can flip on after the async check completes. */if(tabButtons!=null&&tabButtons.Length>=7&&tabButtons[6]!=null)tabButtons[6].SetActive(ApiClient.IsAdmin);switch(currentTab){case 0:RefreshMyStats();break;case 1:RefreshLeaderboard();RefreshRecentSeries();RefreshLiveSeries();break;case 2:RefreshCardStats();break;case 3:RefreshAchievements();break;case 4:RefreshShop();break;case 5:RefreshSettings();break;case 6:RefreshAdmin();break;case 7:RefreshTournaments();break;case 8:RefreshTeamTab();break;}}

        // Match IDs for which we've already auto-enabled ranked. Prevents the
        // every-refresh toggle from re-firing and re-posting /toggle-ranked
        // each tick while in a tournament match.
        private static HashSet<string> _autoEnabledRankedForMatches = new HashSet<string>();

        private static void _EnsureRankedEnabledForTournamentMatch(ApiClient.ActiveTournamentMatch m)
        {
            if (m == null || string.IsNullOrEmpty(m.match_id)) return;
            if (_autoEnabledRankedForMatches.Contains(m.match_id)) return;
            _autoEnabledRankedForMatches.Add(m.match_id);
            // Already on? Nothing to do, just memo.
            if (Plugin.RankedEnabled != null && Plugin.RankedEnabled.Value) return;
            // Flip config + notify server so opponentIsRanked resolves true on
            // the other side too. Identical to the Ranked ON button.
            Plugin.RankedEnabled.Value = true;
            var sid = MatchTracker.LocalSteamId;
            if (!string.IsNullOrEmpty(sid) && sid != "unknown")
                ApiClient.ToggleRanked(sid, true);
            CompetitiveUI.ShowNotification(
                "Ranked auto-enabled for your tournament match - results will auto-record",
                new Color(1f, 0.85f, 0.3f));
            Plugin.Log.LogInfo($"[TOURNAMENT] Auto-enabled Ranked for match {m.match_id}");
        }

        private static void RefreshTournamentGameIndicator()
        {
            if (tournamentIndRow == null || txtTournamentGame == null) return;
            // Fetch is rate-limited inside ApiClient (~20s). Cheap to call every refresh.
            ApiClient.FetchMyActiveTournamentMatches(MatchTracker.LocalSteamId);
            // Auto-enable ranked for each new active match we see. This runs
            // per-MATCH (not per signup) so the check happens fresh at every
            // tournament game - if a player turned ranked off between matches,
            // we flip it back on when their next match lights up.
            var activeMatches = ApiClient.CachedMyActiveTournamentMatches;
            if (activeMatches != null)
                foreach (var m in activeMatches) _EnsureRankedEnabledForTournamentMatch(m);
            // Match only fires when we're actually in a room with someone AND that
            // someone is our active tournament opponent. Avoids the false positive
            // of showing the banner just because we have a pending tournament match
            // while playing casual/ranked elsewhere.
            var matches = ApiClient.CachedMyActiveTournamentMatches;
            if (matches == null || matches.Count == 0 || !GameStateWatcher.IsInRoom)
            {
                tournamentIndRow.SetActive(false);
                return;
            }
            string oppSid = GameStateWatcher.OpponentSteamId;
            if (string.IsNullOrEmpty(oppSid) || oppSid.StartsWith("photon_"))
            {
                tournamentIndRow.SetActive(false);
                return;
            }
            foreach (var m in matches)
            {
                if (m.opponent_steam_id == oppSid)
                {
                    string kindTag = (m.kind ?? "").ToUpper();
                    UIFactory.SetText(txtTournamentGame,
                        $"<color=#FFD94D>* {kindTag} TOURNAMENT GAME - vs {m.opponent_display_name ?? "opponent"}  (results auto-recorded)</color>");
                    tournamentIndRow.SetActive(true);
                    return;
                }
            }
            tournamentIndRow.SetActive(false);
        }

        // Hide the row entirely unless the API actually looks down - see ApiClient.ApiLooksDown.
        // Fires from RefreshCurrentTab so it stays in sync with the rest of the UI.
        private static void RefreshServerBanner()
        {
            if (srvStatusRow == null) return;
            bool down = ApiClient.ApiLooksDown;
            srvStatusRow.SetActive(down);
            if (down)
            {
                string msg = ApiClient.LastResponseWasMaintenance
                    ? "<color=#FFB060>* Server in maintenance - back in a moment</color>"
                    : "<color=#FF8866>* Server reconnecting...</color>";
                UIFactory.SetText(txtServerStatus, msg);
            }
        }

        // Active-series fetch hook - fire on leaderboard tab open in SwitchTab.
        private static void RefreshLiveSeries()
        {
            if (txtLiveSeries == null) return;
            // Redraw the header each refresh with an alternating bright/dim dot color. The
            // filled/empty state is flipped in MaybeRefreshLiveSeries so it ticks exactly once
            // per real server poll. We alternate COLOR instead of glyph because the Gravity
            // SDF font ROUNDS ships with doesn't contain * (U+25CF) or ○ (U+25CB) - both
            // render as the same missing-glyph □, which masks any glyph-swap as stationary.
            // Color change applies to the dot only; the "Live Ranked Games" label stays
            // consistent so the pulse is focal, not distracting.
            if (txtLiveHeader != null)
            {
                string dotColor = liveHeaderPulseFilled ? "#FF6688" : "#552233";
                UIFactory.SetText(txtLiveHeader, $"<color={dotColor}>*</color> <color=#FF6688>Live Ranked Games</color>");
            }
            var list = ApiClient.CachedActiveSeries;
            var teamList = ApiClient.CachedActiveTeamSeries;
            int oneVOneCount = list != null ? list.Count : 0;
            int teamCount = teamList != null ? teamList.Count : 0;
            // Clear pool first, then rebuild.
            foreach (var g in liveBetRowPool) g.SetActive(false);
            if (oneVOneCount == 0 && teamCount == 0)
            {
                UIFactory.SetText(txtLiveSeries, "<color=#666><i>No live games right now.</i></color>");
                if (liveBetsPager != null) liveBetsPager.SetActive(false);
                return;
            }
            UIFactory.SetText(txtLiveSeries, "");

            int totalPages = Math.Max(1, (oneVOneCount + LIVE_SERIES_PER_PAGE - 1) / LIVE_SERIES_PER_PAGE);
            liveSeriesPage = Math.Max(0, Math.Min(liveSeriesPage, totalPages - 1));
            int start = liveSeriesPage * LIVE_SERIES_PER_PAGE;
            int end = Math.Min(start + LIVE_SERIES_PER_PAGE, oneVOneCount);

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

            // 2v2 active series — same 3-row layout (header + bet-on-team1 + bet-on-team2)
            // appended below the 1v1 list. Always render the full team list (no
            // pagination) — 2v2 volume is small.
            if (teamList != null)
            {
                foreach (var ts in teamList)
                {
                    var hdr = GetOrCreateLiveRow(poolIdx++);
                    ApplyTeamHeaderRow(hdr, ts);
                    var bT1 = GetOrCreateLiveRow(poolIdx++);
                    ApplyTeamBetRow(bT1, ts, 1);
                    var bT2 = GetOrCreateLiveRow(poolIdx++);
                    ApplyTeamBetRow(bT2, ts, 2);
                }
            }

            // Pagination controls: only visible when > one page's worth of series.
            if (liveBetsPager != null)
            {
                bool show = totalPages > 1;
                liveBetsPager.SetActive(show);
                if (show)
                {
                    UIFactory.SetText(txtLiveBetsPage, $"{oneVOneCount} live - {liveSeriesPage + 1}/{totalPages}");
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
            // disabled so a long name doesn't push elo onto a second visual line - the column is
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
            //   1. The user already bet on this series - show the bet status, hide buttons.
            //   2. Bets are locked (game past 2 points or game 1 finished) - show locked tag.
            //   3. User is a participant - "your match" tag.
            //   4. Otherwise: show the wager buttons.
            var existing = ApiClient.GetMyBetForSeries(s.series_id);

            // Wider text element + disable wrap; truncate name to 10 so "Bet on <name> @1.0x:"
            // fits even with the longest names. Was 180w with 12-char truncation -> wrapped on
            // "bobbyjoe122333" rows.
            var betLabel = UIFactory.CreateText("bl", row.transform,
                $"Bet on <b>{Trunc(name, 10)}</b> @{odds:F1}x:",
                13f, C_LABEL, UIFactory.AlignMidLeft, sizeDelta: new Vector2(220, 22));
            UIFactory.SetWordWrap(betLabel, false);

            if (existing != null)
            {
                // Only display on the "side" the user actually bet on - the other side stays
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
                        "<color=#666>-</color>",
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

        // 2v2 live-series row builders (parallel to ApplyHeaderRow / ApplyBetRow).
        private static void ApplyTeamHeaderRow(GameObject row, ApiClient.ActiveTeamSeriesEntry s)
        {
            string line = $"<color=#FFB347>2v2</color>  " +
                          $"<color=#AAF>{Trunc(s.t1a_name, 8)}+{Trunc(s.t1b_name, 8)}</color> ({s.t1_rating})  " +
                          $"<b>{s.t1_wins}-{s.t2_wins}</b>  " +
                          $"<color=#FAA>{Trunc(s.t2a_name, 8)}+{Trunc(s.t2b_name, 8)}</color> ({s.t2_rating})";
            var t = UIFactory.CreateText("hdr", row.transform, line,
                14f, C_WHITE, UIFactory.AlignMidLeft, sizeDelta: new Vector2(420, 24));
            UIFactory.SetWordWrap(t, false);
            UIFactory.SetBold(t, true);
        }

        private static void ApplyTeamBetRow(GameObject row, ApiClient.ActiveTeamSeriesEntry s, int team)
        {
            float odds = team == 1 ? s.t1_odds : s.t2_odds;
            string teamLabel = team == 1
                ? $"Team 1 ({Trunc(s.t1a_name, 6)}+{Trunc(s.t1b_name, 6)})"
                : $"Team 2 ({Trunc(s.t2a_name, 6)}+{Trunc(s.t2b_name, 6)})";

            string myId = MatchTracker.LocalSteamId;
            bool localIsParticipant = !string.IsNullOrEmpty(myId)
                && (myId == s.t1a_steam || myId == s.t1b_steam || myId == s.t2a_steam || myId == s.t2b_steam);

            var betLabel = UIFactory.CreateText("tbl", row.transform,
                $"Bet on <b>{teamLabel}</b> @{odds:F1}x:",
                13f, C_LABEL, UIFactory.AlignMidLeft, sizeDelta: new Vector2(220, 22));
            UIFactory.SetWordWrap(betLabel, false);

            if (s.bets_locked)
            {
                string lockMsg = s.lock_reason == "no_meaningful_odds"
                    ? "<color=#A07744><i>odds too uncertain</i></color>"
                    : "<color=#A07744><i>betting period over</i></color>";
                UIFactory.CreateText("tlocked", row.transform, lockMsg,
                    13f, C_DIM, UIFactory.AlignMidLeft, sizeDelta: new Vector2(220, 22));
                return;
            }
            if (localIsParticipant)
            {
                UIFactory.CreateText("tself", row.transform,
                    "<color=#AA9955><i>your match</i></color>",
                    13f, C_DIM, UIFactory.AlignMidLeft, sizeDelta: new Vector2(140, 22));
                return;
            }
            AddTeamBetButton(row.transform, s.series_id, team, 100);
            AddTeamBetButton(row.transform, s.series_id, team, 500);
            AddTeamBetButton(row.transform, s.series_id, team, 2000);
        }

        private static void AddTeamBetButton(Transform parent, string seriesId, int team, int amount)
        {
            var btn = UIFactory.CreateButton($"tb{team}_{amount}", parent,
                $"{amount}g", 11f, C_WHITE, new Color(0.35f, 0.28f, 0.1f, 0.9f),
                () =>
                {
                    string id = MatchTracker.LocalSteamId;
                    if (string.IsNullOrEmpty(id) || id == "unknown") return;
                    Plugin.Log.LogInfo($"[TEAM-BET] Placing {amount}g on team {team} (series {seriesId})");
                    ApiClient.PlaceTeamBet(id, seriesId, team, amount, (ok, resp) =>
                    {
                        var col = ok ? new Color(0.4f, 1f, 0.4f) : new Color(1f, 0.5f, 0.5f);
                        CompetitiveUI.ShowNotification(
                            ok ? $"Bet placed: {amount}g on Team {team}" : $"Bet failed: {resp}", col, 3f);
                        if (ok) { ApiClient.FetchActiveTeamSeries(); ApiClient.FetchPlayerStats(id); }
                    });
                },
                sizeDelta: new Vector2(44, 22));
            UIFactory.AddLE(btn, prefW: 44, prefH: 22, flexW: 0, flexH: 0);
        }

        private static void AddBetButton(Transform parent, string seriesId, string betOnSteamId, int amount)
        {
            // CreateButton already wraps onClick in ClickGuard.Claim() at both the Button.onClick
            // listener AND the auxiliary ClickHandler. A second Claim() inside the body always
            // returned false (the first Claim consumed the budget), so every bet click was
            // silently dropped - Sid clicked many times and only saw "[BET]" log lines never appear.
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

        // -- Shop Tab -------------------------------------------
        private static object txtShopBalance, txtShopStatus;
        private static GameObject shopRowsContainer, shopTitlesHeader, shopTrailsHeader, shopColorsHeader, shopNametagsHeader, shopPColorsHeader;
        // Shop category filter: 0=All, 1=Titles, 2=Trails, 3=Map Colors, 4=Name Styles.
        // Clicking a tab narrows the scroll view to that category so users don't have to
        // scroll through 90+ items to find one kind. Each tab has a description shown
        // under the tab bar so the category's purpose is discoverable.
        private static int shopCategoryFilter = 0;
        private static GameObject[] shopTabBtns;
        private static object[] shopTabTexts;
        private static object txtShopCategoryDesc;
        private static readonly string[] SHOP_TAB_NAMES = { "All", "Titles", "Trails", "Maps", "Name Styles", "Body Color" };
        private static readonly string[] SHOP_TAB_DESCS = {
            "All cosmetics - everything available, grouped by category.",
            "Flair text shown next to your name on the leaderboard, match history, and in chat.",
            "A glowing trail that follows your character body during combat. Only visible to modded players; the shop preview shows it following your cursor.",
            "Map color schemes. Equip as many as you like and cycle between your owned colors with Left Shift in-game.",
            "Bold, italic, underline, strikethrough, and color/size modifiers applied to your player nametag in lobbies and matches. Visible to every player, modded or not.",
            "Override the default orange/blue team color with a tint of your choice. Only visible to modded players. Premium tiers (Prismatic, Chrome) animate during combat.",
        };
        private static List<GameObject> shopRowPool = new List<GameObject>();
        // Per-row glow-preview state. NametagGlowRenderer.ApplyGlowToLabel caches the unmodified
        // material when it first swaps a label; we keep a shared cache keyed by glow sku so the
        // expensive material clone only happens once per sku regardless of how many rows reuse it.
        private static readonly Dictionary<object, Material> shopPreviewOriginalMats = new Dictionary<object, Material>();
        private static readonly Dictionary<string, Material> shopPreviewGlowMatCache = new Dictionary<string, Material>();
        // Per-row typeface-preview state - parallel to the glow state. Stores the label's
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
                "Balance: -", 18f, C_GOLD, UIFactory.AlignMidRight, sizeDelta: new Vector2(320, 30));
            UIFactory.SetBold(txtShopBalance, true);

            txtShopStatus = UIFactory.CreateText("SHStatus", panel.transform,
                "", 14f, C_LABEL, sizeDelta: new Vector2(900, 22));

            // Category tab bar - 5 buttons, filters the scroll view below.
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

            // Description of the active tab - updated on each RefreshShop.
            txtShopCategoryDesc = UIFactory.CreateText("SHDesc", panel.transform,
                SHOP_TAB_DESCS[0], 13f, C_LABEL, UIFactory.AlignMidLeft, sizeDelta: new Vector2(900, 22));

            var sv = UIFactory.CreateScrollView("SHSV", panel.transform, spacing: 4);
            UIFactory.AddLE(sv.scrollGO, flexH: 1);
            shopRowsContainer = sv.content;

            // Section headers - persistent; re-ordered in RefreshShop via SetSiblingIndex.
            shopTitlesHeader = CreateSectionHeader(shopRowsContainer.transform, "SHHT",
                "<color=#FFD94D>=  TITLES  =</color>");
            shopTrailsHeader = CreateSectionHeader(shopRowsContainer.transform, "SHHTr",
                "<color=#A0D4FF>=  TRAILS  =</color>");
            shopColorsHeader = CreateSectionHeader(shopRowsContainer.transform, "SHHC",
                "<color=#B0FFB0>=  MAP COLORS  =</color>");
            shopNametagsHeader = CreateSectionHeader(shopRowsContainer.transform, "SHHN",
                "<color=#FFB0E0>=  NAME STYLES  =</color>");
            shopPColorsHeader = CreateSectionHeader(shopRowsContainer.transform, "SHHPC",
                "<color=#FFA070>=  BODY COLORS  =</color>");

            // Pre-allocate 80 item rows; reused on refresh. v1.22.x nametag expansion pushes
            // total shop items past 65 (16 titles + 12 trails + 22 colors + 17 nametags = 67),
            // so 80 leaves comfortable headroom for more cosmetics.
            // Row pool must exceed total shop_items count or trailing items silently stop
            // rendering - users reported "maps disappearing from shop" when we passed 80.
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
                    // ClickGuard removed - server is idempotent (returns "already_owned" on dup).
                    // Fine-grained logs so we can see exactly where things die.
                    try
                    {
                        Plugin.Log.LogInfo($"[SHOP] onClick ENTRY captured={captured}");
                        var r = shopRows[captured];
                        if (r == null) { Plugin.Log.LogWarning("[SHOP] row is null"); return; }
                        Plugin.Log.LogInfo($"[SHOP] row got sku={r.sku}");
                        if (string.IsNullOrEmpty(r.sku)) { Plugin.Log.LogWarning("[SHOP] empty sku - abort"); return; }
                        string id = MatchTracker.LocalSteamId;
                        Plugin.Log.LogInfo($"[SHOP] steam id={id}");
                        if (string.IsNullOrEmpty(id) || id == "unknown") { Plugin.Log.LogWarning("[SHOP] no steam id yet - abort"); return; }
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

            // Preview button - visible on trail rows only. Spawns a cursor-following trail
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
                        dirty = true;  // refresh button label (Preview <-> Stop)
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

                        // Detect re-click of an already-equipped single-active item
                        // → unequip path. Backend's _set_active_cosmetic clears
                        // the active_*_id when item_id is None, so we send 0
                        // (translated to omitted query param in ApiClient).
                        var cached = ApiClient.CachedPlayerStats;
                        bool clickedActiveTitle = kind == "title" && cached != null && cached.active_title == itemName;
                        bool clickedActiveTrail = kind == "trail" && cached != null && cached.active_trail_sku == itemSku;
                        bool unequipping = clickedActiveTitle || clickedActiveTrail;
                        long apiItemId = unequipping ? 0L : r.itemId;

                        // Optimistic UI update - flip the cached stats IMMEDIATELY so Refresh
                        // reflects the equip without waiting for the server round-trip + FetchPlayerStats.
                        if (cached != null)
                        {
                            if (kind == "title")
                            {
                                if (clickedActiveTitle)
                                {
                                    cached.active_title = null;
                                    cached.active_title_color = null;
                                }
                                else
                                {
                                    cached.active_title = itemName;
                                    cached.active_title_color = itemColor;
                                }
                            }
                            else if (kind == "trail")
                            {
                                if (clickedActiveTrail)
                                {
                                    cached.active_trail_sku = null;
                                    cached.active_trail_color = null;
                                }
                                else
                                {
                                    cached.active_trail_sku = itemSku;
                                    cached.active_trail_color = itemColor;
                                }
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
                            else if (kind == "player_color")
                            {
                                // Single-equip; toggling re-equips the same SKU (clears via re-click).
                                bool same = cached.active_player_color_sku == itemSku;
                                cached.active_player_color_sku = same ? null : itemSku;
                                cached.active_player_color_hex = same ? null : itemColor;
                                cached.active_player_color_name = same ? null : itemName;
                            }
                            dirty = true;
                        }

                        Action<bool, string> cb = (ok, resp) =>
                        {
                            UIFactory.SetText(txtShopStatus, ok
                                ? $"<color=#88FF88>Equipped.</color>"
                                : $"<color=#FF8888>Failed: {resp}</color>");
                            dirty = true;
                            // Nametag styles change how our Photon NickName reads - republish so
                            // opponents (modded or not) see the update mid-room without needing
                            // a full reconnect.
                            if (ok && kind == "nametag") NametagStyler.PublishToPhoton();
                            // Player body color: re-publish the Photon prop so the new tint
                            // applies to in-room opponents next match without a reconnect.
                            if (ok && kind == "player_color")
                            {
                                try { PlayerColorCosmetic.PublishLocalProps(); } catch { }
                                if (GameStateWatcher.IsInMatch)
                                {
                                    try { PlayerColorCosmetic.OnMatchEnd(); PlayerColorCosmetic.OnMatchStart(); } catch { }
                                }
                            }
                        };
                        if (kind == "trail") ApiClient.SetActiveTrail(id, apiItemId, cb);
                        else if (kind == "color") ApiClient.ToggleMapColor(id, r.itemId, cb);
                        else if (kind == "nametag") ApiClient.ToggleNametagStyle(id, r.itemId, cb);
                        else if (kind == "player_color") ApiClient.SetActivePlayerColor(id, r.itemId, cb);
                        else ApiClient.SetActiveTitle(id, apiItemId, cb);
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
            // Partition + sort: titles -> trails -> colors -> nametags -> player_colors. Cheapest first within each kind.
            var titles = new List<ApiClient.ShopItemData>();
            var trails = new List<ApiClient.ShopItemData>();
            var colors = new List<ApiClient.ShopItemData>();
            var nametags = new List<ApiClient.ShopItemData>();
            var pcolors = new List<ApiClient.ShopItemData>();
            if (rawItems != null)
            {
                foreach (var it in rawItems)
                {
                    if (it.kind == "trail") trails.Add(it);
                    else if (it.kind == "color") colors.Add(it);
                    else if (it.kind == "nametag") nametags.Add(it);
                    else if (it.kind == "player_color") pcolors.Add(it);
                    else titles.Add(it);
                }
                titles.Sort((a, b) => a.price.CompareTo(b.price));
                trails.Sort((a, b) => a.price.CompareTo(b.price));
                // Colors sort: price first, then alphabetical within tier - keeps the long
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
                    // Neon items share the "color" subgroup but rank AFTER the plain
                    // colors so they cluster as a premium block at the bottom of the
                    // section instead of getting alphabetically interleaved.
                    int rank(string sku) {
                        if (sku.StartsWith("nametag_neon_", StringComparison.OrdinalIgnoreCase)) return 2;
                        string sub = NametagStyler.GetSubgroup(sku);
                        if (sub == null)   return 0;  // bold/italic/underline/strike
                        if (sub == "color") return 1;
                        if (sub == "glow")  return 3;
                        if (sub == "size")  return 4;
                        return 5;  // font
                    }
                    int r = rank(a.sku).CompareTo(rank(b.sku));
                    if (r != 0) return r;
                    // Within the neon block sort by price asc — keeps any future tier
                    // (e.g. animated rainbow at 1500g) clustered with its peers.
                    int p = a.price.CompareTo(b.price);
                    if (p != 0) return p;
                    return string.Compare(a.name, b.name, StringComparison.OrdinalIgnoreCase);
                });
                pcolors.Sort((a, b) => a.price.CompareTo(b.price));
            }
            var sorted = new List<ApiClient.ShopItemData>();
            // Apply tab filter: keep only items matching the active category. Tab 0=All
            // keeps every list; 1..5 zero out the non-matching lists so the render loop
            // skips them and their section headers hide via the if(count>0) gate below.
            switch (shopCategoryFilter)
            {
                case 1: trails.Clear(); colors.Clear(); nametags.Clear(); pcolors.Clear(); break;  // Titles only
                case 2: titles.Clear(); colors.Clear(); nametags.Clear(); pcolors.Clear(); break;  // Trails only
                case 3: titles.Clear(); trails.Clear(); nametags.Clear(); pcolors.Clear(); break;  // Maps only
                case 4: titles.Clear(); trails.Clear(); colors.Clear();   pcolors.Clear(); break;  // Name Styles only
                case 5: titles.Clear(); trails.Clear(); colors.Clear();   nametags.Clear(); break; // Body Color only
                default: break;  // 0 = All, no filter
            }

            sorted.AddRange(titles);
            sorted.AddRange(trails);
            sorted.AddRange(colors);
            sorted.AddRange(nametags);
            sorted.AddRange(pcolors);

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

            if (pcolors.Count > 0 && shopPColorsHeader != null)
            {
                shopPColorsHeader.SetActive(true);
                shopPColorsHeader.transform.SetSiblingIndex(sibling++);
            }
            else if (shopPColorsHeader != null) shopPColorsHeader.SetActive(false);
            for (int i = 0; i < pcolors.Count && rowIdx < shopRows.Count; i++, rowIdx++)
            {
                ApplyShopRow(shopRows[rowIdx], pcolors[i], balance, s);
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
                // Subgroup hint - "stackable" only applies to bold/italic/underline/strike.
                string sub = NametagStyler.GetSubgroup(it.sku);
                string hint = sub == null ? "stackable"
                    : sub == "color" ? "one color at a time"
                    : sub == "glow"  ? "one glow at a time - modded players only"
                    : sub == "size"  ? "one size at a time"
                    : sub == "typeface" ? "one typeface at a time - modded players only"
                    : "one font at a time";
                UIFactory.SetText(r.txtDesc, $"Preview: {previewWrap}  <color=#888>({hint})</color>");
                // ORDER IS LOAD-BEARING: typeface first, glow second. Setting TMP_Text.font
                // resets fontMaterial to the new font asset's default - if we applied glow
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
                // Recycled row - if it was previously showing a glow / typeface preview,
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
            r.setActiveBtn.SetActive(ownsThis && (it.kind == "title" || it.kind == "trail" || it.kind == "color" || it.kind == "nametag" || it.kind == "player_color"));
            bool isActiveTitle = s != null && it.kind == "title" && s.active_title == it.name;
            bool isActiveTrail = s != null && it.kind == "trail" && s.active_trail_sku == it.sku;
            bool isActiveColor = s != null && it.kind == "color"
                && s.active_color_skus != null && s.active_color_skus.Contains(it.sku);
            bool isActiveNametag = s != null && it.kind == "nametag" && s.active_nametag_skus != null
                && s.active_nametag_skus.Contains(it.sku);
            bool isActivePlayerColor = s != null && it.kind == "player_color" && s.active_player_color_sku == it.sku;
            bool isActive = isActiveTitle || isActiveTrail || isActiveColor || isActiveNametag || isActivePlayerColor;
            if (r.setActiveBtn != null)
            {
                UIFactory.SetImageColor(r.setActiveBtn, isActive
                    ? new Color(0.2f, 0.55f, 0.2f, 0.95f)   // active = green
                    : new Color(0.3f, 0.3f, 0.5f, 0.9f));   // inactive = default
                var txtComp = UIFactory.GetButtonText(r.setActiveBtn);
                // Colors are multi-equip (cycle via Shift) and nametags are stackable so
                // their "active" label is "Remove" - clicking removes from the equipped set.
                // Titles/trails/player-colors are single-active; clicking the equipped one
                // unequips it so the player can run with no title / no trail / default body.
                bool isMultiEquip = it.kind == "nametag" || it.kind == "color";
                if (txtComp != null) UIFactory.SetText(txtComp,
                    isActive
                        ? (isMultiEquip ? "Remove" : "Unequip")
                        : (isMultiEquip ? "Equip" : "Set Active"));
            }

            // Preview button - trails only. Stash the color + price on the row so the click
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

        // -- Settings Tab ----------------------------------------
        private static object txtConsentStatus, txtDeleteStatus;
        private static GameObject consentToggleBtn, deleteBtn, confirmDeleteBtn, cancelDelBtn, notifToggleBtn;
        private static GameObject fpsToggleBtn, pingToggleBtn, ingameChatToggleBtn, trailToggleBtn, blockDbgToggleBtn, playerColorToggleBtn;
        private static object consentToggleTxt, notifToggleTxt, fpsToggleTxt, pingToggleTxt, ingameChatToggleTxt, trailToggleTxt, blockDbgToggleTxt, playerColorToggleTxt;
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

            // -- Data consent (top) --
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

            // -- Display toggles --
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
                    // Live effect mid-match: ON -> re-attach for everyone, OFF -> detach.
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

            // -- Block Debug overlay --
            UIFactory.CreateText("SBlkDbgL", dispBox.transform,
                "Block debug overlay (corner): live act/succ counters + per-hit timing (too early / too slow / unblockable).",
                13f, C_DIM, sizeDelta: new Vector2(700, 34));
            blockDbgToggleBtn = SettingsButton(dispBox.transform, "SBlkDbg", "",
                C_WHITE, C_BTN, new Vector2(260, 28),
                () =>
                {
                    Plugin.Log.LogInfo("[SETTINGS] Block debug overlay toggled");
                    Plugin.ShowBlockDebug.Value = !Plugin.ShowBlockDebug.Value;
                    dirty = true;
                });
            blockDbgToggleTxt = UIFactory.GetButtonText(blockDbgToggleBtn);

            // -- Custom player body colors --
            UIFactory.CreateText("SPColorL", dispBox.transform,
                "Custom player body colors: render shop-purchased Body Colors on yourself + other modded players. Off = everyone falls back to default orange/blue.",
                13f, C_DIM, sizeDelta: new Vector2(700, 34));
            playerColorToggleBtn = SettingsButton(dispBox.transform, "SPColor", "",
                C_WHITE, C_BTN, new Vector2(260, 28),
                () =>
                {
                    Plugin.Log.LogInfo("[SETTINGS] Custom player colors toggled");
                    Plugin.ShowPlayerColors.Value = !Plugin.ShowPlayerColors.Value;
                    try { PlayerColorCosmetic.OnShowPlayerColorsToggled(); } catch { }
                    dirty = true;
                });
            playerColorToggleTxt = UIFactory.GetButtonText(playerColorToggleBtn);

            // -- Chat pop-up notifications --
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

            // -- Filler spacer so Delete sits at the bottom --
            var mid = new GameObject("SMid");
            mid.transform.SetParent(panel.transform, false);
            mid.AddComponent<RectTransform>();
            UIFactory.AddLE(mid, flexH: 1);

            // -- Delete my data (last, so it's hard to click accidentally) --
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
                "Delete my data...", 14f, C_WHITE, new Color(0.45f, 0.18f, 0.18f, 0.9f),
                () =>
                {
                    if (!ClickGuard.Claim()) return;
                    deleteArmed = true;
                    dirty = true;
                },
                sizeDelta: new Vector2(200, 28));
            UIFactory.AddLE(deleteBtn, prefW: 200, prefH: 28, flexW: 0, flexH: 0);
            confirmDeleteBtn = UIFactory.CreateButton("SDCBtn", delRow.transform,
                "Confirm - really delete", 14f, C_WHITE, new Color(0.7f, 0.15f, 0.15f, 0.95f),
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
                    status = "Status: <color=#88FF88>Allowed</color> - match data and linking are active.";
                else if (Plugin.DataConsentAsked)
                    status = "Status: <color=#FF9966>Denied</color> - mod runs offline. No data leaves your machine.";
                else
                    status = "Status: <color=#DDDD66>Unset</color> - the consent prompt will appear on next launch.";
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
            if (blockDbgToggleTxt != null && Plugin.ShowBlockDebug != null)
                UIFactory.SetText(blockDbgToggleTxt,
                    Plugin.ShowBlockDebug.Value
                        ? "Block debug overlay: <color=#88FF88>ON</color>"
                        : "Block debug overlay: <color=#FF9966>OFF</color>");
            if (playerColorToggleTxt != null && Plugin.ShowPlayerColors != null)
                UIFactory.SetText(playerColorToggleTxt,
                    Plugin.ShowPlayerColors.Value
                        ? "Custom player body colors: <color=#88FF88>ON</color>"
                        : "Custom player body colors: <color=#FF9966>OFF</color>");
        }

        private static void RefreshRecentSeries()
        {
            if(txtRecentSeries==null)return;
            var series=ApiClient.CachedRecentSeries;
            if(series==null||series.Count==0){UIFactory.SetText(txtRecentSeries,"No recent series");if(seriesPrev!=null)seriesPrev.SetActive(false);if(seriesNext!=null)seriesNext.SetActive(false);if(txtSeriesPage!=null)UIFactory.SetText(txtSeriesPage,"");return;}
            // 20 series per page (was 8). Server returns up to 100 - see FetchRecentSeries.
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
                // dim grey for losers. Show "AsteRiA bet 500g on Sid -> +505g" style.
                if (s.bets != null && s.bets.Count > 0)
                {
                    foreach (var b in s.bets)
                    {
                        string bettorTag = b.bettor_name == myName ? "<b>You</b>" : Trunc(b.bettor_name ?? "?", 14);
                        if (b.won)
                            txt += $"    <color=#88CC88>-> {bettorTag} bet {b.amount}g on {Trunc(b.bet_on_name ?? "?", 12)} -> <b>+{b.payout}g</b></color>\n";
                        else
                            txt += $"    <color=#664444>-> {bettorTag} bet {b.amount}g on {Trunc(b.bet_on_name ?? "?", 12)} - lost</color>\n";
                    }
                }
            }
            UIFactory.SetText(txtRecentSeries,txt);
            if(seriesPrev!=null)seriesPrev.SetActive(recentSeriesPage>0);
            if(seriesNext!=null)seriesNext.SetActive(recentSeriesPage<totalPages-1);
            if(txtSeriesPage!=null)UIFactory.SetText(txtSeriesPage,totalPages>1?$"{recentSeriesPage+1}/{totalPages}":"");
        }

        private static void RefreshVersionStatus(){if(txtVersionStatus==null)return;if(ApiClient.ForceUpdateRequired){UIFactory.SetText(txtVersionStatus,"<color=#FF4444>UPDATE REQUIRED - server is rejecting this mod version</color>");if(updateBtn!=null)updateBtn.SetActive(true);return;}if(ApiClient.UpdateReady){UIFactory.SetText(txtVersionStatus,"<color=#44FF44>Close ROUNDS to apply update</color>");if(updateBtn!=null)updateBtn.SetActive(false);return;}if(ApiClient.IsUpdating){UIFactory.SetText(txtVersionStatus,"<color=#66CCFF>Downloading...</color>");if(updateBtn!=null)updateBtn.SetActive(false);return;}string latest=ApiClient.LatestModVersion;if(latest==null){UIFactory.SetText(txtVersionStatus,"");if(updateBtn!=null)updateBtn.SetActive(false);return;}if(latest==Plugin.ModVersion){UIFactory.SetText(txtVersionStatus,"<color=#44AA44>up to date</color>");if(updateBtn!=null)updateBtn.SetActive(false);}else{UIFactory.SetText(txtVersionStatus,$"<color=#FFAA33>v{latest} available!</color>");if(updateBtn!=null)updateBtn.SetActive(true);}}

        private static void RefreshMyStats(){var s=ApiClient.CachedPlayerStats;if(s==null){UIFactory.SetText(txtRating,"-");return;}/* Top-left player name. Refresh on every stats reload — was set ONCE
        at panel build time from CachedPlayerStats which could be empty/wrong (e.g., display_name
        defaulted to steam_id during the get_or_create_player initial creation). User reported
        "all of my names are showing up as the steam id instead of the name in the top left". */
        if(txtTopLeftName!=null){string nm=!string.IsNullOrEmpty(s.display_name)&&s.display_name!=s.steam_id?s.display_name:(MatchTracker.LocalDisplayName??s.display_name??"");UIFactory.SetText(txtTopLeftName,nm);}
        UIFactory.SetText(txtRating,$"{s.rating:F0}");UIFactory.SetText(txtRD,$"RD: {s.rating_deviation:F0}    Peak: {s.peak_rating:F0}");UIFactory.SetText(txtLevel,$"Level {s.level}");if(s.level<100&&s.xp_for_next_level>0){UIFactory.SetText(txtXPProg,$"{s.xp_into_level}/{s.xp_for_next_level} XP");UIFactory.SetFill(xpFill,(float)s.xp_into_level/s.xp_for_next_level);}else{UIFactory.SetText(txtXPProg,"MAX");UIFactory.SetFill(xpFill,1f);}UIFactory.SetText(txtTotalXP,$"{s.total_xp:N0} XP");var history=ApiClient.CachedMatchHistory;var sR=history?.FindAll(m=>m.is_ranked)??new List<ApiClient.MatchHistoryEntry>();var sC=history?.FindAll(m=>!m.is_ranked)??new List<ApiClient.MatchHistoryEntry>();int cW=0,cL=0,sweepG=0,sweepT=0;foreach(var m in sC){if(m.won)cW++;else cL++;}if(history!=null)foreach(var m in history){if(m.won&&m.opponent_rounds_won==0)sweepG++;if(!m.won&&m.player_rounds_won==0)sweepT++;}int rW=s.ranked_series_wins,rL=s.ranked_series_losses;UIFactory.SetText(txtRankedRec,rW+rL>0?$"<color=#FFD94D>Ranked:</color> {rW}W / {rL}L ({(rL>0?$"{(float)rW/rL:F1}":$"{rW}:0")})":"<color=#FFD94D>Ranked:</color> -");if(sR.Count>0){int st=CalcStreak(sR);string c=st>0?"#00FF00":"#FF6666";UIFactory.SetText(txtRankedStrk,$"  <color={c}>Streak: {(st>0?$"{st}W":$"{-st}L")}</color>"+(s.best_ranked_streak>0?$"  Best: {s.best_ranked_streak}W":""));}else UIFactory.SetText(txtRankedStrk,"");/* 2v2 line — shows the parallel Glicko / W-L / streak. Hidden when no 2v2 series played, since the row otherwise reads as a confusing 0-0/1500 default. */{var t2=ApiClient.CachedTeamStats;if(t2!=null&&(t2.series_wins+t2.series_losses)>0){string ratio=t2.series_losses>0?$"{(float)t2.series_wins/t2.series_losses:F1}":t2.series_wins>0?$"{t2.series_wins}:0":"0:0";UIFactory.SetText(txtTeam2v2Rec,$"<color=#FFB347>2v2:</color> {t2.series_wins}W / {t2.series_losses}L ({ratio})  <color=#888>Rating:</color> {t2.rating:F0}  <color=#888>Peak:</color> {t2.peak_rating:F0}");int st2=t2.current_streak;if(st2!=0){string c2=st2>0?"#00FF00":"#FF6666";UIFactory.SetText(txtTeam2v2Strk,$"  <color={c2}>Streak: {(st2>0?$"{st2}W":$"{-st2}L")}</color>");}else UIFactory.SetText(txtTeam2v2Strk,"");}else{UIFactory.SetText(txtTeam2v2Rec,"<color=#FFB347>2v2:</color> -");UIFactory.SetText(txtTeam2v2Strk,"");}}UIFactory.SetText(txtCasualRec,sC.Count>0?$"Casual: {cW}W / {cL}L ({(cL>0?$"{(float)cW/cL:F1}":cW>0?$"{cW}:0":"")})":"Casual: -");if(sC.Count>0){int st=CalcStreak(sC);string c=st>0?"#00FF00":"#FF6666";UIFactory.SetText(txtCasualStrk,$"  <color={c}>Streak: {(st>0?$"{st}W":$"{-st}L")}</color>"+(s.best_casual_streak>0?$"  Best: {s.best_casual_streak}W":""));}else UIFactory.SetText(txtCasualStrk,"");UIFactory.SetText(txtSweeps,$"Sweeps: <color=#00FF00>5-0 x{sweepG}</color>  <color=#FF6666>0-5 x{sweepT}</color>");UIFactory.SetText(txtTotalRec,$"Total: {s.total_matches} ({s.wins}W / {s.losses}L)  <color=#FFD94D>Gold: {(s.gold_earned - s.gold_spent)}</color>");/* Hit% / Block% lifetime - one-sided totals (only the reporter-side's client has these
 * counters). Split across two lines in the 44px-tall txtAccuracy field because the
 * combined string overflows 340px at 15pt and TMP wordwrap clips the second line
 * when the field is only 22px tall. Newline gives TMP a proper 2-line render. */
{string hitLine=s.bullets_fired>0?$"<color=#FF9988>Hit:</color> {(float)s.bullets_hit*100f/s.bullets_fired:F1}% ({s.bullets_hit}/{s.bullets_fired})":"<color=#FF9988>Hit:</color> -";string blkLine=s.blocks_activated>0?$"<color=#99CCFF>Block:</color> {(float)s.blocks_successful*100f/s.blocks_activated:F1}% ({s.blocks_successful}/{s.blocks_activated})":"<color=#99CCFF>Block:</color> -";UIFactory.SetText(txtAccuracy,$"{hitLine}\n{blkLine}");}RefreshHistory(sR,sC);RefreshSession();if(linkCodeBtn!=null&&txtLinkCode!=null){bool linked=!string.IsNullOrEmpty(s.discord_id);linkCodeBtn.SetActive(!linked);if(linked){string raw=!string.IsNullOrEmpty(s.discord_username)?$"@{s.discord_username}":$"ID {s.discord_id}";string who=discordRevealed?raw:"<color=#888>***** (click to show)</color>";UIFactory.SetText(txtLinkCode,$"<color=#00FF00>Linked to Discord</color> ({who})");}}RefreshChatLog();}
        private static void RefreshHistory(List<ApiClient.MatchHistoryEntry> ranked,List<ApiClient.MatchHistoryEntry> casual){foreach(var r in rankedRows){r.root.SetActive(false);r.seriesGO.SetActive(false);}if(ranked.Count>0){var groups=GroupBySeries(ranked);int gpp=3,totalP=(groups.Count+gpp-1)/gpp;rankedPage=Math.Max(0,Math.Min(rankedPage,totalP-1));int start=rankedPage*gpp,end=Math.Min(start+gpp,groups.Count);int ri=0;for(int g=start;g<end&&ri<rankedRows.Count;g++){var grp=groups[g];if(grp.matches.Count==0)continue;var first=grp.matches[0];if(grp.series_id!=null&&ri<rankedRows.Count){var row=rankedRows[ri];string score=first.series_score??"?-?",opp=FormatOpponentForRow(first,18);bool complete=false,won=false;try{var p=score.Split('-');int mw=int.Parse(p[0]),tw=int.Parse(p[1]);complete=mw>=2||tw>=2;won=mw>tw;}catch{}UIFactory.SetText(row.txtSeriesHead,complete?$"Series {(won?"W":"L")} {score}  vs {opp}":$"Series {score}  vs {opp}  (in progress)");UIFactory.SetColor(row.txtSeriesHead,complete?(won?C_GREEN:C_RED):C_GOLD);/* The per-match row shows XP->gold (typically 4-5g/match); the series-win bonus (10-12g) was invisible because the history row never referenced series_gold_gained. Find the populated value across matches in this group (server sets it on the last-match-of-series row) and append to the elo line. */int grpSeriesGold=0;foreach(var mm in grp.matches)if(mm.series_gold_gained>grpSeriesGold)grpSeriesGold=mm.series_gold_gained;if(complete&&first.series_rating_change!=0f){float rc=first.series_rating_change;string goldStr=grpSeriesGold>0?$" <color=#FFD94D>+{grpSeriesGold}g</color>":"";UIFactory.SetText(row.txtSeriesElo,$"{(rc>0?"+":"")}{rc:F0} elo{goldStr}");UIFactory.SetColor(row.txtSeriesElo,rc>0?C_GREEN:C_RED);}else UIFactory.SetText(row.txtSeriesElo,"");row.seriesGO.SetActive(true);foreach(var m in grp.matches){if(ri>=rankedRows.Count)break;FillRow(rankedRows[ri],m,true);ri++;}}else{FillRow(rankedRows[ri],first,false);ri++;}}rPrev.SetActive(rankedPage>0);rNext.SetActive(rankedPage<totalP-1);UIFactory.SetText(txtRankedPage,totalP>1?$"{rankedPage+1}/{totalP}":"");}else{rPrev.SetActive(false);rNext.SetActive(false);UIFactory.SetText(txtRankedPage,"");}foreach(var r in casualRows)r.root.SetActive(false);if(casual.Count>0){int mpp=6,totalP=(casual.Count+mpp-1)/mpp;casualPage=Math.Max(0,Math.Min(casualPage,totalP-1));int start=casualPage*mpp,end=Math.Min(start+mpp,casual.Count);for(int i=start;i<end;i++){int ri=i-start;if(ri<casualRows.Count)FillRow(casualRows[ri],casual[i],false);}cPrev.SetActive(casualPage>0);cNext.SetActive(casualPage<totalP-1);UIFactory.SetText(txtCasualPage,totalP>1?$"{casualPage+1}/{totalP}":"");}else{cPrev.SetActive(false);cNext.SetActive(false);UIFactory.SetText(txtCasualPage,"");}}

        private static void FillRow(HistoryRow row,ApiClient.MatchHistoryEntry m,bool indent){string r=m.won?"W":"L";Color c=m.won?C_GREEN:C_RED;string pts=(m.player_points+m.opponent_points>0)?$" <color=#{(m.won?"88AA88":"AA8888")}>{m.player_points}-{m.opponent_points}p</color>":"";UIFactory.SetText(row.txtResult,$"{(indent?"    ":"  ")}{r}  {m.player_rounds_won}-{m.opponent_rounds_won}{pts}");UIFactory.SetColor(row.txtResult,c);UIFactory.SetText(row.txtOpp,indent?"":$"vs {FormatOpponentForRow(m,20)}");UIFactory.SetText(row.txtFps,BuildFpsTag(m));UIFactory.SetText(row.txtXP,m.xp_gained>0?(m.gold_gained>0?$"+{m.xp_gained}xp <color=#FFD94D>+{m.gold_gained}g</color>":$"+{m.xp_gained}xp"):"");string dt="";try{if(!string.IsNullOrEmpty(m.ended_at)&&m.ended_at.Length>=10)dt=DateTime.Parse(m.ended_at).ToString("M/d");}catch{}UIFactory.SetText(row.txtDate,dt);UIFactory.SetText(row.txtCards,!string.IsNullOrEmpty(m.cards_display)?$"        Cards: {m.cards_display}":"");UIFactory.SetText(row.txtOppCards,!string.IsNullOrEmpty(m.opp_cards_display)?$"        Opp:   {m.opp_cards_display}":"");row.root.SetActive(true);}
        // FPS tag — rendered in its own dedicated text field to the right of the
        // opponent name. Player side uses the same blue as the cards line, opponent
        // uses the matching red, mirroring how each side reads in the cards/opp panel.
        private static string BuildFpsTag(ApiClient.MatchHistoryEntry m){if(m==null)return"";int p=m.player_fps_avg,o=m.opponent_fps_avg;if(p<=0&&o<=0)return"";string pStr=p>0?p.ToString():"-";string oStr=o>0?o.ToString():"-";return$"<color=#888>FPS:</color> <color=#99B3E6>{pStr}</color> <color=#888>/</color> <color=#E69988>{oStr}</color>";}

        // Renders the opponent name + colored title tag for match-history rows. Title is the
        // opponent's CURRENT active title (view-time, not snapshot-at-match) - cheap join in the
        // history endpoint, good enough to answer "who am I looking at right now."
        private static string FormatOpponentForRow(ApiClient.MatchHistoryEntry m,int nameMax)
        {
            string nm = Trunc(m?.opponent_name ?? "", nameMax);
            if (m == null || string.IsNullOrEmpty(m.opponent_title)) return nm;
            string col = string.IsNullOrEmpty(m.opponent_title_color) ? "#CCCCCC" : m.opponent_title_color;
            return $"{nm} <b><color={col}>[{m.opponent_title}]</color></b>";
        }

        private static void RefreshSession(){int games=GameStateWatcher.SessionMatchCount;bool inRoom=GameStateWatcher.IsInRoom;string oppSteamId=GameStateWatcher.OpponentSteamId;string oppName=GameStateWatcher.OpponentDisplayName;var history=ApiClient.CachedMatchHistory;/* Show opponent lifetime record when in room */if(inRoom&&!string.IsNullOrEmpty(oppSteamId)&&!oppSteamId.StartsWith("photon_")&&history!=null){int ltW=0,ltL=0;string lastPlayed="";foreach(var m in history){if(m.opponent_steam_id==oppSteamId){if(m.won)ltW++;else ltL++;if(string.IsNullOrEmpty(lastPlayed)){try{lastPlayed=DateTime.Parse(m.ended_at).ToString("M/d/yyyy");}catch{}}}}if(ltW+ltL>0){string col=ltW>ltL?"#00FF00":ltW<ltL?"#FF6666":"#AAAAAA";UIFactory.SetText(txtSessionOppLifetime,$"  vs {oppName}:  <color={col}>{ltW}W-{ltL}L lifetime</color>  (last: {lastPlayed})");}else{UIFactory.SetText(txtSessionOppLifetime,$"  vs {oppName}:  First time playing!");}UIFactory.SetColor(txtSessionOppLifetime,new Color(0.6f,0.75f,1f));}else if(inRoom&&!string.IsNullOrEmpty(oppName)&&oppName!="Opponent"){UIFactory.SetText(txtSessionOppLifetime,$"  In room with {oppName}");UIFactory.SetColor(txtSessionOppLifetime,C_DIM);}else{UIFactory.SetText(txtSessionOppLifetime,"");}if(games<=0){UIFactory.SetText(txtSessionSum,inRoom?"In game - no results yet":"No games this session");UIFactory.SetColor(txtSessionSum,C_DIM);UIFactory.SetText(txtSessionSplit,"");UIFactory.SetText(txtSessionSweeps,"");return;}int mins=(int)(DateTime.UtcNow-GameStateWatcher.SessionStartTime).TotalMinutes;string time=mins>=60?$"{mins/60}h {mins%60}m":$"{mins}m";int rw=GameStateWatcher.SessionRankedWins,rl=GameStateWatcher.SessionRankedLosses,cw=GameStateWatcher.SessionCasualWins,cl=GameStateWatcher.SessionCasualLosses;int t2w=GameStateWatcher.SessionTeamSeriesWins,t2l=GameStateWatcher.SessionTeamSeriesLosses;int sesSweepG=0,sesSweepT=0;if(history!=null){var sesStart=GameStateWatcher.SessionStartTime;foreach(var m in history){DateTime mTime=DateTime.UtcNow;try{if(!string.IsNullOrEmpty(m.ended_at))mTime=DateTime.Parse(m.ended_at).ToUniversalTime();}catch{}if(mTime<sesStart)continue;if(m.won&&m.opponent_rounds_won==0)sesSweepG++;if(!m.won&&m.player_rounds_won==0)sesSweepT++;}}UIFactory.SetText(txtSessionSum,$"{games} games    {rw+cw}W - {rl+cl}L    {time}");UIFactory.SetColor(txtSessionSum,C_WHITE);string splitLine="";var splitParts=new List<string>();if(rw+rl>0)splitParts.Add($"<color=#FFD94D>Ranked:</color> {rw}W/{rl}L");if(t2w+t2l>0)splitParts.Add($"<color=#FFB347>2v2:</color> {t2w}W/{t2l}L");if(cw+cl>0)splitParts.Add($"Casual: {cw}W/{cl}L");if(splitParts.Count>0)splitLine="  "+string.Join("    ",splitParts.ToArray());UIFactory.SetText(txtSessionSplit,splitLine);if(sesSweepG+sesSweepT>0)UIFactory.SetText(txtSessionSweeps,$"  Sweeps: <color=#00FF00>5-0 x{sesSweepG}</color>  <color=#FF6666>0-5 x{sesSweepT}</color>");else UIFactory.SetText(txtSessionSweeps,"");var wl=GameStateWatcher.SessionWLByOpponent;var st=GameStateWatcher.SessionTimeByOpponent;int idx=0;if(wl!=null)foreach(var kvp in wl){int[]a=kvp.Value;if(a==null||a.Length<4)continue;int ow=a[0]+a[2],ol=a[1]+a[3];string line=$"  vs {kvp.Key}:  {ow}W-{ol}L";if(a[0]+a[1]>0&&a[2]+a[3]>0)line+=$"  (R:{a[0]}-{a[1]} C:{a[2]}-{a[3]})";if(st!=null&&st.ContainsKey(kvp.Key)){int m=(int)st[kvp.Key];line+=m>=60?$"   {m/60}h {m%60}m":$"   {m}m";}while(sessionOppTexts.Count<=idx)sessionOppTexts.Add(UIFactory.CreateText($"so{sessionOppTexts.Count}",sessionOppContainer.transform,"",15f,C_LABEL,sizeDelta:new Vector2(340,22)));UIFactory.SetText(sessionOppTexts[idx],line);UIFactory.SetColor(sessionOppTexts[idx],ow>ol?C_GREEN:ow<ol?C_RED:C_DIM);var go=(sessionOppTexts[idx]as Component)?.gameObject;if(go)go.SetActive(true);idx++;}for(int i=idx;i<sessionOppTexts.Count;i++){var go=(sessionOppTexts[i]as Component)?.gameObject;if(go)go.SetActive(false);}}

        private static void RefreshLeaderboard(){string[]hL={"#","Lv","Player","Rating","W","L","W/L","Gold"};string[]hK={"rank","level","display_name","rating","wins","losses","wl_ratio","gold"};if(lbSortTexts!=null)for(int i=0;i<hK.Length&&i<lbSortTexts.Length;i++){if(lbSortTexts[i]==null)continue;string arrow=lbSort==hK[i]?(lbSortDesc?" v":" ^"):"";UIFactory.SetText(lbSortTexts[i],hL[i]+arrow);UIFactory.SetColor(lbSortTexts[i],lbSort==hK[i]?C_WHITE:C_LABEL);if(lbSortBtns!=null&&i<lbSortBtns.Length)UIFactory.SetImageColor(lbSortBtns[i],lbSort==hK[i]?C_TABACT:C_TAB);}var board=ApiClient.CachedLeaderboard;foreach(var r in lbRows)r.root.SetActive(false);if(board==null||board.entries==null||board.entries.Length==0){UIFactory.SetText(txtLBDetail,"No leaderboard data");UIFactory.SetText(txtLBCount,"");return;}var entries=new List<ApiClient.LeaderboardEntry>(board.entries);switch(lbSort){case "rank":entries.Sort((a,b)=>lbSortDesc?b.rank.CompareTo(a.rank):a.rank.CompareTo(b.rank));break;case "level":entries.Sort((a,b)=>lbSortDesc?b.level.CompareTo(a.level):a.level.CompareTo(b.level));break;case "display_name":entries.Sort((a,b)=>lbSortDesc?string.Compare(b.display_name,a.display_name,StringComparison.OrdinalIgnoreCase):string.Compare(a.display_name,b.display_name,StringComparison.OrdinalIgnoreCase));break;case "rating":entries.Sort((a,b)=>lbSortDesc?b.rating.CompareTo(a.rating):a.rating.CompareTo(b.rating));break;case "wins":entries.Sort((a,b)=>lbSortDesc?b.wins.CompareTo(a.wins):a.wins.CompareTo(b.wins));break;case "losses":entries.Sort((a,b)=>lbSortDesc?b.losses.CompareTo(a.losses):a.losses.CompareTo(b.losses));break;case "wl_ratio":entries.Sort((a,b)=>{float ra=a.losses>0?(float)a.wins/a.losses:a.wins*100f;float rb=b.losses>0?(float)b.wins/b.losses:b.wins*100f;return lbSortDesc?rb.CompareTo(ra):ra.CompareTo(rb);});break;case "gold":entries.Sort((a,b)=>lbSortDesc?b.gold.CompareTo(a.gold):a.gold.CompareTo(b.gold));break;}int lbPP=100,lbTotalP=(entries.Count+lbPP-1)/lbPP;lbPage=Math.Max(0,Math.Min(lbPage,lbTotalP-1));int lbStart=lbPage*lbPP,lbEnd=Math.Min(lbStart+lbPP,entries.Count);for(int i=lbStart;i<lbEnd&&(i-lbStart)<lbRows.Count;i++){var e=entries[i];var row=lbRows[i-lbStart];row.steamId=e.steam_id;bool local=e.steam_id==MatchTracker.LocalSteamId;string ratio=e.losses>0?$"{(float)e.wins/e.losses:F1}":e.wins>0?$"{e.wins}:0":"0:0";UIFactory.SetText(row.txtRank,$"{e.rank}");UIFactory.SetColor(row.txtRank,e.rank==1?new Color(1f,0.84f,0f):e.rank==2?new Color(0.75f,0.75f,0.75f):e.rank==3?new Color(0.8f,0.5f,0.2f):C_GOLD);UIFactory.SetText(row.txtLv,$"{e.level}");string _lbName=Trunc(e.display_name,14);if(!string.IsNullOrEmpty(e.title)){string _tc=string.IsNullOrEmpty(e.title_color)?"#FFFFFF":e.title_color;_lbName=$"{_lbName} <b><color={_tc}>[{e.title}]</color></b>";}UIFactory.SetText(row.txtName,_lbName);UIFactory.SetColor(row.txtName,local?C_GREEN:C_WHITE);UIFactory.SetText(row.txtRating,$"{e.rating}");UIFactory.SetText(row.txtW,$"{e.wins}");UIFactory.SetText(row.txtL,$"{e.losses}");UIFactory.SetText(row.txtWL,ratio);UIFactory.SetText(row.txtGold,e.gold>0?$"{e.gold}":"0");bool sel=e.steam_id==selectedSteamId;UIFactory.SetImageColor(row.hlWrap,sel?new Color(0.2f,0.25f,0.4f,0.4f):new Color(0.15f,0.15f,0.2f,0.01f));row.root.SetActive(true);}UIFactory.SetText(txtLBCount,$"{board.total_players} players ranked");lbPrev.SetActive(lbPage>0);lbNext.SetActive(lbPage<lbTotalP-1);UIFactory.SetText(txtLBPage,lbTotalP>1?$"{lbPage+1}/{lbTotalP}":"");if(!string.IsNullOrEmpty(selectedSteamId)&&selectedStats!=null){var ps=selectedStats;UIFactory.SetText(txtLBPlayerName,$"{ps.display_name}   <color=#66CCFF>Level {ps.level}</color>");string detail=$"\nRating: {ps.rating:F0}   RD: {ps.rating_deviation:F0}   Peak: {ps.peak_rating:F0}\n{ps.total_matches} matches ({ps.wins}W / {ps.losses}L)  WR: {(ps.total_matches>0?ps.wins*100f/ps.total_matches:0):F0}%\n";if(ps.ranked_series_wins+ps.ranked_series_losses>0)detail+=$"<color=#FFD94D>Ranked: {ps.ranked_series_wins}W / {ps.ranked_series_losses}L</color>\n";/* Leave % - denominator includes DCs as their own events */if(ps.ranked_dc_count>0||ps.ranked_series_wins+ps.ranked_series_losses>0){int totalRanked=ps.ranked_series_wins+ps.ranked_series_losses+ps.ranked_dc_count;int dc=ps.ranked_dc_count;if(totalRanked>0){float pct=(float)dc/totalRanked*100f;string dcCol=pct<5f?"#44AA44":pct<15f?"#DDAA33":"#FF4444";detail+=$"<color={dcCol}>Leave: {dc}/{totalRanked} ({pct:F0}%)</color>\n";}}/* Hit% / Block% - lifetime counters driven by Harmony patches (Gun.Attack / HealthHandler.TakeDamage / Block.TryBlock / Block.DoBlock). Accumulates only when this player reported a match. Show a dash for players who haven't reported yet so the rows stay consistent with the My Stats Record section (instead of silently disappearing). */{string hitLine=ps.bullets_fired>0?$"<color=#FF9988>Hit:</color> {(float)ps.bullets_hit*100f/ps.bullets_fired:F1}% <color=#888>({ps.bullets_hit}/{ps.bullets_fired})</color>":"<color=#FF9988>Hit:</color> -";string blkLine=ps.blocks_activated>0?$"<color=#99CCFF>Block:</color> {(float)ps.blocks_successful*100f/ps.blocks_activated:F1}% <color=#888>({ps.blocks_successful}/{ps.blocks_activated})</color>":"<color=#99CCFF>Block:</color> -";detail+=$"{hitLine}\n{blkLine}\n";}/* Head to head */var history=ApiClient.CachedMatchHistory;if(history!=null&&selectedSteamId!=MatchTracker.LocalSteamId){int h2hW=0,h2hL=0,h2hCW=0,h2hCL=0,h2hSW=0,h2hSL=0;var seenSeries=new HashSet<string>();foreach(var m in history){if(m.opponent_steam_id==selectedSteamId){if(m.is_ranked){/* Count individual ranked for overall */if(m.won)h2hW++;else h2hL++;/* Count series wins/losses (deduplicate by series_id) */if(!string.IsNullOrEmpty(m.series_id)&&m.series_id!="null"&&!seenSeries.Contains(m.series_id)){string ss=m.series_score;if(!string.IsNullOrEmpty(ss)&&ss.Contains("-")){try{var sp=ss.Split('-');int sw=int.Parse(sp[0]),sl=int.Parse(sp[1]);if(sw>=2||sl>=2){seenSeries.Add(m.series_id);if(sw>sl)h2hSW++;else h2hSL++;}}catch{}}}}else{if(m.won)h2hCW++;else h2hCL++;}}}int h2hAll=h2hW+h2hCW,h2hAllL=h2hL+h2hCL;if(h2hAll+h2hAllL>0){string h2hColor=h2hAll>h2hAllL?"#00FF00":h2hAll<h2hAllL?"#FF6666":"#AAAAAA";detail+=$"\n<b>vs You:</b> <color={h2hColor}>{h2hAll}W - {h2hAllL}L ({h2hAll+h2hAllL} games)</color>\n";if(h2hSW+h2hSL>0)detail+=$"  Ranked Series: {h2hSW}W / {h2hSL}L\n";if(h2hCW+h2hCL>0)detail+=$"  Casual: {h2hCW}W / {h2hCL}L\n";}}/* Top cards with win rates */if(ps.top_card_names!=null&&ps.top_card_names.Count>0){detail+="\n<color=#99AAEE>Top Cards:</color>\n";for(int ci=0;ci<ps.top_card_names.Count&&ci<8;ci++){string picks=ps.top_card_picks.Count>ci?$" ({ps.top_card_picks[ci]}x)":"";float wr=ps.top_card_win_rates!=null&&ps.top_card_win_rates.Count>ci?ps.top_card_win_rates[ci]*100f:0f;string wrCol=wr>=55?"#00FF00":wr<=45?"#FF6666":"#AAAAAA";detail+=$"  {ps.top_card_names[ci]}{picks}  <color={wrCol}>{wr:F0}%</color>\n";}}/* Tournament placements + recent results for the viewed player. Trophy counts stay inline (compact), recent list is capped to 4 rows so the detail doesn't grow off-screen. */if(ApiClient.CachedPlayerTournaments.TryGetValue(selectedSteamId,out var _tHist)&&_tHist!=null&&(_tHist.participant_count>0)){detail+="\n<color=#FFD94D>Tournaments:</color> ";detail+=$"<color=#FFE580>1stx{_tHist.winner_count}</color>  <color=#C8C8C8>2ndx{_tHist.runner_up_count}</color>  <color=#D4894A>3rdx{_tHist.third_place_count}</color>  <color=#888>(played {_tHist.participant_count})</color>\n";if(_tHist.recent!=null&&_tHist.recent.Length>0){int shown=0;foreach(var te in _tHist.recent){if(shown>=4)break;string dt=te.ended_at;try{if(!string.IsNullOrEmpty(dt))dt=TimeZoneInfo.ConvertTimeFromUtc(DateTime.Parse(te.ended_at,null,System.Globalization.DateTimeStyles.RoundtripKind).ToUniversalTime(),_ResolveTz()).ToString("M/d/yy");}catch{}string placeTxt=te.placed_rank==1?"<color=#FFE580>1st</color>":te.placed_rank==2?"<color=#C8C8C8>2nd</color>":te.placed_rank==3?"<color=#D4894A>3rd</color>":$"<color=#888>-</color>";detail+=$"  {dt}  {placeTxt}  <color=#888>({te.signup_count}p)</color>\n";shown++;}}}UIFactory.SetText(txtLBDetail,detail+GetAchievementText());/* Rating line graph - use elo history if available, fall back to form */BuildFormGraph(ps.rating_history,ps.recent_form);/* Block row - always show but hide button for self to prevent layout shift */if(lbBlockRow!=null){lbBlockRow.SetActive(true);bool notSelf=selectedSteamId!=MatchTracker.LocalSteamId;lbBlockBtn.SetActive(notSelf);if(notSelf&&lbBlockTxt!=null){bool blocked=ApiClient.IsPlayerBlocked(selectedSteamId);UIFactory.SetText(lbBlockTxt,blocked?"Unblock from Ranked":"Block from Ranked");UIFactory.SetImageColor(lbBlockBtn,blocked?new Color(0.15f,0.3f,0.15f,0.9f):new Color(0.5f,0.15f,0.15f,0.9f));}}}else{UIFactory.SetText(txtLBPlayerName,"Click a player");UIFactory.SetText(txtLBDetail,"");BuildFormGraph(null,null);if(lbBlockRow!=null)lbBlockRow.SetActive(false);}}

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
                // Form -> running score line (reversed: oldest left)
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

        private static void RefreshCardStats(){string[]hL={"Tier","Card","Rarity","Picks","Wins","WR%","Pass%"};string[]hK={"tier","card_name","card_rarity","times_picked","wins_with_card","win_rate","pass_rate"};if(cardSortTexts!=null)for(int i=0;i<7&&i<cardSortTexts.Length;i++){if(cardSortTexts[i]==null)continue;string arrow=cardSort==hK[i]?(cardSortDesc?" v":" ^"):"";UIFactory.SetText(cardSortTexts[i],hL[i]+arrow);UIFactory.SetColor(cardSortTexts[i],cardSort==hK[i]?C_WHITE:C_LABEL);if(cardSortBtns!=null&&i<cardSortBtns.Length)UIFactory.SetImageColor(cardSortBtns[i],cardSort==hK[i]?C_TABACT:C_TAB);}var cards=ApiClient.CachedCardStats;foreach(var r in cardRows)r.root.SetActive(false);if(cards==null||cards.Count==0)return;var merged=new List<ApiClient.CardStatData>();var seen=new Dictionary<string,int>(StringComparer.OrdinalIgnoreCase);foreach(var c in cards){string key=(c.card_name??"?").ToLower().Replace(" ","");if(seen.ContainsKey(key)){var e=merged[seen[key]];e.times_picked+=c.times_picked;e.wins_with_card+=c.wins_with_card;e.win_rate=e.times_picked>0?(float)e.wins_with_card/e.times_picked:0;e.times_offered=Math.Max(e.times_offered,c.times_offered);if(c.times_offered>0)e.pass_rate=c.pass_rate;if((e.card_rarity==null||e.card_rarity=="Unknown")&&c.card_rarity!=null&&c.card_rarity!="Unknown")e.card_rarity=c.card_rarity;}else{seen[key]=merged.Count;merged.Add(new ApiClient.CardStatData{card_name=c.card_name,card_rarity=c.card_rarity,times_picked=c.times_picked,wins_with_card=c.wins_with_card,win_rate=c.win_rate,times_offered=c.times_offered,pass_rate=c.pass_rate});}}
        // Tier sort: map S/A/B/C/D/E/F to 0..6, unset to 99 so they sort to the
        // bottom regardless of direction. Comparator pulls each card's tier
        // from cardTierMap keyed by the active filter.
        int TierRank(string tier){if(string.IsNullOrEmpty(tier))return 99;switch(tier){case "S":return 0;case "A":return 1;case "B":return 2;case "C":return 3;case "D":return 4;case "E":return 5;case "F":return 6;}return 99;}
        switch(cardSort){case "tier":merged.Sort((a,b)=>{int ar=TierRank(cardTierMap.TryGetValue(CardTierKey(cardFilter,a.card_name),out var av)?av:"");int br=TierRank(cardTierMap.TryGetValue(CardTierKey(cardFilter,b.card_name),out var bv)?bv:"");return cardSortDesc?ar.CompareTo(br):br.CompareTo(ar);});break;case "card_name":merged.Sort((a,b)=>cardSortDesc?string.Compare(b.card_name,a.card_name,StringComparison.OrdinalIgnoreCase):string.Compare(a.card_name,b.card_name,StringComparison.OrdinalIgnoreCase));break;case "card_rarity":merged.Sort((a,b)=>cardSortDesc?string.Compare(b.card_rarity,a.card_rarity,StringComparison.OrdinalIgnoreCase):string.Compare(a.card_rarity,b.card_rarity,StringComparison.OrdinalIgnoreCase));break;case "times_picked":merged.Sort((a,b)=>cardSortDesc?b.times_picked.CompareTo(a.times_picked):a.times_picked.CompareTo(b.times_picked));break;case "wins_with_card":merged.Sort((a,b)=>cardSortDesc?b.wins_with_card.CompareTo(a.wins_with_card):a.wins_with_card.CompareTo(b.wins_with_card));break;case "win_rate":merged.Sort((a,b)=>cardSortDesc?b.win_rate.CompareTo(a.win_rate):a.win_rate.CompareTo(b.win_rate));break;case "pass_rate":merged.Sort((a,b)=>cardSortDesc?b.pass_rate.CompareTo(a.pass_rate):a.pass_rate.CompareTo(b.pass_rate));break;default:merged.Sort((a,b)=>cardSortDesc?b.times_picked.CompareTo(a.times_picked):a.times_picked.CompareTo(b.times_picked));break;}for(int i=0;i<merged.Count&&i<cardRows.Count;i++){var c=merged[i];var row=cardRows[i];float wr=c.win_rate*100;Color wrColor=wr>=55?C_GREEN:wr<=45?C_RED:C_WHITE;row.cardName=c.card_name;UIFactory.SetText(row.txtName,c.card_name??"?");string rarity=c.card_rarity??"Unknown";UIFactory.SetText(row.txtRarity,rarity);UIFactory.SetColor(row.txtRarity,GetRarityColor(rarity));UIFactory.SetText(row.txtPicks,$"{c.times_picked}");UIFactory.SetText(row.txtWins,$"{c.wins_with_card}");UIFactory.SetText(row.txtWR,$"{wr:F0}%");UIFactory.SetColor(row.txtWR,wrColor);if(c.times_offered>0){float pr=c.pass_rate*100;UIFactory.SetText(row.txtPass,$"{pr:F0}%");UIFactory.SetColor(row.txtPass,pr>=70?C_RED:pr<=30?C_GREEN:C_LABEL);}else{UIFactory.SetText(row.txtPass,"-");UIFactory.SetColor(row.txtPass,C_DIM);}
                // Tier badge — letter + color tied to the player's saved tier
                // for this (card, current filter).
                string key=CardTierKey(cardFilter,c.card_name);
                string tierLetter=cardTierMap.TryGetValue(key,out var tv)?tv:"";
                ApplyRowTierVisuals(row, tierLetter);
                row.root.SetActive(true);}}

        // Update one row's tier display in place (no full re-render). Used both
        // by RefreshCardStats's per-row loop and by the click handler so a
        // tier-cycle doesn't trigger a re-sort that shifts cards under the
        // user's mouse cursor.
        private static void ApplyRowTierVisuals(CardRow row, string tierLetter)
        {
            if (string.IsNullOrEmpty(tierLetter))
            {
                UIFactory.SetText(row.txtTier, "<b>-</b>");
                UIFactory.SetImageColor(row.tierBtn, new Color(0.18f, 0.20f, 0.24f, 0.85f));
                UIFactory.SetImageColor(row.hl, new Color(0, 0, 0, 0));
            }
            else
            {
                // Rich-text bold so the letter renders bold on SDF atlases that
                // silently no-op the fontStyle=Bold flag (lesson 14).
                UIFactory.SetText(row.txtTier, $"<b>{tierLetter}</b>");
                Color tc = GetTierColor(tierLetter);
                UIFactory.SetImageColor(row.tierBtn, tc);
                // Translucent tier tint — same hue, ~25% alpha so text stays
                // readable. Bounded to row.hl (Tier→Pass% column wrapper).
                UIFactory.SetImageColor(row.hl, new Color(tc.r, tc.g, tc.b, 0.25f));
            }
        }

        // Click-time tier cycle. Updates state + writes to server + repaints
        // ONLY this single row's visuals — no full re-render and no re-sort,
        // so the row stays put under the user's cursor for follow-up clicks.
        private static void CycleCardTierInPlace(CardRow row, string cardName)
        {
            if (string.IsNullOrEmpty(cardName)) return;
            string filterStr = cardFilter == 1 ? "ranked" : cardFilter == 2 ? "casual" : "all";
            string key = CardTierKey(cardFilter, cardName);
            string current = cardTierMap.TryGetValue(key, out var c) ? c : "";
            int idx = Array.IndexOf(TIER_CYCLE, current);
            if (idx < 0) idx = 0;
            string next = TIER_CYCLE[(idx + 1) % TIER_CYCLE.Length];
            cardTierMap[key] = next;
            ApiClient.SetCardTier(MatchTracker.LocalSteamId, cardName, filterStr, next);
            ApplyRowTierVisuals(row, next);
            // No `dirty = true` — re-sort would shift cards mid-click and the
            // user would end up cycling a different card on their next tap.
        }
        // Tier badge background colors. S = pop red, A = orange, ... F = grey.
        private static Color GetTierColor(string t){switch(t){case "S":return new Color(0.95f,0.30f,0.30f,0.90f);case "A":return new Color(1.00f,0.55f,0.22f,0.90f);case "B":return new Color(0.95f,0.85f,0.30f,0.90f);case "C":return new Color(0.45f,0.85f,0.45f,0.90f);case "D":return new Color(0.45f,0.70f,0.95f,0.90f);case "E":return new Color(0.65f,0.55f,0.95f,0.90f);case "F":return new Color(0.55f,0.55f,0.55f,0.90f);default:return new Color(0.18f,0.20f,0.24f,0.85f);}}

        // Compact stat line for one cell on the tier-list image. Pulls the
        // first 2 CardInfoStats off the matching CardInfo. Layered lookup
        // mirrors the popup: try CardChoice.instance.cards first (always-loaded
        // global registry), then Resources.FindObjectsOfTypeAll. Match against
        // canonical name + GO name + cardName field.
        private static string BuildCellStatLine(string cardName)
        {
            try
            {
                if (string.IsNullOrEmpty(cardName)) return "";
                string canonical = CardRarityLookup.GetCanonicalName(cardName) ?? cardName;
                string lcA = (cardName ?? "").ToLowerInvariant().Replace(" ", "");
                string lcB = canonical.ToLowerInvariant().Replace(" ", "");
                Component found = null;
                Component MatchOne(IEnumerable arr)
                {
                    if (arr == null) return null;
                    foreach (var c in arr)
                    {
                        var comp = c as Component;
                        if (comp == null) continue;
                        string goName = comp.gameObject.name?.Replace("(Clone)", "").Trim() ?? "";
                        string display = comp.GetType().GetField("cardName", BindingFlags.Public | BindingFlags.Instance)?.GetValue(comp) as string ?? "";
                        if (goName.ToLowerInvariant().Replace(" ", "") == lcA
                            || goName.ToLowerInvariant().Replace(" ", "") == lcB
                            || display.ToLowerInvariant().Replace(" ", "") == lcA
                            || display.ToLowerInvariant().Replace(" ", "") == lcB)
                            return comp;
                    }
                    return null;
                }
                // Path 1: CardChoice.instance.cards (always loaded)
                var ccType = AppDomain.CurrentDomain.GetAssemblies()
                    .Select(a => a.GetType("CardChoice")).FirstOrDefault(t => t != null);
                if (ccType != null)
                {
                    object cc = ccType.GetField("instance", BindingFlags.Public | BindingFlags.Static)?.GetValue(null);
                    var cardsArr = ccType.GetField("cards", BindingFlags.Public | BindingFlags.Instance)?.GetValue(cc) as Array;
                    found = MatchOne(cardsArr);
                }
                // Path 2: Resources fallback
                if (found == null) found = MatchOne(Resources.FindObjectsOfTypeAll<CardInfo>());
                // Path 3: hardcoded stats dict fallback (cards where Resources
                // didn't have the prefab loaded — Rico/Leech/etc).
                if (found == null) return BuildStatBlockFromFallback(cardName, 8);
                var sField = found.GetType().GetField("cardStats", BindingFlags.Public | BindingFlags.Instance)
                          ?? found.GetType().GetField("stats", BindingFlags.Public | BindingFlags.Instance);
                var arr = sField?.GetValue(found) as Array;
                // CardInfo found but its stats array is null/empty — fall back
                // to the hardcoded dict (some cards' stats are populated at
                // runtime by their effect components, not on CardInfo itself).
                if (arr == null || arr.Length == 0) return BuildStatBlockFromFallback(cardName, 8);
                // Snip — apply normalization to the live-stat path below.
                var sb = new StringBuilder();
                int shown = 0;
                // Show every non-empty stat — taller cell has room. Earlier
                // 2-stat cap left out the most informative parts of cards
                // like Spray (4 stats) and Demonic Pact (3 stats).
                for (int i = 0; i < arr.Length && shown < 8; i++)
                {
                    var s = arr.GetValue(i);
                    if (s == null) continue;
                    var st = s.GetType();
                    string stat = (st.GetField("stat", BindingFlags.Public | BindingFlags.Instance)?.GetValue(s) as string ?? "").Trim();
                    string amount = (st.GetField("amount", BindingFlags.Public | BindingFlags.Instance)?.GetValue(s) as string ?? "").Trim();
                    var posObj = st.GetField("positive", BindingFlags.Public | BindingFlags.Instance)?.GetValue(s);
                    bool positive = posObj is bool pb ? pb : true;
                    if (string.IsNullOrEmpty(stat) && string.IsNullOrEmpty(amount)) continue;
                    string col = positive ? "#88FF88" : "#FF8888";
                    if (sb.Length > 0) sb.Append("\n");
                    // Normalize the stat label so DMG/DAMAGE/etc all render
                    // consistently across cards.
                    string statNorm = NormalizeStatLabel(stat);
                    string statShort = statNorm.Length > 16 ? statNorm.Substring(0, 14) + "…" : statNorm;
                    sb.Append("<color=").Append(col).Append(">").Append(amount).Append("</color> ").Append(statShort);
                    shown++;
                }
                return sb.ToString();
            }
            catch { return ""; }
        }

        // ── Export tier list as fullscreen PNG ────────────────────
        // Builds a temporary fullscreen overlay with every card grouped by
        // tier, captures via ScreenCapture.CaptureScreenshot, surfaces the
        // saved path. Mirrors the "tierlist maker" community tool but with
        // our own per-card stats baked in.
        private static GameObject tierExportPanel;
        public static void ExportCardTierList()
        {
            if (Plugin.Instance == null) return;
            try { Plugin.Instance.StartCoroutine(ExportTierListCoroutine()); }
            catch (Exception ex) { Plugin.Log.LogWarning($"[TIER-EXPORT] failed: {ex.Message}"); }
        }

        private static System.Collections.IEnumerator ExportTierListCoroutine()
        {
            // Portrait export via offscreen World-Space canvas + Camera +
            // RenderTexture. Earlier versions used ScreenCapture which is
            // locked to the player's monitor aspect (always landscape on a
            // 1920x1080 screen). RenderTexture lets us pick any output size,
            // so we render a tall portrait PNG (1280×N) regardless of the
            // host screen.
            if (tierExportPanel != null) UnityEngine.Object.Destroy(tierExportPanel);
            tierExportPanel = new GameObject("CR_TierExport");
            tierExportPanel.hideFlags = HideFlags.HideAndDontSave;
            // Park the offscreen canvas FAR from any in-game camera's frustum
            // so it can't accidentally render in the live view.
            tierExportPanel.transform.position = new Vector3(50000f, 50000f, 0f);

            // Reusable bg holder — a World-Space canvas, root of the export.
            var canvasComp = tierExportPanel.AddComponent(UIFactory.tCanvas);
            try
            {
                var rmProp = UIFactory.tCanvas.GetProperty("renderMode", BindingFlags.Public | BindingFlags.Instance);
                if (rmProp != null) rmProp.SetValue(canvasComp, Enum.ToObject(rmProp.PropertyType, 2)); // 2 = WorldSpace
                var sortProp = UIFactory.tCanvas.GetProperty("sortingOrder", BindingFlags.Public | BindingFlags.Instance);
                if (sortProp != null) sortProp.SetValue(canvasComp, 30000);
            }
            catch { }
            // GraphicRaycaster optional for rendering-only canvas — skip.

            var rootRT = tierExportPanel.GetComponent<RectTransform>();
            if (rootRT == null) rootRT = tierExportPanel.AddComponent<RectTransform>();
            // 3000 wide × 12 cells per row. Smaller cells (220×330
            // card art + 2 text rows) compress the vertical height so
            // the final image lands close to square aspect rather than
            // tall portrait.
            rootRT.sizeDelta = new Vector2(3000, 6000);  // height shrinks after layout
            rootRT.localScale = Vector3.one;

            var bg = UIFactory.CreatePanel("BG", tierExportPanel.transform, new Color(0.07f, 0.08f, 0.10f, 1f));
            var bgRT = bg.GetComponent<RectTransform>();
            bgRT.anchorMin = Vector2.zero; bgRT.anchorMax = Vector2.one;
            bgRT.offsetMin = Vector2.zero; bgRT.offsetMax = Vector2.zero;
            UIFactory.AddVLG(bg, spacing: 14, padL: 24, padR: 24, padT: 18, padB: 18);
            // ContentSizeFitter on the bg so the bg's preferredHeight tracks
            // the children's stacked heights — used to size the RenderTexture.
            try
            {
                Type csfType = null;
                foreach (var asm in AppDomain.CurrentDomain.GetAssemblies())
                {
                    csfType = asm.GetType("UnityEngine.UI.ContentSizeFitter");
                    if (csfType != null) break;
                }
                if (csfType != null)
                {
                    var csf = bg.AddComponent(csfType);
                    var ft = csfType.GetProperty("verticalFit", BindingFlags.Public | BindingFlags.Instance);
                    if (ft != null) ft.SetValue(csf, Enum.ToObject(ft.PropertyType, 2)); // PreferredSize
                }
            }
            catch { }

            // Title — sized for the 1600px-wide canvas, big enough to
            // read on phone display after ~0.67x scaling.
            string filterStr = cardFilter == 1 ? "Ranked" : cardFilter == 2 ? "Casual" : "All";
            UIFactory.CreateText("TXTitle", bg.transform,
                $"<b>Sid's Competitive Rounds  ·  Card Tier List</b>  <color=#888>({filterStr})</color>",
                36f, C_WHITE, UIFactory.AlignMidLeft, sizeDelta: new Vector2(2900, 52));

            // Group cards by tier.
            var cards = ApiClient.CachedCardStats ?? new List<ApiClient.CardStatData>();
            // Merge duplicates same as RefreshCardStats.
            var merged = new List<ApiClient.CardStatData>();
            var seen = new Dictionary<string, int>(StringComparer.OrdinalIgnoreCase);
            foreach (var c in cards)
            {
                string key = (c.card_name ?? "?").ToLower().Replace(" ", "");
                if (seen.ContainsKey(key))
                {
                    var e = merged[seen[key]];
                    e.times_picked += c.times_picked; e.wins_with_card += c.wins_with_card;
                    e.win_rate = e.times_picked > 0 ? (float)e.wins_with_card / e.times_picked : 0;
                    if ((e.card_rarity == null || e.card_rarity == "Unknown") && !string.IsNullOrEmpty(c.card_rarity) && c.card_rarity != "Unknown") e.card_rarity = c.card_rarity;
                }
                else { seen[key] = merged.Count; merged.Add(new ApiClient.CardStatData { card_name = c.card_name, card_rarity = c.card_rarity, times_picked = c.times_picked, wins_with_card = c.wins_with_card, win_rate = c.win_rate, times_offered = c.times_offered, pass_rate = c.pass_rate }); }
            }
            string[] tierOrder = new[] { "S", "A", "B", "C", "D", "E", "F", "" };
            var byTier = new Dictionary<string, List<ApiClient.CardStatData>>();
            foreach (var t in tierOrder) byTier[t] = new List<ApiClient.CardStatData>();
            foreach (var c in merged)
            {
                string t = cardTierMap.TryGetValue(CardTierKey(cardFilter, c.card_name), out var tv) ? tv : "";
                if (!byTier.ContainsKey(t)) t = "";
                byTier[t].Add(c);
            }

            // Layout — 3000 wide × 12 cells per row. Smaller cells
            // shrink the row count so the final image lands close to
            // square instead of tall portrait. Each cell is 220×330
            // card art + ## played + ##% won.
            const int CANVAS_W = 3000;
            const int BADGE_W = 130;
            const int CELL_W = 226;
            const int CELL_H = 410;       // 330 image + 30 + 30 + 8 spacing + 12 pad
            const int IMG_W = 220, IMG_H = 330;
            const int CELL_GAP = 8;
            int cardsAreaW = CANVAS_W - 48 - BADGE_W - 14;
            int cellsPerRow = Math.Max(3, cardsAreaW / (CELL_W + CELL_GAP)); // = 6

            // Reflected setters for UnityEngine.UI.Image — used to bind
            // the loaded card Sprite to a fresh Image component on each
            // cell.
            var pImgSprite = UIFactory.tImage.GetProperty("sprite", BindingFlags.Public | BindingFlags.Instance);
            var pImgPreserve = UIFactory.tImage.GetProperty("preserveAspect", BindingFlags.Public | BindingFlags.Instance);
            var pImgColor = UIFactory.tImage.GetProperty("color", BindingFlags.Public | BindingFlags.Instance);

            foreach (var tier in tierOrder)
            {
                var list = byTier[tier];
                if (list.Count == 0) continue;
                Color tc = string.IsNullOrEmpty(tier) ? new Color(0.30f, 0.32f, 0.36f, 0.95f) : GetTierColor(tier);
                int rowsNeeded = (list.Count + cellsPerRow - 1) / cellsPerRow;
                int tierBlockH = rowsNeeded * (CELL_H + 6) + 12;

                // Tier row container — badge on the left, wrapping cards on the right.
                var tierGO = new GameObject($"T_{tier}");
                tierGO.transform.SetParent(bg.transform, false);
                tierGO.AddComponent<RectTransform>();
                UIFactory.AddHLG(tierGO, spacing: 8, padL: 8, padR: 8, padT: 6, padB: 6);
                UIFactory.AddLE(tierGO, prefH: tierBlockH, minH: tierBlockH, flexH: 0);

                // Tier badge.
                var badge = UIFactory.CreatePanel($"B_{tier}", tierGO.transform, tc);
                UIFactory.AddLE(badge, prefW: BADGE_W, minW: BADGE_W, prefH: tierBlockH - 12, minH: tierBlockH - 12, flexW: 0);
                UIFactory.CreateText("BL", badge.transform, $"<b>{(string.IsNullOrEmpty(tier) ? "Unranked" : tier)}</b>",
                    string.IsNullOrEmpty(tier) ? 36f : 84f, Color.black,
                    UIFactory.AlignMidCenter, sizeDelta: new Vector2(BADGE_W, tierBlockH - 12));

                // Cards container.
                var cardsCol = new GameObject($"R_{tier}");
                cardsCol.transform.SetParent(tierGO.transform, false);
                cardsCol.AddComponent<RectTransform>();
                UIFactory.AddVLG(cardsCol, spacing: 6, padL: 4, padR: 4, padT: 0, padB: 0);
                UIFactory.AddLE(cardsCol, flexW: 1, prefH: tierBlockH - 12, minH: tierBlockH - 12, flexH: 0);

                GameObject curRow = null;
                int curIdx = 0;
                foreach (var c in list)
                {
                    if (curRow == null || curIdx >= cellsPerRow)
                    {
                        curRow = new GameObject($"row{list.IndexOf(c)}");
                        curRow.transform.SetParent(cardsCol.transform, false);
                        curRow.AddComponent<RectTransform>();
                        UIFactory.AddHLG(curRow, spacing: CELL_GAP);
                        UIFactory.AddLE(curRow, prefH: CELL_H, minH: CELL_H, flexH: 0);
                        curIdx = 0;
                    }
                    var cell = UIFactory.CreatePanel($"C_{c.card_name}", curRow.transform,
                        new Color(tc.r, tc.g, tc.b, 0.22f));
                    UIFactory.AddVLG(cell, spacing: 4, padL: 4, padR: 4, padT: 6, padB: 6);
                    UIFactory.AddLE(cell, prefW: CELL_W, minW: CELL_W, prefH: CELL_H, minH: CELL_H, flexW: 0);

                    // Card art — fills most of the cell. preserveAspect=true
                    // so non-2:3 art letterboxes rather than distorts.
                    Sprite sp = CardImageLoader.GetSprite(c.card_name);
                    var imgGO = new GameObject("Img");
                    imgGO.transform.SetParent(cell.transform, false);
                    imgGO.AddComponent<RectTransform>();
                    var imgComp = imgGO.AddComponent(UIFactory.tImage);
                    if (sp != null)
                    {
                        pImgSprite?.SetValue(imgComp, sp);
                        pImgPreserve?.SetValue(imgComp, true);
                        pImgColor?.SetValue(imgComp, Color.white);
                    }
                    else
                    {
                        // Missing-art fallback — solid colored placeholder
                        // with the card name written across it.
                        pImgColor?.SetValue(imgComp, new Color(0.20f, 0.22f, 0.26f, 1f));
                        UIFactory.CreateText("Miss", imgGO.transform,
                            $"<b>{Trunc(c.card_name ?? "?", 14)}</b>",
                            22f, C_WHITE, UIFactory.AlignMidCenter, sizeDelta: new Vector2(IMG_W - 8, 60));
                    }
                    UIFactory.AddLE(imgGO, prefW: IMG_W, minW: IMG_W, prefH: IMG_H, minH: IMG_H, flexW: 0, flexH: 0);

                    // Picks count.
                    var playedTxt = UIFactory.CreateText("P", cell.transform,
                        $"<b>{c.times_picked} played</b>",
                        26f, C_WHITE, UIFactory.AlignMidCenter, sizeDelta: new Vector2(CELL_W - 8, 30));
                    UIFactory.SetBold(playedTxt, true);
                    // Win % colored by performance band.
                    float wr = c.win_rate * 100f;
                    string wrCol = wr >= 55 ? "#88FF88" : wr <= 45 ? "#FF8888" : "#FFFFFF";
                    var wrTxt = UIFactory.CreateText("W", cell.transform,
                        $"<b><color={wrCol}>{wr:F0}% won</color></b>",
                        26f, C_WHITE, UIFactory.AlignMidCenter, sizeDelta: new Vector2(CELL_W - 8, 30));
                    UIFactory.SetBold(wrTxt, true);

                    curIdx++;
                }
                // Pad the last row so cells aren't stretched if HLG forceExpandW is on.
                while (curRow != null && curIdx < cellsPerRow)
                {
                    var pad = new GameObject("pad");
                    pad.transform.SetParent(curRow.transform, false);
                    pad.AddComponent<RectTransform>();
                    UIFactory.AddLE(pad, prefW: CELL_W, minW: CELL_W, flexW: 0);
                    curIdx++;
                }
            }

            // (Legend dropped — inline labels "## played" / "##% won" make the
            // tier-color guide redundant. Tier-letter badges on the left of
            // each row already convey the ranking.)

            // Bottom watermark — Steam name on the left (claims the tier
            // list as theirs), mod info on the right. Both dark grey italic
            // matching the user's ask.
            string steamName = MatchTracker.LocalDisplayName;
            if (string.IsNullOrEmpty(steamName) || steamName == "unknown") steamName = "Anonymous";
            var wm = new GameObject("WM"); wm.transform.SetParent(bg.transform, false); wm.AddComponent<RectTransform>();
            UIFactory.AddHLG(wm, spacing: 0); UIFactory.AddLE(wm, prefH: 50, flexH: 0);
            UIFactory.CreateText("WMSteam", wm.transform,
                $"<color=#888><i>{steamName}'s tier list</i></color>",
                26f, C_DIM, UIFactory.AlignMidLeft, sizeDelta: new Vector2(1400, 50));
            var wmSp = new GameObject("S"); wmSp.transform.SetParent(wm.transform, false); wmSp.AddComponent<RectTransform>();
            UIFactory.AddLE(wmSp, flexW: 1);
            UIFactory.CreateText("WMTxt", wm.transform,
                $"<color=#888><i>Sid's Competitive Rounds mod  ·  v{Plugin.ModVersion}  ·  {DateTime.Now:yyyy-MM-dd}</i></color>",
                22f, C_DIM, UIFactory.AlignMidRight, sizeDelta: new Vector2(1500, 50));

            // Wait two frames for the LayoutGroups + ContentSizeFitter to
            // push the bg's preferred height into its RectTransform.
            yield return null;
            yield return null;
            try
            {
                Type canvasT = null;
                foreach (var asm in AppDomain.CurrentDomain.GetAssemblies())
                { canvasT = asm.GetType("UnityEngine.Canvas"); if (canvasT != null) break; }
                canvasT?.GetMethod("ForceUpdateCanvases", BindingFlags.Public | BindingFlags.Static)?.Invoke(null, null);
            }
            catch { }
            yield return null;

            // Resolve final canvas height from the bg's measured preferred size.
            int finalH = Mathf.CeilToInt(bgRT.rect.height);
            if (finalH < 600) finalH = 600;
            // Resize the canvas root so the world rect matches the content.
            rootRT.sizeDelta = new Vector2(CANVAS_W, finalH);
            yield return null;

            string outDir;
            try
            {
                outDir = System.IO.Path.GetFullPath(System.IO.Path.Combine(Application.dataPath, "..", "CompetitiveRoundsTierLists"));
                System.IO.Directory.CreateDirectory(outDir);
            }
            catch { outDir = Application.persistentDataPath; }
            string fn = $"tierlist-{filterStr}-{DateTime.Now:yyyyMMdd-HHmmss}.png";
            string fullPath = System.IO.Path.Combine(outDir, fn);

            // RenderTexture path: spawn a temp orthographic camera looking at
            // the offscreen canvas, render into a texture sized to the
            // canvas dimensions, ReadPixels → EncodeToPNG → file. Bypasses
            // ScreenCapture entirely (which is locked to monitor aspect).
            GameObject camGO = null;
            RenderTexture renderT = null;
            Texture2D tex = null;
            try
            {
                camGO = new GameObject("CR_TierCam");
                camGO.hideFlags = HideFlags.HideAndDontSave;
                camGO.transform.position = new Vector3(50000f, 50000f, -10f);
                var cam = camGO.AddComponent<Camera>();
                cam.orthographic = true;
                cam.orthographicSize = finalH / 2f;
                cam.aspect = (float)CANVAS_W / Math.Max(1, finalH);
                cam.clearFlags = CameraClearFlags.SolidColor;
                cam.backgroundColor = new Color(0.07f, 0.08f, 0.10f, 1f);
                cam.cullingMask = ~0;
                cam.nearClipPlane = 0.1f;
                cam.farClipPlane = 100f;

                renderT = new RenderTexture(CANVAS_W, finalH, 24);
                cam.targetTexture = renderT;
                cam.Render();

                var prevActive = RenderTexture.active;
                RenderTexture.active = renderT;
                tex = new Texture2D(CANVAS_W, finalH, TextureFormat.RGB24, false);
                tex.ReadPixels(new Rect(0, 0, CANVAS_W, finalH), 0, 0);
                tex.Apply();
                RenderTexture.active = prevActive;

                byte[] png = tex.EncodeToPNG();
                System.IO.File.WriteAllBytes(fullPath, png);
                Plugin.Log.LogInfo($"[TIER-EXPORT] saved {CANVAS_W}×{finalH} → {fullPath}");
            }
            catch (Exception ex) { Plugin.Log.LogWarning($"[TIER-EXPORT] capture failed: {ex.Message}"); }
            finally
            {
                try { if (camGO != null) UnityEngine.Object.Destroy(camGO); } catch { }
                try { if (renderT != null) UnityEngine.Object.Destroy(renderT); } catch { }
                try { if (tex != null) UnityEngine.Object.Destroy(tex); } catch { }
            }

            try { if (tierExportPanel != null) UnityEngine.Object.Destroy(tierExportPanel); } catch { }
            tierExportPanel = null;

            CompetitiveUI.ShowNotification($"Tier list saved to {fullPath}", new Color(0.4f, 0.9f, 0.4f), 12f);
            Plugin.Log.LogInfo($"[TIER-EXPORT] done — {fullPath}");
        }
        private static Color GetRarityColor(string r){if(string.IsNullOrEmpty(r))return C_LABEL;switch(r.ToLower()){case "common":return C_COMMON;case "uncommon":return C_UNCOMMON;case "rare":return C_RARE;default:return C_LABEL;}}

        // -- Chat --------------------------------------------------
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

        // -- Local chat mute (per-display-name) -----------------
        // Stored as a pipe-delimited list in Plugin.MutedChatNames (BepInEx config).
        // Command syntax: "/mute name", "/unmute name", "/muted".
        // Filter applied in OnChatMessage; commands handled in CompetitiveUI's chat input submit.

        private static HashSet<string> _mutedCache;

        private static HashSet<string> GetMutedSet()
        {
            // Rebuild on each access - config writes are infrequent and the list is small.
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
            // Use ASCII parens instead of CJK brackets so the result stays in the Gravity SDF glyph range
            // (Cyrillic + many Latin locales don't have the U+3008/U+3009 variants as fallbacks).
            return s.Replace("<", "(").Replace(">", ")");
        }

        /// <summary>Numeric field parser - tolerates nulls, whitespace, integers and floats.</summary>
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

        private static void RefreshQueueUI(){if(txtRankedStatus==null)return;bool ranked=Plugin.RankedEnabled.Value;var qs=ApiClient.CurrentQueueState;UIFactory.SetText(txtRankedStatus,ranked?"RANKED: ON":"RANKED: OFF");UIFactory.SetColor(txtRankedStatus,ranked?C_GREEN:Color.gray);rankOnBtn.SetActive(!ranked);rankOffBtn.SetActive(ranked&&!inGameMode);bool inRankedMatch=GameStateWatcher.IsInMatch&&GameStateWatcher.MatchIsRanked;qSearchBtn.SetActive(ranked&&qs==ApiClient.QueueState.Idle&&!inRankedMatch);qCancelBtn.SetActive(ranked&&qs==ApiClient.QueueState.Searching);if(qs==ApiClient.QueueState.Searching){var poll=ApiClient.LastPollData;string line="Searching...";if(poll!=null&&poll.status=="searching"){int m=poll.wait_time/60,sec=poll.wait_time%60;line=$"Searching... {(m>0?$"{m}m ":"")}{sec}s  +/-{poll.elo_range}"+(poll.queue_size>1?$"  ({poll.queue_size} in queue)":"");}UIFactory.SetText(txtQueueInfo,line);UIFactory.SetColor(txtQueueInfo,C_BLUE);((txtQueueInfo as Component)?.gameObject)?.SetActive(true);}else if(qs==ApiClient.QueueState.Idle&&ranked){int qc=ApiClient.CachedQueueSearching;if(qc>0){UIFactory.SetText(txtQueueInfo,$"{qc} searching");UIFactory.SetColor(txtQueueInfo,C_GREEN);}else{UIFactory.SetText(txtQueueInfo,"0 in queue");UIFactory.SetColor(txtQueueInfo,C_DIM);}((txtQueueInfo as Component)?.gameObject)?.SetActive(true);}else{UIFactory.SetText(txtQueueInfo,"");((txtQueueInfo as Component)?.gameObject)?.SetActive(false);}if(qs==ApiClient.QueueState.Matched||qs==ApiClient.QueueState.ReadySent){qMatchPanel.SetActive(true);var poll=ApiClient.LastPollData;if(poll!=null){string oppInfo=$"MATCH FOUND!  vs {poll.opponent_name} ({poll.opponent_rating:F0})";if(qs==ApiClient.QueueState.ReadySent&&poll.opponent_ready)oppInfo+="  [Opponent Ready]";UIFactory.SetText(txtMatchFound,oppInfo);}bool readySent=qs==ApiClient.QueueState.ReadySent;readyBtn.SetActive(!readySent);connectLabel.SetActive(readySent);if(readySent&&txtConnectLabel!=null&&poll!=null){string waitTxt=!string.IsNullOrEmpty(poll.opponent_name)?$"Waiting for {poll.opponent_name} ({poll.opponent_rating:F0})...":"Waiting for opponent...";if(poll.opponent_ready)waitTxt=$"{poll.opponent_name} ready! Joining...";UIFactory.SetText(txtConnectLabel,waitTxt);}declineBtn.SetActive(true);}else qMatchPanel.SetActive(false);}

        private static int CalcStreak(List<ApiClient.MatchHistoryEntry> m){if(m==null||m.Count==0)return 0;bool t=m[0].won;int c=0;for(int i=0;i<m.Count;i++){if(m[i].won==t)c++;else break;}return t?c:-c;}
        private static string Trunc(string s,int max){if(string.IsNullOrEmpty(s))return "";return s.Length<=max?s:s.Substring(0,max-2)+"..";}
        private struct SGroup{public string series_id;public List<ApiClient.MatchHistoryEntry> matches;}
        private static List<SGroup> GroupBySeries(List<ApiClient.MatchHistoryEntry> ranked){var groups=new List<SGroup>();SGroup cur=new SGroup{series_id=null,matches=null};foreach(var m in ranked){string sid=m.series_id;bool has=!string.IsNullOrEmpty(sid)&&sid!="null";if(has&&cur.matches!=null&&cur.series_id==sid)cur.matches.Add(m);else{if(cur.matches!=null&&cur.matches.Count>0)groups.Add(cur);cur=new SGroup{series_id=has?sid:null,matches=new List<ApiClient.MatchHistoryEntry>{m}};}}if(cur.matches!=null&&cur.matches.Count>0)groups.Add(cur);return groups;}
        internal static Type TImage=>UIFactory.tImage;internal static Type TButton=>UIFactory.tButton;

        // -- Admin tab ------------------------------------------
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
            // Rebuild button click handlers - capture this entry's id.
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

        // Replace a Button's onClick listeners - clears via Button.onClick.RemoveAllListeners then re-adds.
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


        // -- Tournaments Tab ----------------------------------------------
        //
        // Layout: 2 columns.
        //   Left:  status header, signup/unsign + discord-link gate, penalty,
        //          time-voting checklist (during voting), force-start button,
        //          ready-up button (during running), my next match callout.
        //   Right: signups list (seed + name + ~ speculative + ready dot),
        //          bracket view (round-by-round text list, compact).
        //
        // Refresh cadence: on tab switch (force=true) + every 10s while tab is
        // open via MaybeRefreshTournament. Heartbeat ready-up fires every 20s
        // while the local player has a ready match and the local ready state
        // is stale >45s.

        private static object txtTState, txtTWhen, txtTInstructions, txtTPenalty, txtTForceCount, txtTMyMatch, txtTDiscordGate, txtTMyHistory, txtTRoomCode, txtTTzNow;
        private static GameObject txtTSignupBtn, txtTUnsignupBtn, txtTReadyBtn, txtTForceBtn, txtTTzButton, txtTDateFmtButton, txtTReconnectBtn, tSubTabSyncBtn, tSubTabAsyncBtn;
        private static GameObject tTimeVoteRow, tSignupList, tBracketList, tMyMatchPanel, tHistoryList, tVoteBoxPanel;
        private static List<GameObject> tHistoryRowPool = new List<GameObject>();
        private static List<object> tHistoryRowTexts = new List<object>();
        // Match IDs we've already set PendingRankedRoom for, so the 10s refresh loop
        // doesn't re-dispatch the same match on every tick.
        private static HashSet<string> _tournamentDispatchedMatches = new HashSet<string>();
        private static List<GameObject> tSlotToggles = new List<GameObject>();
        private static List<bool> tSlotChecked = new List<bool>();
        private static List<object> tSlotLabels = new List<object>();
        private static List<GameObject> tSignupRowPool = new List<GameObject>();
        private static List<object[]> tSignupRowTexts = new List<object[]>();  // [seedTxt, nameTxt, statusTxt]
        private static List<GameObject> tBracketRowPool = new List<GameObject>();
        private static List<object> tBracketRowTexts = new List<object>();
        // Per-row "purpose" - what the row represents on the current refresh.
        // Populated in RefreshTournaments' bracket render so the row's click
        // handler can look up its group key and toggle _tBracketExpanded.
        private struct BracketRowPurpose { public bool isHeader; public string groupKey; }
        private static List<BracketRowPurpose> _tBracketRowPurposes = new List<BracketRowPurpose>();
        // Per-group expansion state, keyed like "W-1", "L-3", "GF", "GF_RESET".
        // Missing key = collapsed.
        private static Dictionary<string, bool> _tBracketExpanded = new Dictionary<string, bool>();
        // Seeded on first render per tournament_id so re-opening the tab
        // doesn't forget the player's click-expand choices mid-session.
        private static string _tBracketSeededForTid = null;
        private static float tTournamentRefreshAt, tReadyHeartbeatAt;

        public static void MaybeRefreshTournament()
        {
            if (currentTab != 7) return;
            if (Time.unscaledTime >= tTournamentRefreshAt)
            {
                tTournamentRefreshAt = Time.unscaledTime + 10f;
                ApiClient.FetchTournamentCurrent(MatchTracker.LocalSteamId);
            }
            // Heartbeat moved to ApiClient.TournamentHeartbeatLoop - runs
            // plugin-level so it keeps firing during gameplay (when the
            // competitive UI is closed).
        }

        private static GameObject BuildTournamentsTab(Transform parent)
        {
            var panel = new GameObject("Tournaments");
            panel.transform.SetParent(parent, false);
            panel.AddComponent<RectTransform>();
            UIFactory.AddHLG(panel, spacing: 8);
            UIFactory.AddLE(panel, flexH: 1);

            // -- LEFT column: status, signup, voting, ready --
            var left = new GameObject("TLeft"); left.transform.SetParent(panel.transform, false);
            left.AddComponent<RectTransform>(); UIFactory.AddVLG(left, spacing: 6);
            UIFactory.AddLE(left, prefW: 430, minW: 360);

            // Sync / Async sub-tab bar. Switches ApiClient.TournamentKind and
            // refetches. Layout lives at the top of the left column so it's
            // visible without consuming a full-width row in the HLG panel.
            var subTabs = new GameObject("TSubTabs"); subTabs.transform.SetParent(left.transform, false);
            subTabs.AddComponent<RectTransform>();
            UIFactory.AddHLG(subTabs, spacing: 4, forceExpandH: true);
            UIFactory.AddLE(subTabs, prefH: 30, flexH: 0);
            tSubTabSyncBtn = UIFactory.CreateButton("TSTSy", subTabs.transform, "SYNC (weekly)", 14f, C_WHITE, C_TABACT, () =>
            {
                if (ApiClient.TournamentKind == "sync") return;
                ApiClient.TournamentKind = "sync";
                ApiClient.FetchTournamentCurrent(MatchTracker.LocalSteamId, force: true);
                dirty = true;
            }, sizeDelta: new Vector2(180, 26));
            tSubTabAsyncBtn = UIFactory.CreateButton("TSTAs", subTabs.transform, "ASYNC (6-week)", 14f, C_LABEL, C_TAB, () =>
            {
                if (ApiClient.TournamentKind == "async") return;
                ApiClient.TournamentKind = "async";
                ApiClient.FetchTournamentCurrent(MatchTracker.LocalSteamId, force: true);
                dirty = true;
            }, sizeDelta: new Vector2(180, 26));

            var hdrBox = UIFactory.CreatePanel("THdr", left.transform, C_PANEL);
            UIFactory.AddVLG(hdrBox, spacing: 2, padL: 10, padR: 10, padT: 6, padB: 6);
            UIFactory.AddLE(hdrBox, flexH: 0);
            txtTState = UIFactory.CreateText("TS", hdrBox.transform, "Loading...", 22f, C_GOLD, UIFactory.AlignMidLeft, sizeDelta: new Vector2(380, 28));
            UIFactory.SetBold(txtTState, true);
            txtTWhen = UIFactory.CreateText("TW", hdrBox.transform, "", 15f, C_SUB, UIFactory.AlignMidLeft, sizeDelta: new Vector2(380, 22));
            UIFactory.SetWordWrap(txtTWhen, true);
            txtTInstructions = UIFactory.CreateText("TI", hdrBox.transform,
                _SYNC_INSTRUCTIONS,
                13f, C_LABEL, UIFactory.AlignMidLeft, sizeDelta: new Vector2(400, 560));
            UIFactory.SetWordWrap(txtTInstructions, true);
            // Zero out the baked LayoutElement prefH so the TMP text's own ILayoutElement
            // (which reports actual rendered height) drives the parent panel size. Without
            // this, the hdrBox sizes to the baked 560 even if content fits in less - and,
            // more importantly, the panel stops clamping content that WOULD overflow.
            // Same pattern the chat log uses (see RefreshMyStats for the precedent).
            { var le = (txtTInstructions as Component)?.gameObject.GetComponent(UIFactory.tLE);
              if (le != null) UIFactory.tLE.GetProperty("preferredHeight", BindingFlags.Public | BindingFlags.Instance)?.SetValue(le, -1f); }

            // Timezone selector - tap to cycle through presets.
            var tzRow = new GameObject("TZRow"); tzRow.transform.SetParent(left.transform, false);
            tzRow.AddComponent<RectTransform>();
            UIFactory.AddHLG(tzRow, spacing: 6, forceExpandH: true);
            UIFactory.AddLE(tzRow, prefH: 26, flexH: 0);
            UIFactory.CreateText("TZL", tzRow.transform, "Times in:", 14f, C_LABEL, UIFactory.AlignMidLeft, sizeDelta: new Vector2(80, 24));
            txtTTzButton = UIFactory.CreateButton("TZBtn", tzRow.transform, _TzLabel(), 14f, C_WHITE, C_BTN, () => _CycleTz(), sizeDelta: new Vector2(80, 24));
            UIFactory.CreateText("TDL", tzRow.transform, "fmt:", 14f, C_LABEL, UIFactory.AlignMidLeft, sizeDelta: new Vector2(40, 24));
            txtTDateFmtButton = UIFactory.CreateButton("TDFBtn", tzRow.transform, _DateFormat(), 14f, C_WHITE, C_BTN, () => _CycleDateFormat(), sizeDelta: new Vector2(60, 24));
            txtTTzNow = UIFactory.CreateText("TZN", tzRow.transform, "", 13f, new Color(0.8f, 0.9f, 1f), UIFactory.AlignMidLeft, sizeDelta: new Vector2(180, 24));

            // Signup action row
            var sRow = new GameObject("TSAct"); sRow.transform.SetParent(left.transform, false);
            sRow.AddComponent<RectTransform>();
            UIFactory.AddHLG(sRow, spacing: 6, forceExpandH: true);
            UIFactory.AddLE(sRow, prefH: 30, flexH: 0);
            txtTSignupBtn = UIFactory.CreateButton("TSign", sRow.transform, "Sign Up for Tournament", 15f, C_WHITE, new Color(0.22f, 0.50f, 0.30f, 0.95f),
                () =>
                {
                    var id = MatchTracker.LocalSteamId;
                    var t = ApiClient.CachedTournament;
                    if (t != null && !string.IsNullOrEmpty(t.tournament_id) && !string.IsNullOrEmpty(id) && id != "unknown")
                        ApiClient.TournamentSignup(t.tournament_id, id, MatchTracker.LocalDisplayName);
                }, sizeDelta: new Vector2(220, 28));
            txtTUnsignupBtn = UIFactory.CreateButton("TUns", sRow.transform, "Leave Signup", 15f, C_WHITE, new Color(0.50f, 0.20f, 0.20f, 0.95f),
                () =>
                {
                    var id = MatchTracker.LocalSteamId;
                    var t = ApiClient.CachedTournament;
                    if (t != null && !string.IsNullOrEmpty(t.tournament_id) && !string.IsNullOrEmpty(id) && id != "unknown")
                        ApiClient.TournamentUnsignup(t.tournament_id, id);
                }, sizeDelta: new Vector2(150, 28));
            txtTUnsignupBtn.SetActive(false);
            txtTDiscordGate = UIFactory.CreateText("TDG", sRow.transform, "", 13f, new Color(1f, 0.6f, 0.4f), UIFactory.AlignMidLeft, sizeDelta: new Vector2(260, 28));

            // Penalty line
            txtTPenalty = UIFactory.CreateText("TPen", left.transform, "", 14f, C_LABEL, UIFactory.AlignMidLeft, sizeDelta: new Vector2(400, 22));

            // Time-vote panel (visible during voting + signed up). The panel reference
            // is stored so RefreshTournaments can hide it entirely for async (which has
            // no scheduled_start_ts delay to vote on).
            tVoteBoxPanel = UIFactory.CreatePanel("TVoteBox", left.transform, C_PANEL);
            var voteBox = tVoteBoxPanel;
            UIFactory.AddVLG(voteBox, spacing: 2, padL: 10, padR: 10, padT: 6, padB: 6);
            UIFactory.AddLE(voteBox, flexH: 0);
            UIFactory.CreateText("TVH", voteBox.transform, "Vote on Start Time (multi-select)", 16f, C_SUB, UIFactory.AlignMidLeft, sizeDelta: new Vector2(380, 22));
            tTimeVoteRow = new GameObject("TVR"); tTimeVoteRow.transform.SetParent(voteBox.transform, false);
            tTimeVoteRow.AddComponent<RectTransform>(); UIFactory.AddVLG(tTimeVoteRow, spacing: 2);
            // 8 slot toggle rows, each: [ box ] label (votes: N)
            for (int i = 0; i < 8; i++)
            {
                int idx = i;
                var row = new GameObject($"Slot{i}"); row.transform.SetParent(tTimeVoteRow.transform, false);
                row.AddComponent<RectTransform>(); UIFactory.AddHLG(row, spacing: 6, forceExpandH: true);
                UIFactory.AddLE(row, prefH: 24, flexH: 0);
                var box = UIFactory.CreateButton($"Tog{i}", row.transform, "[ ]", 14f, C_WHITE, C_BTN, () =>
                {
                    if (tSlotChecked.Count > idx) {
                        tSlotChecked[idx] = !tSlotChecked[idx];
                        _tVoteLocalEdited = true;   // freeze server-sync until Save is pressed
                        dirty = true;
                    }
                }, sizeDelta: new Vector2(36, 22));
                tSlotToggles.Add(box);
                var lbl = UIFactory.CreateText($"Lbl{i}", row.transform, "", 14f, C_LABEL, UIFactory.AlignMidLeft, sizeDelta: new Vector2(320, 22));
                tSlotLabels.Add(lbl);
                tSlotChecked.Add(false);
            }
            var submitRow = new GameObject("TVSub"); submitRow.transform.SetParent(voteBox.transform, false);
            submitRow.AddComponent<RectTransform>(); UIFactory.AddHLG(submitRow, spacing: 6);
            UIFactory.AddLE(submitRow, prefH: 28, flexH: 0);
            UIFactory.CreateButton("TVSubmit", submitRow.transform, "Save Votes", 15f, C_WHITE, new Color(0.22f, 0.38f, 0.65f, 0.95f), () =>
            {
                var t = ApiClient.CachedTournament;
                if (t == null || string.IsNullOrEmpty(t.tournament_id)) return;
                var selected = new List<string>();
                for (int i = 0; i < tSlotChecked.Count && i < (t.time_slot_options?.Length ?? 0); i++)
                    if (tSlotChecked[i]) selected.Add(t.time_slot_options[i]);
                ApiClient.TournamentTimeVote(t.tournament_id, MatchTracker.LocalSteamId, selected.ToArray());
                // Server is now the source of truth; re-enable passive sync.
                _tVoteLocalEdited = false;
            }, sizeDelta: new Vector2(120, 26));
            txtTForceCount = UIFactory.CreateText("TFC", submitRow.transform, "", 13f, C_DIM, UIFactory.AlignMidLeft, sizeDelta: new Vector2(180, 26));
            txtTForceBtn = UIFactory.CreateButton("TFS", submitRow.transform, "Force Start", 15f, C_WHITE, new Color(0.55f, 0.35f, 0.15f, 0.95f), () =>
            {
                var t = ApiClient.CachedTournament;
                if (t != null && !string.IsNullOrEmpty(t.tournament_id))
                    ApiClient.TournamentForceStartVote(t.tournament_id, MatchTracker.LocalSteamId);
            }, sizeDelta: new Vector2(110, 26));

            // Ready-up + my-match panel (visible during running + I have a match)
            tMyMatchPanel = UIFactory.CreatePanel("TMM", left.transform, C_PANEL);
            UIFactory.AddVLG(tMyMatchPanel, spacing: 3, padL: 10, padR: 10, padT: 6, padB: 6);
            UIFactory.AddLE(tMyMatchPanel, flexH: 0);
            txtTMyMatch = UIFactory.CreateText("TMMTxt", tMyMatchPanel.transform, "", 17f, C_WHITE, UIFactory.AlignMidLeft, sizeDelta: new Vector2(400, 26));
            UIFactory.SetBold(txtTMyMatch, true); UIFactory.SetWordWrap(txtTMyMatch, true);
            // Room code is shown so players can manually rejoin via ROUNDS' private-lobby
            // flow if the auto-connect hits a region mismatch or transient Photon glitch.
            // The code matches what auto-connect uses: both paths are the same Photon room.
            txtTRoomCode = UIFactory.CreateText("TRC", tMyMatchPanel.transform, "", 14f, new Color(0.7f, 0.9f, 1f), UIFactory.AlignMidLeft, sizeDelta: new Vector2(400, 22));
            var matchBtnRow = new GameObject("TMBR"); matchBtnRow.transform.SetParent(tMyMatchPanel.transform, false);
            matchBtnRow.AddComponent<RectTransform>();
            UIFactory.AddHLG(matchBtnRow, spacing: 6, forceExpandH: true);
            UIFactory.AddLE(matchBtnRow, prefH: 28, flexH: 0);
            txtTReadyBtn = UIFactory.CreateButton("TRdy", matchBtnRow.transform, "Ready Up (heartbeat)", 15f, C_WHITE, new Color(0.22f, 0.50f, 0.30f, 0.95f), () =>
            {
                var t = ApiClient.CachedTournament;
                if (t != null && !string.IsNullOrEmpty(t.tournament_id))
                    ApiClient.TournamentReady(t.tournament_id, MatchTracker.LocalSteamId);
            }, sizeDelta: new Vector2(200, 26));
            // Reconnect button - clears the per-match dispatch memo so SetPendingRoom fires
            // again on the next refresh tick. Useful when auto-connect failed silently and
            // the player has already been moved back to the main menu.
            txtTReconnectBtn = UIFactory.CreateButton("TRC_btn", matchBtnRow.transform, "Reconnect to Match", 14f, C_WHITE, new Color(0.22f, 0.38f, 0.65f, 0.95f), () =>
            {
                var t = ApiClient.CachedTournament;
                if (t == null || t.matches == null) return;
                foreach (var m in t.matches)
                {
                    if ((m.status == "ready" || m.status == "active") &&
                        (m.p1_signup_id == t.my_signup_id || m.p2_signup_id == t.my_signup_id) &&
                        !string.IsNullOrEmpty(m.match_id))
                    {
                        string roomName = "sct-" + m.match_id.Replace("-", "").Substring(0, 12);
                        _tournamentDispatchedMatches.Remove(m.match_id);
                        Plugin.SetPendingRoom(roomName, t.photon_region);
                        CompetitiveUI.ShowNotification($"Reconnecting to {roomName} (region {t.photon_region ?? "default"})", new Color(0.5f, 0.8f, 1f));
                        break;
                    }
                }
            }, sizeDelta: new Vector2(170, 26));
            tMyMatchPanel.SetActive(false);

            // -- RIGHT column: signups + bracket --
            var right = new GameObject("TRight"); right.transform.SetParent(panel.transform, false);
            right.AddComponent<RectTransform>(); UIFactory.AddVLG(right, spacing: 4);
            UIFactory.AddLE(right, flexW: 1, flexH: 1);

            var signBox = UIFactory.CreatePanel("TSignBox", right.transform, C_PANEL);
            UIFactory.AddVLG(signBox, spacing: 2, padL: 8, padR: 8, padT: 6, padB: 6);
            UIFactory.AddLE(signBox, flexH: 1);
            UIFactory.CreateText("TSH", signBox.transform, "Signups", 18f, C_GOLD, UIFactory.AlignMidLeft, sizeDelta: new Vector2(280, 24));
            var sSv = UIFactory.CreateScrollView("TSSV", signBox.transform, spacing: 1);
            UIFactory.AddLE(sSv.scrollGO, flexH: 1);
            tSignupList = sSv.content;
            for (int i = 0; i < 24; i++)
            {
                var row = new GameObject($"TSig{i}"); row.transform.SetParent(tSignupList.transform, false);
                row.AddComponent<RectTransform>(); UIFactory.AddHLG(row, spacing: 6, forceExpandH: true);
                UIFactory.AddLE(row, prefH: 22, flexH: 0);
                var seedT = UIFactory.CreateText("sd", row.transform, "", 14f, C_GOLD, UIFactory.AlignMidCenter, sizeDelta: new Vector2(40, 22));
                var nameT = UIFactory.CreateText("nm", row.transform, "", 15f, C_WHITE, UIFactory.AlignMidLeft, sizeDelta: new Vector2(280, 22));
                var statT = UIFactory.CreateText("st", row.transform, "", 13f, C_DIM, UIFactory.AlignMidRight, sizeDelta: new Vector2(140, 22));
                tSignupRowPool.Add(row);
                tSignupRowTexts.Add(new object[] { seedT, nameT, statT });
                row.SetActive(false);
            }

            var brkBox = UIFactory.CreatePanel("TBrkBox", right.transform, C_PANEL);
            UIFactory.AddVLG(brkBox, spacing: 2, padL: 8, padR: 8, padT: 6, padB: 6);
            UIFactory.AddLE(brkBox, flexH: 1);
            UIFactory.CreateText("TBH", brkBox.transform, "Bracket", 18f, C_GOLD, UIFactory.AlignMidLeft, sizeDelta: new Vector2(280, 24));
            var bSv = UIFactory.CreateScrollView("TBSV", brkBox.transform, spacing: 1);
            UIFactory.AddLE(bSv.scrollGO, flexH: 1);
            tBracketList = bSv.content;
            // Pool sized for 16p double-elim worst case: 31 matches + ~12 group
            // headers (WB 4 + LB 6 + GF + optional GF_RESET) = 43. Cap at 50 for
            // headroom; pool excess rows remain SetActive(false).
            for (int i = 0; i < 50; i++)
            {
                int idx = i;
                var row = new GameObject($"TBR{i}"); row.transform.SetParent(tBracketList.transform, false);
                row.AddComponent<RectTransform>(); UIFactory.AddHLG(row, spacing: 6, forceExpandH: true);
                UIFactory.AddLE(row, prefH: 22, flexH: 0);
                var t = UIFactory.CreateText("txt", row.transform, "", 14f, C_WHITE, UIFactory.AlignMidLeft, sizeDelta: new Vector2(500, 22), raycastTarget: true);
                // Per-row click handler: headers toggle their group's expansion
                // state; non-header rows are no-ops. The purpose of each row
                // is re-determined on every refresh (see _tBracketRowPurposes).
                var ch = row.AddComponent<ClickHandler>();
                ch.onClick = () =>
                {
                    if (!ClickGuard.Claim()) return;
                    if (idx >= _tBracketRowPurposes.Count) return;
                    var pur = _tBracketRowPurposes[idx];
                    if (!pur.isHeader || string.IsNullOrEmpty(pur.groupKey)) return;
                    bool cur;
                    _tBracketExpanded.TryGetValue(pur.groupKey, out cur);
                    _tBracketExpanded[pur.groupKey] = !cur;
                    dirty = true;
                };
                // Row background image so the whole row catches clicks (not just the text glyphs).
                if (UIFactory.tImage != null)
                {
                    var img = row.AddComponent(UIFactory.tImage);
                    UIFactory.tImage.GetProperty("color", BindingFlags.Public | BindingFlags.Instance)
                        ?.SetValue(img, new Color(1f, 1f, 1f, 0.01f));
                    UIFactory.tImage.GetProperty("raycastTarget", BindingFlags.Public | BindingFlags.Instance)
                        ?.SetValue(img, true);
                }
                tBracketRowPool.Add(row);
                tBracketRowTexts.Add(t);
                row.SetActive(false);
            }

            // "My Tournaments" inline summary for the local player (own trophy line).
            txtTMyHistory = UIFactory.CreateText("TMH", right.transform, "", 14f, new Color(1f, 0.87f, 0.52f), UIFactory.AlignMidLeft, sizeDelta: new Vector2(600, 22));

            // Recent (site-wide completed) tournaments.
            var histBox = UIFactory.CreatePanel("TRH", right.transform, C_PANEL);
            UIFactory.AddVLG(histBox, spacing: 2, padL: 8, padR: 8, padT: 6, padB: 6);
            UIFactory.AddLE(histBox, prefH: 150, flexH: 0);
            UIFactory.CreateText("TRH_h", histBox.transform, "Recent Tournaments", 16f, C_SUB, UIFactory.AlignMidLeft, sizeDelta: new Vector2(260, 22));
            var hSv = UIFactory.CreateScrollView("TRHSV", histBox.transform, spacing: 1);
            UIFactory.AddLE(hSv.scrollGO, flexH: 1);
            tHistoryList = hSv.content;
            for (int i = 0; i < 12; i++)
            {
                var row = new GameObject($"TH{i}"); row.transform.SetParent(tHistoryList.transform, false);
                row.AddComponent<RectTransform>(); UIFactory.AddHLG(row, spacing: 4, forceExpandH: true);
                UIFactory.AddLE(row, prefH: 20, flexH: 0);
                var t = UIFactory.CreateText("txt", row.transform, "", 13f, C_LABEL, UIFactory.AlignMidLeft, sizeDelta: new Vector2(520, 20));
                tHistoryRowPool.Add(row);
                tHistoryRowTexts.Add(t);
                row.SetActive(false);
            }

            return panel;
        }

        // Preset shortcut -> Windows system timezone ID. Falls back to Local if the ID
        // doesn't resolve on this machine (unusual - Windows ships a full tzdb).
        private static readonly (string Label, string SystemId)[] _tzPresets = new[]
        {
            ("Local",  ""),
            ("UTC",    "UTC"),
            ("PT",     "Pacific Standard Time"),
            ("MT",     "Mountain Standard Time"),
            ("CT",     "Central Standard Time"),
            ("ET",     "Eastern Standard Time"),
            ("UK/GMT", "GMT Standard Time"),
            ("CET",    "Central European Standard Time"),
            ("EET",    "E. Europe Standard Time"),
            ("MSK",    "Russian Standard Time"),
            ("JST",    "Tokyo Standard Time"),
            ("AEST",   "AUS Eastern Standard Time"),
        };

        private static TimeZoneInfo _ResolveTz()
        {
            string pref = Plugin.TournamentTimezone?.Value ?? "Local";
            if (pref == "Local") return TimeZoneInfo.Local;
            // Preset label lookup first.
            foreach (var p in _tzPresets)
            {
                if (string.Equals(p.Label, pref, StringComparison.OrdinalIgnoreCase))
                {
                    if (string.IsNullOrEmpty(p.SystemId)) return TimeZoneInfo.Local;
                    try { return TimeZoneInfo.FindSystemTimeZoneById(p.SystemId); } catch { return TimeZoneInfo.Local; }
                }
            }
            // Fall back to treating pref as a raw system ID.
            try { return TimeZoneInfo.FindSystemTimeZoneById(pref); } catch { return TimeZoneInfo.Local; }
        }

        private static string _TzLabel()
        {
            string pref = Plugin.TournamentTimezone?.Value ?? "Local";
            foreach (var p in _tzPresets) if (string.Equals(p.Label, pref, StringComparison.OrdinalIgnoreCase)) return p.Label;
            return pref;
        }

        private static void _CycleTz()
        {
            string cur = Plugin.TournamentTimezone?.Value ?? "Local";
            int idx = 0;
            for (int i = 0; i < _tzPresets.Length; i++)
                if (string.Equals(_tzPresets[i].Label, cur, StringComparison.OrdinalIgnoreCase)) { idx = i; break; }
            idx = (idx + 1) % _tzPresets.Length;
            Plugin.TournamentTimezone.Value = _tzPresets[idx].Label;
            dirty = true;
        }

        private static readonly string[] _dateFormats = new[] { "ISO", "US", "EU" };
        private static string _DateFormat()
        {
            var v = Plugin.TournamentDateFormat?.Value ?? "ISO";
            if (v != "ISO" && v != "US" && v != "EU") v = "ISO";
            return v;
        }
        private static void _CycleDateFormat()
        {
            string cur = _DateFormat();
            int idx = System.Array.IndexOf(_dateFormats, cur);
            if (idx < 0) idx = 0;
            idx = (idx + 1) % _dateFormats.Length;
            Plugin.TournamentDateFormat.Value = _dateFormats[idx];
            dirty = true;
        }

        // Culture-invariant date formatter. All strings are ASCII — the Gravity
        // SDF font ships without Cyrillic, Japanese, etc. glyphs, and a locale-
        // dependent ToString would emit "Пт Кві 24" for Ukrainian users and
        // render as squares in-game. We bypass the OS culture entirely.
        private static readonly System.Globalization.CultureInfo _INV = System.Globalization.CultureInfo.InvariantCulture;
        private static string _FmtSlot(string iso)
        {
            if (string.IsNullOrEmpty(iso)) return "(TBD)";
            try
            {
                var utc = DateTime.Parse(iso, _INV, System.Globalization.DateTimeStyles.RoundtripKind).ToUniversalTime();
                var tz = _ResolveTz();
                var local = TimeZoneInfo.ConvertTimeFromUtc(utc, tz);
                string formatted;
                switch (_DateFormat())
                {
                    case "ISO": formatted = local.ToString("yyyy-MM-dd HH:mm", _INV); break;
                    case "US":  formatted = local.ToString("ddd MM/dd h:mm tt", _INV); break;
                    case "EU":  formatted = local.ToString("ddd dd/MM HH:mm", _INV); break;
                    default:    formatted = local.ToString("yyyy-MM-dd HH:mm", _INV); break;
                }
                return formatted + "  " + _TzLabel();
            }
            catch { return iso; }
        }

        private static void RefreshTournaments()
        {
            var t = ApiClient.CachedTournament;
            if (t == null)
            {
                UIFactory.SetText(txtTState, "Loading...");
                UIFactory.SetText(txtTWhen, "");
                if (txtTSignupBtn != null) txtTSignupBtn.SetActive(false);
                if (txtTUnsignupBtn != null) txtTUnsignupBtn.SetActive(false);
                if (tMyMatchPanel != null) tMyMatchPanel.SetActive(false);
                return;
            }

            // Header label by status.
            string stateLabel;
            Color stateColor = C_GOLD;
            switch (t.status)
            {
                case "voting": stateLabel = "VOTING / SIGNUPS OPEN"; stateColor = new Color(0.4f, 1f, 0.5f); break;
                case "locked": stateLabel = "LOCKED - STARTING SOON"; stateColor = new Color(1f, 0.85f, 0.3f); break;
                case "running": stateLabel = "LIVE"; stateColor = new Color(1f, 0.4f, 0.4f); break;
                case "completed": stateLabel = "COMPLETED"; stateColor = C_DIM; break;
                case "cancelled": stateLabel = "CANCELLED (not enough players)"; stateColor = C_DIM; break;
                default: stateLabel = "No active tournament"; break;
            }
            UIFactory.SetText(txtTState, stateLabel);
            UIFactory.SetColor(txtTState, stateColor);
            if (txtTTzButton != null) UIFactory.SetText(UIFactory.GetButtonText(txtTTzButton), _TzLabel());
            if (txtTDateFmtButton != null) UIFactory.SetText(UIFactory.GetButtonText(txtTDateFmtButton), _DateFormat());

            // Sub-tab highlight.
            bool isAsync = ApiClient.TournamentKind == "async";
            // Swap instruction text per mode.
            if (txtTInstructions != null)
            {
                UIFactory.SetText(txtTInstructions, isAsync ? _ASYNC_INSTRUCTIONS : _SYNC_INSTRUCTIONS);
            }
            if (tSubTabSyncBtn != null) { UIFactory.SetImageColor(tSubTabSyncBtn, isAsync ? C_TAB : C_TABACT); UIFactory.SetColor(UIFactory.GetButtonText(tSubTabSyncBtn), isAsync ? C_LABEL : C_WHITE); UIFactory.SetBold(UIFactory.GetButtonText(tSubTabSyncBtn), !isAsync); }
            if (tSubTabAsyncBtn != null) { UIFactory.SetImageColor(tSubTabAsyncBtn, isAsync ? C_TABACT : C_TAB); UIFactory.SetColor(UIFactory.GetButtonText(tSubTabAsyncBtn), isAsync ? C_WHITE : C_LABEL); UIFactory.SetBold(UIFactory.GetButtonText(tSubTabAsyncBtn), isAsync); }
            // Show the current time in the selected tz so players can verify their pick is
            // correct. Updated every refresh tick - resolution is coarse (~10s poll cadence)
            // but good enough to spot a wrong-tz selection instantly.
            try
            {
                var nowLocal = TimeZoneInfo.ConvertTimeFromUtc(DateTime.UtcNow, _ResolveTz());
                string nowStr;
                switch (_DateFormat())
                {
                    case "ISO": nowStr = nowLocal.ToString("yyyy-MM-dd HH:mm", _INV); break;
                    case "US":  nowStr = nowLocal.ToString("ddd MM/dd h:mm tt", _INV); break;
                    case "EU":  nowStr = nowLocal.ToString("ddd dd/MM HH:mm", _INV); break;
                    default:    nowStr = nowLocal.ToString("yyyy-MM-dd HH:mm", _INV); break;
                }
                UIFactory.SetText(txtTTzNow, $"now: <b>{nowStr}</b>");
            }
            catch { UIFactory.SetText(txtTTzNow, ""); }
            string whenText = "";
            if (!string.IsNullOrEmpty(t.scheduled_start_ts)) whenText = $"Starts: <color=#FFDE88>{_FmtSlot(t.scheduled_start_ts)}</color>";
            else if (!string.IsNullOrEmpty(t.default_start_ts)) whenText = $"Default start: <color=#AABBEE>{_FmtSlot(t.default_start_ts)}</color>   Signups close: {_FmtSlot(t.lock_at)}";
            UIFactory.SetText(txtTWhen, whenText);

            bool signedUp = !string.IsNullOrEmpty(t.my_signup_id);
            bool canSignup = t.status == "voting" && !signedUp && t.my_discord_linked;

            if (txtTSignupBtn != null) txtTSignupBtn.SetActive(canSignup);
            if (txtTUnsignupBtn != null) txtTUnsignupBtn.SetActive(t.status == "voting" && signedUp);
            UIFactory.SetText(txtTDiscordGate, t.my_discord_linked ? "" : "<color=#FFB088>Link Discord first (My Stats tab) to sign up.</color>");
            UIFactory.SetText(txtTPenalty, $"Your no-show penalty: <color=#FFCC44>{(t.my_penalty_pct * 100f):0.0}%</color>");

            // Async skips voting entirely - there's no scheduled_start_ts delay,
            // lock triggers immediate start. Hide the whole vote panel (not just
            // the slot rows) so the "Vote on Start Time" header disappears too.
            if (tVoteBoxPanel != null) tVoteBoxPanel.SetActive(!isAsync);
            // Time-vote UI: visible during voting when signed up.
            bool voteVisible = !isAsync && t.status == "voting" && signedUp;
            // (Previously force-enabled the vote row parent here, which was
            // re-showing the whole box for async. Removed - tVoteBoxPanel above
            // controls visibility.)
            int slots = t.time_slot_options?.Length ?? 0;
            var myVotes = new HashSet<string>(t.my_votes ?? Array.Empty<string>());
            var tallies = new Dictionary<string, int>();
            if (t.time_slot_tallies != null)
                foreach (var tv in t.time_slot_tallies) tallies[tv.slot_ts] = tv.votes;

            for (int i = 0; i < tSlotToggles.Count; i++)
            {
                if (i >= slots)
                {
                    tSlotToggles[i].transform.parent.gameObject.SetActive(false);
                    continue;
                }
                tSlotToggles[i].transform.parent.gameObject.SetActive(voteVisible);
                string iso = t.time_slot_options[i];
                bool alreadyVoted = myVotes.Contains(iso);
                // On first render after fetch, reflect server-side vote state in the UI checkboxes.
                if (i >= tSlotChecked.Count) tSlotChecked.Add(alreadyVoted);
                else if (!_tVoteLocalEdited) tSlotChecked[i] = alreadyVoted;
                UIFactory.SetText(UIFactory.GetButtonText(tSlotToggles[i]), tSlotChecked[i] ? "[X]" : "[ ]");
                int votes; tallies.TryGetValue(iso, out votes);
                string tallyTxt = myVotes.Count > 0 ? $"  <color=#888>({votes} {(votes == 1 ? "vote" : "votes")})</color>" : "";
                UIFactory.SetText(tSlotLabels[i], $"{_FmtSlot(iso)}{tallyTxt}");
            }
            // Force-start only surfaces once the minimum player count is met (min_players, default 8).
            // Before that the button is pointless - the server rejects force-start with <8 signups anyway,
            // and hiding it removes the "why doesn't this work?" confusion early in the voting window.
            int confirmedSignups = 0;
            if (t.signups != null)
                foreach (var _s in t.signups)
                    if (!_s.is_speculative) confirmedSignups++;
            // Force-start is a sync-only concept - async tournaments start
            // immediately when signups close, so there's nothing to force.
            bool forceStartAvailable = !isAsync && voteVisible && confirmedSignups >= t.min_players;
            UIFactory.SetText(txtTForceCount,
                t.status == "voting"
                    ? (forceStartAvailable
                        ? $"Force-start votes: {t.force_vote_count}/{confirmedSignups}"
                        : $"Force-start unlocks at {t.min_players} signups ({confirmedSignups}/{t.min_players})")
                    : "");
            if (txtTForceBtn != null) txtTForceBtn.SetActive(forceStartAvailable);

            // My-match panel (running + I'm in a ready/active match) + auto-connect.
            //
            // Auto-connect mechanics: once both players in the match have their ready_at
            // heartbeat fresh, we set Plugin.PendingRankedRoom to a deterministic name
            // derived from the match_id. Both clients derive the same name independently
            // so they land in the same Photon room. The existing QueueJoiner handles the
            // "leave current room -> connect -> JoinOrCreate" sequence. We memo each
            // match_id we've already dispatched to avoid setting the pending room on
            // every 10s refresh.
            bool showMyMatch = false;
            string myMatchLine = "";
            string myRoomCode = "";
            if (t.status == "running" && signedUp && t.matches != null)
            {
                foreach (var m in t.matches)
                {
                    if (m.status != "ready" && m.status != "active") continue;
                    if (m.p1_signup_id != t.my_signup_id && m.p2_signup_id != t.my_signup_id) continue;
                    if (!string.IsNullOrEmpty(m.match_id))
                        myRoomCode = "sct-" + m.match_id.Replace("-", "").Substring(0, 12);
                    string opp = (m.p1_signup_id == t.my_signup_id) ? m.p2_display_name : m.p1_display_name;
                    string oppSignupId = (m.p1_signup_id == t.my_signup_id) ? m.p2_signup_id : m.p1_signup_id;
                    bool oppReady = false;
                    if (t.signups != null)
                    {
                        foreach (var s in t.signups)
                        {
                            if (s.signup_id == oppSignupId) { oppReady = s.ready; break; }
                        }
                    }
                    string readyState = t.my_ready
                        ? (oppReady ? "<color=#60FF80>both ready - connecting...</color>"
                                    : "<color=#FFD94D>waiting on opponent to ready</color>")
                        : "<color=#FF9060>press Ready Up</color>";
                    myMatchLine = $"Your match (R{m.round}{(m.bracket_side == "TP" ? " 3rd Place" : "")}): vs <color=#FFDE88>{opp ?? "?"}</color>  -  {readyState}";
                    showMyMatch = true;

                    // Auto-connect: sync only. Async is self-paced - players coordinate
                    // via Discord and join a private lobby themselves. The mod still
                    // auto-detects the match result via the active-series lookup when
                    // both players have ranked enabled and play in any private room.
                    if (!isAsync && t.my_ready && oppReady && !string.IsNullOrEmpty(m.match_id))
                    {
                        string roomName = "sct-" + m.match_id.Replace("-", "").Substring(0, 12);
                        if (!_tournamentDispatchedMatches.Contains(m.match_id)
                            && Plugin.PendingRankedRoom != roomName)
                        {
                            _tournamentDispatchedMatches.Add(m.match_id);
                            Plugin.SetPendingRoom(roomName, t.photon_region);
                            Plugin.Log.LogInfo($"[TOURNAMENT] Auto-connecting to {roomName} in region '{t.photon_region ?? "(client default)"}' for match {m.match_id}");
                            CompetitiveUI.ShowNotification($"Tournament match starting vs {opp}", new Color(0.5f, 1f, 0.5f));
                        }
                    }
                    break;
                }
            }
            UIFactory.SetText(txtTMyMatch, myMatchLine);
            string regionBadge = string.IsNullOrEmpty(t.photon_region)
                ? ""
                : $"  <color=#AABBEE>[{t.photon_region.ToUpper()}]</color>";
            UIFactory.SetText(txtTRoomCode, string.IsNullOrEmpty(myRoomCode) ? ""
                : $"Room code: <color=#C0E0FF>{myRoomCode}</color>{regionBadge}  <color=#888>(if auto-connect fails, Reconnect or join via Private Lobby)</color>");
            if (txtTReconnectBtn != null) txtTReconnectBtn.SetActive(showMyMatch);
            if (tMyMatchPanel != null) tMyMatchPanel.SetActive(showMyMatch);

            // Signups list (right column). Seed numbers are only shown once the
            // tournament is actually running - pre-start, exposing seeds would let
            // anyone infer their round-1 opponent because bracket seeding is deterministic
            // for a given signup count. During voting/locked we show a simple "N." position
            // so the list is still informative but non-revealing.
            bool showSeeds = t.status == "running" || t.status == "completed";
            int signupIdx = 0;
            int confirmedCount = 0;
            if (t.signups != null)
            {
                for (int i = 0; i < t.signups.Length && signupIdx < tSignupRowPool.Count; i++)
                {
                    var s = t.signups[i];
                    var row = tSignupRowPool[signupIdx];
                    var texts = tSignupRowTexts[signupIdx];
                    string seed = showSeeds && s.seed > 0 ? $"#{s.seed}" : $"{(i + 1)}.";
                    string name = s.display_name ?? "";
                    if (s.is_speculative) name = $"~ {name}";
                    // Priority: placement > bracket progress > ready/forfeit/penalty.
                    string status;
                    if (s.placed_rank == 1) status = "<color=#FFD850>1st</color>";
                    else if (s.placed_rank == 2) status = "<color=#C0C0C0>2nd</color>";
                    else if (s.placed_rank == 3) status = "<color=#CD7F32>3rd</color>";
                    else if (!string.IsNullOrEmpty(s.progress_label))
                    {
                        // Color code by state: in-bracket = white, eliminated = dim red,
                        // champion = gold (already handled above).
                        if (s.progress_label.StartsWith("eliminated"))
                            status = $"<color=#A86060>{s.progress_label}</color>";
                        else if (s.progress_label == "CHAMPION")
                            status = "<color=#FFD850>CHAMPION</color>";
                        else
                            status = $"<color=#AACCFF>{s.progress_label}</color>";
                    }
                    else if (s.forfeited) status = "<color=#FF6060>FORFEIT</color>";
                    else if (s.ready) status = "<color=#60FF60>ready</color>";
                    else status = $"<color=#888>{s.penalty_at_signup * 100f:0}% pen</color>";
                    UIFactory.SetText(texts[0], seed);
                    UIFactory.SetText(texts[1], name);
                    UIFactory.SetText(texts[2], status);
                    row.SetActive(true);
                    signupIdx++;
                    if (!s.is_speculative) confirmedCount++;
                }
            }
            for (int i = signupIdx; i < tSignupRowPool.Count; i++) tSignupRowPool[i].SetActive(false);

            // Bracket list - flat chronological list grouped by round with separators.
            // Before the tournament starts running, we hide the matchups so signups can't
            // scout their round-1 opponent. During `locked` the bracket exists server-side
            // but the client shows a placeholder. Once `running`, full bracket is revealed.
            int brkIdx = 0;
            // Sync hides the bracket until start-time so nobody scouts their R1
            // opponent. Async brackets are always visible - players need to know
            // their opponent during the 7-day match window to coordinate.
            bool bracketHidden = !isAsync && t.status != "running" && t.status != "completed";
            if (bracketHidden)
            {
                if (t.status == "locked" && brkIdx < tBracketRowPool.Count)
                {
                    UIFactory.SetColor(tBracketRowTexts[brkIdx], C_LABEL);
                    UIFactory.SetText(tBracketRowTexts[brkIdx],
                        $"<i>Bracket revealed when the tournament starts ({_FmtSlot(t.scheduled_start_ts)}).</i>");
                    tBracketRowPool[brkIdx].SetActive(true);
                    brkIdx++;
                }
                else if (brkIdx < tBracketRowPool.Count)
                {
                    UIFactory.SetColor(tBracketRowTexts[brkIdx], C_DIM);
                    UIFactory.SetText(tBracketRowTexts[brkIdx], "<i>Bracket is generated once signups lock.</i>");
                    tBracketRowPool[brkIdx].SetActive(true);
                    brkIdx++;
                }
            }
            else if (t.matches != null && t.matches.Length > 0)
            {
                // Clear the per-row purpose list so each refresh rebuilds it fresh.
                _tBracketRowPurposes.Clear();

                // Group matches by (bracket_side, round). Ordering of groups:
                // W rounds ascending, then L rounds ascending, then GF, then GF_RESET.
                // Within each group, preserve slot_idx order.
                int SideOrder(string s) => s == "W" ? 0 : s == "L" ? 1 : s == "GF" ? 2 : s == "GF_RESET" ? 3 : s == "TP" ? 4 : 5;
                var groups = new Dictionary<string, List<ApiClient.TournamentMatchRow>>();
                var groupOrder = new List<(string key, int sideIdx, int round, string sideLabel)>();
                foreach (var m in t.matches)
                {
                    string key = $"{m.bracket_side}-{m.round}";
                    if (!groups.TryGetValue(key, out var lst))
                    {
                        lst = new List<ApiClient.TournamentMatchRow>();
                        groups[key] = lst;
                        groupOrder.Add((key, SideOrder(m.bracket_side), m.round, m.bracket_side));
                    }
                    lst.Add(m);
                }
                groupOrder.Sort((a, b) =>
                {
                    int c = a.sideIdx.CompareTo(b.sideIdx); if (c != 0) return c;
                    return a.round.CompareTo(b.round);
                });

                // Seed default expansion: on first render for a given tournament,
                // expand only the currently-active round per bracket side so the
                // player sees what matters RIGHT NOW. Completed + pending rounds
                // collapse to headers. User can click to expand any.
                if (_tBracketSeededForTid != t.tournament_id)
                {
                    _tBracketSeededForTid = t.tournament_id;
                    _tBracketExpanded.Clear();
                    var activeBySide = new Dictionary<string, int>();  // side -> round with active match
                    foreach (var g in groupOrder)
                    {
                        bool hasActive = groups[g.key].Exists(mm => mm.status == "ready" || mm.status == "active");
                        if (hasActive && !activeBySide.ContainsKey(g.sideLabel))
                            activeBySide[g.sideLabel] = g.round;
                    }
                    foreach (var g in groupOrder)
                    {
                        bool expand = activeBySide.TryGetValue(g.sideLabel, out int r) && r == g.round;
                        if (expand) _tBracketExpanded[g.key] = true;
                    }
                }

                // Render each group: header (clickable) + match rows if expanded.
                foreach (var g in groupOrder)
                {
                    if (brkIdx >= tBracketRowPool.Count) break;
                    var matches = groups[g.key];
                    int completed = 0;
                    int ready = 0;
                    foreach (var mm in matches)
                    {
                        if (mm.status == "completed" || mm.status == "forfeit" || mm.status == "double_forfeit" || mm.status == "bye_auto") completed++;
                        else if (mm.status == "ready" || mm.status == "active") ready++;
                    }
                    bool expanded;
                    _tBracketExpanded.TryGetValue(g.key, out expanded);
                    string arrow = expanded ? "[-]" : "[+]";
                    string sideLabelPretty =
                        g.sideLabel == "W" ? "Winners" :
                        g.sideLabel == "L" ? "Losers" :
                        g.sideLabel == "GF" ? "Grand Final" :
                        g.sideLabel == "GF_RESET" ? "Bracket Reset" :
                        g.sideLabel == "TP" ? "3rd Place" : g.sideLabel;
                    string roundSuffix = (g.sideLabel == "W" || g.sideLabel == "L") ? $" R{g.round}" : "";
                    string progress = ready > 0
                        ? $"<color=#FFD94D>{completed}/{matches.Count}</color> <color=#888>({ready} live)</color>"
                        : $"<color=#888>{completed}/{matches.Count}</color>";
                    UIFactory.SetColor(tBracketRowTexts[brkIdx], new Color(1f, 0.85f, 0.3f));
                    UIFactory.SetText(tBracketRowTexts[brkIdx],
                        $"  {arrow}  <b><color=#FFD94D>{sideLabelPretty}{roundSuffix}</color></b>  -  {progress}");
                    tBracketRowPool[brkIdx].SetActive(true);
                    _tBracketRowPurposes.Add(new BracketRowPurpose { isHeader = true, groupKey = g.key });
                    brkIdx++;

                    if (!expanded) continue;

                    foreach (var m in matches)
                    {
                        if (brkIdx >= tBracketRowPool.Count) break;
                        var row = tBracketRowPool[brkIdx];
                        var txt = tBracketRowTexts[brkIdx];
                        string p1 = m.p1_display_name ?? (m.is_bye ? "BYE" : "TBD");
                        string p2 = m.p2_display_name ?? (m.is_bye ? "BYE" : "TBD");
                        string scoreLine = "";
                        if (m.status == "completed" || m.status == "forfeit" || m.status == "double_forfeit")
                            scoreLine = (m.status == "completed") ? $" ({m.p1_series_wins}-{m.p2_series_wins})" : $" ({m.status.Replace('_', ' ')})";
                        Color rowColor = m.status == "completed" ? new Color(0.75f, 0.9f, 1f)
                            : m.status == "ready" ? new Color(1f, 0.9f, 0.4f)
                            : m.status == "active" ? new Color(0.8f, 1f, 0.4f)
                            : m.is_bye ? C_DIM : C_LABEL;
                        UIFactory.SetColor(txt, rowColor);
                        string deadlineLine = "";
                        if (isAsync && !string.IsNullOrEmpty(m.deadline_at) && (m.status == "ready" || m.status == "active"))
                        {
                            try
                            {
                                var dl = DateTime.Parse(m.deadline_at, null, System.Globalization.DateTimeStyles.RoundtripKind).ToUniversalTime();
                                var remaining = dl - DateTime.UtcNow;
                                if (remaining.TotalSeconds > 0)
                                {
                                    deadlineLine = remaining.TotalDays >= 1
                                        ? $"   <color=#FFAA44>deadline: {(int)remaining.TotalDays}d {remaining.Hours}h left</color>"
                                        : $"   <color=#FF6060>deadline: {remaining.Hours}h {remaining.Minutes}m left</color>";
                                }
                                else deadlineLine = "   <color=#FF4040>deadline passed</color>";
                            }
                            catch { }
                        }
                        UIFactory.SetText(txt, $"        {p1}  vs  {p2}{scoreLine}{deadlineLine}");
                        row.SetActive(true);
                        _tBracketRowPurposes.Add(new BracketRowPurpose { isHeader = false, groupKey = g.key });
                        brkIdx++;
                    }
                }
            }
            for (int i = brkIdx; i < tBracketRowPool.Count; i++) tBracketRowPool[i].SetActive(false);

            // My own tournament summary line (local player's placements).
            var mySid = MatchTracker.LocalSteamId;
            if (!string.IsNullOrEmpty(mySid) && mySid != "unknown"
                && ApiClient.CachedPlayerTournaments.TryGetValue(mySid, out var myH) && myH != null
                && myH.participant_count > 0)
            {
                UIFactory.SetText(txtTMyHistory,
                    $"Your placements:  <color=#FFE580>1stx{myH.winner_count}</color>  <color=#C8C8C8>2ndx{myH.runner_up_count}</color>  <color=#D4894A>3rdx{myH.third_place_count}</color>  <color=#888>(played {myH.participant_count})</color>");
            }
            else
            {
                UIFactory.SetText(txtTMyHistory, "Your placements: <color=#888>no completed tournaments yet</color>");
            }

            // Site-wide recent tournaments panel (bottom of right column).
            var hist = ApiClient.CachedSiteTournamentHistory;
            int hIdx = 0;
            if (hist != null)
            {
                for (int i = 0; i < hist.Length && hIdx < tHistoryRowPool.Count; i++)
                {
                    var te = hist[i];
                    string dt = te.ended_at;
                    try { if (!string.IsNullOrEmpty(dt)) dt = TimeZoneInfo.ConvertTimeFromUtc(DateTime.Parse(te.ended_at, _INV, System.Globalization.DateTimeStyles.RoundtripKind).ToUniversalTime(), _ResolveTz()).ToString(_DateFormat() == "EU" ? "dd/MM/yy" : "MM/dd/yy", _INV); } catch { }
                    string winner = string.IsNullOrEmpty(te.winner_display_name) ? "-" : te.winner_display_name;
                    UIFactory.SetText(tHistoryRowTexts[hIdx],
                        $"<color=#AABBEE>{dt}</color>  Winner: <color=#FFE580>{winner}</color>  <color=#888>({te.signup_count}p)</color>");
                    tHistoryRowPool[hIdx].SetActive(true);
                    hIdx++;
                }
            }
            for (int i = hIdx; i < tHistoryRowPool.Count; i++) tHistoryRowPool[i].SetActive(false);
        }

        private static bool _tVoteLocalEdited = false;

        private const string _SYNC_INSTRUCTIONS =
            "<b><color=#FFD94D>HOW IT WORKS (Sync)</color></b>\n" +
            "  1. Sign up (Discord must be linked)\n" +
            "  2. Vote on start time if you want\n" +
            "  3. Keep this tab open at start time\n" +
            "  4. Mod <b>auto-connects you to your opponent</b> - no queue, no invites\n" +
            "  5. Play BO3, bracket advances automatically\n" +
            "\n" +
            "<b><color=#FFD94D>READY-UP</color></b>\n" +
            "  * Press <b>Ready Up</b> within 5 min of your match starting or forfeit\n" +
            "  * Tab open = heartbeat keeps you ready; don't alt-tab for long\n" +
            "  * Bracket hidden until start (no scouting your first opponent)\n" +
            "\n" +
            "<b><color=#FFD94D>FORMAT</color></b>\n" +
            "  * <b>Double-elim</b> BO3 (first to 2) - losing once drops you to the losers bracket\n" +
            "  * Matches run in parallel: you play your next match the moment your opponent is ready\n" +
            "  * Top seeds get byes when fewer than 16 sign up\n" +
            "  * Grand Final: WB champ vs LB champ (bracket reset if LB wins first BO3)\n" +
            "  * All matches count toward ranked Elo\n" +
            "\n" +
            "<b><color=#FFD94D>PRIZES</color></b> (16-player full tier)\n" +
            "  * <color=#FFE580>1st</color> - 500g / 2500 XP / Winner role\n" +
            "  * <color=#C8C8C8>2nd</color> - 300g / 1500 XP / Runner Up role\n" +
            "  * <color=#D4894A>3rd</color> - 60g / 75 XP / 3rd Place role (loser of LB final)\n" +
            "  * Scaled 60% at 12-15p, 30% at 8-11p, cancelled under 8\n" +
            "\n" +
            "<b><color=#FFD94D>PENALTY %</color></b>\n" +
            "  * Grows when you sign up but no-show at match time\n" +
            "  * Lower penalty = priority if more than 16 sign up";

        private const string _ASYNC_INSTRUCTIONS =
            "<b><color=#FFD94D>HOW IT WORKS (Async)</color></b>\n" +
            "  1. Sign up any time during the 7-day signup window (Discord must be linked)\n" +
            "  2. On lock, bracket is built and first-round matches activate\n" +
            "  3. Coordinate with your opponent via <b>/dm-opponent</b> on Discord\n" +
            "  4. Both of you enable Ranked, join any private lobby in ROUNDS, play the BO3\n" +
            "  5. <b>Mod records the result automatically</b> - no manual report, no room code needed\n" +
            "  6. Winner advances in bracket; loser drops to LB (or is eliminated)\n" +
            "\n" +
            "<b><color=#FFD94D>AUTO-RECORDING REQUIREMENTS</color></b>\n" +
            "  * Both players must have <b>Ranked</b> toggled ON in-game when playing\n" +
            "  * Any private ROUNDS lobby works - tournament doesn't force a specific room\n" +
            "  * Once you hit 2 BO3 wins, the mod advances the bracket and notifies you\n" +
            "\n" +
            "<b><color=#FFD94D>SCHEDULING</color></b>\n" +
            "  * No fixed start time - self-paced, <b>7 days per match</b>\n" +
            "  * Total tournament runs up to 6-9 weeks depending on how fast matches happen\n" +
            "  * Miss the deadline and you forfeit that match (tracked in penalty %)\n" +
            "\n" +
            "<b><color=#FFD94D>FORMAT</color></b>\n" +
            "  * <b>Double-elim</b> BO3 - lose once, you drop to losers bracket\n" +
            "  * Grand Final: WB champ vs LB champ (bracket reset if LB wins first BO3)\n" +
            "  * All matches count toward ranked Elo\n" +
            "\n" +
            "<b><color=#FFD94D>PRIZES</color></b>\n" +
            "  * Same scaled tier as sync - 1st / 2nd / 3rd get gold + XP + trophy roles\n" +
            "  * 3rd place = loser of LB final\n" +
            "\n" +
            "<b><color=#FFD94D>PENALTY %</color></b>\n" +
            "  * Grows when you sign up but forfeit a match by missing the 7-day deadline";

        // ── 2v2 tab ───────────────────────────────────────────────
        private static object txtTeamHeader, txtTeamStatus, txtTeamMembers, txtTeamLBHeader;
        private static GameObject teamSearchBtn, teamSearchCustomBtn, teamLeaveBtn, teamReadyBtn, teamLBContainer;
        private static List<TeamLBRow> teamLBRows = new List<TeamLBRow>();
        private class TeamLBRow { public GameObject root; public object txtRank, txtName, txtRating, txtWL, txtWR, txtMate, txtGold, txtXp; }
        // 2v2 leaderboard column widths — shared by header + rows so sort
        // labels sit directly above their data column.
        private static readonly int[] TLB_COL_W = new int[] { 36, 200, 70, 80, 60, 92, 76, 88 };

        private static GameObject BuildTeamTab(Transform parent)
        {
            // Outer wrapper that the tab system swaps in. Inside it lives a
            // ScrollView so the user can scroll past the queue panels into
            // the leaderboard + history below — accommodates 8+ queuers per
            // bucket without crushing the bottom panels.
            var outer = new GameObject("Team2v2Outer");
            outer.transform.SetParent(parent, false);
            outer.AddComponent<RectTransform>();
            UIFactory.AddVLG(outer, spacing: 0);
            UIFactory.AddLE(outer, flexH: 1);
            var scroll = UIFactory.CreateScrollView("Team2v2Scroll", outer.transform, spacing: 6);
            UIFactory.AddLE(scroll.scrollGO, flexH: 1);
            var panel = scroll.content;
            // The scroll-content VLG is created with default spacing; we want
            // padding on the inside edges too. Re-add VLG via a panel child so
            // the existing layout assumptions still hold.
            var inner = new GameObject("Team2v2Inner");
            inner.transform.SetParent(panel.transform, false);
            inner.AddComponent<RectTransform>();
            UIFactory.AddVLG(inner, spacing: 6, padL: 10, padR: 10, padT: 8, padB: 8);
            // The ContentSizeFitter on `panel` will compute height from `inner`'s
            // preferred height (which is the sum of the children we add below).
            panel = inner; // route subsequent children into this padded inner panel

            // Header
            txtTeamHeader = UIFactory.CreateText("THdr", panel.transform,
                "<b>2v2 Ranked</b>  <color=#888>(separate Glicko, FF on, BO3 series)</color>",
                20f, C_GOLD, UIFactory.AlignMidLeft, sizeDelta: new Vector2(900, 28));

            // Status / queue panel — height is sum of children. Don't fix it; let VLG
            // size naturally so the button row below isn't clipped off-screen (the
            // earlier 110px fixed height shadowed the buttons because text+padding
            // already filled the box, hiding clicks for no visible reason).
            var statusBox = UIFactory.CreatePanel("TStat", panel.transform, C_PANEL);
            UIFactory.AddVLG(statusBox, spacing: 6, padL: 12, padR: 12, padT: 8, padB: 8);
            UIFactory.AddLE(statusBox, flexH: 0);

            txtTeamStatus = UIFactory.CreateText("TS", statusBox.transform,
                "Click <b>Search</b> to start finding a 2v2.",
                17f, C_WHITE, UIFactory.AlignMidLeft, sizeDelta: new Vector2(900, 24));

            txtTeamMembers = UIFactory.CreateText("TM", statusBox.transform, "",
                15f, C_LABEL, UIFactory.AlignTopLeft, sizeDelta: new Vector2(900, 60));
            UIFactory.SetWordWrap(txtTeamMembers, true);

            // DC sticky-team grace banner: when a player drops mid-series, the
            // server enters a 5-minute window where the same 4 can re-queue and
            // resume the existing series with the same teams. Otherwise the
            // remaining team takes the series win by forfeit at the deadline.
            txtTeamDcGrace = UIFactory.CreateText("TDC", statusBox.transform, "",
                16f, new Color(1f, 0.7f, 0.3f), UIFactory.AlignMidLeft,
                sizeDelta: new Vector2(900, 26));
            UIFactory.SetBold(txtTeamDcGrace, true);
            (txtTeamDcGrace as Component)?.gameObject?.SetActive(false);

            // Buttons row
            var btnRow = new GameObject("TBR");
            btnRow.transform.SetParent(statusBox.transform, false);
            btnRow.AddComponent<RectTransform>();
            UIFactory.AddHLG(btnRow, spacing: 8);
            UIFactory.AddLE(btnRow, prefH: 32, minH: 32, flexH: 0);

            // UIFactory.CreateButton already wraps onClick in ClickGuard.Claim() (line 102).
            // Adding another guard inside the lambda double-claims and silently absorbs every
            // click — see logs-snapshot bepinex-20260424_161027.log for the smoking gun.
            teamSearchBtn = UIFactory.CreateButton("TSB", btnRow.transform, "Search Random", 16f, C_WHITE,
                new Color(0.20f, 0.55f, 0.30f, 0.95f),
                () =>
                {
                    Plugin.Log.LogInfo("[TEAM-QUEUE-UI] Search Random clicked");
                    var sid = MatchTracker.LocalSteamId;
                    if (string.IsNullOrEmpty(sid) || sid == "unknown")
                    {
                        Plugin.Log.LogWarning($"[TEAM-QUEUE-UI] LocalSteamId='{sid}' — Steam not ready yet, ignoring click");
                        CompetitiveUI.ShowNotification("Steam ID not ready yet — try again in a few seconds", new Color(1f, 0.6f, 0.2f), 4f);
                        return;
                    }
                    string region = "";
                    try { region = PhotonNetwork.CloudRegion?.Replace("/*", "") ?? ""; } catch { }
                    Plugin.Log.LogInfo($"[TEAM-QUEUE-UI] joining auto team queue sid={sid} region='{region}'");
                    ApiClient.JoinTeamQueue(sid, MatchTracker.LocalDisplayName, region, "auto");
                },
                sizeDelta: new Vector2(160, 28));

            teamSearchCustomBtn = UIFactory.CreateButton("TSC", btnRow.transform, "Find Custom Lobby", 16f, C_WHITE,
                new Color(0.40f, 0.30f, 0.55f, 0.95f),
                () =>
                {
                    Plugin.Log.LogInfo("[TEAM-QUEUE-UI] Find Custom Lobby clicked");
                    var sid = MatchTracker.LocalSteamId;
                    if (string.IsNullOrEmpty(sid) || sid == "unknown")
                    {
                        CompetitiveUI.ShowNotification("Steam ID not ready yet — try again in a few seconds", new Color(1f, 0.6f, 0.2f), 4f);
                        return;
                    }
                    string region = "";
                    try { region = PhotonNetwork.CloudRegion?.Replace("/*", "") ?? ""; } catch { }
                    Plugin.Log.LogInfo($"[TEAM-QUEUE-UI] joining manual team queue sid={sid} region='{region}'");
                    ApiClient.JoinTeamQueue(sid, MatchTracker.LocalDisplayName, region, "manual");
                },
                sizeDelta: new Vector2(180, 28));

            teamLeaveBtn = UIFactory.CreateButton("TLB", btnRow.transform, "Leave Queue", 16f, C_WHITE,
                new Color(0.55f, 0.20f, 0.20f, 0.95f),
                () =>
                {
                    var sid = MatchTracker.LocalSteamId;
                    if (!string.IsNullOrEmpty(sid)) ApiClient.LeaveTeamQueue(sid);
                },
                sizeDelta: new Vector2(160, 28));
            teamLeaveBtn.SetActive(false);

            teamReadyBtn = UIFactory.CreateButton("TRB", btnRow.transform, "Ready Up", 16f, C_WHITE,
                new Color(0.20f, 0.55f, 0.30f, 0.95f),
                () =>
                {
                    var sid = MatchTracker.LocalSteamId;
                    if (!string.IsNullOrEmpty(sid)) ApiClient.ReadyUpTeam(sid);
                },
                sizeDelta: new Vector2(160, 28));
            teamReadyBtn.SetActive(false);

            // Pick-teams row: visible inside the manual (custom-lobby) queue.
            // Hidden when in the random queue or not queueing — choosing a queue
            // type is the consent now, not a separate checkbox.
            var pickRow = new GameObject("TPR");
            pickRow.transform.SetParent(statusBox.transform, false);
            pickRow.AddComponent<RectTransform>();
            UIFactory.AddHLG(pickRow, spacing: 8);
            UIFactory.AddLE(pickRow, prefH: 30, minH: 30, flexH: 0);
            teamPickT1Btn = UIFactory.CreateButton("TPT1", pickRow.transform, "Team 1 (Orange)",
                14f, C_WHITE, new Color(0.55f, 0.30f, 0.10f, 0.5f),
                () => { var sid = MatchTracker.LocalSteamId; if (!string.IsNullOrEmpty(sid)) ApiClient.SetTeamPreferredTeam(sid, 1); },
                sizeDelta: new Vector2(140, 26));
            teamPickT2Btn = UIFactory.CreateButton("TPT2", pickRow.transform, "Team 2 (Blue)",
                14f, C_WHITE, new Color(0.10f, 0.30f, 0.55f, 0.5f),
                () => { var sid = MatchTracker.LocalSteamId; if (!string.IsNullOrEmpty(sid)) ApiClient.SetTeamPreferredTeam(sid, 2); },
                sizeDelta: new Vector2(140, 26));
            txtPickStatus = UIFactory.CreateText("TPS", pickRow.transform,
                "<color=#888>Custom lobby — claim Team 1 or Team 2.</color>",
                13f, C_LABEL, UIFactory.AlignMidLeft, sizeDelta: new Vector2(440, 26));

            // "In Queue" panel — split into Random and Custom sections. Each
            // body sized for ~8 rows (each row is one queuer, ~18px tall) so
            // the panel doesn't clip into the leaderboard / history below.
            // Bumped pref height per body 60 → 160 (8 * 18 + padding) per
            // tester report: queue panels were cutting into the text below.
            var queueListPanel = UIFactory.CreatePanel("TQL", panel.transform, C_PANEL);
            UIFactory.AddVLG(queueListPanel, spacing: 2, padL: 12, padR: 12, padT: 6, padB: 6);
            UIFactory.AddLE(queueListPanel, flexH: 0);
            txtTeamQueueListHeader = UIFactory.CreateText("TQLH", queueListPanel.transform,
                "<b>Random Queue</b>", 17f, C_SUB, UIFactory.AlignMidLeft, sizeDelta: new Vector2(900, 22));
            txtTeamQueueListBody = UIFactory.CreateText("TQLB", queueListPanel.transform,
                "<color=#888>Loading…</color>", 15f, C_LABEL, UIFactory.AlignTopLeft,
                sizeDelta: new Vector2(900, 160));
            var qlbComp = txtTeamQueueListBody as Component;
            if (qlbComp != null) UIFactory.AddLE(qlbComp.gameObject, prefH: 160, minH: 80, flexH: 0);
            UIFactory.SetWordWrap(txtTeamQueueListBody, true);
            txtTeamQueueManualHeader = UIFactory.CreateText("TQMH", queueListPanel.transform,
                "<b>Custom Lobbies</b>", 17f, C_SUB, UIFactory.AlignMidLeft, sizeDelta: new Vector2(900, 22));
            txtTeamQueueManualBody = UIFactory.CreateText("TQMB", queueListPanel.transform,
                "<color=#888>Loading…</color>", 15f, C_LABEL, UIFactory.AlignTopLeft,
                sizeDelta: new Vector2(900, 160));
            var qmbComp = txtTeamQueueManualBody as Component;
            if (qmbComp != null) UIFactory.AddLE(qmbComp.gameObject, prefH: 160, minH: 80, flexH: 0);
            UIFactory.SetWordWrap(txtTeamQueueManualBody, true);

            // Bottom row: leaderboard (left) + recent history (right).
            // Fixed prefH inside the outer scroll so the bottom row gets a
            // bounded height and the internal lbScroll/histScroll can size
            // properly. Outer scroll handles overflow when total content >
            // viewport.
            var bottom = new GameObject("TBot");
            bottom.transform.SetParent(panel.transform, false);
            bottom.AddComponent<RectTransform>();
            UIFactory.AddHLG(bottom, spacing: 8);
            UIFactory.AddLE(bottom, prefH: 720, minH: 400, flexH: 0);

            // Left: leaderboard
            var lbCol = new GameObject("TLBCol");
            lbCol.transform.SetParent(bottom.transform, false);
            lbCol.AddComponent<RectTransform>();
            UIFactory.AddVLG(lbCol, spacing: 4);
            UIFactory.AddLE(lbCol, flexW: 1, flexH: 1);
            txtTeamLBHeader = UIFactory.CreateText("TLBH", lbCol.transform,
                "<b>2v2 Leaderboard</b>", 18f, C_SUB,
                UIFactory.AlignMidLeft, sizeDelta: new Vector2(560, 24));
            // Column header row — clickable buttons that double as sort
            // toggles. Widths match TLB_COL_W so each label sits above its
            // data column. Mirrors the 1v1 leaderboard pattern.
            var lbHeaderRow = new GameObject("TLBHR");
            lbHeaderRow.transform.SetParent(lbCol.transform, false);
            lbHeaderRow.AddComponent<RectTransform>();
            UIFactory.AddHLG(lbHeaderRow, spacing: 4, padL: 8, padR: 8);
            UIFactory.AddLE(lbHeaderRow, prefH: 24, minH: 24, flexH: 0);
            // Column 0 (#) and 1 (Player) aren't sortable — render as plain
            // labels, not buttons. Columns 2..7 are sortable.
            string[] hdrLabels = new[] { "#", "Player", "Rating", "W-L", "WR", "Avg Mate Elo", "Gold", "XP" };
            string[] hdrSortKey = new[] { null, null, "rating", "wins", "win_rate", "avg_teammate_elo", "team_gold_earned", "team_xp_earned" };
            teamLBSortBtns = new List<GameObject>();
            teamLBSortKeys = hdrSortKey;
            teamLBHeaderTexts = new object[hdrLabels.Length];
            for (int hi = 0; hi < hdrLabels.Length; hi++)
            {
                int idx = hi;
                if (hdrSortKey[hi] == null)
                {
                    var lbl = UIFactory.CreateText($"TLBH_{hi}", lbHeaderRow.transform, hdrLabels[hi],
                        13f, C_LABEL,
                        hi == 0 ? UIFactory.AlignMidLeft : UIFactory.AlignMidLeft,
                        sizeDelta: new Vector2(TLB_COL_W[hi], 24));
                    teamLBHeaderTexts[hi] = lbl;
                    teamLBSortBtns.Add(null);
                }
                else
                {
                    var b = UIFactory.CreateButton($"TLBS_{hdrSortKey[hi]}", lbHeaderRow.transform, hdrLabels[hi],
                        13f, C_LABEL, new Color(0.18f, 0.20f, 0.24f, 0.85f),
                        () => { ApiClient.FetchTeamLeaderboard(200, hdrSortKey[idx]); },
                        sizeDelta: new Vector2(TLB_COL_W[hi], 24));
                    teamLBSortBtns.Add(b);
                    teamLBHeaderTexts[hi] = UIFactory.GetButtonText(b);
                }
            }
            var lbScroll = UIFactory.CreateScrollView("TLBSV", lbCol.transform, spacing: 1);
            UIFactory.AddLE(lbScroll.scrollGO, flexH: 1);
            teamLBContainer = lbScroll.content;
            for (int i = 0; i < 100; i++) teamLBRows.Add(CreateTeamLBRow(teamLBContainer.transform, $"tlb{i}"));

            // Right: recent 2v2 series — paginated 3/page.
            var hCol = new GameObject("TH2Col");
            hCol.transform.SetParent(bottom.transform, false);
            hCol.AddComponent<RectTransform>();
            UIFactory.AddVLG(hCol, spacing: 4);
            UIFactory.AddLE(hCol, flexW: 1, flexH: 1);
            // Header row groups title + pagination on the same line so the
            // panel reads as one unit instead of two stacked widgets.
            var histHdrRow = new GameObject("THHR");
            histHdrRow.transform.SetParent(hCol.transform, false);
            histHdrRow.AddComponent<RectTransform>();
            UIFactory.AddHLG(histHdrRow, spacing: 6);
            UIFactory.AddLE(histHdrRow, prefH: 26, minH: 26, flexH: 0);
            txtTeamHistHeader = UIFactory.CreateText("THH", histHdrRow.transform,
                "<b>Recent 2v2 Series</b>", 18f, C_SUB,
                UIFactory.AlignMidLeft, sizeDelta: new Vector2(280, 26));
            // Right-side spacer pushes the pagination buttons to the right edge.
            var hSp = new GameObject("THSp");
            hSp.transform.SetParent(histHdrRow.transform, false);
            hSp.AddComponent<RectTransform>();
            UIFactory.AddLE(hSp, flexW: 1);
            teamHistPrevBtn = UIFactory.CreateButton("THPP", histHdrRow.transform, "<", 13f, C_WHITE,
                new Color(0.22f, 0.25f, 0.30f, 0.95f),
                () => { teamSeriesPageReq = Math.Max(0, teamSeriesPageReq - 1); ApiClient.FetchAllSeriesPaged(teamSeriesPageReq, 3); },
                sizeDelta: new Vector2(28, 22));
            txtTeamHistPageIndicator = UIFactory.CreateText("THPI", histHdrRow.transform,
                "1/1", 13f, C_LABEL, UIFactory.AlignMidCenter, sizeDelta: new Vector2(48, 22));
            teamHistNextBtn = UIFactory.CreateButton("THPN", histHdrRow.transform, ">", 13f, C_WHITE,
                new Color(0.22f, 0.25f, 0.30f, 0.95f),
                () => { teamSeriesPageReq += 1; ApiClient.FetchAllSeriesPaged(teamSeriesPageReq, 3); },
                sizeDelta: new Vector2(28, 22));
            var histScroll = UIFactory.CreateScrollView("THSV", hCol.transform, spacing: 2);
            UIFactory.AddLE(histScroll.scrollGO, flexH: 1);
            teamHistContainer = histScroll.content;
            // 3 series × ~5 rows per series (header + 4 games max) = 15 rows.
            for (int i = 0; i < 30; i++) teamHistRows.Add(CreateTeamHistRow(teamHistContainer.transform, $"th{i}"));

            return outer;
        }

        private static List<GameObject> teamLBSortBtns;
        private static string[] teamLBSortKeys;
        private static object[] teamLBHeaderTexts;
        private static GameObject teamHistPrevBtn, teamHistNextBtn;
        private static object txtTeamHistPageIndicator;

        private static object txtTeamHistHeader;
        private static GameObject teamHistContainer;
        private static List<TeamHistRow> teamHistRows = new List<TeamHistRow>();
        private class TeamHistRow {
            public GameObject root;
            public object txtLine1, txtLine2;
            // Stacked cards columns — used for game rows. Hidden for series
            // header rows (which show the teams + player titles in txtLine2).
            public GameObject cardsRow;
            public object txtCardsLeft, txtCardsRight;
        }
        private static object txtTeamQueueListHeader;
        private static object txtTeamQueueListBody;
        private static object txtTeamQueueManualHeader;
        private static object txtTeamQueueManualBody;
        private static object txtTeamDcGrace;
        private static GameObject teamPickT1Btn, teamPickT2Btn;
        private static object txtPickStatus;

        private static TeamHistRow CreateTeamHistRow(Transform parent, string name)
        {
            var row = new TeamHistRow();
            row.root = new GameObject(name);
            row.root.transform.SetParent(parent, false);
            row.root.AddComponent<RectTransform>();
            UIFactory.AddVLG(row.root, spacing: 2, padL: 8, padR: 6, padT: 4, padB: 4);
            UIFactory.AddLE(row.root, minH: 30, flexH: 0);
            row.txtLine1 = UIFactory.CreateText("l1", row.root.transform, "", 15f, C_WHITE, UIFactory.AlignTopLeft, sizeDelta: new Vector2(560, 22));
            // Line 2 holds the "Team A vs Team B" header text on series rows.
            // Hidden when the row renders a per-match cards block instead.
            row.txtLine2 = UIFactory.CreateText("l2", row.root.transform, "", 13f, C_LABEL, UIFactory.AlignTopLeft, sizeDelta: new Vector2(560, 22));

            // Per-match cards stack — TWO columns side-by-side. Left = caller's
            // team (or T1 from neutral perspective), right = opponents/T2. Each
            // column lists every card pick stacked vertically, grouped under
            // the player's bolded name. No truncation: tester explicitly asked
            // to see all cards in an Excel-style layout instead of a snake line.
            row.cardsRow = new GameObject("cardsRow");
            row.cardsRow.transform.SetParent(row.root.transform, false);
            row.cardsRow.AddComponent<RectTransform>();
            // Tight inter-column spacing so the two team columns sit close
            // (tester report: "move the enemy/orange team a bit closer to
            // the blue/ally side, they're unnecessarily spaced").
            UIFactory.AddHLG(row.cardsRow, spacing: 4, padL: 12);
            UIFactory.AddLE(row.cardsRow, minH: 24, flexH: 0);
            row.txtCardsLeft  = UIFactory.CreateText("cl", row.cardsRow.transform, "", 13f,
                new Color(0.55f, 0.80f, 1.00f), UIFactory.AlignTopLeft,
                sizeDelta: new Vector2(220, 200));
            row.txtCardsRight = UIFactory.CreateText("cr", row.cardsRow.transform, "", 13f,
                new Color(1.00f, 0.69f, 0.53f), UIFactory.AlignTopLeft,
                sizeDelta: new Vector2(220, 200));
            // Word-wrap on so any single-card name longer than the column
            // width breaks rather than clips. Vertical stacking via newlines
            // in the text content.
            UIFactory.SetWordWrap(row.txtCardsLeft, true);
            UIFactory.SetWordWrap(row.txtCardsRight, true);
            row.cardsRow.SetActive(false);

            row.root.SetActive(false);
            return row;
        }

        private static TeamLBRow CreateTeamLBRow(Transform parent, string name)
        {
            var row = new TeamLBRow();
            row.root = new GameObject(name);
            row.root.transform.SetParent(parent, false);
            row.root.AddComponent<RectTransform>();
            UIFactory.AddHLG(row.root, spacing: 4, padL: 8, padR: 8);
            UIFactory.AddLE(row.root, prefH: 22, minH: 22, flexH: 0);
            row.txtRank   = UIFactory.CreateText("r",  row.root.transform, "", 15f, C_GOLD,  UIFactory.AlignMidLeft,   sizeDelta: new Vector2(TLB_COL_W[0], 22));
            row.txtName   = UIFactory.CreateText("n",  row.root.transform, "", 15f, C_WHITE, UIFactory.AlignMidLeft,   sizeDelta: new Vector2(TLB_COL_W[1], 22));
            row.txtRating = UIFactory.CreateText("rt", row.root.transform, "", 15f, C_WHITE, UIFactory.AlignMidCenter, sizeDelta: new Vector2(TLB_COL_W[2], 22));
            UIFactory.SetBold(row.txtRating, true);
            row.txtWL   = UIFactory.CreateText("wl",   row.root.transform, "", 14f, C_LABEL, UIFactory.AlignMidCenter, sizeDelta: new Vector2(TLB_COL_W[3], 22));
            row.txtWR   = UIFactory.CreateText("wr",   row.root.transform, "", 14f, C_LABEL, UIFactory.AlignMidCenter, sizeDelta: new Vector2(TLB_COL_W[4], 22));
            row.txtMate = UIFactory.CreateText("mt",   row.root.transform, "", 14f, C_LABEL, UIFactory.AlignMidCenter, sizeDelta: new Vector2(TLB_COL_W[5], 22));
            row.txtGold = UIFactory.CreateText("g",    row.root.transform, "", 14f, C_LABEL, UIFactory.AlignMidCenter, sizeDelta: new Vector2(TLB_COL_W[6], 22));
            row.txtXp   = UIFactory.CreateText("xp",   row.root.transform, "", 14f, C_LABEL, UIFactory.AlignMidCenter, sizeDelta: new Vector2(TLB_COL_W[7], 22));
            row.root.SetActive(false);
            return row;
        }

        private static void RefreshTeamTab()
        {
            // Header live count — green when anyone's searching (matches the 1v1 vibe).
            int searchingCount = ApiClient.CachedTeamQueueSearching;
            string countCol = searchingCount > 0 ? "#88FF88" : "#888";
            UIFactory.SetText(txtTeamHeader,
                $"<b>2v2 Ranked</b>  <color={countCol}>({searchingCount} searching)</color>");

            // Queue state UI
            var st = ApiClient.CurrentTeamQueueState;
            var poll = ApiClient.LastTeamPollData;
            string status, members = "";
            switch (st)
            {
                case ApiClient.TeamQueueState.Idle:
                    status = "<color=#888>Pick <b>Search Random</b> for matchmaking, or <b>Find Custom Lobby</b> to choose teams.</color>";
                    if (teamSearchBtn != null) teamSearchBtn.SetActive(true);
                    if (teamSearchCustomBtn != null) teamSearchCustomBtn.SetActive(true);
                    if (teamLeaveBtn != null) teamLeaveBtn.SetActive(false);
                    if (teamReadyBtn != null) teamReadyBtn.SetActive(false);
                    break;
                case ApiClient.TeamQueueState.Searching:
                    int found = poll != null && poll.queue_count > 0 ? poll.queue_count : 1;
                    if (found < 1) found = 1;
                    if (found > 4) found = 4;
                    string qLabel = ApiClient.CurrentTeamQueueType == "manual" ? "custom 2v2 lobby" : "2v2";
                    status = $"<color=#66CCFF>Searching for {qLabel}...</color>  <b>{found}/4</b>";
                    if (teamSearchBtn != null) teamSearchBtn.SetActive(false);
                    if (teamSearchCustomBtn != null) teamSearchCustomBtn.SetActive(false);
                    if (teamLeaveBtn != null) teamLeaveBtn.SetActive(true);
                    if (teamReadyBtn != null) teamReadyBtn.SetActive(false);
                    break;
                case ApiClient.TeamQueueState.Matched:
                    status = "<color=#FFD94D>Match found! Click <b>Ready Up</b>.</color>";
                    if (teamSearchBtn != null) teamSearchBtn.SetActive(false);
                    if (teamSearchCustomBtn != null) teamSearchCustomBtn.SetActive(false);
                    if (teamLeaveBtn != null) teamLeaveBtn.SetActive(true);
                    if (teamReadyBtn != null) teamReadyBtn.SetActive(true);
                    members = BuildTeamMembersString(poll);
                    break;
                case ApiClient.TeamQueueState.ReadySent:
                    status = "<color=#88FF88>Ready! Waiting for the other 3...</color>";
                    if (teamSearchBtn != null) teamSearchBtn.SetActive(false);
                    if (teamSearchCustomBtn != null) teamSearchCustomBtn.SetActive(false);
                    if (teamLeaveBtn != null) teamLeaveBtn.SetActive(true);
                    if (teamReadyBtn != null) teamReadyBtn.SetActive(false);
                    members = BuildTeamMembersString(poll);
                    break;
                default:
                    status = "";
                    break;
            }
            UIFactory.SetText(txtTeamStatus, status);
            UIFactory.SetText(txtTeamMembers, members);

            // DC grace banner. Driven by ApiClient.LastSeriesStateStatus etc. —
            // poll the most-recent series's state when we have one cached and
            // the user might be in a sticky-team requeue window.
            ApiClient.UpdateTeamSeriesStatePoll(force: false);
            int dcRemaining = ApiClient.LastSeriesDcGraceSeconds;
            string dcStatus = ApiClient.LastSeriesStateStatus;
            var dcBanner = (txtTeamDcGrace as Component)?.gameObject;
            if (dcBanner != null)
            {
                if (dcStatus == "dc_paused" && dcRemaining > 0)
                {
                    int mm = dcRemaining / 60, ss = dcRemaining % 60;
                    int t1w = ApiClient.LastSeriesT1Wins, t2w = ApiClient.LastSeriesT2Wins;
                    UIFactory.SetText(txtTeamDcGrace,
                        $"<color=#FFB347>Series paused — same 4 can re-queue to resume</color>  <color=#FF6688>{mm}:{ss:D2}</color>  <color=#888>(score {t1w}-{t2w})</color>");
                    dcBanner.SetActive(true);
                }
                else
                {
                    dcBanner.SetActive(false);
                }
            }

            // In Queue panel — refresh from /team/queue/list (2s throttle).
            ApiClient.UpdateTeamQueueList(force: false);
            var autoList = ApiClient.CachedTeamQueueAuto;
            var manualList = ApiClient.CachedTeamQueueManual;

            // Pick-teams row: only shown inside the manual queue. Highlight
            // the user's currently-claimed team (✓ in label + bright color).
            int myPreferred = 0;
            bool inManualQueue = ApiClient.CurrentTeamQueueType == "manual"
                && (st == ApiClient.TeamQueueState.Searching || st == ApiClient.TeamQueueState.Matched);
            if (manualList != null)
            {
                foreach (var q in manualList)
                {
                    if (q.steam_id == MatchTracker.LocalSteamId) { myPreferred = q.preferred_team; break; }
                }
            }
            if (teamPickT1Btn != null) teamPickT1Btn.SetActive(inManualQueue);
            if (teamPickT2Btn != null) teamPickT2Btn.SetActive(inManualQueue);
            var pickStatusComp = txtPickStatus as Component;
            if (pickStatusComp != null) pickStatusComp.gameObject.SetActive(inManualQueue);
            if (inManualQueue)
            {
                float t1Alpha = 0.95f, t2Alpha = 0.95f;
                var t1Color = myPreferred == 1
                    ? new Color(1.00f, 0.65f, 0.20f, t1Alpha)
                    : new Color(0.40f, 0.25f, 0.10f, t1Alpha * 0.7f);
                var t2Color = myPreferred == 2
                    ? new Color(0.30f, 0.70f, 1.00f, t2Alpha)
                    : new Color(0.10f, 0.25f, 0.45f, t2Alpha * 0.7f);
                UIFactory.SetImageColor(teamPickT1Btn, t1Color);
                UIFactory.SetImageColor(teamPickT2Btn, t2Color);
                UIFactory.SetText(UIFactory.GetButtonText(teamPickT1Btn),
                    myPreferred == 1 ? "<b>✓ Team 1 (Orange)</b>" : "Team 1 (Orange)");
                UIFactory.SetText(UIFactory.GetButtonText(teamPickT2Btn),
                    myPreferred == 2 ? "<b>✓ Team 2 (Blue)</b>" : "Team 2 (Blue)");
                int manualSearching = 0;
                if (manualList != null)
                    foreach (var q in manualList) if (q.status == "searching") manualSearching++;
                string ps = myPreferred == 0
                    ? $"<color=#FFB347>Claim Team 1 or Team 2.</color>  <color=#888>({manualSearching}/4 in lobby)</color>"
                    : $"<color=#88FF88>Locked in to Team {myPreferred}.</color>  <color=#888>({manualSearching}/4 in lobby)</color>";
                UIFactory.SetText(txtPickStatus, ps);
            }

            RenderTeamQueueSection(autoList, txtTeamQueueListHeader, txtTeamQueueListBody, "Random Queue");
            RenderTeamQueueSection(manualList, txtTeamQueueManualHeader, txtTeamQueueManualBody, "Custom Lobbies");

            // Leaderboard
            var lb = ApiClient.CachedTeamLeaderboard ?? new List<ApiClient.TeamLeaderboardEntry>();
            string sortKey = ApiClient.CachedTeamLeaderboardSort ?? "rating";

            // Highlight the active sort column header.
            if (teamLBSortKeys != null && teamLBHeaderTexts != null && teamLBSortBtns != null)
            {
                for (int hi = 0; hi < teamLBSortKeys.Length; hi++)
                {
                    bool active = teamLBSortKeys[hi] != null && teamLBSortKeys[hi] == sortKey;
                    string label;
                    switch (hi)
                    {
                        case 0: label = "#"; break;
                        case 1: label = "Player"; break;
                        case 2: label = "Rating"; break;
                        case 3: label = "W-L"; break;
                        case 4: label = "WR"; break;
                        case 5: label = "Avg Mate Elo"; break;
                        case 6: label = "Gold"; break;
                        case 7: label = "XP"; break;
                        default: label = ""; break;
                    }
                    if (active) label += " v";
                    UIFactory.SetText(teamLBHeaderTexts[hi], label);
                    if (teamLBSortBtns[hi] != null)
                        UIFactory.SetImageColor(teamLBSortBtns[hi],
                            active ? new Color(0.30f, 0.40f, 0.55f, 0.95f) : new Color(0.18f, 0.20f, 0.24f, 0.85f));
                }
            }

            for (int i = 0; i < teamLBRows.Count; i++)
            {
                var row = teamLBRows[i];
                if (i >= lb.Count) { row.root.SetActive(false); continue; }
                var e = lb[i];
                bool me = e.steam_id == MatchTracker.LocalSteamId;
                UIFactory.SetText(row.txtRank, $"#{e.rank}");
                // Title goes AFTER the name in [brackets] (matches 1v1 lb).
                string nameDisplay = Trunc(e.display_name, 14);
                if (!string.IsNullOrEmpty(e.title))
                {
                    string col = string.IsNullOrEmpty(e.title_color) ? "#FFD94D" : e.title_color;
                    nameDisplay = $"{nameDisplay} <color={col}>[{Trunc(e.title, 12)}]</color>";
                }
                UIFactory.SetText(row.txtName, nameDisplay);
                UIFactory.SetColor(row.txtName, me ? C_GREEN : C_WHITE);
                UIFactory.SetText(row.txtRating, $"{e.rating}");
                UIFactory.SetText(row.txtWL, $"{e.series_wins}-{e.series_losses}");
                UIFactory.SetText(row.txtWR, $"{e.win_rate * 100f:F0}%");
                UIFactory.SetText(row.txtMate, e.avg_teammate_elo > 0 ? $"{e.avg_teammate_elo}" : "—");
                UIFactory.SetText(row.txtGold, $"{e.team_gold_earned}");
                UIFactory.SetText(row.txtXp,   $"{e.team_xp_earned}");
                row.root.SetActive(true);
            }
            if (lb.Count == 0)
                UIFactory.SetText(txtTeamLBHeader, "<b>2v2 Leaderboard</b>  <color=#888>— no completed series yet</color>");
            else
                UIFactory.SetText(txtTeamLBHeader, $"<b>2v2 Leaderboard</b>  <color=#888>({lb.Count} ranked)</color>");

            // Recent 2v2 Series — paginated global feed. Drives off the new
            // /team/all-series-paged endpoint so non-participants can see the
            // full series history. Each visible series renders: header row
            // (outcome from caller perspective + score + date + caller's elo
            // delta + caller's gold/xp earned), team line with titles, then
            // one row per game with team-aggregated cards.
            var pagedSeries = ApiClient.CachedTeamSeriesPaged ?? new List<ApiClient.TeamSeriesPagedEntry>();
            string mySid = MatchTracker.LocalSteamId;
            int rowIdx = 0;
            foreach (var s in pagedSeries)
            {
                if (rowIdx >= teamHistRows.Count) break;

                // Caller-perspective outcome. If caller isn't in this series,
                // render neutral (gray) and show t1-t2 score raw.
                ApiClient.TeamSeriesSlot mySlot = null;
                int callerTeam = 0;
                if (s.t1a?.steam_id == mySid) { mySlot = s.t1a; callerTeam = 1; }
                else if (s.t1b?.steam_id == mySid) { mySlot = s.t1b; callerTeam = 1; }
                else if (s.t2a?.steam_id == mySid) { mySlot = s.t2a; callerTeam = 2; }
                else if (s.t2b?.steam_id == mySid) { mySlot = s.t2b; callerTeam = 2; }

                bool callerInSeries = mySlot != null;
                int leftScore = callerInSeries && callerTeam == 2 ? s.t2_series_wins : s.t1_series_wins;
                int rightScore = callerInSeries && callerTeam == 2 ? s.t1_series_wins : s.t2_series_wins;
                bool seriesWon = callerInSeries && (s.winner_team == callerTeam);
                string outcome;
                if (callerInSeries) outcome = seriesWon ? "<color=#00FF00>W</color>" : "<color=#FF6666>L</color>";
                else                outcome = "<color=#888>·</color>";

                string ratingDelta = "";
                if (mySlot != null && Mathf.Abs(mySlot.rating_change) > 0.01f)
                {
                    string rcCol = mySlot.rating_change > 0 ? "#00FF00" : "#FF6666";
                    ratingDelta = $"  <color={rcCol}>{(mySlot.rating_change > 0 ? "+" : "")}{mySlot.rating_change:F0} elo</color>";
                }
                string econ = "";
                if (mySlot != null && (mySlot.gold_earned > 0 || mySlot.xp_earned > 0))
                {
                    econ = $"  <color=#FFD94D>+{mySlot.gold_earned}g</color>  <color=#88CCFF>+{mySlot.xp_earned}xp</color>";
                }
                string dt = "";
                try
                {
                    if (!string.IsNullOrEmpty(s.completed_at) && s.completed_at.Length >= 10)
                        dt = DateTime.Parse(s.completed_at).ToString("M/d");
                }
                catch { }

                var hdr = teamHistRows[rowIdx++];
                UIFactory.SetText(hdr.txtLine1,
                    $"{outcome} <b>Series {leftScore}-{rightScore}</b>  <color=#999>{dt}</color>{ratingDelta}{econ}");
                // Team line: render titles + names. T1 left, T2 right (caller's
                // team rendered LEFT when participant; otherwise raw t1 first).
                ApiClient.TeamSeriesSlot leftA, leftB, rightA, rightB;
                if (callerInSeries && callerTeam == 2)
                { leftA = s.t2a; leftB = s.t2b; rightA = s.t1a; rightB = s.t1b; }
                else
                { leftA = s.t1a; leftB = s.t1b; rightA = s.t2a; rightB = s.t2b; }
                string leftTeamColor = callerInSeries ? "#88CCFF" : "#FFB088";
                string rightTeamColor = "#FFB088";
                string ll = $"<color={leftTeamColor}>{FormatTitleName(leftA)} + {FormatTitleName(leftB)}</color>"
                          + $"  <color=#666>vs</color>  "
                          + $"<color={rightTeamColor}>{FormatTitleName(rightA)} + {FormatTitleName(rightB)}</color>";
                // Series-header row: line2 holds the team summary, cards block hidden.
                UIFactory.SetText(hdr.txtLine2, ll);
                var hl2 = (hdr.txtLine2 as Component)?.gameObject;
                if (hl2 != null) hl2.SetActive(true);
                if (hdr.cardsRow != null) hdr.cardsRow.SetActive(false);
                SetTeamHistRowPrefH(hdr, 50);
                hdr.root.SetActive(true);

                // Per-match rows. Each game shows the outcome line on top and
                // a two-column stacked card list below — one column per team,
                // grouped by player name (Excel-style, no truncation).
                int gameNum = 0;
                foreach (var m in s.matches)
                {
                    if (rowIdx >= teamHistRows.Count) break;
                    gameNum++;
                    int leftR = (callerInSeries && callerTeam == 2) ? m.t2_rounds_won : m.t1_rounds_won;
                    int rightR = (callerInSeries && callerTeam == 2) ? m.t1_rounds_won : m.t2_rounds_won;
                    string gOut;
                    if (callerInSeries)
                        gOut = leftR > rightR ? "<color=#00FF00>W</color>" : "<color=#FF6666>L</color>";
                    else
                        gOut = "<color=#888>·</color>";

                    string leftCards  = BuildTeamCardsColumn(m, leftA, leftB);
                    string rightCards = BuildTeamCardsColumn(m, rightA, rightB);

                    var row = teamHistRows[rowIdx++];
                    UIFactory.SetText(row.txtLine1,
                        $"  <color=#666>—</color>  Game {gameNum}: {gOut} {leftR}-{rightR}");
                    // Hide line2; show stacked cards block.
                    var rl2 = (row.txtLine2 as Component)?.gameObject;
                    if (rl2 != null) rl2.SetActive(false);
                    UIFactory.SetText(row.txtCardsLeft,  string.IsNullOrEmpty(leftCards)  ? "<color=#666>—</color>" : leftCards);
                    UIFactory.SetText(row.txtCardsRight, string.IsNullOrEmpty(rightCards) ? "<color=#666>—</color>" : rightCards);
                    if (row.cardsRow != null) row.cardsRow.SetActive(true);

                    // Auto-size the row to fit the taller of the two card columns.
                    int linesLeft  = CountCardLines(m, leftA, leftB);
                    int linesRight = CountCardLines(m, rightA, rightB);
                    int linesMax = Math.Max(2, Math.Max(linesLeft, linesRight));
                    int cardsBlockH = linesMax * 17 + 4;
                    SetTeamHistRowPrefH(row, 26 + cardsBlockH);
                    row.root.SetActive(true);
                }
            }
            // Hide unused rows.
            for (int i = rowIdx; i < teamHistRows.Count; i++) teamHistRows[i].root.SetActive(false);

            int total = ApiClient.CachedTeamSeriesTotal;
            int totalPages = ApiClient.CachedTeamSeriesTotalPages;
            int curPage = ApiClient.CachedTeamSeriesPage;
            if (total == 0)
            {
                UIFactory.SetText(txtTeamHistHeader, "<b>Recent 2v2 Series</b>  <color=#888>— none yet</color>");
                if (txtTeamHistPageIndicator != null) UIFactory.SetText(txtTeamHistPageIndicator, "—");
                if (teamHistPrevBtn != null) teamHistPrevBtn.SetActive(false);
                if (teamHistNextBtn != null) teamHistNextBtn.SetActive(false);
            }
            else
            {
                UIFactory.SetText(txtTeamHistHeader, $"<b>Recent 2v2 Series</b>  <color=#888>({total} total)</color>");
                if (txtTeamHistPageIndicator != null)
                    UIFactory.SetText(txtTeamHistPageIndicator, $"{curPage + 1}/{Math.Max(1, totalPages)}");
                if (teamHistPrevBtn != null) teamHistPrevBtn.SetActive(curPage > 0);
                if (teamHistNextBtn != null) teamHistNextBtn.SetActive(curPage + 1 < totalPages);
            }
        }

        private static string FormatTitleName(ApiClient.TeamSeriesSlot s)
        {
            if (s == null) return "?";
            string nm = Trunc(s.name ?? "?", 12);
            if (string.IsNullOrEmpty(s.title)) return nm;
            string col = string.IsNullOrEmpty(s.title_color) ? "#FFD94D" : s.title_color;
            return $"{nm} <color={col}>[{Trunc(s.title, 10)}]</color>";
        }

        // Set the preferredHeight on a TeamHistRow so the outer scroll-content
        // VLG sizes it to fit the dynamic cards block. Also stretches the two
        // card column text fields to the full row content height so wrapping +
        // tall lists render in-place rather than clipping at a fixed sizeDelta.
        private static void SetTeamHistRowPrefH(TeamHistRow row, int prefH)
        {
            try
            {
                var le = row.root.GetComponent(UIFactory.tLE);
                if (le != null)
                {
                    var pP = UIFactory.tLE.GetProperty("preferredHeight", BindingFlags.Public | BindingFlags.Instance);
                    pP?.SetValue(le, (float)prefH);
                }
                // Also resize the inner text columns so card content has room.
                if (row.cardsRow != null && row.cardsRow.activeSelf)
                {
                    int contentH = Math.Max(40, prefH - 26);
                    void resizeText(object t)
                    {
                        var c = t as Component;
                        if (c == null) return;
                        var rt = c.GetComponent<RectTransform>();
                        if (rt == null) return;
                        var sz = rt.sizeDelta;
                        rt.sizeDelta = new Vector2(sz.x, contentH);
                    }
                    resizeText(row.txtCardsLeft);
                    resizeText(row.txtCardsRight);
                }
            }
            catch (Exception ex) { Plugin.Log.LogWarning($"[2v2-HIST] row size update failed: {ex.Message}"); }
        }

        // Build a per-team stacked column listing every card pick, grouped by
        // player. Excel-style: each player's name is its own line followed by
        // their card names indented beneath. Returns empty if no card data.
        private static string BuildTeamCardsColumn(ApiClient.TeamSeriesMatch m, ApiClient.TeamSeriesSlot a, ApiClient.TeamSeriesSlot b)
        {
            if (m == null || m.cards_by_player == null) return "";
            var sb = new StringBuilder();
            void appendFor(ApiClient.TeamSeriesSlot s)
            {
                if (s == null || string.IsNullOrEmpty(s.steam_id)) return;
                if (sb.Length > 0) sb.Append("\n");
                bool hasCards = m.cards_by_player.TryGetValue(s.steam_id, out var cards) && cards != null && cards.Count > 0;
                // Bold + brighter player-name header so each player block reads
                // as a heading inside the column.
                sb.Append("<b>").Append(Trunc(s.name ?? "?", 14)).Append("</b>");
                if (!hasCards)
                {
                    sb.Append("\n  <color=#666>—</color>");
                    return;
                }
                // Two cards per line, comma-separated. Each pair starts a new
                // line so the column stays narrow and reads top-to-bottom.
                for (int i = 0; i < cards.Count; i += 2)
                {
                    sb.Append("\n  ").Append(cards[i]);
                    if (i + 1 < cards.Count) sb.Append(", ").Append(cards[i + 1]);
                }
            }
            appendFor(a);
            appendFor(b);
            return sb.ToString();
        }

        // Compute a vertical pixel budget for one cards-column. Header (player
        // name) + ceil(cards/2) lines because each line holds two cards.
        private static int CountCardLines(ApiClient.TeamSeriesMatch m, ApiClient.TeamSeriesSlot a, ApiClient.TeamSeriesSlot b)
        {
            int lines = 0;
            void countFor(ApiClient.TeamSeriesSlot s)
            {
                if (s == null || string.IsNullOrEmpty(s.steam_id)) return;
                lines += 1; // player name header
                if (m != null && m.cards_by_player != null
                    && m.cards_by_player.TryGetValue(s.steam_id, out var cards) && cards != null && cards.Count > 0)
                {
                    lines += (cards.Count + 1) / 2; // 2 cards per line, ceil
                }
                else
                {
                    lines += 1; // "—"
                }
            }
            countFor(a);
            countFor(b);
            return lines;
        }

        // Render one half of the split In Queue panel (Random or Custom).
        private static void RenderTeamQueueSection(
            List<ApiClient.TeamQueueListEntry> list, object header, object body, string label)
        {
            int n = list != null ? list.Count : 0;
            if (n == 0)
            {
                UIFactory.SetText(header, $"<b>{label}</b>  <color=#888>(empty)</color>");
                UIFactory.SetText(body, $"<color=#888>No one in {label.ToLower()} right now.</color>");
                return;
            }
            UIFactory.SetText(header, $"<b>{label}</b>  <color=#888>({n})</color>");
            var sb = new StringBuilder();
            foreach (var q in list)
            {
                bool isMe = q.steam_id == MatchTracker.LocalSteamId;
                string nameC = isMe ? "<color=#88FF88>" : "<color=#FFFFFF>";
                string ratingDisplay = q.using_fallback_rating
                    ? $"<color=#FFB347>{q.balance_rating}</color> <color=#888>1v1</color>"
                    : $"<color=#FFFFFF>{q.rating}</color>";
                string statusTag = q.status == "searching"
                    ? $"<color=#66CCFF>searching</color>"
                    : q.status == "matched" ? $"<color=#FFD94D>matched</color>" : $"<color=#88FF88>{q.status}</color>";
                int waitMin = q.wait_seconds / 60;
                int waitSec = q.wait_seconds % 60;
                string waitStr = waitMin > 0 ? $"{waitMin}m{waitSec:D2}s" : $"{waitSec}s";
                string teamTag = "";
                if (q.preferred_team == 1) teamTag = "  <color=#FFB347>T1</color>";
                else if (q.preferred_team == 2) teamTag = "  <color=#88AAFF>T2</color>";
                sb.Append($"  {nameC}{Trunc(q.display_name, 18)}</color>  {ratingDisplay}  {statusTag}  <color=#888>{waitStr}</color>{teamTag}\n");
            }
            UIFactory.SetText(body, sb.ToString());
        }

        // Helpers for the per-match cards line.
        private static string JoinTeamCards(ApiClient.TeamMatchHistoryEntry m, int team)
        {
            if (m.cards_by_player == null || m.cards_by_player.Count == 0) return "";
            string aSid = team == 1 ? m.t1a_steam_id : m.t2a_steam_id;
            string bSid = team == 1 ? m.t1b_steam_id : m.t2b_steam_id;
            string aName = team == 1 ? m.t1a_name : m.t2a_name;
            string bName = team == 1 ? m.t1b_name : m.t2b_name;
            var sb = new StringBuilder();
            sb.Append(Trunc(aName, 8)).Append(": ");
            if (m.cards_by_player.TryGetValue(aSid, out var aCards) && aCards.Count > 0)
                sb.Append(string.Join(", ", aCards.GetRange(0, Math.Min(aCards.Count, 6)).ToArray()));
            else sb.Append("(no cards)");
            sb.Append("  |  ");
            sb.Append(Trunc(bName, 8)).Append(": ");
            if (m.cards_by_player.TryGetValue(bSid, out var bCards) && bCards.Count > 0)
                sb.Append(string.Join(", ", bCards.GetRange(0, Math.Min(bCards.Count, 6)).ToArray()));
            else sb.Append("(no cards)");
            return sb.ToString();
        }

        private static string BuildTeamMembersString(ApiClient.TeamQueuePollData poll)
        {
            if (poll == null) return "";
            var sb = new StringBuilder();
            sb.Append("<color=#66CCFF>Your Team:</color> ");
            sb.Append("<b>YOU</b>");
            if (poll.teammates != null)
                foreach (var t in poll.teammates) sb.Append($", {Trunc(t.display_name, 16)} {FmtMemberRating(t)}");
            sb.Append("\n<color=#FF6688>Opponents:</color> ");
            if (poll.opponents != null)
            {
                bool first = true;
                foreach (var o in poll.opponents)
                {
                    if (!first) sb.Append(", ");
                    sb.Append($"{Trunc(o.display_name, 16)} {FmtMemberRating(o)}");
                    first = false;
                }
            }
            return sb.ToString();
        }

        // Format the queuer's rating with a hint if the balancer is using their
        // 1v1 rating instead of their 2v2 rating (low completed_series). Lets
        // testers verify the elo-fallback path is firing as expected.
        private static string FmtMemberRating(ApiClient.TeamQueueMember m)
        {
            if (m.using_fallback_rating && m.balance_rating > 0)
                return $"(<color=#FFB347>{m.balance_rating}</color> <color=#888>1v1, {m.completed_series}/10 2v2 series</color>)";
            return $"({m.rating})";
        }
    }
}
