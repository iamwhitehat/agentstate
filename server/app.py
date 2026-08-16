#!/usr/bin/env python3
"""AgentState server - leases, idempotency, recovery reaper, append-only ledger.

Zero dependencies: Python 3.8+ stdlib only.
Run:  python3 server/app.py   (listens on 127.0.0.1:8787)
"""
import json
import sqlite3
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

DB_PATH = "agentstate.db"
HOST, PORT = "127.0.0.1", 8787
LOCK = threading.Lock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS leases (
    work_ref   TEXT PRIMARY KEY,
    lease_id   TEXT NOT NULL,
    status     TEXT NOT NULL,          -- active | done | abandoned
    lease_until REAL NOT NULL,
    heartbeat_at REAL NOT NULL,
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS events (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    work_ref   TEXT NOT NULL,
    step       TEXT NOT NULL,
    planned    TEXT,
    executed   TEXT,
    gate       TEXT,
    at         REAL NOT NULL,
    UNIQUE(work_ref, step)
);
CREATE INDEX IF NOT EXISTS idx_events_work ON events(work_ref);
"""


def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def reap(conn, work_ref):
    """Expire stale leases; each abandonment is itself a ledger event."""
    now = time.time()
    row = conn.execute("SELECT * FROM leases WHERE work_ref=?", (work_ref,)).fetchone()
    if row and row["status"] == "active" and row["lease_until"] < now:
        conn.execute("UPDATE leases SET status='abandoned' WHERE work_ref=?", (work_ref,))
        conn.execute(
            "INSERT OR IGNORE INTO events(work_ref, step, planned, executed, gate, at) "
            "VALUES(?, 'lease-expired', 'complete', 'abandoned', 'reaper', ?)",
            (work_ref, now),
        )


class Handler(BaseHTTPRequestHandler):
    def _json(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read(self):
        n = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(n)) if n else {}

    def do_GET(self):
        path = urlparse(self.path).path
        if path != "/ledger":
            self._json(404, {"error": "not found"})
            return
        q = parse_qs(urlparse(self.path).query)
        work = (q.get("work") or q.get("work_ref") or [""])[0]
        if not work:
            self._json(400, {"error": "work required"})
            return
        with LOCK, db() as conn:
            rows = conn.execute(
                "SELECT step, planned, executed, gate, at FROM events "
                "WHERE work_ref=? ORDER BY id", (work,)
            ).fetchall()
            self._json(200, {"work_ref": work, "events": [dict(r) for r in rows]})

    def do_POST(self):
        path = urlparse(self.path).path
        try:
            body = self._read()
            with LOCK, db() as conn:
                if path == "/lease":
                    self._lease(conn, body)
                elif path == "/heartbeat":
                    self._heartbeat(conn, body)
                elif path == "/complete":
                    self._complete(conn, body)
                elif path == "/event":
                    self._event(conn, body)
                else:
                    self._json(404, {"error": "not found"})
        except Exception as e:
            self._json(400, {"error": str(e)})

    def _lease(self, conn, body):
        work_ref = body.get("work_ref")
        ttl = float(body.get("ttl", 300))
        if not work_ref:
            raise ValueError("work_ref required")
        reap(conn, work_ref)
        row = conn.execute("SELECT * FROM leases WHERE work_ref=?", (work_ref,)).fetchone()
        now = time.time()
        if row and row["status"] == "active":
            self._json(200, {"lease": row["lease_id"], "expires_at": row["lease_until"], "status": "active"})
            return
        lease_id = str(uuid.uuid4())
        conn.execute(
            "INSERT OR REPLACE INTO leases(work_ref, lease_id, status, lease_until, heartbeat_at, created_at) "
            "VALUES(?, ?, 'active', ?, ?, ?)",
            (work_ref, lease_id, now + ttl, now, now),
        )
        self._json(200, {"lease": lease_id, "expires_at": now + ttl, "status": "active"})

    def _heartbeat(self, conn, body):
        work_ref, lease = body.get("work_ref"), body.get("lease")
        row = conn.execute("SELECT * FROM leases WHERE work_ref=?", (work_ref,)).fetchone()
        if not row or row["lease_id"] != lease:
            raise ValueError("unknown lease")
        now = time.time()
        if row["status"] != "active" or row["lease_until"] < now:
            self._json(409, {"error": "lease expired", "status": row["status"]})
            return
        ttl = (row["lease_until"] - row["heartbeat_at"]) or 300
        conn.execute(
            "UPDATE leases SET lease_until=?, heartbeat_at=? WHERE work_ref=?",
            (now + ttl, now, work_ref),
        )
        self._json(200, {"lease": lease, "expires_at": now + ttl, "status": "active"})

    def _complete(self, conn, body):
        work_ref, lease = body.get("work_ref"), body.get("lease")
        row = conn.execute("SELECT * FROM leases WHERE work_ref=?", (work_ref,)).fetchone()
        if not row or row["lease_id"] != lease:
            raise ValueError("unknown lease")
        conn.execute("UPDATE leases SET status='done' WHERE work_ref=?", (work_ref,))
        conn.execute(
            "INSERT OR IGNORE INTO events(work_ref, step, planned, executed, gate, at) "
            "VALUES(?, 'complete', 'run', ?, 'agent', ?)",
            (work_ref, body.get("result", "ok"), time.time()),
        )
        self._json(200, {"work_ref": work_ref, "status": "done"})

    def _event(self, conn, body):
        work_ref, step = body.get("work_ref"), body.get("step")
        if not work_ref or not step:
            raise ValueError("work_ref and step required")
        conn.execute(
            "INSERT OR IGNORE INTO events(work_ref, step, planned, executed, gate, at) "
            "VALUES(?, ?, ?, ?, ?, ?)",
            (work_ref, step, body.get("planned"), body.get("executed"),
             body.get("gate", "agent"), time.time()),
        )
        self._json(200, {"logged": step})


if __name__ == "__main__":
    with LOCK, db() as conn:
        conn.executescript(SCHEMA)
    print(f"AgentState listening on http://{HOST}:{PORT}")
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()