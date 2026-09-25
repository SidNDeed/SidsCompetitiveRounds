# PINNED BY DIGEST, not by tag. `python:3.12-slim` is a moving tag, and what
# this image supplies feeds `renderer_fp` -- the Player Cards face key --
# through `runtime_provenance()`.
#
# WHAT IS ACTUALLY HASHED, stated exactly, because an earlier version of this
# comment said "this image's bytes" and that is not what happens.
# `runtime_provenance()` records the interpreter VERSION STRING, Pillow's and
# `regex`'s version strings, a per-feature record for zlib / freetype2 /
# harfbuzz / fribidi / raqm, the layout engine name, and a digest over SELECTED
# PILLOW FILES. Nothing walks the base image, the interpreter binary, or
# libfribidi's bytes. So a rebuild that changed a shared library WITHOUT moving
# any of those strings would produce the SAME fingerprint over different
# pixels, which fails in the quiet direction -- and is why the digest pin below
# matters more rather than less. Two consequences, and the first is the one
# that bites:
#
#   1. The primary and the standby are built from this file at DIFFERENT times.
#      If the tag moves in between, the two boxes bake different interpreter and
#      libfribidi bytes, compute different `renderer_fp`, and therefore disagree
#      about every `face_rev`. The binder route produces the revision and the
#      face route consumes it, so a player whose two requests land on the two
#      boxes gets a 404 for a picture that exists -- and both boxes answer 200
#      on /health, with nothing in either log.
#   2. A rollback would produce a THIRD fingerprint rather than returning to the
#      pre-release one, so the still-warm cache from before the release becomes
#      unreachable and the emergency path runs cold.
#
# Resolved 2026-09-19 from the registry: the OCI index for 3.12-slim, which
# carries linux/amd64. The tag is kept beside the digest for readability only --
# Docker resolves the digest. To move it deliberately, re-resolve and change it
# here in its own commit, expecting every face to re-render once.
FROM python:3.12-slim@sha256:78387bc3881b8273120a12ebe6c1ab22b018ccc2c9adf565ae1ac9b536e184ea

WORKDIR /app

# Text shaping for the Player Cards renderer. Pillow's manylinux wheel bundles
# libraqm and HarfBuzz but loads libfribidi at RUNTIME, so without this package
# the renderer falls back to Pillow's "basic" layout engine, /api/v1/health
# reports pc_raqm=false, and _pc_require_renderer refuses every face route --
# pack open, portrait upload, the public face and the bot's bytes -- with
# text_shaping_unavailable. That is what production did on 2026-09-12: both
# boxes healthy, fonts present, first pack open refused. The release train now
# asserts pc_raqm on both boxes; test_pc_deploy_wiring.py holds this line.
RUN apt-get update && apt-get install -y --no-install-recommends libfribidi0 && rm -rf /var/lib/apt/lists/*

# Install dependencies first (cached layer)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Player Cards renderer fonts. The font FILES are not in the repo (gitignored,
# ~30 MB); fetch_fonts.py pulls each one from a COMMIT-pinned URL and verifies
# it against fonts.lock.json, so every build of a given ref uses identical
# bytes. That is a requirement, not hygiene: the public face route is immutable
# per revision, so a font whose bytes moved under a fixed face_rev would serve
# two different pictures from one cache key.
#
# Own layer, above the code copy and keyed on the lock, so a rebuild that
# changes only Python does not re-download 30 MB. A hash mismatch returns 1 and
# FAILS the build on purpose: main.py imports the renderer inside a try, so a
# fontless image boots happily and answers 503 on every face route -- the
# feature would ship completely inert with clean logs (#438). Fail at build.
COPY assets/fonts/fetch_fonts.py assets/fonts/fonts.lock.json ./assets/fonts/
RUN python assets/fonts/fetch_fonts.py

# Copy application code
COPY . .

# Run with uvicorn.
#
# EXACTLY ONE WORKER — NEVER RAISE THIS. The API keeps live state in process
# memory: the chat WebSocket registry (_ChatManager), the presence dict behind
# the online counter, chat resend nonces, the maintenance flag, and several
# caches. With N workers each process gets its own private copy, so chat
# broadcasts only reach sockets that happened to land on the same worker and
# the online count splits across workers — production bugs #51 and #52, and
# the whole of learning #125.
#
# docker-compose.yml overrides this command and carries the same rule, so the
# value here has never actually run. That is exactly why it mattered: an image
# built and run without the Compose file (a debug container, a future service,
# a copied Dockerfile) would have silently started two workers and reproduced
# both bugs with nothing pointing back here. The image default now agrees with
# the only supported configuration.
#
# If the API ever needs real concurrency, move the shared state to Redis FIRST.
#
# --no-access-log, for the same reason and by the same argument. Around 40
# endpoints authenticate with an HMAC signature passed as a QUERY PARAMETER, and
# uvicorn's access log writes the full request line — so with access logging on,
# every one of those signatures is recorded verbatim into an unrotated container
# log that any `logs:api` reader can pull. docker-compose.yml already passes the
# flag, which is precisely why it was missing here and unnoticed: an image run
# WITHOUT that Compose file (a debug container, a one-off `docker run`, a future
# service copying this Dockerfile) inherited this CMD and started logging
# credentials with nothing pointing back here. The image default now matches the
# only supported configuration rather than depending on the caller to supply it.
#
# App-level diagnostics are unaffected: the [TAG] print() lines are where real
# diagnosis happens, and PYTHONUNBUFFERED keeps them prompt.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--no-access-log"]
