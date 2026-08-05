# Kasmirana Marketplace Review Sync — 100% Free Edition (GitHub Actions)

Automated pipeline: **Flipkart + Meesho reviews → GitHub Actions (free
scheduler) → Python + Playwright scraper → WordPress REST API → WooCommerce
product page**. No VPS, no paid database, no ongoing hosting cost for the
scraper itself.

## Architecture

```
┌────────────────────────────────────────────┐
│              GitHub Actions                 │   free scheduler — runs every 12h
│  (runs on GitHub's own temporary machines)   │   + a manual "Run workflow" button
└───────────────────┬──────────────────────────┘
                     │ spins up a fresh Ubuntu runner
                     ▼
┌────────────────────────────────────────────┐
│      Python + Playwright scraper            │
│  - opens Flipkart & Meesho product pages    │
│  - extracts rating + reviews                │
│  - cleans/validates/filters (4-5★ only)     │
└───────────────────┬──────────────────────────┘
                     │ HTTPS POST + Application Password + shared secret
                     ▼
┌────────────────────────────────────────────┐
│   WordPress (kasmirana.com)                 │
│   ksm-review-sync plugin                    │
│   - REST endpoints: /v1/sync, /v1/stats     │
│   - stores in its OWN database              │  <- the only persistent
│     (wp_ksm_marketplace_reviews table)      │     storage in this whole system
│   - de-dupes automatically (fingerprint)    │
│   - renders review section on product page  │
└────────────────────────────────────────────┘
```

**Why this is genuinely free and needs no VPS/database of its own:**
- GitHub Actions gives every account a free minutes budget — **public repos:
  unlimited**, **private repos: 2,000 minutes/month free**. One sync run
  (install deps + Playwright + scrape 2 sites) takes ~3-5 minutes. Running
  every 12 hours = ~60 runs/month × 5 min = **~300 min/month** — comfortably
  inside the free tier even on a private repo.
- The GitHub Actions runner is thrown away after every run, so there's
  nowhere for the scraper to keep its own database even if we wanted one.
  Instead, **WordPress's own database is the single source of truth** — the
  plugin's fingerprint-based de-dup means the scraper can safely re-scrape
  and re-push everything on every run; already-seen reviews are silently
  skipped, only genuinely new ones get added.

## Folder structure

```
review-sync-github/
├── .github/workflows/
│   └── review-sync.yml           the free scheduler — GitHub runs this automatically
├── scraper/
│   ├── main.py                   entry point — one full sync cycle
│   ├── config.py                 reads GitHub Secrets (or local .env for testing)
│   ├── wp_sync.py                pushes reviews/stats to WordPress
│   ├── requirements.txt
│   ├── .env.example              for LOCAL testing only
│   ├── scrapers/
│   │   ├── selectors.py          ★ ALL CSS selectors — edit only this file when a site changes
│   │   ├── base_scraper.py       shared Playwright browser setup + retries
│   │   ├── flipkart_scraper.py
│   │   └── meesho_scraper.py
│   └── utils/
│       ├── sanitize.py           cleaning, PII redaction, profanity check, de-dup fingerprint
│       └── logger.py
└── wordpress-plugin/
    └── ksm-review-sync/           upload this folder to wp-content/plugins/
        ├── ksm-review-sync.php
        ├── includes/
        │   ├── class-ksm-review-db.php        the only database in the system
        │   ├── class-ksm-review-rest-api.php  secured endpoints
        │   └── class-ksm-review-display.php
        ├── templates/reviews-section.php
        └── assets/{css,js}/
```

## Setup — step by step

### Step 1 — Create a GitHub repository
1. Go to github.com → New repository → name it e.g. `kasmirana-review-sync`.
2. **Private** is recommended (keeps your scraper code and product URLs out
   of public view), but Public also works and gives unlimited free minutes.
3. Upload this entire `review-sync-github/` folder's contents to the repo
   (drag-and-drop on github.com works fine, or `git push` if you're
   comfortable with git).

### Step 2 — Install the WordPress plugin
1. Upload `wordpress-plugin/ksm-review-sync/` to `/wp-content/plugins/ksm-review-sync/` via FTP.
2. wp-admin → Plugins → activate **"Kasmirana Marketplace Review Sync"**.
   (This automatically creates the 2 database tables it needs.)
3. Add a secret key to `wp-config.php` — open it via FTP, find the line that
   says `/* That's all, stop editing! */`, and add this line **above** it:
   ```php
   define( 'KSM_REVIEW_SYNC_SECRET', 'paste-a-long-random-string-here' );
   ```
   Generate a random string here: https://1password.com/password-generator/
   (32+ characters, letters+numbers is fine).
4. Create a dedicated Application Password: wp-admin → Users → your profile
   → scroll to **Application Passwords** → type a name like
   `github-review-sync` → **Add New Application Password** → **copy the
   password shown** (you can't see it again after leaving the page).

### Step 3 — Add GitHub Secrets
In your GitHub repo: **Settings → Secrets and variables → Actions → New
repository secret**. Add each of these one at a time:

| Secret name | Value |
|---|---|
| `WP_BASE_URL` | `https://kasmirana.com` |
| `WP_API_USERNAME` | your WP admin email, e.g. `kasmirana.saffron@gmail.com` |
| `WP_API_APP_PASSWORD` | the Application Password from Step 2.4 |
| `WP_SYNC_SHARED_SECRET` | the exact same random string you put in `wp-config.php` in Step 2.3 |
| `FLIPKART_PRODUCT_URL` | your Flipkart product page URL |
| `MEESHO_PRODUCT_URL` | your Meesho product page URL |

These are encrypted by GitHub and never shown in logs, even to you, after saving.

### Step 4 — Verify the selectors work (important, do this before relying on it)
Flipkart and Meesho redesign their pages from time to time, so the CSS
selectors in `scraper/scrapers/selectors.py` need a one-time check against
your actual product pages:

1. On your own computer: `cd scraper`, `python -m venv venv`, activate it,
   `pip install -r requirements.txt`, `playwright install chromium`.
2. Copy `.env.example` → `.env`, fill in your real URLs and WordPress
   credentials.
3. Run with a visible browser window so you can watch it work:
   ```
   HEADLESS=false python main.py --source flipkart
   ```
4. If it finds 0 reviews, open the same product page in Chrome, right-click
   a review → **Inspect**, and update the matching line in `selectors.py`.
   Repeat for `--source meesho`.

### Step 5 — Run it once manually on GitHub
In your repo: **Actions tab → "Kasmirana Review Sync" → Run workflow**
button. Watch it run (takes a few minutes). Check the log output for the
`RUN SUMMARY` line — it shows how many reviews were found/synced per source.
Then check your WordPress product page — the "What Customers Are Saying"
section should appear.

### Step 6 — Let it run automatically
Nothing more to do — the `schedule: cron: "0 6,18 * * *"` line in
`.github/workflows/review-sync.yml` means GitHub will run this
automatically twice a day, forever, for free. You can change the schedule
by editing that cron line (e.g. `"0 3 * * *"` for once daily at 3am UTC).

## Security practices implemented

- **Two-factor endpoint auth**: WordPress Application Password + a separate
  shared secret stored only in `wp-config.php` and GitHub Secrets — never in
  any database, never in the repo itself.
- **GitHub Secrets are encrypted** and masked in all logs automatically.
- **Rate limiting** on the REST endpoints (60 req/min).
- **Server-side rating floor**: WordPress itself rejects anything below 4★,
  independent of the scraper's own filtering.
- **PII redaction**: phone numbers, emails, and URLs inside review text are
  automatically masked before anything is sent to WordPress.
- **Profanity/content filter**: flagged reviews are simply never sent —
  nothing inappropriate reaches the live site.
- **Parameterized SQL** in the WordPress plugin (`$wpdb->prepare()`
  everywhere) — no string-built queries.
- **Fingerprint de-duplication** (SHA-256 of source+reviewer+text+date) means
  re-running the workflow forever never creates duplicate review cards.

## Error handling & logging

- Every browser automation step and every WordPress push is wrapped in
  `tenacity` retries (3 attempts, exponential backoff) — handles transient
  network blips automatically.
- One source failing (e.g. Flipkart's page structure changed) does **not**
  stop the other source from syncing — each is isolated with its own
  try/except in `main.py`.
- Every GitHub Actions run uploads its log file as a downloadable
  **artifact** (kept 14 days) — go to the run in the Actions tab →
  Artifacts, even for successful runs, to see exactly what happened.
- A failed run shows a red ✗ in the Actions tab; GitHub can email you on
  failure automatically (Settings → Notifications → Actions).

## Ongoing maintenance (realistic expectations)

- Flipkart/Meesho **will** occasionally change their page layout, which
  breaks scraping until `selectors.py` is updated (Step 4, above). This is
  true of any scraper for any site — there's no way around it without an
  official API, which neither platform offers.
- Check the Actions tab occasionally for red ✗ runs.
- This scrapes your own product's public review page. As discussed
  separately: using your own seller login for a human to browse is fine;
  running an unauthenticated automated scraper against the marketplace is
  against their Terms of Service, which is a business decision you've
  already made — this system is built to be reliable and safe on the
  WordPress side regardless.
