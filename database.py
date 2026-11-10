import sqlite3
import datetime

DB_NAME = 'bot_data.db'

def init_db():
    try:
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        
        c.execute('''CREATE TABLE IF NOT EXISTS links (discord_id INTEGER PRIMARY KEY, roblox_id INTEGER)''')
        c.execute('''CREATE TABLE IF NOT EXISTS temp_roles (id INTEGER PRIMARY KEY AUTOINCREMENT, discord_id INTEGER, role_id INTEGER, expire_at REAL)''')
        c.execute('''CREATE TABLE IF NOT EXISTS bans (id INTEGER PRIMARY KEY AUTOINCREMENT, discord_id INTEGER, discord_name TEXT, roblox_nick TEXT, reason TEXT, moderator TEXT, date TEXT, proof TEXT)''')
        c.execute('''CREATE INDEX IF NOT EXISTS idx_bans_date ON bans(date)''')
        
        c.execute('''CREATE TABLE IF NOT EXISTS chsp_groups 
                     (group_id INTEGER PRIMARY KEY, group_name TEXT, group_link TEXT, reason TEXT, moderator TEXT, date TEXT)''')
                     
        c.execute('''CREATE TABLE IF NOT EXISTS chsp_pending 
                     (discord_id INTEGER, roblox_id INTEGER, group_id INTEGER, deadline REAL, PRIMARY KEY(discord_id, group_id))''')
                      
        c.execute('''CREATE TABLE IF NOT EXISTS chsp_strikes 
                     (discord_id INTEGER PRIMARY KEY, strikes INTEGER DEFAULT 0)''')
        
        # Таблица для кодов верификации
        c.execute('''CREATE TABLE IF NOT EXISTS verify_codes 
                     (code TEXT PRIMARY KEY, discord_id INTEGER, expire_at REAL)''')
        
        c.execute("PRAGMA table_info(chsp_pending)")
        columns = [col[1] for col in c.fetchall()]
        
        if "notified_12h" not in columns:
            c.execute("ALTER TABLE chsp_pending ADD COLUMN notified_12h INTEGER DEFAULT 0")
        if "notified_1h" not in columns:
            c.execute("ALTER TABLE chsp_pending ADD COLUMN notified_1h INTEGER DEFAULT 0")

        conn.commit()
        conn.close()
        print("[+] База данных инициализирована.")
    except sqlite3.Error as e:
        print(f"[!] Ошибка инициализации БД: {e}")

# === ФУНКЦИИ ДЛЯ ВЕРИФИКАЦИИ ===
def add_verify_code(code, discord_id):
    conn = sqlite3.connect(DB_NAME)
    try:
        c = conn.cursor()
        expire_at = datetime.datetime.now().timestamp() + 600 # 10 минут
        c.execute("INSERT OR REPLACE INTO verify_codes VALUES (?, ?, ?)", (code, discord_id, expire_at))
        conn.commit()
    finally:
        conn.close()

def get_discord_id_by_code(code):
    conn = sqlite3.connect(DB_NAME)
    try:
        c = conn.cursor()
        c.execute("SELECT discord_id, expire_at FROM verify_codes WHERE code = ?", (code,))
        res = c.fetchone()
        if res:
            if res[1] > datetime.datetime.now().timestamp():
                return res[0] # Код действителен
            else:
                c.execute("DELETE FROM verify_codes WHERE code = ?", (code,))
                conn.commit()
    finally:
        conn.close()
    return None

def check_link(discord_id):
    conn = sqlite3.connect(DB_NAME)
    try:
        c = conn.cursor()
        c.execute("SELECT roblox_id FROM links WHERE discord_id = ?", (discord_id,))
        res = c.fetchone()
        return res[0] if res else None
    finally:
        conn.close()

def remove_verify_code(code):
    conn = sqlite3.connect(DB_NAME)
    try:
        c = conn.cursor()
        c.execute("DELETE FROM verify_codes WHERE code = ?", (code,))
        conn.commit()
    finally:
        conn.close()

# === ОСНОВНЫЕ ФУНКЦИИ ===
def link_user(discord_id, roblox_id):
    conn = sqlite3.connect(DB_NAME)
    try:
        c = conn.cursor()
        c.execute("INSERT OR REPLACE INTO links VALUES (?, ?)", (discord_id, roblox_id))
        conn.commit()
    finally:
        conn.close()

def get_all_bans():
    conn = sqlite3.connect(DB_NAME)
    try:
        c = conn.cursor()
        c.execute("SELECT discord_id, discord_name, roblox_nick, reason, moderator, date, proof FROM bans ORDER BY date DESC")
        return c.fetchall()
    finally:
        conn.close()

def remove_ban(discord_id):
    conn = sqlite3.connect(DB_NAME)
    try:
        c = conn.cursor()
        c.execute("DELETE FROM bans WHERE discord_id = ?", (discord_id,))
        conn.commit()
    finally:
        conn.close()

def is_banned(discord_id):
    conn = sqlite3.connect(DB_NAME)
    try:
        c = conn.cursor()
        c.execute("SELECT 1 FROM bans WHERE discord_id = ?", (discord_id,))
        return c.fetchone() is not None
    finally:
        conn.close()

def add_ban(discord_id, discord_name, roblox_nick, reason, moderator, proof):
    conn = sqlite3.connect(DB_NAME)
    try:
        c = conn.cursor()
        c.execute("INSERT INTO bans (discord_id, discord_name, roblox_nick, reason, moderator, date, proof) VALUES (?, ?, ?, ?, ?, ?, ?)",
                  (discord_id, discord_name, roblox_nick, reason, moderator, datetime.datetime.now().strftime("%d.%m.%Y %H:%M"), proof))
        conn.commit()
    finally:
        conn.close()

def add_chsp_group(group_id, group_name, group_link, reason, moderator):
    conn = sqlite3.connect(DB_NAME)
    try:
        c = conn.cursor()
        c.execute("INSERT OR REPLACE INTO chsp_groups VALUES (?, ?, ?, ?, ?, ?)",
                  (group_id, group_name, group_link, reason, moderator, datetime.datetime.now().strftime("%d.%m.%Y %H:%M")))
        conn.commit()
    finally:
        conn.close()

def remove_chsp_group(group_id):
    conn = sqlite3.connect(DB_NAME)
    try:
        c = conn.cursor()
        c.execute("DELETE FROM chsp_groups WHERE group_id = ?", (group_id,))
        c.execute("DELETE FROM chsp_pending WHERE group_id = ?", (group_id,))
        conn.commit()
    finally:
        conn.close()

def get_chsp_group_by_id(group_id):
    conn = sqlite3.connect(DB_NAME)
    try:
        c = conn.cursor()
        c.execute("SELECT group_name, group_link FROM chsp_groups WHERE group_id = ?", (group_id,))
        return c.fetchone()
    finally:
        conn.close()

def get_all_chsp_groups():
    conn = sqlite3.connect(DB_NAME)
    try:
        c = conn.cursor()
        c.execute("SELECT group_id, group_name, group_link FROM chsp_groups")
        return c.fetchall()
    finally:
        conn.close()

def add_pending_chsp(discord_id, roblox_id, group_id, deadline_timestamp):
    conn = sqlite3.connect(DB_NAME)
    try:
        c = conn.cursor()
        c.execute("INSERT OR REPLACE INTO chsp_pending (discord_id, roblox_id, group_id, deadline, notified_12h, notified_1h) VALUES (?, ?, ?, ?, 0, 0)", (discord_id, roblox_id, group_id, deadline_timestamp))
        conn.commit()
    finally:
        conn.close()

def get_all_pending():
    conn = sqlite3.connect(DB_NAME)
    try:
        c = conn.cursor()
        c.execute("SELECT discord_id, roblox_id, group_id, deadline, notified_12h, notified_1h FROM chsp_pending")
        return c.fetchall()
    finally:
        conn.close()

def get_expired_pending():
    conn = sqlite3.connect(DB_NAME)
    try:
        c = conn.cursor()
        now = datetime.datetime.now().timestamp()
        c.execute("SELECT discord_id, group_id, roblox_id FROM chsp_pending WHERE deadline <= ?", (now,))
        return c.fetchall()
    finally:
        conn.close()

def get_warnings_to_send():
    conn = sqlite3.connect(DB_NAME)
    try:
        c = conn.cursor()
        now = datetime.datetime.now().timestamp()
        c.execute("SELECT p.discord_id, p.group_id, p.deadline, g.group_name, g.group_link FROM chsp_pending p JOIN chsp_groups g ON p.group_id = g.group_id WHERE p.deadline > ? AND (p.deadline - ?) <= 3600 AND p.notified_1h = 0", (now, now))
        return c.fetchall()
    finally:
        conn.close()

def update_reminder_flag(discord_id, group_id, flag_name):
    conn = sqlite3.connect(DB_NAME)
    try:
        c = conn.cursor()
        c.execute(f"UPDATE chsp_pending SET {flag_name} = 1 WHERE discord_id = ? AND group_id = ?", (discord_id, group_id))
        conn.commit()
    finally:
        conn.close()

def remove_pending_chsp(discord_id, group_id=None):
    conn = sqlite3.connect(DB_NAME)
    try:
        c = conn.cursor()
        if group_id:
            c.execute("DELETE FROM chsp_pending WHERE discord_id = ? AND group_id = ?", (discord_id, group_id))
        else:
            c.execute("DELETE FROM chsp_pending WHERE discord_id = ?", (discord_id,))
        conn.commit()
    finally:
        conn.close()

def get_strikes(discord_id):
    conn = sqlite3.connect(DB_NAME)
    try:
        c = conn.cursor()
        c.execute("SELECT strikes FROM chsp_strikes WHERE discord_id = ?", (discord_id,))
        res = c.fetchone()
        return res[0] if res else 0
    finally:
        conn.close()

def add_strike(discord_id):
    conn = sqlite3.connect(DB_NAME)
    try:
        c = conn.cursor()
        c.execute("INSERT INTO chsp_strikes (discord_id, strikes) VALUES (?, 1) ON CONFLICT(discord_id) DO UPDATE SET strikes = strikes + 1", (discord_id,))
        conn.commit()
    finally:
        conn.close()
