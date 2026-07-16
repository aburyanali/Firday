# NOVA Phase 4.6 Walkthrough

## Websocket Lifecycle

`/ws/assistant` now routes all outgoing events through `safe_send_json()`, which checks websocket state and catches closed-socket failures. Each session owns one active websocket and one active stream task. A new prompt, interrupt, duplicate socket, or disconnect cancels the active stream and stops queued speech.

Measured websocket results:

- Health request latency: `91.9ms`
- Short prompt first token through websocket/Ollama: `1224.58ms`
- Interrupt response: received `assistant.interrupted`
- Standby recovery: received `assistant.status` with `idle`
- Duplicate boot greeting: second boot request did not emit a second assistant message

## Voice Pipeline

Browser speech is the primary path. The frontend chooses browser speech only when `speechSynthesis` and `SpeechSynthesisUtterance` exist. Backend macOS `say` is selected only when browser speech is unavailable. Browser speech and backend speech are mutually exclusive through `voice_engine_source`.

Speech cleanup now normalizes:

- `Mr. Ryan` to `Mister Ryan`
- Markdown and code fences
- LaTeX wrappers and boxed answers
- camelCase
- arithmetic symbols only when used between numbers
- hyphenated words as normal spoken words

Math speech is intentionally limited to:

`Working through the equation now, Sir.`

## Wake Phrase And STT

The microphone system now starts both audio-level VAD and browser speech recognition when supported. Recognized interim and final transcripts are sent over websocket as `user.transcript`, then reflected as `assistant.transcript`.

Wake phrase behavior:

- Wake phrase sets NOVA into listening state.
- Wake phrase interrupts current speech.
- A final command after the wake phrase is sent as a normal user message.

Verified capability state in the in-app browser:

- `speechSynthesis`: unavailable
- `SpeechRecognition`: unavailable

So STT and browser voice are implemented but require Chrome or a Web Speech API-capable browser for live microphone verification.

## Math

SymPy now handles arithmetic and symbolic equations with exact verification before render. Verified examples:

- `what is 18 * 7 + 4` -> `130`
- `solve x^2 - 4 = 0` -> `-2, 2`
- `self-improvement plan` -> casual mode, not math mode

## Formatting Intelligence

Response mode detection now routes:

- `give me points`, `bullet points`, `in points` -> bullet mode
- `short answer`, `one line`, `compact` -> compact mode
- `architecture`, `debug`, `websocket`, `latency` -> technical mode
- `cinematic`, `mission`, `briefing` -> cinematic mode
- verified mathematical expressions and math keywords -> math mode

## Immersion Notes

Startup greeting now uses live telemetry and FRIDAY identity. The in-app browser showed:

`You're working late, Mr. Ryan. Memory allocation is nominal at 99%, and local cores are fully active.`

Remaining immersion breakers:

- Ollama first-token latency is still visible for local model generation.
- Backend voice is chunked, not true streaming audio.
- STT depends on browser Web Speech support.
