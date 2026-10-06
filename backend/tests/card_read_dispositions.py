"""The accountability tables of the two read-set methods (fix pass 4, M2).

Every (measure, fact) pair the static method reads and no perturbation of
the dynamic method moved, and every arm of the measure functions the
dynamic method's fixtures never ran, has an identity-level disposition
here: the pair or the arm, and the reason. check() refuses when a pair or
an arm has none, when a disposition names a pair or an arm that is no
longer static-only or unexercised, and when a pair's stated kind no longer
matches what the run observed (ROWSET: the fact moved only which rows exist).

The arms are named by function, source line, the site's number on that line
(code order) and the arm that never ran (card_read_dynamic.branch_coverage),
so an edit of card_measures.py that moves a line makes the table stale and
the gate refuses until it is redone."""

# -- static-only pairs -----------------------------------------------------------------

PAIR_REASONS = {
    "ROWSET": "the fact moved only which rows exist: a trimmed list removes the rows built from the "
              "entries it lost (hand, pair, phase or window rows), the measure reads the list whole "
              "(a search, a length, a last-entry test), and on every row present in both runs its "
              "value did not move on these fixtures",
    "SPAWN": "the spawn list reaches these measures only through b4.hand.spo inside the eligibility "
             "test (every HAND_RULE must be zero); the one fixture with spawn lists (over the cap) has "
             "no hand that is otherwise eligible, so shortening or emptying a spawn list never makes a "
             "hand eligible and never moves a window",
    "AGG": "window_row's aggregate is read as one value by the static method (Analysis._agg merges the "
           "facts of every contribution field); b4.rar.games is the run's own game count (rows() sets "
           "games to one), b4.rar.meas the source class and b4.rar.paired the coverage class, which no "
           "list's contents move on a window present in both runs",
    "SCK_ZERO": "b4.sc.k counts later shared draws that differ; it holds a value only on the game two, "
                "Same Cards on fixture, where it is zero, and a trimmed hand list only removes draws, so "
                "it stays zero",
}

_RAR_ALL = ["b4.rar.%s.%s" % (k, r) for k in ("obs", "exp", "var", "dev") for r in ("common", "uncommon", "rare")]

PAIRS = {}
for _m in ("b4.hand.eligible", "b4.hand.heldrej", "b4.pair.held", "b4.pair.pick", "b4.pair.slot",
           "b4.pair.spawn"):
    PAIRS[(_m, "hd")] = "ROWSET"
for _m in ("b4.ph.notdone", "b4.ph.picker"):
    PAIRS[(_m, "ph")] = "ROWSET"
for _m in ("b4.rar.games", "b4.rar.meas", "b4.rar.paired"):
    PAIRS[(_m, "hd")] = "ROWSET"
    PAIRS[(_m, "whole")] = "ROWSET"
    for _f in ("ap", "cards", "first", "held0", "sl", "sp"):
        PAIRS[(_m, _f)] = "AGG"
for _m in _RAR_ALL + ["b4.rar.hands", "b4.rar.slots", "b4.rar.notrun", "b4.hand.eligible"]:
    PAIRS[(_m, "sp")] = "SPAWN"
PAIRS[("b4.sc.k", "hd")] = "SCK_ZERO"

# -- unexercised arms ------------------------------------------------------------------

ARM_REASONS = {
    "NO_CALLER": "cannot execute in the measure run: RecFacts.role_of has no caller",
    "UNGATED": "cannot execute in the dynamic run: the gate is taken out and every record states every "
               "fact whole (Ungated), so no coverage flag is false",
    "ELIGIBLE_ONLY": "cannot execute: expectation is called only for an eligible hand, and eligibility "
                     "requires the revision's weights and a supported census (b4.hand.w0, a HAND_RULE, "
                     "is NOT-RUN without one)",
    "OWN_ENTRY": "cannot execute: the search looks in a record for an entry that record's own rows were "
                 "built from (the row's own entry, or a deal both records' rows name), so it finds it "
                 "before the list ends",
    "FIRST_MATCH": "in every fixture record the first entry with the phase sought is the hand sought, so "
                   "the deal and role tests after a phase match never fail",
    "ROLE_KNOWN": "no fixture hand or phase has an unknown role (w = -1), so no deal is attributed to "
                  "no one and no held set is asked for no role",
    "NO_CATS": "no fixture census card carries categories or blacklists, so the blacklist rule never "
               "rejects and its loops never run",
    "NO_LOCK": "no fixture census card is gun-locked, so the lock clause is never needed",
    "MULTI": "every fixture census card allows multiples, so the held-copies test never runs",
    "NO_REJECT": "the held-card rule never rejects a card in the fixtures (no blacklist, no lock, "
                 "multiples allowed), so no slot is rejected and none is undecidable",
    "WEIGHTS_POSITIVE": "the fixture weights deal every rarity: no slot has weight zero and no allowed "
                        "weight sums to zero",
    "SUPPORTED": "every fixture census is supported (its rarities are the three known ones)",
    "RESOLVED": "no fixture slot list or held list holds an unresolved slot (-1)",
    "NO_DUP": "no fixture hand repeats a slot",
    "IN_POOL": "every fixture slot lies in its census, and the record's rarity for it is the census's",
    "DIGEST": "every fixture record names a census digest whose pool state is ok, whose census matches "
              "its game hash and card count, and paired fixtures name the same digest on both seats",
    "PROFILE": "every fixture profile has its mod build hashed and its pool state ok, with a digest",
    "APPS": "no fixture record marks an appearance with an unknown role, every hand states its "
            "appearance index and held count, every picked hand names its appearance, and every "
            "appearance is of kind zero (none offline)",
    "SOURCE_BITS": "every fixture self hand states its source bits and its generation is opening or "
                   "later, so no Same Cards rule is unknown",
    "SHARED_SLOTS": "every own hand Same Cards looks at in the fixtures was served by the shared sequence "
                    "(its source bits set, every slot of the hands it compares), and every later shared "
                    "draw carries its sequence number",
    "SC_CENSUS": "the Same Cards on fixture registers both seats' censuses",
    "SC_PAIRED": "every fixture with Same Cards on is paired",
    "PICKS": "every fixture pick lies in its hand, and paired fixtures agree on every pick",
    "VIEW_IDS": "every fixture hand names its deal's view id, and paired fixtures agree on it",
    "DEALER": "every fixture hand's dealer is known",
    "PHASE_ORDER": "every fixture first-phase order has one entry per player, every later phase's "
                   "predecessor is present, and between consecutive phases the seat's round counter "
                   "rises by at most one and never together with the other's",
}

ARMS = {
    ("RecFacts.__init__", 528, 1, "jump"): "DIGEST",
    ("RecFacts.__init__", 529, 1, "jump"): "DIGEST",
    ("RecFacts.__init__", 530, 2, "jump"): "DIGEST",
    ("RecFacts.__init__", 531, 1, "jump"): "DIGEST",
    ("RecFacts.__init__", 531, 2, "jump"): "DIGEST",
    ("RecFacts.held_at", 560, 1, "jump"): "ROLE_KNOWN",
    ("RecFacts.held_at", 560, 4, "jump"): "APPS",
    ("RecFacts.held_at", 560, 5, "fall"): "APPS",
    ("RecFacts.held_at", 566, 1, "fall"): "RESOLVED",
    ("RecFacts.held_at", 568, 1, "jump"): "APPS",
    ("RecFacts.player", 544, 1, "jump"): "ROLE_KNOWN",
    ("RecFacts.role_of", 549, 1, "both"): "NO_CALLER",
    ("RecFacts.role_of", 551, 1, "both"): "NO_CALLER",
    ("_blacklisted", 613, 1, "jump"): "NO_CATS",
    ("_blacklisted", 615, 1, "both"): "NO_CATS",
    ("_blacklisted", 615, 2, "both"): "NO_CATS",
    ("_blacklisted", 616, 1, "both"): "NO_CATS",
    ("_blacklisted", 618, 1, "both"): "NO_CATS",
    ("_blacklisted", 618, 2, "both"): "NO_CATS",
    ("_blacklisted", 618, 3, "both"): "NO_CATS",
    ("_blacklisted", 618, 4, "both"): "NO_CATS",
    ("_gen_slots", 631, 1, "fall"): "SOURCE_BITS",
    ("_gen_slots", 634, 2, "fall"): "SOURCE_BITS",
    ("_hand_row", 712, 1, "fall"): "ROLE_KNOWN",
    ("_hand_row", 719, 1, "fall"): "DIGEST",
    ("_hand_row", 723, 1, "fall"): "ROLE_KNOWN",
    ("_hand_row", 727, 3, "jump"): "RESOLVED",
    ("_hand_row", 728, 3, "jump"): "NO_DUP",
    ("_hand_row", 731, 2, "fall"): "RESOLVED",
    ("_hand_row", 731, 3, "jump"): "IN_POOL",
    ("_hand_row", 732, 1, "fall"): "IN_POOL",
    ("_hand_row", 737, 2, "jump"): "WEIGHTS_POSITIVE",
    ("_hand_row", 738, 3, "jump"): "SUPPORTED",
    ("_hand_row", 740, 1, "jump"): "ROLE_KNOWN",
    ("_hand_row", 753, 2, "jump"): "ROLE_KNOWN",
    ("_heldrej", 654, 1, "fall"): "NO_REJECT",
    ("_heldrej", 656, 1, "jump"): "NO_REJECT",
    ("_own_hands", 970, 1, "exit"): "OWN_ENTRY",
    ("_own_hands", 970, 3, "fall"): "FIRST_MATCH",
    ("_own_hands", 971, 1, "jump"): "FIRST_MATCH",
    ("_own_hands", 972, 3, "fall"): "SHARED_SLOTS",
    ("_phase_rows", 775, 2, "jump"): "PHASE_ORDER",
    ("_phase_rows", 786, 2, "jump"): "ROLE_KNOWN",
    ("_phase_rows", 792, 1, "jump"): "PHASE_ORDER",
    ("_phase_rows", 794, 2, "jump"): "PHASE_ORDER",
    ("_phase_rows", 796, 1, "jump"): "PHASE_ORDER",
    ("_record_row", 832, 1, "fall"): "DIGEST",
    ("_record_row", 836, 2, "jump"): "UNGATED",
    ("_record_row", 841, 3, "jump"): "APPS",
    ("_record_row", 842, 3, "fall"): "APPS",
    ("_record_row", 844, 1, "jump"): "APPS",
    ("_record_row", 847, 3, "jump"): "APPS",
    ("_rejects_local", 602, 1, "fall"): "NO_CATS",
    ("_rejects_local", 604, 1, "fall"): "NO_LOCK",
    ("_rejects_local", 605, 1, "both"): "NO_LOCK",
    ("_rejects_vanilla", 587, 1, "fall"): "NO_CATS",
    ("_rejects_vanilla", 589, 1, "fall"): "MULTI",
    ("_rejects_vanilla", 589, 2, "both"): "MULTI",
    ("_rejects_vanilla", 589, 3, "both"): "MULTI",
    ("_rejects_vanilla", 591, 1, "fall"): "NO_LOCK",
    ("_rejects_vanilla", 592, 1, "both"): "NO_LOCK",
    ("_report_surplus", 818, 1, "jump"): "PICKS",
    ("_report_surplus", 818, 3, "jump"): "RESOLVED",
    ("_same_cards", 992, 1, "fall"): "SOURCE_BITS",
    ("_same_cards", 996, 1, "fall"): "SOURCE_BITS",
    ("_same_cards", 999, 1, "jump"): "SC_PAIRED",
    ("_same_cards", 1007, 1, "jump"): "RESOLVED",
    ("_same_cards", 1007, 2, "fall"): "RESOLVED",
    ("_same_cards", 1012, 1, "fall"): "SHARED_SLOTS",
    ("_same_cards", 1012, 2, "fall"): "SHARED_SLOTS",
    ("_same_cards", 1016, 2, "fall"): "SHARED_SLOTS",
    ("_same_cards", 1023, 1, "jump"): "SC_CENSUS",
    ("_same_cards", 1023, 2, "jump"): "SC_CENSUS",
    ("_same_cards", 1024, 1, "jump"): "RESOLVED",
    ("_same_cards", 1024, 2, "fall"): "RESOLVED",
    ("_same_cards", 1028, 2, "fall"): "SHARED_SLOTS",
    ("_slot_diff", 862, 1, "jump"): "RESOLVED",
    ("_slot_diff", 862, 2, "fall"): "RESOLVED",
    ("card_view", 903, 2, "fall"): "VIEW_IDS",
    ("card_view", 912, 3, "jump"): "VIEW_IDS",
    ("card_view", 925, 2, "fall"): "DEALER",
    ("card_view", 926, 2, "fall"): "DEALER",
    ("card_view", 930, 3, "jump"): "VIEW_IDS",
    ("card_view", 930, 4, "fall"): "VIEW_IDS",
    ("card_view", 934, 1, "exit"): "OWN_ENTRY",
    ("card_view", 936, 1, "exit"): "OWN_ENTRY",
    ("card_view", 945, 1, "jump"): "PICKS",
    ("card_view", 946, 1, "jump"): "PICKS",
    ("card_view", 947, 1, "jump"): "PICKS",
    ("card_view", 961, 2, "jump"): "UNGATED",
    ("contributions", 1058, 1, "jump"): "DEALER",
    ("expectation", 669, 1, "jump"): "ELIGIBLE_ONLY",
    ("expectation", 669, 2, "fall"): "ELIGIBLE_ONLY",
    ("expectation", 683, 1, "fall"): "NO_REJECT",
    ("expectation", 685, 1, "fall"): "NO_REJECT",
    ("expectation", 689, 1, "fall"): "WEIGHTS_POSITIVE",
    ("profile_complete", 457, 2, "jump"): "PROFILE",
    ("profile_complete", 457, 3, "jump"): "PROFILE",
    ("profile_complete", 457, 4, "jump"): "PROFILE",
}


def check(static_only, rowset, unexercised):
    """The gate. static_only: the (measure, fact) pairs the static method
    reads and no perturbation moved; rowset: per measure, the facts whose
    change only added or removed rows; unexercised: branch_coverage's arms.
    Returns the problems (empty: accounted for)."""
    problems = []
    got = set(static_only)
    for p in sorted(got - set(PAIRS)):
        problems.append("static-only pair with no disposition: %s %s" % p)
    for p in sorted(set(PAIRS) - got):
        problems.append("disposition for a pair that is not static-only: %s %s" % p)
    for (m, f), why in sorted(PAIRS.items()):
        if why not in PAIR_REASONS:
            problems.append("unknown reason %s for %s %s" % (why, m, f))
        elif (m, f) in got and (why == "ROWSET") != (f in rowset.get(m, ())):
            problems.append("disposition %s no longer matches %s %s (rows %s)"
                            % (why, m, f, "moved" if f in rowset.get(m, ()) else "did not move"))
    arms = set(unexercised)
    for a in sorted(arms - set(ARMS), key=str):
        problems.append("unexercised arm with no disposition: %s line %s site %s %s" % a)
    for a in sorted(set(ARMS) - arms, key=str):
        problems.append("disposition for an arm that is not unexercised: %s line %s site %s %s" % a)
    for a, why in sorted(ARMS.items(), key=str):
        if why not in ARM_REASONS:
            problems.append("unknown reason %s for %s" % (why, a))
    return problems
