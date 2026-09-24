import streamlit as st

from qlts import auth, kiemke, thietbi

user = auth.require()
st.subheader("Xác nhận kiểm kê phòng tôi quản lý")
st.caption("Xem kết quả Ban kiểm kê đã kiểm và xác nhận đồng ý / không đồng ý cho từng phòng.")

kiemke.render_confirm(user, thietbi.rooms_managed_by(user.email), key="user_kk")
