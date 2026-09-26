"""Báo cáo tổng quan BGH: chỉ số chính + 12 bảng thống kê, xuất Excel."""

from datetime import date

import pandas as pd
import streamlit as st

from qlts import auth, baocao, charts, schema, storage, thietbi, ui

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


def show(chart, title: str) -> None:
    """Một biểu đồ có tiêu đề nhỏ; bỏ qua nếu không có dữ liệu."""
    st.markdown(f"**{title}**")
    if chart is None:
        st.caption("Chưa có dữ liệu.")
    else:
        st.altair_chart(chart, width="stretch")


def body(df: pd.DataFrame, col: str) -> pd.DataFrame:
    """Bỏ dòng Tổng cộng trước khi vẽ."""
    return df[df[col] != baocao.TOTAL] if not df.empty else df


state = act.assign(TT=act["TinhTrang"].replace("", "(trống)")).groupby("TT", as_index=False).size()

tabs = st.tabs(["Theo nhóm & tình trạng", "Theo nơi sử dụng & người quản lý", "Theo loại tài sản",
                "Theo thời gian & giá trị", "Kiểm kê – Điều chuyển – Thanh lý", "Chất lượng dữ liệu"])

with tabs[0]:
    t1 = baocao.by_group(tb)
    c1, c2 = st.columns(2)
    with c1:
        show(charts.donut(body(t1, "Nhom"), "Nhom", "GiaTri", "Nhóm thiết bị", "Giá trị (VNĐ)"),
             "Tỷ trọng giá trị theo nhóm thiết bị")
    with c2:
        show(charts.donut(state, "TT", "size", "Tình trạng", "Số thiết bị"), "Cơ cấu theo tình trạng")
    show(charts.hbar(body(t1, "Nhom"), "Nhom", "SoTB", "Nhóm thiết bị", "Số thiết bị"),
         "Số thiết bị theo nhóm")
    table(1, "Thống kê theo nhóm thiết bị", t1, "Số loại, số lượng, giá trị, tỷ trọng; cột Đã thanh lý đếm riêng "
          "(không tính vào số thiết bị đang sử dụng).", "NhomThietBi")
    table(2, "Ma trận nhóm thiết bị × tình trạng", baocao.group_by_status(act),
          "Số thiết bị đang sử dụng theo từng tình trạng.", "NhomxTinhTrang")

with tabs[1]:
    t3 = baocao.by_room(act, labels, managers, rooms)
    t4 = baocao.by_manager(act, managers, thietbi.user_directory())
    c1, c2 = st.columns(2)
    with c1:
        show(charts.hbar(body(t3, "Phong"), "Phong", "GiaTri", "Nơi sử dụng", "Giá trị (VNĐ)"),
             "15 nơi sử dụng có giá trị tài sản lớn nhất")
    with c2:
        show(charts.hbar(body(t3, "Phong"), "Phong", "SoTB", "Nơi sử dụng", "Số thiết bị"),
             "15 nơi sử dụng có nhiều thiết bị nhất")
    if not t4.empty:
        t4c = body(t4, "Email").assign(Nguoi=lambda d: d["HoTen"].where(d["HoTen"] != "", d["Email"]))
        show(charts.hbar(t4c, "Nguoi", "SoTB", "Người quản lý", "Số thiết bị"),
             "Số thiết bị theo người quản lý phòng")
    table(3, "Thống kê theo nơi sử dụng", t3, "Sắp xếp theo giá trị giảm dần.", "NoiSuDung", height=420)
    table(4, "Thống kê theo người quản lý phòng", t4,
          "Mỗi người: số phòng phụ trách, số thiết bị, số cần xử lý và tổng giá trị.", "NguoiQuanLy")

with tabs[2]:
    t5 = baocao.by_asset_type(act, thietbi.load_catalog())
    t5c = body(t5, "MaTaiSan").assign(Loai=lambda d: d["Ten"] + " (" + d["MaTaiSan"] + ")")
    c1, c2 = st.columns(2)
    with c1:
        show(charts.hbar(t5c, "Loai", "SoTB", "Loại tài sản", "Số thiết bị"), "15 loại tài sản nhiều nhất")
    with c2:
        show(charts.hbar(t5c, "Loai", "GiaTri", "Loại tài sản", "Giá trị (VNĐ)"), "15 loại tài sản giá trị lớn nhất")
    table(5, "Thống kê theo loại tài sản (Mã tài sản)", t5,
          "Số thiết bị, số phòng đang đặt, tổng giá trị và giá trung bình mỗi thiết bị.", "LoaiTaiSan", height=460)

with tabs[3]:
    t6, t7, t8 = baocao.by_age(act), baocao.by_year(act), baocao.by_value_band(act)
    t7c = body(t7, "Nam").sort_values("Nam") if not t7.empty else t7
    c1, c2 = st.columns(2)
    with c1:
        show(charts.line(t7c, "Nam", "SoTB", "Năm mua", "Số thiết bị"), "Số thiết bị mua theo năm")
    with c2:
        show(charts.line(t7c, "Nam", "GiaTri", "Năm mua", "Giá trị (VNĐ)"), "Giá trị mua sắm theo năm")
    c1, c2 = st.columns(2)
    with c1:
        show(charts.vbar(body(t6, "Tuoi"), "Tuoi", "SoTB", "Tuổi thiết bị", "Số thiết bị",
                         sort=list(body(t6, "Tuoi")["Tuoi"])), "Phân bố tuổi thiết bị")
    with c2:
        show(charts.donut(body(t8, "MucGia"), "MucGia", "GiaTri", "Mức giá trị", "Giá trị (VNĐ)"),
             "Tỷ trọng giá trị theo mức giá")
    table(6, "Thống kê theo tuổi thiết bị", t6, "Tính từ ngày mua đến hôm nay; thiết bị càng cũ càng cần theo dõi "
          "để lên kế hoạch thay thế.", "TuoiThietBi")
    table(7, "Mua sắm theo năm", t7, "Số thiết bị và giá trị theo năm mua.", "MuaSamTheoNam")
    table(8, "Thống kê theo mức giá trị", t8,
          "Phân biệt tài sản từ 30 triệu trở lên với công cụ dụng cụ giá trị nhỏ.", "MucGiaTri")

with tabs[4]:
    dots = sorted(set(kk["DotKiemKe"]) - {""}, reverse=True)
    t9 = pd.DataFrame()
    if dots:
        dot = st.selectbox("Đợt kiểm kê", dots)
        t9 = baocao.inventory_by_room(kk, dot, labels)
    t10 = baocao.transfers_by_month(dc)
    t11 = baocao.disposals_by_round(tl)
    c1, c2 = st.columns(2)
    with c1:
        if not t10.empty:
            t10c = body(t10, "Thang").assign(ThangD=lambda d: pd.to_datetime("01/" + d["Thang"], format="%d/%m/%Y"))
            show(charts.line(t10c, "ThangD", "SoLan", "Tháng", "Số lần điều chuyển", temporal=True),
                 "Số lần điều chuyển theo tháng")
        else:
            show(None, "Số lần điều chuyển theo tháng")
    with c2:
        show(charts.hbar(body(t11, "DotThanhLy"), "DotThanhLy", "GiaMua", "Đợt thanh lý", "Giá mua mới (VNĐ)")
             if not t11.empty else None, "Giá trị tài sản thanh lý theo đợt")
    if not t9.empty:
        show(charts.grouped_bar(body(t9, "Phong").sort_values("Thieu", ascending=False), "Phong",
                                {"Thieu": "Thiếu", "Thua": "Thừa"}, "Nơi sử dụng", "Số lượng"),
             "Chênh lệch kiểm kê theo phòng (thiếu / thừa)")
    table(9, "Kết quả kiểm kê theo phòng" + (f" – {dot}" if dots else ""), t9,
          "Số lượng sổ sách so với thực tế; phòng thiếu nhiều nhất ở trên.", "KiemKe")
    table(10, "Điều chuyển theo tháng", t10, "Số lần điều chuyển, số thiết bị và số phòng liên quan mỗi tháng.",
          "DieuChuyen")
    table(11, "Thanh lý theo đợt", t11, "Từ list ThanhLy (lịch sử thanh lý).", "ThanhLy")

with tabs[5]:
    t12 = baocao.data_quality(act)
    show(charts.hbar(t12, "KiemTra", "SoTB", "Nội dung kiểm tra", "Số thiết bị"), "Số thiết bị còn thiếu thông tin")
    table(12, "Chất lượng dữ liệu thiết bị", t12,
          "Số thiết bị đang sử dụng còn thiếu thông tin – bổ sung ở trang Danh sách thiết bị.", "ChatLuongDuLieu")
    st.markdown("##### Danh sách thiết bị cần kiểm tra / sửa chữa / thanh lý")
    ui.show_table(bad, schema.THIET_BI, ["MaChiTiet", "TenThietBi", "DacDiem", "NoiSuDung", "TinhTrang", "GhiChu"])

# ---- Xuất Excel toàn bộ bảng ----
def header(col: str) -> str:
    spec = COLS.get(col, col)
    return spec if isinstance(spec, str) else spec["label"]


def report_xlsx() -> bytes:
    sheets = {name: df.rename(columns=header) for name, df in SHEETS.items()}
    sheets["CanXuLy"] = bad.drop(columns="id").rename(columns=schema.labels_of(schema.THIET_BI))
    return ui.to_excel(sheets)


st.download_button("Xuất toàn bộ báo cáo (Excel, mỗi bảng 1 sheet)", report_xlsx, on_click="ignore",
                   file_name=f"bao_cao_{date.today():%Y%m%d}.xlsx", type="primary", icon=":material/download:")
