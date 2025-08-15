# core/backup_utils.py
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

def zip_folder(src_dir: str, zip_path: str) -> str:
    """Nén toàn bộ thư mục src_dir vào file zip_path. Trả về đường dẫn file zip."""
    src = Path(src_dir).resolve()
    out = Path(zip_path).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)

    if not src.exists() or not src.is_dir():
        raise FileNotFoundError(f"Source folder not found: {src}")

    with ZipFile(out, "w", ZIP_DEFLATED) as zf:
        for p in src.rglob("*"):
            zf.write(p, p.relative_to(src))
    return str(out)
