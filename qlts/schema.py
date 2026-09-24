"""Định nghĩa các SharePoint List mà ứng dụng sử dụng.

- ``ThietBi`` trỏ tới list có sẵn ``Data_Thietbichitiet``: mỗi dòng là MỘT thiết bị,
  định danh bằng "Mã chi tiết" (``<Mã tài sản>-00001``).
- Các list còn lại do ứng dụng tạo (trang "Kết nối SharePoint"), dùng cột ``Title`` làm mã.
"""

# ---- Vai trò (phân quyền) ----
ROLE_ADMIN = "Quản trị hệ thống"
ROLE_QLTS = "Ban quản lý tài sản"
ROLE_KIEMKE = "Ban kiểm kê"
ROLE_BGH = "Ban giám hiệu"
ROLES = [ROLE_ADMIN, ROLE_QLTS, ROLE_KIEMKE, ROLE_BGH]

# ---- Giá trị lựa chọn ----
# Tình trạng: danh sách gợi ý; các giá trị khác đang có trong SharePoint vẫn được giữ và hiển thị.
TINH_TRANG = ["Mới", "Bình thường", "Cần kiểm tra", "Cần sửa chữa", "Cần thanh lý", "Đã thanh lý", "Mất"]
TINH_TRANG_TOT = {"Mới", "Bình thường", "Tốt"}
TINH_TRANG_DA_THANH_LY = {"Đã thanh lý"}
NOI_THANH_LY = "Thanh lý"
DA_KIEM_KE = "Đã kiểm kê"
DANG_KIEM_KE = "Đang kiểm kê"
DA_XAC_NHAN = "Đã xác nhận"
KHONG_DONG_Y = "Không đồng ý"  # "Nơi sử dụng" của thiết bị đã đưa đi thanh lý
NHOM_THIET_BI = [
    "Nhóm Công Nghệ Thông Tin",
    "Nhóm Thiết bị dạy học",
    "Nhóm Điện - Điện lạnh",
    "Nhóm Nội thất",
    "Nhóm Thí nghiệm",
    "Nhóm Thể thao",
    "Nhóm Khác",
]
DON_VI_TINH = ["Cái", "Bộ", "Chiếc", "Máy", "Bàn", "Ghế", "Hộp", "Khác"]

# ---- Tên list (khóa nội bộ) ----
THIET_BI = "ThietBi"
PHONG = "Phong"
DIEU_CHUYEN = "DieuChuyen"
KIEM_KE = "KiemKe"
PHAN_QUYEN = "PhanQuyen"

# Mỗi list:
#   sp_list: tên list mặc định trên SharePoint (đổi được trong secrets [sharepoint.lists])
#   columns: khóa trong app -> {type, label, sp?}
#     - type: text | note | number | date | choice
#     - label: nhãn hiển thị; đồng thời là TÊN HIỂN THỊ của cột trên SharePoint để app tự dò cột
#     - sp: tên nội bộ bắt buộc (vd "Title")
# Khi đọc list có sẵn, app so khớp mỗi cột theo: [sharepoint.columns] trong secrets -> sp -> khóa -> label.
LISTS: dict[str, dict] = {
    THIET_BI: {
        "sp_list": "Data_Thietbichitiet",
        "aliases": ["1_ThietBi", "ThietBi"],  # tên khi tạo list từ file biểu mẫu
        "columns": {
            "STT": {"type": "number", "label": "STT"},
            "MaTaiSan": {"type": "text", "label": "Mã tài sản"},
            "MaChiTiet": {"type": "text", "label": "Mã chi tiết"},
            "ChiTiet": {"type": "text", "label": "Chi tiết"},
            "DacDiem": {"type": "note", "label": "Đặc điểm"},
            "TenPhongBan": {"type": "text", "label": "Tên phòng ban"},
            "DVT": {"type": "text", "label": "ĐVT"},
            "SL": {"type": "number", "label": "SL"},
            "NoiSuDung": {"type": "text", "label": "Nơi sử dụng"},
            "NguoiSuDung": {"type": "text", "label": "Người sử dụng"},
            "NgayMua": {"type": "date", "label": "Ngày mua"},
            "QuanLyThietBi": {"type": "text", "label": "Quản lý thiết bị"},
            "TinhTrang": {"type": "choice", "label": "Tình trạng", "choices": TINH_TRANG},
            "QuanLyPhong": {"type": "text", "label": "Quản lý phòng"},
            "PhanQuyenTB": {"type": "text", "label": "Phân quyền"},
            "MaSAP": {"type": "text", "label": "Mã SAP"},
            "ThoiHanBaoHanh": {"type": "text", "label": "Thời hạn bảo hành"},
            "GhiChu": {"type": "note", "label": "Ghi chú"},
            "TenThietBi": {"type": "text", "label": "Tên thiết bị"},
            "GiaTri": {"type": "number", "label": "Giá trị"},
            "NgayHoaDon": {"type": "date", "label": "Ngày hóa đơn"},
            "NhomThietBi": {"type": "text", "label": "Nhóm thiết bị"},
            "Mail": {"type": "text", "label": "Mail"},
        },
    },
    PHONG: {
        "sp_list": "Phong",
        "aliases": ["2_Phong"],  # tên khi tạo list từ file biểu mẫu
        "columns": {
            "Title": {"type": "text", "label": "Mã phòng", "sp": "Title"},
            "TenPhong": {"type": "text", "label": "Tên phòng"},
            "KhuVuc": {"type": "text", "label": "Khu vực"},
            "NguoiQuanLy": {"type": "text", "label": "Email người quản lý"},
            "TenNguoiQuanLy": {"type": "text", "label": "Tên người quản lý"},
        },
    },
    DIEU_CHUYEN: {
        "sp_list": "DieuChuyen",
        "aliases": ["3_DieuChuyen"],  # tên khi tạo list từ file biểu mẫu
        "columns": {
            "Title": {"type": "text", "label": "Mã chi tiết", "sp": "Title"},
            "TenThietBi": {"type": "text", "label": "Tên thiết bị"},
            "TuPhong": {"type": "text", "label": "Từ phòng"},
            "DenPhong": {"type": "text", "label": "Đến phòng"},
            "SoLuong": {"type": "number", "label": "Số lượng"},
            "NgayDieuChuyen": {"type": "date", "label": "Ngày điều chuyển"},
            "NguoiThucHien": {"type": "text", "label": "Người thực hiện"},
            "LyDo": {"type": "note", "label": "Lý do"},
        },
    },
    # List kiểm kê dạng gộp (giống "Data_Thietbi"): mỗi dòng = một nhóm thiết bị cùng
    # Mã tài sản + Đặc điểm + Nơi sử dụng trong một đợt kiểm kê.
    KIEM_KE: {
        "sp_list": "Data_Thietbi",
        "aliases": ["4_KiemKe", "KiemKe"],  # tên khi tạo list từ file biểu mẫu
        "columns": {
            "MaTaiSan": {"type": "text", "label": "Mã số tài sản"},
            "STT": {"type": "number", "label": "STT"},
            "TenTaiSan": {"type": "text", "label": "Tên tài sản"},
            "DacDiem": {"type": "note", "label": "Đặc điểm"},
            "DVT": {"type": "text", "label": "ĐVT"},
            "SoLuong": {"type": "number", "label": "Số lượng"},
            "SoLuongKiemKe": {"type": "number", "label": "Số lượng kiểm kê"},
            "GhiChu": {"type": "note", "label": "Ghi chú"},
            "QuanLyThietBi": {"type": "text", "label": "Quản lý thiết bị"},
            "NoiSuDung": {"type": "text", "label": "Nơi sử dụng"},
            "QuanLyPhong": {"type": "text", "label": "Quản lý phòng"},
            "TrangThai": {"type": "text", "label": "Trạng thái"},
            "NgayKiemKe": {"type": "date", "label": "Ngày kiểm kê"},
            "TrangThaiKiemKe": {"type": "text", "label": "Trạng thái kiểm kê"},
            "NgayXacNhan": {"type": "date", "label": "Ngày xác nhận"},
            "TrangThaiXacNhan": {"type": "text", "label": "Trạng thái xác nhận"},
            "DotKiemKe": {"type": "text", "label": "Đợt kiểm kê"},
            # Không bắt buộc: có cột thì app ghi thêm, không có thì bỏ qua
            "NguoiKiemKe": {"type": "text", "label": "Người kiểm kê"},
            "NguoiXacNhan": {"type": "text", "label": "Người xác nhận"},
        },
    },
    PHAN_QUYEN: {
        "sp_list": "PhanQuyen",
        "aliases": ["5_PhanQuyen"],  # tên khi tạo list từ file biểu mẫu
        "columns": {
            "Title": {"type": "text", "label": "Email", "sp": "Title"},
            "HoTen": {"type": "text", "label": "Họ tên"},
            "VaiTro": {"type": "choice", "label": "Vai trò", "choices": ROLES},
            "ChucDanh": {"type": "text", "label": "Chức danh"},
        },
    },
}


def columns_of(list_name: str) -> list[str]:
    """Tất cả cột của một list, theo thứ tự khai báo."""
    return list(LISTS[list_name]["columns"])


def labels_of(list_name: str) -> dict[str, str]:
    """Ánh xạ khóa cột -> nhãn tiếng Việt để hiển thị."""
    return {k: v["label"] for k, v in LISTS[list_name]["columns"].items()}


def column_type(list_name: str, column: str) -> str:
    return LISTS[list_name]["columns"][column]["type"]
