"""Đọc cấu hình từ ``st.secrets`` (Streamlit Cloud / .streamlit/secrets.toml)
hoặc biến môi trường."""

import os

import streamlit as st


def _secrets() -> dict:
    try:
        return st.secrets.to_dict()
    except Exception:  # không có file secrets
        return {}


def sharepoint_config() -> dict | None:
    """Trả về cấu hình SharePoint, hoặc ``None`` nếu chưa cấu hình (chế độ demo)."""
    sp = dict(_secrets().get("sharepoint", {}))
    for key in ("tenant_id", "client_id", "client_secret", "hostname", "site_path"):
        env = os.environ.get(f"SP_{key.upper()}")
        if env:
            sp[key] = env
    required = ("tenant_id", "client_id", "client_secret", "hostname", "site_path")
    if all(sp.get(k) for k in required):
        return sp
    return None


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
