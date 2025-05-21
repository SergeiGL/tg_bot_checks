# Telegram Transaction Verification Bot

## How It Works

1. Users start a chat with your bot
2. Bot prompts them to send a transaction confirmation picture
3. When any image is received:
    
    1. The username of a sender is in the Google Sheet
        - Image is forwarded to the specified admin account
        - Image is saved at a PostgreSQL database
        - The user's name is highlighted green in the Google Sheet
        - User receives a confirmation message and a view-only link to the Google Sheet (with his row number) to check that his username is indeed turned green.
    2. The username of a sender is NOT in the Google Sheet
        - The image sent is NOT forwarded to the specified admin account
        - The image sent is NOT saved at a PostgreSQL database
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
# Telegram Configuration
telegram_bot_token = ""  # Your main bot token
telegram_alerts_chats = [""]  # List of chat IDs to receive transaction images
telegram_alerts_token = ""  # Token for the alerts bot

is_drop_all_tables = False  # Set to True to reset database on startup

# Google Sheet Configuration
google_sheet_id = ""  # Your Google Sheet ID (from the link to a Sheet)
google_sheet_viewer_link = "https://docs.google.com/spreadsheets/d/YOUR_SHEET_ID"

# User Messages
start_text = "Hello!\nHappy to see you here 😀\n\nPlease send a <strong>picture (screenshot/photo)</strong> that confirms your transaction.\n\nRecipient details:\n<pre>+7 111 111 11 11     </pre>"
wrong_message_text = "You can only send plain photos from the gallery (no files).\nPlease try one more time."
alert_text = "User @{} attached:"
success_text = "🥳Thank YOU!🎉\n\nCheck your username at <strong>row {}</strong> (should be green):\n\n" + google_sheet_viewer_link
username_not_found_text = "Your username <strong>@{}</strong> is not in the google sheet:\n\n" + google_sheet_viewer_link

# PostgreSQL Database Configuration
pg_conf_keys = {
    'host': "db",
    'dbname': "",  # Your database name
    'user': "",    # Database username
    'password': "", # Database password
    'port': "5432",
}
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
