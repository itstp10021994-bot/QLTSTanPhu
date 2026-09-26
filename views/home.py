import streamlit as st

from qlts import auth, schema, storage, thietbi

user = auth.require()

st.markdown(f"### Xin chào, {user.name} 👋")
st.caption(user.chuc_danh + (" · " + ", ".join(sorted(user.roles)) if user.roles else ""))

tb = storage.load(schema.THIET_BI)
my_rooms = thietbi.rooms_managed_by(user.email)
my_tb = thietbi.active(tb)[lambda d: d["NoiSuDung"].isin(my_rooms)]

m1, m2, m3 = st.columns(3)
m1.metric("Phòng bạn đang quản lý", len(my_rooms))
m2.metric("Thiết bị trong các phòng", f"{len(my_tb):,}".replace(",", "."))
m3.metric("Thiết bị cần xử lý", int(thietbi.needs_attention(my_tb).sum()))

if user.has_any(schema.ROLE_QLTS, schema.ROLE_BGH):
    act = thietbi.active(tb)
    st.markdown("##### Toàn trường")
    a1, a2, a3 = st.columns(3)
    a1.metric("Thiết bị đang sử dụng", f"{len(act):,}".replace(",", "."))
    a2.metric("Số nơi sử dụng", act["NoiSuDung"].nunique())
    a3.metric("Cần kiểm tra / sửa / thanh lý", int(thietbi.needs_attention(act).sum()))

# ---- Lối tắt theo vai trò ----
links = [("views/phong_quan_ly.py", "Phòng tôi quản lý", ":material/meeting_room:", None),
         ("views/kiem_ke_phong.py", "Xác nhận kiểm kê", ":material/verified:", None),
         ("views/danh_sach_tb.py", "Danh sách thiết bị", ":material/table_view:", schema.ROLE_QLTS),
         ("views/nhap_moi.py", "Nhập mới thiết bị", ":material/add_box:", schema.ROLE_QLTS),
         ("views/dieu_chuyen.py", "Điều chuyển", ":material/swap_horiz:", schema.ROLE_QLTS),
         ("views/ban_giao.py", "Bàn giao tài sản", ":material/assignment:", schema.ROLE_QLTS),
         ("views/thanh_ly.py", "Thanh lý tài sản", ":material/recycling:", schema.ROLE_QLTS),
         ("views/kiem_ke.py", "Kiểm kê", ":material/fact_check:", schema.ROLE_KIEMKE),
         ("views/bao_cao.py", "Báo cáo tổng quan", ":material/bar_chart:", schema.ROLE_BGH),
         ("views/phan_quyen_admin.py", "Phân quyền", ":material/admin_panel_settings:", schema.ROLE_ADMIN)]
allowed = [(p, t, i) for p, t, i, role in links
           if role is None or (role == schema.ROLE_ADMIN and user.is_admin) or
           (role == schema.ROLE_BGH and user.has_any(schema.ROLE_BGH, schema.ROLE_QLTS)) or
           (role not in (schema.ROLE_ADMIN, schema.ROLE_BGH) and user.has_any(role))]
st.markdown("##### Truy cập nhanh")
cols = st.columns(4)
for n, (path, title, icon) in enumerate(allowed):
    cols[n % 4].page_link(path, label=title, icon=icon, width="stretch")
