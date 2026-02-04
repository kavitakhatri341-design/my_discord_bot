import discord
from discord.ext import commands, tasks
import asyncio
import json
import os
import threading
import time
import traceback
from flask import Flask

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

# ───────── Flask keep-alive ─────────
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
intents.members = True
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

kick_lock = asyncio.Lock()
kick_data = {}

KICK_DATA_FILE = "kick_data.json"
if os.path.exists(KICK_DATA_FILE):
    with open(KICK_DATA_FILE, "r") as f:
        try:
            kick_data = json.load(f)
        except:
            kick_data = {}

kick_queue = asyncio.Queue()
invite_queue = asyncio.Queue()

# ───────── Helpers ─────────
async def rate_limit_safe(func, *args, **kwargs):
    for attempt in range(10):
        try:
            return await func(*args, **kwargs)
        except discord.HTTPException as e:
            content = getattr(e, "text", "")
            if "<!doctype html>" in content:  # Cloudflare block
                retry = min(30, 2 ** attempt)
                print(f"⚠ Cloudflare block, retrying in {retry}s...")
                await asyncio.sleep(retry)
            elif e.status == 429:
                retry = getattr(e, "retry_after", 1)
                print(f"⚠ Discord 429, retrying in {retry}s...")
                await asyncio.sleep(retry + 0.1)
            else:
                raise
    return None

async def safe_kick(member):
    return await rate_limit_safe(member.kick, reason="Auto kick every 5 minutes")

async def safe_send(channel, content=None, fetch_msg_id=None):
    if fetch_msg_id:
        try:
            msg = await rate_limit_safe(channel.fetch_message, fetch_msg_id)
            if msg:
                await rate_limit_safe(msg.edit, content=content)
                return msg
        except discord.NotFound:
            pass
    return await rate_limit_safe(channel.send, content=content)

async def schedule_kick(user_id, guild_id, channel_id, first_join_time):
    remaining = max(0, KICK_DELAY_SECONDS - (time.time() - first_join_time))
    await asyncio.sleep(remaining)
    guild = bot.get_guild(guild_id)
    if not guild:
        return
    member = guild.get_member(int(user_id))
    if member and not member.bot:
        if any(role.id in SAFE_ROLE_IDS for role in member.roles):
            async with kick_lock:
                kick_data.pop(f"{guild_id}-{user_id}", None)
                with open(KICK_DATA_FILE, "w") as f:
                    json.dump(kick_data, f, indent=2)
            return
        await kick_queue.put((member, channel_id))

# ───────── Workers ─────────
async def kick_worker():
    while True:
        member, channel_id = await kick_queue.get()
        await safe_kick(member)
        notify_channel = bot.get_channel(channel_id)
        if notify_channel:
            await safe_send(notify_channel, f"User <@{member.id}> has been kicked")
        async with kick_lock:
            key = f"{member.guild.id}-{member.id}"
            kick_data.pop(key, None)
            with open(KICK_DATA_FILE, "w") as f:
                json.dump(kick_data, f, indent=2)
        kick_queue.task_done()

async def invite_worker():
    while True:
        channel, content, old_msg_id = await invite_queue.get()
        await safe_send(channel, content, fetch_msg_id=old_msg_id)
        invite_queue.task_done()

async def start_workers():
    for _ in range(2):
        asyncio.create_task(kick_worker())
    for _ in range(2):
        asyncio.create_task(invite_worker())

# ───────── Periodic scan ─────────
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
                if member.bot or any(role.id in SAFE_ROLE_IDS for role in member.roles):
                    continue
                key = f"{guild_id}-{member.id}"
                if key not in kick_data:
                    kick_data[key] = {
                        "first_join": time.time(),
                        "guild_id": guild_id,
                        "channel_id": channel_id,
                        "user_id": str(member.id)
                    }
                    with open(KICK_DATA_FILE, "w") as f:
                        json.dump(kick_data, f, indent=2)
                    asyncio.create_task(schedule_kick(str(member.id), guild_id, channel_id, kick_data[key]["first_join"]))
                    await asyncio.sleep(0.05)

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
    invite_channel = next((ch for ch in guild.text_channels if ch.permissions_for(me).create_instant_invite), None)
    if not invite_channel:
        print("❌ No channel with invite permission")
        return

    try:
        invite = await rate_limit_safe(invite_channel.create_invite, max_age=3600, max_uses=0, unique=True, reason="Hourly invite refresh")
    except Exception as e:
        print(f"❌ Invite creation failed: {e}")
        return

    for ch_id in POST_CHANNEL_IDS:
        channel = bot.get_channel(ch_id)
        if not channel:
            continue
        old_msg_id = message_ids.get(str(ch_id))
        await invite_queue.put((channel, f"JOIN THE MAIN SERVER\n{invite.url}", old_msg_id))

# ───────── on_ready ─────────
@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    print("⏳ Waiting 20s to avoid Cloudflare / 429 issues...")
    await asyncio.sleep(20)
    await start_workers()
    async with kick_lock:
        for key, info in kick_data.items():
            asyncio.create_task(schedule_kick(info["user_id"], info["guild_id"], info["channel_id"], info["first_join"]))
    if not scan_servers_for_members.is_running():
        scan_servers_for_members.start()
    if not refresh_invite.is_running():
        refresh_invite.start()
    print("✅ Bot fully operational.")

# ───────── Supervisor loop with exponential backoff ─────────
async def start_bot_forever():
    backoff = 5
    while True:
        try:
            await bot.start(TOKEN)
            backoff = 5
        except discord.HTTPException as e:
            if e.status == 429:
                print(f"⚠ Global 429 at login, retrying in {backoff}s...")
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 300)  # max 5 min
            else:
                traceback.print_exc()
                await asyncio.sleep(10)
        except Exception:
            traceback.print_exc()
            await asyncio.sleep(10)

# ───────── Start bot safely on Render ─────────
async def delayed_start():
    await asyncio.sleep(15)  # avoid immediate burst on container start
    await start_bot_forever()

loop = asyncio.get_event_loop()
loop.create_task(delayed_start())
loop.run_forever()
