from datetime import date

import streamlit as st

from qlts import auth, schema, storage, thietbi, ui

user = auth.require(schema.ROLE_QLTS)
st.subheader("Điều chuyển thiết bị")

tb = storage.load(schema.THIET_BI)
labels = ui.room_label_map()
managers = thietbi.room_managers()
rooms = list(labels)
fmt = lambda r: labels.get(r, r)  # noqa: E731

tu_phong = st.selectbox("Từ nơi sử dụng", rooms, format_func=fmt, key="dc_from")
in_room = tb[(tb["NoiSuDung"] == tu_phong)].reset_index(drop=True)
if in_room.empty:
    st.info("Nơi này không có thiết bị.")
else:
    st.caption("Chọn các thiết bị cần điều chuyển (tick ô đầu dòng):")
    event = st.dataframe(
        in_room[["MaChiTiet", "TenThietBi", "DacDiem", "TenPhongBan", "NguoiSuDung", "TinhTrang"]]
        .rename(columns=schema.labels_of(schema.THIET_BI)),
        hide_index=True, width="stretch", on_select="rerun", selection_mode="multi-row", key=f"dc_sel_{tu_phong}",
    )
    chosen = in_room.iloc[event.selection.rows]
    with st.form("dieu_chuyen"):
        c1, c2, c3 = st.columns(3)
        dest_opts = [r for r in rooms if r != tu_phong] + [schema.NOI_THANH_LY]
        den_phong = c1.selectbox("Đến nơi sử dụng", dest_opts, format_func=fmt, accept_new_options=True)
        nguoi_sd = c2.text_input("Người sử dụng mới (email)", help="Để trống = người quản lý phòng nhận.")
        ngay = c3.date_input("Ngày điều chuyển", value=date.today(), format="DD/MM/YYYY")
        ly_do = st.text_area("Lý do", height=68)
        ok = st.form_submit_button(f"Điều chuyển {len(chosen)} thiết bị", type="primary",
                                   icon=":material/swap_horiz:", disabled=chosen.empty)

    if ok:
        den_phong = (den_phong or "").strip()
        if not den_phong or den_phong == tu_phong:
            st.error("Chọn nơi nhận khác nơi hiện tại.")
            st.stop()
        ql_moi = managers.get(den_phong, "")
        with st.spinner("Đang cập nhật SharePoint..."):
            for item in chosen.itertuples():
                storage.update(schema.THIET_BI, item.id, {
                    "NoiSuDung": den_phong,
                    "QuanLyPhong": ql_moi or item.QuanLyPhong,
                    "NguoiSuDung": nguoi_sd.strip().lower() or ql_moi or item.NguoiSuDung,
                })
                storage.create(schema.DIEU_CHUYEN, {
                    "Title": item.MaChiTiet, "TenThietBi": item.TenThietBi, "TuPhong": tu_phong,
                    "DenPhong": den_phong, "SoLuong": 1, "NgayDieuChuyen": ngay,
                    "NguoiThucHien": user.email, "LyDo": ly_do,
                })
        ui.flash(f"Đã điều chuyển {len(chosen)} thiết bị từ {fmt(tu_phong)} sang {fmt(den_phong)}.")
        st.rerun()

st.divider()
st.markdown("##### Lịch sử điều chuyển")
dc = storage.load(schema.DIEU_CHUYEN).sort_values(["NgayDieuChuyen", "id"], ascending=False)
ui.show_table(dc, schema.DIEU_CHUYEN, ["Title", "TenThietBi", "TuPhong", "DenPhong", "NgayDieuChuyen",
                                       "NguoiThucHien", "LyDo"])
