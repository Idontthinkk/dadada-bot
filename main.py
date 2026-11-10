import discord
from discord.ext import commands, tasks
from discord import app_commands
import os
import datetime
import asyncio
import aiohttp
import re
import random
import sqlite3
from dotenv import load_dotenv
import database as db

load_dotenv()

TOKEN = os.getenv('DISCORD_TOKEN')
FIREBASE_URL = "https://ssrpbot-2ac7b-default-rtdb.firebaseio.com" 

VERIFY_CHANNEL_ID = 1569796058413015090 

KAP_GUILD_ID = 1294612883304353812
MAIN_GUILD_ID = 1292881174443720767
KAP_FORUM_ID = 1566139891258097664
CHSP_FORUM_ID = 1568020029117562900
APPEAL_LINK = "https://discord.gg/QUUVRgMqMN"

KAP_OBJ = discord.Object(id=KAP_GUILD_ID)
MAIN_OBJ = discord.Object(id=MAIN_GUILD_ID)

CREATOR_ID = 939996361712074832
OCHS_ROLE_1 = 1360357746972819476
OCHS_ROLE_2 = 1358192820900466932

VERIFY_ROLE_ID = 1569799728210772059 
UNREGISTERED_ROLE_ID = 1511000147969048699
ROBLOX_PLACE_LINK = "https://www.roblox.com/games/86704551294131/1979"

MAIN_MENU_IMAGE = "https://media.discordapp.net/attachments/1511004157535060058/1565492447872557128/image.png?ex=6af44335&is=6af2f1b5&hm=e4183d233b4e591df5a245feebbb017c5d229167bd9ad79ac337fb613cf06f86&=&format=webp&quality=lossless&width=1593&height=856"

GUILDS = {
    1252308402722574416: "Аэрофлот", 1294972362197958656: "Пожарка",
    1463920187790201047: "Милиция", 1273012886398177280: "Госплан (СМИ)",
    1555942702972014683: "Школа КГБ", 1561746093711302687: "Горком Магадана",
    1161675556681678960: "КГБ", 1518322515364024340: "Минобороны",
    1479813733000675515: "Прока", 1518921136111485070: "ВВС",
    1519275056809775146: "ВМФ", 1548348491150131200: "ОПГ",
    1292881174443720767: "Основной сервер проекта", 1294612883304353812: "Сервер КАП"
}

intents = discord.Intents.default()
intents.members = True
intents.message_content = True

# =====================================================================
# КНОПКИ И GUI
# =====================================================================
class VerifyCheckView(discord.ui.View):
    def __init__(self, code):
        super().__init__(timeout=None)
        self.code = code

    @discord.ui.button(label="Проверить", style=discord.ButtonStyle.primary, custom_id="btn_check_after_code")
    async def check_after(self, interaction: discord.Interaction, button: discord.ui.Button):
        roblox_id = db.check_link(interaction.user.id)
        if roblox_id:
            await interaction.response.send_message(f"✅ **Успех!** Аккаунт привязан (Roblox ID: `{roblox_id}`).\nПриятной игры на проекте!", ephemeral=True)
            button.disabled = True
            try:
                await interaction.message.edit(view=self)
            except discord.NotFound:
                pass
        else:
            await interaction.response.send_message("⏳ Бот еще не получил данные от плейса. Введите код в игре и подождите 10 секунд.", ephemeral=True)

class VerifyStartView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Пройти верификацию", style=discord.ButtonStyle.success, custom_id="btn_start_verify")
    async def start_verify(self, interaction: discord.Interaction, button: discord.ui.Button):
        if db.check_link(interaction.user.id):
            guild = bot.get_guild(MAIN_GUILD_ID)
            member = guild.get_member(interaction.user.id)
            if member:
                role_verify = guild.get_role(VERIFY_ROLE_ID)
                role_unreg = guild.get_role(UNREGISTERED_ROLE_ID)
                if role_verify and role_verify not in member.roles: await member.add_roles(role_verify)
                if role_unreg and role_unreg in member.roles: await member.remove_roles(role_unreg)
            return await interaction.response.send_message("✅ Вы уже верифицированы! Роль выдана.", ephemeral=True)

        code = f"SSRP-{random.randint(10000, 99999)}"
        await push_code_to_firebase(code, interaction.user.id)
        
        view = discord.ui.View()
        view.add_item(discord.ui.Button(label="Перейти в плейс", style=discord.ButtonStyle.link, url=ROBLOX_PLACE_LINK))
        
        embed = discord.Embed(
            title="Инструкция по верификации",
            description=f"1. Ваш код: **`{code}`**\n"
                        f"2. Нажмите кнопку ниже, чтобы зайти в плейс.\n"
                        f"3. Введите этот код в игре.\n\n"
                        f"*Код действует 10 минут.*",
            color=discord.Color.blue()
        )
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

# =====================================================================
# БОТ
# =====================================================================
class MyBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        db.init_db()
        self.add_view(VerifyStartView()) 
        self.add_view(VerifyCheckView("")) 
        
        # ГЛОБАЛЬНАЯ СИНХРОНИЗАЦИЯ (для всех серверов)
        await self.tree.sync()
        print("[+] Команды синхронизированы глобально.")

    async def on_ready(self):
        print(f'[+] Бот запущен как {self.user}')
        if VERIFY_CHANNEL_ID != 0:
            channel = self.get_channel(VERIFY_CHANNEL_ID)
            if channel:
                found_panel = False
                async for msg in channel.history(limit=20):
                    if msg.author == self.user and msg.embeds and msg.components:
                        found_panel = True
                        break
                
                if not found_panel:
                    embed = discord.Embed(
                        title="Верификация аккаунта",
                        description="Нажмите на кнопку ниже, чтобы привязать аккаунт Roblox к вашему Discord.\n\n*Безопасно: мы не запрашиваем данные вашего аккаунта, вы просто зайдете в плейс.*",
                        color=discord.Color.blue()
                    )
                    embed.set_image(url=MAIN_MENU_IMAGE)
                    await channel.send(embed=embed, view=VerifyStartView())

        if not firebase_verification_loop.is_running(): firebase_verification_loop.start()
        if not monitor_chsp.is_running(): monitor_chsp.start()
        if not check_deadlines_loop.is_running(): check_deadlines_loop.start()

bot = MyBot()

# =====================================================================
# АВТО-ВЫДАЧА РОЛИ "НЕЗАРЕГИСТРИРОВАН"
# =====================================================================
@bot.event
async def on_member_join(member):
    if member.guild.id == MAIN_GUILD_ID:
        role = member.guild.get_role(UNREGISTERED_ROLE_ID)
        if role:
            try: await member.add_roles(role)
            except: pass

# =====================================================================
# ПРОВЕРКА ПРАВ
# =====================================================================
def is_creator():
    async def predicate(interaction: discord.Interaction):
        return interaction.user.id == CREATOR_ID
    return app_commands.check(predicate)

def is_ochs_staff():
    async def predicate(interaction: discord.Interaction):
        if interaction.user.id == CREATOR_ID: return True
        return any(role.id in [OCHS_ROLE_1, OCHS_ROLE_2] for role in interaction.user.roles)
    return app_commands.check(predicate)

@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.CheckFailure):
        await interaction.response.send_message(embed=discord.Embed(description="## ❌ У вас нет прав.", color=discord.Color(16711680)), ephemeral=True)

# =====================================================================
# ФУНКЦИИ ДЛЯ РОБЛОКСА
# =====================================================================
async def get_all_group_members(group_id):
    members = set()
    cursor = ""
    headers = {"User-Agent": "Mozilla/5.0"}
    
    async with aiohttp.ClientSession() as session:
        while True:
            url = f"https://groups.roblox.com/v1/groups/{group_id}/users?limit=100&sortOrder=Asc"
            if cursor: url += f"&cursor={cursor}"
            
            try:
                async with session.get(url, headers=headers) as resp:
                    if resp.status == 403: return None
                    if resp.status == 429:
                        await asyncio.sleep(5)
                        continue
                    if resp.status != 200: break
                    
                    data = await resp.json()
                    for user in data.get("data", []):
                        members.add(user["user"]["userId"])
                    
                    cursor = data.get("nextPageCursor")
                    if not cursor: break
                    await asyncio.sleep(0.5)
            except Exception as e:
                print(f"[!] Ошибка парсинга группы {group_id}: {e}")
                break
    return members

async def get_roblox_display_name(roblox_id):
    url = f"https://users.roblox.com/v1/users/{roblox_id}"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=5) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get("displayName") or data.get("name")
    except: pass
    return None

async def get_user_roblox_groups(roblox_id):
    url = f"https://groups.roblox.com/v1/users/{roblox_id}/groups/roles"
    headers = {"User-Agent": "Mozilla/5.0"}
    for attempt in range(2):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, timeout=10) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return [group["group"]["id"] for group in data.get("data", [])]
                    elif resp.status == 429:
                        await asyncio.sleep(60)
                        continue
                    else: return []
        except Exception: await asyncio.sleep(2)
    return []

async def get_group_info(group_id):
    url = f"https://groups.roblox.com/v1/groups/{group_id}"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get("name", "Неизвестная группа")
    except: pass
    return "Неизвестная группа"

def extract_group_id(link: str):
    link = link.strip()
    if link.isdigit(): return int(link)
    match = re.search(r'(?:groups|communities)/(\d+)', link)
    if match: return int(match.group(1))
    return None

# =====================================================================
# ВЕРИФИКАЦИЯ
# =====================================================================
async def push_code_to_firebase(code, discord_id):
    url = f"{FIREBASE_URL}/codes/{code}.json"
    data = {"discord_id": discord_id, "status": "pending"}
    try:
        async with aiohttp.ClientSession() as session:
            await session.put(url, json=data)
    except Exception as e: print(f"[!] Firebase Error: {e}")

async def check_firebase_codes():
    url = f"{FIREBASE_URL}/codes.json"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                data = await resp.json()
                if data:
                    for code, info in data.items():
                        if info.get("status") == "activated":
                            discord_id = info.get("discord_id")
                            roblox_id = info.get("roblox_id")
                            roblox_name = info.get("roblox_name", "")
                            avatar_url = info.get("avatar_url", "")
                            
                            db.link_user(discord_id, roblox_id)
                            
                            guild = bot.get_guild(MAIN_GUILD_ID)
                            member = guild.get_member(discord_id)
                            if member:
                                role_verify = guild.get_role(VERIFY_ROLE_ID)
                                role_unreg = guild.get_role(UNREGISTERED_ROLE_ID)
                                if role_verify: await member.add_roles(role_verify)
                                if role_unreg and role_unreg in member.roles: await member.remove_roles(role_unreg)
                                
                                try:
                                    if roblox_name and roblox_name.strip() != "":
                                        ds_display = member.display_name
                                        new_nick = f"{ds_display} (@{roblox_name})"
                                        if len(new_nick) > 32: new_nick = roblox_name
                                        if len(new_nick) > 32: new_nick = new_nick[:32]
                                        await member.edit(nick=new_nick)
                                except: pass

                                try:
                                    embed = discord.Embed(
                                        title="✅ Успешная верификация!",
                                        description="Ваш аккаунт Discord успешно привязан к Roblox.\n"
                                                    "Теперь вам доступны все серверы проекта ССРП.\n\n"
                                                    "**Если это не ваш аккаунт**, немедленно напишите в техническую поддержку проекта.\n\n"
                                                    "*Приятной игры на проекте!*",
                                        color=discord.Color.green()
                                    )
                                    embed.add_field(name="Ваш Discord", value=member.mention, inline=True)
                                    embed.add_field(name="Ваш Roblox", value=f"[Профиль](https://www.roblox.com/users/{roblox_id}/profile)\nID: `{roblox_id}`", inline=True)
                                    if avatar_url: embed.set_thumbnail(url=avatar_url)
                                    await member.send(embed=embed)
                                except: pass

                            await session.delete(f"{FIREBASE_URL}/codes/{code}.json")
    except Exception: pass

@tasks.loop(seconds=10)
async def firebase_verification_loop(): await check_firebase_codes()

# =====================================================================
# КОМАНДЫ
# =====================================================================

# --- АДМИНСКИЕ КОМАНДЫ ---
@bot.tree.command(name="обновитьник", description="[АДМИН] Обновить ники всем верифицированным")
@is_creator()
async def update_all_nicks(interaction: discord.Interaction):
    await interaction.response.send_message("⏳ Начинаю обновление ников для всех верифицированных...")
    
    try:
        conn = sqlite3.connect(db.DB_NAME)
        c = conn.cursor()
        c.execute("SELECT discord_id, roblox_id FROM links")
        linked_users = c.fetchall()
        conn.close()
    except Exception as e:
        return await interaction.followup.send(f"❌ Ошибка БД: {e}")

    guild = bot.get_guild(MAIN_GUILD_ID)
    if not guild:
        return await interaction.followup.send("❌ Бот не видит Основной сервер.")

    updated_count = 0
    error_count = 0
    no_rights = 0

    for discord_id, roblox_id in linked_users:
        member = guild.get_member(discord_id)
        if not member: continue

        roblox_name = await get_roblox_display_name(roblox_id)
        await asyncio.sleep(1.2) 
        
        if not roblox_name:
            error_count += 1
            continue

        try:
            ds_display = member.display_name
            new_nick = f"{ds_display} (@{roblox_name})"
            if len(new_nick) > 32: new_nick = roblox_name
            if len(new_nick) > 32: new_nick = new_nick[:32]
            await member.edit(nick=new_nick)
            updated_count += 1
        except discord.Forbidden:
            no_rights += 1
        except:
            error_count += 1

    await interaction.followup.send(f"✅ Готово!\nОбновлено: **{updated_count}**\nОшибка API: **{error_count}**\nНет прав: **{no_rights}**")

@bot.tree.command(name="список_зареганных", description="[АДМИН] Показать всех верифицированных игроков")
@is_creator()
async def list_registered(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    
    try:
        conn = sqlite3.connect(db.DB_NAME)
        c = conn.cursor()
        c.execute("SELECT discord_id, roblox_id FROM links")
        linked_users = c.fetchall()
        conn.close()
    except Exception as e:
        return await interaction.followup.send(f"❌ Ошибка БД: {e}")

    if not linked_users:
        return await interaction.followup.send("📭 В базе пока нет ни одного верифицированного игрока (список пуст).")

    guild = bot.get_guild(MAIN_GUILD_ID)
    if not guild:
        return await interaction.followup.send("❌ Бот не видит Основной сервер (проверьте ID).")
    
    chunks = [linked_users[i:i + 15] for i in range(0, len(linked_users), 15)]
    
    for idx, chunk in enumerate(chunks):
        embed = discord.Embed(
            title=f"📋 Список зарегистрированных (Стр. {idx + 1} из {len(chunks)})",
            color=discord.Color.blue()
        )
        
        text = ""
        for discord_id, roblox_id in chunk:
            member = guild.get_member(discord_id) if guild else None
            name = member.mention if member else f"`{discord_id}`"
            text += f"{name} | Roblox ID: `{roblox_id}`\n"
            
        embed.description = text
        embed.set_footer(text=f"Всего в базе: {len(linked_users)}")
        await interaction.followup.send(embed=embed, ephemeral=True)

@bot.tree.command(name="debug_chsp", description="[АДМИН] Показать, кто из верифицированных состоит в группе")
@app_commands.describe(link="Ссылка на группу Roblox или её ID")
@is_creator()
async def debug_chsp(interaction: discord.Interaction, link: str):
    await interaction.response.defer(ephemeral=True)
    
    group_id = extract_group_id(link)
    if not group_id:
        return await interaction.followup.send("❌ Неверный формат ссылки или ID.", ephemeral=True)
        
    group_name = await get_group_info(group_id)
    group_members = await get_all_group_members(group_id)
    
    if group_members is None:
        return await interaction.followup.send(f"❌ Группа **{group_name}** закрыта. Список участников скрыт.")
        
    try:
        conn = sqlite3.connect(db.DB_NAME)
        c = conn.cursor()
        c.execute("SELECT discord_id, roblox_id FROM links")
        linked_users = c.fetchall()
        conn.close()
    except Exception as e:
        return await interaction.followup.send(f"❌ Ошибка БД: {e}")

    matches = []
    for discord_id, roblox_id in linked_users:
        if int(roblox_id) in group_members:
            member = bot.get_guild(MAIN_GUILD_ID).get_member(discord_id)
            if member:
                matches.append(f"👤 **{member.name}** (`{discord_id}`) | Роблокс ID: `{roblox_id}`")
            else:
                matches.append(f"👤 Discord ID: `{discord_id}` | Роблокс ID: `{roblox_id}`")

    embed = discord.Embed(title=f"🛠 Отладка группы: {group_name}", color=discord.Color.blue())
    
    if matches:
        chunks = [matches[i:i + 15] for i in range(0, len(matches), 15)]
        for idx, chunk in enumerate(chunks):
            embed.add_field(name=f"Совпадения (часть {idx+1})", value="\n".join(chunk), inline=False)
    else:
        embed.description = "❌ В этой группе нет никого из верифицированных пользователей."
        
    embed.set_footer(text=f"Всего в базе: {len(linked_users)} | Всего в группе: {len(group_members)}")
    await interaction.followup.send(embed=embed, ephemeral=True)

# --- ЧСП ---
@bot.tree.command(name="чсп", description="Добавить группу в ЧСП")
@app_commands.describe(link="Ссылка", reason="Причина")
@is_creator()
async def add_chsp(interaction: discord.Interaction, link: str, reason: str):
    group_id = extract_group_id(link)
    if not group_id: return await interaction.response.send_message("❌ Неверный формат.", ephemeral=True)
    group_name = await get_group_info(group_id)
    if group_name == "Неизвестная группа": return await interaction.response.send_message("❌ Группа не найдена.", ephemeral=True)
    await interaction.response.send_message(f"⏳ **Принято.** Запускаю проверку.")
    db.add_chsp_group(group_id, group_name, link, reason, interaction.user.name)
    forum_channel = bot.get_channel(CHSP_FORUM_ID)
    if isinstance(forum_channel, discord.ForumChannel):
        try: await forum_channel.create_thread(name=f"ЧСП | {group_name}", embed=discord.Embed(description=f"# 🚫 ЧСП | {group_name}\n**Ссылка:** [Перейти]({link})\n**Причина:** {reason}\n**Модератор:** {interaction.user.mention}", color=discord.Color(16711680)))
        except: pass
    asyncio.create_task(perform_global_chsp_check())

@bot.tree.command(name="вынести-из-чсп", description="Удалить группу из ЧСП")
@app_commands.describe(link="Ссылка")
@is_creator()
async def remove_chsp(interaction: discord.Interaction, link: str):
    await interaction.response.send_message("⏳ Удаляю...")
    group_id = extract_group_id(link)
    if not group_id: return await interaction.followup.send("❌ Неверный формат.")
    group_info = db.get_chsp_group_by_id(group_id)
    if not group_info: return await interaction.followup.send("❌ Этой группы нет в ЧСП.")
    group_name = group_info[0]
    db.remove_chsp_group(group_id)
    await interaction.followup.send(f"✅ Группа **{group_name}** удалена.")

@bot.tree.command(name="перепроверить_всех_игроков", description="[АДМИН] Проверить всех")
@is_creator()
async def force_check(interaction: discord.Interaction):
    await interaction.response.send_message("⏳ Проверяю...")
    result = await perform_global_chsp_check()
    await interaction.followup.send(embed=discord.Embed(description=result, color=discord.Color.blue()))

# --- ОЧС ---
@bot.tree.command(name="очс", description="Забанить везде")
@app_commands.describe(user="Пользователь", reason="Причина", roblox_nick="Ник в РБ", proof="Док-во")
@is_ochs_staff()
async def ochs(interaction: discord.Interaction, user: discord.User, reason: str, roblox_nick: str = None, proof: str = None):
    if user.id == interaction.user.id: return await interaction.response.send_message("❌ Нельзя себя!", ephemeral=True)
    await interaction.response.send_message(f"⏳ Обрабатываю...")
    if not roblox_nick: roblox_nick = "Не указан"
    await perform_ochs(user, reason, roblox_nick, proof, interaction.user.mention)
    await interaction.followup.send(embed=discord.Embed(description=f"# ✅ {user.mention} забанен.", color=discord.Color(16711680)))

@bot.tree.command(name="вынести-из-очс", description="Разбанить")
@is_ochs_staff()
async def unban(interaction: discord.Interaction, user: discord.User): await handle_unban(interaction, user)

@bot.tree.command(name="очс-список", description="Показать ЧС")
@is_ochs_staff()
async def list_bans(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=False)
    bans = db.get_all_bans()
    if not bans: return await interaction.followup.send("📭 Пусто.")
    for i in range(0, len(bans), 5):
        desc = "# 📋 ОЧС\n\n"
        for d_id, d_name, r_nick, reason, mod, date, proof in bans[i:i+5]:
            desc += f"**👤 {d_name}** (`{d_id}`)\n**R:** {r_nick}\n**Причина:** {reason}\n**Мод:** {mod}\n**Дата:** {date}\n\n"
        await interaction.followup.send(embed=discord.Embed(description=desc, color=discord.Color(16711680)))

# --- РОЛИ ---
@bot.tree.command(name="времроль", description="Выдать роль")
@app_commands.describe(user="Кому", role="Какую", hours="Часов")
@is_ochs_staff()
async def temp_role(interaction: discord.Interaction, user: discord.Member, role: discord.Role, hours: float = 1.0):
    expire = datetime.datetime.now().timestamp() + (hours * 3600)
    try: await user.add_roles(role)
    except Exception as e: return await interaction.response.send_message(f"❌ Ошибка: {e}", ephemeral=True)
    conn = sqlite3.connect(db.DB_NAME)
    c = conn.cursor()
    c.execute("INSERT INTO temp_roles (discord_id, role_id, expire_at) VALUES (?, ?, ?)", (user.id, role.id, expire))
    conn.commit(); conn.close()
    await interaction.response.send_message(embed=discord.Embed(description=f"## ✅ Роль выдана на {hours} ч.", color=discord.Color(16711680)), ephemeral=True)

@bot.tree.command(name="снятьроль", description="Снять роль")
@app_commands.describe(user="У кого", role="Какую")
@is_ochs_staff()
async def remove_role(interaction: discord.Interaction, user: discord.Member, role: discord.Role):
    try:
        await user.remove_roles(role)
        await interaction.response.send_message(embed=discord.Embed(description="## ✅ Роль снята.", color=discord.Color(16711680)), ephemeral=True)
    except Exception as e: await interaction.response.send_message(f"❌ Ошибка: {e}", ephemeral=True)

# --- ПРОФИЛЬ ---
@bot.tree.command(name="профиль", description="Ваш профиль")
async def profile(interaction: discord.Interaction, user: discord.User = None):
    await interaction.response.defer(ephemeral=True)
    target = user or interaction.user
    roblox_id = db.check_link(target.id)
    if not roblox_id: return await interaction.followup.send(f"❌ {target.mention} не верифицирован. Нажмите кнопку в канале верификации.", ephemeral=True)
    embed = discord.Embed(description=f"## 👤 {target.mention}\n**Roblox ID:** `{roblox_id}`\n[Профиль](https://www.roblox.com/users/{roblox_id}/profile)", color=discord.Color(16711680))
    await interaction.followup.send(embed=embed, ephemeral=True)

# =====================================================================
# ЛОГИКА ЧСП И ОЧС
# =====================================================================
async def perform_global_chsp_check():
    chsp_groups = db.get_all_chsp_groups()
    if not chsp_groups: return "Групп в ЧСП нет."
    
    conn = sqlite3.connect(db.DB_NAME)
    c = conn.cursor()
    c.execute("SELECT discord_id, roblox_id FROM links")
    linked_users = c.fetchall()
    conn.close()

    warned_count, checked_users = 0, 0
    main_guild = bot.get_guild(MAIN_GUILD_ID)
    kap_guild = bot.get_guild(KAP_GUILD_ID)
    if not main_guild: return "❌ Бот не на Основном."

    bad_group_members = set()
    for group_id, _, _ in chsp_groups:
        members = await get_all_group_members(group_id)
        if members: bad_group_members.update(members)

    if not bad_group_members:
        return "⚠️ Не удалось получить участников групп (возможно, все группы закрыты)."

    pending_list = db.get_all_pending()
    pending_dict = {}
    for d_id, r_id, g_id, dl, n12, n1 in pending_list:
        if d_id not in pending_dict: pending_dict[d_id] = {}
        pending_dict[d_id][g_id] = True

    for discord_id, roblox_id in linked_users:
        if db.is_banned(discord_id): continue
        checked_users += 1
        
        if int(roblox_id) in bad_group_members:
            for group_id, group_name, group_link in chsp_groups:
                user_groups = await get_user_roblox_groups(roblox_id)
                if group_id in user_groups:
                    if discord_id not in pending_dict or group_id not in pending_dict[discord_id]:
                        strikes = db.get_strikes(discord_id)
                        hours = 12 if strikes > 0 else 72
                        deadline = datetime.datetime.now().timestamp() + (hours * 3600)
                        try:
                            member = main_guild.get_member(discord_id) or kap_guild.get_member(discord_id)
                            if member:
                                view = CheckGroupView(group_id, group_name)
                                dm_text = f"# ⚠️ ВНИМАНИЕ!\nВы в проекте **{group_name}**.\n**У вас {hours} часов на выход.**\n⏰ <t:{int(deadline)}:F>\n\n🔹 [Выйти]({group_link})"
                                await member.send(embed=discord.Embed(description=dm_text, color=discord.Color.orange()), view=view)
                                db.add_pending_chsp(discord_id, roblox_id, group_id, deadline)
                                if discord_id not in pending_dict: pending_dict[discord_id] = {}
                                pending_dict[discord_id][group_id] = True
                                warned_count += 1
                        except: pass
                    break
        else:
            if discord_id in pending_dict:
                for group_id in list(pending_dict[discord_id].keys()):
                    db.remove_pending_chsp(discord_id, group_id)
                    db.add_strike(discord_id)
                    try:
                        member = main_guild.get_member(discord_id) or kap_guild.get_member(discord_id)
                        if member: await member.send(embed=discord.Embed(description=f"✅ **Обвинения сняты**\nВы вышли из плохой группы.", color=discord.Color.green()))
                    except: pass
                    del pending_dict[discord_id][group_id]
                    
    return f"✅ Проверено: **{checked_users}**. Предупреждений: **{warned_count}**."

@tasks.loop(minutes=30)
async def monitor_chsp(): await perform_global_chsp_check()

@tasks.loop(minutes=1)
async def check_deadlines_loop():
    warnings = db.get_warnings_to_send()
    for d_id, g_id, dl, g_name, g_link in warnings:
        try:
            user = await bot.fetch_user(d_id)
            view = CheckGroupView(g_id, g_name)
            await user.send(embed=discord.Embed(description=f"🚨 **ОСТАЛСЯ 1 ЧАС!**\nГруппа **{g_name}**.\n<t:{int(dl)}:R>", color=discord.Color.red()), view=view)
            db.update_reminder_flag(d_id, g_id, "notified_1h")
        except: pass

    expired = db.get_expired_pending()
    for d_id, g_id, r_id in expired:
        try:
            user = await bot.fetch_user(d_id)
            g_info = db.get_chsp_group_by_id(g_id)
            g_name = g_info[0] if g_info else "Неизвестная"
            await perform_ochs(user, f"Не вышел из ЧСП ({g_name})", f"ID: {r_id}", None, "Система")
            db.remove_pending_chsp(d_id, g_id)
        except: pass

async def perform_ochs(user: discord.User, reason: str, roblox_nick: str, proof: str, moderator_name: str):
    now = datetime.datetime.now()
    time_str = now.strftime("%d.%m.%Y в %H:%M")
    try: await user.send(embed=discord.Embed(description=f"# 🚫 БЛОКИРОВКА\n**Причина:** {reason}\n**Модератор:** {moderator_name}\n**Дата:** {time_str}\n\n{APPEAL_LINK}", color=discord.Color(16711680)))
    except: pass

    forum_channel = bot.get_channel(KAP_FORUM_ID)
    forum_embed = discord.Embed(description=f"# ОЧС | {user.name}\n**Discord:** {user.mention}\n**Roblox:** `{roblox_nick}`\n**Причина:** {reason}\n**Модератор:** {moderator_name}\n**Дата:** {time_str}", color=discord.Color(16711680))
    if isinstance(forum_channel, discord.ForumChannel):
        try: await forum_channel.create_thread(name=f"ОЧС | {user.name}", embed=forum_embed)
        except: pass

    try: db.add_ban(user.id, user.name, roblox_nick, reason, moderator_name, proof)
    except: pass

    async def ban_guild(g_id):
        guild = bot.get_guild(g_id)
        if not guild: return
        try: await asyncio.wait_for(guild.ban(user, reason=f"ОЧС: {reason}"), timeout=3.0)
        except: pass
    await asyncio.gather(*[ban_guild(g_id) for g_id in GUILDS.keys()])

async def handle_unban(interaction: discord.Interaction, user: discord.User):
    await interaction.response.send_message(f"⏳ Разбаниваю {user.mention}...")
    async def unban_guild(g_id):
        guild = bot.get_guild(g_id)
        if not guild: return
        try:
            await guild.fetch_ban(user)
            await asyncio.wait_for(guild.unban(user, reason="Вынесен из ОЧС"), timeout=3.0)
        except: pass
    await asyncio.gather(*[unban_guild(g_id) for g_id in GUILDS.keys()])
    try:
        db.remove_ban(user.id)
        db.remove_pending_chsp(user.id)
        db_status = "✅ Удален"
    except: db_status = "❌ Ошибка"
    await interaction.followup.send(embed=discord.Embed(description=f"# ✅ Вынесен из ОЧС {user.mention}\n{db_status}", color=discord.Color(16711680)))

class CheckGroupView(discord.ui.View):
    def __init__(self, group_id, group_name):
        super().__init__(timeout=None)
        self.group_id = group_id
        self.group_name = group_name

    @discord.ui.button(label="Я вышел", style=discord.ButtonStyle.success, custom_id="check_leave")
    async def check_leave(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        roblox_id = db.check_link(interaction.user.id)
        if not roblox_id: return await interaction.followup.send("❌ Вы не верифицированы.", ephemeral=True)
        user_groups = await get_user_roblox_groups(roblox_id)
        if self.group_id in user_groups:
            await interaction.followup.send(f"❌ **Вы все еще в группе {self.group_name}!**", ephemeral=True)
        else:
            db.remove_pending_chsp(interaction.user.id, self.group_id)
            db.add_strike(interaction.user.id)
            await interaction.followup.send(f"✅ **Спасибо! Вы вышли из {self.group_name}.**", ephemeral=True)
            button.disabled = True
            await interaction.message.edit(view=self)

bot.run(TOKEN)
