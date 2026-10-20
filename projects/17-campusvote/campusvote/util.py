"""Small shared helpers: canonical JSON, hashing, hex, atomic file writes."""

import hashlib
import json
import os
import re
import tempfile
import time

HEX_RE = re.compile(r"^[0-9a-f]+$")


class ValidationError(ValueError):
    """Bad input from a client (HTTP 400)."""


class Conflict(Exception):
    """Request is well-formed but not allowed in the current state (HTTP 409)."""


class NotFound(Exception):
    """Unknown resource (HTTP 404)."""


class Forbidden(Exception):
    """Missing or wrong credentials (HTTP 403)."""


def canonical(obj):
    """Deterministic JSON bytes (sorted keys, no spaces, UTF-8). Mirrored in static/crypto.js."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sha256_hex(data):
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def int_to_hex(x, size_bytes):
    """Fixed-width lowercase hex (2*size_bytes chars), matching I2OSP."""
    return x.to_bytes(size_bytes, "big").hex()


def parse_hex_int(value, max_bytes, name):
    if not isinstance(value, str) or not value or len(value) > 2 * max_bytes or not HEX_RE.match(value):
        raise ValidationError("%s must be lowercase hex (at most %d bytes)" % (name, max_bytes))
    return int(value, 16)


def check_hex(value, length, name):
    if not isinstance(value, str) or len(value) != length or not HEX_RE.match(value):
        raise ValidationError("%s must be %d lowercase hex characters" % (name, length))
    return value


def now():
    return int(time.time())


def iso(ts):
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(int(ts)))


def atomic_write_bytes(path, data):
    d = os.path.dirname(os.path.abspath(path))
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".tmp-", suffix=".json")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.chmod(tmp, 0o644)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def dump_json_bytes(obj):
    return json.dumps(obj, ensure_ascii=False, indent=1).encode("utf-8")


def atomic_write_json(path, obj):
    atomic_write_bytes(path, dump_json_bytes(obj))


def read_json(path, default=None):
    try:
        with open(path, "rb") as f:
            return json.loads(f.read().decode("utf-8"))
    except FileNotFoundError:
        return default
