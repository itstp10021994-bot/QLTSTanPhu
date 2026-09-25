"""Trợ lý tra cứu KHÔNG dùng AI: nhận diện từ khóa trong câu hỏi tiếng Việt rồi lọc dữ liệu đã tải từ SharePoint.

Không gửi dữ liệu ra ngoài. Câu trả lời là danh sách "phần" để trang hiển thị:
``("md", text)``, ``("metrics", [(nhãn, giá trị), ...])``, ``("table", DataFrame)``.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

import pandas as pd

from . import schema, thietbi

CODE_RE = re.compile(r"\b\d{6}-\d{2,6}\b")
ASSET_RE = re.compile(r"(?<![\d-])\d{6}(?![\d-])")
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
MONTH_RE = re.compile(r"\bthang (\d{1,2})(?:\s*[/ -]\s*(\d{4}))?\b")
DOT_RE = re.compile(r"\bdot (\d+)\b")
ROOM_NUM_RE = re.compile(r"\bphong (?:hoc |so )?([a-z]*\d+[a-z]?)\b")

STOP = set("""
phong o tai cua co la gi nhung cac cai chiec bao nhieu may tong so luong danh sach xem cho toi minh hay
tim kiem tra cuu thiet bi tai san nao dau xin chao cam on ban oi trong va hoac voi theo con dang hien nay the nao sao nhu gi a
di den tu duoc bi voi nhe giup ai quan ly su dung nguoi gia tri dem liet ke hien thi thong tin chi tiet
""".split())

EXAMPLES = [
    "máy chiếu phòng L1_PH103",
    "111028-00012",
    "phòng chưa kiểm kê đợt 1",
    "tổng giá trị nhóm CNTT",
    "thiết bị cần sửa chữa theo phòng",
    "ai quản lý phòng L1_PH104",
    "điều chuyển tháng 9",
    "các đợt thanh lý",
]


def norm(text: str) -> str:
    """Chữ thường, bỏ dấu, chỉ giữ chữ/số (dấu _ - . @ / thành khoảng trắng trừ trong email/mã)."""
    text = unicodedata.normalize("NFD", str(text or "")).replace("đ", "d").replace("Đ", "D")
    text = "".join(c for c in text if unicodedata.category(c) != "Mn").lower()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9@.\-]+", " ", text)).strip()


def _flat(text: str) -> str:
    """Dạng dùng để so khớp cụm từ: bỏ luôn . - (giữ số và chữ)."""
    return re.sub(r"\s+", " ", re.sub(r"[.\-]", " ", norm(text))).strip()


def _has(q: str, phrase: str) -> bool:
    return bool(phrase) and f" {phrase} " in f" {q} "


@dataclass
class Context:
    tb: pd.DataFrame
    phong: pd.DataFrame
    kk: pd.DataFrame
    dc: pd.DataFrame
    tl: pd.DataFrame
    catalog: pd.DataFrame
    users: dict  # email -> họ tên
    managers: dict  # phòng -> email
    labels: dict  # phòng -> nhãn hiển thị
    allowed_rooms: set | None = None  # None = xem tất cả


@dataclass
class Parsed:
    codes: list = field(default_factory=list)
    assets: list = field(default_factory=list)
    rooms: list = field(default_factory=list)
    groups: list = field(default_factory=list)
    types: list = field(default_factory=list)
    states: list = field(default_factory=list)
    attention: bool = False
    people: list = field(default_factory=list)
    words: list = field(default_factory=list)
    dot: str = ""
    month: tuple | None = None
    intent: str = "devices"
    by: str = ""
    understood: list = field(default_factory=list)


# ---------------------------------------------------------------------------
# Phân tích câu hỏi
# ---------------------------------------------------------------------------
def parse(query: str, ctx: Context) -> Parsed:
    p = Parsed()
    raw = str(query or "")
    q = _flat(raw)

    p.codes = sorted({m.upper() for m in CODE_RE.findall(raw)})
    rest = CODE_RE.sub(" ", raw)
    p.assets = sorted(set(ASSET_RE.findall(rest)))
    p.people = [e.lower() for e in EMAIL_RE.findall(raw)]

    # --- ý định ---
    if any(_has(q, w) for w in ("huong dan", "giup", "help", "vi du")) or q in ("?", ""):
        p.intent = "help"
    elif _has(q, "ai quan ly") or _has(q, "nguoi quan ly phong") or _has(q, "quan ly phong nao"):
        p.intent = "manager"
    elif _has(q, "kiem ke"):
        p.intent = "inventory"
    elif _has(q, "dieu chuyen") or _has(q, "chuyen phong"):
        p.intent = "transfer"
    elif _has(q, "thanh ly") and not _has(q, "can thanh ly") and not _has(q, "da thanh ly"):
        p.intent = "disposal"
    elif _has(q, "danh sach phong") or _has(q, "cac phong") or q in ("phong", "tat ca phong"):
        p.intent = "rooms"
    for key, name in (("phong", "room"), ("nhom", "group"), ("tinh trang", "state"), ("loai", "type"),
                      ("nguoi su dung", "user"), ("nam mua", "year")):
        if _has(q, f"theo {key}"):
            p.by = name

    m = DOT_RE.search(q)
    dots = [d for d in dict.fromkeys(ctx.kk["DotKiemKe"]) if d] if not ctx.kk.empty else []
    if m:
        cand = [d for d in dots if _has(_flat(d), f"dot {m.group(1)}")]
        years = re.findall(r"\b20\d\d\b", q)
        if years:
            cand = [d for d in cand if all(y in d for y in years)] or cand
        p.dot = sorted(cand)[-1] if cand else ""
    mm = MONTH_RE.search(q)
    if mm:
        p.month = (int(mm.group(1)), int(mm.group(2)) if mm.group(2) else None)

    work = f" {q} "

    def take(phrase: str) -> bool:
        nonlocal work
        if _has(work.strip(), phrase):
            work = work.replace(f" {phrase} ", " ")
            return True
        return False

    # --- phòng: mã phòng, tên phòng, "phòng 103" ---
    room_list = list(ctx.labels)
    for r in sorted(room_list, key=lambda r: -len(r)):
        if take(_flat(r)):
            p.rooms.append(r)
    if not p.rooms:
        names = ctx.phong.set_index("Title")["TenPhong"].to_dict() if not ctx.phong.empty else {}
        for r, name in sorted(names.items(), key=lambda kv: -len(str(kv[1]))):
            if len(_flat(name)) >= 6 and take(_flat(name)):
                p.rooms.append(r)
    if not p.rooms:
        rm = ROOM_NUM_RE.search(work)
        if rm:
            val = rm.group(1)
            cand = [r for r in room_list if any(t.endswith(val) for t in _flat(r).split())]
            if 0 < len(cand) <= 8:
                p.rooms = cand
                work = work.replace(f" {val} ", " ")

    # --- nhóm thiết bị (kèm viết tắt: cntt...) ---
    for g in sorted(set(ctx.tb["NhomThietBi"]) - {""}, key=lambda s: -len(s)):
        full = _flat(g)
        short = re.sub(r"^nhom ", "", full)
        words = short.split()
        abbr = "".join(w[0] for w in words) if len(words) >= 3 else ""
        if take(full) or take(short) or (abbr and take(abbr)):
            p.groups.append(g)

    # --- loại thiết bị (tên) ---
    names = set(ctx.tb["TenThietBi"]) | (set(ctx.catalog["TenThietBi"]) if not ctx.catalog.empty else set())
    for n in sorted({x for x in names if len(_flat(x)) >= 3}, key=lambda s: -len(_flat(s))):
        if take(_flat(n)):
            p.types.append(n)

    # --- tình trạng ---
    if take("can xu ly") or take("hu hong") or take("bi hong") or take("hong") or take("hu"):
        p.attention = True
    for s in sorted(set(schema.TINH_TRANG) | (set(ctx.tb["TinhTrang"]) - {""}), key=lambda s: -len(s)):
        if take(_flat(s)):
            p.states.append(s)

    # --- người (họ tên trong danh sách user) ---
    for email, name in ctx.users.items():
        if name and len(_flat(name)) >= 6 and take(_flat(name)):
            p.people.append(email)
    for e in p.people:
        work = work.replace(f" {_flat(e)} ", " ")

    # --- từ còn lại: tìm trong đặc điểm / tên / serial / mã SAP ---
    for x in [*(_flat(c) for c in p.codes), *p.assets, "dot", "thang", *re.findall(r"\b20\d\d\b", work)]:
        work = work.replace(f" {x} ", " ")
    if p.dot:
        work = re.sub(r"\bdot \d+\b", " ", work)
    for kw in ("kiem ke", "dieu chuyen", "thanh ly", "gia tri", "so luong", "bao nhieu", "chua", "da", "xac nhan",
               "thieu", "thua", "chenh lech", "theo", "nam", "loai", "nhom", "tinh trang", "moi nhat", "gan day"):
        work = work.replace(f" {kw} ", " ")
    p.words = [w for w in work.split() if len(w) >= 3 and w not in STOP and not w.isdigit()]

    if p.rooms:
        p.understood.append("phòng " + ", ".join(ctx.labels.get(r, r) for r in p.rooms))
    if p.groups:
        p.understood.append(", ".join(p.groups))
    if p.types:
        p.understood.append("loại " + ", ".join(p.types))
    if p.assets:
        p.understood.append("mã tài sản " + ", ".join(p.assets))
    if p.attention:
        p.understood.append("thiết bị cần xử lý (hư hỏng / cần sửa / cần thanh lý)")
    if p.states:
        p.understood.append("tình trạng " + ", ".join(p.states))
    if p.people:
        p.understood.append("người " + ", ".join(ctx.users.get(e) or e for e in p.people))
    if p.words:
        p.understood.append("có chữ " + ", ".join(f"“{w}”" for w in p.words))
    if p.dot:
        p.understood.append(p.dot)
    if p.month:
        p.understood.append(f"tháng {p.month[0]}" + (f"/{p.month[1]}" if p.month[1] else ""))
    return p


# ---------------------------------------------------------------------------
# Trả lời
# ---------------------------------------------------------------------------
LABELS = schema.labels_of(schema.THIET_BI)
TB_COLS = ["MaChiTiet", "TenThietBi", "DacDiem", "NoiSuDung", "NguoiSuDung", "TinhTrang", "GiaTri", "NgayMua"]


def money(v: float) -> str:
    return f"{v:,.0f} đ".replace(",", ".")


def num(v: float) -> str:
    return f"{v:,.0f}".replace(",", ".")


def _scope(ctx: Context, df: pd.DataFrame, col: str = "NoiSuDung") -> pd.DataFrame:
    return df if ctx.allowed_rooms is None else df[df[col].isin(ctx.allowed_rooms)]


def _filter_devices(ctx: Context, p: Parsed) -> pd.DataFrame:
    tb = _scope(ctx, ctx.tb)
    tb = tb if p.states and any(s in schema.TINH_TRANG_DA_THANH_LY for s in p.states) else thietbi.active(tb)
    if p.rooms:
        tb = tb[tb["NoiSuDung"].isin(p.rooms)]
    if p.groups:
        tb = tb[tb["NhomThietBi"].isin(p.groups)]
    if p.types:
        names = {_flat(t) for t in p.types}
        tb = tb[tb["TenThietBi"].map(_flat).isin(names) | tb["ChiTiet"].map(_flat).isin(names)]
    if p.assets:
        tb = tb[tb["MaTaiSan"].isin(p.assets)]
    if p.attention:
        tb = tb[thietbi.needs_attention(tb)]
    if p.states:
        tb = tb[tb["TinhTrang"].isin(p.states)]
    if p.people:
        tb = tb[tb["NguoiSuDung"].str.lower().isin(p.people) | tb["QuanLyPhong"].str.lower().isin(p.people)]
    for w in p.words:
        hay = (tb["DacDiem"] + " " + tb["TenThietBi"] + " " + tb["ChiTiet"] + " " + tb["TenPhongBan"] + " "
               + tb["MaSAP"] + " " + tb["NhomThietBi"]).map(_flat)
        tb = tb[hay.str.contains(rf"\b{re.escape(w)}", regex=True)]
    return tb


def _device_table(tb: pd.DataFrame, limit: int = 300) -> pd.DataFrame:
    return tb[TB_COLS].head(limit).rename(columns=LABELS)


def _breakdown(tb: pd.DataFrame, by: str, ctx: Context) -> pd.DataFrame:
    col = {"room": "NoiSuDung", "group": "NhomThietBi", "state": "TinhTrang", "type": "TenThietBi",
           "user": "NguoiSuDung"}.get(by)
    if by == "year":
        key = pd.to_datetime(tb["NgayMua"], errors="coerce").dt.year.fillna(0).astype(int).astype(str) \
            .replace("0", "(chưa có)")
        title = "Năm mua"
    else:
        key = tb[col].replace("", "(trống)")
        if by == "room":
            key = key.map(lambda r: ctx.labels.get(r, r))
        title = {"room": "Nơi sử dụng", "group": "Nhóm", "state": "Tình trạng", "type": "Loại thiết bị",
                 "user": "Người sử dụng"}[by]
    g = tb.assign(_k=key).groupby("_k").agg(SoTB=("id", "size"), GiaTri=("GiaTri", "sum")).reset_index()
    return g.sort_values("SoTB", ascending=False).rename(columns={"_k": title, "SoTB": "Số thiết bị",
                                                                  "GiaTri": "Giá trị (VNĐ)"})


def answer(query: str, ctx: Context) -> list:
    p = parse(query, ctx)
    if p.intent == "help":
        return help_parts()
    if p.codes:
        return _answer_code(ctx, p)
    handler = {"manager": _answer_manager, "inventory": _answer_inventory, "transfer": _answer_transfer,
               "disposal": _answer_disposal, "rooms": _answer_rooms}.get(p.intent)
    if handler:
        return handler(ctx, p)
    if not (p.rooms or p.groups or p.types or p.assets or p.attention or p.states or p.people or p.words or p.by):
        return [("md", "Mình chưa hiểu câu hỏi này. Hãy thử nêu **mã thiết bị**, **tên phòng**, **loại thiết bị**, "
                       "**nhóm**, **tình trạng**, hoặc các từ *kiểm kê / điều chuyển / thanh lý*."), *help_parts()]
    return _answer_devices(ctx, p, query)


def help_parts() -> list:
    return [("md", "**Có thể hỏi, ví dụ:**\n\n" + "\n".join(f"- {e}" for e in EXAMPLES) +
             "\n\nThêm *“theo phòng / theo nhóm / theo tình trạng / theo loại / theo năm mua”* để xem bảng tổng hợp.")]


def _understood(p: Parsed) -> tuple:
    return ("md", "🔎 Đã hiểu: " + (" · ".join(p.understood) if p.understood else "tất cả thiết bị"))


def _answer_devices(ctx: Context, p: Parsed, query: str) -> list:
    tb = _filter_devices(ctx, p)
    parts = [_understood(p)]
    if tb.empty:
        only_words = p.words and not (p.rooms or p.groups or p.types or p.assets or p.attention or p.states
                                      or p.people)
        if only_words:
            return [("md", "Mình chưa hiểu câu hỏi này và cũng không thấy thiết bị nào có các chữ đó."),
                    *help_parts()]
        parts.append(("md", "Không tìm thấy thiết bị nào khớp."))
        return parts
    parts.append(("metrics", [("Số thiết bị", num(len(tb))), ("Tổng giá trị", money(tb["GiaTri"].sum())),
                              ("Số phòng", num(tb["NoiSuDung"].nunique())),
                              ("Cần xử lý", num(int(thietbi.needs_attention(tb).sum())))]))
    by = p.by
    if not by and tb["NoiSuDung"].nunique() > 1 and len(tb) > 5:
        by = "room"
    if by:
        parts.append(("md", "**Tổng hợp**"))
        parts.append(("table", _breakdown(tb, by, ctx)))
    parts.append(("md", "**Danh sách thiết bị**" + (" (300 dòng đầu)" if len(tb) > 300 else "")))
    parts.append(("table", _device_table(tb)))
    return parts


def _answer_code(ctx: Context, p: Parsed) -> list:
    tb = _scope(ctx, ctx.tb)
    parts = []
    for code in p.codes:
        row = tb[tb["MaChiTiet"].str.upper() == code]
        if row.empty:
            parts.append(("md", f"Không tìm thấy thiết bị **{code}**" +
                          (" (hoặc không thuộc phòng bạn quản lý)." if ctx.allowed_rooms is not None else ".")))
            continue
        r = row.iloc[0]
        info = [(LABELS[c], r[c]) for c in ["MaTaiSan", "MaChiTiet", "TenThietBi", "ChiTiet", "DacDiem", "NhomThietBi",
                                            "TenPhongBan", "MaSAP", "DVT", "SL", "GiaTri", "NgayMua", "TinhTrang",
                                            "NoiSuDung", "NguoiSuDung", "QuanLyPhong", "ThoiHanBaoHanh", "GhiChu"]]
        info = [(k, ctx.labels.get(v, v) if k == LABELS["NoiSuDung"] else (money(v) if k == LABELS["GiaTri"] else v))
                for k, v in info if str(v).strip() not in ("", "0", "0.0")]
        parts.append(("md", f"### {r['MaChiTiet']} – {r['TenThietBi'] or r['ChiTiet']}"))
        if thietbi.is_disposed(row).iloc[0]:
            parts.append(("md", "⚠️ Thiết bị này **đã thanh lý**."))
        parts.append(("table", pd.DataFrame([(k, str(v)) for k, v in info], columns=["Thông tin", "Chi tiết"])))
        hist = ctx.dc[ctx.dc["Title"].str.upper() == code] if not ctx.dc.empty else ctx.dc
        if not hist.empty:
            parts.append(("md", "**Lịch sử điều chuyển**"))
            parts.append(("table", hist.sort_values("NgayDieuChuyen", ascending=False)[
                ["NgayDieuChuyen", "TuPhong", "DenPhong", "NguoiThucHien", "LyDo"]].rename(
                columns=schema.labels_of(schema.DIEU_CHUYEN))))
        tl = ctx.tl[ctx.tl["Title"].str.upper() == code] if not ctx.tl.empty else ctx.tl
        if not tl.empty:
            t = tl.iloc[0]
            parts.append(("md", f"**Thanh lý:** {t['DotThanhLy']} · tờ trình {t['SoToTrinh']} · ngày {t['NgayThanhLy']}"))
    return parts


def _answer_manager(ctx: Context, p: Parsed) -> list:
    rooms = p.rooms or sorted(_scope(ctx, pd.DataFrame({"NoiSuDung": list(ctx.labels)}))["NoiSuDung"])
    if p.people and not p.rooms:
        rooms = [r for r, e in ctx.managers.items() if e in p.people]
        if not rooms:
            return [("md", "Người này chưa được gán quản lý phòng nào.")]
    rows = [{"Nơi sử dụng": ctx.labels.get(r, r), "Người quản lý": ctx.users.get(ctx.managers.get(r, ""), ""),
             "Email": ctx.managers.get(r, "")} for r in rooms]
    return [_understood(p), ("table", pd.DataFrame(rows))]


def _answer_rooms(ctx: Context, p: Parsed) -> list:
    tb = thietbi.active(_scope(ctx, ctx.tb))
    g = tb.groupby("NoiSuDung").agg(SoTB=("id", "size"), GiaTri=("GiaTri", "sum")).reset_index()
    g["Nơi sử dụng"] = g["NoiSuDung"].map(lambda r: ctx.labels.get(r, r))
    g["Quản lý"] = g["NoiSuDung"].map(lambda r: ctx.users.get(ctx.managers.get(r, ""), "") or ctx.managers.get(r, ""))
    out = g[["Nơi sử dụng", "Quản lý", "SoTB", "GiaTri"]].rename(columns={"SoTB": "Số thiết bị",
                                                                          "GiaTri": "Giá trị (VNĐ)"})
    return [("metrics", [("Số phòng", num(len(out))), ("Số thiết bị", num(len(tb)))]),
            ("table", out.sort_values("Số thiết bị", ascending=False))]


def _answer_inventory(ctx: Context, p: Parsed) -> list:
    kk = _scope(ctx, ctx.kk)
    if kk.empty:
        return [("md", "Chưa có dữ liệu kiểm kê.")]
    dot = p.dot or sorted(set(kk["DotKiemKe"]) - {""})[-1]
    if not p.dot:
        p.understood.append(f"{dot} (đợt gần nhất)")
    cur = kk[kk["DotKiemKe"] == dot]
    all_rooms = sorted(r for r in ctx.labels if ctx.allowed_rooms is None or r in ctx.allowed_rooms)
    rooms = p.rooms or all_rooms
    done = set(cur[cur["TrangThaiKiemKe"] == schema.DA_KIEM_KE]["NoiSuDung"])
    confirmed = {r for r, g in cur.groupby("NoiSuDung") if (g["TrangThaiXacNhan"] == schema.DA_XAC_NHAN).all()}
    parts = [_understood(p), ("metrics", [("Phòng đã kiểm kê", f"{len(done & set(rooms))}/{len(rooms)}"),
                                          ("Phòng đã xác nhận", num(len(confirmed & set(rooms))))])]
    diff = cur.assign(ChenhLech=cur["SoLuongKiemKe"] - cur["SoLuong"])
    if p.rooms:
        rows = diff[diff["NoiSuDung"].isin(p.rooms)]
        parts.append(("table", rows[["NoiSuDung", "MaTaiSan", "TenTaiSan", "DacDiem", "SoLuong", "SoLuongKiemKe",
                                     "ChenhLech", "TrangThai", "TrangThaiKiemKe", "TrangThaiXacNhan"]].rename(
            columns={**schema.labels_of(schema.KIEM_KE), "ChenhLech": "Chênh lệch"})))
        return parts
    pending = [r for r in rooms if r not in done]
    unconfirmed = [r for r in rooms if r in done and r not in confirmed]
    short = diff[diff["ChenhLech"] != 0]
    parts.append(("md", f"**Phòng chưa kiểm kê ({len(pending)}):** " +
                  (", ".join(ctx.labels.get(r, r) for r in pending) or "không có")))
    parts.append(("md", f"**Đã kiểm kê nhưng quản lý phòng chưa xác nhận ({len(unconfirmed)}):** " +
                  (", ".join(ctx.labels.get(r, r) for r in unconfirmed) or "không có")))
    if not short.empty:
        parts.append(("md", f"**Nhóm thiết bị có chênh lệch ({len(short)})**"))
        parts.append(("table", short[["NoiSuDung", "TenTaiSan", "DacDiem", "SoLuong", "SoLuongKiemKe", "ChenhLech"]]
                      .rename(columns={**schema.labels_of(schema.KIEM_KE), "ChenhLech": "Chênh lệch"})))
    return parts


def _answer_transfer(ctx: Context, p: Parsed) -> list:
    dc = ctx.dc
    if ctx.allowed_rooms is not None:
        dc = dc[dc["TuPhong"].isin(ctx.allowed_rooms) | dc["DenPhong"].isin(ctx.allowed_rooms)]
    if dc.empty:
        return [("md", "Chưa có lịch sử điều chuyển.")]
    d = pd.to_datetime(dc["NgayDieuChuyen"], errors="coerce")
    if p.month:
        m, y = p.month
        dc = dc[(d.dt.month == m) & ((d.dt.year == y) if y else True)]
    if p.rooms:
        dc = dc[dc["TuPhong"].isin(p.rooms) | dc["DenPhong"].isin(p.rooms)]
    if p.types:
        dc = dc[dc["TenThietBi"].map(_flat).isin({_flat(t) for t in p.types})]
    parts = [_understood(p), ("metrics", [("Số lần điều chuyển", num(len(dc))),
                                          ("Số thiết bị", num(dc["Title"].nunique()))])]
    if not dc.empty:
        parts.append(("table", dc.sort_values("NgayDieuChuyen", ascending=False)[
            ["NgayDieuChuyen", "Title", "TenThietBi", "TuPhong", "DenPhong", "NguoiThucHien", "LyDo"]].rename(
            columns=schema.labels_of(schema.DIEU_CHUYEN))))
    return parts


def _answer_disposal(ctx: Context, p: Parsed) -> list:
    tl = ctx.tl
    if tl.empty:
        disposed = thietbi.is_disposed(_scope(ctx, ctx.tb))
        return [("md", f"Chưa có lịch sử thanh lý theo đợt (list ThanhLy). Hiện có **{int(disposed.sum())}** "
                       "thiết bị ở trạng thái đã thanh lý.")]
    g = tl.groupby("DotThanhLy").agg(Ngay=("NgayThanhLy", "max"), SoTT=("SoToTrinh", "first"),
                                     SoTS=("id", "size"), GiaMua=("GiaMua", "sum")).reset_index()
    g = g.sort_values("Ngay", ascending=False).rename(columns={
        "DotThanhLy": "Đợt thanh lý", "Ngay": "Ngày", "SoTT": "Số tờ trình", "SoTS": "Số tài sản",
        "GiaMua": "Tổng giá mua (VNĐ)"})
    parts = [("metrics", [("Số đợt", num(len(g))), ("Số tài sản đã thanh lý", num(len(tl)))]), ("table", g)]
    if p.types or p.rooms:
        rows = tl
        if p.types:
            rows = rows[rows["TenThietBi"].map(_flat).isin({_flat(t) for t in p.types})]
        parts.append(("table", rows.drop(columns="id").rename(columns=schema.labels_of(schema.THANH_LY))))
    return parts
