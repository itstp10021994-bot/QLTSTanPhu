import streamlit as st

from qlts import auth, schema, storage, thietbi, ui

user = auth.require()

with st.container(border=True):
    c1, c2 = st.columns([1, 4], vertical_alignment="center")
    logo = ui.logo_path()
    if logo:
        c1.image(logo, width=140)
    else:
        c1.markdown("## :material/inventory_2:")
    c2.markdown(f"#### Xin chào {user.name}")
    c2.markdown(f"**{user.chuc_danh}**")

tb = storage.load(schema.THIET_BI)
my_rooms = thietbi.rooms_managed_by(user.email)
my_tb = tb[tb["NoiSuDung"].isin(my_rooms)]

st.write("")
m1, m2, m3 = st.columns(3)
m1.metric("Phòng bạn đang quản lý", len(my_rooms), border=True)
m2.metric("Thiết bị trong các phòng", len(my_tb), border=True)
m3.metric("Thiết bị cần xử lý", int(thietbi.needs_attention(my_tb).sum()), border=True)

if user.roles:
    st.caption("Vai trò: " + ", ".join(sorted(user.roles)))
