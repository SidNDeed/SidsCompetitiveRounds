namespace CompetitiveRounds
{
    // TOMBSTONE (Aug 19, Sid): the spectator camera is VANILLA, deliberately.
    //
    // Three generations of dynamic spectator framing lived here and were all
    // rejected on stream: model 1 (raw containment lerp) pumped, model 2
    // (grow-instantly / calm-hold shrink) danced with border approaches, and
    // model 3 (20x0.5s rolling-max window) was still "really jarring smooth
    // camera" (Sid, Aug 19: "have a static screen that doesn't move and have
    // that expand with the map for larger FFA games"). Vanilla already IS
    // that: CameraZoomHandler.Update lerps orthographicSize toward
    // Map.size once per map load and then holds, and FfaMapScale multiplies
    // Map.size in place, so large FFA maps expand the static frame for free.
    //
    // Do not reintroduce dynamic containment, smoothing, or any per-frame
    // zoom retargeting on spectator seats — motion on the broadcast has been
    // rejected twice (Aug 18, Aug 19). The accepted tradeoff: a fighter can
    // briefly leave the visible frame while alive inside the kill band
    // (design review D1 residual, ai-collab/streaming-design-review-d1.log).
    // Screen shake on spectator seats is gated separately in PerfPatches.
    //
    // The companion SpectatorSession.EndSession reset-call was removed with
    // the patch; nothing else ever depended on this file's state (verified in
    // the same review, claim 3).
}
