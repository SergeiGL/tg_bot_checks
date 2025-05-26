# Telegram Transaction Verification Bot

## How It Works

1. Users start a chat (/start)
    1. The username of a sender is in the Google Sheet
        - Bot sends the payment sum (depends on how early the user started the bot) and prompts for a transaction confirmation screenshot
    2. The username of a sender is NOT in the Google Sheet
        - User is prompted that he is not in the Google Sheet
2. When any image is received:
   1. The username of a sender is in the Google Sheet
      - Image is forwarded to the specified admin account with user's position, payment sum and username
      - Image is saved at a PostgreSQL database (see `example_db.png`)
      - The user's name is highlighted green in the Google Sheet
      - User receives a confirmation message and a view-only link to the Google Sheet (with his row number) to check that his username is indeed turned green.
   2. The username of a sender is NOT in the Google Sheet
      - User is prompted that he is not in the Google Sheet

## Prerequisites

- Telegram bot
- A Google Sheet with Telegram usernames in column A (the column will be color-coded)
- Google Cloud account with API access to the Sheet configured
- Docker and Docker Compose installed

## Setup Instructions

### Google Sheets Setup

1. Use @BotFather to setup a Telegram Bot
2. Create a Google Sheet with usernames in column A (see `example_google_sheet.png`)
3. Set up Google Cloud Platform and the Google Sheets API:
   - Follow this helpful guide: https://youtu.be/zCEJurLGFRk?si=IT-Hni9W0eHmPVOR
   - Download your API credentials as `json` and rename the file to `google_sheets_key.json`

### Configuration

Create a `config.py` file with the following content:

```python
telegram_bot_token = ""
telegram_alerts_chats = [""]
telegram_alerts_token = ""

is_drop_all_tables = False

GEOM_SEQ_R = 1.015 # 1.5%
google_sheet_name = "Sheet1"

google_sheet_viewer_link = ""
start_text = "Hello!\nHappy to see you here 😀\n\nYou are <strong>{}</strong> out of {}\n\nYour payment is <strong>{} RUB</strong>.\n\n\
Recipient details:\n<pre></pre>\nX X\nX / X / X / X\n\n\
Please send a <strong>screenshot (or picture/photo)</strong> that confirms your transaction.\n\n\
Interesting stats:\nLowest payment: {} RUB\nHighest payment: {} RUB\nThe next guy will pay: {} RUB ({}% more)"

wrong_message_text = "You can only send plain photos from the gallery (no files).\nPlease try one more time."
alert_text = "#{} @{} {} RUB:"
success_text = "🥳Thank YOU!🎉\n\nCheck your username at <strong>ROW: {}</strong> (should be green):\n\n" + google_sheet_viewer_link
username_not_found_text = "Your username <strong>@{}</strong> is not in the Google Sheet:\n\n" + google_sheet_viewer_link


pg_conf_keys = {
    'host': "db",
    'dbname': "",
    'user': "",
    'password': "",
    'port': "5432",
}


google_sheet_id = ""
```

## Running the Bot

### Run

1. Make sure all configuration files are properly set up
2. Run:

```bash
docker compose up
```

### After Making Changes

If you modify `bot.py` or other source files:

```bash
docker build . -t tg_bot_collect_checks-bot
docker compose up
```
