"""Quản lý list thiết bị dạng bảng: sửa trực tiếp, thêm/xóa dòng, nhập/xuất Excel."""

import pandas as pd
import streamlit as st

from qlts import auth, schema, storage, thietbi, ui

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


def parse_number(value):
    """'12000000', '12000000.0', '12.000.000', '12,000,000' -> 12000000."""
    text = str(value).strip().replace(" ", "")
    num = pd.to_numeric(text, errors="coerce")
    if pd.isna(num):
        num = pd.to_numeric(text.replace(".", "").replace(",", ""), errors="coerce")
    return None if pd.isna(num) else float(num)


def same(a, b) -> bool:
    if pd.isna(a) and pd.isna(b):
        return True
    if pd.isna(a) or pd.isna(b):
        return (a if not pd.isna(a) else b) in ("", 0)
    return a == b


def new_row_fields(row: dict, used_codes: dict, stt: list) -> dict | str:
    """Chuẩn bị một dòng mới: sinh Mã chi tiết, STT, Quản lý phòng. Trả về chuỗi lỗi nếu thiếu dữ liệu."""
    fields = {k: v for k, v in row.items() if k in all_cols and not (isinstance(v, float) and pd.isna(v))}
    ma = str(fields.get("MaTaiSan") or "").strip()
    code = str(fields.get("MaChiTiet") or "").strip()
    if not code:
        if not ma:
            return "thiếu Mã tài sản"
        fresh = used_codes.setdefault(ma, [])
        code = thietbi.next_detail_codes(pd.DataFrame({"MaChiTiet": [*tb["MaChiTiet"], *fresh]}), ma)[0]
        fresh.append(code)
    elif not ma and "-" in code:
        ma = code.rsplit("-", 1)[0]
    fields["MaTaiSan"], fields["MaChiTiet"] = ma, code
    if not fields.get("STT"):
        stt[0] += 1
        fields["STT"] = stt[0]
    room = str(fields.get("NoiSuDung") or "").strip()
    if room and not fields.get("QuanLyPhong"):
        fields["QuanLyPhong"] = managers.get(room, "")
    fields.setdefault("QuanLyThietBi", user.name)
    return fields


tab_edit, tab_import = st.tabs(["Xem & sửa", "Nhập / xuất Excel"])

# ---------------------------------------------------------------------------
with tab_edit:
    filtered = ui.equipment_filters(tb, "ds")
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
    confirm_delete = True
    if deleted:
        confirm_delete = st.checkbox(f"Xác nhận xóa {len(deleted)} thiết bị: " +
                                     ", ".join(before.loc[deleted, "MaChiTiet"].head(10)) +
                                     (" ..." if len(deleted) > 10 else ""))
    c1, c2 = st.columns([1, 5])
    save = c1.button("Lưu thay đổi", type="primary", icon=":material/save:",
                     disabled=not (updates or creates or deleted) or bool(problems) or not confirm_delete)
    if c2.button("Hủy thay đổi", icon=":material/undo:"):
        st.session_state["ds_version"] = version + 1
        st.rerun()
    if save:
        ops = [*updates, *creates, *(("delete", i) for i in deleted)]
        bar = st.progress(0.0, text="Đang lưu lên SharePoint...")
        errors = storage.batch(TB, ops, progress=lambda f: bar.progress(f, text="Đang lưu lên SharePoint..."))
        bar.empty()
        if errors:
            st.session_state["ds_version"] = version + 1
            st.error(f"Lưu xong nhưng có {len(errors)} lỗi:\n\n" + "\n\n".join(errors[:20]))
        else:
            st.session_state["ds_version"] = version + 1
            ui.flash(f"Đã lưu: {len(updates)} sửa, {len(creates)} thêm mới, {len(deleted)} xóa.")
            st.rerun()

# ---------------------------------------------------------------------------
with tab_import:
    st.markdown("##### Xuất Excel")
    export = tb.drop(columns="id").rename(columns=labels)
    st.download_button("Tải toàn bộ danh sách (Excel)", ui.to_excel({"ThietBi": export}),
                       file_name="danh_sach_thiet_bi.xlsx", icon=":material/download:")
    template = pd.DataFrame(columns=[labels[c] for c in all_cols if c not in ("STT",)])
    st.download_button("Tải file mẫu để nhập", ui.to_excel({"ThietBi": template}),
                       file_name="mau_nhap_thiet_bi.xlsx", icon=":material/description:")

    st.markdown("##### Nhập từ Excel")
    st.caption(
        "Dòng đầu là tên cột (như file mẫu). Dòng có **Mã chi tiết đã tồn tại** sẽ được cập nhật; dòng mới "
        "để trống Mã chi tiết thì app tự sinh theo Mã tài sản. Ô trống không ghi đè dữ liệu đang có."
    )
    upload = st.file_uploader("Chọn file .xlsx hoặc .csv", type=["xlsx", "csv"])
    if upload is not None:
        raw = pd.read_csv(upload, dtype=str) if upload.name.endswith(".csv") else pd.read_excel(upload, dtype=str)
        by_label = {schema_label.lower(): key for key, schema_label in labels.items()}
        by_label.update({k.lower(): k for k in all_cols})
        rename = {c: by_label[str(c).strip().lower()] for c in raw.columns if str(c).strip().lower() in by_label}
        unknown = [c for c in raw.columns if c not in rename]
        data = raw.rename(columns=rename)[list(rename.values())].dropna(how="all")
        st.write(f"Đọc được **{len(data)}** dòng, **{len(rename)}** cột khớp.")
        if unknown:
            st.warning("Bỏ qua các cột không nhận ra: " + ", ".join(map(str, unknown)))
        st.dataframe(data.head(20), hide_index=True, width="stretch")

        existing = tb.drop_duplicates("MaChiTiet").set_index("MaChiTiet")
        ops, problems = [], []
        used_codes: dict = {}
        stt = [int(tb["STT"].max()) if not tb.empty else 0]
        for n, row in enumerate(data.to_dict("records"), start=2):
            row = {k: v.strip() if isinstance(v, str) else v for k, v in row.items() if not pd.isna(v) and v != ""}
            for c in num_cols:
                if c in row:
                    row[c] = parse_number(row[c])
            for c in date_cols:
                if c in row:
                    d = pd.to_datetime(row[c], dayfirst=True, errors="coerce")
                    row[c] = d.date() if not pd.isna(d) else row[c]
            code = str(row.get("MaChiTiet", ""))
            if code and code in existing.index:
                ops.append(("update", existing.loc[code, "id"], row))
            else:
                fields = new_row_fields(row, used_codes, stt)
                if isinstance(fields, str):
                    problems.append(f"Dòng Excel {n}: {fields}")
                else:
                    ops.append(("create", fields))
        n_upd = sum(op[0] == "update" for op in ops)
        st.info(f"Sẽ cập nhật **{n_upd}** thiết bị và thêm mới **{len(ops) - n_upd}** thiết bị.")
        for p in problems[:20]:
            st.error(p)
        if st.button("Nhập vào SharePoint", type="primary", icon=":material/upload:", disabled=not ops):
            bar = st.progress(0.0, text="Đang nhập...")
            errors = storage.batch(TB, ops, progress=lambda f: bar.progress(f, text="Đang nhập..."))
            bar.empty()
            if errors:
                st.error(f"Có {len(errors)} lỗi:\n\n" + "\n\n".join(errors[:20]))
            else:
                ui.flash(f"Đã nhập {len(ops)} dòng từ Excel.")
                st.session_state["ds_version"] = version + 1
                st.rerun()
