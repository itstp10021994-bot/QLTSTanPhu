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
    if value is None or (isinstance(value, str) and value == ""):
        return True
    try:
        return bool(pd.isna(value))  # NaN, NaT, pd.NA
    except (TypeError, ValueError):
        return False


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
        self._list_ids: dict[str, str] = {}  # khóa list trong app -> ID list SharePoint
        self._resolved_names: dict[str, str] = {}
        self.list_web_urls: dict[str, str] = {}

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
        """Tên list trên SharePoint: tên đã tìm thấy > khai báo trong secrets > tên mặc định."""
        return (self._resolved_names.get(list_name) or self.list_names.get(list_name)
                or schema.LISTS[list_name]["sp_list"])

    def _list_url(self, list_name: str) -> str:
        return f"/sites/{self.site_id}/lists/{self.list_id(list_name)}"

    def list_id(self, list_name: str) -> str:
        """ID của list, tìm theo tên hiển thị hoặc theo tên trên đường dẫn (…/Lists/<tên>).

        Nếu không khai báo tên trong secrets, thử lần lượt tên mặc định và các tên thay thế
        (vd "2_Phong" – tên khi tạo list từ file biểu mẫu 2_Phong.xlsx).
        """
        if list_name in self._list_ids:
            return self._list_ids[list_name]
        if self.list_names.get(list_name):
            candidates = [self.list_names[list_name]]
        else:
            candidates = [schema.LISTS[list_name]["sp_list"], *schema.LISTS[list_name].get("aliases", [])]
        data = self._request("GET", f"/sites/{self.site_id}/lists?$select=id,displayName,webUrl&$top=999")
        lists = data.get("value", [])
        for cand in candidates:
            wanted = _normalize(cand)
            for lst in lists:
                url_name = requests.utils.unquote(lst.get("webUrl", "").rstrip("/").split("/")[-1])
                if wanted in (_normalize(lst.get("displayName", "")), _normalize(url_name)):
                    self._list_ids[list_name] = lst["id"]
                    self._resolved_names[list_name] = lst.get("displayName") or cand
                    self.list_web_urls[self._resolved_names[list_name]] = lst.get("webUrl", "")
                    return lst["id"]
        raise StorageError(f"Không tìm thấy list “{' / '.join(candidates)}” trên site {self.cfg['site_path']}.")

    def resolve_all(self) -> None:
        """Tìm trước tất cả list (để hiển thị đúng tên thật); bỏ qua list chưa có."""
        for key in schema.LISTS:
            try:
                self.list_id(key)
            except TokenExpired:
                raise
            except StorageError:
                pass

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
        used: set[str] = set()
        for key, spec in schema.LISTS[list_name]["columns"].items():
            # Ưu tiên tên hiển thị (list tạo từ file Excel mẫu có cột "Mã phòng", "Email"... riêng,
            # cột Title mặc định vẫn còn nhưng bỏ trống), sau đó mới tới tên nội bộ / Title.
            candidates = [(overrides.get(key), "any"), (spec["label"], "display"),
                          *((alt, "display") for alt in spec.get("alt", [])), (key, "name"), (spec.get("sp"), "name")]
            for cand, how in candidates:
                if not cand:
                    continue
                if how == "display":
                    col = by_display.get(_normalize(cand))
                elif how == "name":
                    col = by_name.get(cand)
                else:
                    col = by_name.get(cand) or by_display.get(_normalize(cand))
                if col and col["name"] in used:
                    col = None
                if col:
                    kind = next((k for k in ("text", "number", "currency", "dateTime", "choice", "boolean",
                                             "personOrGroup", "lookup", "calculated") if k in col), "text")
                    resolved[key] = {
                        "name": col["name"],
                        "kind": kind,
                        "readonly": bool(col.get("readOnly")) or kind in ("personOrGroup", "lookup", "calculated"),
                    }
                    used.add(col["name"])
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

    def _create_payload(self, list_name: str, fields: dict) -> dict:
        payload = self._to_sp(list_name, fields)
        cols = self.columns(list_name)
        if "Title" not in payload and not any(c["name"] == "Title" for c in cols.values()):
            # Cột Title bắt buộc mặc định nhưng không dùng trong app: điền mã để dễ tra cứu
            payload["Title"] = str(fields.get("MaChiTiet") or next((v for v in fields.values() if v), ""))[:255]
        return payload

    def create(self, list_name: str, fields: dict) -> str:
        item = self._request("POST", f"{self._list_url(list_name)}/items",
                             json={"fields": self._create_payload(list_name, fields)})
        return str(item["id"])

    def batch(self, list_name: str, ops: list[tuple], progress=None) -> list[str]:
        """Ghi nhiều thay đổi bằng Graph $batch (20 yêu cầu / lần).

        ``ops``: ("create", fields) | ("update", id, fields) | ("delete", id).
        Trả về danh sách lỗi (rỗng nếu thành công hết).
        """
        base = self._list_url(list_name)
        requests_ = []
        for i, op in enumerate(ops):
            if op[0] == "create":
                req = {"method": "POST", "url": f"{base}/items", "body": {"fields": self._create_payload(list_name, op[1])}}
            elif op[0] == "update":
                req = {"method": "PATCH", "url": f"{base}/items/{op[1]}/fields", "body": self._to_sp(list_name, op[2])}
            else:
                req = {"method": "DELETE", "url": f"{base}/items/{op[1]}"}
            if "body" in req:
                req["headers"] = {"Content-Type": "application/json"}
            requests_.append({"id": str(i), **req})

        errors: list[str] = []
        pending = requests_
        for attempt in range(4):
            retry = []
            for start in range(0, len(pending), 20):
                chunk = pending[start:start + 20]
                result = self._request("POST", "/$batch", json={"requests": chunk})
                by_id = {r["id"]: r for r in chunk}
                for resp in result.get("responses", []):
                    status = resp.get("status", 500)
                    if status in (429, 503) and attempt < 3:
                        retry.append(by_id[resp["id"]])
                    elif status >= 400:
                        msg = (resp.get("body") or {}).get("error", {}).get("message", "")
                        errors.append(f"Dòng {int(resp['id']) + 1}: lỗi {status} {msg}")
                if progress:
                    progress(min(1.0, (start + len(chunk)) / max(len(pending), 1)))
            if not retry:
                break
            time.sleep(2 ** attempt)
            pending = retry
        return errors

    def update(self, list_name: str, item_id: str, fields: dict) -> None:
        payload = self._to_sp(list_name, fields)
        if payload:
            self._request("PATCH", f"{self._list_url(list_name)}/items/{item_id}/fields", json=payload)

    def delete(self, list_name: str, item_id: str) -> None:
        self._request("DELETE", f"{self._list_url(list_name)}/items/{item_id}")


# ---------------------------------------------------------------------------
# Cầu nối Power Automate (không cần App registration)
# ---------------------------------------------------------------------------
REST_KINDS = {
    "Text": "text", "Note": "text", "Number": "number", "Currency": "currency", "DateTime": "dateTime",
    "Choice": "choice", "MultiChoice": "choice", "Boolean": "boolean", "User": "personOrGroup",
    "UserMulti": "personOrGroup", "Lookup": "lookup", "LookupMulti": "lookup", "Calculated": "calculated",
    "URL": "text", "Integer": "number", "Counter": "number",
}


def _error_text(data) -> str:
    """Lấy thông báo lỗi từ phản hồi SharePoint REST / flow (nhiều dạng khác nhau)."""
    if not isinstance(data, dict):
        return str(data)[:300]
    err = data.get("odata.error") or data.get("error") or data.get("raw") or ""
    if isinstance(err, dict):
        msg = err.get("message", "")
        return msg.get("value", "") if isinstance(msg, dict) else str(msg)
    return str(err)


class BridgeStore(SharePointStore):
    """Đọc/ghi SharePoint REST qua một flow Power Automate (HTTP trigger -> Send an HTTP request to SharePoint).

    App gửi {"key", "action": "sp", "method", "uri", "body"}; flow trả về status + body của SharePoint.
    """

    PARALLEL = 6  # số yêu cầu gửi đồng thời khi ghi hàng loạt

    def __init__(self, cfg: dict):
        super().__init__(cfg, token_provider=lambda: "")
        self.flow_url = cfg["flow_url"]
        self.key = cfg["key"]

    # -- gọi flow --
    def _call(self, payload: dict, timeout: int = 120):
        body = {"key": self.key, **payload}
        for attempt in range(4):
            try:
                resp = requests.post(self.flow_url, json=body, timeout=timeout)
            except requests.RequestException as exc:
                raise StorageError(f"Không gọi được flow Power Automate: {exc}") from exc
            if resp.status_code in (429, 502, 503, 504) and attempt < 3:
                time.sleep(int(resp.headers.get("Retry-After", 2 ** attempt)))
                continue
            break
        try:
            data = resp.json() if resp.content else {}
        except ValueError:
            data = {"raw": resp.text[:500]}
        if resp.status_code >= 400:
            msg = _error_text(data)
            if resp.status_code == 403 and (not msg or msg == "forbidden"):
                msg = "flow từ chối – kiểm tra `key` trong Secrets trùng với mã trong flow."
            raise StorageError(f"SharePoint (qua Power Automate) lỗi {resp.status_code}: {msg or str(data)[:300]}")
        return data

    def rest(self, method: str, uri: str, body: dict | None = None):
        return self._call({"action": "sp", "method": method, "uri": uri, "body": body or {}})

    def send_mail(self, to: str, subject: str, html: str) -> None:
        self._call({"action": "mail", "to": to, "subject": subject, "html": html})

    # -- site / list --
    @property
    def site_id(self) -> str:  # không dùng Graph
        return "bridge"

    def site_info(self) -> dict:
        return self.rest("GET", "_api/web?$select=Title,Url")

    def list_id(self, list_name: str) -> str:
        if list_name in self._list_ids:
            return self._list_ids[list_name]
        if self.list_names.get(list_name):
            candidates = [self.list_names[list_name]]
        else:
            candidates = [schema.LISTS[list_name]["sp_list"], *schema.LISTS[list_name].get("aliases", [])]
        data = self.rest("GET", "_api/web/lists?$select=Id,Title,Hidden,RootFolder/ServerRelativeUrl"
                                "&$expand=RootFolder&$filter=Hidden eq false")
        lists = data.get("value", [])
        for cand in candidates:
            wanted = _normalize(cand)
            for lst in lists:
                url = (lst.get("RootFolder") or {}).get("ServerRelativeUrl", "")
                url_name = requests.utils.unquote(url.rstrip("/").split("/")[-1])
                if wanted in (_normalize(lst.get("Title", "")), _normalize(url_name)):
                    self._list_ids[list_name] = lst["Id"]
                    self._resolved_names[list_name] = lst.get("Title") or cand
                    self.list_web_urls[self._resolved_names[list_name]] = url
                    return lst["Id"]
        raise StorageError(f"Không tìm thấy list “{' / '.join(candidates)}” trên site của flow.")

    def _list_uri(self, list_name: str) -> str:
        return f"_api/web/lists(guid'{self.list_id(list_name)}')"

    def sp_columns(self, list_name: str) -> list[dict]:
        data = self.rest("GET", f"{self._list_uri(list_name)}/fields?$select=InternalName,Title,TypeAsString,"
                                "ReadOnlyField,Hidden&$filter=Hidden eq false")
        cols = []
        for f in data.get("value", []):
            kind = REST_KINDS.get(f.get("TypeAsString", ""), "text")
            cols.append({"name": f["InternalName"], "displayName": f.get("Title", ""), kind: {},
                         "readOnly": bool(f.get("ReadOnlyField")) and f["InternalName"] != "Title"})
        return cols

    # -- CRUD --
    def list_items(self, list_name: str) -> list[dict]:
        cols = {k: c for k, c in self.columns(list_name).items() if c["kind"] not in ("personOrGroup", "lookup")}
        select = ",".join(sorted({c["name"] for c in cols.values()} | {"Id"}))
        uri = f"{self._list_uri(list_name)}/items?$select={select}&$top=5000"
        reverse = {c["name"]: key for key, c in cols.items()}
        rows = []
        while uri:
            data = self.rest("GET", uri)
            for item in data.get("value", []):
                row = {reverse[k]: v for k, v in item.items() if k in reverse}
                row["id"] = str(item["Id"])
                rows.append(row)
            nxt = data.get("odata.nextLink") or data.get("@odata.nextLink") or ""
            uri = "_api/" + nxt.split("/_api/", 1)[1] if "/_api/" in nxt else ""
        return rows

    def create(self, list_name: str, fields: dict) -> str:
        item = self.rest("POST", f"{self._list_uri(list_name)}/items", self._create_payload(list_name, fields))
        return str(item.get("Id") or item.get("ID"))

    def update(self, list_name: str, item_id: str, fields: dict) -> None:
        payload = self._to_sp(list_name, fields)
        if payload:
            self.rest("PATCH", f"{self._list_uri(list_name)}/items({int(item_id)})", payload)

    def delete(self, list_name: str, item_id: str) -> None:
        self.rest("DELETE", f"{self._list_uri(list_name)}/items({int(item_id)})")

    def batch(self, list_name: str, ops: list[tuple], progress=None) -> list[str]:
        from concurrent.futures import ThreadPoolExecutor, as_completed

        self.columns(list_name)  # dò cột một lần trước khi chạy song song

        def run(op):
            if op[0] == "create":
                self.create(list_name, op[1])
            elif op[0] == "update":
                self.update(list_name, op[1], op[2])
            else:
                self.delete(list_name, op[1])

        errors, done = [], 0
        with ThreadPoolExecutor(max_workers=self.PARALLEL) as pool:
            futures = {pool.submit(run, op): i for i, op in enumerate(ops)}
            for fut in as_completed(futures):
                done += 1
                exc = fut.exception()
                if exc:
                    errors.append(f"Dòng {futures[fut] + 1}: {exc}")
                if progress:
                    progress(done / len(ops))
        return sorted(errors)


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
        # dữ liệu demo kiểu cũ -> tạo lại
        rows = data.get(schema.THIET_BI, [])
        if (rows and "MaChiTiet" not in rows[0]) or schema.LOAI_TB not in data:
            return {}
        return data

    def _read(self) -> dict:
        if not self.path.exists():  # file demo bị xóa -> tạo lại dữ liệu mẫu
            from .demo_data import build_demo_data

            self._write(build_demo_data())
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

    def batch(self, list_name: str, ops: list[tuple], progress=None) -> list[str]:
        for i, op in enumerate(ops):
            if op[0] == "create":
                self.create(list_name, op[1])
            elif op[0] == "update":
                self.update(list_name, op[1], op[2])
            else:
                self.delete(list_name, op[1])
            if progress:
                progress((i + 1) / len(ops))
        return []


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


def _config_fingerprint() -> str:
    """Dấu vân tay của cấu hình kết nối: đổi Secrets -> tạo kết nối / bộ nhớ đệm mới."""
    import hashlib

    raw = json.dumps(sharepoint_config() or {}, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def get_store():
    store = _get_store(_config_fingerprint())
    cfg = sharepoint_config()
    expected = {"bridge": BridgeStore}.get(cfg["mode"], SharePointStore) if cfg else LocalStore
    if type(store) is not expected:  # kết nối cũ còn trong bộ nhớ (vd. từ chế độ demo) -> tạo lại
        _get_store.clear()
        store = _get_store(_config_fingerprint())
    return store


@st.cache_resource(max_entries=4)
def _get_store(fingerprint: str):  # noqa: ARG001 - khóa cache theo cấu hình
    cfg = sharepoint_config()
    if not cfg:
        return LocalStore(LOCAL_DB)
    if cfg["mode"] == "bridge":
        return BridgeStore(cfg)
    if cfg["mode"] == "delegated":
        return SharePointStore(cfg, token_provider=_user_token)
    return SharePointStore(cfg)


def is_demo() -> bool:
    return isinstance(get_store(), LocalStore)


def is_bridge() -> bool:
    return isinstance(get_store(), BridgeStore)


def _cache_scope() -> str:
    """Khóa bộ nhớ đệm: theo cấu hình kết nối, và theo người dùng ở chế độ delegated."""
    scope = _config_fingerprint()
    cfg = sharepoint_config()
    if cfg and cfg["mode"] == "delegated" and st.user.is_logged_in:
        scope += "|" + str(st.user.get("email") or st.user.get("preferred_username") or "")
    return scope


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


def batch(list_name: str, ops: list[tuple], progress=None) -> list[str]:
    """Ghi nhiều thay đổi một lần; trả về danh sách lỗi."""
    if not ops:
        return []
    try:
        return get_store().batch(list_name, ops, progress)
    finally:
        refresh()
