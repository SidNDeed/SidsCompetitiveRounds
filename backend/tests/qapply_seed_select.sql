SELECT q.id AS quarantine_id,
       (q.payload->>'photon_room_id') AS room,
       q.group_id AS lobby_id,
       CASE WHEN CAST(substring((q.payload->>'photon_room_id') FROM '_r([0-9]+)\n?$') AS numeric) BETWEEN 1 AND 999
            THEN CAST(CAST(substring((q.payload->>'photon_room_id') FROM '_r([0-9]+)\n?$') AS numeric) AS int4)
       END AS game_number,
       CASE WHEN q.group_id IS NOT NULL
             AND CAST(substring((q.payload->>'photon_room_id') FROM '_r([0-9]+)\n?$') AS numeric) BETWEEN 1 AND 999
            THEN 'seed' ELSE 'refuse'
       END AS decision
  FROM match_report_quarantine q
 WHERE q.mode = 'ffa' AND q.status = 'credited'
 ORDER BY q.group_id, q.id;
