# Campus Coin - CSV Import and Password Reset Email

## CSV import workflow

Student URL:

`http://127.0.0.1:8000/transactions/import/csv/`

Workflow:

1. Upload a UTF-8 CSV file.
2. Campus Coin reads up to 2,000 rows per batch.
3. AI predicts Category in bulk from `description` + `type`.
4. Rows are stored in student-specific staging tables; no final Transaction is created yet.
5. The student reviews and directly edits Type, Amount, Description, Date, and Category.
6. Select **Save and continue to confirmation**.
7. The confirmation page shows row count, total income, total expenses, and category distribution.
8. Select **Confirm and import** to create final Transaction records.
9. The final Description + Category pair is used as AI feedback. Exact duplicate examples are not inserted again.

### CSV columns

```csv
type,category,amount,description,date
expense,,45000,Lunch at cafeteria,2026-09-25
income,,1500000,Part-time job payment,2026-09-24
```

- `type`: `income` or `expense`.
- `category`: optional. Leave blank to let AI suggest it.
- `amount`: a number greater than 0.
- `description`: transaction text used by the AI classifier.
- `date`: recommended format `YYYY-MM-DD`; `DD/MM/YYYY` and `DD-MM-YYYY` are also accepted.

## Password reset email with Gmail

Campus Coin already includes password reset. For a private local setup, configure SMTP in a gitignored `.env` file (it overrides the public `env.txt`).

```env
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_HOST_USER=your_email@gmail.com
EMAIL_HOST_PASSWORD=your_google_app_password
EMAIL_USE_TLS=True
EMAIL_USE_SSL=False
EMAIL_TIMEOUT=20
DEFAULT_FROM_EMAIL=Campus Coin <your_email@gmail.com>
PUBLIC_BASE_URL=auto
AUTO_BASE_URL_SCHEME=http
AUTO_BASE_URL_PORT=8000
```

Use a Google App Password rather than your normal Gmail password. Enable Google 2-Step Verification first, create an App Password, and put that value in `EMAIL_HOST_PASSWORD`.

`PUBLIC_BASE_URL=auto` makes email links use the LAN IPv4 address of the machine running Django. To let other devices on the same Wi-Fi/LAN open those links, start Django with `py manage.py runserver 0.0.0.0:8000` and allow the LAN host in `ALLOWED_HOSTS` (for a temporary local demo, `ALLOWED_HOSTS=*` is acceptable).

For production or a public tunnel/domain, do not use auto detection. Set a fixed value instead, for example `PUBLIC_BASE_URL=https://your-domain.example`. Devices outside the same LAN cannot reach a private `192.168.x.x`/`10.x.x.x` address.

Test SMTP:

```powershell
py manage.py test_email receiver@example.com
```

Student password recovery page:

`http://127.0.0.1:8000/account/forgot-password/`

For local testing without real email, use:

```env
EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend
```

The reset email will be printed in the Django terminal.
