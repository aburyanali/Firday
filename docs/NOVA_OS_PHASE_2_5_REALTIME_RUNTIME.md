# NOVA OS Phase 2.5 Realtime Runtime Architecture

Date: 2026-05-23

## Runtime Evolution

Phase 2.5 upgrades the backend from an API wrapper into a lightweight realtime AI operating runtime. The existing `friday.py` intelligence core remains intact. The new runtime surrounds it with state, sessions, tasks, event orchestration, and private telemetry.

The key design rule is separation:

- Public clients receive cinematic-safe assistant events.
- Admin systems receive private telemetry, reasoning metadata, task lifecycle, and diagnostics.
- The original assistant brain still performs memory, intent, planning, tool choice, and response generation.

## Event Orchestration Strategy

Events are represented by `RuntimeEvent` in `nova_backend/runtime/events.py`.

Supported event families:

- `assistant.boot`
- `assistant.ready`
- `assistant.status`
- `assistant.intent`
- `assistant.reasoning`
- `assistant.memory`
- `assistant.tool_call`
- `assistant.tool_result`
- `assistant.planning`
- `assistant.voice`
- `assistant.token`
- `assistant.message`
- `assistant.error`
- `assistant.shutdown`
- `task.created`
- `task.updated`
- `task.completed`
- `task.failed`

Each event has:

- `event_id`
- `trace_id`
- `session_id`
- `timestamp`
- `type`
- `payload`
- `visibility`

Public events are safe for the frontend. Private events are recorded for administrators and must not be streamed to public clients.

## AI State System

The runtime state machine currently supports:

- `offline`
- `booting`
- `ready`
- `idle`
- `listening`
- `thinking`
- `planning`
- `executing`
- `speaking`
- `error`
- `shutdown`

This state model is intentionally small. It is enough to drive cinematic UI states now, and it can later support wake-word, interruption, multimodal input, and autonomous workers.

## WebSocket Event Lifecycle

For a normal WebSocket assistant turn:

1. Client sends `{ "message": "...", "session_id": "...", "user_id": "..." }`.
2. Runtime emits `assistant.boot` for the turn stream.
3. Runtime creates/updates session state.
4. Runtime creates a task with `task.created`.
5. Assistant enters `thinking`.
6. Existing brain produces intent/reasoning output.
7. Runtime emits public-safe `assistant.intent`.
8. Runtime records private `assistant.reasoning`.
9. Runtime emits memory/planning/tool events if the actual brain path requires them.
10. Runtime streams `assistant.token` chunks.
11. Runtime emits `assistant.message`.
12. Runtime returns to `idle`.

The current token stream is chunked from a completed response. That is not meant to fake intelligence; it establishes the event contract. True provider token streaming can replace the implementation behind the same event names.

## Frontend Synchronization Strategy

The future NOVA OS frontend can subscribe to `/ws/assistant` and bind animations to events:

- `assistant.status`: core AI state, thinking/speaking/idle transitions.
- `assistant.intent`: intent panel or subtle classification animation.
- `assistant.memory`: memory visualization pulse.
- `assistant.planning`: planning interface expansion.
- `assistant.tool_call`: tool execution panel.
- `assistant.voice`: voice waveform/speaking state.
- `assistant.token`: streaming response text.
- `assistant.message`: final message persistence.

The public frontend should never directly request private traces.

## Runtime Session Management

`SessionManager` tracks:

- `session_id`
- `user_id`
- creation/update timestamps
- turn count
- last trace id

This gives the backend stable conversational continuity for future frontend sessions, voice sessions, and long-running agent workflows.

## Agent Task Foundations

`TaskManager` tracks lightweight runtime tasks:

- `queued`
- `running`
- `cancel_requested`
- `completed`
- `failed`

Current assistant turns create `assistant.turn` tasks. Later, the same task model can support coding agents, document generation, website generation, debugging workflows, and cancellable autonomous operations.

## Admin Telemetry Architecture

`TelemetryStore` is an in-memory private ring buffer for runtime events. It provides immediate admin observability without committing to a database schema too early.

Protected endpoints:

- `/admin/runtime`
- `/admin/telemetry/events`
- `/admin/health`

These require `NOVA_ADMIN_API_KEY`. In a production version, this should evolve into role-based auth, persistent trace storage, audit logs, and encrypted memory diagnostics.

## Scalability Implications

This design keeps the runtime modular while avoiding an aggressive rewrite:

- The legacy assistant remains a single protected runtime instance.
- Blocking operations are isolated behind `asyncio.to_thread()`.
- Session/task/event contracts are independent of the assistant implementation.
- True streaming, queues, workers, and distributed traces can be added behind the existing contracts.

Next safe upgrades:

1. Persist private telemetry to SQLite/Postgres.
2. Add cancellable background task execution.
3. Add true OpenAI streaming inside the assistant service.
4. Add structured tool registry events.
5. Add voice input/output event adapters.
6. Add admin role-based authentication.

