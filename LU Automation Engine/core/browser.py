import shutil
import socket
import subprocess
import time
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.chrome.options import Options

from .config import profile_dir


def _chrome_path() -> str:
    candidates = (
        shutil.which("chrome.exe"),
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    )
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return candidate
    raise FileNotFoundError("Google Chrome executable was not found.")


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def launch_browser() -> tuple[subprocess.Popen, int, Path]:
    chrome_path = _chrome_path()
    port = _free_port()
    profile = profile_dir()
    process = subprocess.Popen(
        [
            chrome_path,
            f"--user-data-dir={profile}",
            f"--remote-debugging-port={port}",
            "--start-maximized",
            "https://police.san-andreas.net/ucp.php?mode=login",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"Chrome exited during startup with code {process.returncode}.")
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return process, port, profile
        except OSError:
            time.sleep(0.2)
    process.terminate()
    raise TimeoutError("Chrome remote debugging endpoint did not start.")


def attach_driver(port: int):
    options = Options()
    options.add_experimental_option("debuggerAddress", f"127.0.0.1:{port}")
    return webdriver.Chrome(options=options)
