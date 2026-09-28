# AI Trading System — Learning Notes

> Purpose: compact handoff notes for future development sessions.
> This file records concepts already learned and accepted, not the original teaching dialogue.

## 1. Core backend responsibilities

- **FastAPI**: HTTP/API layer. Handles routes, request/response flow, and invokes business logic.
- **Pydantic**: validates and serializes structured request/response data.
- **SQLAlchemy**: ORM/data-access layer between Python and PostgreSQL.
- **Alembic**: database schema migrations.
- **PostgreSQL**: durable source of truth for business data.
- **Redis**: fast in-memory infrastructure used for queues, cache, locks/coordination, and other temporary state. Redis is not the durable source of truth for core trading data.
- **Celery**: background task execution and queue routing.

## 2. FastAPI vs Worker

FastAPI should handle short-lived HTTP work. Long-running or asynchronous jobs should be delegated to workers.

```text
FastAPI / Discord Collector
        ↓
   create task
        ↓
    Redis Broker
        ↓
   Celery Worker
```

Typical worker categories:

```text
AI Queue        → AI Worker
Trade Queue     → Trade Worker
Backtest Queue  → Backtest Worker
```

Separate queues prevent a slow workload such as backtesting from blocking latency-sensitive trading work.

## 3. I/O vs CPU work

- Database, HTTP, Redis, exchange API and AI API calls are primarily **I/O-bound**.
- `async/await` helps concurrency while waiting for I/O.
- Backtesting and heavy calculations may be **CPU-bound**.
- Async does not create additional CPU capacity.

Initial Celery direction:

- AI Worker: I/O-heavy; threads are reasonable initially.
- Trade Worker: I/O-heavy but concurrency must be conservative because ordering, rate limits and safety matter.
- Backtest Worker: CPU-heavy; prefork/processes are more appropriate.

## 4. Queue routing and priority

Routing answers **which queue should execute this task**.

Priority answers **which task within a workload should run first**.

Prefer separate queues/workers before introducing complicated priority logic.

Latency-sensitive examples:

```text
Emergency close / risk action
        ↓
Normal trading
        ↓
AI parsing
        ↓
Historical backtesting
```

Beware starvation: continuously arriving high-priority tasks can prevent lower-priority work from running.

## 5. Retry + Backoff

Do not retry simply because an operation failed.

First ask:

1. Is the failure temporary or deterministic?
2. Could retrying duplicate a side effect?

Temporary, side-effect-safe failures may use exponential backoff.

Deterministic failures such as invalid parameters should normally not retry.

Trading API calls require stricter handling because an ambiguous response may hide a successfully created order.

## 6. Idempotency

Distributed tasks may execute more than once. The practical goal is:

> Repeated execution must not create repeated business results.

Examples:

- Discord `message_id` should have a database UNIQUE constraint.
- Exchange `trade_id` / Fill ID should be UNIQUE.
- Executions and Orders should have stable internal IDs.
- Exchange orders should use a stable `clientOrderId` where supported.

## 7. Late ACK

With late acknowledgement, a worker acknowledges a task only after successful processing.

```text
Worker receives task
↓
processes it
↓
success
↓
ACK
```

If the worker dies before ACK, the task may be delivered again.

Therefore Late ACK requires idempotent business logic.

## 8. Outbox Pattern

Outbox protects the boundary between committing business data and publishing a background task/event.

```text
BEGIN
  write business data
  write outbox event
COMMIT

Outbox Worker
↓
publish task
```

Key rule:

> **Outbox prevents loss; idempotency prevents duplication.**

## 9. Worker race conditions

Avoid:

```text
SELECT task
↓
Python checks status == queued
↓
UPDATE
```

Two workers can both observe the same old state.

Prefer atomic state acquisition, for example:

```sql
UPDATE tasks
SET status = 'running'
WHERE id = :id
  AND status = 'queued';
```

Only the worker that updates one row acquired the task.

## 10. Lease + Heartbeat

A worker should not own a task forever.

```text
worker_id = worker-A
status = running
lease_expires_at = ...
```

Heartbeat extends the lease.

If the worker dies, the lease eventually expires and another worker can recover the task.

Lease/heartbeat reduces zombie tasks but does not replace idempotency.

## 11. State machines

A status field should have explicit legal transitions.

Example:

```text
QUEUED
  ↓
RUNNING
  ├─→ COMPLETED
  ├─→ RETRYING → RUNNING
  └─→ FAILED
```

Illegal backward transitions should be rejected rather than silently accepted.

## 12. Monitoring

Distinguish infrastructure state from business state.

- Celery/Flower: whether a Python background task ran successfully.
- PostgreSQL: whether the actual business operation succeeded.
- Logs: why something failed.
- Metrics: queue backlog, throughput, latency, failure rate, worker availability.

A Celery task marked `SUCCESS` does **not** mean an exchange Order is `FILLED`.

Use a `correlation_id` / `trace_id` to connect:

```text
Discord Message
→ AI Task
→ Signal
→ Execution
→ Exchange Order
```

## 13. Redis mental model

Redis primarily keeps data in memory, so memory-only data can disappear after restart depending on persistence configuration.

Redis can persist snapshots/logs, but PostgreSQL remains the durable business source of truth for this project.

For temporary state stored under a single key, updating that key replaces the previous value rather than continually creating new independent records. TTL should be used where temporary keys need automatic expiration.

## 14. Principles already established

1. PostgreSQL is the durable business source of truth.
2. Redis/Celery coordinate asynchronous work; they do not define trading truth.
3. Separate workloads into queues.
4. Design every important worker assuming duplicate execution is possible.
5. Use Outbox to prevent lost work and idempotency to prevent duplicated effects.
6. Use state machines instead of unrestricted status mutation.
7. External side effects require more caution than ordinary computation.
8. Infrastructure success and business success are different concepts.
