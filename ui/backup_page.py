# ui/backup_page.py
from __future__ import annotations

import os
from pathlib import Path
from datetime import datetime
from typing import List, Optional

import streamlit as st
from core import backup_utils  # uses mssql_* and zip_folder helpers

# ---------------- Page ----------------
def render() -> None:
    st.title("🔐 Backup Tools")

    tab_sql, tab_folder = st.tabs(["BackupSQL", "Backup Folder..."])

    with tab_sql:
        _tab_backup_sql()

    with tab_folder:
        _tab_backup_folder()


# ---------------- Tab: Backup SQL ----------------
def _tab_backup_sql() -> None:
    st.subheader("Backup SQL Server (.bak)")

    with st.form("sql_conn_form", clear_on_submit=False):
        cols = st.columns(3)
        with cols[0]:
            driver = st.text_input("Driver", value="ODBC Driver 17 for SQL Server", key="sql_driver")
        with cols[1]:
            server = st.text_input("Server / Instance", value="localhost", key="sql_server_instance")
        with cols[2]:
            port = st.text_input("Port (tuỳ chọn, mặc định 1433)", value="", key="sql_port")

        auth = st.radio("Authentication", options=["Windows", "SQL"], index=1, horizontal=True, key="sql_auth")
        c1, c2, c3 = st.columns([1,1,1])
        with c1:
            username = st.text_input("User", value="", key="sql_user")
        with c2:
            password = st.text_input("Password", value="", type="password", key="sql_password")
        with c3:
            dest_dir = st.text_input("Thư mục đích (trên máy SQL Server)", value="C:\\Backup", key="sql_dest_dir")

        connect = st.form_submit_button("🔗 Kết nối & tải danh sách DB")
    if connect:
        try:
            server_full = server.strip()
            if port.strip():
                server_full = f"{server_full},{port.strip()}"
            conn = backup_utils.mssql_connect(
                driver=driver.strip(),
                server=server_full,
                auth=auth,
                username=username.strip(),
                password=password,
            )
            st.session_state["_mssql_conn"] = conn
            # Load DBs
            try:
                dbs = backup_utils.mssql_list_databases(conn)
            except Exception as e:
                dbs = []
                st.warning(f"Không lấy được danh sách DB: {e}")
            st.session_state["_mssql_dbs"] = dbs
            st.success("✅ Kết nối thành công.")
        except Exception as e:
            st.error(f"Lỗi kết nối: {e}")

    # DB & options
    dbs: List[str] = st.session_state.get("_mssql_dbs", []) or []
    if dbs:
        dbname = st.selectbox("Chọn Database", options=dbs, key="sql_dbname")
    else:
        dbname = st.text_input("Database (nếu không tải được danh sách)", value="", key="sql_dbname_fallback")

    copt1, copt2, copt3 = st.columns(3)
    with copt1:
        copy_only = st.checkbox("COPY_ONLY", value=True, key="opt_copy_only")
    with copt2:
        compression = st.checkbox("COMPRESSION", value=True, key="opt_compression")
    with copt3:
        verifyonly = st.checkbox("VERIFYONLY", value=False, key="opt_verify")

    cfile1, cfile2 = st.columns([2,1])
    with cfile1:
        file_name = st.text_input("Tên file .bak (bỏ trống = tự sinh)", value="", key="sql_filename")
    with cfile2:
        do_backup = st.button("📀 Backup ngay", type="primary", key="btn_sql_backup_now", use_container_width=True)

    if do_backup:
        if not server.strip():
            st.error("Vui lòng nhập Server/Instance.")
            return
        chosen_db = dbname if dbs else st.session_state.get("sql_dbname_fallback", "").strip()
        if not chosen_db:
            st.error("Vui lòng chọn hoặc nhập Database.")
            return
        try:
            conn = st.session_state.get("_mssql_conn")
            if conn is None:
                # Try to connect inline
                server_full = server.strip()
                if port.strip():
                    server_full = f"{server_full},{port.strip()}"
                conn = backup_utils.mssql_connect(
                    driver=driver.strip(),
                    server=server_full,
                    auth=auth,
                    username=username.strip(),
                    password=password,
                )
                st.session_state["_mssql_conn"] = conn

            # filename: if empty, let utils auto-generate with timestamp
            fname = (file_name or "").strip() or None
            out_path = backup_utils.mssql_backup_database(
                conn,
                db_name=chosen_db,
                dest_dir=dest_dir.strip(),
                file_name=fname,
                copy_only=copy_only,
                compression=compression,
                verify=verifyonly,
            )
            st.success(f"✅ Đã backup xong: {out_path}")
            st.caption("Lưu ý: file .bak nằm trên **máy SQL Server** theo đường dẫn bạn đã chọn.")
        except Exception as e:
            st.error(f"Lỗi backup: {e}")


# ---------------- Tab: Backup Folder ----------------
def _tab_backup_folder() -> None:
    st.subheader("Nén thư mục → ZIP")

    c1, c2 = st.columns(2)
    with c1:
        src = st.text_input("Thư mục nguồn", value=os.getcwd(), key="zip_src")
    with c2:
        dst = st.text_input("Thư mục đích", value=os.getcwd(), key="zip_dst")

    c3, c4 = st.columns(2)
    with c3:
        zipname = st.text_input("Tên file .zip (bỏ trống = auto)", value="", key="zip_name")
        excludes_text = st.text_area("Loại trừ (mỗi dòng 1 pattern)", value="", key="zip_excludes")
    with c4:
        password = st.text_input("Mật khẩu (tuỳ chọn, cần pyzipper)", value="", type="password", key="zip_password")
        level = st.slider("Mức nén (1=nhanh, 9=nhỏ)", min_value=1, max_value=9, value=6, key="zip_level")

    excludes = [x.strip() for x in excludes_text.splitlines() if x.strip()] or None

    if st.button("📦 Nén ngay", key="btn_zip_now"):
        try:
            pbar = st.progress(0.0)
            def _cb(done: int, total: int):
                frac = (done / total) if total else 0.0
                pbar.progress(min(max(frac, 0.0), 1.0))

            out_file = backup_utils.zip_folder(
                src=src.strip(),
                dst=dst.strip(),
                zipname=(zipname.strip() or None),
                password=(password or None),
                excludes=excludes,
                compression_level=int(level),
                progress_callback=_cb,
            )
            pbar.progress(1.0)
            st.success(f"✅ Đã tạo: {out_file}")
            try:
                st.download_button("⬇️ Tải file .zip", data=open(out_file, "rb"),
                                   file_name=os.path.basename(out_file), key="dl_zip_ready")
            except Exception:
                pass
        except Exception as e:
            st.error(f"Lỗi nén: {e}")


# ---------------- Alias ----------------
main = render

if __name__ == "__main__":
    render()
