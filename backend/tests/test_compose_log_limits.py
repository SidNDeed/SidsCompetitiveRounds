"""Log size limits in docker-compose.yml (item 38).

The Docker daemons under this stack set no log default, so a service with no
`logging:` key writes a json-file log that grows without bound. Every service
carries the same limit, written out in its own block. The database service is
the one exception while its limit waits for a separate, planned change: adding
the key to it changes its rendered config, so the next deploy that considers
it recreates the database container.

Written out, not shared: an anchor, an alias, a merge key or `extends` would
let one block reach another service's config, and a deploy that only meant to
change the api and the bot would then change the database's too.
"""
import os

import yaml

BACKEND = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
COMPOSE = os.path.join(BACKEND, "docker-compose.yml")

LIMIT = {"driver": "json-file", "options": {"max-size": "50m", "max-file": "5"}}

# Services whose limit is a separate, planned change. Each may carry no
# `logging:` key or exactly LIMIT. The planned change removes its name here.
PENDING = {"db"}


def _text():
    with open(COMPOSE, encoding="utf-8") as fh:
        return fh.read()


def _services():
    doc = yaml.safe_load(_text())
    services = doc["services"]
    # The set is asserted before it is used: a check over no services passes
    # for ever.
    assert {"db", "api", "bot"} <= set(services), sorted(services)
    return services


def test_every_service_carries_the_log_limit():
    wrong = {}
    for name, svc in _services().items():
        got = svc.get("logging")
        if name in PENDING and got is None:
            continue
        if got != LIMIT:
            wrong[name] = got
    assert not wrong, ("these services do not carry exactly %r: %r" % (LIMIT, wrong))


def test_the_limit_values_are_strings():
    # Docker takes log options as strings; an unquoted 5 loads as an int.
    for name, svc in _services().items():
        opts = (svc.get("logging") or {}).get("options") or {}
        for key, value in opts.items():
            assert isinstance(value, str), (name, key, value)


def test_no_block_is_shared_between_services():
    anchors, aliases = [], []
    for event in yaml.parse(_text()):
        if isinstance(event, yaml.AliasEvent):
            aliases.append(event.anchor)
        elif getattr(event, "anchor", None):
            anchors.append(event.anchor)
    assert not anchors and not aliases, (anchors, aliases)
    for name, svc in _services().items():
        assert "<<" not in svc and "extends" not in svc, name
        logging = svc.get("logging") or {}
        assert "<<" not in logging and "<<" not in (logging.get("options") or {}), name
