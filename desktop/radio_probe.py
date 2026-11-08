"""Real Meshtastic handshake checks for the desktop app.

Unlike launcher.check_tcp, these open a Meshtastic protocol session and read
the radio's node info. Nothing is transmitted on the mesh.
"""
from __future__ import annotations

import time

from radio_config import validate

TIMEOUT = 20


def split_host(endpoint: str) -> tuple[str, int]:
    host, sep, port = endpoint.rpartition(":")
    if sep and host and port.isdigit():
        return host, int(port)
    return endpoint, 4403


def _construct(cls, *args, **kwargs):
    """Pass a timeout where supported; older meshtastic releases lack the argument."""
    import inspect
    if "timeout" in inspect.signature(cls.__init__).parameters:
        kwargs["timeout"] = TIMEOUT
    return cls(*args, **kwargs)


def open_interface(mode: str, endpoint: str):
    mode, endpoint = validate(mode, endpoint)
    if mode == "tcp":
        from meshtastic.tcp_interface import TCPInterface
        host, port = split_host(endpoint)
        return _construct(TCPInterface, hostname=host, portNumber=port, noNodes=True)
    if mode == "serial":
        from meshtastic.serial_interface import SerialInterface
        return _construct(SerialInterface, devPath=endpoint, noNodes=True)
    from meshtastic.ble_interface import BLEInterface
    return _construct(BLEInterface, endpoint, noNodes=True)


def probe(mode: str, endpoint: str) -> dict:
    """Connect, read the local node identity, then disconnect."""
    interface = open_interface(mode, endpoint)
    try:
        info = interface.getMyNodeInfo() or {}
        if not info:
            raise ConnectionError("Radio did not report node info")
        user = info.get("user", {})
        metadata = getattr(interface, "metadata", None)
        return {
            "long_name": user.get("longName", "?"),
            "short_name": user.get("shortName", "?"),
            "hardware": user.get("hwModel", "?"),
            "firmware": getattr(metadata, "firmware_version", "") or "?",
            "node_num": info.get("num"),
        }
    finally:
        interface.close()


def probe_with_retry(mode: str, endpoint: str, attempts: int = 2, delay: float = 0.5) -> dict:
    """Retry a failed TCP handshake once; never retry non-TCP transports.

    A successful probe always closes its interface before returning. This helper
    does not reconnect a running bot or send mesh packets.
    """
    if attempts < 1 or delay < 0:
        raise ValueError("Retry attempts must be positive and delay nonnegative")
    mode, endpoint = validate(mode, endpoint)
    total = attempts if mode == "tcp" else 1
    for attempt in range(total):
        try:
            return probe(mode, endpoint)
        except (OSError, ConnectionError, TimeoutError):
            if attempt + 1 == total:
                raise
            time.sleep(delay)
    raise AssertionError("Unreachable retry state")

def describe(result: dict) -> str:
    return (f"Connected to {result['long_name']} ({result['short_name']}) • "
            f"{result['hardware']} • firmware {result['firmware']}")


def serial_ports() -> list[str]:
    """USB serial devices that look like Meshtastic radios."""
    from meshtastic.util import findPorts
    return findPorts(eliminate_duplicates=True)


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: radio_probe.py tcp|ble|serial ENDPOINT")
        return 2
    try:
        print("RADIO_PROBE_OK " + describe(probe(argv[0], argv[1])), flush=True)
        return 0
    except Exception as exc:  # report any failure as a clean, non-zero result
        print(f"RADIO_PROBE_FAILED {type(exc).__name__}: {exc}", flush=True)
        return 1


if __name__ == "__main__":
    import sys
    sys.exit(main(sys.argv[1:]))
