"""Thanh lý tài sản: chọn tài sản -> Kế hoạch thanh lý + Tờ trình -> đánh dấu 'Đã thanh lý' trên SharePoint."""

from datetime import date

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

tab_new, tab_done = st.tabs(["Lập thanh lý", "Tài sản đã thanh lý"])

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
    types = ", ".join(dict.fromkeys(t.strip().lower() for t in items["ten"] if t.strip()))
    rooms = ", ".join(dict.fromkeys(r for r in items["don_vi"] if r))
    ngay = date.today()
    with st.container(border=True):
        st.markdown("**3. Thông tin Kế hoạch & Tờ trình**")
        c1, c2, c3 = st.columns([1, 1, 2])
        ngay = c1.date_input("Ngày lập", value=ngay, format="DD/MM/YYYY", key="tl_ngay")
        so = c2.text_input("Số tờ trình", placeholder="VD: 491", key="tl_so")
        tieu_de_phu = c3.text_input("Dòng dưới tiêu đề Kế hoạch", f"Đợt 1 – Niên độ {thanhly.school_year(ngay)}",
                                    key="tl_phu")
        trich_yeu = st.text_input("Trích yếu tờ trình", f"Vv thanh lý {types} hư hỏng năm học "
                                  f"{thanhly.school_year(ngay)}", key=f"tl_ty_{types}")
        noi_dung = st.text_area(
            "Nội dung trình", height=90, key=f"tl_nd_{types}_{rooms}",
            value="Trên cơ sở thực tế, sau khi tiến hành rà soát và đánh giá hiện trạng tài sản. Kính trình Ban "
                  f"giám hiệu về việc thanh lý {types} hư hỏng của {rooms} cụ thể như sau:")
        hinh_thuc = st.text_area(
            "Hình thức thanh lý", height=68, key="tl_ht",
            value="Bán phế liệu. Bộ phận Quản lý hệ thống sẽ chịu trách nhiệm đầu mối triển khai hướng bán phế liệu "
                  "đề xuất thanh lý nêu trên. Chi phí thanh lý dự kiến thu hồi: ...... đồng.")
        bao_cao = st.text_area(
            "Báo cáo kết quả thanh lý", height=68, key="tl_bc",
            value="Sau khi thực hiện xong công tác thanh lý, Bộ phận quản lý CNTT sẽ kết hợp với Phòng Kế toán báo "
                  "cáo kết quả thanh lý.")
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
        stem = f"thanh_ly_{ngay:%Y%m%d}"
        xlsx = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        docx = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        st.caption("Biểu mẫu 1 – Kế hoạch thanh lý")
        c1, c2 = st.columns(2)
        c1.download_button("Kế hoạch – PDF", lambda: thanhly.kh_pdf(tl), f"ke_hoach_{stem}.pdf", "application/pdf",
                           icon=":material/picture_as_pdf:", width="stretch", on_click="ignore", type="primary")
        c2.download_button("Kế hoạch – Excel", lambda: thanhly.kh_xlsx(tl), f"ke_hoach_{stem}.xlsx", xlsx,
                           icon=":material/table:", width="stretch", on_click="ignore")
        st.caption("Biểu mẫu 2 – Tờ trình phê duyệt thanh lý")
        c1, c2 = st.columns(2)
        c1.download_button("Tờ trình – PDF", lambda: thanhly.tt_pdf(tl), f"to_trinh_{stem}.pdf", "application/pdf",
                           icon=":material/picture_as_pdf:", width="stretch", on_click="ignore", type="primary")
        c2.download_button("Tờ trình – Word", lambda: thanhly.tt_docx(tl), f"to_trinh_{stem}.docx", docx,
                           icon=":material/description:", width="stretch", on_click="ignore")

    # ---- 5. Xác nhận thanh lý ----
    with st.container(border=True):
        st.markdown(f"**5. Xác nhận thanh lý** – cập nhật Tình trạng = “{STATUS}” cho {len(items)} tài sản trên "
                    "SharePoint (ghi chú thêm số tờ trình và ngày).")

        def confirm() -> str | None:
            note = f"Thanh lý theo TTr {tl.so_line()[4:]} ngày {ngay:%d/%m/%Y}" if so.strip() \
                else f"Thanh lý ngày {ngay:%d/%m/%Y}"
            old = chosen.set_index("id")["GhiChu"]
            ops = [("update", i, {"TinhTrang": STATUS,
                                  "GhiChu": (f"{old[i]}; {note}" if old.get(i) else note)}) for i in items["id"]]
            errors = storage.batch(schema.THIET_BI, ops)
            if errors:
                return f"Có {len(errors)} lỗi:\n\n" + "\n\n".join(errors[:10])
            for i in items["id"]:
                cart.remove(i)
            ui.flash(f"Đã chuyển {len(ops)} tài sản sang “{STATUS}”.")

        if st.button("Xác nhận thanh lý", icon=":material/delete_sweep:", key="act_del_tl", disabled=items.empty):
            ui.confirm_dialog(
                "Xác nhận thanh lý", f"Chuyển **{len(items)} tài sản** sang tình trạng **{STATUS}**? "
                "Tài sản sẽ không còn tính vào danh sách đang sử dụng, kiểm kê, bàn giao.",
                confirm, confirm_label="Đồng ý thanh lý",
                details=[f"{r.ma} – {r.ten} ({r.don_vi})" for r in items.itertuples()],
            )
