import platform, psutil, socket, getpass, datetime

def get_system_info() -> dict:
    boot_time = datetime.datetime.fromtimestamp(psutil.boot_time()).strftime("%Y-%m-%d %H:%M:%S")
    return {
        "OS": platform.system(),
        "OS Version": platform.version(),
        "OS Release": platform.release(),
        "Hostname": socket.gethostname(),
        "User": getpass.getuser(),
        "CPU Cores (physical)": psutil.cpu_count(logical=False),
        "CPU Cores (logical)": psutil.cpu_count(logical=True),
        "RAM (GB)": round(psutil.virtual_memory().total / (1024 ** 3), 2),
        "Boot Time": boot_time,
        "Python Version": platform.python_version(),
        "Machine": platform.machine(),
        "Processor": platform.processor(),
    }
