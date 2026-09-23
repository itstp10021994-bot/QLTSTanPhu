"""Đăng nhập và phân quyền người dùng."""

from __future__ import annotations

from dataclasses import dataclass, field

import streamlit as st

from . import schema, storage
from .config import admin_emails, auth_configured


@dataclass
class CurrentUser:
    email: str
    name: str
    roles: set[str] = field(default_factory=set)
    chuc_danh: str = ""

    def has_any(self, *roles: str) -> bool:
        return schema.ROLE_ADMIN in self.roles or bool(self.roles.intersection(roles))

    @property
    def is_admin(self) -> bool:
        return schema.ROLE_ADMIN in self.roles


def _build_user(email: str, fallback_name: str = "") -> CurrentUser:
    email = email.strip().lower()
    pq = storage.load(schema.PHAN_QUYEN)
    mine = pq[pq["Title"].str.strip().str.lower() == email]
    roles = {r for r in mine["VaiTro"] if r}
    if email in admin_emails():
        roles.add(schema.ROLE_ADMIN)
    name = next((n for n in mine["HoTen"] if n), "")
    if not name:
        phong = storage.load(schema.PHONG)
        managed = phong[phong["NguoiQuanLy"].str.strip().str.lower() == email]
        name = next((n for n in managed["TenNguoiQuanLy"] if n), "")
    chuc_danh = next((c for c in mine["ChucDanh"] if c), "")
    if not chuc_danh:
        chuc_danh = ", ".join(sorted(roles)) if roles else "Người dùng"
    return CurrentUser(email=email, name=name or fallback_name or email, roles=roles, chuc_danh=chuc_danh)


def _login_screen_microsoft() -> None:
    st.markdown("### Đăng nhập")
    st.write("Vui lòng đăng nhập bằng tài khoản Microsoft 365 của trường.")
    if st.button("Đăng nhập với Microsoft", type="primary", icon=":material/login:"):
        st.login()


def _login_screen_demo() -> None:
    st.markdown("### Đăng nhập (chế độ demo)")
    st.info(
        "Chưa cấu hình đăng nhập Microsoft nên ứng dụng cho phép chọn tài khoản để thử. "
        "Khi triển khai thật, hãy cấu hình mục `[auth]` trong secrets (xem README)."
    )
    pq = storage.load(schema.PHAN_QUYEN)
    phong = storage.load(schema.PHONG)
    options = sorted((set(pq["Title"]) | set(phong["NguoiQuanLy"]) | admin_emails()) - {""})
    with st.form("demo_login"):
        email = st.selectbox("Chọn tài khoản", options, index=None, placeholder="Chọn email...")
        other = st.text_input("Hoặc nhập email khác")
        if st.form_submit_button("Đăng nhập", type="primary"):
            chosen = (other or email or "").strip()
            if chosen:
                st.session_state["demo_email"] = chosen.lower()
                st.rerun()
            st.error("Vui lòng chọn hoặc nhập email.")


def current_user() -> CurrentUser | None:
    """Người dùng hiện tại; ``None`` nếu chưa đăng nhập (màn hình đăng nhập đã được vẽ)."""
    if auth_configured():
        if not st.user.is_logged_in:
            _login_screen_microsoft()
            return None
        email = st.user.get("email") or st.user.get("preferred_username") or ""
        return _build_user(email, st.user.get("name") or "")

    email = st.session_state.get("demo_email")
    if not email:
        _login_screen_demo()
        return None
    return _build_user(email)


def logout() -> None:
    if auth_configured():
        st.logout()
    else:
        st.session_state.pop("demo_email", None)
        st.rerun()


def require(*roles: str) -> CurrentUser:
    """Dùng đầu mỗi trang: dừng trang nếu người dùng không đủ quyền."""
    user: CurrentUser = st.session_state["user"]
    if roles and not user.has_any(*roles):
        st.error("Bạn không có quyền truy cập chức năng này.")
        st.stop()
    return user
