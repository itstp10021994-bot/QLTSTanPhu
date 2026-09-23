"""Dữ liệu mẫu cho chế độ demo (chưa kết nối SharePoint)."""

from . import schema

DEMO_ADMIN = "admin@demo.local"


def build_demo_data() -> dict:
    phan_quyen = [
        {"Title": DEMO_ADMIN, "HoTen": "Quản trị viên (demo)", "VaiTro": schema.ROLE_ADMIN,
         "ChucDanh": "Chuyên viên Quản lý hệ thống"},
        {"Title": "qlts@demo.local", "HoTen": "Nguyễn Văn Tài", "VaiTro": schema.ROLE_QLTS,
         "ChucDanh": "Nhân viên thiết bị"},
        {"Title": "kiemke@demo.local", "HoTen": "Trần Thị Kiểm", "VaiTro": schema.ROLE_KIEMKE,
         "ChucDanh": "Thành viên Ban kiểm kê"},
        {"Title": "bgh@demo.local", "HoTen": "Lê Văn Hiệu", "VaiTro": schema.ROLE_BGH,
         "ChucDanh": "Phó Hiệu trưởng"},
    ]
    phong = [
        {"Title": "A101", "TenPhong": "Lớp 6A1", "KhuVuc": "Dãy A",
         "NguoiQuanLy": "gv1@demo.local", "TenNguoiQuanLy": "Phạm Thị Mai"},
        {"Title": "A102", "TenPhong": "Lớp 6A2", "KhuVuc": "Dãy A",
         "NguoiQuanLy": "gv1@demo.local", "TenNguoiQuanLy": "Phạm Thị Mai"},
        {"Title": "B201", "TenPhong": "Phòng Tin học 1", "KhuVuc": "Dãy B",
         "NguoiQuanLy": "gv2@demo.local", "TenNguoiQuanLy": "Hoàng Minh Tuấn"},
        {"Title": "B202", "TenPhong": "Phòng thí nghiệm Hóa", "KhuVuc": "Dãy B",
         "NguoiQuanLy": "gv2@demo.local", "TenNguoiQuanLy": "Hoàng Minh Tuấn"},
        {"Title": "KHO", "TenPhong": "Kho thiết bị", "KhuVuc": "Dãy C",
         "NguoiQuanLy": "qlts@demo.local", "TenNguoiQuanLy": "Nguyễn Văn Tài"},
    ]
    tb = [
        ("TB0001", "Tivi Samsung 65 inch", "Thiết bị CNTT", "A101", 1, "Cái", 15_000_000, 2023, "Tốt"),
        ("TB0002", "Bàn học sinh 2 chỗ", "Bàn ghế - Nội thất", "A101", 20, "Bàn", 1_200_000, 2021, "Tốt"),
        ("TB0003", "Quạt trần", "Thiết bị điện", "A101", 4, "Cái", 800_000, 2020, "Hư hỏng nhẹ"),
        ("TB0001", "Tivi Samsung 65 inch", "Thiết bị CNTT", "A102", 1, "Cái", 15_000_000, 2023, "Tốt"),
        ("TB0002", "Bàn học sinh 2 chỗ", "Bàn ghế - Nội thất", "A102", 20, "Bàn", 1_200_000, 2021, "Tốt"),
        ("TB0010", "Máy tính để bàn Dell", "Thiết bị CNTT", "B201", 35, "Bộ", 12_000_000, 2022, "Tốt"),
        ("TB0011", "Máy chiếu Epson", "Thiết bị CNTT", "B201", 1, "Máy", 9_500_000, 2019, "Hư hỏng nặng"),
        ("TB0020", "Bộ dụng cụ thí nghiệm Hóa 10", "Thiết bị thí nghiệm", "B202", 10, "Bộ", 2_500_000, 2022, "Tốt"),
        ("TB0021", "Tủ hút khí độc", "Thiết bị thí nghiệm", "B202", 1, "Cái", 35_000_000, 2022, "Tốt"),
        ("TB0030", "Ghế xoay văn phòng", "Bàn ghế - Nội thất", "KHO", 12, "Chiếc", 900_000, 2020, "Chờ thanh lý"),
    ]
    thiet_bi = [
        {"Title": t[0], "TenThietBi": t[1], "LoaiThietBi": t[2], "MaPhong": t[3], "SoLuong": t[4],
         "DonViTinh": t[5], "NguyenGia": t[6], "NamSuDung": t[7], "TinhTrang": t[8],
         "NgayNhap": f"{t[7]}-08-15T00:00:00Z", "NguonGoc": "Ngân sách", "GhiChu": ""}
        for t in tb
    ]

    def with_ids(rows):
        return [{**r, "id": str(i)} for i, r in enumerate(rows, start=1)]

    return {
        schema.PHAN_QUYEN: with_ids(phan_quyen),
        schema.PHONG: with_ids(phong),
        schema.THIET_BI: with_ids(thiet_bi),
        schema.DIEU_CHUYEN: [],
        schema.KIEM_KE: [],
    }
