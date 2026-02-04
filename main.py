import discord
from discord.ext import commands, tasks
import json
import threading
from flask import Flask
import os
import asyncio
import traceback
import time
import random

# ───────────── CONFIG ─────────────
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

KICK_GUILD_IDS = [
    1461096482558972046,
    1461095575280681055,
    1461599680889753610,
    1461601614086406310,
    1462054805437415529,
    1462055057917874190,
    1462136557803671845,
    1462137621517177134,
]

KICK_NOTIFY_CHANNELS = {
    1461096482558972046: 1461096483825914143,
    1461095575280681055: 1461095577231298820,
    1461599680889753610: 1461599681569362083,
    1461601614086406310: 1461601615411810511,
    1462054805437415529: 1462054807002021961,
    1462055057917874190: 1462055058920177696,
    1462136557803671845: 1462136558802047276,
    1462137621517177134: 1462137623320596572
}

KICK_DELAY_SECONDS = 300  # 5 minutes

SAFE_ROLE_IDS = [
    1461096482558972048,
    1461095575280681057,
    1461599680889753612,
    1461601614086406312,
    1462054805437415531,
    1462055057917874192,
    1462136557803671847,
    1462137621517177136
]

# ───────────── Flask keep-alive ─────────────
app = Flask("")

@app.route("/")
def home():
    return "Bot is running!"

def run_flask():
    port = int(os.getenv("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)

threading.Thread(target=run_flask, daemon=True).start()

# ───────────── Discord bot ─────────────
intents = discord.Intents.default()
intents.members = True
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

kick_lock = asyncio.Lock()
kick_data = {}

# Load kick data
if os.path.exists("kick_data.json"):
    with open("kick_data.json", "r") as f:
        try:
            kick_data = json.load(f)
        except:
            kick_data = {}

# ───────────── Helpers ─────────────
async def safe_kick(member):
    """Kick a member safely with rate-limit handling."""
    for _ in range(5):
        try:
            await member.kick(reason="Auto kick every 5 minutes")
            return True
        except discord.HTTPException as e:
            if e.status == 429:
                retry_after = getattr(e, "retry_after", 5)
                await asyncio.sleep(retry_after + random.uniform(0, 1))
            else:
                return False
    return False

async def schedule_kick(user_id, guild_id, channel_id, first_join_time):
    now = time.time()
    remaining = max(0, KICK_DELAY_SECONDS - (now - first_join_time))
    await asyncio.sleep(remaining)

    guild = bot.get_guild(guild_id)
    if not guild:
        return
    member = guild.get_member(int(user_id))
    if member and not member.bot:
        if any(role.id in SAFE_ROLE_IDS for role in member.roles):
            async with kick_lock:
                key = f"{guild_id}-{user_id}"
                kick_data.pop(key, None)
                with open("kick_data.json", "w") as f:
                    json.dump(kick_data, f, indent=2)
            return
        if await safe_kick(member):
            notify_channel = guild.get_channel(channel_id)
            if notify_channel:
                try:
                    await notify_channel.send(f"User <@{user_id}> has been kicked from the server.")
                    await asyncio.sleep(1)  # small delay to avoid 429
                except:
                    pass
    async with kick_lock:
        key = f"{guild_id}-{user_id}"
        kick_data.pop(key, None)
        with open("kick_data.json", "w") as f:
            json.dump(kick_data, f, indent=2)

async def schedule_existing_kicks():
    async with kick_lock:
        for key, info in kick_data.items():
            asyncio.create_task(schedule_kick(
                info["user_id"], info["guild_id"], info["channel_id"], info["first_join"]
            ))

# ───────────── Periodic scan ─────────────
@tasks.loop(seconds=30)
async def scan_servers_for_members():
    async with kick_lock:
        for guild_id in KICK_GUILD_IDS:
            guild = bot.get_guild(guild_id)
            if not guild:
                continue
            channel_id = KICK_NOTIFY_CHANNELS.get(guild_id)
            if not channel_id:
                continue
            for member in guild.members:
                if member.bot:
                    continue
                if any(role.id in SAFE_ROLE_IDS for role in member.roles):
                    continue
                key = f"{guild_id}-{member.id}"
                if key not in kick_data:
                    kick_data[key] = {
                        "first_join": time.time(),
                        "guild_id": guild_id,
                        "channel_id": channel_id,
                        "user_id": str(member.id)
                    }
                    with open("kick_data.json", "w") as f:
                        json.dump(kick_data, f, indent=2)
                    asyncio.create_task(schedule_kick(
                        str(member.id), guild_id, channel_id, kick_data[key]["first_join"]
                    ))
                    await asyncio.sleep(1)  # small delay to avoid 429

# ───────────── Invite system ─────────────
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
    invite_channel = None
    for ch in guild.text_channels:
        if ch.permissions_for(me).create_instant_invite:
            invite_channel = ch
            break
    if not invite_channel:
        print("❌ No channel with invite permission")
        return

    try:
        invite = await invite_channel.create_invite(
            max_age=3600,
            max_uses=0,
            unique=True,
            reason="Hourly invite refresh"
        )
    except Exception as e:
        print(f"❌ Invite creation failed: {e}")
        return

    new_message_ids = {}

    for ch_id in POST_CHANNEL_IDS:
        channel = bot.get_channel(ch_id)
        if not channel:
            continue
        old_msg_id = message_ids.get(str(ch_id))
        try:
            if old_msg_id:
                msg = await channel.fetch_message(old_msg_id)
                await msg.edit(content=f"JOIN THE MAIN SERVER\n{invite.url}")
            else:
                msg = await channel.send(f"JOIN THE MAIN SERVER\n{invite.url}")
            new_message_ids[str(ch_id)] = msg.id
        except discord.HTTPException as e:
            if e.status == 429:
                retry_after = getattr(e, "retry_after", 5)
                await asyncio.sleep(retry_after + random.uniform(0, 1))
            else:
                continue
        await asyncio.sleep(1)  # small delay to avoid 429

    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump({"messages": new_message_ids}, f, indent=2)
    except Exception as e:
        print(f"❌ Failed to save data: {e}")

@refresh_invite.before_loop
async def before_refresh():
    await bot.wait_until_ready()

# ───────────── Bot events ─────────────
@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    await schedule_existing_kicks()
    if not scan_servers_for_members.is_running():
        scan_servers_for_members.start()
    if not refresh_invite.is_running():
        refresh_invite.start()

# ───────────── RUN BOT ─────────────
try:
    bot.run(TOKEN)
except Exception:
    print("❌ Bot crashed:")
    traceback.print_exc()
