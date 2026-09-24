"""Kiểm kê theo nhóm thiết bị (giống list "Data_Thietbi").

Thiết bị chi tiết có cùng Mã tài sản + Đặc điểm + Nơi sử dụng được gộp thành một dòng, cộng số lượng.
- Ban kiểm kê nhập "Số lượng kiểm kê", "Trạng thái" rồi bấm **Xác nhận kiểm kê**
  -> dòng trên list kiểm kê có "Trạng thái kiểm kê" = Đã kiểm kê, "Ngày kiểm kê", "Đợt kiểm kê".
- Người quản lý phòng xem kết quả và bấm **Xác nhận** -> "Trạng thái xác nhận", "Ngày xác nhận".
"""

from __future__ import annotations

import re
from datetime import date

import pandas as pd
import streamlit as st

from . import schema, storage, thietbi, ui
from .auth import CurrentUser

KK = schema.KIEM_KE
NEW_DOT = "+ Đợt mới..."


def default_dot() -> str:
    today = date.today()
    start = today.year if today.month >= 8 else today.year - 1
    return f"Đợt 1 năm {start} - {start + 1}"


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip().lower()


def group_key(ma: str, dac_diem: str, noi: str) -> tuple:
    return _norm(ma), _norm(dac_diem), _norm(noi)


def grouped_equipment(tb: pd.DataFrame, room: str) -> pd.DataFrame:
    """Gộp thiết bị chi tiết của một phòng theo Mã tài sản + Đặc điểm (+ Nơi sử dụng), cộng số lượng."""
    items = tb[(tb["NoiSuDung"] == room) & ~thietbi.is_disposed(tb)].copy()
    if items.empty:
        return pd.DataFrame()
    items["_qty"] = items["SL"].where(items["SL"] > 0, 1)  # mỗi dòng chi tiết = 1 thiết bị nếu SL trống
    items["_key"] = [group_key(r.MaTaiSan, r.DacDiem, r.NoiSuDung) for r in items.itertuples()]
    rows = []
    for key, grp in items.groupby("_key", sort=False):
        first = grp.iloc[0]
        states = grp["TinhTrang"][grp["TinhTrang"] != ""]
        rows.append({
            "GKey": key,
            "MaTaiSan": first["MaTaiSan"],
            "TenTaiSan": first["TenThietBi"] or first["ChiTiet"],
            "DacDiem": first["DacDiem"],
            "DVT": first["DVT"],
            "SoLuong": int(grp["_qty"].sum()),
            "QuanLyThietBi": first["QuanLyThietBi"],
            "NoiSuDung": room,
            "QuanLyPhong": first["QuanLyPhong"],
            "TrangThai": states.mode().iloc[0] if not states.empty else "",
            "MaChiTiet": ", ".join(grp["MaChiTiet"]),
        })
    return pd.DataFrame(rows).sort_values(["MaTaiSan", "DacDiem"]).reset_index(drop=True)


def _existing(kk: pd.DataFrame, dot: str, room: str) -> dict:
    cur = kk[(kk["DotKiemKe"] == dot) & (kk["NoiSuDung"] == room)]
    return {group_key(r.MaTaiSan, r.DacDiem, r.NoiSuDung): r._asdict() for r in cur.itertuples()}


def _choose_dot(kk: pd.DataFrame, key: str, allow_new: bool) -> str:
    dots = sorted(set(kk["DotKiemKe"]) - {""}, reverse=True)
    choices = [*dots, NEW_DOT] if allow_new else dots
    if not choices:
        return ""
    pending = st.session_state.pop(f"{key}_dot_pending", None)
    if pending in choices:
        st.session_state[f"{key}_dot"] = pending
    sel = st.selectbox("Đợt kiểm kê", choices, key=f"{key}_dot")
    if sel == NEW_DOT:
        return st.text_input("Tên đợt kiểm kê mới", value=default_dot(), key=f"{key}_dot_new").strip()
    return sel


def _progress(kk: pd.DataFrame, dot: str, rooms: list[str]) -> None:
    cur = kk[kk["DotKiemKe"] == dot]
    done = set(cur[cur["TrangThaiKiemKe"] == schema.DA_KIEM_KE]["NoiSuDung"])
    confirmed = set(cur[cur["TrangThaiXacNhan"] == schema.DA_XAC_NHAN]["NoiSuDung"])
    n_done = sum(r in done for r in rooms)
    st.progress(n_done / len(rooms) if rooms else 0,
                text=f"Đã kiểm kê {n_done}/{len(rooms)} phòng · đã xác nhận {sum(r in confirmed for r in rooms)} phòng")


# ---------------------------------------------------------------------------
# Ban kiểm kê
# ---------------------------------------------------------------------------
def render_committee(user: CurrentUser, rooms: list[str], key: str) -> None:
    if not rooms:
        st.info("Không có phòng nào để kiểm kê.")
        return
    kk = storage.load(KK)
    tb = storage.load(schema.THIET_BI)
    labels = ui.room_label_map()

    c1, c2 = st.columns(2)
    with c1:
        dot = _choose_dot(kk, key, allow_new=True)
    room = c2.selectbox("Nơi sử dụng", rooms, format_func=lambda r: labels.get(r, r), key=f"{key}_room")
    if not dot:
        st.warning("Nhập tên đợt kiểm kê.")
        return
    _progress(kk, dot, rooms)

    groups = grouped_equipment(tb, room)
    if groups.empty:
        st.info("Nơi này chưa có thiết bị.")
        return
    existing = _existing(kk, dot, room)
    status_opts = thietbi.status_options(tb)

    view = pd.DataFrame([{
        "Mã số tài sản": g.MaTaiSan,
        "Tên tài sản": g.TenTaiSan,
        "Đặc điểm": g.DacDiem,
        "ĐVT": g.DVT,
        "Số lượng": g.SoLuong,
        "Số lượng kiểm kê": int(existing[g.GKey]["SoLuongKiemKe"]) if g.GKey in existing else g.SoLuong,
        "Trạng thái": (existing[g.GKey]["TrangThai"] if g.GKey in existing else g.TrangThai) or "Bình thường",
        "Ghi chú": existing[g.GKey]["GhiChu"] if g.GKey in existing else "",
        "Trạng thái kiểm kê": existing[g.GKey]["TrangThaiKiemKe"] if g.GKey in existing else "",
        "Xác nhận": existing[g.GKey]["TrangThaiXacNhan"] if g.GKey in existing else "",
    } for g in groups.itertuples()])

    st.caption(f"{len(groups)} nhóm thiết bị · {int(groups['SoLuong'].sum())} thiết bị. "
               "Nhập **Số lượng kiểm kê** và **Trạng thái** thực tế, rồi bấm **Xác nhận kiểm kê**.")
    edited = st.data_editor(
        view, key=f"{key}_editor_{dot}_{room}", hide_index=True, width="stretch",
        disabled=["Mã số tài sản", "Tên tài sản", "Đặc điểm", "ĐVT", "Số lượng", "Trạng thái kiểm kê", "Xác nhận"],
        column_config={
            "Số lượng kiểm kê": st.column_config.NumberColumn(min_value=0, step=1),
            "Trạng thái": st.column_config.SelectboxColumn(options=status_opts, required=True),
        },
    )
    diff = edited["Số lượng kiểm kê"] - edited["Số lượng"]
    if (diff != 0).any():
        st.warning(f"{int((diff != 0).sum())} nhóm có chênh lệch: thiếu {int(-diff[diff < 0].sum())}, "
                   f"thừa {int(diff[diff > 0].sum())} thiết bị so với sổ sách.")
    if any(existing[k]["TrangThaiXacNhan"] == schema.DA_XAC_NHAN for k in existing):
        st.info("Phòng này đã được người quản lý xác nhận; kiểm kê lại sẽ xóa trạng thái xác nhận.")

    c1, c2 = st.columns([1, 4])
    confirm = c1.button("Xác nhận kiểm kê", type="primary", icon=":material/task_alt:", key=f"{key}_confirm")
    draft = c2.button("Lưu tạm", icon=":material/save:", key=f"{key}_draft",
                      help=f"Lưu số liệu với trạng thái “{schema.DANG_KIEM_KE}”, chưa xác nhận.")
    if not (confirm or draft):
        return

    stt = int(kk["STT"].max()) if not kk.empty else 0
    ops = []
    for g, row in zip(groups.itertuples(), edited.to_dict("records")):
        fields = {
            "MaTaiSan": g.MaTaiSan, "TenTaiSan": g.TenTaiSan, "DacDiem": g.DacDiem, "DVT": g.DVT,
            "SoLuong": g.SoLuong, "SoLuongKiemKe": row["Số lượng kiểm kê"], "GhiChu": row["Ghi chú"],
            "QuanLyThietBi": g.QuanLyThietBi, "NoiSuDung": room, "QuanLyPhong": g.QuanLyPhong,
            "TrangThai": row["Trạng thái"], "DotKiemKe": dot, "NgayKiemKe": date.today(),
            "TrangThaiKiemKe": schema.DA_KIEM_KE if confirm else schema.DANG_KIEM_KE,
            "NguoiKiemKe": user.email, "TrangThaiXacNhan": "", "NgayXacNhan": None, "NguoiXacNhan": "",
        }
        old = existing.get(g.GKey)
        if old:
            ops.append(("update", old["id"], fields))
        else:
            stt += 1
            ops.append(("create", {**fields, "STT": stt}))
    with st.spinner("Đang ghi lên SharePoint..."):
        errors = storage.batch(KK, ops)
    if errors:
        st.error("Có lỗi khi lưu:\n\n" + "\n\n".join(errors[:20]))
        return
    st.session_state[f"{key}_dot_pending"] = dot
    ui.flash(f"{'Đã xác nhận kiểm kê' if confirm else 'Đã lưu tạm'} {labels.get(room, room)} – {dot} "
             f"({len(ops)} nhóm thiết bị).")
    st.rerun()


# ---------------------------------------------------------------------------
# Người quản lý phòng xác nhận
# ---------------------------------------------------------------------------
def render_confirm(user: CurrentUser, rooms: list[str], key: str) -> None:
    if not rooms:
        st.info("Bạn chưa được phân công quản lý phòng nào.")
        return
    kk = storage.load(KK)
    labels = ui.room_label_map()
    c1, c2 = st.columns(2)
    with c1:
        dot = _choose_dot(kk, key, allow_new=False)
    if not dot:
        st.info("Chưa có đợt kiểm kê nào.")
        return
    room = c2.selectbox("Phòng", rooms, format_func=lambda r: labels.get(r, r), key=f"{key}_room")
    _progress(kk, dot, rooms)

    cur = kk[(kk["DotKiemKe"] == dot) & (kk["NoiSuDung"] == room)]
    if cur.empty:
        st.info("Ban kiểm kê chưa kiểm kê phòng này trong đợt đã chọn.")
        return
    cur = cur.assign(ChenhLech=cur["SoLuongKiemKe"] - cur["SoLuong"])
    cols = ["MaTaiSan", "TenTaiSan", "DacDiem", "DVT", "SoLuong", "SoLuongKiemKe", "ChenhLech", "TrangThai",
            "GhiChu", "NgayKiemKe", "TrangThaiKiemKe", "TrangThaiXacNhan", "NgayXacNhan"]
    st.dataframe(cur[cols].rename(columns={**schema.labels_of(KK), "ChenhLech": "Chênh lệch"}),
                 hide_index=True, width="stretch")

    if (cur["TrangThaiKiemKe"] != schema.DA_KIEM_KE).any():
        st.info("Ban kiểm kê chưa bấm xác nhận kiểm kê cho phòng này.")
        return
    if (cur["TrangThaiXacNhan"] == schema.DA_XAC_NHAN).all():
        st.success(f"Bạn đã xác nhận kết quả kiểm kê ngày {cur['NgayXacNhan'].iloc[0]}.")
        return
    with st.form(f"{key}_form"):
        y_kien = st.radio("Ý kiến", [schema.DA_XAC_NHAN, schema.KHONG_DONG_Y], horizontal=True,
                          format_func=lambda v: "Đồng ý với kết quả kiểm kê" if v == schema.DA_XAC_NHAN else v)
        note = st.text_input("Ghi chú (bắt buộc nếu không đồng ý)")
        ok = st.form_submit_button("Gửi xác nhận", type="primary", icon=":material/verified:")
    if ok:
        if y_kien == schema.KHONG_DONG_Y and not note.strip():
            st.error("Vui lòng ghi rõ lý do không đồng ý.")
            return
        ops = []
        for r in cur.itertuples():
            fields = {"TrangThaiXacNhan": y_kien, "NgayXacNhan": date.today(), "NguoiXacNhan": user.email}
            if note.strip():
                fields["GhiChu"] = (f"{r.GhiChu}\n" if r.GhiChu else "") + f"[Quản lý phòng] {note.strip()}"
            ops.append(("update", r.id, fields))
        errors = storage.batch(KK, ops)
        if errors:
            st.error("Có lỗi khi lưu:\n\n" + "\n\n".join(errors[:20]))
            return
        st.session_state[f"{key}_dot_pending"] = dot
        ui.flash(f"Đã gửi xác nhận ({y_kien}) cho {labels.get(room, room)} – {dot}.")
        st.rerun()
