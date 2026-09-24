"""Nghiệp vụ thiết bị trên list Data_Thietbichitiet (mỗi dòng = một thiết bị)."""

from __future__ import annotations

import re

import pandas as pd
import streamlit as st

from . import schema, storage

DETAIL_WIDTH = 5  # 111028-00001


def next_detail_codes(df: pd.DataFrame, ma_tai_san: str, count: int = 1) -> list[str]:
    """Mã chi tiết tiếp theo của một mã tài sản: số thứ tự lớn nhất hiện có + 1."""
    ma = ma_tai_san.strip()
    pattern = re.compile(rf"^{re.escape(ma)}-(\d+)$")
    numbers = [int(m.group(1)) for code in df["MaChiTiet"] if (m := pattern.match(str(code).strip()))]
    start = max(numbers, default=0) + 1
    width = max([DETAIL_WIDTH, *(len(str(c).split("-")[-1]) for c in df["MaChiTiet"] if pattern.match(str(c).strip()))])
    return [f"{ma}-{n:0{width}d}" for n in range(start, start + count)]


def is_disposed(df: pd.DataFrame) -> pd.Series:
    """Thiết bị đã thanh lý (không còn tính vào tài sản đang sử dụng)."""
    return df["TinhTrang"].isin(schema.TINH_TRANG_DA_THANH_LY) | (df["NoiSuDung"] == schema.NOI_THANH_LY)


def needs_attention(df: pd.DataFrame) -> pd.Series:
    return ~df["TinhTrang"].isin(schema.TINH_TRANG_TOT | {""}) & ~is_disposed(df)


def status_options(df: pd.DataFrame, current: str = "") -> list[str]:
    """Danh sách tình trạng gợi ý + các giá trị đang có trong dữ liệu."""
    extra = sorted(set(df["TinhTrang"]) - set(schema.TINH_TRANG) - {""})
    opts = [*schema.TINH_TRANG, *extra]
    if current and current not in opts:
        opts.append(current)
    return opts


def distinct(df: pd.DataFrame, col: str, defaults: list[str] | None = None) -> list[str]:
    values = [v for v in df[col].unique() if v]
    return list(dict.fromkeys([*(defaults or []), *sorted(values)]))


def all_rooms() -> list[str]:
    """Phòng = danh mục phòng + mọi "Nơi sử dụng" đang có trên thiết bị."""
    phong = storage.load(schema.PHONG)
    tb = storage.load(schema.THIET_BI)
    rooms = set(phong["Title"]) | set(tb["NoiSuDung"])
    return sorted(rooms - {"", schema.NOI_THANH_LY})


def room_managers() -> dict[str, str]:
    """Phòng -> email người quản lý (danh mục phòng ưu tiên, sau đó cột "Quản lý phòng")."""
    tb = storage.load(schema.THIET_BI)
    managers: dict[str, str] = {}
    for room, grp in tb[tb["QuanLyPhong"] != ""].groupby("NoiSuDung"):
        managers[room] = grp["QuanLyPhong"].mode().iloc[0].strip().lower()
    phong = storage.load(schema.PHONG)
    for r in phong.itertuples():
        if r.NguoiQuanLy:
            managers[r.Title] = r.NguoiQuanLy.strip().lower()
    return managers


def rooms_managed_by(email: str) -> list[str]:
    email = email.strip().lower()
    tb = storage.load(schema.THIET_BI)
    from_items = set(tb[tb["QuanLyPhong"].str.strip().str.lower() == email]["NoiSuDung"])
    from_list = {r for r, m in room_managers().items() if m == email}
    return sorted((from_items | from_list) - {"", schema.NOI_THANH_LY})


def prepare_new(fields: dict, existing_codes: list[str], used_codes: dict, stt: list, managers: dict,
                user_name: str) -> dict | str:
    """Chuẩn bị một thiết bị mới: sinh Mã chi tiết, STT, Quản lý phòng, Quản lý thiết bị.

    ``used_codes`` / ``stt`` được cập nhật tại chỗ để nhiều dòng mới liên tiếp không trùng mã.
    Trả về chuỗi lỗi nếu thiếu dữ liệu.
    """
    fields = catalog_fill(fields, load_catalog())
    ma = str(fields.get("MaTaiSan") or "").strip()
    code = str(fields.get("MaChiTiet") or "").strip()
    if not code:
        if not ma:
            return "thiếu Mã tài sản (hoặc Tên thiết bị không có trong danh mục loại thiết bị)"
        fresh = used_codes.setdefault(ma, [])
        code = next_detail_codes(pd.DataFrame({"MaChiTiet": [*existing_codes, *fresh]}), ma)[0]
        fresh.append(code)
    elif not ma and "-" in code:
        ma = code.rsplit("-", 1)[0]
    fields["MaTaiSan"], fields["MaChiTiet"] = ma, code
    if not fields.get("STT"):
        stt[0] += 1
        fields["STT"] = stt[0]
    room = str(fields.get("NoiSuDung") or "").strip()
    if room and not fields.get("QuanLyPhong"):
        fields["QuanLyPhong"] = managers.get(room, "")
    fields.setdefault("QuanLyThietBi", user_name)
    return fields


# ---------------------------------------------------------------------------
# Danh mục loại thiết bị (Data_Loaithietbi): tên -> mã tài sản, nhóm
# ---------------------------------------------------------------------------
def load_catalog() -> pd.DataFrame:
    """Danh mục loại thiết bị; rỗng nếu list chưa có trên SharePoint (app vẫn chạy bình thường)."""
    try:
        cat = storage.load(schema.LOAI_TB)
    except storage.TokenExpired:
        raise
    except storage.StorageError:
        return storage.empty_frame(schema.LOAI_TB)
    cat = cat[(cat["MaPhanLoai"].str.strip() != "")].copy()
    cat["MaPhanLoai"] = cat["MaPhanLoai"].str.strip()
    return cat.drop_duplicates("MaPhanLoai").sort_values("TenThietBi", key=lambda s: s.str.lower())


def catalog_fill(fields: dict, catalog: pd.DataFrame) -> dict:
    """Điền Mã tài sản / Tên / Nhóm thiết bị còn trống dựa vào danh mục loại thiết bị."""
    if catalog is None or catalog.empty:
        return fields
    fields = dict(fields)
    ma = str(fields.get("MaTaiSan") or "").strip()
    ten = str(fields.get("TenThietBi") or "").strip()
    row = None
    if ma:
        hit = catalog[catalog["MaPhanLoai"] == ma]
        row = hit.iloc[0] if not hit.empty else None
    elif ten:
        hit = catalog[catalog["TenThietBi"].str.strip().str.lower() == ten.lower()]
        if len(hit) == 1:  # chỉ tự điền khi tên khớp đúng một loại
            row = hit.iloc[0]
            fields["MaTaiSan"] = row["MaPhanLoai"]
    if row is not None:
        if not ten:
            fields["TenThietBi"] = row["TenThietBi"]
        if not str(fields.get("NhomThietBi") or "").strip():
            fields["NhomThietBi"] = row["NhomThietBi"]
    return fields


# ---------------------------------------------------------------------------
# Người dùng trong trường
# ---------------------------------------------------------------------------
@st.cache_data(ttl=600, show_spinner=False)
def _site_users(scope: str) -> list[dict]:  # noqa: ARG001 - khóa cache theo cấu hình
    store = storage.get_store()
    if not hasattr(store, "site_users"):
        return []
    try:
        return store.site_users()
    except storage.StorageError:
        return []


def user_directory() -> dict[str, str]:
    """email -> họ tên: người dùng site SharePoint + Phân quyền + quản lý phòng + người sử dụng thiết bị."""
    users: dict[str, str] = {}

    def add(email, name=""):
        email = str(email or "").strip().lower()
        if "@" in email and " " not in email:
            if name and not users.get(email):
                users[email] = str(name).strip()
            else:
                users.setdefault(email, "")

    for u in _site_users(storage._cache_scope()):
        add(u["email"], u["name"])
    for r in storage.load(schema.PHAN_QUYEN).itertuples():
        add(r.Title, r.HoTen)
    for r in storage.load(schema.PHONG).itertuples():
        add(r.NguoiQuanLy, r.TenNguoiQuanLy)
    tb = storage.load(schema.THIET_BI)
    for col in ("NguoiSuDung", "QuanLyPhong"):
        for email in tb[col].unique():
            add(email)
    return dict(sorted(users.items(), key=lambda kv: (kv[1] or kv[0]).lower()))


def suggest_user(room: str) -> str:
    """Gợi ý người sử dụng cho một phòng: người dùng phổ biến nhất trong phòng, nếu không có thì người quản lý phòng."""
    tb = storage.load(schema.THIET_BI)
    used = tb[(tb["NoiSuDung"] == room) & tb["NguoiSuDung"].str.contains("@", regex=False)]["NguoiSuDung"]
    if not used.empty:
        return used.str.strip().str.lower().mode().iloc[0]
    return room_managers().get(room, "")
