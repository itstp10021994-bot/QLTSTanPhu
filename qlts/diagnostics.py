"""Kiểm tra từng bước kết nối SharePoint để chỉ ra bước còn thiếu."""

from __future__ import annotations

import base64
import json
import time

import streamlit as st

from . import schema, storage
from .config import (_secrets, auth_configured, bridge_config, parse_sharepoint_url, placeholder_fields,
                     sharepoint_config)

OK, WARN, FAIL = "✅", "⚠️", "❌"
GRAPH_AUDIENCES = {"00000003-0000-0000-c000-000000000000", "https://graph.microsoft.com"}


def _claims(token: str) -> dict:
    try:
        payload = token.split(".")[1]
        return json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    except (IndexError, ValueError):
        return {}


def config_checks() -> list[tuple[str, str, str]]:
    """Kiểm tra Secrets (không gọi mạng)."""
    sec = _secrets()
    sp, auth = sec.get("sharepoint", {}), sec.get("auth", {})
    out = []
    pending = placeholder_fields()
    if pending:
        out.append((FAIL, "Giá trị mẫu <...> chưa thay", ", ".join(pending)))
    pa = sec.get("powerautomate")
    if pa:
        if bridge_config():
            out.append((OK, "Mục [powerautomate]", "Có flow_url và key → đọc/ghi SharePoint qua flow Power Automate."))
            out.append((OK, "Đăng nhập", "Bằng mã 6 số gửi qua email (flow gửi mail)."))
        else:
            out.append((FAIL, "Mục [powerautomate]", "Thiếu `flow_url` hoặc `key` (hoặc còn giá trị mẫu <...>)."))
        return out
    link = sp.get("list_url") or sp.get("site_url")
    if not sp:
        out.append((FAIL, "Mục [sharepoint] trong Secrets", "Chưa có. Streamlit → Manage app → Settings → Secrets, "
                                                          "thêm `[sharepoint]` với `list_url = \"...\"`."))
    elif link and not parse_sharepoint_url(link):
        out.append((FAIL, "Link list_url", "Sai dạng – cần link mở list trên trình duyệt "
                                           "(…/personal/<tên>/Lists/<tên list>/AllItems.aspx), không dùng link Chia sẻ."))
    elif not (link or (sp.get("hostname") and sp.get("site_path"))):
        out.append((FAIL, "Mục [sharepoint]", "Thiếu `list_url`."))
    else:
        parsed = parse_sharepoint_url(link) if link else {"hostname": sp["hostname"], "site_path": sp["site_path"]}
        out.append((OK, "Mục [sharepoint]", f"Site: https://{parsed['hostname']}{parsed['site_path']}"))

    app_mode = all(sp.get(k) for k in ("tenant_id", "client_id", "client_secret"))
    if app_mode:
        out.append((OK, "Chế độ truy cập", "Quyền ứng dụng (tenant_id/client_id/client_secret trong [sharepoint])."))
        return out
    if not auth_configured():
        out.append((FAIL, "Mục [auth] (đăng nhập Microsoft)",
                    "Chưa có `client_id` / `server_metadata_url` → app chạy DEMO, dữ liệu không lên SharePoint."))
        return out
    missing = [k for k in ("redirect_uri", "cookie_secret", "client_secret") if not auth.get(k)]
    out.append((FAIL if missing else OK, "Mục [auth]",
                f"Thiếu: {', '.join(missing)}" if missing else f"redirect_uri = {auth.get('redirect_uri')}"))
    expose = auth.get("expose_tokens", [])
    expose = [expose] if isinstance(expose, str) else expose
    out.append((OK if "access" in expose else FAIL, "expose_tokens",
                "Có \"access\"." if "access" in expose else
                'Thiếu – thêm `expose_tokens = ["id", "access"]` vào [auth], nếu không app không có quyền ghi SharePoint.'))
    scope = str((auth.get("client_kwargs") or {}).get("scope", ""))
    out.append((OK if "Sites.ReadWrite.All" in scope else FAIL, "Quyền đọc/ghi SharePoint (scope)",
                "Có Sites.ReadWrite.All." if "Sites.ReadWrite.All" in scope else
                'Thiếu – trong [auth] thêm `client_kwargs = { "prompt" = "select_account", "scope" = '
                '"openid profile email offline_access https://graph.microsoft.com/Sites.ReadWrite.All" }`, '
                "rồi Đăng xuất và đăng nhập lại."))
    return out


def login_checks() -> list[tuple[str, str, str]]:
    cfg = sharepoint_config()
    if not cfg or cfg["mode"] != "delegated":
        return []
    if not st.user.is_logged_in:
        return [(FAIL, "Đăng nhập Microsoft", "Chưa đăng nhập bằng Microsoft.")]
    token = st.user.tokens.get("access")
    if not token:
        return [(FAIL, "Token Microsoft Graph", "Không có token – kiểm tra expose_tokens rồi Đăng xuất / đăng nhập lại.")]
    claims = _claims(token)
    out = [(OK, "Đăng nhập Microsoft", str(st.user.get("email") or st.user.get("preferred_username")))]
    if claims:
        aud_ok = claims.get("aud") in GRAPH_AUDIENCES
        scopes = str(claims.get("scp", ""))
        out.append((OK if aud_ok else FAIL, "Token dành cho Microsoft Graph",
                    "Đúng." if aud_ok else "Sai – thiếu scope Graph trong client_kwargs, đăng nhập lại sau khi sửa."))
        out.append((OK if "Sites.ReadWrite.All" in scopes else FAIL, "Quyền trong token",
                    scopes or "(trống)"))
        left = int(claims.get("exp", 0) - time.time())
        out.append((OK if left > 60 else FAIL, "Hạn token", f"còn {left // 60} phút" if left > 60 else
                    "Đã hết hạn – bấm Đăng xuất rồi đăng nhập lại."))
    return out


def sharepoint_checks() -> list[tuple[str, str, str]]:
    store = storage.get_store()
    if storage.is_demo():
        return [(FAIL, "Kết nối SharePoint", "App đang chạy DEMO – sửa các mục ❌ ở trên.")]
    out = []
    try:
        if storage.is_bridge():
            web = store.site_info()
            out.append((OK, "Flow Power Automate → site", f"{web.get('Title', '')} – {web.get('Url', '')}"))
        else:
            site = store._request("GET", f"/sites/{store.site_id}?$select=displayName,webUrl")
            out.append((OK, "Truy cập site", f"{site.get('displayName', '')} – {site.get('webUrl', '')}"))
    except storage.TokenExpired:
        raise
    except storage.StorageError as exc:
        return [(FAIL, "Truy cập site", str(exc)[:400])]
    for key in schema.LISTS:
        try:
            store.list_id(key)
            name = store.real_list_name(key)
            cols = store.columns(key)
            n_all = len(schema.LISTS[key]["columns"])
            status = OK if len(cols) == n_all else WARN
            out.append((status, f"List “{name}”", f"{len(cols)}/{n_all} cột khớp · {store.list_web_urls.get(name, '')}"))
        except storage.TokenExpired:
            raise
        except storage.StorageError:
            name = " / ".join([schema.LISTS[key]["sp_list"], *schema.LISTS[key].get("aliases", [])])
            out.append((FAIL, f"List “{name}”", "Không tìm thấy trên site – tạo list hoặc khai báo tên trong [sharepoint.lists]."))
    return out


def write_test() -> tuple[str, str]:
    """Ghi thử rồi xóa một dòng trong list Phong để kiểm tra quyền ghi."""
    store = storage.get_store()
    try:
        item_id = store.create(schema.PHONG, {"Title": "__KIEM_TRA_KET_NOI__", "TenPhong": "Xóa được"})
        store.delete(schema.PHONG, item_id)
        return OK, "Ghi và xóa thử thành công – app có quyền ghi lên SharePoint."
    except storage.TokenExpired:
        raise
    except storage.StorageError as exc:
        return FAIL, f"Không ghi được: {str(exc)[:400]}"


def mail_test(to: str) -> tuple[str, str]:
    """Gửi thử email qua flow (chế độ cầu nối)."""
    try:
        storage.get_store().send_mail(to, "Kiểm tra kết nối – Ứng dụng quản lý thiết bị",
                                      "<p>Flow Power Automate gửi email thành công.</p>")
        return OK, f"Đã gửi email thử tới {to} – kiểm tra hộp thư."
    except storage.StorageError as exc:
        return FAIL, f"Không gửi được: {str(exc)[:400]}"
