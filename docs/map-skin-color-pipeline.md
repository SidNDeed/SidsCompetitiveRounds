# Map skin colours: what actually paints the screen, and every knob

Written 2026-08-20 alongside the bug 249 fix. Read this **before** touching map skin
colours. Four previous rounds of background work were confident and wrong because they
tuned constants against a pipeline nobody had actually mapped; this file is that map.

The short version: **the map background is the background camera's clear colour, and in
vanilla that clear is pure red.** Everything else follows from that.

---

## 1. What renders a frame

Read out of `Rounds_Data/level0`, not inferred:

| | MainCamera | LightCamera |
|---|---|---|
| depth | +1 (draws second) | −1 (draws first) |
| clear | **Depth only** | **SolidColor `RGBA(1, 0, 0, 0)`** |
| culling mask | 2522423 — **excludes layer 9** | 512 — **only layer 9** |
| targetTexture | null | null (renders to the screen) |
| PostProcessLayer volume | 0x100 → layer 8 → `Post_Main` | 0x200 → layer 9 → `Post_Background` |

`Post_Background` is the GameObject that carries `ArtHandler`, and `ArtHandler.volume` is
its `PostProcessVolume`. So:

> **The art profile grades LightCamera — the camera whose clear is pure red.**

Layer 9 (everything the background camera can draw) contains: the `SFLight`,
`ArtHandler.m_background` (= `BackgroudParticles` and its seven children), and
`Post_Background`. Each art's `parts[]` contributes exactly **one** layer-9 system —
`Clouds` for `arts[0..6]`, `FireClouds` for `arts[7],[8]`. Every other art part
(`Sky`, `SkyBG`, `Paint`, `Samsung`, `NightSky`, `Purple pink`, the Rainbow parts) is
**layer 14**, drawn by MainCamera in front, and graded by `Post_Main`.

`Post_Main`'s `Default` profile grades everything MainCamera draws:
gain `(1.00, 0.644, 0.309)`, postExposure **+1.50 EV** (×2.83), contrast +45, ACES.
That is vanilla, it applies to players and cards too, and we do not touch it — but every
colour we choose has to survive it.

### How vanilla turns red into a sky

Every vanilla art profile recolours the red canvas with a big **`hueShift`** plus a deep
negative exposure, in HDR with the ACES tonemapper. Not one of them overrides
`colorFilter`:

| art | hueShift | postExposure |
|---|---|---|
| Sky | −61° | −2.98 EV |
| Gold | −52° | −3.04 EV |
| Poison | −95° | −5.00 EV |
| Soviet | −48° | −2.21 EV |
| Sweden | −65° | — |
| RainbowSequence | −85° | −2.96 EV |

**That is the whole background colour system.** Bug 249 was that our clone deleted that
ColorGrading and replaced it with one driven by `colorFilter` — a per-channel *multiply*.
Against `(1,0,0)` the green and blue of every designed background are multiplied by zero,
so all 23 skins collapsed onto one red that differed only in brightness. Measured proof:
Abyss ("near-black blue") rendered `(0.78, 0.15, 0.60)` magenta before the fix and
`(0.02, 0.24, 0.59)` blue after, same build, one line of difference.

---

## 2. The levers we actually own

In render order, all in `Plugin.cs` `MapPhysicalColorPatch` unless noted:

1. **`ApplyCameraBackground`** — paints LightCamera's clear with the skin's designed
   background. **This is the dominant lever.** Preserves the camera's vanilla **alpha 0**;
   writing alpha 1 is what learning #119 actually recorded going wrong.
2. **`ApplyLighting`** — `SFLight._color` and `SFRenderer.ambientLight`. The scene
   composites as `sprite × lightmap`, so this multiplies every lit sprite.
3. **`TintArtBackground`** — the seven `m_background` children (layer 9).
4. **The art-particle pass** in `ApplyPhysicalTintsForSku` — backdrop systems (layer 9)
   take the designed background; wall systems (layer 14) take the primary/secondary
   two-tone. Classification is by the background camera's **culling mask**, never by
   particle bounds (bounds breathe frame to frame and every system measures 91–130 units).
5. **The ColorGrading clone** in `CustomMapColors.BuildOrGetClone`.

**Retired, do not resurrect:** `TintBackdropQuads` (never matched a backdrop; its only real
hits were Homing bullet sprites and the card-choice face) and the `OutOfBounds/` pass
(learning #118 — those are the players' warning effects).

---

## 3. Every knob

### Per skin — `CustomMapColors.cs`

| knob | what it does |
|---|---|
| `MapBlockColor` | primary wall colour, on layer-14 art slabs |
| `SecondaryColor` | second wall colour, alternating by part index |
| `Sparkle` | premium glint endpoint (gilded / platinum / aurora) |
| `_backgroundColors[sku]` | **the background.** Drives the camera clear, the SFSS light, the m_background tint and the layer-9 backdrop systems |
| `Configure`'s `postExposure` | the background **mood/brightness** band, −0.30 (light) to −0.72 (dark) |
| `NEUTRAL_SKUS` | skins that are *designed* grey and must render grey |

> ⚠ `postExposure` does nothing *through the grading* — we force `LowDefinitionRange`, and
> Unity's `RenderLDRPipeline2D` never sets `ShaderIDs.PostExposure`. It is honoured because
> `GetBackgroundExposureMultiplier` reads it and bakes `2^EV` into the camera clear instead.
> Change the preset value and the background brightness moves; the grading is not involved.

> ⚠ `NEUTRAL_SKUS` is an explicit list on purpose. Two rounds of threshold-guessing got it
> wrong in both directions — a primary-only spread test called **Blackwood** grey and
> flattened the authored −26 its ember backdrop needs; tightening it to also require a
> neutral background then excluded **Platinum** and lost its cold-metal −55.

### Global — `Plugin.cs`

| knob | value | why |
|---|---|---|
| `CLEAR_GAIN_COMP` | `0.48` | the clear passes through our colorFilter (~0.55) and then Post_Main's +1.5 EV; this cancels the net gain so the screen lands on the authored value |
| backdrop lift band | `0.19 + 0.15 × lum` | measured: at the old `0.45–0.80` band a designed `(0.62,0.50,0.40)` came out of the tonemapper at `(0.87,0.73,0.58)`, a washed cream |
| `NEUTRAL_CORRECTION` | `(0.563, 1.000, 1.277)` | **measured, not modelled** — see below |
| `GAIN_COMP_STRENGTH` | `1.00` | master scale on the neutral correction |
| `NEUTRAL_LUM_FULL` | `0.35` | full correction from this luminance up, proportionally less below |
| `MapTransitionGuardSec` | `2.00` | **do not touch** — learnings #45/#85 |

### The neutral correction, and why it is measured

`Post_Main`'s authored gain is `(1.00, 0.644, 0.309)`, and **inverting those numbers
overshoots** — the correction reaches the screen through the SFSS lightmap and an ACES
tonemap with contrast +45, both of which compress it, and the green channel barely responds
at all. Inverting the authored gain pushed Monochrome past neutral into lavender.

The shipped factors were solved from the render: Monochrome measured `(0.79,0.69,0.61)`
with no correction and `(0.65,0.67,0.83)` at the authored inverse, which gives the
per-channel response, and `(0.563, 1.000, 1.277)` is what puts all three channels on the
green channel's level.

Three rules fell out, and all three are load-bearing:

- **Apply the inverse exactly once per path.** The scene multiplies sprite × lightmap, so
  correcting both the surface colour *and* the light applied it twice. With SFSS lighting
  ON the light carries it; with lighting OFF the light is disabled, so
  `CompensateSurfaceIfUnlit` moves it onto the surfaces. Never both.
- **Scale by luminance.** The cast is proportional to brightness. Charcoal was already
  neutral on its own (0.034 spread) and a flat correction pushed it to 0.116 blue.
- **A bright neutral is physically uncorrectable.** Surviving a 0.309 blue gain needs blue
  at 3.2×, so anything above ~0.31 clips. Capping it instead just rails the colour to white
  — "neutral" only by accident.

---

## 4. How to re-tune, repeatably

The broadcast account owns no map colours, so before this there was no way to look at a
skin on the seat that renders the stream. There is now:

1. Set `[Broadcast] TestMapSkin = mapcolor_<name>` in `BepInEx/config/com.competitiverounds.mod.cfg`
   (or `cycle` to exercise the spectator auto-cycle). **Broadcast identity only** — it is
   not a free-cosmetics switch, and it grants nothing server-side.
2. Launch, go **LOCAL → SANDBOX**.
3. Screenshot and sample the sky. **Measure `max(r,g,b) − min(r,g,b)`, never `r − b`** — the
   r−b metric reported Monochrome as fixed while it was visibly lavender, because green had
   dropped out from under both ends.
4. **Clear `TestMapSkin` when you are done.** It pins the skin.

The log proves the pipeline from one session without screenshots:

| line | proves |
|---|---|
| `[MAPCOLOR-CAMS] painted '<cam>' clear for <sku>` | the canvas is being repainted per skin |
| `[MAPCOLOR-CG] <sku> (settled) on '<layer>'` | the **live bundle** values — the only place grading residue is visible |
| `[MAPCOLOR-L9] <sku>: N live background system(s)` | whether layer 9 still has a renderer (`size=0x0` is ambiguous; `activeInHierarchy` + `particleCount` is not) |
| `[MAPCOLOR-CLASS] '<part>' layer=N → BACKDROP\|wall` | the backdrop/wall split |

### Measured reference (broadcast seat, sky spread)

| skin | before bug 249 | after |
|---|---|---|
| Monochrome | 0.175 (warm beige) | 0.066 |
| Platinum | 0.186 | 0.106 |
| Charcoal | 0.034 | 0.051 |
| Magma / Abyss / Mint / Soft | — | unchanged |

---

## 5. Traps

- **`LastMapStartTime` lies.** It is the *previous* map's stamp until the incoming
  `Map.Start` writes it, and ROUNDS fires `NextArt` from `MapTransition`'s own
  `switchMapEvent` — so a "am I mid-transition" test built on it answers **false** inside
  the window it protects. Use `MapPhysicalColorPatch.InMapTransition()`, which leads with
  the game's own `MapTransition.isTransitioning`.
- **`Input.GetKey` is key *state*, not call *origin*.** Holding Shift while the game fires
  its own art change is indistinguishable from a deliberate press.
- **Arts share particle systems.** `Clouds` belongs to seven arts, `FireClouds` to two, and
  those are each art's only layer-9 renderer — so "turn the other arts off" switches off the
  live skin's own backdrop unless you protect the base art's set first. `SetSpecificArt(string)`
  breaks on the **first** name match, and `arts[]` has duplicates (two `Gold`, two `Poison`).
- **`Instantiate(PostProcessProfile)` is shallow.** The clone gets a new settings *list*
  holding the *same* ScriptableObjects as the on-disk art. Copy each element, the way
  Unity's own `PostProcessVolume.profile` getter does.
- **Unity never resets a post-process bundle** whose base setting is disabled, which is all
  of them (`PostProcessManager.ReplaceData` guards on `enabled`, which defaults false). Any
  ColorGrading parameter you do not override keeps whatever profile last wrote it — forever.
  Assert the whole set.
- **Anything touching particles must be deferred** past the transition (learnings #45/#85).
  That includes restores and the flat backdrop, not just tints.

## 6. Known residuals

- The vanilla colour caches are unbounded and keyed by Unity instance id. Growth over a long
  broadcast, not a correctness bug — 2022.3 does not recycle ids within a session.
- Live particles of a gradient-mode system are left to age out on a custom → vanilla switch
  rather than being flattened to one sampled colour, which would be a different kind of damage.
- The first two maps of a spectator sitting can both render cycle entry 0 (cosmetic, and
  documented at the cycle code).
