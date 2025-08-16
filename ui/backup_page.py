from __future__ import annotations
import os
import streamlit as st

from core import backup_utils

# ---------------- Page ----------------
def render() -> None:
    #st.title("🔐 Backup Tools")

    tabs = st.tabs(["BackupSQL", "Backup Folder..."])

    # --- TAB 1: BACKUP SQL ---
    with tabs[0]:
        #st.subheader("Backup SQL")
        backup_sql_tab()

    # --- TAB 2: BACKUP FOLDER ---
    with tabs[1]:
        #st.subheader("Backup Folder")
        backup_folder_tab()


# ---------------- Tabs ----------------
def backup_sql_tab() -> None:
    st.caption("Sao lưu database SQL Server ra file .bak")

    server = st.text_input("SQL Server", value="localhost", key="sql_server")
    database = st.text_input("Database", value="", key="sql_database")
    username = st.text_input("User", value="", key="sql_user")
    password = st.text_input("Password", value="", type="password", key="sql_password")
    outdir = st.text_input("Thư mục đích", value=os.getcwd(), key="sql_outdir")

    if st.button("📀 Backup SQL ngay", key="btn_sql_backup"):
        if not database.strip():
            st.error("Vui lòng nhập tên database.")
            return

        outfile = backup_utils.backup_sql(
            server=server.strip(),
            database=database.strip(),
            username=username.strip(),
            password=password,
            outdir=outdir.strip(),
        )
        if outfile:
            st.success(f"✅ Đã backup thành công: {outfile}")
            try:
                st.download_button(
                    "⬇️ Tải file .bak",
                    data=open(outfile, "rb"),
                    file_name=os.path.basename(outfile),
                    key="dl_sql_bak"
                )
            except Exception:
                pass
        else:
            st.error("❌ Backup thất bại. Kiểm tra lại thông tin kết nối.")


def backup_folder_tab() -> None:
    st.caption("Nén thư mục thành .zip, có thể đặt mật khẩu và loại trừ file/thư mục.")

    col1, col2 = st.columns(2)
    with col1:
        src = st.text_input("Thư mục nguồn", value=os.getcwd(), key="folder_src")
    with col2:
        dst = st.text_input("Thư mục đích", value=os.getcwd(), key="folder_dst")

    zipname = st.text_input("Tên file .zip (bỏ trống = auto)", value="", key="folder_zipname")
    password = st.text_input("Mật khẩu (tuỳ chọn - cần pyzipper để mã hoá)", value="", type="password", key="folder_password")
    excludes = st.text_area("Loại trừ (mỗi dòng 1 pattern, ví dụ *.tmp, .git/*, node_modules/*)", value="", key="folder_excludes")

    if st.button("📦 Nén ngay", key="btn_folder_zip"):
        try:
            patterns = [x.strip() for x in excludes.splitlines() if x.strip()] or None
            pbar = st.progress(0.0)

            def _cb(done: int, total: int):
                try:
                    frac = (done / total) if total else 0.0
                    pbar.progress(min(max(frac, 0.0), 1.0))
                except Exception:
                    pass

            outfile = backup_utils.zip_folder(
                src=src.strip(),
                dst=dst.strip(),
                zipname=zipname.strip() or None,
                password=password or None,
                excludes=patterns,
                progress_callback=_cb,
            )
            pbar.progress(1.0)
            if outfile:
                st.success(f"✅ Đã tạo file: {outfile}")
                try:
                    st.download_button(
                        "⬇️ Tải file .zip",
                        data=open(outfile, "rb"),
                        file_name=os.path.basename(outfile),
                        key="dl_zip_file"
                    )
                except Exception:
                    pass
        except Exception as e:
            st.error(f"Lỗi khi nén: {e}")


# ---------------- Alias ----------------
main = render

if __name__ == "__main__":
    render()
