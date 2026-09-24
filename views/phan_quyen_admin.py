import streamlit as st

from qlts import auth, schema, storage, ui

me = auth.require(schema.ROLE_ADMIN)
st.subheader("Phân quyền admin")
st.caption(
    "Gán vai trò cho người dùng. Một người có thể có nhiều vai trò (mỗi vai trò một dòng). "
    "Người quản lý phòng không cần vai trò – chỉ cần được gán ở mục Phân quyền quản lý phòng."
)

pq = storage.load(schema.PHAN_QUYEN)
ver = st.session_state.setdefault("pq_ver", 0)


def duplicate(email: str, vai_tro: str, skip_id: str = "") -> bool:
    return ((pq["Title"].str.lower() == email) & (pq["VaiTro"] == vai_tro) & (pq["id"] != skip_id)).any()


@st.dialog("Thêm phân quyền")
def add_dialog() -> None:
    with st.form("add_role", border=False):
        email = st.text_input("Email (tài khoản Microsoft 365) *")
        ho_ten = st.text_input("Họ tên")
        vai_tro = st.selectbox("Vai trò", schema.ROLES)
        chuc_danh = st.text_input("Chức danh hiển thị", placeholder="VD: Chuyên viên Quản lý hệ thống")
        ok = st.form_submit_button("Thêm", type="primary", icon=":material/person_add:")
    if ok:
        email = email.strip().lower()
        if "@" not in email:
            st.error("Email không hợp lệ.")
        elif duplicate(email, vai_tro):
            st.error("Người dùng đã có vai trò này.")
        else:
            storage.create(schema.PHAN_QUYEN, {"Title": email, "HoTen": ho_ten.strip(), "VaiTro": vai_tro,
                                               "ChucDanh": chuc_danh.strip()})
            ui.flash(f"Đã cấp quyền {vai_tro} cho {email}.")
            st.rerun()


@st.dialog("Sửa phân quyền")
def edit_dialog(row) -> None:
    with st.form(f"edit_role_{row.id}", border=False):
        st.text_input("Email", row.Title, disabled=True)
        ho_ten = st.text_input("Họ tên", row.HoTen)
        roles = schema.ROLES if row.VaiTro in schema.ROLES else [row.VaiTro, *schema.ROLES]
        vai_tro = st.selectbox("Vai trò", roles, index=roles.index(row.VaiTro) if row.VaiTro in roles else 0)
        chuc_danh = st.text_input("Chức danh hiển thị", row.ChucDanh)
        ok = st.form_submit_button("Lưu thay đổi", type="primary", icon=":material/save:")
    if ok:
        fields = {k: v for k, v in (("HoTen", ho_ten.strip()), ("VaiTro", vai_tro), ("ChucDanh", chuc_danh.strip()))
                  if v != getattr(row, k)}
        if row.Title.lower() == me.email and row.VaiTro == schema.ROLE_ADMIN and "VaiTro" in fields:
            st.error("Không thể tự thu hồi quyền quản trị của chính bạn.")
        elif "VaiTro" in fields and duplicate(row.Title.lower(), vai_tro, row.id):
            st.error("Người dùng đã có vai trò này.")
        else:
            if fields:
                storage.update(schema.PHAN_QUYEN, row.id, fields)
            ui.flash(f"Đã cập nhật phân quyền của {row.Title}." if fields else "Không có thay đổi nào.")
            st.rerun()


st.markdown("##### Danh sách phân quyền")
c1, c2 = st.columns([1, 3], vertical_alignment="center")
if c1.button("Thêm phân quyền", icon=":material/person_add:", width="stretch"):
    add_dialog()
kw = c2.text_input("Tìm", placeholder="Tìm theo email, họ tên, vai trò...", label_visibility="collapsed")
view = pq[["id", "Title", "HoTen", "VaiTro", "ChucDanh"]].sort_values(["VaiTro", "Title"]).reset_index(drop=True)
if kw:
    view = view[view.drop(columns="id").apply(lambda r: kw.lower() in " ".join(r).lower(), axis=1)]
    view = view.reset_index(drop=True)

actions = st.container()
event = st.dataframe(
    view, hide_index=True, width="stretch", on_select="rerun", selection_mode="multi-row", key=f"pq_table_{ver}",
    column_config={"id": None, "Title": "Email", "HoTen": "Họ tên", "VaiTro": "Vai trò", "ChucDanh": "Chức danh"},
)
chosen = view.iloc[event.selection.rows]


def delete_selected() -> str | None:
    if ((chosen["Title"].str.lower() == me.email) & (chosen["VaiTro"] == schema.ROLE_ADMIN)).any():
        return "Không thể tự thu hồi quyền quản trị của chính bạn – bỏ chọn dòng đó rồi thử lại."
    errors = storage.batch(schema.PHAN_QUYEN, [("delete", i) for i in chosen["id"]])
    if errors:
        return "Có lỗi khi xóa:\n\n" + "\n\n".join(errors[:10])
    st.session_state["pq_ver"] = ver + 1
    ui.flash(f"Đã thu hồi {len(chosen)} phân quyền.")


with actions:
    edit_clicked, del_clicked = ui.selection_actions("pq", len(chosen))
if edit_clicked:
    edit_dialog(chosen.iloc[0])
if del_clicked:
    ui.confirm_dialog("Thu hồi phân quyền", f"Bạn có chắc muốn **thu hồi {len(chosen)} phân quyền** sau?",
                      delete_selected, confirm_label="Đồng ý thu hồi",
                      details=[f"{r.Title} – {r.VaiTro}" for r in chosen.itertuples()])
