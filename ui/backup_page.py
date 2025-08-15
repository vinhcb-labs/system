import os
import sys
import time
import string
import subprocess
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

import streamlit as st

# ================= Helpers =================
def _human_bytes(n: int) -> str:
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if n < 1024:
            return f"{n:.2f} {unit}"
        n /= 1024
    return f"{n:.2f} PB"

def _is_hidden_path(parts) -> bool:
    return any(str(p).startswith(".") for p in parts)

def _should_skip_system_dir(rel_parts) -> bool:
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

def _zip_with_progress(src: Path, zip_path: Path, rel_root: Path):
    files = [p for p in src.rglob("*") if p.is_file()]
    total = len(files)
    if total == 0:
        return 0, 0

    total_bytes = sum(f.stat().st_size for f in files)
    progress = st.progress(0)
    status = st.empty()

    with ZipFile(zip_path, "w", ZIP_DEFLATED) as zf:
        for i, f in enumerate(files, start=1):
            zf.write(f, f.relative_to(rel_root))
            if i % 50 == 0 or i == total:
                progress.progress(int(i * 100 / total))
                status.write(f"Nén: {f.relative_to(rel_root)} ({i}/{total})")

    progress.progress(100)
    return total, total_bytes

# ================= UI: Page =================
def render():
    menu = st.radio(
        "Chức năng",
        options=[
            "1- Backup thư mục ➜ ZIP",
            "2- Backup Drive của thiết bị",  # = Driver thiết bị hệ thống
        ],
        index=0,
    )

    # ---------- MENU 1: Backup thư mục -> ZIP ----------
    if menu.startswith("1-"):
        st.subheader("1- Backup thư mục ➜ ZIP")

        col_a, col_b = st.columns(2)
        with col_a:
            src = st.text_input("Thư mục nguồn", placeholder=r"C:\Data\project")
            include_hidden = st.checkbox("Bao gồm file/ thư mục ẩn", value=False)
        with col_b:
            out_dir = st.text_input("Thư mục lưu file .zip", placeholder=r"C:\Backups")
            custom_name = st.text_input("Tên file (tuỳ chọn, không cần .zip)", placeholder="để trống sẽ tự sinh")
            skip_system_dirs = st.checkbox("Bỏ qua thư mục hệ thống", value=True)

        if st.button("Tạo file .zip", type="primary"):
            try:
                if not src or not out_dir:
                    st.error("Vui lòng nhập thư mục nguồn và thư mục lưu.")
                    return

                src_path = Path(src).expanduser().resolve()
                out_path = Path(out_dir).expanduser().resolve()
                if not src_path.exists() or not src_path.is_dir():
                    st.error(f"Thư mục nguồn không tồn tại: {src_path}")
                    return
                out_path.mkdir(parents=True, exist_ok=True)

                ts = time.strftime("%Y%m%d_%H%M%S")
                base_name = (custom_name.strip() or f"{src_path.name}_{ts}")
                if not base_name.lower().endswith(".zip"):
                    base_name += ".zip"
                zip_path = out_path / base_name

                files = _collect_files(src_path, include_hidden, skip_system_dirs)
                if not files:
                    st.warning("Không có file để nén.")
                    return

                st.metric("Số file", f"{len(files):,}")
                st.metric("Dung lượng", _human_bytes(sum(f.stat().st_size for f in files)))

                _zip_with_progress(src_path, zip_path, rel_root=src_path)

                st.success(f"Đã tạo: {zip_path}")
                with open(zip_path, "rb") as fh:
                    st.download_button("📥 Tải file ZIP", fh, file_name=zip_path.name, mime="application/zip", use_container_width=True)

            except Exception as e:
                st.error(f"Lỗi: {e}")

    # ---------- MENU 2: Backup Driver của thiết bị ----------
    else:
        st.subheader("2- Backup Drive của thiết bị (Driver hệ thống)")

        if os.name != "nt":
            st.warning("Chức năng sao lưu driver hiện chỉ hỗ trợ Windows (sử dụng pnputil/DISM).")
            return

        col1, col2 = st.columns(2)
        with col1:
            out_dir = st.text_input("Thư mục lưu", placeholder=r"C:\Backups\Drivers")
        with col2:
            custom_name = st.text_input("Tên gói ZIP (tuỳ chọn, không cần .zip)", placeholder="để trống sẽ tự sinh")
        zip_after_export = st.checkbox("Nén thành ZIP sau khi export", value=True)
        show_log = st.checkbox("Hiện chi tiết log lệnh", value=False)

        help_box = st.info(
            "Trên Windows, công cụ sẽ dùng **pnputil /export-driver /** để xuất driver bên thứ ba.\n"
            "Nếu pnputil không khả dụng, sẽ thử **DISM /Online /Export-Driver**.\n"
            "Khuyến nghị chạy ứng dụng bằng quyền **Administrator** để tránh lỗi quyền truy cập."
        )

        if st.button("Xuất driver hệ thống", type="primary"):
            try:
                if not out_dir:
                    st.error("Vui lòng chọn thư mục lưu.")
                    return

                out_path = Path(out_dir).expanduser().resolve()
                out_path.mkdir(parents=True, exist_ok=True)

                ts = time.strftime("%Y%m%d_%H%M%S")
                export_folder = out_path / f"Drivers_Export_{ts}"
                export_folder.mkdir(parents=True, exist_ok=True)

                # 1) Thử pnputil trước
                pnputil_cmd = ["pnputil", "/export-driver", "*", str(export_folder)]
                dism_cmd = ["DISM", "/Online", "/Export-Driver", f"/Destination:{export_folder}"]

                def _run(cmd):
                    return subprocess.run(cmd, capture_output=True, text=True, shell=False)

                st.write("▶️ Đang thực thi: `pnputil /export-driver * ...`")
                r = _run(pnputil_cmd)

                if r.returncode != 0:
                    st.warning("pnputil không khả dụng hoặc lỗi. Thử DISM...")
                    if show_log:
                        st.code(r.stdout + "\n" + r.stderr)
                    r = _run(dism_cmd)

                if r.returncode != 0:
                    st.error("Xuất driver thất bại. Vui lòng chạy ứng dụng với quyền Administrator hoặc kiểm tra lại môi trường.")
                    if show_log:
                        st.code(r.stdout + "\n" + r.stderr)
                    return

                if show_log:
                    st.code(r.stdout or "(Không có stdout)")
                    if r.stderr:
                        st.code("stderr:\n" + r.stderr)

                # 2) Tính thống kê
                files = [p for p in export_folder.rglob("*") if p.is_file()]
                total_files = len(files)
                total_bytes = sum(p.stat().st_size for p in files)
                st.success(f"Đã export driver vào: {export_folder}")
                colm1, colm2 = st.columns(2)
                colm1.metric("Số file driver", f"{total_files:,}")
                colm2.metric("Dung lượng ước tính", _human_bytes(total_bytes))

                # 3) ZIP (tùy chọn)
                if zip_after_export:
                    base_name = (custom_name.strip() or f"Drivers_{ts}")
                    if not base_name.lower().endswith(".zip"):
                        base_name += ".zip"
                    zip_path = out_path / base_name

                    st.write("🗜️ Đang nén ZIP…")
                    _zip_with_progress(export_folder, zip_path, rel_root=export_folder)

                    st.success(f"Đã tạo gói driver: {zip_path}")
                    with open(zip_path, "rb") as fh:
                        st.download_button("📥 Tải gói driver (.zip)", fh, file_name=zip_path.name, mime="application/zip", use_container_width=True)

                else:
                    # Cho phép tải từng INF/thư mục? (Ở đây chỉ hiển thị đường dẫn export)
                    st.info(f"Driver đã được export tại: `{export_folder}`. Bạn có thể tự nén thủ công nếu muốn.")

            except FileNotFoundError as e:
                st.error("Không tìm thấy lệnh hệ thống (pnputil/DISM). Hãy đảm bảo đang chạy trên Windows và PATH hợp lệ.")
            except PermissionError as e:
                st.error("Thiếu quyền. Hãy chạy ứng dụng bằng quyền Administrator.")
            except Exception as e:
                st.error(f"Lỗi: {e}")
