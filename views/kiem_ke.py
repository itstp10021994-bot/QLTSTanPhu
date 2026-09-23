import streamlit as st

from qlts import auth, kiemke, schema, storage, ui

user = auth.require(schema.ROLE_KIEMKE)
st.subheader("Kiểm kê (Ban kiểm kê)")

tab_input, tab_result = st.tabs(["Thực hiện kiểm kê", "Kết quả kiểm kê"])
with tab_input:
    kiemke.render(user, list(ui.room_label_map()), key="bkk")

with tab_result:
    kk = storage.load(schema.KIEM_KE)
    if kk.empty:
        st.info("Chưa có dữ liệu kiểm kê.")
    else:
        dots = sorted(set(kk["DotKiemKe"]) - {""}, reverse=True)
        dot = st.selectbox("Đợt kiểm kê", dots, key="bkk_result_dot")
        data = kk[kk["DotKiemKe"] == dot].copy()
        data["ChenhLech"] = data["SoLuongThucTe"] - data["SoLuongSoSach"]
        only_diff = st.toggle("Chỉ hiện thiết bị chênh lệch / hư hỏng")
        if only_diff:
            data = data[(data["ChenhLech"] != 0) | (data["TinhTrang"] != "Tốt")]
        cols = ["MaPhong", "Title", "TenThietBi", "SoLuongSoSach", "SoLuongThucTe", "ChenhLech",
                "TinhTrang", "NguoiKiemKe", "NgayKiemKe", "GhiChu"]
        view = data[cols].rename(columns={**schema.labels_of(schema.KIEM_KE), "ChenhLech": "Chênh lệch"})
        st.dataframe(view, hide_index=True, width="stretch")
        st.download_button("Tải Excel", ui.to_excel({"KiemKe": view}), file_name=f"kiem_ke_{dot}.xlsx",
                           icon=":material/download:")
