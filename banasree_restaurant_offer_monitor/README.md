
# Banasree Restaurant Offer Monitor

A zero-subscription-cost experiment that checks public restaurant offer sources
for Banasree, Dhaka and publishes a mobile-friendly dashboard.

## What it monitors

The starter configuration includes:

- Foodpanda's Banasree delivery-area page;
- selected Banasree Foodpanda vendor pages;
- selected restaurant websites;
- experimental public Facebook pages;
- experimental public Instagram profiles.

Edit `config/sources.csv` to add or remove restaurants.

## Status model

### Offer status

- `DETECTED`: a strong discount/deal signal was found;
- `NEEDS REVIEW`: an offer-like statement was found but was not strong enough;
- `EXPIRED`: the text included an expiry date that has passed.

### Source status

- `OFFER FOUND`: one or more candidates were detected;
- `NO OFFER FOUND`: the page loaded and no offer signal was detected;
- `CHECK FAILED`: the request failed;
- `BLOCKED`: robots rules, login wall, CAPTCHA, or another access restriction
  prevented a reliable check.

A blocked social page is never classified as "no offer."

## Important Facebook and Instagram limitation

This project does not log in, solve CAPTCHAs, rotate identities, or bypass an
access restriction. It only reads public content visible to a normal logged-out
browser.

Facebook and Instagram frequently show login walls or incomplete public profile
content. Those sources will appear as `BLOCKED`, and the rest of the monitor will
continue running. For production-quality social monitoring, restaurants should
connect accounts they own through Meta's authorized APIs.

## Setup on GitHub

1. Create a **public** GitHub repository.
2. Upload every file and folder, including the hidden `.github` folder.
3. Open **Settings → Actions → General**.
4. Under Workflow permissions, select **Read and write permissions**.
5. Open **Settings → Pages**.
6. Choose **Deploy from a branch**, branch `main`, folder `/docs`.
7. Open **Actions → Daily Banasree restaurant offer scan**.
8. Click **Run workflow** once.

It will then run every day at 9:15 AM Bangladesh time.

Your dashboard address will normally be:

```text
https://YOUR-USERNAME.github.io/YOUR-REPOSITORY-NAME/
```

## Install it like an app

Open the GitHub Pages dashboard in Chrome on Android and select
**Add to Home screen**. The included web manifest and service worker make it a
basic installable PWA.

## Add a source

Add a row to `config/sources.csv`:

```csv
source_id,restaurant_name,scope,source_type,url,render_mode,active,notes
my-restaurant,My Restaurant,Banasree branch,website,https://example.com/offers,auto,yes,
```

Supported source types:

- `foodpanda_area`
- `foodpanda_vendor`
- `website`
- `social_public`

Rendering modes:

- `requests`: ordinary HTML only;
- `browser`: Chromium/JavaScript;
- `auto`: request first, browser fallback.

Social sources should use `browser`.

## Optional Telegram alerts

Create a Telegram bot and add these repository secrets:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

The workflow sends a message only when a newly detected or review-needed offer
appears. Without these secrets, the notification step safely skips.

## Accuracy and maintenance

This is an experiment, not a guarantee that a restaurant will honour an offer.
Always verify the linked source. Delivery platforms can show personalized,
app-only, first-order, or location-dependent deals.

Review the **Source health** table regularly. Correct wrong URLs in
`config/sources.csv`. Add restaurant-specific sources when you discover them.

The current version reads visible text and page metadata. It deliberately does
not perform OCR on promotional images. Image-only offers therefore require a
later moderation or image-extraction feature.
