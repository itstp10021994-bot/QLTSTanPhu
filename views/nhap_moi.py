from datetime import date

import streamlit as st

from qlts import auth, schema, storage, ui

auth.require(schema.ROLE_QLTS)
st.subheader("Nhập mới thiết bị")

tb = storage.load(schema.THIET_BI)
labels = ui.room_label_map()
rooms = list(labels)
if not rooms:
    st.warning("Chưa có phòng nào. Hãy tạo phòng ở mục **Phân quyền quản lý phòng** trước.")
    st.stop()

known = tb.drop_duplicates("Title").set_index("Title")["TenThietBi"].to_dict()

with st.form("nhap_moi", clear_on_submit=True):
    c1, c2 = st.columns(2)
    code = c1.text_input("Mã thiết bị *", help="Có thể trùng mã ở các phòng khác nhau (cùng loại thiết bị).")
    name = c2.text_input("Tên thiết bị *", help="Để trống nếu mã đã tồn tại – sẽ lấy tên cũ.")
    c1, c2, c3 = st.columns(3)
    loai = c1.selectbox("Loại thiết bị", schema.LOAI_THIET_BI)
    room = c2.selectbox("Phòng *", rooms, format_func=lambda r: labels.get(r, r))
    tinh_trang = c3.selectbox("Tình trạng", schema.TINH_TRANG)
    c1, c2, c3 = st.columns(3)
    so_luong = c1.number_input("Số lượng *", min_value=1, value=1, step=1)
    dvt = c2.selectbox("Đơn vị tính", schema.DON_VI_TINH)
    nguyen_gia = c3.number_input("Nguyên giá / đơn vị (VNĐ)", min_value=0, value=0, step=100_000)
    c1, c2, c3 = st.columns(3)
    nam = c1.number_input("Năm đưa vào sử dụng", min_value=1990, max_value=2100, value=date.today().year)
    ngay_nhap = c2.date_input("Ngày nhập", value=date.today(), format="DD/MM/YYYY")
    nguon_goc = c3.text_input("Nguồn gốc", placeholder="Ngân sách, tài trợ, xã hội hóa...")
    ghi_chu = st.text_area("Ghi chú")
    submitted = st.form_submit_button("Lưu thiết bị", type="primary", icon=":material/save:")

if submitted:
    code = code.strip().upper()
    name = name.strip() or known.get(code, "")
    if not code or not name:
        st.error("Vui lòng nhập Mã thiết bị và Tên thiết bị.")
    elif ((tb["Title"].str.upper() == code) & (tb["MaPhong"] == room)).any():
        st.error(f"Thiết bị {code} đã có trong phòng {room}. Hãy dùng chức năng **Chỉnh sửa** để thay đổi số lượng.")
    else:
        storage.create(schema.THIET_BI, {
            "Title": code, "TenThietBi": name, "LoaiThietBi": loai, "MaPhong": room,
            "SoLuong": so_luong, "DonViTinh": dvt, "NguyenGia": nguyen_gia, "NamSuDung": nam,
            "NgayNhap": ngay_nhap, "NguonGoc": nguon_goc, "TinhTrang": tinh_trang, "GhiChu": ghi_chu,
        })
        ui.flash(f"Đã nhập thiết bị {code} – {name} vào phòng {labels.get(room, room)}.")
        st.rerun()

st.divider()
st.markdown("##### Thiết bị nhập gần đây")
recent = tb.sort_values(["NgayNhap", "id"], ascending=False, key=lambda s: s if s.name == "NgayNhap" else s.astype(int)).head(10)
ui.show_table(recent, schema.THIET_BI, ["Title", "TenThietBi", "MaPhong", "SoLuong", "DonViTinh", "TinhTrang", "NgayNhap"])
