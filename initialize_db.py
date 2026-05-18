from pathlib import Path
import sqlite3

DB_PATH = Path(__file__).parent / "app_data" / "app.db"

def get_connection():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def initialize_database():
    with get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS elements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                description TEXT DEFAULT ''
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS components (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                description TEXT DEFAULT '',
                is_subcomp INTEGER NOT NULL DEFAULT 0 CHECK (is_subcomp IN (0, 1)),
                iface TEXT NOT NULL DEFAULT '',
                parent_id INTEGER NOT NULL,
                category TEXT NOT NULL DEFAULT '',
                functionality TEXT NOT NULL DEFAULT '',
                icon_path TEXT DEFAULT '',
                checkpointable INTEGER NOT NULL DEFAULT 0 CHECK (checkpointable IN (0, 1)),
                
                UNIQUE(parent_id, name, is_subcomp),

                FOREIGN KEY (parent_id) REFERENCES elements(id)
                    ON DELETE CASCADE
                    ON UPDATE RESTRICT
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS subcomp_slots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                description TEXT DEFAULT '',
                iface TEXT NOT NULL,
                parent_id INTEGER NOT NULL,

                FOREIGN KEY (parent_id) REFERENCES components(id)
                    ON DELETE CASCADE
                    ON UPDATE RESTRICT
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS parameters
                (id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                description TEXT DEFAULT '',
                default_val TEXT NOT NULL DEFAULT '',
                parent_id INTEGER NOT NULL,
                parent_type TEXT NOT NULL CHECK (
                    parent_type IN (
                        'components',
                        'statistics'
                    )
                ),
                required INTEGER NOT NULL DEFAULT 0 CHECK (required IN (0, 1))
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS statistics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                description TEXT DEFAULT '',
                units TEXT NOT NULL,
                iface TEXT NOT NULL,
                parent_id INTEGER NOT NULL,

                FOREIGN KEY (parent_id) REFERENCES components(id)
                    ON DELETE CASCADE
                    ON UPDATE RESTRICT
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS ports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                description TEXT DEFAULT '',
                iface TEXT NOT NULL,
                parent_id INTEGER NOT NULL,

                FOREIGN KEY (parent_id) REFERENCES components(id)
                    ON DELETE CASCADE
                    ON UPDATE RESTRICT
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS sst_info_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                command TEXT NOT NULL,
                return_code INTEGER NOT NULL,
                stdout TEXT NOT NULL DEFAULT '',
                stderr TEXT NOT NULL DEFAULT '',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        ensure_component_icon_column(conn)

def save_sst_info_run(command, return_code, stdout, stderr):
    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO sst_info_runs (
                command,
                return_code,
                stdout,
                stderr
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                " ".join(command),
                return_code,
                stdout,
                stderr,
            ),
        )

        return cursor.lastrowid


def ensure_component_icon_column(conn) -> None:
    columns = {
        row["name"]
        for row in conn.execute("PRAGMA table_info(components)").fetchall()
    }

    if "icon_path" not in columns:
        conn.execute(
            """
            ALTER TABLE components
            ADD COLUMN icon_path TEXT
            """
        )


if __name__ == "__main__":
    initialize_database()
    print(f"Database created at: {DB_PATH}")