from datetime import date

import streamlit as st

from qlts import auth, schema, storage, ui

user = auth.require(schema.ROLE_QLTS)
st.subheader("Điều chuyển thiết bị")

tb = storage.load(schema.THIET_BI)
labels = ui.room_label_map()
rooms = list(labels)
fmt = lambda r: labels.get(r, r)  # noqa: E731

c1, c2 = st.columns(2)
tu_phong = c1.selectbox("Từ phòng", rooms, format_func=fmt, key="dc_from")
in_room = tb[(tb["MaPhong"] == tu_phong) & (tb["SoLuong"] > 0)]
if in_room.empty:
    st.info("Phòng này không có thiết bị để điều chuyển.")
else:
    items = in_room.set_index("id")
    with st.form("dieu_chuyen"):
        item_id = st.selectbox(
            "Thiết bị", list(items.index),
            format_func=lambda i: f"{items.loc[i, 'Title']} – {items.loc[i, 'TenThietBi']} "
                                  f"(còn {int(items.loc[i, 'SoLuong'])} {items.loc[i, 'DonViTinh']})",
        )
        c1, c2, c3 = st.columns(3)
        den_phong = c1.selectbox("Đến phòng", [r for r in rooms if r != tu_phong], format_func=fmt)
        so_luong = c2.number_input("Số lượng điều chuyển", min_value=1, value=1, step=1)
        ngay = c3.date_input("Ngày điều chuyển", value=date.today(), format="DD/MM/YYYY")
        ly_do = st.text_area("Lý do")
        ok = st.form_submit_button("Xác nhận điều chuyển", type="primary", icon=":material/swap_horiz:")

    if ok:
        src = items.loc[item_id]
        if not den_phong:
            st.error("Chọn phòng nhận.")
        elif so_luong > src["SoLuong"]:
            st.error(f"Số lượng điều chuyển vượt quá số lượng hiện có ({int(src['SoLuong'])}).")
        else:
            dest = tb[(tb["Title"] == src["Title"]) & (tb["MaPhong"] == den_phong)]
            remaining = src["SoLuong"] - so_luong
            if not dest.empty:
                # Phòng nhận đã có thiết bị cùng mã: cộng dồn số lượng
                d = dest.iloc[0]
                storage.update(schema.THIET_BI, d["id"], {"SoLuong": d["SoLuong"] + so_luong})
                if remaining > 0:
                    storage.update(schema.THIET_BI, item_id, {"SoLuong": remaining})
                else:
                    storage.delete(schema.THIET_BI, item_id)
            elif remaining > 0:
                # Chuyển một phần: tách thành bản ghi mới ở phòng nhận
                fields = {c: src[c] for c in schema.columns_of(schema.THIET_BI)}
                fields.update({"MaPhong": den_phong, "SoLuong": so_luong})
                storage.create(schema.THIET_BI, fields)
                storage.update(schema.THIET_BI, item_id, {"SoLuong": remaining})
            else:
                storage.update(schema.THIET_BI, item_id, {"MaPhong": den_phong})
            storage.create(schema.DIEU_CHUYEN, {
                "Title": src["Title"], "TenThietBi": src["TenThietBi"], "TuPhong": tu_phong,
                "DenPhong": den_phong, "SoLuong": so_luong, "NgayDieuChuyen": ngay,
                "NguoiThucHien": user.email, "LyDo": ly_do,
            })
            ui.flash(f"Đã điều chuyển {so_luong} {src['DonViTinh']} {src['TenThietBi']} từ {tu_phong} sang {den_phong}.")
            st.rerun()

st.divider()
st.markdown("##### Lịch sử điều chuyển")
dc = storage.load(schema.DIEU_CHUYEN).sort_values("NgayDieuChuyen", ascending=False)
ui.show_table(dc, schema.DIEU_CHUYEN)
