# ui/backup_page.py
from __future__ import annotations
import os
import time
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
import streamlit as st

# ========= Helpers =========
def _human_bytes(n: int) -> str:
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if n < 1024:
            return f"{n:.2f} {unit}"
        n /= 1024
    return f"{n:.2f} PB"

def _collect_all_files(src: Path) -> list[Path]:
    return [p for p in src.rglob("*") if p.is_file()]

def _pick_dir_dialog() -> str | None:
    """Hộp thoại chọn thư mục (chạy LOCAL trên máy client)."""
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

def _rerun():
    rr = getattr(st, "rerun", None)
    if callable(rr):
        rr()
    else:
        st.experimental_rerun()

# ========= Page =========
def render():
    st.subheader("1- Backup thư mục ➜ ZIP (máy bạn)")

    # State mặc định
    st.session_state.setdefault("bk_src", "")
    st.session_state.setdefault("bk_dst", "")

    col1, col2 = st.columns([3, 2], gap="large")

    # ---- Chọn nguồn (nút trước, input sau) ----
    with col1:
        st.markdown("**Thư mục nguồn**")
        choose_src = st.button("📁 Chọn nguồn")
        if choose_src:
            chosen = _pick_dir_dialog()
            if chosen:
                st.session_state["bk_src"] = chosen
                _rerun()
            else:
                st.info("Bạn đã hủy hoặc không mở được hộp thoại. Có thể nhập đường dẫn thủ công.")

        src_input = st.text_input(
            " ", key="bk_src",
            placeholder=r"VD: C:\Data\project  hoặc  /Users/you/data",
            label_visibility="collapsed",
        ).strip()

    # ---- Chọn đích (nút trước, input sau) ----
    with col2:
        st.markdown("**Thư mục đích (lưu file .zip)**")
        choose_dst = st.button("📁 Chọn đích")
        if choose_dst:
            chosen = _pick_dir_dialog()
            if chosen:
                st.session_state["bk_dst"] = chosen
                _rerun()
            else:
                st.info("Bạn đã hủy hoặc không mở được hộp thoại. Có thể nhập đường dẫn thủ công.")

        dst_input = st.text_input(
            "  ", key="bk_dst",
            placeholder=r"VD: C:\Backups  hoặc  /Users/you/Backups",
            label_visibility="collapsed",
        ).strip()

    # Gợi ý tên file zip
    ts = time.strftime("%Y%m%d_%H%M%S")
    default_name = f"{Path(src_input).name}_{ts}" if src_input else ""
    coln1, coln2 = st.columns([3, 2])
    with coln1:
        zip_name = st.text_input("Tên file ZIP (không cần .zip)", value=default_name)
    with coln2:
        compress_level = st.select_slider(
            "Mức nén", options=[1, 3, 5, 7, 9], value=5,
            help="Mức nén cao hơn → file nhỏ hơn nhưng chậm hơn."
        )

    st.divider()
    show_preview = st.checkbox("Xem trước danh sách file & dung lượng ước tính", value=True)

    # --- Nén ---
    if st.button("🚀 Nén ngay", type="primary", use_container_width=True):
        try:
            if not src_input or not dst_input:
                st.error("Vui lòng chọn/nhập **thư mục nguồn** và **thư mục đích**.")
                return

            src_path = Path(src_input).expanduser().resolve()
            dst_dir = Path(dst_input).expanduser().resolve()

            if not src_path.exists() or not src_path.is_dir():
                st.error(f"Thư mục nguồn không hợp lệ: `{src_path}`")
                return

            dst_dir.mkdir(parents=True, exist_ok=True)

            base = (zip_name.strip() or f"{src_path.name}_{ts}")
            if not base.lower().endswith(".zip"):
                base += ".zip"
            zip_path = dst_dir / base

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

            # Tạo ZIP (compresslevel có thể không có ở Python rất cũ)
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

            # Tải về (nếu bạn chạy app & trình duyệt trên cùng máy)
            try:
                with open(zip_path, "rb") as fh:
                    st.download_button(
                        "📥 Tải file ZIP", fh, file_name=zip_path.name,
                        mime="application/zip", use_container_width=True
                    )
            except Exception:
                pass

            if os.name == "nt":
                st.caption(f"Mẹo: mở nhanh thư mục đích trên Explorer: `{dst_dir}`")

        except Exception as e:
            st.error(f"Đã xảy ra lỗi: {e}")
