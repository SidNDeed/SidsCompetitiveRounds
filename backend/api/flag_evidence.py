"""Shared anti-cheat evidence formatting for the admin API and Discord feed."""

from sqlalchemy import text


def _value(v, suffix: str = "") -> str:
    return "not recorded" if v is None else f"{v}{suffix}"


def _plain(v, limit: int = 260) -> str:
    rendered = str(v or "").replace("\r", " ").replace("\n", " ").strip()
    return rendered if len(rendered) <= limit else rendered[:limit - 1] + "..."


def _half_score(raw: str) -> str:
    value = int(raw)
    return str(value // 2) if value % 2 == 0 else f"{value // 2}.5"


def _final_score(rounds, points) -> str:
    rounds = int(rounds or 0)
    points = int(points or 0)
    # At game end the winning point can remain at 2 even though it already
    # converted into the final round. Match the client history's normalization.
    if points >= 2:
        points = 0
    return _half_score(str(rounds * 2 + points))


def _point_progress(timeline, times) -> str:
    if not timeline:
        return "Point-by-point progression not recorded by this client version."
    scores = [x.strip() for x in str(timeline).split(",") if x.strip()]
    stamps = [x.strip() for x in str(times or "").split(",")]
    out = []
    for i, score in enumerate(scores[:40]):
        stamp = stamps[i] if i < len(stamps) and stamps[i] else None
        try:
            left, right = score.split(":", 1)
            shown = f"{_half_score(left)}-{_half_score(right)}"
        except (TypeError, ValueError):
            shown = score.replace(":", "-")
        out.append(f"{stamp}s {shown}" if stamp else shown)
    return " -> ".join(out)


def _macro_windows(raw) -> str:
    if not raw:
        return "Per-second KPS/CPS windows were not recorded by this client version."
    windows = []
    for token in str(raw).split(",")[:48]:
        try:
            second, keys, clicks = (int(x) for x in token.split(":", 2))
            windows.append(f"{second}s: {keys} KPS + {clicks} CPS = {keys + clicks}/s")
        except (TypeError, ValueError):
            continue
    return "; ".join(windows) if windows else "Per-second KPS/CPS windows were malformed."


def _suspects(reason: str, details: dict, row) -> list[str]:
    if reason in ("inactive_player", "suspected_macro"):
        sid = details.get("suspect_steam") or details.get("reporter_steam")
        return [sid] if sid else []
    if reason in ("fps_dip_pattern", "low_fps_outlier", "freeze_events", "ping_gap_cluster"):
        sid = details.get("steam_id")
        return [sid] if sid else []
    if reason == "too_many_cards":
        suspects = []
        maximum = int(details.get("max_allowed") or 0)
        if int(details.get("p1_cards") or 0) > maximum:
            suspects.append(row["p1_steam_id"])
        if int(details.get("p2_cards") or 0) > maximum:
            suspects.append(row["p2_steam_id"])
        return suspects
    if reason in ("short_duration_pattern", "suspected_speedhack"):
        return [row["p1_steam_id"], row["p2_steam_id"]]
    return []


def flag_payload(row) -> dict:
    reason = row["flag_reason"]
    raw_details = row["flag_details"]
    details = raw_details if isinstance(raw_details, dict) else {
        "description": _plain(raw_details, 500)
    }
    p1_card_count = int(row["p1_card_count"] or 0)
    p2_card_count = int(row["p2_card_count"] or 0)
    p1_expected = int(row["p2_rounds_won"] or 0) + 1
    p2_expected = int(row["p1_rounds_won"] or 0) + 1
    p1_cards = _plain(row["p1_cards"] or "(none recorded)", 360)
    p2_cards = _plain(row["p2_cards"] or "(none recorded)", 360)
    score_summary = (
        f"Final score: "
        f"{_final_score(row['p1_rounds_won'], row['p1_points_total'])}-"
        f"{_final_score(row['p2_rounds_won'], row['p2_points_total'])}; "
        f"rounds {row['p1_rounds_won']}-{row['p2_rounds_won']}; "
        f"duration {_value(row['duration'], 's')}"
    )
    cards_summary = (
        f"{_plain(row['p1_name'], 64)}: {p1_card_count} pick(s), expected up to {p1_expected}: {p1_cards}\n"
        f"{_plain(row['p2_name'], 64)}: {p2_card_count} pick(s), expected up to {p2_expected}: {p2_cards}"
    )

    def side_telemetry(prefix, name):
        keys = row[f"{prefix}_keys_pressed"]
        active = row[f"{prefix}_active_seconds"]
        avg_rate = (
            f"{float(keys) / float(active):.2f}/s"
            if keys is not None and active is not None and float(active) > 0 else "not recorded"
        )
        return (
            f"{_plain(name, 64)}: shots {_value(row[f'{prefix}_bullets_hit'])}/"
            f"{_value(row[f'{prefix}_bullets_fired'])} hit/fired; blocks "
            f"{_value(row[f'{prefix}_blocks_successful'])}/"
            f"{_value(row[f'{prefix}_blocks_activated'])} successful/activated; "
            f"gameplay events {_value(keys)} over {_value(active, 's')} ({avg_rate}); "
            f"FPS avg {_value(row[f'{prefix}_fps_avg'])}, timeline "
            f"{_plain(row[f'{prefix}_fps_timeline'] or 'not recorded', 220)}"
        )

    def side_connection(prefix, name):
        return (
            f"{_plain(name, 64)}: ping avg/max {_value(row[f'{prefix}_ping_avg'])}/"
            f"{_value(row[f'{prefix}_ping_max'])}ms, timeline "
            f"{_plain(row[f'{prefix}_ping_timeline'] or 'not recorded', 180)}; "
            f"freezes {_value(row[f'{prefix}_freeze_count'])} "
            f"({_value(row[f'{prefix}_freeze_focused_count'])} focused, "
            f"{_value(row[f'{prefix}_freeze_total_sec'], 's')} total); "
            f"recv/hb gaps {_value(row[f'{prefix}_recv_gap_count'])}/"
            f"{_value(row[f'{prefix}_hb_gap_count'])}, max recv "
            f"{_value(row[f'{prefix}_recv_gap_max_ms'], 'ms')}"
        )

    if reason == "too_many_cards":
        evidence = (
            f"Card counts were {p1_card_count}/{p2_card_count}; detector limit "
            f"{details.get('max_allowed', 'not recorded')}. Compare the actual picks below."
        )
    elif reason == "short_duration_pattern":
        prior = details.get("prior_match_ids") or []
        if not isinstance(prior, list):
            prior = []
        related_ids = prior or (
            [details.get("triggered_by_match")]
            if details.get("triggered_by_match") else []
        )
        related = ", ".join(
            str(x).replace("-", "")[:12].upper() for x in related_ids
        ) or "not recorded"
        related_context = row["related_match_context"] or []
        related_lines = []
        if isinstance(related_context, list):
            for item in related_context[:12]:
                if not isinstance(item, dict):
                    continue
                code = str(item.get("id") or "").replace("-", "")[:12].upper()
                ended = str(item.get("ended_at") or "time not recorded")
                invalid = (
                    f"; invalidated ({item.get('invalidation_reason') or 'reason not recorded'})"
                    if item.get("invalidated") else ""
                )
                related_lines.append(
                    f"{code}: {_plain(item.get('p1_name'), 40)} vs "
                    f"{_plain(item.get('p2_name'), 40)}; "
                    f"{item.get('p1_rounds', 0)}-{item.get('p2_rounds', 0)} rounds; "
                    f"{_value(item.get('duration'), 's')}; "
                    f"{item.get('p1_cards', 0)}/{item.get('p2_cards', 0)} cards; "
                    f"{ended}{invalid}"
                )
        context_text = (
            "\nContributing matches:\n" + "\n".join(related_lines)
            if related_lines else
            "\nContributing-match details were not retained for this legacy flag."
        )
        if details.get("retroactive"):
            evidence = (
                f"This {_value(details.get('duration_seconds', row['duration']), 's')} "
                f"match was retroactively included when game "
                f"{str(details.get('triggered_by_match') or '').replace('-', '')[:12].upper()} "
                f"completed the short-duration pattern.{context_text}"
            )
        else:
            evidence = (
                f"{_value(details.get('duration_seconds', row['duration']), 's')} match plus "
                f"{len(prior)} prior sub-60s match(es) inside "
                f"{details.get('window_hours', 2)}h. "
                f"Related game codes: {related}{context_text}"
            )
    elif reason == "inactive_player":
        evidence = (
            f"Reporter {details.get('reporter_steam', 'not recorded')} recorded "
            f"{details.get('shots', 0)} shots, {details.get('blocks', 0)} blocks, "
            f"{details.get('cards_picked', 0)} cards. Check event coverage and opponent activity below."
        )
    elif reason == "suspected_macro":
        peak_kps = details.get("peak_keys_per_second", row["local_macro_peak_kps"])
        peak_cps = details.get("peak_clicks_per_second", row["local_macro_peak_cps"])
        peak_eps = details.get("peak_events_per_second", row["local_macro_peak_eps"])
        suspect = details.get("suspect_steam") or details.get("reporter_steam") or "not recorded"
        windows = details.get("suspect_windows") or row["local_macro_timeline"]
        legacy_note = ""
        if not windows and details.get("macro_suspect_seconds"):
            legacy_note = (
                " Legacy telemetry proves every counted one-second window met the "
                f"{details.get('threshold_events_per_second', 25)} events/s threshold, "
                "but did not retain its KPS/CPS split or the individual rates. "
                "Treat that aggregate as suspicious context, not enough by itself "
                "for a confirmed-cheating verdict."
            )
        evidence = (
            f"Suspect {suspect} ({details.get('evidence_source', 'reporter-side sampler')}): "
            f"{details.get('macro_suspect_seconds', row['local_macro_suspect_seconds'])} suspect second(s), "
            f"threshold {details.get('threshold_events_per_second', 25)} events/s; "
            f"peaks KPS/CPS/total = {_value(peak_kps)}/{_value(peak_cps)}/{_value(peak_eps)}. "
            "A suspect second is one active-combat bucket with at least that many "
            "new WASD/arrow/space/mouse-down presses; holding a key does not repeat-count. "
            f"Windows: {_macro_windows(windows)}{legacy_note}"
        )
    elif reason == "fps_dip_pattern":
        evidence = (
            f"Suspect {details.get('steam_id', 'not recorded')}: median "
            f"{details.get('median', 'not recorded')} FPS with {details.get('dip_buckets', 'not recorded')} "
            f"dip buckets; values {_plain(details.get('dip_values'), 200)}."
        )
    elif reason == "low_fps_outlier":
        evidence = (
            f"Suspect {details.get('steam_id', 'not recorded')}: this match "
            f"{details.get('fps_avg', 'not recorded')} FPS vs own baseline median "
            f"{details.get('baseline_median', 'not recorded')} across "
            f"{details.get('baseline_points', 'not recorded')} match(es)."
        )
    elif reason == "freeze_events":
        evidence = (
            f"Suspect {details.get('steam_id', 'not recorded')}: "
            f"{details.get('freeze_count', 'not recorded')} freezes, "
            f"{details.get('freeze_focused_count', 'not recorded')} focused, "
            f"{details.get('freeze_total_sec', 'not recorded')}s total."
        )
    elif reason == "ping_gap_cluster":
        evidence = (
            f"Suspect {details.get('steam_id', 'not recorded')}; signal "
            f"{details.get('signal', 'not recorded')}. recv gaps/max "
            f"{details.get('recv_gap_count', 'not recorded')}/"
            f"{details.get('recv_gap_max_ms', 'not recorded')}ms vs baseline "
            f"{details.get('baseline_median', 'not recorded')}; heartbeat gaps "
            f"{details.get('hb_gap_count', 'not recorded')} vs baseline "
            f"{details.get('hb_baseline_median', 'not recorded')}."
        )
    elif reason == "suspected_speedhack":
        related_context = row["related_match_context"] or []
        observed_lines = []
        if isinstance(related_context, list):
            for item in related_context[:12]:
                if not isinstance(item, dict):
                    continue
                observed_lines.append(
                    f"{str(item.get('id') or '').replace('-', '')[:12].upper()}: "
                    f"{_value(item.get('duration'), 's')}, "
                    f"{item.get('p1_rounds', 0)}-{item.get('p2_rounds', 0)} rounds, "
                    f"ended {item.get('ended_at') or 'not recorded'}"
                )
        evidence = _plain(details.get("description") or details, 700)
        if observed_lines:
            evidence += "\nServer timing context (baseline first):\n" + "\n".join(observed_lines)
    else:
        evidence = _plain(details, 700)

    suspects = _suspects(reason, details, row)
    match_id = str(row["match_id"])
    return {
        "id": str(row["id"]),
        "discord_evidence_revision": int(row["discord_evidence_revision"]),
        "match_id": match_id,
        "game_code": match_id.replace("-", "")[:12].upper(),
        "series_id": str(row["context_series_id"]) if row["context_series_id"] else None,
        "flag_reason": reason,
        "flag_details": raw_details,
        "auto_invalidated": bool(row["auto_invalidated"]),
        "match_invalidated": row["invalidated_at"] is not None,
        "match_invalidation_reason": row["invalidation_reason"],
        "restoration_required": bool(row["restoration_required"]),
        "player_steam_ids": [row["p1_steam_id"], row["p2_steam_id"]],
        "p1_steam_id": row["p1_steam_id"], "p2_steam_id": row["p2_steam_id"],
        "suspect_steam_ids": suspects,
        "suspect_steam_text": ", ".join(suspects) if suspects else "not attributable",
        "p1_name": row["p1_name"], "p2_name": row["p2_name"],
        "is_ranked": bool(row["is_ranked"]),
        "duration_seconds": row["duration"],
        "duration_text": _value(row["duration"], "s"),
        "score_summary": score_summary,
        "cards_summary": cards_summary,
        "point_progress": _point_progress(row["point_timeline"], row["point_times"]),
        "evidence_summary": evidence,
        "telemetry_summary": (
            side_telemetry("p1", row["p1_name"]) + "\n"
            + side_telemetry("p2", row["p2_name"])
        ),
        "connection_summary": (
            side_connection("p1", row["p1_name"]) + "\n"
            + side_connection("p2", row["p2_name"])
        ),
        "match_context": (
            f"Reporter {_plain(row['reporter_name'], 64)} [{row['reporter_steam_id'] or 'not recorded'}]; "
            f"mod {row['reporter_mod_version'] or 'not recorded'}; game {row['game_version'] or 'not recorded'}; "
            f"region {row['region'] or 'not recorded'}; room {_plain(row['photon_room_id'] or 'not recorded', 80)}"
        ),
        "reviewed_at": row["reviewed_at"].isoformat() if row["reviewed_at"] else None,
        "review_action": row["review_action"],
        "created_at": row["created_at"].isoformat() if row["created_at"] else None,
    }


async def fetch_flag_context_rows(
    db, where_sql: str, params: dict, order_sql: str,
    limit: int, offset: int | None = None,
):
    """Fetch complete 1v1 evidence. SQL fragments are fixed by callers."""
    query_params = dict(params)
    query_params["limit"] = limit
    page_sql = " LIMIT :limit"
    if offset is not None:
        query_params["offset"] = offset
        page_sql += " OFFSET :offset"
    rows = (await db.execute(text(f"""
        SELECT fm.id, fm.match_id, fm.discord_evidence_revision,
               COALESCE(fm.series_id, m.series_id) AS context_series_id,
               fm.flag_reason, fm.flag_details, fm.auto_invalidated, fm.reviewed_at,
               fm.review_action, fm.restoration_required, fm.created_at,
               m.is_ranked, m.invalidated_at, m.invalidation_reason,
               COALESCE(m.duration_seconds, m.match_duration) AS duration,
               m.p1_rounds_won, m.p2_rounds_won, m.p1_points_total, m.p2_points_total,
               m.point_timeline, m.point_times, m.reporter_mod_version, m.game_version,
               m.region, m.photon_room_id, m.local_macro_suspect_seconds,
               m.local_macro_peak_kps, m.local_macro_peak_cps, m.local_macro_peak_eps,
               m.local_macro_timeline,
               m.p1_bullets_fired, m.p1_bullets_hit, m.p1_blocks_activated,
               m.p1_blocks_successful, m.p1_keys_pressed, m.p1_active_seconds,
               m.p2_bullets_fired, m.p2_bullets_hit, m.p2_blocks_activated,
               m.p2_blocks_successful, m.p2_keys_pressed, m.p2_active_seconds,
               m.p1_fps_avg, m.p2_fps_avg, m.p1_fps_timeline, m.p2_fps_timeline,
               m.p1_ping_avg, m.p2_ping_avg, m.p1_ping_max, m.p2_ping_max,
               m.p1_ping_timeline, m.p2_ping_timeline,
               m.p1_freeze_count, m.p2_freeze_count,
               m.p1_freeze_focused_count, m.p2_freeze_focused_count,
               m.p1_freeze_total_sec, m.p2_freeze_total_sec,
               m.p1_recv_gap_count, m.p2_recv_gap_count,
               m.p1_recv_gap_max_ms, m.p2_recv_gap_max_ms,
               m.p1_hb_gap_count, m.p2_hb_gap_count,
               (
                   SELECT jsonb_agg(
                       jsonb_build_object(
                           'id', related.id,
                           'duration', COALESCE(related.duration_seconds, related.match_duration),
                           'p1_rounds', related.p1_rounds_won,
                           'p2_rounds', related.p2_rounds_won,
                           'p1_name', rp1.display_name,
                           'p2_name', rp2.display_name,
                           'p1_cards', (
                               SELECT COUNT(*) FROM match_cards rmc
                               WHERE rmc.match_id = related.id
                                 AND rmc.player_id = related.player1_id
                           ),
                           'p2_cards', (
                               SELECT COUNT(*) FROM match_cards rmc
                               WHERE rmc.match_id = related.id
                                 AND rmc.player_id = related.player2_id
                           ),
                           'ended_at', related.ended_at,
                           'invalidated', related.invalidated_at IS NOT NULL,
                           'invalidation_reason', related.invalidation_reason
                       )
                       ORDER BY related.ended_at, related.id
                   )
                   FROM matches related
                   JOIN players rp1 ON rp1.id = related.player1_id
                   JOIN players rp2 ON rp2.id = related.player2_id
                   WHERE related.id::text IN (
                       SELECT jsonb_array_elements_text(
                           CASE
                               WHEN jsonb_typeof(fm.flag_details->'prior_match_ids') = 'array'
                                   THEN fm.flag_details->'prior_match_ids'
                               WHEN jsonb_typeof(fm.flag_details->'related_match_ids') = 'array'
                                   THEN fm.flag_details->'related_match_ids'
                               WHEN jsonb_typeof(fm.flag_details->'observed_match_ids') = 'array'
                                   THEN fm.flag_details->'observed_match_ids'
                               WHEN fm.flag_details ? 'triggered_by_match'
                                   THEN jsonb_build_array(
                                       fm.flag_details->>'triggered_by_match'
                                   )
                               ELSE '[]'::jsonb
                           END
                       )
                   )
               ) AS related_match_context,
               p1.steam_id AS p1_steam_id, p1.display_name AS p1_name,
               p2.steam_id AS p2_steam_id, p2.display_name AS p2_name,
               reporter.steam_id AS reporter_steam_id, reporter.display_name AS reporter_name,
               (SELECT COUNT(*) FROM match_cards mc
                 WHERE mc.match_id = m.id AND mc.player_id = m.player1_id) AS p1_card_count,
               (SELECT COUNT(*) FROM match_cards mc
                 WHERE mc.match_id = m.id AND mc.player_id = m.player2_id) AS p2_card_count,
               (SELECT string_agg(mc.card_name, ', ' ORDER BY mc.round_number, mc.pick_order)
                  FROM match_cards mc
                 WHERE mc.match_id = m.id AND mc.player_id = m.player1_id) AS p1_cards,
               (SELECT string_agg(mc.card_name, ', ' ORDER BY mc.round_number, mc.pick_order)
                  FROM match_cards mc
                 WHERE mc.match_id = m.id AND mc.player_id = m.player2_id) AS p2_cards
          FROM flagged_matches fm
          JOIN matches m ON m.id = fm.match_id
          JOIN players p1 ON p1.id = m.player1_id
          JOIN players p2 ON p2.id = m.player2_id
          LEFT JOIN players reporter ON reporter.id = m.reported_by
         WHERE {where_sql}
         ORDER BY {order_sql}{page_sql}
    """), query_params)).mappings().all()
    return rows
