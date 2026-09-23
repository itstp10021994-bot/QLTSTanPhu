"""Tầng lưu trữ dữ liệu.

- ``SharePointStore``: đọc/ghi SharePoint List qua Microsoft Graph API
  (xác thực app-only bằng client credentials).
- ``LocalStore``: lưu vào file JSON cục bộ, dùng cho chế độ demo khi chưa
  cấu hình SharePoint.

Mọi trang đều dùng các hàm ``load()``, ``create()``, ``update()``, ``delete()``
ở cuối file, không gọi trực tiếp store.
"""

from __future__ import annotations

import json
import threading
import time
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import requests
import streamlit as st

from . import schema
from .config import sharepoint_config

GRAPH = "https://graph.microsoft.com/v1.0"


class StorageError(RuntimeError):
    pass


def _to_sp_value(list_name: str, col: str, value):
    """Chuẩn hóa giá trị Python trước khi ghi."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    kind = schema.column_type(list_name, col)
    if kind == "date":
        if isinstance(value, (datetime, pd.Timestamp)):
            value = value.date()
        if isinstance(value, date):
            return value.isoformat() + "T00:00:00Z"
        text = str(value).strip()
        return f"{text[:10]}T00:00:00Z" if text else None
    if kind == "number":
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
    return str(value)


# ---------------------------------------------------------------------------
# SharePoint (Microsoft Graph)
# ---------------------------------------------------------------------------
class TokenExpired(StorageError):
    """Token đăng nhập của người dùng đã hết hạn (chế độ delegated)."""


class SharePointStore:
    def __init__(self, cfg: dict, token_provider=None):
        """``token_provider``: hàm trả về access token Graph. Bỏ trống -> dùng
        client credentials (``client_id``/``client_secret``) của ứng dụng."""
        self.cfg = cfg
        self._token_provider = token_provider or self._app_token_provider(cfg)
        self._site_id: str | None = None
        # Tên list thật trên SharePoint, ví dụ {"ThietBi": "DS_ThietBi"}
        self.list_names: dict = cfg.get("lists", {})
        # Ánh xạ cột: {"ThietBi": {"TenThietBi": "TenTB"}}
        self.column_map: dict = cfg.get("columns", {})

    @staticmethod
    def _app_token_provider(cfg: dict):
        import msal

        try:
            app = msal.ConfidentialClientApplication(
                cfg["client_id"],
                authority=f"https://login.microsoftonline.com/{cfg['tenant_id']}",
                client_credential=cfg["client_secret"],
            )
        except ValueError as exc:
            raise StorageError(f"Cấu hình tenant_id không hợp lệ: {exc}") from exc

        def provider() -> str:
            result = app.acquire_token_for_client(scopes=["https://graph.microsoft.com/.default"])
            if "access_token" not in result:
                raise StorageError(f"Không lấy được token Microsoft Graph: {result.get('error_description')}")
            return result["access_token"]

        return provider

    # -- HTTP --
    def _token(self) -> str:
        return self._token_provider()

    def _request(self, method: str, url: str, **kwargs) -> dict:
        if not url.startswith("http"):
            url = GRAPH + url
        for attempt in range(4):
            resp = requests.request(
                method,
                url,
                headers={"Authorization": f"Bearer {self._token()}", "Content-Type": "application/json"},
                timeout=30,
                **kwargs,
            )
            if resp.status_code in (429, 503) and attempt < 3:
                time.sleep(int(resp.headers.get("Retry-After", 2 ** attempt)))
                continue
            if resp.status_code == 401:
                raise TokenExpired("Phiên đăng nhập Microsoft đã hết hạn, vui lòng đăng nhập lại.")
            if resp.status_code >= 400:
                raise StorageError(f"Graph API lỗi {resp.status_code}: {resp.text[:500]}")
            return resp.json() if resp.content else {}
        raise StorageError("Graph API bị giới hạn (throttling), vui lòng thử lại.")

    @property
    def site_id(self) -> str:
        if not self._site_id:
            path = "/" + self.cfg["site_path"].strip("/")
            self._site_id = self._request("GET", f"/sites/{self.cfg['hostname']}:{path}")["id"]
        return self._site_id

    def _list_url(self, list_name: str) -> str:
        real = self.list_names.get(list_name, list_name)
        return f"/sites/{self.site_id}/lists/{requests.utils.quote(real)}"

    def _to_sp(self, list_name: str, fields: dict) -> dict:
        mapping = self.column_map.get(list_name, {})
        return {mapping.get(k, k): _to_sp_value(list_name, k, v) for k, v in fields.items()}

    def _from_sp(self, list_name: str, fields: dict) -> dict:
        reverse = {v: k for k, v in self.column_map.get(list_name, {}).items()}
        return {reverse.get(k, k): v for k, v in fields.items()}

    # -- CRUD --
    def list_items(self, list_name: str) -> list[dict]:
        url = f"{self._list_url(list_name)}/items?$expand=fields&$top=999"
        rows = []
        while url:
            data = self._request("GET", url)
            for item in data.get("value", []):
                row = self._from_sp(list_name, item.get("fields", {}))
                row["id"] = str(item["id"])
                rows.append(row)
            url = data.get("@odata.nextLink")
        return rows

    def create(self, list_name: str, fields: dict) -> str:
        item = self._request("POST", f"{self._list_url(list_name)}/items", json={"fields": self._to_sp(list_name, fields)})
        return str(item["id"])

    def update(self, list_name: str, item_id: str, fields: dict) -> None:
        self._request("PATCH", f"{self._list_url(list_name)}/items/{item_id}/fields", json=self._to_sp(list_name, fields))

    def delete(self, list_name: str, item_id: str) -> None:
        self._request("DELETE", f"{self._list_url(list_name)}/items/{item_id}")


# ---------------------------------------------------------------------------
# Lưu cục bộ (demo)
# ---------------------------------------------------------------------------
class LocalStore:
    _lock = threading.Lock()

    def __init__(self, path: Path):
        self.path = path
        if not path.exists():
            from .demo_data import build_demo_data

            path.parent.mkdir(parents=True, exist_ok=True)
            self._write(build_demo_data())

    def _read(self) -> dict:
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _write(self, data: dict) -> None:
        self.path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")

    def list_items(self, list_name: str) -> list[dict]:
        with self._lock:
            return self._read().get(list_name, [])

    def create(self, list_name: str, fields: dict) -> str:
        with self._lock:
            data = self._read()
            rows = data.setdefault(list_name, [])
            new_id = str(max((int(r["id"]) for r in rows), default=0) + 1)
            rows.append({**{k: _to_sp_value(list_name, k, v) for k, v in fields.items()}, "id": new_id})
            self._write(data)
            return new_id

    def update(self, list_name: str, item_id: str, fields: dict) -> None:
        with self._lock:
            data = self._read()
            for row in data.get(list_name, []):
                if row["id"] == str(item_id):
                    row.update({k: _to_sp_value(list_name, k, v) for k, v in fields.items()})
            self._write(data)

    def delete(self, list_name: str, item_id: str) -> None:
        with self._lock:
            data = self._read()
            data[list_name] = [r for r in data.get(list_name, []) if r["id"] != str(item_id)]
            self._write(data)


# ---------------------------------------------------------------------------
# API dùng chung cho các trang
# ---------------------------------------------------------------------------
LOCAL_DB = Path(__file__).resolve().parent.parent / "data" / "local_db.json"


def _user_token() -> str:
    """Access token Graph của người đang đăng nhập (chế độ delegated)."""
    token = st.user.tokens.get("access") if st.user.is_logged_in else None
    if not token:
        raise TokenExpired("Chưa có token Microsoft Graph, vui lòng đăng nhập lại.")
    return token


@st.cache_resource
def get_store():
    cfg = sharepoint_config()
    if not cfg:
        return LocalStore(LOCAL_DB)
    if cfg["mode"] == "delegated":
        return SharePointStore(cfg, token_provider=_user_token)
    return SharePointStore(cfg)


def is_demo() -> bool:
    return isinstance(get_store(), LocalStore)


def _cache_scope() -> str:
    """Chế độ delegated: mỗi người dùng một bộ nhớ đệm riêng (theo quyền của họ)."""
    cfg = sharepoint_config()
    if cfg and cfg["mode"] == "delegated" and st.user.is_logged_in:
        return str(st.user.get("email") or st.user.get("preferred_username") or "")
    return ""


def empty_frame(list_name: str) -> pd.DataFrame:
    return pd.DataFrame({c: pd.Series(dtype=str) for c in ["id", *schema.columns_of(list_name)]})


@st.cache_data(ttl=120, show_spinner="Đang tải dữ liệu...")
def _load(list_name: str, scope: str) -> pd.DataFrame:  # noqa: ARG001 - scope là khóa cache
    rows = get_store().list_items(list_name)
    cols = ["id", *schema.columns_of(list_name)]
    df = pd.DataFrame(rows)
    for col in cols:
        if col not in df.columns:
            df[col] = None
    df = df[cols].copy()
    for col in schema.columns_of(list_name):
        kind = schema.column_type(list_name, col)
        if kind == "number":
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
        elif kind == "date":
            df[col] = df[col].map(lambda v: str(v)[:10] if v else "")
        else:
            df[col] = df[col].fillna("").astype(str)
    df["id"] = df["id"].astype(str)
    return df


def load(list_name: str) -> pd.DataFrame:
    """DataFrame các mục của list (cột ``id`` là ID item SharePoint)."""
    return _load(list_name, _cache_scope()).copy()


def refresh() -> None:
    _load.clear()


def create(list_name: str, fields: dict) -> str:
    try:
        return get_store().create(list_name, fields)
    finally:
        refresh()


def update(list_name: str, item_id: str, fields: dict) -> None:
    try:
        get_store().update(list_name, item_id, fields)
    finally:
        refresh()


def delete(list_name: str, item_id: str) -> None:
    try:
        get_store().delete(list_name, item_id)
    finally:
        refresh()
