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
        {"Title": "L1_PH103", "TenPhong": "Phòng học 103",
         "NguoiQuanLy": "gv1@demo.local", "TenNguoiQuanLy": "Phạm Thị Mai"},
        {"Title": "L1_PH104", "TenPhong": "Phòng học 104",
         "NguoiQuanLy": "gv1@demo.local", "TenNguoiQuanLy": "Phạm Thị Mai"},
        {"Title": "Trệt_PH001", "TenPhong": "Phòng học 001",
         "NguoiQuanLy": "gv2@demo.local", "TenNguoiQuanLy": "Hoàng Minh Tuấn"},
        {"Title": "Trệt_HOA", "TenPhong": "Phòng thí nghiệm Hóa",
         "NguoiQuanLy": "gv2@demo.local", "TenNguoiQuanLy": "Hoàng Minh Tuấn"},
        {"Title": "Kho_TB", "TenPhong": "Kho thiết bị",
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

    loai = [
        {"TenThietBi": ten, "MaPhanLoai": ma, "NhomThietBi": nhom} for ten, ma, nhom in [
            ("Tivi", "111007", "Nhóm Công Nghệ Thông Tin"), ("Điện thoại", "111027", "Nhóm Công Nghệ Thông Tin"),
            ("Máy chiếu", "111028", "Nhóm Công Nghệ Thông Tin"), ("Máy chấm công", "111032", "Nhóm Công Nghệ Thông Tin"),
            ("Máy Tính Xách Tay", "111036", "Nhóm Công Nghệ Thông Tin"), ("Loa phát thanh", "111051", "Nhóm Thiết Bị Điện"),
            ("Bơm chữa cháy", "111296", "Nhóm Phòng Cháy Chữa Cháy"), ("Máy May", "111306", "Nhóm Thiết Bị Điện"),
            ("Màn hình LED", "111305", "Nhóm Công Nghệ Thông Tin"), ("Micro nói chung", "111304", "Nhóm Công Nghệ Thông Tin"),
        ]
    ]

    return {
        schema.LOAI_TB: with_ids(loai),
        schema.PHAN_QUYEN: with_ids(phan_quyen),
        schema.PHONG: with_ids(phong),
        schema.THIET_BI: with_ids(thiet_bi),
        schema.DIEU_CHUYEN: [],
        schema.KIEM_KE: [],
    }


def build_demo_tuyensinh() -> dict:
    """Hai list tuyển sinh mẫu (cố ý ghi quận/huyện không thống nhất để thử phần chuẩn hóa)."""
    import random

    rnd = random.Random(7)
    districts = [  # (cách ghi trong dữ liệu, trọng số, các phường)
        (["Tân Phú", "Q. Tân Phú", "Quận Tân Phú", "tân phú"], 30,
         ["Phường Tân Sơn Nhì", "P. Tây Thạnh", "Phường Sơn Kỳ", "Phường Tân Quý", "Phường Phú Thọ Hòa",
          "Phường Hòa Thạnh", "Phường Hiệp Tân", "P. Tân Thới Hòa"]),
        (["Tân Bình", "Q.Tân Bình"], 14, ["Phường 13", "Phường 14", "P.15"]),
        (["Bình Tân", "Quận Bình Tân"], 13, ["Phường Bình Hưng Hòa", "Phường Bình Trị Đông", "P. An Lạc"]),
        (["Quận 6", "Q6"], 7, ["Phường 10", "Phường 11"]),
        (["Quận 11", "Q.11"], 6, ["Phường 3", "Phường 5"]),
        (["Bình Thạnh"], 5, ["Phường 25", "Phường 26"]),
        (["Gò Vấp", "Q. Gò Vấp"], 5, ["Phường 10", "Phường 16"]),
        (["Quận 8"], 3, ["Phường 4"]),
        (["Bình Chánh", "H. Bình Chánh", "Huyện Bình Chánh"], 6, ["Xã Vĩnh Lộc A", "Thị trấn Tân Túc"]),
        (["Hóc Môn"], 3, ["Xã Xuân Thới Sơn"]),
        (["Thủ Đức", "TP Thủ Đức"], 3, ["Phường Linh Trung"]),
        (["Quận 12"], 3, ["Phường Tân Thới Nhất"]),
        (["Thuận An"], 2, ["Phường Lái Thiêu"]),
    ]
    weights = [d[1] for d in districts]
    grades = [1, 1, 1, 2, 3, 6, 6, 6, 7, 8, 10, 10, 10, 11]
    sources = ["Facebook", "Website", "Người quen giới thiệu", "Hội thảo tuyển sinh", "Zalo OA", "Trường mầm non"]
    data, nhap_hoc = [], []
    for start, volume in [(2021, 520), (2022, 610), (2023, 700), (2024, 760), (2025, 840)]:
        nam = f"{start}-{start + 1}"
        for i in range(volume):
            d = rnd.choices(districts, weights)[0]
            ward = rnd.choice(d[2])
            grade = rnd.choice(grades)
            enrolled = rnd.random() < 0.34 + 0.02 * (start - 2021)
            status = "Đã nhập học" if enrolled else rnd.choice(["Đang tư vấn", "Không nhập học", "Đã test đầu vào"])
            gioi = rnd.choice(["Nam", "Nữ"])
            data.append({"Title": f"TS{start}-{i + 1:04d}", "Năm học": nam, "Khối đăng ký": f"Khối {grade}",
                         "Quận/Huyện": rnd.choice(d[0]), "Phường/Xã": ward, "Giới tính": gioi,
                         "Nguồn": rnd.choice(sources), "Trạng thái": status,
                         "Created": f"{start}-{rnd.randint(1, 8):02d}-{rnd.randint(1, 28):02d}T08:00:00Z"})
            if enrolled:
                quan = d[0][0]
                prefix = "" if quan.startswith(("Quận", "Huyện", "TP")) else ("Huyện " if quan in ("Bình Chánh", "Hóc Môn") else "Quận ")
                if quan == "Thuận An":
                    prefix = "TP. "
                tinh = "Bình Dương" if quan == "Thuận An" else "TP. Hồ Chí Minh"
                nhap_hoc.append({"Title": f"HS{start % 100}{len(nhap_hoc) + 1:04d}", "Năm học": nam,
                                 "Lớp": f"{grade}A{rnd.randint(1, 4)}", "Giới tính": gioi,
                                 "Địa chỉ": f"{rnd.randint(1, 300)} đường số {rnd.randint(1, 40)}, {ward}, "
                                            f"{prefix}{quan}, {tinh}",
                                 "Ngày nhập học": f"{start}-08-{rnd.randint(1, 28):02d}"})
    return {"NhapHoc": nhap_hoc, "Data_TuyenSinh": data}
