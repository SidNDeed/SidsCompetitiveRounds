FROM python:3.12-slim

WORKDIR /app

# Install dependencies first (cached layer)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

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
