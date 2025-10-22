# app.py — Git-backed Software Catalog
# Search bar is a single selectbox (type-to-filter suggestions). No separate list box.
# Top area (Search + Details) stays visible; only the grid scrolls (inside a styled Expander).

import io
import re
import base64
from typing import Optional
import pandas as pd
import streamlit as st

try:
    import requests
except Exception:
    requests = None

st.set_page_config(
    page_title="OpenSource Softwares",
    page_icon="🪩",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# ----------------------------
# CSS — compact cards + make only the grid region scroll
# ----------------------------
st.markdown(
    """
    """,
    unsafe_allow_html=True,
)

# ----------------------------
# Rerun helper
# ----------------------------
def safe_rerun(scope: str = "app"):
    try:
        st.rerun(scope=scope)
    except Exception:
        try:
            st.experimental_rerun()
        except Exception:
            pass

# ----------------------------
# Helpers
# ----------------------------
def normalize_col(name: str) -> str:
    return re.sub(r"\s+", " ", str(name).strip().lower())

def coerce_to_software_column(df: pd.DataFrame) -> pd.DataFrame:
    norm_map = {normalize_col(c): c for c in df.columns}
    if "software" in norm_map:
        orig = norm_map["software"]
        if orig != "Software":
            df = df.rename(columns={orig: "Software"})
        return df
    if "component" in norm_map:
        return df.rename(columns={norm_map["component"]: "Software"})
    for key in ["name", "item", "asset", "module", "service", "application", "app name", "product"]:
        if key in norm_map:
            return df.rename(columns={norm_map[key]: "Software"})
    return df

def badge(text: str, color: str = "gray"):
    colors = {
        "green": "#2da44e",
        "red": "#d1242f",
        "blue": "#0969da",
        "gray": "#6e7781",
        "orange": "#c9510c",
        "violet": "#8250df",
        "pink": "#bf3989"
    }
    hexcolor = colors.get(color, color)
    # Minimal badge rendering (text only for compatibility in Streamlit markdown)
    html = f"{text}"
    st.markdown(html, unsafe_allow_html=True)

def pretty_kv(label: str, value):
    st.markdown(f"**{label}:** {value if pd.notna(value) else '-'}")

# ----------------------------
# Data loading from Git (secrets)
# ----------------------------
@st.cache_data(ttl=300, show_spinner=True)
def load_excel_from_public_url(url: str, headers: Optional[dict] = None) -> pd.DataFrame:
    if requests is None:
        raise RuntimeError("The 'requests' package is required. Add it to requirements.txt.")
    r = requests.get(url, headers=headers or {}, timeout=30)
    r.raise_for_status()
    return pd.read_excel(io.BytesIO(r.content), dtype=object)

@st.cache_data(ttl=300, show_spinner=True)
def load_excel_from_github_api(owner: str, repo: str, path: str, ref: Optional[str] = None, token: Optional[str] = None) -> pd.DataFrame:
    if requests is None:
        raise RuntimeError("The 'requests' package is required. Add it to requirements.txt.")
    api_url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"
    params = {"ref": ref} if ref else None
    headers = {"Accept": "application/vnd.github.v3+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    resp = requests.get(api_url, headers=headers, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    if isinstance(data, dict) and data.get("encoding") == "base64" and data.get("content"):
        b = base64.b64decode(data["content"])
        return pd.read_excel(io.BytesIO(b), dtype=object)
    raise RuntimeError("Unexpected GitHub API response. Ensure the path points to a file.")

# Determine data source from secrets
DATA_SOURCE = None
err_msg = None
try:
    if "DATA_URL" in st.secrets:
        DATA_SOURCE = ("url", st.secrets["DATA_URL"], st.secrets.get("GITHUB_TOKEN"))
    elif all(k in st.secrets for k in ["GITHUB_OWNER", "GITHUB_REPO", "GITHUB_PATH"]):
        DATA_SOURCE = (
            "github_api",
            {
                "owner": st.secrets["GITHUB_OWNER"],
                "repo": st.secrets["GITHUB_REPO"],
                "path": st.secrets["GITHUB_PATH"],
                "ref": st.secrets.get("GITHUB_REF"),
                "token": st.secrets.get("GITHUB_TOKEN"),
            },
            None,
        )
    else:
        err_msg = "No Git data source configured in secrets. Set DATA_URL or GITHUB_* entries."
except Exception as e:
    err_msg = f"Error reading Streamlit secrets: {e}"

# ----------------------------
# Sidebar
# ----------------------------
with st.sidebar:
    st.header("⚙️ Settings")
    st.caption("Data is loaded from Git (secrets). Use Refresh to re-fetch and clear cache.")
    if st.button("🔄 Refresh data", use_container_width=True):
        st.cache_data.clear()
        safe_rerun()
    st.divider()
    st.markdown("**Configured Source**")
    if DATA_SOURCE is None:
        st.error(err_msg or "No data source configured.")
    else:
        if DATA_SOURCE[0] == "url":
            st.code(f"URL: {DATA_SOURCE[1]}")
        else:
            cfg = DATA_SOURCE[1]
            st.code(f"GitHub API: {cfg['owner']}/{cfg['repo']}/{cfg['path']} @ {cfg.get('ref') or 'default'}")

# ----------------------------
# Load data
# ----------------------------
df = None
load_error = None
if DATA_SOURCE is not None:
    try:
        if DATA_SOURCE[0] == "url":
            url = DATA_SOURCE[1]
            token = DATA_SOURCE[2]
            headers = {"Authorization": f"Bearer {token}"} if token else None
            df = load_excel_from_public_url(url, headers=headers)
        else:
            cfg = DATA_SOURCE[1]
            df = load_excel_from_github_api(
                owner=cfg["owner"],
                repo=cfg["repo"],
                path=cfg["path"],
                ref=cfg.get("ref"),
                token=cfg.get("token"),
            )
    except Exception as e:
        load_error = str(e)
else:
    load_error = err_msg or "No data source configured."

if load_error:
    st.error(f"Failed to load Excel from Git: {load_error}")
    st.stop()

# Normalize / coerce Software column
df.columns = [str(c).strip() for c in df.columns]
df = coerce_to_software_column(df)
if "Software" not in df.columns:
    st.error("No identifying column found. Please include a column named 'Software' (or 'Component').")
    st.stop()

for col in df.columns:
    df[col] = df[col].astype(object)

# Keep selection state
if "selected_software" not in st.session_state:
    st.session_state.selected_software = None
if "license_filter" not in st.session_state:
    st.session_state.license_filter = "All"

# ----------------------------
# TOP BAR: Selectbox AS search bar + Details
# ----------------------------
left, right = st.columns([1, 1], gap="large")

with left:
    st.subheader("OpenSource Softwares")

    # Build the options for the selectbox (license-filtered first)
    list_df = df.copy()
    lic = st.session_state.license_filter
    if "License" in list_df.columns and lic in ("Free", "Paid"):
        list_df = list_df[list_df["License"].astype(str).str.lower() == lic.lower()]

    names = (
        list_df["Software"].dropna().astype(str).map(str.strip)
        .replace("", pd.NA).dropna().drop_duplicates()
        .sort_values(kind="mergesort").tolist()
    )

    # NEW: placeholder is 'select' instead of hyphen/dash
    SELECT_PLACEHOLDER = "select"

    st.markdown('\n', unsafe_allow_html=True)
    choice = st.selectbox(
        "Search or pick an open‑source software (type to filter)…",
        options=[SELECT_PLACEHOLDER] + names,
        index=0,
        key="search_bar",
    )
    st.markdown('\n', unsafe_allow_html=True)

    # When a software is chosen, set selection
    if choice != SELECT_PLACEHOLDER:
        st.session_state.selected_software = choice

    # Provide a way to go back to the full list after searching/choosing
    if st.session_state.selected_software:
        if st.button("← Show all softwares", type="secondary", use_container_width=True):
            st.session_state.selected_software = None
            # Safely reset the selectbox by removing its state; it will default to index=0 (select) on rerun
            st.session_state.pop("search_bar", None)
            safe_rerun()

    # The grid will be filtered by selection if one is chosen; otherwise show license-filtered all
    if st.session_state.selected_software:
        filtered = df[df["Software"].astype(str).str.lower() == st.session_state.selected_software.lower()].copy()
    else:
        filtered = list_df.copy()  # license-filtered set
    filtered = filtered.sort_values(by="Software", kind="mergesort")

with right:
    st.subheader("Details")
    selected = st.session_state.selected_software
    if selected:
        match_mask = df["Software"].astype(str).str.lower() == str(selected).lower()
        detail_df = df[match_mask].copy()
        if not detail_df.empty:
            base = detail_df.iloc[0].to_dict()
            c1, c2 = st.columns(2)
            with c1:
                pretty_kv("Software", base.get("Software"))
                pretty_kv("Version", base.get("Version"))
                pretty_kv("License", base.get("License"))
                pretty_kv("Category", base.get("Category"))
                # REMOVED: Vendor
                # pretty_kv("Vendor", base.get("Vendor"))
            with c2:
                # REMOVED: Platform / Last Updated
                # pretty_kv("Platform", base.get("Platform"))
                # pretty_kv("Last Updated", base.get("Last Updated"))
                pretty_kv("Download URL", base.get("Download URL"))

            url = str(base.get("Download URL") or "").strip()
            if url.lower().startswith(("http://", "https://")):
                try:
                    st.link_button("⬇️ Download", url, use_container_width=True)
                except Exception:
                    st.markdown(f'[⬇️ Download]({url})', unsafe_allow_html=True)
            else:
                st.warning("No valid Download URL found.")

            desc = base.get("Description") or ""
            if str(desc).strip():
                st.markdown("**Description**")
                st.info(str(desc))
        else:
            st.info("No details found for the selected software.")
    else:
        st.caption("Pick a software from the search bar to see details here.")

# ----------------------------
# GRID: inside a styled Expander (scrolls), top stays visible
# ----------------------------
with st.expander("", expanded=True):
    st.caption("Showing {shown} of {total} software".format(shown=len(filtered), total=len(df)))
    n_cols = 5
    rows_iter = list(filtered.iterrows())

    for i in range(0, len(rows_iter), n_cols):
        chunk = rows_iter[i:i+n_cols]
        cols = st.columns(len(chunk), gap="small")
        for col_idx, (idx, row) in enumerate(chunk):
            with cols[col_idx]:
                try:
                    cont = st.container(border=True)
                except TypeError:
                    cont = st.container()
                with cont:
                    st.markdown("\n", unsafe_allow_html=True)

                    title = str(row.get("Software", "—"))
                    license_val = str(row.get("License", "—"))
                    version_val = str(row.get("Version", "—"))
                    category = str(row.get("Category", "—"))
                    # REMOVED: Platform variable / usage
                    # platform = str(row.get("Platform", "—"))
                    desc = str(row.get("Description", "") or "")

                    st.markdown(f"\n🪩{title}\n", unsafe_allow_html=True)

                    # Meta shows only Category now (Platform removed)
                    meta = " • ".join([x for x in [category] if x and x != "—"])
                    if meta:
                        st.markdown(f"\n{meta}\n", unsafe_allow_html=True)

                    b1, b2 = st.columns([1, 1])
                    with b1:
                        badge(f"Version: {version_val}", color="blue")
                    with b2:
                        badge(license_val, color=("green" if license_val.lower() == "free" else "orange"))

                    if desc.strip():
                        st.markdown(
                            f"\n{desc if len(desc) < 100 else (desc[:100] + '…')}\n",
                            unsafe_allow_html=True,
                        )

                    if st.button("Details", key=f"view_{idx}", use_container_width=True):
                        st.session_state.selected_software = title
                        safe_rerun()

                    st.markdown("\n", unsafe_allow_html=True)

    # Footer
    st.divider()
    meta1, meta2 = st.columns(2)
    with meta1:
        st.caption(f"**Rows:** {len(df)}")
    with meta2:
        if DATA_SOURCE is not None:
            st.caption("**Source:** URL" if DATA_SOURCE[0] == "url" else "**Source:** GitHub API")
