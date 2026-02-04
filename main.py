import discord
from discord.ext import commands, tasks
import json
import threading
from flask import Flask
import os
import asyncio
import traceback

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
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    if not refresh_invite.is_running():
        refresh_invite.start()

# ───────────── AUTO KICK ─────────────
@bot.event
async def on_member_join(member):
    if member.bot:
        return

    await asyncio.sleep(AUTO_KICK_DELAY)

    if member.guild.get_member(member.id) is None:
        return

    try:
        await member.kick(reason="Auto-kick after 5 minutes")
        print(f"👢 Auto-kicked {member} from {member.guild.name}")
    except discord.Forbidden:
        print(f"❌ Missing kick permission in {member.guild.name}")
    except Exception as e:
        print(f"❌ Auto-kick failed: {e}")

# ───────────── INVITE LOOP ─────────────
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
                print(f"❌ Channel not found: {ch_id}")
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

            except discord.NotFound:
                msg = await channel.send(f"JOIN THE MAIN SERVER\n{invite.url}")
                new_message_ids[str(ch_id)] = msg.id
                await asyncio.sleep(1)
                return

            except discord.HTTPException as e:
                if e.status == 429:
                    print(f"⏳ Rate limited in {ch_id}, retrying…")
                    await asyncio.sleep(65)
                    continue
                else:
                    print(f"❌ HTTP error in {ch_id}: {e}")
                    return

            except Exception as e:
                print(f"❌ Unexpected error in {ch_id}: {e}")
                return

    await asyncio.gather(*(update_channel(ch_id) for ch_id in POST_CHANNEL_IDS))

    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump({"messages": new_message_ids}, f, indent=2)
    except Exception as e:
        print(f"❌ Failed to save data: {e}")

@refresh_invite.before_loop
async def before_refresh():
    await bot.wait_until_ready()

# ───────────── RUN BOT ─────────────
try:
    bot.run(TOKEN)
except Exception:
    print("❌ Bot crashed:")
    traceback.print_exc()
