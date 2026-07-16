from dataclasses import dataclass

from nova_backend.intelligence.memory_intelligence import MemoryContext, MemoryIntelligence
from nova_backend.intelligence.project_intelligence import ProjectContext, ProjectIntelligence
from nova_backend.intelligence.request_classifier import ClassificationResult, RequestClassifier
from nova_backend.intelligence.task_profiles import TaskProfile, get_task_profile
from nova_backend.intelligence.verification_engine import VerificationEngine, VerificationReport


@dataclass(frozen=True)
class ReasoningRequest:
    message: str
    session: object | None = None
    base_system_instruction: str = ""
    project_root: str = "/Users/aburyanali/Desktop/Project_A"


@dataclass(frozen=True)
class ReasoningResult:
    objective: str
    classification: ClassificationResult
    profile: TaskProfile
    plan: tuple[str, ...]
    system_instruction: str
    memory_context: MemoryContext
    project_context: ProjectContext

    @property
    def max_tokens(self) -> int:
        return self.profile.max_tokens

    @property
    def quality_score_default(self) -> float:
        return 0.0


class ReasoningEngine:
    """NOVA's active intelligence orchestrator."""

    def __init__(self) -> None:
        self.classifier = RequestClassifier()
        self.memory = MemoryIntelligence()
        self.verifier = VerificationEngine()
        self.project_intelligence = ProjectIntelligence("/Users/aburyanali/Desktop/Project_A")

    def prepare(self, request: ReasoningRequest) -> ReasoningResult:
        objective = self.understand_objective(request.message)
        classification = self.classifier.classify(request.message)
        profile = get_task_profile(classification.request_type, classification.depth)
        plan = self.build_plan(objective, classification)
        memory_context = self.memory.build_context(request.message, request.session)
        project_reader = self.project_intelligence
        if request.project_root != str(project_reader.root):
            project_reader = ProjectIntelligence(request.project_root)
        project_context = project_reader.build_context(request.message)
        system_instruction = self.build_system_instruction(
            base_instruction=request.base_system_instruction,
            profile=profile,
            classification=classification,
            objective=objective,
            plan=plan,
            memory_context=memory_context,
            project_context=project_context,
        )
        return ReasoningResult(
            objective=objective,
            classification=classification,
            profile=profile,
            plan=plan,
            system_instruction=system_instruction,
            memory_context=memory_context,
            project_context=project_context,
        )

    def verify_response(self, response: str, result: ReasoningResult) -> VerificationReport:
        return self.verifier.verify(response, result.classification, result.profile)

    @staticmethod
    def understand_objective(message: str) -> str:
        cleaned = " ".join(message.strip().split())
        if not cleaned:
            return "Respond to an empty or unclear user message."
        if len(cleaned) <= 180:
            return cleaned
        return cleaned[:177].rstrip() + "..."

    def build_plan(self, objective: str, classification: ClassificationResult) -> tuple[str, ...]:
        request_type = classification.request_type
        if classification.depth == "shallow":
            return ("Answer directly.", "Check that the response matches the user request.")
        plans: dict[str, tuple[str, ...]] = {
            "coding": (
                "Clarify requirements and assumptions.",
                "Design the implementation approach.",
                "Write complete, maintainable code.",
                "Explain verification and edge cases.",
            ),
            "debugging": (
                "Identify symptoms.",
                "Rank likely causes.",
                "Provide diagnostic steps.",
                "Give the fix and root cause.",
            ),
            "code_review": (
                "Inspect for correctness and risk.",
                "Prioritize findings by severity.",
                "Recommend concrete improvements.",
            ),
            "architecture": (
                "Identify goals and constraints.",
                "Compare design options and tradeoffs.",
                "Recommend a scalable, secure path.",
            ),
            "decision_making": (
                "Identify options and decision criteria.",
                "Compare tradeoffs and risks.",
                "Recommend the best path with caveats.",
            ),
            "game_development": (
                "Define game state and rules.",
                "Provide complete runnable implementation.",
                "Include controls, scoring, reset, and verification.",
            ),
            "project_analysis": (
                "Identify relevant project files.",
                "Read actual code context.",
                "Answer from project evidence, not assumptions.",
                "Call out risks and implementation consequences.",
            ),
            "planning": (
                "Break work into phases.",
                "Identify dependencies and risks.",
                "Give next actions.",
            ),
            "research": (
                "Identify factual claims.",
                "Avoid unsupported certainty.",
                "Summarize with caveats when current data is unavailable.",
            ),
            "mathematics": (
                "Parse the problem.",
                "Solve step by step.",
                "Verify the result.",
            ),
        }
        return plans.get(request_type, ("Understand the request.", "Answer clearly.", "Verify completeness."))

    @staticmethod
    def build_system_instruction(
        base_instruction: str,
        profile: TaskProfile,
        classification: ClassificationResult,
        objective: str,
        plan: tuple[str, ...],
        memory_context: MemoryContext,
        project_context: ProjectContext,
    ) -> str:
        sections = [
            profile.system_instruction,
            f"Current objective: {objective}",
            (
                "Internal response plan. Use this privately; do not reveal hidden reasoning:\n"
                + "\n".join(f"- {step}" for step in plan)
            ),
            (
                "Request metadata:\n"
                f"- type: {classification.request_type}\n"
                f"- depth: {classification.depth}\n"
                f"- classifier confidence: {classification.confidence}"
            ),
            (
                "Self-reflection requirement:\n"
                "- Before finalizing, evaluate correctness, completeness, consistency, and edge cases.\n"
                "- Refine the answer if the first draft is incomplete.\n"
                "- Do not expose chain of thought. Only provide the final answer."
            ),
        ]
        if memory_context.relevant_context:
            sections.append(
                "Relevant memory/context. Use only when helpful; do not mention this section exists:\n"
                f"{memory_context.relevant_context}"
            )
        if project_context.active:
            if project_context.rendered:
                sections.append(project_context.rendered)
            else:
                sections.append(
                    "Project Intelligence Mode active, but no relevant project files were found. "
                    "State that limitation instead of assuming project details."
                )
        if base_instruction:
            sections.append(
                "Existing NOVA style constraints to preserve when they do not conflict with intelligence:\n"
                f"{base_instruction}"
            )
        return "\n\n".join(sections)


reasoning_engine = ReasoningEngine()
