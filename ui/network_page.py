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
            try{
              const pc = new RTCPeerConnection({iceServers:[{urls:'stun:stun.l.google.com:19302'}]});
              pc.createDataChannel('x');
              const cands = new Set();
              pc.onicecandidate = (e)=>{
                if(!e.candidate) return;
                const cand = e.candidate.candidate || "";
                const m = cand.match(/(?:\\s|:)(\\d+\\.\\d+\\.\\d+\\.\\d+)(?:\\s|:)/);
                if(m && m[1] && isPrivateV4(m[1])) cands.add(m[1]);
              };
              const sdp = await pc.createOffer();
              await pc.setLocalDescription(sdp);
              await new Promise(r=>setTimeout(r, 800));
              pc.close();
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
            const [pub4, pub6, local4] = await Promise.all([
              resolvePublicV4(), resolvePublicV6(), resolveLocalV4()
            ]);

            const auto = (pub6 && pub6.trim()) ? pub6 : (pub4 && pub4.trim()) ? pub4 : "Không có";
            setText("#ip_auto", auto);

            if(local4 && local4.trim()){
              setText("#ip_local_v4", local4);
            }else{
              setText("#ip_local_v4", "Không thể lấy (bị chặn bởi bảo mật trình duyệt)");
            }

            if(pub6 && pub6.trim()){
              setText("#ipv6", pub6);
            }else{
              const row6 = document.getElementById("row6");
              if(row6) row6.style.display = "none";
            }

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

def _client_network_tools_widget():
    # Bộ công cụ kiểm tra mạng chạy 100% trên trình duyệt (client-side)
    components.html(
        """
<style>
* { box-sizing: border-box; }
.toolbox { background:#0b1220;color:#e5e7eb;border-radius:12px;padding:14px; font: 13px ui-monospace, SFMono-Regular, Menlo, Consolas, "Liberation Mono", monospace; }
.row { display:flex; gap:10px; align-items:center; margin:6px 0; flex-wrap:wrap; }
input,select,button { padding:6px 8px; border:1px solid #334155; border-radius:8px; background:#111827; color:#e5e7eb; }
button { cursor:pointer; }
pre { background:#0f172a; padding:10px; border-radius:10px; overflow:auto; max-height:240px;}
.badge { padding:2px 6px; border-radius:999px; border:1px solid #334155; }
.small { opacity:0.7; }
</style>

<div class="toolbox">
  <div class="row">
    <div class="badge">CLIENT MODE</div>
    <div class="small">Chạy hoàn toàn trên trình duyệt của bạn</div>
  </div>

  <h4>🔎 DNS (DoH – Cloudflare)</h4>
  <div class="row">
    <input id="d_host" placeholder="vd: example.com" style="min-width:260px">
    <select id="d_type">
      <option>A</option><option>AAAA</option><option>MX</option><option>NS</option><option>TXT</option><option>CNAME</option>
    </select>
    <button id="d_btn">Tra DNS</button>
  </div>
  <pre id="d_out">Kết quả sẽ hiển thị ở đây…</pre>

  <h4>🌍 HTTP(S) Reachability / Pseudo-TCP</h4>
  <div class="row">
    <input id="h_host" placeholder="vd: example.com hoặc 8.8.8.8" style="min-width:260px">
    <input id="h_port" type="number" min="1" max="65535" value="443" style="width:100px">
    <select id="h_scheme"><option>https</option><option>http</option></select>
    <button id="h_btn">Kiểm tra</button>
  </div>
  <div class="small">* Dùng mẹo &lt;img&gt; để thử thiết lập kết nối đến <code>scheme://host:port/</code>. Chỉ phát hiện được dịch vụ HTTP/HTTPS, không xác nhận TCP thuần.</div>
  <pre id="h_out">Kết quả sẽ hiển thị ở đây…</pre>

  <h4>⏱️ WebRTC Latency (STUN)</h4>
  <div class="row">
    <select id="w_stun">
      <option>stun:stun.l.google.com:19302</option>
      <option>stun:global.stun.twilio.com:3478</option>
      <option>stun:stun.cloudflare.com:3478</option>
    </select>
    <button id="w_btn">Đo độ trễ</button>
  </div>
  <pre id="w_out">Kết quả sẽ hiển thị ở đây…</pre>
</div>

<script>
const $ = (s)=>document.querySelector(s);
const out = (el, msg)=>{ el.textContent = msg; };

// --- DNS over HTTPS (Cloudflare JSON) ---
async function dohQuery(name, type){
  const url = `https://cloudflare-dns.com/dns-query?name=${encodeURIComponent(name)}&type=${encodeURIComponent(type)}`;
  const res = await fetch(url, { headers: { "Accept":"application/dns-json" }, cache:"no-store" });
  if(!res.ok) throw new Error("HTTP " + res.status);
  return await res.json();
}

$("#d_btn")?.addEventListener("click", async ()=>{
  const host = $("#d_host").value.trim();
  const type = $("#d_type").value.trim() || "A";
  const o = $("#d_out");
  if(!host){ out(o, "Nhập domain trước."); return; }
  out(o, "Đang tra DoH...");
  try{
    const j = await dohQuery(host, type);
    out(o, JSON.stringify(j, null, 2));
  }catch(e){
    out(o, "Lỗi DoH: " + e);
  }
});

// --- HTTP(S) reachability via <img> trick ---
$("#h_btn")?.addEventListener("click", async ()=>{
  const host = $("#h_host").value.trim();
  const port = parseInt($("#h_port").value, 10);
  const scheme = $("#h_scheme").value;
  const o = $("#h_out");
  if(!host || !port){ out(o, "Nhập host/port hợp lệ."); return; }

  // Mixed Content: nếu trang đang chạy HTTPS, nạp HTTP có thể bị chặn.
  const url = `${scheme}://${host}:${port}/favicon.ico?ts=${Date.now()}`;

  out(o, `Đang thử tải: ${url}`);
  const img = new Image();
  const t0 = performance.now();
  let finished = false;

  const done = (ok, status)=>{
    if(finished) return; finished = true;
    const ms = (performance.now() - t0).toFixed(1);
    out(o, (ok ? "✅ Kết nối thành công " : "❌ Không thể kết nối ") + `(${ms} ms)\\nGhi chú: ${status}`);
  };

  img.onload = ()=> done(true, "onload");
  img.onerror = ()=> done(false, "onerror (bị chặn CORS, MixedContent, hoặc cổng không phục vụ HTTP)");
  img.src = url;

  setTimeout(()=>done(false, "timeout"), 6000);
});

// --- WebRTC latency to STUN (browser -> Internet) ---
$("#w_btn")?.addEventListener("click", async ()=>{
  const stun = $("#w_stun").value;
  const o = $("#w_out");
  out(o, "Đang đo...");
  const t0 = performance.now();
  try{
    const pc = new RTCPeerConnection({ iceServers: [{ urls: stun }] });
    pc.createDataChannel("x");
    await pc.setLocalDescription(await pc.createOffer());

    let got = false;
    pc.onicecandidate = (e)=>{
      if(e && e.candidate){
        got = true;
        const ms = (performance.now() - t0).toFixed(1);
        out(o, `✅ ICE candidate sau ${ms} ms\\nCandidate: ${e.candidate.candidate}`);
        pc.close();
      }
    };
    setTimeout(()=>{
      if(!got){
        out(o, "❌ Không thu được ICE candidate (bị chặn WebRTC/STUN hoặc mạng hạn chế).");
        pc.close();
      }
    }, 6000);
  }catch(e){
    out(o, "Lỗi WebRTC: " + e);
  }
});
</script>
        """,
        height=700,
    )

def render():
    st.header("🌐 Network")

    # Thêm tab "Client (Browser) Tests)" chạy hoàn toàn trên trình duyệt
    tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8 = st.tabs(
        ["View IP", "Ping", "Check SSL", "Traceroute", "DNS", "WHOIS", "Port Scan", "Client (Browser) Tests"]
    )

    # ---- View IP (Client) ----
    with tab1:
        st.subheader("IP (Client)")
        _client_ips_widget()
        st.caption("Public IP (Auto) ưu tiên IPv6 nếu có, nếu không sẽ dùng IPv4. IPv4 Local có thể không lấy được do bảo mật WebRTC của trình duyệt.")

    # ---- Ping (server-side) ----
    with tab2:
        with st.form("f_ping"):
            host = st.text_input("Host/IP", placeholder="vd: 8.8.8.8 hoặc example.com")
            ok = st.form_submit_button("Ping")
        if ok and host.strip():
            st.markdown(f"<span style='color:#d00'>{_ts()}</span>  Ping {_host_link(host)}", unsafe_allow_html=True)
            st.caption("Nếu môi trường không có lệnh `ping`, hệ thống sẽ dùng **TCP ping** (thử 443/80/53).")
            st.code(ping_host(host.strip()))

    # ---- Check SSL (server-side) ----
    with tab3:
        with st.form("f_ssl"):
            host = st.text_input("Host", placeholder="example.com")
            port = st.number_input("Port", min_value=1, max_value=65535, value=443, step=1)
            ok = st.form_submit_button("Check SSL")
        if ok and host.strip():
            st.code(check_ssl(host.strip(), int(port)))

    # ---- Traceroute (server-side) ----
    with tab4:
        with st.form("f_trace"):
            host = st.text_input("Host/IP", placeholder="vd: 8.8.8.8 hoặc example.com")
            ok = st.form_submit_button("Traceroute")
        if ok and host.strip():
            st.caption("Tự phát hiện `tracert`/`traceroute`/`tracepath`. Nếu môi trường không hỗ trợ sẽ hiển thị thông báo.")
            st.code(traceroute_host(host.strip()))

    # ---- DNS (server-side) ----
    with tab5:
        with st.form("f_dns"):
            host = st.text_input("Host/Domain", placeholder="example.com")
            ok = st.form_submit_button("Tra DNS")
        if ok and host.strip():
            st.code(dns_lookup(host.strip()))

    # ---- WHOIS (server-side) ----
    with tab6:
        with st.form("f_whois"):
            domain = st.text_input("Domain", placeholder="example.com")
            ok = st.form_submit_button("WHOIS")
        if ok and domain.strip():
            st.code(whois_query(domain.strip()))

    # ---- Port Scan (server-side) ----
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

    # ---- Client-side tools (browser) ----
    with tab8:
        st.subheader("Kiểm tra mạng từ TRÌNH DUYỆT (client-side)")
        st.caption("Các phép thử chạy 100% trên máy client. Hạn chế: không có ICMP, traceroute thật, và chỉ kiểm tra được cổng HTTP/HTTPS do giới hạn bảo mật trình duyệt.")
        _client_network_tools_widget()
