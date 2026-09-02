"""Token management with auto-refresh for Teams API."""

import json
import os
import threading
import time
from pathlib import Path
from typing import Optional, Union

import requests

from .config import VERIFY_SSL, DEFAULT_TIMEOUT, TOKEN_CACHE_PATH as _DEFAULT_CACHE_PATH
from .utils import retry_with_backoff


class TeamsAuth:
    """Token management with auto-refresh capabilities."""

    CLIENT_ID = os.environ.get(
        "TEAMS_CLIENT_ID", "1fec8e78-bce4-4aaf-ab1b-5451cc387264"
    )
    TENANT = os.environ.get("TEAMS_TENANT_ID", "organizations")
    SKYPE_SCOPE = "https://api.spaces.skype.com/.default offline_access"

    TOKEN_URL = f"https://login.microsoftonline.com/{TENANT}/oauth2/v2.0/token"
    SKYPE_TOKEN_URL = "https://authsvc.teams.microsoft.com/v1.0/authz"

    def __init__(self, cache_path: Optional[Union[str, Path]] = None, verify_ssl: bool = VERIFY_SSL):
        self.cache_path = Path(cache_path) if cache_path is not None else _DEFAULT_CACHE_PATH
        self.verify_ssl = verify_ssl
        self._tokens: Optional[dict] = None
        self._refresh_lock = threading.Lock()

    def load_tokens(self) -> dict:
        """Load tokens from cache file.

        Raises:
            FileNotFoundError: If token cache doesn't exist
            ValueError: If token cache is invalid
        """
        if not self.cache_path.exists():
            raise FileNotFoundError(
                f"Token cache not found at {self.cache_path.resolve()}. "
                "Please run 'python auth_run.py' first to authenticate."
            )

        with open(self.cache_path, "r") as f:
            tokens = json.load(f)

        required_keys = ["access_token", "refresh_token", "skype_token"]
        missing = [k for k in required_keys if k not in tokens]
        if missing:
            raise ValueError(
                f"Token cache is missing required keys: {missing}. "
                "Please run 'python auth_run.py' again."
            )

        self._tokens = tokens
        return tokens

    def save_tokens(self, tokens: dict) -> None:
        """Save tokens to cache file."""
        tokens["saved_at"] = int(time.time())
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.cache_path, "w") as f:
            json.dump(tokens, f, indent=2)
        self._tokens = tokens

    def _is_token_expired(self, tokens: dict, buffer_seconds: int = 300) -> bool:
        """Check if access token is expired or about to expire."""
        now = int(time.time())

        if "expires_at" in tokens:
            return now >= (tokens["expires_at"] - buffer_seconds)

        if "saved_at" in tokens and "expires_in" in tokens:
            expires_at = tokens["saved_at"] + tokens["expires_in"]
            return now >= (expires_at - buffer_seconds)

        return True

    @retry_with_backoff(max_retries=3)
    def _refresh_access_token(self, refresh_token: str) -> dict:
        """Refresh the access token using refresh token."""
        data = {
            "client_id": self.CLIENT_ID,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "scope": self.SKYPE_SCOPE,
        }

        response = requests.post(
            self.TOKEN_URL, data=data,
            verify=self.verify_ssl, timeout=DEFAULT_TIMEOUT,
        )
        response.raise_for_status()
        return response.json()

    @retry_with_backoff(max_retries=3)
    def _get_skype_token(self, access_token: str) -> str:
        """Exchange access token for Skype token."""
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }

        response = requests.post(
            self.SKYPE_TOKEN_URL,
            headers=headers,
            json={},
            verify=self.verify_ssl,
            timeout=DEFAULT_TIMEOUT,
        )
        response.raise_for_status()

        result = response.json()
        return result.get("skypeToken") or result.get("tokens", {}).get("skypeToken")

    def ensure_valid_tokens(self) -> dict:
        """Ensure tokens are loaded and valid, refreshing if needed.

        Uses double-checked locking to prevent redundant refreshes.

        Raises:
            FileNotFoundError: If no token cache exists
            ValueError: If tokens cannot be refreshed
        """
        if self._tokens is None:
            self.load_tokens()

        tokens = self._tokens

        if self._is_token_expired(tokens):
            with self._refresh_lock:
                if self._tokens is not None:
                    tokens = self._tokens
                if self._is_token_expired(tokens):
                    try:
                        new_tokens = self._refresh_access_token(tokens["refresh_token"])
                        skype_token = self._get_skype_token(new_tokens["access_token"])

                        tokens["access_token"] = new_tokens["access_token"]
                        tokens["expires_in"] = new_tokens.get("expires_in", 3600)
                        tokens["skype_token"] = skype_token

                        new_refresh = new_tokens.get("refresh_token")
                        if new_refresh and new_refresh != tokens["refresh_token"]:
                            tokens["refresh_token"] = new_refresh

                        self.save_tokens(tokens)

                    except requests.HTTPError as e:
                        raise ValueError(
                            f"Failed to refresh tokens: {e}. "
                            "Please run 'python auth_run.py' again."
                        )

        return tokens

    @retry_with_backoff(max_retries=3)
    def exchange_for_scope(self, scope: str) -> dict:
        """Thread-safe refresh token exchange for any scope.

        Handles refresh_token rotation atomically. All scope exchanges
        (Graph, IC3, etc.) should go through this single entry point.
        """
        with self._refresh_lock:
            if self._tokens is None:
                self.load_tokens()

            refresh_token = self._tokens["refresh_token"]
            data = {
                "client_id": self.CLIENT_ID,
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "scope": scope,
            }

            response = requests.post(
                self.TOKEN_URL, data=data,
                verify=self.verify_ssl, timeout=DEFAULT_TIMEOUT,
            )
            response.raise_for_status()
            result = response.json()

            new_refresh = result.get("refresh_token")
            if new_refresh and new_refresh != refresh_token:
                self._tokens["refresh_token"] = new_refresh
                self.save_tokens(self._tokens)

            return result

    def get_skype_token(self) -> str:
        """Get a valid Skype token, refreshing if necessary."""
        tokens = self.ensure_valid_tokens()
        return tokens["skype_token"]

    def get_access_token(self) -> str:
        """Get a valid access token, refreshing if necessary."""
        tokens = self.ensure_valid_tokens()
        return tokens["access_token"]

    def clear_cache(self) -> bool:
        """Clear the token cache file."""
        self._tokens = None
        if self.cache_path.exists():
            self.cache_path.unlink()
            return True
        return False

    def cache_exists(self) -> bool:
        """Check if token cache file exists."""
        return self.cache_path.exists()
