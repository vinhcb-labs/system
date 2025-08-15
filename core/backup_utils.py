# core/backup_utils.py
from __future__ import annotations
import os
import fnmatch
import hashlib
from pathlib import Path
from datetime import datetime
from typing import Callable, Iterable, List, Optional

# =========================
# Helpers chung
# =========================
def is_windows() -> bool:
    return os.name == "nt"

def ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)

def sha256_of(file_path: Path, chunk: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with file_path.open("rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()

def _normalize_dir(p: str | os.PathLike) -> Path:
    pp = Path(p).expanduser()
    if not pp.exists() or not pp.is_dir():
        raise ValueError(f"Thư mục không hợp lệ: {p}")
    # Không resolve() cưỡng bách (tránh sửa drive letter khi chạy khác OS)
    return pp

def _should_exclude(rel: str, patterns: Iterable[str]) -> bool:
    for pat in patterns:
        pat = (pat or "").strip()
        if not pat:
            continue
        # cho phép pattern kiểu ".git/*" hay "*.log"
        if fnmatch.fnmatch(rel, pat) or fnmatch.fnmatch("/" + rel, pat):
            return True
    return False


# =========================
# ZIP thư mục (có/không mật khẩu)
# =========================
try:
    import pyzipper  # AES encryption (tuỳ chọn)
    _HAS_PYZIPPER = True
except Exception:
    _HAS_PYZIPPER = False
    pyzipper = None  # type: ignore

def zip_folder(
    src_dir: str | os.PathLike,
    dst_dir: str | os.PathLike,
    zip_name: Optional[str] = None,
    password: Optional[str] = None,
    compression_level: int = 6,
    exclude_globs: Optional[List[str]] = None,
    progress_cb: Optional[Callable[[int, int], None]] = None,
) -> Path:
    """
    Nén một thư mục thành .zip.
    - password: nếu có & pyzipper sẵn → AES-256; nếu không → zip thường.
    - exclude_globs: list pattern loại trừ (vd: ["*.tmp",".git/*","node_modules/*"])
    - progress_cb(done, total): cập nhật tiến độ (cho UI)
    """
    src = _normalize_dir(src_dir)
    dst = Path(dst_dir).expanduser()
    ensure_dir(dst)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    if not zip_name:
        zip_name = f"{src.name}_{stamp}.zip"
    if not zip_name.lower().endswith(".zip"):
        zip_name += ".zip"
    out_path = dst / zip_name

    patterns = exclude_globs or []

    # liệt kê file
    files: List[Path] = []
    for p in src.rglob("*"):
        if p.is_file():
            rel = p.relative_to(src).as_posix()
            if _should_exclude(rel, patterns):
                continue
            files.append(p)

    total = len(files)
    if progress_cb:
        progress_cb(0, total)

    if password and _HAS_PYZIPPER:
        with pyzipper.AESZipFile(out_path, "w", compression=pyzipper.ZIP_DEFLATED, compresslevel=compression_level) as zf:
            zf.setencryption(pyzipper.WZ_AES, nbits=256)
            zf.setpassword(password.encode("utf-8"))
            for i, f in enumerate(files, 1):
                zf.write(f, arcname=f.relative_to(src).as_posix())
                if progress_cb:
                    progress_cb(i, total)
    else:
        import zipfile
        with zipfile.ZipFile(out_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=compression_level) as zf:
            for i, f in enumerate(files, 1):
                zf.write(f, arcname=f.relative_to(src).as_posix())
                if progress_cb:
                    progress_cb(i, total)

    return out_path


# =========================
# SQL Server (pyodbc)
# =========================
try:
    import pyodbc  # cần ODBC Driver 17/18
    _HAS_PYODBC = True
except Exception:
    _HAS_PYODBC = False
    pyodbc = None  # type: ignore

def mssql_connect(
    driver: str,
    server: str,
    auth: str,             # "Windows" | "SQL"
    username: str = "",
    password: str = "",
    *, encrypt: bool = True,
    trust_cert: bool = True,
    timeout: int = 10,
):
    """
    Kết nối SQL Server bằng pyodbc. Trả về connection autocommit=True.
    """
    if not _HAS_PYODBC:
        raise RuntimeError("pyodbc chưa được cài hoặc ODBC Driver thiếu.")

    parts = [f"DRIVER={{{driver}}}", f"SERVER={server}"]
    if auth == "Windows":
        parts.append("Trusted_Connection=yes")
    else:
        parts.append(f"UID={username}")
        parts.append(f"PWD={password}")
    if encrypt:
        parts.append("Encrypt=yes")
    if trust_cert:
        parts.append("TrustServerCertificate=yes")
    cn = ";".join(parts)
    return pyodbc.connect(cn, autocommit=True, timeout=timeout)

def mssql_list_databases(cnxn) -> List[str]:
    q = """
    SELECT name
    FROM sys.databases
    WHERE state = 0 AND name NOT IN ('master','tempdb','model','msdb')
    ORDER BY name;
    """
    cur = cnxn.cursor()
    rows = cur.execute(q).fetchall()
    return [r[0] for r in rows]

def mssql_default_backup_dir(cnxn) -> Optional[str]:
    # SERVERPROPERTY trước
    cur = cnxn.cursor()
    try:
        row = cur.execute("SELECT CAST(SERVERPROPERTY('InstanceDefaultBackupPath') AS nvarchar(4000))").fetchone()
        if row and row[0]:
            return row[0]
    except Exception:
        pass
    # Registry qua xp_instance_regread (có thể không có quyền)
    try:
        cur.execute("""
        DECLARE @dir nvarchar(4000);
        EXEC master.dbo.xp_instance_regread
            N'HKEY_LOCAL_MACHINE',
            N'SOFTWARE\\Microsoft\\MSSQLServer\\MSSQLServer',
            N'BackupDirectory',
            @dir OUTPUT, 'no_output';
        SELECT @dir;
        """)
        row = cur.fetchone()
        if row and row[0]:
            return row[0]
    except Exception:
        pass
    return None

def mssql_engine_edition(cnxn) -> int:
    """
    1=Personal, 2=Standard, 3=Enterprise, 4=Express, 5=SQL Azure...
    """
    cur = cnxn.cursor()
    row = cur.execute("SELECT CAST(SERVERPROPERTY('EngineEdition') AS int)").fetchone()
    return int(row[0]) if row else 0

def mssql_backup_database(
    cnxn,
    db_name: str,
    out_dir: Optional[str] = None,
    file_name: Optional[str] = None,
    *,
    copy_only: bool = True,
    compression: bool = False,
    verify: bool = False,
) -> Path:
    """
    Thực hiện BACKUP DATABASE sang .bak trên **máy chạy SQL Server**.
    - out_dir rỗng → dùng default backup dir của server.
    - compression sẽ tự tắt nếu phát hiện Express.
    - Trả về Path (chuỗi đường dẫn theo máy server – nếu server remote thì path là của server).
    """
    if not db_name:
        raise ValueError("Thiếu tên database.")

    if not out_dir:
        out_dir = mssql_default_backup_dir(cnxn)
        if not out_dir:
            raise RuntimeError("Không lấy được default backup directory của server, hãy nhập out_dir.")

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    if not file_name:
        file_name = f"{db_name}_{ts}.bak"
    if not file_name.lower().endswith(".bak"):
        file_name += ".bak"

    full = str(Path(out_dir) / file_name)
    full_tsql = full.replace("'", "''")

    # Bỏ COMPRESSION trên Express
    if mssql_engine_edition(cnxn) == 4:
        compression = False

    opts = ["INIT", "SKIP", "STATS=10"]
    if copy_only:
        opts.append("COPY_ONLY")
    if compression:
        opts.append("COMPRESSION")

    safe_db = db_name.replace("]", "]]")
    tsql = f"BACKUP DATABASE [{safe_db}] TO DISK = N'{full_tsql}' WITH {', '.join(opts)};"
    cur = cnxn.cursor()
    cur.execute(tsql)

    if verify:
        cur.execute(f"RESTORE VERIFYONLY FROM DISK = N'{full_tsql}';")

    return Path(full)
