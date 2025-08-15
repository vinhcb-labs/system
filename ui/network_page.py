# ui/network_page.py
from __future__ import annotations
import time
import streamlit as st
from datetime import datetime
from core.network_utils import (
    get_public_ip, get_local_ips, ping_host, traceroute_host,
    check_ssl, dns_lookup, whois_query, port_scan
)

def _ts() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def _host_link(h: str) -> str:
    return f"<a href='http://{h}' target='_blank'>{h}</a>"

def render():
    st.header("🌐 Network")

    tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs(
        ["View IP", "Ping", "Check SSL", "Traceroute", "DNS", "WHOIS", "Port Scan"]
    )

    # ---- View IP ----
    with tab1:
        col1, col2 = st.columns(2)
        with col1:
            st.subheader("Public IP")
            st.code(get_public_ip())
        with col2:
            st.subheader("Local IPs")
            ips = get_local_ips()
            st.code("\n".join(ips) if ips else "Không tìm thấy.")

    # ---- Ping ----
    with tab2:
        with st.form("f_ping"):
            host = st.text_input("Host/IP", placeholder="vd: 8.8.8.8 hoặc example.com")
            ok = st.form_submit_button("Ping")
        if ok and host.strip():
            st.markdown(f"<span style='color:#d00'>{_ts()}</span>  Ping {_host_link(host)}", unsafe_allow_html=True)
            st.caption("Nếu môi trường không có lệnh `ping`, hệ thống sẽ dùng **TCP ping** (thử 443/80/53).")
            st.code(ping_host(host.strip()))

    # ---- Check SSL ----
    with tab3:
        with st.form("f_ssl"):
            host = st.text_input("Host", placeholder="example.com")
            port = st.number_input("Port", min_value=1, max_value=65535, value=443, step=1)
            ok = st.form_submit_button("Check SSL")
        if ok and host.strip():
            st.code(check_ssl(host.strip(), int(port)))

    # ---- Traceroute ----
    with tab4:
        with st.form("f_trace"):
            host = st.text_input("Host/IP", placeholder="vd: 8.8.8.8 hoặc example.com")
            ok = st.form_submit_button("Traceroute")
        if ok and host.strip():
            st.caption("Tự phát hiện `tracert`/`traceroute`/`tracepath`. Nếu môi trường không hỗ trợ sẽ hiển thị thông báo.")
            st.code(traceroute_host(host.strip()))

    # ---- DNS ----
    with tab5:
        with st.form("f_dns"):
            host = st.text_input("Host/Domain", placeholder="example.com")
            ok = st.form_submit_button("Tra DNS")
        if ok and host.strip():
            st.code(dns_lookup(host.strip()))

    # ---- WHOIS ----
    with tab6:
        with st.form("f_whois"):
            domain = st.text_input("Domain", placeholder="example.com")
            ok = st.form_submit_button("WHOIS")
        if ok and domain.strip():
            st.code(whois_query(domain.strip()))

    # ---- Port Scan (để trống = quét tất cả) ----
    with tab7:
        with st.form("f_scan"):
            host = st.text_input("Host/IP", placeholder="vd: 8.8.8.8 hoặc example.com")
            ports_str = st.text_input("Cổng (ví dụ: 22,80,443) — để trống sẽ quét **tất cả** 1–65535", value="")
            ok = st.form_submit_button("Scan")
        if ok and host.strip():
            ports = None
            if ports_str.strip():
                parts = [p.strip() for p in ports_str.split(",") if p.strip()]
                ports = [int(p) for p in parts if p.isdigit() and 1 <= int(p) <= 65535]

            st.info("Đang quét... Để trống sẽ quét **1–65535** (có thể mất thời gian).")
            prog = st.progress(0)
            start = time.perf_counter()

            def cb(total, done):
                prog.progress(int(done * 100 / total))

            result = port_scan(host.strip(), ports=ports, progress_cb=cb)
            prog.progress(100)
            elapsed = time.perf_counter() - start
            st.caption(f"Hoàn tất sau {elapsed:.1f}s")
            st.code(result)
