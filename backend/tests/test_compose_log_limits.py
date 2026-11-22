"""Log size limits in the compose files (item 38).

The Docker daemons under this stack set no log default (read 22 Nov 2026), so
a service with no `logging:` key writes a json-file log that grows without
bound. Every service carries the same limit, written out in its own block. A
service named in PENDING may carry none while its limit waits for a separate,
planned change: adding the key to the database service changes its rendered
config, so the next deploy that considers it recreates the database container.

The rule covers every compose file the repository holds: the base file, and
the TLS overlay for a service the overlay ADDS. A service the overlay only
changes is judged in the base file.

Written out, not shared: an anchor, an alias, a merge key or `extends` would
let one block reach another service's config, and a deploy that only meant to
change the api and the bot would then change the database's too. These are
looked for in the YAML events and nodes, before construction, because the
constructor consumes a merge key and leaves no trace of it.

The files are read with a loader stricter than Compose's: a duplicate key at
any mapping level is refused (a plain loader keeps the last one silently), and
so is a key that does not construct to a string (a YAML 1.1 loader turns `on`
and `yes` into the same boolean, so two service names would collapse into one).
"""
import os

import yaml

BACKEND = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
BASE = os.path.join(BACKEND, "docker-compose.yml")
OVERLAYS = [os.path.join(BACKEND, "docker-compose.tls.yml")]

LIMIT = {"driver": "json-file", "options": {"max-size": "50m", "max-file": "5"}}

# Services whose limit is a separate, planned change. Each may carry no
# `logging:` key or exactly LIMIT. The planned change empties this set, and
# test_the_pending_set_is_the_database_alone says which set is approved.
PENDING = {"db"}

MERGE_TAG = "tag:yaml.org,2002:merge"


class _StrictLoader(yaml.SafeLoader):
    """SafeLoader that refuses duplicate keys, non-string keys and merge keys,
    at every mapping level, by looking at each mapping's NODES before the
    constructor flattens merges or a dict drops a repeated key."""

    def construct_mapping(self, node, deep=False):
        seen = set()
        for key_node, _ in node.value:
            if key_node.tag == MERGE_TAG:
                raise yaml.constructor.ConstructorError(
                    None, None, "merge key refused", key_node.start_mark)
            key = self.construct_object(key_node, deep=True)
            if not isinstance(key, str):
                raise yaml.constructor.ConstructorError(
                    None, None, "key %r is not a string" % (key,), key_node.start_mark)
            if key in seen:
                raise yaml.constructor.ConstructorError(
                    None, None, "duplicate key %r" % key, key_node.start_mark)
            seen.add(key)
        return super().construct_mapping(node, deep=deep)


_StrictLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
                              _StrictLoader.construct_mapping)


def _text(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _load(path):
    return yaml.load(_text(path), Loader=_StrictLoader)


def _base_services():
    services = _load(BASE)["services"]
    # The set is asserted before it is used: a check over no services passes
    # for ever.
    assert {"db", "api", "bot"} <= set(services), sorted(services)
    return services


def _added_services(path, base):
    return {name: svc for name, svc in (_load(path).get("services") or {}).items()
            if name not in base}


def _wrong(services, pending):
    wrong = {}
    for name, svc in services.items():
        got = svc.get("logging")
        if name in pending and got is None:
            continue
        if got != LIMIT:
            wrong[name] = got
    return wrong


def test_the_pending_set_is_the_database_alone():
    # Batch A's approved exception is the database service and nothing else.
    assert PENDING == {"db"}, PENDING


def test_every_service_carries_the_log_limit():
    base = _base_services()
    wrong = _wrong(base, PENDING)
    assert not wrong, "base file: these services do not carry exactly %r: %r" % (LIMIT, wrong)
    added_any = False
    for path in OVERLAYS:
        added = _added_services(path, base)
        added_any = added_any or bool(added)
        wrong = _wrong(added, set())
        assert not wrong, "%s adds services without exactly %r: %r" % (
            os.path.basename(path), LIMIT, wrong)
    # The TLS overlay adds nginx; an overlay check that reads no added service
    # passes for ever.
    assert added_any


def test_the_limit_values_are_strings():
    # Docker takes log options as strings; an unquoted 5 loads as an int.
    for path in [BASE] + OVERLAYS:
        for name, svc in (_load(path).get("services") or {}).items():
            opts = (svc.get("logging") or {}).get("options") or {}
            for key, value in opts.items():
                assert isinstance(value, str), (os.path.basename(path), name, key, value)


def _merge_keys(node, path=()):
    found = []
    if isinstance(node, yaml.MappingNode):
        for key_node, value_node in node.value:
            if key_node.tag == MERGE_TAG:
                found.append(path)
            found += _merge_keys(value_node, path + (getattr(key_node, "value", "?"),))
    elif isinstance(node, yaml.SequenceNode):
        for i, item in enumerate(node.value):
            found += _merge_keys(item, path + (i,))
    return found


def test_no_block_is_shared_between_services():
    for path in [BASE] + OVERLAYS:
        text = _text(path)
        anchors, aliases = [], []
        for event in yaml.parse(text, Loader=yaml.SafeLoader):
            if isinstance(event, yaml.AliasEvent):
                aliases.append(event.anchor)
            elif getattr(event, "anchor", None):
                anchors.append(event.anchor)
        name = os.path.basename(path)
        assert not anchors and not aliases, (name, anchors, aliases)
        # Merge keys in the composed node tree, inline or block, at any depth.
        assert not _merge_keys(yaml.compose(text, Loader=yaml.SafeLoader)), name
        for svc_name, svc in (_load(path).get("services") or {}).items():
            assert "extends" not in svc, (name, svc_name)
