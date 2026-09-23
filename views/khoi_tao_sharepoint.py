import streamlit as st

from qlts import auth, schema, sp_setup, storage

auth.require(schema.ROLE_ADMIN)
st.subheader("Khởi tạo SharePoint")

store = storage.get_store()
if storage.is_demo():
    st.info("Ứng dụng đang chạy chế độ demo, chưa kết nối SharePoint.")
    st.stop()

cfg = store.cfg
st.markdown(
    f"Site: `https://{cfg['hostname']}/{cfg['site_path'].strip('/')}`  \n"
    f"Chế độ truy cập: **{'Quyền của người đăng nhập' if cfg['mode'] == 'delegated' else 'Quyền ứng dụng'}**"
)
st.write(
    "Bấm nút dưới đây để tạo các list còn thiếu (ThietBi, Phong, DieuChuyen, KiemKe, PhanQuyen) "
    "và bổ sung cột còn thiếu. List và dữ liệu đã có được giữ nguyên. "
    "Tài khoản của bạn cần quyền **Owner** trên site."
)
if st.button("Kiểm tra & tạo list", type="primary", icon=":material/build:"):
    with st.spinner("Đang làm việc với SharePoint..."):
        log = sp_setup.ensure_lists(store)
    storage.refresh()
    for line in log:
        st.write("✓", line)
    st.success("Hoàn tất.")
