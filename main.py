import discord
from discord.ext import commands, tasks
import json
import threading
from flask import Flask
import os
import asyncio

# ────────────────────────────────────────────────
# CONFIG
# ────────────────────────────────────────────────
import os
TOKEN = os.getenv("DISCORD_TOKEN")
  # Safe token from Render environment variable
if not TOKEN:
    raise ValueError("DISCORD_TOKEN environment variable is missing!")

MAIN_GUILD_ID = 1396058725613305939

POST_CHANNEL_IDS = [
    1461096483825914142,
    1461095577231298819,
    1461599681569362082,
    1461601615411810510,
    1462054807002021960,
    1462055058920177695,
    1462136558802047275,
    1462137623320596571,
]

DATA_FILE = "invite_data.json"

# ────────────────────────────────────────────────
# Flask keep-alive (for Render / UptimeRobot)
# ────────────────────────────────────────────────
app = Flask("")

@app.route("/")
def home():
    return "Bot is running!"

def run_flask():
    app.run(host="0.0.0.0", port=8080, debug=False, use_reloader=False)

threading.Thread(target=run_flask, daemon=True).start()

# ────────────────────────────────────────────────
# Discord bot
# ────────────────────────────────────────────────
intents = discord.Intents.default()
intents.message_content = True
intents.messages = True

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user} (ID: {bot.user.id})")
    print(f"🌐 Serving {len(bot.guilds)} guilds")

    main_guild = bot.get_guild(MAIN_GUILD_ID)
    if main_guild:
        print(f"🛡 Main guild: {main_guild.name} (ID: {main_guild.id})")
    else:
        print(f"⚠ ERROR: Main guild {MAIN_GUILD_ID} not found")

    print("🔄 Starting invite refresh...")
    await refresh_invite(startup=True)

    if not refresh_invite.is_running():
        refresh_invite.start()

@tasks.loop(minutes=30)
async def refresh_invite(startup=False):
    old_data = {}
    if not startup and os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                old_data = json.load(f)
        except Exception as e:
            print(f"⚠ Failed to read {DATA_FILE}: {e} → treating as fresh start")

    guild = bot.get_guild(MAIN_GUILD_ID)
    if not guild:
        print("⚠ Main guild not found")
        return

    # Find a channel with invite permission
    invite_channel = None
    for ch in guild.text_channels:
        if ch.permissions_for(guild.me).create_instant_invite:
            invite_channel = ch
            break

    if not invite_channel:
        print("⚠ No channel found with create_instant_invite permission")
        return

    # Delete ALL previous messages in the target channels
    for ch_id in POST_CHANNEL_IDS:
        channel = bot.get_channel(ch_id)
        if not channel:
            print(f"⚠ Channel {ch_id} not found")
            continue

        try:
            async for msg in channel.history(limit=None):
                await msg.delete()
            print(f"🗑 Cleared all messages in {ch_id}")
        except discord.Forbidden:
            print(f"⚠ No permission to delete messages in {ch_id}")
        except Exception as e:
            print(f"⚠ Failed to clear messages in {ch_id}: {e}")

    # Create a fresh invite
    try:
        invite = await invite_channel.create_invite(
            max_age=1800,  # 30 minutes
            max_uses=0,
            unique=True,
            reason="Periodic public invite refresh"
        )
        print(f"🔗 New invite created: {invite.url}")
    except Exception as e:
        print(f"⚠ Failed to create invite: {e}")
        return

    # Send new invite to all channels
    for ch_id in POST_CHANNEL_IDS:
        channel = bot.get_channel(ch_id)
        if not channel:
            continue

        try:
            msg = await channel.send(f"🚪 JOIN THE MAIN SERVER\n{invite.url}")
            print(f"📤 Posted new invite in {ch_id} → {msg.id}")
            old_data[str(ch_id)] = msg.id
        except Exception as e:
            print(f"⚠ Failed to send message to {ch_id}: {e}")

    # Save last message IDs for reference (optional)
    if old_data:
        try:
            with open(DATA_FILE, "w", encoding="utf-8") as f:
                json.dump(old_data, f, indent=2)
            print("💾 Saved message IDs")
        except Exception as e:
            print(f"⚠ Failed to save {DATA_FILE}: {e}")

# ────────────────────────────────────────────────
# Run bot
# ────────────────────────────────────────────────
bot.run(TOKEN)

