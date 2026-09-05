# Dataset — `razorpay_demo_payments.csv`

## Where this data comes from

This is **not** an arbitrary randomly-generated dataset. Every column, every
`error_code` / `error_reason` / `error_source` / `error_step` value, and every
`method` value is taken **verbatim from Razorpay's public API documentation**:

- Payment entity schema: https://razorpay.com/docs/api/payments/entity/
- Error object schema (`code`, `description`, `field`, `source`, `step`,
  `reason`, `metadata`): https://razorpay.com/docs/api/errors/
- Error codes / reasons catalogue: https://razorpay.com/docs/payments/payment-gateway/rainy-day/errors/error-codes
- Supported payment methods (card, upi, netbanking, wallet, emi): Razorpay
  Payments docs

`build_demo_dataset.py` assembles a **fixture dataset** — rows shaped exactly
like a real Razorpay `payments.fetch_multiple()` / dashboard export, with a
`recovered` outcome label and a `recovery_action` label attached so the ML
and policy layers have something to train/evaluate against. It does not
invent new fields, new error codes, or a fake schema — it recombines
Razorpay's real documented values into transaction rows, and layers on
customer-history fields (`previous_success_rate`, `upi_success_rate`, etc.)
that a merchant's own Razorpay dashboard + database would already have
alongside the Payment entity.

If you have a live Razorpay account, `razorpay_client.py` reads directly from
the real API (`payments.all()`) using your key/secret and normalizes the
response into this same schema — so the rest of the pipeline (diagnosis →
ML → policy → agent → simulator) runs unchanged on real account data. Set
`RAZORPAY_KEY_ID` / `RAZORPAY_KEY_SECRET` env vars and run with
`--source live` (see `app/dashboard.py` sidebar toggle).

## Schema

| column | source | description |
|---|---|---|
| `id` | Payment entity | `pay_XXXXXXXXXXXXXX` |
| `order_id` | Payment entity | `order_XXXXXXXXXXXXXX` |
| `entity` | Payment entity | always `payment` |
| `amount` | Payment entity | amount in paise (smallest currency unit) |
| `currency` | Payment entity | `INR` |
| `status` | Payment entity | `captured`, `failed`, `authorized` |
| `method` | Payment entity | `card`, `upi`, `netbanking`, `wallet`, `emi` |
| `captured` | Payment entity | boolean |
| `email`, `contact` | Payment entity | customer contact fields |
| `customer_id` | Payment entity | `cust_XXXXXXXXXXXXXX` |
| `error_code` | Error object | e.g. `BAD_REQUEST_ERROR`, `GATEWAY_ERROR` |
| `error_description` | Error object | human text tied to `error_code` |
| `error_source` | Error object | `customer`, `business`, `bank`, `gateway` |
| `error_step` | Error object | `payment_authentication`, `payment_authorization`, `payment_processing` |
| `error_reason` | Error object | e.g. `incorrect_otp`, `payment_declined`, `bank_server_error` |
| `created_at` | Payment entity | unix timestamp |
| `notes` | Payment entity | free-form JSON (we store `attempt_number`) |
| `bank` | Payment entity | 4-char bank code (nullable) |

Columns added for the recovery-agent use case (kept separate from the
Razorpay-native columns above, and clearly documented as derived):

`attempt_number`, `previous_success_rate`, `previous_failure_rate`,
`upi_success_rate`, `card_success_rate`, `time_since_last_attempt_min`,
`hour`, `day_of_week`, `checkout_duration_sec`, `customer_value_tier`,
`recovered` (label), `recovery_action` (label).

Run:

```bash
python build_demo_dataset.py
```

to (re)build `razorpay_demo_payments.csv` (1,200 rows — deliberately kept
small and inspectable rather than a 100k-row dump, per the buildathon
timeline).
