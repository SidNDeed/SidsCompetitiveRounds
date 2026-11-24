"""The moderator log's vocabulary (work order MODLOG-1).

One closed set of action words, each with the plain label the read shows,
and the one plain sentence the server builds for a record from its details.
Every admin_actions row is written by main._modlog_write, which refuses a
word that is not in ACTIONS; the read (GET /api/v1/admin/modlog and its
internal twin) refuses a filter word that is not in ACTIONS with 400, and
labels a stored word that is not in it (a row older than this list) as
"Other (<word>)".

Pure: no database, no import of main. The bot image does not copy this file;
the bot shows the label and the sentence the api answers.
"""
from __future__ import annotations

from datetime import datetime, timezone

# word -> plain label. The words are exactly the ones the code writes, plus
# the legacy word migration 028's comment names (reverse_match).
ACTIONS: dict[str, str] = {
    # Bans
    "ban": "Ban",
    "ban_length": "Ban length changed",
    "ban_repeat": "Repeat ban",
    "ban_rate_blocked": "Ban refused by the rate limit",
    "ban_details": "Ban details changed",
    "unban": "Unban",
    # Chat
    "chat_mute": "Chat mute",
    "chat_automute": "Automatic chat mute",
    "chat_mute_msg": "Chat mute from a message",
    "chat_unmute": "Chat unmute",
    "chat_unmute_bridge": "Bridge unmute",
    "chat_delete": "Chat message deleted",
    "chat_purge_user": "Platform user's messages removed",
    "chat_purge_channel": "Platform channel cleared",
    "chat_lockdown": "Chat lockdown",
    "chat_spam_pattern": "Spam pattern changed",
    # Mail
    "modcase_act": "Mail case closed",
    "mail_broadcast": "Mail broadcast",
    "mail_bulk_grant": "Mail bulk-send grant",
    "mail_bulk_grant_revoke": "Mail bulk-send grant revoked",
    # Results
    "grant_achievement": "Achievement granted",
    "reverse_series": "1v1 series reversed",
    "reverse_match": "Match reversed",
    "resolve_team_series": "2v2 series resolved",
    "reverse_team_series": "2v2 series reversed",
    "team_glicko_rebuild": "2v2 ratings rebuilt",
    "flag_review": "Flagged match reviewed",
    "flag_restoration_completed": "Flag restoration completed",
    "record_exclude": "Record excluded",
    "quarantine_accept": "Held report accepted",
    "quarantine_discard": "Held report discarded",
    "quarantine_credit": "Held report credited",
    # Player Cards, cosmetics, roles
    "pc_trade_reverse": "Card trade reversed",
    "pc_portrait_clear": "Portrait cleared",
    "pc_snapshot": "Card pool snapshot",
    "ffa_g3_seat": "FFA seat enrolment",
    "artist-set": "Artist role changed",
    "item-artist": "Shop item artist set",
    "cosmetic-approve": "Cosmetic approved",
    "cosmetic-deny": "Cosmetic denied",
    "cosmetic-placement-approve": "Cosmetic placement approved",
    "cosmetic-placement-deny": "Cosmetic placement denied",
    "i18n_grant": "Language grant changed",
    # Operations
    "alert_create": "Alert posted",
    "alert_revoke": "Alert withdrawn",
    "operator_key_issue": "Operator key issued",
    "operator_key_revoke": "Operator key revoked",
    "read_gate_mode": "Read gate mode set",
    # Reads (not actions on a player; left out of the log unless asked for)
    "evidence_report": "Evidence report read",
}

# Rows that record a READ, not an action: the read leaves them out unless the
# caller asks for them (include_reads, or the word in its action filter).
READ_ACTIONS = frozenset({"evidence_report"})

# The words whose records name no player (affected_steam_ids '{}'): a change
# to the server or its content, a refused action, a rule-chosen or long list
# (its count is in details), or a platform user's id that is not a Steam id.
# Migration 420's fill of the old rows leaves these out by the same list.
NAMES_NONE = frozenset({
    "alert_create", "alert_revoke", "ban_rate_blocked", "chat_lockdown",
    "chat_purge_channel", "chat_purge_user", "chat_spam_pattern", "chat_unmute_bridge", "item-artist",
    "mail_broadcast", "operator_key_issue", "operator_key_revoke", "pc_snapshot",
    "read_gate_mode", "team_glicko_rebuild",
})

# The actor word for a caller proven by the internal key alone (no person).
ACTOR_INTERNAL_KEY = "internal_key"

MAX_WORD = 32
MAX_REASON = 256
assert all(1 <= len(w) <= MAX_WORD for w in ACTIONS)
assert READ_ACTIONS <= set(ACTIONS)
assert NAMES_NONE <= set(ACTIONS)


def label(word: str) -> str:
    """The plain label of a stored word; a word outside the list is shown as
    it is stored, marked as such."""
    return ACTIONS.get(word) or f"Other ({word})"


def labels_matching(q: str) -> list[str]:
    """The words whose label contains q, case-insensitively (the search's
    label arm: matched here, bound as a list, never built into a statement)."""
    needle = (q or "").casefold()
    if not needle:
        return []
    return sorted(w for w, lab in ACTIONS.items() if needle in lab.casefold())


def _num(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def duration_text(minutes) -> str:
    """'7 days', '1 hour', '90 minutes'."""
    m = _num(minutes)
    if m is None or m <= 0:
        return ""
    if m % 1440 == 0:
        n, unit = m // 1440, "day"
    elif m % 60 == 0:
        n, unit = m // 60, "hour"
    else:
        n, unit = m, "minute"
    return f"{n} {unit}" + ("" if n == 1 else "s")


def when_text(iso) -> str:
    """'23 Nov 2026 09:12 UTC' from an ISO 8601 string or a datetime."""
    if iso is None or iso == "":
        return ""
    try:
        if isinstance(iso, datetime):
            dt = iso
        else:
            dt = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        dt = dt.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return ""
    return f"{dt.day} {dt.strftime('%b %Y %H:%M')} UTC"


def _plural(n, one, many=None) -> str:
    return f"{n} {one if n == 1 else (many or one + 's')}"


def _scope(channel) -> str:
    if channel in (None, "", "ALL"):
        return "all channels"
    if isinstance(channel, list):
        return "the " + ", ".join(str(c) for c in channel) + " channels"
    return f"the {channel} channel"


def _end_text(d, key) -> str:
    """A ban end for the length-change sentence: its time, 'permanent' when
    the record stores the key with no end, 'not recorded' when it lacks it."""
    if key not in d:
        return "not recorded"
    return when_text(d.get(key)) or "permanent"


def part_text(details) -> str:
    """For one record of an action recorded in parts (more players than one
    record names): 'Part 1 of 2 of one action on 17 players.'; else ''."""
    d = details if isinstance(details, dict) else {}
    part, parts, total = _num(d.get("batch_part")), _num(d.get("batch_parts")), _num(d.get("affected_total"))
    if not d.get("batch") or part is None or parts is None:
        return ""
    on = f" on {_plural(total, 'player')}" if total is not None else ""
    return f"Part {part} of {parts} of one action{on}."


# A record carried in by a migration from another table's own data, not
# written when the action was taken: its details name the source table in
# `carried_from` (migration 420 writes flag_review records for reviewed flags
# that no record named, with carried_from = 'flagged_matches'). The read says
# so in plain words beside the record's sentence.
CARRIED_FROM = {
    "flagged_matches": ("This record was carried in from the flagged match's own review data; "
                        "it was not written at the time of the review."),
}
CARRIED_OTHER = ("This record was carried in from stored data; "
                 "it was not written at the time of the action.")


def carried_text(details) -> str:
    """The plain words for a carried-in record (see CARRIED_FROM); '' for a
    record written at the time of its action."""
    src = (details if isinstance(details, dict) else {}).get("carried_from")
    if not src:
        return ""
    return CARRIED_FROM.get(str(src), CARRIED_OTHER)


def sentence(word: str, details, reason=None, *, ended=None) -> str:
    """ONE plain sentence saying what was done, with its numbers, built only
    from the stored row (a key a row lacks is left out of the sentence); for
    a carried-in record, that it was carried in (carried_text); and for a
    record that is one part of an action, which part. `ended` is the
    read's answer for a record that starts a run in steps (the 2v2 rebuild):
    True when the run's end is recorded, False when it is not, None when
    the read did not look."""
    out = [_sentence(word, details, ended)]
    carried = carried_text(details)
    if carried:
        out.append(carried)
    unlinked = _num((details if isinstance(details, dict) else {}).get("unlinked_discord_authors"))
    if unlinked:
        out.append("The Discord author had no linked game account." if unlinked == 1 else
                   f"{unlinked} Discord authors had no linked game account.")
    part = part_text(details)
    if part:
        out.append(part)
    return " ".join(out)


def _sentence(word: str, details, ended=None) -> str:
    d = details if isinstance(details, dict) else {}
    if word == "ban":
        dur = duration_text(d.get("duration_minutes"))
        until = when_text(d.get("expires_at"))
        if dur and until:
            return f"Banned for {dur}, until {until}."
        if until:
            return f"Banned until {until}."
        if dur:
            return f"Banned for {dur}."
        # Permanent only when the record says so (MODLOG-1 fix A8): a record
        # that stores no length is read as not recorded, never as permanent.
        if d.get("permanent") is True:
            return "Banned permanently."
        return "Banned (length not recorded)."
    if word == "ban_length":
        if "old_expires_at" not in d and "new_expires_at" not in d:
            return "Ban length changed (lengths not recorded)."
        old = _end_text(d, "old_expires_at")
        new = _end_text(d, "new_expires_at")
        return f"Ban length changed from {old} to {new}."
    if word == "ban_repeat":
        return "Banned again while already banned: sessions and queue places cleared again."
    if word == "ban_rate_blocked":
        n = _num(d.get("recent_bans"))
        return (f"Ban refused: {n} bans already in 5 minutes." if n is not None
                else "Ban refused by the rate limit.")
    if word == "ban_details":
        # Which texts changed and how (main.admin_ban_details); never the texts.
        said = [f"{what} {d.get(key)}" for key, what in (("details_change", "details"),
                                                         ("name_change", "kept name"))
                if d.get(key) in ("added", "changed", "cleared")]
        out = ("Ban " + " and ".join(said) + ".") if said else "Ban details changed (what changed not recorded)."
        if d.get("texts_removed") is True:
            out += " Its texts were removed when the account was deleted."
        return out
    if word == "unban":
        rows = _num(d.get("rows"))
        if rows == 0:
            return "Unban requested; there was no active ban to lift."
        return "Unbanned."
    if word in ("chat_mute", "chat_automute", "chat_mute_msg"):
        mins = d.get("duration_minutes")
        dur = duration_text(mins)
        until = when_text(d.get("expires_at"))
        span = (f"for {dur}" if dur else (f"until {until}" if until else
                                          "permanently" if d.get("permanent") is True
                                          else "(length not recorded)"))
        if word == "chat_automute":
            off = _num(d.get("offense"))
            return (f"Muted automatically in all channels {span}"
                    + (f" (offense {off})." if off else "."))
        if word == "chat_mute_msg":
            purged = _num(d.get("purged"))
            return (f"Muted from a message {span}"
                    + (f"; {_plural(purged, 'message')} removed." if purged else "."))
        return f"Muted in {_scope(d.get('channel'))} {span}."
    if word == "chat_unmute":
        n = _num(d.get("cleared"))
        return f"Unmuted ({_plural(n, 'mute')} lifted)." if n else "Unmuted."
    if word == "chat_unmute_bridge":
        return f"Lifted a {d.get('platform') or 'platform'} mute."
    if word == "chat_delete":
        ids = d.get("message_ids")
        if isinstance(ids, list) and len(ids) != 1:
            return f"Deleted {_plural(len(ids), 'chat message')}."
        chan = d.get("channel")
        return f"Deleted a chat message in {_scope(chan)}." if chan else "Deleted a chat message."
    if word == "chat_purge_user":
        out = f"Removed {_plural(_num(d.get('purged')) or 0, 'message')} of a {d.get('platform') or 'platform'} user"
        dur = duration_text(d.get("duration_minutes"))
        if d.get("muted") is False:
            return out + "; not muted."
        if d.get("permanent") is True:
            return out + "; muted permanently."
        if dur:
            return out + f"; muted for {dur}."
        return out + "; mute length not recorded."
    if word == "chat_purge_channel":
        return f"Removed {_plural(_num(d.get('purged')) or 0, 'bridged message')}."
    if word == "alert_create":
        if "expires_minutes" not in d:
            return "Alert posted."
        dur = duration_text(d.get("expires_minutes"))
        return f"Alert posted, expiring after {dur}." if dur else "Alert posted with no expiry."
    if word == "chat_lockdown":
        return "Locked chat." if d.get("locked") else "Unlocked chat."
    if word == "chat_spam_pattern":
        return "Added a spam pattern." if d.get("op") == "add" else "Revoked a spam pattern."
    if word == "modcase_act":
        act = d.get("action")
        if act == "dismiss":
            return "Dismissed a mail case."
        return f"Closed a mail case ({act})." if act else "Closed a mail case."
    if word == "mail_broadcast":
        n = _num(d.get("recipients"))
        return f"Sent a mail broadcast to {_plural(n, 'player')}." if n is not None else "Sent a mail broadcast."
    if word == "mail_bulk_grant":
        n, days = _num(d.get("max_recipients")), _num(d.get("days"))
        if n and days:
            return f"Allowed mail to {_plural(n, 'recipient')} for {_plural(days, 'day')}."
        return "Granted a mail bulk-send allowance."
    if word == "mail_bulk_grant_revoke":
        return "Revoked the mail bulk-send allowance." if d.get("revoked", True) else \
            "Revoke requested; there was no allowance."
    if word == "grant_achievement":
        key = d.get("achievement_key") or "an achievement"
        if d.get("repair"):
            return f"Re-granted {key}: its title item restored."
        gold = _num(d.get("gold_awarded"))
        return f"Granted {key}" + (f" ({gold} gold)." if gold else ".")
    if word == "reverse_series":
        n, b = _num(d.get("matches_reversed")), _num(d.get("bets_refunded"))
        out = "Reversed a 1v1 series"
        if n is not None:
            out += f": {_plural(n, 'game')} voided"
            if b:
                out += f", {_plural(b, 'bet')} refunded"
        return out + "."
    if word == "reverse_match":
        return "Reversed a match."
    if word == "resolve_team_series":
        act = d.get("action")
        if act == "complete":
            return f"Resolved a 2v2 series: team {d.get('winner_team')} wins."
        if act == "void":
            return "Voided a 2v2 series with no result."
        return "Resolved a 2v2 series."
    if word == "reverse_team_series":
        return "Reversed a 2v2 series."
    if word == "team_glicko_rebuild" and d.get("stage") == "started":
        n = _num(d.get("players_planned"))
        what = ("Started rebuilding every 2v2 rating"
                + (f" ({_plural(n, 'player')} planned)" if n is not None else ""))
        if ended is True:
            return what + "; its finish is recorded."
        if ended is False:
            return what + "; no finish was recorded."
        return what + "."
    if word == "team_glicko_rebuild":
        n = _num(d.get("series_replayed"))
        return (f"Rebuilt every 2v2 rating from {_plural(n, 'series', 'series')}." if n is not None
                else "Rebuilt every 2v2 rating.")
    if word == "flag_review":
        verdict = {"confirmed_cheat": "confirmed cheat",
                   "false_positive": "false positive"}.get(d.get("review_action"), d.get("review_action"))
        return f"Reviewed a flagged match: {verdict}." if verdict else "Reviewed a flagged match."
    if word == "flag_restoration_completed":
        return "Marked a false-positive flag's restoration done."
    if word == "record_exclude":
        board = d.get("board")
        return f"Excluded a record from the {board} board." if board else "Excluded a record."
    if word == "quarantine_accept":
        # QAPPLY-1: a record with details.applied names the game it recorded;
        # a record without it is an Accept from before that build (marked
        # only, nothing applied).
        if d.get("applied"):
            return (f"Accepted a held match report and applied it as game {_num(d.get('game'))}."
                    if _num(d.get("game")) else "Accepted a held match report and applied it.")
        return "Accepted a held match report for replay (not applied)."
    if word == "quarantine_discard":
        return "Discarded a held match report."
    if word == "quarantine_credit":
        # Two forms: the route's one record per report (details.players, by
        # Steam id) and migration 421's one record per player (top-level xp
        # and the three gold kinds).
        players = d.get("players") if isinstance(d.get("players"), dict) else {}
        rows = [v for v in players.values() if isinstance(v, dict)] if players else [d]
        xp = sum(_num(v.get("xp")) or 0 for v in rows)
        gold = sum((_num(v.get("gold")) if _num(v.get("gold")) is not None else
                    sum(_num(v.get(k)) or 0 for k in ("gold_ffa_xp", "gold_ffa_placement",
                                                      "gold_level_reward")))
                   for v in rows)
        if players:
            return (f"Credited a held match report: {_plural(len(players), 'player')} paid "
                    f"{xp} XP and {gold} gold in all, no rating moved.")
        if _num(d.get("xp")) is not None:
            return f"Credited a held match report: {xp} XP and {gold} gold, no rating moved."
        return "Credited a held match report's XP and gold, no rating moved."
    if word == "pc_trade_reverse":
        mb = d.get("moved_back") if isinstance(d.get("moved_back"), dict) else {}
        n = sum(len(v) for v in mb.values() if isinstance(v, list))
        return f"Reversed a card trade: {_plural(n, 'card')} moved back." if mb else "Reversed a card trade."
    if word == "pc_portrait_clear":
        days = _num(d.get("lock_days"))
        return (f"Cleared the portrait; uploads locked for {_plural(days, 'day')}." if days
                else "Cleared the portrait.")
    if word == "pc_snapshot":
        return "Took a card pool snapshot."
    if word == "ffa_g3_seat":
        h = _num(d.get("hours"))
        return ("Removed from the FFA seat list." if h == 0
                else f"Enrolled in the FFA seat list for {_plural(h, 'hour')}." if h
                else "Changed the FFA seat list.")
    if word == "artist-set":
        return "Granted the artist role." if d.get("grant") else "Revoked the artist role."
    if word == "item-artist":
        return f"Set the artist of shop item {d.get('sku')}." if d.get("sku") else "Set a shop item's artist."
    if word in ("cosmetic-approve", "cosmetic-placement-approve"):
        return f"Approved cosmetic {d.get('name')}." if d.get("name") else "Approved a cosmetic."
    if word in ("cosmetic-deny", "cosmetic-placement-deny"):
        return f"Denied cosmetic {d.get('name')}." if d.get("name") else "Denied a cosmetic."
    if word == "i18n_grant":
        verb = "Revoked" if d.get("action") == "revoke" else "Granted"
        scope = {"chat_moderate": "chat moderation", "translate": "translation"}.get(
            d.get("scope"), d.get("scope") or "a scope")
        lang = d.get("language_code")
        return f"{verb} {scope} for {lang}." if lang else f"{verb} {scope}."
    if word == "evidence_report":
        return "Read an evidence report."
    return f"{label(word)}."
