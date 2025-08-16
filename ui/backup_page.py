# ui/backup_page.py
from __future__ import annotations
import os
import streamlit as st
from typing import Any, Callable, Dict
from core import backup_utils


# ---------------- Helper ----------------
def _safe_call(func: Callable, **kwargs) -> Any:
    """Gọi hàm backup_utils với tên tham số có thể khác nhau."""
    import inspect
    sig = inspect.signature(func)
    mapped = {}
    for name in sig.parameters.keys():
        if name in kwargs:
            mapped[name] = kwargs[name]
        else:
            # map alias
            if name in ("src_dir", "src"): mapped[name] = kwargs.get("src") or kwargs.get("src_dir")
            if name in ("dst_dir", "dst"): mapped[name] = kwargs.get("dst") or kwargs.get("dst_dir")
            if name in ("excludes", "exclude_globs"): mapped[name] = kwargs.get("excludes") or kwargs.get("exclude_globs")
            if name in ("progress_callback", "progress_cb"): mapped[name] = kwargs.get("progress_callback") or kwargs.get("progress_cb")
            if name in ("server", "server_instance"): mapped[name] = kwargs.get("server") or kwargs.get("server_instance")
            if name in ("database", "db"): mapped[name] = kwargs.get("database") or kwargs.get("db")
            if name in ("dest_path", "dst"): mapped[name] = kwargs.get("dest_path") or kwargs.get("dst")
    return func(**mapped)


# ---------------- Page ----------------
def render() -> None:
    st.title("Backup Tools")
    st.caption("Chọn loại backup bạn muốn thực hiện")

    tabs = st.tabs(["BackupSQL", "Backup Folder..."])
    with tabs[0]:
        backup_sql_tab()
    with tabs[1]:
        backup_folder_tab()


# ---------------- Backup Folder ----------------
def backup_folder_tab() -> None:
    st.subheader("Backup Folder → ZIP")

    src = st.text_input("Thư mục nguồn", key="bf_src")
    dst = st.text_input("File ZIP đích", value=os.path.join(os.getcwd(), "backup.zip"), key="bf_dst")
    password = st.text_input("Mật khẩu (tùy chọn)", type="password", key="bf_pw")
    exclude = st.text_area("Loại trừ (mỗi dòng một pattern)", key="bf_exclude")

    if st.button("📦 Nén thư mục", key="bf_btn"):
        if not os.path.isdir(src):
            st.error("❌ Thư mục nguồn không tồn tại")
            return

        excludes = [e.strip() for e in exclude.splitlines() if e.strip()]
        progress = st.progress(0.0)

        def _cb(ratio: float):
            progress.progress(min(1.0, ratio))

        try:
            _safe_call(
                backup_utils.zip_folder,
                src=src,
                dst=dst,
                password=password or None,
                excludes=excludes,
                progress_callback=_cb,
            )
            st.success(f"✅ Đã tạo file ZIP: {dst}")
            with open(dst, "rb") as f:
                st.download_button("⬇️ Tải ZIP", f, file_name=os.path.basename(dst))
        except Exception as e:
            st.error(f"Lỗi khi nén thư mục: {e}")


# ---------------- Backup SQL ----------------
def backup_sql_tab() -> None:
    st.subheader("Backup SQL Server → BAK")

    driver = st.text_input("Driver ODBC", value="ODBC Driver 17 for SQL Server", key="sql_driver")
    server = st.text_input("Server / Instance", value="localhost", key="sql_server")
    port = st.text_input("Port (tùy chọn)", value="", key="sql_port")

    auth = st.selectbox("Authentication", ["SQL Server Authentication", "Windows Authentication"], key="sql_auth")
    user, pwd = "", ""
    if auth == "SQL Server Authentication":
        user = st.text_input("User", key="sql_user")
        pwd = st.text_input("Password", type="password", key="sql_pwd")

    if st.button("🔗 Kết nối & tải danh sách DB", key="sql_listbtn"):
        try:
            dbs = _safe_call(
                backup_utils.mssql_list_databases,
                driver=driver,
                server=server,
                port=port or None,
                user=user,
                password=pwd,
                auth=auth,
            )
            st.session_state["db_list"] = dbs
            st.success(f"Đã tải {len(dbs)} database.")
        except Exception as e:
            st.error(f"Lỗi: {e}")

    dbs = st.session_state.get("db_list", [])
    if dbs:
        database = st.selectbox("Chọn Database", dbs, key="sql_db")
    else:
        database = st.text_input("Tên Database", key="sql_dbtxt")

    col1, col2, col3 = st.columns(3)
    with col1:
        copy_only = st.checkbox("COPY_ONLY", value=True, key="sql_copy")
    with col2:
        compression = st.checkbox("COMPRESSION", value=True, key="sql_comp")
    with col3:
        verify = st.checkbox("VERIFYONLY", value=False, key="sql_verify")

    dest_dir = st.text_input("Thư mục đích trên máy SQL Server", value="C:\\Backup", key="sql_dest")
    bak_name = st.text_input("Tên file .bak (tùy chọn)", value="", key="sql_bak")

    if st.button("📀 Backup ngay", key="sql_backupbtn"):
        if not database:
            st.error("❌ Bạn phải nhập/chọn Database")
            return
        try:
            bak_path = _safe_call(
                backup_utils.mssql_backup_database,
                driver=driver,
                server=server,
                port=port or None,
                user=user,
                password=pwd,
                auth=auth,
                database=database,
                dest_path=dest_dir,
                backup_file=bak_name or None,
                copy_only=copy_only,
                compression=compression,
                verify_only=verify,
            )
            st.success(f"✅ Backup thành công: {bak_path}")
            if os.path.exists(bak_path):
                with open(bak_path, "rb") as f:
                    st.download_button("⬇️ Tải file BAK", f, file_name=os.path.basename(bak_path))
        except Exception as e:
            st.error(f"Lỗi khi backup: {e}")


# Giữ alias cho hệ thống import
main = render

if __name__ == "__main__":
    render()
