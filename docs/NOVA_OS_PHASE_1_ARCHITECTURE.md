# NOVA OS Phase 1 Architecture Analysis

Date: 2026-05-23

## Executive Summary

The current project is a compact but capable Python voice assistant centered on `friday.py`. Its strongest assets are semantic memory, persistent SQLite storage, intent inference, planning/tool decision layers, voice input/output, fallback knowledge retrieval, and conversational context. These should be preserved and gradually wrapped in production interfaces rather than rewritten.

The target architecture for NOVA OS should separate the cinematic public assistant experience from a private admin intelligence plane. Users should see realtime chat, voice, streaming responses, memory visualization, and polished AI behavior. Administrators should get protected access to logs, memory databases, reasoning traces, tool execution traces, diagnostics, runtime metrics, and performance telemetry.

## 1. Full System Architecture Map

Current core:

- `friday.py`: monolithic assistant runtime containing schema migration, memory, semantic memory, intent detection, planning, tool decisions, knowledge lookup, math, voice, listener, and CLI loop.
- `config.py`: secure environment loader added in Phase 1.
- `friday_memory.db`: local conversation memory database.
- `~/.friday_memory.db`: advanced semantic memory database path used by `AdvancedMemorySystem`.
- `friday.log` and related logs: runtime observability artifacts.
- `references/friday-tony-stark-demo`: reference architecture using FastMCP, LiveKit Agents, STT, LLM, TTS, SSE tools, and a more modular package layout.

Recommended target:

- Public API layer: FastAPI endpoints for chat, session state, user-safe memory summaries, and voice session bootstrap.
- Realtime layer: WebSocket or SSE stream for tokens, assistant states, tool progress, and voice activity.
- Intelligence layer: Brain, intent, planner, semantic memory, tools, and reflection services.
- Private admin layer: authenticated logs, traces, DB inspection, telemetry, health checks, and diagnostics.
- Storage layer: SQLite initially, then PostgreSQL plus vector storage when scale demands it.
- Frontend layer: Next.js cinematic command center with public user screens and admin-only diagnostics.

## 2. Backend Execution Flow

Current flow:

1. `FridayAssistant.run()` starts the CLI loop and voice listener.
2. User input enters through text input or `VoiceListener`.
3. `process_command()` forwards lowercased text to `EnhancedBrainEngine.think()`.
4. Semantic memory store/recall has first priority.
5. Complex requests call the planner LLM.
6. Non-complex requests call the tool decision LLM.
7. Remaining requests go through `IntentEngine`.
8. `_execute_plan()` handles multi-step tasks, tool execution, knowledge, math, memory, and control commands.
9. Voice output is produced through ElevenLabs if configured, otherwise macOS `say`.
10. Conversations are stored in the local `memory` table.

Risk:

- The full assistant boot requires `OPENAI_API_KEY`, which is correct for production but should later degrade gracefully for offline diagnostics.
- `process_command()` lowers the full user input before semantic processing, which may lose capitalization in names and addresses.
- Several OpenAI clients are created repeatedly instead of using a provider service.

## 3. Memory Architecture Analysis

There are two memory systems:

- `AdvancedMemorySystem`: persistent semantic/factual memory using SQLite, WAL mode, schema migrations, `memories`, `conversation_history`, `habits`, `context`, and `reflections`.
- `FridayAssistant` conversation DB: local `friday_memory.db` with a `memory` table for user input and AI responses.

Strengths:

- Persistent memory exists and is schema-aware.
- Recall reinforces importance and recall count.
- Conversation history stores intents/entities for contextual reasoning.
- Semantic memory scopes keys by user id, for example `user_default:birthday`.

Issues:

- Memory is split across two databases and schemas.
- Local `friday_memory.db` currently has older tables (`memories`, `todos`, `memory`) that do not match the newer schema exactly.
- No encryption, retention policy, backup strategy, or access-control boundary yet.

Target:

- Keep both memory concepts, but define them as separate services:
  - User memory service: facts, preferences, profile, semantic recall.
  - Conversation memory service: dialogue history and session context.
  - Internal trace store: private chain-of-events, tool runs, plan steps, errors, and timings.

## 4. Semantic Memory Pipeline

Current semantic path:

1. Detect memory store when input contains `remember`.
2. Extract canonical key such as birthday, phone, email, address, preferences, goals.
3. Extract raw value from regex patterns.
4. Normalize value by type.
5. Scope key with user id.
6. Store through `AdvancedMemorySystem`.
7. Update in-memory user profile.
8. Return a natural confirmation.

Current recall path:

1. Detect recall phrases.
2. Canonicalize query.
3. Look up scoped key.
4. Return natural response and confidence.

Fix made in Phase 1:

- Date normalization now correctly converts the day to a string before zero-padding.

Gaps:

- Semantic extraction is regex-only.
- User profile updates are in-memory, not persisted as a first-class profile table.
- Ambiguous ownership exists conceptually but is not surfaced through API-level clarification states.

## 5. Intent Engine Analysis

Current priority:

1. Follow-up detection.
2. Memory store.
3. Control commands.
4. Memory recall.
5. Math.
6. Knowledge.
7. Conversation.

Strengths:

- Explicit intents can execute immediately.
- Follow-up detection preserves topic continuity.
- Memory intent is protected from being swallowed by generic knowledge intent.

Issues:

- Some recall keywords are too broad, especially `my`, which can over-trigger semantic recall.
- Math detection is simple and safe, but narrow.
- Intent confidence is mostly rule-based and not calibrated.

Target:

- Preserve the rules as a deterministic first-pass router.
- Add an LLM or classifier fallback only after rules.
- Return structured intent events to the realtime frontend and private traces.

## 6. Planning Engine Analysis

Current planning:

- `BrainEngine.is_complex()` detects complex tasks by keyword.
- `plan()` calls OpenAI and asks for JSON steps.
- JSON parsing has a fallback regex extraction.
- `_execute_single_step()` handles basic calculate/explain/search/code/build placeholders.

Strengths:

- Planning exists and is isolated enough to become a service.
- Fail-safe behavior returns an empty list if planning fails.

Issues:

- Planner and executor are not durable.
- Steps are not persisted as traces.
- Tool availability is not a formal registry.
- Code/build execution is only a placeholder.

Target:

- Introduce `PlanService`, `ToolRegistry`, `ExecutionTraceService`, and `ReflectionService`.
- Persist plan steps and execution events privately.
- Public frontend sees safe progress summaries, while admin sees detailed plan/tool traces.

## 7. Tool Orchestration Flow

Current tools:

- `math`: local safe calculation.
- `knowledge`: Perplexity when configured, Wikipedia fallback.
- `code`: LLM-generated Python code.
- `memory`: handled separately.
- Reference project tools: MCP web/news/system tools exposed via FastMCP and SSE.

Strengths:

- The reference project offers a good model for externalized tools.
- Current project has useful local tool primitives.

Issues:

- Tool decision currently had an accidental literal API key string usage; fixed to use config.
- Tool execution lacks permissions, audit logs, schemas, and admin-only trace views.

Target:

- Adopt a plugin-style registry:
  - Tool schema.
  - Permission level.
  - Public-safe progress message.
  - Private execution trace.
  - Timeout and retry policy.

## 8. Database Structure Analysis

Observed local DB tables:

- `memories`: older schema with `key_phrase`, `information`, `timestamp`, `category`.
- `todos`: task list schema.
- `memory`: conversation history table.

Newer advanced memory schema creates:

- `schema_version`
- `memories` with `key`, `value`, `category`, `timestamp`, `importance`, `recall_count`
- `habits`
- `context`
- `reflections`
- `conversation_history`

Risk:

- Old and new `memories` schema names conflict if pointed at the same DB.
- Current default separates advanced memory into the home directory and conversation memory into the project DB, which avoids immediate collision but needs formal design.

Target:

- Migration plan must preserve data:
  - Snapshot current DBs.
  - Create migration scripts.
  - Normalize tables into `user_memories`, `conversation_messages`, `tasks`, `reflections`, `execution_traces`.
  - Add indexes for user id, timestamp, category, importance, and session id.

## 9. Voice Interaction Pipeline

Current voice:

- `speech_recognition` microphone listener.
- Google recognizer with `en-IN`.
- Text callback to `process_command`.
- TTS through ElevenLabs if configured.
- Fallback TTS through macOS `say`.

Reference voice:

- LiveKit Agents.
- Sarvam STT.
- Gemini or OpenAI LLM.
- OpenAI or Sarvam TTS.
- Silero VAD.
- MCP tools over SSE.

Target:

- Short term: keep current local voice pipeline.
- Medium term: add a FastAPI/LiveKit voice session mode.
- Long term: realtime voice architecture with VAD, barge-in, streaming TTS, interruption handling, and visual voice state.

## 10. AI Reasoning Lifecycle

Current lifecycle:

1. Input normalization.
2. Semantic memory check.
3. Planning check.
4. Tool decision.
5. Intent inference.
6. Execution.
7. Response.
8. Voice output.
9. Conversation persistence.

Target lifecycle:

1. Ingest event.
2. Create private trace id.
3. Load safe user context.
4. Classify intent.
5. Retrieve semantic memories.
6. Plan if needed.
7. Execute tools with audit logs.
8. Stream public response.
9. Persist conversation and memory updates.
10. Write private trace, metrics, and reflection.

## 11. Performance Bottlenecks

- Repeated OpenAI client construction.
- Blocking network calls and TTS calls in the main command path.
- SQLite connections used directly inside multiple classes.
- Synchronous voice playback blocks the assistant.
- Wikipedia and Perplexity calls are not cached.
- Planner and tool decision may both call LLMs for simple tasks.

Fix direction:

- Use async FastAPI services.
- Introduce provider clients as singletons.
- Use background tasks for TTS, logging, and analytics.
- Cache knowledge summaries.
- Stream responses over WebSocket.

## 12. Scalability Issues

- Monolithic `friday.py` limits testability and parallel work.
- No API boundary.
- No session/user model beyond default user id.
- No admin/user role separation.
- No migration framework.
- No durable job queue for long autonomous tasks.

Target:

- Modular services inside one process first.
- Later split into API, worker, realtime gateway, and admin services.

## 13. Security Issues

Found and addressed:

- Hardcoded OpenAI project key removed from `friday.py`.
- Accidental literal `"OPENAI_API_KEY"` usage in tool decision fixed.
- Environment variable loading centralized in `config.py`.
- `.env.example` added.
- `.gitignore` added for secrets, logs, DBs, virtualenvs, node modules, build output, and editor files.

Remaining risk:

- Logs and DB files are still present locally, intentionally, for observability and memory.
- Some runtime artifacts appear to be tracked by Git in the current repository. They should be untracked without deleting local files when approved.
- If the exposed key was ever real, it should be revoked in the provider dashboard because Git history may still contain it.

## 14. Production-Readiness Gaps

- No FastAPI layer yet.
- No auth or role-based access.
- No protected admin dashboard.
- No structured JSON logging.
- No trace ids.
- No request/session correlation.
- No secret validation at startup beyond OpenAI client creation.
- No Docker setup.
- No CI checks.
- No unit test suite beyond semantic test function.
- No rate limiting or abuse protection.
- No data retention policy.

## 15. API Architecture Proposal

Public API:

- `POST /api/chat`: start or continue a chat turn.
- `GET /api/sessions/{id}`: user-safe session state.
- `WS /ws/assistant`: realtime assistant events, streaming text, voice state, tool progress.
- `POST /api/voice/session`: create voice session metadata.
- `GET /api/memory/summary`: safe user-facing memory summaries.

Private admin API:

- `GET /admin/health`
- `GET /admin/logs`
- `GET /admin/traces`
- `GET /admin/traces/{trace_id}`
- `GET /admin/memory/users/{user_id}`
- `GET /admin/metrics`
- `GET /admin/tools/runs`
- `POST /admin/tools/replay`

Security:

- Admin routes must require authentication from day one.
- Public routes must never expose raw prompts, hidden reasoning, secrets, stack traces, DB rows, or internal tool payloads.

## 16. Frontend Integration Strategy

Public NOVA OS frontend:

- Next.js, React, TypeScript, Tailwind, Framer Motion, Zustand.
- Command-center layout, not a generic chatbot.
- Realtime chat stream.
- Voice orb/waveform with listening, thinking, speaking states.
- Memory visualization as safe summaries, not raw database rows.
- Tool execution visualization as public-safe progress cards.
- Cinematic dark interface with glass and motion, using reference aesthetics without copying.

Admin frontend:

- Separate protected route group.
- Logs and telemetry.
- Trace timeline per request.
- Memory inspection.
- Tool run history.
- Latency, token, error, and model usage metrics.
- Diagnostic panels for voice, DB, API providers, and workers.

## 17. WebSocket/Realtime Communication Strategy

Use a typed event stream:

- `assistant.status`: idle, listening, thinking, planning, executing, speaking.
- `assistant.token`: streamed response text.
- `assistant.message`: completed assistant message.
- `tool.started`: public-safe tool name and summary.
- `tool.progress`: safe progress updates.
- `tool.completed`: safe result summary.
- `memory.updated`: user-safe memory category update.
- `error.public`: sanitized error.

Private admin trace stream:

- raw intent result.
- semantic retrieval keys.
- planner steps.
- tool input/output metadata.
- provider latency.
- stack traces.
- DB writes.
- TTS/STT timings.

## 18. Incremental Refactor Roadmap

Phase 1:

- Secret cleanup.
- Environment config.
- Architecture analysis.
- Preserve memory/logs.
- Define public/private boundary.

Phase 2:

- Extract services without changing behavior:
  - `MemoryService`
  - `SemanticMemoryService`
  - `IntentService`
  - `PlannerService`
  - `ToolService`
  - `VoiceService`
  - `TraceService`
- Add FastAPI wrapper.
- Add WebSocket events.
- Add structured logging and trace ids.

Phase 3:

- Build Next.js NOVA OS public interface.
- Add realtime chat, voice visualization, thinking states, and memory summaries.
- Add admin-only observability dashboard.

Phase 4:

- Add durable background jobs, richer agent planning, tool plugins, vector memory, auth, Docker, monitoring, and deployment hardening.

## 19. Safe Modularization Strategy

Rules:

- Do not rewrite `friday.py` in one pass.
- Extract one service at a time.
- Keep compatibility shims.
- Add tests before and after extraction.
- Preserve DB schemas until migrations are explicit.
- Keep current CLI assistant working during API buildout.

Initial extraction order:

1. Config and provider clients.
2. Logging and trace service.
3. Memory service.
4. Semantic memory service.
5. Intent and conversation services.
6. Planner and tool services.
7. Voice service.
8. FastAPI app.

## 20. Long-Term Production Architecture Vision

NOVA OS should become a layered AI operating system:

- Experience plane: cinematic UI, voice, chat, interaction design.
- Realtime plane: WebSocket streams, voice activity, token streaming.
- Intelligence plane: intent, semantic memory, planning, tools, reflection.
- Memory plane: user profile, conversation history, vector recall, task memory.
- Tool plane: plugin framework, permissions, auditing, retries.
- Admin plane: logs, traces, telemetry, memory diagnostics, monitoring.
- Infrastructure plane: Docker, deployment, observability, auth, backups.

The key product principle: the user experiences magic; the administrator sees the machinery. The machinery must be powerful, private, auditable, and secure.

