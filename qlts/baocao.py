"""Các bảng thống kê cho trang Báo cáo (tính từ dữ liệu SharePoint)."""

from __future__ import annotations

from datetime import date

import pandas as pd

from . import schema, thietbi

TOTAL = "Tổng cộng"


def _name(df: pd.DataFrame) -> pd.Series:
    return df["TenThietBi"].where(df["TenThietBi"].str.strip() != "", df["ChiTiet"]).str.strip()


def _blank(s: pd.Series, text: str = "(chưa phân loại)") -> pd.Series:
    return s.fillna("").astype(str).str.strip().replace("", text)


def _pct(part: pd.Series, whole: float) -> pd.Series:
    return (part / whole * 100).round(1) if whole else part * 0.0


def add_total(df: pd.DataFrame, label_col: str, sum_cols: list[str], pct_cols: dict[str, str] | None = None,
              extra: dict | None = None):
    """Thêm dòng Tổng cộng: cộng các cột ``sum_cols``, cột % = 100, ``extra`` = giá trị tự tính;
    cột chữ còn lại để trống."""
    if df.empty:
        return df
    total = {c: df[c].sum() for c in sum_cols}
    total[label_col] = TOTAL
    for pct_col in (pct_cols or {}):
        total[pct_col] = 100.0
    total.update(extra or {})
    for c in df.columns:
        if c not in total and not pd.api.types.is_numeric_dtype(df[c]):
            total[c] = ""
    return pd.concat([df, pd.DataFrame([total])], ignore_index=True)


def by_group(tb: pd.DataFrame) -> pd.DataFrame:
    """Bảng 1 – Theo nhóm thiết bị."""
    df = tb.assign(Nhom=_blank(tb["NhomThietBi"]), Dispo=thietbi.is_disposed(tb))
    act = df[~df["Dispo"]]
    g = act.groupby("Nhom").agg(SoTB=("id", "size"), SoLoai=("MaTaiSan", "nunique"), GiaTri=("GiaTri", "sum"))
    g["CanXuLy"] = act[thietbi.needs_attention(act)].groupby("Nhom").size()
    g["DaThanhLy"] = df[df["Dispo"]].groupby("Nhom").size()
    g = g.fillna(0).reset_index().sort_values("GiaTri", ascending=False)
    g["TyLeSL"] = _pct(g["SoTB"], g["SoTB"].sum())
    g["TyLeGT"] = _pct(g["GiaTri"], g["GiaTri"].sum())
    g = g[["Nhom", "SoLoai", "SoTB", "TyLeSL", "GiaTri", "TyLeGT", "CanXuLy", "DaThanhLy"]]
    return add_total(g, "Nhom", ["SoTB", "GiaTri", "CanXuLy", "DaThanhLy"], {"TyLeSL": "", "TyLeGT": ""},
                     {"SoLoai": act["MaTaiSan"].nunique()})


def group_by_status(act: pd.DataFrame) -> pd.DataFrame:
    """Bảng 2 – Ma trận Nhóm thiết bị × Tình trạng (số thiết bị)."""
    if act.empty:
        return pd.DataFrame()
    t = pd.crosstab(_blank(act["NhomThietBi"]), _blank(act["TinhTrang"], "(trống)"),
                    margins=True, margins_name=TOTAL)
    order = [s for s in schema.TINH_TRANG if s in t.columns] + \
        [c for c in t.columns if c not in schema.TINH_TRANG and c != TOTAL] + [TOTAL]
    return t[order].rename_axis(index="Nhóm thiết bị", columns=None).reset_index()


def by_room(act: pd.DataFrame, labels: dict, managers: dict, rooms: list[str]) -> pd.DataFrame:
    """Bảng 3 – Theo nơi sử dụng."""
    if not rooms:
        return pd.DataFrame()
    need = thietbi.needs_attention(act)
    g = act.assign(_need=need).groupby("NoiSuDung").agg(
        SoTB=("id", "size"), SoLoai=("MaTaiSan", "nunique"), CanXuLy=("_need", "sum"), GiaTri=("GiaTri", "sum"))
    g = g.reindex(rooms).fillna(0)
    df = pd.DataFrame({
        "Phong": [labels.get(r, r) for r in g.index], "QuanLy": [managers.get(r, "") for r in g.index],
        "SoTB": g["SoTB"].astype(int).values, "SoLoai": g["SoLoai"].astype(int).values,
        "CanXuLy": g["CanXuLy"].astype(int).values, "GiaTri": g["GiaTri"].values,
    })
    df = df.sort_values("GiaTri", ascending=False)
    df["TyLeGT"] = _pct(df["GiaTri"], df["GiaTri"].sum())
    return add_total(df, "Phong", ["SoTB", "CanXuLy", "GiaTri"], {"TyLeGT": ""},
                     {"SoLoai": act[act["NoiSuDung"].isin(rooms)]["MaTaiSan"].nunique()})


def by_asset_type(act: pd.DataFrame, catalog: pd.DataFrame) -> pd.DataFrame:
    """Bảng 4 – Theo loại tài sản (Mã tài sản)."""
    if act.empty:
        return pd.DataFrame()
    df = act.assign(Ten=_name(act))
    cat_names = catalog.set_index("MaPhanLoai")["TenThietBi"].to_dict() if not catalog.empty else {}
    g = df.groupby("MaTaiSan").agg(
        Ten=("Ten", lambda s: s.mode().iloc[0] if not s.mode().empty else ""),
        Nhom=("NhomThietBi", lambda s: s.mode().iloc[0] if not s.mode().empty else ""),
        SoTB=("id", "size"), SoPhong=("NoiSuDung", "nunique"), GiaTri=("GiaTri", "sum"),
        GiaTB=("GiaTri", "mean"),
    ).reset_index()
    g["Ten"] = [cat_names.get(m) or t for m, t in zip(g["MaTaiSan"], g["Ten"])]
    g["GiaTB"] = g["GiaTB"].round(0)
    g = g.sort_values(["SoTB", "GiaTri"], ascending=False)
    return add_total(g, "MaTaiSan", ["SoTB", "GiaTri"],
                     extra={"SoPhong": df["NoiSuDung"].nunique(), "GiaTB": round(df["GiaTri"].mean(), 0)})


AGE_BINS = [(-1, 1, "Dưới 1 năm"), (1, 3, "1 – 3 năm"), (3, 5, "3 – 5 năm"), (5, 10, "5 – 10 năm"),
            (10, 200, "Trên 10 năm")]


def _years(act: pd.DataFrame) -> pd.Series:
    return pd.to_datetime(act["NgayMua"], errors="coerce").dt.year


def by_age(act: pd.DataFrame, today: date | None = None) -> pd.DataFrame:
    """Bảng 5 – Theo tuổi thiết bị (tính từ ngày mua)."""
    today = today or date.today()
    age = today.year - _years(act)
    label = pd.Series("(chưa có ngày mua)", index=act.index)
    for lo, hi, name in AGE_BINS:
        label[(age > lo) & (age <= hi)] = name
    label[age <= 0] = AGE_BINS[0][2]
    df = act.assign(Tuoi=label)
    order = [b[2] for b in AGE_BINS] + ["(chưa có ngày mua)"]
    g = df.groupby("Tuoi").agg(SoTB=("id", "size"), GiaTri=("GiaTri", "sum")).reindex(order).dropna(how="all")
    g = g.fillna(0).reset_index()
    g["SoTB"] = g["SoTB"].astype(int)
    g["CanXuLy"] = [int(thietbi.needs_attention(df[df["Tuoi"] == t]).sum()) for t in g["Tuoi"]]
    g["TyLeSL"] = _pct(g["SoTB"], g["SoTB"].sum())
    g = g[["Tuoi", "SoTB", "TyLeSL", "GiaTri", "CanXuLy"]]
    return add_total(g, "Tuoi", ["SoTB", "GiaTri", "CanXuLy"], {"TyLeSL": ""})


def by_year(act: pd.DataFrame) -> pd.DataFrame:
    """Bảng 6 – Mua sắm theo năm."""
    df = act.assign(Nam=_years(act))
    df = df[df["Nam"].notna()]
    if df.empty:
        return pd.DataFrame()
    g = df.groupby("Nam").agg(SoTB=("id", "size"), SoLoai=("MaTaiSan", "nunique"),
                              GiaTri=("GiaTri", "sum")).reset_index().sort_values("Nam", ascending=False)
    g["Nam"] = g["Nam"].astype(int).astype(str)
    return add_total(g, "Nam", ["SoTB", "GiaTri"], extra={"SoLoai": df["MaTaiSan"].nunique()})


VALUE_BINS = [(0, 1, "Chưa có giá trị"), (1, 5e6, "Dưới 5 triệu"), (5e6, 10e6, "5 – dưới 10 triệu"),
              (10e6, 30e6, "10 – dưới 30 triệu"), (30e6, float("inf"), "Từ 30 triệu trở lên")]


def by_value_band(act: pd.DataFrame) -> pd.DataFrame:
    """Bảng 7 – Theo mức giá trị (phân biệt tài sản ≥ 30 triệu / công cụ dụng cụ)."""
    rows = []
    for lo, hi, name in VALUE_BINS:
        items = act[(act["GiaTri"] >= lo) & (act["GiaTri"] < hi)]
        rows.append({"MucGia": name, "SoTB": len(items), "GiaTri": items["GiaTri"].sum()})
    df = pd.DataFrame(rows)
    df["TyLeSL"] = _pct(df["SoTB"], df["SoTB"].sum())
    df["TyLeGT"] = _pct(df["GiaTri"], df["GiaTri"].sum())
    df = df[["MucGia", "SoTB", "TyLeSL", "GiaTri", "TyLeGT"]]
    return add_total(df, "MucGia", ["SoTB", "GiaTri"], {"TyLeSL": "", "TyLeGT": ""})


def by_manager(act: pd.DataFrame, managers: dict, people: dict) -> pd.DataFrame:
    """Bảng 8 – Theo người quản lý phòng."""
    mgr = {room: email for room, email in managers.items() if email}
    if not mgr:
        return pd.DataFrame()
    per_room = act.assign(_need=thietbi.needs_attention(act)).groupby("NoiSuDung").agg(
        SoTB=("id", "size"), CanXuLy=("_need", "sum"), GiaTri=("GiaTri", "sum"))
    rooms = pd.DataFrame({"Email": list(mgr.values())}, index=list(mgr.keys()))
    rooms = rooms.join(per_room).fillna(0)
    df = rooms.groupby("Email").agg(SoPhong=("Email", "size"), SoTB=("SoTB", "sum"), CanXuLy=("CanXuLy", "sum"),
                                    GiaTri=("GiaTri", "sum")).reset_index()
    df.insert(1, "HoTen", df["Email"].map(lambda e: people.get(e, "")))
    df[["SoTB", "CanXuLy"]] = df[["SoTB", "CanXuLy"]].astype(int)
    df = df.sort_values("SoTB", ascending=False)
    return add_total(df, "Email", ["SoPhong", "SoTB", "CanXuLy", "GiaTri"])


def transfers_by_month(dc: pd.DataFrame) -> pd.DataFrame:
    """Bảng 9 – Điều chuyển theo tháng."""
    d = pd.to_datetime(dc["NgayDieuChuyen"], errors="coerce")
    df = dc.assign(Thang=d.dt.strftime("%m/%Y"), _k=d.dt.to_period("M"))
    df = df[df["_k"].notna()]
    if df.empty:
        return pd.DataFrame()
    g = df.groupby(["_k", "Thang"]).agg(SoLan=("id", "size"), SoTB=("Title", "nunique"),
                                        TuPhong=("TuPhong", "nunique"), DenPhong=("DenPhong", "nunique"))
    g = g.reset_index().sort_values("_k", ascending=False).drop(columns="_k")
    return add_total(g, "Thang", ["SoLan"], extra={"SoTB": df["Title"].nunique(), "TuPhong": df["TuPhong"].nunique(),
                                                   "DenPhong": df["DenPhong"].nunique()})


def inventory_by_room(kk: pd.DataFrame, dot: str, labels: dict) -> pd.DataFrame:
    """Bảng 10 – Kết quả kiểm kê theo phòng (một đợt)."""
    cur = kk[kk["DotKiemKe"] == dot]
    if cur.empty:
        return pd.DataFrame()
    rows = []
    for room, g in cur.groupby("NoiSuDung"):
        diff = g["SoLuongKiemKe"] - g["SoLuong"]
        state = "Đã xác nhận" if (g["TrangThaiXacNhan"] == schema.DA_XAC_NHAN).all() else \
            "Không đồng ý" if (g["TrangThaiXacNhan"] == schema.KHONG_DONG_Y).any() else \
            "Đã kiểm kê" if (g["TrangThaiKiemKe"] == schema.DA_KIEM_KE).all() else "Đang kiểm kê"
        rows.append({"Phong": labels.get(room, room), "SoDong": len(g), "SoSach": g["SoLuong"].sum(),
                     "ThucTe": g["SoLuongKiemKe"].sum(), "Thieu": -diff[diff < 0].sum(),
                     "Thua": diff[diff > 0].sum(), "TrangThai": state})
    df = pd.DataFrame(rows).sort_values("Thieu", ascending=False)
    return add_total(df, "Phong", ["SoDong", "SoSach", "ThucTe", "Thieu", "Thua"])


def disposals_by_round(tl: pd.DataFrame) -> pd.DataFrame:
    """Bảng 11 – Thanh lý theo đợt."""
    if tl.empty:
        return pd.DataFrame()
    g = tl.groupby("DotThanhLy").agg(Ngay=("NgayThanhLy", "max"), SoTT=("SoToTrinh", "first"),
                                     SoTS=("id", "size"), SoLuong=("SoLuong", "sum"), GiaMua=("GiaMua", "sum"),
                                     ConLai=("GiaTriConLai", "sum")).reset_index().sort_values("Ngay", ascending=False)
    return add_total(g, "DotThanhLy", ["SoTS", "SoLuong", "GiaMua", "ConLai"])


def data_quality(act: pd.DataFrame) -> pd.DataFrame:
    """Bảng 12 – Chất lượng dữ liệu (các ô còn thiếu cần bổ sung)."""
    n = len(act)
    checks = [
        ("Chưa có Mã SAP", act["MaSAP"].str.strip() == ""),
        ("Chưa có ngày mua", _years(act).isna()),
        ("Chưa có giá trị", act["GiaTri"] <= 0),
        ("Chưa có người sử dụng", act["NguoiSuDung"].str.strip() == ""),
        ("Chưa có người quản lý phòng", act["QuanLyPhong"].str.strip() == ""),
        ("Chưa có nhóm thiết bị", act["NhomThietBi"].str.strip() == ""),
        ("Chưa có nơi sử dụng", act["NoiSuDung"].str.strip() == ""),
        ("Mã chi tiết bị trùng", act["MaChiTiet"].ne("") & act["MaChiTiet"].duplicated(keep=False)),
    ]
    return pd.DataFrame([{"KiemTra": name, "SoTB": int(mask.sum()), "TyLe": round(mask.sum() / n * 100, 1) if n else 0}
                         for name, mask in checks])
