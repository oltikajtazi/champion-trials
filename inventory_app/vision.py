"""Count items in a photo.

Two modes:
  * generic   - the YOLO detector's own labels (only ~80 everyday object types).
  * items     - YOLO only FINDS objects; each one is then identified by comparing it with the
                reference photos the manager uploaded (CLIP image fingerprints). This is how
                your own products (pens, staplers, ...) are recognised correctly.

Everything here is optional: without the models, counts are simply typed in by hand.

Install:   pip install -r requirements-vision.txt
Weights:   set INVENTORY_MODEL to the path of your own trained .pt file (recommended).
           The default `yolov8n.pt` is a general model that only knows ~80 everyday
           object types (bottle, cup, box-like items...), NOT your specific products.
           For reliable counts of your own products, train a model on photos of them.
"""
import base64
import binascii
import importlib.util
import io
import os
import threading
from typing import Optional

import numpy as np
from PIL import Image, ImageDraw, ImageOps

MODEL_PATH = os.environ.get("INVENTORY_MODEL", "yolov8n.pt")
EMBED_MODEL = os.environ.get("INVENTORY_EMBED_MODEL", "openai/clip-vit-base-patch32")
MAX_SIDE = 1600           # larger photos are shrunk (faster, same accuracy for counting)
MAX_BYTES = 15_000_000    # refuse absurdly large uploads

_model = None
_lock = threading.Lock()
_embedder = None
_embed_lock = threading.Lock()
UNRECOGNIZED = "Unrecognized"
MAX_CROPS = 60
MIN_CROP_SIDE = 16


class VisionError(Exception):
    """status 503 = model not available, 400 = bad image."""

    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status = status
        self.detail = detail


def available() -> bool:
    return importlib.util.find_spec("ultralytics") is not None


def recognizer_available() -> bool:
    """True when both the detector and the fingerprint model libraries are installed."""
    return (available() and importlib.util.find_spec("transformers") is not None
            and importlib.util.find_spec("torch") is not None)


def status() -> dict:
    return {"available": available(), "recognizer": recognizer_available(),
            "model": MODEL_PATH, "embed_model": EMBED_MODEL}


def warmup() -> None:
    """Load the models in the background at start-up so the first photo is not slow."""
    try:
        if available():
            load_model()
        if recognizer_available():
            load_embedder()
    except Exception:
        pass   # the real error is reported when a photo is actually processed


def load_model():
    global _model
    with _lock:
        if _model is None:
            if not available():
                raise VisionError(503, "The vision model is not installed. Run: "
                                       "pip install -r requirements-vision.txt (counts can still be typed in).")
            try:
                from ultralytics import YOLO
                _model = YOLO(MODEL_PATH)
            except Exception as exc:  # bad path, download failure, corrupt weights
                raise VisionError(503, f"Could not load the vision model '{MODEL_PATH}': {exc}")
        return _model


def decode_image(data: str) -> Image.Image:
    """Base64 (optionally a data: URL) -> RGB image, rotated upright, capped in size."""
    if not data:
        raise VisionError(400, "No image received.")
    if data.startswith("data:") and "," in data:
        data = data.split(",", 1)[1]
    try:
        raw = base64.b64decode(data, validate=True)
    except (binascii.Error, ValueError):
        raise VisionError(400, "The image data is not valid.")
    if len(raw) > MAX_BYTES:
        raise VisionError(400, "The image is too large (limit 15 MB).")
    try:
        img = Image.open(io.BytesIO(raw))
        img.load()
    except Exception:
        raise VisionError(400, "That file is not a readable image.")
    img = ImageOps.exif_transpose(img).convert("RGB")   # phones store rotation in EXIF
    img.thumbnail((MAX_SIDE, MAX_SIDE))
    return img


def run(image: Image.Image, conf: float = 0.25, model=None, agnostic: bool = False) -> list:
    """Run the detector. Returns [{label, confidence, box:[x1,y1,x2,y2]}]."""
    model = model or load_model()
    try:
        result = model.predict(image, conf=conf, verbose=False, agnostic_nms=agnostic)[0]
    except Exception as exc:
        raise VisionError(503, f"The vision model failed on this image: {exc}")
    names = result.names
    out = []
    for box in result.boxes:
        cls = int(box.cls[0])
        out.append({
            "label": str(names[cls]),
            "confidence": round(float(box.conf[0]), 3),
            "box": [round(float(v), 1) for v in box.xyxy[0].tolist()],
        })
    return out


def summarize(detections: list) -> dict:
    """{label: {"count": n, "avg_confidence": x}}  (one entry per detected label)."""
    groups: dict = {}
    for d in detections:
        groups.setdefault(d["label"], []).append(d["confidence"])
    return {
        label: {"count": len(c), "avg_confidence": round(sum(c) / len(c), 3)}
        for label, c in sorted(groups.items(), key=lambda kv: (kv[0] == UNRECOGNIZED, -len(kv[1])))
    }


def annotate(image: Image.Image, detections: list) -> str:
    """Draw numbered boxes so a person can check the count by eye. Returns base64 JPEG."""
    img = image.copy()
    draw = ImageDraw.Draw(img)
    width = max(2, img.width // 400)
    for n, d in enumerate(detections, 1):
        x1, y1, x2, y2 = d["box"]
        tag = f"{n} {d['label']}" if d.get("label") else f"{n}"
        tw = 7 * len(tag) + 6
        unknown = d.get("label") == UNRECOGNIZED
        colour = (220, 38, 38) if unknown else (37, 99, 235)
        draw.rectangle([x1, y1, x2, y2], outline=colour, width=width)
        draw.rectangle([x1, y1, x1 + tw, y1 + 16], fill=colour)
        draw.text((x1 + 3, y1 + 2), tag, fill=(255, 255, 255))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return base64.b64encode(buf.getvalue()).decode()


def detect(image_b64: str, conf: float = 0.25, model: Optional[object] = None) -> dict:
    image = decode_image(image_b64)
    detections = run(image, conf=conf, model=model)
    return {
        "mode": "generic",
        "model": MODEL_PATH,
        "conf": conf,
        "width": image.width,
        "height": image.height,
        "total": len(detections),
        "labels": summarize(detections),
        "annotated": annotate(image, detections),
    }


# ---------- Recognising your own products (reference photos) ----------
def load_embedder():
    global _embedder
    with _embed_lock:
        if _embedder is None:
            if not recognizer_available():
                raise VisionError(503, "Product recognition is not installed. Run: "
                                       "pip install -r requirements-vision.txt")
            try:
                from transformers import CLIPModel, CLIPProcessor
                _embedder = (CLIPModel.from_pretrained(EMBED_MODEL).eval(),
                             CLIPProcessor.from_pretrained(EMBED_MODEL))
            except Exception as exc:
                raise VisionError(503, f"Could not load the recognition model '{EMBED_MODEL}': {exc}")
        return _embedder


def _as_tensor(out):
    """Different library versions return a tensor or an object holding one."""
    import torch
    if torch.is_tensor(out):
        return out
    for name in ("image_embeds", "pooler_output"):
        value = getattr(out, name, None)
        if value is not None:
            return value
    return out[0]


def embed(images: list) -> np.ndarray:
    """PIL images -> (n, d) float32 fingerprints."""
    if not images:
        return np.zeros((0, 0), dtype=np.float32)
    import torch
    model, processor = load_embedder()
    chunks = []
    try:
        for i in range(0, len(images), 16):
            batch = images[i:i + 16]
            with torch.no_grad():
                inputs = processor(images=batch, return_tensors="pt")
                feats = _as_tensor(model.get_image_features(**inputs))
            chunks.append(feats.detach().cpu().numpy().astype(np.float32))
    except VisionError:
        raise
    except Exception as exc:
        raise VisionError(503, f"The recognition model failed: {exc}")
    return np.vstack(chunks)


def crop_objects(image: Image.Image, boxes: list) -> tuple:
    """Cut each box out of the photo (with a little margin). Returns (crops, kept_boxes)."""
    crops, kept = [], []
    for b in boxes:
        x1, y1, x2, y2 = b["box"]
        pad_x, pad_y = (x2 - x1) * 0.05, (y2 - y1) * 0.05
        box = (max(0, int(x1 - pad_x)), max(0, int(y1 - pad_y)),
               min(image.width, int(x2 + pad_x)), min(image.height, int(y2 + pad_y)))
        if box[2] - box[0] < MIN_CROP_SIDE or box[3] - box[1] < MIN_CROP_SIDE:
            continue
        crops.append(image.crop(box))
        kept.append(b)
    return crops, kept


def find_objects(image: Image.Image, conf: float, model=None) -> list:
    """Where are the objects? (the detector's own label is ignored in this mode)"""
    found = run(image, conf=conf, model=model, agnostic=True)
    found.sort(key=lambda d: -d["confidence"])
    return found[:MAX_CROPS]


def reference_vectors(image: Image.Image, conf: float = 0.10, model=None, embed_fn=None) -> np.ndarray:
    """Fingerprints for a delivery photo: one per object found, or the whole photo if none found.

    The manager is asked to photograph ONE product type per photo, so everything found in
    it is an example of that product.
    """
    embed_fn = embed_fn or embed
    boxes = find_objects(image, conf, model)
    crops, _ = crop_objects(image, boxes)
    if not crops:
        crops = [image]
    return embed_fn(crops)


def storage_bytes(image: Image.Image) -> tuple:
    """(photo JPEG, thumbnail JPEG) for saving in the database."""
    full = io.BytesIO()
    image.save(full, format="JPEG", quality=85)
    small = image.copy()
    small.thumbnail((160, 160))
    thumb = io.BytesIO()
    small.save(thumb, format="JPEG", quality=80)
    return full.getvalue(), thumb.getvalue()


def recognize(image_b64: str, ref_vecs, ref_items: list, names: dict, conf: float = 0.15,
              min_sim: float = 0.80, margin: float = 0.02, model=None, embed_fn=None) -> dict:
    """Find objects, then name each one by its closest reference photos."""
    import references
    embed_fn = embed_fn or embed
    image = decode_image(image_b64)
    boxes = find_objects(image, conf, model)
    crops, kept = crop_objects(image, boxes)
    detections = []
    if crops:
        matches = references.match(embed_fn(crops), ref_vecs, ref_items, min_sim=min_sim, margin=margin)
        for box, (item_id, score) in zip(kept, matches):
            detections.append({
                "label": names.get(item_id, UNRECOGNIZED) if item_id is not None else UNRECOGNIZED,
                "confidence": score, "box": box["box"],
            })
    labels = summarize(detections)
    return {
        "mode": "items",
        "model": f"{MODEL_PATH} + {EMBED_MODEL}",
        "conf": conf,
        "min_similarity": min_sim,
        "width": image.width,
        "height": image.height,
        "total": len(detections),
        "unrecognized": labels.get(UNRECOGNIZED, {}).get("count", 0),
        "labels": labels,
        "annotated": annotate(image, detections),
    }
