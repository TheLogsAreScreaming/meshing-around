"""User-facing wording: connection methods and plain-language errors."""
from __future__ import annotations

TRANSPORTS = (("tcp", "Wi-Fi / Network"), ("ble", "Bluetooth"), ("serial", "USB cable"))
TRANSPORT_LABEL = dict(TRANSPORTS)
ADDRESS_HELP = {
    "tcp": ("Radio address",
            "Hostname or IP address, for example meshtastic.local or 192.168.1.50. "
            "Add :port only if your radio doesn't use 4403."),
    "ble": ("Bluetooth address",
            "The radio's Bluetooth address or name, for example 00:11:22:33:44:55. "
            "Disconnect the radio from your phone first."),
    "serial": ("USB port",
               "Usually /dev/cu.usbmodem… or /dev/cu.usbserial…. "
               "Use Find USB radio to fill this in."),
}
METHOD_HELP = {
    "tcp": "Connect to a radio on the same Wi-Fi or wired network. Network access must be "
           "enabled on the radio.",
    "ble": "Connect wirelessly to a nearby radio. macOS asks for Bluetooth permission the first time.",
    "serial": "Connect a radio to this Mac with a USB cable.",
}


def friendly_error(transport: str, error_type: str, message: str) -> tuple[str, str]:
    """(headline, advice) for a failed connection test."""
    text = f"{error_type} {message}".lower()
    if error_type == "ValueError":
        return "Check the address", message
    if "refused" in text:
        return ("The radio refused the connection",
                "The device is reachable but isn't accepting connections on that port. Make sure "
                "network access is enabled on the radio and that no other app is connected to it.")
    if "nodename" in text or "name or service" in text or "gaierror" in text \
            or "no address" in text or "name resolution" in text:
        return ("Couldn't find a radio at that address",
                "Check the spelling of the hostname, or use the radio's IP address. "
                "This Mac and the radio must be on the same network.")
    if error_type in ("TimeoutError", "timeout", "SerialTimeoutException") or "timed out" in text:
        return ("The radio didn't respond in time",
                "Make sure the radio is powered on and on the same network, then try again. "
                "A busy or distant radio can take a moment to answer.")
    if "permission" in text:
        return ("macOS blocked access to the radio",
                "Allow access when macOS asks, or check System Settings → Privacy & Security.")
    if transport == "serial":
        return ("Couldn't open the USB port",
                "Reconnect the cable, make sure the radio is powered, and use Find USB radio "
                "to pick the right port. Close other apps that use the radio.")
    if transport == "ble":
        return ("Bluetooth connection failed",
                "Make sure Bluetooth is on, the radio is nearby and powered, and it isn't "
                "connected to a phone or another app.")
    return ("Couldn't connect to the radio",
            "Check that the radio is powered on and the address is correct, then try again.")


def exit_message(code: int, requested: bool) -> tuple[str, str]:
    """(tone, sentence) describing how the bot process ended."""
    if requested or code in (0, -15):
        return "neutral", "Stopped"
    if code == 1:
        return "danger", "Stopped with an error — check Activity for details"
    return "danger", f"Stopped unexpectedly (exit code {code})"
