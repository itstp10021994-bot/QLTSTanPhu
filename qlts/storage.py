"""Tầng lưu trữ dữ liệu.

- ``SharePointStore``: đọc/ghi SharePoint List qua Microsoft Graph API. Cột được dò
  tự động theo tên hiển thị (xem ``schema.LISTS``), nên dùng được list có sẵn.
- ``LocalStore``: lưu vào file JSON cục bộ, dùng cho chế độ demo khi chưa
  cấu hình SharePoint.

Mọi trang đều dùng các hàm ``load()``, ``create()``, ``update()``, ``delete()``
ở cuối file, không gọi trực tiếp store.
"""

from __future__ import annotations

import json
import re
import threading
import time
import unicodedata
from datetime import date, datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import requests
import streamlit as st

from . import schema
from .config import app_setting, sharepoint_config

GRAPH = "https://graph.microsoft.com/v1.0"


class StorageError(RuntimeError):
    pass


class TokenExpired(StorageError):
    """Token đăng nhập của người dùng đã hết hạn (chế độ delegated)."""


def _tz() -> ZoneInfo:
    return ZoneInfo(app_setting("timezone", "Asia/Ho_Chi_Minh"))


def _is_blank(value) -> bool:
    return value is None or (isinstance(value, float) and pd.isna(value)) or value == ""


def _as_date(value) -> date | None:
    if _is_blank(value):
        return None
    if isinstance(value, (datetime, pd.Timestamp)):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value).strip()[:10])
    except ValueError:
        return None


def date_to_sp(value) -> str | None:
    """Ngày -> chuỗi UTC SharePoint lưu (0h theo giờ Việt Nam)."""
    d = _as_date(value)
    if d is None:
        return None
    local = datetime(d.year, d.month, d.day, tzinfo=_tz())
    return local.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def date_from_sp(value) -> str:
    """Giá trị ngày đọc từ SharePoint -> 'YYYY-MM-DD' theo giờ Việt Nam.

    SharePoint trả thời điểm UTC (ngày 22/8 lưu thành 2023-08-21T17:00:00Z), nên phải đổi múi giờ.
    Nếu cột là văn bản (vd "8/22/2023") thì giữ nguyên chuỗi.
    """
    if _is_blank(value):
        return ""
    text = str(value).strip()
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return text
    if dt.tzinfo is None:
        return dt.date().isoformat()
    return dt.astimezone(_tz()).date().isoformat()


def _normalize(name: str) -> str:
    text = unicodedata.normalize("NFC", str(name)).strip().lower()
    return re.sub(r"\s+", " ", text)


def _plain_value(list_name: str, col: str, value):
    """Chuẩn hóa giá trị theo kiểu khai báo trong schema (dùng cho LocalStore)."""
    if _is_blank(value):
        return None
    kind = schema.column_type(list_name, col)
    if kind == "date":
        return date_to_sp(value)
    if kind == "number":
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
    return str(value)


# ---------------------------------------------------------------------------
# SharePoint (Microsoft Graph)
# ---------------------------------------------------------------------------
class SharePointStore:
    def __init__(self, cfg: dict, token_provider=None):
        """``token_provider``: hàm trả về access token Graph. Bỏ trống -> dùng
        client credentials (``client_id``/``client_secret``) của ứng dụng."""
        self.cfg = cfg
        self._token_provider = token_provider or self._app_token_provider(cfg)
        self._site_id: str | None = None
        # Tên list thật trên SharePoint, ví dụ {"ThietBi": "Data_Thietbichitiet"}
        self.list_names: dict = cfg.get("lists", {})
        # Ánh xạ cột cố định: {"ThietBi": {"TenThietBi": "TenTB"}} (tên nội bộ hoặc tên hiển thị)
        self.column_map: dict = cfg.get("columns", {})
        self._columns: dict[str, dict] = {}
        self._list_ids: dict[str, str] = {}

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

    def real_list_name(self, list_name: str) -> str:
        return self.list_names.get(list_name) or schema.LISTS[list_name]["sp_list"]

    def _list_url(self, list_name: str) -> str:
        return f"/sites/{self.site_id}/lists/{self.list_id(list_name)}"

    def list_id(self, list_name: str) -> str:
        """ID của list, tìm theo tên hiển thị hoặc theo tên trên đường dẫn (…/Lists/<tên>)."""
        real = self.real_list_name(list_name)
        if real not in self._list_ids:
            data = self._request("GET", f"/sites/{self.site_id}/lists?$select=id,displayName,webUrl&$top=999")
            wanted = _normalize(real)
            for lst in data.get("value", []):
                url_name = requests.utils.unquote(lst.get("webUrl", "").rstrip("/").split("/")[-1])
                if wanted in (_normalize(lst.get("displayName", "")), _normalize(url_name)):
                    self._list_ids[real] = lst["id"]
                    break
            else:
                raise StorageError(f"Không tìm thấy list “{real}” trên site {self.cfg['site_path']}.")
        return self._list_ids[real]

    # -- Dò cột --
    def sp_columns(self, list_name: str) -> list[dict]:
        return self._request("GET", f"{self._list_url(list_name)}/columns")["value"]

    def columns(self, list_name: str) -> dict:
        """Khóa app -> {"name": tên nội bộ, "kind": kiểu SharePoint, "readonly": bool}.
        Cột không tìm thấy thì không có trong kết quả."""
        if list_name in self._columns:
            return self._columns[list_name]
        sp_cols = self.sp_columns(list_name)
        by_name = {c["name"]: c for c in sp_cols}
        by_display = {}
        for c in sp_cols:
            by_display.setdefault(_normalize(c.get("displayName", "")), c)
        overrides = self.column_map.get(list_name, {})
        resolved = {}
        for key, spec in schema.LISTS[list_name]["columns"].items():
            candidates = [overrides.get(key), spec.get("sp"), key, spec["label"]]
            for cand in filter(None, candidates):
                col = by_name.get(cand) or by_display.get(_normalize(cand))
                if col:
                    kind = next((k for k in ("text", "number", "currency", "dateTime", "choice", "boolean",
                                             "personOrGroup", "lookup", "calculated") if k in col), "text")
                    resolved[key] = {
                        "name": col["name"],
                        "kind": kind,
                        "readonly": bool(col.get("readOnly")) or kind in ("personOrGroup", "lookup", "calculated"),
                    }
                    break
        self._columns[list_name] = resolved
        return resolved

    def _encode(self, list_name: str, key: str, value):
        col = self.columns(list_name).get(key)
        if not col or col["readonly"]:
            return None, None
        kind = col["kind"]
        if _is_blank(value):
            return col["name"], None
        if kind == "dateTime":
            return col["name"], date_to_sp(value)
        if kind in ("number", "currency"):
            try:
                return col["name"], float(value)
            except (TypeError, ValueError):
                return col["name"], None
        if kind == "boolean":
            return col["name"], bool(value)
        if schema.column_type(list_name, key) == "date":
            d = _as_date(value)
            return col["name"], d.strftime("%d/%m/%Y") if d else str(value)
        if isinstance(value, float) and value.is_integer():
            value = int(value)
        return col["name"], str(value)

    def _to_sp(self, list_name: str, fields: dict) -> dict:
        out = {}
        for key, value in fields.items():
            name, encoded = self._encode(list_name, key, value)
            if name:
                out[name] = encoded
        return out

    # -- CRUD --
    def list_items(self, list_name: str) -> list[dict]:
        cols = self.columns(list_name)
        select = ",".join(sorted({c["name"] for c in cols.values()} | {"id"}))
        url = f"{self._list_url(list_name)}/items?$expand=fields($select={select})&$top=999"
        reverse = {c["name"]: key for key, c in cols.items()}
        rows = []
        while url:
            data = self._request("GET", url)
            for item in data.get("value", []):
                fields = item.get("fields", {})
                row = {reverse[k]: v for k, v in fields.items() if k in reverse}
                row["id"] = str(item["id"])
                rows.append(row)
            url = data.get("@odata.nextLink")
        return rows

    def create(self, list_name: str, fields: dict) -> str:
        payload = self._to_sp(list_name, fields)
        cols = self.columns(list_name)
        if "Title" not in payload and not any(c["name"] == "Title" for c in cols.values()):
            # Cột Title bắt buộc mặc định nhưng không dùng trong app: điền mã để dễ tra cứu
            payload["Title"] = str(fields.get("MaChiTiet") or next((v for v in fields.values() if v), ""))[:255]
        item = self._request("POST", f"{self._list_url(list_name)}/items", json={"fields": payload})
        return str(item["id"])

    def update(self, list_name: str, item_id: str, fields: dict) -> None:
        payload = self._to_sp(list_name, fields)
        if payload:
            self._request("PATCH", f"{self._list_url(list_name)}/items/{item_id}/fields", json=payload)

    def delete(self, list_name: str, item_id: str) -> None:
        self._request("DELETE", f"{self._list_url(list_name)}/items/{item_id}")


# ---------------------------------------------------------------------------
# Lưu cục bộ (demo)
# ---------------------------------------------------------------------------
class LocalStore:
    _lock = threading.Lock()

    def __init__(self, path: Path):
        self.path = path
        if not path.exists() or schema.THIET_BI not in self._read_safe():
            from .demo_data import build_demo_data

            path.parent.mkdir(parents=True, exist_ok=True)
            self._write(build_demo_data())

    def _read_safe(self) -> dict:
        try:
            data = self._read()
        except (OSError, ValueError):
            return {}
        # dữ liệu demo kiểu cũ (trước khi đổi sang Data_Thietbichitiet) -> tạo lại
        rows = data.get(schema.THIET_BI, [])
        return data if not rows or "MaChiTiet" in rows[0] else {}

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
            rows.append({**{k: _plain_value(list_name, k, v) for k, v in fields.items()}, "id": new_id})
            self._write(data)
            return new_id

    def update(self, list_name: str, item_id: str, fields: dict) -> None:
        with self._lock:
            data = self._read()
            for row in data.get(list_name, []):
                if row["id"] == str(item_id):
                    row.update({k: _plain_value(list_name, k, v) for k, v in fields.items()})
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


def _to_frame(list_name: str, rows: list[dict]) -> pd.DataFrame:
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
            df[col] = df[col].map(date_from_sp)
        else:
            df[col] = df[col].map(lambda v: "" if _is_blank(v) else (
                str(int(v)) if isinstance(v, float) and v.is_integer() else str(v)
            ))
    df["id"] = df["id"].astype(str)
    return df


@st.cache_data(ttl=120, show_spinner="Đang tải dữ liệu...")
def _load(list_name: str, scope: str) -> pd.DataFrame:  # noqa: ARG001 - scope là khóa cache
    return _to_frame(list_name, get_store().list_items(list_name))


def load(list_name: str) -> pd.DataFrame:
    """DataFrame các mục của list (cột ``id`` là ID item SharePoint)."""
    return _load(list_name, _cache_scope()).copy()


def load_fresh(list_name: str) -> pd.DataFrame:
    """Đọc thẳng từ SharePoint, bỏ qua bộ nhớ đệm (dùng khi sinh mã mới)."""
    return _to_frame(list_name, get_store().list_items(list_name))


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
