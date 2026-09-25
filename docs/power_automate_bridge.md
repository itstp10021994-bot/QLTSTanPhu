# Kết nối app với SharePoint qua Power Automate (không cần App registration)

Dùng khi bạn **không có quyền** tạo App registration trên Microsoft Entra nhưng có **Power Automate Premium**.

```
App Python (Streamlit) ──HTTP──▶ Flow "QLTB-API" ──▶ SharePoint site QLTSTanPhu (đọc/ghi list)
                                                 └─▶ Outlook (gửi mã đăng nhập qua email)
```

- App gửi yêu cầu tới flow; flow dùng **tài khoản của bạn** (chủ flow) để đọc/ghi SharePoint và gửi mail.
- Người dùng đăng nhập app bằng **mã 6 số gửi vào email trường** (chỉ email có trong Phân quyền / danh mục phòng /
  cột Quản lý phòng mới nhận được mã).
- Chỉ cần **một flow** với 5 bước.

---

## Bước 1 – Chọn mã bí mật (key)

Tự nghĩ một chuỗi dài, khó đoán, chỉ gồm chữ và số, ví dụ `TanPhu2026QlTbX9k2m7Qp4`.
Mã này dùng ở **bước 3** (trong flow) và **bước 7** (trong Secrets). Không chia sẻ cho ai.

## Bước 2 – Tạo flow và trigger

1. Vào <https://make.powerautomate.com> → **Tạo** → **Luồng đám mây tức thì (Instant cloud flow)** → đặt tên
   `QLTB-API` → bấm **Bỏ qua** (không chọn trigger) .
2. Thêm trigger **When an HTTP request is received** (connector *Request*).
   - **Who can trigger the flow?**: `Anyone`
   - **Request Body JSON Schema**: dán nguyên đoạn sau

```json
{
  "type": "object",
  "properties": {
    "key": { "type": "string" },
    "action": { "type": "string" },
    "method": { "type": "string" },
    "uri": { "type": "string" },
    "body": {},
    "to": { "type": "string" },
    "subject": { "type": "string" },
    "html": { "type": "string" }
  }
}
```

## Bước 3 – Kiểm tra mã bí mật (Condition)

Thêm bước **Condition** (Điều kiện), đặt tên `Kiem tra`. Ở ô bên trái chọn **Expression (fx)** và dán
(thay `MA-BI-MAT` bằng key ở bước 1, thay `@igcschool.edu.vn` nếu trường dùng tên miền khác):

```
and(
  equals(triggerBody()?['key'], 'MA-BI-MAT'),
  or(
    and(equals(triggerBody()?['action'], 'mail'), endsWith(toLower(triggerBody()?['to']), '@igcschool.edu.vn')),
    and(equals(triggerBody()?['action'], 'sp'), startsWith(triggerBody()?['uri'], '_api/web'))
  )
)
```

Toán tử: **is equal to**, ô bên phải: `true`.

- Nhánh **False**: thêm **Response** – Status Code `403`, Body `{"error": "forbidden"}`.

## Bước 4 – Nhánh True: phân loại yêu cầu (Switch)

Trong nhánh **True**, thêm **Switch** – On: *Expression* `triggerBody()?['action']`.

### Case `mail` – gửi mã đăng nhập

1. **Office 365 Outlook → Send an email (V2)**
   - To: *Expression* `triggerBody()?['to']`
   - Subject: *Expression* `triggerBody()?['subject']`
   - Body: *Expression* `triggerBody()?['html']`
2. **Response** – Status Code `200`, Body `{"ok": true}`.

### Case `sp` – đọc/ghi SharePoint

1. **SharePoint → Send an HTTP request to SharePoint** (giữ tên mặc định của bước)
   - **Site Address**: chọn site **QLTSTanPhu**
   - **Method**: chọn *Enter custom value* rồi nhập *Expression* `triggerBody()?['method']`
   - **Uri**: *Expression* `triggerBody()?['uri']`
   - **Headers** (3 dòng):

     | Key | Value |
     |---|---|
     | `Accept` | `application/json;odata=nometadata` |
     | `Content-Type` | `application/json;odata=nometadata` |
     | `IF-MATCH` | `*` |

   - **Body**: *Expression*
     ```
     if(or(equals(triggerBody()?['method'], 'GET'), equals(triggerBody()?['method'], 'DELETE')), '', string(triggerBody()?['body']))
     ```
2. **Response**
   - Status Code: *Expression* `outputs('Send_an_HTTP_request_to_SharePoint')?['statusCode']`
   - Headers: `Content-Type` = `application/json`
   - Body: *Expression* `body('Send_an_HTTP_request_to_SharePoint')`
   - Bấm **…** của bước Response → **Settings / Configure run after** → tích cả **is successful** và
     **has failed** (để app nhận được thông báo lỗi của SharePoint thay vì flow chỉ báo thất bại).

> Nếu bạn đổi tên bước "Send an HTTP request to SharePoint", sửa tên trong 2 biểu thức trên cho khớp
> (dấu cách thay bằng dấu gạch dưới `_`).

## Bước 5 – Lưu và lấy URL

Bấm **Lưu**. Mở lại trigger **When an HTTP request is received** → copy **HTTP URL** (dạng
`https://...logic.azure.com/workflows/.../triggers/manual/paths/invoke?...&sig=...` hoặc
`https://...powerplatform.com/...`). URL này là "chìa khóa" thứ hai – **không chia sẻ**.

## Bước 6 – Tạo các list (nếu chưa có)

Trên site QLTSTanPhu tạo 5 list từ file biểu mẫu: `1_ThietBi`, `2_Phong`, `3_DieuChuyen`, `4_KiemKe`,
`5_PhanQuyen` (app tự nhận các tên này). Nhớ **xóa dòng mẫu**.

## Bước 7 – Điền Secrets trên Streamlit

Streamlit → app → **⋮ → Settings → Secrets**, thay toàn bộ nội dung bằng:

```toml
[app]
admin_emails = ["it.stp@igcschool.edu.vn"]

[powerautomate]
flow_url = "<HTTP URL copy ở bước 5>"
key = "<mã bí mật ở bước 1>"
```

**Không** cần mục `[auth]` và `[sharepoint]` ở chế độ này (xóa đi nếu có). Bấm **Save**.

## Bước 8 – Kiểm tra

1. Mở app → nhập email `it.stp@igcschool.edu.vn` → **Gửi mã** → mở hộp thư lấy mã 6 số → **Đăng nhập**.
2. Vào **Phân quyền → Kết nối SharePoint** → bấm **Kiểm tra truy cập site và các list** (5 list phải ✅)
   → **Ghi thử 1 dòng** → **Gửi thử email cho tôi**.
3. Vào **Phân quyền → Phân quyền admin** thêm email giáo viên / ban kiểm kê / BGH (hoặc gán người quản lý phòng)
   – chỉ những email này đăng nhập được.

## Lưu ý

- Sau khi đăng nhập, app lưu phiên trong **trình duyệt** (localStorage + cookie) 7 ngày (`[app] session_days`): tải lại trang, đóng/mở
  lại trình duyệt vẫn còn đăng nhập. Bấm **Đăng xuất**, xóa dữ liệu duyệt web, hoặc dùng cửa sổ ẩn danh thì phải nhập lại mã.
- Mọi thay đổi trên SharePoint hiển thị người sửa là **chủ flow** (bạn). App vẫn ghi người thao tác vào các cột
  như *Người thực hiện*, *Người kiểm kê*, *Người xác nhận*.
- Người dùng **không cần** quyền trên site SharePoint – chỉ chủ flow cần.
- Mỗi lần app đọc/ghi = 1 lần chạy flow (khoảng 1–2 giây). App tải các list **song song**, giữ dữ liệu
  10 phút (`[app] cache_minutes`), sau khi ghi chỉ tải lại đúng list vừa ghi, và ghi hàng loạt 6 yêu cầu song song.
  Nếu sửa dữ liệu trực tiếp trên SharePoint, bấm **Làm mới** ở thanh bên để app thấy ngay. Gói Premium cho phép hàng chục nghìn lần chạy mỗi ngày – đủ dùng.
- Nếu flow bị tắt, hết hạn Premium, hoặc bạn đổi mật khẩu làm hỏng kết nối SharePoint/Outlook trong flow, app sẽ
  báo lỗi kết nối – vào flow sửa kết nối (Connections) là chạy lại.
- **Nhập nhiều dòng bị chậm / Power Automate gửi mail "flow(s) have failed":** mỗi dòng ghi là 1 lần chạy flow;
  dòng nào SharePoint từ chối (sai kiểu dữ liệu, cột không tồn tại...) thì lần chạy đó bị đánh dấu *Failed* – app
  vẫn nhận lỗi và liệt kê ở cuối. Mở **Run history** của flow, bấm vào lần chạy Failed, xem bước
  *Send an HTTP request to SharePoint* để biết lý do. Để flow không treo lâu khi SharePoint bận: bấm **…** của bước
  *Send an HTTP request to SharePoint* → **Settings** → **Retry policy** chọn **None** (app tự thử lại khi bị giới
  hạn tốc độ). Nếu lỗi liên tiếp 10 dòng, app tự dừng; sửa xong nhập lại file – các dòng đã ghi được bỏ qua.
- Lỗi thường gặp trên trang Kết nối SharePoint:
  - `403 … key` → key trong Secrets khác key trong flow (bước 3).
  - `404 Không tìm thấy list` → sai tên list hoặc site ở bước "Send an HTTP request to SharePoint".
  - `400/502` khi ghi → xem chi tiết lỗi; thường do Method chưa đặt *custom value* hoặc chưa bật *has failed* ở
    Response.
