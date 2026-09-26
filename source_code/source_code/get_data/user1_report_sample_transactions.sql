-- CampusCoin sample transaction data for REPORT testing
-- Target: user_id = 1
-- MySQL / MariaDB
-- Generated for September 2026 report visualization

USE campus_coin;

START TRANSACTION;

-- Ensure useful categories exist.
INSERT INTO transactions_category (name, type)
SELECT 'Allowance', 'income' FROM DUAL
WHERE NOT EXISTS (
    SELECT 1 FROM transactions_category WHERE name='Allowance' AND type='income'
);

INSERT INTO transactions_category (name, type)
SELECT 'Part-time Job', 'income' FROM DUAL
WHERE NOT EXISTS (
    SELECT 1 FROM transactions_category WHERE name='Part-time Job' AND type='income'
);

INSERT INTO transactions_category (name, type)
SELECT 'Scholarship', 'income' FROM DUAL
WHERE NOT EXISTS (
    SELECT 1 FROM transactions_category WHERE name='Scholarship' AND type='income'
);

INSERT INTO transactions_category (name, type)
SELECT 'Gift', 'income' FROM DUAL
WHERE NOT EXISTS (
    SELECT 1 FROM transactions_category WHERE name='Gift' AND type='income'
);

INSERT INTO transactions_category (name, type)
SELECT 'Food', 'expense' FROM DUAL
WHERE NOT EXISTS (
    SELECT 1 FROM transactions_category WHERE name='Food' AND type='expense'
);

INSERT INTO transactions_category (name, type)
SELECT 'Transport', 'expense' FROM DUAL
WHERE NOT EXISTS (
    SELECT 1 FROM transactions_category WHERE name='Transport' AND type='expense'
);

INSERT INTO transactions_category (name, type)
SELECT 'Academics', 'expense' FROM DUAL
WHERE NOT EXISTS (
    SELECT 1 FROM transactions_category WHERE name='Academics' AND type='expense'
);

INSERT INTO transactions_category (name, type)
SELECT 'Entertainment', 'expense' FROM DUAL
WHERE NOT EXISTS (
    SELECT 1 FROM transactions_category WHERE name='Entertainment' AND type='expense'
);

INSERT INTO transactions_category (name, type)
SELECT 'Hostel/Rent', 'expense' FROM DUAL
WHERE NOT EXISTS (
    SELECT 1 FROM transactions_category WHERE name='Hostel/Rent' AND type='expense'
);

INSERT INTO transactions_category (name, type)
SELECT 'Subscriptions', 'expense' FROM DUAL
WHERE NOT EXISTS (
    SELECT 1 FROM transactions_category WHERE name='Subscriptions' AND type='expense'
);

INSERT INTO transactions_category (name, type)
SELECT 'Miscellaneous', 'expense' FROM DUAL
WHERE NOT EXISTS (
    SELECT 1 FROM transactions_category WHERE name='Miscellaneous' AND type='expense'
);

-- Clean only this demo dataset so the script can be run repeatedly without duplicates.
DELETE FROM transactions_transaction
WHERE user_id = 1
  AND description LIKE '[REPORT-DEMO]%';

-- Historical rows for 3-month / 6-month charts.
INSERT INTO transactions_transaction
(user_id, category_id, amount, type, description, ai_suggested_category_id, date,
 ai_prediction_confidence, ai_prediction_correct, ai_feedback_at, created_at)
VALUES
(1, (SELECT id FROM transactions_category WHERE name='Allowance' AND type='income' LIMIT 1), 3000000.00, 'income', '[REPORT-DEMO] Trợ cấp tháng 7 từ gia đình', NULL, '2026-07-03', NULL, NULL, NULL, NOW()),
(1, (SELECT id FROM transactions_category WHERE name='Food' AND type='expense' LIMIT 1), 850000.00, 'expense', '[REPORT-DEMO] Ăn uống tháng 7', NULL, '2026-07-10', NULL, NULL, NULL, NOW()),
(1, (SELECT id FROM transactions_category WHERE name='Hostel/Rent' AND type='expense' LIMIT 1), 1800000.00, 'expense', '[REPORT-DEMO] Tiền trọ tháng 7', NULL, '2026-07-15', NULL, NULL, NULL, NOW()),
(1, (SELECT id FROM transactions_category WHERE name='Part-time Job' AND type='income' LIMIT 1), 2200000.00, 'income', '[REPORT-DEMO] Lương làm thêm tháng 7', NULL, '2026-07-25', NULL, NULL, NULL, NOW()),

(1, (SELECT id FROM transactions_category WHERE name='Allowance' AND type='income' LIMIT 1), 3200000.00, 'income', '[REPORT-DEMO] Trợ cấp tháng 8 từ gia đình', NULL, '2026-08-02', NULL, NULL, NULL, NOW()),
(1, (SELECT id FROM transactions_category WHERE name='Academics' AND type='expense' LIMIT 1), 950000.00, 'expense', '[REPORT-DEMO] Mua sách và tài liệu tháng 8', NULL, '2026-08-07', NULL, NULL, NULL, NOW()),
(1, (SELECT id FROM transactions_category WHERE name='Food' AND type='expense' LIMIT 1), 1100000.00, 'expense', '[REPORT-DEMO] Ăn uống tháng 8', NULL, '2026-08-14', NULL, NULL, NULL, NOW()),
(1, (SELECT id FROM transactions_category WHERE name='Part-time Job' AND type='income' LIMIT 1), 2600000.00, 'income', '[REPORT-DEMO] Lương làm thêm tháng 8', NULL, '2026-08-24', NULL, NULL, NULL, NOW()),
(1, (SELECT id FROM transactions_category WHERE name='Entertainment' AND type='expense' LIMIT 1), 620000.00, 'expense', '[REPORT-DEMO] Đi xem phim và vui chơi tháng 8', NULL, '2026-08-28', NULL, NULL, NULL, NOW());

-- September 2026: deliberately spread across many days for a readable monthly chart.
INSERT INTO transactions_transaction
(user_id, category_id, amount, type, description, ai_suggested_category_id, date,
 ai_prediction_confidence, ai_prediction_correct, ai_feedback_at, created_at)
VALUES
(1, (SELECT id FROM transactions_category WHERE name='Allowance' AND type='income' LIMIT 1), 3500000.00, 'income', '[REPORT-DEMO] Nhận trợ cấp đầu tháng từ gia đình', NULL, '2026-09-01', NULL, NULL, NULL, NOW()),
(1, (SELECT id FROM transactions_category WHERE name='Food' AND type='expense' LIMIT 1), 85000.00, 'expense', '[REPORT-DEMO] Ăn sáng và cà phê', NULL, '2026-09-01', NULL, NULL, NULL, NOW()),
(1, (SELECT id FROM transactions_category WHERE name='Transport' AND type='expense' LIMIT 1), 120000.00, 'expense', '[REPORT-DEMO] Đổ xăng xe máy', NULL, '2026-09-02', NULL, NULL, NULL, NOW()),
(1, (SELECT id FROM transactions_category WHERE name='Food' AND type='expense' LIMIT 1), 145000.00, 'expense', '[REPORT-DEMO] Ăn trưa cùng bạn', NULL, '2026-09-03', NULL, NULL, NULL, NOW()),
(1, (SELECT id FROM transactions_category WHERE name='Academics' AND type='expense' LIMIT 1), 450000.00, 'expense', '[REPORT-DEMO] Mua giáo trình học kỳ mới', NULL, '2026-09-04', NULL, NULL, NULL, NOW()),
(1, (SELECT id FROM transactions_category WHERE name='Food' AND type='expense' LIMIT 1), 90000.00, 'expense', '[REPORT-DEMO] Cơm tối', NULL, '2026-09-05', NULL, NULL, NULL, NOW()),
(1, (SELECT id FROM transactions_category WHERE name='Entertainment' AND type='expense' LIMIT 1), 280000.00, 'expense', '[REPORT-DEMO] Xem phim cuối tuần', NULL, '2026-09-06', NULL, NULL, NULL, NOW()),
(1, (SELECT id FROM transactions_category WHERE name='Part-time Job' AND type='income' LIMIT 1), 900000.00, 'income', '[REPORT-DEMO] Lương ca làm thêm tuần 1', NULL, '2026-09-07', NULL, NULL, NULL, NOW()),
(1, (SELECT id FROM transactions_category WHERE name='Transport' AND type='expense' LIMIT 1), 65000.00, 'expense', '[REPORT-DEMO] Gửi xe và xe buýt', NULL, '2026-09-08', NULL, NULL, NULL, NOW()),
(1, (SELECT id FROM transactions_category WHERE name='Food' AND type='expense' LIMIT 1), 175000.00, 'expense', '[REPORT-DEMO] Ăn uống trong ngày', NULL, '2026-09-09', NULL, NULL, NULL, NOW()),
(1, (SELECT id FROM transactions_category WHERE name='Subscriptions' AND type='expense' LIMIT 1), 79000.00, 'expense', '[REPORT-DEMO] Gia hạn ứng dụng học tập', NULL, '2026-09-10', NULL, NULL, NULL, NOW()),
(1, (SELECT id FROM transactions_category WHERE name='Academics' AND type='expense' LIMIT 1), 320000.00, 'expense', '[REPORT-DEMO] In tài liệu và mua văn phòng phẩm', NULL, '2026-09-11', NULL, NULL, NULL, NOW()),
(1, (SELECT id FROM transactions_category WHERE name='Food' AND type='expense' LIMIT 1), 115000.00, 'expense', '[REPORT-DEMO] Trà sữa và ăn vặt', NULL, '2026-09-12', NULL, NULL, NULL, NOW()),
(1, (SELECT id FROM transactions_category WHERE name='Gift' AND type='income' LIMIT 1), 500000.00, 'income', '[REPORT-DEMO] Được tặng tiền sinh nhật', NULL, '2026-09-13', NULL, NULL, NULL, NOW()),
(1, (SELECT id FROM transactions_category WHERE name='Hostel/Rent' AND type='expense' LIMIT 1), 1800000.00, 'expense', '[REPORT-DEMO] Thanh toán tiền trọ tháng 9', NULL, '2026-09-14', NULL, NULL, NULL, NOW()),
(1, (SELECT id FROM transactions_category WHERE name='Transport' AND type='expense' LIMIT 1), 135000.00, 'expense', '[REPORT-DEMO] Đổ xăng giữa tháng', NULL, '2026-09-15', NULL, NULL, NULL, NOW()),
(1, (SELECT id FROM transactions_category WHERE name='Part-time Job' AND type='income' LIMIT 1), 1250000.00, 'income', '[REPORT-DEMO] Lương ca làm thêm tuần 2', NULL, '2026-09-16', NULL, NULL, NULL, NOW()),
(1, (SELECT id FROM transactions_category WHERE name='Food' AND type='expense' LIMIT 1), 210000.00, 'expense', '[REPORT-DEMO] Ăn tối cùng nhóm đồ án', NULL, '2026-09-17', NULL, NULL, NULL, NOW()),
(1, (SELECT id FROM transactions_category WHERE name='Miscellaneous' AND type='expense' LIMIT 1), 160000.00, 'expense', '[REPORT-DEMO] Mua đồ dùng cá nhân', NULL, '2026-09-18', NULL, NULL, NULL, NOW()),
(1, (SELECT id FROM transactions_category WHERE name='Entertainment' AND type='expense' LIMIT 1), 350000.00, 'expense', '[REPORT-DEMO] Đi chơi cuối tuần', NULL, '2026-09-19', NULL, NULL, NULL, NOW()),
(1, (SELECT id FROM transactions_category WHERE name='Food' AND type='expense' LIMIT 1), 130000.00, 'expense', '[REPORT-DEMO] Ăn uống chủ nhật', NULL, '2026-09-20', NULL, NULL, NULL, NOW()),
(1, (SELECT id FROM transactions_category WHERE name='Scholarship' AND type='income' LIMIT 1), 2500000.00, 'income', '[REPORT-DEMO] Nhận học bổng hỗ trợ học tập', NULL, '2026-09-21', NULL, NULL, NULL, NOW()),
(1, (SELECT id FROM transactions_category WHERE name='Academics' AND type='expense' LIMIT 1), 650000.00, 'expense', '[REPORT-DEMO] Đóng phí khóa học bổ sung', NULL, '2026-09-22', NULL, NULL, NULL, NOW()),
(1, (SELECT id FROM transactions_category WHERE name='Transport' AND type='expense' LIMIT 1), 98000.00, 'expense', '[REPORT-DEMO] Chi phí đi lại', NULL, '2026-09-23', NULL, NULL, NULL, NOW()),
(1, (SELECT id FROM transactions_category WHERE name='Food' AND type='expense' LIMIT 1), 185000.00, 'expense', '[REPORT-DEMO] Ăn uống ngày 24', NULL, '2026-09-24', NULL, NULL, NULL, NOW()),
(1, (SELECT id FROM transactions_category WHERE name='Part-time Job' AND type='income' LIMIT 1), 1100000.00, 'income', '[REPORT-DEMO] Lương làm thêm cuối tháng', NULL, '2026-09-25', NULL, NULL, NULL, NOW()),
(1, (SELECT id FROM transactions_category WHERE name='Food' AND type='expense' LIMIT 1), 155000.00, 'expense', '[REPORT-DEMO] Ăn trưa và nước uống', NULL, '2026-09-25', NULL, NULL, NULL, NOW()),
(1, (SELECT id FROM transactions_category WHERE name='Transport' AND type='expense' LIMIT 1), 70000.00, 'expense', '[REPORT-DEMO] Gửi xe và di chuyển', NULL, '2026-09-26', NULL, NULL, NULL, NOW()),
(1, (SELECT id FROM transactions_category WHERE name='Entertainment' AND type='expense' LIMIT 1), 420000.00, 'expense', '[REPORT-DEMO] Đi xem phim và ăn uống', NULL, '2026-09-27', NULL, NULL, NULL, NOW()),
(1, (SELECT id FROM transactions_category WHERE name='Food' AND type='expense' LIMIT 1), 195000.00, 'expense', '[REPORT-DEMO] Ăn uống cuối tháng', NULL, '2026-09-28', NULL, NULL, NULL, NOW()),
(1, (SELECT id FROM transactions_category WHERE name='Miscellaneous' AND type='expense' LIMIT 1), 230000.00, 'expense', '[REPORT-DEMO] Mua vật dụng linh tinh', NULL, '2026-09-29', NULL, NULL, NULL, NOW()),
(1, (SELECT id FROM transactions_category WHERE name='Allowance' AND type='income' LIMIT 1), 1000000.00, 'income', '[REPORT-DEMO] Gia đình gửi thêm cuối tháng', NULL, '2026-09-30', NULL, NULL, NULL, NOW()),
(1, (SELECT id FROM transactions_category WHERE name='Food' AND type='expense' LIMIT 1), 125000.00, 'expense', '[REPORT-DEMO] Ăn tối cuối tháng', NULL, '2026-09-30', NULL, NULL, NULL, NOW());

COMMIT;

-- Verification queries
SELECT COUNT(*) AS demo_transaction_count
FROM transactions_transaction
WHERE user_id = 1 AND description LIKE '[REPORT-DEMO]%';

SELECT
    type,
    COUNT(*) AS transaction_count,
    SUM(amount) AS total_amount
FROM transactions_transaction
WHERE user_id = 1
  AND description LIKE '[REPORT-DEMO]%'
GROUP BY type;

SELECT
    DATE_FORMAT(date, '%Y-%m') AS month,
    type,
    SUM(amount) AS total_amount
FROM transactions_transaction
WHERE user_id = 1
  AND description LIKE '[REPORT-DEMO]%'
GROUP BY DATE_FORMAT(date, '%Y-%m'), type
ORDER BY month, type;
