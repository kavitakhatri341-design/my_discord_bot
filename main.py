import discord
from discord.ext import commands, tasks
import json
import threading
from flask import Flask

# ────────────────────────────────────────────────
# CONFIG
# ────────────────────────────────────────────────
TOKEN = "MTQ2NDk0Mjc4MDU0NjY4Mjk3Mw.G3R8x9.sFR4A847MkrxqMO2k-qWRknL7ba5SSNsGaNgzg"

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
# Flask keep-alive
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

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")
    print(f"Serving {len(bot.guilds)} guild(s)")

    # Force first refresh immediately
    await refresh_invite(startup=True)

    if not refresh_invite.is_running():
        refresh_invite.start()

@tasks.loop(minutes=30)
async def refresh_invite(startup=False):
    old_data = {}

    if not startup:
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                old_data = json.load(f)
            print("Loaded old message IDs")
        except Exception as e:
            print(f"No old data found or failed to load: {e}")

    guild = bot.get_guild(MAIN_GUILD_ID)
    if not guild:
        print("Main guild not found")
        return

    # Find a channel where we can create invites
    invite_channel = None
    for ch in guild.text_channels:
        if ch.permissions_for(guild.me).create_instant_invite:
            invite_channel = ch
            break

    if not invite_channel:
        print("No channel with invite permission found")
        return

    # Create fresh invite
    try:
        invite = await invite_channel.create_invite(
            max_age=1800,
            max_uses=0,
            unique=True
        )
        print(f"Created new invite: {invite.url}")
    except Exception as e:
        print(f"Failed to create invite: {e}")
        return

    new_data = {}

    for ch_id in POST_CHANNEL_IDS:
        channel = bot.get_channel(ch_id)
        if not channel:
            print(f"Channel {ch_id} not found")
            continue

        # Delete all messages in the channel
        try:
            async for msg in channel.history(limit=None):
                await msg.delete()
            print(f"Deleted all messages in channel {ch_id}")
        except discord.Forbidden:
            print(f"No permission to delete messages in channel {ch_id}")
        except Exception as e:
            print(f"Error deleting messages in channel {ch_id}: {e}")

        # Send new message
        try:
            msg = await channel.send(f"JOIN THE MAIN SERVER\n{invite.url}")
            new_data[str(ch_id)] = msg.id
            print(f"Sent new message in channel {ch_id}")
        except Exception as e:
            print(f"Failed to send message in {ch_id}: {e}")

    # Save new data
    if new_data:
        try:
            with open(DATA_FILE, "w", encoding="utf-8") as f:
                json.dump(new_data, f, indent=2)
            print("Saved new message IDs to file")
        except Exception as e:
            print(f"Failed to save data: {e}")
    else:
        print("No new messages were sent, nothing to save")

# ────────────────────────────────────────────────
# Start bot
# ────────────────────────────────────────────────
bot.run(TOKEN)

