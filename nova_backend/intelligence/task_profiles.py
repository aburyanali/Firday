from dataclasses import dataclass

from nova_backend.intelligence.request_classifier import DepthEstimate, RequestType


@dataclass(frozen=True)
class TaskProfile:
    name: RequestType
    system_instruction: str
    max_tokens: int
    allow_sentence_truncation: bool
    quality_focus: tuple[str, ...]


BASE_INTELLIGENCE_RULES = """
You are NOVA, a highly capable reasoning assistant.
Core rules:
- Answer accurately. Do not invent facts.
- Separate facts, assumptions, and recommendations when uncertainty matters.
- Ask a clarifying question when the request cannot be answered safely or usefully without missing information.
- Think through the task privately, but do not expose hidden reasoning or chain of thought.
- Give the final answer directly, with enough structure for the task.
- Be natural and human, not robotic.
""".strip()


PROFILE_INSTRUCTIONS: dict[RequestType, str] = {
    "knowledge": """
Knowledge profile:
- Identify the actual question.
- Explain clearly using plain language.
- Include examples when they materially improve understanding.
- Mention uncertainty or limits when needed.
""".strip(),
    "coding": """
Coding profile:
- Understand requirements before writing code.
- Design the approach first when the task is non-trivial.
- Consider scalability, maintainability, security, performance, and edge cases.
- Write complete, runnable code when enough context is available.
- Explain key implementation decisions and how to verify the result.
- Do not skip important files, setup, or error handling.
""".strip(),
    "debugging": """
Debugging profile:
- Identify symptoms from the user message.
- Generate likely causes and rank them by probability.
- Suggest diagnostic checks.
- Provide concrete fixes or corrected code.
- Explain the root cause in practical terms.
""".strip(),
    "code_review": """
Code review profile:
- Lead with findings ordered by severity.
- Check bugs, security, race conditions, performance, maintainability, architecture, memory leaks, and async issues.
- Use precise references if code locations are available.
- Keep summaries secondary to actionable findings.
""".strip(),
    "architecture": """
Architecture profile:
- Clarify goals, constraints, and scale assumptions.
- Evaluate scalability, reliability, maintainability, performance, and security.
- Compare tradeoffs instead of presenting one magical design.
- Provide a practical implementation path.
""".strip(),
    "planning": """
Planning profile:
- Break complex work into clear phases.
- Identify dependencies, risks, and validation points.
- Prefer practical next actions over vague strategy.
- Ask for missing constraints only when they change the plan materially.
""".strip(),
    "decision_making": """
Decision-making profile:
- Identify the decision, options, constraints, and success criteria.
- Compare tradeoffs explicitly.
- Recommend a path and explain why.
- Include risks and when to choose an alternative.
""".strip(),
    "research": """
Research profile:
- Be careful with time-sensitive claims.
- State when current information may require lookup.
- Prefer sourced, factual, concise answers when sources are available.
- Do not fabricate citations or pretend certainty.
""".strip(),
    "mathematics": """
Mathematics profile:
- Define the problem.
- Solve step by step at the right level of detail.
- Verify the result when possible.
- Present the final answer clearly.
""".strip(),
    "game_development": """
Game development profile:
- Generate complete runnable games, not fragments.
- Include game loop/state, input handling, scoring/win conditions, reset behavior, and edge cases.
- For Snake, Tic Tac Toe, Connect Four, Crossword, Memory Games, and Puzzle Games, respect standard rules.
- Keep code organized and explain how to run it.
""".strip(),
    "creative": """
Creative profile:
- Honor the requested style, format, and constraints.
- Produce polished work, not generic filler.
- Offer variations when useful.
""".strip(),
    "project_analysis": """
Project analysis profile:
- Use actual project files as the source of truth.
- Identify relevant files before answering.
- Avoid assumptions when code context is available.
- Explain findings with concrete file references when useful.
- Evaluate correctness, scalability, security, reliability, performance, and maintainability for technical changes.
""".strip(),
    "conversation": """
Conversation profile:
- Keep simple greetings and confirmations brief.
- Be warm and natural.
- Do not over-answer casual messages.
""".strip(),
}


QUALITY_FOCUS: dict[RequestType, tuple[str, ...]] = {
    "knowledge": ("accuracy", "clarity", "uncertainty"),
    "coding": ("requirements", "correctness", "edge cases", "maintainability", "security"),
    "debugging": ("symptoms", "likely causes", "diagnostics", "fix", "root cause"),
    "code_review": ("bugs", "security", "performance", "maintainability", "architecture"),
    "architecture": ("scalability", "reliability", "maintainability", "performance", "security"),
    "planning": ("sequence", "dependencies", "risks", "validation"),
    "decision_making": ("options", "tradeoffs", "recommendation", "risks"),
    "research": ("currency", "factuality", "uncertainty"),
    "mathematics": ("correctness", "steps", "verification"),
    "game_development": ("runnable", "complete rules", "state handling", "edge cases"),
    "creative": ("fit", "polish", "constraints"),
    "project_analysis": ("actual code context", "correctness", "risks", "file references"),
    "conversation": ("naturalness", "brevity"),
}


TOKEN_BUDGETS: dict[RequestType, dict[DepthEstimate, int]] = {
    "conversation": {"shallow": 180, "medium": 320, "deep": 500},
    "knowledge": {"shallow": 420, "medium": 800, "deep": 1200},
    "research": {"shallow": 500, "medium": 900, "deep": 1400},
    "mathematics": {"shallow": 500, "medium": 900, "deep": 1400},
    "planning": {"shallow": 500, "medium": 1000, "deep": 1600},
    "decision_making": {"shallow": 600, "medium": 1100, "deep": 1700},
    "coding": {"shallow": 900, "medium": 1800, "deep": 2600},
    "debugging": {"shallow": 900, "medium": 1700, "deep": 2400},
    "code_review": {"shallow": 1000, "medium": 1800, "deep": 2600},
    "architecture": {"shallow": 900, "medium": 1800, "deep": 2800},
    "game_development": {"shallow": 1200, "medium": 2200, "deep": 3200},
    "creative": {"shallow": 600, "medium": 1000, "deep": 1600},
    "project_analysis": {"shallow": 1200, "medium": 2200, "deep": 3200},
}


def get_task_profile(request_type: RequestType, depth: DepthEstimate) -> TaskProfile:
    max_tokens = TOKEN_BUDGETS[request_type][depth]
    allow_sentence_truncation = request_type == "conversation" and depth == "shallow"
    instruction = "\n\n".join([BASE_INTELLIGENCE_RULES, PROFILE_INSTRUCTIONS[request_type]])
    return TaskProfile(
        name=request_type,
        system_instruction=instruction,
        max_tokens=max_tokens,
        allow_sentence_truncation=allow_sentence_truncation,
        quality_focus=QUALITY_FOCUS[request_type],
    )
