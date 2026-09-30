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

## 10. 图片目录调整（2026-09-30）

按用户确认，R2 图片改为 `discord-images/{频道ID}/{原消息月份}/{SHA256}.{扩展名}`。
月份按 Asia/Tokyo 计算，同频道同月去重，不跨频道或月份共享文件。旧哈希目录使用
显式维护命令迁移，完整读取校验后切换数据库引用，再删除旧对象；支持中断后继续。
已保留升级前数据库备份，数据库结构已升级到 `0006_channel_media_layout`。
Docker 后端 Ruff、格式、迁移一致性及 66 项测试通过；运行中 Collector 已恢复连接。
真实迁移完成：556 个旧对象重排为 557 个新对象，旧云端对象与旧数据库引用均为 0，
567 条归档引用有效；3 个频道的稳定图片接口抽检通过。另有 10 个既有历史图片
归档失败任务尚未恢复，不计入已存对象迁移。
云端迁移验收结果与恢复方法见 [R2_IMAGE_ARCHIVE.md](docs/R2_IMAGE_ARCHIVE.md)。
本文件前面的开发顺序属于早期计划，当前已实现范围以项目说明、架构及上述验收文档为准。

## 11. 采集可靠性补齐（2026-10-01）

现有 R2 版本已提交为 `8e99f01`，新任务在 `feat/collector-reliability` 开发。
新增原始编辑、删除/批量删除监听和防复活墓碑，独立补采断点与持久重试，首次
实时/补采/未知来源、入库延迟及版本时效提示。面板单独显示频道补采状态。
Docker `make quality` 前后端检查与 73 项测试通过；离线旧消息变更、真实事件与
长期观察边界见 [COLLECTOR_RELIABILITY.md](docs/COLLECTOR_RELIABILITY.md)。
本机已升级到 `0007`，真实连接正常，4 个来源本轮补采完成并新增 44 条历史消息；
稳定图片接口内容校验通过，PC 消息页观察到自然新消息显示“实时”。真实编辑/删除
及 24–48 小时连续运行尚待验收。升级前数据库备份位于本机临时目录，详见上文档。
