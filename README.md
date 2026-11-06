# Cinema Hall & Canteen POS System

A full-stack Point of Sale (POS) application built with **Django and MySQL** to manage cinema ticketing, canteen inventory, billing, expenses, and business reporting.

The system brings cinema operations and canteen sales together in one application, with account management, inventory tracking, checkout, and administrative tools.

## Features

### Authentication and Security
- User registration, login, and logout
- Email verification and password recovery
- Password validation and protected user sessions
- Login-attempt protection with Django Axes
- Environment-based application configuration

### Cinema Management
- Movie and show management
- Gold and Silver seating sections
- Seat selection and booking
- Cinema ticket generation and billing
- Ticket pricing and tax breakdown

### Inventory and Canteen
- Product and category management
- Product barcode support
- Stock and availability management
- Low-stock monitoring
- Product search and checkout workflow

### Billing and Sales
- Point of Sale checkout
- Shopping cart and invoice generation
- Multiple payment methods
- VAT calculation and payment tracking
- Invoice printing and reprinting
- Sales history and reporting

### Expenses and Administration
- Expense and expense-category management
- Operational cost tracking
- Dashboard summaries and notifications
- Django administration interface powered by Jazzmin

## Technology Stack

| Area | Technology |
|---|---|
| Backend | Python, Django 6 |
| Database | MySQL |
| Database driver | mysqlclient |
| Frontend | Django Templates, Tailwind CSS |
| Admin interface | django-jazzmin |
| Authentication protection | django-axes |
| Environment configuration | python-decouple |
| Images and documents | Pillow, ReportLab |
| Barcode and QR support | python-barcode, qrcode, django-qr-code |

## Project Structure

```text
POS/
├── accounts/       # Authentication and user accounts
├── billing/        # Checkout, invoices, customers and expenses
├── cinema/         # Movies, shows, seats and ticketing
├── inventory/      # Products, categories and stock
├── pos/            # POS application functionality
├── sales/          # Sales operations and reporting
├── core/           # Django settings and URL configuration
├── templates/      # Shared application templates
├── static/         # Static assets
├── media/          # User-uploaded media (local)
├── .env.example    # Environment variable template
├── manage.py
└── requirements.txt
```

## Local Installation

### 1. Clone the repository

```bash
git clone https://github.com/govindarokaya97/POS.git
cd POS
```

### 2. Create a virtual environment

**Windows PowerShell:**

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

**macOS / Linux:**

```bash
python -m venv venv
source venv/bin/activate
```

### 3. Install dependencies

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Configure environment variables

Copy the example configuration:

**Windows PowerShell:**

```powershell
Copy-Item .env.example .env
```

**macOS / Linux:**

```bash
cp .env.example .env
```

Edit `.env` and configure your own secret key, database credentials, and email settings.

Example:

```env
SECRET_KEY=your-generated-secret-key
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1

DB_NAME=your_database_name
DB_USER=your_database_user
DB_PASSWORD=your_database_password
DB_HOST=127.0.0.1
DB_PORT=3306

EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_HOST_USER=your-email@gmail.com
EMAIL_HOST_PASSWORD=your-email-app-password
DEFAULT_FROM_EMAIL=your-email@gmail.com
```

Never commit your actual `.env` file or share its secrets.

### 5. Create the MySQL database

Create a database in MySQL using the same name configured in `DB_NAME`.

```sql
CREATE DATABASE your_database_name
CHARACTER SET utf8mb4
COLLATE utf8mb4_unicode_ci;
```

Make sure the configured MySQL user has permission to access this database.

### 6. Apply migrations

```bash
python manage.py migrate
```

### 7. Create an administrator account

```bash
python manage.py createsuperuser
```

### 8. Start the development server

```bash
python manage.py runserver
```

Open the application at:

- Application: http://127.0.0.1:8000/
- Administration: http://127.0.0.1:8000/admin/

## Useful Development Commands

```bash
# Check Django configuration
python manage.py check

# Display migration status
python manage.py showmigrations

# Run tests
python manage.py test

# Collect static files
python manage.py collectstatic
```

## Security Notes

- Keep `SECRET_KEY`, database passwords, and email credentials outside source control.
- Use `DEBUG=False` in production.
- Configure valid production hosts and HTTPS before enabling secure-cookie and HSTS settings.
- Keep dependencies updated.
- Protect database backups and uploaded customer or business data.
- Do not use the Django development server for production hosting.

See [SECURITY.md](SECURITY.md) for the project's security policy.

## Project Status

This project is under active development. Features, automated tests, deployment configuration, and documentation are being improved incrementally.

## License

All rights reserved. No permission is granted to redistribute or commercially use this project without authorization from the project owner.