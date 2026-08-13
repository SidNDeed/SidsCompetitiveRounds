# How GROW works

A full breakdown of the GROW card — the base-game formula, why it used to depend on
your frame rate, what actually raises its growth rate, and what Sid's Competitive
Rounds changes about it.

All constants below were read directly out of the game's own asset files, not
guessed from the card description. See [Where these numbers come from](#where-these-numbers-come-from)
at the bottom.

---

## 1. What the card actually is

GROW is vanilla ROUNDS' `TrickShot` component. When you pick the card, an object
called `A_Grow` gets attached to every bullet your gun fires. That object carries
`TrickShot`, and `TrickShot` runs once per rendered frame while the bullet is in
the air.

There is exactly **one** `TrickShot` in the entire game, and only the GROW card
references it. Nothing else in ROUNDS grants this effect.

## 2. The per-frame formula

Every frame the bullet is alive, `TrickShot` does this:

```
Δd     = distance the bullet moved since the last frame
factor = 1 + Δd × frametime × scale × multiplier

damage *= factor
shake  *= factor
```

Then, once the bullet has travelled **40 units**, the component deletes itself and
growth stops. Damage stays at whatever it had grown to.

The three constants:

| Symbol | What it is | Value |
|---|---|---|
| `multiplier` | `TrickShot.muiltiplier`, fixed on the prefab | **4.0** |
| `scale` | the growth object's `localScale.x`, set when the bullet spawns | **1 per copy of GROW** |
| window | `TrickShot.removeAt` — distance after which growth stops | **40 units** |

`frametime` is ROUNDS' own scaled frame time: `Time.deltaTime × 0.85`. During
slow-motion it shrinks further, which is why Grow visibly stops growing in slow-mo.

## 3. Why frame rate mattered

This is the important bit. `Δd` is itself *speed × frametime*, so each frame
contributes roughly `speed × frametime²`. Add up every frame across the whole
flight and the bullet's **speed cancels out completely**, leaving:

> **Total multiplier ≈ e^(distance × frametime × scale × multiplier)**

Growth is *exponential in your frame time*. Not in how long the bullet flew, not in
how fast it flew — in how long each of your frames took.

Concretely: with one GROW, `scale × multiplier = 4`, so the exponent over a full
40-unit flight is `160 × frametime`.

**Total damage multiplier on a full-length shot, vanilla:**

| Your FPS | 1 GROW | 2 GROWs | 3 GROWs |
|---|---|---|---|
| 30  | ×82   | ×5,371 | ×285,016 |
| 60  | ×9.4  | ×85    | ×737 |
| 100 | ×3.9  | ×14.9  | ×56.6 |
| 144 | ×2.6  | ×6.6   | ×16.8 |
| 240 | ×1.8  | ×3.1   | ×5.5 |
| 400 | ×1.4  | ×2.0   | ×2.8 |

A cleaner way to say the same thing: **at 60 FPS you reached full-range Grow damage
in a quarter of the distance** a 240 FPS player needed. At 30 FPS, in an eighth of
it. Growth per unit of distance flown scaled directly with your frame time.

Two consequences worth knowing:

- **It's the shooter's frame rate that counts, not the target's.** ROUNDS computes
  damage on the shooting player's client and sends the finished number once. A low-FPS
  player genuinely hit harder on everyone's screen.
- **A single stutter is worth a lot.** A 200 ms hitch frame multiplies damage ×2.16
  on its own, because `Δd` and `frametime` both spike together in the same frame.

## 4. What raises the growth rate

Only **one** thing: **how many copies of GROW you own.**

The growth object's `localScale.x` is set once, when the bullet is created
(`Gun.cs`):

```csharp
localScale *= (1 - scaleFromDamage) + damage/55 × scaleFromDamage;   // scaleFromDamage = 0 → no effect
if (scaleStacks) localScale *= 1 + stacks × scaleStackM;             // scaleStacks = true, scaleStackM = 1.0
```

The card's spawn entry ships `scaleFromDamage = 0`, `scaleStacks = true`,
`scaleStackM = 1.0`. So `scale` comes out as **1 + stacks**, and `stacks` is
(copies of GROW − 1). One GROW → scale 1. Two → scale 2. Three → scale 3.

Because `scale` sits in the *exponent*, each extra copy raises the whole thing to
the next power:

> **N copies of GROW = (one-copy multiplier) ^ N**

Check it against the table: at 240 FPS one GROW is ×1.76, and 1.76² = 3.11, 1.76³ = 5.47.
Exactly the 2- and 3-copy columns. That's why stacked Grow feels so absurd — it's not
additive, it's a power.

### What does *not* raise it

- **Bullet size.** The growth object reads its *own* local scale, and it only carries
  a Transform and `TrickShot` — nothing that copies the bullet's size onto it. Making
  bullets bigger changes nothing about the growth rate.
- **Bullet damage.** The engine *has* a hook for this (`scaleFromDamage`), but GROW
  ships it at zero. Damage cards do not make Grow grow faster.
- **Bullet speed.** It cancels out of the total entirely. A faster bullet covers the
  40 units in fewer frames, each contributing proportionally more — the product is
  the same.
- **Fire rate, gravity, bounces, anything else.** None of them feed `scale` or
  `multiplier`.

**Important distinction:** damage cards don't change Grow's *rate*, but they absolutely
change the *result*, because Grow is a multiplier applied on top of whatever damage the
bullet already had. Grow ×9 on a 55-damage bullet is 495; Grow ×9 on a bullet you've
buffed to 90 is 810. The rate is fixed; the base it multiplies is not.

## 5. What Sid's Competitive Rounds changes

The mod replaces the single `frametime` read inside `TrickShot` with a fixed constant:
`0.85 / 240` — one frame at 240 FPS. Nothing else in the card is touched. The 40-unit
window, the stacking behaviour, slow-motion pausing growth, the sound, the trail — all
still vanilla.

The result is that **every player gets what a 240 FPS player used to get**, regardless
of the frame rate they actually run:

| Copies of GROW | Normalized multiplier (full 40-unit flight) |
|---|---|
| 1 | ×1.76 |
| 2 | ×3.11 |
| 3 | ×5.47 |

Growth is now purely a function of how far the bullet flew. At shorter ranges you get
proportionally less — roughly ×1.15 at 10 units, ×1.33 at 20, ×1.53 at 30, ×1.76 at 40.

The card is still strong and still rewards long shots and stacking. It just no longer
pays you for having a worse computer.

*(Small residual, in the honest direction: the frame-by-frame product isn't perfectly
partition-independent, so a player on very coarse frames grows a hair **less**, never
more.)*

## 6. Where the normalization is active

**Active:**

- Queue-matched ranked 1v1
- 2v2, 1v2, FFA and hosted-lobby rooms
- Sync tournament rooms
- Private / room-code / quickplay games where **every** player had Ranked enabled at
  the moment they launched the game

Mode rooms (queue, tournament, hosted lobbies) apply it regardless of your 1v1 Ranked
toggle — entering the mode is that mode's consent.

**Not active (fully vanilla Grow):**

- Any room containing a player without the mod
- Any room containing a player on a mod version that predates the fix — mixed-version
  rooms stay vanilla **on every seat**, never split rules
- Private / quickplay rooms where a player had Ranked off when they connected
- The offline sandbox

It is always whole-room, all-or-nothing. Nobody is ever playing by different Grow rules
than the person shooting at them. Each bullet also locks its decision on its first
frame, so nothing can flip mid-flight.

Shipped in **v1.38.1**.

## 7. A note on range and FFA

The 40-unit growth cap is only reached on genuinely long shots — most engagements end
well before that, so real-game multipliers usually sit below the table maximum. That
also means FFA's larger maps (which scale up with lobby size) let more shots reach full
growth than a standard 1v1 map does.

---

## Where these numbers come from

Everything above was read out of the shipped game rather than inferred:

| Value | Source |
|---|---|
| `muiltiplier = 4.0`, `removeAt = 40.0` | `TrickShot` component on the `A_Grow` prefab, `sharedassets0.assets` |
| `scaleFromDamage = 0`, `scaleStacks = true`, `scaleStackM = 1.0` | the GROW card's `Gun.objectsToSpawn` entry, same file |
| growth object has no size/damage inheritance | `A_Grow` carries only a Transform and `TrickShot` |
| only one growth source in the game | one `TrickShot` component across every asset file, referenced only by the GROW card |
| per-frame formula, 40-unit cutoff | `TrickShot.Update` |
| how `scale` is set at spawn | `Gun.cs` projectile-object attach block |
| `frametime = Time.deltaTime × 0.85` | `TimeHandler.Update` |

Multipliers in the tables are the real frame-by-frame product (which also accounts for
the engine clamping bullet movement to 0.02 s per frame), not just the exponential
approximation — the two agree within a few percent everywhere except the extreme
low-FPS corner, where the exponential form overstates it.

The mod's side lives in `plugin/VanillaFixes.cs` (`GrowNormalize` / `GrowFpsNormalizePatch`).
