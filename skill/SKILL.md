# AgentState Skill

A state-safety layer for agents: leases with expiry, idempotency, a recovery reaper, and an append-only planned-vs-executed ledger.

## Install

```
mkdir -p ~/.moltbot/skills/agentstate
curl -s https://<host>/skill/SKILL.md > ~/.moltbot/skills/agentstate/SKILL.md
```

Configure the server URL in your agent config (`AGENTSTATE_URL`, default `http://127.0.0.1:8787`).

## Usage

### Before starting any job
```json
POST {AGENTSTATE_URL}/lease
{"work_ref": "<job_id>", "ttl": 300}
```
Returns `{"lease": "<lease_id>", "expires_at": ..., "status": "active"}`.
If the job is already leased by you, the same lease is returned (idempotent).

### Keep a long job alive (every few minutes)
```json
POST {AGENTSTATE_URL}/heartbeat
{"work_ref": "<job_id>", "lease": "<lease_id>"}
```
Extends the lease by its TTL. A 409 means the lease expired — stop, log, and re-lease: the job is no longer owned by you.

### Trace every step (why it works — honesty)
```json
POST {AGENTSTATE_URL}/event
{
  "work_ref": "<job_id>",
  "step": "extract_invoices",
  "planned": "parse 3 PDFs",
  "executed": "parsed 2, one corrupt",
  "gate": "agent"
}
```
Every step is appended. Duplicate `(work_ref, step)` is ignored — retries cannot double-log.

### On completion
```json
POST {AGENTSTATE_URL}/complete
{"work_ref": "<job_id>", "lease": "<lease_id>", "result": "ok"}
```

### Audit anytime
```bash
GET {AGENTSTATE_URL}/ledger?work=<job_id>
```
Returns all steps with planned vs executed and the gate (agent or human) that resolved any divergence.

## Recovery rule

Never trust a lease; trust the ledger. If your process dies mid-job, the lease expires and the reaper marks the job `abandoned`. Anyone (including you, on retry) can re-lease it. The abandoned state is visible in the ledger — a gap without a recorded resolution is itself an event.

## Guarantees

- Leases expire; nothing hangs forever.
- Steps are idempotent; retries do not double-execute or double-log.
- The ledger is append-only and the audit trail survives the operator.