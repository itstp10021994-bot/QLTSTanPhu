import streamlit as st

from qlts import auth, kiemke, thietbi

user = auth.require()
st.subheader("Kiểm kê phòng tôi quản lý")

rooms = thietbi.rooms_managed_by(user.email)
if not rooms:
    st.info("Bạn chưa được phân công quản lý phòng nào.")
else:
    kiemke.render(user, rooms, key="user_kk", allow_update_status=False)
