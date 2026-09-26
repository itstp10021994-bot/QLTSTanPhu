from datetime import date

import streamlit as st

from qlts import auth, schema, storage, thietbi, ui

auth.require(schema.ROLE_QLTS)
st.subheader("Chỉnh sửa thông tin thiết bị")

tb = storage.load(schema.THIET_BI)
labels = ui.room_label_map()
managers = thietbi.room_managers()
show_all = st.toggle("Hiện cả tài sản đã thanh lý", key="cs_all")
filtered = ui.equipment_filters(tb if show_all else thietbi.active(tb), "cs").reset_index(drop=True)
ver = st.session_state.setdefault("cs_ver", 0)

st.caption(f"{len(filtered)} thiết bị – **bấm vào một dòng** để mở cửa sổ chỉnh sửa (có nút xóa trong đó).")
event = st.dataframe(
    filtered[ui.TB_VIEW].rename(columns=schema.labels_of(schema.THIET_BI)),
    hide_index=True, width="stretch", on_select="rerun", selection_mode=["single-row", "single-cell"],
    key=f"cs_table_{ver}_{hash(tuple(filtered['id']))}",
    column_config={"Giá trị": st.column_config.NumberColumn(format="localized")},
)
# Bấm vào ô bất kỳ (hoặc ô chọn đầu dòng) đều tính là chọn dòng đó
cells = list(getattr(event.selection, "cells", []) or [])
sel_rows = list(event.selection.rows) or [c[0] if isinstance(c, (list, tuple)) else c["row"] for c in cells[:1]]
chosen = filtered.iloc[sel_rows[:1]]
sel_sig = (tuple(event.selection.rows), tuple(tuple(c) if isinstance(c, (list, tuple)) else str(c) for c in cells))


def idx(options: list, value, default=0):
    return options.index(value) if value in options else default


def as_date(value: str):
    try:
        return date.fromisoformat(value) if value else None
    except ValueError:
        return None


@st.dialog("Sửa thông tin thiết bị", width="large")
def edit_dialog(item) -> None:
    st.markdown(f"**{item.MaChiTiet}** – {item.TenThietBi}")
    rooms = list(labels)
    with st.form(f"edit_{item.id}", border=False):
        c1, c2, c3 = st.columns(3)
        c1.text_input("Mã tài sản", item.MaTaiSan, disabled=True)
        c2.text_input("Mã chi tiết", item.MaChiTiet, disabled=True)
        ma_sap = c3.text_input("Mã SAP", item.MaSAP)
        c1, c2, c3 = st.columns(3)
        ten = c1.text_input("Tên thiết bị", item.TenThietBi)
        chi_tiet = c2.text_input("Chi tiết", item.ChiTiet)
        nhom_opts = thietbi.distinct(tb, "NhomThietBi", schema.NHOM_THIET_BI)
        nhom = c3.selectbox("Nhóm thiết bị", nhom_opts, index=idx(nhom_opts, item.NhomThietBi),
                            accept_new_options=True)
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
        nguoi_sd = ui.user_picker(c2, "Người sử dụng", default=item.NguoiSuDung, key=f"cs_nsd_{item.id}",
                                  blank="(Để trống)")
        ql_phong = ui.user_picker(c3, "Quản lý phòng", default=item.QuanLyPhong, key=f"cs_qlp_{item.id}",
                                  blank="(Để trống)")
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
            return
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
        close_and_rerun()

    # ---- Xóa (hai bước ngay trong cửa sổ) ----
    st.divider()
    dkey = f"cs_confirm_del_{item.id}"
    if not st.session_state.get(dkey):
        if st.button("Xóa thiết bị này", icon=":material/delete:", key=f"act_del_cs_{item.id}"):
            st.session_state[dkey] = True
            st.rerun(scope="fragment")
    else:
        st.warning(f"Xóa **{item.MaChiTiet} – {item.TenThietBi}** khỏi SharePoint? Thao tác không thể hoàn tác. "
                   f"Thiết bị hỏng/thanh lý nên dùng chức năng **Thanh lý** thay vì xóa.")
        c1, c2 = st.columns(2)
        if c1.button("Đồng ý xóa", key="dlg_confirm", icon=":material/delete_forever:", width="stretch"):
            storage.delete(schema.THIET_BI, item.id)
            st.session_state.pop(dkey, None)
            ui.flash(f"Đã xóa thiết bị {item.MaChiTiet}.")
            close_and_rerun()
        if c2.button("Hủy", key=f"cs_del_cancel_{item.id}", width="stretch"):
            st.session_state.pop(dkey, None)
            st.rerun(scope="fragment")


def close_and_rerun() -> None:
    """Đóng cửa sổ và bỏ chọn dòng (bảng mới) để lần bấm sau mở lại được."""
    st.session_state["cs_ver"] = ver + 1
    st.session_state.pop("cs_open", None)
    st.rerun()


# Bấm vào một dòng -> mở cửa sổ chỉnh sửa (chỉ mở khi vừa chọn dòng mới, không mở lại ở mỗi lần chạy lại trang)
if chosen.empty:
    st.session_state.pop("cs_open", None)
elif st.session_state.get("cs_open") != sel_sig:
    st.session_state["cs_open"] = sel_sig
    edit_dialog(chosen.iloc[0])
