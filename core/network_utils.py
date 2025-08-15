# core/network_utils.py
from __future__ import annotations
import socket, ssl, subprocess, sys, os, datetime, urllib.request, json, shutil, time
from typing import List, Tuple, Iterable, Callable
from concurrent.futures import ThreadPoolExecutor, as_completed

# --------- Helpers ---------
def _run_cmd(cmd: List[str], timeout: int = 60) -> str:
    try:
        cp = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        out = cp.stdout or cp.stderr
        return out.strip() if out else "Không có dữ liệu."
    except Exception as e:
        return f"Lỗi chạy lệnh: {e}"

# ---- TCP ping fallback (khi không có lệnh ping/ICMP bị chặn) ----
def _tcp_ping_once(host: str, port: int, timeout: float = 1.5) -> Tuple[bool, float | None]:
    start = time.perf_counter()
    try:
        with socket.create_connection((host, port), timeout=timeout):
            elapsed = (time.perf_counter() - start) * 1000.0
            return True, elapsed
    except Exception:
        return False, None

def _tcp_ping(host: str, attempts: int = 3) -> str:
    ports = [443, 80, 53]  # HTTPS/HTTP/DNS
    lines = []
    ok_any = False
    for i in range(1, attempts + 1):
        port = ports[(i - 1) % len(ports)]
        ok, ms = _tcp_ping_once(host, port)
        if ok:
            ok_any = True
            lines.append(f"TCP ping to {host}:{port}  time={ms:.1f} ms")
        else:
            lines.append(f"TCP ping to {host}:{port}  timeout")
        time.sleep(0.2)
    if not ok_any:
        lines.append("Không thể ping (không mở port phổ biến hoặc bị chặn).")
    return "\n".join(lines)

# --------- Public / Local IP ---------
def get_public_ip() -> str:
    try:
        with urllib.request.urlopen("https://api.ipify.org?format=json", timeout=5) as r:
            data = json.loads(r.read().decode("utf-8"))
            return data.get("ip", "Không xác định")
    except Exception as e:
        return f"Lỗi lấy IP public: {e}"

def get_local_ips() -> List[str]:
    ips = set()
    try:
        host = socket.gethostname()
        for fam, _, _, _, sockaddr in socket.getaddrinfo(host, None):
            ip = sockaddr[0]
            if ":" not in ip and not ip.startswith("127."):
                ips.add(ip)
    except Exception:
        pass
    # psutil (nếu có) để bổ sung
    try:
        import psutil
        for _, addrs in psutil.net_if_addrs().items():
            for a in addrs:
                if a.family == socket.AF_INET and not a.address.startswith("127."):
                    ips.add(a.address)
    except Exception:
        pass
    return sorted(ips)

# --------- Ping / Traceroute ---------
def ping_host(host: str) -> str:
    exe = "ping.exe" if sys.platform.startswith("win") else "ping"
    if shutil.which(exe) or shutil.which("ping"):
        if sys.platform.startswith("win"):
            return _run_cmd(["ping", "-n", "4", host])
        else:
            return _run_cmd(["ping", "-c", "4", host])
    # Fallback TCP ping
    return _tcp_ping(host)

def traceroute_host(host: str) -> str:
    if sys.platform.startswith("win"):
        if shutil.which("tracert") or shutil.which("tracert.exe"):
            return _run_cmd(["tracert", "-d", host])
    else:
        if shutil.which("traceroute"):
            return _run_cmd(["traceroute", "-n", host])
        if shutil.which("tracepath"):
            return _run_cmd(["tracepath", host])
    return "Môi trường không có lệnh traceroute/tracert/tracepath (Cloud thường chặn)."

# --------- SSL ---------
def check_ssl(host: str, port: int = 443) -> str:
    try:
        ctx = ssl.create_default_context()
        with socket.create_connection((host, port), timeout=5) as sock:
            with ctx.wrap_socket(sock, server_hostname=host) as ssock:
                cert = ssock.getpeercert()
        subj = dict(x[0] for x in cert.get("subject", []))
        issuer = dict(x[0] for x in cert.get("issuer", []))
        not_before = cert.get("notBefore")
        not_after = cert.get("notAfter")
        res = [
            f"Subject: {subj.get('commonName', subj)}",
            f"Issuer: {issuer.get('commonName', issuer)}",
            f"Valid from: {not_before}",
            f"Valid until: {not_after}",
        ]
        return "\n".join(res)
    except Exception as e:
        return f"Lỗi kiểm tra SSL: {e}"

# --------- DNS ---------
def dns_lookup(host: str) -> str:
    lines = []
    try:
        infos = socket.getaddrinfo(host, None)
        addrs = sorted({i[4][0] for i in infos})
        lines.append("Địa chỉ:")
        for a in addrs:
            lines.append(f"  - {a}")
    except Exception as e:
        lines.append(f"Lỗi DNS (socket): {e}")

    # Nếu có dnspython thì xem thêm
    try:
        import dns.resolver
        for rtype in ["A", "AAAA", "MX", "NS", "TXT", "CNAME"]:
            try:
                answers = dns.resolver.resolve(host, rtype)
                vals = [str(rdata).strip() for rdata in answers]
                lines.append(f"{rtype}: " + ", ".join(vals))
            except Exception:
                pass
    except Exception:
        lines.append("(Gợi ý: cài 'dnspython' để xem MX/NS/TXT chi tiết)")
    return "\n".join(lines)

# --------- WHOIS ---------
def whois_query(domain: str) -> str:
    try:
        import whois
        w = whois.whois(domain)
        parts = []
        for k in ["domain_name", "registrar", "creation_date", "expiration_date", "name_servers", "status"]:
            v = w.get(k)
            parts.append(f"{k}: {v}")
        return "\n".join(parts)
    except Exception as e:
        return f"Lỗi WHOIS (cần package 'python-whois'): {e}"

# --------- Port scan ---------
def _probe_port(host: str, port: int, timeout: float) -> tuple[int, bool]:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return port, True
    except Exception:
        return port, False

def port_scan(
    host: str,
    ports: Iterable[int] | None = None,
    timeout: float = 0.3,
    workers: int = 200,
    progress_cb: Callable[[int, int], None] | None = None,
) -> str:
    """
    Quét cổng TCP.
    - Nếu 'ports' = None hoặc rỗng -> quét toàn bộ 1..65535.
    - progress_cb(total, done): callback để UI cập nhật progress.
    """
    try:
        if not ports:
            ports = range(1, 65536)
        ports = [p for p in ports if 1 <= int(p) <= 65535]

        total = len(ports)
        open_ports: list[int] = []
        done = 0

        with ThreadPoolExecutor(max_workers=workers) as ex:
            futures = {ex.submit(_probe_port, host, int(p), timeout): p for p in ports}
            for fut in as_completed(futures):
                port, ok = fut.result()
                if ok:
                    open_ports.append(port)
                done += 1
                if progress_cb:
                    progress_cb(total, done)

        open_ports.sort()
        if open_ports:
            return "OPEN:\n" + "\n".join(f"{p}/tcp OPEN" for p in open_ports)
        return "Không phát hiện cổng mở."
    except Exception as e:
        return f"Lỗi scan: {e}"
