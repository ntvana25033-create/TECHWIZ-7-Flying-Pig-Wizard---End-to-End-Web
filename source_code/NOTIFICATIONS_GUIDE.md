# Campus Coin Notifications

## What the app creates

The `notifications` app stores every user notification in its own database table and can also send the same information by email.

Notification types:

- Weekly finance summary: generated on Sunday.
- Monthly finance summary: generated on the last calendar day of the month.
- Savings goal warning: generated when estimated remaining monthly funds are close to or below the student's `monthly_savings_goal`.
- Low balance warning: generated when estimated remaining monthly funds are at or below 10% of the funds available for the month.

For threshold alerts, available monthly funds are calculated as:

`monthly_allowance + recorded monthly income`

and estimated remaining funds are:

`available monthly funds - recorded monthly expenses`

Each warning type is de-duplicated per student per month, so repeated requests do not spam the same alert. If email delivery fails, the in-app notification stays in the database and a later run can retry the email.

## URLs

Notification Center:

`http://127.0.0.1:8000/notifications/`

Reports:

`http://127.0.0.1:8000/report/`

## Database migration

After replacing the source code, run:

```powershell
py manage.py migrate
py manage.py check
```

The migration creates the `notifications_notification` table.

## Automatic scheduled summaries

Django does not run calendar jobs by itself. Campus Coin includes this management command:

```powershell
py manage.py process_notifications
```

Run it once every day, preferably in the evening. The command automatically decides whether the current date is Sunday or the end of the month. It also checks threshold warnings.

A helper file is included:

`run_notifications.bat`

On Windows Task Scheduler, create a Basic Task that runs daily and points to this `.bat` file. A daily run at 20:00 is a simple choice for a local/student deployment.

For testing without waiting for Sunday or month-end:

```powershell
py manage.py process_notifications --force-weekly
py manage.py process_notifications --force-monthly
```

To create in-app notifications without sending email:

```powershell
py manage.py process_notifications --force-weekly --no-email
```

To test a specific date:

```powershell
py manage.py process_notifications --date 2026-09-27
py manage.py process_notifications --date 2026-09-30
```

## Email configuration

The notification app uses the same SMTP settings as password reset. Configure `.env`:

```env
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_HOST_USER=your_email@gmail.com
EMAIL_HOST_PASSWORD=your_google_app_password
EMAIL_USE_TLS=True
EMAIL_USE_SSL=False
DEFAULT_FROM_EMAIL=Campus Coin <your_email@gmail.com>
PUBLIC_BASE_URL=http://127.0.0.1:8000
```

Use a Google App Password, not the normal Gmail password.

You can test SMTP first with:

```powershell
py manage.py test_email your_receiver@gmail.com
```

The email body includes income, expenses, remaining balance, and a link back to Campus Coin.
