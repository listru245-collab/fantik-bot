"""
 RUSSIANCRAFT BOT v2.9.0
 pip install vk_api
"""

import vk_api
from vk_api.bot_longpoll import VkBotLongPoll, VkBotEventType
from vk_api.keyboard import VkKeyboard, VkKeyboardColor
import sqlite3, threading, time, re, random, traceback, json, hashlib, os, logging

logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(levelname)s: %(message)s')
logger = logging.getLogger("RC")

VK_TOKEN = os.environ.get("VK_TOKEN", "")
GROUP_ID = int(os.environ.get("VK_GROUP_ID", "237161820"))
GLOBAL_ADMINS = [1063123986]
SUPPORT_PEER = 2000000002

if not VK_TOKEN:
    config_path = "config.json"
    if os.path.exists(config_path):
        with open(config_path, "r") as f:
            cfg = json.load(f)
            VK_TOKEN = cfg.get("token", "")
            GROUP_ID = cfg.get("group_id", GROUP_ID)
            GLOBAL_ADMINS = cfg.get("global_admins", GLOBAL_ADMINS)
    else:
        logger.error("Токен не найден.")
        exit(1)

ALLOWED_SETTINGS = {
    "antispam", "antimat", "antilink", "antiflood",
    "welcome_enabled", "welcome_text", "bye_enabled", "bye_text",
    "slowmode", "nightmode", "night_start", "night_end",
    "log_peer", "captcha", "max_warns", "connected", "support_mode", "chat_closed"
}


class Database:
    def __init__(self, db_path="russiancraft.db"):
        self.lock = threading.RLock()
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.cursor = self.conn.cursor()
        self._create_tables()
        self._migrate_tables()

    def _create_tables(self):
        with self.lock:
            self.cursor.execute("""CREATE TABLE IF NOT EXISTS roles (
                id INTEGER PRIMARY KEY AUTOINCREMENT, peer_id INTEGER NOT NULL,
                role_name TEXT NOT NULL, priority INTEGER NOT NULL DEFAULT 1,
                emoji TEXT DEFAULT '', UNIQUE(peer_id, role_name), UNIQUE(peer_id, priority))""")
            self.cursor.execute("""CREATE TABLE IF NOT EXISTS user_roles (
                id INTEGER PRIMARY KEY AUTOINCREMENT, peer_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL, role_id INTEGER NOT NULL,
                UNIQUE(peer_id, user_id), FOREIGN KEY(role_id) REFERENCES roles(id) ON DELETE CASCADE)""")
            self.cursor.execute("""CREATE TABLE IF NOT EXISTS bans (
                id INTEGER PRIMARY KEY AUTOINCREMENT, peer_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL, banned_by INTEGER NOT NULL,
                reason TEXT DEFAULT '', ban_until REAL DEFAULT 0,
                created_at REAL DEFAULT 0, UNIQUE(peer_id, user_id))""")
            self.cursor.execute("""CREATE TABLE IF NOT EXISTS mutes (
                id INTEGER PRIMARY KEY AUTOINCREMENT, peer_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL, muted_by INTEGER NOT NULL,
                reason TEXT DEFAULT '', mute_until REAL DEFAULT 0,
                created_at REAL DEFAULT 0, UNIQUE(peer_id, user_id))""")
            self.cursor.execute("""CREATE TABLE IF NOT EXISTS cmd_permissions (
                id INTEGER PRIMARY KEY AUTOINCREMENT, peer_id INTEGER NOT NULL,
                command TEXT NOT NULL, min_priority INTEGER NOT NULL DEFAULT 100,
                UNIQUE(peer_id, command))""")
            self.cursor.execute("""CREATE TABLE IF NOT EXISTS chat_owners (
                peer_id INTEGER PRIMARY KEY, owner_id INTEGER NOT NULL)""")
            self.cursor.execute("""CREATE TABLE IF NOT EXISTS blacklist (
                id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
                peer_id INTEGER NOT NULL, bl_type TEXT NOT NULL,
                added_by INTEGER NOT NULL, reason TEXT DEFAULT '',
                created_at REAL DEFAULT 0)""")
            self.cursor.execute("""CREATE TABLE IF NOT EXISTS viglist (
                id INTEGER PRIMARY KEY AUTOINCREMENT, peer_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL, issued_by INTEGER NOT NULL,
                vig_type TEXT NOT NULL, reason TEXT DEFAULT '',
                created_at REAL DEFAULT 0)""")
            self.cursor.execute("""CREATE TABLE IF NOT EXISTS msg_count (
                peer_id INTEGER NOT NULL, user_id INTEGER NOT NULL,
                count INTEGER DEFAULT 0, PRIMARY KEY(peer_id, user_id))""")
            self.cursor.execute("""CREATE TABLE IF NOT EXISTS chat_settings (
                peer_id INTEGER PRIMARY KEY, antispam INTEGER DEFAULT 0,
                antimat INTEGER DEFAULT 0, antilink INTEGER DEFAULT 0,
                antiflood INTEGER DEFAULT 0, welcome_enabled INTEGER DEFAULT 0,
                welcome_text TEXT DEFAULT '', bye_enabled INTEGER DEFAULT 0,
                bye_text TEXT DEFAULT '', slowmode INTEGER DEFAULT 0,
                nightmode INTEGER DEFAULT 0, night_start INTEGER DEFAULT 0,
                night_end INTEGER DEFAULT 8, log_peer INTEGER DEFAULT 0,
                captcha INTEGER DEFAULT 0, max_warns INTEGER DEFAULT 3,
                connected INTEGER DEFAULT 0, support_mode INTEGER DEFAULT 0,
                chat_closed INTEGER DEFAULT 0)""")
            self.cursor.execute("""CREATE TABLE IF NOT EXISTS chat_pool (
                id INTEGER PRIMARY KEY AUTOINCREMENT, pool_owner INTEGER NOT NULL,
                peer_id INTEGER NOT NULL, UNIQUE(peer_id))""")
            self.cursor.execute("""CREATE TABLE IF NOT EXISTS import_codes (
                id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT NOT NULL UNIQUE,
                peer_id INTEGER NOT NULL, created_at REAL DEFAULT 0)""")
            self.cursor.execute("""CREATE TABLE IF NOT EXISTS global_bans (
                id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL UNIQUE,
                banned_by INTEGER NOT NULL, reason TEXT DEFAULT '',
                ban_until REAL DEFAULT 0, created_at REAL DEFAULT 0)""")
            self.cursor.execute("""CREATE TABLE IF NOT EXISTS global_mutes (
                id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL UNIQUE,
                muted_by INTEGER NOT NULL, reason TEXT DEFAULT '',
                mute_until REAL DEFAULT 0, created_at REAL DEFAULT 0)""")
            self.cursor.execute("""CREATE TABLE IF NOT EXISTS global_vigs (
                id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
                issued_by INTEGER NOT NULL, vig_type TEXT NOT NULL,
                reason TEXT DEFAULT '', created_at REAL DEFAULT 0)""")
            self.cursor.execute("""CREATE TABLE IF NOT EXISTS support_tickets (
                id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
                problem_text TEXT NOT NULL, problem_type TEXT NOT NULL,
                status TEXT DEFAULT 'open', created_at REAL DEFAULT 0,
                closed_at REAL DEFAULT 0, closed_by INTEGER DEFAULT 0)""")
            self.cursor.execute("""CREATE TABLE IF NOT EXISTS role_aliases (
                peer_id INTEGER NOT NULL, priority INTEGER NOT NULL,
                alias_name TEXT NOT NULL, alias_emoji TEXT DEFAULT '',
                PRIMARY KEY(peer_id, priority))""")
            self.cursor.execute("""CREATE TABLE IF NOT EXISTS chat_notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                peer_id INTEGER NOT NULL, note_name TEXT NOT NULL,
                note_text TEXT DEFAULT '', attachments TEXT DEFAULT '',
                created_by INTEGER NOT NULL, created_at REAL DEFAULT 0,
                UNIQUE(peer_id, note_name))""")
            self.cursor.execute("""CREATE TABLE IF NOT EXISTS cmd_aliases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                peer_id INTEGER NOT NULL,
                original_cmd TEXT NOT NULL,
                alias TEXT NOT NULL,
                UNIQUE(peer_id, alias))""")
            self.cursor.execute("""CREATE TABLE IF NOT EXISTS global_cmd_aliases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                original_cmd TEXT NOT NULL,
                alias TEXT NOT NULL,
                UNIQUE(alias))""")
            self.conn.commit()

    def _migrate_tables(self):
        with self.lock:
            for sql in [
                "ALTER TABLE blacklist ADD COLUMN reason TEXT DEFAULT ''",
                "ALTER TABLE roles ADD COLUMN emoji TEXT DEFAULT ''",
                "ALTER TABLE chat_settings ADD COLUMN support_mode INTEGER DEFAULT 0",
                "ALTER TABLE chat_settings ADD COLUMN chat_closed INTEGER DEFAULT 0"
            ]:
                try:
                    self.cursor.execute(sql)
                    self.conn.commit()
                except sqlite3.OperationalError:
                    pass

    def set_chat_owner(self, peer_id, owner_id):
        with self.lock:
            self.cursor.execute("INSERT OR REPLACE INTO chat_owners (peer_id, owner_id) VALUES (?, ?)", (peer_id, owner_id))
            self.conn.commit()

    def get_chat_owner(self, peer_id):
        with self.lock:
            self.cursor.execute("SELECT owner_id FROM chat_owners WHERE peer_id = ?", (peer_id,))
            r = self.cursor.fetchone()
            return r["owner_id"] if r else None

    def _get_chat_owner_nolock(self, peer_id):
        self.cursor.execute("SELECT owner_id FROM chat_owners WHERE peer_id = ?", (peer_id,))
        r = self.cursor.fetchone()
        return r["owner_id"] if r else None

    def create_role(self, peer_id, role_name, priority, emoji=""):
        with self.lock:
            try:
                self.cursor.execute("INSERT INTO roles (peer_id, role_name, priority, emoji) VALUES (?, ?, ?, ?)", (peer_id, role_name, priority, emoji))
                self.conn.commit()
                return True, "OK"
            except sqlite3.IntegrityError:
                return False, "Роль с таким именем или приоритетом уже существует."

    def delete_role(self, peer_id, priority):
        with self.lock:
            if priority >= 100:
                return False, "Нельзя удалить роль владельца."
            self.cursor.execute("SELECT id FROM roles WHERE peer_id = ? AND priority = ?", (peer_id, priority))
            r = self.cursor.fetchone()
            if not r:
                return False, "Роль не найдена."
            self.cursor.execute("DELETE FROM user_roles WHERE role_id = ?", (r["id"],))
            self.cursor.execute("DELETE FROM roles WHERE id = ?", (r["id"],))
            self.conn.commit()
            return True, "OK"

    def get_roles(self, peer_id):
        with self.lock:
            self.cursor.execute("SELECT * FROM roles WHERE peer_id = ? ORDER BY priority DESC", (peer_id,))
            return self.cursor.fetchall()

    def get_role_by_priority(self, peer_id, priority):
        with self.lock:
            self.cursor.execute("SELECT * FROM roles WHERE peer_id = ? AND priority = ?", (peer_id, priority))
            return self.cursor.fetchone()

    def assign_role(self, peer_id, user_id, priority):
        with self.lock:
            self.cursor.execute("SELECT * FROM roles WHERE peer_id = ? AND priority = ?", (peer_id, priority))
            r = self.cursor.fetchone()
            if not r:
                return False, "Роль не существует."
            self.cursor.execute("INSERT OR REPLACE INTO user_roles (peer_id, user_id, role_id) VALUES (?, ?, ?)", (peer_id, user_id, r["id"]))
            self.conn.commit()
            return True, dict(r)

    def remove_role(self, peer_id, user_id):
        with self.lock:
            self.cursor.execute("DELETE FROM user_roles WHERE peer_id = ? AND user_id = ?", (peer_id, user_id))
            if self.cursor.rowcount == 0:
                return False, "У пользователя нет роли."
            self.conn.commit()
            return True, "OK"

    def get_user_role(self, peer_id, user_id):
        with self.lock:
            self.cursor.execute("SELECT r.role_name, r.priority, r.emoji FROM user_roles ur JOIN roles r ON ur.role_id = r.id WHERE ur.peer_id = ? AND ur.user_id = ?", (peer_id, user_id))
            row = self.cursor.fetchone()
            return dict(row) if row else None

    def get_chat_staff(self, peer_id):
        with self.lock:
            self.cursor.execute("SELECT ur.user_id, r.role_name, r.priority, r.emoji FROM user_roles ur JOIN roles r ON ur.role_id = r.id WHERE ur.peer_id = ? ORDER BY r.priority DESC", (peer_id,))
            return [dict(row) for row in self.cursor.fetchall()]

    def get_user_priority(self, peer_id, user_id):
        with self.lock:
            if user_id in GLOBAL_ADMINS:
                return 1000
            o = self._get_chat_owner_nolock(peer_id)
            if o and o == user_id:
                return 100
            self.cursor.execute("SELECT r.priority FROM user_roles ur JOIN roles r ON ur.role_id = r.id WHERE ur.peer_id = ? AND ur.user_id = ?", (peer_id, user_id))
            r = self.cursor.fetchone()
            return r["priority"] if r else 0

    def get_user_priority_pool(self, peer_id, user_id):
        with self.lock:
            if user_id in GLOBAL_ADMINS:
                return 1000
            o = self._get_chat_owner_nolock(peer_id)
            if o and o == user_id:
                return 100
            self.cursor.execute("SELECT r.priority FROM user_roles ur JOIN roles r ON ur.role_id = r.id WHERE ur.peer_id = ? AND ur.user_id = ?", (peer_id, user_id))
            r = self.cursor.fetchone()
            p = r["priority"] if r else 0
            self.cursor.execute("SELECT pool_owner FROM chat_pool WHERE peer_id = ?", (peer_id,))
            pool_row = self.cursor.fetchone()
            if pool_row:
                owner = pool_row["pool_owner"]
                self.cursor.execute("SELECT peer_id FROM chat_pool WHERE pool_owner = ?", (owner,))
                peers = [x["peer_id"] for x in self.cursor.fetchall()]
                peers.append(owner)
            else:
                self.cursor.execute("SELECT peer_id FROM chat_pool WHERE pool_owner = ?", (peer_id,))
                pp = self.cursor.fetchall()
                peers = [x["peer_id"] for x in pp] + [peer_id] if pp else []
            for pp in peers:
                if pp != peer_id:
                    self.cursor.execute("SELECT r.priority FROM user_roles ur JOIN roles r ON ur.role_id = r.id WHERE ur.peer_id = ? AND ur.user_id = ?", (pp, user_id))
                    rr = self.cursor.fetchone()
                    if rr and rr["priority"] > p:
                        p = rr["priority"]
            return p

    def ban_user(self, peer_id, user_id, banned_by, reason, duration):
        with self.lock:
            if user_id in GLOBAL_ADMINS:
                return False
            bu = 0 if duration == 0 else time.time() + duration
            self.cursor.execute("INSERT OR REPLACE INTO bans (peer_id, user_id, banned_by, reason, ban_until, created_at) VALUES (?, ?, ?, ?, ?, ?)", (peer_id, user_id, banned_by, reason, bu, time.time()))
            self.conn.commit()
            return True

    def unban_user(self, peer_id, user_id):
        with self.lock:
            self.cursor.execute("DELETE FROM bans WHERE peer_id = ? AND user_id = ?", (peer_id, user_id))
            r = self.cursor.rowcount > 0
            self.conn.commit()
            return r

    def is_banned(self, peer_id, user_id):
        with self.lock:
            if user_id in GLOBAL_ADMINS:
                return False
            self.cursor.execute("SELECT * FROM bans WHERE peer_id = ? AND user_id = ?", (peer_id, user_id))
            r = self.cursor.fetchone()
            if not r:
                return False
            if r["ban_until"] == 0:
                return True
            if time.time() > r["ban_until"]:
                self.cursor.execute("DELETE FROM bans WHERE id = ?", (r["id"],))
                self.conn.commit()
                return False
            return True

    def get_ban_info(self, peer_id, user_id):
        with self.lock:
            self.cursor.execute("SELECT * FROM bans WHERE peer_id = ? AND user_id = ?", (peer_id, user_id))
            r = self.cursor.fetchone()
            return dict(r) if r else None

    def get_ban_list(self, peer_id):
        with self.lock:
            now = time.time()
            self.cursor.execute("DELETE FROM bans WHERE peer_id = ? AND ban_until > 0 AND ban_until < ?", (peer_id, now))
            self.conn.commit()
            self.cursor.execute("SELECT * FROM bans WHERE peer_id = ?", (peer_id,))
            rows = self.cursor.fetchall()
            return [dict(r) for r in rows]

    def mute_user(self, peer_id, user_id, muted_by, reason, duration):
        with self.lock:
            if user_id in GLOBAL_ADMINS:
                return False
            mu = 0 if duration == 0 else time.time() + duration
            self.cursor.execute("INSERT OR REPLACE INTO mutes (peer_id, user_id, muted_by, reason, mute_until, created_at) VALUES (?, ?, ?, ?, ?, ?)", (peer_id, user_id, muted_by, reason, mu, time.time()))
            self.conn.commit()
            return True

    def unmute_user(self, peer_id, user_id):
        with self.lock:
            self.cursor.execute("DELETE FROM mutes WHERE peer_id = ? AND user_id = ?", (peer_id, user_id))
            r = self.cursor.rowcount > 0
            self.conn.commit()
            return r

    def is_muted(self, peer_id, user_id):
        with self.lock:
            if user_id in GLOBAL_ADMINS:
                return False
            self.cursor.execute("SELECT * FROM mutes WHERE peer_id = ? AND user_id = ?", (peer_id, user_id))
            r = self.cursor.fetchone()
            if not r:
                return False
            if r["mute_until"] == 0:
                return True
            if time.time() > r["mute_until"]:
                self.cursor.execute("DELETE FROM mutes WHERE id = ?", (r["id"],))
                self.conn.commit()
                return False
            return True

    def get_mute_info(self, peer_id, user_id):
        with self.lock:
            self.cursor.execute("SELECT * FROM mutes WHERE peer_id = ? AND user_id = ?", (peer_id, user_id))
            r = self.cursor.fetchone()
            return dict(r) if r else None

    def get_mute_list(self, peer_id):
        with self.lock:
            now = time.time()
            self.cursor.execute("DELETE FROM mutes WHERE peer_id = ? AND mute_until > 0 AND mute_until < ?", (peer_id, now))
            self.conn.commit()
            self.cursor.execute("SELECT * FROM mutes WHERE peer_id = ?", (peer_id,))
            rows = self.cursor.fetchall()
            return [dict(r) for r in rows]

    def set_cmd_permission(self, peer_id, command, min_priority):
        with self.lock:
            self.cursor.execute("INSERT OR REPLACE INTO cmd_permissions (peer_id, command, min_priority) VALUES (?, ?, ?)", (peer_id, command, min_priority))
            self.conn.commit()

    def get_cmd_permission(self, peer_id, command):
        with self.lock:
            self.cursor.execute("SELECT min_priority FROM cmd_permissions WHERE peer_id = ? AND command = ?", (peer_id, command))
            r = self.cursor.fetchone()
            return r["min_priority"] if r else None

    def get_all_cmd_permissions(self, peer_id):
        with self.lock:
            self.cursor.execute("SELECT command, min_priority FROM cmd_permissions WHERE peer_id = ? ORDER BY command", (peer_id,))
            return [dict(r) for r in self.cursor.fetchall()]

    def add_to_blacklist(self, user_id, peer_id, bl_type, added_by, reason):
        with self.lock:
            if user_id in GLOBAL_ADMINS:
                return False
            self.cursor.execute("INSERT INTO blacklist (user_id, peer_id, bl_type, added_by, reason, created_at) VALUES (?, ?, ?, ?, ?, ?)", (user_id, peer_id, bl_type, added_by, reason, time.time()))
            self.conn.commit()
            return True

    def remove_from_blacklist(self, user_id, peer_id, bl_type=None):
        with self.lock:
            if bl_type:
                self.cursor.execute("DELETE FROM blacklist WHERE user_id = ? AND peer_id = ? AND bl_type = ?", (user_id, peer_id, bl_type))
            else:
                self.cursor.execute("DELETE FROM blacklist WHERE user_id = ? AND peer_id = ?", (user_id, peer_id))
            r = self.cursor.rowcount > 0
            self.conn.commit()
            return r

    def remove_from_blacklist_global(self, user_id):
        with self.lock:
            self.cursor.execute("DELETE FROM blacklist WHERE user_id = ?", (user_id,))
            r = self.cursor.rowcount > 0
            self.conn.commit()
            return r

    def is_blacklisted_in_chat(self, user_id, peer_id):
        with self.lock:
            if user_id in GLOBAL_ADMINS:
                return []
            self.cursor.execute("SELECT * FROM blacklist WHERE user_id = ? AND (peer_id = ? OR bl_type IN ('full_project', 'full_strict'))", (user_id, peer_id))
            return [dict(r) for r in self.cursor.fetchall()]

    def get_blacklist_global(self):
        with self.lock:
            self.cursor.execute("SELECT * FROM blacklist")
            return [dict(r) for r in self.cursor.fetchall()]

    def get_user_blacklist_entries(self, user_id, peer_id):
        with self.lock:
            self.cursor.execute("SELECT * FROM blacklist WHERE user_id = ? AND (peer_id = ? OR bl_type IN ('full_project', 'full_strict'))", (user_id, peer_id))
            return [dict(r) for r in self.cursor.fetchall()]

    def get_all_chat_peers(self):
        with self.lock:
            self.cursor.execute("SELECT peer_id FROM chat_owners")
            return [r["peer_id"] for r in self.cursor.fetchall()]

    def add_vig(self, peer_id, user_id, issued_by, vig_type, reason):
        with self.lock:
            if user_id in GLOBAL_ADMINS:
                return False
            self.cursor.execute("INSERT INTO viglist (peer_id, user_id, issued_by, vig_type, reason, created_at) VALUES (?, ?, ?, ?, ?, ?)", (peer_id, user_id, issued_by, vig_type, reason, time.time()))
            self.conn.commit()
            return True

    def remove_vig_by_id(self, vig_id):
        with self.lock:
            self.cursor.execute("DELETE FROM viglist WHERE id = ?", (vig_id,))
            r = self.cursor.rowcount > 0
            self.conn.commit()
            return r

    def remove_vigs(self, peer_id, user_id):
        with self.lock:
            self.cursor.execute("DELETE FROM viglist WHERE peer_id = ? AND user_id = ?", (peer_id, user_id))
            r = self.cursor.rowcount > 0
            self.conn.commit()
            return r

    def get_vigs(self, peer_id, user_id=None):
        with self.lock:
            if user_id:
                self.cursor.execute("SELECT * FROM viglist WHERE peer_id = ? AND user_id = ? ORDER BY created_at DESC", (peer_id, user_id))
            else:
                self.cursor.execute("SELECT * FROM viglist WHERE peer_id = ? ORDER BY created_at DESC", (peer_id,))
            return [dict(r) for r in self.cursor.fetchall()]

    def get_vig_by_id(self, vig_id):
        with self.lock:
            self.cursor.execute("SELECT * FROM viglist WHERE id = ?", (vig_id,))
            r = self.cursor.fetchone()
            return dict(r) if r else None

    def get_vig_issuer_max_priority(self, peer_id, user_id):
        with self.lock:
            self.cursor.execute("SELECT issued_by FROM viglist WHERE peer_id = ? AND user_id = ?", (peer_id, user_id))
            rows = self.cursor.fetchall()
            if not rows:
                return 0
            mx = 0
            for row in rows:
                iid = row["issued_by"]
                if iid in GLOBAL_ADMINS:
                    return 1000
                o = self._get_chat_owner_nolock(peer_id)
                if o and o == iid:
                    p = 100
                else:
                    self.cursor.execute("SELECT r.priority FROM user_roles ur JOIN roles r ON ur.role_id = r.id WHERE ur.peer_id = ? AND ur.user_id = ?", (peer_id, iid))
                    rr = self.cursor.fetchone()
                    p = rr["priority"] if rr else 0
                if p > mx:
                    mx = p
            return mx

    def increment_msg(self, peer_id, user_id):
        with self.lock:
            self.cursor.execute("INSERT INTO msg_count (peer_id, user_id, count) VALUES (?, ?, 1) ON CONFLICT(peer_id, user_id) DO UPDATE SET count = count + 1", (peer_id, user_id))
            self.conn.commit()

    def get_top_msg(self, peer_id, limit=10):
        with self.lock:
            self.cursor.execute("SELECT user_id, count FROM msg_count WHERE peer_id = ? ORDER BY count DESC LIMIT ?", (peer_id, limit))
            return [dict(r) for r in self.cursor.fetchall()]

    def get_settings(self, peer_id):
        with self.lock:
            self.cursor.execute("SELECT * FROM chat_settings WHERE peer_id = ?", (peer_id,))
            r = self.cursor.fetchone()
            if not r:
                self.cursor.execute("INSERT INTO chat_settings (peer_id) VALUES (?)", (peer_id,))
                self.conn.commit()
                self.cursor.execute("SELECT * FROM chat_settings WHERE peer_id = ?", (peer_id,))
                r = self.cursor.fetchone()
            return dict(r)

    def update_setting(self, peer_id, key, value):
        if key not in ALLOWED_SETTINGS:
            return
        with self.lock:
            self.cursor.execute("INSERT OR IGNORE INTO chat_settings (peer_id) VALUES (?)", (peer_id,))
            self.cursor.execute(f"UPDATE chat_settings SET {key} = ? WHERE peer_id = ?", (value, peer_id))
            self.conn.commit()

    def connect_to_pool(self, peer_id, owner_peer):
        with self.lock:
            try:
                self.cursor.execute("INSERT OR REPLACE INTO chat_pool (pool_owner, peer_id) VALUES (?, ?)", (owner_peer, peer_id))
                self.conn.commit()
                return True
            except:
                return False

    def disconnect_from_pool(self, peer_id):
        with self.lock:
            self.cursor.execute("DELETE FROM chat_pool WHERE peer_id = ?", (peer_id,))
            self.conn.commit()
            return self.cursor.rowcount > 0

    def get_pool_peers(self, peer_id):
        with self.lock:
            self.cursor.execute("SELECT pool_owner FROM chat_pool WHERE peer_id = ?", (peer_id,))
            r = self.cursor.fetchone()
            if not r:
                self.cursor.execute("SELECT peer_id FROM chat_pool WHERE pool_owner = ?", (peer_id,))
                peers = [x["peer_id"] for x in self.cursor.fetchall()]
                return peers + [peer_id] if peers else []
            owner = r["pool_owner"]
            self.cursor.execute("SELECT peer_id FROM chat_pool WHERE pool_owner = ?", (owner,))
            peers = [x["peer_id"] for x in self.cursor.fetchall()]
            peers.append(owner)
            return peers

    def is_connected(self, peer_id):
        with self.lock:
            self.cursor.execute("SELECT * FROM chat_pool WHERE peer_id = ? OR pool_owner = ?", (peer_id, peer_id))
            return self.cursor.fetchone() is not None

    def create_import_code(self, peer_id):
        with self.lock:
            code = hashlib.md5(f"{peer_id}{time.time()}{random.randint(0,999999)}".encode()).hexdigest()[:12].upper()
            self.cursor.execute("DELETE FROM import_codes WHERE peer_id = ?", (peer_id,))
            self.cursor.execute("INSERT INTO import_codes (code, peer_id, created_at) VALUES (?, ?, ?)", (code, peer_id, time.time()))
            self.conn.commit()
            return code

    def get_import_source(self, code):
        with self.lock:
            self.cursor.execute("SELECT * FROM import_codes WHERE code = ?", (code,))
            r = self.cursor.fetchone()
            if not r:
                return None
            if time.time() - r["created_at"] > 600:
                self.cursor.execute("DELETE FROM import_codes WHERE code = ?", (code,))
                self.conn.commit()
                return None
            return r["peer_id"]

    def import_settings(self, from_peer, to_peer):
        with self.lock:
            self.cursor.execute("SELECT * FROM chat_settings WHERE peer_id = ?", (from_peer,))
            s = self.cursor.fetchone()
            if not s:
                return False
            sd = dict(s)
            del sd["peer_id"]
            safe_sd = {k: v for k, v in sd.items() if k in ALLOWED_SETTINGS}
            if not safe_sd:
                return False
            keys = ",".join(safe_sd.keys())
            ph = ",".join(["?" for _ in safe_sd])
            vals = list(safe_sd.values())
            self.cursor.execute(f"INSERT OR REPLACE INTO chat_settings (peer_id, {keys}) VALUES (?, {ph})", [to_peer] + vals)
            self.cursor.execute("DELETE FROM roles WHERE peer_id = ?", (to_peer,))
            self.cursor.execute("SELECT * FROM roles WHERE peer_id = ?", (from_peer,))
            for role in self.cursor.fetchall():
                rd = dict(role)
                try:
                    self.cursor.execute("INSERT INTO roles (peer_id, role_name, priority, emoji) VALUES (?, ?, ?, ?)", (to_peer, rd["role_name"], rd["priority"], rd.get("emoji", "")))
                except sqlite3.IntegrityError:
                    pass
            self.cursor.execute("DELETE FROM cmd_permissions WHERE peer_id = ?", (to_peer,))
            self.cursor.execute("SELECT * FROM cmd_permissions WHERE peer_id = ?", (from_peer,))
            for cp in self.cursor.fetchall():
                cpd = dict(cp)
                self.cursor.execute("INSERT INTO cmd_permissions (peer_id, command, min_priority) VALUES (?, ?, ?)", (to_peer, cpd["command"], cpd["min_priority"]))
            self.conn.commit()
            return True

    def set_role_alias(self, peer_id, priority, alias_name, alias_emoji=""):
        with self.lock:
            self.cursor.execute("INSERT OR REPLACE INTO role_aliases (peer_id, priority, alias_name, alias_emoji) VALUES (?, ?, ?, ?)", (peer_id, priority, alias_name, alias_emoji))
            self.conn.commit()

    def get_role_alias(self, peer_id, priority):
        with self.lock:
            self.cursor.execute("SELECT * FROM role_aliases WHERE peer_id = ? AND priority = ?", (peer_id, priority))
            r = self.cursor.fetchone()
            return dict(r) if r else None

    def create_note(self, peer_id, note_name, note_text, attachments, created_by):
        with self.lock:
            try:
                self.cursor.execute("INSERT INTO chat_notes (peer_id, note_name, note_text, attachments, created_by, created_at) VALUES (?, ?, ?, ?, ?, ?)", (peer_id, note_name.lower().strip(), note_text, attachments, created_by, time.time()))
                self.conn.commit()
                return True, "OK"
            except sqlite3.IntegrityError:
                return False, "Заметка существует."

    def update_note(self, peer_id, note_name, note_text, attachments, created_by):
        with self.lock:
            self.cursor.execute("UPDATE chat_notes SET note_text = ?, attachments = ?, created_by = ?, created_at = ? WHERE peer_id = ? AND note_name = ?", (note_text, attachments, created_by, time.time(), peer_id, note_name.lower().strip()))
            if self.cursor.rowcount == 0:
                return False, "Не найдена."
            self.conn.commit()
            return True, "OK"

    def delete_note(self, peer_id, note_name):
        with self.lock:
            self.cursor.execute("DELETE FROM chat_notes WHERE peer_id = ? AND note_name = ?", (peer_id, note_name.lower().strip()))
            if self.cursor.rowcount == 0:
                return False, "Не найдена."
            self.conn.commit()
            return True, "OK"

    def get_note(self, peer_id, note_name):
        with self.lock:
            self.cursor.execute("SELECT * FROM chat_notes WHERE peer_id = ? AND note_name = ?", (peer_id, note_name.lower().strip()))
            r = self.cursor.fetchone()
            return dict(r) if r else None

    def get_all_notes(self, peer_id):
        with self.lock:
            self.cursor.execute("SELECT * FROM chat_notes WHERE peer_id = ? ORDER BY note_name", (peer_id,))
            return [dict(r) for r in self.cursor.fetchall()]

    def add_cmd_alias(self, peer_id, original_cmd, alias):
        with self.lock:
            try:
                self.cursor.execute("INSERT OR REPLACE INTO cmd_aliases (peer_id, original_cmd, alias) VALUES (?, ?, ?)", (peer_id, original_cmd.lower(), alias.lower()))
                self.conn.commit()
                return True
            except:
                return False

    def remove_cmd_alias(self, peer_id, alias):
        with self.lock:
            self.cursor.execute("DELETE FROM cmd_aliases WHERE peer_id = ? AND alias = ?", (peer_id, alias.lower()))
            r = self.cursor.rowcount > 0
            self.conn.commit()
            return r

    def get_cmd_aliases(self, peer_id):
        with self.lock:
            self.cursor.execute("SELECT * FROM cmd_aliases WHERE peer_id = ? ORDER BY original_cmd", (peer_id,))
            return [dict(r) for r in self.cursor.fetchall()]

    def resolve_alias(self, peer_id, text):
        with self.lock:
            tl = text.lower().strip()
            self.cursor.execute("SELECT * FROM global_cmd_aliases")
            for a in self.cursor.fetchall():
                al = a["alias"]
                if tl == al or tl.startswith(al + " "):
                    rest = text[len(al):].strip()
                    return "/" + a["original_cmd"] + (" " + rest if rest else "")
            self.cursor.execute("SELECT * FROM cmd_aliases WHERE peer_id = ?", (peer_id,))
            for a in self.cursor.fetchall():
                al = a["alias"]
                if tl == al or tl.startswith(al + " "):
                    rest = text[len(al):].strip()
                    return "/" + a["original_cmd"] + (" " + rest if rest else "")
            return None

    # ============ ГЛОБАЛЬНЫЕ АЛИАСЫ ============

    def add_global_cmd_alias(self, original_cmd, alias):
        with self.lock:
            try:
                self.cursor.execute("INSERT OR REPLACE INTO global_cmd_aliases (original_cmd, alias) VALUES (?, ?)", (original_cmd.lower(), alias.lower()))
                self.conn.commit()
                return True
            except:
                return False

    def remove_global_cmd_alias(self, alias):
        with self.lock:
            self.cursor.execute("DELETE FROM global_cmd_aliases WHERE alias = ?", (alias.lower(),))
            r = self.cursor.rowcount > 0
            self.conn.commit()
            return r

    def get_global_cmd_aliases(self):
        with self.lock:
            self.cursor.execute("SELECT * FROM global_cmd_aliases ORDER BY original_cmd")
            return [dict(r) for r in self.cursor.fetchall()]

    # ============ ГЛОБАЛЬНЫЕ НАКАЗАНИЯ ============

    def global_ban_user(self, user_id, banned_by, reason, duration):
        with self.lock:
            if user_id in GLOBAL_ADMINS:
                return False
            bu = 0 if duration == 0 else time.time() + duration
            self.cursor.execute("INSERT OR REPLACE INTO global_bans (user_id, banned_by, reason, ban_until, created_at) VALUES (?, ?, ?, ?, ?)", (user_id, banned_by, reason, bu, time.time()))
            self.conn.commit()
            return True

    def global_unban_user(self, user_id):
        with self.lock:
            self.cursor.execute("DELETE FROM global_bans WHERE user_id = ?", (user_id,))
            r = self.cursor.rowcount > 0
            self.conn.commit()
            return r

    def is_globally_banned(self, user_id):
        with self.lock:
            if user_id in GLOBAL_ADMINS:
                return False
            self.cursor.execute("SELECT * FROM global_bans WHERE user_id = ?", (user_id,))
            r = self.cursor.fetchone()
            if not r:
                return False
            if r["ban_until"] == 0:
                return True
            if time.time() > r["ban_until"]:
                self.cursor.execute("DELETE FROM global_bans WHERE user_id = ?", (user_id,))
                self.conn.commit()
                return False
            return True

    def get_global_ban_info(self, user_id):
        with self.lock:
            self.cursor.execute("SELECT * FROM global_bans WHERE user_id = ?", (user_id,))
            r = self.cursor.fetchone()
            return dict(r) if r else None

    def global_mute_user(self, user_id, muted_by, reason, duration):
        with self.lock:
            if user_id in GLOBAL_ADMINS:
                return False
            mu = 0 if duration == 0 else time.time() + duration
            self.cursor.execute("INSERT OR REPLACE INTO global_mutes (user_id, muted_by, reason, mute_until, created_at) VALUES (?, ?, ?, ?, ?)", (user_id, muted_by, reason, mu, time.time()))
            self.conn.commit()
            return True

    def global_unmute_user(self, user_id):
        with self.lock:
            self.cursor.execute("DELETE FROM global_mutes WHERE user_id = ?", (user_id,))
            r = self.cursor.rowcount > 0
            self.conn.commit()
            return r

    def is_globally_muted(self, user_id):
        with self.lock:
            if user_id in GLOBAL_ADMINS:
                return False
            self.cursor.execute("SELECT * FROM global_mutes WHERE user_id = ?", (user_id,))
            r = self.cursor.fetchone()
            if not r:
                return False
            if r["mute_until"] == 0:
                return True
            if time.time() > r["mute_until"]:
                self.cursor.execute("DELETE FROM global_mutes WHERE user_id = ?", (user_id,))
                self.conn.commit()
                return False
            return True

    def get_global_mute_info(self, user_id):
        with self.lock:
            self.cursor.execute("SELECT * FROM global_mutes WHERE user_id = ?", (user_id,))
            r = self.cursor.fetchone()
            return dict(r) if r else None

    def add_global_vig(self, user_id, issued_by, vig_type, reason):
        with self.lock:
            if user_id in GLOBAL_ADMINS:
                return False
            self.cursor.execute("INSERT INTO global_vigs (user_id, issued_by, vig_type, reason, created_at) VALUES (?, ?, ?, ?, ?)", (user_id, issued_by, vig_type, reason, time.time()))
            self.conn.commit()
            return True

    def remove_global_vig_by_id(self, vig_id):
        with self.lock:
            self.cursor.execute("DELETE FROM global_vigs WHERE id = ?", (vig_id,))
            r = self.cursor.rowcount > 0
            self.conn.commit()
            return r

    def remove_global_vigs(self, user_id):
        with self.lock:
            self.cursor.execute("DELETE FROM global_vigs WHERE user_id = ?", (user_id,))
            r = self.cursor.rowcount > 0
            self.conn.commit()
            return r

    def get_global_vigs(self, user_id=None):
        with self.lock:
            if user_id:
                self.cursor.execute("SELECT * FROM global_vigs WHERE user_id = ? ORDER BY created_at DESC", (user_id,))
            else:
                self.cursor.execute("SELECT * FROM global_vigs ORDER BY created_at DESC")
            return [dict(r) for r in self.cursor.fetchall()]

    def get_global_vig_by_id(self, vig_id):
        with self.lock:
            self.cursor.execute("SELECT * FROM global_vigs WHERE id = ?", (vig_id,))
            r = self.cursor.fetchone()
            return dict(r) if r else None

    def create_ticket(self, user_id, problem_text, problem_type):
        with self.lock:
            self.cursor.execute("INSERT INTO support_tickets (user_id, problem_text, problem_type, status, created_at) VALUES (?, ?, ?, 'open', ?)", (user_id, problem_text, problem_type, time.time()))
            self.conn.commit()
            return self.cursor.lastrowid

    def get_open_ticket(self, user_id):
        with self.lock:
            self.cursor.execute("SELECT * FROM support_tickets WHERE user_id = ? AND status = 'open' ORDER BY created_at DESC LIMIT 1", (user_id,))
            r = self.cursor.fetchone()
            return dict(r) if r else None

    def close_ticket(self, ticket_id, closed_by):
        with self.lock:
            self.cursor.execute("UPDATE support_tickets SET status = 'closed', closed_at = ?, closed_by = ? WHERE id = ?", (time.time(), closed_by, ticket_id))
            self.conn.commit()
            return self.cursor.rowcount > 0

    def get_ticket_by_id(self, ticket_id):
        with self.lock:
            self.cursor.execute("SELECT * FROM support_tickets WHERE id = ?", (ticket_id,))
            r = self.cursor.fetchone()
            return dict(r) if r else None

    def get_all_chats_with_info(self):
        with self.lock:
            self.cursor.execute("SELECT peer_id, owner_id FROM chat_owners")
            return [dict(r) for r in self.cursor.fetchall()]


DEFAULT_CMD_PERMISSIONS = {
    "rcbl": 80, "rcnewrole": 90, "rcdelrole": 90, "rcrole": 80,
    "rcroles": 0, "rchelp": 0, "rccmd": 100, "rcban": 60,
    "rcunban": 60, "rcmute": 50, "rcunmute": 50, "rckick": 50,
    "rcvig": 50, "rcunvig": 50, "rcviglist": 0, "rcbanlist": 0,
    "rcmutelist": 0, "rcunbl": 80, "rctop": 0,
    "rcconnect": 100, "rcimport": 100, "rcbllist": 0, "rcdelmsg": 50,
    "rcstaff": 0, "rcmsg": 1000, "rcgban": 1000, "rcgunban": 1000,
    "rcgmute": 1000, "rcgunmute": 1000, "rcgkick": 1000, "rcgvig": 1000,
    "rcgunvig": 1000, "rclistchat": 1000, "rcstart": 100,
    "rcstats": 0, "rcvlads": 1000, "rcrenamrole": 1000,
    "rcnotes": 50, "rccmdname": 90, "rcgrole": 90, "rcgcmdname": 1000,
    "rcchat": 80
}


class PendingStore:
    def __init__(self, timeout=60):
        self.data = {}
        self.timeout = timeout
        self.lock = threading.Lock()

    def set(self, key, value):
        with self.lock:
            value["_created"] = time.time()
            self.data[key] = value

    def get(self, key):
        with self.lock:
            e = self.data.get(key)
            if not e:
                return None
            if time.time() - e["_created"] > self.timeout:
                del self.data[key]
                return None
            return e

    def pop(self, key):
        with self.lock:
            return self.data.pop(key, None)

    def has(self, key):
        return self.get(key) is not None

    def __contains__(self, key):
        return self.has(key)


bl_pending = PendingStore(60)
vig_pending = PendingStore(60)
unbl_pending = PendingStore(60)
gvig_pending = PendingStore(60)
support_pending = PendingStore(300)
unvig_pending = PendingStore(60)
gunvig_pending = PendingStore(60)


class Handlers:
    def __init__(self, vk, db, group_id):
        self.vk = vk
        self.db = db
        self.group_id = group_id
        self._nc = {}

    def send(self, pid, msg, keyboard=None, attachment=None):
        p = {"peer_id": pid, "message": msg, "random_id": random.randint(0, 2**31)}
        if keyboard:
            p["keyboard"] = keyboard.get_keyboard()
        if attachment:
            p["attachment"] = attachment
        try:
            self.vk.messages.send(**p)
        except Exception as e:
            logger.error(f"Send err: {e}")

    def mention(self, uid):
        if uid in self._nc:
            return f"@id{uid} ({self._nc[uid]})"
        try:
            i = self.vk.users.get(user_ids=uid)
            if i:
                n = f"{i[0]['first_name']} {i[0]['last_name']}"
                self._nc[uid] = n
                return f"@id{uid} ({n})"
        except:
            pass
        return f"@id{uid}"

    def extract_attachments(self, msg):
        attachments = msg.get("attachments", [])
        if not attachments:
            return ""
        result = []
        for att in attachments:
            att_type = att.get("type")
            obj = att.get(att_type, {})
            owner_id = obj.get("owner_id")
            obj_id = obj.get("id")
            access_key = obj.get("access_key", "")
            if not owner_id or not obj_id:
                continue
            if att_type in ("photo", "video", "doc", "audio", "audio_message", "wall", "graffiti"):
                base = f"{att_type}{owner_id}_{obj_id}"
                if access_key:
                    base += f"_{access_key}"
                result.append(base)
        return ",".join(result)

    def parse_target(self, event):
        text = event.get("text", "")
        reply = event.get("reply_message")
        if reply:
            tid = reply.get("from_id")
            if tid and tid <= 0:
                return None, text
            parts = text.split(maxsplit=1)
            return tid, parts[1] if len(parts) > 1 else ""
        fwd = event.get("fwd_messages", [])
        if fwd:
            tid = fwd[0].get("from_id")
            if tid and tid <= 0:
                return None, text
            parts = text.split(maxsplit=1)
            return tid, parts[1] if len(parts) > 1 else ""
        m = re.search(r'\[id(\d+)\|[^\]]*\]', text)
        if m:
            tid = int(m.group(1))
            rest = text.split(maxsplit=1)
            rest = rest[1] if len(rest) > 1 else ""
            rest = re.sub(r'\[id\d+\|[^\]]*\]', '', rest).strip()
            return tid, rest
        parts = text.split()
        if len(parts) >= 2:
            try:
                return int(parts[1]), " ".join(parts[2:])
            except ValueError:
                pass
        return None, text

    def parse_target_from_rest(self, rest_text, event):
        reply = event.get("reply_message")
        if reply:
            tid = reply.get("from_id")
            if tid and tid > 0:
                return tid
        fwd = event.get("fwd_messages", [])
        if fwd:
            tid = fwd[0].get("from_id")
            if tid and tid > 0:
                return tid
        m = re.search(r'\[id(\d+)\|[^\]]*\]', rest_text)
        if m:
            return int(m.group(1))
        parts = rest_text.split()
        if parts:
            try:
                return int(parts[0])
            except ValueError:
                pass
        return None

    def is_ga(self, uid):
        return uid in GLOBAL_ADMINS

    def get_prio(self, pid, uid):
        s = self.db.get_settings(pid)
        if s.get("connected"):
            return self.db.get_user_priority_pool(pid, uid)
        return self.db.get_user_priority(pid, uid)

    def min_prio(self, pid, cmd):
        p = self.db.get_cmd_permission(pid, cmd)
        return p if p is not None else DEFAULT_CMD_PERMISSIONS.get(cmd, 100)

    def has_perm(self, pid, uid, cmd):
        return self.get_prio(pid, uid) >= self.min_prio(pid, cmd)

    def format_role(self, pid, uid):
        if self.is_ga(uid):
            return "⭐ Глобальный Администратор (1000)"
        if self.get_prio(pid, uid) >= 100 and self.db.get_chat_owner(pid) == uid:
            alias = self.db.get_role_alias(pid, 100)
            if alias:
                emoji = alias.get("alias_emoji", "") or ""
                name = alias.get("alias_name", "Владелец")
                return f"{emoji} {name} (100)" if emoji else f"👑 {name} (100)"
            return "👑 Владелец (100)"
        ri = self.db.get_user_role(pid, uid)
        if ri:
            emoji = ri.get("emoji", "") or ""
            return f"{emoji} {ri['role_name']} ({ri['priority']})" if emoji else f"{ri['role_name']} ({ri['priority']})"
        alias = self.db.get_role_alias(pid, 0)
        if alias:
            emoji = alias.get("alias_emoji", "") or ""
            name = alias.get("alias_name", "Пользователь")
            return f"{emoji} {name} (0)" if emoji else f"{name} (0)"
        return "Пользователь (0)"

    def auto_owner(self, pid, event):
        if self.db.get_chat_owner(pid) is not None:
            return
        try:
            ci = self.vk.messages.getConversationsById(peer_ids=pid, group_id=self.group_id)
            items = ci.get("items", [])
            if items:
                ow = items[0].get("chat_settings", {}).get("owner_id")
                if ow:
                    self.db.set_chat_owner(pid, ow)
                    return
        except:
            pass
        fid = event.get("from_id", 0)
        if fid > 0:
            self.db.set_chat_owner(pid, fid)

    def parse_dur(self, t):
        t = t.strip().lower()
        if t in ('n', 'навсегда'):
            return 0, "навсегда"
        m = re.match(r'^(\d+)([smhd])$', t)
        if not m:
            return None, None
        a, u = int(m.group(1)), m.group(2)
        mul = {'s': 1, 'm': 60, 'h': 3600, 'd': 86400}
        nm = {'s': 'сек.', 'm': 'мин.', 'h': 'ч.', 'd': 'дн.'}
        return a * mul[u], f"{a} {nm[u]}"

    def kick(self, pid, uid):
        if uid in GLOBAL_ADMINS:
            return False
        try:
            cid = pid - 2000000000
            if cid > 0:
                self.vk.messages.removeChatUser(chat_id=cid, user_id=uid)
                return True
        except:
            pass
        return False

    def fmt_time(self, ts):
        if ts == 0:
            return "навсегда"
        left = ts - time.time()
        if left <= 0:
            return "истекло"
        if left < 60:
            return f"{int(left)}с"
        if left < 3600:
            return f"{int(left/60)}м"
        if left < 86400:
            return f"{int(left/3600)}ч"
        return f"{int(left/86400)}д"

    def handle_chat_invite(self, pid, uid, inviter):
        if self.db.is_globally_banned(uid):
            gi = self.db.get_global_ban_info(uid)
            self.send(pid, f"⛔ {self.mention(uid)} в глобальном бане!")
            self.kick(pid, uid)
            return
        bi = self.db.get_ban_info(pid, uid)
        if not bi:
            return
        banner_prio = self.get_prio(pid, bi["banned_by"])
        inviter_prio = self.get_prio(pid, inviter)
        if banner_prio > inviter_prio:
            self.send(pid, f"⛔ {self.mention(uid)} забанен!")
            self.kick(pid, uid)
        else:
            self.db.unban_user(pid, uid)
            self.send(pid, f"✅ {self.mention(uid)} разбанен автоматически.")

    def handle_message(self, msg):
        text = msg.get("text", "").strip()
        pid = msg.get("peer_id")
        fid = msg.get("from_id")
        action = msg.get("action")
        if not pid or not fid:
            return
        if action:
            if action.get("type") == "chat_invite_user":
                mid = action.get("member_id")
                if mid and mid > 0:
                    self.handle_chat_invite(pid, mid, fid)
                    return
        self.auto_owner(pid, msg)
        self.db.get_settings(pid)

        if not self.is_ga(fid):
            if self.db.is_globally_banned(fid):
                self.kick(pid, fid)
                return
            if self.db.is_globally_muted(fid):
                try:
                    cmid = msg.get("conversation_message_id")
                    if cmid:
                        self.vk.messages.delete(cmids=cmid, peer_id=pid, delete_for_all=1, group_id=self.group_id)
                except:
                    pass
                return
            if self.db.is_muted(pid, fid):
                try:
                    cmid = msg.get("conversation_message_id")
                    if cmid:
                        self.vk.messages.delete(cmids=cmid, peer_id=pid, delete_for_all=1, group_id=self.group_id)
                except:
                    pass
                return
            if self.db.is_banned(pid, fid):
                self.kick(pid, fid)
                return
            bl = self.db.is_blacklisted_in_chat(fid, pid)
            if bl:
                self.kick(pid, fid)
                return

            # Проверка закрытого чата
            settings = self.db.get_settings(pid)
            if settings.get("chat_closed") and self.get_prio(pid, fid) < 80:
                try:
                    cmid = msg.get("conversation_message_id")
                    if cmid:
                        self.vk.messages.delete(cmids=cmid, peer_id=pid, delete_for_all=1, group_id=self.group_id)
                except:
                    pass
                return

        if not text:
            return
        if fid > 0:
            self.db.increment_msg(pid, fid)
        tl = text.lower().strip()

        if fid in support_pending:
            self.process_support_problem(pid, fid, text)
            return
        if fid in vig_pending and tl in ("грубый выговор", "выговор", "устный выговор"):
            self.process_vig_choice(pid, fid, tl)
            return
        if fid in gvig_pending and tl in ("грубый выговор", "выговор", "устный выговор"):
            self.process_gvig_choice(pid, fid, tl)
            return
        if fid in bl_pending and tl in ("чса", "чсл", "чсп", "чсс"):
            self.process_bl_choice(pid, fid, tl)
            return
        if fid in unbl_pending and tl in ("чса", "чсл", "чсп", "чсс", "все"):
            self.process_unbl_choice(pid, fid, tl)
            return

        if tl.startswith("#") and len(tl) > 1:
            note_name = tl[1:].strip()
            if note_name:
                note = self.db.get_note(pid, note_name)
                if note:
                    att = note.get("attachments", "") or None
                    note_text = note.get("note_text", "")
                    self.send(pid, note_text if note_text else f"📝 #{note_name}", attachment=att if att else None)
                    return

        if "фантик" in tl:
            self.send(pid, f"Привет, {self.mention(fid)}!\nЯ — бот RussianCraft.\nВаша роль » {self.format_role(pid, fid)}\nКоманды: /rchelp")
            return
        if tl == "!id":
            r = f"🆔 Peer ID: {pid}"
            if pid > 2000000000:
                r += f"\n✅ Chat ID: {pid - 2000000000}"
            self.send(pid, r)
            return
        if tl == "!test":
            self.send(pid, "Бот работает!")
            return

        resolved = self.db.resolve_alias(pid, text)
        if resolved:
            msg = dict(msg)
            msg["text"] = resolved
            text = resolved
            tl = text.lower().strip()

        cmds = {
            "/rchelp": self.cmd_help, "/rcnewrole": self.cmd_newrole,
            "/rcdelrole": self.cmd_delrole, "/rcroles": self.cmd_roles,
            "/rcrole": self.cmd_role, "/rccmdname": self.cmd_cmdname,
            "/rcgcmdname": self.cmd_gcmdname,
            "/rccmd": self.cmd_cmd, "/rcchat": self.cmd_chat,
            "/rcban": self.cmd_ban, "/rcunban": self.cmd_unban,
            "/rcmute": self.cmd_mute, "/rcunmute": self.cmd_unmute,
            "/rckick": self.cmd_kick, "/rcbl": self.cmd_bl,
            "/rcunbl": self.cmd_unbl, "/rcbllist": self.cmd_bllist,
            "/rcvig": self.cmd_vig, "/rcunvig": self.cmd_unvig,
            "/rcviglist": self.cmd_viglist, "/rcbanlist": self.cmd_banlist,
            "/rcmutelist": self.cmd_mutelist, "/rctop": self.cmd_top,
            "/rcconnect": self.cmd_connect, "/rcimport": self.cmd_import,
            "/rcdelmsg": self.cmd_delmsg, "/rcstaff": self.cmd_staff,
            "/rcmsg": self.cmd_msg,
            "/rcgban": self.cmd_gban, "/rcgunban": self.cmd_gunban,
            "/rcgmute": self.cmd_gmute, "/rcgunmute": self.cmd_gunmute,
            "/rcgkick": self.cmd_gkick, "/rcgvig": self.cmd_gvig,
            "/rcgunvig": self.cmd_gunvig, "/rclistchat": self.cmd_listchat,
            "/rcgrole": self.cmd_grole,
            "/rcstart": self.cmd_start,
            "/rcstats": self.cmd_stats, "/стата": self.cmd_stats,
            "/rcvlads": self.cmd_vlads,
            "/rcrenamrole": self.cmd_renamrole,
            "/rcnotes": self.cmd_notes,
        }
        for c, f in cmds.items():
            if tl.startswith(c):
                f(msg, pid, fid)
                return

    def cmd_help(self, e, pid, fid):
        self.send(pid, f"📖 Команды RussianCraft\n{self.mention(fid)} | {self.format_role(pid, fid)}\n\nМодерация:\n  /rcban /rcunban /rcmute /rcunmute\n  /rckick /rcbl /rcunbl /rcvig /rcunvig\n  /rcdelmsg /rcchat\n\nГлобальные:\n  /rcgban /rcgunban /rcgmute /rcgunmute\n  /rcgkick /rcgvig /rcgunvig\n  /rcgrole /rcgcmdname /rclistchat\n\nСписки:\n  /rcbanlist /rcmutelist /rcviglist /rcbllist\n\nРоли:\n  /rcnewrole /rcdelrole /rcrole /rcroles /rcstaff\n\nНастройки:\n  /rccmd /rccmdname /rcconnect /rcimport\n\nЗаметки:\n  /rcnotes\n\n⏱ Время: 1s/5m/2h/3d/n")

    # ============ /rcchat ============

    def cmd_chat(self, e, pid, fid):
        if not self.has_perm(pid, fid, "rcchat"):
            return self.send(pid, "❌ Нет прав (мин. 80).")
        text = e.get("text", "").strip()
        parts = text.split()
        settings = self.db.get_settings(pid)
        current = settings.get("chat_closed", 0)
        
        if len(parts) < 2:
            status = "🔒 закрыт" if current else "🔓 открыт"
            return self.send(pid, f"💬 Чат {status}\n\n/rcchat on — закрыть (писать могут только 80+)\n/rcchat off — открыть")
        
        arg = parts[1].lower()
        if arg == "on":
            self.db.update_setting(pid, "chat_closed", 1)
            self.send(pid, "🔒 Чат закрыт. Писать могут только пользователи с приоритетом 80+.")
        elif arg == "off":
            self.db.update_setting(pid, "chat_closed", 0)
            self.send(pid, "🔓 Чат открыт.")
        else:
            self.send(pid, "❌ /rcchat on|off")

    # ============ /rcstats ============

    def cmd_stats(self, e, pid, fid):
        tid, _ = self.parse_target(e)
        target = tid if tid else fid
        name = self.mention(target)
        role_str = self.format_role(pid, target)
        punishments = []
        ban_info = self.db.get_ban_info(pid, target)
        if ban_info and self.db.is_banned(pid, target):
            punishments.append(f"  🔴 Бан -> {self.fmt_time(ban_info.get('ban_until', 0))}")
        mute_info = self.db.get_mute_info(pid, target)
        if mute_info and self.db.is_muted(pid, target):
            punishments.append(f"  🟡 Мут -> {self.fmt_time(mute_info.get('mute_until', 0))}")
        vigs = self.db.get_vigs(pid, target)
        vig_icons = {"грубый выговор": "🔴", "выговор": "🟡", "устный выговор": "🟢"}
        for v in vigs:
            punishments.append(f"  {vig_icons.get(v['vig_type'], '⚠️')} {v['vig_type'].title()}")
        gban_info = self.db.get_global_ban_info(target)
        if gban_info and self.db.is_globally_banned(target):
            punishments.append(f"  🌐🔴 Глобальный бан -> {self.fmt_time(gban_info.get('ban_until', 0))}")
        gmute_info = self.db.get_global_mute_info(target)
        if gmute_info and self.db.is_globally_muted(target):
            punishments.append(f"  🌐🟡 Глобальный мут -> {self.fmt_time(gmute_info.get('mute_until', 0))}")
        punishments_str = "\n".join(punishments) if punishments else "  Нет"
        bl_entries = self.db.get_user_blacklist_entries(target, pid)
        bl_types_map = {"chat_admin": "ЧСА", "chat_local": "ЧСЛ", "full_project": "ЧСП", "full_strict": "ЧСС"}
        bl_str = ", ".join(list(set([bl_types_map.get(b["bl_type"], b["bl_type"]) for b in bl_entries]))) if bl_entries else "Нет"
        self.send(pid, f"⚙️ Имя: {name}\n👾 Роль: {role_str}\n🛡 Наказания:\n{punishments_str}\n❇️ ЧС: {bl_str}")

    # ============ /rccmdname ============

    def cmd_cmdname(self, e, pid, fid):
        if not self.has_perm(pid, fid, "rccmdname"):
            return self.send(pid, "❌ Нет прав (мин. 90).")
        text = e.get("text", "").strip()
        parts = text.split(maxsplit=1)
        if len(parts) < 2:
            return self.send(pid, "📝 /rccmdname /rcban /бан !бан\n/rccmdname list\n/rccmdname del [алиас]")
        args = parts[1].strip()
        args_lower = args.lower()
        if args_lower == "list":
            aliases = self.db.get_cmd_aliases(pid)
            if not aliases:
                return self.send(pid, "📝 Алиасов нет.")
            txt = "📝 Алиасы:\n\n"
            for a in aliases:
                txt += f"  /{a['original_cmd']} -> {a['alias']}\n"
            return self.send(pid, txt)
        if args_lower.startswith("del "):
            alias_to_del = args[4:].strip().lower()
            if self.db.remove_cmd_alias(pid, alias_to_del):
                self.send(pid, f"🗑 Алиас «{alias_to_del}» удалён.")
            else:
                self.send(pid, f"❌ Не найден.")
            return
        tokens = args.split()
        if len(tokens) < 2:
            return self.send(pid, "❌ /rccmdname /rcban /бан !бан")
        original = tokens[0].lower().replace("/", "").strip()
        if original not in DEFAULT_CMD_PERMISSIONS:
            return self.send(pid, f"❌ Неизвестная: {original}")
        added = []
        for alias_raw in tokens[1:]:
            alias = alias_raw.strip().lower()
            if alias and self.db.add_cmd_alias(pid, original, alias):
                added.append(alias)
        if added:
            self.send(pid, f"✅ /{original} -> " + ", ".join(added))
        else:
            self.send(pid, "❌ Не удалось.")

    # ============ /rcgcmdname ============

    def cmd_gcmdname(self, e, pid, fid):
        if not self.is_ga(fid):
            return self.send(pid, "❌ Только ГА.")
        text = e.get("text", "").strip()
        parts = text.split(maxsplit=1)
        if len(parts) < 2:
            return self.send(pid, "🌐 /rcgcmdname /rcban /бан !бан\n/rcgcmdname list\n/rcgcmdname del [алиас]")
        args = parts[1].strip()
        args_lower = args.lower()
        if args_lower == "list":
            aliases = self.db.get_global_cmd_aliases()
            if not aliases:
                return self.send(pid, "🌐 Глобальных алиасов нет.")
            txt = "🌐 Глобальные алиасы:\n\n"
            for a in aliases:
                txt += f"  /{a['original_cmd']} -> {a['alias']}\n"
            return self.send(pid, txt)
        if args_lower.startswith("del "):
            alias_to_del = args[4:].strip().lower()
            if self.db.remove_global_cmd_alias(alias_to_del):
                self.send(pid, f"🗑 Глобальный алиас «{alias_to_del}» удалён.")
            else:
                self.send(pid, f"❌ Не найден.")
            return
        tokens = args.split()
        if len(tokens) < 2:
            return self.send(pid, "❌ /rcgcmdname /rcban /бан !бан")
        original = tokens[0].lower().replace("/", "").strip()
        if original not in DEFAULT_CMD_PERMISSIONS:
            return self.send(pid, f"❌ Неизвестная: {original}")
        added = []
        for alias_raw in tokens[1:]:
            alias = alias_raw.strip().lower()
            if alias and self.db.add_global_cmd_alias(original, alias):
                added.append(alias)
        if added:
            self.send(pid, f"🌐 /{original} -> " + ", ".join(added))
        else:
            self.send(pid, "❌ Не удалось.")

    # ============ /rcgrole ============

    def cmd_grole(self, e, pid, fid):
        if not self.has_perm(pid, fid, "rcgrole"):
            return self.send(pid, "❌ Нет прав (мин. 90).")
        tid, rest = self.parse_target(e)
        if not tid:
            return self.send(pid, "❌ /rcgrole [юзер] [приоритет]")
        if self.is_ga(tid) and not self.is_ga(fid):
            return self.send(pid, "⛔ ГА защищён.")
        try:
            pa = int(rest.strip().split()[0])
        except (ValueError, IndexError):
            return self.send(pid, "❌ Укажите приоритет.")
        all_peers = self.db.get_all_chat_peers()
        assigned = 0
        removed = 0
        if pa == 0:
            for peer in all_peers:
                ok, _ = self.db.remove_role(peer, tid)
                if ok:
                    removed += 1
            self.send(pid, f"🌐 {self.mention(tid)} -> Без роли (0)\n🛡 {self.mention(fid)}\n
self.send(pid, f"🌐 {self.mention(tid)} -> Без роли (0)\n🛡 {self.mention(fid)}\n🌍 Снято в {removed}/{len(all_peers)} чатах")
            # Уведомляем чаты
            for peer in all_peers:
                if peer != pid:
                    try:
                        self.send(peer, f"🌐 Глобальная смена роли:\n👾 {self.mention(tid)} -> Без роли (0)\n🛡 Выдал: {self.mention(fid)}")
                    except:
                        pass
            return
        for peer in all_peers:
            role = self.db.get_role_by_priority(peer, pa)
            if role:
                ok, _ = self.db.assign_role(peer, tid, pa)
                if ok:
                    assigned += 1
        self.send(pid, f"🌐 {self.mention(tid)} -> приоритет {pa}\n🛡 {self.mention(fid)}\n🌍 Назначено в {assigned}/{len(all_peers)} чатах")
        # Уведомляем чаты
        for peer in all_peers:
            if peer != pid:
                try:
                    self.send(peer, f"🌐 Глобальная смена роли:\n👾 {self.mention(tid)} -> приоритет {pa}\n🛡 Выдал: {self.mention(fid)}")
                except:
                    pass

    # ============ /rcnotes ============

    def cmd_notes(self, e, pid, fid):
        text = e.get("text", "").strip()
        parts = text.split(maxsplit=1)
        if len(parts) < 2:
            return self.send(pid, "📝 /rcnotes list|create [имя] [текст]|del [имя]|[имя]\n#имя — быстрый вызов")
        args = parts[1].strip()
        args_lower = args.lower()
        if args_lower == "list":
            notes = self.db.get_all_notes(pid)
            if not notes:
                return self.send(pid, "📝 Заметок нет.")
            txt = "📝 Заметки:\n\n"
            for i, note in enumerate(notes, 1):
                has_att = " 📎" if note.get("attachments") else ""
                txt += f"{i}. #{note['note_name']}{has_att}\n"
            return self.send(pid, txt + f"\n📊 Всего: {len(notes)}")
        if args_lower.startswith("create "):
            if not self.has_perm(pid, fid, "rcnotes"):
                return self.send(pid, "❌ Нет прав.")
            create_rest = args[7:].strip()
            if not create_rest:
                return self.send(pid, "❌ /rcnotes create [название] [текст]")
            create_parts = create_rest.split(maxsplit=1)
            note_name = create_parts[0].strip().lower()
            note_text = create_parts[1].strip() if len(create_parts) > 1 else ""
            if not re.match(r'^[a-zа-яё0-9_\-]+$', note_name):
                return self.send(pid, "❌ Название: буквы, цифры, _ и -")
            attachments = self.extract_attachments(e)
            if not note_text and not attachments:
                return self.send(pid, "❌ Укажите текст и/или прикрепите файлы.")
            existing = self.db.get_note(pid, note_name)
            if existing:
                ok, msg_r = self.db.update_note(pid, note_name, note_text, attachments, fid)
                self.send(pid, f"✅ #{note_name} обновлена." if ok else f"❌ {msg_r}")
            else:
                ok, msg_r = self.db.create_note(pid, note_name, note_text, attachments, fid)
                self.send(pid, f"✅ #{note_name} создана. Вызов: #{note_name}" if ok else f"❌ {msg_r}")
            return
        if args_lower.startswith("del "):
            if not self.has_perm(pid, fid, "rcnotes"):
                return self.send(pid, "❌ Нет прав.")
            note_name = args[4:].strip().lower()
            if not note_name:
                return self.send(pid, "❌ /rcnotes del [название]")
            ok, msg_r = self.db.delete_note(pid, note_name)
            self.send(pid, f"🗑 #{note_name} удалена." if ok else f"❌ {msg_r}")
            return
        note_name = args_lower.strip()
        note = self.db.get_note(pid, note_name)
        if note:
            att = note.get("attachments", "") or None
            note_text = note.get("note_text", "")
            self.send(pid, note_text if note_text else f"📝 #{note_name}", attachment=att if att else None)
        else:
            self.send(pid, f"❌ #{note_name} не найдена.")

    def cmd_vlads(self, e, pid, fid):
        if not self.is_ga(fid):
            return self.send(pid, "❌ Только ГА.")
        tid, _ = self.parse_target(e)
        if not tid or tid <= 0:
            return self.send(pid, "❌ /rcvlads [юзер]")
        old_owner = self.db.get_chat_owner(pid)
        if old_owner and old_owner != tid:
            self.db.remove_role(pid, old_owner)
        self.db.set_chat_owner(pid, tid)
        self.send(pid, f"〽️ Новый владелец чата -> {self.mention(tid)}")

    def cmd_renamrole(self, e, pid, fid):
        if not self.is_ga(fid):
            return self.send(pid, "❌ Только ГА.")
        parts = e.get("text", "").split(maxsplit=2)
        if len(parts) < 3:
            return self.send(pid, "❌ /rcrenamrole [0|100] [Эмодзи Название]")
        try:
            priority = int(parts[1])
        except ValueError:
            return self.send(pid, "❌ Число (0 или 100).")
        if priority not in (0, 100):
            return self.send(pid, "❌ Только 0 или 100.")
        role_text = parts[2].strip()
        emoji, role_name = "", role_text
        ep = re.match(r'^([\U0001F000-\U0001F9FF\U0001FA00-\U0001FA6F\U0001FA70-\U0001FAFF\u2600-\u26FF\u2700-\u27BF])\s*(.+)$', role_text)
        if ep:
            emoji, role_name = ep.group(1), ep.group(2).strip()
        self.db.set_role_alias(pid, priority, role_name, emoji)
        display = f"{emoji} {role_name} ({priority})" if emoji else f"{role_name} ({priority})"
        default_name = "Пользователь" if priority == 0 else "Владелец"
        self.send(pid, f"✅ «{default_name} ({priority})» -> «{display}»")

    def cmd_ban(self, e, pid, fid):
        if not self.has_perm(pid, fid, "rcban"):
            return self.send(pid, "❌ Нет прав.")
        tid, rest = self.parse_target(e)
        if not tid:
            return self.send(pid, "❌ /rcban [юзер] [время] [причина]")
        if self.is_ga(tid):
            return self.send(pid, "⛔ ГА защищён.")
        tp, up = self.get_prio(pid, tid), self.get_prio(pid, fid)
        if tp >= up:
            return self.send(pid, f"🚫 ({tp}) ≥ ({up}).")
        parts = rest.split(maxsplit=1)
        if not parts:
            return self.send(pid, "❌ Укажите время.")
        dur, ht = self.parse_dur(parts[0])
        if dur is None:
            return self.send(pid, "❌ Неверное время.")
        reason = parts[1].strip() if len(parts) > 1 else "Не указана"
        issuer_role = self.format_role(pid, fid)
        tr = self.format_role(pid, tid)
        self.db.ban_user(pid, tid, fid, reason, dur)
        self.kick(pid, tid)
        self.send(pid, f"👾 Бан: {self.mention(tid)}\n🛡 Выдал: {self.mention(fid)}\n〽️ Роль: {issuer_role}\n🌹 Нарушитель: {tr}\n📌 {reason} | {ht}")

    def cmd_unban(self, e, pid, fid):
        if not self.has_perm(pid, fid, "rcunban"):
            return self.send(pid, "❌ Нет прав.")
        tid, _ = self.parse_target(e)
        if not tid:
            return self.send(pid, "❌ /rcunban [юзер]")
        bi = self.db.get_ban_info(pid, tid)
        if bi and not self.is_ga(fid):
            bp = self.get_prio(pid, bi["banned_by"])
            mp = self.get_prio(pid, fid)
            if bp > mp:
                return self.send(pid, f"🚫 Нельзя снять бан! ({bp}) > ({mp})")
        if self.db.unban_user(pid, tid):
            self.send(pid, f"👾 Разбан: {self.mention(tid)}\n🛡 Снял: {self.mention(fid)}")
        else:
            self.send(pid, f"❌ Не в бане.")

    def cmd_mute(self, e, pid, fid):
        if not self.has_perm(pid, fid, "rcmute"):
            return self.send(pid, "❌ Нет прав.")
        tid, rest = self.parse_target(e)
        if not tid:
            return self.send(pid, "❌ /rcmute [юзер] [время] [причина]")
        if self.is_ga(tid):
            return self.send(pid, "⛔ ГА защищён.")
        tp, up = self.get_prio(pid, tid), self.get_prio(pid, fid)
        if tp >= up:
            return self.send(pid, f"🚫 ({tp}) ≥ ({up}).")
        parts = rest.split(maxsplit=1)
        if not parts:
            return self.send(pid, "❌ Укажите время.")
        dur, ht = self.parse_dur(parts[0])
        if dur is None:
            return self.send(pid, "❌ Неверное время.")
        reason = parts[1].strip() if len(parts) > 1 else "Не указана"
        issuer_role = self.format_role(pid, fid)
        tr = self.format_role(pid, tid)
        self.db.mute_user(pid, tid, fid, reason, dur)
        self.send(pid, f"👾 Мут: {self.mention(tid)}\n🛡 Выдал: {self.mention(fid)}\n〽️ Роль: {issuer_role}\n🌹 Нарушитель: {tr}\n📌 {reason} | {ht}")

    def cmd_unmute(self, e, pid, fid):
        if not self.has_perm(pid, fid, "rcunmute"):
            return self.send(pid, "❌ Нет прав.")
        tid, _ = self.parse_target(e)
        if not tid:
            return self.send(pid, "❌ /rcunmute [юзер]")
        mi = self.db.get_mute_info(pid, tid)
        if mi and not self.is_ga(fid):
            mp2 = self.get_prio(pid, mi["muted_by"])
            mp = self.get_prio(pid, fid)
            if mp2 > mp:
                return self.send(pid, f"🚫 Нельзя снять мут! ({mp2}) > ({mp})")
        if self.db.unmute_user(pid, tid):
            self.send(pid, f"👾 Размут: {self.mention(tid)}\n🛡 Снял: {self.mention(fid)}")
        else:
            self.send(pid, f"❌ Не в муте.")

    def cmd_kick(self, e, pid, fid):
        if not self.has_perm(pid, fid, "rckick"):
            return self.send(pid, "❌ Нет прав.")
        tid, rest = self.parse_target(e)
        if not tid:
            return self.send(pid, "❌ /rckick [юзер] [причина]")
        if self.is_ga(tid):
            return self.send(pid, "⛔ ГА защищён.")
        tp, up = self.get_prio(pid, tid), self.get_prio(pid, fid)
        if tp >= up:
            return self.send(pid, f"🚫 ({tp}) ≥ ({up}).")
        reason = rest.strip() or "Не указана"
        issuer_role = self.format_role(pid, fid)
        tr = self.format_role(pid, tid)
        if self.kick(pid, tid):
            self.send(pid, f"👾 Кик: {self.mention(tid)}\n🛡 Выдал: {self.mention(fid)}\n〽️ Роль: {issuer_role}\n🌹 Нарушитель: {tr}\n📌 {reason}")
        else:
            self.send(pid, "❌ Не удалось кикнуть.")

    def cmd_vig(self, e, pid, fid):
        if not self.has_perm(pid, fid, "rcvig"):
            return self.send(pid, "❌ Нет прав.")
        tid, rest = self.parse_target(e)
        if not tid:
            return self.send(pid, "❌ /rcvig [юзер] [причина]")
        if self.is_ga(tid):
            return self.send(pid, "⛔ ГА защищён.")
        tp, up = self.get_prio(pid, tid), self.get_prio(pid, fid)
        if tp >= up:
            return self.send(pid, f"🚫 ({tp}) ≥ ({up}).")
        reason = rest.strip() or "Не указана"
        vig_pending.set(fid, {"target_id": tid, "peer_id": pid, "reason": reason})
        keyboard = VkKeyboard(inline=True)
        keyboard.add_callback_button("Грубый выговор", color=VkKeyboardColor.NEGATIVE, payload=json.dumps({"button": "vig_грубый выговор"}))
        keyboard.add_line()
        keyboard.add_callback_button("Выговор", color=VkKeyboardColor.PRIMARY, payload=json.dumps({"button": "vig_выговор"}))
        keyboard.add_line()
        keyboard.add_callback_button("Устный выговор", color=VkKeyboardColor.POSITIVE, payload=json.dumps({"button": "vig_устный выговор"}))
        self.send(pid, f"⚠️ Выговор для {self.mention(tid)}\n📋 {reason}\n\nВыберите тип:", keyboard=keyboard)

    def process_vig_choice(self, pid, fid, choice):
        p = vig_pending.pop(fid)
        if not p:
            return self.send(pid, "❌ Нет запроса.")
        if time.time() - p["_created"] > 60:
            return self.send(pid, "⏰ Истекло.")
        tid, reason = p["target_id"], p["reason"]
        icons = {"грубый выговор": "🔴", "выговор": "🟡", "устный выговор": "🟢"}
        issuer_role = self.format_role(pid, fid)
        self.db.add_vig(pid, tid, fid, choice, reason)
        total = len(self.db.get_vigs(pid, tid))
        self.send(pid, f"👾 {icons.get(choice,'')} {choice.title()}: {self.mention(tid)}\n🛡 Выдал: {self.mention(fid)}\n〽️ Роль: {issuer_role}\n🌹 {self.format_role(pid, tid)}\n📌 {reason}\n📊 Всего: {total}")

    def cmd_unvig(self, e, pid, fid):
        if not self.has_perm(pid, fid, "rcunvig"):
            return self.send(pid, "❌ Нет прав.")
        tid, _ = self.parse_target(e)
        if not tid:
            return self.send(pid, "❌ /rcunvig [юзер]")
        mx = self.db.get_vig_issuer_max_priority(pid, tid)
        mp = self.get_prio(pid, fid)
        if mx > mp and not self.is_ga(fid):
            return self.send(pid, f"🚫 ({mx}) > ({mp})")
        vigs = self.db.get_vigs(pid, tid)
        if not vigs:
            return self.send(pid, "❌ Нет выговоров.")
        icons = {"грубый выговор": "🔴", "выговор": "🟡", "устный выговор": "🟢"}
        keyboard = VkKeyboard(inline=True)
        for i, v in enumerate(vigs[:5]):
            label = f"{icons.get(v['vig_type'], '⚠️')} {v['vig_type'].title()}"[:40]
            keyboard.add_callback_button(label, color=VkKeyboardColor.PRIMARY, payload=json.dumps({"button": f"unvig_{v['id']}"}))
            if i < len(vigs[:5]) - 1:
                keyboard.add_line()
        keyboard.add_line()
        keyboard.add_callback_button("🗑 Снять все", color=VkKeyboardColor.NEGATIVE, payload=json.dumps({"button": f"unvig_all_{tid}_{pid}"}))
        unvig_pending.set(fid, {"target_id": tid, "peer_id": pid})
        txt = f"⚠️ Выговоры {self.mention(tid)}:\n\n"
        for i, v in enumerate(vigs[:5], 1):
            txt += f"{i}. {icons.get(v['vig_type'], '')} {v['vig_type']} — {v['reason']}\n"
        txt += f"\n📊 Всего: {len(vigs)}\nВыберите какой снять:"
        self.send(pid, txt, keyboard=keyboard)

    def cmd_viglist(self, e, pid, fid):
        text = e.get("text", "").strip()
        parts = text.split(maxsplit=1)
        tid = None
        if len(parts) > 1:
            tid = self.parse_target_from_rest(parts[1].strip(), e)
        vigs = self.db.get_vigs(pid, tid)
        if not vigs:
            return self.send(pid, "📋 Выговоров нет.")
        icons = {"грубый выговор": "🔴", "выговор": "🟡", "устный выговор": "🟢"}
        txt = "📋 Выговоры\n\n"
        for i, v in enumerate(vigs[:20], 1):
            txt += f"{i}. {icons.get(v['vig_type'],'')} {self.mention(v['user_id'])} — {v['vig_type']}\n   📌 {v['reason']}\n   🛡 {self.mention(v['issued_by'])}\n"
        self.send(pid, txt + f"\n📊 Всего: {len(vigs)}")

    def cmd_bl(self, e, pid, fid):
        if not self.has_perm(pid, fid, "rcbl"):
            return self.send(pid, "❌ Нет прав.")
        tid, rest = self.parse_target(e)
        if not tid:
            return self.send(pid, "❌ /rcbl [юзер] [причина]")
        if self.is_ga(tid):
            return self.send(pid, "⛔ ГА защищён.")
        tp, up = self.get_prio(pid, tid), self.get_prio(pid, fid)
        if tp >= up:
            return self.send(pid, f"🚫 ({tp}) ≥ ({up}).")
        reason = rest.strip() or "Не указана"
        bl_pending.set(fid, {"target_id": tid, "peer_id": pid, "reason": reason})
        keyboard = VkKeyboard(inline=True)
        keyboard.add_callback_button("ЧСА", color=VkKeyboardColor.PRIMARY, payload=json.dumps({"button": "ЧСА"}))
        keyboard.add_callback_button("ЧСЛ", color=VkKeyboardColor.PRIMARY, payload=json.dumps({"button": "ЧСЛ"}))
        keyboard.add_line()
        keyboard.add_callback_button("ЧСП", color=VkKeyboardColor.NEGATIVE, payload=json.dumps({"button": "ЧСП"}))
        keyboard.add_callback_button("ЧСС", color=VkKeyboardColor.NEGATIVE, payload=json.dumps({"button": "ЧСС"}))
        self.send(pid, f"⛔ ЧС для {self.mention(tid)}\n📋 {reason}", keyboard=keyboard)

    def process_bl_choice(self, pid, fid, choice):
        p = bl_pending.pop(fid)
        if not p:
            return self.send(pid, "❌ Нет запроса.")
        if time.time() - p["_created"] > 60:
            return self.send(pid, "⏰ Истекло.")
        tid, op, reason = p["target_id"], p["peer_id"], p["reason"]
        tr = self.format_role(pid, tid)
        tm = {"чса": "chat_admin", "чсл": "chat_local", "чсп": "full_project", "чсс": "full_strict"}
        tn = {"чса": "ЧСА", "чсл": "ЧСЛ", "чсп": "ЧСП", "чсс": "ЧСС"}
        if not self.db.add_to_blacklist(tid, op, tm[choice], fid, reason):
            return self.send(pid, "⛔ Защита ГА.")
        name = tn[choice]
        if choice in ("чса", "чсл"):
            self.db.ban_user(op, tid, fid, f"{name}: {reason}", 0)
            self.kick(op, tid)
            self.send(op, f"⛔ {self.mention(tid)} -> {name}\n📋 {reason}")
        else:
            ap = self.db.get_all_chat_peers()
            for cp in ap:
                self.db.ban_user(cp, tid, fid, f"{name}: {reason}", 0)
                self.kick(cp, tid)
            self.send(op, f"⛔ {self.mention(tid)} -> {name}\n📋 {reason}\n🌐 {len(ap)} чатов")

    def cmd_unbl(self, e, pid, fid):
        if not self.has_perm(pid, fid, "rcunbl"):
            return self.send(pid, "❌ Нет прав.")
        tid, _ = self.parse_target(e)
        if not tid:
            return self.send(pid, "❌ /rcunbl [юзер]")
        unbl_pending.set(fid, {"target_id": tid, "peer_id": pid})
        keyboard = VkKeyboard(inline=True)
        keyboard.add_callback_button("ЧСА", color=VkKeyboardColor.PRIMARY, payload=json.dumps({"button": "unbl_ЧСА"}))
        keyboard.add_callback_button("ЧСЛ", color=VkKeyboardColor.PRIMARY, payload=json.dumps({"button": "unbl_ЧСЛ"}))
        keyboard.add_line()
        keyboard.add_callback_button("ЧСП", color=VkKeyboardColor.NEGATIVE, payload=json.dumps({"button": "unbl_ЧСП"}))
        keyboard.add_callback_button("ЧСС", color=VkKeyboardColor.NEGATIVE, payload=json.dumps({"button": "unbl_ЧСС"}))
        keyboard.add_line()
        keyboard.add_callback_button("ВСЕ", color=VkKeyboardColor.POSITIVE, payload=json.dumps({"button": "unbl_ВСЕ"}))
        self.send(pid, f"🔓 Убрать {self.mention(tid)} из ЧС:", keyboard=keyboard)

    def process_unbl_choice(self, pid, fid, choice):
        p = unbl_pending.pop(fid)
        if not p:
            return self.send(pid, "❌ Нет запроса.")
        if time.time() - p["_created"] > 60:
            return self.send(pid, "⏰ Истекло.")
        tid = p["target_id"]
        tm = {"чса": "chat_admin", "чсл": "chat_local", "чсп": "full_project", "чсс": "full_strict"}
        if choice == "все":
            ok = self.db.remove_from_blacklist_global(tid)
            self.send(pid, f"✅ Убран из всех ЧС." if ok else f"❌ Не в ЧС.")
        else:
            ok = self.db.remove_from_blacklist(tid, p["peer_id"], tm[choice])
            self.send(pid, f"✅ Убран из {choice.upper()}." if ok else f"❌ Не найден.")

    def cmd_bllist(self, e, pid, fid):
        bl = self.db.get_blacklist_global()
        if not bl:
            return self.send(pid, "📋 ЧС пуст.")
        bl_types_map = {"chat_admin": "ЧСА", "chat_local": "ЧСЛ", "full_project": "ЧСП", "full_strict": "ЧСС"}
        txt = "📋 Чёрный список\n\n"
        for i, b in enumerate(bl[:30], 1):
            txt += f"{i}. {self.mention(b['user_id'])} — {bl_types_map.get(b['bl_type'], b['bl_type'])}\n   📌 {b.get('reason', '')}\n   🛡 {self.mention(b['added_by'])}\n"
        self.send(pid, txt + f"\n📊 Всего: {len(bl)}")

    def cmd_banlist(self, e, pid, fid):
        bans = self.db.get_ban_list(pid)
        if not bans:
            return self.send(pid, "📋 Банов нет.")
        txt = "📋 Баны\n\n"
        for i, b in enumerate(bans[:20], 1):
            txt += f"{i}. {self.mention(b['user_id'])} -> {self.fmt_time(b.get('ban_until', 0))}\n   📌 {b.get('reason', '')}\n   🛡 {self.mention(b['banned_by'])}\n"
        self.send(pid, txt + f"\n📊 Всего: {len(bans)}")

    def cmd_mutelist(self, e, pid, fid):
        mutes = self.db.get_mute_list(pid)
        if not mutes:
            return self.send(pid, "📋 Мутов нет.")
        txt = "📋 Муты\n\n"
        for i, m in enumerate(mutes[:20], 1):
            txt += f"{i}. {self.mention(m['user_id'])} -> {self.fmt_time(m.get('mute_until', 0))}\n   📌 {m.get('reason', '')}\n   🛡 {self.mention(m['muted_by'])}\n"
        self.send(pid, txt + f"\n📊 Всего: {len(mutes)}")

    def cmd_newrole(self, e, pid, fid):
        if not self.has_perm(pid, fid, "rcnewrole"):
            return self.send(pid, "❌ Нет прав.")
        parts = e.get("text", "").split(maxsplit=2)
        if len(parts) < 3:
            return self.send(pid, "❌ /rcnewrole [приоритет] [Эмодзи Название]")
        try:
            pr = int(parts[1])
        except ValueError:
            return self.send(pid, "❌ Число.")
        if pr < 1 or pr > 99:
            return self.send(pid, "❌ 1-99.")
        up = self.get_prio(pid, fid)
        if pr >= up:
            return self.send(pid, f"🚫 ≥ ({up}).")
        role_text = parts[2].strip()
        emoji, role_name = "", role_text
        ep = re.match(r'^([\U0001F000-\U0001F9FF\U0001FA00-\U0001FA6F\U0001FA70-\U0001FAFF\u2600-\u26FF\u2700-\u27BF])\s*(.+)$', role_text)
        if ep:
            emoji, role_name = ep.group(1), ep.group(2).strip()
        ok, msg_r = self.db.create_role(pid, role_name, pr, emoji)
        if ok:
            d = f"{emoji} {role_name} ({pr})" if emoji else f"{role_name} ({pr})"
            self.send(pid, f"✅ Роль «{d}» создана.")
        else:
            self.send(pid, f"❌ {msg_r}")

    def cmd_delrole(self, e, pid, fid):
        if not self.has_perm(pid, fid, "rcdelrole"):
            return self.send(pid, "❌ Нет прав.")
        parts = e.get("text", "").split()
        if len(parts) < 2:
            return self.send(pid, "❌ /rcdelrole [приоритет]")
        try:
            pr = int(parts[1])
        except ValueError:
            return self.send(pid, "❌ Число.")
        up = self.get_prio(pid, fid)
        if pr >= up:
            return self.send(pid, f"🚫 ≥ ({up}).")
        ok, msg_r = self.db.delete_role(pid, pr)
        self.send(pid, f"🗑 Удалена." if ok else f"❌ {msg_r}")

    def cmd_role(self, e, pid, fid):
        text = e.get("text", "")
        tid, rest = self.parse_target(e)
        if not tid and len(text.split()) <= 1:
            return self.send(pid, f"Ваша роль » {self.format_role(pid, fid)}")
        if tid and not rest.strip():
            return self.send(pid, f"Роль {self.mention(tid)} » {self.format_role(pid, tid)}")
        if not self.has_perm(pid, fid, "rcrole"):
            return self.send(pid, "❌ Нет прав.")
        if not tid:
            return self.send(pid, "❌ /rcrole [юзер] [приоритет/0]")
        if self.is_ga(tid) and not self.is_ga(fid):
            return self.send(pid, "⛔ ГА защищён.")
        try:
            pa = int(rest.strip().split()[0])
        except (ValueError, IndexError):
            return self.send(pid, "❌ Укажите приоритет.")
        up = self.get_prio(pid, fid)
        tcp = self.get_prio(pid, tid)
        if tcp >= up and not self.is_ga(fid):
            return self.send(pid, f"🚫 ({tcp}) ≥ ({up}).")
        old = self.format_role(pid, tid)
        if pa == 0:
            ok, msg_r = self.db.remove_role(pid, tid)
            if ok:
                self.send(pid, f"👾 {self.mention(tid)}\n{old} -> {self.format_role(pid, tid)}\n📌 Сменил: {self.mention(fid)}")
            else:
                self.send(pid, f"❌ {msg_r}")
            return
        if pa >= up and not self.is_ga(fid):
            return self.send(pid, f"🚫 ≥ ({up}).")
        if pa < 1 or pa > 99:
            return self.send(pid, "❌ 1-99.")
        ok, res = self.db.assign_role(pid, tid, pa)
        if ok:
            self.send(pid, f"👾 {self.mention(tid)}\n{old} -> {self.format_role(pid, tid)}\n📌 Сменил: {self.mention(fid)}")
        else:
            self.send(pid, f"❌ {res}")

    def cmd_roles(self, e, pid, fid):
        roles = self.db.get_roles(pid)
        oid = self.db.get_chat_owner(pid)
        txt = "📋 Роли чата\n\n⭐ ГА (1000)\n"
        if oid:
            alias_100 = self.db.get_role_alias(pid, 100)
            if alias_100:
                emoji = alias_100.get("alias_emoji", "") or ""
                name = alias_100.get("alias_name", "Владелец")
                txt += f"{emoji} {name} (100)\n" if emoji else f"👑 {name} (100)\n"
            else:
                txt += "👑 Владелец (100)\n"
        if roles:
            for r in roles:
                rd = dict(r)
                em = rd.get("emoji", "") or ""
                txt += f"{em} {rd['role_name']} ({rd['priority']})\n" if em else f"{rd['role_name']} ({rd['priority']})\n"
        alias_0 = self.db.get_role_alias(pid, 0)
        if alias_0:
            emoji = alias_0.get("alias_emoji", "") or ""
            name = alias_0.get("alias_name", "Пользователь")
            txt += f"{emoji} {name} (0)\n" if emoji else f"{name} (0)\n"
        else:
            txt += "Пользователь (0)\n"
        self.send(pid, txt)

    def cmd_staff(self, e, pid, fid):
        staff = self.db.get_chat_staff(pid)
        oid = self.db.get_chat_owner(pid)
        rg = {}
        gm = [self.mention(g) for g in GLOBAL_ADMINS]
        if gm:
            rg[1001] = {"d": "⭐ ГА (1000)", "u": gm}
        if oid and oid not in GLOBAL_ADMINS:
            rg[100] = {"d": "👑 Владелец (100)", "u": [self.mention(oid)]}
        for s in (staff or []):
            uid = s["user_id"]
            if uid == oid or uid in GLOBAL_ADMINS:
                continue
            p = s["priority"]
            em = s.get("emoji", "") or ""
            d = f"{em} {s['role_name']} ({p})" if em else f"{s['role_name']} ({p})"
            if p not in rg:
                rg[p] = {"d": d, "u": []}
            rg[p]["u"].append(self.mention(uid))
        if not rg:
            return self.send(pid, "👮 Пусто.")
        txt = "👮 Персонал\n\n"
        for p in sorted(rg.keys(), reverse=True):
            g = rg[p]
            txt += f"{g['d']} -> {', '.join(g['u'])}\n"
        self.send(pid, txt)

    def cmd_cmd(self, e, pid, fid):
        if not self.has_perm(pid, fid, "rccmd"):
            return self.send(pid, "❌ Только владелец.")
        parts = e.get("text", "").split()
        if len(parts) < 3:
            perms = self.db.get_all_cmd_permissions(pid)
            pt = "".join([f"  /{p['command']} — {p['min_priority']}\n" for p in perms]) or "  По умолчанию.\n"
            return self.send(pid, f"⚙️ Права\n\n{pt}\n/rccmd [cmd] [prio]")
        cn = parts[1].lower().replace("/", "")
        try:
            mp = int(parts[2])
        except ValueError:
            return self.send(pid, "❌ Число.")
        if cn not in DEFAULT_CMD_PERMISSIONS:
            return self.send(pid, f"❌ Неизвестная: {cn}")
        self.db.set_cmd_permission(pid, cn, mp)
        self.send(pid, f"✅ /{cn} — мин: {mp}")

    def cmd_top(self, e, pid, fid):
        top = self.db.get_top_msg(pid, 15)
        if not top:
            return self.send(pid, "📊 Пусто.")
        medals = {1: "🥇", 2: "🥈", 3: "🥉"}
        txt = "📊 Топ\n\n"
        for i, t in enumerate(top, 1):
            txt += f"{medals.get(i, f'{i}.')} {self.mention(t['user_id'])} — {t['count']}\n"
        self.send(pid, txt)

    def cmd_connect(self, e, pid, fid):
        if not self.has_perm(pid, fid, "rcconnect"):
            return self.send(pid, "❌ Только владелец.")
        parts = e.get("text", "").split()
        if len(parts) < 2:
            return self.send(pid, "🔗 /rcconnect create|[peer_id]|off")
        arg = parts[1].lower()
        if arg == "create":
            self.db.connect_to_pool(pid, pid)
            self.db.update_setting(pid, "connected", 1)
            self.send(pid, f"✅ Пул создан.")
        elif arg == "off":
            self.db.disconnect_from_pool(pid)
            self.db.update_setting(pid, "connected", 0)
            self.send(pid, "✅ Отключён.")
        else:
            try:
                op = int(arg)
            except ValueError:
                return self.send(pid, "❌ Число.")
            self.db.connect_to_pool(pid, op)
            self.db.update_setting(pid, "connected", 1)
            self.send(pid, f"✅ Подключён к {op}.")

    def cmd_import(self, e, pid, fid):
        if not self.has_perm(pid, fid, "rcimport"):
            return self.send(pid, "❌ Только владелец.")
        parts = e.get("text", "").split()
        if len(parts) < 2:
            code = self.db.create_import_code(pid)
            return self.send(pid, f"📦 Код: {code}\n/rcimport {code}")
        code = parts[1].strip().upper()
        src = self.db.get_import_source(code)
        if not src or src == pid:
            return self.send(pid, "❌ Неверный код.")
        if self.db.import_settings(src, pid):
            self.send(pid, f"✅ Импортировано.")
        else:
            self.send(pid, "❌ Ошибка.")

    def cmd_delmsg(self, e, pid, fid):
        if not self.has_perm(pid, fid, "rcdelmsg"):
            return self.send(pid, "❌ Нет прав.")
        parts = e.get("text", "").split()
        if len(parts) < 2:
            return self.send(pid, "❌ /rcdelmsg [1-100]")
        try:
            count = int(parts[1])
            assert 1 <= count <= 100
        except:
            return self.send(pid, "❌ 1-100.")
        try:
            msgs = self.vk.messages.getHistory(peer_id=pid, count=count+1).get("items", [])
            ids = [m["id"] for m in msgs if m["from_id"] != -self.group_id]
            if ids:
                self.vk.messages.delete(peer_id=pid, message_ids=ids, delete_for_all=1, group_id=self.group_id)
                self.send(pid, f"🗑 Удалено {len(ids)}.")
        except Exception as ex:
            self.send(pid, f"❌ {ex}")

    def cmd_msg(self, e, pid, fid):
        if not self.is_ga(fid):
            return
        parts = e.get("text", "").split(maxsplit=1)
        if len(parts) < 2:
            return self.send(pid, "❌ /rcmsg [текст]")
        text = parts[1].strip()
        all_peers = self.db.get_all_chat_peers()
        sent = 0
        for peer in all_peers:
            try:
                self.vk.messages.send(peer_id=peer, message=f"📨 {text}", random_id=random.randint(0, 2**31))
                sent += 1
            except:
                pass
        self.send(pid, f"✅ {sent}/{len(all_peers)}")

    # ============ ГЛОБАЛЬНЫЕ ============

    def cmd_gban(self, e, pid, fid):
        if not self.is_ga(fid):
            return self.send(pid, "❌ Только ГА.")
        tid, rest = self.parse_target(e)
        if not tid:
            return self.send(pid, "❌ /rcgban [юзер] [время] [причина]")
        if self.is_ga(tid):
            return self.send(pid, "⛔")
        parts = rest.split(maxsplit=1)
        if not parts:
            return self.send(pid, "❌ Время.")
        dur, ht = self.parse_dur(parts[0])
        if dur is None:
            return self.send(pid, "❌ Неверное время.")
        reason = parts[1].strip() if len(parts) > 1 else "Не указана"
        self.db.global_ban_user(tid, fid, reason, dur)
        all_peers = self.db.get_all_chat_peers()
        kicked = 0
        for peer in all_peers:
            self.db.ban_user(peer, tid, fid, f"[Глобал] {reason}", dur)
            if self.kick(peer, tid):
                kicked += 1
        self.send(pid, f"🌐 БАН: {self.mention(tid)}\n📌 {reason} | {ht}\n🌍 {kicked}/{len(all_peers)}")

    def cmd_gunban(self, e, pid, fid):
        if not self.is_ga(fid):
            return self.send(pid, "❌ Только ГА.")
        tid, _ = self.parse_target(e)
        if not tid:
            return self.send(pid, "❌ /rcgunban [юзер]")
        if self.db.global_unban_user(tid):
            for peer in self.db.get_all_chat_peers():
                self.db.unban_user(peer, tid)
            self.send(pid, f"🌐 РАЗБАН: {self.mention(tid)}")
        else:
            self.send(pid, "❌ Не в бане.")

    def cmd_gmute(self, e, pid, fid):
        if not self.is_ga(fid):
            return self.send(pid, "❌ Только ГА.")
        tid, rest = self.parse_target(e)
        if not tid:
            return self.send(pid, "❌ /rcgmute [юзер] [время] [причина]")
        if self.is_ga(tid):
            return self.send(pid, "⛔")
        parts = rest.split(maxsplit=1)
        if not parts:
            return self.send(pid, "❌ Время.")
        dur, ht = self.parse_dur(parts[0])
        if dur is None:
            return self.send(pid, "❌ Неверное время.")
        reason = parts[1].strip() if len(parts) > 1 else "Не указана"
        self.db.global_mute_user(tid, fid, reason, dur)
        all_peers = self.db.get_all_chat_peers()
        for peer in all_peers:
            self.db.mute_user(peer, tid, fid, f"[Глобал] {reason}", dur)
        self.send(pid, f"🌐 МУТ: {self.mention(tid)}\n📌 {reason} | {ht}\n🌍 {len(all_peers)}")

    def cmd_gunmute(self, e, pid, fid):
        if not self.is_ga(fid):
            return self.send(pid, "❌ Только ГА.")
        tid, _ = self.parse_target(e)
        if not tid:
            return self.send(pid, "❌ /rcgunmute [юзер]")
        if self.db.global_unmute_user(tid):
            for peer in self.db.get_all_chat_peers():
                self.db.unmute_user(peer, tid)
            self.send(pid, f"🌐 РАЗМУТ: {self.mention(tid)}")
        else:
            self.send(pid, "❌ Не в муте.")

    def cmd_gkick(self, e, pid, fid):
        if not self.is_ga(fid):
            return self.send(pid, "❌ Только ГА.")
        tid, rest = self.parse_target(e)
        if not tid:
            return self.send(pid, "❌ /rcgkick [юзер]")
        if self.is_ga(tid):
            return self.send(pid, "⛔")
        reason = rest.strip() or "Не указана"
        kicked = sum(1 for peer in self.db.get_all_chat_peers() if self.kick(peer, tid))
        self.send(pid, f"🌐 КИК: {self.mention(tid)}\n📌 {reason}\n🌍 {kicked}")

    def cmd_gvig(self, e, pid, fid):
        if not self.is_ga(fid):
            return self.send(pid, "❌ Только ГА.")
        tid, rest = self.parse_target(e)
        if not tid:
            return self.send(pid, "❌ /rcgvig [юзер] [причина]")
        if self.is_ga(tid):
            return self.send(pid, "⛔")
        reason = rest.strip() or "Не указана"
        gvig_pending.set(fid, {"target_id": tid, "peer_id": pid, "reason": reason})
        keyboard = VkKeyboard(inline=True)
        keyboard.add_callback_button("Грубый выговор", color=VkKeyboardColor.NEGATIVE, payload=json.dumps({"button": "gvig_грубый выговор"}))
        keyboard.add_line()
        keyboard.add_callback_button("Выговор", color=VkKeyboardColor.PRIMARY, payload=json.dumps({"button": "gvig_выговор"}))
        keyboard.add_line()
        keyboard.add_callback_button("Устный выговор", color=VkKeyboardColor.POSITIVE, payload=json.dumps({"button": "gvig_устный выговор"}))
        self.send(pid, f"🌐 Выговор для {self.mention(tid)}\n📋 {reason}", keyboard=keyboard)

    def process_gvig_choice(self, pid, fid, choice):
        p = gvig_pending.pop(fid)
        if not p:
            return self.send(pid, "❌ Нет запроса.")
        if time.time() - p["_created"] > 60:
            return self.send(pid, "⏰ Истекло.")
        tid, reason = p["target_id"], p["reason"]
        icons = {"грубый выговор": "🔴", "выговор": "🟡", "устный выговор": "🟢"}
        self.db.add_global_vig(tid, fid, choice, reason)
        total = len(self.db.get_global_vigs(tid))
        self.send(pid, f"🌐 {icons.get(choice,'')} {choice.title()}: {self.mention(tid)}\n📌 {reason}\n📊 Всего: {total}")

    def cmd_gunvig(self, e, pid, fid):
        if not self.is_ga(fid):
            return self.send(pid, "❌ Только ГА.")
        tid, _ = self.parse_target(e)
        if not tid:
            return self.send(pid, "❌ /rcgunvig [юзер]")
        gvigs = self.db.get_global_vigs(tid)
        if not gvigs:
            return self.send(pid, "❌ Нет глобальных выговоров.")
        icons = {"грубый выговор": "🔴", "выговор": "🟡", "устный выговор": "🟢"}
        keyboard = VkKeyboard(inline=True)
        for i, v in enumerate(gvigs[:5]):
            label = f"{icons.get(v['vig_type'], '⚠️')} {v['vig_type'].title()}"[:40]
            keyboard.add_callback_button(label, color=VkKeyboardColor.PRIMARY, payload=json.dumps({"button": f"gunvig_{v['id']}"}))
            if i < len(gvigs[:5]) - 1:
                keyboard.add_line()
        keyboard.add_line()
        keyboard.add_callback_button("🗑 Снять все", color=VkKeyboardColor.NEGATIVE, payload=json.dumps({"button": f"gunvig_all_{tid}"}))
        gunvig_pending.set(fid, {"target_id": tid})
        txt = f"🌐 Глобальные выговоры {self.mention(tid)}:\n\n"
        for i, v in enumerate(gvigs[:5], 1):
            txt += f"{i}. {icons.get(v['vig_type'], '')} {v['vig_type']} — {v['reason']}\n"
        txt += f"\n📊 Всего: {len(gvigs)}\nВыберите какой снять:"
        self.send(pid, txt, keyboard=keyboard)

    def cmd_listchat(self, e, pid, fid):
        if not self.is_ga(fid):
            return self.send(pid, "❌ Только ГА.")
        chats = self.db.get_all_chats_with_info()
        if not chats:
            return self.send(pid, "📋 Нет чатов.")
        txt = "📋 ВСЕ ЧАТЫ\n\n"
        for i, chat in enumerate(chats[:50], 1):
            txt += f"{i}. 🆔 {chat['peer_id']} | 👑 {self.mention(chat['owner_id'])}\n"
        self.send(pid, txt + f"\n📊 {len(chats)}")

    # ============ ТЕХПОДДЕРЖКА ============

    def cmd_start(self, e, pid, fid):
        if pid != fid:
            return
        open_ticket = self.db.get_open_ticket(fid)
        if open_ticket:
            return self.send(pid, f"⚠️ Обращение #{open_ticket['id']} уже открыто.")
        support_pending.set(fid, {"stage": "waiting_problem"})
        self.send(pid, "👋 Опишите проблему одним сообщением.")

    def process_support_problem(self, pid, fid, text):
        pending = support_pending.get(fid)
        if not pending or pending.get("stage") != "waiting_problem":
            return
        support_pending.set(fid, {"stage": "waiting_type", "problem_text": text})
        keyboard = VkKeyboard(inline=True)
        keyboard.add_callback_button("🖥 Сервер", color=VkKeyboardColor.PRIMARY, payload=json.dumps({"button": "support_server"}))
        keyboard.add_line()
        keyboard.add_callback_button("🤖 Бот", color=VkKeyboardColor.PRIMARY, payload=json.dumps({"button": "support_bot"}))
        keyboard.add_line()
        keyboard.add_callback_button("💳 Донат", color=VkKeyboardColor.PRIMARY, payload=json.dumps({"button": "support_donate"}))
        self.send(pid, "✅ Выберите категорию:", keyboard=keyboard)

    def handle_support_type_choice(self, pid, fid, problem_type):
        pending = support_pending.pop(fid)
        if not pending or pending.get("stage") != "waiting_type":
            return
        problem_text = pending.get("problem_text", "")
        type_names = {"server": "🖥 Сервер", "bot": "🤖 Бот", "donate": "💳 Донат"}
        ticket_id = self.db.create_ticket(fid, problem_text, problem_type)
        self.send(pid, f"✅ #{ticket_id} принято!\n📂 {type_names.get(problem_type, '?')}")
        try:
            sk = VkKeyboard(inline=True)
            sk.add_callback_button("✅ Закрыть", color=VkKeyboardColor.POSITIVE, payload=json.dumps({"button": f"support_close_{ticket_id}"}))
            self.vk.messages.send(peer_id=SUPPORT_PEER, message=f"🆘 ОБРАЩЕНИЕ #{ticket_id}\n👤 {self.mention(fid)}\n📂 {type_names.get(problem_type, '?')}\n📝 {problem_text}", keyboard=sk.get_keyboard(), random_id=random.randint(0, 2**31))
        except:
            pass

    def handle_support_reply(self, msg):
        reply = msg.get("reply_message")
        if not reply:
            return
        match = re.search(r'ОБРАЩЕНИЕ #(\d+)', reply.get("text", ""))
        if not match:
            return
        ticket_id = int(match.group(1))
        ticket = self.db.get_ticket_by_id(ticket_id)
        if not ticket or ticket['status'] != 'open':
            return
        try:
            self.vk.messages.send(peer_id=ticket['user_id'], message=f"💬 Ответ #{ticket_id}:\n{msg.get('text', '')}", random_id=random.randint(0, 2**31))
            self.send(msg['peer_id'], "✅ Отправлено.")
        except Exception as ex:
            self.send(msg['peer_id'], f"❌ {ex}")

    def handle_close_ticket(self, ticket_id, closed_by, peer_id):
        ticket = self.db.get_ticket_by_id(ticket_id)
        if not ticket or ticket['status'] == 'closed':
            return self.send(peer_id, f"❌ #{ticket_id} закрыто/не найдено.")
        self.db.close_ticket(ticket_id, closed_by)
        user_id = ticket['user_id']
        if peer_id != user_id:
            try:
                self.vk.messages.send(peer_id=user_id, message=f"✅ #{ticket_id} закрыто.", random_id=random.randint(0, 2**31))
            except:
                pass
        self.send(peer_id, f"✅ #{ticket_id} закрыто.")


def main():
    print("=" * 50)
    print("  🎮 RussianCraft Bot v2.9.0")
    print("=" * 50)
    try:
        vk_session = vk_api.VkApi(token=VK_TOKEN)
        vk = vk_session.get_api()
        longpoll = VkBotLongPoll(vk_session, GROUP_ID)
        try:
            gi = vk.groups.getById(group_id=GROUP_ID)
            print(f"  ✅ {gi[0]['name']}")
        except Exception as ex:
            print(f"  ❌ {ex}")
            return
        db = Database()
        handlers = Handlers(vk, db, GROUP_ID)
        print("  🟢 Запущен!")
        print("=" * 50)
        for event in longpoll.listen():
            if event.type == VkBotEventType.MESSAGE_NEW:
                msg = event.object.message
                try:
                    if msg.get("peer_id") == SUPPORT_PEER and msg.get("reply_message"):
                        handlers.handle_support_reply(msg)
                    else:
                        handlers.handle_message(msg)
                except Exception as ex:
                    logger.error(f"Err: {ex}")
                    traceback.print_exc()
            elif event.type == VkBotEventType.MESSAGE_EVENT:
                try:
                    eo = event.object
                    uid, pid, eid = eo.get("user_id"), eo.get("peer_id"), eo.get("event_id")
                    payload = eo.get("payload", {})
                    try:
                        vk.messages.sendMessageEventAnswer(event_id=eid, user_id=uid, peer_id=pid, event_data=json.dumps({"type": "show_snackbar", "text": "✅"}))
                    except:
                        pass
                    bt = ""
                    if isinstance(payload, dict):
                        bt = payload.get("button", "")
                    elif isinstance(payload, str):
                        try:
                            bt = json.loads(payload).get("button", "")
                        except:
                            pass
                    if not bt or not uid or not pid:
                        continue
                    btl = bt.lower().strip()
                    if bt.startswith("support_") and not bt.startswith("support_close_"):
                        handlers.handle_support_type_choice(pid, uid, bt.split("_")[1])
                    elif bt.startswith("close_ticket_"):
                        handlers.handle_close_ticket(int(bt.split("_")[2]), uid, pid)
                    elif bt.startswith("support_close_"):
                        handlers.handle_close_ticket(int(bt.split("_")[2]), uid, pid)
                    elif btl in ("чса", "чсл", "чсп", "чсс"):
                        if uid in bl_pending:
                            handlers.process_bl_choice(pid, uid, btl)
                    elif bt.startswith("unbl_"):
                        ch = bt[5:].lower().strip()
                        if uid in unbl_pending:
                            handlers.process_unbl_choice(pid, uid, ch)
                    elif bt.startswith("vig_"):
                        ch = bt[4:].lower().strip()
                        if uid in vig_pending:
                            handlers.process_vig_choice(pid, uid, ch)
                    elif bt.startswith("gvig_"):
                        ch = bt[5:].lower().strip()
                        if uid in gvig_pending:
                            handlers.process_gvig_choice(pid, uid, ch)
                    # Снятие конкретного выговора
                    elif bt.startswith("unvig_all_"):
                        parts_b = bt.split("_")
                        if len(parts_b) >= 4:
                            target_id = int(parts_b[2])
                            peer_id_v = int(parts_b[3])
                            if db.remove_vigs(peer_id_v, target_id):
                                handlers.send(pid, f"🗑 Все выговоры сняты: {handlers.mention(target_id)}")
                            else:
                                handlers.send(pid, "❌ Нет выговоров.")
                    elif bt.startswith("unvig_"):
                        vig_id = int(bt.split("_")[1])
                        vig = db.get_vig_by_id(vig_id)
                        if vig and db.remove_vig_by_id(vig_id):
                            handlers.send(pid, f"✅ Выговор #{vig_id} снят ({vig['vig_type']})")
                        else:
                            handlers.send(pid, "❌ Не найден.")
                    # Снятие глобального выговора
                    elif bt.startswith("gunvig_all_"):
                        target_id = int(bt.split("_")[2])
                        if db.remove_global_vigs(target_id):
                            handlers.send(pid, f"🌐🗑 Все глобальные выговоры сняты: {handlers.mention(target_id)}")
                        else:
                            handlers.send(pid, "❌ Нет выговоров.")
                    elif bt.startswith("gunvig_"):
                        vig_id = int(bt.split("_")[1])
                        vig = db.get_global_vig_by_id(vig_id)
                        if vig and db.remove_global_vig_by_id(vig_id):
                            handlers.send(pid, f"🌐✅ Глобальный выговор #{vig_id} снят ({vig['vig_type']})")
                        else:
                            handlers.send(pid, "❌ Не найден.")
                except Exception as ex:
                    logger.error(f"CB err: {ex}")
                    traceback.print_exc()
    except KeyboardInterrupt:
        print("\nСтоп.")
    except Exception as ex:
        logger.critical(f"Fatal: {ex}")
        traceback.print_exc()


if __name__ == "__main__":
    main()
