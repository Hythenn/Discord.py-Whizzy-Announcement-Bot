# Whizzy Bot

An asynchronous Discord bot designed to monitor Mapúa Malayan Colleges Laguna's Facebook announcements in near real-time and broadcast them to configured Discord channels.

## Features

- **Non-blocking Feed Processing**: Uses `asyncio.to_thread` for RSS feed ingestion via `feedparser` to keep the Discord gateway connection stable without blocking heartbeats.
- **Keyword Filtering**: Scans posts for critical keywords such as `ADVISORY:` and `ANNOUNCEMENT:` to ensure only relevant school updates get broadcasted.
- **Rich Embeds**: Cleans incoming HTML, strips provider watermarks, unescapes CDN image links, and builds PatchBot-style Discord embeds with interactive link buttons.
- **Multi-Server State Management**: Uses local JSON files (`channels.json` and `posted_ids.json`) for guild channel routing and duplicate post prevention.
- **Slash Commands**: Full Discord application commands support built on `discord.app_commands`.

## Tech Stack

- **Language**: Python 3.9+
- **Library**: `discord.py` (v2.x)
- **Feed Parser**: `feedparser`
- **Configuration**: `python-dotenv`

## Project Structure

```text
.
├── bot.py              # Main bot script with commands and background task
├── requirements.txt    # Project Python dependencies
├── channels.json       # Mapping of guild IDs to announcement channel IDs
├── posted_ids.json     # Cache of processed post IDs for deduplication
└── .env                # Secret environment variables (ignored in Git)
```

## Setup & Installation

### 1. Clone the Repository

```bash
git clone https://github.com/Hythenn/Discord.py-Whizzy-Announcement-Bot.git
cd Discord.py-Whizzy-Announcement-Bot
```

### 2. Create and Activate Virtual Environment

On Windows:
```bash
python -m venv venv
venv\Scripts\activate
```

On Linux / macOS:
```bash
python3 -m venv venv
source venv/bin/activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure Environment Variables

Create a `.env` file in the root directory:

```env
DISCORD_TOKEN=your_discord_bot_token_here
FEED_URL=your_rss_feed_url_here
SCHOOL_LOGO_URL=optional_school_logo_image_url
```

## Running the Bot

Start the bot with:

```bash
python bot.py
```

## Slash Commands

| Command | Description | Default Permissions |
| :--- | :--- | :--- |
| `/whizzy-setchannel <channel>` | Configure the channel for school announcements | Manage Channels |
| `/whizzy-removechannel` | Disable school announcements in the server | Manage Channels |
| `/whizzy-currentchannel` | View currently configured announcements channel | Everyone |
| `/whizzy-checknow` | Immediately check the RSS feed for new posts | Manage Channels |
| `/whizzy-latest` | Display the most recent announcement or advisory post | Everyone |
| `/whizzy-debug` | Display the latest post from the feed regardless of tag | Everyone |

## License

This project is licensed under the MIT License.

