# app.py (Git-backed, with safe_rerun)
import io
import re
import base64
from typing import List, Optional

import pandas as pd
import streamlit as st

try:
    import requests
except Exception:
    requests = None

# ---------------------------
# Page config
# ---------------------------
st.set_page_config(page_title="Software Catalog", page_icon="🧩", layout="wide")
st.title("🧩 Software Catalog")
st.caption("Loads Excel from Git on startup. Browse all software as cards, search, and view full details with a download button.")

# ---------------------------
# Rerun helper (works across Streamlit versions)
# ---------------------------

def safe_rerun(scope: str = "app"):
    """Call st.rerun if available; fall back to st.experimental_rerun for old versions."""
    try:
        # Streamlit >= 1.27
        st.rerun(scope=scope)
    except Exception:
        # Older Streamlit (<1.27) fallback
        try:
            st.experimental_rerun()
        except Exception:
            # As a last resort, do nothing
            pass

# ---------------------------
# Helpers
# ---------------------------

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

def unique_software(df: pd.DataFrame) -> List[str]:
    return (
        df["Software"].dropna().astype(str).map(str.strip)
          .replace("", pd.NA).dropna().drop_duplicates()
          .sort_values(kind="mergesort").tolist()
    )

def link_button(label: str, url: str, use_container_width: bool = True):
    try:
        st.link_button(label, url, use_container_width=use_container_width)
    except Exception:
        html = (
            '<a href="{url}" target="_blank" '
            'style="text-decoration:none;background:#0969da;color:white;'
            'padding:0.5rem 0.75rem;border-radius:0.5rem;display:inline-block;'
            'text-align:center;font-weight:600;">{label}</a>'
        ).format(url=url, label=label)
        st.markdown(html, unsafe_allow_html=True)

def badge(text: str, color: str = "gray"):
    colors = {
        "green": "#2da44e", "red": "#d1242f", "blue": "#0969da", "gray": "#6e7781",
        "orange": "#c9510c", "violet": "#8250df", "pink": "#bf3989"
    }
    hexcolor = colors.get(color, color)
    bg = hexcolor + "20"
    bd = hexcolor + "40"
    html = (
        "<span style='display:inline-block;padding:2px 8px;border-radius:999px;"
        "font-size:12px;font-weight:600;background:{bg};color:{fg};"
        "border:1px solid {bd}'>{text}</span>"
    ).format(bg=bg, fg=hexcolor, bd=bd, text=text)
    st.markdown(html, unsafe_allow_html=True)

def pretty_kv(label: str, value):
    st.markdown("**{k}:** {v}".format(k=label, v=(value if pd.notna(value) else "-")))

# ---------------------------
# Data loading from Git
# ---------------------------

@st.cache_data(ttl=300, show_spinner=True)
def load_excel_from_public_url(url: str, headers: Optional[dict] = None) -> pd.DataFrame:
    if requests is None:
        raise RuntimeError("The 'requests' package is required. Add it to requirements.txt.")
    r = requests.get(url, headers=headers or {}, timeout=30)
    r.raise_for_status()
    content = r.content
    return pd.read_excel(io.BytesIO(content), dtype=object)

@st.cache_data(ttl=300, show_spinner=True)
def load_excel_from_github_api(owner: str, repo: str, path: str, ref: Optional[str] = None, token: Optional[str] = None) -> pd.DataFrame:
    if requests is None:
        raise RuntimeError("The 'requests' package is required. Add it to requirements.txt.")
    api_url = "https://api.github.com/repos/{owner}/{repo}/contents/{path}".format(owner=owner, repo=repo, path=path)
    params = {"ref": ref} if ref else None
    headers = {"Accept": "application/vnd.github.v3+json"}
    if token:
        headers["Authorization"] = "Bearer {t}".format(t=token)
    resp = requests.get(api_url, headers=headers, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    if isinstance(data, dict) and data.get("encoding") == "base64" and data.get("content"):
        b = base64.b64decode(data["content"])
        return pd.read_excel(io.BytesIO(b), dtype=object)
    else:
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
    err_msg = "Error reading Streamlit secrets: {e}".format(e=e)

# ---------------------------
# Sidebar: controls
# ---------------------------
with st.sidebar:
    st.header("⚙️ Settings")
    st.caption("Data is loaded from Git (secrets). Use Refresh to re-fetch and clear cache.")
    refresh = st.button("🔄 Refresh data", use_container_width=True)
    if refresh:
        st.cache_data.clear()
        safe_rerun()

    st.divider()
    st.markdown("**Configured Source**")
    if DATA_SOURCE is None:
        st.error(err_msg or "No data source configured.")
    else:
        if DATA_SOURCE[0] == "url":
            st.code("URL: {u}".format(u=DATA_SOURCE[1]))
        else:
            cfg = DATA_SOURCE[1]
            st.code("GitHub API: {o}/{r}/{p} @ {ref}".format(
                o=cfg["owner"], r=cfg["repo"], p=cfg["path"], ref=(cfg.get("ref") or "default")
            ))

# ---------------------------
# Load data
# ---------------------------

df = None
load_error = None

if DATA_SOURCE is not None:
    try:
        if DATA_SOURCE[0] == "url":
            url = DATA_SOURCE[1]
            token = DATA_SOURCE[2]
            headers = {"Authorization": "Bearer {t}".format(t=token)} if token else None
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
    st.error("Failed to load Excel from Git: {e}".format(e=load_error))
    st.stop()

# ---------------------------
# Prepare DataFrame
# ---------------------------

df.columns = [str(c).strip() for c in df.columns]
df = coerce_to_software_column(df)

if "Software" not in df.columns:
    st.error("No identifying column found. Please include a column named 'Software' (or 'Component').")
    st.stop()

for col in df.columns:
    df[col] = df[col].astype(object)

# ---------------------------
# Search and Grid
# ---------------------------

st.subheader("Browse All Software")
query = st.text_input(
    "Search by software name (matches within the 'Software' column)",
    placeholder="e.g., editor, vpn, browser …",
).strip()

if query:
    mask = df["Software"].astype(str).str.contains(re.escape(query), case=False, na=False)
    filtered = df[mask].copy()
else:
    filtered = df.copy()

filtered = filtered.sort_values(by="Software", kind="mergesort")
st.caption("Showing {shown} of {total} software".format(shown=len(filtered), total=len(df)))

if "selected_software" not in st.session_state:
    st.session_state.selected_software = None

n_cols = 3

# Render cards
rows = list(filtered.iterrows())
for i in range(0, len(rows), n_cols):
    chunk = rows[i:i+n_cols]
    cols = st.columns(len(chunk), gap="large")
    for col_idx, (idx, row) in enumerate(chunk):
        with cols[col_idx]:
            try:
                ctx = st.container(border=True)
            except TypeError:
                ctx = st.container()
            with ctx:
                title = str(row.get("Software", "—"))
                license_val = str(row.get("License", "—"))
                version_val = str(row.get("Version", "—"))
                category = str(row.get("Category", "—"))
                platform = str(row.get("Platform", "—"))
                desc = str(row.get("Description", "") or "")

                st.markdown("### {t}".format(t=title))
                meta = " • ".join([x for x in [category, platform] if x and x != "—"])
                if meta:
                    st.caption(meta)

                b1, b2 = st.columns([1, 1])
                with b1:
                    badge("Version: {v}".format(v=version_val), color="blue")
                with b2:
                    badge(license_val, color=("green" if license_val.lower() == "free" else "orange"))

                if desc.strip():
                    st.write(desc if len(desc) < 140 else (desc[:140] + "…"))

                if st.button("View details", key="view_{i}".format(i=idx), use_container_width=True):
                    st.session_state.selected_software = title

st.divider()

# ---------------------------
# Details panel
# ---------------------------

selected = st.session_state.selected_software

if not selected and query and len(filtered["Software"].unique()) == 1:
    selected = filtered["Software"].iloc[0]
    st.session_state.selected_software = selected

if selected:
    match_mask = filtered["Software"].astype(str).str.lower() == str(selected).lower()
    detail_df = filtered[match_mask].copy()

    st.subheader("Details — {s}".format(s=selected))

    if len(detail_df) >= 1:
        base = detail_df.iloc[0].to_dict()

        c1, c2 = st.columns(2)
        with c1:
            pretty_kv("Software", base.get("Software"))
            pretty_kv("Version", base.get("Version"))
            pretty_kv("License", base.get("License"))
            pretty_kv("Category", base.get("Category"))
            pretty_kv("Vendor", base.get("Vendor"))
        with c2:
            pretty_kv("Platform", base.get("Platform"))
            pretty_kv("Last Updated", base.get("Last Updated"))
            pretty_kv("Download URL", base.get("Download URL"))
            url = str(base.get("Download URL") or "").strip()
            if url.lower().startswith(("http://", "https://")):
                link_button("⬇️ Download", url, use_container_width=True)
            else:
                st.warning("No valid Download URL found.")

        desc = base.get("Description") or ""
        if str(desc).strip():
            st.markdown("**Description**")
            st.info(str(desc))

        if len(detail_df) > 1:
            st.markdown("**All records for {s}** ({n}):".format(s=selected, n=len(detail_df)))
            st.dataframe(detail_df, use_container_width=True)
    else:
        st.info("No details found for the selected software.")

    st.button("Clear selection", on_click=lambda: st.session_state.update({"selected_software": None}))
else:
    st.info("Click **View details** on any card to see its full information here.")

st.divider()
meta1, meta2 = st.columns(2)
with meta1:
    st.caption("**Rows:** {n}".format(n=len(df)))
with meta2:
    if DATA_SOURCE is not None:
        if DATA_SOURCE[0] == "url":
            st.caption("**Source:** URL")
        else:
            st.caption("**Source:** GitHub API")
