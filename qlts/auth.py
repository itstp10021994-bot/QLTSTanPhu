"""Đăng nhập và phân quyền người dùng."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass, field

import streamlit as st

from . import schema, storage
from .config import (admin_emails, app_setting, auth_configured, bridge_config, login_mode, placeholder_fields,
                     sharepoint_config)


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
    try:
        storage.prefetch()  # tải song song mọi list một lần (nhanh hơn nhiều khi đi qua Power Automate)
        pq = storage.load(schema.PHAN_QUYEN)
        phong = storage.load(schema.PHONG)
    except storage.TokenExpired:
        raise
    except storage.StorageError as exc:
        # Thường gặp lần đầu khi chưa tạo list: vẫn cho quản trị vào trang "Kết nối SharePoint"
        st.session_state["startup_error"] = str(exc)
        pq = storage.empty_frame(schema.PHAN_QUYEN)
        phong = storage.empty_frame(schema.PHONG)
    else:
        st.session_state.pop("startup_error", None)
    mine = pq[pq["Title"].str.strip().str.lower() == email]
    roles = {r for r in mine["VaiTro"] if r}
    if email in admin_emails():
        roles.add(schema.ROLE_ADMIN)
    name = next((n for n in mine["HoTen"] if n), "")
    if not name:
        managed = phong[phong["NguoiQuanLy"].str.strip().str.lower() == email]
        name = next((n for n in managed["TenNguoiQuanLy"] if n), "")
    chuc_danh = next((c for c in mine["ChucDanh"] if c), "")
    if not chuc_danh:
        chuc_danh = ", ".join(sorted(roles)) if roles else "Người dùng"
    return CurrentUser(email=email, name=name or fallback_name or email, roles=roles, chuc_danh=chuc_danh)


def _login_screen_microsoft() -> None:
    st.markdown("### Đăng nhập")
    st.write("Vui lòng đăng nhập bằng tài khoản Microsoft 365 của trường.")
    pending = placeholder_fields()
    if pending:
        st.error(
            "Secrets còn giá trị mẫu dạng `<...>` chưa thay bằng giá trị thật: "
            + ", ".join(f"`{p}`" for p in pending)
            + ". Vào Streamlit → Manage app → Settings → Secrets để sửa, nếu không sẽ không đăng nhập được.",
            icon=":material/error:",
        )
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
    tb = storage.load(schema.THIET_BI)
    options = sorted((set(pq["Title"]) | set(phong["NguoiQuanLy"]) | set(tb["QuanLyPhong"]) | admin_emails()) - {""})
    with st.form("demo_login"):
        email = st.selectbox("Chọn tài khoản", options, index=None, placeholder="Chọn email...")
        other = st.text_input("Hoặc nhập email khác")
        if st.form_submit_button("Đăng nhập", type="primary"):
            chosen = (other or email or "").strip()
            if chosen:
                st.session_state["demo_email"] = chosen.lower()
                st.rerun()
            st.error("Vui lòng chọn hoặc nhập email.")


def access_token_expired() -> bool:
    """Chế độ delegated: token Graph trong cookie đăng nhập đã (sắp) hết hạn chưa."""
    token = st.user.tokens.get("access")
    if not token:
        return True
    try:
        payload = token.split(".")[1]
        claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        return claims.get("exp", 0) < time.time() + 60
    except (IndexError, ValueError):
        return False  # token không phải JWT: để Graph tự báo lỗi 401


def relogin_screen(message: str = "Phiên làm việc với SharePoint đã hết hạn.") -> None:
    st.warning(message + " Vui lòng đăng nhập lại để tiếp tục.")
    if st.button("Đăng nhập lại", type="primary", icon=":material/login:"):
        st.login()


# ---------------------------------------------------------------------------
# Đăng nhập bằng mã gửi qua email (chế độ cầu nối Power Automate, không cần App registration)
# ---------------------------------------------------------------------------
OTP_TTL = 600  # giây
OTP_COOLDOWN = 60
OTP_MAX_TRIES = 5
SESSION_PARAM = "s"  # cách cũ (token trên URL) – vẫn nhận để link/dấu trang cũ còn dùng được
SESSION_COOKIE = "qlts_session"


def _session_secret() -> bytes:
    return (str(app_setting("session_secret", "")) or bridge_config()["key"] + "|qlts-session").encode()


def _sign(payload: str) -> str:
    return hmac.new(_session_secret(), payload.encode(), hashlib.sha256).hexdigest()[:40]


def make_session_token(email: str) -> str:
    days = float(app_setting("session_days", 7))
    payload = f"{email}|{int(time.time() + days * 86400)}"
    return base64.urlsafe_b64encode(payload.encode()).decode().rstrip("=") + "." + _sign(payload)


def read_session_token(token: str) -> str | None:
    try:
        raw, sig = token.split(".", 1)
        payload = base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)).decode()
        email, exp = payload.rsplit("|", 1)
    except (ValueError, UnicodeDecodeError):
        return None
    if not hmac.compare_digest(sig, _sign(payload)) or int(exp) < time.time():
        return None
    return email


def known_emails() -> set[str]:
    """Email được phép đăng nhập: có trong Phân quyền, danh mục phòng, cột Quản lý phòng, hoặc admin_emails."""
    emails = set(admin_emails())
    try:
        storage.prefetch([schema.PHAN_QUYEN, schema.PHONG, schema.THIET_BI])
        emails |= set(storage.load(schema.PHAN_QUYEN)["Title"].str.strip().str.lower())
        emails |= set(storage.load(schema.PHONG)["NguoiQuanLy"].str.strip().str.lower())
        emails |= set(storage.load(schema.THIET_BI)["QuanLyPhong"].str.strip().str.lower())
    except storage.StorageError:
        pass
    return {e for e in emails if "@" in e}


def _hash_code(email: str, code: str) -> str:
    return hmac.new(_session_secret(), f"{email}|{code}".encode(), hashlib.sha256).hexdigest()


def _login_screen_otp() -> None:
    st.markdown("### Đăng nhập")
    st.write("Nhập email trường của bạn, ứng dụng sẽ gửi **mã đăng nhập 6 số** vào hộp thư.")
    pending = st.session_state.get("otp")

    with st.form("otp_email"):
        email = st.text_input("Email", value=pending["email"] if pending else "",
                              placeholder="ten@igcschool.edu.vn").strip().lower()
        send = st.form_submit_button("Gửi mã", icon=":material/mail:")
    if send:
        if "@" not in email:
            st.error("Email không hợp lệ.")
        elif pending and pending["email"] == email and time.time() - pending["sent_at"] < OTP_COOLDOWN:
            st.warning(f"Vui lòng chờ {OTP_COOLDOWN - int(time.time() - pending['sent_at'])} giây rồi gửi lại.")
        elif email not in known_emails():
            st.error("Email này chưa được cấp quyền sử dụng ứng dụng. Liên hệ quản trị viên.")
        else:
            code = f"{secrets.randbelow(10**6):06d}"
            try:
                # Tạo kết nối mới từ Secrets (không dùng kết nối đã lưu đệm – có thể là của chế độ demo cũ)
                storage.BridgeStore(bridge_config()).send_mail(
                    email, f"Mã đăng nhập Ứng dụng quản lý thiết bị: {code}",
                    f"<p>Mã đăng nhập của bạn là <b style='font-size:20px'>{code}</b>.</p>"
                    f"<p>Mã có hiệu lực {OTP_TTL // 60} phút. Nếu bạn không yêu cầu, hãy bỏ qua email này.</p>",
                )
            except Exception as exc:  # hiện lỗi dễ hiểu thay vì màn hình lỗi của Streamlit
                st.error(f"Không gửi được email: {exc}")
            else:
                st.session_state["otp"] = pending = {
                    "email": email, "hash": _hash_code(email, code), "exp": time.time() + OTP_TTL,
                    "sent_at": time.time(), "tries": 0,
                }
                st.success(f"Đã gửi mã tới {email}. Kiểm tra hộp thư (cả mục Spam/Junk).")

    if not pending:
        return
    with st.form("otp_code"):
        code = st.text_input("Mã 6 số", max_chars=6).strip()
        ok = st.form_submit_button("Đăng nhập", type="primary", icon=":material/login:")
    if ok:
        if time.time() > pending["exp"]:
            st.error("Mã đã hết hạn, vui lòng gửi mã mới.")
        elif pending["tries"] >= OTP_MAX_TRIES:
            st.error("Nhập sai quá nhiều lần, vui lòng gửi mã mới.")
        elif not hmac.compare_digest(_hash_code(pending["email"], code), pending["hash"]):
            pending["tries"] += 1
            st.error(f"Mã không đúng (còn {OTP_MAX_TRIES - pending['tries']} lần thử).")
        else:
            st.session_state.pop("otp", None)
            st.session_state.pop("logged_out", None)
            st.session_state["session_token"] = make_session_token(pending["email"])
            st.rerun()


_STORE_JS = """
export default function({ data, setStateValue }) {
  const K = "qlts_session";
  const d = data || {};
  const secure = location.protocol === "https:" ? "; Secure" : "";
  const put = (v, age) => { document.cookie = K + "=" + v + "; path=/; max-age=" + age + "; SameSite=Lax" + secure; };
  if (d.clear) {
    try { localStorage.removeItem(K); } catch (e) {}
    put("", 0);
    return;
  }
  if (d.write) {
    try { localStorage.setItem(K, d.write); } catch (e) {}
    put(d.write, d.max_age);
    return;
  }
  let v = "";
  try { v = localStorage.getItem(K) || ""; } catch (e) {}
  if (!v) {
    const m = document.cookie.match(/(?:^|; )qlts_session=([^;]*)/);
    v = m ? m[1] : "";
  }
  setStateValue("token", v);
}
"""
_session_store = st.components.v2.component("qlts_session_store", js=_STORE_JS)


def _browser_store(data: dict) -> str | None:
    """Đọc/ghi token phiên ở trình duyệt (localStorage + cookie) qua một component JS nhỏ.

    Trả ``None`` khi trình duyệt chưa báo về (lần chạy đầu tiên của phiên), ``""`` nếu không có token.
    """
    res = _session_store(key="qlts_session_store", data=data, default={"token": None},
                         on_token_change=lambda: None)
    return getattr(res, "token", None)


def _otp_user() -> CurrentUser | None:
    logged_out = bool(st.session_state.get("logged_out"))
    token = st.session_state.get("session_token", "")
    if SESSION_PARAM in st.query_params:  # link cũ có ?s=
        token = token or st.query_params[SESSION_PARAM]
        del st.query_params[SESSION_PARAM]  # không để token trên thanh địa chỉ (tránh lộ khi chia sẻ link)
    if token and read_session_token(token):
        if st.session_state.get("stored_token") != token:
            # Lưu ở trình duyệt: tải lại trang / mở lại trình duyệt vẫn còn đăng nhập
            _browser_store({"write": token, "max_age": int(float(app_setting("session_days", 7)) * 86400)})
            st.session_state["stored_token"] = token
        st.session_state["session_token"] = token
        return _build_user(read_session_token(token))

    st.session_state.pop("session_token", None)
    if logged_out:
        # Sau khi đăng xuất bỏ qua token cũ (kể cả st.context.cookies – chỉ đọc lúc mở kết nối)
        _browser_store({"clear": True})
        _login_screen_otp()
        return None
    stored = _browser_store({})
    token = stored or st.context.cookies.get(SESSION_COOKIE, "")
    email = read_session_token(token) if token else None
    if email:
        st.session_state["session_token"] = st.session_state["stored_token"] = token
        return _build_user(email)
    if stored is None:
        st.caption("Đang kiểm tra phiên đăng nhập đã lưu...")
    _login_screen_otp()
    return None


def current_user() -> CurrentUser | None:
    """Người dùng hiện tại; ``None`` nếu chưa đăng nhập (màn hình đăng nhập đã được vẽ)."""
    if auth_configured():
        if not st.user.is_logged_in:
            _login_screen_microsoft()
            return None
        cfg = sharepoint_config()
        if cfg and cfg["mode"] == "delegated" and access_token_expired():
            relogin_screen()
            return None
        email = st.user.get("email") or st.user.get("preferred_username") or ""
        return _build_user(email, st.user.get("name") or "")

    if login_mode() == "otp":
        return _otp_user()

    email = st.session_state.get("demo_email")
    if not email:
        _login_screen_demo()
        return None
    return _build_user(email)


def logout() -> None:
    if auth_configured():
        st.logout()
    elif login_mode() == "otp":
        st.query_params.pop(SESSION_PARAM, None)
        for k in ("session_token", "stored_token"):
            st.session_state.pop(k, None)
        st.session_state["logged_out"] = True  # màn hình đăng nhập sẽ xóa cookie
        st.rerun()
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
