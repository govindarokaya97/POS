# Security Policy

## Supported Versions

Security updates are currently provided for the actively maintained version of this project.

| Version | Supported |
|---|---|
| Main branch | Yes |
| Older versions | No guarantee |

## Reporting a Vulnerability

If you discover a security vulnerability, please do not publish sensitive details in a public GitHub issue.

Instead, report it privately through GitHub's private vulnerability reporting feature, if enabled for this repository, or contact the repository maintainer through their GitHub profile.

Please include:

- A description of the vulnerability.
- Steps to reproduce the issue.
- Potential impact.
- Any suggested mitigation.

## Security Practices

This project aims to follow these practices:

- Store secrets and credentials in environment variables.
- Never commit `.env` files, passwords, or API credentials.
- Use Django's password validation and authentication protections.
- Protect administrative and business operations with appropriate access controls.
- Use HTTPS and secure cookies in production.
- Keep Django and third-party dependencies updated.
- Restrict access to database backups and uploaded business data.
- Review security-sensitive changes before deployment.

## Production Deployment

The application must be deployed with:

- `DEBUG=False`.
- A strong, unique Django `SECRET_KEY`.
- Properly configured `ALLOWED_HOSTS`.
- HTTPS and secure cookie settings.
- Protected database credentials.
- Restricted database and backup access.

The Django development server must not be used for production hosting.

## Scope

This policy applies to the Cinema Hall and Canteen Point of Sale application and its maintained source code.