# Campus Coin - Quick Setup

## 1. Create a virtual environment

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

## 2. Install dependencies

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## 3. Configure the environment

Copy `.env.example` to `.env`, then update the MySQL settings.

You can quickly run the project with SQLite for testing by setting:

```env
DB_ENGINE=sqlite
```

## 4. Create database tables

```bash
python manage.py migrate
```

## 5. Create an Admin account

Recommended method: enter the password directly in the terminal:

```bash
python manage.py create_admin_account
```

Or provide the email and name:

```bash
python manage.py create_admin_account --email admin@example.com --name "Campus Coin Admin"
```

Django also supports the default command:

```bash
python manage.py createsuperuser
```

## 6. Run the project

```bash
python manage.py runserver
```

Users sign in at `/account/login/`.

Admins sign in at `/account/admin-account/login/`.

Django Admin is available at `/django-admin/`.

## Transactions app permissions

- STUDENT users can only view, create, edit, and delete their own transactions.
- STUDENT users cannot access `/transactions/manage/...` URLs.
- ADMIN users can manage categories and view all transactions.
- ADMIN users do not use STUDENT personal transaction screens.
- The AJAX category API requires a signed-in STUDENT account.

## Profile pictures

Profile pictures are uploaded to `media/avatars/` through the Personal Profile page. The user can preview a selected image before saving it, replace the current picture, or remove it.

For local development, keep `DEBUG=True` so Django serves files from `MEDIA_ROOT` automatically. In production, configure the web server or storage service to serve `/media/` from the configured `MEDIA_ROOT`.
