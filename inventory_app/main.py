"""Inventory Manager API: FastAPI + SQLite with token authentication.

Run with:  uvicorn main:app --reload
Docs at:   http://127.0.0.1:8000/docs

Default account (created on first run): admin / admin
Change it from the Account page after signing in.
"""
import base64
import hashlib
import hmac
import json
import secrets
import sqlite3
import threading
import time
from contextlib import contextmanager, asynccontextmanager
from datetime import datetime
from typing import Literal, Optional

from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException, Query
from pydantic import BaseModel, Field, ValidationError

import references
import shift_count
import vision

DB_PATH = "inventory.db"
TOKEN_TTL = 8 * 3600          # sessions last 8 hours
PBKDF2_ROUNDS = 200_000
MAX_FAILED_LOGINS = 5
LOCKOUT_SECONDS = 60

SECRET = ""                    # loaded from the database in init_db()
_failed_logins: dict = {}      # username -> {"count": int, "locked_until": float}

NOW = "datetime('now','localtime')"


# ---------- Database helpers ----------
@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def hash_password(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode(), bytes.fromhex(salt), PBKDF2_ROUNDS
    ).hex()


def add_column(db, table: str, name: str, ddl: str) -> None:
    """Add a column to an existing table (used to upgrade older databases)."""
    cols = {r["name"] for r in db.execute(f"PRAGMA table_info({table})").fetchall()}
    if name not in cols:
        db.execute(f"ALTER TABLE {table} ADD COLUMN {ddl}")


def log_move(db, item_id, item_name, delta, qty_after, reason, note, user, when=None, days_ago=None):
    """Write one row to the stock movement history."""
    if days_ago is None:
        db.execute(
            f"INSERT INTO movements (item_id, item_name, delta, quantity_after, reason, note, user, created_at) "
            f"VALUES (?, ?, ?, ?, ?, ?, ?, {NOW})",
            (item_id, item_name, delta, qty_after, reason, note, user),
        )
    else:
        db.execute(
            "INSERT INTO movements (item_id, item_name, delta, quantity_after, reason, note, user, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now','localtime', ?))",
            (item_id, item_name, delta, qty_after, reason, note, user, f"-{days_ago} days"),
        )


def seed_demo(db) -> None:
    """Demo suppliers, items and a realistic 40-day stock history."""
    suppliers = [
        ("TechSource Ltd", "Alex Morgan", "orders@techsource.example", "+1 555 0101"),
        ("OfficeHub Supplies", "Sam Rivera", "sales@officehub.example", "+1 555 0102"),
        ("HomeGoods Co", "Jordan Lee", "hello@homegoods.example", "+1 555 0103"),
    ]
    sup_ids = [
        db.execute("INSERT INTO suppliers (name, contact, email, phone) VALUES (?, ?, ?, ?)", s).lastrowid
        for s in suppliers
    ]
    # name, sku, category, price, cost, supplier index, alert level, reorder qty, history
    demo = [
        ("Laptop", "LAP-001", "Electronics", 899.99, 640.00, 0, 5, 5,
         [(40, 10, "Initial stock", ""), (30, -2, "Sale", ""),
          (20, 6, "Received", "Supplier delivery"), (12, -2, "Sale", "")]),
        ("USB-C Cable", "CAB-014", "Electronics", 9.99, 3.20, 0, 10, 30,
         [(40, 20, "Initial stock", ""), (28, -6, "Sale", ""), (18, -5, "Sale", ""),
          (9, -4, "Sale", ""), (3, -2, "Sale", "")]),
        ("Notebook", "NTB-120", "Stationery", 2.50, 0.90, 1, 15, 50,
         [(40, 60, "Initial stock", ""), (25, -8, "Sale", ""), (14, -6, "Sale", ""), (4, -6, "Sale", "")]),
        ("Ballpoint Pen", "PEN-050", "Stationery", 0.99, 0.25, 1, 20, 100,
         [(40, 50, "Initial stock", ""), (30, -15, "Sale", ""), (20, -12, "Sale", ""),
          (11, -10, "Sale", ""), (2, -5, "Sale", "")]),
        ("Desk Lamp", "LMP-007", "Furniture", 24.00, 11.50, 2, 4, 10,
         [(40, 10, "Initial stock", ""), (38, -2, "Sale", ""),
          (33, -2, "Damaged / lost", "Broken in storage")]),
    ]
    for name, sku, cat, price, cost, sup_idx, thr, reorder, history in demo:
        qty = sum(h[1] for h in history)
        cur = db.execute(
            "INSERT INTO items (name, sku, category, quantity, price, cost, supplier_id, "
            "reorder_qty, low_stock_threshold, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now','localtime', ?))",
            (name, sku, cat, qty, price, cost, sup_ids[sup_idx], reorder, thr, f"-{history[-1][0]} days"),
        )
        running = 0
        for days_ago, delta, reason, note in history:
            running += delta
            log_move(db, cur.lastrowid, name, delta, running, reason, note, "admin", days_ago=days_ago)


def init_db() -> None:
    global SECRET
    with get_db() as db:
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                category TEXT NOT NULL DEFAULT 'General',
                quantity INTEGER NOT NULL DEFAULT 0 CHECK (quantity >= 0),
                price REAL NOT NULL DEFAULT 0 CHECK (price >= 0),
                low_stock_threshold INTEGER NOT NULL DEFAULT 5,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        # Upgrade databases created by earlier versions
        add_column(db, "items", "sku", "sku TEXT")
        add_column(db, "items", "cost", "cost REAL NOT NULL DEFAULT 0")
        add_column(db, "items", "supplier_id", "supplier_id INTEGER")
        add_column(db, "items", "reorder_qty", "reorder_qty INTEGER NOT NULL DEFAULT 10")
        db.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_items_sku ON items(sku) WHERE sku IS NOT NULL")

        db.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE COLLATE NOCASE,
                salt TEXT NOT NULL,
                password_hash TEXT NOT NULL
            )
            """
        )
        db.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS suppliers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE COLLATE NOCASE,
                contact TEXT NOT NULL DEFAULT '',
                email TEXT NOT NULL DEFAULT '',
                phone TEXT NOT NULL DEFAULT ''
            )
            """
        )
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS movements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_id INTEGER,
                item_name TEXT NOT NULL,
                delta INTEGER NOT NULL,
                quantity_after INTEGER NOT NULL,
                reason TEXT NOT NULL,
                note TEXT NOT NULL DEFAULT '',
                user TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            )
            """
        )
        db.execute("CREATE INDEX IF NOT EXISTS idx_movements_item ON movements(item_id)")
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS purchase_orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                supplier_id INTEGER,
                status TEXT NOT NULL DEFAULT 'Ordered',
                note TEXT NOT NULL DEFAULT '',
                created_by TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                received_at TEXT
            )
            """
        )
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS purchase_order_lines (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                po_id INTEGER NOT NULL,
                item_id INTEGER NOT NULL,
                quantity INTEGER NOT NULL CHECK (quantity > 0),
                unit_cost REAL NOT NULL DEFAULT 0
            )
            """
        )

        shift_count.init_tables(db)
        references.init_tables(db)

        # Signing key for session tokens (kept in the DB so logins survive restarts)
        row = db.execute("SELECT value FROM meta WHERE key = 'secret'").fetchone()
        if row is None:
            SECRET = secrets.token_hex(32)
            db.execute("INSERT INTO meta (key, value) VALUES ('secret', ?)", (SECRET,))
        else:
            SECRET = row["value"]

        # Default admin account on first run
        if db.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0:
            salt = secrets.token_hex(16)
            db.execute(
                "INSERT INTO users (username, salt, password_hash) VALUES (?, ?, ?)",
                ("admin", salt, hash_password("admin", salt)),
            )

        if db.execute("SELECT COUNT(*) FROM items").fetchone()[0] == 0:
            seed_demo(db)
        elif db.execute("SELECT COUNT(*) FROM movements").fetchone()[0] == 0:
            # Older database: record today's stock as the opening balance
            for r in db.execute("SELECT id, name, quantity FROM items WHERE quantity > 0").fetchall():
                log_move(db, r["id"], r["name"], r["quantity"], r["quantity"],
                         "Initial stock", "Opening balance", "system")


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    threading.Thread(target=vision.warmup, daemon=True).start()   # load models in the background
    yield


app = FastAPI(title="Inventory Manager API", version="3.2.0", lifespan=lifespan)


# ---------- Authentication ----------
def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def make_token(username: str) -> str:
    payload = _b64(json.dumps({"u": username, "exp": int(time.time()) + TOKEN_TTL}).encode())
    sig = hmac.new(SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}.{sig}"


def read_token(token: str) -> Optional[str]:
    try:
        payload, sig = token.split(".", 1)
        expected = hmac.new(SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected):
            return None
        data = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        if data["exp"] < time.time():
            return None
        return data["u"]
    except (ValueError, KeyError, TypeError):
        return None


def require_auth(authorization: Optional[str] = Header(None)) -> str:
    unauthorized = HTTPException(
        status_code=401, detail="Not authenticated", headers={"WWW-Authenticate": "Bearer"}
    )
    if not authorization or not authorization.startswith("Bearer "):
        raise unauthorized
    username = read_token(authorization[7:])
    if username is None:
        raise unauthorized
    with get_db() as db:
        if db.execute("SELECT 1 FROM users WHERE username = ?", (username,)).fetchone() is None:
            raise unauthorized
    return username


class LoginIn(BaseModel):
    username: str = Field(..., min_length=1, max_length=64)
    password: str = Field(..., min_length=1, max_length=200)


class PasswordChange(BaseModel):
    current_password: str
    new_password: str = Field(..., min_length=6, max_length=200)


@app.post("/login")
def login(body: LoginIn):
    key = body.username.strip().lower()
    now = time.time()
    state = _failed_logins.get(key, {"count": 0, "locked_until": 0.0})
    if state["locked_until"] > now:
        wait = int(state["locked_until"] - now) + 1
        raise HTTPException(status_code=429, detail=f"Too many attempts. Try again in {wait}s.")

    with get_db() as db:
        row = db.execute(
            "SELECT * FROM users WHERE username = ?", (body.username.strip(),)
        ).fetchone()

    if row is not None:
        ok = hmac.compare_digest(hash_password(body.password, row["salt"]), row["password_hash"])
    else:
        hash_password(body.password, "00" * 16)  # keep timing similar for unknown users
        ok = False

    if not ok:
        state["count"] += 1
        if state["count"] >= MAX_FAILED_LOGINS:
            state = {"count": 0, "locked_until": now + LOCKOUT_SECONDS}
        _failed_logins[key] = state
        raise HTTPException(status_code=401, detail="Invalid username or password")

    _failed_logins.pop(key, None)
    return {"token": make_token(row["username"]), "username": row["username"],
            "expires_in": TOKEN_TTL}


# Everything below requires a valid token
router = APIRouter(dependencies=[Depends(require_auth)])


@router.get("/me")
def me(user: str = Depends(require_auth)):
    return {"username": user}


@router.post("/account/password")
def change_password(body: PasswordChange, user: str = Depends(require_auth)):
    with get_db() as db:
        row = db.execute("SELECT * FROM users WHERE username = ?", (user,)).fetchone()
        current = hash_password(body.current_password, row["salt"])
        if not hmac.compare_digest(current, row["password_hash"]):
            raise HTTPException(status_code=400, detail="Current password is incorrect")
        salt = secrets.token_hex(16)
        db.execute(
            "UPDATE users SET salt = ?, password_hash = ? WHERE id = ?",
            (salt, hash_password(body.new_password, salt), row["id"]),
        )
    return {"status": "updated"}


# ---------- Schemas ----------
class ItemIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    sku: Optional[str] = Field(None, max_length=40)
    category: str = Field("General", min_length=1, max_length=50)
    quantity: int = Field(0, ge=0)
    price: float = Field(0, ge=0)
    cost: float = Field(0, ge=0)
    supplier_id: Optional[int] = None
    reorder_qty: int = Field(10, ge=0)
    low_stock_threshold: int = Field(5, ge=0)


class ItemOut(ItemIn):
    id: int
    updated_at: str
    low_stock: bool
    supplier_name: Optional[str] = None


class StockAdjust(BaseModel):
    delta: int = Field(..., description="Positive to add stock, negative to remove")
    reason: str = Field("Adjustment", max_length=40)
    note: str = Field("", max_length=200)


class SupplierIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    contact: str = Field("", max_length=100)
    email: str = Field("", max_length=120)
    phone: str = Field("", max_length=40)


class POLine(BaseModel):
    item_id: int
    quantity: int = Field(..., gt=0)
    unit_cost: float = Field(0, ge=0)


class POIn(BaseModel):
    supplier_id: Optional[int] = None
    note: str = Field("", max_length=200)
    lines: list[POLine]


class ImportIn(BaseModel):
    rows: list[dict]


# ---------- Item helpers ----------
ITEM_SELECT = (
    "SELECT i.*, s.name AS supplier_name FROM items i "
    "LEFT JOIN suppliers s ON s.id = i.supplier_id"
)


def row_to_item(row: sqlite3.Row) -> dict:
    item = dict(row)
    item["low_stock"] = item["quantity"] <= item["low_stock_threshold"]
    return item


def get_or_404(db: sqlite3.Connection, item_id: int) -> sqlite3.Row:
    row = db.execute(ITEM_SELECT + " WHERE i.id = ?", (item_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"Item {item_id} not found")
    return row


def clean_sku(sku: Optional[str]) -> Optional[str]:
    return (sku or "").strip().upper() or None


def check_supplier(db, supplier_id: Optional[int]) -> None:
    if supplier_id is not None and db.execute(
        "SELECT 1 FROM suppliers WHERE id = ?", (supplier_id,)
    ).fetchone() is None:
        raise HTTPException(status_code=400, detail="Supplier not found")


def insert_item(db, item: ItemIn, user: str) -> int:
    check_supplier(db, item.supplier_id)
    name = item.name.strip()
    cur = db.execute(
        "INSERT INTO items (name, sku, category, quantity, price, cost, supplier_id, "
        f"reorder_qty, low_stock_threshold, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, {NOW})",
        (name, clean_sku(item.sku), item.category.strip(), item.quantity, item.price,
         item.cost, item.supplier_id, item.reorder_qty, item.low_stock_threshold),
    )
    if item.quantity > 0:
        log_move(db, cur.lastrowid, name, item.quantity, item.quantity, "Initial stock", "", user)
    return cur.lastrowid


DUPLICATE = "An item with that name or SKU already exists"


# ---------- Inventory endpoints ----------
@router.get("/items", response_model=list[ItemOut])
def list_items(
    search: Optional[str] = Query(None, description="Match on item name or SKU"),
    category: Optional[str] = None,
    low_stock_only: bool = False,
):
    query, params = ITEM_SELECT + " WHERE 1=1", []
    if search:
        query += " AND (i.name LIKE ? OR i.sku LIKE ?)"
        params += [f"%{search}%", f"%{search}%"]
    if category:
        query += " AND i.category = ?"
        params.append(category)
    query += " ORDER BY i.name COLLATE NOCASE"
    with get_db() as db:
        items = [row_to_item(r) for r in db.execute(query, params).fetchall()]
    if low_stock_only:
        items = [i for i in items if i["low_stock"]]
    return items


@router.post("/items/import")
def import_items(body: ImportIn, user: str = Depends(require_auth)):
    """Bulk-create items from parsed CSV rows. Existing names/SKUs are skipped."""
    created, skipped, errors = 0, [], []
    with get_db() as db:
        for n, raw in enumerate(body.rows, start=1):
            raw = dict(raw)
            supplier_name = str(raw.pop("supplier", "") or "").strip()
            try:
                item = ItemIn(**raw)
            except (ValidationError, TypeError) as exc:
                try:
                    first = exc.errors()[0]
                    msg = f"{'.'.join(str(p) for p in first['loc'])}: {first['msg']}"
                except Exception:
                    msg = "invalid row"
                errors.append({"row": n, "name": str(raw.get("name", "")), "error": msg})
                continue
            if supplier_name:
                found = db.execute("SELECT id FROM suppliers WHERE name = ?", (supplier_name,)).fetchone()
                item.supplier_id = found["id"] if found else db.execute(
                    "INSERT INTO suppliers (name) VALUES (?)", (supplier_name,)
                ).lastrowid
            try:
                db.execute("SAVEPOINT row_import")
                insert_item(db, item, user)
                db.execute("RELEASE row_import")
                created += 1
            except sqlite3.IntegrityError:
                db.execute("ROLLBACK TO row_import")
                db.execute("RELEASE row_import")
                skipped.append({"row": n, "name": item.name, "error": DUPLICATE})
    return {"created": created, "skipped": skipped, "errors": errors}


@router.get("/items/{item_id}", response_model=ItemOut)
def get_item(item_id: int):
    with get_db() as db:
        return row_to_item(get_or_404(db, item_id))


@router.post("/items", response_model=ItemOut, status_code=201)
def create_item(item: ItemIn, user: str = Depends(require_auth)):
    with get_db() as db:
        try:
            new_id = insert_item(db, item, user)
        except sqlite3.IntegrityError:
            raise HTTPException(status_code=409, detail=DUPLICATE)
        return row_to_item(get_or_404(db, new_id))


@router.put("/items/{item_id}", response_model=ItemOut)
def update_item(item_id: int, item: ItemIn, user: str = Depends(require_auth)):
    with get_db() as db:
        old = get_or_404(db, item_id)
        check_supplier(db, item.supplier_id)
        name = item.name.strip()
        try:
            db.execute(
                "UPDATE items SET name=?, sku=?, category=?, quantity=?, price=?, cost=?, "
                f"supplier_id=?, reorder_qty=?, low_stock_threshold=?, updated_at={NOW} WHERE id=?",
                (name, clean_sku(item.sku), item.category.strip(), item.quantity, item.price,
                 item.cost, item.supplier_id, item.reorder_qty, item.low_stock_threshold, item_id),
            )
        except sqlite3.IntegrityError:
            raise HTTPException(status_code=409, detail=DUPLICATE)
        if name != old["name"]:
            db.execute("UPDATE movements SET item_name = ? WHERE item_id = ?", (name, item_id))
        if item.quantity != old["quantity"]:
            log_move(db, item_id, name, item.quantity - old["quantity"], item.quantity,
                     "Correction", "Changed in item details", user)
        return row_to_item(get_or_404(db, item_id))


@router.post("/items/{item_id}/adjust", response_model=ItemOut)
def adjust_stock(item_id: int, body: StockAdjust, user: str = Depends(require_auth)):
    if body.delta == 0:
        raise HTTPException(status_code=400, detail="Enter a quantity greater than zero")
    with get_db() as db:
        row = get_or_404(db, item_id)
        new_qty = row["quantity"] + body.delta
        if new_qty < 0:
            raise HTTPException(status_code=400, detail="Not enough stock for that removal")
        db.execute(f"UPDATE items SET quantity=?, updated_at={NOW} WHERE id=?", (new_qty, item_id))
        log_move(db, item_id, row["name"], body.delta, new_qty,
                 body.reason.strip() or "Adjustment", body.note.strip(), user)
        return row_to_item(get_or_404(db, item_id))


@router.delete("/items/{item_id}", status_code=204)
def delete_item(item_id: int, user: str = Depends(require_auth)):
    with get_db() as db:
        row = get_or_404(db, item_id)
        open_po = db.execute(
            "SELECT p.id FROM purchase_order_lines l JOIN purchase_orders p ON p.id = l.po_id "
            "WHERE l.item_id = ? AND p.status = 'Ordered' LIMIT 1", (item_id,),
        ).fetchone()
        if open_po:
            raise HTTPException(status_code=409,
                                detail=f"This item is on open purchase order #{open_po['id']}")
        log_move(db, item_id, row["name"], -row["quantity"], 0, "Item deleted", "", user)
        references.delete_for_item(db, item_id)
        db.execute("DELETE FROM items WHERE id = ?", (item_id,))


# ---------- Stock movement history ----------
@router.get("/movements")
def list_movements(
    item_id: Optional[int] = None,
    reason: Optional[str] = None,
    days: Optional[int] = Query(None, ge=1),
    limit: int = Query(500, ge=1, le=5000),
):
    query, params = "SELECT * FROM movements WHERE 1=1", []
    if item_id is not None:
        query += " AND item_id = ?"
        params.append(item_id)
    if reason:
        query += " AND reason = ?"
        params.append(reason)
    if days:
        query += " AND created_at >= datetime('now','localtime', ?)"
        params.append(f"-{days} days")
    query += " ORDER BY created_at DESC, id DESC LIMIT ?"
    params.append(limit)
    with get_db() as db:
        return [dict(r) for r in db.execute(query, params).fetchall()]


# ---------- Suppliers ----------
@router.get("/suppliers")
def list_suppliers():
    with get_db() as db:
        rows = db.execute(
            "SELECT s.*, (SELECT COUNT(*) FROM items i WHERE i.supplier_id = s.id) AS item_count "
            "FROM suppliers s ORDER BY s.name COLLATE NOCASE"
        ).fetchall()
    return [dict(r) for r in rows]


@router.post("/suppliers", status_code=201)
def create_supplier(body: SupplierIn):
    with get_db() as db:
        try:
            cur = db.execute(
                "INSERT INTO suppliers (name, contact, email, phone) VALUES (?, ?, ?, ?)",
                (body.name.strip(), body.contact.strip(), body.email.strip(), body.phone.strip()),
            )
        except sqlite3.IntegrityError:
            raise HTTPException(status_code=409, detail="A supplier with that name already exists")
        return dict(db.execute("SELECT * FROM suppliers WHERE id = ?", (cur.lastrowid,)).fetchone())


@router.put("/suppliers/{supplier_id}")
def update_supplier(supplier_id: int, body: SupplierIn):
    with get_db() as db:
        if db.execute("SELECT 1 FROM suppliers WHERE id = ?", (supplier_id,)).fetchone() is None:
            raise HTTPException(status_code=404, detail="Supplier not found")
        try:
            db.execute(
                "UPDATE suppliers SET name=?, contact=?, email=?, phone=? WHERE id=?",
                (body.name.strip(), body.contact.strip(), body.email.strip(),
                 body.phone.strip(), supplier_id),
            )
        except sqlite3.IntegrityError:
            raise HTTPException(status_code=409, detail="A supplier with that name already exists")
        return dict(db.execute("SELECT * FROM suppliers WHERE id = ?", (supplier_id,)).fetchone())


@router.delete("/suppliers/{supplier_id}", status_code=204)
def delete_supplier(supplier_id: int):
    with get_db() as db:
        if db.execute("SELECT 1 FROM suppliers WHERE id = ?", (supplier_id,)).fetchone() is None:
            raise HTTPException(status_code=404, detail="Supplier not found")
        open_po = db.execute(
            "SELECT id FROM purchase_orders WHERE supplier_id = ? AND status = 'Ordered' LIMIT 1",
            (supplier_id,),
        ).fetchone()
        if open_po:
            raise HTTPException(status_code=409,
                                detail=f"This supplier has open purchase order #{open_po['id']}")
        db.execute("UPDATE items SET supplier_id = NULL WHERE supplier_id = ?", (supplier_id,))
        db.execute("DELETE FROM suppliers WHERE id = ?", (supplier_id,))


# ---------- Purchase orders ----------
def po_to_dict(db, row: sqlite3.Row) -> dict:
    po = dict(row)
    lines = db.execute(
        "SELECT l.item_id, l.quantity, l.unit_cost, i.name AS item_name, i.sku "
        "FROM purchase_order_lines l LEFT JOIN items i ON i.id = l.item_id "
        "WHERE l.po_id = ? ORDER BY l.id", (po["id"],),
    ).fetchall()
    po["lines"] = [dict(line) for line in lines]
    po["total"] = round(sum(line["quantity"] * line["unit_cost"] for line in po["lines"]), 2)
    return po


PO_SELECT = (
    "SELECT p.*, s.name AS supplier_name FROM purchase_orders p "
    "LEFT JOIN suppliers s ON s.id = p.supplier_id"
)


@router.get("/purchase-orders")
def list_purchase_orders(status: Optional[str] = None):
    query, params = PO_SELECT + " WHERE 1=1", []
    if status:
        query += " AND p.status = ?"
        params.append(status)
    query += " ORDER BY p.id DESC"
    with get_db() as db:
        return [po_to_dict(db, r) for r in db.execute(query, params).fetchall()]


@router.post("/purchase-orders", status_code=201)
def create_purchase_order(body: POIn, user: str = Depends(require_auth)):
    if not body.lines:
        raise HTTPException(status_code=400, detail="A purchase order needs at least one line")
    with get_db() as db:
        check_supplier(db, body.supplier_id)
        cur = db.execute(
            "INSERT INTO purchase_orders (supplier_id, status, note, created_by, created_at) "
            f"VALUES (?, 'Ordered', ?, ?, {NOW})",
            (body.supplier_id, body.note.strip(), user),
        )
        po_id = cur.lastrowid
        for line in body.lines:
            item = db.execute("SELECT cost FROM items WHERE id = ?", (line.item_id,)).fetchone()
            if item is None:
                raise HTTPException(status_code=400, detail=f"Item {line.item_id} not found")
            unit_cost = line.unit_cost if line.unit_cost > 0 else item["cost"]
            db.execute(
                "INSERT INTO purchase_order_lines (po_id, item_id, quantity, unit_cost) VALUES (?, ?, ?, ?)",
                (po_id, line.item_id, line.quantity, unit_cost),
            )
        return po_to_dict(db, db.execute(PO_SELECT + " WHERE p.id = ?", (po_id,)).fetchone())


def _open_po_or_error(db, po_id: int) -> sqlite3.Row:
    row = db.execute(PO_SELECT + " WHERE p.id = ?", (po_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Purchase order not found")
    if row["status"] != "Ordered":
        raise HTTPException(status_code=409, detail=f"This order is already {row['status'].lower()}")
    return row


@router.post("/purchase-orders/{po_id}/receive")
def receive_purchase_order(po_id: int, user: str = Depends(require_auth)):
    """Add the ordered quantities to stock and mark the order as received."""
    with get_db() as db:
        _open_po_or_error(db, po_id)
        lines = db.execute(
            "SELECT * FROM purchase_order_lines WHERE po_id = ?", (po_id,)
        ).fetchall()
        for line in lines:
            item = db.execute("SELECT * FROM items WHERE id = ?", (line["item_id"],)).fetchone()
            if item is None:
                continue
            new_qty = item["quantity"] + line["quantity"]
            new_cost = line["unit_cost"] if line["unit_cost"] > 0 else item["cost"]
            db.execute(
                f"UPDATE items SET quantity=?, cost=?, updated_at={NOW} WHERE id=?",
                (new_qty, new_cost, item["id"]),
            )
            log_move(db, item["id"], item["name"], line["quantity"], new_qty,
                     "Received", f"PO #{po_id}", user)
        db.execute(
            f"UPDATE purchase_orders SET status='Received', received_at={NOW} WHERE id=?", (po_id,)
        )
        return po_to_dict(db, db.execute(PO_SELECT + " WHERE p.id = ?", (po_id,)).fetchone())


@router.post("/purchase-orders/{po_id}/cancel")
def cancel_purchase_order(po_id: int):
    with get_db() as db:
        _open_po_or_error(db, po_id)
        db.execute("UPDATE purchase_orders SET status='Cancelled' WHERE id=?", (po_id,))
        return po_to_dict(db, db.execute(PO_SELECT + " WHERE p.id = ?", (po_id,)).fetchone())


@router.get("/reorder-suggestions")
def reorder_suggestions():
    """Low-stock items with a suggested order quantity.

    Suggested = (alert level - on hand) + reorder quantity - already on order.
    """
    with get_db() as db:
        incoming = {
            r["item_id"]: r["q"]
            for r in db.execute(
                "SELECT l.item_id, SUM(l.quantity) AS q FROM purchase_order_lines l "
                "JOIN purchase_orders p ON p.id = l.po_id WHERE p.status = 'Ordered' "
                "GROUP BY l.item_id"
            ).fetchall()
        }
        items = [row_to_item(r) for r in db.execute(ITEM_SELECT + " ORDER BY i.name COLLATE NOCASE").fetchall()]
    out = []
    for item in items:
        if not item["low_stock"]:
            continue
        on_order = incoming.get(item["id"], 0)
        suggested = (item["low_stock_threshold"] - item["quantity"]) + item["reorder_qty"] - on_order
        if suggested > 0:
            item["on_order"] = on_order
            item["suggested_qty"] = suggested
            out.append(item)
    return out


# ---------- Reports ----------
@router.get("/reports/slow-movers")
def slow_movers(days: int = Query(30, ge=1, le=730)):
    """In-stock items with no outbound movement for at least `days` days."""
    with get_db() as db:
        rows = db.execute(
            "SELECT i.id, i.name, i.sku, i.category, i.quantity, i.cost, "
            "(SELECT MAX(created_at) FROM movements m WHERE m.item_id = i.id AND m.delta < 0) AS last_out, "
            "(SELECT MIN(created_at) FROM movements m WHERE m.item_id = i.id) AS first_seen "
            "FROM items i WHERE i.quantity > 0"
        ).fetchall()
    now, out = datetime.now(), []
    for r in rows:
        ref = r["last_out"] or r["first_seen"]
        try:
            idle = (now - datetime.strptime(ref, "%Y-%m-%d %H:%M:%S")).days if ref else days
        except ValueError:
            continue
        if idle >= days:
            item = dict(r)
            item["days_idle"] = idle
            item["stock_value"] = round(r["quantity"] * r["cost"], 2)
            out.append(item)
    return sorted(out, key=lambda x: x["stock_value"], reverse=True)


@router.get("/stats")
def stats():
    with get_db() as db:
        rows = [row_to_item(r) for r in db.execute("SELECT * FROM items").fetchall()]
        open_pos = db.execute(
            "SELECT COUNT(*) FROM purchase_orders WHERE status = 'Ordered'"
        ).fetchone()[0]
    cost_value = round(sum(r["quantity"] * r["cost"] for r in rows), 2)
    retail_value = round(sum(r["quantity"] * r["price"] for r in rows), 2)
    return {
        "total_items": len(rows),
        "total_units": sum(r["quantity"] for r in rows),
        "cost_value": cost_value,
        "retail_value": retail_value,
        "total_value": retail_value,
        "low_stock_count": sum(1 for r in rows if r["low_stock"]),
        "open_purchase_orders": open_pos,
        "categories": sorted({r["category"] for r in rows}),
    }


# ---------- End-of-shift count ----------
class CountStart(BaseModel):
    note: str = Field("", max_length=200)


class CountLineIn(BaseModel):
    counted: Optional[int] = Field(None, ge=0, le=1_000_000)
    detected: Optional[int] = Field(None, ge=0, le=1_000_000)
    source: Literal["manual", "vision"] = "manual"
    label: str = Field("", max_length=100)
    confidence: Optional[float] = Field(None, ge=0, le=1)


class CountApprove(BaseModel):
    allow_uncounted: bool = False


def count_call(fn, *args, **kwargs):
    """Run a shift_count operation in one transaction; turn its errors into HTTP errors.
    Nothing is saved if it fails (get_db only commits when no exception escapes)."""
    try:
        with get_db() as db:
            return fn(db, *args, **kwargs)
    except shift_count.CountError as exc:
        raise HTTPException(status_code=exc.status, detail=exc.detail)


@router.get("/counts")
def counts_history(limit: int = Query(50, ge=1, le=500)):
    return count_call(shift_count.list_counts, limit)


@router.get("/counts/current")
def counts_current():
    return count_call(shift_count.current_count)


@router.post("/counts", status_code=201)
def counts_start(body: CountStart, user: str = Depends(require_auth)):
    return count_call(shift_count.start_count, user, body.note)


@router.get("/counts/{count_id}")
def counts_get(count_id: int):
    return count_call(shift_count.get_count, count_id)


@router.put("/counts/{count_id}/lines/{line_id}")
def counts_update_line(count_id: int, line_id: int, body: CountLineIn):
    return count_call(shift_count.update_line, count_id, line_id, body.counted, body.detected,
                      body.source, body.label, body.confidence)


@router.post("/counts/{count_id}/approve")
def counts_approve(count_id: int, body: CountApprove, user: str = Depends(require_auth)):
    return count_call(shift_count.approve, count_id, user, log_move, body.allow_uncounted)


@router.post("/counts/{count_id}/cancel")
def counts_cancel(count_id: int, user: str = Depends(require_auth)):
    return count_call(shift_count.cancel, count_id, user)


class VisionIn(BaseModel):
    image: str
    conf: float = Field(0.25, ge=0.05, le=0.95)
    min_similarity: float = Field(0.80, ge=0.30, le=0.99)


class ReferenceIn(BaseModel):
    item_id: int
    image: str


def ref_call(fn, *args, **kwargs):
    try:
        with get_db() as db:
            return fn(db, *args, **kwargs)
    except references.RefError as exc:
        raise HTTPException(status_code=exc.status, detail=exc.detail)


@router.get("/vision/status")
def vision_status():
    info = vision.status()
    with get_db() as db:
        _, ref_items, _ = references.load_index(db, vision.EMBED_MODEL)
    info["references"] = len(ref_items)
    info["items_with_references"] = len(set(ref_items))
    return info


@router.post("/vision/count")
def vision_count(body: VisionIn):
    with get_db() as db:
        ref_vecs, ref_items, names = references.load_index(db, vision.EMBED_MODEL)
    try:
        if ref_items and vision.recognizer_available():
            return vision.recognize(body.image, ref_vecs, ref_items, names, conf=body.conf,
                                    min_sim=body.min_similarity)
        result = vision.detect(body.image, conf=body.conf)
        if ref_items:
            result["notice"] = ("Reference photos exist but product recognition is not installed, "
                                "so generic labels are shown. Run: pip install -r requirements-vision.txt")
        return result
    except vision.VisionError as exc:
        raise HTTPException(status_code=exc.status, detail=exc.detail)


@router.get("/references/summary")
def references_summary():
    return ref_call(references.summary)


@router.get("/references")
def references_list(item_id: int):
    return ref_call(references.list_references, item_id)


@router.post("/references", status_code=201)
def references_add(body: ReferenceIn, user: str = Depends(require_auth)):
    with get_db() as db:
        if db.execute("SELECT 1 FROM items WHERE id = ?", (body.item_id,)).fetchone() is None:
            raise HTTPException(status_code=404, detail="Item not found")
    try:
        image = vision.decode_image(body.image)
    except vision.VisionError as exc:
        raise HTTPException(status_code=exc.status, detail=exc.detail)
    embeddings, warning = None, ""
    if vision.recognizer_available():
        try:
            embeddings = vision.reference_vectors(image)
        except vision.VisionError as exc:      # keep the photo even if the model failed
            warning = exc.detail
    else:
        warning = ("Photo saved, but product recognition is not installed so nothing was learned yet. "
                   "Run: pip install -r requirements-vision.txt")
    jpeg, thumb = vision.storage_bytes(image)
    result = ref_call(references.add_reference, body.item_id, jpeg, thumb, embeddings,
                      vision.EMBED_MODEL, user)
    result["warning"] = warning
    return result


@router.delete("/references/{ref_id}", status_code=204)
def references_delete(ref_id: int):
    ref_call(references.delete_reference, ref_id)


app.include_router(router)
