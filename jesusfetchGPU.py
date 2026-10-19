# COPYRIGHT (C) akettunen 2026
import os
import platform
import shutil
import sys
import threading
import time
import subprocess
import glob

#read requirments.txt 
import psutil

# customize by changing the color ansi code example: "\033[38;2;255;215;0m" <-- GOLD
COLOR = "\033[38;2;255;215;0m"  # default color = GOLD
BOLD = "\033[1m"
RESET = "\033[0m"
CLEAR_LINE = "\033[K"

# logo ascii (you can change the logo by removing the cross and replacing it with ur ascii logo)
logo = r"""
     .-.
   __| |__
  [__   __]
     | |
     | |
     | |
     '-'
""".strip("\n").splitlines()

lock = threading.Lock()
IS_WINDOWS = platform.system() == "Windows"

# powershell things
POWERSHELL = (shutil.which("pwsh") or shutil.which("powershell")) if IS_WINDOWS else None
CD_COMMANDS = ("cd", "chdir", "set-location", "sl")
# names powershell treats as aliases/cmdlets: never fast-path these
PS_ALIASES = {
    "ls", "dir", "cat", "cp", "mv", "rm", "ps", "kill", "echo", "curl", "wget",
    "sort", "man", "type", "diff", "sleep", "pwd", "clear", "cls", "where",
    "tee", "gc", "gci", "copy", "move", "del",
}
# characters that need a real powershell parser
PS_SPECIAL = set("|;&$`<>(){}\"'\n")


def enable_ansi():
    """Turn on ANSI escape codes on Windows without spawning a process."""
    if not IS_WINDOWS:
        return
    try:
        import ctypes
        k32 = ctypes.windll.kernel32
        handle = k32.GetStdHandle(-11)
        mode = ctypes.c_ulong()
        if k32.GetConsoleMode(handle, ctypes.byref(mode)):
            k32.SetConsoleMode(handle, mode.value | 0x0004)
    except Exception:
        os.system("")


#info static
def get_kernel():
    if IS_WINDOWS:
        return platform.release()
    try:
        with open("/proc/sys/kernel/osrelease") as f:
            return f.read().strip()
    except OSError:
        return platform.release()


def get_cpu_windows():
    import winreg
    key = r"HARDWARE\DESCRIPTION\System\CentralProcessor\0"
    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key) as k:
        return " ".join(winreg.QueryValueEx(k, "ProcessorNameString")[0].split())


def get_cpu_mac():
    import subprocess
    return subprocess.check_output(
        ["sysctl", "-n", "machdep.cpu.brand_string"], text=True
    ).strip()


def get_cpu_linux():
    name = None
    try:
        with open("/proc/cpuinfo") as f:
            for line in f:
                if line.startswith(("model name", "Model", "Hardware")):
                    name = line.split(":", 1)[1].strip()
                    break
    except OSError:
        pass

    freq = ""
    try:
        with open("/sys/devices/system/cpu/cpu0/cpufreq/cpuinfo_max_freq") as f:
            freq = f" @ {int(f.read()) / 1_000_000:.2f}GHz"
    except (OSError, ValueError):
        pass

    return f"{name or 'Unknown'} ({os.cpu_count()}){freq}"
    

def get_gpu():
    system = platform.system()

    # NVIDIA
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name",
                "--format=csv,noheader"
            ],
            capture_output=True,
            text=True,
            timeout=2,
            check=True
        )
        names = [x.strip() for x in result.stdout.splitlines() if x.strip()]
        if names:
            return ", ".join(names)
    except (FileNotFoundError, subprocess.SubprocessError):
        pass

    # Windows
    if system == "Windows":
        try:
            result = subprocess.run(
                [
                    POWERSHELL or "powershell",
                    "-NoProfile",
                    "-Command",
                    "Get-CimInstance Win32_VideoController | "
                    "Select-Object -ExpandProperty Name"
                ],
                capture_output=True,
                text=True,
                timeout=4,
                check=True
            )
            names = [
                x.strip() for x in result.stdout.splitlines()
                if x.strip()
            ]
            if names:
                return ", ".join(names)
        except (OSError, subprocess.SubprocessError):
            pass

    # macOS
    if system == "Darwin":
        try:
            result = subprocess.run(
                ["system_profiler", "SPDisplaysDataType"],
                capture_output=True,
                text=True,
                timeout=5,
                check=True
            )
            names = []
            for line in result.stdout.splitlines():
                line = line.strip()
                if line.startswith("Chipset Model:"):
                    names.append(line.split(":", 1)[1].strip())
            if names:
                return ", ".join(names)
        except (OSError, subprocess.SubprocessError):
            pass

    # AMD, INTEL (Linux)
    if system == "Linux":
        try:
            result = subprocess.run(
                ["lspci"],
                capture_output=True,
                text=True,
                timeout=2,
                check=True
            )
            names = []
            for line in result.stdout.splitlines():
                lower = line.lower()
                if any(x in lower for x in (
                    "vga compatible controller",
                    "3d controller",
                    "display controller"
                )):
                    names.append(line.split(": ", 1)[-1].strip())

            if names:
                return ", ".join(names)
        except (FileNotFoundError, subprocess.SubprocessError):
            pass

    return "Unknown"


def get_cpu():
    system = platform.system()
    try:
        if system == "Windows":
            return get_cpu_windows()
        if system == "Darwin":
            return get_cpu_mac()
        return get_cpu_linux()
    except Exception:
        return "Unknown"


# info live
GB = 1024 ** 3
DISK_PATH = "C:\\" if IS_WINDOWS else "/"
_disk_cache = ["", 0.0]


def get_cpu_usage():
    return f"{psutil.cpu_percent(interval=None):.1f}%"

def get_gpu_usage():
    # NVIDIA
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=utilization.gpu",
                "--format=csv,noheader,nounits"
            ],
            capture_output=True,
            text=True,
            timeout=2,
            check=True
        )
        values = [
            x.strip() for x in result.stdout.splitlines() if x.strip()
        ]
        if values:
            usages = [int(x) for x in values]
            return f"{usages[0]}%"
    except (FileNotFoundError, subprocess.SubprocessError, ValueError):
        pass

    # AMD, INTEL (Linux)
    if platform.system() == "Linux":
        for path in sorted(glob.glob(
            "/sys/class/drm/card*/device/gpu_busy_percent"
        )):
            try:
                with open(path) as f:
                    value = int(f.read().strip())
                if 0 <= value <= 100:
                    return f"{value}%"
            except (OSError, ValueError):
                continue

    return "N/A"


def get_memory_usage():
    ram = psutil.virtual_memory()
    return f"{ram.percent:.1f}% ({ram.used / GB:.1f}/{ram.total / GB:.1f} GB)"


def get_disk_usage():
    now = time.monotonic()
    if now - _disk_cache[1] >= 5:
        d = psutil.disk_usage(DISK_PATH)
        _disk_cache[0] = f"{d.percent:.1f}% ({d.used / GB:.1f}/{d.total / GB:.1f} GB)"
        _disk_cache[1] = now
    return _disk_cache[0]


def get_uptime():
    secs = int(time.time() - psutil.boot_time())
    days, rem = divmod(secs, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, seconds = divmod(rem, 60)

    parts = []
    if days:
        parts.append(f"{days}d")
    if days or hours:
        parts.append(f"{hours}h")
    if days or hours or minutes:
        parts.append(f"{minutes}m")
    parts.append(f"{seconds:02d}s")
    return " ".join(parts)


def build_info(static):
    return [
        ("OS", static["os"]),
        ("Host", static["host"]),
        ("Kernel", static["kernel"]),
        ("CPU", f"{get_cpu_usage()} | {static['cpu']}"),
        ("GPU", f"{get_gpu_usage()} | {static['gpu']}"),
        ("Memory", get_memory_usage()),
        ("Disk", get_disk_usage()),
    ]


#print
def render(info, left_cols, blank, max_right):
    out = []
    for i in range(max(len(left_cols), len(info))):
        left = left_cols[i] if i < len(left_cols) else blank
        if i < len(info):
            label, value = info[i]
            value = value[:max(max_right - len(label) - 2, 0)]
            out.append(f"{left}{BOLD}{COLOR}{label}{RESET}: {value}{CLEAR_LINE}")
        else:
            out.append(f"{left}{CLEAR_LINE}")
    return out


def draw(lines):
    """Draw the header at the top without disturbing the prompt (one write)."""
    buf = "\0337" + "".join(f"\033[{i + 1};1H{l}" for i, l in enumerate(lines)) + "\0338"
    with lock:
        sys.stdout.write(buf)
        sys.stdout.flush()


def updater(static, left_cols, blank, max_right, stop):
    while not stop.is_set():
        draw(render(build_info(static), left_cols, blank, max_right))
        stop.wait(1 - (time.time() % 1))


#command thing
def get_prompt():
    cwd = os.getcwd()
    if IS_WINDOWS:
        return f"PS {cwd}> "
    import getpass
    home = os.path.expanduser("~")
    if cwd == home or cwd.startswith(home + os.sep):
        cwd = "~" + cwd[len(home):]
    return f"{getpass.getuser()}@{platform.node()}:{cwd}$ "


def run_command(cmd):
    import subprocess

    parts = cmd.split(None, 1)
    head = parts[0].lower()

    if head in CD_COMMANDS:
        arg = parts[1].strip().strip("\"'") if len(parts) > 1 else "~"
        try:
            os.chdir(os.path.expanduser(arg))
        except OSError as e:
            print(f"cd: {e}")
        return

    try:
        if IS_WINDOWS and POWERSHELL:
            if head not in PS_ALIASES and not PS_SPECIAL.intersection(cmd):
                exe = shutil.which(parts[0])
                if exe and exe.lower().endswith(".exe"):
                    subprocess.run([exe] + cmd.split()[1:])
                    return
            subprocess.run([POWERSHELL, "-NoLogo", "-NoProfile", "-Command", cmd])
        else:
            subprocess.run(cmd, shell=True)
    except KeyboardInterrupt:
        print()


def main():
    enable_ansi()


    static = {
        "os": platform.system(),
        "host": platform.node(),
        "kernel": get_kernel(),
        "cpu": get_cpu(),
        "gpu": get_gpu(),
    }
    psutil.cpu_percent(interval=None)

    #print (slowed + reverb)
    logo_width = max(len(l) for l in logo)
    left_cols = [f"{COLOR}{l.ljust(logo_width)}{RESET}   " for l in logo]
    blank = " " * (logo_width + 3)
    height = max(len(logo), len(build_info(static)))

    size = shutil.get_terminal_size()
    rows, cols = size.lines, size.columns
    max_right = cols - logo_width - 4
    if rows < height + 6:
        print(f"Terminal too small: need at least {height + 6} rows.")
        return

    first_row = height + 2
    sys.stdout.write(
        "\033[2J"
        f"\033[{height + 1};1H{COLOR}{'─' * cols}{RESET}"
        f"\033[{first_row};{rows}r"
        f"\033[{first_row};1H"
    )
    sys.stdout.flush()

    stop = threading.Event()
    thread = threading.Thread(
        target=updater, args=(static, left_cols, blank, max_right, stop), daemon=True
    )
    thread.start()

    try:
        while True:
            try:
                cmd = input(get_prompt()).strip()
            except KeyboardInterrupt:
                print()
                continue
            except EOFError:
                break

            if not cmd:
                continue
            if cmd in ("exit", "quit", "q"):
                break
            if cmd == "help":
                print("  help         show this message")
                print("  clear        clear the command area")
                print("  cd <dir>     change directory")
                print("  exit         quit")
                print("  anything else runs in your shell")
                continue
            if cmd == "clear":
                with lock:
                    sys.stdout.write(f"\033[{first_row};1H\033[J")
                    sys.stdout.flush()
                continue

            run_command(cmd)
    finally:
        stop.set()
        thread.join(timeout=2)
        with lock:
            sys.stdout.write(f"\033[r\033[{rows};1H\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
