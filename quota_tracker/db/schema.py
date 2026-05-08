"""Database schema and migration management."""
import sqlite3


def get_db_connection(
    db_path: str = "~/.local/share/quota-tracker/quota-tracker.sqlite3",
) -> sqlite3.Connection:
    """Establish a connection to the SQLite database.

    Args:
        db_path: Path to the database file.

    Returns:
        A sqlite3.Connection object.
    """
    import os

    db_path = os.path.expanduser(db_path)
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    return conn


def apply_migrations(conn: sqlite3.Connection) -> None:
    """Apply pending database migrations.

    Args:
        conn: The database connection.
    """
    conn.execute("""
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    migrations: list[tuple[int, str]] = [
        (
            1,
            """
            CREATE TABLE IF NOT EXISTS providers (
                id TEXT PRIMARY KEY,
                enabled BOOLEAN NOT NULL DEFAULT 0,
                config TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            
            CREATE TABLE IF NOT EXISTS quota_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                provider_id TEXT NOT NULL,
                quota_name TEXT NOT NULL,
                timestamp TIMESTAMP NOT NULL,
                used_percent REAL,
                remaining_percent REAL,
                window_minutes INTEGER,
                resets_at TIMESTAMP,
                source TEXT NOT NULL,
                raw_data TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(provider_id) REFERENCES providers(id)
            );
            
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                provider_id TEXT NOT NULL,
                external_session_id TEXT NOT NULL,
                model_name TEXT,
                project_path TEXT,
                project_name TEXT,
                created_at TIMESTAMP NOT NULL,
                last_seen_at TIMESTAMP NOT NULL,
                metadata TEXT,
                FOREIGN KEY(provider_id) REFERENCES providers(id)
            );
            
            CREATE TABLE IF NOT EXISTS token_usage_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                provider_id TEXT NOT NULL,
                external_event_id TEXT NOT NULL,
                model_name TEXT,
                source TEXT NOT NULL,
                input_tokens INTEGER DEFAULT 0,
                output_tokens INTEGER DEFAULT 0,
                cached_tokens INTEGER DEFAULT 0,
                reasoning_tokens INTEGER DEFAULT 0,
                thoughts_tokens INTEGER DEFAULT 0,
                tool_tokens INTEGER DEFAULT 0,
                total_tokens INTEGER DEFAULT 0,
                raw_data TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(provider_id, session_id, external_event_id),
                FOREIGN KEY(session_id) REFERENCES sessions(id),
                FOREIGN KEY(provider_id) REFERENCES providers(id)
            );

            CREATE INDEX IF NOT EXISTS idx_quota_history_provider_id
                ON quota_history(provider_id);
            CREATE INDEX IF NOT EXISTS idx_quota_history_timestamp
                ON quota_history(timestamp);
            CREATE INDEX IF NOT EXISTS idx_quota_history_quota_name
                ON quota_history(quota_name);
            CREATE INDEX IF NOT EXISTS idx_quota_history_resets_at
                ON quota_history(resets_at);
        """,
        )
    ]

    cursor = conn.cursor()
    for version, sql in migrations:
        cursor.execute("SELECT 1 FROM schema_migrations WHERE version = ?", (version,))
        if not cursor.fetchone():
            conn.executescript(sql)
            conn.execute(
                "INSERT INTO schema_migrations (version) VALUES (?)",
                (version,),
            )
            conn.commit()
