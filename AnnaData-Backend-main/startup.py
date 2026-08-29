"""
Google Earth Engine initialisation.

Earth Engine backs the soil tool only. It used to be initialised at import time
with a hardcoded POSIX temp path, so a missing key or a Windows host took the
entire API down. It is now optional and lazy: if it cannot initialise, the soil
tool reports itself unavailable and every other feature keeps working.
"""
import json
import os
import tempfile

from config import EE_SERVICE_KEY

_initialized = False
_init_error: str | None = None


def init_earth_engine() -> bool:
    """Initialise Earth Engine once. Returns True if usable."""
    global _initialized, _init_error

    if _initialized:
        return True
    if _init_error is not None:
        return False

    if not EE_SERVICE_KEY:
        _init_error = "EE_SERVICE_KEY not set; soil data disabled"
        print(f"Earth Engine: {_init_error}")
        return False

    try:
        import ee

        key_data = json.loads(EE_SERVICE_KEY)
        service_account = key_data["client_email"]

        # Cross-platform temp path; the old hardcoded /tmp broke on Windows.
        fd, temp_key_path = tempfile.mkstemp(suffix=".json", prefix="ee-key-")
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(key_data, f)
            credentials = ee.ServiceAccountCredentials(service_account, temp_key_path)
            ee.Initialize(credentials)
        finally:
            try:
                os.unlink(temp_key_path)
            except OSError:
                pass

        _initialized = True
        print("Google Earth Engine initialized")
        return True

    except Exception as e:
        _init_error = str(e)
        print(f"Earth Engine initialization failed, soil data disabled: {e}")
        return False


def is_available() -> bool:
    return _initialized


def status() -> str:
    if _initialized:
        return "initialized"
    return _init_error or "not initialized"
