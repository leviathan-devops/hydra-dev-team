#!/usr/bin/env python3
"""
Strategic Forgetting v2.9 for Leviathan Super-Brain
======================================================
Advanced memory management with session-aware decay, smart morning predictions,
and intelligent tier management.

Features:
  1. Session-aware decay (active/passive/sleep modes)
  2. Smart morning prediction (exempt memories from decay)
  3. Hourly decay cycles (5-minute run interval)
  4. Tier promotion/demotion (hot/warm/cold)
  5. Per-agent transactions and atomicity
  6. Integration with T2-Auditor daemon
  7. /dmm Discord slash command for stats

Author: Leviathan DevOps v2.9
Date: 2026-03-02
"""

import sqlite3
import json
import os
import logging
import threading
import time
from datetime import datetime, timedelta, timezone
from collections import OrderedDict

# ──────────────────────────────────────────────
# Configuration
# ──────────────────────────────────────────────
DB_PATH = os.environ.get("SUPER_BRAIN_DB_PATH", "/data/hydra-brain.db")
CYCLE_INTERVAL = int(os.environ.get("DMM_CYCLE_SECONDS", "300"))  # 5 minutes
LOG_LEVEL = os.environ.get("DMM_LOG_LEVEL", "INFO")

# Decay Configuration (Hourly rates)
BASE_DECAY_RATE = 0.05  # 5% per hour during active sessions
PASSIVE_DECAY_RATE = 0.01  # 1% per hour (no messages 45-90 min)
SLEEP_DECAY_RATE = 0.001  # 0.1% per hour (no messages 90+ min)
ARCH_DECISION_DECAY_RATE = 0.01  # 1% per hour regardless of session state

# Session Timeouts
ACTIVE_SESSION_MINUTES = 45  # User messages within this → active mode
PASSIVE_SESSION_MINUTES = 90  # User messages within this → passive mode
# Beyond 90 min → sleep mode

# Tier Configuration
DEFAULT_QUOTA_PER_AGENT = 10000
MAX_HOT_MEMORIES = 100
MAX_WARM_MEMORIES = 5000
COLD_PRUNE_DAYS = 30

# Promotion/Demotion Thresholds
ACCESS_PROMOTE_THRESHOLD = 5  # warm→hot when access_count >= this
ACCESS_DEMOTE_THRESHOLD_DAYS = 7  # hot→warm after X days without access
COLD_CONFIDENCE_THRESHOLD = 0.2  # warm→cold when confidence < this

# ──────────────────────────────────────────────
# Logging
# ──────────────────────────────────────────────
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s [DMM-V2.9] %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("memory_manager_v2")


# ══════════════════════════════════════════════
# STRATEGIC FORGETTING MEMORY MANAGER V2.9
# ══════════════════════════════════════════════

class StrategicMemoryManager:
    """
    Advanced memory management with session-aware decay and smart predictions.

    Architecture:
      - Hourly decay cycles (runs every 5 minutes)
      - Session-aware decay rates based on user activity
      - Smart morning prediction: exempts predicted-needed memories from decay
      - Per-agent transaction atomicity
      - Architectural decisions get special handling (1% decay always)
    """

    def __init__(self, db_path: str):
        self.db_path = db_path
        self.running = False
        self.cycle_count = 0
        self.last_cycle_time = None

    def _connect(self) -> sqlite3.Connection:
        """Create a database connection with WAL and timeout."""
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA busy_timeout=5000;")
        return conn

    def ensure_schema(self):
        """
        Migrate knowledge table to add V2.9 columns.
        Safe: only adds columns if they don't exist.
        """
        conn = self._connect()
        try:
            # Get existing columns
            cursor = conn.execute("PRAGMA table_info(knowledge)")
            columns = {row[1] for row in cursor.fetchall()}

            migrations = [
                ("confidence", "REAL DEFAULT 1.0"),
                ("tier", "TEXT DEFAULT 'warm'"),
                ("priority", "INTEGER DEFAULT 5"),
                ("deleted", "INTEGER DEFAULT 0"),
                ("decay_rate", "REAL DEFAULT 0.05"),
                ("exempt_from_decay", "INTEGER DEFAULT 0"),
                ("is_architectural_decision", "INTEGER DEFAULT 0"),
                ("last_user_message_at", "TEXT"),
            ]

            for col_name, col_def in migrations:
                if col_name not in columns:
                    try:
                        conn.execute(f"ALTER TABLE knowledge ADD COLUMN {col_name} {col_def}")
                        log.info(f"[SCHEMA] Added column '{col_name}' to knowledge table")
                    except sqlite3.OperationalError as e:
                        log.warning(f"[SCHEMA] Column '{col_name}' migration failed: {e}")

            # Create tracking tables
            conn.execute("""
                CREATE TABLE IF NOT EXISTS memory_quotas (
                    agent_id TEXT PRIMARY KEY,
                    max_memories INTEGER NOT NULL DEFAULT 10000,
                    current_count INTEGER NOT NULL DEFAULT 0,
                    hot_count INTEGER NOT NULL DEFAULT 0,
                    warm_count INTEGER NOT NULL DEFAULT 0,
                    cold_count INTEGER NOT NULL DEFAULT 0,
                    last_enforced_at TEXT NOT NULL DEFAULT ''
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS dmm_cycles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    cycle_at TEXT NOT NULL,
                    duration_ms REAL NOT NULL DEFAULT 0.0,
                    promoted INTEGER DEFAULT 0,
                    demoted INTEGER DEFAULT 0,
                    decayed INTEGER DEFAULT 0,
                    pruned INTEGER DEFAULT 0,
                    session_mode TEXT DEFAULT 'unknown',
                    details TEXT
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS session_tracking (
                    agent_id TEXT PRIMARY KEY,
                    last_user_message_at TEXT NOT NULL,
                    current_session_mode TEXT DEFAULT 'active',
                    updated_at TEXT NOT NULL
                )
            """)

            # Create indexes
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_knowledge_tier
                ON knowledge(tier, confidence)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_knowledge_access
                ON knowledge(access_count, last_accessed)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_knowledge_exempt
                ON knowledge(exempt_from_decay, deleted)
            """)

            conn.commit()
            log.info("[SCHEMA] V2.9 schema verified/migrated successfully")
        except Exception as e:
            log.error(f"[SCHEMA] Migration failed: {e}")
            conn.rollback()
        finally:
            conn.close()

    def run_cycle(self) -> dict:
        """
        Run a complete V2.9 DMM cycle:
          1. Update session modes (active/passive/sleep)
          2. Apply session-aware decay
          3. Tier management (promote/demote)
          4. Quota enforcement
          5. Cold tier pruning
          6. Log cycle

        Returns dict with stats.
        """
        conn = self._connect()
        cycle_start = time.time()
        stats = {
            "promoted": 0,
            "demoted": 0,
            "decayed": 0,
            "pruned": 0,
            "quota_enforced": 0,
            "session_mode": "unknown",
        }

        try:
            now = datetime.now(timezone.utc).isoformat()

            # 1. Update session tracking and determine global session mode
            session_mode = self._update_session_tracking(conn, now)
            stats["session_mode"] = session_mode

            log.info(f"[CYCLE] Starting DMM cycle #{self.cycle_count} (mode: {session_mode})")

            # 2. Get all agents
            agents = conn.execute(
                "SELECT DISTINCT agent_id FROM knowledge WHERE deleted = 0"
            ).fetchall()

            # 3. Process each agent in its own transaction
            for (agent_id,) in agents:
                try:
                    conn.execute("BEGIN IMMEDIATE")
                    agent_stats = self._process_agent(
                        conn, agent_id, now, session_mode
                    )
                    conn.execute("COMMIT")
                    for k, v in agent_stats.items():
                        stats[k] = stats.get(k, 0) + v
                except Exception as e:
                    conn.execute("ROLLBACK")
                    log.error(f"[AGENT] Failed to process {agent_id[:8]}: {e}")

            # 4. Global cold tier pruning
            try:
                conn.execute("BEGIN IMMEDIATE")
                cutoff = (
                    datetime.now(timezone.utc) - timedelta(days=COLD_PRUNE_DAYS)
                ).isoformat()
                pruned = conn.execute(
                    """UPDATE knowledge SET deleted = 1
                       WHERE tier = 'cold'
                       AND (confidence < ? OR last_accessed < ?)
                       AND deleted = 0""",
                    (COLD_CONFIDENCE_THRESHOLD, cutoff),
                ).rowcount
                stats["pruned"] += pruned
                conn.execute("COMMIT")
            except Exception as e:
                conn.execute("ROLLBACK")
                log.error(f"[PRUNE] Cold tier pruning failed: {e}")

            # 5. Log cycle
            cycle_duration_ms = (time.time() - cycle_start) * 1000
            conn.execute(
                """INSERT INTO dmm_cycles
                   (cycle_at, duration_ms, promoted, demoted, decayed, pruned, session_mode, details)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    now,
                    cycle_duration_ms,
                    stats["promoted"],
                    stats["demoted"],
                    stats["decayed"],
                    stats["pruned"],
                    stats["session_mode"],
                    json.dumps({k: v for k, v in stats.items() if k != "session_mode"}),
                ),
            )
            conn.commit()

            self.cycle_count += 1
            self.last_cycle_time = now

            log.info(
                f"[CYCLE] Complete in {cycle_duration_ms:.1f}ms: "
                f"promoted={stats['promoted']}, demoted={stats['demoted']}, "
                f"decayed={stats['decayed']}, pruned={stats['pruned']}"
            )

        except Exception as e:
            log.error(f"[CYCLE] Fatal error: {e}", exc_info=True)
            try:
                conn.rollback()
            except Exception:
                pass
        finally:
            conn.close()

        return stats

    def _update_session_tracking(self, conn: sqlite3.Connection, now: str) -> str:
        """
        Update session tracking for all agents.
        Determine global session mode based on most recent user message.

        Returns: "active", "passive", or "sleep"
        """
        now_dt = datetime.fromisoformat(now)
        active_threshold = now_dt - timedelta(minutes=ACTIVE_SESSION_MINUTES)
        passive_threshold = now_dt - timedelta(minutes=PASSIVE_SESSION_MINUTES)

        # Get the most recent user message timestamp across all sessions
        latest_msg = conn.execute(
            "SELECT last_user_message_at FROM session_tracking "
            "ORDER BY last_user_message_at DESC LIMIT 1"
        ).fetchone()

        global_session_mode = "sleep"  # default
        if latest_msg and latest_msg[0]:
            latest_dt = datetime.fromisoformat(latest_msg[0])
            if latest_dt >= active_threshold:
                global_session_mode = "active"
            elif latest_dt >= passive_threshold:
                global_session_mode = "passive"

        log.debug(f"[SESSION] Global mode: {global_session_mode}")
        return global_session_mode

    def _process_agent(
        self,
        conn: sqlite3.Connection,
        agent_id: str,
        now: str,
        session_mode: str,
    ) -> dict:
        """Process a single agent: decay, tier management, quota enforcement."""
        stats = {"promoted": 0, "demoted": 0, "decayed": 0, "quota_enforced": 0}

        # ── 1. Apply Session-Aware Confidence Decay ──
        decayed = self._apply_decay(conn, agent_id, now, session_mode)
        stats["decayed"] = decayed

        # ── 2. Tier Promotion: warm → hot ──
        promoted = conn.execute(
            """UPDATE knowledge SET tier = 'hot'
               WHERE agent_id = ? AND tier = 'warm'
               AND access_count >= ? AND deleted = 0""",
            (agent_id, ACCESS_PROMOTE_THRESHOLD),
        ).rowcount
        stats["promoted"] = promoted

        # ── 3. Tier Demotion: hot → warm ──
        demote_cutoff = (
            datetime.now(timezone.utc) - timedelta(days=ACCESS_DEMOTE_THRESHOLD_DAYS)
        ).isoformat()
        demoted = conn.execute(
            """UPDATE knowledge SET tier = 'warm'
               WHERE agent_id = ? AND tier = 'hot'
               AND last_accessed < ? AND deleted = 0""",
            (agent_id, demote_cutoff),
        ).rowcount
        stats["demoted"] = demoted

        # ── 4. Tier Demotion: warm → cold ──
        demoted_cold = conn.execute(
            """UPDATE knowledge SET tier = 'cold'
               WHERE agent_id = ? AND tier = 'warm'
               AND confidence < ? AND deleted = 0""",
            (agent_id, COLD_CONFIDENCE_THRESHOLD),
        ).rowcount
        stats["demoted"] += demoted_cold

        # ── 5. Enforce hot tier capacity ──
        hot_count = conn.execute(
            "SELECT COUNT(*) FROM knowledge WHERE agent_id = ? AND tier = 'hot' AND deleted = 0",
            (agent_id,),
        ).fetchone()[0]

        if hot_count > MAX_HOT_MEMORIES:
            excess = hot_count - MAX_HOT_MEMORIES
            conn.execute(
                """UPDATE knowledge SET tier = 'warm'
                   WHERE id IN (
                       SELECT id FROM knowledge
                       WHERE agent_id = ? AND tier = 'hot' AND deleted = 0
                       ORDER BY access_count ASC, last_accessed ASC
                       LIMIT ?
                   )""",
                (agent_id, excess),
            )
            stats["demoted"] += excess

        # ── 6. Quota Enforcement ──
        count = conn.execute(
            "SELECT COUNT(*) FROM knowledge WHERE agent_id = ? AND deleted = 0",
            (agent_id,),
        ).fetchone()[0]

        if count > DEFAULT_QUOTA_PER_AGENT:
            excess = count - DEFAULT_QUOTA_PER_AGENT
            conn.execute(
                """UPDATE knowledge SET deleted = 1
                   WHERE id IN (
                       SELECT id FROM knowledge
                       WHERE agent_id = ? AND deleted = 0
                       ORDER BY priority ASC, confidence ASC, last_accessed ASC
                       LIMIT ?
                   )""",
                (agent_id, excess),
            )
            stats["quota_enforced"] = excess

        # ── 7. Update quota tracking ──
        tier_counts = conn.execute(
            """SELECT tier, COUNT(*) FROM knowledge
               WHERE agent_id = ? AND deleted = 0 GROUP BY tier""",
            (agent_id,),
        ).fetchall()
        tier_map = {t: c for t, c in tier_counts}

        conn.execute(
            """INSERT OR REPLACE INTO memory_quotas
               (agent_id, max_memories, current_count, hot_count, warm_count, cold_count, last_enforced_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                agent_id,
                DEFAULT_QUOTA_PER_AGENT,
                sum(tier_map.values()),
                tier_map.get("hot", 0),
                tier_map.get("warm", 0),
                tier_map.get("cold", 0),
                now,
            ),
        )

        return stats

    def _apply_decay(
        self,
        conn: sqlite3.Connection,
        agent_id: str,
        now: str,
        session_mode: str,
    ) -> int:
        """
        Apply session-aware decay to non-exempt memories.

        Decay rates (per hour):
          - active mode: 5% (BASE_DECAY_RATE)
          - passive mode: 1% (PASSIVE_DECAY_RATE)
          - sleep mode: 0.1% (SLEEP_DECAY_RATE)
          - architectural decisions: always 1%

        Exempt memories are those marked with exempt_from_decay = 1
        (set by smart morning prediction).
        """
        now_dt = datetime.fromisoformat(now)

        # Determine decay rate based on session mode
        if session_mode == "active":
            decay_rate = BASE_DECAY_RATE
        elif session_mode == "passive":
            decay_rate = PASSIVE_DECAY_RATE
        else:  # sleep
            decay_rate = SLEEP_DECAY_RATE

        decay_factor = 1.0 - (decay_rate / 60.0)  # Convert hourly to per-cycle (5 min)

        # Decay non-exempt regular memories
        decayed = conn.execute(
            """UPDATE knowledge SET confidence = MAX(0.05, confidence * ?)
               WHERE agent_id = ? AND exempt_from_decay = 0
               AND is_architectural_decision = 0 AND deleted = 0
               AND confidence > 0.1""",
            (decay_factor, agent_id),
        ).rowcount

        # Decay architectural decisions at their own rate (1% per hour)
        arch_decay_factor = 1.0 - (ARCH_DECISION_DECAY_RATE / 60.0)
        decayed_arch = conn.execute(
            """UPDATE knowledge SET confidence = MAX(0.05, confidence * ?)
               WHERE agent_id = ? AND is_architectural_decision = 1
               AND deleted = 0 AND confidence > 0.1""",
            (arch_decay_factor, agent_id),
        ).rowcount

        return decayed + decayed_arch

    def record_user_message(self, agent_id: str, timestamp: str = None):
        """
        Record that a user sent a message, updating session tracking.
        Called by team_server when receiving Discord messages.
        """
        if timestamp is None:
            timestamp = datetime.now(timezone.utc).isoformat()

        conn = self._connect()
        try:
            now = datetime.now(timezone.utc).isoformat()
            conn.execute(
                """INSERT OR REPLACE INTO session_tracking
                   (agent_id, last_user_message_at, current_session_mode, updated_at)
                   VALUES (?, ?, 'active', ?)""",
                (agent_id, timestamp, now),
            )
            conn.commit()
            log.debug(f"[SESSION] Recorded user message for {agent_id[:8]}")
        except Exception as e:
            log.error(f"[SESSION] Failed to record message: {e}")
        finally:
            conn.close()

    def predict_morning_memories(self, agent_id: str) -> int:
        """
        Smart morning prediction: analyze recent context and tag memories
        that will likely be needed in the next session as exempt from decay.

        Heuristics:
          - Recent topic clusters (keywords in recent access_count > 0)
          - Unfinished tasks (priority > 5)
          - Architectural decisions (is_architectural_decision = 1)

        Returns count of memories exempted.
        """
        conn = self._connect()
        try:
            # Get recent high-access memories (accessed in last 24h)
            cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
            recent_memories = conn.execute(
                """SELECT id, keywords, priority FROM knowledge
                   WHERE agent_id = ? AND deleted = 0
                   AND last_accessed > ? AND access_count > 0
                   ORDER BY access_count DESC, last_accessed DESC
                   LIMIT 20""",
                (agent_id, cutoff),
            ).fetchall()

            # Extract keywords for clustering
            recent_keywords = set()
            high_priority_ids = []
            for mem_id, keywords, priority in recent_memories:
                if keywords:
                    recent_keywords.update(keywords.lower().split())
                if priority > 5:
                    high_priority_ids.append(mem_id)

            exempted = 0

            # Exempt architectural decisions
            exempted += conn.execute(
                """UPDATE knowledge SET exempt_from_decay = 1
                   WHERE agent_id = ? AND is_architectural_decision = 1
                   AND deleted = 0 AND exempt_from_decay = 0""",
                (agent_id,),
            ).rowcount

            # Exempt high-priority items
            if high_priority_ids:
                placeholders = ",".join("?" * len(high_priority_ids))
                exempted += conn.execute(
                    f"""UPDATE knowledge SET exempt_from_decay = 1
                       WHERE id IN ({placeholders}) AND exempt_from_decay = 0""",
                    high_priority_ids,
                ).rowcount

            # Exempt memories with keywords from recent access (topic clustering)
            for keyword in list(recent_keywords)[:5]:  # Top 5 keywords
                exempted += conn.execute(
                    """UPDATE knowledge SET exempt_from_decay = 1
                       WHERE agent_id = ? AND keywords LIKE ?
                       AND deleted = 0 AND exempt_from_decay = 0""",
                    (agent_id, f"%{keyword}%"),
                ).rowcount

            conn.commit()
            log.info(
                f"[PREDICT] Exempted {exempted} memories from decay for {agent_id[:8]}"
            )
            return exempted

        except Exception as e:
            log.error(f"[PREDICT] Morning prediction failed: {e}")
            return 0
        finally:
            conn.close()

    def get_memory_stats(self) -> dict:
        """Return current memory statistics for display (e.g., /dmm command)."""
        conn = self._connect()
        try:
            stats = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "cycle_count": self.cycle_count,
                "last_cycle": self.last_cycle_time,
                "agents": {},
            }

            # Get per-agent stats
            agents = conn.execute(
                "SELECT DISTINCT agent_id FROM memory_quotas"
            ).fetchall()

            for (agent_id,) in agents:
                quota = conn.execute(
                    "SELECT current_count, hot_count, warm_count, cold_count FROM memory_quotas WHERE agent_id = ?",
                    (agent_id,),
                ).fetchone()

                if quota:
                    current, hot, warm, cold = quota
                    stats["agents"][agent_id[:8]] = {
                        "total": current,
                        "hot": hot,
                        "warm": warm,
                        "cold": cold,
                    }

            # Global stats
            total = conn.execute("SELECT COUNT(*) FROM knowledge WHERE deleted = 0").fetchone()[0]
            by_tier = conn.execute(
                "SELECT tier, COUNT(*) FROM knowledge WHERE deleted = 0 GROUP BY tier"
            ).fetchall()
            tier_counts = {t: c for t, c in by_tier}

            stats["global"] = {
                "total_memories": total,
                "hot": tier_counts.get("hot", 0),
                "warm": tier_counts.get("warm", 0),
                "cold": tier_counts.get("cold", 0),
                "high_confidence": conn.execute(
                    "SELECT COUNT(*) FROM knowledge WHERE confidence >= 0.8 AND deleted = 0"
                ).fetchone()[0],
                "low_confidence": conn.execute(
                    "SELECT COUNT(*) FROM knowledge WHERE confidence < 0.3 AND deleted = 0"
                ).fetchone()[0],
            }

            return stats

        except Exception as e:
            log.error(f"[STATS] Failed to get stats: {e}")
            return {"error": str(e)}
        finally:
            conn.close()


# ══════════════════════════════════════════════
# DAEMON MANAGER
# ══════════════════════════════════════════════

class DMM_Daemon:
    """Background daemon runner for Strategic Memory Manager."""

    def __init__(self, db_path: str = DB_PATH):
        self.manager = StrategicMemoryManager(db_path)
        self.running = False
        self.thread = None

    def start(self):
        """Start the DMM daemon in a background thread."""
        if self.running:
            return
        self.running = True
        self.manager.ensure_schema()
        self.thread = threading.Thread(target=self._run_loop, daemon=True, name="dmm-v2.9")
        self.thread.start()
        log.info(f"[DAEMON] DMM v2.9 daemon started (cycle every {CYCLE_INTERVAL}s)")

    def _run_loop(self):
        """Main daemon loop."""
        # Wait 30 seconds for database to stabilize
        time.sleep(30)

        while self.running:
            try:
                self.manager.run_cycle()
            except Exception as e:
                log.error(f"[DAEMON] Cycle error: {e}", exc_info=True)

            time.sleep(CYCLE_INTERVAL)

    def stop(self):
        """Stop the daemon."""
        self.running = False
        log.info("[DAEMON] DMM daemon stopped")

    def get_stats(self) -> dict:
        """Get current stats."""
        return self.manager.get_memory_stats()

    def predict_morning(self, agent_id: str) -> int:
        """Predict and exempt morning memories."""
        return self.manager.predict_morning_memories(agent_id)

    def record_message(self, agent_id: str, timestamp: str = None):
        """Record user message for session tracking."""
        self.manager.record_user_message(agent_id, timestamp)


# ══════════════════════════════════════════════
# MODULE EXPORTS
# ══════════════════════════════════════════════

__all__ = [
    "StrategicMemoryManager",
    "DMM_Daemon",
]

# Example standalone usage
if __name__ == "__main__":
    log.info("Strategic Forgetting v2.9 module loaded")
    dmm = DMM_Daemon()
    dmm.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        dmm.stop()
        log.info("Shutdown complete")
