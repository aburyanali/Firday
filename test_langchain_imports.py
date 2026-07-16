# 🤖 FRIDAY - ULTIMATE AI ASSISTANT (WORKING VERSION)
# Fully functional with GUI, Voice, Text - Everything working!
# Created by Mr. Ryan

import os
import sys
import speech_recognition as sr
import subprocess
import datetime
import pytz
import threading
import re
import math
import logging
import time
import random
import sqlite3
from pathlib import Path
from typing import Optional, Dict, List
from urllib.parse import quote_plus

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('friday.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Try importing tkinter for GUI
try:
    import tkinter as tk
    from tkinter import scrolledtext, messagebox
    TKINTER_AVAILABLE = True
except ImportError:
    TKINTER_AVAILABLE = False
    logger.warning("tkinter not available - GUI disabled")

# ============================================================================
# CONVERSATION MEMORY
# ============================================================================


class ConversationMemory:
    """Store conversations in SQLite"""

    def __init__(self):
        self.db_path = str(Path.home() / ".friday_memory.db")
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.lock = threading.Lock()
        self.setup()

    def setup(self):
        cursor = self.conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY,
                user_message TEXT,
                friday_response TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        self.conn.commit()

    def save(self, user_msg: str, response: str):
        with self.lock:
            cursor = self.conn.cursor()
            cursor.execute("""
                INSERT INTO conversations (user_message, friday_response)
                VALUES (?, ?)
            """, (user_msg, response))
            self.conn.commit()


# ============================================================================
# MATH CALCULATOR
# ============================================================================

class Calculator:
    """Smart math calculator"""

    def __init__(self):
        self.safe_dict = {
            'abs': abs, 'round': round, 'min': min, 'max': max,
            'sum': sum, 'pow': pow, 'pi': math.pi, 'e': math.e,
            'sqrt': math.sqrt, 'log': math.log, 'sin': math.sin, 'cos': math.cos
        }

    def parse(self, text: str) -> str:
        """Convert natural language to math"""
        text = text.lower().strip()

        # Remove words
        for word in ['what is', 'calculate', 'compute', 'solve', '?']:
            text = text.replace(word, '')

        # Replace operators
        replacements = {
            ' plus ': ' + ', ' and ': ' + ',
            ' minus ': ' - ', ' subtract ': ' - ',
            ' times ': ' * ', ' multiplied by ': ' * ',
            ' divided by ': ' / ', ' divide ': ' / ',
            ' to the power of ': ' ** ', '^': '**',
            ' squared': '**2', ' cubed': '**3',
            'sqrt': 'sqrt'
        }

        for word, op in replacements.items():
            text = text.replace(word, op)

        return text.strip()

    def calculate(self, expression: str) -> Optional[str]:
        """Calculate safely"""
        try:
            expr = self.parse(expression)

            # Security check
            if any(x in expr for x in ['__', 'import', 'eval', 'exec', 'open']):
                return None

            result = eval(expr, {"__builtins__": {}}, self.safe_dict)

            if isinstance(result, float):
                result = int(result) if result.is_integer(
                ) else round(result, 4)

            return str(result)
        except:
            return None


# ============================================================================
# FRIENDLY CONVERSATION
# ============================================================================

class FriendlyChat:
    """Friendly conversational responses"""

    def __init__(self, name: str = "Mr. Ryan"):
        self.name = name
        self.tz = pytz.timezone('Asia/Kolkata')

    def get_greeting(self) -> str:
        """Get time-appropriate greeting"""
        hour = datetime.datetime.now(self.tz).hour

        if 5 <= hour < 12:
            return random.choice([
                f"Good morning {self.name}! 🌅 Hope you slept well. Ready to conquer the day? 💪",
                f"Hey {self.name}! ☀️ Morning! What can I help you with today?",
                f"Rise and shine {self.name}! 🌟 Let's make today amazing!",
                f"Good morning! 💪 How are you feeling today?"
            ])
        elif 12 <= hour < 17:
            return random.choice([
                f"Good afternoon {self.name}! 🌤️ How's your day going?",
                f"Afternoon {self.name}! ⏰ What's on your mind?",
                f"Good afternoon! 💼 Productive day so far?",
                f"Hey {self.name}! 🎯 Ready to tackle some tasks?"
            ])
        elif 17 <= hour < 21:
            return random.choice([
                f"Good evening {self.name}! 🌆 How was your day?",
                f"Evening {self.name}! 🌙 Time to wind down. What can I help?",
                f"Good evening! 😊 Hope you had a great day {self.name}.",
                f"Hey {self.name}! 🌇 Let's wrap up the day right!"
            ])
        else:
            return random.choice([
                f"Good evening {self.name}! 🌙 Still working? Let's finish strong!",
                f"Hey {self.name}! 🌃 Night owl mode? 🦉 What's up?",
                f"Evening {self.name}! ✨ Working late, I see!",
                f"Hello {self.name}! 🌟 What's on your mind?"
            ])

    def get_goodbye(self) -> str:
        """Get goodbye message"""
        hour = datetime.datetime.now(self.tz).hour

        if 21 <= hour or hour < 6:
            return random.choice([
                f"Good night {self.name}! 😴 Sleep well and dream big! 🌟",
                f"Sweet dreams {self.name}! 🌙 Rest up for tomorrow!",
                f"Night night {self.name}! 💤 Take care!",
                f"Good night! 🌙 See you tomorrow {self.name}!"
            ])
        else:
            return random.choice([
                f"See you later {self.name}! 👋 Have an amazing day! 🚀",
                f"Catch you soon {self.name}! ⚡ Keep crushing it!",
                f"Goodbye {self.name}! 🎉 Make it great!",
                f"Take care {self.name}! 💪 I'll be here when you need me!"
            ])

    def casual_response(self, query: str) -> Optional[str]:
        """Casual chat responses"""
        q = query.lower()

        if any(x in q for x in ['hi', 'hello', 'hey', 'sup']):
            return random.choice([
                f"Hey {self.name}! 👋 Great to hear from you! What's up?",
                f"Hello! 😊 Always happy to chat with you!",
                f"Hi there! 🎉 What can I do for you?",
                f"Hey! 👋 Ready to help. What's on your mind?"
            ])

        if any(x in q for x in ['how are you', 'how are u', 'how r u']):
            return random.choice([
                "I'm doing fantastic! 🚀 All systems running smoothly. How about you?",
                "Excellent! ⚡ Charged up and ready to assist. You good?",
                "Great! 😊 Always energized when helping you. How's everything?",
                "Perfect! 💪 Ready for anything. What about you?"
            ])

        if any(x in q for x in ['thank', 'thanks', 'thx']):
            return random.choice([
                f"You're welcome {self.name}! 😊 Happy to help anytime!",
                "My pleasure! 🎉 That's what I'm here for!",
                f"Anytime {self.name}! 👍 Glad I could assist!",
                "No problem! 💪 Always here for you!"
            ])

        if any(x in q for x in ['joke', 'funny', 'laugh']):
            jokes = [
                "Why do programmers prefer dark mode? 🌙 Because light attracts bugs! 🐛",
                "Why did the AI go to school? 🎓 To improve its learning model! 🧠",
                "How many programmers does it take to change a light? 💡 None - that's a hardware problem! 😄",
                "Why did the function go to therapy? 📞 It had too many nested issues! 😂"
            ]
            return random.choice(jokes)

        return None

    def get_time_response(self) -> str:
        """Get current time"""
        now = datetime.datetime.now(self.tz)
        return f"It's {now.strftime('%I:%M %p')} on {now.strftime('%A, %B %d, %Y')} ⏰"


# ============================================================================
# VOICE ENGINE
# ============================================================================

class VoiceEngine:
    """macOS text-to-speech"""

    def __init__(self):
        self.voice = self.select_voice()
        self.rate = 200

    def get_voices(self):
        try:
            result = subprocess.run(
                ['say', '-v', '?'], capture_output=True, text=True, check=True)
            voices = []
            for line in result.stdout.splitlines():
                parts = line.split()
                if parts:
                    voices.append(parts[0])
            return voices
        except:
            return ['Alex']

    def select_voice(self):
        voices = self.get_voices()
        preferred = ['Samantha', 'Alex', 'Victoria', 'Allison']
        for p in preferred:
            for v in voices:
                if p.lower() in v.lower():
                    return v
        return voices[0] if voices else 'Alex'

    def speak(self, text: str):
        """Speak text"""
        if not text or len(text.strip()) == 0:
            return
        try:
            subprocess.run(['killall', 'say'], check=False,
                           stderr=subprocess.DEVNULL)
            cmd = ['say', '-v', self.voice, '-r', str(self.rate), text]
            threading.Thread(
                target=lambda: subprocess.run(cmd, stderr=subprocess.DEVNULL),
                daemon=True
            ).start()
            time.sleep(0.1)
        except Exception as e:
            logger.error(f"Voice error: {e}")


# ============================================================================
# VOICE LISTENER
# ============================================================================

class VoiceListener:
    """Continuous voice listener"""

    def __init__(self, callback):
        self.callback = callback
        self.recognizer = sr.Recognizer()
        self.microphone = sr.Microphone()
        self.listening = False
        self.setup()

    def setup(self):
        try:
            with self.microphone as m:
                self.recognizer.adjust_for_ambient_noise(m, duration=0.5)
            self.recognizer.energy_threshold = 350
            self.recognizer.pause_threshold = 1.0
        except Exception as e:
            logger.warning(f"Microphone setup: {e}")

    def start(self):
        if self.listening:
            return
        self.listening = True
        threading.Thread(target=self.listen_loop, daemon=True).start()

    def listen_loop(self):
        while self.listening:
            try:
                with self.microphone as source:
                    audio = self.recognizer.listen(
                        source, timeout=30, phrase_time_limit=8)
                try:
                    text = self.recognizer.recognize_google(
                        audio, language='en-IN').lower().strip()
                    if text and len(text) > 1:
                        self.callback(text)
                except:
                    pass
            except:
                continue

    def stop(self):
        self.listening = False


# ============================================================================
# MAIN FRIDAY ASSISTANT
# ============================================================================

class Friday:
    """Main Friday Assistant"""

    def __init__(self, name: str = "Mr. Ryan"):
        self.name = name
        self.memory = ConversationMemory()
        self.calculator = Calculator()
        self.chat = FriendlyChat(name)
        self.voice = VoiceEngine()
        self.listener = None
        self.running = False
        logger.info(f"Friday initialized for {name}")

    def process(self, query: str) -> str:
        """Process user query"""
        if not query or len(query.strip()) == 0:
            return ""

        query = query.strip()
        logger.info(f"Query: {query}")

        # Casual response
        casual = self.chat.casual_response(query)
        if casual:
            self.memory.save(query, casual)
            return casual

        # Exit commands
        if any(x in query.lower() for x in ['exit', 'quit', 'bye', 'goodbye']):
            return "EXIT"

        # Math
        if any(x in query.lower() for x in ['plus', 'minus', 'times', 'divide', 'calculate', '+', '-', '*', '/']):
            result = self.calculator.calculate(query)
            if result:
                response = f"The answer is {result} 🧮"
                self.memory.save(query, response)
                return response

        # Time
        if any(x in query.lower() for x in ['time', 'date', 'what time']):
            response = self.chat.get_time_response()
            self.memory.save(query, response)
            return response

        # Code
        if any(x in query.lower() for x in ['code', 'generate', 'write', 'python']):
            response = f"Here's your Python code template 💻:\n\ndef main():\n    print('Hello {self.name}!')\n\nif __name__ == '__main__':\n    main()"
            self.memory.save(query, response)
            return response

        # Default
        response = f"That's an interesting question {self.name}! 🤔 You asked about: {query[:50]}... I'm learning more every day!"
        self.memory.save(query, response)
        return response

    def voice_callback(self, text: str):
        """Process voice input"""
        if text:
            print(f"\n🎤 You (voice): {text}")
            response = self.process(text)
            if response and response != "EXIT":
                print(f"🎤 Friday: {response}\n")
                self.voice.speak(response)


# ============================================================================
# GUI VERSION
# ============================================================================

class FridayGUI:
    """GUI Interface for Friday"""

    def __init__(self):
        if not TKINTER_AVAILABLE:
            raise ImportError("tkinter not available")

        self.friday = Friday()
        self.root = tk.Tk()
        self.root.title("FRIDAY - Ultimate AI Assistant")
        self.root.geometry("1000x600")
        self.root.configure(bg='#0a0e27')

        self.setup()
        self.show_greeting()

    def setup(self):
        """Setup GUI"""
        # Header
        header = tk.Frame(self.root, bg='#1a1f3a', height=60)
        header.pack(fill='x', padx=10, pady=5)

        title = tk.Label(
            header,
            text="⚡ FRIDAY - Ultimate AI Assistant",
            font=('Helvetica', 24, 'bold'),
            bg='#1a1f3a',
            fg='#00d4ff'
        )
        title.pack(pady=10)

        # Chat display
        chat_frame = tk.Frame(self.root, bg='#0a0e27')
        chat_frame.pack(fill='both', expand=True, padx=10, pady=5)

        self.chat_display = scrolledtext.ScrolledText(
            chat_frame,
            wrap=tk.WORD,
            font=('Courier', 11),
            bg='#0d1225',
            fg='#ffffff',
            height=20
        )
        self.chat_display.pack(fill='both', expand=True)

        self.chat_display.tag_config('user', foreground='#00d4ff')
        self.chat_display.tag_config('friday', foreground='#00ff88')

        # Input frame
        input_frame = tk.Frame(self.root, bg='#0a0e27')
        input_frame.pack(fill='x', padx=10, pady=5)

        self.input_entry = tk.Entry(
            input_frame,
            font=('Helvetica', 12),
            bg='#0d1225',
            fg='#ffffff'
        )
        self.input_entry.pack(side='left', fill='x', expand=True, padx=(0, 5))
        self.input_entry.bind('<Return>', lambda e: self.send_message())

        send_btn = tk.Button(
            input_frame,
            text="⚡ SEND",
            font=('Helvetica', 10, 'bold'),
            bg='#00d4ff',
            fg='#0a0e27',
            command=self.send_message,
            padx=20,
            cursor='hand2'
        )
        send_btn.pack(side='left', padx=2)

        voice_btn = tk.Button(
            input_frame,
            text="🎤 VOICE",
            font=('Helvetica', 10, 'bold'),
            bg='#00ff88',
            fg='#0a0e27',
            command=self.toggle_voice,
            padx=20,
            cursor='hand2'
        )
        voice_btn.pack(side='left', padx=2)

        self.voice_btn = voice_btn

    def show_greeting(self):
        """Show greeting"""
        greeting = self.friday.chat.get_greeting()
        self.add_message("FRIDAY", greeting, 'friday')
        self.friday.voice.speak(greeting)

    def add_message(self, sender: str, message: str, tag: str = 'friday'):
        """Add message to display"""
        self.chat_display.insert(tk.END, f"{sender}: ", tag)
        self.chat_display.insert(tk.END, f"{message}\n\n")
        self.chat_display.see(tk.END)
        self.root.update()

    def send_message(self):
        """Send message"""
        msg = self.input_entry.get().strip()
        if msg:
            self.add_message("YOU", msg, 'user')
            self.input_entry.delete(0, tk.END)
            threading.Thread(target=self.process_msg,
                             args=(msg,), daemon=True).start()

    def process_msg(self, msg: str):
        """Process message"""
        response = self.friday.process(msg)
        if response == "EXIT":
            self.root.after(0, self.root.quit)
        else:
            self.root.after(0, self.add_message, "FRIDAY", response, 'friday')
            self.friday.voice.speak(response)

    def toggle_voice(self):
        """Toggle voice"""
        if self.friday.listener is None:
            self.friday.listener = VoiceListener(self.friday.voice_callback)

        if self.friday.listener.listening:
            self.friday.listener.stop()
            self.voice_btn.config(text="🎤 START", bg='#00ff88')
            self.add_message("SYSTEM", "Voice stopped 🔕", 'friday')
        else:
            self.friday.listener.start()
            self.voice_btn.config(text="🎤 STOP", bg='#ff3366')
            self.add_message("SYSTEM", "Voice listening... 🎙️", 'friday')

    def run(self):
        """Run GUI"""
        self.root.mainloop()


# ============================================================================
# CLI VERSION
# ============================================================================

class FridayCLI:
    """CLI Interface for Friday"""

    def __init__(self):
        self.friday = Friday()

    def run(self):
        """Run CLI"""
        print("\n" + "="*80)
        print("🤖 FRIDAY - ULTIMATE AI ASSISTANT 🤖".center(80))
        print("="*80)
        print(f"Owner: {self.friday.name}\n")

        greeting = self.friday.chat.get_greeting()
        print(f"🎤 Friday: {greeting}\n")
        self.friday.voice.speak(greeting)

        # Start voice listener
        self.friday.listener = VoiceListener(self.friday.voice_callback)
        self.friday.listener.start()
        print("🎤 Voice listening activated! You can speak and type.\n")

        try:
            while True:
                user_input = input("💭 You: ").strip()
                if user_input:
                    response = self.friday.process(user_input)
                    if response == "EXIT":
                        goodbye = self.friday.chat.get_goodbye()
                        print(f"\n🎤 Friday: {goodbye}")
                        self.friday.voice.speak(goodbye)
                        break
                    else:
                        print(f"🎤 Friday: {response}\n")
                        self.friday.voice.speak(response)
        except KeyboardInterrupt:
            print("\n\n👋 Goodbye!")
        finally:
            if self.friday.listener:
                self.friday.listener.stop()


# ============================================================================
# MAIN ENTRY POINT
# ============================================================================

if __name__ == "__main__":
    print("\n🚀 Starting FRIDAY Ultimate AI Assistant...\n")

    try:
        if TKINTER_AVAILABLE:
            print("🎨 Launching GUI mode...\n")
            gui = FridayGUI()
            gui.run()
        else:
            print("📱 Running CLI mode...\n")
            cli = FridayCLI()
            cli.run()
    except Exception as e:
        logger.error(f"Error: {e}")
        print(f"\n❌ Error: {e}")
        print("📱 Running CLI mode as fallback...\n")
        try:
            cli = FridayCLI()
            cli.run()
        except KeyboardInterrupt:
            print("\n\n👋 Goodbye!")
