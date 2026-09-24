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
        {"Title": "L1_PH103", "TenPhong": "Phòng học 103", "KhuVuc": "Lầu 1",
         "NguoiQuanLy": "gv1@demo.local", "TenNguoiQuanLy": "Phạm Thị Mai"},
        {"Title": "L1_PH104", "TenPhong": "Phòng học 104", "KhuVuc": "Lầu 1",
         "NguoiQuanLy": "gv1@demo.local", "TenNguoiQuanLy": "Phạm Thị Mai"},
        {"Title": "Trệt_PH001", "TenPhong": "Phòng học 001", "KhuVuc": "Tầng trệt",
         "NguoiQuanLy": "gv2@demo.local", "TenNguoiQuanLy": "Hoàng Minh Tuấn"},
        {"Title": "Trệt_HOA", "TenPhong": "Phòng thí nghiệm Hóa", "KhuVuc": "Tầng trệt",
         "NguoiQuanLy": "gv2@demo.local", "TenNguoiQuanLy": "Hoàng Minh Tuấn"},
        {"Title": "Kho_TB", "TenPhong": "Kho thiết bị", "KhuVuc": "Tầng trệt",
         "NguoiQuanLy": "qlts@demo.local", "TenNguoiQuanLy": "Nguyễn Văn Tài"},
    ]
    managers = {p["Title"]: p["NguoiQuanLy"] for p in phong}
    # (Mã tài sản, Tên thiết bị/Chi tiết, Đặc điểm, Serial, Nơi sử dụng, Tình trạng, Mã SAP, Giá trị, Ngày mua)
    units = [
        ("111007", "Tivi BGH", "Samsung 65inch, UA65NU7100", "05SK3NNK70118", "L1_PH103", "Bình thường", "T000766001", 15_000_000, "2022-08-15"),
        ("111027", "Điện thoại", "Oppo, 6GB, F9", "", "Thanh lý", "Cần thanh lý", "", 5_000_000, "2019-06-01"),
        ("111028", "Máy chiếu", "Epson, 1024x768, EB-530", "VFQF610018L", "Trệt_PH001", "Bình thường", "T000816001", 12_000_000, "2021-08-20"),
        ("111028", "Máy chiếu", "Epson, 1024x768, EB-530", "VFQF980117L", "L1_PH103", "Bình thường", "T000816001", 12_000_000, "2021-08-20"),
        ("111028", "Máy chiếu", "Epson, 1024x768, EB-530", "X4J7910026", "Trệt_HOA", "Bình thường", "T000817001", 12_000_000, "2021-08-20"),
        ("111028", "Máy chiếu", "Epson, 1280x800, EB-955WH", "VFQF670219L", "L1_PH104", "Mới", "T000817001", 18_000_000, "2024-08-10"),
        ("111028", "Máy chiếu", "Panasonic, 1024x768, PT-LB386", "", "Kho_TB", "Cần kiểm tra", "T000215007", 11_000_000, "2020-09-01"),
        ("111032", "Máy chấm công", "ZKTeco, MB80-SL", "", "Trệt_PH001", "Bình thường", "T002172001", 4_500_000, "2023-08-22"),
        ("111032", "Máy chấm công", "ZKTeco, MB80-SL", "", "L1_PH104", "Bình thường", "T002172002", 4_500_000, "2023-08-22"),
        ("111036", "Máy Tính Xách Tay", "Dell, 16RAM - 512 SSD", "", "Kho_TB", "Mới", "T000231002", 22_000_000, "2023-11-01"),
        ("111051", "Loa phát thanh", "Guinness, Loa, KS-103G", "", "L1_PH103", "Bình thường", "", 1_200_000, "2024-09-05"),
        ("111051", "Loa phát thanh", "Guinness, Loa, KS-103G", "", "L1_PH103", "Bình thường", "", 1_200_000, "2024-09-05"),
        ("111051", "Loa phát thanh", "Guinness, Loa, KS-103G", "", "L1_PH103", "Mới", "", 1_200_000, "2024-09-05"),
        ("111051", "Loa phát thanh", "Âm thanh thông báo", "", "L1_PH103", "Bình thường", "", 900_000, "2022-01-10"),
    ]
    counters: dict[str, int] = {}
    thiet_bi = []
    for i, u in enumerate(units, start=1):
        counters[u[0]] = counters.get(u[0], 0) + 1
        thiet_bi.append({
            "STT": i, "MaTaiSan": u[0], "MaChiTiet": f"{u[0]}-{counters[u[0]]:05d}", "ChiTiet": u[1],
            "DacDiem": u[2], "TenPhongBan": u[3], "DVT": "Cái", "SL": None, "NoiSuDung": u[4],
            "NguoiSuDung": managers.get(u[4], ""), "NgayMua": u[8] + "T00:00:00+07:00",
            "QuanLyThietBi": "Nguyễn Văn Tài", "TinhTrang": u[5], "QuanLyPhong": managers.get(u[4], ""),
            "PhanQuyenTB": "admin", "MaSAP": u[6], "ThoiHanBaoHanh": "", "GhiChu": "", "TenThietBi": u[1],
            "GiaTri": u[7], "NgayHoaDon": "", "NhomThietBi": "Nhóm Công Nghệ Thông Tin", "Mail": "",
        })

    def with_ids(rows):
        return [{**r, "id": str(i)} for i, r in enumerate(rows, start=1)]

    return {
        schema.PHAN_QUYEN: with_ids(phan_quyen),
        schema.PHONG: with_ids(phong),
        schema.THIET_BI: with_ids(thiet_bi),
        schema.DIEU_CHUYEN: [],
        schema.KIEM_KE: [],
    }
