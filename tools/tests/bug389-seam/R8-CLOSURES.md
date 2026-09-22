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

Keys as in the round-8 brief. Every offset is at the round-8 tip. Prog =
tools/tests/bug389-seam/Program.cs, Run = its run-tests.ps1, P and S = the two
plugin/ProximityVictim files, log = bug389-r8-tests-final.log, lensprior and
applyprior = the two blind-control logs, notes = BUG389-R8-NOTES.md.

THE METHOD IS HELD AND NO PRODUCT MECHANISM CHANGED THIS ROUND. The round-7
verdict landed no finding inside the selection method - the fifth gate verdict in
a row to do so, counted from the list in round-findings.md rather than typed - and
all ten findings are defects in the TEST SURFACE, in the evidence logs or in the
NOTES. The two shipped files are untouched by this round.

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

N3 LOW - ??= WAS ABSENT FROM THE CLASSIFIER.
REPLACED: the forward operator table knew ++, --, <<=, >>=, the arithmetic and
bitwise compound forms and the simple assignment, and not ??=.
NOW: ??= is classified as a compound assignment with its right-hand side, in the
same place and the same shape as the others. Seeing it is only half the closure:
the request prefix is declared with the EMPTY string, which is not null, so
`baseUrl ??= ...` reads as a writer and leaves the previous value standing. R8
therefore requires every write to that field to be a form that always retargets,
which is what makes the mutant reddenable at all rather than merely visible.

N4 LOW - AN UNMARKED FINDING BODY WAS INVISIBLE TO BOTH CENSUSES.
REPLACED: DerivedCensus counted SEVERITY markers and derived the total FROM them,
so a body written without one moved neither number and H1 stayed green; the file
stated a total guarantee the code did not implement.
NOW: FindingBodies counts the bodies by their own ### heading, knowing nothing
about markers; H1 requires bodies == markers, NAMES any body carrying none, and
prints both counts on a NOTE line. An unreadable findings file stays a failure.
The guarantee sentence in round-findings.md is corrected to what is implemented.

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
tabled in the notes at 15m-0(c) and 15m-2.

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
the notes at 15m-8.

N10 LOW - THE PROMISED REPOSITORY COPY NEVER REACHED THE PIN.
REPLACED: a closure table that promised a copy at a gitignored path.
NOW: the canonical copy is tracked beside the harness, so it rides every clone and
every pin; two published copies are made from it byte for byte; H3 holds it to
naming all three paths. See the head of this file.

B14b STAYS OWED and is never claimed here.
