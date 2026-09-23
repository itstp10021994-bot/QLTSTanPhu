import streamlit as st

from qlts import auth, kiemke, schema, storage

user = auth.require()
st.subheader("Kiểm kê phòng tôi quản lý")

phong = storage.load(schema.PHONG)
rooms = list(phong[phong["NguoiQuanLy"].str.strip().str.lower() == user.email]["Title"])
if not rooms:
    st.info("Bạn chưa được phân công quản lý phòng nào.")
else:
    kiemke.render(user, rooms, key="user_kk", allow_update_status=False)
