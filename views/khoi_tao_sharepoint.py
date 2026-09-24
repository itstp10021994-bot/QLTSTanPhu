import pandas as pd
import streamlit as st

from qlts import auth, diagnostics, schema, sp_setup, storage

auth.require(schema.ROLE_ADMIN)
st.subheader("Kết nối SharePoint")

st.markdown("##### Kiểm tra kết nối")
st.caption("Nếu dữ liệu nhập trong app không thấy trên SharePoint, sửa lần lượt các dòng ❌ bên dưới.")


def show(rows):
    if rows:
        st.dataframe(pd.DataFrame(rows, columns=["", "Bước", "Chi tiết"]), hide_index=True, width="stretch",
                     column_config={"": st.column_config.TextColumn(width=40)})


show(diagnostics.config_checks())
show(diagnostics.login_checks())
if st.button("Kiểm tra truy cập site và các list", icon=":material/lan:"):
    with st.spinner("Đang kết nối SharePoint..."):
        show(diagnostics.sharepoint_checks())
if not storage.is_demo() and st.button("Ghi thử 1 dòng (rồi xóa)", icon=":material/edit_note:",
                                       help="Kiểm tra tài khoản có quyền ghi vào list Phong."):
    status, message = diagnostics.write_test()
    (st.success if status == diagnostics.OK else st.error)(message)

store = storage.get_store()
if storage.is_demo():
    st.stop()

cfg = store.cfg
st.divider()
st.markdown(
    f"Site: `https://{cfg['hostname']}/{cfg['site_path'].strip('/')}`  \n"
    f"Chế độ truy cập: **{'Quyền của người đăng nhập' if cfg['mode'] == 'delegated' else 'Quyền ứng dụng'}**"
)

st.markdown("##### 1. Kiểm tra cột của từng list")
st.caption("App tự dò cột theo tên hiển thị. Cột ❌ sẽ để trống khi đọc và bị bỏ qua khi ghi.")
names = {k: store.real_list_name(k) for k in schema.LISTS}
key = st.selectbox("List", list(names), format_func=lambda k: names[k])
if st.button("Kiểm tra", icon=":material/fact_check:"):
    try:
        st.dataframe(sp_setup.column_report(store, key), hide_index=True, width="stretch")
    except storage.TokenExpired:
        raise
    except storage.StorageError as exc:
        st.error(f"Không đọc được list {names[key]}: {exc}")

st.markdown("##### 2. Tạo các list còn thiếu")
st.write(
    "Tạo các list ứng dụng cần mà site chưa có (Phong, DieuChuyen, KiemKe, PhanQuyen...). "
    "List và dữ liệu đã có được giữ nguyên. Tài khoản của bạn cần quyền **Owner** trên site."
)
add_tb = st.checkbox(
    f"Thêm cả các cột còn thiếu vào list thiết bị “{names[schema.THIET_BI]}”", value=False,
    help="Mặc định không đụng vào list thiết bị đang dùng.",
)
if st.button("Tạo list còn thiếu", type="primary", icon=":material/build:"):
    add_to = set(schema.LISTS) - ({schema.THIET_BI} if not add_tb else set())
    with st.spinner("Đang làm việc với SharePoint..."):
        log = sp_setup.ensure_lists(store, add_columns_to=add_to)
    storage.refresh()
    for line in log:
        st.write("•", line)
    st.success("Hoàn tất.")

