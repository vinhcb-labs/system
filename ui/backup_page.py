# ui/backup_page.py
from __future__ import annotations
import os
import re
import sys
import socket
import platform
import subprocess
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
    # Driver 18 mặc định Encrypt=Yes; với LocalDB/Named Pipes/Shared Memory nên tắt
    if encrypt is None:
        s = server_value.lower()
        encrypt = not (s.startswith("lpc:") or s.startswith("np:") or "(localdb)" in s)

    parts.append("Encrypt=Yes" if encrypt else "Encrypt=No")
    if encrypt and trust_server_certificate:
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

# ===================== TCP probe (kiểm tra cổng) ======================
def tcp_probe(host: str, port: int, timeout: float = 0.6) -> Tuple[bool, str]:
    try:
        with socket.create_connection((host, int(port)), timeout=timeout):
            return True, f"TCP OK {host}:{port}"
    except Exception as e:
        return False, f"TCP FAIL {host}:{port} - {e}"

# ===================== SSRP (SQL Server Browser) ======================
def _ssrp_query(host: str = "127.0.0.1", timeout: float = 0.8) -> bytes | None:
    """Hỏi SQL Browser (UDP 1434) để lấy danh sách instance."""
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
            if current:
                result.append(current)
            current = {key: val}
        else:
            current[key] = val
    if current:
        result.append(current)
    return result

def detect_instances_ssrp_local() -> List[dict]:
    payload = _ssrp_query("127.0.0.1", timeout=0.8)
    if not payload:
        return []
    infos = _parse_ssrp_instances(payload)
    items: List[dict] = []
    for info in infos:
        name = info.get("InstanceName") or "MSSQLSERVER"
        tcp = info.get("tcp")
        port = int(tcp) if tcp and tcp.isdigit() else None
        items.append({"source": "SSRP", "instance": name, "port": port})
    items.sort(key=lambda x: (x["instance"] != "MSSQLSERVER", x["instance"]))
    dedup: Dict[str, dict] = {}
    for it in items:
        dedup.setdefault(it["instance"], it)
    return list(dedup.values())

# =================== Windows Registry (nếu khả dụng) ===================
def detect_instances_registry() -> List[dict]:
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

    def enum_subkeys(root, path: str) -> List[str]:
        keys = []
        try:
            key = winreg.OpenKey(root, path)
        except Exception:
            return keys
        i = 0
        while True:
            try:
                sub = winreg.EnumKey(key, i)
                keys.append(sub)
                i += 1
            except OSError:
                break
        winreg.CloseKey(key)
        return keys

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
        tcp_root = rf"SOFTWARE\Microsoft\Microsoft SQL Server\{inst_id}\MSSQLServer\SuperSocketNetLib\Tcp"
        tcp_root_wow = rf"SOFTWARE\WOW6432Node\Microsoft\Microsoft SQL Server\{inst_id}\MSSQLServer\SuperSocketNetLib\Tcp"

        # Ưu tiên IPAll
        tcp_port = (
            read_value(ROOT, tcp_root + r"\IPAll", "TcpPort")
            or read_value(ROOT, tcp_root_wow + r"\IPAll", "TcpPort")
        )
        tcp_dyn = (
            read_value(ROOT, tcp_root + r"\IPAll", "TcpDynamicPorts")
            or read_value(ROOT, tcp_root_wow + r"\IPAll", "TcpDynamicPorts")
        )
        port: Optional[int] = None
        if tcp_port and tcp_port.strip().isdigit():
            port = int(tcp_port.strip())
        elif tcp_dyn:
            for token in filter(None, [x.strip() for x in tcp_dyn.split(",")]):
                if token.isdigit() and token != "0":
                    port = int(token)
                    break

        # Nếu IPAll không có, quét từng IPn
        if port is None:
            for base in (tcp_root, tcp_root_wow):
                for sub in enum_subkeys(ROOT, base):
                    if not sub.upper().startswith("IP"):
                        continue
                    en = read_value(ROOT, rf"{base}\{sub}", "Enabled")
                    if en and en.strip().isdigit() and int(en) == 1:
                        p1 = read_value(ROOT, rf"{base}\{sub}", "TcpPort")
                        p2 = read_value(ROOT, rf"{base}\{sub}", "TcpDynamicPorts")
                        if p1 and p1.strip().isdigit():
                            port = int(p1.strip())
                            break
                        if p2:
                            for token in filter(None, [x.strip() for x in p2.split(",")]):
                                if token.isdigit() and token != "0":
                                    port = int(token)
                                    break
                    if port is not None:
                        break
                if port is not None:
                    break

        items.append({"source": "Registry", "instance": inst_name, "port": port})
    items.sort(key=lambda x: (x["instance"] != "MSSQLSERVER", x["instance"]))
    return items

# ================= Windows Services (không cần quyền admin) ============
def detect_instances_services_windows() -> List[dict]:
    if platform.system() != "Windows":
        return []
    try:
        # Dò qua sc.exe để lấy danh sách dịch vụ
        cp = subprocess.run(["sc", "query", "type=", "service", "state=", "all"], capture_output=True)
        text = cp.stdout.decode(errors="ignore")
    except Exception:
        return []
    names = re.findall(r"SERVICE_NAME:\s*(\S+)", text, flags=re.IGNORECASE)
    items: List[dict] = []
    for n in names:
        if n.upper() == "MSSQLSERVER":
            items.append({"source": "Service", "instance": "MSSQLSERVER", "port": None})
        elif n.upper().startswith("MSSQL$"):
            inst = n.split("$", 1)[1]
            items.append({"source": "Service", "instance": inst, "port": None})
    # Loại trùng
    dedup: Dict[str, dict] = {}
    for it in items:
        dedup.setdefault(it["instance"], it)
    items = list(dedup.values())
    items.sort(key=lambda x: (x["instance"] != "MSSQLSERVER", x["instance"]))
    return items

# ====================== LocalDB (nếu có SqlLocalDB) ====================
def detect_instances_localdb() -> List[dict]:
    try:
        cp = subprocess.run(["SqlLocalDB", "info"], capture_output=True)
        if cp.returncode != 0:
            return []
        text = cp.stdout.decode(errors="ignore")
        names = [ln.strip() for ln in text.splitlines() if ln.strip() and not ln.strip().startswith("LocalDB")]
        items = []
        for nm in names:
            items.append({"source": "LocalDB", "instance": nm, "port": None})
        return items
    except Exception:
        return []

# ====================== Tổng hợp phát hiện instance ======================
def detect_local_instances() -> List[dict]:
    """
    Gộp Registry (Windows) + SSRP (UDP 1434) + Services (Windows) + LocalDB rồi loại trùng.
    Nếu vẫn rỗng, thử default localhost:1433 nếu cổng mở.
    """
    merged: Dict[str, dict] = {}

    for it in detect_instances_registry():
        merged[it["instance"]] = it
    for it in detect_instances_ssrp_local():
        merged.setdefault(it["instance"], it)
        # Nếu SSRP cung cấp port thì cập nhật
        if it.get("port") and merged[it["instance"]].get("port") is None:
            merged[it["instance"]]["port"] = it["port"]
    for it in detect_instances_services_windows():
        merged.setdefault(it["instance"], it)
    for it in detect_instances_localdb():
        merged.setdefault(it["instance"], it)

    items = list(merged.values())
    # Fallback: nếu không có gì và 1433 mở, coi như default
    if not items:
        ok, _ = tcp_probe("127.0.0.1", 1433, timeout=0.6)
        if ok:
            items = [{"source": "Fallback", "instance": "MSSQLSERVER", "port": 1433}]

    items.sort(key=lambda x: (x["instance"] != "MSSQLSERVER", x["instance"]))
    return items

# ============================ Kết nối đa chế độ ===========================
def server_variants_for_instance(instance: str, port: Optional[int]) -> List[str]:
    """
    Trả về nhiều biến thể server để thử:
      - TCP (nếu có port): 127.0.0.1,PORT và localhost,PORT
      - Shared Memory (lpc:) cho local
      - Named Pipe (np:) cho default/named
      - HOST\INSTANCE (cần SQL Browser nếu không có port)
      - LocalDB: (localdb)\NAME
    """
    v: List[str] = []
    if instance.lower().startswith("(localdb)"):
        # (localdb)\MSSQLLocalDB
        v.append(instance)  # giữ nguyên
        return v

    # TCP khi có port
    if port:
        v.append(f"127.0.0.1,{port}")
        v.append(f"localhost,{port}")

    # Shared Memory (local only)
    if instance.upper() == "MSSQLSERVER":
        v.append("lpc:.")
        v.append("np:\\\\.\\pipe\\sql\\query")
        v.append("localhost")
        v.append(".")
    else:
        v.append(f"lpc:localhost\\{instance}")
        v.append(f"np:\\\\.\\pipe\\MSSQL${instance}\\sql\\query")
        v.append(f"localhost\\{instance}")
        v.append(f".\\{instance}")

    return v

def try_open_connection(
    instance: str,
    port: Optional[int],
    auth_mode: str,
    user: Optional[str],
    pwd: Optional[str],
    timeout: int = 8,
) -> Tuple[pyodbc.Connection, str]:
    """
    Thử lần lượt các biến thể server cho tới khi kết nối được.
    Trả về (connection, server_value_đã_dùng).
    """
    driver = pick_sql_odbc_driver()
    last_err = None
    for server_value in server_variants_for_instance(instance, port):
        try:
            conn_str = build_odbc_conn_str(
                driver=driver,
                server_value=server_value,
                database="master",
                auth=("windows" if auth_mode == "Windows Authentication" else "sql"),
                user=user,
                password=pwd,
                encrypt=None,  # auto; sẽ tắt nếu lpc:/np:/localdb
                trust_server_certificate=True,
                timeout=timeout,
            )
            cn = pyodbc.connect(conn_str, timeout=timeout)
            return cn, server_value
        except Exception as e:
            last_err = f"{server_value} -> {e}"
            continue
    raise RuntimeError(last_err or "Không thể mở kết nối với bất kỳ biến thể server nào.")

# ============================ DB operations ============================
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
    st.title("SQL Server — Auto Detect & Backup (Enhanced)")

    # --------- Phát hiện instance cục bộ ----------
    with st.expander("🔎 Instances phát hiện trên máy (Registry / SSRP / Services / LocalDB)", expanded=True):
        try:
            items = detect_local_instances()
            if not items:
                st.error(
                    "Không phát hiện được instance cục bộ.\n"
                    "• Đảm bảo SQL Server đã cài & đang chạy.\n"
                    "• Với named instance không đặt port tĩnh, hãy bật dịch vụ **SQL Server Browser** (UDP 1434).\n"
                    "• Hoặc đặt **TCP Port tĩnh** trong SQL Server Configuration Manager."
                )
                st.stop()
            for i, it in enumerate(items, 1):
                src = it.get("source", "?")
                st.write(f"{i}. **{it['instance']}**  (nguồn: {src})  → Port: `{it['port'] if it['port'] else '—'}`")
        except Exception as e:
            st.error(f"Lỗi khi dò instance: {e}")
            st.stop()

    ins_names = [it["instance"] for it in items]
    pick = st.selectbox("Chọn instance", ins_names, index=0, key="ins_pick")

    # --------- Authentication ----------
    colA, colB = st.columns([1, 2])
    with colA:
        default_auth = "Windows Authentication" if platform.system() == "Windows" else "SQL Server Authentication"
        auth = st.radio("Authentication", ["Windows Authentication", "SQL Server Authentication"],
                        index=0 if default_auth.startswith("Windows") else 1, key="auth_mode")
    user = pwd = None
    with colB:
        if auth == "SQL Server Authentication":
            user = st.text_input("User (ví dụ: sa)", key="auth_user")
            pwd = st.text_input("Password", type="password", key="auth_pwd")

    # --------- Kết nối & Load DB ----------
    if st.button("🔗 Kết nối & lấy danh sách DB", type="primary"):
        try:
            chosen = next(x for x in items if x["instance"] == pick)
            instance = chosen["instance"]
            port = chosen.get("port")

            # Thông tin TCP nếu có
            if port:
                ok, note = tcp_probe("127.0.0.1", port, timeout=0.8)
                st.info(note)

            cn, used_server = try_open_connection(instance, port, auth, user, pwd, timeout=8)
            with cn:
                dbs = list_databases(cn, include_system=False)

            st.session_state["used_server"] = used_server
            st.session_state["auth"] = auth
            st.session_state["user"] = user
            st.session_state["pwd"] = pwd
            st.session_state["dbs"] = dbs
            st.success(f"Đã kết nối bằng: `{used_server}` — Lấy được {len(dbs)} database.")
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
            used_server = st.session_state.get("used_server")
            auth = st.session_state.get("auth")
            user = st.session_state.get("user")
            pwd = st.session_state.get("pwd")
            if not used_server:
                st.error("Chưa có kết nối hợp lệ.")
                st.stop()

            driver = pick_sql_odbc_driver()
            conn_str = build_odbc_conn_str(
                driver=driver,
                server_value=used_server,
                database="master",
                auth=("windows" if auth == "Windows Authentication" else "sql"),
                user=user,
                password=pwd,
                encrypt=None,
                trust_server_certificate=True,
                timeout=12,
            )
            cn = pyodbc.connect(conn_str, timeout=12)
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

# Alias
main = render

if __name__ == "__main__":
    render()
