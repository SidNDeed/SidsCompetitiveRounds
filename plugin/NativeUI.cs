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
        // Bug #73: the guard used to be one GLOBAL 0.2s window — clicking any
        // button armed it, and a click on a DIFFERENT button (e.g. Shop row →
        // Artist sub-tab) inside the window was silently swallowed, which read
        // as "sometimes the tab doesn't respond". The guard only exists to
        // dedup the SAME control's Button+ClickHandler double-fire (learning
        // #7), so the window is now per-control. Callers without a key share
        // one legacy bucket (still deduped against themselves only).
        private static readonly Dictionary<object, float> _lastByKey = new Dictionary<object, float>();
        private static readonly object _legacyKey = new object();
        public static bool Claim() => Claim(null);
        public static bool Claim(object key)
        {
            key = key ?? _legacyKey;
            float now = Time.unscaledTime;
            if (_lastByKey.TryGetValue(key, out float last) && now - last < 0.2f) return false;
            _lastByKey[key] = now;
            // Opportunistic prune so destroyed buttons' keys don't accumulate
            // over a long session (a few hundred entries max in practice).
            if (_lastByKey.Count > 600) _lastByKey.Clear();
            return true;
        }
    }

    internal static class UIFactory
    {
        internal static Type tImage, tButton, tCanvas, tLE;
        internal static Type tCanvasGroup;
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
                if(tCanvasGroup==null)tCanvasGroup=asm.GetType("UnityEngine.CanvasGroup");
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
            foreach(var tmp in UnityEngine.Object.FindObjectsOfType(tTMP)){try{var f=pTmpFont?.GetValue(tmp);if(f!=null){tmpFont=f;fontReady=true;TryInstallUnicodeFallback();return true;}}catch{}}
            return false;
        }

        // ── Unicode font fallback (v1.29, multi-language support) ─────────────
        // ROUNDS' Gravity SDF atlas has no Cyrillic / CJK / most non-ASCII —
        // foreign Steam names and chat rendered as squares (learning #47). Fix:
        // build DYNAMIC TMP font assets from installed OS fonts at runtime and
        // append them to (a) the Gravity asset's own fallback table (covers every
        // label that uses Gravity: our UI, chat log, vanilla nametags) and (b)
        // TMP_Settings' global fallback list (covers everything else). Dynamic
        // atlas mode populates glyphs on demand, so one Segoe UI asset covers
        // Latin-ext + Cyrillic + Greek, and the CJK families cover zh/ja/ko.
        // Foreign glyphs render in the OS font's style rather than Gravity —
        // an acceptable trade against □□□□.
        private static bool _unicodeFallbackInstalled;
        public static void TryInstallUnicodeFallback()
        {
            if (_unicodeFallbackInstalled || tmpFont == null) return;
            try
            {
                var fontAssetType = tmpFont.GetType();               // TMPro.TMP_FontAsset
                var mCreate = fontAssetType.GetMethod("CreateFontAsset",
                    BindingFlags.Public | BindingFlags.Static, null, new Type[] { typeof(Font) }, null);
                if (mCreate == null) { Plugin.Log.LogWarning("[FONT] TMP_FontAsset.CreateFontAsset(Font) not found — unicode fallback disabled"); return; }

                string[] installed;
                try { installed = Font.GetOSInstalledFontNames(); } catch { installed = new string[0]; }
                var installedSet = new HashSet<string>(installed, StringComparer.OrdinalIgnoreCase);
                // One candidate list per script family — first installed name wins.
                string[][] families = new string[][]
                {
                    new[] { "Segoe UI", "Arial", "Tahoma" },                        // Latin-ext / Cyrillic / Greek
                    new[] { "Microsoft YaHei", "SimHei", "SimSun" },                // Chinese
                    new[] { "Yu Gothic UI", "Meiryo", "MS Gothic" },                // Japanese
                    new[] { "Malgun Gothic", "Gulim" },                             // Korean
                };
                var created = new List<object>();
                foreach (var fam in families)
                {
                    foreach (var name in fam)
                    {
                        if (!installedSet.Contains(name)) continue;
                        try
                        {
                            var osFont = Font.CreateDynamicFontFromOSFont(name, 48);
                            if (osFont == null) continue;
                            var asset = mCreate.Invoke(null, new object[] { osFont });
                            if (asset != null)
                            {
                                created.Add(asset);
                                Plugin.Log.LogInfo($"[FONT] built dynamic fallback font asset from OS font '{name}'");
                            }
                        }
                        catch (Exception fx) { Plugin.Log.LogWarning($"[FONT] fallback build failed for '{name}': {fx.Message}"); }
                        break; // one per family, whether it worked or not
                    }
                }
                if (created.Count == 0) { Plugin.Log.LogWarning("[FONT] no OS fallback fonts available"); return; }

                // (a) Gravity's instance fallback table. TMP 2.x: fallbackFontAssetTable;
                // TMP 1.x: fallbackFontAssets. Try property then field, both names.
                AppendToFontList(tmpFont, fontAssetType, created, "fallbackFontAssetTable");
                AppendToFontList(tmpFont, fontAssetType, created, "fallbackFontAssets");
                // (b) Global TMP_Settings fallback list (static property).
                try
                {
                    var tSettings = fontAssetType.Assembly.GetType("TMPro.TMP_Settings");
                    var pGlobal = tSettings?.GetProperty("fallbackFontAssets", BindingFlags.Public | BindingFlags.Static);
                    var list = pGlobal?.GetValue(null) as System.Collections.IList;
                    if (list != null) foreach (var a in created) list.Add(a);
                }
                catch (Exception gx) { Plugin.Log.LogWarning($"[FONT] TMP_Settings fallback append failed: {gx.Message}"); }

                _unicodeFallbackInstalled = true;
                Plugin.Log.LogInfo($"[FONT] unicode fallback installed ({created.Count} OS font asset(s)) — foreign names/chat now render");
            }
            catch (Exception ex) { Plugin.Log.LogWarning($"[FONT] unicode fallback install failed: {ex.Message}"); }
        }

        private static void AppendToFontList(object fontAsset, Type fontAssetType, List<object> assets, string memberName)
        {
            try
            {
                var bf = BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance;
                System.Collections.IList list = null;
                var prop = fontAssetType.GetProperty(memberName, bf);
                if (prop != null) list = prop.GetValue(fontAsset) as System.Collections.IList;
                if (list == null)
                {
                    var field = fontAssetType.GetField(memberName, bf);
                    if (field != null) list = field.GetValue(fontAsset) as System.Collections.IList;
                    if (list == null && field != null)
                    {
                        // Null list — create one of the right type and assign.
                        try
                        {
                            list = (System.Collections.IList)Activator.CreateInstance(field.FieldType);
                            field.SetValue(fontAsset, list);
                        }
                        catch { }
                    }
                    if (list == null && prop != null && prop.CanWrite)
                    {
                        try
                        {
                            list = (System.Collections.IList)Activator.CreateInstance(prop.PropertyType);
                            prop.SetValue(fontAsset, list);
                        }
                        catch { }
                    }
                }
                if (list == null) return;
                foreach (var a in assets)
                    if (!list.Contains(a)) list.Add(a);
            }
            catch { }
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
        {var go=new GameObject(name);go.transform.SetParent(parent,false);var rt=go.AddComponent<RectTransform>();Vector2 sz=sizeDelta??new Vector2(200,24);rt.sizeDelta=sz;if(sz.x>0&&sz.y>0)AddLE(go,prefW:sz.x,prefH:sz.y);var tmp=go.AddComponent(tTMP);pTmpText?.SetValue(tmp,richText?_BoldWrap(text):text);/* Bug batch item 12: global floor — below ~12pt the Gravity SDF font drops thin glyphs (l, i, -) even in bold. */fontSize=Mathf.Max(fontSize,12f);pTmpFontSize?.SetValue(tmp,fontSize);pTmpColor?.SetValue(tmp,color);pTmpRichText?.SetValue(tmp,richText);pTmpRaycastTarget?.SetValue(tmp,raycastTarget);if(tmpFont!=null)pTmpFont?.SetValue(tmp,tmpFont);pTmpCharSpacing?.SetValue(tmp,1.0f);try{pTmpFontStyle?.SetValue(tmp,Enum.ToObject(pTmpFontStyle.PropertyType,1));}catch{}try{var at=pTmpAlignment?.PropertyType;if(at!=null)pTmpAlignment.SetValue(tmp,Enum.ToObject(at,alignment));}catch{}return tmp;}

        public static GameObject CreateButton(string name,Transform parent,string label,float fontSize,Color textColor,Color bgColor,UnityEngine.Events.UnityAction onClick,Vector2? sizeDelta=null)
        {
            var sz=sizeDelta??new Vector2(100,28);var go=CreatePanel(name,parent,bgColor,sizeDelta:sz);var rt=go.GetComponent<RectTransform>();rt.anchorMin=rt.anchorMax=new Vector2(0.5f,0.5f);rt.sizeDelta=sz;AddLE(go,prefW:sz.x,prefH:sz.y);
            CreateText(name+"_Txt",go.transform,label,fontSize,textColor,AlignMidCenter,sizeDelta:Vector2.zero);
            var txtRT=go.transform.GetChild(0).GetComponent<RectTransform>();txtRT.anchorMin=Vector2.zero;txtRT.anchorMax=Vector2.one;txtRT.offsetMin=Vector2.zero;txtRT.offsetMax=Vector2.zero;
            var innerLE=go.transform.GetChild(0).GetComponent(tLE);if(innerLE!=null)UnityEngine.Object.Destroy(innerLE as UnityEngine.Object);
            var btn=go.AddComponent(tButton);try{var tgt=tButton.GetProperty("targetGraphic",BindingFlags.Public|BindingFlags.Instance);var img=go.GetComponent(tImage);if(tgt!=null&&img!=null)tgt.SetValue(btn,img);}catch{}
            if(pBtnOnClick!=null&&mOnClickAdd!=null&&onClick!=null){var guarded=new UnityEngine.Events.UnityAction(()=>{if(ClickGuard.Claim(go))onClick();});mOnClickAdd.Invoke(pBtnOnClick.GetValue(btn),new object[]{guarded});}
            if(onClick!=null){var ch=go.AddComponent<ClickHandler>();ch.onClick=()=>{if(ClickGuard.Claim(go))onClick();};}
            return go;
        }

        public static ScrollViewRefs CreateScrollView(string name,Transform parent,float spacing=2f,bool childForceExpandWidth=true)
        {var refs=new ScrollViewRefs();var sGO=new GameObject(name);sGO.transform.SetParent(parent,false);var sRT=sGO.AddComponent<RectTransform>();sRT.anchorMin=Vector2.zero;sRT.anchorMax=Vector2.one;sRT.offsetMin=Vector2.zero;sRT.offsetMax=Vector2.zero;var vp=new GameObject("Viewport");vp.transform.SetParent(sGO.transform,false);var vpRT=vp.AddComponent<RectTransform>();vpRT.anchorMin=Vector2.zero;vpRT.anchorMax=Vector2.one;vpRT.offsetMin=Vector2.zero;vpRT.offsetMax=Vector2.zero;var vpImg=vp.AddComponent(tImage);pImgColor?.SetValue(vpImg,new Color(0,0,0,0.01f));/* raycastTarget so the mouse wheel scrolls anywhere over the viewport — including empty space below/around the rows, not just when hovering a row button. */tImage.GetProperty("raycastTarget",BindingFlags.Public|BindingFlags.Instance)?.SetValue(vpImg,true);if(tMask!=null){var m=vp.AddComponent(tMask);tMask.GetProperty("showMaskGraphic",BindingFlags.Public|BindingFlags.Instance)?.SetValue(m,false);}var cnt=new GameObject("Content");cnt.transform.SetParent(vp.transform,false);var cRT=cnt.AddComponent<RectTransform>();cRT.anchorMin=new Vector2(0,1);cRT.anchorMax=new Vector2(1,1);cRT.pivot=new Vector2(0.5f,1f);cRT.sizeDelta=Vector2.zero;if(tVLG!=null){var v=cnt.AddComponent(tVLG);pVLGSpacing?.SetValue(v,spacing);pVLGChildForceW?.SetValue(v,childForceExpandWidth);pVLGChildForceH?.SetValue(v,false);pVLGChildControlW?.SetValue(v,true);pVLGChildControlH?.SetValue(v,true);}if(tCSF!=null){var csf=cnt.AddComponent(tCSF);var ft=pCSFFit?.PropertyType;if(ft!=null)pCSFFit.SetValue(csf,Enum.ToObject(ft,2));}var sr=sGO.AddComponent(tScrollRect);pSRContent?.SetValue(sr,cRT);pSRViewport?.SetValue(sr,vpRT);pSRVertical?.SetValue(sr,true);pSRHorizontal?.SetValue(sr,false);pSRScrollSensitivity?.SetValue(sr,25f);var mt=pSRMovementType?.PropertyType;if(mt!=null)pSRMovementType.SetValue(sr,Enum.ToObject(mt,1));refs.scrollGO=sGO;refs.content=cnt;refs.contentRT=cRT;return refs;}
        public struct ScrollViewRefs{public GameObject scrollGO,content;public RectTransform contentRT;}

        public static void AddVLG(GameObject go,float spacing=2,int padL=0,int padR=0,int padT=0,int padB=0,bool forceExpandW=true,bool forceExpandH=false){if(tVLG==null)return;var v=go.AddComponent(tVLG);pVLGSpacing?.SetValue(v,spacing);pVLGPadding?.SetValue(v,new RectOffset(padL,padR,padT,padB));pVLGChildForceW?.SetValue(v,forceExpandW);pVLGChildForceH?.SetValue(v,forceExpandH);pVLGChildControlW?.SetValue(v,true);pVLGChildControlH?.SetValue(v,true);}
        public static void AddHLG(GameObject go,float spacing=4,int padL=0,int padR=0,int padT=0,int padB=0,bool forceExpandW=false,bool forceExpandH=true){if(tHLG==null)return;var h=go.AddComponent(tHLG);pHLGSpacing?.SetValue(h,spacing);pHLGPadding?.SetValue(h,new RectOffset(padL,padR,padT,padB));pHLGChildForceW?.SetValue(h,forceExpandW);pHLGChildForceH?.SetValue(h,forceExpandH);pHLGChildControlW?.SetValue(h,true);pHLGChildControlH?.SetValue(h,true);}
        public static void AddLE(GameObject go,float minW=-1,float minH=-1,float prefW=-1,float prefH=-1,float flexW=-1,float flexH=-1){if(tLE==null)return;var le=go.AddComponent(tLE);if(minW>=0)pLEMinW?.SetValue(le,minW);if(minH>=0)pLEMinH?.SetValue(le,minH);if(prefW>=0)pLEPrefW?.SetValue(le,prefW);if(prefH>=0)pLEPrefH?.SetValue(le,prefH);if(flexW>=0)pLEFlexW?.SetValue(le,flexW);if(flexH>=0)pLEFlexH?.SetValue(le,flexH);}
        // Update an EXISTING LayoutElement's preferredHeight (AddLE would stack a second component).
        public static void SetPrefH(GameObject go,float prefH){if(tLE==null||go==null)return;var le=go.GetComponent(tLE);if(le!=null)pLEPrefH?.SetValue(le,prefH);}
        public static void SetPrefWH(GameObject go,float prefW,float prefH){if(tLE==null||go==null)return;var le=go.GetComponent(tLE);if(le==null)return;pLEPrefW?.SetValue(le,prefW);pLEPrefH?.SetValue(le,prefH);}
        // Make an EXISTING panel clickable (Button on its own Image) — same wiring as
        // CreateButton but without spawning a new GO. Child buttons still win raycasts.
        public static void AddClick(GameObject go,UnityEngine.Events.UnityAction onClick){
            if(go==null||tButton==null||onClick==null)return;
            var btn=go.AddComponent(tButton);
            try{var tgt=tButton.GetProperty("targetGraphic",BindingFlags.Public|BindingFlags.Instance);var img=go.GetComponent(tImage);if(tgt!=null&&img!=null)tgt.SetValue(btn,img);}catch{}
            if(pBtnOnClick!=null&&mOnClickAdd!=null){var guarded=new UnityEngine.Events.UnityAction(()=>{if(ClickGuard.Claim(go))onClick();});mOnClickAdd.Invoke(pBtnOnClick.GetValue(btn),new object[]{guarded});}
            var ch=go.AddComponent<ClickHandler>();ch.onClick=()=>{if(ClickGuard.Claim(go))onClick();};
        }
        public static Component CreateFillBar(string name,Transform parent,Color bgColor,Color fillColor,float height=8f){var bgGO=new GameObject(name+"_BG");bgGO.transform.SetParent(parent,false);bgGO.AddComponent<RectTransform>();AddLE(bgGO,prefH:height,flexH:0);bgGO.AddComponent(tImage);pImgColor?.SetValue(bgGO.GetComponent(tImage),bgColor);var fGO=new GameObject(name+"_Fill");fGO.transform.SetParent(bgGO.transform,false);var fRT=fGO.AddComponent<RectTransform>();fRT.anchorMin=Vector2.zero;fRT.anchorMax=new Vector2(0f,1f);fRT.offsetMin=Vector2.zero;fRT.offsetMax=Vector2.zero;fGO.AddComponent(tImage);pImgColor?.SetValue(fGO.GetComponent(tImage),fillColor);return fRT;}
        public static void SetFill(Component f,float a){if(f==null)return;var rt=f as RectTransform;if(rt!=null)rt.anchorMax=new Vector2(Mathf.Clamp01(a),1f);}
        public static void SetText(object t,string s){if(t!=null)pTmpText?.SetValue(t,_BoldWrap(s??""));}
        public static void SetColor(object t,Color c){if(t!=null)pTmpColor?.SetValue(t,c);}
        public static void SetBold(object t,bool b){if(t==null)return;try{var tp=pTmpFontStyle?.PropertyType;if(tp!=null)pTmpFontStyle.SetValue(t,Enum.ToObject(tp,b?1:0));}catch{}}
        public static void SetWordWrap(object t,bool on){if(t==null||tTMP==null)return;try{var p=tTMP.GetProperty("enableWordWrapping",BindingFlags.Public|BindingFlags.Instance);p?.SetValue(t,on);}catch{}}
        // Release a text element's fixed preferred height so its OWN TMP-reported
        // (content-driven) height feeds the layout instead. CreateText always adds a
        // LayoutElement with prefH = sizeDelta.y (priority 1), which OVERRIDES TMP's
        // ILayoutElement (priority 0) — so any growing text inside a ScrollView+CSF
        // stays locked at sizeDelta.y and never scrolls. Setting the LE's preferred
        // dims to -1 makes the layout fall through to TMP's computed values; minH is
        // an optional floor. This is the missing piece behind "the panel won't scroll".
        public static void SetTextAutoHeight(object tmp,float minH=0f){if(tmp==null||tLE==null)return;try{var go=((Component)tmp).gameObject;var le=go.GetComponent(tLE);if(le==null)le=go.AddComponent(tLE);tLE.GetProperty("preferredHeight",BindingFlags.Public|BindingFlags.Instance)?.SetValue(le,-1f);tLE.GetProperty("preferredWidth",BindingFlags.Public|BindingFlags.Instance)?.SetValue(le,-1f);if(minH>0f)tLE.GetProperty("minHeight",BindingFlags.Public|BindingFlags.Instance)?.SetValue(le,minH);}catch{}}
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
        // When true, ClickHandlers ignore clicks — an IMGUI modal owns the screen.
        // Bug #75: the uGUI click-blocker only stops EventSystem raycasts, but
        // ClickHandler polls Input.GetMouseButtonDown directly and does its own
        // hit test, bypassing the blocker entirely — so shop/artist buttons behind
        // the artist price/stock modal still fired ("clickable through the menu").
        // CompetitiveUI sets this whenever any IMGUI modal is open, the same
        // condition that drives the uGUI blocker.
        public static bool ModalBlockInput;
        private bool ContainsScreenPoint(RectTransform target, Vector3 point)
        {
            if (target == null) return false;
            Vector3[] corners = new Vector3[4];
            target.GetWorldCorners(corners);
            float minX = float.PositiveInfinity, minY = float.PositiveInfinity;
            float maxX = float.NegativeInfinity, maxY = float.NegativeInfinity;
            for (int i = 0; i < corners.Length; i++)
            {
                Vector3 c = canvasCamera != null
                    ? canvasCamera.WorldToScreenPoint(corners[i])
                    : corners[i];
                minX = Mathf.Min(minX, c.x);
                minY = Mathf.Min(minY, c.y);
                maxX = Mathf.Max(maxX, c.x);
                maxY = Mathf.Max(maxY, c.y);
            }
            return point.x >= minX && point.x <= maxX
                && point.y >= minY && point.y <= maxY;
        }
        private bool IsInsideAncestorMasks(Vector3 point)
        {
            // Unity's EventSystem respects a ScrollView Mask when raycasting,
            // but this component polls Input directly. Enforce every ancestor
            // mask here too so clipped rows cannot be clicked through panels
            // that visually cover them.
            if (UIFactory.tMask == null) return true;
            Transform cursor = transform.parent;
            while (cursor != null)
            {
                try
                {
                    if (cursor.GetComponent(UIFactory.tMask) != null
                        && !ContainsScreenPoint(cursor as RectTransform, point))
                        return false;
                }
                catch { }
                cursor = cursor.parent;
            }
            return true;
        }
        private void Update()
        {
            if(rt==null||onClick==null||!gameObject.activeInHierarchy)return;
            if(ModalBlockInput)return;
            if(!Input.GetMouseButtonDown(0))return;
            if(!cameraResolved)ResolveCamera();
            Vector3 mp=Input.mousePosition;
            if(ContainsScreenPoint(rt,mp)&&IsInsideAncestorMasks(mp))onClick.Invoke();
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
        // Exposed for CompetitiveUI's card hover tooltip — only render when
        // My Stats (tab 0) is actually showing, otherwise the registered
        // rects from a previous My Stats refresh keep painting tooltips
        // over Shop/Admin/Settings tabs at the same screen positions.
        public static int CurrentTab => currentTab;
        private static Component listMenu;
        private static GameObject[] tabPanels;
        // (item 7 reorg) Two-row navigation: 9 top-level GROUP buttons + a sub-tab
        // row for groups with more than one member. Panel indices stay historical.
        private static GameObject[] groupButtons,subButtons;private static object[] groupTexts,subTexts;private static GameObject subTabBar;
        // Round 5 item 3: the sub-tab row is REPARENTED into the active tab's
        // panel (for Leaderboard: into the middle column, so the Live-Games and
        // player-detail side panels keep their full height up to the tab bar).
        // One anchor per groupable tab index; UpdateTabBarVisual moves the bar.
        private static GameObject[] subTabAnchors;
        private static GameObject MakeSubTabAnchor(int tabIdx, Transform parent, bool asFirst)
        {
            var a = new GameObject($"SubTabAnchor{tabIdx}");
            a.transform.SetParent(parent, false);
            a.AddComponent<RectTransform>();
            UIFactory.AddHLG(a, spacing: 0);
            UIFactory.AddLE(a, prefH: 30, minH: 30, flexH: 0);
            if (asFirst) a.transform.SetAsFirstSibling();
            if (subTabAnchors == null) subTabAnchors = new GameObject[NUM_TABS];
            subTabAnchors[tabIdx] = a;
            a.SetActive(false);
            return a;
        }
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
        private static object txtMyBets;   // v1.30 (#53): personal bet ledger under the live panel
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
        // F8: manual Refresh-button debounce. Mashing it fired a burst of fetches
        // every click (player stats + history + achievements + team + tab data) →
        // self-DoS of the server + the local HTTP coroutines. Gate to once / 2s.
        private static float _nextManualRefreshAt;
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

        /// <summary>Copy recent chat into caller-owned storage without allocating
        /// an array every OnGUI repaint.</summary>
        public static void CopyChatTail(List<ChatEntry> destination, int tail)
        {
            if (destination == null) return;
            lock (chatLinesLock)
            {
                destination.Clear();
                int start = Math.Max(0, chatLines.Count - tail);
                for (int i = start; i < chatLines.Count; i++) destination.Add(chatLines[i]);
            }
        }
        private static GameObject rankedContainer,casualContainer;
        private static List<HistoryRow> rankedRows=new List<HistoryRow>(),casualRows=new List<HistoryRow>();
        private static object txtRankedPage,txtCasualPage;private static GameObject rPrev,rNext,cPrev,cNext;private static int rankedPage,casualPage;
        // Card display mode toggle (v1.26.8). Persists across launches via PlayerPrefs.
        // When OFF (default), history rows show 2-letter chips like [MA][EM][EC] for
        // a compact scan. When ON, full names appear (legacy behavior). Sid wanted a
        // vanilla-style hover tooltip; that needs a screen-space hit-test system the
        // mod doesn't have yet — this toggle is the pragmatic interim.
        private const string PP_CARD_NAMES_FULL = "cr_history_card_names_full";
        private static bool _historyCardsFull = PlayerPrefs.GetInt(PP_CARD_NAMES_FULL, 0) != 0;
        private static GameObject rCardModeBtn, cCardModeBtn;
        private static object rCardModeTxt, cCardModeTxt;
        private static void ToggleHistoryCardMode()
        {
            _historyCardsFull = !_historyCardsFull;
            PlayerPrefs.SetInt(PP_CARD_NAMES_FULL, _historyCardsFull ? 1 : 0);
            PlayerPrefs.Save();
            dirty = true;
        }
        private static string HistoryCardModeLabel()
        {
            return _historyCardsFull ? "Cards: <color=#88FF88>FULL</color>"
                                     : "Cards: <color=#FFCC66>chips</color>";
        }
        private class HistoryRow{public GameObject root,seriesGO,btnId;public string currentMatchId;public object txtResult,txtOpp,txtFps,txtPing,txtXP,txtDate,txtCards,txtOppCards,txtSeriesHead,txtSeriesElo,txtStats,txtHitYou,txtBlockYou,txtKpsYou,txtHitOpp,txtBlockOpp,txtKpsOpp;}

        // July 22 item 6: short game code — first 12 hex of the match UUID,
        // dashes stripped, uppercase (same convention as ranked_/sct- rooms).
        private static string GameCode(string matchId){if(string.IsNullOrEmpty(matchId))return null;var hx=matchId.Replace("-","");return hx.Substring(0,Math.Min(12,hx.Length)).ToUpperInvariant();}
        /* Review [0]: NO ClickGuard here — both callers already claimed their
         * per-control key this frame (the ID button via CreateButton's wrapper,
         * the 2v2 row via Claim(row.root)); a same-frame re-claim on the same
         * key is deterministically rejected, which made the copy a 100% no-op. */
        private static void CopyGameCode(string matchId){if(string.IsNullOrEmpty(matchId))return;string code=GameCode(matchId);GUIUtility.systemCopyBuffer=code;CompetitiveUI.ShowNotification($"Game ID {code} copied - paste into /game in Discord",new Color(0.6f,0.9f,1f));}
        private static List<LBRow> lbRows=new List<LBRow>();private static object txtLBCount,txtLBDetail,txtLBDetailB,txtLBAch;
        private static string selectedSteamId="";private static ApiClient.PlayerStatsData selectedStats;
        // Clicked player's match history (for the detail panel's ranked-history + H2H-last-series
        // sections). Fetched on click via FetchMatchHistoryForView; does NOT touch the local
        // player's CachedMatchHistory. Keyed implicitly to selectedSteamId.
        private static List<ApiClient.MatchHistoryEntry> selectedViewHistory;
        // Pagination for "Ranked Series vs You" in the player-detail panel.
        private static int h2hSeriesPage = 0;
        private const int H2H_SERIES_PER_PAGE = 2;
        private static int h2hSeriesTotalPages = 1; // set by BuildViewHistoryText, read by the pager refresh
        private static GameObject h2hPager, h2hPrev, h2hNext; private static object txtH2hPage;
        private static string lbSort="rating";private static bool lbSortDesc=true;private static object[] lbSortTexts;private static GameObject[] lbSortBtns;
        private static int lbPage=0;private static object txtLBPage;private static GameObject lbPrev,lbNext,lbBlockBtn,lbBlockRow;private static object lbBlockTxt;
        // July 17 round 3 (Sid item 10): admin-only click-to-copy Steam ID row.
        private static object txtLBSteamId;
        private static GameObject lbGraphPanel;
        private static object txtRecentSeries;
        private static int recentSeriesPage=0;private static object txtSeriesPage;private static GameObject seriesPrev,seriesNext;
        private class LBRow{public GameObject root,hlWrap;public object txtRank,txtLv,txtName,txtRating,txtW,txtL,txtWL,txtGold;public string steamId;}
        private static List<CardRow> cardRows=new List<CardRow>();private static int cardFilter;private static string cardSort="times_picked";private static bool cardSortDesc=true;
        private static object[] cardSortTexts;private static GameObject[] cardSortBtns,cardFilterBtns;private static object[] cardFilterTexts;
        private class CardRow{public GameObject root;public GameObject hl;public object txtName,txtRarity,txtPicks,txtWins,txtWR,txtPass,txtTier;public GameObject tierBtn;public string cardName;}
        private static List<AchRow> achRows=new List<AchRow>();
        private class AchRow{public GameObject root;public GameObject main;public object txtIcon,txtName,txtDesc,txtDate;public string key;}
        private static object txtRankedStatus,txtQueueInfo,txtMatchFound,txtConnectLabel;
        private static GameObject lfpBtn;   // July 21 item 8: Discord LFP ping
        private static object txtVersionStatus;
        private static GameObject updateBtn;
        private static GameObject qSearchBtn,qCancelBtn,qMatchPanel,readyBtn,declineBtn,connectLabel,rankOnBtn,rankOffBtn;
        // TOURNAMENT GAME indicator - row below RankedRow, shows yellow text when
        // the local player is in a Photon room with someone who's an active
        // tournament opponent (sync or async).
        private static object txtTournamentGame;
        private static GameObject tournamentIndRow;
        // Column widths (scaled)
        // Round 4 item 4: widened to fill the middle column (the old 560px table
        // floated between two flex spacers — Sid's screenshot X'd the dead zones).
        private static readonly float[] LB_COL_W={40,40,300,92,56,56,80,90};
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
            /* Bug #46: use IsInOnlineRoom, not IsInRoom — Photon's OfflineMode (Sandbox)
             * counts as "in a room" and lingers at the main menu after leaving Sandbox,
             * which kept inGameMode=true and hid the ranked Disable button until relaunch. */
            bool inRoom=GameStateWatcher.IsInOnlineRoom;
            inGameMode=inRoom;
            // Always use our own overlay canvas - guarantees we render on top of all ROUNDS UI
            EnsureOverlayCanvas();
            bool builtThisOpen=false;
            if(!pageBuilt||pageGO==null||pageGO.transform.parent!=overlayCanvasGO.transform){if(pageGO!=null)UnityEngine.Object.Destroy(pageGO);pageBuilt=false;BuildPage(overlayCanvasGO.transform);if(!pageBuilt)return;builtThisOpen=true;}
            pageGO.SetActive(true);
            // ForceUpdateCanvases is a synchronous whole-canvas layout rebuild — one of the
            // F5-open hitches (v1.29). Only needed right after a fresh BuildPage; a plain
            // SetActive(true) re-open lays out through Unity's normal end-of-frame pass.
            if(builtThisOpen)
                try{UIFactory.tCanvas?.GetMethod("ForceUpdateCanvases",BindingFlags.Public|BindingFlags.Static)?.Invoke(null,null);}catch{}
            isOpen=true;dirty=true;RefreshData();ApiClient.ResetQueueCountTimer();Plugin.Log.LogInfo($"[NATIVE] Opened competitive page (inGame={inGameMode})");
        }

        public static void Close(){if(pageGO!=null)pageGO.SetActive(false);isOpen=false;try{TrailPreview.Stop();}catch{}try{PlayerEffectCosmetic.StopPreview();}catch{}SetClickBlocker(false);Plugin.Log.LogInfo("[NATIVE] Closed competitive page");}

        // Bug batch item 6: while a player-effect preview runs, the aura is a WORLD
        // particle system, and a ScreenSpaceOverlay canvas composites above ALL
        // world renderers regardless of sortingOrder — the old "sortingOrder
        // 30500" attempt could never draw it in front. Instead fade the page to
        // near-transparent while previewing: the aura (following the cursor) is
        // fully visible and the buttons stay clickable through the CanvasGroup.
        private static object menuFadeCG;
        public static void SetMenuFade(bool on)
        {
            try
            {
                if (pageGO == null) return;
                if (menuFadeCG == null)
                {
                    var tCG = UIFactory.tCanvasGroup;
                    if (tCG == null) return;
                    menuFadeCG = pageGO.GetComponent(tCG) ?? pageGO.AddComponent(tCG);
                }
                var aProp = menuFadeCG.GetType().GetProperty("alpha", BindingFlags.Public | BindingFlags.Instance);
                aProp?.SetValue(menuFadeCG, on ? 0.16f : 1f);
            }
            catch { }
        }

        // Full-screen uGUI raycast blocker for IMGUI modals (bug report form, log/admin
        // viewers). The IMGUI backdrop those draw blocks NOTHING in uGUI — they're separate
        // input paths — so clicks on the form also hit the F5 buttons behind it (lopi #14).
        // A transparent raycastTarget Image as the TOP child of the overlay canvas intercepts
        // every uGUI raycast while a modal is up; the IMGUI form still works (separate path).
        private static GameObject clickBlocker;
        public static void SetClickBlocker(bool on)
        {
            try
            {
                if (clickBlocker == null)
                {
                    if (overlayCanvasGO == null) return;
                    clickBlocker = new GameObject("CR_ClickBlocker");
                    clickBlocker.transform.SetParent(overlayCanvasGO.transform, false);
                    var rt = clickBlocker.AddComponent<RectTransform>();
                    rt.anchorMin = Vector2.zero; rt.anchorMax = Vector2.one; rt.offsetMin = Vector2.zero; rt.offsetMax = Vector2.zero;
                    var img = clickBlocker.AddComponent(UIFactory.tImage);
                    UIFactory.tImage.GetProperty("color", BindingFlags.Public | BindingFlags.Instance)?.SetValue(img, new Color(0, 0, 0, 0.001f));
                    UIFactory.tImage.GetProperty("raycastTarget", BindingFlags.Public | BindingFlags.Instance)?.SetValue(img, true);
                    clickBlocker.SetActive(false);
                }
                if (on) clickBlocker.transform.SetAsLastSibling();
                if (clickBlocker.activeSelf != on) clickBlocker.SetActive(on);
            }
            catch { }
        }

        private static float dataCheckTimer;private static int lastMatchCount=-1,lastLBCount=-1,lastCardCount=-1;
        public static void Tick()
        {
            if(!isOpen||!pageBuilt)return;if(pageGO==null){isOpen=false;pageBuilt=false;return;}
            if(Input.GetKeyDown(KeyCode.Escape)){Close();return;}
            dataCheckTimer+=Time.deltaTime;if(dataCheckTimer>=0.3f){dataCheckTimer=0f;int mc=ApiClient.CachedMatchHistory?.Count??0,lc=ApiClient.CachedLeaderboard?.entries?.Length??0,cc=ApiClient.CachedCardStats?.Count??0;if(mc!=lastMatchCount||lc!=lastLBCount||cc!=lastCardCount){lastMatchCount=mc;lastLBCount=lc;lastCardCount=cc;dirty=true;}}
            if(dirty){dirty=false;RefreshCurrentTab();}
            MaybeRefreshTournament();
            MaybeRefreshTeamTab();
            MaybeRefreshLeaderboardTab();
            MaybeRefreshOvtTab();
            MaybeRefreshHomeTab();
            TickAnimatedThumbnails();
        }

        // Bug #74: animated cosmetics were static in the shop. Registry of shop-row
        // Image components showing an animated sku; the sprite property is re-set at
        // the item's own fps from Tick. Entries are (re)assigned per ApplyShopRow
        // fill (rows are pooled) and cleared when the row shows a static item.
        private static readonly Dictionary<object, (Sprite[] frames, float fps)> _animThumbs =
            new Dictionary<object, (Sprite[], float)>();
        private static PropertyInfo _pImgSprite;
        // Last frame index actually assigned per Image — at 3.6-6 fps the frame
        // only changes every 10+ rendered frames, so skipping same-index sets
        // avoids ~94% of the per-frame reflection SetValue + Canvas dirtying
        // (the Home pool doubled to 12 rows in item 4, making this worth it).
        private static readonly Dictionary<object, int> _animThumbLastIdx = new Dictionary<object, int>();
        public static void TrackAnimatedThumb(object img, Sprite[] frames, float fps)
        {
            if (img == null) return;
            if (frames == null || frames.Length < 2 || fps <= 0f) { _animThumbs.Remove(img); _animThumbLastIdx.Remove(img); return; }
            _animThumbs[img] = (frames, fps);
            _animThumbLastIdx.Remove(img);  // force a fresh set on the next tick
        }
        private static void TickAnimatedThumbnails()
        {
            // Shop tab (4) AND Home tab (newest-cosmetics art, v1.33). Both use
            // distinct Image objects, so _animThumbs entries never collide.
            if (_animThumbs.Count == 0 || (currentTab != 4 && currentTab != TAB_HOME)) return;
            try
            {
                if (_pImgSprite == null && UIFactory.tImage != null)
                    _pImgSprite = UIFactory.tImage.GetProperty("sprite", BindingFlags.Public | BindingFlags.Instance);
                if (_pImgSprite == null) return;
                // v1.32 item 8: static-cosmetics mode pins shop thumbnails to frame 1.
                bool _static = Plugin.AnimatedCosmetics != null && !Plugin.AnimatedCosmetics.Value;
                foreach (var kv in _animThumbs)
                {
                    var (frames, fps) = kv.Value;
                    int idx = _static ? 0 : (int)(Time.unscaledTime * fps) % frames.Length;
                    int last;
                    if (_animThumbLastIdx.TryGetValue(kv.Key, out last) && last == idx) continue;
                    _pImgSprite.SetValue(kv.Key, frames[idx]);
                    _animThumbLastIdx[kv.Key] = idx;
                }
            }
            catch { }
        }

        // The Leaderboard tab was session-stale: SwitchTab used to fetch only when
        // the cache was NULL, and RefreshData only refetches it if the menu happens
        // to be OPENED on tab 1 — so ratings from series played mid-session never
        // showed up without a manual Refresh ("leaderboard tab hasn't been updating").
        // Same shape as MaybeRefreshTeamTab (learning #62): throttled ticker while
        // the tab is open. 30s — a 500-row board doesn't need the 2s queue cadence.
        private static float lbTabRefreshAt;
        private static void MaybeRefreshLeaderboardTab()
        {
            if (currentTab != 1) return;
            TickPodiumSparkle();
            if (Time.unscaledTime < lbTabRefreshAt) return;
            lbTabRefreshAt = Time.unscaledTime + 30f;
            ApiClient.FetchLeaderboard();
            ApiClient.FetchRecentSeries();
        }

        // ── Podium title sparkle (v1.32 item 4) ────────────────────────────
        // The server resolves sku 'title_podium' to "1st Place"/"2nd Place"/
        // "3rd Place" (gold/silver/bronze). The client adds a per-character
        // glitter; on the 1v1 leaderboard the glitter ANIMATES by rewriting
        // only the (at most 3) podium rows' name text on a slow tick — never
        // a full-board repaint (F5 perf, learning #109). Detection is by exact
        // title text: the server never issues another title with these names.
        internal static bool IsPodiumTitle(string t) =>
            t == "1st Place" || t == "2nd Place" || t == "3rd Place";
        private static uint _podiumTick = 0;
        private static float _podiumTickAt = 0f;
        // Entries: [0]=txtName object, [1]=base name (no title), [2]=title, [3]=color hex
        private static readonly List<object[]> _podiumLbRows = new List<object[]>();
        // Dark SDF outline on podium rows' cells so text stays readable over the
        // gold/silver/bronze tints (Sid: "Stan's elo is hard to read"). Original
        // materials keyed by label; one outline clone per base material.
        private static readonly Dictionary<object, Material> _lbOutlineOrig = new Dictionary<object, Material>();
        private static readonly Dictionary<Material, Material> _lbOutlineCache = new Dictionary<Material, Material>();
        private static void SetLbRowOutline(LBRow row, bool on)
        {
            if (row == null) return;
            NametagGlowRenderer.ApplyOutlineToLabel(row.txtRank,   on, _lbOutlineOrig, _lbOutlineCache);
            NametagGlowRenderer.ApplyOutlineToLabel(row.txtLv,     on, _lbOutlineOrig, _lbOutlineCache);
            NametagGlowRenderer.ApplyOutlineToLabel(row.txtName,   on, _lbOutlineOrig, _lbOutlineCache);
            NametagGlowRenderer.ApplyOutlineToLabel(row.txtRating, on, _lbOutlineOrig, _lbOutlineCache);
            NametagGlowRenderer.ApplyOutlineToLabel(row.txtW,      on, _lbOutlineOrig, _lbOutlineCache);
            NametagGlowRenderer.ApplyOutlineToLabel(row.txtL,      on, _lbOutlineOrig, _lbOutlineCache);
            NametagGlowRenderer.ApplyOutlineToLabel(row.txtWL,     on, _lbOutlineOrig, _lbOutlineCache);
            NametagGlowRenderer.ApplyOutlineToLabel(row.txtGold,   on, _lbOutlineOrig, _lbOutlineCache);
        }
        internal static string PodiumSparkleSpan(string title, string hex, uint tick)
        {
            // Brackets carry the title color too — bare brackets inherit the row's
            // BASE color (green on the local player's row), which read as a bug
            // (Sid feedback, v1.32 round 2).
            var sb = new System.Text.StringBuilder(title.Length * 24 + 40);
            sb.Append("<b><color=").Append(hex).Append(">[</color>");
            for (int i = 0; i < title.Length; i++)
            {
                bool glint = ((i + (int)tick) % 3) == 0;
                sb.Append("<color=").Append(glint ? "#FFFFFF" : hex).Append(">")
                  .Append(title[i]).Append("</color>");
            }
            sb.Append("<color=").Append(hex).Append(">]</color></b>");
            return sb.ToString();
        }
        private static void TickPodiumSparkle()
        {
            if (_podiumLbRows.Count == 0) return;
            if (Time.unscaledTime < _podiumTickAt) return;
            _podiumTickAt = Time.unscaledTime + 0.7f;
            _podiumTick++;
            foreach (var r in _podiumLbRows)
            {
                if (r == null || r.Length < 4 || r[0] == null) continue;
                UIFactory.SetText(r[0],
                    $"{(string)r[1]} {PodiumSparkleSpan((string)r[2], (string)r[3], _podiumTick)}");
            }
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
            // Live 2v2 strip — pull the active team series feed every 5s so
            // the inline panel inside the 2v2 tab stays current without
            // requiring the user to switch to the leaderboard tab.
            ApiClient.FetchActiveTeamSeries();
            // Recent 2v2 Series (paged) — refresh every 10s. Page state lives
            // in teamSeriesPageReq so prev/next buttons can change it.
            if (Time.unscaledTime >= teamSeriesRefreshAt)
            {
                teamSeriesRefreshAt = Time.unscaledTime + 10f;
                ApiClient.FetchAllSeriesPaged(teamSeriesPageReq, 10);
            }
        }

        private static void FindMainMenuGroup(){var all=UnityEngine.Object.FindObjectsOfType<ListMenuButton>();Type tt=null;PropertyInfo tp=null;foreach(var a in AppDomain.CurrentDomain.GetAssemblies()){tt=a.GetType("TMPro.TMP_Text");if(tt!=null)break;}if(tt!=null)tp=tt.GetProperty("text",BindingFlags.Public|BindingFlags.Instance);foreach(var b in all){if(tp==null)break;try{var tc=b.GetComponentInChildren(tt,true);if(tc==null)continue;if((tp.GetValue(tc)as string??"").Trim().ToUpper()=="QUIT"){mainMenuGroup=b.transform.parent.gameObject;Plugin.Log.LogInfo($"[NATIVE] Found main menu group: {mainMenuGroup.name}");return;}}catch{}}Plugin.Log.LogWarning("[NATIVE] Could not find QUIT button");}
        private static Transform FindCanvasAbove(Transform from){Transform c=from;while(c!=null){if(UIFactory.tCanvas!=null&&c.GetComponent(UIFactory.tCanvas)!=null){Plugin.Log.LogInfo($"[NATIVE] Found Canvas: {c.gameObject.name}");return c;}c=c.parent;}return from.parent??from;}
        private static void EnsureOverlayCanvas(){if(overlayCanvasGO!=null)return;overlayCanvasGO=new GameObject("CR_OverlayCanvas");overlayCanvasGO.hideFlags=HideFlags.HideAndDontSave;UnityEngine.Object.DontDestroyOnLoad(overlayCanvasGO);if(UIFactory.tCanvas!=null){var cv=overlayCanvasGO.AddComponent(UIFactory.tCanvas);var bf=BindingFlags.Public|BindingFlags.Instance;UIFactory.tCanvas.GetProperty("renderMode",bf)?.SetValue(cv,Enum.ToObject(UIFactory.tCanvas.GetProperty("renderMode",bf).PropertyType,0));UIFactory.tCanvas.GetProperty("sortingOrder",bf)?.SetValue(cv,30000);}if(UIFactory.tCanvasScaler!=null){var sc=overlayCanvasGO.AddComponent(UIFactory.tCanvasScaler);var bf=BindingFlags.Public|BindingFlags.Instance;var smp=UIFactory.tCanvasScaler.GetProperty("uiScaleMode",bf);if(smp!=null)smp.SetValue(sc,Enum.ToObject(smp.PropertyType,1));UIFactory.tCanvasScaler.GetProperty("referenceResolution",bf)?.SetValue(sc,new Vector2(1920,1080));}if(UIFactory.tGR!=null)overlayCanvasGO.AddComponent(UIFactory.tGR);Plugin.Log.LogInfo("[NATIVE] Created persistent overlay Canvas");}

        private static void BuildPage(Transform canvasParent)
        {
            try{rankedRows.Clear();casualRows.Clear();lbRows.Clear();cardRows.Clear();sessionOppTexts.Clear();ovtLbRows.Clear();
            pageGO=new GameObject("CompetitiveRoundsPage");pageGO.transform.SetParent(canvasParent,false);var rt=pageGO.AddComponent<RectTransform>();rt.anchorMin=Vector2.zero;rt.anchorMax=Vector2.one;rt.offsetMin=Vector2.zero;rt.offsetMax=Vector2.zero;pageGO.SetActive(false);
            var bgGO=UIFactory.CreatePanel("BG",pageGO.transform,C_BG);var bgImg=bgGO.GetComponent(UIFactory.tImage);if(bgImg!=null)UIFactory.tImage.GetProperty("raycastTarget",BindingFlags.Public|BindingFlags.Instance)?.SetValue(bgImg,true);
            var content=new GameObject("Content");content.transform.SetParent(pageGO.transform,false);var crt=content.AddComponent<RectTransform>();crt.anchorMin=Vector2.zero;crt.anchorMax=Vector2.one;crt.offsetMin=new Vector2(30,10);crt.offsetMax=new Vector2(-30,-10);UIFactory.AddVLG(content,spacing:4,padL:8,padR:8,padT:8,padB:8);

            /* Title banner trimmed 42->30px (July 12 round 2, item 1): the sub-tab
             * row costs ~30px of vertical space on grouped tabs, and this is the
             * chrome that pays for it — the Leaderboard/2v2 panels sit back at
             * (or above) their pre-reorg height. */
            var titleRow=new GameObject("TitleRow");titleRow.transform.SetParent(content.transform,false);titleRow.AddComponent<RectTransform>();UIFactory.AddHLG(titleRow,spacing:8,forceExpandH:true);UIFactory.AddLE(titleRow,prefH:30,minH:30,flexH:0);
            UIFactory.CreateText("Title",titleRow.transform,"SID'S COMPETITIVE ROUNDS",24f,C_WHITE,UIFactory.AlignMidCenter,sizeDelta:new Vector2(0,30));
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
            tabPanels=new GameObject[NUM_TABS];tabPanels[0]=BuildMyStatsTab(content.transform);tabPanels[1]=BuildLeaderboardTab(content.transform);tabPanels[2]=BuildCardStatsTab(content.transform);tabPanels[3]=BuildAchievementsTab(content.transform);tabPanels[4]=BuildShopTab(content.transform);tabPanels[5]=BuildSettingsTab(content.transform);tabPanels[6]=BuildAdminTab(content.transform);tabPanels[7]=BuildTournamentsTab(content.transform);tabPanels[8]=BuildTeamTab(content.transform);tabPanels[9]=BuildCompareTab(content.transform);tabPanels[10]=BuildArtistTab(content.transform);tabPanels[11]=BuildOneVTwoTab(content.transform,11);tabPanels[12]=BuildFfaTab(content.transform,12);tabPanels[13]=BuildHomeTab(content.transform);
            // (The [ID] button's position is set in CreateHistoryRow itself, so
            // it cannot desync from tab-build ordering.)

            var bottom=new GameObject("Bottom");bottom.transform.SetParent(content.transform,false);bottom.AddComponent<RectTransform>();UIFactory.AddHLG(bottom,spacing:8,forceExpandH:true);UIFactory.AddLE(bottom,prefH:26,minH:26,flexH:0);
            UIFactory.CreateText("Ver",bottom.transform,$"<b>v{Plugin.ModVersion}</b>",13f,C_DIM,UIFactory.AlignMidLeft,sizeDelta:new Vector2(90,22));
            txtVersionStatus=UIFactory.CreateText("VerStatus",bottom.transform,"",12f,C_DIM,UIFactory.AlignMidLeft,sizeDelta:new Vector2(130,22));
            updateBtn=UIFactory.CreateButton("UpdateBtn",bottom.transform,"Update",14f,C_WHITE,new Color(0.6f,0.4f,0.1f,0.9f),()=>{ApiClient.StartAutoUpdate();},sizeDelta:new Vector2(75,26));updateBtn.SetActive(false);
            UIFactory.CreateButton("Discord",bottom.transform,"Discord",14f,Color.white,new Color(0.345f,0.396f,0.949f,0.9f),()=>{Application.OpenURL("https://discord.gg/comp-rounds");},sizeDelta:new Vector2(80,26));
            UIFactory.CreateButton("GitHub",bottom.transform,"GitHub",14f,Color.white,new Color(0.2f,0.2f,0.2f,0.9f),()=>{Application.OpenURL("https://github.com/SidNDeed/SidsCompetitiveRounds");},sizeDelta:new Vector2(75,26));
            var bSp=new GameObject("S");bSp.transform.SetParent(bottom.transform,false);bSp.AddComponent<RectTransform>();UIFactory.AddLE(bSp,flexW:1);
            UIFactory.CreateButton("RefreshBtn",bottom.transform,"Refresh",15f,C_WHITE,C_BTN,()=>{if(Time.unscaledTime>=_nextManualRefreshAt){_nextManualRefreshAt=Time.unscaledTime+2f;RefreshData();dirty=true;}else{CompetitiveUI.ShowNotification("Refreshing too fast - give it a sec",Color.yellow,1.5f);}},sizeDelta:new Vector2(85,26));
            SwitchTab(TAB_HOME);pageBuilt=true;Plugin.Log.LogInfo("[NATIVE] Competitive page built");
            }catch(Exception ex){Plugin.Log.LogError($"[NATIVE] BuildPage failed: {ex}");pageBuilt=false;}
        }

        // ── July 21 item 8: LFP Discord ping ──────────────────────────────
        public static bool LfpPromptOpen { get; private set; }
        public static string LfpMessageText = "";
        public static int LfpExpiryIdx = 2;   // default 1h
        public static readonly int[] LfpExpiryMinutes = { 15, 30, 60, 180 };
        public static readonly string[] LfpExpiryLabels = { "15m", "30m", "1h", "3h" };
        private static float lfpCooldownUntil = -1f;   // Time.realtimeSinceStartup
        private static object _lfpStatsRef;

        private static void OnLfpButton()
        {
            var stats = ApiClient.CachedPlayerStats;
            if (stats == null) { CompetitiveUI.ShowNotification("Stats still loading - try again in a moment.", C_DIM); return; }
            if (string.IsNullOrEmpty(stats.discord_id))
            { CompetitiveUI.ShowNotification("Link your Discord account first (Home tab) to use RLFP pings.", new Color(1f, 0.8f, 0.3f), 7f); return; }
            if (Plugin.RankedEnabled == null || !Plugin.RankedEnabled.Value)
            { CompetitiveUI.ShowNotification("Enable Ranked first - the RLFP ping is for ranked matches.", new Color(1f, 0.8f, 0.3f), 6f); return; }
            float remain = lfpCooldownUntil - Time.realtimeSinceStartup;
            if (remain > 0f)
            { CompetitiveUI.ShowNotification($"RLFP ping available in {(int)(remain / 60)}m {(int)(remain % 60)}s (1 per hour).", C_DIM, 6f); return; }
            LfpMessageText = "";
            LfpExpiryIdx = 2;
            LfpPromptOpen = true;
        }

        public static void SubmitLfpPing()
        {
            LfpPromptOpen = false;
            int mins = LfpExpiryMinutes[Mathf.Clamp(LfpExpiryIdx, 0, LfpExpiryMinutes.Length - 1)];
            ApiClient.SendLfpPing(MatchTracker.LocalSteamId, LfpMessageText ?? "", mins);
        }

        public static void CancelLfpPing() { LfpPromptOpen = false; }

        public static void LfpArmCooldown(int seconds)
        {
            if (seconds > 0) { lfpCooldownUntil = Time.realtimeSinceStartup + seconds; dirty = true; }
        }

        private static void BuildRankedRow(Transform parent)
        {
            var row=new GameObject("RankedRow");row.transform.SetParent(parent,false);row.AddComponent<RectTransform>();UIFactory.AddHLG(row,spacing:10,padL:4,padR:4,forceExpandH:true);UIFactory.AddLE(row,prefH:26,minH:26,flexH:0);
            var pn=UIFactory.CreateText("PName",row.transform,ApiClient.CachedPlayerStats?.display_name??MatchTracker.LocalDisplayName??"",20f,C_SUB,UIFactory.AlignMidLeft,sizeDelta:new Vector2(110,28));UIFactory.SetBold(pn,true);txtTopLeftName=pn;
            txtRankedStatus=UIFactory.CreateText("RS",row.transform,"RANKED: OFF",18f,Color.gray,UIFactory.AlignMidLeft,sizeDelta:new Vector2(140,28));UIFactory.SetBold(txtRankedStatus,true);
            qSearchBtn=UIFactory.CreateButton("Search",row.transform,"Search Ranked",15f,C_WHITE,C_BTN,()=>{var id=MatchTracker.LocalSteamId;if(!string.IsNullOrEmpty(id)&&id!="unknown")ApiClient.JoinQueue(id,MatchTracker.LocalDisplayName,null,false);},sizeDelta:new Vector2(130,26));
            qCancelBtn=UIFactory.CreateButton("Cancel",row.transform,"Cancel",15f,C_WHITE,C_BTN,()=>ApiClient.LeaveQueue(MatchTracker.LocalSteamId),sizeDelta:new Vector2(70,26));
            /* July 21 item 8: pings the Discord "Ranked Looking For Player" role so
             * players who aren't in-game right now get poked. Gated: Discord linked +
             * ranked enabled + 1/hour (server-enforced; client mirrors for UX). */
            lfpBtn=UIFactory.CreateButton("LfpPing",row.transform,"RLFP Ping",15f,C_WHITE,C_BTN,()=>OnLfpButton(),sizeDelta:new Vector2(95,26));
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

        // (item 7 reorg) Panel indices are HISTORICAL — every per-tab gate in the
        // file (currentTab==8 tickers, SwitchTab fetch chain, RefreshCurrentTab
        // switch) keys on them, so they never move. 11=1v2, 12=FFA are new WIP
        // placeholders under the Multiplayer group. 13=Home (v1.33 splash/landing).
        private static readonly string[] TAB_NAMES={"My Stats","Leaderboard","Card Stats","Achievements","Shop","Settings","Admin","Tournaments","2v2","Compare","Artist","1v2","FFA","Home"};
        private const int NUM_TABS=14;
        private const int TAB_HOME=13;
        // Top bar order per Sid's spec (July 12 round 2): Multiplayer right after
        // Tournaments; Settings last; Admin gated. Sub-tabs: Compare under
        // Leaderboard, Artist under Shop, 2v2/1v2/FFA under Multiplayer. First
        // member of a group = its landing tab. v1.33: Home leads the bar and is
        // the landing tab when the menu is first built; Card Stats + Achievements
        // moved under My Stats as sub-tabs (Sid's item 4).
        private static readonly string[] GROUP_LABELS={"Home","My Stats","Leaderboard","Tournaments","Multiplayer","Shop","Admin","Settings"};
        private static readonly int[][] GROUP_MEMBERS={new[]{13},new[]{0,2,3},new[]{1,9},new[]{7},new[]{8,11,12},new[]{4,10},new[]{6},new[]{5}};
        private const int GROUP_ADMIN=6;   // GROUP_LABELS index of the admin-gated slot
        private static int GroupOf(int tabIdx){for(int g=0;g<GROUP_MEMBERS.Length;g++)for(int m=0;m<GROUP_MEMBERS[g].Length;m++)if(GROUP_MEMBERS[g][m]==tabIdx)return g;return 0;}
        private static bool TabVisible(int i){return i!=10||ApiClient.IsArtist;}
        private static void BuildTabBar(Transform parent)
        {
            var bar=new GameObject("TabBar");bar.transform.SetParent(parent,false);bar.AddComponent<RectTransform>();UIFactory.AddHLG(bar,spacing:4);UIFactory.AddLE(bar,prefH:28,minH:28,flexH:0);
            groupButtons=new GameObject[GROUP_LABELS.Length];groupTexts=new object[GROUP_LABELS.Length];
            for(int g=0;g<GROUP_LABELS.Length;g++)
            {
                int gi=g;
                var btn=UIFactory.CreateButton($"TabG{g}",bar.transform,GROUP_LABELS[g],13f,C_LABEL,C_TAB,()=>SwitchTab(GROUP_MEMBERS[gi][0]),sizeDelta:new Vector2(0,26));
                if(UIFactory.tLE!=null){var el=btn.GetComponent(UIFactory.tLE);if(el!=null)UnityEngine.Object.Destroy(el as UnityEngine.Object);}
                UIFactory.AddLE(btn,prefH:26,minH:26,flexW:1,flexH:0);
                groupButtons[g]=btn;groupTexts[g]=UIFactory.GetButtonText(btn);
            }
            // Sub-tab row: pre-create a button for every member of every multi-member
            // group; UpdateTabBarVisual shows only the active group's set. Flexible
            // spacers on both ends keep the visible set CENTERED whatever the group
            // (July 12 round 2, items 1-3/8 — they were left-packed and tiny).
            subTabBar=new GameObject("SubTabBar");subTabBar.transform.SetParent(parent,false);subTabBar.AddComponent<RectTransform>();UIFactory.AddHLG(subTabBar,spacing:8,forceExpandH:false);/* flexW:1 so the bar stretches to its ANCHOR's width and the internal spacers center the buttons (round 5 item 3). */UIFactory.AddLE(subTabBar,prefH:28,minH:28,flexH:0,flexW:1);
            var subSpL=new GameObject("S");subSpL.transform.SetParent(subTabBar.transform,false);subSpL.AddComponent<RectTransform>();UIFactory.AddLE(subSpL,flexW:1);
            subButtons=new GameObject[NUM_TABS];subTexts=new object[NUM_TABS];
            for(int g=0;g<GROUP_MEMBERS.Length;g++)
            {
                if(GROUP_MEMBERS[g].Length<2)continue;
                for(int m=0;m<GROUP_MEMBERS[g].Length;m++)
                {
                    int idx=GROUP_MEMBERS[g][m];
                    /* Round 4: 360px each — a two-button group spans ~730px centered,
                     * matching the leaderboard table's width beneath it. */
                    var sb=UIFactory.CreateButton($"SubTab{idx}",subTabBar.transform,TAB_NAMES[idx],14f,C_LABEL,C_TAB,()=>SwitchTab(idx),sizeDelta:new Vector2(360,26));
                    subButtons[idx]=sb;subTexts[idx]=UIFactory.GetButtonText(sb);
                    sb.SetActive(false);
                }
            }
            var subSpR=new GameObject("S");subSpR.transform.SetParent(subTabBar.transform,false);subSpR.AddComponent<RectTransform>();UIFactory.AddLE(subSpR,flexW:1);
            /* Admin/Artist visibility flips on as soon as the async status checks
             * resolve true (poll-driven update from RefreshCurrentTab). */
            UpdateTabBarVisual();
        }
        // Repaints group highlight + sub-row contents from currentTab. Called on
        // every SwitchTab AND from RefreshCurrentTab so late IsAdmin/IsArtist
        // resolutions flip the gated buttons on without a rebuild.
        private static void UpdateTabBarVisual()
        {
            if(groupButtons==null)return;
            int ag=GroupOf(currentTab);
            for(int g=0;g<GROUP_LABELS.Length;g++)
            {
                if(groupButtons[g]==null)continue;
                if(g==GROUP_ADMIN)groupButtons[g].SetActive(ApiClient.IsAdmin);
                UIFactory.SetImageColor(groupButtons[g],g==ag?C_TABACT:C_TAB);
                if(groupTexts[g]!=null){UIFactory.SetColor(groupTexts[g],g==ag?C_WHITE:C_LABEL);UIFactory.SetBold(groupTexts[g],g==ag);}
            }
            var members=GROUP_MEMBERS[ag];
            int visCount=0;for(int m=0;m<members.Length;m++)if(TabVisible(members[m]))visCount++;
            bool showSub=visCount>1;
            // Round 5 item 3: park the bar inside the active tab's anchor. Panels
            // without an anchor (single-member groups) never show the bar.
            GameObject anchor=(subTabAnchors!=null&&currentTab>=0&&currentTab<subTabAnchors.Length)?subTabAnchors[currentTab]:null;
            if(subTabAnchors!=null)
                for(int i=0;i<subTabAnchors.Length;i++)
                    if(subTabAnchors[i]!=null&&subTabAnchors[i]!=anchor)subTabAnchors[i].SetActive(false);
            bool showBar=showSub&&anchor!=null;
            if(anchor!=null)anchor.SetActive(showBar);
            if(subTabBar!=null)
            {
                if(showBar&&subTabBar.transform.parent!=anchor.transform)
                    subTabBar.transform.SetParent(anchor.transform,false);
                subTabBar.SetActive(showBar);
            }
            if(subButtons!=null)
                for(int i=0;i<subButtons.Length;i++)
                {
                    if(subButtons[i]==null)continue;
                    bool inGroup=false;for(int m=0;m<members.Length;m++)if(members[m]==i){inGroup=true;break;}
                    bool vis=showSub&&inGroup&&TabVisible(i);
                    subButtons[i].SetActive(vis);
                    if(vis)
                    {
                        UIFactory.SetImageColor(subButtons[i],i==currentTab?C_TABACT:C_TAB);
                        if(subTexts[i]!=null){UIFactory.SetColor(subTexts[i],i==currentTab?C_WHITE:C_LABEL);UIFactory.SetBold(subTexts[i],i==currentTab);}
                    }
                }
        }
        // ── FFA tab (design preview; the mode itself is NOT playable yet) ──
        // The locked design (docs/design-1v2-ffa.md, Sid's July 13 decisions)
        // rendered as a preview so testers know what's coming and why it's
        // gated. No queue controls until the mode ships — a joinable queue
        // that can't produce a playable game would be worse than none.
        private static GameObject BuildFfaTab(Transform parent,int tabIdx)
        {
            // Same outer-wrapper pattern as 2v2/1v2: the sub-tab anchor lives
            // in an UNPADDED outer so the Multiplayer sub-tab bar sits at the
            // identical top position on all three tabs.
            var outer=new GameObject("FfaOuter");outer.transform.SetParent(parent,false);outer.AddComponent<RectTransform>();
            UIFactory.AddVLG(outer,spacing:0);UIFactory.AddLE(outer,flexH:1);
            MakeSubTabAnchor(tabIdx,outer.transform,true);
            var panel=new GameObject("Ffa");panel.transform.SetParent(outer.transform,false);panel.AddComponent<RectTransform>();
            UIFactory.AddVLG(panel,spacing:8,padL:20,padR:20,padT:8,padB:14);UIFactory.AddLE(panel,flexH:1);
            UIFactory.CreateText("FfaH",panel.transform,"FFA — Free For All",24f,C_GOLD,sizeDelta:new Vector2(700,32));
            UIFactory.CreateText("FfaStatus",panel.transform,"<color=#FF6666><b>IN DEVELOPMENT — not playable yet.</b></color> <color=#888>This page previews the locked design. The queue will open here once the mode ships.</color>",14f,C_DIM,sizeDelta:new Vector2(820,22));

            var how=UIFactory.CreatePanel("FfaHow",panel.transform,C_PANEL);
            UIFactory.AddVLG(how,spacing:3,padL:12,padR:12,padT:8,padB:8);UIFactory.AddLE(how,flexH:0);
            UIFactory.CreateText("FfaHowH",how.transform,"How it will work",18f,C_SUB,sizeDelta:new Vector2(400,26));
            string[] ffaRules={
                "<color=#FFD94D>4 players</color>, everyone for themselves — each player is their own team. A lobby of 3 can start if a 4th doesn't show.",
                "A round ends when <color=#FFD94D>one player is left standing</color>; the game goes to the first player with <color=#FFD94D>5 round wins</color>.",
                "<color=#FFD94D>Single games only</color> — no BO3 series. Queue again for another game.",
                "After each round the <color=#FFD94D>three non-winners pick a card</color>; the round winner doesn't.",
                "<color=#FFD94D>Rolling 5-card bar</color> (the signature rule): you can only hold 5 cards — picking a 6th replaces your OLDEST card, so builds rotate instead of stacking.",
                "<color=#FFD94D>Unranked at launch</color> — every game is recorded from day one, so ratings can be applied retroactively when ranked FFA lands.",
            };
            foreach(var r in ffaRules)
            {
                var t=UIFactory.CreateText("FfaR",how.transform,"-  "+r,14f,C_LABEL,UIFactory.AlignTopLeft,sizeDelta:new Vector2(820,20));
                UIFactory.SetWordWrap(t,true);UIFactory.SetTextAutoHeight(t);
            }

            var why=UIFactory.CreatePanel("FfaWhy",panel.transform,C_PANEL);
            UIFactory.AddVLG(why,spacing:3,padL:12,padR:12,padT:8,padB:8);UIFactory.AddLE(why,flexH:0);
            UIFactory.CreateText("FfaWhyH",why.transform,"Why it isn't out yet",18f,C_SUB,sizeDelta:new Vector2(400,26));
            var whyT=UIFactory.CreateText("FfaWhyB",why.transform,"The rolling card bar removes and re-applies cards mid-match — brand-new netcode that has to survive ROUNDS' messiest cards. It gets a dedicated Sandbox test matrix (Empower, Shield Charge, Phoenix, Abyssal, Brainwash) before any public lobby sees it. 1v2 shipped first because it reuses proven 2v2 machinery; FFA gets its own focused pass next.",14f,C_LABEL,UIFactory.AlignTopLeft,sizeDelta:new Vector2(820,40));
            UIFactory.SetWordWrap(whyT,true);UIFactory.SetTextAutoHeight(whyT);

            var ffaSp=new GameObject("S");ffaSp.transform.SetParent(panel.transform,false);ffaSp.AddComponent<RectTransform>();UIFactory.AddLE(ffaSp,flexH:1);
            return outer;
        }

        // ── 1v2 tab (solo vs duo; UNSCORED beta) ──────────────────────────
        private static object txtOvtStatus, txtOvtLbHeader, txtOvtLobbyHeader, txtOvtLobbyBody; private static GameObject ovtJoinBtn, ovtLeaveBtn, ovtSideBtn, ovtExtraBtn, ovtLbContainer;
        private static int ovtPreferredSide = 0;   // 0 any, 1 solo, 2 duo
        private static bool ovtSoloExtraPick = false;
        private static readonly List<object> ovtLbRows = new List<object>();
        private static GameObject BuildOneVTwoTab(Transform parent,int tabIdx)
        {
            // Outer wrapper (2v2 pattern): the sub-tab anchor lives in an
            // UNPADDED outer so the Multiplayer sub-tab bar renders at the
            // same top position on every tab in the group. Putting the anchor
            // inside the padded content panel made the bar sit padT lower
            // here than on 2v2 — the "sub-tabs drift down as you click
            // through 2v2/1v2/FFA" report.
            var outer=new GameObject("OneVTwoOuter");outer.transform.SetParent(parent,false);outer.AddComponent<RectTransform>();
            UIFactory.AddVLG(outer,spacing:0);UIFactory.AddLE(outer,flexH:1);
            MakeSubTabAnchor(tabIdx,outer.transform,true);
            var panel=new GameObject("OneVTwo");panel.transform.SetParent(outer.transform,false);panel.AddComponent<RectTransform>();
            UIFactory.AddVLG(panel,spacing:8,padL:20,padT:8,padB:14);UIFactory.AddLE(panel,flexH:1);
            UIFactory.CreateText("O1H",panel.transform,"1v2 — Solo vs Duo",24f,C_GOLD,sizeDelta:new Vector2(700,32));
            UIFactory.CreateText("O1Beta",panel.transform,"<color=#FFCC44>UNRANKED BETA</color> — single games, no series rating yet. Stats are tracked and will count once ranked launches.",14f,C_DIM,sizeDelta:new Vector2(760,22));

            // Queue controls row.
            var ctl=new GameObject("O1Ctl");ctl.transform.SetParent(panel.transform,false);ctl.AddComponent<RectTransform>();
            UIFactory.AddHLG(ctl,spacing:8);UIFactory.AddLE(ctl,prefH:34,flexH:0);
            ovtSideBtn=UIFactory.CreateButton("O1Side",ctl.transform,"Side: Any",13f,C_WHITE,C_BTN,()=>{ovtPreferredSide=(ovtPreferredSide+1)%3;dirty=true;},sizeDelta:new Vector2(120,28));
            ovtExtraBtn=UIFactory.CreateButton("O1Extra",ctl.transform,"Solo Extra Initial Pick: OFF",13f,C_WHITE,C_BTN,()=>{ovtSoloExtraPick=!ovtSoloExtraPick;dirty=true;},sizeDelta:new Vector2(235,28));
            ovtJoinBtn=UIFactory.CreateButton("O1Join",ctl.transform,"Join 1v2 Lobby",14f,C_WHITE,new Color(0.25f,0.45f,0.18f,0.9f),()=>{ApiClient.OvtJoinQueue(ovtPreferredSide,ovtSoloExtraPick);dirty=true;},sizeDelta:new Vector2(150,28));
            ovtLeaveBtn=UIFactory.CreateButton("O1Leave",ctl.transform,"Leave",14f,C_WHITE,new Color(0.5f,0.2f,0.2f,0.9f),()=>{ApiClient.OvtLeaveQueue();dirty=true;},sizeDelta:new Vector2(90,28));
            // How the toggle actually resolves (server ORs it across the
            // lobby) + honest status: recorded but not yet applied in-game.
            var ovtNote=UIFactory.CreateText("O1Note",panel.transform,"<color=#888>Solo Extra Initial Pick: the solo gets one extra card in the game's FIRST draw only. It's ON for the match if ANY of the three lobby members turned it on.  <color=#7FDF7F>Active in-game</color> <color=#888>— the solo's first pick screen deals twice.</color>",12f,C_DIM,sizeDelta:new Vector2(760,34));
            UIFactory.SetWordWrap(ovtNote,true);
            txtOvtStatus=UIFactory.CreateText("O1St",panel.transform,"Not in queue.",15f,C_LABEL,sizeDelta:new Vector2(760,24));

            // In-lobby panel (2v2 "In Queue" parity): who's queueing, their
            // 1v1/2v2 elo, side preference, wait time, status.
            var lobbyPanel=UIFactory.CreatePanel("O1QL",panel.transform,C_PANEL);
            UIFactory.AddVLG(lobbyPanel,spacing:2,padL:10,padR:10,padT:6,padB:6);
            UIFactory.AddLE(lobbyPanel,flexH:0);
            txtOvtLobbyHeader=UIFactory.CreateText("O1QLH",lobbyPanel.transform,"<b>1v2 Lobby</b>",16f,C_SUB,UIFactory.AlignMidLeft,sizeDelta:new Vector2(740,22));
            txtOvtLobbyBody=UIFactory.CreateText("O1QLB",lobbyPanel.transform,"<color=#888>Loading…</color>",14f,C_LABEL,UIFactory.AlignTopLeft,sizeDelta:new Vector2(740,22));
            var qlbComp=txtOvtLobbyBody as Component;
            if(qlbComp!=null)UIFactory.AddLE(qlbComp.gameObject,prefH:22,minH:22,flexH:0);
            UIFactory.SetWordWrap(txtOvtLobbyBody,true);

            // Leaderboard.
            UIFactory.CreateText("O1LbH",panel.transform,"1v2 Leaderboard (by games played)",17f,C_SUB,sizeDelta:new Vector2(700,26));
            var sv=UIFactory.CreateScrollView("O1LbSV",panel.transform,spacing:1);UIFactory.AddLE(sv.scrollGO,flexH:1);
            ovtLbContainer=sv.content;
            txtOvtLbHeader=UIFactory.CreateText("O1LbHdr",ovtLbContainer.transform,"Loading...",14f,C_DIM,sizeDelta:new Vector2(760,20));
            return outer;
        }

        private static float ovtTabRefreshAt;
        private static void MaybeRefreshOvtTab()
        {
            if(currentTab!=11)return;
            ApiClient.UpdateOvtQueuePoll(false);   // safe no-op when not polling
            ApiClient.UpdateOvtQueueList(false);   // lobby panel snapshot (2s throttle)
            if(Time.unscaledTime<ovtTabRefreshAt)return;
            ovtTabRefreshAt=Time.unscaledTime+3f;
            ApiClient.FetchOvtLeaderboard();
        }

        private static void RefreshOneVTwoTab()
        {
            if(ovtSideBtn!=null)UIFactory.SetText(UIFactory.GetButtonText(ovtSideBtn),ovtPreferredSide==1?"Side: Solo":ovtPreferredSide==2?"Side: Duo":"Side: Any");
            if(ovtExtraBtn!=null)UIFactory.SetText(UIFactory.GetButtonText(ovtExtraBtn),ovtSoloExtraPick?"Solo Extra Initial Pick: ON":"Solo Extra Initial Pick: OFF");
            bool polling=ApiClient.IsOvtQueuePolling;
            // Locked = a lock landed (pending slot / active series) even though
            // polling stopped. In that state Join must stay HIDDEN (re-joining
            // mid-lock is what used to let one click cancel a live series) and
            // Leave must stay VISIBLE — it is the only escape from a husk lock
            // (leave dissolves it server-side). Inside an actual ovt room both
            // are hidden: queue actions from within a running match are never
            // legitimate.
            bool ovtLocked=Plugin.PendingOvtSlot>=0||!string.IsNullOrEmpty(ApiClient.ActiveOvt1v2SeriesId);
            bool inOvtRoom=false;
            try{inOvtRoom=PhotonNetwork.InRoom&&(PhotonNetwork.CurrentRoom?.Name??"").StartsWith("ovt_");}catch{}
            if(ovtJoinBtn!=null)ovtJoinBtn.SetActive(!polling&&!ovtLocked&&!inOvtRoom);
            if(ovtLeaveBtn!=null)ovtLeaveBtn.SetActive((polling||ovtLocked)&&!inOvtRoom);
            if(txtOvtStatus!=null)
            {
                string st=ApiClient.OvtQueueStatus;
                string msg;
                if(inOvtRoom)msg="<color=#66DD66>In a 1v2 match.</color>";
                else if(st=="searching")msg=$"<color=#FFCC44>Searching…</color> {ApiClient.OvtQueueCount} in lobby <color=#888>(locks at 3)</color>";
                else if(st=="ready_join")
                {
                    // Locked lineup: who ended up solo vs duo.
                    string solo=Trunc(ApiClient.OvtLockedSoloName??"?",14);
                    var duo=ApiClient.OvtLockedDuo;
                    string duoNames=(duo!=null&&duo.Count>=2)?$"{Trunc(duo[0].display_name,14)} + {Trunc(duo[1].display_name,14)}":"duo";
                    msg=$"<color=#66DD66>Match found! Joining…</color>  <color=#FFB347>{solo}</color> <color=#888>vs</color> <color=#88AAFF>{duoNames}</color>"
                        +(ApiClient.OvtSoloExtraPick?"  <color=#888>(solo extra pick)</color>":"");
                }
                else if(ovtLocked)msg="<color=#FFB347>1v2 lobby pending</color> — Leave to dissolve it if nothing happens.";
                else msg="Not in queue.";
                UIFactory.SetText(txtOvtStatus,msg);
            }
            RenderOvtLobbySection();
            // Leaderboard rows (pooled text lines).
            var lb=ApiClient.CachedOvtLeaderboard;
            if(ovtLbContainer!=null&&lb!=null)
            {
                while(ovtLbRows.Count<lb.Count)
                {
                    var t=UIFactory.CreateText($"O1LbR{ovtLbRows.Count}",ovtLbContainer.transform,"",14f,C_WHITE,UIFactory.AlignMidLeft,sizeDelta:new Vector2(760,20));
                    ovtLbRows.Add(t);
                }
                for(int i=0;i<ovtLbRows.Count;i++)
                {
                    var comp=ovtLbRows[i] as Component;if(comp==null)continue;
                    if(i<lb.Count){var e=lb[i];comp.gameObject.SetActive(true);string _orc=e.rank==1?"#FFD700":e.rank==2?"#C0C0C0":e.rank==3?"#CD7F32":"#FFD94D";/* July 22 item 3: W/L split by role, colored per the tab's solo=orange / duo=blue convention. Falls back to the old totals if the server hasn't sent the split yet. */string _roleSplit=(e.solo_wins+e.solo_losses+e.duo_wins+e.duo_losses)>0?$"<color=#FFB347>solo {e.solo_wins}W-{e.solo_losses}L</color> <color=#88AAFF>duo {e.duo_wins}W-{e.duo_losses}L</color>":$"<color=#888>(solo {e.solo_games} / duo {e.duo_games})</color>";UIFactory.SetText(ovtLbRows[i],$"<color={_orc}>#{e.rank}</color>  <b>{e.display_name}</b>  {e.games_played}g  <color=#66DD66>{e.win_rate:F0}%</color>  {_roleSplit}");}
                    else comp.gameObject.SetActive(false);
                }
                if(txtOvtLbHeader!=null)UIFactory.SetText(txtOvtLbHeader,lb.Count==0?"No 1v2 games played yet — be the first!":"");
            }
        }

        // Same shape as RenderTeamQueueSection: text-line body with a dynamic
        // LayoutElement height so an empty lobby collapses to one line. 1v2 is
        // unscored, so the context ratings are the queuer's 1v1 elo (always)
        // and 2v2 elo (when they have a completed 2v2 series).
        private static void RenderOvtLobbySection()
        {
            if(txtOvtLobbyHeader==null||txtOvtLobbyBody==null)return;
            var list=ApiClient.CachedOvtQueueList;
            int n=list!=null?list.Count:0;
            float perRow=18f;
            int newH;
            if(n==0)
            {
                UIFactory.SetText(txtOvtLobbyHeader,"<b>1v2 Lobby</b>  <color=#888>(empty)</color>");
                UIFactory.SetText(txtOvtLobbyBody,list==null?"<color=#888>Loading…</color>":"<color=#888>No one in the 1v2 lobby right now.</color>");
                newH=22;
            }
            else
            {
                UIFactory.SetText(txtOvtLobbyHeader,$"<b>1v2 Lobby</b>  <color=#888>({n} — locks at 3)</color>");
                var sb=new StringBuilder();
                foreach(var q in list)
                {
                    bool isMe=q.steam_id==MatchTracker.LocalSteamId;
                    string nameC=isMe?"<color=#88FF88>":"<color=#FFFFFF>";
                    string ratingDisplay=$"<color=#FFFFFF>{q.rating_1v1}</color> <color=#888>1v1</color>";
                    if(q.rating_2v2>0)ratingDisplay+=$"  <color=#DDDDDD>{q.rating_2v2}</color> <color=#888>2v2</color>";
                    string sideTag;
                    if(q.side_assigned==1)sideTag="<color=#FFB347><b>SOLO</b></color>";
                    else if(q.side_assigned==2)sideTag="<color=#88AAFF><b>DUO</b></color>";
                    else if(q.preferred_side==1)sideTag="<color=#FFB347>wants solo</color>";
                    else if(q.preferred_side==2)sideTag="<color=#88AAFF>wants duo</color>";
                    else sideTag="<color=#888>any side</color>";
                    string statusTag=q.status=="searching"?"<color=#66CCFF>searching</color>"
                        :q.status=="ready_join"?"<color=#88FF88>locked</color>":$"<color=#FFD94D>{q.status}</color>";
                    int waitMin=q.wait_seconds/60,waitSec=q.wait_seconds%60;
                    string waitStr=waitMin>0?$"{waitMin}m{waitSec:D2}s":$"{waitSec}s";
                    string extraTag=q.solo_extra_pick?"  <color=#888>+pick</color>":"";
                    sb.Append($"  {nameC}{Trunc(q.display_name,18)}</color>  {ratingDisplay}  {sideTag}  {statusTag}  <color=#888>{waitStr}</color>{extraTag}\n");
                }
                UIFactory.SetText(txtOvtLobbyBody,sb.ToString());
                newH=(int)(n*perRow+6);
            }
            var bodyComp=txtOvtLobbyBody as Component;
            if(bodyComp!=null)
            {
                var le=bodyComp.gameObject.GetComponent(UIFactory.tLE);
                if(le!=null)
                {
                    UIFactory.tLE.GetProperty("preferredHeight",BindingFlags.Public|BindingFlags.Instance)?.SetValue(le,(float)newH);
                    UIFactory.tLE.GetProperty("minHeight",BindingFlags.Public|BindingFlags.Instance)?.SetValue(le,(float)newH);
                }
                var rt=bodyComp.GetComponent<RectTransform>();
                if(rt!=null)rt.sizeDelta=new Vector2(rt.sizeDelta.x,newH);
            }
        }
        private static void SwitchTab(int idx){currentTab=idx;CompetitiveUI.ClearCardHoverRegions();for(int i=0;i<NUM_TABS;i++){if(tabPanels[i]!=null)tabPanels[i].SetActive(i==idx);}UpdateTabBarVisual();if(idx==1){lbTabRefreshAt=Time.unscaledTime+30f;ApiClient.FetchLeaderboard();ApiClient.FetchRecentSeries();ApiClient.FetchActiveSeries();var sid=MatchTracker.LocalSteamId;if(!string.IsNullOrEmpty(sid)&&sid!="unknown")ApiClient.FetchMyBets(sid);}if(idx==2&&ApiClient.CachedCardStats==null)ApiClient.FetchCardStats(200,MatchTracker.LocalSteamId);if(idx==3&&ApiClient.CachedAchievements==null){var id=MatchTracker.LocalSteamId;if(!string.IsNullOrEmpty(id)&&id!="unknown")ApiClient.FetchAchievements(id);}if(idx==4){var id=MatchTracker.LocalSteamId;if(!string.IsNullOrEmpty(id)&&id!="unknown"){ApiClient.FetchShopItems(id);ApiClient.FetchInventory(id);}else ApiClient.FetchShopItems();}if(idx==6){var id=MatchTracker.LocalSteamId;if(!string.IsNullOrEmpty(id)&&ApiClient.IsAdmin){ApiClient.FetchFlaggedMatches(id);ApiClient.FetchBannedUsers(id);ApiClient.FetchAdminRecentSeries(id);}}if(idx==7){ApiClient.FetchTournamentCurrent(MatchTracker.LocalSteamId,force:true);ApiClient.FetchSiteTournamentHistory();ApiClient.FetchActiveSeries();var _msid=MatchTracker.LocalSteamId;if(!string.IsNullOrEmpty(_msid)&&_msid!="unknown"){ApiClient.FetchPlayerTournaments(_msid);ApiClient.FetchMyBets(_msid);}}if(idx==8){if(ApiClient.CachedTeamLeaderboard==null||ApiClient.CachedTeamLeaderboard.Count==0)ApiClient.FetchTeamLeaderboard();var _msid=MatchTracker.LocalSteamId;if(!string.IsNullOrEmpty(_msid)&&_msid!="unknown")ApiClient.FetchTeamMatchHistory(_msid);}if(idx==9){if(ApiClient.CachedLeaderboard==null)ApiClient.FetchLeaderboard();}if(idx==10){var _asid=MatchTracker.LocalSteamId;if(!string.IsNullOrEmpty(_asid)&&_asid!="unknown"&&ApiClient.IsArtist){ApiClient.FetchArtistItems(_asid);ApiClient.FetchMySubmissions(_asid);ApiClient.FetchArtistSales(_asid);}}if(idx==11){ovtTabRefreshAt=Time.unscaledTime+3f;ApiClient.FetchOvtLeaderboard();ApiClient.UpdateOvtQueueList(force:true);}if(idx==TAB_HOME){homeTabRefreshAt=Time.unscaledTime+15f;ApiClient.FetchOnlinePlayers();ApiClient.FetchNewestCosmetics();ApiClient.FetchReleaseNotes();}dirty=true;}

        // ── Home tab (v1.33) — splash/landing page: big logo, latest release
        // notes (GitHub), newest cosmetics, online/recently-online players,
        // plus the Discord Link + chat panels moved over from My Stats. ──
        private static object txtHomeOnlineHdr,txtHomeOnline,txtHomeReleases,txtHomeCosmetics;
        // Newest-cosmetics art rows (Sid feedback: show the actual cosmetic art,
        // animated frames included). A fixed pool filled by RefreshHomeTab; each
        // row is an Image (sprite for face art, or a preview_color swatch for
        // kinds with no shipped PNG) + a two-line text cell.
        private class HomeCosRow{public GameObject root;public GameObject artGO;public object artImg;public object txt;}
        private static readonly List<HomeCosRow> homeCosRows=new List<HomeCosRow>();
        // Item 4: pool covers the last TWO cosmetic-update batches (server
        // caps at 12); the rows live in a scroll so overflow is reachable.
        private const int HOME_COS_ROWS=12;
        private static HomeCosRow CreateHomeCosRow(Transform parent,int idx)
        {
            var r=new HomeCosRow();
            r.root=new GameObject($"hcos{idx}");r.root.transform.SetParent(parent,false);r.root.AddComponent<RectTransform>();
            UIFactory.AddHLG(r.root,spacing:8,padL:2,padR:2,forceExpandH:true);UIFactory.AddLE(r.root,prefH:80,minH:80,flexH:0);
            r.artGO=new GameObject("art");r.artGO.transform.SetParent(r.root.transform,false);r.artGO.AddComponent<RectTransform>();
            // Item 4: art doubled 38 -> 76, text 14 -> 17.
            UIFactory.AddLE(r.artGO,prefW:76,minW:76,prefH:76,flexW:0,flexH:0);
            if(UIFactory.tImage!=null)
            {
                r.artImg=r.artGO.AddComponent(UIFactory.tImage);
                try{UIFactory.tImage.GetProperty("preserveAspect",BindingFlags.Public|BindingFlags.Instance)?.SetValue(r.artImg,true);}catch{}
                try{UIFactory.tImage.GetProperty("raycastTarget",BindingFlags.Public|BindingFlags.Instance)?.SetValue(r.artImg,false);}catch{}
            }
            r.txt=UIFactory.CreateText("t",r.root.transform,"",17f,C_WHITE,UIFactory.AlignMidLeft,sizeDelta:new Vector2(310,76));
            UIFactory.SetWordWrap(r.txt,false);
            r.root.SetActive(false);
            return r;
        }
        private static float homeTabRefreshAt;
        private static Sprite _homeLogoSprite;private static bool _homeLogoTried;
        private static Sprite GetHomeLogoSprite()
        {
            if(_homeLogoTried)return _homeLogoSprite;
            _homeLogoTried=true;
            try
            {
                var asm=Assembly.GetExecutingAssembly();
                string resName=null;
                foreach(var n in asm.GetManifestResourceNames())if(n.EndsWith("logo.png",StringComparison.OrdinalIgnoreCase)){resName=n;break;}
                if(resName==null){Plugin.Log.LogWarning("[HOME] embedded logo resource not found");return null;}
                using(var st=asm.GetManifestResourceStream(resName))
                {
                    if(st==null)return null;
                    var bytes=new byte[st.Length];int off=0;
                    while(off<bytes.Length){int r=st.Read(bytes,off,bytes.Length-off);if(r<=0)break;off+=r;}
                    var tex=new Texture2D(2,2,TextureFormat.RGBA32,false);
                    if(!tex.LoadImage(bytes))return null;
                    tex.hideFlags=HideFlags.HideAndDontSave;
                    _homeLogoSprite=Sprite.Create(tex,new Rect(0,0,tex.width,tex.height),new Vector2(0.5f,0.5f));
                    _homeLogoSprite.hideFlags=HideFlags.HideAndDontSave;
                }
            }
            catch(Exception ex){Plugin.Log.LogWarning($"[HOME] logo load failed: {ex.Message}");}
            return _homeLogoSprite;
        }
        /* Player names / server strings entering rich text — neuter angle brackets
         * so a crafted name can't inject TMP tags into the Home panels. */
        private static string HomeSan(string s){return string.IsNullOrEmpty(s)?"":s.Replace("<","[").Replace(">","]");}
        /* Coarse by design (Sid's item 6): no exact minutes — under an hour is
         * just "recently online", beyond that flat hours. */
        private static string FmtAgo(int minutes){if(minutes<60)return "recently online";return $"{minutes/60}h ago";}
        private static string HomeTitleSpan(ApiClient.OnlinePlayerEntry p){if(string.IsNullOrEmpty(p.title))return "";string tc=string.IsNullOrEmpty(p.titleColor)?"#FFFFFF":p.titleColor;return $" <b><color={tc}>[{HomeSan(p.title)}]</color></b>";}
        private static GameObject BuildHomeTab(Transform parent)
        {
            var panel=new GameObject("Home");panel.transform.SetParent(parent,false);panel.AddComponent<RectTransform>();UIFactory.AddVLG(panel,spacing:6);UIFactory.AddLE(panel,flexH:1);
            /* Header row: logo + title block, centered as a unit via end spacers. */
            var hdr=new GameObject("HomeHdr");hdr.transform.SetParent(panel.transform,false);hdr.AddComponent<RectTransform>();UIFactory.AddHLG(hdr,spacing:16,forceExpandH:false);UIFactory.AddLE(hdr,prefH:112,minH:112,flexH:0);
            var hSpL=new GameObject("S");hSpL.transform.SetParent(hdr.transform,false);hSpL.AddComponent<RectTransform>();UIFactory.AddLE(hSpL,flexW:1);
            var logoGO=new GameObject("HomeLogo");logoGO.transform.SetParent(hdr.transform,false);logoGO.AddComponent<RectTransform>();UIFactory.AddLE(logoGO,prefW:104,prefH:104,minW:104,minH:104,flexW:0,flexH:0);
            var logoSpr=GetHomeLogoSprite();
            if(logoSpr!=null&&UIFactory.tImage!=null)
            {
                var img=logoGO.AddComponent(UIFactory.tImage);
                UIFactory.tImage.GetProperty("sprite",BindingFlags.Public|BindingFlags.Instance)?.SetValue(img,logoSpr);
                UIFactory.tImage.GetProperty("preserveAspect",BindingFlags.Public|BindingFlags.Instance)?.SetValue(img,true);
                UIFactory.tImage.GetProperty("raycastTarget",BindingFlags.Public|BindingFlags.Instance)?.SetValue(img,false);
            }
            var hTxtCol=new GameObject("HomeHdrTxt");hTxtCol.transform.SetParent(hdr.transform,false);hTxtCol.AddComponent<RectTransform>();UIFactory.AddVLG(hTxtCol,spacing:2);UIFactory.AddLE(hTxtCol,prefW:460,flexW:0,flexH:0);
            UIFactory.CreateText("HT",hTxtCol.transform,"SID'S COMPETITIVE ROUNDS",30f,C_WHITE,UIFactory.AlignMidLeft,sizeDelta:new Vector2(460,40));
            UIFactory.CreateText("HS",hTxtCol.transform,$"Ranked 1v1 - 2v2 - tournaments - cosmetics   <color=#666>v{Plugin.ModVersion}</color>",15f,C_LABEL,UIFactory.AlignMidLeft,sizeDelta:new Vector2(460,22));
            txtHomeOnlineHdr=UIFactory.CreateText("HO",hTxtCol.transform,"",17f,C_GREEN,UIFactory.AlignMidLeft,sizeDelta:new Vector2(460,26));
            var hSpR=new GameObject("S");hSpR.transform.SetParent(hdr.transform,false);hSpR.AddComponent<RectTransform>();UIFactory.AddLE(hSpR,flexW:1);
            /* Columns: LEFT players + Discord link + chat, RIGHT releases + cosmetics.
             * flexW:0 EXPLICIT on the fixed left column (learning #132). */
            var cols=new GameObject("HomeCols");cols.transform.SetParent(panel.transform,false);cols.AddComponent<RectTransform>();UIFactory.AddHLG(cols,spacing:8);UIFactory.AddLE(cols,flexH:1);
            var left=new GameObject("HLeft");left.transform.SetParent(cols.transform,false);left.AddComponent<RectTransform>();UIFactory.AddVLG(left,spacing:4);UIFactory.AddLE(left,prefW:420,minW:360,flexW:0,flexH:1);
            var onBox=UIFactory.CreatePanel("HOn",left.transform,C_PANEL);UIFactory.AddVLG(onBox,spacing:2,padL:10,padR:10,padT:6,padB:6);UIFactory.AddLE(onBox,flexH:1);
            UIFactory.CreateText("HOnH",onBox.transform,"Players",19f,C_SUB,sizeDelta:new Vector2(380,28));
            var onSV=UIFactory.CreateScrollView("HOnSV",onBox.transform,spacing:0);UIFactory.AddLE(onSV.scrollGO,flexH:1);
            txtHomeOnline=UIFactory.CreateText("HOnT",onSV.content.transform,"<color=#888><i>Loading...</i></color>",15f,C_WHITE,UIFactory.AlignTopLeft,sizeDelta:new Vector2(380,24));
            UIFactory.SetWordWrap(txtHomeOnline,true);UIFactory.SetTextAutoHeight(txtHomeOnline);
            /* Discord Link panel (moved from My Stats — same statics rewired). */
            var linkBox=UIFactory.CreatePanel("LkB",left.transform,C_PANEL);UIFactory.AddVLG(linkBox,spacing:4,padL:10,padR:10,padT:6,padB:6);UIFactory.AddLE(linkBox,flexH:0);UIFactory.CreateText("LkL",linkBox.transform,"Discord Link",19f,new Color(0.55f,0.55f,0.95f),sizeDelta:new Vector2(340,28));var lkRow=new GameObject("LkR");lkRow.transform.SetParent(linkBox.transform,false);lkRow.AddComponent<RectTransform>();UIFactory.AddHLG(lkRow,spacing:8);UIFactory.AddLE(lkRow,prefH:28);linkCodeBtn=UIFactory.CreateButton("LkBtn",lkRow.transform,"Get Link Code",15f,C_WHITE,C_BTN,()=>{var id=MatchTracker.LocalSteamId;if(!string.IsNullOrEmpty(id)&&id!="unknown")ApiClient.GenerateLinkCode(id);},sizeDelta:new Vector2(130,26));/* Click-to-reveal on the link text - Discord ID/username defaults hidden for streamers.
 * TMP text IS already a Graphic; adding an Image to the same GO throws. Just enable its own raycastTarget. */
            txtLinkCode=UIFactory.CreateText("LkC",lkRow.transform,"Type !link CODE in Discord",15f,C_DIM,sizeDelta:new Vector2(240,26),raycastTarget:true);{var lkTextComp=txtLinkCode as Component;if(lkTextComp!=null){var ch=lkTextComp.gameObject.AddComponent<ClickHandler>();ch.onClick=()=>{if(ClickGuard.Claim()){discordRevealed=!discordRevealed;dirty=true;}};}}
            /* Newest cosmetics — now shows the ACTUAL art (animated included),
             * so it's taller and eats flex space the Players box used to take
             * (Sid feedback). prefH 300 vs the old 170; Players (onBox flexH:1)
             * shrinks to whatever's left. */
            /* Item 4: bigger art (76px) + bigger text + the last TWO update
             * batches, so the rows now live in a ScrollView (learning #63:
             * rows carry fixed prefH:80, the scroll itself takes the flex). */
            var cosBox=UIFactory.CreatePanel("HCos",left.transform,C_PANEL);UIFactory.AddVLG(cosBox,spacing:3,padL:10,padR:10,padT:6,padB:6);UIFactory.AddLE(cosBox,prefH:340,minH:280,flexH:0);
            UIFactory.CreateText("HCosH",cosBox.transform,"Newest Cosmetics",22f,new Color(0.85f,0.6f,1f),sizeDelta:new Vector2(380,30));
            txtHomeCosmetics=UIFactory.CreateText("HCosT",cosBox.transform,"<color=#888><i>Loading...</i></color>",15f,C_DIM,UIFactory.AlignTopLeft,sizeDelta:new Vector2(380,22));
            var cosSV=UIFactory.CreateScrollView("HCosSV",cosBox.transform,spacing:2);UIFactory.AddLE(cosSV.scrollGO,flexH:1);
            homeCosRows.Clear();for(int i=0;i<HOME_COS_ROWS;i++)homeCosRows.Add(CreateHomeCosRow(cosSV.content.transform,i));
            var right=new GameObject("HRight");right.transform.SetParent(cols.transform,false);right.AddComponent<RectTransform>();UIFactory.AddVLG(right,spacing:4);UIFactory.AddLE(right,flexW:1,flexH:1);
            var relBox=UIFactory.CreatePanel("HRel",right.transform,C_PANEL);UIFactory.AddVLG(relBox,spacing:2,padL:10,padR:10,padT:6,padB:6);UIFactory.AddLE(relBox,flexH:1);
            UIFactory.CreateText("HRelH",relBox.transform,"Latest Releases",19f,C_GOLD,sizeDelta:new Vector2(400,28));
            var relSV=UIFactory.CreateScrollView("HRelSV",relBox.transform,spacing:0);UIFactory.AddLE(relSV.scrollGO,flexH:1);
            txtHomeReleases=UIFactory.CreateText("HRelT",relSV.content.transform,"<color=#888><i>Loading release notes...</i></color>",14f,C_WHITE,UIFactory.AlignTopLeft,sizeDelta:new Vector2(560,24));
            UIFactory.SetWordWrap(txtHomeReleases,true);UIFactory.SetTextAutoHeight(txtHomeReleases);
            /* In-game <-> Discord chat panel (moved from My Stats; item 1 swap put
             * it in the WIDE right column and made it taller — 240px vs the old
             * 160px corner box). Users send via hotkey T (IMGUI overlay). */
            var chatBox=UIFactory.CreatePanel("CB",right.transform,C_PANEL);UIFactory.AddVLG(chatBox,spacing:4,padL:10,padR:10,padT:6,padB:6);UIFactory.AddLE(chatBox,flexH:0);UIFactory.CreateText("CH",chatBox.transform,"Chat  <color=#888>(press T to send)</color>",17f,new Color(0.7f,0.85f,1f),sizeDelta:new Vector2(340,26));var chSV=UIFactory.CreateScrollView("ChSV",chatBox.transform,spacing:0);UIFactory.AddLE(chSV.scrollGO,prefH:240,minH:240,flexH:0);chatScrollRect=chSV.scrollGO.GetComponent(UIFactory.tScrollRect);txtChatLog=UIFactory.CreateText("ChLog",chSV.content.transform,"<color=#888><i>No messages yet. Anyone chatting here or in #scr-discussion on Discord will appear.</i></color>",14f,C_WHITE,UIFactory.AlignTopLeft,sizeDelta:new Vector2(560,400));UIFactory.SetWordWrap(txtChatLog,true);
/* CreateText baked a LayoutElement with prefH=400 onto the chat-log GO. With the parent VLG/CSF reading
 * that, a single very long message (e.g. a 9000-char changelog paste) renders as TMP overflow but the
 * scroll content stays clamped at 400px -> unreachable bottom. Zero out the prefH so TMP's own
 * ILayoutElement.preferredHeight (its actual rendered height) drives the content size instead. */
            {var chatLE=(txtChatLog as Component)?.gameObject.GetComponent(UIFactory.tLE);if(chatLE!=null){var prefHProp=UIFactory.tLE.GetProperty("preferredHeight",BindingFlags.Public|BindingFlags.Instance);prefHProp?.SetValue(chatLE,-1f);}}
            return panel;
        }
        private static void RefreshHomeTab()
        {
            /* Discord-link state (moved from RefreshMyStats — statics live here now). */
            var s=ApiClient.CachedPlayerStats;
            if(linkCodeBtn!=null&&txtLinkCode!=null)
            {
                bool linked=s!=null&&!string.IsNullOrEmpty(s.discord_id);
                linkCodeBtn.SetActive(!linked);
                if(linked)
                {
                    string raw=!string.IsNullOrEmpty(s.discord_username)?$"@{s.discord_username}":$"ID {s.discord_id}";
                    string who=discordRevealed?raw:"<color=#888>***** (click to show)</color>";
                    UIFactory.SetText(txtLinkCode,$"<color=#00FF00>Linked to Discord</color> ({who})");
                }
            }
            /* Online / recently-online players. */
            int onlineCount=ApiClient.CachedOnlineListCount>0?ApiClient.CachedOnlineListCount:ApiClient.CachedOnlineCount;
            if(txtHomeOnlineHdr!=null)UIFactory.SetText(txtHomeOnlineHdr,onlineCount>0?$"{onlineCount} player{(onlineCount==1?"":"s")} online now":"");
            if(txtHomeOnline!=null)
            {
                var sb=new StringBuilder();
                var on=ApiClient.CachedOnlinePlayers;var rec=ApiClient.CachedRecentPlayers;
                sb.Append("<color=#66FF88>Online now</color>\n");
                if(on==null)sb.Append("<color=#888><i>Loading...</i></color>\n");
                else if(on.Count==0)sb.Append("<color=#888><i>Nobody visible right now.</i></color>\n");
                else foreach(var p in on)sb.Append($"<color=#66FF88>*</color> {HomeSan(p.name)}{HomeTitleSpan(p)}  <color=#8FA3B8>{p.rating}</color>\n");
                sb.Append("\n<color=#99AAEE>Recently online</color>\n");
                if(rec==null||rec.Count==0)sb.Append("<color=#888><i>-</i></color>\n");
                else foreach(var p in rec)sb.Append($"{HomeSan(p.name)}{HomeTitleSpan(p)}  <color=#8FA3B8>{p.rating}</color>  <color=#777>{FmtAgo(p.minutesAgo)}</color>\n");
                sb.Append("\n<color=#666><i>Hide yourself here: Settings -> Appear offline.</i></color>");
                UIFactory.SetText(txtHomeOnline,sb.ToString());
            }
            /* Latest releases (GitHub). */
            if(txtHomeReleases!=null)
            {
                var rel=ApiClient.CachedReleaseNotes;
                if(rel==null)UIFactory.SetText(txtHomeReleases,"<color=#888><i>Loading release notes...</i></color>");
                else if(rel.Count==0)UIFactory.SetText(txtHomeReleases,"<color=#888><i>Release notes unavailable right now.</i></color>");
                else
                {
                    var sb=new StringBuilder();
                    foreach(var r in rel)
                    {
                        sb.Append($"<color=#FFD94D>{HomeSan(r.tag)}</color>");
                        if(!string.IsNullOrEmpty(r.title)&&r.title!=r.tag)sb.Append($"  <b>{HomeSan(r.title)}</b>");
                        if(!string.IsNullOrEmpty(r.date))sb.Append($"  <color=#777>{r.date}</color>");
                        sb.Append('\n');
                        if(!string.IsNullOrEmpty(r.body))sb.Append($"<color=#C8D2DC>{r.body}</color>\n");
                        sb.Append('\n');
                    }
                    UIFactory.SetText(txtHomeReleases,sb.ToString());
                }
            }
            /* Newest cosmetics — art thumbnails (animated where available). */
            {
                var cos=ApiClient.CachedNewestCosmetics;
                // Item 4: the list covers the last two update batches — name
                // both dates in the caption so the split is legible.
                string cosCaption="<color=#888><i>Grab them in the Shop tab.</i></color>";
                if(cos!=null&&cos.Count>0)
                {
                    var batchDates=new List<string>();
                    foreach(var cc in cos)
                        if(!string.IsNullOrEmpty(cc.added)&&!batchDates.Contains(cc.added))batchDates.Add(cc.added);
                    if(batchDates.Count>=2)
                        cosCaption=$"<color=#888><i>Updates of {batchDates[0]} & {batchDates[1]} - grab them in the Shop tab.</i></color>";
                    else if(batchDates.Count==1)
                        cosCaption=$"<color=#888><i>Update of {batchDates[0]} - grab them in the Shop tab.</i></color>";
                }
                if(txtHomeCosmetics!=null)
                    UIFactory.SetText(txtHomeCosmetics,
                        cos==null?"<color=#888><i>Loading...</i></color>":
                        cos.Count==0?"<color=#888><i>None yet.</i></color>":
                        cosCaption);
                for(int i=0;i<homeCosRows.Count;i++)
                {
                    var row=homeCosRows[i];
                    if(cos==null||i>=cos.Count){if(row.artImg!=null)TrackAnimatedThumb(row.artImg,null,0f);row.root.SetActive(false);continue;}
                    var c=cos[i];
                    // Defense-in-depth (learning #163): the server hides community
                    // face items whose PNG hasn't shipped (catalog_ready=false), but
                    // a client older than the release that flipped catalog_ready could
                    // still receive one — and a face sku with no local sprite renders
                    // as a flat preview_color swatch (the "green square"). Skip it.
                    if((c.kind??"")=="face"&&CustomCosmetics.GetShopSprite(c.sku)==null)
                    {if(row.artImg!=null)TrackAnimatedThumb(row.artImg,null,0f);row.root.SetActive(false);continue;}
                    string col=!string.IsNullOrEmpty(c.previewColor)&&c.previewColor.StartsWith("#")?c.previewColor:"#FFFFFF";
                    string kind=(c.kind??"").Replace('_',' ');
                    string artistLine=!string.IsNullOrEmpty(c.artistName)?$"  <color=#888>by {HomeSan(c.artistName)}</color>":"";
                    string addedTag=!string.IsNullOrEmpty(c.added)?$"  <color=#666>{c.added}</color>":"";
                    // July 17 round 4: not-yet-opened artist items show as a
                    // tease — the artist sets the real price when opening
                    // sales, so the seed price would mislead.
                    string priceTag=c.onSale?$"<color=#FFD94D>{c.price}g</color>":"<color=#FF9BE0>coming soon!</color>";
                    UIFactory.SetText(row.txt,
                        $"<color={col}>{HomeSan(c.name)}</color>  {priceTag}\n"
                        +$"<color=#8FA3B8>({HomeSan(kind)}, {HomeSan(c.rarity)})</color>{artistLine}{addedTag}");
                    if(row.artImg!=null)
                    {
                        var pSprite=UIFactory.tImage.GetProperty("sprite",BindingFlags.Public|BindingFlags.Instance);
                        var pColor=UIFactory.tImage.GetProperty("color",BindingFlags.Public|BindingFlags.Instance);
                        var sp=CustomCosmetics.GetShopSprite(c.sku);
                        if(sp!=null)
                        {
                            // Real cosmetic art (face PNGs) — white tint, register
                            // animation frames so multi-frame skus cycle on Home too.
                            try{pSprite?.SetValue(row.artImg,sp);pColor?.SetValue(row.artImg,Color.white);}catch{}
                            var frames=CustomCosmetics.GetShopFrames(c.sku,out float fps);
                            TrackAnimatedThumb(row.artImg,frames,fps);
                        }
                        else
                        {
                            // Kinds with no shipped art (titles/trails/colors/nametags)
                            // — a solid preview_color swatch (a null-sprite Image
                            // renders as its color).
                            Color sw;if(!ColorUtility.TryParseHtmlString(col,out sw))sw=new Color(0.4f,0.42f,0.5f);sw.a=1f;
                            try{pSprite?.SetValue(row.artImg,null);pColor?.SetValue(row.artImg,sw);}catch{}
                            TrackAnimatedThumb(row.artImg,null,0f);
                        }
                    }
                    row.root.SetActive(true);
                }
            }
            RefreshChatLog();
        }
        /* Throttled presence refresh while the Home tab is open (learning #62 —
         * tabs only repaint on dirty flips; this is the flip source). */
        private static void MaybeRefreshHomeTab()
        {
            if(currentTab!=TAB_HOME)return;
            if(Time.unscaledTime<homeTabRefreshAt)return;
            homeTabRefreshAt=Time.unscaledTime+15f;
            ApiClient.FetchOnlinePlayers();
        }
        private static GameObject BuildMyStatsTab(Transform parent){/* v1.33 item 4: My Stats heads a sub-tab group (Card Stats + Achievements).
         * Same outer-wrapper pattern as 2v2/1v2/FFA — the anchor lives in an
         * UNPADDED VLG outer so the sub-tab bar sits at the identical top
         * position on all three tabs; the original HLG panel nests inside. */
        var outer=new GameObject("MyStatsOuter");outer.transform.SetParent(parent,false);outer.AddComponent<RectTransform>();UIFactory.AddVLG(outer,spacing:2);UIFactory.AddLE(outer,flexH:1);MakeSubTabAnchor(0,outer.transform,true);
        var panel=new GameObject("MyStats");panel.transform.SetParent(outer.transform,false);panel.AddComponent<RectTransform>();UIFactory.AddHLG(panel,spacing:8);UIFactory.AddLE(panel,flexH:1);var left=new GameObject("Left");left.transform.SetParent(panel.transform,false);left.AddComponent<RectTransform>();UIFactory.AddVLG(left,spacing:4);UIFactory.AddLE(left,prefW:380);var rBox=UIFactory.CreatePanel("RB",left.transform,C_PANEL);UIFactory.AddVLG(rBox,spacing:2,padL:10,padR:10,padT:6,padB:6);UIFactory.AddLE(rBox,flexH:0);var glHdr=UIFactory.CreateText("RL",rBox.transform,"Glicko-2 Rating",19f,C_SUB,sizeDelta:new Vector2(250,28));UIFactory.SetCharSpacing(glHdr,1f);var rRow=new GameObject("RR");rRow.transform.SetParent(rBox.transform,false);rRow.AddComponent<RectTransform>();UIFactory.AddHLG(rRow,spacing:12);UIFactory.AddLE(rRow,prefH:38);txtRating=UIFactory.CreateText("Rat",rRow.transform,"1500",30f,C_WHITE,UIFactory.AlignMidLeft,sizeDelta:new Vector2(110,38));UIFactory.SetBold(txtRating,true);txtRD=UIFactory.CreateText("RD",rRow.transform,"RD: 350",18f,C_LABEL,UIFactory.AlignMidLeft,sizeDelta:new Vector2(240,38));var xBox=UIFactory.CreatePanel("XB",left.transform,C_PANEL);UIFactory.AddVLG(xBox,spacing:2,padL:10,padR:10,padT:6,padB:6);UIFactory.AddLE(xBox,flexH:0);var lvRow=new GameObject("LR");lvRow.transform.SetParent(xBox.transform,false);lvRow.AddComponent<RectTransform>();UIFactory.AddHLG(lvRow,spacing:8);UIFactory.AddLE(lvRow,prefH:28);txtLevel=UIFactory.CreateText("Lv",lvRow.transform,"Level 1",19f,C_BLUE,UIFactory.AlignMidLeft,sizeDelta:new Vector2(100,28));UIFactory.SetBold(txtLevel,true);txtXPProg=UIFactory.CreateText("XPP",lvRow.transform,"",16f,C_LABEL,UIFactory.AlignMidLeft,sizeDelta:new Vector2(130,28));var xSp=new GameObject("S");xSp.transform.SetParent(lvRow.transform,false);xSp.AddComponent<RectTransform>();UIFactory.AddLE(xSp,flexW:1);txtTotalXP=UIFactory.CreateText("TXP",lvRow.transform,"0 XP",16f,C_LABEL,UIFactory.AlignMidRight,sizeDelta:new Vector2(110,28));xpFill=UIFactory.CreateFillBar("XP",xBox.transform,new Color(0.2f,0.2f,0.25f,0.8f),new Color(0.3f,0.7f,1f,0.9f),10f);var recBox=UIFactory.CreatePanel("RecB",left.transform,C_PANEL);UIFactory.AddVLG(recBox,spacing:1,padL:10,padR:10,padT:6,padB:6);UIFactory.AddLE(recBox,flexH:0);UIFactory.CreateText("RecL",recBox.transform,"Record",19f,C_SUB,sizeDelta:new Vector2(340,28));txtRankedRec=UIFactory.CreateText("RR",recBox.transform,"",16f,C_WHITE,sizeDelta:new Vector2(340,24));txtRankedStrk=UIFactory.CreateText("RS",recBox.transform,"",15f,C_LABEL,sizeDelta:new Vector2(340,44));txtTeam2v2Rec=UIFactory.CreateText("T2",recBox.transform,"",16f,C_WHITE,sizeDelta:new Vector2(340,24));txtTeam2v2Strk=UIFactory.CreateText("T2S",recBox.transform,"",15f,C_LABEL,sizeDelta:new Vector2(340,22));txtCasualRec=UIFactory.CreateText("CR",recBox.transform,"",16f,C_WHITE,sizeDelta:new Vector2(340,24));txtCasualStrk=UIFactory.CreateText("CS",recBox.transform,"",15f,C_LABEL,sizeDelta:new Vector2(340,22));txtSweeps=UIFactory.CreateText("SW",recBox.transform,"",16f,C_WHITE,sizeDelta:new Vector2(340,24));txtTotalRec=UIFactory.CreateText("TR",recBox.transform,"",15f,C_LABEL,sizeDelta:new Vector2(340,22));txtAccuracy=UIFactory.CreateText("AC",recBox.transform,"",15f,C_LABEL,sizeDelta:new Vector2(340,44));var sesBox=UIFactory.CreatePanel("SB",left.transform,C_PANEL);UIFactory.AddVLG(sesBox,spacing:3,padL:10,padR:10,padT:8,padB:8);UIFactory.AddLE(sesBox,flexH:0);UIFactory.CreateText("SL",sesBox.transform,"Session Info",19f,new Color(0.7f,0.8f,1f),sizeDelta:new Vector2(340,28));txtSessionSum=UIFactory.CreateText("SS",sesBox.transform,"No games this session",17f,C_DIM,sizeDelta:new Vector2(340,26));txtSessionSplit=UIFactory.CreateText("SSp",sesBox.transform,"",16f,C_LABEL,sizeDelta:new Vector2(340,24));txtSessionSweeps=UIFactory.CreateText("SSw",sesBox.transform,"",16f,C_WHITE,sizeDelta:new Vector2(340,24));txtSessionOppLifetime=UIFactory.CreateText("SOL",sesBox.transform,"",15f,new Color(0.6f,0.75f,1f),sizeDelta:new Vector2(340,22));sessionOppContainer=new GameObject("SOC");sessionOppContainer.transform.SetParent(sesBox.transform,false);sessionOppContainer.AddComponent<RectTransform>();UIFactory.AddVLG(sessionOppContainer,spacing:1);
        /* Discord Link + chat panels moved to the Home tab (v1.33) — the left
         * column here keeps rating/XP/record/session; Home is the social hub. */
        var right=new GameObject("Right");right.transform.SetParent(panel.transform,false);right.AddComponent<RectTransform>();UIFactory.AddVLG(right,spacing:4);UIFactory.AddLE(right,flexW:1,flexH:1);var rkBox=UIFactory.CreatePanel("RkB",right.transform,C_PANEL);UIFactory.AddVLG(rkBox,spacing:1,padL:8,padR:8,padT:6,padB:6);UIFactory.AddLE(rkBox,flexH:1);UIFactory.CreateText("RkH",rkBox.transform,"Ranked History",21f,C_GOLD,sizeDelta:new Vector2(250,30));txtOppSummary=UIFactory.CreateText("OS",rkBox.transform,"",15f,new Color(0.7f,0.8f,1f),sizeDelta:new Vector2(500,22));var rkSV=UIFactory.CreateScrollView("RkSV",rkBox.transform,spacing:1);UIFactory.AddLE(rkSV.scrollGO,flexH:1);rankedContainer=rkSV.content;for(int i=0;i<15;i++)rankedRows.Add(CreateHistoryRow(rankedContainer.transform,$"rr{i}"));var rPg=new GameObject("RPg");rPg.transform.SetParent(rkBox.transform,false);rPg.AddComponent<RectTransform>();UIFactory.AddHLG(rPg,spacing:6,forceExpandH:true);UIFactory.AddLE(rPg,prefH:20,flexH:0);var rS1=new GameObject("S");rS1.transform.SetParent(rPg.transform,false);rS1.AddComponent<RectTransform>();UIFactory.AddLE(rS1,flexW:1);rPrev=UIFactory.CreateButton("rP",rPg.transform,"< Prev",10f,C_LABEL,C_BTN,()=>{if(rankedPage>0){rankedPage--;dirty=true;}},sizeDelta:new Vector2(50,18));txtRankedPage=UIFactory.CreateText("rPI",rPg.transform,"",10f,C_LABEL,UIFactory.AlignMidCenter,sizeDelta:new Vector2(35,18));rNext=UIFactory.CreateButton("rN",rPg.transform,"Next >",10f,C_LABEL,C_BTN,()=>{rankedPage++;dirty=true;},sizeDelta:new Vector2(50,18));var rS2=new GameObject("S");rS2.transform.SetParent(rPg.transform,false);rS2.AddComponent<RectTransform>();UIFactory.AddLE(rS2,flexW:1);rCardModeBtn=UIFactory.CreateButton("rCm",rPg.transform,"",10f,C_LABEL,C_BTN,ToggleHistoryCardMode,sizeDelta:new Vector2(100,18));rCardModeTxt=UIFactory.GetButtonText(rCardModeBtn);
        var csBox=UIFactory.CreatePanel("CsB",right.transform,C_PANEL);UIFactory.AddVLG(csBox,spacing:1,padL:8,padR:8,padT:6,padB:6);UIFactory.AddLE(csBox,flexH:1);UIFactory.CreateText("CsH",csBox.transform,"Casual History",21f,C_SUB,sizeDelta:new Vector2(250,30));var csSV=UIFactory.CreateScrollView("CsSV",csBox.transform,spacing:1);UIFactory.AddLE(csSV.scrollGO,flexH:1);casualContainer=csSV.content;for(int i=0;i<12;i++)casualRows.Add(CreateHistoryRow(casualContainer.transform,$"cr{i}"));var cPg=new GameObject("CPg");cPg.transform.SetParent(csBox.transform,false);cPg.AddComponent<RectTransform>();UIFactory.AddHLG(cPg,spacing:6,forceExpandH:true);UIFactory.AddLE(cPg,prefH:20,flexH:0);var cS1=new GameObject("S");cS1.transform.SetParent(cPg.transform,false);cS1.AddComponent<RectTransform>();UIFactory.AddLE(cS1,flexW:1);cPrev=UIFactory.CreateButton("cP",cPg.transform,"< Prev",10f,C_LABEL,C_BTN,()=>{if(casualPage>0){casualPage--;dirty=true;}},sizeDelta:new Vector2(50,18));txtCasualPage=UIFactory.CreateText("cPI",cPg.transform,"",10f,C_LABEL,UIFactory.AlignMidCenter,sizeDelta:new Vector2(35,18));cNext=UIFactory.CreateButton("cN",cPg.transform,"Next >",10f,C_LABEL,C_BTN,()=>{casualPage++;dirty=true;},sizeDelta:new Vector2(50,18));var cS2=new GameObject("S");cS2.transform.SetParent(cPg.transform,false);cS2.AddComponent<RectTransform>();UIFactory.AddLE(cS2,flexW:1);cCardModeBtn=UIFactory.CreateButton("cCm",cPg.transform,"",10f,C_LABEL,C_BTN,ToggleHistoryCardMode,sizeDelta:new Vector2(100,18));cCardModeTxt=UIFactory.GetButtonText(cCardModeBtn);return outer;}

        private static HistoryRow CreateHistoryRow(Transform parent,string name){var row=new HistoryRow();row.seriesGO=new GameObject(name+"s");row.seriesGO.transform.SetParent(parent,false);row.seriesGO.AddComponent<RectTransform>();UIFactory.AddHLG(row.seriesGO,spacing:4,padL:4);UIFactory.AddLE(row.seriesGO,prefH:25);row.txtSeriesHead=UIFactory.CreateText("sh",row.seriesGO.transform,"",19f,C_GREEN,sizeDelta:new Vector2(500,25));row.txtSeriesElo=UIFactory.CreateText("se",row.seriesGO.transform,"",19f,C_GREEN,UIFactory.AlignMidRight,sizeDelta:new Vector2(160,25));row.seriesGO.SetActive(false);row.root=new GameObject(name);row.root.transform.SetParent(parent,false);row.root.AddComponent<RectTransform>();UIFactory.AddVLG(row.root,spacing:0,padL:4);var main=new GameObject("m");main.transform.SetParent(row.root.transform,false);main.AddComponent<RectTransform>();UIFactory.AddHLG(main,spacing:4);UIFactory.AddLE(main,prefH:25);/* Feedback item 4: txtResult width hugs the score text (was 200 — the dead right half pushed the ID button visually next to "vs Player" instead of the score). */row.txtResult=UIFactory.CreateText("r",main.transform,"",19f,C_GREEN,UIFactory.AlignMidLeft,sizeDelta:new Vector2(132,25));/* July 22 item 6: tiny click-to-copy game-ID button. Sits OUTSIDE txtResult's rect so the score hover graph keeps its region. Ordered FIRST (before the score) in both ranked and casual history — next to the scoring column, not the "vs Player" text. Setting the sibling index here, at creation, is deliberate: doing it from BuildPage instead would silently no-op if tab construction ever became lazy or reordered (learning #91/#158). Later-created children append after it, so index 0 stays index 0. */row.btnId=UIFactory.CreateButton("id",main.transform,"ID",9f,C_DIM,C_BTN,()=>CopyGameCode(row.currentMatchId),sizeDelta:new Vector2(24,17));row.btnId.transform.SetSiblingIndex(0);row.btnId.SetActive(false);row.txtOpp=UIFactory.CreateText("o",main.transform,"",18f,C_WHITE,UIFactory.AlignMidLeft,sizeDelta:new Vector2(240,25));row.txtFps=UIFactory.CreateText("fp",main.transform,"",14f,C_LABEL,UIFactory.AlignMidLeft,sizeDelta:new Vector2(120,25));var spFp=new GameObject("Sfp");spFp.transform.SetParent(main.transform,false);spFp.AddComponent<RectTransform>();UIFactory.AddLE(spFp,prefW:22,flexW:0);row.txtPing=UIFactory.CreateText("pg",main.transform,"",14f,C_LABEL,UIFactory.AlignMidLeft,sizeDelta:new Vector2(150,25));/* July 22: FPS and Ping are SEPARATE hover targets, spaced apart */var sp=new GameObject("S");sp.transform.SetParent(main.transform,false);sp.AddComponent<RectTransform>();UIFactory.AddLE(sp,flexW:1);row.txtXP=UIFactory.CreateText("x",main.transform,"",16f,C_BLUE,UIFactory.AlignMidRight,sizeDelta:new Vector2(65,25));row.txtDate=UIFactory.CreateText("d",main.transform,"",15f,C_DIM,UIFactory.AlignMidRight,sizeDelta:new Vector2(45,25));/* Item 4 (v1.30): per-game combat stats line — sits in the dead space under the FPS values. Hidden (empty) for rows without telemetry. July 22 item 1: split into per-player elements so each Hit%/Block% is its own hover target popping its own graph. */var st=new GameObject("st");st.transform.SetParent(row.root.transform,false);st.AddComponent<RectTransform>();UIFactory.AddHLG(st,spacing:2);UIFactory.AddLE(st,prefH:20);var cStat=new Color(0.65f,0.7f,0.78f);/* Feedback item 4: widths hug the rendered text so the line reads like the old single-string layout (hover regions trim to preferredWidth regardless). */row.txtStats=UIFactory.CreateText("st0",st.transform,"",14f,cStat,UIFactory.AlignMidLeft,sizeDelta:new Vector2(70,20));row.txtHitYou=UIFactory.CreateText("hy",st.transform,"",14f,cStat,UIFactory.AlignMidLeft,sizeDelta:new Vector2(110,20));row.txtBlockYou=UIFactory.CreateText("by",st.transform,"",14f,cStat,UIFactory.AlignMidLeft,sizeDelta:new Vector2(88,20));row.txtKpsYou=UIFactory.CreateText("ky",st.transform,"",14f,cStat,UIFactory.AlignMidLeft,sizeDelta:new Vector2(96,20));row.txtHitOpp=UIFactory.CreateText("ho",st.transform,"",14f,cStat,UIFactory.AlignMidLeft,sizeDelta:new Vector2(110,20));row.txtBlockOpp=UIFactory.CreateText("bo",st.transform,"",14f,cStat,UIFactory.AlignMidLeft,sizeDelta:new Vector2(88,20));row.txtKpsOpp=UIFactory.CreateText("ko",st.transform,"",14f,cStat,UIFactory.AlignMidLeft,sizeDelta:new Vector2(96,20));row.txtCards=UIFactory.CreateText("c",row.root.transform,"",19f,new Color(0.6f,0.7f,0.9f),sizeDelta:new Vector2(900,25));UIFactory.SetCharSpacing(row.txtCards,1.5f);row.txtOppCards=UIFactory.CreateText("oc",row.root.transform,"",19f,new Color(0.9f,0.6f,0.5f),sizeDelta:new Vector2(900,25));UIFactory.SetCharSpacing(row.txtOppCards,1.5f);row.root.SetActive(false);return row;}

        private static object txtLBPlayerName;
        private static GameObject BuildLeaderboardTab(Transform parent){var panel=new GameObject("Leaderboard");panel.transform.SetParent(parent,false);panel.AddComponent<RectTransform>();UIFactory.AddHLG(panel,spacing:6);UIFactory.AddLE(panel,flexH:1);/* === LEFT: Recent Ranked Series === */var seriesCol=UIFactory.CreatePanel("LBSeries",panel.transform,C_PANEL);UIFactory.AddVLG(seriesCol,spacing:2,padL:8,padR:8,padT:6,padB:6);/* Round 7: both SIDE panels carry identical prefW 400 + flexW 1 so the leftover splits evenly and the fixed-width table column sits in the TRUE screen center (sub-tabs anchor inside it and center with it). The flex value being EXPLICIT is still load-bearing — see learning #132. */UIFactory.AddLE(seriesCol,prefW:400,minW:340,flexW:1,flexH:1);txtLiveHeader=UIFactory.CreateText("RSL",seriesCol.transform,"<color=#FF6688>* Live Ranked Games</color>",17f,C_WHITE,UIFactory.AlignMidLeft,sizeDelta:new Vector2(280,26));txtLiveSeries=UIFactory.CreateText("LIVE",seriesCol.transform,"<color=#666><i>No live games right now.</i></color>",13f,C_WHITE,UIFactory.AlignTopLeft,sizeDelta:new Vector2(280,24));UIFactory.SetWordWrap(txtLiveSeries,true);liveBetsContainer=new GameObject("LiveBets");liveBetsContainer.transform.SetParent(seriesCol.transform,false);liveBetsContainer.AddComponent<RectTransform>();UIFactory.AddVLG(liveBetsContainer,spacing:2);/* No LayoutElement: VLG on this container already sums child preferred heights with priority 0 and reports that as its preferred height, so the parent VLG sizes us correctly. Previously an LE with prefH:0 priority:1 was overriding that sum to 0, collapsing the live series into the recent series list below. */
/* Live-series pagination header row - shows "X live (page N/M) < >" when >5 series. */
liveBetsPager=new GameObject("LivePg");liveBetsPager.transform.SetParent(seriesCol.transform,false);liveBetsPager.AddComponent<RectTransform>();UIFactory.AddHLG(liveBetsPager,spacing:4,forceExpandH:true);UIFactory.AddLE(liveBetsPager,prefH:18,flexH:0);
liveBetsPrev=UIFactory.CreateButton("lvP",liveBetsPager.transform,"< Prev",10f,C_LABEL,C_BTN,()=>{if(liveSeriesPage>0){liveSeriesPage--;dirty=true;}},sizeDelta:new Vector2(50,18));
txtLiveBetsPage=UIFactory.CreateText("lvPI",liveBetsPager.transform,"",10f,C_LABEL,UIFactory.AlignMidCenter,sizeDelta:new Vector2(80,18));
liveBetsNext=UIFactory.CreateButton("lvN",liveBetsPager.transform,"Next >",10f,C_LABEL,C_BTN,()=>{liveSeriesPage++;dirty=true;},sizeDelta:new Vector2(50,18));
/* Your-bets ledger (v1.30, bug #53): pending bets + the last few settled ones,
 * INCLUDING refunds — Discord-placed bets land here too (same bets table), so
 * "did my bet register / what happened to it" is finally answerable in-game.
 * Refunds render explicitly instead of being silently hidden (learning #107
 * excludes them from win/loss RESULT lists; a personal ledger names them). */
txtMyBets=UIFactory.CreateText("MYBETS",seriesCol.transform,"",15f,C_WHITE,UIFactory.AlignTopLeft,sizeDelta:new Vector2(380,20));
UIFactory.SetWordWrap(txtMyBets,true);UIFactory.SetTextAutoHeight(txtMyBets);UIFactory.SetBold(txtMyBets,true);
liveBetsPager.SetActive(false);
/* Visual spacer between Live and Recent panels - was visually jammed previously. */
{var liveRecentSpacer=new GameObject("LRSp");liveRecentSpacer.transform.SetParent(seriesCol.transform,false);liveRecentSpacer.AddComponent<RectTransform>();UIFactory.AddLE(liveRecentSpacer,prefH:18,minH:18,flexH:0);}
UIFactory.CreateText("RSL",seriesCol.transform,"<color=#99AAEE>Recent Ranked Series</color>",17f,C_WHITE,UIFactory.AlignMidLeft,sizeDelta:new Vector2(280,26));var rsSV=UIFactory.CreateScrollView("RSSV",seriesCol.transform,spacing:1);UIFactory.AddLE(rsSV.scrollGO,flexH:1);txtRecentSeries=UIFactory.CreateText("RST",rsSV.content.transform,"Loading...",16f,C_DIM,sizeDelta:new Vector2(380,20));/* Round 5 item 1: no wrap — names are truncated to fit and residue clips at the mask. */UIFactory.SetWordWrap(txtRecentSeries,false);UIFactory.SetTextAutoHeight(txtRecentSeries);var sPg=new GameObject("SPg");sPg.transform.SetParent(seriesCol.transform,false);sPg.AddComponent<RectTransform>();UIFactory.AddHLG(sPg,spacing:4,forceExpandH:true);UIFactory.AddLE(sPg,prefH:20,flexH:0);var sS1=new GameObject("S");sS1.transform.SetParent(sPg.transform,false);sS1.AddComponent<RectTransform>();UIFactory.AddLE(sS1,flexW:1);seriesPrev=UIFactory.CreateButton("sP",sPg.transform,"< Prev",10f,C_LABEL,C_BTN,()=>{if(recentSeriesPage>0){recentSeriesPage--;dirty=true;}},sizeDelta:new Vector2(50,18));txtSeriesPage=UIFactory.CreateText("sPI",sPg.transform,"",10f,C_LABEL,UIFactory.AlignMidCenter,sizeDelta:new Vector2(35,18));seriesNext=UIFactory.CreateButton("sN",sPg.transform,"Next >",10f,C_LABEL,C_BTN,()=>{recentSeriesPage++;dirty=true;},sizeDelta:new Vector2(50,18));var sS2=new GameObject("S");sS2.transform.SetParent(sPg.transform,false);sS2.AddComponent<RectTransform>();UIFactory.AddLE(sS2,flexW:1);/* === MIDDLE: Leaderboard list === */var mid=new GameObject("LBMid");mid.transform.SetParent(panel.transform,false);mid.AddComponent<RectTransform>();UIFactory.AddVLG(mid,spacing:2);/* Round 5 item 2 + round 6: width = exactly the table (768) + slack. flexW:0 is LOAD-BEARING — the pager row's internal flexW:1 spacers otherwise bubble up as the column's flexible width (layout groups inherit max child flex), stretching it ~100px past the table: that WAS the dead wheel-scroll strip beyond Gold, and it dragged the anchored sub-tabs off the table's center. */UIFactory.AddLE(mid,prefW:772,minW:620,flexW:0,flexH:1);/* Round 5 item 3: sub-tabs live at the TOP OF THIS COLUMN — the side panels keep full height. */MakeSubTabAnchor(1,mid.transform,true);/* July 22 item 8: search row under the sub-tabs — IMGUI field drawn over the empty anchor (CompetitiveUI.DrawLeaderboardSearch), focus-mutexed vs T-chat. No flexW:1 spacers here (learning #132 — this column's flexW:0 is load-bearing). */var lbSr=new GameObject("LBSearch");lbSr.transform.SetParent(mid.transform,false);lbSr.AddComponent<RectTransform>();UIFactory.AddHLG(lbSr,spacing:6);UIFactory.AddLE(lbSr,prefH:24,flexH:0,flexW:0);UIFactory.CreateText("LBSc",lbSr.transform,"<color=#8899AA>Search</color>",13f,C_LABEL,UIFactory.AlignMidLeft,sizeDelta:new Vector2(52,22));lbSearchField=UIFactory.CreateText("LBSLbl",lbSr.transform,"",13f,C_WHITE,UIFactory.AlignMidLeft,sizeDelta:new Vector2(240,22));UIFactory.CreateButton("LBSClr",lbSr.transform,"Clear",11f,C_LABEL,new Color(0.25f,0.3f,0.4f,0.9f),()=>{lbSearch="";dirty=true;},sizeDelta:new Vector2(48,20));string[]hL={"#","Lv","Player","Rating","W","L","W/L","Gold"};string[]hK={"rank","level","display_name","rating","wins","losses","wl_ratio","gold"};var hRow=new GameObject("LBH");hRow.transform.SetParent(mid.transform,false);hRow.AddComponent<RectTransform>();UIFactory.AddHLG(hRow,spacing:2,forceExpandH:true);UIFactory.AddLE(hRow,prefH:28,minH:28,flexH:0);lbSortTexts=new object[hL.Length];lbSortBtns=new GameObject[hL.Length];/* Round 4 item 4: no centering spacers — table fills the column flush-left. */for(int hi=0;hi<hL.Length;hi++){int idx=hi;string arrow=lbSort==hK[hi]?(lbSortDesc?" v":" ^"):"";var hBtn=UIFactory.CreateButton($"LH{hi}",hRow.transform,hL[hi]+arrow,14f,lbSort==hK[hi]?C_WHITE:C_LABEL,lbSort==hK[hi]?C_TABACT:C_TAB,()=>{if(lbSort==hK[idx])lbSortDesc=!lbSortDesc;else{lbSort=hK[idx];lbSortDesc=(idx>=3);}dirty=true;},sizeDelta:new Vector2(LB_COL_W[hi],22));if(UIFactory.tLE!=null){var el=hBtn.GetComponent(UIFactory.tLE);if(el!=null)UnityEngine.Object.Destroy(el as UnityEngine.Object);}UIFactory.AddLE(hBtn,prefW:LB_COL_W[hi],prefH:22,flexH:0);lbSortBtns[hi]=hBtn;lbSortTexts[hi]=UIFactory.GetButtonText(hBtn);}var sv=UIFactory.CreateScrollView("LBSV",mid.transform);UIFactory.AddLE(sv.scrollGO,flexH:1);for(int i=0;i<100;i++)lbRows.Add(CreateLBRow(sv.content.transform,$"lb{i}",i));var lbPg=new GameObject("LBPg");lbPg.transform.SetParent(mid.transform,false);lbPg.AddComponent<RectTransform>();UIFactory.AddHLG(lbPg,spacing:6,forceExpandH:true);UIFactory.AddLE(lbPg,prefH:24,flexH:0);txtLBCount=UIFactory.CreateText("LBC",lbPg.transform,"",15f,C_LABEL,sizeDelta:new Vector2(160,22));var lbS1=new GameObject("S");lbS1.transform.SetParent(lbPg.transform,false);lbS1.AddComponent<RectTransform>();UIFactory.AddLE(lbS1,flexW:1);lbPrev=UIFactory.CreateButton("lbP",lbPg.transform,"< Prev",13f,C_LABEL,C_BTN,()=>{if(lbPage>0){lbPage--;dirty=true;}},sizeDelta:new Vector2(60,22));txtLBPage=UIFactory.CreateText("lbPI",lbPg.transform,"",13f,C_LABEL,UIFactory.AlignMidCenter,sizeDelta:new Vector2(40,22));lbNext=UIFactory.CreateButton("lbN",lbPg.transform,"Next >",13f,C_LABEL,C_BTN,()=>{lbPage++;dirty=true;},sizeDelta:new Vector2(60,22));/* === RIGHT: Player detail === */var right=UIFactory.CreatePanel("LBR",panel.transform,C_PANEL);UIFactory.AddVLG(right,spacing:4,padL:12,padR:12,padT:8,padB:8);/* prefW mirrors the LEFT column so the table centers (round 7). */UIFactory.AddLE(right,prefW:400,flexW:1,flexH:1);txtLBPlayerName=UIFactory.CreateText("LBName",right.transform,"Click a player",20f,C_WHITE,UIFactory.AlignMidLeft,sizeDelta:new Vector2(340,26));UIFactory.SetBold(txtLBPlayerName,true);lbGraphPanel=new GameObject("Graph");lbGraphPanel.transform.SetParent(right.transform,false);var grt=lbGraphPanel.AddComponent<RectTransform>();UIFactory.AddLE(lbGraphPanel,prefH:110,minH:110,flexH:0);/* Add mask to clip graph bars within bounds */var gMaskImg=lbGraphPanel.AddComponent(UIFactory.tImage);UIFactory.tImage.GetProperty("color",BindingFlags.Public|BindingFlags.Instance)?.SetValue(gMaskImg,new Color(0,0,0,0.01f));if(UIFactory.tMask!=null){var gMask=lbGraphPanel.AddComponent(UIFactory.tMask);try{UIFactory.tMask.GetProperty("showMaskGraphic",BindingFlags.Public|BindingFlags.Instance)?.SetValue(gMask,false);}catch{}}lbGraphPanel.SetActive(false);
var lbDetailSV=UIFactory.CreateScrollView("LBDSV",right.transform,spacing:0);UIFactory.AddLE(lbDetailSV.scrollGO,flexH:1);txtLBDetail=UIFactory.CreateText("LBD",lbDetailSV.content.transform,"",16f,C_DIM,sizeDelta:new Vector2(340,24));UIFactory.SetTextAutoHeight(txtLBDetail);
/* H2H series pager (item 10 rework) — the "Series vs You" pager used to be parented to
 * the right column ABOVE the detail scroll view, so it floated at the top of the panel
 * while the series list it pages sat way down inside the scrolled text. It now lives
 * INSIDE the scroll content, directly after the detail text — and BuildViewHistoryText
 * output is composed LAST in RefreshLeaderboard so the pager renders immediately under
 * the series rows it controls. Bigger + bold per Sid. */
/* July 12 round 3 (screenshot markup): the pager sits DIRECTLY under the
 * Ranked-Series-vs-You section — the detail text is split into two elements
 * (txtLBDetail = stats + series-vs-you, txtLBDetailB = ranked history+) with
 * the pager between them. The redundant "Series vs You" label is gone (the
 * section header right above it already says it); buttons centered. */
h2hPager=new GameObject("H2HPg");h2hPager.transform.SetParent(lbDetailSV.content.transform,false);h2hPager.AddComponent<RectTransform>();UIFactory.AddHLG(h2hPager,spacing:6,forceExpandH:true);UIFactory.AddLE(h2hPager,prefH:26,flexH:0);var h2hSpL=new GameObject("S");h2hSpL.transform.SetParent(h2hPager.transform,false);h2hSpL.AddComponent<RectTransform>();UIFactory.AddLE(h2hSpL,flexW:1);h2hPrev=UIFactory.CreateButton("h2hP",h2hPager.transform,"< Newer",13f,C_LABEL,C_BTN,()=>{if(h2hSeriesPage>0){h2hSeriesPage--;dirty=true;}},sizeDelta:new Vector2(78,24));UIFactory.SetBold(UIFactory.GetButtonText(h2hPrev),true);txtH2hPage=UIFactory.CreateText("h2hI",h2hPager.transform,"",13f,C_LABEL,UIFactory.AlignMidCenter,sizeDelta:new Vector2(46,24));UIFactory.SetBold(txtH2hPage,true);h2hNext=UIFactory.CreateButton("h2hN",h2hPager.transform,"Older >",13f,C_LABEL,C_BTN,()=>{h2hSeriesPage++;dirty=true;},sizeDelta:new Vector2(78,24));UIFactory.SetBold(UIFactory.GetButtonText(h2hNext),true);var h2hSpR=new GameObject("S");h2hSpR.transform.SetParent(h2hPager.transform,false);h2hSpR.AddComponent<RectTransform>();UIFactory.AddLE(h2hSpR,flexW:1);h2hPager.SetActive(false);
txtLBDetailB=UIFactory.CreateText("LBDB",lbDetailSV.content.transform,"",16f,C_DIM,sizeDelta:new Vector2(340,24));UIFactory.SetTextAutoHeight(txtLBDetailB);UIFactory.SetWordWrap(txtLBDetailB,true);
/* Achievements live in their OWN text element AFTER the pager (Sid July 12 item 5):
 * scroll order = stats detail + Series-vs-You (txtLBDetail) -> pager -> achievements.
 * The pager therefore sits directly under the series list, and achievements sink to
 * the bottom where they stop crowding the important stats. */
txtLBAch=UIFactory.CreateText("LBDAch",lbDetailSV.content.transform,"",16f,C_DIM,sizeDelta:new Vector2(340,24));UIFactory.SetTextAutoHeight(txtLBAch);UIFactory.SetWordWrap(txtLBAch,true);
/* Enable word wrap on the detail text so TMP reports a preferredHeight that
   matches the rendered multi-line content. Without this, TMP reports the
   sizeDelta height (24 px) and the ContentSizeFitter on the scroll content
   sizes the scrollable area to ~24 px regardless of how many achievements
   are rendered → the bottom of the achievement list gets clipped and the
   scroll can't reach it. With wrap on, TMP computes proper line count from
   the 340 px-wide text box and the scroll content sizes correctly. */
UIFactory.SetWordWrap(txtLBDetail, true);
UIFactory.CreateText("LBDScrollHint",right.transform,"<color=#777><i>scroll for full history — hover + mouse wheel</i></color>",11f,C_DIM,UIFactory.AlignMidCenter,sizeDelta:new Vector2(340,15));
lbBlockRow=new GameObject("BlockRow");lbBlockRow.transform.SetParent(right.transform,false);lbBlockRow.AddComponent<RectTransform>();UIFactory.AddHLG(lbBlockRow,spacing:0);UIFactory.AddLE(lbBlockRow,prefH:28,minH:28,flexH:0);lbBlockBtn=UIFactory.CreateButton("LBBlock",lbBlockRow.transform,"Block from Ranked",14f,C_WHITE,new Color(0.5f,0.15f,0.15f,0.9f),()=>{if(string.IsNullOrEmpty(selectedSteamId)||selectedSteamId==MatchTracker.LocalSteamId)return;string myId=MatchTracker.LocalSteamId;if(ApiClient.IsPlayerBlocked(selectedSteamId))ApiClient.UnblockPlayer(myId,selectedSteamId);else ApiClient.BlockPlayer(myId,selectedSteamId);},sizeDelta:new Vector2(160,24));var lbBlockSpacer=new GameObject("S");lbBlockSpacer.transform.SetParent(lbBlockRow.transform,false);lbBlockSpacer.AddComponent<RectTransform>();UIFactory.AddLE(lbBlockSpacer,flexW:1);lbBlockBtn.SetActive(true);lbBlockRow.SetActive(false);lbBlockTxt=UIFactory.GetButtonText(lbBlockBtn);
        /* July 17 round 3 (Sid item 10): admin-only Steam ID row, click-to-
         * copy (first systemCopyBuffer use in the mod — plain IMGUIModule
         * API, no reflection needed). Visibility handled in RefreshLeaderboard
         * (IsAdmin resolves async — late-resolution pattern, see tab-bar). */
        txtLBSteamId=UIFactory.CreateText("LBSid",right.transform,"",13f,C_DIM,UIFactory.AlignMidLeft,sizeDelta:new Vector2(340,18),raycastTarget:true);
        {var sidComp=txtLBSteamId as Component;if(sidComp!=null){var sch=sidComp.gameObject.AddComponent<ClickHandler>();sch.onClick=()=>{if(ClickGuard.Claim(sidComp.gameObject)&&!string.IsNullOrEmpty(selectedSteamId)){GUIUtility.systemCopyBuffer=selectedSteamId;CompetitiveUI.ShowNotification("Steam ID copied to clipboard",new Color(0.6f,0.9f,1f));}};}}
        ((Component)txtLBSteamId).gameObject.SetActive(false);
        return panel;}

        private static LBRow CreateLBRow(Transform parent,string name,int rowIndex){var row=new LBRow();row.root=new GameObject(name);row.root.transform.SetParent(parent,false);row.root.AddComponent<RectTransform>();UIFactory.AddHLG(row.root,spacing:0,forceExpandH:true);UIFactory.AddLE(row.root,prefH:28);/* Round 4 item 4: no centering spacers — rows align flush with the header. */row.hlWrap=new GameObject("W");row.hlWrap.transform.SetParent(row.root.transform,false);row.hlWrap.AddComponent<RectTransform>();UIFactory.AddHLG(row.hlWrap,spacing:2,forceExpandH:true);if(UIFactory.tImage!=null){var img=row.hlWrap.AddComponent(UIFactory.tImage);UIFactory.tImage.GetProperty("color",BindingFlags.Public|BindingFlags.Instance)?.SetValue(img,new Color(0.15f,0.15f,0.2f,0.01f));UIFactory.tImage.GetProperty("raycastTarget",BindingFlags.Public|BindingFlags.Instance)?.SetValue(img,true);}row.txtRank=UIFactory.CreateText("r",row.hlWrap.transform,"",15f,C_GOLD,UIFactory.AlignMidCenter,sizeDelta:new Vector2(LB_COL_W[0],25));row.txtLv=UIFactory.CreateText("l",row.hlWrap.transform,"",15f,C_BLUE,UIFactory.AlignMidCenter,sizeDelta:new Vector2(LB_COL_W[1],25));row.txtName=UIFactory.CreateText("n",row.hlWrap.transform,"",16f,C_WHITE,UIFactory.AlignMidLeft,sizeDelta:new Vector2(LB_COL_W[2],25));row.txtRating=UIFactory.CreateText("rt",row.hlWrap.transform,"",16f,C_WHITE,UIFactory.AlignMidCenter,sizeDelta:new Vector2(LB_COL_W[3],25));UIFactory.SetBold(row.txtRating,true);row.txtW=UIFactory.CreateText("w",row.hlWrap.transform,"",15f,C_GREEN,UIFactory.AlignMidCenter,sizeDelta:new Vector2(LB_COL_W[4],25));row.txtL=UIFactory.CreateText("ls",row.hlWrap.transform,"",15f,C_RED,UIFactory.AlignMidCenter,sizeDelta:new Vector2(LB_COL_W[5],25));row.txtWL=UIFactory.CreateText("wl",row.hlWrap.transform,"",15f,C_LABEL,UIFactory.AlignMidCenter,sizeDelta:new Vector2(LB_COL_W[6],25));row.txtGold=UIFactory.CreateText("gd",row.hlWrap.transform,"",15f,C_GOLD,UIFactory.AlignMidCenter,sizeDelta:new Vector2(LB_COL_W[7],25));UIFactory.SetBold(row.txtGold,true);int idx=rowIndex;var ch=row.root.AddComponent<ClickHandler>();ch.onClick=()=>{if(ClickGuard.Claim()&&idx>=0&&idx<lbRows.Count&&!string.IsNullOrEmpty(lbRows[idx].steamId)){string sid=lbRows[idx].steamId;h2hSeriesPage=0;if(selectedSteamId==sid){selectedSteamId="";selectedStats=null;selectedViewHistory=null;}else{selectedSteamId=sid;selectedStats=null;selectedViewHistory=null;ApiClient.FetchPlayerStatsForView(sid,(d)=>{selectedStats=d;dirty=true;});ApiClient.FetchAchievementsForView(sid);ApiClient.FetchPlayerTournaments(sid);ApiClient.FetchMatchHistoryForView(sid,(h)=>{if(selectedSteamId==sid){selectedViewHistory=h;dirty=true;}});}dirty=true;}};row.root.SetActive(false);return row;}

        private static GameObject BuildCardStatsTab(Transform parent){var panel=new GameObject("CardStats");panel.transform.SetParent(parent,false);panel.AddComponent<RectTransform>();UIFactory.AddVLG(panel,spacing:4);UIFactory.AddLE(panel,flexH:1);/* v1.33 item 4: Card Stats is a My Stats sub-tab — anchor row up top (the
        panel is an unpadded VLG, so the bar lands at the standard position). */MakeSubTabAnchor(2,panel.transform,true);var fBar=new GameObject("Filt");fBar.transform.SetParent(panel.transform,false);fBar.AddComponent<RectTransform>();UIFactory.AddHLG(fBar,spacing:4,padL:12,forceExpandH:true);UIFactory.AddLE(fBar,prefH:34,minH:34,flexH:0);
        // Export Tier List button on the LEFT of the filter row (was its own
        // row — tester asked to move card list up). Filter buttons still
        // center under the data columns via flex spacers.
        var expBtnInline=UIFactory.CreateButton("ExpBtn",fBar.transform,"Export Tier List",16f,C_WHITE,new Color(0.20f,0.55f,0.30f,0.95f),
            ()=>{ ExportCardTierList(); }, sizeDelta:new Vector2(180,30));
        UIFactory.SetBold(UIFactory.GetButtonText(expBtnInline),true);
        if(UIFactory.tLE!=null){var el=expBtnInline.GetComponent(UIFactory.tLE);if(el!=null)UnityEngine.Object.Destroy(el as UnityEngine.Object);}
        UIFactory.AddLE(expBtnInline,prefW:180,minW:180,prefH:30,minH:30,flexH:0,flexW:0);
        // Open Tier List Folder sits RIGHT BESIDE Export (Sid July 12 item 4 —
        // it originally landed on the far right of the row). Opens the export
        // directory (<ROUNDS>\CompetitiveRoundsTierLists) in Explorer.
        var openFolderBtn=UIFactory.CreateButton("ExpDir",fBar.transform,"Open Tier List Folder",14f,C_WHITE,new Color(0.25f,0.35f,0.55f,0.95f),()=>{
            try{
                string dir;
                try{dir=System.IO.Path.GetFullPath(System.IO.Path.Combine(Application.dataPath,"..","CompetitiveRoundsTierLists"));System.IO.Directory.CreateDirectory(dir);}
                catch{dir=Application.persistentDataPath;}
                Application.OpenURL("file:///"+dir.Replace('\\','/'));
                CompetitiveUI.ShowNotification($"Tier lists live in {dir}",new Color(0.6f,0.8f,1f),8f);
            }catch(Exception ex){Plugin.Log.LogWarning($"[TIER-EXPORT] open folder: {ex.Message}");}
        },sizeDelta:new Vector2(180,30));
        if(UIFactory.tLE!=null){var ofEl=openFolderBtn.GetComponent(UIFactory.tLE);if(ofEl!=null)UnityEngine.Object.Destroy(ofEl as UnityEngine.Object);}
        UIFactory.AddLE(openFolderBtn,prefW:180,minW:180,prefH:30,minH:30,flexH:0,flexW:0);UIFactory.SetBold(UIFactory.GetButtonText(openFolderBtn),true);
        var fSp1=new GameObject("S");fSp1.transform.SetParent(fBar.transform,false);fSp1.AddComponent<RectTransform>();UIFactory.AddLE(fSp1,flexW:1);string[]fN={"All","Ranked","Casual"};cardFilterBtns=new GameObject[3];cardFilterTexts=new object[3];
        // Filter buttons sized to share the same total span as the data
        // columns below them (Tier→Pass% sum from CS_COL_W). 3 buttons, no
        // flex, fixed prefW each. Mirrors the data row's flex-spacer pattern
        // so they line up visually.
        float CS_TOTAL_W=0f; for(int ci=0;ci<CS_COL_W.Length;ci++) CS_TOTAL_W+=CS_COL_W[ci];
        float perFilterW=Mathf.Floor((CS_TOTAL_W-2f*2f)/3f); // 2 = HLG spacing
        for(int i=0;i<3;i++){int idx=i;var btn=UIFactory.CreateButton($"F{i}",fBar.transform,fN[i],18f,C_LABEL,i==0?C_TABACT:C_TAB,()=>{cardFilter=idx;string r=idx==1?"true":idx==2?"false":null;ApiClient.FetchCardStats(200,MatchTracker.LocalSteamId,"times_picked",r);LoadCardTiersForCurrentFilter();for(int fi=0;fi<3;fi++){UIFactory.SetImageColor(cardFilterBtns[fi],fi==idx?C_TABACT:C_TAB);if(cardFilterTexts[fi]!=null){UIFactory.SetColor(cardFilterTexts[fi],fi==idx?C_WHITE:C_LABEL);UIFactory.SetBold(cardFilterTexts[fi],fi==idx);}}dirty=true;},sizeDelta:new Vector2(perFilterW,30));if(UIFactory.tLE!=null){var el=btn.GetComponent(UIFactory.tLE);if(el!=null)UnityEngine.Object.Destroy(el as UnityEngine.Object);}UIFactory.AddLE(btn,prefW:perFilterW,minW:perFilterW,prefH:30,minH:30,flexH:0,flexW:0);UIFactory.SetBold(UIFactory.GetButtonText(btn),true);cardFilterBtns[i]=btn;cardFilterTexts[i]=UIFactory.GetButtonText(btn);}var fSp2=new GameObject("S");fSp2.transform.SetParent(fBar.transform,false);fSp2.AddComponent<RectTransform>();UIFactory.AddLE(fSp2,flexW:1);
        // Right-side balance spacer = the two left buttons' width (2x180 + 4
        // spacing) so the filter buttons stay centered above the data columns.
        var fBalance=new GameObject("FBal");fBalance.transform.SetParent(fBar.transform,false);fBalance.AddComponent<RectTransform>();UIFactory.AddLE(fBalance,prefW:364,minW:364,flexW:0);
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

        // Filters (0=All,1=Ranked,2=Casual) whose tier fetch has COMPLETED this
        // session. Lets RefreshCardStats tell "tiers legitimately empty" apart
        // from "fetch never landed" (failed / raced the panel build) so it can
        // self-heal instead of showing blank tiers until a manual Refresh (#32).
        private static readonly HashSet<int> _tierFiltersLoaded = new HashSet<int>();
        private static float _tierAutoFetchAt = -999f;
        private static float _seriesAutoFetchAt = -999f;
        private static float _cardStatsAutoFetchAt = -999f;

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
                _tierFiltersLoaded.Add(filterIdx);
                dirty = true;
            });
        }

        // Cycle one card's tier and write through to the server. Filter is
        // tied to the current cardFilter index (0=All,1=Ranked,2=Casual).
        // -- Achievements Tab ------------------------------------
        // July 21 item 7: sortable (rarity / gold / date), gold visible on
        // LOCKED rows too, and rows are clickable — a click loads the list of
        // players who earned that achievement (sorted by current 1v1 elo).
        private static string achSort = "default";
        private static bool achSortDesc = false;   // re-click the active sort to flip direction
        private static string achSelectedKey = null;
        // July 22 item 4: earner-list pagination (20 per page).
        private static int achEarnersPage = 0;
        private static GameObject achEarnPager, achEarnPrev, achEarnNext;
        private static object txtAchEarnPage;
        private static GameObject achSortDefBtn, achSortRarBtn, achSortGoldBtn, achSortDateBtn;
        private static object achEarnersHdr, achEarnersBody;
        private static GameObject achEarnersPanel, achEarnersStash;
        private static GameObject BuildAchievementsTab(Transform parent){/* v1.33 item 4: Achievements is a My Stats sub-tab. Unpadded outer carries
        the anchor (the panel itself is padded, which would offset the bar). */
        var achOuter=new GameObject("AchOuter");achOuter.transform.SetParent(parent,false);achOuter.AddComponent<RectTransform>();UIFactory.AddVLG(achOuter,spacing:0);UIFactory.AddLE(achOuter,flexH:1);MakeSubTabAnchor(3,achOuter.transform,true);
        var panel=new GameObject("Achievements");panel.transform.SetParent(achOuter.transform,false);panel.AddComponent<RectTransform>();UIFactory.AddVLG(panel,spacing:6,padL:20,padR:20,padT:10);UIFactory.AddLE(panel,flexH:1);UIFactory.CreateText("AchH",panel.transform,"Achievements",22f,C_GOLD,UIFactory.AlignTopCenter,sizeDelta:new Vector2(600,30));var countRow=new GameObject("AchCnt");countRow.transform.SetParent(panel.transform,false);countRow.AddComponent<RectTransform>();UIFactory.AddLE(countRow,prefH:22);txtAchCount=UIFactory.CreateText("AC",countRow.transform,"",15f,C_DIM,UIFactory.AlignMidCenter,sizeDelta:new Vector2(400,22));
        // Sort bar (Card Stats header pattern).
        var sortRow=new GameObject("AchSort");sortRow.transform.SetParent(panel.transform,false);sortRow.AddComponent<RectTransform>();UIFactory.AddHLG(sortRow,spacing:6);UIFactory.AddLE(sortRow,prefH:24,flexH:0);
        UIFactory.CreateText("AchSortL",sortRow.transform,"Sort:",14f,C_DIM,UIFactory.AlignMidLeft,sizeDelta:new Vector2(46,22));
        achSortDefBtn=UIFactory.CreateButton("AchSD",sortRow.transform,"Default",12f,C_WHITE,C_BTN,()=>{achSort="default";achSortDesc=false;dirty=true;},sizeDelta:new Vector2(72,22));
        achSortRarBtn=UIFactory.CreateButton("AchSR",sortRow.transform,"Rarity",12f,C_WHITE,C_BTN,()=>{if(achSort=="rarity")achSortDesc=!achSortDesc;else{achSort="rarity";achSortDesc=false;}dirty=true;},sizeDelta:new Vector2(72,22));
        achSortGoldBtn=UIFactory.CreateButton("AchSG",sortRow.transform,"Gold",12f,C_WHITE,C_BTN,()=>{if(achSort=="gold")achSortDesc=!achSortDesc;else{achSort="gold";achSortDesc=false;}dirty=true;},sizeDelta:new Vector2(72,22));
        achSortDateBtn=UIFactory.CreateButton("AchSDt",sortRow.transform,"Date earned",12f,C_WHITE,C_BTN,()=>{if(achSort=="date")achSortDesc=!achSortDesc;else{achSort="date";achSortDesc=false;}dirty=true;},sizeDelta:new Vector2(100,22));
        UIFactory.CreateText("AchClickHint",sortRow.transform,"<color=#667>click an achievement to see who earned it</color>",12f,C_DIM,UIFactory.AlignMidLeft,sizeDelta:new Vector2(320,22));
        var sv=UIFactory.CreateScrollView("AchSV",panel.transform,spacing:4);UIFactory.AddLE(sv.scrollGO,flexH:1);achRows.Clear();int _achIdx=0;foreach(var kvp in ApiClient.AchievementDefs){var row=new AchRow();string key=kvp.Key;string[]def=kvp.Value;row.key=key;
        /* July 22 item 1: each row is a VLG WRAPPER (root, auto-height) holding the
         * clickable HLG strip (main). The shared earners panel re-parents under the
         * clicked row's wrapper, so the expansion appears inline right below it. */
        row.root=new GameObject($"ach_{key}");row.root.transform.SetParent(sv.content.transform,false);row.root.AddComponent<RectTransform>();UIFactory.AddVLG(row.root,spacing:2);
        row.main=new GameObject("main");row.main.transform.SetParent(row.root.transform,false);row.main.AddComponent<RectTransform>();UIFactory.AddHLG(row.main,spacing:10,padL:8,padR:8,padT:6,padB:6,forceExpandH:true);UIFactory.AddLE(row.main,prefH:50,flexH:0);if(UIFactory.tImage!=null){var img=row.main.AddComponent(UIFactory.tImage);UIFactory.tImage.GetProperty("color",BindingFlags.Public|BindingFlags.Instance)?.SetValue(img,C_PANEL);}
        row.txtIcon=UIFactory.CreateText("ic",row.main.transform,"",24f,C_DIM,UIFactory.AlignMidCenter,sizeDelta:new Vector2(36,40));var infoCol=new GameObject("Info");infoCol.transform.SetParent(row.main.transform,false);infoCol.AddComponent<RectTransform>();UIFactory.AddVLG(infoCol,spacing:1);UIFactory.AddLE(infoCol,flexW:1);row.txtName=UIFactory.CreateText("nm",infoCol.transform,def[0],17f,C_WHITE,UIFactory.AlignMidLeft,sizeDelta:new Vector2(500,22));row.txtDesc=UIFactory.CreateText("ds",infoCol.transform,def[1],14f,C_LABEL,UIFactory.AlignMidLeft,sizeDelta:new Vector2(500,20));row.txtDate=UIFactory.CreateText("dt",row.main.transform,"",13f,C_DIM,UIFactory.AlignMidRight,sizeDelta:new Vector2(180,40));
        /* Rows are re-filled in sorted order, so the click handler reads the row's
         * CURRENT key — never the build-time capture. */
        int _ci=_achIdx;UIFactory.AddClick(row.main,()=>OnAchievementRowClicked(_ci));
        row.root.SetActive(true);achRows.Add(row);_achIdx++;}
        /* Shared inline earners panel — ONE instance, re-parented under the clicked
         * row at refresh (stash keeps it alive while nothing is selected). Fixed
         * prefH (learning #63: no flexH inside a scroll region). */
        achEarnersStash=new GameObject("AchEarnStash");achEarnersStash.transform.SetParent(panel.transform,false);achEarnersStash.AddComponent<RectTransform>();UIFactory.AddLE(achEarnersStash,prefH:0,minH:0,flexH:0);
        /* July 22 item 4: minH dropped 96 -> 34 so a 0-1 earner list doesn't
         * reserve a giant blank box; RefreshAchievements SetPrefH's the panel
         * to fit the page it's actually showing (20 earners max + pager). */
        achEarnersPanel=UIFactory.CreatePanel("AchEarn",achEarnersStash.transform,new Color(0.10f,0.12f,0.17f,0.95f));UIFactory.AddVLG(achEarnersPanel,spacing:2,padL:14,padR:10,padT:5,padB:5);UIFactory.AddLE(achEarnersPanel,prefH:96,minH:34,flexH:0);
        achEarnersHdr=UIFactory.CreateText("AeH",achEarnersPanel.transform,"",14f,C_GOLD,UIFactory.AlignTopLeft,sizeDelta:new Vector2(900,20));
        var esv=UIFactory.CreateScrollView("AeSV",achEarnersPanel.transform,spacing:0);UIFactory.AddLE(esv.scrollGO,flexH:1);
        achEarnersBody=UIFactory.CreateText("AeB",esv.content.transform,"",13f,C_WHITE,UIFactory.AlignTopLeft,sizeDelta:new Vector2(900,24));UIFactory.SetWordWrap(achEarnersBody,true);
        {var bLE=(achEarnersBody as Component)?.gameObject.GetComponent(UIFactory.tLE);if(bLE!=null)UIFactory.tLE.GetProperty("preferredHeight",BindingFlags.Public|BindingFlags.Instance)?.SetValue(bLE,-1f);}
        /* Pager (first 20, then < N/M > for the rest — v1.25.22 compact style). */
        achEarnPager=new GameObject("AePg");achEarnPager.transform.SetParent(achEarnersPanel.transform,false);achEarnPager.AddComponent<RectTransform>();UIFactory.AddHLG(achEarnPager,spacing:6);UIFactory.AddLE(achEarnPager,prefH:18,flexH:0);
        var aeS1=new GameObject("S");aeS1.transform.SetParent(achEarnPager.transform,false);aeS1.AddComponent<RectTransform>();UIFactory.AddLE(aeS1,flexW:1);
        achEarnPrev=UIFactory.CreateButton("aeP",achEarnPager.transform,"< Prev",10f,C_LABEL,C_BTN,()=>{if(achEarnersPage>0){achEarnersPage--;dirty=true;}},sizeDelta:new Vector2(50,16));
        txtAchEarnPage=UIFactory.CreateText("aePI",achEarnPager.transform,"",10f,C_LABEL,UIFactory.AlignMidCenter,sizeDelta:new Vector2(40,16));
        achEarnNext=UIFactory.CreateButton("aeN",achEarnPager.transform,"Next >",10f,C_LABEL,C_BTN,()=>{achEarnersPage++;dirty=true;},sizeDelta:new Vector2(50,16));
        var aeS2=new GameObject("S2");aeS2.transform.SetParent(achEarnPager.transform,false);aeS2.AddComponent<RectTransform>();UIFactory.AddLE(aeS2,flexW:1);
        achEarnPager.SetActive(false);
        achEarnersPanel.SetActive(false);
        return achOuter;}

        private static void OnAchievementRowClicked(int rowIdx)
        {
            try
            {
                if (rowIdx < 0 || rowIdx >= achRows.Count) return;
                string key = achRows[rowIdx].key;
                if (string.IsNullOrEmpty(key)) return;
                if (achSelectedKey == key) { achSelectedKey = null; dirty = true; return; }  // second click closes
                achSelectedKey = key;
                achEarnersPage = 0;
                ApiClient.FetchAchievementEarners(key);
                dirty = true;
            }
            catch { }
        }

        private static object txtAchCount;
        private static void RefreshAchievements(){var ach=ApiClient.CachedAchievements;int total=ApiClient.AchievementDefs.Count;
            // July 21 item 7: ordered key list per the active sort. Server gold
            // (ach[key].gold) replaces the old client hardcode; fall back to the
            // legacy values when the server hasn't sent gold yet (old server).
            Func<string,int> goldOf=k=>{int g=ach!=null&&ach.ContainsKey(k)?ach[k].gold:0;if(g<=0)g=(k=="regicide"||k=="stan_slayer")?1000:100;return g;};
            Func<string,float> pctOf=k=>ach!=null&&ach.ContainsKey(k)?ach[k].global_pct:0f;
            Func<string,bool> gotOf=k=>ach!=null&&ach.ContainsKey(k)&&ach[k].unlocked;
            Func<string,DateTime> dateOf=k=>{if(gotOf(k)){string ua=ach[k].unlocked_at;if(!string.IsNullOrEmpty(ua)&&ua!="null"){try{return DateTime.Parse(ua);}catch{}}}return DateTime.MinValue;};
            var keys=new List<string>(ApiClient.AchievementDefs.Keys);
            switch(achSort)
            {
                case "rarity":  // rarest first; 0% (uncomputed/never earned) leads
                    keys.Sort((a,b)=>pctOf(a).CompareTo(pctOf(b)));break;
                case "gold":    // biggest reward first
                    keys.Sort((a,b)=>goldOf(b).CompareTo(goldOf(a)));break;
                case "date":    // most recently earned first, locked rows last
                    keys.Sort((a,b)=>dateOf(b).CompareTo(dateOf(a)));break;
            }
            if(achSortDesc&&achSort!="default")keys.Reverse();   // re-click = other direction
            int unlocked=0,i=0;
            foreach(var key in keys){if(i>=achRows.Count)break;var row=achRows[i];string[]def=ApiClient.AchievementDefs[key];row.key=key;bool got=gotOf(key);if(got)unlocked++;
            UIFactory.SetText(row.txtIcon,got?"[X]":"[ ]");UIFactory.SetColor(row.txtIcon,got?C_GOLD:new Color(0.3f,0.3f,0.35f));
            UIFactory.SetText(row.txtName,def[0]);UIFactory.SetColor(row.txtName,got?C_WHITE:C_DIM);
            {float gp=pctOf(key);string ds=def[1];if(gp>0f)ds+=$"  <color=#66AACC>{gp:F1}% of players have this</color>";UIFactory.SetText(row.txtDesc,ds);}
            UIFactory.SetColor(row.txtDesc,got?C_LABEL:new Color(0.4f,0.4f,0.45f));
            /* Gold shows on EVERY row now (item 7: players should see the prize
             * before earning it); date joins it once unlocked. */
            int ag=goldOf(key);string dt=got?"":$"<color=#8a7a4a>+{ag}g</color>";
            if(got){string d="";string ua=ach[key].unlocked_at;if(!string.IsNullOrEmpty(ua)&&ua!="null"){try{d=DateTime.Parse(ua).ToString("M/d/yyyy");}catch{}}dt=$"{d}  <color=#FFD94D>+{ag}g</color>";}
            UIFactory.SetText(row.txtDate,dt);UIFactory.SetColor(row.txtDate,got?C_GREEN:C_DIM);
            /* Selected-row highlight so the earners panel has a visible anchor. */
            try{if(UIFactory.tImage!=null&&row.main!=null){var img=row.main.GetComponent(UIFactory.tImage);UIFactory.tImage.GetProperty("color",BindingFlags.Public|BindingFlags.Instance)?.SetValue(img,key==achSelectedKey?new Color(0.22f,0.25f,0.34f,0.95f):C_PANEL);}}catch{}
            i++;}
            UIFactory.SetText(txtAchCount,$"{unlocked} / {total} unlocked");UIFactory.SetColor(txtAchCount,unlocked==total?C_GOLD:C_LABEL);
            // Sort-button styling.
            try{UIFactory.SetImageColor(achSortDefBtn,achSort=="default"?C_TABACT:C_BTN);UIFactory.SetImageColor(achSortRarBtn,achSort=="rarity"?C_TABACT:C_BTN);UIFactory.SetImageColor(achSortGoldBtn,achSort=="gold"?C_TABACT:C_BTN);UIFactory.SetImageColor(achSortDateBtn,achSort=="date"?C_TABACT:C_BTN);}catch{}
            // Inline earners panel (July 22 item 1): parent it UNDER the selected
            // row's wrapper so it expands in place; server order = who earned it
            // FIRST; each earner shows their displayed title.
            try
            {
                if(achEarnersPanel!=null)
                {
                    bool show=!string.IsNullOrEmpty(achSelectedKey);
                    AchRow selRow=null;
                    if(show)foreach(var r2 in achRows)if(r2.key==achSelectedKey){selRow=r2;break;}
                    var wantParent=(show&&selRow!=null)?selRow.root.transform:achEarnersStash.transform;
                    if(achEarnersPanel.transform.parent!=wantParent){achEarnersPanel.transform.SetParent(wantParent,false);achEarnersPanel.transform.SetAsLastSibling();}
                    achEarnersPanel.SetActive(show&&selRow!=null);
                    if(show&&selRow!=null)
                    {
                        string nm=ApiClient.AchievementDefs.ContainsKey(achSelectedKey)?ApiClient.AchievementDefs[achSelectedKey][0]:achSelectedKey;
                        if(ApiClient.EarnersKey==achSelectedKey&&ApiClient.CachedEarners!=null)
                        {
                            var es=ApiClient.CachedEarners;
                            int totalEarn=Math.Max(ApiClient.CachedEarnersTotal,es.Count);
                            UIFactory.SetText(achEarnersHdr,$"Earned by {totalEarn} player{(totalEarn==1?"":"s")}  <color=#888>(in the order they got it - click again to close)</color>");
                            /* July 22 item 4: 20 per page; box height follows the page. */
                            const int per=20;
                            int totalPages=Math.Max(1,(es.Count+per-1)/per);
                            if(achEarnersPage>totalPages-1)achEarnersPage=totalPages-1;
                            if(achEarnersPage<0)achEarnersPage=0;
                            int shown=1;
                            if(es.Count==0)UIFactory.SetText(achEarnersBody,"<color=#888><i>Nobody has earned this yet. Be the first!</i></color>");
                            else
                            {
                                int start=achEarnersPage*per,end=Math.Min(start+per,es.Count);
                                shown=end-start;
                                var sb=new System.Text.StringBuilder();
                                for(int e=start;e<end;e++)
                                {
                                    var en=es[e];string rt=en.rating>=0?en.rating.ToString():"--";string d="";
                                    if(!string.IsNullOrEmpty(en.unlocked_at)&&en.unlocked_at!="null"){try{d=DateTime.Parse(en.unlocked_at).ToString("M/d/yyyy");}catch{}}
                                    string ttl="";
                                    if(!string.IsNullOrEmpty(en.title)){string tc=string.IsNullOrEmpty(en.title_color)?"#CCCCCC":en.title_color;ttl=$" <b><color={tc}>[{en.title}]</color></b>";}
                                    sb.Append($"<color=#889>{e+1}.</color> {Trunc(en.display_name,24)}{ttl}  <color=#66CCFF>{rt}</color>  <color=#667>{d}</color>\n");
                                }
                                UIFactory.SetText(achEarnersBody,sb.ToString());
                            }
                            bool pag=totalPages>1;
                            if(achEarnPager!=null)achEarnPager.SetActive(pag);
                            if(pag){UIFactory.SetText(txtAchEarnPage,$"{achEarnersPage+1}/{totalPages}");if(achEarnPrev!=null)achEarnPrev.SetActive(achEarnersPage>0);if(achEarnNext!=null)achEarnNext.SetActive(achEarnersPage+1<totalPages);}
                            UIFactory.SetPrefH(achEarnersPanel,Mathf.Clamp(34f+shown*19f+(pag?22f:0f),52f,470f));
                        }
                        else { UIFactory.SetText(achEarnersHdr,"<color=#888>loading earners...</color>"); UIFactory.SetText(achEarnersBody,""); if(achEarnPager!=null)achEarnPager.SetActive(false); UIFactory.SetPrefH(achEarnersPanel,52f); }
                    }
                }
            }
            catch{}
        }

        // -- Artist Tab (v1.30) ----------------------------------
        // Community artists manage their OWN cosmetics: price, stock cap,
        // gifting copies, and blocking specific buyers. Server-gated by
        // artist_users; every mutation is HMAC-signed and audited.
        private class ArtistRow
        {
            public GameObject root;
            public object txtInfo;
            public GameObject priceBtn, stockBtn, giftBtn;
            public GameObject artImgGO; public object artImg;   // item 9: cosmetic art thumbnail
            public string sku, name;
            public int price, stock;
            public bool catalogReady;
        }
        private class ArtistBlockRow
        {
            public GameObject root;
            public object txtInfo;
            public GameObject unblockBtn;
            public string steamId, name;
        }
        private static readonly List<ArtistRow> artistRows = new List<ArtistRow>();
        private static readonly List<ArtistBlockRow> artistBlockRows = new List<ArtistBlockRow>();
        private static GameObject artistItemsContainer, artistBlocksContainer;
        private static object txtArtistStatus, txtArtistSubs, txtArtistSales;
        private static bool cosmeticPlacementLoading;
        private static int cosmeticPlacementLoadTicket;

        private static GameObject BuildArtistTab(Transform parent)
        {
            var panel = new GameObject("Artist");
            panel.transform.SetParent(parent, false);
            panel.AddComponent<RectTransform>();
            UIFactory.AddVLG(panel, spacing: 6, padL: 20, padR: 20, padT: 10, padB: 10);
            UIFactory.AddLE(panel, flexH: 1);
            MakeSubTabAnchor(10, panel.transform, true);  // round 5 item 3

            UIFactory.CreateText("ArtH", panel.transform, "Artist Studio", 22f, C_GOLD,
                UIFactory.AlignTopLeft, sizeDelta: new Vector2(600, 30));
            UIFactory.CreateText("ArtHint", panel.transform,
                "Manage your cosmetics and earn 30% of every sale. Scale/placement changes return to admin review; badly scaled, obstructive, or misplaced art may be rejected or adjusted by an admin.",
                13f, C_LABEL, UIFactory.AlignTopLeft, sizeDelta: new Vector2(900, 32));
            txtArtistStatus = UIFactory.CreateText("ArtSt", panel.transform, "", 14f, C_LABEL,
                UIFactory.AlignTopLeft, sizeDelta: new Vector2(900, 22));

            var sv = UIFactory.CreateScrollView("ArtSV", panel.transform, spacing: 4);
            UIFactory.AddLE(sv.scrollGO, flexH: 1);
            artistItemsContainer = sv.content;

            // Item 1: per-purchase sales log — who bought what, at what price,
            // and the artist's cut. Single wrapped text block inside a fixed
            // scroll (same shape as the F5 chat log: LE prefH zeroed so TMP's
            // rendered height drives the scroll content).
            UIFactory.CreateText("ArtSalesH", panel.transform,
                "<color=#7FE8C3>Sales log</color>  <color=#888>(every purchase and gift of your items, newest first)</color>",
                16f, C_WHITE, UIFactory.AlignTopLeft, sizeDelta: new Vector2(900, 24));
            var ssv = UIFactory.CreateScrollView("ArtSalesSV", panel.transform, spacing: 0);
            UIFactory.AddLE(ssv.scrollGO, prefH: 150, minH: 100, flexH: 0);
            txtArtistSales = UIFactory.CreateText("ArtSales", ssv.content.transform,
                "<color=#888><i>No sales yet.</i></color>", 13f, C_WHITE,
                UIFactory.AlignTopLeft, sizeDelta: new Vector2(900, 24));
            UIFactory.SetWordWrap(txtArtistSales, true);
            {
                var salesLE = (txtArtistSales as Component)?.gameObject.GetComponent(UIFactory.tLE);
                if (salesLE != null)
                    UIFactory.tLE.GetProperty("preferredHeight", BindingFlags.Public | BindingFlags.Instance)?.SetValue(salesLE, -1f);
            }

            var blkHdr = UIFactory.CreateText("ArtBH", panel.transform,
                "<color=#FF9988>Blocked buyers</color>  <color=#888>(can't purchase your items; gifts still work)</color>",
                16f, C_WHITE, UIFactory.AlignTopLeft, sizeDelta: new Vector2(900, 24));
            var bsv = UIFactory.CreateScrollView("ArtBSV", panel.transform, spacing: 3);
            UIFactory.AddLE(bsv.scrollGO, prefH: 130, minH: 90, flexH: 0);
            artistBlocksContainer = bsv.content;

            // Item 11: the panel VLG force-expands children to full width, which
            // stretched this button across the whole tab. Park it in an HLG row
            // (no width force-expand) with a flexible spacer so it keeps its own
            // size, and use the name search instead of raw Steam64 entry.
            var blockRow = new GameObject("ArtBlockRow");
            blockRow.transform.SetParent(panel.transform, false);
            blockRow.AddComponent<RectTransform>();
            UIFactory.AddHLG(blockRow, spacing: 8);
            UIFactory.AddLE(blockRow, prefH: 32, minH: 32, flexH: 0);
            UIFactory.CreateButton("ArtBlockBtn", blockRow.transform,
                "Block a player...", 14f, C_WHITE, new Color(0.5f, 0.2f, 0.2f, 0.9f), () =>
                {
                    CompetitiveUI.OpenPlayerSearch("Block a buyer - find the player",
                        (sid, pname) =>
                        {
                            if (string.IsNullOrEmpty(sid)) return;
                            var me = MatchTracker.LocalSteamId;
                            ApiClient.ArtistBlock(me, sid, true, (ok, resp) =>
                                ShowArtistResult(ok, ok ? $"Blocked {pname}." : resp));
                        });
                }, sizeDelta: new Vector2(190, 28));
            // Round 3 item 2: artists submit their own cosmetics for review.
            UIFactory.CreateButton("ArtUpBtn", blockRow.transform,
                "Upload a cosmetic...", 14f, C_WHITE, new Color(0.2f, 0.4f, 0.55f, 0.9f),
                StartCosmeticUpload, sizeDelta: new Vector2(190, 28));
            UIFactory.CreateButton("ArtUpDir", blockRow.transform,
                "Open upload folder", 14f, C_WHITE, new Color(0.25f, 0.35f, 0.55f, 0.95f), () =>
                {
                    try
                    {
                        string dir = CosmeticUploadDir();
                        Application.OpenURL("file:///" + dir.Replace('\\', '/'));
                    }
                    catch (Exception ex) { Plugin.Log.LogWarning($"[COSMETIC] open folder: {ex.Message}"); }
                }, sizeDelta: new Vector2(180, 28));
            UIFactory.CreateButton("ArtPlace", blockRow.transform,
                "Adjust placement...", 14f, C_WHITE, new Color(0.35f, 0.3f, 0.55f, 0.95f),
                StartCosmeticPlacementAdjustment, sizeDelta: new Vector2(175, 28));
            var blockSp = new GameObject("S");
            blockSp.transform.SetParent(blockRow.transform, false);
            blockSp.AddComponent<RectTransform>();
            UIFactory.AddLE(blockSp, flexW: 1);
            // Submission statuses (pending / approved / denied with note).
            txtArtistSubs = UIFactory.CreateText("ArtSubs", panel.transform, "", 13f, C_LABEL,
                UIFactory.AlignTopLeft, sizeDelta: new Vector2(900, 20));
            UIFactory.SetTextAutoHeight(txtArtistSubs);
            UIFactory.SetWordWrap(txtArtistSubs, true);
            return panel;
        }

        // ── Cosmetic upload flow (round 3 item 2) ──────────────────────────
        // Folder-based (no OS file dialog in BepInEx): the artist drops a PNG in
        // plugins/CompetitiveRounds/cosmetic-uploads/, then picks it, names it,
        // and tags the slot. Client validates EXACTLY what the server enforces
        // (PNG, 512x512, transparency) plus a real per-pixel alpha check the
        // server can't do without an image library.
        private static string CosmeticUploadDir()
        {
            string dllDir = System.IO.Path.GetDirectoryName(System.Reflection.Assembly.GetExecutingAssembly().Location);
            string dir = System.IO.Path.Combine(dllDir, "cosmetic-uploads");
            System.IO.Directory.CreateDirectory(dir);
            return dir;
        }

        private static void StartCosmeticUpload()
        {
            try
            {
                string dir = CosmeticUploadDir();
                var files = System.IO.Directory.GetFiles(dir, "*.png");
                if (files.Length == 0)
                {
                    CompetitiveUI.ShowNotification(
                        "Drop a 512x512 transparent PNG into the upload folder first - opening it now.",
                        new Color(1f, 0.8f, 0.4f), 6f);
                    Application.OpenURL("file:///" + dir.Replace('\\', '/'));
                    return;
                }
                var names = new string[files.Length];
                var ids = new string[files.Length];
                for (int i = 0; i < files.Length; i++)
                { names[i] = System.IO.Path.GetFileName(files[i]); ids[i] = files[i]; }
                CompetitiveUI.OpenArtistPicker("Pick the PNG to submit", names, ids,
                    ValidateAndNameCosmetic, actionLabel: "Next", showClear: false);
            }
            catch (Exception ex) { Plugin.Log.LogWarning($"[COSMETIC] upload start: {ex.Message}"); }
        }

        private static void ValidateAndNameCosmetic(string path)
        {
            try
            {
                if (string.IsNullOrEmpty(path) || !System.IO.File.Exists(path)) return;
                var bytes = System.IO.File.ReadAllBytes(path);
                if (bytes.Length > 1_200_000)
                { ShowArtistResult(false, "{\"detail\":\"PNG too large - 1 MB max\"}"); return; }
                var tex = new Texture2D(2, 2, TextureFormat.RGBA32, false);
                bool loaded = tex.LoadImage(bytes);
                int w = tex.width, h = tex.height;
                int transparent = 0, total = 1;
                if (loaded)
                {
                    var px = tex.GetPixels32();
                    total = px.Length;
                    for (int i = 0; i < px.Length; i++) if (px[i].a < 250) transparent++;
                }
                UnityEngine.Object.Destroy(tex);
                if (!loaded)
                { ShowArtistResult(false, "{\"detail\":\"that file is not a readable PNG\"}"); return; }
                if (w != 512 || h != 512)
                { ShowArtistResult(false, $"{{\"detail\":\"must be exactly 512x512 - this one is {w}x{h}\"}}"); return; }
                if (transparent < total / 50)
                { ShowArtistResult(false, "{\"detail\":\"no transparent background detected - export with an alpha layer\"}"); return; }
                CompetitiveUI.OpenArtistInput("Name your cosmetic", "Display name (letters/numbers, max 40)", "",
                    nm =>
                    {
                        if (string.IsNullOrEmpty(nm) || nm.Trim().Length < 2)
                        { ShowArtistResult(false, "{\"detail\":\"name too short\"}"); return; }
                        PickSlotAndSubmitCosmetic(bytes, nm.Trim());
                    });
            }
            catch (Exception ex) { Plugin.Log.LogWarning($"[COSMETIC] validate: {ex.Message}"); }
        }

        private static void PickSlotAndSubmitCosmetic(byte[] bytes, string name)
        {
            CompetitiveUI.OpenArtistPicker($"What type of cosmetic is '{name}'?",
                new[] { "Eyes", "Mouth", "Detail (hat / accessory)" },
                new[] { "eyes", "mouth", "detail" },
                slot =>
                {
                    if (string.IsNullOrEmpty(slot)) return;
                    CompetitiveUI.OpenCosmeticTestPreview(bytes, name, slot,
                        (renderScale, renderOffsetX, renderOffsetY) =>
                    {
                        string b64 = Convert.ToBase64String(bytes);
                        ApiClient.ArtistSubmitCosmetic(
                            MatchTracker.LocalSteamId, name, slot, b64,
                            renderScale, renderOffsetX, renderOffsetY,
                            (ok, resp) => ShowArtistResult(ok,
                                ok ? $"'{name}' submitted for scale/placement review. You'll see the status on this tab."
                                   : resp));
                    });
                }, actionLabel: "Preview", showClear: false);
        }

        private static void StartCosmeticPlacementAdjustment()
        {
            if (cosmeticPlacementLoading)
            {
                CompetitiveUI.ShowNotification(
                    "The selected cosmetic is still loading.",
                    new Color(0.55f, 0.75f, 1f), 3f);
                return;
            }
            var all = ApiClient.CachedMySubmissions;
            var editable = all == null
                ? new List<ApiClient.CosmeticSubmission>()
                : all.Where(s => s != null && (s.status == "pending" || s.status == "approved")).ToList();
            var linkedSkus = new HashSet<string>(
                editable.Where(s => !string.IsNullOrEmpty(s.shop_sku))
                        .Select(s => s.shop_sku),
                StringComparer.OrdinalIgnoreCase);
            var legacyItems = (ApiClient.CachedArtistItems ?? new List<ApiClient.ArtistItemEntry>())
                .Where(it => it != null
                    && it.catalog_ready
                    && string.Equals(it.kind, "face", StringComparison.OrdinalIgnoreCase)
                    && !string.IsNullOrEmpty(it.sku)
                    && !linkedSkus.Contains(it.sku))
                .ToList();
            if (editable.Count == 0 && legacyItems.Count == 0)
            {
                ShowArtistResult(false, "{\"detail\":\"no pending or approved cosmetics to adjust\"}");
                return;
            }
            string[] labels = new string[editable.Count + legacyItems.Count];
            string[] ids = new string[labels.Length];
            for (int i = 0; i < editable.Count; i++)
            {
                var s = editable[i];
                string state = s.status == "approved"
                    ? (s.placement_status == "pending" ? "placement pending" : "approved")
                    : "initial review pending";
                labels[i] = $"{s.name} ({s.slot}, {state})";
                ids[i] = $"submission:{s.id}";
            }
            for (int i = 0; i < legacyItems.Count; i++)
            {
                var it = legacyItems[i];
                int at = editable.Count + i;
                labels[at] = $"{it.name} (published; first placement revision)";
                ids[at] = $"catalog:{it.sku}";
            }
            CompetitiveUI.OpenArtistPicker(
                "Adjust which cosmetic? Changes return to admin review.",
                labels, ids, selected =>
                {
                    if (selected.StartsWith("catalog:", StringComparison.Ordinal))
                    {
                        string sku = selected.Substring("catalog:".Length);
                        var item = legacyItems.FirstOrDefault(
                            it => string.Equals(it.sku, sku, StringComparison.OrdinalIgnoreCase));
                        string slot;
                        float publishedScale;
                        Vector2 publishedOffset;
                        byte[] bytes;
                        if (item == null || !CustomCosmetics.TryGetPublishedPlacement(
                                sku, out slot, out publishedScale, out publishedOffset, out bytes))
                        {
                            ShowArtistResult(false,
                                "{\"detail\":\"the published PNG is missing locally; reinstall or update the cosmetic art bundle\"}");
                            return;
                        }
                        CompetitiveUI.OpenCosmeticTestPreview(
                            bytes, item.name, slot,
                            (scale, offsetX, offsetY) =>
                                ApiClient.ArtistStartCatalogPlacementRevision(
                                    MatchTracker.LocalSteamId, sku, slot,
                                    Convert.ToBase64String(bytes),
                                    publishedScale, publishedOffset.x, publishedOffset.y,
                                    scale, offsetX, offsetY,
                                    (saved, saveResp) => ShowArtistResult(
                                        saved,
                                        saved
                                            ? $"'{item.name}' placement revision sent for admin review. Its current published placement stays active until the approved revision ships."
                                            : saveResp)),
                            publishedScale, publishedOffset.x, publishedOffset.y,
                            "Send to review", isRevision: true);
                        return;
                    }

                    if (!selected.StartsWith("submission:", StringComparison.Ordinal)) return;
                    int submissionId;
                    if (!int.TryParse(
                            selected.Substring("submission:".Length), out submissionId))
                        return;
                    cosmeticPlacementLoading = true;
                    int ticket = ++cosmeticPlacementLoadTicket;
                    CompetitiveUI.ShowNotification(
                        "Loading the reviewed cosmetic...", new Color(0.55f, 0.75f, 1f), 3f);
                    ApiClient.FetchCosmeticSubmissionPreview(
                        MatchTracker.LocalSteamId, submissionId, (ok, sub, resp) =>
                        {
                            if (ticket != cosmeticPlacementLoadTicket) return;
                            cosmeticPlacementLoading = false;
                            if (!ok || sub == null)
                            {
                                ShowArtistResult(false, resp);
                                return;
                            }
                            byte[] bytes;
                            try { bytes = Convert.FromBase64String(sub.png_base64 ?? ""); }
                            catch
                            {
                                ShowArtistResult(false, "{\"detail\":\"could not decode the saved preview\"}");
                                return;
                            }
                            if (!isOpen) return;
                            CompetitiveUI.OpenCosmeticTestPreview(
                                bytes, sub.name, sub.slot,
                                (scale, offsetX, offsetY) =>
                                    ApiClient.ArtistUpdateCosmeticPlacement(
                                        MatchTracker.LocalSteamId, sub.id, sub.placement_revision,
                                        scale, offsetX, offsetY,
                                        (saved, saveResp) => ShowArtistResult(
                                            saved,
                                            saved
                                                ? $"'{sub.name}' placement revision sent for admin review. The last approved placement stays active until this one is approved and shipped."
                                                : saveResp)),
                                sub.render_scale, sub.render_offset_x, sub.render_offset_y,
                                "Send to review", isRevision: true);
                        });
                }, actionLabel: "Preview", showClear: false);
        }

        private static void ShowArtistResult(bool ok, string msg)
        {
            CompetitiveUI.ShowNotification(ok ? (string.IsNullOrEmpty(msg) ? "Done." : msg)
                                              : $"Failed: {ExtractServerDetail(msg)}",
                ok ? new Color(0.4f, 0.9f, 0.5f) : new Color(1f, 0.45f, 0.4f));
            dirty = true;
        }

        // Server errors arrive as {"detail":"..."} — surface just the message.
        private static string ExtractServerDetail(string resp)
        {
            if (string.IsNullOrEmpty(resp)) return "no response";
            int i = resp.IndexOf("\"detail\":\"", StringComparison.Ordinal);
            if (i < 0) return resp.Length > 90 ? resp.Substring(0, 90) : resp;
            int s = i + 10, e = resp.IndexOf('"', s);
            return e > s ? resp.Substring(s, e - s) : resp;
        }

        private static void RefreshArtistTab()
        {
            if (!ApiClient.IsArtist) { UIFactory.SetText(txtArtistStatus, "Not an artist account."); return; }
            var items = ApiClient.CachedArtistItems;
            var blocks = ApiClient.CachedArtistBlocks;
            UIFactory.SetText(txtArtistStatus, items == null || items.Count == 0
                ? "<color=#888>No items assigned to you yet - art gets wired to your account when it ships in a mod update.</color>"
                : $"{items.Count} item(s), {SumSold(items)} cop(ies) out there.");

            int i = 0;
            if (items != null)
            {
                foreach (var it in items)
                {
                    var row = GetOrCreateArtistRow(i++);
                    row.sku = it.sku; row.name = it.name; row.price = it.price;
                    row.stock = it.stock_limit; row.catalogReady = it.catalog_ready;
                    if (row.stockBtn != null) row.stockBtn.SetActive(it.catalog_ready);
                    if (row.giftBtn != null) row.giftBtn.SetActive(it.catalog_ready);
                    // Item 9: cosmetic art thumbnail (face items have runtime sprites;
                    // other kinds simply hide the slot).
                    try
                    {
                        var sp = CustomCosmetics.GetShopSprite(it.sku);
                        if (sp != null && row.artImg != null)
                        {
                            UIFactory.tImage.GetProperty("sprite", BindingFlags.Public | BindingFlags.Instance)?.SetValue(row.artImg, sp);
                            UIFactory.tImage.GetProperty("color", BindingFlags.Public | BindingFlags.Instance)?.SetValue(row.artImg, Color.white);
                            row.artImgGO.SetActive(true);
                        }
                        else if (row.artImgGO != null) row.artImgGO.SetActive(false);
                    }
                    catch { }
                    string stockStr = !it.catalog_ready
                        ? "<color=#FFD94D>APPROVED - awaiting mod update</color>"
                        : it.stock_limit < 0
                            ? "<color=#FF6666>NOT OPENED - set stock to start selling!</color>"
                            : it.stock_limit > 0
                                ? $"{Math.Max(0, it.stock_limit - it.sold)} of {it.stock_limit} left"
                                : "unlimited";
                    UIFactory.SetText(row.txtInfo,
                        $"<b>{it.name}</b> <color=#888>({it.kind}, {it.rarity})</color>  " +
                        $"<color=#FFD94D>{it.price}g</color>  <color=#7FE8C3>{stockStr}</color>  " +
                        $"<color=#888>sold {Math.Max(0, it.sold - it.gifted)}, gifted {it.gifted}</color>" +
                        (it.earned > 0 ? $"  <color=#FFD94D>earned {it.earned}g</color>" : ""));
                    row.root.SetActive(true);
                }
            }
            for (int j = i; j < artistRows.Count; j++) artistRows[j].root.SetActive(false);

            // Round 3 item 2: submission statuses under the item list.
            if (txtArtistSubs != null)
            {
                var subs = ApiClient.CachedMySubmissions;
                if (subs == null || subs.Count == 0) UIFactory.SetText(txtArtistSubs, "");
                else
                {
                    var ssb = new System.Text.StringBuilder("<color=#9AD0FF>Your submissions:</color>\n");
                    int shown = 0;
                    foreach (var s in subs)
                    {
                        if (shown++ >= 6) break;
                        string st;
                        if (s.status == "approved" && s.placement_status == "pending")
                            st = "<color=#FFD94D>PLACEMENT PENDING REVIEW</color> <color=#888>(last approved placement stays active)</color>";
                        else if (s.status == "approved" && s.placement_status == "denied")
                            st = "<color=#FF9966>PLACEMENT CHANGE REJECTED</color>"
                               + (string.IsNullOrEmpty(s.placement_review_note) ? ""
                                  : $" <color=#888>- {HomeSan(s.placement_review_note)}</color>")
                               + " <color=#888>(last approved placement stays active)</color>";
                        else if (s.status == "approved")
                            st = s.approved_placement_revision > s.published_placement_revision
                                ? $"<color=#66DD66>APPROVED</color> <color=#888>(rev {s.approved_placement_revision} awaits a mod update)</color>"
                                : $"<color=#66DD66>APPROVED</color> <color=#888>({s.shop_sku})</color>";
                        else if (s.status == "denied")
                            st = $"<color=#FF6666>DENIED</color>{(string.IsNullOrEmpty(s.review_note) ? "" : $" <color=#888>- {HomeSan(s.review_note)}</color>")}";
                        else
                            st = "<color=#FFD94D>pending initial review</color>";
                        // Offset is just the default start position (players drag
                        // face items themselves), so it isn't shown in list rows —
                        // scale is the value that decides whether the art fits.
                        ssb.Append($"  {HomeSan(s.name)} <color=#888>({s.slot}, {s.render_scale:F2}x, "
                                   + $"rev {s.placement_revision})</color>  {st}\n");
                    }
                    UIFactory.SetText(txtArtistSubs, ssb.ToString().TrimEnd('\n'));
                }
            }

            // Item 1: per-purchase sales log. Buyer names are user-authored —
            // sanitize before splicing into rich text.
            if (txtArtistSales != null)
            {
                var sales = ApiClient.CachedArtistSales;
                if (sales == null || sales.Count == 0)
                    UIFactory.SetText(txtArtistSales, "<color=#888><i>No sales yet.</i></color>");
                else
                {
                    var slb = new System.Text.StringBuilder();
                    foreach (var s in sales)
                    {
                        string item = HomeSan(s.item);
                        string buyer = HomeSan(s.buyer);
                        if (s.price <= 0)
                            slb.Append($"<color=#888>{s.when}</color>  <b>{buyer}</b> received <color=#C8A2FF>{item}</color>  <color=#888>(gift)</color>\n");
                        else
                            slb.Append($"<color=#888>{s.when}</color>  <b>{buyer}</b> bought <color=#C8A2FF>{item}</color> for <color=#FFD94D>{s.price}g</color>  <color=#7FE8C3>+{s.earned}g to you</color>\n");
                    }
                    UIFactory.SetText(txtArtistSales, slb.ToString().TrimEnd('\n'));
                }
            }

            int bi = 0;
            if (blocks != null)
            {
                foreach (var b in blocks)
                {
                    var row = GetOrCreateArtistBlockRow(bi++);
                    row.steamId = b.steam_id; row.name = b.display_name;
                    UIFactory.SetText(row.txtInfo, $"{b.display_name}  <color=#888>({b.steam_id})</color>");
                    row.root.SetActive(true);
                }
            }
            for (int j = bi; j < artistBlockRows.Count; j++) artistBlockRows[j].root.SetActive(false);
        }

        private static int SumSold(List<ApiClient.ArtistItemEntry> items)
        {
            int n = 0; foreach (var it in items) n += it.sold; return n;
        }

        private static ArtistRow GetOrCreateArtistRow(int idx)
        {
            while (artistRows.Count <= idx)
            {
                var row = new ArtistRow();
                row.root = new GameObject($"artRow{artistRows.Count}");
                row.root.transform.SetParent(artistItemsContainer.transform, false);
                row.root.AddComponent<RectTransform>();
                UIFactory.AddHLG(row.root, spacing: 8, padL: 6, padR: 6, padT: 4, padB: 4, forceExpandH: true);
                UIFactory.AddLE(row.root, prefH: 32);
                if (UIFactory.tImage != null)
                {
                    var img = row.root.AddComponent(UIFactory.tImage);
                    UIFactory.tImage.GetProperty("color", BindingFlags.Public | BindingFlags.Instance)?.SetValue(img, C_PANEL);
                }
                // July 12 round 2 item 9: the cosmetic's actual art beside the row
                // (same runtime-loaded sprite the shop rows use).
                row.artImgGO = new GameObject("art");
                row.artImgGO.transform.SetParent(row.root.transform, false);
                row.artImgGO.AddComponent<RectTransform>();
                UIFactory.AddLE(row.artImgGO, prefW: 30, minW: 30, prefH: 30, flexW: 0, flexH: 0);
                if (UIFactory.tImage != null)
                {
                    row.artImg = row.artImgGO.AddComponent(UIFactory.tImage);
                    try { UIFactory.tImage.GetProperty("preserveAspect", BindingFlags.Public | BindingFlags.Instance)?.SetValue(row.artImg, true); } catch { }
                    try { UIFactory.tImage.GetProperty("raycastTarget", BindingFlags.Public | BindingFlags.Instance)?.SetValue(row.artImg, false); } catch { }
                }
                row.artImgGO.SetActive(false);
                row.txtInfo = UIFactory.CreateText("i", row.root.transform, "", 14f, C_WHITE,
                    UIFactory.AlignMidLeft, sizeDelta: new Vector2(400, 28));
                var r = row; // capture the ROW — pooled rows re-target via fields
                // July 12: artists control the NAME + DESCRIPTION of their art too.
                UIFactory.CreateButton("nm", row.root.transform, "Name", 13f, C_WHITE, C_BTN, () =>
                {
                    CompetitiveUI.OpenArtistInput($"Rename - {r.name}", "New display name (max 64 chars)",
                        r.name ?? "", v =>
                        {
                            if (string.IsNullOrEmpty(v)) { ShowArtistResult(false, "{\"detail\":\"name can't be empty\"}"); return; }
                            ApiClient.ArtistSetName(MatchTracker.LocalSteamId, r.sku, v,
                                (ok, resp) => ShowArtistResult(ok, ok ? "Renamed." : resp));
                        });
                }, sizeDelta: new Vector2(56, 24));
                UIFactory.CreateButton("ds", row.root.transform, "Desc", 13f, C_WHITE, C_BTN, () =>
                {
                    CompetitiveUI.OpenArtistInput($"Description - {r.name}", "Shop description (max 200 chars)",
                        "", v => ApiClient.ArtistSetDesc(MatchTracker.LocalSteamId, r.sku, v,
                            (ok, resp) => ShowArtistResult(ok, ok ? "Description updated." : resp)));
                }, sizeDelta: new Vector2(52, 24));
                row.priceBtn = UIFactory.CreateButton("p", row.root.transform, "Price", 13f, C_WHITE, C_BTN, () =>
                {
                    CompetitiveUI.OpenArtistInput($"Set price - {r.name}", "New price in gold (0-100000)",
                        r.price.ToString(), v =>
                        {
                            int nv;
                            if (!int.TryParse(v, out nv) || nv < 0 || nv > 100000)
                            { ShowArtistResult(false, "{\"detail\":\"price must be 0-100000\"}"); return; }
                            ApiClient.ArtistSetPrice(MatchTracker.LocalSteamId, r.sku, nv,
                                (ok, resp) => ShowArtistResult(ok, ok ? $"{r.name} is now {nv}g." : resp));
                        });
                }, sizeDelta: new Vector2(60, 24));
                row.stockBtn = UIFactory.CreateButton("s", row.root.transform, "Stock", 13f, C_WHITE, C_BTN, () =>
                {
                    if (!r.catalogReady)
                    { ShowArtistResult(false, "{\"detail\":\"art is still awaiting a mod update\"}"); return; }
                    CompetitiveUI.OpenArtistInput($"Set stock - {r.name}", "Max copies (0 = unlimited)",
                        r.stock.ToString(), v =>
                        {
                            int nv;
                            if (!int.TryParse(v, out nv) || nv < 0 || nv > 100000)
                            { ShowArtistResult(false, "{\"detail\":\"stock must be 0-100000\"}"); return; }
                            ApiClient.ArtistSetStock(MatchTracker.LocalSteamId, r.sku, nv,
                                (ok, resp) => ShowArtistResult(ok, ok ? $"{r.name} stock set." : resp));
                        });
                }, sizeDelta: new Vector2(60, 24));
                row.giftBtn = UIFactory.CreateButton("g", row.root.transform, "Gift", 13f, C_WHITE,
                    new Color(0.2f, 0.45f, 0.25f, 0.9f), () =>
                {
                    if (!r.catalogReady)
                    { ShowArtistResult(false, "{\"detail\":\"art is still awaiting a mod update\"}"); return; }
                    // Item 8: search by name (elo shown beside each result so a
                    // rename-imposter can't receive someone else's gift).
                    CompetitiveUI.OpenPlayerSearch($"Gift {r.name} - find the recipient",
                        (sid, pname) =>
                        {
                            if (string.IsNullOrEmpty(sid)) return;
                            ApiClient.ArtistGift(MatchTracker.LocalSteamId, r.sku, sid,
                                (ok, resp) => ShowArtistResult(ok, ok ? $"Gifted {r.name} to {pname}." : resp));
                        });
                }, sizeDelta: new Vector2(60, 24));
                artistRows.Add(row);
            }
            return artistRows[idx];
        }

        private static ArtistBlockRow GetOrCreateArtistBlockRow(int idx)
        {
            while (artistBlockRows.Count <= idx)
            {
                var row = new ArtistBlockRow();
                row.root = new GameObject($"artBlk{artistBlockRows.Count}");
                row.root.transform.SetParent(artistBlocksContainer.transform, false);
                row.root.AddComponent<RectTransform>();
                UIFactory.AddHLG(row.root, spacing: 8, padL: 6, padR: 6, padT: 3, padB: 3, forceExpandH: true);
                UIFactory.AddLE(row.root, prefH: 26);
                row.txtInfo = UIFactory.CreateText("i", row.root.transform, "", 13f, C_WHITE,
                    UIFactory.AlignMidLeft, sizeDelta: new Vector2(420, 22));
                var r = row;
                row.unblockBtn = UIFactory.CreateButton("u", row.root.transform, "Unblock", 12f, C_WHITE, C_BTN, () =>
                {
                    CompetitiveUI.OpenConfirm($"Unblock {r.name} from buying your items?", () =>
                        ApiClient.ArtistBlock(MatchTracker.LocalSteamId, r.steamId, false,
                            (ok, resp) => ShowArtistResult(ok, ok ? $"{r.name} unblocked." : resp)));
                }, sizeDelta: new Vector2(70, 22));
                artistBlockRows.Add(row);
            }
            return artistBlockRows[idx];
        }

        private static void RefreshData(){string id=MatchTracker.LocalSteamId;if(!string.IsNullOrEmpty(id)&&id!="unknown"){ApiClient.FetchPlayerStats(id);ApiClient.FetchMatchHistory(id);ApiClient.FetchAchievements(id);ApiClient.FetchTeamStats(id);}if(currentTab==1){ApiClient.FetchLeaderboard();ApiClient.FetchRecentSeries();}if(currentTab==2){ApiClient.FetchCardStats(200,MatchTracker.LocalSteamId);LoadCardTiersForCurrentFilter();}}
        private static void RefreshCurrentTab(){RefreshQueueUI();RefreshVersionStatus();RefreshServerBanner();RefreshTournamentGameIndicator();/* Admin/Artist button visibility - the async checks can flip on late. */UpdateTabBarVisual();switch(currentTab){case 0:RefreshMyStats();break;case 1:RefreshLeaderboard();RefreshRecentSeries();RefreshLiveSeries();break;case 2:RefreshCardStats();break;case 3:RefreshAchievements();break;case 4:RefreshShop();break;case 5:RefreshSettings();break;case 6:RefreshAdmin();break;case 7:RefreshTournaments();break;case 8:RefreshTeamTab();break;case 9:RefreshCompare();break;case 10:RefreshArtistTab();break;case 11:RefreshOneVTwoTab();break;case 13:RefreshHomeTab();break;}}

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
            var rawList = ApiClient.CachedActiveSeries;
            // Filter out tournament series that haven't actually gone live
            // yet (no points scored, no game wins). Pre-match tournament
            // matches show up in the Tournament tab's bet section instead.
            // Once any in-game activity registers (server flips
            // phase=='live'), they appear in the Live Ranked Games panel
            // alongside queue + private matches.
            var list = new List<ApiClient.ActiveSeriesEntry>();
            if (rawList != null)
            {
                foreach (var s in rawList)
                {
                    if (s.is_tournament && s.phase == "pre_match") continue;
                    list.Add(s);
                }
            }
            var teamList = ApiClient.CachedActiveTeamSeries;
            int oneVOneCount = list.Count;
            int teamCount = teamList != null ? teamList.Count : 0;
            // Clear pool first, then rebuild.
            foreach (var g in liveBetRowPool) g.SetActive(false);
            if (oneVOneCount == 0 && teamCount == 0)
            {
                UIFactory.SetText(txtLiveSeries, "<color=#666><i>No live games right now.</i></color>");
                if (liveBetsPager != null) liveBetsPager.SetActive(false);
                RefreshMyBetsLedger();   // ledger shows outcomes even with nothing live
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

            RefreshMyBetsLedger();
        }

        /// <summary>Personal bet ledger (v1.30, bug #53 + item 6 polish). Shows
        /// every PENDING bet (with the full matchup, so a bet that landed on a
        /// player's other series is visible immediately — Discord-placed bets
        /// included) plus the last few settled outcomes. Refunds are named
        /// explicitly instead of being silently dropped. Full words, full names,
        /// date, stake, and the opponent faced — no abbreviations (Sid item 6).
        /// Bold comes free via UIFactory.SetText's rich-text bold wrap.</summary>
        private static void RefreshMyBetsLedger()
        {
            if (txtMyBets == null) return;
            var bets = ApiClient.CachedMyBets;
            if (bets == null || bets.Count == 0) { UIFactory.SetText(txtMyBets, ""); return; }
            var sb = new System.Text.StringBuilder();
            int settledShown = 0;
            foreach (var b in bets)
            {
                if (b.settled) continue;
                sb.Append($"<color=#FFD94D>{BetDate(b)}  Bet {b.amount:N0} gold on {b.bet_on_name} vs {b.vs_name}</color> <color=#AAA>- in play, score {b.series_score}</color>\n");
            }
            foreach (var b in bets)
            {
                // July 12 round 2 item 5: outcomes older than 3 days age out of
                // the panel (pending bets always show — they're live money).
                if (!b.settled || settledShown >= 3 || !BetWithinDays(b, 3)) continue;
                settledShown++;
                if (b.payout == b.amount)
                    sb.Append($"<color=#BBB>{BetDate(b)}  Bet {b.amount:N0} gold on {b.bet_on_name} vs {b.vs_name} - refunded, series never finished</color>\n");
                else if (b.payout > 0)
                    sb.Append($"<color=#66DD66>{BetDate(b)}  Bet {b.amount:N0} gold on {b.bet_on_name} vs {b.vs_name} - WON {b.payout - b.amount:N0} gold</color>\n");
                else
                    sb.Append($"<color=#DD7777>{BetDate(b)}  Bet {b.amount:N0} gold on {b.bet_on_name} vs {b.vs_name} - LOST</color>\n");
            }
            string body = sb.ToString().TrimEnd('\n');
            // Leading newline: a blank line between the live-games list above and
            // this ledger so the two sections stop blending (item 5).
            UIFactory.SetText(txtMyBets, body.Length > 0 ? $"\n<color=#CCC>Your Recent Bets</color>\n{body}" : "");
        }

        private static bool BetWithinDays(ApiClient.MyBetEntry b, int days)
        {
            try
            {
                if (string.IsNullOrEmpty(b.created_at)) return true;   // no timestamp -> keep
                var dt = DateTime.Parse(b.created_at, null, System.Globalization.DateTimeStyles.RoundtripKind);
                return (DateTime.UtcNow - dt.ToUniversalTime()).TotalDays <= days;
            }
            catch { return true; }
        }

        private static string BetDate(ApiClient.MyBetEntry b)
        {
            try
            {
                if (!string.IsNullOrEmpty(b.created_at))
                    return DateTime.Parse(b.created_at, null,
                        System.Globalization.DateTimeStyles.RoundtripKind).ToLocalTime().ToString("M/d");
            }
            catch { }
            return "";
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
            // Lead the line with a tournament tag for tournament series so
            // the user instantly sees these aren't open-queue games. Tag
            // styled gold like the rest of the tournament UI; kind suffix
            // ([Async]/[Sync]) only when the kind is known.
            string tag = "";
            if (s.is_tournament)
            {
                string kindSuffix = string.IsNullOrEmpty(s.tournament_kind)
                    ? ""
                    : $" {char.ToUpper(s.tournament_kind[0]) + s.tournament_kind.Substring(1)}";
                tag = $"<color=#FFD94D><b>[TOURNAMENT{kindSuffix}]</b></color>  ";
            }
            else if (s.is_private)
            {
                tag = "<color=#888><b>[PRIVATE]</b></color>  ";
            }
            string line = tag +
                          $"<color=#AAF>{Trunc(s.p1_name, 12)}</color> ({s.p1_rating})  " +
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

            // One label carrying name+odds AND any status suffix, so a status tag
            // can't overlap the odds number (the overlap bug). Open state: label
            // then buttons. Bet/locked/self states: status folded into the label.
            var existing = ApiClient.GetMyBetForSeries(s.series_id);
            if (existing != null)
            {
                bool betOnThisSide = existing.bet_on_steam_id == steamId;
                string suffix = betOnThisSide
                    ? $"  <color=#FFD94D><b>You bet {existing.amount}g</b></color>"
                    : "";  // other side stays plain so live odds still read
                var t = UIFactory.CreateText("bl", row.transform,
                    $"<b>{Trunc(name, 10)}</b> @{odds:F1}x{suffix}",
                    13f, C_LABEL, UIFactory.AlignMidLeft, sizeDelta: new Vector2(440, 22));
                UIFactory.SetWordWrap(t, false);
                return;
            }
            if (s.bets_locked)
            {
                string lockMsg = s.lock_reason == "no_meaningful_odds"
                    ? "odds too uncertain"
                    : "betting period over";
                var t = UIFactory.CreateText("bl", row.transform,
                    $"<b>{Trunc(name, 10)}</b> @{odds:F1}x  <color=#A07744><i>{lockMsg}</i></color>",
                    13f, C_LABEL, UIFactory.AlignMidLeft, sizeDelta: new Vector2(440, 22));
                UIFactory.SetWordWrap(t, false);
                return;
            }
            if (localIsParticipant)
            {
                var t = UIFactory.CreateText("bl", row.transform,
                    $"<b>{Trunc(name, 10)}</b> @{odds:F1}x  <color=#AA9955><i>your match</i></color>",
                    13f, C_LABEL, UIFactory.AlignMidLeft, sizeDelta: new Vector2(440, 22));
                UIFactory.SetWordWrap(t, false);
                return;
            }
            var betLabel = UIFactory.CreateText("bl", row.transform,
                $"Bet on <b>{Trunc(name, 10)}</b> @{odds:F1}x:",
                13f, C_LABEL, UIFactory.AlignMidLeft, sizeDelta: new Vector2(240, 22));
            UIFactory.SetWordWrap(betLabel, false);

            AddBetButton(row.transform, s.series_id, steamId, 100);
            AddBetButton(row.transform, s.series_id, steamId, 500);
            AddBetButton(row.transform, s.series_id, steamId, 2000);
            AddCustomBetButton(row.transform, s.series_id, steamId, 0, false, Trunc(name, 14));
        }

        // 2v2 live-series row builders (parallel to ApplyHeaderRow / ApplyBetRow).
        private static void ApplyTeamHeaderRow(GameObject row, ApiClient.ActiveTeamSeriesEntry s)
        {
            // Show each player's ACTUAL 2v2 rating (was the team average for both,
            // which read as "1500 for all 4"). Format: "Name(elo)+Name(elo)".
            string line = $"<color=#FFB347>2v2</color>  " +
                          $"<color=#AAF>{Trunc(s.t1a_name, 7)}({s.t1a_rating})+{Trunc(s.t1b_name, 7)}({s.t1b_rating})</color>  " +
                          $"<b>{s.t1_wins}-{s.t2_wins}</b>  " +
                          $"<color=#FAA>{Trunc(s.t2a_name, 7)}({s.t2a_rating})+{Trunc(s.t2b_name, 7)}({s.t2b_rating})</color>";
            var t = UIFactory.CreateText("hdr", row.transform, line,
                14f, C_WHITE, UIFactory.AlignMidLeft, sizeDelta: new Vector2(560, 24));
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

            // Single label that carries BOTH the team + odds AND any status suffix,
            // so a locked/self state can never paint over the odds number (the
            // overlap bug — previously a second text element was layered on top of
            // the odds-bearing label in the same HLG row). When locked/self, the
            // status is appended INTO this one label; when open, the buttons follow.
            if (s.bets_locked)
            {
                string lockMsg = s.lock_reason == "no_meaningful_odds"
                    ? "odds too uncertain"
                    : "betting period over";
                var lbl = UIFactory.CreateText("tbl", row.transform,
                    $"<b>{teamLabel}</b> @{odds:F1}x  <color=#A07744><i>{lockMsg}</i></color>",
                    13f, C_LABEL, UIFactory.AlignMidLeft, sizeDelta: new Vector2(440, 22));
                UIFactory.SetWordWrap(lbl, false);
                return;
            }
            if (localIsParticipant)
            {
                var lbl = UIFactory.CreateText("tbl", row.transform,
                    $"<b>{teamLabel}</b> @{odds:F1}x  <color=#AA9955><i>your match</i></color>",
                    13f, C_LABEL, UIFactory.AlignMidLeft, sizeDelta: new Vector2(440, 22));
                UIFactory.SetWordWrap(lbl, false);
                return;
            }
            var betLabel = UIFactory.CreateText("tbl", row.transform,
                $"Bet on <b>{teamLabel}</b> @{odds:F1}x:",
                13f, C_LABEL, UIFactory.AlignMidLeft, sizeDelta: new Vector2(240, 22));
            UIFactory.SetWordWrap(betLabel, false);
            AddTeamBetButton(row.transform, s.series_id, team, 100);
            AddTeamBetButton(row.transform, s.series_id, team, 500);
            AddTeamBetButton(row.transform, s.series_id, team, 2000);
            AddCustomBetButton(row.transform, s.series_id, null, team, true, teamLabel);
        }

        // ── Custom bet amount prompt (v1.29, F6) ─────────────────────────────
        // The "..." button next to the preset amounts opens an IMGUI prompt
        // (all text entry in this codebase is IMGUI) where any amount from 1
        // to 2,000 gold can be entered (cap requested by Sid; the server
        // enforces the same le=2000 on every bet endpoint).
        public static bool CustomBetPromptOpen { get; private set; }
        public static string CustomBetAmountText = "";
        public static string CustomBetTargetLabel { get; private set; } = "";
        private static string customBetSeriesId, customBetOnSteamId;
        private static int customBetTeam;
        private static bool customBetIsTeam;

        public static void OpenCustomBetPrompt(string seriesId, string betOnSteamId, int team, bool isTeam, string targetLabel)
        {
            customBetSeriesId = seriesId;
            customBetOnSteamId = betOnSteamId;
            customBetTeam = team;
            customBetIsTeam = isTeam;
            CustomBetTargetLabel = targetLabel ?? "";
            CustomBetAmountText = "";
            CustomBetPromptOpen = true;
        }

        public static void CancelCustomBet() { CustomBetPromptOpen = false; }

        public static void SubmitCustomBet()
        {
            CustomBetPromptOpen = false;
            string raw = (CustomBetAmountText ?? "").Replace(",", "").Replace(" ", "").Trim();
            int amount;
            if (!int.TryParse(raw, out amount) || amount < 1 || amount > 2000)
            {
                CompetitiveUI.ShowNotification("Enter a whole amount between 1 and 2,000 gold.", new Color(1f, 0.5f, 0.5f), 3f);
                return;
            }
            string id = MatchTracker.LocalSteamId;
            if (string.IsNullOrEmpty(id) || id == "unknown") return;
            if (customBetIsTeam)
            {
                Plugin.Log.LogInfo($"[TEAM-BET] Placing CUSTOM {amount}g on team {customBetTeam} (series {customBetSeriesId})");
                ApiClient.PlaceTeamBet(id, customBetSeriesId, customBetTeam, amount, (ok, resp) =>
                {
                    var col = ok ? new Color(0.4f, 1f, 0.4f) : new Color(1f, 0.5f, 0.5f);
                    CompetitiveUI.ShowNotification(ok ? $"Bet placed: {amount}g on Team {customBetTeam}" : $"Bet failed: {resp}", col, 3f);
                    if (ok) { ApiClient.FetchActiveTeamSeries(); ApiClient.FetchPlayerStats(id); }
                });
            }
            else
            {
                Plugin.Log.LogInfo($"[BET] Placing CUSTOM {amount}g on {customBetOnSteamId} (series {customBetSeriesId})");
                ApiClient.PlaceBet(id, customBetSeriesId, customBetOnSteamId, amount, (ok, resp) =>
                {
                    var col = ok ? new Color(0.4f, 1f, 0.4f) : new Color(1f, 0.5f, 0.5f);
                    CompetitiveUI.ShowNotification(ok ? $"Bet placed: {amount}g" : $"Bet failed: {resp}", col, 3f);
                    if (ok) { ApiClient.FetchActiveSeries(); ApiClient.FetchPlayerStats(id); ApiClient.FetchMyBets(id); }
                });
            }
        }

        private static void AddCustomBetButton(Transform parent, string seriesId, string betOnSteamId, int team, bool isTeam, string targetLabel)
        {
            var btn = UIFactory.CreateButton(isTeam ? $"tbc{team}" : "bc", parent,
                "...", 11f, C_WHITE, new Color(0.28f, 0.24f, 0.12f, 0.9f),
                () => OpenCustomBetPrompt(seriesId, betOnSteamId, team, isTeam, targetLabel),
                sizeDelta: new Vector2(30, 22));
            UIFactory.AddLE(btn, prefW: 30, prefH: 22, flexW: 0, flexH: 0);
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
        private static GameObject shopCursorHeader, shopEffectsHeader, shopFacesHeader, shopOtherHeader;
        // Bug batch item 9: artist filter for the CHARACTER COSMETICS section.
        // null = show all; otherwise the artist display name ("House" = unattributed).
        private static string shopArtistFilter = null;
        private static GameObject shopArtistFilterRow;
        private static readonly List<GameObject> shopArtistBtns = new List<GameObject>();
        private static readonly List<object> shopArtistBtnTexts = new List<object>();
        private static readonly List<string> shopArtistBtnNames = new List<string>();
        private const string SHOP_HOUSE_ARTIST = "House";
        // Shop category filter: 0=All, then categories ordered "cooler and more
        // affordable first" (v1.32 item 9): Cosmetics, Name Styles, Maps, Titles.
        // Clicking a tab narrows the scroll view to that category so users don't have to
        // scroll through 90+ items to find one kind. Each tab has a description shown
        // under the tab bar so the category's purpose is discoverable.
        private static int shopCategoryFilter = 0;
        private static GameObject[] shopTabBtns;
        private static object[] shopTabTexts;
        private static object txtShopCategoryDesc;
        // Index order MUST match the filter switch in RefreshShop:
        // 0 All, 1 Cosmetics, 2 Name Styles, 3 Maps, 4 Titles, 5 Trails, 6 Body Color, 7 Cursor, 8 Effects, 9 Other.
        private static readonly string[] SHOP_TAB_NAMES = { "All", "Cosmetics", "Name Styles", "Maps", "Titles", "Trails", "Body Color", "Cursor", "Effects", "Other" };
        private static readonly string[] SHOP_TAB_DESCS = {
            "All cosmetics - everything available, grouped by category.",
            "Character cosmetics - faces, eyes, and accessories, many made by community artists. Buy here, then equip them in ROUNDS' own character editor (F8 or main menu). Visible to all modded players.",
            "Bold, italic, underline, strikethrough, and color/size modifiers applied to your player nametag in lobbies and matches. Visible to every player, modded or not.",
            "Map color schemes. Equip as many as you like and cycle between your owned colors with Left Shift in-game.",
            "Flair text shown next to your name on the leaderboard, match history, and in chat.",
            "A glowing trail that follows your character body during combat. Only visible to modded players; the shop preview shows it following your cursor.",
            "Override the default orange/blue team color with a tint of your choice. Only visible to modded players. Premium tiers (Prismatic, Chrome) animate during combat.",
            "Mouse-cursor color tint (local-only). Pick the cursor SHAPE — arrow, dot, crosshair, circle — in Settings; the tint colors whichever shape you choose.",
            "In-combat particle aura around your character. Only visible to modded players.",
            "Utility unlocks (e.g. hide your gold total on the leaderboard).",
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
            public string kind;
            // Item 1 previews: cosmetic art thumbnail (faces), 3-color scheme
            // swatches (map skins), and the admin-only "assign artist" button.
            public GameObject artImgGO;
            public object artImg;                 // Image component (reflection)
            public GameObject swatchGO;
            public object[] swatchImgs = new object[3];
            public GameObject artistBtn;
        }
        private static List<ShopRow> shopRows = new List<ShopRow>();

        private static GameObject BuildShopTab(Transform parent)
        {
            var panel = new GameObject("Shop");
            panel.transform.SetParent(parent, false);
            panel.AddComponent<RectTransform>();
            UIFactory.AddVLG(panel, spacing: 6, padL: 20, padR: 20, padT: 10, padB: 10);
            UIFactory.AddLE(panel, flexH: 1);
            MakeSubTabAnchor(4, panel.transform, true);   // round 5 item 3

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
            shopCursorHeader = CreateSectionHeader(shopRowsContainer.transform, "SHHCur",
                "<color=#9AD0FF>=  CURSOR COLORS  =</color>");
            shopEffectsHeader = CreateSectionHeader(shopRowsContainer.transform, "SHHEf",
                "<color=#C8A0FF>=  PLAYER EFFECTS  =</color>");
            shopFacesHeader = CreateSectionHeader(shopRowsContainer.transform, "SHHFc",
                "<color=#7FE8C3>=  CHARACTER COSMETICS  =</color>");
            // Bug batch item 9: clickable artist boxes under the header filter the
            // cosmetics list to one artist's creations. Populated per refresh.
            shopArtistFilterRow = new GameObject("SHArtF");
            shopArtistFilterRow.transform.SetParent(shopRowsContainer.transform, false);
            shopArtistFilterRow.AddComponent<RectTransform>();
            UIFactory.AddHLG(shopArtistFilterRow, spacing: 6, padL: 8, forceExpandH: false);
            UIFactory.AddLE(shopArtistFilterRow, prefH: 36, minH: 36, flexH: 0);  // fits the 30px artist tabs
            shopArtistFilterRow.SetActive(false);
            shopOtherHeader = CreateSectionHeader(shopRowsContainer.transform, "SHHOt",
                "<color=#FFD94D>=  OTHER  =</color>");

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

        // Click-to-highlight (Sid, July 13 item 2): the selected row's sku. Clicking
        // a row selects it (whole row tinted); clicking it again deselects. Child
        // buttons (Buy/Preview/...) win their own raycasts, so this only fires on
        // the row's empty space.
        private static string shopSelectedSku = null;
        private static readonly Color C_ROWSEL = new Color(0.20f, 0.32f, 0.47f, 0.95f);

        private static ShopRow CreateShopRow(Transform parent, int idx)
        {
            var row = new ShopRow();
            row.root = UIFactory.CreatePanel($"sr{idx}", parent, C_PANEL);
            UIFactory.AddHLG(row.root, spacing: 10, padL: 10, padR: 10, padT: 6, padB: 6, forceExpandH: true);
            UIFactory.AddLE(row.root, prefH: 44, flexH: 0);
            int rowIdxCaptured = idx;
            UIFactory.AddClick(row.root, () =>
            {
                try
                {
                    var rr = shopRows[rowIdxCaptured];
                    if (rr == null || string.IsNullOrEmpty(rr.sku)) return;
                    shopSelectedSku = (shopSelectedSku == rr.sku) ? null : rr.sku;
                    dirty = true;
                }
                catch { }
            });

            // Item 1: cosmetic art thumbnail (face items) — the actual PNG the
            // player is buying, 40x40, left of the name.
            row.artImgGO = new GameObject("art");
            row.artImgGO.transform.SetParent(row.root.transform, false);
            row.artImgGO.AddComponent<RectTransform>();
            UIFactory.AddLE(row.artImgGO, prefW: 40, minW: 40, prefH: 40, flexW: 0, flexH: 0);
            if (UIFactory.tImage != null)
            {
                row.artImg = row.artImgGO.AddComponent(UIFactory.tImage);
                try { UIFactory.tImage.GetProperty("preserveAspect", BindingFlags.Public | BindingFlags.Instance)?.SetValue(row.artImg, true); } catch { }
                try { UIFactory.tImage.GetProperty("raycastTarget", BindingFlags.Public | BindingFlags.Instance)?.SetValue(row.artImg, false); } catch { }
            }
            row.artImgGO.SetActive(false);

            // Item 1: color-scheme swatches (map skins) — primary / secondary /
            // background squares so the scheme is visible before buying.
            row.swatchGO = new GameObject("sw");
            row.swatchGO.transform.SetParent(row.root.transform, false);
            row.swatchGO.AddComponent<RectTransform>();
            UIFactory.AddHLG(row.swatchGO, spacing: 3);
            UIFactory.AddLE(row.swatchGO, prefW: 66, minW: 66, prefH: 22, flexW: 0, flexH: 0);
            for (int swi = 0; swi < 3; swi++)
            {
                var s = new GameObject($"s{swi}");
                s.transform.SetParent(row.swatchGO.transform, false);
                s.AddComponent<RectTransform>();
                UIFactory.AddLE(s, prefW: 20, minW: 20, prefH: 20, flexW: 0, flexH: 0);
                if (UIFactory.tImage != null)
                {
                    row.swatchImgs[swi] = s.AddComponent(UIFactory.tImage);
                    try { UIFactory.tImage.GetProperty("raycastTarget", BindingFlags.Public | BindingFlags.Instance)?.SetValue(row.swatchImgs[swi], false); } catch { }
                }
            }
            row.swatchGO.SetActive(false);

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
                        // Item 1: the button now serves trails AND player effects —
                        // effects preview as a cursor-following particle aura.
                        if (rr.kind == "player_effect")
                            PlayerEffectCosmetic.TogglePreview(rr.sku);
                        else
                            TrailPreview.Toggle(rr.sku, rr.previewColor, rr.previewPrice);
                        dirty = true;  // refresh button label (Preview <-> Stop)
                    }
                    catch (Exception ex) { Plugin.Log.LogWarning($"[SHOP-PREVIEW] {ex.Message}"); }
                },
                sizeDelta: new Vector2(80, 28));
            UIFactory.AddLE(row.previewBtn, prefW: 80, prefH: 28, flexW: 0, flexH: 0);
            row.previewBtnTxt = UIFactory.GetButtonText(row.previewBtn);

            // Item 1 (admin-only): assign this cosmetic to an artist — a PICKER over
            // the defined artist roster, no steam-id typing (July 12 item 3).
            row.artistBtn = UIFactory.CreateButton($"sab{idx}", row.root.transform,
                "Artist", 12f, C_WHITE, new Color(0.45f, 0.3f, 0.5f, 0.9f),
                () =>
                {
                    try
                    {
                        var rr = shopRows[captured];
                        if (rr == null || string.IsNullOrEmpty(rr.sku)) return;
                        string skuForPick = rr.sku;
                        ApiClient.FetchArtistsList(ok =>
                        {
                            var roster = ApiClient.CachedAllArtists;
                            if (roster == null || roster.Count == 0)
                            {
                                ShowArtistResult(false, "{\"detail\":\"no artists defined yet - grant the role in the Admin tab first\"}");
                                return;
                            }
                            var names = new string[roster.Count];
                            var ids = new string[roster.Count];
                            for (int ai = 0; ai < roster.Count; ai++)
                            { names[ai] = roster[ai].display_name; ids[ai] = roster[ai].steam_id; }
                            CompetitiveUI.OpenArtistPicker($"Assign artist - {skuForPick}", names, ids,
                                picked => ApiClient.AdminSetItemArtist(MatchTracker.LocalSteamId, skuForPick, picked,
                                    (ok2, resp) => ShowArtistResult(ok2, ok2 ? $"{skuForPick} assigned." : resp)));
                        });
                    }
                    catch (Exception ex) { Plugin.Log.LogWarning($"[SHOP-ARTIST] {ex.Message}"); }
                },
                sizeDelta: new Vector2(60, 28));
            UIFactory.AddLE(row.artistBtn, prefW: 60, prefH: 28, flexW: 0, flexH: 0);
            row.artistBtn.SetActive(false);

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
                        // Compare titles by SKU (active_title holds the DISPLAY name, which
                        // the dynamic Current Rank title rewrites to e.g. "Master" — name
                        // equality made an equipped rank title look unequipped, #48).
                        // Name fallback covers stats cached by a pre-1.29.1 server.
                        bool clickedActiveTitle = kind == "title" && cached != null
                            && (!string.IsNullOrEmpty(cached.active_title_sku)
                                ? cached.active_title_sku == itemSku
                                : cached.active_title == itemName);
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
                                    cached.active_title_sku = null;
                                }
                                else
                                {
                                    cached.active_title = itemName;
                                    cached.active_title_color = itemColor;
                                    cached.active_title_sku = itemSku;
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
                            else if (kind == "cursor_color")
                            {
                                bool same = cached.active_cursor_color_sku == itemSku;
                                cached.active_cursor_color_sku = same ? null : itemSku;
                                cached.active_cursor_color_hex = same ? null : itemColor;
                            }
                            else if (kind == "player_effect")
                            {
                                bool same = cached.active_player_effect_sku == itemSku;
                                cached.active_player_effect_sku = same ? null : itemSku;
                            }
                            else if (kind == "utility")
                            {
                                // Hide Gold toggle — flip the cached flag for instant UI feedback.
                                cached.hide_gold = !cached.hide_gold;
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
                            // Player effect: re-publish + re-apply mid-match so the aura swaps live.
                            if (ok && kind == "player_effect")
                            {
                                try { PlayerEffectCosmetic.PublishLocalProps(); } catch { }
                                if (GameStateWatcher.IsInMatch)
                                {
                                    try { PlayerEffectCosmetic.OnMatchEnd(); PlayerEffectCosmetic.OnMatchStart(); } catch { }
                                }
                            }
                            // Cursor color: local-only — re-apply the tinted hardware cursor immediately.
                            if (ok && kind == "cursor_color")
                            {
                                try { CursorColorCosmetic.ApplyFromStats(); } catch { }
                            }
                        };
                        if (kind == "trail") ApiClient.SetActiveTrail(id, apiItemId, cb);
                        else if (kind == "color") ApiClient.ToggleMapColor(id, r.itemId, cb);
                        else if (kind == "nametag") ApiClient.ToggleNametagStyle(id, r.itemId, cb);
                        else if (kind == "player_color")
                            // After the optimistic toggle, cached holds post-click state: sku still
                            // set → equipped (send itemId); cleared → unequipped (send 0). Without
                            // this check unequip sent the item_id back and the server re-equipped it,
                            // so the body color reverted after a second / on refresh (lopi's report).
                            ApiClient.SetActivePlayerColor(id, (cached != null && cached.active_player_color_sku == itemSku) ? r.itemId : 0L, cb);
                        else if (kind == "cursor_color")
                            // After the optimistic toggle, cached holds post-click state: sku still
                            // set → equipped (send itemId); cleared → unequipped (send 0).
                            ApiClient.SetActiveCursorColor(id, (cached != null && cached.active_cursor_color_sku == itemSku) ? r.itemId : 0L, cb);
                        else if (kind == "player_effect")
                            ApiClient.SetActivePlayerEffect(id, (cached != null && cached.active_player_effect_sku == itemSku) ? r.itemId : 0L, cb);
                        else if (kind == "utility")
                            ApiClient.SetHideGold(id, cached != null && cached.hide_gold, cb);
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
            var cursors = new List<ApiClient.ShopItemData>();
            var effects = new List<ApiClient.ShopItemData>();
            var faces = new List<ApiClient.ShopItemData>();
            var others = new List<ApiClient.ShopItemData>();
            if (rawItems != null)
            {
                foreach (var it in rawItems)
                {
                    if (it.kind == "trail") trails.Add(it);
                    else if (it.kind == "color") colors.Add(it);
                    else if (it.kind == "nametag") nametags.Add(it);
                    else if (it.kind == "player_color") pcolors.Add(it);
                    else if (it.kind == "cursor_color") cursors.Add(it);
                    else if (it.kind == "player_effect") effects.Add(it);
                    // Character cosmetics (v1.30, bug #55): their own category —
                    // Stan's report was them landing under Titles via the
                    // catch-all on 1.29.1. Purchasable here, EQUIPPED in the
                    // game's own character editor, so no Set Active button.
                    else if (it.kind == "face") faces.Add(it);
                    else if (it.kind == "utility") others.Add(it);
                    else titles.Add(it);
                }
                titles.Sort((a, b) => a.price.CompareTo(b.price));
                trails.Sort((a, b) => a.price.CompareTo(b.price));
                // Colors sort (July 12 item 3): the VANILLA skins (Sky, Poison,
                // Gold, ... — presets that just reproduce a vanilla art) group
                // together at the top, custom-designed palettes after. Price then
                // alphabetical within each group.
                colors.Sort((a, b) => {
                    bool va = CustomMapColors.IsVanillaStyled(a.sku);
                    bool vb = CustomMapColors.IsVanillaStyled(b.sku);
                    if (va != vb) return va ? -1 : 1;
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
                cursors.Sort((a, b) => a.price.CompareTo(b.price));
                effects.Sort((a, b) => a.price.CompareTo(b.price));
                faces.Sort((a, b) => a.price.CompareTo(b.price));
                others.Sort((a, b) => a.price.CompareTo(b.price));
            }
            var sorted = new List<ApiClient.ShopItemData>();
            // Apply tab filter: keep only items matching the active category. Tab 0=All
            // keeps every list; any other tab keeps ONLY its own list so the render loop
            // skips the rest and their section headers hide via the if(count>0) gate.
            // 1 Cosmetics, 2 Name Styles, 3 Maps, 4 Titles, 5 Trails, 6 Body Color, 7 Cursor, 8 Effects, 9 Other.
            if (shopCategoryFilter != 0)
            {
                if (shopCategoryFilter != 1) faces.Clear();
                if (shopCategoryFilter != 2) nametags.Clear();
                if (shopCategoryFilter != 3) colors.Clear();
                if (shopCategoryFilter != 4) titles.Clear();
                if (shopCategoryFilter != 5) trails.Clear();
                if (shopCategoryFilter != 6) pcolors.Clear();
                if (shopCategoryFilter != 7) cursors.Clear();
                if (shopCategoryFilter != 8) effects.Clear();
                if (shopCategoryFilter != 9) others.Clear();
            }

            sorted.AddRange(faces);
            sorted.AddRange(nametags);
            sorted.AddRange(colors);
            sorted.AddRange(titles);
            sorted.AddRange(trails);
            sorted.AddRange(pcolors);
            sorted.AddRange(cursors);
            sorted.AddRange(effects);
            sorted.AddRange(others);

            // Slot ordering inside the container (VLG renders in sibling order):
            //   [Titles header][title rows...][Trails header][trail rows...][Colors header][color rows...]
            int sibling = 0;
            // Render order matches the tab order (v1.32 item 9):
            // Cosmetics, Name Styles, Maps, Titles, Trails, Body Color, Cursor, Effects, Other.
            int rowIdx = 0;
            if (faces.Count > 0 && shopFacesHeader != null)
            {
                shopFacesHeader.SetActive(true);
                shopFacesHeader.transform.SetSiblingIndex(sibling++);
            }
            else if (shopFacesHeader != null) shopFacesHeader.SetActive(false);
            // Bug batch item 9: artist filter boxes + filtered face list. The row
            // only appears when at least one cosmetic has a real artist credit.
            var facesShown = faces;
            {
                bool anyCredited = false;
                var artistNames = new List<string>();
                foreach (var f in faces)
                {
                    string an = string.IsNullOrEmpty(f.artist_name) ? SHOP_HOUSE_ARTIST : f.artist_name;
                    if (!string.IsNullOrEmpty(f.artist_name)) anyCredited = true;
                    if (!artistNames.Contains(an)) artistNames.Add(an);
                }
                bool showFilter = faces.Count > 0 && anyCredited && shopArtistFilterRow != null;
                if (shopArtistFilterRow != null) shopArtistFilterRow.SetActive(showFilter);
                if (showFilter)
                {
                    artistNames.Sort(StringComparer.OrdinalIgnoreCase);
                    // "House" sorts with the rest; pin it last so real artists lead.
                    if (artistNames.Remove(SHOP_HOUSE_ARTIST)) artistNames.Add(SHOP_HOUSE_ARTIST);
                    var btnNames = new List<string> { "" };  // "" = All
                    btnNames.AddRange(artistNames);
                    SyncShopArtistFilterButtons(btnNames);
                    shopArtistFilterRow.transform.SetSiblingIndex(sibling++);
                    if (!string.IsNullOrEmpty(shopArtistFilter))
                    {
                        facesShown = faces.FindAll(f =>
                            (string.IsNullOrEmpty(f.artist_name) ? SHOP_HOUSE_ARTIST : f.artist_name) == shopArtistFilter);
                        if (facesShown.Count == 0) { shopArtistFilter = null; facesShown = faces; }
                    }
                }
                else shopArtistFilter = null;
            }
            for (int i = 0; i < facesShown.Count && rowIdx < shopRows.Count; i++, rowIdx++)
            {
                ApplyShopRow(shopRows[rowIdx], facesShown[i], balance, s);
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

            if (titles.Count > 0 && shopTitlesHeader != null)
            {
                shopTitlesHeader.SetActive(true);
                shopTitlesHeader.transform.SetSiblingIndex(sibling++);
            }
            else if (shopTitlesHeader != null) shopTitlesHeader.SetActive(false);
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

            if (cursors.Count > 0 && shopCursorHeader != null)
            {
                shopCursorHeader.SetActive(true);
                shopCursorHeader.transform.SetSiblingIndex(sibling++);
            }
            else if (shopCursorHeader != null) shopCursorHeader.SetActive(false);
            for (int i = 0; i < cursors.Count && rowIdx < shopRows.Count; i++, rowIdx++)
            {
                ApplyShopRow(shopRows[rowIdx], cursors[i], balance, s);
                shopRows[rowIdx].root.transform.SetSiblingIndex(sibling++);
            }

            if (effects.Count > 0 && shopEffectsHeader != null)
            {
                shopEffectsHeader.SetActive(true);
                shopEffectsHeader.transform.SetSiblingIndex(sibling++);
            }
            else if (shopEffectsHeader != null) shopEffectsHeader.SetActive(false);
            for (int i = 0; i < effects.Count && rowIdx < shopRows.Count; i++, rowIdx++)
            {
                ApplyShopRow(shopRows[rowIdx], effects[i], balance, s);
                shopRows[rowIdx].root.transform.SetSiblingIndex(sibling++);
            }

            if (others.Count > 0 && shopOtherHeader != null)
            {
                shopOtherHeader.SetActive(true);
                shopOtherHeader.transform.SetSiblingIndex(sibling++);
            }
            else if (shopOtherHeader != null) shopOtherHeader.SetActive(false);
            for (int i = 0; i < others.Count && rowIdx < shopRows.Count; i++, rowIdx++)
            {
                ApplyShopRow(shopRows[rowIdx], others[i], balance, s);
                shopRows[rowIdx].root.transform.SetSiblingIndex(sibling++);
            }

            // Hide leftovers. Bound on rowIdx (rows actually filled this pass),
            // not sorted.Count — the artist filter can shrink the face section,
            // and stale rows between the two counts would keep old content.
            for (int i = rowIdx; i < shopRows.Count; i++)
                shopRows[i].root.SetActive(false);
        }

        // Bug batch item 9: pooled filter buttons. names[0] is "" (All); the rest
        // are artist display names. onClick reads the CURRENT name via the parallel
        // list so pooled buttons survive roster changes between refreshes.
        private static void SyncShopArtistFilterButtons(List<string> names)
        {
            while (shopArtistBtns.Count < names.Count)
            {
                int ii = shopArtistBtns.Count;
                // 16pt / 150x30 (was 13pt / 120x24): the artist tabs are the section's
                // primary navigation and read undersized next to the row text (Sid,
                // July 13 item 2 — text is already bold via CreateText's default).
                var b = UIFactory.CreateButton($"shArt{ii}", shopArtistFilterRow.transform, "", 16f, C_LABEL, C_BTN,
                    () =>
                    {
                        string v = ii < shopArtistBtnNames.Count ? shopArtistBtnNames[ii] : "";
                        shopArtistFilter = string.IsNullOrEmpty(v) ? null : v;
                        dirty = true;
                    }, sizeDelta: new Vector2(150, 30));
                shopArtistBtns.Add(b);
                shopArtistBtnTexts.Add(UIFactory.GetButtonText(b));
            }
            while (shopArtistBtnNames.Count < shopArtistBtns.Count) shopArtistBtnNames.Add("");
            for (int i = 0; i < shopArtistBtns.Count; i++)
            {
                bool used = i < names.Count;
                shopArtistBtns[i].SetActive(used);
                if (!used) continue;
                shopArtistBtnNames[i] = names[i];
                bool active = string.IsNullOrEmpty(names[i]) ? shopArtistFilter == null : shopArtistFilter == names[i];
                UIFactory.SetText(shopArtistBtnTexts[i], string.IsNullOrEmpty(names[i]) ? "All" : names[i]);
                UIFactory.SetImageColor(shopArtistBtns[i], active ? C_TABACT : C_BTN);
                UIFactory.SetColor(shopArtistBtnTexts[i], active ? C_WHITE : C_LABEL);
            }
        }

        // Bug #63: shop-item NAME colors get a lightness floor so dark preview
        // colors (deep map-skin hues) stay readable on the dark panel.
        private static string ReadableNameColor(string hex)
        {
            if (string.IsNullOrEmpty(hex)) return "#FFFFFF";
            Color c;
            if (!ColorUtility.TryParseHtmlString(hex.StartsWith("#") ? hex : "#" + hex, out c)) return "#FFFFFF";
            float lum = 0.299f * c.r + 0.587f * c.g + 0.114f * c.b;
            if (lum < 0.45f) c = Color.Lerp(c, Color.white, (0.45f - lum) / 0.45f * 0.8f);
            return "#" + ColorUtility.ToHtmlStringRGB(c);
        }

        private static void ApplyShopRow(ShopRow r, ApiClient.ShopItemData it, int balance, ApiClient.PlayerStatsData s)
        {
            r.itemId = it.id;
            r.sku = it.sku;
            r.kind = it.kind;
            // Click-to-highlight: tint the whole row while selected. Rows are
            // pooled, so both states must be asserted on every fill.
            UIFactory.SetImageColor(r.root, (!string.IsNullOrEmpty(shopSelectedSku) && shopSelectedSku == it.sku) ? C_ROWSEL : C_PANEL);
            // Bug #63 (lopidav): dark preview colors made some NAMES unreadable on
            // the dark panel — floor the name color's lightness (swatches/art
            // elsewhere keep the true color).
            string col = ReadableNameColor(it.preview_color);
            // Item 9: artist credit inline — makes the by-artist grouping legible.
            string artistTag = !string.IsNullOrEmpty(it.artist_name) ? $"  <color=#7FE8C3>by {it.artist_name}</color>" : "";
            UIFactory.SetText(r.txtName, $"<color={col}>{it.name}</color>  <color=#888>({it.rarity})</color>{artistTag}");

            // Item 1 previews. Face items: the actual PNG art. Map skins: the
            // designed color scheme as primary/secondary/background swatches.
            bool showArt = false;
            if (it.kind == "face" && r.artImg != null)
            {
                var sp = CustomCosmetics.GetShopSprite(it.sku);
                if (sp != null)
                {
                    try
                    {
                        UIFactory.tImage.GetProperty("sprite", BindingFlags.Public | BindingFlags.Instance)?.SetValue(r.artImg, sp);
                        UIFactory.tImage.GetProperty("color", BindingFlags.Public | BindingFlags.Instance)?.SetValue(r.artImg, Color.white);
                        showArt = true;
                        // Bug #74: cycle animated skus' thumbnails; static skus
                        // clear any stale registration this pooled row had.
                        var frames = CustomCosmetics.GetShopFrames(it.sku, out float thumbFps);
                        TrackAnimatedThumb(r.artImg, frames, thumbFps);
                    }
                    catch { }
                }
            }
            // July 21 item 9: Body Color rows get a character glyph preview
            // (circle + hands + feet in the ACTUAL color — the name text uses
            // ReadableNameColor which deliberately distorts dark colors). Served
            // white (outline is baked). Rows stay 44px — the glyph fits the
            // already-reserved 40x40 slot.
            else if (it.kind == "player_color" && r.artImg != null)
            {
                var sp = GetBodyGlyphSprite(it.sku, it.preview_color);
                if (sp != null)
                {
                    try
                    {
                        UIFactory.tImage.GetProperty("sprite", BindingFlags.Public | BindingFlags.Instance)?.SetValue(r.artImg, sp);
                        UIFactory.tImage.GetProperty("color", BindingFlags.Public | BindingFlags.Instance)?.SetValue(r.artImg, Color.white);
                        showArt = true;
                    }
                    catch { }
                }
                TrackAnimatedThumb(r.artImg, null, 0f);   // pooled row: clear any face-frame registration
            }
            else if (r.artImg != null) TrackAnimatedThumb(r.artImg, null, 0f);
            if (r.artImgGO != null && r.artImgGO.activeSelf != showArt) r.artImgGO.SetActive(showArt);
            // Cosmetic art x2 (Sid, July 13 item 2): face rows get an 80x80 art
            // thumbnail and a taller row; every other kind resets to the 40/44
            // base because rows are pooled and reused across kinds. The bigArt
            // split is load-bearing (July 21 item 9): body-color glyphs set
            // showArt but must NOT double every row's height.
            bool bigArt = showArt && it.kind == "face";
            if (r.artImgGO != null) UIFactory.SetPrefWH(r.artImgGO, bigArt ? 80 : 40, bigArt ? 80 : 40);
            UIFactory.SetPrefH(r.root, bigArt ? 88 : 44);
            bool showSwatches = false;
            if (it.kind == "color" && r.swatchGO != null && CustomMapColors.IsCustomSku(it.sku))
            {
                var prim = CustomMapColors.GetMapBlockColor(it.sku);
                var sec = CustomMapColors.GetSecondaryColor(it.sku);
                var bg = CustomMapColors.GetBackgroundColor(it.sku);
                var swCols = new Color[] {
                    prim ?? Color.grey,
                    sec,
                    bg ?? new Color(0.25f, 0.28f, 0.35f),
                };
                for (int swi = 0; swi < 3 && swi < r.swatchImgs.Length; swi++)
                {
                    if (r.swatchImgs[swi] == null) continue;
                    try
                    {
                        var c2 = swCols[swi]; c2.a = 1f;
                        UIFactory.tImage.GetProperty("color", BindingFlags.Public | BindingFlags.Instance)?.SetValue(r.swatchImgs[swi], c2);
                    }
                    catch { }
                }
                showSwatches = true;
            }
            if (r.swatchGO != null && r.swatchGO.activeSelf != showSwatches) r.swatchGO.SetActive(showSwatches);
            if (r.artistBtn != null)
            {
                // Cosmetics only (Sid July 12 item 3) — artist assignment is a
                // character-cosmetic concept, not a titles/trails one.
                bool showArtistBtn = ApiClient.IsAdmin && it.kind == "face";
                if (r.artistBtn.activeSelf != showArtistBtn) r.artistBtn.SetActive(showArtistBtn);
            }
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
                string desc = it.description ?? "";
                // Limited-stock counter (v1.30). The artist byline lives on the
                // NAME line only now (round 3 item 1 — twice per row was noise).
                if (it.stock_limit < 0)
                {
                    // Round 3 item 2: newly-approved community cosmetics are born
                    // out of stock until the artist opens sales.
                    desc += "  <color=#FF6666>(OUT OF STOCK - artist hasn't opened sales yet)</color>";
                }
                else if (it.stock_limit > 0)
                {
                    int left = Math.Max(0, it.stock_limit - it.stock_sold);
                    desc += left > 0
                        ? $"  <color=#FFD94D>({left} of {it.stock_limit} left)</color>"
                        : "  <color=#FF6666>(SOLD OUT)</color>";
                }
                if (it.kind == "face")
                    desc += "  <color=#888>(equip in the character editor)</color>";
                UIFactory.SetText(r.txtDesc, desc);
                // Recycled row - if it was previously showing a glow / typeface preview,
                // restore the originals in the same order as apply (font first, glow second).
                NametagFontRenderer.ApplyFontToLabel(r.txtDesc, "", shopPreviewOriginalFonts);
                NametagGlowRenderer.ApplyGlowToLabel(r.txtDesc, "", shopPreviewOriginalMats, shopPreviewGlowMatCache);
            }
            UIFactory.SetText(r.txtPrice, $"{it.price}g");

            bool ownsThis = it.owned;
            bool canAfford = balance >= it.price;
            bool soldOut = !ownsThis && it.stock_limit > 0 && it.stock_sold >= it.stock_limit;
            if (ownsThis) UIFactory.SetColor(r.txtPrice, C_GREEN);
            else if (canAfford) UIFactory.SetColor(r.txtPrice, C_GOLD);
            else UIFactory.SetColor(r.txtPrice, C_DIM);

            r.buyBtn.SetActive(!ownsThis);
            if (r.buyBtnTxt != null)
            {
                UIFactory.SetText(r.buyBtnTxt, soldOut ? "Sold out" : "Buy");
                UIFactory.SetColor(r.buyBtnTxt, (canAfford && !soldOut) ? C_WHITE : new Color(0.55f, 0.55f, 0.6f));
                UIFactory.SetImageColor(r.buyBtn, (canAfford && !soldOut)
                    ? new Color(0.25f, 0.45f, 0.18f, 0.9f)
                    : new Color(0.25f, 0.25f, 0.28f, 0.8f));
            }
            r.setActiveBtn.SetActive(ownsThis && (it.kind == "title" || it.kind == "trail" || it.kind == "color" || it.kind == "nametag" || it.kind == "player_color" || it.kind == "cursor_color" || it.kind == "player_effect" || it.kind == "utility"));
            // Sku compare, name fallback for pre-1.29.1 server payloads: the dynamic
            // Current Rank title's DISPLAY name is rewritten to the live rank, so name
            // equality showed it unequipped while equipped (#48).
            bool isActiveTitle = s != null && it.kind == "title"
                && (!string.IsNullOrEmpty(s.active_title_sku)
                    ? s.active_title_sku == it.sku
                    : s.active_title == it.name);
            bool isActiveTrail = s != null && it.kind == "trail" && s.active_trail_sku == it.sku;
            bool isActiveColor = s != null && it.kind == "color"
                && s.active_color_skus != null && s.active_color_skus.Contains(it.sku);
            bool isActiveNametag = s != null && it.kind == "nametag" && s.active_nametag_skus != null
                && s.active_nametag_skus.Contains(it.sku);
            bool isActivePlayerColor = s != null && it.kind == "player_color" && s.active_player_color_sku == it.sku;
            bool isActiveCursor = s != null && it.kind == "cursor_color" && s.active_cursor_color_sku == it.sku;
            bool isActiveEffect = s != null && it.kind == "player_effect" && s.active_player_effect_sku == it.sku;
            // Utility (hide-gold) is a stateful toggle, not an equip — "active" means the mask is ON.
            bool isActiveUtility = s != null && it.kind == "utility" && it.sku == "util_hide_gold" && s.hide_gold;
            bool isActive = isActiveTitle || isActiveTrail || isActiveColor || isActiveNametag
                || isActivePlayerColor || isActiveCursor || isActiveEffect || isActiveUtility;
            if (r.setActiveBtn != null)
            {
                UIFactory.SetImageColor(r.setActiveBtn, isActive
                    ? new Color(0.2f, 0.55f, 0.2f, 0.95f)   // active = green
                    : new Color(0.3f, 0.3f, 0.5f, 0.9f));   // inactive = default
                var txtComp = UIFactory.GetButtonText(r.setActiveBtn);
                // Colors are multi-equip (cycle via Shift) and nametags are stackable so
                // their "active" label is "Remove" - clicking removes from the equipped set.
                // Titles/trails/player-colors/cursor/effects are single-active; clicking the
                // equipped one unequips it. Utility (hide-gold) is a plain on/off toggle.
                bool isMultiEquip = it.kind == "nametag" || it.kind == "color";
                if (txtComp != null)
                {
                    if (it.kind == "utility")
                        UIFactory.SetText(txtComp, isActiveUtility ? "Show Gold" : "Hide Gold");
                    else
                        UIFactory.SetText(txtComp,
                            isActive
                                ? (isMultiEquip ? "Remove" : "Unequip")
                                : (isMultiEquip ? "Equip" : "Set Active"));
                }
            }

            // Preview button - trails AND player effects (item 1). Stash the color +
            // price on the row so the click handler has everything without re-lookup.
            if (r.previewBtn != null)
            {
                bool isTrail = it.kind == "trail";
                bool isEffect = it.kind == "player_effect";
                r.previewBtn.SetActive(isTrail || isEffect);
                if (isTrail || isEffect)
                {
                    r.previewColor = it.preview_color ?? "";
                    r.previewPrice = it.price;
                    bool previewingThis = isTrail
                        ? (TrailPreview.IsActive && TrailPreview.ActiveSku == it.sku)
                        : (PlayerEffectCosmetic.PreviewSku == it.sku);
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
        private static GameObject fpsToggleBtn, pingToggleBtn, ingameChatToggleBtn, trailToggleBtn, blockDbgToggleBtn, playerColorToggleBtn, inputOverlayToggleBtn, cursorShapeBtn;
        private static GameObject appearOfflineBtn; private static object appearOfflineTxt;
        private static GameObject showDiscordBtn; private static object showDiscordTxt;
        // v1.32 items 7+8 toggle rows.
        private static GameObject screenShakeToggleBtn, mapLightingToggleBtn, mapShadowsToggleBtn, animCosToggleBtn;
        private static object screenShakeToggleTxt, mapLightingToggleTxt, mapShadowsToggleTxt, animCosToggleTxt;
        // July 20 item 8: chromatic aberration toggle row.
        private static GameObject chromAbToggleBtn;
        private static object chromAbToggleTxt;
        private static object consentToggleTxt, notifToggleTxt, fpsToggleTxt, pingToggleTxt, ingameChatToggleTxt, trailToggleTxt, blockDbgToggleTxt, playerColorToggleTxt, inputOverlayToggleTxt, cursorShapeTxt;
        // v1.26.8 perf-pass toggles. Master + 7 per-patch flags; renders in a
        // collapsible section at the bottom of the Settings panel.
        private static GameObject perfMasterBtn, perfStunBtn, perfBulletsBtn, perfHitSndBtn, perfColorGhBtn, perfEdgeBnBtn, perfTagBtn, perfMenuBtn;
        private static object perfMasterTxt, perfStunTxt, perfBulletsTxt, perfHitSndTxt, perfColorGhTxt, perfEdgeBnTxt, perfTagTxt, perfMenuTxt;
        // v1.26.9 additions (cap-style perf wins).
        private static GameObject perfBulletCapBtn, perfPoolBtn;
        private static object perfBulletCapTxt, perfPoolTxt;
        private static bool _perfSectionOpen = false;
        private static object _perfSectionHeaderTxt;
        private static GameObject _perfSectionBody;
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
            // Outer fills the tab area; scroll view eats all extra height so the
            // contents auto-size and any added rows just extend the scrollable
            // region instead of squeezing every existing button smaller. The
            // user reported having to resize text/buttons to fit the perf
            // toggles — the scroll wrap fixes that for any future additions.
            var outer = new GameObject("SettingsOuter");
            outer.transform.SetParent(parent, false);
            outer.AddComponent<RectTransform>();
            UIFactory.AddVLG(outer, spacing: 0);
            UIFactory.AddLE(outer, flexH: 1);
            var scroll = UIFactory.CreateScrollView("SettingsScroll", outer.transform, spacing: 0);
            UIFactory.AddLE(scroll.scrollGO, flexH: 1);

            var panel = new GameObject("Settings");
            panel.transform.SetParent(scroll.content.transform, false);
            panel.AddComponent<RectTransform>();
            UIFactory.AddVLG(panel, spacing: 10, padL: 20, padR: 20, padT: 10, padB: 10);
            // flexH:0 so the panel sizes to its content height (the scroll viewport
            // handles overflow). flexH:1 here would collapse children with no prefH
            // (learning #63).
            UIFactory.AddLE(panel, flexH: 0);

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
            /* Appear-offline (v1.33): server-synced privacy toggle — hides the
             * player from the Home tab's online / recently-online lists.
             * Optimistic flip on the cached stats; FetchPlayerStats in the
             * SetAppearOffline callback reconciles with the server truth. */
            appearOfflineBtn = SettingsButton(dispBox.transform, "SAppOff", "",
                C_WHITE, C_BTN, new Vector2(340, 28),
                () =>
                {
                    var st = ApiClient.CachedPlayerStats;
                    var id = MatchTracker.LocalSteamId;
                    if (st == null || string.IsNullOrEmpty(id) || id == "unknown") return;
                    Plugin.Log.LogInfo("[SETTINGS] appear-offline toggled");
                    st.appear_offline = !st.appear_offline;
                    dirty = true;
                    ApiClient.SetAppearOffline(id, st.appear_offline, (ok, resp) =>
                    {
                        if (!ok) CompetitiveUI.ShowNotification("Appear-offline update failed - try again", Color.yellow, 3f);
                        dirty = true;
                    });
                });
            appearOfflineTxt = UIFactory.GetButtonText(appearOfflineBtn);
            /* July 22 item 8: opt-IN "show my Discord on the leaderboard" —
             * server-synced like appear-offline, default OFF. */
            showDiscordBtn = SettingsButton(dispBox.transform, "SShowDc", "",
                C_WHITE, C_BTN, new Vector2(340, 28),
                () =>
                {
                    var st = ApiClient.CachedPlayerStats;
                    var id = MatchTracker.LocalSteamId;
                    if (st == null || string.IsNullOrEmpty(id) || id == "unknown") return;
                    if (string.IsNullOrEmpty(st.discord_username) && string.IsNullOrEmpty(st.discord_id))
                    {
                        CompetitiveUI.ShowNotification("Link your Discord first (Home tab)", Color.yellow, 4f);
                        return;
                    }
                    Plugin.Log.LogInfo("[SETTINGS] show-discord toggled");
                    st.show_discord = !st.show_discord;
                    dirty = true;
                    ApiClient.SetShowDiscord(id, st.show_discord, (ok, resp) =>
                    {
                        if (!ok) CompetitiveUI.ShowNotification("Show-Discord update failed - try again", Color.yellow, 3f);
                        dirty = true;
                    });
                });
            showDiscordTxt = UIFactory.GetButtonText(showDiscordBtn);
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
            // Cursor shape cycler (local-only). Combines with the equipped cursor color.
            cursorShapeBtn = SettingsButton(dispBox.transform, "SCursor", "",
                C_WHITE, C_BTN, new Vector2(260, 28),
                () => { CursorColorCosmetic.CycleShape(); dirty = true; });
            cursorShapeTxt = UIFactory.GetButtonText(cursorShapeBtn);
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
                    try { PlayerEffectCosmetic.OnShowPlayerColorsToggled(); } catch { }
                    dirty = true;
                });
            playerColorToggleTxt = UIFactory.GetButtonText(playerColorToggleBtn);

            // -- Input overlay (WASD + Space + mouse buttons) --
            UIFactory.CreateText("SInpOvL", dispBox.transform,
                "Input overlay (bottom-left): shows W/A/S/D/Space and L/R click. Keys glow red when pressed. Useful for streams or diagnosing missed inputs.",
                13f, C_DIM, sizeDelta: new Vector2(700, 34));
            inputOverlayToggleBtn = SettingsButton(dispBox.transform, "SInpOv", "",
                C_WHITE, C_BTN, new Vector2(260, 28),
                () =>
                {
                    Plugin.Log.LogInfo("[SETTINGS] Input overlay toggled");
                    Plugin.ShowInputOverlay.Value = !Plugin.ShowInputOverlay.Value;
                    dirty = true;
                });
            inputOverlayToggleTxt = UIFactory.GetButtonText(inputOverlayToggleBtn);

            // -- Screen shake (v1.32 item 7) --
            UIFactory.CreateText("SShakeL", dispBox.transform,
                "Camera screen shake on shots/hits/deaths. Off = a perfectly steady camera (local only).",
                13f, C_DIM, sizeDelta: new Vector2(700, 20));
            screenShakeToggleBtn = SettingsButton(dispBox.transform, "SShake", "",
                C_WHITE, C_BTN, new Vector2(260, 28),
                () =>
                {
                    Plugin.Log.LogInfo("[SETTINGS] Screen shake toggled");
                    Plugin.ScreenShakeEnabled.Value = !Plugin.ScreenShakeEnabled.Value;
                    dirty = true;
                });
            screenShakeToggleTxt = UIFactory.GetButtonText(screenShakeToggleBtn);

            // -- Map lighting (v1.32 item 7) --
            UIFactory.CreateText("SLightL", dispBox.transform,
                "Map lighting: the per-frame lightmap render. Off = flat full-bright scene, skips the whole pass for extra FPS.",
                13f, C_DIM, sizeDelta: new Vector2(700, 20));
            mapLightingToggleBtn = SettingsButton(dispBox.transform, "SLight", "",
                C_WHITE, C_BTN, new Vector2(260, 28),
                () =>
                {
                    Plugin.Log.LogInfo("[SETTINGS] Map lighting toggled");
                    Plugin.MapLightingEnabled.Value = !Plugin.MapLightingEnabled.Value;
                    try { MapPhysicalColorPatch.RenderPerfSettings.Apply(); MapPhysicalColorPatch.RenderPerfSettings.ApplyBackdrop(); } catch { }
                    dirty = true;
                });
            mapLightingToggleTxt = UIFactory.GetButtonText(mapLightingToggleBtn);

            // -- Map shadows (v1.32 item 7) --
            UIFactory.CreateText("SShadL", dispBox.transform,
                "Soft shadow beams cast by map lighting. Off = skips the shadow render pass (lighting stays) for extra FPS.",
                13f, C_DIM, sizeDelta: new Vector2(700, 20));
            mapShadowsToggleBtn = SettingsButton(dispBox.transform, "SShad", "",
                C_WHITE, C_BTN, new Vector2(260, 28),
                () =>
                {
                    Plugin.Log.LogInfo("[SETTINGS] Map shadows toggled");
                    Plugin.MapShadowsEnabled.Value = !Plugin.MapShadowsEnabled.Value;
                    try { MapPhysicalColorPatch.RenderPerfSettings.Apply(); MapPhysicalColorPatch.RenderPerfSettings.ApplyBackdrop(); } catch { }
                    dirty = true;
                });
            mapShadowsToggleTxt = UIFactory.GetButtonText(mapShadowsToggleBtn);

            // -- Animated cosmetics (v1.32 item 8) --
            UIFactory.CreateText("SAnimCosL", dispBox.transform,
                "Animated cosmetics: prismatic/chrome body colors, prism trail, player effects, map-skin shimmer, animated faces. Off = all freeze to a static frame instantly.",
                13f, C_DIM, sizeDelta: new Vector2(700, 34));
            animCosToggleBtn = SettingsButton(dispBox.transform, "SAnimCos", "",
                C_WHITE, C_BTN, new Vector2(260, 28),
                () =>
                {
                    Plugin.Log.LogInfo("[SETTINGS] Animated cosmetics toggled");
                    Plugin.AnimatedCosmetics.Value = !Plugin.AnimatedCosmetics.Value;
                    try { PlayerEffectCosmetic.OnAnimatedCosmeticsToggled(); } catch { }
                    dirty = true;
                });
            animCosToggleTxt = UIFactory.GetButtonText(animCosToggleBtn);

            // -- Chromatic aberration (July 20 item 8) --
            UIFactory.CreateText("SChromAbL", dispBox.transform,
                "Chromatic aberration: the RGB color-fringing that pulses on shots/hits/deaths. Off = crisp edges, tiny FPS gain. Visual only, local only.",
                13f, C_DIM, sizeDelta: new Vector2(700, 20));
            chromAbToggleBtn = SettingsButton(dispBox.transform, "SChromAb", "",
                C_WHITE, C_BTN, new Vector2(260, 28),
                () =>
                {
                    Plugin.Log.LogInfo("[SETTINGS] Chromatic aberration toggled");
                    Plugin.ChromaticAberrationEnabled.Value = !Plugin.ChromaticAberrationEnabled.Value;
                    try { MapPhysicalColorPatch.ChromaticAberrationSetting.Apply(); } catch { }
                    dirty = true;
                });
            chromAbToggleTxt = UIFactory.GetButtonText(chromAbToggleBtn);

            // ── Performance toggles (v1.26.8) ──
            // Collapsible — header is the click-to-expand line. Each row maps
            // 1:1 to a BepInEx config flag in Plugin.PerfXYZ. Same logic as
            // PerfGate.Check: master must be on AND the per-patch flag must
            // be on for the patch to fire.
            var perfBox = UIFactory.CreatePanel("SPerfB", dispBox.transform, C_PANEL);
            UIFactory.AddVLG(perfBox, spacing: 2, padL: 8, padR: 8, padT: 6, padB: 6);
            UIFactory.AddLE(perfBox, flexH: 0);
            var perfHdrBtn = SettingsButton(perfBox.transform, "SPerfH", "",
                new Color(1f, 0.85f, 0.4f), C_BTN, new Vector2(700, 28),
                () =>
                {
                    _perfSectionOpen = !_perfSectionOpen;
                    if (_perfSectionBody != null) _perfSectionBody.SetActive(_perfSectionOpen);
                    dirty = true;
                });
            _perfSectionHeaderTxt = UIFactory.GetButtonText(perfHdrBtn);
            _perfSectionBody = new GameObject("SPerfBody");
            _perfSectionBody.transform.SetParent(perfBox.transform, false);
            _perfSectionBody.AddComponent<RectTransform>();
            UIFactory.AddVLG(_perfSectionBody, spacing: 3, padL: 4, padR: 4, padT: 4, padB: 4);
            UIFactory.AddLE(_perfSectionBody, flexH: 0);
            _perfSectionBody.SetActive(_perfSectionOpen);

            // Each row: a short label + a small toggle button on the right.
            void AddPerfRow(string id, string label, UnityEngine.Events.UnityAction onClick, out GameObject btnOut, out object txtOut)
            {
                UIFactory.CreateText("SPerfL_" + id, _perfSectionBody.transform,
                    "<color=#AAAAAA>" + label + "</color>",
                    12f, C_DIM, sizeDelta: new Vector2(700, 18));
                btnOut = SettingsButton(_perfSectionBody.transform, "SPerf_" + id, "",
                    C_WHITE, C_BTN, new Vector2(280, 22), onClick);
                txtOut = UIFactory.GetButtonText(btnOut);
            }

            AddPerfRow("Master", "Performance master switch — flips ALL the patches below at once.",
                () => { if (Plugin.PerfOptimizations != null) { Plugin.PerfOptimizations.Value = !Plugin.PerfOptimizations.Value; dirty = true; } },
                out perfMasterBtn, out perfMasterTxt);
            AddPerfRow("Stun", "StunPlayer null-guard — stops NRE spam when a player is destroyed mid-stun.",
                () => { if (Plugin.PerfStunPlayerNullGuard != null) { Plugin.PerfStunPlayerNullGuard.Value = !Plugin.PerfStunPlayerNullGuard.Value; dirty = true; } },
                out perfStunBtn, out perfStunTxt);
            AddPerfRow("OOB", "Despawn off-screen bullets — host clears bullets that exit the camera viewport.",
                () => { if (Plugin.PerfDespawnOffscreenBullets != null) { Plugin.PerfDespawnOffscreenBullets.Value = !Plugin.PerfDespawnOffscreenBullets.Value; dirty = true; } },
                out perfBulletsBtn, out perfBulletsTxt);
            AddPerfRow("HitSnd", "Swallow RayHitBulletSound NREs from destroyed parents.",
                () => { if (Plugin.PerfSwallowHitSoundNREs != null) { Plugin.PerfSwallowHitSoundNREs.Value = !Plugin.PerfSwallowHitSoundNREs.Value; dirty = true; } },
                out perfHitSndBtn, out perfHitSndTxt);
            // ("ColorGh" + "Tag" rows removed v1.28.2 — their patches were
            // old-game ports whose targets no longer exist; see PerfPatches.cs)
            AddPerfRow("EdgeBn", "Swallow ScreenEdgeBounce NREs from destroyed bullets.",
                () => { if (Plugin.PerfSwallowEdgeBounceNREs != null) { Plugin.PerfSwallowEdgeBounceNREs.Value = !Plugin.PerfSwallowEdgeBounceNREs.Value; dirty = true; } },
                out perfEdgeBnBtn, out perfEdgeBnTxt);
            AddPerfRow("Menu", "Skip MenuControllerHandler.Update during an active match.",
                () => { if (Plugin.PerfSkipMenuUpdateInMatch != null) { Plugin.PerfSkipMenuUpdateInMatch.Value = !Plugin.PerfSkipMenuUpdateInMatch.Value; dirty = true; } },
                out perfMenuBtn, out perfMenuTxt);
            AddPerfRow("BulletCap", "Cap bullet-hit particles at 2/frame — biggest user-visible win on heavy firefights.",
                () => { if (Plugin.PerfBulletHitParticleCap != null) { Plugin.PerfBulletHitParticleCap.Value = !Plugin.PerfBulletHitParticleCap.Value; dirty = true; } },
                out perfBulletCapBtn, out perfBulletCapTxt);
            AddPerfRow("PoolInit", "Clamp ObjectPool init-spawn to 4 in-match — reduces frame stutter from new pool allocation.",
                () => { if (Plugin.PerfClampObjectPoolInit != null) { Plugin.PerfClampObjectPoolInit.Value = !Plugin.PerfClampObjectPoolInit.Value; dirty = true; } },
                out perfPoolBtn, out perfPoolTxt);
            // "CardPickPart" row removed v1.28.3 — pausing the pick-phase skin
            // particles made the picker's body invisible (bug #29).

            // -- Chat pop-up notifications --
            var notifBox = UIFactory.CreatePanel("SNB", panel.transform, C_PANEL);
            UIFactory.AddVLG(notifBox, spacing: 4, padL: 12, padR: 12, padT: 8, padB: 8);
            UIFactory.AddLE(notifBox, flexH: 0);
            UIFactory.CreateText("SNL", notifBox.transform,
                "Chat log notifications", 17f, new Color(0.7f, 0.85f, 1f),
                sizeDelta: new Vector2(700, 24));
            UIFactory.CreateText("SND", notifBox.transform,
                "On-screen pop-ups for incoming chat + XP / level notifications. Chat log on the Home tab still updates either way.",
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

            // -- Bug report --
            var bugBox = UIFactory.CreatePanel("SBugB", panel.transform, C_PANEL);
            UIFactory.AddVLG(bugBox, spacing: 4, padL: 12, padR: 12, padT: 8, padB: 8);
            UIFactory.AddLE(bugBox, flexH: 0);
            UIFactory.CreateText("SBugL", bugBox.transform,
                "Report a bug", 17f, new Color(1f, 0.9f, 0.6f),
                sizeDelta: new Vector2(700, 24));
            UIFactory.CreateText("SBugD", bugBox.transform,
                "Send a bug report straight to the mod team — description, severity, and optionally your game logs. Use the Preview button to see what gets attached.",
                13f, C_DIM, sizeDelta: new Vector2(700, 38));
            var bugBtn = SettingsButton(bugBox.transform, "SBugBtn", "Open Report Form",
                C_WHITE, new Color(0.20f, 0.30f, 0.45f, 0.9f), new Vector2(260, 28),
                () => { CompetitiveUI.OpenBugReportModal(); });

            // (No filler spacer — when the panel lives inside a ScrollView the
            // content sizes to fit its children, so a flex spacer would collapse
            // anyway and just left the bottom panels jammed against the next
            // item. Delete is still at the bottom because it's added last.)

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

            return outer;
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
            if (appearOfflineTxt != null)
            {
                var stAo = ApiClient.CachedPlayerStats;
                UIFactory.SetText(appearOfflineTxt,
                    stAo != null && stAo.appear_offline
                        ? "Appear offline (Home lists): <color=#88FF88>ON</color>"
                        : "Appear offline (Home lists): <color=#FF9966>OFF</color>");
            }
            if (showDiscordTxt != null)
            {
                var stSd = ApiClient.CachedPlayerStats;
                bool linked = stSd != null && (!string.IsNullOrEmpty(stSd.discord_username) || !string.IsNullOrEmpty(stSd.discord_id));
                UIFactory.SetText(showDiscordTxt,
                    !linked
                        ? "Show Discord on leaderboard: <color=#888>link Discord first</color>"
                        : (stSd.show_discord
                            ? "Show Discord on leaderboard: <color=#88FF88>ON</color>"
                            : "Show Discord on leaderboard: <color=#FF9966>OFF</color>"));
            }
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
            if (cursorShapeTxt != null)
                UIFactory.SetText(cursorShapeTxt,
                    $"Cursor: <color=#88CCFF>{CursorColorCosmetic.CurrentShapeLabel()}</color>");
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
            if (inputOverlayToggleTxt != null && Plugin.ShowInputOverlay != null)
                UIFactory.SetText(inputOverlayToggleTxt,
                    Plugin.ShowInputOverlay.Value
                        ? "Input overlay: <color=#88FF88>ON</color>"
                        : "Input overlay: <color=#FF9966>OFF</color>");
            // v1.32 items 7+8 labels.
            if (screenShakeToggleTxt != null && Plugin.ScreenShakeEnabled != null)
                UIFactory.SetText(screenShakeToggleTxt,
                    Plugin.ScreenShakeEnabled.Value
                        ? "Screen shake: <color=#88FF88>ON</color>"
                        : "Screen shake: <color=#FF9966>OFF</color>");
            if (mapLightingToggleTxt != null && Plugin.MapLightingEnabled != null)
                UIFactory.SetText(mapLightingToggleTxt,
                    Plugin.MapLightingEnabled.Value
                        ? "Map lighting: <color=#88FF88>ON</color>"
                        : "Map lighting: <color=#FF9966>OFF</color>");
            if (mapShadowsToggleTxt != null && Plugin.MapShadowsEnabled != null)
                UIFactory.SetText(mapShadowsToggleTxt,
                    Plugin.MapShadowsEnabled.Value
                        ? "Map shadows: <color=#88FF88>ON</color>"
                        : "Map shadows: <color=#FF9966>OFF</color>");
            if (animCosToggleTxt != null && Plugin.AnimatedCosmetics != null)
                UIFactory.SetText(animCosToggleTxt,
                    Plugin.AnimatedCosmetics.Value
                        ? "Animated cosmetics: <color=#88FF88>ON</color>"
                        : "Animated cosmetics: <color=#FF9966>OFF</color> (static)");
            if (chromAbToggleTxt != null && Plugin.ChromaticAberrationEnabled != null)
                UIFactory.SetText(chromAbToggleTxt,
                    Plugin.ChromaticAberrationEnabled.Value
                        ? "Chromatic aberration: <color=#88FF88>ON</color>"
                        : "Chromatic aberration: <color=#FF9966>OFF</color>");

            // ── Perf section labels (v1.26.8) ──
            if (_perfSectionHeaderTxt != null)
            {
                int onCount = 0, total = 7;
                if (Plugin.PerfStunPlayerNullGuard?.Value ?? false) onCount++;
                if (Plugin.PerfDespawnOffscreenBullets?.Value ?? false) onCount++;
                if (Plugin.PerfSwallowHitSoundNREs?.Value ?? false) onCount++;
                if (Plugin.PerfSwallowEdgeBounceNREs?.Value ?? false) onCount++;
                if (Plugin.PerfSkipMenuUpdateInMatch?.Value ?? false) onCount++;
                if (Plugin.PerfBulletHitParticleCap?.Value ?? false) onCount++;
                if (Plugin.PerfClampObjectPoolInit?.Value ?? false) onCount++;
                bool masterOn = Plugin.PerfOptimizations?.Value ?? false;
                string masterTag = masterOn
                    ? $"<color=#88FF88>{onCount}/{total} active</color>"
                    : "<color=#FF9966>MASTER OFF</color>";
                string arrow = _perfSectionOpen ? "v" : ">";
                UIFactory.SetText(_perfSectionHeaderTxt,
                    $"<b>{arrow} Performance patches</b>  {masterTag}");
            }
            void SetPerfRow(object txt, BepInEx.Configuration.ConfigEntry<bool> e, string label)
            {
                if (txt == null) return;
                if (e == null) { UIFactory.SetText(txt, label + ": <color=#888>(not bound)</color>"); return; }
                UIFactory.SetText(txt,
                    e.Value
                        ? label + ": <color=#88FF88>ON</color>"
                        : label + ": <color=#FF9966>OFF</color>");
            }
            SetPerfRow(perfMasterTxt,    Plugin.PerfOptimizations,             "Master");
            SetPerfRow(perfStunTxt,      Plugin.PerfStunPlayerNullGuard,       "Stun null-guard");
            SetPerfRow(perfBulletsTxt,   Plugin.PerfDespawnOffscreenBullets,   "OOB bullet despawn");
            SetPerfRow(perfHitSndTxt,    Plugin.PerfSwallowHitSoundNREs,       "Hit-sound NRE swallow");
            SetPerfRow(perfEdgeBnTxt,    Plugin.PerfSwallowEdgeBounceNREs,     "EdgeBounce NRE swallow");
            SetPerfRow(perfMenuTxt,      Plugin.PerfSkipMenuUpdateInMatch,     "Menu update bail");
            SetPerfRow(perfBulletCapTxt, Plugin.PerfBulletHitParticleCap,      "Bullet-hit particle cap (2/frame)");
            SetPerfRow(perfPoolTxt,      Plugin.PerfClampObjectPoolInit,       "ObjectPool init clamp (in-match)");
        }

        private static void RefreshRecentSeries()
        {
            if(txtRecentSeries==null)return;
            var series=ApiClient.CachedRecentSeries;
            if(series==null)
            {
                // Self-heal (#32): null = never loaded OR the open-time fetch
                // failed (timeout/server blip) — nothing used to retry until
                // the user clicked Refresh. Throttled refetch while the panel
                // is visibly empty; the fetch callback MarkDirty()s us back.
                if(Time.realtimeSinceStartup-_seriesAutoFetchAt>8f)
                {
                    _seriesAutoFetchAt=Time.realtimeSinceStartup;
                    ApiClient.FetchRecentSeries();
                }
                UIFactory.SetText(txtRecentSeries,"Loading recent series...");
                if(seriesPrev!=null)seriesPrev.SetActive(false);if(seriesNext!=null)seriesNext.SetActive(false);if(txtSeriesPage!=null)UIFactory.SetText(txtSeriesPage,"");return;
            }
            if(series.Count==0){UIFactory.SetText(txtRecentSeries,"No recent series");if(seriesPrev!=null)seriesPrev.SetActive(false);if(seriesNext!=null)seriesNext.SetActive(false);if(txtSeriesPage!=null)UIFactory.SetText(txtSeriesPage,"");return;}
            // 50 series per page (item 7): the list lives in a flex ScrollView, so a
            // short page left dead space between the last row and the pager. A big
            // page keeps the column visually full and scrolls; the pager only
            // matters past 50. Server returns up to 100 - see FetchRecentSeries.
            int perPage=50,totalPages=(series.Count+perPage-1)/perPage;
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
                // Round 5 item 1: wrapping a long line ("HOLY SHIT IS THAT THE
                // KNIGHT") orphaned the elo tail on its own line and looked
                // awful. Cap each NAME so the whole line fits the column; the
                // element no longer word-wraps (overflow clips at the mask).
                string wNameT=Trunc(wName,16), lNameT=Trunc(lName,16);
                txt+=$"<color={wCol}>{wNameT}</color>{wRatingTag}{wElo}  <b>{wScore}-{lScore}</b>  <color={lCol}>{lNameT}</color>{lRatingTag}{lElo}\n";
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
        UIFactory.SetText(txtRating,$"{s.rating:F0}");UIFactory.SetText(txtRD,$"RD: {s.rating_deviation:F0}    Peak: {s.peak_rating:F0}");UIFactory.SetText(txtLevel,$"Level {s.level}");if(s.level<100&&s.xp_for_next_level>0){UIFactory.SetText(txtXPProg,$"{s.xp_into_level}/{s.xp_for_next_level} XP");UIFactory.SetFill(xpFill,(float)s.xp_into_level/s.xp_for_next_level);}else{UIFactory.SetText(txtXPProg,"MAX");UIFactory.SetFill(xpFill,1f);}UIFactory.SetText(txtTotalXP,$"{s.total_xp:N0} XP");var history=ApiClient.CachedMatchHistory;var sR=history?.FindAll(m=>m.is_ranked)??new List<ApiClient.MatchHistoryEntry>();var sC=history?.FindAll(m=>!m.is_ranked)??new List<ApiClient.MatchHistoryEntry>();
/* Casual W/L + sweeps come from the SERVER stats, not a local history scan:
 * since the v1.32.1 lazy history load the cache only holds the head ~400
 * matches, so scanning it understated lifetime numbers (Sid: "casual losses
 * gone" — his 28 lifetime losses had 1 inside the window). sR/sC stay for
 * the CURRENT-streak calcs, which are inherently recent. */
int cW=s.casual_wins,cL=s.casual_losses,sweepG=s.sweeps_given,sweepT=s.sweeps_taken;int rW=s.ranked_series_wins,rL=s.ranked_series_losses;UIFactory.SetText(txtRankedRec,rW+rL>0?$"<color=#FFD94D>Ranked (series):</color> {rW}W / {rL}L ({(rL>0?$"{(float)rW/rL:F1}":$"{rW}:0")})":"<color=#FFD94D>Ranked:</color> -");/* July 20 item 5: the old single line mixed UNITS — "Streak" was per-GAME
 * (client calc over the cached history head) while "Best" was per-SERIES
 * (server walk) with no label; Sid's real 177-game best never displayed and
 * "Best: 128W" (his true series best) read as an uncounted game streak.
 * Now: two labeled lines, both from new server fields (full-history, no
 * 400-row cache cap); client CalcStreak stays only as an old-server fallback. */
{int gCur=s.current_ranked_game_streak!=0?s.current_ranked_game_streak:(sR.Count>0?CalcStreak(sR):0);int gBest=s.best_ranked_game_streak;int srCur=s.current_ranked_series_streak;int srBest=s.best_ranked_series_streak>0?s.best_ranked_series_streak:s.best_ranked_streak;if(gCur==0&&gBest==0&&srCur==0&&srBest==0)UIFactory.SetText(txtRankedStrk,"");else{string gc=gCur>=0?"#00FF00":"#FF6666";string sc2=srCur>=0?"#00FF00":"#FF6666";string l1=$"  <color={gc}>Game streak: {(gCur>=0?$"{gCur}W":$"{-gCur}L")}</color>"+(gBest>0?$"  Best: {gBest}W":"");string l2=$"  <color={sc2}>Series streak: {(srCur>=0?$"{srCur}W":$"{-srCur}L")}</color>"+(srBest>0?$"  Best: {srBest}W":"");UIFactory.SetText(txtRankedStrk,l1+"\n"+l2);}}/* 2v2 line — shows the parallel Glicko / W-L / streak. Hidden when no 2v2 series played, since the row otherwise reads as a confusing 0-0/1500 default. */{var t2=ApiClient.CachedTeamStats;if(t2!=null&&(t2.series_wins+t2.series_losses)>0){string ratio=t2.series_losses>0?$"{(float)t2.series_wins/t2.series_losses:F1}":t2.series_wins>0?$"{t2.series_wins}:0":"0:0";UIFactory.SetText(txtTeam2v2Rec,$"<color=#FFB347>2v2:</color> {t2.series_wins}W / {t2.series_losses}L ({ratio})  <color=#888>Rating:</color> {t2.rating:F0}  <color=#888>Peak:</color> {t2.peak_rating:F0}");int st2=t2.current_streak;if(st2!=0){string c2=st2>0?"#00FF00":"#FF6666";UIFactory.SetText(txtTeam2v2Strk,$"  <color={c2}>Streak: {(st2>0?$"{st2}W":$"{-st2}L")}</color>");}else UIFactory.SetText(txtTeam2v2Strk,"");}else{UIFactory.SetText(txtTeam2v2Rec,"<color=#FFB347>2v2:</color> -");UIFactory.SetText(txtTeam2v2Strk,"");}}UIFactory.SetText(txtCasualRec,cW+cL>0?$"Casual: {cW}W / {cL}L ({(cL>0?$"{(float)cW/cL:F1}":cW>0?$"{cW}:0":"")})":"Casual: -");if(sC.Count>0){int st=CalcStreak(sC);string c=st>0?"#00FF00":"#FF6666";UIFactory.SetText(txtCasualStrk,$"  <color={c}>Streak: {(st>0?$"{st}W":$"{-st}L")}</color>"+(s.best_casual_streak>0?$"  Best: {s.best_casual_streak}W":""));}else UIFactory.SetText(txtCasualStrk,"");UIFactory.SetText(txtSweeps,$"Sweeps: <color=#00FF00>5-0 x{sweepG}</color>  <color=#FF6666>0-5 x{sweepT}</color>");UIFactory.SetText(txtTotalRec,$"Total: {s.total_matches} ({s.wins}W / {s.losses}L)  <color=#FFD94D>Gold: {(s.gold_earned - s.gold_spent)}</color>");/* Hit% / Block% lifetime - one-sided totals (only the reporter-side's client has these
 * counters). Split across two lines in the 44px-tall txtAccuracy field because the
 * combined string overflows 340px at 15pt and TMP wordwrap clips the second line
 * when the field is only 22px tall. Newline gives TMP a proper 2-line render. */
{string hitLine=s.bullets_fired>0?$"<color=#FF9988>Hit:</color> {(float)s.bullets_hit*100f/s.bullets_fired:F1}% ({s.bullets_hit}/{s.bullets_fired})":"<color=#FF9988>Hit:</color> -";string blkLine=s.blocks_activated>0?$"<color=#99CCFF>Block:</color> {(float)s.blocks_successful*100f/s.blocks_activated:F1}% ({s.blocks_successful}/{s.blocks_activated})":"<color=#99CCFF>Block:</color> -";UIFactory.SetText(txtAccuracy,$"{hitLine}\n{blkLine}");}RefreshHistory(sR,sC);RefreshSession();}
        private static void RefreshHistory(List<ApiClient.MatchHistoryEntry> ranked,List<ApiClient.MatchHistoryEntry> casual){CompetitiveUI.ClearCardHoverRegions();foreach(var r in rankedRows){r.root.SetActive(false);r.seriesGO.SetActive(false);}if(ranked.Count>0){var groups=GroupBySeries(ranked);int gpp=3,totalP=(groups.Count+gpp-1)/gpp;/* v1.33 lazy history (item 8): pager shows the FULL page count from the
 * server summary while only a window of matches is loaded; nearing the end
 * of the loaded window prefetches the next chunk. */int fullGroups=Math.Max(groups.Count,ApiClient.HistoryTotalRankedGroups);int fullRankedP=Math.Max(totalP,(fullGroups+gpp-1)/gpp);rankedPage=Math.Max(0,Math.Min(rankedPage,totalP-1));if(rankedPage>=totalP-2&&!ApiClient.MatchHistoryLoadedAll)ApiClient.FetchMoreMatchHistory(MatchTracker.LocalSteamId);int start=rankedPage*gpp,end=Math.Min(start+gpp,groups.Count);int ri=0;for(int g=start;g<end&&ri<rankedRows.Count;g++){var grp=groups[g];if(grp.matches.Count==0)continue;var first=grp.matches[0];if(grp.series_id!=null&&ri<rankedRows.Count){var row=rankedRows[ri];string score=first.series_score??"?-?",opp=FormatOpponentForRow(first,18);bool complete=false,won=false;try{var p=score.Split('-');int mw=int.Parse(p[0]),tw=int.Parse(p[1]);complete=mw>=2||tw>=2;won=mw>tw;}catch{}UIFactory.SetText(row.txtSeriesHead,complete?$"Series {(won?"W":"L")} {score}  vs {opp}":$"Series {score}  vs {opp}  (in progress)");UIFactory.SetColor(row.txtSeriesHead,complete?(won?C_GREEN:C_RED):C_GOLD);/* The per-match row shows XP->gold (typically 4-5g/match); the series-win bonus (10-12g) was invisible because the history row never referenced series_gold_gained. Find the populated value across matches in this group (server sets it on the last-match-of-series row) and append to the elo line. */int grpSeriesGold=0;foreach(var mm in grp.matches)if(mm.series_gold_gained>grpSeriesGold)grpSeriesGold=mm.series_gold_gained;/* July 20 item 6: also show series gold when the elo delta is 0/absent — losers now
 * earn series gold (tier multipliers) and their rows previously hid it entirely. */if(complete&&(first.series_rating_change!=0f||grpSeriesGold>0)){float rc=first.series_rating_change;string goldStr=grpSeriesGold>0?$" <color=#FFD94D>+{grpSeriesGold}g</color>":"";string eloStr=rc!=0f?$"{(rc>0?"+":"")}{rc:F0} elo":"";UIFactory.SetText(row.txtSeriesElo,(eloStr+goldStr).TrimStart());UIFactory.SetColor(row.txtSeriesElo,rc>0?C_GREEN:rc<0?C_RED:C_GOLD);}else UIFactory.SetText(row.txtSeriesElo,"");row.seriesGO.SetActive(true);foreach(var m in grp.matches){if(ri>=rankedRows.Count)break;FillRow(rankedRows[ri],m,true);ri++;}}else{FillRow(rankedRows[ri],first,false);ri++;}}rPrev.SetActive(rankedPage>0);rNext.SetActive(rankedPage<totalP-1||!ApiClient.MatchHistoryLoadedAll);UIFactory.SetText(txtRankedPage,fullRankedP>1?$"{rankedPage+1}/{fullRankedP}":"");}else{rPrev.SetActive(false);rNext.SetActive(false);UIFactory.SetText(txtRankedPage,"");}foreach(var r in casualRows)r.root.SetActive(false);if(casual.Count>0){int mpp=6,totalP=(casual.Count+mpp-1)/mpp;int fullCasual=Math.Max(casual.Count,ApiClient.HistoryTotalCasual);int fullCasualP=Math.Max(totalP,(fullCasual+mpp-1)/mpp);casualPage=Math.Max(0,Math.Min(casualPage,totalP-1));if(casualPage>=totalP-2&&!ApiClient.MatchHistoryLoadedAll)ApiClient.FetchMoreMatchHistory(MatchTracker.LocalSteamId);int start=casualPage*mpp,end=Math.Min(start+mpp,casual.Count);for(int i=start;i<end;i++){int ri=i-start;if(ri<casualRows.Count)FillRow(casualRows[ri],casual[i],false);}cPrev.SetActive(casualPage>0);cNext.SetActive(casualPage<totalP-1||!ApiClient.MatchHistoryLoadedAll);UIFactory.SetText(txtCasualPage,fullCasualP>1?$"{casualPage+1}/{fullCasualP}":"");}else{cPrev.SetActive(false);cNext.SetActive(false);UIFactory.SetText(txtCasualPage,"");}}

        /// <summary>Half-point score format (item 4): each point is half a round, so
        /// "2-1 with 1-0 partial points" reads "2.5-1" instead of the old "2-1 1-0p".
        /// pts>=2 is END-OF-GAME RESIDUE, not a real half point: two points convert
        /// to a round instantly mid-game, but when the WINNING point lands the game
        /// stops before the counter resets — so winners carried rounds=5,pts=2 and
        /// rendered "6-x" (Sid's July 12 item 1). Treat >=2 as already-counted.</summary>
        private static string FmtHalfScore(int rounds,int pts){if(pts>=2)pts=0;return pts>0?(rounds+pts*0.5f).ToString("0.#",System.Globalization.CultureInfo.InvariantCulture):rounds.ToString();}

        private static void FillRow(HistoryRow row,ApiClient.MatchHistoryEntry m,bool indent){string r=m.won?"W":"L";Color c=m.won?C_GREEN:C_RED;UIFactory.SetText(row.txtResult,$"{(indent?"    ":"  ")}{r}  {FmtHalfScore(m.player_rounds_won,m.player_points)}-{FmtHalfScore(m.opponent_rounds_won,m.opponent_points)}");UIFactory.SetColor(row.txtResult,c);UIFactory.SetText(row.txtOpp,indent?"":$"vs {FormatOpponentForRow(m,20)}");UIFactory.SetText(row.txtFps,BuildFpsTag(m));UIFactory.SetText(row.txtPing,BuildPingTag(m));RegisterTeleGraphRectFor(row.txtFps,m.player_fps_timeline,m.opp_fps_timeline,false,m.point_times,m.point_timeline);RegisterTeleGraphRectFor(row.txtPing,m.player_ping_timeline,m.opp_ping_timeline,true,m.point_times,m.point_timeline);/* Item 4: per-game combat stats under the FPS line. Only rows with telemetry (post-mig-111 + both mods) render; old rows stay clean. July 22 item 1: split into per-player elements — hovering a Hit% pops that player's fired-vs-hit graph, a Block% pops dmg-taken-vs-blocks, all with point markers. */{string durTag=m.duration_seconds>0?$"      <color=#8FA3B8>{m.duration_seconds/60}:{m.duration_seconds%60:00}</color>":"";UIFactory.SetText(row.txtStats,durTag);string hy="",by="",ky="",ho="",bo="",ko="";if(m.player_bullets_fired>0||m.player_blocks_activated>0){float hp=m.player_bullets_fired>0?100f*m.player_bullets_hit/m.player_bullets_fired:0f;float bp=m.player_blocks_activated>0?100f*m.player_blocks_successful/m.player_blocks_activated:0f;float kps=m.player_active_seconds>0.5f?m.player_keys_pressed/m.player_active_seconds:0f;hy=$"<color=#99B3E6>You: Hit {hp:F0}%</color>";by=$"<color=#99B3E6>Block {bp:F0}%</color>";ky=$"<color=#99B3E6>{kps:F1} keys/s</color>";if(m.opp_bullets_fired>0||m.opp_blocks_activated>0){float ohp=m.opp_bullets_fired>0?100f*m.opp_bullets_hit/m.opp_bullets_fired:0f;float obp=m.opp_blocks_activated>0?100f*m.opp_blocks_successful/m.opp_blocks_activated:0f;float okps=m.opp_active_seconds>0.5f?m.opp_keys_pressed/m.opp_active_seconds:0f;ho=$"<color=#E69988>Opp: Hit {ohp:F0}%</color>";bo=$"<color=#E69988>Block {obp:F0}%</color>";ko=$"<color=#E69988>{okps:F1} keys/s</color>";}}UIFactory.SetText(row.txtHitYou,hy);UIFactory.SetText(row.txtBlockYou,by);UIFactory.SetText(row.txtKpsYou,ky);UIFactory.SetText(row.txtHitOpp,ho);UIFactory.SetText(row.txtBlockOpp,bo);UIFactory.SetText(row.txtKpsOpp,ko);/* Review [8]: only register a hover zone when the cell actually renders text — an EMPTY element has preferredWidth 0, which ResolveHoverSource treats as "no fraction" = FULL-width region: an invisible hover trap across the row. */if(!string.IsNullOrEmpty(hy))RegisterPairGraphRectFor(row.txtHitYou,m.player_hit_timeline,false,false,m.point_times,m.point_timeline);if(!string.IsNullOrEmpty(by))RegisterPairGraphRectFor(row.txtBlockYou,m.player_block_timeline,true,false,m.point_times,m.point_timeline);if(!string.IsNullOrEmpty(ho))RegisterPairGraphRectFor(row.txtHitOpp,m.opp_hit_timeline,false,true,m.point_times,m.point_timeline);if(!string.IsNullOrEmpty(bo))RegisterPairGraphRectFor(row.txtBlockOpp,m.opp_block_timeline,true,true,m.point_times,m.point_timeline);}/* Item 4: hovering the W/L score pops a line graph of the scoring history. */RegisterScoreGraphRectFor(row.txtResult,m.point_timeline,m.won);/* July 22 item 6: click-to-copy game ID. */row.currentMatchId=m.match_id;if(row.btnId!=null)row.btnId.SetActive(!string.IsNullOrEmpty(m.match_id));UIFactory.SetText(row.txtXP,m.xp_gained>0?(m.gold_gained>0?$"+{m.xp_gained}xp <color=#FFD94D>+{m.gold_gained}g</color>":$"+{m.xp_gained}xp"):"");string dt="";try{if(!string.IsNullOrEmpty(m.ended_at)&&m.ended_at.Length>=10)dt=DateTime.Parse(m.ended_at).ToString("M/d");}catch{}UIFactory.SetText(row.txtDate,dt);UIFactory.SetText(row.txtCards,!string.IsNullOrEmpty(m.cards_display)?$"        Cards: {(_historyCardsFull ? m.cards_display : FormatCardLine(m.cards_display))}":"");UIFactory.SetText(row.txtOppCards,!string.IsNullOrEmpty(m.opp_cards_display)?$"        Opp:   {(_historyCardsFull ? m.opp_cards_display : FormatCardLine(m.opp_cards_display))}":"");if(rCardModeTxt!=null)UIFactory.SetText(rCardModeTxt,HistoryCardModeLabel());if(cCardModeTxt!=null)UIFactory.SetText(cCardModeTxt,HistoryCardModeLabel());RegisterHoverRectFor(row.txtCards,m.cards_display,false);RegisterHoverRectFor(row.txtOppCards,m.opp_cards_display,true);row.root.SetActive(true);}

        // Resolve a TMP text component's screen-space rect via its parent
        // chain. Handles both Screen Space - Overlay (corners are screen
        // coords already) and Screen Space - Camera (need WorldToScreenPoint
        // via the canvas's worldCamera). Caches nothing — runs per FillRow.
        // Bug #61: shared resolver for hover-region registration. Extracts the
        // element's RectTransform, its canvas camera (null on the Overlay canvas,
        // where world corners ARE screen coords), the rendered-text width fraction
        // (#22 / learning #90 — the card text lives in a fixed-width box but only
        // fills part of it; registering the whole box made the empty right side a
        // dead hover zone), and a registration-time rect as fallback. The hit test
        // in CompetitiveUI recomputes the rect LIVE from these pieces each frame,
        // so scrolling the history ScrollView can no longer desync the hover
        // region from its row (bug #61 — regions used to be baked once per
        // refresh and drifted as content moved).
        private static bool ResolveHoverSource(object txt, out RectTransform rt, out Camera cam,
                                               out float frac, out Rect rect, out RectTransform clip)
        {
            rt = null; cam = null; frac = -1f; rect = default(Rect); clip = null;
            try
            {
                var comp = txt as Component;
                if (comp == null) return false;
                rt = comp.GetComponent<RectTransform>();
                if (rt == null) return false;
                bool isOverlay = true;
                Transform t = rt;
                while (t != null)
                {
                    // UIFactory.CreateScrollView names its masked child "Viewport";
                    // the nearest one bounds where this row is actually visible.
                    if (clip == null && t.gameObject.name == "Viewport")
                        clip = t as RectTransform;
                    var canvasComp = t.GetComponent(UIFactory.tCanvas);
                    if (canvasComp != null)
                    {
                        var bf = BindingFlags.Public | BindingFlags.Instance;
                        var rmProp = UIFactory.tCanvas.GetProperty("renderMode", bf);
                        if (rmProp != null)
                        {
                            int rm = (int)rmProp.GetValue(canvasComp);
                            isOverlay = (rm == 0);
                            if (!isOverlay)
                            {
                                var wcProp = UIFactory.tCanvas.GetProperty("worldCamera", bf);
                                cam = (wcProp?.GetValue(canvasComp) as Camera) ?? Camera.main;
                            }
                        }
                        break;
                    }
                    t = t.parent;
                }
                if (!isOverlay && cam == null) return false;
                // Rendered-text width fraction. The element is left-aligned
                // (AlignTopLeft) so the live rect keeps the left edge and only
                // trims the right. prefLocal and rect.width are both local units,
                // so the ratio maps cleanly onto screen width at any canvas scale.
                try
                {
                    var prefProp = comp.GetType().GetProperty("preferredWidth",
                                       BindingFlags.Public | BindingFlags.Instance);
                    float localW = rt.rect.width;
                    if (prefProp != null && localW > 0f)
                    {
                        float prefLocal = (float)prefProp.GetValue(comp);
                        if (prefLocal > 0f) frac = Mathf.Clamp01(prefLocal / localW);
                    }
                }
                catch { /* keep full-width region on any reflection miss */ }
                rect = CompetitiveUI.LiveRegionRect(rt, cam, frac, clip, default(Rect));
                return true;
            }
            catch { return false; }
        }

        private static void RegisterHoverRectFor(object txt, string fullLine, bool isOpponent,
                                                 string titleOverride = null, string bodyOverride = null)
        {
            if (txt == null || string.IsNullOrEmpty(fullLine)) return;
            try
            {
                RectTransform rt; Camera cam; float frac; Rect rect; RectTransform clip;
                if (!ResolveHoverSource(txt, out rt, out cam, out frac, out rect, out clip)) return;
                CompetitiveUI.RegisterCardHoverRegion(rect, fullLine, isOpponent, titleOverride, bodyOverride, rt, cam, frac, clip, txt);
            }
            catch { /* silent — tooltip is opt-in cosmetic */ }
        }

        /// <summary>Item 4: register the score text as a hover region that pops the
        /// scoring-history line graph. Same screen-rect resolution as the card
        /// hover (Overlay vs ScreenSpaceCamera canvases, learning #6), trimmed to
        /// the rendered text width (learning #90).</summary>
        private static void RegisterScoreGraphRectFor(object txt, string timeline, bool won)
        {
            if (txt == null || string.IsNullOrEmpty(timeline) || timeline.IndexOf(':') < 0) return;
            try
            {
                RectTransform rt; Camera cam; float frac; Rect rect; RectTransform clip;
                if (!ResolveHoverSource(txt, out rt, out cam, out frac, out rect, out clip)) return;
                CompetitiveUI.RegisterScoreGraphRegion(rect, timeline, won, rt, cam, frac, clip, txt);
            }
            catch { }
        }

        // July 21 item 2: hover the FPS tag → both players' fps timelines on one
        // chart (same live-rect mechanics as the score graph). July 22 item 1:
        // optional point-marker data + a my-cadence override (2v2 series are 3s).
        private static void RegisterTeleGraphRectFor(object txt, string mySeries, string oppSeries, bool isPing,
                                                     string pointTimes = null, string pointTimeline = null,
                                                     float myStep = 0f)
        {
            if (txt == null || (string.IsNullOrEmpty(mySeries) && string.IsNullOrEmpty(oppSeries))) return;
            try
            {
                RectTransform rt; Camera cam; float frac; Rect rect; RectTransform clip;
                if (!ResolveHoverSource(txt, out rt, out cam, out frac, out rect, out clip)) return;
                CompetitiveUI.RegisterFpsGraphRegion(rect, mySeries, oppSeries, isPing, rt, cam, frac, clip, txt,
                                                     pointTimes, pointTimeline, myStep);
            }
            catch { }
        }

        // July 22 item 1: hover a Hit%/Block% tag → that player's cumulative
        // pair chart (fired-vs-hit / dmg-vs-blocks) with point markers.
        private static void RegisterPairGraphRectFor(object txt, string pairSeries, bool isBlock, bool subjectIsOpp,
                                                     string pointTimes, string pointTimeline)
        {
            if (txt == null || string.IsNullOrEmpty(pairSeries)) return;
            try
            {
                RectTransform rt; Camera cam; float frac; Rect rect; RectTransform clip;
                if (!ResolveHoverSource(txt, out rt, out cam, out frac, out rect, out clip)) return;
                CompetitiveUI.RegisterPairGraphRegion(rect, pairSeries, isBlock, subjectIsOpp, rt, cam, frac, clip, txt,
                                                      pointTimes, pointTimeline);
            }
            catch { }
        }

        // July 22 item 7: hover a 2v2 player's telemetry cell → their combo popup.
        private static void RegisterComboGraphRectFor(object txt, ApiClient.TeamPlayerTele tele, string playerName, bool isRightTeam)
        {
            if (txt == null || tele == null) return;
            try
            {
                RectTransform rt; Camera cam; float frac; Rect rect; RectTransform clip;
                if (!ResolveHoverSource(txt, out rt, out cam, out frac, out rect, out clip)) return;
                CompetitiveUI.RegisterPlayerComboRegion(rect, tele.fps_timeline, tele.ping_timeline,
                    tele.hit_timeline, tele.block_timeline, playerName, isRightTeam, rt, cam, frac, clip, txt);
            }
            catch { }
        }

        // July 22 item 7: one 2v2 telemetry cell — "Name 142fps 23ms Hit 42% Blk 31%",
        // team-tinted; degrades to fps-only for old-client peers; empty when no data.
        private static void FillTeleCell(object txt, ApiClient.TeamSeriesMatch m, ApiClient.TeamSeriesSlot sl, bool right)
        {
            string s = "";
            ApiClient.TeamPlayerTele tele = null;
            if (sl != null)
            {
                string hex = right ? "#FFB086" : "#8CCFFF";
                string sid = sl.steam_id ?? "";
                if (m.telemetry_by_player != null) m.telemetry_by_player.TryGetValue(sid, out tele);
                int favg = 0;
                if (m.fps_by_player != null) m.fps_by_player.TryGetValue(sid, out favg);
                string nm = sl.name ?? "?";
                if (nm.Length > 10) nm = nm.Substring(0, 10);
                if (tele != null)
                {
                    float hp = tele.bullets_fired > 0 ? 100f * tele.bullets_hit / tele.bullets_fired : 0f;
                    float bp = tele.blocks_activated > 0 ? 100f * tele.blocks_successful / tele.blocks_activated : 0f;
                    string fpsPart = favg > 0 ? favg + "fps " : "";
                    string pingPart = tele.ping_avg > 0 ? tele.ping_avg + "ms " : "";
                    s = $"<color={hex}>{nm}</color> <color=#8FA3B8>{fpsPart}{pingPart}Hit {hp:F0}% Blk {bp:F0}%</color>";
                }
                else if (favg > 0)
                {
                    s = $"<color={hex}>{nm}</color> <color=#8FA3B8>{favg}fps</color>";
                }
            }
            UIFactory.SetText(txt, s);
            if (tele != null) RegisterComboGraphRectFor(txt, tele, sl.name ?? "?", right);
        }

        // Compact a comma-separated card-name list into bracketed chips like
        // [MA][EM][EC][BS] for the F5 history rows. Each chip is the first two
        // letters of the card name, upper-cased. Vanilla ROUNDS shows the same
        // 2-letter glyph in the in-game corner indicator so the abbreviation
        // is already a familiar mental model for players. Original full names
        // still flow through cards_display in the API response (the leaderboard
        // detail panel + the 2v2 series viewer both keep the long form), so
        // we lose no information — just compress the row.
        private static string FormatCardLine(string raw)
        {
            if (string.IsNullOrEmpty(raw)) return "";
            var sb = new System.Text.StringBuilder();
            foreach (var part in raw.Split(','))
            {
                string name = part.Trim();
                if (string.IsNullOrEmpty(name)) continue;
                // Strip leading "Common/Uncommon/..." rarity prefix the server
                // sometimes pre-attaches in <color> markup; we want just the
                // card's display name for the abbreviation.
                int lt = name.IndexOf('>');
                if (lt >= 0 && lt < name.Length - 1) name = name.Substring(lt + 1);
                int gt = name.IndexOf('<');
                if (gt > 0) name = name.Substring(0, gt);
                name = name.Trim();
                if (name.Length == 0) continue;
                string ab = name.Length >= 2 ? name.Substring(0, 2).ToUpperInvariant()
                                              : name.ToUpperInvariant();
                sb.Append('[').Append(ab).Append("] ");
            }
            return sb.ToString().TrimEnd();
        }
        // FPS tag — rendered in its own dedicated text field to the right of the
        // opponent name. Player side uses the same blue as the cards line, opponent
        // uses the matching red, mirroring how each side reads in the cards/opp panel.
        private static string BuildFpsTag(ApiClient.MatchHistoryEntry m){if(m==null)return"";int p=m.player_fps_avg,o=m.opponent_fps_avg;if(p<=0&&o<=0)return"";string pStr=p>0?p.ToString():"-";string oStr=o>0?o.ToString():"-";return$"<color=#888>FPS:</color> <color=#99B3E6>{pStr}</color> <color=#888>/</color> <color=#E69988>{oStr}</color>";}
        // July 22 item 3: latency is its OWN tag (separate hover graph).
        private static string BuildPingTag(ApiClient.MatchHistoryEntry m){if(m==null)return"";int pp=m.player_ping_avg,op=m.opponent_ping_avg;if(pp<=0&&op<=0)return"";string a=pp>0?pp.ToString():"-";string b=op>0?op.ToString():"-";return$"<color=#888>Ping:</color> <color=#99B3E6>{a}</color> <color=#888>/</color> <color=#E69988>{b}</color><color=#888>ms</color>";}

        // Renders the opponent name + colored title tag for match-history rows. Title is the
        // opponent's CURRENT active title (view-time, not snapshot-at-match) - cheap join in the
        // history endpoint, good enough to answer "who am I looking at right now."
        private static string FormatOpponentForRow(ApiClient.MatchHistoryEntry m,int nameMax)
        {
            string nm = Trunc(m?.opponent_name ?? "", nameMax);
            if (m == null || string.IsNullOrEmpty(m.opponent_title)) return nm;
            string col = string.IsNullOrEmpty(m.opponent_title_color) ? "#CCCCCC" : m.opponent_title_color;
            if (IsPodiumTitle(m.opponent_title))
                return $"{nm} {PodiumSparkleSpan(m.opponent_title, col, 0)}";
            return $"{nm} <b><color={col}>[{m.opponent_title}]</color></b>";
        }

        private static void RefreshSession(){int games=GameStateWatcher.SessionMatchCount;bool inRoom=GameStateWatcher.IsInRoom;string oppSteamId=GameStateWatcher.OpponentSteamId;string oppName=GameStateWatcher.OpponentDisplayName;var history=ApiClient.CachedMatchHistory;/* Show opponent lifetime record when in room. v1.33: the counts come from
 * the SERVER's H2H (whole matches table) — the lazily-loaded local history
 * window may not reach an old opponent (item 8). The local scan renders as
 * the interim value until the fetch lands; last-played date still comes from
 * the loaded window when present. */if(inRoom&&!string.IsNullOrEmpty(oppSteamId)&&!oppSteamId.StartsWith("photon_")){ApiClient.FetchOpponentLifetime(oppSteamId);int ltW=0,ltL=0;string lastPlayed="";if(history!=null)foreach(var m in history){if(m.opponent_steam_id==oppSteamId){if(m.won)ltW++;else ltL++;if(string.IsNullOrEmpty(lastPlayed)){try{lastPlayed=DateTime.Parse(m.ended_at).ToString("M/d/yyyy");}catch{}}}}if(ApiClient.CachedOppLifetime.TryGetValue(oppSteamId,out var _lt)){ltW=_lt[0];ltL=_lt[1];}if(ltW+ltL>0){string col=ltW>ltL?"#00FF00":ltW<ltL?"#FF6666":"#AAAAAA";string lastStr=string.IsNullOrEmpty(lastPlayed)?"":$"  (last: {lastPlayed})";UIFactory.SetText(txtSessionOppLifetime,$"  vs {oppName}:  <color={col}>{ltW}W-{ltL}L lifetime</color>{lastStr}");}else{UIFactory.SetText(txtSessionOppLifetime,$"  vs {oppName}:  First time playing!");}UIFactory.SetColor(txtSessionOppLifetime,new Color(0.6f,0.75f,1f));}else if(inRoom&&!string.IsNullOrEmpty(oppName)&&oppName!="Opponent"){UIFactory.SetText(txtSessionOppLifetime,$"  In room with {oppName}");UIFactory.SetColor(txtSessionOppLifetime,C_DIM);}else{UIFactory.SetText(txtSessionOppLifetime,"");}if(games<=0){UIFactory.SetText(txtSessionSum,inRoom?"In game - no results yet":"No games this session");UIFactory.SetColor(txtSessionSum,C_DIM);UIFactory.SetText(txtSessionSplit,"");UIFactory.SetText(txtSessionSweeps,"");return;}int mins=(int)(DateTime.UtcNow-GameStateWatcher.SessionStartTime).TotalMinutes;string time=mins>=60?$"{mins/60}h {mins%60}m":$"{mins}m";int rw=GameStateWatcher.SessionRankedWins,rl=GameStateWatcher.SessionRankedLosses,cw=GameStateWatcher.SessionCasualWins,cl=GameStateWatcher.SessionCasualLosses;int t2w=GameStateWatcher.SessionTeamSeriesWins,t2l=GameStateWatcher.SessionTeamSeriesLosses;int sesSweepG=0,sesSweepT=0;if(history!=null){var sesStart=GameStateWatcher.SessionStartTime;foreach(var m in history){DateTime mTime=DateTime.UtcNow;try{if(!string.IsNullOrEmpty(m.ended_at))mTime=DateTime.Parse(m.ended_at).ToUniversalTime();}catch{}if(mTime<sesStart)continue;if(m.won&&m.opponent_rounds_won==0)sesSweepG++;if(!m.won&&m.player_rounds_won==0)sesSweepT++;}}UIFactory.SetText(txtSessionSum,$"{games} games    {rw+cw}W - {rl+cl}L    {time}");UIFactory.SetColor(txtSessionSum,C_WHITE);string splitLine="";var splitParts=new List<string>();if(rw+rl>0)splitParts.Add($"<color=#FFD94D>Ranked:</color> {rw}W/{rl}L");if(t2w+t2l>0)splitParts.Add($"<color=#FFB347>2v2:</color> {t2w}W/{t2l}L");if(cw+cl>0)splitParts.Add($"Casual: {cw}W/{cl}L");if(splitParts.Count>0)splitLine="  "+string.Join("    ",splitParts.ToArray());UIFactory.SetText(txtSessionSplit,splitLine);if(sesSweepG+sesSweepT>0)UIFactory.SetText(txtSessionSweeps,$"  Sweeps: <color=#00FF00>5-0 x{sesSweepG}</color>  <color=#FF6666>0-5 x{sesSweepT}</color>");else UIFactory.SetText(txtSessionSweeps,"");var wl=GameStateWatcher.SessionWLByOpponent;var st=GameStateWatcher.SessionTimeByOpponent;int idx=0;if(wl!=null)foreach(var kvp in wl){int[]a=kvp.Value;if(a==null||a.Length<4)continue;int ow=a[0]+a[2],ol=a[1]+a[3];/* 2v2 teammates are keyed "w/ Name" (bug #56) - render as-is, no "vs" */string line=kvp.Key.StartsWith("w/ ")?$"  {kvp.Key}:  {ow}W-{ol}L":$"  vs {kvp.Key}:  {ow}W-{ol}L";if(a[0]+a[1]>0&&a[2]+a[3]>0)line+=$"  (R:{a[0]}-{a[1]} C:{a[2]}-{a[3]})";if(st!=null&&st.ContainsKey(kvp.Key)){int m=(int)st[kvp.Key];line+=m>=60?$"   {m/60}h {m%60}m":$"   {m}m";}while(sessionOppTexts.Count<=idx)sessionOppTexts.Add(UIFactory.CreateText($"so{sessionOppTexts.Count}",sessionOppContainer.transform,"",15f,C_LABEL,sizeDelta:new Vector2(340,22)));UIFactory.SetText(sessionOppTexts[idx],line);UIFactory.SetColor(sessionOppTexts[idx],ow>ol?C_GREEN:ow<ol?C_RED:C_DIM);var go=(sessionOppTexts[idx]as Component)?.gameObject;if(go)go.SetActive(true);idx++;}for(int i=idx;i<sessionOppTexts.Count;i++){var go=(sessionOppTexts[i]as Component)?.gameObject;if(go)go.SetActive(false);}}

        private static void RefreshLeaderboard(){_podiumLbRows.Clear();string[]hL={"#","Lv","Player","Rating","W","L","W/L","Gold"};string[]hK={"rank","level","display_name","rating","wins","losses","wl_ratio","gold"};if(lbSortTexts!=null)for(int i=0;i<hK.Length&&i<lbSortTexts.Length;i++){if(lbSortTexts[i]==null)continue;string arrow=lbSort==hK[i]?(lbSortDesc?" v":" ^"):"";UIFactory.SetText(lbSortTexts[i],hL[i]+arrow);UIFactory.SetColor(lbSortTexts[i],lbSort==hK[i]?C_WHITE:C_LABEL);if(lbSortBtns!=null&&i<lbSortBtns.Length)UIFactory.SetImageColor(lbSortBtns[i],lbSort==hK[i]?C_TABACT:C_TAB);}var board=ApiClient.CachedLeaderboard;foreach(var r in lbRows)r.root.SetActive(false);if(board==null||board.entries==null||board.entries.Length==0){UIFactory.SetText(txtLBDetail,"No leaderboard data");UIFactory.SetText(txtLBDetailB,"");UIFactory.SetText(txtLBCount,"");return;}var entries=new List<ApiClient.LeaderboardEntry>(board.entries);switch(lbSort){case "rank":entries.Sort((a,b)=>lbSortDesc?b.rank.CompareTo(a.rank):a.rank.CompareTo(b.rank));break;case "level":entries.Sort((a,b)=>lbSortDesc?b.level.CompareTo(a.level):a.level.CompareTo(b.level));break;case "display_name":entries.Sort((a,b)=>lbSortDesc?string.Compare(b.display_name,a.display_name,StringComparison.OrdinalIgnoreCase):string.Compare(a.display_name,b.display_name,StringComparison.OrdinalIgnoreCase));break;case "rating":entries.Sort((a,b)=>lbSortDesc?b.rating.CompareTo(a.rating):a.rating.CompareTo(b.rating));break;case "wins":entries.Sort((a,b)=>lbSortDesc?b.wins.CompareTo(a.wins):a.wins.CompareTo(b.wins));break;case "losses":entries.Sort((a,b)=>lbSortDesc?b.losses.CompareTo(a.losses):a.losses.CompareTo(b.losses));break;case "wl_ratio":entries.Sort((a,b)=>{float ra=a.losses>0?(float)a.wins/a.losses:a.wins*100f;float rb=b.losses>0?(float)b.wins/b.losses:b.wins*100f;return lbSortDesc?rb.CompareTo(ra):ra.CompareTo(rb);});break;case "gold":entries.Sort((a,b)=>lbSortDesc?b.gold.CompareTo(a.gold):a.gold.CompareTo(b.gold));break;}/* July 22 item 8: search filter (whole board is client-side; ~500 cap). Reset to page 0 when the query changes. */if(lbSearchField!=null)UIFactory.SetText(lbSearchField,"");string lbQ=(lbSearch??"").Trim();if(lbQ!=lbSearchLast){lbSearchLast=lbQ;lbPage=0;}if(lbQ.Length>0)entries.RemoveAll(e=>e.display_name==null||e.display_name.IndexOf(lbQ,StringComparison.OrdinalIgnoreCase)<0);int lbPP=100,lbTotalP=(entries.Count+lbPP-1)/lbPP;lbPage=Math.Max(0,Math.Min(lbPage,lbTotalP-1));int lbStart=lbPage*lbPP,lbEnd=Math.Min(lbStart+lbPP,entries.Count);for(int i=lbStart;i<lbEnd&&(i-lbStart)<lbRows.Count;i++){var e=entries[i];var row=lbRows[i-lbStart];row.steamId=e.steam_id;bool local=e.steam_id==MatchTracker.LocalSteamId;string ratio=e.losses>0?$"{(float)e.wins/e.losses:F1}":e.wins>0?$"{e.wins}:0":"0:0";UIFactory.SetText(row.txtRank,$"{e.rank}");UIFactory.SetColor(row.txtRank,e.rank==1?new Color(1f,0.84f,0f):e.rank==2?new Color(0.75f,0.75f,0.75f):e.rank==3?new Color(0.8f,0.5f,0.2f):C_GOLD);UIFactory.SetText(row.txtLv,$"{e.level}");string _lbName=Trunc(e.display_name,20);if(!string.IsNullOrEmpty(e.title)){string _tc=string.IsNullOrEmpty(e.title_color)?"#FFFFFF":e.title_color;if(IsPodiumTitle(e.title)){_podiumLbRows.Add(new object[]{row.txtName,_lbName,e.title,_tc});_lbName=$"{_lbName} {PodiumSparkleSpan(e.title,_tc,_podiumTick)}";}else{_lbName=$"{_lbName} <b><color={_tc}>[{e.title}]</color></b>";}}UIFactory.SetText(row.txtName,_lbName);UIFactory.SetColor(row.txtName,local?C_GREEN:C_WHITE);/* v1.29: rating cell carries the Discord rank-role color, so ranks read at a glance */string _rc=string.IsNullOrEmpty(e.rank_color)?"#FFFFFF":e.rank_color;UIFactory.SetText(row.txtRating,$"<color={_rc}>{e.rating}</color>");UIFactory.SetText(row.txtW,$"{e.wins}");UIFactory.SetText(row.txtL,$"{e.losses}");UIFactory.SetText(row.txtWL,ratio);if(e.gold<0){UIFactory.SetText(row.txtGold,"<color=#888><i>Hidden</i></color>");}else{UIFactory.SetText(row.txtGold,e.gold>0?$"{e.gold}":"0");}bool sel=e.steam_id==selectedSteamId;/* podium tint alphas halved per Sid feedback — 0.22 read too strong behind text */UIFactory.SetImageColor(row.hlWrap,sel?new Color(0.2f,0.25f,0.4f,0.4f):e.rank==1?new Color(1f,0.84f,0f,0.11f):e.rank==2?new Color(0.75f,0.75f,0.78f,0.10f):e.rank==3?new Color(0.8f,0.5f,0.2f,0.10f):new Color(0.15f,0.15f,0.2f,0.01f));SetLbRowOutline(row,e.rank<=3);row.root.SetActive(true);}UIFactory.SetText(txtLBCount,lbQ.Length>0?$"{entries.Count} of {board.total_players} players":$"{board.total_players} players ranked");lbPrev.SetActive(lbPage>0);lbNext.SetActive(lbPage<lbTotalP-1);UIFactory.SetText(txtLBPage,lbTotalP>1?$"{lbPage+1}/{lbTotalP}":"");if(!string.IsNullOrEmpty(selectedSteamId)&&selectedStats!=null){var ps=selectedStats;UIFactory.SetText(txtLBPlayerName,$"{ps.display_name}   <color=#66CCFF>Level {ps.level}</color>");string _rkLine=!string.IsNullOrEmpty(ps.rank_name)?$"Rank: <b><color={(string.IsNullOrEmpty(ps.rank_color)?"#FFFFFF":ps.rank_color)}>{ps.rank_name}</color></b>   ":"";string detail=$"\n{_rkLine}Rating: {ps.rating:F0}   RD: {ps.rating_deviation:F0}   Peak: {ps.peak_rating:F0}\n{ps.total_matches} matches ({ps.wins}W / {ps.losses}L)  WR: {(ps.total_matches>0?ps.wins*100f/ps.total_matches:0):F0}%\n";if(ps.ranked_series_wins+ps.ranked_series_losses>0)detail+=$"<color=#FFD94D>Ranked (series): {ps.ranked_series_wins}W / {ps.ranked_series_losses}L</color>\n";/* Leave % - denominator includes DCs as their own events */if(ps.ranked_dc_count>0||ps.ranked_series_wins+ps.ranked_series_losses>0){int totalRanked=ps.ranked_series_wins+ps.ranked_series_losses+ps.ranked_dc_count;int dc=ps.ranked_dc_count;if(totalRanked>0){float pct=(float)dc/totalRanked*100f;string dcCol=pct<5f?"#44AA44":pct<15f?"#DDAA33":"#FF4444";detail+=$"<color={dcCol}>Leave: {dc}/{totalRanked} ({pct:F0}%)</color>\n";}}/* Hit% / Block% - lifetime counters driven by Harmony patches (Gun.Attack / HealthHandler.TakeDamage / Block.TryBlock / Block.DoBlock). Accumulates only when this player reported a match. Show a dash for players who haven't reported yet so the rows stay consistent with the My Stats Record section (instead of silently disappearing). */{string hitLine=ps.bullets_fired>0?$"<color=#FF9988>Hit:</color> {(float)ps.bullets_hit*100f/ps.bullets_fired:F1}% <color=#888>({ps.bullets_hit}/{ps.bullets_fired})</color>":"<color=#FF9988>Hit:</color> -";string blkLine=ps.blocks_activated>0?$"<color=#99CCFF>Block:</color> {(float)ps.blocks_successful*100f/ps.blocks_activated:F1}% <color=#888>({ps.blocks_successful}/{ps.blocks_activated})</color>":"<color=#99CCFF>Block:</color> -";detail+=$"{hitLine}\n{blkLine}\n";}/* Head to head — server-computed (full matches table) replaces the
 * earlier client-side iteration over CachedMatchHistory which was
 * limited to the viewer's most-recent 500 matches and silently dropped
 * H2H rows for older opponents. */if(selectedSteamId!=MatchTracker.LocalSteamId){int h2hW=ps.h2h_ranked_wins,h2hL=ps.h2h_ranked_losses,h2hCW=ps.h2h_casual_wins,h2hCL=ps.h2h_casual_losses,h2hSW=ps.h2h_series_wins,h2hSL=ps.h2h_series_losses;int h2hAll=h2hW+h2hCW,h2hAllL=h2hL+h2hCL;if(h2hAll+h2hAllL>0){string h2hColor=h2hAll>h2hAllL?"#00FF00":h2hAll<h2hAllL?"#FF6666":"#AAAAAA";detail+=$"\n<b>vs You:</b> <color={h2hColor}>{h2hAll}W - {h2hAllL}L ({h2hAll+h2hAllL} games)</color>\n";if(h2hSW+h2hSL>0)detail+=$"  Ranked Series: {h2hSW}W / {h2hSL}L\n";if(h2hCW+h2hCL>0)detail+=$"  Casual: {h2hCW}W / {h2hCL}L\n";}}/* Mod version this player was last seen running (X-Mod-Version
 * header on their last mod-only API call). Helps testers tell at a
 * glance who's on a build that has a given fix. *//* July 22 item 8: opt-in Discord display name, right above the Mod line. Server already nulls discord_display_name for non-opted-in third-party views; the show_discord check is the client-side second layer. */if(ps.show_discord&&!string.IsNullOrEmpty(ps.discord_display_name)){detail+=$"\n<color=#888>Discord:</color> <color=#8899FF>@{Trunc(ps.discord_display_name,24)}</color>";}if(!string.IsNullOrEmpty(ps.mod_version)){string mvCol=ps.mod_version==Plugin.ModVersion?"#88FF88":"#FFD94D";detail+=$"\n<color=#888>Mod:</color> <color={mvCol}>v{ps.mod_version}</color>\n";}else{detail+=$"\n<color=#888>Mod: <i>not detected</i></color>\n";}/* Top cards with win rates */if(ps.top_card_names!=null&&ps.top_card_names.Count>0){detail+="\n<color=#99AAEE>Top Cards:</color>\n";for(int ci=0;ci<ps.top_card_names.Count&&ci<8;ci++){string picks=ps.top_card_picks.Count>ci?$" ({ps.top_card_picks[ci]}x)":"";float wr=ps.top_card_win_rates!=null&&ps.top_card_win_rates.Count>ci?ps.top_card_win_rates[ci]*100f:0f;string wrCol=wr>=55?"#00FF00":wr<=45?"#FF6666":"#AAAAAA";detail+=$"  {ps.top_card_names[ci]}{picks}  <color={wrCol}>{wr:F0}%</color>\n";}}/* Tournament placements + recent results for the viewed player. Trophy counts stay inline (compact), recent list is capped to 4 rows so the detail doesn't grow off-screen. */if(ApiClient.CachedPlayerTournaments.TryGetValue(selectedSteamId,out var _tHist)&&_tHist!=null&&(_tHist.participant_count>0)){detail+="\n<color=#FFD94D>Tournaments:</color> ";detail+=$"<color=#FFE580>1stx{_tHist.winner_count}</color>  <color=#C8C8C8>2ndx{_tHist.runner_up_count}</color>  <color=#D4894A>3rdx{_tHist.third_place_count}</color>  <color=#888>(played {_tHist.participant_count})</color>\n";if(_tHist.recent!=null&&_tHist.recent.Length>0){int shown=0;foreach(var te in _tHist.recent){if(shown>=4)break;string dt=te.ended_at;try{if(!string.IsNullOrEmpty(dt))dt=TimeZoneInfo.ConvertTimeFromUtc(DateTime.Parse(te.ended_at,null,System.Globalization.DateTimeStyles.RoundtripKind).ToUniversalTime(),_ResolveTz()).ToString("M/d/yy");}catch{}string placeTxt=te.placed_rank==1?"<color=#FFE580>1st</color>":te.placed_rank==2?"<color=#C8C8C8>2nd</color>":te.placed_rank==3?"<color=#D4894A>3rd</color>":$"<color=#888>-</color>";detail+=$"  {dt}  {placeTxt}  <color=#888>({te.signup_count}p)</color>\n";shown++;}}}/* Composition (item 10 + July 12 item 5): main text = stats + Series-vs-You
 * (so the pager GameObject right after it lands directly under the series
 * list); achievements render in their own element BELOW the pager. */string _histPart;string _seriesPart=BuildViewHistoryText(out _histPart);UIFactory.SetText(txtLBDetail,detail+_seriesPart);UIFactory.SetText(txtLBDetailB,_histPart);UIFactory.SetText(txtLBAch,GetAchievementText());/* Rating line graph - use elo history if available, fall back to form */BuildFormGraph(ps.rating_history,ps.recent_form);/* Block row - always show but hide button for self to prevent layout shift */if(lbBlockRow!=null){lbBlockRow.SetActive(true);bool notSelf=selectedSteamId!=MatchTracker.LocalSteamId;lbBlockBtn.SetActive(notSelf);if(notSelf&&lbBlockTxt!=null){bool blocked=ApiClient.IsPlayerBlocked(selectedSteamId);UIFactory.SetText(lbBlockTxt,blocked?"Unblock from Ranked":"Block from Ranked");UIFactory.SetImageColor(lbBlockBtn,blocked?new Color(0.15f,0.3f,0.15f,0.9f):new Color(0.5f,0.15f,0.15f,0.9f));}}
/* Admin-only Steam ID (Sid item 10) - IsAdmin resolves async, so gate here
 * in the refresh (late-resolution pattern), not at build time. */if(txtLBSteamId!=null){var _sidGO=((Component)txtLBSteamId).gameObject;bool showSid=ApiClient.IsAdmin&&!string.IsNullOrEmpty(selectedSteamId);if(_sidGO.activeSelf!=showSid)_sidGO.SetActive(showSid);if(showSid)UIFactory.SetText(txtLBSteamId,$"<color=#888>Steam ID:</color> <color=#9AD0FF>{selectedSteamId}</color> <color=#666>(click to copy)</color>");}}else{UIFactory.SetText(txtLBPlayerName,"Click a player");UIFactory.SetText(txtLBDetail,"");UIFactory.SetText(txtLBDetailB,"");UIFactory.SetText(txtLBAch,"");BuildFormGraph(null,null);if(lbBlockRow!=null)lbBlockRow.SetActive(false);if(txtLBSteamId!=null)((Component)txtLBSteamId).gameObject.SetActive(false);if(h2hPager!=null)h2hPager.SetActive(false);}}

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
                // Server returns ASC (oldest→newest) as of v1.26.8. Bucket-average
                // to ~100 points when the history is long so a heavy player's
                // 300-series timeline doesn't draw as illegible dot-spam.
                var raw = ratingHistory.ToArray();
                const int MAX_DRAW_POINTS = 100;
                if (raw.Length > MAX_DRAW_POINTS)
                {
                    int bucketCount = MAX_DRAW_POINTS;
                    pts = new float[bucketCount];
                    for (int b = 0; b < bucketCount; b++)
                    {
                        int s = (int)((long)b * raw.Length / bucketCount);
                        int e = (int)((long)(b + 1) * raw.Length / bucketCount);
                        if (e <= s) e = s + 1;
                        if (e > raw.Length) e = raw.Length;
                        float sum = 0f; int cnt = 0;
                        for (int i = s; i < e; i++) { sum += raw[i]; cnt++; }
                        pts[b] = cnt > 0 ? sum / cnt : raw[s];
                    }
                    graphLabel = $"Rating History  ({raw[raw.Length - 1]:F0} Elo, {raw.Length} games)";
                }
                else
                {
                    pts = raw;
                    graphLabel = $"Rating History  ({pts[pts.Length-1]:F0} Elo)";
                }
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
            // July 21 item 6: keep in sync with the lbGraphPanel LayoutElement
            // (prefH/minH at build time) — a mismatch clips or letterboxes.
            float graphH = 110f;
            // padR reserves the right gutter for the fixed rating-line labels;
            // the data line ends just short of them.
            float padL = 6f, padR = 44f, padT = 18f, padB = 6f;
            // The old hardcoded 310px was the panel width of an ancient layout —
            // after the round-5/6/7 leaderboard reworks the panel is ~506px, so
            // the line visibly stopped ~3/5 of the way across. Read the LIVE
            // panel width (parent minus VLG padding as fallback for the first
            // paint while the panel GO is still inactive).
            float panelW = 0f;
            try { var grt2 = lbGraphPanel.GetComponent<RectTransform>(); if (grt2 != null) panelW = grt2.rect.width; } catch { }
            if (panelW < 100f)
            {
                try { var prt = lbGraphPanel.transform.parent as RectTransform; if (prt != null) panelW = prt.rect.width - 24f; } catch { }
            }
            if (panelW < 100f) panelW = 506f;   // deterministic 1920-ref-canvas fallback
            float plotW = panelW - padL - padR;
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

            // July 21 item 6: the old green/red YMax/YMin window labels (arbitrary
            // per-player values) are GONE — fixed rating reference lines below
            // give every player's graph the same universally-readable scale.
            // Same colors for everyone: 1500 purple, 1600 tan, 1800 blue,
            // 2000 green, 2400 red. Only lines inside the current y-range draw.
            if (useElo)
            {
                float[] refVals = { 1500f, 1600f, 1800f, 2000f, 2400f };
                Color[] refCols = {
                    new Color(0.63f, 0.42f, 0.84f),   // purple
                    new Color(0.90f, 0.72f, 0.42f),   // light tan/orange
                    new Color(0.35f, 0.60f, 0.90f),   // blue
                    new Color(0.34f, 0.75f, 0.35f),   // green
                    new Color(0.88f, 0.35f, 0.35f),   // red
                };
                float lastLabelY = -999f;
                for (int ri = 0; ri < refVals.Length; ri++)
                {
                    float rv = refVals[ri];
                    if (rv < minV || rv > maxV) continue;
                    float ry = padB + (rv - minV) / range * plotH;
                    var line = new GameObject($"Ref{(int)rv}");
                    line.transform.SetParent(lbGraphPanel.transform, false);
                    var lrt2 = line.AddComponent<RectTransform>();
                    lrt2.anchorMin = Vector2.zero; lrt2.anchorMax = Vector2.zero;
                    lrt2.pivot = new Vector2(0f, 0.5f);
                    lrt2.anchoredPosition = new Vector2(padL, ry);
                    lrt2.sizeDelta = new Vector2(plotW, 1f);
                    var limg = line.AddComponent(UIFactory.tImage);
                    var lc = refCols[ri]; lc.a = 0.38f;
                    UIFactory.tImage.GetProperty("color", BindingFlags.Public | BindingFlags.Instance)?.SetValue(limg, lc);
                    // Right-gutter value label (skip if crowding the previous one).
                    float labelY = Mathf.Clamp(ry, 6f, graphH - 8f);
                    if (Mathf.Abs(labelY - lastLabelY) < 10f) continue;
                    lastLabelY = labelY;
                    var rl = UIFactory.CreateText($"RefL{(int)rv}", lbGraphPanel.transform, $"{rv:F0}", 9f,
                        new Color(refCols[ri].r, refCols[ri].g, refCols[ri].b, 0.85f), UIFactory.AlignMidRight,
                        sizeDelta: new Vector2(38, 10));
                    try
                    {
                        var rGO = (rl as Component)?.gameObject;
                        if (rGO != null)
                        {
                            var rrt = rGO.GetComponent<RectTransform>();
                            rrt.anchorMin = new Vector2(1, 0); rrt.anchorMax = new Vector2(1, 0);
                            rrt.pivot = new Vector2(1, 0.5f);
                            rrt.anchoredPosition = new Vector2(-2f, labelY);
                            var le = rGO.GetComponent(UIFactory.tLE);
                            if (le != null) UnityEngine.Object.Destroy(le as UnityEngine.Object);
                        }
                    }
                    catch { }
                }
            }

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

        }

        // ── Compare tab (multi-player Elo / top-card comparison) ──────────────
        private static GameObject comparePickerContent, compareGraphPanel, compareCardsScroll, compareCardsContent;
        private static object txtCompareStatus, compareMetricBtnTxt, txtCompareCards;
        private static GameObject compareMetricBtn;
        // Metric index into COMPARE_METRICS. 0 = Elo-over-games graph; the rest are
        // table metrics rendered into the text/cards scroll panel.
        private static int compareMetric = 0;
        private static readonly string[] COMPARE_METRICS = {
            "Elo over games", "Elo over time", "Top Cards", "Worst Cards", "Hit / Block %",
            "Avg Cards / Game", "Avg FPS", "Peak Elo", "Total XP",
            "Achievements", "Achievement Grid", "Region Time",
            // v1.29 additions (Sid's Compare wishlist).
            "Top Streaks", "5-0s Given / Taken", "Bets Won / Lost",
            "Keys / Sec", "Keys / Game", "Avg Game Length", "2v2 Rating",
        };
        private static string compareSearch = "";
        // Exposed so CompetitiveUI's IMGUI search field (drawn over the Compare tab)
        // can read/write the filter — the codebase does all text entry via IMGUI.
        public static string CompareSearch { get { return compareSearch; } set { compareSearch = value ?? ""; } }
        // Screen-space (IMGUI/GUI coordinate) Rect of the Compare search placeholder
        // label, so CompetitiveUI can draw its IMGUI TextField exactly over it without
        // re-deriving the menu layout. The overlay canvas is ScreenSpaceOverlay, so
        // RectTransform world corners ARE screen pixels; IMGUI's Y is top-down, Unity's
        // screen Y is bottom-up, so flip. Returns Rect.zero when unavailable.
        public static Rect GetCompareSearchScreenRect()
        {
            try
            {
                var go = (compareSearchField as Component)?.gameObject;
                if (go == null) return new Rect(0, 0, 0, 0);
                var rt = go.GetComponent<RectTransform>();
                if (rt == null) return new Rect(0, 0, 0, 0);
                var c = new Vector3[4]; rt.GetWorldCorners(c); // 0=BL,1=TL,2=TR,3=BR
                float x = c[0].x, w = c[2].x - c[0].x, h = c[1].y - c[0].y;
                float guiY = Screen.height - c[1].y;
                if (w < 1f || h < 1f) return new Rect(0, 0, 0, 0);
                return new Rect(x, guiY, w, h);
            }
            catch { return new Rect(0, 0, 0, 0); }
        }
        private static object compareSearchField;  // status label (not a real input)

        // July 22 item 8: leaderboard search — same IMGUI-over-anchor pattern
        // as the Compare search above (all text entry in this codebase is IMGUI).
        private static string lbSearch = "";
        private static string lbSearchLast = "";
        public static string LeaderboardSearch { get { return lbSearch; } set { lbSearch = value ?? ""; } }
        private static object lbSearchField;   // empty anchor label under the sub-tabs
        public static Rect GetLbSearchScreenRect()
        {
            try
            {
                var go = (lbSearchField as Component)?.gameObject;
                if (go == null) return new Rect(0, 0, 0, 0);
                var rt = go.GetComponent<RectTransform>();
                if (rt == null) return new Rect(0, 0, 0, 0);
                var c = new Vector3[4]; rt.GetWorldCorners(c);
                float x = c[0].x, w = c[2].x - c[0].x, h = c[1].y - c[0].y;
                float guiY = Screen.height - c[1].y;
                if (w < 1f || h < 1f) return new Rect(0, 0, 0, 0);
                return new Rect(x, guiY, w, h);
            }
            catch { return new Rect(0, 0, 0, 0); }
        }
        private const int COMPARE_MAX = 12;
        private static readonly List<string> compareSelected = new List<string>();
        private static readonly List<string> comparePickerSteamIds = new List<string>();
        private static readonly List<GameObject> comparePickerRows = new List<GameObject>();
        private static readonly List<object> comparePickerTexts = new List<object>();
        private static readonly Dictionary<string, ApiClient.PlayerStatsData> compareStatsCache
            = new Dictionary<string, ApiClient.PlayerStatsData>();
        // 12 visually-distinct colors so up to COMPARE_MAX players each get a unique
        // hue on the graphs/charts and matching picker swatch.
        private static readonly Color[] COMPARE_COLORS = {
            new Color(0.40f, 0.80f, 1.00f), // blue
            new Color(1.00f, 0.50f, 0.40f), // red-orange
            new Color(0.55f, 1.00f, 0.55f), // green
            new Color(1.00f, 0.85f, 0.30f), // gold
            new Color(0.80f, 0.55f, 1.00f), // violet
            new Color(0.40f, 0.95f, 0.90f), // teal
            new Color(1.00f, 0.65f, 0.85f), // pink
            new Color(0.70f, 0.90f, 0.45f), // lime
            new Color(1.00f, 0.78f, 0.45f), // amber
            new Color(0.60f, 0.70f, 1.00f), // periwinkle
            new Color(0.90f, 0.55f, 0.55f), // salmon
            new Color(0.65f, 0.85f, 0.75f), // sage
        };

        private static GameObject BuildCompareTab(Transform parent)
        {
            // Round 5 item 3: outer VLG wrapper hosts the sub-tab anchor above
            // the two-column HLG content.
            var outer = new GameObject("CompareOuter");
            outer.transform.SetParent(parent, false);
            outer.AddComponent<RectTransform>();
            UIFactory.AddVLG(outer, spacing: 4);
            UIFactory.AddLE(outer, flexH: 1);
            MakeSubTabAnchor(9, outer.transform, true);

            var panel = new GameObject("Compare");
            panel.transform.SetParent(outer.transform, false);
            panel.AddComponent<RectTransform>();
            UIFactory.AddHLG(panel, spacing: 8);
            UIFactory.AddLE(panel, flexH: 1);

            // LEFT: player picker. Narrower than before (was 300/260) — lopi wanted
            // it shorter width-wise; the freed horizontal space on the right belongs
            // to the chart panel. Scroll works anywhere over the viewport now
            // (CreateScrollView sets viewport raycastTarget).
            var left = UIFactory.CreatePanel("CmpL", panel.transform, C_PANEL);
            UIFactory.AddVLG(left, spacing: 4, padL: 8, padR: 8, padT: 6, padB: 6);
            UIFactory.AddLE(left, prefW: 222, minW: 200, flexW: 0, flexH: 1);
            UIFactory.CreateText("CmpLH", left.transform, "Compare Players", 19f, C_GOLD,
                UIFactory.AlignMidLeft, sizeDelta: new Vector2(204, 26));
            // Round 4 item 2: the status line is longer than the 204px column and
            // TMP's default overflow spilled it over the graph — wrap to two lines
            // inside the column instead.
            txtCompareStatus = UIFactory.CreateText("CmpSt", left.transform, "Select up to 12 players",
                13f, C_LABEL, UIFactory.AlignTopLeft, sizeDelta: new Vector2(204, 38));
            UIFactory.SetWordWrap(txtCompareStatus, true);
            // Static caption ABOVE the field. The field itself is the IMGUI box drawn by
            // CompetitiveUI over the empty `compareSearchField` anchor below — keeping the
            // anchor's TMP text EMPTY means only one layer of text shows in the box (was
            // double-layered before: native label text behind the IMGUI field).
            UIFactory.CreateText("CmpSearchCap", left.transform, "<color=#88AAFF>Search players</color>",
                12f, C_SUB, UIFactory.AlignMidLeft, sizeDelta: new Vector2(204, 16));
            compareSearchField = UIFactory.CreateText("CmpSearchLbl", left.transform, "",
                13f, C_SUB, UIFactory.AlignMidLeft, sizeDelta: new Vector2(204, 22));
            var btnRow = new GameObject("CmpBtns"); btnRow.transform.SetParent(left.transform, false);
            btnRow.AddComponent<RectTransform>(); UIFactory.AddHLG(btnRow, spacing: 4, forceExpandH: true);
            UIFactory.AddLE(btnRow, prefH: 24, flexH: 0);
            var clrBtn = UIFactory.CreateButton("CmpClr", btnRow.transform, "Clear", 13f, C_WHITE,
                new Color(0.4f, 0.2f, 0.2f, 0.9f), () => { compareSelected.Clear(); dirty = true; },
                sizeDelta: new Vector2(120, 24));
            UIFactory.AddLE(clrBtn, prefH: 24, flexW: 1, flexH: 0);
            var clrSearchBtn = UIFactory.CreateButton("CmpClrS", btnRow.transform, "Clear search", 13f, C_WHITE,
                new Color(0.25f, 0.3f, 0.4f, 0.9f), () => { compareSearch = ""; dirty = true; },
                sizeDelta: new Vector2(120, 24));
            UIFactory.AddLE(clrSearchBtn, prefH: 24, flexW: 1, flexH: 0);
            // childForceExpandWidth:false → the row buttons keep their own (narrower)
            // width and sit left-aligned, leaving a dead strip on the right of the picker
            // that's still inside the scroll viewport. Sid can click/scroll there without
            // selecting a player (the freed space stays in the picker, not handed to the
            // right panel like the previous attempt).
            var sv = UIFactory.CreateScrollView("CmpSV", left.transform, spacing: 2, childForceExpandWidth: false);
            UIFactory.AddLE(sv.scrollGO, flexH: 1);
            comparePickerContent = sv.content;

            // RIGHT: metric toggle + graph + cards.
            var right = UIFactory.CreatePanel("CmpR", panel.transform, C_PANEL);
            UIFactory.AddVLG(right, spacing: 6, padL: 10, padR: 10, padT: 8, padB: 8);
            UIFactory.AddLE(right, flexW: 1, flexH: 1);
            var metricRow = new GameObject("CmpMetRow"); metricRow.transform.SetParent(right.transform, false);
            metricRow.AddComponent<RectTransform>(); UIFactory.AddHLG(metricRow, spacing: 4, forceExpandH: true);
            UIFactory.AddLE(metricRow, prefH: 30, flexH: 0);
            var metricPrev = UIFactory.CreateButton("CmpMetP", metricRow.transform, "<", 15f, C_WHITE, C_TAB,
                () => { compareMetric = (compareMetric - 1 + COMPARE_METRICS.Length) % COMPARE_METRICS.Length; dirty = true; },
                sizeDelta: new Vector2(30, 30));
            UIFactory.AddLE(metricPrev, prefW: 30, prefH: 30, flexW: 0, flexH: 0);
            compareMetricBtn = UIFactory.CreateButton("CmpMet", metricRow.transform, "Metric: Elo over games",
                15f, C_WHITE, C_TAB, () => { compareMetric = (compareMetric + 1) % COMPARE_METRICS.Length; dirty = true; },
                sizeDelta: new Vector2(320, 30));
            UIFactory.AddLE(compareMetricBtn, prefH: 30, flexW: 1, flexH: 0);
            compareMetricBtnTxt = UIFactory.GetButtonText(compareMetricBtn);
            var metricNext = UIFactory.CreateButton("CmpMetN", metricRow.transform, ">", 15f, C_WHITE, C_TAB,
                () => { compareMetric = (compareMetric + 1) % COMPARE_METRICS.Length; dirty = true; },
                sizeDelta: new Vector2(30, 30));
            UIFactory.AddLE(metricNext, prefW: 30, prefH: 30, flexW: 0, flexH: 0);

            // Chart plot — FILLS the right panel (was a fixed 640x320 that used ~1/4 of
            // the space, forcing abbreviated/cut-off names). The chart math reads the
            // RectTransform's actual size at render time (CompareChartSize) so it scales.
            compareGraphPanel = new GameObject("CmpGraph");
            compareGraphPanel.transform.SetParent(right.transform, false);
            compareGraphPanel.AddComponent<RectTransform>();
            UIFactory.AddLE(compareGraphPanel, flexW: 1, flexH: 1);
            var gbg = compareGraphPanel.AddComponent(UIFactory.tImage);
            UIFactory.tImage.GetProperty("color", BindingFlags.Public | BindingFlags.Instance)
                ?.SetValue(gbg, new Color(0.08f, 0.09f, 0.12f, 0.7f));
            if (UIFactory.tMask != null)
            {
                var gm = compareGraphPanel.AddComponent(UIFactory.tMask);
                try { UIFactory.tMask.GetProperty("showMaskGraphic", BindingFlags.Public | BindingFlags.Instance)?.SetValue(gm, true); } catch {}
            }

            // Table-metric scroll (shown for every metric except the Elo graph).
            // Used for Top/Worst Cards, Hit/Block %, Avg metrics, Peak Elo, XP,
            // Achievements, Region time. Word-wrap on so the content height tracks
            // the rendered text and the scroll actually scrolls (learnings #63).
            var cardsSV = UIFactory.CreateScrollView("CmpCardsSV", right.transform, spacing: 0);
            UIFactory.AddLE(cardsSV.scrollGO, flexH: 1);
            compareCardsScroll = cardsSV.scrollGO;
            compareCardsContent = cardsSV.content;
            // txtCompareCards is the empty/loading message; the actual card data is
            // rendered as a multi-column grid of per-player blocks (BuildCompareCardGrid)
            // so 12 players wrap sideways instead of running off the bottom.
            txtCompareCards = UIFactory.CreateText("CmpCards", cardsSV.content.transform, "",
                15f, C_DIM, UIFactory.AlignTopLeft, sizeDelta: new Vector2(820, 24));
            UIFactory.SetWordWrap(txtCompareCards, true);
            UIFactory.SetTextAutoHeight(txtCompareCards);
            // Scroll affordance — matches the 2v2 tab's pattern (codebase avoids
            // real Unity Scrollbars). Tells the user the panel scrolls.
            UIFactory.CreateText("CmpScrollHint", right.transform,
                "<color=#777><i>scroll for more — hover the panel + mouse wheel</i></color>",
                12f, C_DIM, UIFactory.AlignMidCenter, sizeDelta: new Vector2(820, 16));

            return outer;
        }

        private static void ToggleCompareSelect(int rowIdx)
        {
            if (rowIdx < 0 || rowIdx >= comparePickerSteamIds.Count) return;
            string sid = comparePickerSteamIds[rowIdx];
            if (string.IsNullOrEmpty(sid)) return;
            if (compareSelected.Contains(sid))
            {
                compareSelected.Remove(sid);
            }
            else
            {
                if (compareSelected.Count >= COMPARE_MAX)
                {
                    CompetitiveUI.ShowNotification($"Max {COMPARE_MAX} players", new Color(1f, 0.6f, 0.3f));
                    return;
                }
                compareSelected.Add(sid);
                if (!compareStatsCache.ContainsKey(sid))
                    ApiClient.FetchPlayerStatsForView(sid, (d) => { if (d != null) compareStatsCache[sid] = d; dirty = true; });
            }
            dirty = true;
        }

        private static void RefreshCompare()
        {
            if (ApiClient.CachedLeaderboard == null) ApiClient.FetchLeaderboard();
            string metricName = COMPARE_METRICS[Math.Max(0, Math.Min(compareMetric, COMPARE_METRICS.Length - 1))];
            if (compareMetricBtnTxt != null)
                UIFactory.SetText(compareMetricBtnTxt, $"Metric: {metricName}   <color=#888>(click / use < >)</color>");
            if (txtCompareStatus != null)
                UIFactory.SetText(txtCompareStatus, $"Selected {compareSelected.Count}/{COMPARE_MAX}  -  click a player to add/remove");
            // Keep the anchor label EMPTY — the IMGUI text field (CompetitiveUI.DrawCompareSearch)
            // draws over it and shows the value/placeholder. Setting text here too caused the
            // double-layered, hard-to-read box.
            if (compareSearchField != null) UIFactory.SetText(compareSearchField, "");

            // Build the picker list from the current leaderboard, filtered by the
            // search box. comparePickerSteamIds[rowIdx] maps the VISIBLE row index to
            // a steam_id so ToggleCompareSelect(rowIdx) resolves correctly.
            var board = ApiClient.CachedLeaderboard;
            var allEntries = (board != null && board.entries != null)
                ? board.entries : new ApiClient.LeaderboardEntry[0];
            string q = (compareSearch ?? "").Trim();
            var shown = new List<ApiClient.LeaderboardEntry>();
            foreach (var e in allEntries)
            {
                if (string.IsNullOrEmpty(q)
                    || (e.display_name != null && e.display_name.IndexOf(q, StringComparison.OrdinalIgnoreCase) >= 0))
                    shown.Add(e);
            }
            int n = shown.Count;
            while (comparePickerSteamIds.Count < n) comparePickerSteamIds.Add("");
            for (int i = 0; i < n; i++)
            {
                var e = shown[i];
                comparePickerSteamIds[i] = e.steam_id;
                while (comparePickerRows.Count <= i)
                {
                    int idx = comparePickerRows.Count;
                    var b = UIFactory.CreateButton($"cmpP{idx}", comparePickerContent.transform, "",
                        13f, C_WHITE, C_TAB, () => ToggleCompareSelect(idx), sizeDelta: new Vector2(168, 24));
                    UIFactory.AddLE(b, prefW: 168, prefH: 24, flexW: 0, flexH: 0);
                    comparePickerRows.Add(b);
                    comparePickerTexts.Add(UIFactory.GetButtonText(b));
                }
                var row = comparePickerRows[i];
                row.SetActive(true);
                bool sel = compareSelected.Contains(e.steam_id);
                int selOrder = compareSelected.IndexOf(e.steam_id);
                Color swatch = sel && selOrder >= 0 ? COMPARE_COLORS[selOrder % COMPARE_COLORS.Length] : C_LABEL;
                string dot = sel ? $"<color=#{ColorToHex(swatch)}>[X]</color> " : "<color=#555>[ ]</color> ";
                UIFactory.SetText(comparePickerTexts[i], $"{dot}{Trunc(e.display_name, 16)}  <color=#888>{e.rating}</color>");
                UIFactory.SetImageColor(row, sel ? new Color(0.2f, 0.3f, 0.25f, 0.9f) : C_TAB);
            }
            for (int i = n; i < comparePickerRows.Count; i++) comparePickerRows[i].SetActive(false);

            // Route each metric to the renderer that fits its data:
            //   "Elo over games"      → line graph        (compareGraphPanel)
            //   "Top/Worst Cards"     → multi-column grid  (compareCardsScroll)
            //   everything else       → bar/grouped/stacked chart (compareGraphPanel)
            bool isCards = metricName == "Top Cards" || metricName == "Worst Cards";
            bool useGraphPanel = !isCards;
            if (compareGraphPanel != null) compareGraphPanel.SetActive(useGraphPanel);
            if (compareCardsScroll != null) compareCardsScroll.SetActive(isCards);

            if (metricName == "Elo over games") BuildCompareGraph();
            else if (metricName == "Elo over time") BuildCompareGraph(timeAxis: true);
            else if (isCards) BuildCompareCardGrid(metricName);
            else BuildCompareBarChart(metricName);
        }

        private static string ColorToHex(Color c)
        {
            int r = Mathf.Clamp((int)(c.r * 255f), 0, 255);
            int g = Mathf.Clamp((int)(c.g * 255f), 0, 255);
            int b = Mathf.Clamp((int)(c.b * 255f), 0, 255);
            return $"{r:X2}{g:X2}{b:X2}";
        }

        private static void BuildCompareGraph(bool timeAxis = false)
        {
            if (compareGraphPanel == null) return;
            for (int c = compareGraphPanel.transform.childCount - 1; c >= 0; c--)
                UnityEngine.Object.Destroy(compareGraphPanel.transform.GetChild(c).gameObject);

            // Gather each selected player's Elo series from cache. timeAxis
            // (v1.29 "Elo over time") plots x by SNAPSHOT DATE instead of game
            // index, so gaps in play show as flat stretches, and players who
            // started months apart line up on a real calendar.
            var names = new List<string>();
            var cols = new List<Color>();
            var seriesList = new List<float[]>();
            var timesList = new List<float[]>();
            for (int i = 0; i < compareSelected.Count; i++)
            {
                string sid = compareSelected[i];
                if (!compareStatsCache.TryGetValue(sid, out var ps) || ps == null) continue;
                if (ps.rating_history == null || ps.rating_history.Count < 2) continue;
                float[] times = null;
                if (timeAxis)
                {
                    if (ps.rating_history_times == null || ps.rating_history_times.Count != ps.rating_history.Count)
                        continue; // no usable timestamps for this player
                    times = ps.rating_history_times.ToArray();
                }
                names.Add(Trunc(ps.display_name ?? "?", 14));
                cols.Add(COMPARE_COLORS[i % COMPARE_COLORS.Length]);
                seriesList.Add(ps.rating_history.ToArray());
                timesList.Add(times);
            }

            CompareChartSize(out float W, out float H);
            float padL = 56f, padR = 16f, padT = 30f, padB = 26f;
            float plotW = W - padL - padR, plotH = H - padT - padB;

            if (seriesList.Count == 0)
            {
                var msg = UIFactory.CreateText("CmpNone", compareGraphPanel.transform,
                    "<color=#888>Select 2+ players with ranked history to compare Elo.</color>",
                    15f, C_DIM, UIFactory.AlignMidCenter, sizeDelta: new Vector2(W - 20, 40));
                var mrt = (msg as Component)?.gameObject.GetComponent<RectTransform>();
                if (mrt != null) { mrt.anchorMin = new Vector2(0.5f, 0.5f); mrt.anchorMax = new Vector2(0.5f, 0.5f); mrt.anchoredPosition = Vector2.zero; }
                var mle = (msg as Component)?.gameObject.GetComponent(UIFactory.tLE);
                if (mle != null) UnityEngine.Object.Destroy(mle as UnityEngine.Object);
                return;
            }

            // Global Y range + max length (X = game index, shared across players).
            float minV = float.MaxValue, maxV = float.MinValue; int maxLen = 0;
            foreach (var s in seriesList)
            {
                if (s.Length > maxLen) maxLen = s.Length;
                foreach (var v in s) { if (v < minV) minV = v; if (v > maxV) maxV = v; }
            }
            if (maxLen < 2) maxLen = 2;
            // Round the Y range to clean Elo numbers (e.g. 1400, 1500, … 1900) instead of
            // padded fractions like 1437→1913 with a label at 2185. Snap min DOWN and max
            // UP to a nice step, then label every step.
            float rawRange = Mathf.Max(1f, maxV - minV);
            float step = NiceStep(rawRange / 4f);
            float gMin = Mathf.Floor(minV / step) * step;
            float gMax = Mathf.Ceil(maxV / step) * step;
            if (gMax - gMin < step) gMax = gMin + step;
            minV = gMin; maxV = gMax; float range = maxV - minV;

            // Y-axis: a gridline + clean Elo label at every step.
            int yDivs = Mathf.Clamp(Mathf.RoundToInt(range / step), 2, 8);
            for (int gi = 0; gi <= yDivs; gi++)
            {
                float val = gMin + gi * step;
                if (val > gMax + 0.5f) break;
                float yy = padB + (val - gMin) / range * plotH;
                DrawBar($"CmpYGrid{gi}", padL, yy, plotW, 1f, new Color(1f, 1f, 1f, 0.10f));
                MakeGraphLabel($"CmpYLbl{gi}", $"<color=#999>{FullNum(val)}</color>",
                    new Vector2(0, 0), new Vector2(padL - 4f, yy - 6f), new Vector2(50, 12), UIFactory.AlignMidRight);
            }
            // X axis: game index (default) or calendar time (timeAxis).
            float tMin = 0f, tRange = 1f;
            if (timeAxis)
            {
                tMin = float.MaxValue; float tMax = float.MinValue;
                foreach (var ts in timesList)
                    foreach (var t in ts) { if (t < tMin) tMin = t; if (t > tMax) tMax = t; }
                tRange = Mathf.Max(0.5f, tMax - tMin);
                // Date gridlines: 4 divisions labeled M/d (days since 2020-01-01 base).
                var epoch = new DateTime(2020, 1, 1);
                for (int d = 0; d <= 4; d++)
                {
                    float tv = tMin + tRange * d / 4f;
                    float xx = padL + (tv - tMin) / tRange * plotW;
                    DrawBar($"CmpXGrid{d}", xx, padB, 1f, plotH, new Color(1f, 1f, 1f, 0.07f));
                    string dl = epoch.AddDays(tv).ToString("M/d", System.Globalization.CultureInfo.InvariantCulture);
                    MakeGraphLabel($"CmpXDate{d}", $"<color=#999>{dl}</color>",
                        new Vector2(0, 0), new Vector2(xx - 24f, padB - 16f), new Vector2(48, 12), UIFactory.AlignMidCenter);
                }
            }
            else
            {
                MakeGraphLabel("CmpXLbl", "<color=#888>games -></color>", new Vector2(1, 0), new Vector2(-padR, padB - 14f), new Vector2(90, 12), UIFactory.AlignMidRight);
            }

            // Draw each player's line + legend chip (full names — there's room now).
            for (int si = 0; si < seriesList.Count; si++)
            {
                var pts = seriesList[si];
                var ts = timesList[si];
                Color col = cols[si];
                for (int j = 0; j < pts.Length - 1; j++)
                {
                    float x1 = timeAxis
                        ? padL + (ts[j] - tMin) / tRange * plotW
                        : padL + (float)j / (maxLen - 1) * plotW;
                    float y1 = padB + (pts[j] - minV) / range * plotH;
                    float x2 = timeAxis
                        ? padL + (ts[j + 1] - tMin) / tRange * plotW
                        : padL + (float)(j + 1) / (maxLen - 1) * plotW;
                    float y2 = padB + (pts[j + 1] - minV) / range * plotH;
                    DrawGraphSegment($"CmpL{si}_{j}", x1, y1, x2, y2, col, 2f);
                }
                // Legend: a SOLID colored line swatch (matches the player's graph line)
                // + their name. The old "--" dashes were too thin to read as a color.
                int perRow = 3;
                float colW = plotW / perRow;
                float lx = padL + (si % perRow) * colW;
                float ly = -2f - (si / perRow) * 16f;
                // Swatch line sits in the panel's top band; convert top-anchored ly to a
                // bottom-left y for DrawGraphSegment (it anchors at bottom-left).
                float swY = H + ly - 7f;
                DrawGraphSegment($"CmpLegSw{si}", lx + 2f, swY, lx + 24f, swY, col, 4f);
                MakeGraphLabel($"CmpLeg{si}", $"<b>{names[si]}</b>",
                    new Vector2(0, 1), new Vector2(lx + 30f, ly), new Vector2(colW - 30f, 16), UIFactory.AlignMidLeft, 13f);
            }
        }

        // Helper: a rotated 1px-tall rect acting as a line segment in compareGraphPanel.
        private static void DrawGraphSegment(string name, float x1, float y1, float x2, float y2, Color col, float thick)
        {
            float dx = x2 - x1, dy = y2 - y1;
            float len = Mathf.Sqrt(dx * dx + dy * dy);
            float angle = Mathf.Atan2(dy, dx) * Mathf.Rad2Deg;
            var seg = new GameObject(name);
            seg.transform.SetParent(compareGraphPanel.transform, false);
            var srt = seg.AddComponent<RectTransform>();
            srt.anchorMin = Vector2.zero; srt.anchorMax = Vector2.zero; srt.pivot = new Vector2(0f, 0.5f);
            srt.anchoredPosition = new Vector2(x1, y1);
            srt.sizeDelta = new Vector2(len, thick);
            srt.localRotation = Quaternion.Euler(0, 0, angle);
            var img = seg.AddComponent(UIFactory.tImage);
            UIFactory.tImage.GetProperty("color", BindingFlags.Public | BindingFlags.Instance)?.SetValue(img, col);
        }

        // Helper: a positioned label inside compareGraphPanel (bottom-left anchored coords).
        private static void MakeGraphLabel(string name, string text, Vector2 anchor, Vector2 pos, Vector2 size, int align, float fontSize = 11f)
        {
            var lbl = UIFactory.CreateText(name, compareGraphPanel.transform, text, fontSize, C_DIM, align, sizeDelta: size);
            var go = (lbl as Component)?.gameObject;
            if (go == null) return;
            var rt = go.GetComponent<RectTransform>();
            rt.anchorMin = anchor; rt.anchorMax = anchor; rt.pivot = anchor;
            rt.anchoredPosition = pos; rt.sizeDelta = size;
            var le = go.GetComponent(UIFactory.tLE);
            if (le != null) UnityEngine.Object.Destroy(le as UnityEngine.Object);
        }

        // Helper: a filled rectangle bar in compareGraphPanel, anchored bottom-left
        // (same coordinate space as DrawGraphSegment / the line graph plot math).
        private static void DrawBar(string name, float x, float y, float w, float h, Color col)
        {
            if (h < 0f) h = 0f;
            var go = new GameObject(name);
            go.transform.SetParent(compareGraphPanel.transform, false);
            var rt = go.AddComponent<RectTransform>();
            rt.anchorMin = Vector2.zero; rt.anchorMax = Vector2.zero; rt.pivot = new Vector2(0f, 0f);
            rt.anchoredPosition = new Vector2(x, y);
            rt.sizeDelta = new Vector2(w, h);
            var img = go.AddComponent(UIFactory.tImage);
            UIFactory.tImage.GetProperty("color", BindingFlags.Public | BindingFlags.Instance)?.SetValue(img, col);
        }

        // Region → color for the stacked "Region Time" chart + its legend.
        private static Color RegionColor(string region)
        {
            // Distinct, well-separated hues — the old palette had several near-identical
            // blues (us/in/kr looked the same in the legend).
            switch ((region ?? "").ToLowerInvariant())
            {
                case "us":   return new Color(0.25f, 0.55f, 1.00f);  // blue
                case "usw":  return new Color(0.15f, 0.85f, 0.85f);  // cyan
                case "ussc": return new Color(0.35f, 0.80f, 0.35f);  // green
                case "eu":   return new Color(1.00f, 0.62f, 0.18f);  // orange
                case "asia": return new Color(0.95f, 0.32f, 0.32f);  // red
                case "jp":   return new Color(1.00f, 0.42f, 0.80f);  // pink
                case "au":   return new Color(0.68f, 0.42f, 1.00f);  // purple
                case "sa":   return new Color(0.80f, 0.85f, 0.20f);  // yellow-green
                case "kr":   return new Color(1.00f, 0.82f, 0.28f);  // gold
                case "in":   return new Color(0.45f, 0.40f, 0.92f);  // indigo
                case "cae":  return new Color(0.50f, 0.78f, 0.62f);  // sea green
                case "za":   return new Color(0.90f, 0.55f, 0.35f);  // terracotta
                case "ru": case "rue": return new Color(0.80f, 0.50f, 0.55f); // mauve
                default:     return new Color(0.70f, 0.70f, 0.74f);  // grey
            }
        }

        // Actual on-screen size of the chart panel (it now FILLS the right panel, so the
        // chart math must read the live RectTransform instead of a fixed 640x320). Falls
        // back to sane defaults before the first layout pass computes the rect.
        private static void CompareChartSize(out float W, out float H)
        {
            W = 900f; H = 460f;
            try
            {
                var rt = compareGraphPanel != null ? compareGraphPanel.GetComponent<RectTransform>() : null;
                if (rt != null)
                {
                    if (rt.rect.width > 50f) W = rt.rect.width;
                    if (rt.rect.height > 50f) H = rt.rect.height;
                }
            }
            catch { }
        }

        // A "nice" round step so axis labels are clean numbers (100, 250, 500, 1000, …)
        // instead of maxV/divs giving 2185. Returns a step; caller takes ceil(max/step)*step.
        private static float NiceStep(float roughStep)
        {
            if (roughStep <= 0f) return 1f;
            float mag = Mathf.Pow(10f, Mathf.Floor(Mathf.Log10(roughStep)));
            float norm = roughStep / mag; // 1..10
            float nice = norm <= 1f ? 1f : norm <= 2f ? 2f : norm <= 2.5f ? 2.5f : norm <= 5f ? 5f : 10f;
            return nice * mag;
        }

        // Whole-number formatting with thousands separators — Sid wanted "12,345" not "12.3k".
        private static string FullNum(float v) => Mathf.RoundToInt(v).ToString("N0");

        // Mirror of the server XP curve (main.py xp_for_level = 100*n^1.5, cumulative).
        // Used to label the Total XP chart's gridlines with LEVELS instead of raw XP.
        private static long TotalXpForLevel(int level)
        {
            long sum = 0;
            for (int n = 1; n <= level && n <= 100; n++) sum += (long)(100.0 * Math.Pow(n, 1.5));
            return sum;
        }
        private static int LevelForXp(float xp)
        {
            long rem = (long)Math.Max(0f, xp); int lvl = 0;
            for (int n = 1; n <= 100; n++) { long need = (long)(100.0 * Math.Pow(n, 1.5)); if (rem < need) return lvl; rem -= need; lvl = n; }
            return 100;
        }

        // Smooth green(best) → yellow → red(worst) gradient for t in [0,1].
        private static Color GradeColor(float t)
        {
            t = Mathf.Clamp01(t);
            Color green = new Color(0.35f, 0.85f, 0.40f);
            Color amber = new Color(0.95f, 0.82f, 0.30f);
            Color red = new Color(0.95f, 0.40f, 0.40f);
            return t < 0.5f ? Color.Lerp(green, amber, t * 2f) : Color.Lerp(amber, red, (t - 0.5f) * 2f);
        }

        // Lazily-built white circle sprite for pie slices (Image type=Filled, Radial360).
        private static UnityEngine.Sprite _pieCircleSprite;
        private static UnityEngine.Sprite GetCircleSprite()
        {
            if (_pieCircleSprite != null) return _pieCircleSprite;
            try
            {
                int S = 128; float r = S * 0.5f, cx = r, cy = r;
                var tex = new Texture2D(S, S, TextureFormat.RGBA32, false);
                tex.hideFlags = HideFlags.HideAndDontSave;
                var px = new Color32[S * S];
                for (int y = 0; y < S; y++)
                    for (int x = 0; x < S; x++)
                    {
                        float dx = x + 0.5f - cx, dy = y + 0.5f - cy;
                        bool inside = dx * dx + dy * dy <= (r - 1f) * (r - 1f);
                        px[y * S + x] = inside ? new Color32(255, 255, 255, 255) : new Color32(255, 255, 255, 0);
                    }
                tex.SetPixels32(px); tex.Apply();
                _pieCircleSprite = UnityEngine.Sprite.Create(tex, new Rect(0, 0, S, S), new Vector2(0.5f, 0.5f), 100f);
                _pieCircleSprite.hideFlags = HideFlags.HideAndDontSave;
            }
            catch { _pieCircleSprite = null; }
            return _pieCircleSprite;
        }

        // ── July 21 item 9: Body Color shop glyphs ────────────────────────
        // A ROUNDS-character-ish preview (big circle body + two floating hands
        // + two feet) rasterized per color with a baked contrasting 1px outline
        // (dark SKUs like Obsidian/Charcoal would vanish on the panel without
        // it — which is also why the sprite must be served with Image.color =
        // WHITE, never tinted, or the outline gets tinted too). Prismatic gets
        // a baked rainbow (its preview_color is #FFFFFF = a lying white blob);
        // no runtime animation — a static frame is the agreed preview.
        // Cache tolerates destroyed sprites (Unity fake-null → rebuild).
        private static readonly Dictionary<string, UnityEngine.Sprite> _bodyGlyphCache =
            new Dictionary<string, UnityEngine.Sprite>();
        internal static UnityEngine.Sprite GetBodyGlyphSprite(string sku, string hex)
        {
            string key = sku == "pcolor_prismatic" ? "prismatic" : (hex ?? "").Trim().ToLowerInvariant();
            if (string.IsNullOrEmpty(key)) key = "#666a80";
            if (_bodyGlyphCache.TryGetValue(key, out var cached) && cached != null) return cached;
            try
            {
                const int S = 64;
                bool[] mask = new bool[S * S];
                Action<float, float, float> circle = (cx, cy, r) =>
                {
                    for (int y = 0; y < S; y++)
                        for (int x = 0; x < S; x++)
                        {
                            float dx = x + 0.5f - cx, dy = y + 0.5f - cy;
                            if (dx * dx + dy * dy <= r * r) mask[y * S + x] = true;
                        }
                };
                circle(32f, 36f, 20f);   // body
                circle(8f, 34f, 6f);     // left hand (ROUNDS hands float beside the body)
                circle(56f, 34f, 6f);    // right hand
                circle(22f, 9f, 5f);     // left foot
                circle(42f, 9f, 5f);     // right foot

                Color fill = new Color(0.40f, 0.42f, 0.50f);
                bool prismatic = key == "prismatic";
                if (!prismatic)
                {
                    string h = key.StartsWith("#") ? key : "#" + key;
                    if (!ColorUtility.TryParseHtmlString(h, out fill)) fill = new Color(0.40f, 0.42f, 0.50f);
                }
                float lum = 0.299f * fill.r + 0.587f * fill.g + 0.114f * fill.b;
                Color outline = (prismatic || lum > 0.5f) ? new Color(0.06f, 0.06f, 0.08f, 1f) : new Color(0.85f, 0.87f, 0.92f, 1f);

                var tex = new Texture2D(S, S, TextureFormat.RGBA32, false);
                tex.hideFlags = HideFlags.HideAndDontSave;
                var px = new Color32[S * S];
                for (int y = 0; y < S; y++)
                    for (int x = 0; x < S; x++)
                    {
                        int i = y * S + x;
                        if (!mask[i]) { px[i] = new Color32(0, 0, 0, 0); continue; }
                        bool edge = x == 0 || y == 0 || x == S - 1 || y == S - 1
                                    || !mask[i - 1] || !mask[i + 1] || !mask[i - S] || !mask[i + S];
                        Color c;
                        if (edge) c = outline;
                        else if (prismatic)
                            // Match the in-match prismatic look (S=0.85, V=1) across x.
                            c = Color.HSVToRGB(x / (float)(S - 1), 0.85f, 1f);
                        else c = fill;
                        px[i] = (Color32)c;
                    }
                tex.SetPixels32(px); tex.Apply();
                var sp = UnityEngine.Sprite.Create(tex, new Rect(0, 0, S, S), new Vector2(0.5f, 0.5f), 100f);
                sp.hideFlags = HideFlags.HideAndDontSave;
                _bodyGlyphCache[key] = sp;
                return sp;
            }
            catch { return null; }
        }

        // One pie wedge: a full circle Image radial-filled to `sweepFrac`, rotated so it
        // begins at `startFrac` of the way around (clockwise from top). Anchored at a
        // bottom-left point in compareGraphPanel.
        private static void DrawPieSlice(string name, float cx, float cy, float radius, float startFrac, float sweepFrac, Color col)
        {
            var sprite = GetCircleSprite();
            if (sprite == null) return;
            var go = new GameObject(name);
            go.transform.SetParent(compareGraphPanel.transform, false);
            var rt = go.AddComponent<RectTransform>();
            rt.anchorMin = Vector2.zero; rt.anchorMax = Vector2.zero; rt.pivot = new Vector2(0.5f, 0.5f);
            rt.anchoredPosition = new Vector2(cx, cy);
            rt.sizeDelta = new Vector2(radius * 2f, radius * 2f);
            rt.localRotation = Quaternion.Euler(0, 0, -startFrac * 360f); // clockwise
            var img = go.AddComponent(UIFactory.tImage);
            var bf = BindingFlags.Public | BindingFlags.Instance;
            UIFactory.tImage.GetProperty("sprite", bf)?.SetValue(img, sprite);
            UIFactory.tImage.GetProperty("color", bf)?.SetValue(img, col);
            try { UIFactory.tImage.GetProperty("type", bf)?.SetValue(img, Enum.ToObject(UIFactory.tImage.GetProperty("type", bf).PropertyType, 3)); } catch {} // Filled
            try { UIFactory.tImage.GetProperty("fillMethod", bf)?.SetValue(img, Enum.ToObject(UIFactory.tImage.GetProperty("fillMethod", bf).PropertyType, 4)); } catch {} // Radial360
            try { UIFactory.tImage.GetProperty("fillOrigin", bf)?.SetValue(img, 2); } catch {} // Top
            try { UIFactory.tImage.GetProperty("fillClockwise", bf)?.SetValue(img, true); } catch {}
            try { UIFactory.tImage.GetProperty("fillAmount", bf)?.SetValue(img, Mathf.Clamp01(sweepFrac)); } catch {}
        }

        // Charts every non-card, non-line metric as bars in compareGraphPanel:
        //   • single value per player  → one bar per player (Avg FPS, Peak Elo, Total
        //     XP, Achievements, Avg Cards/Game)
        //   • two values per player    → grouped bars (Hit / Block %)
        //   • distribution per player  → stacked bar (Region Time, by region %)
        // Y axis gets 4 gridlines + labels; player names sit under each group.
        private static void BuildCompareBarChart(string metricName)
        {
            if (compareGraphPanel == null) return;
            for (int c = compareGraphPanel.transform.childCount - 1; c >= 0; c--)
                UnityEngine.Object.Destroy(compareGraphPanel.transform.GetChild(c).gameObject);

            // Gather selected players that have cached stats, preserving select order
            // (so bar color matches the picker swatch).
            var idxs = new List<int>();
            for (int i = 0; i < compareSelected.Count; i++)
                if (compareStatsCache.TryGetValue(compareSelected[i], out var ps) && ps != null)
                    idxs.Add(i);

            CompareChartSize(out float W, out float H);

            if (idxs.Count == 0)
            {
                MakeGraphLabel("CmpBarNone", $"<color=#888>Select players (left) to chart <b>{metricName}</b>.</color>",
                    new Vector2(0.5f, 0.5f), Vector2.zero, new Vector2(W - 40, 40), UIFactory.AlignMidCenter);
                return;
            }

            // Region distribution → pie-chart grid (much clearer than the old stacked bar).
            if (metricName == "Region Time") { BuildComparePieChart(idxs, W, H); return; }
            // Per-achievement comparison grid (v1.29).
            if (metricName == "Achievement Grid") { BuildCompareAchievementGrid(idxs, W, H); return; }

            float padL = 60f, padR = 16f, padT = 34f, padB = 48f;
            float plotW = W - padL - padR, plotH = H - padT - padB;
            int n = idxs.Count;
            float groupW = plotW / n;

            string title; bool grouped = false, avgCards = false; string unit = "";
            switch (metricName)
            {
                case "Hit / Block %": title = "Hit % vs Block %"; grouped = true; unit = "%"; break;
                case "Avg Cards / Game": title = "Avg Cards per Game  (lower = stronger)"; avgCards = true; break;
                case "Avg FPS": title = "Average FPS"; break;
                case "Peak Elo": title = "Peak Elo"; break;
                case "Total XP": title = "Total XP"; break;
                case "Achievements": title = "Achievements unlocked"; break;
                // v1.29 —  grouped pairs get data-driven scale (groupedData below).
                case "Top Streaks": title = "Best Win Streak"; grouped = true; break;
                case "5-0s Given / Taken": title = "5-0 Sweeps"; grouped = true; break;
                case "Bets Won / Lost": title = "Betting Record"; grouped = true; break;
                case "Keys / Sec": title = "Avg Keystrokes per Second (in combat)"; break;
                case "Keys / Game": title = "Avg Key Presses per Game"; break;
                case "Avg Game Length": title = "Avg Game Length (minutes)"; break;
                case "2v2 Rating": title = "2v2 Rating"; break;
                default: title = metricName; break;
            }
            // Per-pair legend labels for grouped metrics (solid vs dim bars).
            string legA = "Hit", legB = "Block";
            switch (metricName)
            {
                // Units differ: ranked best is per-SERIES, casual per-GAME (item 5).
                case "Top Streaks": legA = "Ranked (series)"; legB = "Casual (games)"; break;
                case "5-0s Given / Taken": legA = "Given"; legB = "Taken"; break;
                case "Bets Won / Lost": legA = "Won"; legB = "Lost"; break;
            }
            bool groupedPct = metricName == "Hit / Block %";
            MakeGraphLabel("CmpBarTitle", $"<color=#CCC><b>{title}</b></color>",
                new Vector2(0, 1), new Vector2(padL, -4f), new Vector2(W - padL, 18), UIFactory.AlignMidLeft);

            Func<ApiClient.PlayerStatsData, float> v1 = null, v2 = null;
            switch (metricName)
            {
                case "Hit / Block %":
                    v1 = ps => ps.bullets_fired > 0 ? (float)ps.bullets_hit * 100f / ps.bullets_fired : 0f;
                    v2 = ps => ps.blocks_activated > 0 ? (float)ps.blocks_successful * 100f / ps.blocks_activated : 0f;
                    break;
                case "Avg Cards / Game": v1 = ps => ps.avg_cards_per_game; break;
                case "Avg FPS": v1 = ps => ps.avg_fps; break;
                case "Peak Elo": v1 = ps => ps.peak_rating; break;
                case "Total XP": v1 = ps => ps.total_xp; break;
                case "Achievements": v1 = ps => ps.achievements_unlocked; break;
                // v1.29 metrics — all server-computed fields on PlayerStatsData.
                case "Top Streaks":
                    v1 = ps => ps.best_ranked_streak;
                    v2 = ps => ps.best_casual_streak;
                    break;
                case "5-0s Given / Taken":
                    v1 = ps => ps.sweeps_given;
                    v2 = ps => ps.sweeps_taken;
                    break;
                case "Bets Won / Lost":
                    v1 = ps => ps.bets_won;
                    v2 = ps => ps.bets_lost;
                    break;
                case "Keys / Sec": v1 = ps => ps.avg_keys_per_sec; break;
                case "Keys / Game": v1 = ps => ps.avg_keys_per_game; break;
                case "Avg Game Length": v1 = ps => ps.avg_game_seconds / 60f; break;
                case "2v2 Rating": v1 = ps => ps.team_rating; break;
                default: v1 = ps => 0f; break;
            }

            // Axis scale + a NICE round step so labels are clean whole numbers.
            float maxV, step;
            if (groupedPct) { maxV = 100f; step = 25f; }       // 0..100 %
            else if (avgCards) { maxV = 5f; step = 1f; }       // fixed 0..5, lines at each int
            else
            {
                float dataMax = 0.0001f;
                foreach (int i in idxs)
                {
                    var psX = compareStatsCache[compareSelected[i]];
                    float v = v1(psX); if (v > dataMax) dataMax = v;
                    if (grouped && v2 != null) { float vb = v2(psX); if (vb > dataMax) dataMax = vb; }
                }
                step = NiceStep(dataMax / 4f);
                maxV = Mathf.Ceil(dataMax * 1.08f / step) * step;
                if (maxV < step) maxV = step;
            }

            if (metricName == "Total XP")
            {
                // Gridlines/labels are LEVELS (at each level's cumulative-XP threshold),
                // not raw XP — Sid's request. Levels aren't evenly XP-spaced, so the lines
                // bunch toward the top; that's expected.
                int topLevel = LevelForXp(maxV);
                int lvlStep = Mathf.Max(1, Mathf.CeilToInt(topLevel / 6f));
                MakeGraphLabel("CmpBarY0", "<color=#999>Lv 0</color>",
                    new Vector2(0, 0), new Vector2(padL - 4f, padB - 6f), new Vector2(52, 12), UIFactory.AlignMidRight);
                for (int L = lvlStep; L <= topLevel; L += lvlStep)
                {
                    float xpAt = TotalXpForLevel(L);
                    if (xpAt > maxV) break;
                    float yy = padB + (xpAt / maxV) * plotH;
                    DrawBar($"CmpBarGridL{L}", padL, yy, plotW, 1f, new Color(1f, 1f, 1f, 0.10f));
                    MakeGraphLabel($"CmpBarYL{L}", $"<color=#999>Lv {L}</color>",
                        new Vector2(0, 0), new Vector2(padL - 4f, yy - 6f), new Vector2(52, 12), UIFactory.AlignMidRight);
                }
            }
            else
            {
                int yDivs = Mathf.Clamp(Mathf.RoundToInt(maxV / step), 2, 10);
                for (int gi = 0; gi <= yDivs; gi++)
                {
                    float val = gi * step;
                    if (val > maxV + 0.001f) break;
                    float yy = padB + (val / maxV) * plotH;
                    DrawBar($"CmpBarGrid{gi}", padL, yy, plotW, 1f, new Color(1f, 1f, 1f, 0.10f));
                    MakeGraphLabel($"CmpBarYLbl{gi}", $"<color=#999>{(avgCards ? val.ToString("0") : FullNum(val))}{unit}</color>",
                        new Vector2(0, 0), new Vector2(padL - 4f, yy - 6f), new Vector2(52, 12), UIFactory.AlignMidRight);
                }
            }

            if (grouped)
                MakeGraphLabel("CmpHBLeg", $"<color=#EEEEEE>solid = {legA}</color>   <color=#888888>dim = {legB}</color>",
                    new Vector2(1, 1), new Vector2(-padR, -4f), new Vector2(260, 14), UIFactory.AlignMidRight);

            // Adaptive name length: full names when there's room, trimmed when crowded.
            int nameLen = Mathf.Clamp((int)(groupW / 8f), 5, 18);

            for (int gi2 = 0; gi2 < n; gi2++)
            {
                int i = idxs[gi2];
                var ps = compareStatsCache[compareSelected[i]];
                Color pc = COMPARE_COLORS[i % COMPARE_COLORS.Length];
                float gx = padL + gi2 * groupW;

                if (grouped)
                {
                    float bw = groupW * 0.32f, gap = groupW * 0.06f;
                    float bx0 = gx + (groupW - (bw * 2f + gap)) * 0.5f;
                    float hv = Mathf.Clamp(v1(ps), 0f, maxV), bvv = Mathf.Clamp(v2(ps), 0f, maxV);
                    DrawBar($"CmpGrpA{gi2}", bx0, padB, bw, hv / maxV * plotH, new Color(pc.r, pc.g, pc.b, 1f));
                    DrawBar($"CmpGrpB{gi2}", bx0 + bw + gap, padB, bw, bvv / maxV * plotH, new Color(pc.r * 0.5f, pc.g * 0.5f, pc.b * 0.5f, 1f));
                    MakeGraphLabel($"CmpGrpVA{gi2}", $"<color=#EEE>{v1(ps):F1}</color>", new Vector2(0, 0), new Vector2(bx0 - 8f, padB + hv / maxV * plotH + 1f), new Vector2(bw + 16f, 11), UIFactory.AlignMidCenter);
                    MakeGraphLabel($"CmpGrpVB{gi2}", $"<color=#AAA>{v2(ps):F1}</color>", new Vector2(0, 0), new Vector2(bx0 + bw + gap - 8f, padB + bvv / maxV * plotH + 1f), new Vector2(bw + 16f, 11), UIFactory.AlignMidCenter);
                }
                else
                {
                    float bw = groupW * 0.58f;
                    float bx = gx + (groupW - bw) * 0.5f;
                    float val = v1(ps);
                    float clamped = Mathf.Clamp(val, 0f, maxV);
                    Color bc = pc;
                    if (avgCards && val > 0f) bc = GradeColor((val - 1f) / 4f); // 1=best→green, 5=worst→red
                    DrawBar($"CmpBar{gi2}", bx, padB, bw, clamped / maxV * plotH, bc);
                    string vlbl = avgCards ? val.ToString("F2")
                                : metricName == "Total XP" ? $"Lv {ps.level}"
                                // Small-float metrics keep their decimals — FullNum's
                                // whole-number rounding made every game length a solid
                                // minute (Sid). 5.4m reads as 5m24s.
                                : metricName == "Avg Game Length" ? $"{val:F1}m"
                                : metricName == "Keys / Sec" ? val.ToString("F1")
                                : FullNum(val);
                    MakeGraphLabel($"CmpBarV{gi2}", $"<color=#EEE>{vlbl}</color>",
                        new Vector2(0, 0), new Vector2(bx - 6f, padB + clamped / maxV * plotH + 1f), new Vector2(bw + 12f, 12), UIFactory.AlignMidCenter);
                }

                MakeGraphLabel($"CmpBarName{gi2}", $"<b><color=#{ColorToHex(pc)}>{Trunc(ps.display_name, nameLen)}</color></b>",
                    new Vector2(0, 0), new Vector2(gx - 4f, padB - 18f), new Vector2(groupW + 8f, 16), UIFactory.AlignMidCenter, 13f);
            }
        }

        // v1.29 — per-achievement comparison: one row per achievement, one column
        // per selected player, YES/no cells in each player's compare color. Data
        // comes from FetchAchievementsForCompare (cached per steam id).
        private static void BuildCompareAchievementGrid(List<int> idxs, float W, float H)
        {
            try
            {
                MakeGraphLabel("CmpAchTitle", "<color=#CCC><b>Achievement comparison</b></color>",
                    new Vector2(0, 1), new Vector2(16f, -4f), new Vector2(W - 20, 18), UIFactory.AlignMidLeft);

                bool missing = false;
                foreach (int i in idxs)
                {
                    string sid = compareSelected[i];
                    if (!ApiClient.CompareAchievements.ContainsKey(sid))
                    {
                        ApiClient.FetchAchievementsForCompare(sid);
                        missing = true;
                    }
                }
                if (missing)
                {
                    MakeGraphLabel("CmpAchLoad", "<color=#888>Loading achievements...</color>",
                        new Vector2(0.5f, 0.5f), Vector2.zero, new Vector2(W - 40, 30), UIFactory.AlignMidCenter);
                    return;
                }

                // Union of keys across the selected players, stable-sorted by display name.
                var keys = new List<string>();
                foreach (int i in idxs)
                    foreach (var k in ApiClient.CompareAchievements[compareSelected[i]].Keys)
                        if (!keys.Contains(k)) keys.Add(k);
                keys.Sort((a, b) => string.CompareOrdinal(AchName(a), AchName(b)));
                if (keys.Count == 0)
                {
                    MakeGraphLabel("CmpAchNone", "<color=#888>No achievement data.</color>",
                        new Vector2(0.5f, 0.5f), Vector2.zero, new Vector2(W - 40, 30), UIFactory.AlignMidCenter);
                    return;
                }

                // Bug batch item 12: with ~40 achievements a single column forced
                // 15px rows and 11f text — unreadable, and below ~12pt the SDF
                // font drops thin glyphs entirely. Split the grid into two
                // side-by-side halves so rows stay >=20px at a fixed 13f bold.
                int half = (keys.Count + 1) / 2;
                float blockW = (W - 36f) / 2f;
                float nameW = Mathf.Min(200f, blockW * 0.46f);
                float colW = (blockW - nameW - 8f) / Mathf.Max(1, idxs.Count);
                float headerY = -26f;
                float rowH = Mathf.Clamp((H - 66f) / Mathf.Max(1, half), 20f, 28f);
                const float fontSz = 13f;
                for (int blk = 0; blk < 2; blk++)
                {
                    float bx = 12f + blk * (blockW + 12f);
                    int from = blk * half, to = Mathf.Min(keys.Count, (blk + 1) * half);
                    if (from >= to) break;
                    for (int c = 0; c < idxs.Count; c++)
                    {
                        int i = idxs[c];
                        var ps = compareStatsCache[compareSelected[i]];
                        Color pc = COMPARE_COLORS[i % COMPARE_COLORS.Length];
                        MakeGraphLabel($"CmpAchHdr{blk}_{c}",
                            $"<b><color=#{ColorToHex(pc)}>{Trunc(ps.display_name, Mathf.Clamp((int)(colW / 9f), 4, 16))}</color></b>",
                            new Vector2(0, 1), new Vector2(bx + nameW + c * colW, headerY), new Vector2(colW, 16), UIFactory.AlignMidCenter, 13f);
                    }
                    for (int r = from; r < to; r++)
                    {
                        float y = headerY - 20f - (r - from) * rowH;
                        MakeGraphLabel($"CmpAchN{r}", $"<color=#CCCCCC>{Trunc(AchName(keys[r]), 24)}</color>",
                            new Vector2(0, 1), new Vector2(bx, y), new Vector2(nameW, rowH), UIFactory.AlignMidLeft, fontSz);
                        for (int c = 0; c < idxs.Count; c++)
                        {
                            int i = idxs[c];
                            var achs = ApiClient.CompareAchievements[compareSelected[i]];
                            bool has = achs.TryGetValue(keys[r], out var ad) && ad.unlocked;
                            Color pc = COMPARE_COLORS[i % COMPARE_COLORS.Length];
                            string cell = has ? $"<b><color=#{ColorToHex(pc)}>YES</color></b>" : "<color=#555555>-</color>";
                            MakeGraphLabel($"CmpAchC{r}_{c}", cell,
                                new Vector2(0, 1), new Vector2(bx + nameW + c * colW, y), new Vector2(colW, rowH), UIFactory.AlignMidCenter, fontSz);
                        }
                    }
                }
            }
            catch (Exception ex) { Plugin.Log.LogWarning($"[COMPARE] achievement grid failed: {ex.Message}"); }
        }

        private static string AchName(string key)
        {
            if (ApiClient.AchievementDisplayNames.TryGetValue(key, out var n) && !string.IsNullOrEmpty(n)) return n;
            // Fallback: prettify the key ("stan_slayer" → "Stan Slayer").
            var parts = (key ?? "").Split('_');
            for (int i = 0; i < parts.Length; i++)
                if (parts[i].Length > 0) parts[i] = char.ToUpperInvariant(parts[i][0]) + parts[i].Substring(1);
            return string.Join(" ", parts);
        }

        // Region distribution as a grid of per-player pie charts with a shared region
        // legend; the larger (1-2 player) pies also get leader lines + % labels sticking
        // out. Replaces the old stacked bar Sid called "hideous".
        private static void BuildComparePieChart(List<int> idxs, float W, float H)
        {
            try
            {
                MakeGraphLabel("CmpPieTitle", "<color=#CCC><b>Region distribution</b></color>",
                    new Vector2(0, 1), new Vector2(16f, -4f), new Vector2(W - 20, 18), UIFactory.AlignMidLeft);

                // Shared region legend.
                var regions = new List<string>();
                foreach (int i in idxs)
                {
                    var ps = compareStatsCache[compareSelected[i]];
                    if (ps.region_names == null) continue;
                    foreach (var rn in ps.region_names) if (!regions.Contains(rn)) regions.Add(rn);
                }
                // Bigger, more-readable legend chips (wrap every 4). A TMP <mark> highlight
                // gives each a solid color swatch that stays glued to its label (a separate
                // positioned rect drifted out of alignment).
                for (int li = 0; li < regions.Count; li++)
                {
                    float lxr = -14f - (li % 4) * 104f;
                    float lyr = -4f - (li / 4) * 17f;
                    string hex = ColorToHex(RegionColor(regions[li]));
                    MakeGraphLabel($"CmpPieLeg{li}",
                        $"<mark=#{hex}FF>  </mark> <b>{regions[li].ToUpperInvariant()}</b>",
                        new Vector2(1, 1), new Vector2(lxr, lyr), new Vector2(96, 14), UIFactory.AlignMidLeft, 13f);
                }

                int n = idxs.Count;
                int cols = n <= 1 ? 1 : n <= 2 ? 2 : n <= 6 ? 3 : 4;
                int rows = (n + cols - 1) / cols;
                float topPad = 30f + Mathf.Ceil(regions.Count / 4f) * 17f;
                float botPad = 8f;
                float cellW = (W - 20f) / cols;
                float cellH = (H - topPad - botPad) / Mathf.Max(1, rows);
                float radius = Mathf.Max(26f, Mathf.Min(cellW, cellH) * 0.36f);
                bool leaderLines = cols <= 3;

                for (int k = 0; k < n; k++)
                {
                    int i = idxs[k];
                    var ps = compareStatsCache[compareSelected[i]];
                    int col = k % cols, row = k / cols;
                    float cx = 10f + col * cellW + cellW * 0.5f;
                    float cy = H - topPad - row * cellH - cellH * 0.5f; // bottom-left coord space

                    MakeGraphLabel($"CmpPieName{k}",
                        $"<b><color=#{ColorToHex(COMPARE_COLORS[i % COMPARE_COLORS.Length])}>{Trunc(ps.display_name, 14)}</color></b>",
                        new Vector2(0, 0), new Vector2(cx - cellW * 0.5f, cy + radius + 4f), new Vector2(cellW, 16), UIFactory.AlignMidCenter, 14f);

                    int tot = 0; if (ps.region_matches != null) foreach (var m in ps.region_matches) tot += m;
                    if (ps.region_names == null || tot <= 0)
                    {
                        MakeGraphLabel($"CmpPieNo{k}", "<color=#888>no data</color>",
                            new Vector2(0, 0), new Vector2(cx - 40f, cy - 6f), new Vector2(80, 12), UIFactory.AlignMidCenter);
                        continue;
                    }
                    // Border ring: a slightly larger dark circle behind the slices gives the
                    // pie a clean edge (Sid: "put a border around the edge, looks rough").
                    DrawPieSlice($"CmpPieBdr{k}", cx, cy, radius + 2.5f, 0f, 1f, new Color(0.10f, 0.11f, 0.14f, 1f));
                    float acc = 0f;
                    for (int ri = 0; ri < ps.region_names.Count; ri++)
                    {
                        int mm = ps.region_matches.Count > ri ? ps.region_matches[ri] : 0;
                        if (mm <= 0) continue;
                        float frac = (float)mm / tot;
                        DrawPieSlice($"CmpPie{k}_{ri}", cx, cy, radius, acc, frac, RegionColor(ps.region_names[ri]));
                        if (leaderLines && frac >= 0.07f)
                        {
                            float midFrac = acc + frac * 0.5f;
                            float ang = Mathf.PI * 0.5f - midFrac * 2f * Mathf.PI; // top, clockwise
                            float ex = cx + Mathf.Cos(ang) * radius, ey = cy + Mathf.Sin(ang) * radius;
                            float lx = cx + Mathf.Cos(ang) * (radius + 20f), ly = cy + Mathf.Sin(ang) * (radius + 20f);
                            DrawGraphSegment($"CmpPieLn{k}_{ri}", ex, ey, lx, ly, new Color(0.8f, 0.8f, 0.8f, 0.7f), 1.5f);
                            bool rightSide = Mathf.Cos(ang) >= 0f;
                            int align = rightSide ? UIFactory.AlignMidLeft : UIFactory.AlignMidRight;
                            float lblX = rightSide ? lx + 2f : lx - 66f;
                            MakeGraphLabel($"CmpPieLbl{k}_{ri}",
                                $"<color=#CCC>{ps.region_names[ri].ToUpperInvariant()} {frac * 100f:F0}%</color>",
                                new Vector2(0, 0), new Vector2(lblX, ly - 6f), new Vector2(64, 12), align);
                        }
                        acc += frac;
                    }
                }
            }
            catch (Exception ex) { Plugin.Log.LogWarning($"[COMPARE] pie chart failed: {ex.Message}"); }
        }

        // Card metrics (Top / Worst) as a multi-column grid of per-player blocks so
        // many players wrap sideways instead of running off the bottom of the page.
        // Built into compareCardsContent (the card scroll's content). 3 columns.
        private static void BuildCompareCardGrid(string metricName)
        {
            if (compareCardsContent == null || txtCompareCards == null) return;
            // Tear down any prior grid container.
            var prev = compareCardsContent.transform.Find("CmpCardCols");
            if (prev != null) UnityEngine.Object.Destroy(prev.gameObject);

            if (compareSelected.Count == 0)
            {
                UIFactory.SetText(txtCompareCards, $"<color=#888>Select players (left) to compare <b>{metricName}</b>.</color>");
                ((Component)txtCompareCards).gameObject.SetActive(true);
                return;
            }
            ((Component)txtCompareCards).gameObject.SetActive(false);

            // Columns container: an HLG of N vertical columns. Players fill column by
            // column (down, then across).
            int cols = compareSelected.Count <= 3 ? compareSelected.Count : compareSelected.Count <= 8 ? 2 : 3;
            if (cols < 1) cols = 1;
            int perCol = (compareSelected.Count + cols - 1) / cols;

            var grid = new GameObject("CmpCardCols");
            grid.transform.SetParent(compareCardsContent.transform, false);
            grid.AddComponent<RectTransform>();
            UIFactory.AddHLG(grid, spacing: 10, forceExpandH: false);

            var colGOs = new GameObject[cols];
            for (int c = 0; c < cols; c++)
            {
                var colGO = new GameObject($"CmpCol{c}");
                colGO.transform.SetParent(grid.transform, false);
                colGO.AddComponent<RectTransform>();
                UIFactory.AddVLG(colGO, spacing: 8);
                UIFactory.AddLE(colGO, flexW: 1);
                colGOs[c] = colGO;
            }

            for (int i = 0; i < compareSelected.Count; i++)
            {
                int col = Math.Min(i / perCol, cols - 1);
                string sid = compareSelected[i];
                Color pc = COMPARE_COLORS[i % COMPARE_COLORS.Length];
                var sb = new System.Text.StringBuilder();
                if (!compareStatsCache.TryGetValue(sid, out var ps) || ps == null)
                {
                    sb.Append($"<color=#{ColorToHex(pc)}><b>(loading...)</b></color>");
                }
                else
                {
                    sb.Append($"<color=#{ColorToHex(pc)}><b>{ps.display_name}</b></color>\n");
                    if (metricName == "Worst Cards")
                        AppendCardList(sb, ps.worst_card_names, ps.worst_card_picks, ps.worst_card_win_rates, "not enough data (4+ picks)");
                    else
                        AppendCardList(sb, ps.top_card_names, ps.top_card_picks, ps.top_card_win_rates, "no card data");
                }
                var cell = UIFactory.CreateText($"CmpCell{i}", colGOs[col].transform, sb.ToString(),
                    14f, C_DIM, UIFactory.AlignTopLeft, sizeDelta: new Vector2(250, 24));
                UIFactory.SetWordWrap(cell, true);
                UIFactory.SetTextAutoHeight(cell);
            }
        }

        // Renders the currently-selected metric for all selected players into the
        // scroll panel. metricName drives the layout: card lists, per-player rows,
        // or a region breakdown. (Retained for reference; routing now uses
        // BuildCompareBarChart / BuildCompareCardGrid.)
        private static void BuildCompareMetricTable()
        {
            if (txtCompareCards == null) return;
            string metricName = COMPARE_METRICS[Math.Max(0, Math.Min(compareMetric, COMPARE_METRICS.Length - 1))];
            if (compareSelected.Count == 0)
            {
                UIFactory.SetText(txtCompareCards, $"<color=#888>Select players (left) to compare <b>{metricName}</b>.</color>");
                return;
            }
            var sb = new System.Text.StringBuilder();
            for (int i = 0; i < compareSelected.Count; i++)
            {
                string sid = compareSelected[i];
                Color col = COMPARE_COLORS[i % COMPARE_COLORS.Length];
                if (!compareStatsCache.TryGetValue(sid, out var ps) || ps == null)
                {
                    sb.Append($"<color=#{ColorToHex(col)}><b>(loading...)</b></color>\n\n");
                    continue;
                }
                sb.Append($"<color=#{ColorToHex(col)}><b>{ps.display_name}</b></color>  ");
                switch (metricName)
                {
                    case "Top Cards":
                        sb.Append("\n");
                        AppendCardList(sb, ps.top_card_names, ps.top_card_picks, ps.top_card_win_rates, "no card data");
                        break;
                    case "Worst Cards":
                        sb.Append("\n");
                        AppendCardList(sb, ps.worst_card_names, ps.worst_card_picks, ps.worst_card_win_rates,
                                       "not enough card data (need 4+ picks)");
                        break;
                    case "Hit / Block %":
                    {
                        string hit = ps.bullets_fired > 0
                            ? $"<color=#FF9988>Hit {(float)ps.bullets_hit * 100f / ps.bullets_fired:F1}%</color> <color=#888>({ps.bullets_hit}/{ps.bullets_fired})</color>"
                            : "<color=#888>Hit —</color>";
                        string blk = ps.blocks_activated > 0
                            ? $"<color=#99CCFF>Block {(float)ps.blocks_successful * 100f / ps.blocks_activated:F1}%</color> <color=#888>({ps.blocks_successful}/{ps.blocks_activated})</color>"
                            : "<color=#888>Block —</color>";
                        sb.Append($"{hit}   {blk}\n");
                        break;
                    }
                    case "Avg Cards / Game":
                    {
                        // Closer to 1 = stronger (wins faster, picks fewer cards).
                        float v = ps.avg_cards_per_game;
                        string vc = v > 0 && v <= 2.0f ? "#00FF00" : v <= 3.0f ? "#AAAAAA" : "#FF6666";
                        sb.Append(v > 0 ? $"<color={vc}>{v:F2}</color> cards/game  <color=#888>(lower = stronger)</color>\n"
                                        : "<color=#888>no data</color>\n");
                        break;
                    }
                    case "Avg FPS":
                        sb.Append(ps.avg_fps > 0 ? $"<color=#9AD0FF>{ps.avg_fps}</color> avg fps\n" : "<color=#888>no fps data</color>\n");
                        break;
                    case "Peak Elo":
                        sb.Append($"<color=#FFD94D>{ps.peak_rating:F0}</color> peak  <color=#888>(now {ps.rating:F0})</color>\n");
                        break;
                    case "Total XP":
                        sb.Append($"<color=#66CCFF>{ps.total_xp:N0}</color> XP  <color=#888>(Lv {ps.level})</color>\n");
                        break;
                    case "Achievements":
                    {
                        int total = ApiClient.AchievementDefs != null ? ApiClient.AchievementDefs.Count : 0;
                        sb.Append(total > 0
                            ? $"<color=#FFD94D>{ps.achievements_unlocked}/{total}</color> unlocked  <color=#888>({ps.achievements_unlocked * 100 / Math.Max(1, total)}%)</color>\n"
                            : $"<color=#FFD94D>{ps.achievements_unlocked}</color> unlocked\n");
                        break;
                    }
                    case "Region Time":
                        sb.Append("\n");
                        if (ps.region_names != null && ps.region_names.Count > 0)
                        {
                            int tot = 0; foreach (var m in ps.region_matches) tot += m;
                            for (int ri = 0; ri < ps.region_names.Count && ri < 8; ri++)
                            {
                                int mm = ps.region_matches.Count > ri ? ps.region_matches[ri] : 0;
                                int pct = tot > 0 ? mm * 100 / tot : 0;
                                sb.Append($"   <color=#AAD>{ps.region_names[ri].ToUpperInvariant()}</color>  {pct}% <color=#888>({mm})</color>\n");
                            }
                        }
                        else sb.Append("   <color=#888><i>no region data</i></color>\n");
                        break;
                    default:
                        sb.Append("\n");
                        break;
                }
                sb.Append("\n");
            }
            UIFactory.SetText(txtCompareCards, sb.ToString());
        }

        private static void AppendCardList(System.Text.StringBuilder sb, List<string> names,
                                           List<int> picks, List<float> wrs, string emptyMsg)
        {
            if (names != null && names.Count > 0)
            {
                for (int ci = 0; ci < names.Count && ci < 8; ci++)
                {
                    string p = picks != null && picks.Count > ci ? $" <color=#888>({picks[ci]}x)</color>" : "";
                    float wr = wrs != null && wrs.Count > ci ? wrs[ci] * 100f : 0f;
                    string wrCol = wr >= 55 ? "#00FF00" : wr <= 45 ? "#FF6666" : "#AAAAAA";
                    sb.Append($"   {names[ci]}{p}  <color={wrCol}>{wr:F0}%</color>\n");
                }
            }
            else sb.Append($"   <color=#888><i>{emptyMsg}</i></color>\n");
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

        /// <summary>Builds the clicked player's "Ranked Series vs You" section (returned) and
        /// the "Ranked History" section (out param). Split into two strings (round 3 screenshot
        /// markup) so the Older/Newer pager GameObject can sit BETWEEN them — directly under
        /// the series list it pages — instead of below the whole blob.</summary>
        private static string BuildViewHistoryText(out string historyPart)
        {
            historyPart = "";
            if (string.IsNullOrEmpty(selectedSteamId)) return "";
            var hist = selectedViewHistory;
            if (hist == null) return "\n<color=#888><i>Loading match history...</i></color>\n";
            var sb = new System.Text.StringBuilder();
            string myId = MatchTracker.LocalSteamId;
            bool viewingSelf = selectedSteamId == myId;
            string theirName = Trunc(selectedStats?.display_name ?? "Them", 12);

            // ── Ranked Series vs You (only when viewing someone else) ──
            // Shows ALL head-to-head ranked series, paginated (H2H_SERIES_PER_PAGE per
            // page) via the h2hPager controls. History is newest-first, so GroupBySeries
            // yields groups newest→oldest; page 0 is the most recent series.
            int h2hGroupCount = 0;
            if (!viewingSelf && !string.IsNullOrEmpty(myId) && myId != "unknown")
            {
                var vsMe = hist.FindAll(m => m.opponent_steam_id == myId
                    && !string.IsNullOrEmpty(m.series_id) && m.series_id != "null" && m.is_ranked);
                if (vsMe.Count > 0)
                {
                    var grp = GroupBySeries(vsMe);
                    grp.RemoveAll(g => g.matches == null || g.matches.Count == 0);
                    h2hGroupCount = grp.Count;
                    if (h2hGroupCount > 0)
                    {
                        int totalPages = (h2hGroupCount + H2H_SERIES_PER_PAGE - 1) / H2H_SERIES_PER_PAGE;
                        h2hSeriesTotalPages = totalPages;
                        if (h2hSeriesPage < 0) h2hSeriesPage = 0;
                        if (h2hSeriesPage > totalPages - 1) h2hSeriesPage = totalPages - 1;
                        int start = h2hSeriesPage * H2H_SERIES_PER_PAGE;
                        int end = Math.Min(start + H2H_SERIES_PER_PAGE, h2hGroupCount);
                        string pageTag = totalPages > 1 ? $"  <color=#888>(page {h2hSeriesPage + 1}/{totalPages}, {h2hGroupCount} total)</color>" : "";
                        sb.Append($"\n<color=#FFD94D>Ranked Series vs You</color>{pageTag}\n");
                        for (int gi = start; gi < end; gi++)
                        {
                            var g = grp[gi];
                            var first = g.matches[0];
                            string score = first.series_score ?? "?-?";
                            string hdt = ""; try { if (!string.IsNullOrEmpty(first.ended_at) && first.ended_at.Length >= 10) hdt = DateTime.Parse(first.ended_at).ToString("M/d/yy"); } catch {}
                            // series_score is their side; flip for "your" series result.
                            bool sComplete = false, sIWon = false;
                            try { var p = score.Split('-'); int tw = int.Parse(p[0]), mw = int.Parse(p[1]); sComplete = tw >= 2 || mw >= 2; sIWon = mw > tw; } catch {}
                            string sHdr = sComplete ? (sIWon ? "<color=#00FF00>WON</color>" : "<color=#FF6666>LOST</color>") : "<color=#FFD94D>in progress</color>";
                            sb.Append($"  {sHdr}  <color=#888>{score} their side</color>  <color=#666>{hdt}</color>\n");
                            foreach (var m in g.matches)
                            {
                                // m.* is the VIEWED player's perspective; flip for "my" result.
                                bool iWon = !m.won;
                                string r = iWon ? "<color=#00FF00>W</color>" : "<color=#FF6666>L</color>";
                                string dt = ""; try { if (!string.IsNullOrEmpty(m.ended_at) && m.ended_at.Length >= 10) dt = DateTime.Parse(m.ended_at).ToString("M/d"); } catch {}
                                // opponent_rounds_won is MY rounds (I'm their opponent); player_rounds_won is theirs.
                                sb.Append($"    {r}  {m.opponent_rounds_won}-{m.player_rounds_won}  <color=#888>{dt}</color>\n");
                                if (!string.IsNullOrEmpty(m.opp_cards_display))
                                    sb.Append($"      <color=#6677AA>You:</color> {FormatCardLine(m.opp_cards_display)}\n");
                                if (!string.IsNullOrEmpty(m.cards_display))
                                    sb.Append($"      <color=#AA7766>{theirName}:</color> {FormatCardLine(m.cards_display)}\n");
                            }
                        }
                    }
                }
            }
            // Drive the pager visibility/labels off this render (it lives outside the
            // scrolled text so its buttons stay clickable).
            if (h2hPager != null)
            {
                bool showPager = h2hGroupCount > H2H_SERIES_PER_PAGE;
                h2hPager.SetActive(showPager);
                if (showPager)
                {
                    if (txtH2hPage != null) UIFactory.SetText(txtH2hPage, $"{h2hSeriesPage + 1}/{h2hSeriesTotalPages}");
                    if (h2hPrev != null) h2hPrev.SetActive(h2hSeriesPage > 0);
                    if (h2hNext != null) h2hNext.SetActive(h2hSeriesPage < h2hSeriesTotalPages - 1);
                }
            }

            // ── Ranked History (their recent completed ranked series) ──
            // Composed into its OWN string so it renders in txtLBDetailB, below
            // the pager (round 3 screenshot markup).
            var hb = new System.Text.StringBuilder();
            var ranked = hist.FindAll(m => m.is_ranked && !string.IsNullOrEmpty(m.series_id) && m.series_id != "null");
            if (ranked.Count > 0)
            {
                var grp = GroupBySeries(ranked);
                hb.Append("\n<color=#99AAEE>Ranked History</color>  <color=#888>(recent series)</color>\n");
                int shown = 0;
                foreach (var g in grp)
                {
                    if (shown >= 12) break;
                    if (g.matches == null || g.matches.Count == 0) continue;
                    var first = g.matches[0];
                    string score = first.series_score ?? "?-?";
                    bool complete = false, won = false;
                    try { var p = score.Split('-'); int mw = int.Parse(p[0]), tw = int.Parse(p[1]); complete = mw >= 2 || tw >= 2; won = mw > tw; } catch {}
                    string oppName = Trunc(first.opponent_name ?? "?", 14);
                    string dt = ""; try { if (!string.IsNullOrEmpty(first.ended_at) && first.ended_at.Length >= 10) dt = DateTime.Parse(first.ended_at).ToString("M/d"); } catch {}
                    string res = complete ? (won ? "<color=#00FF00>W</color>" : "<color=#FF6666>L</color>") : "<color=#FFD94D>-</color>";
                    string elo = (complete && first.series_rating_change != 0f)
                        ? $" <color={(first.series_rating_change > 0 ? "#00FF00" : "#FF6666")}>{(first.series_rating_change > 0 ? "+" : "")}{first.series_rating_change:F0}</color>"
                        : "";
                    hb.Append($"  {res} {score} vs {oppName}{elo}  <color=#888>{dt}</color>\n");
                    shown++;
                }
            }
            else
            {
                hb.Append("\n<color=#99AAEE>Ranked History:</color> <color=#888><i>no ranked series yet</i></color>\n");
            }

            historyPart = hb.ToString();
            return sb.ToString();
        }

        private static void RefreshCardStats(){string[]hL={"Tier","Card","Rarity","Picks","Wins","WR%","Pass%"};string[]hK={"tier","card_name","card_rarity","times_picked","wins_with_card","win_rate","pass_rate"};if(cardSortTexts!=null)for(int i=0;i<7&&i<cardSortTexts.Length;i++){if(cardSortTexts[i]==null)continue;string arrow=cardSort==hK[i]?(cardSortDesc?" v":" ^"):"";UIFactory.SetText(cardSortTexts[i],hL[i]+arrow);UIFactory.SetColor(cardSortTexts[i],cardSort==hK[i]?C_WHITE:C_LABEL);if(cardSortBtns!=null&&i<cardSortBtns.Length)UIFactory.SetImageColor(cardSortBtns[i],cardSort==hK[i]?C_TABACT:C_TAB);}var cards=ApiClient.CachedCardStats;foreach(var r in cardRows)r.root.SetActive(false);
        // Self-heal (#32): refetch when the open-time fetch never landed —
        // stats null, or the tier set for the current filter never completed.
        if(cards==null&&Time.realtimeSinceStartup-_cardStatsAutoFetchAt>8f){_cardStatsAutoFetchAt=Time.realtimeSinceStartup;ApiClient.FetchCardStats(200,MatchTracker.LocalSteamId);}
        if(!_tierFiltersLoaded.Contains(cardFilter)&&Time.realtimeSinceStartup-_tierAutoFetchAt>8f){_tierAutoFetchAt=Time.realtimeSinceStartup;LoadCardTiersForCurrentFilter();}
        if(cards==null||cards.Count==0)return;var merged=new List<ApiClient.CardStatData>();var seen=new Dictionary<string,int>(StringComparer.OrdinalIgnoreCase);foreach(var c in cards){string key=(c.card_name??"?").ToLower().Replace(" ","");if(seen.ContainsKey(key)){var e=merged[seen[key]];e.times_picked+=c.times_picked;e.wins_with_card+=c.wins_with_card;e.win_rate=e.times_picked>0?(float)e.wins_with_card/e.times_picked:0;e.times_offered=Math.Max(e.times_offered,c.times_offered);if(c.times_offered>0)e.pass_rate=c.pass_rate;if((e.card_rarity==null||e.card_rarity=="Unknown")&&c.card_rarity!=null&&c.card_rarity!="Unknown")e.card_rarity=c.card_rarity;}else{seen[key]=merged.Count;merged.Add(new ApiClient.CardStatData{card_name=c.card_name,card_rarity=c.card_rarity,times_picked=c.times_picked,wins_with_card=c.wins_with_card,win_rate=c.win_rate,times_offered=c.times_offered,pass_rate=c.pass_rate});}}
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
        // Highest server chat id we've rendered. Server messages carry their DB
        // row id (v1.28.3); the scrollback refetch that ChatClient fires on
        // EVERY reconnect used to re-append all 50 recent entries to the log —
        // each WS blip re-printed old chat (one of #30's "duplicated" reports).
        // Local echoes carry no id and always render.
        private static int _lastChatIdSeen = 0;

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
                int chatId = ExtractChatIntField(json, "id");
                if (chatId > 0)
                {
                    if (chatId <= _lastChatIdSeen) return;  // already rendered (reconnect replay)
                    _lastChatIdSeen = chatId;
                }
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

        private static void RefreshQueueUI(){if(txtRankedStatus==null)return;bool ranked=Plugin.RankedEnabled.Value;var qs=ApiClient.CurrentQueueState;UIFactory.SetText(txtRankedStatus,ranked?"RANKED: ON":"RANKED: OFF");UIFactory.SetColor(txtRankedStatus,ranked?C_GREEN:Color.gray);rankOnBtn.SetActive(!ranked);rankOffBtn.SetActive(ranked&&!inGameMode);bool inRankedMatch=GameStateWatcher.IsInMatch&&GameStateWatcher.MatchIsRanked;
/* July 21 item 8: LFP button — visible while ranked and not mid-ranked-match.
 * Cooldown armed from the server-side lfp_seconds_left whenever a FRESH stats
 * object arrives (reference compare — stats are re-fetched on refresh). */
try{
    var _lst=ApiClient.CachedPlayerStats;
    if(_lst!=null&&!ReferenceEquals(_lst,_lfpStatsRef)){_lfpStatsRef=_lst;LfpArmCooldown(_lst.lfp_seconds_left);}
    if(lfpBtn!=null){
        lfpBtn.SetActive(ranked&&!inRankedMatch);
        float _rem=lfpCooldownUntil-Time.realtimeSinceStartup;
        var _lbt=UIFactory.GetButtonText(lfpBtn);
        if(_lbt!=null)UIFactory.SetText(_lbt,_rem>0f?$"RLFP ({(int)(_rem/60)+1}m)":"RLFP Ping");
    }
}catch{}
qSearchBtn.SetActive(ranked&&qs==ApiClient.QueueState.Idle&&!inRankedMatch);qCancelBtn.SetActive(ranked&&qs==ApiClient.QueueState.Searching);if(qs==ApiClient.QueueState.Searching){var poll=ApiClient.LastPollData;string line="Searching...";if(poll!=null&&poll.status=="searching"){int m=poll.wait_time/60,sec=poll.wait_time%60;line=$"Searching... {(m>0?$"{m}m ":"")}{sec}s  +/-{poll.elo_range}"+(poll.queue_size>1?$"  ({poll.queue_size} in queue)":"");}line+=OnlineSuffix();UIFactory.SetText(txtQueueInfo,line);UIFactory.SetColor(txtQueueInfo,C_BLUE);((txtQueueInfo as Component)?.gameObject)?.SetActive(true);}else if(qs==ApiClient.QueueState.Idle&&ranked){int qc=ApiClient.CachedQueueSearching;if(qc>0){UIFactory.SetText(txtQueueInfo,$"{qc} searching"+OnlineSuffix());UIFactory.SetColor(txtQueueInfo,C_GREEN);}else{UIFactory.SetText(txtQueueInfo,"0 in queue"+OnlineSuffix());UIFactory.SetColor(txtQueueInfo,C_DIM);}((txtQueueInfo as Component)?.gameObject)?.SetActive(true);}else{UIFactory.SetText(txtQueueInfo,"");((txtQueueInfo as Component)?.gameObject)?.SetActive(false);}if(qs==ApiClient.QueueState.Matched||qs==ApiClient.QueueState.ReadySent){qMatchPanel.SetActive(true);var poll=ApiClient.LastPollData;if(poll!=null){string oppInfo=$"MATCH FOUND!  vs {poll.opponent_name} ({poll.opponent_rating:F0})";if(qs==ApiClient.QueueState.ReadySent&&poll.opponent_ready)oppInfo+="  [Opponent Ready]";UIFactory.SetText(txtMatchFound,oppInfo);}bool readySent=qs==ApiClient.QueueState.ReadySent;readyBtn.SetActive(!readySent);connectLabel.SetActive(readySent);if(readySent&&txtConnectLabel!=null&&poll!=null){string waitTxt=!string.IsNullOrEmpty(poll.opponent_name)?$"Waiting for {poll.opponent_name} ({poll.opponent_rating:F0})...":"Waiting for opponent...";if(poll.opponent_ready)waitTxt=$"{poll.opponent_name} ready! Joining...";UIFactory.SetText(txtConnectLabel,waitTxt);}declineBtn.SetActive(true);}else qMatchPanel.SetActive(false);}

        // "N online" suffix for the queue-status line (v1.29). Rich-text grey so it
        // reads as secondary info next to the queue count. Empty until the first
        // presence response lands (0 would be a lie — we ourselves are online).
        private static string OnlineSuffix(){int on=ApiClient.CachedOnlineCount;return on>0?$"  <color=#7FDBFF>|</color>  <color=#AAAAAA>{on} online</color>":"";}

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
        private static GameObject adminSeriesContainer;
        private static object txtAdminSeriesHdr;
        private static List<GameObject> adminSeriesRowPool = new List<GameObject>();

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
                if (!string.IsNullOrEmpty(sid)) { ApiClient.FetchFlaggedMatches(sid); ApiClient.FetchBannedUsers(sid); ApiClient.FetchAdminRecentSeries(sid); }
            }, sizeDelta: new Vector2(90, 26));

            var actionRow = new GameObject("AAct"); actionRow.transform.SetParent(panel.transform, false); actionRow.AddComponent<RectTransform>();
            UIFactory.AddHLG(actionRow, spacing: 8); UIFactory.AddLE(actionRow, prefH: 30, flexH: 0);
            UIFactory.CreateButton("ABan", actionRow.transform, "Ban Steam ID...", 13f, C_WHITE, new Color(0.55f, 0.15f, 0.15f, 0.9f), () =>
                CompetitiveUI.OpenAdminPrompt("ban"), sizeDelta: new Vector2(140, 26));
            UIFactory.CreateButton("AGrant", actionRow.transform, "Grant Achievement...", 13f, C_WHITE, new Color(0.2f, 0.45f, 0.2f, 0.9f), () =>
                CompetitiveUI.OpenAdminPrompt("grant"), sizeDelta: new Vector2(170, 26));
            UIFactory.CreateButton("ARev", actionRow.transform, "Reverse Series...", 13f, C_WHITE, new Color(0.45f, 0.3f, 0.55f, 0.9f), () =>
                CompetitiveUI.OpenAdminPrompt("reverse"), sizeDelta: new Vector2(150, 26));
            UIFactory.CreateButton("ABugRpt", actionRow.transform, "Bug Reports...", 13f, C_WHITE, new Color(0.2f, 0.3f, 0.5f, 0.9f), () =>
                CompetitiveUI.OpenBugReportAdminViewer(), sizeDelta: new Vector2(150, 26));
            var artistActionRow = new GameObject("AArtistAct");
            artistActionRow.transform.SetParent(panel.transform, false);
            artistActionRow.AddComponent<RectTransform>();
            UIFactory.AddHLG(artistActionRow, spacing: 8);
            UIFactory.AddLE(artistActionRow, prefH: 30, flexH: 0);
            // Item 1 (v1.30): artist-role management. Assigning ITEMS to an
            // artist lives on the shop rows (admin-only "Artist" button there).
            UIFactory.CreateButton("AArtG", artistActionRow.transform, "Grant Artist...", 13f, C_WHITE, new Color(0.3f, 0.45f, 0.35f, 0.9f), () =>
                // Grant targets someone who ISN'T an artist yet, so the roster
                // can't offer them — use the name search (elo disambiguates).
                CompetitiveUI.OpenPlayerSearch("Grant the artist role - find the player",
                    (sid, pname) => { if (!string.IsNullOrEmpty(sid)) ApiClient.AdminSetArtist(MatchTracker.LocalSteamId, sid, true,
                        (ok, resp) => ShowArtistResult(ok, ok ? $"Artist role granted to {pname}." : resp)); }),
                sizeDelta: new Vector2(130, 26));
            UIFactory.CreateButton("AArtR", artistActionRow.transform, "Revoke Artist...", 13f, C_WHITE, new Color(0.45f, 0.3f, 0.3f, 0.9f), () =>
                // Bug batch item 5: revoking should list the CURRENT artists, not
                // ask for a raw Steam64.
                ApiClient.FetchArtistsList(ok =>
                {
                    var roster = ApiClient.CachedAllArtists;
                    if (roster == null || roster.Count == 0)
                    {
                        ShowArtistResult(false, "{\"detail\":\"no artists defined\"}");
                        return;
                    }
                    var names = new string[roster.Count];
                    var ids = new string[roster.Count];
                    for (int ai = 0; ai < roster.Count; ai++)
                    { names[ai] = roster[ai].display_name; ids[ai] = roster[ai].steam_id; }
                    CompetitiveUI.OpenArtistPicker("Revoke which artist?", names, ids,
                        picked => { if (!string.IsNullOrEmpty(picked)) ApiClient.AdminSetArtist(MatchTracker.LocalSteamId, picked, false,
                            (ok2, resp) => ShowArtistResult(ok2, ok2 ? "Artist revoked." : resp)); },
                        actionLabel: "Revoke", showClear: false);
                }),
                sizeDelta: new Vector2(135, 26));
            // Round 3 item 2: review queue for artist-submitted cosmetics.
            UIFactory.CreateButton("ACosR", artistActionRow.transform, "Cosmetic Reviews...", 13f, C_WHITE, new Color(0.3f, 0.4f, 0.55f, 0.9f), () =>
                CompetitiveUI.OpenCosmeticReview(), sizeDelta: new Vector2(150, 26));
            UIFactory.CreateButton("ACosQ", artistActionRow.transform, "Approved Update Queue...", 13f, C_WHITE, new Color(0.35f, 0.3f, 0.6f, 0.95f), () =>
                CompetitiveUI.OpenCosmeticReleaseQueue(), sizeDelta: new Vector2(190, 26));

            // Recent Ranked Series — the main series-management section (Award/Void/Reverse).
            var seriesHdrRow = new GameObject("ASHRow"); seriesHdrRow.transform.SetParent(panel.transform, false); seriesHdrRow.AddComponent<RectTransform>();
            UIFactory.AddHLG(seriesHdrRow, spacing: 8); UIFactory.AddLE(seriesHdrRow, prefH: 24, flexH: 0);
            txtAdminSeriesHdr = UIFactory.CreateText("ASH", seriesHdrRow.transform, "Recent Ranked Series", 16f, new Color(0.6f, 0.85f, 1f), UIFactory.AlignMidLeft, sizeDelta: new Vector2(700, 22));
            UIFactory.SetBold(txtAdminSeriesHdr, true);
            var seriesSV = UIFactory.CreateScrollView("ASSV", panel.transform, spacing: 3);
            // Responsive 1:2 split: enough series space to operate at 1024x576,
            // while Flagged Matches receives the larger share at every height.
            UIFactory.AddLE(seriesSV.scrollGO, minH: 80, flexH: 1);
            adminSeriesContainer = seriesSV.content;

            var split = new GameObject("ASplit"); split.transform.SetParent(panel.transform, false); split.AddComponent<RectTransform>();
            UIFactory.AddHLG(split, spacing: 8); UIFactory.AddLE(split, minH: 140, flexH: 2);

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
            UIFactory.SetText(txtAdminFlagsHdr, $"Flagged Matches ({flags.Count} actionable)");
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

            // Recent series rows (Award/Void/Reverse)
            var series = ApiClient.CachedAdminSeries ?? new List<ApiClient.AdminSeriesEntry>();
            int needResolve = 0;
            foreach (var s in series) if (s.incomplete && s.ladder == "2v2") needResolve++;
            UIFactory.SetText(txtAdminSeriesHdr, needResolve > 0
                ? $"Recent Ranked Series  <color=#FFCC44>({needResolve} 2v2 need resolving)</color>"
                : "Recent Ranked Series");
            for (int i = series.Count; i < adminSeriesRowPool.Count; i++) adminSeriesRowPool[i].SetActive(false);
            for (int i = 0; i < series.Count; i++)
            {
                if (i >= adminSeriesRowPool.Count) adminSeriesRowPool.Add(BuildAdminSeriesRow(adminSeriesContainer.transform, i));
                FillAdminSeriesRow(adminSeriesRowPool[i], series[i]);
            }
        }

        private static GameObject BuildAdminFlagRow(Transform parent, int idx)
        {
            var row = UIFactory.CreatePanel($"AF{idx}", parent, new Color(0.18f, 0.13f, 0.13f, 0.85f));
            UIFactory.AddHLG(row, spacing: 6, padL: 6, padR: 6, padT: 4, padB: 4);
            UIFactory.AddLE(row, prefH: 38, flexH: 0);
            var txt = UIFactory.CreateText("AFT", row.transform, "", 13f, C_WHITE, UIFactory.AlignMidLeft, sizeDelta: new Vector2(420, 30));
            UIFactory.SetWordWrap(txt, false);
            // The flag line grew (steam ids + suspect + score), and an unwrapped
            // TMP overflows its rect and draws OVER the Details button that
            // follows it in this HLG. Take the row's spare width and ellipsize
            // instead of overflowing — full text lives in the Details viewer.
            {
                var txtComp = txt as Component;
                if (txtComp != null && UIFactory.tLE != null)
                {
                    var le = txtComp.gameObject.GetComponent(UIFactory.tLE)
                             ?? txtComp.gameObject.AddComponent(UIFactory.tLE);
                    UIFactory.tLE.GetProperty("flexibleWidth", BindingFlags.Public | BindingFlags.Instance)?.SetValue(le, 1f);
                    UIFactory.tLE.GetProperty("minWidth", BindingFlags.Public | BindingFlags.Instance)?.SetValue(le, 240f);
                }
                UIFactory.SetOverflowMode(txt, 1);   // TMP TextOverflowModes.Ellipsis
            }
            // Decisions live in the evidence viewer so admins see the telemetry
            // before choosing Cheat or False positive.
            UIFactory.CreateButton($"AFDT{idx}", row.transform, "Details", 11f, C_WHITE,
                new Color(0.25f, 0.38f, 0.55f, 0.95f), () => { },
                sizeDelta: new Vector2(76, 26));
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
                string verdict = e.restoration_required
                    ? "<color=#FFCC44>FALSE+ / MANUAL REPAIR</color>"
                    : e.auto_invalidated
                        ? "<color=#FF6666>auto-inv</color>"
                        : "<color=#DDAA44>advisory</color>";
                string mode = e.is_ranked ? "R" : "C";
                string duration = string.IsNullOrEmpty(e.duration_text)
                    ? (e.duration_seconds > 0 ? e.duration_seconds + "s" : "not recorded")
                    : e.duration_text;
                string line = $"[{when}] <b>{e.flag_reason}</b> {verdict}  "
                            + $"{Trunc(HomeSan(e.p1_name), 12)} vs {Trunc(HomeSan(e.p2_name), 12)}  "
                            + $"{mode}/{duration}  <color=#889>{e.game_code}</color>";
                // tTMP isn't accessible outside UIFactory. Iterate child components by reflected name.
                foreach (var c in txt.GetComponents<Component>())
                    if (c.GetType().Name == "TextMeshProUGUI") { UIFactory.SetText(c, line); break; }
            }
            var details = row.transform.Find("AFDT" + row.name.Substring(2));
            if (details != null) WireButton(details.gameObject, () => CompetitiveUI.OpenFlagEvidence(e));
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

        // -- Admin recent-series rows -------------------------------------
        private static GameObject BuildAdminSeriesRow(Transform parent, int idx)
        {
            var row = UIFactory.CreatePanel($"AS{idx}", parent, new Color(0.13f, 0.15f, 0.19f, 0.9f));
            UIFactory.AddVLG(row, spacing: 2, padL: 6, padR: 6, padT: 4, padB: 4);
            UIFactory.AddLE(row, prefH: 52, flexH: 0);

            var top = new GameObject("AStop"); top.transform.SetParent(row.transform, false); top.AddComponent<RectTransform>();
            UIFactory.AddHLG(top, spacing: 6); UIFactory.AddLE(top, prefH: 26, flexH: 0);
            var info = UIFactory.CreateText($"ASI{idx}", top.transform, "", 13f, C_WHITE, UIFactory.AlignMidLeft, sizeDelta: new Vector2(500, 24));
            UIFactory.SetWordWrap(info, false);
            var infoGO = top.transform.Find($"ASI{idx}")?.gameObject;
            if (infoGO != null) UIFactory.AddLE(infoGO, flexW: 1, flexH: 0);
            UIFactory.CreateButton($"ASB1{idx}", top.transform, "", 11f, C_WHITE, new Color(0.2f, 0.45f, 0.2f, 0.9f), () => { }, sizeDelta: new Vector2(78, 24));
            UIFactory.CreateButton($"ASB2{idx}", top.transform, "", 11f, C_WHITE, new Color(0.2f, 0.45f, 0.2f, 0.9f), () => { }, sizeDelta: new Vector2(78, 24));
            UIFactory.CreateButton($"ASB3{idx}", top.transform, "", 11f, C_WHITE, new Color(0.5f, 0.35f, 0.15f, 0.9f), () => { }, sizeDelta: new Vector2(78, 24));

            var cards = UIFactory.CreateText($"ASC{idx}", row.transform, "", 11f, new Color(0.6f, 0.6f, 0.62f), UIFactory.AlignMidLeft, sizeDelta: new Vector2(760, 18));
            UIFactory.SetWordWrap(cards, false);
            row.SetActive(false);
            return row;
        }

        private static string SeriesPairName(ApiClient.AdminSeriesEntry e, int team)
        {
            if (e.num_players == 4) return team == 1 ? $"{e.p1_name}+{e.p2_name}" : $"{e.p3_name}+{e.p4_name}";
            return team == 1 ? e.p1_name : e.p2_name;
        }

        // Bug #68: the server now encodes cards per GAME ('||' between games, '|'
        // between cards) instead of one series-wide mash. Render one line per game
        // so the admin can see who picked what in which game. Legacy payloads with
        // no '||' fall out of the same code path as a single game line.
        private static string BuildSeriesCards(ApiClient.AdminSeriesEntry e, out int lineCount)
        {
            string[] SplitGames(string cards) =>
                string.IsNullOrEmpty(cards) ? Array.Empty<string>() : cards.Split(new[] { "||" }, StringSplitOptions.None);
            var byPlayer = new List<(string name, string[] games)>
            { (e.p1_name, SplitGames(e.p1_cards)), (e.p2_name, SplitGames(e.p2_cards)) };
            if (e.num_players == 4)
            { byPlayer.Add((e.p3_name, SplitGames(e.p3_cards))); byPlayer.Add((e.p4_name, SplitGames(e.p4_cards))); }

            int games = 0;
            foreach (var p in byPlayer) games = Math.Max(games, p.games.Length);
            var lines = new List<string>();
            for (int g = 0; g < games; g++)
            {
                var parts = new List<string>();
                foreach (var (name, pg) in byPlayer)
                {
                    string cards = g < pg.Length ? pg[g] : "";
                    if (!string.IsNullOrEmpty(cards)) parts.Add($"{Trunc(name, 8)}: {cards.Replace("|", ", ")}");
                }
                if (parts.Count == 0) continue;
                string line = $"<color=#AAAACC>G{g + 1}</color>  {string.Join("    ", parts)}";
                if (line.Length > 170) line = line.Substring(0, 168) + "..";
                lines.Add(line);
            }
            lineCount = Math.Max(1, lines.Count);
            string s = lines.Count > 0 ? string.Join("\n", lines) : "(no cards recorded)";
            return $"<color=#888>{s}</color>";
        }

        private static void FillAdminSeriesRow(GameObject row, ApiClient.AdminSeriesEntry e)
        {
            row.SetActive(true);
            string sfx = row.name.Substring(2);

            string ladderCol = e.ladder == "2v2" ? "#88CCFF" : "#CFA0FF";
            string teamA = e.num_players == 4 ? $"{Trunc(e.p1_name, 10)}+{Trunc(e.p2_name, 10)}" : Trunc(e.p1_name, 14);
            string teamB = e.num_players == 4 ? $"{Trunc(e.p3_name, 10)}+{Trunc(e.p4_name, 10)}" : Trunc(e.p2_name, 14);
            if (e.winner_team == 1) teamA = $"<b>{teamA}</b>";
            else if (e.winner_team == 2) teamB = $"<b>{teamB}</b>";
            string dcStr = string.IsNullOrEmpty(e.dc_name) ? "" : $"  <color=#FF8888>DC:{Trunc(e.dc_name, 10)}</color>";
            string statusCol = e.incomplete ? "#FFCC44" : (e.status == "completed" ? "#88DD88" : "#AAAAAA");
            string line = $"<b>#{e.series_number}</b> <color={ladderCol}>{e.ladder}</color>  {teamA} <b>{e.score}</b> {teamB}{dcStr}  <color={statusCol}>{e.status}</color>";
            var infoT = row.transform.Find("AStop/ASI" + sfx);
            if (infoT != null) foreach (var c in infoT.GetComponents<Component>()) if (c.GetType().Name == "TextMeshProUGUI") { UIFactory.SetText(c, line); break; }

            var cardsT = row.transform.Find("ASC" + sfx);
            if (cardsT != null)
            {
                string cardsText = BuildSeriesCards(e, out int cardLines);
                foreach (var c in cardsT.GetComponents<Component>()) if (c.GetType().Name == "TextMeshProUGUI") { UIFactory.SetText(c, cardsText); break; }
                // Grow the row for multi-game card lines (one 16px line per game).
                UIFactory.SetPrefH(row, Math.Max(52, 34 + 16 * cardLines));
                var rt = cardsT.GetComponent<RectTransform>();
                if (rt != null) rt.sizeDelta = new Vector2(rt.sizeDelta.x, 16 * cardLines + 2);
            }

            var b1 = row.transform.Find("AStop/ASB1" + sfx)?.gameObject;
            var b2 = row.transform.Find("AStop/ASB2" + sfx)?.gameObject;
            var b3 = row.transform.Find("AStop/ASB3" + sfx)?.gameObject;
            void setBtn(GameObject b, bool show, string label, Color col, Action onClick)
            {
                if (b == null) return;
                b.SetActive(show);
                if (!show) return;
                UIFactory.SetText(UIFactory.GetButtonText(b), label);
                UIFactory.SetImageColor(b, col);
                WireButton(b, onClick);
            }

            if (e.ladder == "2v2" && e.incomplete)
            {
                setBtn(b1, true, "Win T1", new Color(0.2f, 0.45f, 0.2f, 0.9f), () => ConfirmResolveTeam(e, "complete", 1));
                setBtn(b2, true, "Win T2", new Color(0.2f, 0.45f, 0.2f, 0.9f), () => ConfirmResolveTeam(e, "complete", 2));
                setBtn(b3, true, "Void", new Color(0.5f, 0.35f, 0.15f, 0.9f), () => ConfirmResolveTeam(e, "void", 0));
            }
            else if (e.status == "completed")
            {
                setBtn(b1, true, "Reverse", new Color(0.55f, 0.2f, 0.5f, 0.9f), () => ConfirmReverseSeries(e));
                setBtn(b2, false, "", C_BTN, null);
                setBtn(b3, false, "", C_BTN, null);
            }
            else
            {
                setBtn(b1, false, "", C_BTN, null);
                setBtn(b2, false, "", C_BTN, null);
                setBtn(b3, false, "", C_BTN, null);
            }
        }

        private static void ConfirmResolveTeam(ApiClient.AdminSeriesEntry e, string action, int winner)
        {
            var sid = MatchTracker.LocalSteamId;
            if (string.IsNullOrEmpty(sid)) return;
            string what = action == "void"
                ? "VOID this series (no result, no rating/gold)"
                : $"award the win to Team {winner} ({SeriesPairName(e, winner)}) — applies Glicko + gold now";
            CompetitiveUI.OpenConfirm($"2v2 series #{e.series_number}\n\n{what}?", () =>
            {
                ApiClient.AdminResolveTeamSeries(sid, e.series_id, action, winner, (ok, resp) =>
                {
                    Plugin.Log.LogInfo($"[ADMIN] resolve {action} T{winner} on {e.series_id}: {(ok ? "OK" : "FAIL")} {resp}");
                    if (ok) ApiClient.FetchAdminRecentSeries(sid);
                });
            });
        }

        private static void ConfirmReverseSeries(ApiClient.AdminSeriesEntry e)
        {
            var sid = MatchTracker.LocalSteamId;
            if (string.IsNullOrEmpty(sid)) return;
            CompetitiveUI.OpenConfirm($"Reverse {e.ladder} series #{e.series_number}?\n\nUndoes the ratings + gold and cancels the series.", () =>
            {
                Action<bool, string> done = (ok, resp) =>
                {
                    Plugin.Log.LogInfo($"[ADMIN] reverse {e.series_id}: {(ok ? "OK" : "FAIL")} {resp}");
                    if (ok) ApiClient.FetchAdminRecentSeries(sid);
                };
                if (e.ladder == "2v2") ApiClient.AdminReverseTeamSeries(sid, e.series_id, "admin_reverse", done);
                else ApiClient.AdminReverseSeries(sid, e.series_id, "admin_reverse", done);
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
                        // Key the debounce on THIS button (learning #142): a
                        // parameterless Claim() shares one global key, so
                        // clicking Details on two different flagged rows inside
                        // 0.2s silently swallowed the second click.
                        UnityEngine.Events.UnityAction guarded = () => { if (ClickGuard.Claim(btn)) onClick(); };
                        add.Invoke(ev, new object[] { guarded });
                    }
                }
                // Also rewire the secondary ClickHandler attached by CreateButton.
                var ch = btn.GetComponent<ClickHandler>();
                if (ch != null) ch.onClick = () => { if (ClickGuard.Claim(btn)) onClick(); };
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
        // Item 3: mandatory time voting — slots are pickable BEFORE signup (the
        // vote rides the signup request); Save Votes only applies once signed up.
        private static GameObject tVoteSaveBtn;
        private static object txtTVoteHdr;
        // July 17 round 2: live prize block (scales with signups) + the
        // between-rounds Play Now button.
        private static object txtTPrizes;
        private static GameObject tPlayNowBtn;
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
        // Visual bracket host — sibling of the row-pool, positioned-content
        // canvas for rendering matches as a true bracket diagram. When the
        // visual bracket is shown, all row-pool rows are hidden and we
        // populate this host with absolutely-positioned match cells +
        // connector lines. When the bracket should be blanked (locked
        // sync, voting), the row-pool's first row holds the placeholder
        // text and the visual host is hidden.
        private static GameObject tBracketVisual;
        // "Upcoming Match Bets" section in the Tournament tab — surfaces
        // tournament series that exist server-side but haven't gone live
        // in-game yet. Rebuilds on each refresh from CachedActiveSeries.
        private static GameObject tTournBetsBox, tTournBetsContainer;
        private static object tTournBetsHeader;
        private static List<GameObject> tTournBetRowPool = new List<GameObject>();
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
            // v1.32 item 5: state/when/instructions bumped 2pt — the block read too small.
            txtTState = UIFactory.CreateText("TS", hdrBox.transform, "Loading...", 24f, C_GOLD, UIFactory.AlignMidLeft, sizeDelta: new Vector2(410, 32));
            UIFactory.SetBold(txtTState, true);
            txtTWhen = UIFactory.CreateText("TW", hdrBox.transform, "", 17f, C_SUB, UIFactory.AlignMidLeft, sizeDelta: new Vector2(410, 26));
            UIFactory.SetWordWrap(txtTWhen, true);
            // Item 2 (July 17 round 2): the when-line word-wraps to 2 lines in
            // the voting phase ("Default start ... Signups close ...") but the
            // baked LayoutElement only allotted its one-line 26px — the second
            // line painted straight over the instructions block (screenshot-
            // verified overlap). Same prefH-zeroing as txtTInstructions below.
            { var wle = (txtTWhen as Component)?.gameObject.GetComponent(UIFactory.tLE);
              if (wle != null) UIFactory.tLE.GetProperty("preferredHeight", BindingFlags.Public | BindingFlags.Instance)?.SetValue(wle, -1f); }
            txtTInstructions = UIFactory.CreateText("TI", hdrBox.transform,
                _SYNC_INSTRUCTIONS,
                14f, C_LABEL, UIFactory.AlignMidLeft, sizeDelta: new Vector2(410, 560));
            UIFactory.SetWordWrap(txtTInstructions, true);
            // Zero out the baked LayoutElement prefH so the TMP text's own ILayoutElement
            // (which reports actual rendered height) drives the parent panel size. Without
            // this, the hdrBox sizes to the baked 560 even if content fits in less - and,
            // more importantly, the panel stops clamping content that WOULD overflow.
            // Same pattern the chat log uses (see RefreshMyStats for the precedent).
            { var le = (txtTInstructions as Component)?.gameObject.GetComponent(UIFactory.tLE);
              if (le != null) UIFactory.tLE.GetProperty("preferredHeight", BindingFlags.Public | BindingFlags.Instance)?.SetValue(le, -1f); }
            // Item 2: prizes moved out of the static instructions into a live
            // block — amounts scale with the confirmed signup count, so the
            // text is rebuilt every refresh (RefreshTournaments).
            txtTPrizes = UIFactory.CreateText("TPrz", hdrBox.transform, "",
                14f, C_LABEL, UIFactory.AlignMidLeft, sizeDelta: new Vector2(410, 90));
            UIFactory.SetWordWrap(txtTPrizes, true);
            { var ple = (txtTPrizes as Component)?.gameObject.GetComponent(UIFactory.tLE);
              if (ple != null) UIFactory.tLE.GetProperty("preferredHeight", BindingFlags.Public | BindingFlags.Instance)?.SetValue(ple, -1f); }

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
                    if (t == null || string.IsNullOrEmpty(t.tournament_id) || string.IsNullOrEmpty(id) || id == "unknown") return;
                    // Item 3: sync signups must pick >= 1 start time — the vote
                    // rides the signup request (server enforces it too).
                    if (ApiClient.TournamentKind != "async")
                    {
                        var selected = new List<string>();
                        for (int i = 0; i < tSlotChecked.Count && i < (t.time_slot_options?.Length ?? 0); i++)
                            if (tSlotChecked[i]) selected.Add(t.time_slot_options[i]);
                        if (selected.Count == 0)
                        {
                            CompetitiveUI.ShowNotification("Pick at least one start time below first", new Color(1f, 0.75f, 0.35f));
                            return;
                        }
                        ApiClient.TournamentSignup(t.tournament_id, id, MatchTracker.LocalDisplayName, selected.ToArray());
                    }
                    else ApiClient.TournamentSignup(t.tournament_id, id, MatchTracker.LocalDisplayName);
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
            txtTVoteHdr = UIFactory.CreateText("TVH", voteBox.transform, "Pick Your Start Times (multi-select)", 16f, C_SUB, UIFactory.AlignMidLeft, sizeDelta: new Vector2(440, 22));
            tTimeVoteRow = new GameObject("TVR"); tTimeVoteRow.transform.SetParent(voteBox.transform, false);
            tTimeVoteRow.AddComponent<RectTransform>(); UIFactory.AddVLG(tTimeVoteRow, spacing: 2);
            // Item 2 (July 17 round 2): 8 slots in TWO columns of 4 — half the
            // vertical space of the old single-column list. Each slot is its
            // own cell GameObject (toggle + label) so the refresh code's
            // per-slot show/hide (transform.parent) can't hide a row-mate.
            for (int r = 0; r < 4; r++)
            {
                var row = new GameObject($"SlotRow{r}"); row.transform.SetParent(tTimeVoteRow.transform, false);
                row.AddComponent<RectTransform>(); UIFactory.AddHLG(row, spacing: 10, forceExpandH: true);
                UIFactory.AddLE(row, prefH: 24, flexH: 0);
                for (int c = 0; c < 2; c++)
                {
                    int idx = r * 2 + c;
                    var cell = new GameObject($"Slot{idx}"); cell.transform.SetParent(row.transform, false);
                    cell.AddComponent<RectTransform>(); UIFactory.AddHLG(cell, spacing: 5, forceExpandH: true);
                    UIFactory.AddLE(cell, prefW: 200, minW: 180, flexW: 0, flexH: 0);
                    var box = UIFactory.CreateButton($"Tog{idx}", cell.transform, "[ ]", 14f, C_WHITE, C_BTN, () =>
                    {
                        if (tSlotChecked.Count > idx) {
                            tSlotChecked[idx] = !tSlotChecked[idx];
                            _tVoteLocalEdited = true;   // freeze server-sync until Save is pressed
                            dirty = true;
                        }
                    }, sizeDelta: new Vector2(36, 22));
                    tSlotToggles.Add(box);
                    var lbl = UIFactory.CreateText($"Lbl{idx}", cell.transform, "", 13f, C_LABEL, UIFactory.AlignMidLeft, sizeDelta: new Vector2(158, 22));
                    tSlotLabels.Add(lbl);
                    tSlotChecked.Add(false);
                }
            }
            var submitRow = new GameObject("TVSub"); submitRow.transform.SetParent(voteBox.transform, false);
            submitRow.AddComponent<RectTransform>(); UIFactory.AddHLG(submitRow, spacing: 6);
            UIFactory.AddLE(submitRow, prefH: 28, flexH: 0);
            tVoteSaveBtn = UIFactory.CreateButton("TVSubmit", submitRow.transform, "Save Votes", 15f, C_WHITE, new Color(0.22f, 0.38f, 0.65f, 0.95f), () =>
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
            // Item 2 (July 17 round 2): skip the between-rounds break — the
            // match starts the moment BOTH players press this.
            tPlayNowBtn = UIFactory.CreateButton("TPlayNow", matchBtnRow.transform, "Play Now (skip break)", 15f, C_WHITE, new Color(0.55f, 0.40f, 0.15f, 0.95f), () =>
            {
                var t = ApiClient.CachedTournament;
                if (t == null || string.IsNullOrEmpty(t.tournament_id) || t.matches == null) return;
                foreach (var m in t.matches)
                {
                    if (m.status == "scheduled" &&
                        (m.p1_signup_id == t.my_signup_id || m.p2_signup_id == t.my_signup_id) &&
                        !string.IsNullOrEmpty(m.match_id))
                    {
                        ApiClient.TournamentPlayNow(t.tournament_id, m.match_id, MatchTracker.LocalSteamId);
                        break;
                    }
                }
            }, sizeDelta: new Vector2(190, 26));
            tPlayNowBtn.SetActive(false);
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
                        // Prefer server-issued room name; fall back to the
                        // legacy client-derived format only when the server
                        // hasn't populated it yet (older matches pre-072
                        // migration). Both formats are identical for matches
                        // activated post-migration.
                        string roomName = !string.IsNullOrEmpty(m.photon_room_name)
                            ? m.photon_room_name
                            : "sct-" + m.match_id.Replace("-", "").Substring(0, 12);
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

            // Pre-match tournament bets — bracket pairings that have a
            // ranked_series row but no in-game activity yet. RefreshLiveSeries
            // hides these from the Live Ranked Games panel until they go live;
            // betting still happens here so people can wager pre-game.
            tTournBetsBox = UIFactory.CreatePanel("TBetsBox", right.transform, C_PANEL);
            UIFactory.AddVLG(tTournBetsBox, spacing: 2, padL: 8, padR: 8, padT: 6, padB: 6);
            UIFactory.AddLE(tTournBetsBox, flexH: 0);
            tTournBetsHeader = UIFactory.CreateText("TBH_Bets", tTournBetsBox.transform,
                "<color=#FFD94D>Upcoming Match Bets</color>",
                17f, C_WHITE, UIFactory.AlignMidLeft, sizeDelta: new Vector2(360, 24));
            tTournBetsContainer = new GameObject("TBetsRows");
            tTournBetsContainer.transform.SetParent(tTournBetsBox.transform, false);
            tTournBetsContainer.AddComponent<RectTransform>();
            UIFactory.AddVLG(tTournBetsContainer, spacing: 2);
            tTournBetsBox.SetActive(false); // hidden until there's a pre-match tournament series

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

            // Visual bracket canvas — sibling of the row-pool inside the
            // bracket ScrollView's content. Manual positional layout (no
            // VLG); each match is anchored at a computed (x, y) within
            // this host so connector lines line up cleanly. Initial size
            // is a placeholder — RenderVisualBracket recomputes per render
            // based on tournament size.
            tBracketVisual = new GameObject("TBV");
            tBracketVisual.transform.SetParent(tBracketList.transform, false);
            var tbvRT = tBracketVisual.AddComponent<RectTransform>();
            tbvRT.anchorMin = new Vector2(0f, 1f);
            tbvRT.anchorMax = new Vector2(0f, 1f);
            tbvRT.pivot = new Vector2(0f, 1f);
            tbvRT.sizeDelta = new Vector2(900, 600);
            UIFactory.AddLE(tBracketVisual, prefH: 600, minH: 600, prefW: 900, minW: 900, flexH: 0, flexW: 0);
            tBracketVisual.SetActive(false);

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
        private static string _FmtSlot(string iso, bool includeTz = true)
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
                // includeTz=false for the two-column slot cells (item 2): the
                // tz is already named in the "Times in:" row directly above,
                // and the 158px cell can't fit "Sat 07/18 12:00 PM Local (5)".
                return includeTz ? formatted + "  " + _TzLabel() : formatted;
            }
            catch { return iso; }
        }

        // ── Visual bracket renderer ─────────────────────────────────────
        // Positional layout: each match is a 170×48 cell anchored at a
        // computed (x, y) inside tBracketVisual. Connector lines join
        // each match to its prereq matches (an L-shape: short horizontal
        // out of the prereq → vertical to align with target → short
        // horizontal into target). WB rounds in the top half, LB in the
        // bottom, GF/GF_RESET on the right. Cell colors mirror the
        // legacy text view (cyan=completed, yellow=ready, green=active,
        // gray=bye/pending). Replaces the collapsing list when bracket
        // data is available.
        private static void RenderVisualBracket(ApiClient.TournamentSnapshot t, bool blankNames, int blankSize, bool isAsync)
        {
            if (tBracketVisual == null) return;
            // Tear down previous render. We rebuild fully each refresh —
            // simpler than diffing individual cells, and the bracket data
            // changes seldom enough that the rebuild cost is negligible.
            for (int i = tBracketVisual.transform.childCount - 1; i >= 0; i--)
                UnityEngine.Object.Destroy(tBracketVisual.transform.GetChild(i).gameObject);

            const int CELL_W = 170, CELL_H = 48;
            const int COL_GAP = 24;
            const int ROW_GAP = 56;
            const int PAD = 12;
            const int WB_LB_GAP = 30; // vertical gap between WB section and LB section

            // Resolve matches list (real or synthesized for blank shape).
            ApiClient.TournamentMatchRow[] matches = t.matches;
            if (matches == null || matches.Length == 0)
            {
                if (blankSize >= 4) matches = SynthesizeBlankBracket(blankSize);
                else { return; }
            }

            // Group by (side, round) and find max round per side.
            var bySide = new Dictionary<string, Dictionary<int, List<ApiClient.TournamentMatchRow>>>();
            int wbMaxRound = 0, lbMaxRound = 0;
            foreach (var m in matches)
            {
                if (!bySide.TryGetValue(m.bracket_side, out var rounds))
                { rounds = new Dictionary<int, List<ApiClient.TournamentMatchRow>>(); bySide[m.bracket_side] = rounds; }
                if (!rounds.TryGetValue(m.round, out var lst)) { lst = new List<ApiClient.TournamentMatchRow>(); rounds[m.round] = lst; }
                lst.Add(m);
                if (m.bracket_side == "W" && m.round > wbMaxRound) wbMaxRound = m.round;
                if (m.bracket_side == "L" && m.round > lbMaxRound) lbMaxRound = m.round;
            }

            // Compute height of WB section: WB R1's slot count drives it.
            int wbR1Count = (bySide.TryGetValue("W", out var wbRounds) && wbRounds.TryGetValue(1, out var wbR1)) ? wbR1.Count : 0;
            int lbR1Count = (bySide.TryGetValue("L", out var lbRounds) && lbRounds.TryGetValue(1, out var lbR1)) ? lbR1.Count : 0;
            int wbHeight = Math.Max(wbR1Count * ROW_GAP, ROW_GAP);
            int lbHeight = Math.Max(lbR1Count * ROW_GAP, ROW_GAP);

            // Compute (x, y) for each match. Positions are anchored from
            // top-left of tBracketVisual (anchorMin/Max already set in
            // BuildTournamentTab) → +x is right, +y is down.
            var pos = new Dictionary<string, Vector2>();
            int maxX = 0, maxY = 0;

            // WB cells: classic centering (each subsequent round's match
            // sits between its two prereqs from the previous round).
            if (wbRounds != null)
            {
                foreach (var kv in wbRounds)
                {
                    int r = kv.Key;
                    foreach (var m in kv.Value)
                    {
                        int s = m.slot_idx;
                        int x = PAD + (r - 1) * (CELL_W + COL_GAP);
                        // Spread doubles per round so descendants land between their prereqs.
                        float pitch = ROW_GAP * (1 << (r - 1));
                        float y = PAD + s * pitch + (pitch - ROW_GAP) / 2f;
                        pos[m.match_id] = new Vector2(x, y);
                        if (x + CELL_W > maxX) maxX = x + CELL_W;
                        if (y + CELL_H > maxY) maxY = (int)(y + CELL_H);
                    }
                }
            }

            // LB cells: positioned in the bottom half. LB rounds zig-zag
            // (minor / major) but the slot_idx ordering is monotonic, so
            // we lay them out as a simple stack within each round, scaled
            // similarly to WB.
            int lbStartY = PAD + wbHeight + WB_LB_GAP;
            if (lbRounds != null)
            {
                foreach (var kv in lbRounds)
                {
                    int r = kv.Key;
                    foreach (var m in kv.Value)
                    {
                        int s = m.slot_idx;
                        int x = PAD + (r - 1) * (CELL_W + COL_GAP);
                        // LB R1 + R2 share LB R1's row count, then halves
                        // every two rounds. Approximate via ceiling of
                        // (lbR1Count / 2^((r-1)/2)) to match standard
                        // double-elim shape.
                        int divPower = (r - 1) / 2;
                        float pitch = ROW_GAP * (1 << divPower);
                        // Major (even) rounds offset by half a pitch from the minor.
                        float yOff = (r % 2 == 0) ? pitch / 2f : 0f;
                        float y = lbStartY + s * pitch + yOff;
                        pos[m.match_id] = new Vector2(x, y);
                        if (x + CELL_W > maxX) maxX = x + CELL_W;
                        if (y + CELL_H > maxY) maxY = (int)(y + CELL_H);
                    }
                }
            }

            // GF + GF_RESET column — far right, vertically centered between WB and LB sections.
            int gfX = PAD + Math.Max(wbMaxRound, lbMaxRound) * (CELL_W + COL_GAP);
            float gfY = PAD + (wbHeight + WB_LB_GAP) / 2f - CELL_H / 2f;
            int gfStack = 0;
            foreach (var sideKey in new[] { "GF", "GF_RESET", "TP" })
            {
                if (!bySide.TryGetValue(sideKey, out var sideRounds)) continue;
                foreach (var kv in sideRounds)
                {
                    foreach (var m in kv.Value)
                    {
                        int x = gfX;
                        float y = gfY + gfStack * (CELL_H + 14);
                        pos[m.match_id] = new Vector2(x, y);
                        if (x + CELL_W > maxX) maxX = x + CELL_W;
                        if (y + CELL_H > maxY) maxY = (int)(y + CELL_H);
                        gfStack++;
                    }
                }
            }

            // Resize the host canvas to fit content + padding.
            int hostW = maxX + PAD;
            int hostH = maxY + PAD;
            var rt = tBracketVisual.GetComponent<RectTransform>();
            rt.sizeDelta = new Vector2(hostW, hostH);
            UIFactory.AddLE(tBracketVisual, prefH: hostH, minH: hostH, prefW: hostW, minW: hostW, flexH: 0, flexW: 0);

            // Connector lines first (so cells render on top). For each
            // non-bye match with prereq_match_ids populated, draw an
            // L-shape from each prereq's right-center to the match's
            // left-center.
            foreach (var m in matches)
            {
                if (m.prereq_match_ids == null) continue;
                if (!pos.TryGetValue(m.match_id, out var to)) continue;
                Vector2 toAnchor = new Vector2(to.x, to.y + CELL_H / 2f); // left-center of target cell
                foreach (var pid in m.prereq_match_ids)
                {
                    if (string.IsNullOrEmpty(pid)) continue;
                    if (!pos.TryGetValue(pid, out var from)) continue;
                    Vector2 fromAnchor = new Vector2(from.x + CELL_W, from.y + CELL_H / 2f); // right-center of source
                    DrawBracketConnector(tBracketVisual, fromAnchor, toAnchor);
                }
            }

            // Cells.
            foreach (var m in matches)
            {
                if (!pos.TryGetValue(m.match_id, out var p)) continue;
                CreateBracketCell(tBracketVisual, m, p, blankNames, isAsync);
            }
        }

        /// <summary>L-shaped connector: short horizontal segment out of
        /// the source, vertical to align with target Y, short horizontal
        /// into the target. Drawn as 2px-thick Image rectangles.</summary>
        private static void DrawBracketConnector(GameObject host, Vector2 fromTopLeftPx, Vector2 toTopLeftPx)
        {
            // Coords are top-left-anchored; +y is DOWN. Convert into
            // anchoredPosition (which uses top-left pivot so y becomes
            // negative-of-top).
            float midX = (fromTopLeftPx.x + toTopLeftPx.x) / 2f;
            float thickness = 2f;
            Color lineColor = new Color(1f, 0.85f, 0.3f, 0.55f);
            // Horizontal seg 1: from source.x to midX at source.y
            DrawLineSegment(host, fromTopLeftPx.x, fromTopLeftPx.y, midX - fromTopLeftPx.x, thickness, lineColor);
            // Vertical seg: from min(source.y, target.y) to max at midX
            float vY = Math.Min(fromTopLeftPx.y, toTopLeftPx.y);
            float vH = Math.Abs(toTopLeftPx.y - fromTopLeftPx.y) + thickness;
            DrawLineSegment(host, midX - thickness / 2f, vY, thickness, vH, lineColor);
            // Horizontal seg 2: from midX to target.x at target.y
            DrawLineSegment(host, midX, toTopLeftPx.y, toTopLeftPx.x - midX, thickness, lineColor);
        }

        private static void DrawLineSegment(GameObject host, float x, float y, float w, float h, Color c)
        {
            var seg = new GameObject("Conn");
            seg.transform.SetParent(host.transform, false);
            var srt = seg.AddComponent<RectTransform>();
            srt.anchorMin = new Vector2(0f, 1f);
            srt.anchorMax = new Vector2(0f, 1f);
            srt.pivot = new Vector2(0f, 1f);
            srt.anchoredPosition = new Vector2(x, -y);
            srt.sizeDelta = new Vector2(Math.Max(1f, w), Math.Max(1f, h));
            var img = seg.AddComponent(UIFactory.tImage);
            UIFactory.tImage.GetProperty("color", BindingFlags.Public | BindingFlags.Instance)?.SetValue(img, c);
            UIFactory.tImage.GetProperty("raycastTarget", BindingFlags.Public | BindingFlags.Instance)?.SetValue(img, false);
        }

        private static void CreateBracketCell(GameObject host, ApiClient.TournamentMatchRow m, Vector2 topLeftPx, bool blankNames, bool isAsync)
        {
            const int CELL_W = 170, CELL_H = 48;

            // Pick background tint by match status.
            Color bg = m.is_bye ? new Color(0.18f, 0.20f, 0.24f, 0.80f)
                : m.status == "completed" ? new Color(0.18f, 0.32f, 0.45f, 0.85f)
                : m.status == "active" ? new Color(0.20f, 0.42f, 0.20f, 0.90f)
                : m.status == "ready" ? new Color(0.45f, 0.38f, 0.15f, 0.90f)
                : new Color(0.16f, 0.17f, 0.21f, 0.85f); // pending

            var cell = UIFactory.CreatePanel($"M_{m.match_id}", host.transform, bg);
            var crt = cell.GetComponent<RectTransform>();
            crt.anchorMin = new Vector2(0f, 1f);
            crt.anchorMax = new Vector2(0f, 1f);
            crt.pivot = new Vector2(0f, 1f);
            crt.anchoredPosition = new Vector2(topLeftPx.x, -topLeftPx.y);
            crt.sizeDelta = new Vector2(CELL_W, CELL_H);

            // Two text rows: p1 + p2 with the score on the right.
            string p1Name = blankNames ? "?" : (m.p1_display_name ?? (m.is_bye ? "BYE" : "TBD"));
            string p2Name = blankNames ? "?" : (m.p2_display_name ?? (m.is_bye ? "BYE" : "TBD"));
            string p1Score = "", p2Score = "";
            if (m.status == "completed")
            {
                p1Score = m.p1_series_wins.ToString();
                p2Score = m.p2_series_wins.ToString();
            }
            else if (m.status == "forfeit" || m.status == "double_forfeit")
            {
                p1Score = m.status == "forfeit" ? "FF" : "FF";
                p2Score = m.status == "forfeit" ? "FF" : "FF";
            }

            // Highlight winner row in completed matches.
            int winner = 0;
            if (m.status == "completed") winner = m.p1_series_wins > m.p2_series_wins ? 1 : 2;

            float rowH = (CELL_H - 2) / 2f;
            CreateBracketCellRow(cell, p1Name, p1Score, 1, winner, 0, rowH, CELL_W);
            CreateBracketCellRow(cell, p2Name, p2Score, 2, winner, rowH + 1, rowH, CELL_W);

            // Tap-target: clicks on the cell currently no-op (could route
            // to a series detail view in a future pass).
        }

        private static void CreateBracketCellRow(GameObject cell, string playerName, string score, int rowSlot, int winnerSlot, float yTop, float h, float cellW)
        {
            var row = new GameObject($"R{rowSlot}");
            row.transform.SetParent(cell.transform, false);
            var rrt = row.AddComponent<RectTransform>();
            rrt.anchorMin = new Vector2(0f, 1f);
            rrt.anchorMax = new Vector2(0f, 1f);
            rrt.pivot = new Vector2(0f, 1f);
            rrt.anchoredPosition = new Vector2(0f, -yTop);
            rrt.sizeDelta = new Vector2(cellW, h);

            bool isWinner = winnerSlot == rowSlot;
            bool isLoser = winnerSlot != 0 && winnerSlot != rowSlot;
            Color nameColor = isWinner ? new Color(0.95f, 1f, 0.7f) : isLoser ? new Color(0.55f, 0.55f, 0.55f) : new Color(0.92f, 0.95f, 1f);

            string nameText = isWinner ? $"<b>{playerName}</b>" : playerName;
            UIFactory.CreateText("N", row.transform, nameText, 13f, nameColor, UIFactory.AlignMidLeft, sizeDelta: new Vector2(cellW - 36, h));
            // Position name with left padding.
            var nGo = row.transform.Find("N");
            if (nGo != null)
            {
                var nrt = nGo.GetComponent<RectTransform>();
                nrt.anchorMin = new Vector2(0f, 1f); nrt.anchorMax = new Vector2(0f, 1f); nrt.pivot = new Vector2(0f, 1f);
                nrt.anchoredPosition = new Vector2(8f, 0f);
            }

            if (!string.IsNullOrEmpty(score))
            {
                Color scoreColor = isWinner ? new Color(1f, 0.95f, 0.4f) : new Color(0.7f, 0.7f, 0.7f);
                UIFactory.CreateText("S", row.transform, score, 14f, scoreColor, UIFactory.AlignMidRight, sizeDelta: new Vector2(28, h));
                var sGo = row.transform.Find("S");
                if (sGo != null)
                {
                    var srt = sGo.GetComponent<RectTransform>();
                    srt.anchorMin = new Vector2(0f, 1f); srt.anchorMax = new Vector2(0f, 1f); srt.pivot = new Vector2(0f, 1f);
                    srt.anchoredPosition = new Vector2(cellW - 32, 0f);
                }
            }
        }

        /// <summary>Build a placeholder bracket of the given size (4/8/16)
        /// for the voting / pre-lock state. All matches have null player
        /// names, prereq_match_ids set so connector lines still draw.
        /// Tournament format = double_elim_bo3.</summary>
        private static ApiClient.TournamentMatchRow[] SynthesizeBlankBracket(int n)
        {
            var list = new List<ApiClient.TournamentMatchRow>();
            int wbRounds = 0; int x = n; while (x > 1) { x >>= 1; wbRounds++; }
            // WB
            var wbIds = new Dictionary<(int r, int s), string>();
            for (int r = 1; r <= wbRounds; r++)
            {
                int matchCount = n / (1 << r);
                for (int s = 0; s < matchCount; s++)
                {
                    string id = $"BLANK_W_{r}_{s}";
                    wbIds[(r, s)] = id;
                    var prereq = new List<string>();
                    if (r > 1)
                    {
                        if (wbIds.TryGetValue((r - 1, s * 2), out var p1)) prereq.Add(p1);
                        if (wbIds.TryGetValue((r - 1, s * 2 + 1), out var p2)) prereq.Add(p2);
                    }
                    list.Add(new ApiClient.TournamentMatchRow {
                        match_id = id, bracket_side = "W", round = r, slot_idx = s, status = "pending",
                        prereq_match_ids = prereq.ToArray(),
                    });
                }
            }
            // LB — skip for blank to keep the placeholder simple. A real
            // LB layout requires careful prereq plumbing that mirrors the
            // server's build_double_elim_bracket output. The blank shape
            // shows the WB tree only, which is enough for "what does an
            // 8-player tournament look like?".
            // GF placeholder.
            list.Add(new ApiClient.TournamentMatchRow {
                match_id = "BLANK_GF", bracket_side = "GF", round = 1, slot_idx = 0, status = "pending",
                prereq_match_ids = new string[0],
            });
            return list.ToArray();
        }

        /// <summary>Render the Tournament tab's "Upcoming Match Bets" section.
        /// Pulls every active tournament series in pre_match phase from
        /// CachedActiveSeries (which polls server-side every few seconds via
        /// /series/active), builds the same 3-row bet UI used in the Live
        /// Ranked Games panel for each one. Hides the whole box when there's
        /// nothing to bet on.</summary>
        private static void RefreshTournamentBets()
        {
            if (tTournBetsBox == null || tTournBetsContainer == null) return;
            // Reset pool.
            foreach (var r in tTournBetRowPool) r.SetActive(false);

            var raw = ApiClient.CachedActiveSeries;
            var preMatch = new List<ApiClient.ActiveSeriesEntry>();
            if (raw != null)
            {
                foreach (var s in raw)
                    if (s.is_tournament && s.phase == "pre_match")
                        preMatch.Add(s);
            }
            if (preMatch.Count == 0)
            {
                tTournBetsBox.SetActive(false);
                return;
            }
            tTournBetsBox.SetActive(true);
            UIFactory.SetText(tTournBetsHeader,
                $"<color=#FFD94D>Upcoming Match Bets</color>  <color=#888>({preMatch.Count})</color>");

            int idx = 0;
            foreach (var s in preMatch)
            {
                // Header row, bet-on-p1 row, bet-on-p2 row — 3 per series.
                var hdr = GetOrCreateTournBetRow(idx++);
                ApplyHeaderRow(hdr, s);
                var bp1 = GetOrCreateTournBetRow(idx++);
                ApplyBetRow(bp1, s, true);
                var bp2 = GetOrCreateTournBetRow(idx++);
                ApplyBetRow(bp2, s, false);
            }
        }

        private static GameObject GetOrCreateTournBetRow(int idx)
        {
            while (tTournBetRowPool.Count <= idx)
            {
                var go = new GameObject($"tbet{tTournBetRowPool.Count}");
                go.transform.SetParent(tTournBetsContainer.transform, false);
                go.AddComponent<RectTransform>();
                UIFactory.AddHLG(go, spacing: 4, forceExpandH: true);
                UIFactory.AddLE(go, prefH: 26, flexH: 0);
                tTournBetRowPool.Add(go);
            }
            var row = tTournBetRowPool[idx];
            for (int i = row.transform.childCount - 1; i >= 0; i--)
                UnityEngine.Object.Destroy(row.transform.GetChild(i).gameObject);
            row.SetActive(true);
            return row;
        }

        private static void RefreshTournaments()
        {
            // Tournament-tab pre-match bet section runs on every tab refresh
            // — pulls from the same CachedActiveSeries that the Leaderboard
            // tab's Live Ranked Games panel uses, so the data is always
            // fresh as long as ApiClient.FetchActiveSeries is being polled.
            RefreshTournamentBets();

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
            // Live prize block (item 2): amounts scale with confirmed signups —
            // server-computed (single source of truth), growth spelled out so
            // every extra signup visibly raises the pot.
            if (txtTPrizes != null)
            {
                if (t.prize_gold_1 > 0)
                {
                    int pp = Math.Max(8, t.prize_players);
                    string growth = t.status == "voting"
                        ? (t.prize_players < 16
                            ? $"\n  <color=#7FE8C3>Every signup past 8 grows the pot - 16 players doubles it! (now: {t.prize_players})</color>"
                            : "\n  <color=#7FE8C3>Max pot - 16 players!</color>")
                        : "";
                    UIFactory.SetText(txtTPrizes,
                        $"<b><color=#FFD94D>PRIZES</color></b> <color=#888>(at {pp} players{(t.status == "voting" ? ", live" : "")})</color>\n"
                        + $"  * <color=#FFE580>1st</color> - {t.prize_gold_1}g / {t.prize_xp_1} XP / Winner role\n"
                        + $"  * <color=#C8C8C8>2nd</color> - {t.prize_gold_2}g / {t.prize_xp_2} XP / Runner Up role\n"
                        + $"  * <color=#D4894A>3rd</color> - {t.prize_gold_3}g / {t.prize_xp_3} XP / 3rd Place role (loser of LB final)"
                        + growth);
                }
                else UIFactory.SetText(txtTPrizes, "");
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
            UIFactory.SetText(txtTDiscordGate, t.my_discord_linked ? "" : "<color=#FFB088>Link Discord first (Home tab) to sign up.</color>");
            UIFactory.SetText(txtTPenalty, $"Your no-show penalty: <color=#FFCC44>{(t.my_penalty_pct * 100f):0.0}%</color>");

            // Async skips voting entirely - there's no scheduled_start_ts delay,
            // lock triggers immediate start. Hide the whole vote panel (not just
            // the slot rows) so the "Pick Your Start Times" header disappears too.
            if (tVoteBoxPanel != null) tVoteBoxPanel.SetActive(!isAsync);
            // Item 3: time-vote UI is visible during voting even BEFORE signup —
            // picking times is now a prerequisite of signing up (the vote rides
            // the signup request). Save Votes stays signup-gated below.
            bool voteVisible = !isAsync && t.status == "voting";
            // (Previously force-enabled the vote row parent here, which was
            // re-showing the whole box for async. Removed - tVoteBoxPanel above
            // controls visibility.)
            int slots = t.time_slot_options?.Length ?? 0;
            // Offered slots changed (pushback / new week / slots aging out):
            // drop frozen local edits so the index-based checkboxes re-sync
            // from server truth instead of silently pointing at new times.
            string slotSig = string.Join("|", t.time_slot_options ?? Array.Empty<string>());
            if (slotSig != _tVoteSlotSig) { _tVoteSlotSig = slotSig; _tVoteLocalEdited = false; }
            var myVotes = new HashSet<string>(t.my_votes ?? Array.Empty<string>());
            var tallies = new Dictionary<string, int>();
            if (t.time_slot_tallies != null)
                foreach (var tv in t.time_slot_tallies) tallies[tv.slot_ts] = tv.votes;
            // Agreement progress: the lock needs min_players votes on ONE slot.
            if (txtTVoteHdr != null)
            {
                int topTally = 0;
                foreach (var kv in tallies) if (kv.Value > topTally) topTally = kv.Value;
                UIFactory.SetText(txtTVoteHdr, t.status == "voting"
                    ? $"Pick Your Start Times <color=#888>(multi-select, required to sign up)</color>  " +
                      $"<color=#7FE8C3>best time: {topTally}/{t.min_players} agreed</color>"
                    : "Pick Your Start Times (multi-select)");
            }

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
                // Compact "(N)" + tz-less label + no wrap: the two-column cell
                // is 158px — the old "(5 votes)" + " Local" suffix wrapped over
                // the row below (review find; learning #70 family).
                string tallyTxt = votes > 0 ? $" <color=#7FE8C3>({votes})</color>" : "";
                UIFactory.SetWordWrap(tSlotLabels[i], false);
                UIFactory.SetText(tSlotLabels[i], $"{_FmtSlot(iso, includeTz: false)}{tallyTxt}");
            }
            // Collapse fully-empty slot rows (future-filtered options can leave
            // fewer than 8 slots; a row whose both cells are hidden would
            // otherwise keep its fixed 24px and read as a gap).
            for (int r = 0; r * 2 < tSlotToggles.Count; r++)
            {
                var rowGO = tSlotToggles[r * 2].transform.parent.parent != null
                    ? tSlotToggles[r * 2].transform.parent.parent.gameObject : null;
                if (rowGO == null || rowGO == tTimeVoteRow) continue;
                bool anyCell = false;
                for (int c = 0; c < 2 && r * 2 + c < tSlotToggles.Count; c++)
                    if (tSlotToggles[r * 2 + c].transform.parent.gameObject.activeSelf) { anyCell = true; break; }
                rowGO.SetActive(anyCell);
            }
            // Save Votes only applies to an existing signup (pre-signup picks
            // ride the signup request instead).
            if (tVoteSaveBtn != null) tVoteSaveBtn.SetActive(voteVisible && signedUp);
            // Force-start only surfaces once the minimum player count is met (min_players, default 8).
            // Before that the button is pointless - the server rejects force-start with <8 signups anyway,
            // and hiding it removes the "why doesn't this work?" confusion early in the voting window.
            int confirmedSignups = 0;
            if (t.signups != null)
                foreach (var _s in t.signups)
                    if (!_s.is_speculative) confirmedSignups++;
            // Force-start is a sync-only concept - async tournaments start
            // immediately when signups close, so there's nothing to force.
            bool forceStartAvailable = !isAsync && voteVisible && signedUp && confirmedSignups >= t.min_players;
            UIFactory.SetText(txtTForceCount,
                t.status == "voting"
                    ? (forceStartAvailable
                        ? $"Force-start votes: {t.force_vote_count}/{confirmedSignups}"
                        : !signedUp
                            ? "Sign up to unlock force-start"
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
            bool showPlayNow = false;
            bool inBreak = false;
            string myMatchLine = "";
            string myRoomCode = "";
            if (t.status == "running" && signedUp && t.matches != null)
            {
                // Break state (July 17 round 2): a 'scheduled' match of mine
                // shows a countdown + the Play Now button instead of the
                // ready-up flow. Countdown comes from my-active-matches
                // (scheduled_seconds_left snapshot + fetch time).
                foreach (var m in t.matches)
                {
                    if (m.status != "scheduled") continue;
                    if (m.p1_signup_id != t.my_signup_id && m.p2_signup_id != t.my_signup_id) continue;
                    string opp2 = (m.p1_signup_id == t.my_signup_id) ? m.p2_display_name : m.p1_display_name;
                    string cdown = "";
                    bool iPressed = false, oppPressed = false;
                    var live = ApiClient.CachedMyActiveTournamentMatches;
                    if (live != null)
                        foreach (var am in live)
                            if (am.match_id == m.match_id)
                            {
                                iPressed = am.my_early_ok; oppPressed = am.opp_early_ok;
                                if (am.scheduled_seconds_left >= 0)
                                {
                                    float left = am.scheduled_seconds_left - (Time.realtimeSinceStartup - am.fetched_at_realtime);
                                    if (left < 0) left = 0;
                                    cdown = $" starts in <color=#FFDE88>{(int)(left / 60)}:{(int)(left % 60):00}</color>";
                                }
                                break;
                            }
                    string earlyState = iPressed
                        ? (oppPressed ? "" : "  <color=#7FE8C3>(Play Now sent - waiting on opponent)</color>")
                        : "  <color=#888>(both press Play Now to skip the break)</color>";
                    myMatchLine = $"Next match (R{m.round}{(m.bracket_side == "TP" ? " 3rd Place" : "")}): vs <color=#FFDE88>{opp2 ?? "?"}</color> -{cdown}{earlyState}";
                    showMyMatch = true;
                    inBreak = true;
                    showPlayNow = !iPressed;
                    break;
                }
                foreach (var m in t.matches)
                {
                    if (m.status != "ready" && m.status != "active") continue;
                    if (m.p1_signup_id != t.my_signup_id && m.p2_signup_id != t.my_signup_id) continue;
                    if (!string.IsNullOrEmpty(m.match_id))
                        myRoomCode = !string.IsNullOrEmpty(m.photon_room_name)
                            ? m.photon_room_name
                            : "sct-" + m.match_id.Replace("-", "").Substring(0, 12);
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
                        string roomName = !string.IsNullOrEmpty(m.photon_room_name)
                            ? m.photon_room_name
                            : "sct-" + m.match_id.Replace("-", "").Substring(0, 12);
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
            if (txtTReconnectBtn != null) txtTReconnectBtn.SetActive(showMyMatch && !inBreak);
            if (tPlayNowBtn != null) tPlayNowBtn.SetActive(showPlayNow);
            if (txtTReadyBtn != null) txtTReadyBtn.SetActive(showMyMatch && !inBreak);
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

            // Bracket render — visual diagram (positional cells + connector lines)
            // when we have data; row-pool placeholder for true empty states only.
            // Sync `locked` shows a BLANK bracket of the right shape (no names)
            // so signups can see the structure without scouting matchups, then
            // reveals names when status flips to `running`.
            int brkIdx = 0;
            bool bracketHidden = !isAsync && t.status != "running" && t.status != "completed";
            bool haveMatches = t.matches != null && t.matches.Length > 0;
            bool wantBlankBracket = bracketHidden && haveMatches; // sync locked: show shape, no names
            int blankBracketSize = 0;
            if (!haveMatches && (t.status == "voting" || t.status == "locked"))
            {
                // No bracket built yet — derive a shape from current signup
                // count (rounded to next power of 2), capped to the
                // tournament's max_players so the diagram doesn't balloon.
                int active = 0;
                if (t.signups != null)
                    foreach (var s in t.signups) if (!s.is_speculative) active++;
                int targetSize = Math.Max(active, 4);
                blankBracketSize = 1;
                while (blankBracketSize < targetSize) blankBracketSize *= 2;
                if (blankBracketSize > 16) blankBracketSize = 16;
            }

            if (haveMatches || blankBracketSize > 0)
            {
                // Hide all row-pool placeholder rows, render the visual bracket.
                for (int i = 0; i < tBracketRowPool.Count; i++) tBracketRowPool[i].SetActive(false);
                if (tBracketVisual != null)
                {
                    tBracketVisual.SetActive(true);
                    RenderVisualBracket(t, wantBlankBracket, blankBracketSize, isAsync);
                }
                _tBracketRowPurposes.Clear();
                brkIdx = tBracketRowPool.Count; // skip the trailing row-hide loop
            }
            else if (bracketHidden && !haveMatches)
            {
                if (tBracketVisual != null) tBracketVisual.SetActive(false);
                if (brkIdx < tBracketRowPool.Count)
                {
                    UIFactory.SetColor(tBracketRowTexts[brkIdx], C_DIM);
                    UIFactory.SetText(tBracketRowTexts[brkIdx],
                        $"<i>Bracket revealed when the tournament starts ({_FmtSlot(t.scheduled_start_ts)}).</i>");
                    tBracketRowPool[brkIdx].SetActive(true);
                    brkIdx++;
                }
            }
            else
            {
                // Voting / no-data state with no signups yet — minimal placeholder.
                if (tBracketVisual != null) tBracketVisual.SetActive(false);
                if (brkIdx < tBracketRowPool.Count)
                {
                    UIFactory.SetColor(tBracketRowTexts[brkIdx], C_DIM);
                    UIFactory.SetText(tBracketRowTexts[brkIdx], "<i>Bracket appears once signups have rolled in.</i>");
                    tBracketRowPool[brkIdx].SetActive(true);
                    brkIdx++;
                }
            }

            // ── End of new bracket render. The block below is the legacy
            // text-list render (kept as an unreached fallback in case the
            // visual path bails out). Skipping via the trailing for-loop.
            if (false)
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
        // Signature of the server's offered slot set. When it changes (weekly
        // pushback, new tournament), local checkbox edits are stale — the
        // checked state is INDEX-based, so keeping it would silently retarget
        // picks onto different datetimes (and freeze server re-sync forever,
        // since Save Votes is the only other reset).
        private static string _tVoteSlotSig = "";

        private const string _SYNC_INSTRUCTIONS =
            "<b><color=#FFD94D>HOW IT WORKS (Sync)</color></b>\n" +
            "  1. Pick every start time you can make, then sign up (Discord must be linked)\n" +
            "  2. It locks when <b>8+ players agree on one time</b> - decided <b>2 days before</b> the default start, so you always get 24h+ notice; players who can't make the winning time are removed (no penalty)\n" +
            "  3. <b>Have ROUNDS open at start time</b> (main menu is fine - no tab-sitting needed)\n" +
            "  4. Mod <b>auto-connects you to your opponent</b> - no queue, no invites\n" +
            "  5. Play BO3, bracket advances automatically - <b>plan for a couple of hours total</b>\n" +
            "\n" +
            "<b><color=#FFD94D>BETWEEN MATCHES</color></b>\n" +
            "  * ~7 min breather before each of your matches after round 1\n" +
            "  * Both players press <b>Play Now</b> to skip the break and start early\n" +
            "  * Show up within 10 min of your match or forfeit\n" +
            "  * Bracket hidden until start (no scouting your first opponent)\n" +
            "\n" +
            "<b><color=#FFD94D>FORMAT</color></b>\n" +
            "  * <b>Double-elim</b> BO3 (first to 2) - losing once drops you to the losers bracket\n" +
            "  * Matches run in parallel: your next match schedules the moment its players are known\n" +
            "  * Top seeds get byes when fewer than 16 sign up\n" +
            "  * Grand Final: WB champ vs LB champ (bracket reset if LB wins first BO3)\n" +
            "  * All matches count toward ranked Elo\n" +
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
            "<b><color=#FFD94D>PENALTY %</color></b>\n" +
            "  * Grows when you sign up but forfeit a match by missing the 7-day deadline";

        // ── 2v2 tab ───────────────────────────────────────────────
        private static object txtTeamHeader, txtTeamStatus, txtTeamMembers, txtTeamLBHeader;
        private static GameObject teamSearchBtn, teamSearchCustomBtn, teamLeaveBtn, teamReadyBtn, teamLBContainer;
        // Bug #76: inner-ScrollRect handle for the nested-scroll wheel fix.
        private static Component teamLBScrollRect;
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
            MakeSubTabAnchor(8, outer.transform, true);   // round 5 item 3
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

            // Live 2v2 Now — compact strip showing active 2v2 series. Mirrors
            // the leaderboard-tab Live Ranked Games panel but lives directly
            // in the 2v2 tab so users don't have to switch tabs to see who's
            // currently mid-series. Hidden when no 2v2 is live.
            var liveTeamPanel = UIFactory.CreatePanel("TLT", panel.transform, C_PANEL);
            UIFactory.AddVLG(liveTeamPanel, spacing: 2, padL: 12, padR: 12, padT: 6, padB: 6);
            UIFactory.AddLE(liveTeamPanel, flexH: 0);
            txtTeamLiveHeader = UIFactory.CreateText("TLTH", liveTeamPanel.transform,
                "<b><color=#FF6688>* Live 2v2 Now</color></b>", 16f, C_SUB,
                UIFactory.AlignMidLeft, sizeDelta: new Vector2(900, 22));
            txtTeamLiveBody = UIFactory.CreateText("TLTB", liveTeamPanel.transform,
                "<color=#666><i>No live 2v2 right now.</i></color>", 14f, C_LABEL,
                UIFactory.AlignTopLeft, sizeDelta: new Vector2(900, 22));
            var ltbComp = txtTeamLiveBody as Component;
            if (ltbComp != null) UIFactory.AddLE(ltbComp.gameObject, prefH: 22, minH: 22, flexH: 0);
            UIFactory.SetWordWrap(txtTeamLiveBody, false);
            teamLivePanel = liveTeamPanel;

            // Queue row — Random Queue + Custom Lobbies side-by-side as two
            // columns. Was previously stacked vertically with both bodies at
            // a fixed 900-wide × 160-tall block; that wasted half the screen
            // horizontally when 0-2 people were queueing in either bucket.
            // Side-by-side packs both buckets in a single vertical band.
            var queueRow = new GameObject("TQR");
            queueRow.transform.SetParent(panel.transform, false);
            queueRow.AddComponent<RectTransform>();
            UIFactory.AddHLG(queueRow, spacing: 8);
            UIFactory.AddLE(queueRow, flexH: 0);

            // Random Queue (left column)
            var queueListPanel = UIFactory.CreatePanel("TQL", queueRow.transform, C_PANEL);
            UIFactory.AddVLG(queueListPanel, spacing: 2, padL: 10, padR: 10, padT: 6, padB: 6);
            UIFactory.AddLE(queueListPanel, flexW: 1, flexH: 0);
            txtTeamQueueListHeader = UIFactory.CreateText("TQLH", queueListPanel.transform,
                "<b>Random Queue</b>", 16f, C_SUB, UIFactory.AlignMidLeft, sizeDelta: new Vector2(440, 22));
            txtTeamQueueListBody = UIFactory.CreateText("TQLB", queueListPanel.transform,
                "<color=#888>Loading…</color>", 14f, C_LABEL, UIFactory.AlignTopLeft,
                sizeDelta: new Vector2(440, 22));
            var qlbComp = txtTeamQueueListBody as Component;
            if (qlbComp != null) UIFactory.AddLE(qlbComp.gameObject, prefH: 22, minH: 22, flexH: 0);
            UIFactory.SetWordWrap(txtTeamQueueListBody, true);

            // Custom Lobbies (right column)
            var manualPanel = UIFactory.CreatePanel("TQM", queueRow.transform, C_PANEL);
            UIFactory.AddVLG(manualPanel, spacing: 2, padL: 10, padR: 10, padT: 6, padB: 6);
            UIFactory.AddLE(manualPanel, flexW: 1, flexH: 0);
            txtTeamQueueManualHeader = UIFactory.CreateText("TQMH", manualPanel.transform,
                "<b>Custom Lobbies</b>", 16f, C_SUB, UIFactory.AlignMidLeft, sizeDelta: new Vector2(440, 22));
            txtTeamQueueManualBody = UIFactory.CreateText("TQMB", manualPanel.transform,
                "<color=#888>Loading…</color>", 14f, C_LABEL, UIFactory.AlignTopLeft,
                sizeDelta: new Vector2(440, 22));
            var qmbComp = txtTeamQueueManualBody as Component;
            if (qmbComp != null) UIFactory.AddLE(qmbComp.gameObject, prefH: 22, minH: 22, flexH: 0);
            UIFactory.SetWordWrap(txtTeamQueueManualBody, true);

            // Defensive: turn off raycastTarget on these panel backgrounds so
            // mouse-wheel scroll + drag-scroll bubble cleanly to the outer
            // ScrollRect even when the cursor is on a dark panel background.
            void disablePanelRaycast(GameObject p)
            {
                var pImg = p.GetComponent(UIFactory.tImage);
                if (pImg != null) UIFactory.tImage.GetProperty("raycastTarget", BindingFlags.Public | BindingFlags.Instance)?.SetValue(pImg, false);
            }
            disablePanelRaycast(liveTeamPanel);
            disablePanelRaycast(queueListPanel);
            disablePanelRaycast(manualPanel);

            // Scroll-discoverability hint. Tester feedback: "the scroll
            // only works on the grey background, people don't know they can
            // scroll down". Always-visible label between the queue band and
            // the leaderboard/history row that explicitly tells the user
            // there's more below — solves the affordance problem without
            // pulling in a full Unity Scrollbar component (which would need
            // reflection-built handle/track infra and is a lot of risk for
            // a static visual hint).
            var scrollHint = UIFactory.CreateText("TSH", panel.transform,
                "<color=#888><i>v  Scroll down for leaderboard + recent series  v</i></color>",
                13f, C_LABEL, UIFactory.AlignMidCenter, sizeDelta: new Vector2(900, 18));
            UIFactory.SetBold(scrollHint, false);

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

            // Left: leaderboard. Feedback item 5: the table's columns are fixed
            // (TLB_COL_W sums to ~750 incl. spacing), so cap the column there and
            // give ALL remaining width to Recent 2v2 Series on the right — the
            // dead strip between the Gold/XP columns and the series panel is
            // gone. flexW:0 is explicit and load-bearing (learning #132: the
            // pager rows inside would otherwise bubble flexW:1 up).
            var lbCol = new GameObject("TLBCol");
            lbCol.transform.SetParent(bottom.transform, false);
            lbCol.AddComponent<RectTransform>();
            UIFactory.AddVLG(lbCol, spacing: 4);
            UIFactory.AddLE(lbCol, prefW: 770, minW: 700, flexW: 0, flexH: 1);
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
            // Bug #76: keep the ScrollRect handle so the refresh can disable
            // it while the content fits (nested-scroll wheel capture fix).
            teamLBScrollRect = lbScroll.scrollGO.GetComponent(UIFactory.tScrollRect);
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
                () => { teamSeriesPageReq = Math.Max(0, teamSeriesPageReq - 1); ApiClient.FetchAllSeriesPaged(teamSeriesPageReq, 10); },
                sizeDelta: new Vector2(28, 22));
            txtTeamHistPageIndicator = UIFactory.CreateText("THPI", histHdrRow.transform,
                "1/1", 13f, C_LABEL, UIFactory.AlignMidCenter, sizeDelta: new Vector2(48, 22));
            teamHistNextBtn = UIFactory.CreateButton("THPN", histHdrRow.transform, ">", 13f, C_WHITE,
                new Color(0.22f, 0.25f, 0.30f, 0.95f),
                () => { teamSeriesPageReq += 1; ApiClient.FetchAllSeriesPaged(teamSeriesPageReq, 10); },
                sizeDelta: new Vector2(28, 22));
            var histScroll = UIFactory.CreateScrollView("THSV", hCol.transform, spacing: 2);
            UIFactory.AddLE(histScroll.scrollGO, flexH: 1);
            teamHistContainer = histScroll.content;
            teamHistScrollRect = histScroll.scrollGO.GetComponent(UIFactory.tScrollRect);
            // Page size is now 10 series (was 3). Worst case all 10 expanded =
            // 10 × (1 header + 4 game rows) = 50 rows; pool 80 leaves headroom.
            // The scroll already flexes to fill the column (flexH:1 above), so
            // the extra rows just fill the previously-empty vertical space.
            for (int i = 0; i < 80; i++) teamHistRows.Add(CreateTeamHistRow(teamHistContainer.transform, $"th{i}"));

            return outer;
        }

        private static List<GameObject> teamLBSortBtns;
        private static string[] teamLBSortKeys;
        private static object[] teamLBHeaderTexts;
        private static GameObject teamHistPrevBtn, teamHistNextBtn;
        private static object txtTeamHistPageIndicator;

        private static object txtTeamHistHeader;
        private static GameObject teamHistContainer;
        // ScrollRect for the Recent 2v2 Series list. Captured at build so
        // RefreshTeamTab can SAVE/RESTORE scroll position across re-renders —
        // without this the 10s auto-refetch (and every expand click) re-rendered
        // the list and snapped scroll back to the top, so the user could never
        // stay scrolled down to reach series at the bottom ("locked in place").
        private static object teamHistScrollRect;
        private static List<TeamHistRow> teamHistRows = new List<TeamHistRow>();
        private class TeamHistRow {
            public GameObject root;
            public object txtLine1, txtLine2;
            // Game-ID copy is a tightly-sized control parented to line 1.
            // Header rows hide it; game rows place it after the rendered text.
            public GameObject btnId;
            // Stacked cards columns — used for game rows. Hidden for series
            // header rows (which show the teams + player titles in txtLine2).
            public GameObject cardsRow;
            public object txtCardsLeft, txtCardsRight;
            // July 22 item 7: per-player telemetry cells (two lines of two) —
            // each is a hover target popping that player's combo graph popup.
            public GameObject teleRow;
            public object txtTeleLA, txtTeleLB, txtTeleRA, txtTeleRB;
            // Compact/expand (v1.26.11): header rows are clickable to toggle the
            // per-game detail. seriesKey is set each render so the (index-captured)
            // ClickHandler knows which series this pooled row currently represents.
            public string seriesKey;
            public bool isHeader;
            // Game rows carry the match UUID for their small [ID] copy button.
            public string matchKey;
        }

        // series_id -> expanded? Persists across re-renders so a series stays open
        // until clicked again. Mirrors the tournament bracket's _tBracketExpanded.
        private static Dictionary<string, bool> _teamSeriesExpanded = new Dictionary<string, bool>();
        private static object txtTeamQueueListHeader;
        private static object txtTeamQueueListBody;
        private static object txtTeamQueueManualHeader;
        private static object txtTeamQueueManualBody;
        private static object txtTeamDcGrace;
        private static GameObject teamPickT1Btn, teamPickT2Btn;
        private static object txtPickStatus;
        // Live 2v2 strip in the 2v2 tab — mirrors the leaderboard tab's Live
        // Ranked Games panel but lives directly inside the 2v2 view.
        private static GameObject teamLivePanel;
        private static object txtTeamLiveHeader;
        private static object txtTeamLiveBody;

        private static TeamHistRow CreateTeamHistRow(Transform parent, string name)
        {
            var row = new TeamHistRow();
            row.root = new GameObject(name);
            row.root.transform.SetParent(parent, false);
            row.root.AddComponent<RectTransform>();
            UIFactory.AddVLG(row.root, spacing: 2, padL: 8, padR: 6, padT: 4, padB: 4);
            UIFactory.AddLE(row.root, minH: 30, flexH: 0);
            /* Feedback item 5: bigger series text (15->17 / 13->14) + rows widened
             * to use the panel (the column itself is also wider now). */
            row.txtLine1 = UIFactory.CreateText("l1", row.root.transform, "", 17f, C_WHITE, UIFactory.AlignTopLeft, sizeDelta: new Vector2(1000, 26));
            // Keep the chip outside the row VLG by parenting it to the line text.
            // Its 34x18 rect is the whole copy target; the old target was the
            // complete game row, including both card columns and blank space.
            var line1Comp = row.txtLine1 as Component;
            if (line1Comp != null)
            {
                row.btnId = UIFactory.CreateButton("id", line1Comp.transform, "[ID]", 12f, C_DIM,
                    new Color(0.18f, 0.20f, 0.26f, 0.45f),
                    () =>
                    {
                        if (!string.IsNullOrEmpty(row.matchKey))
                            CopyGameCode(row.matchKey);
                    },
                    sizeDelta: new Vector2(34, 18));
                var idRt = row.btnId.GetComponent<RectTransform>();
                idRt.anchorMin = idRt.anchorMax = new Vector2(0f, 0.5f);
                idRt.pivot = new Vector2(0f, 0.5f);
                idRt.anchoredPosition = new Vector2(260f, 0f);
                row.btnId.SetActive(false);
            }
            // Line 2 holds the "Team A vs Team B" header text on series rows.
            // Hidden when the row renders a per-match cards block instead.
            row.txtLine2 = UIFactory.CreateText("l2", row.root.transform, "", 14f, C_LABEL, UIFactory.AlignTopLeft, sizeDelta: new Vector2(1000, 24));

            // July 22 item 7 (rebuilt after playtest): ONE flat HLG line with a
            // hover cell per player — the earlier nested two-line block laid out
            // wrong (overlapping text). Single-level HLG-under-VLG is the same
            // proven shape as the history rows' stats line. Hidden on header
            // rows and on games with no telemetry.
            row.teleRow = new GameObject("teleRow");
            row.teleRow.transform.SetParent(row.root.transform, false);
            row.teleRow.AddComponent<RectTransform>();
            UIFactory.AddHLG(row.teleRow, spacing: 6, padL: 12);
            UIFactory.AddLE(row.teleRow, prefH: 20, flexH: 0);
            row.txtTeleLA = UIFactory.CreateText("ta", row.teleRow.transform, "", 13f, C_LABEL, UIFactory.AlignMidLeft, sizeDelta: new Vector2(245, 20));
            row.txtTeleLB = UIFactory.CreateText("tb", row.teleRow.transform, "", 13f, C_LABEL, UIFactory.AlignMidLeft, sizeDelta: new Vector2(245, 20));
            row.txtTeleRA = UIFactory.CreateText("tc", row.teleRow.transform, "", 13f, C_LABEL, UIFactory.AlignMidLeft, sizeDelta: new Vector2(245, 20));
            row.txtTeleRB = UIFactory.CreateText("td", row.teleRow.transform, "", 13f, C_LABEL, UIFactory.AlignMidLeft, sizeDelta: new Vector2(245, 20));
            row.teleRow.SetActive(false);

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
            // July 22 item 7a: padT 6 gives the top-left player name breathing
            // room under the "Game N:" line (header rows keep cardsRow inactive
            // so their 46px prefH is untouched).
            UIFactory.AddHLG(row.cardsRow, spacing: 4, padL: 12, padT: 6);
            UIFactory.AddLE(row.cardsRow, minH: 24, flexH: 0);
            row.txtCardsLeft  = UIFactory.CreateText("cl", row.cardsRow.transform, "", 14f,
                new Color(0.55f, 0.80f, 1.00f), UIFactory.AlignTopLeft,
                sizeDelta: new Vector2(300, 200));
            row.txtCardsRight = UIFactory.CreateText("cr", row.cardsRow.transform, "", 14f,
                new Color(1.00f, 0.69f, 0.53f), UIFactory.AlignTopLeft,
                sizeDelta: new Vector2(300, 200));
            // Word-wrap on so any single-card name longer than the column
            // width breaks rather than clips. Vertical stacking via newlines
            // in the text content.
            UIFactory.SetWordWrap(row.txtCardsLeft, true);
            UIFactory.SetWordWrap(row.txtCardsRight, true);
            row.cardsRow.SetActive(false);

            // Make the whole row clickable to expand/collapse its series. The
            // handler reads row.seriesKey/isHeader (set fresh each render) so a
            // pooled row toggles whichever series it currently shows. Transparent
            // Image gives the row a raycast target so clicks land anywhere on it,
            // not just on text glyphs (mirrors the tournament-bracket pattern).
            if (UIFactory.tImage != null && row.root.GetComponent(UIFactory.tImage) == null)
            {
                var img = row.root.AddComponent(UIFactory.tImage);
                UIFactory.tImage.GetProperty("color", BindingFlags.Public | BindingFlags.Instance)
                    ?.SetValue(img, new Color(1f, 1f, 1f, 0.01f));
                UIFactory.tImage.GetProperty("raycastTarget", BindingFlags.Public | BindingFlags.Instance)
                    ?.SetValue(img, true);
            }
            if (row.root.GetComponent<ClickHandler>() == null)
            {
                var ch = row.root.AddComponent<ClickHandler>();
                var capturedRow = row;
                ch.onClick = () =>
                {
                    if (!ClickGuard.Claim(capturedRow.root)) return;
                    // Game rows intentionally do nothing here. Their small [ID]
                    // button owns copy input; the rest of the row remains inert.
                    if (!capturedRow.isHeader) return;
                    if (string.IsNullOrEmpty(capturedRow.seriesKey)) return;
                    bool cur;
                    _teamSeriesExpanded.TryGetValue(capturedRow.seriesKey, out cur);
                    _teamSeriesExpanded[capturedRow.seriesKey] = !cur;
                    dirty = true;
                };
            }

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

        // Preserve the content's PIXEL offset, not verticalNormalizedPosition.
        // Expanding a series changes the content height; restoring the same
        // percentage against that new height maps to a different pixel offset
        // and is the intermittent "click a series, list scrolls down" jump.
        private static float ReadTeamHistScrollY()
        {
            try
            {
                var contentRt = teamHistContainer?.GetComponent<RectTransform>();
                return contentRt != null ? contentRt.anchoredPosition.y : -1f;
            }
            catch { return -1f; }
        }

        private static void WriteTeamHistScrollY(float y)
        {
            try
            {
                if (teamHistScrollRect == null || y < 0f) return;
                var contentRt = teamHistContainer?.GetComponent<RectTransform>();
                var scrollComp = teamHistScrollRect as Component;
                var viewportRt = scrollComp != null && scrollComp.transform.childCount > 0
                    ? scrollComp.transform.GetChild(0) as RectTransform
                    : null;
                if (contentRt == null) return;

                float maxY = viewportRt != null
                    ? Mathf.Max(0f, contentRt.rect.height - viewportRt.rect.height)
                    : Mathf.Max(0f, y);
                var pos = contentRt.anchoredPosition;
                pos.y = Mathf.Clamp(y, 0f, maxY);
                contentRt.anchoredPosition = pos;

                // A wheel flick immediately before the click can leave ScrollRect
                // velocity active; stop it so inertia cannot move the restored anchor.
                UIFactory.tScrollRect.GetMethod("StopMovement", BindingFlags.Public | BindingFlags.Instance)
                    ?.Invoke(teamHistScrollRect, null);
            }
            catch { }
        }

        private static void PositionTeamHistIdButton(TeamHistRow row)
        {
            if (row?.btnId == null || row.txtLine1 == null || row.isHeader) return;
            try
            {
                var textComp = row.txtLine1 as Component;
                var textRt = textComp?.GetComponent<RectTransform>();
                var idRt = row.btnId.GetComponent<RectTransform>();
                if (textComp == null || textRt == null || idRt == null) return;

                float renderedW = 0f;
                var p = textComp.GetType().GetProperty("preferredWidth", BindingFlags.Public | BindingFlags.Instance);
                if (p != null) renderedW = Convert.ToSingle(p.GetValue(textComp));
                if (renderedW < 1f) renderedW = 260f;
                float maxX = textRt.rect.width > idRt.rect.width
                    ? textRt.rect.width - idRt.rect.width
                    : renderedW + 4f;
                idRt.anchoredPosition = new Vector2(Mathf.Clamp(renderedW + 4f, 0f, maxX), 0f);
            }
            catch { }
        }

        // Restore AFTER ContentSizeFitter + VLG settle. The button positions use
        // TMP's rendered width from the same completed layout pass.
        private static System.Collections.IEnumerator RestoreTeamHistScroll(float y)
        {
            yield return null;
            yield return new WaitForEndOfFrame();
            foreach (var row in teamHistRows)
                if (row.root.activeSelf && !row.isHeader) PositionTeamHistIdButton(row);
            WriteTeamHistScrollY(y);
        }

        private static void RefreshTeamTab()
        {
            // Preserve the Recent-2v2-Series scroll position across this re-render
            // (the 10s auto-refetch + expand clicks both re-render the list and
            // would otherwise snap it to the top). Restored at the end of the method.
            float _savedTeamScrollY = ReadTeamHistScrollY();
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

            // Live 2v2 Now strip. One line per active team series. Hidden
            // entirely when no 2v2 is live.
            var liveTeam = ApiClient.CachedActiveTeamSeries;
            int liveCount = liveTeam != null ? liveTeam.Count : 0;
            if (teamLivePanel != null) teamLivePanel.SetActive(liveCount > 0);
            if (liveCount > 0)
            {
                UIFactory.SetText(txtTeamLiveHeader, $"<b><color=#FF6688>* Live 2v2 Now</color></b>  <color=#888>({liveCount})</color>");
                var sbLive = new StringBuilder();
                foreach (var ts in liveTeam)
                {
                    sbLive.Append($"<color=#AAF>{Trunc(ts.t1a_name, 7)}({ts.t1a_rating})+{Trunc(ts.t1b_name, 7)}({ts.t1b_rating})</color>");
                    sbLive.Append($"  <b>{ts.t1_wins}-{ts.t2_wins}</b>  ");
                    sbLive.Append($"<color=#FAA>{Trunc(ts.t2a_name, 7)}({ts.t2a_rating})+{Trunc(ts.t2b_name, 7)}({ts.t2b_rating})</color>\n");
                }
                UIFactory.SetText(txtTeamLiveBody, sbLive.ToString().TrimEnd('\n'));
                int newH = Math.Max(22, liveCount * 18 + 4);
                var liveBodyComp = txtTeamLiveBody as Component;
                if (liveBodyComp != null)
                {
                    var le = liveBodyComp.gameObject.GetComponent(UIFactory.tLE);
                    if (le != null)
                    {
                        UIFactory.tLE.GetProperty("preferredHeight", BindingFlags.Public | BindingFlags.Instance)?.SetValue(le, (float)newH);
                        UIFactory.tLE.GetProperty("minHeight",       BindingFlags.Public | BindingFlags.Instance)?.SetValue(le, (float)newH);
                    }
                }
            }

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
                // v1.32 item 1: podium rank numbers read gold/silver/bronze here too.
                UIFactory.SetColor(row.txtRank,
                    e.rank == 1 ? new Color(1f, 0.84f, 0f) :
                    e.rank == 2 ? new Color(0.75f, 0.75f, 0.75f) :
                    e.rank == 3 ? new Color(0.8f, 0.5f, 0.2f) : C_GOLD);
                // Title goes AFTER the name in [brackets] (matches 1v1 lb).
                string nameDisplay = Trunc(e.display_name, 14);
                if (!string.IsNullOrEmpty(e.title))
                {
                    string col = string.IsNullOrEmpty(e.title_color) ? "#FFD94D" : e.title_color;
                    nameDisplay = IsPodiumTitle(e.title)
                        ? $"{nameDisplay} {PodiumSparkleSpan(e.title, col, 0)}"
                        : $"{nameDisplay} <color={col}>[{Trunc(e.title, 12)}]</color>";
                }
                UIFactory.SetText(row.txtName, nameDisplay);
                UIFactory.SetColor(row.txtName, me ? C_GREEN : C_WHITE);
                // Show 2v2 elo WITH rating deviation (±RD) so confidence is visible.
                // Lower RD = more settled rating. Dim/smaller so it doesn't crowd
                // the headline number. rd defaults to 0 if the server omitted it.
                if (e.rd > 0)
                    UIFactory.SetText(row.txtRating, $"{e.rating} <size=72%><color=#9AA0A6>±{e.rd}</color></size>");
                else
                    UIFactory.SetText(row.txtRating, $"{e.rating}");
                UIFactory.SetText(row.txtWL, $"{e.series_wins}-{e.series_losses}");
                UIFactory.SetText(row.txtWR, $"{e.win_rate * 100f:F0}%");
                UIFactory.SetText(row.txtMate, e.avg_teammate_elo > 0 ? $"{e.avg_teammate_elo}" : "—");
                UIFactory.SetText(row.txtGold, $"{e.team_gold_earned}");
                UIFactory.SetText(row.txtXp,   $"{e.team_xp_earned}");
                row.root.SetActive(true);
            }
            /* Bug #76: the leaderboard's INNER ScrollRect captured mouse-wheel
             * events even when its content fit its viewport (nothing to
             * scroll), so wheeling over it elastic-bounced in place and the
             * TAB's outer scroll never received the event — panels below the
             * fold were unreachable ("doesn't quite scroll, bounces back to
             * the top"). Disable the inner ScrollRect while content fits: a
             * disabled Behaviour doesn't handle OnScroll, so the wheel
             * bubbles up to the outer tab scroll. Re-enables automatically
             * once enough rows exist to genuinely need inner scrolling. */
            try
            {
                var srBeh = teamLBScrollRect as Behaviour;
                if (srBeh != null)
                {
                    float viewH = 0f;
                    var srRT = srBeh.transform as RectTransform;
                    if (srRT != null) viewH = srRT.rect.height;
                    int shownRows = Math.Min(lb.Count, teamLBRows.Count);
                    bool needsScroll = viewH > 1f && shownRows * 23f > viewH;
                    if (srBeh.enabled != needsScroll) srBeh.enabled = needsScroll;
                }
            }
            catch { }
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
            // Reset card hover regions each team-tab render so they don't
            // accumulate across refreshes (mirrors RefreshHistory for My Stats).
            // Only expanded series register chip rects below.
            CompetitiveUI.ClearCardHoverRegions();
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

                // Team sides: caller's team rendered LEFT when a participant;
                // otherwise raw t1 first. Coloring is by SIDE, not by win/loss —
                // left team = blue (#6FB7FF), right team = orange (#FFA864). The
                // old code wrapped an OUTER team <color> around FormatTitleName,
                // whose inner [title] <color>…</color> popped the stack back to
                // the DEFAULT color (not the team color) for everything after it,
                // so most of the vs-line rendered in the row's base color (read as
                // red on loss rows) — that's the "all players show red" bug. We now
                // color each name span individually and never nest team-vs-title.
                ApiClient.TeamSeriesSlot leftA, leftB, rightA, rightB;
                if (callerInSeries && callerTeam == 2)
                { leftA = s.t2a; leftB = s.t2b; rightA = s.t1a; rightB = s.t1b; }
                else
                { leftA = s.t1a; leftB = s.t1b; rightA = s.t2a; rightB = s.t2b; }
                const string LEFT_COL = "#6FB7FF";   // blue side
                const string RIGHT_COL = "#FFA864";  // orange side
                string youTag = callerInSeries ? "  <size=80%><color=#7CFF7C>(you)</color></size>" : "";
                string vsLine =
                    $"{FormatTeamSide(leftA, leftB, LEFT_COL)}{youTag}"
                  + $"   <color=#888>vs</color>   "
                  + $"{FormatTeamSide(rightA, rightB, RIGHT_COL)}";

                bool isExpanded;
                _teamSeriesExpanded.TryGetValue(s.series_id ?? "", out isExpanded);
                string caret = isExpanded ? "<color=#888>[-]</color>" : "<color=#888>[+]</color>";
                // Clear winner readout: name the winning SIDE + their score, not
                // just W/L. Caller sees "You won 3-1" / "You lost 1-3"; spectators
                // see "Blue won 3-1".
                string winLine;
                if (callerInSeries)
                    winLine = seriesWon
                        ? $"<color=#00FF00><b>WON</b></color> {leftScore}-{rightScore}"
                        : $"<color=#FF6666><b>LOST</b></color> {leftScore}-{rightScore}";
                else
                {
                    bool leftWonNeutral = (s.winner_team == 1);
                    string wSide = leftWonNeutral ? $"<color={LEFT_COL}>Blue</color>" : $"<color={RIGHT_COL}>Orange</color>";
                    int wHi = Math.Max(leftScore, rightScore), wLo = Math.Min(leftScore, rightScore);
                    winLine = $"{wSide} <b>won</b> {wHi}-{wLo}";
                }

                var hdr = teamHistRows[rowIdx++];
                hdr.isHeader = true;
                hdr.seriesKey = s.series_id ?? "";
                // Compact header: one rich line — caret + outcome/score + date +
                // your elo delta + your econ. The vs-line (line2) shows the teams.
                UIFactory.SetText(hdr.txtLine1,
                    $"{caret} {outcome} {winLine}  <color=#999>{dt}</color>{ratingDelta}{econ}");
                UIFactory.SetText(hdr.txtLine2, vsLine);
                var hl2 = (hdr.txtLine2 as Component)?.gameObject;
                if (hl2 != null) hl2.SetActive(true);
                if (hdr.cardsRow != null) hdr.cardsRow.SetActive(false);
                if (hdr.teleRow != null) hdr.teleRow.SetActive(false);
                hdr.matchKey = null;
                if (hdr.btnId != null) hdr.btnId.SetActive(false);
                // Honest height: pad 8 + l1 26 + spacing 2 + l2 24 = 60.
                SetTeamHistRowPrefH(hdr, 60, 0);
                hdr.root.SetActive(true);

                // Collapsed series → skip the per-game detail rows entirely. This
                // is the "compact card" default; click the header to expand.
                if (!isExpanded) continue;

                // Per-game detail rows (only when expanded). Each game shows the
                // outcome line + two card columns. Player names render LARGER than
                // their cards (size=120% header vs the 13f card text) and cards are
                // 2-letter ABBREVIATION chips ([MA][EM]…) matching the My Stats page,
                // not long-form names.
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

                    string leftCards  = BuildTeamCardsColumnChips(m, leftA, leftB);
                    string rightCards = BuildTeamCardsColumnChips(m, rightA, rightB);

                    var row = teamHistRows[rowIdx++];
                    row.isHeader = false;
                    row.seriesKey = s.series_id ?? "";
                    row.matchKey = m.match_id;
                    string durChip = m.duration_seconds > 0 ?
                        $"  <color=#8FA3B8><size=85%>{m.duration_seconds / 60}:{m.duration_seconds % 60:00}</size></color>" : "";
                    UIFactory.SetText(row.txtLine1,
                        $"    <color=#666>—</color>  <b>Game {gameNum}</b>: {gOut} {leftR}-{rightR}{durChip}");
                    if (row.btnId != null)
                    {
                        row.btnId.SetActive(!string.IsNullOrEmpty(m.match_id));
                        PositionTeamHistIdButton(row);
                    }
                    // Hide line2; show stacked cards block.
                    var rl2 = (row.txtLine2 as Component)?.gameObject;
                    if (rl2 != null) rl2.SetActive(false);
                    // July 22 item 7: per-player telemetry cells + combo hover graphs.
                    bool anyTele = (m.telemetry_by_player != null && m.telemetry_by_player.Count > 0)
                                   || (m.fps_by_player != null && m.fps_by_player.Count > 0);
                    if (row.teleRow != null) row.teleRow.SetActive(anyTele);
                    int teleH = anyTele ? 22 : 0;   // one flat line (20) + VLG spacing
                    if (anyTele)
                    {
                        FillTeleCell(row.txtTeleLA, m, leftA, false);
                        FillTeleCell(row.txtTeleLB, m, leftB, false);
                        FillTeleCell(row.txtTeleRA, m, rightA, true);
                        FillTeleCell(row.txtTeleRB, m, rightB, true);
                    }
                    UIFactory.SetText(row.txtCardsLeft,  string.IsNullOrEmpty(leftCards)  ? "<color=#666>—</color>" : leftCards);
                    UIFactory.SetText(row.txtCardsRight, string.IsNullOrEmpty(rightCards) ? "<color=#666>—</color>" : rightCards);
                    if (row.cardsRow != null) row.cardsRow.SetActive(true);
                    // Hover tooltip: chips are abbreviated, so the tooltip shows the
                    // FULL card list. Body is grouped BY PLAYER (each teammate's name
                    // then one card per line) so a team column's two players don't
                    // merge into one undifferentiated blob, and titleOverride="" drops
                    // the My-Stats "Your/Opponent's picks" header (wrong framing for a
                    // 2-player team column). fullLine is still passed as the non-empty
                    // gate so columns with no card data simply don't register.
                    RegisterHoverRectFor(row.txtCardsLeft,  BuildTeamCardsFullLine(m, leftA, leftB), false,
                        "", BuildTeamCardsTooltipBody(m, leftA, leftB));
                    RegisterHoverRectFor(row.txtCardsRight, BuildTeamCardsFullLine(m, rightA, rightB), true,
                        "", BuildTeamCardsTooltipBody(m, rightA, rightB));

                    // Auto-size the row to fit the taller of the two card columns.
                    // Height budget (honest layout — the card texts' LayoutElement
                    // now reports the REAL content height, see SetTeamHistRowPrefH):
                    // padT4 + l1 26 + sp2 + [tele 20 + sp2] + cardsPadT6 + content
                    // + padB4 = 42 + teleH + content. 22px/line covers the 14f
                    // chips incl. the 120% bolded name lines.
                    int linesLeft  = CountCardChipLines(m, leftA, leftB);
                    int linesRight = CountCardChipLines(m, rightA, rightB);
                    int linesMax = Math.Max(2, Math.Max(linesLeft, linesRight));
                    int cardsBlockH = linesMax * 22 + 8;
                    SetTeamHistRowPrefH(row, 42 + teleH + cardsBlockH, cardsBlockH);
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

            // Restore the pre-render scroll position once layout settles, so the
            // periodic 10s refetch and expand clicks don't yank the user to top.
            if (_savedTeamScrollY >= 0f && Plugin.Instance != null)
                Plugin.Instance.StartCoroutine(RestoreTeamHistScroll(_savedTeamScrollY));
        }

        private static string FormatTitleName(ApiClient.TeamSeriesSlot s)
        {
            if (s == null) return "?";
            string nm = Trunc(s.name ?? "?", 12);
            if (string.IsNullOrEmpty(s.title)) return nm;
            string col = string.IsNullOrEmpty(s.title_color) ? "#FFD94D" : s.title_color;
            return $"{nm} <color={col}>[{Trunc(s.title, 10)}]</color>";
        }

        // Render one team side of the vs-line in a single side color, with each
        // player's 2v2 elo shown after their name. Critically, the team color is
        // applied PER-NAME (not as an outer wrap around the whole "A + B [title]"
        // span) so an inner [title] <color> tag can't pop the stack back to the
        // base color and leave the rest of the side uncolored — that was the
        // "everyone shows red" bug. Each name is its own closed color span; the
        // title keeps its own color; elo is dim grey.
        private static string FormatTeamSide(ApiClient.TeamSeriesSlot a, ApiClient.TeamSeriesSlot b, string sideColor)
        {
            return $"{FormatPlayerToken(a, sideColor)} <color=#666>+</color> {FormatPlayerToken(b, sideColor)}";
        }

        private static string FormatPlayerToken(ApiClient.TeamSeriesSlot s, string sideColor)
        {
            if (s == null) return $"<color={sideColor}>?</color>";
            string nm = $"<color={sideColor}>{Trunc(s.name ?? "?", 12)}</color>";
            string title = "";
            if (!string.IsNullOrEmpty(s.title))
            {
                string col = string.IsNullOrEmpty(s.title_color) ? "#FFD94D" : s.title_color;
                title = $" <color={col}>[{Trunc(s.title, 10)}]</color>";
            }
            string elo = s.rating > 0 ? $" <size=78%><color=#9AA0A6>{s.rating}</color></size>" : "";
            return $"{nm}{title}{elo}";
        }

        // Compact 2-letter card chips per player for the expanded game detail.
        // Player name is rendered LARGER (size=120%) than the chips so the name
        // reads as a heading; chips are [MA][EM]… exactly like the My Stats page
        // (FormatCardLine). No long-form card names. Two cards... actually chips
        // are tiny so we fit many per line and let word-wrap break them.
        private static string BuildTeamCardsColumnChips(ApiClient.TeamSeriesMatch m, ApiClient.TeamSeriesSlot a, ApiClient.TeamSeriesSlot b)
        {
            if (m == null || m.cards_by_player == null) return "";
            bool anyCards = false;
            foreach (var slot in new[] { a, b })
            {
                if (slot == null || string.IsNullOrEmpty(slot.steam_id)) continue;
                if (m.cards_by_player.TryGetValue(slot.steam_id, out var cs) && cs != null && cs.Count > 0)
                { anyCards = true; break; }
            }
            if (!anyCards) return "<color=#666><i>(card data not recorded)</i></color>";
            var sb = new StringBuilder();
            void appendFor(ApiClient.TeamSeriesSlot s)
            {
                if (s == null || string.IsNullOrEmpty(s.steam_id)) return;
                if (sb.Length > 0) sb.Append("\n");
                bool hasCards = m.cards_by_player.TryGetValue(s.steam_id, out var cards) && cards != null && cards.Count > 0;
                // Larger, bold player-name heading (size=120% over the 13f field).
                sb.Append("<size=120%><b>").Append(Trunc(s.name ?? "?", 14)).Append("</b></size>");
                if (!hasCards) { sb.Append("\n  <color=#666>—</color>"); return; }
                sb.Append("\n  ").Append(CardsToChips(cards));
            }
            appendFor(a);
            appendFor(b);
            return sb.ToString();
        }

        // Flat comma-separated FULL card-name list for a whole team column — used
        // only as the non-empty GATE for tooltip registration (so a column with no
        // card data doesn't register). The visible tooltip BODY comes from
        // BuildTeamCardsTooltipBody below.
        private static string BuildTeamCardsFullLine(ApiClient.TeamSeriesMatch m, ApiClient.TeamSeriesSlot a, ApiClient.TeamSeriesSlot b)
        {
            if (m == null || m.cards_by_player == null) return "";
            var parts = new List<string>();
            void addFor(ApiClient.TeamSeriesSlot s)
            {
                if (s == null || string.IsNullOrEmpty(s.steam_id)) return;
                if (m.cards_by_player.TryGetValue(s.steam_id, out var cards) && cards != null)
                    foreach (var c in cards) if (!string.IsNullOrEmpty(c)) parts.Add(c.Trim());
            }
            addFor(a);
            addFor(b);
            return string.Join(", ", parts);
        }

        // Pre-formatted tooltip body for a team column: each teammate's name as a
        // bold heading, then one FULL card name per line beneath it. Grouping by
        // player keeps the two teammates' picks visually separate (the bug was both
        // players' cards merging into one clump) and one-per-line keeps them legible.
        private static string BuildTeamCardsTooltipBody(ApiClient.TeamSeriesMatch m, ApiClient.TeamSeriesSlot a, ApiClient.TeamSeriesSlot b)
        {
            if (m == null || m.cards_by_player == null) return "";
            var sb = new StringBuilder();
            void addFor(ApiClient.TeamSeriesSlot s)
            {
                if (s == null || string.IsNullOrEmpty(s.steam_id)) return;
                if (sb.Length > 0) sb.Append('\n');
                sb.Append("<b>").Append(Trunc(s.name ?? "?", 16)).Append("</b>");
                bool has = m.cards_by_player.TryGetValue(s.steam_id, out var cards) && cards != null && cards.Count > 0;
                if (!has) { sb.Append("\n  <color=#888>(no cards)</color>"); return; }
                foreach (var raw in cards)
                {
                    string name = (raw ?? "").Trim();
                    if (name.Length == 0) continue;
                    // Strip any rarity color markup the server may prefix.
                    int lt = name.IndexOf('>'); if (lt >= 0 && lt < name.Length - 1) name = name.Substring(lt + 1);
                    int gt = name.IndexOf('<'); if (gt > 0) name = name.Substring(0, gt);
                    name = name.Trim();
                    if (name.Length == 0) continue;
                    sb.Append("\n  • ").Append(name);
                }
            }
            addFor(a);
            addFor(b);
            return sb.ToString();
        }

        // Turn a card-name list into bracketed 2-letter chips ([MA][EM][EC]…),
        // mirroring FormatCardLine on the My Stats page. Strips any rarity color
        // markup the server may have prefixed.
        private static string CardsToChips(List<string> cards)
        {
            if (cards == null || cards.Count == 0) return "";
            var sb = new StringBuilder();
            foreach (var raw in cards)
            {
                string name = (raw ?? "").Trim();
                if (name.Length == 0) continue;
                int lt = name.IndexOf('>');
                if (lt >= 0 && lt < name.Length - 1) name = name.Substring(lt + 1);
                int gt = name.IndexOf('<');
                if (gt > 0) name = name.Substring(0, gt);
                name = name.Trim();
                if (name.Length == 0) continue;
                string ab = name.Length >= 2 ? name.Substring(0, 2).ToUpperInvariant() : name.ToUpperInvariant();
                sb.Append('[').Append(ab).Append("] ");
            }
            return sb.ToString().TrimEnd();
        }

        // Line estimate for chip layout: 1 name heading + ~ceil(cards/8) chip
        // rows (chips are small; ~8 fit per column before word-wrap), per player.
        private static int CountCardChipLines(ApiClient.TeamSeriesMatch m, ApiClient.TeamSeriesSlot a, ApiClient.TeamSeriesSlot b)
        {
            int lines = 0;
            void countFor(ApiClient.TeamSeriesSlot s)
            {
                if (s == null || string.IsNullOrEmpty(s.steam_id)) return;
                lines += 1; // name heading (rendered taller, counts ~1.2 — covered by row math)
                if (m != null && m.cards_by_player != null
                    && m.cards_by_player.TryGetValue(s.steam_id, out var cards) && cards != null && cards.Count > 0)
                    lines += Math.Max(1, (cards.Count + 7) / 8);
                else
                    lines += 1;
            }
            countFor(a);
            countFor(b);
            return lines;
        }

        // Set the preferredHeight on a TeamHistRow so the outer scroll-content
        // VLG sizes it to fit the dynamic cards block. Also stretches the two
        // card column text fields to the full row content height so wrapping +
        // tall lists render in-place rather than clipping at a fixed sizeDelta.
        private static void SetTeamHistRowPrefH(TeamHistRow row, int prefH, int cardContentH)
        {
            try
            {
                var le = row.root.GetComponent(UIFactory.tLE);
                if (le != null)
                {
                    var pP = UIFactory.tLE.GetProperty("preferredHeight", BindingFlags.Public | BindingFlags.Instance);
                    pP?.SetValue(le, (float)prefH);
                }
                // Resize the card columns to the ACTUAL content height — both the
                // rect AND the LayoutElement. The LE half is load-bearing (July 22
                // playtest): CreateText pinned prefH to the build-time sizeDelta
                // (200), so the row's VLG budgeted 200px for the cards block no
                // matter what the rect said — the layout overflowed the row and
                // neighboring rows' text overlapped ("names shifting into the
                // Game N line"). With the LE honest, VLG child sums equal the
                // row's prefH by construction.
                if (row.cardsRow != null && row.cardsRow.activeSelf)
                {
                    int contentH = Math.Max(40, cardContentH);
                    void resizeText(object t)
                    {
                        var c = t as Component;
                        if (c == null) return;
                        var rt = c.GetComponent<RectTransform>();
                        if (rt == null) return;
                        var sz = rt.sizeDelta;
                        rt.sizeDelta = new Vector2(sz.x, contentH);
                        UIFactory.SetPrefH(c.gameObject, contentH);
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
            // If neither player on this team has any card entries, render
            // a single-line "(card data not recorded)" placeholder instead
            // of repeating "—" under every name. Hits historical matches
            // recovered without per-pick data, where the row otherwise
            // looked like 4 confused dashes.
            bool anyCards = false;
            foreach (var slot in new[] { a, b })
            {
                if (slot == null || string.IsNullOrEmpty(slot.steam_id)) continue;
                if (m.cards_by_player.TryGetValue(slot.steam_id, out var cs) && cs != null && cs.Count > 0)
                {
                    anyCards = true;
                    break;
                }
            }
            if (!anyCards) return "<color=#666><i>(card data not recorded)</i></color>";
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
            // Dynamic body height: collapse to one line when empty, grow to fit
            // the active row count otherwise. Was a fixed 160px / 8-row block
            // that left a wall of whitespace when 0-2 people were queueing.
            float perRow = 18f;
            int newH;
            if (n == 0)
            {
                UIFactory.SetText(header, $"<b>{label}</b>  <color=#888>(empty)</color>");
                UIFactory.SetText(body, $"<color=#888>No one in {label.ToLower()} right now.</color>");
                newH = 22;
            }
            else
            {
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
                newH = (int)(n * perRow + 6);
            }
            // Push the new prefH onto the body's LayoutElement so the parent
            // VLG resizes the panel to match. Keeps the wasted space out of
            // the queue panel area when ~0-3 people are queueing.
            var bodyComp = body as Component;
            if (bodyComp != null)
            {
                var le = bodyComp.gameObject.GetComponent(UIFactory.tLE);
                if (le != null)
                {
                    UIFactory.tLE.GetProperty("preferredHeight", BindingFlags.Public | BindingFlags.Instance)?.SetValue(le, (float)newH);
                    UIFactory.tLE.GetProperty("minHeight",       BindingFlags.Public | BindingFlags.Instance)?.SetValue(le, (float)newH);
                }
                var rt = bodyComp.GetComponent<RectTransform>();
                if (rt != null) rt.sizeDelta = new Vector2(rt.sizeDelta.x, newH);
            }
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
            sb.Append($"{ReadyTag(poll.my_ready)}<b>YOU</b>");
            if (poll.teammates != null)
                foreach (var t in poll.teammates)
                    sb.Append($", {ReadyTag(t.ready)}{Trunc(t.display_name, 16)} {FmtMemberRating(t)}");
            sb.Append("\n<color=#FF6688>Opponents:</color> ");
            if (poll.opponents != null)
            {
                bool first = true;
                foreach (var o in poll.opponents)
                {
                    if (!first) sb.Append(", ");
                    sb.Append($"{ReadyTag(o.ready)}{Trunc(o.display_name, 16)} {FmtMemberRating(o)}");
                    first = false;
                }
            }
            return sb.ToString();
        }

        // Per-slot ready/pending tag shown in front of each player name in the
        // 2v2 lock-in prompt so all 4 can see who they're waiting on.
        private static string ReadyTag(bool isReady)
        {
            return isReady ? "<color=#44FF66>[R]</color> " : "<color=#888>[ ]</color> ";
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
