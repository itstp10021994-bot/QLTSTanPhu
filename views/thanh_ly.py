"""Thanh lý tài sản: chọn tài sản -> Kế hoạch thanh lý + Tờ trình -> đánh dấu 'Đã thanh lý' trên SharePoint."""

from datetime import date

import pandas as pd
import streamlit as st

from qlts import auth, schema, storage, thanhly, thietbi, ui
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
        st.download_button("Tải danh sách đợt này (Excel)",
                           ui.to_excel({"ThanhLy": rows.drop(columns="id").rename(
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
                    "Tài sản đã thanh lý sẽ ẩn khỏi các màn hình chung.")

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
            ui.flash(f"Đã chuyển {len(ops)} tài sản sang “{STATUS}” và lưu vào {dot}.{saved_note}")

        if st.button("Xác nhận thanh lý", icon=":material/delete_sweep:", key="act_del_tl", disabled=items.empty):
            ui.confirm_dialog(
                "Xác nhận thanh lý", f"Chuyển **{len(items)} tài sản** sang tình trạng **{STATUS}**? "
                "Tài sản sẽ không còn tính vào danh sách đang sử dụng, kiểm kê, bàn giao.",
                confirm, confirm_label="Đồng ý thanh lý",
                details=[f"{r.ma} – {r.ten} ({r.don_vi})" for r in items.itertuples()],
            )
