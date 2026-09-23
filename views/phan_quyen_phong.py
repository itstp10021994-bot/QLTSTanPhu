import streamlit as st

from qlts import auth, schema, storage, ui

auth.require(schema.ROLE_ADMIN)
st.subheader("Phân quyền quản lý phòng")
st.caption("Quản lý danh mục phòng và gán người phụ trách. Người phụ trách sẽ thấy phòng ở mục **Người dùng**.")

phong = storage.load(schema.PHONG)
tb = storage.load(schema.THIET_BI)

with st.form("add_room", clear_on_submit=True):
    st.markdown("**Thêm phòng mới**")
    c1, c2, c3 = st.columns(3)
    code = c1.text_input("Mã phòng *")
    name = c2.text_input("Tên phòng *")
    khu = c3.text_input("Khu vực / Dãy")
    c1, c2 = st.columns(2)
    email = c1.text_input("Email người quản lý")
    ten = c2.text_input("Tên người quản lý")
    if st.form_submit_button("Thêm phòng", type="primary", icon=":material/add:"):
        code = code.strip().upper()
        if not code or not name.strip():
            st.error("Nhập mã phòng và tên phòng.")
        elif (phong["Title"].str.upper() == code).any():
            st.error(f"Mã phòng {code} đã tồn tại.")
        else:
            storage.create(schema.PHONG, {"Title": code, "TenPhong": name.strip(), "KhuVuc": khu,
                                          "NguoiQuanLy": email.strip().lower(), "TenNguoiQuanLy": ten})
            ui.flash(f"Đã thêm phòng {code}.")
            st.rerun()

st.markdown("##### Danh sách phòng")
st.caption("Sửa trực tiếp người quản lý trong bảng rồi bấm Lưu. Chỉ xóa được phòng không còn thiết bị.")
view = phong[["id", "Title", "TenPhong", "KhuVuc", "NguoiQuanLy", "TenNguoiQuanLy"]].copy()
view["SoTB"] = view["Title"].map(tb.groupby("MaPhong").size()).fillna(0).astype(int)
view["Xoa"] = False
edited = st.data_editor(
    view, hide_index=True, width="stretch", key="phong_editor", disabled=["id", "Title", "SoTB"],
    column_config={
        "id": None, "Title": "Mã phòng", "TenPhong": "Tên phòng", "KhuVuc": "Khu vực",
        "NguoiQuanLy": "Email người quản lý", "TenNguoiQuanLy": "Tên người quản lý",
        "SoTB": "Số đầu TB", "Xoa": st.column_config.CheckboxColumn("Xóa"),
    },
)
if st.button("Lưu thay đổi", icon=":material/save:"):
    original = view.set_index("id")
    changes = 0
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
        for k in ("TenPhong", "KhuVuc", "NguoiQuanLy", "TenNguoiQuanLy"):
            val = (getattr(row, k) or "").strip()
            if k == "NguoiQuanLy":
                val = val.lower()
            if val != old[k]:
                fields[k] = val
        if fields:
            storage.update(schema.PHONG, row.id, fields)
            changes += 1
    ui.flash(f"Đã lưu {changes} thay đổi.")
    st.rerun()
