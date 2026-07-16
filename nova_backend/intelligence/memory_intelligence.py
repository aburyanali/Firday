from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha1
import re
from typing import Iterable


@dataclass(frozen=True)
class MemoryContext:
    relevant_context: str
    summary: str
    stored_fact: str | None = None


@dataclass
class MemoryFact:
    id: str
    content: str
    timestamp: datetime
    relevance_score: float
    category: str
    access_count: int
    last_accessed: datetime

    def effective_score(self, now: datetime | None = None) -> float:
        now = now or _utcnow()
        age_days = max(0.0, (now - self.timestamp).total_seconds() / 86400)
        aging_penalty = min(30.0, age_days * 0.15)
        return self.current_relevance(now) - aging_penalty

    def current_relevance(self, now: datetime | None = None) -> float:
        now = now or _utcnow()
        score = self.relevance_score
        if self.access_count >= 3:
            score += 10
        hours_since_access = max(0.0, (now - self.last_accessed).total_seconds() / 3600)
        if hours_since_access <= 72:
            score += 10
        return score


@dataclass(frozen=True)
class FactCandidate:
    content: str
    category: str
    relevance_score: float


class MemoryIntelligence:
    """Active-response memory layer with strict prompt-bloat controls."""

    MAX_SESSION_FACTS = 50
    MAX_GLOBAL_FACTS = 200
    MAX_MEMORY_CONTEXT_CHARS = 2000

    CATEGORY_SCORES = {
        "user_preference": 40.0,
        "project_preference": 35.0,
        "recurring_goal": 38.0,
        "long_term_context": 25.0,
        "technical_context": 20.0,
    }

    TRANSIENT_RELEVANCE = -100.0

    IMPORTANT_FACT_PATTERNS = (
        re.compile(r"\bremember(?: that)? (?P<fact>.+)", re.I),
        re.compile(r"\bmy (?P<key>[a-z][a-z0-9 _-]{1,40}) is (?P<value>.+)", re.I),
        re.compile(r"\bi prefer (?P<fact>.+)", re.I),
        re.compile(r"\bcall me (?P<fact>.+)", re.I),
        re.compile(r"\bmy goal is (?P<fact>.+)", re.I),
        re.compile(r"\bi am building (?P<fact>.+)", re.I),
        re.compile(r"\b(?:for|in) (?P<project>nova|this project|our code|the codebase)[, ]+(?P<fact>.+)", re.I),
    )

    STOPWORDS = {
        "about", "after", "again", "also", "because", "before", "between", "could",
        "hello", "please", "should", "their", "there", "these", "thing", "those",
        "what", "when", "where", "which", "while", "would", "with", "your",
    }

    TRANSIENT_PATTERNS = (
        re.compile(r"^\s*(hi|hello|hey|yo|sup|thanks|thank you|ok|okay|yes|no|sure|got it)[.!?\s]*$", re.I),
        re.compile(r"^\s*(what is|what's|calculate|solve)\s+[-+*/().\d\s]+\??\s*$", re.I),
        re.compile(r"\b(can you|please)\s+(summarize|explain|fix|debug|review|write|implement|create)\b", re.I),
        re.compile(r"\b(traceback|exception|syntaxerror|typeerror|temporary|for now|just this once)\b", re.I),
    )

    def __init__(self) -> None:
        self.global_facts: list[MemoryFact] = []
        self.last_evicted_facts: list[MemoryFact] = []
        self.last_rejected_memory: str | None = None

    def build_context(self, message: str, session: object | None) -> MemoryContext:
        stored_fact = self._store_important_fact(message, session)
        messages = list(getattr(session, "messages", []) or [])
        relevant = self._select_relevant_messages(message, messages)
        relevant_facts = self._retrieve_relevant_facts(message, session)
        summary = self._summarize_messages(messages)
        parts: list[str] = []

        if summary:
            parts.append(f"Conversation summary: {summary}")
        if relevant_facts:
            parts.append("Relevant long-term memory:\n" + "\n".join(relevant_facts))
        if relevant:
            parts.append("Relevant recent context:\n" + "\n".join(relevant))
        if stored_fact:
            parts.append(f"Newly stored user fact: {stored_fact}")

        return MemoryContext(
            relevant_context="\n\n".join(parts)[: self.MAX_MEMORY_CONTEXT_CHARS],
            summary=summary,
            stored_fact=stored_fact,
        )

    def _store_important_fact(self, message: str, session: object | None) -> str | None:
        if session is None:
            return None
        candidate = self._candidate_from_message(message)
        if candidate is None:
            self.last_rejected_memory = message.strip()
            return None
        if candidate.relevance_score < 0:
            self.last_rejected_memory = candidate.content
            return None

        fact = self._make_fact(candidate)
        session_facts = self._session_facts(session)
        self._upsert_fact(session_facts, fact)
        self._upsert_fact(self.global_facts, fact)
        self.last_evicted_facts = []
        self.last_evicted_facts.extend(self._evict(session_facts, self.MAX_SESSION_FACTS))
        self.last_evicted_facts.extend(self._evict(self.global_facts, self.MAX_GLOBAL_FACTS))
        return f"{fact.category}: {fact.content}"
        return None

    def _candidate_from_message(self, message: str) -> FactCandidate | None:
        text = " ".join(message.strip().split())
        if not text:
            return None
        if self._is_transient(text):
            return FactCandidate(text, "transient", self.TRANSIENT_RELEVANCE)

        lowered = text.lower()
        category: str | None = None
        content = text.rstrip(".")

        if re.search(r"\bi prefer\b|\bmy preference\b|\bcall me\b", lowered):
            category = "user_preference"
        elif re.search(r"\b(nova|this project|our code|codebase|backend)\b", lowered) and re.search(
            r"\b(prefer|use|should|standard|convention|architecture|provider|runtime|memory)\b", lowered
        ):
            category = "project_preference"
        elif re.search(r"\b(my goal is|i want to become|i am becoming|long[- ]term goal|recurring goal)\b", lowered):
            category = "recurring_goal"
        elif re.search(r"\b(i am building|i'm building|i work on|i am working on|my project is)\b", lowered):
            category = "long_term_context"
        elif re.search(r"\b(backend uses|frontend uses|provider|runtime|websocket|api route|database|model routing)\b", lowered):
            category = "technical_context"

        for pattern in self.IMPORTANT_FACT_PATTERNS:
            match = pattern.search(text)
            if not match:
                continue
            groups = match.groupdict()
            if groups.get("key") and groups.get("value"):
                content = f"{groups['key'].strip()} is {groups['value'].strip()}".rstrip(".")
                category = category or "long_term_context"
            elif groups.get("project") and groups.get("fact"):
                content = f"{groups['project'].strip()}: {groups['fact'].strip()}".rstrip(".")
                category = category or "project_preference"
            elif groups.get("fact"):
                content = groups["fact"].strip().rstrip(".")
                category = category or self._category_for_fact(content)
            break

        if category is None:
            return None
        return FactCandidate(content[:500], category, self.CATEGORY_SCORES[category])

    def _select_relevant_messages(self, message: str, messages: Iterable[dict[str, str]]) -> list[str]:
        query_terms = self._terms(message)
        if not query_terms:
            return []

        scored: list[tuple[int, str]] = []
        for item in messages:
            role = item.get("role", "user")
            content = item.get("content", "")
            terms = self._terms(content)
            overlap = len(query_terms.intersection(terms))
            if overlap <= 0:
                continue
            label = "User" if role == "user" else "NOVA"
            scored.append((overlap, f"{label}: {content[:500]}"))

        scored.sort(key=lambda row: row[0], reverse=True)
        return [line for _, line in scored[:4]]

    def _retrieve_relevant_facts(self, message: str, session: object | None) -> list[str]:
        query_terms = self._terms(message)
        if not query_terms:
            return []
        facts = list(self.global_facts)
        if session is not None:
            facts.extend(self._session_facts(session))

        deduped: dict[str, MemoryFact] = {}
        for fact in facts:
            deduped[fact.id] = fact

        now = _utcnow()
        scored: list[tuple[float, MemoryFact]] = []
        for fact in deduped.values():
            fact_terms = self._terms(fact.content)
            overlap = len(query_terms.intersection(fact_terms))
            if overlap <= 0:
                continue
            score = fact.effective_score(now) + (overlap * 8)
            scored.append((score, fact))

        scored.sort(key=lambda row: (row[0], row[1].last_accessed), reverse=True)
        rendered: list[str] = []
        total_chars = 0
        for _, fact in scored:
            line = f"- [{fact.category}] {fact.content}"
            if total_chars + len(line) > self.MAX_MEMORY_CONTEXT_CHARS:
                break
            fact.access_count += 1
            fact.last_accessed = now
            rendered.append(line)
            total_chars += len(line)
            if len(rendered) >= 8:
                break
        return rendered

    def _summarize_messages(self, messages: list[dict[str, str]]) -> str:
        if len(messages) < 8:
            return ""

        older = messages[:-6]
        user_topics: list[str] = []
        for item in older[-10:]:
            if item.get("role") != "user":
                continue
            topic = " ".join(sorted(self._terms(item.get("content", "")))[:5])
            if topic and topic not in user_topics:
                user_topics.append(topic)

        if not user_topics:
            return ""
        summary = "; ".join(user_topics[-4:])
        return summary[:500]

    def _terms(self, text: str) -> set[str]:
        words = re.findall(r"[a-zA-Z][a-zA-Z0-9_+-]{2,}", text.lower())
        return {word for word in words if word not in self.STOPWORDS}

    def _session_facts(self, session: object) -> list[MemoryFact]:
        facts = getattr(session, "intelligence_facts", None)
        if not isinstance(facts, list):
            facts = []
            setattr(session, "intelligence_facts", facts)
        return facts

    def _upsert_fact(self, facts: list[MemoryFact], fact: MemoryFact) -> None:
        for existing in facts:
            if existing.id == fact.id:
                existing.content = fact.content
                existing.category = fact.category
                existing.relevance_score = max(existing.relevance_score, fact.relevance_score)
                existing.last_accessed = _utcnow()
                existing.access_count += 1
                return
        facts.append(fact)

    @staticmethod
    def _evict(facts: list[MemoryFact], limit: int) -> list[MemoryFact]:
        evicted: list[MemoryFact] = []
        while len(facts) > limit:
            now = _utcnow()
            victim = min(facts, key=lambda fact: (fact.effective_score(now), fact.timestamp))
            facts.remove(victim)
            evicted.append(victim)
        return evicted

    def _make_fact(self, candidate: FactCandidate) -> MemoryFact:
        now = _utcnow()
        content = candidate.content.strip()
        fact_id = sha1(f"{candidate.category}:{content.lower()}".encode("utf-8")).hexdigest()[:16]
        return MemoryFact(
            id=fact_id,
            content=content,
            timestamp=now,
            relevance_score=candidate.relevance_score,
            category=candidate.category,
            access_count=0,
            last_accessed=now,
        )

    def _is_transient(self, text: str) -> bool:
        lowered = text.lower()
        durable_markers = (
            "remember",
            "my goal is",
            "i prefer",
            "my preference",
            "call me",
            "i am building",
            "i'm building",
            "my project is",
        )
        if text.strip().endswith("?") and not any(marker in lowered for marker in durable_markers):
            return True
        if lowered.startswith(("can you ", "could you ", "would you ", "please ", "how do ", "how does ", "how should ", "what is ", "what are ")):
            if not any(marker in lowered for marker in durable_markers):
                return True
        if len(lowered.split()) <= 2 and not any(word in lowered for word in ("prefer", "goal", "building", "nova")):
            return True
        return any(pattern.search(text) for pattern in self.TRANSIENT_PATTERNS)

    def _category_for_fact(self, fact: str) -> str:
        lowered = fact.lower()
        if "prefer" in lowered or "call me" in lowered:
            return "user_preference"
        if any(word in lowered for word in ("nova", "project", "codebase", "backend")):
            return "project_preference"
        if "goal" in lowered or "become" in lowered:
            return "recurring_goal"
        if any(word in lowered for word in ("provider", "runtime", "websocket", "api", "database")):
            return "technical_context"
        return "long_term_context"

    @staticmethod
    def _clean_fact_key(key: str) -> str:
        return re.sub(r"[^a-z0-9_-]+", "_", key.lower()).strip("_")[:48] or "note"

    @staticmethod
    def _fact_key_from_text(fact: str) -> str:
        match = re.match(r"(?:my )?([a-z][a-z0-9 _-]{1,40})\s+(?:is|=)\s+", fact.lower())
        if match:
            return match.group(1)
        return "preference" if "prefer" in fact.lower() else "note"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)
