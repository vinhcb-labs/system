# ui/backup_page.py
from __future__ import annotations
import os
import time
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
import streamlit as st

# ===== Helpers =====
def _human_bytes(n: int) -> str:
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if n < 1024:
            return f"{n:.2f} {unit}"
        n /= 1024
    return f"{n:.2f} PB"

def _collect_all_files(src: Path) -> list[Path]:
    """Thu thập toàn bộ file trong thư mục (kể cả file ẩn)."""
    return [p for p in src.rglob("*") if p.is_file()]

# ===== Page =====
def render():
    st.subheader("1- Backup thư mục ➜ ZIP (nhập đường dẫn thủ công)")

    # Nhập đường dẫn bằng tay
    st.markdown("**Thư mục nguồn**")
    src_input = st.text_input(
        " ", key="bk_src_manual",
        placeholder=r"Ví dụ: C:\Data\project  hoặc  /home/user/data",
        label_visibility="collapsed",
    ).strip()

    st.markdown("**Thư mục đích (nơi lưu file .zip)**")
    dst_input = st.text_input(
        "  ", key="bk_dst_manual",
        placeholder=r"Ví dụ: C:\Backups  hoặc  /home/user/backups",
        label_visibility="collapsed",
    ).strip()

    # Gợi ý tên file zip theo thư mục nguồn
    ts = time.strftime("%Y%m%d_%H%M%S")
    default_name = f"{Path(src_input).name}_{ts}" if src_input else ""
    coln1, coln2 = st.columns([3, 2])
    with coln1:
        zip_name = st.text_input("Tên file ZIP (không cần .zip)", value=default_name, key="zip_name_manual")
    with coln2:
        compress_level = st.select_slider(
            "Mức nén (ZIP_DEFLATED)", options=[1, 3, 5, 7, 9], value=5,
            help="Mức nén cao hơn → file nhỏ hơn nhưng chậm hơn."
        )

    st.divider()
    show_preview = st.checkbox("Xem trước danh sách file & dung lượng ước tính", value=True)

    # Nút thực thi
    if st.button("🚀 Nén ngay", type="primary", use_container_width=True):
        try:
            if not src_input or not dst_input:
                st.error("Vui lòng nhập **thư mục nguồn** và **thư mục đích**.")
                return

            src_path = Path(src_input).expanduser().resolve()
            out_dir  = Path(dst_input).expanduser().resolve()

            if not src_path.exists() or not src_path.is_dir():
                st.error(f"Thư mục nguồn không hợp lệ: `{src_path}`")
                return

            try:
                out_dir.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                st.error(f"Không tạo được thư mục đích: `{out_dir}`\nLý do: {e}")
                return

            base = (zip_name.strip() or f"{src_path.name}_{ts}")
            if not base.lower().endswith(".zip"):
                base += ".zip"
            zip_path = out_dir / base

            # Thu thập file & thống kê
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
                    for f in files[:500]:  # tránh quá dài giao diện
                        st.write(f"- {f.relative_to(src_path)}")
                    if len(files) > 500:
                        st.caption(f"... và {len(files) - 500} file nữa")

            # Nén với progress
            prog = st.progress(0)
            status = st.empty()
            try:
                zf = ZipFile(zip_path, "w", compression=ZIP_DEFLATED, compresslevel=compress_level)
            except TypeError:
                # Python cũ không hỗ trợ compresslevel
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

            # Nút tải về (nếu client và server cùng máy)
            try:
                with open(zip_path, "rb") as fh:
                    st.download_button(
                        "📥 Tải file ZIP", fh, file_name=zip_path.name,
                        mime="application/zip", use_container_width=True
                    )
            except Exception:
                pass

            if os.name == "nt":
                st.caption(f"Mẹo: mở nhanh thư mục đích trên Explorer: `{out_dir}`")

        except Exception as e:
            st.error(f"Đã xảy ra lỗi: {e}")
