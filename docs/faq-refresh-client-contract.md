# The FAQ refresh — the client half, owed to the client lane

The FAQ refresh ships as a BACKEND change: the Discord answers, `docs/FAQ.md`, the
channel-post bus that corrects an already-posted sheet in place, and the portal's
i18n keys. Three of its corrections and one of its constants have a twin in
`plugin/`, and NONE of those twins moves with it — `plugin/` and `tools/` belong
to the client lane, and a second edit from the backend branch could only collide
at merge:

    plugin/InfoLibrary.cs         three article corrections (§1 below)
    plugin/I18nSourceKeys.g.cs    regenerated from the corrected sources (§2)
    plugin/I18nCatalogues.cs      four locales for the three new keys (§2)
    tools/i18n_source.json        the EXTRACTION OUTPUT of the files above, so
                                  editing it without re-running the extractor
                                  would leave the tree asserting an extraction
                                  its own inputs no longer produce (#432)
    plugin/NativeUI.cs            an upload refusal quoting a limit it does not
                                  enforce (§3)

**This file is the specification of that owed work, and it is TRACKED on purpose.**
Four shipped files point the reader here — `backend/api/main.py`,
`backend/sql/340_i18n_keys_item11.sql`,
`backend/sql/341_seed_machine_translations_item11.sql` and
`backend/tests/test_faq_surfaces.py` — and `backend/tests/fixtures/faq_claims.json`
records the same items as `owed_to_client_lane`. A pointer into a gitignored
scratch directory resolves to nothing on every other clone, which would leave the
backend shipping while claiming its twin was "recorded" and no tracked artifact
going red. Nothing in the backend's tests fails if the work below is never done —
which is the whole reason it is written down rather than described as handled
(#302).

Everything below is stated as before -> after plus the code the corrected text is
anchored on.

---

## 1. `plugin/InfoLibrary.cs` — three article edits

### 1a. Ranked 1v1 article — the lone-room warning

BEFORE

    - If your opponent never arrives: a warning at 25 seconds, then an automatic return to the menu at 60.

AFTER

    - If your opponent never arrives: a warning at 15 seconds, then an automatic return to the menu at 60.

ANCHOR: `plugin/GameStateWatcher.cs`, `warnAfter` — a room that is none of
tournament / FFA / ovt / team (i.e. the 1v1 queue room this article is about)
warns at **15** s. The comment beside it records the Sept 6 move from 25 s to 15 s
(bugs 335/340); the article was never updated with it. `bailAfter` is 60 s for the
same room, which the sentence already stated correctly.

### 1b. Economy article — the 500 g and 300 g tier lines

BEFORE

    - <color=#7FD4FF>500g</color> - Master (reach 1980), Tag Team Sweep, Rise from the Ashes, Casual Conqueror, Twins!, Immortal, Hostile Takeover, Bodycount.
    - <color=#7FD4FF>300g</color> - Stacked Deck, Flawless, Silly Drill, Into the Deep End, Century Club, Unstoppable, Party Crasher, Heartbreak, Dragoman.

AFTER

    - <color=#7FD4FF>500g</color> - Master (reach 1980), Tag Team Sweep, Rise from the Ashes, Casual Conqueror, Twins!, Immortal, Hostile Takeover, Bodycount, Sync Champion, Async Champion.
    - <color=#7FD4FF>300g</color> - Stacked Deck, Flawless, Silly Drill, Into the Deep End, Century Club, Unstoppable, Party Crasher, Heartbreak, Dragoman, Sync Finalist, Async Finalist.

ANCHOR: `backend/api/main.py`, `ACHIEVEMENT_GOLD_OVERRIDES` priced the four
tournament achievements when they shipped (Aug 31) and the article's ladder was
never extended. The labels are `ACHIEVEMENT_DEFS`' own shipped names —
`tourn_champion_sync` / `tourn_champion_async` on the 500 g line,
`tourn_second_sync` / `tourn_second_async` on the 300 g line. The server-side
twin of this list is checked by
`backend/tests/test_faq_surfaces.py::test_every_achievement_is_on_the_tier_line_that_pays_it`,
which requires the labels on a tier line to be exactly the labels
`ACHIEVEMENT_DEFS` ships for the keys priced at that tier — so the client's copy
has to carry the same two additions or the two lists disagree.

### 1c. Cosmetics article — what the artist studio accepts

BEFORE

    - An artist (a role granted in-game) submits art from the Artist tab: a PNG or animated frames, positioned on a live on-body preview with slot, scale and offset.

AFTER

    - An artist (a role granted in-game) submits art from the Artist tab: one 512x512 PNG, a GIF, or up to 16 numbered PNG frames, positioned on a live on-body preview with slot, scale and offset.

ANCHOR: `plugin/NativeUI.cs` — the uploader refuses anything whose dimensions are
not 512x512 (`w != 512 || h != 512`, checked on both the still and the animated
half), accepts a GIF, and scans at most 16 numbered frames. The old sentence
predated GIF and frame submission entirely.

---

## 2. The re-key that follows those three edits

The catalogue key IS the English source string, so each edit above orphans its
article in every locale until the key moves with it (#578; #583 — the
DLL-bundled catalogue is the artifact a player renders). The client lane's step
is therefore:

1. apply 1a/1b/1c to `plugin/InfoLibrary.cs`;
2. re-run `tools/i18n_extract.py`, which rewrites `tools/i18n_source.json`;
3. regenerate `plugin/I18nSourceKeys.g.cs`;
4. add the ES / RU / UK / SV entries for the three CORRECTED sources to
   `plugin/I18nCatalogues.cs`. Machine translations for all four locales already
   exist and do not need re-generating: they are the twelve `target` strings in
   `backend/sql/341_seed_machine_translations_item11.sql`, keyed by the same
   `key_id` 340 registers, so the catalogue entry for a locale is that file's
   row for (successor key, locale). They are unreviewed machine output — see
   §2's note on what the portal is for.

SERVER SIDE, ALREADY DONE: `backend/sql/340_i18n_keys_item11.sql`
registers the three successor keys and retires the three predecessors, and
`backend/sql/341_seed_machine_translations_item11.sql` seeds 3 x 4 = 12 locale
proposals against them. The key id is `sha1("client\0" + <english source>)[:16]`,
and 340 carries the full corrected English inline, so the ids it registers are
derived from EXACTLY the strings 1a/1b/1c produce.
`test_the_client_keys_340_registers_are_derived_from_the_text_it_carries`
re-computes all three from 340's own bodies and fails if either half moves.

CONSEQUENCE OF THE SPLIT, stated rather than papered over: between this backend
release and the client release, the three successor keys exist server-side with no
client rendering them, and the three predecessors are retired from the translator
surface. A client of any version keeps rendering its own BUNDLED text throughout,
so nothing a player sees breaks; what is lost for the length of the window is
translator work on those three articles.

---

## 3. `plugin/NativeUI.cs:9001-9002` — the PNG refusal reports a limit it does not enforce

Not part of the FAQ refresh's own diff; recorded here because it is the exact twin
of a line that release DOES fix on the server.

CURRENT (`plugin/NativeUI.cs`)

    if (bytes == null || bytes.Length > 1_200_000)
        return $"{{\"detail\":\"{label}: PNG missing or too large - 1 MB max\"}}";

REQUIRED: the message must read the value the line above enforces — **1,200,000
bytes** — as the GIF refusal at `NativeUI.cs:9075` already does for its own check.
An artist shrinking a 1.1 MB file that the client would have accepted is the cost
of leaving it.

THE SERVER TWIN IS ALREADY FIXED: `backend/api/main.py`'s
`artist_submit_cosmetic` refused over `COSMETIC_MAX_B64` while saying "1 MB max"
too; it now quotes `1,600,000 base64 characters`, and
`test_the_uploader_error_texts_quote_the_limits_they_enforce` reads that message
against its own constant. The client half is deliberately NOT asserted in the
backend's tests: asserting the text the tree still carries would PIN the defect,
and asserting only that the message sits near its check is a check that cannot
fail on the thing it exists for (#342). Nothing in the backend artifact will go
red if this line is never fixed — which is the whole reason it is written down
here.
