# app_searchbar_selectbox.py
# Streamlit app – Software Catalog wired to Excel with "OSS Top 100" column layout
# - Top 30% sticky area: left (search + category chips), right (result tab)
# - Scrollable grid below
# - Windows/macOS download buttons per software (mac optional)
# - No Free/Paid filters; search placeholder "Search for software"

import io
import re
import base64
from typing import Optional, Dict, List

import pandas as pd
import streamlit as st

try:
    import requests
except Exception:
    requests = None

st.set_page_config(
    page_title="Software Catalog",
    page_icon="🧭",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ---------------------- CSS / Layout (top sticky 30%) ----------------------
st.markdown(
    """
    <style>
      /* 30% / 70% layout: keep the header area stuck, body area scrolls */
      .topbar-sticky {
        position: sticky;
        top: 0;
        z-index: 1000;
        background: var(--background-color, #fff);
        padding-top: .25rem;
        padding-bottom: .5rem;
        border-bottom: 1px solid rgba(0,0,0,.06);
      }
      /* Reserve ~30vh for the top (visual guidance) */
      .topbar-sticky .height-guard {
        min-height: 30vh;  /* acts like desired 30% area */
      }

      /* Below grid wrapper should scroll within remaining viewport */
      .grid-wrapper {
        height: calc(100vh - 30vh - 1rem);
        overflow: auto;
        padding-top: .25rem;
      }

      /* Make input placeholder look softer ("blurred") */
      input::placeholder {
        color: #98A2B3 !important;
        opacity: 1 !important;
      }

      /* Category "chips" look */
      .chip-row { margin-top: .25rem; }
      .chip {
        display: inline-block;
        background: #F2F4F7;
        border: 1px solid #E4E7EC;
        color: #344054;
        border-radius: 16px;
        padding: 6px 12px;
        margin: 2px 6px 0 0;
        font-size: 0.85rem;
        cursor: pointer;
        user-select: none;
      }
      .chip.active {
        background: #EEF4FF;
        border-color: #4C6FFF;
        color: #3538CD;
        font-weight: 600;
      }

      /* Compact badges */
      .tag {
        display:inline-block;
        padding:2px 8px; font-size:12px; border-radius:10px;
        background: #EDF2FF; color:#3538CD; border:1px solid #D1DBFF;
      }
      .license-tag { background:#FFF1E7; border-color:#FFD6BA; color:#B54708; }

      /* Give Streamlit containers a bit tighter spacing for cards */
      div[data-testid="stVerticalBlock"] > div:has(> div[data-testid="stContainer"]) { margin-bottom:.5rem; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------------------- Utilities ----------------------
def safe_rerun(scope: str = "app"):
    try:
        st.rerun(scope=scope)
    except Exception:
        try:
            st.experimental_rerun()
        except Exception:
            pass

def normalize_col(name: str) -> str:
    return re.sub(r"\s+", " ", str(name or "")).strip().lower()

def find_version_column(cols: List[str]) -> Optional[str]:
    # Find "Latest Version (as of 2025-..)" style header
    for c in cols:
        if normalize_col(c).startswith("latest version (as of"):
            return c
    # fallback common names
    for cand in ["version", "latest version", "current version"]:
        for c in cols:
            if normalize_col(c) == cand:
                return c
    return None

def coerce_to_oss_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Map your Excel columns to unified app schema."""
    df = df.copy()
    # Normalize column names a bit
    original = list(df.columns)
    cols_norm_map: Dict[str, str] = {normalize_col(c): c for c in original}

    # Software
    if "software name" in cols_norm_map:
        df = df.rename(columns={cols_norm_map["software name"]: "Software"})
    elif "software" in cols_norm_map:
        df = df.rename(columns={cols_norm_map["software"]: "Software"})
    else:
        # Try a few alternatives
        for key in ["name", "product", "application", "app name", "component"]:
            if key in cols_norm_map:
                df = df.rename(columns={cols_norm_map[key]: "Software"})
                break

    # Version (detect dynamic header)
    ver_col = find_version_column(list(df.columns))
    if ver_col:
        df = df.rename(columns={ver_col: "Version"})

    # Category, License
    if "category" in cols_norm_map:
        df = df.rename(columns={cols_norm_map["category"]: "Category"})
    if "license" in cols_norm_map:
        df = df.rename(columns={cols_norm_map["license"]: "License"})

    # Platform-specific download URLs
    if "windows download url" in cols_norm_map:
        df = df.rename(columns={cols_norm_map["windows download url"]: "WindowsURL"})
    if "macos download url" in cols_norm_map:
        df = df.rename(columns={cols_norm_map["macos download url"]: "MacURL"})
    if "linux download url" in cols_norm_map:
        df = df.rename(columns={cols_norm_map["linux download url"]: "LinuxURL"})

    # Description
    if "notes" in cols_norm_map:
        df = df.rename(columns={cols_norm_map["notes"]: "Description"})
    elif "description" in cols_norm_map:
        df = df.rename(columns={cols_norm_map["description"]: "Description"})

    return df

def badge_html(text: str, cls: str = "tag"):
    return f'<span class="{cls}">{text}</span>'

def link_button(label: str, url: str, key: str, fill=True):
    """Try Streamlit's link_button, fallback to markdown link."""
    url_s = (url or "").strip()
    if not url_s or not url_s.lower().startswith(("http://", "https://")):
        return False
    try:
        st.link_button(label, url_s, use_container_width=fill, key=key)
    except Exception:
        st.markdown(f"[{label}]({url_s})", unsafe_allow_html=True)
    return True

# ---------------------- Data loading (from secrets) ----------------------
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

with st.sidebar:
    st.header("⚙️ Settings")
    st.caption("Data loads from Git (secrets). Use Refresh to clear cache.")
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

# ---------------------- Load and normalize data ----------------------
if DATA_SOURCE is None:
    st.error(err_msg or "No data source configured.")
    st.stop()

try:
    if DATA_SOURCE[0] == "url":
        url = DATA_SOURCE[1]
        token = DATA_SOURCE[2]
        headers = {"Authorization": f"Bearer {token}"} if token else None
        df_raw = load_excel_from_public_url(url, headers=headers)
    else:
        cfg = DATA_SOURCE[1]
        df_raw = load_excel_from_github_api(
            owner=cfg["owner"], repo=cfg["repo"], path=cfg["path"],
            ref=cfg.get("ref"), token=cfg.get("token")
        )
except Exception as e:
    st.error(f"Failed to load Excel from Git: {e}")
    st.stop()

df_raw.columns = [str(c).strip() for c in df_raw.columns]
df = coerce_to_oss_columns(df_raw)

if "Software" not in df.columns:
    st.error("Could not find 'Software Name' / 'Software' column in the Excel.")
    st.stop()

# Make sure expected columns exist (even if empty)
for needed in ["Version", "Category", "License", "WindowsURL", "MacURL", "LinuxURL", "Description"]:
    if needed not in df.columns:
        df[needed] = None

# Ensure object dtype
for c in df.columns:
    df[c] = df[c].astype(object)

# Session state
ss = st.session_state
if "selected_software" not in ss:
    ss.selected_software = None
if "selected_category" not in ss:
    ss.selected_category = "All"
if "search_text" not in ss:
    ss.search_text = ""

# ---------------------- TOP (sticky ~30%): Left (search+categories), Right (result tab) ----------------------
# Wrap in sticky top bar with 2 columns
st.markdown('<div class="topbar-sticky">', unsafe_allow_html=True)
with st.container():
    c_left, c_right = st.columns([1, 1], gap="large")

    with c_left:
        # SEARCH
        st.subheader("Search")
        ss.search_text = st.text_input(
            label="",
            value=ss.search_text,
            placeholder="Search for software",
            label_visibility="collapsed",
            key="search_input",
        )

        # CATEGORY CHIPS
        st.markdown('<div class="chip-row">', unsafe_allow_html=True)
        categories = ["All"] + sorted(
            list(pd.Series(df["Category"].dropna().astype(str).str.strip().unique()).sort_values())
        )
        chip_cols = st.columns(6)
        for i, cat in enumerate(categories):
            col = chip_cols[i % 6]
            with col:
                pressed = st.button(
                    cat,
                    key=f"chip_{cat}",
                    use_container_width=True,
                    type="secondary" if ss.selected_category != cat else "primary",
                )
                if pressed:
                    ss.selected_category = cat
        st.markdown('</div>', unsafe_allow_html=True)

    with c_right:
        st.subheader("Result")
        if ss.selected_software:
            sel_mask = df["Software"].astype(str).str.lower() == str(ss.selected_software).lower()
            detail_df = df[sel_mask].head(1)
            if not detail_df.empty:
                rec = detail_df.iloc[0].to_dict()
                # Header
                st.markdown(f"### {rec.get('Software', '-')}")
                top_meta = []
                ver = str(rec.get("Version") or "").strip()
                lic = str(rec.get("License") or "").strip()
                if ver:
                    top_meta.append(badge_html(f"Version: {ver}", "tag"))
                if lic:
                    top_meta.append(badge_html(lic, "license-tag"))
                if top_meta:
                    st.markdown(" ".join(top_meta), unsafe_allow_html=True)

                # Description
                desc = str(rec.get("Description") or "").strip()
                if desc:
                    st.caption(desc)

                # Download buttons (Windows / macOS)
                w = (rec.get("WindowsURL") or "").strip()
                m = (rec.get("MacURL") or "").strip()
                b1, b2 = st.columns(2)
                with b1:
                    if not link_button("⬇️ Windows", w, key="d_win_detail"):
                        st.write(" ")
                with b2:
                    if m:
                        link_button("⬇️ macOS", m, key="d_mac_detail")
                    else:
                        st.write(" ")
            else:
                st.info("Select any software from the grid to see details here.")
        else:
            st.caption("Pick a software from the grid to see details here.")

    st.markdown('<div class="height-guard"></div>', unsafe_allow_html=True)

st.markdown('</div>', unsafe_allow_html=True)  # end sticky topbar

# ---------------------- Filtering logic ----------------------
filtered = df.copy()

# Category filter
if ss.selected_category and ss.selected_category != "All":
    filtered = filtered[
        filtered["Category"].astype(str).str.strip().str.lower() == ss.selected_category.strip().lower()
    ]

# Text search
q = (ss.search_text or "").strip().lower()
if q:
    filtered = filtered[
        filtered["Software"].astype(str).str.lower().str.contains(re.escape(q))
    ]

filtered = filtered.sort_values(by="Software", kind="mergesort")

# ---------------------- GRID (scrollable area) ----------------------
with st.container():
    st.markdown('<div class="grid-wrapper">', unsafe_allow_html=True)

    st.caption(f"Showing {len(filtered)} of {len(df)} software")

    n_cols = 4
    rows = list(filtered.iterrows())
    for i in range(0, len(rows), n_cols):
        chunk = rows[i:i + n_cols]
        cols = st.columns(len(chunk), gap="small")
        for col_idx, (idx, row) in enumerate(chunk):
            with cols[col_idx]:
                try:
                    cont = st.container(border=True)
                except TypeError:
                    cont = st.container()
                with cont:
                    title = str(row.get("Software", "—"))
                    version_val = str(row.get("Version", "") or "")
                    license_val = str(row.get("License", "") or "")
                    category = str(row.get("Category", "") or "")
                    desc = str(row.get("Description", "") or "")

                    st.markdown(f"**{title}**")
                    meta_badges = []
                    if category:
                        meta_badges.append(badge_html(category, "tag"))
                    if version_val:
                        meta_badges.append(badge_html(f"Version: {version_val}", "tag"))
                    if license_val:
                        meta_badges.append(badge_html(license_val, "license-tag"))
                    if meta_badges:
                        st.markdown(" ".join(meta_badges), unsafe_allow_html=True)

                    if desc:
                        st.caption(desc if len(desc) <= 110 else (desc[:110] + "…"))

                    # Download buttons
                    wurl = str(row.get("WindowsURL") or "").strip()
                    murl = str(row.get("MacURL") or "").strip()
                    d1, d2 = st.columns(2)
                    with d1:
                        link_button("⬇️ Windows", wurl, key=f"card_win_{idx}")
                    with d2:
                        if murl:
                            link_button("⬇️ macOS", murl, key=f"card_mac_{idx}")
                        else:
                            st.write(" ")

                    # Details button
                    if st.button("Details", key=f"view_{idx}", use_container_width=True):
                        st.session_state.selected_software = title
                        safe_rerun()

    st.markdown('</div>', unsafe_allow_html=True)  # end grid-wrapper

# Footer
st.divider()
st.caption(f"Rows: {len(df)}")
