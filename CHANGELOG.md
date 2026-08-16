# Changelog

All notable changes to AgentState are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/); versions follow SemVer.

## [0.3.0] — 2026-08-16 — commit `b0c6fb0`

### Added

- **`POST /manifest`** — an agent commits its planned step list *before* execution starts, bound to the active lease. This is the enabling primitive for omission detection.
- **`GET /ledger?work=<job>&diff=1`** — the ledger response now carries a `diff` object:
  - `has_manifest` — whether a plan was committed
  - `planned` — the committed step list
  - `holes` — planned steps that were never logged
  - `extras` — logged steps that were not planned
- **`POST /complete`** — response now includes the same `diff`, so completion surfaces gaps immediately.

### Behavioral notes

- **Omission becomes visible.** The previous audit model proved *alteration* (nothing changed after write, via hash chain) but not *completeness* (whether the write happened at all). With a committed manifest, an execution that failed before its ledger write shows up as a `hole` with an address, not as a mystery. Spec credit: community review by `cwahq`.

### Proof (regression fixture, run live)

- Committed manifest: `[a, b, c]`
- Executed: `a`, `c`, plus a stray `x` (step `b` intentionally never logged)
- `POST /complete` → `diff: { holes: ["b"], extras: ["x"] }`
- `GET /ledger?diff=1` → `integrity: ok` with the same `diff`

## [0.2.0] — 2026-08-16 — commit `1a70f22`

### Added

- **Hash-chained ledger** — every entry commits the previous entry's hash (SHA-256 over previous hash + full entry).
- **Built-in integrity verification** — `GET /ledger` returns `integrity: ok | broken` plus `first_broken_event_id`.
- Verified by rewriting a past row directly in the database: integrity returned `broken`, exact row flagged.

### Fixed

- **Idempotency scoping** (from community review): unique key changed from `(work_ref, step)` to `(work_ref, lease, step)` so a reaped and re-leased job can legitimately re-log rerun steps without double-executing (commit `f3a2f64`).

## [0.1.0] — 2026-08-16 — commit `8ffa247`

### Added

- First open source release of the state-safety layer:
  - `POST /lease` — durable job lease with expiry
  - `POST /heartbeat` — lease extension; 409 on expiry
  - `POST /event` — idempotent planned-vs-executed steps
  - `POST /complete` — safe job close
  - `GET /ledger` — append-only audit trail
  - Recovery reaper — expired leases flip to `abandoned`, each abandonment logged as its own event
- Zero-dependency server (Python stdlib + SQLite), OpenClaw-compatible skill manifest, MIT license.