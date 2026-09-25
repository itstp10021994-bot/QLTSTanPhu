from datetime import date

import streamlit as st

from qlts import auth, bienban, schema, storage, thietbi, ui

user = auth.require(schema.ROLE_QLTS)
st.subheader("Điều chuyển thiết bị")

tb = storage.load(schema.THIET_BI)
labels = ui.room_label_map()
managers = thietbi.room_managers()
rooms = list(labels)
fmt = lambda r: labels.get(r, r)  # noqa: E731

tu_phong = st.selectbox("Từ nơi sử dụng", rooms, format_func=fmt, key="dc_from")
in_room = tb[(tb["NoiSuDung"] == tu_phong)].reset_index(drop=True)
chosen = in_room.iloc[0:0]
if in_room.empty:
    st.info("Nơi này không có thiết bị.")
else:
    st.caption("Chọn các thiết bị cần điều chuyển (tick ô đầu dòng):")
    event = st.dataframe(
        in_room[["MaChiTiet", "TenThietBi", "DacDiem", "TenPhongBan", "NguoiSuDung", "TinhTrang"]]
        .rename(columns=schema.labels_of(schema.THIET_BI)),
        hide_index=True, width="stretch", on_select="rerun", selection_mode="multi-row", key=f"dc_sel_{tu_phong}",
    )
    chosen = in_room.iloc[event.selection.rows]
    with st.form("dieu_chuyen"):
        c1, c2, c3 = st.columns(3)
        dest_opts = [r for r in rooms if r != tu_phong] + [schema.NOI_THANH_LY]
        den_phong = c1.selectbox("Đến nơi sử dụng", dest_opts, format_func=fmt, accept_new_options=True)
        nguoi_sd = ui.user_picker(c2, "Người sử dụng mới", key="dc_nsd", blank="(Người quản lý phòng nhận)")
        ngay = c3.date_input("Ngày điều chuyển", value=date.today(), format="DD/MM/YYYY")
        ly_do = st.text_area("Lý do", height=68)
        ok = st.form_submit_button(f"Điều chuyển {len(chosen)} thiết bị", type="primary",
                                   icon=":material/swap_horiz:", disabled=chosen.empty)

    if ok:
        den_phong = (den_phong or "").strip()
        if not den_phong or den_phong == tu_phong:
            st.error("Chọn nơi nhận khác nơi hiện tại.")
            st.stop()
        ql_moi = managers.get(den_phong, "")
        with st.spinner("Đang cập nhật SharePoint..."):
            items = list(chosen.itertuples())
            errors = storage.batch(schema.THIET_BI, [("update", item.id, {
                "NoiSuDung": den_phong,
                "QuanLyPhong": ql_moi or item.QuanLyPhong,
                "NguoiSuDung": nguoi_sd.strip().lower() or ql_moi or item.NguoiSuDung,
            }) for item in items])
            errors += storage.batch(schema.DIEU_CHUYEN, [("create", {
                "Title": item.MaChiTiet, "TenThietBi": item.TenThietBi, "TuPhong": tu_phong,
                "DenPhong": den_phong, "SoLuong": 1, "NgayDieuChuyen": ngay,
                "NguoiThucHien": user.email, "LyDo": ly_do,
            }) for item in items])
        if errors:
            st.error("Có lỗi khi lưu:\n\n" + "\n\n".join(errors[:20]))
            st.stop()
        st.session_state["dc_last"] = {
            "codes": list(chosen["MaChiTiet"]), "tu": tu_phong, "den": den_phong, "ngay": ngay,
            "nhan": nguoi_sd.strip().lower() or ql_moi,
        }
        ui.flash(f"Đã điều chuyển {len(chosen)} thiết bị từ {fmt(tu_phong)} sang {fmt(den_phong)}. "
                 "Lập biên bản bàn giao ở cuối trang.")
        st.rerun()

st.divider()
st.markdown("##### Lịch sử điều chuyển")
dc = storage.load(schema.DIEU_CHUYEN).sort_values(["NgayDieuChuyen", "id"], ascending=False).reset_index(drop=True)
hist_cols = ["Title", "TenThietBi", "TuPhong", "DenPhong", "NgayDieuChuyen", "NguoiThucHien", "LyDo"]
hist = st.dataframe(
    dc[hist_cols].rename(columns=schema.labels_of(schema.DIEU_CHUYEN)), hide_index=True, width="stretch",
    on_select="rerun", selection_mode="multi-row", key="dc_hist", height=260,
)
hist_sel = dc.iloc[hist.selection.rows]

# ---------------------------------------------------------------------------
# Biên bản nghiệm thu / bàn giao cho thiết bị điều chuyển
# ---------------------------------------------------------------------------
st.divider()
st.markdown("##### Biên bản bàn giao")
last = st.session_state.get("dc_last")
sources = {}
if last:
    sources["last"] = f"Lần điều chuyển vừa rồi ({len(last['codes'])} thiết bị: {fmt(last['tu'])} → {fmt(last['den'])})"
if not chosen.empty:
    sources["chosen"] = f"Thiết bị đang chọn ở bảng trên ({len(chosen)} thiết bị)"
if not hist_sel.empty:
    sources["hist"] = f"Các dòng đang chọn trong Lịch sử điều chuyển ({len(hist_sel)} dòng)"
if not sources:
    st.caption("Chọn thiết bị ở bảng trên (hoặc tick các dòng trong Lịch sử điều chuyển) để lập biên bản.")
    st.stop()

src = st.radio("Thiết bị đưa vào biên bản", list(sources), format_func=sources.get, key="bb_src")
if src == "last":
    items_df = tb[tb["MaChiTiet"].isin(last["codes"])]
    tu, den, ngay_bb, nhan_default = last["tu"], last["den"], last["ngay"], last["nhan"]
elif src == "chosen":
    items_df = chosen
    tu, den, ngay_bb = tu_phong, "", date.today()
    nhan_default = ""
else:
    items_df = tb[tb["MaChiTiet"].isin(hist_sel["Title"])]
    tu, den = hist_sel["TuPhong"].iloc[0], hist_sel["DenPhong"].iloc[0]
    try:
        ngay_bb = date.fromisoformat(hist_sel["NgayDieuChuyen"].iloc[0])
    except ValueError:
        ngay_bb = date.today()
    nhan_default = ""
nhan_default = nhan_default or managers.get(den, "")

c1, c2 = st.columns(2)
giao_ten, giao_cv = ui.party_picker(c1.container(border=True), "Người bàn giao",
                                    default=managers.get(tu, "") or user.email, key=f"bb_giao_{src}")
nhan_ten, nhan_cv = ui.party_picker(c2.container(border=True), "Người nhận", default=nhan_default,
                                    key=f"bb_nhan_{src}")
c1, c2, c3 = st.columns([1, 2, 1], vertical_alignment="bottom")
ngay_bb = c1.date_input("Ngày bàn giao", value=ngay_bb, format="DD/MM/YYYY", key=f"bb_ngay_{src}")
dia_diem = c2.text_input("Địa điểm", bienban.default_place(), key="bb_place")
note_code = c3.checkbox("Ghi Mã tài sản vào Ghi chú", value=True, key="bb_note")

doc = bienban.BienBan(giao_ten=giao_ten, giao_chuc_vu=giao_cv, nhan_ten=nhan_ten, nhan_chuc_vu=nhan_cv,
                      items=bienban.group_items(items_df, note_code=note_code), ngay=ngay_bb,
                      dia_diem=dia_diem.strip(), sheet=(den or tu or "Bien ban"))
st.dataframe(
    [{"STT": i, "Tên hàng hóa/dịch vụ": it["ten"], "Mã hiệu/Quy cách": it["quy_cach"], "ĐVT": it["dvt"],
      "Số lượng": it["sl"], "Ghi chú": it["ghi_chu"]} for i, it in enumerate(doc.items, start=1)],
    hide_index=True, width="stretch",
)
if not (giao_ten and nhan_ten):
    st.warning("Chọn người bàn giao và người nhận.")
ui.bienban_downloads([doc], f"bien_ban_ban_giao_{ngay_bb:%Y%m%d}_{den or tu}", key="bb_dl",
                     formats=("docx", "pdf", "xlsx"))
