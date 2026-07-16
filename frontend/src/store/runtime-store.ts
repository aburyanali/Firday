import { create } from "zustand";
import { AssistantState, ChatMessage, RuntimeEvent, isAssistantState } from "@/lib/runtime-events";

if (typeof window !== "undefined") {
  console.log("[PHASE_4_8_6_ACTIVE]");
}

const WS_URL = process.env.NEXT_PUBLIC_NOVA_WS_URL || "ws://127.0.0.1:8000/ws/assistant";


// ============================================================
// PHASE 4.8.6 — BOOT STATE MACHINE
// ============================================================
type BootPhase =
  | "BOOT_INIT"
  | "WS_CONNECTED"
  | "FRONTEND_READY"
  | "VOICES_READY"
  | "FEMALE_LOCK_CONFIRMED"
  | "GREETING_ALLOWED"
  | "GREETING_COMPLETE";

type VoiceLockResult = {
  ready: boolean;
  lockedVoiceName?: string;
  reason?: string;
};

type RuntimeStore = {
  socket?: WebSocket;
  connected: boolean;
  sessionId: string;
  assistantState: AssistantState;
  events: RuntimeEvent[];
  messages: ChatMessage[];
  streamText: string;
  intent?: string;
  confidence: number;
  lastError?: string;
  voiceLevel: number;
  latencyMs: number;
  tokensPerSecond: number;
  degradedMode: boolean;
  activeProvider: string;
  activeModel: string;
  lastTokenAt: number;

  // Voice Preferences
  voicePersonality: "jarvis" | "friday" | "tactical" | "neutral";
  voiceRate: number;
  voicePitch: number;
  voiceVolume: number;
  firstLaunch: boolean;
  voiceEngineSource: "browser" | "backend";
  voiceLinkStatus: string;

  connect: () => void;
  disconnect: () => void;
  sendMessage: (content: string) => void;
  sendVoiceFrame: (base64Data: string) => void;
  sendTranscript: (text: string, final?: boolean, wake?: boolean) => void;
  interruptSpeaking: () => void;
  ingestEvent: (event: RuntimeEvent) => void;
  setVoiceSettings: (settings: Partial<Pick<RuntimeStore, "voicePersonality" | "voiceRate" | "voicePitch" | "voiceVolume" | "firstLaunch" | "voiceEngineSource">>) => void;
  triggerReactorBoot: () => void;
  previewVoice: (personality: "jarvis" | "friday" | "tactical" | "neutral") => void;
};

export const VOICE_LOCK_ACTIVE = true;

// ============================================================
// GLOBAL SINGLETON STATE — Outside Zustand (module-level singletons)
// ============================================================
let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
let reconnectAttempts = 0;
let isExplicitlyClosed = false;
let activeAssistantMessageId: string | undefined;
let streamStartedAt = 0;
let streamTokenCount = 0;

// Phase 4.8.6: Connection mutex — prevents concurrent connect() calls
let isConnecting = false;

// Phase 4.8.6: Boot state machine
let bootPhase: BootPhase = "BOOT_INIT";
let bootTimeoutTimer: ReturnType<typeof setTimeout> | null = null;
const greetedSessions = new Set<string>();
const bootGreetingAttempts = new Map<string, number>();
let audioUnlocked = false;
let pendingBootRequest:
  | {
      socket: WebSocket;
      sessionId: string;
      voiceEngineSource: "browser" | "backend";
      voicePersonality: string;
    }
  | null = null;

// Phase 4.8.6: Heartbeat
let heartbeatTimer: ReturnType<typeof setInterval> | null = null;

// Phase 4.8.6: Speech mutex — prevents overlapping utterances
let isSpeaking = false;
let speechMutexTimer: ReturnType<typeof setTimeout> | null = null;

// ============================================================
// VOICE ENGINE
// ============================================================

export function waitForVoices(): Promise<VoiceLockResult> {
  return new Promise((resolve) => {
    if (typeof window === "undefined" || !("speechSynthesis" in window)) {
      resolve({ ready: false, reason: "speech_synthesis_unavailable" });
      return;
    }

    let resolved = false;
    const tryResolve = () => {
      if (resolved) return;
      const voices = window.speechSynthesis.getVoices();
      const lockedVoice = getLockedFemaleVoice();
      if (voices.length > 0 && lockedVoice) {
        resolved = true;
        logVoiceDiagnostics(voices, lockedVoice);
        console.log(`[VOICE READY] ${lockedVoice.name}`);
        resolve({ ready: true, lockedVoiceName: lockedVoice.name });
      }
    };

    tryResolve();

    if (!("speechSynthesis" in window)) return;

    // Retry loop — Chrome loads voices asynchronously
    const retryInterval = setInterval(() => {
      tryResolve();
      if (resolved) clearInterval(retryInterval);
    }, 80);

    if (window.speechSynthesis.onvoiceschanged !== undefined) {
      const prev = window.speechSynthesis.onvoiceschanged;
      window.speechSynthesis.onvoiceschanged = (e) => {
        if (prev) prev.call(window.speechSynthesis, e);
        tryResolve();
        if (resolved) clearInterval(retryInterval);
      };
    }

    // Hard timeout — report exact failure and let boot recovery retry once.
    setTimeout(() => {
      if (!resolved) {
        resolved = true;
        const count = window.speechSynthesis.getVoices().length;
        const reason = `voice_lock_timeout voices=${count}`;
        console.warn(`[VOICE LOCK FAILED] ${reason}`);
        resolve({ ready: false, reason });
      }
      clearInterval(retryInterval);
    }, 3000);
  });
}

export function getLockedFemaleVoice(): SpeechSynthesisVoice | null {
  if (typeof window === "undefined" || !("speechSynthesis" in window)) return null;
  const voices = window.speechSynthesis.getVoices();
  if (!voices.length) return null;

  return voices
    .map((voice) => ({ voice, score: scoreVoiceQuality(voice) }))
    .sort((a, b) => b.score - a.score)[0]?.voice || voices[0];
}

function scoreVoiceQuality(voice: SpeechSynthesisVoice) {
  const name = voice.name.toLowerCase();
  const lang = voice.lang.toLowerCase();
  let score = 0;

  if (/^en([-_]|$)/.test(lang)) score += 20;
  if (/en[-_]in|en[-_]gb|en[-_]us/.test(lang)) score += 8;
  if (voice.localService) score += 12;

  if (/siri|premium|enhanced|neural|natural|eloquence/.test(name)) score += 30;
  if (/allison/.test(name)) score += 24;
  if (/ava|zoe|susan|victoria|karen|moira|tessa|serena|veena|fiona|kate|joanna|aria|jenny|sandy|shelley/.test(name)) score += 20;
  if (/samantha/.test(name)) score += 12;
  if (/compact|novelty|whisper|bells|boing|bubbles|cellos|zarvox|trinoids|bad news|good news|pipe organ|superstar|wobble|bahh|jester/.test(name)) score -= 45;
  if (/alex|daniel|david|fred|mark|tom|rishi|rocko|reed|aaron/.test(name)) score -= 20;
  if (!/^en([-_]|$)/.test(lang)) score -= 18;

  return score;
}

function logVoiceDiagnostics(voices: SpeechSynthesisVoice[], selected: SpeechSynthesisVoice) {
  const ranked = voices
    .map((voice) => ({ voice, score: scoreVoiceQuality(voice) }))
    .sort((a, b) => b.score - a.score);

  for (const { voice, score } of ranked.slice(0, 12)) {
    console.log(
      `[VOICE CANDIDATE] name="${voice.name}" lang=${voice.lang || "unknown"} local=${voice.localService} score=${score}`
    );
  }

  console.log(`[VOICE SELECTED] ${selected.name}`);
  console.log(`[VOICE QUALITY SCORE] ${scoreVoiceQuality(selected)} reason=highest_ranked_reliable_warm_local_voice`);
}

function installAudioUnlockListeners() {
  if (typeof window === "undefined") return;
  const unlock = () => {
    unlockAudio("user_gesture");
  };
  window.addEventListener("pointerdown", unlock, { once: true, passive: true });
  window.addEventListener("keydown", unlock, { once: true });
}

function unlockAudio(reason: string) {
  if (audioUnlocked || typeof window === "undefined" || !("speechSynthesis" in window)) return;
  const activation = window.navigator.userActivation;
  const trustedActivation = !activation || activation.hasBeenActive;
  if (!trustedActivation && reason !== "message_submit" && reason !== "manual_boot" && reason !== "interrupt") {
    return;
  }
  try {
    window.speechSynthesis.resume();
  } catch {}
  audioUnlocked = true;
  useRuntimeStore.setState({ voiceLinkStatus: "Voice link awake" });
  console.log(`[AUDIO UNLOCKED] ${reason}`);

  if (pendingBootRequest) {
    const pending = pendingBootRequest;
    pendingBootRequest = null;
    advanceBootPhase(
      "GREETING_ALLOWED",
      pending.socket,
      pending.sessionId,
      pending.voiceEngineSource,
      pending.voicePersonality
    );
  }
}

// ============================================================
// SPEECH CONTROLLER — Phase 4.8.6
// ============================================================
const speechController = {
  supported() {
    return speechSynthesisSupported();
  },

  cancel(reason = "unspecified") {
    isSpeaking = false;
    if (speechMutexTimer) {
      clearTimeout(speechMutexTimer);
      speechMutexTimer = null;
    }
    if (this.supported()) {
      try {
        console.log(`[VOICE CANCEL] reason=${reason}`);
        window.speechSynthesis.cancel();
      } catch {}
    }
  },

  speakFinal(text: string) {
    if (!this.supported()) return;
    const state = useRuntimeStore.getState();
    if (state.voiceEngineSource === "backend") {
      // Backend voice active — browser synthesis completely suppressed
      return;
    }
    if (!audioUnlocked) {
      console.warn("[VOICE DEFERRED] audio_locked");
      useRuntimeStore.setState({ voiceLinkStatus: "Voice link standing by" });
      installAudioUnlockListeners();
      return;
    }

    const cleaned = cleanForSpeech(text);
    if (!cleaned) return;
    const utterance = new SpeechSynthesisUtterance(cleaned);
    const rate = state.voiceRate !== 1.0 ? state.voiceRate : 0.93;
    const pitch = state.voicePitch !== 1.0 ? state.voicePitch : 0.97;
    const volume = state.voiceVolume || 0.95;

    const lockedVoice = getLockedFemaleVoice();
    if (!lockedVoice) {
      return;
    }

    utterance.voice = lockedVoice;
    utterance.rate = rate;
    utterance.pitch = pitch;
    utterance.volume = volume;

    utterance.onboundary = (e) => {
      if (e.name === "word") {
        useRuntimeStore.setState({ voiceLevel: 0.35 + Math.random() * 0.45 });
        setTimeout(() => {
          if (window.speechSynthesis?.speaking) {
            useRuntimeStore.setState({ voiceLevel: 0.15 + Math.random() * 0.2 });
          }
        }, 120);
      }
    };

    utterance.onstart = () => {
      isSpeaking = true;
      console.log(`[VOICE SPEAK START] voice=${lockedVoice.name} mode=final`);
    };

    utterance.onend = () => {
      isSpeaking = false;
      useRuntimeStore.setState({ voiceLevel: 0.12 });
      console.log(`[VOICE SPEAK END] voice=${lockedVoice.name}`);
    };

    utterance.onerror = (event) => {
      isSpeaking = false;
      useRuntimeStore.setState({ voiceLevel: 0.12 });
      console.error(`[VOICE SPEAK ERROR] voice=${lockedVoice.name} reason=${event.error}`);
      if (event.error === "not-allowed") {
        audioUnlocked = false;
        useRuntimeStore.setState({ voiceLinkStatus: "Voice link standing by" });
        console.warn("[VOICE LOCKED] browser_autoplay_blocked");
        installAudioUnlockListeners();
      }
    };

    try {
      window.speechSynthesis.speak(utterance);
    } catch {}
  },
};

// ============================================================
// INITIAL VALUES
// ============================================================
let initialPersonality: "jarvis" | "friday" | "tactical" | "neutral" = "friday";
let initialRate = 0.93;
let initialPitch = 0.97;
let initialVolume = 0.95;
let initialFirstLaunch = false;
let initialEngineSource: "browser" | "backend" = "backend";

if (typeof window !== "undefined") {
  initialRate = parseFloat(window.localStorage.getItem("nova_voice_rate") || "0.93");
  initialPitch = parseFloat(window.localStorage.getItem("nova_voice_pitch") || "0.97");
  initialVolume = parseFloat(window.localStorage.getItem("nova_voice_volume") || "0.95");
  initialEngineSource = "backend";
}

// ============================================================
// HEARTBEAT — Phase 4.8.6
// ============================================================
function startHeartbeat(socket: WebSocket) {
  stopHeartbeat();
  heartbeatTimer = setInterval(() => {
    if (socket.readyState === WebSocket.OPEN) {
      try {
        socket.send(JSON.stringify({ type: "ping", timestamp: Date.now() }));
      } catch {}
    } else {
      stopHeartbeat();
    }
  }, 15000);
}

function stopHeartbeat() {
  if (heartbeatTimer) {
    clearInterval(heartbeatTimer);
    heartbeatTimer = null;
  }
}

// ============================================================
// BOOT SEQUENCE HELPERS — Phase 4.8.6
// ============================================================
function clearBootTimeout() {
  if (bootTimeoutTimer) {
    clearTimeout(bootTimeoutTimer);
    bootTimeoutTimer = null;
  }
}

function sendBootGreetingRequest(socket: WebSocket, sessionId: string, voiceEngineSource: "browser" | "backend", voicePersonality: string) {
  if (greetedSessions.has(sessionId)) {
    console.log("[BOOT] Session already greeted — skipping.");
    bootPhase = "GREETING_COMPLETE";
    return;
  }

  const attempts = bootGreetingAttempts.get(sessionId) || 0;
  console.log(`[BOOT GREETING START] attempt=${attempts + 1}`);

  try {
    socket.send(
      JSON.stringify({
        type: "user.boot",
        voice_personality: voicePersonality,
        voice_engine_source: voiceEngineSource,
        session_id: sessionId,
        user_id: "user_default",
      })
    );
    greetedSessions.add(sessionId);
    bootGreetingAttempts.delete(sessionId);
    bootPhase = "GREETING_COMPLETE";
    console.log("[BOOT GREETING REQUEST SENT]");
    clearBootTimeout();
  } catch (error) {
    const reason = error instanceof Error ? error.message : String(error);
    console.error(`[BOOT GREETING FAILED] ${reason}`);
    bootGreetingAttempts.set(sessionId, attempts + 1);
    if (attempts < 1) {
      setTimeout(() => {
        if (socket.readyState === WebSocket.OPEN && !greetedSessions.has(sessionId)) {
          sendBootGreetingRequest(socket, sessionId, voiceEngineSource, voicePersonality);
        }
      }, 350);
    } else {
      bootPhase = "GREETING_ALLOWED";
    }
  }
}

function advanceBootPhase(phase: BootPhase, socket: WebSocket, sessionId: string, voiceEngineSource: "browser" | "backend", voicePersonality: string) {
  bootPhase = phase;
  console.log(`[BOOT] Phase: ${phase}`);
  console.log("[BOOT STATE]", bootPhase);


  if (phase === "GREETING_ALLOWED") {
    if (voiceEngineSource === "browser" && !audioUnlocked) {
      pendingBootRequest = { socket, sessionId, voiceEngineSource, voicePersonality };
      console.warn("[BOOT GREETING DEFERRED] audio_locked_waiting_for_user_gesture");
      return;
    }
    sendBootGreetingRequest(socket, sessionId, voiceEngineSource, voicePersonality);
  }
}

// ============================================================
// STORE
// ============================================================
export const useRuntimeStore = create<RuntimeStore>((set, get) => ({
  connected: false,
  sessionId: "pending",
  assistantState: "offline",
  events: [],
  messages: [],
  streamText: "",
  confidence: 0,
  voiceLevel: 0.12,
  latencyMs: 0,
  tokensPerSecond: 0,
  degradedMode: false,
  activeProvider: "READY",
  activeModel: "standby",
  lastTokenAt: 0,

  voicePersonality: initialPersonality,
  voiceRate: initialRate,
  voicePitch: initialPitch,
  voiceVolume: initialVolume,
  firstLaunch: initialFirstLaunch,
  voiceEngineSource: initialEngineSource,
  voiceLinkStatus: "Mac voice ready",

  connect: () => {
    // Phase 4.8.6: Connection mutex — prevent concurrent connect calls
    if (isConnecting) {
      return;
    }

    const existing = get().socket;
    if (
      existing &&
      (existing.readyState === WebSocket.OPEN ||
        existing.readyState === WebSocket.CONNECTING)
    ) {
      return;
    }

    isConnecting = true;
    isExplicitlyClosed = false;

    if (reconnectTimer) {
      clearTimeout(reconnectTimer);
      reconnectTimer = null;
    }

    // Stale socket cleanup — explicitly close before creating new one
    if (existing && existing.readyState !== WebSocket.CLOSED) {
      try {
        existing.close();
      } catch {}
    }

    if (reconnectAttempts > 0) {
      set({ assistantState: "recovering" });
    } else {
      set({ assistantState: "booting" });
    }

    bootPhase = "BOOT_INIT";
    clearBootTimeout();
    installAudioUnlockListeners();

    const socket = new WebSocket(WS_URL);

    socket.onopen = () => {
      isConnecting = false;
      reconnectAttempts = 0;

      const resolvedSessionId =
        get().sessionId === "pending" ? createId() : get().sessionId;

      const state = get();
      const engineSource: "browser" | "backend" = "backend";
      if (engineSource === "backend") {
        speechController.cancel("voice_owner_switched_to_backend");
      }

      set({
        connected: true,
        assistantState: "idle",
        lastError: undefined,
        sessionId: resolvedSessionId,
        voiceEngineSource: engineSource,
      });

      startHeartbeat(socket);

      bootPhase = "WS_CONNECTED";

      // Phase 4.8.6: Send frontend_ready event
      try {
        socket.send(
          JSON.stringify({
            type: "frontend.ready",
            session_id: resolvedSessionId,
            user_id: "user_default",
          })
        );
      } catch {}

      bootPhase = "FRONTEND_READY";

      if (!state.firstLaunch) {
        if (engineSource === "backend") {
          set({ voiceLinkStatus: "Mac voice ready" });
          advanceBootPhase(
            "GREETING_ALLOWED",
            socket,
            resolvedSessionId,
            engineSource,
            get().voicePersonality
          );
          return;
        }
        waitForVoices().then((voiceLock) => {
          if (!voiceLock.ready) {
            console.warn(`[BOOT] Voice lock pending: ${voiceLock.reason || "unknown"}`);
            set({ voiceLinkStatus: "Voice link standing by" });
            return;
          }
          bootPhase = "VOICES_READY";
          console.log(`[FEMALE VOICE LOCK CONFIRMED] ${voiceLock.lockedVoiceName}`);


          // Send voice.ready to backend
          try {
            socket.send(
              JSON.stringify({
                type: "voice.ready",
                session_id: resolvedSessionId,
                user_id: "user_default",
                locked_voice: voiceLock.lockedVoiceName,
              })
            );
          } catch {}

          bootPhase = "FEMALE_LOCK_CONFIRMED";

          if (engineSource === "browser" && !audioUnlocked) {
            pendingBootRequest = { socket, sessionId: resolvedSessionId, voiceEngineSource: engineSource, voicePersonality: get().voicePersonality };
            set({ voiceLinkStatus: "Voice link standing by" });
            console.warn("[BOOT GREETING DEFERRED] audio_locked_waiting_for_user_gesture");
          } else {
            advanceBootPhase(
              "GREETING_ALLOWED",
              socket,
              resolvedSessionId,
              engineSource,
              get().voicePersonality
            );
          }
        });
      }
    };

    socket.onclose = () => {
      isConnecting = false;
      stopHeartbeat();
      set({ connected: false, socket: undefined });

      if (!isExplicitlyClosed) {
        set({ assistantState: "recovering", lastError: "Link lost. Reconnecting..." });
        reconnectAttempts++;
        // Exponential backoff: 1.2s, 2s, 3.4s, ... max 12s
        const delay = Math.min(1200 * Math.pow(1.7, reconnectAttempts - 1), 12000);

        if (reconnectTimer) clearTimeout(reconnectTimer);
        reconnectTimer = setTimeout(() => {
          get().connect();
        }, delay);
      } else {
        set({ assistantState: "offline" });
      }
    };

    socket.onerror = () => {
      isConnecting = false;
      set({ connected: false, lastError: "Runtime link unavailable." });
    };

    socket.onmessage = (message) => {
      try {
        const event = JSON.parse(message.data) as RuntimeEvent;
        // Filter out pong (heartbeat response) — no store update needed
        if ((event as any).type === "pong") return;
        get().ingestEvent(event);
      } catch {
        set({ lastError: "Malformed runtime event." });
      }
    };

    set({ socket });
  },

  disconnect: () => {
    isExplicitlyClosed = true;
    isConnecting = false;
    reconnectAttempts = 0;
    stopHeartbeat();
    clearBootTimeout();

    if (reconnectTimer) {
      clearTimeout(reconnectTimer);
      reconnectTimer = null;
    }

    get().socket?.close();
    set({ socket: undefined, connected: false, assistantState: "offline" });
  },

  sendMessage: (content: string) => {
    unlockAudio("message_submit");
    const socket = get().socket;
    const trimmed = content.trim();
    if (!trimmed) return;
    if (/^(stop|pause|quiet|be quiet)[.!?]?$/i.test(trimmed)) {
      get().interruptSpeaking();
      return;
    }

    // Phase 4.8.6: Cancel speech BEFORE everything
    speechController.cancel("new_user_message");

    const isActive =
      get().assistantState === "speaking" ||
      get().assistantState === "streaming" ||
      get().streamText.length > 0;
    if (isActive) {
      get().interruptSpeaking();
    }

    const userMessage: ChatMessage = {
      id: createId(),
      role: "user",
      content: trimmed,
      timestamp: Date.now(),
    };
    activeAssistantMessageId = createId();
    streamStartedAt = performance.now();
    streamTokenCount = 0;

    set((state) => ({
      messages: [
        ...state.messages,
        userMessage,
        {
          id: activeAssistantMessageId!,
          role: "assistant",
          content: "",
          timestamp: Date.now(),
        },
      ],
      streamText: "",
      lastError: undefined,
      assistantState: state.connected ? "thinking" : "offline",
      degradedMode: false,
      tokensPerSecond: 0,
      latencyMs: 0,
    }));

    if (!socket || socket.readyState !== WebSocket.OPEN) {
      set({ lastError: "NOVA is unavailable right now.", assistantState: "error" });
      return;
    }

    socket.send(
      JSON.stringify({
        type: "user.message",
        message: trimmed,
        session_id: get().sessionId,
        user_id: "user_default",
        voice_personality: get().voicePersonality,
        voice_engine_source: get().voiceEngineSource,
        client_sent_at: Date.now(),
      })
    );
  },

  sendVoiceFrame: (base64Data: string) => {
    const socket = get().socket;
    if (!socket || socket.readyState !== WebSocket.OPEN) return;
    // Removed passive voice frame cancellation.

    socket.send(
      JSON.stringify({
        type: "user.audio",
        audio: base64Data,
        session_id: get().sessionId,
        user_id: "user_default",
      })
    );
  },

  sendTranscript: (text: string, final = false, wake = false) => {
    const socket = get().socket;
    if (!socket || socket.readyState !== WebSocket.OPEN) return;
    socket.send(
      JSON.stringify({
        type: "user.transcript",
        transcript: text,
        final,
        wake,
        session_id: get().sessionId,
        user_id: "user_default",
      })
    );
  },

  interruptSpeaking: () => {
    unlockAudio("interrupt");
    const socket = get().socket;

    // Phase 4.8.6: Always cancel speech immediately
    speechController.cancel("intentional_interrupt");

    if (!socket || socket.readyState !== WebSocket.OPEN) {
      set({ assistantState: "interrupted", streamText: "" });
      activeAssistantMessageId = undefined;
      return;
    }

    socket.send(
      JSON.stringify({
        type: "user.interrupt",
        session_id: get().sessionId,
        user_id: "user_default",
      })
    );

    set((state) => ({
      assistantState: "interrupted",
      streamText: "",
      messages: activeAssistantMessageId
        ? state.messages.map((message) =>
            message.id === activeAssistantMessageId && !message.content
              ? { ...message, content: "—" }
              : message
          )
        : state.messages,
    }));
    activeAssistantMessageId = undefined;
  },

  ingestEvent: (event: RuntimeEvent) => {
    set((state) => ({
      events: [event, ...state.events].slice(0, 80),
      sessionId: event.session_id || state.sessionId,
    }));

    const payload = event.payload || {};

    if (event.type === "assistant.status" && isAssistantState(payload.state)) {
      set({ assistantState: payload.state });
    }

    if (event.type === "assistant.listening") {
      set({ assistantState: "listening" });
    }

    if (event.type === "assistant.processing") {
      set({ assistantState: "analyzing" });
    }

    if (event.type === "assistant.ready") {
      set({ assistantState: "streaming" });
    }

    if (event.type === "assistant.interrupted") {
      const reason = typeof payload.reason === "string" ? payload.reason : "unknown";
      if (reason === "user_action" || reason === "voice_activity") {
        speechController.cancel(`server_interrupt_${reason}`);
      }
      set({ assistantState: "interrupted", streamText: "", lastTokenAt: Date.now() });
    }

    if (event.type === "assistant.degraded") {
      set({ degradedMode: true, assistantState: "warning", lastError: undefined });
    }

    if (event.type === "assistant.provider") {
      const provider = typeof payload.provider === "string" ? payload.provider : "local";
      const model = typeof payload.model === "string" ? payload.model : "standby";
      set({
        activeProvider: providerLabel(provider),
        activeModel: model,
        degradedMode:
          provider === "emergency" ? true : get().degradedMode,
      });
    }

    if (event.type === "assistant.failover") {
      set({
        assistantState: "recovering",
        activeProvider: "RETRYING",
      });
    }

    if (event.type === "assistant.intent") {
      set({
        intent: typeof payload.intent === "string" ? payload.intent : undefined,
        confidence: typeof payload.confidence === "number" ? payload.confidence : 0,
      });
    }

    if (event.type === "assistant.voice") {
      if (isAssistantState(payload.state)) {
        set({ assistantState: payload.state });
      }
    }

    if (event.type === "assistant.token") {
      const token = typeof payload.text === "string" ? payload.text : "";
      const provider = typeof payload.provider === "string" ? payload.provider : undefined;
      streamTokenCount += token.length ? 1 : 0;
      const elapsedSeconds = Math.max((performance.now() - streamStartedAt) / 1000, 0.1);
      set((state) => ({
        assistantState: "streaming",
        activeProvider: provider ? providerLabel(provider) : state.activeProvider,
        activeModel: typeof payload.model === "string" ? payload.model : state.activeModel,
        streamText: state.streamText + token,
        lastTokenAt: Date.now(),
        tokensPerSecond: Math.round((streamTokenCount / elapsedSeconds) * 10) / 10,
        messages: activeAssistantMessageId
          ? state.messages.map((message) =>
              message.id === activeAssistantMessageId
                ? { ...message, content: message.content + token }
                : message
            )
          : state.messages,
      }));
    }

    if (event.type === "assistant.message") {
      const text = typeof payload.text === "string" ? payload.text : get().streamText;
      if (!text) return;

      set((state) => ({
        messages: activeAssistantMessageId
          ? state.messages.map((message) =>
              message.id === activeAssistantMessageId
                ? { ...message, content: text }
                : message
            )
          : [
              ...state.messages,
              {
                id: event.event_id || createId(),
                role: "assistant",
                content: text,
                timestamp: Date.now(),
              },
            ],
        streamText: "",
        assistantState: "idle",
        activeProvider:
          typeof payload.provider === "string"
            ? providerLabel(payload.provider)
            : state.activeProvider,
        activeModel:
          typeof payload.model === "string" ? payload.model : state.activeModel,
        degradedMode: payload.degraded === true ? true : state.degradedMode,
        latencyMs:
          typeof payload.latency_ms === "number"
            ? payload.latency_ms
            : Math.round(performance.now() - streamStartedAt),
      }));
      speechController.speakFinal(text);
      activeAssistantMessageId = undefined;
    }

    if (event.type === "assistant.error") {
      set({
        lastError: "NOVA is reconnecting.",
        assistantState: "error",
        streamText: "",
      });
    }

    if (event.type === "assistant.telemetry") {
      const energy = typeof payload.energy === "number" ? payload.energy : 0.0;
      set({ voiceLevel: energy });
    }
  },

  setVoiceSettings: (settings) => {
    set((state) => {
      const newState = {
        ...state,
        ...settings,
        // Phase 4.8.6: Personality locked to Friday (female AI)
        voicePersonality: "friday" as const,
        firstLaunch: settings.firstLaunch !== undefined ? settings.firstLaunch : false,
      };
      if (typeof window !== "undefined") {
        window.localStorage.setItem("nova_voice_personality", "friday");
        window.localStorage.setItem("nova_first_launch", String(newState.firstLaunch));
        if (settings.voiceRate !== undefined)
          window.localStorage.setItem("nova_voice_rate", settings.voiceRate.toString());
        if (settings.voicePitch !== undefined)
          window.localStorage.setItem("nova_voice_pitch", settings.voicePitch.toString());
        if (settings.voiceVolume !== undefined)
          window.localStorage.setItem("nova_voice_volume", settings.voiceVolume.toString());
        if (settings.voiceEngineSource !== undefined)
          window.localStorage.setItem("nova_voice_engine_source", settings.voiceEngineSource);
      }
      return newState;
    });
  },

  triggerReactorBoot: () => {
    unlockAudio("manual_boot");
    const socket = get().socket;
    const state = get();
    const sessionId = state.sessionId;

    set({ firstLaunch: false });
    if (typeof window !== "undefined") {
      window.localStorage.setItem("nova_first_launch", "false");
    }

    if (socket && socket.readyState === WebSocket.OPEN) {
      if (!greetedSessions.has(sessionId)) {
        waitForVoices().then((voiceLock) => {
          if (!voiceLock.ready) {
            console.error(`[BOOT GREETING BLOCKED] ${voiceLock.reason || "voice_lock_unavailable"}`);
            return;
          }
          console.log(`[FEMALE VOICE LOCK CONFIRMED] ${voiceLock.lockedVoiceName}`);
          sendBootGreetingRequest(socket, sessionId, state.voiceEngineSource, state.voicePersonality);
        });
      }
    }
  },

  previewVoice: (_personality) => {
    speechController.cancel("voice_preview");
    if (!speechController.supported()) return;

    const text = "Hello, sir. I’m here.";
    const utterance = new SpeechSynthesisUtterance(text);
    const voice = getLockedFemaleVoice();

    utterance.voice = voice;
    utterance.rate = 0.93;
    utterance.pitch = 0.97;
    utterance.volume = 0.95;

    utterance.onboundary = (e) => {
      if (e.name === "word") {
        useRuntimeStore.setState({ voiceLevel: 0.45 + Math.random() * 0.45 });
        setTimeout(() => {
          if (window.speechSynthesis?.speaking) {
            useRuntimeStore.setState({ voiceLevel: 0.15 + Math.random() * 0.2 });
          }
        }, 120);
      }
    };
    utterance.onend = () => {
      useRuntimeStore.setState({ voiceLevel: 0.12 });
    };

    try {
      window.speechSynthesis.speak(utterance);
    } catch {}
  },
}));

// ============================================================
// HELPERS
// ============================================================

function createId() {
  return globalThis.crypto?.randomUUID?.() || Math.random().toString(36).slice(2);
}

function providerLabel(provider: string) {
  if (provider === "openai") return "NOVA";
  if (provider === "perplexity") return "NOVA";
  if (provider === "ollama") return "NOVA";
  if (provider === "nova") return "NOVA";
  if (provider === "local") return "QUIET MODE";
  if (provider === "emergency") return "QUIET MODE";
  return provider.toUpperCase();
}

function cleanForSpeech(text: string) {
  return splitCamelCase(text)
    .replace(/\bMr\.\s*/gi, "Mister ")
    .replace(/\bMr\b/gi, "Mister")
    .replace(/\bMrs\.\s*/gi, "Misses ")
    .replace(/\bMrs\b/gi, "Misses")
    .replace(/###\s*(Problem|Steps|Simplification|Final Answer)/gi, "")
    .replace(/\\color\{orange\}/g, "")
    .replace(/\\boxed\{([\s\S]*?)\}/g, "$1")
    .replace(/\\int/g, "integral of ")
    .replace(/\\times/g, " times ")
    .replace(/\\cdot/g, " times ")
    .replace(/\\frac\{([\s\S]*?)\}\{([\s\S]*?)\}/g, "$1 divided by $2")
    .replace(/\$\$/g, "")
    .replace(/\$/g, "")
    .replace(/```[\s\S]*?```/g, "code block")
    .replace(/`([^`]+)`/g, "$1")
    .replace(/\*\*([^*]+)\*\*/g, "$1")
    .replace(/\[([^\]]+)\]\([^)]+\)/g, "$1")
    .replace(/(?<=\d)\s*\+\s*(?=\d)/g, " plus ")
    .replace(/(?<=\d)\s*-\s*(?=\d)/g, " minus ")
    .replace(/(?<=\d)\s*\*\s*(?=\d)/g, " times ")
    .replace(/(?<=\d)\s*\/\s*(?=\d)/g, " divided by ")
    .replace(/([A-Za-z])\-([A-Za-z])/g, "$1 $2")
    .replace(/\^2/g, " squared ")
    .replace(/\^3/g, " cubed ")
    .replace(/\^([a-zA-Z0-9]+)/g, " to the power of $1")
    .replace(/=/g, " equals ")
    .replace(/\\/g, "")
    .replace(/[{}]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function speechSynthesisSupported() {
  return (
    typeof window !== "undefined" &&
    "speechSynthesis" in window &&
    "SpeechSynthesisUtterance" in window
  );
}

function splitCamelCase(text: string) {
  return text.replace(/([a-z])([A-Z])/g, "$1 $2");
}
