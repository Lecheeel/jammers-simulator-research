"""Local test envelope compatible with the *algorithm family* recovered from
the Go simulator.

The executable's package layer was identified as:

* gzip payload compression;
* AES-256-GCM data encryption (chunked framing);
* RSA-OAEP with SHA-256 to wrap a random DEK;
* Ed25519 signature over the canonical envelope bytes;
* SHA-256 digests and HKDF-SHA256 are available in the package layer.

This module deliberately uses a self-describing JSON envelope for local
automation.  It is not an official server package: the official verifier owns
the RSA private key and Ed25519 signing key, so a client-side test key cannot
produce an accepted competition upload.
"""
from __future__ import annotations

import base64
import gzip
import hashlib
import json
import os
from dataclasses import dataclass
from typing import Any, Mapping

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ed25519, padding, rsa
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF


FORMAT = "local-test-envelope-v1"
CHUNK_FORMAT = "aes-256-gcm-chunked"


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _unb64(data: str) -> bytes:
    return base64.b64decode(data.encode("ascii"), validate=True)


def _canonical(obj: Mapping[str, Any]) -> bytes:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


def generate_test_keys() -> dict[str, bytes]:
    """Generate an ephemeral local RSA wrapping key and Ed25519 signing key."""
    rsa_priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    ed_priv = ed25519.Ed25519PrivateKey.generate()
    return {
        "rsa_private_pem": rsa_priv.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ),
        "rsa_public_pem": rsa_priv.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        ),
        "ed25519_private_raw": ed_priv.private_bytes(
            serialization.Encoding.Raw,
            serialization.PrivateFormat.Raw,
            serialization.NoEncryption(),
        ),
        "ed25519_public_raw": ed_priv.public_key().public_bytes(
            serialization.Encoding.Raw,
            serialization.PublicFormat.Raw,
        ),
    }


def _derive_dek(seed: bytes, context: bytes = b"jammers-simulator/local-test") -> bytes:
    # HKDF is included to mirror the recovered key-derivation family while
    # retaining a 32-byte AES-256 key.
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=None,
                info=context).derive(seed)


def encrypt_envelope(payload: bytes | str, *, rsa_public_pem: bytes,
                     ed25519_private_raw: bytes, package_type: str = "behavior-payload-v1",
                     chunk_size: int = 64 * 1024, aad: bytes = b"") -> bytes:
    """Return a local test envelope containing a signed encrypted payload."""
    if isinstance(payload, str):
        payload = payload.encode("utf-8")
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    pub = serialization.load_pem_public_key(rsa_public_pem)
    signer = ed25519.Ed25519PrivateKey.from_private_bytes(ed25519_private_raw)
    compressed = gzip.compress(payload, mtime=0)
    dek = _derive_dek(os.urandom(32))
    nonce_prefix = os.urandom(8)
    aes = AESGCM(dek)
    chunks: list[str] = []
    for index, start in enumerate(range(0, len(compressed), chunk_size)):
        part = compressed[start:start + chunk_size]
        # 96-bit nonce: fixed per-envelope prefix + big-endian chunk index.
        nonce = nonce_prefix + index.to_bytes(4, "big")
        chunk_aad = aad + index.to_bytes(4, "big")
        chunks.append(_b64(aes.encrypt(nonce, part, chunk_aad)))
    if not chunks:  # AES-GCM still needs an authenticated empty frame.
        chunks.append(_b64(aes.encrypt(nonce_prefix + (0).to_bytes(4, "big"), b"", aad)))
    wrapped = pub.encrypt(
        dek,
        padding.OAEP(mgf=padding.MGF1(hashes.SHA256()), algorithm=hashes.SHA256(), label=None),
    )
    body: dict[str, Any] = {
        "format": FORMAT,
        "package_type": package_type,
        "package_envelope_version": 1,
        "compression": "gzip",
        "encryption": CHUNK_FORMAT,
        "kdf": "HKDF-SHA2-256",
        "wrap_algorithm": "RSA-OAEP-SHA256",
        "wrap_key_id": "local-test-wrap",
        "wrapped_dek": _b64(wrapped),
        "nonce_prefix": _b64(nonce_prefix),
        "chunk_size": chunk_size,
        "chunks": chunks,
        "aad_sha256": hashlib.sha256(aad).hexdigest(),
    }
    body["payload_sha256"] = hashlib.sha256(payload).hexdigest()
    body["signature_algorithm"] = "Ed25519"
    body["signature"] = _b64(signer.sign(_canonical(body)))
    return _canonical(body)


def decrypt_envelope(envelope: bytes | str, *, rsa_private_pem: bytes,
                     aad: bytes = b"", verify_public_raw: bytes | None = None) -> bytes:
    """Verify and decrypt a local envelope; raise on any integrity failure."""
    obj = json.loads(envelope.decode("utf-8") if isinstance(envelope, bytes) else envelope)
    if obj.get("format") != FORMAT:
        raise ValueError("unsupported envelope format")
    sig = _unb64(obj.pop("signature"))
    if verify_public_raw is not None:
        ed25519.Ed25519PublicKey.from_public_bytes(verify_public_raw).verify(sig, _canonical(obj))
    if hashlib.sha256(aad).hexdigest() != obj.get("aad_sha256"):
        raise ValueError("AAD digest mismatch")
    priv = serialization.load_pem_private_key(rsa_private_pem, password=None)
    dek = priv.decrypt(
        _unb64(obj["wrapped_dek"]),
        padding.OAEP(mgf=padding.MGF1(hashes.SHA256()), algorithm=hashes.SHA256(), label=None),
    )
    aes = AESGCM(dek)
    prefix = _unb64(obj["nonce_prefix"])
    compressed = bytearray()
    for index, encoded in enumerate(obj["chunks"]):
        nonce = prefix + index.to_bytes(4, "big")
        compressed.extend(aes.decrypt(nonce, _unb64(encoded), aad + index.to_bytes(4, "big")))
    payload = gzip.decompress(bytes(compressed))
    if hashlib.sha256(payload).hexdigest() != obj.get("payload_sha256"):
        raise ValueError("payload digest mismatch")
    return payload


def write_test_keypair(directory: str) -> dict[str, str]:
    """Write a generated keypair to *directory* and return paths."""
    os.makedirs(directory, exist_ok=True)
    keys = generate_test_keys()
    paths: dict[str, str] = {}
    for name, data in keys.items():
        path = os.path.join(directory, name + (".pem" if name.endswith("pem") else ".bin"))
        with open(path, "wb") as fh:
            fh.write(data)
        paths[name] = path
    return paths

