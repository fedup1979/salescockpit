from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import requests

from sales_cockpit.config import get_settings


FRONT_API_BASE_URL = "https://api2.frontapp.com"


class FrontApiError(Exception):
    pass


@dataclass
class FrontClient:
    api_token: str
    base_url: str = FRONT_API_BASE_URL
    session: Any | None = None
    max_retries: int = 3
    retry_base_delay_seconds: float = 1.0
    max_retry_delay_seconds: float = 15.0

    @classmethod
    def from_settings(cls) -> "FrontClient":
        settings = get_settings()
        if not settings.front_api_token:
            raise FrontApiError("Configure SALES_COCKPIT_FRONT_API_TOKEN.")
        return cls(api_token=settings.front_api_token)

    def list_conversations(
        self,
        query: dict[str, Any] | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"limit": min(limit, 100)}
        if query:
            params["q"] = query
        return self._paginate("/conversations", params=params)

    def search_conversations(self, query: str, limit: int = 100) -> list[dict[str, Any]]:
        safe_query = query.strip()
        if not safe_query:
            return []
        return self._paginate(
            f"/conversations/search/{quote(safe_query)}",
            params={"limit": min(limit, 100)},
        )

    def list_conversation_messages(
        self,
        conversation_id: str,
        sort_order: str = "asc",
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        conversation_id = conversation_id.strip()
        if not conversation_id:
            raise FrontApiError("conversation_id is required.")
        return self._paginate(
            f"/conversations/{conversation_id}/messages",
            params={
                "limit": min(limit, 100),
                "sort_by": "created_at",
                "sort_order": sort_order,
            },
        )

    def _paginate(
        self,
        path_or_url: str,
        params: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        url = self._url(path_or_url)
        next_params = params or {}
        results: list[dict[str, Any]] = []
        while url:
            payload = self._request("GET", url, params=next_params)
            results.extend(payload.get("_results") or [])
            pagination = payload.get("_pagination") or {}
            url = pagination.get("next")
            next_params = {}
        return results

    def _request(self, method: str, url: str, **kwargs: Any) -> dict[str, Any]:
        session = self.session or requests
        headers = kwargs.pop("headers", {})
        headers["Authorization"] = f"Bearer {self.api_token}"
        headers["Accept"] = "application/json"
        response = None
        for attempt in range(self.max_retries + 1):
            try:
                response = session.request(
                    method,
                    self._url(url),
                    headers=headers,
                    timeout=30,
                    **kwargs,
                )
            except requests.RequestException as exc:
                raise FrontApiError(f"Front API inaccessible : {exc}") from exc
            if response.status_code != 429 or attempt >= self.max_retries:
                break
            time.sleep(self._retry_delay_seconds(response, attempt))
        if response is None:
            raise FrontApiError("Front API inaccessible.")
        if response.status_code >= 400:
            raise FrontApiError(f"Front API a refusé la demande : {self._error_detail(response)}")
        try:
            return response.json()
        except ValueError as exc:
            raise FrontApiError("Réponse Front API invalide.") from exc

    def _url(self, path_or_url: str) -> str:
        if path_or_url.startswith("http://") or path_or_url.startswith("https://"):
            return path_or_url
        return f"{self.base_url.rstrip('/')}/{path_or_url.lstrip('/')}"

    def _retry_delay_seconds(self, response: Any, attempt: int) -> float:
        headers = getattr(response, "headers", {}) or {}
        retry_after = headers.get("Retry-After") or headers.get("retry-after")
        if retry_after:
            try:
                return self._bounded_retry_delay(max(float(retry_after), 0.1))
            except ValueError:
                pass
        detail = self._error_detail(response)
        milliseconds_match = re.search(r"retry in (\d+) milliseconds", detail, re.IGNORECASE)
        if milliseconds_match:
            return self._bounded_retry_delay(max(int(milliseconds_match.group(1)) / 1000, 0.1))
        seconds_match = re.search(r"retry in (\d+) seconds", detail, re.IGNORECASE)
        if seconds_match:
            return self._bounded_retry_delay(max(float(seconds_match.group(1)), 0.1))
        return self._bounded_retry_delay(self.retry_base_delay_seconds * (2**attempt))

    def _bounded_retry_delay(self, delay_seconds: float) -> float:
        return min(delay_seconds, self.max_retry_delay_seconds)

    def _error_detail(self, response: Any) -> str:
        detail = getattr(response, "text", "")
        try:
            payload = response.json()
        except ValueError:
            return detail
        if isinstance(payload, dict):
            if payload.get("message") or payload.get("detail"):
                return str(payload.get("message") or payload.get("detail"))
            error = payload.get("_error")
            if isinstance(error, dict):
                return str(error.get("message") or error.get("title") or payload)
        return str(payload)
