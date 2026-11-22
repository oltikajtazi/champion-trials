"""Inventory Manager: Streamlit front end.

Run with:  streamlit run app.py
(The FastAPI backend must be running first.)
"""
import base64
import hashlib
import html
import io
import os
from urllib.parse import quote

import altair as alt
import pandas as pd
import requests
import streamlit as st
from PIL import Image, ImageOps

st.set_page_config(
    page_title="Inventory Manager",
    page_icon=":material/inventory_2:",
    layout="wide",
    initial_sidebar_state="expanded",
)

ACCENT = "#2563EB"
ADMIN_PAGES = ["Dashboard", "Inventory", "Add Item", "Manage Stock", "Receive Stock", "Shift Count",
               "Purchasing", "Activity", "Reports", "Users", "Account"]
WORKER_PAGES = ["Inventory", "Manage Stock", "Receive Stock", "Shift Count", "Account"]

# Backend address is configured outside the UI (environment variable).
API_URL = os.environ.get("INVENTORY_API_URL", "http://127.0.0.1:8000").rstrip("/")

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

html, body, .stApp, .stMarkdown, button, input, textarea, select {
    font-family: 'Inter', -apple-system, 'Segoe UI', sans-serif;
}
#MainMenu, footer, .stDeployButton { visibility: hidden; }
header[data-testid="stHeader"] { background: transparent; }
.block-container { padding-top: 2.2rem; padding-bottom: 3rem; max-width: 1280px; }

/* ---------- Sidebar ---------- */
section[data-testid="stSidebar"] {
    background: #0F172A;
    border-right: none;
}
section[data-testid="stSidebar"] > div { padding-top: 1.2rem; }
section[data-testid="stSidebar"] * { color: #CBD5E1; }
section[data-testid="stSidebar"] input { color: #0F172A !important; }

.brand { display: flex; align-items: center; gap: 12px; padding: 4px 6px 22px 6px; }
.brand .logo {
    width: 38px; height: 38px; border-radius: 10px; background: #2563EB;
    display: flex; align-items: center; justify-content: center;
    font-weight: 700; font-size: 14px; color: #fff !important; letter-spacing: .04em;
}
.brand .name { font-size: 15px; font-weight: 600; color: #F8FAFC !important; line-height: 1.2; }
.brand .sub { font-size: 12px; color: #64748B !important; }
.nav-label {
    font-size: 11px; font-weight: 600; letter-spacing: .1em; text-transform: uppercase;
    color: #64748B !important; padding: 0 8px 8px 8px;
}

section[data-testid="stSidebar"] div[role="radiogroup"] { gap: 4px; }
section[data-testid="stSidebar"] div[role="radiogroup"] > label {
    width: 100%; padding: 10px 14px; border-radius: 8px; cursor: pointer;
    transition: background .15s ease;
}
section[data-testid="stSidebar"] div[role="radiogroup"] > label:hover { background: #1E293B; }
section[data-testid="stSidebar"] div[role="radiogroup"] > label > div:first-child { display: none; }
section[data-testid="stSidebar"] div[role="radiogroup"] > label:has(input:checked) { background: #2563EB; }
section[data-testid="stSidebar"] div[role="radiogroup"] > label:has(input:checked) * {
    color: #FFFFFF !important; font-weight: 600;
}
section[data-testid="stSidebar"] .stButton > button {
    width: 100%; background: transparent; border: 1px solid #334155; justify-content: center;
}
section[data-testid="stSidebar"] .stButton > button:hover {
    background: #1E293B; border-color: #475569;
}
.side-status {
    display: flex; align-items: center; gap: 8px; font-size: 12.5px;
    padding: 10px 8px; margin-top: 8px; border-top: 1px solid #1E293B;
}
.dot { width: 8px; height: 8px; border-radius: 50%; display: inline-block; }
.dot.ok { background: #22C55E; }
.dot.bad { background: #EF4444; }

/* ---------- Page header ---------- */
.page-title { font-size: 26px; font-weight: 700; color: #0F172A; margin: 0; letter-spacing: -.01em; }
.page-sub { font-size: 14px; color: #64748B; margin: 4px 0 24px 0; }
.section-title { font-size: 15px; font-weight: 600; color: #0F172A; margin: 0 0 2px 0; }
.section-sub { font-size: 12.5px; color: #64748B; margin: 0 0 12px 0; }

/* ---------- KPI cards ---------- */
.kpi {
    background: #FFFFFF; border: 1px solid #E5E7EB; border-radius: 12px;
    padding: 18px 20px; height: 100%;
}
.kpi .label {
    font-size: 11.5px; font-weight: 600; letter-spacing: .06em;
    text-transform: uppercase; color: #64748B;
}
.kpi .value { font-size: 28px; font-weight: 700; color: #0F172A; margin-top: 8px; line-height: 1.1; }
.kpi .sub { font-size: 12.5px; color: #94A3B8; margin-top: 6px; }
.kpi.alert .value { color: #B45309; }
.kpi.alert { border-left: 3px solid #F59E0B; }

/* ---------- Containers ---------- */
div[data-testid="stVerticalBlockBorderWrapper"] { border-radius: 12px; border-color: #E5E7EB; background: #FFFFFF; }
div[data-testid="stForm"] {
    background: #FFFFFF; border: 1px solid #E5E7EB; border-radius: 12px; padding: 24px;
}
div[data-testid="stTabs"] button[role="tab"] { font-weight: 500; }
.stButton > button, .stDownloadButton > button, .stFormSubmitButton > button {
    border-radius: 8px; font-weight: 500;
}
</style>
"""

LOGIN_CSS = """
<style>
section[data-testid="stSidebar"], [data-testid="stSidebarCollapsedControl"] { display: none; }
.login-brand { display: flex; align-items: center; gap: 12px; margin-bottom: 28px; }
.login-brand .logo {
    width: 42px; height: 42px; border-radius: 11px; background: #2563EB; color: #fff;
    display: flex; align-items: center; justify-content: center;
    font-weight: 700; font-size: 15px; letter-spacing: .04em;
}
.login-brand .name { font-size: 17px; font-weight: 600; color: #0F172A; }
.login-title { font-size: 24px; font-weight: 700; color: #0F172A; margin: 0 0 4px 0; }
.login-sub { font-size: 14px; color: #64748B; margin: 0 0 18px 0; }
.stFormSubmitButton > button { width: 100%; }
</style>
"""

st.markdown(CSS, unsafe_allow_html=True)


# ---------- Helpers ----------
def api(method: str, path: str, **kwargs):
    """Call the backend and return (data, error_message)."""
    headers = {"Authorization": f"Bearer {st.session_state.get('token', '')}"}
    kwargs.setdefault("timeout", 5)
    try:
        resp = requests.request(method, f"{API_URL}{path}", headers=headers, **kwargs)
    except requests.exceptions.RequestException:
        return None, "Cannot reach the server. Make sure the backend is running."
    if resp.status_code == 401:
        sign_out("Your session has expired. Please sign in again.")
    if resp.status_code >= 400:
        try:
            detail = resp.json().get("detail", resp.text)
        except ValueError:
            detail = resp.text
        if isinstance(detail, list):
            detail = "; ".join(d.get("msg", "Invalid input") for d in detail)
        return None, str(detail)
    return (resp.json() if resp.content else True), None


def load_items(search="", category="All", low_only=False):
    params = {"low_stock_only": low_only}
    if search:
        params["search"] = search
    if category and category != "All":
        params["category"] = category
    return api("GET", "/items", params=params)


def flash(message: str) -> None:
    """Show a toast on the next run (survives st.rerun)."""
    st.session_state["_flash"] = message


def money(value: float) -> str:
    return f"${value:,.2f}"


def stock_status(row) -> str:
    if row["quantity"] == 0:
        return "Out of stock"
    return "Low stock" if row["low_stock"] else "In stock"


def header(title: str, subtitle: str) -> None:
    st.markdown(f'<p class="page-title">{title}</p><p class="page-sub">{subtitle}</p>',
                unsafe_allow_html=True)


def section(title: str, subtitle: str = "") -> None:
    sub = f'<p class="section-sub">{subtitle}</p>' if subtitle else ""
    st.markdown(f'<p class="section-title">{title}</p>{sub}', unsafe_allow_html=True)


def kpi(col, label: str, value: str, sub: str = "", alert: bool = False) -> None:
    cls = "kpi alert" if alert else "kpi"
    col.markdown(
        f'<div class="{cls}"><div class="label">{label}</div>'
        f'<div class="value">{value}</div><div class="sub">{sub}</div></div>',
        unsafe_allow_html=True,
    )


def bar_chart(df: pd.DataFrame, category: str, value: str, fmt: str, color: str = "") -> None:
    mark = alt.Chart(df).mark_bar(cornerRadiusEnd=4, size=20, **({} if color else {"color": ACCENT}))
    chart = (
        mark
        .encode(
            **({"color": alt.Color(f"{color}:N", title="Class", scale=alt.Scale(
                domain=["A", "B", "C"], range=[ACCENT, "#60A5FA", "#CBD5E1"]))} if color else {}),
            y=alt.Y(f"{category}:N", sort="-x", title=None, axis=alt.Axis(labelLimit=200)),
            x=alt.X(f"{value}:Q", title=None,
                    axis=alt.Axis(format=fmt, gridColor="#EEF1F5")),
            tooltip=[alt.Tooltip(f"{category}:N"), alt.Tooltip(f"{value}:Q", format=fmt)],
        )
        .properties(height=max(120, 42 * len(df)))
        .configure_view(strokeWidth=0)
        .configure_axis(domain=False, labelColor="#475569", tickColor="transparent",
                        labelFontSize=12)
    )
    st.altair_chart(chart)


def items_frame(items: list) -> pd.DataFrame:
    df = pd.DataFrame(items)
    df["cost_value"] = df["quantity"] * df["cost"]
    df["retail_value"] = df["quantity"] * df["price"]
    df["margin"] = ((df["price"] - df["cost"]) / df["price"] * 100).where(df["price"] > 0)
    df["status"] = df.apply(stock_status, axis=1)
    return df


def get_suppliers() -> list:
    data, err = api("GET", "/suppliers")
    if err:
        st.error(err)
        return []
    return data or []


def signed(delta: int) -> str:
    return f"+{delta}" if delta > 0 else str(delta)


def movements_frame(rows: list) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    df["change"] = df["delta"].map(signed)
    return df


MOVE_COLUMNS = ["created_at", "item_name", "change", "quantity_after", "reason", "note", "user"]
MOVE_CONFIG = {
    "created_at": "When", "item_name": "Item", "change": "Change",
    "quantity_after": "Stock after", "reason": "Reason", "note": "Note", "user": "User",
}
REASONS_IN = ["Received", "Return", "Correction"]
REASONS_OUT = ["Sale", "Damaged / lost", "Correction"]
INT_FIELDS = {"quantity", "low_stock_threshold", "reorder_qty"}
FLOAT_FIELDS = {"price", "cost"}
CSV_FIELDS = ["name", "sku", "category", "quantity", "cost", "price",
              "low_stock_threshold", "reorder_qty", "supplier"]
CSV_ALIASES = {
    "item": "name", "product": "name", "product_name": "name", "item_name": "name",
    "barcode": "sku", "stock": "quantity", "qty": "quantity", "on_hand": "quantity",
    "cost_price": "cost", "selling_price": "price", "sell_price": "price", "unit_price": "price",
    "alert_level": "low_stock_threshold", "alert": "low_stock_threshold",
    "reorder_quantity": "reorder_qty",
}
CSV_TEMPLATE = (
    "name,sku,category,quantity,cost,price,low_stock_threshold,reorder_qty,supplier\n"
    "Wireless Mouse,MSE-001,Electronics,25,8.50,19.99,5,20,TechSource Ltd\n"
)


def item_form_fields(defaults: dict, suppliers: list) -> dict:
    """Render the shared item fields inside a form and return the payload."""
    sup_ids = [None] + [s["id"] for s in suppliers]
    sup_names = {s["id"]: s["name"] for s in suppliers}
    c1, c2, c3 = st.columns(3)
    name = c1.text_input("Item name", defaults.get("name", ""), placeholder="e.g. Wireless Mouse")
    sku = c2.text_input("SKU / barcode", defaults.get("sku") or "",
                        help="Unique code. A barcode scanner types straight into this field.")
    category = c3.text_input("Category", defaults.get("category", "General"))
    c4, c5, c6 = st.columns(3)
    qty = c4.number_input("Quantity on hand", min_value=0, step=1,
                          value=int(defaults.get("quantity", 0)))
    cost = c5.number_input("Cost price ($)", min_value=0.0, step=0.5, format="%.2f",
                           value=float(defaults.get("cost", 0.0)))
    price = c6.number_input("Selling price ($)", min_value=0.0, step=0.5, format="%.2f",
                            value=float(defaults.get("price", 0.0)))
    c7, c8, c9 = st.columns(3)
    thresh = c7.number_input("Low-stock alert level", min_value=0, step=1,
                             value=int(defaults.get("low_stock_threshold", 5)))
    reorder = c8.number_input("Reorder quantity", min_value=0, step=1,
                              value=int(defaults.get("reorder_qty", 10)),
                              help="How many units to order in one batch when stock runs low.")
    current = defaults.get("supplier_id")
    supplier = c9.selectbox("Supplier", sup_ids,
                            index=sup_ids.index(current) if current in sup_ids else 0,
                            format_func=lambda i: "None" if i is None else sup_names[i])
    return {
        "name": name.strip(), "sku": sku.strip() or None,
        "category": category.strip() or "General", "quantity": int(qty),
        "cost": float(cost), "price": float(price), "low_stock_threshold": int(thresh),
        "reorder_qty": int(reorder), "supplier_id": supplier,
    }


def sign_out(notice: str) -> None:
    for key in ("token", "user", "role"):
        st.session_state.pop(key, None)
    st.session_state["_notice"] = notice
    st.rerun()


def do_login(username: str, password: str):
    """Return None on success, or an error message."""
    try:
        resp = requests.post(f"{API_URL}/login", timeout=5,
                             json={"username": username.strip(), "password": password})
    except requests.exceptions.RequestException:
        return "Cannot reach the server. Make sure the backend is running."
    if resp.status_code == 200:
        data = resp.json()
        st.session_state["token"] = data["token"]
        st.session_state["user"] = data["username"]
        st.session_state["role"] = data.get("role", "worker")
        return None
    try:
        return str(resp.json().get("detail", "Sign in failed"))
    except ValueError:
        return "Sign in failed"


def login_screen() -> None:
    st.markdown(LOGIN_CSS, unsafe_allow_html=True)
    _, middle, _ = st.columns([1, 1.1, 1])
    with middle:
        st.write("")
        st.write("")
        st.markdown(
            '<div class="login-brand"><div class="logo">IM</div>'
            '<div class="name">Inventory Manager</div></div>'
            '<p class="login-title">Sign in</p>'
            '<p class="login-sub">Enter your credentials to access the inventory.</p>',
            unsafe_allow_html=True,
        )
        notice = st.session_state.pop("_notice", None)
        if notice:
            st.info(notice)
        with st.form("login_form"):
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Sign in", type="primary")
        if submitted:
            if not username.strip() or not password:
                st.error("Enter your username and password.")
            else:
                error = do_login(username, password)
                if error:
                    st.error(error)
                else:
                    st.rerun()


# Gate: nothing below runs until the user is signed in
if "token" not in st.session_state:
    login_screen()
    st.stop()


IS_ADMIN = st.session_state.get("role") == "admin"


# ---------- Sidebar ----------
with st.sidebar:
    st.markdown(
        '<div class="brand"><div class="logo">IM</div><div>'
        '<div class="name">Inventory Manager</div><div class="sub">Stock control</div>'
        '</div></div><div class="nav-label">Menu</div>',
        unsafe_allow_html=True,
    )
    page = st.radio("Navigation", ADMIN_PAGES if IS_ADMIN else WORKER_PAGES,
                    label_visibility="collapsed")
    st.write("")

stats, stats_err = api("GET", "/stats")

with st.sidebar:
    if stats_err:
        st.markdown('<div class="side-status"><span class="dot bad"></span>API offline</div>',
                    unsafe_allow_html=True)
    else:
        low = stats["low_stock_count"]
        note = f"{low} item{'s' if low != 1 else ''} low on stock" if low else "All stock healthy"
        st.markdown(
            f'<div class="side-status"><span class="dot ok"></span>Connected &middot; {note}</div>',
            unsafe_allow_html=True,
        )
    user = html.escape(st.session_state.get("user", ""))
    st.markdown(f'<div class="side-status">Signed in as&nbsp;<b>{user}</b>'
                f'&nbsp;({"admin" if IS_ADMIN else "worker"})</div>',
                unsafe_allow_html=True)
    if st.button("Sign out", icon=":material/logout:", key="signout"):
        sign_out("You have been signed out.")

if "_flash" in st.session_state:
    st.toast(st.session_state.pop("_flash"))

if stats_err:
    header("Connection error", "The front end could not reach the backend service.")
    st.error(stats_err)
    st.code("uvicorn main:app --reload", language="bash")
    st.stop()


# ---------- Pages ----------
def page_dashboard():
    header("Dashboard", "Overview of current stock levels, inventory value and recent activity")

    items, err = load_items()
    if err:
        st.error(err)
        return
    df = items_frame(items) if items else pd.DataFrame()

    cost_value, retail_value = stats["cost_value"], stats["retail_value"]
    margin = (retail_value - cost_value) / retail_value * 100 if retail_value else 0
    cols = st.columns(4)
    kpi(cols[0], "Products", f"{stats['total_items']:,}", f"{stats['total_units']:,} units in stock")
    kpi(cols[1], "Stock value (cost)", money(cost_value), "What the stock cost you")
    kpi(cols[2], "Retail value", money(retail_value), f"Potential margin {margin:.0f}%")
    kpi(cols[3], "Needs attention", f"{stats['low_stock_count']}",
        f"{stats['open_purchase_orders']} open purchase order(s)",
        alert=stats["low_stock_count"] > 0)
    st.write("")

    if df.empty:
        st.info("No items yet. Add your first item from the sidebar.")
        return

    by_cat = df.groupby("category", as_index=False).agg(units=("quantity", "sum"),
                                                        value=("cost_value", "sum"))
    left, right = st.columns(2)
    with left, st.container(border=True):
        section("Stock value by category", "Value of stock on hand, at cost price")
        bar_chart(by_cat, "category", "value", "$,.0f")
    with right, st.container(border=True):
        section("Units by category", "Number of units currently in stock")
        bar_chart(by_cat, "category", "units", ",.0f")

    left, right = st.columns(2)
    with left, st.container(border=True):
        section("Items needing attention", "At or below their alert level. Reorder from Purchasing.")
        attention = df[df["low_stock"]]
        if attention.empty:
            st.caption("Nothing to report. All products are above their alert levels.")
        else:
            st.dataframe(
                attention[["name", "quantity", "low_stock_threshold", "status"]],
                hide_index=True,
                column_config={"name": "Item", "quantity": "On hand",
                               "low_stock_threshold": "Alert level", "status": "Status"},
            )
    with right, st.container(border=True):
        section("Recent activity", "Latest stock movements")
        moves, merr = api("GET", "/movements", params={"limit": 8})
        if merr:
            st.error(merr)
        elif not moves:
            st.caption("No stock movements yet.")
        else:
            st.dataframe(movements_frame(moves)[["created_at", "item_name", "change", "reason"]],
                         hide_index=True,
                         column_config={"created_at": "When", "item_name": "Item",
                                        "change": "Change", "reason": "Reason"})


def page_inventory():
    header("Inventory", "Search by name or SKU, filter and export your full product list")

    with st.container(border=True):
        f1, f2, f3 = st.columns([3, 2, 1.5], vertical_alignment="bottom")
        search = f1.text_input("Search", placeholder="Item name or SKU (scan a barcode here)")
        category = f2.selectbox("Category", ["All"] + stats["categories"])
        low_only = f3.toggle("Low stock only")

    items, err = load_items(search, category, low_only)
    if err:
        st.error(err)
        return
    if not items:
        st.info("No items match the current filters.")
        return

    df = items_frame(items)
    st.caption(f"{len(df)} item{'s' if len(df) != 1 else ''}")
    cols_shown = ["id", "sku", "name", "category", "supplier_name", "quantity", "cost", "price",
                  "margin", "cost_value", "low_stock_threshold", "status", "updated_at"]
    if not IS_ADMIN:
        cols_shown = [c for c in cols_shown if c not in ("cost", "margin", "cost_value")]
    st.dataframe(
        df[cols_shown],
        hide_index=True,
        height=min(600, 38 * (len(df) + 1) + 3),
        column_config={
            "id": st.column_config.NumberColumn("ID", width="small"),
            "sku": "SKU", "name": "Item", "category": "Category", "supplier_name": "Supplier",
            "quantity": st.column_config.NumberColumn("On hand"),
            "cost": st.column_config.NumberColumn("Cost", format="$%.2f"),
            "price": st.column_config.NumberColumn("Price", format="$%.2f"),
            "margin": st.column_config.NumberColumn("Margin", format="%.0f%%"),
            "cost_value": st.column_config.NumberColumn("Stock value", format="$%.2f"),
            "low_stock_threshold": st.column_config.NumberColumn("Alert level"),
            "status": "Status", "updated_at": "Last updated",
        },
    )
    if IS_ADMIN:
        st.download_button(
            "Export CSV",
            df[["name", "sku", "category", "quantity", "cost", "price", "low_stock_threshold",
                "reorder_qty", "supplier_name"]].rename(columns={"supplier_name": "supplier"})
              .to_csv(index=False),
            file_name="inventory.csv", mime="text/csv", icon=":material/download:",
        )


def csv_to_rows(raw: pd.DataFrame) -> list:
    """Turn the uploaded CSV into the row dicts the API expects."""
    rows = []
    for rec in raw.to_dict("records"):
        row = {}
        for key in CSV_FIELDS:
            val = str(rec.get(key, "")).strip()
            if val == "":
                continue
            if key in INT_FIELDS:
                try:
                    row[key] = int(float(val))
                except ValueError:
                    row[key] = val
            elif key in FLOAT_FIELDS:
                try:
                    row[key] = float(val.replace("$", "").replace(",", ""))
                except ValueError:
                    row[key] = val
            else:
                row[key] = val
        rows.append(row)
    return rows


def page_add():
    header("Add Item", "Register a single product, or import many from a spreadsheet")
    tab_single, tab_import = st.tabs(["Single item", "Import from CSV"])

    with tab_single:
        suppliers = get_suppliers()
        form_col, _ = st.columns([4, 1])
        with form_col, st.form("add_form", clear_on_submit=True):
            payload = item_form_fields({}, suppliers)
            submitted = st.form_submit_button("Add item", type="primary")
        if submitted:
            if not payload["name"]:
                st.error("Item name is required.")
            else:
                _, err = api("POST", "/items", json=payload)
                if err:
                    st.error(err)
                else:
                    flash(f"Added {payload['name']}")
                    st.rerun()

    with tab_import:
        result = st.session_state.pop("_import_result", None)
        if result:
            st.success(f"Imported {result['created']} item(s).")
            for label, rows in (("Skipped (already exist)", result["skipped"]),
                                ("Rows with errors", result["errors"])):
                if rows:
                    st.warning(f"{label}: {len(rows)}")
                    st.dataframe(pd.DataFrame(rows), hide_index=True)

        with st.container(border=True):
            section("Move off spreadsheets",
                    "Upload a CSV with a header row. Only a name column is required. "
                    "Items that already exist (same name or SKU) are skipped.")
            st.caption("Recognised columns: " + ", ".join(CSV_FIELDS))
            st.download_button("Download CSV template", CSV_TEMPLATE,
                               file_name="inventory_template.csv", mime="text/csv",
                               icon=":material/download:")
        upload = st.file_uploader("CSV file", type=["csv"])
        if upload is not None:
            try:
                raw = pd.read_csv(upload, dtype=str, keep_default_na=False)
            except Exception as exc:  # unreadable or empty file
                st.error(f"Could not read the file: {exc}")
                return
            raw.columns = [c.strip().lower().replace(" ", "_") for c in raw.columns]
            raw = raw.rename(columns=CSV_ALIASES)
            if "name" not in raw.columns:
                st.error("The file needs a 'name' column (or 'item' / 'product').")
                return
            known = [c for c in raw.columns if c in CSV_FIELDS]
            ignored = [c for c in raw.columns if c not in CSV_FIELDS]
            st.caption(f"{len(raw)} row(s) found. Using columns: {', '.join(known)}."
                       + (f" Ignoring: {', '.join(ignored)}." if ignored else ""))
            st.dataframe(raw[known].head(10), hide_index=True)
            if st.button(f"Import {len(raw)} row(s)", type="primary", icon=":material/upload:"):
                data, err = api("POST", "/items/import", json={"rows": csv_to_rows(raw)})
                if err:
                    st.error(err)
                else:
                    st.session_state["_import_result"] = data
                    st.rerun()


def page_manage():
    header("Manage Stock", "Adjust quantities, review history, edit product details or remove items")
    items, err = load_items()
    if err:
        st.error(err)
        return
    if not items:
        st.info("No items to manage yet.")
        return

    by_id = {i["id"]: i for i in items}
    item_id = st.selectbox(
        "Select an item", list(by_id),
        format_func=lambda i: f"{by_id[i]['name']}  ({by_id[i]['sku'] or 'no SKU'})",
    )
    item = by_id[item_id]

    cols = st.columns(4)
    kpi(cols[0], "On hand", f"{item['quantity']:,}", "Units in stock")
    if IS_ADMIN:
        kpi(cols[1], "Cost / price", f"{money(item['cost'])} / {money(item['price'])}", "Per unit")
        kpi(cols[2], "Stock value", money(item["quantity"] * item["cost"]), "On hand x cost")
    else:
        kpi(cols[1], "Price", money(item["price"]), "Per unit")
        kpi(cols[2], "SKU", item["sku"] or "-", "Item code")
    kpi(cols[3], "Status", stock_status(item), f"Alert at {item['low_stock_threshold']}",
        alert=item["low_stock"])
    st.write("")

    if IS_ADMIN:
        tab_adjust, tab_history, tab_edit, tab_delete = st.tabs(
            ["Adjust stock", "History", "Edit details", "Delete"])
    else:
        tab_adjust, tab_history = st.tabs(["Adjust stock", "History"])
        tab_edit = tab_delete = None

    with tab_adjust:
        with st.container(border=True):
            section("Record a stock movement", "Every change is saved to the activity history")
            direction = st.radio("Direction", ["Add stock", "Remove stock"], horizontal=True)
            with st.form(f"adjust_{item_id}", clear_on_submit=True):
                c1, c2 = st.columns(2)
                units = c1.number_input("Units", min_value=1, value=1, step=1)
                reason = c2.selectbox("Reason", REASONS_IN if direction == "Add stock" else REASONS_OUT)
                note = st.text_input("Note (optional)", placeholder="e.g. order reference")
                go = st.form_submit_button(direction, type="primary")
            if go:
                delta = int(units) if direction == "Add stock" else -int(units)
                _, err = api("POST", f"/items/{item_id}/adjust",
                             json={"delta": delta, "reason": reason, "note": note})
                if err:
                    st.error(err)
                else:
                    flash(f"{signed(delta)} unit(s) for {item['name']} ({reason})")
                    st.rerun()

    with tab_history:
        moves, merr = api("GET", "/movements", params={"item_id": item_id, "limit": 200})
        if merr:
            st.error(merr)
        elif not moves:
            st.info("No movements recorded for this item yet.")
        else:
            st.dataframe(movements_frame(moves)[MOVE_COLUMNS], hide_index=True,
                         column_config=MOVE_CONFIG)

    if IS_ADMIN:
        with tab_edit:
            suppliers = get_suppliers()
            with st.form(f"edit_{item_id}"):
                payload = item_form_fields(item, suppliers)
                saved = st.form_submit_button("Save changes", type="primary")
            if saved:
                if not payload["name"]:
                    st.error("Item name is required.")
                else:
                    _, err = api("PUT", f"/items/{item_id}", json=payload)
                    if err:
                        st.error(err)
                    else:
                        flash("Changes saved")
                        st.rerun()

    if IS_ADMIN:
        with tab_delete:
            with st.container(border=True):
                section("Delete item", f"This permanently removes {item['name']} from the inventory. "
                                       "Its movement history is kept.")
                confirm = st.checkbox("I understand this cannot be undone")
                if st.button("Delete item", type="primary", disabled=not confirm,
                             icon=":material/delete:"):
                    _, err = api("DELETE", f"/items/{item_id}")
                    if err:
                        st.error(err)
                    else:
                        flash(f"Deleted {item['name']}")
                        st.rerun()



# ----- Receive stock (delivery photos teach the app what products look like) -----
def page_receive():
    header("Receive Stock",
           "Record a delivery and teach the app what each product looks like")
    items, err = load_items()
    if err:
        st.error(err)
        return
    if not items:
        st.info("Add items first (Add Item page), then come back to receive stock for them.")
        return
    vstat, _ = api("GET", "/vision/status")
    vstat = vstat or {}
    by_id = {i["id"]: i for i in items}
    summary, _ = api("GET", "/references/summary")
    photos_by_item = {r["item_id"]: r["photos"] for r in (summary or [])}

    cols = st.columns(3)
    kpi(cols[0], "Items with photos",
        f"{sum(1 for i in items if photos_by_item.get(i['id'], 0) > 0)} / {len(items)}",
        "Items the app can recognise in a photo")
    kpi(cols[1], "Learned objects", f"{vstat.get('references', 0):,}", "Examples stored")
    kpi(cols[2], "Recognition", "Ready" if vstat.get("recognizer") else "Not installed",
        "Needs requirements-vision.txt" if not vstat.get("recognizer") else "Models available",
        alert=not vstat.get("recognizer"))
    st.write("")

    tab_recv, tab_refs = st.tabs(["Receive delivery", "Reference photos"])

    with tab_recv:
        gen = st.session_state.get("recv_gen", 0)
        with st.container(border=True):
            section("Record a delivery",
                    "Photos are saved so the app learns this product. Stock is added only if you enter units.")
            item_id = st.selectbox(
                "Item received", list(by_id), key=f"recv_item_{gen}",
                format_func=lambda i: f"{by_id[i]['name']}  ({photos_by_item.get(i, 0)} photo(s))")
            c1, c2 = st.columns(2)
            units = c1.number_input("Units received", min_value=0, value=0, step=1, key=f"recv_units_{gen}",
                                    help="Leave at 0 to only add photos without changing stock.")
            note = c2.text_input("Note (optional)", placeholder="e.g. delivery note number",
                                 key=f"recv_note_{gen}")
            source = st.radio("Photo source", ["Upload photos", "Take a photo"], horizontal=True,
                              key=f"recv_src_{gen}")
            if source == "Upload photos":
                files = st.file_uploader("Photos", type=["jpg", "jpeg", "png", "webp"],
                                         accept_multiple_files=True, key=f"recv_up_{gen}",
                                         label_visibility="collapsed")
            else:
                shot = st.camera_input("Photo", key=f"recv_cam_{gen}", label_visibility="collapsed")
                files = [shot] if shot is not None else []
            st.caption("For best recognition: photograph only ONE kind of product per photo, "
                       "spread the items out so each one is fully visible, on a plain background, "
                       "from above. Add 3 to 5 photos with different arrangements.")
            if st.button("Save delivery", type="primary", icon=":material/inventory:",
                         key=f"recv_save_{gen}"):
                if not files and units == 0:
                    st.error("Add at least one photo, or enter the number of units received.")
                    return
                learned_shapes, warning = 0, ""
                progress = st.progress(0.0, text="Saving photos...")
                for n, f in enumerate(files, 1):
                    try:
                        payload = {"item_id": item_id, "image": encode_photo(f.getvalue())}
                    except Exception:
                        st.error(f"'{f.name}' could not be read as an image. Nothing was added to stock.")
                        return
                    data, perr = api("POST", "/references", json=payload, timeout=180)
                    if perr:
                        st.error(f"Photo {n} failed: {perr}. Stock was NOT changed. "
                                 "Photos before this one were saved; you can retry safely.")
                        return
                    learned_shapes += data["shapes"]
                    warning = data.get("warning") or warning
                    progress.progress(n / len(files), text=f"Saved photo {n} of {len(files)}")
                progress.empty()
                if units > 0:   # stock changes last, only after every photo succeeded
                    _, aerr = api("POST", f"/items/{item_id}/adjust", json={
                        "delta": int(units), "reason": "Received",
                        "note": (note.strip() + " " if note.strip() else "") +
                                (f"({len(files)} photo(s))" if files else "")})
                    if aerr:
                        st.error(f"Photos saved, but stock was not updated: {aerr}")
                        return
                msg = f"{by_id[item_id]['name']}: "
                msg += f"+{int(units)} units" if units else "photos saved"
                if files:
                    msg += f", {len(files)} photo(s), {learned_shapes} object(s) learned"
                if warning:
                    st.session_state["_recv_warning"] = warning
                st.session_state["recv_gen"] = gen + 1
                flash(msg)
                st.rerun()
        if "_recv_warning" in st.session_state:
            st.warning(st.session_state.pop("_recv_warning"))

    with tab_refs:
        with st.container(border=True):
            section("Reference photos", "What the app has learned for each item")
            table = pd.DataFrame([{
                "Item": i["name"], "Photos": photos_by_item.get(i["id"], 0),
                "Ready": "Yes" if photos_by_item.get(i["id"], 0) else "No photos yet",
            } for i in items])
            st.dataframe(table, hide_index=True)
            pick = st.selectbox("Review photos for", list(by_id), key="refs_item",
                                format_func=lambda i: by_id[i]["name"])
            refs, rerr = api("GET", "/references", params={"item_id": pick})
            if rerr:
                st.error(rerr)
            elif not refs:
                st.info("No photos for this item yet. Add some on the Receive delivery tab.")
            else:
                grid = st.columns(4)
                for n, ref in enumerate(refs):
                    with grid[n % 4]:
                        st.image(base64.b64decode(ref["thumb"]),
                                 caption=f"{ref['created_at']} - {ref['shapes']} object(s)")
                        if st.button("Delete", key=f"delref_{ref['id']}", icon=":material/delete:"):
                            _, derr = api("DELETE", f"/references/{ref['id']}")
                            if derr:
                                st.error(derr)
                            else:
                                flash("Photo deleted")
                                st.rerun()


# ----- Shift count -----
LABEL_ALL = "All detected objects"
SOURCE_NAMES = {"vision": "Photo", "manual": "Typed"}


def encode_photo(raw: bytes) -> str:
    """Upright, shrink and JPEG-encode a photo for the API (base64 text)."""
    img = ImageOps.exif_transpose(Image.open(io.BytesIO(raw))).convert("RGB")
    img.thumbnail((1600, 1600))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return base64.b64encode(buf.getvalue()).decode()


def lines_frame(lines: list, with_result: bool = False) -> pd.DataFrame:
    rows = []
    for ln in lines:
        counted = ln["counted"]
        if counted is None:
            status = "Not counted"
        elif counted == ln["expected"]:
            status = "Matches"
        else:
            status = "Difference"
        row = {
            "Item": ln["item_name"],
            "Expected": ln["expected"],
            "Counted": counted,
            "Difference": None if counted is None else counted - ln["expected"],
            "How": SOURCE_NAMES.get(ln["source"], "") if counted is not None else "",
            "Status": status,
        }
        if with_result:
            row["Result"] = ln["result"]
        rows.append(row)
    df = pd.DataFrame(rows)
    for col in ("Counted", "Difference"):
        df[col] = df[col].astype("Int64")
    return df


def save_count_line(draft_id: int, line: dict, counted: int, detected, source: str,
                    label: str = "", confidence=None) -> bool:
    _, err = api("PUT", f"/counts/{draft_id}/lines/{line['id']}", json={
        "counted": int(counted), "detected": detected, "source": source,
        "label": label, "confidence": confidence,
    })
    if err:
        st.error(err)
        return False
    # jump to the next item that still needs counting
    todo = [x for x in st.session_state.get("_count_order", []) if x != line["id"]
            and x not in st.session_state.get("_count_done", set())]
    if todo:
        st.session_state["_count_next"] = todo[0]
    flash(f"Saved {counted} for {line['item_name']}")
    st.rerun()
    return True


def photo_panel(draft_id: int, line: dict, vstat: dict) -> None:
    if not vstat or not vstat.get("available"):
        st.info("Photo counting is not installed on this computer, so counts are typed in. "
                "To turn it on run `pip install -r requirements-vision.txt` and restart the backend "
                "(see README).")
        return
    source = st.radio("Photo source", ["Take a photo", "Upload a photo"], horizontal=True,
                      key=f"src_{line['id']}", label_visibility="collapsed")
    if source == "Take a photo":
        photo = st.camera_input("Photograph the item", key=f"cam_{line['id']}",
                                label_visibility="collapsed")
    else:
        photo = st.file_uploader("Photo", type=["jpg", "jpeg", "png", "webp"],
                                 key=f"up_{line['id']}", label_visibility="collapsed")
    has_refs = vstat.get("references", 0) > 0 and vstat.get("recognizer")
    if not has_refs:
        st.caption("Tip: add delivery photos on the Receive Stock page so the app learns your own "
                   "products. Until then it only knows generic objects and may name them wrongly.")
    with st.expander("Detection settings"):
        conf = st.slider("Minimum confidence", 0.05, 0.90, 0.15 if has_refs else 0.25, 0.05,
                         key=f"conf_{line['id']}",
                         help="Lower finds more objects but may count things that are not items.")
        min_sim = 0.80
        if has_refs:
            min_sim = st.slider("Match strictness", 0.60, 0.95, 0.80, 0.01, key=f"sim_{line['id']}",
                                help="Higher = fewer wrong matches but more 'Unrecognized'. "
                                     "Lower = accepts looser matches.")
    if photo is None:
        st.caption("Take or upload a photo where every unit is visible, then press Count.")
        return

    raw = photo.getvalue()
    sig = f"{hashlib.md5(raw).hexdigest()}_{conf}_{min_sim}"
    det_key = f"det_{line['id']}"
    if st.button("Count items in photo", icon=":material/center_focus_strong:",
                 key=f"detect_{line['id']}"):
        try:
            payload = {"image": encode_photo(raw), "conf": conf, "min_similarity": min_sim}
        except Exception:
            st.error("That file could not be read as an image.")
            return
        with st.spinner("Counting..."):
            data, err = api("POST", "/vision/count", json=payload, timeout=180)
        if err:
            st.error(err)
            return
        st.session_state[det_key] = {"sig": sig, "data": data}

    result = st.session_state.get(det_key)
    if not result or result["sig"] != sig:
        return
    data = result["data"]
    st.image(base64.b64decode(data["annotated"]),
             caption="Check that every box is one unit and nothing is missed")
    if data.get("notice"):
        st.warning(data["notice"])
    if data["total"] == 0:
        st.warning("Nothing was detected. Try a clearer photo, a lower confidence, "
                   "or type the count in.")
        return
    if data.get("unrecognized"):
        st.warning(f"{data['unrecognized']} object(s) were not recognised (red boxes). If they belong to "
                   "an item, add more photos of it on Receive Stock or lower the match strictness.")

    labels = data["labels"]
    options = [f"{name} ({info['count']})" for name, info in labels.items()]
    options.append(f"{LABEL_ALL} ({data['total']})")
    wanted = line["item_name"].strip().lower()
    default = next((i for i, name in enumerate(labels) if name.lower() == wanted), None)
    if default is None:
        default = next((i for i, name in enumerate(labels) if name != "Unrecognized"), 0)
    choice = st.selectbox("What counts for this item?", range(len(options)),
                          index=default, format_func=lambda i: options[i], key=f"lab_{line['id']}_{sig}")
    if choice < len(labels):
        label = list(labels)[choice]
        detected = labels[label]["count"]
        confidence = labels[label]["avg_confidence"]
    else:
        label, detected = "", data["total"]
        confidence = round(sum(v["avg_confidence"] * v["count"] for v in labels.values())
                           / data["total"], 3)
    if data.get("mode") == "items":
        st.caption("Names come from your delivery photos. Check the boxes, then pick this item.")
    else:
        st.caption("Generic labels only (the app has not learned your products yet). "
                   "Pick the label that matches this item, or add delivery photos first.")
    with st.form(f"vform_{line['id']}_{sig}_{choice}"):
        final = st.number_input("Counted quantity (edit if the photo count is wrong)",
                                min_value=0, value=int(detected), step=1)
        if st.form_submit_button("Save this count", type="primary"):
            how = "vision" if int(final) == int(detected) else "manual"
            save_count_line(st.session_state["_count_id"], line, final, int(detected), how,
                            label, confidence)


def typed_panel(draft_id: int, line: dict) -> None:
    with st.form(f"tform_{line['id']}"):
        start = line["counted"] if line["counted"] is not None else line["expected"]
        final = st.number_input("Counted quantity", min_value=0, value=int(start), step=1)
        if st.form_submit_button("Save this count", type="primary"):
            save_count_line(draft_id, line, final, None, "manual")


def count_draft_view(draft: dict) -> None:
    draft_id = draft["id"]
    st.session_state["_count_id"] = draft_id
    lines = draft["lines"]
    st.session_state["_count_order"] = [ln["id"] for ln in lines if ln["counted"] is None] + \
        [ln["id"] for ln in lines if ln["counted"] is not None]
    st.session_state["_count_done"] = {ln["id"] for ln in lines if ln["counted"] is not None}
    summ = draft["summary"]

    st.caption(f"Count #{draft_id} started {draft['created_at']} by {draft['created_by']}"
               + (f" - {draft['note']}" if draft["note"] else ""))
    cols = st.columns(4)
    kpi(cols[0], "Items", f"{summ['lines']:,}", "In this count")
    kpi(cols[1], "Counted", f"{summ['counted']:,}", f"{summ['uncounted']} still to do",
        alert=summ["uncounted"] > 0)
    kpi(cols[2], "Differences", f"{summ['with_difference']:,}", "Counted vs expected")
    kpi(cols[3], "Net change", f"{signed(summ['net_units'])} units",
        f"{money(summ['net_value'])} at cost" if IS_ADMIN else "Counted vs expected")
    st.write("")

    vstat, _ = api("GET", "/vision/status")
    by_id = {ln["id"]: ln for ln in lines}
    if "_count_next" in st.session_state:       # set after saving, before the picker is drawn
        st.session_state["count_pick"] = st.session_state.pop("_count_next")
    if st.session_state.get("count_pick") not in by_id:
        st.session_state["count_pick"] = st.session_state["_count_order"][0]

    with st.container(border=True):
        section("Count an item", "Pick an item, photograph it (or type the number), and save")
        pick = st.selectbox(
            "Item", st.session_state["_count_order"], key="count_pick",
            format_func=lambda i: ("\u2713 " if by_id[i]["counted"] is not None else "") +
            f"{by_id[i]['item_name']}  (expected {by_id[i]['expected']})",
        )
        line = by_id[pick]
        tab_photo, tab_type = st.tabs(["Count from photo", "Type the number"])
        with tab_photo:
            photo_panel(draft_id, line, vstat)
        with tab_type:
            typed_panel(draft_id, line)

    st.write("")
    with st.container(border=True):
        section("All items", "Expected stock was recorded when the count started")
        view = st.radio("Show", ["All", "Not counted", "Differences"], horizontal=True,
                        label_visibility="collapsed")
        df = lines_frame(lines)
        if view == "Not counted":
            df = df[df["Status"] == "Not counted"]
        elif view == "Differences":
            df = df[df["Status"] == "Difference"]
        st.dataframe(df, hide_index=True)

    st.write("")
    if not IS_ADMIN:
        with st.container(border=True):
            section("Finish", "Keep counting. An admin reviews the count and approves it to update stock.")
            if summ["uncounted"] == 0:
                st.success("Every item is counted. Tell an admin it is ready to approve.")
        return
    with st.container(border=True):
        section("Finish", "Approving updates your stock and writes every change to the Activity history")
        allow = True
        if summ["uncounted"]:
            st.warning(f"{summ['uncounted']} item(s) have not been counted. "
                       "If you approve now they are left unchanged (they are NOT set to zero).")
            allow = st.checkbox("Approve anyway and leave those items unchanged")
        if summ["with_difference"]:
            st.write(f"**{summ['with_difference']}** item(s) will change by "
                     f"**{signed(summ['net_units'])}** units in total.")
        if summ["counted"] == 0:
            st.info("Count at least one item before approving.")
        b1, b2 = st.columns(2)
        if b1.button("Approve and update stock", type="primary", icon=":material/check:",
                     disabled=(summ["counted"] == 0 or not allow)):
            data, err = api("POST", f"/counts/{draft_id}/approve", json={"allow_uncounted": allow})
            if err:
                st.error(err)
            else:
                flash(f"Count #{draft_id} approved: {data['items_adjusted']} item(s) adjusted")
                st.rerun()
        sure = b2.checkbox("Yes, cancel this count (nothing will change)")
        if b2.button("Cancel count", icon=":material/close:", disabled=not sure):
            _, err = api("POST", f"/counts/{draft_id}/cancel")
            if err:
                st.error(err)
            else:
                flash(f"Count #{draft_id} cancelled")
                st.rerun()


def count_start_view() -> None:
    with st.container(border=True):
        section("Start an end-of-shift count",
                "Records what the system expects for every item right now, then you count what is really there")
        with st.form("start_count"):
            note = st.text_input("Note (optional)", placeholder="e.g. Evening shift, front shelf")
            go = st.form_submit_button("Start count", type="primary", icon=":material/play_arrow:")
        if go:
            _, err = api("POST", "/counts", json={"note": note})
            if err:
                st.error(err)
            else:
                st.rerun()


def count_history_view() -> None:
    history, err = api("GET", "/counts", params={"limit": 50})
    if err or not history:
        return
    st.write("")
    with st.container(border=True):
        section("Past counts")
        rows = [{
            "#": c["id"], "Started": c["created_at"], "By": c["created_by"], "Status": c["status"],
            "Counted": c["summary"]["counted"], "Differences": c["summary"]["with_difference"],
            "Net units": c["summary"]["net_units"], "Net value": c["summary"]["net_value"],
            "Note": c["note"],
        } for c in history]
        history_df = pd.DataFrame(rows)
        if not IS_ADMIN:
            history_df = history_df.drop(columns=["Net value"])
        st.dataframe(history_df, hide_index=True,
                     column_config={"Net value": st.column_config.NumberColumn(format="%.2f")})
        ids = [c["id"] for c in history]
        shown = st.selectbox("Show details for count", [None] + ids,
                             format_func=lambda i: "Select..." if i is None else f"#{i}")
        if shown is not None:
            detail, derr = api("GET", f"/counts/{shown}")
            if derr:
                st.error(derr)
            else:
                st.dataframe(lines_frame(detail["lines"], with_result=detail["status"] == "Approved"),
                             hide_index=True)


def page_count():
    header("Shift Count", "Count stock at the end of a shift, compare it with the system and update it")
    draft, err = api("GET", "/counts/current")
    if err:
        st.error(err)
        return
    if draft is None:
        count_start_view()
    else:
        count_draft_view(draft)
    count_history_view()


# ----- Purchasing -----
def tab_reorder():
    suggestions, err = api("GET", "/reorder-suggestions")
    if err:
        st.error(err)
        return
    if not suggestions:
        st.info("Nothing to reorder. Every item is above its alert level, or already on order.")
        return

    st.caption("Suggested quantity = alert level - on hand + reorder batch - already on order. "
               "Edit quantities or untick items, then create the orders. "
               "One order is created per supplier.")
    table = pd.DataFrame({
        "Order": True,
        "Item": [s["name"] for s in suggestions],
        "SKU": [s["sku"] or "" for s in suggestions],
        "Supplier": [s["supplier_name"] or "No supplier" for s in suggestions],
        "On hand": [s["quantity"] for s in suggestions],
        "On order": [s["on_order"] for s in suggestions],
        "Quantity": [s["suggested_qty"] for s in suggestions],
        "Unit cost": [s["cost"] for s in suggestions],
    })
    editor_key = f"reorder_{len(suggestions)}_{sum(s['suggested_qty'] for s in suggestions)}"
    edited = st.data_editor(
        table, hide_index=True, key=editor_key,
        disabled=["Item", "SKU", "Supplier", "On hand", "On order"],
        column_config={
            "Order": st.column_config.CheckboxColumn("Order", width="small"),
            "Quantity": st.column_config.NumberColumn("Order qty", min_value=0, step=1),
            "Unit cost": st.column_config.NumberColumn("Unit cost", min_value=0.0, format="$%.2f"),
        },
    )
    edited["Quantity"] = edited["Quantity"].fillna(0)
    edited["Unit cost"] = edited["Unit cost"].fillna(0)
    chosen = edited[edited["Order"] & (edited["Quantity"] > 0)]
    total = float((chosen["Quantity"] * chosen["Unit cost"]).sum())
    st.caption(f"{len(chosen)} item(s) selected. Estimated total {money(total)}.")

    if st.button("Create purchase orders", type="primary", disabled=chosen.empty,
                 icon=":material/shopping_cart:"):
        groups = {}
        for idx, row in chosen.iterrows():
            s = suggestions[int(idx)]
            groups.setdefault(s["supplier_id"], []).append({
                "item_id": s["id"], "quantity": int(row["Quantity"]),
                "unit_cost": float(row["Unit cost"]),
            })
        made = 0
        for supplier_id, lines in groups.items():
            _, err = api("POST", "/purchase-orders", json={
                "supplier_id": supplier_id, "note": "From reorder suggestions", "lines": lines})
            if err:
                st.error(err)
                return
            made += 1
        flash(f"Created {made} purchase order(s)")
        st.rerun()


def tab_orders():
    choice = st.radio("Show", ["Open", "Received", "Cancelled", "All"], horizontal=True,
                      label_visibility="collapsed")
    status = {"Open": "Ordered", "Received": "Received", "Cancelled": "Cancelled"}.get(choice)
    pos, err = api("GET", "/purchase-orders", params={"status": status} if status else None)
    if err:
        st.error(err)
        return

    with st.expander("New purchase order"):
        suppliers = get_suppliers()
        items, _ = load_items()
        items = items or []
        if not items:
            st.caption("Add items first.")
        else:
            sup_names = {s["id"]: s["name"] for s in suppliers}
            with st.form("new_po", clear_on_submit=True):
                c1, c2, c3, c4 = st.columns([2, 2, 1, 1])
                sup = c1.selectbox("Supplier", [None] + list(sup_names),
                                   format_func=lambda i: "No supplier" if i is None else sup_names[i])
                item_id = c2.selectbox("Item", [i["id"] for i in items],
                                       format_func=lambda i: next(x["name"] for x in items if x["id"] == i))
                qty = c3.number_input("Quantity", min_value=1, value=10, step=1)
                cost = c4.number_input("Unit cost", min_value=0.0, step=0.5, format="%.2f",
                                       help="Leave at 0 to use the item's cost price")
                if st.form_submit_button("Create order", type="primary"):
                    _, err = api("POST", "/purchase-orders", json={
                        "supplier_id": sup, "note": "Manual order",
                        "lines": [{"item_id": item_id, "quantity": int(qty), "unit_cost": float(cost)}]})
                    if err:
                        st.error(err)
                    else:
                        flash("Purchase order created")
                        st.rerun()

    if not pos:
        st.info("No purchase orders to show.")
        return
    for po in pos:
        label = (f"PO #{po['id']}  |  {po['supplier_name'] or 'No supplier'}  |  "
                 f"{po['status']}  |  {money(po['total'])}")
        with st.expander(label, expanded=po["status"] == "Ordered"):
            when = f"Created {po['created_at']} by {po['created_by']}"
            if po["received_at"]:
                when += f"  |  Received {po['received_at']}"
            st.caption(when)
            lines = pd.DataFrame(po["lines"])
            lines["line_total"] = lines["quantity"] * lines["unit_cost"]
            st.dataframe(lines[["item_name", "sku", "quantity", "unit_cost", "line_total"]],
                         hide_index=True,
                         column_config={"item_name": "Item", "sku": "SKU", "quantity": "Quantity",
                                        "unit_cost": st.column_config.NumberColumn("Unit cost", format="$%.2f"),
                                        "line_total": st.column_config.NumberColumn("Total", format="$%.2f")})
            if po["status"] == "Ordered":
                b1, b2, _ = st.columns([1.3, 1, 3])
                if b1.button("Mark as received", key=f"recv_{po['id']}", type="primary",
                             icon=":material/inventory:"):
                    _, err = api("POST", f"/purchase-orders/{po['id']}/receive")
                    if err:
                        st.error(err)
                    else:
                        flash(f"PO #{po['id']} received. Stock updated.")
                        st.rerun()
                if b2.button("Cancel order", key=f"cancel_{po['id']}"):
                    _, err = api("POST", f"/purchase-orders/{po['id']}/cancel")
                    if err:
                        st.error(err)
                    else:
                        flash(f"PO #{po['id']} cancelled")
                        st.rerun()


def tab_suppliers():
    suppliers = get_suppliers()
    if suppliers:
        st.dataframe(pd.DataFrame(suppliers)[["name", "contact", "email", "phone", "item_count"]],
                     hide_index=True,
                     column_config={"name": "Supplier", "contact": "Contact", "email": "Email",
                                    "phone": "Phone", "item_count": "Items"})
    else:
        st.info("No suppliers yet.")

    left, right = st.columns(2)
    with left, st.container(border=True):
        section("Add supplier")
        with st.form("add_supplier", clear_on_submit=True):
            name = st.text_input("Company name")
            contact = st.text_input("Contact person")
            email = st.text_input("Email")
            phone = st.text_input("Phone")
            if st.form_submit_button("Add supplier", type="primary"):
                if not name.strip():
                    st.error("Company name is required.")
                else:
                    _, err = api("POST", "/suppliers", json={
                        "name": name, "contact": contact, "email": email, "phone": phone})
                    if err:
                        st.error(err)
                    else:
                        flash(f"Added supplier {name.strip()}")
                        st.rerun()
    with right, st.container(border=True):
        section("Edit or delete supplier")
        if not suppliers:
            st.caption("Nothing to edit yet.")
            return
        by_id = {s["id"]: s for s in suppliers}
        sid = st.selectbox("Supplier", list(by_id), format_func=lambda i: by_id[i]["name"],
                           label_visibility="collapsed")
        sup = by_id[sid]
        with st.form(f"edit_supplier_{sid}"):
            e_name = st.text_input("Company name", sup["name"])
            e_contact = st.text_input("Contact person", sup["contact"])
            e_email = st.text_input("Email", sup["email"])
            e_phone = st.text_input("Phone", sup["phone"])
            if st.form_submit_button("Save supplier"):
                _, err = api("PUT", f"/suppliers/{sid}", json={
                    "name": e_name, "contact": e_contact, "email": e_email, "phone": e_phone})
                if err:
                    st.error(err)
                else:
                    flash("Supplier saved")
                    st.rerun()
        confirm = st.checkbox(f"Delete {sup['name']}", key=f"del_sup_{sid}")
        if st.button("Delete supplier", disabled=not confirm, icon=":material/delete:"):
            _, err = api("DELETE", f"/suppliers/{sid}")
            if err:
                st.error(err)
            else:
                flash(f"Deleted supplier {sup['name']}")
                st.rerun()


def page_purchasing():
    header("Purchasing", "Reorder suggestions, purchase orders and suppliers")
    t1, t2, t3 = st.tabs(["Reorder suggestions", "Purchase orders", "Suppliers"])
    with t1:
        tab_reorder()
    with t2:
        tab_orders()
    with t3:
        tab_suppliers()


# ----- Activity -----
def page_activity():
    header("Activity", "A full audit trail of every stock movement")
    items, err = load_items()
    if err:
        st.error(err)
        return

    with st.container(border=True):
        f1, f2, f3 = st.columns([2, 2, 1.5])
        item_choice = f1.selectbox("Item", [None] + [i["id"] for i in items or []],
                                   format_func=lambda i: "All items" if i is None
                                   else next(x["name"] for x in items if x["id"] == i))
        period = f2.selectbox("Period", ["Last 7 days", "Last 30 days", "Last 90 days", "All time"], index=1)
        reasons = f3.multiselect("Reason", sorted(set(REASONS_IN + REASONS_OUT + [
            "Initial stock", "Adjustment", "Item deleted", "Shift count"])))
    days = {"Last 7 days": 7, "Last 30 days": 30, "Last 90 days": 90}.get(period)
    params = {"limit": 2000}
    if item_choice is not None:
        params["item_id"] = item_choice
    if days:
        params["days"] = days
    moves, err = api("GET", "/movements", params=params)
    if err:
        st.error(err)
        return
    if reasons:
        moves = [m for m in moves if m["reason"] in reasons]
    if not moves:
        st.info("No movements match the current filters.")
        return

    df = movements_frame(moves)
    cols = st.columns(3)
    kpi(cols[0], "Units added", f"{int(df.loc[df['delta'] > 0, 'delta'].sum()):,}", "Stock coming in")
    kpi(cols[1], "Units removed", f"{int(-df.loc[df['delta'] < 0, 'delta'].sum()):,}", "Stock going out")
    kpi(cols[2], "Movements", f"{len(df):,}", period)
    st.write("")
    st.dataframe(df[MOVE_COLUMNS], hide_index=True, column_config=MOVE_CONFIG, height=480)
    st.download_button("Export CSV", df[MOVE_COLUMNS].to_csv(index=False),
                       file_name="stock_activity.csv", mime="text/csv", icon=":material/download:")


# ----- Reports -----
def report_abc(items: list):
    section("ABC analysis (the 80/20 rule)",
            "Ranks products by sales revenue. A items drive about 80% of sales, B the next 15%, C the rest.")
    period = st.selectbox("Sales period", [30, 90, 180, 365], index=1,
                          format_func=lambda d: f"Last {d} days")
    moves, err = api("GET", "/movements", params={"reason": "Sale", "days": period, "limit": 5000})
    if err:
        st.error(err)
        return
    if not moves:
        st.info("No sales recorded in this period. Record stock removals with the reason 'Sale'.")
        return
    price = {i["id"]: i["price"] for i in items}
    sales = pd.DataFrame(moves)
    sales = sales[sales["item_id"].isin(list(price))].copy()
    sales["units"] = -sales["delta"]
    sales["revenue"] = sales["item_id"].map(price) * sales["units"]
    abc = sales.groupby("item_name", as_index=False).agg(units=("units", "sum"),
                                                         revenue=("revenue", "sum"))
    abc = abc.sort_values("revenue", ascending=False).reset_index(drop=True)
    total = abc["revenue"].sum()
    if total <= 0:
        st.info("Sales exist but revenue is zero. Set selling prices on your items.")
        return
    abc["share"] = abc["revenue"] / total * 100
    abc["cumulative"] = abc["share"].cumsum()
    before = abc["cumulative"] - abc["share"]
    abc["class"] = before.apply(lambda c: "A" if c < 80 else ("B" if c < 95 else "C"))

    counts = abc["class"].value_counts()
    cols = st.columns(3)
    for col, cls, text in zip(cols, "ABC", ["Top sellers", "Mid-range", "Slow sellers"]):
        kpi(col, f"Class {cls}", f"{int(counts.get(cls, 0))} item(s)", text)
    st.write("")
    with st.container(border=True):
        bar_chart(abc, "item_name", "revenue", "$,.0f", color="class")
    st.dataframe(abc[["class", "item_name", "units", "revenue", "share", "cumulative"]],
                 hide_index=True,
                 column_config={"class": "Class", "item_name": "Item", "units": "Units sold",
                                "revenue": st.column_config.NumberColumn("Revenue", format="$%.2f"),
                                "share": st.column_config.NumberColumn("Share", format="%.1f%%"),
                                "cumulative": st.column_config.NumberColumn("Cumulative", format="%.1f%%")})


def report_slow():
    section("Slow-moving stock", "In-stock items with no sales or removals for a while. This is cash sitting on shelves.")
    days = st.slider("No outbound movement for at least (days)", 7, 180, 30)
    rows, err = api("GET", "/reports/slow-movers", params={"days": days})
    if err:
        st.error(err)
        return
    if not rows:
        st.success(f"No items have been idle for {days} days or more.")
        return
    df = pd.DataFrame(rows)
    cols = st.columns(2)
    kpi(cols[0], "Idle items", f"{len(df)}", f"No movement in {days}+ days")
    kpi(cols[1], "Cash tied up", money(df["stock_value"].sum()), "Stock value at cost", alert=True)
    st.write("")
    st.dataframe(df[["name", "sku", "category", "quantity", "days_idle", "last_out", "stock_value"]],
                 hide_index=True,
                 column_config={"name": "Item", "sku": "SKU", "category": "Category",
                                "quantity": "On hand", "days_idle": "Days idle",
                                "last_out": "Last sold / removed",
                                "stock_value": st.column_config.NumberColumn("Stock value", format="$%.2f")})


def report_valuation(items: list):
    section("Inventory valuation", "What your stock is worth at cost and at retail, by category")
    df = items_frame(items)
    val = df.groupby("category", as_index=False).agg(
        items=("id", "count"), units=("quantity", "sum"),
        cost_value=("cost_value", "sum"), retail_value=("retail_value", "sum"))
    val["profit"] = val["retail_value"] - val["cost_value"]
    val["margin"] = (val["profit"] / val["retail_value"] * 100).where(val["retail_value"] > 0)
    total = {"category": "Total", "items": val["items"].sum(), "units": val["units"].sum(),
             "cost_value": val["cost_value"].sum(), "retail_value": val["retail_value"].sum(),
             "profit": val["profit"].sum()}
    total["margin"] = total["profit"] / total["retail_value"] * 100 if total["retail_value"] else None
    val = pd.concat([val.sort_values("cost_value", ascending=False), pd.DataFrame([total])],
                    ignore_index=True)
    money_cfg = lambda label: st.column_config.NumberColumn(label, format="$%.2f")
    st.dataframe(val, hide_index=True,
                 column_config={"category": "Category", "items": "Items", "units": "Units",
                                "cost_value": money_cfg("Value at cost"),
                                "retail_value": money_cfg("Value at retail"),
                                "profit": money_cfg("Potential profit"),
                                "margin": st.column_config.NumberColumn("Margin", format="%.1f%%")})
    st.download_button("Export valuation CSV", val.to_csv(index=False),
                       file_name="inventory_valuation.csv", mime="text/csv",
                       icon=":material/download:")


def page_reports():
    header("Reports", "Understand what sells, what sits, and what your stock is worth")
    items, err = load_items()
    if err:
        st.error(err)
        return
    if not items:
        st.info("Add some items to see reports.")
        return
    t1, t2, t3 = st.tabs(["ABC analysis", "Slow-moving stock", "Valuation"])
    with t1:
        report_abc(items)
    with t2:
        report_slow()
    with t3:
        report_valuation(items)


# ----- Account -----
def page_account():
    header("Account", "Change the password used to sign in")
    form_col, _ = st.columns([2, 2])
    with form_col, st.form("password_form", clear_on_submit=True):
        current = st.text_input("Current password", type="password")
        new = st.text_input("New password", type="password", help="At least 6 characters")
        confirm = st.text_input("Confirm new password", type="password")
        submitted = st.form_submit_button("Update password", type="primary")
    if submitted:
        if not current or not new:
            st.error("Fill in all fields.")
        elif new != confirm:
            st.error("The new passwords do not match.")
        elif len(new) < 6:
            st.error("The new password must be at least 6 characters.")
        else:
            _, err = api("POST", "/account/password",
                         json={"current_password": current, "new_password": new})
            if err:
                st.error(err)
            else:
                flash("Password updated")
                st.rerun()


# ----- Users (admin only) -----
def page_users():
    header("Users", "Create worker accounts and manage who can sign in")
    users, err = api("GET", "/users")
    if err:
        st.error(err)
        return
    me = st.session_state.get("user", "")
    with st.container(border=True):
        section("Accounts", "Workers count stock and record deliveries. Admins can do everything.")
        st.dataframe(pd.DataFrame(users)[["username", "role"]], hide_index=True,
                     column_config={"username": "Username", "role": "Role"})

    c1, c2 = st.columns(2)
    with c1, st.container(border=True):
        section("Add a user")
        with st.form("new_user", clear_on_submit=True):
            name = st.text_input("Username")
            pw = st.text_input("Password", type="password", help="At least 6 characters")
            role = st.selectbox("Role", ["worker", "admin"])
            go = st.form_submit_button("Create user", type="primary")
        if go:
            if not name.strip() or not pw:
                st.error("Enter a username and a password.")
            elif len(pw) < 6:
                st.error("The password must be at least 6 characters.")
            else:
                _, err = api("POST", "/users", json={"username": name.strip(), "password": pw,
                                                      "role": role})
                if err:
                    st.error(err)
                else:
                    flash(f"Created {role} account for {name.strip()}")
                    st.rerun()

    with c2, st.container(border=True):
        section("Reset a password or remove a user")
        names = [u["username"] for u in users]
        target = st.selectbox("User", names)
        with st.form("reset_pw", clear_on_submit=True):
            new_pw = st.text_input("New password", type="password", help="At least 6 characters")
            reset = st.form_submit_button("Reset password")
        if reset:
            if len(new_pw) < 6:
                st.error("The password must be at least 6 characters.")
            else:
                _, err = api("POST", f"/users/{quote(target, safe='')}/password",
                             json={"new_password": new_pw})
                if err:
                    st.error(err)
                else:
                    flash(f"Password reset for {target}")
                    st.rerun()
        sure = st.checkbox(f"Yes, delete {target}")
        if st.button("Delete user", icon=":material/delete:", disabled=not sure or target == me):
            _, err = api("DELETE", f"/users/{quote(target, safe='')}")
            if err:
                st.error(err)
            else:
                flash(f"Deleted {target}")
                st.rerun()
        if target == me:
            st.caption("You cannot delete the account you are signed in with.")


{
    "Dashboard": page_dashboard,
    "Inventory": page_inventory,
    "Add Item": page_add,
    "Manage Stock": page_manage,
    "Receive Stock": page_receive,
    "Shift Count": page_count,
    "Purchasing": page_purchasing,
    "Activity": page_activity,
    "Reports": page_reports,
    "Users": page_users,
    "Account": page_account,
}[page]()
