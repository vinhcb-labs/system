# ui/backup_page.py
from __future__ import annotations
import os
import sys
import socket
import platform
import datetime as dt
from typing import List, Optional, Tuple

import streamlit as st

# ======================== HỆ ĐIỀU HÀNH & THƯ VIỆN =========================
if platform.system() != "Windows":
    st.error("Công cụ này chỉ hỗ trợ Windows (để dò instance qua Registry).")
    st.stop()

try:
    import pyodbc
except Exception:
    st.error("Thiếu thư viện 'pyodbc'. Vui lòng cài:  \n`pip install pyodbc`")
    st.stop()

try:
    import winreg  # chuẩn Windows, không cần cài thêm
except Exception:
    st.error("Không truy cập được Windows Registry (winreg).")
    st.stop()


# ============================ TIỆN ÍCH CHUNG ===============================
def _pick_sql_odbc_driver() -> str:
    """
    Chọn driver ODBC SQL Server tốt nhất:
    - Ưu tiên 'ODBC Driver 18 for SQL Server'
    - Sau đó 'ODBC Driver 17 for SQL Server'
    - Nếu chỉ còn 'SQL Server' (DBNETLIB) -> báo lỗi vì quá cũ/TLS.
    """
    drivers = [d.strip() for d in pyodbc.drivers() if "SQL Server" in d]
    if "ODBC Driver 18 for SQL Server" in drivers:
        return "ODBC Driver 18 for SQL Server"
    if "ODBC Driver 17 for SQL Server" in drivers:
        return "ODBC Driver 17 for SQL Server"
    if "SQL Server" in drivers:
        raise RuntimeError(
            "Chỉ phát hiện driver cũ 'SQL Server' (DBNETLIB) — không hỗ trợ TLS/Encrypt hiện đại.\n"
            "Hãy cài 'ODBC Driver 18 for SQL Server' (khuyến nghị) hoặc 'ODBC Driver 17 for SQL Server'."
        )
    raise RuntimeError(
        "Không tìm thấy driver ODBC cho SQL Server.\n"
        "Hãy cài 'ODBC Driver 18 for SQL Server' (khuyến nghị) hoặc 'ODBC Driver 17 for SQL Server'."
    )


def _build_server_for_odbc(host: str, instance_name: Optional[str], port: Optional[int]) -> str:
    """
    - Nếu có port: trả 'HOST,PORT' (ổn định, không cần SQL Browser).
    - Nếu không có port:
        + Instance mặc định: 'HOST'
        + Instance tên riêng: 'HOST\\INSTANCE' (cần SQL Browser UDP 1434).
    """
    host = (host or "localhost").strip()
    if port:
        return f"{host},{int(port)}"
    if instance_name and instance_name.upper() != "MSSQLSERVER":
        return f"{host}\\{instance_name}"
    return host


def _tcp_probe(host: str, port: Optional[int], timeout=2) -> Tuple[bool, str]:
    if not port:
        return True, "Không có Port cố định (sẽ cần SQL Browser nếu dùng \\INSTANCE)."
    try:
        with socket.create_connection((host, int(port)), timeout=timeout):
            return True, f"TCP OK {host}:{port}"
    except Exception as e:
        return False, f"TCP FAIL {host}:{port} - {e}"


def _odbc_conn_str(
    driver: str,
    server_value: str,
    database: str = "master",
    auth: str = "windows",  # "windows" | "sql"
    user: Optional[str] = None,
    password: Optional[str] = None,
    encrypt: Optional[bool] = None,  # None -> auto theo driver
    trust_server_certificate: bool = True,
    timeout: int = 8,
) -> str:
    parts = [
        f"Driver={{{driver}}}".format(driver=driver),
        f"Server={server_value}",
        f"Database={database}",
        f"Connection Timeout={int(timeout)}",
    ]
    # Encrypt mặc định cho Driver 18 là Yes
    use_encrypt = (encrypt if encrypt is not None else ("18" in driver))
    parts.append("Encrypt=Yes" if use_encrypt else "Encrypt=No")
    if use_encrypt and trust_server_certificate:
        parts.append("TrustServerCertificate=Yes")

    if auth.lower().startswith("win"):
        parts.append("Trusted_Connection=Yes")
    else:
        if not user or password is None:
            raise ValueError("SQL Authentication yêu cầu user/password.")
        parts.append(f"UID={user}")
        parts.append(f"PWD={password}")

    return ";".join(parts) + ";"


# ===================== DÒ INSTANCE QUA REGISTRY (LOCAL) ====================
def _read_reg_value(root, path: str, name: str) -> Optional[str]:
    try:
        key = winreg.OpenKey(root, path)
        val, _ = winreg.QueryValueEx(key, name)
        winreg.CloseKey(key)
        return str(val)
    except Exception:
        return None


def _enum_reg_values(root, path: str) -> List[Tuple[str, str]]:
    """Trả về danh sách (value_name, value_data) trong key."""
    results = []
    try:
        key = winreg.OpenKey(root, path)
    except Exception:
        return results

    i = 0
    while True:
        try:
            name, val, _ = winreg.EnumValue(key, i)
            results.append((name, str(val)))
            i += 1
        except OSError:
            break
    winreg.CloseKey(key)
    return results


def detect_local_instances() -> List[dict]:
    """
    Tìm SQL Server instances cài trên máy:
      HKLM\SOFTWARE\Microsoft\Microsoft SQL Server\Instance Names\SQL
      HKLM\SOFTWARE\WOW6432Node\Microsoft\Microsoft SQL Server\Instance Names\SQL
    Lấy thêm Port từ:
      HKLM\SOFTWARE\Microsoft\Microsoft SQL Server\<InstanceID>\MSSQLServer\SuperSocketNetLib\Tcp\IPAll
    Trả về list dict: {instance, instance_id, port (int|None)}
    """
    ROOT = winreg.HKEY_LOCAL_MACHINE
    paths = [
        r"SOFTWARE\Microsoft\Microsoft SQL Server\Instance Names\SQL",
        r"SOFTWARE\WOW6432Node\Microsoft\Microsoft SQL Server\Instance Names\SQL",
    ]

    found: dict[str, str] = {}  # instance_name -> instance_id
    for p in paths:
        for name, inst_id in _enum_reg_values(ROOT, p):
            # name: 'MSSQLSERVER' | 'SQLEXPRESS' ...
            # inst_id: 'MSSQL15.MSSQLSERVER' | 'MSSQL16.SQLEXPRESS' ...
            if name not in found:
                found[name] = inst_id

    instances: List[dict] = []
    for inst_name, inst_id in found.items():
        tcp_path = rf"SOFTWARE\Microsoft\Microsoft SQL Server\{inst_id}\MSSQLServer\SuperSocketNetLib\Tcp\IPAll"
        tcp_path_wow = rf"SOFTWARE\WOW6432Node\Microsoft\Microsoft SQL Server\{inst_id}\MSSQLServer\SuperSocketNetLib\Tcp\IPAll"

        tcp_port = _read_reg_value(ROOT, tcp_path, "TcpPort") or _read_reg_value(ROOT, tcp_path_wow, "TcpPort")
        tcp_dyn = _read_reg_value(ROOT, tcp_path, "TcpDynamicPorts") or _read_reg_value(ROOT, tcp_path_wow, "TcpDynamicPorts")

        port: Optional[int] = None
        if tcp_port and tcp_port.strip().isdigit():
            port = int(tcp_port.strip())
        elif tcp_dyn:
            # 1 số bản đặt DynamicPorts là "0" hoặc chuỗi nhiều giá trị; chọn số đầu tiên hợp lệ
            for token in filter(None, [x.strip() for x in tcp_dyn.split(",")]):
                if token.isdigit():
                    port = int(token)
                    break

        instances.append({
            "instance": inst_name,          # 'MSSQLSERVER' | 'SQLEXPRESS' ...
            "instance_id": inst_id,         # 'MSSQL16.SQLEXPRESS' ...
            "port": port                    # int | None
        })

    # Ưu tiên instance mặc định trên cùng
    instances.sort(key=lambda x: (x["instance"] != "MSSQLSERVER", x["instance"]))
    return instances


# =========================== HÀM LÀM VIỆC VỚI DB ===========================
def open_connection(server_value: str, auth: str, user: Optional[str], pwd: Optional[str]) -> pyodbc.Connection:
    driver = _pick_sql_odbc_driver()
    conn_str = _odbc_conn_str(
        driver=driver,
        server_value=server_value,
        database="master",
        auth=("windows" if auth == "Windows Authentication" else "sql"),
        user=user,
        password=pwd,
        encrypt=None,  # auto
        trust_server_certificate=True,
        timeout=8,
    )
    return pyodbc.connect(conn_str, timeout=8)


def list_databases(cnxn: pyodbc.Connection, include_system: bool = False) -> List[str]:
    sql = "SELECT name FROM sys.databases"
    if not include_system:
        sql += " WHERE name NOT IN ('master','tempdb','model','msdb')"
    sql += " ORDER BY name;"
    cur = cnxn.cursor()
    rows = cur.execute(sql).fetchall()
    return [r[0] for r in rows]


def backup_database(cnxn: pyodbc.Connection, db: str, dest_dir: str, file_name: Optional[str] = None,
                    copy_only: bool = True, compression: bool = True, verify: bool = False) -> str:
    db_q = "[" + db.replace("]", "]]") + "]"
    os.makedirs(dest_dir, exist_ok=True)  # tạo thư mục trên máy local; với local SQL cũng hữu ích

    if not file_name:
        ts = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        file_name = f"{db}_{ts}.bak"

    full_path = os.path.abspath(os.path.join(dest_dir, file_name))

    # Lưu ý: backup chạy TRÊN SQL SERVER. Nếu SQL là local thì đường dẫn local giống nhau.
    # Nếu SQL ở máy khác -> đường dẫn phải là thư mục của MÁY SQL, không phải máy client.
    opts = []
    if copy_only:
        opts.append("COPY_ONLY")
    if compression:
        opts.append("COMPRESSION")
    opts.append("INIT")
    opts.append("STATS=10")
    with cnxn.cursor() as cur:
        cur.execute(f"BACKUP DATABASE {db_q} TO DISK = ? WITH {', '.join(opts)};", (full_path,))
        cur.commit()
        if verify:
            cur.execute("RESTORE VERIFYONLY FROM DISK = ?;", (full_path,))
            cur.commit()
    return full_path


# ================================== UI =====================================
def render():
    st.title("SQL Server — Auto Detect & Backup")

    # --------- Phát hiện instance cục bộ ----------
    with st.expander("🔎 Instances phát hiện trên máy (Registry)", expanded=True):
        try:
            instances = detect_local_instances()
            if not instances:
                st.error("Không tìm thấy SQL Server instance trong Registry.\n"
                         "• Hãy cài SQL Server hoặc đảm bảo bạn có quyền đọc Registry.\n"
                         "• Nếu dùng LocalDB, hãy khởi tạo qua `SqlLocalDB` và kết nối bằng `(localdb)\\MSSQLLocalDB`.")
                st.stop()
            for i, ins in enumerate(instances, 1):
                st.write(f"{i}. **{ins['instance']}**  "
                         f"(Instance ID: `{ins['instance_id']}`)  "
                         f"→ Port: `{ins['port'] if ins['port'] else '—'}`")
        except Exception as e:
            st.error(f"Lỗi khi dò instance: {e}")
            st.stop()

    # --------- Chọn instance cần dùng ----------
    ins_names = [ins["instance"] for ins in instances]
    pick = st.selectbox("Chọn instance", ins_names, index=0, key="ins_pick")

    # --------- Authentication ----------
    colA, colB = st.columns([1, 2])
    with colA:
        auth = st.radio("Authentication", ["Windows Authentication", "SQL Server Authentication"], horizontal=False, key="auth_mode")
    user = pwd = None
    with colB:
        if auth == "SQL Server Authentication":
            user = st.text_input("User (ví dụ: sa)", key="auth_user")
            pwd = st.text_input("Password", type="password", key="auth_pwd")

    # --------- Kết nối & Load DB ----------
    if st.button("🔗 Kết nối & lấy danh sách DB", type="primary"):
        try:
            chosen = next(x for x in instances if x["instance"] == pick)
            server_value = _build_server_for_odbc("localhost", chosen["instance"], chosen["port"])
            ok, note = _tcp_probe("localhost", chosen["port"])
            st.info(note)
            cn = open_connection(server_value, auth, user, pwd)
            with cn:
                dbs = list_databases(cn, include_system=False)
            st.session_state["server_value"] = server_value
            st.session_state["dbs"] = dbs
            st.success(f"Đã lấy {len(dbs)} database.")
        except StopIteration:
            st.error("Không tìm thấy instance đã chọn.")
        except Exception as e:
            st.error(f"Lỗi khi kết nối/đọc DB: {e}")

    dbs = st.session_state.get("dbs", [])
    if dbs:
        st.divider()
        st.subheader("📀 Backup database")
        col1, col2 = st.columns(2)
        with col1:
            db_pick = st.selectbox("Chọn database", dbs, key="db_pick")
        with col2:
            dest_dir = st.text_input("Thư mục đích trên máy SQL Server", value="C:\\Backup", key="dest_dir")

        col3, col4, col5 = st.columns(3)
        with col3:
            copy_only = st.checkbox("COPY_ONLY", value=True)
        with col4:
            compression = st.checkbox("COMPRESSION", value=True)
        with col5:
            verify = st.checkbox("VERIFYONLY", value=False)

        file_name = st.text_input("Tên file .bak (tùy chọn)", value="", key="bak_name")

        if st.button("🚀 Backup ngay"):
            try:
                server_value = st.session_state.get("server_value")
                if not server_value:
                    st.error("Chưa có kết nối hợp lệ.")
                else:
                    cn = open_connection(server_value, auth, user, pwd)
                    with cn:
                        path = backup_database(
                            cn,
                            db=db_pick,
                            dest_dir=dest_dir.strip(),
                            file_name=(file_name.strip() or None),
                            copy_only=copy_only,
                            compression=compression,
                            verify=verify,
                        )
                    st.success(f"✅ Backup thành công: {path}")
                    try:
                        if os.path.exists(path):
                            with open(path, "rb") as f:
                                st.download_button("⬇️ Tải file BAK", f, file_name=os.path.basename(path))
                    except Exception:
                        pass
            except Exception as e:
                st.error(f"Lỗi khi backup: {e}")

# Alias (giữ tương thích nếu import)
main = render

if __name__ == "__main__":
    render()
