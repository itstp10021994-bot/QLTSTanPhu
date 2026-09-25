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
COLUMNS_TTL = 900  # giây – dò lại cột SharePoint sau 15 phút (phòng khi list bị sửa)


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
        self._columns_at: dict[str, float] = {}
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
        if list_name in self._columns and time.time() - self._columns_at.get(list_name, 0) < COLUMNS_TTL:
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
        self._columns_at[list_name] = time.time()
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
        try:
            return self._list_items_once(list_name)
        except TokenExpired:
            raise
        except StorageError as exc:
            if "does not exist" not in str(exc) and "không tồn tại" not in str(exc):
                raise
            # Cột vừa bị xóa/đổi tên trên SharePoint: dò lại cột rồi thử lại một lần
            self.forget_schema(list_name)
            return self._list_items_once(list_name)

    def forget_schema(self, list_name: str | None = None) -> None:
        """Quên thông tin cột/list đã dò (để dò lại sau khi sửa list trên SharePoint)."""
        if list_name:
            self._columns.pop(list_name, None)
            self._columns_at.pop(list_name, None)
        else:
            self._columns.clear()
            self._columns_at.clear()
            self._list_ids.clear()
            self._resolved_names.clear()

    def _list_items_once(self, list_name: str) -> list[dict]:
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
                    done = min(len(pending), start + len(chunk))
                    progress(done / max(len(pending), 1), f"{done}/{len(pending)} dòng · {len(errors)} lỗi")
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
    msg = data.get("message")
    if isinstance(msg, str) and "odata.error" in msg:  # lỗi của bước "Send an HTTP request to SharePoint"
        try:
            inner = json.loads(msg[msg.index("{"):msg.rindex("}") + 1])
            return _error_text(inner)
        except ValueError:
            return msg.split("\r\n")[0][:300]
    err = data.get("odata.error") or data.get("error") or data.get("raw") or msg or ""
    if isinstance(err, dict):
        msg = err.get("message", "")
        return msg.get("value", "") if isinstance(msg, dict) else str(msg)
    return str(err)


class BridgeStore(SharePointStore):
    """Đọc/ghi SharePoint REST qua một flow Power Automate (HTTP trigger -> Send an HTTP request to SharePoint).

    App gửi {"key", "action": "sp", "method", "uri", "body"}; flow trả về status + body của SharePoint.
    """

    PARALLEL = 6  # số yêu cầu gửi đồng thời khi ghi hàng loạt
    STOP_AFTER = 10  # dừng ghi hàng loạt sau chừng này lỗi liên tiếp

    def __init__(self, cfg: dict):
        super().__init__(cfg, token_provider=lambda: "")
        self._index: tuple[float, list] | None = None
        self._index_lock = threading.Lock()
        self.flow_url = cfg["flow_url"]
        self.key = cfg["key"]

    # -- gọi flow --
    def _call(self, payload: dict, timeout: int = 75):
        body = {"key": self.key, **payload}
        write = payload.get("method") in ("POST", "PATCH", "DELETE", "MERGE")
        timed_out = 0
        for attempt in range(4):
            try:
                resp = requests.post(self.flow_url, json=body, timeout=90 if write else timeout)
            except requests.Timeout as exc:
                raise StorageError("flow Power Automate không phản hồi (quá thời gian chờ). Mở flow QLTB-API → "
                                   "Run history: nếu có nhiều lần chạy đang 'Running' thì hủy (Cancel) chúng, "
                                   "đợi 1–2 phút rồi bấm Làm mới.") from exc
            except requests.RequestException as exc:
                raise StorageError(f"Không gọi được flow Power Automate: {exc}") from exc
            if resp.status_code in (502, 504):
                # Flow quá thời gian / không trả lời: chỉ thử lại 1 lần để không treo lâu
                timed_out += 1
                if timed_out < 2 and attempt < 3:
                    time.sleep(2)
                    continue
                break
            if resp.status_code in (429, 503) and attempt < 3:  # bị giới hạn tốc độ: chờ rồi thử lại
                try:
                    wait = int(resp.headers.get("Retry-After", 0)) or 2 ** (attempt + 1)
                except ValueError:
                    wait = 2 ** (attempt + 1)
                time.sleep(min(wait, 30))
                continue
            break
        try:
            data = resp.json() if resp.content else {}
        except ValueError:
            data = {"raw": resp.text[:500]}
        if resp.status_code >= 400:
            msg = _error_text(data)
            if "trigger is not enabled" in msg or "state 'Disabled'" in msg or "state 'Suspended'" in msg:
                msg = ("flow QLTB-API đang TẮT. Vào make.powerautomate.com → My flows → QLTB-API → bấm "
                       "Turn on (Bật), rồi bấm Làm mới trong app. (Chi tiết: " + msg[:200] + ")")
            if resp.status_code in (502, 504) and not msg:
                msg = ("flow không trả lời kịp (quá thời gian) – mở Run history của flow QLTB-API để xem bước "
                       "'Send an HTTP request to SharePoint' báo lỗi gì.")
            if resp.status_code == 403 and (not msg or msg == "forbidden"):
                msg = "flow từ chối – kiểm tra `key` trong Secrets trùng với mã trong flow."
            raise StorageError(f"SharePoint (qua Power Automate) lỗi {resp.status_code}: {msg or str(data)[:300]}")
        return data

    def rest(self, method: str, uri: str, body: dict | None = None):
        return self._call({"action": "sp", "method": method, "uri": uri, "body": body or {}})

    def site_users(self) -> list[dict]:
        """Người dùng của site SharePoint (email + họ tên)."""
        data = self.rest("GET", "_api/web/siteusers?$select=Title,Email,PrincipalType&$filter=PrincipalType eq 1")
        return [{"email": u.get("Email", ""), "name": u.get("Title", "")} for u in data.get("value", [])]

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
        lists = self._lists_index()
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

    def _lists_index(self) -> list[dict]:
        """Danh sách các list của site – gọi flow MỘT lần rồi dùng lại cho mọi list."""
        with self._index_lock:
            if self._index and time.time() - self._index[0] < COLUMNS_TTL:
                return self._index[1]
            data = self.rest("GET", "_api/web/lists?$select=Id,Title,Hidden,RootFolder/ServerRelativeUrl"
                                    "&$expand=RootFolder&$filter=Hidden eq false")
            self._index = (time.time(), data.get("value", []))
            return self._index[1]

    def forget_schema(self, list_name: str | None = None) -> None:
        super().forget_schema(list_name)
        if list_name is None:
            self._index = None

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
    def _list_items_once(self, list_name: str) -> list[dict]:
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

        errors, done, streak, stopped = [], 0, 0, False
        with ThreadPoolExecutor(max_workers=self.PARALLEL) as pool:
            futures = {pool.submit(run, op): i for i, op in enumerate(ops)}
            for fut in as_completed(futures):
                if fut.cancelled():
                    continue
                done += 1
                exc = fut.exception()
                if exc:
                    errors.append(f"Dòng {futures[fut] + 1}: {exc}")
                    streak += 1
                else:
                    streak = 0
                if streak >= self.STOP_AFTER and not stopped:
                    # Lỗi liên tiếp (flow tắt, hết kết nối, sai cột...): dừng thay vì chờ hết mọi dòng
                    stopped = True
                    left = sum(f.cancel() for f in futures)
                    errors.append(f"Đã DỪNG sau {streak} lỗi liên tiếp; {left} dòng chưa ghi. Sửa lỗi rồi nhập lại "
                                  "(các dòng đã ghi sẽ được nhận là 'không đổi').")
                if progress:
                    last = f" – lỗi gần nhất: {errors[-1][:220]}" if errors else ""
                    progress(done / len(ops), f"{done}/{len(ops)} dòng · {len(errors)} lỗi{last}")
        return sorted(errors, key=lambda e: (not e.startswith("Đã DỪNG"), e))


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
                progress((i + 1) / len(ops), f"{i + 1}/{len(ops)} dòng")
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


# ---------------------------------------------------------------------------
# Bộ nhớ đệm dữ liệu (dùng chung cho mọi người dùng của app)
# ---------------------------------------------------------------------------
@st.cache_resource
def _data_cache() -> dict:
    return {"lock": threading.Lock(), "data": {}}


def _cache_ttl() -> float:
    """Thời gian giữ dữ liệu (giây). App tự làm mới list khi chính nó ghi; sửa trực tiếp trên
    SharePoint thì bấm "Làm mới". Đổi được bằng [app] cache_minutes trong Secrets."""
    try:
        return float(app_setting("cache_minutes", 10)) * 60
    except (TypeError, ValueError):
        return 600.0


def _cached(key) -> pd.DataFrame | None:
    hit = _data_cache()["data"].get(key)
    if hit and time.time() - hit[0] < _cache_ttl():
        return hit[1]
    return None


def _put(key, df: pd.DataFrame) -> None:
    with _data_cache()["lock"]:
        _data_cache()["data"][key] = (time.time(), df)


def load(list_name: str) -> pd.DataFrame:
    """DataFrame các mục của list (cột ``id`` là ID item SharePoint)."""
    key = (_cache_scope(), list_name)
    df = _cached(key)
    if df is None:
        with st.spinner("Đang tải dữ liệu..."):
            df = _to_frame(list_name, get_store().list_items(list_name))
        _put(key, df)
    return df.copy()


PREFETCH_TIMEOUT = 45  # giây


def prefetch(list_names: list[str] | None = None) -> None:
    """Tải trước nhiều list CÙNG LÚC (song song) – nhanh hơn nhiều so với tải lần lượt
    khi mỗi lần đọc phải chạy flow Power Automate. Lỗi được bỏ qua ở đây (sẽ hiện khi trang đọc list)."""
    cfg = sharepoint_config()
    if not cfg or cfg["mode"] == "delegated":  # delegated cần ngữ cảnh người dùng -> không chạy song song
        return
    scope = _cache_scope()
    stale = [n for n in (list_names or list(schema.LISTS)) if _cached((scope, n)) is None]
    if len(stale) < 2:
        return
    from concurrent.futures import ThreadPoolExecutor, wait

    store = get_store()
    if hasattr(store, "resolve_all"):
        try:
            store.resolve_all()  # tìm ID các list bằng MỘT lần gọi trước khi chạy song song
        except StorageError:
            return
    pool = ThreadPoolExecutor(max_workers=6)
    try:
        with st.spinner("Đang tải dữ liệu..."):
            futures = {pool.submit(store.list_items, name): name for name in stale}
            # Không chờ mãi khi flow chậm/treo: list nào chưa xong thì trang sẽ tự đọc lại (và báo lỗi rõ ràng)
            done, _ = wait(futures, timeout=PREFETCH_TIMEOUT)
            for fut in done:
                if fut.exception() is None:
                    _put((scope, futures[fut]), _to_frame(futures[fut], fut.result()))
    finally:
        pool.shutdown(wait=False, cancel_futures=True)


def load_fresh(list_name: str) -> pd.DataFrame:
    """Đọc thẳng từ SharePoint, bỏ qua bộ nhớ đệm (dùng khi sinh mã mới)."""
    df = _to_frame(list_name, get_store().list_items(list_name))
    _put((_cache_scope(), list_name), df)
    return df.copy()


def refresh(list_name: str | None = None, schema_too: bool = False) -> None:
    """Xóa bộ nhớ đệm: của một list (sau khi ghi) hoặc tất cả; ``schema_too`` = dò lại cột/list."""
    cache = _data_cache()
    with cache["lock"]:
        if list_name is None:
            cache["data"].clear()
        else:
            for key in [k for k in cache["data"] if k[1] == list_name]:
                cache["data"].pop(key, None)
    if schema_too:
        store = get_store()
        if hasattr(store, "forget_schema"):
            store.forget_schema()


def create(list_name: str, fields: dict) -> str:
    try:
        return get_store().create(list_name, fields)
    finally:
        refresh(list_name)


def update(list_name: str, item_id: str, fields: dict) -> None:
    try:
        get_store().update(list_name, item_id, fields)
    finally:
        refresh(list_name)


def delete(list_name: str, item_id: str) -> None:
    try:
        get_store().delete(list_name, item_id)
    finally:
        refresh(list_name)


def writable_columns(list_name: str) -> set[str] | None:
    """Các cột app ghi được trên SharePoint (None = không xác định được / chế độ demo: coi như ghi được hết)."""
    store = get_store()
    if not hasattr(store, "columns"):
        return None
    try:
        return {k for k, c in store.columns(list_name).items() if not c["readonly"]}
    except StorageError:
        return None


def batch(list_name: str, ops: list[tuple], progress=None) -> list[str]:
    """Ghi nhiều thay đổi một lần; trả về danh sách lỗi."""
    if not ops:
        return []
    try:
        return get_store().batch(list_name, ops, progress)
    finally:
        refresh(list_name)
