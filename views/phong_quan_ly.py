import streamlit as st

from qlts import auth, schema, storage, ui

user = auth.require()
st.subheader("Danh sách Phòng đang quản lý")

phong = storage.load(schema.PHONG)
mine = phong[phong["NguoiQuanLy"].str.strip().str.lower() == user.email]
if mine.empty:
    st.info("Bạn chưa được phân công quản lý phòng nào. Liên hệ quản trị viên để được phân quyền.")
    st.stop()

tb = storage.load(schema.THIET_BI)
cols = ["Title", "TenThietBi", "LoaiThietBi", "SoLuong", "DonViTinh", "TinhTrang", "NamSuDung", "GhiChu"]
for room in mine.itertuples():
    items = tb[tb["MaPhong"] == room.Title]
    bad = int((~items["TinhTrang"].isin(["Tốt", "Đã thanh lý"])).sum())
    title = f"**{room.Title} – {room.TenPhong}** · {room.KhuVuc} · {len(items)} loại thiết bị"
    if bad:
        title += f" · :red[{bad} cần xử lý]"
    with st.expander(title, expanded=len(mine) == 1):
        if items.empty:
            st.caption("Phòng chưa có thiết bị.")
        else:
            ui.show_table(items, schema.THIET_BI, cols)

all_items = tb[tb["MaPhong"].isin(mine["Title"])]
st.download_button("Tải danh sách thiết bị (Excel)",
                   ui.to_excel({"ThietBi": all_items.drop(columns="id").rename(columns=schema.labels_of(schema.THIET_BI))}),
                   file_name="thiet_bi_phong_quan_ly.xlsx", icon=":material/download:")
