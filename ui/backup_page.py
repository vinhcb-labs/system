from __future__ import annotations
import os
import streamlit as st

from core import backup_utils

# ---------------- Page ----------------
def render() -> None:
    st.title("🔐 Backup Tools")

    tabs = st.tabs(["BackupSQL", "Backup Folder..."])

    # --- TAB 1: BACKUP SQL ---
    with tabs[0]:
        st.subheader("Backup SQL (SQL Server)")
        backup_sql_tab()

    # --- TAB 2: BACKUP FOLDER ---
    with tabs[1]:
        st.subheader("Backup Folder")
        backup_folder_tab()


# ---------------- Tabs ----------------
def backup_sql_tab() -> None:
    st.caption("Sao lưu database SQL Server ra file .bak (giữ nguyên cách kết nối như bản chuẩn).")

    col1, col2 = st.columns(2)
    with col1:
        driver = st.selectbox(
            "ODBC Driver",
            options=["ODBC Driver 17 for SQL Server", "ODBC Driver 18 for SQL Server"],
            index=0,
            key="sql_driver",
        )
        server = st.text_input("Server (có thể dạng SERVER\\INSTANCE hoặc HOST,PORT)", value="localhost", key="sql_server")
        auth = st.radio("Authentication", options=["Windows", "SQL"], horizontal=True, key="sql_auth")
        username = st.text_input("User", value="", key="sql_user", disabled=(auth == "Windows"))
        password = st.text_input("Password", value="", type="password", key="sql_password", disabled=(auth == "Windows"))
    with col2:
        outdir = st.text_input("Thư mục đích", value=os.getcwd(), key="sql_outdir")
        if "mssql_db_list" not in st.session_state:
            st.session_state["mssql_db_list"] = []

        if st.button("🔗 Kết nối & tải danh sách DB", key="btn_sql_connect"):
            try:
                cnxn = backup_utils.mssql_connect(
                    driver=driver,
                    server=server.strip(),
                    auth=auth,
                    username=username.strip(),
                    password=password,
                )
                dbs = backup_utils.mssql_list_databases(cnxn)
                cnxn.close()
                st.session_state["mssql_db_list"] = dbs
                st.success(f"Đã lấy {len(dbs)} database.")
            except Exception as e:
                st.error(f"Lỗi kết nối: {e}")

    db_list = st.session_state.get("mssql_db_list", [])
    database = st.selectbox("Chọn Database", options=db_list, key="sql_database")

    col3, col4, col5 = st.columns(3)
    with col3:
        copy_only = st.checkbox("COPY_ONLY", value=True, key="sql_copy_only")
    with col4:
        compression = st.checkbox("COMPRESSION (nếu hỗ trợ)", value=True, key="sql_compression")
    with col5:
        verify = st.checkbox("VERIFYONLY sau backup", value=False, key="sql_verify")

    zip_col1, zip_col2 = st.columns(2)
    with zip_col1:
        bak_name = st.text_input("Tên file .bak (bỏ trống = auto)", value="", key="sql_bakname")
    with zip_col2:
        do_backup = st.button("📀 Backup ngay", key="btn_do_backup")

    if do_backup:
        if not database:
            st.error("Vui lòng chọn database.")
            return
        try:
            cnxn = backup_utils.mssql_connect(
                driver=driver,
                server=server.strip(),
                auth=auth,
                username=username.strip(),
                password=password,
            )
            outfile = backup_utils.mssql_backup_database(
                cnxn=cnxn,
                db_name=database,
                out_dir=outdir.strip(),
                file_name=bak_name.strip() or None,
                copy_only=copy_only,
                compression=compression,
                verify=verify,
            )
            cnxn.close()
            st.success(f"✅ Đã backup thành công: {outfile}")
            try:
                st.download_button(
                    "⬇️ Tải file .bak",
                    data=open(outfile, "rb"),
                    file_name=os.path.basename(outfile),
                    key="dl_sql_bak",
                )
            except Exception:
                pass
        except Exception as e:
            st.error(f"Lỗi backup: {e}")


def backup_folder_tab() -> None:
    st.caption("Nén thư mục thành .zip, có thể đặt mật khẩu (nếu máy có pyzipper) và loại trừ file/thư mục.")

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
