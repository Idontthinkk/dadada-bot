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
        self.tree.copy_global_to(guild=KAP_OBJ)
        await self.tree.sync(guild=KAP_OBJ)
        self.tree.copy_global_to(guild=MAIN_OBJ)
        await self.tree.sync(guild=MAIN_OBJ)

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
# НОВАЯ ФУНКЦИЯ: ПОЛУЧЕНИЕ ВСЕХ УЧАСТНИКОВ ГРУППЫ
# =====================================================================
async def get_all_group_members(group_id):
    """Возвращает список ID всех участников группы или None, если группа закрыта."""
    members = set()
    cursor = ""
    headers = {"User-Agent": "Mozilla/5.0"}
    
    async with aiohttp.ClientSession() as session:
        while True:
            url = f"https://groups.roblox.com/v1/groups/{group_id}/users?limit=100&sortOrder=Asc"
            if cursor: url += f"&cursor={cursor}"
            
            try:
                async with session.get(url, headers=headers) as resp:
                    if resp.status == 403:
                        return None # Группа закрыта
                    if resp.status == 429:
                        await asyncio.sleep(5)
                        continue
                    if resp.status != 200:
                        break
                    
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

# =====================================================================
# ВЕРИФИКАЦИЯ (С АВАТАРКОЙ И ПРАВИЛЬНЫМ НИКОМ)
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
# КОМАНДА ДЛЯ ОБНОВЛЕНИЯ ВСЕХ НИКОВ
# =====================================================================
@bot.tree.command(name="обновитьник", description="[АДМИН] Обновить ники всем верифицированным", guild=KAP_OBJ)
@is_creator()
async def update_all_nicks(interaction: discord.Interaction):
    await interaction.response.send_message("⏳ Начинаю обновление ников для всех верифицированных...")
    
    conn = sqlite3.connect('bot_data.db')
    c = conn.cursor()
    c.execute("SELECT discord_id, roblox_id FROM links")
    linked_users = c.fetchall()
    conn.close()

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

# =====================================================================
# НОВАЯ КОМАНДА: СПИСОК ВСЕХ ЗАРЕГИСТРИРОВАННЫХ
# =====================================================================
@bot.tree.command(name="список_зареганных", description="[АДМИН] Показать всех верифицированных игроков", guild=KAP_OBJ)
@is_creator()
async def list_registered(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    
    conn = sqlite3.connect('bot_data.db')
    c = conn.cursor()
    c.execute("SELECT discord_id, roblox_id FROM links")
    linked_users = c.fetchall()
    conn.close()

    if not linked_users:
        return await interaction.followup.send("📭 В базе пока нет ни одного верифицированного игрока.")

    guild = bot.get_guild(MAIN_GUILD_ID)
    
    # Разбиваем на страницы по 15 человек, чтобы не превысить лимиты Discord
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

# =====================================================================
# ОБНОВЛЕННАЯ КОМАНДА /debug_chsp (ЧЕРЕЗ СПИСОК УЧАСТНИКОВ)
# =====================================================================
@bot.tree.command(name="debug_chsp", description="[АДМИН] Показать, кто из верифицированных состоит в группе", guild=KAP_OBJ)
@app_commands.describe(link="Ссылка на группу Roblox или её ID")
@is_creator()
async def debug_chsp(interaction: discord.Interaction, link: str):
    await interaction.response.defer(ephemeral=True)
    
    group_id = extract_group_id(link)
    if not group_id:
        return await interaction.followup.send("❌ Неверный формат ссылки или ID.", ephemeral=True)
        
    group_name = await get_group_info(group_id)
    
    # 1. Получаем ВЕСЬ список участников группы (1-2 запроса)
    group_members = await get_all_group_members(group_id)
    
    if group_members is None:
        return await interaction.followup.send(f"❌ Группа **{group_name}** закрыта. Список участников скрыт настройками приватности Roblox.")
        
    # 2. Берем базу наших верифицированных
    conn = sqlite3.connect('bot_data.db')
    c = conn.cursor()
    c.execute("SELECT discord_id, roblox_id FROM links")
    linked_users = c.fetchall()
    conn.close()

    # 3. Сравниваем ID (мгновенно)
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

# =====================================================================
# ОСТАЛЬНОЙ КОД (ЧСП, ОЧС, РОЛИ)
# =====================================================================
def extract_group_id(link: str):
    link = link.strip()
    if link.isdigit(): return int(link)
    match = re.search(r'(?:groups|communities)/(\d+)', link)
    if match: return int(match.group(1))
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

async def perform_global_chsp_check():
    chsp_groups = db.get_all_chsp_groups()
    if not chsp_groups: return "Групп в ЧСП нет."
    
    conn = sqlite3.connect('bot_data.db')
    c = conn.cursor()
    c.execute("SELECT discord_id, roblox_id FROM links")
    linked_users = c.fetchall()
    conn.close()

    warned_count, checked_users = 0, 0
    main_guild = bot.get_guild(MAIN_GUILD_ID)
    kap_guild = bot.get_guild(KAP_GUILD_ID)
    if not main_guild: return "❌ Бот не на Основном."

    # Собираем ID всех участников всех плохих групп
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
            # Нашли нарушителя (проверяем, в какой именно группе)
            for group_id, group_name, group_link in chsp_groups:
                user_groups = await get_user_roblox_groups(roblox_id) # Точечная проверка для точности группы
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
                    break # Дальше не проверяем
        else:
            # Если его нет в плохих группах, но он в базе pending - снимаем
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

# ... (остальные команды check_deadlines_loop, perform_ochs, CheckGroupView, чсп, очс, роли, профиль остаются без изменений) ...
# (Вставь их из предыдущего кода, они не менялись)

bot.run(TOKEN)
