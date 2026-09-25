"""Quản lý list thiết bị dạng bảng: sửa trực tiếp, thêm/xóa dòng, nhập/xuất Excel."""

import pandas as pd
import streamlit as st

from qlts import auth, excel_io, schema, storage, thietbi, ui

user = auth.require(schema.ROLE_QLTS)
st.subheader("Danh sách thiết bị")

TB = schema.THIET_BI
labels = schema.labels_of(TB)
all_cols = schema.columns_of(TB)
date_cols = [c for c in all_cols if schema.column_type(TB, c) == "date"]
num_cols = [c for c in all_cols if schema.column_type(TB, c) == "number"]
DEFAULT_COLS = ["MaTaiSan", "MaChiTiet", "TenThietBi", "DacDiem", "TenPhongBan", "NoiSuDung", "NguoiSuDung",
                "TinhTrang", "QuanLyPhong", "MaSAP", "GiaTri", "NgayMua", "GhiChu"]

tb = storage.load(TB)
managers = thietbi.room_managers()
version = st.session_state.setdefault("ds_version", 0)


def to_editor(df: pd.DataFrame) -> pd.DataFrame:
    """Chuyển cột ngày sang kiểu date để sửa bằng lịch."""
    out = df.copy()
    for c in date_cols:
        if c in out.columns:
            out[c] = pd.to_datetime(out[c], format="%Y-%m-%d", errors="coerce").dt.date
    return out


def same(a, b) -> bool:
    if pd.isna(a) and pd.isna(b):
        return True
    if pd.isna(a) or pd.isna(b):
        return (a if not pd.isna(a) else b) in ("", 0)
    return a == b


def new_row_fields(row: dict, used_codes: dict, stt: list) -> dict | str:
    fields = {k: v for k, v in row.items() if k in all_cols and not (isinstance(v, float) and pd.isna(v))}
    return thietbi.prepare_new(fields, list(tb["MaChiTiet"]), used_codes, stt, managers, user.name)


tab_edit, tab_import = st.tabs(["Xem & sửa", "Nhập / xuất Excel"])

# ---------------------------------------------------------------------------
with tab_edit:
    show_all = st.toggle("Hiện cả tài sản đã thanh lý", key="ds_all",
                         help="Mặc định ẩn các tài sản đã thanh lý (xem ở mục Thanh lý tài sản).")
    filtered = ui.equipment_filters(tb if show_all else thietbi.active(tb), "ds")
    shown = st.multiselect("Cột hiển thị", all_cols, default=DEFAULT_COLS, format_func=labels.get, key="ds_cols")
    shown = ["MaTaiSan", "MaChiTiet", *[c for c in shown if c not in ("MaTaiSan", "MaChiTiet")]]
    initial = to_editor(filtered[["id", *shown]]).reset_index(drop=True)

    st.caption(
        f"{len(filtered)}/{len(tb)} thiết bị. Sửa trực tiếp trong ô; thêm dòng ở cuối bảng "
        "(nhập Mã tài sản, Mã chi tiết sẽ tự sinh); chọn dòng và nhấn Delete để xóa. Bấm **Lưu thay đổi** để ghi lên SharePoint."
    )
    config = {"id": None, "MaChiTiet": st.column_config.TextColumn(labels["MaChiTiet"], help="Tự sinh khi thêm mới")}
    for c in shown:
        if c in config:
            continue
        if c in date_cols:
            config[c] = st.column_config.DateColumn(labels[c], format="DD/MM/YYYY")
        elif c in num_cols:
            config[c] = st.column_config.NumberColumn(labels[c], format="localized", min_value=0)
        elif c == "TinhTrang":
            config[c] = st.column_config.SelectboxColumn(labels[c], options=thietbi.status_options(tb))
        else:
            config[c] = st.column_config.TextColumn(labels[c])
    edited = st.data_editor(initial, key=f"ds_editor_{version}", num_rows="dynamic", hide_index=True,
                            width="stretch", height=560, column_config=config, disabled=["MaChiTiet"])

    # ---- So sánh để tìm thay đổi ----
    before = initial.set_index("id")
    kept_ids = set(edited["id"].dropna())
    deleted = [i for i in before.index if i not in kept_ids]
    updates, creates, problems = [], [], []
    used_codes: dict = {}
    stt = [int(tb["STT"].max()) if not tb.empty else 0]
    for n, row in enumerate(edited.to_dict("records"), start=1):
        if row.get("id") in before.index:
            old = before.loc[row["id"]]
            changed = {c: row[c] for c in shown if not same(row[c], old[c])}
            if changed:
                updates.append(("update", row["id"], changed))
        elif any(not same(v, None) for k, v in row.items() if k != "id"):
            fields = new_row_fields(row, used_codes, stt)
            if isinstance(fields, str):
                problems.append(f"Dòng mới {n}: {fields}")
            else:
                creates.append(("create", fields))

    if updates or creates or deleted:
        st.info(f"Thay đổi chưa lưu: **{len(updates)}** dòng sửa, **{len(creates)}** dòng mới, "
                f"**{len(deleted)}** dòng xóa.", icon=":material/pending:")
    for p in problems:
        st.error(p)
    ops = [*updates, *creates, *(("delete", i) for i in deleted)]

    def save_all() -> str | None:
        bar = st.progress(0.0, text="Đang lưu lên SharePoint...")
        errors = storage.batch(TB, ops,
                               progress=lambda f, t="": bar.progress(f, text=f"Đang lưu lên SharePoint... {t}"))
        bar.empty()
        st.session_state["ds_version"] = version + 1
        if errors:
            return f"Lưu xong nhưng có {len(errors)} lỗi:\n\n" + "\n\n".join(errors[:20])
        ui.flash(f"Đã lưu: {len(updates)} sửa, {len(creates)} thêm mới, {len(deleted)} xóa.")

    c1, c2 = st.columns([1, 5])
    save = c1.button("Lưu thay đổi", type="primary", icon=":material/save:",
                     disabled=not ops or bool(problems))
    if c2.button("Hủy thay đổi", icon=":material/undo:"):
        st.session_state["ds_version"] = version + 1
        st.rerun()
    if save and deleted:
        # Có dòng bị xóa -> hỏi lại trước khi ghi
        ui.confirm_dialog(
            "Xác nhận lưu thay đổi",
            f"Bạn sắp **xóa {len(deleted)} thiết bị** khỏi SharePoint"
            + (f" (kèm {len(updates)} dòng sửa, {len(creates)} dòng mới)" if updates or creates else "")
            + ". Đồng ý?",
            save_all, confirm_label="Đồng ý xóa & lưu",
            details=[f"{r.MaChiTiet} – {getattr(r, 'TenThietBi', '')}" for r in before.loc[deleted].itertuples()],
        )
    elif save:
        error = save_all()
        if error:
            st.error(error)
        else:
            st.rerun()

# ---------------------------------------------------------------------------
with tab_import:
    st.markdown("##### Xuất Excel")
    export = tb.drop(columns="id").rename(columns=labels)
    st.download_button("Tải toàn bộ danh sách (Excel)", ui.to_excel({"ThietBi": export}),
                       file_name="danh_sach_thiet_bi.xlsx", icon=":material/download:")
    st.download_button("Tải file mẫu để nhập", excel_io.template_workbook(TB, "Thiết bị"),
                       file_name="mau_nhap_thiet_bi.xlsx", icon=":material/description:")

    st.markdown("##### Nhập từ Excel")
    st.caption(
        "Dòng đầu là tên cột (như file mẫu). Dòng có **Mã chi tiết đã tồn tại** được ghi đè – chỉ những ô khác "
        "dữ liệu hiện có mới được cập nhật; dòng mới (để trống Mã chi tiết thì app tự sinh theo Mã tài sản) được "
        "thêm vào. Ô trống không xóa dữ liệu đang có."
    )
    upload = st.file_uploader("Chọn file .xlsx hoặc .csv", type=["xlsx", "csv"], key=f"ds_upload_{version}")
    if upload is not None:
        data, unknown = excel_io.read_upload(upload, TB)
        st.write(f"Đọc được **{len(data)}** dòng, **{len(data.columns)}** cột khớp.")
        if unknown:
            st.warning("Bỏ qua các cột không nhận ra: " + ", ".join(unknown))
        st.dataframe(data.head(20).astype(object).fillna("").rename(columns=labels), hide_index=True, width="stretch")
        plan = excel_io.plan_import(TB, data, tb, update_existing=True, user_name=user.name, managers=managers,
                                    writable=storage.writable_columns(TB))
        st.info(f"Sẽ thêm mới **{plan['create']}** thiết bị, cập nhật **{plan['update']}** thiết bị có thay đổi; "
                f"**{plan['same']}** thiết bị giống hệt dữ liệu hiện có sẽ bỏ qua.")
        if plan["changes"]:
            with st.expander(f"Xem {len(plan['changes'])} ô sẽ được ghi đè"):
                st.dataframe(plan["changes"], hide_index=True, width="stretch")
        _w = storage.writable_columns(TB)
        _skip = [c for c in data.columns if _w is not None and c not in _w]
        if _skip:
            st.warning("Các cột sau không có (hoặc chỉ đọc) trên SharePoint nên sẽ không được ghi: "
                       + ", ".join(schema.labels_of(TB).get(c, c) for c in _skip))
        for p in plan["problems"][:20]:
            st.error(p)
        ui.reconcile_panel(TB, data, tb, key=f"ds_rec_{version}")
        if st.button("Nhập vào SharePoint", type="primary", icon=":material/upload:", disabled=not plan["ops"]):
            bar = st.progress(0.0, text="Đang nhập...")
            errors = storage.batch(TB, plan["ops"],
                                   progress=lambda f, t="": bar.progress(f, text=f"Đang nhập... {t}"))
            bar.empty()
            if errors:
                st.error(f"Có {len(errors)} lỗi:\n\n" + "\n\n".join(errors[:20]))
            else:
                ui.flash(f"Đã nhập {len(plan['ops'])} dòng từ Excel.")
                st.session_state["ds_version"] = version + 1
                st.rerun()
