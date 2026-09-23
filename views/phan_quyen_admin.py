import streamlit as st

from qlts import auth, schema, storage, ui

me = auth.require(schema.ROLE_ADMIN)
st.subheader("Phân quyền admin")
st.caption(
    "Gán vai trò cho người dùng. Một người có thể có nhiều vai trò (mỗi vai trò một dòng). "
    "Người quản lý phòng không cần vai trò – chỉ cần được gán ở mục Phân quyền quản lý phòng."
)

pq = storage.load(schema.PHAN_QUYEN)

with st.form("add_role", clear_on_submit=True):
    c1, c2 = st.columns(2)
    email = c1.text_input("Email (tài khoản Microsoft 365) *")
    ho_ten = c2.text_input("Họ tên")
    c1, c2 = st.columns(2)
    vai_tro = c1.selectbox("Vai trò", schema.ROLES)
    chuc_danh = c2.text_input("Chức danh hiển thị", placeholder="VD: Chuyên viên Quản lý hệ thống")
    if st.form_submit_button("Thêm phân quyền", type="primary", icon=":material/person_add:"):
        email = email.strip().lower()
        if "@" not in email:
            st.error("Email không hợp lệ.")
        elif ((pq["Title"].str.lower() == email) & (pq["VaiTro"] == vai_tro)).any():
            st.error("Người dùng đã có vai trò này.")
        else:
            storage.create(schema.PHAN_QUYEN, {"Title": email, "HoTen": ho_ten, "VaiTro": vai_tro,
                                               "ChucDanh": chuc_danh})
            ui.flash(f"Đã cấp quyền {vai_tro} cho {email}.")
            st.rerun()

st.markdown("##### Danh sách phân quyền")
st.caption("Sửa trực tiếp trong bảng; tick cột **Xóa** để thu hồi quyền, rồi bấm Lưu.")
view = pq[["id", "Title", "HoTen", "VaiTro", "ChucDanh"]].copy()
view["Xoa"] = False
edited = st.data_editor(
    view, hide_index=True, width="stretch", key="pq_editor", disabled=["id", "Title"],
    column_config={
        "id": None,
        "Title": "Email", "HoTen": "Họ tên", "ChucDanh": "Chức danh",
        "VaiTro": st.column_config.SelectboxColumn("Vai trò", options=schema.ROLES, required=True),
        "Xoa": st.column_config.CheckboxColumn("Xóa"),
    },
)
if st.button("Lưu thay đổi", icon=":material/save:"):
    original = view.set_index("id")
    changes = 0
    for row in edited.itertuples(index=False):
        if row.Xoa:
            if row.Title.lower() == me.email and row.VaiTro == schema.ROLE_ADMIN:
                st.error("Không thể tự thu hồi quyền quản trị của chính bạn.")
                st.stop()
            storage.delete(schema.PHAN_QUYEN, row.id)
            changes += 1
            continue
        old = original.loc[row.id]
        fields = {k: getattr(row, k) for k in ("HoTen", "VaiTro", "ChucDanh") if getattr(row, k) != old[k]}
        if fields:
            storage.update(schema.PHAN_QUYEN, row.id, fields)
            changes += 1
    ui.flash(f"Đã lưu {changes} thay đổi.")
    st.rerun()
