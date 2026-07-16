from dataclasses import dataclass
from pathlib import Path
import re


@dataclass(frozen=True)
class ProjectFileContext:
    path: str
    relevance_score: int
    excerpt: str


@dataclass(frozen=True)
class ProjectContext:
    active: bool
    query: str
    files: tuple[ProjectFileContext, ...]

    @property
    def rendered(self) -> str:
        if not self.files:
            return ""
        sections = [
            "Project Intelligence Mode active. Use these project files as source of truth."
        ]
        for file_context in self.files:
            sections.append(
                f"File: {file_context.path}\n"
                f"Relevance: {file_context.relevance_score}\n"
                f"{file_context.excerpt}"
            )
        return "\n\n".join(sections)


class ProjectIntelligence:
    """Bounded local project reader for project-aware answers."""

    PROJECT_MARKERS = (
        "this project",
        "our code",
        "nova",
        "codebase",
        "backend",
        "architecture",
        "implementation",
    )
    ALLOWED_SUFFIXES = {
        ".py",
        ".ts",
        ".tsx",
        ".js",
        ".jsx",
        ".md",
        ".json",
        ".toml",
        ".yaml",
        ".yml",
    }
    SKIP_PARTS = {
        ".git",
        "__pycache__",
        "node_modules",
        ".next",
        "dist",
        "build",
        ".venv",
        "venv",
    }

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()

    def should_activate(self, message: str) -> bool:
        text = message.lower()
        return any(marker in text for marker in self.PROJECT_MARKERS)

    def build_context(
        self,
        message: str,
        max_files: int = 6,
        max_chars_per_file: int = 1800,
        max_total_chars: int = 7200,
    ) -> ProjectContext:
        if not self.should_activate(message):
            return ProjectContext(False, message, ())

        query_terms = self._terms(message)
        scored: list[tuple[int, Path]] = []
        for path in self._iter_candidate_files():
            score = self._score_path(path, query_terms)
            if score <= 0:
                continue
            scored.append((score, path))

        scored.sort(key=lambda row: (row[0], -len(row[1].parts)), reverse=True)
        files: list[ProjectFileContext] = []
        remaining_chars = max_total_chars
        for score, path in scored[: max_files * 2]:
            if len(files) >= max_files or remaining_chars <= 0:
                break
            excerpt = self._read_relevant_excerpt(path, query_terms, min(max_chars_per_file, remaining_chars))
            if not excerpt:
                continue
            files.append(
                ProjectFileContext(
                    path=str(path.relative_to(self.root)),
                    relevance_score=score,
                    excerpt=excerpt,
                )
            )
            remaining_chars -= len(excerpt)

        return ProjectContext(True, message, tuple(files))

    def _iter_candidate_files(self):
        if not self.root.exists():
            return
        for path in self.root.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix.lower() not in self.ALLOWED_SUFFIXES:
                continue
            if any(part in self.SKIP_PARTS for part in path.parts):
                continue
            if path.name.endswith(".tsbuildinfo") or path.name in {"package-lock.json"}:
                continue
            yield path

    def _score_path(self, path: Path, query_terms: set[str]) -> int:
        rel = str(path.relative_to(self.root)).lower()
        score = 0
        for term in query_terms:
            if term in rel:
                score += 5
        priority_terms = {
            "assistant": ("assistant_service", "response_modes"),
            "provider": ("provider_manager", "provider_router", "openai_provider", "ollama_provider"),
            "memory": ("memory", "sessions"),
            "verification": ("verification",),
            "reasoning": ("reasoning", "classifier", "task_profiles"),
            "architecture": ("architecture", "provider", "runtime", "service"),
            "backend": ("nova_backend",),
            "nova": ("nova_backend", "friday", "docs"),
        }
        for term, markers in priority_terms.items():
            if term in query_terms and any(marker in rel for marker in markers):
                score += 10
        if "nova_backend/intelligence" in rel:
            score += 6
        if rel.startswith("docs/") and {"architecture", "project", "nova"}.intersection(query_terms):
            score += 4
        return score

    def _read_relevant_excerpt(self, path: Path, query_terms: set[str], max_chars: int) -> str:
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return ""
        if len(text) <= max_chars:
            return text.strip()

        lines = text.splitlines()
        hits: list[int] = []
        lowered_terms = {term.lower() for term in query_terms}
        for index, line in enumerate(lines):
            lowered = line.lower()
            if any(term in lowered for term in lowered_terms):
                hits.append(index)

        if not hits:
            return text[:max_chars].strip()

        chunks: list[str] = []
        used: set[int] = set()
        for hit in hits[:8]:
            start = max(0, hit - 8)
            end = min(len(lines), hit + 16)
            for line_no in range(start, end):
                if line_no in used:
                    continue
                used.add(line_no)
                chunks.append(f"{line_no + 1}: {lines[line_no]}")
            chunks.append("...")
            if sum(len(chunk) for chunk in chunks) >= max_chars:
                break
        return "\n".join(chunks)[:max_chars].strip()

    @staticmethod
    def _terms(text: str) -> set[str]:
        words = re.findall(r"[a-zA-Z][a-zA-Z0-9_+-]{2,}", text.lower())
        stopwords = {
            "the",
            "and",
            "for",
            "that",
            "with",
            "what",
            "when",
            "where",
            "this",
            "our",
            "code",
            "project",
        }
        return {word for word in words if word not in stopwords}
