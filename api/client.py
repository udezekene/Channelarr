"""Thin HTTP wrapper for the Dispatcharr REST API.

Responsibilities
----------------
- Inject the Bearer token auth header on every authenticated request
- Retry on 5xx server errors (up to max_retries)
- Raise APIException with status code and response body on any non-2xx response
- No business logic — all decisions happen in planner / executor
"""

from __future__ import annotations
import time
import requests
from utils.exceptions import APIException
from api import endpoints


class APIClient:
    def __init__(
        self,
        base_url: str,
        username: str,
        password: str,
        max_retries: int = 3,
        retry_delay: float = 5.0,
    ) -> None:
        self.base_url = base_url.rstrip('/')
        self.username = username
        self.password = password
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self._token: str | None = None

    # ------------------------------------------------------------------ auth

    def authenticate(self) -> None:
        """Fetch a Bearer token and store it. Raises APIException on failure."""
        data = self._request(
            "POST",
            endpoints.AUTH,
            json={"username": self.username, "password": self.password},
            auth=False,
        )
        self._token = data["access"]

    @property
    def _auth_headers(self) -> dict[str, str]:
        if self._token is None:
            self.authenticate()
        return {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    # ---------------------------------------------------------------- public

    def get(self, path: str, params: dict | None = None) -> dict | list:
        return self._request("GET", path, params=params)

    def post(self, path: str, json: dict | None = None) -> dict:
        return self._request("POST", path, json=json)

    def put(self, path: str, json: dict | None = None) -> dict:
        return self._request("PUT", path, json=json)

    def delete(self, path: str) -> None:
        self._request("DELETE", path)

    # --------------------------------------------------------------- private

    def _request(
        self,
        method: str,
        path: str,
        json: dict | None = None,
        params: dict | None = None,
        auth: bool = True,
    ) -> dict | list | None:
        url = f"{self.base_url}{path}"
        headers = self._auth_headers if auth else {"Content-Type": "application/json"}

        for attempt in range(self.max_retries):
            try:
                resp = requests.request(
                    method, url, json=json, params=params, headers=headers, timeout=30
                )

                if resp.status_code >= 500:
                    if attempt < self.max_retries - 1:
                        time.sleep(self.retry_delay)
                        continue
                    raise APIException(
                        f"{method} {path} failed after {self.max_retries} attempts",
                        status_code=resp.status_code,
                        response_text=resp.text,
                    )

                if not resp.ok:
                    raise APIException(
                        f"{method} {path} failed",
                        status_code=resp.status_code,
                        response_text=resp.text,
                    )

                # 204 No Content or empty body
                if resp.status_code == 204 or not resp.content:
                    return None

                return resp.json()

            except requests.exceptions.RequestException as exc:
                if attempt < self.max_retries - 1:
                    time.sleep(self.retry_delay)
                    continue
                raise APIException(f"{method} {path} request error: {exc}") from exc

        # Should not be reachable, but satisfies type checkers
        raise APIException(f"{method} {path} failed after {self.max_retries} attempts")
