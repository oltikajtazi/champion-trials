"""End-of-shift stock count: snapshot, record counted quantities, review, approve.

Pure sqlite3 logic (no web framework) so it can be tested on its own.
main.py exposes it through the API.

How a count works
-----------------
1. start_count()  snapshots every item's system quantity as "expected".
2. update_line()  records what was actually counted (typed in or from a photo).
3. approve()      applies the differences to stock and writes the movement history.

Why approval applies a DIFFERENCE and not "set stock to counted":
sales or deliveries can be recorded while people are still counting. Applying
(counted - expected) keeps those movements instead of wiping them out.
Items that were never counted are left untouched (never treated as zero).
"""
from typing import Callable, Optional


class CountError(Exception):
    """A problem the API should report to the user (carries an HTTP status)."""

    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status = status
        self.detail = detail


def init_tables(db) -> None:
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS shift_counts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            status TEXT NOT NULL DEFAULT 'Draft',
            note TEXT NOT NULL DEFAULT '',
            created_by TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            finished_by TEXT NOT NULL DEFAULT '',
            finished_at TEXT
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS shift_count_lines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            count_id INTEGER NOT NULL,
            item_id INTEGER NOT NULL,
            item_name TEXT NOT NULL,
            expected INTEGER NOT NULL,
            counted INTEGER,
            detected INTEGER,
            source TEXT NOT NULL DEFAULT 'manual',
            label TEXT NOT NULL DEFAULT '',
            confidence REAL,
            applied_delta INTEGER,
            result TEXT NOT NULL DEFAULT ''
        )
        """
    )
    db.execute("CREATE INDEX IF NOT EXISTS idx_count_lines ON shift_count_lines(count_id)")
    # At most one open (Draft) count at a time, enforced by the database itself
    db.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_one_draft ON shift_counts(status) "
        "WHERE status = 'Draft'"
    )


def _now(db) -> str:
    return db.execute("SELECT datetime('now','localtime')").fetchone()[0]


def _summary(db, count_id: int) -> dict:
    rows = db.execute(
        "SELECT l.*, i.cost AS cost FROM shift_count_lines l "
        "LEFT JOIN items i ON i.id = l.item_id WHERE l.count_id = ?", (count_id,),
    ).fetchall()
    counted = [r for r in rows if r["counted"] is not None]
    diff = [r for r in counted if r["counted"] != r["expected"]]
    return {
        "lines": len(rows),
        "counted": len(counted),
        "uncounted": len(rows) - len(counted),
        "with_difference": len(diff),
        "net_units": sum(r["counted"] - r["expected"] for r in diff),
        "net_value": round(sum((r["counted"] - r["expected"]) * (r["cost"] or 0) for r in diff), 2),
    }


def get_count(db, count_id: int, with_lines: bool = True) -> dict:
    row = db.execute("SELECT * FROM shift_counts WHERE id = ?", (count_id,)).fetchone()
    if row is None:
        raise CountError(404, "Count not found")
    out = dict(row)
    out["summary"] = _summary(db, count_id)
    if with_lines:
        out["lines"] = [dict(r) for r in db.execute(
            "SELECT * FROM shift_count_lines WHERE count_id = ? "
            "ORDER BY item_name COLLATE NOCASE", (count_id,)).fetchall()]
    return out


def current_count(db) -> Optional[dict]:
    row = db.execute("SELECT id FROM shift_counts WHERE status = 'Draft'").fetchone()
    return get_count(db, row["id"]) if row else None


def list_counts(db, limit: int = 50) -> list:
    rows = db.execute(
        "SELECT id FROM shift_counts ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    return [get_count(db, r["id"], with_lines=False) for r in rows]


def start_count(db, user: str, note: str = "") -> dict:
    if db.execute("SELECT 1 FROM shift_counts WHERE status = 'Draft'").fetchone():
        raise CountError(409, "A count is already in progress. Finish or cancel it first.")
    items = db.execute("SELECT id, name, quantity FROM items ORDER BY name COLLATE NOCASE").fetchall()
    if not items:
        raise CountError(400, "There are no items to count yet.")
    cur = db.execute(
        "INSERT INTO shift_counts (status, note, created_by, created_at) VALUES ('Draft', ?, ?, ?)",
        (note.strip(), user, _now(db)),
    )
    count_id = cur.lastrowid
    db.executemany(
        "INSERT INTO shift_count_lines (count_id, item_id, item_name, expected) VALUES (?, ?, ?, ?)",
        [(count_id, r["id"], r["name"], r["quantity"]) for r in items],
    )
    return get_count(db, count_id)


def _draft_or_error(db, count_id: int):
    row = db.execute("SELECT * FROM shift_counts WHERE id = ?", (count_id,)).fetchone()
    if row is None:
        raise CountError(404, "Count not found")
    if row["status"] != "Draft":
        raise CountError(409, f"This count is already {row['status'].lower()}.")
    return row


def update_line(db, count_id: int, line_id: int, counted: Optional[int], detected: Optional[int],
                source: str, label: str, confidence: Optional[float]) -> dict:
    _draft_or_error(db, count_id)
    line = db.execute(
        "SELECT id FROM shift_count_lines WHERE id = ? AND count_id = ?", (line_id, count_id)
    ).fetchone()
    if line is None:
        raise CountError(404, "Count line not found")
    if counted is not None and counted < 0:
        raise CountError(400, "A counted quantity cannot be negative.")
    db.execute(
        "UPDATE shift_count_lines SET counted = ?, detected = ?, source = ?, label = ?, "
        "confidence = ? WHERE id = ?",
        (counted, detected, source, label.strip(), confidence, line_id),
    )
    return dict(db.execute("SELECT * FROM shift_count_lines WHERE id = ?", (line_id,)).fetchone())


def cancel(db, count_id: int, user: str) -> dict:
    _draft_or_error(db, count_id)
    db.execute(
        "UPDATE shift_counts SET status = 'Cancelled', finished_by = ?, finished_at = ? WHERE id = ?",
        (user, _now(db), count_id),
    )
    return get_count(db, count_id, with_lines=False)


def approve(db, count_id: int, user: str, log_move: Callable, allow_uncounted: bool = False) -> dict:
    """Apply a draft count to stock. Raises CountError (nothing is saved) on any problem.

    The caller must run this inside one transaction and NOT commit if it raises.
    """
    # Claim the draft first: two people approving at once cannot both succeed.
    claimed = db.execute(
        "UPDATE shift_counts SET status = 'Approved', finished_by = ?, finished_at = ? "
        "WHERE id = ? AND status = 'Draft'", (user, _now(db), count_id),
    ).rowcount
    if claimed != 1:
        _draft_or_error(db, count_id)          # raises the right 404/409
        raise CountError(409, "This count could not be approved.")

    lines = db.execute(
        "SELECT * FROM shift_count_lines WHERE count_id = ? ORDER BY item_name COLLATE NOCASE",
        (count_id,),
    ).fetchall()
    uncounted = [r for r in lines if r["counted"] is None]
    if uncounted and not allow_uncounted:
        raise CountError(409, f"{len(uncounted)} item(s) have not been counted. "
                              "Count them, or approve anyway to leave them unchanged.")

    changed = 0
    for ln in lines:
        if ln["counted"] is None:
            result = "Not counted - stock left unchanged"
            delta = None
        else:
            item = db.execute("SELECT * FROM items WHERE id = ?", (ln["item_id"],)).fetchone()
            if item is None:
                result, delta = "Item no longer exists - skipped", None
            else:
                delta = ln["counted"] - ln["expected"]
                if delta == 0:
                    result = "Matches"
                else:
                    new_qty = item["quantity"] + delta
                    if new_qty < 0:
                        raise CountError(
                            409,
                            f"'{item['name']}': stock changed during the count, so applying "
                            f"{delta:+d} would make it negative. Recount this item.",
                        )
                    db.execute(
                        "UPDATE items SET quantity = ?, updated_at = datetime('now','localtime') "
                        "WHERE id = ?", (new_qty, item["id"]),
                    )
                    how = "photo count" if ln["source"] == "vision" else "manual count"
                    log_move(db, item["id"], item["name"], delta, new_qty, "Shift count",
                             f"Count #{count_id}: expected {ln['expected']}, counted "
                             f"{ln['counted']} ({how})", user)
                    result = f"Adjusted {delta:+d}"
                    changed += 1
        db.execute("UPDATE shift_count_lines SET applied_delta = ?, result = ? WHERE id = ?",
                   (delta, result, ln["id"]))
    out = get_count(db, count_id)
    out["items_adjusted"] = changed
    return out
