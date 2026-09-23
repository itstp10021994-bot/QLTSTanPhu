"""Màn hình kiểm kê dùng chung cho Ban kiểm kê và người quản lý phòng."""

from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from . import schema, storage, thietbi, ui
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

    all_tb = storage.load(schema.THIET_BI)
    tb = all_tb[(all_tb["NoiSuDung"] == room) & ~thietbi.is_disposed(all_tb)].drop_duplicates("MaChiTiet")
    if tb.empty:
        st.info("Phòng này chưa có thiết bị.")
        return

    existing = kk[(kk["DotKiemKe"] == dot) & (kk["MaPhong"] == room)].drop_duplicates("Title", keep="last")
    existing = existing.set_index("Title")
    status_opts = thietbi.status_options(all_tb)

    rows = []
    for r in tb.itertuples():
        old = existing.loc[r.MaChiTiet] if r.MaChiTiet in existing.index else None
        rows.append(
            {
                "Mã chi tiết": r.MaChiTiet,
                "Tên thiết bị": r.TenThietBi,
                "Đặc điểm": r.DacDiem,
                "Serial": r.TenPhongBan,
                "Có mặt": bool(old["SoLuongThucTe"]) if old is not None else True,
                "Tình trạng": (old["TinhTrang"] if old is not None else r.TinhTrang) or "Bình thường",
                "Ghi chú": old["GhiChu"] if old is not None else "",
                "Đã kiểm": old is not None,
            }
        )
    editor_df = pd.DataFrame(rows)

    st.caption("Bỏ tick **Có mặt** nếu không tìm thấy thiết bị, chọn tình trạng thực tế rồi bấm **Lưu kết quả kiểm kê**.")
    edited = st.data_editor(
        editor_df,
        key=f"{key}_editor_{dot}_{room}",
        hide_index=True,
        width="stretch",
        disabled=["Mã chi tiết", "Tên thiết bị", "Đặc điểm", "Serial", "Đã kiểm"],
        column_config={
            "Có mặt": st.column_config.CheckboxColumn(),
            "Tình trạng": st.column_config.SelectboxColumn(options=status_opts, required=True),
            "Đã kiểm": st.column_config.CheckboxColumn(help="Đã có kết quả trong đợt này"),
        },
    )
    missing = int((~edited["Có mặt"]).sum())
    if missing:
        st.warning(f"Có {missing} thiết bị không tìm thấy trong phòng.")

    update_status = allow_update_status and st.checkbox(
        "Cập nhật tình trạng mới vào danh sách thiết bị", value=True, key=f"{key}_upd"
    )
    if st.button("Lưu kết quả kiểm kê", type="primary", icon=":material/save:", key=f"{key}_save"):
        tb_by_code = tb.set_index("MaChiTiet")
        with st.spinner("Đang lưu..."):
            for row in edited.to_dict("records"):
                code = row["Mã chi tiết"]
                fields = {
                    "Title": code,
                    "TenThietBi": row["Tên thiết bị"],
                    "MaPhong": room,
                    "DotKiemKe": dot,
                    "SoLuongSoSach": 1,
                    "SoLuongThucTe": 1 if row["Có mặt"] else 0,
                    "TinhTrang": row["Tình trạng"],
                    "GhiChu": row["Ghi chú"],
                    "NguoiKiemKe": user.email,
                    "NgayKiemKe": date.today(),
                }
                if code in existing.index:
                    storage.update(schema.KIEM_KE, existing.loc[code, "id"], fields)
                else:
                    storage.create(schema.KIEM_KE, fields)
                if update_status and tb_by_code.loc[code, "TinhTrang"] != row["Tình trạng"]:
                    storage.update(schema.THIET_BI, tb_by_code.loc[code, "id"], {"TinhTrang": row["Tình trạng"]})
        st.session_state[f"{key}_dot_pending"] = dot
        ui.flash(f"Đã lưu kết quả kiểm kê {labels.get(room, room)} – {dot}.")
        st.rerun()
