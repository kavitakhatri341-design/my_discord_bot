import discord
from discord.ext import commands, tasks
import json
import os
import asyncio
from flask import Flask
import threading

# ───────── CONFIG ─────────
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

# ───────── Minimal Flask for UptimeRobot ─────────
app = Flask("")

@app.route("/")
def home():
    return "Bot is running!"

def run_flask():
    port = int(os.getenv("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)

threading.Thread(target=run_flask, daemon=True).start()

# ───────── Discord bot ─────────
intents = discord.Intents.default()
intents.guilds = True
bot = commands.Bot(command_prefix="!", intents=intents)

# ───────── Helper: safe invite/message functions ─────────
async def safe_create_invite(channel):
    for attempt in range(5):
        try:
            return await channel.create_invite(
                max_age=3600, max_uses=0, unique=True
            )
        except discord.HTTPException as e:
            if e.status == 429:
                retry = getattr(e, "retry_after", 5)
                print(f"⚠ 429 rate limited, retrying invite in {retry}s...")
                await asyncio.sleep(retry + 1)
            else:
                raise
    return None

async def safe_send(channel, content, old_msg_id=None):
    if old_msg_id:
        try:
            msg = await channel.fetch_message(old_msg_id)
            await msg.edit(content=content)
            return msg
        except discord.NotFound:
            pass
        except discord.HTTPException as e:
            if e.status == 429:
                retry = getattr(e, "retry_after", 2)
                print(f"⚠ 429 rate limited, retrying edit in {retry}s...")
                await asyncio.sleep(retry + 1)
                return await safe_send(channel, content, old_msg_id)
            else:
                raise
    for attempt in range(5):
        try:
            return await channel.send(content)
        except discord.HTTPException as e:
            if e.status == 429:
                retry = getattr(e, "retry_after", 2)
                print(f"⚠ 429 rate limited, retrying send in {retry}s...")
                await asyncio.sleep(retry + 1)
            else:
                raise
    return None

# ───────── Invite system ─────────
@tasks.loop(hours=1)
async def refresh_invite():
    data = {}
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        except:
            data = {}

    message_ids = data.get("messages", {})

    guild = bot.get_guild(MAIN_GUILD_ID)
    if not guild:
        print("❌ Guild not found")
        return

    me = guild.get_member(bot.user.id)
    invite_channel = next(
        (ch for ch in guild.text_channels if ch.permissions_for(me).create_instant_invite),
        None
    )

    if not invite_channel:
        print("❌ No channel with invite permission")
        return

    invite = await safe_create_invite(invite_channel)
    if not invite:
        print("❌ Failed to create invite after retries")
        return

    for ch_id in POST_CHANNEL_IDS:
        channel = bot.get_channel(ch_id)
        if not channel:
            continue

        old_msg_id = message_ids.get(str(ch_id))
        msg = await safe_send(channel, f"JOIN THE MAIN SERVER\n{invite.url}", old_msg_id)
        if msg:
            message_ids[str(ch_id)] = msg.id

        # ✅ Small delay between channels to reduce burst
        await asyncio.sleep(2)

    data["messages"] = message_ids
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

# ───────── on_ready with startup delay ─────────
@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")

    # ✅ Delay only on startup/redeploy to avoid 429
    await asyncio.sleep(30)  # wait 30s before sending invites

    if not refresh_invite.is_running():
        refresh_invite.start()

    print("✅ Invite system active.")

# ───────── Start bot ─────────
bot.run(TOKEN)
