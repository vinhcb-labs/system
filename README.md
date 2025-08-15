# vlabstools_streamlit

Ứng dụng Streamlit nhiều trang:
- **1) Backup thư mục ➜ ZIP**
- **2) Backup Driver thiết bị (Windows)**
- **System / Network / About**

## Chạy local
```bash
python -m venv .venv
. .venv/Scripts/activate   # Windows
pip install -r requirements.txt
streamlit run app.py
```

## Cấu trúc
```
app.py
requirements.txt
ui/
  mainwindow_page.py
  network_page.py
  system_page.py
  backup_page.py
  about_page.py
core/
  system_utils.py
  network_utils.py
  backup_utils.py
assets/
  logo.png (tuỳ chọn)
```
