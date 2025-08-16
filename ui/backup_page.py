from __future__ import annotations
import os
import streamlit as st

from core import backup_utils

# ---------------- Page ----------------
def render() -> None:
    #st.title("🔐 Backup Tools")

    tabs = st.tabs(["Backup SQL", "Backup Folder..."])

    # --- TAB 1: BACKUP SQL ---
    with tabs[0]:
        #st.subheader("Backup SQL (SQL Server)")
        backup_sql_tab()

    # --- TAB 2: BACKUP FOLDER ---
    with tabs[1]:
        #st.subheader("Backup Folder")
        backup_folder_tab()


# ---------------- Tabs ----------------
def backup_sql_tab() -> None:
    st.caption("Sao lưu SQL Server ra file .bak (pyodbc).")

    # Params
    driver = st.selectbox(
        "ODBC Driver",
        options=[
            "ODBC Driver 18 for SQL Server",
            "ODBC Driver 17 for SQL Server",
            "SQL Server",
        ],
        index=0,
        key="mssql_driver",
    )
    server = st.text_input("Server", value="localhost", key="mssql_server")
    auth = st.selectbox("Xác thực", ["Windows", "SQL Server"], index=0, key="mssql_auth")

    colu, colp = st.columns(2)
    with colu:
        username = st.text_input("User", value="", key="mssql_user", disabled=(auth=="Windows"))
    with colp:
        password = st.text_input("Password", value="", type="password", key="mssql_pass", disabled=(auth=="Windows"))

    # Connect & get DB list
    if st.button("🔗 Kết nối & lấy danh sách DB", key="btn_sql_load"):
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
    db_name = st.selectbox("Chọn database", options=db_list if db_list else ["<Chưa tải danh sách>"], key="mssql_dbname")

    # Options
    col1, col2 = st.columns(2)
    with col1:
        out_dir = st.text_input("Thư mục đích (.bak)", value=os.getcwd(), key="mssql_outdir")
        copy_only = st.checkbox("COPY_ONLY (không ảnh hưởng chuỗi log)", value=True, key="mssql_copyonly")
    with col2:
        file_name = st.text_input("Tên file (tuỳ chọn, ví dụ mydb.bak)", value="", key="mssql_filename")
        compression = st.checkbox("COMPRESSION (nếu bản Enterprise)", value=False, key="mssql_compression")
    verify = st.checkbox("VERIFYONLY sau khi backup", value=False, key="mssql_verify")

    if st.button("📀 Backup SQL ngay", key="btn_sql_backup2"):
        if not db_list or db_name == "<Chưa tải danh sách>":
            st.warning("Vui lòng bấm 'Kết nối & lấy danh sách DB' trước, rồi chọn database.")
            return
        try:
            cnxn = backup_utils.mssql_connect(
                driver=driver,
                server=server.strip(),
                auth=auth,
                username=username.strip(),
                password=password,
            )
            out = backup_utils.mssql_backup_database(
                cnxn,
                db_name=db_name,
                out_dir=out_dir.strip() or None,
                file_name=file_name.strip() or None,
                copy_only=copy_only,
                compression=compression,
                verify=verify,
            )
            cnxn.close()
            st.success(f"✅ Đã backup: {out}")
            try:
                st.download_button(
                    "⬇️ Tải file .bak",
                    data=open(out, "rb"),
                    file_name=os.path.basename(out),
                    key="dl_sql_bak2",
                )
            except Exception:
                pass
        except Exception as e:
            st.error(f"Lỗi backup: {e}")


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
