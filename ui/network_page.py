import html
import pandas as pd
import streamlit as st
from datetime import datetime

from core.network_utils import (
    get_public_ip, get_ip_local, get_dns_servers, ping_host,
    dns_lookup, whois_lookup_verbose, check_ssl_expiry,
    scan_open_ports, traceroute_host
)

# Map cổng -> dịch vụ (suy diễn từ network_utils.getservbyport nếu bạn muốn)
from socket import getservbyport

COMMON_MAP = {
    "53":"DNS","80":"HTTP","443":"HTTPS","3389":"RDP","3306":"MySQL","5432":"PostgreSQL",
    "6379":"Redis","8080":"HTTP Proxy","22":"SSH","25":"SMTP","110":"POP3","143":"IMAP",
    "389":"LDAP","445":"SMB","853":"DNS over TLS","8000":"HTTP-alt","8081":"HTTP-alt"
}

def _service_for(p: str) -> str:
    if p in COMMON_MAP: return COMMON_MAP[p]
    try:  return getservbyport(int(p), "tcp").upper()
    except: pass
    try:  return getservbyport(int(p), "udp").upper()
    except: return "Unknown"

def _ts():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def _host_link(host: str) -> str:
    url = host if host.lower().startswith(("http://","https://")) else f"http://{host}"
    return f"[**{html.escape(host)}**]({html.escape(url)})"

def render():
    st.subheader("🌐 Network")

    tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
        "View IP", "Ping", "Check SSL", "Traceroute", "DNS", "WHOIS", "Port Scan"
    ])

    with tab1:
        if st.button("Xem IP"):
            st.markdown(f"<span style='color:#d00'>{_ts()}</span>", unsafe_allow_html=True)
            st.code(f"[IP PUBLIC]: {get_public_ip()}\n[IP LOCAL]: {get_ip_local()}\n[DNS]: {get_dns_servers()}")

    with tab2:
        with st.form("f_ping"):
            host = st.text_input("Host/IP", placeholder="vd: 8.8.8.8 hoặc example.com")
            ok = st.form_submit_button("Ping")
        if ok:
            st.markdown(f"<span style='color:#d00'>{_ts()}</span>  Ping {_host_link(host)}", unsafe_allow_html=True)
            st.code(ping_host(host.strip()))

    with tab3:
        with st.form("f_ssl"):
            domain = st.text_input("Domain", placeholder="vd: google.com")
            ok = st.form_submit_button("Kiểm tra")
        if ok:
            st.markdown(f"<span style='color:#d00'>{_ts()}</span>  SSL {_host_link(domain)}", unsafe_allow_html=True)
            st.code(check_ssl_expiry(domain.strip()))

    with tab4:
        with st.form("f_tr"):
            host = st.text_input("Host/IP", placeholder="vd: 1.1.1.1 hoặc cloudflare.com")
            ok = st.form_submit_button("Traceroute")
        if ok:
            st.markdown(f"<span style='color:#d00'>{_ts()}</span>  Traceroute {_host_link(host)}", unsafe_allow_html=True)
            st.code(traceroute_host(host.strip()))

    with tab5:
        with st.form("f_dns"):
            host = st.text_input("Host/Domain", placeholder="vd: example.com")
            ok = st.form_submit_button("Lookup")
        if ok:
            st.markdown(f"<span style='color:#d00'>{_ts()}</span>  DNS {_host_link(host)}", unsafe_allow_html=True)
            st.code(dns_lookup(host.strip()))

    with tab6:
        with st.form("f_whois"):
            domain = st.text_input("Domain", placeholder="vd: example.com")
            ok = st.form_submit_button("WHOIS")
        if ok:
            st.markdown(f"<span style='color:#d00'>{_ts()}</span>  WHOIS {_host_link(domain)}", unsafe_allow_html=True)
            st.code(whois_lookup_verbose(domain.strip()))

    with tab7:
        with st.form("f_ps"):
            host = st.text_input("Host/IP", placeholder="vd: 113.161.95.110 hoặc example.com")
            ok = st.form_submit_button("Scan")
        if ok:
            st.markdown(f"<div style='color:#d00'>{_ts()}</div> {_host_link(host)}:", unsafe_allow_html=True)
            raw = scan_open_ports(host.strip())
            lines = [s.strip() for s in str(raw).splitlines() if s.strip()]
            ports = [l.replace("Cổng mở: ", "") for l in lines]

            if not ports:
                st.info("Không có cổng mở.")
            else:
                df = pd.DataFrame(
                    [{"Port": p, "Service": _service_for(p)} for p in ports],
                    columns=["Port", "Service"]
                )
                st.dataframe(df, use_container_width=True, hide_index=True)
                st.caption("Service được suy diễn từ map phổ biến + getservbyport(tcp/udp).")
