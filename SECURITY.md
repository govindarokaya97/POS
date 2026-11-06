# Security Policy

## Overview

The Cinema Hall & Canteen POS System is a Django-based point-of-sale application designed to manage cinema ticket sales, canteen inventory, billing, expenses, and sales reporting.

Security is important to this project. We aim to protect user accounts, business information, transaction records, and application data.

## Supported Versions

Security updates are primarily provided for the latest maintained version.

| Version | Supported |
|---|---|
| Latest development version | Yes |
| Older versions | No guarantee |

## Security Features

The application incorporates the following security measures:

- **Authentication:** Django-based user authentication.
- **Registration Security:** Email verification for newly registered accounts.
- **Password Protection:** Django password hashing and password validation.
- **Password Recovery:** Secure password-reset links using Django's built-in authentication system.
- **Login Protection:** Django Axes to help protect against repeated failed login attempts.
- **CSRF Protection:** Django CSRF middleware and token validation.
- **Session Security:** Configurable secure session cookies for HTTPS deployments.
- **Environment Variables:** Sensitive configuration and credentials are stored outside source code.
- **Database Security:** MySQL integration with environment-based credentials.
- **Production Security:** Configurable HTTPS redirects, HSTS, and secure browser headers.

Security settings must be correctly configured for the deployment environment.

## Reporting a Vulnerability

If you discover a security vulnerability, please report it responsibly.

**Please do not publish sensitive vulnerability details in a public GitHub issue.**

Instead, report it privately through GitHub's private vulnerability reporting feature, if enabled for this repository, or contact the project maintainer through their GitHub profile.

Please include:

1. A clear description of the vulnerability.
2. Steps to reproduce the issue.
3. Potential security impact.
4. Screenshots or proof of concept, if applicable.
5. Suggested remediation, if known.

## Security Best Practices

Users and administrators should:

- Use strong and unique passwords.
- Never share account credentials.
- Keep application dependencies updated.
- Never commit `.env` files, passwords, API keys, or database credentials.
- Use HTTPS in production.
- Restrict access to administrative accounts.
- Maintain regular database backups.
- Restrict access to database backups and uploaded business data.
- Review security updates and dependency vulnerability alerts.

## Production Deployment

The application must be deployed with appropriate production security settings, including:

- `DEBUG=False`.
- A strong, unique Django `SECRET_KEY`.
- Properly configured `ALLOWED_HOSTS`.
- HTTPS and secure cookie settings.
- Protected database credentials.
- Restricted database and backup access.
- Appropriate security headers.

The Django development server must not be used for production hosting.

## Responsible Disclosure

Please allow the maintainer reasonable time to investigate and address reported vulnerabilities before publicly disclosing them.

We appreciate responsible security research and contributions that help improve the safety and reliability of this project.

## Scope

This policy applies to the Cinema Hall & Canteen Point of Sale application and its maintained source code.

---

**Project:** Cinema Hall & Canteen POS System
**Framework:** Django
**Database:** MySQL
**Security:** Django Authentication, Django Axes, CSRF Protection, HTTPS Configuration
