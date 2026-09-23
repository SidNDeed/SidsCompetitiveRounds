"""FFA: which game a report is for, and what that changes (RJ-4 + RJ-3 server).

Two live defects share one missing fact — `ffa_matches` never recorded WHICH
game of a sitting a row was. Migration 327 adds `game_number`; this file pins
what the api then does with it.

  RJ-4  The pace anchor took MAX(ended_at) over every row of the lobby, so a
        second row for one game became the next game's anchor. The verified
        2026-08-07 lobby metered a full game against the 57-second gap between
        two receipts and paid about a tenth.
  RJ-3  Two clients of one game each stamp their own start time into their own
        room id, so the room-id unique never saw them as the same game and both
        settled. The two rows name different winners.

THE RULE THIS FILE EXISTS TO PIN: the number a report settles is the LOBBY's
(`ffa_lobbies.games_played + 1`, read under the lobby row's FOR UPDATE), never
the report's — and the report room id's `_rN` tail has to AGREE with it. A tail
naming a number the lobby already holds is compared against that row; any other
disagreeing tail is refused and recorded. Nothing is ever stored under a number
the report did not name, which is what keeps the already-recorded lookup able
to find a repeat: the stored number and the named number are one number. Every
test below whose name says what a misreported number "gains" answers: nothing.

Round 2 ACCEPTED an ahead tail and stored the lobby's slot anyway. The repeat
that allowed is pinned here by name
(test_an_ahead_tail_is_refused_because_accepting_it_let_one_game_settle_twice):
the row for the game the client calls K sits at slot N, so the second client of
that same game finds neither K nor N+1 and settles the same physical game
again, rated and paid twice.

THE SECOND RULE: a game played to a target the lobby did not freeze settles,
but not with the frozen target's economics — its wagers were priced by
_ffa_field_odds for the frozen race length, so they are REFUNDED, and its
Glicko weight takes the length actually played. The row records both numbers.

THE THIRD RULE (RJ-4 round 4): every answer this endpoint gives names the
LOBBY's progress — games_played, the number the next settlement takes, and the
number of the recorded game when the answer is about one. A refusal that says
nothing a client can realign to makes the FIRST refusal poison the rest of the
sitting, because the client's counter advances at every game start and the
lobby's advances only at a settlement. The client half of that is a contract
document (ai-collab/rejoin/RJ-CLIENT-RESYNC-CONTRACT.md), not code in this
lane; the three tests under "what a client can resync FROM" are the server half
and are what make the document checkable.

THE FOURTH RULE (round 5): the two numbers an answer carries are two
INSTRUCTIONS, and `settled_game` may never equal `expected_game` — an answer
saying "this number is finished" and "name this number next" in one body makes
a client name it for the rest of the sitting. A lobby holds a row at its own
next slot whenever its counter is behind its rows, which migration 327
preserves on purpose, so _ffa_lock_lobby_slot brings the counter up to the rows
under the same FOR UPDATE.

AND THE THING ROUND 5 EXISTS FOR: round 4 closed every one of its claims with
tests that never ran the endpoint, so a tree whose submit_ffa_match raised
TypeError on its third statement reported 1708 passed. Nothing textual can tell
a live path from an unreachable one. The last section of this file awaits the
endpoint itself, and the binding sweep beside it asks the same question of the
whole module in every mode, database or not (#286/#405, #313/#340/#465).

The live tests RUN the production SQL and the production migration against a
real PostgreSQL — `_FFA_PACE_ANCHOR_SQL` carries `CAST(:g AS SMALLINT)` and an
`IS DISTINCT FROM`, `_FFA_PRIOR_GAME_SQL` carries `CAST(:g AS SMALLINT)` for
the ONE number the report named, and a bind Postgres cannot type is not a
subtle bug (#275/#448/#438). They also drive production's own lock/derive/
increment functions under two live sessions, rather than rebuilding their SQL.
Point FFA_TEST_PG_DSN at a throwaway DATABASE — the schema below drops and
recreates players/ffa_*, so never at one another session is using:

    FFA_TEST_PG_DSN="postgresql+asyncpg://postgres@127.0.0.1:5432/rjtest" \\
        python -m pytest backend/tests/test_ffa_game_number_anchor.py -q

Without it they FAIL, naming the DSN. A run that means to go without a
PostgreSQL says so out loud by setting FFA_TEST_PG_OPTOUT=1, which turns them
back into skips — the point is that nobody gets a green run they did not ask
for (#438: a feature can ship inert with perfect logs).

Named mutation controls, each applied to a copy-aside of the file, run RED, and
restored from the copy (never `git checkout --`, #290).

THE TALLY, COUNTED RATHER THAN REMEMBERED. Round 3's docstring claimed nineteen
round-3 controls; the list below carries SIXTEEN marked (r3), and the r3 gate
was right to say so. A count asserted from memory next to the list that
contradicts it is the same defect class as a comment asserting a guarantee the
code does not supply, so the numbers here are the ones in the list, counted off
it: 22 unmarked and still live (rounds 1 and 2), 1 unmarked and RETIRED because
round 4 deleted the code it mutated (prior-tail-only, annotated in place), 16
marked (r3), 15 marked (r4), 10 marked (r5), 7 marked (r6), 7 marked (r7), 8
marked (r8), 3 marked (r9), 8 marked (r10), 6 marked (r11), 8 marked (r12),
5 marked (r13), 3 marked (r14),
and
one more that is a committed test rather than a hand-run control
(backfill-neutered, at the end). The rounds in that sentence are read off the
sentence and compared with the rounds the list carries, both ways: a round
whose controls are here and whose count is not stated reds as loudly as a
count that disagrees, which is what stops the sentence going one round stale.
Those numbers count LIST ENTRIES, which is not the same set as the controls the
runner carries: one r13 entry is RETIRED IN PLACE
(terminal-walk-redirects-a-second-time, whose rule round 14 removed), so it is
still listed, still counted here, and no longer in the runner. Retiring an
entry by deleting it would leave nothing to read about a control the evidence
of two earlier rounds names.
Rounds 4 through 8's are the ones with a
NEGATIVE control — an inert edit at the same site that must leave the same
test GREEN — so each test is shown to redden for the mutation and not for any
edit at all (#391); the runner, the red line of every mutant and the
negative-control result for each are COMMITTED under backend/tests/evidence/,
beside the executed PostgreSQL runs. Round 5 named two paths under a gitignored
scratch directory instead, which is a reference nobody reading this repository
can follow — and round 6, having moved the artifacts into the repository, still
sourced the suites' failure counts from one, which is what r7's
evidence-cites-a-gitignored-path control now makes impossible.
All KILLED:

  replay-echo-call-short (r5)  the endpoint: drop `_progress` from the
                           replay-echo call, i.e. exactly the round-4 tree.
                           Run against the binding sweep AND the executed
                           endpoint test, which is the pair the round-4 suite
                           had neither half of.
  endpoint-never-called (r5)  this file: remove the one line that awaits
                           main.submit_ffa_match
  lobby-counter-not-caught-up (r5)  _ffa_lock_lobby_slot: drop the catch-up,
                           so expected_game can name a number the lobby holds
  refund-bound-off-by-one (r5)  _refund_ffa_game_bets_strict: range(
                           FFA_REFUND_MAX_BATCHES) again, i.e. round 4's
  strict-refund-asserts-service (r5)  put _assert_no_service_subject back into
                           the strict refund
  skew-refusal-bare-http (r5)  the skew-refund handler back to
                           `except HTTPException: raise`
  left-early-compared-raw (r5)  _ffa_report_contradiction: compare the raw
                           left_early flag again
  decision-from-one-reading (r5)  _ffa_report_contradiction: the leave decision
                           from the incoming report's form alone
  absent-columns-claimed-safe (r5)  _ffa_recorded_game_outcome's docstring back
                           to promising that missing columns degrade
  race-progress-from-a-bare-read (r5)  the unique-violation fallback: derive
                           its progress from a bare SELECT of games_played
                           again, so the echo's settled_game can sit at or
                           past its own expected_game

  prior-lookup-takes-the-earliest-of-a-set (r4)  _FFA_PRIOR_GAME_SQL: back to
                           a SET bind under ORDER BY ended_at
  prior-lookup-ignores-the-named-number (r4)  _FFA_PRIOR_GAME_SQL: the equality
                           becomes `OR TRUE`
  skew-refund-is-fail-soft (r4)  the endpoint: call _refund_ffa_lobby_bets for
                           this game's skew instead of the strict helper
  skew-refund-caps-at-one-pass (r4)  _refund_ffa_game_bets_strict: one batch
  later-pass-settles-a-recorded-skew (r4)  _ffa_recorded_game_outcome: drop the
                           refund verdict, so a leftover is paid at the frozen
                           price
  leave-not-compared (r4)  _ffa_report_contradiction: the leave decision
                           becomes empty
  kills-gate-narrowed (r4)  the field comparison back to kills_break_ties
  quota-before-idempotency (r4)  _quarantine_report: count the quota before the
                           on-file read, i.e. round 3's order
  variant-rows-are-not-deduped (r4)  _quarantine_on_file: drop the NULL-room
                           scan
  commit-between-the-lock-and-the-increment (r4)  the endpoint: commit between
                           _ffa_lock_lobby_slot and _ffa_advance_lobby_slot
  lobby-lock-no-for-update (r4)  _FFA_LOBBY_LOCK_SQL: drop FOR UPDATE. The r3
                           version of this control reddened a test that ran its
                           OWN copy of the statement; this one reddens a test
                           that calls the production function.
  refusal-carries-no-progress (r4)  the FfaReportRefusal handler: body back to
                           {"detail": ...} alone
  advisory-count-dropped (r4)  _ffa_poll_locked_payload: drop games_played
  trigger-raises-on-a-full-tail (r4)  327: the free-number fallback becomes a
                           raise, i.e. round 3's behaviour
  terminal-refusals-unenumerated (r4)  the endpoint: one terminal 409 raised
                           without a kept record

...and the twenty-four unmarked plus sixteen (r3) below, run as batches:

  anchor-per-row           _FFA_PACE_ANCHOR_SQL: MIN(ended_at) -> MAX(ended_at)
  anchor-includes-self     _FFA_PACE_ANCHOR_SQL: IS DISTINCT FROM CAST(:g AS
                           SMALLINT) -> IS NOT NULL
  anchor-less-than         _FFA_PACE_ANCHOR_SQL: IS DISTINCT FROM -> <
  prior-skips-invalidated  _FFA_PRIOR_GAME_SQL: add `AND invalidated_at IS NULL`
  prior-tail-only (retired)  the endpoint's _candidates set is gone in round 4
                           — the lookup keys on the ONE named number, so there
                           is no second candidate to drop. Replaced by the two
                           prior-lookup controls above.
  number-from-the-tail     the endpoint: _game_number = _room_tail
  number-rule-gone         _ffa_game_number_refusal: first line -> `return None`
  tail-ahead-accepted (r3) _ffa_game_number_refusal: drop the `tail > expected`
                           arm, i.e. round 2's behaviour restored. Run against
                           the named test AND the enumeration table.
  skew-keeps-frozen-weight (r3)  the endpoint: _ffa_rating_deltas(...,
                           _score_target)
  skew-pays-its-wagers (r3)  the endpoint: settle this game's wagers on a skew
                           instead of refunding them
  skew-not-recorded (r3)   the endpoint's INSERT: drop the two target binds
  closure-reads-the-room (r3)  _reconcile_ffa_lobby_bets: back to the `_rN` LIKE
  history-reads-the-room (r3)  get_player_bets' discriminator: back to the LIKE
  conflict-is-always-already (r3)  _quarantine_report: return "already" on any
                           ON CONFLICT, without comparing the stored payload
  variant-detail-silent (r3)  _ffa_record_and_refuse: drop the variant suffix
  replay-refusal-uncaptured (r3)  _ffa_replay_echo's roster branch back to a
                           bare 409
  game-limit-uncaptured (r3)  the game-limit branch back to a bare 409
  room-race-spends-the-report (r3)  the unique-violation fallback back to 409
  closed-lobby-one-answer (r3)  the closed-lobby branch: one 409 for all three
  optout-any-nonempty (r3)  _optout -> bool(raw), i.e. "0" opts out again
  lobby-lock-no-for-update (r3)  the endpoint's lobby read: drop FOR UPDATE
  trigger-clamps-999 (r3)  327: the sequence arm back to LEAST(tail, 999)
  postcheck-sequence-only (r3)  327: the tail assertion back to
                           `AND game_number_source = 'sequence'`
  contradiction-blind      _ffa_report_contradiction: first line -> `return None`
  kills-not-compared       _ffa_report_contradiction: drop the compare_kills arm
  shape-winner-gone        _ffa_score_shape_error: drop the unique-maximum arm
  shape-target-gone        _ffa_score_shape_error: never take the target arm
  shape-skew-refused       _ffa_score_shape_error: admissible -> (score_target,)
  bound-gate-open-coded    the closed-lobby capture gate: back to its own copy
                           of `max_rounds == _score_target`
  replay-after-the-status-gate   the endpoint: drop the replay-echo call
  capture-always-ok        _ffa_record_and_refuse: drop the `_kept not in` arm
  capture-quota-silent     _quarantine_report: the quota arm returns "recorded"
  headroom-hostile         FFA_PACE_HEADROOM = 0.01
  insert-unnumbered        submit_ffa_match's INSERT: drop `game_number`
  bets-reparse-the-room    the bet settle: re-derive game_no from the room id
  migration-no-trigger     327: the BEFORE INSERT trigger never attaches
  migration-no-not-null    327: drop `SET NOT NULL`
  migration-no-check       327: the CHECK becomes `IS NOT NULL`
  postcheck-nulls-only     327: drop the post-check's derivable-tail assertion,
                           which is the control ON the backfill-neutered test

  refund-clamps-the-delta (r6)  _return_stake_exactly: the exact subtraction
                           back to GREATEST(0, gold_spent - :amt)
  refund-class-swept (r6)  main.py: put the clamped form back at ONE of the
                           five refund sites
  variant-scan-unbounded (r6)  _quarantine_on_file: drop the variant scan's
                           `status = 'pending'` and its LIMIT
  settlement-takes-for-update (r6)  _FFA_LOBBY_LOCK_SQL back to FOR UPDATE
  settled-game-without-a-named-number (r6)  _ffa_with_settled: ignore `named`
                           and take the row's number unconditionally
  insert-failure-answers-bare (r6)  the endpoint: the non-duplicate integrity
                           arm back to a bare HTTPException(500, ...)
  binding-sweep-posonly (r6)  _binding_failures: fold posonlyargs back into
                           `positional` before the keywords are tested, and
                           make one production def positional-only

  refund-statement-never-executed (r7)  _return_stake_exactly: read the
                           RETURNING as a VALUE (`if not moved`) rather than
                           as a row, which only a live server can tell apart
  refund-refusal-kills-the-queue (r7)  _flush_lobby_bet_refunds: the refusal
                           arm back to `break`, i.e. round 6's shape
  refund-refusal-kills-the-sweep (r7)  _prune_stale_series: the mode-2 call
                           back to a bare _refund_series_bets
  wager-lock-dropped-as-redundant (r7)  place_ffa_bet: drop its own FOR NO KEY
                           UPDATE on the lobby row, on the deleted reading
                           that the settlement lock no longer excludes wagers
  relock-leaves-a-poisoned-transaction (r7)  _ffa_progress_relocked: drop the
                           rollback from its handler
  evidence-cites-a-gitignored-path (r7)  backend/tests/evidence: state a
                           committed count as a grep over an ai-collab/ path
  refusal-skips-without-ending-the-transaction (r7)  _refund_or_skip: drop the
                           rollback, so the sweep takes the next series still
                           holding this one's locks. Its test lives in
                           test_report_disconnect_durability.py, which owns the
                           prune sweep's shape -- the one control in this set
                           that names a file other than this one.

  commit-between (r8)      submit_ffa_match: `await db.commit()` between the
                           lock and the slot it consumes, which unlocks the row
                           with games_played unchanged. Described as a
                           structural assertion for four rounds and never RUN
                           as a mutation; its inert twin is a COMMENT at the
                           same site, which is the negative control that matters
                           for a test measured on comment-stripped source
                           (#441).
  settlement-lock-removed-live (r8)  _FFA_LOBBY_LOCK_SQL: the row lock comes
                           off entirely, and the LIVE two-connection contention
                           test reds -- round 7 had this one as prose saying it
                           had been hand-run.
  refusal-after-capture-reuses-stale-progress (r8)  _ffa_progress_after_capture:
                           return the caller's copy instead of re-reading the
                           lobby under a fresh lock after the capture.
  advertised-number-is-not-the-settling-one (r8)  _ffa_progress: emit
                           `expected_game = games_played`, so the number every
                           refusal advertises is one the endpoint would refuse.
  production-cites-a-gitignored-path (r8)  backend/api/main.py: put a citation
                           of the gitignored scratch back into a shipped file.
                           The forbidden path is ASSEMBLED in the runner, for
                           the same reason the evidence control assembles it.
  relock-gives-up-after-one-attempt (r8)  _ffa_progress_relocked: delete the
                           second attempt, so a re-read that failed once
                           answers with the caller's stale-low snapshot
  evidence-result-pattern-forgets-the-repin (r8)  the result pattern in
                           test_the_committed_evidence_re_derives_its_own
                           _numbers: drop the token the re-pin's own
                           result line uses, so a pattern that was WIDENED
                           is shown to still red when it stops covering an
                           artifact this directory actually holds.
  control-list-drifts-from-the-inventory (r8)  this docstring: misspell the
                           entry above by one letter, so the check that
                           every control the runner carries is named here
                           and pairs with a live test is shown to red on a
                           control that exists in the runner and nowhere
                           else.
  realignment-reuses-the-advertised-number (r9)  _ffa_replay_echo: drop the
                           field comparison, so a DIFFERENT physical game
                           delivered under an already-settled room key is
                           echoed as that game instead of refused. The
                           realignment section keyed exactly that delivery
                           there, and the room key is what stops one number
                           answering for two physical games.
  shipped-file-outside-the-swept-set (r9)  backend/Dockerfile.bot: put a
                           citation of the gitignored scratch into a shipped
                           file that round 8's three hand-written globs did
                           not read. Its point is the SET, not the line: the
                           same mutation was green for the whole of round 8.
  catch-up-log-claims-a-persisted-repair (r9)  _ffa_lock_lobby_slot: restore
                           the past-tense line that announced `games_played
                           N -> M` on a path whose transaction is never
                           committed, so a log asserting a repair the request
                           discards is shown to red.

  capture-refusal-restores-the-snapshot (r10)  _ffa_progress_after_capture:
                           catch the 503 the fresh read now raises and answer
                           from the caller's pre-capture copy instead, which
                           is the snapshot fallback put back at the one site
                           where that copy is still in scope.
  double-failure-invents-a-progress (r10)  _ffa_progress_relocked: on the arm
                           where BOTH relock attempts failed, return
                           `_ffa_progress(0)` rather than refusing -- the
                           invention the old docstring named and declined.
  vanished-lobby-invents-a-progress (r10)  _ffa_progress_relocked: the same
                           invention on the other exhausted arm, a lobby with
                           no row left to read. Two reachable states, one
                           control each: a control on one says nothing about
                           the other.
  join-payload-omits-the-advertised-number (r10)  _ffa_poll_locked_payload:
                           emit the settled count alone, so a seat with no
                           other reading has to count `games_played + 1` for
                           itself -- the arithmetic the sole-allocator rule
                           removes.
  acceptance-does-not-name-its-settled-game (r10)  submit_ffa_match: drop
                           `settled_game` from the answer that settled the
                           game, so an acceptance stops naming the number it
                           took. Its inert twin is the same call REFLOWED,
                           which is what keeps the assertion measuring a call
                           and not a line shape (#441).
  evidence-results-without-an-invocation (r10)  the suites report: replace one
                           half's command line, so a results block is left
                           with no record of what produced it. The inert twin
                           is the same line with a space added, which is still
                           a command line.
  suites-report-carries-an-underived-number (r10)  the suites report: put a
                           number into its prose that no run here can print,
                           which is the round-9 finding itself. The assembler
                           has to refuse it rather than transcribe it.
  refusal-advertises-the-number-it-just-settled (r10)  _ffa_with_settled:
                           also overwrite `expected_game` with the number the
                           answer reports as settled, so an answer names a
                           number that is already taken as the one to use
                           next. A seat deriving its key from the last
                           advertisement then keys every later report at a
                           settled number and is refused for ever, which is the
                           permanent exclusion the sole-allocator rule rules
                           out.

  evidence-scope-keys-on-the-opt-in-set (r11)  evidence_rules.scope_problems:
                           derive the newest round from the reports that
                           already declare a stdout, which is what round 10
                           did. A later round whose reports declare none then
                           moves the scope with it and is bound by nothing.
                           The rule's own fabricated directory is what reds,
                           because a directory satisfying both readings cannot
                           tell them apart.
  scope-lets-a-report-belong-to-no-round (r11)  evidence_rules.scope
                           _problems: drop the clause that refuses a report
                           whose NAME carries no round. The scope is derived
                           from the name so that no report can opt out, which
                           makes an unparseable name the same escape one
                           spelling over.
  selftest-count-is-not-derived (r11)  assemble-evidence.selftest: print the
                           check count as the constant it used to be instead
                           of the number of checks the run recorded. Its inert
                           twin is the same expression REFLOWED, so the test
                           is shown to measure a number and not a line shape
                           (#441).
  new-controls-list-credits-another-round (r11)  the previous round's
                           mutation-controls report: swap one listed name for
                           a control the inventory tags for an earlier round,
                           which is round 10's own defect. It reds in both
                           directions at once -- one name listed and not
                           tagged, one tagged and not listed.
  residual-reach-rule-admits-a-prose-count (r11)  residual_rules.reach
                           _problems: search an EMPTY remainder for a second
                           statement of the reach, so a hand-counted summary
                           beside the tags passes. Its inert twin is a comment
                           at the same site.
  invocation-frame-drops-a-known-key (r11)  evidence_rules.BETWEEN: take the
                           two frame keys this round's runner prints --
                           reports and swap -- back out of the list the
                           upward scan reads past, so a result whose command
                           IS above it is reported as carrying none. The
                           rule's own fabricated frame reds, and the negative
                           twin inside that self-test -- a frame key the list
                           has never been told about, which must still STOP
                           the scan -- proves the list is what reads past a
                           frame rather than something else. Its inert twin
                           here is a comment at the same site.

  capture-failure-503-carries-the-settled-game (r12)  _ffa_record_and
                           _refuse: move the capture-failure raise back below
                           the re-derivation and let it answer with it, which
                           puts `settled_game` on a 503 -- one response in two
                           dispositions, TERMINAL by its field and RETRYABLE
                           by its status. Its inert twin is the same detail
                           string REFLOWED across the two lines, so what reds
                           is the value the arm carries and not the shape of
                           the raise.
  recovery-re-keys-the-parked-delivery (r12)  the missed-update walk's
                           recovery rule: file the re-signed body as a SECOND
                           entry instead of re-signing the one the seat holds,
                           which is the re-keying the freeze exists to stop.
                           Its inert twin is the same statement reflowed.
  relock-takes-a-fallback-again (r12)  _ffa_progress_relocked: put a
                           `fallback` parameter back on the signature, so the
                           caller's pre-rollback copy is reachable from the
                           span again. Its inert twin is the same signature
                           reflowed across two lines.
  evidence-log-negation-admits-any-log (r12)  .gitignore: two of the
                           per-producer names back to the blanket `*.log`,
                           which admits a capture no instrument here writes.
                           Re-anchored in r13 on the exact names that replaced
                           the suffix patterns; the mutation is the one it
                           always was. Its inert twin is two of the names
                           swapped, which is the same set in a different
                           order.
  producer-stops-naming-its-capture (r12)  run-assembly.sh: drop the line in
                           which the producer names the capture it is
                           redirected into, leaving a pattern in .gitignore
                           that no committed instrument produces. Its inert
                           twin is a DOUBLED SPACE inside that line -- not the
                           line reflowed, which removes the declaration as
                           surely as the mutant does, because a declaration
                           has to OPEN its line.
  repin-names-a-capture-no-pattern-admits (r12)  repin-last.py: change the
                           name its capture_name returns, which is the value
                           that wrapper opens its log under. No pattern in
                           .gitignore re-includes the new name, so the round's
                           re-pin record could not be committed. Its inert
                           twin is the same return with the operand
                           parenthesised.
  terminal-arm-splits-into-two-exits (r12)  _ffa_record_and_refuse: give the
                           variant case its own raise, so there are TWO
                           terminal exits below the re-derivation instead of
                           one. The answers are unchanged, which is the point
                           -- what reds is the SHAPE the disjointness rests
                           on. Its inert twin is the same detail string built
                           across two lines.
  recovery-mints-a-second-parked-key (r12)  the missed-update walk's recovery
                           rule again, in the shape that does NOT crash: the
                           original entry is left reachable and a second key
                           is added beside it, so every leg runs and the key
                           set is what sees it. Its inert twin is a comment
                           at the same site.
  recovery-resubmits-the-stale-number (r13)  _recover_parked: drop the line
                           that writes the advertised number into the body,
                           so the advertisement is never taken up and the seat
                           keys its NEXT game at the number it was just refused
                           for. The leg it reds moved in round 14 -- it was the
                           redirected entry's acceptance, it is now the seat's
                           next game -- and the mutation is the one it always
                           was. Its inert twin is the same assignment with a
                           doubled space.
  terminal-walk-redirects-a-second-time (r13)  RETIRED IN ROUND 14, and named
                           here rather than deleted. It mutated the BOUND on a
                           redirect -- once per entry, terminal the second time
                           -- and the ruling removes the redirect itself, so
                           the rule it guarded no longer exists and a control
                           that cannot be re-run on the tree it certifies is an
                           assertion about a different tree. Its site is now
                           held by terminal-arm-redirects-the-refused-entry,
                           which reds on the redirect happening at all.
  evidence-log-negation-takes-a-suffix-wildcard (r13)  .gitignore: one exact
                           capture name back to the producer-suffix wildcard
                           it replaced, which re-admits every name shaped like
                           a capture under a round nothing here has run. Its
                           inert twin is two of the exact names swapped, which
                           is the same set in a different order.
  inventory-mislabels-an-inert-twin (r13)  this inventory: say the twin above
                           is a reflow, which is what it said before this
                           round -- while the runner holds a comment. The
                           executed RED and GREEN are unaffected, which is the
                           point: what reds is the LABEL an auditor reads.
                           Its inert twin is a doubled space in the same
                           sentence.
  repin-types-its-commit-trailer (r13)  repin-last.py: make derive_trailer
                           return a typed constant instead of the form the
                           branch's most recent commits carry, so a sitting
                           commits under whatever the last sitting wrote down.
                           Its inert twin is a comment at the same site.
  terminal-arm-redirects-the-refused-entry (r14)  _settled_game_disposition:
                           answer a settled-game refusal with a REDIRECT, which
                           is the rule rounds 12 and 13 stated and the ruling
                           removed. The conflicting-account walk then re-signs
                           that entry at the free number, the endpoint settles
                           it, and a SECOND row for one physical game is what
                           reds -- a second rating and a second payout. Its
                           inert twin is a comment at the same site.
  terminal-walk-keeps-the-dropped-entry (r14)  _drop_parked: return a copy of
                           the entry instead of popping it, so the terminal
                           disposition is announced and not taken. The walk
                           reports the drop it never made and the outbox still
                           holds a delivery the server has refused. Its inert
                           twin is a comment at the same site.
  refusal-keeps-nothing-for-review (r14)  the endpoint's contradiction arm:
                           raise the terminal refusal directly instead of
                           through _ffa_record_and_refuse, so the answer is
                           unchanged and NOTHING is kept. That is the whole
                           cost of the terminal disposition -- it is
                           conservative only because the payload survives for
                           an operator -- and what reds is the quarantine
                           record the walk reads back. Its inert twin is a
                           comment at the same site.
...and one more that is a COMMITTED TEST rather than a hand-run control:
  backfill-neutered        327's room_tail backfill: WHERE FALSE. See
                           test_pg_migration_327_post_check_fails_when_the_
                           backfill_is_neutered, and the negative control
                           asserting that mutation is exactly one predicate.

One control was initially LIVE and the CONTROL was the defect:
migration-no-not-null first replaced the ALTER with a comment that still
contained the words "SET NOT NULL", so the text assertion it aimed at kept
passing — it was measuring its own replacement string. Rebuilt to remove the
line, and the assertion it now reddens is an EXECUTED insert against a
disabled trigger.
"""
import ast
import asyncio
import fnmatch
import inspect
import json
import os
import pathlib
import re
import subprocess
import sys
import types
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "api"))

import main
import schemas

MIGRATION = (pathlib.Path(__file__).resolve().parents[1]
             / "sql" / "327_ffa_game_number.sql")


# ── fixtures shaped like the verified 2026-08-07 rows ─────────────────────
# lobby 0ea879a4-ff42-44c4-9473-4c58f89ef934, game 1, three players, two rows
# that disagree. Steam ids are the real ones only in shape: they are outside
# the SteamID64 space so nothing here can be mistaken for a production row.
S1, S2, S3 = "90000000000000101", "90000000000000102", "90000000000000103"

# steam -> (rounds_won, points_total, kills)
ROW_A = {S1: (4, 11, 6), S2: (1, 6, 2), S3: (5, 15, 9)}      # winner S3
ROW_B = {S1: (5, 11, 6), S2: (1, 5, 2), S3: (3, 12, 9)}      # winner S1
# A THIRD scoreboard, added in round 13 for the terminal half of the
# missed-update walk. It needs a winner neither of the other two has, because
# what that leg exercises is a body the lobby's row at the delivered number
# disagrees with -- twice, at two different numbers -- and a body that agreed
# with either row would reach the identical-body echo instead.
ROW_C = {S1: (2, 8, 3), S2: (5, 14, 7), S3: (1, 4, 1)}       # winner S2


# steam -> (left_early, absent, game_points_at_leave) for the seats that left.
# Everyone else is present, which is the three-way default below.
PRESENT = (False, False, None)


def _report(vec, winner, room="rm_211531_r1", leave=None):
    """The fields the pure helpers read off a FfaMatchReport, INCLUDING the
    leave fields: _ffa_report_contradiction asks _ffa_leave_decision what this
    report says about who played, because that decision is what the settlement
    stores in ffa_match_players.absent and acts on."""
    leave = leave or {}
    return types.SimpleNamespace(
        photon_room_id=room, winner_steam_id=winner,
        reported_by_steam_id=winner,
        players=[types.SimpleNamespace(steam_id=s, rounds_won=r,
                                       points_total=p, kills=k,
                                       left_early=leave.get(s, PRESENT)[0],
                                       absent=leave.get(s, PRESENT)[1],
                                       game_points_at_leave=leave.get(s, PRESENT)[2])
                 for s, (r, p, k) in vec.items()])


def _vec(rows, leave=None):
    """One recorded game as _FFA_PRIOR_VECTOR_SQL reads it back:
    steam -> (rounds_won, points_total, kills, left_early, absent). `leave`
    names the seats whose two stored leave columns are not (False, False)."""
    leave = leave or {}
    return {s: (r, p, k) + leave.get(s, (False, False))
            for s, (r, p, k) in rows.items()}


def _code_lines(src: str) -> str:
    """`src` with its whole-line comments removed.

    A structural assertion about what the code DOES must not be answerable by
    what a comment SAYS — in either direction. Round 3's span checks ran over
    the raw text, so a sentence quoting the very call it forbade reddened the
    test, and (the direction that matters) a comment could have supplied a
    required literal that the code no longer contained."""
    return "\n".join(ln for ln in src.splitlines()
                      if not ln.strip().startswith("#"))


def _endpoint_src():
    return inspect.getsource(main.submit_ffa_match)


# ── the number: whose is it? ──────────────────────────────────────────────

def test_the_number_a_report_settles_is_the_lobbys_own_next_slot():
    src = _endpoint_src()
    # The lock and the derivation are ONE production function, so the endpoint
    # cannot hold one without the other and a test can drive both together
    # (test_pg_two_reports_for_one_lobby_cannot_settle_the_same_number).
    slot = inspect.getsource(main._ffa_lock_lobby_slot)
    # FOR NO KEY UPDATE since round 6 (#202/#203/#207) - see
    # test_the_lobby_lock_is_the_weakest_mode_that_still_conflicts_with_itself
    # for why the weaker mode still serialises two settlements.
    assert "FOR NO KEY UPDATE" in main._FFA_LOBBY_LOCK_SQL
    lock = slot.index("_FFA_LOBBY_LOCK_SQL")
    derive = slot.index('int(lobby["games_played"] or 0) + 1')
    assert lock < derive
    assert "lobby, _expected_game = await _ffa_lock_lobby_slot(db, lobby_uuid)" in src
    assert "_game_number = _expected_game" in src
    # ...and the endpoint does not re-derive it from anything else.
    assert 'int(lobby["games_played"] or 0) + 1' not in src
    # The room tail is read, but only as a cross-check: it never becomes the
    # stored number. (Control: number-from-the-tail.)
    assert "_room_tail = _ffa_room_game_no(" in src
    assert "_game_number = _room_tail" not in src
    assert "_game_number = int(_room_tail" not in src
    # The round-1 helper that took the tail as the number is gone entirely.
    assert not hasattr(main, "_ffa_report_game_number")


def test_the_stored_number_is_the_one_the_anchor_and_the_bet_settle_use():
    src = _endpoint_src()
    derive = src.index("_ffa_lock_lobby_slot(")
    prior = src.index("_FFA_PRIOR_GAME_SQL")
    anchor = src.index("_FFA_PACE_ANCHOR_SQL")
    insert = src.index("INSERT INTO ffa_matches")
    bets = src.index("game_no = _game_number")
    assert derive < prior < anchor < insert < bets
    # The INSERT's column list carries the number, or every row written from
    # here is NULL — which migration 327's NOT NULL now rejects outright.
    # (Control: insert-unnumbered.)
    cols = src[insert:src.index("VALUES", insert)]
    assert "game_number" in cols
    assert "CAST(:gn AS SMALLINT)" in src
    # One derivation, not two: a bet settle that re-parsed the room id is how
    # game N's wagers get paid against a row stored as something else.
    assert src.count("_ffa_room_game_no(") == 1
    # ...and the straggler catch-up reads the column too, not a LIKE on the
    # room string. It asks through the ONE verdict helper now, so the typed
    # read lives there; the endpoint must still hold no second derivation.
    assert "photon_room_id LIKE :sfx" not in src
    assert "_ffa_recorded_game_outcome(" in src
    assert "game_number = CAST(:g AS SMALLINT)" in \
        inspect.getsource(main._ffa_recorded_game_outcome)


def test_every_surface_that_names_a_game_reads_the_column_not_the_room_string():
    """Controls: closure-reads-the-room, and the two history surfaces.

    Four places used to re-derive a game's identity from the report room id.
    Each one is a second derivation of the thing the column exists to hold, and
    each could disagree with the row it was describing: the closure reconcile
    would settle one game's stakes against another game's winner, and the two
    history surfaces would show them under the wrong game. The parse survives
    in exactly ONE place — the endpoint's own cross-check of the tail against
    the lobby's slot, which is the comparison, not a source."""
    whole = pathlib.Path(main.__file__).read_text(encoding="utf-8")
    # The terminal bet resolution for a closing lobby.
    rec = inspect.getsource(main._reconcile_ffa_lobby_bets)
    assert "photon_room_id LIKE" not in rec
    # It asks the row, through the one helper that decides settle-or-refund
    # for every after-the-fact resolver (round 4: a recorded config skew must
    # not be PAID by a later pass at the frozen price).
    assert "_ffa_recorded_game_outcome(db, lobby_id, int(g))" in rec
    outcome = inspect.getsource(main._ffa_recorded_game_outcome)
    assert "game_number = CAST(:g AS SMALLINT)" in outcome
    # The bet-history surface's settlement-cause discriminator.
    assert "fm2.game_number = fb.game_number" in whole
    assert "fm2.photon_room_id LIKE" not in whole
    # ...and no LIKE building an _rN suffix survives anywhere in the module.
    assert "_r' || " not in whole and "'%!_r'" not in whole
    assert "%\\\\_r" not in whole
    # The recent-matches panel keys its bet list on the row's own number.
    assert 'gno = int(r["game_number"])' in whole
    # One CALL of the room-id parse, and it is the endpoint's cross-check. (The
    # other two occurrences are the def itself and the refusal rule's docstring
    # naming its own argument.)
    calls = [ln for ln in whole.splitlines()
             if "_ffa_room_game_no(" in ln
             and not ln.lstrip().startswith(("def ", "#", "`", "-"))
             and "`tail` is" not in ln]
    # TWO calls since round 6, and the split between them is the point. The
    # NUMBER A REPORT NAMES is derived once, in _ffa_named_game_number, and
    # both the endpoint and the room-keyed replay read it from there — round 5
    # bounded the tail inline in the endpoint and never asked the question at
    # all in the replay, which is how an answer came to name a game the report
    # had not (see _ffa_with_settled). The endpoint keeps the RAW tail beside
    # it because _ffa_game_number_refusal's message distinguishes a missing
    # tail from an out-of-domain one, and `None` cannot say which it was.
    assert calls == ['    tail = _ffa_room_game_no(room_id)',
                     '    _room_tail = _ffa_room_game_no(report.photon_room_id)']
    assert calls[0] in inspect.getsource(main._ffa_named_game_number)
    # The raw tail's ONLY use in the endpoint is that refusal rule.
    endpoint = _endpoint_src()
    assert endpoint.count("_room_tail") == 2
    assert "_ffa_game_number_refusal(_room_tail, _expected_game)" in endpoint
    for user in (endpoint, inspect.getsource(main._ffa_replay_echo)):
        assert "_ffa_named_game_number(" in user
    assert "_ffa_room_game_no(" not in inspect.getsource(main._ffa_replay_echo)


def test_the_lookup_asks_about_the_number_the_report_named():
    """Controls: prior-lookup-takes-the-slot, prior-lookup-takes-either.

    The comparison has to be against the row that holds the number under
    discussion, or it is not a comparison of that game. Round 3 asked about a
    SET — the named number plus the lobby's next slot — and took the earliest
    row that came back, so a lobby holding a row at its next slot as well could
    have a report compared against a different game entirely (and, if that
    other game agreed, answered 200).

    Dropping the slot arm loses nothing: a report whose tail is not the lobby's
    next slot settles only where the lobby already HOLDS that number, which is
    exactly the row this lookup returns, and is otherwise refused by the one
    equality in _ffa_game_number_refusal."""
    src = _endpoint_src()
    named = src[src.index("_named_game = "):src.index("if _prior_game is not None:")]
    assert "_ffa_named_game_number(report.photon_room_id)" in named
    assert "_expected_game" not in named         # the slot is NOT a candidate
    # out-of-domain tails name nothing - the bound moved into the helper
    # with the derivation, so it is asserted where it now lives.
    assert "FFA_GAME_NUMBER_MAX" in inspect.getsource(main._ffa_named_game_number)
    assert '"g": _named_game' in src
    assert "game_number = CAST(:g AS SMALLINT)" in main._FFA_PRIOR_GAME_SQL
    assert "ANY(" not in main._FFA_PRIOR_GAME_SQL
    # A report that names no usable number looks nothing up; the refusal below
    # is what answers it.
    assert "if _named_game is not None:" in src


# ── what a misreported number gains: nothing ──────────────────────────────

def test_a_number_matching_the_lobbys_next_game_is_accepted():
    assert main._ffa_game_number_refusal(4, 4) is None


def test_an_ahead_tail_is_refused_because_accepting_it_let_one_game_settle_twice():
    """Control: tail-ahead-accepted.

    Round 2 accepted a tail ahead of the lobby and stored `expected` anyway.
    Walk what that bought, with the numbers: the lobby is on slot 3, a client
    whose counter has drifted to 4 reports its game, and the row for "game 4"
    is written at slot 3. games_played becomes 3, so the lobby is now on 4. The
    SECOND client of that same game reports — same physical game, its own room
    string, its own tail of 4. The lookup asks for {4, 4}; the row that holds
    this game is at 3; nothing is found; it settles as game 4. One game, two
    full settlements, two ratings, two payouts — which is the 2026-08-07 defect
    this whole file exists to close, reintroduced by the acceptance.

    Refusing is what makes the stored number and the named number one number,
    so the lookup can never miss the repeat."""
    assert main._ffa_game_number_refusal(4, 3) is not None
    assert main._ffa_game_number_refusal(9, 4) is not None
    assert main._ffa_game_number_refusal(main.FFA_GAME_NUMBER_MAX, 1) is not None
    # The refusal names the number an honest drifted client should be using.
    assert "expected_game=3" in main._ffa_game_number_refusal(4, 3)
    # ...and the one tail that is not refused is the equal one.
    assert main._ffa_game_number_refusal(3, 3) is None


def test_a_lower_number_with_no_recorded_game_is_refused():
    why = main._ffa_game_number_refusal(2, 5)
    assert why is not None and "expected_game=5" in why


@pytest.mark.parametrize("tail,expected,gains", [
    (4, 4, "the lobby's own slot, which it would have had anyway"),
    (9, 4, "nothing: refused and recorded (ahead of the sitting)"),
    (2, 5, "nothing: refused and recorded (behind, no row)"),
    (0, 1, "nothing: refused and recorded (zero)"),
    (None, 1, "nothing: refused and recorded (no tail at all)"),
    (1000, 1, "nothing: refused and recorded (over the bound)"),
    (99999, 7, "nothing: refused and recorded (over the bound)"),
])
def test_what_each_misreported_tail_gains(tail, expected, gains):
    """The enumeration the acceptance bar asks for, as one table. Every answer
    but the equality is a refusal, and a refusal settles nothing, pays nothing,
    rates nothing and moves nobody else's game.

    The two answers NOT in this table are the reused ones — a tail naming a
    number this lobby already holds, live or admin-reversed. Those never reach
    this rule at all: the already-recorded lookup finds the row first and the
    report is compared against it, which is
    test_the_candidate_set_covers_both_the_slot_and_the_room_tail and
    test_pg_a_reused_invalidated_number_cannot_widen_the_window."""
    why = main._ffa_game_number_refusal(tail, expected)
    if tail == expected:
        assert why is None, gains
    else:
        assert why is not None, gains


def test_a_missing_game_number_is_refused():
    assert main._ffa_room_game_no("rm_no_tail_at_all") is None
    why = main._ffa_game_number_refusal(None, 1)
    assert why is not None and "no game number" in why


def test_a_zero_game_number_is_refused():
    # The counter a seat carries before it has run this game's start: exactly
    # the partial-view reporter RJ-3 keeps out.
    assert main._ffa_room_game_no("rm_101000_r0") == 0
    why = main._ffa_game_number_refusal(0, 1)
    assert why is not None and "outside 1..999" in why


def test_a_game_number_over_the_bound_is_refused():
    assert main._ffa_room_game_no("rm_102000_r99999") == 99999
    why = main._ffa_game_number_refusal(99999, 1)
    assert why is not None and "outside 1..999" in why


def test_every_refusal_this_rule_can_return_is_recorded_before_it_answers():
    """Control: number-rule-gone. A 409 is terminal for the client's outbox
    precisely because the server keeps what it refuses."""
    src = _endpoint_src()
    block = src[src.index("_number_error = "):src.index("# Players pass:")]
    assert "_ffa_record_and_refuse" in block
    assert "ffa_game_number_mismatch" in block
    # ...and the refusal names the number an honest drifted client should use.
    assert "expected_game={_expected_game}" in block


def test_the_number_rule_stays_inside_the_column_domain():
    assert main.FFA_GAME_NUMBER_MAX <= 32767          # SMALLINT width
    assert main.FFA_GAME_NUMBER_MAX > main.FFA_MAX_GAMES_PER_LOBBY
    # The bound is the CHECK's, not the width's (a SMALLINT accepts 32767).
    sql = MIGRATION.read_text(encoding="utf-8")
    assert "CHECK (game_number BETWEEN 1 AND 999)" in sql
    assert str(main.FFA_GAME_NUMBER_MAX) in sql


# ── what the anchor is worth: the meter (control: headroom-hostile) ───────

def test_a_full_game_window_pays_every_claimed_battle():
    # Row A's own numbers: 32 battles over the ~686s the game really took.
    # Under the fitted pace for three players that window is far above the
    # claim, so the ceiling does not bind and the claim is paid in full.
    assert main._ffa_paid_battles(32, 686.0, 3) == 32.0


def test_a_duplicates_receipt_gap_throttles_the_payout():
    # The same claim metered against the 57s between the two receipts — the
    # defect's signature. Nothing here asserts a policy; it asserts that the
    # window is what decides, which is why the window had to stop being
    # "since the previous ROW".
    throttled = main._ffa_paid_battles(32, 57.0, 3)
    assert throttled < 32.0
    assert throttled == pytest.approx(57.0 * main.FFA_PACE_HEADROOM
                                      / main._ffa_sec_per_battle(3))


def test_the_anchor_and_the_prior_lookup_treat_a_reversal_the_same_way():
    """Control: prior-skips-invalidated. Both INCLUDE invalidated rows. A
    lookup that skipped them while the anchor kept excluding their number would
    let a report reusing a reversed game's number settle a second time AND be
    metered against a window that row had been removed from — a wider window
    and a larger payout than the honest game got."""
    assert "invalidated_at IS NULL" not in main._FFA_PRIOR_GAME_SQL
    assert "invalidated_at" not in main._FFA_PACE_ANCHOR_SQL


# ── the detector (controls: contradiction-blind, kills-not-compared) ──────

def test_the_two_verified_rows_are_a_contradiction():
    why = main._ffa_report_contradiction(S3, _vec(ROW_A), _report(ROW_B, S1), False)
    assert why is not None
    assert S1 in why                      # names the winner disagreement first


def test_a_redelivery_of_the_same_report_is_not_a_contradiction():
    assert main._ffa_report_contradiction(S3, _vec(ROW_A), _report(ROW_A, S3), True) is None


def test_a_tally_that_differs_by_one_point_is_a_contradiction():
    near = dict(ROW_A, **{S2: (1, 7, 2)})
    why = main._ffa_report_contradiction(S3, _vec(ROW_A), _report(near, S3), False)
    assert why is not None and S2 in why


def test_a_kills_only_difference_is_a_contradiction_wherever_kills_are_signed():
    # Control: kills-not-compared. Signed kills decide three things - placement
    # where the lobby's FROZEN kills_tiebreak flag is set, the ffa_kills_50/100
    # achievements and their gold in EVERY lobby, and the refutation of an
    # absent or grace claim - so a kills-only difference between two accounts
    # is a settlement difference wherever the signature covers them.
    near = dict(ROW_A, **{S1: (4, 11, 99)})
    why = main._ffa_report_contradiction(S3, _vec(ROW_A), _report(near, S3), True)
    assert why is not None and "kills" in why


def test_the_comparisons_gate_is_the_signature_not_the_tie_break():
    """Control: kills-gate-narrowed (round 3's own gate, restored).

    kills_break_ties is kills_in_canonical AND the lobby's frozen flag, i.e.
    STRICTLY narrower - so using it here classified a kills difference that
    moved achievement gold, in a lobby with the flag off, as agreement."""
    src = _endpoint_src()
    assert "report, kills_break_ties)" not in src
    assert "len(report.players), kills_break_ties" not in src
    assert "report, kills_in_canonical)" in src
    # The replay-echo call carries the lobby's progress after the gate since
    # round 5, so what follows the flag is a comma and not the closing paren.
    assert "len(report.players), kills_in_canonical," in src
    # ...and the achievement those kills feed is gated on the same fact, not on
    # the tie-break flag, which is what makes them paid either way.
    grant = src.index('_grant_achievement_inline(db, _ach_pid, "ffa_kills_50")')
    ach = src[grant - 700:grant]
    assert "if kills_in_canonical:" in ach


def test_a_kills_only_difference_is_not_a_contradiction_where_they_decide_nothing():
    # An UNSIGNED (v1) kills field decides nothing at all: no placement, no
    # achievement, no refutation. Two honest clients of one game can tally
    # kills from different local observations, and a 409 for a difference that
    # changed nothing would spend an honest report (#430).
    near = dict(ROW_A, **{S1: (4, 11, 99)})
    assert main._ffa_report_contradiction(S3, _vec(ROW_A), _report(near, S3), False) is None


def test_a_leave_difference_is_a_contradiction():
    """Round 3 compared the winner and the tallies and stopped there, so two
    accounts that disagreed about who PLAYED were called agreement and the
    second got 200. left_early is stored per player, and the effective absent
    flag - _ffa_leave_decision's union of the carried ghosts and the
    early-leave graces - is what excludes a seat from rating, XP, gold, the
    payout denominator and everyone else's beaten counts."""
    zeroed = dict(ROW_A, **{S2: (0, 0, 0)})
    # Recorded: S2 played. Reported: S2 left this game and is graced out of it.
    graced = _report(zeroed, S3, leave={S2: (True, False, 1)})
    why = main._ffa_report_contradiction(S3, _vec(zeroed), graced, True)
    assert why is not None and S2 in why
    # Recorded: S2 was an absent carried ghost. Reported: the same. Agreement.
    ghost = _report(zeroed, S3, leave={S2: (True, True, None)})
    assert main._ffa_report_contradiction(
        S3, _vec(zeroed, leave={S2: (True, True)}), ghost, True) is None


def test_a_refuted_leave_claim_agrees_with_the_row_that_refuted_it():
    """The DECISION is compared, not the claim. A seat with a signed non-zero
    tally has its absent claim refuted, so the row stores absent=False; a
    second report making the same refuted claim therefore AGREES with it, and
    the comparison must not turn every honest redelivery into a 409."""
    claimed = _report(ROW_A, S3, leave={S1: (True, True, None)})
    assert main._ffa_report_contradiction(
        S3, _vec(ROW_A, leave={S1: (True, False)}), claimed, True) is None


def test_a_grace_that_only_differs_in_the_number_is_not_a_disagreement():
    """game_points_at_leave is compared only through the decision it feeds: two
    clients can read the field's running total an instant apart and still be on
    the same side of FFA_LEAVE_GRACE_POINTS."""
    zeroed = dict(ROW_A, **{S2: (0, 0, 0)})
    rec = _vec(zeroed, leave={S2: (True, True)})
    for gp in range(0, main.FFA_LEAVE_GRACE_POINTS):
        r = _report(zeroed, S3, leave={S2: (True, False, gp)})
        assert main._ffa_report_contradiction(S3, rec, r, True) is None, gp


def test_a_roster_difference_is_a_contradiction_either_way():
    short = {S1: ROW_A[S1], S3: ROW_A[S3]}
    assert main._ffa_report_contradiction(S3, _vec(ROW_A), _report(short, S3), False) is not None
    assert main._ffa_report_contradiction(S3, _vec(short), _report(ROW_A, S3), False) is not None


def test_the_detector_is_symmetric():
    # Whichever of the two verified rows had settled first, the other is a
    # contradiction: the detector reports a disagreement, it never ranks the
    # two accounts.
    assert main._ffa_report_contradiction(S3, _vec(ROW_A), _report(ROW_B, S1), False) is not None
    assert main._ffa_report_contradiction(S1, _vec(ROW_B), _report(ROW_A, S3), False) is not None


def test_the_leave_rule_has_exactly_one_definition():
    """#279/#432: the settlement and the comparison ask the same question, and
    a second copy of the rule is the one that stops being updated. The endpoint
    calls the helper and prints what it returns; it does not re-derive."""
    src = _endpoint_src()
    assert "ghosts, graced, _leave_log = _ffa_leave_decision(report, kills_in_canonical)" in src
    assert "ghosts.add(" not in src and "graced.add(" not in src
    assert "_ffa_leave_decision(" in inspect.getsource(main._ffa_report_contradiction)
    # The helper is PURE - it returns its log lines instead of printing them,
    # so the comparison path cannot emit a second copy of the endpoint's own
    # evidence about a report that is about to be refused.
    assert "print(" not in inspect.getsource(main._ffa_leave_decision)


def test_a_same_room_second_report_is_compared_before_it_is_echoed():
    """The room id is "<photon room>_<HHmmss>_r<N>", so two clients of one game
    that started inside the same second build the SAME string. That report used
    to receive 200 with the stored result, uncompared."""
    src = inspect.getsource(main._ffa_replay_echo)
    compare = src.index("_ffa_prior_field_disagreement")
    echo = src.index("return await _ffa_match_echo")
    assert compare < echo
    assert "_ffa_record_and_refuse" in src
    # A roster that is not the recorded one is refused — and its payload is
    # KEPT now, like every other terminal refusal on this path. Round 2 left
    # it bare on the capture-before-binding argument, which weighed the flood
    # a capture could produce (quota-bounded) against spending a report
    # outright (unbounded loss), and weighed the wrong one (#430).
    assert 'raise HTTPException(409, "Duplicate room id")' not in src
    assert '"ffa_replay_roster_mismatch"' in src
    assert '"ffa_room_other_lobby"' in src
    assert src.count("_ffa_record_and_refuse") == 3


# ── the partial-view refusal, and the skew it must not catch ──────────────

def test_an_all_zero_scoreboard_has_no_unique_round_maximum():
    """Control: shape-winner-gone. The shape a seat with empty per-game tables
    reports. It used to be a bare 400 above the lobby read — refused with
    nothing kept, which is the one outcome the July-30 rule exists to stop."""
    zeros = {S1: (0, 0, 0), S2: (0, 0, 0), S3: (0, 0, 0)}
    why = main._ffa_score_shape_error(_report(zeros, S1), 5, 3)
    assert why == "winner disagrees with the round tallies"


def test_a_report_short_of_the_score_target_is_refused():
    # 1/0/0 against first-to-5 is the relaunched-reporter shape: it HAS a
    # unique maximum, and is still not a complete game at either target.
    near_zero = {S1: (1, 2, 0), S2: (0, 0, 0), S3: (0, 0, 0)}
    why = main._ffa_score_shape_error(_report(near_zero, S1), 5, 3)
    assert why is not None and "complete game" in why


def test_a_complete_game_at_the_lobbys_frozen_target_is_accepted():
    assert main._ffa_score_shape_error(_report(ROW_A, S3), 5, 3) is None
    assert main._ffa_score_shape_error(_report(ROW_B, S1), 5, 3) is None


def test_a_complete_game_at_the_module_default_is_settled_in_a_skewed_lobby():
    """Control: shape-skew-refused. A client that missed the score-target room
    property plays to the module default and reports a REAL completed game.
    Refusing it left that player with the local result and no server match, no
    rating, no XP and no gold — a refusal costing more than the report it was
    easing (#430)."""
    assert main.FFA_ROUNDS_TO_WIN == 5
    # DISTINCT values, or this test passes with the arm deleted: the lobby froze
    # 3 and the report is a complete game to 5. (Round 2's version asked about a
    # lobby frozen at 5, where the two admissible values coincide and removing
    # the second one changed nothing.)
    assert main._ffa_score_shape_error(_report(ROW_A, S3), 3, 3) is None
    assert max(r for r, _, _ in ROW_A.values()) == 5 != 3
    # ...and the endpoint settles it, naming the skew rather than refusing.
    src = _endpoint_src()
    assert "score-target skew" in src
    assert src.index("INSERT INTO ffa_matches") > src.index("score-target skew")


# ── a skewed game is settled, but not with the frozen target's economics ──

def test_the_frozen_and_the_played_target_are_two_different_prices():
    """The fact the refund exists for. _ffa_field_odds' own docstring says race
    length changes true win probabilities, so a wager placed on a first-to-3
    field is not the same wager on a first-to-5 one — and the bettor agreed to
    the price they were shown, which was the frozen lobby's."""
    field = [(S1, 1500.0, 60.0), (S2, 1200.0, 60.0), (S3, 1800.0, 60.0)]
    short = main._ffa_field_odds(field, 3)
    long_ = main._ffa_field_odds(field, 5)
    assert short != long_
    # ...and the direction is the one that makes a mispriced payout a real
    # money move: a longer race is safer for the favourite, so their odds drop.
    assert long_[S3] < short[S3]


def test_a_skewed_game_refunds_its_wagers_instead_of_paying_frozen_prices():
    """Control: skew-pays-its-wagers. The stakes come back; they are never paid
    at a price for a race that was not run, and never kept either."""
    src = _endpoint_src()
    assert "_target_skew = _played_target != int(_score_target)" in src
    bets = src[src.index("game_no = _game_number"):src.index("await _ffa_advance_lobby_slot")]
    assert "if _target_skew:" in bets
    assert '_refund_ffa_game_bets_strict(db, lobby_uuid, game_no,' in bets
    # ...and this game's own settle is the branch that does NOT run.
    assert "if not _target_skew:" in bets
    settle = bets.index("_settle_ffa_bets_for_game(db, lobby_uuid, game_no")
    assert bets.index("if not _target_skew:") < settle
    # The refund is idempotent and moves gold as an EXACT delta (#326), so a
    # retry, the straggler pass and the closure reconcile can all cross it.
    # Round 5 pinned the clamped form here — `GREATEST(0, gold_spent - :amt)`
    # beside a ledger row for the whole stake — which is the defect, not the
    # guarantee: it records 10 returned while moving 5.
    ref = inspect.getsource(main._refund_ffa_game_bets_strict)
    assert "settled_at IS NULL RETURNING id" in ref
    assert "_return_stake_exactly(" in ref
    assert "GREATEST" not in ref
    # ...and because the refund stamps settled_at, every later pass skips it:
    # both the straggler query and the closure reconcile select on IS NULL.
    assert "settled_at IS NULL AND game_number < :g" in src
    assert "settled_at IS NULL ORDER BY game_number" in \
        inspect.getsource(main._reconcile_ffa_lobby_bets)


def test_the_skew_refund_is_part_of_the_settlement_and_not_a_best_effort_pass():
    """Controls: skew-refund-is-fail-soft, skew-refund-caps-at-one-pass.

    Round 3 called the SWEEP helper here, from inside the block whose except
    swallows everything. That helper also ends its pass at 200 rows. Either way
    a wager on a skewed game could still be unsettled at commit, and the next
    pass over it - the straggler loop, the closure reconcile, the janitor -
    settled it against the recorded winner at the FROZEN price, which is the
    one outcome the branch exists to prevent (#412).

    Three properties, and the file's own fail-soft refund has to keep NOT
    having them, or this test is measuring nothing."""
    strict = inspect.getsource(main._refund_ffa_game_bets_strict)
    soft = inspect.getsource(main._refund_ffa_lobby_bets)
    # 1. It does not swallow. 2. It opens no savepoint of its own, so a failure
    # takes the caller's transaction with it. 3. It loops to exhaustion and
    # RAISES at its bound rather than returning short.
    assert "except Exception" not in strict and "except Exception" in soft
    assert "begin_nested" not in strict and "begin_nested" in soft
    assert "raise RuntimeError(" in strict
    # `+ 1` since round 5: the bound is a number of WAGERS, and only an empty
    # read returns, so a run that refunds the full 50 x 200 still needs a
    # confirming read before the refusal may fire. The executed pair
    # (test_a_game_whose_wagers_the_refund_moved_in_full_..., and the one past
    # the bound) is what holds that; this only pins the shape.
    assert "for _ in range(FFA_REFUND_MAX_BATCHES + 1)" in strict
    # The caller runs it OUTSIDE the block whose except swallows bet problems,
    # and turns a failure into a retryable answer rather than a committed row.
    src = _endpoint_src()
    swallow = src.index("[FFA-BETS] settle failed (report unaffected")
    assert src.index("_refund_ffa_game_bets_strict(") > swallow
    assert src.index("_refund_ffa_game_bets_strict(") < src.index("await _ffa_advance_lobby_slot")
    blk = src[swallow:src.index("await _ffa_advance_lobby_slot")]
    assert "FfaReportRefusal(" in blk and "503" in blk


def test_a_later_pass_refunds_a_recorded_skew_instead_of_settling_it():
    """The other half of the same guarantee, and the one a leftover needs. Every
    after-the-fact resolver asks ONE helper what a recorded game's wagers must
    do, and that helper reads the row's two target columns - so a wager that
    somehow outlives the settlement's own refund is returned, never paid at the
    price the bettor did not agree to."""
    outcome = inspect.getsource(main._ffa_recorded_game_outcome)
    assert "score_target_frozen" in outcome and "score_target_played" in outcome
    assert 'return "refund", None' in outcome
    # Both resolvers go through it, and neither settles without asking.
    rec = inspect.getsource(main._reconcile_ffa_lobby_bets)
    assert "_ffa_recorded_game_outcome(" in rec
    assert 'verdict == "settle"' in rec
    assert 'verdict == "refund"' in rec
    src = _endpoint_src()
    strag = src[src.index("stragglers = "):src.index("[FFA-BETS] settle failed")]
    assert "_ffa_recorded_game_outcome(" in strag
    assert "SELECT winner_id FROM ffa_matches" not in strag
    # NULL columns (every pre-327 row) mean "no skew recorded", which is the
    # pre-327 behaviour - a guessed skew would refund a game that was paid.
    assert "frozen is not None and played is not None" in outcome


def test_a_skewed_game_is_rated_with_the_weight_of_the_target_it_was_played_to():
    """Control: skew-keeps-frozen-weight. w(N) is the information weight of the
    result, and the result is evidence about the race that was actually run."""
    src = _endpoint_src()
    assert "_ffa_rating_deltas([p.steam_id for p in report.players]," in src
    assert "pre, _played_target)" in src
    assert "pre, _score_target)" not in src
    # The weight really does move between the two targets, or the control above
    # would redden nothing: w(3) = 0.5 against w(5) = 1.0.
    placements = {S1: 2, S2: 3, S3: 1}
    pre = {s: (1500.0, 200.0, 0.06) for s in (S1, S2, S3)}
    at3 = main._ffa_rating_deltas(list(pre), frozenset(), placements, pre, 3)
    at5 = main._ffa_rating_deltas(list(pre), frozenset(), placements, pre, 5)
    assert at3[S3][0] != at5[S3][0]
    assert abs(at5[S3][0] - 1500.0) > abs(at3[S3][0] - 1500.0)


def test_the_match_row_records_both_targets():
    src = _endpoint_src()
    cols = src[src.index("INSERT INTO ffa_matches"):src.index("VALUES", src.index("INSERT INTO ffa_matches"))]
    assert "score_target_frozen" in cols and "score_target_played" in cols
    assert '"stf": int(_score_target), "stp": _played_target,' in src
    sql = MIGRATION.read_text(encoding="utf-8")
    assert "ADD COLUMN IF NOT EXISTS score_target_frozen SMALLINT" in sql
    assert "ADD COLUMN IF NOT EXISTS score_target_played SMALLINT" in sql


def test_the_played_target_is_one_of_two_server_held_numbers():
    """The narrower claim, which is the true one. `_played_target` IS the
    report's own max tally, so the report selects which of the two branches
    runs; what it cannot do is name a third length, because the shape rule
    above admits exactly the lobby's frozen target and the module default and
    refuses everything else. Round 3 wrote "never a number the report chose",
    which reads as the stronger claim and is not what the code does."""
    src = _endpoint_src()
    assert "_played_target = int(max_rounds)" in src
    note = src[src.index("The target the game was actually played to"):
               src.index("_played_target = int(max_rounds)")]
    assert "never a number the report chose" not in note
    assert "SELECTS between two server-held numbers" in note
    # max_rounds has been through the shape rule by then, which admits exactly
    # those two values and refuses everything else.
    assert src.index("_shape_error = ") < src.index("_played_target = ")
    shape = inspect.getsource(main._ffa_score_shape_error)
    assert "admissible = (int(score_target), int(FFA_ROUNDS_TO_WIN))" in shape
    assert main._ffa_score_shape_error(_report({S1: (7, 16, 3), S2: (2, 5, 1),
                                                S3: (1, 3, 0)}, S1), 8, 3) is not None


def test_a_game_at_neither_target_is_refused():
    # A lobby frozen at 8: seven rounds is neither its target nor the default.
    seven = {S1: (7, 16, 3), S2: (2, 5, 1), S3: (1, 3, 0)}
    why = main._ffa_score_shape_error(_report(seven, S1), 8, 3)
    assert why is not None and "ends at 8" in why


def test_the_points_ceiling_follows_the_target_the_game_ran_to():
    # A longer game honestly banks more; the ceiling is one of two SERVER-held
    # numbers (the frozen target, the module default) and never one the report
    # names.
    fat = dict(ROW_A, **{S1: (4, main._ffa_max_points(3, 5) + 1, 0)})
    assert main._ffa_score_shape_error(_report(fat, S3), 5, 3) == \
        "point tally above the game limit"
    assert main._ffa_score_shape_error(_report(ROW_A, S3), 3, 3) is None


def test_a_report_whose_accepted_response_was_lost_gets_the_stored_result():
    """The outbox retries a committed report under the SAME room id. It reaches
    the replay echo, the comparison finds its own stored values, and it gets
    200 with the recorded result — no second settlement, and nothing written.
    The comparison is what makes this safe to answer 200: the same client's
    retry agrees with itself by construction."""
    src = inspect.getsource(main._ffa_replay_echo)
    assert "photon_room_id = :room" in src
    assert "_ffa_match_echo" in src
    assert 'message="Already recorded"' in inspect.getsource(main._ffa_match_echo)
    # The retry runs above every quarantine branch of the endpoint, so a
    # committed report arriving after its lobby closed is echoed, not captured.
    esrc = _endpoint_src()
    assert esrc.index("_ffa_replay_echo") < esrc.index('lobby["status"] != "active"')


def test_the_closed_lobby_capture_gate_reads_the_same_win_invariant():
    """One definition of "this is a complete game", not two. An open-coded
    `max_rounds == _score_target` here would refuse to KEEP exactly the
    config-skew report the shape rule now settles (#279/#432)."""
    src = _endpoint_src()
    block = src[src.index("_roster_bound = "):src.index('detail="Lobby is not active"')]
    assert "_ffa_score_shape_error" in block
    assert "max_rounds == _score_target" not in block


def test_the_shape_refusal_is_recorded_before_it_is_refused():
    src = _endpoint_src()
    block = src[src.index("_shape_error = "):src.index("# Rate ceiling:")]
    assert "_ffa_record_and_refuse" in block
    assert "score_shape_mismatch" in block
    # The bare 400 that ran above the lobby read is gone.
    assert 'HTTPException(400, "winner disagrees' not in src


def test_the_summed_rounds_floor_could_never_fire():
    # Recorded rather than shipped: the brief asked for sum(rounds_won) >=
    # score_target. The winner alone contributes the target on every report the
    # rule above admits, and rounds_won is non-negative, so such a check cannot
    # fail — and a check that cannot fail is worse than none (#342).
    for vec in (ROW_A, ROW_B):
        winner = max(vec, key=lambda s: vec[s][0])
        assert main._ffa_score_shape_error(_report(vec, winner), 5, 3) is None
        assert sum(r for r, _, _ in vec.values()) >= 5


def test_the_two_rules_that_could_not_fire_are_gone():
    src = inspect.getsource(main._ffa_score_shape_error)
    assert "rounds_won > score_target" not in src
    assert "round tally above the game limit" not in src


# ── a refusal that says "recorded" must have recorded ─────────────────────

class _FakeResult:
    def __init__(self, value=None, rows=None):
        self._value = value
        self._rows = list(rows or [])

    def scalar(self):
        return self._value

    def scalars(self):
        return self

    def all(self):
        return self._rows


class _FakeDb:
    """Enough AsyncSession for _quarantine_report: a scripted reply per
    statement, and a record of what it was asked."""

    def __init__(self, pending=0, insert_id=None, boom=False, stored=None,
                 variants=()):
        self.pending = pending
        self.insert_id = uuid.uuid4() if insert_id == "new" else insert_id
        self.boom = boom
        self.stored = stored           # what (mode, room) already holds
        self.variants = list(variants)  # the group's NULL-room rows
        self.committed = False
        self.statements = []
        self.inserts = 0

    async def rollback(self):
        return None

    async def commit(self):
        self.committed = True

    async def execute(self, stmt, params=None):
        sql = str(stmt)
        self.statements.append(sql)
        if "pg_advisory_xact_lock" in sql:
            return _FakeResult(1)
        if "SELECT COUNT(*)" in sql:
            return _FakeResult(self.pending)
        if "SELECT payload FROM match_report_quarantine" in sql:
            if "photon_room_id IS NULL" in sql:
                return _FakeResult(rows=self.variants)
            return _FakeResult(self.stored)
        if "INSERT INTO match_report_quarantine" in sql:
            if self.boom:
                raise RuntimeError("insert failed")
            self.inserts += 1
            return _FakeResult(self.insert_id)
        return _FakeResult(None)


PAYLOAD = {"a": 1, "players": [{"steam_id": S1, "rounds_won": 5}]}
OTHER = {"a": 1, "players": [{"steam_id": S1, "rounds_won": 0}]}


def _capture(db, payload=None):
    return asyncio.run(main._quarantine_report(
        db, mode="ffa", reason="r", status_code=409,
        payload=PAYLOAD if payload is None else payload,
        group_id=uuid.uuid4(), photon_room_id="rm_r1"))


def test_the_capture_says_which_of_the_five_things_happened():
    assert _capture(_FakeDb(insert_id="new")) == "recorded"
    # The room's row already holds THIS report: the retry-idempotency, not a
    # drop.
    assert _capture(_FakeDb(insert_id=None,
                            stored=json.dumps(PAYLOAD))) == "already"
    assert _capture(_FakeDb(pending=50)) == "quota"
    assert _capture(_FakeDb(boom=True)) == "failed"


def test_a_delivery_that_adds_no_row_is_not_charged_for_one():
    """Control: quota-before-idempotency (round 3's order).

    The pending bound exists to stop a flood of NEW rows. Counting it FIRST
    meant that at saturation an honest outbox retry of a payload the table
    already held was answered 503 instead of its idempotent terminal answer -
    so the bound spent the very report it exists to preserve. The read is now
    first, and neither kept answer touches the count."""
    full = _FakeDb(pending=50, stored=json.dumps(PAYLOAD))
    assert _capture(full) == "already"
    assert full.inserts == 0
    # A REPEAT of a variant is the same kind of delivery: its payload is on
    # file, so it adds nothing and costs nothing, even at saturation.
    repeat = _FakeDb(pending=50, stored=json.dumps(OTHER),
                     variants=[json.dumps(PAYLOAD)])
    assert _capture(repeat) == "variant"
    assert repeat.inserts == 0
    # ...and the order is what does it: the on-file read runs before the count.
    src = inspect.getsource(main._quarantine_report)
    assert src.index("_quarantine_on_file(") < src.index("SELECT COUNT(*)")


def test_a_variant_is_kept_once_however_often_it_is_delivered():
    """Control: variant-rows-are-not-deduped.

    A variant row carries photon_room_id NULL so it cannot take the
    (mode, room) key that makes an honest retry idempotent - which left it with
    no idempotency at all: round 3 inserted a fresh row for every redelivery,
    so one differing payload delivered four times (three immediate retries plus
    an outbox attempt) cost four rows of a 50-row bound. The group's NULL-room
    rows are compared as values too."""
    first = _FakeDb(insert_id=None, stored=json.dumps(OTHER))
    assert _capture(first) == "variant"
    assert first.inserts == 1
    again = _FakeDb(insert_id=None, stored=json.dumps(OTHER),
                    variants=[json.dumps(PAYLOAD)])
    assert _capture(again) == "variant"
    assert again.inserts == 0
    # A DIFFERENT second account is still kept - the dedupe is on the payload,
    # not on "there is already a variant".
    third = _FakeDb(insert_id=None, stored=json.dumps(OTHER),
                    variants=[json.dumps({"a": 2})])
    assert _capture(third) == "variant"
    assert third.inserts == 1


def test_a_distinct_account_of_a_captured_room_is_compared_and_kept():
    """Control: conflict-is-always-already.

    "Same room id" is not "same report": the report room id is
    "<photon room>_<HHmmss>_r<N>", so two clients of one game that started
    inside the same second build the SAME string. Answering "already" without
    looking dropped the second account while its reporter was told the server
    had kept the report — and a 409 is terminal, so that payload was gone."""
    db = _FakeDb(insert_id=None, stored=json.dumps(OTHER))
    assert _capture(db) == "variant"
    # It was COMPARED (the stored payload was read back)...
    assert any("SELECT payload FROM match_report_quarantine" in s
               for s in db.statements)
    # ...and RECORDED: one insert, carrying a NULL room so the partial unique
    # index that makes an honest retry idempotent still does. (Round 3 tried
    # the keyed insert first and wrote this row after the conflict came back,
    # i.e. two statements; the read above already knows the key is taken.)
    assert db.inserts == 1
    variant = [s for s in db.statements
               if "INSERT INTO match_report_quarantine" in s][-1]
    assert ":rep, :pids, CAST(:pl AS JSONB))" in variant
    assert ":g, NULL, :rep" in variant
    # The room is not lost — the payload itself names it.
    assert "photon_room_id" in main.FfaMatchReport.model_fields


def test_a_variant_row_is_as_actionable_in_the_admin_queue_as_any_other():
    """Keeping a payload nobody can act on would be half a fix. The queue's
    three endpoints key on the row's id, its mode, its player_ids and its
    created_at — never on photon_room_id, which the list only renders."""
    listing = inspect.getsource(main.admin_list_quarantine)
    assert "q.status = 'pending'" in listing
    assert "photon_room_id = " not in listing
    for fn in (main.admin_accept_quarantine, main.admin_discard_quarantine):
        src = inspect.getsource(fn)
        assert "WHERE id=CAST(:qid AS UUID)" in src or \
               "WHERE id = CAST(:qid AS UUID)" in src
        assert "photon_room_id" not in src


def test_an_encoding_difference_is_not_a_distinct_account():
    """Compared as VALUES, not as text: key order and separator spacing are not
    two different reports, and calling them different would keep a duplicate
    row for every honest retry."""
    reordered = json.dumps({"players": PAYLOAD["players"], "a": 1},
                           separators=(", ", ": "))
    assert _capture(_FakeDb(insert_id=None, stored=reordered)) == "already"
    # A decoded object (a driver with a JSON codec) reads the same way.
    assert _capture(_FakeDb(insert_id=None, stored=dict(PAYLOAD))) == "already"


def test_an_unreadable_stored_payload_keeps_the_new_one():
    """The conservative direction: a comparison nobody could make must not be
    the reason a report is discarded."""
    assert _capture(_FakeDb(insert_id=None, stored=None)) == "variant"
    assert _capture(_FakeDb(insert_id=None, stored="{not json")) == "variant"


def _refuse(capture_result, status=409, reread=True, progress=None):
    """_ffa_record_and_refuse with the capture's answer scripted.

    `progress` is what the CALLER resolved before it asked for the refusal, and
    it defaults to the two counters alone. The contradictory-replay caller
    resolves `_ffa_with_settled(...)` instead, so passing a dict carrying
    `settled_game` here is how a test drives the arm the endpoint reaches on a
    report whose game the lobby has already settled.

    ROUND 10 scripts the post-capture re-read as well, and that is not
    convenience. Since the re-read FAILS CLOSED, the `None` session these
    tests pass makes EVERY answer here the 503 that says "there is no reading
    of the lobby to give" -- so none of them would be asking the question
    about the CAPTURE that this helper exists to ask, and four tests would
    have gone green on an answer none of them is about (#342).

    `reread=False` is the other side of the same switch: it leaves the real
    helper in place over a session that cannot answer, which is the exhausted
    case itself, and it is what
    test_a_refusal_whose_lobby_cannot_be_read_carries_no_progress_at_all
    drives."""
    async def fake_quarantine(db, **kw):
        return capture_result

    async def fake_relock(db, lobby_uuid):
        return main._ffa_progress(3)

    real = main._quarantine_report
    real_relock = main._ffa_progress_relocked
    main._quarantine_report = fake_quarantine
    if reread:
        main._ffa_progress_relocked = fake_relock
    try:
        rep = types.SimpleNamespace(
            photon_room_id="rm_r1", reported_by_steam_id=S1,
            model_dump=lambda: {"a": 1})
        asyncio.run(main._ffa_record_and_refuse(
            None, report=rep, lobby_uuid=uuid.uuid4(),
            id_by_steam={S1: uuid.uuid4()}, reason="ffa_game_contradiction",
            why="w", detail="This game is already recorded",
            progress=(main._ffa_progress(3) if progress is None else progress),
            status=status))
    finally:
        main._quarantine_report = real
        main._ffa_progress_relocked = real_relock


def test_a_refusal_whose_capture_recorded_is_terminal():
    """Control: capture-always-ok."""
    for kept in ("recorded", "already", "variant"):
        with pytest.raises(main.HTTPException) as ex:
            _refuse(kept)
        assert ex.value.status_code == 409, kept
    # The one caller that refuses with 403 (a downgraded signature) gets 403,
    # not a 409 — the status is the reason, and the 503 arm below is the report.
    with pytest.raises(main.HTTPException) as ex:
        _refuse("recorded", status=403)
    assert ex.value.status_code == 403


def test_a_refusal_whose_capture_did_not_record_is_not_terminal():
    # 409 (and 403) are terminal for the client's outbox, so answering one over
    # a capture that hit the pending bound or raised would SPEND the report and
    # lose it. 503 is "could not judge this yet", which the same outbox retries.
    for kept in ("quota", "failed"):
        for status in (409, 403):
            with pytest.raises(main.HTTPException) as ex:
                _refuse(kept, status=status)
            assert ex.value.status_code == 503, (kept, status)


def test_a_refusal_whose_lobby_cannot_be_read_carries_no_progress_at_all():
    """Control: capture-refusal-restores-the-snapshot (r10).

    The r6 MEDIUM. A capture ends this request's transaction, so the counters
    the caller still holds predate it and every answer below the capture is
    built from a FRESH read. Rounds 5 to 9 made the exhausted case -- both
    relock attempts failed, or the lobby row is gone -- answer from the
    caller's pre-rollback copy instead, and called that safe because it could
    only be stale-LOW.

    What it COSTS is the test a guard has to pass (#430). The copy is a number
    the server may no longer accept, handed to the one seat trying to
    resynchronise; naming it earns another terminal refusal and spends one
    more game of the sitting. So the answer is now a 503 -- which this
    client's outbox retries rather than spends -- carrying NO progress fields
    at all, because there is no reading to give. `detail` is the only key in
    the body, so nothing in that answer can be read as an advertised number,
    and the contract's rule for it is RETRY THE SAME BODY LATER, never
    re-key."""
    last = None
    for kept in ("recorded", "already", "variant"):
        with pytest.raises(main.HTTPException) as ex:
            _refuse(kept, reread=False)
        last = ex.value
        assert last.status_code == 503, (kept, last.status_code, last.detail)
        assert last.progress == {}, (kept, last.progress)
        assert "retry this report unchanged" in last.detail, (kept, last.detail)
    # The status is 503 whatever TERMINAL status the caller asked for: a
    # terminal answer whose number the client cannot trust is the one
    # combination this must never produce.
    with pytest.raises(main.HTTPException) as ex403:
        _refuse("recorded", status=403, reread=False)
    assert ex403.value.status_code == 503
    assert ex403.value.progress == {}
    # ...and the handler really does put nothing else in the body.
    handler = main.app.exception_handlers[main.FfaReportRefusal]
    body = json.loads(bytes(asyncio.run(handler(None, last)).body))
    assert set(body) == {"detail"}, body


def test_the_two_503_arms_are_disjoint_on_the_answers_the_endpoint_builds():
    """Control: capture-failure-503-carries-the-settled-game (r12).

    THE r7 HIGH, RUN. A response carries exactly ONE disposition, and the two
    that a 503 could be read as are mutually exclusive:

      * RETRYABLE -- the capture did not record, so nothing about the game was
        decided. The body is kept UNCHANGED and sent again later, and the
        answer carries no progress fields at all: an unchanged body needs no
        number, and a number in this answer would be one nobody asked for;
      * TERMINAL -- `settled_game` names a game the lobby already holds a row
        for. That game is over for this seat however often it is sent, so the
        entry is dropped and the seat resynchronises from `expected_game`.

    A capture-failure answer that ALSO carried `settled_game` would be both at
    once, and the cost of a consumer resolving that the terminal way is a seat
    dropping evidence the server did not keep -- a wrong result, a wrong rating
    or a wrong gold award left standing with nothing on file to correct it
    from. So the two arms are disjoint BY CONSTRUCTION: the capture-failure arm
    raises above the line that re-derives the progress, and the caller's
    resolved `settled_game` is not reachable from it.

    Driven on the answers the endpoint's own helper BUILDS, through the real
    exception handler that serialises them, with the caller supplying exactly
    what the contradictory-replay site supplies -- a progress dict carrying
    `settled_game`. Both arms run in this test; a run that exercised one of
    them would be a check that cannot fail (#342)."""
    handler = main.app.exception_handlers[main.FfaReportRefusal]

    def body_of(exc):
        return json.loads(bytes(asyncio.run(handler(None, exc)).body))

    # What the contradictory-replay caller resolves: _ffa_with_settled over a
    # row the lobby holds at the number the report named.
    named = main._ffa_with_settled(main._ffa_progress(3), {"game_number": 3}, 3)
    assert named.get("settled_game") == 3 and named["expected_game"] == 4, named

    arm_a, arm_b = [], []
    # ARM A: the capture did not record. Retryable, and it says so with
    # nothing else in the body.
    for kept in ("quota", "failed"):
        for status in (409, 403):
            with pytest.raises(main.HTTPException) as ex:
                _refuse(kept, status=status, progress=dict(named))
            arm_a.append(ex.value)
            assert ex.value.status_code == 503, (kept, status)
            assert ex.value.progress == {}, (kept, ex.value.progress)
            assert "retry this report unchanged" in ex.value.detail, ex.value.detail
    # ARM B: the capture recorded. Terminal, and this is the answer that
    # carries the settled number.
    for kept in ("recorded", "already", "variant"):
        with pytest.raises(main.HTTPException) as ex:
            _refuse(kept, status=409, progress=dict(named))
        arm_b.append(ex.value)
        assert ex.value.status_code == 409, kept
    assert len(arm_a) == 4 and len(arm_b) == 3

    # THE DISJOINTNESS, on the serialised bodies rather than on the objects.
    for exc in arm_a:
        body = body_of(exc)
        assert set(body) == {"detail"}, body
        assert "settled_game" not in body, body
    for exc in arm_b:
        body = body_of(exc)
        assert body.get("settled_game") == 3, body
        assert body["expected_game"] == 4, body
    for exc in arm_a + arm_b:
        if exc.status_code == 503:
            assert "settled_game" not in body_of(exc), body_of(exc)

    # ...and the SHAPE that makes it so, read off the helper's own syntax tree
    # rather than off the answers: the capture-failure raise takes a literal
    # empty dict, and it is the raise that comes FIRST, above the
    # re-derivation. A later edit that moved it below would have the caller's
    # dict in scope again.
    tree = ast.parse(inspect.getsource(main._ffa_record_and_refuse))
    raises = [n for n in ast.walk(tree) if isinstance(n, ast.Raise)]
    # WHICH SIDE OF THE RE-DERIVATION EACH EXIT SITS ON, asserted before the
    # total, because the total on its own is ambiguous and the helper's
    # docstring was read against it. "The two terminal answers" are two values
    # of `status` carried by ONE raise; a reader who took them for two raise
    # SITES would add a second terminal exit and meet a bare count with
    # nothing in the function saying which reading is authoritative (#351).
    # The message below is where that is said, so a later round reads it at
    # the moment it matters instead of re-deriving it from prose.
    rederive = [n for n in ast.walk(tree)
                if isinstance(n, ast.Assign)
                and any(getattr(t, "id", None) == "progress"
                        for t in n.targets)
                and "_ffa_progress_after_capture" in ast.unparse(n.value)]
    assert len(rederive) == 1, [ast.unparse(n) for n in rederive]
    split = rederive[0].lineno
    above = [n for n in raises if n.lineno < split]
    below = [n for n in raises if n.lineno > split]
    assert (len(above), len(below)) == (1, 1), (
        "this helper has ONE exit above the re-derivation -- the "
        "capture-failure arm, which carries no progress fields -- and ONE "
        "below it, the terminal arm, which answers 409 or 403 from the "
        "re-derived progress. A second exit below would be a second place "
        "the caller's resolved settled_game can reach a response. "
        "above=%s below=%s"
        % ([ast.unparse(n) for n in above], [ast.unparse(n) for n in below]))
    assert len(raises) == 2, [ast.unparse(r) for r in raises]
    by_status = {}
    for node in raises:
        call = node.exc
        assert isinstance(call, ast.Call) and getattr(call.func, "id", None) \
            == "FfaReportRefusal", ast.unparse(node)
        by_status[ast.unparse(call.args[0])] = call.args[2]
    assert sorted(by_status) == ["503", "status"], sorted(by_status)
    assert isinstance(by_status["503"], ast.Dict) and not by_status["503"].keys, (
        "the capture-failure 503 carries progress fields: "
        + ast.unparse(by_status["503"]))
    assert ast.unparse(by_status["status"]) == "progress"

    # THE CLASS, not the one line (#432): every 503 the endpoint itself raises
    # carries either the empty dict or one of the names the sibling test proves
    # is a locked reading -- never a call, and in particular never a
    # _ffa_with_settled of one.
    seen = 0
    for node in ast.walk(ast.parse(_endpoint_src())):
        if (isinstance(node, ast.Call)
                and getattr(node.func, "id", None) == "FfaReportRefusal"
                and isinstance(node.args[0], ast.Constant)
                and node.args[0].value == 503):
            seen += 1
            arg = node.args[2]
            assert isinstance(arg, (ast.Dict, ast.Name)), ast.unparse(node)
            if isinstance(arg, ast.Dict):
                assert not arg.keys, ast.unparse(node)
    assert seen >= 3, seen


def test_a_refusal_over_a_variant_capture_says_which():
    """The reporter is told its account is not the one that was already on
    file, instead of being told "already recorded" about a report that said
    something else."""
    with pytest.raises(main.HTTPException) as ex:
        _refuse("variant")
    assert "different account of this room" in ex.value.detail
    with pytest.raises(main.HTTPException) as plain:
        _refuse("recorded")
    assert "different account" not in plain.value.detail


def test_the_rj3_branches_never_answer_409_without_asking_the_capture():
    src = _endpoint_src()
    for reason in ("ffa_game_contradiction", "ffa_game_number_mismatch",
                   "score_shape_mismatch"):
        i = src.index(reason)
        window = src[max(0, i - 400):i + 400]
        assert "_ffa_record_and_refuse" in window, reason
    # ...and no branch of the endpoint writes a match or player row while
    # refusing.
    branch = src[src.index("_named_game = "):src.index("INSERT INTO ffa_matches")]
    for forbidden in ("UPDATE ffa_matches", "UPDATE players", "invalidated_at =",
                      "DELETE FROM"):
        assert forbidden not in branch, forbidden


def _terminal_raises(src):
    """Every terminal refusal literal in a source blob, in EITHER raise form.

    The FFA report path raises FfaReportRefusal wherever it can name the
    lobby's progress and plain HTTPException where it cannot (above the lobby
    read). A regex that only saw one of them would stop seeing half the class
    the moment a site moved between the two - a check that cannot fail (#342).
    The message literal is the key; what follows it is the progress argument."""
    return re.findall(
        r"raise (?:HTTPException|FfaReportRefusal)\((4\d\d), (f?\"[^\"]*\")",
        src)


def test_no_terminal_refusal_on_the_ffa_report_path_is_answered_over_nothing():
    """The whole class, not the two lines the last round named (#432).

    A 4xx is terminal for the client's outbox, so the report is spent either
    way. Every one of them on this path therefore has to be one of exactly
    three things: a capture that was STATUS-CHECKED (so it is a 503 when
    nothing was kept), an INTEGRITY refusal the quarantine table may not hold
    (bad signature, unknown player, malformed ids — capturing those makes the
    table an unauthenticated write primitive), or an UNBOUND payload that is
    not evidence about this lobby's game and is refused before binding.

    The list below is the whole enumeration, by message. Adding a terminal
    refusal without deciding which of the three it is fails this test."""
    src = _endpoint_src() + inspect.getsource(main._ffa_replay_echo)
    # Refusals that may not be captured, with the reason each one may not.
    integrity = {
        '"Invalid FFA match signature"': "HMAC",
        '"Invalid lobby_id format"': "unparseable id",
        '"Need at least two distinct players"': "malformed roster",
        '"Winner is not among the players"': "malformed roster",
        '"Reporter is not a participant"': "malformed roster",
        '"photon_room_id is required"': "malformed room id",
        '"One or more players not registered"': "unknown player",
        '"Lobby not found"': "no row to bind to",
    }
    unbound = {
        '"Report must cover exactly the lobby roster"': "roster binding",
        '"Report player count does not match the lobby"': "roster binding",
    }
    seen = 0
    for status, rest in _terminal_raises(src):
        key = rest.strip()
        seen += 1
        if key in integrity or key in unbound:
            continue
        if key.startswith('f"Slot mismatch'):
            continue
        raise AssertionError(
            f"terminal HTTP {status} answered without a kept record: {key}")
    # The enumeration has to have MATCHED something, or a rename of the raise
    # form turns this whole test into a check that cannot fail (#342/#441).
    assert seen >= len(integrity) + len(unbound)
    # ...and the captures that DO stand behind a terminal answer all run
    # through the one helper that checks whether the capture happened.
    for reason in ('"ffa_room_other_lobby"', '"ffa_replay_roster_mismatch"',
                   '"ffa_lobby_no_roster"', '"lobby_game_limit"',
                   '"v1_canonical_downgrade"', 'f"lobby_{lobby[\'status\']}"'):
        i = src.index(reason)
        assert "_ffa_record_and_refuse" in src[max(0, i - 400):i], reason
    # The bare _quarantine_report call, whose answer nobody read, is gone from
    # this endpoint entirely.
    assert "_quarantine_report(" not in src


def test_a_room_whose_row_is_not_visible_yet_is_retried_not_spent():
    """The unique fired, so a row exists — but the writing transaction has not
    committed, so the lookup cannot see it. That is a race, not a verdict."""
    src = _endpoint_src()
    blk = src[src.index("uq_ffa_match_room"):src.index("Pairwise Glicko")]
    assert "FfaReportRefusal(503" in blk
    assert 'HTTPException(409, "Duplicate room id")' not in blk
    # ...and the progress it answers with is RE-READ, because the rollback
    # above released the lock and the in-memory lobby row is a stale snapshot.
    # Through the LOCKED helper since round 5, not a bare SELECT of the
    # counter: this branch names a `settled_game`, so its expected_game has to
    # come from the same derivation every other answer's does or the pair can
    # come back inconsistent. See
    # test_every_progress_the_endpoint_builds_comes_from_a_locked_slot.
    # Round 6 moved the re-read to _ffa_progress_relocked and takes it for
    # BOTH arms of the handler, so the arm that is not the replay cannot be
    # the one that answers bare. The helper is still the locked derivation.
    assert "_race_progress = await _ffa_progress_relocked(" in src[
        src.index("except IntegrityError as ie:"):src.index("uq_ffa_match_room")]
    assert "_race_progress" in blk
    assert "await _ffa_lock_lobby_slot(db, lobby_uuid)" in inspect.getsource(
        main._ffa_progress_relocked)
    assert "SELECT games_played FROM ffa_lobbies" not in blk


def test_a_closed_lobbys_unbound_report_is_not_answered_as_a_lifecycle_refusal():
    """Three different answers, told apart. Round 2 gave a roster that does not
    bind, a shape that does not hold and a genuinely closed lobby the SAME
    terminal 409, and kept a record for only the third."""
    src = _endpoint_src()
    blk = src[src.index('if lobby["status"] != "active":'):
              src.index("# Roster validation")]
    assert "_roster_bound" in blk
    assert 'raise FfaReportRefusal(403, "Report must cover exactly the lobby roster"' in blk
    assert blk.count("_ffa_record_and_refuse") == 2
    assert "score_shape_mismatch" in blk
    assert 'reason=f"lobby_{lobby[\'status\']}"' in blk


# ── the migration, as text ────────────────────────────────────────────────

def test_the_migration_declares_the_column_the_code_binds_and_no_key():
    sql = MIGRATION.read_text(encoding="utf-8")
    assert "ADD COLUMN IF NOT EXISTS game_number SMALLINT" in sql
    assert "BEGIN;" in sql and "COMMIT;" in sql          # #340
    assert "BEFORE THE CODE" in sql.upper()
    # Acceptance bar: no dedup key was added or widened. A unique on
    # (lobby_id, game_number) would fold the 2026-08-07 pair, which means
    # picking one of two unreconciled accounts (#283).
    upper = sql.upper()
    assert "CREATE UNIQUE INDEX" not in upper
    assert "UNIQUE (" not in upper
    assert "DELETE FROM" not in upper and "DROP TABLE" not in upper


def test_the_migration_states_what_the_old_code_does_during_the_window():
    sql = MIGRATION.read_text(encoding="utf-8")
    assert "BEFORE INSERT" in sql
    assert "ffa_matches_derive_game_number" in sql
    # The claim the header makes has to be the one the trigger implements: a
    # writer that supplies no number still lands, numbered.
    fn = sql[sql.index("CREATE OR REPLACE FUNCTION"):sql.index("DROP TRIGGER")]
    assert "IF NEW.game_number IS NOT NULL THEN" in fn        # never overrides
    assert "room_tail" in fn and "sequence" in fn


# ── comments that are claims ──────────────────────────────────────────────
# A comment asserting a guarantee is a claim about the whole state space, and
# it is usually written from the one state its author had in mind (#351/#277).
# Each of these was found false or overstated and is pinned here to what the
# code below it actually does.

def test_the_anchor_does_not_claim_the_table_holds_no_repeat():
    """It does hold one — the 2026-08-07 pair, deliberately preserved, and the
    migration backfills historical rows from their tails rather than from a
    counter. The anchor handles that with GROUP BY instead of assuming it
    away, and the note says so."""
    src = pathlib.Path(main.__file__).read_text(encoding="utf-8")
    note = src[src.index("# ── Pace anchor:"):src.index("_FFA_PACE_ANCHOR_SQL = ")]
    assert "no gap and no repeat by construction" not in note
    assert "That is a statement about NEW rows" in note
    assert "GROUP BY game_number" in main._FFA_PACE_ANCHOR_SQL


def test_the_echo_names_the_two_helpers_that_actually_run_before_it():
    """There is no `_ffa_prior_disagreement`; the roster question and the field
    question are two helpers, kept apart on purpose."""
    doc = inspect.getsource(main._ffa_match_echo)
    assert "_ffa_prior_roster_matches" in doc
    assert "_ffa_prior_field_disagreement" in doc
    assert not hasattr(main, "_ffa_prior_disagreement")
    for caller in (main._ffa_replay_echo, _endpoint_src()):
        src = caller if isinstance(caller, str) else inspect.getsource(caller)
        assert src.index("_ffa_prior_roster_matches") < src.index("_ffa_match_echo")


def test_the_capture_note_no_longer_calls_every_conflict_a_retry():
    doc = inspect.getsource(main._quarantine_report)
    assert "the same report under the same room id is the same report" not in doc
    # A conflict on the key is TWO cases and the note names both: the retry,
    # compared as values rather than as text, and the second account.
    assert "compared as VALUES" in doc
    assert "a DIFFERENT account of the" in doc
    assert '"variant"' in doc
    # ...and it no longer says the quota bounds variants "exactly as it bounds
    # any other capture" without saying what makes a REDELIVERY of one free.
    # Round 5 answered that with "EVERY kept outcome is idempotent", which the
    # bounded scan makes untrue: a variant an admin has reviewed is no longer
    # recognised. The note has to state WHICH row holds the payload and for
    # how long redelivery is free, or it is a guarantee over a case it does
    # not cover (#351).
    assert "EVERY kept outcome is idempotent" not in doc
    assert "EVERY kept outcome means this exact payload IS in the table" in doc
    assert "free while that\n    row is still PENDING" in doc
    assert "whatever its\n    review status" in doc


def test_the_refusal_note_states_the_retry_budget_as_a_bound():
    """Round 3 wrote that a 503 makes the report survive "until an operator
    clears the backlog". It survives as long as the client keeps retrying, and
    that ladder is finite - so the sentence promised something no server-side
    change can deliver."""
    doc = inspect.getsource(main._ffa_record_and_refuse)
    assert "until an operator clears the backlog" not in doc
    assert "FINITE ladder" in doc


def test_the_shutout_note_no_longer_infers_the_target_from_the_tally():
    """The shape rule admits a game played to the module default in a lobby
    frozen at something else, so `winner.rounds_won == 5` and
    `_score_target == 5` are two different claims."""
    src = _endpoint_src()
    i = src.index("ffa_shutout_3")
    note = src[max(0, i - 1400):i]
    assert "is equivalent to" not in note
    assert "NOT the same claim" in note


def test_the_migration_header_says_the_tail_has_to_agree():
    sql = MIGRATION.read_text(encoding="utf-8")
    assert "HAS TO AGREE" in sql
    assert "refused and kept for review" in sql.replace("\n-- ", " ")
    # Provenance documentation covers the writer rows and states what the
    # trigger's sequence arm actually computes.
    assert "writer = the inserting statement supplied it" in sql
    # The trigger's sequence arm has TWO results and the column comment has to
    # name both. Round 5 pinned only the first half ("one above the lobby's
    # highest number for the trigger"), which is the arm's description for
    # every lobby except the one the fallback exists for — so the assertion
    # stayed green over a comment that stopped short exactly where the
    # behaviour gets interesting.
    assert ("for the trigger one above the lobby''s highest number, or the "
            "lobby''s lowest free number when that one would leave the "
            "1..999 domain") in sql
    # The sequence arm is described as what it computes. Round 2 called it "the
    # next free number", which it was not; round 4 added a free-number FALLBACK
    # for the one input MAX+1 cannot serve, and says which is which.
    fn = sql[sql.index("CREATE OR REPLACE FUNCTION"):sql.index("DROP TRIGGER")]
    assert 'NOT "the next free number", which this expression does not compute' in fn
    assert "falls back to the LOWEST FREE number" in fn


def test_the_migration_makes_the_column_total_and_bounded():
    sql = MIGRATION.read_text(encoding="utf-8")
    assert "SET NOT NULL" in sql
    assert "CHECK (game_number BETWEEN 1 AND 999)" in sql
    # Provenance for every backfilled row: which rule gave it its number.
    assert "game_number_source" in sql


def test_the_trigger_claims_only_the_totality_it_has():
    """Round 3's header called the derivation "a total function from a row to a
    number" while its sequence arm raised for any lobby whose HIGHEST number
    was 999 - and that exception reaches the pre-327 api as an HTTP 500. The
    arm now falls back to the lobby's lowest free number, so the only refused
    input is a lobby holding all 999, and the header says so as a bound."""
    sql = MIGRATION.read_text(encoding="utf-8")
    head = sql[sql.index("Insert-time derivation"):sql.index("CREATE OR REPLACE FUNCTION")]
    assert "A total function from a row to a number" not in head
    assert "every lobby that has a free number" in head
    fn = sql[sql.index("CREATE OR REPLACE FUNCTION"):sql.index("DROP TRIGGER")]
    assert "generate_series(1, 999)" in fn
    assert "holds every number in 1..999" in fn


# ── the control inventory, checked against itself ─────────────────────────

def test_the_control_tally_matches_the_list_it_sits_next_to():
    """Control: tally-from-memory (the round-3 LOW at line 50).

    Round 3's docstring said nineteen round-3 controls and listed sixteen. A
    number asserted beside the list that contradicts it is the same defect
    class as a comment asserting a guarantee the code does not supply, and it
    stays wrong silently because nothing counts. This counts.

    It reads the SAME docstring the inventory lives in, so the two cannot
    drift: adding a control without updating the tally reddens here."""
    doc = sys.modules[__name__].__doc__
    entries = [ln for ln in doc.splitlines()
               if re.match(r"^  [a-z0-9-]+( \((?:r3|r4|retired)\))? +\S", ln)]
    # The ROUNDS are derived from the entries too, not listed here. A check
    # whose round list is written down goes stale the round after it is
    # written, and then covers a growing set with a fixed question -- which is
    # the defect two of round 11's findings are about, one level up.
    counted = {}
    for line in entries:
        tag = re.match(r"^  [a-z0-9-]+ \((r\d+|retired)\)", line)
        key = tag.group(1) if tag else "plain"
        counted[key] = counted.get(key, 0) + 1
    counted.setdefault("retired", 0)
    # The committed-test one is listed in the same shape but is called out
    # separately in the prose, so it is not a hand-run control.
    assert any("backfill-neutered" in ln for ln in entries)
    counted["plain"] = counted.get("plain", 0) - 1

    head = re.search(
        r"counted off\s*\n?it: (\d+) unmarked and still live .*?"
        r"(\d+) unmarked and RETIRED", doc, re.S)
    assert head, "the docstring no longer states a tally in a readable form"
    region = doc.split("counted off", 1)[1].split("(backfill-neutered", 1)[0]
    claimed = {}
    for number, tag in re.findall(r"(\d+)\s+marked \((r\d+)\)", region):
        assert tag not in claimed, f"the tally states {tag} twice"
        claimed[tag] = int(number)
    assert claimed, "the docstring states no per-round tally"

    listed = {k: v for k, v in counted.items()
              if k not in ("plain", "retired")}
    assert claimed == listed, (
        f"the docstring's tally and its own list disagree: claimed {claimed}, "
        f"listed {listed}")
    want = (int(head.group(1)), int(head.group(2)))
    have = (counted["plain"], counted["retired"])
    assert want == have, (
        f"the unmarked tallies disagree: claimed {want}, listed {have}")
    # ...and the list is not empty, or the whole check passes on nothing.
    assert len(listed) >= 8, listed
    assert all(n >= 3 for n in listed.values()), listed
    assert counted["plain"] >= 10
    # The evidence sentence names a path that EXISTS in this repository. Round
    # 5 pointed at two files under the gitignored ai-collab scratch, so the
    # inventory's own provenance line was unfollowable from a clone (#302: a
    # claim that cannot be traced is a finding).
    assert "ai-collab/" not in doc.split("All KILLED:")[0].split("counted off")[1]
    evidence = pathlib.Path(__file__).resolve().parent / "evidence"
    assert evidence.is_dir(), f"{evidence} is named by the inventory and absent"
    assert any(evidence.iterdir()), f"{evidence} is empty"


def test_every_round_four_control_names_a_test_that_exists():
    """A control whose test was renamed is a control nobody can re-run, and the
    inventory is the only place the pairing is written down. Every round-4
    control ran against a named node; those names are in the log, and the ones
    the docstring's prose points at have to still be in this module."""
    mod = sys.modules[__name__]
    for name in ("test_pg_the_prior_lookup_reads_the_row_that_holds_the_named_number",
                 "test_pg_a_tail_behind_the_slot_finds_its_own_game_not_the_next_one",
                 "test_the_skew_refund_is_part_of_the_settlement_and_not_a_best_effort_pass",
                 "test_a_later_pass_refunds_a_recorded_skew_instead_of_settling_it",
                 "test_a_leave_difference_is_a_contradiction",
                 "test_the_comparisons_gate_is_the_signature_not_the_tie_break",
                 "test_a_delivery_that_adds_no_row_is_not_charged_for_one",
                 "test_a_variant_is_kept_once_however_often_it_is_delivered",
                 "test_the_lock_the_derivation_and_the_increment_are_one_transaction",
                 "test_pg_two_reports_for_one_lobby_cannot_settle_the_same_number",
                 "test_every_report_answer_carries_the_lobbys_progress",
                 "test_the_lobby_state_advertises_the_sittings_settled_count",
                 "test_pg_the_trigger_never_hands_back_a_number_the_lobby_is_using",
                 "test_no_terminal_refusal_on_the_ffa_report_path_is_answered_over_nothing"):
        assert callable(getattr(mod, name, None)), name


def test_every_round_five_control_names_a_test_that_exists():
    """The same pairing for round 5. Two of them name a PAIR — a static test
    and an executed one — because the round-4 defect was invisible to the
    static half alone."""
    mod = sys.modules[__name__]
    for name in ("test_every_call_in_main_binds_to_the_function_it_names",
                 "test_the_binding_sweep_can_actually_fail",
                 "test_this_file_actually_executes_the_report_endpoint",
                 "test_pg_the_report_endpoint_runs_and_its_echo_carries_the_lobbys_progress",
                 "test_pg_an_answer_never_tells_a_client_to_name_a_number_it_just_settled",
                 "test_pg_the_catch_up_only_ever_moves_the_counter_forward",
                 "test_pg_a_settlement_commits_the_catch_up_and_lands_on_the_free_number",
                 "test_a_game_whose_wagers_the_refund_moved_in_full_is_not_called_an_overflow",
                 "test_one_wager_past_the_bound_still_refuses",
                 "test_the_strict_refund_does_not_inherit_a_guard_it_cannot_afford",
                 "test_a_refusal_raised_out_of_the_skew_refund_still_carries_the_progress",
                 "test_raw_left_early_is_not_a_contradiction_when_the_decision_agrees",
                 "test_the_signature_form_alone_is_not_a_disagreement_about_the_game",
                 "test_the_recorded_outcome_note_does_not_promise_a_missing_column_degrades",
                 "test_pg_a_recorded_outcome_without_the_columns_raises_rather_than_defaulting",
                 "test_every_progress_the_endpoint_builds_comes_from_a_locked_slot"):
        assert callable(getattr(mod, name, None)), name

# ── what a client can resync FROM ─────────────────────────────────────────
# RJ-CLIENT-RESYNC-CONTRACT.md is the client lane's side of these fields. The
# tests below are the server side of the same contract: they are what makes
# the document checkable rather than descriptive.

def test_the_lobby_state_advertises_the_sittings_settled_count():
    """Control: advisory-count-has-no-semantic-test (the round-3 LOW).

    `games_played` was added to the ready-join payload with nothing asserting
    it is EMITTED, what it is measured against, or that it names the same
    quantity the report path refuses on. A field with no test is a field that
    can be renamed, moved under a nested object or dropped, and nothing here
    would notice — which is exactly the state an unchanged client consumer
    cannot be built against (#438: acceptance is a positive signal)."""
    src = inspect.getsource(main._ffa_poll_locked_payload)
    # It is a TOP-LEVEL key of the ready-join payload, which is what the
    # client's substring JSON reader can reach.
    body = src[src.index('return {'):]
    # ROUND 10: BOTH counters, out of the ONE derivation the report path's own
    # answers are built from. The contract makes the server the sole allocator
    # of the game number and forbids a seat to count one for itself --
    # `games_played + 1` is counting, so a payload that carried only the
    # settled count would have required exactly the arithmetic the rule
    # removes, on the one seat with no other reading to go on.
    # Control: join-payload-omits-the-advertised-number (r10). Flattened for
    # the reason the acceptance assertion is: this is about a CALL, and the
    # control's inert twin is that call reflowed (#441).
    flat = " ".join(body.split())
    assert '**_ffa_progress(int(lobby["games_played"] or 0)),' in flat
    assert '"status": "ready_join"' in flat
    # ...and it is the LOBBY's count, not a member count or a queue length.
    assert 'lobby["games_played"]' in flat
    # The spread really does put two TOP-LEVEL integers in the payload, which
    # is what the client's substring JSON reader can reach; a nested object
    # would be unreachable to it.
    emitted = main._ffa_progress(4)
    assert set(emitted) == {"games_played", "expected_game"}
    assert emitted == {"games_played": 4, "expected_game": 5}
    assert all(not isinstance(v, (dict, list)) for v in emitted.values())
    # The one quantity: what the payload advertises and what the report path
    # derives its slot from are the same column, read the same way.
    lock = inspect.getsource(main._ffa_lock_lobby_slot)
    assert 'int(lobby["games_played"] or 0) + 1' in lock
    # And the number a client that reads it should name is the NEXT one.
    assert main._ffa_progress(4)["expected_game"] == 5
    assert main._ffa_progress(0)["expected_game"] == 1


def test_the_join_time_payload_really_emits_both_counters():
    """A structural assertion says the spread is written; this RUNS it.

    A field can be declared and still ship inert -- the acceptance bar for one
    is a positive signal the code actually emits (#438). So the production
    function is awaited over a scripted session and the dict it returns is
    read: both counters present, both top-level, both plain integers, and the
    advertised one exactly one above the settled count. Nothing about the
    lobby's real columns is under test here, so the two helpers that read them
    are scripted and restored."""
    class _Result:
        def __init__(self, rows):
            self._rows = rows

        def mappings(self):
            return self

        def first(self):
            return self._rows[0] if self._rows else None

        def all(self):
            return list(self._rows)

    class _PollDb:
        def __init__(self, lobby):
            self._lobby = lobby
            self._n = 0

        async def execute(self, *a, **kw):
            self._n += 1
            return _Result([self._lobby] if self._n == 1 else [])

    async def fake_tristate(db, lobby_id, lobby):
        return None

    lobby = {"id": LOBBY, "photon_room_id": "rm", "region": "eu",
             "player_count": 3, "games_played": 6, "is_ranked": True}
    real_cfg = main._ffa_lobby_config
    real_tri = main._ffa_game_in_progress_tristate
    main._ffa_lobby_config = lambda row: {
        "score_target": 5, "card_candidates": 4, "initial_picks": 1,
        "card_cap": 20, "same_card_rule": "allow", "sudden_death": False}
    main._ffa_game_in_progress_tristate = fake_tristate
    try:
        payload = asyncio.run(
            main._ffa_poll_locked_payload(_PollDb(lobby), LOBBY, S1))
    finally:
        main._ffa_lobby_config = real_cfg
        main._ffa_game_in_progress_tristate = real_tri
    assert payload["status"] == "ready_join"
    # BOTH, at the TOP level, as plain integers -- the client's JSON reader is
    # a substring scan, so a nested object would be unreachable to it.
    assert payload["games_played"] == 6
    assert payload["expected_game"] == 7
    assert isinstance(payload["games_played"], int)
    assert isinstance(payload["expected_game"], int)
    assert payload["expected_game"] == payload["games_played"] + 1
    # ...and it is the same derivation the report path's own answers use, so
    # the join-time copy and the report-time copy cannot be two different
    # pieces of arithmetic.
    assert {"games_played": 6, "expected_game": 7}.items() <= payload.items()
    assert main._ffa_progress(6).items() <= payload.items()


def test_every_report_answer_carries_the_lobbys_progress():
    """The resync fields, on all three answer shapes.

    One refusal used to poison the rest of a same-room sitting: the client's
    counter advanced at every game start, the server's did not, and no answer
    carried anything a client could realign to — so the first refusal made
    every later report of that sitting one further ahead, and all of them were
    refused (RJ-R3 HIGH, plugin/FfaMode.cs:1077). The server half is that
    EVERY answer names the lobby's authoritative progress."""
    # 1. The shape. Two keys always, and the third only when the answer is
    #    about a game the lobby has already settled.
    assert main._ffa_progress(2) == {"games_played": 2, "expected_game": 3}
    assert main._ffa_progress(2, settled_game=1) == {
        "games_played": 2, "expected_game": 3, "settled_game": 1}
    # The counter is authoritative, not a delta: a client adopts it whole.
    assert main._ffa_progress(0) == {"games_played": 0, "expected_game": 1}

    # 2. The refusals. FfaReportRefusal carries the progress to the handler,
    #    and `detail` stays a plain string so an existing client's error text
    #    is unchanged.
    ex = main.FfaReportRefusal(409, "This game is already recorded",
                               main._ffa_progress(2, settled_game=2))
    assert isinstance(ex, main.HTTPException)
    assert ex.status_code == 409 and ex.detail == "This game is already recorded"
    assert ex.progress == {"games_played": 2, "expected_game": 3,
                           "settled_game": 2}
    handler = main.app.exception_handlers[main.FfaReportRefusal]
    body = json.loads(bytes(asyncio.run(handler(None, ex)).body))
    assert body == {"detail": "This game is already recorded",
                    "games_played": 2, "expected_game": 3, "settled_game": 2}
    # Top-level integer keys: ApiClient.ExtractJsonInt is a substring reader,
    # so a nested object would not be reachable by the unchanged client.
    assert all(not isinstance(v, (dict, list)) for v in body.values())

    # 3. The success answer. The schema carries the same three names, so a
    #    client reads one vocabulary whatever the outcome.
    fields = schemas.FfaMatchResponse.model_fields
    assert {"games_played", "expected_game", "settled_game"} <= set(fields)
    src = _code_lines(_endpoint_src())
    # Control: acceptance-does-not-name-its-settled-game (r10).
    #
    # Whitespace-flattened, because a CALL is what this is about and a call
    # wrapped across two lines is the same call. Matching the raw text would
    # make this measure a LINE SHAPE, and that control's inert twin -- the
    # very reflow -- would redden it (#391/#441, the shape round 6 paid for
    # once already).
    flat = " ".join(src.split())
    ok = "**_ffa_progress(_game_number, settled_game=_game_number)"
    assert ok in flat
    # ...and the success answer's progress is the COMMITTED state: it is built
    # from the number this transaction settled, after the advance.
    assert flat.index("await _ffa_advance_lobby_slot(") < flat.index(ok)
    # ROUND 10: the acceptance ADVERTISES the number the server accepts next
    # AND names the one it just settled. Every answer about a row holding the
    # number the report named says which number that is, so a client never has
    # to infer "settled" from the absence of a refusal. Past
    # _ffa_game_number_refusal the tail and the slot are one number, so this
    # cannot disagree with the row, and the pair's own inequality holds by
    # construction.
    accepted = main._ffa_progress(7, settled_game=7)
    assert accepted == {"games_played": 7, "expected_game": 8, "settled_game": 7}
    assert accepted["settled_game"] < accepted["expected_game"]


def test_a_refusal_the_client_can_act_on_names_the_settled_game():
    """The difference between "retry later" and "this one is done".

    An outbox entry whose game the lobby has already settled must be DROPPED,
    not retried to the end of a finite ladder — and the only way a client can
    tell is the answer. Every refusal about an already-recorded game carries
    settled_game; the ones about a game that is not settled do not."""
    src = _code_lines(_endpoint_src())
    # The already-recorded answers name the game they are about.
    assert "_ffa_with_settled(" in src
    withs = inspect.getsource(main._ffa_with_settled)
    assert '"settled_game"' in withs
    # A 503 (capture failed, room race, refund failed) is retryable and says
    # nothing about a settled game, because none is settled.
    assert main._ffa_progress(2).get("settled_game") is None

# ── live PostgreSQL ───────────────────────────────────────────────────────
# No silent skip. Unset DSN FAILS with the reason; FFA_TEST_PG_OPTOUT=1 is the
# explicit, visible way to run this file without a PostgreSQL.

DSN = os.environ.get("FFA_TEST_PG_DSN")


def _optout(raw) -> bool:
    """Is FFA_TEST_PG_OPTOUT an actual opt-out?

    `if os.environ.get(...)` is true for "0", "false", "no" and "off" — so a
    run that meant to SAY it was not opting out would have opted out silently,
    which is the whole failure mode this gate exists to prevent (#438). Only
    an affirmative word counts, and an unrecognised value is not an opt-out
    either: the live checks then FAIL and name the DSN, which is the direction
    that cannot hide."""
    return str(raw or "").strip().lower() in {"1", "true", "yes", "on"}


OPTOUT = _optout(os.environ.get("FFA_TEST_PG_OPTOUT"))


def require_pg():
    if DSN:
        return DSN
    if OPTOUT:
        pytest.skip("FFA_TEST_PG_OPTOUT is set — live-PostgreSQL checks "
                    "deliberately not run in this invocation")
    pytest.fail(
        "FFA_TEST_PG_DSN is not set, so the production SQL in this file was "
        "never executed: the typed binds (SMALLINT, SMALLINT[]), the anchor's "
        "grouping, the prior-game lookup and migration 327 itself are all "
        "unverified. Set FFA_TEST_PG_DSN=postgresql+asyncpg://... to run them, "
        "or FFA_TEST_PG_OPTOUT=1 to say out loud that this run skips them.")


@pytest.mark.parametrize("raw,opts_out", [
    ("1", True), ("true", True), ("TRUE", True), (" yes ", True), ("on", True),
    ("0", False), ("false", False), ("no", False), ("off", False),
    ("", False), (None, False), ("maybe", False),
])
def test_only_an_affirmative_opt_out_turns_the_live_checks_into_skips(raw, opts_out):
    """A meta-test on the gate itself: `if os.environ.get(...)` treated "0" and
    "false" as opt-outs, so a run that said it was NOT skipping skipped. An
    unrecognised value is not an opt-out either — the live checks fail and name
    the DSN, which is the direction that cannot pass unnoticed."""
    assert _optout(raw) is opts_out


def test_the_live_checks_cannot_be_skipped_by_a_missing_dsn_alone():
    """Control: the round-1 finding that no meta-test reddens if silent
    skipping comes back. require_pg's own source must fail, not skip, when the
    DSN is unset and nobody asked to go without one."""
    src = inspect.getsource(require_pg)
    assert "pytest.fail(" in src
    # No decorator can quietly take the live tests out of a run: pytest's own
    # marker registry for this module carries no skip mark.
    mod = sys.modules[__name__]
    for name in dir(mod):
        fn = getattr(mod, name)
        if callable(fn) and name.startswith("test_pg_"):
            marks = {m.name for m in getattr(fn, "pytestmark", [])}
            assert "skipif" not in marks and "skip" not in marks, name
    # ...and it really does fail: run it with both variables cleared.
    saved_dsn, saved_opt = globals()["DSN"], globals()["OPTOUT"]
    globals()["DSN"], globals()["OPTOUT"] = None, False
    try:
        with pytest.raises(BaseException) as ex:
            require_pg()
        assert "Failed" in type(ex.value).__name__
        assert "FFA_TEST_PG_DSN" in str(ex.value)
        # And with the opt-out set it is a Skipped, not a Failed.
        globals()["OPTOUT"] = True
        with pytest.raises(BaseException) as sk:
            require_pg()
        assert "Skipped" in type(sk.value).__name__
    finally:
        globals()["DSN"], globals()["OPTOUT"] = saved_dsn, saved_opt


# CASCADE on the players drop, and it is load-bearing rather than defensive.
# MONEY_SCHEMA below builds a SECOND set of tables in the same scratch database
# -- gold_transactions, lobby_bets, bets, ranked_series -- and every one of
# them carries a foreign key to players. A plain DROP therefore succeeds on a
# virgin database and raises DependentObjectsStillExistError on every run
# after the first, which makes the live half of this file pass once per scratch
# database and never again. That is not a hypothetical: it is what 14 of these
# tests did on the second run, and it is why r7-postgresql-controls.txt runs
# the whole selection TWICE against one database and quotes both summaries.
# Dropping the constraints is harmless in both directions, because each schema
# block drops and recreates its own tables before using them.
SCHEMA = """
DROP TABLE IF EXISTS match_report_quarantine;
DROP TABLE IF EXISTS ffa_match_players;
DROP TABLE IF EXISTS ffa_matches;
DROP TABLE IF EXISTS ffa_lobbies;
DROP TABLE IF EXISTS players CASCADE;

CREATE TABLE players (
    id UUID PRIMARY KEY,
    steam_id TEXT NOT NULL UNIQUE
);
-- games_played is INTEGER, as 154_ffa_schema.sql declares it: the catch-up in
-- _ffa_lock_lobby_slot casts its bind to INTEGER, and a test table that
-- narrowed the column would be exercising a different write. The other four
-- columns are the ones submit_ffa_match reads off the locked row before it
-- answers. (No colon-prefixed name in this comment -- SQLAlchemy's text()
-- scans comments for binds too, and one here makes every CREATE TABLE in
-- this string demand a parameter.)
CREATE TABLE ffa_lobbies (
    id UUID PRIMARY KEY,
    status VARCHAR(16) NOT NULL DEFAULT 'active',
    player_count SMALLINT NOT NULL DEFAULT 3,
    member_ids UUID[] NOT NULL DEFAULT '{}',
    games_played INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE ffa_matches (
    id UUID PRIMARY KEY,
    lobby_id UUID,
    photon_room_id VARCHAR(64) NOT NULL,
    player_count SMALLINT NOT NULL DEFAULT 3,
    winner_id UUID REFERENCES players(id),
    ended_at TIMESTAMPTZ NOT NULL,
    invalidated_at TIMESTAMPTZ,
    game_number SMALLINT,
    score_target_frozen SMALLINT,
    score_target_played SMALLINT,
    CONSTRAINT uq_ffa_match_room UNIQUE (photon_room_id)
);
CREATE TABLE ffa_match_players (
    match_id UUID NOT NULL REFERENCES ffa_matches(id) ON DELETE CASCADE,
    player_id UUID NOT NULL REFERENCES players(id),
    rounds_won SMALLINT NOT NULL DEFAULT 0,
    points_total SMALLINT NOT NULL DEFAULT 0,
    kills INTEGER NOT NULL DEFAULT 0,
    left_early BOOLEAN NOT NULL DEFAULT FALSE,
    absent BOOLEAN NOT NULL DEFAULT FALSE,
    -- What _ffa_match_echo reads back as the reporter's own answer.
    placement SMALLINT NOT NULL DEFAULT 0,
    rating_change DOUBLE PRECISION NOT NULL DEFAULT 0,
    xp_gained INTEGER NOT NULL DEFAULT 0,
    gold_gained INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (match_id, player_id)
);
-- The capture table, as 169_match_report_quarantine.sql declares the columns
-- the writer touches, INCLUDING the partial unique index -- that index is the
-- retry-idempotency the writer keys on, and a test table without it would let
-- a second delivery insert a second row and call the difference production.
CREATE TABLE match_report_quarantine (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    mode            VARCHAR(8)  NOT NULL,
    reason          VARCHAR(64) NOT NULL,
    http_status     SMALLINT    NOT NULL,
    group_id        UUID,
    photon_room_id  VARCHAR(64),
    reporter_id     UUID REFERENCES players(id) ON DELETE SET NULL,
    player_ids      UUID[]      NOT NULL DEFAULT '{}',
    payload         JSONB       NOT NULL,
    status          VARCHAR(16) NOT NULL DEFAULT 'pending',
    reviewed_by     UUID REFERENCES players(id) ON DELETE SET NULL,
    reviewed_at     TIMESTAMPTZ,
    review_note     TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE UNIQUE INDEX uq_quarantine_room
    ON match_report_quarantine (mode, photon_room_id)
    WHERE photon_room_id IS NOT NULL;
"""

LOBBY = uuid.UUID("0ea879a4-ff42-44c4-9473-4c58f89ef934")
T0 = datetime(2026, 8, 7, 21, 15, 0, tzinfo=timezone.utc)


def run(coro):
    return asyncio.run(coro)


async def _setup(rows, games_played=None):
    """rows: (room, game_number, seconds_after_T0, invalidated) tuples."""
    engine = create_async_engine(require_pg())
    sm = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        for stmt in [s for s in SCHEMA.split(";") if s.strip()]:
            await conn.execute(text(stmt))
        if games_played is not None:
            await conn.execute(text(
                "INSERT INTO ffa_lobbies (id, games_played, created_at)"
                " VALUES (:i, :g, CAST(:t AS TIMESTAMPTZ))"),
                {"i": LOBBY, "g": int(games_played), "t": T0})
    pids = {}
    async with sm() as db:
        for s in (S1, S2, S3):
            pids[s] = uuid.uuid4()
            await db.execute(text("INSERT INTO players (id, steam_id) VALUES (:i, :s)"),
                             {"i": pids[s], "s": s})
        for room, gn, secs, inval in rows:
            await db.execute(text("""
                INSERT INTO ffa_matches (id, lobby_id, photon_room_id, winner_id,
                                         ended_at, invalidated_at, game_number)
                VALUES (:i, :l, :r, :w,
                        CAST(:t0 AS TIMESTAMPTZ)
                          + make_interval(secs => CAST(:s AS DOUBLE PRECISION)),
                        CASE WHEN CAST(:inv AS BOOLEAN) THEN NOW() ELSE NULL END,
                        CAST(:g AS SMALLINT))
            """), {"i": uuid.uuid4(), "l": LOBBY, "r": room, "w": pids[S3],
                   "t0": T0, "s": float(secs), "inv": bool(inval), "g": gn})
        await db.commit()
    return engine, sm, pids


async def _anchor(sm, g):
    async with sm() as db:
        return (await db.execute(text(main._FFA_PACE_ANCHOR_SQL),
                                 {"lid": LOBBY, "g": g})).scalar()


async def _prior(sm, g):
    """The production lookup, asked the way production asks it: about the ONE
    number the report named."""
    async with sm() as db:
        return (await db.execute(text(main._FFA_PRIOR_GAME_SQL),
                                 {"lid": LOBBY, "g": int(g)})).mappings().first()


def test_pg_a_second_row_for_one_game_is_not_the_next_games_anchor():
    """Control: anchor-per-row, anchor-includes-self."""
    require_pg()

    async def go():
        # game 1 reported at +686s, a second row for game 1 57s later.
        engine, sm, _ = await _setup([
            ("rm_211532_r1", 1, 686, False),
            ("rm_211531_r1", 1, 743, False),
        ])
        try:
            a2 = await _anchor(sm, 2)          # reporting game 2
            a1 = await _anchor(sm, 1)          # a further report OF game 1
            return a2, a1
        finally:
            await engine.dispose()
    a2, a1 = run(go())
    # The first receipt of game 1, not the second row's 57 seconds later.
    assert a2 == T0 + timedelta(seconds=686)
    assert a2 != T0 + timedelta(seconds=743)
    # And the game being reported is never its own anchor: for game 1 this
    # lobby has no OTHER game, so the endpoint falls back to lobby.created_at.
    assert a1 is None


def test_pg_a_low_number_late_in_a_sitting_cannot_widen_the_window():
    """The #283 direction. Control: anchor-less-than."""
    require_pg()

    async def go():
        engine, sm, _ = await _setup([
            ("rm_a_r1", 1, 600, False),
            ("rm_b_r2", 2, 1300, False),
            ("rm_c_r3", 3, 2000, False),
        ])
        try:
            return await _anchor(sm, 1), await _anchor(sm, 4)
        finally:
            await engine.dispose()
    as_one, as_four = run(go())
    # A report numbered 1 still anchors on game 3's receipt, not on lobby
    # creation: choosing the number must not choose the window.
    assert as_one is not None and as_four is not None
    assert as_one == as_four


def test_pg_rows_with_no_derivable_number_still_count_as_earlier_games():
    """Migration 327 leaves no NULL behind, so this arm covers only a reader
    running ahead of the migration — and a row it cannot group must not fall
    out of the window entirely."""
    require_pg()

    async def go():
        engine, sm, _ = await _setup([
            ("legacy_room", None, 600, False),
            ("rm_b_r2", 2, 1300, False),
        ])
        try:
            return await _anchor(sm, 2), await _anchor(sm, 9)
        finally:
            await engine.dispose()
    as_two, as_nine = run(go())
    assert as_two is not None            # the legacy row anchors game 2
    assert as_nine > as_two              # game 2's own receipt anchors game 9


def test_pg_the_prior_lookup_reads_the_row_that_holds_the_named_number():
    """Control: prior-lookup-takes-the-earliest-of-a-set (round 3's shape).

    The lookup used to bind a SET — the lobby's expected slot and the report's
    own `_rN` tail — under `game_number = ANY(...) ORDER BY ended_at LIMIT 1`.
    A set plus "earliest" is not "the row that holds the number the report
    named": with rows at BOTH numbers it returned whichever settled first, so a
    report naming the tail was compared against, and could be declared a
    duplicate of, a DIFFERENT game. The bind is now the single named number and
    the row is the one holding it; the typed cast (`CAST(:g AS SMALLINT)`)
    stays, because an untyped bind is the #275/#448 shape.

    Every gap state a live sitting can be in, enumerated against real rows."""
    require_pg()

    async def go():
        # Rows at BOTH numbers a round-3 report would have offered: the lobby's
        # expected slot 2 (settled LATER) and the tail 1 (settled first).
        engine, sm, _ = await _setup([
            ("rm_g1_r1", 1, 686, False),
            ("rm_g2_r2", 2, 1300, False),
            ("rm_dup_r3", 3, 2000, False),
            ("rm_dup2_r3", 3, 2100, False),
        ])
        try:
            return {
                "both_named_2": await _prior(sm, 2),
                "both_named_1": await _prior(sm, 1),
                "duplicate_pair": await _prior(sm, 3),
                "gap": await _prior(sm, 4),
                "above_domain": await _prior(sm, 999),
            }
        finally:
            await engine.dispose()
    got = run(go())
    # 1. Two numbers held, the report names 2: the row holding 2 comes back,
    #    though the row holding 1 is EARLIER. (Round 3 returned rm_g1_r1 here,
    #    and the caller then compared game 2's report against game 1's row.)
    assert got["both_named_2"] is not None
    assert got["both_named_2"]["photon_room_id"] == "rm_g2_r2"
    assert int(got["both_named_2"]["game_number"]) == 2
    # 2. The same table, the report names 1: the row holding 1.
    assert got["both_named_1"]["photon_room_id"] == "rm_g1_r1"
    # 3. Two rows hold ONE number (the verified-pair case that made the set
    #    ambiguous in the first place). ORDER BY ended_at makes the choice
    #    deterministic: the account that settled first. Both are live — neither
    #    was reversed — so this is a stable choice, not a claim about validity.
    assert got["duplicate_pair"]["photon_room_id"] == "rm_dup_r3"
    # 4. and 5. No row holds the named number: nothing comes back, and the
    #    refusal rule alone decides — which is the honest state for a number
    #    the lobby has not reached, and for one outside the sitting entirely.
    assert got["gap"] is None
    assert got["above_domain"] is None


def test_pg_a_tail_behind_the_slot_finds_its_own_game_not_the_next_one():
    """The finding's own failure scenario, end to end on real rows.

    A same-room sitting where the client's counter fell behind: the lobby is on
    slot 3 and the report names 2. The lookup has to hand the endpoint the row
    holding 2 — that is the game being re-reported, and comparing against it is
    what makes an honest redelivery a 409-with-evidence instead of a settlement
    of somebody else's game. The refusal rule and the lookup have to agree
    about WHICH number is in question."""
    require_pg()

    async def go():
        engine, sm, _ = await _setup([
            ("rm_g1_r1", 1, 600, False),
            ("rm_g2_r2", 2, 1300, False),
        ], games_played=2)
        try:
            async with sm() as db:
                _row, expected = await main._ffa_lock_lobby_slot(db, LOBBY)
                await db.rollback()
            return expected, await _prior(sm, 2), await _prior(sm, expected)
        finally:
            await engine.dispose()
    expected, named, at_slot = run(go())
    assert expected == 3
    # The named number is behind the slot, and the row it names is the one that
    # comes back — not game 1's, and not nothing.
    assert named is not None and int(named["game_number"]) == 2
    assert named["photon_room_id"] == "rm_g2_r2"
    # The slot itself is empty, which is what makes it the next settlement.
    assert at_slot is None
    # ...and the rule refuses the report, with the row above as its evidence.
    assert main._ffa_game_number_refusal(2, expected) is not None


def test_pg_a_reused_invalidated_number_cannot_widen_the_window():
    """Control: prior-skips-invalidated. Game 2 was reversed by an admin. A
    report reusing number 2 must still FIND that row, because the anchor keeps
    excluding number 2 — a lookup that skipped it plus an anchor that excluded
    it removes the 700s that game consumed and meters the second report against
    the wider window."""
    require_pg()

    async def go():
        engine, sm, _ = await _setup([
            ("rm_a_r1", 1, 600, False),
            ("rm_b_r2", 2, 1300, True),          # reversed by an admin
        ])
        try:
            found = await _prior(sm, 2)
            widened = await _anchor(sm, 2)       # if that report DID settle
            honest = await _anchor(sm, 3)
            return found, widened, honest
        finally:
            await engine.dispose()
    found, widened, honest = run(go())
    assert found is not None and found["photon_room_id"] == "rm_b_r2"
    assert found["invalidated_at"] is not None
    # The window the refusal protects: 700 seconds wider, and a wider window is
    # a larger paid_battles ceiling.
    assert honest - widened == timedelta(seconds=700)
    assert (main._ffa_paid_battles(400, (honest - T0).total_seconds(), 3)
            < main._ffa_paid_battles(400, (honest - widened).total_seconds()
                                     + (honest - T0).total_seconds(), 3))


def test_pg_the_recorded_vector_reads_back_for_the_comparison():
    require_pg()

    async def go():
        engine, sm, pids = await _setup([("rm_live_r1", 1, 686, False)])
        try:
            async with sm() as db:
                mid = (await db.execute(text(
                    "SELECT id FROM ffa_matches WHERE photon_room_id = 'rm_live_r1'"
                ))).scalar()
                for s, (r, p, k) in ROW_A.items():
                    await db.execute(text(
                        "INSERT INTO ffa_match_players (match_id, player_id,"
                        " rounds_won, points_total, kills, left_early, absent)"
                        " VALUES (:m, :p, :r, :t, :k, :le, :ab)"),
                        {"m": mid, "p": pids[s], "r": r, "t": p, "k": k,
                         "le": s == S2, "ab": False})
                await db.commit()
                rows = (await db.execute(text(main._FFA_PRIOR_VECTOR_SQL),
                                         {"m": mid})).mappings().all()
            return {r["steam_id"]: (int(r["rounds_won"]), int(r["points_total"]),
                                    int(r["kills"]), bool(r["left_early"]),
                                    bool(r["absent"])) for r in rows}
        finally:
            await engine.dispose()
    vec = run(go())
    # The five stored fields the comparison reads, off real columns — the two
    # new ones are what round 3 left out, so two accounts that disagreed about
    # who PLAYED were called agreement and the second settled (#430).
    assert vec == _vec(ROW_A, leave={S2: (True, False)})
    assert main._ffa_report_contradiction(S3, vec, _report(ROW_B, S1), True) is not None
    # The same tallies, and S2's early leave reported as it is recorded: same
    # account.
    same = _report(ROW_A, S3, leave={S2: (True, False, 99)})
    assert main._ffa_report_contradiction(S3, vec, same, True) is None
    # The same tallies with S2 reported as never having left. Round 4 called
    # this a contradiction on the strength of the raw flag; it is not one, and
    # the sentence that justified it here ("the settlement it asks for is a
    # different one") was the claim round 5 refuted. S2's stored absent is
    # False either way, so the seat is rated, paid and counted identically —
    # the only difference is the stored flag and the history line drawn from
    # it. See test_raw_left_early_is_not_a_contradiction_when_the_decision_
    # agrees for the cost of the refusal this used to produce.
    assert main._ffa_report_contradiction(S3, vec, _report(ROW_A, S3), True) is None
    # What a leave difference that DOES change the settlement still is: S2
    # scoreless and graced out of the game by one report, rated by the row.
    graced_vec = {S2: (0, 0, 0, True, False), S1: vec[S1], S3: vec[S3]}
    graced = _report(dict(ROW_A, **{S2: (0, 0, 0)}), S3, leave={S2: (True, False, 1)})
    assert main._ffa_report_contradiction(S3, graced_vec, graced, True) is not None


# ── migration 327, EXECUTED ───────────────────────────────────────────────
# asyncpg's simple-query path runs a whole file (BEGIN/COMMIT and DO blocks
# included) in one call, which is what `psql -f` does on the box.

MIGRATION_FIXTURE = """
DROP TABLE IF EXISTS ffa_matches CASCADE;
CREATE TABLE ffa_matches (
    id UUID PRIMARY KEY,
    lobby_id UUID,
    photon_room_id VARCHAR(64) NOT NULL,
    player_count SMALLINT NOT NULL DEFAULT 3,
    ended_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    invalidated_at TIMESTAMPTZ,
    CONSTRAINT uq_ffa_match_room UNIQUE (photon_room_id)
);
INSERT INTO ffa_matches (id, lobby_id, photon_room_id, ended_at) VALUES
  (gen_random_uuid(), '00000000-0000-0000-0000-0000000000a1', 'rmA_211531_r1', '2026-08-07 21:15:31Z'),
  (gen_random_uuid(), '00000000-0000-0000-0000-0000000000a1', 'rmA_211532_r1', '2026-08-07 21:16:28Z'),
  (gen_random_uuid(), '00000000-0000-0000-0000-0000000000a1', 'rmA_212540_r2', '2026-08-07 21:25:40Z'),
  (gen_random_uuid(), '00000000-0000-0000-0000-0000000000b2', 'rmB_100000_r4', '2026-08-08 10:00:00Z'),
  (gen_random_uuid(), '00000000-0000-0000-0000-0000000000b2', 'rmB_101000_r0', '2026-08-08 10:10:00Z'),
  (gen_random_uuid(), '00000000-0000-0000-0000-0000000000b2', 'rmB_102000_r99999', '2026-08-08 10:20:00Z'),
  (gen_random_uuid(), '00000000-0000-0000-0000-0000000000b2', 'rmB_no_tail_here', '2026-08-08 10:30:00Z'),
  (gen_random_uuid(), NULL, 'orphan_room_no_tail', '2026-08-09 09:00:00Z');
"""

# The one edit that neuters the tail backfill without touching anything else:
# its own SET clause is the unique anchor.
_BACKFILL_ANCHOR = "       game_number_source = 'room_tail'\n WHERE game_number IS NULL"
_BACKFILL_NEUTERED = ("       game_number_source = 'room_tail'\n"
                      " WHERE FALSE AND game_number IS NULL")


async def _raw_pg():
    import asyncpg
    return await asyncpg.connect(require_pg().replace("+asyncpg", ""))


async def _unwedge(conn):
    """A migration that RAISES does so inside its own BEGIN, so the connection
    is left in an aborted transaction block and every later statement is
    ignored. The tests that assert on a refusal keep using the connection
    afterwards, so they end that block first."""
    try:
        await conn.execute("ROLLBACK")
    except Exception:
        pass


# ── two sessions, one lobby ───────────────────────────────────────────────

def test_the_lock_the_derivation_and_the_increment_are_one_transaction():
    """Control: commit-between-the-lock-and-the-increment.

    The live test below proves the LOCK holds. What it cannot see is the
    endpoint deciding to commit in the middle — at which point the row unlocks
    with games_played unchanged, the waiting report reads the same number, and
    two settlements take one slot with the lock still nominally in place. So
    the transaction SCOPE is asserted here, structurally, on the production
    source: between taking the lock and consuming the slot there is no commit,
    and the advance is the last thing before the one that ends it."""
    src = _code_lines(_endpoint_src())
    lock = src.index("await _ffa_lock_lobby_slot(")
    advance = src.index("await _ffa_advance_lobby_slot(")
    commit = src.index("await db.commit()", advance)
    assert lock < advance < commit
    # Nothing commits in between. Measured on the CODE, with the comments
    # stripped — a prose mention of `await db.commit()` is not a commit, and a
    # check that a comment can redden is a check that a comment can also keep
    # green (#441). `db.commit()` inside the quarantine helper is a different
    # session-level call in a DIFFERENT function; this span is the endpoint's.
    assert "await db.commit()" not in src[lock:advance]
    # ...and the advance is not itself inside a savepoint that a later failure
    # could roll back while the settlement stands.
    assert "begin_nested" not in src[advance:commit]
    # Exactly one advance per settlement, in the whole endpoint (#330/#279).
    assert src.count("_ffa_advance_lobby_slot(") == 1
    # ...and the increment is nowhere else in the file either: one rule, one
    # place, so the slot cannot be consumed by a second writer's copy.
    whole = _code_lines(pathlib.Path(main.__file__).read_text(encoding="utf-8"))
    assert whole.count("games_played = games_played + 1") == 1


def test_pg_two_reports_for_one_lobby_cannot_settle_the_same_number():
    """The concurrency bar, on two real connections, through PRODUCTION's own
    functions.

    Report A calls `_ffa_lock_lobby_slot` and derives its slot. Report B,
    arriving while A is still open, must WAIT on that row — and when it is let
    through it must RE-READ, not reuse the value it would have seen (#208: the
    second half of a split operation working from a snapshot is how a settled
    row gets acted on twice).

    Round 3's version lifted the endpoint's SQL STRINGS out with a regex and
    ran them itself, on its own connections, in its own transaction — so it
    proved PostgreSQL's row locking and nothing about production's ordering.
    Moving the derivation above the lock, or splitting the transaction in two,
    left it green. It now calls `main._ffa_lock_lobby_slot` and
    `main._ffa_advance_lobby_slot` directly, so the derivation, the lock and
    the increment under test are the ones the endpoint runs.

    Control: settlement-lock-removed-live (r8) -- the row lock comes off
    `_FFA_LOBBY_LOCK_SQL` entirely and B returns immediately with
    games_played = 0, deriving 1 exactly as A did. Round 7 described that
    mutation as hand-run, which is a sentence about a run nobody can check; it
    is in the committed runner now, with its RED line and its inert twin."""
    require_pg()

    async def go():
        engine, sm, pids = await _setup([], games_played=0)
        # Two SEPARATE sessions: two connections, two transactions.
        a, b = sm(), sm()
        try:
            await b.execute(text("SET lock_timeout = '10s'"))
            row_a, expected_a = await main._ffa_lock_lobby_slot(a, LOBBY)

            waiting = asyncio.create_task(main._ffa_lock_lobby_slot(b, LOBBY))
            await asyncio.sleep(0.5)
            blocked = not waiting.done()

            # A settles its game and consumes the slot, in the SAME
            # transaction as its lock, exactly as the endpoint does.
            await a.execute(text(
                "INSERT INTO ffa_matches (id, lobby_id, photon_room_id,"
                " winner_id, ended_at, game_number) VALUES"
                " (:i, :l, :r, :w, NOW(), CAST(:g AS SMALLINT))"),
                {"i": uuid.uuid4(), "l": LOBBY,
                 "r": f"rm_211531_r{expected_a}", "w": pids[S3],
                 "g": expected_a})
            await main._ffa_advance_lobby_slot(a, LOBBY)
            await a.commit()

            _row_b, expected_b = await asyncio.wait_for(waiting, 10)
            await b.rollback()
            # What B's own already-recorded lookup sees when its report still
            # carries A's number as its tail — production's statement, with
            # production's typed bind.
            found = await _prior(sm, expected_a)
            return blocked, expected_a, expected_b, found
        finally:
            await a.close()
            await b.close()
            await engine.dispose()

    blocked, expected_a, expected_b, found = run(go())
    assert blocked, ("the second report did not wait on the lobby row, so both "
                     "derived the same number from the same snapshot")
    assert expected_a == 1
    assert expected_b == 2, "the second report reused a stale games_played"
    # ...and A's game is found rather than settled again.
    assert found is not None
    assert int(found["game_number"]) == expected_a
    assert found["photon_room_id"] == f"rm_211531_r{expected_a}"
    # The tail B would have carried for that same game is now behind its own
    # slot, and the rule refuses it outright when no row is there to compare.
    assert main._ffa_game_number_refusal(expected_a, expected_b) is not None


def test_pg_a_refusal_carries_the_lobbys_progress_off_the_locked_row():
    """The resync half of the same lock, as a live read.

    Every refusal the report path raises answers with the lobby's authoritative
    progress, and that progress comes off the row this transaction locked — so
    what a refused client adopts is the committed counter, not a prediction of
    it. RJ-CLIENT-RESYNC-CONTRACT.md is what consumes these three fields."""
    require_pg()

    async def go():
        engine, sm, _ = await _setup([("rm_g1_r1", 1, 600, False),
                                      ("rm_g2_r2", 2, 1300, False)],
                                     games_played=2)
        try:
            async with sm() as db:
                _row, expected = await main._ffa_lock_lobby_slot(db, LOBBY)
                await db.rollback()
            return expected
        finally:
            await engine.dispose()
    expected = run(go())
    progress = main._ffa_progress(expected - 1)
    assert progress == {"games_played": 2, "expected_game": 3}
    # A refusal about a number the lobby already holds says so, and names the
    # settled game, which is what lets the client drop that outbox entry as
    # terminal rather than retry it forever.
    settled = main._ffa_progress(expected - 1, settled_game=2)
    assert settled["settled_game"] == 2
    assert settled["games_played"] == 2 and settled["expected_game"] == 3


def test_pg_migration_327_numbers_every_row_and_rerunning_changes_nothing():
    require_pg()
    sql = MIGRATION.read_text(encoding="utf-8")

    async def go():
        conn = await _raw_pg()
        try:
            await conn.execute(MIGRATION_FIXTURE)
            await conn.execute(sql)
            first = await conn.fetch(
                "SELECT photon_room_id, game_number, game_number_source"
                "  FROM ffa_matches ORDER BY photon_room_id")
            await conn.execute(sql)                       # idempotence
            second = await conn.fetch(
                "SELECT photon_room_id, game_number, game_number_source"
                "  FROM ffa_matches ORDER BY photon_room_id")
            # The migration-first window: the OLD api's INSERT names no
            # game_number and must still land, numbered by the trigger.
            await conn.execute(
                "INSERT INTO ffa_matches (id, lobby_id, photon_room_id, ended_at)"
                " VALUES (gen_random_uuid(),"
                " '00000000-0000-0000-0000-0000000000a1', 'rmA_215000_r3',"
                " '2026-08-07 21:50:00Z')")
            await conn.execute(
                "INSERT INTO ffa_matches (id, lobby_id, photon_room_id, ended_at)"
                " VALUES (gen_random_uuid(),"
                " '00000000-0000-0000-0000-0000000000a1', 'rmA_no_tail',"
                " '2026-08-07 21:55:00Z')")
            old_api = await conn.fetch(
                "SELECT photon_room_id, game_number, game_number_source"
                "  FROM ffa_matches"
                " WHERE photon_room_id IN ('rmA_215000_r3', 'rmA_no_tail')"
                " ORDER BY photon_room_id")
            try:
                await conn.execute(
                    "INSERT INTO ffa_matches (id, lobby_id, photon_room_id,"
                    " ended_at, game_number) VALUES (gen_random_uuid(), NULL,"
                    " 'over_bound', NOW(), 1000)")
                over = "accepted"
            except Exception as ex:
                over = type(ex).__name__
            # NOT NULL, executed rather than grepped: with the trigger out of
            # the way there is nothing left to supply a number, and the column
            # itself has to be what refuses.
            await conn.execute("ALTER TABLE ffa_matches"
                               " DISABLE TRIGGER trg_ffa_matches_game_number")
            try:
                await conn.execute(
                    "INSERT INTO ffa_matches (id, lobby_id, photon_room_id,"
                    " ended_at) VALUES (gen_random_uuid(), NULL,"
                    " 'unnumbered', NOW())")
                unnumbered = "accepted"
            except Exception as ex:
                unnumbered = type(ex).__name__
            return first, second, old_api, over, unnumbered
        finally:
            await conn.close()

    first, second, old_api, over, unnumbered = run(go())
    by_room = {r["photon_room_id"]: (r["game_number"], r["game_number_source"])
               for r in first}
    # Usable tails taken as-is, including the two rows that share game 1.
    assert by_room["rmA_211531_r1"] == (1, "room_tail")
    assert by_room["rmA_211532_r1"] == (1, "room_tail")
    assert by_room["rmA_212540_r2"] == (2, "room_tail")
    assert by_room["rmB_100000_r4"] == (4, "room_tail")
    # Zero, over-domain and absent tails: the lobby's own ended_at sequence,
    # above the highest tail that lobby carries, so they cannot collide with it.
    assert by_room["rmB_101000_r0"] == (5, "sequence")
    assert by_room["rmB_102000_r99999"] == (6, "sequence")
    assert by_room["rmB_no_tail_here"] == (7, "sequence")
    # A row whose lobby row is gone (lobby_id NULL) still gets a number.
    assert by_room["orphan_room_no_tail"] == (1, "sequence")
    assert all(1 <= v[0] <= 999 for v in by_room.values())
    # Re-running is a no-op, row for row.
    assert [tuple(r) for r in first] == [tuple(r) for r in second]
    # The old api's unnumbered INSERT lands, numbered by both rules.
    got = {r["photon_room_id"]: (r["game_number"], r["game_number_source"])
           for r in old_api}
    assert got["rmA_215000_r3"] == (3, "room_tail")
    # ...and one without a tail takes the lobby's next free number, above the
    # 3 the row inserted just before it took from its own tail.
    assert got["rmA_no_tail"] == (4, "sequence")
    # The bound is the CHECK's, not SMALLINT's width.
    assert over == "CheckViolationError"
    # ...and the column is total, so no writer can leave a row unnumbered.
    assert unnumbered == "NotNullViolationError"


def test_pg_migration_327_post_check_fails_when_the_backfill_is_neutered():
    """The migration's own mutation control, as a test rather than a note in a
    handover file. Neuter the tail backfill and the post-check must RAISE and
    take the whole file down with it — a post-check that only counted NULLs
    would pass here, because the sequence arm fills them all in."""
    require_pg()
    sql = MIGRATION.read_text(encoding="utf-8")
    assert sql.count(_BACKFILL_ANCHOR) == 1
    neutered = sql.replace(_BACKFILL_ANCHOR, _BACKFILL_NEUTERED)

    async def go():
        conn = await _raw_pg()
        try:
            await conn.execute(MIGRATION_FIXTURE)
            try:
                await conn.execute(neutered)
                return "accepted"
            except Exception as ex:
                return str(ex)
        finally:
            await conn.close()

    why = run(go())
    assert "derivable _rN tail" in why, why


def test_pg_the_trigger_never_hands_back_a_number_the_lobby_is_using():
    """Controls: trigger-clamps-999, trigger-raises-on-a-full-tail.

    `LEAST(MAX(game_number) + 1, 999)` is total against the CHECK and wrong: it
    hands back a number the lobby is already using, so a writer that supplied
    none would silently share a slot with a settled game.

    Round 3 replaced the clamp with a RAISE — correct about the collision and
    wrong about the cost (#430). MAX+1 leaves the domain for any lobby holding
    999, whatever else is free, and that lobby's next unnumbered insert then
    reaches the pre-327 api as an HTTP 500: a settled game destroyed over a
    number the lobby had 998 of. The arm now falls back to the lobby's LOWEST
    FREE number, and only a lobby with no free number at all is refused.

    Both arms, executed: the fallback lands on a free number, and the refusal
    still fires when there is genuinely nothing left."""
    require_pg()
    sql = MIGRATION.read_text(encoding="utf-8")
    # The clamp is gone from the STATEMENTS; it survives only in the note that
    # explains why (comment lines start with `--`).
    code = "\n".join(ln for ln in sql.splitlines()
                     if not ln.strip().startswith("--"))
    assert "LEAST(" not in code
    assert "NEW.game_number := tail::SMALLINT;" in code

    C3 = "00000000-0000-0000-0000-0000000000c3"
    C4 = "00000000-0000-0000-0000-0000000000c4"

    async def go():
        conn = await _raw_pg()
        try:
            await conn.execute(MIGRATION_FIXTURE)
            await conn.execute(sql)
            # Lobby c3 holds 999 and nothing else. MAX + 1 is 1000.
            await conn.execute(
                "INSERT INTO ffa_matches (id, lobby_id, photon_room_id,"
                " ended_at, game_number) VALUES (gen_random_uuid(),"
                " $1, 'c3_r999', NOW(), 999)", C3)
            await conn.execute(
                "INSERT INTO ffa_matches (id, lobby_id, photon_room_id,"
                " ended_at) VALUES (gen_random_uuid(), $1, 'c3_no_tail', NOW())",
                C3)
            fell_back = await conn.fetchrow(
                "SELECT game_number, game_number_source FROM ffa_matches"
                " WHERE photon_room_id = 'c3_no_tail'")
            # ...and it is FREE, not a reuse: c3 now holds two distinct numbers.
            distinct = await conn.fetchval(
                "SELECT COUNT(DISTINCT game_number) FROM ffa_matches"
                " WHERE lobby_id = $1", C3)
            # Lobby c4 holds every number in 1..999: there is nothing to give.
            await conn.execute(
                "INSERT INTO ffa_matches (id, lobby_id, photon_room_id,"
                " ended_at, game_number)"
                " SELECT gen_random_uuid(), $1, 'c4_r' || n, NOW(),"
                "        n::SMALLINT FROM generate_series(1, 999) AS n", C4)
            try:
                await conn.execute(
                    "INSERT INTO ffa_matches (id, lobby_id, photon_room_id,"
                    " ended_at) VALUES (gen_random_uuid(), $1,"
                    " 'c4_no_tail', NOW())", C4)
                why = "accepted"
            except Exception as ex:
                why = str(ex)
                await _unwedge(conn)
            landed = await conn.fetchval(
                "SELECT COUNT(*) FROM ffa_matches WHERE photon_room_id = 'c4_no_tail'")
            return fell_back, distinct, why, landed
        finally:
            await conn.close()

    fell_back, distinct, why, landed = run(go())
    # The fallback: the lobby's lowest free number, flagged as neither the
    # writer's nor the room id's.
    assert int(fell_back["game_number"]) == 1
    assert fell_back["game_number_source"] == "sequence"
    assert distinct == 2                    # 999 and 1, not 999 twice
    # The refusal, for the one input that has no answer — and it names the
    # lobby rather than failing on the CHECK, so an operator reading it knows
    # which sitting is full.
    assert "holds every number in 1..999" in why, why
    assert landed == 0                      # refused, not clamped onto 999


def test_pg_the_post_check_covers_a_writer_row_that_stored_another_number():
    """Control: postcheck-sequence-only.

    The assertion used to end `AND game_number_source = 'sequence'`, which made
    it blind to exactly the rows a RE-RUN would be checking: rows a writer
    supplied. Since the api refuses any report whose `_rN` tail is not the
    number it stores, such a row is a real fault — and the migration is where
    it gets caught rather than lived with."""
    require_pg()
    sql = MIGRATION.read_text(encoding="utf-8")

    async def go():
        conn = await _raw_pg()
        try:
            await conn.execute(MIGRATION_FIXTURE)
            await conn.execute(sql)
            # A writer row whose stored number is not the number its room names.
            await conn.execute(
                "INSERT INTO ffa_matches (id, lobby_id, photon_room_id,"
                " ended_at, game_number) VALUES (gen_random_uuid(),"
                " '00000000-0000-0000-0000-0000000000d4', 'd4_120000_r7',"
                " NOW(), 2)")
            src = await conn.fetchval(
                "SELECT game_number_source FROM ffa_matches"
                " WHERE photon_room_id = 'd4_120000_r7'")
            try:
                await conn.execute(sql)
                why = "accepted"
            except Exception as ex:
                why = str(ex)
                await _unwedge(conn)
            # ...and with that row gone the file passes again, so the assertion
            # is about the row and not about the re-run.
            await conn.execute(
                "DELETE FROM ffa_matches WHERE photon_room_id = 'd4_120000_r7'")
            await conn.execute(sql)
            return src, why
        finally:
            await conn.close()

    src, why = run(go())
    assert src == "writer"
    assert "derivable _rN tail" in why, why


def test_the_neutered_control_is_exactly_one_predicate_away():
    """Negative control on the control (#391): the mutation must be the ONE
    edit, or a red result proves nothing about the post-check."""
    sql = MIGRATION.read_text(encoding="utf-8")
    neutered = sql.replace(_BACKFILL_ANCHOR, _BACKFILL_NEUTERED)
    diff = [(a, b) for a, b in zip(sql.splitlines(), neutered.splitlines())
            if a != b]
    assert len(diff) == 1
    assert re.match(r"^ WHERE game_number IS NULL$", diff[0][0])
    assert len(sql.splitlines()) == len(neutered.splitlines())


# ── round 5: the request path, EXECUTED ───────────────────────────────────
# Round 4 closed every one of its own claims with tests that never ran the
# endpoint. `grep -rn "submit_ffa_match(" backend/tests` found no caller, and
# no test issued a request to /api/v1/ffa/matches; the three tests §1 of the
# client contract names as the server-side pin all assert on
# inspect.getsource(...) substrings. So a tree whose endpoint raised
# TypeError on its third statement — round 4 gave _ffa_replay_echo a seventh
# required parameter and updated one of its two call sites — reported 1708
# passed / 0 failed, and every one of the fifteen mutation controls inherited
# the same blindness: a textual mutation cannot tell a live path from an
# unreachable one (#286/#405 verify reachability before logic; #313/#340/#465
# not reviewed until it has RUN).
#
# Two things close that, at two different costs:
#   * the binding sweep below, which runs in EVERY mode including opt-out and
#     needs no database. It is the defect's CLASS — a helper gains a
#     parameter, one call site is updated — and not the one line;
#   * the live tests at the end of this section, which build a lobby and a
#     recorded game and AWAIT submit_ffa_match, so the request path is
#     executed and the body it answers with is read off a real response.



def _non_docstring_strings(src: str) -> list:
    """Every string literal in `src` that is NOT a docstring.

    The statements, separated from the prose about them. A file-wide grep for
    an SQL form cannot tell the two apart, so a docstring that names the shape
    it replaced would either defeat the check or force the explanation out of
    the code -- and a check that a comment can redden is one a comment can also
    keep green (#441). Docstrings are the first statement of a module, class or
    function, which is exactly what this excludes."""
    tree = ast.parse(src)
    docs = set()
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if not isinstance(node, (ast.Module, ast.ClassDef,
                                 ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if (body and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)):
            docs.add(id(body[0].value))
    return [n.value for n in ast.walk(tree)
            if isinstance(n, ast.Constant) and isinstance(n.value, str)
            and id(n) not in docs]

def _own_functions(tree):
    """name -> the single top-level-or-nested def, for names defined once.

    A name defined twice is skipped rather than guessed at: the sweep is
    about call sites whose target is unambiguous."""
    seen = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            seen.setdefault(node.name, []).append(node)
    return {k: v[0] for k, v in seen.items() if len(v) == 1}


def _binding_failures(src: str):
    """Every call in `src` to a function `src` itself defines that could not
    bind, as (lineno, name, reason)."""
    tree = ast.parse(src)
    defs = _own_functions(tree)
    out = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)):
            continue
        target = defs.get(node.func.id)
        if target is None:
            continue
        args = target.args
        if args.vararg is not None or args.kwarg is not None:
            continue                      # the def accepts anything
        if any(isinstance(a, ast.Starred) for a in node.args):
            continue                      # f(*seq) — the count is runtime
        if any(k.arg is None for k in node.keywords):
            continue                      # f(**d) — the names are runtime
        # A POSITIONAL-ONLY parameter cannot be bound by keyword, so the two
        # groups are kept apart. Round 5 folded posonlyargs into one
        # `positional` list and then tested keywords against it, which made
        # `f(a, b, /)` called as `f(a=1, b=2)` read as fully bound — the call
        # raises TypeError at runtime and the sweep said nothing. One `/` in a
        # def is all that takes, which is why it is tested below by mutating a
        # real signature rather than only a synthetic one.
        posonly = [p.arg for p in args.posonlyargs]
        byname = [p.arg for p in args.args]
        positional = posonly + byname
        required = positional[:len(positional) - len(args.defaults)]
        kwonly = [p.arg for p in args.kwonlyargs]
        kwonly_required = [p.arg for p, d in zip(args.kwonlyargs, args.kw_defaults)
                           if d is None]
        given_kw = [k.arg for k in node.keywords]
        if len(node.args) > len(positional):
            out.append((node.lineno, node.func.id,
                        f"{len(node.args)} positional into {len(positional)}"))
            continue
        nameable = set(byname) | set(kwonly)
        # Only a keyword the def can actually accept binds anything.
        bound = set(positional[:len(node.args)]) | (set(given_kw) & nameable)
        missing = [a for a in required if a not in bound]
        missing += [a for a in kwonly_required if a not in bound]
        unknown = [g for g in given_kw if g not in nameable]
        duplicated = [a for a in positional[:len(node.args)]
                      if a in given_kw and a in nameable]
        if missing or unknown or duplicated:
            out.append((node.lineno, node.func.id,
                        f"missing={missing} unknown={unknown} duplicated={duplicated}"))
    return out


def test_every_call_in_main_binds_to_the_function_it_names():
    """Control: replay-echo-call-short (r5), and the whole class it belongs to.

    The round-4 tree shipped `_ffa_replay_echo(db, report, lobby_uuid,
    id_by_steam, len(report.players), kills_in_canonical)` against a def
    carrying seven required parameters, as the third statement of
    submit_ffa_match's body — so every POST /api/v1/ffa/matches raised
    TypeError before it could do anything, and the suite was green. This is
    that fact asked of the whole module rather than of one line, it costs one
    parse, and it runs in the opt-out mode too, where nothing else can see it.

    It is deliberately conservative: a def taking *args/**kwargs, a call
    unpacking *seq or **d, and a name this module defines twice are all
    skipped, because for those the count is not decidable here. What is left
    is the shape that actually happened."""
    src = pathlib.Path(main.__file__).read_text(encoding="utf-8")
    failures = _binding_failures(src)
    assert failures == [], "\n".join(
        f"main.py:{ln}: {name}() {why}" for ln, name, why in failures)


def test_the_binding_sweep_can_actually_fail():
    """A check that cannot fail is worse than no check (#342/#431). The sweep
    is shown to catch the exact round-4 defect — a call one argument short of
    its def — and to stay quiet on the forms it deliberately skips."""
    caught = _binding_failures(
        "async def f(a, b, c):\n    return a\n\nasync def g():\n    return await f(1, 2)\n")
    assert len(caught) == 1 and caught[0][1] == "f", caught
    assert "missing=['c']" in caught[0][2], caught
    # ...and the skips are real skips, not accidental passes.
    assert _binding_failures("def f(a, b, c):\n    pass\n\ndef g(s):\n    f(*s)\n") == []
    assert _binding_failures("def f(a, **kw):\n    pass\n\ndef g():\n    f(1, z=2)\n") == []
    assert _binding_failures("def f(a, b=1):\n    pass\n\ndef g():\n    f(1)\n") == []
    # A name this module defines twice is not guessed at.
    assert _binding_failures(
        "def f(a):\n    pass\n\ndef f(a, b):\n    pass\n\ndef g():\n    f(1)\n") == []
    # An unknown keyword and a doubly-supplied parameter are both caught.
    assert len(_binding_failures("def f(a):\n    pass\n\ndef g():\n    f(1, z=2)\n")) == 1
    assert len(_binding_failures("def f(a, b):\n    pass\n\ndef g():\n    f(1, a=2)\n")) == 1
    # A POSITIONAL-ONLY parameter named by keyword is a TypeError, and round 5
    # read it as bound. Both halves: the call that raises is caught...
    posonly = _binding_failures(
        "def f(a, b, /):\n    pass\n\ndef g():\n    f(a=1, b=2)\n")
    assert len(posonly) == 1 and "unknown=['a', 'b']" in posonly[0][2], posonly
    # ...and a legal call against the same signature is still silent, so the
    # rule is "a keyword may not name a posonly parameter" and not "any `/` is
    # a failure".
    assert _binding_failures("def f(a, b, /):\n    pass\n\ndef g():\n    f(1, 2)\n") == []
    assert _binding_failures(
        "def f(a, /, b):\n    pass\n\ndef g():\n    f(1, b=2)\n") == []
    # A posonly parameter left unsupplied is still missing, not unknown.
    assert "missing=['b']" in _binding_failures(
        "def f(a, b, /):\n    pass\n\ndef g():\n    f(1)\n")[0][2]


def _awaited_endpoint_calls(src: str) -> list:
    """The lines of `src` holding an AWAITED call of main.submit_ffa_match,
    taken off the AST rather than out of the text.

    A SUBSTRING scan cannot ask this question about the file it lives in: the
    line carrying the pattern contains the pattern, so the scan matches its
    own predicate and the assertion built on it can never fail (#342/#431 — a
    check that cannot fail is worse than no check). That is exactly what the
    first draft of the test below did, and the control is what found it:
    `endpoint-never-called` came back GREEN against a copy of this file whose
    only await of the endpoint had been replaced by `return None`. A string
    literal is not an Await node, so this reading tells the two apart."""
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return []
    # THE RECEIVER IS PART OF THE QUESTION. Round 5 matched any attribute call
    # named submit_ffa_match, so `await dummy.submit_ffa_match(...)` — a stub,
    # a fake, a module-shaped stand-in — satisfied it while the production
    # endpoint stayed unexecuted, which is the round-4 defect wearing a
    # different hat. It has to be `main`, which is how every other test in this
    # file reaches production.
    return [node.lineno for node in ast.walk(tree)
            if isinstance(node, ast.Await)
            and isinstance(node.value, ast.Call)
            and isinstance(node.value.func, ast.Attribute)
            and node.value.func.attr == "submit_ffa_match"
            and isinstance(node.value.func.value, ast.Name)
            and node.value.func.value.id == "main"]


def test_this_file_actually_executes_the_report_endpoint():
    """Control: endpoint-never-called (r5).

    The round-4 suite asserted on the endpoint's SOURCE and never ran it. This
    pins that at least one test in this module awaits the endpoint itself, so
    the file cannot quietly go back to reading text about a path nobody
    enters. It asserts on this module's own source, which is the only place
    the fact lives."""
    own = pathlib.Path(__file__).read_text(encoding="utf-8")
    assert _awaited_endpoint_calls(own), (
        "no test in this file awaits main.submit_ffa_match; the endpoint's "
        "own request path would be unexercised")
    # ...and the detector CAN fail, which is the half the first draft lacked:
    # a file that only mentions the call in a string is not a caller of it.
    assert _awaited_endpoint_calls(
        'MENTION = "await main.submit_ffa_match(report, req, db)"\n') == []
    assert len(_awaited_endpoint_calls(
        "async def t(db):\n    return await main.submit_ffa_match(r, q, db)\n")) == 1
    # ...and neither is a call on something that merely has the same attribute
    # name. Round 5's detector ignored the receiver, so a stub satisfied it
    # while production went unexecuted (#342/#431 again, one level up).
    assert _awaited_endpoint_calls(
        "async def t(db):\n    return await dummy.submit_ffa_match(r, q, db)\n") == []
    assert _awaited_endpoint_calls(
        "async def t(db):\n    return await self.main.submit_ffa_match(r, q, db)\n") == []


# ── the strict refund: its bound, and the guard it must not inherit ───────

class _RefundBatchResult:
    def __init__(self, rows=None, scalar=None):
        self._rows, self._scalar = rows or [], scalar

    def mappings(self):
        return self

    def all(self):
        return self._rows

    def scalar(self):
        return self._scalar


class _RefundDb:
    """The narrowest stand-in the strict refund actually uses: it answers the
    batch SELECT from a queue of batches, claims every UPDATE, and records
    what was added. Enough to EXECUTE the loop and count its passes, which is
    the thing the bound is about."""

    def __init__(self, batches, covers=True):
        self.batches = list(batches)
        self.reads = 0
        self.claimed = 0
        self.gold_moves = 0
        self.added = []
        # Whether the conditional gold UPDATE finds a row. It is the whole
        # question _return_stake_exactly asks: a row means the balance covered
        # the exact stake, no row means it did not. `0` is a real balance, so
        # the covered answer has to be a falsy value that is not None.
        self.covers = covers

    async def execute(self, stmt, params=None):
        sql = str(stmt)
        if sql.lstrip().startswith("SELECT id, player_id, amount"):
            self.reads += 1
            rows = self.batches.pop(0) if self.batches else []
            return _RefundBatchResult(rows=rows)
        if "UPDATE ffa_bets" in sql:
            self.claimed += 1
            return _RefundBatchResult(scalar=uuid.uuid4())
        if "UPDATE players" in sql:
            self.gold_moves += 1
            return _RefundBatchResult(scalar=0 if self.covers else None)
        return _RefundBatchResult(scalar=None)

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        return None


def _bet_batch(n):
    return [{"id": uuid.uuid4(), "player_id": uuid.uuid4(), "amount": 10}
            for _ in range(n)]


def test_a_game_whose_wagers_the_refund_moved_in_full_is_not_called_an_overflow():
    """Control: refund-bound-off-by-one (r5).

    `for _ in range(FFA_REFUND_MAX_BATCHES)` returns only on a read that comes
    back EMPTY, so the 50th pass could refund its 200 rows and then fall
    straight through to `raise RuntimeError(... after 50 passes of 200)`. The
    clean capacity was 9 800 wagers while the constant's comment, the
    docstring and the error all said 10 000 — and the caller turns the raise
    into a 503, rolls the settlement back, and repeats it on every retry: a
    game whose wagers were in fact fully refundable would have been
    permanently unsettleable, reported as an overflow that did not happen.

    Executed, not read: the loop runs against exactly the bound."""
    full = main.FFA_REFUND_MAX_BATCHES
    db = _RefundDb([_bet_batch(200) for _ in range(full)])
    moved = run(main._refund_ffa_game_bets_strict(db, uuid.uuid4(), 3, "t"))
    assert moved == full * 200
    assert db.reads == full + 1, "the confirming empty read never happened"


def test_one_wager_past_the_bound_still_refuses():
    """The other side of the same edge: the bound has to still be a bound, or
    the fix is just a larger silent truncation (#391 — the negative control
    for the test above)."""
    full = main.FFA_REFUND_MAX_BATCHES
    db = _RefundDb([_bet_batch(200) for _ in range(full + 1)])
    with pytest.raises(RuntimeError) as ex:
        run(main._refund_ffa_game_bets_strict(db, uuid.uuid4(), 3, "t"))
    assert f"{full} passes of 200" in str(ex.value)
    assert f"{full * 200} refunded" in str(ex.value)


def test_the_strict_refund_does_not_inherit_a_guard_it_cannot_afford():
    """Control: strict-refund-asserts-service (r5).

    #412 in the other direction. _refund_ffa_lobby_bets asserts no service
    account is among the subjects and swallows the 403 in its own savepoint —
    a skipped batch, which that caller can afford. The strict helper has no
    savepoint and its failure is the report's answer, so the same assertion
    reached the reporter as a bare HTTPException(403): no progress fields, no
    captured payload, terminal by the client's rule, and identical on every
    retry — the game never rated, never paid, no evidence kept. It is also the
    wrong question for this operation: a refund RETURNS a stake, which is the
    one movement that takes a service account back out of the economy, and
    refusing it strands the stake and freezes the lobby.

    The route keeps its own guard, which is what the service-policy gate
    measures: submit_ffa_match asserts on the reported roster before any of
    this runs."""
    src = inspect.getsource(main._refund_ffa_game_bets_strict)
    assert "_assert_no_service_subject" not in _code_lines(src)
    # The fail-soft sweep still has it — the two polarities are the point, and
    # a sweep that lost it would be a different defect.
    assert "_assert_no_service_subject" in _code_lines(
        inspect.getsource(main._refund_ffa_lobby_bets))
    # ...and the endpoint's own guard, on the roster it is about to rate.
    assert "_assert_no_service_subject(db, affected_steam_ids=steams)" in _endpoint_src()


def test_a_refusal_raised_out_of_the_skew_refund_still_carries_the_progress():
    """Control: skew-refusal-bare-http (r5).

    Below the lobby lock every answer this endpoint gives carries the lobby's
    progress. The skew refund's handler used to re-raise an HTTPException
    unchanged, which serialises as `detail` alone — so the one answer whose
    whole purpose is to tell a client where the lobby is would have told it
    nothing. The status is kept exactly as raised (it is what says terminal or
    retryable); only the body gains the fields."""
    src = _endpoint_src()
    block = src[src.index("await _refund_ffa_game_bets_strict("):]
    block = block[:block.index("await _ffa_advance_lobby_slot")]
    assert "except HTTPException:\n            raise" not in block
    assert "except FfaReportRefusal:" in block
    assert "raise FfaReportRefusal(_skew_http.status_code" in block
    # Still exactly one generic arm, and it still answers 503 with progress.
    assert block.count("raise FfaReportRefusal(") == 2
    assert "_progress)" in block


# ── the comparison: what it may and may not call a contradiction ──────────

def test_raw_left_early_is_not_a_contradiction_when_the_decision_agrees():
    """Control: left-early-compared-raw (r5).

    _ffa_report_contradiction's docstring says WHAT IS COMPARED IS WHAT THE
    SETTLEMENT ACTS ON, and round 4 then compared raw `left_early` as well as
    the effective decision. With the decision equal, left_early moves no
    rating, gold, XP, placement or beaten count — only the stored flag and
    whether game_points_at_leave is kept beside it. It is unsigned, outside
    the frozen canonical, and two honest clients of a seat that drops on the
    winning point really do differ on it; the cost of calling that a
    contradiction is a terminal 409 to an honest reporter, a spent quarantine
    row and an operator review item over one identical settlement (#430)."""
    # Above the grace threshold, so neither reading marks the seat unrated:
    # the two reports reach the SAME effective decision and differ only in the
    # raw claim.
    gp = main.FFA_LEAVE_GRACE_POINTS + 3
    rec = _vec(ROW_A, leave={S2: (True, False)})
    same_decision = _report(ROW_A, S3, leave={S2: (False, False, None)})
    assert main._ffa_report_contradiction(S3, rec, same_decision, True) is None
    # ...and the other way round, because the detector is symmetric.
    rec_plain = _vec(ROW_A)
    claimed = _report(ROW_A, S3, leave={S2: (True, False, gp)})
    assert main._ffa_report_contradiction(S3, rec_plain, claimed, True) is None
    # The claim is still the INPUT to the decision, so a left_early difference
    # that changes who PLAYED is caught where it means something.
    zeroed = dict(ROW_A, **{S2: (0, 0, 0)})
    graced = _report(zeroed, S3, leave={S2: (True, False, 1)})
    why = main._ffa_report_contradiction(S3, _vec(zeroed), graced, True)
    assert why is not None and "did-not-play" in why


def test_the_signature_form_alone_is_not_a_disagreement_about_the_game():
    """Control: decision-from-one-reading (r5).

    The effective decision is recomputed here from the INCOMING report while
    the stored flag was decided from the first one, and _ffa_leave_decision's
    refutation guard is weaker for an unsigned (v1) report: kills prove
    presence only when signed, so the unsigned reading refutes fewer claims
    and marks a SUPERSET of seats unrated. Two members of one lobby can be on
    different mod versions wherever the lobby is not kills-capable, so the
    same claims arrive in both forms — and the round-4 comparison could reach
    two different verdicts on one game from signature form alone.

    Both readings are computed and a flag agreeing with EITHER is agreement.
    That can only turn a refusal into an echo, and an echo writes nothing."""
    # A seat claiming absent with zero rounds/points but NON-ZERO kills: the
    # signed reading refutes the claim (it played), the unsigned one cannot.
    kills_only = dict(ROW_A, **{S2: (0, 0, 7)})
    claim = {S2: (True, True, None)}
    signed = _report(kills_only, S3, leave=claim)
    assert main._ffa_leave_decision(signed, True)[0] == set()
    assert main._ffa_leave_decision(signed, False)[0] == {S2}
    # The row was written by a v2 report: absent = False, the refuted reading.
    recorded_signed = _vec(kills_only, leave={S2: (True, False)})
    # The SAME claims delivered as a v1 report are still the same game.
    assert main._ffa_report_contradiction(S3, recorded_signed, signed, False) is None
    # ...and a row written by a v1 report is agreed with by a v2 delivery.
    recorded_plain = _vec(kills_only, leave={S2: (True, True)})
    assert main._ffa_report_contradiction(S3, recorded_plain, signed, True) is None
    # The leniency is bounded: a decision NEITHER reading can reach is still a
    # contradiction.
    played = dict(ROW_A, **{S2: (4, 9, 7)})
    present = _report(played, S3)
    assert main._ffa_report_contradiction(
        S3, _vec(played, leave={S2: (False, True)}), present, True) is not None


def test_the_recorded_outcome_note_does_not_promise_a_missing_column_degrades():
    """Control: absent-columns-claimed-safe (r5).

    _ffa_recorded_game_outcome's docstring asserted that columns ABSENT (a
    database the migration has not reached) or NULL both mean "no skew
    recorded, the pre-327 behaviour and the right default". The NULL half is
    true. The absent half is not: SELECT of a column that does not exist
    raises UndefinedColumn and never yields NULL, and both callers swallow the
    exception — so the documented safe default is in fact "resolve nothing, on
    every report, for the whole window", with a log line that says catch-up
    next report about a next report that fails identically (#351/#277)."""
    doc = inspect.getdoc(main._ffa_recorded_game_outcome)
    assert "A NULL in either column" in doc
    assert "UndefinedColumn" in doc
    assert "is not that case" in doc.lower()
    # The claim that was false is gone in the form that made it false.
    assert "Columns absent" not in doc
    assert not re.search(r"absent .{0,40}mean[s]? .{0,20}no skew recorded", doc)


# ── the endpoint, AWAITED against a live PostgreSQL ───────────────────────
# What the binding sweep above proves statically, these prove by running: a
# report arrives, submit_ffa_match executes, and the body it answers with is
# read off the response object rather than off the function's source text.
#
# They take the ECHO path deliberately. It runs through the first third of the
# endpoint — the session check, the signature, the roster resolution, the
# lobby's FOR UPDATE, the progress derivation and the replay comparison — and
# answers from the four tables this file's schema already builds, without
# needing the settlement's glicko/bets/cards/achievements surfaces. That is
# the stretch where round 4's TypeError sat, and it is where the progress
# fields are decided.


class _NoHeaders:
    @staticmethod
    def get(_name, _default=None):
        return None


class _FakeRequest:
    """Only what _check_steam_session reads. The session check itself is
    replaced below: this file is about the report path, and an unarmed
    soft-fail would make the test depend on which auth env vars happen to be
    set on the machine running it (#438)."""
    headers = _NoHeaders()
    client = None
    url = "http://test/api/v1/ffa/matches"


def _endpoint_report(vec, winner, room, *, lobby=None, leave=None, reporter=None,
                     with_slots=False):
    """A real schemas.FfaMatchReport, which is what the endpoint is annotated
    with and what FastAPI would have validated.

    `with_slots` numbers the entries in the order _endpoint_fixture writes
    member_ids, which is what the endpoint's slot binding compares against. It
    is off by default because every report built before round 8 is answered by
    the room-keyed replay echo, which returns ABOVE that binding -- a report
    that has to travel past it needs the slots, and a report that does not must
    keep the shape its own test was written against."""
    leave = leave or {}
    return schemas.FfaMatchReport(
        lobby_id=str(lobby or LOBBY),
        photon_room_id=room,
        winner_steam_id=winner,
        reported_by_steam_id=reporter or winner,
        is_ranked=True,
        players=[schemas.FfaPlayerEntry(
            steam_id=s, rounds_won=r, points_total=p, kills=k,
            slot=(i if with_slots else 0),
            left_early=leave.get(s, PRESENT)[0],
            absent=leave.get(s, PRESENT)[1],
            game_points_at_leave=leave.get(s, PRESENT)[2])
            for i, (s, (r, p, k)) in enumerate(vec.items())])


async def _endpoint_fixture(games_played, recorded_number, recorded_room,
                            vec=None, awarded=(2, 1.5, 40, 7)):
    """A lobby, its three members and ONE recorded game, shaped so the echo
    path can answer. `awarded` is what the reporter's stored row holds, so the
    echo's own numbers can be told apart from defaults."""
    vec = vec or ROW_A
    engine = create_async_engine(require_pg())
    sm = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        for stmt in [s for s in SCHEMA.split(";") if s.strip()]:
            await conn.execute(text(stmt))
    pids = {}
    match_id = uuid.uuid4()
    async with sm() as db:
        for s in (S1, S2, S3):
            pids[s] = uuid.uuid4()
            await db.execute(text("INSERT INTO players (id, steam_id) VALUES (:i, :s)"),
                             {"i": pids[s], "s": s})
        await db.execute(text(
            "INSERT INTO ffa_lobbies (id, status, player_count, member_ids,"
            "                         games_played, created_at)"
            " VALUES (:i, 'active', 3, CAST(:m AS uuid[]), CAST(:g AS INTEGER),"
            "         CAST(:t AS TIMESTAMPTZ))"),
            {"i": LOBBY, "m": [str(pids[s]) for s in (S1, S2, S3)],
             "g": int(games_played), "t": T0})
        await db.execute(text(
            "INSERT INTO ffa_matches (id, lobby_id, photon_room_id, player_count,"
            "                         winner_id, ended_at, game_number)"
            " VALUES (:i, :l, :r, 3, :w, CAST(:t AS TIMESTAMPTZ),"
            "         CAST(:g AS SMALLINT))"),
            {"i": match_id, "l": LOBBY, "r": recorded_room, "w": pids[S3],
             "t": T0, "g": int(recorded_number)})
        place, delta, xp, gold = awarded
        for s, (r, p, k) in vec.items():
            await db.execute(text(
                "INSERT INTO ffa_match_players (match_id, player_id, rounds_won,"
                "        points_total, kills, placement, rating_change, xp_gained,"
                "        gold_gained)"
                " VALUES (:m, :p, :r, :pt, :k, :pl, :rc, :xp, :gd)"),
                {"m": match_id, "p": pids[s], "r": r, "pt": p, "k": k,
                 "pl": place if s == S3 else 3,
                 "rc": delta if s == S3 else -1.0,
                 "xp": xp if s == S3 else 0, "gd": gold if s == S3 else 0})
        await db.commit()
    return engine, sm, pids, match_id


async def _call_endpoint(sm, report):
    """Await the production endpoint with a real session, exactly as the route
    would. The signature check is neutralised by clearing MATCH_HMAC_SECRET,
    which is the module's own documented "no secret configured" path, and the
    session check is replaced: neither is what these tests are about, and both
    would otherwise make the result depend on this machine's env."""
    saved_secret = main.MATCH_HMAC_SECRET
    saved_session = main._check_steam_session

    async def _no_session_check(request, steam_id, db):
        return None

    main.MATCH_HMAC_SECRET = ""
    main._check_steam_session = _no_session_check
    try:
        async with sm() as db:
            return await main.submit_ffa_match(report, _FakeRequest(), db)
    finally:
        main.MATCH_HMAC_SECRET = saved_secret
        main._check_steam_session = saved_session


def test_pg_the_report_endpoint_runs_and_its_echo_carries_the_lobbys_progress():
    """Control: replay-echo-call-short (r5) — the RUNTIME half.

    This is the test round 4 did not have. It awaits submit_ffa_match itself,
    so a call inside it that cannot bind is a TypeError here and not a green
    suite over a dead endpoint. The answer's progress fields are read off the
    response object, which is the same place the client reads them."""
    require_pg()

    async def go():
        engine, sm, pids, match_id = await _endpoint_fixture(
            games_played=1, recorded_number=1, recorded_room="rm_211531_r1")
        try:
            return await _call_endpoint(sm, _endpoint_report(
                ROW_A, S3, "rm_211531_r1")), match_id
        finally:
            await engine.dispose()

    answer, match_id = run(go())
    assert isinstance(answer, schemas.FfaMatchResponse)
    assert answer.match_id == match_id
    assert answer.message == "Already recorded"
    # The stored figures, not defaults — so the echo really read the row.
    assert (answer.placement, answer.xp_gained, answer.gold_gained) == (2, 40, 7)
    # ...and the three fields the client resyncs from.
    assert answer.games_played == 1
    assert answer.expected_game == 2
    assert answer.settled_game == 1


def test_pg_an_answer_never_tells_a_client_to_name_a_number_it_just_settled():
    """Control: lobby-counter-not-caught-up (r5).

    `settled_game` and `expected_game` are two instructions, and round 4 could
    emit them EQUAL. A lobby holds a row at its own next slot whenever its
    counter is behind its rows — migration 327 numbers every historical row
    from its room tail and does not touch games_played, so a sitting whose
    game 1 was refused by an older api while its game 2 settled carries a row
    at 2 with games_played = 1. Every report naming 2 was then answered "2 is
    settled" and "name 2 next", the client adopted 2, played on, named 2
    again, and the sitting settled nothing more for as long as the seats kept
    playing. _ffa_lock_lobby_slot brings the counter up to the rows under the
    same FOR UPDATE, so the pair is consistent and the sitting resumes."""
    require_pg()

    async def go():
        engine, sm, _pids, _mid = await _endpoint_fixture(
            games_played=1, recorded_number=2, recorded_room="rm_211531_r2")
        try:
            answer = await _call_endpoint(sm, _endpoint_report(
                ROW_A, S3, "rm_211531_r2"))
            async with sm() as db:
                gp = (await db.execute(text(
                    "SELECT games_played FROM ffa_lobbies WHERE id = :l"),
                    {"l": LOBBY})).scalar()
            return answer, int(gp)
        finally:
            await engine.dispose()

    answer, gp = run(go())
    assert answer.settled_game == 2
    # The number the client is told to name next is one it can actually settle.
    assert answer.expected_game == 3
    assert answer.settled_game < answer.expected_game
    assert answer.games_played == 2
    # The catch-up is a DERIVATION, not a repair job: it is recomputed from the
    # rows under the lock on every report, and it becomes durable only in a
    # transaction that commits. An echo commits nothing, so the stored counter
    # is still 1 here — and that costs nothing, because the next report
    # recomputes the same 2 before settling 3 on top of it. What must not
    # depend on the write is the ANSWER, and it does not.
    assert gp == 1


def test_pg_the_catch_up_only_ever_moves_the_counter_forward():
    """The negative half (#391): a lobby whose counter is AHEAD of its rows —
    which is every ordinary lobby, since a settlement increments the counter
    and the row it wrote carries the number it just consumed — is not rewound,
    and nothing is written to it at all."""
    require_pg()

    async def go():
        engine, sm, _pids, _mid = await _endpoint_fixture(
            games_played=4, recorded_number=1, recorded_room="rm_211531_r1")
        try:
            async with sm() as db:
                _row, expected = await main._ffa_lock_lobby_slot(db, LOBBY)
                await db.commit()
            async with sm() as db:
                gp = (await db.execute(text(
                    "SELECT games_played FROM ffa_lobbies WHERE id = :l"),
                    {"l": LOBBY})).scalar()
            return expected, int(gp)
        finally:
            await engine.dispose()

    expected, gp = run(go())
    assert (expected, gp) == (5, 4)


def test_pg_a_settlement_commits_the_catch_up_and_lands_on_the_free_number():
    """The half the echo path cannot show: in a transaction that COMMITS, the
    catch-up persists and the increment beside it lands the sitting on the
    number after the one just settled. Without the catch-up the settlement
    would store 3 (the caught-up slot) while the counter went 1 -> 2, so the
    gap would reopen at the same width on every game, for ever."""
    require_pg()

    async def go():
        engine, sm, _pids, _mid = await _endpoint_fixture(
            games_played=1, recorded_number=2, recorded_room="rm_211531_r2")
        try:
            async with sm() as db:
                _row, expected = await main._ffa_lock_lobby_slot(db, LOBBY)
                # What the settlement does with the slot it took.
                await main._ffa_advance_lobby_slot(db, LOBBY)
                await db.commit()
            async with sm() as db:
                gp = (await db.execute(text(
                    "SELECT games_played FROM ffa_lobbies WHERE id = :l"),
                    {"l": LOBBY})).scalar()
                _row2, next_expected = await main._ffa_lock_lobby_slot(db, LOBBY)
            return expected, int(gp), next_expected
        finally:
            await engine.dispose()

    expected, gp, next_expected = run(go())
    assert expected == 3          # the free number, not the held 2
    assert gp == 3                # 2 (caught up) + 1 (consumed)
    assert next_expected == 4     # and the gap does not reopen


def test_pg_a_recorded_outcome_without_the_columns_raises_rather_than_defaulting():
    """Control: absent-columns-claimed-safe (r5) — the RUNTIME half.

    The docstring used to promise that a database without score_target_frozen
    / score_target_played degrades to the pre-327 "no skew recorded" answer.
    It does not: the SELECT raises. Asserted against a real table with the
    columns dropped, so the claim cannot come back as prose."""
    require_pg()

    async def go():
        engine, sm, _pids, _mid = await _endpoint_fixture(
            games_played=1, recorded_number=1, recorded_room="rm_211531_r1")
        try:
            async with sm() as db:
                with_columns = await main._ffa_recorded_game_outcome(db, LOBBY, 1)
            async with engine.begin() as conn:
                await conn.execute(text(
                    "ALTER TABLE ffa_matches DROP COLUMN score_target_frozen"))
                await conn.execute(text(
                    "ALTER TABLE ffa_matches DROP COLUMN score_target_played"))
            raised = None
            try:
                async with sm() as db:
                    await main._ffa_recorded_game_outcome(db, LOBBY, 1)
            except Exception as ex:          # noqa: BLE001 - the point is the class
                raised = ex
            return with_columns, raised
        finally:
            await engine.dispose()

    with_columns, raised = run(go())
    # Both columns NULL is the genuine pre-327 row, and it DOES mean "settle".
    assert with_columns[0] == "settle" and with_columns[1] is not None
    # A table without them is a different fact, and it is not silent.
    assert raised is not None
    assert "score_target_frozen" in str(raised) or "UndefinedColumn" in type(raised).__name__


def test_every_progress_the_endpoint_builds_comes_from_a_locked_slot():
    """Control: race-progress-from-a-bare-read (r5).

    The invariant `settled_game < expected_game` is a property of the PAIR, so
    it holds only where both numbers come from the same derivation. The
    unique-violation fallback answers with `settled_game` taken from the row
    the insert collided with, and round 4 paired it with a bare
    `SELECT games_played FROM ffa_lobbies` — which is the counter before any
    catch-up, i.e. exactly the state that produces an expected_game the client
    cannot settle. It re-reads through _ffa_lock_lobby_slot instead.

    Found by re-reading the comment this round's own fix had just written
    ("every answer that carries both"), which is where the next false claim
    usually is."""
    src = _endpoint_src()
    # No bare read of the counter anywhere in the endpoint: the one derivation
    # is the locked helper's.
    assert "SELECT games_played FROM ffa_lobbies" not in src
    # Round 6 moved the post-rollback re-read into _ffa_progress_relocked, so
    # the endpoint takes the lock once and every answer given after a rollback
    # goes through the helper — which is itself the locked derivation, not a
    # second one.
    assert src.count("_ffa_lock_lobby_slot(") == 1
    assert src.count("_ffa_progress_relocked(") == 2
    relock = inspect.getsource(main._ffa_progress_relocked)
    assert "_ffa_lock_lobby_slot(db, lobby_uuid)" in relock
    assert "SELECT games_played" not in relock
    # The integrity handler takes it ONCE, above its own branch, so the arm
    # that is not the replay cannot be the one that skips it.
    race = src[src.index("except IntegrityError as ie:"):]
    race = race[:race.index("_ffa_replay_echo(")]
    assert "_race_progress = await _ffa_progress_relocked(" in race
    assert (race.index("_race_progress = await _ffa_progress_relocked(")
            < race.index('"uq_ffa_match_room" not in str('))

    # ...and the exits below a CAPTURE, which round 7 left out. A capture is
    # not a passive write: _quarantine_report rolls this request's transaction
    # back and commits its own row, so the lobby lock is released inside it and
    # every number the caller still holds is a snapshot of a sitting that may
    # have moved. Both of _ffa_record_and_refuse's raises must answer from a
    # re-derivation taken AFTER the capture.
    refuse = _code_lines(inspect.getsource(main._ffa_record_and_refuse))
    capture = refuse.index("_quarantine_report(")
    rederive = refuse.index("progress = await _ffa_progress_after_capture(")
    assert capture < rederive, (
        "the re-read runs before the capture, so it re-reads a lobby whose "
        "lock this request is still holding")
    # ...which is true of the TERMINAL arm. ROUND 12 splits the other one off:
    # a capture that did not record answers about the DELIVERY, so it carries
    # no progress at all and is raised ABOVE the re-derivation -- not below it
    # with the fields stripped afterwards. That ordering is what makes the two
    # dispositions disjoint by construction rather than by a later edit
    # remembering to keep them apart.
    assert "raise FfaReportRefusal(status, detail, progress)" in refuse
    assert refuse.index("raise FfaReportRefusal(status, detail, progress)") > rederive, (
        "the terminal refusal answers from the copy read before the capture")
    assert refuse.count("raise FfaReportRefusal(503,") == 1, refuse
    capture_arm = refuse.index("raise FfaReportRefusal(503,")
    assert capture < capture_arm < rederive, (
        "the capture-failure 503 is not between the capture and the "
        "re-derivation, so the caller's settled_game is reachable from it")
    # The re-derivation is the LOCKED one, not a second bare read of the
    # counter, and settled_game is carried only while the pair's own
    # inequality still holds.
    after = _code_lines(inspect.getsource(main._ffa_progress_after_capture))
    assert "_ffa_progress_relocked(db, lobby_uuid)" in after
    assert "SELECT games_played" not in after
    assert '< int(fresh.get("expected_game", 0))' in after

    # ── ROUND 10. A FAILED FRESH READ FAILS CLOSED, and the caller's copy is
    # not reachable from the helper at all.
    #
    # Rounds 5 to 9 answered the two exhausted cases -- both relocks failed,
    # or the lobby row is gone -- from the caller's pre-rollback copy, on the
    # reading that it could only be stale-LOW and was therefore safe. What
    # that answer COSTS is a number the server may no longer accept, handed to
    # the one seat that is trying to resynchronise, which earns it another
    # terminal refusal and spends one more game of the sitting (#430). So the
    # helper now answers 503 with NO progress fields, and the identifier that
    # made a stale answer reachable is GONE from its span rather than merely
    # unused -- while it was in scope, every exit added there had a stale
    # answer within one line of it.
    assert "fallback" not in relock, (
        "the caller's copy is reachable from _ffa_progress_relocked again")
    assert "return dict(" not in relock, (
        "_ffa_progress_relocked returns a dict it did not read under the lock")
    # Both exhausted arms raise, and both raise the SAME shape: a 503 whose
    # progress is the EMPTY dict, so the handler's `**exc.progress` adds no
    # key at all. Derived from the parsed function rather than counted by
    # hand: a third arm added later has to satisfy this too (#432).
    relock_tree = ast.parse(inspect.getsource(main._ffa_progress_relocked))
    raises = [n for n in ast.walk(relock_tree) if isinstance(n, ast.Raise)]
    assert len(raises) == 2, [ast.unparse(r) for r in raises]
    for node in raises:
        call = node.exc
        assert isinstance(call, ast.Call) and getattr(call.func, "id", None) \
            == "FfaReportRefusal", ast.unparse(node)
        assert isinstance(call.args[0], ast.Constant) and call.args[0].value == 503
        assert isinstance(call.args[2], ast.Dict) and not call.args[2].keys, (
            "an exhausted re-read still answers with progress fields: "
            + ast.unparse(node))
    # ── ROUND 12 (the r7 LOW on B1). The zero-occurrence claim is made on the
    # SPAN THAT WAS PARSED, not only on its text. The text check above reds on
    # the word wherever it appears, including in a sentence about it; this one
    # reds on the NAME being reachable as an identifier -- a parameter, a load,
    # an attribute or a keyword argument -- which is the fact the helper's own
    # docstring claims about itself. Both are kept: a claim of absence that has
    # only one form of the question behind it is half a claim.
    relock_fn = relock_tree.body[0]
    assert isinstance(relock_fn, (ast.AsyncFunctionDef, ast.FunctionDef))
    # THE CLASS, not the one name (#432): the defect is a caller's copy
    # reachable inside this span, whatever it is called. The span takes the
    # session and the lobby and NOTHING ELSE, so there is no third parameter
    # for a substitute reading to arrive in.
    assert [a.arg for a in relock_fn.args.args] == ["db", "lobby_uuid"],         [a.arg for a in relock_fn.args.args]
    assert not relock_fn.args.kwonlyargs and relock_fn.args.vararg is None         and relock_fn.args.kwarg is None
    assert "fallback" not in inspect.signature(
        main._ffa_progress_relocked).parameters, (
        "the fallback is a parameter of _ffa_progress_relocked again")
    fallback_nodes = []
    for node in ast.walk(relock_tree):
        if isinstance(node, ast.arg) and node.arg == "fallback":
            fallback_nodes.append("arg " + node.arg)
        elif isinstance(node, ast.Name) and node.id == "fallback":
            fallback_nodes.append("name " + node.id)
        elif isinstance(node, ast.Attribute) and node.attr == "fallback":
            fallback_nodes.append("attribute ." + node.attr)
        elif isinstance(node, ast.keyword) and node.arg == "fallback":
            fallback_nodes.append("keyword " + node.arg)
    assert fallback_nodes == [], (
        "the fallback name occurs in the parsed relock span: "
        + ", ".join(fallback_nodes))
    # A zero-count assertion passes on an empty parse, so the walk has to have
    # seen the span it is making the claim about (#342).
    named = {n.arg for n in ast.walk(relock_tree) if isinstance(n, ast.arg)}
    assert {"db", "lobby_uuid"} <= named, sorted(named)
    # The ONE return is the locked reading.
    returns = [n for n in ast.walk(relock_tree) if isinstance(n, ast.Return)]
    assert len(returns) == 1, [ast.unparse(r) for r in returns]
    assert ast.unparse(returns[0].value) == \
        "_ffa_progress(max(0, int(_expected) - 1))", ast.unparse(returns[0])

    # ── ...and EVERY progress the endpoint emits is one of those readings.
    #
    # Derived from the endpoint's own syntax tree, not from a list: every name
    # that holds a progress dict is assigned from `_ffa_progress` over the slot
    # read under the lobby lock, or from the relocked helper; and every answer
    # that carries progress carries one of those names, or a `_ffa_with_settled`
    # of one. A refusal built from anything else -- a literal, a bare column
    # read, a copy taken before a rollback -- reds here.
    tree = ast.parse(_endpoint_src())
    holders = {"_progress", "_race_progress", "_fail_progress"}
    seen = {}
    for node in ast.walk(tree):
        if (isinstance(node, ast.Assign) and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
                and node.targets[0].id in holders):
            value = node.value
            value = value.value if isinstance(value, ast.Await) else value
            seen.setdefault(node.targets[0].id, []).append(ast.unparse(value))
    assert set(seen) == holders, sorted(seen)
    for name, sources in seen.items():
        for expr in sources:
            assert expr in ("_ffa_progress(_expected_game - 1)",
                            "_ffa_progress_relocked(db, lobby_uuid)"), (name, expr)
    carried = 0
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fname = getattr(node.func, "id", None)
        if fname == "FfaReportRefusal":
            assert len(node.args) == 3, ast.unparse(node)
            assert getattr(node.args[2], "id", None) in holders, ast.unparse(node)
            carried += 1
        elif fname == "_ffa_record_and_refuse":
            kw = {k.arg: k.value for k in node.keywords}
            assert "progress" in kw, ast.unparse(node)
            got = ast.unparse(kw["progress"])
            assert (got in holders
                    or got.startswith("_ffa_with_settled(_progress,")), got
            carried += 1
    # A sweep that found nothing is not a sweep that found nothing wrong
    # (#342): the endpoint really does carry a double-figure number of these.
    assert carried >= 12, carried


# ── round 6: the exact stake, the bounded scan, the weaker lock ───────────

def test_a_refund_moves_the_exact_stake_and_never_a_clamped_one():
    """Control: refund-clamps-the-delta (r6).

    Round 5 wrote `gold_spent = GREATEST(0, COALESCE(gold_spent,0) - :amt)`
    beside a `GoldTransaction` for the WHOLE stake. With gold_spent = 5 and a
    10-gold wager the ledger records 10 returned and the balance moves 5, so
    the ledger's sum and `gold_earned - gold_spent` stop agreeing and the
    player is short with nothing in the record saying so (#326: a money
    mutation is a DB delta, and a delta is the amount or it is wrong).

    Executed in BOTH directions against the loop that uses it, because a
    refusal that never fires and a clamp that never refuses look identical
    from outside (#391)."""
    ref = inspect.getsource(main._return_stake_exactly)
    # The predicate is IN the statement - a read-then-write pair would let a
    # concurrent debit land between them.
    assert "COALESCE(gold_spent, 0) >= CAST(:amt AS integer)" in ref
    assert "RETURNING gold_spent" in ref
    # The clamp survives in the PROSE, which is where it belongs: the
    # docstring has to be able to name the form it replaced. Measured on
    # the statements, never on the file's text (#441).
    assert "GREATEST" not in "".join(_non_docstring_strings(ref))
    # ...and the ledger row is written by the same helper, so no caller can
    # keep one half of the record.
    assert "GoldTransaction(" in ref

    # Covered: the stake goes back, the ledger row is added, nothing raises.
    db = _RefundDb([_bet_batch(3), []], covers=True)
    moved = run(main._refund_ffa_game_bets_strict(db, uuid.uuid4(), 3, "t"))
    assert moved == 3
    assert db.gold_moves == 3 and len(db.added) == 3

    # NOT covered: nothing is added, and the refusal propagates to the caller
    # rather than being rounded down into a partial payment.
    db = _RefundDb([_bet_batch(3), []], covers=False)
    with pytest.raises(RuntimeError) as ex:
        run(main._refund_ffa_game_bets_strict(db, uuid.uuid4(), 3, "t"))
    assert "does not cover the stake" in str(ex.value)
    assert db.added == [], "a ledger row was written for gold that never moved"


def test_no_refund_in_the_file_still_clamps_its_delta():
    """The defect is a CLASS, not the line the report named (#432/#330).

    Five sites wrote the same clamped subtraction beside a full-stake ledger
    row - the series refund, the team-bet reconcile, both FFA bet refunds and
    the lobby-bet refund. Grepping the OPERATION is what found the other four,
    and asserting on the operation is what keeps a sixth from being added."""
    src = pathlib.Path(main.__file__).read_text(encoding="utf-8")
    # On the STATEMENTS, not the text: the one surviving mention is the
    # helper docstring naming the form it replaced, and a check that a
    # comment can redden is a check a comment can also keep green (#441).
    statements = "\n".join(_non_docstring_strings(src))
    assert "GREATEST(0, COALESCE(gold_spent" not in statements
    assert "GREATEST(0, COALESCE(gold_spent, 0)" not in statements
    # ...and the negative control for that reading: the clamp IS still in
    # the file, so the assertion above is not passing on an empty view.
    assert "GREATEST(0, COALESCE(gold_spent,0) - :amt)" in src
    # ...and every refund path reaches the one helper.
    for fn in (main._refund_series_bets, main._refund_ffa_game_bets_strict,
               main._refund_ffa_lobby_bets, main._lobby_bet_pay_refund):
        assert "_return_stake_exactly(" in inspect.getsource(fn), fn.__name__
    # The claw-back sites (gold_earned coming back down on an admin reversal)
    # are a DIFFERENT question and are deliberately untouched here: refusing a
    # reversal leaves a paid award standing, which is the opposite polarity
    # (#412). Named so the next round knows they were seen, not missed.
    assert "GREATEST(0, COALESCE(gold_earned,0) - :amt)" in src


def test_the_variant_scan_is_bounded_by_the_quota_it_claims():
    """Control: variant-scan-unbounded (r6).

    The note said "the scan is bounded by the same quota it protects" and the
    statement had neither a status filter nor a LIMIT: it read every NULL-room
    row the group had ever produced, reviewed and discarded history included,
    under the advisory lock the caller holds. A comment asserting a bound the
    SQL does not have is the highest-risk kind (#351)."""
    src = inspect.getsource(main._quarantine_on_file)
    scan = src[src.index("photon_room_id IS NULL"):]
    assert "status = 'pending'" in scan
    assert "LIMIT 50" in scan
    # The LIMIT and the quota are the SAME number. Both are literals in their
    # own statements (the janitor's boot self-test refuses SQL assembled at
    # runtime), so nothing but this assertion stops them drifting apart.
    quota = re.search(r"int\(_pending\) >= (\d+)",
                      inspect.getsource(main._quarantine_report))
    assert quota, "the pending quota is no longer a readable literal"
    limit = re.search(r"LIMIT (\d+)", scan)
    assert limit and limit.group(1) == quota.group(1), (
        "the variant scan and the quota name different numbers")
    # ...and the note now says what the bound COSTS rather than claiming it
    # free: a reviewed variant is no longer recognised.
    doc = main._quarantine_on_file.__doc__
    assert "THE VARIANT SCAN READS THE SAME SET THE QUOTA COUNTS" in doc
    assert "already REVIEWED is not recognised any more" in doc


def test_the_lobby_lock_is_the_weakest_mode_that_still_conflicts_with_itself():
    """Control: settlement-takes-for-update (r6).

    Take the WEAKEST mode that still conflicts with everything this
    transaction has to exclude (#202/#203/#207). Nothing in the settlement
    changes a KEY column of ffa_lobbies, so FOR UPDATE was strictly more than
    it needed; what FOR NO KEY UPDATE still conflicts with - another of
    itself, the games_played UPDATE, every FOR UPDATE taker - is what the
    exclusion is actually made of, and
    `test_pg_two_reports_for_one_lobby_cannot_settle_the_same_number` is the
    executed half: RED when the lock is removed, GREEN under the weaker mode.

    The BENEFIT half of round 6's justification - that the stronger mode had
    made concurrent wagers wait for nothing - was false and is gone. It is
    `test_a_wager_cannot_be_inserted_while_its_game_settles` (r7) that pins
    the corrected reading and the explicit lock the false claim would have
    licensed removing. This test keeps the mode; that one keeps the reason."""
    assert "FOR NO KEY UPDATE" in main._FFA_LOBBY_LOCK_SQL
    assert "FOR UPDATE" not in main._FFA_LOBBY_LOCK_SQL.replace(
        "FOR NO KEY UPDATE", "")
    # B13: placement and the delete path keep the mode they already had, so
    # this round weakened one lock and strengthened none.
    src = pathlib.Path(main.__file__).read_text(encoding="utf-8")
    place = src[src.index('@app.post("/api/v1/ffa/bets"'):]
    place = place[:place.index("@app.", 10)]
    assert "FROM ffa_lobbies WHERE id = :lid FOR NO KEY UPDATE" in place
    assert src.count(
        "SELECT 1 FROM ffa_lobbies WHERE id = :lid FOR NO KEY UPDATE") == 1
    # ...and the prose that named the old mode was corrected with it: a
    # comment naming a mechanism the change removed is where the next false
    # claim lives (#432/#459).
    lock_note = src[src.index("# FOR NO KEY UPDATE, not FOR UPDATE (#202/#203/#207)"):
                    src.index("_FFA_LOBBY_LOCK_SQL =")]
    assert "never changes a KEY column" in lock_note
    endpoint = _endpoint_src()
    assert "under the FOR UPDATE" not in endpoint
    assert "under the lobby lock" in endpoint


def test_an_answer_names_a_settled_game_only_when_the_report_named_it():
    """Control: settled-game-without-a-named-number (r6).

    `settled_game` means "the number THIS report named is already settled",
    and a consumer drops the outbox entry as terminal on it. Round 5 took the
    number off the recorded row without asking what the report named, so the
    room-keyed replay of a report whose room id has no usable `_rN` tail -
    reachable in the migration window, where 327 numbers a tail-less
    historical row from the lobby's own sequence - was answered "game N is
    settled" about a number it had never mentioned."""
    progress = main._ffa_progress(4)
    prior = {"game_number": 3}
    # Named, and the same number: the field is there.
    assert main._ffa_with_settled(progress, prior, 3)["settled_game"] == 3
    # Named nothing: no claim about any number.
    assert "settled_game" not in main._ffa_with_settled(progress, prior, None)
    # Named a DIFFERENT number from the row's: still no claim, because the
    # answer would be about a game the report did not send.
    assert "settled_game" not in main._ffa_with_settled(progress, prior, 2)
    # The progress itself survives every one of those.
    for named in (3, None, 2):
        out = main._ffa_with_settled(progress, prior, named)
        assert out["games_played"] == 4 and out["expected_game"] == 5
    # The number a report names has ONE derivation, used by both the replay
    # path and the endpoint - a second reading is how the two disagreed.
    assert main._ffa_named_game_number("rm_211531_r7") == 7
    assert main._ffa_named_game_number("rm_no_tail") is None
    assert main._ffa_named_game_number("rm_r0") is None
    assert main._ffa_named_game_number("rm_r1000") is None
    assert "_ffa_named_game_number(" in inspect.getsource(main._ffa_replay_echo)
    assert _endpoint_src().count("_ffa_named_game_number(") == 1


def test_every_reachable_insert_failure_answers_with_the_lobbys_progress():
    """Control: insert-failure-answers-bare (r6).

    Two answers below the lobby lock used to carry nothing. A non-duplicate
    integrity error raised `HTTPException(500, ...)`, and a DBAPI-level
    failure of the INSERT - migration 327's trigger refusing a lobby holding
    every number in 1..999 - was not caught at all. Both roll the settlement
    back, so neither can move a result; both left the reporter without the
    number to resume from, which is the whole of B3."""
    src = _endpoint_src()
    # Whitespace-normalised, because a CALL is what this is about and a call
    # wrapped across two lines is the same call. The first draft matched the
    # raw text and its own negative control reddened it: an inert reflow of
    # the very line under test turned the check red, which means it was
    # measuring a line shape and not the answer (#391 — the negative control
    # earning its place, and #441).
    flat = " ".join(src.split())
    assert 'raise HTTPException(500, "FFA match insert failed")' not in flat
    assert 'FfaReportRefusal(500, "FFA match insert failed", _race_progress)' in flat
    # The DBAPI arm exists, is AFTER the integrity arm (IntegrityError is a
    # subclass of DBAPIError, so the narrower clause has to come first or it
    # is dead), and answers a retryable status carrying the progress.
    assert "except DBAPIError as _insert_ex:" in src
    assert (src.index("except IntegrityError as ie:")
            < src.index("except DBAPIError as _insert_ex:"))
    dbapi = " ".join(src[src.index("except DBAPIError as _insert_ex:"):].split())
    assert "_ffa_progress_relocked(" in dbapi
    assert 'FfaReportRefusal(503, "Could not record this game - retry"' in dbapi
    # The service-account guard moved BELOW the progress, so its 403 is no
    # longer the one post-lock answer outside the rule.
    lock = src.index("_progress = _ffa_progress(_expected_game - 1)")
    # The roster guard higher up the endpoint is a different call; this is
    # the LOBBY-MEMBER one, and it has to sit after the progress exists.
    member_guard = src.index("_assert_no_service_subject(\n", lock)
    assert member_guard > lock
    guard = src[lock:member_guard + 900]
    assert "FfaReportRefusal(_svc.status_code, str(_svc.detail), _progress)" in guard


def test_pg_an_exhausted_number_space_reaches_the_arm_that_answers_it():
    """The reachability half of the test above (#286/#405: prove the path is
    entered before trusting the logic).

    The handler is worth nothing unless a plpgsql RAISE from the migration's
    trigger really reaches SQLAlchemy as DBAPIError and NOT as IntegrityError:
    the narrower clause runs first, and a refusal landing there would be
    answered 500 "FFA match insert failed" instead of the retryable refusal
    that names the lobby's progress. Executed against the real trigger."""
    from sqlalchemy.exc import DBAPIError, IntegrityError
    require_pg()
    sql = MIGRATION.read_text(encoding="utf-8")
    FULL = "00000000-0000-0000-0000-0000000000f9"

    async def go():
        conn = await _raw_pg()
        try:
            await conn.execute(MIGRATION_FIXTURE)
            await conn.execute(sql)
            await conn.execute(
                "INSERT INTO ffa_matches (id, lobby_id, photon_room_id,"
                " ended_at, game_number)"
                " SELECT gen_random_uuid(), $1, 'f9_r' || n, NOW(),"
                "        n::SMALLINT FROM generate_series(1, 999) AS n", FULL)
        finally:
            await conn.close()
        engine = create_async_engine(require_pg())
        sm = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with sm() as db:
                try:
                    await db.execute(text(
                        "INSERT INTO ffa_matches (id, lobby_id, photon_room_id,"
                        " ended_at) VALUES (gen_random_uuid(),"
                        " CAST(:l AS uuid), 'f9_no_tail', NOW())"), {"l": FULL})
                    return ("accepted",), ""
                except Exception as ex:
                    await db.rollback()
                    return type(ex).__mro__, str(ex)
        finally:
            await engine.dispose()

    mro, why = run(go())
    assert mro != ("accepted",), "the exhausted lobby accepted an unnumbered insert"
    assert DBAPIError in mro, mro
    # ...and NOT the narrower class, which the handler above answers 500.
    assert IntegrityError not in mro, mro
    assert "holds every number in 1..999" in why, why


def test_every_round_six_control_names_a_test_that_exists():
    """The same pairing for round 6. Every control in the inventory marked
    (r6) names one of these, and a rename that left the log pointing at
    nothing reddens here."""
    mod = sys.modules[__name__]
    for name in ("test_a_refund_moves_the_exact_stake_and_never_a_clamped_one",
                 "test_no_refund_in_the_file_still_clamps_its_delta",
                 "test_the_variant_scan_is_bounded_by_the_quota_it_claims",
                 "test_the_lobby_lock_is_the_weakest_mode_that_still_conflicts_with_itself",
                 "test_pg_two_reports_for_one_lobby_cannot_settle_the_same_number",
                 "test_an_answer_names_a_settled_game_only_when_the_report_named_it",
                 "test_every_reachable_insert_failure_answers_with_the_lobbys_progress",
                 "test_pg_an_exhausted_number_space_reaches_the_arm_that_answers_it",
                 "test_the_binding_sweep_can_actually_fail",
                 "test_every_call_in_main_binds_to_the_function_it_names",
                 "test_this_file_actually_executes_the_report_endpoint",
                 "test_the_capture_note_no_longer_calls_every_conflict_a_retry",
                 "test_the_migration_header_says_the_tail_has_to_agree"):
        assert callable(getattr(mod, name, None)), name


# ── round 7: what a refusal costs, executed rather than asserted ───────────

# The money tables, declared as their own migrations declare them. Separate
# from SCHEMA above because these tests are about gold and wagers rather than
# about game numbers, and a test table that quietly widened a column would be
# exercising a different write than production runs (the SCHEMA header's rule,
# applied to a second set of tables).
#
# `players.gold_spent` is INTEGER NOT NULL DEFAULT 0 (020_economy.sql).
# `gold_transactions.id` is BIGSERIAL because the ORM model declares
# BigInteger autoincrement and SQLAlchemy asks for the generated value back.
# `lobby_bets.id` is UUID (207_lobby_bets.sql), which is what the flush's
# skip-list binds as `uuid[]`.
MONEY_SCHEMA = """
DROP TABLE IF EXISTS gold_transactions;
DROP TABLE IF EXISTS lobby_bets;
DROP TABLE IF EXISTS bets;
DROP TABLE IF EXISTS tournament_matches;
DROP TABLE IF EXISTS matches;
DROP TABLE IF EXISTS ranked_series;
DROP TABLE IF EXISTS players CASCADE;

CREATE TABLE players (
    id UUID PRIMARY KEY,
    steam_id TEXT NOT NULL UNIQUE,
    gold_earned INTEGER NOT NULL DEFAULT 0,
    gold_spent INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE gold_transactions (
    id BIGSERIAL PRIMARY KEY,
    player_id UUID NOT NULL REFERENCES players(id) ON DELETE CASCADE,
    amount INTEGER NOT NULL,
    reason VARCHAR(64) NOT NULL,
    reference_id TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE lobby_bets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    mode VARCHAR(8) NOT NULL,
    lobby_id UUID NOT NULL,
    player_id UUID NOT NULL REFERENCES players(id) ON DELETE CASCADE,
    amount INTEGER NOT NULL,
    status VARCHAR(16) NOT NULL DEFAULT 'open',
    resolve_reason VARCHAR(48),
    bound_bet_id UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resolved_at TIMESTAMPTZ
);
CREATE TABLE ranked_series (
    id UUID PRIMARY KEY,
    player1_id UUID REFERENCES players(id),
    player2_id UUID REFERENCES players(id),
    status VARCHAR(16) NOT NULL DEFAULT 'active',
    is_tournament BOOLEAN NOT NULL DEFAULT FALSE,
    p1_series_wins SMALLINT NOT NULL DEFAULT 0,
    p2_series_wins SMALLINT NOT NULL DEFAULT 0,
    invalidated_at TIMESTAMPTZ,
    invalidation_reason VARCHAR(64),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE matches (
    id UUID PRIMARY KEY,
    series_id UUID REFERENCES ranked_series(id),
    ended_at TIMESTAMPTZ
);
CREATE TABLE bets (
    id BIGSERIAL PRIMARY KEY,
    series_id UUID REFERENCES ranked_series(id),
    player_id UUID NOT NULL REFERENCES players(id),
    amount INTEGER NOT NULL,
    payout INTEGER,
    settlement_kind VARCHAR(16),
    settled_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE tournament_matches (
    id BIGSERIAL PRIMARY KEY,
    series_id UUID REFERENCES ranked_series(id),
    status VARCHAR(20) NOT NULL DEFAULT 'pending'
);
"""


async def _money_setup(players):
    """A scratch money schema plus `players`, each with the gold_spent it is
    given. Returns (engine, sessionmaker, {steam_id: uuid})."""
    engine = create_async_engine(require_pg())
    sm = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        for stmt in [s for s in MONEY_SCHEMA.split(";") if s.strip()]:
            await conn.execute(text(stmt))
    pids = {}
    async with sm() as db:
        for steam, spent in players.items():
            pids[steam] = uuid.uuid4()
            await db.execute(text(
                "INSERT INTO players (id, steam_id, gold_spent)"
                " VALUES (:i, :s, CAST(:g AS integer))"),
                {"i": pids[steam], "s": steam, "g": int(spent)})
        await db.commit()
    return engine, sm, pids


async def _gold(sm, pid):
    """(gold_spent, [ledger amounts]) for one player, read back committed."""
    async with sm() as db:
        spent = (await db.execute(text(
            "SELECT gold_spent FROM players WHERE id = :i"), {"i": pid})).scalar()
        ledger = (await db.execute(text(
            "SELECT amount FROM gold_transactions WHERE player_id = :i"
            " ORDER BY id"), {"i": pid})).scalars().all()
    return spent, list(ledger)


def test_pg_the_exact_refund_statement_runs_against_a_real_server():
    """Control: refund-statement-never-executed (r7).

    Round 6 closed the clamped-delta finding and pinned it with a source
    substring plus a mock whose answer was a CONSTRUCTOR FLAG: `_RefundDb`
    returns a row or None according to `covers=`, so the predicate
    `COALESCE(gold_spent, 0) >= CAST(:amt AS integer)` and the
    RETURNING-row-versus-None reading were never run by a database at all.
    The recorded RED for that control came from the substring assertion, which
    fires before the behavioural half is reached - so the statement could have
    been wrong in either direction and the suite stayed green (#313/#340/#465:
    not reviewed until it has RUN).

    This runs it. Four questions, all about the statement rather than about
    the loop that calls it:

      1. a covered refund moves the balance by EXACTLY the stake and writes
         exactly one ledger row for the same number;
      2. a refund that takes the balance to exactly 0 SUCCEEDS - `0` is a real
         balance and a falsy one, and reading the returned VALUE rather than
         its presence is the bug this shape exists to make impossible;
      3. an uncovered refund raises and writes NOTHING - no partial move, no
         ledger row;
      4. `:pid` takes both shapes its callers arrive with, a `uuid.UUID` off
         an ORM row and a `str` off a mappings row, which is the claim the
         docstring makes about why that one bind is deliberately untyped."""
    require_pg()

    async def go():
        engine, sm, pids = await _money_setup({S1: 25, S2: 10, S3: 4})
        try:
            out = {}
            # 1: exact move, exact ledger row. player_id as a UUID object.
            async with sm() as db:
                await main._return_stake_exactly(db, pids[S1], 10,
                                                 reason="ffa_bet_refund",
                                                 reference_id="ref-1")
                await db.commit()
            out["exact"] = await _gold(sm, pids[S1])

            # 2: down to exactly 0, and player_id as a STRING this time.
            async with sm() as db:
                await main._return_stake_exactly(db, str(pids[S2]), 10,
                                                 reason="ffa_bet_refund",
                                                 reference_id="ref-2")
                await db.commit()
            out["to_zero"] = await _gold(sm, pids[S2])

            # 3: the balance does not cover the stake the wager records.
            async with sm() as db:
                try:
                    await main._return_stake_exactly(db, pids[S3], 10,
                                                     reason="ffa_bet_refund",
                                                     reference_id="ref-3")
                    out["refused"] = None
                except main.StakeRefundRefused as ex:
                    out["refused"] = str(ex)
                await db.rollback()
            out["short"] = await _gold(sm, pids[S3])
            return out
        finally:
            await engine.dispose()

    got = run(go())
    assert got["exact"] == (15, [10]), got["exact"]
    assert got["to_zero"] == (0, [10]), got["to_zero"]
    assert got["refused"] is not None, (
        "a 10-gold refund against a 4-gold balance was not refused")
    assert "does not cover the stake" in got["refused"]
    assert got["short"] == (4, []), (
        "a refused refund moved gold or wrote a ledger row")


def test_pg_one_unpayable_wager_does_not_block_the_rest_of_the_queue():
    """Control: refund-refusal-kills-the-queue (r7).

    `_flush_lobby_bet_refunds` selects `ORDER BY created_at, id LIMIT 1` with
    no exclusion of a row it has already failed on, so a single wager whose
    owner's gold_spent cannot cover it sits at the head of the order forever.
    Round 6's refusal turned that into a `break` after zero refunds: every
    OTHER player's queued lobby-bet refund went unpaid, silently, one log line
    per tick, for as long as that one row existed - while the function's own
    docstring said a failure degrades to "skip it, the janitor retries".

    Executed against a real server because the fix IS a SQL predicate: the
    skip-list is `NOT (id = ANY(CAST(:skip AS uuid[])))` with a Python list
    bound into it, including the EMPTY list on the first pass, and a bind that
    does not round-trip would either select nothing or raise (#448/#391).

    Both directions, because a queue that pays everyone and a queue that
    refuses nobody look identical from outside: the same three wagers with the
    head-of-queue owner made solvent must pay all three."""
    require_pg()

    async def go(head_can_pay):
        engine, sm, pids = await _money_setup({
            S1: 50 if head_can_pay else 0, S2: 50, S3: 50})
        try:
            lobby = uuid.uuid4()
            async with sm() as db:
                for i, steam in enumerate((S1, S2, S3)):
                    await db.execute(text(
                        "INSERT INTO lobby_bets (id, mode, lobby_id, player_id,"
                        "        amount, status, resolved_at, created_at)"
                        " VALUES (gen_random_uuid(), 'ffa', CAST(:l AS uuid),"
                        "         :p, 10, 'refund_pending', NOW(),"
                        "         NOW() - MAKE_INTERVAL(secs => CAST(:o AS int)))"),
                        {"l": str(lobby), "p": pids[steam], "o": 300 - i * 60})
                await db.commit()
            async with sm() as db:
                paid = await main._flush_lobby_bet_refunds(db)
            states = {}
            async with sm() as db:
                for steam in (S1, S2, S3):
                    states[steam] = (await db.execute(text(
                        "SELECT status FROM lobby_bets WHERE player_id = :p"),
                        {"p": pids[steam]})).scalar()
            gold = {}
            for steam in (S1, S2, S3):
                gold[steam] = await _gold(sm, pids[steam])
            return paid, states, gold
        finally:
            await engine.dispose()

    # The head of the queue cannot be paid. Everybody else still is.
    paid, states, gold = run(go(head_can_pay=False))
    assert paid == 2, f"the queue stopped at the row it could not pay: {paid}"
    assert states[S1] == "refund_pending", states[S1]
    assert states[S2] == "refunded" and states[S3] == "refunded", states
    assert gold[S1] == (0, []), gold[S1]
    assert gold[S2] == (40, [10]) and gold[S3] == (40, [10]), gold

    # Negative direction: nothing is being skipped for its own sake.
    paid, states, gold = run(go(head_can_pay=True))
    assert paid == 3, paid
    assert set(states.values()) == {"refunded"}, states
    assert gold[S1] == (40, [10]), gold[S1]


def test_pg_one_unpayable_series_does_not_stop_the_stale_series_sweep():
    """Control: refund-refusal-kills-the-sweep (r7).

    `_refund_series_bets` can now raise, and round 6 left all three of its
    call sites in `_prune_stale_series` unguarded. One bettor whose gold_spent
    is below their stake therefore aborted the WHOLE pass out of the function:
    the remaining mode-2 rows and the entire mode-1 abandon loop never ran,
    and because the selects are ordered and unfiltered the next tick rebuilt
    the same set in the same order and stopped at the same series. The sweep
    was dead, for every other pair, for as long as that one row existed - the
    opposite of the per-item degradation #204 asks for and the comment above
    the loops claimed.

    Mode 2 is the arm exercised here because its select carries `ORDER BY
    rs.id`, so the unpayable series is deterministically FIRST and the test
    cannot pass by luck of ordering. Both directions: with the same bettor
    made solvent, both series are refunded."""
    require_pg()

    async def go(first_can_pay):
        engine, sm, pids = await _money_setup({
            S1: 50 if first_can_pay else 0, S2: 50, S3: 50})
        try:
            # Sorted by id, so the 0000... series is reached first.
            bad = uuid.UUID("00000000-0000-4000-8000-000000000001")
            good = uuid.UUID("ffffffff-0000-4000-8000-000000000002")
            async with sm() as db:
                for sid, bettor in ((bad, S1), (good, S2)):
                    await db.execute(text(
                        "INSERT INTO ranked_series (id, player1_id, player2_id,"
                        "        status, is_tournament, created_at)"
                        " VALUES (:i, :a, :b, 'active', FALSE,"
                        "         NOW() - MAKE_INTERVAL(mins => 300))"),
                        {"i": sid, "a": pids[S3], "b": pids[S2]})
                    await db.execute(text(
                        "INSERT INTO matches (id, series_id, ended_at)"
                        " VALUES (gen_random_uuid(), :s,"
                        "         NOW() - MAKE_INTERVAL(mins => 120))"),
                        {"s": sid})
                    await db.execute(text(
                        "INSERT INTO bets (series_id, player_id, amount)"
                        " VALUES (:s, :p, 10)"), {"s": sid, "p": pids[bettor]})
                await db.commit()
            async with sm() as db:
                changed = await main._prune_stale_series(db)
            async with sm() as db:
                rows = (await db.execute(text(
                    "SELECT series_id, settlement_kind FROM bets"))).all()
            settled = {str(r[0]): r[1] for r in rows}
            gold = {}
            for steam in (S1, S2):
                gold[steam] = await _gold(sm, pids[steam])
            return changed, settled[str(bad)], settled[str(good)], gold
        finally:
            await engine.dispose()

    changed, bad_kind, good_kind, gold = run(go(first_can_pay=False))
    assert changed == 1, f"the sweep stopped at the series it could not pay: {changed}"
    assert bad_kind is None, "an unpayable series was marked settled anyway"
    assert good_kind == "refunded", good_kind
    assert gold[S1] == (0, []), gold[S1]
    assert gold[S2] == (40, [10]), gold[S2]

    changed, bad_kind, good_kind, gold = run(go(first_can_pay=True))
    assert changed == 2, changed
    assert bad_kind == "refunded" and good_kind == "refunded"
    assert gold[S1] == (40, [10]), gold[S1]


def test_a_wager_cannot_be_inserted_while_its_game_settles():
    """Control: wager-lock-dropped-as-redundant (r7).

    The justification round 6 wrote for weakening the settlement lock said the
    stronger mode had made "every concurrent bet insert on that lobby wait
    behind all of it for no benefit". That is false, and the false half is the
    dangerous one: the FK's FOR KEY SHARE is NOT what excludes a wager during
    settlement, because both ffa_bets writers take an explicit lock on the
    ffa_lobbies row FIRST - `place_ffa_bet` (the POST /api/v1/ffa/bets handler,
    which this file and main.py's older comments call ffa_bet_place, a name no
    identifier carries) its own FOR NO KEY UPDATE (which conflicts with FOR NO
    KEY UPDATE exactly as it conflicted with FOR UPDATE), and the lobby-bet
    bind under the Start's FOR UPDATE. Nothing was freed.

    A reader who believed the deleted claim would drop `place_ffa_bet`'s lock
    as redundant, and a wager could then be inserted for the game currently
    settling - after `_refund_ffa_game_bets_strict` has taken its claim SELECT,
    leaving that stake on a config-skewed game neither paid nor returned. So
    this pins the lock, and pins that the comment no longer says the thing
    that would license removing it (#432/#459: the highest-risk comment names
    a mechanism a fix already killed)."""
    src = pathlib.Path(main.__file__).read_text(encoding="utf-8")
    place = src[src.index('@app.post("/api/v1/ffa/bets"'):]
    place = place[:place.index("@app.", 10)]
    assert "FROM ffa_lobbies WHERE id = :lid FOR NO KEY UPDATE" in place, (
        "place_ffa_bet no longer takes its own lock on the lobby row")
    lock_note = src[src.index("# FOR NO KEY UPDATE, not FOR UPDATE (#202/#203/#207)"):
                    src.index("_FFA_LOBBY_LOCK_SQL =")]
    # Measured on the FLATTENED comment, never on its lines. Round 6's one
    # negative control that fired proved the point: an assertion over source
    # as it is wrapped measures where the author broke the line, so reflowing
    # a paragraph reddens a test about its meaning. Strip the comment markers
    # and collapse the whitespace, and the sentence is the sentence.
    flat = " ".join(ln.lstrip().lstrip("#").strip() for ln in lock_note.splitlines())
    flat = " ".join(flat.split())
    # The false benefit claim is gone...
    assert "for no benefit" not in flat
    assert "waited behind all of it" not in flat
    # ...and what replaced it says out loud that no writer is freed, and that
    # the other lock is load-bearing. A deletion that left the paragraph
    # silent would let the next reader re-derive the same wrong conclusion.
    assert "no writer is freed by this change" in flat
    assert "IS LOAD-BEARING AND IS NOT REDUNDANT" in flat
    assert "test_a_wager_cannot_be_inserted_while_its_game_settles" in flat


def test_the_relock_leaves_a_transaction_the_next_read_can_run_in():
    """Control: relock-leaves-a-poisoned-transaction (r7).

    `_ffa_progress_relocked`'s docstring said "IT CANNOT ITSELF BE THE THING
    THAT FAILS THE ANSWER" while its handler only swallowed the exception.
    Under asyncpg one failed statement poisons the whole transaction (#235),
    so on the replay arm a failed re-lock left the session aborted and the
    very next statement - `_ffa_replay_echo`'s SELECT - raised into an
    unhandled 500 carrying none of the progress the function exists to carry.
    The guarantee was written from the arm where the catch is enough.

    The rollback is what makes the sentence true, so the rollback is what is
    pinned: inside the handler, before the fallback is returned, and itself
    contained because a connection that is gone cannot be rolled back either -
    which is the one residue the docstring now states rather than hides."""
    relock = inspect.getsource(main._ffa_progress_relocked)
    body = relock[relock.index("except Exception as _relock_ex:"):]
    # Round 8 gave the handler a SECOND attempt, which moved the thing this
    # assertion has to measure. "A rollback somewhere before the fallback is
    # returned" is now satisfiable by the retry's own rollback, so it would
    # stay green with the first one deleted -- the defect it exists for. What
    # is pinned is the rollback BEFORE THE RETRY: a second attempt made inside
    # a transaction that is still aborted raises for the reason the first one
    # did, which is a retry that cannot succeed.
    retry = body.index("await _ffa_lock_lobby_slot(db, lobby_uuid)")
    assert "await db.rollback()" in body[:retry], (
        "the relock retries without clearing the failed statement, so the "
        "second attempt raises for the reason the first one did")
    assert "await db.rollback()" in body[:body.index("raise FfaReportRefusal(")], (
        "the relock refuses without clearing the failed statement, so the "
        "caller's remaining reads run in an aborted transaction")
    assert "#235" in relock, "the docstring no longer names why the rollback is there"
    # An absolute the code cannot keep is the defect class here, so neither
    # absolute form comes back. Round 10 retired the second of them along with
    # the behaviour it described: this helper IS now the thing that refuses the
    # answer when it has no reading to give, and a docstring still promising it
    # could not would be the same false guarantee one round further on.
    assert "IT CANNOT ITSELF BE THE THING THAT FAILS" not in relock
    assert "IT MUST NOT ITSELF BE THE THING THAT FAILS" not in relock
    assert "IT FAILS CLOSED" in relock
    # The residue is stated, not implied.
    assert "connection that is gone" in relock



# ── the evidence directory's own rules, loaded from where they live ────
#
# ROUND 10 adds the INVOCATION rule (the r6 LOW): a committed report that shows
# a result with no record of the command that produced it is a number from a
# selection nobody can rebuild. Until this round the evidence check asked only
# that a report carry SOME executed result, so a later log could drop its
# command line and stay green -- a check that cannot fail on its own class
# (#342).
#
# The rule lives in backend/tests/evidence/evidence_rules.py rather than here,
# because the re-pin wrapper applies the SAME rule to the one file a pytest run
# cannot cover: its own output, which is written after that run by
# construction. A rule with two implementations is a rule that drifts, and the
# half nobody re-reads is the half that stops matching (#432).

def _evidence_rules():
    import importlib.util

    path = (pathlib.Path(__file__).resolve().parent / "evidence"
            / "evidence_rules.py")
    assert path.is_file(), path
    spec = importlib.util.spec_from_file_location("_scr_evidence_rules", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_the_committed_evidence_re_derives_its_own_numbers():
    """Control: evidence-cites-a-gitignored-path (r7).

    Round 6 committed four evidence files to answer round 4's "the artifacts
    are named under a gitignored scratch directory" - and then stated the
    load-bearing number of one of them, the failure count of each full suite,
    as `ai-collab/<file>.log:0`. That is a grep count over a path that is not
    in the repository, so a reader on a fresh clone cannot confirm the zero at
    all: the finding was closed for the PostgreSQL subset and only narrated
    for the suites (#302 - a claim that cannot be traced to something in the
    repository is a finding, not a record).

    The rule this pins is the general one rather than that one line: NOTHING
    under evidence/ may point outside the repository, for a number or for the
    instrument that produced one. Round 6 pointed at its runner and its
    migration script that way too - less load-bearing than a count, and just
    as unfollowable - so the close is to COMMIT the instruments beside the
    output rather than to narrow the rule to counts. An evidence file quotes
    the run it is evidence of, and names something a clone can open."""
    evidence = pathlib.Path(__file__).resolve().parent / "evidence"
    assert evidence.is_dir(), f"{evidence} is named by the inventory and absent"
    files = sorted(p for p in evidence.iterdir() if p.is_file())
    assert len(files) >= 4, [p.name for p in files]
    reports = [p for p in files if p.suffix == ".txt"]
    assert len(reports) >= 4, [p.name for p in reports]
    for path in files:
        body = path.read_text(encoding="utf-8", errors="replace")
        assert "ai-collab/" not in body, (
            f"{path.name} points at a gitignored path; evidence has to carry "
            f"the output it is evidence of and name instruments a clone has")
    # ...and each report actually carries run output rather than prose. The
    # alternation holds one token per ARTIFACT TYPE this directory keeps: a
    # pytest summary, the migration's second run and its dump comparison, a
    # mutation RED, and the re-pin's own count. Round 8 added the last of
    # those. The re-pin states its result as `rows rewritten now : 0`, and
    # with no token for it this check reddened a report that carried exactly
    # the result it exists to carry. A rule that refuses a legitimate artifact
    # does not hold the line; it teaches the next author to pad the file until
    # the pattern is satisfied, and the padding is what the rule was meant to
    # catch. So the pattern learns the artifact, rather than the artifact
    # learning the pattern.
    result_token = re.compile(
        r"\d+ passed|second run|rows identical|RED:|rows rewritten now")
    for path in reports:
        body = path.read_text(encoding="utf-8", errors="replace")
        assert result_token.search(body), f"{path.name} states no executed result"
    # Both directions on that pattern, in the test that uses it: a typo in the
    # alternation would otherwise make the sweep above pass on every file
    # forever, which is the check that cannot fail (#342/#391). One line of
    # each artifact type has to match, and prose that describes a run without
    # reporting one has to not.
    for positive in ("47 passed, 100 deselected in 10.13s",
                     "rows rewritten now : 0",
                     "IDENTICAL: the second run changed no row",
                     "    RED: E   AssertionError: boom"):
        assert result_token.search(positive), positive
    assert not result_token.search(
        "The runner ran against a real server and everything was fine.")
    # The instruments are here too, or the reports cannot be re-derived.
    names = {p.name for p in files}
    assert any(n.endswith("mutation-runner.py") for n in names), sorted(names)
    assert any(n.endswith("assemble-evidence.py") for n in names), sorted(names)

    # ── ROUND 10: AN INVOCATION ABOVE EVERY RESULT (the r6 LOW) ──────────
    #
    # The rule above asks that a report carry an executed result. It does not
    # ask that the result name the command that produced it, so a later log
    # could drop its invocation line and this check would stay green -- which
    # is the check that cannot fail on its own class (#342). Two summary lines
    # with no record of the selection are two numbers nobody can rebuild.
    #
    # Both directions FIRST, on a fabricated pair, so a typo in either pattern
    # reds here from an assertion ABOUT the rule rather than from whatever the
    # directory happens to contain today. The pair and the checks over it live
    # beside the rule, so the wrapper that cannot run pytest asserts the same
    # two directions rather than an approximation of them.
    rules = _evidence_rules()
    assert rules.selftest() == [], rules.selftest()
    assert rules.results_without_an_invocation(rules.FABRICATED_WITH) == []
    missing = rules.results_without_an_invocation(rules.FABRICATED_WITHOUT)
    assert [line for _n, line in missing] == [
        "1734 passed, 42 skipped, 1 xfailed in 566.55s"], missing
    # ...and a report that declares no run section is not silently exempt: the
    # newest round's reports are required to declare one, below.
    assert rules.results_without_an_invocation("no marker here\n") == []

    # SCOPE, derived from the files rather than written down, and stated
    # rather than left implicit.
    #
    # The rule binds the NEWEST round, and the round is derived from the file
    # NAMES. Earlier rounds' reports stay exempt: they are the record of
    # rounds already judged, on the shapes their instruments printed at the
    # time, and rewriting one now would be editing a log to satisfy a rule
    # written after it, which is not the same artifact as a log that was true
    # when it was written.
    #
    # ROUND 11 CORRECTED WHERE THAT BOUNDARY IS READ FROM. Round 10 derived
    # the newest round from the reports that DECLARED a stdout header -- the
    # ones that had already adopted the rule -- and then required that round
    # to be whole. A later round that declared no stdout in any of its reports
    # therefore moved the boundary with it: it was not the newest ADOPTING
    # round, so none of its files were read, and the rule was satisfied by a
    # directory that had dropped it. That is the check that cannot fail on its
    # own class (#342). A file name carries its round whatever the file says,
    # so the scope is taken from there and no report can opt itself out.
    #
    # THE SET IS TOTAL OVER WHAT EXISTS, and that is what makes it usable: a
    # round's reports are written one at a time, and the suite pair that
    # certifies the source necessarily runs before ANY of them exists, since
    # a report is written FROM that pair's output. So this check covers
    # whatever is there when it runs. What covers the completed set is the
    # re-pin wrapper, which runs last over the directory as committed.
    bodies = {p.name: p.read_text(encoding="utf-8", errors="replace")
              for p in reports}
    newest = rules.newest_round(bodies)
    assert newest is not None, sorted(bodies)
    bound = [n for n in bodies if rules.round_of(n) == newest]
    assert bound, (newest, sorted(bodies))
    assert not rules.scope_problems(bodies), rules.scope_problems(bodies)


def test_the_committed_evidence_is_assembled_from_its_run_stdout():
    """Control: suites-report-carries-an-underived-number (r10).

    The r6 HIGH. Every report here CLAIMED to be generated from the stdout of
    the run it describes, and nothing checked the claim: round 9's suites
    report carried a file count its own run never printed, in a sentence
    shaped exactly like the sentences around it that WERE quoted.

    `assemble-evidence.py` is the answer, and it refuses rather than
    transcribes -- it exits non-zero, naming how many claims it could not
    derive. This runs it twice over: its SELF-TEST, which asserts every
    matching rule fires and every exemption stays quiet in both directions,
    and then `--check` on each report of the newest round, which re-derives
    every number that report's prose asserts from the committed stdout it
    names and rebuilds its verbatim block byte for byte.

    Run from the test rather than trusted from a log, because a committed log
    says what was true when it was written and this says what is true of the
    bytes that ship."""
    evidence = pathlib.Path(__file__).resolve().parent / "evidence"
    tool = evidence / "assemble-evidence.py"
    assert tool.is_file(), tool
    root = pathlib.Path(__file__).resolve().parent.parent.parent

    def run_tool(*args):
        return subprocess.run([sys.executable, str(tool), *args],
                              cwd=str(root), capture_output=True, text=True,
                              timeout=120)

    selftest = run_tool("--selftest")
    assert selftest.returncode == 0, selftest.stdout + selftest.stderr
    assert "rule checks, all as stated" in selftest.stdout, selftest.stdout

    reports = sorted(p for p in evidence.iterdir() if p.suffix == ".txt")
    # EVERY report of the newest round, by its file name, plus every earlier
    # one that declares a stdout of its own. The first half is the scope the
    # invocation rule states -- a round cannot leave itself out by writing a
    # report the assembler never built -- and the second keeps an earlier
    # round's adopted report checked rather than dropping it.
    rules = _evidence_rules()
    names = {p.name: p.read_text(encoding="utf-8", errors="replace")
             for p in reports}
    newest = rules.newest_round(names)
    assert newest is not None, sorted(names)
    checked = [p for p in reports
               if rules.round_of(p.name) == newest
               or rules.STDOUT_HEADER.search(names[p.name])]
    assert checked, sorted(names)
    for path in checked:
        done = run_tool("--check", str(path))
        assert done.returncode == 0, (path.name, done.stdout + done.stderr)
        assert "all derived from" in done.stdout, (path.name, done.stdout)

    # Both directions on the tool itself, from here: a report whose prose
    # carries a number its stdout does not is REFUSED, and the refusal names
    # the count. A check that only ever sees green files is a check nobody has
    # seen fail (#391).
    import importlib.util
    spec = importlib.util.spec_from_file_location("_scr_assembler", tool)
    assembler = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(assembler)
    assert assembler.undrivable("9 paths were hashed\n", "9 paths\n") == []
    refused = assembler.undrivable("12 paths were hashed\n", "9 paths\n")
    assert [c for _k, c in refused] == ["12 paths"], refused


def newest_of_all(rules, paths):
    """The newest round over EVERY report in the directory, not just one kind.

    The kind-restricted maximum answers a different question: a round that has
    written its suites report and not yet its controls report is the newest
    round of the directory and not of the controls reports, and the two
    questions want different answers in different places."""
    return rules.newest_round([p.name for p in paths])


def _load_evidence_module(filename, modname):
    import importlib.util

    path = pathlib.Path(__file__).resolve().parent / "evidence" / filename
    assert path.is_file(), path
    spec = importlib.util.spec_from_file_location(modname, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_the_assembler_counts_the_checks_it_ran():
    """Control: selftest-count-is-not-derived (r11).

    The assembler exists to refuse a number a run did not produce, and the
    last line of its own self-test was one: `len(TERMS) + 19`, a constant
    beside a body that runs two loops and thirteen standalone checks. It
    printed one fewer than the run made, and that line is committed verbatim
    in several of the previous round's logs -- so every report of that round
    carried a count of the instrument's own checks that the instrument could
    not derive. Nothing noticed, because the test that read the output
    asserted the PHRASE and never the number (#342).

    Two comparisons here, and the second is the one that makes the first
    worth making. The printed number has to equal the number of check RECORDS
    the run produced -- and that number has to equal the number of times the
    run actually invoked `expect`, counted independently by tracing the run
    rather than by reading the source, because the source's two loops are
    exactly why a count read off the source went wrong."""
    evidence = pathlib.Path(__file__).resolve().parent / "evidence"
    tool = evidence / "assemble-evidence.py"
    assert tool.is_file(), tool
    root = pathlib.Path(__file__).resolve().parent.parent.parent

    done = subprocess.run([sys.executable, str(tool), "--selftest"],
                          cwd=str(root), capture_output=True, text=True,
                          timeout=120)
    assert done.returncode == 0, done.stdout + done.stderr
    printed = re.search(r"selftest: (\d+) rule checks, all as stated",
                        done.stdout)
    assert printed, done.stdout

    assembler = _load_evidence_module("assemble-evidence.py", "_scr_assembler2")
    records = assembler.run_checks()
    assert all(ok for _name, ok, _detail in records), [
        (name, detail) for name, ok, detail in records if not ok]
    assert len(records) >= 30, len(records)

    # The independent count: what the run DID, not what the file looks like.
    seen = []

    def tracer(frame, event, _arg):
        if event == "call" and frame.f_code.co_name == "expect":
            seen.append(frame.f_code.co_name)
        return None

    previous = sys.gettrace()
    sys.settrace(tracer)
    try:
        assembler.run_checks()
    finally:
        sys.settrace(previous)

    assert len(seen) == len(records), (
        f"the self-test invoked its check {len(seen)} times and recorded "
        f"{len(records)} results")
    assert int(printed.group(1)) == len(records), (
        f"the self-test printed {printed.group(1)} and ran {len(records)} "
        f"checks")


def test_the_new_controls_a_report_claims_are_the_ones_the_inventory_tags():
    """Control: new-controls-list-credits-another-round (r11).

    A mutation-controls report lists the controls that are new in its round.
    That list is written beside a set that grows, which is the shape this
    file has already been wrong in twice -- and it was wrong again: round
    10's report listed nine, one of which a previous round had added and this
    one had not touched, while the inventory below tagged eight. Two
    statements of one set, and nothing compared them.

    This compares them, in both directions: a name listed as new that the
    inventory tags for another round reds, and a name the inventory tags for
    this round that the report does not list reds. The inventory is this
    module's own docstring, so the comparison is against the place every
    control is already registered rather than against a third list."""
    rules = _evidence_rules()
    evidence = pathlib.Path(__file__).resolve().parent / "evidence"
    doc = sys.modules[__name__].__doc__
    reports = sorted(p for p in evidence.iterdir()
                     if p.name.endswith("-mutation-controls.txt"))
    assert len(reports) >= 4, [p.name for p in reports]

    newest = rules.newest_round([p.name for p in reports])
    assert newest is not None, [p.name for p in reports]
    claiming = []
    for path in reports:
        body = path.read_text(encoding="utf-8", errors="replace")
        number = rules.round_of(path.name)
        if rules.controls_claimed_new(body) is None:
            # A report written before the heading existed says nothing this
            # rule can check, and is left as its round wrote it. The newest
            # round's report is NOT allowed that: a round cannot answer the
            # rule by making no claim.
            assert number != newest, (
                f"{path.name} is the newest round's mutation-controls report "
                f"and lists no controls as new in its round")
            continue
        claiming.append(path.name)
        bad = rules.new_control_problems(body, doc, number)
        assert not bad, (path.name, bad)
    assert len(claiming) >= 2, claiming

    # ...and the same requirement keyed on CONTENT rather than on the file
    # name, because a name is something a round chooses. Any report of the
    # newest round that names the mutation runner's own log as its stdout IS
    # that round's mutation-controls report, whatever it is called, and has to
    # carry the list. Vacuous while the round is still being written -- the
    # report is assembled from that log and cannot exist before it -- and
    # binding by the time the closing check runs over the directory as
    # committed.
    evidence_reports = sorted(p for p in evidence.iterdir()
                              if p.suffix == ".txt")
    for path in evidence_reports:
        if rules.round_of(path.name) != newest_of_all(rules, evidence_reports):
            continue
        body = path.read_text(encoding="utf-8", errors="replace")
        if not re.search(r"^stdout:.*mutation-run", body, re.M):
            continue
        assert rules.controls_claimed_new(body) is not None, (
            f"{path.name} names the mutation runner's log as its stdout and "
            f"lists no controls as new in its round")

    # Both directions, on the rule, from here -- so a parse that silently
    # matched nothing would red on an assertion ABOUT the rule rather than
    # pass over whatever the directory happens to hold (#391).
    good = rules.FABRICATED_REPORT
    assert rules.new_control_problems(good, rules.FABRICATED_INVENTORY,
                                      3) == []
    credited = good.replace("  another-thing-that-broke\n",
                            "  an-older-control\n")
    named = sorted(n for n, _why in
                   rules.new_control_problems(credited,
                                              rules.FABRICATED_INVENTORY, 3))
    assert named == ["an-older-control", "another-thing-that-broke"], named


def test_the_residual_reach_rule_holds_in_both_directions():
    """Control: residual-reach-rule-admits-a-prose-count (r11).

    A round's residual list is the one place it says what it did not close,
    and it is read by somebody deliberately not reading the rest. One list
    said, in an item, that two seats one number apart can both settle -- a
    second settlement of one physical game, which pays and rates twice -- and
    said sixteen lines later that a different item was the only one that
    could move a rating. Neither sentence was wrong about its own subject;
    the second was a hand-made count of the first.

    `residual_rules.py` takes the reach out of the prose: each item carries
    one tag in a pinned shape, the count under the list is derived from the
    tags, and no other line in the section may state a reach. This asserts
    the rule in both directions on its own fixtures -- a clean list, an inert
    reword, a second statement of the reach, an item with no tag, a count
    that disagrees, and a list with no count at all.

    The document it is run against lives under the gitignored scratch, so it
    is not named here and not read here: the executed run over the real list,
    with its mutation and its inert twin, is in this round's report."""
    rules = _load_evidence_module("residual_rules.py", "_scr_residual_rules")
    checks = rules.selftest_checks()
    assert all(ok for _name, ok, _detail in checks), [
        (name, detail) for name, ok, detail in checks if not ok]
    assert len(checks) >= 8, len(checks)
    assert rules.selftest() == [], rules.selftest()

    # The two directions again from here, on the claim the round is about, so
    # that a fixture quietly edited to agree with a broken rule still reds.
    assert rules.reach_problems(rules.CLEAN) == []
    assert rules.reach_problems(rules.INERT) == []
    stale = rules.reach_problems(rules.DIRTY_CLAIM)
    assert len(stale) == 1 and "one item in this list" in stale[0], stale


def test_every_round_seven_control_names_a_test_that_exists():
    """The same pairing for round 7."""
    mod = sys.modules[__name__]
    for name in ("test_pg_the_exact_refund_statement_runs_against_a_real_server",
                 "test_pg_one_unpayable_wager_does_not_block_the_rest_of_the_queue",
                 "test_pg_one_unpayable_series_does_not_stop_the_stale_series_sweep",
                 "test_a_wager_cannot_be_inserted_while_its_game_settles",
                 "test_the_relock_leaves_a_transaction_the_next_read_can_run_in",
                 "test_the_committed_evidence_re_derives_its_own_numbers"):
        assert callable(getattr(mod, name, None)), name
    # One round-7 control names a test in ANOTHER file, because the property
    # it guards belongs to the prune sweep's shape rather than to this file's
    # subject. Checked by reading that file rather than importing it: a
    # control whose test has been renamed away is a control that runs nothing,
    # and the pairing has to cover the case that is easiest to lose.
    neighbour = (pathlib.Path(__file__).resolve().parent
                 / "test_report_disconnect_durability.py")
    assert neighbour.is_file(), neighbour
    assert ("def test_the_prune_batch_commits_per_series_so_it_cannot_hold_the_chain("
            in neighbour.read_text(encoding="utf-8")), (
        "the refusal-skips-without-ending-the-transaction control names a "
        "test that is no longer in test_report_disconnect_durability.py")


# ── round 8: the capture exits, the realigned resubmission, the shipped files ─

def test_pg_a_refusal_raised_after_a_capture_reads_the_lobby_again():
    """Control: refusal-after-capture-reuses-stale-progress (r8).

    `_quarantine_report` rolls this request's transaction back before it takes
    its advisory lock, and commits its own row -- so the lobby lock the endpoint
    was holding is RELEASED inside the capture, and a report of the same sitting
    that had been waiting on that row can derive its slot and settle in the gap.
    The progress the caller is still holding was read before all of that.

    Driven on a real server, through the production refusal path and the
    production capture writer: the counters are read under the lock, the sitting
    then advances exactly as a waiting report would advance it, and
    `_ffa_record_and_refuse` is called with the copy read before the advance.
    The refusal it raises has to carry the lobby's CURRENT numbers.

    `settled_game` is the other half. It is a claim about a ROW, it does not
    move when the counter does, and it has to survive the re-read -- while
    staying strictly below the fresh `expected_game`, which is the pair's own
    invariant and the one an answer must never break."""
    require_pg()

    async def go():
        engine, sm, pids, _mid = await _endpoint_fixture(
            games_played=1, recorded_number=1, recorded_room="rm_211531_r1")
        try:
            async with sm() as db:
                _row, expected = await main._ffa_lock_lobby_slot(db, LOBBY)
                # What every answer of this request would have carried: this
                # report named game 1 and the lobby holds a row for it.
                stale = main._ffa_progress(expected - 1, settled_game=1)
                await db.rollback()
            # The waiting report settles game 2 and consumes the slot.
            async with sm() as db:
                await db.execute(text(
                    "INSERT INTO ffa_matches (id, lobby_id, photon_room_id,"
                    " winner_id, ended_at, game_number) VALUES"
                    " (:i, :l, :r, :w, NOW(), CAST(:g AS SMALLINT))"),
                    {"i": uuid.uuid4(), "l": LOBBY, "r": "rm_211531_r2",
                     "w": pids[S3], "g": 2})
                await main._ffa_advance_lobby_slot(db, LOBBY)
                await db.commit()
            raised = None
            async with sm() as db:
                try:
                    await main._ffa_record_and_refuse(
                        db, report=_endpoint_report(ROW_A, S3, "rm_211531_r1"),
                        lobby_uuid=LOBBY, id_by_steam=dict(pids),
                        reason="ffa_game_contradiction",
                        why="game 1 recorded as rm_211531_r1: test",
                        detail="This game is already recorded",
                        progress=stale)
                except main.FfaReportRefusal as ex:
                    raised = ex
            async with sm() as db:
                kept = (await db.execute(text(
                    "SELECT COUNT(*) FROM match_report_quarantine"
                    " WHERE group_id = :g"), {"g": LOBBY})).scalar()
            return stale, raised, int(kept)
        finally:
            await engine.dispose()

    stale, raised, kept = run(go())
    assert stale == {"games_played": 1, "expected_game": 2, "settled_game": 1}
    assert raised is not None, "_ffa_record_and_refuse did not raise"
    # The capture really happened, so this is the terminal arm and not the 503.
    assert kept == 1
    assert raised.status_code == 409
    # The counters are the sitting's CURRENT ones, not the pre-capture copy.
    assert raised.progress["games_played"] == 2, (
        "the refusal answered with the counter read before the capture")
    assert raised.progress["expected_game"] == 3
    # ...and the row claim survived the re-read, still strictly below it.
    assert raised.progress["settled_game"] == 1
    assert raised.progress["settled_game"] < raised.progress["expected_game"]


def test_pg_a_realigned_resubmission_is_echoed_and_never_settled_twice():
    """Control: advertised-number-is-not-the-settling-one (r8).

    The client lane's realignment rests on one property of this endpoint, and
    this is the executed statement of it: the number a terminal refusal
    ADVERTISES is the number the room must key its next delivery at, and a
    delivery of one physical game under the room-wide corrected key is answered
    ONCE -- settled, or echoed against the row that already holds it -- never
    settled twice.

    Three steps, through the real endpoint, in the order the contract's
    realignment section describes them:

      1. a report whose tail is AHEAD of the lobby is refused, and the refusal
         names the lobby's own next slot, in the body field and in the detail
         string both;
      2. the room realigns to that number and the first elector settles there;
         the SECOND elector's delivery of the same physical game carries the
         same key and the same body, and is answered by the identical-body echo
         rather than settled again -- which is what makes a room-wide re-key
         safe where a per-seat one is not;
      3. a DIFFERENT account under that same key is not echoed and settles
         nothing: the lobby still holds exactly one row for that game.

    Step 1's settlement is written directly rather than driven through the
    endpoint. What it stands in for is pinned by
    test_pg_a_settlement_commits_the_catch_up_and_lands_on_the_free_number;
    what THIS test is about is the pair -- advertised number, and the answer a
    delivery keyed at it receives."""
    require_pg()

    async def go():
        engine, sm, pids, _mid = await _endpoint_fixture(
            games_played=2, recorded_number=1, recorded_room="rm_211531_r1")
        try:
            # 1. the room is four games ahead of the lobby.
            ahead = None
            try:
                await _call_endpoint(sm, _endpoint_report(
                    ROW_A, S3, "rm_211531_r7", with_slots=True))
            except main.FfaReportRefusal as ex:
                ahead = ex
            if ahead is None:
                # Five, because the caller unpacks five: a failure here has to
                # reach its own assertion rather than a tuple-size error.
                return ahead, None, None, None, 0
            advertised = int(ahead.progress["expected_game"])
            # 2. the room realigns onto `advertised`, and the first elector
            #    settles the physical game there.
            async with sm() as db:
                mid = uuid.uuid4()
                await db.execute(text(
                    "INSERT INTO ffa_matches (id, lobby_id, photon_room_id,"
                    " player_count, winner_id, ended_at, game_number) VALUES"
                    " (:i, :l, :r, 3, :w, NOW(), CAST(:g AS SMALLINT))"),
                    {"i": mid, "l": LOBBY,
                     "r": f"rm_211531_r{advertised}", "w": pids[S3],
                     "g": advertised})
                for s, (r, p, k) in ROW_A.items():
                    await db.execute(text(
                        "INSERT INTO ffa_match_players (match_id, player_id,"
                        "  rounds_won, points_total, kills, placement,"
                        "  rating_change, xp_gained, gold_gained)"
                        " VALUES (:m, :p, :r, :pt, :k, :pl, :rc, :xp, :gd)"),
                        {"m": mid, "p": pids[s], "r": r, "pt": p, "k": k,
                         "pl": 1 if s == S3 else 3, "rc": 2.5 if s == S3 else -1.0,
                         "xp": 40 if s == S3 else 0, "gd": 7 if s == S3 else 0})
                await main._ffa_advance_lobby_slot(db, LOBBY)
                await db.commit()
            # the second elector, same key, same body.
            echo = await _call_endpoint(sm, _endpoint_report(
                ROW_A, S3, f"rm_211531_r{advertised}", with_slots=True))
            # 3. a different account of that same game, same key.
            disagreeing = None
            try:
                await _call_endpoint(sm, _endpoint_report(
                    ROW_B, S1, f"rm_211531_r{advertised}", with_slots=True))
            except Exception as ex:          # noqa: BLE001 - the class is the point
                disagreeing = ex
            async with sm() as db:
                rows = (await db.execute(text(
                    "SELECT COUNT(*) FROM ffa_matches WHERE lobby_id = :l"
                    "   AND game_number = CAST(:g AS SMALLINT)"),
                    {"l": LOBBY, "g": advertised})).scalar()
            return ahead, advertised, echo, disagreeing, int(rows)
        finally:
            await engine.dispose()

    ahead, advertised, echo, disagreeing, rows = run(go())
    # 1. the refusal is terminal and it names the lobby's own next slot.
    assert ahead is not None, "an ahead tail was not refused"
    assert ahead.status_code == 409
    assert advertised == 3
    assert ahead.progress == {"games_played": 2, "expected_game": 3}, (
        "the refusal did not advertise the lobby's free slot")
    # The same number is in the detail string too, which is the marker the
    # shipped live-points path already reads (ApiClient.cs:2844).
    assert "expected_game=3" in ahead.detail
    # ...and it is a number this endpoint would SETTLE, which is the whole
    # point of advertising it: a realignment onto a number the rule refuses
    # would loop the sitting rather than recover it.
    assert main._ffa_game_number_refusal(advertised, advertised) is None
    # 2. the second elector's identical body is echoed, not settled again.
    assert echo is not None
    assert echo.message == "Already recorded"
    assert echo.settled_game == advertised
    assert echo.games_played == 3 and echo.expected_game == 4
    assert echo.settled_game < echo.expected_game
    # 3. a different account under that key settles nothing.
    assert disagreeing is not None, "a contradicting account was not refused"
    assert rows == 1, "one physical game holds more than one row"


# ── round 12: what a REAL settlement through the endpoint needs ───────────
# `_settle_directly` below exists because this file's narrow `ffa_matches` and
# `ffa_match_players` do not carry the columns a settlement writes. That is
# fine for a test about WHICH NUMBER a delivery may use -- but the r7 lens
# found the thing it is not fine for: the recovery leg of the missed-update
# sequence checked the number and then wrote the row itself, so the step the
# finding is about -- a re-signed parked delivery ACCEPTED by the endpoint --
# was never driven at all.
#
# So the columns are added, once, on top of the fixture the rest of this file
# uses. They are the ones 154/156/167/177/206/216/233/324/327 declare, at the
# types those migrations declare, because a test table that narrows a column is
# exercising a different write. Cards, offers, achievements, earned packs and
# wagers are NOT built here and do not need to be: every one of them is inside
# the endpoint's own savepointed try/except, so a missing table degrades to the
# same "not this game" the production guard gives and the report still settles.
_SETTLE_SCHEMA = """
DROP TABLE IF EXISTS gold_transactions;
DROP TABLE IF EXISTS glicko_ratings_ffa;

ALTER TABLE players
    ADD COLUMN IF NOT EXISTS total_xp INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS ffa_xp_earned INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS gold_earned INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS ffa_gold_earned INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS active_player_color_id BIGINT;

ALTER TABLE ffa_matches
    ADD COLUMN IF NOT EXISTS duration_seconds INTEGER,
    ADD COLUMN IF NOT EXISTS game_version VARCHAR(32),
    ADD COLUMN IF NOT EXISTS region VARCHAR(8),
    ADD COLUMN IF NOT EXISTS hmac_signature VARCHAR(160),
    ADD COLUMN IF NOT EXISTS reported_by UUID,
    ADD COLUMN IF NOT EXISTS is_ranked BOOLEAN NOT NULL DEFAULT TRUE,
    ADD COLUMN IF NOT EXISTS started_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS timeline TEXT,
    ADD COLUMN IF NOT EXISTS battles_total INTEGER,
    ADD COLUMN IF NOT EXISTS paid_battles REAL,
    ADD COLUMN IF NOT EXISTS elapsed_seconds INTEGER;

ALTER TABLE ffa_match_players
    ADD COLUMN IF NOT EXISTS slot SMALLINT,
    ADD COLUMN IF NOT EXISTS rating_before DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS rating_after DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS fps_avg SMALLINT,
    ADD COLUMN IF NOT EXISTS ping_avg SMALLINT,
    ADD COLUMN IF NOT EXISTS bullets_fired INTEGER,
    ADD COLUMN IF NOT EXISTS bullets_hit INTEGER,
    ADD COLUMN IF NOT EXISTS blocks_activated INTEGER,
    ADD COLUMN IF NOT EXISTS blocks_successful INTEGER,
    ADD COLUMN IF NOT EXISTS keys_pressed INTEGER,
    ADD COLUMN IF NOT EXISTS active_seconds REAL,
    ADD COLUMN IF NOT EXISTS fps_timeline VARCHAR(512),
    ADD COLUMN IF NOT EXISTS ping_timeline VARCHAR(512),
    ADD COLUMN IF NOT EXISTS hit_timeline VARCHAR(1024),
    ADD COLUMN IF NOT EXISTS block_timeline VARCHAR(1024),
    ADD COLUMN IF NOT EXISTS damage_dealt INTEGER,
    ADD COLUMN IF NOT EXISTS damage_dealt_timeline VARCHAR(1024),
    ADD COLUMN IF NOT EXISTS kill_timeline VARCHAR(512),
    ADD COLUMN IF NOT EXISTS end_stats TEXT,
    ADD COLUMN IF NOT EXISTS game_points_at_leave SMALLINT,
    ADD COLUMN IF NOT EXISTS color_name VARCHAR(40),
    ADD COLUMN IF NOT EXISTS color_hex VARCHAR(9);

-- The two columns 324 declares, both on this path since bug 392. The
-- endpoint reads the lobby's departure_causes map just before it writes
-- the per-player rows, and each of those rows carries left_early_involuntary.
ALTER TABLE ffa_lobbies
    ADD COLUMN IF NOT EXISTS departure_causes JSONB NOT NULL DEFAULT '{}'::jsonb;

ALTER TABLE ffa_match_players
    ADD COLUMN IF NOT EXISTS left_early_involuntary BOOLEAN NOT NULL DEFAULT false;

CREATE TABLE glicko_ratings_ffa (
    player_id        UUID PRIMARY KEY REFERENCES players(id) ON DELETE CASCADE,
    rating           DOUBLE PRECISION NOT NULL DEFAULT 1500,
    rating_deviation DOUBLE PRECISION NOT NULL DEFAULT 350,
    volatility       DOUBLE PRECISION NOT NULL DEFAULT 0.06,
    peak_rating      DOUBLE PRECISION NOT NULL DEFAULT 1500,
    games_played     INTEGER NOT NULL DEFAULT 0,
    wins             INTEGER NOT NULL DEFAULT 0,
    top3             INTEGER NOT NULL DEFAULT 0,
    placement_sum    INTEGER NOT NULL DEFAULT 0,
    last_calculated  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE gold_transactions (
    id           BIGSERIAL PRIMARY KEY,
    player_id    UUID NOT NULL REFERENCES players(id) ON DELETE CASCADE,
    amount       INTEGER NOT NULL,
    reason       VARCHAR(64) NOT NULL,
    reference_id TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""


async def _settling_fixture(games_played, recorded_number, recorded_room):
    """`_endpoint_fixture` plus the columns a settlement writes."""
    engine, sm, pids, mid = await _endpoint_fixture(
        games_played=games_played, recorded_number=recorded_number,
        recorded_room=recorded_room)
    async with engine.begin() as conn:
        for stmt in [s for s in _SETTLE_SCHEMA.split(";") if s.strip()]:
            await conn.execute(text(stmt))
    return engine, sm, pids, mid


def _park(key, room_base, vec, winner, reporter):
    """One parked delivery: this seat's record of ONE physical game.

    `key` is the seat's identity for that game, frozen at the first write for
    it. The room id is a FIELD of the body, and the number the server
    advertises lives in that field's `_rN` tail -- so a number that changes is
    a field that changes, never an entry that moves.

    `refusals` counts the times THIS entry has been answered with a refusal,
    which is at most once: a refusal carrying `settled_game` is terminal for
    the entry, so there is no second answer to count."""
    return {"key": key, "room_base": room_base, "vec": vec, "winner": winner,
            "reporter": reporter, "advertised": None, "deliveries": 0,
            "refusals": 0}


def _recover_parked(outbox, key, refusal):
    """Write the number the server advertised into a parked entry's room-id
    FIELD -- the seat taking up the last advertisement it holds.

    THE KEY DOES NOT MOVE, and that is the whole rule. A refusal advertises
    `expected_game`; the seat writes that number into the room-id FIELD of the
    body it holds for the physical game it is keying. It does not mint a second
    entry for that game, and it does not re-identify the one it holds --
    first-write-wins says one delivery per physical game, and a keying that
    opened a second one would be exactly the second settlement of one game that
    the freeze exists to prevent.

    ROUND 14: WHICH ENTRY THIS IS APPLIED TO IS THE RULING. It is the entry the
    seat is about to deliver for the FIRST time -- a game it has keyed but not
    yet filed. It is never an entry the server has already refused with
    `settled_game`: that entry is terminal and is dropped, because the server
    cannot tell a behind seat's later game from a conflicting second account of
    the game already settled at the number it named, and re-keying it at the
    free number would settle that conflicting account as a game of its own
    (#283, #378). What the advertisement moves is the NEXT game's field.

    Nothing else about the body changes: same roster, same tallies, same
    winner, same reporter. A delivery is a RESEND of what the seat froze, not
    an edit of the evidence."""
    advertised = int(refusal.progress["expected_game"])
    entry = outbox[key]
    entry["advertised"] = advertised
    return entry


def _settled_game_disposition(entry, refusal):
    """What the seat does with THIS entry when this refusal answers it, and
    which number its NEXT key derives from: `(disposition, number)`.

    The contract's arm table gives a refusal carrying `settled_game` exactly
    one disposition, and round 14 is where it stopped being a redirect. The
    field says the NUMBER this delivery named is finished and says nothing
    about the physical game the body describes -- and TWO deliveries produce
    that answer, which the server cannot tell apart. One is a behind seat's
    LATER physical game, refused there because the seat is behind. The other is
    a CONFLICTING second account of the game already settled at that number.
    They arrive as the same bytes under the same key, no fact the server holds
    separates them, and a delay is under a client's own control, so nothing the
    client carries separates them either (#283, #378).

    So the entry is TERMINAL. Re-keying it at the free number would settle a
    conflicting account as a second physical game -- a second row, a second
    rating, a second payout -- while dropping it costs at most one real game's
    automatic settlement, and the server has already quarantined that payload
    for an operator (`_ffa_record_and_refuse`). One of those costs is
    recoverable and the other is not.

    The NUMBER returned beside the disposition is what the refusal advertises,
    and it is the seat's next KEY rather than this entry's: the entry is gone.
    A refusal carrying no `settled_game` is terminal for the payload on the
    same answer, which is the row beside it in the same table -- both 409 arms
    agree here, and saying so is the finding rather than a simplification."""
    entry["refusals"] += 1
    advertised = refusal.progress.get("expected_game")
    return "terminal", None if advertised is None else int(advertised)


def _drop_parked(outbox, key):
    """The terminal disposition, executed: the entry leaves the outbox.

    Returned rather than discarded, because "kept for review" is part of the
    rule and a caller has to be able to say what was dropped -- how often it
    was delivered, and that it was never delivered again."""
    return outbox.pop(key)


def _delivery_of(entry):
    """The report the parked entry is sent as, at the number it now carries."""
    entry["deliveries"] += 1
    return _endpoint_report(
        entry["vec"], entry["winner"],
        "%s_r%d" % (entry["room_base"], int(entry["advertised"])),
        reporter=entry["reporter"], with_slots=True)


async def _settle_directly(sm, pids, row, number):
    """Write the settlement a report keyed at `number` would leave, and consume
    the slot -- the two steps the witness above writes inline.

    Behind the endpoint on purpose, and the reason is the same one that
    docstring gives: this fixture's `ffa_matches` is the narrow one these tests
    need, and a settlement driven through the endpoint writes columns it does
    not carry. What a REAL settlement does with the slot is pinned separately by
    test_pg_a_settlement_commits_the_catch_up_and_lands_on_the_free_number. What
    the test below is about is which NUMBER the next delivery may use, and that
    is decided before any column is written.

    The winner is derived from the row rather than named, so a caller cannot
    silently seat the wrong one: ROW_A is won by S3 and ROW_B by S1, and a
    hardcoded winner would have made the second settlement disagree with its own
    scoreboard."""
    winner = max(row, key=lambda s: (row[s][0], row[s][1]))
    order = sorted(row, key=lambda s: (-row[s][0], -row[s][1]))
    async with sm() as db:
        mid = uuid.uuid4()
        await db.execute(text(
            "INSERT INTO ffa_matches (id, lobby_id, photon_room_id,"
            " player_count, winner_id, ended_at, game_number) VALUES"
            " (:i, :l, :r, 3, :w, NOW(), CAST(:g AS SMALLINT))"),
            {"i": mid, "l": LOBBY, "r": f"rm_211531_r{number}",
             "w": pids[winner], "g": number})
        for s, (r, p, k) in row.items():
            await db.execute(text(
                "INSERT INTO ffa_match_players (match_id, player_id,"
                "  rounds_won, points_total, kills, placement,"
                "  rating_change, xp_gained, gold_gained)"
                " VALUES (:m, :p, :r, :pt, :k, :pl, :rc, :xp, :gd)"),
                {"m": mid, "p": pids[s], "r": r, "pt": p, "k": k,
                 "pl": order.index(s) + 1,
                 "rc": 2.5 if s == winner else -1.0,
                 "xp": 40 if s == winner else 0,
                 "gd": 7 if s == winner else 0})
        await main._ffa_advance_lobby_slot(db, LOBBY)
        await db.commit()


def test_pg_a_realigned_sitting_issues_each_game_its_own_number():
    """Control: realignment-reuses-the-advertised-number (r9).

    The witness above delivers ONE game at the advertised number and stops, so
    it cannot see what the sitting does next -- and that is where round 8's
    realignment section contradicted itself. It said the host sets the base so
    the NEXT PHYSICAL GAME keys at `E`, and it also said the game that was
    refused is recovered by one further delivery under the room's corrected
    base, which is the same `E`. Two different physical games, one number. The
    number is an identity, so the second of them to arrive is refused
    terminally, captured, and lost -- and the seat then advertises `E+1` and the
    room repeats the pattern for every remaining game of the sitting, which is
    not the one-lost-game-per-measurement bound the section claimed.

    So this test runs the sitting ON past the advertised number and states the
    three facts the corrected rule rests on:

      1. the parked game, redelivered at `E`, SETTLES -- the advertised number
         is the one the recovered game takes;
      2. the next physical game, keyed at `E+1`, ALSO settles -- the sitting
         continues, two physical games hold two numbers;
      3. a second physical game keyed at `E` is REFUSED and names `E` as
         settled -- which is what makes the numbers an issued sequence rather
         than a base two games can share.

    Together they are the executed form of the rule: the room issues `E` to
    exactly one delivery, the parked one when there is a parked one, and every
    later game takes the next number up. Fact 3 is the finding itself, run."""
    require_pg()

    async def go():
        engine, sm, pids, _mid = await _endpoint_fixture(
            games_played=2, recorded_number=1, recorded_room="rm_211531_r1")
        try:
            ahead = None
            try:
                await _call_endpoint(sm, _endpoint_report(
                    ROW_A, S3, "rm_211531_r7", with_slots=True))
            except main.FfaReportRefusal as ex:
                ahead = ex
            if ahead is None:
                # SIX values on every path. A five-value return here met the
                # caller's unpack with a ValueError naming a count, so the
                # failure reported the shape of the return instead of the
                # fact that failed -- and the assertion written to name that
                # fact never ran. A check whose message cannot reach the
                # reader is the same defect one layer down from a check that
                # cannot fail (#342).
                return None, None, None, None, [], None
            advertised = int(ahead.progress["expected_game"])
            # 1. the PARKED game is recovered at the advertised number. Written
            #    behind the endpoint, the same way the witness above writes it
            #    and for the same reason -- what a real settlement does with
            #    this slot is pinned by
            #    test_pg_a_settlement_commits_the_catch_up_and_lands_on_the_free_number.
            await _settle_directly(sm, pids, ROW_A, advertised)
            async with sm() as db:
                _row, after_recovery = await main._ffa_lock_lobby_slot(db, LOBBY)
            # 2. THE FINDING, run. The NEXT physical game -- a different
            #    scoreboard -- keyed at the SAME number, which is what round 8's
            #    3a.3 instructed the host to set the base to.
            collided = None
            try:
                await _call_endpoint(sm, _endpoint_report(
                    ROW_B, S3, f"rm_211531_r{advertised}", with_slots=True))
            except main.FfaReportRefusal as ex:
                collided = ex
            # 3. the same next physical game at the number the corrected rule
            #    issues it instead.
            free = main._ffa_game_number_refusal(advertised + 1, advertised + 1)
            await _settle_directly(sm, pids, ROW_B, advertised + 1)
            async with sm() as db:
                numbers = [int(n) for n in (await db.execute(text(
                    "SELECT game_number FROM ffa_matches WHERE lobby_id = :l"
                    " ORDER BY game_number"), {"l": LOBBY})).scalars().all()]
                gp = int((await db.execute(text(
                    "SELECT games_played FROM ffa_lobbies WHERE id = :l"),
                    {"l": LOBBY})).scalar())
            return advertised, after_recovery, collided, free, numbers, gp
        finally:
            await engine.dispose()

    advertised, after_recovery, collided, free, numbers, gp = run(go())
    assert advertised is not None, (
        "the ahead tail was not refused, so the sitting was never realigned "
        "and nothing below this line was exercised")
    assert advertised == 3, advertised
    # 1. the recovered game consumed the advertised number, and the sitting's
    #    next slot is the one above it -- not the same one again.
    assert after_recovery == advertised + 1, after_recovery
    # 2. a second physical game keyed at the advertised number is REFUSED,
    #    terminally, and the answer names that number as settled. Round 8's
    #    rule keyed exactly this delivery there, so this is the cost it carried:
    #    one physical game refused and captured per measurement, for every
    #    remaining game of the sitting.
    assert collided is not None, (
        "a second physical game keyed at the advertised number was not refused")
    assert collided.status_code in (403, 409), collided.status_code
    assert collided.progress.get("settled_game") == advertised, collided.progress
    # 3. the next number up is one this endpoint would settle, so issuing it to
    #    the next physical game recovers the sitting rather than stalling it.
    assert free is None, free
    # The lobby holds one row per physical game at distinct numbers -- the
    # pre-seeded 1, the recovered game at 3, the next physical game at 4 -- and
    # the counter is on the last of them. Two physical games never share a
    # number, and none was lost to a collision.
    assert numbers == [1, advertised, advertised + 1], numbers
    assert gp == advertised + 1, gp


def test_pg_a_seat_that_missed_an_update_recovers_in_one_submission():
    """Controls: refusal-advertises-the-number-it-just-settled (r10),
    recovery-re-keys-the-parked-delivery (r12),
    recovery-mints-a-second-parked-key (r12),
    recovery-resubmits-the-stale-number (r13),
    terminal-walk-keeps-the-dropped-entry (r14).

    The SERVER is the sole allocator of the game number, and this is the
    property that makes a seat which missed a room update recoverable rather
    than excluded: every answer given under the lobby lock advertises the
    number the server accepts NEXT, so the answer that refuses a behind seat is
    also the answer that tells it what to use. Nothing is counted locally and
    nothing is realigned between seats.

    IT IS THE SEAT THAT RECOVERS IN ONE SUBMISSION, AND ROUND 14 IS WHERE THE
    ENTRY STOPPED DOING SO. Rounds 12 and 13 had the refused entry re-signed at
    the advertised number and settled, which is a REDIRECT, and the redirect is
    ruled out: a refusal carrying `settled_game` is given by two deliveries the
    server cannot tell apart -- this seat's later physical game, and a
    conflicting second account of the game already settled at that number --
    so re-keying such a delivery at the free number can settle the conflicting
    account as a game of its own. The conservative disposition is the only one
    the integrity bar admits. The entry is dropped, the server has already
    quarantined its payload for an operator, and the seat derives its NEXT
    key from the advertised number. The cost -- a real later game that now
    waits on a human -- is the residual this walk makes visible rather than
    hides: it asserts that the dropped body settles at NO number.

    The sequence such a seat actually walks:

      1. it holds an advertisement, and another elector settles the parked game
         at that number while it is not looking;
      2. it delivers the SAME body for that SAME physical game under the number
         it still holds. That is the identical-body case: ECHOED, once, and the
         echo carries the number the server accepts next. Nothing settles
         twice, and the seat did not re-key anything -- the key it sent is the
         one the server had named;
      3. the next physical game is a DIFFERENT body, so it is a new report. A
         seat that LATCHED the old number instead of deriving from the last
         advertisement keys it there and is refused -- and that refusal names
         the settled number and advertises the next one;
      4. THE TERMINAL DISPOSITION. The rule is asked what to do with that
         entry and answers `terminal`: it is DROPPED, the outbox shrinks by
         exactly that key, and it was delivered exactly once. No second
         submission of it is made under any number;
      5. the seat's NEXT physical game is keyed from the number that refusal
         advertised -- not from the number it was refused for -- and the
         endpoint SETTLES it. That is the one submission the seat's recovery
         costs;
      6. the same key delivered a second time settles nothing more. It meets
         the row it wrote and is echoed, so a redelivery can never become a
         second settlement of one physical game;
      7. the lobby ends holding one row per physical game at distinct numbers,
         and NO row for the dropped body -- checked by winner, because the
         dropped game's winner is a player no surviving row names. Its payload
         is on the quarantine record instead, with the reason the capture
         wrote.

    So the cost of having missed the update is exactly ONE refused submission,
    at step 3, and the seat files normally from there on. The r10 control is
    the absence steps 3 and 5 state together: an answer that advertised the
    number it had just settled would leave a derived key exactly where it was,
    so every later submission is refused for the same reason and the seat never
    files again. The r12 controls are the identity half: a keying that RE-KEYED
    a parked delivery -- filing it as a second entry rather than writing the
    number into the one it holds -- is what mints a second delivery for one
    physical game. The r13 control is the adoption: leave the advertised number
    out and the seat keys its next game where it was just refused. The r14
    control is the drop itself.

    THE DISPOSITION IS ASKED OF A RULE, NEVER WRITTEN INTO THE WALK. Round
    12's walk knew what each answer meant because the steps were written in
    the order the answers arrive, so the rule the contract states was nowhere
    a mutation could reach it. Each refusal below is handed to
    `_settled_game_disposition`, which returns the disposition and the number
    the seat's next key derives from; the walk does what it is told, AND IT
    IMPLEMENTS BOTH ANSWERS. The redirect branch is written out even though the
    rule never returns it, because a branch that does not exist makes the
    mutation that returns `redirect` red on a KeyError three legs away instead
    of on the assertion that names the fact (#391).

    THE KEY-SET CHECK IS MADE WHERE THE KEYING HAPPENS, and that is round
    12's correction to it. The comparison used to sit at the very end,
    against a hardcoded pair of names, and the mutation credited to it never
    reached it: a keying that pops the entry and re-files it is met by a
    KeyError on the very next lookup, three legs earlier, so the red came from
    an incidental crash rather than from the check the inventory named (#391).
    Now the set is read immediately after each keying step and compared with
    the set CAPTURED before it -- not with a literal, which is a second
    statement of the same thing -- and the walk stops there, so the assertion
    that names the defect is the assertion that reds. The additive shape is
    covered too: a keying that leaves the original entry reachable and adds
    a second key walks every leg without raising, and the same comparison sees
    it."""
    require_pg()

    async def go():
        engine, sm, pids, _mid = await _settling_fixture(
            games_played=2, recorded_number=1, recorded_room="rm_211531_r1")
        # EVERY LEG WRITES ITS OWN KEY INTO ONE RESULT, and the caller asserts
        # presence before it asserts a value. Round 12 returned an eight-value
        # tuple from six places with a comment on each early return telling
        # the next reader to keep the count -- a rule a reader has to remember,
        # standing beside the thing it describes, which is the shape three of
        # this ladder's findings are about. A mapping cannot be unpacked
        # short: a leg that did not run leaves its key absent, and the
        # assertion that names it says which leg stopped (#342).
        out = {}
        try:
            # The seat's outbox: ONE parked delivery per physical game, each
            # under the key it was frozen with at that game's over-edge.
            outbox = {
                "game-A": _park("game-A", "rm_211531", ROW_A, S3, S3),
                "game-B": _park("game-B", "rm_211531", ROW_B, S1, S1),
            }
            keys_before = sorted(outbox)
            out["keys_before"] = keys_before
            # The advertisement this seat holds, taken from a real answer
            # rather than assumed: a hardcoded number here would be a test of
            # arithmetic rather than of what the endpoint says (#342).
            ahead = None
            try:
                await _call_endpoint(sm, _endpoint_report(
                    ROW_A, S3, "rm_211531_r7", with_slots=True))
            except main.FfaReportRefusal as ex:
                ahead = ex
            if ahead is None:
                return out
            advertised = int(ahead.progress["expected_game"])
            out["advertised"] = advertised
            _recover_parked(outbox, "game-A", ahead)
            # THE KEY SET, READ WHERE THE KEYING HAPPENED. A keying that
            # re-keyed this entry is met by a KeyError on the next line, and
            # an assertion written to name the moved key never runs. So the
            # set is compared here and the walk stops with both sets in hand.
            out["keys_after_a"] = sorted(outbox)
            if out["keys_after_a"] != keys_before:
                return out
            # 1. another elector settles the parked game there; this seat sees
            #    nothing of it.
            await _settle_directly(sm, pids, ROW_A, advertised)
            # 2. the same body, under the number this seat still holds.
            out["echo"] = await _call_endpoint(
                sm, _delivery_of(outbox["game-A"]))
            # 3. the NEXT physical game, keyed at the latched number.
            outbox["game-B"]["advertised"] = advertised
            latched = None
            try:
                await _call_endpoint(sm, _delivery_of(outbox["game-B"]))
            except main.FfaReportRefusal as ex:
                latched = ex
            if latched is None:
                return out
            out["latched"] = latched
            # 4. THE DISPOSITION, asked of the rule rather than decided here,
            #    and BOTH answers implemented so that a mutation returning the
            #    other one is executed instead of crashing (#391).
            disposition, next_number = _settled_game_disposition(
                outbox["game-B"], latched)
            out["latched_disposition"] = disposition
            out["next_number"] = next_number
            if disposition == "redirect":
                entry = _recover_parked(outbox, "game-B", latched)
                try:
                    out["redirected"] = await _call_endpoint(
                        sm, _delivery_of(entry))
                except main.FfaReportRefusal as ex:
                    out["redirected_refusal"] = ex
            else:
                out["dropped"] = _drop_parked(outbox, "game-B")
            out["keys_after_drop"] = sorted(outbox)
            # 5. THE SEAT'S NEXT KEY, derived from the number that refusal
            #    advertised. The entry is parked holding the number the seat
            #    was LAST refused for, which is the state the r13 control
            #    restores by leaving the adoption out; taking up the
            #    advertisement is what moves it off that number.
            third = _park("game-C", "rm_211531", ROW_C, S2, S2)
            third["advertised"] = advertised
            outbox["game-C"] = third
            keys_with_c = sorted(outbox)
            out["keys_with_c"] = keys_with_c
            _recover_parked(outbox, "game-C", latched)
            out["keys_after_c"] = sorted(outbox)
            if out["keys_after_c"] != keys_with_c:
                return out
            # CAUGHT rather than allowed to escape: a next key that did not
            # take up the advertised number is refused here, and an exception
            # leaving this coroutine would red the test on a traceback three
            # legs from the assertion that names the fact (#391).
            try:
                out["accepted"] = await _call_endpoint(sm, _delivery_of(third))
            except main.FfaReportRefusal as ex:
                out["accepted_refusal"] = ex
                return out
            # 6. ...and the same key again, which must settle nothing more.
            out["again"] = await _call_endpoint(sm, _delivery_of(third))
            out["keys_final"] = sorted(outbox)
            async with sm() as db:
                rows = (await db.execute(text(
                    "SELECT game_number, winner_id FROM ffa_matches"
                    " WHERE lobby_id = :l ORDER BY game_number"),
                    {"l": LOBBY})).mappings().all()
                steam_of = {str(v): k for k, v in pids.items()}
                out["numbers"] = [int(r["game_number"]) for r in rows]
                out["winners"] = [steam_of.get(str(r["winner_id"]))
                                  for r in rows]
                # 7. WHAT THE SERVER KEPT. Sorted by room id rather than by
                #    insertion time: two captures written inside the same
                #    clock tick order arbitrarily, and an arbitrary order
                #    compared against a written-out list is a check that reds
                #    on the weather.
                out["captured"] = sorted(
                    (r["photon_room_id"], r["reason"], r["status"],
                     r["payload"].get("winner_steam_id"))
                    for r in (await db.execute(text(
                        "SELECT photon_room_id, reason, status, payload"
                        "  FROM match_report_quarantine WHERE mode = 'ffa'"
                    ))).mappings().all())
            return out
        finally:
            await engine.dispose()

    out = run(go())
    advertised = out.get("advertised")
    echo = out.get("echo")
    latched = out.get("latched")
    accepted = out.get("accepted")
    again = out.get("again")
    numbers = out.get("numbers", [])
    winners = out.get("winners", [])
    keys_before = out.get("keys_before", [])
    keys_with_c = out.get("keys_with_c", [])
    assert advertised is not None, (
        "the ahead tail was not refused, so no advertisement was ever made "
        "and nothing below this line was exercised")
    assert advertised == 3, advertised
    # THE KEY DID NOT MOVE, and this is asserted FIRST because every step
    # below is a step taken on the entries this set names. Compared with the
    # set captured before the keying rather than with a written-out pair: a
    # literal here is a second statement of the same set, and the two drift
    # (#432).
    assert out.get("keys_after_a") == keys_before, (
        out.get("keys_after_a"), keys_before)
    # 2. the identical body is ECHOED, and the echo advertises the next number
    #    -- an accepted answer re-aligns the seat exactly as a refusal does.
    assert echo is not None
    assert echo.message == "Already recorded"
    assert echo.settled_game == advertised
    assert echo.expected_game == advertised + 1, echo.expected_game
    assert echo.settled_game < echo.expected_game
    # 3. the latched key is refused, ONCE, and the refusal carries both
    #    numbers: which one is finished, and which one to use.
    assert latched is not None, (
        "a different physical game at the latched number was not refused")
    assert latched.status_code in (403, 409), latched.status_code
    assert latched.progress.get("settled_game") == advertised, latched.progress
    assert latched.progress["expected_game"] == advertised + 1, latched.progress
    # 4. THE DISPOSITION THE RULE RETURNS for that refusal is TERMINAL, and
    #    the number beside it is the one the seat's NEXT key derives from --
    #    not a number this entry will ever carry. The walk did not decide it;
    #    it asked, and every step below happened because the answer was this
    #    one.
    assert out.get("latched_disposition") == "terminal", (
        "the first settled-game refusal of an entry is the TERMINAL arm: the "
        "server cannot tell this delivery from a conflicting account of the "
        "game already settled at that number, so the entry is dropped")
    assert out.get("next_number") == advertised + 1, out.get("next_number")
    # ...and the entry left the outbox because the rule said so. The set is
    # compared with the one captured BEFORE the drop, so nothing else left
    # and nothing was minted beside it.
    dropped = out.get("dropped")
    assert dropped is not None and dropped["key"] == "game-B", dropped
    assert out.get("keys_after_drop") == sorted(
        set(keys_before) - {"game-B"}), (out.get("keys_after_drop"),
                                         keys_before)
    # ...and it was delivered exactly ONCE. A second submission of it, under
    # any number, is what the terminal arm forbids, and counting the
    # deliveries is how the walk says it made none.
    assert dropped["deliveries"] == 1, dropped["deliveries"]
    assert dropped["refusals"] == 1, dropped["refusals"]
    # 5. THE SEAT'S RECOVERY, not a claim about it: the next physical game,
    #    keyed from the advertised number, is ACCEPTED by the endpoint -- a
    #    match id, the number the server named, and the next one after it.
    assert out.get("keys_after_c") == keys_with_c, (
        out.get("keys_after_c"), keys_with_c)
    assert accepted is not None, (
        "the seat's next physical game was not accepted at the advertised "
        "number: %s"
        % (getattr(out.get("accepted_refusal"), "progress", None),))
    assert accepted.message == "FFA match recorded", accepted.message
    assert accepted.match_id is not None
    assert accepted.settled_game == advertised + 1, accepted.settled_game
    assert accepted.expected_game == advertised + 2, accepted.expected_game
    assert accepted.settled_game < accepted.expected_game
    # 6. ...EXACTLY once. The same key again meets the row it wrote.
    assert again is not None
    assert again.message == "Already recorded", again.message
    assert again.settled_game == advertised + 1, again.settled_game
    assert again.expected_game == advertised + 2, again.expected_game
    assert out.get("keys_final") == keys_with_c, (
        out.get("keys_final"), keys_with_c)
    # 7. One row per physical game, at distinct numbers: the pre-seeded 1, the
    #    game the other elector settled at 3, and this seat's next game at 4 --
    #    written by the ENDPOINT, from the parked body, not by this test.
    assert numbers == [1, advertised, advertised + 1], numbers
    # ...and the DROPPED body settled at NO number. Checked by winner, because
    # the number is what the walk is about and a row count cannot say WHICH
    # game is missing: ROW_B's winner is a player no surviving row names,
    # so a redirect that filed it anywhere at all shows up here.
    assert winners == [S3, S3, S2], winners
    assert S1 not in winners, (
        "the dropped body settled after all, which is the second settlement "
        "the terminal arm exists to prevent")
    # ...and it is not lost either: the server kept the whole payload before
    # it refused, which is what makes the drop a conservative disposition
    # rather than a destroyed game. Both refused deliveries of this walk are
    # on the record -- the ahead probe and the dropped entry.
    assert out.get("captured") == [
        ("rm_211531_r3", "ffa_game_contradiction", "pending", S1),
        ("rm_211531_r7", "ffa_game_number_mismatch", "pending", S3),
    ], out.get("captured")


def test_pg_a_conflicting_account_of_the_settled_game_is_dropped_and_kept():
    """Controls: terminal-arm-redirects-the-refused-entry (r14),
    refusal-keeps-nothing-for-review (r14).

    THE WITNESS THE ROUND-9 LENS ASKED FOR, and the reason the redirect was
    ruled out. The walk above frames its refused entry as a LATER physical
    game of a behind seat. This one frames the SAME delivery as what it can
    equally be: a second, DIFFERING account of the physical game another
    elector has already settled at that number. Two electors of one game
    compose the same key from the same advertisement, so the two framings
    reach the endpoint as the same bytes -- which is the whole point. No fact
    the server holds separates them, and a delay is under a client's own
    control, so nothing the client carries separates them either (#283,
    #378).

    So the disposition has to be the one that is safe for BOTH readings, and
    only one of them is. Dropping a later game costs that game's automatic
    settlement, and the payload is kept for an operator. Redirecting a
    conflicting account to the free number settles it as a physical game of
    its own: a second `ffa_matches` row for one sitting, a second rating
    change and a second payout, and nothing undoes those.

    WHAT THIS ASSERTS, and why each one is here:

      * the differing account is refused with `settled_game` naming the number
        the other elector settled -- the same answer the walk above gets;
      * the rule returns `terminal` and the entry is dropped, delivered once;
      * the lobby holds NO second settlement AT ANY NUMBER. The count is read
        over the whole lobby rather than at the settled number, because the
        defect this exists for puts the second row at a DIFFERENT number --
        asserting only at N would pass on exactly the failure;
      * the payload is on the quarantine record, under the reason the capture
        writes, so what the conservative disposition costs is recoverable by
        hand.

    The redirect branch is implemented rather than omitted, so the mutation
    that restores the round-9 rule is EXECUTED: it re-signs the dropped entry
    at the advertised number, the endpoint settles it, and the second row is
    what reds."""
    require_pg()

    async def go():
        engine, sm, pids, _mid = await _settling_fixture(
            games_played=2, recorded_number=1, recorded_room="rm_211531_r1")
        out = {}
        try:
            # This seat's own account of the physical game the lobby is on.
            # It differs from the other elector's in winner and in tallies,
            # which is what makes it a CONFLICT rather than a retry.
            outbox = {"game-X": _park("game-X", "rm_211531", ROW_B, S1, S1)}
            keys_before = sorted(outbox)
            out["keys_before"] = keys_before
            ahead = None
            try:
                await _call_endpoint(sm, _endpoint_report(
                    ROW_A, S3, "rm_211531_r7", with_slots=True))
            except main.FfaReportRefusal as ex:
                ahead = ex
            if ahead is None:
                return out
            advertised = int(ahead.progress["expected_game"])
            out["advertised"] = advertised
            # The OTHER elector's account of THAT SAME physical game settles
            # at the advertised number while this seat is not looking. Written
            # behind the endpoint because it is this walk's precondition and
            # not one of its steps -- what a real settlement does with the
            # slot is pinned by
            # test_pg_a_settlement_commits_the_catch_up_and_lands_on_the_free_number.
            await _settle_directly(sm, pids, ROW_A, advertised)
            # This seat keys ITS account of that same game from the same
            # advertisement, so the two compose the same room id.
            _recover_parked(outbox, "game-X", ahead)
            out["keys_after_keying"] = sorted(outbox)
            if out["keys_after_keying"] != keys_before:
                return out
            refusal = None
            try:
                await _call_endpoint(sm, _delivery_of(outbox["game-X"]))
            except main.FfaReportRefusal as ex:
                refusal = ex
            if refusal is None:
                return out
            out["refusal"] = refusal
            disposition, next_number = _settled_game_disposition(
                outbox["game-X"], refusal)
            out["disposition"] = disposition
            out["next_number"] = next_number
            if disposition == "redirect":
                entry = _recover_parked(outbox, "game-X", refusal)
                try:
                    out["redirected"] = await _call_endpoint(
                        sm, _delivery_of(entry))
                except main.FfaReportRefusal as ex:
                    out["redirected_refusal"] = ex
                out["entry"] = dict(entry)
            else:
                out["entry"] = _drop_parked(outbox, "game-X")
                out["dropped"] = True
            out["keys_after"] = sorted(outbox)
            async with sm() as db:
                rows = (await db.execute(text(
                    "SELECT game_number, winner_id FROM ffa_matches"
                    " WHERE lobby_id = :l ORDER BY game_number"),
                    {"l": LOBBY})).mappings().all()
                steam_of = {str(v): k for k, v in pids.items()}
                out["numbers"] = [int(r["game_number"]) for r in rows]
                out["winners"] = [steam_of.get(str(r["winner_id"]))
                                  for r in rows]
                out["captured"] = sorted(
                    (r["photon_room_id"], r["reason"], r["status"],
                     r["payload"].get("winner_steam_id"))
                    for r in (await db.execute(text(
                        "SELECT photon_room_id, reason, status, payload"
                        "  FROM match_report_quarantine WHERE mode = 'ffa'"
                    ))).mappings().all())
            return out
        finally:
            await engine.dispose()

    out = run(go())
    advertised = out.get("advertised")
    refusal = out.get("refusal")
    numbers = out.get("numbers", [])
    winners = out.get("winners", [])
    keys_before = out.get("keys_before", [])
    assert advertised is not None, (
        "the ahead tail was not refused, so no advertisement was ever made "
        "and nothing below this line was exercised")
    assert advertised == 3, advertised
    assert out.get("keys_after_keying") == keys_before, (
        out.get("keys_after_keying"), keys_before)
    # The conflicting account is refused, and the refusal names the number the
    # OTHER elector settled -- the same answer a later physical game gets,
    # which is the fact this walk exists to show.
    assert refusal is not None, (
        "a differing account of the settled game was not refused, so this "
        "walk never reached the arm it is about")
    assert refusal.status_code in (403, 409), refusal.status_code
    assert refusal.progress.get("settled_game") == advertised, refusal.progress
    assert refusal.progress["expected_game"] == advertised + 1, refusal.progress
    # THE HARM IS ASSERTED BEFORE THE BOOKKEEPING, and the order is the check
    # rather than a matter of taste. A redirect on this arm is not wrong
    # because a helper returned a different word; it is wrong because the
    # conflicting account SETTLES under its own number and rates and pays that
    # sitting a second time. The walk drives that whole path -- the redirect
    # branch above re-signs the entry and submits it to the endpoint -- so the
    # assertion that reads the lobby's rows has something real to fail on.
    # With `disposition` asserted first it never got the chance: the control
    # that makes the rule redirect reddened on the WORD, three legs before the
    # row, which is a check reporting the first symptom it reached instead of
    # the one it exists for (#391).
    #
    # NO SECOND SETTLEMENT, AT ANY NUMBER. Read over the whole lobby: a
    # redirect puts the second row at the FREE number, so a check made only at
    # the settled one passes on exactly the failure it is for.
    assert numbers == [1, advertised], numbers
    assert winners == [S3, S3], winners
    assert S1 not in winners, (
        "a second account of one physical game settled under its own number, "
        "which rates and pays that sitting twice")
    # ...and the refused payload is on the record, with the reason the capture
    # wrote, so an operator can read the two accounts side by side. The ahead
    # probe's capture is the second row: both refusals of this walk kept what
    # they refused.
    assert out.get("captured") == [
        ("rm_211531_r3", "ffa_game_contradiction", "pending", S1),
        ("rm_211531_r7", "ffa_game_number_mismatch", "pending", S3),
    ], out.get("captured")
    # ...and only THEN how the seat got there: the disposition the rule
    # returned, the number it named, and the entry leaving the outbox. These
    # are the walk's account of its own steps, and an account is checked after
    # the thing it is an account of.
    assert out.get("disposition") == "terminal", out.get("disposition")
    assert out.get("next_number") == advertised + 1, out.get("next_number")
    assert out.get("dropped") is True, (
        "the conflicting account was not dropped, so the outbox still holds a "
        "delivery the server has already refused")
    assert out.get("keys_after") == [], out.get("keys_after")
    entry = out.get("entry")
    assert entry is not None and entry["key"] == "game-X", entry
    assert entry["deliveries"] == 1, entry["deliveries"]


def test_pg_a_catch_up_on_a_refusing_path_logs_a_claim_its_transaction_can_keep(capsys):
    """Control: catch-up-log-claims-a-persisted-repair (r9).

    `_ffa_lock_lobby_slot` brings a counter that is behind its own rows up to
    them, and every refusal raised after a capture goes through it. On that path
    the UPDATE is never committed: the capture has already rolled this request's
    transaction back, `FfaReportRefusal` is answered by building a JSONResponse,
    and `get_db` closes the session, which rolls back with it. Round 8's log line
    said `games_played 1 -> 2 ... The sitting resumes at 3` -- an accomplished
    repair, in the past tense, on a path that discards it. The numbers were
    right and the claim was not, and an operator reading it concluded the
    counter had been fixed while the next report of that lobby re-derived and
    re-logged the same repair (#302, and #249 for a teardown that reports work
    the path does not do).

    THE ASSERTION ON THE WORDING IS NOT A GREP FOR A PHRASE. It sits beside the
    row itself: the lobby's `games_played` is read back AFTER the refusal has
    been answered and is required to be exactly where it started. That is the
    fact the sentence now states, so the two cannot drift apart -- if a later
    round makes this path commit, the row assertion fails first and the wording
    is corrected because it has become wrong, rather than the wording quietly
    outliving its subject."""
    require_pg()

    async def go():
        engine, sm, _pids, _mid = await _endpoint_fixture(
            games_played=1, recorded_number=2, recorded_room="rm_211531_r2")
        try:
            raised = None
            try:
                await _call_endpoint(sm, _endpoint_report(
                    ROW_A, S3, "rm_211531_r7", with_slots=True))
            except main.FfaReportRefusal as ex:
                raised = ex
            async with sm() as db:
                gp = (await db.execute(text(
                    "SELECT games_played FROM ffa_lobbies WHERE id = :l"),
                    {"l": LOBBY})).scalar()
            return raised, int(gp)
        finally:
            await engine.dispose()

    raised, gp = run(go())
    printed = capsys.readouterr().out
    assert raised is not None, "an ahead tail was not refused"
    assert raised.status_code == 409
    # The catch-up DID happen, as a derivation: the answer carries the counter
    # brought up to the rows, not the stored 1.
    assert raised.progress["games_played"] == 2, raised.progress
    assert raised.progress["expected_game"] == 3, raised.progress
    # ...and the row is exactly where it was. The statement ran and was
    # discarded, twice over on this path, which is what the line has to say.
    assert gp == 1, (
        "the catch-up persisted on a refusing path; the log line's condition "
        "is now the wrong way round and has to be re-derived")

    def claims_persistence(body):
        return "stands only if that request commits" in body

    def claims_a_completed_repair(body):
        return "games_played 1 -> 2" in body or "was behind its own rows" in body

    assert "counter is behind its own rows" in printed, printed[-800:]
    assert claims_persistence(printed), printed[-800:]
    assert not claims_a_completed_repair(printed), printed[-800:]
    # Both predicates exercised in BOTH directions on the same code path, so a
    # typo in either literal cannot make the two assertions above vacuous
    # (#391): a check that cannot fail is worse than no check (#342).
    assert claims_persistence(
        "correction is issued in this request's transaction and stands only if "
        "that request commits")
    assert not claims_persistence("the sitting resumes at 3")
    assert claims_a_completed_repair(
        "[FFA] lobby X counter was behind its own rows: games_played 1 -> 2")
    assert not claims_a_completed_repair(
        "[FFA] lobby X counter is behind its own rows: games_played 1, "
        "highest recorded game 2")


def test_the_evidence_log_negation_admits_only_produced_logs():
    """Controls: evidence-log-negation-admits-any-log (r12),
    producer-stops-naming-its-capture (r12),
    repin-names-a-capture-no-pattern-admits (r12),
    evidence-log-negation-takes-a-suffix-wildcard (r13).

    The r7 LOW on B12. `*.log` is ignored repository-wide and this directory's
    captures are re-included, because a report whose numbers come from a log
    nobody has is a number nobody can re-derive (#302). The re-inclusion was
    `!backend/tests/evidence/*.log`, which admits ANY file that lands here with
    that extension -- produced or not, and whatever it is called. A rule that
    cannot refuse anything is not a rule (#342), and what it costs is a file
    nothing in this tree writes being carried by the same line that carries the
    evidence.

    ROUND 13 TAKES THE WILDCARD OUT OF IT. Per-producer suffix patterns are
    narrower than `*.log` and still cannot refuse a name nobody produced: any
    file that lands here ending `-suite-run.log`, under any round or none, was
    re-included by the same line as the evidence and would ride an `add -A`
    in. A negation is a promise that this repository carries one file on
    purpose, so each line is now the WHOLE NAME of one capture of one round.
    The suffixes are still read off the instruments; what stops being a
    pattern is the name. The planted `zz-suite-run.log` below is the class
    that used to be admitted and now is not.

    So the negation is PER PRODUCER AND PER ROUND, and both halves of the
    pairing are derived rather than listed:

      * each producer under this directory NAMES the capture it writes, and
        the name is a value that producer produces. Seven of them are
        redirected into their capture by a caller and print its name in a
        `capture` header line of their own stdout; the eighth, repin-last.py,
        opens its own capture, so the name is read by LOADING that module and
        CALLING the function that decides it -- the same value it opens the
        file under, writes into that file's header, and checks against this
        block before writing anything;
      * `.gitignore` carries one pattern per producer.

    Compared in BOTH directions here. A pattern no producer names reds -- that
    is the blanket `*.log` coming back, and it is also a pattern left behind
    after its producer is deleted. A capture a producer names that no pattern
    admits reds too -- that is the round-11 shape, an instrument added with its
    log left unadmitted, which would have been a report naming a file the
    repository does not carry.

    And the refusal is exercised: names that no producer writes, including the
    two shapes a working directory is most likely to leave behind, are checked
    to stay IGNORED rather than merely assumed to be."""
    root = pathlib.Path(__file__).resolve().parent.parent.parent
    evidence = pathlib.Path(__file__).resolve().parent / "evidence"
    assert (root / ".gitignore").is_file(), root
    prefix = "!backend/tests/evidence/"
    patterns = [ln.strip()[len(prefix):]
                for ln in (root / ".gitignore").read_text(
                    encoding="utf-8").splitlines()
                if ln.strip().startswith(prefix)]
    assert patterns, "this directory re-includes no capture at all"
    assert "*.log" not in patterns, (
        "the blanket re-inclusion is back: any .log in this directory is "
        "admitted, produced or not")
    assert len(set(patterns)) == len(patterns), patterns
    # NOT A PATTERN AT ALL. A negation carrying a glob metacharacter admits a
    # set rather than a file, and every member of that set this tree does not
    # write is admitted for nothing. The round-12 block's suffix wildcards are
    # exactly that class one step narrower than `*.log`.
    for pat in patterns:
        assert not set(pat) & set("*?["), (
            "%s is a pattern rather than a name, so it admits captures no "
            "instrument here writes" % pat)
        assert re.match(r"^r\d+-\S+\.log$", pat), (
            "%s is re-included and is not <round>-<producer suffix>.log, so "
            "no producer and no round owns it" % pat)

    # THE PRODUCERS' OWN NAMES FOR THEIR CAPTURES, read off the instruments.
    #
    # THE DECLARATION HAS TO BEGIN ITS LINE, and that is not cosmetic. A
    # substring search finds a capture name anywhere it is MENTIONED, and one
    # file here mentions every other file's: the mutation runner carries the
    # producers' own lines as the anchors and mutants of the controls that
    # mutate them. Under a substring rule, deleting a producer's declaration
    # left the derived set unchanged -- because the control's own anchor still
    # said it -- and the mutation that proves this test works came back GREEN.
    # A mention is not a declaration, so the line must OPEN with it: bare, or
    # behind a comment marker, or inside the `echo "` / `print("` that prints
    # it. The runner's anchors sit inside a quoted Python string and are
    # excluded by exactly that.
    capture = re.compile(
        r"""^[ \t]*(?:\#[ \t]*|echo[ \t]+"[ \t]*|print\("[ \t]*)?"""
        r"""capture[ \t]+(?:<repo>/)?backend/tests/evidence/(\S+?\.log)""",
        re.MULTILINE)
    produced = {}
    for path in sorted(evidence.iterdir()):
        if path.suffix not in (".py", ".sh"):
            continue
        body = path.read_text(encoding="utf-8", errors="replace")
        for name in capture.findall(body):
            # The round part of the name is a variable in every producer --
            # `${TAG}`, `<round>`, `r%d`. What is compared is the SUFFIX, so
            # whatever stands before the first hyphen is normalised away.
            assert "-" in name, (path.name, name)
            produced.setdefault("rX" + name[name.index("-"):], set()).add(path.name)
    assert produced, "no instrument under this directory names its own capture"

    # THE PRODUCER THAT OPENS ITS OWN CAPTURE, read by calling it rather than
    # by reading the source around it. Round 12's first pass paired the
    # `*-repin-run.log` pattern with a COMMENT in that wrapper, which the
    # regex above admits by design. A comment is not what the tool writes: the
    # expression that opens the file could be changed with the comment left
    # where it was, both directions below would still pass, and the wrapper
    # would write a capture this repository cannot carry -- failing at the
    # `git add` that ends the round, after the run it records has been spent.
    # Loaded and CALLED, the pairing is against the value itself.
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "_scr_repin_last", str(evidence / "repin-last.py"))
    repin = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(repin)
    # Two sample rounds, because what the pattern matches is the SUFFIX: a
    # name whose round part is not the leading token would normalise to
    # something no pattern means, and that reds here rather than in a commit.
    one, two = repin.capture_name(0), repin.capture_name(9)
    assert "-" in one and one.endswith(".log"), one
    assert one[one.index("-"):] == two[two.index("-"):], (one, two)
    produced.setdefault("rX" + one[one.index("-"):], set()).add(
        "repin-last.py")

    # The SUFFIXES, which is the half the instruments own. The round part of
    # every declaration is a variable, so what an instrument decides is the
    # text from the first hyphen on.
    suffixes = {name[name.index("-"):]: writers
                for name, writers in produced.items()}

    # DIRECTION 1: every re-included NAME is one a producer here could have
    # written -- its suffix is some instrument's, and its round part is a
    # round. Nothing is a pattern, so nothing admits a set.
    for pat in sorted(patterns):
        tail = pat[pat.index("-"):]
        assert tail in suffixes, (
            "%s is re-included and no committed instrument writes a capture "
            "ending %s; the producers write %s"
            % (pat, tail, sorted(suffixes)))
    # DIRECTION 2a: every capture a producer names is admitted for some round,
    # so an instrument added with no line at all reds -- the round-11 shape.
    for tail, writers in sorted(suffixes.items()):
        assert any(p.endswith(tail) for p in patterns), (
            "captures ending %s are written by %s and no line re-includes "
            "one, so a fresh clone would not carry them"
            % (tail, sorted(writers)))
    # DIRECTION 2b: every capture this directory ALREADY carries is named
    # EXACTLY, so narrowing from a wildcard to a name orphaned nothing.
    on_disk = sorted(p.name for p in evidence.glob("*.log"))
    assert on_disk, "this directory carries no capture at all"
    for name in on_disk:
        assert name in patterns, (
            "%s is committed here and no line re-includes it by name" % name)

    # ...and the wrapper's OWN admission check, exercised in both directions
    # from here. It is what turns a capture this tree cannot carry into a
    # refusal before the run instead of a failed `git add` after it, and a
    # guard nothing ever runs is a guard nobody knows the polarity of. The
    # round is the one the wrapper itself derives -- the newest a report in
    # this directory carries -- because under exact names the answer is a
    # question about THIS round rather than about the shape of a name.
    rules_path = evidence / "evidence_rules.py"
    rules_spec = importlib.util.spec_from_file_location(
        "_scr_evidence_rules_for_negation", str(rules_path))
    ev_rules = importlib.util.module_from_spec(rules_spec)
    rules_spec.loader.exec_module(ev_rules)
    latest = ev_rules.newest_round(
        [p.name for p in evidence.iterdir() if p.name.endswith(".txt")])
    assert latest is not None, "this directory carries no numbered report"
    ignores = (root / ".gitignore").read_text(encoding="utf-8")
    assert repin.capture_is_admitted(repin.capture_name(latest), ignores), (
        "the wrapper would refuse to write the capture of the round this "
        "directory is on (r%d)" % latest)
    assert not repin.capture_is_admitted("r0-repin.log", ignores), (
        "the wrapper's admission check accepts a name no line re-includes")

    # THE REFUSAL, on names no producer writes. A check that only ever admits
    # is a check that cannot fail. The first two carry a PRODUCER'S SUFFIX and
    # are the class the round-12 wildcards admitted: a name shaped like a
    # capture, under a round nothing here has run.
    for outside in ("zz-suite-run.log", "zz-repin-run.log",
                    ".env.local.log", "id_rsa.log", "debug.log", "scratch.log",
                    "r12-notes.log", "suite.log", "api.log"):
        assert outside not in patterns, (
            "%s is admitted by the evidence negation" % outside)
        assert not repin.capture_is_admitted(outside, ignores), (
            "%s is admitted by the wrapper's own check" % outside)


def _inventory_entries():
    """{control name: the whole of its inventory entry, lines joined}.

    Parsed the way the tally check parses it -- an entry OPENS a line, its
    continuation lines are indented past it -- so the two cannot disagree
    about what an entry is."""
    doc = sys.modules[__name__].__doc__
    entries = {}
    current = None
    for line in doc.splitlines():
        head = re.match(r"^  ([a-z0-9-]+)( \((?:r\d+|retired)\))? +(\S.*)$",
                        line)
        if head:
            current = head.group(1)
            entries[current] = head.group(3)
        elif current is not None and line.startswith("    "):
            entries[current] = entries[current] + " " + line.strip()
        elif not line.strip():
            continue
        else:
            current = None
    return entries


def _inert_twin_kind(anchor, inert):
    """`comment` when the inert edit's only addition is a comment line.

    Read off the runner's own two strings rather than off a description of
    them, because the description is the thing under test."""
    before = [ln.strip() for ln in anchor.splitlines()]
    added = [ln.strip() for ln in inert.splitlines() if ln.strip() not in before]
    if added and all(ln.startswith("#") for ln in added):
        return "comment"
    return "not a comment"


def test_every_inert_twin_is_labelled_as_the_kind_the_runner_holds():
    """Control: inventory-mislabels-an-inert-twin (r13).

    The r8 lens LOW. `recovery-mints-a-second-parked-key`'s inventory entry
    said "Its inert twin is the same statement reflowed" and the runner holds
    a COMMENT at that site. The executed RED and GREEN were sound either way,
    so nothing in the run could notice: what was wrong is the sentence an
    auditor reads to decide WHICH twin was executed, and an auditor who went
    looking for a reflow at that site would not find one.

    That is the shape this ladder keeps closing -- a description standing
    beside the thing it describes with nothing comparing the two -- so it is
    closed the same way. The KIND is derived from the runner's own anchor and
    inert strings; the LABEL is read out of the entry; a control whose entry
    states a label has to state the kind the runner holds.

    Both directions on the derivation itself, because a classifier that
    answered `comment` for everything would pass the sweep above on a tree
    where every label said comment (#391)."""
    import importlib.util

    evidence = pathlib.Path(__file__).resolve().parent / "evidence"
    spec = importlib.util.spec_from_file_location(
        "_scr_mutation_runner_twins", str(evidence / "mutation-runner.py"))
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)

    # The classifier, both directions on fabricated pairs.
    assert _inert_twin_kind("x = 1\n", "# note\nx = 1\n") == "comment"
    assert _inert_twin_kind("x = 1\n", "x  = 1\n") == "not a comment"
    assert _inert_twin_kind("a\nb\n", "b\na\n") == "not a comment"

    entries = _inventory_entries()
    assert len(entries) >= 60, len(entries)

    labelled = 0
    for control in runner.CONTROLS:
        # (name, file, anchor, mutant, inert, test) -- the INERT is the fifth,
        # and reading the fourth would have compared the label with the
        # MUTATION, which is a different edit at the same site.
        name, anchor, inert = control[0], control[2], control[4]
        entry = entries.get(name)
        assert entry is not None, (
            "%s is a control the runner carries and this module's inventory "
            "does not name" % name)
        if "inert twin" not in entry:
            continue
        labelled += 1
        tail = entry.split("inert twin", 1)[1]
        sentence = tail.split(".", 1)[0]
        kind = _inert_twin_kind(anchor, inert)
        says_comment = "comment" in sentence
        assert says_comment == (kind == "comment"), (
            "%s: the inventory says %r and the runner holds %s"
            % (name, sentence.strip(), kind))
    # A check over an empty set passes for ever (#342), and this one names a
    # growing set, so the number of entries that state a label is asserted.
    assert labelled >= 10, labelled


def test_the_repin_trailer_is_derived_and_the_sweep_exempts_only_it():
    """Control: repin-types-its-commit-trailer (r13).

    The r8 lens LOW on R4-17. The re-pin wrapper writes both of its commit
    messages itself, and the attribution trailer in them was a constant in
    that file. Nothing compared the constant with the sitting that ran the
    wrapper, so a sitting that forgot to change it committed under the
    previous sitting's attribution and no check reddened -- and it had
    already gone stale once by the time the lens read it. Round 12 recorded
    that as a residual and named deriving it as the fix; this is the fix.

    THE TRAILER IS DERIVED FROM ONE SOURCE: the form the branch's most recent
    commits carry, read from `git log`. The wrapper types none, and it
    REFUSES when none can be derived -- an attribution nobody can derive is
    exactly the thing that used to be typed.

    THE SWEEP EXEMPTS EXACTLY THAT LINE AND NOTHING ELSE. A rule that exempted
    "anything beginning Co-Authored-By" would exempt the stale attribution it
    exists to catch, so the exemption is the whole derived line, compared
    whole. Everything else that claims an author -- a second trailer, a stale
    one, an address or a handle in prose -- is a refusal before any commit is
    made.

    Run in both directions on HARNESS COPIES: fabricated messages the real
    functions are called on, so what is proved is the rule rather than
    whatever this branch happens to hold. The live branch is then swept too,
    because a rule nobody has run against the real thing is a rule nobody has
    run."""
    import importlib.util

    evidence = pathlib.Path(__file__).resolve().parent / "evidence"
    spec = importlib.util.spec_from_file_location(
        "_scr_repin_trailer", str(evidence / "repin-last.py"))
    repin = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(repin)

    # NOTHING TYPED. The wrapper's own source carries no full attribution --
    # tested with the wrapper's own pattern, so the two cannot drift.
    source = (evidence / "repin-last.py").read_text(encoding="utf-8")
    typed = [ln.strip() for ln in source.splitlines()
             if repin.TRAILER_LINE.match(ln.strip())]
    assert not typed, (
        "repin-last.py carries a typed attribution: %r" % (typed,))

    # ── the harness, both directions ────────────────────────────────────
    good = "Co-Authored-By: A Reviewer <nobody@example.invalid>"
    stale = "Co-Authored-By: An Earlier Sitting <nobody@example.invalid>"
    body = "A subject line\n\nOne paragraph about what this commit does.\n"
    bodies = [body + "\n" + good + "\n"] * 3
    trailer, why = repin.derive_trailer(bodies)
    assert why is None and trailer == good, (trailer, why)

    # DERIVED -> GREEN. The message the wrapper would build carries exactly
    # the derived line and nothing else that claims an author.
    built = repin.commit_message("A subject\n\nSome prose.", trailer)
    assert built.rstrip("\n").endswith(good), built
    assert repin.foreign_attributions(built, trailer) == [], (
        repin.foreign_attributions(built, trailer))

    # A TYPED STALE TRAILER, PLANTED -> RED. This is the defect itself: the
    # message carries an attribution from an earlier sitting.
    planted = repin.commit_message("A subject\n\nSome prose.", stale)
    hits = repin.foreign_attributions(planted, trailer)
    assert [line for _n, line in hits] == [stale], hits
    # ...and a SECOND trailer beside the right one, which an exemption keyed
    # on the prefix rather than on the whole line would have let through.
    doubled = built.rstrip("\n") + "\n" + stale + "\n"
    assert [line for _n, line in repin.foreign_attributions(doubled, trailer)] \
        == [stale]
    # ...and an address in prose, which is not a trailer at all.
    prose = repin.commit_message(
        "A subject\n\nAsk <someone@example.invalid> about it.", trailer)
    assert repin.foreign_attributions(prose, trailer), prose

    # THE DERIVATION REFUSES rather than guessing. A newest commit with no
    # trailer, and a newest pair that disagree, are the two ways the branch
    # can fail to state a form.
    none_at_head = [body] + bodies
    got, why = repin.derive_trailer(none_at_head)
    assert got is None and why, (got, why)
    disagree = [body + "\n" + good + "\n", body + "\n" + stale + "\n"]
    got, why = repin.derive_trailer(disagree)
    assert got is None and why, (got, why)
    got, why = repin.derive_trailer([])
    assert got is None and why, (got, why)

    # ── THE LIVE BRANCH, swept at the tip it is at now ──────────────────
    root = pathlib.Path(__file__).resolve().parent.parent.parent
    shown = subprocess.run(["git", "log", "-n", "8", "--format=%B%x00"],
                           cwd=str(root), capture_output=True, text=True,
                           timeout=60)
    assert shown.returncode == 0, shown.stderr
    live_bodies = [b for b in shown.stdout.split("\0") if b.strip()]
    assert live_bodies, "git log printed no commit message"
    live, why = repin.derive_trailer(live_bodies)
    assert live is not None, (
        "this branch states no current attribution form, so the wrapper would "
        "refuse rather than type one: %s" % why)
    # The WINDOW is where the form changes, derived rather than counted. An
    # earlier sitting of this branch committed under a different attribution,
    # and that history is not a finding -- what the sweep is about is the tip
    # this round leaves.
    window = repin.tip_messages(live_bodies, live)
    assert window, "the derived form is carried by no commit, which cannot be"
    for number, text_of in enumerate(window):
        assert repin.foreign_attributions(text_of, live) == [], (
            "HEAD~%d carries an attribution that is not the branch's derived "
            "trailer: %r" % (number,
                             repin.foreign_attributions(text_of, live)))
    # ...and the window really is bounded by the trailer rather than by the
    # length of the log: a form no commit carries selects nothing.
    assert repin.tip_messages(live_bodies, stale) == []


def test_no_production_file_cites_the_gitignored_scratch():
    """Control: production-cites-a-gitignored-path (r8) and
    shipped-file-outside-the-swept-set (r9).

    Round 7 closed this for `backend/tests/evidence/` and left the shipped
    server outside the rule, so main.py went on sending the next reader to the
    rejoin lane's own brief under the gitignored scratch -- an authority nobody
    reading this repository can open (#302). The rule is not about that one
    line: a file we SHIP must not name a path this repository does not contain.
    The sweep behind this check removed the citation from SEVEN shipped files,
    on sixteen lines: main.py, pc_portrait.py, discord_bot.py and four
    migrations. Counted by the grep the sweep itself ran, not by memory.

    Scoped to the shipped server deliberately. A TEST may name the review
    document it pins -- this file does -- and the evidence directory has its own
    rule in test_the_committed_evidence_re_derives_its_own_numbers.

    ROUND 9 WIDENS THE SET, AND STOPS WRITING IT DOWN. Round 8 stated the rule
    over every file we SHIP and then read three hand-written globs -- api/*.py,
    discord_bot.py, sql/*.sql. `backend/Dockerfile.bot` is shipped by the same
    deploy (docs/deploy-reference.md maps it to the primary) and was outside all
    three, so the one surviving citation in the tree was the one file the check
    could not see, and the check passed on every run while it stood. A
    hand-written list of a set that GROWS under-covers it the moment someone
    adds a file, and the flag names a LINE where the defect is a CLASS (#432),
    so the set is now DERIVED from what the repository actually tracks:
    everything under `backend/` except the test tree. Dockerfiles, requirements
    and the compose file come in by construction, and so does anything added
    later."""
    root = pathlib.Path(__file__).resolve().parent.parent.parent
    listed = subprocess.run(["git", "ls-files", "backend/"], cwd=str(root),
                            capture_output=True, text=True, timeout=60)
    assert listed.returncode == 0, f"git ls-files failed: {listed.stderr!r}"
    files = [root / line for line in listed.stdout.splitlines()
             if line and not line.startswith("backend/tests/")]
    # A check over an empty set passes for ever (#342), so the set is asserted
    # before it is used -- by size, and by the four files the rule is anchored
    # on by name, one of which is the file round 8's set did not reach.
    assert len(files) >= 200, len(files)
    assert all(f.is_file() for f in files), [
        f.name for f in files if not f.is_file()]
    rel = {f.relative_to(root).as_posix() for f in files}
    assert {"backend/api/main.py", "backend/discord_bot.py",
            "backend/Dockerfile.bot",
            "backend/docker-compose.yml"} <= rel, sorted(rel)[:40]

    scratch = "ai-collab/"

    def offends(body):
        return scratch in body

    offenders = [f.relative_to(root).as_posix() for f in files
                 if offends(f.read_text(encoding="utf-8", errors="replace"))]
    assert not offenders, (
        f"a shipped file cites the gitignored scratch: {offenders} -- a comment "
        f"has to name an authority a reader of this repository can open")
    # The predicate is exercised in BOTH directions on the same code path, so a
    # typo in `scratch` cannot make the sweep above pass on everything (#391).
    assert offends("# Design: " + scratch + "rejoin/A1-BRIEF.md")
    assert not offends("# Schema: backend/sql/327_ffa_game_number.sql")


def test_every_round_eight_control_names_a_test_that_exists():
    """The same pairing for round 8. Two of these name a test this round did
    not write -- the point of those two is that a mutation nobody had ever RUN
    is now run against the test that was already there."""
    mod = sys.modules[__name__]
    for name in ("test_the_lock_the_derivation_and_the_increment_are_one_transaction",
                 "test_pg_two_reports_for_one_lobby_cannot_settle_the_same_number",
                 "test_pg_a_refusal_raised_after_a_capture_reads_the_lobby_again",
                 "test_pg_a_realigned_resubmission_is_echoed_and_never_settled_twice",
                 "test_no_production_file_cites_the_gitignored_scratch",
                 "test_the_committed_evidence_re_derives_its_own_numbers",
                 "test_every_mutation_control_the_runner_carries_is_named_and_paired",
                 "test_pg_the_relock_retries_once_and_answers_from_the_lobby_not_the_snapshot"):
        assert callable(getattr(mod, name, None)), name


def test_every_mutation_control_the_runner_carries_is_named_and_paired():
    """Control: control-list-drifts-from-the-inventory (r8).

    The pairing tests above are hand-written lists, and a hand-written list
    of a set that GROWS under-covers the moment someone forgets to extend
    it. Round 8 proved that on itself: it added a twenty-first control and
    every existing check stayed green without it. The tally check has the
    same shape from the other side -- it reads the docstring's claimed
    numbers against the docstring's own list -- so a control living in the
    RUNNER and in neither list was invisible to both at once.

    This derives the set instead of restating it. It loads the committed
    runner and, for every control it carries, requires two things: this
    module's docstring inventory NAMES it, and the test it names EXISTS.
    Adding a control without listing it, or naming a test that has since
    been renamed, reds here rather than passing quietly (#342).

    Round 9 added three controls and did NOT add a fourth hand-written
    list beside them. That is what deriving the set buys: the lists above
    are the ones that already existed, this check covers whatever the
    runner carries today, and a round that adds a control extends the
    module inventory and nothing else.
    """
    import importlib.util

    evidence = pathlib.Path(__file__).resolve().parent / "evidence"
    runner_path = evidence / "mutation-runner.py"
    assert runner_path.is_file(), runner_path
    spec = importlib.util.spec_from_file_location(
        "_scr_mutation_runner", runner_path)
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)

    controls = list(runner.CONTROLS)
    assert len(controls) >= 22, len(controls)

    # The SAME parse the tally check uses, so the two cannot disagree
    # about what counts as an inventory entry.
    doc = sys.modules[__name__].__doc__
    listed = set()
    for line in doc.splitlines():
        m = re.match(r"^  ([a-z0-9-]+)( \((?:r3|r4|retired)\))? +\S", line)
        if m:
            listed.add(m.group(1))
    assert len(listed) >= 60, len(listed)

    backend = pathlib.Path(__file__).resolve().parent.parent
    for control in controls:
        name, test = control[0], control[5]
        assert name in listed, (
            f"{name} is a control the runner carries and this module's "
            f"docstring inventory does not name")
        rel_path, func = runner.split_test(test)
        target = backend / rel_path
        assert target.is_file(), (name, rel_path)
        body = target.read_text(encoding="utf-8", errors="replace")
        assert f"def {func}(" in body, (
            f"{name} names {func}, which does not exist in {rel_path}")

    # Both directions, or the two sweeps above pass on a parse that
    # accidentally swallowed the whole docstring.
    assert "definitely-not-a-control" not in listed
    assert "relock-gives-up-after-one-attempt" in listed
    assert "evidence-result-pattern-forgets-the-repin" in listed


def test_pg_the_relock_retries_once_and_answers_from_the_lobby_not_the_snapshot():
    """Control: relock-gives-up-after-one-attempt (r8).

    The r5 gate's other B3 clause: a re-read that failed once answered with the
    caller's pre-rollback copy. That copy is stale-LOW -- safe, in that a client
    acting on it is refused rather than misled, and expensive, in that the
    refusal costs one more game of the sitting before it realigns.

    Under asyncpg one failed statement poisons the whole transaction (#235), so
    the likeliest reason the first attempt failed is a statement that the
    handler's own rollback has just cleared. This drives exactly that state on a
    real server: a statement is failed on purpose, the transaction is left
    aborted, and `_ffa_progress_relocked` is called with a fallback that is
    deliberately nothing like the truth. The answer has to be the LOBBY's."""
    require_pg()

    async def go():
        engine, sm, _pids, _mid = await _endpoint_fixture(
            games_played=4, recorded_number=1, recorded_room="rm_211531_r1")
        try:
            async with sm() as db:
                # Poison it the way a real failure does. Nothing else in this
                # transaction can run until it is ended.
                poisoned = False
                try:
                    await db.execute(text("SELECT no_such_column_anywhere"))
                except Exception:
                    poisoned = True
                # Prove the transaction really is unusable, or the retry is
                # being credited for a state that never existed (#342).
                still_broken = False
                try:
                    await db.execute(text("SELECT 1"))
                except Exception:
                    still_broken = True
                answer = await main._ffa_progress_relocked(db, LOBBY)
            return poisoned, still_broken, answer
        finally:
            await engine.dispose()

    poisoned, still_broken, answer = run(go())
    assert poisoned, "the statement that was supposed to fail did not"
    assert still_broken, (
        "the transaction was not left aborted, so this test never posed the "
        "question it exists to pose")
    assert answer == {"games_played": 4, "expected_game": 5}, (
        "the re-read gave up after one attempt instead of asking again on the "
        "session its own rollback had just cleared")


def test_pg_an_exhausted_progress_read_answers_503_with_no_progress_fields():
    """Controls: double-failure-invents-a-progress and
    vanished-lobby-invents-a-progress (r10).

    The test above proves the SECOND attempt is made. This one is about what
    happens when there is no third: both attempts failed, or the lobby has no
    row to derive anything from. Until round 10 both answered from the
    caller's pre-rollback copy.

    Both arms are driven for real, with nothing patched. The first passes a
    lobby identifier the server itself refuses to read, so the retry over the
    cleared session fails for the same reason the first attempt did -- which
    is the exhausted case as a live server produces it, not a stubbed one. The
    second deletes the lobby row, which is the other reachable shape of
    "nothing to read".

    What both must answer is a 503 -- a status this client's outbox retries
    rather than spends -- with NO progress fields anywhere in the body. The
    fields are what a resynchronising seat derives its next key from, and a
    number this path did not read under the lock is a number that can send it
    back into the refusal it is trying to leave (#430). `detail` names which
    of the two happened, because a reason nobody can tell apart is a reason
    nobody can act on."""
    require_pg()

    async def go():
        engine, sm, _pids, _mid = await _endpoint_fixture(
            games_played=4, recorded_number=1, recorded_room="rm_211531_r1")
        try:
            # ARM 1 -- both attempts fail. The identifier is one the server
            # refuses to read at all, so the second attempt over a cleared
            # session fails exactly as the first did.
            async with sm() as db:
                arm1 = None
                try:
                    arm1 = await main._ffa_progress_relocked(
                        db, "not-a-lobby-identifier")
                except Exception as ex:
                    arm1 = ex
            # ARM 2 -- the lobby row is gone. Its matches go first: the
            # question is about a lobby with nothing to derive from, and a
            # constraint failure would be a different one.
            async with sm() as db:
                await db.execute(text(
                    "DELETE FROM ffa_matches WHERE lobby_id = :l"), {"l": LOBBY})
                await db.execute(text(
                    "DELETE FROM ffa_lobbies WHERE id = :l"), {"l": LOBBY})
                await db.commit()
            async with sm() as db:
                gone = int((await db.execute(text(
                    "SELECT COUNT(*) FROM ffa_lobbies WHERE id = :l"),
                    {"l": LOBBY})).scalar())
                arm2 = None
                try:
                    arm2 = await main._ffa_progress_relocked(db, LOBBY)
                except Exception as ex:
                    arm2 = ex
            return arm1, arm2, gone
        finally:
            await engine.dispose()

    arm1, arm2, gone = run(go())
    assert gone == 0, (
        "the lobby row was still there, so arm 2 never posed its question")
    for name, ex in (("both attempts failed", arm1), ("the lobby is gone", arm2)):
        assert isinstance(ex, main.FfaReportRefusal), (
            f"{name}: the exhausted read answered with {ex!r} instead of "
            f"refusing")
        assert ex.status_code == 503, (name, ex.status_code)
        assert ex.progress == {}, (name, ex.progress)
        assert "retry this report unchanged" in ex.detail, (name, ex.detail)
    # Two reasons, not one string doing both jobs.
    assert arm1.detail != arm2.detail, arm1.detail
    # ...and the body really carries nothing else, so neither answer can be
    # read as advertising a number.
    handler = main.app.exception_handlers[main.FfaReportRefusal]
    for name, ex in (("both attempts failed", arm1), ("the lobby is gone", arm2)):
        body = json.loads(bytes(asyncio.run(handler(None, ex)).body))
        assert set(body) == {"detail"}, (name, body)
