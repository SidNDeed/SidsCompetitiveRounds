"""The frozen providers of the pure-callee whitelists (rehearsal-four round
10, ruling REHEARSAL-R9-A1 (D); finding closed_walk:859: a module binding
`int = writer` left the frozen `int(...)` pure).

Every walk family that admits a call by a whitelisted spelling binds the
spelling to its PROVIDER: one object per component of the spelling, bound by
the family's own static imports (closed_walk.PLAIN_BODY_CALLS, the a1 file's
_PURE_CALLS and _PURE_AWAITS, the gate file's _PLAIN_CALLS and
_PLAIN_AWAITS). closed_walk.Bindings.listed admits a listed call only when
the walked scope's binding of the spelling IS that provider object.

This file names each provider by its description, written by hand, never
generated from the objects it describes: per component, ("<module>", the
module's __name__) for a module, else (the object's __module__, or for a
method bound to a class its class's __module__, and its __qualname__). The
tests assert that every family's table describes to exactly these entries,
so a provider rebound before the tables were built (`json.loads = writer`
at import) fails there, and that each family's spellings are exactly
FAMILIES[family] (round 9's frozensets, unchanged).

Two providers are notes of their own:
  * StakeRefundRefused is main's own class; its description is main's, and
    the a1 test also requires main's source to bind the name exactly once,
    at the top level, by that class statement.
  * text is SQLAlchemy's, bound through ro_covered's own import of it.
"""

_BI = "builtins"

PROVIDERS = {
    "Counter": (("collections", "Counter"),),
    "GoldTransaction": (("models", "GoldTransaction"),),
    "HTTPException": (("fastapi.exceptions", "HTTPException"),),
    "QueuePollResponse": (("schemas", "QueuePollResponse"),),
    "StakeRefundRefused": (("main", "StakeRefundRefused"),),
    "TeamQueuePollResponse": (("schemas", "TeamQueuePollResponse"),),
    "ValueError": ((_BI, "ValueError"),),
    "_json.dumps": (("<module>", "json"), ("json", "dumps")),
    "_json.loads": (("<module>", "json"), ("json", "loads")),
    "abs": ((_BI, "abs"),),
    "all": ((_BI, "all"),),
    "any": ((_BI, "any"),),
    "asyncio.sleep": (("<module>", "asyncio"), ("asyncio.tasks", "sleep")),
    "bool": ((_BI, "bool"),),
    "datetime.now": (("datetime", "datetime"), ("datetime", "datetime.now")),
    "dict": ((_BI, "dict"),),
    "enumerate": ((_BI, "enumerate"),),
    "float": ((_BI, "float"),),
    "getattr": ((_BI, "getattr"),),
    "hasattr": ((_BI, "hasattr"),),
    "id": ((_BI, "id"),),
    "int": ((_BI, "int"),),
    "isinstance": ((_BI, "isinstance"),),
    "len": ((_BI, "len"),),
    "list": ((_BI, "list"),),
    "math.ceil": (("<module>", "math"), ("math", "ceil")),
    "max": ((_BI, "max"),),
    "min": ((_BI, "min"),),
    "next": ((_BI, "next"),),
    "print": ((_BI, "print"),),
    "random.choice": (("<module>", "random"), ("random", "Random.choice")),
    "repr": ((_BI, "repr"),),
    "round": ((_BI, "round"),),
    "set": ((_BI, "set"),),
    "sorted": ((_BI, "sorted"),),
    "str": ((_BI, "str"),),
    "sum": ((_BI, "sum"),),
    "text": (("sqlalchemy.sql._elements_constructors", "text"),),
    "time.monotonic": (("<module>", "time"), ("time", "monotonic")),
    "time.time": (("<module>", "time"), ("time", "time")),
    "timedelta": (("datetime", "timedelta"),),
    "tuple": ((_BI, "tuple"),),
    "type": ((_BI, "type"),),
    "uuid.UUID": (("<module>", "uuid"), ("uuid", "UUID")),
    "uuid.uuid4": (("<module>", "uuid"), ("uuid", "uuid4")),
    "uuid_mod.uuid4": (("<module>", "uuid"), ("uuid", "uuid4")),
    "zip": ((_BI, "zip"),),
}

# Each family's spellings: round 9's frozensets, unchanged.
FAMILIES = {
    "closed_walk.PLAIN_BODY_CALLS": frozenset({
        "Counter", "_json.dumps", "_json.loads", "abs", "all", "any", "dict",
        "float", "getattr", "id", "isinstance", "len", "math.ceil", "max",
        "min", "repr", "hasattr", "set", "sorted", "sum", "timedelta",
        "tuple", "zip"}),
    "a1._PURE_CALLS": frozenset({
        "GoldTransaction", "HTTPException", "QueuePollResponse",
        "StakeRefundRefused", "TeamQueuePollResponse", "ValueError",
        "_json.loads", "all", "any", "bool", "datetime.now", "dict",
        "enumerate", "float", "int", "isinstance", "len", "list", "min",
        "next", "print", "random.choice", "round", "set", "sorted", "str",
        "text", "time.monotonic", "time.time", "type", "uuid.UUID",
        "uuid.uuid4", "uuid_mod.uuid4"}),
    "a1._PURE_AWAITS": frozenset({"asyncio.sleep"}),
    "gate._PLAIN_CALLS": frozenset({"bool", "int", "str", "list", "text",
                                    "HTTPException"}),
    "gate._PLAIN_AWAITS": frozenset(),
}
