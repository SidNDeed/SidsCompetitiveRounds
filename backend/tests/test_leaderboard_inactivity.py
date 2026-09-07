"""Item d (Sept 6): every leaderboard hides players not seen for
LEADERBOARD_ACTIVE_DAYS days unless the caller passes include_inactive=true,
and the podium queries plus the player-stats standings apply the same
predicate so titles, the doubled bonus and "#N of M" follow the board.

Source-shape tests in the style of test_queue_ready_strict.py: they prove the
statements carry the TYPED bind (CAST(:active_days AS integer) inside
make_interval) or, for the parameter-less podium statements, the interpolated
int -- and never a string-concatenated interval (learning #448).
"""

import inspect

import main


BIND_PRED = "make_interval(days => CAST(:active_days AS integer))"
INACTIVE_COL = "NOT (p.last_seen > NOW() - " + BIND_PRED + ") AS inactive"
WHERE_TERM = ("AND ((p.last_seen > NOW() - " + BIND_PRED
              + ") OR CAST(:include_inactive AS boolean))")
DAYS_BIND = '"active_days": LEADERBOARD_ACTIVE_DAYS'
FLAG_BIND = '"include_inactive": include_inactive'

# handler -> (predicate occurrences, bind-dict occurrences) within the handler.
# 1v1 / 2v2 / FFA: column + WHERE + the population COUNT. 1v2: column + WHERE
# only -- its total_players is len(entries), which already follows the filter.
BOARDS = {
    main.get_leaderboard: (3, 2),
    main.team_leaderboard: (3, 2),
    main.ffa_leaderboard: (3, 2),
    main.ovt_leaderboard: (2, 1),
}
PODIUMS = {
    "_PODIUM_QUERY": main._PODIUM_QUERY,
    "_PODIUM_2V2_QUERY": main._PODIUM_2V2_QUERY,
    "_PODIUM_FFA_QUERY": main._PODIUM_FFA_QUERY,
    "_OVT_PODIUM_QUERY": main._OVT_PODIUM_QUERY,
}


def _standing_block() -> str:
    src = inspect.getsource(main.get_player_stats)
    start = src.index("numeric standings on all four boards")
    end = src.index("standings block failed")
    return src[start:end]


def _no_string_interval(src: str, label: str) -> None:
    for bad in ("' days'", "' day'", ":active_days ||", "|| :active_days",
                ":active_days || ", "INTERVAL '90"):
        assert bad not in src, f"{label}: string-built interval {bad!r}"


def test_default_is_90_days_and_an_int():
    assert main.LEADERBOARD_ACTIVE_DAYS == 90
    assert type(main.LEADERBOARD_ACTIVE_DAYS) is int


def test_every_board_takes_include_inactive_defaulting_off():
    for handler in BOARDS:
        sig = inspect.signature(handler)
        assert "include_inactive" in sig.parameters, handler.__name__
        p = sig.parameters["include_inactive"]
        assert p.annotation is bool, handler.__name__
        # plain `= False` or `Query(False, ...)` -- both must default to off
        assert getattr(p.default, "default", p.default) is False, handler.__name__


def test_every_board_binds_the_typed_predicate_in_page_and_count():
    for handler, (n_pred, n_bind) in BOARDS.items():
        src = inspect.getsource(handler)
        name = handler.__name__
        assert src.count(BIND_PRED) == n_pred, (name, src.count(BIND_PRED))
        assert src.count(INACTIVE_COL) == 1, name
        assert src.count(WHERE_TERM) == n_pred - 1, name
        assert src.count(DAYS_BIND) == n_bind, name
        assert src.count(FLAG_BIND) == n_bind, name
        # the row builder forwards the flag exactly once
        assert src.count('inactive=bool(') == 1, name
        _no_string_interval(src, name)


def test_podium_queries_interpolate_the_int_and_bind_nothing():
    rendered = f"make_interval(days => {main.LEADERBOARD_ACTIVE_DAYS})"
    for name, q in PODIUMS.items():
        assert rendered in q, name
        assert "p.last_seen > NOW() - " + rendered in q, name
        # parameter-less statements: an unbound :name here would 500 the podium
        assert ":active_days" not in q and ":include_inactive" not in q, name
        assert "LIMIT 3" in q, name
        _no_string_interval(q, name)


def test_player_stats_standings_apply_the_same_predicate_by_bind():
    block = _standing_block()
    assert block.count(BIND_PRED) == 4
    assert block.count(DAYS_BIND) == 4
    # the standings are the DEFAULT board's numbering: no include_inactive arm
    assert "include_inactive" not in block
    _no_string_interval(block, "standings")


def test_no_board_keeps_a_filterless_population_count():
    # the 2v2 count used to be a bare `SELECT COUNT(*) FROM glicko_ratings_2v2`
    src = inspect.getsource(main.team_leaderboard)
    assert 'text("SELECT COUNT(*) FROM glicko_ratings_2v2 WHERE completed_series >= :m")' not in src
    assert "JOIN players p ON p.id = g2.player_id" in src
