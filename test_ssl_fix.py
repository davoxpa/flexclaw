"""Test standalone per verificare il fix SSL del bot Discord."""
import asyncio
import os
import ssl

import aiohttp
import certifi
import discord
from dotenv import load_dotenv

load_dotenv()

token = os.environ.get("DISCORD_TOKEN")

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)

# Stessa logica del fix in bot.py
_original_static_login = client.http.static_login


async def _static_login_with_ssl(token_val):
    ssl_ctx = ssl.create_default_context(cafile=certifi.where())
    client.http.connector = aiohttp.TCPConnector(limit=0, ssl=ssl_ctx)
    return await _original_static_login(token_val)


client.http.static_login = _static_login_with_ssl


@client.event
async def on_ready():
    print(f"SUCCESSO! Connesso come {client.user} (ID: {client.user.id})")
    print(f"Server: {len(client.guilds)}")
    await client.close()


print("Avvio test connessione Discord con fix SSL...")
client.run(token, log_handler=None)
print("Test completato senza errori!")
