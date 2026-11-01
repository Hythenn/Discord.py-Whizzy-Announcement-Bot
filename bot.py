import os
import re
import json
import html
import time
import asyncio
from datetime import datetime, timezone
import discord
from discord import app_commands
from discord.ext import commands, tasks
import feedparser
from dotenv import load_dotenv

# Load credentials from .env file
load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
FEED_URL = os.getenv("FEED_URL", "")

# School branding & colors (Mapúa Cardinal Red)
EMBED_COLOR = 0xC8102E
LOGO_URL = os.getenv("SCHOOL_LOGO_URL", None)

# Keywords to match (checked case-insensitively)
KEYWORDS = ["ADVISORY:", "ANNOUNCEMENT:"]
POSTED_FILE = "posted_ids.json"
CHANNELS_FILE = "channels.json"

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

# --- Storage Helper Functions ---

def load_posted_ids():
    """Load previously posted announcement IDs to prevent duplicates."""
    if os.path.exists(POSTED_FILE):
        try:
            with open(POSTED_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return []
    return []

def save_posted_ids(posted_list):
    """Save IDs to file, keeping only the last 100 to manage file size."""
    with open(POSTED_FILE, "w", encoding="utf-8") as f:
        json.dump(posted_list[-100:], f, indent=2)

def load_channels():
    """Load the mapping of guild_id -> channel_id."""
    if os.path.exists(CHANNELS_FILE):
        try:
            with open(CHANNELS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {}
    return {}

def save_channels(channels_dict):
    """Save guild_id -> channel_id mapping to file."""
    with open(CHANNELS_FILE, "w", encoding="utf-8") as f:
        json.dump(channels_dict, f, indent=2)

# --- Content Cleaning & Photo Extraction ---

def is_placeholder_icon(url):
    """Filter out tracking pixels or third-party service logos."""
    if not url:
        return True
    url_lower = url.lower()
    placeholders = ["fetchrss.png", "facebook.png", "1x1.png", "pixel.gif", "provider/"]
    return any(p in url_lower for p in placeholders)

def extract_image_url(entry):
    """Extract full-resolution post image with properly unescaped query tokens."""
    # 1. Check media enclosures (media:content)
    if hasattr(entry, "media_content") and entry.media_content:
        for media in entry.media_content:
            url = media.get("url")
            if url and not is_placeholder_icon(url):
                return html.unescape(url)

    # 2. Check standard RSS enclosures
    if hasattr(entry, "enclosures") and entry.enclosures:
        for enc in entry.enclosures:
            url = enc.get("href")
            enc_type = enc.get("type", "")
            if url and (enc_type.startswith("image/") or any(ext in url.lower() for ext in [".jpg", ".jpeg", ".png", ".webp"])):
                if not is_placeholder_icon(url):
                    return html.unescape(url)

    # 3. Check HTML bodies for <img> tags
    html_sources = [
        getattr(entry, "summary", ""),
        getattr(entry, "description", "")
    ]
    if hasattr(entry, "content"):
        for c in entry.content:
            html_sources.append(c.get("value", ""))

    for raw in html_sources:
        if not raw:
            continue
        matches = re.findall(r'<img[^>]+src=["\']([^"\']+)["\']', raw, re.IGNORECASE)
        for img_url in matches:
            clean_url = html.unescape(img_url)
            if not is_placeholder_icon(clean_url):
                return clean_url

    return None

def clean_html(raw_html):
    """Strip HTML tags, remove third-party feed notices, and convert to clean markdown."""
    if not raw_html:
        return ""
    
    # Remove third-party feed generator signatures
    text = re.sub(r'\(Feed generated with\s+<a[^>]*>FetchRSS</a>\)', '', raw_html, flags=re.IGNORECASE)
    text = re.sub(r'\(Feed generated with.*?FetchRSS.*?\)', '', text, flags=re.IGNORECASE)

    # Convert line break tags to actual newlines
    text = re.sub(r"<(br|p|div)[^>]*>", "\n", text, flags=re.IGNORECASE)
    # Remove remaining HTML tags
    text = re.sub(r"<[^>]+>", "", text)
    # Decode HTML entities (e.g. &amp; -> &)
    text = html.unescape(text)
    # Normalize multiple newlines
    return re.sub(r"\n{3,}", "\n\n", text).strip()

def build_post_view(post_link):
    """Creates a clickable link button component."""
    if not post_link:
        return None
    view = discord.ui.View()
    view.add_item(discord.ui.Button(
        label="View on Facebook",
        url=post_link,
        style=discord.ButtonStyle.link,
        emoji="🔗"
    ))
    return view

def build_post_embed(entry, header_tag=None):
    """Constructs a PatchBot-style rich Discord embed with author header, thumbnail, and banner image."""
    raw_title = getattr(entry, "title", "School Update")
    raw_summary = getattr(entry, "summary", "")
    
    # Keep the entire post caption intact
    full_caption = clean_html(raw_summary) if raw_summary else clean_html(raw_title)
    post_link = getattr(entry, "link", "https://www.facebook.com/MapuaMCL")
    title_display = f"{header_tag} {raw_title}" if header_tag else raw_title

    # Include explicit link line at bottom of description
    link_line = f"\n\n🔗 [**View Original Post on Facebook**]({post_link})"
    description_text = (full_caption[:3800] + link_line) if full_caption else link_line.strip()

    embed = discord.Embed(
        title=title_display[:256],
        url=post_link,
        description=description_text,
        color=EMBED_COLOR
    )

    # Author header (small label above title, like PatchBot)
    if LOGO_URL:
        embed.set_author(
            name="Mapúa Malayan Colleges Laguna",
            url="https://www.facebook.com/MapuaMCL",
            icon_url=LOGO_URL
        )
        embed.set_thumbnail(url=LOGO_URL)
    else:
        embed.set_author(
            name="Mapúa Malayan Colleges Laguna",
            url="https://www.facebook.com/MapuaMCL"
        )

    # Large post photo banner at bottom
    image_url = extract_image_url(entry)
    if image_url:
        embed.set_image(url=image_url)

    # Timestamp from publication date
    if hasattr(entry, "published_parsed") and entry.published_parsed:
        try:
            dt = datetime.fromtimestamp(time.mktime(entry.published_parsed), tz=timezone.utc)
            embed.timestamp = dt
        except Exception:
            pass

    embed.set_footer(text="Official Facebook Announcement")
    return embed

async def fetch_feed_async(url):
    """Fetch feed non-blockingly using asyncio.to_thread."""
    return await asyncio.to_thread(feedparser.parse, url)

# --- Core Feed Processing Logic ---

async def process_feed():
    """Fetches feed and broadcasts new matching announcements."""
    if not FEED_URL:
        return 0

    channels_map = load_channels()
    if not channels_map:
        return 0

    feed = await fetch_feed_async(FEED_URL)
    if feed.bozo and not feed.entries:
        return 0

    posted_ids = load_posted_ids()
    new_posts_sent = 0

    # Iterate reversed so older unposted items are sent first
    for entry in reversed(feed.entries):
        post_id = getattr(entry, "id", getattr(entry, "link", None))
        if not post_id or post_id in posted_ids:
            continue

        raw_title = getattr(entry, "title", "")
        raw_summary = getattr(entry, "summary", "")
        full_text = f"{raw_title} {raw_summary}".upper()

        matches = [kw for kw in KEYWORDS if kw.upper() in full_text]
        if not matches:
            # Mark non-matching post as seen so we don't inspect it repeatedly
            posted_ids.append(post_id)
            save_posted_ids(posted_ids)
            continue

        # Build PatchBot-style Discord Embed and Button
        matched_tag = matches[0]
        embed = build_post_embed(entry, header_tag=f"📢 {matched_tag}")
        post_link = getattr(entry, "link", "https://www.facebook.com/MapuaMCL")
        view = build_post_view(post_link)

        # Broadcast to all registered channels
        successful_send = False
        for guild_id_str, channel_id in list(channels_map.items()):
            channel = bot.get_channel(channel_id)
            if not channel:
                try:
                    channel = await bot.fetch_channel(channel_id)
                except Exception:
                    channel = None

            if channel:
                try:
                    if view:
                        await channel.send(embed=embed, view=view)
                    else:
                        await channel.send(embed=embed)
                    successful_send = True
                except Exception as e:
                    print(f"[Error] Failed to send to channel {channel_id}: {e}")

        # Mark as posted
        posted_ids.append(post_id)
        save_posted_ids(posted_ids)
        if successful_send:
            new_posts_sent += 1
            print(f"[Success] Broadcasted announcement: {post_id}")

    return new_posts_sent

# --- Background Task ---

@tasks.loop(minutes=5)
async def check_announcements():
    """Background task that runs every 5 minutes."""
    await process_feed()

@check_announcements.before_loop
async def before_check_announcements():
    """Wait until the Discord client is connected and ready."""
    await bot.wait_until_ready()

# --- Slash Commands with whizzy- Prefix ---

@bot.tree.command(
    name="whizzy-debug",
    description="Display the last post the page ever posted, regardless of tag"
)
async def whizzy_debug(interaction: discord.Interaction):
    if not FEED_URL:
        await interaction.response.send_message(
            "❌ FEED_URL is not set in your .env file.",
            ephemeral=True
        )
        return

    await interaction.response.defer()

    feed = await fetch_feed_async(FEED_URL)

    if not feed.entries:
        bozo_msg = getattr(feed, "bozo_exception", "Unknown issue")
        await interaction.followup.send(
            f"⚠️ **Feed returned 0 entries.**\n"
            f"• **Feed URL:** `{FEED_URL}`\n"
            f"• **Feed Title:** `{getattr(feed.feed, 'title', 'None')}`\n"
            f"• **Status / Error:** `{bozo_msg}`"
        )
        return

    # Grab the newest entry without filtering
    first_entry = feed.entries[0]
    embed = build_post_embed(first_entry, header_tag=None)
    post_link = getattr(first_entry, "link", "https://www.facebook.com/MapuaMCL")
    view = build_post_view(post_link)

    if view:
        await interaction.followup.send(embed=embed, view=view)
    else:
        await interaction.followup.send(embed=embed)

@bot.tree.command(
    name="whizzy-setchannel",
    description="Set the channel where school announcements will be posted"
)
@app_commands.describe(channel="The channel to send school announcements to")
@app_commands.default_permissions(manage_channels=True)
async def whizzy_set_channel(interaction: discord.Interaction, channel: discord.TextChannel):
    if not interaction.guild:
        await interaction.response.send_message(
            "This command can only be used inside a server.",
            ephemeral=True
        )
        return

    permissions = channel.permissions_for(interaction.guild.me)
    if not permissions.send_messages or not permissions.embed_links:
        await interaction.response.send_message(
            f"⚠️ I need **Send Messages** and **Embed Links** permissions in {channel.mention}.",
            ephemeral=True
        )
        return

    channels_map = load_channels()
    channels_map[str(interaction.guild.id)] = channel.id
    save_channels(channels_map)

    await interaction.response.send_message(
        f"✅ Announcements channel has been set to {channel.mention}!",
        ephemeral=True
    )

@bot.tree.command(
    name="whizzy-removechannel",
    description="Disable school announcements in this server"
)
@app_commands.default_permissions(manage_channels=True)
async def whizzy_remove_channel(interaction: discord.Interaction):
    if not interaction.guild:
        await interaction.response.send_message(
            "This command can only be used inside a server.",
            ephemeral=True
        )
        return

    channels_map = load_channels()
    guild_id_str = str(interaction.guild.id)

    if guild_id_str in channels_map:
        del channels_map[guild_id_str]
        save_channels(channels_map)
        await interaction.response.send_message(
            "✅ School announcements have been disabled for this server.",
            ephemeral=True
        )
    else:
        await interaction.response.send_message(
            "ℹ️ No announcement channel was configured for this server.",
            ephemeral=True
        )

@bot.tree.command(
    name="whizzy-currentchannel",
    description="View the currently configured announcements channel"
)
async def whizzy_current_channel(interaction: discord.Interaction):
    if not interaction.guild:
        await interaction.response.send_message(
            "This command can only be used inside a server.",
            ephemeral=True
        )
        return

    channels_map = load_channels()
    channel_id = channels_map.get(str(interaction.guild.id))

    if channel_id:
        channel = interaction.guild.get_channel(channel_id)
        mention = channel.mention if channel else f"ID: {channel_id}"
        await interaction.response.send_message(
            f"📢 Current announcements channel is {mention}.",
            ephemeral=True
        )
    else:
        await interaction.response.send_message(
            "ℹ️ No announcements channel is currently set. Use `/whizzy-setchannel` to set one.",
            ephemeral=True
        )

@bot.tree.command(
    name="whizzy-latest",
    description="Display the very last post that included announcement keywords"
)
async def whizzy_latest(interaction: discord.Interaction):
    if not FEED_URL:
        await interaction.response.send_message(
            "⚠️ FEED_URL is not configured in the bot's .env file.",
            ephemeral=True
        )
        return

    await interaction.response.defer()

    feed = await fetch_feed_async(FEED_URL)
    if feed.bozo and not feed.entries:
        await interaction.followup.send(
            "❌ Unable to retrieve posts from the school feed at this moment. Please try again shortly."
        )
        return

    matching_entry = None
    matched_keyword = None

    for entry in feed.entries:
        raw_title = getattr(entry, "title", "")
        raw_summary = getattr(entry, "summary", "")
        full_text = f"{raw_title} {raw_summary}".upper()

        matches = [kw for kw in KEYWORDS if kw.upper() in full_text]
        if matches:
            matching_entry = entry
            matched_keyword = matches[0]
            break

    if matching_entry:
        embed = build_post_embed(matching_entry, header_tag=f"📢 {matched_keyword}")
        post_link = getattr(matching_entry, "link", "https://www.facebook.com/MapuaMCL")
        view = build_post_view(post_link)
        if view:
            await interaction.followup.send(embed=embed, view=view)
        else:
            await interaction.followup.send(embed=embed)
    else:
        await interaction.followup.send("ℹ️ No posts containing 'ADVISORY:' or 'ANNOUNCEMENT:' were found in the feed.")

@bot.tree.command(
    name="whizzy-checknow",
    description="Check the school Facebook feed immediately for new announcements"
)
@app_commands.default_permissions(manage_channels=True)
async def whizzy_check_now(interaction: discord.Interaction):
    if not interaction.guild:
        await interaction.response.send_message(
            "This command can only be used inside a server.",
            ephemeral=True
        )
        return

    await interaction.response.defer(ephemeral=True)
    count = await process_feed()
    if count > 0:
        await interaction.followup.send(
            f"✅ Feed checked! Found and posted {count} new announcement(s).",
            ephemeral=True
        )
    else:
        await interaction.followup.send(
            "You're all set! No announcements for now 👍",
            ephemeral=True
        )

# --- Bot Events ---

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")
    
    # Sync slash commands with Discord
    try:
        synced = await bot.tree.sync()
        print(f"Successfully synced {len(synced)} slash command(s).")
    except Exception as e:
        print(f"Failed to sync slash commands: {e}")

    # Start loop if not already running
    if not check_announcements.is_running():
        check_announcements.start()
        print("Announcement background loop started (5 minute interval).")

if __name__ == "__main__":
    if not DISCORD_TOKEN:
        print("[Error] DISCORD_TOKEN is missing. Please set it in your .env file.")
    else:
        bot.run(DISCORD_TOKEN)
