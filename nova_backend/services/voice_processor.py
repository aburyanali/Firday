import base64
import math
import struct
from collections import deque
from typing import Dict, Any, Optional
from nova_backend.logging_config import get_logger

logger = get_logger(__name__)

class VoiceProcessor:
    """
    Scaffold for real-time speech and duplex voice processing in NOVA OS.
    Handles:
    - Safe base64 audio chunk ingestion
    - Energy calculation for simulated Voice Activity Detection (VAD)
    - Active speech and interruption state management
    - Developer diagnostics for latency and buffer quality
    """
    def __init__(self, energy_threshold: float = 0.08, speech_history_size: int = 15):
        self.energy_threshold = energy_threshold
        # Rolling queue of recent audio frame energies to smooth VAD detection
        self.energy_history = deque(maxlen=speech_history_size)
        self.is_user_speaking = False
        self.silence_frames_count = 0
        self.speech_frames_count = 0
        
    def ingest_audio_frame(self, base64_audio: str) -> Dict[str, Any]:
        """
        Ingests a base64 encoded audio slice from the client websocket.
        Calculates frame energy, checks for active speech, and tracks rolling average.
        """
        if not base64_audio:
            return {"active": False, "energy": 0.0, "interrupted": False}

        try:
            # Safely decode base64 audio data
            raw_bytes = base64.b64decode(base64_audio)
            frame_len = len(raw_bytes)
            
            # Compute a realistic or simulated root-mean-square (RMS) energy level.
            # If the user is sending real mic audio, calculate genuine amplitude.
            energy = 0.0
            if frame_len >= 2:
                # Try to read PCM 16-bit mono frames if possible
                try:
                    samples_count = frame_len // 2
                    format_str = f"<{samples_count}h"
                    samples = struct.unpack(format_str, raw_bytes[:samples_count * 2])
                    if samples:
                        sum_squares = sum((s / 32768.0) ** 2 for s in samples)
                        energy = math.sqrt(sum_squares / len(samples))
                except Exception:
                    # Fallback to general byte level metrics if format varies (e.g. WebM chunks)
                    sum_squares = sum((b / 255.0 - 0.5) ** 2 for b in raw_bytes)
                    energy = math.sqrt(sum_squares / frame_len) if frame_len > 0 else 0.0
            
            self.energy_history.append(energy)
            
            # Simple VAD logic
            avg_energy = sum(self.energy_history) / len(self.energy_history) if self.energy_history else 0.0
            was_speaking = self.is_user_speaking
            
            if avg_energy > self.energy_threshold:
                self.speech_frames_count += 1
                self.silence_frames_count = 0
                if self.speech_frames_count >= 3:  # Require a brief build-up to avoid clicks triggering VAD
                    self.is_user_speaking = True
            else:
                self.silence_frames_count += 1
                self.speech_frames_count = 0
                if self.silence_frames_count >= 8:  # Require a brief pause to confirm silence
                    self.is_user_speaking = False
                    
            state_changed = was_speaking != self.is_user_speaking
            
            # Interruption indicator: User suddenly starts speaking loud
            interrupted = self.is_user_speaking and avg_energy > (self.energy_threshold * 1.5)
            
            return {
                "frame_bytes": frame_len,
                "energy": round(energy, 4),
                "avg_energy": round(avg_energy, 4),
                "user_speaking": self.is_user_speaking,
                "state_changed": state_changed,
                "interrupted": interrupted
            }
            
        except Exception as e:
            logger.exception("Failed to ingest voice audio frame.")
            return {"active": False, "energy": 0.0, "interrupted": False, "error": str(e)}
            
    def reset(self):
        """Reset the internal VAD queues and states."""
        self.energy_history.clear()
        self.is_user_speaking = False
        self.silence_frames_count = 0
        self.speech_frames_count = 0

voice_processor = VoiceProcessor()
