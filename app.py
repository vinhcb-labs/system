# app.py
from pathlib import Path
import sys
import os

# ==== Paths & sys.path ====
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# ==== Streamlit ====
import streamlit as st

# Đặt cấu hình trang càng sớm càng tốt (trước mọi lệnh st.* khác)
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
#st.title("VLabsTools – Streamlit")

# Header + logo (tuỳ chọn)
#logo_path = ROOT / "assets" / "logo.png"
cols = st.columns([1, 1])
with cols[0]:
    if logo_path.exists():
        st.image(str(logo_path), use_column_width=True)
with cols[1]:
    st.markdown("### ")

# ==== Sidebar điều hướng ====
PAGES = {
    "🏠 Home": mainwindow_page.render,
    #"ℹ️ About": mainwindow_page.render,
    "🌐 Network":     network_page.render,
    "🖥️ System":      system_page.render,
    "🗂️ Backup":      backup_page.render,
    "ℹ️ About":       about_page.render,
}

choice = st.sidebar.radio("Điều hướng", list(PAGES.keys()))
# Gọi hàm render() của trang tương ứng
PAGES[choice]()
