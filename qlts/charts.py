"""Biểu đồ cho trang Báo cáo (Altair – có sẵn trong Streamlit).

Màu: một màu cho biểu đồ một chuỗi; biểu đồ tròn dùng bảng màu phân loại cố định (đã kiểm tra phân biệt
cho người mù màu), tối đa 7 phần + "Khác". Mỗi biểu đồ có tooltip; số liệu chi tiết nằm ở bảng đi kèm.
"""

from __future__ import annotations

import altair as alt
import pandas as pd

BLUE = "#2a78d6"
CATEGORICAL = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7"]
OTHER = "#9e9d97"
OTHER_LABEL = "Khác"


def _axis(title: str, grid: bool = True) -> alt.Axis:
    """Trục giá trị: tiền hiển thị theo triệu đồng ("15 tr"), số đếm là số nguyên."""
    if "VNĐ" in title:
        return alt.Axis(grid=grid, labelExpr="format(datum.value / 1e6, ',.0f') + ' tr'")
    return alt.Axis(grid=grid, format="d", tickMinStep=1)


def donut(df: pd.DataFrame, cat: str, val: str, cat_title: str, val_title: str, height: int = 300):
    """Biểu đồ tròn (vành khuyên) – tối đa 7 phần lớn nhất, phần còn lại gộp vào 'Khác'."""
    data = df[[cat, val]].copy()
    data = data[data[val] > 0].sort_values(val, ascending=False)
    if data.empty:
        return None
    if len(data) > 7:
        head, tail = data.iloc[:7], data.iloc[7:]
        data = pd.concat([head, pd.DataFrame([{cat: OTHER_LABEL, val: tail[val].sum()}])], ignore_index=True)
    data["TyLe"] = data[val] / data[val].sum()
    order = list(data[cat])
    colors = CATEGORICAL[: len(order)]
    if order and order[-1] == OTHER_LABEL:
        colors = CATEGORICAL[: len(order) - 1] + [OTHER]
    base = alt.Chart(data).encode(
        theta=alt.Theta(f"{val}:Q", stack=True),
        color=alt.Color(f"{cat}:N", title=cat_title, sort=order,
                        scale=alt.Scale(domain=order, range=colors),
                        legend=alt.Legend(orient="right", labelLimit=180)),
        order=alt.Order("TyLe:Q", sort="descending"),
        tooltip=[alt.Tooltip(f"{cat}:N", title=cat_title), alt.Tooltip(f"{val}:Q", title=val_title, format=",.0f"),
                 alt.Tooltip("TyLe:Q", title="Tỷ lệ", format=".1%")],
    )
    arcs = base.mark_arc(innerRadius=62, outerRadius=110, stroke="white", strokeWidth=2)
    labels = base.transform_filter(alt.datum.TyLe >= 0.06).mark_text(radius=128, fontSize=11).encode(
        text=alt.Text("TyLe:Q", format=".0%"), color=alt.value("#52514e"))
    return (arcs + labels).properties(height=height)


def hbar(df: pd.DataFrame, cat: str, val: str, cat_title: str, val_title: str, top: int = 15,
         height: int | None = None):
    """Cột ngang một màu, sắp xếp giảm dần (tối đa ``top`` dòng)."""
    data = df[[cat, val]].copy()
    data = data[data[val] > 0].sort_values(val, ascending=False).head(top)
    if data.empty:
        return None
    return alt.Chart(data).mark_bar(color=BLUE, cornerRadiusEnd=4, height={"band": 0.7}).encode(
        y=alt.Y(f"{cat}:N", sort="-x", title=None, axis=alt.Axis(labelLimit=220)),
        x=alt.X(f"{val}:Q", title=val_title, axis=_axis(val_title)),
        tooltip=[alt.Tooltip(f"{cat}:N", title=cat_title), alt.Tooltip(f"{val}:Q", title=val_title, format=",.0f")],
    ).properties(height=height or max(140, 26 * len(data)))


def vbar(df: pd.DataFrame, cat: str, val: str, cat_title: str, val_title: str, sort: list | None = None,
         height: int = 280):
    """Cột đứng một màu, giữ thứ tự ``sort`` (vd nhóm tuổi, mức giá)."""
    data = df[[cat, val]].copy()
    if data.empty or data[val].sum() == 0:
        return None
    return alt.Chart(data).mark_bar(color=BLUE, cornerRadiusEnd=4, width={"band": 0.6}).encode(
        x=alt.X(f"{cat}:N", sort=sort or "-y", title=None, axis=alt.Axis(labelAngle=0, labelLimit=120)),
        y=alt.Y(f"{val}:Q", title=val_title, axis=_axis(val_title)),
        tooltip=[alt.Tooltip(f"{cat}:N", title=cat_title), alt.Tooltip(f"{val}:Q", title=val_title, format=",.0f")],
    ).properties(height=height)


def line(df: pd.DataFrame, x: str, y: str, x_title: str, y_title: str, temporal: bool = False, height: int = 280):
    """Đường một chuỗi (2px) + điểm, có tooltip."""
    data = df[[x, y]].dropna()
    if data.empty:
        return None
    if temporal:
        xenc = alt.X(f"{x}:T", title=x_title, axis=alt.Axis(labelAngle=0, format="%m/%Y", tickCount="month"))
        xtip = alt.Tooltip(f"{x}:T", title=x_title, format="%m/%Y")
    else:
        xenc = alt.X(f"{x}:O", title=x_title, axis=alt.Axis(labelAngle=0))
        xtip = alt.Tooltip(f"{x}:O", title=x_title)
    base = alt.Chart(data).encode(
        x=xenc, y=alt.Y(f"{y}:Q", title=y_title, axis=_axis(y_title)),
        tooltip=[xtip, alt.Tooltip(f"{y}:Q", title=y_title, format=",.0f")],
    )
    return (base.mark_line(color=BLUE, strokeWidth=2) + base.mark_point(color=BLUE, filled=True, size=60)) \
        .properties(height=height)


def grouped_bar(df: pd.DataFrame, cat: str, series: dict[str, str], cat_title: str, val_title: str,
                top: int = 15):
    """Cột ngang nhóm 2–3 chuỗi (vd Thiếu / Thừa) – có chú thích."""
    data = df[[cat, *series]].head(top).melt(cat, var_name="Chuoi", value_name="GiaTri")
    data["Chuoi"] = data["Chuoi"].map(series)
    data = data[data["GiaTri"] > 0]
    if data.empty:
        return None
    names = list(series.values())
    return alt.Chart(data).mark_bar(cornerRadiusEnd=4).encode(
        y=alt.Y(f"{cat}:N", title=None, axis=alt.Axis(labelLimit=220)),
        yOffset=alt.YOffset("Chuoi:N", sort=names),
        x=alt.X("GiaTri:Q", title=val_title, axis=_axis(val_title)),
        color=alt.Color("Chuoi:N", title=None, sort=names,
                        scale=alt.Scale(domain=names, range=CATEGORICAL[: len(names)]),
                        legend=alt.Legend(orient="top")),
        tooltip=[alt.Tooltip(f"{cat}:N", title=cat_title), alt.Tooltip("Chuoi:N", title=" "),
                 alt.Tooltip("GiaTri:Q", title=val_title, format=",.0f")],
    ).properties(height=max(160, 40 * data[cat].nunique()))
