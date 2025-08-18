# app.py
from pathlib import Path
import sys
import importlib
import streamlit as st

# ==== Paths & sys.path ====
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# ==== Streamlit ====
st.set_page_config(
    page_title="VLabsTools",
    page_icon="🛠️",
    layout="wide",
)

# ==== Import các trang sau khi đã config ====
# Chỉ giữ các trang còn dùng: mainwindow_page, network_page, soft_page, encryption_page, about_page
required_modules = {
    "mainwindow_page": "🏠 Home",
    "network_page":    "🌐 Network",
    "soft_page":       "📀 Software",
    "encryption_page": "🔐 Encryption",
    "about_page":      "ℹ️ About",
}

PAGES = {}
errors = []

for mod_name, label in required_modules.items():
    try:
        mod = importlib.import_module(f"ui.{mod_name}")
        render_fn = getattr(mod, "render", None)
        if callable(render_fn):
            PAGES[label] = render_fn
        else:
            errors.append(f"Module 'ui.{mod_name}' thiếu hàm render().")
    except Exception as e:
        errors.append(f"Lỗi import 'ui.{mod_name}': {e}")

# Nếu có lỗi, hiển thị nhưng vẫn cho chạy các trang còn lại
for msg in errors:
    st.error(msg)
if not PAGES:
    st.stop()

# ==== Header (logo tuỳ chọn) ====
logo_path = ROOT / "assets" / "logo.ico"  # đổi thành logo.png nếu cần
cols = st.columns([1, 1])
with cols[0]:
    if logo_path.exists():
        st.image(str(logo_path), width=80)
with cols[1]:
    st.markdown("### ")

# ==== Sidebar điều hướng ====
choice = st.sidebar.radio(" ", list(PAGES.keys()))
PAGES[choice]()
