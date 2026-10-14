"""Identity (self-signed TLS cert), paired-device store and one-time pairing tokens.

No Qt imports here, so this module is easy to unit test.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import ipaddress
import json
import os
import secrets
import socket
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID
from platformdirs import user_data_dir

TOKEN_TTL = 120  # seconds a QR code stays valid


def data_dir() -> Path:
    override = os.environ.get("PORTNOIR_DATA_DIR")
    path = Path(override) if override else Path(user_data_dir("PortNoir", appauthor=False))
    path.mkdir(parents=True, exist_ok=True)
    return path


def _is_useful_ipv4(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return not (addr.is_loopback or addr.is_link_local or addr.is_multicast or addr.is_unspecified)


def local_ip() -> str:
    candidates: list[str] = []
    seen: set[str] = set()
    for host in ("8.8.8.8", "1.1.1.1", "10.255.255.255"):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(0.25)
            s.connect((host, 53))
            ip = s.getsockname()[0]
            if _is_useful_ipv4(ip) and ip not in seen:
                candidates.append(ip)
                seen.add(ip)
        except OSError:
            pass
        finally:
            try:
                s.close()
            except Exception:
                pass
    for family, _, _, _, sockaddr in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET, socket.SOCK_DGRAM):
        ip = sockaddr[0] if sockaddr else ""
        if _is_useful_ipv4(ip) and ip not in seen:
            candidates.append(ip)
            seen.add(ip)
    for ip in candidates:
        try:
            addr = ipaddress.ip_address(ip)
            if addr.is_private:
                return ip
        except ValueError:
            continue
    return candidates[0] if candidates else "127.0.0.1"


@dataclass
class Identity:
    cert_path: Path
    key_path: Path
    fingerprint: str  # sha256 of the DER certificate, hex

    @property
    def mac_id(self) -> str:
        return self.fingerprint[:16]

    @classmethod
    def load_or_create(cls, directory: Path) -> "Identity":
        cert_path, key_path = directory / "server.crt", directory / "server.key"
        if not (cert_path.exists() and key_path.exists()):
            _generate(cert_path, key_path)
        der = x509.load_pem_x509_certificate(cert_path.read_bytes()).public_bytes(serialization.Encoding.DER)
        return cls(cert_path, key_path, hashlib.sha256(der).hexdigest())


def _generate(cert_path: Path, key_path: Path) -> None:
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "PortNoir")])
    now = dt.datetime.now(dt.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
            .public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now - dt.timedelta(days=1))
            .not_valid_after(now + dt.timedelta(days=3650))
            .sign(key, hashes.SHA256()))
    key_path.write_bytes(key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    os.chmod(key_path, 0o600)
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))


@dataclass
class PairedDevice:
    id: str
    name: str
    model: str = ""
    key_hash: str = ""
    paired_at: float = 0.0
    last_seen: float = 0.0
    last_ip: str = ""


class DeviceStore:
    def __init__(self, path: Path):
        self.path = path
        self._devices: dict[str, PairedDevice] = {}
        if path.exists():
            for item in json.loads(path.read_text()):
                self._devices[item["id"]] = PairedDevice(**item)

    def all(self) -> list[PairedDevice]:
        return sorted(self._devices.values(), key=lambda d: d.name.lower())

    def get(self, device_id: str) -> PairedDevice | None:
        return self._devices.get(device_id)

    def upsert(self, device: PairedDevice) -> None:
        self._devices[device.id] = device
        self.save()

    def remove(self, device_id: str) -> None:
        self._devices.pop(device_id, None)
        self.save()

    def save(self) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps([asdict(d) for d in self._devices.values()], indent=2))
        tmp.replace(self.path)


def _hash(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


class PairingService:
    def __init__(self, identity: Identity, store: DeviceStore):
        self.identity, self.store = identity, store
        self._tokens: dict[str, float] = {}

    def new_payload(self, host: str, port: int, mac_name: str) -> dict:
        """Content of the QR code."""
        now = time.time()
        self._tokens = {t: exp for t, exp in self._tokens.items() if exp > now}
        token = secrets.token_urlsafe(16)  # 128 bits, single use
        self._tokens[token] = now + TOKEN_TTL
        return {"v": 1, "name": mac_name, "host": host, "port": port,
                "token": token, "fp": self.identity.fingerprint}

    def consume_token(self, token: str) -> bool:
        expires = self._tokens.pop(token, 0.0)
        return expires > time.time()

    def register(self, device_id: str, name: str, model: str, ip: str) -> str:
        """Create a long-lived key for a newly paired phone. Only its hash is stored."""
        key = secrets.token_urlsafe(32)
        now = time.time()
        self.store.upsert(PairedDevice(device_id, name, model, _hash(key), now, now, ip))
        return key

    def verify(self, device_id: str, key: str) -> PairedDevice | None:
        device = self.store.get(device_id)
        if device and hmac.compare_digest(device.key_hash, _hash(key)):
            return device
        return None
