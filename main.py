import asyncio
import discord
from discord.ext import commands, tasks
import traceback
import os
import json
import time

TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    raise ValueError("DISCORD_TOKEN environment variable is missing!")

intents = discord.Intents.default()
intents.members = True
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# Kick & Invite queues (from previous code)
kick_queue = asyncio.Queue()
invite_queue = asyncio.Queue()

async def rate_limit_safe(func, *args, **kwargs):
    for attempt in range(10):
        try:
            return await func(*args, **kwargs)
        except discord.HTTPException as e:
            content = getattr(e, "text", "")
            # Detect Cloudflare block HTML
            if "<!doctype html>" in content:
                retry = min(30, 2 ** attempt)  # exponential backoff
                print(f"⚠ Cloudflare block detected, retrying in {retry}s...")
                await asyncio.sleep(retry)
            elif e.status == 429:
                retry = getattr(e, "retry_after", 1)
                print(f"⚠ Discord 429, retrying in {retry}s...")
                await asyncio.sleep(retry + 0.1)
            else:
                raise
    return None

# Example safe_send using rate_limit_safe
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

# Startup-safe on_ready with Cloudflare handling
@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    print("⏳ Waiting 20s to avoid Cloudflare / 429 issues...")
    await asyncio.sleep(20)  # long initial wait
    # Start workers, scan members, schedule kicks, etc.
    # (Insert your previous worker and scheduling setup here)
    if not refresh_invite.is_running():
        refresh_invite.start()
    if not scan_servers_for_members.is_running():
        scan_servers_for_members.start()
    print("✅ Bot is fully operational.")

# Retry bot.run on unexpected exit
async def start_bot():
    while True:
        try:
            bot.run(TOKEN)
        except Exception:
            print("❌ Bot crashed, retrying in 10s...")
            traceback.print_exc()
            await asyncio.sleep(10)

# Only needed if using asyncio loop for start_bot
# asyncio.run(start_bot())
