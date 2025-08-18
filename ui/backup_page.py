# ui/backup_page.py
from __future__ import annotations
import os
import sys
import socket
import platform
import datetime as dt
from typing import List, Optional, Tuple, Dict

import streamlit as st

# ========================= Thư viện bắt buộc =========================
try:
    import pyodbc
except Exception:
    st.error("Thiếu thư viện 'pyodbc'. Cài: `pip install pyodbc`")
    st.stop()

# ============================ Utils: Driver ==========================
def pick_sql_odbc_driver() -> str:
    """
    Chọn driver ODBC cho SQL Server:
      - Ưu tiên ODBC Driver 18 for SQL Server
      - Sau đó ODBC Driver 17 for SQL Server
      - Từ chối 'SQL Server' (DBNETLIB) vì quá cũ/TLS
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

def build_odbc_conn_str(
    driver: str,
    server_value: str,
    database: str = "master",
    auth: str = "windows",   # "windows" | "sql"
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
    # Driver 18 mặc định Encrypt=Yes
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

def normalize_host_for_port(server: str) -> str:
    server = (server or "localhost").strip()
    if "\\" in server:
        host, _ = server.split("\\", 1)
        return host.strip()
    return server

def build_server_for_odbc(host: str, instance: Optional[str], port: Optional[int]) -> str:
    """
    - Có port -> 'HOST,PORT' (ổn định, không cần SQL Browser)
    - Không có port:
        + Instance mặc định -> 'HOST'
        + Named instance -> 'HOST\\INSTANCE' (cần SQL Browser)
    """
    host = (host or "localhost").strip()
    if port:
        return f"{host},{int(port)}"
    if instance and instance.upper() != "MSSQLSERVER":
        return f"{host}\\{instance}"
    return host

# ===================== SSRP (SQL Server Browser) ======================
def _ssrp_query(host: str = "127.0.0.1", timeout: float = 0.8) -> bytes | None:
    """
    Gửi gói 0x02 tới UDP 1434 để hỏi danh sách instance trên host.
    Trả về bytes phản hồi (ASCII key-value;…;) hoặc None nếu không trả lời.
    """
    buf = None
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(timeout)
    try:
        sock.sendto(b"\x02", (host, 1434))
        buf, _ = sock.recvfrom(8192)
    except Exception:
        buf = None
    finally:
        try:
            sock.close()
        except Exception:
            pass
    return buf

def _parse_ssrp_instances(payload: bytes) -> List[Dict[str, str]]:
    """
    Phân tích chuỗi phản hồi SSRP thành list instance.
    Định dạng: 'ServerName;HOST;InstanceName;SQLEXPRESS;IsClustered;No;Version;...;tcp;1433;np;...;ServerName;HOST;InstanceName;...;'
    """
    text = (payload or b"").decode("ascii", errors="ignore")
    tokens = [t for t in text.strip(";\x00").split(";") if t != ""]
    result: List[Dict[str, str]] = []
    i = 0
    current: Dict[str, str] = {}
    while i < len(tokens):
        key = tokens[i]
        val = tokens[i + 1] if (i + 1) < len(tokens) else ""
        i += 2
        if key == "ServerName":
            # Bắt đầu instance mới
            if current:
                result.append(current)
            current = {key: val}
        else:
            current[key] = val
    if current:
        result.append(current)
    return result

def detect_instances_ssrp_local() -> List[dict]:
    """
    Dò instance qua SQL Browser (UDP 1434) trên localhost. Trả về [{instance, port}, ...]
    """
    payload = _ssrp_query("127.0.0.1", timeout=0.8)
    if not payload:
        return []
    infos = _parse_ssrp_instances(payload)
    items: List[dict] = []
    for info in infos:
        name = info.get("InstanceName") or "MSSQLSERVER"
        tcp = info.get("tcp")
        port = int(tcp) if tcp and tcp.isdigit() else None
        items.append({"instance": name, "port": port})
    # Ưu tiên instance mặc định
    items.sort(key=lambda x: (x["instance"] != "MSSQLSERVER", x["instance"]))
    # Loại trùng
    dedup: Dict[str, dict] = {}
    for it in items:
        dedup.setdefault(it["instance"], it)
    return list(dedup.values())

# =================== Windows Registry (nếu khả dụng) ===================
def detect_instances_registry() -> List[dict]:
    """
    Trả về danh sách instance từ Registry (chỉ Windows). [{instance, port}, ...]
    """
    if platform.system() != "Windows":
        return []
    try:
        import winreg  # type: ignore
    except Exception:
        return []

    def read_value(root, path: str, name: str) -> Optional[str]:
        try:
            key = winreg.OpenKey(root, path)
            val, _ = winreg.QueryValueEx(key, name)
            winreg.CloseKey(key)
            return str(val)
        except Exception:
            return None

    def enum_values(root, path: str) -> List[Tuple[str, str]]:
        results = []
        try:
            key = winreg.OpenKey(root, path)
        except Exception:
            return results
        i = 0
        while True:
            try:
                nm, val, _ = winreg.EnumValue(key, i)
                results.append((nm, str(val)))
                i += 1
            except OSError:
                break
        winreg.CloseKey(key)
        return results

    ROOT = winreg.HKEY_LOCAL_MACHINE
    paths = [
        r"SOFTWARE\Microsoft\Microsoft SQL Server\Instance Names\SQL",
        r"SOFTWARE\WOW6432Node\Microsoft\Microsoft SQL Server\Instance Names\SQL",
    ]
    name_to_id: Dict[str, str] = {}
    for p in paths:
        for nm, inst_id in enum_values(ROOT, p):
            name_to_id.setdefault(nm, inst_id)

    items: List[dict] = []
    for inst_name, inst_id in name_to_id.items():
        ipall = rf"SOFTWARE\Microsoft\Microsoft SQL Server\{inst_id}\MSSQLServer\SuperSocketNetLib\Tcp\IPAll"
        ipall_wow = rf"SOFTWARE\WOW6432Node\Microsoft\Microsoft SQL Server\{inst_id}\MSSQLServer\SuperSocketNetLib\Tcp\IPAll"
        tcp_port = read_value(ROOT, ipall, "TcpPort") or read_value(ROOT, ipall_wow, "TcpPort")
        tcp_dyn = read_value(ROOT, ipall, "TcpDynamicPorts") or read_value(ROOT, ipall_wow, "TcpDynamicPorts")
        port: Optional[int] = None
        if tcp_port and tcp_port.strip().isdigit():
            port = int(tcp_port.strip())
        elif tcp_dyn:
            for token in filter(None, [x.strip() for x in tcp_dyn.split(",")]):
                if token.isdigit():
                    port = int(token)
                    break
        items.append({"instance": inst_name, "port": port})
    items.sort(key=lambda x: (x["instance"] != "MSSQLSERVER", x["instance"]))
    return items

# ====================== Tổng hợp phát hiện instance ======================
def detect_local_instances() -> List[dict]:
    """
    Gộp Registry (nếu có) + SSRP (UDP 1434) rồi loại trùng.
    Nếu vẫn không có, thử default localhost:1433 nếu port mở.
    """
    merged: Dict[str, dict] = {}
    for it in detect_instances_registry():
        merged[it["instance"]] = it
    for it in detect_instances_ssrp_local():
        merged.setdefault(it["instance"], it)

    items = list(merged.values())
    if not items:
        # Fallback: thử 1433
        ok, _ = tcp_probe("127.0.0.1", 1433, timeout=0.6)
        if ok:
            items = [{"instance": "MSSQLSERVER", "port": 1433}]
    items.sort(key=lambda x: (x["instance"] != "MSSQLSERVER", x["instance"]))
    return items

def tcp_probe(host: str, port: int, timeout: float = 0.6) -> Tuple[bool, str]:
    try:
        with socket.create_connection((host, int(port)), timeout=timeout):
            return True, f"TCP OK {host}:{port}"
    except Exception as e:
        return False, f"TCP FAIL {host}:{port} - {e}"

# ============================ DB operations ============================
def open_connection(server_value: str, auth_mode: str, user: Optional[str], pwd: Optional[str]) -> pyodbc.Connection:
    driver = pick_sql_odbc_driver()
    conn_str = build_odbc_conn_str(
        driver=driver,
        server_value=server_value,
        database="master",
        auth=("windows" if auth_mode == "Windows Authentication" else "sql"),
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
    with cnxn.cursor() as cur:
        rows = cur.execute(sql).fetchall()
    return [r[0] for r in rows]

def backup_database(
    cnxn: pyodbc.Connection,
    db: str,
    dest_dir: str,
    file_name: Optional[str] = None,
    copy_only: bool = True,
    compression: bool = True,
    verify: bool = False,
) -> str:
    db_q = "[" + db.replace("]", "]]") + "]"
    if not file_name:
        ts = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        file_name = f"{db}_{ts}.bak"
    full_path = os.path.abspath(os.path.join(dest_dir, file_name))

    opts = []
    if copy_only:
        opts.append("COPY_ONLY")
    if compression:
        opts.append("COMPRESSION")
    opts.extend(["INIT", "STATS=10"])

    with cnxn.cursor() as cur:
        cur.execute(f"BACKUP DATABASE {db_q} TO DISK = ? WITH {', '.join(opts)};", (full_path,))
        cur.commit()
        if verify:
            cur.execute("RESTORE VERIFYONLY FROM DISK = ?;", (full_path,))
            cur.commit()
    return full_path

# ================================ UI =================================
def render():
    st.title("SQL Server — Auto Detect (Cross-Platform) & Backup")

    # --------- Phát hiện instance cục bộ ----------
    with st.expander("🔎 Instances phát hiện trên máy (Registry & SSRP)", expanded=True):
        try:
            items = detect_local_instances()
            if not items:
                st.error(
                    "Không phát hiện được instance cục bộ.\n"
                    "• Hãy đảm bảo SQL Server đã cài & đang chạy.\n"
                    "• Nếu là named instance, bật dịch vụ **SQL Server Browser** (UDP 1434).\n"
                    "• Hoặc mở port TCP (thường 1433) để công cụ dò."
                )
                st.stop()
            for i, it in enumerate(items, 1):
                st.write(f"{i}. **{it['instance']}** → Port: `{it['port'] if it['port'] else '—'}`")
        except Exception as e:
            st.error(f"Lỗi khi dò instance: {e}")
            st.stop()

    ins_names = [it["instance"] for it in items]
    pick = st.selectbox("Chọn instance", ins_names, index=0, key="ins_pick")

    # --------- Authentication ----------
    colA, colB = st.columns([1, 2])
    with colA:
        default_auth = "Windows Authentication" if platform.system() == "Windows" else "SQL Server Authentication"
        auth = st.radio("Authentication", ["Windows Authentication", "SQL Server Authentication"], index=0 if default_auth.startswith("Windows") else 1, key="auth_mode")
    user = pwd = None
    with colB:
        if auth == "SQL Server Authentication":
            user = st.text_input("User (ví dụ: sa)", key="auth_user")
            pwd = st.text_input("Password", type="password", key="auth_pwd")

    # --------- Kết nối & Load DB ----------
    if st.button("🔗 Kết nối & lấy danh sách DB", type="primary"):
        try:
            chosen = next(x for x in items if x["instance"] == pick)
            host = "localhost"
            server_value = build_server_for_odbc(host, chosen["instance"], chosen["port"])
            # Info TCP nếu biết port
            if chosen["port"]:
                ok, note = tcp_probe(normalize_host_for_port(server_value), chosen["port"])
                st.info(note)
            cn = open_connection(server_value, auth, user, pwd)
            with cn:
                dbs = list_databases(cn, include_system=False)
            st.session_state["server_value"] = server_value
            st.session_state["auth"] = auth
            st.session_state["user"] = user
            st.session_state["pwd"] = pwd
            st.session_state["dbs"] = dbs
            st.success(f"Đã lấy {len(dbs)} database.")
        except StopIteration:
            st.error("Không tìm thấy instance đã chọn.")
        except Exception as e:
            st.error(f"Lỗi khi kết nối/đọc DB: {e}")

    dbs = st.session_state.get("dbs", [])
    if not dbs:
        st.stop()

    st.divider()
    st.subheader("📀 Backup database")

    col1, col2 = st.columns(2)
    with col1:
        db_pick = st.selectbox("Chọn database", dbs, key="db_pick")

    # Thư mục đích: mặc định theo HĐH
    default_dir = "C:\\Backup" if platform.system() == "Windows" else "/var/opt/mssql/backups"
    with col2:
        dest_dir = st.text_input("Thư mục đích trên máy SQL Server", value=default_dir, key="dest_dir")

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
            auth = st.session_state.get("auth")
            user = st.session_state.get("user")
            pwd = st.session_state.get("pwd")
            if not server_value:
                st.error("Chưa có kết nối hợp lệ.")
                st.stop()
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
            # Lưu ý: file do SQL Server ghi; nếu SQL ở máy khác, nút tải dưới đây có thể không đọc được.
            try:
                if os.path.exists(path):
                    with open(path, "rb") as f:
                        st.download_button("⬇️ Tải file BAK", f, file_name=os.path.basename(path))
            except Exception:
                pass
        except Exception as e:
            st.error(f"Lỗi khi backup: {e}")

# Alias
main = render

if __name__ == "__main__":
    render()
