# Bug 389 client, round 8 - the findings this round answers

The round-7 gate returned a NO-GO: 0 HIGH, 1 MEDIUM, 9 LOW. This file is the ONE
place the round's findings are written down, and it exists so the severity census
in the test log can be COMPUTED from the bodies instead of typed beside them.

The round-6 log's header said "two MEDIUM, five LOW" while its own seven bodies
read three MEDIUM and four LOW. Every other number in that header was counted
from the run; that one was typed, and a typed number standing beside derived
ones is the one a reader cannot tell apart. `H1` in `Program.cs` reads the
`SEVERITY:` marker on each body below, derives the census, and fails if the
`CENSUS:` line disagrees with what the bodies say - so the line a reader sees
cannot drift from the bodies it summarises.

One marker per finding. **A body written WITHOUT a marker is a RED FAILURE, not
a skip.** The round-7 wording here promised that the total was derived too, "so a
body added without a marker changes the total rather than quietly not counting" -
and it did not: the total was derived FROM the markers, so an unmarked body moved
neither number, `H1` stayed green and the body left the round unrecorded. `H1`
now counts the bodies a SECOND time, by their own `###` heading, by a counter
that knows nothing about markers, requires the two counts to agree, and NAMES any
body that carries none.

CENSUS: 10 findings: 0 HIGH, 1 MEDIUM, 9 LOW

## The selection-method streak

The rounds whose gate verdict landed no finding inside the selection method, one
per line. The method was established by round 3 and is unchanged since. The
streak line below is COUNTED from this list by `H2` and never typed: the
round-7 notes gave the same streak as both "sixth" and "fifth", which is what a
typed ordinal does.

STREAK-ROUND: R3
STREAK-ROUND: R4
STREAK-ROUND: R5
STREAK-ROUND: R6
STREAK-ROUND: R7
STREAK: 5 gate verdicts have landed no finding inside the selection method

### N1 - the allowed writer methods were closed by owner and not by caller

SEVERITY: MEDIUM

`R8` bounds the members that may WRITE the request prefix - `ApiClient.Initialize`
and `ProbeEndpointThenStart` - and nothing bounded who may CALL them. `W25c` only
requires the existing `ApiClient.Initialize` call to SIT inside `DoInitialize`; it
does not reject a second one elsewhere. `FfaProbeServerState` is a permitted
member of the staging entry-point set but is not itself an entry point, so `R6`
never placed its callers either. The eight-member map the run prints is evidence
for a reader and cannot fail. Closed by `R9`, which resolves every call site of
each allowed writer and of the FFA wrapper to its enclosing member across the
whole shipped assembly and compares that set, site for site, with a closed set
written out in the harness. `wire-callerextra` and `wire-probecaller` redden it;
`wire-callerinert` leaves it green. Distinct from the three disclosed OPEN
PREMISES, which this does not close.

### N2 - qualified pre-increment, `ref` and `out` writes read as reads

SEVERITY: LOW

`ClassifyWrite` has two halves. The forward half reads the operator after the
name and sees a qualified occurrence for free. The backward half - the
pre-increment, pre-decrement, `ref` and `out` forms - read the character
immediately before the BARE name, found the `.` of a qualifier and filed the
occurrence as a read, so `--ProximityVictimGate._attached` and
`out ProximityVictimGate._attached` were invisible to a pass whose case is called
"every write in ANY spelling". `SkipQualifierBack` already solved exactly this and
was wired only into the deconstruction recogniser. Closed by putting the backward
half through it, with `wire-qualifiedprefix` planting both forms in the declining
branch and `wire-qualifiedprefixinert` as the green twin.

### N3 - `??=` was absent from the classifier

SEVERITY: LOW

`ClassifyWrite` recognised `++`, `--`, `<<=`, `>>=`, the arithmetic and bitwise
compound forms and the simple assignment, and not `??=`. Closed by classifying it
as a compound assignment with its right-hand side, in the same place and shape as
the others. Seeing it is only half: the request prefix is declared with the EMPTY
string, which is not null, so `baseUrl ??= ...` reads as a writer and leaves the
previous value standing - `R8` now requires every write to that field to be a
form that always retargets. `wire-nullcoalesceassign` rewrites the TLS fallback
to `??=` and reddens; `wire-nullcoalesceinert` stays green.

### N4 - an unmarked finding body was invisible to both censuses

SEVERITY: LOW

`DerivedCensus` counts `SEVERITY:` markers and derives the total from them, so a
body added without a marker moved neither the derived census nor the declared
one: `H1` stayed green and the body disappeared. This file stated a total
guarantee the code did not implement. Closed by `FindingBodies`, which counts the
bodies by their own heading and knows nothing about markers, and by `H1`
requiring bodies to equal markers and naming any body that has none.
`wire-bodynomarker` reddens; `wire-bodymarked` stays green.

### N5 - the promised universal cached CODE view was not what every counter read

SEVERITY: LOW

The deletion register named "one cached CODE view read by every code counter" as
the replacement for the three-views defect. `LoadBlanked` did cache one, and
`CountOnCodeLines`, `CallsTo`, `AttributesOf` and `WritesTo` each blanked raw text
again, as did the FFA distance count, the `W25` surface map and the `MarkAttached`
tag count - seven blanking sites and one cache. The semantics agreed at that tip,
so nothing was wrong; the CLAIM was false, and `B0g`, `B16` and `B21` read NOT MET
on it. Closed by making it true: every counter is handed the cached view,
`CallsTo` is deleted in favour of `CallsToIn`, and `W27` asserts that a shipped
file is blanked in exactly one place and that the place is the cache.
`wire-uncachedview` reddens; `wire-viewinert` stays green.

### N6 - the BUILD blind-control lead said twelve rows over a body of fourteen

SEVERITY: LOW

The tabulated block of that header was counted from the run; the lead sentence
was typed. Corrected to the derived number, and the round-8 control logs compute
the lead sentence from the same value as the table, with the assembler refusing
to write a header whose prose and table disagree.

### N7 - the APPLY blind-control lead called six variants "six new rows"

SEVERITY: LOW

Variant count and assertion-row count are different quantities; the body carried
thirteen failed rows. Same correction and same computed-lead rule as N6.

### N8 - the route prose named seven permitted members over a set of eight

SEVERITY: LOW

`permittedMembers` holds 1 + 2 + 5 entries and two comment sentences said seven.
Corrected, and closed by `H2`, which counts the set out of the file's own text and
requires both sentences to carry that count, so a ninth member reddens the prose.
`wire-prosecount` reddens; `wire-proseinert` stays green.

### N9 - the untouched-selection streak was called both sixth and fifth

SEVERITY: LOW

The substantive claim was true and the ordinal was typed twice, differently.
Closed by the list at the head of this file and by `H2`, which counts it and
requires the declared streak to be that length. `wire-streakrow` reddens.

### N10 - the promised repository copy of the closure table never reached the pin

SEVERITY: LOW

The round-7 closure table promised an identical copy at
`ai-collab/bugs/R7-CLOSURES.md` so the archived brief would be reproducible, and a
pin-only read found neither that file nor the directory: the whole `ai-collab`
tree is gitignored, so the promise was made by a document that lived only where it
could not travel, and `B19` read NOT MET on that alone. Closed by making the
canonical copy a TRACKED file beside the harness - `tools/tests/bug389-seam/R8-CLOSURES.md` -
so every clone and every pin built from the tip carries it by construction, and by
`H3`, which holds it to naming each published copy. `wire-closuresmissing`
reddens; `wire-closuresinert` stays green.
