"""Báo cáo tổng quan BGH: chỉ số chính + 12 bảng thống kê, xuất Excel."""

from datetime import date

import pandas as pd
import streamlit as st

from qlts import auth, baocao, schema, storage, thietbi, ui

auth.require(schema.ROLE_BGH, schema.ROLE_QLTS)
st.subheader("Báo cáo tổng quan BGH")

tb = storage.load(schema.THIET_BI)
kk = storage.load(schema.KIEM_KE)
dc = storage.load(schema.DIEU_CHUYEN)
try:
    tl = storage.load(schema.THANH_LY)
except storage.StorageError:
    tl = storage.empty_frame(schema.THANH_LY)
labels = ui.room_label_map()
managers = thietbi.room_managers()
BAR = "#2a78c4"  # một màu: mỗi biểu đồ chỉ có một chuỗi dữ liệu

# ---- Bộ lọc chung (áp dụng cho mọi bảng thiết bị) ----
c1, c2 = st.columns(2)
f_groups = c1.multiselect("Nhóm thiết bị", sorted(set(tb["NhomThietBi"]) - {""}), placeholder="Tất cả nhóm")
f_rooms = c2.multiselect("Nơi sử dụng", thietbi.all_rooms(), format_func=lambda r: labels.get(r, r),
                         placeholder="Tất cả nơi sử dụng")
if f_groups:
    tb = tb[tb["NhomThietBi"].isin(f_groups)]
if f_rooms:
    tb = tb[tb["NoiSuDung"].isin(f_rooms)]
rooms = f_rooms or thietbi.all_rooms()
disposed = thietbi.is_disposed(tb)
act = tb[~disposed]
bad = act[thietbi.needs_attention(act)]

m1, m2, m3, m4 = st.columns(4)
m1.metric("Thiết bị đang sử dụng", f"{len(act):,}".replace(",", "."), border=True,
          help=f"{act['MaTaiSan'].nunique()} loại tài sản")
m2.metric("Tổng giá trị", ui.money_short(act["GiaTri"].sum()), border=True, help=ui.money(act["GiaTri"].sum()))
m3.metric("Cần kiểm tra / sửa / thanh lý", len(bad), border=True)
m4.metric("Đã thanh lý", int(disposed.sum()), border=True)

# ---- Định dạng cột dùng chung ----
NUM = st.column_config.NumberColumn
COLS = {
    "Nhom": "Nhóm thiết bị", "SoLoai": NUM("Số loại TS", format="localized"),
    "SoTB": NUM("Số thiết bị", format="localized"), "TyLeSL": NUM("% số lượng", format="%.1f %%"),
    "GiaTri": NUM("Giá trị (VNĐ)", format="localized"), "TyLeGT": NUM("% giá trị", format="%.1f %%"),
    "CanXuLy": NUM("Cần xử lý", format="localized"), "DaThanhLy": NUM("Đã thanh lý", format="localized"),
    "Phong": "Nơi sử dụng", "QuanLy": "Quản lý phòng", "MaTaiSan": "Mã tài sản", "Ten": "Tên tài sản",
    "SoPhong": NUM("Số phòng", format="localized"), "GiaTB": NUM("Giá TB / thiết bị", format="localized"),
    "Tuoi": "Tuổi thiết bị", "Nam": "Năm mua", "MucGia": "Mức giá trị", "Email": "Email quản lý",
    "HoTen": "Họ tên", "Thang": "Tháng", "SoLan": NUM("Số lần điều chuyển", format="localized"),
    "TuPhong": NUM("Số phòng chuyển đi", format="localized"),
    "DenPhong": NUM("Số phòng nhận", format="localized"), "SoDong": NUM("Số dòng", format="localized"),
    "SoSach": NUM("Sổ sách", format="localized"), "ThucTe": NUM("Thực tế", format="localized"),
    "Thieu": NUM("Thiếu", format="localized"), "Thua": NUM("Thừa", format="localized"),
    "TrangThai": "Trạng thái", "DotThanhLy": "Đợt thanh lý", "Ngay": "Ngày", "SoTT": "Số tờ trình",
    "SoTS": NUM("Số tài sản", format="localized"), "SoLuong": NUM("Số lượng", format="localized"),
    "GiaMua": NUM("Giá mua mới", format="localized"), "ConLai": NUM("Giá trị còn lại", format="localized"),
    "KiemTra": "Nội dung kiểm tra", "TyLe": NUM("% thiết bị", format="%.1f %%"),
}
SHEETS: dict[str, pd.DataFrame] = {}


def table(no: int, title: str, df: pd.DataFrame, note: str = "", sheet: str = "", height: int | str = "auto"):
    st.markdown(f"##### Bảng {no}. {title}")
    if note:
        st.caption(note)
    if df.empty:
        st.info("Chưa có dữ liệu.")
        return
    config = {c: COLS[c] for c in df.columns if c in COLS}
    st.dataframe(df, hide_index=True, width="stretch", column_config=config,
                 height=height if len(df) > 12 else "auto")
    SHEETS[f"B{no}_{sheet}"[:31]] = df


def bar(df: pd.DataFrame, x: str, y: str, x_title: str, y_title: str):
    data = df[df[x] != baocao.TOTAL][[x, y]].rename(columns={x: x_title, y: y_title})
    if not data.empty:
        st.bar_chart(data, x=x_title, y=y_title, color=BAR, horizontal=True, sort=f"-{y_title}", height=260)


tabs = st.tabs(["Theo nhóm & tình trạng", "Theo nơi sử dụng & người quản lý", "Theo loại tài sản",
                "Theo thời gian & giá trị", "Kiểm kê – Điều chuyển – Thanh lý", "Chất lượng dữ liệu"])

with tabs[0]:
    t1 = baocao.by_group(tb)
    table(1, "Thống kê theo nhóm thiết bị", t1, "Số loại, số lượng, giá trị, tỷ trọng; cột Đã thanh lý đếm riêng "
          "(không tính vào số thiết bị đang sử dụng).", "NhomThietBi")
    bar(t1, "Nhom", "GiaTri", "Nhóm thiết bị", "Giá trị (VNĐ)")
    table(2, "Ma trận nhóm thiết bị × tình trạng", baocao.group_by_status(act),
          "Số thiết bị đang sử dụng theo từng tình trạng.", "NhomxTinhTrang")

with tabs[1]:
    t3 = baocao.by_room(act, labels, managers, rooms)
    table(3, "Thống kê theo nơi sử dụng", t3, "Sắp xếp theo giá trị giảm dần.", "NoiSuDung", height=420)
    table(4, "Thống kê theo người quản lý phòng", baocao.by_manager(act, managers, thietbi.user_directory()),
          "Mỗi người: số phòng phụ trách, số thiết bị, số cần xử lý và tổng giá trị.", "NguoiQuanLy")

with tabs[2]:
    t5 = baocao.by_asset_type(act, thietbi.load_catalog())
    table(5, "Thống kê theo loại tài sản (Mã tài sản)", t5,
          "Số thiết bị, số phòng đang đặt, tổng giá trị và giá trung bình mỗi thiết bị.", "LoaiTaiSan", height=460)
    bar(t5.head(16), "Ten", "SoTB", "Loại tài sản", "Số thiết bị")

with tabs[3]:
    t6 = baocao.by_age(act)
    table(6, "Thống kê theo tuổi thiết bị", t6, "Tính từ ngày mua đến hôm nay; thiết bị càng cũ càng cần theo dõi "
          "để lên kế hoạch thay thế.", "TuoiThietBi")
    bar(t6, "Tuoi", "SoTB", "Tuổi thiết bị", "Số thiết bị")
    table(7, "Mua sắm theo năm", baocao.by_year(act), "Số thiết bị và giá trị theo năm mua.", "MuaSamTheoNam")
    table(8, "Thống kê theo mức giá trị", baocao.by_value_band(act),
          "Phân biệt tài sản từ 30 triệu trở lên với công cụ dụng cụ giá trị nhỏ.", "MucGiaTri")

with tabs[4]:
    dots = sorted(set(kk["DotKiemKe"]) - {""}, reverse=True)
    if dots:
        dot = st.selectbox("Đợt kiểm kê", dots)
        table(9, f"Kết quả kiểm kê theo phòng – {dot}", baocao.inventory_by_room(kk, dot, labels),
              "Số lượng sổ sách so với thực tế; phòng thiếu nhiều nhất ở trên.", "KiemKe")
    else:
        table(9, "Kết quả kiểm kê theo phòng", pd.DataFrame(), sheet="KiemKe")
    table(10, "Điều chuyển theo tháng", baocao.transfers_by_month(dc), "Số lần điều chuyển, số thiết bị và số "
          "phòng liên quan mỗi tháng.", "DieuChuyen")
    table(11, "Thanh lý theo đợt", baocao.disposals_by_round(tl), "Từ list ThanhLy (lịch sử thanh lý).",
          "ThanhLy")

with tabs[5]:
    table(12, "Chất lượng dữ liệu thiết bị", baocao.data_quality(act),
          "Số thiết bị đang sử dụng còn thiếu thông tin – bổ sung ở trang Danh sách thiết bị.", "ChatLuongDuLieu")
    st.markdown("##### Danh sách thiết bị cần kiểm tra / sửa chữa / thanh lý")
    ui.show_table(bad, schema.THIET_BI, ["MaChiTiet", "TenThietBi", "DacDiem", "NoiSuDung", "TinhTrang", "GhiChu"])

# ---- Xuất Excel toàn bộ bảng ----
def header(col: str) -> str:
    spec = COLS.get(col, col)
    return spec if isinstance(spec, str) else spec["label"]


sheets = {name: df.rename(columns=header) for name, df in SHEETS.items()}
sheets["CanXuLy"] = bad.drop(columns="id").rename(columns=schema.labels_of(schema.THIET_BI))
st.download_button("Xuất toàn bộ báo cáo (Excel, mỗi bảng 1 sheet)", ui.to_excel(sheets),
                   file_name=f"bao_cao_{date.today():%Y%m%d}.xlsx", type="primary", icon=":material/download:")
