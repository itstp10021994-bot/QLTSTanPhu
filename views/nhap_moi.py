from datetime import date

import streamlit as st

from qlts import auth, schema, storage, thietbi, ui

user = auth.require(schema.ROLE_QLTS)
st.subheader("Nhập mới thiết bị")

tb = storage.load(schema.THIET_BI)
labels = ui.room_label_map()
rooms = list(labels)
managers = thietbi.room_managers()

# ---- Chọn loại thiết bị -> Mã tài sản (ngoài form để gợi ý thông tin & mã chi tiết ngay) ----
NEW = "+ Mã tài sản mới (không có trong danh mục)"
catalog = thietbi.load_catalog().set_index("MaPhanLoai")
latest = tb.sort_values("id", key=lambda s: s.astype(int)).drop_duplicates("MaTaiSan", keep="last")
latest = latest[latest["MaTaiSan"] != ""].set_index("MaTaiSan")
# Danh mục trước (theo tên), sau đó các mã đang dùng nhưng chưa có trong danh mục
codes_opts = [*catalog.index, *sorted(set(latest.index) - set(catalog.index))]


def option_label(m: str) -> str:
    if m == NEW:
        return m
    if m in catalog.index:
        row = catalog.loc[m]
        return f"{row['TenThietBi']} – {m}" + (f" · {row['NhomThietBi']}" if row["NhomThietBi"] else "")
    return f"{latest.loc[m, 'TenThietBi'] or latest.loc[m, 'ChiTiet']} – {m} (chưa có trong danh mục)"


c1, c2 = st.columns([2, 1])
ma_sel = c1.selectbox(
    "Loại thiết bị (gõ tên để tìm)", [*codes_opts, NEW], index=None, format_func=option_label,
    placeholder="Chọn loại thiết bị – app tự điền Mã tài sản và Nhóm thiết bị",
)
if catalog.empty:
    c1.caption("Chưa đọc được danh mục loại thiết bị (list Data_Loaithietbi) – đang dùng các mã đã có.")
ma = c1.text_input("Nhập mã tài sản mới *").strip() if ma_sel == NEW else (ma_sel or "")
so_luong = c2.number_input("Số thiết bị nhập", min_value=1, max_value=200, value=1, step=1,
                           help="Mỗi thiết bị là một dòng với Mã chi tiết riêng.")
if not ma:
    st.info("Chọn loại thiết bị để bắt đầu.", icon=":material/touch_app:")
    st.stop()
tpl = latest.loc[ma] if ma in latest.index else None
cat_row = catalog.loc[ma] if ma in catalog.index else None
codes = thietbi.next_detail_codes(tb, ma, so_luong)
shown = codes[0] if len(codes) == 1 else f"{codes[0]} → {codes[-1]}"
st.info(f"Mã tài sản: **{ma}** · Mã chi tiết sẽ tạo: **{shown}**", icon=":material/tag:")


def tv(col: str, default=""):
    """Giá trị gợi ý: danh mục loại thiết bị (tên, nhóm) > thiết bị cùng mã gần nhất."""
    if cat_row is not None and col in ("TenThietBi", "NhomThietBi") and cat_row[col]:
        return cat_row[col]
    return tpl[col] if tpl is not None and tpl[col] else default


def idx(options: list, value, default=0):
    return options.index(value) if value in options else default


with st.form(f"nhap_moi_{ma}", clear_on_submit=False):
    c1, c2, c3 = st.columns(3)
    ten = c1.text_input("Tên thiết bị *", tv("TenThietBi"))
    chi_tiet = c2.text_input("Chi tiết", tv("ChiTiet"))
    nhom_opts = thietbi.distinct(tb, "NhomThietBi", [*catalog["NhomThietBi"].unique(), *schema.NHOM_THIET_BI])
    if tv("NhomThietBi") and tv("NhomThietBi") not in nhom_opts:
        nhom_opts.insert(0, tv("NhomThietBi"))
    nhom_opts = [o for o in nhom_opts if o]
    nhom = c3.selectbox("Nhóm thiết bị", nhom_opts, index=idx(nhom_opts, tv("NhomThietBi")),
                        accept_new_options=True)
    dac_diem = st.text_input("Đặc điểm", tv("DacDiem"), placeholder="Hãng, cấu hình, model...")
    c1, c2, c3 = st.columns(3)
    noi = c1.selectbox("Nơi sử dụng *", rooms, format_func=lambda r: labels.get(r, r), accept_new_options=True)
    nguoi_sd = c2.text_input("Người sử dụng (email)", help="Để trống sẽ lấy người quản lý phòng.")
    tinh_trang_opts = thietbi.status_options(tb)
    tinh_trang = c3.selectbox("Tình trạng", tinh_trang_opts, index=idx(tinh_trang_opts, "Mới"))
    c1, c2, c3, c4 = st.columns(4)
    dvt_opts = thietbi.distinct(tb, "DVT", schema.DON_VI_TINH)
    dvt = c1.selectbox("ĐVT", dvt_opts, index=idx(dvt_opts, tv("DVT", "Cái")), accept_new_options=True)
    gia_tri = c2.number_input("Giá trị / thiết bị (VNĐ)", min_value=0, value=int(tv("GiaTri", 0)), step=100_000)
    ngay_mua = c3.date_input("Ngày mua", value=date.today(), format="DD/MM/YYYY")
    ngay_hd = c4.date_input("Ngày hóa đơn", value=None, format="DD/MM/YYYY")
    c1, c2 = st.columns(2)
    ma_sap = c1.text_input("Mã SAP", tv("MaSAP"))
    bao_hanh = c2.text_input("Thời hạn bảo hành", placeholder="VD: 24 tháng / 31/12/2027")
    serials = st.text_area(
        "Tên phòng ban / Serial – mỗi dòng cho một thiết bị (theo thứ tự mã chi tiết)",
        height=80 if so_luong == 1 else 120,
    )
    ghi_chu = st.text_area("Ghi chú", height=68)
    submitted = st.form_submit_button(f"Lưu {so_luong} thiết bị", type="primary", icon=":material/save:")

if submitted:
    noi = (noi or "").strip()
    if not ma or not ten.strip() or not noi:
        st.error("Vui lòng nhập Mã tài sản, Tên thiết bị và Nơi sử dụng.")
        st.stop()
    serial_lines = [s.strip() for s in serials.splitlines()]
    with st.spinner("Đang lưu lên SharePoint..."):
        fresh = storage.load_fresh(schema.THIET_BI)  # tránh trùng mã khi nhiều người nhập cùng lúc
        codes = thietbi.next_detail_codes(fresh, ma, so_luong)
        stt = int(fresh["STT"].max()) if not fresh.empty else 0
        quan_ly_phong = managers.get(noi, "")
        for i, code in enumerate(codes):
            storage.create(schema.THIET_BI, {
                "MaChiTiet": code, "MaTaiSan": ma, "STT": stt + i + 1,
                "TenThietBi": ten.strip(), "ChiTiet": chi_tiet.strip() or ten.strip(), "DacDiem": dac_diem,
                "TenPhongBan": serial_lines[i] if i < len(serial_lines) else "",
                "DVT": dvt, "NoiSuDung": noi, "NguoiSuDung": nguoi_sd.strip().lower() or quan_ly_phong,
                "QuanLyPhong": quan_ly_phong, "QuanLyThietBi": user.name, "TinhTrang": tinh_trang,
                "NgayMua": ngay_mua, "NgayHoaDon": ngay_hd, "GiaTri": gia_tri, "MaSAP": ma_sap,
                "ThoiHanBaoHanh": bao_hanh, "NhomThietBi": nhom, "GhiChu": ghi_chu,
                "PhanQuyenTB": tv("PhanQuyenTB"),
            })
    shown = codes[0] if len(codes) == 1 else f"{codes[0]} → {codes[-1]}"
    ui.flash(f"Đã nhập {len(codes)} thiết bị {ten} ({shown}) vào {labels.get(noi, noi)}.")
    st.rerun()

st.divider()
st.markdown("##### Thiết bị nhập gần đây")
recent = tb.sort_values("id", key=lambda s: s.astype(int), ascending=False).head(10)
ui.show_table(recent, schema.THIET_BI, ["MaChiTiet", "TenThietBi", "DacDiem", "NoiSuDung", "TinhTrang", "NgayMua"])
