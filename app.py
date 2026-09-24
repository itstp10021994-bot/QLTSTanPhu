"""ỨNG DỤNG QUẢN LÝ THIẾT BỊ – Trường TH-THCS-THPT Tân Phú.

Chạy:  streamlit run app.py
"""

import streamlit as st

from qlts import auth, storage, ui
from qlts.schema import ROLE_BGH, ROLE_KIEMKE, ROLE_QLTS

st.set_page_config(page_title="Quản lý thiết bị", page_icon=":material/inventory_2:", layout="wide")

logo = ui.logo_path()
if logo:
    st.logo(logo, size="large")

try:
    user = auth.current_user()
except storage.TokenExpired:
    auth.relogin_screen()
    st.stop()
except storage.StorageError as exc:
    st.error(f"Không kết nối được SharePoint: {exc}")
    st.stop()

if user is None:
    ui.footer()
    st.stop()

st.session_state["user"] = user


def page(path: str, title: str, icon: str) -> st.Page:
    return st.Page(f"views/{path}", title=title, icon=icon)


home = st.Page("views/home.py", title="Trang chủ", icon=":material/home:", default=True)
sections: dict[str, list[st.Page]] = {"": [home]}

if user.has_any(ROLE_QLTS):
    sections["Ban quản lý tài sản"] = [
        page("danh_sach_tb.py", "Danh sách thiết bị", ":material/table_view:"),
        page("nhap_moi.py", "Nhập mới thiết bị", ":material/edit_square:"),
        page("chinh_sua.py", "Chỉnh sửa thông tin thiết bị", ":material/settings:"),
        page("dieu_chuyen.py", "Điều chuyển thiết bị", ":material/swap_horiz:"),
    ]
if user.has_any(ROLE_KIEMKE):
    sections["Ban kiểm kê"] = [page("kiem_ke.py", "Kiểm kê", ":material/fact_check:")]
sections["Người dùng"] = [
    page("phong_quan_ly.py", "Danh sách Phòng đang quản lý", ":material/meeting_room:"),
    page("kiem_ke_phong.py", "Kiểm kê", ":material/search:"),
]
if user.has_any(ROLE_BGH, ROLE_QLTS):
    sections["Báo cáo"] = [page("bao_cao.py", "Báo cáo tổng quan BGH", ":material/bar_chart:")]
if user.is_admin:
    sections["Phân quyền"] = [
        page("phan_quyen_admin.py", "Phân quyền admin", ":material/admin_panel_settings:"),
        page("phan_quyen_phong.py", "Phân quyền quản lý phòng", ":material/manage_accounts:"),
        page("xuat_nhap.py", "Xuất / nhập biểu mẫu", ":material/import_export:"),
        page("khoi_tao_sharepoint.py", "Kết nối SharePoint", ":material/lan:"),
    ]

nav = st.navigation(sections, expanded=True)  # luôn hiện đủ menu (mặc định chỉ hiện 10 mục)

with st.sidebar:
    st.divider()
    st.caption(f"Đăng nhập: **{user.email}**")
    c1, c2 = st.columns(2)
    if c1.button("Làm mới", icon=":material/refresh:", width="stretch",
                 help="Tải lại dữ liệu và dò lại cột SharePoint (sau khi sửa list trên SharePoint)."):
        storage.refresh(schema_too=True)
        st.rerun()
    if c2.button("Đăng xuất", icon=":material/logout:", width="stretch"):
        auth.logout()

ui.header(user.name)
if st.session_state.get("startup_error"):
    st.warning(
        "Chưa đọc được dữ liệu phân quyền từ SharePoint. Nếu đây là lần đầu, quản trị viên hãy vào "
        "**Phân quyền → Kết nối SharePoint** để kiểm tra và tạo list.  \n" + st.session_state["startup_error"][:300]
    )
ui.show_flash()
try:
    nav.run()
except storage.TokenExpired:
    auth.relogin_screen()
except storage.StorageError as exc:
    st.error(f"Lỗi khi làm việc với SharePoint: {exc}")
ui.footer()
