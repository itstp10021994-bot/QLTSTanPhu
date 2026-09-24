"""Nghiệp vụ thiết bị trên list Data_Thietbichitiet (mỗi dòng = một thiết bị)."""

from __future__ import annotations

import re

import pandas as pd

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
    fields = dict(fields)
    ma = str(fields.get("MaTaiSan") or "").strip()
    code = str(fields.get("MaChiTiet") or "").strip()
    if not code:
        if not ma:
            return "thiếu Mã tài sản"
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
