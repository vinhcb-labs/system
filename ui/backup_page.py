# ui/backup_page.py
from __future__ import annotations
import os
import re
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

_WIN_DRIVE_RE = re.compile(r"^([A-Za-z]):[\\/](.*)$")

def _normalize_path_for_server(raw: str) -> tuple[Path, str, bool]:
    """
    Chuẩn hoá đường dẫn người dùng nhập sang đường dẫn hợp lệ trên MÁY CHẠY APP.
    Trả về: (path, hint, is_win_drive_input)
    - Trên Windows: trả về Path(raw).
    - Trên Linux/macOS: nếu nhập dạng 'E:\\something', thử quy đổi sang /mnt/e/something, /media/e/something.
    """
    hint = ""
    if not raw:
        return Path(""), hint, False

    s = raw.strip().strip('"').strip("'")
    # Windows host
    if os.name == "nt":
        return Path(s).expanduser(), hint, False

    # POSIX host (Linux/macOS)
    m = _WIN_DRIVE_RE.match(s)
    if m:
        drv = m.group(1).lower()
        rest = m.group(2).replace("\\", "/").lstrip("/")
        candidates = [Path(f"/mnt/{drv}/{rest}"), Path(f"/media/{drv}/{rest}"), Path(f"/{drv}/{rest}")]
        for cand in candidates:
            if cand.exists():
                hint = f"Đã quy đổi từ `{s}` → `{cand}`."
                return cand, hint, True
        # Không tìm thấy, vẫn trả về quy đổi mặc định để người dùng thấy đường dẫn mục tiêu
        cand = Path(f"/mnt/{drv}/{rest}")
        hint = f"Đã cố quy đổi `{s}` → `{cand}` nhưng không tìm thấy trên server."
        return cand, hint, True

    # POSIX path bình thường
    return Path(s).expanduser(), hint, False

# ===== Page =====
def render():
    st.subheader("1- Backup thư mục ➜ ZIP (nhập đường dẫn)")

    st.markdown("**Thư mục nguồn**")
    src_raw = st.text_input(
        " ", key="bk_src",
        placeholder=r"Ví dụ: C:\Data\project  hoặc  /home/user/data",
        label_visibility="collapsed",
    ).strip()

    st.markdown("**Thư mục đích (nơi lưu file .zip)**")
    dst_raw = st.text_input(
        "  ", key="bk_dst",
        placeholder=r"Ví dụ: C:\Backups  hoặc  /home/user/backups",
        label_visibility="collapsed",
    ).strip()

    # Chuẩn hoá & gợi ý
    src_path, src_hint, src_windrive = _normalize_path_for_server(src_raw)
    dst_path, dst_hint, dst_windrive = _normalize_path_for_server(dst_raw)
    if src_hint:
        st.caption(src_hint)
    if dst_hint:
        st.caption(dst_hint)

    # Gợi ý tên zip
    ts = time.strftime("%Y%m%d_%H%M%S")
    default_name = f"{(src_path.name or 'backup')}_{ts}" if src_path else ""
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

    if st.button("🚀 Nén ngay", type="primary", use_container_width=True):
        try:
            if not src_raw or not dst_raw:
                st.error("Vui lòng nhập **thư mục nguồn** và **thư mục đích**.")
                return

            # Kiểm tra tồn tại thực tế
            if not src_path.exists() or not src_path.is_dir():
                # Thông báo thân thiện khi người dùng nhập đường dẫn Windows nhưng server là Linux/Cloud
                if os.name != "nt" and _WIN_DRIVE_RE.match(src_raw):
                    st.error(
                        f"Thư mục nguồn không hợp lệ trên server: `{src_path}`.\n\n"
                        "Bạn đã nhập đường dẫn **Windows** (vd. `E:\\...`) nhưng app đang chạy trên **Linux/Cloud**.\n"
                        "Mình đã thử quy đổi sang dạng WSL (`/mnt/e/...`) nhưng không tìm thấy.\n\n"
                        "**Cách xử lý:**\n"
                        "• Chạy app trên chính máy Windows đó (localhost), hoặc\n"
                        "• Mount thư mục Windows vào server (SMB/NFS/WSL), hoặc\n"
                        "• Nén thư mục thành ZIP trên máy bạn rồi **upload** lên thư mục đích trên server."
                    )
                else:
                    st.error(f"Thư mục nguồn không hợp lệ: `{src_path}`")
                return

            # Đích: tạo nếu hợp lệ (chỉ tạo được khi cha tồn tại / có quyền)
            try:
                dst_path.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                st.error(f"Không tạo được thư mục đích: `{dst_path}`\nLý do: {e}")
                return

            base = (zip_name.strip() or f"{src_path.name}_{ts}")
            if not base.lower().endswith(".zip"):
                base += ".zip"
            zip_path = (dst_path / base)

            # Thu thập file
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

            # Tạo ZIP (compresslevel có thể không hỗ trợ trên Python rất cũ)
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

            # Nút tải về (nếu client == server)
            try:
                with open(zip_path, "rb") as fh:
                    st.download_button(
                        "📥 Tải file ZIP", fh, file_name=zip_path.name,
                        mime="application/zip", use_container_width=True
                    )
            except Exception:
                pass

            if os.name == "nt":
                st.caption(f"Mẹo: dán đường dẫn sau vào Explorer để mở nhanh: `{dst_path}`")

        except Exception as e:
            st.error(f"Đã xảy ra lỗi: {e}")
