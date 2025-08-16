# ui/network_page.py
from __future__ import annotations

import streamlit as st
import streamlit.components.v1 as components
from datetime import datetime
from typing import List

from core.network_utils import (
    check_ssl, dns_lookup, whois_query, port_scan
)

# ---------------- Utils ----------------
def _ts() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ---------------- Widgets ----------------
def _client_ips_widget() -> None:
    """Show only Public IP (Auto)."""
    components.html(
        """
<div id="ipbox" style="
     font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, 'Liberation Mono', monospace;
     background:#111827;color:#e5e7eb;padding:12px 14px;border-radius:8px;line-height:1.6">
  <div style="display:flex;gap:10px;align-items:center;justify-content:space-between;">
    <div><b>Public IP (Auto):</b> <span id="ip_auto">Đang lấy...</span></div>
    <button id="copy_auto" style="padding:4px 8px;border:1px solid #374151;border-radius:6px;
            background:#374151;color:#e5e7eb;cursor:pointer;">Copy</button>
  </div>
</div>
<script>
(function(){
  const $ = (sel)=>document.querySelector(sel);
  const setText = (sel, v)=>{ const el = $(sel); if(el) el.textContent = (v ?? "").toString().trim() || "Không có"; };

  async function getJSON(url){
    const r = await fetch(url, {cache:'no-store'});
    return await r.json();
  }
  async function getText(url){
    const r = await fetch(url, {cache:'no-store'});
    return (await r.text()).trim();
  }

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

  function setupCopy(btnSel, valueSel){
    const btn = $(btnSel);
    if(!btn) return;
    btn.addEventListener('click', async ()=>{
      const ip = $(valueSel)?.textContent?.trim();
      if(!ip || ip === "Không có") return;
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

  (async function(){
    try{
      const [v4, v6] = await Promise.all([ resolvePublicV4(), resolvePublicV6() ]);
      const auto = (v6 && v6.trim()) ? v6 : (v4 && v4.trim()) ? v4 : "Không có";
      setText("#ip_auto", auto);
      setupCopy("#copy_auto", "#ip_auto");
    }catch(e){
      setText("#ip_auto", "Lỗi: " + e);
    }
  })();
})();
</script>
        """,
        height=90,
    )


# ---------------- Page ----------------
def render() -> None:
   

    # Tabs: View IP, Check SSL, DNS, WHOIS, Port Scan
    tab1, tab2, tab3, tab4, tab5 = st.tabs(
        ["View IP", "Check SSL", "DNS", "WHOIS", "Port Scan"]
    )

    # ---- View IP ----
    with tab1:
        st.write(f"Thời điểm: {_ts()}")
        _client_ips_widget()

    # ---- Check SSL ----
    with tab2:
        with st.form("f_ssl"):
            host = st.text_input("Host/Domain", placeholder="example.com")
            port = st.number_input("Port", min_value=1, max_value=65535, value=443, step=1)
            ok = st.form_submit_button("Check SSL")
        if ok and host.strip():
            st.code(check_ssl(host.strip(), int(port)))

    # ---- DNS ----
    with tab3:
        with st.form("f_dns"):
            host = st.text_input("Host/Domain", placeholder="example.com")
            ok = st.form_submit_button("Tra DNS")
        if ok and host.strip():
            st.code(dns_lookup(host.strip()))

    # ---- WHOIS ----
    with tab4:
        with st.form("f_whois"):
            domain = st.text_input("Domain", placeholder="example.com")
            ok = st.form_submit_button("Tra WHOIS")
        if ok and domain.strip():
            st.code(whois_query(domain.strip()))

    # ---- Port Scan ----
    with tab5:
        def _parse_ports(s: str) -> List[int]:
            """Parse '22,80,443' and ranges like '1-1024' into a list of ints."""
            s = (s or "").strip()
            if not s:
                return []
            out: List[int] = []
            for part in s.split(","):
                part = part.strip()
                if not part:
                    continue
                if "-" in part:
                    a, b = part.split("-", 1)
                    try:
                        a, b = int(a), int(b)
                        if a > b:
                            a, b = b, a
                        out.extend(range(a, b + 1))
                    except:
                        pass
                else:
                    try:
                        out.append(int(part))
                    except:
                        pass
            # unique & valid
            out = sorted({p for p in out if 1 <= p <= 65535})
            return out

        with st.form("f_scan"):
            host = st.text_input("Host/IP", placeholder="example.com hoặc 8.8.8.8")
            ports_str = st.text_input("Ports (ví dụ: 22,80,443 hoặc 1-1024)", value="80,443,22")
            ok = st.form_submit_button("Quét cổng")
        if ok and host.strip():
            ports = _parse_ports(ports_str)
            if not ports:
                st.warning("Vui lòng nhập danh sách cổng hợp lệ.")
            else:
                pbar = st.progress(0)
                total_cache = {"total": 1}  # will be updated by callback

                def _cb(total: int, done: int) -> None:
                    total_cache["total"] = max(total, 1)
                    p = int(done * 100 / total_cache["total"])
                    pbar.progress(min(max(p, 0), 100))

                result = port_scan(host.strip(), ports=ports, progress_cb=_cb)
                pbar.progress(100)
                st.code(result)


# Keep a callable for other modules
main = render

if __name__ == "__main__":
    render()
