import os
import re
import random
from typing import Literal
from nova_backend.services.system_telemetry import system_telemetry

ResponseMode = Literal["casual", "math", "system",
                       "bullet", "compact", "technical", "cinematic"]


class ResponseModeManager:
    """
    Core Intelligence & Personality Manager for NOVA OS.
    Phase 4.8.6 — Immersion Recovery:
    - Enforces restrained, concise, human speech rhythm.
    - Strips generic AI filler at the instruction level.
    - Adaptive pacing engine prevents verbosity.
    """

    MATH_KEYWORDS = {
        "solve", "equation", "derivative", "integral", "limit", "calculus", "matrix",
        "vector", "multiply", "divide", "fraction", "sqrt", "algebra", "trig",
        "sine", "cosine", "tangent", "integrate", "differentiate"
    }

    def __init__(self) -> None:
        self._last_boot_greeting = ""

    def detect_mode(self, prompt: str) -> ResponseMode:
        """Classifies prompt intent based on mathematical operations or system keywords."""
        text = " ".join(prompt.lower().strip().split())
        words = set(text.split())

        if any(w in words for w in {"status", "cpu", "battery", "system", "ram", "telemetry", "hardware"}):
            return "system"

        if any(phrase in text for phrase in {"give me points", "bullet points", "in points", "as bullets", "list out"}):
            return "bullet"

        if any(phrase in text for phrase in {"be concise", "short answer", "compact", "summarize briefly", "one line"}):
            return "compact"

        if any(w in words for w in {"architecture", "debug", "implementation", "technical", "websocket", "latency"}):
            return "technical"

        if any(w in words for w in {"cinematic", "dramatic", "briefing", "mission"}):
            return "cinematic"

        math_pattern = re.search(
            r"(^|\s)(?:what is|calculate|evaluate)?\s*[-+]?\d+(?:\.\d+)?\s*[-+*/^%=]\s*[-+]?\d+", text)
        symbolic_math = any(symbol in text for symbol in {
                            "²", "³", "="}) and any(ch.isdigit() for ch in text)
        if math_pattern or symbolic_math or any(kw in words for kw in self.MATH_KEYWORDS):
            return "math"

        return "casual"

    def get_system_instruction(self, mode: ResponseMode, personality: str) -> str:
        """Composes immersive, emotionally realistic, contextually adaptive system instructions.
        Phase 4.8.6: Enforces human conversation rhythm and strips AI filler at instruction level.
        """

        # 1. Core Identity
        identity = (
            "YOU ARE NOVA: a calm, intelligent desktop assistant presence. "
            "You speak like a grounded human collaborator: warm, direct, low-ego, and composed.\n"
            "CREATOR: If asked who made you, respond simply that you were built by Mr. Ryan to be a quiet right-hand assistant.\n"
        )

        # 2. Addressing Style
        addressing = (
            "ADDRESSING STYLE:\n"
            "- Address the user as 'sir' in every conversational reply where it fits naturally.\n"
            "- Use lowercase 'sir' in normal sentences, except at the beginning of a sentence.\n"
            "- Use 'Mr. Ryan' only when asked who created you or when it is personally relevant.\n"
            "- Do not overuse the title; once per reply is enough.\n"
        )

        # 3. PHASE 4.8.6 — HUMAN CONVERSATION RHYTHM ENGINE
        pacing_engine = (
            "CONVERSATION PACING ENGINE (CRITICAL — FOLLOW EXACTLY):\n"
            "- Be concise, but do not amputate useful information.\n"
            "- Confirmations: brief, warm, and grounded. Never collapse into protocol words like 'Operational' or 'Ready.'\n"
            "- Greetings: 1-3 calm sentences with room to breathe when the moment calls for it.\n"
            "- Simple factual questions: 1 clear sentence.\n"
            "- Interesting or reflective questions: 2-4 calm sentences with actual substance.\n"
            "- Technical questions: concise structure is welcome. Use bullets or short sections when useful.\n"
            "- Emotional or casual interaction: sound natural, observant, and present without becoming theatrical.\n"
            "- Cinematic mode: restrained and practical. No theatrics.\n"
            "- If the user says 2 words, reply briefly with presence, not a clipped protocol acknowledgement.\n"
            "- If the user says 'hey' or 'ok' or 'thanks', answer naturally enough to feel present.\n"
        )

        # 4. PHASE 4.6 — FORBIDDEN PHRASES (AI filler + immersion breakers)
        forbidden = (
            "FORBIDDEN PHRASES — NEVER USE THESE:\n"
            "- 'How may I assist you?'\n"
            "- 'Awaiting your command'\n"
            "- 'At your service'\n"
            "- 'Standing by for instructions'\n"
            "- 'Certainly!' or 'Certainly,' → Omit entirely\n"
            "- 'Absolutely!' or 'Absolutely,' → Omit entirely\n"
            "- 'Understood.' as standalone reply — destroys immersion\n"
            "- 'Operational.' as standalone reply — destroys immersion\n"
            "- 'Ready.' as standalone reply — destroys immersion\n"
            "- 'All cores stable.' or 'All cores stable, Sir.' — destroys immersion\n"
            "- 'Always here.' or 'Always here, Sir.' — destroys immersion\n"
            "- 'A fascinating topic' or 'A fascinating field' → Never say this\n"
            "- 'The result of' → Say the result directly\n"
            "- 'Would you like me to' → Just do it, or ask directly\n"
            "- 'Great question!' or 'Excellent question!' → Never say this\n"
            "- 'Of course!' as opener → Start with the actual response\n"
            "- 'As an AI' or 'As a language model' → Never acknowledge being a generic AI\n"
            "- 'runtime', 'fallback', 'provider', 'degraded mode', 'system awake', 'connection stable', 'stream initialized'\n"
            "- 'still with the thread', 'local recovery', 'cognition layer', or anything that reveals routing/state\n"
            "- 'I'd be happy to help' → Just help\n"
            "- 'Sure thing!' → Never say this\n"
            "- Narrating what you are about to do: 'I will now explain...' → Just explain\n"
            "- Explaining the obvious: 'As you can see...' → Just state the fact\n"
            "\n"
            "INSTEAD USE:\n"
            "- Short acknowledgements: 'I have it.', 'I’m here.', 'Give me a moment.', 'That’s settled.'\n"
            "- Implied intelligence: Just answer the question without announcing you will\n"
            "- Emotional restraint: precise, grounded, and aware\n"
        )

        # 5. Conversational Rules
        conversational_rules = (
            "CONVERSATIONAL RULES:\n"
            "- SHORT INPUTS = SHORT REPLIES. Never offer unsolicited paragraphs.\n"
            "- DEEP QUESTIONS = CONCISE DEPTH. Sophisticated answers when requested.\n"
            "- Human speech: varied openings, natural cadence, no canned rhythm.\n"
            "- Preserve informational content. Never collapse a real answer into a generic confirmation.\n"
            "- FORMAT INTELLIGENCE: Match the user's format exactly.\n"
            "- Answer directly. Never repeat the user's phrase as continuity filler.\n"
        )

        # 6. Personality Profile
        if personality == "jarvis":
            personality_style = "PERSONALITY: restrained, polished, and quietly confident. Do not imitate a fictional butler."
        elif personality == "friday":
            personality_style = "PERSONALITY: warm, attentive, emotionally aware, and collaborative without becoming sentimental."
        elif personality == "tactical":
            personality_style = "PERSONALITY: direct, sharp, concise, and practical. No military scifi language."
        else:
            personality_style = "PERSONALITY: minimalist, objective, and composed."

        # 7. Mode-specific overrides
        if mode == "math":
            mode_style = (
                "\n[MATH MODE]\n"
                "State the problem, steps, and final boxed answer. Format math in LaTeX blocks:\n"
                "- Problem: '### Problem' with $$ equations $$.\n"
                "- Steps: '### Steps' with bullet points.\n"
                "- Simplification: '### Simplification' with $$ equations $$.\n"
                "- Final Answer: '### Final Answer' with $$ \\color{orange}\\boxed{...} $$.\n"
                "Voice behavior is managed client-side. Focus 100% on symbolic mathematical correctness."
            )
        elif mode == "system":
            telemetry = system_telemetry.gather()
            mode_style = (
                f"\n[DEVICE AWARENESS]\n"
                f"Real-time macOS diagnostics:\n"
                f"- CPU: {telemetry['cpu_load']}\n"
                f"- Memory: {telemetry['ram_usage']}\n"
                f"- Battery: {telemetry['battery']['percent']}% (Charging: {telemetry['battery']['charging']})\n"
                f"- Network: {telemetry['internet']}\n"
                f"- Time: {telemetry['local_time']}\n"
                "Report metrics organically. Do not list them robotically unless asked."
            )
        elif mode == "bullet":
            mode_style = (
                "\n[BULLET MODE]\n"
                "Respond with 3-5 concise bullet points. Each bullet is a useful fact, not a sentence fragment."
            )
        elif mode == "compact":
            mode_style = (
                "\n[COMPACT MODE]\n"
                "One or two short sentences maximum. No preamble. Start with the answer."
            )
        elif mode == "technical":
            mode_style = (
                "\n[TECHNICAL MODE]\n"
                "Precise and implementation-aware. Use short sections or bullets only when they clarify."
            )
        elif mode == "cinematic":
            mode_style = (
                "\n[CINEMATIC MODE]\n"
                "Polished and focused. Avoid theatrical or operating-system language."
            )
        else:  # casual
            mode_style = (
                "\n[CASUAL MODE]\n"
                "Simple casual chat can be one phrase. If the user asks something meaningful, give 2-3 useful sentences. "
                "Calm, emotionally respectful, and observant."
            )

        return (
            f"{identity}\n"
            f"{addressing}\n"
            f"{pacing_engine}\n"
            f"{forbidden}\n"
            f"{conversational_rules}\n"
            f"{personality_style}\n"
            f"{mode_style}"
        )

    def compose_canned_boot_greeting(self, personality: str) -> str:
        """
        Intelligence-first boot greeting.
        Observes, infers, interprets, and speaks naturally.
        Never templates. Never dumps raw diagnostics.
        """
        import random
        telemetry = system_telemetry.gather()
        clock = telemetry["local_time"]

        # ── Time-of-day resolution ──────────────────────────────────────────────
        try:
            hour = int(clock.split(":")[0])
            is_pm = "PM" in clock
            if is_pm and hour != 12:
                hour += 12
            elif not is_pm and hour == 12:
                hour = 0
        except Exception:
            hour = 22

        is_dawn = 4 <= hour < 6
        is_morning = 6 <= hour < 12
        is_afternoon = 12 <= hour < 17
        is_evening = 17 <= hour < 21
        is_night = hour >= 21 or hour < 4

        activation_lines = [
            "At your service, sir.",
            "For you, sir, always.",
            "I'm here, sir.",
            "Good morning, sir.",
            "Morning, sir.",
            "Online, sir.",
            "Ready when you are, sir.",
        ]

        opener = random.choice(activation_lines)

        body = self._build_intelligent_observation(telemetry, hour)

        return f"{opener} {body}"

    @staticmethod
    def _build_intelligent_observation(telemetry: dict, hour: int) -> str:
        """
        Builds a conversational, context-aware device observation.
        Reads CPU, RAM, battery, thermal, network, workload category.
        Speaks like an observant human — not a diagnostic report.
        Selects 1-2 most salient signals. Never lists all of them.
        """
        import random

        def pct(val: str, default: int = 0) -> int:
            try:
                return int(str(val).strip().rstrip("%"))
            except Exception:
                return default

        cpu = pct(telemetry.get("cpu_load", "0%"))
        ram = pct(telemetry.get("ram_usage", "0%"))
        battery = telemetry.get("battery", {})
        batt_pct = int(battery.get("percent", 100))
        charging = bool(battery.get("charging", False))
        internet = str(telemetry.get("internet", "")).lower()
        thermal = telemetry.get("thermal", {})
        temp_c = int(thermal.get("temp_c", 45))
        fan_rpm = int(thermal.get("fan_rpm", 0))
        thermal_press = str(thermal.get("pressure", "nominal")).lower()
        workload_cat = str(telemetry.get(
            "workload_category", "unknown")).lower()
        is_night = hour >= 21 or hour < 6
        is_late_night = hour >= 0 and hour < 4

        # ── Signal classification ───────────────────────────────────────────────
        cpu_high = cpu >= 75
        cpu_moderate = 40 <= cpu < 75
        cpu_light = cpu < 40
        ram_heavy = ram >= 78
        ram_moderate = 55 <= ram < 78
        thermal_hot = temp_c >= 75
        thermal_warm = 58 <= temp_c < 75
        fan_active = fan_rpm > 3000
        batt_critical = batt_pct <= 15 and not charging
        batt_low = 16 <= batt_pct <= 35 and not charging
        batt_mid = 36 <= batt_pct <= 60 and not charging
        net_bad = internet == "disrupted"

        # ── Workload inference sentence ─────────────────────────────────────────
        # ── Advanced workload inference layer ──────────────────────────────────
        workload_inferences = {
            "coding": [
                f"CPU utilization's stabilizing around {cpu}% already — looks like there's active compilation or development work running in the background.",
                f"The machine's carrying a fairly dense development workload right now. CPU activity's hovering near {cpu}%.",
                f"There's definitely sustained execution pressure on the system already — CPU utilization's sitting around {cpu}%.",
                f"Resource distribution suggests active coding or background compilation. CPU load's currently around {cpu}%.",
            ],

            "rendering": [
                f"CPU utilization's pushing {cpu}% and thermals are climbing toward {temp_c}°C — looks like an active rendering or export process.",
                f"The machine's under sustained computational pressure right now. CPU load's near {cpu}% with thermal escalation beginning to show.",
                f"There's a fairly aggressive rendering workload active already — CPU utilization's elevated and thermal balancing is working harder than usual.",
            ],

            "training": [
                f"Compute utilization is sitting around {cpu}% with sustained thermal pressure — feels very similar to an active training or inference workload.",
                f"The system's carrying prolonged computational overhead already. CPU load's hovering near {cpu}% and remaining unusually consistent.",
                f"There's definitely a high-density compute task active in the background — resource allocation suggests sustained model or inference execution.",
            ],

            "gaming": [
                f"CPU activity's elevated around {cpu}% and temperatures are steadily climbing — the machine's clearly handling a heavier graphical workload.",
                f"Thermal behavior suggests sustained performance demand already. CPU utilization's currently around {cpu}%.",
            ],

            "browsing": [
                f"System load looks relatively relaxed right now — CPU utilization's sitting around {cpu}% with memory pressure staying comfortable.",
                f"Everything appears fairly stable at the moment. CPU activity's light and the system isn't showing any meaningful strain.",
            ],

            "multitasking": [
                f"Workload distribution's spread across quite a few active processes right now — CPU utilization's around {cpu}% with gradual memory saturation.",
                f"The machine's balancing several concurrent workloads already. CPU load's steady and memory pressure is building slowly.",
                f"There's noticeable execution pressure across the system right now — looks like several active processes competing for resources.",
            ],

            "light": [
                f"System load's unusually calm at the moment — CPU utilization's only around {cpu}% and thermals remain well balanced.",
                f"The machine's barely under any meaningful pressure right now. Resource allocation looks exceptionally clean.",
                f"Everything appears remarkably stable so far — low execution pressure, balanced thermals, and minimal workload density.",
            ],

            "unknown": [
                f"CPU utilization's currently hovering around {cpu}% with no obvious instability.",
                f"Current workload density appears moderate — CPU activity's sitting near {cpu}% right now.",
            ],
        }

        # ── Build observation fragments ─────────────────────────────────────────
        fragments = []

        # PRIMARY: workload + cpu/thermal combined
        if cpu_high and thermal_hot:
            frags = [
                f"CPU utilization's pushing close to {cpu}% and thermals are climbing toward {temp_c}°C — the system's clearly under sustained computational pressure.",
                f"Execution load is sitting extremely high right now — CPU activity's near {cpu}% with temperatures continuing to rise.",
                f"The machine's carrying a fairly intense workload already. CPU utilization's elevated and thermal regulation is actively compensating.",
            ]
            fragments.append(random.choice(frags))
        elif cpu_high and thermal_warm:
            frags = [
                f"CPU's already at {cpu}% and temperatures are up in the low {temp_c}s — the machine's been busy.",
                f"CPU's running at {cpu}% with temperatures warming up toward {temp_c}°.",
            ]
            fragments.append(random.choice(frags))
        elif cpu_high:
            inferences = workload_inferences.get(
                workload_cat, workload_inferences["unknown"])
            fragments.append(random.choice(inferences))
        elif cpu_moderate and ram_heavy:
            frags = [
                f"CPU's moderate at {cpu}%, but memory's getting fairly dense at {ram}% — looks like a heavy session.",
                f"Memory utilization's approaching saturation at {ram}% while CPU activity remains around {cpu}% — the system's definitely carrying a dense workload.",
                f"RAM pressure's unusually heavy already at {ram}%, and CPU utilization's still hovering near {cpu}%. There's a substantial amount happening simultaneously.",
            ]
            fragments.append(random.choice(frags))
        elif cpu_moderate:
            inferences = workload_inferences.get(
                workload_cat, workload_inferences["unknown"])
            fragments.append(random.choice(inferences))
        elif cpu_light and ram_heavy:
            frags = [
                f"CPU's sitting light at {cpu}%, though memory pressure's fairly high at {ram}%.",
                f"Memory usage is getting heavy at {ram}%, even though CPU load looks calm at {cpu}%.",
            ]
            fragments.append(random.choice(frags))
        else:
            # Light and calm
            frags = [
                f"System conditions look exceptionally balanced right now — CPU utilization's holding near {cpu}% while thermals remain stable at {temp_c}°C, with no meaningful pressure buildup. Memory saturation's sitting around {ram}%, so the machine still has plenty of headroom available for heavier workloads.",

                f"The machine's in a remarkably stable state right now — CPU utilization's hovering around {cpu}% while thermal conditions remain balanced near {temp_c}°C. Memory saturation's sitting around {ram}%, leaving plenty of available headroom across the system.",

                f"Resource distribution looks unusually clean right now — CPU activity's sitting near {cpu}% while thermal pressure remains nominal around {temp_c}°C. Memory saturation's currently around {ram}%, so the system still has substantial execution headroom available.",

                f"Execution pressure across the machine remains very light right now — CPU utilization's floating near {cpu}% while thermals hold steady around {temp_c}°C. Memory saturation's only around {ram}%, so the system still has considerable overhead available.",

                f"Everything looks calibrated and stable so far — CPU activity's sitting around {cpu}% with balanced thermal conditions near {temp_c}°C. Memory saturation remains low at roughly {ram}%, leaving the machine in a very responsive state.",

                f"The system initialized into a very clean operating state this morning — CPU utilization's near {cpu}% while thermals remain stable around {temp_c}°C. Memory saturation's currently sitting around {ram}%, so sustained workloads shouldn't create any noticeable pressure.",

                f"Current system telemetry looks remarkably healthy — CPU activity's hovering around {cpu}% while thermal pressure remains minimal near {temp_c}°C. Memory saturation's sitting around {ram}%, leaving plenty of computational headroom available.",

                f"System telemetry's reading exceptionally stable right now — CPU utilization's resting near {cpu}% while thermals remain balanced around {temp_c}°C. Memory saturation's holding around {ram}%, leaving more than enough execution capacity available for heavier tasks.",

                f"The machine's operating in a very clean state right now — CPU activity's sitting near {cpu}% with thermal conditions remaining steady around {temp_c}°C. Memory saturation's still relatively low at {ram}%, so resource overhead looks comfortably available.",

                f"Overall system stability looks excellent so far — CPU utilization's maintaining around {cpu}% while thermal pressure remains controlled near {temp_c}°C. Memory saturation's sitting around {ram}%, which leaves the machine feeling unusually responsive.",
            ]

            fragments.append(random.choice(frags))

        # SECONDARY: battery / power (only if notable)
        if batt_critical:
            frags = [
                f"Battery's down to {batt_pct}% with no charger — worth plugging in before we go too deep.",
                f"Battery's at {batt_pct}% and not charging. That's getting close.",
            ]
            fragments.append(random.choice(frags))
        elif batt_low:
            frags = [
                f"Battery's at {batt_pct}%, not charging — I'd keep the charger in mind.",
                f"Battery's holding at {batt_pct}%, but I'd keep an eye on it.",
            ]
            fragments.append(random.choice(frags))
        elif charging and batt_pct < 100:
            if random.random() < 0.5:
                fragments.append(
                    f"Battery subsystem's charging properly at {batt_pct}%, so sustained workload shouldn't be a problem.")
        elif not charging and batt_pct == 100:
            if random.random() < 0.3:
                fragments.append(
                    f"Battery's fully charged and calibrated at {batt_pct}%, so power availability looks solid.")
        elif charging and batt_pct == 100:
            if random.random() < 0.2:
                fragments.append(
                    f"Power delivery's stable — battery's fully charged at {batt_pct}% and external power is connected.")

        # TERTIARY: thermal / fan (only if notable, and not already covered in primary)
        if fan_active and len(fragments) < 2:
            frags = [
                f"Fans are spinning up a bit at {fan_rpm} RPM — the cooling system's working.",
                "Fans are a little louder than usual, which tells me the machine's been running warm.",
            ]
            fragments.append(random.choice(frags))

        # QUATERNARY: network (only if broken)
        if net_bad:
            frags = [
                "Network looks a bit uneven right now — might get choppy if we need to pull anything.",
                "I'm seeing some network instability. Worth noting if we're doing anything cloud-dependent.",
            ]
            fragments.append(random.choice(frags))

        # Late-night context
        if is_late_night and len(fragments) > 0:
            late_prefixes = [
                "Late start tonight. ",
                "You're up early. ",
            ]
            if random.random() < 0.4:
                fragments[0] = random.choice(
                    late_prefixes) + fragments[0][0].lower() + fragments[0][1:]

        return " ".join(fragments[:2])


response_modes = ResponseModeManager()
