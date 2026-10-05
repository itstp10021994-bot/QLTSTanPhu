"""Báo cáo tuyển sinh qua các năm: chia theo Nhập học và Data tuyển sinh, chi tiết theo quận/huyện."""

import pandas as pd
import streamlit as st

from qlts import auth, charts, schema, storage, ui
from qlts import tuyensinh as ts
from qlts.config import app_setting

auth.require(schema.ROLE_BGH, schema.ROLE_TS)
st.subheader("Báo cáo tuyển sinh")

SOURCES = {  # khóa: (nhãn, khóa Secrets tên list, khóa Secrets cột, từ khóa đoán tên list)
    "nh": (ts.NH, "ts_nhap_hoc_list", "ts_cot_nhap_hoc", ["nhaphoc"]),
    "data": (ts.DATA, "ts_data_list", "ts_cot_data", ["datatuyensinh", "tuyensinh", "datats"]),
}


def default_list(src: str, titles: list[str]) -> str | None:
    _, secret, _, words = SOURCES[src]
    if app_setting(secret) in titles:
        return app_setting(secret)
    for w in words:
        for t in titles:
            k = ts._key(t)
            if w in k and (src == "nh" or "nhaphoc" not in k):
                return t
    return None


try:
    titles = storage.raw_lists()
except storage.StorageError as exc:
    st.error(f"Không đọc được danh sách list trên SharePoint: {exc}")
    st.stop()

# ---- Nguồn dữ liệu & cột ----
frames: dict[str, pd.DataFrame] = {}
raw_cols: dict[str, list[str]] = {}
chosen: dict[str, str | None] = {}
for src in SOURCES:
    key = f"ts_list_{src}"
    if st.session_state.get(key) not in titles:
        st.session_state[key] = default_list(src, titles)
    chosen[src] = st.session_state[key]

missing = [SOURCES[s][0] for s in SOURCES if not chosen[s]]
with st.expander("Nguồn dữ liệu & cột", expanded=bool(missing), icon=":material/database:"):
    st.caption("Chọn 2 list trên SharePoint và kiểm tra app đã nhận đúng cột. Quận/huyện, phường/xã được chuẩn hóa "
               "tự động (vd “Q.Tân Bình”, “tân bình” → “Quận Tân Bình”); nếu list không có cột riêng thì tách từ "
               "cột Địa chỉ. Năm học ghi một số (vd 2023) được hiểu là năm học 2023-2024.")
    c = st.columns(2)
    for i, src in enumerate(SOURCES):
        c[i].selectbox(f"List {SOURCES[src][0]}", titles, key=f"ts_list_{src}", index=None,
                       placeholder="Chọn list...")
    mapping_area = st.container()

for src in SOURCES:
    title = st.session_state.get(f"ts_list_{src}")
    if not title:
        continue
    try:
        frames[src] = storage.load_raw(title)
    except storage.StorageError as exc:
        st.error(f"Không đọc được list “{title}”: {exc}")
        st.stop()
    raw_cols[src] = list(frames[src].columns)

if len(frames) < 2:
    names = missing or [SOURCES[s][0] for s in SOURCES if s not in frames]
    st.info("Chọn list **" + "** và **".join(names) + "** trong mục *Nguồn dữ liệu & cột* ở trên.")
    st.stop()

mapping: dict[str, dict[str, str | None]] = {}
with mapping_area:
    tabs_map = st.tabs([f"Cột của list {SOURCES[s][0]}" for s in SOURCES])
    for tab, src in zip(tabs_map, SOURCES):
        cols = raw_cols[src]
        guess = ts.guess_columns(cols)
        guess.update({k: v for k, v in (app_setting(SOURCES[src][2]) or {}).items() if v in cols})
        mapping[src] = {}
        with tab:
            st.caption(f"{len(frames[src]):,} dòng · {len(cols)} cột".replace(",", "."))
            grid = st.columns(3)
            for j, (field, (label, _)) in enumerate(ts.FIELDS.items()):
                opts = [None, *cols]
                mapping[src][field] = grid[j % 3].selectbox(
                    label, opts, index=opts.index(guess.get(field)), key=f"ts_map_{src}_{field}",
                    format_func=lambda v: "— không có —" if v is None else v)

problems = [f"**{SOURCES[s][0]}**: chưa có cột năm học hoặc ngày" for s in SOURCES
            if not (mapping[s]["nam"] or mapping[s]["ngay"])]
problems += [f"**{SOURCES[s][0]}**: chưa có cột quận/huyện hoặc địa chỉ" for s in SOURCES
             if not (mapping[s]["quan"] or mapping[s]["diachi"])]
if problems:
    st.warning("Cần chọn thêm cột trong mục *Nguồn dữ liệu & cột*: " + "; ".join(problems) + ".")


@st.cache_data(show_spinner=False, max_entries=8)
def _prepare(df: pd.DataFrame, cols: tuple) -> pd.DataFrame:
    return ts.prepare(df, dict(cols))


nh_all = _prepare(frames["nh"], tuple(mapping["nh"].items())).copy()
data_all = _prepare(frames["data"], tuple(mapping["data"].items())).copy()
ts.fill_province(nh_all, data_all)

# ---- Bộ lọc ----
all_years = ts.years_of(nh_all, data_all)
known_years = [y for y in all_years if y != ts.UNKNOWN]
f1, f2, f3 = st.columns([2, 1, 1])
years = f1.multiselect("Năm học", all_years, default=known_years or all_years, key="ts_years")
years = [y for y in all_years if y in years]
caps = sorted((set(nh_all["Cap"]) | set(data_all["Cap"])) - {ts.UNKNOWN}) + \
    ([ts.UNKNOWN] if ts.UNKNOWN in set(nh_all["Cap"]) | set(data_all["Cap"]) else [])
f_cap = f2.multiselect("Cấp học", caps, placeholder="Tất cả", key="ts_cap")
khois = sorted(set(nh_all["Khoi"]) | set(data_all["Khoi"]), key=ts.grade_order)
f_khoi = f3.multiselect("Khối", khois, placeholder="Tất cả", key="ts_khoi")


def apply(df: pd.DataFrame) -> pd.DataFrame:
    df = df[df["Nam"].isin(years)]
    if f_cap:
        df = df[df["Cap"].isin(f_cap)]
    if f_khoi:
        df = df[df["Khoi"].isin(f_khoi)]
    return df


nh, data = apply(nh_all), apply(data_all)
if not years:
    st.info("Chọn ít nhất một năm học.")
    st.stop()
note = " · ".join(x for x in [("Cấp: " + ", ".join(f_cap)) if f_cap else "",
                              ("Khối: " + ", ".join(f_khoi)) if f_khoi else ""] if x)

# ---- Chỉ số năm gần nhất ----
by_year = ts.by_year(data, nh, years)
body_year = by_year[by_year["Nam"] != ts.TOTAL]
last = body_year[body_year["Nam"] != ts.UNKNOWN].tail(2)
if not last.empty:
    cur = last.iloc[-1]
    prev = last.iloc[0] if len(last) == 2 else None

    def delta(col):
        return None if prev is None else int(cur[col] - prev[col])

    m1, m2, m3, m4 = st.columns(4)
    m1.metric(f"Data tuyển sinh {cur['Nam']}", f"{int(cur['Data']):,}".replace(",", "."), delta("Data"), border=True)
    m2.metric(f"Nhập học {cur['Nam']}", f"{int(cur['NhapHoc']):,}".replace(",", "."), delta("NhapHoc"), border=True)
    rate_delta = None if prev is None or pd.isna(prev["TyLe"]) or pd.isna(cur["TyLe"]) else \
        f"{cur['TyLe'] - prev['TyLe']:+.1f} điểm %"
    m3.metric("Tỷ lệ nhập học / data", "—" if pd.isna(cur["TyLe"]) else f"{cur['TyLe']:.1f} %", rate_delta,
              border=True)
    n_q = nh[(nh["Nam"] == cur["Nam"]) & (nh["QuanHuyen"] != ts.UNKNOWN)]["QuanHuyen"].nunique()
    m4.metric("Số quận/huyện có HS nhập học", n_q, border=True)
st.caption("Báo cáo chỉ hiển thị số tổng hợp, không hiển thị hồ sơ học sinh. "
           "Tỷ lệ nhập học = số nhập học ÷ số data tuyển sinh của cùng năm học.")

NUM = st.column_config.NumberColumn
CFG = {"Nam": "Năm học", "Data": NUM(ts.DATA, format="localized"), "NhapHoc": NUM(ts.NH, format="localized"),
       "TyLe": NUM("Tỷ lệ NH/Data", format="%.1f %%"), "TangGiam": NUM("Tăng/giảm NH so năm trước", format="%+.1f %%")}
SHEETS: dict[str, pd.DataFrame] = {}


def table(title: str, df: pd.DataFrame, sheet: str, config: dict | None = None) -> None:
    st.markdown(f"##### {title}")
    if df.empty:
        st.info("Chưa có dữ liệu.")
        return
    cfg = dict(config or {})
    for c in df.columns:
        if c in ts.DIMS.values():
            cfg.setdefault(c, st.column_config.TextColumn(c, pinned=True))
        elif c not in cfg and pd.api.types.is_numeric_dtype(df[c]):
            cfg[c] = NUM(c, format="%.1f %%" if "Tỷ lệ" in c else "localized")
    st.dataframe(df, hide_index=True, width="stretch", column_config=cfg, height="auto" if len(df) <= 14 else 460)
    SHEETS[sheet[:31]] = df


def show(chart, title: str) -> None:
    st.markdown(f"**{title}**")
    if chart is None:
        st.caption("Chưa có dữ liệu.")
    else:
        st.altair_chart(chart, width="stretch")


def long_counts(df: pd.DataFrame, dim: str) -> pd.DataFrame:
    return df.groupby(["Nam", dim]).size().reset_index(name="SoHS")


tab1, tab2, tab3, tab4 = st.tabs(["Qua các năm", "Nhập học", "Data tuyển sinh", "Chi tiết theo quận/huyện"])

with tab1:
    c1, c2 = st.columns(2)
    with c1:
        show(charts.vgrouped(body_year, "Nam", {"Data": ts.DATA, "NhapHoc": ts.NH}, "Năm học", "Số học sinh"),
             "Data tuyển sinh và nhập học theo năm học")
    with c2:
        show(charts.lines(body_year, "Nam", {"TyLe": "Tỷ lệ nhập học (%)"}, "Năm học", "%", fmt=".1f"),
             "Tỷ lệ nhập học / data qua các năm")
    table("Bảng 1. Tổng hợp tuyển sinh theo năm học", by_year, "B1_Theo nam", CFG)
    rate = []
    for cap in [c for c in caps if c != ts.UNKNOWN]:
        r = ts.by_year(data[data["Cap"] == cap], nh[nh["Cap"] == cap], years)
        r = r[r["Nam"] != ts.TOTAL]
        rate.append(r.set_index("Nam")["TyLe"].rename(cap))
    if rate:
        rate_df = pd.concat(rate, axis=1).reset_index()
        show(charts.lines(rate_df, "Nam", {c: c for c in rate_df.columns[1:8]}, "Năm học", "%", fmt=".1f"),
             "Tỷ lệ nhập học theo cấp học")

with tab2:
    c1, c2 = st.columns(2)
    with c1:
        show(charts.stacked(long_counts(nh, "Cap"), "Nam", "Cap", "SoHS", "Năm học", "Cấp học", "Số học sinh",
                            x_order=years), "Nhập học theo cấp học")
    with c2:
        latest = years[-1] if years[-1] != ts.UNKNOWN or len(years) == 1 else years[-2]
        q = nh[nh["Nam"] == latest].groupby("QuanHuyen").size().reset_index(name="SoHS")
        show(charts.hbar(q, "QuanHuyen", "SoHS", "Quận/Huyện", "Số học sinh", top=12),
             f"Quận/huyện có nhiều HS nhập học nhất – {latest}")
    table("Bảng 2. Nhập học theo khối", ts.pivot(nh, "Khoi", years), "B2_NH theo khoi")
    table("Bảng 3. Nhập học theo quận/huyện", ts.pivot(nh, "QuanHuyen", years), "B3_NH theo quan")
    if mapping["nh"]["gioitinh"]:
        table("Bảng 4. Nhập học theo giới tính", ts.pivot(nh, "GioiTinh", years), "B4_NH gioi tinh")
    if mapping["nh"]["nguon"]:
        table("Bảng 5. Nhập học theo nguồn", ts.pivot(nh, "Nguon", years), "B5_NH nguon")

with tab3:
    c1, c2 = st.columns(2)
    with c1:
        show(charts.stacked(long_counts(data, "Cap"), "Nam", "Cap", "SoHS", "Năm học", "Cấp học", "Số hồ sơ",
                            x_order=years), "Data tuyển sinh theo cấp học")
    with c2:
        if mapping["data"]["trangthai"]:
            st_df = data.groupby("TrangThai").size().reset_index(name="SoHS")
            show(charts.donut(st_df, "TrangThai", "SoHS", "Trạng thái", "Số hồ sơ"), "Trạng thái hồ sơ (các năm đã chọn)")
        else:
            q = data.groupby("QuanHuyen").size().reset_index(name="SoHS")
            show(charts.hbar(q, "QuanHuyen", "SoHS", "Quận/Huyện", "Số hồ sơ", top=12), "Data theo quận/huyện")
    table("Bảng 6. Data tuyển sinh theo khối", ts.pivot(data, "Khoi", years), "B6_Data theo khoi")
    table("Bảng 7. Data tuyển sinh theo quận/huyện", ts.pivot(data, "QuanHuyen", years), "B7_Data theo quan")
    if mapping["data"]["trangthai"]:
        table("Bảng 8. Data tuyển sinh theo trạng thái", ts.pivot(data, "TrangThai", years), "B8_Data trang thai")
    if mapping["data"]["nguon"]:
        table("Bảng 9. Data tuyển sinh theo nguồn", ts.pivot(data, "Nguon", years), "B9_Data nguon")

with tab4:
    multi_tinh = len((set(data["Tinh"]) | set(nh["Tinh"])) - {ts.UNKNOWN}) > 1
    detail = ts.compare(data, nh, "QuanHuyen", years, group="Tinh" if multi_tinh else None)
    st.caption("Mẫu chi tiết: mỗi năm học gồm Data tuyển sinh · Nhập học · Tỷ lệ nhập học (%), cột cuối là tổng các năm.")
    table("Bảng 10. Tuyển sinh theo quận/huyện qua các năm", detail, "B10_Quan huyen")
    school = app_setting("school_name", "TRƯỜNG TH-THCS-THPT TÂN PHÚ")
    st.download_button("Tải mẫu chi tiết theo quận/huyện (Excel – tổng hợp + mỗi quận/huyện 1 sheet)",
                       lambda: ts.district_xlsx(data, nh, [y for y in years if y != ts.UNKNOWN] or years, school,
                                                note),
                       file_name="bao_cao_tuyen_sinh_quan_huyen.xlsx", on_click="ignore", type="primary",
                       icon=":material/download:")

    st.divider()
    dists = [d for d in detail[ts.DIMS["QuanHuyen"]] if d not in (ts.TOTAL, "")]
    pick = st.selectbox("Xem chi tiết một quận/huyện", list(dict.fromkeys(dists)), key="ts_pick")
    if pick:
        d, e = data[data["QuanHuyen"] == pick], nh[nh["QuanHuyen"] == pick]
        trend = ts.by_year(d, e, years)
        show(charts.vgrouped(trend[trend["Nam"] != ts.TOTAL], "Nam", {"Data": ts.DATA, "NhapHoc": ts.NH},
                             "Năm học", "Số học sinh", height=240), f"{pick} qua các năm")
        table(f"Bảng 11. {pick} – theo phường/xã", ts.compare(d, e, "PhuongXa", years), "B11_Phuong xa")
        table(f"Bảng 12. {pick} – theo khối", ts.compare(d, e, "Khoi", years), "B12_Khoi")

st.divider()
st.download_button("Xuất toàn bộ báo cáo (Excel, mỗi bảng 1 sheet)", lambda: ui.to_excel(SHEETS),
                   file_name="bao_cao_tuyen_sinh.xlsx", on_click="ignore", icon=":material/table_view:")
