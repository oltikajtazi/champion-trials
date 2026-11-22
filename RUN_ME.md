# ▶️ RUN ME: Mini Inventory App

A FastAPI + SQLite backend with a Streamlit front end.

## 📁 Project structure
```
inventory_app/
├── main.py            # FastAPI backend (API + SQLite)
├── app.py             # Streamlit front end
├── requirements.txt   # Libraries to install
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

Python 3.9+ is required. `sqlite3` is built into Python.

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
The app opens at http://localhost:8501

## 🛠️ Troubleshooting
- **"Cannot reach the API"**: the backend (step 4) isn't running, or the API URL in the Streamlit sidebar is wrong (default `http://127.0.0.1:8000`).
- **`uvicorn` not found**: the venv isn't activated, or use `python -m uvicorn main:app --reload`.
- **Port already in use**: run `uvicorn main:app --reload --port 8001` and set the sidebar API URL to `http://127.0.0.1:8001`.
- **Reset the data**: stop the backend and delete `inventory.db`; demo items are re-created on the next start.
