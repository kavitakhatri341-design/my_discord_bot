import discord
from discord.ext import commands, tasks
import json
import threading
from flask import Flask
import os
import asyncio
import traceback
import time

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
JOIN_DATA_FILE = "joins.json"
AUTO_KICK_DELAY = 300  # 5 minutes

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

bot = commands.Bot(command_prefix="!", intents=intents)

# ───────────── HELPERS ─────────────
def load_joins():
    if not os.path.exists(JOIN_DATA_FILE):
        return {}
    with open(JOIN_DATA_FILE, "r") as f:
        return json.load(f)

def save_joins(data):
    with open(JOIN_DATA_FILE, "w") as f:
        json.dump(data, f)

def is_post_server(guild: discord.Guild):
    return any(guild.get_channel(ch_id) for ch_id in POST_CHANNEL_IDS)

# ───────────── JOIN TRACKING ─────────────
@bot.event
async def on_member_join(member):
    if member.bot:
        return

    if member.guild.id == MAIN_GUILD_ID:
        return

    if not is_post_server(member.guild):
        return

    joins = load_joins()
    joins[str(member.id)] = {
        "guild_id": member.guild.id,
        "joined_at": time.time()
    }
    save_joins(joins)

    print(f"🕒 Tracking {member} in {member.guild.name}")

@bot.event
async def on_member_remove(member):
    joins = load_joins()
    joins.pop(str(member.id), None)
    save_joins(joins)

# ───────────── AUTO KICK LOOP ─────────────
@tasks.loop(seconds=30)
async def auto_kick_check():
    joins = load_joins()
    now = time.time()
    changed = False

    for user_id, data in list(joins.items()):
        if now - data["joined_at"] >= AUTO_KICK_DELAY:
            guild = bot.get_guild(data["guild_id"])
            if not guild:
                joins.pop(user_id)
                changed = True
                continue

            member = guild.get_member(int(user_id))
            if member:
                try:
                    await member.kick(reason="Auto-kick after 5 minutes")
                    print(f"👢 Kicked {member} from {guild.name}")
                except Exception as e:
                    print(f"❌ Kick failed: {e}")

            joins.pop(user_id)
            changed = True

    if changed:
        save_joins(joins)

# ───────────── INVITE LOOP (UNCHANGED) ─────────────
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

    async def update_channel(ch_id):
        while True:
            channel = bot.get_channel(ch_id)
            if not channel:
                return

            old_msg_id = message_ids.get(str(ch_id))

            try:
                if old_msg_id:
                    msg = await channel.fetch_message(old_msg_id)
                    await msg.edit(content=f"JOIN THE MAIN SERVER\n{invite.url}")
                else:
                    msg = await channel.send(f"JOIN THE MAIN SERVER\n{invite.url}")

                new_message_ids[str(ch_id)] = msg.id
                await asyncio.sleep(1)
                return

            except discord.HTTPException as e:
                if e.status == 429:
                    await asyncio.sleep(65)
                else:
                    return

    await asyncio.gather(*(update_channel(ch_id) for ch_id in POST_CHANNEL_IDS))

    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump({"messages": new_message_ids}, f, indent=2)

@refresh_invite.before_loop
async def before_refresh():
    await bot.wait_until_ready()

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    if not refresh_invite.is_running():
        refresh_invite.start()
    if not auto_kick_check.is_running():
        auto_kick_check.start()

# ───────────── RUN BOT ─────────────
try:
    bot.run(TOKEN)
except Exception:
    print("❌ Bot crashed:")
    traceback.print_exc()
