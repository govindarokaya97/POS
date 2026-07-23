# For Small Shops — POS System

A Django-based Point of Sale (POS) system built for **small business**.


## Features

- 🔐 **Accounts** — custom login/register/logout with a staff dashboard
- 📦 **Inventory management** — categories and products, stock tracking, low-stock alerts
- 📊 **Dashboard** — quick overview of categories, products, sales, and revenue
- 🎛️ **Django admin** — customized with Jazzmin for a cleaner admin UI

## Tech stack

- **Backend:** Django 6
- **Database:** MySQL (via `mysqlclient`)
- **Admin UI:** django-jazzmin
- **Images:** Pillow
- **Frontend:** Django templates + Tailwind CSS (via CDN), Font Awesome, SweetAlert2

## Project structure

```
POS/
├── accounts/       # Auth, dashboard
├── inventory/      # Categories & products
├── sales/          # Point of sale, sales history
├── core/           # Project settings, root URLs
├── templates/      # Shared base template, sidebar
├── static/         # CSS, images (logo)
├── media/          # Uploaded product images
└── manage.py
```

## Setup

1. **Clone and enter the project**
   ```bash
   git clone <this-repo-url>
   cd POS
   ```

2. **Create and activate a virtual environment**
   ```bash
   python -m venv env
   # Windows
   env\Scripts\activate
   # macOS/Linux
   source env/bin/activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure the database**

   Create a MySQL database (default name used in `core/settings.py` is `mini_project_db`), then update the credentials in `core/settings.py` under `DATABASES` if needed:
   ```python
   DATABASES = {
       'default': {
           'ENGINE': 'django.db.backends.mysql',
           'NAME': 'mini_project_db',
           'USER': 'root',
           'PASSWORD': '<your-password>',
           'HOST': 'localhost',
           'PORT': '3306',
       }
   }
   ```

5. **Run migrations**
   ```bash
   python manage.py migrate
   ```

6. **Create an admin/superuser account**
   ```bash
   python manage.py createsuperuser
   ```

7. **Run the development server**
   ```bash
   python manage.py runserver
   ```

8. Visit `http://127.0.0.1:8000/` to log in, and `http://127.0.0.1:8000/admin/` for the admin panel.

## Usage

- Add **categories** and **products** under Inventory before ringing up sales.
- Go to **Sales → New sale** to check out a customer:
- View past transactions from **Sales → History**.

## Notes

- `DEBUG = True` and the `SECRET_KEY` in `core/settings.py` are for local development only — do not use these as-is in production.
- Logs are written to `logs/app.log` (rotating) as well as the console.

## License

Internal project — all rights reserved by POS.
