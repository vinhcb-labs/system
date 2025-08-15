# ui/backup_page.py
from __future__ import annotations
import os, re, time
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
import streamlit as st

# ---------- Helpers ----------
_DRIVE_PATH = re.compile(r"^[A-Za-z]:\\")  # C:\..., D:\...
_UNC_PATH   = re.compile(r"^\\\\")         # \\server\share\...

def _human_bytes(n: int) -> str:
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if n < 1024:
            return f"{n:.2f} {unit}"
        n /= 1024
    return f"{n:.2f} PB"

def _collect_all_files(src: Path) -> list[Path]:
    return [p for p in src.rglob("*") if p.is_file()]

def _norm_win_path(raw: str) -> Path:
    """
    Chuẩn hóa chuỗi đường dẫn Windows:
    - bỏ quote, expand %ENV% và ~
    - chấp nhận cả / và \ (đổi về \)
    - thêm prefix \\?\ để hỗ trợ đường dẫn dài (nếu có thể)
    """
    s = (raw or "").strip().strip('"').strip("'")
    if not s:
        return Path("")
    s = os.path.expandvars(s)
    s = os.path.expanduser(s)
    s = s.replace("/", "\\")

    # UNC: \\server\share\...
    if _UNC_PATH.match(s):
        long = "\\\\?\\UNC" + s[1:]          # -> \\?\UNC\server\share\...
        try:
            return Path(long)
        except Exception:
            return Path(s)

    # Drive: C:\..., D:\...
    if _DRIVE_PATH.match(s):
        long = "\\\\?\\" + s                 # -> \\?\C:\...
        try:
            return Path(long)
        except Exception:
            return Path(s)

    # Tương đối hoặc dạng khác
    return Path(s)

# ---------- Page ----------
def render():
    st.subheader("1- Backup thư mục ➜ ZIP (Windows, nhập đường dẫn)")

    if os.name != "nt":
        st.error("Máy chạy app hiện **không phải Windows**. Trang này chỉ dùng khi chạy app trên Windows.")
        return

    st.markdown("**Thư mục nguồn (VD: `E:\\Data\\Project`)**")
    src_raw = st.text_input(
        " ", key="bk_src_manual",
        placeholder=r"Ví dụ: C:\Data\Project  hoặc  E:\123",
        label_visibility="collapsed",
    ).strip()

    st.markdown("**Thư mục đích (nơi lưu file .zip, VD: `E:\\Backups`)**")
    dst_raw = st.text_input(
        "  ", key="bk_dst_manual",
        placeholder=r"Ví dụ: C:\Backups  hoặc  E:\Backups",
        label_visibility="collapsed",
    ).strip()

    # Gợi ý tên file zip
    ts = time.strftime("%Y%m%d_%H%M%S")
    default_name = f"{Path(src_raw).name}_{ts}" if src_raw else ""
    c1, c2 = st.columns([3, 2])
    with c1:
        zip_name = st.text_input("Tên file ZIP (không cần .zip)", value=default_name, key="zip_name_manual")
    with c2:
        compress_level = st.select_slider(
            "Mức nén (ZIP_DEFLATED)", options=[1, 3, 5, 7, 9], value=5,
            help="Mức nén cao hơn → file nhỏ hơn nhưng nén chậm hơn."
        )

    st.divider()
    show_preview = st.checkbox("Xem trước danh sách file & dung lượng ước tính", value=True)

    # Nén
    if st.button("🚀 Nén ngay", type="primary", use_container_width=True):
        try:
            if not src_raw or not dst_raw:
                st.error("Vui lòng nhập **thư mục nguồn** và **thư mục đích**.")
                return

            src_path = _norm_win_path(src_raw)
            dst_dir  = _norm_win_path(dst_raw)

            # Kiểm tra tồn tại (không dùng resolve() để tránh biến đổi ký tự)
            if not src_path.exists() or not src_path.is_dir():
                st.error(f"Thư mục nguồn không hợp lệ hoặc không tồn tại: `{src_raw}`")
                return

            try:
                dst_dir.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                st.error(f"Không tạo được thư mục đích: `{dst_raw}`\nLý do: {e}")
                return

            base = (zip_name.strip() or f"{src_path.name}_{ts}")
            if not base.lower().endswith(".zip"):
                base += ".zip"
            zip_path = dst_dir / base

            files = _collect_all_files(src_path)
            if not files:
                st.warning("Thư mục nguồn không có file để nén.")
                return

            # Thống kê
            try:
                total_bytes = sum(f.stat().st_size for f in files)
                size_str = _human_bytes(total_bytes)
            except Exception:
                total_bytes = 0
                size_str = "—"

            m1, m2, m3 = st.columns(3)
            m1.metric("Số file", f"{len(files):,}")
            m2.metric("Dung lượng ước tính", size_str)
            m3.write(f"**Lưu thành:** `{zip_path}`")

            if show_preview:
                with st.expander("📂 Xem danh sách file", expanded=False):
                    for f in files[:500]:
                        st.write(f"- {f.relative_to(src_path)}")
                    if len(files) > 500:
                        st.caption(f"... và {len(files) - 500} file nữa")

            # Nén với progress
            prog = st.progress(0)
            status = st.empty()
            try:
                zf = ZipFile(zip_path, "w", compression=ZIP_DEFLATED, compresslevel=compress_level)
            except TypeError:
                zf = ZipFile(zip_path, "w", compression=ZIP_DEFLATED)

            with zf as z:
                for i, f in enumerate(files, start=1):
                    z.write(f, f.relative_to(src_path))
                    if i % 20 == 0 or i == len(files):
                        prog.progress(int(i * 100 / len(files)))
                        status.write(f"Đang nén: `{f.relative_to(src_path)}` ({i}/{len(files)})")

            prog.progress(100)
            status.write("✅ Hoàn tất nén.")
            st.success(f"Đã tạo: `{zip_path}`")

            # Cho tải về (nếu bạn chạy app & trình duyệt trên cùng máy)
            try:
                with open(zip_path, "rb") as fh:
                    st.download_button(
                        "📥 Tải file ZIP", fh, file_name=zip_path.name,
                        mime="application/zip", use_container_width=True
                    )
            except Exception:
                pass

            st.caption(f"Mở nhanh thư mục đích: `{dst_dir}`")

        except Exception as e:
            st.error(f"Đã xảy ra lỗi: {e}")
