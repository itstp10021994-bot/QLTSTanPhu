"""Trợ lý tra cứu (không dùng AI): gõ câu hỏi tự nhiên, app nhận diện từ khóa và trả kết quả từ SharePoint."""

import pandas as pd
import streamlit as st

from qlts import auth, schema, storage, thietbi, tracuu, ui

user = auth.require()
st.subheader("Trợ lý tra cứu")
st.caption("Gõ câu hỏi ngắn: mã thiết bị, tên phòng, loại thiết bị, nhóm, tình trạng, người sử dụng, hoặc "
           "*kiểm kê / điều chuyển / thanh lý*. Trợ lý chạy ngay trong app – không dùng AI, dữ liệu không gửi ra ngoài.")


def load(key: str) -> pd.DataFrame:
    try:
        return storage.load(key)
    except storage.StorageError:
        return storage.empty_frame(key)


full_access = user.has_any(schema.ROLE_QLTS, schema.ROLE_BGH, schema.ROLE_KIEMKE)
ctx = tracuu.Context(
    tb=load(schema.THIET_BI), phong=load(schema.PHONG), kk=load(schema.KIEM_KE), dc=load(schema.DIEU_CHUYEN),
    tl=load(schema.THANH_LY), catalog=thietbi.load_catalog(), users=thietbi.user_directory(),
    managers=thietbi.room_managers(), labels=ui.room_label_map(),
    allowed_rooms=None if full_access else set(thietbi.rooms_managed_by(user.email)),
)
if not full_access:
    st.info("Bạn chỉ tra cứu được thiết bị trong các phòng mình quản lý.", icon=":material/lock:")

history: list = st.session_state.setdefault("tc_history", [])
NUM_COLS = {"Giá trị", "Giá trị (VNĐ)", "Tổng giá mua (VNĐ)", "Giá mua mới", "Số thiết bị"}


def render(parts: list, key: str) -> None:
    for n, (kind, val) in enumerate(parts):
        if kind == "md":
            st.markdown(val)
        elif kind == "metrics":
            cols = st.columns(len(val))
            for col, (label, value) in zip(cols, val):
                col.metric(label, value)
        elif kind == "table":
            config = {c: st.column_config.NumberColumn(format="localized") for c in val.columns if c in NUM_COLS}
            st.dataframe(val, hide_index=True, width="stretch", column_config=config,
                         height=min(420, 38 + 35 * len(val)))
            if len(val) > 10:
                st.download_button("Tải Excel", ui.to_excel({"KetQua": val}), file_name="tra_cuu.xlsx",
                                   icon=":material/download:", key=f"tc_dl_{key}_{n}", on_click="ignore")


def ask(question: str) -> None:
    question = question.strip()
    if question:
        history.append(("user", question))
        history.append(("assistant", tracuu.answer(question, ctx)))


# ---- Câu hỏi mẫu ----
picked = st.pills("Thử hỏi", tracuu.EXAMPLES, key=f"tc_pills_{len(history)}", label_visibility="collapsed")
if picked:
    ask(picked)
    st.rerun()

if not history:
    with st.chat_message("assistant", avatar=":material/search:"):
        render(tracuu.help_parts(), "help")
for i, (role, content) in enumerate(history):
    with st.chat_message(role, avatar=":material/search:" if role == "assistant" else None):
        if role == "user":
            st.markdown(content)
        else:
            render(content, str(i))

c1, c2 = st.columns([6, 1], vertical_alignment="bottom")
if history and c2.button("Xóa lịch sử", icon=":material/delete_sweep:", width="stretch"):
    history.clear()
    st.rerun()
question = st.chat_input("Ví dụ: máy chiếu phòng L1_PH103")
if question:
    ask(question)
    st.rerun()
