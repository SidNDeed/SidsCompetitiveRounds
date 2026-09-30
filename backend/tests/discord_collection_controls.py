"""DISCORD-COLLECTION section 10: the mutation runner.

Every row of DISCORD-COLLECTION-DESIGN.md rev 13 section 10 is a mutation that
must turn a NAMED test red, paired with a negative control that keeps passing.
ROWS below holds each row's named test and its mutation, written as exact
edits: each edit is bounded to the AST span of one named top-level function,
class method or module-level assignment, and its anchor text must occur
EXACTLY ONCE inside that span before the edit (#432/#330) - never a
file-wide match. A row with more than one variant (5b, 10, 12n, 18b, 19, 20,
24, 24e, 25g, 29) runs each variant alone.

The controls of a row are the nodes named test_cNN_... in the two test
modules (NN the row id, zero-padded to two digits on the server side). Each
variant runs its named test, its controls and any cross control in ONE
pytest process on the mutated tree. `unmutated` names the controls the
design states over the UNMUTATED tree; their under-mutation outcome is
recorded for information, and their unmutated pass is the baseline's.

Usage, from the repository root or anywhere else (paths resolve from this
file; the database gate is the test modules' own):

    DISCORD_COLLECTION_TEST_PG_DSN=<lane DSN> python backend/tests/discord_collection_controls.py --out DIR
    ... --check             validate every anchor and the mutated parse, write nothing
    ... --list              print the variants
    ... --only 12l 12m      run the named rows (every variant of each)
    ... --skip-baseline     skip the unmutated run of every node

The tree must be clean: each mutation is written to the working file, the
file is restored from a copy held aside - never through git - and the
restoration is proven by sha256 and by `git diff --quiet` before the next
variant starts. A run interrupted mid-variant leaves DIR/aside/IN_PROGRESS.json;
the next run restores from it before anything else.
"""

import argparse
import ast
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
SERVER = "backend/tests/test_discord_collection_server.py"
BOT = "backend/tests/test_discord_collection_bot.py"
M = "backend/api/main.py"
S = "backend/api/pc_strip.py"
F = "backend/api/pc_face.py"
B = "backend/discord_bot.py"
EXPECTED_ROWS = 94
VARIANT_TIMEOUT_S = 1200


def E(path, span, old, new):
    """One edit: in `path`, inside the span of `span`, `old` -> `new`."""
    return {"path": path, "span": span, "old": old, "new": new}


def V(row, named, edits, label="", cross=(), expect=(), unmutated=(), note=""):
    return {"row": row, "label": label, "named": named, "edits": list(edits), "cross": list(cross),
            "expect": list(expect), "unmutated": list(unmutated), "note": note}


# -- shared anchors ---------------------------------------------------------------------

_BANNED_RULE = E(M, "_pc_composite_tile", '    if row["subject_banned"]:\n        return "back", "subject_banned"\n', "")
_HASH_CLAUSE = E(M, "internal_pc_lease_check",
                 '    if now_hash != row["leased_hash"]:\n'
                 '        raise HTTPException(status_code=404, detail={"error": "lease_gone"})\n', "")
_BAN_TERM = E(M, "internal_pc_lease_check", ' or row["subject_banned"]', "")
_NO_REREAD = E(B, "_pc_reveal_run", "        st, again = await reread()", "        st, again = 200, first")
_TIE_KEY = [E(M, "_pc_binder_page_sql", 'pool_rank, minted_at, print_id "', 'pool_rank, minted_at "'),
            E(M, "_pc_binder_page_sql", 'p.pool_rank, p.minted_at, p.print_id")', 'p.pool_rank, p.minted_at")')]
_POOL_DELETED = E(M, "_PC_POOL_MEMBER_SQL", "(p.deleted_at IS NULL\n           AND ", "(")
_PACE_ANCHOR = '    _pc_reveal_pace(pid, "json")\n'
_ROSTER_ANCHOR = '        packs[0]["prints"], _live = await _pc_roster_prints(db, pack_id, ctx)\n'
_STRIP_TOKEN = ('        tokens.append(_pcstrip.strip_slot_token(e["slot"], e["print_id"], e["tile"], word, state))')
_FACES = 'for p in prints if p.get("tile") == "face"}'
_RETRY = "        if st == 503 and code in _PC_COMPOSITE_RETRYABLE and attempt < _PC_COMPOSITE_RETRIES:"
_META_RETURN = "                meta.update(parsed)\n                return r.status, None, meta"
_RENDER_CALL = '_functools.partial(_pcf.render_face, spec, ctx["labels"], pbytes, size))'
_CONSENT_IMAGE = '    if not (is_owner or bool(getattr(owner, "pc_collection_public", True))):'
_KEY_CHECK = "    _require_internal_key(x_internal_key)\n"

ROWS = [
    # -- 1-4: ownership and consent ------------------------------------------------------
    V("1", "test_strip_refuses_a_pack_that_is_not_the_actors",
      [E(M, "internal_pc_pack_strip", "           AND player_id = CAST(:pid AS uuid)\n", "")]),
    V("2", "test_strip_404s_rather_than_403s_for_a_foreign_pack",
      [E(M, "internal_pc_pack_strip",
         '    if owned is None:\n        raise HTTPException(status_code=404, detail="Not found")',
         '    if owned is None:\n        raise HTTPException(status_code=403, detail="Not found")')]),
    V("3", "test_binder_JSON_of_a_private_player_is_refused",
      [E(M, "internal_pc_binder",
         '    if not is_owner and not bool(getattr(owner, "pc_collection_public", True)):', "    if False:")]),
    V("3b", "test_binder_IMAGE_of_a_private_player_is_refused",
      [E(M, "internal_pc_binder_page", _CONSENT_IMAGE, "    if not (is_owner or True):")]),
    V("3c", "test_binder_image_serves_a_public_binder_to_a_non_owner",
      [E(M, "internal_pc_binder_page", _CONSENT_IMAGE, "    if not is_owner:")]),
    V("3d", "test_binder_image_owner_with_no_discord_id_is_not_the_owner",
      [E(M, "internal_pc_binder_page", "                and owner.discord_id is not None\n", "")]),
    V("4", "test_binder_shards_reach_the_owner_only",
      [E(M, "internal_pc_binder", "    if is_owner:\n", "    if True:\n")]),
    # -- 5-7: nothing written, nothing scheduled ---------------------------------------------
    V("5", "test_no_reveal_route_writes_a_row",
      [E(M, "internal_pc_binder", _PACE_ANCHOR, _PACE_ANCHOR
         + '    await db.execute(text("UPDATE players SET pc_shards = pc_shards WHERE id = CAST(:p AS uuid)"),'
           ' {"p": pid})\n')]),
    V("5b", "test_no_reveal_route_touches_a_rating_an_item_or_a_match_result",
      [E(M, "internal_pc_binder", _PACE_ANCHOR, _PACE_ANCHOR
         + '    await db.execute(text("UPDATE player_items SET purchase_price = purchase_price'
           ' WHERE player_id = CAST(:p AS uuid)"), {"p": pid})\n')],
      label="player_items", expect=[r"'player_items': \['UPDATE player_items"]),
    V("5b", "test_no_reveal_route_touches_a_rating_an_item_or_a_match_result",
      [E(M, "internal_pc_binder", _PACE_ANCHOR, _PACE_ANCHOR
         + '    await db.execute(text("UPDATE matches SET id = id WHERE false"))\n')],
      label="matches", expect=[r"'matches': \['UPDATE matches"]),
    V("5b", "test_no_reveal_route_touches_a_rating_an_item_or_a_match_result",
      [E(M, "internal_pc_binder", _PACE_ANCHOR, _PACE_ANCHOR
         + '    await db.execute(text("UPDATE glicko_ratings SET rating = rating'
           ' WHERE player_id = CAST(:p AS uuid)"), {"p": pid})\n')],
      label="glicko_ratings", expect=[r"'glicko_ratings': \['UPDATE glicko_ratings"]),
    V("6", "test_reveal_never_schedules_a_prerender",
      [E(M, "internal_pc_packs", _ROSTER_ANCHOR, _ROSTER_ANCHOR
         + '        _pc_schedule_prerender([p["print_id"] for p in packs[0]["prints"]], ctx["locale"])\n')],
      note="the new packs route has no answer builder with a prerender parameter: the mutation adds the"
           " call prerender=True makes, at the point the route's prints are built"),
    V("7", "test_reveal_never_primes_steam",
      [E(M, "internal_pc_packs", _ROSTER_ANCHOR, _ROSTER_ANCHOR
         + '        await _pc_steam_prime([p["subject_player_id"] for p in packs[0]["prints"]])\n')]),
    # -- 8-10: the strip digest --------------------------------------------------------------
    V("8", "test_strip_key_moves_with_any_face_rev",
      [E(M, "internal_pc_pack_strip", _STRIP_TOKEN,
         '        tokens.append(_pcstrip.strip_slot_token(e["slot"], e["print_id"], e["tile"],'
         ' word if e["slot"] != 3 else "", state))')],
      note="drops the face_rev of slot 3, the slot the fixture renames"),
    V("9", "test_strip_key_moves_with_slot_order",
      [E(S, "composite_digest", "    parts.extend(tokens)", "    parts.extend(sorted(tokens))")]),
    V("10", "test_strip_key_moves_with_locale_and_layout_version",
      [E(S, "composite_digest", "             locale, renderer_fp]", "             renderer_fp]")],
      label="locale", expect=["the locale is not in the digest input"]),
    V("10", "test_strip_key_moves_with_locale_and_layout_version",
      [E(S, "_strip_layout_word",
         '    return "margin=%d;gutter=%d;tile=%dx%d;grid=%dx%d" % (\n'
         "        STRIP_MARGIN, STRIP_GUTTER, _strip_face.TILE_W, _strip_face.TILE_H, cols, rows)",
         '    return "grid=%dx%d" % (cols, rows)')],
      label="layout", expect=["a layout constant is not in the digest input"]),
    # -- 11-12i: what each slot draws --------------------------------------------------------
    V("11", "test_strip_has_exactly_five_slots_in_order",
      [E(S, "compose_composite", "    for box, (tile, data, discarded) in zip(boxes, cells):",
         "    for box, (tile, data, discarded) in zip(boxes, cells[::-1]):")]),
    V("12", "test_a_slot_whose_subject_has_no_steamid64_becomes_the_back_not_a_gap",
      [E(S, "compose_composite", '        elif tile == "back":\n            image = strip_back_tile()',
         '        elif tile == "back":\n            continue')]),
    V("12b", "test_the_back_tile_is_375x525_and_matches_the_asset_path",
      [E(S, "strip_back_tile", "    return _strip_back_at(_strip_face.ASSETS_DIR).copy()",
         '    return _StripImage.open(_strip_io.BytesIO(_strip_face.render_back())).convert("RGBA")')]),
    V("12c", "test_a_pack_with_a_no_steamid64_subject_still_posts_an_image",
      [E(B, "_pc_reveal_run", _FACES, 'for p in prints if p.get("tile") in ("face", "back")}')]),
    V("12d", "test_a_released_portrait_blob_503s_the_composite_and_publishes_nothing",
      [E(M, "_pc_composite_cold",
         '            if tile == "face":\n'
         '                _rev, face = await _pc_render_face(db, row, ctx, "tile")\n'
         '                tiles.append(("face", face, discarded))',
         '            if tile == "face":\n'
         '                try:\n'
         '                    _rev, face = await _pc_render_face(db, row, ctx, "tile")\n'
         '                    tiles.append(("face", face, discarded))\n'
         '                except _PcPortraitMissing:\n'
         '                    tiles.append(("back", None, False))')]),
    V("12e", "test_the_digest_separates_a_back_slot_from_a_drawn_slot",
      [E(M, "internal_pc_pack_strip", _STRIP_TOKEN,
         '        tokens.append(_pcstrip.strip_slot_token(e["slot"], e["print_id"], "face", e["face_rev"], state))')],
      note="the build's token formatter has no back branch (the caller picks the word): the collapse is"
           " written at the caller, every slot tokenised as a face with its face_rev"),
    V("12f", "test_a_discarded_print_of_a_no_steamid64_subject_draws_the_back_and_posts",
      [E(M, "_pc_composite_tile", '    if not row["subject_id_ok"]:\n        return "back", "no_steam_id"',
         '    if row["discarded_at"] is not None:\n        return "face", None\n'
         '    if not row["subject_id_ok"]:\n        return "back", "no_steam_id"')],
      note="the build states the discarded case as the fall-through (a face the compositor stamps); the"
           " mutation evaluates it first"),
    V("12g", "test_a_discard_changes_the_pixels_and_not_only_the_digest",
      [E(S, "compose_composite", "            if discarded:\n                image = _stamp_discarded(image)\n", "")],
      unmutated=["test_c12g_the_digest_half_alone_still_passes"]),
    V("12h", "test_a_pack_whose_subject_deleted_their_data_still_posts_five_slots",
      [E(M, "_pc_roster_prints", '    for e in roster:\n        row = live.get(e["print_id"])',
         '    for e in [x for x in roster if x["print_id"] in live]:\n        row = live.get(e["print_id"])')],
      note="enumerates only the rows the statement returned, in roster order: the pre-roster shape"),
    V("12i", "test_a_pack_whose_stored_roster_is_short_is_a_500",
      [E(M, "_pc_roster_slots", '    if tuple(e["slot"] for e in entries) != _PC_ROSTER_SLOTS:\n        return None\n',
         "")]),
    V("12j", "test_the_print_gone_slot_needs_no_lease_and_the_pack_posts",
      [E(B, "_pc_reveal_run", _FACES,
         'for p in prints if p.get("tile") == "face" or p.get("reason") == "print_gone"}')]),
    V("12k", "test_a_banned_subjects_slot_draws_the_back_and_takes_no_lease", [_BANNED_RULE]),
    V("12l", "test_a_ban_landing_after_the_row_read_drops_the_image", [_BAN_TERM],
      cross=["test_a_moved_portrait_hash_drops_the_image"]),
    V("12m", "test_a_moved_portrait_hash_drops_the_image", [_HASH_CLAUSE],
      cross=["test_a_ban_landing_after_the_row_read_drops_the_image"]),
    V("12n", "test_the_first_failing_clause_names_the_outcome", [_BANNED_RULE],
      label="clause1-banned", expect=[r"ROW12N failed runs: 1(?![0-9,])"]),
    V("12n", "test_the_first_failing_clause_names_the_outcome",
      [E(M, "internal_pc_pack_strip",
         '    if owned is None:\n        raise HTTPException(status_code=404, detail="Not found")\n', "")],
      label="clause2-ownership", expect=[r"ROW12N failed runs: 2(?![0-9,])"]),
    V("12n", "test_the_first_failing_clause_names_the_outcome",
      [E(M, "internal_pc_binder_page",
         _CONSENT_IMAGE + '\n        raise HTTPException(status_code=403, detail={"error": "private"})\n', "")],
      label="clause3-consent", expect=[r"ROW12N failed runs: 3(?![0-9,])"]),
    V("12n", "test_the_first_failing_clause_names_the_outcome",
      [E(B, "_pc_reveal_run", "            failed = _pc_reveal_check(kind, first, prints, meta)",
         "            failed = None")],
      label="clause4-manifest", expect=[r"ROW12N failed runs: 4(?![0-9,])"]),
    V("12n", "test_the_first_failing_clause_names_the_outcome",
      [E(M, "internal_pc_lease_check", 'not row["unexpired"] or ', "")],
      label="clause5-expired", expect=[r"ROW12N failed runs: 5(?![0-9,])"]),
    V("12n", "test_the_first_failing_clause_names_the_outcome", [_HASH_CLAUSE],
      label="clause6-portrait", expect=[r"ROW12N failed runs: 6(?![0-9,])"]),
    V("12n", "test_the_first_failing_clause_names_the_outcome",
      [E(B, "_pc_reveal_run", "        st, again = await reread()",
         "        st, again = await reread()\n        st, again = 200, first")],
      label="clause7-reread", expect=[r"ROW12N failed runs: 7(?![0-9,])"],
      note="the re-read's answer is deleted and its call kept: run 4's fixture hooks on that call and"
           " reads it, so deleting the call would red run 4 as well"),
    V("13", "test_discarded_print_still_draws_in_a_strip",
      [E(M, "internal_pc_pack_strip", "    for e in entries:\n        state = ",
         '    for e in entries:\n        if e.get("discarded"):\n'
         '            raise HTTPException(status_code=404, detail="Not found")\n        state = ')]),
    # -- 14-15: leases, the manifest, the re-read ---------------------------------------------
    V("14", "test_send_is_dropped_when_any_lease_is_gone",
      [E(B, "_pc_reveal_revalidate", "    return all(answers)", "    return answers[0]")]),
    V("14b", "test_the_leased_set_is_exactly_the_distinct_face_subjects",
      [E(B, "_pc_leases", "            leased[ref] = (lease_id, deadline)",
         "            leased[lease_id] = (lease_id, deadline)")],
      unmutated=["test_c14b_nine_distinct_subjects_take_nine_leases_and_attach"]),
    V("14c", "test_no_lease_taken_means_no_byte_get",
      [E(B, "_pc_reveal_run",
         "        if faces:\n            image, meta, note = await _pc_reveal_bytes(image_path, image_params)",
         "        if True:\n            image, meta, note = await _pc_reveal_bytes(image_path, image_params)")]),
    V("14d", "test_grid_is_dropped_when_the_manifest_differs_from_the_list_even_though_the_reread_agrees",
      [E(B, "_pc_reveal_check", '        if (got[1], got[2]) != (want[1], want[2]):\n            return "ids"\n', "")]),
    V("14g", "test_a_binder_page_never_lists_a_discarded_print",
      [E(M, "_pc_binder_page_sql", '"WHERE pr.owner_player_id = CAST(:owner AS uuid) AND pr.discarded_at IS NULL"',
         '"WHERE pr.owner_player_id = CAST(:owner AS uuid)"')]),
    V("14g2", "test_the_grid_manifest_numbers_grid_positions_not_pack_slots",
      [E(M, "internal_pc_binder_page",
         '        manifest.append(_pcstrip.grid_manifest_entry(pos, d["print_id"], d["subject_player_id"], tile, word))',
         '        manifest.append(_pcstrip.grid_manifest_entry(d["slot"], d["print_id"], d["subject_player_id"],'
         ' tile, word))')]),
    V("14h", "test_the_final_reread_runs_on_the_text_only_branch",
      [E(B, "_pc_reveal_run", "        st, again = await reread()",
         "        st, again = (await reread()) if image is not None else (200, first)")]),
    V("14i", "test_the_consent_reread_is_the_last_read_before_the_post",
      [E(B, "_pc_reveal_run",
         "        if image is not None and not await _pc_reveal_revalidate(leases):\n"
         '            print(f"[PC-REVEAL] {kind} ref={ref} picture dropped: a lease no longer authorises the send")\n'
         '            image, note = None, "unavailable"\n'
         "        st, again = await reread()",
         "        st, again = await reread()\n"
         "        if image is not None and not await _pc_reveal_revalidate(leases):\n"
         '            print(f"[PC-REVEAL] {kind} ref={ref} picture dropped: a lease no longer authorises the send")\n'
         '            image, note = None, "unavailable"')]),
    V("14j", "test_a_rebind_between_the_reads_is_caught_by_owner_ref",
      [E(B, "_PC_VIEW_MEMBERS", '_PC_VIEW_MEMBERS = ("actor_ref", "owner_ref", "settings_rev")',
         '_PC_VIEW_MEMBERS = ("actor_ref", "settings_rev")')]),
    V("14k", "test_the_binder_page_orders_a_tie_by_print_id", _TIE_KEY),
    V("14l", "test_a_tie_does_not_flip_the_binder_digest_or_the_binding", _TIE_KEY,
      unmutated=["test_c14l_with_the_key_the_same_heap_flip_still_attaches_and_keeps_one_digest"],
      note="the control is stated with the key present in both places: under the mutation the same"
           " heap flip reorders the page by construction"),
    V("14m", "test_the_binder_json_carries_a_tile_decision_for_every_entry",
      [E(M, "internal_pc_binder", "    for r in rows:\n        d = _pc_print_dict(r, ctx)",
         '    for r in rows:\n        r = {**dict(r), "subject_id_ok": False}\n        d = _pc_print_dict(r, ctx)')],
      note="both binder routes send ONE statement, so 'in the JSON route's statement only' is written as"
           " the JSON route's own copy of each row with subject_id_ok false"),
    V("14n", "test_a_subject_renamed_between_the_two_reads_drops_the_image",
      [E(B, "_pc_reveal_check",
         '        if got[4] != want[4]:\n            return "face_rev" if want[3] == "face" else "reason"',
         '        if want[3] != "face" and got[4] != want[4]:\n            return "reason"')]),
    V("14o", "test_the_caption_is_rendered_from_the_final_reread",
      [E(B, "_pc_reveal_run", "ctx.send(render(again, None), file=", "ctx.send(render(first, None), file="),
       E(B, "_pc_reveal_run", "ctx.send(render(again, note), **kwargs)", "ctx.send(render(first, note), **kwargs)")]),
    V("14p", "test_a_rename_after_the_image_still_posts_the_new_name",
      [E(B, "_pc_reveal_run", "        moved = _pc_reveal_moved(before_drawn, _pc_reveal_drawn(again_prints))",
         "        moved = []")]),
    V("14q", "test_a_discard_between_the_revalidation_and_the_reread_drops_the_image",
      [E(B, "_PC_DRAWN_MEMBERS", '"reason", "face_rev", "discarded")', '"reason", "face_rev")')]),
    V("14r", "test_the_binder_metadata_survives_an_empty_page",
      [E(M, "_pc_binder_page_sql", '" AS text)) AS n_r" + str(i)', '" AS text)) OVER () AS n_r" + str(i)'),
       E(M, "_pc_binder_page_sql",
         '            + "meta AS ( SELECT count(*) AS live_total" + per_rarity\n'
         '            + ", count(*) FILTER (WHERE rarity <> ALL(CAST(:rall AS text[]))) AS n_other FROM live ), "\n'
         '            + "page AS ( SELECT * FROM live "',
         '            + "page AS ( SELECT *, count(*) OVER () AS live_total" + per_rarity\n'
         '            + ", count(*) FILTER (WHERE rarity <> ALL(CAST(:rall AS text[]))) OVER () AS n_other FROM live "'),
       E(M, "_pc_binder_page_sql", '            + "SELECT m.*, p.* FROM meta m LEFT JOIN page p ON true "',
         '            + "SELECT p.* FROM page p "')],
      note="the window terms on the page statement, the handler unchanged"),
    V("14s", "test_the_binder_rarity_totals_sum_to_the_count",
      [E(M, "_pc_binder_page_sql",
         '            + ", count(*) FILTER (WHERE rarity <> ALL(CAST(:rall AS text[]))) AS n_other FROM live ), "',
         '            + " FROM live ), "'),
       E(M, "_pc_binder_page", '    by_rarity["other"] = int(head["n_other"])\n', ""),
       E(M, "_pc_binder_page",
         "    if sum(by_rarity.values()) != count:\n"
         '        print(f"[PC-BINDER] rarity_sum owner={owner_ref} count={count} sum={sum(by_rarity.values())}")\n'
         '        raise HTTPException(status_code=500, detail={"error": "binder_count_mismatch"})\n', ""),
       E(M, "_pc_binder_page",
         '    if by_rarity["other"]:\n'
         "        print(f\"[PC-BINDER] unknown_rarity owner={owner_ref} count={by_rarity['other']}\")\n", "")],
      note="the unknown_rarity log reads the 'other' key the mutation removes, so it goes with it"),
    V("14e", "test_grid_is_dropped_when_consent_rev_moved",
      [E(B, "_PC_VIEW_MEMBERS", '_PC_VIEW_MEMBERS = ("actor_ref", "owner_ref", "settings_rev")',
         '_PC_VIEW_MEMBERS = ("actor_ref", "owner_ref")')]),
    V("14f", "test_pack_is_dropped_when_actor_ref_moved", [_NO_REREAD]),
    V("15", "test_leases_are_released_on_every_exit_path",
      [E(B, "_pc_reveal_run",
         '                                                filename=f"{kind}.png"), **kwargs), timeout=budget)\n'
         '                return "posted"',
         '                                                filename=f"{kind}.png"), **kwargs), timeout=budget)\n'
         "                await _pc_lease_release_all([lease_id for lease_id, _deadline in leases.values()])\n"
         '                return "posted"'),
       E(B, "_pc_reveal_run",
         "    finally:\n        await _pc_lease_release_all([lease_id for lease_id, _deadline in leases.values()])",
         "    finally:\n        pass")],
      note="the finally is removed and the release kept on the image-sent path, which the control reads"),
    # -- 16-20: the pool, the cap, pacing, the key, the renderer gate ---------------------------
    V("16", "test_composite_does_not_nest_on_the_render_pool",
      [E(M, "_pc_composite_cold",
         "        tiles = []\n"
         "        for tile, row, discarded in cells:\n"
         '            if tile == "face":\n'
         '                _rev, face = await _pc_render_face(db, row, ctx, "tile")\n'
         '                tiles.append(("face", face, discarded))\n'
         "            else:\n"
         '                tiles.append(("back", None, False))\n'
         "        try:\n"
         "            return await _pc_face_cache.get_or_render(\n"
         "                key, _functools.partial(_pcstrip.compose_composite, tiles, cols, rows, _PC_COMPOSITE_MAX_BYTES))",
         "        loop = asyncio.get_running_loop()\n"
         "\n"
         "        def _nested():\n"
         "            tiles = []\n"
         "            for tile, row, discarded in cells:\n"
         '                if tile == "face":\n'
         "                    _rev, face = asyncio.run_coroutine_threadsafe(\n"
         '                        _pc_render_face(db, row, ctx, "tile"), loop).result(timeout=75)\n'
         '                    tiles.append(("face", face, discarded))\n'
         "                else:\n"
         '                    tiles.append(("back", None, False))\n'
         "            return _pcstrip.compose_composite(tiles, cols, rows, _PC_COMPOSITE_MAX_BYTES)\n"
         "        try:\n"
         "            return await _pc_face_cache.get_or_render(key, _nested)")],
      note="the tile renders run inside the composite's own pool job; the job's wait on each tile is bounded"
           " at 75 s only so that the blocked workers let the process exit after the test's 60 s red"),
    V("16b", "test_composites_do_not_starve_the_face_routes",
      [E(M, "internal_pc_face_print", "    rev, data = await _pc_render_face(db, row, ctx, size)",
         "    async with _pc_composite_gate.admit():\n        rev, data = await _pc_render_face(db, row, ctx, size)")]),
    V("17", "test_composite_over_the_cap_is_refused_not_truncated",
      [E(M, "_pc_composite_cold", "_functools.partial(_pcstrip.compose_composite, tiles, cols, rows, _PC_COMPOSITE_MAX_BYTES))",
         "_functools.partial(_pcstrip.compose_composite, tiles, cols, rows, 1 << 62))")],
      note="the cap check lifted out of the fuse to its caller: the compositor no longer refuses, the"
           " caller's post-render check does"),
    V("17b", "test_the_composite_cap_is_one_number_on_both_sides",
      [E(B, "_pc_reveal_bytes", "timeout=35.0, max_bytes=_PC_COMPOSITE_MAX_BYTES)", "timeout=35.0)")]),
    V("17c", "test_the_densest_grid_is_served_whole_under_the_cap",
      [E(M, "_PC_COMPOSITE_MAX_BYTES", "_PC_COMPOSITE_MAX_BYTES = 8 << 20", "_PC_COMPOSITE_MAX_BYTES = 64 << 10")],
      unmutated=["test_c17c_the_five_slot_strip_of_the_same_tiles_is_also_served_whole"]),
    V("18", "test_per_player_composite_pacing_refuses_the_seventh_in_a_minute",
      [E(M, "_PC_COMPOSITE_PER_PLAYER", "_PC_COMPOSITE_PER_PLAYER = 6", "_PC_COMPOSITE_PER_PLAYER = 7")]),
    V("18b", "test_the_pacing_window_is_bracketed_from_both_sides",
      [E(M, "_PC_REVEAL_WINDOW_S", "_PC_REVEAL_WINDOW_S = 60", "_PC_REVEAL_WINDOW_S = 30")],
      label="window30", expect=["request 7 at t=45 s answered 200"],
      unmutated=["test_c18b_requests_one_to_six_still_pass_in_both_runs"]),
    V("18b", "test_the_pacing_window_is_bracketed_from_both_sides",
      [E(M, "_PC_REVEAL_WINDOW_S", "_PC_REVEAL_WINDOW_S = 60", "_PC_REVEAL_WINDOW_S = 120")],
      label="window120", expect=["request 7 at t=61 s answered 429"],
      unmutated=["test_c18b_requests_one_to_six_still_pass_in_both_runs"]),
] + [
    V("19", "test_internal_key_is_required_before_any_work", [E(M, handler, _KEY_CHECK, "")], label=handler)
    for handler in ("internal_pc_packs", "internal_pc_pack_strip", "internal_pc_binder", "internal_pc_binder_page")
] + [
    V("19b", "test_the_middleware_refuses_before_the_handler_is_entered",
      [E(M, "rate_limit_gate",
         '            return JSONResponse(status_code=403, content={"error": "forbidden"})\n'
         "        return await call_next(request)   # authorized bot",
         "            pass\n        return await call_next(request)   # authorized bot")]),
    V("20", "test_renderer_unavailable_503s_before_ownership_is_read",
      [E(M, "internal_pc_pack_strip", _KEY_CHECK + "    _pc_require_renderer()\n", _KEY_CHECK),
       E(M, "internal_pc_pack_strip", "    actor = await _pc_player_by_discord(db, discord_id)\n",
         "    actor = await _pc_player_by_discord(db, discord_id)\n    _pc_require_renderer()\n")],
      label="strip"),
    V("20", "test_renderer_unavailable_503s_before_ownership_is_read",
      [E(M, "internal_pc_packs", _KEY_CHECK + "    _pc_require_renderer()\n", _KEY_CHECK),
       E(M, "internal_pc_packs", "    actor = await _pc_player_by_discord(db, discord_id)\n",
         "    actor = await _pc_player_by_discord(db, discord_id)\n    _pc_require_renderer()\n")],
      label="packs"),
    V("20", "test_renderer_unavailable_503s_before_ownership_is_read",
      [E(M, "internal_pc_binder_page", _KEY_CHECK + "    _pc_require_renderer()\n", _KEY_CHECK),
       E(M, "internal_pc_binder_page",
         "        Player.id == uuid.UUID(owner_ref), Player.deleted_at.is_(None)))).scalar_one_or_none()\n",
         "        Player.id == uuid.UUID(owner_ref), Player.deleted_at.is_(None)))).scalar_one_or_none()\n"
         "    _pc_require_renderer()\n")],
      label="page"),
    # -- 21-24e: the bot's own reads -----------------------------------------------------------
    V("21", "test_prefix_pack_with_private_true_sends_one_line_and_nothing_else",
      [E(B, "_pc_reveal_pack", '    if private and getattr(ctx, "interaction", None) is None:', "    if False:")]),
    V("22", "test_composite_leases_name_a_subject_and_never_a_print",
      [E(B, "_pc_leases", "await _pc_lease(ref, timeout=min(2.0, remaining))",
         "await _pc_lease(ref, print_id=ref, timeout=min(2.0, remaining))")],
      unmutated=["test_c22_the_discarded_prints_subject_is_leased_and_the_image_attached"],
      note="_pc_leases holds subject refs only, so the print_id it passes is the ref it holds"),
    V("23", "test_bot_falls_back_to_text_on_404_without_retrying",
      [E(B, "_pc_reveal_bytes", _RETRY,
         "        if (st == 503 and code in _PC_COMPOSITE_RETRYABLE or st == 404) and attempt < _PC_COMPOSITE_RETRIES:")]),
    V("23b", "test_a_portrait_pending_503_is_retried_once_and_the_image_is_attached",
      [E(B, "_pc_api_bytes", _META_RETURN, "                return r.status, None, {}")],
      unmutated=["test_c23b_a_flat_portrait_pending_body_is_also_retried"]),
    V("23c", "test_composite_busy_is_retried_at_most_twice_then_falls_back",
      [E(B, "_pc_reveal_bytes", _RETRY, "        if st == 503 and code in _PC_COMPOSITE_RETRYABLE:")]),
    V("23d", "test_the_acquire_to_send_span_fits_the_lease",
      [E(B, "_pc_reveal_run",
         "            image, meta, note = await _pc_reveal_bytes(image_path, image_params)\n"
         "        if image is not None:\n            started = time.monotonic()",
         '            image = b""\n        if image is not None:\n            started = time.monotonic()'),
       E(B, "_pc_reveal_run",
         "        if image is not None:\n            failed = _pc_reveal_check(kind, first, prints, meta)",
         "        if image is not None:\n            image, meta, note = await _pc_reveal_bytes(image_path, image_params)\n"
         "        if image is not None:\n            failed = _pc_reveal_check(kind, first, prints, meta)")],
      expect=[r"ROW23D byte phase"],
      note="the control is the named test's own unmutated run (same 63 s byte phase, image attached)"),
    V("23e", "test_the_acquire_phase_is_bounded_by_its_deadline",
      [E(B, "_pc_leases", "timeout=min(2.0, remaining))", "timeout=2.0)")],
      expect=[r"ROW23E measured acquire phase 21\.125 s over 10 requests"]),
    V("23f", "test_the_composite_byte_timeout_outlives_the_server_ceiling",
      [E(B, "_pc_reveal_bytes", "timeout=35.0, max_bytes=", "timeout=20.0, max_bytes=")]),
    V("23g", "test_the_byte_phase_is_bounded_by_its_attempt_count",
      [E(B, "_PC_COMPOSITE_RETRIES", "_PC_COMPOSITE_RETRIES = 2 ", "_PC_COMPOSITE_RETRIES = 5 ")],
      unmutated=["test_c23g_two_slow_busy_answers_then_a_200_still_attach"]),
    V("23h", "test_the_shipped_lease_callers_keep_their_own_timeouts",
      [E(B, "_pc_lease", "event_ids=None, *, timeout=None):", "event_ids=None, *, timeout=2.0):"),
       E(B, "_pc_lease_live", "async def _pc_lease_live(lease_id, *, timeout=None):",
         "async def _pc_lease_live(lease_id, *, timeout=3.0):")]),
    V("23i", "test_the_acquire_phase_count_term_is_enforced_by_the_refusal",
      [E(B, "_pc_leases", "    if len(refs) > 10:", "    if False:")],
      expect=[r"ROW23I measured acquire phase 6\.25 s over 25 requests"]),
    V("23j", "test_a_ref_past_the_deadline_is_never_issued",
      [E(B, "_pc_leases", "        if remaining <= 0:", "        if False:")]),
] + [
    V("24", "test_pc_api_bytes_returns_three_and_every_caller_unpacks_three",
      [E(B, span, old, old.replace(", _ = ", " = "))], label=span)
    for span, old in (("_pc_back_bytes", "st, data, _ = await _pc_api_bytes("),
                      ("_pc_best_face", "st, face, _ = await _pc_api_bytes("),
                      ("cmd_pc_card", "st, face, _ = await _pc_api_bytes("),
                      ("poll_pc_events", "st, face, _ = await _pc_api_bytes("))
] + [
    V("24b", "test_pc_api_bytes_honours_max_bytes_per_call",
      [E(B, "_pc_api_bytes", "            if declared <= 0 or declared > max_bytes:",
         "            if declared <= 0 or declared > _PC_FACE_MAX_BYTES:")]),
    V("24c", "test_a_non_200_never_returns_bytes",
      [E(B, "_pc_api_bytes", _META_RETURN, "                return r.status, (parsed or None), meta")],
      note="the parsed error body, when one was parsed, goes to the bytes slot instead of meta: the"
           " build parses an empty body to {} on the same return, which is no error body"),
    V("24d", "test_a_non_200_body_is_unwrapped_from_detail",
      [E(B, "_pc_api_bytes", "                        d = _pc_detail(json.loads(await r.content.readexactly(size)))",
         "                        d = json.loads(await r.content.readexactly(size))")]),
    V("24e", "test_a_composite_timeout_is_a_retryable_code",
      [E(M, "_pc_composite_bytes",
         '            raise HTTPException(status_code=503, detail={"error": "composite_timeout", "retry_after": 5},\n'
         '                                headers={"Retry-After": "5"})',
         "            raise HTTPException(status_code=503)")],
      label="bare-503"),
    V("24e", "test_a_composite_timeout_is_a_retryable_code",
      [E(B, "_PC_COMPOSITE_RETRYABLE",
         '_PC_COMPOSITE_RETRYABLE = ("portrait_pending", "composite_busy", "composite_timeout")',
         '_PC_COMPOSITE_RETRYABLE = ("portrait_pending", "composite_busy")')],
      label="retryable-set"),
    # -- 25-28: the face inputs, the pool, the statement, the layout -----------------------------
    V("25", "test_every_drawn_face_input_is_in_the_spec_dict",
      [E(M, "_pc_render_face", _RENDER_CALL,
         '_functools.partial(_pcf.render_face, dict(spec, subtitle=str(spec.get("subtitle") or "")'
         ' + str(row["slot"])), ctx["labels"], pbytes, size))')],
      note="the drawn input that bypasses spec is the print's slot, drawn into the subtitle after the key"),
    V("25b", "test_render_face_takes_exactly_four_arguments",
      [E(F, "render_face", "def render_face(spec: dict, labels: dict, portrait_png: bytes | None, size: str) -> bytes:",
         "def render_face(spec: dict, labels: dict, portrait_png: bytes | None, size: str, tint=None) -> bytes:"),
       E(M, "_pc_render_face", _RENDER_CALL,
         '_functools.partial(_pcf.render_face, spec, ctx["labels"], pbytes, size, (255, 0, 255)))')],
      unmutated=["test_c25b_the_four_argument_call_and_a_keyed_spec_field_still_pass"]),
    V("25c", "test_every_resolved_colour_reaches_the_renderer_inside_the_spec",
      [E(M, "_pc_face_inputs", '"band": band, "name": name or "", "title": title, "title_rgb": _pc_hex_rgb(title_hex),',
         '"band": band, "name": name or "", "title": title,'),
       E(M, "_pc_face_inputs", "    return spec, kind, phash, rev",
         '    spec["title_rgb"] = _pc_hex_rgb(title_hex)\n    return spec, kind, phash, rev')],
      note="the colour reaches the renderer in the spec object AFTER its key was taken"),
    V("25d", "test_no_face_colour_arrives_from_outside_spec_source_or_assets",
      [E(F, "FONTS_DIR", "FONTS_DIR = str(_FONTS_PATH)",
         "FONTS_DIR = str(_FONTS_PATH)\nimport os as _tint_os\n"
         '_TITLE_TINT = tuple(int(x) for x in _tint_os.environ.get("PC_TITLE_TINT", "255,0,255").split(","))'),
       E(F, "_draw_stats", '    if title_colour is None:\n        title_colour = LAYOUT["colours"]["label"]',
         "    if title_colour is None:\n        title_colour = _TITLE_TINT")]),
    V("25e", "test_a_colour_table_failure_does_not_abort_a_composite",
      [E(M, "_rank_colors",
         "            async with db.begin_nested():\n"
         "                rows = (await db.execute(select(RankRoleColor))).scalars().all()",
         "            rows = (await db.execute(select(RankRoleColor))).scalars().all()")]),
    V("26", "test_only_the_four_new_routes_move_in_the_route_manifest",
      [E(M, "_PC_PRINT_FACE_SELECT",
         '           s.display_name AS subject_name, """ + _pc_portrait_resolve_cols("s") + """,',
         '           s.display_name AS subject_name, """ + _sid64.individual_id_sql("s.steam_id")'
         ' + """ AS subject_id_ok, """ + _pc_portrait_resolve_cols("s") + """,'),
       E(M, "_pc_composite_row_sql", '    return ("SELECT q.*, " + _PC_COMPOSITE_SUBJECT_ID_SQL + " AS subject_id_ok "\n',
         '    return ("SELECT q.* "\n')],
      unmutated=["test_c26_the_new_route_set_is_still_exactly_the_four"]),
    V("26b", "test_the_composite_wrap_states_no_order_and_preserves_the_row_set",
      [E(M, "_pc_composite_row_sql", '" JOIN players s2 ON s2.id = q.subject_player_id ")',
         '" JOIN players s2 ON true ")')],
      unmutated=["test_c26b_the_pack_form_still_returns_every_row_of_its_pack"]),
    V("26c", "test_the_composite_statement_is_assembled_and_runs",
      [E(M, "_pc_composite_row_sql",
         '            + " FROM ( " + _PC_PRINT_FACE_SELECT + " " + where + " ) q "\n'
         '            + " JOIN players s2 ON s2.id = q.subject_player_id ")',
         '            + " FROM ( " + _PC_PRINT_FACE_SELECT + " {where} ) q "\n'
         '            + " JOIN players s2 ON s2.id = q.subject_player_id ").format(where=where)')],
      expect=[r"per route: \{'strip': \(500, 0\), 'pack read': \(500, 0\), 'binder': \(500, 0\)\}",
              r"the builder: IndexError: Replacement index 17 out of range"]),
    V("26d", "test_the_binder_statement_restates_its_order_at_depth_zero",
      [E(M, "_pc_binder_page_sql",
         '            + "SELECT m.*, p.* FROM meta m LEFT JOIN page p ON true "\n'
         "            + \"ORDER BY CASE p.rarity WHEN 'legendary' THEN 0 WHEN 'epic' THEN 1 WHEN 'rare' THEN 2 WHEN"
         " 'uncommon' THEN 3 ELSE 4 END, p.signed DESC, p.foil DESC, p.pool_rank, p.minted_at, p.print_id\")",
         '            + "SELECT m.*, p.* FROM meta m LEFT JOIN page p ON true ")')],
      expect=["the last ORDER BY sits at parenthesis depth"],
      unmutated=["test_c26d_the_intact_statement_returns_one_sequence_under_both_plans"]),
    V("25f", "test_the_face_context_carries_the_rank_colour_map",
      [E(M, "_pc_face_ctx", '"colors": colors}', '"colors": {}}')]),
    V("25g", "test_the_pool_still_refuses_a_deleted_or_non_steamid_subject", [_POOL_DELETED],
      label="deleted_at", expect=["a deleted subject is admitted"]),
    V("25g", "test_the_pool_still_refuses_a_deleted_or_non_steamid_subject",
      [E(M, "_PC_POOL_STEAM_ID_SQL", "\"(CASE WHEN p.steam_id ~ '^[0-9]{17}$' THEN ",
         "\"(true OR CASE WHEN p.steam_id ~ '^[0-9]{17}$' THEN ")],
      label="steam-id-true", expect=["an anonymised deleted_ id is admitted"],
      note="the id rule reads true: `(true OR <rule>)`"),
    V("27", "test_composite_rects_come_from_the_layout_formula",
      [E(S, "strip_paste_boxes", "            x, y = strip_origin(col, row)\n",
         "            x, y = strip_origin(col, row)\n            if col == 4:\n                x = 1185\n")]),
    V("28", "test_a_deleted_subject_cannot_be_minted", [_POOL_DELETED]),
    # -- 29-31 ---------------------------------------------------------------------------------
    V("29", "test_the_actor_is_resolved_from_the_gateway_id_alone",
      [E(B, "_pc_reveal_pack", "    me, locale = str(ctx.author.id), _pc_locale_of(ctx)",
         "    me, locale = str(ctx.author.name), _pc_locale_of(ctx)")],
      label="pack", unmutated=["test_c29_a_handle_matching_nobody_still_resolves_normally"]),
    V("29", "test_the_actor_is_resolved_from_the_gateway_id_alone",
      [E(B, "_pc_reveal_binder", '"viewer_discord_id": str(ctx.author.id), "page": int(page),',
         '"viewer_discord_id": str(ctx.author.name), "page": int(page),')],
      label="binder-viewer", unmutated=["test_c29_a_handle_matching_nobody_still_resolves_normally"]),
    V("30", "test_the_reveal_adds_no_second_pending_dm_poller",
      [E(B, "on_ready", "    if not poll_pending_dms.is_running(): poll_pending_dms.start()",
         "    if not poll_pending_dms.is_running(): poll_pending_dms.start()\n"
         "    asyncio.create_task(poll_pending_dms.coro())")]),
    V("31", "test_a_gone_slot_never_carries_a_stored_name",
      [E(M, "_pc_roster_prints", '"subject_name": _pc_neutral_name(ctx), "face_rev": None})',
         '"subject_name": None, "face_rev": None})')]),
]


# -- the tree -------------------------------------------------------------------------------

def git(*args, check=True):
    return subprocess.run(["git", "-C", str(ROOT)] + list(args), capture_output=True, text=True, check=check)


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def tree_clean():
    return git("status", "--porcelain").stdout.strip() == ""


def read_text(path):
    raw = (ROOT / path).read_bytes()
    crlf, lf = raw.count(b"\r\n"), raw.count(b"\n")
    if crlf and crlf != lf:
        raise SystemExit(f"{path}: mixed line endings ({crlf} CRLF of {lf} LF), refusing to edit")
    return raw, raw.decode("utf-8").replace("\r\n", "\n"), bool(crlf)


def span_of(text, name, path):
    """(first line, last line), 1-based inclusive, of the ONE top-level
    function, class, method (Class.method) or assignment called `name`."""
    tree = ast.parse(text)
    parts = name.split(".")
    scope = tree.body
    node = None
    for i, part in enumerate(parts):
        hits = []
        for n in scope:
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and n.name == part:
                hits.append(n)
            elif i == len(parts) - 1 and isinstance(n, (ast.Assign, ast.AnnAssign)):
                targets = n.targets if isinstance(n, ast.Assign) else [n.target]
                if any(isinstance(t, ast.Name) and t.id == part for t in targets):
                    hits.append(n)
        if len(hits) != 1:
            raise ValueError(f"{path}: {len(hits)} definitions of {'.'.join(parts[:i + 1])}")
        node = hits[0]
        scope = getattr(node, "body", [])
    first = min([node.lineno] + [d.lineno for d in getattr(node, "decorator_list", [])])
    return first, node.end_lineno


def apply_edit(text, edit):
    first, last = span_of(text, edit["span"], edit["path"])
    lines = text.split("\n")
    seg = "\n".join(lines[first - 1:last])
    n = seg.count(edit["old"])
    if n != 1:
        raise ValueError(f"{edit['path']}:{edit['span']} (lines {first}-{last}): anchor occurs {n} times: "
                         f"{edit['old'][:80]!r}")
    seg = seg.replace(edit["old"], edit["new"], 1)
    return "\n".join(lines[:first - 1] + [seg] + lines[last:]), (first, last)


def mutated_files(variant):
    """{path: (original bytes, mutated bytes, [(span, first, last)])}."""
    out = {}
    for path in dict.fromkeys(e["path"] for e in variant["edits"]):
        raw, text, crlf = read_text(path)
        spans = []
        for edit in [e for e in variant["edits"] if e["path"] == path]:
            text, (first, last) = apply_edit(text, edit)
            spans.append((edit["span"], first, last))
        ast.parse(text)
        new = (text.replace("\n", "\r\n") if crlf else text).encode("utf-8")
        if new == raw:
            raise ValueError(f"{path}: the mutation changed nothing")
        out[path] = (raw, new, spans)
    return out


# -- the tests ------------------------------------------------------------------------------

def test_names(module):
    return re.findall(r"^def (test_[A-Za-z0-9_]+)\(", (ROOT / module).read_text(encoding="utf-8"), re.M)


def control_prefix(row):
    m = re.fullmatch(r"([0-9]+)([a-z0-9]*)", row)
    return f"test_c{int(m.group(1)):02d}{m.group(2)}_", f"test_c{int(m.group(1))}{m.group(2)}_"


def resolve(variants):
    """Attach node ids: the named test, the row's controls, the cross nodes."""
    where = {}
    for module in (SERVER, BOT):
        for name in test_names(module):
            if name in where:
                raise SystemExit(f"{name} is defined in two modules")
            where[name] = module
    for v in variants:
        if v["named"] not in where:
            raise SystemExit(f"row {v['row']}: named test {v['named']} not found")
        prefixes = control_prefix(v["row"])
        v["controls"] = sorted(n for n in where if n.startswith(prefixes))
        for n in v["cross"] + v["unmutated"]:
            if n not in where:
                raise SystemExit(f"row {v['row']}: node {n} not found")
        v["nodes"] = {n: f"{where[n]}::{n}" for n in [v["named"]] + v["controls"] + v["cross"]}
    return where


def variant_id(v):
    return v["row"] + ("-" + v["label"] if v["label"] else "")


def parse_junit(path):
    out = {}
    if not path.exists():
        return out
    for tc in ET.parse(path).getroot().iter("testcase"):
        outcome, message, text = "passed", "", ""
        for child in tc:
            if child.tag in ("failure", "error") and outcome == "passed":
                outcome = "failed" if child.tag == "failure" else "error"
                message, text = child.get("message") or "", child.text or ""
            elif child.tag == "skipped" and outcome == "passed":
                outcome = "skipped"
        stdout = "".join(c.text or "" for c in tc if c.tag == "system-out")
        out[tc.get("name")] = {"outcome": outcome, "message": message, "text": text, "stdout": stdout,
                               "time": float(tc.get("time") or 0)}
    return out


def run_pytest(nodes, junit, log, timeout):
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    cmd = [sys.executable, "-m", "pytest", *nodes, "-p", "no:cacheprovider", "-p", "no:randomly", "-q", "-rfE",
           f"--junitxml={junit}", "-o", "junit_logging=all", "-o", "junit_log_passing_tests=True"]
    started = time.monotonic()
    with open(log, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("$ " + " ".join(cmd) + "\n")
        fh.flush()
        proc = subprocess.Popen(cmd, cwd=str(ROOT), env=env, stdout=fh, stderr=subprocess.STDOUT)
        try:
            code = proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
            code = "timeout"
    return code, round(time.monotonic() - started, 1)


def red_excerpt(result, limit=14):
    lines = [ln for ln in result["text"].split("\n") if ln.startswith("E ")]
    rows = [ln for ln in result["stdout"].split("\n") if ln.startswith("ROW")]
    return {"message": result["message"][:600], "E": lines[:limit], "ROW": rows[:12]}


# -- aside copies ---------------------------------------------------------------------------

def aside_dir(out):
    return out / "aside"


def recover(out):
    marker = aside_dir(out) / "IN_PROGRESS.json"
    if not marker.exists():
        return None
    record = json.loads(marker.read_text(encoding="utf-8"))
    for path, info in record["files"].items():
        data = (aside_dir(out) / info["copy"]).read_bytes()
        if sha256(data) != info["sha256"]:
            raise SystemExit(f"aside copy of {path} does not match its recorded sha256; restore by hand")
        (ROOT / path).write_bytes(data)
    marker.unlink()
    return record


def restore(out, files):
    problems = []
    for path, (raw, _new, _spans) in files.items():
        (ROOT / path).write_bytes(raw)
        if sha256((ROOT / path).read_bytes()) != sha256(raw):
            problems.append(f"{path}: sha256 after restore differs")
    if git("diff", "--quiet", check=False).returncode != 0:
        problems.append("git diff --quiet reports a difference")
    if not tree_clean():
        problems.append("git status --porcelain is not empty: " + git("status", "--porcelain").stdout[:300])
    marker = aside_dir(out) / "IN_PROGRESS.json"
    if not problems and marker.exists():
        marker.unlink()
    return problems


def judge(v, results, code):
    named = results.get(v["named"])
    verdict, notes = "MET", []
    if code == "timeout":
        notes.append("the pytest process was killed at the variant timeout")
    if named is None:
        return "NO-RESULT", notes + ["the named test has no junit result"]
    if named["outcome"] not in ("failed", "error"):
        return "NOT-RED", notes + [f"the named test {named['outcome']} under the mutation"]
    blob = named["message"] + "\n" + named["text"] + "\n" + named["stdout"]
    for pattern in v["expect"]:
        if not re.search(pattern, blob):
            verdict = "EXPECT-MISS"
            notes.append(f"expected output not found: {pattern}")
    for n in v["controls"] + v["cross"]:
        r = results.get(n)
        got = r["outcome"] if r else "missing"
        if got != "passed":
            if n in v["unmutated"]:
                notes.append(f"{n} {got} under the mutation (the design states it over the unmutated tree)")
            else:
                if verdict == "MET":
                    verdict = "CONTROL-RED"
                notes.append(f"{n} {got} under the mutation")
    return verdict, notes


# -- main -----------------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=False)
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--skip-baseline", action="store_true")
    ap.add_argument("--timeout", type=int, default=VARIANT_TIMEOUT_S)
    args = ap.parse_args()
    # A red message can quote response bytes (a PNG body read as text); on a
    # console or file whose encoding cannot hold them, print escapes them
    # rather than raising mid-run.
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(errors="backslashreplace")

    variants = [dict(v) for v in ROWS]
    rows = list(dict.fromkeys(v["row"] for v in variants))
    if len(rows) != EXPECTED_ROWS:
        raise SystemExit(f"{len(rows)} rows in ROWS, section 10 has {EXPECTED_ROWS}")
    resolve(variants)
    if args.only:
        unknown = set(args.only) - set(rows)
        if unknown:
            raise SystemExit(f"unknown rows: {sorted(unknown)}")
        variants = [v for v in variants if v["row"] in set(args.only)]
    print(f"rows {len(rows)}; variants selected {len(variants)}")

    if args.list:
        for v in variants:
            print(f"{variant_id(v):28} {v['named']}  controls={len(v['controls'])} cross={len(v['cross'])}"
                  f" edits={len(v['edits'])}")
        return 0
    if args.check:
        bad = 0
        for v in variants:
            try:
                files = mutated_files(v)
                spans = "; ".join(f"{p}:{s}@{a}-{b}" for p, (_r, _n, sp) in files.items() for s, a, b in sp)
                print(f"OK   {variant_id(v):28} {spans}")
            except Exception as ex:
                bad += 1
                print(f"FAIL {variant_id(v):28} {type(ex).__name__}: {ex}")
        print(f"check: {len(variants) - bad} of {len(variants)} variants apply and parse")
        return 1 if bad else 0

    if not args.out:
        raise SystemExit("--out DIR is required for a run")
    if not os.environ.get("DISCORD_COLLECTION_TEST_PG_DSN"):
        raise SystemExit("DISCORD_COLLECTION_TEST_PG_DSN is not set: the rows need the lane database")
    out = Path(args.out)
    (out / "variants").mkdir(parents=True, exist_ok=True)
    aside_dir(out).mkdir(parents=True, exist_ok=True)
    recovered = recover(out)
    if recovered:
        print(f"RECOVERED an interrupted variant ({recovered['variant']}) from the aside copies")
    if not tree_clean():
        raise SystemExit("the tree is not clean: commit first, the runner mutates a frozen tree")
    head = git("rev-parse", "HEAD").stdout.strip()
    report = {"head": head, "started": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
              "rows": len(rows), "variants": [], "baseline": None}

    if not args.skip_baseline:
        nodes = sorted({node for v in variants for node in v["nodes"].values()})
        junit, log = out / "baseline.junit.xml", out / "baseline.log"
        code, secs = run_pytest(nodes, junit, log, max(args.timeout, 3600))
        results = parse_junit(junit)
        failing = sorted(n for n, r in results.items() if r["outcome"] != "passed")
        report["baseline"] = {"nodes": len(nodes), "results": len(results), "exit": code, "seconds": secs,
                              "not_passed": failing,
                              "ROW": {n: [ln for ln in r["stdout"].split("\n") if ln.startswith("ROW")]
                                      for n, r in results.items() if "ROW" in r["stdout"]}}
        print(f"baseline: {len(results)} of {len(nodes)} nodes, exit {code}, {secs} s, not passed {failing}")
        if failing or len(results) != len(nodes):
            (out / "controls.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
            raise SystemExit("the unmutated baseline is not green: no mutation is judged against it")

    for i, v in enumerate(variants, 1):
        vid = variant_id(v)
        entry = {"id": vid, "row": v["row"], "named": v["named"], "controls": v["controls"], "cross": v["cross"],
                 "unmutated": v["unmutated"], "note": v["note"],
                 "edits": [{"path": e["path"], "span": e["span"], "old": e["old"], "new": e["new"]}
                           for e in v["edits"]]}
        try:
            files = mutated_files(v)
        except Exception as ex:
            entry.update(verdict="ANCHOR", notes=[f"{type(ex).__name__}: {ex}"])
            report["variants"].append(entry)
            print(f"[{i}/{len(variants)}] {vid}: ANCHOR {ex}")
            continue
        record = {"variant": vid, "files": {}}
        for path, (raw, _new, _spans) in files.items():
            copy = path.replace("/", "__")
            (aside_dir(out) / copy).write_bytes(raw)
            record["files"][path] = {"copy": copy, "sha256": sha256(raw)}
        (aside_dir(out) / "IN_PROGRESS.json").write_text(json.dumps(record), encoding="utf-8")
        entry["spans"] = {p: sp for p, (_r, _n, sp) in files.items()}
        entry["sha256_before"] = {p: sha256(raw) for p, (raw, _n, _s) in files.items()}
        entry["sha256_mutated"] = {p: sha256(new) for p, (_r, new, _s) in files.items()}
        try:
            for path, (_raw, new, _spans) in files.items():
                (ROOT / path).write_bytes(new)
            safe = re.sub(r"[^A-Za-z0-9_.-]", "_", vid)
            junit, log = out / "variants" / f"{safe}.junit.xml", out / "variants" / f"{safe}.log"
            if junit.exists():
                junit.unlink()
            code, secs = run_pytest(list(v["nodes"].values()), junit, log, args.timeout)
        finally:
            problems = restore(out, files)
        entry["restored"] = {"ok": not problems, "problems": problems,
                             "sha256_after": {p: sha256((ROOT / p).read_bytes()) for p in files}}
        if problems:
            report["variants"].append(entry)
            (out / "controls.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
            raise SystemExit(f"{vid}: restoration not proven: {problems}")
        results = parse_junit(junit)
        verdict, notes = judge(v, results, code)
        entry.update(exit=code, seconds=secs, verdict=verdict, notes=notes,
                     outcomes={n: (results[n]["outcome"] if n in results else "missing") for n in v["nodes"]},
                     red=red_excerpt(results[v["named"]]) if v["named"] in results else None,
                     control_rows={n: [ln for ln in results[n]["stdout"].split("\n") if ln.startswith("ROW")]
                                   for n in v["controls"] + v["cross"] if n in results})
        report["variants"].append(entry)
        (out / "controls.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
        first = (entry["red"] or {}).get("message", "").split("\n")[0][:150] if entry["red"] else ""
        print(f"[{i}/{len(variants)}] {vid}: {verdict} ({secs} s) {first}")
        for note in notes:
            print(f"      {note}")

    if git("rev-parse", "HEAD").stdout.strip() != head or not tree_clean():
        raise SystemExit("HEAD moved or the tree changed during the run")
    report["finished"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    (out / "controls.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    tally = {}
    for e in report["variants"]:
        tally[e["verdict"]] = tally.get(e["verdict"], 0) + 1
    met_rows = {e["row"] for e in report["variants"] if e["verdict"] == "MET"}
    all_rows = {e["row"] for e in report["variants"]}
    print(f"variants {len(report['variants'])}: {tally}")
    print(f"rows with every variant MET: {len([r for r in all_rows if all(e['verdict'] == 'MET' for e in report['variants'] if e['row'] == r)])} of {len(all_rows)}; rows with any MET: {len(met_rows)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
