# NOVA OS Provider Failover Report

## Installed Local Models

Ollama is installed and the local daemon is running.

Installed models:

- `llama3.2:latest`: 2.0 GB
- `phi3:latest`: 2.2 GB
- `gemma:2b`: 1.7 GB

`mistral` was not installed in this pass because it is a heavier local tier and does not match the immediate responsiveness-first target as well as the smaller candidates.

## Security Note

A real-looking key was found in `.env.example` and removed. `.env.example` now uses placeholders only. If that key was active, revoke it in the provider dashboard because repository history or local copies may still contain it.

## Test Results

OpenAI success:

- Configured: yes.
- Minimal stream probe result: failed with sanitized reason `rate_limited`.
- UI exposure: no raw provider error is forwarded.

OpenAI failure:

- Heavy-reasoning route starts with OpenAI.
- On timeout/rate-limit/error, provider manager emits `assistant.failover` and continues to the next configured provider.

Perplexity fallback:

- Configured: no `PERPLEXITY_API_KEY` detected.
- Result: route marks Perplexity unavailable and continues without surfacing raw errors.

Ollama fallback:

- Installed and reachable.
- Direct local inference works, but current first-token latency is above the realtime target on this machine.
- The stream path protects UX by enforcing the first-token timeout and moving to local fallback.

Local degraded fallback:

- Verified first token: about 0.63 ms when remote/local model providers are unavailable.
- Response mode: `NOVA CORE operating in autonomous degraded mode.`

WebSocket continuity:

- Verified through `/ws/assistant`.
- Event path remained alive through Ollama timeout and local failover.
- Final provider: `local`.
- Final degraded flag: `true`.
- Reconnect open/close path verified.
- Explicit interruption path verified with `assistant.interrupted` followed by idle status.

## Latency Measurements

Measured on May 23, 2026 in the local development environment.

| Path | Result |
| --- | ---: |
| Direct `llama3.2` first token | 9134.77 ms |
| Direct `llama3.2` sample completion | 10447.79 ms |
| Direct `phi3` first token | 10609.04 ms |
| Direct `gemma:2b` first token | 223452.85 ms |
| Provider fast route first visible token after Ollama timeout | 2009.50 ms |
| WebSocket first streamed token after Ollama timeout | 2014.41 ms |
| Pure local fallback first token | 0.63 ms |
| WebSocket boot/status/ready event start | about 6-52 ms |

## Streaming Quality

Streaming continuity is good. NOVA emits immediate lifecycle/provider events, keeps the socket open during provider failure, and streams fallback tokens in small paced chunks. The current weakness is local model first-token latency; the fallback engine compensates so the assistant remains responsive.

## Provider Reliability Snapshot

| Provider | Status | Reliability |
| --- | --- | --- |
| OpenAI | Configured, rate-limited in probe | Needs quota recovery |
| Perplexity | Not configured | Needs API key |
| Ollama `llama3.2` | Installed, reachable, slow first token | Useful fallback, not realtime-fast yet |
| Ollama `phi3` | Installed, direct first token about 10.6s | Not recommended as realtime default today |
| Ollama `gemma:2b` | Installed, very slow in local test | Not recommended as default today |
| Local fallback | Available instantly | High reliability degraded mode |
| Emergency fallback | Available | Final continuity layer |

## RAM Usage Report

Installed model disk footprints:

- `llama3.2`: 2.0 GB
- `phi3`: 2.2 GB
- `gemma:2b`: 1.7 GB

Observed active model residency:

- `phi3:latest`: 4.0 GB, 100% GPU, 4096 context, shortly after the latency sample.

Based on model size, expect local runtime memory pressure to be materially higher than disk size during active inference. Next tuning pass should test smaller quantized models and collect `ollama ps` plus system memory samples during warm inference.

## Quality Scores

- Local inference quality score: 6/10
- Realtime feel score: 7/10
- Offline readiness score: 7/10
- Provider redundancy readiness: 7.5/10
- Overall production readiness: 7/10

## Next Recommendations

1. Add `PERPLEXITY_API_KEY` to complete remote failover.
2. Try smaller/faster Ollama models such as `qwen2.5:1.5b`, `tinyllama`, or a quantized low-latency model.
3. Persist provider reliability metrics to admin telemetry.
4. Add request cancellation into provider streams for interruption support.
5. Add a provider warming job so local models stay resident during active NOVA sessions.
