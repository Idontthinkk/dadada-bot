import discord
from discord.ext import commands, tasks
from discord import app_commands
import os
import datetime
import asyncio
import aiohttp
import re
from dotenv import load_dotenv
import database as db

load_dotenv()

import os
TOKEN = os.getenv('DISCORD_TOKEN')

KAP_GUILD_ID = 1294612883304353812
MAIN_GUILD_ID = 1292881174443720767
KAP_FORUM_ID = 1566139891258097664

CHSP_FORUM_ID = 1568020029117562900
APPEAL_LINK = "https://discord.gg/QUUVRgMqMN"

KAP_OBJ = discord.Object(id=KAP_GUILD_ID)
MAIN_OBJ = discord.Object(id=MAIN_GUILD_ID)

# ID для проверки прав
CREATOR_ID = 939996361712074832
OCHS_ROLE_1 = 1360357746972819476
OCHS_ROLE_2 = 1358192820900466932

# Роль, гарантирующая привязку к Bloxlink
BLOXLINK_ROLE_ID = 1511001116559802368

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

        if not monitor_chsp.is_running():
            monitor_chsp.start()
            print("[*] Таймер проверки ЧСП (раз в 30 мин) запущен.")

        if not check_deadlines_loop.is_running():
            check_deadlines_loop.start()
            print("[*] Таймер дедлайнов (раз в 1 мин) запущен.")


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
        await interaction.response.send_message(
            embed=discord.Embed(description="## ❌ У вас нет прав для использования этой команды.",
                                color=discord.Color(16711680)), ephemeral=True)
    else:
        print(f"[!] Ошибка команды: {error}")


# =====================================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ API (Bloxlink и Roblox)
# =====================================================================
def extract_group_id(link: str):
    link = link.strip()
    if link.isdigit(): return int(link)
    match = re.search(r'(?:groups|communities)/(\d+)', link)
    if match: return int(match.group(1))
    return None


async def get_bloxlink_roblox_id(discord_id):
    url = f"https://api.blox.link/v4/public/guilds/{MAIN_GUILD_ID}/discord-to-roblox/{discord_id}"
    headers = {"Authorization": BLOXLINK_API_KEY}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get("robloxID")
                elif resp.status == 429:
                    print(f"[!] Лимит Bloxlink (429) для {discord_id}. Ждем 60 секунд...")
                    await asyncio.sleep(60)
                    return await get_bloxlink_roblox_id(discord_id)
                elif resp.status == 404:
                    return None
                else:
                    print(f"[!] Bloxlink API Error {resp.status}: {await resp.text()}")
    except Exception as e:
        print(f"[!] Ошибка Bloxlink (Exception): {e}")
    return None


async def get_user_roblox_groups(roblox_id):
    url = f"https://groups.roblox.com/v1/users/{roblox_id}/groups/roles"
    headers = {"User-Agent": "Mozilla/5.0"}

    for attempt in range(2):  # 2 попытки на запрос
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, timeout=10) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return [group["group"]["id"] for group in data.get("data", [])]
                    elif resp.status == 429:
                        print(f"[!] Лимит Roblox API (429). Ждем 60 секунд...")
                        await asyncio.sleep(60)  # ЖДЕМ МИНУТУ
                        continue
                    else:
                        # Если 500 или другая ошибка, просто идем дальше
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
    except:
        pass
    return "Неизвестная группа"


async def get_bloxlink_users_count():
    main_guild = bot.get_guild(MAIN_GUILD_ID)
    kap_guild = bot.get_guild(KAP_GUILD_ID)
    users_to_check = set()

    for guild in [main_guild, kap_guild]:
        if guild:
            for member in guild.members:
                try:
                    member = await guild.fetch_member(member.id)
                except:
                    pass
                if not member.bot and any(r.id == BLOXLINK_ROLE_ID for r in member.roles):
                    users_to_check.add(member.id)
    return len(users_to_check)


# =====================================================================
# КНОПКА ПРОВЕРКИ ("Я ВЫШЕЛ")
# =====================================================================
class CheckGroupView(discord.ui.View):
    def __init__(self, group_id, group_name):
        super().__init__(timeout=None)
        self.group_id = group_id
        self.group_name = group_name

    @discord.ui.button(label="Я вышел / Перепроверить", style=discord.ButtonStyle.success, custom_id="check_leave")
    async def check_leave(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)

        r_id = await get_bloxlink_roblox_id(interaction.user.id)
        if not r_id:
            return await interaction.followup.send("❌ Не удалось проверить ваш аккаунт (вы не привязаны к Bloxlink).",
                                                   ephemeral=True)

        user_groups = await get_user_roblox_groups(r_id)

        if self.group_id in user_groups:
            await interaction.followup.send(
                f"❌ **Вы все еще состоите в группе {self.group_name}!**\nВыйдите из неё и нажмите кнопку снова.",
                ephemeral=True)
        else:
            db.remove_pending_chsp(interaction.user.id, self.group_id)
            db.add_strike(interaction.user.id)
            await interaction.followup.send(
                f"✅ **Спасибо! Вы вышли из группы {self.group_name}.**\nОбвинения с вас сняты.", ephemeral=True)
            button.disabled = True
            await interaction.message.edit(view=self)


# =====================================================================
# БАН И РАЗБАН
# =====================================================================
async def perform_ochs(user: discord.User, reason: str, roblox_nick: str, proof: str, moderator_name: str):
    now = datetime.datetime.now()
    time_str = now.strftime("%d.%m.%Y в %H:%M")

    dm_embed = discord.Embed(description=(
                f"# 🚫 УВЕДОМЛЕНИЕ О БЛОКИРОВКЕ (ОЧС)\nВаш аккаунт был заблокирован на всех серверах сети **проекта ССРП**.\nВы внесены в **Общий Чёрный Список (ОЧС)**.\n\n**Нарушитель:** `{user.name}`\n**Discord ID:** `{user.id}`\n**Roblox:** `{roblox_nick}`\n**Причина:** **{reason}**\n**Кто забанил:** {moderator_name}\n**Дата:** {time_str}\n" + (
            f"**Доказательство:** [Ссылка]({proof})\n" if proof else "") + f"\n**Что делать дальше?**\nЕсли это ошибка — подайте апелляцию.\nСсылка: {APPEAL_LINK}"),
                             color=discord.Color(16711680))
    try:
        await user.send(embed=dm_embed)
    except:
        pass

    forum_channel = bot.get_channel(KAP_FORUM_ID)
    forum_embed = discord.Embed(description=(
                f"# ОЧС | {user.name}\nПользователь внесён в Общий Чёрный Список.\n\n**Нарушитель:** {user.mention}\n**Discord ID:** `{user.id}`\n**Roblox:** `{roblox_nick}`\n**Причина:** **{reason}**\n**Модератор:** {moderator_name}\n**Дата:** {time_str}\n" + (
            f"**Доказательство:** [Ссылка]({proof})" if proof else "")), color=discord.Color(16711680))
    if isinstance(forum_channel, discord.ForumChannel):
        try:
            await forum_channel.create_thread(name=f"ОЧС | {user.name}", embed=forum_embed)
        except:
            pass

    try:
        db.add_ban(user.id, user.name, roblox_nick, reason, moderator_name, proof)
    except:
        pass

    async def ban_guild(g_id):
        guild = bot.get_guild(g_id)
        if not guild: return
        try:
            await asyncio.wait_for(guild.ban(user, reason=f"ОЧС: {reason}"), timeout=3.0)
        except:
            pass

    await asyncio.gather(*[ban_guild(g_id) for g_id in GUILDS.keys()])


async def handle_unban(interaction: discord.Interaction, user: discord.User):
    await interaction.response.send_message(f"⏳ **Принято.** Разбаниваю {user.mention}...")

    async def unban_guild(g_id):
        guild = bot.get_guild(g_id)
        if not guild: return
        try:
            await guild.fetch_ban(user)
            await asyncio.wait_for(guild.unban(user, reason=f"Вынесен из ОЧС | {interaction.user}"), timeout=3.0)
        except:
            pass

    await asyncio.gather(*[unban_guild(g_id) for g_id in GUILDS.keys()])

    forum_status = "⚪ Тема не найдена"
    forum_channel = bot.get_channel(KAP_FORUM_ID)
    if isinstance(forum_channel, discord.ForumChannel):
        target_name = f"ОЧС | {user.name}"
        found_thread = None
        async for thread in forum_channel.archived_threads(limit=100):
            if thread.name == target_name: found_thread = thread; break
        if not found_thread:
            for thread in forum_channel.threads:
                if thread.name == target_name: found_thread = thread; break
        if found_thread:
            try:
                await found_thread.delete(); forum_status = "✅ Тема удалена"
            except:
                forum_status = "❌ Ошибка удаления"

    try:
        db.remove_ban(user.id)
        db.remove_pending_chsp(user.id)
        db_status = "✅ Удален из базы"
    except:
        db_status = "❌ Ошибка БД"

    try:
        await user.send(embed=discord.Embed(
            description=f"✅ **Вы были вынесены из Общего Чёрного Списка (ОЧС) проекта ССРП.**\n\nВы снова можете пользоваться серверами проекта. Пожалуйста, соблюдайте правила.",
            color=discord.Color.green()
        ))
        dm_status = "✅ ЛС отправлено"
    except:
        dm_status = "❌ ЛС не отправлено (закрыты)"

    await interaction.followup.send(embed=discord.Embed(
        description=f"# ✅ Вынесен из ОЧС {user.mention}\n**Форум:** {forum_status}\n**База:** {db_status}\n**Уведомление:** {dm_status}",
        color=discord.Color(16711680)))


# =====================================================================
# ЛОГИКА ПРОВЕРКИ ЧЕРЕЗ BLOXLINK (Раз в 30 минут)
# =====================================================================
async def perform_global_chsp_check():
    chsp_groups = db.get_all_chsp_groups()
    if not chsp_groups: return "Групп в ЧСП нет."

    print(f"\n[{datetime.datetime.now().strftime('%H:%M:%S')}] [*] Запущена проверка через Bloxlink...")
    pending_list = db.get_all_pending()
    pending_dict = {}
    for d_id, r_id, g_id, dl, n12, n1 in pending_list:
        if d_id not in pending_dict: pending_dict[d_id] = {}
        pending_dict[d_id][g_id] = True

    warned_count = 0
    cleared_count = 0
    checked_users = 0
    no_bloxlink = 0

    main_guild = bot.get_guild(MAIN_GUILD_ID)
    kap_guild = bot.get_guild(KAP_GUILD_ID)
    users_to_check = set()

    if not main_guild:
        return "❌ Бот не находится на Основном сервере."

    for guild in [main_guild, kap_guild]:
        if guild:
            for member in guild.members:
                try:
                    member = await guild.fetch_member(member.id)
                except:
                    pass
                if not member.bot and any(r.id == BLOXLINK_ROLE_ID for r in member.roles):
                    users_to_check.add(member.id)

    total_users = len(users_to_check)
    print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] [*] Найдено {total_users} человек с ролью Bloxlink.")

    if total_users == 0:
        return "❌ Бот не нашел ни одного человека с ролью Bloxlink. Проверьте ID роли и иерархию."

    for index, discord_id in enumerate(users_to_check, 1):
        if db.is_banned(discord_id): continue

        # Выводим лог прогресса каждые 10 человек (чтобы не спамить)
        if index % 10 == 0 or index == total_users:
            print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] [*] Проверено {index} из {total_users}...")

        roblox_id = await get_bloxlink_roblox_id(discord_id)
        await asyncio.sleep(1.2)  # 50 человек в минуту

        if not roblox_id:
            no_bloxlink += 1
            continue

        checked_users += 1
        user_groups = await get_user_roblox_groups(roblox_id)

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
                            dm_text = f"# ⚠️ ВНИМАНИЕ! ВЫ В ЧЕРНОМ СПИСКЕ ПРОЕКТА\nВы находитесь в проекте **{group_name}**, который внесен в ЧСП ССРП.\n\n"
                            dm_text += f"**У вас есть {hours} часов, чтобы выйти из этой группы.**\n"
                            dm_text += f"⏰ **Срок истекает:** <t:{int(deadline)}:F> (<t:{int(deadline)}:R>)\n\n"
                            dm_text += f"🔹 **{group_name}** — [Выйти из группы]({group_link})\n\n"
                            dm_text += f"**Если вы вышли, нажмите кнопку ниже для перепроверки.**\n**Иначе вы будете внесены в ОЧС.**"

                            await member.send(embed=discord.Embed(description=dm_text, color=discord.Color.orange()),
                                              view=view)
                            db.add_pending_chsp(discord_id, roblox_id, group_id, deadline)
                            if discord_id not in pending_dict: pending_dict[discord_id] = {}
                            pending_dict[discord_id][group_id] = True
                            warned_count += 1
                    except:
                        pass
            else:
                if discord_id in pending_dict and group_id in pending_dict[discord_id]:
                    db.remove_pending_chsp(discord_id, group_id)
                    db.add_strike(discord_id)
                    try:
                        member = main_guild.get_member(discord_id) or kap_guild.get_member(discord_id)
                        if member:
                            await member.send(embed=discord.Embed(
                                description=f"✅ **Обвинения сняты**\nВы вышли из проекта **{group_name}**. Предупреждение аннулировано.",
                                color=discord.Color.green()))
                    except:
                        pass
                    del pending_dict[discord_id][group_id]
                    cleared_count += 1

    print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] [*] Проверка завершена.")
    return f"✅ Проверка завершена.\nС ролью найдено: **{total_users}**\nПроверено: **{checked_users}** (ошибка Bloxlink: {no_bloxlink})\nНовых предупреждений: **{warned_count}**\nСнято: **{cleared_count}**."


@tasks.loop(minutes=30)
async def monitor_chsp():
    await perform_global_chsp_check()


# =====================================================================
# ТАЙМЕР ДЕДЛАЙНОВ (Раз в 1 минуту)
# =====================================================================
@tasks.loop(minutes=1)
async def check_deadlines_loop():
    warnings = db.get_warnings_to_send()
    for d_id, g_id, dl, g_name, g_link in warnings:
        try:
            user = await bot.fetch_user(d_id)
            view = CheckGroupView(g_id, g_name)
            await user.send(embed=discord.Embed(
                description=f"🚨 **ОСТАЛСЯ 1 ЧАС!**\nВы до сих пор в группе **{g_name}**.\nСрок истекает <t:{int(dl)}:R>.\n\nЕсли вы уже вышли, нажмите кнопку ниже, иначе будете забанены.",
                color=discord.Color.red()
            ), view=view)
            db.update_reminder_flag(d_id, g_id, "notified_1h")
        except:
            pass

    expired = db.get_expired_pending()
    for d_id, g_id, r_id in expired:
        try:
            user = await bot.fetch_user(d_id)
            g_info = db.get_chsp_group_by_id(g_id)
            g_name = g_info[0] if g_info else "Неизвестная группа"
            reason = f"Не вышел из проекта, находящегося в ЧСП ({g_name})"
            await perform_ochs(user, reason, f"ID: {r_id}", None, "Система (ЧСП)")
            db.remove_pending_chsp(d_id, g_id)
        except:
            pass


# =====================================================================
# КОМАНДЫ
# =====================================================================

@bot.tree.command(name="debug_chsp", description="[АДМИН] Отладка системы ЧСП", guild=KAP_OBJ)
@app_commands.describe(user="Пользователь для проверки", link="Ссылка на группу для проверки")
@is_creator()
async def debug_chsp(interaction: discord.Interaction, user: discord.Member = None, link: str = None):
    if link:
        group_id = extract_group_id(link)
        if not group_id:
            return await interaction.response.send_message("❌ Неверный ID группы.", ephemeral=True)

        group_name = await get_group_info(group_id)

        await interaction.response.send_message(
            f"⏳ **Принято.** Ищу игроков в группе **{group_name}**. Результат пришлю сюда.", ephemeral=True)

        async def do_debug_check():
            main_guild = bot.get_guild(MAIN_GUILD_ID)
            kap_guild = bot.get_guild(KAP_GUILD_ID)
            matches = []

            users_to_check = set()
            for guild in [main_guild, kap_guild]:
                if guild:
                    for member in guild.members:
                        try:
                            member = await guild.fetch_member(member.id)
                        except:
                            pass
                        if not member.bot and any(r.id == BLOXLINK_ROLE_ID for r in member.roles):
                            users_to_check.add(member.id)

            total = len(users_to_check)
            print(
                f"[{datetime.datetime.now().strftime('%H:%M:%S')}] [*] DEBUG: Начинаю проверку {total} человек для группы {group_name}...")

            for index, discord_id in enumerate(users_to_check, 1):
                if index % 10 == 0:
                    print(
                        f"[{datetime.datetime.now().strftime('%H:%M:%S')}] [*] DEBUG: Проверено {index} из {total}...")

                r_id = await get_bloxlink_roblox_id(discord_id)
                await asyncio.sleep(1.2)
                if r_id:
                    u_groups = await get_user_roblox_groups(r_id)
                    if group_id in u_groups:
                        member = main_guild.get_member(discord_id) or kap_guild.get_member(discord_id)
                        if member:
                            matches.append(f"👤 **{member.name}** (`{member.id}`) | Роблокс: `{r_id}`")

            embed = discord.Embed(title=f"🛠 Отладка: {group_name}", color=discord.Color.blue())
            if matches:
                chunks = [matches[i:i + 15] for i in range(0, len(matches), 15)]
                for idx, chunk in enumerate(chunks):
                    embed.add_field(name=f"Совпадения (часть {idx + 1})", value="\n".join(chunk), inline=False)
            else:
                embed.description = "Нет игроков из этой группы (или нет привязки Bloxlink)."

            try:
                await interaction.channel.send(embed=embed)
                await interaction.edit_original_response(content="✅ Проверка завершена! Результат отправлен выше.")
            except Exception as e:
                await interaction.edit_original_response(content=f"❌ Ошибка отправки: {e}")

        asyncio.create_task(do_debug_check())

    elif user:
        await interaction.response.defer(ephemeral=True)
        try:
            fetched_member = await bot.get_guild(MAIN_GUILD_ID).fetch_member(user.id)
            has_role = any(r.id == BLOXLINK_ROLE_ID for r in fetched_member.roles)
            role_list = [f"<@&{r.id}>" for r in fetched_member.roles if r.name != "@everyone"]
        except Exception as e:
            has_role = False
            role_list = [f"Ошибка загрузки ролей: {e}"]

        embed = discord.Embed(title="🛠 Отладка ЧСП (Bloxlink)", color=discord.Color.blue())
        embed.add_field(name="Пользователь",
                        value=f"**Имя:** {user.mention}\n**Есть роль Bloxlink:** {'✅ Да' if has_role else '❌ Нет'}",
                        inline=False)
        embed.add_field(name="Все роли (что видит бот)", value=", ".join(role_list) if role_list else "Нет ролей",
                        inline=False)

        if has_role:
            r_id = await get_bloxlink_roblox_id(user.id)
            embed.add_field(name="Bloxlink API", value=f"**Roblox ID:** `{r_id or 'Не найден/Ошибка'}`", inline=False)

            if r_id:
                user_groups = await get_user_roblox_groups(r_id)
                chsp_groups = db.get_all_chsp_groups()
                matches = []
                for g_id, g_name, _ in chsp_groups:
                    if g_id in user_groups:
                        matches.append(f"🔹 {g_name} (`{g_id}`)")

                embed.add_field(name="Найден в группах ЧСП", value="\n".join(matches) if matches else "Нет совпадений",
                                inline=False)

        await interaction.followup.send(embed=embed, ephemeral=True)

    else:
        await interaction.response.defer(ephemeral=True)
        main_guild = bot.get_guild(MAIN_GUILD_ID)
        members_count = len(main_guild.members) if main_guild else 0

        has_role_count = 0
        if main_guild:
            for m in main_guild.members:
                try:
                    m = await main_guild.fetch_member(m.id)
                except:
                    pass
                if not m.bot and any(r.id == BLOXLINK_ROLE_ID for r in m.roles):
                    has_role_count += 1

        embed = discord.Embed(title="🛠 Отладка ЧСП (Bloxlink)", color=discord.Color.blue())
        embed.add_field(name="Основной сервер", value=f"Участников (видит бот): **{members_count}**", inline=False)
        embed.add_field(name="Роль Bloxlink", value=f"Найдено с ролью: **{has_role_count}**", inline=False)
        embed.add_field(name="Подсказка",
                        value="Укажите `user` или `link`, чтобы проверить конкретного человека или группу.",
                        inline=False)

        await interaction.followup.send(embed=embed, ephemeral=True)


# --- КОМАНДЫ ЧСП (ТОЛЬКО СОЗДАТЕЛЬ) ---
@bot.tree.command(name="чсп", description="Добавить группу в Черный список проектов", guild=KAP_OBJ)
@app_commands.describe(link="Ссылка на группу Roblox или её ID", reason="Причина")
@is_creator()
async def add_chsp_kap(interaction: discord.Interaction, link: str, reason: str): await process_add_chsp(interaction,
                                                                                                         link, reason)


@bot.tree.command(name="чсп", description="Добавить группу в Черный список проектов", guild=MAIN_OBJ)
@app_commands.describe(link="Ссылка на группу Roblox или её ID", reason="Причина")
@is_creator()
async def add_chsp_main(interaction: discord.Interaction, link: str, reason: str): await process_add_chsp(interaction,
                                                                                                          link, reason)


async def process_add_chsp(interaction: discord.Interaction, link: str, reason: str):
    group_id = extract_group_id(link)
    if not group_id: return await interaction.response.send_message("❌ Неверный формат.", ephemeral=True)

    group_name = await get_group_info(group_id)
    if group_name == "Неизвестная группа": return await interaction.response.send_message("❌ Группа не найдена.",
                                                                                          ephemeral=True)

    count = await get_bloxlink_users_count()
    est_time = max(1, int(count * 1.25 / 60))

    await interaction.response.send_message(
        f"⏳ **Принято.** Анализирую группу и запускаю проверку.\n⏱️ Расчётное время проверки всех игроков: **~{est_time} мин.** (Игроков с ролью Bloxlink: {count})")

    db.add_chsp_group(group_id, group_name, link, reason, interaction.user.name)
    forum_channel = bot.get_channel(CHSP_FORUM_ID)
    forum_embed = discord.Embed(
        description=f"# 🚫 ЧСП | {group_name}\nПроект внесён в Черный список.\n\n**Ссылка:** [Перейти в группу]({link})\n**Причина:** **{reason}**\n**Модератор:** {interaction.user.mention}\n**Дата:** {datetime.datetime.now().strftime('%d.%m.%Y в %H:%M')}",
        color=discord.Color(16711680))
    if isinstance(forum_channel, discord.ForumChannel):
        try:
            await forum_channel.create_thread(name=f"ЧСП | {group_name}", embed=forum_embed)
        except:
            pass

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
            try:
                await found_thread.delete(); forum_status = "✅ Тема удалена"
            except:
                forum_status = "❌ Ошибка удаления"

    await interaction.followup.send(f"✅ Группа **{group_name}** удалена из ЧСП.\n**Форум:** {forum_status}")


@bot.tree.command(name="перепроверить_всех_игроков", description="[АДМИН] Принудительно проверить всех игроков",
                  guild=KAP_OBJ)
@is_creator()
async def force_check_kap(interaction: discord.Interaction):
    count = await get_bloxlink_users_count()
    est_time = max(1, int(count * 1.25 / 60))
    await interaction.response.send_message(
        f"⏳ **Принято.** Запускаю внеплановую проверку.\n⏱️ Расчётное время: **~{est_time} мин.** (Игроков: {count})")
    result = await perform_global_chsp_check()
    await interaction.followup.send(
        embed=discord.Embed(description=f"# 🛠 Ручная проверка\n{result}", color=discord.Color.blue()))


@bot.tree.command(name="перепроверить_всех_игроков", description="[АДМИН] Принудительно проверить всех игроков",
                  guild=MAIN_OBJ)
@is_creator()
async def force_check_main(interaction: discord.Interaction):
    count = await get_bloxlink_users_count()
    est_time = max(1, int(count * 1.25 / 60))
    await interaction.response.send_message(
        f"⏳ **Принято.** Запускаю внеплановую проверку.\n⏱️ Расчётное время: **~{est_time} мин.** (Игроков: {count})")
    result = await perform_global_chsp_check()
    await interaction.followup.send(
        embed=discord.Embed(description=f"# 🛠 Ручная проверка\n{result}", color=discord.Color.blue()))


# --- КОМАНДЫ ОЧС (СОЗДАТЕЛЬ + РОЛИ) ---
@bot.tree.command(name="очс", description="Забанить везде", guild=KAP_OBJ)
@app_commands.describe(user="Пользователь", reason="Причина", roblox_nick="Ник в РБ", proof="Док-во")
@is_ochs_staff()
async def ochs_kap(interaction: discord.Interaction, user: discord.User, reason: str, roblox_nick: str = None,
                   proof: str = None):
    if user.id == interaction.user.id: return await interaction.response.send_message("❌ Нельзя себя!", ephemeral=True)
    await interaction.response.send_message(f"⏳ **Принято.** Обрабатываю {user.mention}...")
    if not roblox_nick: roblox_nick = "Не указан"
    await perform_ochs(user, reason, roblox_nick, proof, interaction.user.mention)
    await interaction.followup.send(
        embed=discord.Embed(description=f"# ✅ Готово!\n{user.mention} забанен.", color=discord.Color(16711680)))


@bot.tree.command(name="очс", description="Забанить везде", guild=MAIN_OBJ)
@app_commands.describe(user="Пользователь", reason="Причина", roblox_nick="Ник в РБ", proof="Док-во")
@is_ochs_staff()
async def ochs_main(interaction: discord.Interaction, user: discord.User, reason: str, roblox_nick: str = None,
                    proof: str = None):
    if user.id == interaction.user.id: return await interaction.response.send_message("❌ Нельзя себя!", ephemeral=True)
    await interaction.response.send_message(f"⏳ **Принято.** Обрабатываю {user.mention}...")
    if not roblox_nick: roblox_nick = "Не указан"
    await perform_ochs(user, reason, roblox_nick, proof, interaction.user.mention)
    await interaction.followup.send(
        embed=discord.Embed(description=f"# ✅ Готово!\n{user.mention} забанен.", color=discord.Color(16711680)))


@bot.tree.command(name="вынести-из-очс", description="Разбанить и удалить тему из ЧС", guild=KAP_OBJ)
@is_ochs_staff()
async def unban_kap(interaction: discord.Interaction, user: discord.User): await handle_unban(interaction, user)


@bot.tree.command(name="вынести-из-очс", description="Разбанить и удалить тему из ЧС", guild=MAIN_OBJ)
@is_ochs_staff()
async def unban_main(interaction: discord.Interaction, user: discord.User): await handle_unban(interaction, user)


async def handle_list_bans(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=False)
    bans = db.get_all_bans()
    if not bans: return await interaction.followup.send("📭 В ОЧС никого нет.")
    chunks = [bans[i:i + 5] for i in range(0, len(bans), 5)]
    for chunk in chunks:
        desc = "# 📋 ОЧС\n\n"
        for ban in chunk:
            d_id, d_name, r_nick, reason, mod, date, proof = ban
            desc += f"**👤 {d_name}** (`{d_id}`)\n**Roblox:** {r_nick}\n**Причина:** {reason}\n**Модератор:** {mod}\n**Дата:** {date}\n"
            if proof: desc += f"**Док-во:** [Ссылка]({proof})\n"
            desc += "\n"
        await interaction.followup.send(embed=discord.Embed(description=desc, color=discord.Color(16711680)))


@bot.tree.command(name="очс-список", description="Показать всех в ЧС", guild=KAP_OBJ)
@is_ochs_staff()
async def list_bans_kap(interaction: discord.Interaction): await handle_list_bans(interaction)


@bot.tree.command(name="очс-список", description="Показать всех в ЧС", guild=MAIN_OBJ)
@is_ochs_staff()
async def list_bans_main(interaction: discord.Interaction): await handle_list_bans(interaction)


# --- ОБЩИЕ КОМАНДЫ ---
@bot.tree.command(name="времроль", description="Выдать роль на время", guild=KAP_OBJ)
@app_commands.describe(user="Кому", role="Какую", hours="Часов")
@is_ochs_staff()
async def temp_role_kap(interaction: discord.Interaction, user: discord.Member, role: discord.Role,
                        hours: float = 1.0): await handle_temp_role(interaction, user, role, hours)


@bot.tree.command(name="времроль", description="Выдать роль на время", guild=MAIN_OBJ)
@app_commands.describe(user="Кому", role="Какую", hours="Часов")
@is_ochs_staff()
async def temp_role_main(interaction: discord.Interaction, user: discord.Member, role: discord.Role,
                         hours: float = 1.0): await handle_temp_role(interaction, user, role, hours)


async def handle_temp_role(interaction, user, role, hours):
    expire = datetime.datetime.now().timestamp() + (hours * 3600)
    try:
        await user.add_roles(role)
    except Exception as e:
        return await interaction.response.send_message(f"❌ Ошибка: {e}", ephemeral=True)
    import sqlite3
    conn = sqlite3.connect('bot_data.db')
    c = conn.cursor()
    c.execute("INSERT INTO temp_roles (discord_id, role_id, expire_at) VALUES (?, ?, ?)", (user.id, role.id, expire))
    conn.commit();
    conn.close()
    await interaction.response.send_message(
        embed=discord.Embed(description=f"## ✅ Роль выдана на {hours} ч.", color=discord.Color(16711680)),
        ephemeral=True)


@bot.tree.command(name="снятьроль", description="Снять роль", guild=KAP_OBJ)
@app_commands.describe(user="У кого", role="Какую")
@is_ochs_staff()
async def remove_role_kap(interaction: discord.Interaction, user: discord.Member,
                          role: discord.Role): await handle_remove_role(interaction, user, role)


@bot.tree.command(name="снятьроль", description="Снять роль", guild=MAIN_OBJ)
@app_commands.describe(user="У кого", role="Какую")
@is_ochs_staff()
async def remove_role_main(interaction: discord.Interaction, user: discord.Member,
                           role: discord.Role): await handle_remove_role(interaction, user, role)


async def handle_remove_role(interaction, user, role):
    try:
        await user.remove_roles(role)
        await interaction.response.send_message(
            embed=discord.Embed(description="## ✅ Роль снята.", color=discord.Color(16711680)), ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"❌ Ошибка: {e}", ephemeral=True)


# ПРОФИЛЬ - ДОСТУПЕН ВСЕМ
@bot.tree.command(name="профиль", description="Показать Roblox профиль", guild=KAP_OBJ)
@app_commands.describe(user="Пользователь", roblox_name="Ник в Роблоксе")
async def profile_kap(interaction: discord.Interaction, user: discord.User = None,
                      roblox_name: str = None): await handle_profile(interaction, user, roblox_name)


@bot.tree.command(name="профиль", description="Показать Roblox профиль", guild=MAIN_OBJ)
@app_commands.describe(user="Пользователь", roblox_name="Ник в Роблоксе")
async def profile_main(interaction: discord.Interaction, user: discord.User = None,
                       roblox_name: str = None): await handle_profile(interaction, user, roblox_name)


async def handle_profile(interaction, user, roblox_name=None):
    await interaction.response.defer(ephemeral=True)
    target = user or interaction.user

    if not roblox_name:
        member = bot.get_guild(MAIN_GUILD_ID).get_member(target.id)
        if member:
            name_to_check = (member.nick or member.display_name)
            found = re.findall(r'[a-zA-Z0-9_]{3,20}', name_to_check)
            if found: roblox_name = max(found, key=len)

    if not roblox_name: return await interaction.followup.send(
        f"❌ Не удалось определить ник. Используйте `/профиль roblox_name:ВашНик`.", ephemeral=True)

    url = "https://users.roblox.com/v1/usernames/users"
    payload = {"usernames": [roblox_name], "excludeBannedUsers": True}
    headers = {"User-Agent": "Mozilla/5.0", "Content-Type": "application/json"}
    roblox_id = None
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get("data"): roblox_id = data["data"][0]["id"]
    except:
        pass

    if not roblox_id: return await interaction.followup.send(f"❌ Не удалось найти Roblox ID по нику `{roblox_name}`.",
                                                             ephemeral=True)

    db.link_user(target.id, roblox_id)

    avatar_url = None
    try:
        async with aiohttp.ClientSession() as session:
            thumb_url = f"https://thumbnails.roblox.com/v1/users/avatar-headshot?userIds={roblox_id}&size=420x420&format=Png"
            async with session.get(thumb_url) as resp:
                if resp.status == 200:
                    thumb_data = await resp.json()
                    if thumb_data.get("data"): avatar_url = thumb_data["data"][0].get("imageUrl")
    except:
        pass

    embed = discord.Embed(
        description=f"## 👤 Профиль {target.mention}\n**Roblox:** {roblox_name}\n**Ссылка:** [Профиль](https://www.roblox.com/users/{roblox_id}/profile)\n**ID:** `{roblox_id}`",
        color=discord.Color(16711680))
    if avatar_url: embed.set_image(url=avatar_url)
    await interaction.followup.send(embed=embed, ephemeral=True)


bot.run(TOKEN)