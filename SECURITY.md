# Security Baseline

This project is a frontend-only demo application. Before any production usage, apply the following hardening checklist.

## Required Baseline

- Do not store plaintext credentials in `localStorage`.
- Keep auth/session data non-sensitive and time-bound.
- Use a strict Content Security Policy (CSP) at hosting level.
- Ensure all external links using `target="_blank"` include `rel="noopener noreferrer"`.
- Restrict HTML rendering from i18n keys to approved tags only.

## Recommended CSP Template

Use this as a starting point and tighten per deployment:

```text
Content-Security-Policy:
  default-src 'self';
  script-src 'self';
  style-src 'self' https://fonts.googleapis.com;
  font-src 'self' https://fonts.gstatic.com;
  img-src 'self' data:;
  connect-src 'self';
  object-src 'none';
  base-uri 'self';
  frame-ancestors 'none';
```

## Release Security Checks

- Verify no new `innerHTML` paths bypass sanitization.
- Verify no credentials/tokens are persisted in clear text.
- Verify language/data payloads are trusted or sanitized.
- Verify security headers in local staging and production.
