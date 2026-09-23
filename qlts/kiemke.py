"""Màn hình kiểm kê dùng chung cho Ban kiểm kê và người quản lý phòng."""

from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from . import schema, storage, ui
from .auth import CurrentUser


def default_dot() -> str:
    today = date.today()
    start = today.year if today.month >= 8 else today.year - 1
    return f"Năm học {start}-{start + 1}"


def render(user: CurrentUser, rooms: list[str], key: str, allow_update_status: bool = True) -> None:
    if not rooms:
        st.info("Không có phòng nào để kiểm kê.")
        return

    kk = storage.load(schema.KIEM_KE)
    labels = ui.room_label_map()

    dots = sorted(set(kk["DotKiemKe"]) - {""}, reverse=True)
    c1, c2 = st.columns(2)
    dot_choices = [*dots, "+ Đợt mới..."] if dots else ["+ Đợt mới..."]
    pending = st.session_state.pop(f"{key}_dot_pending", None)
    if pending in dot_choices:
        st.session_state[f"{key}_dot"] = pending
    dot_sel = c1.selectbox("Đợt kiểm kê", dot_choices, key=f"{key}_dot")
    dot = dot_sel
    if dot_sel == "+ Đợt mới...":
        dot = c1.text_input("Tên đợt kiểm kê mới", value=default_dot(), key=f"{key}_dot_new").strip()
    room = c2.selectbox("Phòng", rooms, format_func=lambda r: labels.get(r, r), key=f"{key}_room")
    if not dot:
        st.warning("Nhập tên đợt kiểm kê.")
        return

    # Tiến độ đợt kiểm kê trên các phòng được phép
    done_rooms = set(kk[kk["DotKiemKe"] == dot]["MaPhong"])
    checked = [r for r in rooms if r in done_rooms]
    st.progress(len(checked) / len(rooms), text=f"Tiến độ: đã kiểm kê {len(checked)}/{len(rooms)} phòng")

    tb = storage.load(schema.THIET_BI)
    tb = tb[(tb["MaPhong"] == room) & (tb["TinhTrang"] != "Đã thanh lý")]
    if tb.empty:
        st.info("Phòng này chưa có thiết bị.")
        return

    existing = kk[(kk["DotKiemKe"] == dot) & (kk["MaPhong"] == room)].drop_duplicates("Title", keep="last")
    existing = existing.set_index("Title")

    rows = []
    for r in tb.itertuples():
        old = existing.loc[r.Title] if r.Title in existing.index else None
        rows.append(
            {
                "Mã TB": r.Title,
                "Tên thiết bị": r.TenThietBi,
                "ĐVT": r.DonViTinh,
                "SL sổ sách": int(r.SoLuong),
                "SL thực tế": int(old["SoLuongThucTe"]) if old is not None else int(r.SoLuong),
                "Tình trạng": (old["TinhTrang"] if old is not None else r.TinhTrang) or "Tốt",
                "Ghi chú": old["GhiChu"] if old is not None else "",
                "Đã kiểm": old is not None,
            }
        )
    editor_df = pd.DataFrame(rows)

    st.caption("Nhập số lượng thực tế và tình trạng, sau đó bấm **Lưu kết quả kiểm kê**.")
    edited = st.data_editor(
        editor_df,
        key=f"{key}_editor_{dot}_{room}",
        hide_index=True,
        width="stretch",
        disabled=["Mã TB", "Tên thiết bị", "ĐVT", "SL sổ sách", "Đã kiểm"],
        column_config={
            "SL thực tế": st.column_config.NumberColumn(min_value=0, step=1),
            "Tình trạng": st.column_config.SelectboxColumn(options=schema.TINH_TRANG, required=True),
            "Đã kiểm": st.column_config.CheckboxColumn(help="Đã có kết quả trong đợt này"),
        },
    )
    diff = edited["SL thực tế"] - edited["SL sổ sách"]
    if (diff != 0).any():
        st.warning(f"Có {(diff != 0).sum()} thiết bị chênh lệch giữa sổ sách và thực tế.")

    update_status = allow_update_status and st.checkbox(
        "Cập nhật tình trạng mới vào danh mục thiết bị", value=True, key=f"{key}_upd"
    )
    if st.button("Lưu kết quả kiểm kê", type="primary", icon=":material/save:", key=f"{key}_save"):
        tb_by_code = tb.set_index("Title")
        with st.spinner("Đang lưu..."):
            for row in edited.itertuples(index=False):
                code = row[0]
                fields = {
                    "Title": code,
                    "TenThietBi": row[1],
                    "MaPhong": room,
                    "DotKiemKe": dot,
                    "SoLuongSoSach": row[3],
                    "SoLuongThucTe": row[4],
                    "TinhTrang": row[5],
                    "GhiChu": row[6],
                    "NguoiKiemKe": user.email,
                    "NgayKiemKe": date.today(),
                }
                if code in existing.index:
                    storage.update(schema.KIEM_KE, existing.loc[code, "id"], fields)
                else:
                    storage.create(schema.KIEM_KE, fields)
                if update_status and tb_by_code.loc[code, "TinhTrang"] != row[5]:
                    storage.update(schema.THIET_BI, tb_by_code.loc[code, "id"], {"TinhTrang": row[5]})
        st.session_state[f"{key}_dot_pending"] = dot
        ui.flash(f"Đã lưu kết quả kiểm kê phòng {labels.get(room, room)} – {dot}.")
        st.rerun()
