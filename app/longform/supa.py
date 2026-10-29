"""Minimal Supabase REST client for the worker (service role, server-side only)."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

import requests

from app.longform.settings import get_settings


class SupaError(RuntimeError):
    pass


class Supa:
    def __init__(self, url: str | None = None, key: str | None = None) -> None:
        s = get_settings()
        self.url = (url or s.supabase_url).rstrip("/")
        key = key or s.supabase_service_role_key
        if not self.url or not key:
            raise SupaError("SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY are not configured")
        self.session = requests.Session()
        self.session.headers.update({
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        })

    def _check(self, r: requests.Response) -> Any:
        if not r.ok:
            raise SupaError(f"Supabase {r.request.method} failed ({r.status_code}): {r.text[:300]}")
        if not r.content:
            return None
        return r.json()

    def rpc(self, fn: str, params: dict | None = None) -> Any:
        return self._check(self.session.post(f"{self.url}/rest/v1/rpc/{fn}", json=params or {}, timeout=30))

    @staticmethod
    def _filters(match: dict) -> dict:
        return {k: f"eq.{v}" for k, v in match.items()}

    def select(self, table: str, match: dict, columns: str = "*") -> list[dict]:
        params = {"select": columns, **self._filters(match)}
        return self._check(self.session.get(f"{self.url}/rest/v1/{table}", params=params, timeout=30)) or []

    def select_in(self, table: str, column: str, values: list, columns: str = "*") -> list[dict]:
        if not values:
            return []
        joined = ",".join(quote(str(v), safe="-") for v in values)
        params = {"select": columns, column: f"in.({joined})"}
        return self._check(self.session.get(f"{self.url}/rest/v1/{table}", params=params, timeout=30)) or []

    def one(self, table: str, match: dict, columns: str = "*") -> dict:
        rows = self.select(table, match, columns)
        if not rows:
            raise SupaError(f"{table} row not found")
        return rows[0]

    def update(self, table: str, match: dict, values: dict) -> None:
        self._check(self.session.patch(
            f"{self.url}/rest/v1/{table}", params=self._filters(match), json=values,
            headers={"Prefer": "return=minimal"}, timeout=30,
        ))
