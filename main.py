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

# === ТОКЕН И FIREBASE ===
TOKEN = os.getenv('DISCORD_TOKEN')
FIREBASE_URL = "https://ssrpbot-2ac7b-default-rtdb.firebaseio.com" 

KAP_GUILD_ID = 1294612883304353812
MAIN_GUILD_ID = 1292881174443720767
KAP_FORUM_ID = 1566139891258097664
CHSP_FORUM_ID = 1568020029117562900
APPEAL_LINK = "https://discord.gg/QUUVRgMqMN"

KAP_OBJ = discord.Object(id=KAP_GUILD_ID)
MAIN_OBJ = discord.Object(id=MAIN_GUILD_ID)

# ID для проверки прав и ролей
CREATOR_ID = 939996361712074832
OCHS_ROLE_1 = 1360357746972819476
OCHS_ROLE_2 = 1358192820900466932
VERIFY_ROLE_ID = 1511001116559802368 # Роль, которая выдается после верификации

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

class MyBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        db.init_db()
        self.tree.copy_global_to(guild=KAP_OBJ)
        await self.tree.sync(guild=KAP_OBJ)
        self.tree.copy_global_to(guild=MAIN_OBJ)
        await self.tree.sync(guild=MAIN_OBJ)
        print("[+] Команды синхронизированы.")

    async def on_ready(self):
        print(f'[+] Бот запущен как {self.user}')

        if not firebase_verification_loop.is_running():
            firebase_verification_loop.start()
            print("[*] Таймер верификации Firebase запущен (каждые 10 сек).")

        if not monitor_chsp.is_running():
            monitor_chsp.start()
            print("[*] Таймер проверки ЧСП запущен (раз в 30 мин).")

        if not check_deadlines_loop.is_running():
            check_deadlines_loop.start()
            print("[*] Таймер дедлайнов ЧСП запущен (раз в 1 мин).")

bot = MyBot()

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
        await interaction.response.send_message(embed=discord.Embed(description="## ❌ У вас нет прав для использования этой команды.", color=discord.Color(16711680)), ephemeral=True)
    else:
        print(f"[!] Ошибка команды: {error}")

# =====================================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
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
                        print(f"[!] Лимит Roblox API (429). Ждем 60 секунд...")
                        await asyncio.sleep(60)
                        continue
                    else:
                        return []
        except Exception:
            await asyncio.sleep(2)
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

# =====================================================================
# ВЕРИФИКАЦИЯ ЧЕРЕЗ FIREBASE
# =====================================================================
async def push_code_to_firebase(code, discord_id):
    url = f"{FIREBASE_URL}/codes/{code}.json"
    data = {"discord_id": discord_id, "status": "pending"}
    try:
        async with aiohttp.ClientSession() as session:
            await session.put(url, json=data)
    except Exception as e:
        print(f"[!] Ошибка записи в Firebase: {e}")

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
                            
                            # 1. Сохраняем привязку
                            db.link_user(discord_id, roblox_id)
                            
                            # 2. Выдаем роль
                            guild = bot.get_guild(MAIN_GUILD_ID)
                            member = guild.get_member(discord_id)
                            if member:
                                role = guild.get_role(VERIFY_ROLE_ID)
                                if role: await member.add_roles(role)
                            
                            # 3. Уведомление
                            try:
                                user = await bot.fetch_user(discord_id)
                                await user.send("✅ **Успешная верификация!** Вы успешно привязали аккаунт Roblox.")
                            except: pass
                            
                            # 4. Удаление кода
                            await session.delete(f"{FIREBASE_URL}/codes/{code}.json")
    except Exception:
        pass

@tasks.loop(seconds=10)
async def firebase_verification_loop():
    await check_firebase_codes()

@bot.tree.command(name="верификация", description="Привязать аккаунт Roblox", guild=MAIN_OBJ)
async def verify_user(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    
    if db.check_link(interaction.user.id):
        return await interaction.followup.send("❌ Вы уже верифицированы!", ephemeral=True)

    code = f"SSRP-{random.randint(10000, 99999)}"
    await push_code_to_firebase(code, interaction.user.id)
    
    embed = discord.Embed(
        title="Верификация аккаунта",
        description=f"Ваш код: **`{code}`**\n\n"
                    f"1. Зайдите в плейс верификации.\n"
                    f"2. Введите этот код.\n"
                    f"3. Бот автоматически выдаст вам роль.\n\n"
                    f"*Код действует 10 минут.*",
        color=discord.Color.blue()
    )
    await interaction.followup.send(embed=embed, ephemeral=True)

# =====================================================================
# ЛОГИКА ЧСП
# =====================================================================
async def perform_global_chsp_check():
    chsp_groups = db.get_all_chsp_groups()
    if not chsp_groups: return "Групп в ЧСП нет."

    print(f"\n[{datetime.datetime.now().strftime('%H:%M:%S')}] [*] Запущена проверка ЧСП...")
    
    conn = sqlite3.connect('bot_data.db')
    c = conn.cursor()
    c.execute("SELECT discord_id, roblox_id FROM links")
    linked_users = c.fetchall()
    conn.close()

    warned_count = 0
    checked_users = 0
    
    main_guild = bot.get_guild(MAIN_GUILD_ID)
    kap_guild = bot.get_guild(KAP_GUILD_ID)

    if not main_guild: return "❌ Бот не на Основном сервере."

    pending_list = db.get_all_pending()
    pending_dict = {}
    for d_id, r_id, g_id, dl, n12, n1 in pending_list:
        if d_id not in pending_dict: pending_dict[d_id] = {}
        pending_dict[d_id][g_id] = True

    for discord_id, roblox_id in linked_users:
        if db.is_banned(discord_id): continue
        
        checked_users += 1
        user_groups = await get_user_roblox_groups(roblox_id)
        await asyncio.sleep(1.2)
        
        for group_id, group_name, group_link in chsp_groups:
            if group_id in user_groups:
                if discord_id not in pending_dict or group_id not in pending_dict[discord_id]:
                    strikes = db.get_strikes(discord_id)
                    hours = 12 if strikes > 0 else 72
                    deadline = datetime.datetime.now().timestamp() + (hours * 3600)
                    
                    try:
                        member = main_guild.get_member(discord_id) or kap_guild.get_member(discord_id)
                        if member:
                            view = CheckGroupView(group_id, group_name)
                            dm_text = f"# ⚠️ ВНИМАНИЕ! ВЫ В ЧЕРНОМ СПИСКЕ ПРОЕКТА\nВы находитесь в проекте **{group_name}**.\n**У вас есть {hours} часов, чтобы выйти.**\n⏰ **Срок истекает:** <t:{int(deadline)}:F> (<t:{int(deadline)}:R>)\n\n🔹 **{group_name}** — [Выйти]({group_link})\n\n**Если вы вышли, нажмите кнопку.**"
                            await member.send(embed=discord.Embed(description=dm_text, color=discord.Color.orange()), view=view)
                            db.add_pending_chsp(discord_id, roblox_id, group_id, deadline)
                            if discord_id not in pending_dict: pending_dict[discord_id] = {}
                            pending_dict[discord_id][group_id] = True
                            warned_count += 1
                    except: pass
            else:
                if discord_id in pending_dict and group_id in pending_dict[discord_id]:
                    db.remove_pending_chsp(discord_id, group_id)
                    db.add_strike(discord_id)
                    try:
                        member = main_guild.get_member(discord_id) or kap_guild.get_member(discord_id)
                        if member:
                            await member.send(embed=discord.Embed(description=f"✅ **Обвинения сняты**\nВы вышли из проекта **{group_name}**.", color=discord.Color.green()))
                    except: pass
                    del pending_dict[discord_id][group_id]

    print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] [*] Проверка завершена.")
    return f"✅ Проверка завершена. Проверено: **{checked_users}**. Предупреждений: **{warned_count}**."

@tasks.loop(minutes=30)
async def monitor_chsp():
    await perform_global_chsp_check()

@tasks.loop(minutes=1)
async def check_deadlines_loop():
    warnings = db.get_warnings_to_send()
    for d_id, g_id, dl, g_name, g_link in warnings:
        try:
            user = await bot.fetch_user(d_id)
            view = CheckGroupView(g_id, g_name)
            await user.send(embed=discord.Embed(description=f"🚨 **ОСТАЛСЯ 1 ЧАС!**\nВы до сих пор в группе **{g_name}**.\nСрок истекает <t:{int(dl)}:R>.", color=discord.Color.red()), view=view)
            db.update_reminder_flag(d_id, g_id, "notified_1h")
        except: pass

    expired = db.get_expired_pending()
    for d_id, g_id, r_id in expired:
        try:
            user = await bot.fetch_user(d_id)
            g_info = db.get_chsp_group_by_id(g_id)
            g_name = g_info[0] if g_info else "Неизвестная группа"
            reason = f"Не вышел из проекта, находящегося в ЧСП ({g_name})"
            await perform_ochs(user, reason, f"ID: {r_id}", None, "Система (ЧСП)")
            db.remove_pending_chsp(d_id, g_id)
        except: pass

# =====================================================================
# БАН И РАЗБАН (ОЧС)
# =====================================================================
async def perform_ochs(user: discord.User, reason: str, roblox_nick: str, proof: str, moderator_name: str):
    now = datetime.datetime.now()
    time_str = now.strftime("%d.%m.%Y в %H:%M")

    dm_embed = discord.Embed(description=(f"# 🚫 УВЕДОМЛЕНИЕ О БЛОКИРОВКЕ (ОЧС)\nВаш аккаунт был заблокирован.\n\n**Причина:** **{reason}**\n**Кто забанил:** {moderator_name}\n**Дата:** {time_str}\n\nСсылка: {APPEAL_LINK}"), color=discord.Color(16711680))
    try: await user.send(embed=dm_embed)
    except: pass

    forum_channel = bot.get_channel(KAP_FORUM_ID)
    forum_embed = discord.Embed(description=(f"# ОЧС | {user.name}\n**Нарушитель:** {user.mention}\n**Discord ID:** `{user.id}`\n**Roblox:** `{roblox_nick}`\n**Причина:** **{reason}**\n**Модератор:** {moderator_name}\n**Дата:** {time_str}"), color=discord.Color(16711680))
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
    await interaction.response.send_message(f"⏳ **Принято.** Разбаниваю {user.mention}...")
    async def unban_guild(g_id):
        guild = bot.get_guild(g_id)
        if not guild: return
        try:
            await guild.fetch_ban(user)
            await asyncio.wait_for(guild.unban(user, reason=f"Вынесен из ОЧС"), timeout=3.0)
        except: pass

    await asyncio.gather(*[unban_guild(g_id) for g_id in GUILDS.keys()])
    
    try:
        db.remove_ban(user.id)
        db.remove_pending_chsp(user.id)
        db_status = "✅ Удален из базы"
    except: db_status = "❌ Ошибка БД"

    await interaction.followup.send(embed=discord.Embed(description=f"# ✅ Вынесен из ОЧС {user.mention}\n**База:** {db_status}", color=discord.Color(16711680)))

# =====================================================================
# КНОПКА ПРОВЕРКИ ЧСП
# =====================================================================
class CheckGroupView(discord.ui.View):
    def __init__(self, group_id, group_name):
        super().__init__(timeout=None)
        self.group_id = group_id
        self.group_name = group_name

    @discord.ui.button(label="Я вышел / Перепроверить", style=discord.ButtonStyle.success, custom_id="check_leave")
    async def check_leave(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        roblox_id = db.check_link(interaction.user.id)
        if not roblox_id:
            return await interaction.followup.send("❌ Вы не верифицированы.", ephemeral=True)
        user_groups = await get_user_roblox_groups(roblox_id)
        if self.group_id in user_groups:
            await interaction.followup.send(f"❌ **Вы все еще состоите в группе {self.group_name}!**", ephemeral=True)
        else:
            db.remove_pending_chsp(interaction.user.id, self.group_id)
            db.add_strike(interaction.user.id)
            await interaction.followup.send(f"✅ **Спасибо! Вы вышли из группы {self.group_name}.**", ephemeral=True)
            button.disabled = True
            await interaction.message.edit(view=self)

# =====================================================================
# КОМАНДЫ ЧСП
# =====================================================================
@bot.tree.command(name="debug_chsp", description="[АДМИН] Отладка системы ЧСП", guild=KAP_OBJ)
@app_commands.describe(user="Пользователь для проверки", link="Ссылка на группу для проверки")
@is_creator()
async def debug_chsp(interaction: discord.Interaction, user: discord.Member = None, link: str = None):
    await interaction.response.defer(ephemeral=True)
    embed = discord.Embed(title="🛠 Отладка ЧСП", color=discord.Color.blue())

    if link:
        group_id = extract_group_id(link)
        if not group_id: return await interaction.followup.send("❌ Неверный ID группы.", ephemeral=True)
        group_name = await get_group_info(group_id)
        
        conn = sqlite3.connect('bot_data.db')
        c = conn.cursor()
        c.execute("SELECT discord_id, roblox_id FROM links")
        linked_users = c.fetchall()
        conn.close()

        matches = []
        for discord_id, roblox_id in linked_users:
            u_groups = await get_user_roblox_groups(roblox_id)
            if group_id in u_groups:
                member = bot.get_guild(MAIN_GUILD_ID).get_member(discord_id)
                if member: matches.append(f"👤 {member.name} (`{discord_id}`)")

        embed.add_field(name=f"Группа: {group_name}", value="\n".join(matches) if matches else "Нет совпадений", inline=False)
        
    elif user:
        roblox_id = db.check_link(user.id)
        embed.add_field(name="Пользователь", value=f"{user.mention}\n**Roblox ID:** `{roblox_id or 'Не верифицирован'}`", inline=False)
        if roblox_id:
            user_groups = await get_user_roblox_groups(roblox_id)
            chsp_groups = db.get_all_chsp_groups()
            matches = [f"🔹 {g_name}" for g_id, g_name, _ in chsp_groups if g_id in user_groups]
            embed.add_field(name="Найден в ЧСП", value="\n".join(matches) if matches else "Нет", inline=False)
    else:
        embed.add_field(name="Инфо", value="Укажите `user` или `link`.", inline=False)

    await interaction.followup.send(embed=embed, ephemeral=True)

@bot.tree.command(name="чсп", description="Добавить группу в Черный список проектов", guild=KAP_OBJ)
@app_commands.describe(link="Ссылка на группу Roblox или её ID", reason="Причина")
@is_creator()
async def add_chsp_kap(interaction: discord.Interaction, link: str, reason: str): await process_add_chsp(interaction, link, reason)

@bot.tree.command(name="чсп", description="Добавить группу в Черный список проектов", guild=MAIN_OBJ)
@app_commands.describe(link="Ссылка на группу Roblox или её ID", reason="Причина")
@is_creator()
async def add_chsp_main(interaction: discord.Interaction, link: str, reason: str): await process_add_chsp(interaction, link, reason)

async def process_add_chsp(interaction: discord.Interaction, link: str, reason: str):
    group_id = extract_group_id(link)
    if not group_id: return await interaction.response.send_message("❌ Неверный формат.", ephemeral=True)
    group_name = await get_group_info(group_id)
    if group_name == "Неизвестная группа": return await interaction.response.send_message("❌ Группа не найдена.", ephemeral=True)

    await interaction.response.send_message(f"⏳ **Принято.** Анализирую группу и запускаю проверку в фоне.")
    db.add_chsp_group(group_id, group_name, link, reason, interaction.user.name)
    
    forum_channel = bot.get_channel(CHSP_FORUM_ID)
    forum_embed = discord.Embed(description=f"# 🚫 ЧСП | {group_name}\nПроект внесен в Черный список.\n\n**Ссылка:** [Перейти]({link})\n**Причина:** **{reason}**\n**Модератор:** {interaction.user.mention}", color=discord.Color(16711680))
    if isinstance(forum_channel, discord.ForumChannel):
        try: await forum_channel.create_thread(name=f"ЧСП | {group_name}", embed=forum_embed)
        except: pass

    asyncio.create_task(perform_global_chsp_check())

@bot.tree.command(name="вынести-из-чсп", description="Удалить группу из Черного списка проектов", guild=KAP_OBJ)
@app_commands.describe(link="Ссылка на группу Roblox или её ID")
@is_creator()
async def remove_chsp_kap(interaction: discord.Interaction, link: str): await process_remove_chsp(interaction, link)

@bot.tree.command(name="вынести-из-чсп", description="Удалить группу из Черного списка проектов", guild=MAIN_OBJ)
@app_commands.describe(link="Ссылка на группу Roblox или её ID")
@is_creator()
async def remove_chsp_main(interaction: discord.Interaction, link: str): await process_remove_chsp(interaction, link)

async def process_remove_chsp(interaction: discord.Interaction, link: str):
    await interaction.response.send_message("⏳ **Принято.** Удаляю группу из ЧСП...")
    group_id = extract_group_id(link)
    if not group_id: return await interaction.followup.send("❌ Неверный формат.")

    group_info = db.get_chsp_group_by_id(group_id)
    if not group_info: return await interaction.followup.send("❌ Этой группы нет в ЧСП.")
    
    group_name = group_info[0]
    db.remove_chsp_group(group_id)

    forum_status = "⚪ Тема не найдена"
    forum_channel = bot.get_channel(CHSP_FORUM_ID)
    if isinstance(forum_channel, discord.ForumChannel):
        target_name = f"ЧСП | {group_name}"
        found_thread = None
        async for thread in forum_channel.archived_threads(limit=100):
            if thread.name == target_name: found_thread = thread; break
        if not found_thread:
            for thread in forum_channel.threads:
                if thread.name == target_name: found_thread = thread; break
        if found_thread:
            try: await found_thread.delete(); forum_status = "✅ Тема удалена"
            except: forum_status = "❌ Ошибка удаления"

    await interaction.followup.send(f"✅ Группа **{group_name}** удалена из ЧСП.\n**Форум:** {forum_status}")

@bot.tree.command(name="перепроверить_всех_игроков", description="[АДМИН] Принудительно проверить всех игроков", guild=KAP_OBJ)
@is_creator()
async def force_check_kap(interaction: discord.Interaction):
    await interaction.response.send_message(f"⏳ **Принято.** Запускаю внеплановую проверку...")
    result = await perform_global_chsp_check()
    await interaction.followup.send(embed=discord.Embed(description=f"# 🛠 Ручная проверка\n{result}", color=discord.Color.blue()))

@bot.tree.command(name="перепроверить_всех_игроков", description="[АДМИН] Принудительно проверить всех игроков", guild=MAIN_OBJ)
@is_creator()
async def force_check_main(interaction: discord.Interaction):
    await interaction.response.send_message(f"⏳ **Принято.** Запускаю внеплановую проверку...")
    result = await perform_global_chsp_check()
    await interaction.followup.send(embed=discord.Embed(description=f"# 🛠 Ручная проверка\n{result}", color=discord.Color.blue()))

# =====================================================================
# КОМАНДЫ ОЧС
# =====================================================================
@bot.tree.command(name="очс", description="Забанить везде", guild=KAP_OBJ)
@app_commands.describe(user="Пользователь", reason="Причина", roblox_nick="Ник в РБ", proof="Док-во")
@is_ochs_staff()
async def ochs_kap(interaction: discord.Interaction, user: discord.User, reason: str, roblox_nick: str = None, proof: str = None):
    if user.id == interaction.user.id: return await interaction.response.send_message("❌ Нельзя себя!", ephemeral=True)
    await interaction.response.send_message(f"⏳ **Принято.** Обрабатываю {user.mention}...")
    if not roblox_nick: roblox_nick = "Не указан"
    await perform_ochs(user, reason, roblox_nick, proof, interaction.user.mention)
    await interaction.followup.send(embed=discord.Embed(description=f"# ✅ Готово!\n{user.mention} забанен.", color=discord.Color(16711680)))

@bot.tree.command(name="очс", description="Забанить везде", guild=MAIN_OBJ)
@app_commands.describe(user="Пользователь", reason="Причина", roblox_nick="Ник в РБ", proof="Док-во")
@is_ochs_staff()
async def ochs_main(interaction: discord.Interaction, user: discord.User, reason: str, roblox_nick: str = None, proof: str = None):
    if user.id == interaction.user.id: return await interaction.response.send_message("❌ Нельзя себя!", ephemeral=True)
    await interaction.response.send_message(f"⏳ **Принято.** Обрабатываю {user.mention}...")
    if not roblox_nick: roblox_nick = "Не указан"
    await perform_ochs(user, reason, roblox_nick, proof, interaction.user.mention)
    await interaction.followup.send(embed=discord.Embed(description=f"# ✅ Готово!\n{user.mention} забанен.", color=discord.Color(16711680)))

@bot.tree.command(name="вынести-из-очс", description="Разбанить и удалить тему из ЧС", guild=KAP_OBJ)
@is_ochs_staff()
async def unban_kap(interaction: discord.Interaction, user: discord.User): await handle_unban(interaction, user)

@bot.tree.command(name="вынести-из-очс", description="Разбанить и удалить тему из ЧС", guild=MAIN_OBJ)
@is_ochs_staff()
async def unban_main(interaction: discord.Interaction, user: discord.User): await handle_unban(interaction, user)

@bot.tree.command(name="очс-список", description="Показать всех в ЧС", guild=KAP_OBJ)
@is_ochs_staff()
async def list_bans_kap(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=False)
    bans = db.get_all_bans()
    if not bans: return await interaction.followup.send("📭 В ОЧС никого нет.")
    for i in range(0, len(bans), 5):
        desc = "# 📋 ОЧС\n\n"
        for d_id, d_name, r_nick, reason, mod, date, proof in bans[i:i+5]:
            desc += f"**👤 {d_name}** (`{d_id}`)\n**Roblox:** {r_nick}\n**Причина:** {reason}\n**Модератор:** {mod}\n**Дата:** {date}\n\n"
        await interaction.followup.send(embed=discord.Embed(description=desc, color=discord.Color(16711680)))

@bot.tree.command(name="очс-список", description="Показать всех в ЧС", guild=MAIN_OBJ)
@is_ochs_staff()
async def list_bans_main(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=False)
    bans = db.get_all_bans()
    if not bans: return await interaction.followup.send("📭 В ОЧС никого нет.")
    for i in range(0, len(bans), 5):
        desc = "# 📋 ОЧС\n\n"
        for d_id, d_name, r_nick, reason, mod, date, proof in bans[i:i+5]:
            desc += f"**👤 {d_name}** (`{d_id}`)\n**Roblox:** {r_nick}\n**Причина:** {reason}\n**Модератор:** {mod}\n**Дата:** {date}\n\n"
        await interaction.followup.send(embed=discord.Embed(description=desc, color=discord.Color(16711680)))

# =====================================================================
# ОБЩИЕ КОМАНДЫ (ВРЕМРОЛЬ, СНЯТЬРОЛЬ, ПРОФИЛЬ)
# =====================================================================
@bot.tree.command(name="времроль", description="Выдать роль на время", guild=KAP_OBJ)
@app_commands.describe(user="Кому", role="Какую", hours="Часов")
@is_ochs_staff()
async def temp_role_kap(interaction: discord.Interaction, user: discord.Member, role: discord.Role, hours: float = 1.0): await handle_temp_role(interaction, user, role, hours)

@bot.tree.command(name="времроль", description="Выдать роль на время", guild=MAIN_OBJ)
@app_commands.describe(user="Кому", role="Какую", hours="Часов")
@is_ochs_staff()
async def temp_role_main(interaction: discord.Interaction, user: discord.Member, role: discord.Role, hours: float = 1.0): await handle_temp_role(interaction, user, role, hours)

async def handle_temp_role(interaction, user, role, hours):
    expire = datetime.datetime.now().timestamp() + (hours * 3600)
    try: await user.add_roles(role)
    except Exception as e: return await interaction.response.send_message(f"❌ Ошибка: {e}", ephemeral=True)
    conn = sqlite3.connect('bot_data.db')
    c = conn.cursor()
    c.execute("INSERT INTO temp_roles (discord_id, role_id, expire_at) VALUES (?, ?, ?)", (user.id, role.id, expire))
    conn.commit(); conn.close()
    await interaction.response.send_message(embed=discord.Embed(description=f"## ✅ Роль выдана на {hours} ч.", color=discord.Color(16711680)), ephemeral=True)

@bot.tree.command(name="снятьроль", description="Снять роль", guild=KAP_OBJ)
@app_commands.describe(user="У кого", role="Какую")
@is_ochs_staff()
async def remove_role_kap(interaction: discord.Interaction, user: discord.Member, role: discord.Role): await handle_remove_role(interaction, user, role)

@bot.tree.command(name="снятьроль
