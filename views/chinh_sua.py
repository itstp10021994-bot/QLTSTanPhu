from datetime import date

import streamlit as st

from qlts import auth, schema, storage, ui

auth.require(schema.ROLE_QLTS)
st.subheader("Chỉnh sửa thông tin thiết bị")

tb = storage.load(schema.THIET_BI)
labels = ui.room_label_map()
filtered = ui.equipment_filters(tb, "cs").reset_index(drop=True)

st.caption(f"{len(filtered)} thiết bị – chọn một dòng để chỉnh sửa.")
cols = ["Title", "TenThietBi", "LoaiThietBi", "MaPhong", "SoLuong", "DonViTinh", "NguyenGia", "TinhTrang"]
event = st.dataframe(
    filtered[cols].rename(columns=schema.labels_of(schema.THIET_BI)),
    hide_index=True, width="stretch", on_select="rerun", selection_mode="single-row", key="cs_table",
)
selected = event.selection.rows
if not selected:
    st.stop()

item = filtered.iloc[selected[0]]


def _index(options, value, default=0):
    return options.index(value) if value in options else default


st.divider()
st.markdown(f"##### Sửa thiết bị **{item.Title} – {item.TenThietBi}** (phòng {labels.get(item.MaPhong, item.MaPhong)})")
rooms = list(labels)
with st.form(f"edit_{item.id}"):
    c1, c2 = st.columns(2)
    code = c1.text_input("Mã thiết bị", item.Title)
    name = c2.text_input("Tên thiết bị", item.TenThietBi)
    c1, c2, c3 = st.columns(3)
    loai = c1.selectbox("Loại thiết bị", schema.LOAI_THIET_BI, index=_index(schema.LOAI_THIET_BI, item.LoaiThietBi))
    room = c2.selectbox("Phòng", rooms, index=_index(rooms, item.MaPhong), format_func=lambda r: labels.get(r, r),
                        help="Muốn ghi nhận lịch sử di chuyển, hãy dùng chức năng Điều chuyển.")
    tinh_trang = c3.selectbox("Tình trạng", schema.TINH_TRANG, index=_index(schema.TINH_TRANG, item.TinhTrang))
    c1, c2, c3 = st.columns(3)
    so_luong = c1.number_input("Số lượng", min_value=0, value=int(item.SoLuong), step=1)
    dvt_opts = schema.DON_VI_TINH if item.DonViTinh in schema.DON_VI_TINH or not item.DonViTinh else [item.DonViTinh, *schema.DON_VI_TINH]
    dvt = c2.selectbox("Đơn vị tính", dvt_opts, index=_index(dvt_opts, item.DonViTinh))
    nguyen_gia = c3.number_input("Nguyên giá / đơn vị (VNĐ)", min_value=0, value=int(item.NguyenGia), step=100_000)
    c1, c2, c3 = st.columns(3)
    nam = c1.number_input("Năm đưa vào sử dụng", min_value=1990, max_value=2100,
                          value=int(item.NamSuDung) if item.NamSuDung else date.today().year)
    ngay_nhap = c2.date_input("Ngày nhập", value=date.fromisoformat(item.NgayNhap) if item.NgayNhap else None,
                              format="DD/MM/YYYY")
    nguon_goc = c3.text_input("Nguồn gốc", item.NguonGoc)
    ghi_chu = st.text_area("Ghi chú", item.GhiChu)
    save = st.form_submit_button("Lưu thay đổi", type="primary", icon=":material/save:")

if save:
    code = code.strip().upper()
    dup = (tb["Title"].str.upper() == code) & (tb["MaPhong"] == room) & (tb["id"] != item.id)
    if not code or not name.strip():
        st.error("Mã và tên thiết bị không được để trống.")
    elif dup.any():
        st.error(f"Phòng {room} đã có thiết bị mã {code}.")
    else:
        storage.update(schema.THIET_BI, item.id, {
            "Title": code, "TenThietBi": name.strip(), "LoaiThietBi": loai, "MaPhong": room,
            "SoLuong": so_luong, "DonViTinh": dvt, "NguyenGia": nguyen_gia, "NamSuDung": nam,
            "NgayNhap": ngay_nhap, "NguonGoc": nguon_goc, "TinhTrang": tinh_trang, "GhiChu": ghi_chu,
        })
        ui.flash(f"Đã cập nhật thiết bị {code}.")
        st.rerun()

with st.expander("Xóa thiết bị", icon=":material/delete:"):
    st.warning("Xóa sẽ không thể khôi phục. Nếu thiết bị hỏng/thanh lý, nên đổi tình trạng thay vì xóa.")
    confirm = st.checkbox(f"Tôi chắc chắn muốn xóa {item.Title} khỏi phòng {item.MaPhong}", key=f"del_{item.id}")
    if st.button("Xóa thiết bị", disabled=not confirm, icon=":material/delete_forever:"):
        storage.delete(schema.THIET_BI, item.id)
        ui.flash(f"Đã xóa thiết bị {item.Title} khỏi phòng {item.MaPhong}.")
        st.rerun()
