# ▶️ RUN ME: Mini Inventory App

A FastAPI + SQLite backend with a Streamlit front end.

## 📁 Project structure
```
inventory_app/
├── main.py            # FastAPI backend (API + SQLite)
├── shift_count.py     # End-of-shift count logic
├── vision.py          # Photo counting + product recognition (optional models)
├── references.py      # Delivery reference photos and matching
├── app.py             # Streamlit front end (sidebar UI)
├── .streamlit/
│   └── config.toml    # Theme settings (keep this folder!)
├── requirements.txt   # Libraries to install
├── requirements-vision.txt  # Optional: photo counting
├── RUN_ME.md          # This file
└── README.md          # Short overview
```
(`inventory.db` is created automatically the first time the backend starts.)

## 📚 Libraries needed
| Library | Used for |
|---|---|
| fastapi | Backend API |
| uvicorn[standard] | Server that runs FastAPI |
| streamlit | Front end |
| requests | Front end talks to the API |
| pandas | Tables and charts |

Python 3.9+ is required. Streamlit 1.40 or newer is needed for the redesigned interface. Altair (charts) is installed automatically with Streamlit. `sqlite3` is built into Python.

## 🚀 Steps

### 1. Open a terminal in the `inventory_app` folder
```bash
cd inventory_app
```

### 2. (Recommended) Create a virtual environment
```bash
python -m venv venv
```
Activate it:
- **Windows:** `venv\Scripts\activate`
- **Mac / Linux:** `source venv/bin/activate`

### 3. Install the libraries
```bash
pip install -r requirements.txt
```
Or install them manually:
```bash
pip install fastapi "uvicorn[standard]" streamlit requests pandas
```

### 4. Start the backend (Terminal 1)
```bash
uvicorn main:app --reload
```
Leave it running. API docs: http://127.0.0.1:8000/docs

### 5. Start the front end (Terminal 2)
Open a **second** terminal in the same folder (activate the venv again), then:
```bash
streamlit run app.py
```
The app opens at http://localhost:8501 and shows a sign-in screen.

### 6. Sign in
| Username | Password |
|---|---|
| `admin` | `admin` |

Change the password from the **Account** page after your first sign-in. Use the sidebar to switch between Dashboard, Inventory, Add Item, Manage Stock, Purchasing, Activity, Reports and Account. Always start Streamlit from inside the project folder so the theme in `.streamlit/config.toml` is applied.

## 🛠️ Troubleshooting
- **"Cannot reach the server"**: the backend (step 4) isn't running, or it is on a different address than the front end expects (default `http://127.0.0.1:8000`).
- **`uvicorn` not found**: the venv isn't activated, or use `python -m uvicorn main:app --reload`.
- **Port already in use**: start the backend on another port, e.g. `uvicorn main:app --reload --port 8001`, then tell the front end where it is before launching it:
  - Mac / Linux: `INVENTORY_API_URL=http://127.0.0.1:8001 streamlit run app.py`
  - Windows (PowerShell): `$env:INVENTORY_API_URL="http://127.0.0.1:8001"; streamlit run app.py`
- **Reset the data**: stop the backend and delete `inventory.db`; demo items and the default `admin` / `admin` account are re-created on the next start.
- **Forgot your password**: do the reset above (this also deletes your items), or stop the backend and delete only the `users` row with any SQLite tool.
- **Locked out**: after 5 wrong passwords, sign-in is blocked for 60 seconds.
- **Signed out after refreshing the page**: expected. Sign in again.

## What is in the app
| Page | What it does |
|---|---|
| Dashboard | Stock value at cost and retail, low-stock alerts, charts, recent activity |
| Inventory | Search by name or SKU (barcode scanners work), filter, margin, CSV export |
| Add Item | Add one item (SKU, cost, supplier, reorder quantity) or **import many from a CSV** |
| Receive Stock | Record a delivery and add photos so the app learns what each product looks like |
| Shift Count | Count stock at the end of a shift (photo or typed), compare with the system, approve to update stock |
| Manage Stock | Add or remove stock with a reason and note, per-item history, edit, delete |
| Purchasing | **Reorder suggestions**, purchase orders (receive them to update stock), suppliers |
| Activity | Full audit trail of every stock movement, filterable, exportable |
| Reports | **ABC analysis** (80/20 rule), **slow-moving stock**, inventory valuation |
| Account | Change your password |

## Importing from a spreadsheet
Add Item -> Import from CSV. Download the template, fill it in, upload it. Only `name` is required.
Existing names or SKUs are skipped, and unknown suppliers are created automatically.

## Upgrading an older database
Just start the backend. Missing columns and tables are added automatically, and today's stock is
recorded as the opening balance in the activity history. Delete `inventory.db` only if you want
a fresh start with the demo data.
