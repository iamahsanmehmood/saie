"""transport/ws_client.py — Persistent WebSocket client for the AI Bridge.

Replaces v1's socket-per-call TCP client. Holds one long-lived WebSocket
connection to the SketchUp Ruby plugin and speaks JSON-RPC 2.0.

Hardening over the prototype:
  * configurable per-request timeout
  * automatic reconnect on transient errors (broken pipe, server restart)
  * request-id correlation: response is always matched to its request,
    so out-of-order events / server-pushed notifications cannot poison a
    `send_request` call
  * structured exception classes (`BridgeError`, `BridgeTimeout`, `BridgeConnectionError`)
    instead of raw `RuntimeError`
  * JSON-RPC 2.0 compliant error parsing: handles both spec-shaped
    `{"code": int, "message": str, "data": ...}` and legacy string errors

The implementation stays SYNCHRONOUS because the SketchUp side processes
ops on the main UI thread one at a time. Async would not buy us throughput
here; it would just complicate the call sites.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from typing import Any, Dict, Optional
from typing import Any, Dict, Optional

from websockets.sync.client import connect as ws_connect
from websockets.exceptions import ConnectionClosed, WebSocketException

# Use core logger if available, else fall back to print.
try:
    from su_mcp_bridge.core.logger import get_logger
    log = get_logger(__name__)
except Exception:  # pragma: no cover -- core not yet importable during install
    import logging
    log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class BridgeError(RuntimeError):
    """Base class for all SketchUp-bridge transport errors."""

    def __init__(self, message: str, code: Optional[int] = None, data: Any = None):
        super().__init__(message)
        self.code = code
        self.data = data

    def __repr__(self) -> str:
        return f"BridgeError(code={self.code}, message={self.args[0]!r})"


class BridgeTimeout(BridgeError):
    """Raised when a request does not receive a response within the timeout."""


class BridgeConnectionError(BridgeError):
    """Raised when we cannot establish or recover the WebSocket connection."""


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


class SketchUpWSClient:
    """Synchronous JSON-RPC 2.0 client over a persistent WebSocket.

    Typical usage:
        with SketchUpWSClient() as client:
            client.send_request("ping")
            client.send_request("ops.wall.create", {...})

    Or manual:
        client = SketchUpWSClient()
        client.connect()
        ...
        client.disconnect()
    """

    DEFAULT_TIMEOUT_S: float = 30.0
    HANDSHAKE_TIMEOUT_S: float = 5.0
    MAX_RECONNECT_ATTEMPTS: int = 3
    RECONNECT_BACKOFF_S: float = 0.5

    # Adaptive timeout constants — used by batch_timeout() below.
    _BATCH_BASE_S: float = 15.0   # minimum for any batch
    _BATCH_PER_OP_S: float = 0.8  # extra seconds per sub-op
    _BATCH_MAX_S: float = 300.0   # hard cap (5 min)

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: Optional[int] = None,
        timeout: float = DEFAULT_TIMEOUT_S,
    ):
        # Allow the active port file to override the default 9876, 
        # so multiple SketchUp instances don't clash and the CLI always talks to the most recent one.
        resolved_port = port
        if resolved_port is None:
            resolved_port = 9876
            port_file = os.path.join(os.path.expanduser("~"), ".su_mcp_port")
            if os.path.exists(port_file):
                try:
                    with open(port_file, "r") as f:
                        resolved_port = int(f.read().strip())
                except Exception:
                    pass

        self.uri = f"ws://{host}:{resolved_port}"
        self.timeout = timeout
        self._ws = None
        # Buffer for out-of-order or server-pushed messages we haven't claimed yet.
        self._pending: Dict[str, Dict[str, Any]] = {}

    # -- context manager -----------------------------------------------------

    def __enter__(self) -> "SketchUpWSClient":
        self.connect()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.disconnect()

    @classmethod
    def batch_timeout(cls, n_ops: int) -> float:
        """Return a timeout (seconds) scaled to the number of batch sub-ops.

        Use this as the `timeout` arg when calling send_request for ops.batch
        to prevent false timeouts on large model builds.

        Examples:
            10 ops  →  23 s
            50 ops  →  55 s
            200 ops → 175 s
            500 ops → 300 s (capped)
        """
        return min(cls._BATCH_BASE_S + n_ops * cls._BATCH_PER_OP_S, cls._BATCH_MAX_S)

    # -- lifecycle -----------------------------------------------------------

    def connect(self) -> None:
        """Open the WebSocket. Idempotent: no-op if already connected."""
        if self._ws is not None:
            return
        last_err: Optional[Exception] = None
        for attempt in range(1, self.MAX_RECONNECT_ATTEMPTS + 1):
            try:
                self._ws = ws_connect(
                    self.uri,
                    open_timeout=self.HANDSHAKE_TIMEOUT_S,
                )
                log.info("Connected to bridge at %s (attempt %d)", self.uri, attempt)
                return
            except (OSError, WebSocketException) as e:
                last_err = e
                if attempt < self.MAX_RECONNECT_ATTEMPTS:
                    backoff = self.RECONNECT_BACKOFF_S * attempt
                    log.warning(
                        "Connect to %s failed (%s); retrying in %.1fs",
                        self.uri,
                        e,
                        backoff,
                    )
                    time.sleep(backoff)
                    continue
        raise BridgeConnectionError(
            f"Could not connect to SketchUp bridge at {self.uri} after "
            f"{self.MAX_RECONNECT_ATTEMPTS} attempts: {last_err}"
        ) from last_err

    def disconnect(self) -> None:
        """Close the WebSocket. Idempotent."""
        if self._ws is None:
            return
        try:
            self._ws.close()
        except Exception as e:
            log.debug("disconnect: ignoring close error: %s", e)
        self._ws = None
        self._pending.clear()

    @property
    def is_connected(self) -> bool:
        return self._ws is not None

    # -- request/response ----------------------------------------------------

    def send_request(
        self,
        method: str,
        params: Optional[Dict[str, Any]] = None,
        timeout: Optional[float] = None,
    ) -> Any:
        """Send a JSON-RPC 2.0 request and block until the matching response.

        Args:
            method: JSON-RPC method name, e.g. "ops.wall.create".
            params: optional params dict. Defaults to {}.
            timeout: per-call override of the client's default timeout.

        Returns:
            The `result` field of the JSON-RPC response (a dict / list / scalar).

        Raises:
            BridgeError: server returned a JSON-RPC error.
            BridgeTimeout: no matching response within timeout.
            BridgeConnectionError: connection was lost and could not be re-established.
        """
        if self._ws is None:
            self.connect()

        req_id = str(uuid.uuid4())
        payload = {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": method,
            "params": params or {},
        }
        wire = json.dumps(payload, separators=(",", ":"))
        effective_timeout = timeout if timeout is not None else self.timeout

        # Send with one-shot reconnect retry on broken-pipe-style failures.
        try:
            self._ws.send(wire)
        except (ConnectionClosed, OSError, WebSocketException) as e:
            log.warning("send failed (%s); reconnecting and retrying once", e)
            self._ws = None
            self.connect()
            assert self._ws is not None
            self._ws.send(wire)

        # Wait for the response with the matching id. Drop / log other messages.
        res = self._receive_matching(req_id, effective_timeout)
        
        # Post-process: Convert PNG captures to WebP automatically to save bandwidth/storage.
        if method == "view.capture" and isinstance(res, dict) and res.get("path"):
            res["path"] = self._convert_png_to_webp(res["path"])
        elif method == "view.capture_canonical" and isinstance(res, dict) and "captures" in res:
            for c in res.get("captures", []):
                if c.get("path"):
                    c["path"] = self._convert_png_to_webp(c["path"])
                    
        return res

    # -- internals -----------------------------------------------------------

    def _receive_matching(self, expected_id: str, timeout: float) -> Any:
        # Check if we already buffered the response while reading earlier.
        if expected_id in self._pending:
            response = self._pending.pop(expected_id)
            return self._unwrap_response(response)

        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise BridgeTimeout(
                    f"No response for request id={expected_id} within {timeout:.1f}s"
                )

            try:
                raw = self._ws.recv(timeout=remaining)
            except TimeoutError as e:
                raise BridgeTimeout(
                    f"recv timed out after {timeout:.1f}s for id={expected_id}"
                ) from e
            except (ConnectionClosed, OSError, WebSocketException) as e:
                raise BridgeConnectionError(
                    f"WebSocket closed while waiting for id={expected_id}: {e}"
                ) from e

            try:
                msg = json.loads(raw)
            except json.JSONDecodeError as e:
                log.warning("Discarding non-JSON message from bridge: %s", e)
                continue

            msg_id = msg.get("id")

            # Server-pushed event (no id) — log and keep waiting.
            if msg_id is None:
                method = msg.get("method")
                if method:
                    log.debug("bridge event %s: %s", method, msg.get("params"))
                else:
                    log.debug("bridge: discarded id-less message: %s", msg)
                continue

            if msg_id == expected_id:
                return self._unwrap_response(msg)

            # Out-of-order response. Buffer and keep waiting.
            log.debug("buffering out-of-order response id=%s", msg_id)
            self._pending[msg_id] = msg

    @staticmethod
    def _unwrap_response(response: Dict[str, Any]) -> Any:
        """Translate a JSON-RPC response into a Python return value or raise."""
        if "error" in response and response["error"] is not None:
            err = response["error"]
            # JSON-RPC 2.0 spec: error is {"code": int, "message": str, "data": any}.
            # Older Ruby code returned a bare string; tolerate it for one cycle.
            if isinstance(err, dict):
                raise BridgeError(
                    err.get("message", "Unknown bridge error"),
                    code=err.get("code"),
                    data=err.get("data"),
                )
            raise BridgeError(str(err))
        return response.get("result")

    # -- convenience helpers -------------------------------------------------

    def ping(self, timeout: float = 5.0) -> bool:
        """Verify the bridge is alive. Returns True on success."""
        try:
            self.send_request("ping", timeout=timeout)
            return True
        except BridgeError as e:
            log.warning("ping failed: %s", e)
            return False

    def _convert_png_to_webp(self, path: str) -> str:
        """Convert a local PNG file to WebP and delete the original."""
        if not path.lower().endswith(".png"):
            return path
        try:
            # Import Pillow here to avoid hard dependency failure if not installed
            from PIL import Image
        except ImportError:
            log.warning("Pillow not installed; skipping WebP conversion.")
            return path
            
        webp_path = path[:-4] + ".webp"
        try:
            with Image.open(path) as img:
                # Convert to RGB if it's RGBA but we want a smaller file, 
                # but WebP supports alpha. We'll keep it as is.
                img.save(webp_path, "WEBP", quality=85)
            # Remove original PNG to save space
            if os.path.exists(path):
                os.remove(path)
            return webp_path
        except Exception as e:
            log.error("Failed to convert %s to webp: %s", path, e)
            return path
