"""The ONE order of the identity advisory key (bans part 2a, FIX-1B point 3).

The identity key is pg_advisory_xact_lock(hashtext(steam_id)), taken shared
(_ban_lock_and_gate and the player-card actors) or exclusive (the ban core,
_identity_lock_many, _enrollment_identity_gate, the report window's
_guard_identities). Two takers that lock the same two keys in different
orders can each wait for the other until the server ends one of the two
requests, so every taker of SEVERAL keys orders them by identity_lock_key.

The stored ids are not all 17 digits: ids of other lengths and short words
are ordinary input. The key is total for any text: (length, text) orders
digits of any length numerically when they carry no leading zero, and orders
words, mixed text and the empty text deterministically. None is the empty
text.
"""
from __future__ import annotations


def identity_lock_key(steam_id) -> tuple:
    s = "" if steam_id is None else str(steam_id)
    return (len(s), s)
