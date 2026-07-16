import os
import sys
import time
import datetime
import threading
import json
import sqlite3
import logging
import re
import math
import subprocess
from pathlib import Path
from urllib.parse import quote_plus
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from collections import deque

from config import config, create_openai_client
import speech_recognition as sr
import pytz
import requests
import sqlite3
from datetime import datetime

try:
    from elevenlabs.client import ElevenLabs
    from elevenlabs import VoiceSettings
    ELEVENLABS_AVAILABLE = True
except ImportError:
    ELEVENLABS_AVAILABLE = False

try:
    from openai import OpenAI
    PERPLEXITY_AVAILABLE = True
except ImportError:
    PERPLEXITY_AVAILABLE = False

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler('friday.log'), logging.StreamHandler()]
)
logger = logging.getLogger(__name__)


# ============================================================================
# FIX: Column-Aware Schema Migration (Safe for any DB state)
# ============================================================================

class SchemaManager:
    """
    FIX: Safe, idempotent schema migration
    - Inspects actual columns before creating indexes
    - Adds missing columns safely
    - Never assumes column existence
    - Works on fresh, v0, v1, or broken DBs
    """

    CURRENT_SCHEMA_VERSION = 2

    @staticmethod
    def get_columns(conn, table: str) -> set:
        """FIX: Safely get actual columns in table"""
        try:
            cursor = conn.cursor()
            cursor.execute(f"PRAGMA table_info({table})")
            columns = {row[1] for row in cursor.fetchall()}
            logger.info(f"Columns in {table}: {columns}")
            return columns
        except Exception as e:
            logger.error(f"Error getting columns for {table}: {e}")
            return set()

    @staticmethod
    def column_exists(conn, table: str, column: str) -> bool:
        """FIX: Check if column exists before using it"""
        columns = SchemaManager.get_columns(conn, table)
        exists = column in columns
        if not exists:
            logger.warning(f"Column {table}.{column} does NOT exist")
        return exists

    @staticmethod
    def add_column_safe(conn, table: str, column: str, col_type: str = "TEXT", default: str = "NULL") -> bool:
        """FIX: Safely add column if it doesn't exist"""
        if SchemaManager.column_exists(conn, table, column):
            logger.info(f"Column {table}.{column} already exists, skipping")
            return True

        try:
            cursor = conn.cursor()
            # Add column with DEFAULT to avoid NULL issues
            if default == "NULL":
                cursor.execute(
                    f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")
            else:
                cursor.execute(
                    f"ALTER TABLE {table} ADD COLUMN {column} {col_type} DEFAULT {default}")
            conn.commit()
            logger.info(f"✓ Added column: {table}.{column}")
            return True
        except Exception as e:
            logger.error(f"Error adding column {table}.{column}: {e}")
            return False

    @staticmethod
    def init_schema(conn):
        """FIX: Initialize schema with column-aware migration"""
        cursor = conn.cursor()

        # Create version table first
        try:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS schema_version (
                    version INTEGER PRIMARY KEY,
                    applied_at REAL
                )
            """)
            conn.commit()
        except Exception as e:
            logger.error(f"Error creating schema_version table: {e}")

        # Get current version
        try:
            cursor.execute(
                "SELECT version FROM schema_version ORDER BY version DESC LIMIT 1")
            result = cursor.fetchone()
            current_version = result[0] if result else 0
        except:
            current_version = 0

        logger.info(
            f"DB schema version: {current_version}, target: {SchemaManager.CURRENT_SCHEMA_VERSION}")

        # Apply migrations
        if current_version < 1:
            SchemaManager._migrate_to_v1(conn)
            try:
                cursor.execute(
                    "INSERT OR IGNORE INTO schema_version (version, applied_at) VALUES (1, ?)", (time.time(),))
                conn.commit()
                logger.info("✓ Schema migrated to v1")
            except Exception as e:
                logger.error(f"Error recording v1 migration: {e}")

        if current_version < 2:
            SchemaManager._migrate_to_v2(conn)
            try:
                cursor.execute(
                    "INSERT OR IGNORE INTO schema_version (version, applied_at) VALUES (2, ?)", (time.time(),))
                conn.commit()
                logger.info("✓ Schema migrated to v2")
            except Exception as e:
                logger.error(f"Error recording v2 migration: {e}")

    @staticmethod
    def _migrate_to_v1(conn):
        """V1: Create core tables if they don't exist"""
        cursor = conn.cursor()

        try:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS memories (
                    id INTEGER PRIMARY KEY,
                    key TEXT,
                    value TEXT,
                    category TEXT DEFAULT 'general',
                    timestamp REAL,
                    importance INTEGER DEFAULT 0,
                    recall_count INTEGER DEFAULT 0
                )
            """)
            logger.info("✓ Created memories table")
        except Exception as e:
            logger.error(f"Error creating memories table: {e}")

        try:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS habits (
                    id INTEGER PRIMARY KEY,
                    habit_name TEXT UNIQUE,
                    frequency INTEGER DEFAULT 1,
                    last_timestamp REAL,
                    context TEXT
                )
            """)
            logger.info("✓ Created habits table")
        except Exception as e:
            logger.error(f"Error creating habits table: {e}")

        try:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS context (
                    id INTEGER PRIMARY KEY,
                    user_message TEXT,
                    assistant_response TEXT,
                    timestamp REAL,
                    task_type TEXT
                )
            """)
            logger.info("✓ Created context table")
        except Exception as e:
            logger.error(f"Error creating context table: {e}")

        try:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS reflections (
                    id INTEGER PRIMARY KEY,
                    task_type TEXT,
                    success INTEGER,
                    outcome TEXT,
                    timestamp REAL
                )
            """)
            logger.info("✓ Created reflections table")
        except Exception as e:
            logger.error(f"Error creating reflections table: {e}")

        conn.commit()

    @staticmethod
    def _migrate_to_v2(conn):
        """FIX: V2 - Column-aware migration"""
        cursor = conn.cursor()

        # Ensure memories table exists
        try:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS memories (
                    id INTEGER PRIMARY KEY,
                    key TEXT,
                    value TEXT,
                    category TEXT DEFAULT 'general',
                    timestamp REAL,
                    importance INTEGER DEFAULT 0,
                    recall_count INTEGER DEFAULT 0
                )
            """)
            conn.commit()
        except Exception as e:
            logger.error(f"Error ensuring memories table: {e}")

        # FIX: Add missing columns safely
        logger.info("Performing column-aware schema migration...")

        # Add key column if missing
        if not SchemaManager.column_exists(conn, 'memories', 'key'):
            SchemaManager.add_column_safe(
                conn, 'memories', 'key', 'TEXT', 'NULL')

        # Add value column if missing
        if not SchemaManager.column_exists(conn, 'memories', 'value'):
            SchemaManager.add_column_safe(
                conn, 'memories', 'value', 'TEXT', 'NULL')

        # Add category column if missing
        if not SchemaManager.column_exists(conn, 'memories', 'category'):
            SchemaManager.add_column_safe(
                conn, 'memories', 'category', "TEXT DEFAULT 'general'", 'NULL')

        # Add timestamp column if missing
        if not SchemaManager.column_exists(conn, 'memories', 'timestamp'):
            SchemaManager.add_column_safe(
                conn, 'memories', 'timestamp', 'REAL', 'NULL')

        # Add importance column if missing
        if not SchemaManager.column_exists(conn, 'memories', 'importance'):
            SchemaManager.add_column_safe(
                conn, 'memories', 'importance', 'INTEGER DEFAULT 0', '0')

        # Add recall_count column if missing
        if not SchemaManager.column_exists(conn, 'memories', 'recall_count'):
            SchemaManager.add_column_safe(
                conn, 'memories', 'recall_count', 'INTEGER DEFAULT 0', '0')

        # Create conversation_history table
        try:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS conversation_history (
                    id INTEGER PRIMARY KEY,
                    user_input TEXT,
                    intent TEXT,
                    entities TEXT,
                    response TEXT,
                    timestamp REAL
                )
            """)
            conn.commit()
            logger.info("✓ Created conversation_history table")
        except Exception as e:
            logger.error(f"Error creating conversation_history table: {e}")

        # FIX: Only create indexes AFTER ensuring columns exist
        logger.info("Creating indexes (columns now guaranteed to exist)...")

        try:
            cursor.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS idx_memory_key 
                ON memories(key)
            """)
            logger.info("✓ Created index: idx_memory_key")
        except Exception as e:
            logger.error(f"Error creating idx_memory_key: {e}")

        try:
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_conversation_timestamp 
                ON conversation_history(timestamp)
            """)
            logger.info("✓ Created index: idx_conversation_timestamp")
        except Exception as e:
            logger.error(f"Error creating idx_conversation_timestamp: {e}")

        try:
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_memory_importance 
                ON memories(importance DESC)
            """)
            logger.info("✓ Created index: idx_memory_importance")
        except Exception as e:
            logger.error(f"Error creating idx_memory_importance: {e}")

        conn.commit()
        logger.info("✓ Schema migration to v2 completed safely")


# ============================================================================
# Enhanced Memory System with Deterministic Storage
# ============================================================================

class AdvancedMemorySystem:
    """
    FIX: Schema-safe memory with column-aware migration
    NEW: Conversation context tracking
    """

    def __init__(self):
        self.db_path = os.path.expanduser(config.memory_db_path)
        self.conn = sqlite3.connect(
            self.db_path, check_same_thread=False, timeout=30)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.lock = threading.Lock()

        # FIX: Initialize schema with column-aware migration
        SchemaManager.init_schema(self.conn)

        logger.info("✓ MemorySystem ready (schema v2)")

    def store_memory(self, key: str, value: str, category: str = 'general') -> str:
        """FIX: Schema-safe storage"""
        with self.lock:
            cursor = self.conn.cursor()
            try:
                # Explicit column names, never positional
                cursor.execute(
                    """INSERT OR REPLACE INTO memories 
                       (key, value, category, timestamp, importance, recall_count)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (key.lower(), value, category, time.time(), 1, 0)
                )
                self.conn.commit()
                logger.info(f"✓ Memory stored: {key} = {value[:30]}...")
                return f"Got it. I'll remember: {key} = {value}"
            except Exception as e:
                logger.error(f"Memory store error: {e}")
                return f"I had trouble remembering that. Error: {str(e)[:50]}"

    def recall_memory(self, query: str) -> Optional[str]:
        """FIX: Safe recall with reinforcement"""
        try:
            cursor = self.conn.cursor()
            query_normalized = query.lower().strip()

            # Exact match
            cursor.execute(
                "SELECT value FROM memories WHERE key = ?",
                (query_normalized,)
            )
            result = cursor.fetchone()

            if result:
                # Reinforce on successful recall
                cursor.execute(
                    """UPDATE memories SET recall_count = recall_count + 1, 
                       importance = importance + 1 WHERE key = ?""",
                    (query_normalized,)
                )
                self.conn.commit()
                logger.info(f"✓ Memory recalled: {query} = {result[0]}")
                return result[0]

            # Fuzzy match
            cursor.execute(
                "SELECT key, value FROM memories WHERE key LIKE ? ORDER BY importance DESC LIMIT 1",
                (f"%{query_normalized}%",)
            )
            result = cursor.fetchone()

            if result:
                key, value = result
                cursor.execute(
                    "UPDATE memories SET recall_count = recall_count + 1 WHERE key = ?",
                    (key,)
                )
                self.conn.commit()
                logger.info(f"✓ Memory recalled (fuzzy): {query}")
                return value

            logger.warning(f"Memory not found: {query}")
            return None
        except Exception as e:
            logger.error(f"Memory recall error: {e}")
            return None

    def store_conversation(self, user_input: str, intent: str, entities: Dict, response: str) -> None:
        """Store conversation for context"""
        with self.lock:
            cursor = self.conn.cursor()
            try:
                cursor.execute(
                    """INSERT INTO conversation_history 
                       (user_input, intent, entities, response, timestamp)
                       VALUES (?, ?, ?, ?, ?)""",
                    (user_input, intent, json.dumps(
                        entities), response, time.time())
                )
                self.conn.commit()
            except Exception as e:
                logger.error(f"Conversation store error: {e}")

    def get_last_intents(self, count: int = 3) -> List[Dict]:
        """Get last N intents for context"""
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                """SELECT user_input, intent, entities, timestamp 
                   FROM conversation_history 
                   ORDER BY timestamp DESC LIMIT ?""",
                (count,)
            )
            results = cursor.fetchall()

            return [
                {
                    'user_input': row[0],
                    'intent': row[1],
                    'entities': json.loads(row[2]) if row[2] else {},
                    'timestamp': row[3]
                }
                for row in reversed(results)
            ]
        except Exception as e:
            logger.error(f"Get history error: {e}")
            return []


# ============================================================================
# SEMANTIC MEMORY ENHANCEMENT (ADDITIVE)
# ============================================================================

class SemanticMemoryManager:
    """
    Semantic layer on top of existing AdvancedMemorySystem.
    Handles:
    - Pronoun resolution (my → current_user)
    - Canonical key normalization (birthday facts)
    - Value normalization (dates, phones)
    - Multi-user scoping
    - Temporal fact resolution
    - Personality trait storage
    """

    # Canonical memory keys (extendable registry)
    CANONICAL_KEYS = {
        'birthday': 'birthday',
        'phone': 'phone',
        'email': 'email',
        'address': 'address',
        'name': 'name',
        'occupation': 'occupation',
        'preferences': 'preferences',
        'personality': 'personality',
        'habits': 'habits',
        'goals': 'goals',
    }

    # Personality trait domains
    PERSONALITY_TRAITS = [
        'tone', 'detail_level', 'humor', 'formality',
        'preferred_language', 'communication_style', 'learning_pace'
    ]

    def __init__(self, memory_system, current_user_id: str = "user_default"):
        """
        Initialize semantic layer.
        Wraps existing AdvancedMemorySystem without replacing it.
        """
        self.memory = memory_system
        self.current_user_id = current_user_id
        self.user_profile = self._load_user_profile(current_user_id)
        logger.info(
            f"SemanticMemoryManager initialized for user: {current_user_id}")

    # ========================================================================
    # 1. PRONOUN RESOLUTION (Rule 1A)
    # ========================================================================

    def resolve_ownership(self, pronoun: str, explicit_person: str = None) -> str:
        """
        Resolve pronouns to actual user identities.

        pronoun: 'my', 'his', 'her', 'our', 'your'
        explicit_person: 'John', 'Sarah', etc. (optional)

        Returns: resolved user_id or raises clarification needed
        """
        pronoun_lower = pronoun.lower().strip()

        # Explicit ownership provided
        if explicit_person:
            return self._resolve_person(explicit_person)

        # Map pronouns to users
        pronoun_map = {
            'my': self.current_user_id,
            'i': self.current_user_id,
            'me': self.current_user_id,
            'our': self._get_group_owner(),  # May need clarification
            'his': None,  # Needs explicit reference
            'her': None,  # Needs explicit reference
            'your': 'assistant',  # Properties about the AI
            'its': None,  # Needs clarification
        }

        resolved = pronoun_map.get(pronoun_lower)

        if resolved is None:
            raise OwnershipResolutionNeeded(
                f"Cannot resolve '{pronoun}' ownership. Who are you referring to?"
            )

        return resolved

    def _resolve_person(self, name: str) -> str:
        """Resolve person name to user_id"""
        # In future: look up in contacts, relationships
        # For now: return normalized name as user_id
        return name.lower().replace(' ', '_')

    def _get_group_owner(self) -> str:
        """Get current user's group (if applicable)"""
        # For personal assistant: treat as individual
        return self.current_user_id

    # ========================================================================
    # 2. CANONICAL KEY NORMALIZATION (Rule 1B)
    # ========================================================================

    def extract_canonical_key(self, user_input: str) -> Optional[str]:
        """
        Extract canonical memory key from raw user language.

        Examples:
        "my birthday is 22nd jan" → 'birthday'
        "my phone number is 1234567890" → 'phone'
        "i prefer coffee" → 'preferences.beverage'

        Returns: canonical key or None
        """
        user_lower = user_input.lower()

        # Direct key matching
        for keyword, canonical in self.CANONICAL_KEYS.items():
            if keyword in user_lower:
                return canonical

        # Pattern-based extraction
        patterns = {
            r'(birth|born|birthday)': 'birthday',
            r'(phone|mobile|cell)': 'phone',
            r'(email|mail|address@)': 'email',
            r'(home|address|live)': 'address',
            r'(occupation|job|work|do for a living)': 'occupation',
            r'(prefer|like|favorite|love)': 'preferences',
            r'(personality|am|trait|character)': 'personality',
            r'(habit|usually|typically|routinely)': 'habits',
            r'(goal|want|aim|aspire)': 'goals',
        }

        for pattern, key in patterns.items():
            if re.search(pattern, user_lower):
                return key

        return None

    # ========================================================================
    # 3. FACT NORMALIZATION (Rule 1C)
    # ========================================================================

    def normalize_fact_value(self, key: str, raw_value: str) -> str:
        """
        Normalize raw values into stable, canonical formats.

        key: canonical key (birthday, phone, etc.)
        raw_value: user-provided value

        Returns: normalized value
        """
        raw_lower = raw_value.lower().strip()

        # DATE NORMALIZATION
        if key == 'birthday':
            return self._normalize_date(raw_value)

        # PHONE NORMALIZATION
        if key == 'phone':
            digits = re.sub(r'\D', '', raw_value)
            if len(digits) >= 10:
                return digits[-10:]  # Last 10 digits
            raise ValueError(f"Invalid phone: {raw_value}")

        # EMAIL NORMALIZATION
        if key == 'email':
            email = raw_value.strip().lower()
            if '@' in email:
                return email
            raise ValueError(f"Invalid email: {raw_value}")

        # NAME NORMALIZATION
        if key in ['name', 'occupation']:
            return raw_value.strip().title()

        # ADDRESS NORMALIZATION
        if key == 'address':
            return self._normalize_address(raw_value)

        # PERSONALITY TRAITS
        if key.startswith('personality.'):
            return raw_value.strip().lower()

        # PREFERENCES
        if key.startswith('preferences.'):
            return raw_value.strip().lower()

        # DEFAULT: minimal normalization
        return raw_value.strip()

    def _normalize_date(self, date_str: str) -> str:
        """Normalize dates to canonical format: DD Month"""
        # Patterns: "22 jan", "22nd january", "jan 22", "22-01-2025"
        import re

        month_map = {
            'january': 'January', 'february': 'February', 'march': 'March',
            'april': 'April', 'may': 'May', 'june': 'June',
            'july': 'July', 'august': 'August', 'september': 'September',
            'october': 'October', 'november': 'November', 'december': 'December',
            'jan': 'January', 'feb': 'February', 'mar': 'March',
            'apr': 'April', 'may': 'May', 'jun': 'June',
            'jul': 'July', 'aug': 'August', 'sep': 'September',
            'oct': 'October', 'nov': 'November', 'dec': 'December',
        }

        date_lower = date_str.lower()

        # Extract day and month
        day_match = re.search(r'(\d{1,2})', date_lower)
        month_match = None

        for month_key, month_full in month_map.items():
            if month_key in date_lower:
                month_match = month_full
                break

        if day_match and month_match:
            day = str(int(day_match.group(1))).zfill(2)
            return f"{day} {month_match}"

        # If parsing fails, return as-is
        logger.warning(f"Could not normalize date: {date_str}")
        return date_str

    def _normalize_address(self, address_str: str) -> str:
        """Normalize addresses to canonical format"""
        # For now: Title case the full address
        # In future: geocoding, canonicalization
        return address_str.title()

    # ========================================================================
    # 4. SEMANTIC STORAGE (Core Operation)
    # ========================================================================

    def store_semantic_memory(
        self,
        user_input: str,
        current_user_id: str = None
    ) -> str:
        """
        High-level semantic memory storage.
        Handles: resolution → normalization → storage

        Returns: confirmation message
        """
        if current_user_id is None:
            current_user_id = self.current_user_id

        try:
            # Step 1: Extract canonical key
            key = self.extract_canonical_key(user_input)
            if not key:
                return "I couldn't identify what to remember from that."

            # Step 2: Extract value (simple regex or intent-based)
            raw_value = self._extract_value_from_input(user_input, key)
            if not raw_value:
                return f"Could you tell me the specific {key}?"

            # Step 3: Normalize value
            normalized_value = self.normalize_fact_value(key, raw_value)

            # Step 4: Create scoped memory key (user_id:key)
            scoped_key = f"{current_user_id}:{key}"

            # Step 5: Store in existing memory system with metadata
            confirmation = self.memory.store_memory(
                key=scoped_key,
                value=normalized_value,
                category='semantic'  # Track as semantic memory
            )

            # Step 6: Update user profile
            self._update_user_profile(current_user_id, key, normalized_value)

            # Step 7: Return naturalized response
            return self._naturalize_confirmation(key, normalized_value, current_user_id)

        except OwnershipResolutionNeeded as e:
            return f"I need clarification: {str(e)}"
        except ValueError as e:
            return f"I couldn't process that: {str(e)}"
        except Exception as e:
            logger.error(f"Semantic storage error: {e}")
            return f"I had trouble storing that memory."

    def _extract_value_from_input(self, user_input: str, key: str) -> Optional[str]:
        """Extract the actual value from user input"""
        # Simple approach: extract after key phrase
        patterns = {
            'birthday': r'(?:birthday|born).+?(?:is|on|:)?\s*(.+?)(?:\.|$)',
            'phone': r'(?:phone|mobile|cell).+?(?:is|:)?\s*(.+?)(?:\.|$)',
            'email': r'(?:email|mail).+?(?:is|:)?\s*(.+?)(?:\.|$)',
            'address': r'(?:address|live).+?(?:is|in|:)?\s*(.+?)(?:\.|$)',
            'name': r'(?:my name|call|named|am)\s+(.+?)(?:\.|$)',
            'occupation': r'(?:occupation|job|work).+?(?:is|as|:)?\s*(.+?)(?:\.|$)',
        }

        pattern = patterns.get(key)
        if pattern:
            match = re.search(pattern, user_input.lower(), re.IGNORECASE)
            if match:
                return match.group(1).strip()

        # Fallback: extract everything after "is"
        if ' is ' in user_input.lower():
            parts = user_input.split(' is ', 1)
            if len(parts) > 1:
                return parts[1].strip()

        return None

    # ========================================================================
    # 5. SEMANTIC RECALL (Rule 2)
    # ========================================================================

    def recall_semantic_memory(
        self,
        query: str,
        user_id: str = None,
        confidence_threshold: float = 0.8
    ) -> Dict[str, any]:
        """
        Recall with semantic canonicalization.

        Returns: {
            'found': bool,
            'value': str or None,
            'key': canonical_key,
            'confidence': float,
            'owner': user_id,
            'message': human_readable_response
        }
        """
        if user_id is None:
            user_id = self.current_user_id

        try:
            # Step 1: Canonicalize the query
            canonical_key = self.extract_canonical_key(query)

            if not canonical_key:
                return {
                    'found': False,
                    'message': "I'm not sure what you're asking about.",
                    'value': None,
                }

            # Step 2: Look up scoped memory
            scoped_key = f"{user_id}:{canonical_key}"

            recalled_value = self.memory.recall_memory(scoped_key)

            if recalled_value:
                # Step 3: Naturalize response
                message = self._naturalize_recall(
                    canonical_key, recalled_value, user_id)

                return {
                    'found': True,
                    'value': recalled_value,
                    'key': canonical_key,
                    'confidence': 0.95,
                    'owner': user_id,
                    'message': message,
                }

            # Not found in scoped memory
            return {
                'found': False,
                'value': None,
                'key': canonical_key,
                'confidence': 0.0,
                'owner': user_id,
                'message': f"I don't have that stored.",
            }

        except Exception as e:
            logger.error(f"Semantic recall error: {e}")
            return {
                'found': False,
                'message': "I had trouble recalling that.",
                'value': None,
            }

    # ========================================================================
    # 6. USER PROFILE MANAGEMENT (Rule 7)
    # ========================================================================

    def _load_user_profile(self, user_id: str) -> Dict:
        """Load or initialize user profile"""
        # Structure:
        # {
        #   'identity': {},
        #   'preferences': {},
        #   'personality': {},
        #   'habits': {},
        #   'goals': {},
        # }

        return {
            'user_id': user_id,
            'identity': {},  # birthday, name, phone, etc.
            'preferences': {},  # likes, dislikes
            'personality': {},  # traits
            'habits': {},  # routines
            'goals': {},  # aspirations
            'last_updated': time.time(),
        }

    def _update_user_profile(self, user_id: str, key: str, value: str):
        """Update user profile with new fact"""
        if ':' in key:
            key = key.split(':', 1)[1]

        # Determine category
        if key == 'birthday' or key == 'name':
            category = 'identity'
        elif key.startswith('preferences'):
            category = 'preferences'
        elif key.startswith('personality'):
            category = 'personality'
        elif key.startswith('habits'):
            category = 'habits'
        elif key.startswith('goals'):
            category = 'goals'
        else:
            category = 'identity'

        # Update profile
        if category not in self.user_profile:
            self.user_profile[category] = {}

        self.user_profile[category][key] = {
            'value': value,
            'timestamp': time.time(),
        }

        logger.info(f"Profile updated: {user_id}/{category}/{key} = {value}")

    # ========================================================================
    # 7. RESPONSE NATURALIZATION
    # ========================================================================

    def _naturalize_confirmation(self, key: str, value: str, user_id: str) -> str:
        """Convert structured fact to human-readable confirmation"""
        confirmations = {
            'birthday': f"Got it. I'll remember your birthday is {value}.",
            'phone': f"I'll save your phone number as {value}.",
            'email': f"I'll save your email as {value}.",
            'address': f"I'll remember your address: {value}.",
            'name': f"Nice to meet you, {value}!",
            'occupation': f"Got it, you're a {value}.",
        }

        return confirmations.get(key, f"Got it. I'll remember: {key} = {value}")

    def _naturalize_recall(self, key: str, value: str, user_id: str) -> str:
        """Convert stored fact to natural language response"""
        recalls = {
            'birthday': f"Your birthday is {value}.",
            'phone': f"Your phone number is {value}.",
            'email': f"Your email is {value}.",
            'address': f"Your address is {value}.",
            'name': f"Your name is {value}.",
            'occupation': f"You're a {value}.",
        }

        return recalls.get(key, f"{key}: {value}")

    # ========================================================================
    # 8. TEMPORAL FACT RESOLUTION (Rule 5)
    # ========================================================================

    def resolve_temporal_fact(self, time_phrase: str) -> Dict:
        """
        Convert relative time to absolute timestamp.

        Examples:
        "tomorrow" → {absolute_date: 2026-01-11, original: "tomorrow"}
        "next week" → {absolute_date: 2026-01-17, original: "next week"}
        """
        from datetime import datetime, timedelta

        time_lower = time_phrase.lower().strip()
        today = datetime.now().date()

        temporal_map = {
            'today': today,
            'tomorrow': today + timedelta(days=1),
            'yesterday': today - timedelta(days=1),
            'next week': today + timedelta(weeks=1),
            'next month': today + timedelta(days=30),
            'in 1 day': today + timedelta(days=1),
            'in 2 days': today + timedelta(days=2),
            'in 3 days': today + timedelta(days=3),
            'in 1 week': today + timedelta(weeks=1),
        }

        # Check for exact matches
        if time_lower in temporal_map:
            return {
                'absolute_date': str(temporal_map[time_lower]),
                'original_phrase': time_phrase,
                'is_relative': True,
            }

        # Check for patterns like "in X days"
        match = re.search(r'in (\d+)\s*(day|week|month)', time_lower)
        if match:
            count = int(match.group(1))
            unit = match.group(2)

            if unit == 'day':
                target = today + timedelta(days=count)
            elif unit == 'week':
                target = today + timedelta(weeks=count)
            elif unit == 'month':
                target = today + timedelta(days=count*30)

            return {
                'absolute_date': str(target),
                'original_phrase': time_phrase,
                'is_relative': True,
            }

        # If not relative, assume it's already canonical
        return {
            'absolute_date': time_phrase,
            'original_phrase': time_phrase,
            'is_relative': False,
        }


# ============================================================================
# EXCEPTION TYPES
# ============================================================================

class OwnershipResolutionNeeded(Exception):
    """Raised when pronoun ownership cannot be resolved"""
    pass

# ============================================================================
# TESTING & VERIFICATION
# ============================================================================


def test_semantic_memory():
    """
    Test semantic memory layer.
    Run with: python friday.py --test-semantic
    """
    logger.info("=== SEMANTIC MEMORY TESTS ===")

    # Create dummy memory system
    class DummyMemory:
        def __init__(self):
            self.store = {}

        def store_memory(self, key, value, category):
            self.store[key] = value
            logger.info(f"✓ Stored: {key} = {value}")
            return f"Got it. I'll remember: {key} = {value}"

        def recall_memory(self, key):
            return self.store.get(key)

    memory = DummyMemory()
    semantic = SemanticMemoryManager(memory, "test_user")

    # Test 1: Birthday storage
    logger.info("Test 1: Birthday normalization")
    result = semantic.store_semantic_memory("my birthday is 22nd jan")
    logger.info(f"Result: {result}")
    assert "22 January" in result

    # Test 2: Phone normalization
    logger.info("Test 2: Phone normalization")
    result = semantic.store_semantic_memory("my phone is 9876543210")
    logger.info(f"Result: {result}")
    assert "9876543210" in result

    # Test 3: Recall
    logger.info("Test 3: Semantic recall")
    result = semantic.recall_semantic_memory("when is my birthday")
    logger.info(f"Result: {result}")
    assert result['found'] and "22 January" in result['message']

    logger.info("✓ All semantic memory tests passed!")


if __name__ == "__main__":
    # For testing
    if "--test-semantic" in sys.argv:
        test_semantic_memory()
        sys.exit(0)


# ============================================================================
# Conversation Manager - Follow-up Understanding
# ============================================================================

class ConversationManager:
    """Understand human conversation patterns"""

    def __init__(self, memory_system):
        self.memory = memory_system
        self.last_topic = None
        self.last_problem = None

        self.continuation_phrases = [
            'tell me more', 'more', 'continue', 'go on', 'yes', 'ok', 'sure',
            'what about', 'how about', 'what else', 'anything else'
        ]

        self.negation_phrases = [
            'no', 'nope', 'wrong', 'that\'s wrong', 'incorrect', 'not right',
            'undo that', 'forget that'
        ]

    def detect_followup(self, user_input: str) -> Dict:
        """Detect type of follow-up"""
        user_lower = user_input.lower().strip()

        # Continuation
        if any(phrase in user_lower for phrase in self.continuation_phrases):
            return {'type': 'continuation', 'confidence': 0.95, 'use_last_topic': True}

        # Negation/Correction
        if any(phrase in user_lower for phrase in self.negation_phrases):
            return {'type': 'correction', 'confidence': 0.90, 'use_last_topic': True}

        return {'type': 'new_topic', 'confidence': 0.0}

    def resolve_followup(self, user_input: str, followup_info: Dict) -> Optional[str]:
        """Resolve follow-up to actual topic"""
        if followup_info['type'] in ['continuation', 'correction']:
            return self.last_topic
        return None

    def update_state(self, intent: str, topic: str = None) -> None:
        """Update conversation state"""
        if intent in ['knowledge', 'problem']:
            if topic:
                self.last_topic = topic
                self.last_problem = topic


# ============================================================================
# Intent Engine - Context-Aware
# ============================================================================

@dataclass
class IntentResult:
    intent: str
    confidence: float
    entities: Dict
    requires_clarification: bool
    reasoning: str
    is_explicit: bool = False


class IntentEngine:
    """Context-aware intent detection"""

    def __init__(self, memory_system, conversation_manager):
        self.memory = memory_system
        self.conversation = conversation_manager

        self.strong_keywords = {
            'control': ['shut down', 'shut it', 'exit', 'quit', 'bye', 'goodbye'],
            'memory_store': ['remember', 'add to important', 'note that'],
        }

        self.memory_recall_phrases = [
            'when is my', 'what is my', "what's my", 'tell me my',
        ]

        self.explicit_knowledge_markers = [
            'tell me about', 'explain', 'what is', 'what are',
            'define', 'how does', 'how do', 'why is', 'why does'
        ]

    def infer_intent(self, user_input: str) -> IntentResult:
        """FIX: Correct priority with context"""
        user_lower = user_input.lower().strip()

        # NEW: Detect if this is a follow-up
        followup_info = self.conversation.detect_followup(user_input)
        if followup_info['type'] != 'new_topic' and self.conversation.last_topic:
            return IntentResult(
                intent='knowledge',
                confidence=0.95,
                entities={'topic': self.conversation.last_topic,
                          'is_followup': True},
                requires_clarification=False,
                reasoning=f"Follow-up: {followup_info['type']}",
                is_explicit=True
            )

        # PRIORITY 1: Memory STORE
        store_result = self._detect_memory_store(user_lower)
        if store_result.confidence >= 0.80:
            return store_result

        # PRIORITY 2: Control
        strong_result = self._check_strong_keywords(user_lower)
        if strong_result:
            return strong_result

        # PRIORITY 3: Memory RECALL
        recall_result = self._detect_memory_recall(user_lower)
        if recall_result.confidence >= 0.80:
            return recall_result

        # PRIORITY 4: Math
        math_result = self._detect_math_pattern(user_lower)
        if math_result.confidence >= 0.80:
            return math_result

        # PRIORITY 5: Knowledge
        knowledge_result = self._infer_knowledge_intent(user_lower)
        return knowledge_result

    def _detect_memory_store(self, user_lower: str) -> IntentResult:
        """Memory store detection"""
        store_keywords = ['remember', 'add to important', 'note that']

        if any(kw in user_lower for kw in store_keywords):
            info = user_lower
            for kw in store_keywords:
                if kw in info:
                    info = info.replace(kw, '').strip()
                    break

            key, value = self._normalize_fact(info)

            return IntentResult(
                intent='memory_store',
                confidence=0.95,
                entities={'key': key, 'value': value},
                requires_clarification=False,
                reasoning="Memory store detected",
                is_explicit=True
            )

        return IntentResult('unknown', 0.0, {}, False, "", False)

    def _detect_memory_recall(self, user_lower: str) -> IntentResult:
        """Memory recall detection"""
        if any(phrase in user_lower for phrase in self.memory_recall_phrases):
            topic = user_lower
            for phrase in self.memory_recall_phrases:
                if phrase in topic:
                    topic = topic.replace(phrase, '').strip()
                    break

            return IntentResult(
                intent='memory_recall',
                confidence=0.95,
                entities={'query': topic},
                requires_clarification=False,
                reasoning="Memory recall (explicit phrase)",
                is_explicit=True
            )

        return IntentResult('unknown', 0.0, {}, False, "", False)

    def _check_strong_keywords(self, user_lower: str) -> Optional[IntentResult]:
        """Check strong control keywords"""
        for intent, keywords in self.strong_keywords.items():
            if any(kw in user_lower for kw in keywords):
                return IntentResult(
                    intent=intent,
                    confidence=0.99,
                    entities={},
                    requires_clarification=False,
                    reasoning=f"Strong keyword: {intent}",
                    is_explicit=True
                )
        return None

    def _detect_math_pattern(self, user_lower: str) -> IntentResult:
        """Detect math expressions"""
        has_digits = bool(re.search(r'\d', user_lower))
        has_operators = bool(re.search(r'[\+\-\*\/\%\=\^]', user_lower))

        score = 0.95 if (has_digits and has_operators) else 0.0

        return IntentResult(
            intent='math' if score > 0 else 'unknown',
            confidence=score,
            entities={'expression': user_lower} if score > 0 else {},
            requires_clarification=False,
            reasoning="Math pattern" if score > 0 else "",
            is_explicit=score >= 0.85
        )

    def _infer_knowledge_intent(self, user_lower: str) -> IntentResult:
        """Knowledge detection - explicit beats implicit"""
        has_explicit_marker = any(
            marker in user_lower for marker in self.explicit_knowledge_markers)

        if has_explicit_marker:
            topic = user_lower
            for marker in self.explicit_knowledge_markers:
                if marker in topic:
                    topic = topic.replace(marker, '').strip()
                    break

            # FIX: EXECUTE IMMEDIATELY, NO CONFIRMATION
            return IntentResult(
                intent='knowledge',
                confidence=0.95,
                entities={'topic': topic},
                requires_clarification=False,
                reasoning=f"Explicit knowledge: {topic}",
                is_explicit=True
            )

        # Implicit knowledge
        word_count = len(user_lower.split())
        if word_count >= 2 and not any(op in user_lower for op in ['=', '+', '-', '*', '/']):
            return IntentResult(
                intent='knowledge',
                confidence=0.75,
                entities={'topic': user_lower},
                requires_clarification=False,
                reasoning="Compound noun topic",
                is_explicit=False
            )

        return IntentResult(
            intent='conversation',
            confidence=0.5,
            entities={},
            requires_clarification=False,
            reasoning="No strong intent",
            is_explicit=False
        )

    def _normalize_fact(self, raw_info: str) -> Tuple[str, str]:
        """Normalize to structured fact"""
        raw_lower = raw_info.lower()

        if 'birthday' in raw_lower:
            match = re.search(
                r'(\d{1,2})\s*(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)', raw_lower)
            if match:
                day = match.group(1).zfill(2)
                months = {
                    'jan': 'January', 'feb': 'February', 'mar': 'March',
                    'apr': 'April', 'may': 'May', 'jun': 'June',
                    'jul': 'July', 'aug': 'August', 'sep': 'September',
                    'oct': 'October', 'nov': 'November', 'dec': 'December'
                }
                month = months.get(match.group(2)[:3], match.group(2))
                return ('birthday', f"{day} {month}")

        if 'phone' in raw_lower:
            digits = re.sub(r'\D', '', raw_info)
            if len(digits) >= 10:
                return ('phone', digits[-10:])

        parts = raw_info.split(maxsplit=1)
        key = parts[0] if parts else 'note'
        value = parts[1] if len(parts) > 1 else raw_info

        return (key.lower(), value)

# ============================================================================
# Brain Engine - Reasoning Pipeline
# ============================================================================


class BrainEngine:
    """Think → Plan → Execute → Reflect (with semantic memory)"""

    def __init__(self, memory_system, conversation_manager, client, user_id: str = "user_default"):
        self.memory = memory_system
        self.conversation = conversation_manager
        self.client = client
        self.intent_engine = IntentEngine(memory_system, conversation_manager)
        self.semantic = SemanticMemoryManager(memory_system, user_id)

    # ============================================================
    # 🔥 COMPLEXITY DETECTION
    # ============================================================
    def is_complex(self, user_input: str) -> bool:
        keywords = [
            "build", "create", "make", "develop",
            "project", "system", "app", "program",
            "analyze", "step by step", "how to"
        ]
        return any(k in user_input.lower() for k in keywords)

    # ============================================================
    # 🔥 PLANNING ENGINE (SAFE VERSION)
    # ============================================================
    def plan(self, user_input: str) -> list:
        try:
            from openai import OpenAI
            import os
            import json
            import re

            client = create_openai_client()

            prompt = f"""
You are an AI planner.

Break the user request into clear actionable steps.

User Request:
{user_input}

Rules:
- Output ONLY valid JSON
- No explanation
- Keep steps simple

Example:
[
  {{"step": 1, "action": "Understand the problem"}},
  {{"step": 2, "action": "Choose approach"}},
  {{"step": 3, "action": "Generate solution"}}
]
"""

            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3
            )

            content = response.choices[0].message.content.strip()

            # 🛡️ SAFE JSON PARSING
            try:
                return json.loads(content)
            except:
                match = re.search(r'\[.*\]', content, re.DOTALL)
                if match:
                    return json.loads(match.group())
                else:
                    return []

        except Exception as e:
            print("Planning error:", e)
            return []
 # ============================================================
    # 🔥 NEW: TOOL DECISION ENGINE (LAYER 2)
    # ============================================================

    def decide_tools(self, user_input: str) -> dict:
        try:
            from openai import OpenAI
            import os
            import json

            client = create_openai_client()

            prompt = f"""
You are an AI decision engine.

Decide what tools are needed to solve the user request.

Available tools:
- math → calculations
- knowledge → explanations / general info
- code → programming tasks
- memory → store or recall user data

User Request:
{user_input}

Rules:
- Output ONLY valid JSON
- No explanation

Example:
{{
  "tools": ["math", "knowledge"]
}}
"""

            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2
            )

            content = response.choices[0].message.content.strip()

            import re
            import json

            try:
                return json.loads(content)

            except Exception:
                match = re.search(r'\{.*?\}', content, re.DOTALL)

                if match:
                    try:
                        return json.loads(match.group())
                    except:
                        pass

                return {"tools": ["knowledge"]}

        except Exception as e:
            print("Tool decision error:", e)
            return {"tools": ["knowledge"]}

    # ============================================================
    # 🧠 CORE THINK FUNCTION
    # ============================================================
    def think(self, user_input: str) -> Dict:
        """Enhanced reasoning with semantic memory + planning"""

        text = user_input.lower()

        # ========================================================
        # 🧠 1. SEMANTIC MEMORY STORE
        # ========================================================
        if 'remember' in text:
            confirmation = self.semantic.store_semantic_memory(user_input)
            return {
                'text': confirmation,
                'intent': 'memory_store',
                'confidence': 0.95,
                'needs_followup': False,
                'execute_immediately': True,
                'is_explicit': True,
            }

        # ========================================================
        # 🧠 2. SEMANTIC MEMORY RECALL
        # ========================================================
        recall_keywords = ['when is', "what's my",
                           'my', 'birthday', 'phone', 'email']

        if any(kw in text for kw in recall_keywords):
            result = self.semantic.recall_semantic_memory(user_input)

            if result['found']:
                return {
                    'text': result['message'],
                    'intent': 'memory_recall',
                    'confidence': result['confidence'],
                    'needs_followup': False,
                    'execute_immediately': True,
                    'is_explicit': True,
                }

        # ========================================================
        # 🔥 3. PLANNING LAYER
        # ========================================================
        if self.is_complex(user_input):

            steps = self.plan(user_input)

            # ✅ FAIL-SAFE: if planning fails → fallback
            if steps:
                return {
                    'text': f"I've created a plan with {len(steps)} steps. Executing...",
                    'intent': 'multi_step',
                    'steps': steps,
                    'confidence': 0.95,
                    'needs_followup': False,
                    'execute_immediately': True,
                    'is_explicit': True,
                }
        # ========================================================
        # 🔥 4. TOOL DECISION LAYER (LAYER 2)
        # ========================================================
        tool_decision = self.decide_tools(user_input)

        tools = tool_decision.get("tools", [])

        # ✅ Only trigger if meaningful tools detected
        if tools and not self.is_complex(user_input):
            return {
                'text': "Analyzing and selecting tools...",
                'intent': 'tool_execution',
                'tools': tools,
                'confidence': 0.9,
                'needs_followup': False,
                'execute_immediately': True,
                'is_explicit': True,
            }

        # ========================================================
        # 🧠 5. EXISTING INTENT ENGINE (UNCHANGED)
        # ========================================================
        intent_result = self.intent_engine.infer_intent(user_input)

        response = {
            'text': '',
            'intent': intent_result.intent,
            'confidence': intent_result.confidence,
            'needs_followup': intent_result.requires_clarification and not intent_result.is_explicit,
            'execute_immediately': intent_result.is_explicit,
            'is_explicit': intent_result.is_explicit,
        }

        # ========================================================
        # 💬 6. SMALL TALK HANDLING
        # ========================================================
        if response['intent'] in ['knowledge', 'conversation']:
            small_talk_reply = self.handle_small_talk(user_input)

            if small_talk_reply:
                response['text'] = small_talk_reply
                response['execute_immediately'] = True

        return response

    # ============================================================
    # 💬 SMALL TALK HANDLER
    # ============================================================
    def handle_small_talk(self, user_input: str) -> str:
        text = user_input.lower()

        if "how are you" in text:
            return "I’m doing well, sir. Ready whenever you are."

        if "hey" in text or "hello" in text:
            return "Hello, sir. What are we working on today?"

        if "bye" in text or "bey" in text:
            return "Catch you later, sir."

        return ""

# ============================================================================
# INTEGRATION WITH EXISTING BRAIN ENGINE
# ============================================================================


class EnhancedBrainEngine(BrainEngine):
    """
    BrainEngine with semantic layer.
    This is additive, not replacing.
    """

    def __init__(self, memory_system, conversation_manager, client, user_id: str = "user_default"):
        super().__init__(memory_system, conversation_manager, client, user_id)
        self.semantic = SemanticMemoryManager(memory_system, user_id)

    def think(self, user_input: str) -> Dict:
        """
        Enhanced thinking with semantic memory.
        Falls back to parent if not semantic memory intent.
        """
        # First, try semantic memory interpretation
        if 'remember' in user_input.lower():
            # Semantic storage intent
            confirmation = self.semantic.store_semantic_memory(user_input)
            return {
                'text': confirmation,
                'intent': 'memory_store',
                'confidence': 0.95,
                'needs_followup': False,
                'execute_immediately': True,
                'is_explicit': True,
            }

        # Check for recall patterns that need semantic interpretation
        recall_keywords = ['when is', "what's my",
                           'my', 'birthday', 'phone', 'email']
        if any(kw in user_input.lower() for kw in recall_keywords):
            result = self.semantic.recall_semantic_memory(user_input)

            if result['found']:
                return {
                    'text': result['message'],
                    'intent': 'memory_recall',
                    'confidence': result['confidence'],
                    'needs_followup': False,
                    'execute_immediately': True,
                    'is_explicit': True,
                }

        # Otherwise, use parent's logic
        return super().think(user_input)


# ============================================================================
# Knowledge Engine - Clean Output
# ============================================================================

class KnowledgeEngine:
    """FIX: Clean output, no citations"""

    def __init__(self):
        self.perplexity_client = None
        self.setup_perplexity()

    def setup_perplexity(self):
        api_key = config.perplexity_api_key
        if api_key and PERPLEXITY_AVAILABLE:
            try:
                self.perplexity_client = OpenAI(
                    api_key=api_key,
                    base_url="https://api.perplexity.ai"
                )
                logger.info("✓ Perplexity ready")
            except Exception as e:
                logger.error(f"Perplexity setup error: {e}")

    def clean_text(self, text: str) -> str:
        """FIX: Strip citations"""
        text = re.sub(r'\[\d+(?:,\s*\d+)*\]', '', text)
        text = re.sub(r'\s+', ' ', text).strip()
        return text

    def get_summary(self, topic: str) -> str:
        """Get knowledge with clean output"""
        if self.perplexity_client:
            try:
                response = self.perplexity_client.chat.completions.create(
                    model="sonar-pro",
                    messages=[
                        {"role": "system", "content": "Provide clear, concise explanations in 40-60 words. No citations needed."},
                        {"role": "user", "content": f"Explain {topic} in 40-60 words"}
                    ],
                    max_tokens=100,
                    temperature=0.7
                )
                raw = response.choices[0].message.content.strip()
                return self.clean_text(raw)
            except Exception as e:
                logger.error(f"Perplexity error: {e}")
                return self.get_wikipedia_summary(topic)
        else:
            return self.get_wikipedia_summary(topic)

    def get_wikipedia_summary(self, topic: str) -> str:
        """Fallback to Wikipedia"""
        try:
            url = "https://en.wikipedia.org/api/rest_v1/page/summary/"
            res = requests.get(url + quote_plus(topic), timeout=10)
            if res.status_code == 200:
                data = res.json()
                extract = data.get('extract', '')
                if extract:
                    words = extract.split()[:60]
                    summary = ' '.join(words)
                    if len(extract.split()) > 60:
                        summary += "..."
                    return self.clean_text(summary)
            return f"Couldn't find info about {topic}."
        except Exception as e:
            logger.error(f"Wikipedia error: {e}")
            return f"I had trouble finding info about {topic}."


# ============================================================================
# Math Engine
# ============================================================================

class MathEngine:
    def __init__(self):
        self.safe_dict = {
            '__builtins__': {},
            'abs': abs, 'round': round, 'min': min, 'max': max, 'sum': sum,
            'pow': pow, 'pi': math.pi, 'e': math.e,
            'sqrt': math.sqrt, 'log': math.log, 'exp': math.exp,
        }

    def calculate(self, expression: str) -> Optional[str]:
        try:
            expr = expression.lower().strip()
            for word in ['calculate', 'compute', 'what is', 'solve', '?']:
                expr = expr.replace(word, '')

            replacements = {
                ' plus ': '+', ' minus ': '-', ' times ': '*',
                ' divided by ': '/', ' divided ': '/'
            }
            for word, op in replacements.items():
                expr = expr.replace(word, op)

            expr = re.sub(r'\s+', '', expr)

            if not re.match(r'^[\d\.\+\-\*\/\%\(\)eE]+$', expr):
                raise ValueError("Invalid characters")

            result = eval(expr, self.safe_dict)

            if isinstance(result, float):
                return str(int(result)) if result.is_integer() else str(round(result, 6))
            return str(result)
        except Exception as e:
            logger.error(f"Math error: {e}")
            return None


# ============================================================================
# Voice Engine
# ============================================================================

class VoiceEngine:
    """FIX: Clean output before voice"""

    def __init__(self):
        self.client = None
        self.voice_id = "EXAVITQu4vr4xnSDxMaL"
        self.model_id = "eleven_monolingual_v1"
        self.speaking = False
        self.setup_elevenlabs()

    def setup_elevenlabs(self):
        api_key = config.elevenlabs_api_key
        if api_key and ELEVENLABS_AVAILABLE:
            try:
                self.client = ElevenLabs(api_key=api_key)
                logger.info("✓ ElevenLabs ready")
            except Exception as e:
                logger.error(f"ElevenLabs error: {e}")

    def clean_for_voice(self, text: str) -> str:
        """FIX: Clean citations and meta before voice"""
        text = re.sub(r'\[\d+(?:,\s*\d+)*\]', '', text)
        text = re.sub(r'\*\*(.*?)\*\*', r'\1', text)
        text = re.sub(r'\*(.*?)\*', r'\1', text)
        text = re.sub(r'\s+', ' ', text).strip()
        return text

    def speak(self, text):
        """Speak with cleaned text"""
        if not text or self.speaking:
            return

        text = self.clean_for_voice(text)

        self.speaking = True
        try:
            if self.client:
                try:
                    audio = self.client.text_to_speech.convert(
                        text=text,
                        voice_id=self.voice_id,
                        model_id=self.model_id,
                        voice_settings=VoiceSettings(
                            stability=0.65, similarity_boost=0.8)
                    )
                    audio_path = "/tmp/friday_audio.mp3"
                    with open(audio_path, "wb") as f:
                        for chunk in audio:
                            if chunk:
                                f.write(chunk)
                    subprocess.run(["afplay", audio_path],
                                   stderr=subprocess.DEVNULL)
                except:
                    self.speak_mac(text)
            else:
                self.speak_mac(text)
        finally:
            self.speaking = False

    def speak_mac(self, text):
        try:
            subprocess.run(['say', '-v', 'Samantha', text],
                           stderr=subprocess.DEVNULL)
        except:
            pass


# ============================================================================
# Voice Listener
# ============================================================================

class VoiceListener:
    def __init__(self, callback):
        self.callback = callback
        self.recognizer = sr.Recognizer()
        self.microphone = sr.Microphone()
        self.listening = False
        self.text_input_active = False
        self.setup()

    def setup(self):
        try:
            with self.microphone as m:
                self.recognizer.adjust_for_ambient_noise(m, duration=1)
            self.recognizer.energy_threshold = 350
        except:
            pass

    def start(self):
        if self.listening:
            return
        self.listening = True
        threading.Thread(target=self.listen_loop, daemon=True).start()

    def listen_loop(self):
        while self.listening:
            if self.text_input_active:
                time.sleep(0.1)
                continue

            try:
                with self.microphone as source:
                    audio = self.recognizer.listen(
                        source, timeout=30, phrase_time_limit=8)
                try:
                    text = self.recognizer.recognize_google(
                        audio, language='en-IN').lower().strip()
                    if text and len(text) > 1 and 'friday' not in text:
                        self.callback(text)
                except:
                    pass
            except:
                continue

    def stop(self):
        self.listening = False

    def set_text_input_active(self, active: bool):
        self.text_input_active = active


# ============================================================================
# Main Friday Assistant
# ============================================================================

class FridayAssistant:
    """Production-grade conversational AI"""

    def __init__(self, name: str = "Mr. Ryan"):
        self.name = name
        self.memory = AdvancedMemorySystem()
        self.conversation = ConversationManager(self.memory)
        self.client = create_openai_client()
        self.brain = EnhancedBrainEngine(
            self.memory, self.conversation, self.client)
        self.knowledge = KnowledgeEngine()
        self.math = MathEngine()
        self.voice = VoiceEngine()
        self.listener = None
        self.running = False
        logger.info(f"✓ Friday V4.1 initialized for {name}")
        # =============================
        # 💾 DATABASE MEMORY INIT
        # ==============================
        import sqlite3

        self.conn = sqlite3.connect(os.path.expanduser(config.conversation_db_path))
        self.cursor = self.conn.cursor()

        self.cursor.execute("""
        CREATE TABLE IF NOT EXISTS memory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_input TEXT,
            ai_response TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """)

        self.conn.commit()

        # # ==============================
        # # 🤖 OPENAI CLIENT (GLOBAL)
        # # ==============================
        # from openai import OpenAI
        # import os

        # self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    def greet(self):
        greeting = "Hello, sir. I’m ready. What are we working on?"
        print(greeting)
        self.voice.speak(greeting)

    def process_command(self, cmd):
        if not cmd or not cmd.strip():
            return

        cmd = cmd.strip()
        logger.info(f"Input: {cmd}")

        if self.listener:
            self.listener.set_text_input_active(True)

        try:
            brain_response = self.brain.think(cmd.lower())

            logger.info(
                f"Decision: intent={brain_response['intent']}, execute={brain_response['execute_immediately']}")

            if brain_response.get("text") and brain_response['execute_immediately']:
                print(f"Friday: {brain_response['text']}")
                self.voice.speak(brain_response['text'])
                return

            if brain_response['needs_followup']:
                print(f"Friday: {brain_response['text']}")
                self.voice.speak(brain_response['text'])

                if self.listener:
                    self.listener.set_text_input_active(False)

                print("You: ", end="")
                try:
                    clarification = input().strip().lower()
                    if clarification:
                        self.process_command(clarification)
                except:
                    pass
                return

            outcome = self._execute_plan(brain_response, cmd.lower())

        finally:
            if self.listener:
                self.listener.set_text_input_active(False)

    def _execute_plan(self, brain_response: Dict, cmd: str) -> str:
        """Execute with clean output"""
        intent = brain_response['intent']
        # ============================================================
        # 🔥 MULTI-STEP EXECUTION (SAFE ADD)
        # ============================================================
        if intent == "multi_step":

            steps = brain_response.get("steps", [])

            print("Friday: Executing plan...")

            results = []

            for step in steps:
                action = step.get("action", "")

                print(f"→ Step {step.get('step')}: {action}")

                result = self._execute_single_step(action)
                results.append(result)

            final_output = "\n".join(results) if results else "Task completed."

            print(f"Friday: {final_output}")
            self.voice.speak(final_output)

            return final_output
        # ============================================================
        # 🔥 TOOL EXECUTION (ADD HERE ✅)
        # ============================================================
        elif intent == "tool_execution":

            tools = brain_response.get("tools", [])

            print(f"Friday: Using tools: {tools}")

            results = []

            for tool in tools:
                if tool == "math":
                    result = self.math.calculate(cmd)
                    results.append(f"Math Result: {result}")

                elif tool == "knowledge":
                    result = self.knowledge.get_summary(cmd)
                    results.append(result)

                elif tool == "code":
                    from openai import OpenAI
                    import os

                    client = create_openai_client()

                    response = client.chat.completions.create(
                        model="gpt-4o-mini",
                        messages=[
                            {"role": "user", "content": f"Write Python code for: {cmd}"}
                        ]
                    )

                    code = response.choices[0].message.content
                    results.append(code)

                elif tool == "memory":
                    results.append("Memory tool handled separately")

            final = "\n".join(results)

            # 🧠 SECOND PASS (AI thinking)
            from openai import OpenAI
            import os

            client = create_openai_client()

            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system",
                        "content": "Summarize and refine the result clearly."},
                    {"role": "user", "content": final}
                ]
            )

            final_output = response.choices[0].message.content

            print(f"Friday: {final_output}")
            self.voice.speak(final_output)

            return final_output

        if intent == 'memory_recall':
            result = brain_response['text']
            print(f"Friday: {result}")
            self.voice.speak(result)
            return result

        elif intent == 'memory_store':
            if '[EXEC_STORE]' in brain_response['text']:
                parts = brain_response['text'].replace(
                    '[EXEC_STORE]', '').split('||')
                key = parts[0] if len(parts) > 0 else 'note'
                value = parts[1] if len(parts) > 1 else ''
                response = self.memory.store_memory(key, value)
                print(f"Friday: {response}")
                self.voice.speak(response)
                return response

        elif intent == 'knowledge':

            from datetime import datetime, timedelta
            import pytz
            import os
            from openai import OpenAI

            cmd_lower = cmd.lower()

            # ==============================
            # 🧠 CONTEXT (SESSION MEMORY)
            # ==============================
            if not hasattr(self, "context"):
                self.context = {
                    "last_timezone": None,
                    "last_query": None
                }

            # ==============================
            # 🌍 STEP 1: SMART SHORT NAME HANDLING
            # ==============================
            special_map = {
                "usa": "US",
                "us": "US",
                "america": "US",
                "uk": "GB",
                "britain": "GB",
                "uae": "AE"
            }

            timezone = None

            # ==============================
            # STEP 2: CHECK SPECIAL NAMES
            # ==============================
            for key, code in special_map.items():
                if key in cmd_lower:
                    tz_list = pytz.country_timezones.get(code)
                    if tz_list:
                        timezone = pytz.timezone(tz_list[0])
                        break

            # ==============================
            # STEP 3: GLOBAL COUNTRY DETECTION
            # ==============================
            if timezone is None:
                for code, name in pytz.country_names.items():
                    if name.lower() in cmd_lower:
                        tz_list = pytz.country_timezones.get(code)
                        if tz_list:
                            timezone = pytz.timezone(tz_list[0])
                            break

            # ==============================
            # STEP 4: CITY / TIMEZONE MATCH
            # ==============================
            if timezone is None:
                words = cmd_lower.split()
                ignore = {
                    "what", "is", "the", "time", "date",
                    "in", "now", "right", "current", "tell", "me"
                }

                keywords = [w for w in words if w not in ignore]

                for tz in pytz.all_timezones:
                    tz_lower = tz.lower()
                    for word in keywords:
                        if word in tz_lower:
                            timezone = pytz.timezone(tz)
                            break
                    if timezone:
                        break

            # ==============================
            # STEP 5: CONTEXT MEMORY
            # ==============================
            if timezone:
                self.context["last_timezone"] = timezone
            else:
                timezone = self.context.get("last_timezone")

            if timezone is None:
                timezone = pytz.timezone("Asia/Kolkata")

            # ==============================
            # ⏰ TIME ENGINE
            # ==============================
            now = datetime.now(timezone)

            if "tomorrow" in cmd_lower:
                now += timedelta(days=1)
            elif "yesterday" in cmd_lower:
                now -= timedelta(days=1)

            wants_time = any(w in cmd_lower for w in ["time", "clock"])
            wants_date = any(w in cmd_lower for w in [
                             "date", "day", "today", "tomorrow"])

            # ==============================
            # TIME / DATE RESPONSE
            # ==============================
            if wants_time or wants_date:

                if wants_time and wants_date:
                    response = now.strftime(
                        "Today is %A, %d %B %Y and the time is %I:%M %p"
                    )

                elif wants_time:
                    response = now.strftime("The time now is %I:%M %p")

                else:
                    response = now.strftime("Today is %A, %d %B %Y")

                print(f"Friday: {response}")
                self.voice.speak(response)
                return response

            # ==============================
            # 💾 FETCH LAST 5 MEMORY
            # ==============================
            self.cursor.execute("""
                SELECT user_input, ai_response
                FROM memory
                ORDER BY id DESC
                LIMIT 5
            """)

            past_data = self.cursor.fetchall()

            memory_context = ""
            for user_q, ai_a in reversed(past_data):
                memory_context += f"User: {user_q}\nAssistant: {ai_a}\n"

            # ==============================
            # 🤖 OPENAI INTELLIGENCE
            # ==============================
            try:
                print("Friday: Thinking...")

                client = create_openai_client()

                system_prompt = f"""
You are Friday, a highly advanced AI assistant.

Capabilities:
- Answer any question intelligently
- Use memory of past conversations
- Understand vague questions
- Be concise but insightful

Conversation Memory:
{memory_context}

Current Context:
Last query: {self.context["last_query"]}
Timezone: {self.context["last_timezone"]}
"""

                completion = self.client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": cmd}
                    ],
                    temperature=0.6,
                    max_tokens=400
                )

                ai_response = completion.choices[0].message.content.strip()

                # ==============================
                # 💾 STORE MEMORY
                # ==============================
                self.cursor.execute("""
                    INSERT INTO memory (user_input, ai_response)
                    VALUES (?, ?)
                """, (cmd, ai_response))

                self.conn.commit()

                self.context["last_query"] = cmd

                print(f"Friday: {ai_response}")
                self.voice.speak(ai_response)

                return ai_response

            except Exception as e:
                print(f"OpenAI Error: {e}")

            # ==============================
            # ⚠️ FALLBACK
            # ==============================
            fallback = "I didn’t quite catch that, sir. Say it once more, and I’ll try again."
            print(f"Friday: {fallback}")
            self.voice.speak(fallback)
            return fallback

            # # 📚 EXISTING KNOWLEDGE SYSTEM
            # if '[EXEC_KNOWLEDGE]' in brain_response['text']:
            #     topic = brain_response['text'].replace(
            #         '[EXEC_KNOWLEDGE]', '').strip()
            #     print(f"Explaining: {topic}...")
            #     summary = self.knowledge.get_summary(topic)
            #     print(f"Friday: {summary}")
            #     self.voice.speak(summary)

            #     offer = "If you'd like to know more, just let me know."
            #     print(f"Friday: {offer}")
            #     self.voice.speak(offer)
            #     return summary

            # # 📚 EXISTING KNOWLEDGE SYSTEM
            # if '[EXEC_KNOWLEDGE]' in brain_response['text']:
            #     topic = brain_response['text'].replace(
            #         '[EXEC_KNOWLEDGE]', '').strip()
            #     print(f"Explaining: {topic}...")
            #     summary = self.knowledge.get_summary(topic)
            #     print(f"Friday: {summary}")
            #     self.voice.speak(summary)

            #     offer = "If you'd like to know more, just let me know."
            #     print(f"Friday: {offer}")
            #     self.voice.speak(offer)
            #     return summary

        elif intent == 'math':
            if '[EXEC_MATH]' in brain_response['text']:
                expr = brain_response['text'].replace(
                    '[EXEC_MATH]', '').strip()
                result = self.math.calculate(expr)
                response = f"That's {result}" if result else "I couldn't calculate that"
                print(f"Friday: {response}")
                self.voice.speak(response)
                return response

        elif intent == 'control':
            if 'shut' in cmd or 'exit' in cmd or 'bye' in cmd:
                msg = f"Catch you later, {self.name}!"
                print(msg)
                self.voice.speak(msg)
                self.running = False
                return msg

        return "Executed"

    # ============================================================
    # 🔥 NEW STEP EXECUTOR (ADDED ONLY)
    # ============================================================
    def _execute_single_step(self, action: str) -> str:

        action_lower = action.lower()

        if "calculate" in action_lower:
            result = self.math.calculate(action)
            return f"Result: {result}"

        elif "explain" in action_lower or "search" in action_lower:
            return self.knowledge.get_summary(action)

        elif "code" in action_lower or "build" in action_lower:
            return "Code generation step (next upgrade)"

        return f"Processed: {action}"

    def run(self):
        self.running = True
        self.greet()

        self.listener = VoiceListener(self.process_command)
        self.listener.start()

        try:
            while self.running:
                try:
                    user_input = input("You: ").strip()
                    if user_input:
                        self.process_command(user_input)
                except KeyboardInterrupt:
                    break
                except Exception as e:
                    logger.error(f"Error: {e}")
        finally:
            if self.listener:
                self.listener.stop()


# ============================================================================
# Main Entry
# ============================================================================

if __name__ == "__main__":
    friday = FridayAssistant(name="Mr. Ryan")
    try:
        friday.run()
    except KeyboardInterrupt:
        print("Goodbye!")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Fatal: {e}")
        sys.exit(1)
