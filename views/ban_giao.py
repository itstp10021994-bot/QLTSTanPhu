"""Tài sản hiện có theo đơn vị sử dụng (gom nhóm) và Biên bản bàn giao tài sản (mẫu HC/QT–02/M03)."""

from datetime import date

import pandas as pd
import streamlit as st

from qlts import auth, bangiao, schema, storage, thietbi, ui

user = auth.require(schema.ROLE_QLTS)
st.subheader("Bàn giao tài sản")

tb = storage.load(schema.THIET_BI)
labels = ui.room_label_map()
managers = thietbi.room_managers()
disposed = thietbi.is_disposed(tb)
in_use = tb[~disposed]  # tất cả thiết bị đang sử dụng (kể cả chưa có vị trí) – dùng cho tab xem
active = in_use[in_use["NoiSuDung"] != ""]  # lập biên bản: cần có phòng
rooms = [r for r in labels if r in set(active["NoiSuDung"])]
fmt_room = lambda r: labels.get(r, r)  # noqa: E731


def view_frame(g: pd.DataFrame) -> pd.DataFrame:
    out = g.copy()
    out.insert(0, "stt", range(1, len(out) + 1))
    return out[[k for k, _, _ in bangiao.COLUMNS]].rename(columns=bangiao.LABELS)


tab_view, tab_export = st.tabs(["Tài sản hiện có", "Xuất biên bản bàn giao"])

# ---------------------------------------------------------------------------
with tab_view:
    st.caption("Thiết bị cùng **Mã tài sản, Quy cách, Nhân sự sử dụng, Tình trạng** trong một vị trí được gom "
               "thành một dòng, số lượng cộng lại. Quy cách lấy theo **Chi tiết**.")
    c1, c2, c3 = st.columns([2, 1.5, 1.5])
    kw = c1.text_input("Tìm kiếm (mã, tên, quy cách, người sử dụng...)", key="bgv_kw")
    sel_rooms = c2.multiselect("Vị trí tài sản", rooms, format_func=fmt_room, key="bgv_rooms")
    sel_groups = c3.multiselect("Nhóm tài sản", sorted(set(in_use["NhomThietBi"]) - {""}), key="bgv_groups")
    data = in_use
    if sel_rooms:
        data = data[data["NoiSuDung"].isin(sel_rooms)]
    if sel_groups:
        data = data[data["NhomThietBi"].isin(sel_groups)]
    g = bangiao.group_assets(data)
    if kw:
        mask = g[["ma", "ten", "quy_cach", "nguoi", "nhom", "vi_tri"]].apply(
            lambda col: col.str.contains(kw, case=False, regex=False)).any(axis=1)
        g = g[mask].reset_index(drop=True)
    fmt_n = lambda v: f"{v:,.0f}".replace(",", ".")  # noqa: E731
    sl_raw = pd.to_numeric(data["SL"], errors="coerce").fillna(0)
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Số thiết bị (dòng trên SharePoint)", fmt_n(len(data)))
    m2.metric("Tổng số lượng", fmt_n(g["sl"].sum()), help="Cộng cột SL; dòng SL trống hoặc 0 tính là 1.")
    m3.metric("Số dòng sau khi gom", fmt_n(len(g)))
    m4.metric("Số vị trí", g["vi_tri"].nunique())
    if not (sel_rooms or sel_groups or kw):
        no_place = int((in_use["NoiSuDung"] == "").sum())
        with st.expander("Đối chiếu với tổng số trên SharePoint"):
            st.markdown(
                f"- Tổng số dòng trong list thiết bị: **{fmt_n(len(tb))}**\n"
                f"- Trừ tài sản **đã thanh lý** (không hiển thị ở đây): **{fmt_n(int(disposed.sum()))}**\n"
                f"- Còn lại đang sử dụng: **{fmt_n(len(in_use))}** dòng"
                + (f" – trong đó **{fmt_n(no_place)}** dòng chưa có Nơi sử dụng (nhóm "
                   f"“{bangiao.NO_PLACE}”, không lập được biên bản bàn giao)" if no_place else "") + "\n"
                f"- Dòng có SL lớn hơn 1: **{fmt_n(int((sl_raw > 1).sum()))}** (thêm "
                f"{fmt_n((sl_raw[sl_raw > 1] - 1).sum())} vào tổng số lượng); dòng SL trống/0 (tính là 1): "
                f"**{fmt_n(int((sl_raw <= 0).sum()))}**"
            )
    table = view_frame(g)
    st.dataframe(table, hide_index=True, width="stretch", height=560,
                 column_config={"Số lượng": st.column_config.NumberColumn(format="localized")})
    st.download_button("Tải bảng này (Excel)", ui.to_excel({"TaiSanHienCo": table}),
                       file_name=f"tai_san_hien_co_{date.today():%Y%m%d}.xlsx", icon=":material/download:")

# ---------------------------------------------------------------------------
with tab_export:
    st.caption("Mỗi phòng (đơn vị sử dụng tài sản) là một biên bản. **Excel**: mỗi phòng một sheet · "
               "**PDF**: mỗi phòng bắt đầu một trang mới (A4 ngang, font Times New Roman).")
    with st.container(border=True):
        st.markdown("**1. Đơn vị sử dụng tài sản (phòng)**")
        c1, c2 = st.columns([4, 1], vertical_alignment="bottom")
        if c2.button("Chọn tất cả", width="stretch"):
            st.session_state["bg_rooms"] = rooms
        chosen = c1.multiselect("Phòng", rooms, key="bg_rooms", format_func=fmt_room,
                                placeholder="Chọn một hoặc nhiều phòng")

    with st.container(border=True):
        st.markdown("**2. Đại diện Ban bàn giao tài sản**")
        c1, c2, c3 = st.columns([1, 1, 2])
        n_ban = c1.number_input("Số thành viên", min_value=1, max_value=6, value=3, step=1, key="bg_nban")
        ngay = c2.date_input("Ngày bàn giao", value=date.today(), format="DD/MM/YYYY", key="bg_ngay")
        nam_hoc = c3.text_input("Năm (in trên tiêu đề)", bangiao.school_year(ngay), key=f"bg_nam_{ngay}")
        ban = []
        for i in range(int(n_ban)):
            name, cv = ui.party_picker(st.container(), f"{i + 1}. Ông/Bà", default=user.email if i == 0 else "",
                                       key=f"bg_ban{i}", inline=True)
            if name:
                ban.append((name, cv))

    if not chosen:
        st.info("Chọn phòng để lập biên bản.", icon=":material/touch_app:")
        st.stop()

    st.markdown("**3. Đại diện đơn vị sử dụng** – mặc định là người quản lý phòng, sửa trực tiếp nếu cần")
    rows = []
    for room in chosen:
        email = managers.get(room, "")
        name, title = thietbi.person_info(email) if email else ("", "")
        rows.append({"Phong": room, "Ten": fmt_room(room), "Email": email, "DaiDien": name, "ChucVu": title,
                     "SoTB": int((active["NoiSuDung"] == room).sum())})
    receivers = st.data_editor(
        pd.DataFrame(rows), hide_index=True, width="stretch", key=f"bg_recv_{hash(tuple(chosen))}",
        disabled=["Phong", "Ten", "Email", "SoTB"],
        column_config={"Phong": None, "Ten": "Đơn vị sử dụng tài sản", "Email": "Email quản lý phòng",
                       "DaiDien": "Đại diện đơn vị", "ChucVu": "Chức vụ", "SoTB": "Số thiết bị"},
    )
    missing = receivers[receivers["DaiDien"].fillna("").str.strip() == ""]
    if not missing.empty:
        st.warning("Chưa có đại diện cho: " + ", ".join(missing["Ten"]) +
                   ". Gán người quản lý ở **Phân quyền quản lý phòng** hoặc nhập trực tiếp vào bảng.")

    docs = [
        bangiao.BanGiao(
            don_vi=r.Ten, dai_dien=(r.DaiDien or "").strip(), dai_dien_cv=(r.ChucVu or "").strip(), ban=ban,
            rows=bangiao.group_assets(active[active["NoiSuDung"] == r.Phong]), ngay=ngay,
            nam_hoc=nam_hoc.strip(), sheet=r.Phong,
        )
        for r in receivers.itertuples()
    ]

    with st.container(border=True):
        st.markdown(f"**4. Xuất biên bản** – {len(docs)} phòng, {sum(len(d.rows) for d in docs)} dòng tài sản")
        if not ban:
            st.warning("Chọn ít nhất một thành viên Ban bàn giao.")
        stem = f"bien_ban_ban_giao_{ngay:%Y%m%d}" + (f"_{chosen[0]}" if len(chosen) == 1 else f"_{len(chosen)}_phong")
        c1, c2 = st.columns(2)
        c1.download_button("Tải PDF (in)", data=lambda: bangiao.to_pdf(docs), file_name=f"{stem}.pdf",
                           mime="application/pdf", icon=":material/picture_as_pdf:", type="primary",
                           width="stretch", on_click="ignore", key="bg_pdf")
        c2.download_button("Tải Excel (mỗi phòng 1 sheet)", data=lambda: bangiao.to_xlsx(docs),
                           file_name=f"{stem}.xlsx", icon=":material/table:", width="stretch", on_click="ignore",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key="bg_xlsx")

    st.markdown("##### Xem trước")
    for d in docs:
        with st.expander(f"{d.don_vi} – {len(d.rows)} dòng, tổng số lượng {d.rows['sl'].sum():g} · "
                         f"Đại diện: {d.dai_dien or '(chưa có)'}"):
            st.html(bangiao.to_html(d))
