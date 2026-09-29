# Campus Coin

Campus Coin is a small student finance web app made with Django. The main idea is pretty simple: help students record income/expenses, understand where their money goes, and get a few useful warnings or AI-assisted suggestions without making the app too complicated.

This project was built as a school/TechWiz project, so some parts are made for demo and learning purposes, but the main flows are working end-to-end.

## What the project can do

### Student side

- Register, login and logout with email
- Forgot/reset password by email
- Edit personal profile, avatar, monthly allowance and savings goal
- View and revoke active login sessions
- Add, edit and delete personal transactions
- Search/filter transactions by description, category, type, amount and date
- Get AI category suggestions when entering a transaction
- Import many transactions from CSV, review them first, then confirm the import
- View finance reports with income, expense, balance and category breakdown
- View charts for different report periods
- Receive in-app notifications and email notifications
- Use the finance assistant to ask about spending, budget, savings, recent transactions, etc.

### Admin side

- Separate admin login/dashboard
- Manage users and account status
- Create, edit and delete transaction categories
- View/search transactions from users
- Send password reset email to a user
- Access Django Admin when needed

## AI parts

There are two different AI-related parts in the project.

**Transaction category classifier** works locally using `scikit-learn` (TF-IDF + similarity). It learns from the final category selected by the user, so an external AI API is not required for this part.

**Finance Assistant** can use Groq through an OpenAI-compatible API when `GROQ_API_KEY` is configured. It can use Campus Coin data/tools to answer questions about spending, balance, affordability, savings, reports and how the app works. If the external AI is not configured, the project still has a fallback finance engine for supported questions.

## CSV import

CSV import uses this format:

```csv
type,category,amount,description,date
expense,,45000,Lunch at cafeteria,2026-09-25
income,,1500000,Part-time job payment,2026-09-24
```

`category` can be left blank so the classifier can suggest one.

The imported rows are not saved directly as final transactions. They first go to a preview/staging screen where the student can fix the data before confirming.

## Reports and notifications

Reports currently support common periods such as today, last 7 days, this month, 3 months and 6 months. The report page includes totals, transaction count, category information and Chart.js charts.

Notifications can include:

- Weekly finance summary
- Monthly finance summary
- Savings goal warning
- Low balance warning

The notification command should be run regularly if you want automatic summaries:

```bash
py manage.py process_notifications
```

For a local demo it can be scheduled once per day using Windows Task Scheduler.

## Tech stack

- Python / Django 5.2
- MySQL (default) or SQLite for quick testing
- HTML, CSS and JavaScript
- Chart.js
- scikit-learn
- Django Channels
- Redis / Channels Redis (optional, useful for production or multiple workers)
- SMTP/Gmail for email
- Groq API for the optional LLM assistant

The project was developed/tested with Python 3.13, but a recent supported Python version should be fine as long as the packages in `requirements.txt` install correctly.

## Project structure

```text
source_code/
├── accounts/              # login, register, profile, sessions, admin accounts
├── transactions/          # transactions, categories, AI classifier, CSV import
├── finance_assistant/     # chatbot / finance assistant
├── report/                # financial report dashboard
├── notifications/         # in-app + email notifications
├── config/                # Django settings, urls, ASGI/WSGI, public URL helper
├── database/              # sample/training SQL and CSV data
├── get_data/              # additional sample data
├── static/
├── templates/
├── media/
├── manage.py
└── requirements.txt
```

## Run the project locally

### 1. Create a virtual environment

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Windows CMD:

```bat
python -m venv .venv
.venv\Scripts\activate
```

### 2. Install packages

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 3. Create your environment file

The repository contains `.env.txt` as a sample. Copy it to `.env` and put your local/private settings there.

PowerShell:

```powershell
Copy-Item .env.txt .env
```

`.env` is already ignored by Git, so API keys and email passwords should stay there and should not be pushed to GitHub.

A simple local setup can look like this:

```env
SECRET_KEY=change-this-for-your-machine
DEBUG=True
ALLOWED_HOSTS=127.0.0.1,localhost

DB_ENGINE=mysql
DB_NAME=campus_coin
DB_USER=root
DB_PASSWORD=your_mysql_password
DB_HOST=127.0.0.1
DB_PORT=3306

PUBLIC_BASE_URL=auto
AUTO_BASE_URL_SCHEME=http
AUTO_BASE_URL_PORT=8000

GROQ_API_KEY=
GROQ_MODEL=openai/gpt-oss-120b
```

If you just want to test the project quickly and do not want to configure MySQL yet:

```env
DB_ENGINE=sqlite
```

### 4. MySQL database (skip this when using SQLite)

Create the database first:

```sql
CREATE DATABASE campus_coin
CHARACTER SET utf8mb4
COLLATE utf8mb4_unicode_ci;
```

Then make sure the MySQL username/password in `.env` are correct.

### 5. Run migrations

```bash
py manage.py migrate
py manage.py check
```

### 6. Create an admin account

```bash
py manage.py create_admin_account
```

or use Django's normal command:

```bash
py manage.py createsuperuser
```

There is also a demo-account command for local testing:

```bash
py manage.py create_demo_accounts
```

Do not use demo/default passwords on a real public deployment.

### 7. Start the server

```bash
py manage.py runserver
```

Open:

```text
http://127.0.0.1:8000/
```

Student login:

```text
/account/login/
```

Admin login:

```text
/account/admin-account/login/
```

Django Admin:

```text
/django-admin/
```

## Run on another device in the same Wi-Fi/LAN

Start Django like this:

```bash
py manage.py runserver 0.0.0.0:8000
```

Then open the computer's LAN IP from the other device, for example:

```text
http://172.16.2.89:8000/
```

Make sure that IP is allowed in `ALLOWED_HOSTS` (or temporarily use `ALLOWED_HOSTS=*` for a local demo) and allow port 8000 through Windows Firewall if needed.

`0.0.0.0` is only the address Django listens on. Other devices still connect using the real LAN IP of the computer.

## Email setup

Password reset, reports and notifications can send email through SMTP.

For Gmail, use a Google **App Password**, not your normal Gmail password.

Example `.env`:

```env
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_HOST_USER=your_email@gmail.com
EMAIL_HOST_PASSWORD=your_google_app_password
EMAIL_USE_TLS=True
EMAIL_USE_SSL=False
DEFAULT_FROM_EMAIL=Campus Coin <your_email@gmail.com>
PUBLIC_BASE_URL=auto
```

Test email with:

```bash
py manage.py test_email receiver@example.com
```

If you do not want real email while developing, use:

```env
EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend
```

Then the email content will be printed in the terminal.

## Groq assistant setup (optional)

Put the key in your private `.env`:

```env
GROQ_API_KEY=your_key_here
GROQ_MODEL=openai/gpt-oss-120b
GROQ_BASE_URL=https://api.groq.com/openai/v1
GROQ_TIMEOUT=20
GROQ_MAX_OUTPUT_TOKENS=900
GROQ_REASONING_EFFORT=medium
```

Then test the connection:

```bash
py manage.py check_ai
```

The local transaction-category classifier does **not** need this API key.

## Public deployment / tunnel note

For a real domain or public tunnel, do not leave production settings as the local defaults.

At minimum:

```env
DEBUG=False
ALLOWED_HOSTS=your-domain.example
PUBLIC_BASE_URL=https://your-domain.example
```

Also use a strong `SECRET_KEY`, keep credentials outside Git, configure HTTPS, and use a proper production WSGI/ASGI server instead of Django's development `runserver`.

## Useful files already included

There are a few extra notes/data files in the repository if you need them:

- `SETUP.md`
- `CSV_IMPORT_AND_EMAIL_GUIDE.md`
- `NOTIFICATIONS_GUIDE.md`
- `README_AI_REPORT.md`
- `database/sample_transactions_import.csv`
- `database/ai_training_from_excel.sql`

## Before pushing to GitHub

The `.gitignore` already excludes the main local/private files, but it is still worth checking before every push.

Do not commit:

```text
.env
.venv/
.idea/
db.sqlite3
uploaded media files
real API keys
real email/app passwords
```

If a secret was committed before, removing it from the latest file is not enough. Revoke/rotate that key as well.

## Small note

This is still a student project, so there may be parts that can be cleaned up or improved later. The goal for now is to keep the main Campus Coin flow understandable and working: account -> transactions -> AI/category help -> reports -> notifications -> finance assistant.

