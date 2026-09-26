import streamlit as st

from qlts import auth, kiemke, schema, storage, thietbi, ui

user = auth.require(schema.ROLE_KIEMKE)
st.subheader("Kiểm kê (Ban kiểm kê)")

tab_input, tab_result = st.tabs(["Thực hiện kiểm kê", "Kết quả kiểm kê"])
with tab_input:
    kiemke.render_committee(user, thietbi.all_rooms(), key="bkk")

with tab_result:
    kk = storage.load(schema.KIEM_KE)
    dots = sorted(set(kk["DotKiemKe"]) - {""}, reverse=True)
    if not dots:
        st.info("Chưa có dữ liệu kiểm kê.")
    else:
        dot = st.selectbox("Đợt kiểm kê", dots, key="bkk_result_dot")
        data = kk[kk["DotKiemKe"] == dot].copy()
        data["ChenhLech"] = data["SoLuongKiemKe"] - data["SoLuong"]
        c1, c2 = st.columns(2)
        only_diff = c1.toggle("Chỉ hiện dòng chênh lệch / cần xử lý")
        only_unconfirmed = c2.toggle("Chỉ hiện dòng chưa được quản lý phòng xác nhận")
        if only_diff:
            data = data[(data["ChenhLech"] != 0) | ~data["TrangThai"].isin(schema.TINH_TRANG_TOT)]
        if only_unconfirmed:
            data = data[data["TrangThaiXacNhan"] != schema.DA_XAC_NHAN]
        cols = ["NoiSuDung", "MaTaiSan", "TenTaiSan", "DacDiem", "DVT", "SoLuong", "SoLuongKiemKe", "ChenhLech",
                "TrangThai", "GhiChu", "NgayKiemKe", "TrangThaiKiemKe", "NgayXacNhan", "TrangThaiXacNhan"]
        view = data[cols].rename(columns={**schema.labels_of(schema.KIEM_KE), "ChenhLech": "Chênh lệch"})
        st.dataframe(view, hide_index=True, width="stretch")
        st.download_button("Tải Excel", lambda: ui.to_excel({"KiemKe": view}), on_click="ignore", file_name=f"kiem_ke_{dot}.xlsx",
                           icon=":material/download:")
