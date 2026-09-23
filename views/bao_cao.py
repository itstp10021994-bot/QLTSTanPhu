import streamlit as st

from qlts import auth, schema, storage, ui

auth.require(schema.ROLE_BGH, schema.ROLE_QLTS)
st.subheader("Báo cáo tổng quan BGH")

tb = storage.load(schema.THIET_BI)
phong = storage.load(schema.PHONG)
kk = storage.load(schema.KIEM_KE)
dc = storage.load(schema.DIEU_CHUYEN)
labels = ui.room_label_map()

active = tb[tb["TinhTrang"] != "Đã thanh lý"].copy()
active["GiaTri"] = active["SoLuong"] * active["NguyenGia"]
bad = active[~active["TinhTrang"].isin(["Tốt", ""])]

m1, m2, m3, m4 = st.columns(4)
m1.metric("Số phòng", len(phong), border=True)
m2.metric("Tổng số lượng thiết bị", f"{int(active['SoLuong'].sum()):,}".replace(",", "."), border=True)
m3.metric("Tổng nguyên giá", ui.money_short(active["GiaTri"].sum()), border=True,
          help=ui.money(active["GiaTri"].sum()))
m4.metric("Thiết bị cần sửa / thanh lý", f"{int(bad['SoLuong'].sum()):,}".replace(",", "."), border=True)

BAR = "#2a78c4"  # một màu duy nhất: mỗi biểu đồ chỉ có một chuỗi dữ liệu

c1, c2 = st.columns(2)
with c1:
    st.markdown("##### Số lượng thiết bị theo tình trạng")
    by_state = active.groupby("TinhTrang", as_index=False)["SoLuong"].sum()
    by_state = by_state.rename(columns={"TinhTrang": "Tình trạng", "SoLuong": "Số lượng"})
    st.bar_chart(by_state, x="Tình trạng", y="Số lượng", color=BAR, horizontal=True, sort="-Số lượng")
with c2:
    st.markdown("##### Giá trị thiết bị theo loại (VNĐ)")
    by_type = active.groupby("LoaiThietBi", as_index=False)["GiaTri"].sum()
    by_type = by_type.rename(columns={"LoaiThietBi": "Loại", "GiaTri": "Giá trị"})
    st.bar_chart(by_type, x="Loại", y="Giá trị", color=BAR, horizontal=True, sort="-Giá trị")

st.markdown("##### Tổng hợp theo phòng")
by_room = (
    active.groupby("MaPhong")
    .agg(SoDauTB=("Title", "count"), SoLuong=("SoLuong", "sum"), GiaTri=("GiaTri", "sum"))
    .reset_index()
)
by_room = phong[["Title", "TenPhong", "KhuVuc", "TenNguoiQuanLy"]].merge(
    by_room, left_on="Title", right_on="MaPhong", how="left"
).drop(columns="MaPhong").fillna({"SoDauTB": 0, "SoLuong": 0, "GiaTri": 0})
room_view = by_room.rename(columns={
    "Title": "Mã phòng", "TenPhong": "Tên phòng", "KhuVuc": "Khu vực", "TenNguoiQuanLy": "Người quản lý",
    "SoDauTB": "Số đầu TB", "SoLuong": "Tổng số lượng", "GiaTri": "Giá trị (VNĐ)",
})
st.dataframe(room_view, hide_index=True, width="stretch",
             column_config={"Giá trị (VNĐ)": st.column_config.NumberColumn(format="localized")})

st.markdown("##### Tiến độ kiểm kê")
dots = sorted(set(kk["DotKiemKe"]) - {""}, reverse=True)
kk_view = None
if not dots:
    st.caption("Chưa có đợt kiểm kê nào.")
else:
    dot = st.selectbox("Đợt kiểm kê", dots)
    cur = kk[kk["DotKiemKe"] == dot].copy()
    cur["ChenhLech"] = cur["SoLuongThucTe"] - cur["SoLuongSoSach"]
    done = cur["MaPhong"].nunique()
    k1, k2, k3 = st.columns(3)
    k1.metric("Phòng đã kiểm kê", f"{done}/{len(phong)}", border=True)
    k2.metric("Thiết bị chênh lệch", int((cur["ChenhLech"] != 0).sum()), border=True)
    k3.metric("Tổng chênh lệch số lượng", int(cur["ChenhLech"].sum()), border=True)
    pending = phong[~phong["Title"].isin(cur["MaPhong"])]
    if not pending.empty:
        st.caption("Phòng chưa kiểm kê: " + ", ".join(labels.get(r, r) for r in pending["Title"]))
    kk_view = cur.drop(columns="id").rename(columns={**schema.labels_of(schema.KIEM_KE), "ChenhLech": "Chênh lệch"})

st.markdown("##### Thiết bị cần sửa chữa / thanh lý")
ui.show_table(bad, schema.THIET_BI, ["Title", "TenThietBi", "MaPhong", "SoLuong", "DonViTinh", "TinhTrang", "GhiChu"])

st.markdown("##### Điều chuyển gần đây")
ui.show_table(dc.sort_values("NgayDieuChuyen", ascending=False).head(10), schema.DIEU_CHUYEN)

sheets = {
    "TongHopPhong": room_view,
    "ThietBi": tb.drop(columns="id").rename(columns=schema.labels_of(schema.THIET_BI)),
    "CanXuLy": bad.drop(columns=["id", "GiaTri"]).rename(columns=schema.labels_of(schema.THIET_BI)),
    "DieuChuyen": dc.drop(columns="id").rename(columns=schema.labels_of(schema.DIEU_CHUYEN)),
}
if kk_view is not None:
    sheets["KiemKe"] = kk_view
st.download_button("Xuất báo cáo Excel", ui.to_excel(sheets), file_name="bao_cao_tong_quan.xlsx",
                   type="primary", icon=":material/download:")
