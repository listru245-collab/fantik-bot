import aiohttp
import discord
from discord import app_commands
from discord.ext import commands
import json
import os
import datetime
import time
import uuid
import re
import sqlite3
from typing import Optional, Dict
import hashlib
import base64

DIR = os.path.dirname(os.path.abspath(__file__))

# ===== ЗАГРУЗКА ТОКЕНА (из зашифрованного файла или env) =====
def decrypt_token(encrypted_b64, key_b64):
    key = base64.b64decode(key_b64)
    enc = base64.b64decode(encrypted_b64)
    derived = hashlib.pbkdf2_hmac('sha256', key, b'failbot_salt', 100000)
    dec = bytes([enc[i] ^ derived[i % len(derived)] for i in range(len(enc))])
    return dec.decode()

def load_token():
    keyf = os.path.join(DIR, "bot.key")
    encf = os.path.join(DIR, "token.enc")
    if os.path.exists(keyf) and os.path.exists(encf):
        try:
            with open(keyf, "r") as f: key_data = f.read().strip()
            with open(encf, "r") as f: enc_data = f.read().strip()
            t = decrypt_token(enc_data, key_data)
            if t: return t
        except Exception as e:
            print(f"[-] Ошибка расшифровки токена: {e}")
    env_t = os.getenv("DISCORD_TOKEN")
    if env_t: return env_t
    return ""

# ===== БАЗА ДАННЫХ =====
DB_FILE = os.path.join(DIR, "failbot.db")

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS message_buttons (message_id TEXT PRIMARY KEY, guild_id INTEGER, channel_id INTEGER, buttons TEXT)")
    # Начальные значения если их нет
    defaults = {
        "log_channel_id": "",
        "everyone_role_id": "",
        "owner_id": "",
        "allowed_role_ids": "[]",
        "allowed_guilds": "[]",
        "boost_channel_id": "",
        "welcome_channel_id": "",
    }
    for k, v in defaults.items():
        c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (k, v))
    conn.commit()
    conn.close()

def get_setting(key, default=""):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT value FROM settings WHERE key = ?", (key,))
    row = c.fetchone()
    conn.close()
    if row: return row[0]
    return default

def set_setting(key, value):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(value)))
    conn.commit()
    conn.close()

def get_allowed_roles():
    v = get_setting("allowed_role_ids", "[]")
    try: return json.loads(v)
    except: return []

def add_allowed_role(rid):
    roles = get_allowed_roles()
    if rid not in roles: roles.append(rid)
    set_setting("allowed_role_ids", json.dumps(roles))

def get_allowed_guilds():
    v = get_setting("allowed_guilds", "[]")
    try: return json.loads(v)
    except: return []

def add_allowed_guild(gid):
    guilds = get_allowed_guilds()
    if gid not in guilds: guilds.append(gid)
    set_setting("allowed_guilds", json.dumps(guilds))

def save_buttons(msg_id, guild_id, channel_id, buttons_list):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO message_buttons (message_id, guild_id, channel_id, buttons) VALUES (?, ?, ?, ?)",
              (str(msg_id), int(guild_id), int(channel_id), json.dumps(buttons_list, ensure_ascii=False)))
    conn.commit()
    conn.close()

def get_all_buttons():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT message_id, guild_id, channel_id, buttons FROM message_buttons")
    rows = c.fetchall()
    conn.close()
    result = {}
    for mid, gid, chid, btns in rows:
        try: result[mid] = {"guild_id": gid, "channel_id": chid, "buttons": json.loads(btns)}
        except: pass
    return result

def delete_button(msg_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("DELETE FROM message_buttons WHERE message_id = ?", (str(msg_id),))
    conn.commit()
    conn.close()

# ===== ТЕКСТА (ЖЁСТКО ЗАШИТЫ) =====
WELCOME_TEXT = """<a:PinkBearSparkle:1522047492420800695> **ДОБРО ПОЖАЛОВАТЬ** <a:PinkBearSparkle:1522047492420800695>

<a:excited_cinnamoroll:1522048092273377500> Привет, **{name}**! Добро пожаловать на сервер **{server}**!

└ Мы очень рады, что ты присоединился к нашему уютному сообществу.
└ Желаем тебе найти здесь новых друзей и отлично провести время!

📌 **Не забудь заглянуть в правила и выбрать себе роли, чтобы полноценно пользоваться сервером.**"""

BOOST_TEXT = """<a:PinkBearSparkle:1522047492420800695> **СЕРВЕР ЗАБУСТЕН** <a:PinkBearSparkle:1522047492420800695>

<a:PinkHeart:1522047975952744699> **{user}**, огромное спасибо за поддержку нашего сервера **{server}**!

└ Твой буст помогает нам развиваться, добавлять новые функции и становиться ещё уютнее.
└ Мы очень ценим твою помощь и преданность проекту!

<a:flex:1522052547257303070> **Ты просто легенда!**"""

# ===== ИНИЦИАЛИЗАЦИЯ =====
TOKEN = load_token()
init_db()

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents, case_insensitive=True)

COOLDOWNS: Dict[str, float] = {}
CMD_COOLDOWNS: Dict[str, float] = {}
COOLDOWN_SECONDS = 3600

def get_moscow_time():
    return datetime.datetime.utcnow() + datetime.timedelta(hours=3)

def is_night_time():
    now = get_moscow_time()
    hour = now.hour
    return hour >= 23 or hour < 8

def has_ad_keywords(text):
    if not text: return False
    kw = ["заходите", "переходите", "мы ищем", "мы даем"]
    t = text.lower()
    return any(k.lower() in t for k in kw)

async def get_log_channel(guild):
    cid = get_setting("log_channel_id")
    if cid and cid.isdigit():
        ch = guild.get_channel(int(cid))
        if ch: return ch
    return None

async def send_log(guild, embed):
    ch = await get_log_channel(guild)
    if ch:
        try: await ch.send(embed=embed)
        except: pass

def make_log_embed(title, desc, color, author=None):
    e = discord.Embed(title=title, description=desc, color=color, timestamp=datetime.datetime.now(datetime.timezone.utc))
    if author:
        e.set_footer(text=f"{author} ({author.id})", icon_url=author.display_avatar.url)
    else:
        e.set_footer(text=f"Fail Bot - {get_moscow_time().strftime('%d.%m.%Y %H:%M')} MSK")
    return e

async def check_access(interaction):
    if interaction.user.guild_permissions.administrator: return True
    oid = get_setting("owner_id")
    if oid and oid.isdigit() and interaction.user.id == int(oid): return True
    allowed = get_allowed_roles()
    if allowed:
        uroles = [r.id for r in interaction.user.roles]
        if any(rid in uroles for rid in allowed): return True
    return False

# ===== ЦВЕТА =====
COLOR_OPTIONS = {
    "Синий": discord.Color.blurple(), "Красный": discord.Color.red(),
    "Зелёный": discord.Color.green(), "Жёлтый": discord.Color.gold(),
    "Оранжевый": discord.Color.orange(), "Фиолетовый": discord.Color.purple(),
    "Розовый": discord.Color.magenta(), "Бирюзовый": discord.Color.teal(),
    "Серый": discord.Color.greyple(), "Чёрный": discord.Color.default(),
}

BUTTON_ACTIONS = {"give": "Выдать роль", "remove": "Снять роль", "toggle": "Переключать"}

# ===== КНОПКИ =====
class RoleButtonView(discord.ui.View):
    def __init__(self, message_id):
        super().__init__(timeout=None)
        self.message_id = str(message_id)
        all_btns = get_all_buttons()
        msg_config = all_btns.get(self.message_id)
        if not msg_config: return
        for i, bc in enumerate(msg_config["buttons"]):
            sm = {"primary": discord.ButtonStyle.primary, "secondary": discord.ButtonStyle.secondary, "success": discord.ButtonStyle.success, "danger": discord.ButtonStyle.danger}
            self.add_item(RoleButtonItem(bc["label"], sm.get(bc.get("style_str","primary"), discord.ButtonStyle.primary), f"fail_btn_{self.message_id}_{i}", bc, msg_config))

class RoleButtonItem(discord.ui.Button):
    def __init__(self, label, style, custom_id, bc, mc):
        super().__init__(label=label, style=style, custom_id=custom_id)
        self.bc = bc; self.mc = mc
    async def callback(self, interaction):
        role = interaction.guild.get_role(self.bc["role_id"])
        if not role:
            self.label = f"{self.bc['label']} (удалена)"; self.disabled = True
            await interaction.response.edit_message(view=self.view)
            await interaction.followup.send("Эта роль удалена на сервере.", ephemeral=True); return
        action = self.bc["action"]; ck = f"{interaction.user.id}_{self.custom_id}"; now = time.time()
        if action == "toggle":
            last = COOLDOWNS.get(ck, 0); rem = COOLDOWN_SECONDS - (now - last)
            if rem > 0:
                m, s = int(rem//60), int(rem%60)
                await interaction.response.send_message(f"Подождите {m} мин {s} сек.", ephemeral=True); return
            COOLDOWNS[ck] = now
            if role in interaction.user.roles:
                await interaction.user.remove_roles(role, reason="Fail toggle")
                await interaction.response.send_message(f"Роль {role.mention} снята.", ephemeral=True)
                await send_log(interaction.guild, make_log_embed("Роль снята", f"{interaction.user.mention}\nРоль: {role.mention}", discord.Color.orange(), interaction.user))
            else:
                await interaction.user.add_roles(role, reason="Fail toggle")
                await interaction.response.send_message(f"Роль {role.mention} выдана.", ephemeral=True)
                await send_log(interaction.guild, make_log_embed("Роль выдана", f"{interaction.user.mention}\nРоль: {role.mention}", discord.Color.green(), interaction.user))
        elif action == "give":
            if role in interaction.user.roles: await interaction.response.send_message(f"Роль {role.mention} уже есть.", ephemeral=True); return
            await interaction.user.add_roles(role, reason="Fail give")
            await interaction.response.send_message(f"Роль {role.mention} выдана.", ephemeral=True)
            await send_log(interaction.guild, make_log_embed("Роль выдана", f"{interaction.user.mention}\nРоль: {role.mention}", discord.Color.green(), interaction.user))
        elif action == "remove":
            if role not in interaction.user.roles: await interaction.response.send_message(f"Роль {role.mention} и так нет.", ephemeral=True); return
            await interaction.user.remove_roles(role, reason="Fail remove")
            await interaction.response.send_message(f"Роль {role.mention} снята.", ephemeral=True)
            await send_log(interaction.guild, make_log_embed("Роль снята", f"{interaction.user.mention}\nРоль: {role.mention}", discord.Color.orange(), interaction.user))

GIF_NOTIF = "https://i.ibb.co/68Wc6bby/profile.png"       # Картинка ПРОФИЛЬ
GIF_HOBBY = "https://i.ibb.co/YFp9Y3gW/cozy-roles.png"     # Картинка УЮТНЫЕ РОЛИ
GIF_GENDER = "https://i.ibb.co/Pv0GswT0/gaming-roles.png"  # Картинка ИГРОВЫЕ РОЛИ

BUTTON_EMOJI = discord.PartialEmoji(name="emoji_40", id=1523848897590726668)

class RoleSelectItem(discord.ui.Select):
    def __init__(self, guild, roles_list, placeholder, min_vals, max_vals):
        opts = []
        for rid, label in roles_list:
            r = guild.get_role(rid)
            if r:
                opts.append(discord.SelectOption(label=label, value=str(rid)))
        super().__init__(placeholder=placeholder, options=opts, min_values=min_vals, max_values=max_vals)
    async def callback(self, interaction):
        now = time.time()
        changed = []
        for val in self.values:
            rid = int(val)
            role = interaction.guild.get_role(rid)
            if not role:
                await interaction.response.send_message("Роль удалена на сервере.", ephemeral=True)
                return
            ck = f"rolesel_{interaction.user.id}_{rid}"
            last = COOLDOWNS.get(ck, 0)
            rem = COOLDOWN_SECONDS - (now - last)
            if rem > 0:
                continue
            COOLDOWNS[ck] = now
            if role in interaction.user.roles:
                await interaction.user.remove_roles(role, reason="Выбор ролей")
                changed.append((role, False))
            else:
                await interaction.user.add_roles(role, reason="Выбор ролей")
                changed.append((role, True))
        if not changed:
            m, s = int(COOLDOWN_SECONDS//60), int(COOLDOWN_SECONDS%60)
            await interaction.response.send_message(f"Подождите {m} мин {s} сек между действиями с одной ролью.", ephemeral=True)
            return
        lines = []
        for role, added in changed:
            em = ":white_check_mark:" if added else ":x:"
            lines.append(f"{em} {role.mention} {'выдана' if added else 'снята'}")
            log_title = "Роль выдана" if added else "Роль снята"
            await send_log(interaction.guild, make_log_embed(log_title, f"{interaction.user.mention}\nРоль: {role.mention}", discord.Color.green() if added else discord.Color.orange(), interaction.user))
        await interaction.response.send_message("\n".join(lines), ephemeral=True)

POL_ROLES = [(1522402019137159329, "Мужской"), (1522402087252529203, "Женский")]
UVLECHENIYA_ROLES = [(1522402430212505722, "Дизайнер"), (1522402293188788355, "Читатель"), (1522402184686473398, "Геймер")]
NOTIFICATION_ROLES = [(1522402699310792807, "Важные новости"), (1522402763324260464, "Розыгрыши и дропы"), (1522402871293775952, "Игровые сборы"), (1522402942999724222, "Войс-Активность")]

class RoleMenuView1(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
    @discord.ui.button(label="Список ролей уведомлений", emoji=BUTTON_EMOJI, style=discord.ButtonStyle.secondary, custom_id="roles_notifications")
    async def notif_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        opts = []
        for rid, label in NOTIFICATION_ROLES:
            r = interaction.guild.get_role(rid)
            if r: opts.append(discord.SelectOption(label=label, value=str(rid)))
        if not opts:
            await interaction.response.send_message("Роли уведомлений не найдены.", ephemeral=True); return
        v = discord.ui.View(timeout=60)
        v.add_item(RoleSelectItem(interaction.guild, NOTIFICATION_ROLES, "Выберите роли уведомлений", 0, len(NOTIFICATION_ROLES)))
        await interaction.response.send_message("Выберите роли уведомлений:", view=v, ephemeral=True)

class RoleMenuView2(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
    @discord.ui.button(label="Список ролей увлечений", emoji=BUTTON_EMOJI, style=discord.ButtonStyle.secondary, custom_id="roles_hobbies")
    async def hobby_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        opts = []
        for rid, label in UVLECHENIYA_ROLES:
            r = interaction.guild.get_role(rid)
            if r: opts.append(discord.SelectOption(label=label, value=str(rid)))
        if not opts:
            await interaction.response.send_message("Роли увлечений не найдены.", ephemeral=True); return
        v = discord.ui.View(timeout=60)
        v.add_item(RoleSelectItem(interaction.guild, UVLECHENIYA_ROLES, "Выберите роли увлечений", 0, len(UVLECHENIYA_ROLES)))
        await interaction.response.send_message("Выберите роли увлечений:", view=v, ephemeral=True)

class RoleMenuView3(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
    @discord.ui.button(label="Список ролей пола", emoji=BUTTON_EMOJI, style=discord.ButtonStyle.secondary, custom_id="roles_gender")
    async def gender_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        opts = []
        for rid, label in POL_ROLES:
            r = interaction.guild.get_role(rid)
            if r: opts.append(discord.SelectOption(label=label, value=str(rid)))
        if not opts:
            await interaction.response.send_message("Роли пола не найдены.", ephemeral=True); return
        v = discord.ui.View(timeout=60)
        v.add_item(RoleSelectItem(interaction.guild, POL_ROLES, "Выберите пол", 1, 1))
        await interaction.response.send_message("Выберите пол:", view=v, ephemeral=True)

# ===== UI КОМПОНЕНТЫ =====
class ColorSelect(discord.ui.Select):
    def __init__(self, cb):
        self.cb = cb
        super().__init__(placeholder="Цвет полоски", options=[discord.SelectOption(label=n, value=n) for n in COLOR_OPTIONS])
    async def callback(self, i): await self.cb(i, self.values[0])

class ColorView(discord.ui.View):
    def __init__(self, cb, t=60):
        super().__init__(timeout=t); self.add_item(ColorSelect(cb))

class RoleSelect(discord.ui.Select):
    def __init__(self, guild, pl, cb):
        self.cb = cb
        roles = [r for r in guild.roles if not r.is_default() and not r.is_bot_managed() and r.name != "@everyone"][:25]
        super().__init__(placeholder=pl, options=[discord.SelectOption(label=r.name, value=str(r.id)) for r in roles])
    async def callback(self, i): await self.cb(i, self.values[0])

class RoleView(discord.ui.View):
    def __init__(self, guild, pl, cb, t=60):
        super().__init__(timeout=t); self.add_item(RoleSelect(guild, pl, cb))

class ChannelSelect(discord.ui.Select):
    def __init__(self, guild, pl, cb):
        self.cb = cb
        channels = [c for c in guild.text_channels][:25]
        super().__init__(placeholder=pl, options=[discord.SelectOption(label=f"#{c.name}", value=str(c.id)) for c in channels])
    async def callback(self, i): await self.cb(i, self.values[0])

class ChannelView(discord.ui.View):
    def __init__(self, guild, pl, cb, t=60):
        super().__init__(timeout=t); self.add_item(ChannelSelect(guild, pl, cb))

class ButtonCreateModal(discord.ui.Modal, title="Создание кнопки"):
    def __init__(self, cb):
        super().__init__()
        self.cb = cb
        self.add_item(discord.ui.TextInput(label="Текст", placeholder="VIP", style=discord.TextStyle.short, required=True, max_length=80))
        self.add_item(discord.ui.TextInput(label="Цвет", placeholder="success/danger/primary/secondary", style=discord.TextStyle.short, required=True, max_length=20))
        self.add_item(discord.ui.TextInput(label="Действие", placeholder="give/remove/toggle", style=discord.TextStyle.short, required=True, max_length=10))
    async def on_submit(self, i):
        s = self.children[1].value.strip().lower(); a = self.children[2].value.strip().lower()
        if s not in {"success","danger","primary","secondary"}: await i.response.send_message("Цвет: success/danger/primary/secondary", ephemeral=True); return
        if a not in {"give","remove","toggle"}: await i.response.send_message("Действие: give/remove/toggle", ephemeral=True); return
        await self.cb(i, self.children[0].value, s, a)

class SetMsgModal(discord.ui.Modal, title="Создание embed"):
    def __init__(self):
        super().__init__()
        self.add_item(discord.ui.TextInput(label="Заголовок", placeholder="Заголовок", style=discord.TextStyle.short, required=True, max_length=256))
        self.add_item(discord.ui.TextInput(label="Текст", placeholder="Текст сообщения", style=discord.TextStyle.paragraph, required=True, max_length=4000))
        self.add_item(discord.ui.TextInput(label="Картинка", placeholder="https://... (необязательно)", style=discord.TextStyle.short, required=False, max_length=512))
    async def on_submit(self, i):
        self.t1 = self.children[0].value; self.t2 = self.children[1].value; self.t3 = self.children[2].value
        v = ColorView(self.on_color)
        await i.response.send_message(embed=discord.Embed(title="Цвет", description="Выберите цвет:", color=discord.Color.blue()), view=v, ephemeral=True)
    async def on_color(self, i, cn):
        c = COLOR_OPTIONS[cn]; e = discord.Embed(title=self.t1, description=self.t2, color=c)
        if self.t3: e.set_image(url=self.t3)
        e.set_footer(text=f"Fail Bot - {get_moscow_time().strftime('%d.%m.%Y %H:%M')} MSK")
        v = SetMsgActionView(e, i.channel, cn, [])
        await i.response.edit_message(embed=discord.Embed(title="Предпросмотр", description=f"Цвет: {cn}", color=discord.Color.green()), view=v)
        await i.followup.send(embed=e, ephemeral=True)

class SetMsgActionView(discord.ui.View):
    def __init__(self, embed, channel, color_name="Синий", buttons_list=None):
        super().__init__(timeout=300)
        self.embed = embed; self.channel = channel; self.target_channel = channel
        self.color_name = color_name; self.buttons_list = buttons_list or []
        self.update_buttons()
    def update_buttons(self):
        self.clear_items()
        self.add_item(discord.ui.Button(label="Отправить", style=discord.ButtonStyle.success, custom_id="send_msg"))
        self.add_item(discord.ui.Button(label="Редактировать", style=discord.ButtonStyle.primary, custom_id="edit_msg"))
        self.add_item(discord.ui.Button(label="Сменить канал", style=discord.ButtonStyle.secondary, custom_id="chan_msg"))
        self.add_item(discord.ui.Button(label="Добавить кнопку", style=discord.ButtonStyle.primary, custom_id="add_btn_msg"))
        if self.buttons_list:
            self.add_item(discord.ui.Button(label=f"Кнопок: {len(self.buttons_list)}", style=discord.ButtonStyle.success, custom_id="show_btns"))
        self.add_item(discord.ui.Button(label="Отмена", style=discord.ButtonStyle.danger, custom_id="cancel_msg"))
    async def interaction_check(self, i):
        cid = i.data.get("custom_id")
        if cid == "send_msg":
            found = re.findall(r'https?://[^\s]+', (self.embed.title or "") + " " + (self.embed.description or ""))
            if found:
                await i.response.edit_message(embed=discord.Embed(title="Ссылки найдены", description=f"Обнаружено {len(found)} ссылок.", color=discord.Color.gold()), view=None)
                await i.followup.send("\n".join(found[:5]), ephemeral=True)
            sent = await self.target_channel.send(embed=self.embed)
            if self.buttons_list:
                save_buttons(sent.id, sent.guild.id, sent.channel.id, self.buttons_list)
                await sent.edit(view=RoleButtonView(sent.id))
            await send_log(i.guild, make_log_embed("Отправка embed", f"Автор: {i.user.mention}\nКанал: {self.target_channel.mention}", discord.Color.orange(), i.user))
            await i.response.edit_message(embed=discord.Embed(title="Отправлено!", description=f"В {self.target_channel.mention}", color=discord.Color.green()), view=None)
        elif cid == "edit_msg": await i.response.send_modal(EditEmbedModal(self.embed, self.buttons_list))
        elif cid == "chan_msg":
            async def on_ch(i2, cid2):
                ch = i2.guild.get_channel(int(cid2))
                if ch: self.target_channel = ch; self.update_buttons()
                await i2.response.edit_message(embed=discord.Embed(title="Канал изменён", description=f"Канал: {ch.mention}", color=discord.Color.green()), view=self)
            await i.response.edit_message(view=ChannelView(i.guild, "Выберите канал:", on_ch))
        elif cid == "add_btn_msg": await i.response.send_modal(ButtonCreateModal(lambda inter, label, s, a: self.handle_create(inter, label, s, a)))
        elif cid == "show_btns":
            txt = "**Кнопки:**\n"
            for idx, b in enumerate(self.buttons_list, 1):
                an = {"give":"Выдать","remove":"Снять","toggle":"Переключать"}
                txt += f"{idx}. `{b['label']}` | {b['style_str']} | {an.get(b['action'],b['action'])} | <@&{b['role_id']}>\n"
            await i.response.send_message(txt, ephemeral=True)
        elif cid == "cancel_msg": await i.response.edit_message(embed=discord.Embed(title="Отменено", color=discord.Color.red()), view=None)
        return False
    async def handle_create(self, i, label, style_str, action):
        async def on_role(i2, rid):
            role = i2.guild.get_role(int(rid))
            if not role: await i2.response.send_message("Роль не найдена", ephemeral=True); return
            self.buttons_list.append({"label": label, "style_str": style_str, "action": action, "role_id": int(rid)})
            v = SetMsgActionView(self.embed, self.channel, self.color_name, self.buttons_list)
            await i2.response.edit_message(embed=discord.Embed(title="Готово!", description=f"Кнопка `{label}`. Всего: {len(self.buttons_list)}", color=discord.Color.green()), view=v)
        v = RoleView(i.guild, "Выберите роль:", on_role)
        await i.response.edit_message(embed=discord.Embed(title="Выбор роли", description=f"{label}\n{style_str}\n{BUTTON_ACTIONS.get(action,action)}", color=discord.Color.blue()), view=v)

class EditEmbedModal(discord.ui.Modal, title="Редактировать embed"):
    def __init__(self, embed, buttons_list=None):
        super().__init__()
        self.original_embed = embed; self.buttons_list = buttons_list or []
        self.add_item(discord.ui.TextInput(label="Заголовок", default=embed.title or "", style=discord.TextStyle.short, required=True, max_length=256))
        self.add_item(discord.ui.TextInput(label="Текст", default=embed.description or "", style=discord.TextStyle.paragraph, required=True, max_length=4000))
        self.add_item(discord.ui.TextInput(label="Картинка", default=embed.image.url if embed.image else "", style=discord.TextStyle.short, required=False, max_length=512))
    async def on_submit(self, i):
        self.t1 = self.children[0].value; self.t2 = self.children[1].value; self.t3 = self.children[2].value
        v = ColorView(self.on_color)
        await i.response.edit_message(embed=discord.Embed(title="Цвет", description="Выберите цвет:", color=discord.Color.blue()), view=v)
    async def on_color(self, i, cn):
        c = COLOR_OPTIONS[cn]; e = discord.Embed(title=self.t1, description=self.t2, color=c)
        if self.t3: e.set_image(url=self.t3)
        e.set_footer(text=f"Fail Bot - {get_moscow_time().strftime('%d.%m.%Y %H:%M')} MSK")
        v = SetMsgActionView(e, i.channel, cn, self.buttons_list)
        await i.response.edit_message(embed=discord.Embed(title="Предпросмотр", description=f"Цвет: {cn}", color=discord.Color.green()), view=v)
        await i.followup.send(embed=e, ephemeral=True)

# ===== СОБЫТИЯ =====
@bot.event
async def on_ready():
    print(f"[+] Бот {bot.user} запущен!")
    await bot.change_presence(status=discord.Status.dnd, activity=discord.Activity(type=discord.ActivityType.listening, name="ПУМА MARIA BOGINYA"))
    allowed = get_allowed_guilds()
    if allowed:
        for g in bot.guilds:
            if g.id not in allowed:
                try:
                    print(f"[-] Выход с {g.name} ({g.id})")
                    await g.leave()
                except: pass
    all_btns = get_all_buttons()
    for mid_str in list(all_btns.keys()):
        try: bot.add_view(RoleButtonView(int(mid_str)), message_id=int(mid_str))
        except: pass
    
    # Регистрируем persistent views для setroles
    bot.add_view(RoleMenuView1())
    bot.add_view(RoleMenuView2())
    bot.add_view(RoleMenuView3())
    
    print(f"[+] Кнопок загружено: {len(all_btns)}")
    try:
        synced = await bot.tree.sync()
        print(f"[+] Команд: {', '.join(c.name for c in synced)}")
    except Exception as e: print(f"[-] Ошибка синхронизации: {e}")

@bot.event
async def on_message_delete(msg):
    if msg.author.bot or not msg.guild: return
    mid = str(msg.id)
    all_btns = get_all_buttons()
    if mid in all_btns: delete_button(mid)
    e = make_log_embed("Удаление", f"**Канал:** {msg.channel.mention}\n**Автор:** {msg.author.mention}", discord.Color.red(), msg.author)
    if msg.content: e.description += f"\n**Содержимое:** ```{msg.content[:1000]}```"
    if msg.attachments: e.add_field(name="Вложения", value=f"{len(msg.attachments)} файл(ов)", inline=False)
    await send_log(msg.guild, e)

@bot.event
async def on_message_edit(before, after):
    if before.author.bot or not before.guild or before.content == after.content: return
    e = make_log_embed("Редактирование", f"**Канал:** {before.channel.mention}\n**Автор:** {before.author.mention}", discord.Color.orange(), before.author)
    e.add_field(name="**До:**", value=before.content[:1024] or "Пусто", inline=False)
    e.add_field(name="**После:**", value=after.content[:1024] or "Пусто", inline=False)
    await send_log(before.guild, e)

@bot.event
async def on_member_remove(member):
    if not member.guild: return
    e = make_log_embed("Выход / Кик", f"**Участник:** {member.mention} (`{member.id}`)", discord.Color.light_grey(), member)
    async for entry in member.guild.audit_logs(limit=1, action=discord.AuditLogAction.kick):
        if entry.target.id == member.id:
            e.title = "Кик"; e.add_field(name="**Модератор:**", value=f"{entry.user.mention}", inline=False)
            if entry.reason: e.add_field(name="**Причина:**", value=entry.reason, inline=False)
    await send_log(member.guild, e)

@bot.event
async def on_member_ban(guild, user):
    e = make_log_embed("Бан", f"**Пользователь:** {user.mention} (`{user.id}`)", discord.Color.dark_red())
    async for entry in guild.audit_logs(limit=1, action=discord.AuditLogAction.ban):
        if entry.target.id == user.id:
            e.add_field(name="**Модератор:**", value=f"{entry.user.mention}", inline=False)
            if entry.reason: e.add_field(name="**Причина:**", value=entry.reason, inline=False)
    await send_log(guild, e)

@bot.event
async def on_member_unban(guild, user):
    e = make_log_embed("Разбан", f"**Пользователь:** {user.mention} (`{user.id}`)", discord.Color.green())
    async for entry in guild.audit_logs(limit=1, action=discord.AuditLogAction.unban):
        if entry.target.id == user.id: e.add_field(name="**Модератор:**", value=f"{entry.user.mention}", inline=False)
    await send_log(guild, e)

@bot.event
async def on_guild_channel_create(channel):
    e = make_log_embed("Создание канала", f"**{channel.name}**\nТип: {str(channel.type).capitalize()}", discord.Color.green())
    async for entry in channel.guild.audit_logs(limit=1, action=discord.AuditLogAction.channel_create):
        e.add_field(name="**Создал:**", value=f"{entry.user.mention}", inline=False)
    await send_log(channel.guild, e)

@bot.event
async def on_guild_channel_delete(channel):
    e = make_log_embed("Удаление канала", f"**{channel.name}**\nТип: {str(channel.type).capitalize()}", discord.Color.red())
    async for entry in channel.guild.audit_logs(limit=1, action=discord.AuditLogAction.channel_delete):
        e.add_field(name="**Удалил:**", value=f"{entry.user.mention}", inline=False)
    await send_log(channel.guild, e)

@bot.event
async def on_guild_channel_update(before, after):
    e = make_log_embed("Изменение канала", f"**Канал:** {after.mention}\n**Было:** {before.name}\n**Стало:** {after.name}", discord.Color.orange())
    async for entry in after.guild.audit_logs(limit=1, action=discord.AuditLogAction.channel_update):
        e.add_field(name="**Изменил:**", value=f"{entry.user.mention}", inline=False)
    await send_log(after.guild, e)

@bot.event
async def on_guild_role_create(role):
    e = make_log_embed("Создание роли", f"**{role.name}**\nЦвет: {role.color}\nID: {role.id}", discord.Color.green())
    async for entry in role.guild.audit_logs(limit=1, action=discord.AuditLogAction.role_create):
        e.add_field(name="**Создал:**", value=f"{entry.user.mention}", inline=False)
    await send_log(role.guild, e)

@bot.event
async def on_guild_role_delete(role):
    e = make_log_embed("Удаление роли", f"**{role.name}**\nЦвет: {role.color}\nID: {role.id}", discord.Color.red())
    async for entry in role.guild.audit_logs(limit=1, action=discord.AuditLogAction.role_delete):
        e.add_field(name="**Удалил:**", value=f"{entry.user.mention}", inline=False)
    await send_log(role.guild, e)

@bot.event
async def on_guild_role_update(before, after):
    e = make_log_embed("Изменение роли", f"**Роль:** {after.mention}\nID: {after.id}", discord.Color.orange())
    ch = []
    if before.name != after.name: ch.append(f"Название: `{before.name}` -> `{after.name}`")
    if before.color != after.color: ch.append(f"Цвет: `{before.color}` -> `{after.color}`")
    if before.hoist != after.hoist: ch.append(f"Отдельная: `{before.hoist}` -> `{after.hoist}`")
    if before.mentionable != after.mentionable: ch.append(f"Упоминаемая: `{before.mentionable}` -> `{after.mentionable}`")
    if before.permissions != after.permissions: ch.append("Права: изменены")
    if ch: e.description += "\n" + "\n".join(ch)
    async for entry in after.guild.audit_logs(limit=1, action=discord.AuditLogAction.role_update):
        e.add_field(name="**Изменил:**", value=f"{entry.user.mention}", inline=False)
    await send_log(after.guild, e)

@bot.event
async def on_member_update(before, after):
    if before.roles != after.roles:
        added = [r for r in after.roles if r not in before.roles and r != after.guild.default_role]
        removed = [r for r in before.roles if r not in after.roles and r != after.guild.default_role]
        if added or removed:
            e = make_log_embed("Изменение ролей", f"**Участник:** {after.mention} (`{after.id}`)", discord.Color.blue(), after)
            if added: e.add_field(name="**Добавлено:**", value=", ".join(r.mention for r in added), inline=False)
            if removed: e.add_field(name="**Убрано:**", value=", ".join(r.mention for r in removed), inline=False)
            async for entry in after.guild.audit_logs(limit=1, action=discord.AuditLogAction.member_role_update):
                if entry.target.id == after.id: e.add_field(name="**Изменил:**", value=f"{entry.user.mention}", inline=False)
            await send_log(after.guild, e)
    if before.premium_since != after.premium_since and after.premium_since:
        bci = get_setting("boost_channel_id")
        if bci and bci.isdigit():
            ch = after.guild.get_channel(int(bci))
            if ch:
                try:
                    t = BOOST_TEXT.replace("{user}", after.mention).replace("{name}", after.name).replace("{server}", after.guild.name)
                    await ch.send(embed=discord.Embed(description=t, color=discord.Color.pink()).set_footer(text=f"Fail Bot - {get_moscow_time().strftime('%d.%m.%Y %H:%M')} MSK"))
                    await send_log(after.guild, make_log_embed("Буст", f"{after.mention} забустил!", discord.Color.pink(), after))
                except: pass
    if before.timed_out_until != after.timed_out_until:
        if after.timed_out_until:
            e = make_log_embed("Мут", f"**Участник:** {after.mention}\n**До:** <t:{int(after.timed_out_until.timestamp())}:F>", discord.Color.dark_grey(), after)
            async for entry in after.guild.audit_logs(limit=1, action=discord.AuditLogAction.member_update):
                if entry.target.id == after.id: e.add_field(name="**Модератор:**", value=f"{entry.user.mention}", inline=False)
            await send_log(after.guild, e)
        elif before.timed_out_until and not after.timed_out_until:
            e = make_log_embed("Анмут", f"**Участник:** {after.mention}", discord.Color.green(), after)
            async for entry in after.guild.audit_logs(limit=1, action=discord.AuditLogAction.member_update):
                if entry.target.id == after.id: e.add_field(name="**Модератор:**", value=f"{entry.user.mention}", inline=False)
            await send_log(after.guild, e)

@bot.event
async def on_member_join(member):
    if not member.guild: return
    wci = get_setting("welcome_channel_id")
    if wci and wci.isdigit():
        ch = member.guild.get_channel(int(wci))
        if ch:
            try:
                t = WELCOME_TEXT.replace("{user}", member.mention).replace("{name}", member.name).replace("{server}", member.guild.name)
                await ch.send(embed=discord.Embed(description=t, color=discord.Color.green()))
            except: pass

message_cache = {}
FLOOD_LIMIT = 5; FLOOD_INTERVAL = 5

@bot.event
async def on_message(msg):
    if msg.author.bot or not msg.guild: return
    erid = get_setting("everyone_role_id")
    has_er = False
    if erid and erid.isdigit():
        r = msg.guild.get_role(int(erid))
        if r and r in msg.author.roles: has_er = True
    now = datetime.datetime.utcnow().timestamp(); uid = msg.author.id
    if uid not in message_cache: message_cache[uid] = []
    message_cache[uid] = [m for m in message_cache[uid] if now - m[0] < FLOOD_INTERVAL]
    message_cache[uid].append((now, msg.content))
    if len(message_cache[uid]) > FLOOD_LIMIT and not msg.author.guild_permissions.administrator:
        try: await msg.delete(); await msg.channel.send(f"{msg.author.mention} **Не флуди!**", delete_after=3)
        except: pass
        await send_log(msg.guild, make_log_embed("Флуд", f"{msg.author.mention}\n**Канал:** {msg.channel.mention}", discord.Color.red(), msg.author))
        return
    if msg.mention_everyone and is_night_time() and not has_er and not msg.author.guild_permissions.administrator:
        e = make_log_embed("Тег @everyone ночью", f"{msg.author.mention}\n**Канал:** {msg.channel.mention}", discord.Color.dark_purple(), msg.author)
        e.add_field(name="Действие:", value="Мут на 7 дней", inline=False)
        await send_log(msg.guild, e)
        try:
            await msg.delete()
            await msg.author.timeout(discord.utils.utcnow() + datetime.timedelta(days=7), reason="everyone ночью")
            try: await msg.channel.send(f"{msg.author.mention} **Мут на 7 дней**", delete_after=10)
            except: pass
        except Exception as ex:
            lc = await get_log_channel(msg.guild)
            if lc: await lc.send(f"Не удалось замутить: {ex}")
        return
    if has_ad_keywords(msg.content) and not msg.author.guild_permissions.administrator and not has_er:
        await send_log(msg.guild, make_log_embed("Реклама", f"{msg.author.mention}\n**Канал:** {msg.channel.mention}", discord.Color.red(), msg.author))
        try: await msg.delete(); await msg.channel.send(f"{msg.author.mention} **Реклама запрещена!**", delete_after=5)
        except: pass
    await bot.process_commands(msg)

# ===== КОМАНДЫ =====
@bot.tree.command(name="roleeveryone", description="Установить роль для @everyone")
async def roleeveryone(i):
    if not await check_access(i): await i.response.send_message("Нет доступа", ephemeral=True); return
    async def on_role(i2, rid):
        r = i2.guild.get_role(int(rid))
        if r: set_setting("everyone_role_id", rid); await i2.response.edit_message(embed=discord.Embed(title="Готово", description=f"{r.mention} может тегать @everyone", color=discord.Color.green()), view=None)
        else: await i2.response.send_message("Роль не найдена", ephemeral=True)
    await i.response.send_message(embed=discord.Embed(title="Выбор роли", color=discord.Color.blue()), view=RoleView(i.guild, "Выберите роль:", on_role), ephemeral=True)

@bot.tree.command(name="logchatset", description="Установить канал логов")
async def logchatset(i):
    if not await check_access(i): await i.response.send_message("Нет доступа", ephemeral=True); return
    async def on_ch(i2, cid):
        ch = i2.guild.get_channel(int(cid))
        if ch: set_setting("log_channel_id", cid); await i2.response.edit_message(embed=discord.Embed(title="Готово", description=f"Логи в {ch.mention}", color=discord.Color.green()), view=None)
        else: await i2.response.send_message("Канал не найден", ephemeral=True)
    await i.response.send_message(embed=discord.Embed(title="Выбор канала", color=discord.Color.blue()), view=ChannelView(i.guild, "Выберите канал:", on_ch), ephemeral=True)

@bot.tree.command(name="setrole", description="Назначить роль для команд")
async def setrole(i):
    if not await check_access(i): await i.response.send_message("Нет доступа", ephemeral=True); return
    async def on_role(i2, rid):
        r = i2.guild.get_role(int(rid))
        if r: add_allowed_role(int(rid)); await i2.response.edit_message(embed=discord.Embed(title="Готово", description=f"{r.mention} может использовать команды", color=discord.Color.green()), view=None)
        else: await i2.response.send_message("Роль не найдена", ephemeral=True)
    await i.response.send_message(embed=discord.Embed(title="Выбор роли", color=discord.Color.blue()), view=RoleView(i.guild, "Выберите роль:", on_role), ephemeral=True)

@bot.tree.command(name="setmsg", description="Создать embed с кнопками (админ)")
async def setmsg(i):
    oid = get_setting("owner_id")
    if not (i.user.guild_permissions.administrator or (oid and oid.isdigit() and i.user.id == int(oid))):
        await i.response.send_message("Только админ", ephemeral=True); return
    ck = f"setmsg_{i.user.id}"; now = time.time()
    last = CMD_COOLDOWNS.get(ck, 0)
    if now - last < 10: await i.response.send_message(f"Подождите {int(10-(now-last))} сек", ephemeral=True); return
    CMD_COOLDOWNS[ck] = now
    await i.response.send_modal(SetMsgModal())

@bot.tree.command(name="copy", description="Скопировать эмодзи (можно несколько через пробел)")
@app_commands.describe(emojis="Эмодзи через пробел (сколько хочешь)")
async def copy_emoji(i, emojis: str):
    if not await check_access(i): await i.response.send_message("Нет доступа", ephemeral=True); return
    await i.response.defer(ephemeral=True)
    raw = emojis.strip()
    parts = raw.split()
    parsed_emojis = []
    for part in parts:
        try:
            p = discord.PartialEmoji.from_str(part)
            if p and p.id:
                parsed_emojis.append(p)
        except:
            pass
    if not parsed_emojis:
        await i.followup.send("Не найдено ни одного кастомного эмодзи. Отправляй эмодзи с других серверов.", ephemeral=True); return
    total = len(parsed_emojis)
    success = 0
    failed = 0
    results = []
    log_lines = []
    async with aiohttp.ClientSession() as ss:
        for p in parsed_emojis:
            ext = "gif" if p.animated else "png"
            url = "https://cdn.discordapp.com/emojis/{}.{}".format(p.id, ext)
            try:
                async with ss.get(url) as resp:
                    if resp.status != 200:
                        results.append(":x: `{}` - не загружен".format(p.name or p.id))
                        failed += 1
                        continue
                    data = await resp.read()
                name = (p.name or "emoji_{}".format(p.id))[:32]
                created = await i.guild.create_custom_emoji(name=name, image=data, reason="Скопировано {}".format(i.user))
                results.append(":white_check_mark: {} `:{}:`".format(created, name))
                log_lines.append("{} `:{}:`".format(created, name))
                success += 1
            except discord.Forbidden:
                results.append(":x: `{}` - нет прав".format(p.name or p.id))
                failed += 1
            except discord.HTTPException as e:
                txt = str(e).lower()
                if "emojis" in txt and "max" in txt:
                    results.append(":x: `{}` - лимит эмодзи".format(p.name or p.id))
                else:
                    results.append(":x: `{}` - ошибка".format(p.name or p.id))
                failed += 1
            except:
                results.append(":x: `{}` - ошибка".format(p.name or p.id))
                failed += 1
    desc = "**Успешно:** {}/{}".format(success, total) + "\n**Не удалось:** {}".format(failed)
    embed = discord.Embed(
        title="Копирование эмодзи завершено",
        description=desc,
        color=discord.Color.green() if success > 0 else discord.Color.red()
    )
    result_text = "\n".join(results[:15])
    if len(results) > 15:
        result_text += "\n...и ещё {}".format(len(results)-15)
    embed.add_field(name="Результаты:", value=result_text, inline=False)
    await i.followup.send(embed=embed, ephemeral=True)
    if log_lines:
        log_text = "\n".join(log_lines[:5])
        if len(log_lines) > 5:
            log_text += "\n...и ещё {}".format(len(log_lines)-5)
        log_desc = "{}\n**Кто:** {}".format(log_text, i.user.mention)
        await send_log(i.guild, make_log_embed("Копирование эмодзи ({}/{})".format(success, total), log_desc, discord.Color.green(), i.user))

@bot.tree.command(name="setroles", description="Отправить меню выбора ролей с кнопками")
async def setroles(i):
    if not await check_access(i): await i.response.send_message("Нет доступа", ephemeral=True); return
    await i.response.send_message("\u2705 Сообщение с ролями отправляется...", ephemeral=True)
    
    # Чтобы получить темно-серый задний фон без видимой левой цветной полоски,
    # мы используем специальный "невидимый" цвет Discord (0x2b2d31).
    INVISIBLE_BG_COLOR = 0x2b2d31
    
    # 1. Секция Уведомлений
    desc1 = "Получи интересующие тебя **роли уведомлений**, которые ты бы не хотел пропускать. Для этого **выбери роли** из списка ниже."
    embed1 = discord.Embed(description=desc1, color=INVISIBLE_BG_COLOR)
    embed1.set_image(url=GIF_NOTIF)
    await i.channel.send(embed=embed1, view=RoleMenuView1())
    
    # 2. Секция Увлечений
    desc2 = "Получи интересующие тебя **роли увлечений**, чтобы получать уведомления на интересующие тебя **ивенты**. Для этого **выбери роли** из списка ниже."
    embed2 = discord.Embed(description=desc2, color=INVISIBLE_BG_COLOR)
    embed2.set_image(url=GIF_HOBBY)
    await i.channel.send(embed=embed2, view=RoleMenuView2())
    
    # 3. Секция Пола
    desc3 = "Выбери роль **пола**, чтобы участники сервера могли лучше понимать, как к тебе обращаться."
    embed3 = discord.Embed(description=desc3, color=INVISIBLE_BG_COLOR)
    embed3.set_image(url=GIF_GENDER)
    await i.channel.send(embed=embed3, view=RoleMenuView3())

@bot.tree.command(name="setboost", description="Выбрать канал для бустов")
async def setboost(i):
    if not await check_access(i): await i.response.send_message("Нет доступа", ephemeral=True); return
    async def on_ch(i2, cid):
        ch = i2.guild.get_channel(int(cid))
        if ch: set_setting("boost_channel_id", cid)
        await i2.response.edit_message(embed=discord.Embed(title="Готово", description=f"Канал бустов: {ch.mention}\n\nТекст уже вшит в бота, менять не нужно!", color=discord.Color.green()), view=None)
    await i.response.send_message(embed=discord.Embed(title="Выбор канала для бустов", color=discord.Color.blue()), view=ChannelView(i.guild, "Выберите канал:", on_ch), ephemeral=True)

@bot.tree.command(name="setwelcome", description="Выбрать канал для приветствий")
async def setwelcome(i):
    if not await check_access(i): await i.response.send_message("Нет доступа", ephemeral=True); return
    async def on_ch(i2, cid):
        ch = i2.guild.get_channel(int(cid))
        if ch: set_setting("welcome_channel_id", cid)
        await i2.response.edit_message(embed=discord.Embed(title="Готово", description=f"Канал приветствий: {ch.mention}\n\nТекст уже вшит в бота, менять не нужно!", color=discord.Color.green()), view=None)
    await i.response.send_message(embed=discord.Embed(title="Выбор канала приветствий", color=discord.Color.blue()), view=ChannelView(i.guild, "Выберите канал:", on_ch), ephemeral=True)

@bot.tree.command(name="exitbot", description="Выйти с сервера (владелец)")
async def exitbot(i):
    oid = get_setting("owner_id")
    if not oid or not oid.isdigit() or i.user.id != int(oid): await i.response.send_message("Только владелец", ephemeral=True); return
    gn, gid = i.guild.name, i.guild.id
    await i.response.send_message("Бот выходит...", ephemeral=True)
    await send_log(i.guild, make_log_embed("Выход", f"**Инициатор:** {i.user.mention}\n**Сервер:** {gn} ({gid})", discord.Color.red(), i.user))
    await i.guild.leave()

@bot.tree.command(name="shutdown", description="Выключить бота (владелец)")
async def shutdown(i):
    oid = get_setting("owner_id")
    if not oid or not oid.isdigit() or i.user.id != int(oid): await i.response.send_message("Только владелец", ephemeral=True); return
    await i.response.send_message("Бот выключается...", ephemeral=True)
    await send_log(i.guild, make_log_embed("Выключение", f"**Инициатор:** {i.user.mention}", discord.Color.red(), i.user))
    await bot.close()

@bot.tree.command(name="setserver", description="Добавить сервер в whitelist (владелец)")
async def setserver(i):
    oid = get_setting("owner_id")
    if not oid or not oid.isdigit() or i.user.id != int(oid): await i.response.send_message("Только владелец", ephemeral=True); return
    add_allowed_guild(i.guild.id)
    await i.response.send_message(embed=discord.Embed(title="Сервер добавлен", description=f"{i.guild.name} ({i.guild.id})", color=discord.Color.green()), ephemeral=True)

@bot.tree.command(name="setowner", description="Установить владельца бота (первый запуск)")
async def setowner(i, user: discord.User):
    if not i.user.guild_permissions.administrator: await i.response.send_message("Нет доступа", ephemeral=True); return
    current = get_setting("owner_id")
    if current and current.isdigit() and i.user.id != int(current):
        await i.response.send_message("Владелец уже установлен", ephemeral=True); return
    set_setting("owner_id", str(user.id))
    await i.response.send_message(embed=discord.Embed(title="Владелец установлен", description=f"{user.mention} теперь владелец бота", color=discord.Color.green()), ephemeral=True)

if __name__ == "__main__":
    if not TOKEN:
        print("Ошибка: Токен не найден!")
        exit(1)
    bot.run(TOKEN)