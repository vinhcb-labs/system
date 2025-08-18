# ui/backup_page.py
from __future__ import annotations
import os
import socket
import streamlit as st
from typing import Any, Callable, List, Optional, Tuple

from core import backup_utils

# ---------------- Small helpers ----------------
def _safe_call(func: Callable, **kwargs) -> Any:
    """Gọi hàm backup_utils với tên tham số có thể khác nhau (map alias)."""
    import inspect
    sig = inspect.signature(func)
    mapped = {}
    for name in sig.parameters.keys():
        if name in kwargs:
            mapped[name] = kwargs[name]
        else:
            # map alias phổ biến
            if name in ("src_dir", "src"): mapped[name] = kwargs.get("src") or kwargs.get("src_dir")
            if name in ("dst_dir", "dst"): mapped[name] = kwargs.get("dst") or kwargs.get("dst_dir")
            if name in ("excludes", "exclude_globs"): mapped[name] = kwargs.get("excludes") or kwargs.get("exclude_globs")
            if name in ("progress_callback", "progress_cb"): mapped[name] = kwargs.get("progress_callback") or kwargs.get("progress_cb")
            if name in ("server", "server_instance"): mapped[name] = kwargs.get("server") or kwargs.get("server_instance")
            if name in ("database", "db"): mapped[name] = kwargs.get("database") or kwargs.get("db")
            if name in ("dest_path", "dst"): mapped[name] = kwargs.get("dest_path") or kwargs.get("dst")
            if name in ("backup_file", "filename"): mapped[name] = kwargs.get("backup_file") or kwargs.get("filename")
    return func(**mapped)

def _normalize_host_for_port(server: str) -> str:
    """Nếu server có dạng 'HOST\\INSTANCE' và có Port thì chỉ lấy 'HOST'."""
    server = (server or "").strip()
    if "\\" in server:
        host, _instance = server.split("\\", 1)
        return host.strip()
    return server

def _build_server_for_odbc(server: str, port: Optional[str]) -> str:
    """
    - Nếu có port -> trả về 'HOST,PORT' (tự loại bỏ '\INSTANCE' nếu có).
    - Nếu không port -> trả về 'SERVER' nguyên gốc (có thể là 'HOST' hoặc 'HOST\\INSTANCE').
    """
    server = (server or "").strip()
    port = (port or "").strip()
    if port:
        host = _normalize_host_for_port(server)
        return f"{host},{int(port)}"
    return server

# ---- Dò driver ODBC SQL Server có sẵn ----
def _list_sql_odbc_drivers() -> List[str]:
    try:
        import pyodbc
        return [d for d in pyodbc.drivers() if "SQL Server" in d]
    except Exception:
        return []

def _pick_installed_sql_driver(preferred_label: str) -> str:
    """
    Trả về tên driver ODBC SQL Server đã cài (đúng chính tả).
    - Nếu preferred_label có sẵn -> dùng luôn.
    - Nếu không -> chọn driver SQL Server có version cao nhất hiện có.
    - Nếu máy chưa có driver SQL Server -> raise RuntimeError.
    """
    import re
    installed = _list_sql_odbc_drivers()
    preferred = (preferred_label or "").strip()
    if preferred in installed:
        return preferred
    if installed:
        def ver(n: str) -> int:
            import re as _re
            m = _re.search(r"(\d+)", n)
            return int(m.group(1)) if m else -1
        return sorted(installed, key=ver, reverse=True)[0]
    raise RuntimeError(
        "Không tìm thấy ODBC driver cho SQL Server trên hệ thống. "
        "Vui lòng cài 'ODBC Driver 18 for SQL Server' (khuyến nghị) hoặc 'ODBC Driver 17 for SQL Server'."
    )

def _driver_label_to_braced(driver_label: str) -> str:
    """Đổi tên driver sang dạng có ngoặc nhọn đúng chuẩn ODBC."""
    d = (driver_label or "").strip()
    if d.startswith("{") and d.endswith("}"):
        return d
    return "{" + d + "}"

def build_connection_string(
    driver: str,
    server_input: str,
    port: str | int | None = None,
    database: str | None = "master",
    auth_mode: str = "sql",          # "sql" | "windows"
    user: str | None = None,
    password: str | None = None,
    encrypt: bool | None = None,     # None = tự động theo driver
    trust_server_certificate: bool = True,
    timeout: int = 8,
    application_intent: str | None = None,  # e.g. "ReadOnly"
) -> str:
    """
    Trả về pyodbc connection string cho SQL Server (ODBC 17/18).
    - Nếu có port -> luôn dùng HOST,PORT (không phụ thuộc SQL Browser).
    - Nếu không có port nhưng có INSTANCE -> dùng HOST\\INSTANCE (cần SQL Browser UDP 1434).
    - Tự dò và chọn driver phù hợp nếu driver mong muốn không tồn tại.
    """
    resolved = _pick_installed_sql_driver(driver or "ODBC Driver 18 for SQL Server")
    drv = _driver_label_to_braced(resolved)
    default_encrypt = ("18" in resolved)

    server_value = _build_server_for_odbc(server_input, str(port) if port is not None and str(port).strip() else None)

    parts = [
        f"Driver={drv}",
        f"Server={server_value}",
        f"Connection Timeout={int(timeout)}",
    ]
    if database:
        parts.append(f"Database={database}")

    use_encrypt = default_encrypt if encrypt is None else bool(encrypt)
    if use_encrypt:
        parts.append("Encrypt=yes")
        if trust_server_certificate:
            parts.append("TrustServerCertificate=yes")
    else:
        parts.append("Encrypt=no")

    if application_intent:
        parts.append(f"Application Intent={application_intent}")

    if auth_mode.lower().startswith("win"):
        parts.append("Trusted_Connection=yes")
    else:
        if not user:
            raise ValueError("auth_mode='sql' yêu cầu user.")
        if password is None:
            raise ValueError("auth_mode='sql' yêu cầu password.")
        parts.append(f"UID={user}")
        parts.append(f"PWD={password}")

    return ";".join(parts) + ";"

# ---- Preflight checks: DNS & Port ----
def _preflight_checks(server_input: str, port: Optional[str], timeout_s: int = 3) -> List[str]:
    """
    Trả về list cảnh báo/tình trạng trước khi connect:
    - Resolve tên host
    - Ping TCP port (connect socket) nếu có port
    """
    msgs: List[str] = []
    host = _normalize_host_for_port(server_input)
    try:
        ip = socket.gethostbyname(host)
        msgs.append(f"🧭 DNS: {host} → {ip}")
    except Exception as e:
        msgs.append(f"⚠️ DNS: Không resolve được '{host}': {e}")

    p = (port or "").strip()
    if p:
        try:
            with socket.create_connection((host, int(p)), timeout=timeout_s):
                msgs.append(f"🔌 TCP: Kết nối được {host}:{p}")
        except Exception as e:
            msgs.append(f"❌ TCP: Không kết nối được {host}:{p} - {e}")
    else:
        msgs.append("ℹ️ Bạn không nhập Port → Nếu dùng SERVER\\INSTANCE, cần SQL Browser (UDP 1434) và mở firewall.")

    return msgs

# ---- Thử nhiều driver tự động ----
def _candidate_drivers(preferred: str) -> List[str]:
    installed = _list_sql_odbc_drivers()
    if not installed:
        return [preferred]  # để lỗi rõ ràng hơn ở bước sau
    # sắp xếp theo số phiên bản (18 > 17 > 13 ...)
    def ver(n: str) -> int:
        import re
        m = re.search(r"(\d+)", n)
        return int(m.group(1)) if m else -1
    ordered = sorted(installed, key=ver, reverse=True)
    # đưa preferred lên đầu nếu có
    if preferred in ordered:
        ordered.remove(preferred)
        ordered.insert(0, preferred)
    return ordered

def _connect_once(conn_str: str, timeout_s: int) -> Tuple[bool, str]:
    import pyodbc
    try:
        with pyodbc.connect(conn_str, timeout=timeout_s) as cn:
            return True, cn.getinfo(pyodbc.SQL_SERVER_NAME)
    except pyodbc.Error as e:
        # gom thông điệp lỗi chi tiết
        details = []
        for arg in getattr(e, "args", []):
            details.append(str(arg))
        text = "; ".join(details) if details else str(e)
        return False, text
    except Exception as e:
        return False, str(e)

def _try_connect_pyodbc(driver: str, server: str, port: Optional[str],
                        auth: str, user: str, pwd: str,
                        encrypt: bool, trust: bool, timeout_s: int = 8) -> str:
    """Thử kết nối nhanh: preflight + thử nhiều driver nếu cần."""
    try:
        import pyodbc  # noqa: F401
    except Exception as e:
        raise RuntimeError("Chưa cài thư viện 'pyodbc'. Vui lòng chạy: pip install pyodbc") from e

    # Preflight
    for line in _preflight_checks(server, port, timeout_s=3):
        st.info(line)

    # Danh sách driver sẽ thử
    drivers = _candidate_drivers(driver or "ODBC Driver 18 for SQL Server")
    last_error = None
    for drv in drivers:
        try:
            conn_str = build_connection_string(
                driver=drv,
                server_input=server,
                port=(port.strip() if isinstance(port, str) else port),
                database="master",
                auth_mode=("windows" if auth == "Windows Authentication" else "sql"),
                user=(user or None),
                password=(pwd or None),
                encrypt=encrypt,
                trust_server_certificate=trust,
                timeout=timeout_s,
            )
        except Exception as e:
            last_error = f"[{drv}] build conn string lỗi: {e}"
            continue

        ok, info = _connect_once(conn_str, timeout_s=timeout_s)
        if ok:
            return f"OK. Driver: {drv} | Server name: {info}"
        else:
            last_error = f"[{drv}] {info}"
            # Nếu lỗi thuộc nhóm kết nối/driver, tiếp tục thử driver kế
            # IM002 (driver/DSN), 08001 (connection open), HYT00 (timeout), 28000 (login failed)
            if not any(code in info for code in ("IM002", "08001", "HYT00", "28000")):
                # lỗi kiểu khác (ví dụ syntax) -> dừng ngay
                break

    raise RuntimeError(last_error or "Không kết nối được với bất kỳ driver nào.")

# ---------------- Page ----------------
def render() -> None:
    st.title("Backup Tools")
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
            try:
                progress.progress(min(1.0, max(0.0, float(ratio))))
            except Exception:
                pass

        try:
            _safe_call(
                backup_utils.zip_folder,
                src=src,
                dst=dst,
                password=password or None,
                excludes=excludes or None,
                progress_callback=_cb,
            )
            st.success(f"✅ Đã tạo file ZIP: {dst}")
            try:
                with open(dst, "rb") as f:
                    st.download_button("⬇️ Tải ZIP", f, file_name=os.path.basename(dst), key="bf_dlzip")
            except Exception:
                pass
        except Exception as e:
            st.error(f"Lỗi khi nén thư mục: {e}")

# ---------------- Backup SQL ----------------
def backup_sql_tab() -> None:
    st.subheader("Backup SQL Server ")

    # ---- Kết nối ----
    col1, col2 = st.columns(2)
    with col1:
        driver = st.selectbox(
            "Driver ODBC",
            ["ODBC Driver 18 for SQL Server", "ODBC Driver 17 for SQL Server"],  # chỉ 2 lựa chọn
            index=1,  # mặc định 17
            key="sql_driver",
        )
        server = st.text_input("Server / Instance", value="localhost", key="sql_server")
    with col2:
        port = st.text_input("Port (tùy chọn, nên điền để tránh phụ thuộc SQL Browser)", value="", key="sql_port")

    auth = st.radio("Authentication", ["SQL Server Authentication", "Windows Authentication"], horizontal=True, key="sql_auth")
    user, pwd = "", ""
    if auth == "SQL Server Authentication":
        ucol, pcol = st.columns(2)
        with ucol:
            user = st.text_input("User", key="sql_user")
        with pcol:
            pwd = st.text_input("Password", type="password", key="sql_pwd")

    ecol, tcol = st.columns(2)
    with ecol:
        encrypt = st.checkbox("Encrypt", value=("18" in driver), key="sql_encrypt")
    with tcol:
        trust = st.checkbox("Trust server certificate", value=True, key="sql_trust")

    if "\\" in (server or "") and not (port or "").strip():
        st.warning(
            "Bạn đang dùng dạng SERVER\\INSTANCE **mà không nhập Port** → cần dịch vụ **SQL Browser (UDP 1434)** và mở firewall. "
            "Khuyến nghị: nhập Port (thường 1433) để ghép chuỗi **SERVER,PORT** cho ổn định."
        )

    # ---- Test nhanh kết nối ----
    if st.button("🧪 Test connection", key="sql_test"):
        try:
            # In ra danh sách driver sẵn có (nếu có pyodbc)
            drivers = _list_sql_odbc_drivers()
            if drivers:
                st.info(f"Drivers ODBC SQL Server đã cài: {', '.join(drivers)}")
            else:
                st.info("Chưa dò được driver hệ thống (có thể chưa cài pyodbc hoặc chưa có driver).")

            msg = _try_connect_pyodbc(driver, server, port, auth, user, pwd, encrypt, trust, timeout_s=8)
            st.success(msg)
        except Exception as e:
            st.error(f"❌ Kết nối thất bại: {e}")

    st.divider()

    # ---- Tải danh sách DB ----
    if st.button("🔗 Kết nối & tải danh sách DB", key="sql_listbtn"):
        try:
            server_for_utils = _build_server_for_odbc(server, port)
            dbs: List[str] = _safe_call(
                backup_utils.mssql_list_databases,
                driver=driver,
                server=server_for_utils,
                port=None,
                user=user,
                password=pwd,
                auth=auth,
                encrypt=encrypt,
                trust=trust,
            ) or []
            st.session_state["db_list"] = dbs
            st.success(f"Đã tải {len(dbs)} database.")
        except Exception as e:
            st.error(f"Lỗi khi tải DB: {e}")

    dbs = st.session_state.get("db_list", [])
    if dbs:
        database = st.selectbox("Chọn Database", dbs, key="sql_db")
    else:
        database = st.text_input("Tên Database", key="sql_dbtxt")

    # ---- Tuỳ chọn backup ----
    c1, c2, c3 = st.columns(3)
    with c1:
        copy_only = st.checkbox("COPY_ONLY", value=True, key="sql_copy")
    with c2:
        compression = st.checkbox("COMPRESSION", value=True, key="sql_comp")
    with c3:
        verify = st.checkbox("VERIFYONLY", value=False, key="sql_verify")

    dest_dir = st.text_input("Thư mục đích trên máy SQL Server", value="C:\\Backup", key="sql_dest")
    bak_name = st.text_input("Tên file .bak (tùy chọn)", value="", key="sql_bak")

    # ---- Backup ----
    if st.button("📀 Backup ngay", key="sql_backupbtn"):
        if not (database or "").strip():
            st.error("❌ Bạn phải nhập/chọn Database")
            return
        try:
            server_for_utils = _build_server_for_odbc(server, port)
            bak_path = _safe_call(
                backup_utils.mssql_backup_database,
                driver=driver,
                server=server_for_utils,
                user=user,
                password=pwd,
                auth=auth,
                database=database.strip(),
                dest_path=dest_dir.strip(),
                backup_file=(bak_name.strip() or None),
                copy_only=copy_only,
                compression=compression,
                verify_only=verify,
                encrypt=encrypt,
                trust=trust,
            )
            st.success(f"✅ Backup thành công: {bak_path}")
            try:
                if bak_path and os.path.exists(bak_path):
                    with open(bak_path, "rb") as f:
                        st.download_button("⬇️ Tải file BAK", f, file_name=os.path.basename(bak_path), key="sql_dlbak")
            except Exception:
                pass
        except Exception as e:
            st.error(f"Lỗi khi backup: {e}")

# Alias
main = render

if __name__ == "__main__":
    render()
