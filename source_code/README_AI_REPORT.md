# Campus Coin - AI phân loại giao dịch + Report

## Đã nâng cấp

### 1. AI tự đoán danh mục ngay trong Transaction
- Người dùng chọn **Thu/Chi** và nhập **Mô tả**.
- Front-end gọi `/transactions/ajax/ai-predict/` và hiển thị danh mục AI đề xuất + độ tương đồng.
- Khi bấm **Lưu giao dịch**, server tự dự đoán lại để tránh phụ thuộc vào dữ liệu từ trình duyệt.
- Nếu danh mục người dùng giữ nguyên = AI dự đoán đúng.
- Nếu người dùng đổi sang danh mục khác = AI dự đoán sai.
- Cả hai trường hợp đều được ghi nhận thành `AITrainingExample`, vì câu mô tả + danh mục cuối cùng là dữ liệu học hợp lệ.
- Giao dịch lưu thêm:
  - `ai_suggested_category`
  - `ai_prediction_confidence`
  - `ai_prediction_correct`
  - `ai_feedback_at`

### 2. Không đọc Excel lúc chạy app
Excel chỉ còn là nguồn dữ liệu migration ban đầu. Runtime không gọi `pandas.read_excel()`.

Dữ liệu 2,359 dòng trong Excel đã được chuyển thành SQL:
`database/ai_training_from_excel.sql`

Chạy sau khi đã tạo database và migrate:
```sql
USE campus_coin;
SOURCE database/ai_training_from_excel.sql;
```

File SQL:
- tạo các category còn thiếu
- chuyển toàn bộ 2,359 dòng training
- giữ cả trường `In / Out` gốc qua `source_direction`
- đánh dấu nguồn là `excel`

### 3. Report
Route:
`/report/`

Có các khoảng:
- Hôm nay
- 7 ngày
- Tháng
- 3 tháng
- 6 tháng

Có:
- Tổng thu
- Tổng chi
- Số dư
- Số giao dịch
- Chi tiết từng danh mục thu
- Chi tiết từng danh mục chi
- Line chart song song Thu/Chi theo thời gian

## Cài thêm dependency

```bash
pip install -r requirements.txt
```

Dependency mới:
`scikit-learn==1.8.0`

## Migration

```bash
python manage.py makemigrations
python manage.py migrate
```

Migration đã có sẵn trong:
`transactions/migrations/0002_ai_feedback.py`

## Thứ tự triển khai dữ liệu

1. Tạo database MySQL `campus_coin`.
2. Cấu hình `.env`.
3. `python manage.py migrate`
4. Import `database/ai_training_from_excel.sql`.
5. Chạy server:
```bash
python manage.py runserver
```

## Lưu ý AI

Model hiện tại là TF-IDF ký tự + cosine similarity. Đây là lựa chọn nhẹ, chạy local và không cần API AI bên ngoài. Quan trọng hơn, dữ liệu học nằm trong MySQL nên không phụ thuộc Excel.

Khi người dùng sửa một dự đoán, câu mô tả và category cuối cùng được lưu vào database với `source='user_feedback'`; lần dự đoán sau classifier sẽ tự đọc thêm dữ liệu này.
