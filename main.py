"""
============================================================
BOT DE DISCORD 24/7 - CORRE EN RENDER.COM
============================================================

Este bot SIEMPRE está prendido y recibe comandos de Discord.
Se comunica con el Colab notebook via API web.

COMANDOS EN DISCORD:
- !prender → Muestra link de Colab para ejecutar
- !apagar  → Apaga el servidor remotamente
- !estado  → Ver si está online
- !ip      → Ver la IP
- !guardar → Guardar mundo en Drive remotamente
"""

import os
import json
import time
import threading
import asyncio
import discord
from discord.ext import commands
from flask import Flask, request, jsonify
import nest_asyncio

nest_asyncio.apply()

# ===== CONFIGURACIÓN (se lee de variables de entorno en Render) =====
TOKEN = os.environ.get("DISCORD_TOKEN", "")
CANAL_ID = int(os.environ.get("CANAL_ID", "0"))
API_SECRET = os.environ.get("API_SECRET", "changeme")
COLAB_LINK = os.environ.get("COLAB_LINK", "")
# =========================

# ===== ESTADO DEL SERVIDOR =====
server_status = {
    "status": "offline",
    "ip": "",
    "players": 0,
    "last_update": 0
}
pending_command = None
status_lock = threading.Lock()

# ===== FLASK API =====
app = Flask(__name__)

@app.route("/")
def home():
    """UptimeRobot pinguea acá para mantener Render despierto."""
    with status_lock:
        s = server_status["status"]
    return f"Bot de Minecraft activo | Servidor: {s}", 200

@app.route("/api/status", methods=["GET"])
def get_status():
    """El Colab consulta el estado y comandos pendientes."""
    with status_lock:
        return jsonify({
            "server": server_status,
            "command": pending_command
        })

@app.route("/api/status", methods=["POST"])
def update_status():
    """El Colab actualiza su estado."""
    global pending_command
    data = request.json or {}

    if data.get("secret") != API_SECRET:
        return jsonify({"error": "unauthorized"}), 401

    with status_lock:
        old_status = server_status["status"]
        server_status["status"] = data.get("status", "offline")
        server_status["ip"] = data.get("ip", server_status.get("ip", ""))
        server_status["players"] = data.get("players", 0)
        server_status["last_update"] = time.time()

        if data.get("command_received"):
            pending_command = None

    nuevo = server_status["status"]
    if old_status != nuevo:
        if nuevo == "online":
            avisar_discord(
                f"🟢 **El servidor esta ONLINE!**\n"
                f"📡 IP: `{server_status['ip']}`\n"
                f"🎮 ¡Conectense ya!"
            )
        elif nuevo == "starting":
            avisar_discord("🟡 **Servidor arrancando...** Esperen un momento.")
        elif nuevo == "offline" and old_status in ("online", "starting"):
            avisar_discord("🔴 **El servidor se APAGO.**")

    return jsonify({"ok": True})

@app.route("/api/command", methods=["POST"])
def send_command():
    """Envía un comando al Colab."""
    global pending_command
    data = request.json or {}
    if data.get("secret") != API_SECRET:
        return jsonify({"error": "unauthorized"}), 401

    with status_lock:
        pending_command = data.get("command", "")

    return jsonify({"ok": True})


# ===== BOT DE DISCORD =====

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)


def avisar_discord(mensaje):
    async def _avisar():
        await bot.wait_until_ready()
        canal = bot.get_channel(CANAL_ID)
        if canal:
            await canal.send(mensaje)
    try:
        loop = asyncio.get_event_loop()
        asyncio.run_coroutine_threadsafe(_avisar(), loop)
    except Exception as e:
        print(f"[DISCORD] Error: {e}")


@bot.event
async def on_ready():
    print(f"[BOT] Conectado como {bot.user}")
    canal = bot.get_channel(CANAL_ID)
    if canal:
        await canal.send(
            "🤖 **Bot del servidor activo (24/7 en Render).**\n"
            "Comandos:\n"
            "• `!prender` — Prende el servidor\n"
            "• `!apagar` — Apaga el servidor\n"
            "• `!estado` — Ver si esta online\n"
            "• `!ip` — Ver la IP\n"
            "• `!guardar` — Guardar el mundo en Drive"
        )


@bot.command(name="prender")
async def cmd_prender(ctx):
    with status_lock:
        status = server_status["status"]

    if status == "online":
        await ctx.send(f"🟢 El servidor ya esta ONLINE.\n📡 IP: `{server_status['ip']}`")
        return

    if status == "starting":
        await ctx.send("🟡 El servidor ya esta arrancando... Espera.")
        return

    if not COLAB_LINK:
        await ctx.send("⚠️ No esta configurado el link del Colab.")
        return

    await ctx.send(
        f"🟡 **Para prender el servidor:**\n"
        f"1. Abri este link: {COLAB_LINK}\n"
        f"2. Conecta el runtime (▶️ arriba a la derecha)\n"
        f"3. Ejecuta Runtime → Run all\n\n"
        f"⏳ El servidor arranca solo y aviso aca cuando este listo."
    )


@bot.command(name="apagar")
async def cmd_apagar(ctx):
    global pending_command

    with status_lock:
        status = server_status["status"]

    if status != "online":
        await ctx.send("⚠️ El servidor no esta online.")
        return

    with status_lock:
        pending_command = "stop"

    await ctx.send("🔴 **Enviando senal de apagado al servidor...**")


@bot.command(name="estado")
async def cmd_estado(ctx):
    with status_lock:
        status = server_status["status"]
        ip = server_status["ip"]
        last = server_status["last_update"]

    if status == "online":
        minutos = int((time.time() - last) / 60) if last else 0
        await ctx.send(
            f"🟢 **Servidor ONLINE**\n"
            f"📡 IP: `{ip}`\n"
            f"⏱️ Ultimo update: hace {minutos} min"
        )
    elif status == "starting":
        await ctx.send("🟡 **Servidor ARRANCANDO...**")
    else:
        await ctx.send(
            "🔴 **Servidor OFFLINE**\n"
            f"Usa `!prender` para encenderlo."
        )


@bot.command(name="ip")
async def cmd_ip(ctx):
    with status_lock:
        ip = server_status["ip"]

    if ip:
        await ctx.send(f"📡 **IP del servidor:** `{ip}`")
    else:
        await ctx.send("⚠️ No hay IP registrada. El servidor probablemente esta apagado.")


@bot.command(name="guardar")
async def cmd_guardar(ctx):
    global pending_command

    with status_lock:
        status = server_status["status"]

    if status != "online":
        await ctx.send("⚠️ El servidor no esta online, no se puede guardar.")
        return

    with status_lock:
        pending_command = "save-all"

    await ctx.send("💾 **Enviando senal de guardado...**")


# ===== MONITOR DE SALUD =====

def health_monitor():
    while True:
        time.sleep(60)
        with status_lock:
            if server_status["status"] == "online":
                elapsed = time.time() - server_status["last_update"]
                if elapsed > 300:
                    print("[MONITOR] Colab no responde, marcando offline")
                    server_status["status"] = "offline"
                    avisar_discord(
                        "⚠️ **El servidor no responde hace 5 minutos.** "
                        "Probablemente se desconecto Colab."
                    )


# ===== INICIO =====

def run_flask():
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)), use_reloader=False)


if __name__ == "__main__":
    print("=" * 50)
    print("  MINECRAFT BOT 24/7 - RENDER")
    print("=" * 50)

    threading.Thread(target=run_flask, daemon=True).start()
    threading.Thread(target=health_monitor, daemon=True).start()

    print("[BOT] Iniciando bot de Discord...")
    bot.run(TOKEN)
