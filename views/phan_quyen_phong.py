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

ver = st.session_state.setdefault("phong_ver", 0)


@st.dialog("Thêm phòng mới")
def add_dialog() -> None:
    code = st.text_input("Mã phòng (Nơi sử dụng) *", placeholder="VD: L1_PH103")
    name = st.text_input("Tên phòng")
    email = ui.user_picker(st, "Người quản lý phòng", key="add_room_ql", blank="(Chưa có)")
    ten = st.text_input("Tên người quản lý", help="Để trống sẽ lấy họ tên theo danh sách người dùng.")
    if st.button("Thêm phòng", type="primary", icon=":material/add:"):
        code = code.strip()
        if not code:
            st.error("Nhập mã phòng.")
        elif (phong["Title"].str.lower() == code.lower()).any():
            st.error(f"Phòng {code} đã có trong danh mục.")
        else:
            email = email.strip().lower()
            ten = ten.strip() or thietbi.user_directory().get(email, "")
            storage.create(schema.PHONG, {"Title": code, "TenPhong": name.strip() or code,
                                          "NguoiQuanLy": email, "TenNguoiQuanLy": ten})
            n = sync_items(code, email) if email else 0
            ui.flash(f"Đã thêm phòng {code}" + (f", cập nhật {n} thiết bị." if n else "."))
            st.rerun()


@st.dialog("Sửa phòng")
def edit_dialog(row) -> None:
    st.text_input("Mã phòng", row.Title, disabled=True)
    name = st.text_input("Tên phòng", row.TenPhong)
    email = ui.user_picker(st, "Người quản lý phòng", default=row.NguoiQuanLy, key=f"edit_room_ql_{row.id}",
                           blank="(Chưa có)")
    auto = thietbi.user_directory().get(email, "") if email != row.NguoiQuanLy.strip().lower() else ""
    ten = st.text_input("Tên người quản lý", auto or row.TenNguoiQuanLy, key=f"edit_room_ten_{row.id}_{email}")
    if row.SoTB:
        st.caption(f"Đổi người quản lý sẽ cập nhật cột Quản lý phòng của {row.SoTB} thiết bị trong phòng.")
    if st.button("Lưu thay đổi", type="primary", icon=":material/save:"):
        new = {"TenPhong": name.strip(), "NguoiQuanLy": email.strip().lower(), "TenNguoiQuanLy": ten.strip()}
        fields = {k: v for k, v in new.items() if v != getattr(row, k)}
        n = 0
        if fields:
            with st.spinner("Đang lưu..."):
                storage.update(schema.PHONG, row.id, fields)
                if "NguoiQuanLy" in fields and fields["NguoiQuanLy"]:
                    n = sync_items(row.Title, fields["NguoiQuanLy"])
        ui.flash((f"Đã cập nhật phòng {row.Title}" + (f", cập nhật Quản lý phòng cho {n} thiết bị." if n else "."))
                 if fields else "Không có thay đổi nào.")
        st.rerun()


st.markdown("##### Danh mục phòng")
c1, c2 = st.columns([1, 3], vertical_alignment="center")
if c1.button("Thêm phòng", icon=":material/add:", width="stretch"):
    add_dialog()
kw = c2.text_input("Tìm", placeholder="Tìm theo mã phòng, tên phòng, người quản lý...", label_visibility="collapsed")
view = phong[["id", "Title", "TenPhong", "NguoiQuanLy", "TenNguoiQuanLy"]].sort_values("Title").copy()
view["SoTB"] = view["Title"].map(tb.groupby("NoiSuDung").size()).fillna(0).astype(int)
if kw:
    view = view[view.drop(columns=["id", "SoTB"]).apply(lambda r: kw.lower() in " ".join(r).lower(), axis=1)]
view = view.reset_index(drop=True)

actions = st.container()
event = st.dataframe(
    view, hide_index=True, width="stretch", on_select="rerun", selection_mode="multi-row", key=f"phong_table_{ver}",
    column_config={"id": None, "Title": "Mã phòng", "TenPhong": "Tên phòng", "NguoiQuanLy": "Email người quản lý",
                   "TenNguoiQuanLy": "Tên người quản lý", "SoTB": st.column_config.NumberColumn("Số thiết bị")},
)
chosen = view.iloc[event.selection.rows]
busy = chosen[chosen["SoTB"] > 0]


def delete_selected() -> str | None:
    errors = storage.batch(schema.PHONG, [("delete", i) for i in chosen["id"]])
    if errors:
        return "Có lỗi khi xóa:\n\n" + "\n\n".join(errors[:10])
    st.session_state["phong_ver"] = ver + 1
    ui.flash(f"Đã xóa {len(chosen)} phòng khỏi danh mục.")


with actions:
    edit_clicked, del_clicked = ui.selection_actions("phong", len(chosen),
                                                     extra="Chỉ xóa được phòng không còn thiết bị.")
if edit_clicked:
    edit_dialog(chosen.iloc[0])
if del_clicked:
    if not busy.empty:
        @st.dialog("Không thể xóa")
        def _blocked():
            st.warning("Các phòng sau còn thiết bị, hãy **điều chuyển** thiết bị đi trước khi xóa:\n\n"
                       + "\n".join(f"- {r.Title}: {r.SoTB} thiết bị" for r in busy.itertuples()))
            if st.button("Đóng", width="stretch"):
                st.rerun()
        _blocked()
    else:
        ui.confirm_dialog("Xóa phòng", f"Bạn có chắc muốn **xóa {len(chosen)} phòng** khỏi danh mục?",
                          delete_selected,
                          details=[f"{r.Title} – {r.TenPhong}" for r in chosen.itertuples()])
