# Campus Coin - AI Classification, CSV Import, Reports, and Notifications

Campus Coin supports database-backed AI transaction categorization, user feedback training, bulk CSV import with staging review, financial reports, and stored/email notifications.

## AI classification

- The user selects Income/Expense and enters a Description.
- The browser requests an AI category suggestion without training the model.
- Only the final saved Description + Category becomes feedback training data.
- CSV imports use the same classifier in bulk and only train after final confirmation.

## Reports

Available report periods: Today, Last 7 days, This month, 3 months, and 6 months.

Reports show total income, total expenses, balance, transaction count, category breakdowns, and an income/expense trend chart.

## Notifications

The `notifications` app stores weekly summaries, monthly summaries, savings-goal warnings, and low-balance warnings in its own table and can email the same information. See `NOTIFICATIONS_GUIDE.md`.

## Setup

```powershell
py manage.py migrate
py manage.py check
py manage.py runserver
```

For scheduled notifications, run `py manage.py process_notifications` once per day using Windows Task Scheduler or another scheduler.
