"""Single source of truth for Release A W1 test expectations."""

from __future__ import annotations


COUNTER_MAX = 1_000_000
MILLISECONDS_MAX = 3_600_000

REQUEST_NUMERIC_MAX = {
    "local_net_writes": COUNTER_MAX,
    "local_net_unchanged": COUNTER_MAX,
    "local_net_move_raise_attempted": COUNTER_MAX,
    "local_net_move_raise_accepted": COUNTER_MAX,
    "local_net_resent_reliable": COUNTER_MAX,
    "local_net_discarded": COUNTER_MAX,
    "local_net_crc_loss": COUNTER_MAX,
    "local_net_queued_out_max": COUNTER_MAX,
    "local_net_queued_in_max": COUNTER_MAX,
    "local_net_fragment_cmds": COUNTER_MAX,
    "local_net_view_update_faults": COUNTER_MAX,
    "local_net_hitch50": COUNTER_MAX,
    "local_net_hitch200": COUNTER_MAX,
    "local_net_worst_frame_ms": MILLISECONDS_MAX,
    "local_obs_gap300": COUNTER_MAX,
    "local_obs_gap750": COUNTER_MAX,
    "local_obs_gap1500": COUNTER_MAX,
    "local_obs_max_gap_ms": MILLISECONDS_MAX,
    "local_obs_excess150": COUNTER_MAX,
    "local_obs_max_excess_ms": MILLISECONDS_MAX,
    "local_obs_payload_equal_gaps": COUNTER_MAX,
    "local_obs_receiver_frame_gaps": COUNTER_MAX,
    "local_obs_phoenix_intervals": COUNTER_MAX,
    "local_obs_batches": COUNTER_MAX,
}
REQUEST_TAG = "local_net_worst_frame_tags"
REQUEST_FIELDS = tuple(REQUEST_NUMERIC_MAX) + (REQUEST_TAG,)

SUFFIX_TO_REQUEST = {
    name.removeprefix("local_"): name for name in REQUEST_FIELDS
}
STORAGE_FIELDS = tuple(
    f"{seat}_{suffix}"
    for seat in ("p1", "p2")
    for suffix in SUFFIX_TO_REQUEST
)


def old_match_body() -> dict:
    """Smallest legacy 1v1 report accepted before W1 existed."""
    return {
        "player1": {
            "steam_id": "76561198000000001",
            "display_name": "Player One",
        },
        "player2": {
            "steam_id": "76561198000000002",
            "display_name": "Player Two",
        },
        "p1_rounds_won": 5,
        "p2_rounds_won": 3,
        "reported_by_steam_id": "76561198000000001",
    }


def request_sentinels() -> dict:
    """Unique, valid values for all 25 reporter-local request fields."""
    values = {
        name: 900_001 + index
        for index, name in enumerate(REQUEST_NUMERIC_MAX)
    }
    values[REQUEST_TAG] = "net-seat-tag-sentinel"
    return values


def storage_sentinels() -> dict:
    """Unique values that make accidental response serialization obvious."""
    values = {}
    for index, name in enumerate(STORAGE_FIELDS):
        if name.endswith("_tags"):
            values[name] = f"private-{name[:2]}-tag-sentinel"
        else:
            values[name] = 910_001 + index
    return values


def recursive_keys_and_scalars(value) -> tuple[set[str], set[object]]:
    """Collect keys and JSON-scalar values from an arbitrarily nested value."""
    keys: set[str] = set()
    scalars: set[object] = set()

    def visit(item):
        if isinstance(item, dict):
            for key, child in item.items():
                keys.add(str(key))
                visit(child)
        elif isinstance(item, (list, tuple)):
            for child in item:
                visit(child)
        elif item is None or isinstance(item, (str, int, float, bool)):
            scalars.add(item)

    visit(value)
    return keys, scalars


def assert_no_net_seat_sentinels(value, sentinels: dict | None = None) -> None:
    """Fail on either a private column name or one of its unique values."""
    sentinels = sentinels or storage_sentinels()
    keys, scalars = recursive_keys_and_scalars(value)
    # impl-review r1 LOW 21: a public surface that echoed a REQUEST-shaped key
    # (e.g. {"local_net_writes": 0}) is a leak too — ban both name families.
    banned = set(STORAGE_FIELDS) | set(REQUEST_FIELDS)
    leaked_keys = keys & banned
    assert not leaked_keys, f"private net-seat key names leaked: {sorted(leaked_keys)}"
    leaked_values = set(sentinels.values()) & scalars
    assert not leaked_values, f"private net-seat sentinel values leaked: {leaked_values}"
