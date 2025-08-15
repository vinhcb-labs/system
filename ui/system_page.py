import pandas as pd
import streamlit as st
from core.system_utils import get_system_info

def render():
    st.subheader("🖥️ System")
    
    if st.button("Lấy thông tin hệ thống"):
        data = get_system_info()
        df = pd.DataFrame([data]).T
        df.columns = ["Giá trị"]
        st.dataframe(df, use_container_width=True)

    st.subheader("📦 Công cụ")

    # Danh sách ứng dụng và link tải
    apps = [
        {"name": "Unikey", "url": "https://example.com/Unikey.zip"},
        {"name": "Vietkey2000", "url": "https://example.com/Vietkey2000.zip"},
        {"name": "WinRAR", "url": "https://example.com/WinRAR.zip"},
        {"name": "XMind", "url": "https://example.com/XMind.zip"},
        {"name": "Activate_OW", "url": "https://example.com/Activate_OW.zip"},
        {"name": "GoogleDriveSetup", "url": "https://dl.google.com/drive-file-stream/GoogleDriveSetup.exe"},
        {"name": "DropboxSetup", "url": "https://example.com/DropboxSetup.exe"},
    ]

    # HTML bảng 2 cột
    table_html = """
    <table style="border-collapse: collapse; width: 100%;" border="1">
        <tr>
            <th style="padding: 6px; text-align: left;">Tên công cụ</th>
            <th style="padding: 6px; text-align: center;"></th>
        </tr>
    """

    for i, app in enumerate(apps, start=1):
        table_html += "<tr>"
        # Cột 1: STT + tên công cụ
        table_html += f"<td style='padding: 6px;'>{i}. {app['name']}</td>"
        # Cột 2: nút tải
        table_html += f"""
            <td style='padding: 6px; text-align: center;'>
                <a href="{app['url']}" target="_blank">
                    <button style="
                        background-color: #4CAF50;
                        color: white;
                        border: none;
                        border-radius: 4px;
                        padding: 4px 10px;
                        cursor: pointer;
                        font-size: 13px;
                    ">Tải về</button>
                </a>
            </td>
        """
        table_html += "</tr>"

    table_html += "</table>"

    # Hiển thị bảng
    st.markdown(table_html, unsafe_allow_html=True)
