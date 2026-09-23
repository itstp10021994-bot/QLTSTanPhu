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
| Phân quyền | Phân quyền admin (vai trò) · Phân quyền quản lý phòng (danh mục phòng + người phụ trách) · Khởi tạo SharePoint | Quản trị |

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

## Hai chế độ kết nối SharePoint

| | **Chế độ 1 – Tài khoản cá nhân** (khuyên dùng) | Chế độ 2 – Quyền ứng dụng |
|---|---|---|
| Cần quản trị Microsoft 365 / IT? | **Không** (nếu trường cho phép người dùng tự đăng ký app) | Có – phải *Grant admin consent* |
| Ai đọc/ghi SharePoint | Chính người đang đăng nhập – giống Power Apps | Ứng dụng (một tài khoản chung) |
| Yêu cầu với người dùng | Có quyền Edit trên site/list chứa dữ liệu | Không |
| Cấu hình | `[auth]` có `expose_tokens`, `[sharepoint]` **không** có `client_secret` | `[sharepoint]` có `tenant_id/client_id/client_secret` |

> **Về Power Automate:** app Python không cần Power Automate. Bản Power Automate miễn phí đi kèm
> Microsoft 365 không gọi được từ bên ngoài (trigger *When an HTTP request is received* là Premium),
> nên app kết nối thẳng SharePoint qua Microsoft Graph bằng tài khoản của bạn. Các flow Power Automate
> hiện có (gửi mail khi thêm thiết bị…) vẫn chạy bình thường vì dữ liệu vẫn nằm trên cùng list.

## Bước 1 – Đăng ký ứng dụng (App registration)

1. Đăng nhập <https://entra.microsoft.com> bằng tài khoản trường → **Applications → App registrations →
   New registration**. *Nếu thấy thông báo không có quyền, tổ chức đã tắt chức năng này – hãy nhờ IT
   làm bước 1 giúp (chỉ mất 5 phút, không cần cấp quyền quản trị cho app).*
   - Tên: `QLTB-TanPhu`; Supported account types: *Accounts in this organizational directory only*.
   - Redirect URI (loại **Web**): `https://<ten-app>.streamlit.app/oauth2callback`
     (thêm `http://localhost:8501/oauth2callback` nếu muốn chạy thử trên máy).
2. Ghi lại **Application (client) ID** và **Directory (tenant) ID** ở trang Overview.
3. **Certificates & secrets → New client secret** → ghi lại cột *Value* (chỉ hiện một lần).
4. **API permissions → Add a permission → Microsoft Graph → Delegated permissions**: chọn
   `openid`, `profile`, `email`, `offline_access`, `Sites.ReadWrite.All`. Quyền *Delegated* này **không bắt buộc**
   admin consent – mỗi người sẽ tự bấm *Chấp nhận* ở lần đăng nhập đầu.
   Nếu khi đăng nhập hiện "Need admin approval", trường đã chặn người dùng tự đồng ý – khi đó cần IT bấm
   *Grant admin consent* cho app.
5. Điền vào secrets (xem `.streamlit/secrets.toml.example`):
   - `[auth]`: `client_id`, `client_secret`, tenant ID trong `server_metadata_url`, `redirect_uri`,
     một chuỗi ngẫu nhiên cho `cookie_secret`; giữ nguyên `expose_tokens` và `client_kwargs`.
   - `[sharepoint]`: `hostname` và `site_path` của site chứa list
     (ví dụ `https://igc.sharepoint.com/sites/TanPhuThietBi` → hostname `igc.sharepoint.com`, site_path `/sites/TanPhuThietBi`).
   - `[app] admin_emails`: email của bạn.
6. Mở app, đăng nhập, vào **Phân quyền → Khởi tạo SharePoint** → bấm *Kiểm tra & tạo list*
   (cần quyền Owner trên site; list/dữ liệu có sẵn được giữ nguyên).

Token đăng nhập Microsoft hết hạn sau khoảng 1 giờ; khi đó app hiện nút **Đăng nhập lại** (một cú bấm).

*Chế độ 2:* làm như trên nhưng ở bước 4 chọn **Application permissions** `Sites.ReadWrite.All` + *Grant admin consent*,
rồi điền `tenant_id/client_id/client_secret` vào `[sharepoint]` và có thể tạo list bằng
`python scripts/setup_sharepoint.py --seed-admin email@truong.edu.vn`.

## Bước 2 – Chạy thử trên máy (tùy chọn)

```bash
git clone https://github.com/itstp10021994-bot/QLTSTanPhu.git
cd QLTSTanPhu
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

Chưa có `secrets.toml` → app chạy **chế độ demo**: dữ liệu mẫu lưu ở `data/local_db.json`, đăng nhập bằng cách
chọn email (ví dụ `admin@demo.local`, `gv1@demo.local`). Muốn kết nối thật thì
`cp .streamlit/secrets.toml.example .streamlit/secrets.toml` và điền như Bước 1.

## Bước 3 – Đưa lên Internet miễn phí (Streamlit Community Cloud)

1. Đăng nhập <https://share.streamlit.io> bằng tài khoản GitHub.
2. **Create app** → chọn repo `QLTSTanPhu`, branch, file chính `app.py`, đặt tên miền `<ten-app>.streamlit.app`.
3. **Advanced settings → Secrets**: dán nội dung `secrets.toml` (các mục `[app]`, `[sharepoint]`, `[auth]`).
   `redirect_uri` phải đúng tên miền vừa đặt và trùng với Redirect URI ở Bước 1.
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
qlts/sp_setup.py        # tạo list/cột trên SharePoint (trang Khởi tạo + script)
scripts/setup_sharepoint.py  # tạo list bằng dòng lệnh (chế độ 2)
assets/logo.png         # (tùy chọn) đặt logo trường vào đây
```

Dữ liệu được cache 2 phút để giảm số lần gọi SharePoint; bấm **Làm mới** ở thanh bên để tải lại ngay.
