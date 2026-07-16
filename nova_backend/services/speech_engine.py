import asyncio
import os
import re
import shutil
import subprocess
import tempfile

from config import config
from nova_backend.logging_config import get_logger

try:
    from elevenlabs import VoiceSettings
    from elevenlabs.client import ElevenLabs
    ELEVENLABS_AVAILABLE = True
except ImportError:
    ELEVENLABS_AVAILABLE = False

logger = get_logger(__name__)


class LocalSpeechEngine:
    """Low-latency local speech queue using authentic macOS voices matching the frontend identity packs."""

    def __init__(self, voice: str = "Allison", rate: int = 152) -> None:
        self.voice = voice
        self.rate = rate
        self.available = shutil.which("say") is not None
        self.elevenlabs_voice_id = os.getenv("ELEVENLABS_VOICE_ID", "EXAVITQu4vr4xnSDxMaL")
        self.elevenlabs_model_id = os.getenv("ELEVENLABS_MODEL_ID", "eleven_monolingual_v1")
        self._elevenlabs_client = None
        self._processes: dict[str, subprocess.Popen] = {}

    def set_personality(self, personality: str, speed_multiplier: float = 1.0) -> None:
        """
        Dynamically adjusts the macOS say voice and speed matching the frontend selection.
        - jarvis: Deep male voice Rishi, rate ~150
        - friday: Calm female voice selected for warmth and realism, rate ~152
        - tactical: Direct scifi voice Rocko, rate ~175
        - neutral: Minimal futuristic voice Reed, rate ~160
        """
        if personality == "jarvis":
            self.voice = self._select_best_macos_female_voice()
            self.rate = int(152 * speed_multiplier)
        elif personality == "friday":
            self.voice = self._select_best_macos_female_voice()
            self.rate = int(152 * speed_multiplier)
        elif personality == "tactical":
            self.voice = "Rocko"
            self.rate = int(175 * speed_multiplier)
        else:  # neutral
            self.voice = self._select_best_macos_female_voice()
            self.rate = int(152 * speed_multiplier)
        logger.info("Local speech engine configured: voice=%s, rate=%d", self.voice, self.rate)

    def _select_best_macos_female_voice(self) -> str:
        voices = self._available_macos_voices()
        if not voices:
            return "Samantha"
        ranked = sorted(voices, key=lambda item: item[1], reverse=True)
        for name, score, lang in ranked[:12]:
            logger.info("[VOICE CANDIDATE] name=%s lang=%s score=%s", name, lang, score)
        selected = ranked[0]
        logger.info("[VOICE SELECTED] %s", selected[0])
        logger.info("[VOICE QUALITY SCORE] %s reason=highest_ranked_reliable_warm_local_voice", selected[1])
        return selected[0]

    def _available_macos_voices(self) -> list[tuple[str, int, str]]:
        try:
            res = subprocess.run(["say", "-v", "?"], capture_output=True, text=True, timeout=1.0)
        except Exception:
            return []
        voices: list[tuple[str, int, str]] = []
        for line in res.stdout.splitlines():
            match = re.match(r"^(.+?)\s+([a-zA-Z_]+)\s+#", line)
            if not match:
                continue
            name = match.group(1).strip()
            lang = match.group(2).strip()
            voices.append((name, self._voice_quality_score(name, lang), lang))
        return voices

    @staticmethod
    def _voice_quality_score(name: str, lang: str) -> int:
        n = name.lower()
        l = lang.lower().replace("_", "-")
        score = 0
        if l.startswith("en"):
            score += 20
        if l in {"en-us", "en-gb", "en-in", "en-au", "en-ie", "en-za"}:
            score += 8
        if "enhanced" in n:
            score += 12
        if re.search(r"siri|premium|enhanced|neural|natural", n):
            score += 30
        if "allison" in n:
            score += 24
        if re.search(r"ava|zoe|susan|victoria|karen|moira|tessa|serena|veena|fiona|kate|sandy|shelley", n):
            score += 20
        if "samantha" in n:
            score += 12
        if re.search(r"compact|bells|boing|bubbles|cellos|zarvox|trinoids|bad news|good news|pipe organ|superstar|wobble|bahh|jester", n):
            score -= 45
        if re.search(r"alex|daniel|david|fred|mark|tom|rishi|rocko|reed|aaron", n):
            score -= 20
        return score

    async def speak_text(self, session_id: str, text: str) -> None:
        cleaned = self.clean_for_voice(text)
        if not cleaned:
            return
        # Explicitly stop and fully wait for any active speech process in this session to clear completely.
        # This guarantees that replacement speech waits until prior cancellation completes.
        await self.stop(session_id)
        if await asyncio.to_thread(self._speak_with_elevenlabs, session_id, cleaned):
            logger.info("[VOICE PROVIDER] elevenlabs")
            return
        if self.available:
            logger.info("[VOICE PROVIDER] macos_say voice=%s rate=%d", self.voice, self.rate)
            await self._speak_with_macos(session_id, cleaned)

    async def stop(self, session_id: str) -> None:
        process = self._processes.pop(session_id, None)
        if process and process.poll() is None:
            logger.info("[SPEECH ENGINE] Actively terminating speech process for session %s", session_id)
            process.terminate()
            try:
                # Synchronously wait for the process to die to prevent audio overlapping
                await asyncio.to_thread(process.wait, timeout=0.5)
            except subprocess.TimeoutExpired:
                logger.warn("[SPEECH ENGINE] Process did not exit; killing it.")
                try:
                    process.kill()
                    await asyncio.to_thread(process.wait)
                except Exception:
                    pass
            except Exception:
                pass

    async def stop_all(self) -> None:
        for session_id in list(self._processes):
            await self.stop(session_id)

    def clean_for_voice(self, text: str) -> str:
        """
        Applies comprehensive speech cleaning matching client-side store normalizations.
        Corrects title pronunciations, strips Markdown/LaTeX structures, and converts mathematical symbols.
        """
        # Pronunciation normalizations
        text = re.sub(r"\bMr\.\s*", "Mister ", text, flags=re.IGNORECASE)
        text = re.sub(r"\bMr\b", "Mister", text, flags=re.IGNORECASE)
        text = re.sub(r"\bMrs\.\s*", "Misses ", text, flags=re.IGNORECASE)
        text = re.sub(r"\bMrs\b", "Misses", text, flags=re.IGNORECASE)

        # LaTeX header cleanup
        text = re.sub(r"###\s*(Problem|Steps|Simplification|Final Answer)", "", text, flags=re.IGNORECASE)
        text = text.replace(r"\color{orange}", "")
        text = re.sub(r"\\boxed\{([\s\S]*?)\}", r"\1", text)
        text = text.replace(r"\int", "integral of ")
        text = text.replace(r"\times", " times ")
        text = text.replace(r"\cdot", " times ")
        text = re.sub(r"\\frac\{([\s\S]*?)\}\{([\s\S]*?)\}", r"\1 divided by \2", text)
        text = text.replace("$$", "").replace("$", "")

        # General markdown and code cleanups
        text = re.sub(r"```[\s\S]*?```", "code block", text)
        text = re.sub(r"`([^`]+)`", r"\1", text)
        text = re.sub(r"\[\d+(?:,\s*\d+)*\]", "", text)
        text = re.sub(r"\*\*(.*?)\*\*", r"\1", text)
        text = re.sub(r"\*(.*?)\*", r"\1", text)
        text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)

        # Mathematical operations mapping without turning hyphenated words into arithmetic.
        text = re.sub(r"(?<=\d)\s*\+\s*(?=\d)", " plus ", text)
        text = re.sub(r"(?<=\d)\s*-\s*(?=\d)", " minus ", text)
        text = re.sub(r"(^|\s)-(\d+)", r"\1minus \2", text)
        text = re.sub(r"(^|\s)-\s+", r"\1", text)
        text = re.sub(r"(?<=\d)\s*\*\s*(?=\d)", " times ", text)
        text = re.sub(r"(?<=\d)\s*/\s*(?=\d)", " divided by ", text)
        text = re.sub(r"([A-Za-z])-([A-Za-z])", r"\1 \2", text)
        text = text.replace("^2", " squared ")
        text = text.replace("^3", " cubed ")
        text = re.sub(r"\^([a-zA-Z0-9]+)", r" to the power of \1", text)
        text = text.replace("=", " equals ")

        # Clean LaTeX brackets and leftover slashes
        text = text.replace("\\", "")
        text = re.sub(r"[{}]", " ", text)

        # Normalize whitespace
        text = re.sub(r"\s+", " ", text).strip()
        return text

    def _speak_with_elevenlabs(self, session_id: str, text: str) -> bool:
        if not config.elevenlabs_api_key or not ELEVENLABS_AVAILABLE or shutil.which("afplay") is None:
            return False
        try:
            if self._elevenlabs_client is None:
                self._elevenlabs_client = ElevenLabs(api_key=config.elevenlabs_api_key)
            audio = self._elevenlabs_client.text_to_speech.convert(
                text=text,
                voice_id=self.elevenlabs_voice_id,
                model_id=self.elevenlabs_model_id,
                voice_settings=VoiceSettings(
                    stability=0.68,
                    similarity_boost=0.82,
                )
            )
            with tempfile.NamedTemporaryFile(prefix="nova_voice_", suffix=".mp3", delete=False) as f:
                audio_path = f.name
                for chunk in audio:
                    if chunk:
                        f.write(chunk)
            
            # Spawn afplay via Popen so that it can be actively tracked and terminated on interruption!
            process = subprocess.Popen(
                ["afplay", audio_path],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            self._processes[session_id] = process
            
            try:
                process.wait()
            finally:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=0.1)
                    except Exception:
                        process.kill()
                if self._processes.get(session_id) is process:
                    self._processes.pop(session_id, None)
                try:
                    os.unlink(audio_path)
                except OSError:
                    pass
            return True
        except Exception:
            logger.exception("ElevenLabs speech failed; falling back to macOS voice.")
            return False

    async def _speak_with_macos(self, session_id: str, text: str) -> None:
        process = subprocess.Popen(
            ["say", "-v", self.voice, "-r", str(self.rate), text],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self._processes[session_id] = process
        try:
            await asyncio.to_thread(process.wait)
        finally:
            # Active termination check: if speak_text is cancelled, make sure the say process is killed instantly!
            if process.poll() is None:
                logger.info("[SPEECH ENGINE] Cancelling active macOS say process due to cancellation/interruption.")
                process.terminate()
                try:
                    process.wait(timeout=0.1)
                except Exception:
                    process.kill()
            if self._processes.get(session_id) is process:
                self._processes.pop(session_id, None)


speech_engine = LocalSpeechEngine()
