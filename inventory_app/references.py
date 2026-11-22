"""Reference photos: what each product looks like, and matching new crops against them.

The manager uploads photos of a delivery. Every object found in a photo is turned into a
numeric "fingerprint" (embedding) and stored against that item. Later, when stock is
counted from a photo, each object is compared with the stored fingerprints and given
the name of the closest item, or "Unrecognized" if nothing is close enough.

Pure sqlite3 + numpy (no web framework, no AI model) so it can be tested alone.
"""
import base64
from typing import Optional

import numpy as np

UNRECOGNIZED = "Unrecognized"


class RefError(Exception):
    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status = status
        self.detail = detail


def init_tables(db) -> None:
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS reference_images (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id INTEGER NOT NULL,
            image BLOB NOT NULL,
            thumb BLOB NOT NULL,
            created_by TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL
        )
        """
    )
    db.execute("CREATE INDEX IF NOT EXISTS idx_refimg_item ON reference_images(item_id)")
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS reference_embeddings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ref_id INTEGER NOT NULL,
            item_id INTEGER NOT NULL,
            model TEXT NOT NULL,
            embedding BLOB NOT NULL
        )
        """
    )
    db.execute("CREATE INDEX IF NOT EXISTS idx_refemb_item ON reference_embeddings(item_id)")


def add_reference(db, item_id: int, image: bytes, thumb: bytes, embeddings: Optional[np.ndarray],
                  model: str, user: str) -> dict:
    if db.execute("SELECT 1 FROM items WHERE id = ?", (item_id,)).fetchone() is None:
        raise RefError(404, "Item not found")
    cur = db.execute(
        "INSERT INTO reference_images (item_id, image, thumb, created_by, created_at) "
        "VALUES (?, ?, ?, ?, datetime('now','localtime'))", (item_id, image, thumb, user),
    )
    ref_id = cur.lastrowid
    shapes = 0
    if embeddings is not None and len(embeddings):
        arr = np.asarray(embeddings, dtype=np.float32)
        db.executemany(
            "INSERT INTO reference_embeddings (ref_id, item_id, model, embedding) VALUES (?, ?, ?, ?)",
            [(ref_id, item_id, model, row.tobytes()) for row in arr],
        )
        shapes = len(arr)
    return {"id": ref_id, "item_id": item_id, "shapes": shapes, "learned": shapes > 0}


def list_references(db, item_id: int) -> list:
    rows = db.execute(
        "SELECT r.id, r.item_id, r.thumb, r.created_by, r.created_at, "
        "(SELECT COUNT(*) FROM reference_embeddings e WHERE e.ref_id = r.id) AS shapes "
        "FROM reference_images r WHERE r.item_id = ? ORDER BY r.id DESC", (item_id,),
    ).fetchall()
    return [{
        "id": r["id"], "item_id": r["item_id"], "created_by": r["created_by"],
        "created_at": r["created_at"], "shapes": r["shapes"],
        "thumb": base64.b64encode(r["thumb"]).decode(),
    } for r in rows]


def delete_reference(db, ref_id: int) -> None:
    if db.execute("SELECT 1 FROM reference_images WHERE id = ?", (ref_id,)).fetchone() is None:
        raise RefError(404, "Reference photo not found")
    db.execute("DELETE FROM reference_embeddings WHERE ref_id = ?", (ref_id,))
    db.execute("DELETE FROM reference_images WHERE id = ?", (ref_id,))


def delete_for_item(db, item_id: int) -> None:
    db.execute("DELETE FROM reference_embeddings WHERE item_id = ?", (item_id,))
    db.execute("DELETE FROM reference_images WHERE item_id = ?", (item_id,))


def summary(db) -> list:
    rows = db.execute(
        "SELECT i.id AS item_id, i.name, "
        "(SELECT COUNT(*) FROM reference_images r WHERE r.item_id = i.id) AS photos, "
        "(SELECT COUNT(*) FROM reference_embeddings e WHERE e.item_id = i.id) AS shapes "
        "FROM items i ORDER BY i.name COLLATE NOCASE"
    ).fetchall()
    return [dict(r) for r in rows]


def load_index(db, model: str):
    """All stored fingerprints for `model`: (matrix, item_id per row, {item_id: name})."""
    rows = db.execute(
        "SELECT e.item_id, e.embedding, i.name FROM reference_embeddings e "
        "JOIN items i ON i.id = e.item_id WHERE e.model = ?", (model,),
    ).fetchall()
    if not rows:
        return np.zeros((0, 0), dtype=np.float32), [], {}
    vecs = np.vstack([np.frombuffer(r["embedding"], dtype=np.float32) for r in rows])
    return vecs, [r["item_id"] for r in rows], {r["item_id"]: r["name"] for r in rows}


def normalize(arr: np.ndarray) -> np.ndarray:
    arr = np.asarray(arr, dtype=np.float32)
    norms = np.linalg.norm(arr, axis=1, keepdims=True)
    return arr / np.maximum(norms, 1e-9)


def match(embs: np.ndarray, ref_vecs: np.ndarray, ref_items: list,
          min_sim: float = 0.80, margin: float = 0.02, topk: int = 3) -> list:
    """For each object fingerprint return (item_id or None, score).

    Score of an item = average of its `topk` closest reference fingerprints.
    An object is accepted only if the best item scores >= min_sim AND beats the
    second-best item by at least `margin` (so look-alike products are not guessed).
    """
    n = len(embs)
    if n == 0:
        return []
    if len(ref_items) == 0:
        return [(None, 0.0)] * n
    sims = normalize(embs) @ normalize(ref_vecs).T                 # (n, refs)
    items = sorted(set(ref_items))
    owner = np.array(ref_items)
    scores = np.full((n, len(items)), -1.0, dtype=np.float32)
    for j, item in enumerate(items):
        cols = sims[:, owner == item]
        k = min(topk, cols.shape[1])
        top = -np.sort(-cols, axis=1)[:, :k]
        scores[:, j] = top.mean(axis=1)
    out = []
    for row in scores:
        order = np.argsort(-row)
        best = float(row[order[0]])
        second = float(row[order[1]]) if len(items) > 1 else -1.0
        if best >= min_sim and (best - second) >= margin:
            out.append((items[int(order[0])], round(best, 3)))
        else:
            out.append((None, round(best, 3)))
    return out
