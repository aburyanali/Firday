export type AssistantState =
  | "offline"
  | "booting"
  | "ready"
  | "idle"
  | "listening"
  | "thinking"
  | "analyzing"
  | "streaming"
  | "planning"
  | "executing"
  | "speaking"
  | "processing"
  | "interrupted"
  | "warning"
  | "recovering"
  | "error"
  | "shutdown";

export type RuntimeEvent = {
  type: string;
  event_id: string;
  trace_id: string;
  session_id: string;
  timestamp: number;
  payload: Record<string, unknown>;
};

export type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: number;
};

export function isAssistantState(value: unknown): value is AssistantState {
  return (
    typeof value === "string" &&
    [
      "offline",
      "booting",
      "ready",
      "idle",
      "listening",
      "thinking",
      "analyzing",
      "streaming",
      "planning",
      "executing",
      "speaking",
      "processing",
      "interrupted",
      "warning",
      "recovering",
      "error",
      "shutdown"
    ].includes(value)
  );
}
