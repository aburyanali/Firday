# NOVA OS Phase 3 Frontend Foundation

Date: 2026-05-23

## What This Slice Adds

The frontend foundation is now a Next.js cinematic runtime interface under `frontend/`.

Stack:

- Next.js
- React
- TypeScript
- Tailwind CSS
- Framer Motion
- Zustand
- Lucide icons
- WebSocket runtime integration

## Architecture

The frontend is intentionally separated from the Python backend:

- `nova_backend`: realtime AI runtime, WebSocket events, public/admin boundaries.
- `frontend`: cinematic public interaction layer for text, voice-ready UI, and realtime runtime visualization.

The core realtime store is `frontend/src/store/runtime-store.ts`. It owns:

- WebSocket connection lifecycle
- assistant state
- session id
- incoming runtime events
- streaming token text
- chat messages
- intent/confidence metadata
- public error handling

## Realtime Event Integration

The UI consumes the backend event contract from Phase 2.5:

- `assistant.boot`
- `assistant.ready`
- `assistant.status`
- `assistant.intent`
- `assistant.voice`
- `assistant.token`
- `assistant.message`
- `assistant.error`

These events drive:

- assistant presence state
- central core animation
- runtime event rail
- streaming chat response
- voice output state
- degraded/runtime error surface

## Voice Preparation

The voice layer is scaffolded but not yet wired to backend voice streaming. It currently supports local microphone permission and live audio-level visualization. This prepares the UI architecture for:

- microphone streaming
- realtime transcription
- assistant speaking state
- interruption handling
- wake-word systems
- voice waveform synchronization

## Design Direction

The first screen is the actual NOVA OS operating surface, not a landing page. It uses:

- animated runtime canvas field
- assistant presence core
- realtime vitals
- cognition stream
- voice dock
- runtime event rail
- responsive command-center layout

The design intentionally avoids a generic chatbot layout. Chat exists as a cognition stream inside a larger realtime AI operating interface.

## Verification

Verified:

- `npm run typecheck`
- `npm run build`
- local frontend at `http://127.0.0.1:3000`
- backend WebSocket connection to `ws://127.0.0.1:8000/ws/assistant`
- degraded-mode event flow when `OPENAI_API_KEY` is not configured
- hydration issue fixed by generating session id after client connection

## Next Safe Upgrades

1. Add true assistant-token streaming when backend supports provider streaming.
2. Add memory visualization tied to `assistant.memory`.
3. Add planning/tool visualization tied to `assistant.planning` and `assistant.tool_call`.
4. Add voice input transport when backend microphone streaming is ready.
5. Add admin-only runtime dashboard as a separate protected frontend route.

