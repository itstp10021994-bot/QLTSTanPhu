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
    used_qr = any(QR_TAG in str(r.get("GhiChu", "")) for r in existing.values())
    method = st.radio(
        "Phương án kiểm kê", [M_QTY, M_QR], horizontal=True, index=1 if used_qr else 0,
        key=f"{key}_method_{dot}_{room}",
        help="Hai phương án ghi vào cùng một đợt kiểm kê; mỗi phòng chọn một phương án.",
    )
    if any(existing[k]["TrangThaiXacNhan"] == schema.DA_XAC_NHAN for k in existing):
        st.info("Phòng này đã được người quản lý xác nhận; kiểm kê lại sẽ xóa trạng thái xác nhận.")
    if method == M_QR:
        _render_qr(user, kk, tb, groups, existing, dot, room, labels, key)
    else:
        _render_quantity(user, kk, tb, groups, existing, dot, room, labels, key)


M_QTY = "Nhập số lượng"
M_QR = "Quét mã QR"
QR_TAG = "[QR]"
_QR_RE = re.compile(r"\[QR\] Đã quét: ([^\n]*)")
_QR_EXTRA_RE = re.compile(r"Thiết bị phòng khác quét được: ([^\n]*)")


def _save(user: CurrentUser, kk: pd.DataFrame, groups: pd.DataFrame, existing: dict, dot: str, room: str,
          values: list[dict], confirm: bool, labels: dict, key: str) -> None:
    """Ghi kết quả (một dòng / nhóm thiết bị) lên list kiểm kê – dùng chung cho 2 phương án."""
    stt = int(kk["STT"].max()) if not kk.empty else 0
    ops = []
    for g, row in zip(groups.itertuples(), values):
        fields = {
            "MaTaiSan": g.MaTaiSan, "TenTaiSan": g.TenTaiSan, "DacDiem": g.DacDiem, "DVT": g.DVT,
            "SoLuong": g.SoLuong, "SoLuongKiemKe": row["qty"], "GhiChu": row["note"],
            "QuanLyThietBi": g.QuanLyThietBi, "NoiSuDung": room, "QuanLyPhong": g.QuanLyPhong,
            "TrangThai": row["state"], "DotKiemKe": dot, "NgayKiemKe": date.today(),
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


def _buttons(key: str, suffix: str) -> tuple[bool, bool]:
    c1, c2 = st.columns([1, 4])
    confirm = c1.button("Xác nhận kiểm kê", type="primary", icon=":material/task_alt:", key=f"{key}_confirm{suffix}")
    draft = c2.button("Lưu tạm", icon=":material/save:", key=f"{key}_draft{suffix}",
                      help=f"Lưu số liệu với trạng thái “{schema.DANG_KIEM_KE}”, chưa xác nhận.")
    return confirm, draft


# ---- Phương án 1: nhập số lượng ----
def _render_quantity(user, kk, tb, groups, existing, dot, room, labels, key) -> None:
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
    confirm, draft = _buttons(key, "")
    if confirm or draft:
        values = [{"qty": r["Số lượng kiểm kê"], "note": r["Ghi chú"], "state": r["Trạng thái"]}
                  for r in edited.to_dict("records")]
        _save(user, kk, groups, existing, dot, room, values, confirm, labels, key)


# ---- Phương án 2: quét mã QR ----
def _render_qr(user, kk, tb, groups, existing, dot, room, labels, key) -> None:
    from . import qr

    items = tb[(tb["NoiSuDung"] == room) & ~thietbi.is_disposed(tb)]
    all_codes = {c.lower(): c for c in tb["MaChiTiet"] if c}
    skey = f"{key}_qr_{dot}_{room}"
    if skey not in st.session_state:  # khôi phục mã đã quét từ lần lưu tạm trước
        found: set[str] = set()
        for r in existing.values():
            note = str(r.get("GhiChu", ""))
            for pattern in (_QR_RE, _QR_EXTRA_RE):
                m = pattern.search(note)
                if m:
                    found |= {c.strip() for c in m.group(1).split(",") if c.strip()}
        st.session_state[skey] = found
    scanned: set[str] = st.session_state[skey]

    st.caption("Quét mã QR dán trên thiết bị (nội dung = **Mã chi tiết**). Mỗi mã quét được tính là thiết bị "
               "**có mặt**; thiết bị chưa quét tính là **thiếu**. Có thể dùng camera điện thoại, súng quét mã, "
               "hoặc gõ mã vào ô bên dưới.")
    with st.expander("In tem QR cho thiết bị trong phòng này"):
        st.download_button(f"Tải tem QR ({len(items)} thiết bị, PDF A4 – 24 tem/trang)",
                           lambda: qr.labels_pdf(items.sort_values("MaChiTiet"), labels.get(room, room)),
                           file_name=f"tem_qr_{room}.pdf", mime="application/pdf", icon=":material/qr_code_2:",
                           on_click="ignore", key=f"{key}_labels_{room}")

    def add(text: str) -> None:
        code = qr.resolve(text, all_codes)
        if not code:
            st.session_state[f"{skey}_msg"] = ("error", f"Không nhận ra mã “{text.strip()[:60]}”.")
        elif code in scanned:
            st.session_state[f"{skey}_msg"] = ("info", f"{code} đã quét rồi.")
        else:
            scanned.add(code)
            row = tb[tb["MaChiTiet"] == code].iloc[0]
            where = "" if row["NoiSuDung"] == room else f" – ⚠ đang ghi ở {labels.get(row['NoiSuDung'], row['NoiSuDung'])}"
            st.session_state[f"{skey}_msg"] = ("success" if not where else "warning",
                                               f"✔ {code} – {row['TenThietBi'] or row['ChiTiet']}{where}")

    def on_manual() -> None:
        text = st.session_state.get(f"{skey}_manual", "")
        for part in re.split(r"[\s;]+", text.strip()):
            if part:
                add(part)
        st.session_state[f"{skey}_manual"] = ""

    @st.fragment
    def scan_area() -> None:
        code = qr.scanner(key=f"{skey}_cam")
        if code:
            add(code)
        st.text_input("Hoặc nhập / quét mã bằng súng quét rồi nhấn Enter", key=f"{skey}_manual",
                      on_change=on_manual, placeholder="VD: 111028-00001")
        msg = st.session_state.get(f"{skey}_msg")
        if msg:
            getattr(st, msg[0])(msg[1])
        present = items["MaChiTiet"].isin(scanned)
        extra = sorted(scanned - set(items["MaChiTiet"]))
        m1, m2, m3 = st.columns(3)
        m1.metric("Đã quét trong phòng", f"{int(present.sum())}/{len(items)}", border=True)
        m2.metric("Chưa quét (thiếu)", int((~present).sum()), border=True)
        m3.metric("Thiết bị của phòng khác", len(extra), border=True)
        view = items.assign(CoMat=present.map({True: "✅ Có mặt", False: "⬜ Chưa quét"}))
        only_missing = st.toggle("Chỉ hiện thiết bị chưa quét", key=f"{skey}_only")
        if only_missing:
            view = view[~present]
        st.dataframe(view[["CoMat", "MaChiTiet", "TenThietBi", "DacDiem", "TenPhongBan", "TinhTrang"]].rename(
            columns={"CoMat": "Kiểm kê", **schema.labels_of(schema.THIET_BI)}), hide_index=True, width="stretch",
            height=320)
        if extra:
            other = tb[tb["MaChiTiet"].isin(extra)]
            st.warning("Thiết bị quét được nhưng đang ghi ở nơi khác (cân nhắc Điều chuyển về phòng này):")
            st.dataframe(other[["MaChiTiet", "TenThietBi", "NoiSuDung"]].rename(
                columns=schema.labels_of(schema.THIET_BI)), hide_index=True, width="stretch")
        if scanned:
            c1, c2 = st.columns([3, 1], vertical_alignment="bottom")
            rm = c1.selectbox("Bỏ một mã đã quét (quét nhầm)", sorted(scanned), index=None, key=f"{skey}_rm")
            if c2.button("Bỏ mã", key=f"{skey}_rmbtn", disabled=not rm):
                scanned.discard(rm)
                st.rerun(scope="fragment")

    scan_area()

    state_by_code = dict(zip(items["MaChiTiet"], items["TinhTrang"]))
    qty_by_code = {c: (q if q > 0 else 1) for c, q in zip(tb["MaChiTiet"], tb["SL"])}
    confirm, draft = _buttons(key, "_qr")
    if not (confirm or draft):
        return
    values = []
    for g in groups.itertuples():
        codes = [c.strip() for c in g.MaChiTiet.split(",") if c.strip()]
        found = [c for c in codes if c in scanned]
        missing = [c for c in codes if c not in scanned]
        note = f"{QR_TAG} Đã quét: {', '.join(found)}"
        if missing:
            note += f"\nChưa thấy: {', '.join(missing)}"
        states = [state_by_code.get(c, "") for c in found if state_by_code.get(c)]
        values.append({"qty": int(sum(qty_by_code.get(c, 1) for c in found)), "note": note,
                       "state": (max(set(states), key=states.count) if states else g.TrangThai) or "Bình thường"})
    extra = sorted(scanned - set(items["MaChiTiet"]))
    if extra and values:
        values[0]["note"] += f"\nThiết bị phòng khác quét được: {', '.join(extra)}"
    _save(user, kk, groups, existing, dot, room, values, confirm, labels, key)


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
