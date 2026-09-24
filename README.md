# Ứng dụng Quản lý Thiết bị – Trường TH-THCS-THPT Tân Phú

Phiên bản Python (Streamlit) của app Power Apps **STP_Thietbi**. Dữ liệu vẫn lưu trên **SharePoint List**
(qua Microsoft Graph API). Ứng dụng chạy **miễn phí** trên [Streamlit Community Cloud](https://streamlit.io/cloud).

## Chức năng

| Nhóm | Chức năng | Ai thấy |
|---|---|---|
| Ban quản lý tài sản | Danh sách thiết bị (sửa như bảng tính, thêm/xóa, nhập/xuất Excel) · Nhập mới thiết bị (tự sinh Mã chi tiết) · Chỉnh sửa thông tin thiết bị (sửa/xóa) · Điều chuyển nhiều thiết bị (có lịch sử) | Quản trị, Ban quản lý tài sản |
| Ban kiểm kê | Kiểm kê theo đợt / phòng (tick có mặt, tình trạng), xem kết quả, lọc thiết bị không thấy, xuất Excel | Quản trị, Ban kiểm kê |
| Người dùng | Danh sách Phòng đang quản lý · Kiểm kê phòng mình phụ trách | Mọi người đăng nhập |
| Báo cáo | Báo cáo tổng quan BGH: số liệu, biểu đồ, tiến độ kiểm kê, thiết bị hỏng, xuất Excel | Quản trị, BGH, Ban quản lý tài sản |
| Phân quyền | Phân quyền admin (vai trò) · Phân quyền quản lý phòng (danh mục phòng + người phụ trách) · Khởi tạo SharePoint | Quản trị |

## Cấu trúc SharePoint List

**Thiết bị – dùng list có sẵn `Data_Thietbichitiet`** (mỗi dòng là một thiết bị). App tự dò cột theo **tên hiển thị**:
STT, Mã tài sản, Mã chi tiết, Chi tiết, Đặc điểm, Tên phòng ban, ĐVT, SL, Nơi sử dụng, Người sử dụng, Ngày mua,
Quản lý thiết bị, Tình trạng, Quản lý phòng, Phân quyền, Mã SAP, Thời hạn bảo hành, Ghi chú, Tên thiết bị, Giá trị,
Ngày hóa đơn, Nhóm thiết bị, Mail.

- **Mã chi tiết** tự sinh khi nhập mới: `<Mã tài sản>-<số>` với số = số lớn nhất đang có của mã tài sản đó + 1
  (vd đang có `111028-00018` → tạo `111028-00019`). Nhập nhiều thiết bị cùng lúc sẽ tạo các mã liên tiếp.
- **Nơi sử dụng** là phòng; **Quản lý phòng** (email) quyết định ai thấy phòng ở mục *Người dùng*.
- Thiết bị có Nơi sử dụng = `Thanh lý` hoặc Tình trạng = `Đã thanh lý` không tính vào tài sản đang dùng.
- Trang **Phân quyền → Khởi tạo SharePoint → Kiểm tra** cho biết từng cột đã khớp chưa.
  Cột kiểu *Person/Lookup* chỉ đọc (app không ghi vào).

**Tạo list bằng file Excel mẫu** (thư mục `templates/`, tạo lại bằng `python scripts/make_excel_templates.py`):

| File | Tên list nên đặt |
|---|---|
| `1_ThietBi.xlsx` | `Data_Thietbichitiet` (hoặc tên khác, rồi dán link list vào `list_url`) |
| `2_Phong.xlsx` | `Phong` |
| `3_DieuChuyen.xlsx` | `DieuChuyen` |
| `4_KiemKe.xlsx` | `KiemKe` |
| `5_PhanQuyen.xlsx` | `PhanQuyen` |

Microsoft Lists → **+ Danh sách mới → Từ Excel** → chọn file → chọn bảng `tbl_...` → chỉnh kiểu cột theo sheet
*HuongDan* → đặt tên list như bảng trên → **Tạo** → xóa dòng mẫu. Tạo cả 5 list ở cùng một chỗ (cùng khu vực cá nhân
hoặc cùng site). **Không đổi tên cột** – app dò cột theo đúng tên trong file. Nếu đặt tên list khác, khai báo trong
`[sharepoint.lists]`.

Hoặc để app tự tạo các list còn thiếu:

**Các list phụ** (nếu site chưa có, trang *Khởi tạo SharePoint* tạo được) – cột đầu tiên là mã:

| List | Title | Các cột |
|---|---|---|
| `Phong` | Mã phòng (= Nơi sử dụng) | TenPhong, KhuVuc, NguoiQuanLy (email), TenNguoiQuanLy |
| `DieuChuyen` | Mã chi tiết | TenThietBi, TuPhong, DenPhong, SoLuong, NgayDieuChuyen, NguoiThucHien, LyDo |
| `KiemKe` | Mã chi tiết | TenThietBi, MaPhong, DotKiemKe, SoLuongSoSach, SoLuongThucTe (1 = có mặt, 0 = không thấy), TinhTrang, NguoiKiemKe, NgayKiemKe, GhiChu |
| `PhanQuyen` | Email | HoTen, VaiTro (Quản trị hệ thống / Ban quản lý tài sản / Ban kiểm kê / Ban giám hiệu), ChucDanh |

**Tên list/cột khác mặc định?** Khai báo trong secrets, không cần sửa code:

```toml
[sharepoint.lists]
ThietBi = "Data_Thietbichitiet"   # tên list thật
Phong = "DS_Phong"

[sharepoint.columns.ThietBi]
TenPhongBan = "Số serial"          # khóa trong app = tên hiển thị hoặc tên nội bộ trên SharePoint
```

Các khóa cột của list thiết bị: `STT, MaTaiSan, MaChiTiet, ChiTiet, DacDiem, TenPhongBan, DVT, SL, NoiSuDung,
NguoiSuDung, NgayMua, QuanLyThietBi, TinhTrang, QuanLyPhong, PhanQuyenTB, MaSAP, ThoiHanBaoHanh, GhiChu,
TenThietBi, GiaTri, NgayHoaDon, NhomThietBi, Mail`.

## Hai chế độ kết nối SharePoint

| | **Chế độ 1 – Tài khoản cá nhân** (khuyên dùng) | Chế độ 2 – Quyền ứng dụng |
|---|---|---|
| Cần quản trị Microsoft 365 / IT? | **Không** (nếu trường cho phép người dùng tự đăng ký app) | Có – phải *Grant admin consent* |
| Ai đọc/ghi SharePoint | Chính người đang đăng nhập – giống Power Apps | Ứng dụng (một tài khoản chung) |
| Yêu cầu với người dùng | Có quyền Edit trên site/list chứa dữ liệu | Không |
| Cấu hình | `[auth]` có `expose_tokens`, `[sharepoint]` **không** có `client_secret` | `[sharepoint]` có `tenant_id/client_id/client_secret` |

### List cá nhân (Microsoft Lists / OneDrive) và Power Automate

Nếu list `Data_Thietbichitiet` nằm trong khu vực cá nhân của bạn (địa chỉ dạng
`https://<ten>-my.sharepoint.com/personal/<email>/Lists/...`), app vẫn dùng được – chỉ cần dán link đó vào
`list_url`. Lưu ý:

- App đọc/ghi **trực tiếp** list bằng tài khoản người đang đăng nhập, giống Power Apps với connector SharePoint.
  Không cần Power Automate làm trung gian.
- Ai dùng app (giáo viên quản lý phòng, ban kiểm kê…) phải được bạn **chia sẻ quyền Chỉnh sửa** trên list –
  giống như khi họ dùng app Power Apps hiện tại.
- Các list phụ (Phong, KiemKe, DieuChuyen, PhanQuyen) sẽ được tạo cùng chỗ với list thiết bị khi bấm
  *Khởi tạo SharePoint*; nhớ chia sẻ cả các list này.
- Các flow Power Automate bạn đang có (vd *When an item is created* → gửi mail) **vẫn chạy**, vì app ghi vào đúng list đó.
- App Python không gọi flow Power Automate được với bản miễn phí: trigger *When a HTTP request is received* là
  tính năng **Premium**.
- Về lâu dài nên chuyển list sang một **site nhóm** (Teams/SharePoint site) để dữ liệu không phụ thuộc tài khoản
  cá nhân (nếu tài khoản bị khóa khi nghỉ việc, OneDrive và list cá nhân sẽ bị xóa theo).

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
   - `[sharepoint]`: `list_url` = link của list thiết bị (mở list trên trình duyệt, copy thanh địa chỉ;
     không dùng link "Chia sẻ"). Ví dụ list cá nhân:
     `https://igcschool-my.sharepoint.com/personal/ten_igcschool_edu_vn/Lists/Data_Thietbichitiet/AllItems.aspx`.
   - `[app] admin_emails`: email của bạn.
6. Mở app, đăng nhập, vào **Phân quyền → Khởi tạo SharePoint**: bấm *Kiểm tra* để xem cột của
   `Data_Thietbichitiet` đã khớp chưa, rồi *Tạo list còn thiếu* (cần quyền Owner; list/dữ liệu có sẵn được giữ nguyên).
   Sau đó vào **Phân quyền quản lý phòng** → *Thêm tất cả vào danh mục* để tạo danh mục phòng từ các Nơi sử dụng.

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
qlts/thietbi.py         # nghiệp vụ thiết bị: sinh mã chi tiết, phòng, người quản lý phòng
qlts/kiemke.py          # màn hình kiểm kê dùng chung
qlts/ui.py              # header, footer, bảng, bộ lọc, xuất Excel
views/*.py              # từng chức năng trong menu
qlts/sp_setup.py        # tạo list/cột trên SharePoint (trang Khởi tạo + script)
scripts/setup_sharepoint.py  # tạo list bằng dòng lệnh (chế độ 2)
assets/logo.png         # (tùy chọn) đặt logo trường vào đây
```

Dữ liệu được cache 2 phút để giảm số lần gọi SharePoint; bấm **Làm mới** ở thanh bên để tải lại ngay.
