# Sid's Competitive Rounds — Completed-work archive

Prior sessions' "Completed This Session" entries. Newest dated heading on top. See `docs/CHANGELOG.md` for the version-oriented record; this file is organized by when the work was done, not by what version carried it.

## Archived 2026-07-29 (from TODO.md — previous session status, superseded)

## 🟢 v1.34.4 — SHIPPED 2026-07-26 ✅ (GitHub release + cosmetics.zip; backend + bot live; migration 150 applied; **HTTPS now live**)

Release: https://github.com/SidNDeed/SidsCompetitiveRounds/releases/tag/v1.34.4 (tag `v1.34.4`, commits `5d9f40f` + `95034c2`). Pre-release snapshot `cc_pre-release-1-34-4__20260726_010220`. Sid named the version (patch bump, per his standing preference).

### What went live
- **1v2 Solo Extra Pick crash FIXED** (bugs #85/#86). Root cause is vanilla: `CardChoice.DoPlayerSelect` sets `pickrID = -1` the instant a card is picked, then `SpawnUniqueCard` does `players[pickrID]` on the NEXT deal and throws `ArgumentOutOfRangeException` — the guard `if (pickrID != -1)` sits four lines BELOW the deref. Only our extra pick ever leaves `picks > 0` there, so it was the first thing in ROUNDS history to hit it. Fix = `ReplaceCards` prefix restoring `pickrID`, scoped to `ActivePickerId >= 0 && picks > 0`. Also makes the 2nd card selectable at all (`Update` only calls `DoPlayerSelect` when `pickrID != -1`). Learning #195. **My first diagnosis (PlayerID/list-index ordering) was WRONG and was reverted — Codex refuted it. The exception text said "must be NON-NEGATIVE"; that was the whole answer and I read past it.**
- **HTTPS client migration.** `https://competitive-rounds.duckdns.org:8444`. One-shot config migration (gated on a new `HttpsMigrationDone` flag) rewrites ONLY the exact legacy default and leaves LAN/custom values alone. Session-scoped fallback to plain 8443 on `ConnectionError` or an unusable response — never persisted, re-probes every launch. `ChatClient.Retarget` added; the ws URL is now re-derived per reconnect instead of once at loop entry. **CONFIRMED WORKING IN THE FIELD** — two third-party IPs on 8444 (`88.97.177.121`, `101.177.182.214`) as of 2026-07-26 ~13:00.
- **Crown + Dark Aura approved placements** (bug #84). Crown scale 1.1→1.6, offset (0,0.55)→(-0.028,4.499); Dark Aura 1.45→2.25, (0,0.05)→(0.032,1.17). **Both are big jumps — eyeball them in-game.** Migration 150 advances `published_placement_revision` explicitly, because the 148 trigger only fires when `catalog_ready` FLIPS and these were already released — they'd have stayed "pending release" forever and fallen out of every future ship (learning #183 family).

### Server-side, live before the release
- **Unauthenticated SQL injection CLOSED.** `/api/v1/cards` `sort_by` was interpolated into `ORDER BY`; FastAPI's `Query(enum=[...])` validates NOTHING (learning #188). Proven live: `sort_by=zzz_not_a_column` → 500 straight from Postgres. Now an allowlist (`_CARD_SORT_MAP`) with silent fallback. Swept every other `text(f"...")` in main.py / tournaments.py / tournament_bracket.py / flag_evidence.py — this was the ONLY injectable one.
- **Two internal endpoints key-gated.** The bug-report comment endpoints trusted `client_host.startswith("172.")` — all of 172/8, mostly public space — and would have become world-writable the moment a proxy existed. Now `_require_internal_key`, fails closed.
- **nginx TLS front-end** on 8444, `docker-compose.tls.yml` + `nginx/app.conf` on the LXC. Let's Encrypt cert valid to **2026-10-24**, acme.sh auto-renew **2026-09-23** with a hot-reload hook. uvicorn runs `--proxy-headers --forwarded-allow-ips 172.30.0.10`; verified real client IPs survive the proxy (uvicorn logs `<real-ip>:0`, where port 0 means the address came from `X-Forwarded-For`).
- `cc-deploy-wrapper.sh` **2026-07-26.6** installed: scp branch RESTORED (I had broken it — see below), colon-verb dispatch fixed (the `case` matched `$VERB`, which strips everything from the first colon, so `logs:` / `migrate:` / `sql-readonly:` could NEVER match — the repo copy had never been a working wrapper), `health` now curls :8443 not :8000, new read-only `backup-status` verb, new `wrapper-version` verb for drift detection.
- `pg-backup.sh` hardened (temp file → verify → atomic mv → rotate). It had been exiting non-zero after every SUCCESSFUL backup: `HEAD=$(gzip -dc "$OUT" | head -5)` under `pipefail` takes SIGPIPE. **Proxmox vzdump was always healthy** (daily 04:00, 13 retained, ~2.9 GB each), so no data was ever at risk — I overstated that at one point and corrected it.

---

## 🔴 PICK UP HERE — actions that need Sid

0. **COMMIT THE LOCK-PROTOCOL WORK** — worktree `claude/heuristic-matsumoto-de7bbf` (`.claude/worktrees/heuristic-matsumoto-de7bbf`), based on `main` @ `b01acf2`. `backend/api/main.py` +255/−31 and `docs/CHANGELOG.md`. Reviewed to death (5 adversarial rounds / 37 agents, plus a cold Codex pass) and left uncommitted **on purpose** — Sid asked for one session to commit it all at once. Backend-only: **no migration, no client change, no version bump**, so it can ride with whatever ships next or deploy on its own. Write-up at the top of `docs/HANDOFF.md`; learnings #202–#206. ⚠ A SECOND worktree exists (`amazing-euclid-0e152d` @ `b102b8f`) — check it before assuming the tree is clean.
1. **Re-scp the snapshot wrapper.** First attempt failed on a CRLF shebang (learning #196); fixed locally, now pure LF.
   ```
   scp scripts/cc-snapshot-wrapper.sh root@192.168.72.219:/usr/local/bin/
   ssh root@192.168.72.219 "chmod 755 /usr/local/bin/cc-snapshot-wrapper.sh"
   ssh ccsnap@192.168.72.219 prune-snapshots:dry-run
   ```
   Then `prune-snapshots:apply` **about 8 times** until the summary reports `kept=10`. **81 snapshots exist**, dating back to 2026-04-18 — pruning never ran once, because the awk pattern required the arrow and name to be adjacent and anchored at line start, while `pct listsnapshot` emits an indented tree with a space; and `sort -r` sorted by label instead of the trailing timestamp. Chain depth this deep costs disk, degrades copy-on-write performance, and makes rollback a trap.
2. **Upload the Thunderstore bundle** — built and verified at `thunderstore/SidsCompetitiveRounds-1.34.4.zip` (20.5 MB, 128 entries; gate confirmed by byte-scan — the TS build contains "update through your mod manager" and NOT "Downloading update", Release is the inverse). Manual submit at https://thunderstore.io. **Do this before any MIN_MOD_VERSION raise.**
3. **Playtest the 1v2 extra-pick fix** with Solo Extra Pick ON (Stan and NotNic both asked; both tickets are commented). Also run plain 1v2 with it OFF to check for regression.
4. **Someone must click Leave in the 1v2 tab** to dissolve the stale lobby lock from 07:05 (Stan / NotNic / TechTara). Re-queueing just re-enters the husk. 1v2 locks dissolve ONLY on an explicit leave — there is no timeout. That design gap is still open.
5. **A/B the stutter** — play a session with **Despawn Offscreen Bullets OFF**. See the FPS section below.
6. Discord pinned message + #releases announcement.

---

## 🟡 UNCOMMITTED / PARKED (nothing lost, nothing shipped)

- **🔴 `backend/api/main.py` — the 1v1+2v2 LOCK PROTOCOL (worktree `heuristic-matsumoto-de7bbf`).** See item 0 above. Establishes one acquisition order per ladder — 2v2 `team_series FOR UPDATE` → `players` sorted `str(pid)` **`FOR NO KEY UPDATE`** → `glicko_ratings_2v2` sorted; 1v1 `players` sorted → `ranked_series` → `glicko_ratings` (series-first is impossible in 1v1 — the report carries no series id, learning #206). Closes the deferred Codex finding 5 plus, unexpectedly, two unfiled races: `submit_match` advanced `p*_series_wins` read-modify-write with **no series lock at all**, and its post-commit glicko block did an unlocked rating read-modify-write. Also closes an unguarded double-reversal in `admin_reverse_series`. **The two designs I got wrong before review caught them are learnings #202 (`FOR UPDATE` vs FK `FOR KEY SHARE`) and #203/#204** — read those before touching any of this.
- **`plugin/NativeUI.cs`** — Codex's font-fallback fix. Reviewed, builds clean, **NOT shipped**. The loop did `break` after the first *installed* face whether or not it worked, so when Segoe UI / YaHei / Yu Gothic / Malgun all failed to load, Arial, Tahoma, SimHei, Meiryo and Gulim were never tried → `[FONT] no OS fallback fonts available` → ~3,800 missing-glyph warnings per session and squares in foreign names. Now breaks only on success, and logs which faces it tried. **Ready to ship in the next release.**
- **✅ LANDED (2026-07-26, commit `b01acf2` "queue-lock hardening") — `ai-collab/parked/queue-lock-hardening-1v1-and-2v2.patch`.** Verified in the tree: `_lock_queue_rows_ordered` + `_lock_queue_group_for_player` are present and used by poll/ready/decline/leave/team/ovt. The patch file and this entry are kept for the reasoning below (it explains WHY the shape is what it is, and learning #197 generalises it). Historical description follows — it contained BOTH:
  - **The proven 1v1 deadlock fix (WANTED).** Postgres logged ABBA twice, 07:02:27 and 07:02:28, on `ranked_queue`: `queue_poll` and `queue_ready` both locked caller-then-opponent, so two simultaneous pollers took the same two rows in opposite order. Fix = `_lock_queue_rows_ordered` (one `FOR UPDATE` per row, ascending player_id — deliberately NOT `ANY(...) ORDER BY ... FOR UPDATE`, which relies on the planner putting LockRows above Sort) + unlocked discovery read + authoritative re-read + bounded retry + 503 on exhaustion. `/queue/decline` also ordered (it wrote the pair in request order). **Codex verified this CONFIRMED after refuting my first attempt** — my original re-pair guard returned HTTP 200, and `PostRequestWithRetry` treats 200 as success and stops, `ReadyUp` early-returns unless state is `Matched`, and the `matched` poll branch only transitions from `Searching`. The player would have been stuck in `ReadySent` until the match timed out: worse than the deadlock.
  - **Codex's Task-2 scope creep (HELD BACK).** 379 insertions across 38 regions, reaching into `delete_player_data`, `_complete_team_series_with_ratings`, `admin_resolve_team_series`, both janitor loops, and the team/ovt grouped-lock paths. None of those appear in the observed deadlock, and Codex itself later labelled most of it "theoretical hardening, not demonstrated". **Split it: land the 1v1 half after a line-by-line review, then treat the rest as its own pass with an adversarial check by someone OTHER than Codex** (it wrote the code, so it cannot verify it).

---

## 🔴 NEW findings Codex had NOT called out (Sid asked it directly — good instinct)

- **HIGH · `delete_player_data` does not delete 2v2 / 1v2 queue rows.** The endpoint promises to remove "queue entries" (main.py:9464) but only clears `ranked_queue` (main.py:9490). `team_queue` (models.py:719-724) and `ovt_queue` (sql/120_1v2_schema.sql:44-47) store COPIED raw `steam_id` and `display_name`, and because the player row is anonymised rather than deleted, `ON DELETE CASCADE` never fires. A player who deletes their data while queued keeps their identity in those tables. **A privacy commitment not being met, unrelated to the lock work, and it would have been thrown away with the parked patch.** Related: `steam_sessions` (models.py:465) also stores the raw Steam ID and isn't cleared.
- **MEDIUM · janitor "never matched" deletes don't filter on status** (main.py:575-579 team, 613-616 ranked). The comment says "never matched"; the query deletes any row older than 30 minutes. The comment/query mismatch is definite; the player-visible consequence is unproven.
- **MEDIUM · team janitor threshold mismatch** — queue-row delete at 30 s stale (main.py:567-572) vs series-cancel detection at 60 s (545-554), so a row can be deleted while its active series is still uncancelled.
- **✅ MOSTLY CLOSED · broad `except` around transactional writes with no savepoints.** The 2v2 settle blocks got `begin_nested` in `b01acf2` (learning #187), and the **1v1** `_settle_series_bets` call got the same treatment in the uncommitted lock-protocol work — so all three settle sites are now savepoint-isolated and a settle failure genuinely cannot take the match write with it. Sweep the remaining broad `except` blocks in main.py for the same shape when convenient; the settle sites were the ones with a known trigger.
- **🔴 NEW · a failed bet settle now strands the bets FOREVER — no retry path exists.** Direct consequence of the savepoint fix above (correct trade, but it has a tail). Verified in the uncommitted work: `_settle_series_bets` has exactly one call site (the completed transition); a duplicate report exits via the idempotent `IntegrityError` branch without re-settling; and `_prune_stale_series`' refund arm requires `status='active'`, which a completed series fails. So bets stay `settled_at IS NULL` with stakes already charged. **Fix: a janitor arm that finds `settled_at IS NULL` bets on completed/cancelled series older than ~10 min and settles (completed) or refunds (cancelled), covering BOTH `bets` and `team_bets`, each settlement in its own small transaction so one failure can't wedge the sweep.**
- **✅ FIXED in `b01acf2` · `_complete_team_series_with_ratings` docstring claimed XP but awards none.** Resolved the other way — the docstring was wrong, not the body. It now states the no-XP behaviour and why (match XP is a per-GAME payout; a forfeit ends the series without another game to pay for).
- **✅ FIXED in `b01acf2` · malformed team series with a null participant skipped queue cleanup.** The defensive early return now takes the ordered queue locks and DELETEs the rows, so it can no longer leave players unable to re-queue until the janitor.
- **LOW/MED perf · ovt candidate selection locks the ENTIRE searching pool** (13214-13222, no `LIMIT 3`; only `rows[:3]` are used), so a second independent trio cannot form concurrently.

---

## 🔴 Codex cold review of the lock-protocol diff (2026-07-26) — PRE-EXISTING items left OPEN

Codex reviewed the uncommitted lock-protocol diff at Ultra and returned 9 confirmed + 1 plausible. **Four were about my new code and are FIXED in that same diff** (the 1v1 create-race TOCTOU — a recount can't prove absence for a later statement, now a `pg_advisory_xact_lock` on sorted steam_ids; the post-commit rating pass applying a forward Glicko period + slayer title + bracket advance to a series an admin reversed in the gap, now an authoritative re-read; the rebuild's per-player guard missing OPPONENT-history changes, now a global generation check; and a player whose only series was reversed being skipped forever, now fixed by seeding the universe from existing rating rows too). Transcript + task file: `ai-collab/codex-review-lock-protocol-transcript.txt`, `ai-collab/codex-task-lock-protocol.md`. The rest are pre-existing, out of that diff's scope, and listed here:

- **🔴 HIGH · free payout: prune-refund vs settle double-credit.** `_prune_stale_series` refunds stakes on an ACTIVE stalled series while a deciding report settles the same bet; both load the same row through stale ORM state and both commit, so the bettor banks **refund + winnings**. Fix: claim bets atomically — `UPDATE bets SET … WHERE id = :id AND settled_at IS NULL RETURNING id` — and treat "no row returned" as already handled. Same shape applies to `team_bets`. (main.py ~6958 settle, ~7665 refund.)
- **🔴 HIGH · a bet can be placed on an already-completed series and is then never settled.** Placement reads the series as active, the deciding report completes and settles, then placement charges gold and inserts. No authoritative status re-check under a lock. Stake charged, never paid or refunded. (main.py ~8210.)
- **🔴 HIGH · a failed bet settle strands the bets FOREVER** — see the entry above in the previous findings block; the janitor sweep is the fix and it should be built together with the two items above, since all three are "bet lifecycle has no reconciliation".
- **🟠 MEDIUM/HIGH · other multi-player writers still bypass the canonical player order.** The lock protocol now holds for the result-writing paths, but three writers take player rows in their own order and can still form ABBA against them: **preflight** (concurrent `(A,B)` and `(B,A)` autoflush their first player in opposite order, then `_mark_mod_seen` flushes the other, main.py ~8018); **shop purchase royalty** (locks the buyer, then dirties the artist for their cut, ~7231); **privacy deletion** (holds/deletes a `team_queue` row before its late `Player` update, ~10123 — should be series → players → queue with a re-read). Real fix is factoring the canonical pass into a helper every multi-player writer calls — ideally into `get_or_create_player` itself, which would also close the advisory-lock residual noted in `submit_match` (a non-report path can still create a players row mid-flight because it doesn't take that advisory lock).
- **🟠 MEDIUM · `/glicko/recalculate` is a competing rating writer** (main.py ~4611). Loads a player's ORM rating + match set, and if a live series commits a Glicko update before it flushes, its stale object overwrites the live result; its multi-row order is unspecified and can invert against other rating writers. Either retire it (the inline path plus the 2v2 rebuild may already cover every use) or make it take the player gate with a post-lock re-read and short ordered transactions.
- **⚪ PLAUSIBLE · lock convoy on the hot 1v1 endpoint.** `submit_match` now holds both player rows for the whole transaction (match/card inserts, anti-cheat, rewards, achievements, series work, settlement) and there is **no `lock_timeout`/`statement_timeout` set anywhere** (`backend/api/database.py`), so waiters queue indefinitely and hold a pool connection while doing it — 30 connections total. Cheap mitigations: set a modest `lock_timeout` on the pool so a wedged waiter fails fast and the client retries, and cap the per-report card/telemetry collection sizes.
- **⚪ Documented trade, no action planned:** the 2v2 rebuild commits per player, so a reader (`place_team_bet` storing durable odds) can observe a mixed rating generation mid-run. The alternative is the single wide transaction that deadlocks live reports. It is an admin repair tool — run it when nobody is playing. Noted in its docstring.

---


---

## 2026-04-28 — 2v2 polish marathon (v1.25.18 → v1.25.23)

- **v1.25.18** Decoupled Random vs Custom-Lobby 2v2 queues (migration 064 `team_queue.queue_type`); F5 Search Random / Find Custom Lobby; queue beacon filtered to auto.
- **v1.25.19** Queue auto-refresh (`MaybeRefreshTeamTab`); `FindMatchingBrace` for `{}` (cards parser bailing); series-preflight gated `!inCrFf`; migration 065 cancelled 3 phantom 1v1 rows; `[POPUP-DIAG]` logging.
- **v1.25.20** `CardPickBodyTinter` coroutine from `CardChoiceVisuals.Show` Postfix.
- **v1.25.21** 2v2 economy (migration 066); matchmaker trusts 2v2 elo when RD≤110; `/team/all-series-paged`; leaderboard columns+sort; FacePublisher republish; toggle-off skin re-bake.
- **v1.25.22** 2v2 tab ScrollView; click-to-sort; Avg Mate Elo; stacked card columns; mid-series rebalance backend (`AUTO_BALANCE_SWAP_MARGIN`, `rebalance_assignments`).
- **v1.25.23** Hotfix: cards 2-per-line + tighter team columns. Ship: backend 1.25.23 + migrations 064/065/066.

## 2026-04-24 — Automated tournaments (v1.24.0)

- Phase 1 sync + Phase 2 async tournaments, double-elim BO3 (migration 050); bracket generator (byes, GF_RESET, prereq W/L role tags); region-pinned auto-connect; deterministic room name; plugin-level heartbeat; penalty % + speculative backfill.
- Discord lifecycle DMs, trophy roles, `/dm-opponent`, `/opp-online`. Bracket click-to-expand UI; timezone/date pickers (culture-invariant); per-match ranked auto-enable; multi-tournament series-lookup fix.
- Polish: round-won animation stall fix (deferred tint 2s); locale unicode strip; `<b>` bold-wrap; AFK flag requires cards_picked==0; ready-up 30s→90s. Hotfix: `/matches` AttributeError (26 min of 500s). Ship: v1.24.0 + Thunderstore zip.

> Sessions between 2026-04-28 and 2026-06-03 (v1.26.x, v1.27.0) were not formally handed off — see git history + `docs/CHANGELOG.md`.

---

## 2026-04-22 — v1.23.0 shipped (nametag styles, multi-color maps, hit/block/pass stats)

### v1.23.0 — Nametag Styles, Multi-Color Maps, Hit/Block/Pass Stats, Polish
Lifetime Hit % / Block % / Card Pass % stats with per-projectile hit gating and 1s dedup on block successes. 16 stackable nametag style SKUs (bold/italic/underline/strike + 6 colors + 3 sizes + 3 font transforms) visible to modded AND vanilla opponents via rich-text NickName. Multi-equip map colors with in-match Shift cycle (previously single-active). Shop category tabs + 200-row pool fix for "disappearing items". Ranked gold doubled + ranked XP multiplier 1.2x→1.5x. Live Ranked Games header pulsing (2.5s cadence). Card-name dedup: 175 offers + 297 match-cards across 11 variants. Phantom offline-room matches blocked + purged. New-install ranked-sync race fixed. Full details: CHANGELOG.md v1.23.0.

### v1.23.1 — Map cycle moving-box tint regression hotfix
Pressing Left Shift to cycle map colors was tinting every SpriteRenderer under `Map/*` (the 49 moving physics boxes) and every non-UI/non-player scene sprite. The tint pass now applies only where intended: the `OutOfBounds/*` wall particle systems + ArtInstance atmosphere particles. Moving boxes keep vanilla art.

---

## Older than v1.23

### v1.22.0 — Anti-cheat, Admin Tools, Map Colors, Polish
Anti-cheat flagging + auto-invalidation, admin tab with HMAC-signed endpoints and audit log, RD-aware betting odds + cutoff at 2 points in game 1 + one-bet-per-series, cosmetic trail Photon-late-arrival fix + in-shop preview, shop expansion (pronoun/uncommon titles, 4 rare trails, Tride legendary, vanilla and custom map color presets, Tride gradient), chat outside F5 with T key + bot reconnect catch-up + sync dedup, maintenance mode + server-status banner, Immovable/Pacifist pick-phase gate fix, admin username backfill.

### v1.20.0 — Economy, Chat, Betting, Trails
Gold currency, shop tab, 10 titles + 7 trails, betting with Elo odds, WebSocket in-game ↔ Discord chat bridge, pass-rate tracking on cards, data consent modal + Delete-my-data, version gate, auto-update, settings tab.

### v1.18.7 — Leaderboard polish, leave % tracking
Rating history line graph, Recent Ranked Series pagination, leave % tracking full stack, rating history inline snapshots, rating change swap fix, auto-update Thunderstore compatibility.

### v1.18.6
Menu overlay canvas, match found panel split, 3-column leaderboard, Recent Ranked Series panel, form graph, LB-detail achievements, achievement state reset, active-combat gate, API retry, match found sound, taskbar flash, casual W/L + sweep tracking, mod version endpoint, Discord bot rank/stats redesign, card aliases, installer polish.

### v1.18.4 → v1.18.5
(see git log for the granular summary — baseline of the ranked queue, Glicko-2, matchmaking, leaderboard tabs)

---

### Archived 2026-08-10 (from TODO.md)

## ✅ v1.38.0 — SHIPPED 2026-08-08

GitHub release live (DLL + cosmetics.zip), backend deployed, migrations
202-206 applied, release notes posted in en/es/ru for BOTH v1.37.0 and
v1.38.0, i18n at 0 missing in es/ru. 8 Codex Ultra rounds converged
16 → 12 → 12 → 7 → 5 → 3 → 1 → 1 (GO-WITH-FIXES, last LOW fixed).

**Delivered:** hosted 2v2/1v2 lobbies (create/browse/join/kick/member lists,
host-owned settings) replacing the old manual + consent queues · standing
admin alerts · chat slur filter with escalating auto-mute · animated cosmetic
uploads (multi-PNG + GIF) · body-colour team identity (server-decided coin
flip, room-prop distributed) · FFA max card draw · watch buttons on every
mode tab · LFP mode multi-select + Discord emoji · deep idle · shop New chip
+ on-body preview · admin tab restructure + ban-velocity gate · uncut
formatted release notes · Stan #178-181 (FFA before/after ratings, /game
codes, stats help page, graph redesign + whole-game timelines).

## 2026-08-16/17 — Broadcast infrastructure sessions
- Spectator broadcast system designed (8 review rounds), implemented across
  server (deployed, migration 225) and client, with an automated streaming
  pipeline brought to first light on dedicated infrastructure. Reserved
  broadcast spectator seat, service-account isolation policy, and stream
  lifecycle automation. Twitch/YouTube channels: SidsCompetitiveRounds.

## Archived 2026-08-23 (from TODO.md — previous “Completed This Session” sections, moved at the v1.39.2 handoff)

## ✅ Completed This Session (2026-08-11b) — bugs 199 + 200

* **Bug 199 root-caused and fixed** (server-only): resumed-series liveness.
  `ranked_series.last_activity_at` + migration 215, stamped at all three
  resume sites and the live-points POST, third liveness arm on **both**
  `/series/active` and `POST /bets`, activity-based `ORDER BY`. Verified
  against prod: 1432 rows backfill, 0 of 31 active series falsely surface.
* **Bug 200 root-caused and fixed** (server + client): queue-lock payloads now
  carry the resumed BO3 tally; client stashes it keyed on room name and
  consumes it one-shot inside the room-join reset (adopting at lock time is
  clobbered by the reset).
* **Adjacent finding fixed**: `spectate_games.ended_at` was written by nothing
  (0/34 rows) — `POST /spectate/close` on room leave + a 10-minute janitor
  sweep. This was the cause of Sid's `Game does not exist` rejoin failures.
* **Two adversarial review rounds.** Round 1 caught a REAL defect in the fix
  (three ORM assignments to an unmapped column = silent no-ops, Fix A 3/4
  inert while five comments claimed otherwise). Round 2: zero code defects,
  five comment corrections. Learnings **#345–#349** added.
* Bug reports **199** and **200** commented twice each (diagnosis, then fix).
* Ruled out and answered explicitly: spectators-disabled was NOT the cause;
  the @Gambler ping silence is CORRECT and stays; Spirit's "other issues" was
  bug 200 itself.

## ✅ Completed This Session (2026-07-29)

**Bug reports #111, #115–#123** — all root-caused, implemented, Codex-reviewed, comments posted.
- #116/#117 **the big one**: `SpawnPoint.localStartPos` is a pre-scale LOCAL coord consumed as a
  WORLD coord, so every 5+ player FFA round put everyone off their marker and into crates that deal
  damage + knockback. Live since v1.35.0. Map growth 3%→6%/player landed with it.
- #115 bug-report log in its own non-rich-text chunked pane with measured heights.
- #118 10-colour FFA graph palette (the vanilla skin bank is 4 wide, so slot 4 wrapped onto slot 0's
  exact colour).
- #119 1s FFA no-fire spawn grace, armed on the real combat-start edge.
- #120 FFA ID button → shared 12-char game code; `/matches/by-code` FFA branch; bot `/game` renders
  FFA.
- #121 economy rebalance + **migration 164 back-paid 1020g across 7 players**.
- #122 dedicated "How FFA works" / "How 1v2 works" FAQ entries.
- #123 per-opponent session W/L is pairwise by placement (was one `localWon` flag applied to the
  whole roster).
- #111 Hold-Start built, then **deleted** on Sid's call once item 5 superseded it.

**Wave 5 items 2, 3, 4(server), 6, 7** — odds band, `/rank-tiers` live role colours + FFA history
wrapping, bettable liveness/window, `/series/recent-multimode`, display-name fixes.

**LIVE INCIDENT resolved** — 4 players freed from a `ready_join` lockout (migration 165), root cause
found, server backstop deployed, client half committed. **Corrected learning #233, which was
built on a false premise and was dead code.**

**Pre-existing bug found in the incident logs:** `get_ranked_streak` was nested inside
`get_recent_series` but called from `submit_match`, so **streak achievements have never granted
since v1.30.0**. Fixed.

**Migrations applied: 163** (FFA shortcode index), **164** (gold back-pay), **165** (free stuck
ready_join rows + close abandoned lobbies + heal 2 display names from chat).

## ✅ Completed This Session (2026-07-14) — v1.32.0

- **11-item feature batch** (items 1–11): podium highlights + dynamic title + 3× XP; slayer 1000g + mig-123 backfill + God Build rename; bigger tournament text; tournament Discord feed + mig-124 availability DMs; screen-shake/lighting/shadows/animated-cosmetics settings; shop reorder; Block/Hit% analysis (list delivered in-chat); Discord bot expansion (/rank + /stats rework, /mystats, /cards, /graph, head-to-head /compare, /lb 50/page, live tournament board).
- **Two same-day feedback rounds fixed:** podium alpha/bracket-color/outline, /lb 50-per-page + server rank double-offset fix, /compare→head-to-head + /graph split, tournament board "How it works". Lighting purple = documented known issue.
- **Adversarial review** (27 agents / 6 dimensions): 18 confirmed findings (7 distinct) fixed pre-ship — availability-DM key mismatch, podium filter mismatch, wrong-time posts, pushback re-ask gap, board budget overflow, matplotlib thread race, slayer-gold HMAC hole.
- Learnings **#151–#155**.

## ✅ Completed This Session (2026-06-09) — v1.28.1 (bug-report validation + block fix)

**Shipped v1.28.1** (backend live, GitHub release + DLL, Thunderstore bundle built, clients auto-update).

- **#15 block in ranked/matchmade games** — block activated but absorbed nothing in competitive rooms. `GMArmsRaceStartGameBlockResetPatch` rebuilt block delegates every round even when nothing was destroyed (the rebuild strips the working chain). Gated on `if (r > 0)`. Validated by logs: 0/70 successful blocks (old) → 8/91 (fixed). (learning #89)
- **#20 phantom HUD series score ("4-0")** — per-series counter only reset on the reporter's client; now self-corrects off the BO3 score. Server confirmed clean.
- **#22 My Stats card-hover blocked the refresh button** — hover region was the full 900px text box; sized to rendered text via TMP `preferredWidth`. (learning #90)
- **#17 streak cap 20** — removed `LIMIT 20` in `get_ranked_streak()` + `LIMIT 50` in the 2v2 path.
- **#18 Discord "0 elo"** — display rounding `:.0f`→`:.1f` (data was correct; 1v1 + 2v2 embeds).
- **Bug reports/day 3 → 10.**
- **DC tracer widened to 1v1** — first NetworkRestart→LeaveRoom stack captured (turned out to be a normal end-of-series leave).
- Posted `bug-comment` audit notes on #15/#17/#18/#20/#22.
