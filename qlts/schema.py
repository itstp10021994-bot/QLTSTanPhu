"""Định nghĩa các SharePoint List mà ứng dụng sử dụng.

Mỗi list luôn có cột mặc định ``Title`` của SharePoint; ứng dụng dùng cột này
làm "mã" (mã thiết bị, mã phòng, email...). Các cột còn lại được khai báo dưới
đây kèm kiểu dữ liệu để script ``scripts/setup_sharepoint.py`` tự tạo list.

Nếu list SharePoint hiện có của bạn dùng tên cột khác, không cần sửa code:
khai báo ánh xạ trong ``.streamlit/secrets.toml`` (xem README).
"""

# ---- Vai trò (phân quyền) ----
ROLE_ADMIN = "Quản trị hệ thống"
ROLE_QLTS = "Ban quản lý tài sản"
ROLE_KIEMKE = "Ban kiểm kê"
ROLE_BGH = "Ban giám hiệu"
ROLES = [ROLE_ADMIN, ROLE_QLTS, ROLE_KIEMKE, ROLE_BGH]

# ---- Giá trị lựa chọn ----
TINH_TRANG = ["Tốt", "Hư hỏng nhẹ", "Hư hỏng nặng", "Chờ thanh lý", "Đã thanh lý", "Mất"]
LOAI_THIET_BI = [
    "Thiết bị dạy học",
    "Thiết bị CNTT",
    "Thiết bị điện",
    "Bàn ghế - Nội thất",
    "Thiết bị thí nghiệm",
    "Thiết bị thể thao",
    "Khác",
]
DON_VI_TINH = ["Cái", "Bộ", "Chiếc", "Máy", "Bàn", "Ghế", "Hộp", "Khác"]

# ---- Tên list (khóa nội bộ) ----
THIET_BI = "ThietBi"
PHONG = "Phong"
DIEU_CHUYEN = "DieuChuyen"
KIEM_KE = "KiemKe"
PHAN_QUYEN = "PhanQuyen"

# kiểu: text | note | number | date | choice
LISTS: dict[str, dict] = {
    THIET_BI: {
        "title_label": "Mã thiết bị",
        "columns": {
            "TenThietBi": {"type": "text", "label": "Tên thiết bị"},
            "LoaiThietBi": {"type": "choice", "label": "Loại thiết bị", "choices": LOAI_THIET_BI},
            "MaPhong": {"type": "text", "label": "Mã phòng"},
            "SoLuong": {"type": "number", "label": "Số lượng"},
            "DonViTinh": {"type": "text", "label": "Đơn vị tính"},
            "NguyenGia": {"type": "number", "label": "Nguyên giá (VNĐ)"},
            "NamSuDung": {"type": "number", "label": "Năm đưa vào sử dụng"},
            "NgayNhap": {"type": "date", "label": "Ngày nhập"},
            "NguonGoc": {"type": "text", "label": "Nguồn gốc"},
            "TinhTrang": {"type": "choice", "label": "Tình trạng", "choices": TINH_TRANG},
            "GhiChu": {"type": "note", "label": "Ghi chú"},
        },
    },
    PHONG: {
        "title_label": "Mã phòng",
        "columns": {
            "TenPhong": {"type": "text", "label": "Tên phòng"},
            "KhuVuc": {"type": "text", "label": "Khu vực / Dãy"},
            "NguoiQuanLy": {"type": "text", "label": "Email người quản lý"},
            "TenNguoiQuanLy": {"type": "text", "label": "Tên người quản lý"},
        },
    },
    DIEU_CHUYEN: {
        "title_label": "Mã thiết bị",
        "columns": {
            "TenThietBi": {"type": "text", "label": "Tên thiết bị"},
            "TuPhong": {"type": "text", "label": "Từ phòng"},
            "DenPhong": {"type": "text", "label": "Đến phòng"},
            "SoLuong": {"type": "number", "label": "Số lượng"},
            "NgayDieuChuyen": {"type": "date", "label": "Ngày điều chuyển"},
            "NguoiThucHien": {"type": "text", "label": "Người thực hiện"},
            "LyDo": {"type": "note", "label": "Lý do"},
        },
    },
    KIEM_KE: {
        "title_label": "Mã thiết bị",
        "columns": {
            "TenThietBi": {"type": "text", "label": "Tên thiết bị"},
            "MaPhong": {"type": "text", "label": "Mã phòng"},
            "DotKiemKe": {"type": "text", "label": "Đợt kiểm kê"},
            "SoLuongSoSach": {"type": "number", "label": "SL sổ sách"},
            "SoLuongThucTe": {"type": "number", "label": "SL thực tế"},
            "TinhTrang": {"type": "choice", "label": "Tình trạng", "choices": TINH_TRANG},
            "NguoiKiemKe": {"type": "text", "label": "Người kiểm kê"},
            "NgayKiemKe": {"type": "date", "label": "Ngày kiểm kê"},
            "GhiChu": {"type": "note", "label": "Ghi chú"},
        },
    },
    PHAN_QUYEN: {
        "title_label": "Email",
        "columns": {
            "HoTen": {"type": "text", "label": "Họ tên"},
            "VaiTro": {"type": "choice", "label": "Vai trò", "choices": ROLES},
            "ChucDanh": {"type": "text", "label": "Chức danh"},
        },
    },
}


def columns_of(list_name: str) -> list[str]:
    """Tất cả cột (kể cả Title) của một list, theo thứ tự khai báo."""
    return ["Title", *LISTS[list_name]["columns"].keys()]


def labels_of(list_name: str) -> dict[str, str]:
    """Ánh xạ tên cột -> nhãn tiếng Việt để hiển thị."""
    spec = LISTS[list_name]
    return {"Title": spec["title_label"], **{k: v["label"] for k, v in spec["columns"].items()}}


def column_type(list_name: str, column: str) -> str:
    if column == "Title":
        return "text"
    return LISTS[list_name]["columns"][column]["type"]
