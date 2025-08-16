# ui/soft_page.py
from __future__ import annotations

import streamlit as st
from typing import Dict, Callable, List

# ---------------- Page ----------------
def render() -> None:
    #st.title("Software Tools")
    #st.caption("Tổng hợp công cụ/phần mềm theo nền tảng.")

    sections: Dict[str, Callable[[], None]] = {
        "Windows": _win_tab,
        "Android": _android_tab,
    }

    tabs = st.tabs(list(sections.keys()))
    for (name, fn), tab in zip(sections.items(), tabs):
        with tab:
            fn()

# ---------------- Tabs ----------------
def _win_tab() -> None:
    st.subheader("Windows")

    # Danh sách ứng dụng và link tải (theo yêu cầu)
    apps: List[dict] = [
        {"name": "Activate_OW", "url": "https://www.dropbox.com/scl/fi/buicqfdwim1gg3r9wj1gn/Activate_OW.zip?rlkey=m9wmtbdit28atsej7o56zpmt7&st=dq1hrgsa&dl=1"},
        {"name": "Dropbox", "url": "https://www.dropbox.com/download?plat=win"},
        {"name": "GoogleDrive", "url": "https://dl.google.com/drive-file-stream/GoogleDriveSetup.exe"},
        {"name": "Unikey", "url": "https://www.dropbox.com/scl/fi/kqx1it8b72sfek1oyn6nq/UniKey.zip?rlkey=791rk5ngikf9kqub21tbfedzr&st=fxs9clvr&dl=1"},
        {"name": "Vietkey2000", "url": "https://www.dropbox.com/scl/fi/x03tgdg7gfq59dtpryk9c/Vietkey2000.zip?rlkey=jr90ue89tnxf276nfwp391rmk&st=6qvhmt4s&dl=1"},
        {"name": "WinRAR", "url": "https://www.dropbox.com/scl/fi/xu3thzg1kru6blo3pky6d/WinRAR.zip?rlkey=tgmviojwg5q29aodp7qxywrv7&st=8zx1fpq6&dl=1"},
        {"name": "XMind", "url": "https://www.dropbox.com/scl/fi/bf4bm8hcghts1nc8cpu7q/XMind.zip?rlkey=bozsq9lgzwhbc5tu589y05qj9&st=9hj4x86c&dl=1"},
        {"name": "Teams", "url": "https://statics.teams.cdn.office.net/evergreen-assets/DesktopClient/MSTeamsSetup.exe"},
        {"name": "UltraViewer_version_6.6", "url": "https://www.ultraviewer.net/vi/UltraViewer_setup_6.6_vi.exe"},
    ]

    # Tìm kiếm nhanh
    q = st.text_input("Tìm ứng dụng", placeholder="Nhập tên ứng dụng (ví dụ: Unikey, WinRAR, ...)").strip().lower()
    filtered = [a for a in apps if q in a["name"].lower()] if q else apps

    # Sắp xếp theo tên để tự động gọn gàng khi thêm app mới
    filtered = sorted(filtered, key=lambda a: a["name"].lower())

    # 3 cột tự động sắp xếp, dùng thuần Streamlit
    cols = st.columns(3)
    if not filtered:
        st.info("Không tìm thấy ứng dụng phù hợp.")
    else:
        for i, app in enumerate(filtered):
            with cols[i % 3]:
                st.write(f"**{app['name']}**")
                st.link_button("DOWNLOAD", app["url"])

    with st.expander("Ghi chú nhanh"):
        st.text_area("Notes", value="", height=150, placeholder="Nhập ghi chú cài đặt, license, tips...")


def _android_tab() -> None:
    st.subheader("Android")

    # Danh sách ứng dụng Android và link tải (cấu trúc giống Windows; điền dữ liệu của bạn vào đây)
    apps: List[dict] = [
        {"name": "Zalo", "url": "https://zalo.dl.sourceforge.net/project/zalo-apk/latest.apk"}
    ]

    # Tìm kiếm nhanh
    q = st.text_input("Tìm ứng dụng Android", placeholder="Nhập tên ứng dụng (ví dụ: VLC, Zalo, ...)").strip().lower()
    filtered = [a for a in apps if q in a["name"].lower()] if q else apps

    # Sắp xếp theo tên
    filtered = sorted(filtered, key=lambda a: a["name"].lower())

    # 3 cột tự động sắp xếp, dùng thuần Streamlit
    cols = st.columns(3)
    if not filtered:
        st.info("Chưa có ứng dụng Android. Hãy thêm vào danh sách 'apps'.")
    else:
        for i, app in enumerate(filtered):
            with cols[i % 3]:
                st.write(f"**{app['name']}**")
                st.link_button("DOWNLOAD", app["url"])

    with st.expander("Ghi chú nhanh"):
        st.text_area("Notes", value="", height=150, placeholder="Nhập ghi chú cài đặt, ADB tips, cấu hình...")

# Giữ alias cho hệ thống import hiện tại
main = render

if __name__ == "__main__":
    render()
