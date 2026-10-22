"""Malware scanning for uploaded documents, before anything is stored.

Documents (title deeds, indentures, authorisation letters) are kept as uploaded, so unlike
photos they are never re-encoded. Every one is scanned first; an infected or unscannable
file is refused and never reaches storage (fail closed).

- ClamAvScanner: talks to clamd over TCP with the INSTREAM command (standard ClamAV).
- FakeScanner: development and tests only; flags the EICAR test string. Refused in production.
"""

import importlib
import socket
import struct
from dataclasses import dataclass

from app.config import get_settings

# The standard antivirus test string, built in two parts so this source file isn't itself
# quarantined by antivirus on a developer's machine.
EICAR = b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$" + b"EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"


class ScanUnavailable(Exception):
    """The scanner couldn't be reached; the upload is refused rather than let through."""


@dataclass(frozen=True)
class ScanResult:
    clean: bool
    signature: str = ""


class FakeScanner:
    name = "fake"

    def scan(self, data: bytes) -> ScanResult:
        return ScanResult(False, "Eicar-Test-Signature") if EICAR in data else ScanResult(True)


class ClamAvScanner:
    name = "clamav"
    CHUNK = 64 * 1024

    def scan(self, data: bytes) -> ScanResult:
        settings = get_settings()
        try:
            with socket.create_connection((settings.clamd_host, settings.clamd_port), timeout=30) as conn:
                conn.sendall(b"zINSTREAM\0")
                for i in range(0, len(data), self.CHUNK):
                    chunk = data[i : i + self.CHUNK]
                    conn.sendall(struct.pack("!L", len(chunk)) + chunk)
                conn.sendall(struct.pack("!L", 0))
                reply = b""
                while not reply.endswith(b"\0"):
                    part = conn.recv(4096)
                    if not part:
                        break
                    reply += part
        except OSError as exc:
            raise ScanUnavailable(str(exc)) from exc
        text = reply.rstrip(b"\0").decode(errors="replace")  # "stream: OK" or "stream: <name> FOUND"
        if text.endswith("OK"):
            return ScanResult(True)
        if text.endswith("FOUND"):
            return ScanResult(False, text.removeprefix("stream:").removesuffix("FOUND").strip())
        raise ScanUnavailable(f"Unexpected scanner reply: {text[:80]}")


def get_scanner():
    module, _, cls = get_settings().malware_scanner.rpartition(".")
    return getattr(importlib.import_module(module), cls)()
