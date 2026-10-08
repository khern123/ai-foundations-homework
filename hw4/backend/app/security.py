"""Password hashing.

New passwords: scrypt (Python standard library), stored as
    scrypt$<n>$<r>$<p>$<salt_b64>$<hash_b64>
Existing course accounts: verified in the course database's format
    pbkdf2_sha256$<salt>$<hex digest>     (PBKDF2-HMAC-SHA256, 120,000 iterations, text salt)
Each hash has its own salt, so equal passwords produce different hashes.
"""

import base64
import hashlib
import hmac
import secrets

N, R, P = 2**14, 8, 1
SALT_BYTES, KEY_BYTES = 16, 32
COURSE_PBKDF2_ITERATIONS = 120_000


def _scrypt(password: str, salt: bytes, n: int, r: int, p: int) -> bytes:
    return hashlib.scrypt(password.encode("utf-8"), salt=salt, n=n, r=r, p=p, dklen=KEY_BYTES)


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(SALT_BYTES)
    key = _scrypt(password, salt, N, R, P)
    b64 = lambda b: base64.b64encode(b).decode("ascii")
    return f"scrypt${N}${R}${P}${b64(salt)}${b64(key)}"


def verify_password(password: str, stored: str) -> bool:
    try:
        parts = stored.split("$")
        if parts[0] == "scrypt" and len(parts) == 6:
            _, n, r, p, salt_b64, key_b64 = parts
            expected = base64.b64decode(key_b64)
            actual = _scrypt(password, base64.b64decode(salt_b64), int(n), int(r), int(p))
        elif parts[0] == "pbkdf2_sha256" and len(parts) == 3:
            _, salt, hex_digest = parts
            expected = bytes.fromhex(hex_digest)
            actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), COURSE_PBKDF2_ITERATIONS)
        else:
            return False
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)


# Used when an email is unknown, so failed logins take the same time either way.
DUMMY_HASH = hash_password(secrets.token_hex(16))
