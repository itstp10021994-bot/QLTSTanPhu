"""Thành phần giao diện dùng chung."""

from __future__ import annotations

import io
from pathlib import Path

import pandas as pd
import streamlit as st

from . import schema, storage
from .config import app_setting

ASSETS = Path(__file__).resolve().parent.parent / "assets"

CSS = """
<style>
[data-testid="stMainBlockContainer"], .block-container {padding-top: 3.5rem !important;}
.qlts-header {display:flex; align-items:center; justify-content:space-between;
  border-bottom:1px solid rgba(128,128,128,.25); padding:.4rem 0 .8rem; margin-bottom:1rem; gap:1rem; flex-wrap:wrap}
.qlts-school {font-size:.8rem; line-height:1.2; color:#1f3a93; font-weight:600}
.qlts-title {color:#e00000; font-weight:700; font-size:1.35rem; text-align:center; flex:1}
.qlts-user {color:#1f4e8c; font-weight:600; font-size:.95rem}
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
        st.caption(":orange[● Chế độ demo] — dữ liệu lưu cục bộ, chưa kết nối SharePoint.")


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
    st.dataframe(view, hide_index=True, width="stretch", **kwargs)


def room_label_map() -> dict[str, str]:
    phong = storage.load(schema.PHONG)
    return {r.Title: f"{r.Title} - {r.TenPhong}" if r.TenPhong else r.Title for r in phong.itertuples()}


def to_excel(sheets: dict[str, pd.DataFrame]) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        for name, df in sheets.items():
            df.to_excel(writer, sheet_name=name[:31], index=False)
    return buf.getvalue()


def equipment_filters(df: pd.DataFrame, key: str, rooms: list[str] | None = None) -> pd.DataFrame:
    """Bộ lọc tìm kiếm thiết bị (từ khóa, phòng, loại, tình trạng)."""
    labels = room_label_map()
    c1, c2, c3, c4 = st.columns([2, 1.3, 1.3, 1.3])
    kw = c1.text_input("Tìm kiếm (mã / tên thiết bị)", key=f"{key}_kw")
    room_opts = rooms if rooms is not None else sorted(set(df["MaPhong"]) - {""})
    sel_rooms = c2.multiselect("Phòng", room_opts, key=f"{key}_room", format_func=lambda r: labels.get(r, r))
    sel_types = c3.multiselect("Loại", schema.LOAI_THIET_BI, key=f"{key}_type")
    sel_state = c4.multiselect("Tình trạng", schema.TINH_TRANG, key=f"{key}_state")
    if kw:
        mask = df["Title"].str.contains(kw, case=False, regex=False) | df["TenThietBi"].str.contains(
            kw, case=False, regex=False
        )
        df = df[mask]
    if sel_rooms:
        df = df[df["MaPhong"].isin(sel_rooms)]
    if sel_types:
        df = df[df["LoaiThietBi"].isin(sel_types)]
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
