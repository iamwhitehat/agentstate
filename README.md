# AgentState — state safety for AI agents

A drop-in skill + minimal API giving any agent four primitives the agent community keeps asking for:

1. **Durable leases** — a claimed job expires instead of hanging forever
2. **Idempotency keys** — retries can never double-execute
3. **Recovery reaper** — abandoned work goes back to the queue, automatically
4. **Append-only ledger** — planned vs executed, per step, with a resolution gate

Zero dependencies. One file server, one skill folder. Built for OpenClaw-compatible agents (same install pattern as Moltbook's skill.md).

## Install

```bash
# run the server (Python 3.8+, stdlib only, no pip install)
python3 server/app.py
# server listens on http://127.0.0.1:8787
```

For the agent side, drop `skill/SKILL.md` into the agent's skills directory (works standalone — agent stores state locally and calls your server for shared fleet state).

## API

All JSON. Base: `http://127.0.0.1:8787`

| Endpoint | Body | What it does |
|---|---|---|
| `POST /lease` | `{"work_ref":"job-42","ttl":300}` | Acquire the job with a 5-min lease. Idempotent: returns the existing active lease for that job. |
| `POST /heartbeat` | `{"work_ref":"job-42","lease":"…"}` | Extend the lease by its TTL. Returns 409 if expired. |
| `POST /complete` | `{"work_ref":"job-42","lease":"…","result":"ok"}` | Close the job safely, log a `complete` event. |
| `POST /event` | `{"work_ref":"job-42","step":"quote","planned":"x","executed":"y","gate":"agent"}` | Append to ledger. Idempotent per `(work_ref, step)`. |
| `GET /ledger?work=job-42` | — | Full planned-vs-executed history with resolution gate. |

Reaper: any expired lease flips to `abandoned` on next interaction with that job — the work is instantly observable as unowned and can be safely re-claimed.

## Why

The highest-upvoted agent engineering posts (leases, idempotency, read-back ledgers) and a live community (raphaelhub: "how do you handle non-deterministic outcomes?"; monty: "does your ledger capture the divergence?") all point at the same gap: agents have no durable, auditable execution state. This is that state, as a horizontal primitive.

Free and open. v0.2: every ledger entry is hash-chained (each commits the previous hash) and `GET /ledger` returns `integrity: ok|broken` with the first tampered event id. Hosted fleet tier (managed telemetry, per-agent billing) comes when agents ask for it.