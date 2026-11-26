"""ALT-BAN-1 step 8: the contract of the two admin surfaces (CONTRACT-BAN-1124
points 1 and 4 with ADD2) read from the source, and a census of who
reaches the relation reader and the recording functions.

No database. What the answers hold row by row is proven over planted rows
in test_alt_ban_links_pg.py and test_alt_ban_notice_pg.py; this file pins
the shape those tests and the admin page read: the route and its
parameters, the words and their order, the caps, the keys and their order,
and the call graph of the functions that read or write the lane's
tables."""
import ast
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
API = os.path.normpath(os.path.join(HERE, "..", "api"))
if API not in sys.path:
    sys.path.insert(0, API)

import main  # noqa: E402

SRC = open(os.path.join(API, "main.py"), encoding="utf-8").read()
TREE = ast.parse(SRC)


def _fn(name):
    found = [n for n in TREE.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name]
    assert len(found) == 1, (name, len(found))
    return found[0]


def _callers(name):
    """Every top-level function of main.py that calls `name` (by its bare
    name), and every other module of api/ that names it at all."""
    out = set()
    for node in TREE.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for sub in ast.walk(node):
            if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Name) and sub.func.id == name:
                out.add(node.name)
    for f in sorted(os.listdir(API)):
        if f.endswith(".py") and f != "main.py":
            if name in open(os.path.join(API, f), encoding="utf-8").read():
                out.add(f)
    return out


def _dict_keys(node):
    return [k.value for k in node.keys if isinstance(k, ast.Constant)]


def test_the_links_route_its_method_and_its_parameters():
    routes = [r for r in main.app.routes if getattr(r, "path", None) == "/api/v1/admin/bans/links"]
    assert len(routes) == 1 and routes[0].methods == {"GET"}, routes
    params = [p.name for p in routes[0].dependant.query_params]
    assert params == ["admin_steam_id", "target_steam_id", "hmac_signature"], params
    src = ast.unparse(_fn("admin_ban_links"))
    assert src.count("_require_admin(db, admin_steam_id, 'ban_links', target_steam_id, hmac_signature)") == 1, src[:400]


def test_the_five_words_the_caps_and_the_windows():
    assert main._ALT_BAN_HOW == ("address", "block", "family_shared", "family_lender", "family_borrower")
    assert (main._ALT_BAN_LINKS_SHOWN, main._ALT_BAN_REGIONS_SHOWN) == (50, 20)
    assert main._ALT_BAN_OWN_DAYS >= 36500
    assert (main._ALT_BAN_LINKS_LOCK_MS, main._ALT_BAN_LINKS_STATEMENT_MS) == (500, 3000)
    rows_src = ast.unparse(_fn("_ban_links_rows"))
    order = [rows_src.index("'%s'" % w) for w in main._ALT_BAN_HOW]
    assert order == sorted(order), "the rows are built in the words' order"


def test_the_links_answer_keys_in_their_order():
    ret = [n for n in ast.walk(_fn("admin_ban_links")) if isinstance(n, ast.Return)]
    assert len(ret) == 1 and isinstance(ret[0].value, ast.Dict), ret
    top = ret[0].value
    assert _dict_keys(top) == ["steam_id", "recording", "regions", "links", "links_total"]
    comps = {k.value: v for k, v in zip(top.keys, top.values)}
    assert _dict_keys(comps["regions"].elt) == ["region", "conn_class", "first_at", "last_at"]
    assert _dict_keys(comps["links"].elt) == ["linked_steam_id", "linked_name", "how", "days", "last_day", "others"]


def test_the_lists_four_keys_and_their_unrecorded_values():
    assert dict(main._BAN_LIST_ALT_NONE) == {"region": "", "region_at": None, "regions": None, "links": None}
    assert [k for k, _v in main._BAN_LIST_ALT_NONE] == ["region", "region_at", "regions", "links"]
    src = ast.unparse(_fn("admin_list_bans"))
    assert src.count("_ban_list_alt(db, ") == 1 and src.count("_BAN_LIST_ALT_NONE") == 1, src[-600:]
    fill = ast.unparse(_fn("_ban_list_alt"))
    assert fill.count("begin_nested()") == 1 and fill.count("sp.rollback()") == 1, fill
    assert fill.count("db.execute(") == 1, "the page's four keys come from ONE statement"


def test_the_notice_settings_and_its_caps():
    assert main._BAN_NOTICE_CHANNEL_ENV == "SCR_BAN_NOTICE_CHANNEL"
    assert main._BAN_NOTICE_DAY_CAP == 20
    compose = open(os.path.join(HERE, "..", "docker-compose.yml"), encoding="utf-8").read()
    api = compose[compose.index("\n  api:\n"):compose.index("\n  bot:\n")]
    assert api.count("SCR_BAN_NOTICE_CHANNEL: ${SCR_BAN_NOTICE_CHANNEL:-}") == 1
    assert compose.count("SCR_BAN_NOTICE_CHANNEL: ${") == 1, "another service names the channel"


def test_who_reaches_the_reader_and_the_recording_functions():
    assert _callers("alt_relations") == {"admin_ban_links"}
    assert _callers("_alt_store") == {"_alt_record", "_ban_ticket_seen"}
    assert _callers("_alt_record") == {"steam_auth"}
    assert _callers("_ban_ticket_seen") == {"_alt_ban_refused"}
    assert _callers("_ban_list_alt") == {"admin_list_bans"}
    assert _callers("_ban_links_rows") == {"admin_ban_links"}
    assert _callers("_ban_notice_pair_tx") == {"ban_link_notice_pass"}
    assert _callers("ban_link_notice_pass") == {"ban_link_notice_loop"}
    # the loop is a name passed to _supervised in lifespan, not a call
    assert _callers("ban_link_notice_loop") == set()
    assert SRC.count('_supervised("ban_link_notice", ban_link_notice_loop)') == 1


def test_the_reads_in_flight_are_one_pool_of_three_and_three_kinds():
    assert main._ALT_BAN_READS._max_workers == 3
    assert set(main._alt_ban_reading) == {"word", "region", "steam"}
    starts = {}
    for node in TREE.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for sub in ast.walk(node):
                if (isinstance(sub, ast.Call) and isinstance(sub.func, ast.Name)
                        and sub.func.id == "_alt_ban_read_start"):
                    starts.setdefault(sub.args[0].value, set()).add(node.name)
    assert starts == {"word": {"_ban_region_word"}, "region": {"_ban_ticket_seen"},
                      "steam": {"_steam_ticket_check"}}, starts
    for name in ("_ban_region_word", "_ban_ticket_seen", "_steam_ticket_check"):
        assert "to_thread" not in ast.unparse(_fn(name)), name


def test_the_links_route_stands_with_the_ban_list_in_the_admin_censuses():
    """Fix 1, H1: the read gate classes the links route as it classes the ban
    list (the handler's own admin check; the gate refuses nothing), the
    moderator log's census classes it a read, and the read gate inventory's
    review names it nowhere (it reaches an admin check inside its class)."""
    import read_gate
    import modlog_census as MC
    import test_read_gate_inventory as INV
    links, bans = "/api/v1/admin/bans/links", "/api/v1/admin/banned-users"
    assert read_gate.route_class(links) == read_gate.route_class(bans) == read_gate.C_ADMIN_SIGNED
    assert links in read_gate.ADMIN_SIGNED and links not in read_gate.PLAYER and links not in read_gate.BOT_ONLY
    assert MC.CENSUS[("GET", links)] == MC.CENSUS[("GET", bans)] == (MC.NOT, "read", ())
    assert not [ln for ln in INV.review_report(main.app.routes) if links in ln]
