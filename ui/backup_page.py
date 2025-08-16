# ui/backup_page.py
from __future__ import annotations
import os
from pathlib import Path
from datetime import datetime
import streamlit as st

# ===== Optional drivers (tự động phát hiện) =====
try:
    import pytds  # python-tds: không cần ODBC, hợp với Cloud
    HAS_PYTDS = True
except Exception:
    HAS_PYTDS = False

try:
    import pyodbc  # dùng khi máy đã cài ODBC Driver 17/18
    HAS_PYODBC = True
except Exception:
    HAS_PYODBC = False


# ===== KẾT NỐI MSSQL =====
def connect_mssql_with_pytds(server: str, port: int, database: str,
                             username: str, password: str,
                             encrypt: bool = True, validate_certificate: bool = False):
    if not HAS_PYTDS:
        raise RuntimeError("python-tds chưa được cài (requirements: python-tds).")
    conn = pytds.connect(
        server=server, port=port, database=database,
        user=username, password=password,
        autocommit=True, encrypt=encrypt, validate_certificate=validate_certificate,
    )
    return conn


def connect_mssql_with_pyodbc(driver: str, server: str, database: str,
                              username: str | None, password: str | None,
                              trusted_connection: bool = False,
                              encrypt: bool = True, trust_cert: bool = True):
    if not HAS_PYODBC:
        raise RuntimeError("pyodbc chưa được cài (requirements: pyodbc).")
    parts = [
        f"DRIVER={{{driver}}}",
        f"SERVER={server}",
        f"DATABASE={database}",
    ]
    if trusted_connection:
        parts.append("Trusted_Connection=yes")
    else:
        parts.append(f"UID={username or ''}")
        parts.append(f"PWD={password or ''}")
    if encrypt:
        parts.append("Encrypt=yes")
    if trust_cert:
        parts.append("TrustServerCertificate=yes")
    conn_str = ";".join(parts)
    return pyodbc.connect(conn_str, autocommit=True)


# ===== TIỆN ÍCH =====
def run_scalar(conn, sql: str, params: tuple | None = None):
    cur = conn.cursor()
    cur.execute(sql, params or ())
    row = cur.fetchone()
    cur.close()
    return row[0] if row else None


def list_databases(conn) -> list[str]:
    # Bỏ 4 DB hệ thống cho gọn
    sql = """
    SELECT name
    FROM sys.databases
    WHERE database_id > 4
    ORDER BY name;
    """
    cur = conn.cursor()
    cur.execute(sql)
    rows = cur.fetchall()
    cur.close()
    return [r[0] for r in rows]


def build_backup_tsql(dbname: str, disk_path: str, kind: str,
                      use_compression: bool = True, use_checksum: bool = False) -> str:
    """
    Trả về câu lệnh BACKUP an toàn (escape tên DB & đường dẫn).
    kind: 'FULL' | 'DIFFERENTIAL' | 'LOG'
    """
    # Escape: dùng QUOTENAME cho DB, và replace ' trong đường dẫn
    db_quoted = f"[{dbname.replace(']', ']]')}]"
    disk_escaped = disk_path.replace("'", "''")

    options = ["INIT", "STATS = 10"]
    if use_compression:
        options.append("COMPRESSION")
    if use_checksum:
        options.append("CHECKSUM")

    if kind == "LOG":
        return (
            f"BACKUP LOG {db_quoted} "
            f"TO DISK = N'{disk_escaped}' "
            f"WITH {', '.join(options)};"
        )
    elif kind == "DIFFERENTIAL":
        return (
            f"BACKUP DATABASE {db_quoted} "
            f"TO DISK = N'{disk_escaped}' "
            f"WITH DIFFERENTIAL, {', '.join(options)};"
        )
    else:  # FULL
        return (
            f"BACKUP DATABASE {db_quoted} "
            f"TO DISK = N'{disk_escaped}' "
            f"WITH {', '.join(options)};"
        )


def do_backup(conn, dbname: str, dest_folder: str, filename: str,
              kind: str, use_compression: bool, use_checksum: bool) -> tuple[bool, str]:
    """
    Thực thi backup, trả (ok, message)
    Lưu ý: đường dẫn phải là THƯ MỤC TRÊN MÁY CHẠY SQL SERVER (dịch vụ SQL phải có quyền ghi).
    """
    # Ghép đường dẫn file .bak (trên máy SQL)
    out = Path(dest_folder) / filename
    tsql = build_backup_tsql(dbname, str(out), kind, use_compression, use_checksum)

    cur = conn.cursor()
    try:
        cur.execute(tsql)
        # Một số driver không trả message chi tiết; coi như OK nếu không ném lỗi.
        return True, f"Tạo xong: {out}"
    except Exception as e:
        return False, f"Lỗi khi BACKUP: {e}"
    finally:
        try:
            cur.close()
        except Exception:
            pass


# ===== PAGE UI =====
def render():
    st.subheader("1- Backup SQL Server → .BAK")

    st.info(
        "Backup chạy trực tiếp trên **Microsoft SQL Server**.\n\n"
        "- **Đường dẫn đích** phải là thư mục **trên máy SQL Server** (dịch vụ SQL có quyền ghi).\n"
        "- **Azure SQL Database** (không phải Managed Instance) **không hỗ trợ BACKUP/RESTORE .BAK**."
    )

    # ----------- Chọn driver & thông số kết nối -----------
    drivers = []
    if HAS_PYTDS:
        drivers.append("MS SQL (python-tds) — khuyên dùng/Cloud")
    if HAS_PYODBC:
        drivers.append("MS SQL (pyodbc/ODBC) — Windows")
    if not drivers:
        st.error("Không tìm thấy kết nối. ")
        return

    backend = st.selectbox("Kết nối bằng", options=drivers, index=0)

    with st.expander("Thiết lập kết nối", expanded=True):
        col1, col2 = st.columns(2)
        with col1:
            server = st.text_input("Server / Host", value="localhost")
            port = st.number_input("Port", min_value=1, max_value=65535, value=1433, step=1)
            database_for_connect = st.text_input("Kết nối vào DB (nên để master)", value="master")
        with col2:
            if backend.startswith("MS SQL (pyodbc"):
                driver_name = st.text_input("ODBC Driver", value="ODBC Driver 17 for SQL Server")
                trusted = st.checkbox("Trusted_Connection", value=False)
                username = st.text_input("Username", value="sa", disabled=trusted)
                password = st.text_input("Password", value="", type="password", disabled=trusted)
                encrypt = st.checkbox("Encrypt TLS", value=True)
                trust_cert = st.checkbox("TrustServerCertificate", value=True)
            else:
                username = st.text_input("Username", value="sa")
                password = st.text_input("Password", value="", type="password")
                encrypt = st.checkbox("Encrypt TLS", value=True)
                validate_cert = st.checkbox("Validate certificate", value=False)

        btn_conn = st.button("🔌 Lấy DB", use_container_width=True)

    db_list = st.session_state.get("mssql_db_list", [])
    if btn_conn:
        try:
            if backend.startswith("MS SQL (pyodbc"):
                conn = connect_mssql_with_pyodbc(
                    driver=driver_name, server=f"{server},{port}",
                    database=database_for_connect,
                    username=None if trusted else username,
                    password=None if trusted else password,
                    trusted_connection=trusted, encrypt=encrypt, trust_cert=trust_cert
                )
            else:
                conn = connect_mssql_with_pytds(
                    server=server, port=int(port), database=database_for_connect,
                    username=username, password=password,
                    encrypt=encrypt, validate_certificate=validate_cert
                )
            with conn:
                db_list = list_databases(conn)
            st.session_state["mssql_conn_params"] = {
                "backend": backend, "server": server, "port": int(port),
                "database": database_for_connect, "username": username, "password": password,
                "encrypt": encrypt,
                "trusted": (trusted if backend.startswith("MS SQL (pyodbc") else False),
                "driver_name": (driver_name if backend.startswith("MS SQL (pyodbc") else None),
                "trust_cert": (trust_cert if backend.startswith("MS SQL (pyodbc") else None),
                "validate_cert": (validate_cert if not backend.startswith("MS SQL (pyodbc") else None),
            }
            st.session_state["mssql_db_list"] = db_list
            if not db_list:
                st.warning("Kết nối OK nhưng không thấy DB user (có thể chỉ có DB hệ thống).")
            else:
                st.success(f"Kết nối OK. Tìm thấy {len(db_list)} DB.")
        except Exception as e:
            st.error(f"Không kết nối được: {e}")

    # ----------- Chọn DB & tuỳ chọn backup -----------
    st.markdown("### Thiết lập backup")
    if db_list:
        dbname = st.selectbox("Chọn database", options=db_list)
    else:
        dbname = st.text_input("Tên database", value="YourDatabase")

    colA, colB = st.columns(2)
    with colA:
        kind = st.selectbox("Loại backup", options=["FULL", "DIFFERENTIAL", "LOG"], index=0)
        use_compression = st.checkbox("COMPRESSION", value=True)
        use_checksum = st.checkbox("CHECKSUM", value=False)
    with colB:
        dest_folder = st.text_input(
            "Thư mục đích trên MÁY SQL (ví dụ Windows: D:\\SQLBackups | Linux: /var/opt/mssql/backups)",
            value=r"D:\SQLBackups" if os.name == "nt" else " "
        )
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        default_name = f"{dbname}_{kind}_{ts}.bak" if dbname else f"backup_{ts}.bak"
        filename = st.text_input("Tên file .bak", value=default_name)

    run_backup = st.button("🗂️ Backup ngay", type="primary", use_container_width=True)

    if run_backup:
        # Lấy lại tham số kết nối đã test
        params = st.session_state.get("mssql_conn_params")
        if not params:
            st.warning("Bạn chưa 'Kết nối & lấy danh sách DB'. Mình sẽ cố gắng kết nối bằng tham số hiện tại.")
            params = {
                "backend": backend, "server": server, "port": int(port),
                "database": database_for_connect, "username": username, "password": password,
                "encrypt": encrypt,
                "trusted": (trusted if backend.startswith("MS SQL (pyodbc") else False),
                "driver_name": (driver_name if backend.startswith("MS SQL (pyodbc") else None),
                "trust_cert": (trust_cert if backend.startswith("MS SQL (pyodbc") else None),
                "validate_cert": (validate_cert if not backend.startswith("MS SQL (pyodbc") else None),
            }

        try:
            # Kết nối tới DB đích (dùng 'master' cũng được vì BACKUP chấp nhận tên DB khác)
            if params["backend"].startswith("MS SQL (pyodbc"):
                conn = connect_mssql_with_pyodbc(
                    driver=params["driver_name"], server=f'{params["server"]},{params["port"]}',
                    database=params["database"],
                    username=None if params["trusted"] else params["username"],
                    password=None if params["trusted"] else params["password"],
                    trusted_connection=params["trusted"],
                    encrypt=params["encrypt"],
                    trust_cert=params["trust_cert"],
                )
            else:
                conn = connect_mssql_with_pytds(
                    server=params["server"], port=int(params["port"]), database=params["database"],
                    username=params["username"], password=params["password"],
                    encrypt=params["encrypt"], validate_certificate=bool(params["validate_cert"])
                )

            with st.spinner("Đang thực hiện BACKUP…"):
                with conn:
                    ok, msg = do_backup(
                        conn=conn, dbname=dbname, dest_folder=dest_folder,
                        filename=filename, kind=kind,
                        use_compression=use_compression, use_checksum=use_checksum
                    )
            if ok:
                st.success(f"✅ {msg}")
                st.caption("Lưu ý: file .bak nằm **trên máy chạy SQL Server**. "
                           "Nếu SQL Server ở máy khác, hãy copy về máy bạn sau.")
            else:
                st.error(msg)

        except Exception as e:
            st.error(f"Lỗi kết nối/thi hành: {e}")
