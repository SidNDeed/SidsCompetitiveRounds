"""A stand-in for the automatic post-match log upload, for the L6 contract in
test_ticket_redaction.py. Mounted on that file's test app only, never on
main.app.

The real route, POST /api/v1/logs/auto, is backend/api/auto_logs.py on the
v1.41.0 branches and is not on this tree, so the contract's two cases against
it skip here and run at merge. This module lets the same checker run here, in
both directions: its write path is the real route's, reduced to what the
contract judges --

  * the request model's tail clamp of log_text to the bug-report ceiling
    (auto_logs.AutoLogRequest._clamp_log there);
  * the write-time scrub through main._scrub_pass_one, late-imported as the
    real route does, in a worker thread;
  * the gzip, the file write under BUG_REPORT_LOG_DIR, the kind='auto' row.

It is written the way a CONFORMING upload must be: the credential rule over
the log as sent, then the clamp; the scrub, then the write. The controls in
ticket_redaction_controls.py plant here the defects the contract exists to
catch (no scrub, the scrub after the write, the clamp before the rule) and an
inert extra call the contract must tolerate.
"""
import asyncio
import gzip
import json
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, field_validator
from sqlalchemy import text

import log_redaction
from database import get_db

# The real model's ceiling (schemas.BUG_REPORT_LOG_MAX_CHARS on the v1.41.0
# branches, the value BugReportRequest clamps log_text to on this tree).
LOG_MAX_CHARS = 12_000_000

router = APIRouter(prefix="/api/v1/ticket-redaction-standin/logs")


class StandinAutoLogRequest(BaseModel):
    steam_id: str
    log_text: str | None = None

    @field_validator("log_text", mode="before")
    @classmethod
    def _clamp_log(cls, v):
        # Keep the TAIL, as the real model does -- after the credential rule.
        if isinstance(v, str):
            v = log_redaction.redact_credentials(v)     # the rule, over the log as sent
            if len(v) > LOG_MAX_CHARS:
                v = v[-LOG_MAX_CHARS:]                  # then the tail is kept
        return v


@router.post("/auto")
async def upload_auto_log(request: Request, db=Depends(get_db)):
    from main import _bug_report_log_path, _scrub_pass_one     # late import, as the real route does

    req = StandinAutoLogRequest.model_validate(json.loads(await request.body()))
    log_blob = (req.log_text or "").strip()
    if not log_blob:
        raise HTTPException(status_code=400, detail="log_text required")
    scrubbed, counts, _ids = await asyncio.to_thread(_scrub_pass_one, log_blob)
    report_id = uuid.uuid4()
    data = gzip.compress(scrubbed.encode("utf-8", errors="replace"))
    path = _bug_report_log_path(str(report_id))
    with open(path, "wb") as f:
        f.write(data)
    await db.execute(
        text("INSERT INTO bug_reports (id, steam_id, severity, category, kind, description,"
             " log_filename, log_bytes)"
             " VALUES (CAST(:id AS uuid), :sid, 'low', 'other', 'auto', 'stand-in upload', :f, :b)"),
        {"id": str(report_id), "sid": req.steam_id, "f": path.name, "b": len(data)})
    await db.commit()
    return {"status": "received", "id": str(report_id)}
