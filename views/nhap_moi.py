from datetime import date

import streamlit as st

from qlts import auth, schema, storage, thietbi, ui

user = auth.require(schema.ROLE_QLTS)
st.subheader("Nhập mới thiết bị")

tb = storage.load(schema.THIET_BI)
labels = ui.room_label_map()
rooms = list(labels)
managers = thietbi.room_managers()

# ---- Chọn mã tài sản (ngoài form để gợi ý thông tin & mã chi tiết ngay) ----
NEW = "+ Mã tài sản mới"
latest = tb.sort_values("id", key=lambda s: s.astype(int)).drop_duplicates("MaTaiSan", keep="last")
latest = latest[latest["MaTaiSan"] != ""].set_index("MaTaiSan")
c1, c2 = st.columns([2, 1])
ma_sel = c1.selectbox(
    "Mã tài sản", [NEW, *sorted(latest.index)],
    format_func=lambda m: m if m == NEW else f"{m} – {latest.loc[m, 'TenThietBi'] or latest.loc[m, 'ChiTiet']}",
)
ma = c1.text_input("Nhập mã tài sản mới *").strip() if ma_sel == NEW else ma_sel
so_luong = c2.number_input("Số thiết bị nhập", min_value=1, max_value=200, value=1, step=1,
                           help="Mỗi thiết bị là một dòng với Mã chi tiết riêng.")
tpl = latest.loc[ma] if ma in latest.index else None
codes = thietbi.next_detail_codes(tb, ma, so_luong) if ma else []
if codes:
    shown = codes[0] if len(codes) == 1 else f"{codes[0]} → {codes[-1]}"
    st.info(f"Mã chi tiết sẽ tạo: **{shown}**", icon=":material/tag:")


def tv(col: str, default=""):
    """Giá trị gợi ý từ thiết bị cùng mã tài sản gần nhất."""
    return tpl[col] if tpl is not None and tpl[col] else default


def idx(options: list, value, default=0):
    return options.index(value) if value in options else default


with st.form(f"nhap_moi_{ma}", clear_on_submit=False):
    c1, c2, c3 = st.columns(3)
    ten = c1.text_input("Tên thiết bị *", tv("TenThietBi"))
    chi_tiet = c2.text_input("Chi tiết", tv("ChiTiet"))
    nhom_opts = thietbi.distinct(tb, "NhomThietBi", schema.NHOM_THIET_BI)
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
