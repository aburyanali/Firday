# NOVA OS Multi-Provider Runtime Architecture

## Purpose

NOVA now has a provider orchestration layer around the existing intelligence system. The goal is not to replace the original assistant core; it is to keep the runtime alive when a remote provider is slow, quota-limited, unavailable, or offline.

## Provider Stack

Current providers:

- OpenAI: primary heavy reasoning provider.
- Perplexity: factual/search-oriented provider and remote backup path.
- Ollama: local inference engine for fast local/offline operation.
- Local fallback: instant deterministic degraded-mode responder.
- Emergency fallback: final safety layer if every other provider fails.

Environment controls:

- `OPENAI_API_KEY`
- `OPENAI_MODEL`
- `PERPLEXITY_API_KEY`
- `PERPLEXITY_MODEL`
- `OLLAMA_BASE_URL`
- `OLLAMA_MODEL`
- `PROVIDER_FIRST_TOKEN_TIMEOUT_SECONDS`
- `PROVIDER_REQUEST_TIMEOUT_SECONDS`

## Runtime Files

- `nova_backend/providers/unified_stream.py`: shared provider protocol, stream chunks, and provider-safe errors.
- `nova_backend/providers/provider_router.py`: intent-aware routing policy.
- `nova_backend/providers/provider_manager.py`: async failover manager, first-token race, provider telemetry, reliability accounting.
- `nova_backend/providers/openai_provider.py`: OpenAI streaming adapter.
- `nova_backend/providers/perplexity_provider.py`: Perplexity OpenAI-compatible streaming adapter.
- `nova_backend/providers/ollama_provider.py`: Ollama HTTP streaming adapter.
- `nova_backend/providers/local_stream_adapter.py`: token pacing for local fallback streams.
- `nova_backend/providers/fallback_engine.py`: degraded and emergency local response engines.
- `nova_backend/providers/local_fallback_engine.py`: compatibility export for local fallback engines.

## Routing Policy

Fast short prompts:

1. Ollama
2. Local fallback
3. OpenAI
4. Perplexity
5. Emergency

Factual/search prompts:

1. Perplexity
2. OpenAI
3. Ollama
4. Local fallback
5. Emergency

Heavy reasoning prompts:

1. OpenAI
2. Perplexity
3. Ollama
4. Local fallback
5. Emergency

Balanced prompts:

1. Ollama
2. Local fallback
3. OpenAI
4. Perplexity
5. Emergency

## Streaming Contract

Every provider exposes an async token stream. `ProviderManager.stream()` emits structured runtime events:

- `route`
- `provider_start`
- `first_token`
- `token`
- `failover`
- `completed`

The assistant service converts these into NOVA runtime events:

- `assistant.provider`
- `assistant.failover`
- `assistant.degraded`
- `assistant.voice`
- `assistant.token`
- `assistant.message`

This keeps WebSocket clients alive across provider failures and lets the cinematic frontend animate provider changes without exposing raw internal errors.

## Admin And Public Boundary

Public runtime events expose safe provider labels and degraded status only. Raw errors, provider internals, logs, traces, memory stores, and reliability details remain admin/private.

Admin provider status is available through:

- `/admin/providers`

This route is protected by the existing admin dependency and is intended for future role-based admin tooling.

## Frontend Synchronization

The frontend store now tracks:

- active provider label
- active model
- degraded mode
- failover events
- token stream activity

Provider labels shown in the UI:

- `OPENAI LINK`
- `PERPLEXITY LINK`
- `LOCAL CORE`
- `LOCAL FALLBACK`
- `DEGRADED MODE`

## Scalability Notes

The provider layer is intentionally thin and hot-swappable. Future providers such as Gemini can be added by implementing the unified stream interface and inserting the provider into the router order. More advanced routing can later use latency history, reliability scores, cost budgets, user tier, and task complexity.

## Current Production Readiness

The architecture is ready for realtime frontend integration and safe failover. The main remaining production gaps are provider authentication hardening, durable reliability metrics, queue-aware agent task routing, richer cancellation propagation, and local-model latency tuning.
