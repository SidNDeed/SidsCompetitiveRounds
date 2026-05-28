-- 087_clear_orphaned_bug_logs.sql
--
-- Logs for bug reports #2/#3/#4 were written into the API container's
-- writable layer (no bind mount existed) and got destroyed by repeated
-- `docker compose up -d --build api` cycles during initial deploys. The
-- log_filename column points to .log.gz files that no longer exist on
-- disk, so the admin viewer shows a [log] tag but reads empty content.
--
-- Going forward, docker-compose.yml has a bind-mount to /opt/competitive-rounds/bug-reports
-- on the host so new logs persist. This one-shot migration clears the
-- orphan pointers so the UI doesn't keep lying about logs being available.

UPDATE bug_reports
   SET log_filename = NULL,
       log_bytes    = NULL
 WHERE log_filename IS NOT NULL
   AND created_at < NOW();   -- safe filter: only existing rows, not anything new
