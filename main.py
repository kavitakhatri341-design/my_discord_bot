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
TOKEN = os.getenv("DISCORD_TOKEN")
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
intents.messages = True

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user} (ID: {bot.user.id})")
    print(f"🌐 Serving {len(bot.guilds)} guilds")

    print("🔄 Starting invite refresh...")
    await refresh_invite(startup=True)

    if not refresh_invite.is_running():
        refresh_invite.start()

@tasks.loop(minutes=30)
async def refresh_invite(startup=False):
    old_data = {}

    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                old_data = json.load(f)
        except:
            old_data = {}

    guild = bot.get_guild(MAIN_GUILD_ID)
    if not guild:
        print("⚠ Main guild not found")
        return

    invite_channel = None
    for ch in guild.text_channels:
        if ch.permissions_for(guild.me).create_instant_invite:
            invite_channel = ch
            break

    if not invite_channel:
        print("⚠ No channel with invite permission")
        return

    # ────────────────────────────────────────────────
    # DELETE ONLY PREVIOUS BOT MESSAGE (RATE SAFE)
    # ────────────────────────────────────────────────
    for ch_id in POST_CHANNEL_IDS:
        channel = bot.get_channel(ch_id)
        if not channel:
            continue

        old_msg_id = old_data.get(str(ch_id))
        if old_msg_id:
            try:
                msg = await channel.fetch_message(old_msg_id)
                await msg.delete()
                await asyncio.sleep(1)  # small delay = safe
            except discord.NotFound:
                pass
            except Exception as e:
                print(f"⚠ Failed to delete old message in {ch_id}: {e}")

    # ────────────────────────────────────────────────
    # CREATE NEW INVITE
    # ────────────────────────────────────────────────
    try:
        invite = await invite_channel.create_invite(
            max_age=1800,
            max_uses=0,
            unique=True,
            reason="Periodic public invite refresh"
        )
        print(f"🔗 New invite: {invite.url}")
    except Exception as e:
        print(f"⚠ Failed to create invite: {e}")
        return

    # ────────────────────────────────────────────────
    # POST NEW INVITE
    # ────────────────────────────────────────────────
    new_data = {}

    for ch_id in POST_CHANNEL_IDS:
        channel = bot.get_channel(ch_id)
        if not channel:
            continue

        try:
            msg = await channel.send(f"JOIN THE MAIN SERVER\n{invite.url}")
            new_data[str(ch_id)] = msg.id
            await asyncio.sleep(1)
        except Exception as e:
            print(f"⚠ Failed to send message to {ch_id}: {e}")

    # ────────────────────────────────────────────────
    # SAVE MESSAGE IDS
    # ────────────────────────────────────────────────
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(new_data, f, indent=2)
    except Exception as e:
        print(f"⚠ Failed to save data: {e}")

# ────────────────────────────────────────────────
# RUN
# ────────────────────────────────────────────────
bot.run(TOKEN)
