"""core/lifecycle.py — SketchUp application lifecycle control.

Start, stop, and restart SketchUp from Python. Also provides
file operations (save, open, new) via the bridge RPC.
"""

from __future__ import annotations

import os
import subprocess
import time
import winreg
from pathlib import Path
from typing import Optional

from .logger import get_logger

log = get_logger(__name__)

# Common SketchUp install paths
_COMMON_PATHS = [
    r"C:\Program Files\SketchUp\SketchUp 2025\SketchUp.exe",
    r"C:\Program Files\SketchUp\SketchUp 2024\SketchUp.exe",
    r"C:\Program Files (x86)\SketchUp\SketchUp 2025\SketchUp.exe",
]


def find_sketchup_exe() -> Optional[Path]:
    """Auto-detect SketchUp installation from registry and common paths."""
    # Try Windows registry first
    try:
        key = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\SketchUp\SketchUp 2025",
            0,
            winreg.KEY_READ | winreg.KEY_WOW64_64KEY,
        )
        install_dir, _ = winreg.QueryValueEx(key, "InstallDir")
        winreg.CloseKey(key)
        exe = Path(install_dir) / "SketchUp.exe"
        if exe.exists():
            log.info(f"Found SketchUp via registry: {exe}")
            return exe
    except (OSError, FileNotFoundError):
        pass

    # Try environment variable
    env_path = os.environ.get("SKETCHUP_EXE")
    if env_path and Path(env_path).exists():
        log.info(f"Found SketchUp via SKETCHUP_EXE env: {env_path}")
        return Path(env_path)

    # Try common paths
    for p in _COMMON_PATHS:
        if Path(p).exists():
            log.info(f"Found SketchUp at common path: {p}")
            return Path(p)

    log.warning("Could not find SketchUp installation")
    return None


def _set_active_port(port: int):
    port_file = Path.home() / ".su_mcp_port"
    with open(port_file, "w") as f:
        f.write(str(port))


def _find_sketchup_with_model(filepath: str) -> Optional[int]:
    """Scan ports 9876-9885 to find if a SketchUp instance already has this model open."""
    from su_mcp_bridge.transport.ws_client import SketchUpWSClient
    import os
    
    abs_path = os.path.abspath(filepath).lower()
    for port in range(9876, 9886):
        try:
            # Short timeout since we just want to know if it's there
            with SketchUpWSClient(port=port, timeout=1.0) as client:
                res = client.send_request("lifecycle.model_info")
                if res and isinstance(res, dict):
                    open_path = res.get("path")
                    if open_path and os.path.abspath(open_path).lower() == abs_path:
                        return port
        except Exception:
            continue
    return None


def start_sketchup(filepath: str = "", wait_for_bridge: bool = True, timeout: int = 30) -> Optional[subprocess.Popen]:
    """Launch SketchUp, optionally opening a file.
    
    Args:
        filepath: Path to .skp file to open (optional)
        wait_for_bridge: If True, wait for the WebSocket bridge to become available
        timeout: Seconds to wait for bridge connection
    
    Returns:
        The subprocess.Popen object, or None if SketchUp wasn't found
    """
    exe = find_sketchup_exe()
    if not exe:
        log.error("Cannot start SketchUp: executable not found")
        return None

    if filepath and Path(filepath).exists():
        found_port = _find_sketchup_with_model(filepath)
        if found_port:
            log.info(f"Model already open in SketchUp (port {found_port}). Switching active context.")
            _set_active_port(found_port)
            class ExistingProc:
                pid = "existing"
            return ExistingProc()

    cmd = [str(exe)]
    if filepath and Path(filepath).exists():
        cmd.append(filepath)
    else:
        # Prevent SketchUp from showing the Welcome Screen by opening a default template
        template = exe.parent / "Resources" / "en-US" / "Templates" / "Temp02b - Arch.skp"
        if template.exists():
            cmd.append(str(template))

    log.info(f"Starting SketchUp: {' '.join(cmd)}")
    proc = subprocess.Popen(cmd)

    if wait_for_bridge:
        _wait_for_bridge_connection(timeout)

    return proc


def _wait_for_bridge_connection(timeout: int = 30) -> bool:
    """Poll until the WebSocket bridge accepts connections."""
    from su_mcp_bridge.transport.ws_client import SketchUpWSClient, BridgeConnectionError

    host = os.environ.get("SKETCHUP_HOST", "localhost")
    port = int(os.environ.get("SKETCHUP_PORT", "9876"))

    start = time.time()
    while time.time() - start < timeout:
        try:
            client = SketchUpWSClient(host=host, port=port, timeout=5)
            client.connect()
            client.disconnect()
            log.info("Bridge connection established")
            return True
        except BridgeConnectionError:
            time.sleep(1)

    log.warning(f"Bridge did not become available within {timeout}s")
    return False


def close_sketchup() -> dict:
    """Send close command to SketchUp via the bridge."""
    from su_mcp_bridge.transport.ws_client import SketchUpWSClient

    host = os.environ.get("SKETCHUP_HOST", "localhost")
    port = int(os.environ.get("SKETCHUP_PORT", "9876"))

    try:
        client = SketchUpWSClient(host=host, port=port, timeout=10)
        client.connect()
        result = client.send_request("lifecycle.close")
        client.disconnect()
        return result
    except Exception as e:
        log.error(f"Failed to close SketchUp: {e}")
        return {"error": str(e)}


def restart_sketchup(filepath: str = "", timeout: int = 30) -> dict:
    """Close SketchUp, wait for exit, then restart."""
    close_result = close_sketchup()
    time.sleep(3)  # Give SketchUp time to close
    proc = start_sketchup(filepath, wait_for_bridge=True, timeout=timeout)
    return {
        "close_result": close_result,
        "restarted": proc is not None,
    }
