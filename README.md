# E-Commerce FastAPI backend

## Run locally

1. Install the dependencies in `requirements.txt`.
2. Copy `.env.example` to `.env` and set `DATABASE_URL` and a strong `SECRET_KEY`. The API starts without Razorpay, SMTP, or Twilio credentials; the related endpoints return a `503` response explaining which provider environment details are missing.
3. Apply database migrations with `alembic upgrade head`.
4. Start the API with `uvicorn app.main:app --reload` and open `/docs`.

Email verification and password recovery need `SMTP_HOST`, `SMTP_PORT`, `EMAIL_FROM`, and, when required by the mail server, `SMTP_USERNAME` and `SMTP_PASSWORD`. Set `FRONTEND_URL` to the frontend origin to generate verification/reset links. Phone verification needs `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, and `TWILIO_FROM_NUMBER`. Online payments and refunds need Razorpay key ID and secret. Configure Razorpay's refund webhook to send `refund.processed` and `refund.failed` events to `/payments/razorpay/webhook`, and set `RAZORPAY_WEBHOOK_SECRET`. `CORS_ORIGINS` accepts a JSON array of allowed origins.

## Main API areas

- `/auth`: registration, OAuth2 login, logout, email/phone verification, forgot/reset password.
- `/customers/me`: dashboard, profile, addresses, wallet and ledger, wishlist, verified-purchase reviews, returns, refunds, support tickets, notifications.
- `/products` and `/categories`: approved catalog, search/filter/sort, reviews, categories and subcategories.
- `/cart` and `/orders`: cart, checkout, Razorpay verification, wallet/COD payments, customer order history, cancellation, tracking, and invoice data.
- `/vendors/me`: shop profile, products/images/specifications, inventory, vendor orders/statuses, sales, market insights, earnings, payout requests, and reviews.
- `/admin`: dashboards, user/vendor/product/review/payment moderation, refunds, coupons, commission, payout processing, checkout/content settings, notifications, support, audit logs, analytics, and CSV sales export.

Vendor products are hidden from the public catalog until an admin approves them. Vendor deletion is not provided; admins can review applications and manage listings without deleting approved vendor accounts. Payouts are tracked and marked paid by an admin with a reference; bank transfers are not initiated by this API.

The API uses bearer JWTs. Logout revokes all current tokens for that account. Product image uploads accept JPEG, PNG, or WebP, verify file signatures, and cap uploads at 5 MB. Images are stored under `app/static/products` and served from `/media`.

The built-in rate limiter is per process. A multi-worker or production deployment should enforce limits at a shared gateway or with a shared store. Email and SMS delivery remain disabled until their provider credentials are configured.
