"""Ephemeral test PKI for Phase 8 mTLS loopback harness (cryptography only).

Generates CA / server / client material under a temporary directory.
Never commit private keys. Cleanup is the caller's responsibility (tmp_path).
"""

from __future__ import annotations

import datetime as dt
import ssl
from dataclasses import dataclass
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID


@dataclass
class BranchMtLsPkiPaths:
    root: Path
    ca_cert: Path
    ca_key: Path
    server_cert: Path
    server_key: Path
    client_cert: Path
    client_key: Path
    client_fingerprint_sha256: str
    ca_fingerprint_sha256: str


def _write_key(path: Path, key: ec.EllipticCurvePrivateKey) -> None:
    path.write_bytes(
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    path.chmod(0o600)


def _write_cert(path: Path, cert: x509.Certificate) -> None:
    path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    path.chmod(0o644)


def _name(cn: str) -> x509.Name:
    return x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])


def generate_test_pki(
    root: Path,
    *,
    server_sans: list[str] | None = None,
    client_days: int = 30,
    server_days: int = 30,
    not_before_days: int = -1,
    include_client_eku: bool = True,
    server_cn: str = "origin.test.ifilm.local",
) -> BranchMtLsPkiPaths:
    """Create a dedicated CA + server + client chain for loopback mTLS tests."""
    root.mkdir(parents=True, exist_ok=True)
    now = dt.datetime.now(tz=dt.UTC)

    ca_key = ec.generate_private_key(ec.SECP256R1())
    ca_cert = (
        x509.CertificateBuilder()
        .subject_name(_name("iFilm Test CA"))
        .issuer_name(_name("iFilm Test CA"))
        .public_key(ca_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now + dt.timedelta(days=-30))
        .not_valid_after(now + dt.timedelta(days=365))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                key_cert_sign=True,
                crl_sign=True,
                content_commitment=False,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .sign(ca_key, hashes.SHA256())
    )

    server_key = ec.generate_private_key(ec.SECP256R1())
    sans = server_sans or ["localhost", "127.0.0.1"]
    san_list: list[x509.GeneralName] = []
    for item in sans:
        try:
            san_list.append(x509.IPAddress(__import__("ipaddress").ip_address(item)))
        except ValueError:
            san_list.append(x509.DNSName(item))
    server_cert = (
        x509.CertificateBuilder()
        .subject_name(_name(server_cn))
        .issuer_name(ca_cert.subject)
        .public_key(server_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now + dt.timedelta(days=not_before_days))
        .not_valid_after(now + dt.timedelta(days=server_days))
        .add_extension(x509.SubjectAlternativeName(san_list), critical=False)
        .add_extension(
            x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]),
            critical=False,
        )
        .sign(ca_key, hashes.SHA256())
    )

    client_key = ec.generate_private_key(ec.SECP256R1())
    builder = (
        x509.CertificateBuilder()
        .subject_name(_name("branch-node-client"))
        .issuer_name(ca_cert.subject)
        .public_key(client_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now + dt.timedelta(days=not_before_days))
        .not_valid_after(now + dt.timedelta(days=client_days))
    )
    if include_client_eku:
        builder = builder.add_extension(
            x509.ExtendedKeyUsage([ExtendedKeyUsageOID.CLIENT_AUTH]),
            critical=False,
        )
    client_cert = builder.sign(ca_key, hashes.SHA256())

    paths = BranchMtLsPkiPaths(
        root=root,
        ca_cert=root / "ca.pem",
        ca_key=root / "ca.key",
        server_cert=root / "server.crt",
        server_key=root / "server.key",
        client_cert=root / "client.crt",
        client_key=root / "client.key",
        client_fingerprint_sha256=client_cert.fingerprint(hashes.SHA256()).hex(),
        ca_fingerprint_sha256=ca_cert.fingerprint(hashes.SHA256()).hex(),
    )
    _write_key(paths.ca_key, ca_key)
    _write_cert(paths.ca_cert, ca_cert)
    _write_key(paths.server_key, server_key)
    _write_cert(paths.server_cert, server_cert)
    _write_key(paths.client_key, client_key)
    _write_cert(paths.client_cert, client_cert)
    return paths


def build_server_ssl_context(
    pki: BranchMtLsPkiPaths, *, require_client: bool = True
) -> ssl.SSLContext:
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_3
    ctx.load_cert_chain(certfile=str(pki.server_cert), keyfile=str(pki.server_key))
    if require_client:
        ctx.verify_mode = ssl.CERT_REQUIRED
        ctx.load_verify_locations(cafile=str(pki.ca_cert))
    else:
        ctx.verify_mode = ssl.CERT_NONE
    return ctx
