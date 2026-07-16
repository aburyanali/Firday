"use client";

import { AnimatePresence, motion } from "framer-motion";
import { AudioLines, CircleStop, Mic, Radio, Send, Shield, Zap, Cpu, Network, Activity } from "lucide-react";
import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { AssistantState, ChatMessage, RuntimeEvent } from "@/lib/runtime-events";
import { useRuntimeStore } from "@/store/runtime-store";

const labelFor: Record<AssistantState, string> = {
  offline: "OFFLINE",
  booting: "BOOTING",
  ready: "READY",
  idle: "STANDBY",
  listening: "LISTENING",
  thinking: "THINKING",
  analyzing: "THINKING",
  streaming: "RESPONDING",
  planning: "PLANNING",
  executing: "EXECUTING",
  speaking: "SPEAKING",
  processing: "PROCESSING",
  interrupted: "INTERRUPTED",
  warning: "QUIET MODE",
  recovering: "RETRYING",
  error: "RECONNECTING",
  shutdown: "SHUTDOWN"
};

const activeStates: AssistantState[] = ["thinking", "analyzing", "planning", "executing", "processing", "streaming", "speaking"];

export default function NovaHome() {
  const [draft, setDraft] = useState("");
  const [mounted, setMounted] = useState(false);
  const {
    connect,
    disconnect,
    sendMessage,
    sendVoiceFrame,
    interruptSpeaking,
    connected,
    assistantState,
    sessionId,
    messages,
    events,
    voiceLevel,
    latencyMs,
    tokensPerSecond,
    degradedMode,
    activeProvider,
    activeModel,
    lastTokenAt,
    
    // Newly added store variables and methods
    voicePersonality,
    voiceRate,
    voicePitch,
    voiceVolume,
    voiceLinkStatus,
    firstLaunch,
    voiceEngineSource,
    setVoiceSettings,
    triggerReactorBoot,
    previewVoice
  } = useRuntimeStore();

  useEffect(() => {
    setMounted(true);
    connect();
    return () => disconnect();
  }, [connect, disconnect]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape" && activeStates.includes(assistantState)) {
        interruptSpeaking();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [assistantState, interruptSpeaking]);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const message = draft.trim();
    if (!message) return;
    sendMessage(message);
    setDraft("");
  };

  if (!mounted) {
    return (
      <main className="nova-stage offline">
        <div className="fixed inset-0 bg-[#010203] z-[200] flex items-center justify-center">
          <div className="text-[10px] tracking-[0.3em] text-[#2df0ff] font-mono animate-pulse">
            SYNCHRONIZING NOVA OS...
          </div>
        </div>
      </main>
    );
  }

  return (
    <main className={`nova-stage ${assistantState} ${degradedMode ? "degraded" : ""} ${connected ? "linked" : "unlinked"}`}>
      <HudAtmosphere state={assistantState} />
      
      {/* HUD scanline and screen reflections */}
      <div className="hud-overlay-grid" aria-hidden />
      
      <AnimatePresence mode="wait">
        {firstLaunch ? (
          <FirstLaunchSetup 
            personality={voicePersonality}
            setVoiceSettings={setVoiceSettings}
            previewVoice={previewVoice}
            triggerReactorBoot={triggerReactorBoot}
          />
        ) : (
          <motion.section 
            key="hud-composition"
            className="reference-composition"
            initial={{ opacity: 0, scale: 0.98, filter: "blur(12px)" }}
            animate={{ opacity: 1, scale: 1, filter: "blur(0px)" }}
            exit={{ opacity: 0 }}
            transition={{ duration: 1.2, ease: "easeOut" }}
          >
            {/* TOP BAR */}
            <Header 
              state={assistantState} 
              connected={connected} 
              degradedMode={degradedMode} 
              activeProvider={activeProvider} 
              setVoiceSettings={setVoiceSettings}
            />

            {/* LEFT COLUMN - TELEMETRY & DX 62 GRAPH */}
            <LeftTelemetry 
              sessionId={sessionId} 
              latencyMs={latencyMs} 
              tokensPerSecond={tokensPerSecond} 
              events={events} 
              state={assistantState}
            />

            {/* CENTER COLUMN - THE LIVE CONCENTRIC REACTOR */}
            <NeuralReactor 
              state={assistantState} 
              connected={connected} 
              voiceLevel={voiceLevel} 
              lastTokenAt={lastTokenAt} 
            />

            {/* CHAT / MESSAGE CONTAINER */}
            <CommandProtocol
              draft={draft}
              setDraft={setDraft}
              submit={submit}
              messages={messages}
              state={assistantState}
              connected={connected}
              interruptSpeaking={interruptSpeaking}
              degradedMode={degradedMode}
              voiceLinkStatus={voiceLinkStatus}
            />

            {/* RIGHT COLUMN - PERFORMANCE MODULES */}
            <RightHud 
              state={assistantState} 
              connected={connected} 
              degradedMode={degradedMode} 
              activeProvider={activeProvider} 
              activeModel={activeModel}
              latencyMs={latencyMs}
              tokensPerSecond={tokensPerSecond}
              voicePersonality={voicePersonality}
              voiceRate={voiceRate}
              voicePitch={voicePitch}
              voiceVolume={voiceVolume}
              voiceEngineSource={voiceEngineSource}
              setVoiceSettings={setVoiceSettings}
              previewVoice={previewVoice}
            />

            {/* VOICE INPUT SYSTEM */}
            <VoiceSystem state={assistantState} sendVoiceFrame={sendVoiceFrame} />
          </motion.section>
        )}
      </AnimatePresence>
    </main>
  );
}

function Header({ 
  state, 
  connected, 
  degradedMode, 
  activeProvider, 
  setVoiceSettings 
}: { 
  state: AssistantState; 
  connected: boolean; 
  degradedMode: boolean; 
  activeProvider: string; 
  setVoiceSettings: (settings: any) => void;
}) {
  return (
    <header className="hud-header">
      <div className="micro-logo">N</div>
      <div className="hud-title">
        <span>NOVA OS / PHASE 4</span>
        <strong 
          style={{ cursor: "pointer" }} 
          onClick={() => setVoiceSettings({ firstLaunch: true })}
          title="Reset voice choice"
        >
          NEURAL COMMAND INTERFACE
        </strong>
      </div>
      <div className="hud-status-strip">
        <StatusNode icon={<Radio size={13} />} label={connected ? "CONNECTED" : "RECONNECTING"} />
        <StatusNode icon={<Shield size={13} />} label={activeProvider || (degradedMode ? "QUIET MODE" : labelFor[state])} hot={degradedMode || state === "warning"} />
        <StatusNode icon={<Zap size={13} />} label={state === "streaming" && !degradedMode ? "RESPONDING" : "READY"} />
      </div>
    </header>
  );
}

function LeftTelemetry({
  sessionId,
  latencyMs,
  tokensPerSecond,
  events,
  state
}: {
  sessionId: string;
  latencyMs: number;
  tokensPerSecond: number;
  events: RuntimeEvent[];
  state: AssistantState;
}) {
  const [logs, setLogs] = useState<string[]>([]);

  // Scrolling diagnostic lines
  useEffect(() => {
    const diagnosticPool = [
      "DX_62 // SECTOR CHECK: OPTIMAL",
      "FG_84 // FREQ OSCILLATOR: STABLE",
      "SYS // LATENCY TELEMETRY ARMED",
      "NET // COMMAND MATRIX SYNCED",
      "VAD // THRESHOLD METRIC 0.08",
      "RMS // POWER INGEST ACTIVE",
      "CORE // NEURAL WEAVE SECURE",
      "HUD // PROCEDURAL SCAN ACTIVE"
    ];
    setLogs([
      "INITIALIZING TELEMETRY STRIP...",
      "LINK ESTABLISHED ON PORT 8000"
    ]);

    const interval = setInterval(() => {
      const line = diagnosticPool[Math.floor(Math.random() * diagnosticPool.length)];
      setLogs((prev) => [line, ...prev].slice(0, 10));
    }, 4500);

    return () => clearInterval(interval);
  }, []);

  const active = activeStates.includes(state);

  return (
    <aside className="left-reference">
      {/* Oscillating Diagnostic Graphs */}
      <SignalGraph code="DX 62" active={active || tokensPerSecond > 0} color="var(--cyan)" />
      <SignalGraph code="FG 84" active={active || events.length > 0} color="var(--orange)" />
      
      {/* Holographic Diagnostic Panel */}
      <div className="encryption-key">
        <span>ENCRYPTION SYSTEM</span>
        <div className="scrolling-hud-feed">
          {logs.map((log, index) => (
            <div key={index} className="diagnostic-line">
              <span className="bullet">&gt;</span> {log}
            </div>
          ))}
        </div>
        <div className="telemetry-compact-grid">
          <p>LATENCY // {latencyMs ? `${Math.round(latencyMs)} MS` : "PENDING"}</p>
          <p>SPEED // {tokensPerSecond ? `${tokensPerSecond} T/S` : "ARMED"}</p>
          <p>UUID // {sessionId === "pending" ? "AWAITING" : sessionId.slice(0, 8).toUpperCase()}</p>
        </div>
      </div>
      
      {/* Glowing vertical data fragment pipeline */}
      <div className="data-fragment">
        <span>DATA FRAGMENT PIPELINE</span>
        <div className="fragment-line">
          {Array.from({ length: 8 }).map((_, index) => (
            <motion.i 
              key={index} 
              className={`pipeline-accent pip-${index}`} 
              animate={{ opacity: [0.15, 0.8, 0.15] }}
              transition={{ duration: 1.5 + index * 0.4, repeat: Infinity }}
            />
          ))}
        </div>
      </div>
    </aside>
  );
}

function SignalGraph({ code, active, color }: { code: string; active: boolean; color: string }) {
  const [points, setPoints] = useState("5,32 42,31 78,29 115,30 152,28 190,30 230,29 274,28");

  // Realtime graph oscillation to make HUD feel alive
  useEffect(() => {
    let frameId = 0;
    let t = 0;
    const animate = () => {
      t += active ? 0.18 : 0.04;
      const computedPoints = Array.from({ length: 8 }).map((_, idx) => {
        const x = 5 + idx * 38;
        const amplitude = active ? 18 : 3;
        const y = 30 + Math.sin(t + idx * 0.8) * amplitude + Math.cos(t * 0.6 - idx) * (amplitude * 0.4);
        return `${x},${Math.max(10, Math.min(50, y))}`;
      }).join(" ");
      setPoints(computedPoints);
      frameId = requestAnimationFrame(animate);
    };
    animate();
    return () => cancelAnimationFrame(frameId);
  }, [active]);

  return (
    <div className="signal-graph" style={{ borderColor: `${color}25` }}>
      <strong style={{ color }}>{code}</strong>
      <svg viewBox="0 0 290 58" aria-hidden>
        <path d="M0 48H290" />
        <polyline points={points} style={{ stroke: color }} />
        {points.split(" ").map((pt, index) => {
          const [cx, cy] = pt.split(",");
          return (
            <circle 
              key={index} 
              cx={cx} 
              cy={cy} 
              r="2" 
              fill={active ? color : "rgba(233, 251, 255, 0.4)"} 
              style={{ filter: active ? `drop-shadow(0 0 4px ${color})` : "none" }}
            />
          );
        })}
      </svg>
    </div>
  );
}

function NeuralReactor({
  state,
  connected,
  voiceLevel,
  lastTokenAt
}: {
  state: AssistantState;
  connected: boolean;
  voiceLevel: number;
  lastTokenAt: number;
}) {
  const mode = useMemo(() => {
    if (!connected || state === "recovering") return "recovering";
    if (state === "warning" || state === "error") return "warning";
    if (state === "interrupted") return "interrupted";
    if (state === "listening") return "listening";
    if (state === "streaming" || state === "speaking") return "streaming";
    if (activeStates.includes(state)) return "active";
    return "idle";
  }, [connected, state]);

  const tokenPulse = lastTokenAt ? Math.min(1, (Date.now() - lastTokenAt) / 800) : 1;

  // Concentric Rings Rotating speeds based on active states
  const speeds = useMemo(() => {
    switch (mode) {
      case "active":
      case "streaming":
        return { outer: 12, middle: 8, inner: 4, scanner: 3 };
      case "listening":
        return { outer: 26, middle: 16, inner: 10, scanner: 4 };
      case "warning":
      case "recovering":
        return { outer: 48, middle: 32, inner: 18, scanner: 8 };
      default:
        return { outer: 40, middle: 30, inner: 20, scanner: 6 };
    }
  }, [mode]);

  return (
    <section className={`reactor-field ${mode}`}>
      <span className="neural-label">NEURAL MAP</span>
      <span className="core-label">ALGORITHM CORE</span>
      
      {/* Constellation overlay nodes */}
      <div className="connection-web">
        {Array.from({ length: 14 }).map((_, index) => (
          <i key={index} className={`web-line web-${index}`} />
        ))}
        {Array.from({ length: 10 }).map((_, index) => (
          <b key={index} className={`web-node web-node-${index}`} />
        ))}
      </div>

      <div className="reactor-stack" style={{ ["--voice" as any]: voiceLevel, ["--token" as any]: tokenPulse }}>
        {/* Reactor concentric rings with separate rotation parameters */}
        <motion.div 
          className="ring outer-shell" 
          animate={{ rotate: 360 }} 
          transition={{ duration: speeds.outer, repeat: Infinity, ease: "linear" }} 
        />
        <motion.div 
          className="ring cyan-segments" 
          animate={{ rotate: -360 }} 
          transition={{ duration: speeds.middle, repeat: Infinity, ease: "linear" }} 
        />
        <motion.div 
          className="ring inner-cyan" 
          animate={{ rotate: [0, 90, 180, 360] }} 
          transition={{ duration: speeds.inner, repeat: Infinity, ease: "easeInOut" }} 
        />
        <motion.div 
          className="ring orange-arcs" 
          animate={{ rotate: 360 }} 
          transition={{ duration: mode === "interrupted" ? 2 : 18, repeat: Infinity, ease: "linear" }} 
        />
        <motion.div 
          className="ring fine-dial" 
          animate={{ rotate: -360 }} 
          transition={{ duration: 28, repeat: Infinity, ease: "linear" }} 
        />
        <motion.div 
          className="scanner" 
          animate={{ rotate: 360 }} 
          transition={{ duration: speeds.scanner, repeat: Infinity, ease: "linear" }} 
        />

        {/* Micro-nodes orbiting independently */}
        {Array.from({ length: 8 }).map((_, index) => (
          <motion.span
            key={index}
            className={`orbit-dot orbit-${index}`}
            animate={{ rotate: index % 2 ? -360 : 360 }}
            transition={{ duration: 6 + index * 1.5, repeat: Infinity, ease: "linear" }}
          />
        ))}

        {/* Core Nucleus syncing live to audio frequencies */}
        <motion.div
          className="reactor-nucleus"
          animate={{
            scale: state === "speaking" ? 1 + voiceLevel * 0.35 : mode === "streaming" ? [1, 1.05, 1] : [1, 1.02, 1]
          }}
          transition={{ duration: state === "speaking" ? 0.08 : 2.0, repeat: state === "speaking" ? 0 : Infinity, ease: "easeInOut" }}
        >
          <span />
        </motion.div>
      </div>
    </section>
  );
}

function CommandProtocol({
  draft,
  setDraft,
  submit,
  messages,
  state,
  connected,
  interruptSpeaking,
  degradedMode,
  voiceLinkStatus
}: {
  draft: string;
  setDraft: (value: string) => void;
  submit: (event: FormEvent) => void;
  messages: ChatMessage[];
  state: AssistantState;
  connected: boolean;
  interruptSpeaking: () => void;
  degradedMode: boolean;
  voiceLinkStatus: string;
}) {
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const busy = activeStates.includes(state);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages]);

  return (
    <section className="command-zone">
      <div className="protocol-orb">
        <span>COMMAND</span>
        <strong>PROTOCOL</strong>
      </div>
      
      {/* Futuristic chat window with Orange/Cyan accents */}
      <div className="chat-glass">
        <div className="chat-header">
          <span>{degradedMode ? "QUIET RESPONSE" : "CONVERSATION"}</span>
          {busy ? (
            <button type="button" onClick={interruptSpeaking} className="interrupt-control">
              <CircleStop size={12} className="pulse-rose" /> INTERRUPT (ESC)
            </button>
          ) : (
            <AudioLines size={16} className={state === "speaking" ? "animate-pulse active-teal" : ""} />
          )}
        </div>
        
        <div className="message-stream" ref={scrollRef}>
          <AnimatePresence initial={false}>
            {messages.length === 0 && (
              <motion.div key="empty-command" className="empty-command" initial={{ opacity: 0 }} animate={{ opacity: 0.6 }}>
                {voiceLinkStatus || "Voice link standing by"}
              </motion.div>
            )}
            
            {messages.map((message) => {
              const isMath = message.role === "assistant" && (
                message.content.includes("### Problem") || 
                message.content.includes("### Steps") || 
                message.content.includes("### Final Answer")
              );
              return (
                <motion.article
                  key={message.id}
                  layout
                  className={`hud-message ${message.role} ${message.content ? "" : "arming"}`}
                  initial={{ opacity: 0, y: 12, filter: "blur(8px)" }}
                  animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
                  exit={{ opacity: 0 }}
                  transition={{ duration: 0.2 }}
                >
                  <span className="msg-header">{message.role === "user" ? "TRANSMIT" : "NOVA"}</span>
                  {message.content ? (
                    isMath ? (
                      <StructuredMathBlock text={message.content} />
                    ) : (
                      <p>
                        {message.content}
                        {message.role === "assistant" && busy ? <span className="token-caret animate-pulse" /> : null}
                      </p>
                    )
                  ) : (
                    <TypingPulse />
                  )}
                </motion.article>
              );
            })}
          </AnimatePresence>
        </div>
        
        {/* Command console submission bar */}
        <form className="command-input" onSubmit={submit}>
          <input 
            value={draft} 
            onChange={(event) => setDraft(event.target.value)} 
            placeholder={
              state === "recovering"
                ? "One moment..."
                : connected 
                ? "Ask NOVA..." 
                : "NOVA is unavailable..."
            } 
            disabled={!connected || state === "recovering"}
          />
          <button 
            type={busy ? "button" : "submit"} 
            onClick={busy ? interruptSpeaking : undefined} 
            disabled={!connected || state === "recovering"}
          >
            {busy ? <CircleStop size={16} /> : <Send size={16} />}
          </button>
        </form>
      </div>
    </section>
  );
}

function TypingPulse() {
  return (
    <div className="typing-pulse">
      <i />
      <i />
      <i />
      <span>STREAM CONNECTED</span>
    </div>
  );
}

function StructuredMathBlock({ text }: { text: string }) {
  // Parse the sections out of the text
  const problemMatch = text.match(/### Problem([\s\S]*?)(?=### Steps|### Simplification|### Final Answer|$)/i);
  const stepsMatch = text.match(/### Steps([\s\S]*?)(?=### Problem|### Simplification|### Final Answer|$)/i);
  const simplificationMatch = text.match(/### Simplification([\s\S]*?)(?=### Problem|### Steps|### Final Answer|$)/i);
  const finalAnswerMatch = text.match(/### Final Answer([\s\S]*?)(?=### Problem|### Steps|### Simplification|$)/i);

  const cleanMath = (str: string) => {
    return str
      .replace(/\$\$/g, "")
      .replace(/\$/g, "")
      .replace(/\\color\{orange\}/g, "")
      .replace(/\\boxed\{([\s\S]*?)\}/g, "$1")
      .replace(/\\times/g, " × ")
      .replace(/\\cdot/g, " · ")
      .replace(/\\int/g, "∫ ")
      .replace(/\\delta/g, "δ")
      .replace(/\\Delta/g, "Δ")
      .replace(/\\pi/g, "π")
      .replace(/\\infty/g, "∞")
      .replace(/\\sqrt\{([\s\S]*?)\}/g, "√($1)")
      .trim();
  };

  const problem = problemMatch ? cleanMath(problemMatch[1]) : "";
  const stepsText = stepsMatch ? stepsMatch[1].trim() : "";
  const simplification = simplificationMatch ? cleanMath(simplificationMatch[1]) : "";
  const finalAnswer = finalAnswerMatch ? cleanMath(finalAnswerMatch[1]) : "";

  // Split steps into bullet items
  const steps = stepsText
    .split(/\n+/)
    .map((line) => line.replace(/^-\s*/, "").trim())
    .filter((line) => line.length > 0)
    .map((step) => cleanMath(step));

  return (
    <div className="math-structured-panel border border-[rgba(93,246,208,0.25)] bg-[rgba(3,5,8,0.75)] p-5 rounded relative overflow-hidden backdrop-blur-md my-4">
      {/* Grid pattern background */}
      <div className="absolute inset-0 bg-[linear-gradient(rgba(93,246,208,0.02)_1px,transparent_1px),linear-gradient(90deg,rgba(93,246,208,0.02)_1px,transparent_1px)] bg-[size:16px_16px]" />
      
      {/* Corner indicators */}
      <span className="absolute top-0 left-0 w-2 h-2 border-t-2 border-l-2 border-[var(--cyan)]" />
      <span className="absolute top-0 right-0 w-2 h-2 border-t-2 border-r-2 border-[var(--cyan)]" />
      <span className="absolute bottom-0 left-0 w-2 h-2 border-b-2 border-l-2 border-[var(--cyan)]" />
      <span className="absolute bottom-0 right-0 w-2 h-2 border-b-2 border-r-2 border-[var(--cyan)]" />

      <div className="relative z-10 flex flex-col gap-5">
        <div className="flex items-center justify-between border-b border-[rgba(93,246,208,0.15)] pb-2">
          <span className="text-[10px] tracking-[0.2em] text-[var(--cyan)] font-mono">MATH SOLUTION</span>
          <span className="text-[10px] tracking-[0.1em] text-[var(--orange)] font-mono">STEP BY STEP</span>
        </div>

        {problem && (
          <div className="math-block-section">
            <h4 className="text-[10px] font-mono text-[var(--cyan)] tracking-wider mb-2 flex items-center gap-2">
              <span className="w-1.5 h-1.5 rounded-full bg-[var(--cyan)] animate-ping" /> PROBLEM STATEMENT
            </h4>
            <div className="bg-[rgba(93,246,208,0.03)] border border-[rgba(93,246,208,0.1)] rounded p-4 text-center text-lg font-serif italic text-slate-200">
              {problem}
            </div>
          </div>
        )}

        {steps.length > 0 && (
          <div className="math-block-section">
            <h4 className="text-[10px] font-mono text-[var(--cyan)] tracking-wider mb-2">SEQUENCE OF STEPS</h4>
            <div className="flex flex-col gap-2 font-mono text-xs text-slate-300 pl-2 border-l-2 border-[rgba(93,246,208,0.15)]">
              {steps.map((step, idx) => (
                <div key={idx} className="flex gap-3 py-1">
                  <span className="text-[var(--orange)] font-bold">[{idx + 1}]</span>
                  <p>{step}</p>
                </div>
              ))}
            </div>
          </div>
        )}

        {simplification && (
          <div className="math-block-section">
            <h4 className="text-[10px] font-mono text-[var(--cyan)] tracking-wider mb-2">SIMPLIFICATION STAGES</h4>
            <div className="bg-[rgba(93,246,208,0.02)] border border-[rgba(93,246,208,0.06)] rounded p-3 font-mono text-center text-sm text-[rgba(233,251,255,0.85)]">
              {simplification}
            </div>
          </div>
        )}

        {finalAnswer && (
          <div className="math-block-section mt-2">
            <h4 className="text-[10px] font-mono text-[var(--orange)] tracking-wider mb-2">RESOLVED OUTCOME</h4>
            <div className="border-2 border-[var(--orange)] bg-[rgba(255,118,28,0.05)] rounded p-5 text-center shadow-[0_0_15px_rgba(255,118,28,0.15)] overflow-hidden relative group">
              <span className="absolute inset-0 bg-[radial-gradient(circle_at_center,rgba(255,118,28,0.08)_0%,transparent_70%)] animate-pulse" />
              <p className="text-2xl font-bold font-mono tracking-wide text-[var(--orange)] drop-shadow-[0_0_10px_rgba(255,118,28,0.5)]">
                {finalAnswer}
              </p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function FirstLaunchSetup({
  personality,
  setVoiceSettings,
  previewVoice,
  triggerReactorBoot
}: {
  personality: "jarvis" | "friday" | "tactical" | "neutral";
  setVoiceSettings: (settings: any) => void;
  previewVoice: (p: any) => void;
  triggerReactorBoot: () => void;
}) {
  const [igniting, setIgniting] = useState(false);

  const startIgnition = () => {
    setIgniting(true);
    setTimeout(() => {
      triggerReactorBoot();
    }, 1500);
  };

  const options: { id: typeof personality; label: string; desc: string; sample: string }[] = [
    {
      id: "jarvis",
      label: "POLISHED // RESERVED",
      desc: "Calm, formal, and concise.",
      sample: "I’m here, sir. What are we working on?"
    },
    {
      id: "friday",
      label: "CALM // WARM",
      desc: "Warm, attentive, and easy to listen to.",
      sample: "Hello, sir. What’s on your mind?"
    },
    {
      id: "neutral",
      label: "BALANCED // CLEAR",
      desc: "Precise, objective, and composed.",
      sample: "Good evening, sir. What are we tackling?"
    },
    {
      id: "tactical",
      label: "DIRECT // FOCUSED",
      desc: "Short, direct, and practical.",
      sample: "I have it, sir. Give me a moment."
    }
  ];

  return (
    <motion.div 
      className="first-launch-overlay"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.8 }}
    >
      <div className="setup-container">
        <h2 className="setup-title">NOVA INTEL OS</h2>
        <span className="setup-subtitle">VOICE SETUP</span>
        
        <p className="text-slate-400 text-sm max-w-lg mb-6 leading-relaxed text-center">
          Choose the voice you want NOVA to use.
        </p>

        <div className="setup-options-grid">
          {options.map((opt) => (
            <div 
              key={opt.id} 
              className={`setup-card ${personality === opt.id ? "selected" : ""}`}
              onClick={() => setVoiceSettings({ voicePersonality: opt.id })}
            >
              <div className="card-selection-indicator" />
              <strong>{opt.label}</strong>
              <p>{opt.desc}</p>
              
              <button 
                type="button" 
                className="preview-btn"
                onClick={(e) => {
                  e.stopPropagation();
                  previewVoice(opt.id);
                }}
              >
                PREVIEW IDENTITY
              </button>
            </div>
          ))}
        </div>

        <button 
          type="button" 
          className={`ignite-reactor-btn ${igniting ? "igniting" : ""}`}
          onClick={startIgnition}
          disabled={igniting}
        >
          {igniting ? "Starting..." : "Start NOVA"}
        </button>
      </div>
    </motion.div>
  );
}

function RightHud({
  state,
  connected,
  degradedMode,
  activeProvider,
  activeModel,
  latencyMs,
  tokensPerSecond,
  voicePersonality,
  voiceRate,
  voicePitch,
  voiceVolume,
  voiceEngineSource,
  setVoiceSettings,
  previewVoice
}: {
  state: AssistantState;
  connected: boolean;
  degradedMode: boolean;
  activeProvider: string;
  activeModel: string;
  latencyMs: number;
  tokensPerSecond: number;
  voicePersonality: "jarvis" | "friday" | "tactical" | "neutral";
  voiceRate: number;
  voicePitch: number;
  voiceVolume: number;
  voiceEngineSource: "browser" | "backend";
  setVoiceSettings: (settings: any) => void;
  previewVoice: (p: any) => void;
}) {
  const [showConfig, setShowConfig] = useState(false);

  return (
    <aside className="right-reference">
      <div className="module-readout">
        <h3>NOVA</h3>
        <p className="status-item" style={statusItemStyle}>
          <span>CONNECTION</span>
          <strong>{connected ? "CONNECTED" : "RECONNECTING"}</strong>
        </p>
        <p className="status-item" style={statusItemStyle}>
          <span>RESPONSE</span>
          <strong style={{ color: degradedMode ? "var(--orange)" : "var(--cyan)" }}>
            {activeProvider || (degradedMode ? "QUIET MODE" : "READY")}
          </strong>
        </p>
        <p className="status-item" style={statusItemStyle}>
          <span>VOICE</span>
          <strong>{activeModel || "STANDBY"}</strong>
        </p>
        <p className="status-item" style={statusItemStyle}>
          <span>STATE</span>
          <strong className="accent-blink">{labelFor[state]}</strong>
        </p>

        {/* Sliding configuration toggler */}
        <button 
          type="button" 
          className="settings-toggle-btn"
          onClick={() => setShowConfig(!showConfig)}
        >
          {showConfig ? "CLOSE CONFIG PROTOCOL" : "OPEN CONFIG PROTOCOL"}
        </button>

        {/* Glassmorphic sliding configs panel */}
        {showConfig && (
          <motion.div 
            className="settings-config-pane"
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.2 }}
          >
            <h4>VOCAL OS PACKS</h4>
            
            <div className="config-slider-group">
              <label>PERSONALITY IDENTITY</label>
              <div className="config-readonly-badge" style={{ color: "var(--cyan)", fontFamily: "monospace", fontSize: "11px", letterSpacing: "1px", textTransform: "uppercase", padding: "8px", border: "1px solid rgba(0,242,254,0.2)", borderRadius: "4px", background: "rgba(0,242,254,0.05)" }}>
                FEMALE AI CORE (FRIDAY) [LOCKED]
              </div>
            </div>

            <div className="config-slider-group">
              <label>SPEECH SYNTHESIS PATH</label>
              <div className="config-readonly-badge" style={{ color: "var(--orange)", fontFamily: "monospace", fontSize: "11px", letterSpacing: "1px", textTransform: "uppercase", padding: "8px", border: "1px solid rgba(255,118,28,0.2)", borderRadius: "4px", background: "rgba(255,118,28,0.05)" }}>
                {voiceEngineSource === "browser" ? "BROWSER VOICE" : "MAC VOICE"}
              </div>
            </div>

            <div className="config-slider-group">
              <label>
                <span>SPEED / RATE</span>
                <span>{voiceRate}x</span>
              </label>
              <input 
                type="range" 
                min="0.8" 
                max="1.3" 
                step="0.05" 
                value={voiceRate}
                onChange={(e) => setVoiceSettings({ voiceRate: parseFloat(e.target.value) })}
              />
            </div>

            <div className="config-slider-group">
              <label>
                <span>TONE / PITCH</span>
                <span>{voicePitch}x</span>
              </label>
              <input 
                type="range" 
                min="0.8" 
                max="1.2" 
                step="0.05" 
                value={voicePitch}
                onChange={(e) => setVoiceSettings({ voicePitch: parseFloat(e.target.value) })}
              />
            </div>

            <div className="config-slider-group">
              <label>
                <span>OS SPEAKER VOLUME</span>
                <span>{Math.round(voiceVolume * 100)}%</span>
              </label>
              <input 
                type="range" 
                min="0.5" 
                max="1.0" 
                step="0.05" 
                value={voiceVolume}
                onChange={(e) => setVoiceSettings({ voiceVolume: parseFloat(e.target.value) })}
              />
            </div>

            <div className="config-actions">
              <button 
                type="button" 
                className="config-btn-primary"
                onClick={() => previewVoice(voicePersonality)}
              >
                PREVIEW IDENTITY
              </button>
              <button 
                type="button" 
                className="config-btn-secondary"
                onClick={() => setVoiceSettings({ firstLaunch: true })}
              >
                RESET OS
              </button>
            </div>
          </motion.div>
        )}
      </div>
      
      {/* Glowing progress wheels representing HUD dials */}
      <div className="telemetry-dials">
        <TelemetryDial 
          value={latencyMs ? Math.min(100, (latencyMs / 1000) * 100) : 0} 
          label="LATENCY" 
          valueText={latencyMs ? `${Math.round(latencyMs)}ms` : "0ms"} 
          color="var(--cyan)"
        />
        <TelemetryDial 
          value={tokensPerSecond ? Math.min(100, (tokensPerSecond / 80) * 100) : 0} 
          label="COMPUTATION" 
          valueText={tokensPerSecond ? `${tokensPerSecond} t/s` : "STANDBY"} 
          color="var(--orange)"
        />
      </div>
    </aside>
  );
}

const statusItemStyle = {
  display: "flex",
  alignItems: "baseline",
  justifyContent: "space-between",
  gap: "12px"
} as const;

function TelemetryDial({ value, label, valueText, color }: { value: number; label: string; valueText: string; color: string }) {
  const radius = 28;
  const circumference = 2 * Math.PI * radius;
  const strokeDashoffset = circumference - (value / 100) * circumference;

  return (
    <div className="hud-dial-box">
      <svg width="78" height="78" viewBox="0 0 78 78">
        <circle 
          cx="39" 
          cy="39" 
          r={radius} 
          fill="none" 
          stroke="rgba(255,255,255,0.04)" 
          strokeWidth="3" 
        />
        <circle 
          cx="39" 
          cy="39" 
          r={radius} 
          fill="none" 
          stroke={color} 
          strokeWidth="3.5" 
          strokeDasharray={circumference}
          strokeDashoffset={strokeDashoffset}
          style={{ transition: "stroke-dashoffset 0.35s ease", filter: `drop-shadow(0 0 4px ${color})` }}
        />
      </svg>
      <div className="dial-labels">
        <small>{label}</small>
        <strong>{valueText}</strong>
      </div>
    </div>
  );
}

function VoiceSystem({ state, sendVoiceFrame }: { state: AssistantState; sendVoiceFrame: (base64Data: string) => void }) {
  const [enabled, setEnabled] = useState(false);
  const [levels, setLevels] = useState(Array.from({ length: 18 }, () => 0.16));
  const recognitionRef = useRef<any>(null);
  const wakeArmedRef = useRef(false);
  const enabledRef = useRef(false); // Mirror for use inside closures
  const watchdogRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const lastResultRef = useRef(Date.now());
  const silenceTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const streamRefs = useRef<{ stream: MediaStream | null; context: AudioContext | null; raf: number }>({
    stream: null, context: null, raf: 0
  });

  const { sendMessage, interruptSpeaking, sendTranscript } = useRuntimeStore();

  // Phase 4.8.6: Always cancel TTS on mic activation
  const cancelTTS = () => {
    if (typeof window !== "undefined" && "speechSynthesis" in window) {
      try {
        console.log("[VOICE CANCEL] reason=microphone_activation");
        window.speechSynthesis.cancel();
      } catch {}
    }
  };

  const startRecognition = () => {
    if (!enabledRef.current) return;

    const SpeechRecognitionCtor =
      (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (!SpeechRecognitionCtor) return;

    // Clean up stale recognition
    const existing = recognitionRef.current;
    if (existing) {
      try { existing.abort(); } catch {}
    }

    const recognition = new SpeechRecognitionCtor();
    recognitionRef.current = recognition;
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.lang = "en-US";
    recognition.maxAlternatives = 1;

    recognition.onstart = () => {
      lastResultRef.current = Date.now();
      useRuntimeStore.setState({ assistantState: "listening" });
    };

    recognition.onresult = (event: any) => {
      if (silenceTimerRef.current) clearTimeout(silenceTimerRef.current);
      lastResultRef.current = Date.now();

      let interim = "";
      let finalText = "";
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const transcript = event.results[i][0]?.transcript || "";
        if (event.results[i].isFinal) {
          finalText += transcript;
        } else {
          interim += transcript;
        }
      }

      const liveText = `${finalText} ${interim}`.trim();
      if (!liveText) return;

      const wake = detectWakePhrase(liveText);
      if (wake) {
        wakeArmedRef.current = true;
        cancelTTS();
        interruptSpeaking();
        useRuntimeStore.setState({ assistantState: "listening" });
      }
      sendTranscript(liveText, Boolean(finalText), Boolean(wake));

      // 1.2s silence detection auto-submit
      silenceTimerRef.current = setTimeout(() => {
        const cleaned = stripWakePhrase(liveText).trim();
        if (cleaned) {
          cancelTTS();
          interruptSpeaking();
          sendMessage(cleaned);
          // Restart recognition after message send
          setTimeout(() => {
            if (enabledRef.current) startRecognition();
          }, 200);
        }
      }, 1200);

      if (finalText) {
        const cleaned = stripWakePhrase(finalText).trim();
        if (wakeArmedRef.current && cleaned) {
          wakeArmedRef.current = false;
          cancelTTS();
          sendMessage(cleaned);
        } else if (wake && !cleaned) {
          wakeArmedRef.current = true;
        }
      }
    };

    recognition.onend = () => {
      // Phase 4.8.6: Watchdog handles restart — onend should just restart if enabled
      if (enabledRef.current) {
        setTimeout(() => {
          if (enabledRef.current) startRecognition();
        }, 180);
      }
    };

    recognition.onerror = (event: any) => {
      const error = event?.error;
      if (error === "aborted" || error === "no-speech") {
        // Non-fatal — restart
        if (enabledRef.current) {
          setTimeout(() => {
            if (enabledRef.current) startRecognition();
          }, 300);
        }
      } else if (error === "network") {
        // Network error — retry with exponential backoff
        if (enabledRef.current) {
          setTimeout(() => {
            if (enabledRef.current) startRecognition();
          }, 800);
        }
      } else if (error === "not-allowed" || error === "service-not-allowed") {
        // Hard error — disable mic
        enabledRef.current = false;
        setEnabled(false);
      } else {
        // Unknown — restart with delay
        if (enabledRef.current) {
          setTimeout(() => {
            if (enabledRef.current) startRecognition();
          }, 500);
        }
      }
    };

    try {
      recognition.start();
    } catch {
      // Already started — ignore
    }
  };

  // Phase 4.8.6: Watchdog timer — checks every 2s for stale recognition
  const startWatchdog = () => {
    if (watchdogRef.current) clearInterval(watchdogRef.current);
    watchdogRef.current = setInterval(() => {
      if (!enabledRef.current) return;

      const recognition = recognitionRef.current;
      const staleSince = Date.now() - lastResultRef.current;

      // If recognition has been silent for >8s and no results — restart
      if (staleSince > 8000) {
        const isAlive =
          recognition &&
          typeof recognition.abort === "function";

        if (isAlive) {
          try { recognition.abort(); } catch {}
        }
        setTimeout(() => {
          if (enabledRef.current) startRecognition();
        }, 200);
        lastResultRef.current = Date.now();
      }
    }, 2000);
  };

  useEffect(() => {
    enabledRef.current = enabled;

    if (!enabled) {
      // Cleanup on disable
      if (watchdogRef.current) {
        clearInterval(watchdogRef.current);
        watchdogRef.current = null;
      }
      if (silenceTimerRef.current) {
        clearTimeout(silenceTimerRef.current);
        silenceTimerRef.current = null;
      }
      const recognition = recognitionRef.current;
      if (recognition) {
        try { recognition.abort(); } catch {}
        recognitionRef.current = null;
      }

      // Release media streams
      streamRefs.current.stream?.getTracks().forEach((t) => t.stop());
      streamRefs.current.context?.close().catch(() => {});
      cancelAnimationFrame(streamRefs.current.raf);
      streamRefs.current = { stream: null, context: null, raf: 0 };
      return;
    }

    // Phase 4.6: Cancel TTS once when the microphone is intentionally activated
    cancelTTS();

    const start = async () => {
      try {
        const SpeechRecognitionCtor =
          (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
        if (!SpeechRecognitionCtor) {
          useRuntimeStore.setState({ lastError: "Speech recognition unavailable." });
          setEnabled(false);
          enabledRef.current = false;
          return;
        }

        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        streamRefs.current.stream = stream;

        const context = new AudioContext({ sampleRate: 16000 });
        streamRefs.current.context = context;

        const source = context.createMediaStreamSource(stream);
        const analyser = context.createAnalyser();
        analyser.fftSize = 64;
        source.connect(analyser);

        const processor = context.createScriptProcessor(2048, 1, 1);
        source.connect(processor);
        processor.connect(context.destination);
        processor.onaudioprocess = (e) => {
          if (!enabledRef.current) return;
          const pcm = e.inputBuffer.getChannelData(0);
          const int16 = new Int16Array(pcm.length);
          for (let i = 0; i < pcm.length; i++) {
            const s = Math.max(-1, Math.min(1, pcm[i]));
            int16[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
          }
          sendVoiceFrame(btoa(String.fromCharCode.apply(null, new Uint8Array(int16.buffer) as unknown as number[])));
        };

        startRecognition();
        startWatchdog();

        const data = new Uint8Array(analyser.frequencyBinCount);
        const frame = () => {
          analyser.getByteFrequencyData(data);
          setLevels(Array.from(data.slice(0, 18)).map((v) => Math.max(0.12, v / 255)));
          streamRefs.current.raf = requestAnimationFrame(frame);
        };
        frame();
      } catch (err) {
        console.error("Microphone access failed:", err);
        setEnabled(false);
        enabledRef.current = false;
      }
    };

    start();

    return () => {
      enabledRef.current = false;

      if (watchdogRef.current) {
        clearInterval(watchdogRef.current);
        watchdogRef.current = null;
      }
      if (silenceTimerRef.current) {
        clearTimeout(silenceTimerRef.current);
        silenceTimerRef.current = null;
      }

      const recognition = recognitionRef.current;
      if (recognition) {
        try { recognition.abort(); } catch {}
        recognitionRef.current = null;
      }

      cancelAnimationFrame(streamRefs.current.raf);
      streamRefs.current.stream?.getTracks().forEach((t) => t.stop());
      streamRefs.current.context?.close().catch(() => {});
      streamRefs.current = { stream: null, context: null, raf: 0 };
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled]);

  // Passive waveform animation when mic is off
  useEffect(() => {
    if (enabled) return;
    let raf = 0;
    let tick = 0;
    const loop = () => {
      tick += state === "speaking" || state === "streaming" ? 0.16 : 0.055;
      setLevels((current) =>
        current.map((_, i) =>
          activeStates.includes(state)
            ? 0.32 + Math.sin(tick + i * 0.6) * 0.22 + Math.cos(tick * 0.7 - i) * 0.1
            : 0.14 + Math.sin(tick + i) * 0.035
        )
      );
      raf = requestAnimationFrame(loop);
    };
    loop();
    return () => cancelAnimationFrame(raf);
  }, [enabled, state]);

  return (
    <section className="voice-strip">
      <button
        type="button"
        className={enabled ? "mic-toggle active" : "mic-toggle"}
        onClick={() => setEnabled((v) => !v)}
        aria-label="Toggle microphone"
      >
        <Mic size={16} />
      </button>
      <div className="voice-bars">
        {levels.map((level, i) => (
          <motion.i
            key={i}
            animate={{ height: 8 + level * 54 }}
            transition={{ type: "spring", stiffness: 260, damping: 24 }}
            style={{
              background: state === "speaking"
                ? "linear-gradient(180deg, var(--teal, #5df6d0), var(--cyan))"
                : "linear-gradient(180deg, var(--cyan), var(--orange))"
            }}
          />
        ))}
      </div>
    </section>
  );
}




const wakePhrases = [
  "wake up nova",
  "hey nova",
  "time to work nova",
  "you there nova",
  "up there nova",
  "wake up, nova",
  "time to work, nova",
  "you there, nova",
  "up there, nova"
];

function detectWakePhrase(text: string) {
  const normalized = text.toLowerCase().replace(/[?.,!-]/g, "").replace(/\s+/g, " ").trim();
  
  // Exact match or includes
  const matched = wakePhrases.some((phrase) => {
    const cleanPhrase = phrase.toLowerCase().replace(/[?.,!-]/g, "").trim();
    return normalized.includes(cleanPhrase);
  });
  
  if (matched) return true;
  
  // Fuzzy token check: check if the word "nova" appears separately
  const tokens = normalized.split(" ");
  if (tokens.includes("nova")) return true;
  
  return false;
}

function stripWakePhrase(text: string) {
  let cleaned = text;
  for (const phrase of wakePhrases) {
    cleaned = cleaned.replace(new RegExp(escapeRegExp(phrase).replace("\\,\\ ", "[, ]*").replace("\\?", "\\??"), "ig"), "");
  }
  return cleaned.replace(/[?.,!]\s*$/, "").trim();
}

function escapeRegExp(value: string) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function HudAtmosphere({ state }: { state: AssistantState }) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext("2d");
    if (!canvas || !ctx) return;
    let raf = 0;
    let tick = 0;
    const resize = () => {
      const ratio = window.devicePixelRatio || 1;
      canvas.width = window.innerWidth * ratio;
      canvas.height = window.innerHeight * ratio;
      ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    };
    const draw = () => {
      const width = window.innerWidth;
      const height = window.innerHeight;
      tick += activeStates.includes(state) ? 0.016 : 0.006;
      ctx.clearRect(0, 0, width, height);
      ctx.fillStyle = "#030508";
      ctx.fillRect(0, 0, width, height);
      ctx.lineWidth = 1;
      for (let x = -80; x < width + 120; x += 58) {
        ctx.strokeStyle = `rgba(47, 210, 235, ${0.018 + Math.sin(tick + x) * 0.005})`;
        ctx.beginPath();
        ctx.moveTo(x + Math.sin(tick + x * 0.01) * 6, 0);
        ctx.lineTo(x - 210, height);
        ctx.stroke();
      }
      for (let y = 0; y < height; y += 58) {
        ctx.strokeStyle = "rgba(255, 118, 28, 0.014)";
        ctx.beginPath();
        ctx.moveTo(0, y);
        ctx.lineTo(width, y + Math.cos(tick + y) * 3);
        ctx.stroke();
      }
      const cx = width * 0.63;
      const cy = height * 0.42;
      const gradient = ctx.createRadialGradient(cx, cy, 0, cx, cy, Math.min(width, height) * 0.55);
      gradient.addColorStop(0, state === "warning" ? "rgba(255, 122, 32, 0.12)" : "rgba(38, 215, 242, 0.13)");
      gradient.addColorStop(0.45, "rgba(15, 75, 84, 0.04)");
      gradient.addColorStop(1, "rgba(0,0,0,0)");
      ctx.fillStyle = gradient;
      ctx.beginPath();
      ctx.arc(cx, cy, Math.min(width, height) * 0.56, 0, Math.PI * 2);
      ctx.fill();
      raf = requestAnimationFrame(draw);
    };
    resize();
    draw();
    window.addEventListener("resize", resize);
    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("resize", resize);
    };
  }, [state]);

  return <canvas ref={canvasRef} className="hud-atmosphere" aria-hidden />;
}

function StatusNode({ icon, label, hot }: { icon: React.ReactNode; label: string; hot?: boolean }) {
  return (
    <div className={hot ? "status-node hot" : "status-node"}>
      {icon}
      <span>{label}</span>
    </div>
  );
}
