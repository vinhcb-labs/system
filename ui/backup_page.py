# ui/backup_page.py
from __future__ import annotations
import os
import platform
import subprocess
import datetime as dt
from typing import List, Optional, Tuple, Dict

import streamlit as st

# =============== Bắt buộc: pyodbc ==================
try:
    import pyodbc
except Exception:
    st.error("Thiếu thư viện 'pyodbc'. Hãy cài:  pip install pyodbc")
    st.stop()

# ================== ODBC driver ====================
def pick_sql_odbc_driver() -> str:
    """Ưu tiên Driver 18 → 17; từ chối 'SQL Server' (DBNETLIB)."""
    drivers = [d for d in pyodbc.drivers() if "SQL Server" in d]
    if "ODBC Driver 18 for SQL Server" in drivers:
        return "ODBC Driver 18 for SQL Server"
    if "ODBC Driver 17 for SQL Server" in drivers:
        return "ODBC Driver 17 for SQL Server"
    if "SQL Server" in drivers:
        raise RuntimeError(
            "Chỉ thấy driver cũ 'SQL Server' (DBNETLIB) — không hỗ trợ TLS hiện đại.\n"
            "Hãy cài 'ODBC Driver 18/17 for SQL Server'."
        )
    raise RuntimeError("Không tìm thấy ODBC driver cho SQL Server.")

def build_conn_str(
    driver: str,
    server_value: str,
    database: str = "master",
    user: str | None = None,
    password: str | None = None,
    timeout: int = 8,
) -> str:
    """
    - Tự tắt Encrypt nếu dùng lpc:/np:/(localdb) (kết nối nội bộ).
    - Dùng SQL Authentication (user + password).
    """
    parts = [
        f"Driver={{{driver}}}",
        f"Server={server_value}",
        f"Database={database}",
        f"Connection Timeout={int(timeout)}",
    ]
    s = server_value.lower()
    encrypt = not (s.startswith("lpc:") or s.startswith("np:") or "(localdb)" in s)
    parts.append("Encrypt=Yes" if encrypt else "Encrypt=No")
    if encrypt:
        parts.append("TrustServerCertificate=Yes")

    if not user or password is None:
        raise ValueError("Cần nhập user và password cho SQL Authentication.")
    parts.append(f"UID={user}")
    parts.append(f"PWD={password}")
    return ";".join(parts) + ";"

# ================ Dò instance LOCAL (Windows) =================
def detect_instances_registry() -> List[str]:
    """Lấy tên instance từ Registry (Windows)."""
    if platform.system() != "Windows":
        return []
    try:
        import winreg
    except Exception:
        return []

    def enum_values(root, path: str) -> List[Tuple[str, str]]:
        out = []
        try:
            k = winreg.OpenKey(root, path)
        except Exception:
            return out
        i = 0
        while True:
            try:
                n, v, _ = winreg.EnumValue(k, i)
                out.append((n, str(v)))
                i += 1
            except OSError:
                break
        winreg.CloseKey(k)
        return out

    ROOT = winreg.HKEY_LOCAL_MACHINE
    paths = [
        r"SOFTWARE\Microsoft\Microsoft SQL Server\Instance Names\SQL",
        r"SOFTWARE\WOW6432Node\Microsoft\Microsoft SQL Server\Instance Names\SQL",
    ]
    names: Dict[str, str] = {}
    for p in paths:
        for nm, _ in enum_values(ROOT, p):
            names[nm] = nm
    instances = sorted(names.keys(), key=lambda x: (x != "MSSQLSERVER", x))
    return instances

def detect_instances_services() -> List[str]:
    """Đọc danh sách dịch vụ MSSQL* để suy ra tên instance."""
    if platform.system() != "Windows":
        return []
    try:
        cp = subprocess.run(["sc", "query", "type=", "service", "state=", "all"], capture_output=True)
        txt = cp.stdout.decode(errors="ignore")
    except Exception:
        return []
    import re
    names = set()
    for m in re.finditer(r"SERVICE_NAME:\s*(\S+)", txt, flags=re.IGNORECASE):
        svc = m.group(1)
        if svc.upper() == "MSSQLSERVER":
            names.add("MSSQLSERVER")
        elif svc.upper().startswith("MSSQL$"):
            names.add(svc.split("$", 1)[1])
    return sorted(names, key=lambda x: (x != "MSSQLSERVER", x))

def detect_local_instances() -> List[str]:
    """Ghép Registry + Services, chỉ trả về TÊN INSTANCE (không port)."""
    if platform.system() != "Windows":
        st.error("Chức năng dò instance local chỉ hỗ trợ Windows.")
        return []
    merged: Dict[str, str] = {}
    for nm in detect_instances_registry():
        merged[nm] = nm
    for nm in detect_instances_services():
        merged.setdefault(nm, nm)
    items = sorted(merged.keys(), key=lambda x: (x != "MSSQLSERVER", x))
    return items

# ================ Kết nối KHÔNG DÙNG PORT ===================
def server_variants_no_port(instance: str) -> List[str]:
    r"""
    Thử theo thứ tự không cần port (chỉ local):
      - lpc:.\  hoặc lpc:.\INSTANCE
      - np:\\.\pipe\sql\query  hoặc np:\\.\pipe\MSSQL$INSTANCE\sql\query
      - .  hoặc .\INSTANCE
      - localhost  hoặc localhost\INSTANCE
    """
    v: List[str] = []
    if instance.upper() == "MSSQLSERVER":
        v += [
            "lpc:.",
            r"np:\\.\pipe\sql\query",
            ".",
            "localhost",
        ]
    else:
        v += [
            f"lpc:.\\{instance}",
            rf"np:\\.\pipe\MSSQL${instance}\sql\query",
            f".\\{instance}",
            f"localhost\\{instance}",
        ]
    return v

def try_open_connection_no_port(instance: str, user: str, pwd: str, timeout: int = 8) -> Tuple[pyodbc.Connection, str]:
    """Thử lần lượt các biến thể KHÔNG PORT cho đến khi kết nối được."""
    driver = pick_sql_odbc_driver()
    last_err = None
    for server_value in server_variants_no_port(instance):
        try:
            conn_str = build_conn_str(driver, server_value, "master", user, pwd, timeout)
            cn = pyodbc.connect(conn_str, timeout=timeout)
            return cn, server_value
        except Exception as e:
            last_err = f"{server_value} -> {e}"
            continue
    raise RuntimeError(last_err or "Không thể kết nối bằng các biến thể không dùng port.")

# ================== DB ops ======================
def list_databases(cnxn: pyodbc.Connection) -> List[str]:
    sql = "SELECT name FROM sys.databases WHERE name NOT IN ('master','tempdb','model','msdb') ORDER BY name;"
    with cnxn.cursor() as cur:
        rows = cur.execute(sql).fetchall()
    return [r[0] for r in rows]

def backup_database(
    cnxn: pyodbc.Connection,
    db: str,
    dest_dir: str,
    file_name: Optional[str] = None,
) -> str:
    db_q = "[" + db.replace("]", "]]") + "]"
    if not file_name:
        ts = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        file_name = f"{db}_{ts}.bak"
    dest_dir = os.path.abspath(dest_dir)
    full_path = os.path.join(dest_dir, file_name)

    with cnxn.cursor() as cur:
        cur.execute(f"BACKUP DATABASE {db_q} TO DISK = ? WITH COPY_ONLY, COMPRESSION, INIT, STATS=10;", (full_path,))
        cur.commit()
    return full_path

# ========================= UI =========================
def render():
    st.title("SQL Server — Local Instance (No Port) Backup")

    # 1) Dò instance local (Windows)
    instances = detect_local_instances()
    if not instances:
        st.error("Không tìm thấy instance nào trên máy. Hãy đảm bảo SQL Server đã cài & đang chạy.")
        st.stop()

    pick = st.selectbox("Chọn instance", instances, index=0)

    # 2) Nhập user + password (SQL Authentication)
    col1, col2 = st.columns(2)
    with col1:
        user = st.text_input("User (VD: sa)")
    with col2:
        pwd = st.text_input("Password", type="password")

    if st.button("🔗 Kết nối & tải danh sách DB", type="primary"):
        try:
            if not user or pwd is None or pwd == "":
                st.error("Vui lòng nhập user & password.")
                st.stop()
            cn, used_server = try_open_connection_no_port(pick, user, pwd, timeout=8)
            with cn:
                dbs = list_databases(cn)
            st.session_state["used_server"] = used_server
            st.session_state["user"] = user
            st.session_state["pwd"] = pwd
            st.session_state["dbs"] = dbs
            st.success(f"Đã kết nối bằng: {used_server} — có {len(dbs)} database.")
        except Exception as e:
            st.error(f"Lỗi kết nối: {e}")

    dbs = st.session_state.get("dbs", [])
    if not dbs:
        st.stop()

    st.divider()
    st.subheader("📀 Backup database")

    db_pick = st.selectbox("Chọn database", dbs, key="db_pick")
    dest_dir = st.text_input("Thư mục đích (trên MÁY SQL)", value="C:\\Backup")
    file_name = st.text_input("Tên file .bak (tùy chọn)", value="")

    if st.button("🚀 Backup ngay"):
        try:
            used_server = st.session_state["used_server"]
            user = st.session_state["user"]
            pwd = st.session_state["pwd"]
            driver = pick_sql_odbc_driver()
            conn_str = build_conn_str(driver, used_server, "master", user, pwd, timeout=12)
            cn = pyodbc.connect(conn_str, timeout=12)
            with cn:
                path = backup_database(cn, db_pick, dest_dir, file_name.strip() or None)
            st.success(f"✅ Backup thành công: {path}")
            # Nếu SQL local và đường dẫn tồn tại trên máy chạy app -> cho tải file
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
