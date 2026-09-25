import streamlit as st

from qlts import auth, schema, storage, thietbi, ui

user = auth.require()
st.subheader("Danh sách Phòng đang quản lý")

rooms = thietbi.rooms_managed_by(user.email)
if not rooms:
    st.info("Bạn chưa được phân công quản lý phòng nào. Liên hệ quản trị viên để được phân quyền.")
    st.stop()

labels = ui.room_label_map()
tb = storage.load(schema.THIET_BI)
mine = thietbi.active(tb)[lambda d: d["NoiSuDung"].isin(rooms)]  # ẩn tài sản đã thanh lý
attention = thietbi.needs_attention(mine)

m1, m2, m3 = st.columns(3)
m1.metric("Số phòng", len(rooms), border=True)
m2.metric("Số thiết bị", len(mine), border=True)
m3.metric("Cần xử lý", int(attention.sum()), border=True)

cols = ["MaChiTiet", "TenThietBi", "DacDiem", "TenPhongBan", "NguoiSuDung", "TinhTrang", "MaSAP"]
for room in rooms:
    items = mine[mine["NoiSuDung"] == room]
    bad = int(thietbi.needs_attention(items).sum())
    title = f"**{labels.get(room, room)}** · {len(items)} thiết bị"
    if bad:
        title += f" · :red[{bad} cần xử lý]"
    with st.expander(title, expanded=len(rooms) == 1):
        if items.empty:
            st.caption("Phòng chưa có thiết bị.")
        else:
            ui.show_table(items, schema.THIET_BI, cols)

st.download_button("Tải danh sách thiết bị (Excel)",
                   ui.to_excel({"ThietBi": mine.drop(columns="id").rename(columns=schema.labels_of(schema.THIET_BI))}),
                   file_name="thiet_bi_phong_quan_ly.xlsx", icon=":material/download:")
