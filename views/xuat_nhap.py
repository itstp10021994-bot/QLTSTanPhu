"""Admin: xuất biểu mẫu / dữ liệu Excel và nhập Excel lên các SharePoint List."""

import io
import zipfile
from datetime import date

import streamlit as st

from qlts import auth, excel_io, schema, storage, thietbi, ui

user = auth.require(schema.ROLE_ADMIN)
st.subheader("Xuất / nhập biểu mẫu")
st.caption("Tải biểu mẫu Excel, xuất dữ liệu đang có trên SharePoint, hoặc nhập hàng loạt từ file Excel.")

store = storage.get_store()


def real_name(key: str) -> str:
    return store.real_list_name(key) if hasattr(store, "real_list_name") else schema.LISTS[key]["sp_list"]


if storage.is_demo():
    st.error("App đang ở **chế độ DEMO**: dữ liệu nhập ở đây chỉ lưu tạm trong app, **không lên SharePoint**. "
             "Vào **Phân quyền → Kết nối SharePoint** để xem bước cấu hình còn thiếu.", icon=":material/cloud_off:")

list_key = st.selectbox(
    "List", list(excel_io.LIST_TITLES),
    format_func=lambda k: f"{excel_io.LIST_TITLES[k]} ({real_name(k)})",
)
labels = schema.labels_of(list_key)
if not storage.is_demo():
    try:
        store.list_id(list_key)
        st.caption(f"Ghi vào SharePoint: {store.list_web_urls.get(real_name(list_key)) or real_name(list_key)}")
    except storage.TokenExpired:
        raise
    except storage.StorageError as exc:
        st.error(str(exc))
        st.stop()
today = date.today().strftime("%Y%m%d")

# ---------------------------------------------------------------------------
st.markdown("##### Xuất")
data = storage.load(list_key)
c1, c2, c3 = st.columns(3)
c1.download_button(
    "Biểu mẫu trống", excel_io.template_workbook(list_key, real_name(list_key)),
    file_name=f"bieu_mau_{real_name(list_key)}.xlsx", icon=":material/description:", width="stretch",
    help="Có 1 dòng mẫu và sheet hướng dẫn kiểu cột. Dùng để nhập dữ liệu hoặc tạo list mới trên SharePoint.",
)
c2.download_button(
    f"Dữ liệu hiện có ({len(data)} dòng)",
    excel_io.template_workbook(list_key, real_name(list_key), rows=data.drop(columns="id")),
    file_name=f"{real_name(list_key)}_{today}.xlsx", icon=":material/download:", width="stretch",
    help="Sửa file này rồi nhập lại: các dòng trùng khóa sẽ được cập nhật.",
)
buf = io.BytesIO()
with zipfile.ZipFile(buf, "w") as zf:
    for key, (filename, name) in excel_io.FILES.items():
        zf.writestr(filename, excel_io.template_workbook(key, real_name(key)))
c3.download_button("Tất cả biểu mẫu (.zip)", buf.getvalue(), file_name="bieu_mau_qltb.zip",
                   icon=":material/folder_zip:", width="stretch")

keys = excel_io.MATCH_KEYS[list_key]
if keys:
    st.caption("Khóa nhận biết dòng đã có: **" + " + ".join(labels[k] for k in keys) + "**.")
else:
    st.caption("List này là lịch sử: mọi dòng nhập vào đều được thêm mới.")

# ---------------------------------------------------------------------------
st.markdown("##### Nhập")
upload = st.file_uploader("Chọn file .xlsx hoặc .csv (dòng đầu là tên cột như biểu mẫu)", type=["xlsx", "csv"],
                          key=f"upload_{list_key}_{st.session_state.get('xn_version', 0)}")
if upload is None:
    st.stop()

try:
    rows, unknown = excel_io.read_upload(upload, list_key)
except Exception as exc:  # file hỏng / sai định dạng
    st.error(f"Không đọc được file: {exc}")
    st.stop()
if rows.empty:
    st.warning("Không tìm thấy dòng dữ liệu nào khớp với cột của list này. Hãy dùng biểu mẫu trống ở trên.")
    st.stop()
st.write(f"Đọc được **{len(rows)}** dòng, **{len(rows.columns)}** cột khớp.")
if unknown:
    st.warning("Bỏ qua các cột không có trong list: " + ", ".join(unknown))
st.dataframe(rows.head(50).astype(object).fillna("").rename(columns=labels), hide_index=True, width="stretch")

update_existing = st.radio(
    "Dòng đã có trên SharePoint (trùng khóa)", [True, False], horizontal=True,
    format_func=lambda v: "Cập nhật theo file" if v else "Bỏ qua, chỉ thêm dòng mới",
    disabled=not keys,
)
plan = excel_io.plan_import(
    list_key, rows, storage.load(list_key), update_existing, user_name=user.name,
    managers=thietbi.room_managers() if list_key == schema.THIET_BI else None,
)
m1, m2, m3, m4 = st.columns(4)
m1.metric("Thêm mới", plan["create"], border=True)
m2.metric("Cập nhật", plan["update"], border=True)
m3.metric("Bỏ qua", plan["skip"], border=True)
m4.metric("Lỗi", len(plan["problems"]), border=True)
if plan["problems"]:
    with st.expander(f"{len(plan['problems'])} dòng lỗi sẽ không được nhập", expanded=True):
        for p in plan["problems"][:100]:
            st.write("•", p)
st.caption("Ô trống trong file không ghi đè dữ liệu đang có.")

target = "dữ liệu DEMO (không lên SharePoint)" if storage.is_demo() else "SharePoint"
if st.button(f"Nhập {len(plan['ops'])} dòng vào {target}", type="primary", icon=":material/upload:",
             disabled=not plan["ops"]):
    bar = st.progress(0.0, text="Đang ghi lên SharePoint...")
    errors = storage.batch(list_key, plan["ops"],
                           progress=lambda f: bar.progress(f, text="Đang ghi lên SharePoint..."))
    bar.empty()
    if errors:
        st.error(f"Hoàn tất với {len(errors)} lỗi:\n\n" + "\n\n".join(errors[:30]))
    else:
        st.session_state["xn_version"] = st.session_state.get("xn_version", 0) + 1
        after = len(storage.load_fresh(list_key))  # đọc lại trực tiếp để xác nhận
        where = "dữ liệu DEMO" if storage.is_demo() else f"SharePoint list {real_name(list_key)}"
        ui.flash(f"Đã nhập vào {where}: {plan['create']} thêm mới, {plan['update']} cập nhật. "
                 f"List hiện có {after} dòng (trước khi nhập: {len(data)}).")
        st.rerun()
