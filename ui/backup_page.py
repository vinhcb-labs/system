# ui/backup_page.py
import os
import time
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

import streamlit as st

# ========== Helpers ==========
def _human_bytes(n: int) -> str:
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if n < 1024:
            return f"{n:.2f} {unit}"
        n /= 1024
    return f"{n:.2f} PB"

def _is_hidden_path(parts) -> bool:
    # Ẩn kiểu Unix: tên bắt đầu bằng '.'
    return any(str(p).startswith(".") for p in parts)

def _should_skip_system_dir(rel_parts) -> bool:
    # Bỏ qua các thư mục hệ thống lớn/khó nén
    sys_dirs = {
        "System Volume Information",
        "$RECYCLE.BIN",
        "$Recycle.Bin",
        "Windows\\WinSxS",
        "Windows\\SoftwareDistribution",
    }
    joined = "\\".join(rel_parts)
    return any(sd.lower() in joined.lower() for sd in sys_dirs)

def _collect_files(src: Path, include_hidden: bool, skip_system_dirs: bool) -> list[Path]:
    files = []
    for p in src.rglob("*"):
        if p.is_file():
            rel = p.relative_to(src)
            parts = rel.parts
            if not include_hidden and _is_hidden_path(parts):
                continue
            if skip_system_dirs and _should_skip_system_dir(parts):
                continue
            files.append(p)
    return files

# ========== Page ==========
def render():
    st.subheader("1- Backup thư mục ➜ ZIP")

    col_a, col_b = st.columns(2)
    with col_a:
        src = st.text_input("Thư mục nguồn", placeholder=r"C:\Data\project")
        include_hidden = st.checkbox("Bao gồm file/ thư mục ẩn (bắt đầu bằng .)", value=False)
    with col_b:
        out_dir = st.text_input("Thư mục lưu file .zip", placeholder=r"C:\Backups")
        custom_name = st.text_input("Tên file (tuỳ chọn, không cần .zip)", placeholder="để trống sẽ tự sinh")
        skip_system_dirs = st.checkbox("Bỏ qua thư mục hệ thống (khuyên dùng)", value=True)

    # Nút tạo ZIP
    if st.button("Tạo file .zip", type="primary"):
        try:
            if not src or not out_dir:
                st.error("Vui lòng nhập **thư mục nguồn** và **thư mục lưu**.")
                return

            src_path = Path(src).expanduser().resolve()
            out_path = Path(out_dir).expanduser().resolve()

            if not src_path.exists() or not src_path.is_dir():
                st.error(f"Thư mục nguồn không tồn tại hoặc không phải thư mục: {src_path}")
                return

            out_path.mkdir(parents=True, exist_ok=True)

            # Tên file zip
            ts = time.strftime("%Y%m%d_%H%M%S")
            base_name = (custom_name.strip() or f"{src_path.name}_{ts}")
            if not base_name.lower().endswith(".zip"):
                base_name += ".zip"
            zip_path = out_path / base_name

            # Thu thập file
            files = _collect_files(src_path, include_hidden, skip_system_dirs)
            total_files = len(files)
            total_bytes = sum(f.stat().st_size for f in files)

            if total_files == 0:
                st.warning("Thư mục nguồn không có file để nén (hoặc đã bị lọc).")
                return

            c1, c2, c3 = st.columns(3)
            c1.metric("Số file", f"{total_files:,}")
            c2.metric("Dung lượng ước tính", _human_bytes(total_bytes))
            c3.write(f"**Đích:** `{zip_path}`")

            progress = st.progress(0)
            status = st.empty()

            # Nén kèm progress
            with ZipFile(zip_path, "w", compression=ZIP_DEFLATED) as zf:
                for i, f in enumerate(files, start=1):
                    zf.write(f, f.relative_to(src_path))
                    if i % 20 == 0 or i == total_files:
                        progress.progress(int(i * 100 / total_files))
                        status.write(f"Đang nén: `{f.relative_to(src_path)}` ({i}/{total_files})")

            progress.progress(100)
            status.write("✅ Hoàn tất nén.")
            st.success(f"Đã tạo: {zip_path}")

            with open(zip_path, "rb") as fh:
                st.download_button(
                    label="📥 Tải file ZIP",
                    data=fh,
                    file_name=zip_path.name,
                    mime="application/zip",
                    use_container_width=True,
                )

            if os.name == "nt":
                st.caption(f"Mẹo: dán vào Explorer để mở nhanh thư mục: `{out_path}`")

        except Exception as e:
            st.error(f"Đã xảy ra lỗi: {e}")
