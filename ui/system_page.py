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
        {"name": "Unikey", "url": "https://www.dropbox.com/scl/fi/kqx1it8b72sfek1oyn6nq/UniKey.zip?rlkey=791rk5ngikf9kqub21tbfedzr&st=fxs9clvr&dl=1"},
        {"name": "Vietkey2000", "url": "https://www.dropbox.com/scl/fi/x03tgdg7gfq59dtpryk9c/Vietkey2000.zip?rlkey=jr90ue89tnxf276nfwp391rmk&st=6qvhmt4s&dl=1"},
        {"name": "WinRAR", "url": "https://www.dropbox.com/scl/fi/xu3thzg1kru6blo3pky6d/WinRAR.zip?rlkey=tgmviojwg5q29aodp7qxywrv7&st=8zx1fpq6&dl=1"},
        {"name": "XMind", "url": "https://www.dropbox.com/scl/fi/bf4bm8hcghts1nc8cpu7q/XMind.zip?rlkey=bozsq9lgzwhbc5tu589y05qj9&st=9hj4x86c&dl=1"},
        {"name": "Activate_OW", "url": "https://www.dropbox.com/scl/fi/buicqfdwim1gg3r9wj1gn/Activate_OW.zip?rlkey=m9wmtbdit28atsej7o56zpmt7&st=dq1hrgsa&dl=1"},
        {"name": "GoogleDriveSetup", "url": "https://dl.google.com/drive-file-stream/GoogleDriveSetup.exe"},
        {"name": "DropboxSetup", "url": "https://www.dropbox.com/download?plat=win"},
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
