"""Thanh lý tài sản: chọn tài sản -> Kế hoạch thanh lý + Tờ trình -> đánh dấu 'Đã thanh lý' trên SharePoint."""

from datetime import date

import pandas as pd
import streamlit as st

from qlts import auth, schema, storage, thanhly, thietbi, ui
from qlts import hoso_thanhly as hoso
from qlts.config import app_setting

user = auth.require(schema.ROLE_QLTS)
st.subheader("Thanh lý tài sản")

STATUS = str(app_setting("thanh_ly_tinh_trang", "Đã thanh lý"))
tb = storage.load(schema.THIET_BI)
labels = ui.room_label_map()
phong = storage.load(schema.PHONG).set_index("Title")["TenPhong"].to_dict()
room_names = {r: (phong.get(r) or r) for r in set(tb["NoiSuDung"])}
cart: list[str] = st.session_state.setdefault("tl_cart", [])  # id thiết bị đã chọn

try:
    history = storage.load(schema.THANH_LY)
    history_error = ""
except storage.StorageError as exc:
    history, history_error = storage.empty_frame(schema.THANH_LY), str(exc)

tab_new, tab_rounds, tab_done = st.tabs(["Lập thanh lý", "Các đợt thanh lý", "Tài sản đã thanh lý"])

if history_error:
    st.warning(
        "Chưa có list **ThanhLy** trên SharePoint để lưu lịch sử từng đợt thanh lý. Vào **Phân quyền → Xuất / nhập "
        "biểu mẫu**, chọn *Lịch sử thanh lý (theo đợt)* → tải **Biểu mẫu trống** (7_ThanhLy.xlsx) → tạo list trên "
        "site từ file này (New → List → From Excel), đặt tên **ThanhLy**, xóa dòng mẫu, rồi bấm **Làm mới**. "
        "Chưa có list thì app vẫn chuyển tình trạng thiết bị nhưng không lưu được danh sách theo đợt.",
        icon=":material/playlist_remove:",
    )
    st.caption(f"Chi tiết: {history_error}")
    if storage.is_bridge() and user.is_admin and st.button("Tạo list ThanhLy tự động", icon=":material/build:"):
        try:
            with st.spinner("Đang tạo list ThanhLy trên SharePoint..."):
                name = storage.get_store().create_list(schema.THANH_LY)
            storage.refresh(schema_too=True)
            ui.flash(f"Đã tạo list {name} trên SharePoint.")
            st.rerun()
        except storage.StorageError as exc:
            st.error(f"Không tạo được list: {exc}")


def round_items(rows: pd.DataFrame) -> pd.DataFrame:
    """Dòng lịch sử thanh lý (list ThanhLy) -> dòng biểu mẫu."""
    return pd.DataFrame({
        "id": rows["id"].values, "ngay_mua": rows["NamMua"].values, "ma": rows["Title"].values,
        "ten": rows["TenThietBi"].values, "dac_diem": rows["DacDiem"].values, "dvt": rows["DVT"].values,
        "sl": rows["SoLuong"].values, "gia_mua": rows["GiaMua"].values, "con_lai": rows["GiaTriConLai"].values,
        "don_vi": rows["NoiSuDung"].values, "tinh_trang": rows["TinhTrang"].values, "du_kien": rows["DuKien"].values,
        "ghi_chu": rows["GhiChu"].values,
    })


def default_texts(items, ngay: date) -> tuple[str, str]:
    types = ", ".join(dict.fromkeys(str(t).strip().lower() for t in items["ten"] if str(t).strip()))
    rooms = ", ".join(dict.fromkeys(str(r) for r in items["don_vi"] if r))
    return (f"Vv thanh lý {types} hư hỏng năm học {thanhly.school_year(ngay)}",
            "Trên cơ sở thực tế, sau khi tiến hành rà soát và đánh giá hiện trạng tài sản. Kính trình Ban giám "
            f"hiệu về việc thanh lý {types} hư hỏng của {rooms} cụ thể như sau:")


HINH_THUC = ("Bán phế liệu. Bộ phận Quản lý hệ thống sẽ chịu trách nhiệm đầu mối triển khai hướng bán phế liệu đề "
             "xuất thanh lý nêu trên. Chi phí thanh lý dự kiến thu hồi: ...... đồng.")
BAO_CAO = ("Sau khi thực hiện xong công tác thanh lý, Bộ phận quản lý CNTT sẽ kết hợp với Phòng Kế toán báo cáo kết "
           "quả thanh lý.")
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def downloads(tl, stem: str, key: str) -> None:
    st.caption("Biểu mẫu 1 – Kế hoạch thanh lý")
    c1, c2 = st.columns(2)
    c1.download_button("Kế hoạch – PDF", lambda: thanhly.kh_pdf(tl), f"ke_hoach_{stem}.pdf", "application/pdf",
                       icon=":material/picture_as_pdf:", width="stretch", on_click="ignore", type="primary",
                       key=f"{key}_khpdf")
    c2.download_button("Kế hoạch – Excel", lambda: thanhly.kh_xlsx(tl), f"ke_hoach_{stem}.xlsx", XLSX,
                       icon=":material/table:", width="stretch", on_click="ignore", key=f"{key}_khx")
    st.caption("Biểu mẫu 2 – Tờ trình phê duyệt thanh lý")
    c1, c2 = st.columns(2)
    c1.download_button("Tờ trình – PDF", lambda: thanhly.tt_pdf(tl), f"to_trinh_{stem}.pdf", "application/pdf",
                       icon=":material/picture_as_pdf:", width="stretch", on_click="ignore", type="primary",
                       key=f"{key}_ttpdf")
    c2.download_button("Tờ trình – Word", lambda: thanhly.tt_docx(tl), f"to_trinh_{stem}.docx", DOCX,
                       icon=":material/description:", width="stretch", on_click="ignore", key=f"{key}_ttw")


def hoso_downloads(word, pdf, stem: str, key: str) -> None:
    c1, c2 = st.columns(2)
    c1.download_button("Tải PDF", pdf, f"{stem}.pdf", "application/pdf", icon=":material/picture_as_pdf:",
                       width="stretch", on_click="ignore", type="primary", key=f"{key}_pdf")
    c2.download_button("Tải Word", word, f"{stem}.docx", DOCX, icon=":material/description:", width="stretch",
                       on_click="ignore", key=f"{key}_docx")


def with_device_info(items: pd.DataFrame) -> pd.DataFrame:
    """Bổ sung từ list thiết bị (theo Mã chi tiết): ngày mua đầy đủ, và nguyên giá khi đợt thanh lý lưu 0."""
    info = tb.drop_duplicates("MaChiTiet").set_index("MaChiTiet")
    out = items.copy()
    ngay = out["ma"].map(info["NgayMua"]).fillna("")
    full = pd.to_datetime(ngay, errors="coerce")
    out["ngay_mua"] = [f"{d:%d/%m/%Y}" if pd.notna(d) else str(o or "") for d, o in zip(full, out["ngay_mua"])]
    gia = pd.to_numeric(out["gia_mua"], errors="coerce").fillna(0)
    gia_tb = pd.to_numeric(out["ma"].map(info["GiaTri"]), errors="coerce").fillna(0)
    out["gia_mua"] = gia.where(gia > 0, gia_tb)
    out["con_lai"] = pd.to_numeric(out["con_lai"], errors="coerce").fillna(0)
    return out


def render_hoso(dot: str, rows: pd.DataFrame, items_r: pd.DataFrame, ngay_r: date) -> None:
    """3 mẫu hồ sơ sau khi xác nhận thanh lý: M02 – đề nghị mang ra ngoài, M06 – biên bản bàn giao – thanh lý,
    M07 – báo cáo kết quả thanh lý. Danh sách tài sản lấy từ đợt; các ô khác điền trên màn hình."""
    k = "hs_" + "".join(ch for ch in dot if ch.isalnum())[:40]
    items_r = with_device_info(items_r)
    stem = dot.replace(" ", "_").replace("–", "-")
    so = str(rows["SoToTrinh"].iloc[0] or "").strip()
    grouped = hoso.group_items(items_r)
    types = ", ".join(dict.fromkeys(str(t).strip().lower() for t in items_r["ten"] if str(t).strip()))
    st.markdown(f"**Hồ sơ sau thanh lý – {dot}**")
    st.caption("Hoàn tất quy trình thanh lý: đề nghị mang tài sản ra ngoài (M02), biên bản bàn giao – thanh lý cho "
               "bên mua (M06) và báo cáo kết quả thanh lý (M07). Danh sách tài sản lấy từ đợt này.")
    t2, t6, t7 = st.tabs(["M02 – Đề nghị mang tài sản ra ngoài", "M06 – Biên bản bàn giao – thanh lý",
                          "M07 – Báo cáo kết quả thanh lý"])

    with t2:
        nguoi, _ = ui.party_picker(st.container(), "Người đề nghị", default=user.email, key=f"{k}_m02_nguoi",
                                   inline=True)
        c1, c2 = st.columns(2)
        don_vi = c1.text_input("Đơn vị", app_setting("thanhly_don_vi", "Bộ phận Quản lý hệ thống"), key=f"{k}_m02_dv")
        noi = c2.text_input("Mang ra ngoài", hoso.school(), key=f"{k}_m02_noi", help="[Công ty/Trường/Trung tâm]")
        ly_do = st.text_input("Lý do", f"Mang tài sản đã thanh lý ({dot}"
                              + (f", theo tờ trình số {so}" if so else "") + ") ra ngoài để bàn giao cho bên mua.",
                              key=f"{k}_m02_lydo")
        items2 = st.data_editor(
            grouped.assign(ghi_chu="Tài sản thanh lý")[["ten", "dac_diem", "dvt", "sl", "ghi_chu"]],
            hide_index=True, width="stretch", key=f"{k}_m02_items", disabled=["ten", "dac_diem", "dvt", "sl"],
            column_config={"ten": "Tên tài sản", "dac_diem": "Đặc điểm", "dvt": "ĐVT", "sl": "Số lượng",
                           "ghi_chu": "Ghi chú"})
        c1, c2 = st.columns(2)
        ky_ht = c1.text_input("Ký: CTQ/Hiệu trưởng", key=f"{k}_m02_ht")
        ky_ql = c2.text_input("Ký: Đơn vị Quản lý tài sản", user.name, key=f"{k}_m02_ql")
        d = hoso.DeNghi(items=items2, nguoi_de_nghi=nguoi, don_vi=don_vi.strip(), noi=noi.strip(),
                        ly_do=ly_do.strip(), ky_hieu_truong=ky_ht.strip(), ky_quan_ly=ky_ql.strip())
        hoso_downloads(lambda: hoso.m02_docx(d), lambda: hoso.m02_pdf(d), f"M02_de_nghi_mang_ra_{stem}", f"{k}_m02")

    with t6:
        c1, c2 = st.columns([1, 2])
        ngay_bg = c1.date_input("Ngày bàn giao", value=ngay_r, format="DD/MM/YYYY", key=f"{k}_m06_ngay")
        ben_tl = c2.text_input("Bên thanh lý", hoso.school(), key=f"{k}_m06_btl")
        dia_chi = st.text_input("Địa chỉ bên thanh lý", hoso.school_address(), key=f"{k}_m06_dc")
        st.markdown("Đại diện bên thanh lý")
        reps = [ui.party_picker(st.container(), f"Đại diện {i}", default=user.email if i == 1 else "",
                                key=f"{k}_m06_rep{i}", inline=True) for i in (1, 2)]
        st.markdown("Bên mua")
        c1, c2 = st.columns(2)
        ben_mua = c1.text_input("Ông/Bà/Công ty", key=f"{k}_m06_mua")
        dc_mua = c2.text_input("Địa chỉ", key=f"{k}_m06_dcmua")
        c1, c2, c3 = st.columns(3)
        cccd = c1.text_input("CCCD/CMND/Mã số thuế", key=f"{k}_m06_cccd")
        dd = c2.text_input("Người đại diện", key=f"{k}_m06_dd", help="Khi bên mua là công ty/pháp nhân")
        cccd_dd = c3.text_input("CCCD/CMND của người đại diện", key=f"{k}_m06_cccddd")
        st.caption("Nhập đơn giá bán từng loại tài sản; thành tiền và tổng cộng tự tính.")
        items6 = st.data_editor(
            grouped.assign(don_gia=0.0)[["ten", "dac_diem", "dvt", "sl", "don_gia"]],
            hide_index=True, width="stretch", key=f"{k}_m06_items", disabled=["ten", "dac_diem", "dvt", "sl"],
            column_config={"ten": "Tên tài sản", "dac_diem": "Đặc điểm", "dvt": "ĐVT", "sl": "Số lượng",
                           "don_gia": st.column_config.NumberColumn("Đơn giá (VNĐ)", min_value=0, step=1000,
                                                                    format="localized")})
        b = hoso.BanGiaoTL(items=items6, ngay=ngay_bg, ben_thanh_ly=ben_tl.strip(), dia_chi=dia_chi.strip(),
                           dai_dien=[r for r in reps if r[0]], ben_mua=ben_mua.strip(), dia_chi_mua=dc_mua.strip(),
                           cccd_mst=cccd.strip(), nguoi_dai_dien=dd.strip(), cccd_dai_dien=cccd_dd.strip())
        c1, c2 = st.columns(2)
        b.so_tien = c1.number_input("Số tiền bên mua đã thanh toán (VNĐ)", min_value=0.0, value=b.tong, step=1000.0,
                                    format="%.0f", key=f"{k}_m06_tien_{int(b.tong)}")
        b.ngay_thanh_toan = c2.date_input("Ngày thanh toán", value=ngay_bg, format="DD/MM/YYYY", key=f"{k}_m06_ngaytt")
        st.markdown(f"Tổng cộng: **{thanhly.money(b.tong)} VNĐ** – "
                    f"*{hoso.so_thanh_chu(b.tong) if b.tong else 'chưa nhập đơn giá'} đồng*")
        if b.tong and abs(b.da_thanh_toan - b.tong) >= 1:
            st.warning("Số tiền đã thanh toán khác tổng thành tiền – mẫu M06 chỉ dùng khi bên mua đã thanh toán đủ.")
        st.session_state[f"{k}_thu_hoi"] = b.da_thanh_toan
        hoso_downloads(lambda: hoso.m06_docx(b), lambda: hoso.m06_pdf(b), f"M06_bien_ban_ban_giao_thanh_ly_{stem}",
                       f"{k}_m06")
        st.caption("Bên mua là công ty/pháp nhân: điền mã số thuế và người đại diện; người ký không phải đại diện "
                   "theo pháp luật thì cần giấy ủy quyền.")

    with t7:
        can_cu = st.text_input(
            "Thực hiện theo", (f"Tờ trình số: {so}/TTr-TP" if so else "Tờ trình số: ....../TTr-TP")
            + f" ngày {ngay_r.day} tháng {ngay_r.month} năm {ngay_r.year} về việc thanh lý {types}",
            key=f"{k}_m07_cancu")
        st.markdown("Nhân sự phụ trách việc thanh lý")
        nhan_su = [ui.party_picker(st.container(), f"Nhân sự {i}", default=user.email if i == 1 else "",
                                   key=f"{k}_m07_ns{i}", inline=True) for i in (1, 2, 3)]
        c1, c2, c3 = st.columns(3)
        chi_phi = c1.text_input("Chi phí thanh lý", "không phát sinh", key=f"{k}_m07_cp")
        thu_hoi = st.session_state.get(f"{k}_thu_hoi", 0.0)
        gia_tri = c2.number_input("Giá trị thu hồi (VNĐ, gồm VAT)", min_value=0.0, value=float(thu_hoi), step=1000.0,
                                  format="%.0f", key=f"{k}_m07_thuhoi_{int(thu_hoi)}",
                                  help="Mặc định lấy tổng tiền ở biên bản M06.")
        ghi_giam = c3.date_input("Ngày ghi giảm tài sản", value=None, format="DD/MM/YYYY", key=f"{k}_m07_gg",
                                 help="Để trống nếu kế toán chưa ghi giảm.")
        c1, c2, c3, c4 = st.columns(4)
        nguoi_lap = c1.text_input("Ký: Người lập báo cáo", user.name, key=f"{k}_m07_lap")
        ke_toan = c2.text_input("Ký: Đơn vị phụ trách kế toán", key=f"{k}_m07_kt")
        quan_ly = c3.text_input("Ký: Đơn vị QLTS / Hội đồng thanh lý", key=f"{k}_m07_ql")
        tham_quyen = c4.text_input("Ký: Cấp thẩm quyền", key=f"{k}_m07_tq")
        kq = hoso.KetQua(items=items_r, can_cu=can_cu.strip(), nhan_su=[n for n in nhan_su if n[0]],
                         chi_phi=chi_phi.strip(), gia_tri_thu_hoi=gia_tri, ngay_ghi_giam=ghi_giam,
                         nguoi_lap=nguoi_lap.strip(), ke_toan=ke_toan.strip(), quan_ly=quan_ly.strip(),
                         tham_quyen=tham_quyen.strip())
        hoso_downloads(lambda: hoso.m07_docx(kq), lambda: hoso.m07_pdf(kq), f"M07_bao_cao_ket_qua_thanh_ly_{stem}",
                       f"{k}_m07")


# ---------------------------------------------------------------------------
with tab_rounds:
    if history.empty:
        st.info("Chưa có đợt thanh lý nào được lưu." if not history_error else "Chưa có list ThanhLy (xem hướng dẫn ở trên).")
    else:
        rounds = (history.assign(_d=history["NgayThanhLy"]).groupby("DotThanhLy", sort=False)
                  .agg(SoTB=("id", "size"), Ngay=("_d", "max"), SoTT=("SoToTrinh", "first"),
                       TongSL=("SoLuong", "sum"), GiaMua=("GiaMua", "sum"))
                  .reset_index().sort_values("Ngay", ascending=False))
        st.dataframe(rounds, hide_index=True, width="stretch", column_config={
            "DotThanhLy": "Đợt thanh lý", "SoTB": "Số tài sản", "Ngay": "Ngày thanh lý", "SoTT": "Số tờ trình",
            "TongSL": "Tổng số lượng", "GiaMua": st.column_config.NumberColumn("Tổng giá mua", format="localized")})
        dot = st.selectbox("Xem / in lại đợt", list(rounds["DotThanhLy"]), key="tl_round")
        rows = history[history["DotThanhLy"] == dot]
        items_r = round_items(rows)
        st.dataframe(items_r.drop(columns="id"), hide_index=True, width="stretch", column_config={
            "ngay_mua": "Ngày mua", "ma": "Mã tài sản", "ten": "Tên tài sản", "dac_diem": "Đặc điểm", "dvt": "Đvt",
            "sl": "SL", "gia_mua": st.column_config.NumberColumn("Giá mua mới", format="localized"),
            "con_lai": st.column_config.NumberColumn("Giá trị còn lại", format="localized"),
            "don_vi": "Đơn vị sử dụng", "tinh_trang": "Tình trạng", "du_kien": "Dự kiến", "ghi_chu": "Ghi chú"})
        try:
            ngay_r = date.fromisoformat(rows["NgayThanhLy"].max())
        except ValueError:
            ngay_r = date.today()
        ty, nd = default_texts(items_r, ngay_r)
        tl_r = thanhly.ThanhLy(items=items_r, ngay=ngay_r, so=rows["SoToTrinh"].iloc[0], trich_yeu=ty,
                               noi_dung=nd, hinh_thuc=HINH_THUC, bao_cao=BAO_CAO, trien_khai=ngay_r,
                               tieu_de_phu=dot, ky_quan_ly=user.name)
        with st.container(border=True):
            st.markdown(f"**In lại biểu mẫu – {dot}** (nội dung tờ trình dùng mẫu mặc định; muốn sửa, mở bản Word)")
            downloads(tl_r, f"{dot}".replace(" ", "_").replace("–", "-"), key="tlr")
        with st.container(border=True):
            render_hoso(dot, rows, items_r, ngay_r)
        st.download_button("Tải danh sách đợt này (Excel)", on_click="ignore",
                           data=lambda: ui.to_excel({"ThanhLy": rows.drop(columns="id").rename(
                               columns=schema.labels_of(schema.THANH_LY))}),
                           file_name=f"thanh_ly_{dot}.xlsx", icon=":material/download:")

# ---------------------------------------------------------------------------
with tab_done:
    done = tb[thietbi.is_disposed(tb)]
    st.caption(f"{len(done)} tài sản đã thanh lý (Tình trạng “{STATUS}” hoặc Nơi sử dụng “{schema.NOI_THANH_LY}”).")
    ui.show_table(done, schema.THIET_BI, ["MaChiTiet", "TenThietBi", "DacDiem", "NoiSuDung", "TinhTrang",
                                          "GiaTri", "NgayMua", "GhiChu"])

# ---------------------------------------------------------------------------
with tab_new:
    # ---- 1. Chọn tài sản ----
    with st.container(border=True):
        st.markdown("**1. Chọn tài sản cần thanh lý** – lọc, tick các dòng rồi bấm *Thêm vào danh sách*")
        pool = tb[~thietbi.is_disposed(tb) & ~tb["id"].isin(cart)]
        filtered = ui.equipment_filters(pool, "tl").reset_index(drop=True)
        event = st.dataframe(
            filtered[ui.TB_VIEW].rename(columns=schema.labels_of(schema.THIET_BI)), hide_index=True,
            width="stretch", height=300, on_select="rerun", selection_mode="multi-row",
            key=f"tl_pick_{len(cart)}", column_config={"Giá trị": st.column_config.NumberColumn(format="localized")},
        )
        picked = filtered.iloc[event.selection.rows]
        if st.button(f"Thêm {len(picked)} tài sản vào danh sách thanh lý", icon=":material/playlist_add:",
                     disabled=picked.empty, type="primary"):
            cart.extend(i for i in picked["id"] if i not in cart)
            st.rerun()

    chosen = tb[tb["id"].isin(cart)].set_index("id").loc[[i for i in cart if i in set(tb["id"])]].reset_index()
    if chosen.empty:
        st.info("Chưa có tài sản nào trong danh sách thanh lý.", icon=":material/touch_app:")
        st.stop()

    # ---- 2. Danh sách thanh lý (sửa được) ----
    with st.container(border=True):
        st.markdown(f"**2. Danh sách thanh lý – {len(chosen)} tài sản** (sửa Tình trạng, Giá trị còn lại, "
                    "Dự kiến thời gian, Ghi chú trực tiếp trong bảng)")
        c1, c2, c3 = st.columns(3)
        du_kien = c1.text_input("Dự kiến thời gian thanh lý (mặc định)", f"Tháng {date.today().month}/"
                                f"{date.today().year}", key="tl_dukien")
        ghi_chu = c2.text_input("Ghi chú / hình thức (mặc định)", "Hủy bỏ", key="tl_ghichu")
        if c3.button("Xóa hết danh sách", icon=":material/clear_all:"):
            cart.clear()
            st.rerun()
        base = thanhly.items_from(chosen, room_names, du_kien, ghi_chu)
        base.insert(0, "Bo", False)
        edited = st.data_editor(
            base, hide_index=True, width="stretch", key=f"tl_items_{len(cart)}_{du_kien}_{ghi_chu}",
            disabled=["ngay_mua", "ma", "ten", "dac_diem", "dvt", "gia_mua", "don_vi"],
            column_config={
                "id": None, "Bo": st.column_config.CheckboxColumn("Bỏ", help="Tick để bỏ khỏi danh sách"),
                "ngay_mua": "Ngày mua", "ma": "Mã tài sản", "ten": "Tên tài sản", "dac_diem": "Đặc điểm",
                "dvt": "Đvt", "sl": st.column_config.NumberColumn("SL", min_value=0),
                "gia_mua": st.column_config.NumberColumn("Giá mua mới", format="localized"),
                "con_lai": st.column_config.NumberColumn("Giá trị còn lại", format="localized", min_value=0),
                "don_vi": "Đơn vị sử dụng", "tinh_trang": "Tình trạng", "du_kien": "Dự kiến thời gian thanh lý",
                "ghi_chu": "Ghi chú",
            },
        )
        if edited["Bo"].any():
            if st.button(f"Bỏ {int(edited['Bo'].sum())} tài sản đã tick khỏi danh sách", icon=":material/remove:"):
                for i in edited.loc[edited["Bo"], "id"]:
                    cart.remove(i)
                st.rerun()
        items = edited[~edited["Bo"]].drop(columns="Bo").reset_index(drop=True)

    # ---- 3. Thông tin biểu mẫu ----
    ngay = date.today()
    with st.container(border=True):
        st.markdown("**3. Thông tin Kế hoạch & Tờ trình**")
        c1, c2, c3 = st.columns([1, 1, 2])
        ngay = c1.date_input("Ngày lập", value=ngay, format="DD/MM/YYYY", key="tl_ngay")
        so = c2.text_input("Số tờ trình", placeholder="VD: 491", key="tl_so")
        year = thanhly.school_year(ngay)
        n_dot = history.loc[history["DotThanhLy"].str.contains(year, regex=False), "DotThanhLy"].nunique() + 1
        dot = c3.text_input("Tên đợt thanh lý", f"Đợt {n_dot} – Niên độ {year}", key=f"tl_dot_{year}_{n_dot}",
                            help="Dùng để nhóm danh sách thanh lý theo đợt (tab Các đợt thanh lý) và in dưới "
                                 "tiêu đề Kế hoạch.")
        tieu_de_phu = dot
        ty, nd = default_texts(items, ngay)
        trich_yeu = st.text_input("Trích yếu tờ trình", ty, key=f"tl_ty_{hash(ty)}")
        noi_dung = st.text_area("Nội dung trình", nd, height=90, key=f"tl_nd_{hash(nd)}")
        hinh_thuc = st.text_area("Hình thức thanh lý", HINH_THUC, height=68, key="tl_ht")
        bao_cao = st.text_area("Báo cáo kết quả thanh lý", BAO_CAO, height=68, key="tl_bc")
        c1, c2, c3, c4 = st.columns(4)
        trien_khai = c1.date_input("Thời điểm triển khai", value=ngay, format="DD/MM/YYYY", key="tl_tk")
        ky_ql = c2.text_input("Ký: Đơn vị quản lý tài sản", user.name, key="tl_kyql")
        ky_kt = c3.text_input("Ký: Đơn vị phụ trách kế toán", key="tl_kykt")
        ky_pd = c4.text_input("Ký: Phê duyệt", key="tl_kypd")

    tl = thanhly.ThanhLy(
        items=items, ngay=ngay, so=so.strip(), trich_yeu=trich_yeu.strip(), noi_dung=noi_dung.strip(),
        hinh_thuc=hinh_thuc.strip(), bao_cao=bao_cao.strip(), trien_khai=trien_khai, tieu_de_phu=tieu_de_phu.strip(),
        ky_quan_ly=ky_ql.strip(), ky_ke_toan=ky_kt.strip(), ky_phe_duyet=ky_pd.strip(),
    )

    # ---- 4. Xuất biểu mẫu ----
    with st.container(border=True):
        st.markdown(f"**4. In biểu mẫu** – {len(items)} tài sản, tổng số lượng {thanhly.qty(tl.total)}")
        downloads(tl, f"thanh_ly_{ngay:%Y%m%d}", key="tln")

    # ---- 5. Xác nhận thanh lý ----
    with st.container(border=True):
        st.markdown(f"**5. Xác nhận thanh lý** – cập nhật Tình trạng = “{STATUS}” cho {len(items)} tài sản trên "
                    f"SharePoint (ghi chú thêm số tờ trình, ngày) và lưu danh sách vào **{dot}** (list ThanhLy). "
                    "Tài sản đã thanh lý sẽ ẩn khỏi các màn hình chung. Sau khi xác nhận, lập tiếp 3 mẫu hồ sơ "
                    "(M02 đề nghị mang ra ngoài, M06 biên bản bàn giao – thanh lý, M07 báo cáo kết quả) ở tab "
                    "**Các đợt thanh lý**.")

        def confirm() -> str | None:
            note = f"Thanh lý theo TTr {tl.so_line()[4:]} ngày {ngay:%d/%m/%Y}" if so.strip() \
                else f"Thanh lý ngày {ngay:%d/%m/%Y}"
            old = chosen.set_index("id")["GhiChu"]
            ops = [("update", i, {"TinhTrang": STATUS,
                                  "GhiChu": (f"{old[i]}; {note}" if old.get(i) else note)}) for i in items["id"]]
            info = chosen.set_index("id")
            records = [("create", {
                "Title": r.ma, "DotThanhLy": dot.strip(), "SoToTrinh": so.strip(), "NgayThanhLy": ngay,
                "MaTaiSan": info.at[r.id, "MaTaiSan"], "TenThietBi": r.ten, "DacDiem": r.dac_diem, "DVT": r.dvt,
                "SoLuong": float(r.sl or 0), "NamMua": r.ngay_mua, "GiaMua": float(r.gia_mua or 0),
                "GiaTriConLai": float(r.con_lai or 0), "NoiSuDung": r.don_vi, "TinhTrang": r.tinh_trang,
                "DuKien": r.du_kien, "GhiChu": r.ghi_chu, "NguoiThucHien": user.email,
            }) for r in items.itertuples()]
            saved_note = ""
            try:
                rec_errors = storage.batch(schema.THANH_LY, records)
                if rec_errors:
                    saved_note = f" Lưu lịch sử đợt bị {len(rec_errors)} lỗi: {rec_errors[0][:200]}"
            except storage.StorageError as exc:
                saved_note = f" Chưa lưu được danh sách đợt (list ThanhLy): {str(exc)[:200]}"
            errors = storage.batch(schema.THIET_BI, ops)
            if errors:
                return f"Có {len(errors)} lỗi:\n\n" + "\n\n".join(errors[:10]) + saved_note
            for i in items["id"]:
                cart.remove(i)
            if not saved_note:
                st.session_state["tl_round"] = dot.strip()  # mở sẵn đợt này ở tab Các đợt thanh lý
            ui.flash(f"Đã chuyển {len(ops)} tài sản sang “{STATUS}” và lưu vào {dot}.{saved_note} "
                     "Tiếp theo: tab **Các đợt thanh lý** → lập 3 mẫu hồ sơ sau thanh lý (M02, M06, M07).")

        if st.button("Xác nhận thanh lý", icon=":material/delete_sweep:", key="act_del_tl", disabled=items.empty):
            ui.confirm_dialog(
                "Xác nhận thanh lý", f"Chuyển **{len(items)} tài sản** sang tình trạng **{STATUS}**? "
                "Tài sản sẽ không còn tính vào danh sách đang sử dụng, kiểm kê, bàn giao.",
                confirm, confirm_label="Đồng ý thanh lý",
                details=[f"{r.ma} – {r.ten} ({r.don_vi})" for r in items.itertuples()],
            )
