R8 CLOSURE TABLE - part of the round-8 brief, to be RULED and not taken.
AUTHORED THIS ROUND, not a prior-round artifact.

WHY THIS FILE IS HERE AND NOT IN ai-collab. The round-7 closure table promised an
identical copy inside the repository "so the archived brief is reproducible", and
a pin-only read found neither that file nor the directory it named: the whole
ai-collab tree is gitignored, so the promise was made by a document that lived
only where it could not travel, and B19 read NOT MET on that alone (N10). The
canonical copy is therefore THIS file, tools/tests/bug389-seam/R8-CLOSURES.md,
tracked beside the harness it describes, so every clone and every pin built from
the tip carries it by construction rather than by somebody remembering to copy
it. Two published copies are made from it, byte for byte: one at
ai-collab/bugs/BUG389-R8-CLOSURES.md, the path the round-8 brief cites, and one
at REVIEW-INPUT/R8-CLOSURES.md inside the pin. H3 holds this file to naming all
three, so a promise a reader cannot resolve reddens instead of standing.

EVERY CLOSURE CARRIES A CLOSES: LINE, and that line is not decoration: H4 reads
these lines, reads the finding bodies in tools/tests/bug389-seam/round-findings.md,
and requires the two lists to be the SAME LIST in both directions. The build
closed fourteen findings and wrote bodies for ten, so the round's own census
described a different round and nothing in the harness could see it - the
census and the bodies were two readings of one file (LENS 10).

Keys as in the round-8 brief. Every offset is at the round-8 tip. Prog =
tools/tests/bug389-seam/Program.cs, Run = its run-tests.ps1, P and S = the two
plugin/ProximityVictim files, log = bug389-r8-tests-final.log, lensprior and
applyprior = the two blind-control logs, notes = BUG389-R8-NOTES.md.

THE METHOD IS HELD AND NO PRODUCT MECHANISM CHANGED THIS ROUND. The round-7
verdict landed no finding inside the selection method - the fifth gate verdict in
a row to do so, counted from the list in round-findings.md rather than typed - and
every one of the round's twenty findings, the gate's ten and the two cold lenses'
ten, is a defect in the TEST SURFACE, in the evidence logs or in the NOTES. The
two shipped files are untouched by this round.

WHERE THE MECHANISM PROSE LIVES. Mechanism REPLACED and mechanism NOW, per
finding, are tabled in the notes at section 15m-2.

ROUND-7 FINDINGS, BY NUMBER.

N1 MEDIUM - THE ALLOWED WRITER METHODS WERE CLOSED BY OWNER AND NOT BY CALLER.
REPLACED: nothing bound the callers at all - W25c requires only that the existing
ApiClient.Initialize call SIT inside DoInitialize, R8 permits Initialize and
ProbeEndpointThenStart as writers without bounding their invocation, and
FfaProbeServerState is a permitted member absent from stageEntries so R6 never
placed its callers either. The eight-member map the run printed was evidence for
a reader and could not fail (#342/#431).
NOW: R9, in Program.cs beside R8, resolves EVERY call site of each allowed writer
and of the FFA wrapper to its enclosing member over the whole shipped assembly and
compares that set - as a set and site for site, one call per named member - with a
closed set written out in the harness. The bound set is three pairs:
  ApiClient.Initialize             <- plugin/Plugin.cs :: private void DoInitialize()
  ApiClient.ProbeEndpointThenStart <- plugin/ApiClient.cs :: public static void Initialize(string url)
  ApiClient.FfaProbeServerState    <- plugin/NativeUI.cs :: private static void MaybeRefreshFfaTab()
Two spelling rules carry the clause and both are load-bearing: a call is searched
QUALIFIED across the assembly and BARE only in the file that DECLARES the target,
because nine shipped types declare a method called Initialize and six of those
calls stand in the very member the set names; and a bare hit standing behind a '.'
is rejected, which is what BareCallSitesIn exists for - CallSitesIn accepts a '.'
because a '.' is not an identifier character, right for a qualified search and
wrong for a bare one. The printed map stays BESIDE the assertion, never instead of
it, and a second map line names the writer callers.
This closes B0, B0f and B5 ON THE SAME EVIDENCE. It does NOT close the three
disclosed OPEN PREMISES, which stay open: that Awake runs before the first tick
that can reach DoInitialize; that a call through a delegate, an event or
reflection names no member a text scan can follow; and that a request built from
an EMPTY prefix brings back no successful reply.
CLOSES: N1

N2 LOW - QUALIFIED PRE-INCREMENT, ref AND out WRITES READ AS READS.
REPLACED: the backward half of ClassifyWrite read the character immediately
before the BARE name and stopped at the '.' of a qualifier.
NOW: the backward half goes through SkipQualifierBack first, the same helper the
deconstruction recogniser has used since round 7. THE SPELLINGS IT NOW SEES: bare
and qualified, for increment and decrement in both positions, ref and out, every
compound assignment including ??=, the simple assignment and the deconstruction
target. WHAT IT STILL CANNOT SEE, unchanged and disclosed: a write through a
property setter, through an alias whose name the scan does not know, through
reflection, and behind a null-conditional '.' the walk refuses to pass because no
identifier precedes it.
CLOSES: N2

N3 LOW - ??= WAS ABSENT FROM THE CLASSIFIER.
REPLACED: the forward operator table knew ++, --, <<=, >>=, the arithmetic and
bitwise compound forms and the simple assignment, and not ??=.
NOW: ??= is classified as a compound assignment with its right-hand side, in the
same place and the same shape as the others. Seeing it is only half the closure:
the request prefix is declared with the EMPTY string, which is not null, so
`baseUrl ??= ...` reads as a writer and leaves the previous value standing. R8
therefore requires every write to that field to be a form that always retargets,
which is what makes the mutant reddenable at all rather than merely visible.
CLOSES: N3

N4 LOW - AN UNMARKED FINDING BODY WAS INVISIBLE TO BOTH CENSUSES.
REPLACED: DerivedCensus counted SEVERITY markers and derived the total FROM them,
so a body written without one moved neither number and H1 stayed green; the file
stated a total guarantee the code did not implement.
NOW: FindingBodies counts the bodies by their own ### heading, knowing nothing
about markers; H1 requires bodies == markers, NAMES any body carrying none, and
prints both counts on a NOTE line. An unreadable findings file stays a failure.
The guarantee sentence in round-findings.md is corrected to what is implemented.
CLOSES: N4

N5 LOW - THE PROMISED UNIVERSAL CACHED CODE VIEW WAS NOT WHAT EVERY COUNTER READ.
REPLACED - and this is the part to grep for, because the register entry was the
defect: SEVEN places blanked a shipped file - LoadBlanked plus CountOnCodeLines,
CallsTo, AttributesOf, WritesTo, the FFA distance count, the W25 surface map and
the MarkAttached tag count - while the register named ONE cached view read by
every code counter. The semantics agreed at that tip, so nothing was wrong; the
CLAIM was false and B0g, B16 and B21 read NOT MET on it.
NOW: one blanking site. CallsTo is DELETED and its two callers use CallsToIn;
CountOnCodeLines, AttributesOf and WritesTo are handed the CODE view and blank
nothing; the FFA count, the surface map and the tag count read LoadBlanked. W27
asserts that BlankComments has exactly ONE call site in the harness and that it
lies inside LoadBlanked - written against the CALL and not against the word,
because a declaration is not a call. The PROSE view keeps its declared purpose for
absence bounds and deleted-sentence cases. WHICH COUNTER READS WHICH VIEW is
tabled in the notes at 15m-0(c) and 15m-2. LENS 7 retires CountOnCodeLines
outright, because by then it was CountOf under a name that still promised a view.
CLOSES: N5

N6, N7, N8 AND N9 LOW - FOUR PROSE COUNTS DISAGREED WITH THEIR OWN ARTIFACTS.
REPLACED: four typed numbers - twelve BUILD blind-control rows against fourteen,
six variants called six new rows against thirteen APPLY rows, seven permitted
route members against eight, and a streak called both sixth and fifth.
NOW: each number is READ OUT of the thing it counts. H2 counts permittedMembers
out of the file's own text - over the CODE view, so a signature quoted in a
comment declares nothing - and requires both route sentences to carry that count
over the PROSE view, so a ninth member reddens the prose. H2 also counts the
STREAK-ROUND list in round-findings.md and requires the declared STREAK line to be
that length. Both blind-control log headers, table AND lead sentence, are computed
by one assembler from the rows the run produced; the assembler refuses to emit a
header whose prose and table disagree, and that refusal is exercised on a doctored
copy rather than assumed. The corrections to what section 15l said are recorded in
the notes at 15m-8. LENS 8 closes the one sameness claim in those headers that
was still typed.
CLOSES: N6, N7, N8, N9

N10 LOW - THE PROMISED REPOSITORY COPY NEVER REACHED THE PIN.
REPLACED: a closure table that promised a copy at a gitignored path.
NOW: the canonical copy is tracked beside the harness, so it rides every clone and
every pin; two published copies are made from it byte for byte; H3 holds it to
naming all three paths. See the head of this file.
CLOSES: N10

THIS PASS'S OWN COLD LENS, read on the build tip 7786d7c. Four findings, all
REAL, one MEDIUM and three LOW, applied on the tip this table describes. They are
NOT round-7 findings and are listed apart from them.

LENS 1 MEDIUM - H2 READ THE PERMITTED-MEMBER SIZE OFF PART OF THE SET. Its span
opened at one assignment and closed at the nearest brace-shaped line, which
belongs to the last block only by accident of formatting and order, so an
assignment written after that block is invisible to the very count the route
sentences are held to. NOW: the span opens at the declaration and closes at the
first statement after the assignments, and the assignment count inside the span
must equal the count in the whole file. wire-prosemember reddens H2;
wire-proseinert is the twin. The fix's own first cut spelled its needle whole in
the file it counts and reddened on that literal; the needle is in halves now and
the episode is recorded in the notes at 15m-9 rather than tidied away.
CLOSES: LENS 1

LENS 2 LOW - TWO COUNTERS OF ONE THING INSIDE THE CASE BUILT TO HOLD TWO COUNTS
APART. H1's marker count was a second copy of DerivedCensus's own rule. NOW: one
SeverityMarker constant, the census returns the marker total it already computed,
and the BODY count stays independent because that is the half that must be. W28
holds the literal to one spelling; wire-secondmarker reddens it,
wire-markerinert is the twin. That twin's anchor is re-sited this pass so the
whole driver can run against the swapped-to harness (LENS 8).
CLOSES: LENS 2

LENS 3 LOW - THE PREMISE THE BARE-NAME RULE RESTS ON WAS WRITTEN DOWN, NOT
CHECKED. R9 admits a bare name only in the declaring file, which is complete only
while no shipped file imports those members statically or aliases their owner.
NOW: a clause in the same group reads the enumerated surface and reddens on
either construct, naming file and line. wire-aliasusing reddens W25;
wire-aliasinert is the twin. Its price - a legitimate static import anywhere under
plugin/ now has to be answered - is stated in the notes at 15m-7.
CLOSES: LENS 3

LENS 4 LOW - THE TWO SOURCE VIEWS WERE ONE MEMBERSHIP BY ACCIDENT. Every reach
scan treats an absent CODE view as a SKIP, and what made that safe was a null
check on the OTHER dictionary a hundred lines up.
NOW: the closure written for it in the same pass - a second null guard and a
clause requiring the two dictionaries to cover the same count - could not fire on
any input, and the reason recorded for its having no mutant was refuted by the
suite's own log. That is LENS 6 and LENS 9, and the structural closure there is
what answers this one: one read decides both views, one pair type carries them,
one dictionary holds the pairs, and W29 keeps it that way with a mutant of its
own. The claim that this clause fires on a sparse root is WITHDRAWN.
CLOSES: LENS 4

THIS PASS'S COLD LENS, read on the build tip ed3b1e5. Six findings, all REAL,
none refuted: one HIGH, two MEDIUM and three LOW, applied on the tip this table
describes. Four of the six landed inside the round-8 build's own new code and two
of those inside the code written to CLOSE a finding, which is where confirmed
findings keep landing.

LENS 5 HIGH - A CALL SITE SPELLED ACROSS A LINE BREAK WAS INVISIBLE TO EVERY
CALL-SITE SCAN. REPLACED: CallSitesIn matched a qualified name as one contiguous
substring while its own summary called the counter whitespace-tolerant, so the
ordinary member-access continuation - the owner ending one line, .Member(...)
opening the next - was invisible to it and to R1's staging surface, R5's route
links, R6's file-grain and member-grain placement and R9's caller bound alike. A
second ApiClient.Initialize written that way inside CompetitiveUI.Tick left the
caller bound GREEN and absent from the printed map; the one-line spelling reddened.
The shipped plugin files already carry that continuation shape in the hundreds, so
the caller bound held for ONE of the two spellings the codebase uses - a spelling
bound of the class #432/#342/#431 name.
NOW: the LAST segment is found first and the qualifier is walked BACKWARD across
whitespace - a line break included, and a blanked comment with it - and its dots,
so both spellings reach the same answer; the boundary rule is applied at the FIRST
segment, so MyApiClient cannot satisfy a search for ApiClient.Initialize. The two
remaining IndexOf searches of a qualified call - the merge site inside a staging
member and the initialisation call inside DoInitialize - go through the same
counter, so no second rule can answer differently. The summary now NAMES what it
still cannot see: an alias, a static import, a generic call, a null-conditional
dot, a target named at run time. wire-splitcall and wire-splitentry redden W25;
wire-splitinert is the twin.
CLOSES: LENS 5

LENS 6 MEDIUM and LENS 9 MEDIUM - THE CLAUSES THAT CLOSED LENS 4 COULD NOT FIRE,
AND THE REASON GIVEN FOR THEIR HAVING NO MUTANT WAS REFUTED BY THE RUN.
REPLACED: surfaceText.Count != surfaceBlank.Count cannot be true for any input -
both dictionaries are written in one iteration after both guards - and the second
null guard is unreachable because LoadBlanked answers null for exactly the files
LoadSource answers null for. The notes justified the absent mutant with "the
clause fires on a SPARSE source root, and the suite already runs one"; the failure
string occurs zero times in the round's own tests log, across the clean run, every
mutant variant and the prior-r2 root.
NOW: both are DELETED and the question removed rather than restated. SurfaceFile
carries both views of one file, SurfaceFile.Load is the one guard, one dictionary
holds the pairs, and ScanField and every reach scan read that one membership. W29
holds the structure: the pair is constructed in exactly one place and that place is
its own loader, and exactly one dictionary carries the surface. wire-secondsurface
reddens W29; wire-surfaceinert is the twin. The refuted sentence is corrected in
the notes at 15m-10 rather than quietly dropped.
CLOSES: LENS 6, LENS 9

LENS 7 LOW - A COUNTER WHOSE NAME CARRIED A VIEW IT NO LONGER TOOK. REPLACED:
after N5, CountOnCodeLines forwarded to CountOf with no blanking - byte for byte
the same operation under a name that asserted otherwise - and nothing held its
callers to the cached CODE view, so passing the PROSE text of the same file, one
identifier apart, would have made a count comment-sensitive again with the
blanking-site count unmoved and W27 green throughout.
NOW: the name is retired. CountIn takes a relative PATH and a named SourceView and
fetches the text itself, so no caller can hand it the wrong view; the one caller
that counts over a member BODY uses CountOf directly, because MemberBody has one
view and no way to ask for the other. W30 requires the retired name to have no call
site left and every call to the view-taking counter to name its view in the call.
wire-viewbyname reddens W30; wire-viewbynameinert is the twin. wire-uncachedview is
re-sited to a cached read in Main, since the member it used to land in is gone.
CLOSES: LENS 7

LENS 8 LOW - THE BLIND CONTROL'S HEADER CLAIMED A SAMENESS NOBODY HAD CHECKED.
REPLACED: the BUILD control's header said the run differed from the deliverable run
only in Program.cs, and it also used a different driver - 77 per-variant commands
and 109 result rows against 82 and 114 - because one mutant's anchor did not exist
at the tip the harness was swapped to, so the control could not have been run with
the final driver at all. Every number in that header was computed and the SAMENESS
was typed, which is the one claim a reader cannot tell apart from the derived ones
(#302/#431); the notes reconciled the gap in prose, and 109 + 3 is not 114.
NOW: the offending anchor is moved to a line that exists at the swapped-to tip, as
the driver's own rule already required, so every blind control runs with the SAME
driver as the deliverable run; and the assembler computes the substitution sentence
from the sha256 of both driver copies and both harness copies, refuses a blind
header that does not carry the rendered clause, and refuses one whose claim
disagrees with the hashes. The refusal is exercised on a doctored invocation.
CLOSES: LENS 8

LENS 10 LOW - THE CENSUS WAS SCOPED TO THE GATE'S FINDINGS AND SAID SO NOWHERE.
REPLACED: round-findings.md claimed to be the one place the round's findings are
written down and declared ten, while four findings the round had found and closed
in the same pass had no body in it and counted in neither census; the log header
printed one MEDIUM for a round that had two, with no scope qualifier. N4 made an
UNMARKED body a red failure; a body written outside the file entirely still quietly
did not count, which is N4's defect at FILE scope.
NOW: H4 reads the CLOSES: lines of this table - an artifact independent of the
findings file - and requires that list and the bodies to be the same list in both
directions. Every finding of this round has a body, and the declared census is the
twenty they produce. wire-closurenobody reddens H4; wire-closurebodyinert is the
twin.
CLOSES: LENS 10

B14b STAYS OWED and is never claimed here.
