"""Thành phần giao diện dùng chung."""

from __future__ import annotations

import io
from pathlib import Path

import pandas as pd
import streamlit as st

from . import schema, storage
from .config import app_setting, sharepoint_config_problem

ASSETS = Path(__file__).resolve().parent.parent / "assets"

CSS = """
<style>
[data-testid="stMainBlockContainer"], .block-container {padding-top: 3.5rem !important;}
.qlts-header {display:flex; align-items:center; justify-content:space-between;
  border-bottom:1px solid rgba(128,128,128,.25); padding:.4rem 0 .8rem; margin-bottom:1rem; gap:1rem; flex-wrap:wrap}
.qlts-school {font-size:.8rem; line-height:1.2; color:#1f3a93; font-weight:600}
.qlts-title {color:#e00000; font-weight:700; font-size:1.35rem; text-align:center; flex:1}
.qlts-user {color:#1f4e8c; font-weight:600; font-size:.95rem}
.st-key-dlg_confirm button, [class*="st-key-act_del"] button {background:#d32f2f !important;
  border-color:#d32f2f !important; color:#fff !important}
.st-key-dlg_confirm button:hover, [class*="st-key-act_del"] button:hover {background:#b71c1c !important}
[class*="st-key-act_del"] button:disabled {background:transparent !important; color:rgba(128,128,128,.6) !important;
  border-color:rgba(128,128,128,.3) !important}
.qlts-footer {text-align:center; font-style:italic; color:#1f4e8c; margin-top:2.5rem;
  border-top:1px solid rgba(128,128,128,.25); padding-top:.6rem; font-size:.9rem}
</style>
"""


def header(user_name: str) -> None:
    school = app_setting("school_name", "TRƯỜNG TH-THCS-THPT TÂN PHÚ")
    title = app_setting("app_title", "ỨNG DỤNG QUẢN LÝ THIẾT BỊ")
    st.markdown(CSS, unsafe_allow_html=True)
    st.markdown(
        f"""<div class="qlts-header">
              <div class="qlts-school">{school}</div>
              <div class="qlts-title">{title}</div>
              <div class="qlts-user">{user_name}</div>
            </div>""",
        unsafe_allow_html=True,
    )
    if storage.is_demo():
        problem = sharepoint_config_problem() or "Chưa cấu hình kết nối SharePoint trong Secrets."
        st.warning(
            "**CHẾ ĐỘ DEMO – dữ liệu KHÔNG được ghi lên SharePoint** (chỉ lưu tạm trong app, mất khi app khởi động lại). "
            f"{problem} Admin xem chi tiết ở **Phân quyền → Kết nối SharePoint**.",
            icon=":material/warning:",
        )


def footer() -> None:
    text = app_setting("footer", "Ứng dụng được phát triển bởi trường TH, THCS và THPT Tân Phú")
    st.markdown(f'<div class="qlts-footer">{text}</div>', unsafe_allow_html=True)


def logo_path() -> str | None:
    for name in ("logo.png", "logo.jpg", "logo.svg"):
        if (ASSETS / name).exists():
            return str(ASSETS / name)
    return None


def money(value: float) -> str:
    return f"{value:,.0f} đ".replace(",", ".")


def money_short(value: float) -> str:
    """Rút gọn số tiền cho thẻ số liệu: 581,5 triệu / 1,2 tỷ."""
    if abs(value) >= 1e9:
        return f"{value / 1e9:,.2f} tỷ".replace(".", ",")
    if abs(value) >= 1e6:
        return f"{value / 1e6:,.1f} triệu".replace(".", ",")
    return money(value)


def show_table(df: pd.DataFrame, list_name: str, columns: list[str] | None = None, **kwargs) -> None:
    """Hiển thị bảng với nhãn cột tiếng Việt."""
    columns = columns or schema.columns_of(list_name)
    view = df[columns].rename(columns=schema.labels_of(list_name))
    config = {label: st.column_config.NumberColumn(label, format="localized")
              for col, label in schema.labels_of(list_name).items()
              if col in columns and schema.column_type(list_name, col) == "number"}
    st.dataframe(view, hide_index=True, width="stretch", column_config=config, **kwargs)


def room_label_map() -> dict[str, str]:
    """Mã phòng -> nhãn hiển thị; gồm cả các "Nơi sử dụng" chưa có trong danh mục phòng."""
    from . import thietbi

    phong = storage.load(schema.PHONG).set_index("Title")["TenPhong"].to_dict()
    return {r: f"{r} - {phong[r]}" if phong.get(r) and phong[r].strip() != r else r for r in thietbi.all_rooms()}


def to_excel(sheets: dict[str, pd.DataFrame]) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        for name, df in sheets.items():
            df.to_excel(writer, sheet_name=name[:31], index=False)
    return buf.getvalue()


TB_VIEW = ["MaChiTiet", "TenThietBi", "DacDiem", "TenPhongBan", "NoiSuDung", "NguoiSuDung",
           "TinhTrang", "MaSAP", "GiaTri", "NgayMua"]
TB_SEARCH = ["MaChiTiet", "MaTaiSan", "TenThietBi", "ChiTiet", "DacDiem", "TenPhongBan", "MaSAP", "NguoiSuDung"]


def equipment_filters(df: pd.DataFrame, key: str, rooms: list[str] | None = None) -> pd.DataFrame:
    """Bộ lọc tìm kiếm thiết bị (từ khóa, nơi sử dụng, nhóm, tình trạng)."""
    labels = room_label_map()
    c1, c2, c3, c4 = st.columns([2, 1.3, 1.3, 1.3])
    kw = c1.text_input("Tìm kiếm (mã, tên, đặc điểm, serial, mã SAP...)", key=f"{key}_kw")
    room_opts = rooms if rooms is not None else sorted(set(df["NoiSuDung"]) - {""})
    sel_rooms = c2.multiselect("Nơi sử dụng", room_opts, key=f"{key}_room", format_func=lambda r: labels.get(r, r))
    sel_groups = c3.multiselect("Nhóm thiết bị", sorted(set(df["NhomThietBi"]) - {""}), key=f"{key}_group")
    sel_state = c4.multiselect("Tình trạng", sorted(set(df["TinhTrang"]) - {""}), key=f"{key}_state")
    if kw:
        mask = pd.Series(False, index=df.index)
        for col in TB_SEARCH:
            mask |= df[col].str.contains(kw, case=False, regex=False)
        df = df[mask]
    if sel_rooms:
        df = df[df["NoiSuDung"].isin(sel_rooms)]
    if sel_groups:
        df = df[df["NhomThietBi"].isin(sel_groups)]
    if sel_state:
        df = df[df["TinhTrang"].isin(sel_state)]
    return df


def flash(message: str) -> None:
    """Lưu thông báo để hiển thị sau khi trang tải lại (st.rerun)."""
    st.session_state["_flash"] = message


def show_flash() -> None:
    msg = st.session_state.pop("_flash", None)
    if msg:
        st.success(msg)


def user_picker(container, label: str, default: str = "", key: str | None = None, blank: str | None = None,
                help: str | None = None) -> str:
    """Ô chọn người dùng trong trường (gõ để tìm, hoặc nhập email mới). Trả về email (chữ thường)."""
    from . import thietbi

    users = thietbi.user_directory()
    default = (default or "").strip()
    if "@" in default:
        default = default.lower()  # email: không phân biệt hoa/thường; họ tên thì giữ nguyên
    options = list(users)
    if default and default not in users:
        options.insert(0, default)
    if blank is not None:
        options.insert(0, "")
    names = {**users}

    def fmt(email: str) -> str:
        if not email:
            return blank or ""
        return f"{names[email]} – {email}" if names.get(email) else email

    index = options.index(default) if default in options else (0 if blank is not None else None)
    value = container.selectbox(label, options, index=index, format_func=fmt, key=key, help=help,
                                accept_new_options=True, placeholder="Gõ tên hoặc email để tìm...")
    value = (value or "").strip()
    return value.lower() if "@" in value else value


def confirm_dialog(title: str, message: str, on_confirm, *, confirm_label: str = "Đồng ý xóa",
                   details: list[str] | None = None) -> None:
    """Hộp thoại hỏi xác nhận (dùng cho xóa). ``on_confirm()`` trả về chuỗi lỗi nếu thất bại."""

    @st.dialog(title)
    def _dialog():
        st.markdown(message)
        if details:
            shown = details[:15]
            st.markdown("\n".join(f"- {d}" for d in shown) + (f"\n- ... và {len(details) - 15} mục khác"
                                                                if len(details) > 15 else ""))
        st.caption("Thao tác này không thể hoàn tác.")
        c1, c2 = st.columns(2)
        if c1.button(confirm_label, key="dlg_confirm", icon=":material/delete_forever:", width="stretch"):
            with st.spinner("Đang xử lý..."):
                error = on_confirm()
            if error:
                st.error(error)
                return
            st.rerun()
        if c2.button("Hủy", key="dlg_cancel", icon=":material/close:", width="stretch"):
            st.rerun()

    _dialog()


def selection_actions(key: str, count: int, *, edit: bool = True, delete: bool = True, extra: str = ""):
    """Thanh nút Sửa / Xóa cho các dòng đang chọn. Trả về (bấm_sửa, bấm_xóa)."""
    cols = st.columns([1, 1, 4], vertical_alignment="center")
    edit_clicked = cols[0].button("Sửa", key=f"act_edit_{key}", icon=":material/edit:", type="primary",
                                  disabled=count != 1, width="stretch") if edit else False
    del_clicked = cols[1].button(f"Xóa ({count})" if count > 1 else "Xóa", key=f"act_del_{key}",
                                 icon=":material/delete:", disabled=count == 0, width="stretch") if delete else False
    hint = "Tick ô đầu dòng để chọn." if count == 0 else f"Đã chọn {count} dòng."
    if count > 1 and edit:
        hint += " Chọn đúng 1 dòng để sửa."
    cols[2].caption(hint + (" " + extra if extra else ""))
    return edit_clicked, del_clicked


def party_picker(container, label: str, default: str = "", key: str = "") -> tuple[str, str]:
    """Chọn một người trong danh sách user -> (Họ tên, Chức vụ), tự điền theo Phân quyền, cho phép sửa."""
    from . import thietbi

    with container:
        who = user_picker(st, label, default=default, key=f"{key}_who", blank="(Chọn người)")
        name, title = thietbi.person_info(who) if who else ("", "")
        c1, c2 = st.columns(2)
        name = c1.text_input("Họ và tên", name, key=f"{key}_name_{who}")
        title = c2.text_input("Chức vụ", title, key=f"{key}_title_{who}",
                              help="Tự lấy theo Chức danh ở Phân quyền admin; sửa nếu cần.")
    return name.strip(), title.strip()


def bienban_downloads(docs, file_stem: str, key: str, formats=("pdf", "xlsx", "docx")) -> None:
    """Các nút tải biên bản (tạo file khi bấm)."""
    from . import bienban

    spec = {
        "pdf": ("Tải PDF (in)", bienban.to_pdf, "application/pdf", ":material/picture_as_pdf:"),
        "xlsx": ("Tải Excel", bienban.to_xlsx,
                 "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", ":material/table:"),
        "docx": ("Tải Word (theo mẫu)", bienban.to_docx,
                 "application/vnd.openxmlformats-officedocument.wordprocessingml.document", ":material/description:"),
    }
    cols = st.columns(len(formats))
    for col, fmt in zip(cols, formats):
        label, fn, mime, icon = spec[fmt]
        col.download_button(label, data=lambda fn=fn: fn(docs), file_name=f"{file_stem}.{fmt}", mime=mime,
                            icon=icon, key=f"{key}_{fmt}", width="stretch", on_click="ignore",
                            type="primary" if fmt == formats[0] else "secondary")
