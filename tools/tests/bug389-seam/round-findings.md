# Bug 389 client, round 7 - the findings this round answers

The round-6 gate returned a NO-GO. This file is the ONE place the round's
findings are written down, and it exists so the severity census in the test log
can be COMPUTED from the bodies instead of typed beside them.

The round-6 log's header said "two MEDIUM, five LOW" while its own seven bodies
read three MEDIUM and four LOW. Every other number in that header was counted
from the run; that one was typed, and a typed number standing beside derived
ones is the one a reader cannot tell apart. `H1` in `Program.cs` reads the
`SEVERITY:` marker on each body below, derives the census, and fails if the
`CENSUS:` line disagrees with what the bodies say - so the line a reader sees
cannot drift from the bodies it summarises.

One marker per finding. The total is derived too, so a body added without a
marker changes the total rather than quietly not counting.

CENSUS: 7 findings: 0 HIGH, 1 MEDIUM, 6 LOW

### F1 - the staging merges' downstream relation is asserted by a count

SEVERITY: MEDIUM

`W25` said the three staging merges are downstream of `ApiClient.Initialize`,
but its executable condition only COUNTED three calls, and `W25c` only LOCATES
that call inside `DoInitialize`. Where a thing is is not when it runs, so the
check could not reject a source change that makes a staging member reachable
before initialisation. Closed by the R1-R5 clauses inside `W25`, with
`wire-stageabove` and `wire-stagecaller` as the two reddening mutations and
`W23` as the inert twin for both. Distinct from the disclosed
Awake-before-the-first-frame premise, which stays OPEN.

### F2 - a deconstruction assignment reads as a read

SEVERITY: LOW

The every-write, ANY-spelling classifier did not recognise a legal
DECONSTRUCTION assignment targeting a monitored field: the identifier is
followed by `,` or `)` and never by an operator, so `ClassifyWrite` filed it as
a read and both `W23` and `W25` passed over it. The project sets
`LangVersion` `latest`, so the form compiles today. Closed by
`DeconstructionRhs`, with `wire-deconstructwrite` planting one in the declining
branch.

### F3 - three views of one source

SEVERITY: LOW

`W7a-c` and `W25` counted raw call text; `CallsTo` excluded only whole-line
comments; the member anchors used raw `CountOf`. Three readings of the same
file, so a live call could be lost while its spelling survived inside a block
comment and every counter went on printing the same number. Closed by the single
comment-blanked, offset-preserving CODE view that every code counter and every
anchor now reads, with `wire-blockcommentcall` as the reddening mutation.

### F4 - the gold provenance pointer names the deletion table

SEVERITY: LOW

The residual lead and the `L7` body pointed at section 14f for the gold answer.
14f is the DELETED-MECHANISM table; the answer - the grep, the buckets and the
two expiry conditions - is in 15f. A reviewer following the pointer landed on
unrelated evidence. Corrected at every pointer, with the legitimate 14f
deletion-register cites left alone.

### F5 - a provenance comment names a bar that was never written

SEVERITY: LOW

The new harness comments claimed round 3's bar named `FfaMode` beside the seam
and the patches. It did not: the round-5 brief, the round-5 report and all five
places the notes carry the clause say "in the seam and the patches" or "in
either file". Corrected so the text distinguishes the ACTUAL acceptance bar from
the later hazard observation that `N1b` answers.

### F6 - the severity line was typed

SEVERITY: LOW

The final log printed two MEDIUM and five LOW while the bodies read three MEDIUM
and four LOW. Closed by this file and by `H1`, which derives the census from the
markers above and fails when the declared line disagrees.

### F7 - one file called an untested step pinned

SEVERITY: LOW

Only the patches file recorded the Unity lifecycle step as an assumption. The
seam stated the ordering and said `W25` pins the premises, which `W25` expressly
does not do for that step. Closed by stating the same disclosure in both shipped
files in the same words, and by `W26`, whose negative control removes it from
one of them.
