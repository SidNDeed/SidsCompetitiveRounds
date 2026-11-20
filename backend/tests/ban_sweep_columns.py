"""Bans part 2a (FIX-3 section 1, class II): the typed census of the columns
of the LIVE tables that can name an account.

The key set is the test database's catalog: for every table that
ban_sweep_tables.TABLE_CLASSES classes LIVE, every column of type uuid and
every column whose name contains "steam" (catalog_key_set). Each stands in
exactly one of ACCOUNT_COLUMNS (it names an account) or NOT_AN_ACCOUNT (typed
with what it holds); test_ban_sweep_live_census_pg checks both directions
against the catalog.

Each ACCOUNT_COLUMNS entry carries one disposition per account state:
  HAS   the account has a players row;
  NONE  the account has no players row (only for a column that holds a steam
        id; a uuid column names a players.id and has no such state).
A disposition is (END, why) -- the void ends the row -- or (STAND, why) -- the
row stays by a rule, the reason typed -- or, for NONE only, (NO_ROW, why): the
table cannot hold a row for an account without a players row (a NOT NULL
reference to players in the same row), checked against the catalog.
"""
END, STAND, NO_ROW = "END", "STAND", "NO_ROW"

_BETTOR_STAND = (STAND, "a wager the account placed before the ban on a game of other accounts is decided by "
                        "that game's result alone; the ban ends the account's own play and its own records, "
                        "not its stake in a game it does not play (ruling of FIX-3 1.3); its wager on a "
                        "record the ban ends is refused with the record (END through the record)")
_MEMBER_END = (END, "a member of the record: the void ends the record (the record's live status leaves)")
_QUEUE_END = (END, "the account's own queue row or lobby seat: the void deletes it")
_QUEUE_NONE = (NO_ROW, "the queue row's player_id is a NOT NULL reference to players")
_KICKED_STAND = (STAND, "a lobby of other accounts that once kicked this one: BAN-R21, a lobby is not ended "
                        "for its other members because one member was banned, and its rows equal a twin "
                        "lobby's whose member left by the leave route, which keeps the kicked list")

ACCOUNT_COLUMNS = {
    ("bets", "player_id"): {"HAS": _BETTOR_STAND},
    ("bets", "bet_on_player_id"): {"HAS": (END, "a wager on the banned account's own series: the void ends "
                                                "the series and refunds its unsettled wagers")},
    ("ffa_bets", "player_id"): {"HAS": _BETTOR_STAND},
    ("ffa_bets", "bet_on_player_id"): {"HAS": (END, "a wager on the banned account in its own FFA lobby: "
                                                    "the void ends the lobby and refunds its wagers")},
    ("team_bets", "player_id"): {"HAS": _BETTOR_STAND},
    ("lobby_bets", "player_id"): {"HAS": (END, "the account's own lobby-phase wager on a lobby it leaves is "
                                               "refunded (BAN-R21)")},
    ("lobby_bets", "target_steams"): {"HAS": (STAND, "another account's lobby-phase wager naming this one, "
                                                     "on a lobby that stays: BAN-R21's twin rule (the leave "
                                                     "route keeps the other members' wagers)"),
                                      "NONE": (STAND, "as with a players row: the wager is another account's")},
    ("ffa_lobbies", "host_player_id"): {"HAS": (END, "the open lobby the account hosts: the host passes or the "
                                                     "lobby is disbanded (BAN-R21); a live lobby is ended")},
    ("ffa_lobbies", "first_leaver"): {"HAS": _MEMBER_END},
    ("ffa_lobbies", "kicked_steam_ids"): {"HAS": _KICKED_STAND, "NONE": _KICKED_STAND},
    ("team_lobbies", "host_player_id"): {"HAS": (END, "as ffa_lobbies.host_player_id (BAN-R21)")},
    ("team_lobbies", "kicked_steam_ids"): {"HAS": _KICKED_STAND, "NONE": _KICKED_STAND},
    ("ovt_lobbies", "host_player_id"): {"HAS": (END, "as ffa_lobbies.host_player_id (BAN-R21)")},
    ("ovt_lobbies", "kicked_steam_ids"): {"HAS": _KICKED_STAND, "NONE": _KICKED_STAND},
    ("ffa_queue", "player_id"): {"HAS": _QUEUE_END},
    ("ffa_queue", "steam_id"): {"HAS": _QUEUE_END, "NONE": _QUEUE_NONE},
    ("team_queue", "player_id"): {"HAS": _QUEUE_END},
    ("team_queue", "steam_id"): {"HAS": _QUEUE_END, "NONE": _QUEUE_NONE},
    ("ovt_queue", "player_id"): {"HAS": _QUEUE_END},
    ("ovt_queue", "steam_id"): {"HAS": _QUEUE_END, "NONE": _QUEUE_NONE},
    ("ranked_queue", "player_id"): {"HAS": _QUEUE_END},
    ("ranked_queue", "steam_id"): {"HAS": _QUEUE_END, "NONE": _QUEUE_NONE},
    ("ranked_queue", "matched_with"): {"HAS": (END, "a partner's row matched with the banned account: the "
                                                    "void ends it with the pairing")},
    ("lobby_invites", "sender_player_id"): {"HAS": (END, "invites the account sent (BAN-R21)")},
    ("lobby_invites", "invitee_player_id"): {"HAS": (END, "invites the account holds (BAN-R21)")},
    ("match_seat_holds", "player_id"): {"HAS": _MEMBER_END},
    ("match_seat_holds", "opener_player_id"): {"HAS": _MEMBER_END},
    ("ranked_series", "player1_id"): {"HAS": _MEMBER_END},
    ("ranked_series", "player2_id"): {"HAS": _MEMBER_END},
    ("ranked_series", "winner_id"): {"HAS": (END, "set only on a terminal series; on a live one the account "
                                                  "is a member and the void ends it")},
    ("team_series", "t1a_id"): {"HAS": _MEMBER_END},
    ("team_series", "t1b_id"): {"HAS": _MEMBER_END},
    ("team_series", "t2a_id"): {"HAS": _MEMBER_END},
    ("team_series", "t2b_id"): {"HAS": _MEMBER_END},
    ("team_series", "dc_player_id"): {"HAS": _MEMBER_END},
    ("team_series", "dc_fallback_player_id"): {"HAS": _MEMBER_END},
    ("ovt_series", "solo_id"): {"HAS": _MEMBER_END},
    ("ovt_series", "duo_a_id"): {"HAS": _MEMBER_END},
    ("ovt_series", "duo_b_id"): {"HAS": _MEMBER_END},
    ("ovt_series", "dc_player_id"): {"HAS": _MEMBER_END},
    ("pc_delivery_leases", "subject_id"): {"HAS": (END, "a card delivery lease of the account: revoked")},
    ("queue_leases", "player_id"): {"HAS": (END, "the account's queue leases: deleted")},
    ("spectate_leases", "spectator_steam_id"): {"HAS": (END, "the spectate leave of every live lease (F2 d)"),
                                                "NONE": (END, "the same, outside the players-row block")},
    ("steam_sessions", "steam_id"): {"HAS": (END, "the account's sessions: deleted"),
                                     "NONE": (END, "the same: keyed on the steam id")},
    ("i18n_portal_sessions", "steam_id"): {"HAS": (END, "the account's portal tokens: deleted"),
                                           "NONE": (END, "the same: keyed on the steam id")},
    ("lfp_pings", "steam_id"): {"HAS": (END, "the account's queued looking-for-players post: deleted"),
                                "NONE": (END, "the same: keyed on the steam id")},
}

NOT_AN_ACCOUNT = {
    ("bets", "series_id"): "the record (a 1v1 series) the wager is on",
    ("ffa_bets", "id"): "the row's own key",
    ("ffa_bets", "lobby_id"): "the record (an FFA lobby) the wager is on",
    ("team_bets", "team_series_id"): "the record (a 2v2 series) the wager is on",
    ("lobby_bets", "id"): "the row's own key",
    ("lobby_bets", "lobby_id"): "the lobby the wager is on",
    ("lobby_bets", "bound_bet_id"): "the id of the record wager this lobby wager became",
    ("ffa_lobbies", "id"): "the row's own key",
    ("ffa_lobbies", "reformed_from"): "a record id: the lobby this one was reformed from",
    ("ffa_lobbies", "reformed_to"): "a record id: the lobby this one was reformed into",
    ("team_lobbies", "id"): "the row's own key",
    ("team_lobbies", "series_id"): "a record id: the series the lobby started",
    ("ovt_lobbies", "id"): "the row's own key",
    ("ovt_lobbies", "series_id"): "a record id: the series the lobby started",
    ("ffa_queue", "series_id"): "a record id: the lobby of the seat",
    ("ffa_queue", "held_lobby"): "a record id: the lobby the row is held for",
    ("team_queue", "series_id"): "a record id: the series or lobby of the row",
    ("ovt_queue", "series_id"): "a record id: the series or lobby of the row",
    ("lobby_invites", "id"): "the row's own key",
    ("lobby_invites", "lobby_id"): "the lobby the invite is to",
    ("lobby_invites", "mail_message_id"): "a message id: the mail that carried the invite",
    ("match_seat_holds", "id"): "the row's own key",
    ("match_seat_holds", "series_id"): "a record id: the series the hold is on",
    ("match_seat_holds", "game_id"): "a record id: the game the hold is on",
    ("ranked_series", "id"): "the row's own key",
    ("ranked_series", "tournament_id"): "a record id: the tournament",
    ("team_series", "id"): "the row's own key",
    ("ovt_series", "id"): "the row's own key",
    ("pc_delivery_leases", "id"): "the row's own key",
    ("pc_delivery_leases", "print_id"): "a record id: the card print delivered",
    ("queue_leases", "group_id"): "a record id: the pair or group the lease is for",
    ("queue_leases", "generation"): "a token: the lease's generation",
    ("spectate_leases", "id"): "the row's own key",
    ("spectate_leases", "game_id"): "a record id: the spectated game",
}


def catalog_key_set(columns, live_tables):
    """{(table, column)} from catalog rows (table, column, data_type): every
    uuid column and every column whose name contains 'steam', of a LIVE table."""
    return {(t, c) for t, c, ty in columns
            if t in live_tables and (ty == "uuid" or "steam" in c)}


def census_failures(keys, account=None, not_account=None):
    account = ACCOUNT_COLUMNS if account is None else account
    not_account = NOT_AN_ACCOUNT if not_account is None else not_account
    out = []
    both = set(account) & set(not_account)
    out += [f"{k}: typed both as an account and not" for k in sorted(both)]
    typed = set(account) | set(not_account)
    out += [f"{k}: in the catalog and typed in neither table" for k in sorted(keys - typed)]
    out += [f"{k}: typed and not in the catalog" for k in sorted(typed - keys)]
    for k, states in sorted(account.items()):
        steam = "steam" in k[1]
        want = {"HAS", "NONE"} if steam else {"HAS"}
        if set(states) != want:
            out.append(f"{k}: states {sorted(states)}, want {sorted(want)}")
        for st, (disp, why) in states.items():
            if disp not in (END, STAND, NO_ROW) or (disp == NO_ROW and st != "NONE") or not why.strip():
                out.append(f"{k}: {st} disposition {disp!r} is not typed with a reason")
    return out
