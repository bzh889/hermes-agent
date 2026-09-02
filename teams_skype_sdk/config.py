"""Centralized configuration — single source of truth.

All shared constants (SSL, timeouts, timezone) live here.
Other modules import from this file instead of defining their own.
"""

import os
from pathlib import Path

import urllib3

# Project root (parent of src/)
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Token cache path — single source of truth
# Default: ~/.teams-tokens/token_cache.json (user's home folder)
# Override with env var TEAMS_CACHE_PATH for custom locations
_cache_override = os.getenv("TEAMS_CACHE_PATH")
TOKEN_CACHE_PATH = Path(_cache_override) if _cache_override else Path.home() / ".teams-tokens" / "token_cache.json"

# WAM Broker token cache (MSAL SerializableTokenCache)
WAM_CACHE_PATH = Path.home() / ".teams-automation" / "token_cache.bin"

# Auth method: "wam" (default on Windows) or "device_code"
AUTH_METHOD = os.getenv("TEAMS_AUTH_METHOD", "wam")

# SSL verification — enabled at runtime by inject_truststore() in entry points,
# otherwise disabled (corporate proxy with self-signed CA)
VERIFY_SSL = False

# HTTP request timeout: (connect_timeout, read_timeout)
DEFAULT_TIMEOUT = (10, 30)

# Default timezone for calendar / timestamp operations
TIMEZONE = "Asia/Taipei"

def inject_truststore():
    """Inject OS cert store via truststore, enabling SSL verification.

    Call from application entry points (server.py, teams_login.py), not at import time.
    """
    global VERIFY_SSL
    try:
        import truststore
        truststore.inject_into_ssl()
        VERIFY_SSL = True
    except ImportError:
        pass

if not VERIFY_SSL:
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
