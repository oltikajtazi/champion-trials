"""Create or update a user straight in inventory.db (no server needed).

Usage:   python add_user.py USERNAME PASSWORD [worker|admin]
Example: python add_user.py "olti kajtazi" "olti kajtazi" worker

Run it in the project folder. If the user already exists, its password and role are replaced.
Uses the same salted PBKDF2 hashing as main.py.
"""
import hashlib
import secrets
import sqlite3
import sys

DB_PATH = "inventory.db"
PBKDF2_ROUNDS = 200_000          # keep identical to main.py


def main() -> int:
    if len(sys.argv) < 3 or len(sys.argv) > 4:
        print(__doc__)
        return 1
    username, password = sys.argv[1].strip(), sys.argv[2]
    role = sys.argv[3] if len(sys.argv) == 4 else "worker"
    if role not in ("worker", "admin"):
        print("Role must be 'worker' or 'admin'.")
        return 1
    if not username or len(password) < 6:
        print("Username is required and the password needs at least 6 characters.")
        return 1
    db = sqlite3.connect(DB_PATH)
    cols = {r[1] for r in db.execute("PRAGMA table_info(users)").fetchall()}
    if not cols:
        print("No users table found. Start the backend once (uvicorn main:app) so the database is created.")
        return 1
    if "role" not in cols:      # older database: existing accounts stay admins
        db.execute("ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'admin'")
    salt = secrets.token_hex(16)
    pw_hash = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), PBKDF2_ROUNDS).hex()
    existing = db.execute("SELECT id FROM users WHERE username = ? COLLATE NOCASE", (username,)).fetchone()
    if existing:
        db.execute("UPDATE users SET salt=?, password_hash=?, role=? WHERE id=?",
                   (salt, pw_hash, role, existing[0]))
        print(f"Updated '{username}' ({role}).")
    else:
        db.execute("INSERT INTO users (username, salt, password_hash, role) VALUES (?, ?, ?, ?)",
                   (username, salt, pw_hash, role))
        print(f"Created '{username}' ({role}).")
    db.commit()
    db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
