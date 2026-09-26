# Campus Coin - CSV Import + Password Reset Email

## 1. Luồng import CSV

Mỗi sinh viên đăng nhập và mở:

`http://127.0.0.1:8000/transactions/import/csv/`

Luồng xử lý:

1. Upload CSV.
2. Hệ thống đọc tối đa 2.000 dòng/lần.
3. AI chạy dự đoán Category hàng loạt từ `description` + `type`.
4. Dữ liệu được lưu vào bảng staging của đúng sinh viên, chưa tạo Transaction thật.
5. Sinh viên sửa trực tiếp Type, Amount, Description, Date và Category ở bảng xem trước.
6. Chọn **Lưu và tiếp tục xác nhận**.
7. Trang xác nhận lần cuối hiển thị số dòng, tổng thu, tổng chi và phân bố Category.
8. Bấm **Xác nhận nhập vào hệ thống** mới tạo Transaction thật trong SQL.
9. Description + Category cuối cùng được dùng làm feedback cho AI. Mẫu trùng hoàn toàn không bị thêm lặp lại.

### Cột CSV

File mẫu có thể tải ngay trên trang import. Header chuẩn:

```csv
type,category,amount,description,date
expense,,45000,Mua cơm trưa,2026-09-25
income,,1500000,Nhận lương làm thêm,2026-09-24
```

- `type`: `income`, `expense`, `thu`, `chi`, `thu nhập`, `chi tiêu`.
- `category`: có thể để trống để AI tự gợi ý. Nếu có nhập thì phải trùng tên Category trong hệ thống và đúng Type.
- `amount`: số > 0.
- `description`: nội dung giao dịch; AI dựa chủ yếu vào trường này.
- `date`: khuyến nghị `YYYY-MM-DD`; cũng nhận `DD/MM/YYYY` và `DD-MM-YYYY`.

### Migration bắt buộc

Sau khi lấy source mới, chạy:

```powershell
py manage.py migrate
py manage.py check
py manage.py runserver
```

Migration `transactions/0003_transaction_import_staging.py` tạo hai bảng staging cho lô import và từng dòng import.

---

## 2. Gửi email khôi phục mật khẩu bằng Gmail/Google Workspace

Project đã có sẵn luồng reset password. Bạn chỉ cần cấu hình SMTP trong `.env`.

### Bước A - tạo App Password

Không dùng mật khẩu đăng nhập Gmail thông thường. Với tài khoản Google cho phép App Password:

1. Bật xác minh 2 bước (2-Step Verification) cho tài khoản Google.
2. Mở phần **App passwords** của tài khoản Google.
3. Tạo một App Password cho Campus Coin.
4. Google cấp một mã riêng. Dùng mã này cho `EMAIL_HOST_PASSWORD`.

Nếu tài khoản trường/Google Workspace không cho tạo App Password thì quản trị viên có thể đã tắt tính năng này. Khi đó dùng một tài khoản Gmail khác được phép App Password hoặc cấu hình SMTP do trường cung cấp.

### Bước B - cấu hình `.env`

```env
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_HOST_USER=your_google_email@gmail.com
EMAIL_HOST_PASSWORD=your_app_password
EMAIL_USE_TLS=True
EMAIL_USE_SSL=False
EMAIL_TIMEOUT=20
DEFAULT_FROM_EMAIL=Campus Coin <your_google_email@gmail.com>
PUBLIC_BASE_URL=http://127.0.0.1:8000
```

Không thêm khoảng trắng sau dấu `=`. Không commit/chia sẻ file `.env` có App Password.

`DEFAULT_FROM_EMAIL` nên dùng cùng địa chỉ với `EMAIL_HOST_USER` để Gmail không từ chối hoặc thay đổi người gửi.

### Test luồng reset mà chưa cần Gmail (tùy chọn)

Nếu chỉ muốn kiểm tra chức năng trước, tạm đặt:

```env
EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend
```

Khi bấm Forgot Password, nội dung email và link reset sẽ in ngay trong terminal đang chạy Django. Sau khi test xong, đổi lại SMTP backend để gửi email thật.

### Bước C - test SMTP trước

Chạy:

```powershell
py manage.py test_email your_receiver@gmail.com
```

Nếu thành công sẽ thấy:

`EMAIL SENT OK`

### Bước D - test chức năng quên mật khẩu

Trang sinh viên:

`http://127.0.0.1:8000/account/forgot-password/`

1. Nhập email của Student đã tồn tại trong database.
2. Campus Coin tạo token reset có thời hạn 30 phút.
3. Email nhận được nút **Reset Password**.
4. Bấm link để vào `/account/reset-password/<token>/`.
5. Nhập mật khẩu mới.
6. Token bị đánh dấu đã dùng và các session cũ của user bị revoke.

Admin có trang riêng:

`http://127.0.0.1:8000/account/admin-account/forgot-password/`

### Lưu ý khi demo local

`PUBLIC_BASE_URL=http://127.0.0.1:8000` chỉ mở được nếu trình duyệt bấm link đang chạy trên chính máy có Django server. Khi deploy thật, đổi thành domain thực, ví dụ:

```env
PUBLIC_BASE_URL=https://campuscoin.example.com
```

Sau mỗi lần sửa `.env`, dừng và chạy lại `py manage.py runserver`.
