# ui/backup_page.py
from __future__ import annotations
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

def _collect_all_files(src: Path) -> list[Path]:
    """Thu thập toàn bộ file trong thư mục (kể cả file ẩn)."""
    return [p for p in src.rglob("*") if p.is_file()]

def _pick_dir_dialog() -> str | None:
    """Mở hộp thoại chọn thư mục bằng Tk (nếu chạy local)."""
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        path = filedialog.askdirectory()
        root.destroy()
        return path or None
    except Exception:
        return None

# ========== Page ==========
def render():
    st.subheader("1- Backup thư mục ➜ ZIP (chọn thư mục)")

    # Khởi tạo state
    st.session_state.setdefault("bk_src", "")
    st.session_state.setdefault("bk_dst", "")

    col1, col2 = st.columns([3, 2], gap="large")

    # --- Nút chọn nguồn đặt TRƯỚC text_input để có thể set session_state an toàn ---
    with col1:
        st.markdown("**Thư mục nguồn**")
        if st.button("📁 Chọn nguồn", key="btn_pick_src"):
            chosen = _pick_dir_dialog()
            if chosen:
                st.session_state["bk_src"] = chosen
            else:
                st.info("Không mở được hộp thoại hoặc bạn đã hủy. Có thể nhập đường dẫn thủ công.")

        st.text_input(
            " ", key="bk_src",
            value=st.session_state.get("bk_src", ""),
            placeholder=r"C:\Data\project hoặc /home/user/data",
            label_visibility="collapsed",
        )

    with col2:
        st.markdown("**Thư mục đích (lưu file .zip)**")
        if st.button("📁 Chọn đích", key="btn_pick_dst"):
            chosen = _pick_dir_dialog()
            if chosen:
                st.session_state["bk_dst"] = chosen
            else:
                st.info("Không mở được hộp thoại hoặc bạn đã hủy. Có thể nhập đường dẫn thủ công.")

        st.text_input(
            "  ", key="bk_dst",
            value=st.session_state.get("bk_dst", ""),
            placeholder=r"C:\Backups hoặc /home/user/backups",
            label_visibility="collapsed",
        )

    # Gợi ý tên file zip
    ts = time.strftime("%Y%m%d_%H%M%S")
    default_name = ""
    try:
        p = Path(st.session_state["bk_src"]).expanduser()
        if p.name:
            default_name = f"{p.name}_{ts}"
    except Exception:
        pass

    coln1, coln2 = st.columns([3, 2])
    with coln1:
        zip_name = st.text_input("Tên file ZIP (không cần .zip)", value=default_name)
    with coln2:
        compress_level = st.select_slider(
            "Mức nén (ZIP_DEFLATED)", options=[1, 3, 5, 7, 9], value=5,
            help="Mức nén cao hơn thì chậm hơn, nhưng file nhỏ hơn."
        )

    st.divider()
    show_preview = st.checkbox("Xem trước danh sách file & dung lượng ước tính", value=True)

    # Nút nén
    if st.button("🚀 Nén ngay", type="primary", use_container_width=True):
        try:
            src_dir = (st.session_state.get("bk_src") or "").strip()
            dst_dir = (st.session_state.get("bk_dst") or "").strip()
            if not src_dir or not dst_dir:
                st.error("Vui lòng chọn **thư mục nguồn** và **thư mục đích**.")
                return

            src_path = Path(src_dir).expanduser().resolve()
            out_dir = Path(dst_dir).expanduser().resolve()
            if not src_path.exists() or not src_path.is_dir():
                st.error(f"Thư mục nguồn không hợp lệ: `{src_path}`")
                return
            out_dir.mkdir(parents=True, exist_ok=True)

            base = (zip_name.strip() or f"{src_path.name}_{ts}")
            if not base.lower().endswith(".zip"):
                base += ".zip"
            zip_path = out_dir / base

            files = _collect_all_files(src_path)
            if not files:
                st.warning("Thư mục nguồn không có file để nén.")
                return

            total_bytes = sum(f.stat().st_size for f in files)
            c = st.columns(3)
            c[0].metric("Số file", f"{len(files):,}")
            c[1].metric("Dung lượng ước tính", _human_bytes(total_bytes))
            c[2].write(f"**Lưu thành:** `{zip_path}`")

            if show_preview:
                with st.expander("📂 Xem danh sách file", expanded=False):
                    for f in files[:500]:
                        st.write(f"- {f.relative_to(src_path)}")
                    if len(files) > 500:
                        st.caption(f"... và {len(files) - 500} file nữa")

            prog = st.progress(0)
            status = st.empty()

            # Tạo ZIP (Python mới hỗ trợ compresslevel; nếu không có thì fallback)
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

            # Cho phép tải về (nếu client và server là cùng máy)
            try:
                with open(zip_path, "rb") as fh:
                    st.download_button(
                        "📥 Tải file ZIP", fh, file_name=zip_path.name,
                        mime="application/zip", use_container_width=True
                    )
            except Exception:
                pass

            if os.name == "nt":
                st.caption(f"Mẹo: Dán đường dẫn sau vào Explorer để mở nhanh: `{out_dir}`")

        except Exception as e:
            st.error(f"Đã xảy ra lỗi: {e}")
