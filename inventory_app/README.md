# Mini Inventory App

FastAPI + SQLite backend with a Streamlit front end.

## Setup
```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

## Run (two terminals, both in this folder)
```bash
# Terminal 1: backend
uvicorn main:app --reload

# Terminal 2: front end
streamlit run app.py
```

- App:      http://localhost:8501
- API docs: http://127.0.0.1:8000/docs

The database (`inventory.db`) is created automatically with a few demo items on first run.

## Features
- Add, edit, delete, and search items; filter by category
- Quick +/- stock adjustment
- Low-stock alerts (per-item threshold)
- Dashboard metrics, charts, CSV export
- Validation (no negative stock/price, unique names) with clear error messages

## Interface
Sign-in screen, then sidebar navigation: Dashboard, Inventory, Add Item (single or CSV import),
Manage Stock, Receive Stock (delivery photos), Shift Count (end-of-shift count), Purchasing (reorder suggestions, purchase orders, suppliers), Activity (audit trail),
Reports (ABC analysis, slow-moving stock, valuation) and Account (change password).

## Users and roles
Two roles: **admin** (everything) and **worker** (day-to-day stock work).
- Workers see Inventory, Manage Stock (adjust + history), Receive Stock, Shift Count and Account. They cannot
  see costs, margins or stock value, edit or delete items, use Purchasing/Reports/Activity, or approve a count.
- Admins also manage accounts on the **Users** page (add, reset password, delete).
- Roles are enforced by the API, not just hidden in the menu.
- From the command line: `python add_user.py "name" "password" worker` (also resets an existing user).
- Accounts that existed before roles were added stay admins.

## Security
- Default login: `admin` / `admin` (change it on the Account page).
- Passwords are stored as salted PBKDF2 hashes; sessions use signed tokens that expire after 8 hours.
- Every inventory endpoint requires a valid token, so the API cannot be used without signing in.
- 5 failed sign-ins lock that username for 60 seconds.

## End-of-shift count (Shift Count page)
1. **Start count** records the stock the system expects for every item.
2. For each item, count it from a **photo** or **type the number**. You can edit a photo count before saving.
3. Review the table, then **Approve**. Only differences are applied, each one is written to Activity
   with the reason "Shift count".

Rules the app enforces:
- Only one count can be open at a time.
- Items you did not count are left unchanged (never set to zero).
- Approval applies `counted - expected`, so sales or deliveries recorded while you were counting are kept.
- If a change would make stock negative, nothing is saved and you are asked to recount that item.
- A count can only be approved once.

### Photo counting (optional)
```bash
pip install -r requirements-vision.txt     # large download (PyTorch)
set INVENTORY_MODEL=C:\path\to\my_model.pt   # Windows; on Mac/Linux: export INVENTORY_MODEL=...
uvicorn main:app --reload
```
- Without this the page still works; counts are typed in.
- The default detector (`yolov8n.pt`) only knows ~80 everyday objects and will name your products wrongly
  (e.g. pens as knives). That is why the **Receive Stock** page exists, see below.
- Photos work best with one layer of items, every unit visible, good light. Stacked or hidden items
  will be under-counted, so always glance at the numbered boxes before saving.
- `ultralytics` is licensed AGPL-3.0; check that suits you if you distribute the app commercially.

### Receive Stock page: teaching the app your products
1. Open **Receive Stock**, pick the item, add photos of the delivery (one product type per photo,
   items spread out and fully visible, plain background, 3 to 5 photos), optionally enter the units received
   and press **Save delivery**. Stock is only changed if you enter units, and only after every photo saved.
2. The detector finds each object in the photo. Each one is turned into a numeric "fingerprint"
   (CLIP image model) and stored for that item.
3. In **Shift Count**, objects are now named by comparing them with those fingerprints, so you see
   "Pens: 12" instead of "knife: 12". Objects that match nothing are shown as **Unrecognized** (red boxes).

Tuning: use **Match strictness** in Detection settings. Raise it if wrong items get matched, lower it if
too many real items are "Unrecognized". The **Reference photos** tab lets you review or delete photos.

Limits: the detector must first find each object as a box. Items piled on top of each other, or very small,
may be missed, so always check the boxes before saving. First start downloads the models (about 600 MB).
You can change the fingerprint model with the `INVENTORY_EMBED_MODEL` environment variable; photos learned
with another model are ignored until re-added.
