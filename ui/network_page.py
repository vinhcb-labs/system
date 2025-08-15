# ui/network_page.py
from __future__ import annotations
import time
import streamlit as st
import streamlit.components.v1 as components
from datetime import datetime
from core.network_utils import (
    ping_host, traceroute_host,
    check_ssl, dns_lookup, whois_query, port_scan
)

def _ts() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def _host_link(h: str) -> str:
    return f"<a href='http://{h}' target='_blank'>{h}</a>"

def _client_ips_widget():
    """
    Hiển thị:
    - Public IP (Auto): ưu tiên IPv6, fallback IPv4 (IP ra mạng của thiết bị).
    - IPv4 (Local - Client): IP nội bộ của thiết bị (thử lấy qua WebRTC; có thể bị trình duyệt chặn).
    - Public IPv6 (Client): nếu không có thì ẩn dòng.
    Tất cả có nút Copy.
    """
    components.html(
        """
        <div id="ipbox" style="
             font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, 'Liberation Mono', monospace;
             background:#111827;color:#e5e7eb;padding:12px 14px;border-radius:8px;line-height:1.6">
          <!-- Public Auto -->
          <div style="display:flex;gap:10px;align-items:center;justify-content:space-between;">
            <div><b>Public IP (Auto):</b> <span id="ip_auto">Đang lấy...</span></div>
            <button id="copy_auto" style="padding:4px 8px;border:1px solid #374151;border-radius:6px;
                    background:#374151;color:#e5e7eb;cursor:pointer;">Copy</button>
          </div>
          <!-- IPv4 Local -->
          <div style="display:flex;gap:10px;align-items:center;justify-content:space-between;margin-top:6px;">
            <div><b>IPv4 (Local - Client):</b> <span id="ip_local_v4">Đang lấy...</span></div>
            <button id="copy_local_v4" style="padding:4px 8px;border:1px solid #374151;border-radius:6px;
                    background:#374151;color:#e5e7eb;cursor:pointer;">Copy</button>
          </div>
          <!-- Public IPv6 -->
          <div id="row6" style="display:flex;gap:10px;align-items:center;justify-content:space-between;margin-top:6px;">
            <div><b>Public IPv6 (Client):</b> <span id="ipv6">Đang lấy...</span></div>
            <button id="copy6" style="padding:4px 8px;border:1px solid #374151;border-radius:6px;
                    background:#374151;color:#e5e7eb;cursor:pointer;">Copy</button>
          </div>
        </div>
        <script>
        (async function(){
          const $ = (sel)=>document.querySelector(sel);
          const setText = (sel, v)=>{ const el = $(sel); if(el) el.textContent = (v ?? "").toString().trim() || "Không có"; };
          const isPrivateV4 = (ip)=>{
            // RFC1918 & CGNAT
            return /^10\\./.test(ip) || /^192\\.168\\./.test(ip) ||
                   /^(172\\.(1[6-9]|2\\d|3[0-1])\\.)/.test(ip) ||
                   /^100\\.(6[4-9]|[7-9]\\d|1\\d\\d|2([0-1]\\d|2[0-7]))\\./.test(ip);
          };

          async function getJSON(url){ const r = await fetch(url, {cache:'no-store'}); return await r.json(); }
          async function getText(url){ const r = await fetch(url, {cache:'no-store'}); return (await r.text()).trim(); }

          async function resolvePublicV4(){
            try{ const j = await getJSON('https://api4.ipify.org?format=json'); if(j && j.ip) return j.ip; }catch(e){}
            try{ const t = await getText('https://ipv4.icanhazip.com'); if(t) return t; }catch(e){}
            return "";
          }
          async function resolvePublicV6(){
            try{ const j = await getJSON('https://api6.ipify.org?format=json'); if(j && j.ip) return j.ip; }catch(e){}
            try{ const t = await getText('https://ipv6.icanhazip.com'); if(t) return t; }catch(e){}
            return "";
          }

          async function resolveLocalV4(){
            // Thử lấy IPv4 nội bộ qua WebRTC; nhiều trình duyệt hiện đại có thể chặn (mDNS).
            try{
              const pc = new RTCPeerConnection({iceServers:[{urls:'stun:stun.l.google.com:19302'}]});
              pc.createDataChannel('x');  // cần channel để sinh ICE
              const cands = new Set();
              pc.onicecandidate = (e)=>{
                if(!e.candidate) return;
                const cand = e.candidate.candidate || "";
                // cand ví dụ: "candidate:... typ host ... 192.168.1.5 ..."
                const m = cand.match(/(?:\\s|:)(\\d+\\.\\d+\\.\\d+\\.\\d+)(?:\\s|:)/);
                if(m && m[1] && isPrivateV4(m[1])) cands.add(m[1]);
              };
              const sdp = await pc.createOffer();
              await pc.setLocalDescription(sdp);
              // chờ ICE trong thời gian ngắn
              await new Promise(r=>setTimeout(r, 800));
              pc.close();
              // trả về 1 IP private nếu có
              const arr = Array.from(cands);
              return arr.length ? arr[0] : "";
            }catch(e){
              return "";
            }
          }

          function setupCopy(btnSel, valueSel){
            const btn = $(btnSel);
            btn?.addEventListener('click', async ()=>{
              const ip = $(valueSel)?.textContent?.trim();
              if(!ip || ip === "Không có"){ return; }
              try{
                await navigator.clipboard.writeText(ip);
                const old = btn.textContent; btn.textContent = "Đã copy";
                setTimeout(()=>btn.textContent = old, 1200);
              }catch(e){
                const old = btn.textContent; btn.textContent = "Lỗi copy";
                setTimeout(()=>btn.textContent = old, 1200);
              }
            });
          }

          try{
            // Lấy public v4/v6 song song và local v4
            const [pub4, pub6, local4] = await Promise.all([
              resolvePublicV4(), resolvePublicV6(), resolveLocalV4()
            ]);

            // Public IP (Auto): ưu tiên IPv6, nếu rỗng dùng IPv4
            const auto = (pub6 && pub6.trim()) ? pub6 : (pub4 && pub4.trim()) ? pub4 : "Không có";
            setText("#ip_auto", auto);

            // IPv4 Local (Client): nếu không lấy được, báo không thể lấy (do bảo mật)
            if(local4 && local4.trim()){
              setText("#ip_local_v4", local4);
            }else{
              setText("#ip_local_v4", "Không thể lấy (bị chặn bởi bảo mật trình duyệt)");
            }

            // Public IPv6: nếu không có -> ẩn dòng
            if(pub6 && pub6.trim()){
              setText("#ipv6", pub6);
            }else{
              const row6 = document.getElementById("row6");
              if(row6) row6.style.display = "none";
            }

            // Nút copy
            setupCopy("#copy_auto", "#ip_auto");
            setupCopy("#copy_local_v4", "#ip_local_v4");
            setupCopy("#copy6", "#ipv6");
          }catch(e){
            setText("#ip_auto", "Lỗi: " + e);
            setText("#ip_local_v4", "Không thể lấy (bị chặn bởi bảo mật trình duyệt)");
            const row6 = document.getElementById("row6");
            if(row6) row6.style.display = "none";
          }
        })();
        </script>
        """,
        height=170,
    )

def render():
    st.header("🌐 Network")

    tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs(
        ["View IP", "Ping", "Check SSL", "Traceroute", "DNS", "WHOIS", "Port Scan"]
    )

    # ---- View IP (Client) ----
    with tab1:
        st.subheader("IP (Client)")
        _client_ips_widget()
        st.caption("Public IP (Auto) ưu tiên IPv6 nếu có, nếu không sẽ dùng IPv4. IPv4 Local có thể không lấy được do bảo mật WebRTC của trình duyệt.")

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

    # ---- Port Scan (để trống = quét tất cả 1–65535) ----
    with tab7:
        with st.form("f_scan"):
            host = st.text_input("Host/IP", placeholder="vd: 8.8.8.8 hoặc example.com")
            ports_str = st.text_input("Cổng (ví dụ: 22,80,443) — để trống sẽ quét **1–65535**", value="")
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
