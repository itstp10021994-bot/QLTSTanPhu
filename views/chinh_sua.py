from datetime import date

import streamlit as st

from qlts import auth, schema, storage, thietbi, ui

auth.require(schema.ROLE_QLTS)
st.subheader("Chỉnh sửa thông tin thiết bị")

tb = storage.load(schema.THIET_BI)
labels = ui.room_label_map()
managers = thietbi.room_managers()
filtered = ui.equipment_filters(tb, "cs").reset_index(drop=True)

st.caption(f"{len(filtered)} thiết bị – chọn một dòng để chỉnh sửa.")
event = st.dataframe(
    filtered[ui.TB_VIEW].rename(columns=schema.labels_of(schema.THIET_BI)),
    hide_index=True, width="stretch", on_select="rerun", selection_mode="single-row", key="cs_table",
    column_config={"Giá trị": st.column_config.NumberColumn(format="localized")},
)
if not event.selection.rows:
    st.stop()

item = filtered.iloc[event.selection.rows[0]]


def idx(options: list, value, default=0):
    return options.index(value) if value in options else default


def as_date(value: str):
    try:
        return date.fromisoformat(value) if value else None
    except ValueError:
        return None


st.divider()
st.markdown(f"##### {item.MaChiTiet} – {item.TenThietBi}")
rooms = list(labels)
with st.form(f"edit_{item.id}"):
    c1, c2, c3 = st.columns(3)
    c1.text_input("Mã tài sản", item.MaTaiSan, disabled=True)
    c2.text_input("Mã chi tiết", item.MaChiTiet, disabled=True)
    ma_sap = c3.text_input("Mã SAP", item.MaSAP)
    c1, c2, c3 = st.columns(3)
    ten = c1.text_input("Tên thiết bị", item.TenThietBi)
    chi_tiet = c2.text_input("Chi tiết", item.ChiTiet)
    nhom_opts = thietbi.distinct(tb, "NhomThietBi", schema.NHOM_THIET_BI)
    nhom = c3.selectbox("Nhóm thiết bị", nhom_opts, index=idx(nhom_opts, item.NhomThietBi), accept_new_options=True)
    dac_diem = st.text_input("Đặc điểm", item.DacDiem)
    c1, c2, c3 = st.columns(3)
    ten_pb = c1.text_input("Tên phòng ban / Serial", item.TenPhongBan)
    dvt_opts = thietbi.distinct(tb, "DVT", schema.DON_VI_TINH)
    dvt = c2.selectbox("ĐVT", dvt_opts, index=idx(dvt_opts, item.DVT), accept_new_options=True)
    st_opts = thietbi.status_options(tb, item.TinhTrang)
    tinh_trang = c3.selectbox("Tình trạng", st_opts, index=idx(st_opts, item.TinhTrang))
    c1, c2, c3 = st.columns(3)
    room_opts = rooms if item.NoiSuDung in rooms or not item.NoiSuDung else [item.NoiSuDung, *rooms]
    noi = c1.selectbox("Nơi sử dụng", room_opts, index=idx(room_opts, item.NoiSuDung),
                       format_func=lambda r: labels.get(r, r), accept_new_options=True,
                       help="Muốn lưu lịch sử di chuyển, hãy dùng chức năng Điều chuyển.")
    nguoi_sd = c2.text_input("Người sử dụng", item.NguoiSuDung)
    ql_phong = c3.text_input("Quản lý phòng", item.QuanLyPhong)
    c1, c2, c3, c4 = st.columns(4)
    gia_tri = c1.number_input("Giá trị (VNĐ)", min_value=0, value=int(item.GiaTri), step=100_000)
    ngay_mua = c2.date_input("Ngày mua", value=as_date(item.NgayMua), format="DD/MM/YYYY")
    ngay_hd = c3.date_input("Ngày hóa đơn", value=as_date(item.NgayHoaDon), format="DD/MM/YYYY")
    bao_hanh = c4.text_input("Thời hạn bảo hành", item.ThoiHanBaoHanh)
    c1, c2, c3 = st.columns(3)
    ql_tb = c1.text_input("Quản lý thiết bị", item.QuanLyThietBi)
    phan_quyen = c2.text_input("Phân quyền", item.PhanQuyenTB)
    mail = c3.text_input("Mail", item.Mail)
    ghi_chu = st.text_area("Ghi chú", item.GhiChu, height=68)
    save = st.form_submit_button("Lưu thay đổi", type="primary", icon=":material/save:")

if save:
    if not ten.strip():
        st.error("Tên thiết bị không được để trống.")
        st.stop()
    new = {
        "MaSAP": ma_sap, "TenThietBi": ten.strip(), "ChiTiet": chi_tiet, "NhomThietBi": nhom, "DacDiem": dac_diem,
        "TenPhongBan": ten_pb, "DVT": dvt, "TinhTrang": tinh_trang, "NoiSuDung": (noi or "").strip(),
        "NguoiSuDung": nguoi_sd.strip(), "QuanLyPhong": ql_phong.strip(), "GiaTri": gia_tri,
        "NgayMua": ngay_mua, "NgayHoaDon": ngay_hd, "ThoiHanBaoHanh": bao_hanh, "QuanLyThietBi": ql_tb,
        "PhanQuyenTB": phan_quyen, "Mail": mail, "GhiChu": ghi_chu,
    }
    if new["NoiSuDung"] != item.NoiSuDung and ql_phong.strip() == item.QuanLyPhong:
        new["QuanLyPhong"] = managers.get(new["NoiSuDung"], item.QuanLyPhong)
    # chỉ gửi các cột thực sự thay đổi
    changed = {}
    for k, v in new.items():
        old = item[k]
        if schema.column_type(schema.THIET_BI, k) == "date":
            if v is None and as_date(old) is None:
                continue  # ngày dạng chữ không đọc được -> giữ nguyên, không xóa
            v = v.isoformat() if v else ""
        elif schema.column_type(schema.THIET_BI, k) == "number":
            v, old = float(v), float(old)
        if v != old:
            changed[k] = new[k]
    if changed:
        storage.update(schema.THIET_BI, item.id, changed)
        ui.flash(f"Đã cập nhật {item.MaChiTiet} ({len(changed)} thông tin).")
    else:
        ui.flash("Không có thay đổi nào.")
    st.rerun()

with st.expander("Xóa thiết bị", icon=":material/delete:"):
    st.warning("Xóa sẽ không thể khôi phục. Thiết bị hỏng/thanh lý nên đổi Tình trạng hoặc Nơi sử dụng = "
               f"“{schema.NOI_THANH_LY}” thay vì xóa.")
    confirm = st.checkbox(f"Tôi chắc chắn muốn xóa {item.MaChiTiet}", key=f"del_{item.id}")
    if st.button("Xóa thiết bị", disabled=not confirm, icon=":material/delete_forever:"):
        storage.delete(schema.THIET_BI, item.id)
        ui.flash(f"Đã xóa thiết bị {item.MaChiTiet}.")
        st.rerun()
