# Bug 389 client, round 8 - the findings this round answers

The round-7 gate returned a NO-GO: 0 HIGH, 1 MEDIUM, 9 LOW. This file holds a
body for EVERY finding the round closes - the ten from that gate, the ten its
own two cold lenses found on its own build tips, and the five the round-8 gate
returned - and it exists so the severity census in the test log can be COMPUTED
from the bodies instead of typed beside them. The round-8 gate returned a NO-GO
of its own: 0 HIGH, 1 MEDIUM, 4 LOW, every one of them in the test surface or in
the closure documents, and the round-9 pass answers them here by the same
numbers it received.

**The scope is the whole round, and that is CHECKED rather than promised.** The
round-8 build closed fourteen findings and wrote bodies for ten, so the derived
census read "0 HIGH, 1 MEDIUM, 9 LOW" for a round that had two MEDIUM and the log
header printed it with no scope qualifier. Nothing in the harness could see it:
the census and the bodies were two readings of ONE file. `H4` now holds this file
against the closure table `R8-CLOSURES.md`, which names by number every finding
the round closes - each closure carries a `CLOSES:` line - and requires the two
lists to be the same list. A finding closed without a body here reddens, and so
does a body naming a finding the round never closed.

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

CENSUS: 25 findings: 1 HIGH, 5 MEDIUM, 19 LOW

## The permitted staging-entry members

The members that may hold a call to a staging entry point, one per line. This is
the DECLARED list, and `H2` holds it to the collection the harness actually
builds - in both directions, so a member permitted and not declared reddens and
so does one declared and not permitted. The keys are compared with runs of
whitespace collapsed, so a respelling is not a finding.

The round-8 form of that case read the set's size off SOURCE SPELLINGS: the
parity of one assignment token and a count of `)"` inside a bounded span. A
signature extracted to a constant and named in the array enlarged the compiled
set while the case went on reporting eight, and both route sentences stayed
green. A size is not a set, and a spelling is not either.

PERMITTED-MEMBER: plugin/Plugin.cs :: private void Update()
PERMITTED-MEMBER: plugin/NativeUI.cs :: private static void MaybeRefreshOvtTab()
PERMITTED-MEMBER: plugin/NativeUI.cs :: private static void MaybeRefreshFfaTab()
PERMITTED-MEMBER: plugin/ApiClient.cs :: public static void UpdateTeamQueuePoll(string steamId)
PERMITTED-MEMBER: plugin/ApiClient.cs :: private static void FfaEnrollResult(bool ok, string resp, string intendedLobbyId, bool wasRecovery)
PERMITTED-MEMBER: plugin/ApiClient.cs :: public static void FfaProbeServerState()
PERMITTED-MEMBER: plugin/ApiClient.cs :: private void HandleResolveProbe(string status, string resp, string sid)
PERMITTED-MEMBER: plugin/ApiClient.cs :: public static void FfaKickFromLobby(string targetSteamId)

## What the call walker actually sees

One line per syntactic form the residuals in these documents name, with the
answer the walker gives when it is ASKED. `H5` spells each form into a snippet,
puts it to `CallSitesIn`, and holds both documents to what comes back - so a
residual describing a form the code already handles reddens instead of standing.
Round 8 said a null-conditional dot stayed invisible while the walker had
stepped over `?.` since the `LENS 5` rewrite; a false residual is worse than a
missing one, because a reader stops looking.

WALKER-FORM: ?. = SEEN
WALKER-FORM: !. = UNSEEN
WALKER-FORM: line-break = SEEN
WALKER-FORM: spaced-dot = SEEN
WALKER-FORM: type-args = UNSEEN
WALKER-FORM: alias = UNSEEN

## The blind controls this evidence set holds

One line per round, with the number of blind-control logs that round's evidence
set carries. `H6` counts the files and holds both documents to the count, so the
legend a reader uses to find the logs cannot name a set that is not there. The
round-8 legend inventoried two logs for a round that ran three.

BLIND-CONTROLS: r8 = 3
BLIND-CONTROLS: r9 = 1

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
STREAK-ROUND: R8
STREAK: 6 gate verdicts have landed no finding inside the selection method

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

### LENS 1 - `H2` read the permitted-member size off PART of the set

SEVERITY: MEDIUM

Read on the build tip. `H2`'s span opened at the first assignment to
`permittedMembers` and closed at the next brace-shaped line, which belongs to the
last block only because the other two assignments happen to be one-liners and
that one happens to come last. Reorder them, or add a fourth file's entries after
that block, and the size the two route sentences are held to is read out of a
span that no longer holds the set - while the sentences still agree with it, so
the case stays GREEN over a set it did not read. Closed by opening the span at
the DECLARATION, closing it at the first statement after the assignments, and
requiring the assignment count inside the span to equal the count in the whole
file. `wire-prosemember` reddens `H2`; `wire-proseinert` is the twin.

### LENS 2 - two counters of one thing inside the case built to hold two counts apart

SEVERITY: LOW

`H1` holds a marker count and a body count against each other, which is evidence
only while the two are taken off DIFFERENT evidence. Its first cut counted the
markers a second time, from a second copy of the rule for what a marker looks
like. Closed by one `SeverityMarker` constant, by the census returning the marker
total it has already computed, and by the BODY count staying independent because
that is the half that must be. `W28` holds the literal to one spelling;
`wire-secondmarker` reddens it, `wire-markerinert` is the twin.

### LENS 3 - the premise the bare-name rule rests on was written down, not checked

SEVERITY: LOW

`R9` admits a bare member name only in the file that declares the target, which
is complete only while no shipped file imports those members statically and none
aliases their owner. Both were true and both were stated in a comment. Closed by
a clause in the same group that reads the enumerated surface and reddens on
either construct, naming file and line. `wire-aliasusing` reddens `W25`;
`wire-aliasinert` is the twin. Its price - a legitimate static import anywhere
under `plugin/` now has to be answered - is stated in the residuals.

### LENS 4 - the two source views were one membership by accident

SEVERITY: LOW

Every reach scan read the CODE view through a `TryGetValue` whose miss was a
silent `continue`, and what made that safe was a null check a hundred lines above
on the OTHER dictionary - a guarantee kept by a mechanism nowhere near the reader
who depended on it. The closure written for it in the same pass was a second null
guard and a clause requiring the two dictionaries to hold the same count, and
NEITHER COULD FIRE; that is `LENS 6` and `LENS 9`, and the structural closure
recorded there is what actually answers this one.

### LENS 5 - a call site spelled across a line break was invisible to every call-site scan

SEVERITY: HIGH

Read on the round-8 build tip. `CallSitesIn` matched a qualified name as one
contiguous substring, so it was whitespace-tolerant between the name and its `(`
and nowhere else. The ordinary member-access continuation - the owner ending one
line and `.Member(...)` opening the next - was invisible to it and therefore to
every scan built on it: the staging surface, the route links, the file-grain and
member-grain placement of entry-point callers, and the `R9` caller bound added
this round. A second `ApiClient.Initialize` written that way inside
`CompetitiveUI.Tick` left the caller bound GREEN and absent from the printed map,
while the one-line spelling reddened; the same held for a staging entry point.
This is not a hypothetical spelling: the shipped plugin files already carry that
continuation shape in the hundreds, so the caller bound held for one of the two
spellings the codebase uses - a spelling bound of the class `#432`/`#342`/`#431`
name. Closed at the root: the last segment is found first and the qualifier is
walked BACKWARD across whitespace and its dots, so both spellings reach the same
answer, and the two remaining `IndexOf` searches of a qualified call go through
the same counter. The summary names what it still cannot see - an alias, a
static import, a generic call, a target named at run time. CORRECTED in round 9
(`R8-new-L3`): this sentence also listed a null-conditional dot, which the walker
had stepped over from the day it was written. The forms are answered by the
walker itself now, above, and not by this sentence. `wire-splitcall` and
`wire-splitentry` redden `W25`; `wire-splitinert` leaves it green.

### LENS 6 - the clause added to close LENS 4 could not fail

SEVERITY: MEDIUM

`if (surfaceText.Count != surfaceBlank.Count)` cannot be true for any input: both
dictionaries are assigned in the same iteration after both null guards, so their
counts are equal by construction. A sparse source root narrows the enumeration
itself, so both narrow together. A check that cannot fail is worse than no check,
and one added to CLOSE a finding is the finding again (`#342`/`#431`). Closed by
deleting it and removing the question instead of restating it: one read decides
both views, one pair type carries them, one dictionary holds the pairs, and `W29`
holds the structure - the pair is constructed in exactly one place and that place
is its own loader. `wire-secondsurface` reddens `W29`; `wire-surfaceinert` is the
twin.

### LENS 7 - a counter whose NAME carried a view it no longer took

SEVERITY: LOW

After the single-blanking-site change, `CountOnCodeLines` forwarded to `CountOf`
with no blanking - byte for byte the same operation under a name that asserted
otherwise, with nothing holding its callers to the cached CODE view. Passing the
PROSE text of the same file, one identifier apart and the spelling that stood
there a round earlier, would have made a count comment-sensitive again under a
case still called "read nowhere else on code lines", with the blanking-site count
unmoved and `W27` green throughout. Closed by retiring the name: the counter takes
a relative PATH and a named `SourceView` and fetches the text itself, so no caller
can hand it the wrong view, and the one caller that counts over a member BODY uses
`CountOf` directly because `MemberBody` has one view and no way to ask for the
other. `W30` requires the retired name to have no call site left and every call to
the view-taking counter to name its view. `wire-viewbyname` reddens `W30`;
`wire-viewbynameinert` is the twin.

### LENS 8 - the blind control's header claimed a sameness nobody had checked

SEVERITY: LOW

The BUILD blind control's header said the run differed from the deliverable run
only in `Program.cs`. It also used a different driver - 77 per-variant commands
and 109 result rows against 82 and 114 - because one mutant's anchor did not
exist at the tip the harness was swapped to, so the control could not have been
run with the final driver at all. The notes reconciled the gap in prose, and
109 + 3 is not 114. Every number in that header was computed and the SAMENESS was
typed, which is the one claim a reader has no way to tell apart from the derived
ones (`#302`/`#431`). Closed in two places: the offending anchor is moved to a line
that exists at the swapped-to tip, as the driver's own rule requires, so the
control runs with the SAME driver; and the assembler now computes the
substitution sentence from the sha256 of both driver copies and of both harness
copies, refuses a blind header that does not carry the rendered clause, and
refuses one whose claim disagrees with the hashes. The refusal is exercised on a
doctored invocation rather than assumed.

### LENS 9 - the guard LENS 4 added was unreachable, and the reason given for its having no mutant was refuted by the run

SEVERITY: MEDIUM

The same clause as `LENS 6`, read one step deeper. `LoadBlanked` returns null
exactly when `LoadSource` does, so the second null guard is unreachable whenever
the first has passed; and the notes justified giving the clause no mutant with
"it fires on a SPARSE source root, and the suite already runs one" - which the
suite's own log refutes, the failure string occurring zero times across the clean
run, every mutant variant and the prior-tip root. A mechanism claim that the
evidence contradicts is how the next reader builds on a mechanism that does not
exist (`#302`/`#391`). Closed by the same structural change as `LENS 6` - the
unreachable guard is deleted with the clause - and by `W29`, so the finding that
was closed without a mutant is closed with one. The refuted sentence is corrected
in the notes rather than quietly dropped.

### LENS 10 - the census was scoped to the gate's findings and said so nowhere

SEVERITY: LOW

`round-findings.md` claimed to be the one place the round's findings are written
down and declared ten findings, while four the round had found and closed in the
same pass had no body in it and were counted by neither census. The log header
printed "10 findings: 0 HIGH, 1 MEDIUM, 9 LOW" with no scope qualifier for a
round that had two MEDIUM. `N4` made an UNMARKED body a red failure so a finding
could not quietly not count; a finding written outside the file entirely still
quietly did not, which is `N4`'s defect at file scope, and nothing could see it
because the census and the bodies were two readings of one file. Closed by `H4`,
which reads the closure table's `CLOSES:` lines - an independent artifact that
names every finding the round closes - and requires that list and the bodies here
to be the same list, in both directions. Every finding of this round now has a
body above and the declared census is the twenty they produce.
`wire-closurenobody` reddens `H4`; `wire-closurebodyinert` is the twin.

### R8-new-M1 - the permitted-member size was read off source spellings

SEVERITY: MEDIUM

`H2` bounded the permitted-member declaration by two literals and read the set's
size out of the span between them: the parity of a `permittedMembers[` token and
a count of `)"`. Both are spellings, and neither is the set. A signature
extracted to a constant and then named in the array - an ordinary refactor -
enlarges the COMPILED permitted set while the count stays at eight and both route
sentences stay green, so a member could join the staging route with nothing
saying so. The clause was written that way on purpose: a wiring mutant changes
what a case READS and never what executes, so a count taken from the running
dictionary could not have been made to fail. That is a measurement chosen by its
test harness. Closed by measuring the right thing and moving the mechanism to
meet it: `H2` enumerates the collection the harness built, its size is that
collection's own `Count`, and the members are bound BOTH WAYS to the
`PERMITTED-MEMBER:` lines above - the shape `H4` already uses for closures and
bodies. `New-HarnessMutant` compiles a one-line-changed copy of the harness, so
a case that reads a running object can still be made to fail.
`harness-ninthmember` adds the ninth through an extracted constant and
`harness-memberdropped` takes a declared one out; `harness-memberswapped` renames
one so the count cannot move and only the binding can tell.
`wire-memberspacing` is the twin. The span, the parity clause and the `)"` count
are DELETED, not corrected, and `wire-prosemember` went with them.

### R8-new-L1 - the using guard read a line prefix and not a directive

SEVERITY: LOW

The premise the bare-name search rests on - that no shipped file imports the
writers' members statically or gives their owner a second name - was checked by
`StartsWith("using static")` and `StartsWith("using ")` on the trimmed line. Both
miss `global using static ...;` and `global using Alias = ...;`, and `using
static` spelled with two spaces misses too. This is not a hypothetical spelling:
`plugin/MusicEngine.cs` opens with a `global using` alias today. A guard that
holds for one spelling of a construct the tree already uses is the spelling bound
`#432`/`#342`/`#431` name, and it is the same defect `LENS 5` found in the call
counter. Closed by reading the directive as TOKENS: the line is collapsed, an
optional leading `global` is consumed, and what remains is read as `using` and
then as the rest of the directive. `wire-globalstatic` and `wire-globalalias`
redden `W25`; `wire-globalinert` adds an ordinary global using and leaves it
green.

### R8-new-L2 - the construction count was a substring count

SEVERITY: LOW

`W29` holds the scan surface to one membership by counting the literals
`new SurfaceFile(` and `new Dictionary<string, SurfaceFile>`. A target-typed
`SurfaceFile x = new(...)` - the form the language offers for exactly this
declaration - builds a second pair that neither literal can see, and so does a
qualified spelling or one extra space; meanwhile a respelling of the one real
site makes the count read zero and reddens on the typist rather than on the
structure. Closed by reading the construction structurally, through the same
boundary rule `CallSitesIn` applies to a call: `NewSitesIn` finds the `new`
keyword at its own identifier boundaries, reads the type spelling after it as a
unit - or, for the target-typed form, out of the declaration head the assignment
carries - and matches the segment as a whole identifier, with the type-argument
list telling a PAIR from a MAP of pairs. `wire-surfacetargettyped` reddens `W29`;
`wire-surfacespacing` respells the one real site and leaves it green.

### R8-new-L3 - a residual named a form the walker already handled

SEVERITY: LOW

This file and the closure table both said a null-conditional dot stayed invisible
to the call walker. The walker has stepped over `?.` since the `LENS 5` rewrite
and says so at the walk. A false residual is worse than a missing one: it tells a
reader a hole exists where none does, and the reader stops looking at the ones
that do. `H4` holds identifiers to identifiers and has no opinion about whether a
body's prose is true, and nothing else could see it while the claim was prose.
Closed by making the claim a LINE with a verdict on it and the verdict the
walker's own answer to a live probe: `H5` spells each named form into a snippet,
asks `CallSitesIn`, and requires both documents to carry every live verdict and
no other. `!.` is a TRUE residual and stays one - if the walker ever gained it,
`H5` would redden until the documents said so. `wire-formstale` restores the
stale verdict and reddens `H5`; `wire-forminert` is the twin.

### R8-new-L4 - the evidence legend inventoried two logs of three

SEVERITY: LOW

The closure table's key legend named "the two blind-control logs" and its `N6-N9`
closure said "Both blind-control log headers" for a round that ran three: a build
control, an apply control and the third the cold-lens pass added. Every other
count in these documents is read out of its artifact; this one was typed, which
is the one a reader cannot tell from the derived ones. Closed by deriving it from
the FILES: `H6` counts the blind-control logs present in the round's evidence set,
per round, and holds both documents to that count in both directions, so a legend
naming a set that is not there reddens. The evidence set is an input and an absent
one is a FAILURE, never a skip. `evidence-logrenamed` takes a log out of the set
and reddens `H6`; `evidence-otherfile` renames one WITHIN the set - the count is
of files, not of names - and leaves it green.
