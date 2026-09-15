# Credit Chat

A single-file meetup demo: FastHTML + fastlite + fastllm + faststripe.
Google sign-in, saved cards, manual top-ups (including bank authentication),
automatic top-ups, and streaming chat. HTMX handles forms and streaming;
the only handwritten JavaScript calls Stripe.

## Run

```bash
uv sync --locked
cp .env.example .env
```

Fill in `.env` with Stripe **test** keys, an Anthropic API key, and a random
`SESSION_SECRET`. Register a Google OAuth web application with
`http://localhost:8000/redirect` as its authorized redirect URI, and put its
client id and secret in `.env` as `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET`.

```bash
python main.py
```

Open **http://localhost:8000**, sign in, save a test card, and add credit.
Enable automatic top-up and set its amount and threshold to demonstrate it.

## Code

- `User`, `Entry`, `Turn` are fastlite records. Credit is the sum of ledger entries.
- `charge` handles manual and automatic payments; `credit` records each successful
  Stripe payment once.
- `generate` streams fastllm output and deducts model cost plus 50%. Automatic
  top-up runs before and after each response.
- HTMX's SSE extension displays the answer while generation runs independently
  of the browser connection.

Amounts sent to Stripe are cents; ledger amounts are millionths of a dollar.
Run one server worker. This deliberately omits payment retries, recovery,
webhooks, country-specific handling, and automatic-top-up failure workflows.
