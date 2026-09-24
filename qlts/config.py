"""Đọc cấu hình từ ``st.secrets`` (Streamlit Cloud / .streamlit/secrets.toml)
hoặc biến môi trường."""

import json
import os
import re
from urllib.parse import unquote, urlparse

import streamlit as st


def _secrets() -> dict:
    try:
        return st.secrets.to_dict()
    except Exception:  # không có file secrets
        return {}


def parse_sharepoint_url(url: str) -> dict:
    """Tách link SharePoint/Microsoft Lists thành hostname, site_path và tên list (nếu có).

    Hỗ trợ cả list trong site nhóm (…sharepoint.com/sites/<site>/Lists/<list>/…) và
    list cá nhân trong OneDrive (…-my.sharepoint.com/personal/<user>/Lists/<list>/…).
    """
    parsed = urlparse(url.strip())
    if not parsed.hostname or "sharepoint.com" not in parsed.hostname:
        return {}
    path = unquote(parsed.path)
    match = re.match(r"^(/(?:sites|teams|personal)/[^/]+)(?:/Lists/([^/]+))?", path, re.IGNORECASE)
    if not match:
        return {}
    out = {"hostname": parsed.hostname, "site_path": match.group(1)}
    if match.group(2):
        out["list"] = match.group(2)
    return out


def placeholder_fields() -> list[str]:
    """Các ô trong Secrets còn để giá trị mẫu dạng <...> (chưa thay bằng giá trị thật)."""
    found = []

    def walk(prefix: str, value) -> None:
        if isinstance(value, dict):
            for k, v in value.items():
                walk(f"{prefix}.{k}" if prefix else k, v)
        elif isinstance(value, (list, tuple)):
            for v in value:
                walk(prefix, v)
        elif isinstance(value, str) and re.search(r"<[^<>]+>", value):
            found.append(prefix)

    walk("", _secrets())
    return found


def bridge_config() -> dict | None:
    """Cấu hình cầu nối Power Automate (mục [powerautomate]: flow_url, key)."""
    pa = dict(_secrets().get("powerautomate", {}))
    if pa.get("flow_url") and pa.get("key") and not placeholder_in(pa):
        return pa
    return None


def placeholder_in(value) -> bool:
    return bool(re.search(r"<[^<>]+>", json.dumps(value, ensure_ascii=False)))


def login_mode() -> str:
    """microsoft (st.login) | otp (mã qua email, dùng cầu nối Power Automate) | demo."""
    if auth_configured():
        return "microsoft"
    if bridge_config():
        return "otp"
    return "demo"


def sharepoint_config() -> dict | None:
    """Cấu hình SharePoint, hoặc ``None`` nếu chưa cấu hình (chế độ demo).

    ``mode`` trong kết quả:
    - ``"app"``: có client_secret -> ứng dụng tự truy cập (cần quản trị cấp quyền).
    - ``"delegated"``: dùng quyền của chính người đang đăng nhập (không cần quản trị);
      token lấy từ đăng nhập Microsoft ``[auth]``.
    """
    sp = dict(_secrets().get("sharepoint", {}))
    sp["lists"] = dict(sp.get("lists", {}))
    bridge = bridge_config()
    if bridge:
        # Chế độ cầu nối: flow Power Automate đọc/ghi site đã chọn sẵn trong flow
        if sp.get("list_url"):
            parsed = parse_sharepoint_url(sp["list_url"])
            if parsed.get("list"):
                sp["lists"].setdefault("ThietBi", parsed["list"])
        return {**sp, **bridge, "mode": "bridge", "hostname": "", "site_path": "(site trong flow Power Automate)"}
    # Cách đơn giản nhất: dán link của list thiết bị (hoặc của site) vào list_url / site_url
    for key in ("list_url", "site_url"):
        if sp.get(key):
            parsed = parse_sharepoint_url(sp[key])
            sp.setdefault("hostname", parsed.get("hostname"))
            sp.setdefault("site_path", parsed.get("site_path"))
            if key == "list_url" and parsed.get("list"):
                sp["lists"].setdefault("ThietBi", parsed["list"])
    for key in ("tenant_id", "client_id", "client_secret", "hostname", "site_path"):
        env = os.environ.get(f"SP_{key.upper()}")
        if env:
            sp[key] = env
    if not (sp.get("hostname") and sp.get("site_path")):
        return None
    if all(sp.get(k) for k in ("tenant_id", "client_id", "client_secret")):
        sp["mode"] = "app"
        return sp
    if delegated_available():
        sp["mode"] = "delegated"
        return sp
    return None


def sharepoint_config_problem() -> str | None:
    """Lý do mục [sharepoint] đã khai báo nhưng chưa dùng được (để báo cho người dùng)."""
    sp = _secrets().get("sharepoint")
    pa = _secrets().get("powerautomate")
    if pa and not bridge_config():
        return ("Mục [powerautomate] chưa đủ: cần `flow_url` (URL của bước “When a HTTP request is received”) "
                "và `key` (mã bí mật trùng với flow).")
    if not sp or sharepoint_config():
        return None
    link = sp.get("list_url") or sp.get("site_url")
    if link and not parse_sharepoint_url(link):
        return ("Link SharePoint không đúng dạng. Hãy mở list trên trình duyệt và copy địa chỉ dạng "
                "`https://…sharepoint.com/personal/<tên>/Lists/<tên list>/AllItems.aspx` "
                "(không dùng link “Chia sẻ”).")
    if not (link or (sp.get("hostname") and sp.get("site_path"))):
        return "Thiếu `list_url` (hoặc `hostname` + `site_path`) trong mục [sharepoint]."
    return ("Chưa có cách truy cập SharePoint: cấu hình đăng nhập Microsoft `[auth]` kèm "
            '`expose_tokens = ["id", "access"]`, hoặc `tenant_id/client_id/client_secret` trong [sharepoint].')


def delegated_available() -> bool:
    """Đăng nhập Microsoft đã được cấu hình để trả về access token Microsoft Graph."""
    expose = _secrets().get("auth", {}).get("expose_tokens", [])
    if isinstance(expose, str):
        expose = [expose]
    return auth_configured() and "access" in expose


def auth_configured() -> bool:
    """Đã cấu hình đăng nhập Microsoft (OIDC) cho ``st.login`` chưa."""
    auth = _secrets().get("auth", {})
    return bool(auth.get("client_id") and auth.get("server_metadata_url"))


def admin_emails() -> set[str]:
    """Email luôn có quyền quản trị (dùng để khởi tạo phân quyền lần đầu)."""
    app = _secrets().get("app", {})
    raw = app.get("admin_emails", []) or os.environ.get("ADMIN_EMAILS", "")
    if isinstance(raw, str):
        raw = raw.split(",")
    return {e.strip().lower() for e in raw if e and e.strip()}


def app_setting(key: str, default=None):
    return _secrets().get("app", {}).get(key, default)
