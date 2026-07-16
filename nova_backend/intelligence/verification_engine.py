from dataclasses import dataclass

from nova_backend.intelligence.request_classifier import ClassificationResult
from nova_backend.intelligence.task_profiles import TaskProfile


@dataclass(frozen=True)
class VerificationReport:
    verification_score: int
    issues: tuple[str, ...]
    improved_response: str

    @property
    def quality_score(self) -> float:
        return self.verification_score / 100.0


class VerificationEngine:
    """Rule-based verification that never calls a second model pass."""

    SECOND_PASS_ALLOWED_TYPES = {"architecture", "code_review", "debugging"}

    def verify(
        self,
        response: str,
        classification: ClassificationResult,
        profile: TaskProfile,
    ) -> VerificationReport:
        cleaned = response.strip()
        issues: list[str] = []

        if not cleaned:
            issues.append("empty_response")
            cleaned = "I need a little more information to answer that well."

        lowered = cleaned.lower()
        word_count = len(cleaned.split())
        if any(phrase in lowered for phrase in ("as an ai language model", "i cannot assist with anything")):
            issues.append("generic_ai_disclaimer")
            cleaned = self._remove_generic_disclaimers(cleaned)

        self._check_completeness(cleaned, lowered, word_count, classification, issues)
        self._check_contradictions(lowered, issues)
        self._check_missing_code_blocks(cleaned, classification, issues)
        self._check_missing_explanations(lowered, classification, issues)
        self._check_missing_edge_cases(lowered, classification, profile, issues)

        score = self._score(cleaned, issues, classification, profile)
        return VerificationReport(
            verification_score=score,
            issues=tuple(issues),
            improved_response=cleaned,
        )

    def allows_second_model_pass(self, classification: ClassificationResult) -> bool:
        if classification.depth != "deep":
            return False
        return classification.request_type in self.SECOND_PASS_ALLOWED_TYPES or classification.request_type == "coding"

    @staticmethod
    def _remove_generic_disclaimers(response: str) -> str:
        replacements = (
            "As an AI language model, ",
            "As a language model, ",
            "As an AI, ",
        )
        cleaned = response
        for phrase in replacements:
            cleaned = cleaned.replace(phrase, "")
        return cleaned.strip()

    @staticmethod
    def _check_completeness(
        response: str,
        lowered: str,
        word_count: int,
        classification: ClassificationResult,
        issues: list[str],
    ) -> None:
        if classification.request_type == "conversation":
            return
        minimum_words = 25 if classification.depth == "shallow" else 70 if classification.depth == "medium" else 120
        if word_count < minimum_words:
            issues.append("possibly_incomplete")
        if classification.request_type == "debugging":
            required = ("symptom", "cause", "fix")
            if not any(word in lowered for word in ("symptom", "error", "failing", "failure")):
                issues.append("debugging_missing_symptoms")
            if not all(word in lowered for word in required[1:]):
                issues.append("debugging_missing_cause_or_fix")
        if classification.request_type == "code_review":
            if "finding" not in lowered and "issue" not in lowered and "bug" not in lowered:
                issues.append("review_missing_findings")
        if classification.request_type == "decision_making":
            if not any(word in lowered for word in ("recommend", "choose", "option", "tradeoff")):
                issues.append("decision_missing_recommendation_or_tradeoffs")

    @staticmethod
    def _check_contradictions(lowered: str, issues: list[str]) -> None:
        contradiction_pairs = (
            ("always", "never"),
            ("must", "must not"),
            ("safe", "unsafe"),
            ("supported", "unsupported"),
            ("available", "unavailable"),
        )
        for left, right in contradiction_pairs:
            if left in lowered and right in lowered:
                issues.append(f"possible_contradiction_{left}_{right}".replace(" ", "_"))

    @staticmethod
    def _check_missing_code_blocks(
        response: str,
        classification: ClassificationResult,
        issues: list[str],
    ) -> None:
        if classification.request_type in {"coding", "game_development"} and classification.depth != "shallow":
            if "```" not in response:
                issues.append("missing_code_block")

    @staticmethod
    def _check_missing_explanations(
        lowered: str,
        classification: ClassificationResult,
        issues: list[str],
    ) -> None:
        explanation_types = {
            "debugging",
            "architecture",
            "mathematics",
            "coding",
            "code_review",
            "project_analysis",
            "decision_making",
        }
        if classification.request_type not in explanation_types:
            return
        if not any(word in lowered for word in ("because", "why", "reason", "tradeoff", "root cause", "works by")):
            issues.append("missing_explanation")

    @staticmethod
    def _check_missing_edge_cases(
        lowered: str,
        classification: ClassificationResult,
        profile: TaskProfile,
        issues: list[str],
    ) -> None:
        needs_edge_cases = classification.request_type in {
            "coding",
            "debugging",
            "architecture",
            "game_development",
            "project_analysis",
        } or "edge cases" in profile.quality_focus
        if not needs_edge_cases:
            return
        if not any(term in lowered for term in ("edge case", "edge cases", "failure mode", "risk", "fallback", "invalid")):
            issues.append("missing_edge_cases")

    @staticmethod
    def _score(
        response: str,
        issues: list[str],
        classification: ClassificationResult,
        profile: TaskProfile,
    ) -> int:
        score = 96
        issue_weights = {
            "empty_response": 70,
            "missing_code_block": 18,
            "possibly_incomplete": 14,
            "missing_explanation": 12,
            "missing_edge_cases": 10,
            "debugging_missing_cause_or_fix": 16,
            "review_missing_findings": 18,
        }
        for issue in issues:
            score -= issue_weights.get(issue, 8 if issue.startswith("possible_contradiction") else 7)
        if classification.confidence < 0.6:
            score -= 5
        if len(response.split()) < 12 and classification.request_type not in {"conversation", "knowledge"}:
            score -= 8
        if profile.name in {"coding", "debugging", "architecture", "game_development", "project_analysis"} and classification.depth == "deep":
            if len(response.split()) < 120:
                score -= 12
        return max(0, min(score, 100))
