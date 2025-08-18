# app.py
from pathlib import Path
import sys
import os
# Imports
from ui import mainwindow_page, network_page, about_page, encryption_page, soft_page

# ==== Paths & sys.path ====
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# ==== Streamlit ====
import streamlit as st

# Đặt cấu hình trang càng sớm càng tốt
_set_page_config = getattr(st, "set_page_config", None)
if callable(_set_page_config):
    _set_page_config(
        page_title="VLabsTools",
        page_icon="🛠️",
        layout="wide"
    )

# ==== Import các trang sau khi đã config ====
try:
    from ui import mainwindow_page, network_page, system_page, backup_page, about_page
except Exception as e:
    st.error(f"Lỗi import module trang trong 'ui': {e}")
    st.stop()

# ==== Header ====
logo_path = ROOT / "assets" / "logo.ico"  # đổi thành logo.png nếu bạn dùng PNG
cols = st.columns([1, 1])
with cols[0]:
    if logo_path.exists():
        # Thu nhỏ logo bằng width (px). Điều chỉnh số 80 theo ý bạn.
        st.image(str(logo_path), width=80)
with cols[1]:
    st.markdown("### ")

# ==== Sidebar điều hướng ====
PAGES = {
    "🏠 Home":     mainwindow_page.render,
    "🌐 Network":  network_page.render,
    "📀 Software": soft_page.render,
    "🔐 Encryption": encryption_page.render,
    "ℹ️ About":    about_page.render,
}

choice = st.sidebar.radio(" ", list(PAGES.keys()))
PAGES[choice]()
