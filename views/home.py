import streamlit as st

from qlts import auth, schema, storage, ui

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
phong = storage.load(schema.PHONG)
my_rooms = phong[phong["NguoiQuanLy"].str.strip().str.lower() == user.email]
my_tb = tb[tb["MaPhong"].isin(my_rooms["Title"])]

st.write("")
m1, m2, m3 = st.columns(3)
m1.metric("Phòng bạn đang quản lý", len(my_rooms), border=True)
m2.metric("Số đầu thiết bị trong các phòng", len(my_tb), border=True)
m3.metric("Thiết bị cần sửa chữa / thanh lý",
          int((~my_tb["TinhTrang"].isin(["Tốt", "", "Đã thanh lý"])).sum()), border=True)

if user.roles:
    st.caption("Vai trò: " + ", ".join(sorted(user.roles)))
