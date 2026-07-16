# NOVA OS Phase 2 Backend Foundation

Date: 2026-05-23

## What This Slice Adds

This phase introduces a production backend boundary around the existing Friday intelligence runtime without rewriting it.

Added:

- FastAPI application layer: `nova_backend/app.py`
- Health endpoints: `/health`, `/api/health`
- Chat API: `/api/chat`
- WebSocket event stream: `/ws/assistant`
- Admin-only health scaffold: `/admin/health`
- Async-safe assistant service bridge: `nova_backend/services/assistant_service.py`
- Structured logging setup: `nova_backend/logging_config.py`
- Request lifecycle middleware with trace IDs and latency headers
- Secure admin API key config placeholder
- Backend runner: `run_backend.py`

## Why This Architecture

The existing intelligence in `friday.py` is valuable and should remain the source of truth during early backend evolution. The new backend package wraps that runtime with service, API, WebSocket, and observability boundaries. This creates the future shape of NOVA OS while avoiding a risky rewrite.

## Public Layer

Public routes are designed for frontend integration:

- `/api/chat` returns a complete assistant turn with trace ID, intent, confidence, response, and lifecycle events.
- `/ws/assistant` streams structured realtime events for future cinematic UI states.
- `/health` reports service readiness without exposing logs, memory rows, traces, prompts, or internals.

Current event types:

- `assistant.status`
- `assistant.intent`
- `assistant.completed`
- `assistant.token`
- `assistant.message`
- `error.public`

The current token stream is simulated from completed responses. This is deliberate: it gives the frontend a stable realtime contract now, while true model-token streaming can be added later behind the same event interface.

## Private Admin Layer

The admin layer begins with `/admin/health`, protected by `NOVA_ADMIN_API_KEY`.

Planned protected surfaces:

- logs
- runtime telemetry
- reasoning traces
- tool execution traces
- memory diagnostics
- provider latency
- model usage analytics
- infrastructure health

These must never be exposed through public routes or client-safe WebSocket events.

## Runtime Strategy

`AssistantService` lazily initializes `FridayAssistant` only when `OPENAI_API_KEY` is configured. Health checks can run in degraded mode without booting the full AI runtime.

The service uses:

- an async lock to protect the current single runtime instance
- `asyncio.to_thread()` for blocking legacy operations
- trace IDs for request correlation
- silent voice substitution during API execution so HTTP/WebSocket calls do not speak aloud

## Migration Impact

No memory systems were removed.
No reasoning systems were removed.
No voice systems were removed.
No existing CLI entrypoint was replaced.

This is an additive backend layer. The legacy assistant can still run through `friday.py`, and the new server can run through:

```bash
python3 run_backend.py
```

## Next Safe Steps

1. Extract a first-class trace service.
2. Add persistent private execution traces.
3. Add a formal tool registry while preserving current tools.
4. Convert blocking knowledge and LLM calls to async service methods.
5. Add real token streaming from the LLM provider.
6. Add user/session models.
7. Add admin diagnostics pages after auth is in place.

