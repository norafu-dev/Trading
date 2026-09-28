# AI Trading System — Project Progress & Handoff

> Purpose: starting context for a new development conversation.

## 1. Project status

The implementation project has **not been created yet**.

The work so far has primarily been architecture/backend learning and trading-system design.

The next goal is to stop expanding the theoretical scope temporarily and implement the first small vertical slice.

## 2. Current milestone

# M1 — Discord Message Ingestion

Implement the **minimal Discord Collector** first.

Target flow:

```text
Discord
↓
receive message
↓
normalize required fields
↓
idempotent persistence
↓
PostgreSQL
```

This milestone intentionally stops before AI parsing and trading.

## 3. M1 minimum scope

The Collector should be able to ingest messages from configured Discord locations and persist normalized message data.

Initial fields should include concepts such as:

```text
message_id
guild_id
channel_id
thread_id          # nullable where appropriate
author_id
content
created_at
attachments
```

Exact database schema should be designed during implementation rather than assumed from this handoff.

### Required reliability property

Discord messages may be delivered/processed more than once.

Therefore:

```text
Discord message_id
→ database UNIQUE constraint
→ repeated ingestion must not create duplicate business records
```

The worker/process should be safe if it crashes after inserting a message and later receives the same Discord message again.

## 4. Explicitly out of scope for the first implementation

Do **not** expand M1 into all later architecture.

For the first checkpoint, exclude:

- AI/LLM message parsing.
- Signal generation.
- Trader Target Position.
- Trade Execution.
- Bitget integration.
- CCXT order submission.
- Complex trading state machines.
- Backtesting.
- Complex priority infrastructure.
- Manual-position policy.

The goal is to establish one reliable working ingestion path.

## 5. Likely later flow

After M1 works:

```text
Discord Collector
↓
PostgreSQL message
↓
AI Parse Task
↓
Redis / Celery
↓
AI Worker
↓
structured Signal
```

Then later:

```text
Signal
↓
Target State
↓
Execution
↓
Order
↓
Bitget
↓
Fill
↓
Position / Balance
↓
Reconciliation
```

## 6. Architectural principles already learned

Implementation should preserve these principles where relevant:

- PostgreSQL is durable business storage.
- Redis is infrastructure, not the authoritative store for core trading facts.
- Duplicate task/message delivery is expected; design idempotently.
- Use database constraints/atomic operations for correctness instead of only Python checks.
- Outbox may be introduced where DB commit + task publication must be reliable.
- Keep FastAPI request handling separate from long-running workers.
- Separate workloads into queues when workload characteristics justify it.
- Do not equate Celery task success with business success.
- Trading side effects require reconciliation before ambiguous retries.

## 7. Suggested first development-session workflow

When starting the new project/conversation:

```text
1. Read:
   - LEARNING_NOTES.md
   - TRADING_EXECUTION.md
   - PROJECT_PROGRESS.md

2. Create the minimal project skeleton.

3. Before coding, describe:
   - proposed Discord Collector boundaries
   - minimal database model
   - process/runtime choice
   - how duplicate messages are handled

4. Implement only the smallest useful M1 slice.

5. Test:
   - normal message ingestion
   - duplicate message ingestion
   - restart/reconnect behavior

6. Update this progress document after the checkpoint.
```

## 8. Learning workflow

Use development to reinforce the concepts rather than attempting to learn the entire trading architecture before writing code.

Preferred sequence:

```text
Backend/worker fundamentals learned
        ↓
M1 Discord Collector implementation
        ↓
AI Parser implementation
        ↓
return to remaining Trading Execution topics
        ↓
Trading Worker implementation
```

When a real implementation problem exposes a missing concept, learn that concept at that point and then apply it immediately.

## 9. Next task

**Create the project and implement M1 — Discord Message Ingestion.**

The first checkpoint is complete when:

```text
a real/configured Discord message
↓
is captured
↓
normalized
↓
persisted once in PostgreSQL
↓
duplicate processing does not create a second record
```

No real-money trading functionality should be required for this checkpoint.
