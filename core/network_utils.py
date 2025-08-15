import socket, ssl, subprocess, sys, os, datetime, urllib.request, json
from typing import List

# ---------- Public/Local IP ----------
def get_public_ip() -> str:
    # Thử nhiều dịch vụ công cộng
    for url in ("https://api.ipify.org?format=json", "https://ifconfig.me/all.json"):
        try:
            with urllib.request.urlopen(url, timeout=5) as r:
                data = r.read().decode("utf-8", errors="ignore")
                if "ip" in data:
                    return json.loads(data)["ip"]
                # ifconfig.me
                if "ip_addr" in data:
                    return json.loads(data)["ip_addr"]
        except Exception:
            continue
    return "Không lấy được IP public"

def get_ip_local() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return socket.gethostbyname(socket.gethostname())

def get_dns_servers() -> str:
    try:
        import dns.resolver
        return ", ".join(dns.resolver.Resolver().nameservers)
    except Exception:
        return "Không đọc được DNS (cần dnspython)"

# ---------- Ping / Traceroute ----------
def _run_cmd(cmd: List[str]) -> str:
    try:
        cp = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        out = cp.stdout or cp.stderr
        return out.strip() if out else "Không có dữ liệu."
    except Exception as e:
        return f"Lỗi chạy lệnh: {e}"

def ping_host(host: str) -> str:
    if sys.platform.startswith("win"):
        return _run_cmd(["ping", "-n", "4", host])
    else:
        return _run_cmd(["ping", "-c", "4", host])

def traceroute_host(host: str) -> str:
    if sys.platform.startswith("win"):
        return _run_cmd(["tracert", "-d", host])
    else:
        return _run_cmd(["traceroute", "-n", host])

# ---------- DNS / WHOIS ----------
def dns_lookup(host: str) -> str:
    try:
        import dns.resolver
        res = dns.resolver.Resolver()
        records = []
        for rtype in ("A", "AAAA", "CNAME", "NS", "MX", "TXT"):
            try:
                ans = res.resolve(host, rtype)
                for rr in ans:
                    records.append(f"{rtype}\t{rr.to_text()}")
            except Exception:
                pass
        return "\n".join(records) or "Không có bản ghi."
    except Exception as e:
        return f"Lỗi DNS: {e}"

def whois_lookup_verbose(domain: str) -> str:
    try:
        import whois
        data = whois.whois(domain)
        return "\n".join([f"{k}: {v}" for k, v in data.items()])
    except Exception as e:
        return f"Lỗi WHOIS: {e}"

# ---------- SSL ----------
def check_ssl_expiry(domain: str, port: int = 443) -> str:
    try:
        ctx = ssl.create_default_context()
        with socket.create_connection((domain, port), timeout=8) as sock:
            with ctx.wrap_socket(sock, server_hostname=domain) as ssock:
                cert = ssock.getpeercert()
        not_after = cert.get("notAfter")
        if not not_after:
            return "Không đọc được ngày hết hạn."
        exp = datetime.datetime.strptime(not_after, "%b %d %H:%M:%S %Y %Z")
        days = (exp - datetime.datetime.utcnow()).days
        return f"Chứng chỉ hết hạn: {exp} (UTC) ~ còn {days} ngày"
    except Exception as e:
        return f"Lỗi SSL: {e}"

# ---------- Port Scan ----------
COMMON_PORTS = [
    7,9,13,17,19,20,21,22,23,25,37,49,53,67,68,69,80,88,110,111,123,135,137,138,139,
    143,161,162,179,389,427,443,445,465,500,515,520,548,554,587,593,631,636,853,873,
    902,903,990,993,995,1080,1194,1433,1521,1723,1883,2375,2376,27017,27018,27019,
    3000,3050,3306,3310,3389,3478,3690,433,4369,4430,5000,5001,5044,5222,5223,5432,
    5601,5671,5672,5900,5985,5986,6129,6379,6443,6881,7000,7001,7199,8000,8008,8080,
    8081,8088,8089,8161,8333,8443,8500,8883,8888,9000,9042,9092,9100,9200,9300,9418,
    9443,10050,10051,11211
]

def scan_open_ports(host: str, ports: List[int] = None, timeout: float = 0.5) -> str:
    target_ports = ports or COMMON_PORTS
    lines = []
    for p in target_ports:
        try:
            with socket.create_connection((host, p), timeout=timeout):
                lines.append(f"Cổng mở: {p}")
        except Exception:
            pass
    return "\n".join(lines) if lines else "Không tìm thấy cổng mở."

# ---------- LAN "speedtest" đơn giản ----------
def run_lan_speedtest():
    """
    Demo: ping gateway phổ biến; bạn có thể thay bằng logic riêng.
    """
    for gw in ("192.168.1.1", "192.168.0.1", "10.0.0.1"):
        res = ping_host(gw)
        if "TTL=" in res or "ttl=" in res:
            return res
    return "Không đo được (không thấy gateway phổ biến)."
