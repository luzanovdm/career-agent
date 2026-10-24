#!/usr/bin/env python3
"""Observe a fictional database commit read-only; never mutate application state."""
import json
from pathlib import Path
import sqlite3
import sys
import time

database, target = Path(sys.argv[1]).resolve(), int(sys.argv[2])
connection = sqlite3.connect(database.as_uri() + "?mode=ro", uri=True, isolation_level=None)
print(json.dumps({"ready": True, "poll_interval_ms": 5}), flush=True)
deadline = time.monotonic() + 20
while time.monotonic() < deadline:
    started = time.time_ns()
    revision = connection.execute("SELECT revision FROM workspace").fetchone()[0]
    observed = time.time_ns()
    if revision >= target:
        print(json.dumps({"revision": revision, "observed_ns": observed,
                          "query_duration_ns": observed - started, "poll_interval_ms": 5}), flush=True)
        break
    time.sleep(0.005)
else:
    raise SystemExit("No target committed revision observed within 20 seconds.")
connection.close()
