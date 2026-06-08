import logging
import os
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class SQLiteManager:
    def __init__(self, db_path: str = ":memory:"):
        self.db_path = db_path
        self.connection = sqlite3.connect(self.db_path, check_same_thread=False)
        self._lock = threading.Lock()
        self._migrate_history_table()
        self._create_history_table()
        self._create_messages_table()

    def _migrate_history_table(self) -> None:
        """
        If a pre-existing history table had the old group-chat columns,
        rename it, create the new schema, copy the intersecting data, then
        drop the old table.
        """
        with self._lock:
            try:
                # Start a transaction
                self.connection.execute("BEGIN")
                cur = self.connection.cursor()

                cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='history'")
                if cur.fetchone() is None:
                    self.connection.execute("COMMIT")
                    return  # nothing to migrate

                cur.execute("PRAGMA table_info(history)")
                old_cols = {row[1] for row in cur.fetchall()}

                expected_cols = {
                    "id",
                    "memory_id",
                    "old_memory",
                    "new_memory",
                    "event",
                    "created_at",
                    "updated_at",
                    "is_deleted",
                    "actor_id",
                    "role",
                }

                if old_cols == expected_cols:
                    self.connection.execute("COMMIT")
                    return

                logger.info("Migrating history table to new schema (no convo columns).")

                # Clean up any existing history_old table from previous failed migration
                cur.execute("DROP TABLE IF EXISTS history_old")

                # Rename the current history table
                cur.execute("ALTER TABLE history RENAME TO history_old")

                # Create the new history table with updated schema
                cur.execute(
                    """
                    CREATE TABLE history (
                        id           TEXT PRIMARY KEY,
                        memory_id    TEXT,
                        old_memory   TEXT,
                        new_memory   TEXT,
                        event        TEXT,
                        created_at   DATETIME,
                        updated_at   DATETIME,
                        is_deleted   INTEGER,
                        actor_id     TEXT,
                        role         TEXT
                    )
                """
                )

                # Copy data from old table to new table
                intersecting = list(expected_cols & old_cols)
                if intersecting:
                    cols_csv = ", ".join(intersecting)
                    cur.execute(f"INSERT INTO history ({cols_csv}) SELECT {cols_csv} FROM history_old")

                # Drop the old table
                cur.execute("DROP TABLE history_old")

                # Commit the transaction
                self.connection.execute("COMMIT")
                logger.info("History table migration completed successfully.")

            except Exception as e:
                # Rollback the transaction on any error
                self.connection.execute("ROLLBACK")
                logger.error(f"History table migration failed: {e}")
                raise

    def _create_history_table(self) -> None:
        with self._lock:
            try:
                self.connection.execute("BEGIN")
                self.connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS history (
                        id           TEXT PRIMARY KEY,
                        memory_id    TEXT,
                        old_memory   TEXT,
                        new_memory   TEXT,
                        event        TEXT,
                        created_at   DATETIME,
                        updated_at   DATETIME,
                        is_deleted   INTEGER,
                        actor_id     TEXT,
                        role         TEXT
                    )
                """
                )
                self.connection.execute("COMMIT")
            except Exception as e:
                self.connection.execute("ROLLBACK")
                logger.error(f"Failed to create history table: {e}")
                raise

    def _create_messages_table(self) -> None:
        with self._lock:
            try:
                self.connection.execute("BEGIN")
                self.connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS messages (
                        id TEXT PRIMARY KEY,
                        session_scope TEXT,
                        role TEXT,
                        content TEXT,
                        name TEXT,
                        created_at DATETIME
                    )
                """
                )
                self.connection.execute("COMMIT")
            except Exception as e:
                self.connection.execute("ROLLBACK")
                logger.error(f"Failed to create messages table: {e}")
                raise

    def add_history(
        self,
        memory_id: str,
        old_memory: Optional[str],
        new_memory: Optional[str],
        event: str,
        *,
        created_at: Optional[str] = None,
        updated_at: Optional[str] = None,
        is_deleted: int = 0,
        actor_id: Optional[str] = None,
        role: Optional[str] = None,
    ) -> None:
        with self._lock:
            try:
                self.connection.execute("BEGIN")
                self.connection.execute(
                    """
                    INSERT INTO history (
                        id, memory_id, old_memory, new_memory, event,
                        created_at, updated_at, is_deleted, actor_id, role
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                    (
                        str(uuid.uuid4()),
                        memory_id,
                        old_memory,
                        new_memory,
                        event,
                        created_at,
                        updated_at,
                        is_deleted,
                        actor_id,
                        role,
                    ),
                )
                self.connection.execute("COMMIT")
            except Exception as e:
                self.connection.execute("ROLLBACK")
                logger.error(f"Failed to add history record: {e}")
                raise

    def batch_add_history(self, records: List[Dict[str, Any]]) -> None:
        with self._lock:
            try:
                self.connection.execute("BEGIN")
                self.connection.executemany(
                    """
                    INSERT INTO history (
                        id, memory_id, old_memory, new_memory, event,
                        created_at, updated_at, is_deleted, actor_id, role
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                    [
                        (
                            str(uuid.uuid4()),
                            record.get("memory_id"),
                            record.get("old_memory"),
                            record.get("new_memory"),
                            record.get("event"),
                            record.get("created_at"),
                            record.get("updated_at"),
                            record.get("is_deleted", 0),
                            record.get("actor_id"),
                            record.get("role"),
                        )
                        for record in records
                    ],
                )
                self.connection.execute("COMMIT")
            except Exception as e:
                self.connection.execute("ROLLBACK")
                logger.error(f"Failed to batch add history records: {e}")
                raise

    def get_history(self, memory_id: str) -> List[Dict[str, Any]]:
        with self._lock:
            cur = self.connection.execute(
                """
                SELECT id, memory_id, old_memory, new_memory, event,
                       created_at, updated_at, is_deleted, actor_id, role
                FROM history
                WHERE memory_id = ?
                ORDER BY created_at ASC, DATETIME(updated_at) ASC
            """,
                (memory_id,),
            )
            rows = cur.fetchall()

        return [
            {
                "id": r[0],
                "memory_id": r[1],
                "old_memory": r[2],
                "new_memory": r[3],
                "event": r[4],
                "created_at": r[5],
                "updated_at": r[6],
                "is_deleted": bool(r[7]),
                "actor_id": r[8],
                "role": r[9],
            }
            for r in rows
        ]

    def save_messages(self, messages: List[Dict[str, Any]], session_scope: str) -> None:
        if not messages:
            return
        with self._lock:
            try:
                self.connection.execute("BEGIN")
                now = datetime.now(timezone.utc).isoformat()
                for message in messages:
                    self.connection.execute(
                        """
                        INSERT INTO messages (id, session_scope, role, content, name, created_at)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """,
                        (
                            str(uuid.uuid4()),
                            session_scope,
                            message.get("role"),
                            message.get("content"),
                            message.get("name"),
                            now,
                        ),
                    )
                # Evict old messages beyond the most recent 10 for this scope.
                # Wrapped in a derived table to force SQLite to materialize the
                # ORDER BY before the outer NOT IN evaluates it.
                self.connection.execute(
                    """
                    DELETE FROM messages WHERE session_scope = ? AND id NOT IN (
                        SELECT id FROM (
                            SELECT id FROM messages WHERE session_scope = ? ORDER BY created_at DESC LIMIT 10
                        )
                    )
                """,
                    (session_scope, session_scope),
                )
                self.connection.execute("COMMIT")
            except Exception as e:
                self.connection.execute("ROLLBACK")
                logger.error(f"Failed to save messages: {e}")
                raise

    def get_last_messages(self, session_scope: str, limit: int = 10) -> List[Dict[str, Any]]:
        with self._lock:
            # Subquery picks the latest N rows (DESC + LIMIT), outer query
            # re-sorts them chronologically (ASC) for the caller.
            cur = self.connection.execute(
                """
                SELECT role, content, name, created_at FROM (
                    SELECT role, content, name, created_at
                    FROM messages
                    WHERE session_scope = ?
                    ORDER BY created_at DESC
                    LIMIT ?
                ) ORDER BY created_at ASC
            """,
                (session_scope, limit),
            )
            rows = cur.fetchall()

        return [
            {
                "role": r[0],
                "content": r[1],
                "name": r[2],
                "created_at": r[3],
            }
            for r in rows
        ]

    def reset(self) -> None:
        """Drop and recreate the history and messages tables."""
        with self._lock:
            try:
                self.connection.execute("BEGIN")
                self.connection.execute("DROP TABLE IF EXISTS history")
                self.connection.execute("DROP TABLE IF EXISTS messages")
                self.connection.execute("COMMIT")
            except Exception as e:
                self.connection.execute("ROLLBACK")
                logger.error(f"Failed to reset tables: {e}")
                raise
        self._create_history_table()
        self._create_messages_table()

    def close(self) -> None:
        if self.connection:
            self.connection.close()
            self.connection = None

    def __del__(self):
        self.close()


class PostgreSQLManager:
    """Mirrors SQLiteManager interface but persists history/messages in PostgreSQL."""

    def __init__(self):
        import psycopg

        host = os.environ.get("POSTGRES_HOST", "localhost")
        port = os.environ.get("POSTGRES_PORT", "5432")
        user = os.environ.get("POSTGRES_USER", "postgres")
        password = os.environ.get("POSTGRES_PASSWORD", "postgres")
        db = os.environ.get("APP_DB_NAME", "mem0_app")

        self.connection = psycopg.connect(host=host, port=int(port), user=user, password=password, dbname=db)
        self._lock = threading.Lock()
        self._migrate_history_table()
        self._create_history_table()
        self._create_messages_table()

    def _migrate_history_table(self) -> None:
        with self._lock:
            try:
                cur = self.connection.execute(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = 'public' AND table_name = 'history'"
                )
                if cur.fetchone() is None:
                    self.connection.commit()
                    return

                cur = self.connection.execute(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema = 'public' AND table_name = 'history'"
                )
                old_cols = {row[0] for row in cur.fetchall()}
                expected_cols = {"id", "memory_id", "old_memory", "new_memory", "event", "created_at", "updated_at", "is_deleted", "actor_id", "role"}

                if old_cols == expected_cols:
                    self.connection.commit()
                    return

                logger.info("Migrating history table to new schema.")
                self.connection.execute("DROP TABLE IF EXISTS history_old")
                self.connection.execute("ALTER TABLE history RENAME TO history_old")
                self.connection.execute(
                    """
                    CREATE TABLE history (
                        id TEXT PRIMARY KEY, memory_id TEXT, old_memory TEXT,
                        new_memory TEXT, event TEXT, created_at TIMESTAMPTZ,
                        updated_at TIMESTAMPTZ, is_deleted INTEGER, actor_id TEXT, role TEXT
                    )
                    """
                )
                intersecting = list(expected_cols & old_cols)
                if intersecting:
                    cols_csv = ", ".join(intersecting)
                    self.connection.execute(f"INSERT INTO history ({cols_csv}) SELECT {cols_csv} FROM history_old")
                self.connection.execute("DROP TABLE history_old")
                self.connection.commit()
                logger.info("History table migration completed successfully.")
            except Exception as e:
                self.connection.rollback()
                logger.error(f"History table migration failed: {e}")
                raise

    def _create_history_table(self) -> None:
        with self._lock:
            try:
                self.connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS history (
                        id TEXT PRIMARY KEY, memory_id TEXT, old_memory TEXT,
                        new_memory TEXT, event TEXT, created_at TIMESTAMPTZ,
                        updated_at TIMESTAMPTZ, is_deleted INTEGER, actor_id TEXT, role TEXT
                    )
                    """
                )
                self.connection.commit()
            except Exception as e:
                self.connection.rollback()
                logger.error(f"Failed to create history table: {e}")
                raise

    def _create_messages_table(self) -> None:
        with self._lock:
            try:
                self.connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS messages (
                        id TEXT PRIMARY KEY, session_scope TEXT, role TEXT,
                        content TEXT, name TEXT, created_at TIMESTAMPTZ
                    )
                    """
                )
                self.connection.commit()
            except Exception as e:
                self.connection.rollback()
                logger.error(f"Failed to create messages table: {e}")
                raise

    def add_history(self, memory_id: str, old_memory: Optional[str], new_memory: Optional[str], event: str, *, created_at: Optional[str] = None, updated_at: Optional[str] = None, is_deleted: int = 0, actor_id: Optional[str] = None, role: Optional[str] = None) -> None:
        with self._lock:
            try:
                self.connection.execute(
                    "INSERT INTO history (id, memory_id, old_memory, new_memory, event, created_at, updated_at, is_deleted, actor_id, role) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    (str(uuid.uuid4()), memory_id, old_memory, new_memory, event, created_at, updated_at, is_deleted, actor_id, role),
                )
                self.connection.commit()
            except Exception as e:
                self.connection.rollback()
                logger.error(f"Failed to add history record: {e}")
                raise

    def batch_add_history(self, records: List[Dict[str, Any]]) -> None:
        with self._lock:
            try:
                with self.connection.cursor() as cur:
                    cur.executemany(
                        "INSERT INTO history (id, memory_id, old_memory, new_memory, event, created_at, updated_at, is_deleted, actor_id, role) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                        [(str(uuid.uuid4()), r.get("memory_id"), r.get("old_memory"), r.get("new_memory"), r.get("event"), r.get("created_at"), r.get("updated_at"), r.get("is_deleted", 0), r.get("actor_id"), r.get("role")) for r in records],
                    )
                self.connection.commit()
            except Exception as e:
                self.connection.rollback()
                logger.error(f"Failed to batch add history records: {e}")
                raise

    def get_history(self, memory_id: str) -> List[Dict[str, Any]]:
        with self._lock:
            cur = self.connection.execute(
                "SELECT id, memory_id, old_memory, new_memory, event, created_at, updated_at, is_deleted, actor_id, role FROM history WHERE memory_id = %s ORDER BY created_at ASC, updated_at ASC",
                (memory_id,),
            )
            rows = cur.fetchall()
        return [{"id": r[0], "memory_id": r[1], "old_memory": r[2], "new_memory": r[3], "event": r[4], "created_at": str(r[5]) if r[5] else None, "updated_at": str(r[6]) if r[6] else None, "is_deleted": bool(r[7]), "actor_id": r[8], "role": r[9]} for r in rows]

    def save_messages(self, messages: List[Dict[str, Any]], session_scope: str) -> None:
        if not messages:
            return
        with self._lock:
            try:
                now = datetime.now(timezone.utc).isoformat()
                with self.connection.cursor() as cur:
                    for message in messages:
                        cur.execute(
                            "INSERT INTO messages (id, session_scope, role, content, name, created_at) VALUES (%s, %s, %s, %s, %s, %s)",
                            (str(uuid.uuid4()), session_scope, message.get("role"), message.get("content"), message.get("name"), now),
                        )
                    cur.execute(
                        "DELETE FROM messages WHERE session_scope = %s AND id NOT IN (SELECT id FROM (SELECT id FROM messages WHERE session_scope = %s ORDER BY created_at DESC LIMIT 10) AS subq)",
                        (session_scope, session_scope),
                    )
                self.connection.commit()
            except Exception as e:
                self.connection.rollback()
                logger.error(f"Failed to save messages: {e}")
                raise

    def get_last_messages(self, session_scope: str, limit: int = 10) -> List[Dict[str, Any]]:
        with self._lock:
            cur = self.connection.execute(
                "SELECT role, content, name, created_at FROM (SELECT role, content, name, created_at FROM messages WHERE session_scope = %s ORDER BY created_at DESC LIMIT %s) AS subq ORDER BY created_at ASC",
                (session_scope, limit),
            )
            rows = cur.fetchall()
        return [{"role": r[0], "content": r[1], "name": r[2], "created_at": str(r[3]) if r[3] else None} for r in rows]

    def reset(self) -> None:
        with self._lock:
            try:
                self.connection.execute("DROP TABLE IF EXISTS history")
                self.connection.execute("DROP TABLE IF EXISTS messages")
                self.connection.commit()
            except Exception as e:
                self.connection.rollback()
                logger.error(f"Failed to reset tables: {e}")
                raise
        self._create_history_table()
        self._create_messages_table()

    def close(self) -> None:
        if self.connection and not self.connection.closed:
            self.connection.close()
            self.connection = None

    def __del__(self):
        self.close()


def create_storage_manager(history_db_path: str = ":memory:"):
    """Return PostgreSQLManager if POSTGRES_HOST is set, otherwise SQLiteManager."""
    if os.environ.get("POSTGRES_HOST"):
        return PostgreSQLManager()
    return SQLiteManager(history_db_path)
