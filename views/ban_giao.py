"""Biên bản bàn giao tài sản theo từng phòng (đơn vị sử dụng tài sản)."""

from datetime import date

import pandas as pd
import streamlit as st

from qlts import auth, bienban, schema, storage, thietbi, ui

user = auth.require(schema.ROLE_QLTS)
st.subheader("Biên bản bàn giao tài sản")
st.caption(
    "Mỗi phòng (đơn vị sử dụng tài sản) là một biên bản: bên nhận là **người quản lý phòng**, chức vụ theo "
    "Phân quyền. Thiết bị cùng Mã tài sản được gom lại – Quy cách lấy theo **Chi tiết**, số lượng cộng lại. "
    "Excel: mỗi phòng một sheet · PDF: mỗi phòng bắt đầu một trang mới."
)

tb = storage.load(schema.THIET_BI)
labels = ui.room_label_map()
managers = thietbi.room_managers()
active = tb[(tb["NoiSuDung"] != "") & (tb["NoiSuDung"] != schema.NOI_THANH_LY)]
rooms = [r for r in labels if r in set(active["NoiSuDung"])]

with st.container(border=True):
    st.markdown("**1. Phòng cần lập biên bản**")
    c1, c2 = st.columns([4, 1], vertical_alignment="bottom")
    if c2.button("Chọn tất cả", width="stretch"):
        st.session_state["bg_rooms"] = rooms
    chosen = c1.multiselect("Đơn vị sử dụng tài sản (phòng)", rooms, key="bg_rooms",
                            format_func=lambda r: labels.get(r, r), placeholder="Chọn một hoặc nhiều phòng")
    note_code = st.checkbox("Ghi Mã tài sản vào cột Ghi chú", value=True, key="bg_note")

with st.container(border=True):
    st.markdown("**2. Bên giao & thông tin chung**")
    giao_ten, giao_cv = ui.party_picker(st.container(), "Người bàn giao", default=user.email, key="bg_giao")
    c1, c2 = st.columns([1, 3])
    ngay = c1.date_input("Ngày bàn giao", value=date.today(), format="DD/MM/YYYY", key="bg_ngay")
    dia_diem = c2.text_input("Địa điểm", bienban.default_place(), key="bg_place")

if not chosen:
    st.info("Chọn phòng để xem trước và xuất biên bản.", icon=":material/touch_app:")
    st.stop()

# ---- Bên nhận từng phòng: người quản lý phòng (sửa được) ----
st.markdown("**3. Bên nhận từng phòng** – mặc định là người quản lý phòng, sửa trực tiếp nếu cần")
rows = []
for room in chosen:
    email = managers.get(room, "")
    name, title = thietbi.person_info(email) if email else ("", "")
    rows.append({"Phong": room, "Ten": labels.get(room, room), "Email": email, "DaiDien": name, "ChucVu": title,
                 "SoTB": int((active["NoiSuDung"] == room).sum())})
receivers = st.data_editor(
    pd.DataFrame(rows), hide_index=True, width="stretch", key=f"bg_recv_{hash(tuple(chosen))}",
    disabled=["Phong", "Ten", "Email", "SoTB"],
    column_config={"Phong": None, "Ten": "Đơn vị sử dụng tài sản", "Email": "Email quản lý phòng",
                   "DaiDien": "Đại diện (Họ và tên)", "ChucVu": "Chức vụ", "SoTB": "Số thiết bị"},
)
missing = receivers[receivers["DaiDien"].fillna("").str.strip() == ""]
if not missing.empty:
    st.warning("Chưa có người đại diện cho: " + ", ".join(missing["Ten"]) +
               ". Gán người quản lý ở **Phân quyền quản lý phòng** hoặc nhập trực tiếp vào bảng.")

docs = []
for r in receivers.itertuples():
    items = bienban.group_items(active[active["NoiSuDung"] == r.Phong], note_code=note_code)
    docs.append(bienban.BienBan(
        giao_ten=giao_ten, giao_chuc_vu=giao_cv, nhan_ten=(r.DaiDien or "").strip(),
        nhan_chuc_vu=(r.ChucVu or "").strip(), items=items, ngay=ngay, dia_diem=dia_diem.strip(),
        don_vi=r.Ten, sheet=r.Phong,
    ))

with st.container(border=True):
    st.markdown(f"**4. Xuất biên bản** – {len(docs)} phòng, "
                f"{sum(len(d.items) for d in docs)} dòng tài sản")
    if not giao_ten:
        st.warning("Chọn người bàn giao.")
    stem = f"bien_ban_ban_giao_{ngay:%Y%m%d}" + (f"_{chosen[0]}" if len(chosen) == 1 else f"_{len(chosen)}_phong")
    ui.bienban_downloads(docs, stem, key="bg_dl")

st.markdown("##### Xem trước")
for d in docs:
    with st.expander(f"{d.don_vi} – {len(d.items)} dòng · Đại diện: {d.nhan_ten or '(chưa có)'}"):
        st.dataframe(
            pd.DataFrame([{"STT": i, "Tên hàng hóa/dịch vụ": it["ten"], "Mã hiệu/Quy cách": it["quy_cach"],
                           "ĐVT": it["dvt"], "Số lượng": it["sl"], "Ghi chú": it["ghi_chu"]}
                          for i, it in enumerate(d.items, start=1)]),
            hide_index=True, width="stretch",
        )
