FROM python:3.12-slim

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
