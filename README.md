# Ứng dụng Quản lý Thiết bị – Trường TH-THCS-THPT Tân Phú

Phiên bản Python (Streamlit) của app Power Apps **STP_Thietbi**. Dữ liệu vẫn lưu trên **SharePoint List**
(qua Microsoft Graph API). Ứng dụng chạy **miễn phí** trên [Streamlit Community Cloud](https://streamlit.io/cloud).

## Chức năng

| Nhóm | Chức năng | Ai thấy |
|---|---|---|
| Ban quản lý tài sản | Nhập mới thiết bị · Chỉnh sửa thông tin thiết bị (sửa/xóa) · Điều chuyển thiết bị (có lịch sử) | Quản trị, Ban quản lý tài sản |
| Ban kiểm kê | Kiểm kê theo đợt / phòng, xem kết quả, lọc chênh lệch, xuất Excel | Quản trị, Ban kiểm kê |
| Người dùng | Danh sách Phòng đang quản lý · Kiểm kê phòng mình phụ trách | Mọi người đăng nhập |
| Báo cáo | Báo cáo tổng quan BGH: số liệu, biểu đồ, tiến độ kiểm kê, thiết bị hỏng, xuất Excel | Quản trị, BGH, Ban quản lý tài sản |
| Phân quyền | Phân quyền admin (vai trò) · Phân quyền quản lý phòng (danh mục phòng + người phụ trách) | Quản trị |

## Cấu trúc SharePoint List

Mỗi list dùng cột mặc định **Title** làm mã. Các cột khác (tên nội bộ, không dấu):

| List | Title | Các cột |
|---|---|---|
| `ThietBi` | Mã thiết bị | TenThietBi, LoaiThietBi (choice), MaPhong, SoLuong (number), DonViTinh, NguyenGia (number), NamSuDung (number), NgayNhap (date), NguonGoc, TinhTrang (choice), GhiChu |
| `Phong` | Mã phòng | TenPhong, KhuVuc, NguoiQuanLy (email), TenNguoiQuanLy |
| `DieuChuyen` | Mã thiết bị | TenThietBi, TuPhong, DenPhong, SoLuong, NgayDieuChuyen, NguoiThucHien, LyDo |
| `KiemKe` | Mã thiết bị | TenThietBi, MaPhong, DotKiemKe, SoLuongSoSach, SoLuongThucTe, TinhTrang, NguoiKiemKe, NgayKiemKe, GhiChu |
| `PhanQuyen` | Email | HoTen, VaiTro (Quản trị hệ thống / Ban quản lý tài sản / Ban kiểm kê / Ban giám hiệu), ChucDanh |

Một mã thiết bị có thể có ở nhiều phòng (mỗi phòng một dòng). Điều chuyển một phần số lượng sẽ tách dòng
hoặc cộng dồn vào phòng nhận.

**Đã có list từ Power Apps với tên khác?** Không cần sửa code – khai báo ánh xạ trong secrets:

```toml
[sharepoint.lists]
ThietBi = "DS_ThietBi"          # tên list thật

[sharepoint.columns.ThietBi]
TenThietBi = "TenTB"            # tên cột trong app = internal name trên SharePoint
MaPhong = "Phong"
```

(Xem internal name: mở List settings → bấm vào cột → phần `Field=` trên thanh địa chỉ.)

## Bước 1 – Đăng ký ứng dụng trên Microsoft Entra ID (Azure AD)

Cần tài khoản quản trị Microsoft 365 của trường (gói Education miễn phí có Entra ID).

1. Vào <https://entra.microsoft.com> → **App registrations** → **New registration**.
   - Tên: `QLTB-TanPhu`; Supported account types: *Single tenant*.
   - Redirect URI (Web): `https://<ten-app>.streamlit.app/oauth2callback`
     (thêm cả `http://localhost:8501/oauth2callback` để chạy thử trên máy).
2. Ghi lại **Application (client) ID** và **Directory (tenant) ID**.
3. **Certificates & secrets** → *New client secret* → ghi lại *Value*.
4. **API permissions** → *Add* → *Microsoft Graph* → **Application permissions** → `Sites.ReadWrite.All`
   (hoặc `Sites.Selected` nếu muốn chỉ cấp quyền cho 1 site) → **Grant admin consent**.
   Thêm **Delegated permissions** `openid`, `email`, `profile` cho việc đăng nhập.

Một app registration dùng được cho cả đọc/ghi SharePoint (`[sharepoint]`) và đăng nhập (`[auth]`).

## Bước 2 – Chạy thử trên máy

```bash
git clone https://github.com/itstp10021994-bot/QLTSTanPhu.git
cd QLTSTanPhu
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

Chưa có `secrets.toml` → app chạy **chế độ demo**: dữ liệu mẫu lưu ở `data/local_db.json`, đăng nhập bằng cách
chọn email (ví dụ `admin@demo.local`, `gv1@demo.local`).

Kết nối SharePoint thật:

```bash
cp .streamlit/secrets.toml.example .streamlit/secrets.toml   # rồi điền thông tin
python scripts/setup_sharepoint.py --seed-admin email_cua_ban@truong.edu.vn
```

Script tự tạo 5 list và các cột còn thiếu trên site (list đã có sẽ được giữ nguyên).

## Bước 3 – Đưa lên Internet miễn phí (Streamlit Community Cloud)

1. Đăng nhập <https://share.streamlit.io> bằng tài khoản GitHub.
2. **Create app** → chọn repo `QLTSTanPhu`, branch, file chính `app.py`, đặt tên miền `<ten-app>.streamlit.app`.
3. **Advanced settings → Secrets**: dán nội dung `secrets.toml` (các mục `[app]`, `[sharepoint]`, `[auth]`).
   Nhớ sửa `redirect_uri` đúng tên miền và thêm URI đó vào app registration ở Bước 1.
4. **Deploy**. Mỗi lần push code lên GitHub, app tự cập nhật.

> `secrets.toml` đã nằm trong `.gitignore` – **không** commit mật khẩu lên GitHub.
> App miễn phí sẽ "ngủ" sau vài ngày không ai dùng; người vào sau chỉ cần bấm *Wake up*.

## Phân quyền

- Email trong `[app] admin_emails` luôn là quản trị – dùng để đăng nhập lần đầu và phân quyền cho người khác.
- **Phân quyền admin**: gán vai trò (một người nhiều vai trò = nhiều dòng). Cột *Chức danh* hiển thị ở trang chủ.
- **Phân quyền quản lý phòng**: gán email người phụ trách cho từng phòng. Người đó thấy phòng ở mục *Người dùng*
  và tự kiểm kê được.

## Cấu trúc mã nguồn

```
app.py                  # khung app, menu theo quyền, header/footer
qlts/schema.py          # định nghĩa list, cột, vai trò, danh mục lựa chọn
qlts/storage.py         # SharePointStore (Graph API) + LocalStore (demo), cache
qlts/auth.py            # đăng nhập Microsoft (st.login) / demo, phân quyền
qlts/kiemke.py          # màn hình kiểm kê dùng chung
qlts/ui.py              # header, footer, bảng, bộ lọc, xuất Excel
views/*.py              # từng chức năng trong menu
scripts/setup_sharepoint.py  # tạo list trên SharePoint
assets/logo.png         # (tùy chọn) đặt logo trường vào đây
```

Dữ liệu được cache 2 phút để giảm số lần gọi SharePoint; bấm **Làm mới** ở thanh bên để tải lại ngay.
