import pandas as pd
import streamlit as st

from qlts import auth, schema, storage, thietbi, ui

auth.require(schema.ROLE_BGH, schema.ROLE_QLTS)
st.subheader("Báo cáo tổng quan BGH")

tb = storage.load(schema.THIET_BI)
kk = storage.load(schema.KIEM_KE)
dc = storage.load(schema.DIEU_CHUYEN)
labels = ui.room_label_map()
managers = thietbi.room_managers()
rooms = thietbi.all_rooms()

disposed = thietbi.is_disposed(tb)
active = tb[~disposed]
bad = active[thietbi.needs_attention(active)]

m1, m2, m3, m4 = st.columns(4)
m1.metric("Thiết bị đang sử dụng", f"{len(active):,}".replace(",", "."), border=True)
m2.metric("Tổng giá trị", ui.money_short(active["GiaTri"].sum()), border=True, help=ui.money(active["GiaTri"].sum()))
m3.metric("Cần kiểm tra / sửa / thanh lý", len(bad), border=True)
m4.metric("Đã thanh lý", int(disposed.sum()), border=True)

BAR = "#2a78c4"  # một màu duy nhất: mỗi biểu đồ chỉ có một chuỗi dữ liệu

c1, c2 = st.columns(2)
with c1:
    st.markdown("##### Số thiết bị theo tình trạng")
    by_state = active.assign(TinhTrang=active["TinhTrang"].replace("", "(trống)")).groupby(
        "TinhTrang", as_index=False).size().rename(columns={"TinhTrang": "Tình trạng", "size": "Số thiết bị"})
    st.bar_chart(by_state, x="Tình trạng", y="Số thiết bị", color=BAR, horizontal=True, sort="-Số thiết bị")
with c2:
    st.markdown("##### 10 loại thiết bị nhiều nhất")
    by_name = active.assign(TenThietBi=active["TenThietBi"].where(active["TenThietBi"] != "", active["ChiTiet"]))
    by_name = by_name.groupby("TenThietBi", as_index=False).size().nlargest(10, "size")
    by_name = by_name.rename(columns={"TenThietBi": "Thiết bị", "size": "Số lượng"})
    st.bar_chart(by_name, x="Thiết bị", y="Số lượng", color=BAR, horizontal=True, sort="-Số lượng")

st.markdown("##### Tổng hợp theo nơi sử dụng")
room_rows = []
for room in rooms:
    items = active[active["NoiSuDung"] == room]
    room_rows.append({
        "Nơi sử dụng": labels.get(room, room),
        "Quản lý phòng": managers.get(room, ""),
        "Số thiết bị": len(items),
        "Cần xử lý": int(thietbi.needs_attention(items).sum()),
        "Giá trị (VNĐ)": items["GiaTri"].sum(),
    })
room_view = pd.DataFrame(room_rows)
st.dataframe(room_view, hide_index=True, width="stretch",
             column_config={"Giá trị (VNĐ)": st.column_config.NumberColumn(format="localized")})

st.markdown("##### Tiến độ kiểm kê")
dots = sorted(set(kk["DotKiemKe"]) - {""}, reverse=True)
kk_view = None
if not dots:
    st.caption("Chưa có đợt kiểm kê nào.")
else:
    dot = st.selectbox("Đợt kiểm kê", dots)
    cur = kk[kk["DotKiemKe"] == dot]
    done_rooms = set(cur[cur["TrangThaiKiemKe"] == schema.DA_KIEM_KE]["NoiSuDung"])
    confirmed = set(cur[cur["TrangThaiXacNhan"] == schema.DA_XAC_NHAN]["NoiSuDung"])
    diff = cur["SoLuongKiemKe"] - cur["SoLuong"]
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Phòng đã kiểm kê", f"{len(done_rooms & set(rooms))}/{len(rooms)}", border=True)
    k2.metric("Phòng đã xác nhận", len(confirmed & set(rooms)), border=True)
    k3.metric("Thiết bị thiếu", int(-diff[diff < 0].sum()), border=True)
    k4.metric("Thiết bị thừa", int(diff[diff > 0].sum()), border=True)
    pending = [r for r in rooms if r not in done_rooms]
    if pending:
        st.caption("Chưa kiểm kê: " + ", ".join(labels.get(r, r) for r in pending))
    disagree = sorted(set(cur[cur["TrangThaiXacNhan"] == schema.KHONG_DONG_Y]["NoiSuDung"]))
    if disagree:
        st.warning("Quản lý phòng không đồng ý: " + ", ".join(labels.get(r, r) for r in disagree))
    kk_view = cur.drop(columns="id").rename(columns=schema.labels_of(schema.KIEM_KE))

st.markdown("##### Thiết bị cần kiểm tra / sửa chữa / thanh lý")
ui.show_table(bad, schema.THIET_BI, ["MaChiTiet", "TenThietBi", "DacDiem", "NoiSuDung", "TinhTrang", "GhiChu"])

st.markdown("##### Điều chuyển gần đây")
ui.show_table(dc.sort_values("NgayDieuChuyen", ascending=False).head(10), schema.DIEU_CHUYEN,
              ["Title", "TenThietBi", "TuPhong", "DenPhong", "NgayDieuChuyen", "NguoiThucHien"])

sheets = {
    "TongHopPhong": room_view,
    "ThietBi": tb.drop(columns="id").rename(columns=schema.labels_of(schema.THIET_BI)),
    "CanXuLy": bad.drop(columns="id").rename(columns=schema.labels_of(schema.THIET_BI)),
    "DieuChuyen": dc.drop(columns="id").rename(columns=schema.labels_of(schema.DIEU_CHUYEN)),
}
if kk_view is not None:
    sheets["KiemKe"] = kk_view
st.download_button("Xuất báo cáo Excel", ui.to_excel(sheets), file_name="bao_cao_tong_quan.xlsx",
                   type="primary", icon=":material/download:")
