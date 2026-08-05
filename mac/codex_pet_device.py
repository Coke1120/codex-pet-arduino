#!/usr/bin/env python3
"""Pure USB identity helpers shared by Codex Pet host processes."""

import re
from typing import Any, Iterable, Optional


_COMPACT_USB_SERIAL = re.compile(r"^[0-9A-Fa-f]{12}$")
_COLON_USB_SERIAL = re.compile(r"^(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$")
_HYPHEN_USB_SERIAL = re.compile(r"^(?:[0-9A-Fa-f]{2}-){5}[0-9A-Fa-f]{2}$")
_C6_IDENTITY = re.compile(
    r"(?:esp32[\s_-]*c6|(?<![a-z0-9])c6(?![a-z0-9]))",
    re.IGNORECASE,
)


def canonicalize_usb_serial(raw: str) -> str:
    """Return a complete USB serial/MAC as uppercase colon-separated octets."""
    if not isinstance(raw, str) or not raw:
        raise ValueError("USB serial must be a complete 12-hex value")
    if _COMPACT_USB_SERIAL.fullmatch(raw):
        compact = raw
    elif _COLON_USB_SERIAL.fullmatch(raw) or _HYPHEN_USB_SERIAL.fullmatch(raw):
        compact = raw.replace(":", "").replace("-", "")
    else:
        raise ValueError("USB serial must be a complete 12-hex value")
    return ":".join(compact[index : index + 2] for index in range(0, 12, 2)).upper()


def _identity_text(port: Any) -> str:
    return " ".join(
        str(getattr(port, name, None) or "")
        for name in (
            "description",
            "manufacturer",
            "product",
            "interface",
            "hwid",
        )
    ).lower()


def _mentions_c6(text: str) -> bool:
    return _C6_IDENTITY.search(text) is not None


def board_score(port: Any) -> int:
    """Rank descriptor-identified P4 boards without guessing generic devices."""
    # Keep the pre-pin descriptor contract exact; hwid/serial never influence it.
    text = " ".join(
        str(getattr(port, name, None) or "")
        for name in ("description", "manufacturer", "product", "interface")
    ).lower()
    if _mentions_c6(text):
        return 0
    if "esp32-p4" in text or "esp32p4" in text or "jc4880p443c" in text:
        return 150
    return 0


def _canonical_port_serial(port: Any) -> Optional[str]:
    try:
        return canonicalize_usb_serial(getattr(port, "serial_number", None))
    except ValueError:
        return None


def _is_pinned_p4_identity(port: Any) -> bool:
    text = _identity_text(port)
    if _mentions_c6(text):
        return False
    clearly_espressif = "espressif" in text or "esp32" in text
    return (
        clearly_espressif
        and getattr(port, "vid", None) == 0x303A
        and getattr(port, "pid", None) == 0x1001
    )


def select_p4_port(
    ports: Iterable[Any], requested: str, pinned_serial: Optional[str] = None
) -> Optional[str]:
    """Select one P4 path using descriptors or a strict explicit USB pin."""
    enumerated = list(ports)
    if pinned_serial is not None:
        try:
            canonical_pin = canonicalize_usb_serial(pinned_serial)
        except ValueError:
            return None
        if requested == "auto" or not requested.startswith("/dev/cu."):
            return None
        serial_matches = [
            port
            for port in enumerated
            if _canonical_port_serial(port) == canonical_pin
        ]
        if len(serial_matches) != 1:
            return None
        port = serial_matches[0]
        if getattr(port, "device", None) != requested:
            return None
        return requested if _is_pinned_p4_identity(port) else None

    if requested != "auto":
        matches = [
            port
            for port in enumerated
            if getattr(port, "device", None) == requested
        ]
        if len(matches) != 1 or board_score(matches[0]) <= 0:
            return None
        return requested

    candidates = [port for port in enumerated if board_score(port) > 0]
    return getattr(candidates[0], "device", None) if len(candidates) == 1 else None
