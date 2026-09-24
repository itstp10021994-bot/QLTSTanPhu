import streamlit as st

from qlts import auth, schema, storage, thietbi, ui

auth.require(schema.ROLE_ADMIN)
st.subheader("Phân quyền quản lý phòng")
st.caption(
    "Gán người phụ trách cho từng phòng (Nơi sử dụng). Khi đổi người quản lý, cột **Quản lý phòng** của mọi "
    "thiết bị trong phòng cũng được cập nhật. Người phụ trách thấy phòng ở mục **Người dùng**."
)

phong = storage.load(schema.PHONG)
tb = storage.load(schema.THIET_BI)
managers = thietbi.room_managers()


def sync_items(room: str, email: str) -> int:
    """Cập nhật cột Quản lý phòng của các thiết bị trong phòng."""
    items = tb[(tb["NoiSuDung"] == room) & (tb["QuanLyPhong"].str.strip().str.lower() != email)]
    storage.batch(schema.THIET_BI, [("update", item_id, {"QuanLyPhong": email}) for item_id in items["id"]])
    return len(items)


# Nơi sử dụng có trên thiết bị nhưng chưa có trong danh mục phòng
missing = [r for r in thietbi.all_rooms() if r not in set(phong["Title"])]
if missing:
    with st.container(border=True):
        st.markdown(f"**{len(missing)} nơi sử dụng chưa có trong danh mục phòng:** " + ", ".join(missing[:30])
                    + (" ..." if len(missing) > 30 else ""))
        if st.button("Thêm tất cả vào danh mục (lấy người quản lý từ thiết bị)", icon=":material/playlist_add:"):
            with st.spinner("Đang tạo..."):
                storage.batch(schema.PHONG, [("create", {"Title": room, "TenPhong": room,
                                                         "NguoiQuanLy": managers.get(room, "")}) for room in missing])
            ui.flash(f"Đã thêm {len(missing)} phòng vào danh mục.")
            st.rerun()

with st.form("add_room", clear_on_submit=True):
    st.markdown("**Thêm phòng mới**")
    c1, c2 = st.columns(2)
    code = c1.text_input("Mã phòng (Nơi sử dụng) *", placeholder="VD: L1_PH103")
    name = c2.text_input("Tên phòng")
    c1, c2 = st.columns(2)
    email = ui.user_picker(c1, "Người quản lý phòng", key="add_room_ql", blank="(Chưa có)")
    ten = c2.text_input("Tên người quản lý", help="Để trống sẽ lấy họ tên theo danh sách người dùng.")
    if st.form_submit_button("Thêm phòng", type="primary", icon=":material/add:"):
        code = code.strip()
        if not code:
            st.error("Nhập mã phòng.")
        elif (phong["Title"].str.lower() == code.lower()).any():
            st.error(f"Phòng {code} đã có trong danh mục.")
        else:
            ten = ten.strip() or thietbi.user_directory().get(email, "")
            storage.create(schema.PHONG, {"Title": code, "TenPhong": name.strip() or code,
                                          "NguoiQuanLy": email.strip().lower(), "TenNguoiQuanLy": ten})
            n = sync_items(code, email.strip().lower()) if email.strip() else 0
            ui.flash(f"Đã thêm phòng {code}" + (f", cập nhật {n} thiết bị." if n else "."))
            st.rerun()

st.markdown("##### Danh mục phòng")
st.caption("Sửa trực tiếp trong bảng rồi bấm Lưu. Chỉ xóa được phòng không còn thiết bị.")
view = phong[["id", "Title", "TenPhong", "NguoiQuanLy", "TenNguoiQuanLy"]].copy()
view["SoTB"] = view["Title"].map(tb.groupby("NoiSuDung").size()).fillna(0).astype(int)
view["Xoa"] = False
edited = st.data_editor(
    view, hide_index=True, width="stretch", key="phong_editor", disabled=["id", "Title", "SoTB"],
    column_config={
        "id": None, "Title": "Mã phòng", "TenPhong": "Tên phòng",
        "NguoiQuanLy": "Email người quản lý", "TenNguoiQuanLy": "Tên người quản lý",
        "SoTB": "Số thiết bị", "Xoa": st.column_config.CheckboxColumn("Xóa"),
    },
)
if st.button("Lưu thay đổi", icon=":material/save:"):
    original = view.set_index("id")
    changes, synced = 0, 0
    with st.spinner("Đang lưu..."):
        for row in edited.itertuples(index=False):
            if row.Xoa:
                if row.SoTB:
                    st.error(f"Phòng {row.Title} còn {row.SoTB} thiết bị, hãy điều chuyển trước khi xóa.")
                    st.stop()
                storage.delete(schema.PHONG, row.id)
                changes += 1
                continue
            old = original.loc[row.id]
            fields = {}
            for k in ("TenPhong", "NguoiQuanLy", "TenNguoiQuanLy"):
                val = (getattr(row, k) or "").strip()
                if k == "NguoiQuanLy":
                    val = val.lower()
                if val != old[k]:
                    fields[k] = val
            if fields:
                storage.update(schema.PHONG, row.id, fields)
                changes += 1
            if fields.get("NguoiQuanLy"):
                synced += sync_items(row.Title, fields["NguoiQuanLy"])
    ui.flash(f"Đã lưu {changes} thay đổi" + (f", cập nhật Quản lý phòng cho {synced} thiết bị." if synced else "."))
    st.rerun()
