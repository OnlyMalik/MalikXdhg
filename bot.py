#!/usr/bin/env python3
"""
Car Parking Multiplayer Account Manager Bot (Enterprise Edition)
Author: MalikX
Features: Admin Panel, User Management, Broadcast, Blacklist,
          Logs, Bulk .txt Processing, Manual Single Account Change
"""

import sys
import asyncio

if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import os
import json
import logging
import random
import datetime
import time
from typing import Dict, Any, List, Tuple, Optional, Set
import httpx
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    constants,
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    ConversationHandler,
    filters,
)

# ==========================================
#  LOGGING SETUP
# ==========================================
LOG_FORMAT = "%(asctime)s | [%(levelname)s] | %(name)s | %(message)s"
logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)
logger = logging.getLogger("AccountManagerPro")

# ==========================================
#  CONSTANTS & CONFIGURATION
# ==========================================
BOT_TOKEN: str = os.getenv("BOT_TOKEN", "8341646052:AAFVlV1rasQPs8PIeK546QHCDZIZ5MKMdPM")
OWNER_IDS: Set[int] = {5922556939}

GAMES: Dict[str, Dict[str, str]] = {
    "1": {
        "name": "🚗 Car Parking Multiplayer",
        "short": "CPM1",
        "firebase_api_key": "AIzaSyBW1ZbMiUeDZHYUO2bY8Bfnf5rRgrQGPTM",
    },
    "2": {
        "name": "🚗 Car Parking Multiplayer 2",
        "short": "CPM2",
        "firebase_api_key": "AIzaSyCQDz9rgjgmvmFkvVfmvr2-7fT4tfrzRRQ",
    },
}

BASE_DIR: str = os.path.dirname(os.path.abspath(__file__))
STATS_FILE: str = os.path.join(BASE_DIR, "bot_stats.json")
USERS_FILE: str = os.path.join(BASE_DIR, "users.json")
ADMINS_FILE: str = os.path.join(BASE_DIR, "admins.json")
BLACKLIST_FILE: str = os.path.join(BASE_DIR, "blacklist.json")
LOGS_FILE: str = os.path.join(BASE_DIR, "activity_logs.json")
CONFIG_FILE: str = os.path.join(BASE_DIR, "bot_config.json")
OUTPUTS_DIR: str = os.path.join(BASE_DIR, "outputs")
os.makedirs(OUTPUTS_DIR, exist_ok=True)

# ==========================================
#  CONVERSATION STATES
# ==========================================
(
    SELECT_GAME,
    SET_PREFIX,
    UPLOAD_FILE,
    ADMIN_PANEL,
    BROADCAST_MSG,
    ADD_ADMIN_STATE,
    REMOVE_ADMIN_STATE,
    BLACKLIST_ADD_STATE,
    BLACKLIST_REMOVE_STATE,
    SET_NEW_PASSWORD,
    # ── Manual Change States ──
    MANUAL_SELECT_GAME,
    MANUAL_ENTER_EMAIL,
    MANUAL_ENTER_PASSWORD,
    MANUAL_ENTER_NEW_EMAIL_PREFIX,
    MANUAL_ENTER_NEW_PASSWORD,
    MANUAL_CONFIRM,
) = range(16)


# ==========================================
#  DATA MANAGER
# ==========================================
class DataManager:
    @staticmethod
    def load(filepath: str, default: Any = None) -> Any:
        if os.path.exists(filepath):
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Failed to load {filepath}: {e}")
        return default if default is not None else {}

    @staticmethod
    def save(filepath: str, data: Any) -> None:
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Failed to save {filepath}: {e}")

    @staticmethod
    def append_log(entry: Dict[str, Any]) -> None:
        logs = DataManager.load(LOGS_FILE, [])
        logs.append(entry)
        if len(logs) > 500:
            logs = logs[-500:]
        DataManager.save(LOGS_FILE, logs)


# ==========================================
#  BOT CONFIG
# ==========================================
class BotConfig:
    DEFAULTS = {
        "maintenance_mode": False,
        "max_file_size_mb": 5,
        "new_password": "111111",
        "concurrent_tasks": 3,
        "bot_name": "Account Manager PRO",
        "allow_users": False,
    }

    def __init__(self):
        stored = DataManager.load(CONFIG_FILE, {})
        self._config = {**self.DEFAULTS, **stored}

    def get(self, key: str) -> Any:
        return self._config.get(key, self.DEFAULTS.get(key))

    def set(self, key: str, value: Any) -> None:
        self._config[key] = value
        DataManager.save(CONFIG_FILE, self._config)

    def get_all(self) -> Dict[str, Any]:
        return self._config.copy()


bot_config = BotConfig()


# ==========================================
#  USER MANAGER
# ==========================================
class UserManager:
    def __init__(self):
        self._users: Dict[str, Dict[str, Any]] = DataManager.load(USERS_FILE, {})
        self._admins: Set[int] = set(DataManager.load(ADMINS_FILE, []))
        self._blacklist: Set[int] = set(DataManager.load(BLACKLIST_FILE, []))

    def register_user(self, user_id: int, name: str, username: str = "") -> None:
        uid = str(user_id)
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if uid not in self._users:
            self._users[uid] = {
                "id": user_id,
                "name": name,
                "username": username or "N/A",
                "joined": now,
                "last_seen": now,
                "total_sessions": 0,
                "total_success": 0,
                "manual_changes": 0,
            }
        else:
            self._users[uid]["last_seen"] = now
            self._users[uid]["name"] = name
        DataManager.save(USERS_FILE, self._users)

    def update_user_stats(self, user_id: int, success: int) -> None:
        uid = str(user_id)
        if uid in self._users:
            self._users[uid]["total_sessions"] += 1
            self._users[uid]["total_success"] += success
            DataManager.save(USERS_FILE, self._users)

    def increment_manual_changes(self, user_id: int) -> None:
        uid = str(user_id)
        if uid in self._users:
            self._users[uid]["manual_changes"] = (
                self._users[uid].get("manual_changes", 0) + 1
            )
            DataManager.save(USERS_FILE, self._users)

    def get_all_users(self) -> Dict[str, Dict[str, Any]]:
        return self._users

    def get_user(self, user_id: int) -> Optional[Dict[str, Any]]:
        return self._users.get(str(user_id))

    def total_users(self) -> int:
        return len(self._users)

    def add_admin(self, user_id: int) -> bool:
        if user_id not in self._admins:
            self._admins.add(user_id)
            DataManager.save(ADMINS_FILE, list(self._admins))
            return True
        return False

    def remove_admin(self, user_id: int) -> bool:
        if user_id in self._admins:
            self._admins.discard(user_id)
            DataManager.save(ADMINS_FILE, list(self._admins))
            return True
        return False

    def is_admin(self, user_id: int) -> bool:
        return user_id in OWNER_IDS or user_id in self._admins

    def get_all_admins(self) -> Set[int]:
        return self._admins | OWNER_IDS

    def blacklist_add(self, user_id: int) -> bool:
        if user_id not in self._blacklist:
            self._blacklist.add(user_id)
            DataManager.save(BLACKLIST_FILE, list(self._blacklist))
            return True
        return False

    def blacklist_remove(self, user_id: int) -> bool:
        if user_id in self._blacklist:
            self._blacklist.discard(user_id)
            DataManager.save(BLACKLIST_FILE, list(self._blacklist))
            return True
        return False

    def is_blacklisted(self, user_id: int) -> bool:
        return user_id in self._blacklist

    def get_blacklist(self) -> Set[int]:
        return self._blacklist.copy()


user_manager = UserManager()


# ==========================================
#  PERSISTENT STATISTICS
# ==========================================
class PersistentStats:
    def __init__(self, filepath: str):
        self.filepath = filepath
        self.start_time = datetime.datetime.now()
        data = DataManager.load(filepath, {})
        self.total_processed: int = data.get("total_processed", 0)
        self.total_success: int = data.get("total_success", 0)
        self.total_failed: int = data.get("total_failed", 0)
        self.manual_total: int = data.get("manual_total", 0)
        self.manual_success: int = data.get("manual_success", 0)
        self.sessions: List[Dict[str, Any]] = data.get("sessions", [])

    def save(self) -> None:
        DataManager.save(self.filepath, {
            "total_processed": self.total_processed,
            "total_success": self.total_success,
            "total_failed": self.total_failed,
            "manual_total": self.manual_total,
            "manual_success": self.manual_success,
            "sessions": self.sessions,
        })

    def add_session(
        self, success: int, failed: int, game_name: str, user_id: int
    ) -> None:
        self.total_processed += success + failed
        self.total_success += success
        self.total_failed += failed
        self.sessions.append({
            "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "game": game_name,
            "success": success,
            "failed": failed,
            "user_id": user_id,
            "type": "bulk",
        })
        if len(self.sessions) > 1000:
            self.sessions = self.sessions[-1000:]
        self.save()

    def add_manual_session(
        self, success: bool, game_name: str, user_id: int
    ) -> None:
        self.manual_total += 1
        if success:
            self.manual_success += 1
        self.sessions.append({
            "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "game": game_name,
            "success": 1 if success else 0,
            "failed": 0 if success else 1,
            "user_id": user_id,
            "type": "manual",
        })
        self.save()

    def get_uptime(self) -> str:
        delta = datetime.datetime.now() - self.start_time
        h, rem = divmod(int(delta.total_seconds()), 3600)
        m, s = divmod(rem, 60)
        return f"{h}h {m}m {s}s"

    def get_summary(self) -> str:
        bulk_rate = (
            round((self.total_success / self.total_processed) * 100, 1)
            if self.total_processed > 0 else 0
        )
        manual_rate = (
            round((self.manual_success / self.manual_total) * 100, 1)
            if self.manual_total > 0 else 0
        )
        return (
            f"📊 **System Performance Statistics**\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"⏱️ Uptime: `{self.get_uptime()}`\n\n"
            f"📦 **Bulk Processing:**\n"
            f"├ 📁 Total Processed: `{self.total_processed}`\n"
            f"├ ✅ Total Success: `{self.total_success}`\n"
            f"├ ❌ Total Failed: `{self.total_failed}`\n"
            f"└ 📈 Success Rate: `{bulk_rate}%`\n\n"
            f"✏️ **Manual Changes:**\n"
            f"├ 🔄 Total Attempts: `{self.manual_total}`\n"
            f"├ ✅ Successful: `{self.manual_success}`\n"
            f"└ 📈 Success Rate: `{manual_rate}%`\n\n"
            f"💼 Sessions Run: `{len(self.sessions)}`\n"
            f"👥 Registered Users: `{user_manager.total_users()}`\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )


stats = PersistentStats(STATS_FILE)


# ==========================================
#  DECORATORS
# ==========================================
def owner_only(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        if not user:
            return
        user_manager.register_user(user.id, user.full_name, user.username or "")
        if user.id not in OWNER_IDS:
            msg = "🚫 **Access Denied**\nOwner-level authorization required."
            if update.message:
                await update.message.reply_text(msg, parse_mode="Markdown")
            elif update.callback_query:
                await update.callback_query.answer("🚫 Owners only!", show_alert=True)
            return ConversationHandler.END
        return await func(update, context)
    return wrapper


def admin_only(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        if not user:
            return
        user_manager.register_user(user.id, user.full_name, user.username or "")

        if user_manager.is_blacklisted(user.id):
            msg = "🚫 **You have been blacklisted** from this system."
            if update.message:
                await update.message.reply_text(msg, parse_mode="Markdown")
            elif update.callback_query:
                await update.callback_query.answer(
                    "🚫 You are blacklisted!", show_alert=True
                )
            return ConversationHandler.END

        if bot_config.get("maintenance_mode") and user.id not in OWNER_IDS:
            msg = "🔧 **Bot is under maintenance.** Please try again later."
            if update.message:
                await update.message.reply_text(msg, parse_mode="Markdown")
            elif update.callback_query:
                await update.callback_query.answer(
                    "🔧 Maintenance mode!", show_alert=True
                )
            return ConversationHandler.END

        if not user_manager.is_admin(user.id):
            msg = "🚫 **Access Denied**\nYou are not an authorized admin."
            if update.message:
                await update.message.reply_text(msg, parse_mode="Markdown")
            elif update.callback_query:
                await update.callback_query.answer("🚫 Admins only!", show_alert=True)
            DataManager.append_log({
                "event": "UNAUTHORIZED_ACCESS",
                "user_id": user.id,
                "name": user.full_name,
                "time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            })
            return ConversationHandler.END
        return await func(update, context)
    return wrapper


# ==========================================
#  FIREBASE ENGINE (Async HTTPX)
# ==========================================
class FirebaseEngine:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.client = httpx.AsyncClient(timeout=15.0)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        await self.client.aclose()

    async def login(self, email: str, password: str) -> Optional[str]:
        url = (
            f"https://www.googleapis.com/identitytoolkit/v3/"
            f"relyingparty/verifyPassword?key={self.api_key}"
        )
        try:
            r = await self.client.post(
                url,
                json={
                    "email": email,
                    "password": password,
                    "returnSecureToken": True,
                },
            )
            data = r.json()
            if r.status_code == 200 and "idToken" in data:
                return data["idToken"]
            err = data.get("error", {}).get("message", "Unknown")
            logger.debug(f"Login failed [{email}]: {err}")
            return None
        except Exception as e:
            logger.error(f"Login error [{email}]: {e}")
            return None

    async def change_email(
        self, id_token: str, new_email: str
    ) -> Tuple[Optional[str], Optional[str]]:
        url = (
            f"https://identitytoolkit.googleapis.com/v1/"
            f"accounts:update?key={self.api_key}"
        )
        try:
            r = await self.client.post(
                url,
                json={
                    "idToken": id_token,
                    "email": new_email,
                    "returnSecureToken": True,
                },
            )
            if r.status_code == 200:
                data = r.json()
                return data.get("email"), data.get("idToken")
            err = r.json().get("error", {}).get("message", "Unknown")
            logger.debug(f"Email change failed: {err}")
        except Exception as e:
            logger.error(f"Email change error: {e}")
        return None, None

    async def change_password(self, id_token: str, password: str) -> bool:
        url = (
            f"https://identitytoolkit.googleapis.com/v1/"
            f"accounts:update?key={self.api_key}"
        )
        try:
            r = await self.client.post(
                url,
                json={
                    "idToken": id_token,
                    "password": password,
                    "returnSecureToken": True,
                },
            )
            return r.status_code == 200
        except Exception as e:
            logger.error(f"Password change error: {e}")
            return False


# ==========================================
#  HELPERS
# ==========================================
def generate_email(prefix: str) -> str:
    return f"{prefix.lower()}{random.randint(100000, 999999)}@gmail.com"


def build_progress_bar(current: int, total: int, length: int = 18) -> str:
    if total == 0:
        return "`" + "░" * length + "` **0%**"
    filled = int(length * current / total)
    bar = "█" * filled + "░" * (length - filled)
    pct = int(100 * current / total)
    return f"`{bar}` **{pct}%**"


def build_main_keyboard(is_admin: bool) -> InlineKeyboardMarkup:
    keyboard = [
        [
            InlineKeyboardButton(
                "📦 Bulk Changer (.txt)", callback_data="mode_bulk"
            )
        ],
        [
            InlineKeyboardButton(
                "✏️ Manual Single Change", callback_data="mode_manual"
            )
        ],
        [
            InlineKeyboardButton("📊 My Stats", callback_data="stats"),
            InlineKeyboardButton("📖 Help", callback_data="help"),
        ],
    ]
    if is_admin:
        keyboard.append([
            InlineKeyboardButton("🛡️ Admin Panel 🔐", callback_data="admin_panel")
        ])
    return InlineKeyboardMarkup(keyboard)


def build_game_keyboard(callback_prefix: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "🚗💨 Car Parking Multiplayer 1",
                callback_data=f"{callback_prefix}_game_1",
            )
        ],
        [
            InlineKeyboardButton(
                "🏎️💨 Car Parking Multiplayer 2",
                callback_data=f"{callback_prefix}_game_2",
            )
        ],
        [InlineKeyboardButton("🔙 Back to Menu", callback_data="back_main")],
    ])


def build_admin_panel_keyboard(is_owner: bool = False) -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton("👥 Users", callback_data="ap_users"),
            InlineKeyboardButton("👑 Admins", callback_data="ap_admins"),
        ],
        [
            InlineKeyboardButton("🚫 Blacklist", callback_data="ap_blacklist"),
            InlineKeyboardButton("📊 Statistics", callback_data="ap_stats"),
        ],
        [
            InlineKeyboardButton("📢 Broadcast", callback_data="ap_broadcast"),
            InlineKeyboardButton("📋 Activity Logs", callback_data="ap_logs"),
        ],
        [
            InlineKeyboardButton("⚙️ Bot Config", callback_data="ap_config"),
            InlineKeyboardButton("🔧 Maintenance", callback_data="ap_maintenance"),
        ],
    ]
    if is_owner:
        buttons.append([
            InlineKeyboardButton("➕ Add Admin", callback_data="ap_add_admin"),
            InlineKeyboardButton("➖ Remove Admin", callback_data="ap_remove_admin"),
        ])
    buttons.append([
        InlineKeyboardButton("🏠 Main Menu", callback_data="back_main")
    ])
    return InlineKeyboardMarkup(buttons)


# ==========================================
#  BULK ACCOUNT PROCESSING PIPELINE
# ==========================================
async def run_account_pipeline(
    line: str,
    engine: FirebaseEngine,
    prefix: str,
    new_password: str,
) -> Tuple[str, str, str]:
    parts = line.split(":", 1)
    if len(parts) != 2:
        return "SKIP", "", ""
    email, password = parts[0].strip(), parts[1].strip()
    if not email or not password:
        return "SKIP", "", ""

    token = await engine.login(email, password)
    if not token:
        return "LOGIN_FAIL", f"{email}:{password}", "Auth rejected"

    new_email = generate_email(prefix)
    final_email, new_token = await engine.change_email(token, new_email)
    if not final_email or not new_token:
        return "EMAIL_FAIL", f"{email}:{password}", "Email swap failed"

    ok = await engine.change_password(new_token, new_password)
    if not ok:
        return "PASSWORD_FAIL", f"{email}:{password}", "Password rotation failed"

    return "SUCCESS", f"{final_email}:{new_password}", ""


async def process_accounts(
    local_path: str,
    game: Dict[str, str],
    prefix: str,
    status_msg,
    new_password: str = "111111",
) -> Dict[str, Any]:
    results: Dict[str, Any] = {
        "success": 0,
        "login_fail": 0,
        "email_fail": 0,
        "password_fail": 0,
        "skipped": 0,
        "updated_accounts": [],
        "failed_accounts": [],
    }

    with open(local_path, "r", encoding="utf-8", errors="ignore") as f:
        lines = [l.strip() for l in f if ":" in l.strip()]

    total = len(lines)
    sem = asyncio.Semaphore(bot_config.get("concurrent_tasks"))
    last_edit = time.time()

    async with FirebaseEngine(game["firebase_api_key"]) as engine:

        async def worker(line_str: str):
            nonlocal last_edit
            async with sem:
                res, payload, remark = await run_account_pipeline(
                    line_str, engine, prefix, new_password
                )
                if res == "SUCCESS":
                    results["success"] += 1
                    results["updated_accounts"].append(payload)
                elif res == "SKIP":
                    results["skipped"] += 1
                elif res == "LOGIN_FAIL":
                    results["login_fail"] += 1
                    results["failed_accounts"].append(f"{payload} | ❌ {remark}")
                elif res == "EMAIL_FAIL":
                    results["email_fail"] += 1
                    results["failed_accounts"].append(f"{payload} | 📧 {remark}")
                elif res == "PASSWORD_FAIL":
                    results["password_fail"] += 1
                    results["failed_accounts"].append(f"{payload} | 🔐 {remark}")

                done = (
                    results["success"]
                    + results["login_fail"]
                    + results["email_fail"]
                    + results["password_fail"]
                    + results["skipped"]
                )
                now = time.time()
                if (now - last_edit) > 2.5 or done == total:
                    last_edit = now
                    bar = build_progress_bar(done, total)
                    fail_count = (
                        results["login_fail"]
                        + results["email_fail"]
                        + results["password_fail"]
                    )
                    try:
                        await status_msg.edit_text(
                            f"⚡ *Live Bulk Processing Engine*\n"
                            f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                            f"🔄 Progress: `{done}` / `{total}`\n"
                            f"✅ Success: `{results['success']}` "
                            f"│ ❌ Failed: `{fail_count}`\n"
                            f"⏭️ Skipped: `{results['skipped']}`\n"
                            f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                            f"{bar}",
                            parse_mode=constants.ParseMode.MARKDOWN,
                        )
                    except Exception:
                        pass

        await asyncio.gather(*[worker(line) for line in lines])

    return results


# ==========================================
#  MANUAL SINGLE ACCOUNT CHANGE HANDLERS
# ==========================================
@admin_only
async def manual_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    """Entry point for /manual command"""
    context.user_data.clear()
    context.user_data["mode"] = "manual"

    await update.message.reply_text(
        f"✏️ *Manual Single Account Changer*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🎯 You'll be guided through 4 simple steps\n"
        f"to update a single game account.\n\n"
        f"🎮 First, select your *target game:*",
        reply_markup=build_game_keyboard("manual"),
        parse_mode=constants.ParseMode.MARKDOWN,
    )
    return MANUAL_SELECT_GAME


async def manual_game_selected(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    """Handles game selection for manual mode"""
    query = update.callback_query
    await query.answer()

    game_id = query.data.split("_")[-1]
    game = GAMES.get(game_id)
    if not game:
        await query.message.reply_text("❌ Invalid game selection.")
        return MANUAL_SELECT_GAME

    context.user_data["game"] = game
    context.user_data["game_id"] = game_id

    await query.message.reply_text(
        f"✅ *Game:* `{game['name']}`\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📧 *Step 1 of 4 — Current Email*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Enter the *current email* of the account:\n\n"
        f"💡 Example: `player123@gmail.com`",
        parse_mode=constants.ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ Cancel", callback_data="manual_cancel")]
        ]),
    )
    return MANUAL_ENTER_EMAIL


async def manual_enter_email(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    """Receives current email"""
    email = update.message.text.strip()

    # Basic email validation
    if "@" not in email or "." not in email.split("@")[-1]:
        await update.message.reply_text(
            "❌ **Invalid email format.**\n\n"
            "Please enter a valid email address:\n"
            "💡 Example: `player123@gmail.com`",
            parse_mode=constants.ParseMode.MARKDOWN,
        )
        return MANUAL_ENTER_EMAIL

    context.user_data["current_email"] = email

    await update.message.reply_text(
        f"✅ *Email saved:* `{email}`\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🔑 *Step 2 of 4 — Current Password*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Enter the *current password* of the account:",
        parse_mode=constants.ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ Cancel", callback_data="manual_cancel")]
        ]),
    )
    return MANUAL_ENTER_PASSWORD


async def manual_enter_password(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    """Receives current password"""
    password = update.message.text.strip()

    if len(password) < 3:
        await update.message.reply_text(
            "❌ **Password too short.** Minimum 3 characters.\n\nTry again:",
            parse_mode=constants.ParseMode.MARKDOWN,
        )
        return MANUAL_ENTER_PASSWORD

    context.user_data["current_password"] = password

    await update.message.reply_text(
        f"✅ *Password saved* 🔐\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📧 *Step 3 of 4 — New Email Prefix*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Enter a *new email prefix* for the account.\n\n"
        f"💡 The bot will generate:\n"
        f"`yourprefix + 6 digits + @gmail.com`\n\n"
        f"📝 Examples: `VIP`, `PRO`, `BOSS`, `KING`\n\n"
        f"Or tap *Skip* to keep the current email.",
        parse_mode=constants.ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("⏭️ Skip — Keep Current Email", callback_data="manual_skip_email")],
            [InlineKeyboardButton("❌ Cancel", callback_data="manual_cancel")],
        ]),
    )
    return MANUAL_ENTER_NEW_EMAIL_PREFIX


async def manual_enter_new_email_prefix(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    """Receives new email prefix"""
    prefix = update.message.text.strip()

    if prefix.lower() == "skip":
        context.user_data["new_email_prefix"] = None
    elif not prefix.isalnum() or len(prefix) < 1 or len(prefix) > 10:
        await update.message.reply_text(
            "❌ **Invalid prefix.**\n\n"
            "Must be **1–10 alphanumeric characters** (A-Z, 0-9).\n\n"
            "Or type `skip` to keep the current email.",
            parse_mode=constants.ParseMode.MARKDOWN,
        )
        return MANUAL_ENTER_NEW_EMAIL_PREFIX
    else:
        context.user_data["new_email_prefix"] = prefix

    await update.message.reply_text(
        f"✅ *Email Prefix:* "
        f"`{context.user_data['new_email_prefix'] or 'Unchanged'}`\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🔑 *Step 4 of 4 — New Password*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Enter a *new password* for the account.\n\n"
        f"Or tap *Skip* to use the default:\n"
        f"`{bot_config.get('new_password')}`",
        parse_mode=constants.ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    f"⏭️ Use Default: {bot_config.get('new_password')}",
                    callback_data="manual_skip_password",
                )
            ],
            [InlineKeyboardButton("❌ Cancel", callback_data="manual_cancel")],
        ]),
    )
    return MANUAL_ENTER_NEW_PASSWORD


async def manual_enter_new_password(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    """Receives new password"""
    password = update.message.text.strip()

    if password.lower() == "skip":
        context.user_data["new_password"] = bot_config.get("new_password")
    elif len(password) < 4:
        await update.message.reply_text(
            "❌ **Password too short.** Minimum 4 characters.\n\n"
            "Or type `skip` to use default.",
            parse_mode=constants.ParseMode.MARKDOWN,
        )
        return MANUAL_ENTER_NEW_PASSWORD
    else:
        context.user_data["new_password"] = password

    return await show_manual_confirm(update, context)


async def manual_skip_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    """Handles inline skip/cancel buttons during manual flow"""
    query = update.callback_query
    await query.answer()

    if query.data == "manual_cancel":
        context.user_data.clear()
        await query.message.reply_text(
            "❌ **Manual change cancelled.**\n\nUse /start to return.",
            parse_mode=constants.ParseMode.MARKDOWN,
        )
        return ConversationHandler.END

    if query.data == "manual_skip_email":
        context.user_data["new_email_prefix"] = None
        await query.message.reply_text(
            f"✅ **Email:** Unchanged\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🔑 **Step 4 of 4**\n\n"
            f"Enter the **New Password** for the account.\n\n"
            f"Or type `skip` to use default: "
            f"`{bot_config.get('new_password')}`",
            parse_mode=constants.ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        f"⏭️ Use Default ({bot_config.get('new_password')})",
                        callback_data="manual_skip_password",
                    )
                ],
                [InlineKeyboardButton("❌ Cancel", callback_data="manual_cancel")],
            ]),
        )
        return MANUAL_ENTER_NEW_PASSWORD

    if query.data == "manual_skip_password":
        context.user_data["new_password"] = bot_config.get("new_password")
        return await show_manual_confirm_from_query(query, context)

    return MANUAL_ENTER_NEW_PASSWORD


async def show_manual_confirm(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    """Shows confirmation summary before executing manual change"""
    ud = context.user_data
    game = ud.get("game", {})
    current_email = ud.get("current_email", "N/A")
    current_pass = ud.get("current_password", "N/A")
    new_prefix = ud.get("new_email_prefix")
    new_pass = ud.get("new_password", bot_config.get("new_password"))

    preview_email = (
        generate_email(new_prefix) if new_prefix else current_email
    )
    context.user_data["preview_email"] = preview_email

    confirm_text = (
        f"📋 *Review & Confirm Change*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🎮 *Game:* `{game.get('name', 'Unknown')}`\n\n"
        f"📤 *Current Account:*\n"
        f"├ 📧 Email: `{current_email}`\n"
        f"└ 🔑 Password: `{current_pass}`\n\n"
        f"📥 *New Account Details:*\n"
        f"├ 📧 New Email: `{preview_email}`\n"
        f"└ 🔑 New Password: `{new_pass}`\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"⚠️ *Ready to execute this change?*"
    )

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Confirm & Execute 🚀", callback_data="manual_execute"),
            InlineKeyboardButton("❌ Cancel", callback_data="manual_cancel"),
        ]
    ])

    await update.message.reply_text(
        confirm_text,
        parse_mode=constants.ParseMode.MARKDOWN,
        reply_markup=keyboard,
    )
    return MANUAL_CONFIRM


async def show_manual_confirm_from_query(query, context) -> int:
    """Same confirm screen but triggered from a callback query"""
    ud = context.user_data
    game = ud.get("game", {})
    current_email = ud.get("current_email", "N/A")
    current_pass = ud.get("current_password", "N/A")
    new_prefix = ud.get("new_email_prefix")
    new_pass = ud.get("new_password", bot_config.get("new_password"))

    preview_email = (
        generate_email(new_prefix) if new_prefix else current_email
    )
    context.user_data["preview_email"] = preview_email

    confirm_text = (
        f"📋 *Review & Confirm Change*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🎮 *Game:* `{game.get('name', 'Unknown')}`\n\n"
        f"📤 *Current Account:*\n"
        f"├ 📧 Email: `{current_email}`\n"
        f"└ 🔑 Password: `{current_pass}`\n\n"
        f"📥 *New Account Details:*\n"
        f"├ 📧 New Email: `{preview_email}`\n"
        f"└ 🔑 New Password: `{new_pass}`\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"⚠️ *Ready to execute this change?*"
    )

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Confirm & Execute 🚀", callback_data="manual_execute"),
            InlineKeyboardButton("❌ Cancel", callback_data="manual_cancel"),
        ]
    ])

    await query.message.reply_text(
        confirm_text,
        parse_mode=constants.ParseMode.MARKDOWN,
        reply_markup=keyboard,
    )
    return MANUAL_CONFIRM


async def manual_execute_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    """Executes the manual account change after confirmation"""
    query = update.callback_query
    user = update.effective_user
    await query.answer()

    if query.data == "manual_cancel":
        context.user_data.clear()
        await query.message.reply_text(
            "❌ **Manual change cancelled.**",
            parse_mode=constants.ParseMode.MARKDOWN,
        )
        return ConversationHandler.END

    if query.data != "manual_execute":
        return MANUAL_CONFIRM

    ud = context.user_data
    game = ud.get("game", {})
    current_email = ud.get("current_email")
    current_password = ud.get("current_password")
    new_email_prefix = ud.get("new_email_prefix")
    new_password = ud.get("new_password", bot_config.get("new_password"))

    # ── Live processing message ──
    processing_msg = await query.message.reply_text(
        f"⚙️ **Executing Manual Change...**\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🔐 **Step 1/3:** Authenticating credentials...\n"
        f"⏳ Please wait...",
        parse_mode=constants.ParseMode.MARKDOWN,
    )

    async with FirebaseEngine(game["firebase_api_key"]) as engine:

        # ── Step 1: Login ──
        token = await engine.login(current_email, current_password)
        if not token:
            await processing_msg.edit_text(
                f"❌ **Authentication Failed!**\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"🎮 Game: `{game['name']}`\n"
                f"📧 Email: `{current_email}`\n\n"
                f"⚠️ **Reason:** Invalid credentials or account does not exist.\n\n"
                f"💡 Double-check your email and password.",
                parse_mode=constants.ParseMode.MARKDOWN,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔄 Try Again", callback_data="retry_manual")],
                    [InlineKeyboardButton("🏠 Main Menu", callback_data="back_main")],
                ]),
            )
            stats.add_manual_session(False, game["name"], user.id)
            DataManager.append_log({
                "event": "MANUAL_LOGIN_FAIL",
                "user_id": user.id,
                "name": user.full_name,
                "game": game["name"],
                "time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            })
            context.user_data.clear()
            return ConversationHandler.END

        # ── Step 2: Change Email ──
        await processing_msg.edit_text(
            f"⚙️ **Executing Manual Change...**\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"✅ **Step 1/3:** Authentication successful!\n"
            f"📧 **Step 2/3:** Swapping email address...\n"
            f"⏳ Please wait...",
            parse_mode=constants.ParseMode.MARKDOWN,
        )

        final_email = current_email
        new_token = token

        if new_email_prefix:
            new_email = generate_email(new_email_prefix)
            final_email, new_token = await engine.change_email(token, new_email)
            if not final_email or not new_token:
                await processing_msg.edit_text(
                    f"❌ **Email Change Failed!**\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                    f"🎮 Game: `{game['name']}`\n"
                    f"📧 Original: `{current_email}`\n\n"
                    f"⚠️ **Reason:** Email already in use or Firebase rejected the request.\n\n"
                    f"💡 Try a different prefix.",
                    parse_mode=constants.ParseMode.MARKDOWN,
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("🏠 Main Menu", callback_data="back_main")]
                    ]),
                )
                stats.add_manual_session(False, game["name"], user.id)
                context.user_data.clear()
                return ConversationHandler.END

        # ── Step 3: Change Password ──
        await processing_msg.edit_text(
            f"⚙️ **Executing Manual Change...**\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"✅ **Step 1/3:** Authentication successful!\n"
            f"✅ **Step 2/3:** Email updated!\n"
            f"🔑 **Step 3/3:** Rotating password...\n"
            f"⏳ Almost done...",
            parse_mode=constants.ParseMode.MARKDOWN,
        )

        pw_ok = await engine.change_password(new_token, new_password)

    if pw_ok:
        # ── SUCCESS ──
        stats.add_manual_session(True, game["name"], user.id)
        user_manager.increment_manual_changes(user.id)
        DataManager.append_log({
            "event": "MANUAL_SUCCESS",
            "user_id": user.id,
            "name": user.full_name,
            "game": game["name"],
            "new_email": final_email,
            "time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        })

        await processing_msg.edit_text(
            f"🎉 **Manual Change Successful!**\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"🎮 **Game:** `{game['name']}`\n\n"
            f"📤 **Old Account:**\n"
            f"├ 📧 `{current_email}`\n"
            f"└ 🔑 `{current_password}`\n\n"
            f"📥 **New Account:**\n"
            f"├ 📧 `{final_email}`\n"
            f"└ 🔑 `{new_password}`\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"✅ All 3 steps completed successfully!\n"
            f"🔄 Use /start or /manual for another change.",
            parse_mode=constants.ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✏️ Change Another", callback_data="retry_manual")],
                [InlineKeyboardButton("🏠 Main Menu", callback_data="back_main")],
            ]),
        )

        # ── Send result as text file too ──
        result_text = (
            f"# Manual Change Result\n"
            f"# Game: {game['name']}\n"
            f"# Date: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"# Changed by: {user.full_name} ({user.id})\n"
            f"# {'=' * 40}\n\n"
            f"OLD: {current_email}:{current_password}\n"
            f"NEW: {final_email}:{new_password}\n"
        )
        result_bytes = result_text.encode("utf-8")
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

        import io
        await query.message.reply_document(
            document=io.BytesIO(result_bytes),
            filename=f"manual_result_{timestamp}.txt",
            caption=(
                f"📄 **Manual change result saved.**\n"
                f"✅ `{final_email}:{new_password}`"
            ),
            parse_mode=constants.ParseMode.MARKDOWN,
        )

    else:
        # ── PASSWORD FAIL ──
        stats.add_manual_session(False, game["name"], user.id)
        await processing_msg.edit_text(
            f"❌ **Password Change Failed!**\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"✅ Login: Successful\n"
            f"✅ Email Swap: `{final_email}`\n"
            f"❌ Password Rotation: Failed\n\n"
            f"⚠️ Firebase rejected the password update.\n"
            f"💡 Try again or contact support.",
            parse_mode=constants.ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🏠 Main Menu", callback_data="back_main")]
            ]),
        )

    context.user_data.clear()
    return ConversationHandler.END


# ==========================================
#  ADMIN PANEL HANDLERS
# ==========================================
@owner_only
async def admin_panel_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    user = update.effective_user
    is_owner = user.id in OWNER_IDS
    await update.message.reply_text(
        f"🛡️ *Admin Control Panel*\n"
        f"╔══════════════════════════╗\n"
        f"║  👤 {user.full_name[:20]:<20}  ║\n"
        f"║  🎖️ Role: {'Owner' if is_owner else 'Admin':<18}  ║\n"
        f"║  🕐 {datetime.datetime.now().strftime('%Y-%m-%d %H:%M'):<20}  ║\n"
        f"╚══════════════════════════╝\n\n"
        f"Select an option below 👇",
        reply_markup=build_admin_panel_keyboard(is_owner),
        parse_mode=constants.ParseMode.MARKDOWN,
    )
    return ADMIN_PANEL


async def admin_panel_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    query = update.callback_query
    user = update.effective_user
    await query.answer()

    if not user_manager.is_admin(user.id):
        await query.answer("🚫 Admins only!", show_alert=True)
        return ADMIN_PANEL

    data = query.data
    is_owner = user.id in OWNER_IDS

    if data == "ap_users":
        all_users = user_manager.get_all_users()
        if not all_users:
            text = "👥 **Registered Users**\n\nNo users registered yet."
        else:
            lines = [
                f"👤 **Registered Users** (`{len(all_users)}`)\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━"
            ]
            for uid, u in list(all_users.items())[-15:]:
                badge = (
                    "👑" if int(uid) in OWNER_IDS
                    else ("🛡️" if user_manager.is_admin(int(uid)) else "👤")
                )
                lines.append(
                    f"{badge} `{u['id']}` — **{u['name']}**\n"
                    f"   📅 `{u['joined']}`\n"
                    f"   ✅ Sessions: `{u['total_sessions']}` "
                    f"| ✏️ Manual: `{u.get('manual_changes', 0)}`"
                )
            text = "\n\n".join(lines)
        await query.message.reply_text(
            text,
            parse_mode=constants.ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Back", callback_data="back_admin")]
            ]),
        )
        return ADMIN_PANEL

    if data == "ap_admins":
        admins = user_manager.get_all_admins()
        lines = [
            f"👑 **Admin Registry** (`{len(admins)}`)\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━"
        ]
        for aid in admins:
            role = "👑 Owner" if aid in OWNER_IDS else "🛡️ Admin"
            u = user_manager.get_user(aid)
            name = u["name"] if u else "Unknown"
            lines.append(f"{role} — `{aid}` | **{name}**")
        await query.message.reply_text(
            "\n".join(lines),
            parse_mode=constants.ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("➕ Add Admin", callback_data="ap_add_admin"),
                    InlineKeyboardButton("➖ Remove Admin", callback_data="ap_remove_admin"),
                ],
                [InlineKeyboardButton("🔙 Back", callback_data="back_admin")],
            ]) if is_owner else InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Back", callback_data="back_admin")]
            ]),
        )
        return ADMIN_PANEL

    if data == "ap_blacklist":
        bl = user_manager.get_blacklist()
        if not bl:
            text = "🚫 **Blacklist**\n\nNo users blacklisted."
        else:
            lines = [
                f"🚫 **Blacklisted Users** (`{len(bl)}`)\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━"
            ]
            for bid in bl:
                u = user_manager.get_user(bid)
                name = u["name"] if u else "Unknown"
                lines.append(f"• `{bid}` — **{name}**")
            text = "\n".join(lines)
        await query.message.reply_text(
            text,
            parse_mode=constants.ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("➕ Ban User", callback_data="ap_blacklist_add"),
                    InlineKeyboardButton("➖ Unban User", callback_data="ap_blacklist_remove"),
                ],
                [InlineKeyboardButton("🔙 Back", callback_data="back_admin")],
            ]),
        )
        return ADMIN_PANEL

    if data == "ap_blacklist_add":
        await query.message.reply_text(
            "🚫 **Ban User**\n\nSend the **User ID** to blacklist:",
            parse_mode=constants.ParseMode.MARKDOWN,
        )
        return BLACKLIST_ADD_STATE

    if data == "ap_blacklist_remove":
        await query.message.reply_text(
            "✅ **Unban User**\n\nSend the **User ID** to unban:",
            parse_mode=constants.ParseMode.MARKDOWN,
        )
        return BLACKLIST_REMOVE_STATE

    if data == "ap_stats":
        recent = stats.sessions[-5:] if stats.sessions else []
        recent_text = ""
        for s in reversed(recent):
            icon = "✏️" if s.get("type") == "manual" else "📦"
            recent_text += (
                f"\n{icon} `{s['timestamp']}` | {s['game']}\n"
                f"  ✅ {s['success']} | ❌ {s['failed']}"
            )
        await query.message.reply_text(
            f"{stats.get_summary()}\n\n"
            f"🕐 **Recent Sessions:**{recent_text or ' None.'}",
            parse_mode=constants.ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Back", callback_data="back_admin")]
            ]),
        )
        return ADMIN_PANEL

    if data == "ap_broadcast":
        if not is_owner:
            await query.answer("👑 Owner only!", show_alert=True)
            return ADMIN_PANEL
        await query.message.reply_text(
            "📢 **Broadcast Message**\n\n"
            "Type the message to send to **all registered users**:",
            parse_mode=constants.ParseMode.MARKDOWN,
        )
        return BROADCAST_MSG

    if data == "ap_logs":
        logs_data = DataManager.load(LOGS_FILE, [])
        if not logs_data:
            text = "📋 **Activity Logs**\n\nNo logs yet."
        else:
            lines = [
                f"📋 **Recent Logs** (last {min(10, len(logs_data))})\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━"
            ]
            for log in reversed(logs_data[-10:]):
                lines.append(
                    f"🔹 `{log.get('time', 'N/A')}` | **{log.get('event', 'N/A')}**\n"
                    f"   `{log.get('user_id', 'N/A')}` — {log.get('name', 'N/A')}"
                )
            text = "\n\n".join(lines)
        await query.message.reply_text(
            text,
            parse_mode=constants.ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("🗑️ Clear Logs", callback_data="ap_clear_logs"),
                    InlineKeyboardButton("🔙 Back", callback_data="back_admin"),
                ]
            ]),
        )
        return ADMIN_PANEL

    if data == "ap_clear_logs":
        if not is_owner:
            await query.answer("👑 Owner only!", show_alert=True)
            return ADMIN_PANEL
        DataManager.save(LOGS_FILE, [])
        await query.answer("🗑️ Logs cleared!", show_alert=True)
        return ADMIN_PANEL

    if data == "ap_config":
        cfg = bot_config.get_all()
        await query.message.reply_text(
            f"⚙️ **Bot Configuration**\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🔑 Default Password: `{cfg['new_password']}`\n"
            f"📁 Max File Size: `{cfg['max_file_size_mb']} MB`\n"
            f"⚡ Concurrent Tasks: `{cfg['concurrent_tasks']}`\n"
            f"🔧 Maintenance: `{'ON 🔴' if cfg['maintenance_mode'] else 'OFF 🟢'}`\n"
            f"👥 Allow Users: `{'Yes ✅' if cfg['allow_users'] else 'No ❌'}`\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━",
            parse_mode=constants.ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔑 Change Default Password", callback_data="ap_set_password")],
                [InlineKeyboardButton("👥 Toggle User Access", callback_data="ap_toggle_users")],
                [InlineKeyboardButton("🔙 Back", callback_data="back_admin")],
            ]),
        )
        return ADMIN_PANEL

    if data == "ap_toggle_users":
        if not is_owner:
            await query.answer("👑 Owner only!", show_alert=True)
            return ADMIN_PANEL
        current = bot_config.get("allow_users")
        bot_config.set("allow_users", not current)
        await query.answer(
            f"User access {'✅ Enabled' if not current else '❌ Disabled'}",
            show_alert=True,
        )
        return ADMIN_PANEL

    if data == "ap_set_password":
        if not is_owner:
            await query.answer("👑 Owner only!", show_alert=True)
            return ADMIN_PANEL
        await query.message.reply_text(
            "🔑 **Set Default Password**\n\nSend the new default password:",
            parse_mode=constants.ParseMode.MARKDOWN,
        )
        return SET_NEW_PASSWORD

    if data == "ap_maintenance":
        if not is_owner:
            await query.answer("👑 Owner only!", show_alert=True)
            return ADMIN_PANEL
        current = bot_config.get("maintenance_mode")
        bot_config.set("maintenance_mode", not current)
        state = "🔴 ON" if not current else "🟢 OFF"
        await query.answer(f"Maintenance: {state}", show_alert=True)
        DataManager.append_log({
            "event": "MAINTENANCE_TOGGLED",
            "user_id": user.id,
            "name": user.full_name,
            "state": not current,
            "time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        })
        return ADMIN_PANEL

    if data == "ap_add_admin":
        if not is_owner:
            await query.answer("👑 Owner only!", show_alert=True)
            return ADMIN_PANEL
        await query.message.reply_text(
            "➕ **Add Admin**\n\nSend the **User ID** to promote:",
            parse_mode=constants.ParseMode.MARKDOWN,
        )
        return ADD_ADMIN_STATE

    if data == "ap_remove_admin":
        if not is_owner:
            await query.answer("👑 Owner only!", show_alert=True)
            return ADMIN_PANEL
        await query.message.reply_text(
            "➖ **Remove Admin**\n\nSend the **User ID** to demote:",
            parse_mode=constants.ParseMode.MARKDOWN,
        )
        return REMOVE_ADMIN_STATE

    if data == "back_admin":
        await query.message.edit_text(
            f"🛡️ **Admin Control Panel**\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 **{user.full_name}**\n"
            f"🔑 Role: `{'Owner' if is_owner else 'Admin'}`\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"Select an option:",
            reply_markup=build_admin_panel_keyboard(is_owner),
            parse_mode=constants.ParseMode.MARKDOWN,
        )
        return ADMIN_PANEL

    return ADMIN_PANEL


async def handle_add_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    if user.id not in OWNER_IDS:
        return ADMIN_PANEL
    try:
        target_id = int(update.message.text.strip())
        if target_id in OWNER_IDS:
            await update.message.reply_text("⚠️ This user is already an Owner.")
            return ADMIN_PANEL
        if user_manager.add_admin(target_id):
            DataManager.append_log({
                "event": "ADMIN_ADDED", "by": user.id,
                "target": target_id, "name": user.full_name,
                "time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            })
            await update.message.reply_text(
                f"✅ **Admin Added**\n\n`{target_id}` is now an admin.",
                parse_mode=constants.ParseMode.MARKDOWN,
            )
        else:
            await update.message.reply_text(f"⚠️ `{target_id}` is already an admin.")
    except ValueError:
        await update.message.reply_text("❌ Invalid numeric User ID.")
    return ADMIN_PANEL


async def handle_remove_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    if user.id not in OWNER_IDS:
        return ADMIN_PANEL
    try:
        target_id = int(update.message.text.strip())
        if target_id in OWNER_IDS:
            await update.message.reply_text("🚫 Cannot demote an Owner.")
            return ADMIN_PANEL
        if user_manager.remove_admin(target_id):
            DataManager.append_log({
                "event": "ADMIN_REMOVED", "by": user.id,
                "target": target_id, "name": user.full_name,
                "time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            })
            await update.message.reply_text(
                f"✅ **Demoted**\n\n`{target_id}` is no longer an admin.",
                parse_mode=constants.ParseMode.MARKDOWN,
            )
        else:
            await update.message.reply_text(f"⚠️ `{target_id}` is not an admin.")
    except ValueError:
        await update.message.reply_text("❌ Invalid User ID.")
    return ADMIN_PANEL


async def handle_blacklist_add(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    if not user_manager.is_admin(user.id):
        return ADMIN_PANEL
    try:
        target_id = int(update.message.text.strip())
        if target_id in OWNER_IDS:
            await update.message.reply_text("🚫 Cannot ban an Owner.")
            return ADMIN_PANEL
        if user_manager.blacklist_add(target_id):
            DataManager.append_log({
                "event": "USER_BLACKLISTED", "by": user.id,
                "target": target_id, "name": user.full_name,
                "time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            })
            await update.message.reply_text(
                f"🚫 **Banned**\n\n`{target_id}` has been blacklisted.",
                parse_mode=constants.ParseMode.MARKDOWN,
            )
        else:
            await update.message.reply_text(f"⚠️ `{target_id}` is already banned.")
    except ValueError:
        await update.message.reply_text("❌ Invalid User ID.")
    return ADMIN_PANEL


async def handle_blacklist_remove(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    if not user_manager.is_admin(user.id):
        return ADMIN_PANEL
    try:
        target_id = int(update.message.text.strip())
        if user_manager.blacklist_remove(target_id):
            await update.message.reply_text(
                f"✅ **Unbanned**\n\n`{target_id}` removed from blacklist.",
                parse_mode=constants.ParseMode.MARKDOWN,
            )
        else:
            await update.message.reply_text(f"⚠️ `{target_id}` is not banned.")
    except ValueError:
        await update.message.reply_text("❌ Invalid User ID.")
    return ADMIN_PANEL


async def handle_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    if user.id not in OWNER_IDS:
        return ADMIN_PANEL
    message_text = update.message.text.strip()
    all_users = user_manager.get_all_users()
    sent, failed = 0, 0

    progress = await update.message.reply_text(
        f"📢 Broadcasting to `{len(all_users)}` users...",
        parse_mode=constants.ParseMode.MARKDOWN,
    )
    for uid in all_users.keys():
        try:
            await context.bot.send_message(
                chat_id=int(uid),
                text=f"📢 **System Broadcast**\n\n{message_text}",
                parse_mode=constants.ParseMode.MARKDOWN,
            )
            sent += 1
            await asyncio.sleep(0.05)
        except Exception:
            failed += 1

    DataManager.append_log({
        "event": "BROADCAST_SENT", "by": user.id,
        "name": user.full_name, "sent": sent, "failed": failed,
        "time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    })
    await progress.edit_text(
        f"📢 **Broadcast Complete**\n\n✅ Sent: `{sent}` | ❌ Failed: `{failed}`",
        parse_mode=constants.ParseMode.MARKDOWN,
    )
    return ADMIN_PANEL


async def handle_set_password(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    if user.id not in OWNER_IDS:
        return ADMIN_PANEL
    new_pw = update.message.text.strip()
    if len(new_pw) < 4:
        await update.message.reply_text("❌ Minimum 4 characters.")
        return SET_NEW_PASSWORD
    bot_config.set("new_password", new_pw)
    await update.message.reply_text(
        f"✅ **Default password updated:** `{new_pw}`",
        parse_mode=constants.ParseMode.MARKDOWN,
    )
    return ADMIN_PANEL


# ==========================================
#  MAIN BOT HANDLERS
# ==========================================
@admin_only
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    user_manager.register_user(user.id, user.full_name, user.username or "")
    is_admin = user_manager.is_admin(user.id)

    DataManager.append_log({
        "event": "START", "user_id": user.id, "name": user.full_name,
        "time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    })

    role_badge = "👑 Owner" if user.id in OWNER_IDS else "🛡️ Admin"
    await update.message.reply_text(
        f"╔══════════════════════════╗\n"
        f"║  🚗 *Account Manager PRO* 🚗  ║\n"
        f"╚══════════════════════════╝\n\n"
        f"👋 Hey, *{user.full_name}*!\n"
        f"🎖️ Role: `{role_badge}`\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"⚡ *Choose Your Operation:*\n\n"
        f"📦 *Bulk Changer* — Process hundreds of\n"
        f"   accounts at once via `.txt` upload\n\n"
        f"✏️ *Manual Changer* — Precisely update\n"
        f"   a single account step-by-step\n\n"
        f"📊 *Stats* — View performance metrics\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"💡 Use /help for full command list",
        reply_markup=build_main_keyboard(is_admin),
        parse_mode=constants.ParseMode.MARKDOWN,
    )
    return SELECT_GAME


@admin_only
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    user = update.effective_user
    await query.answer()

    # ── Mode Selection ──
    if query.data == "mode_bulk":
        await query.message.reply_text(
            "📦 *Bulk Changer Mode*\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "🎯 Upload a `.txt` file with accounts in\n"
            "`email:password` format — one per line.\n\n"
            "🎮 First, select your *target game:*",
            reply_markup=build_game_keyboard("bulk"),
            parse_mode=constants.ParseMode.MARKDOWN,
        )
        return SELECT_GAME

    if query.data == "mode_manual":
        context.user_data.clear()
        context.user_data["mode"] = "manual"
        await query.message.reply_text(
            "✏️ *Manual Single Account Changer*\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "🔍 Change one account with full control\n"
            "over email prefix and password.\n\n"
            "🎮 Select your *target game:*",
            reply_markup=build_game_keyboard("manual"),
            parse_mode=constants.ParseMode.MARKDOWN,
        )
        return MANUAL_SELECT_GAME

    # ── Bulk Game Selection ──
    if query.data.startswith("bulk_game_"):
        game_id = query.data.split("_")[-1]
        game = GAMES.get(game_id)
        if not game:
            await query.message.reply_text("❌ Invalid game.")
            return SELECT_GAME
        context.user_data["game"] = game
        context.user_data["game_id"] = game_id
        await query.message.reply_text(
            f"✅ *Game Selected:* `{game['name']}`\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🏷️ *Enter an Email Prefix* (1–10 chars)\n\n"
            f"💡 This becomes part of the new email:\n"
            f"`yourprefix + 6 digits @gmail.com`\n\n"
            f"📝 Examples: `VIP`, `PRO`, `KING`, `BOSS`",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Back to Menu", callback_data="back_main")]
            ]),
            parse_mode=constants.ParseMode.MARKDOWN,
        )
        return SET_PREFIX

    # ── Admin Panel from main menu ──
    if query.data == "admin_panel":
        if not user_manager.is_admin(user.id):
            await query.answer("🚫 Not authorized!", show_alert=True)
            return SELECT_GAME
        is_owner = user.id in OWNER_IDS
        await query.message.reply_text(
            f"🛡️ **Admin Control Panel**\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 **{user.full_name}**\n"
            f"🔑 Role: `{'Owner' if is_owner else 'Admin'}`\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"Select an option:",
            reply_markup=build_admin_panel_keyboard(is_owner),
            parse_mode=constants.ParseMode.MARKDOWN,
        )
        return ADMIN_PANEL

    if query.data == "stats":
        await query.message.reply_text(
            stats.get_summary(), parse_mode=constants.ParseMode.MARKDOWN
        )
        return SELECT_GAME

    if query.data == "help":
        await query.message.reply_text(
            "📖 *How To Use Account Manager PRO*\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "📦 *Bulk Mode:*\n"
            "1️⃣ Tap *Bulk Changer*\n"
            "2️⃣ Select game & enter prefix\n"
            "3️⃣ Upload `.txt` file (`email:pass` per line)\n"
            "4️⃣ Get live results + output files 📁\n\n"
            "✏️ *Manual Mode:*\n"
            "1️⃣ Tap *Manual Single Change*\n"
            "2️⃣ Select game\n"
            "3️⃣ Enter current email\n"
            "4️⃣ Enter current password\n"
            "5️⃣ Enter new email prefix (or skip)\n"
            "6️⃣ Enter new password (or skip)\n"
            "7️⃣ Confirm & execute! 🚀\n\n"
            "📌 *Commands:*\n"
            "├ `/start` — 🏠 Main menu\n"
            "├ `/manual` — ✏️ Manual changer\n"
            "├ `/admin` — 🛡️ Admin panel\n"
            "├ `/stats` — 📊 Statistics\n"
            "├ `/id` — 🪪 Your info\n"
            "└ `/cancel` — ❌ Cancel current op\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "💬 Contact admin for support.",
            parse_mode=constants.ParseMode.MARKDOWN,
        )
        return SELECT_GAME

    if query.data == "back_main":
        context.user_data.clear()
        is_admin = user_manager.is_admin(user.id)
        await query.message.edit_text(
            "🚗 *Account Manager PRO*\n\n⚡ Select your operation:",
            reply_markup=build_main_keyboard(is_admin),
            parse_mode=constants.ParseMode.MARKDOWN,
        )
        return SELECT_GAME

    # ── Retry Manual ──
    if query.data == "retry_manual":
        context.user_data.clear()
        context.user_data["mode"] = "manual"
        await query.message.reply_text(
            "✏️ **Manual Single Account Changer**\n\n🎮 Select game:",
            reply_markup=build_game_keyboard("manual"),
            parse_mode=constants.ParseMode.MARKDOWN,
        )
        return MANUAL_SELECT_GAME

    return SELECT_GAME


@admin_only
async def handle_prefix(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    prefix = update.message.text.strip()
    if not (1 <= len(prefix) <= 10) or not prefix.isalnum():
        await update.message.reply_text(
            "❌ **Invalid prefix.** Must be 1–10 alphanumeric characters.",
            parse_mode=constants.ParseMode.MARKDOWN,
        )
        return SET_PREFIX
    context.user_data["prefix"] = prefix
    game = context.user_data.get("game", {})
    pw = bot_config.get("new_password")
    await update.message.reply_text(
        f"✅ **Prefix:** `{prefix}`\n\n"
        f"📋 **Manifest:**\n"
        f"├ 🎮 Game: `{game.get('name', 'Unknown')}`\n"
        f"├ ⚙️ Prefix: `{prefix}`\n"
        f"└ 🔑 New Password: `{pw}`\n\n"
        f"📂 Upload your `.txt` file\n"
        f"📝 Format: `email:password` per line",
        parse_mode=constants.ParseMode.MARKDOWN,
    )
    return UPLOAD_FILE


@admin_only
async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    if "game" not in context.user_data:
        await update.message.reply_text("❌ Session expired. Use `/start`.")
        return ConversationHandler.END

    doc = update.message.document
    max_mb = bot_config.get("max_file_size_mb")

    if not doc or not doc.file_name.lower().endswith(".txt"):
        await update.message.reply_text("❌ Only `.txt` files accepted.")
        return UPLOAD_FILE

    if doc.file_size > max_mb * 1024 * 1024:
        await update.message.reply_text(
            f"❌ File too large! Max: **{max_mb}MB**",
            parse_mode=constants.ParseMode.MARKDOWN,
        )
        return UPLOAD_FILE

    game = context.user_data["game"]
    prefix = context.user_data.get("prefix", "CUSTOM")
    new_password = bot_config.get("new_password")
    temp_path = os.path.join(BASE_DIR, f"temp_{user.id}_{int(time.time())}.txt")

    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id,
        action=constants.ChatAction.TYPING,
    )

    tg_file = await context.bot.get_file(doc.file_id)
    await tg_file.download_to_drive(temp_path)

    try:
        with open(temp_path, "r", encoding="utf-8", errors="ignore") as f:
            total = sum(1 for l in f if ":" in l.strip())
    except Exception:
        await update.message.reply_text("❌ Failed to read file.")
        if os.path.exists(temp_path):
            os.remove(temp_path)
        return UPLOAD_FILE

    if total == 0:
        await update.message.reply_text("❌ No valid `email:password` lines found.")
        if os.path.exists(temp_path):
            os.remove(temp_path)
        return UPLOAD_FILE

    DataManager.append_log({
        "event": "BULK_FILE_UPLOADED", "user_id": user.id,
        "name": user.full_name, "game": game["name"], "lines": total,
        "time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    })

    status_msg = await update.message.reply_text(
        f"🚀 *Bulk Engine Initialized!*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🎮 Game: `{game['name']}`\n"
        f"🏷️ Prefix: `{prefix}`\n"
        f"🔑 New Password: `{new_password}`\n"
        f"📋 Total Accounts: `{total}`\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"⚡ Processing... Please wait ⏳",
        parse_mode=constants.ParseMode.MARKDOWN,
    )

    start_time = time.time()
    try:
        results = await process_accounts(temp_path, game, prefix, status_msg, new_password)
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)

    elapsed = round(time.time() - start_time, 2)
    total_failed = results["login_fail"] + results["email_fail"] + results["password_fail"]

    stats.add_session(results["success"], total_failed, game["name"], user.id)
    user_manager.update_user_stats(user.id, results["success"])

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

    if results["updated_accounts"]:
        suc_path = os.path.join(OUTPUTS_DIR, f"success_{prefix}_{timestamp}.txt")
        with open(suc_path, "w", encoding="utf-8") as f:
            f.write(
                f"# SUCCESS LOG | Game: {game['name']}\n"
                f"# Date: {timestamp} | Count: {len(results['updated_accounts'])}\n\n"
            )
            f.write("\n".join(results["updated_accounts"]))
        with open(suc_path, "rb") as f:
            await update.message.reply_document(
                f, filename=f"success_{prefix}_{timestamp}.txt",
                caption=f"✅ **{len(results['updated_accounts'])} accounts updated!**",
                parse_mode=constants.ParseMode.MARKDOWN,
            )
        os.remove(suc_path)

    if results["failed_accounts"]:
        fail_path = os.path.join(OUTPUTS_DIR, f"failed_{prefix}_{timestamp}.txt")
        with open(fail_path, "w", encoding="utf-8") as f:
            f.write(
                f"# FAILED LOG | Game: {game['name']}\n"
                f"# Date: {timestamp} | Count: {len(results['failed_accounts'])}\n\n"
            )
            f.write("\n".join(results["failed_accounts"]))
        with open(fail_path, "rb") as f:
            await update.message.reply_document(
                f, filename=f"failed_{prefix}_{timestamp}.txt",
                caption=f"❌ **{len(results['failed_accounts'])} failed accounts logged.**",
                parse_mode=constants.ParseMode.MARKDOWN,
            )
        os.remove(fail_path)

    total_eff = results["success"] + total_failed
    rate = round((results["success"] / total_eff) * 100, 1) if total_eff > 0 else 0.0

    await status_msg.edit_text(
        f"🏁 *Bulk Processing Complete!* 🎉\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🎮 Game: `{game['name']}`\n"
        f"⏱️ Time: `{elapsed}s` │ 🎯 Rate: `{rate}%`\n\n"
        f"📊 *Final Results:*\n"
        f"├ ✅ Updated:    `{results['success']}`\n"
        f"├ 🔐 Login Fail: `{results['login_fail']}`\n"
        f"├ 📧 Email Fail: `{results['email_fail']}`\n"
        f"├ ⚙️ Pass Fail:  `{results['password_fail']}`\n"
        f"└ ⏭️ Skipped:    `{results['skipped']}`\n\n"
        f"{build_progress_bar(total_eff, total_eff)}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🔄 Use /start for more operations.",
        parse_mode=constants.ParseMode.MARKDOWN,
    )

    DataManager.append_log({
        "event": "BULK_DONE", "user_id": user.id, "name": user.full_name,
        "game": game["name"], "success": results["success"], "failed": total_failed,
        "time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    })
    return ConversationHandler.END


async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    await update.message.reply_text(
        "🚫 *Operation Cancelled*\n\n"
        "No changes were made. Use /start to begin again. 🏠",
        parse_mode=constants.ParseMode.MARKDOWN,
    )
    return ConversationHandler.END


@owner_only
async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        stats.get_summary(), parse_mode=constants.ParseMode.MARKDOWN
    )


async def id_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not user:
        return
    u_data = user_manager.get_user(user.id)
    role = (
        "👑 Owner" if user.id in OWNER_IDS
        else ("🛡️ Admin" if user_manager.is_admin(user.id) else "👤 User")
    )
    await update.message.reply_text(
        f"🪪 *Your Account Info*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🆔 ID: `{user.id}`\n"
        f"📛 Name: *{user.full_name}*\n"
        f"🎖️ Role: `{role}`\n"
        f"🚫 Blacklisted: `{'⛔ Yes' if user_manager.is_blacklisted(user.id) else '✅ No'}`\n"
        f"📦 Bulk Sessions: `{u_data.get('total_sessions', 0) if u_data else 0}`\n"
        f"✏️ Manual Changes: `{u_data.get('manual_changes', 0) if u_data else 0}`\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━",
        parse_mode=constants.ParseMode.MARKDOWN,
    )


# ==========================================
#  ENTRYPOINT
# ==========================================
def main() -> None:
    if BOT_TOKEN == "8341646052:AAFVlV1rasQPs8PIeK546QHCDZIZ5MKMdPM":
        logger.critical("BOT_TOKEN not set!")
        sys.exit("Set BOT_TOKEN environment variable.")

    app = Application.builder().token(BOT_TOKEN).build()

    # ── Main / Bulk Conversation ──
    main_conv = ConversationHandler(
        entry_points=[CommandHandler("start", start_command)],
        states={
            SELECT_GAME: [CallbackQueryHandler(button_handler)],
            ADMIN_PANEL: [CallbackQueryHandler(admin_panel_callback)],
            ADD_ADMIN_STATE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_add_admin)
            ],
            REMOVE_ADMIN_STATE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_remove_admin)
            ],
            BLACKLIST_ADD_STATE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_blacklist_add)
            ],
            BLACKLIST_REMOVE_STATE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_blacklist_remove)
            ],
            BROADCAST_MSG: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_broadcast)
            ],
            SET_NEW_PASSWORD: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_set_password)
            ],
            SET_PREFIX: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_prefix),
                CallbackQueryHandler(button_handler),
            ],
            UPLOAD_FILE: [
                MessageHandler(filters.Document.FileExtension("txt"), handle_document),
                CallbackQueryHandler(button_handler),
            ],
            # Manual states nested in main conv via button_handler routing
            MANUAL_SELECT_GAME: [
                CallbackQueryHandler(manual_game_selected, pattern="^manual_game_"),
                CallbackQueryHandler(button_handler),
            ],
            MANUAL_ENTER_EMAIL: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, manual_enter_email),
                CallbackQueryHandler(manual_skip_callback),
            ],
            MANUAL_ENTER_PASSWORD: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, manual_enter_password),
                CallbackQueryHandler(manual_skip_callback),
            ],
            MANUAL_ENTER_NEW_EMAIL_PREFIX: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND, manual_enter_new_email_prefix
                ),
                CallbackQueryHandler(manual_skip_callback),
            ],
            MANUAL_ENTER_NEW_PASSWORD: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND, manual_enter_new_password
                ),
                CallbackQueryHandler(manual_skip_callback),
            ],
            MANUAL_CONFIRM: [
                CallbackQueryHandler(manual_execute_callback)
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel_command),
            CommandHandler("start", start_command),
        ],
    )

    # ── Admin Panel Conversation ──
    admin_conv = ConversationHandler(
        entry_points=[CommandHandler("admin", admin_panel_command)],
        states={
            ADMIN_PANEL: [CallbackQueryHandler(admin_panel_callback)],
            ADD_ADMIN_STATE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_add_admin)
            ],
            REMOVE_ADMIN_STATE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_remove_admin)
            ],
            BLACKLIST_ADD_STATE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_blacklist_add)
            ],
            BLACKLIST_REMOVE_STATE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_blacklist_remove)
            ],
            BROADCAST_MSG: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_broadcast)
            ],
            SET_NEW_PASSWORD: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_set_password)
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel_command),
            CommandHandler("admin", admin_panel_command),
        ],
    )

    # ── Manual Conversation (via /manual command) ──
    manual_conv = ConversationHandler(
        entry_points=[CommandHandler("manual", manual_command)],
        states={
            MANUAL_SELECT_GAME: [
                CallbackQueryHandler(manual_game_selected, pattern="^manual_game_"),
                CallbackQueryHandler(manual_skip_callback),
            ],
            MANUAL_ENTER_EMAIL: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, manual_enter_email),
                CallbackQueryHandler(manual_skip_callback),
            ],
            MANUAL_ENTER_PASSWORD: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, manual_enter_password),
                CallbackQueryHandler(manual_skip_callback),
            ],
            MANUAL_ENTER_NEW_EMAIL_PREFIX: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND, manual_enter_new_email_prefix
                ),
                CallbackQueryHandler(manual_skip_callback),
            ],
            MANUAL_ENTER_NEW_PASSWORD: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND, manual_enter_new_password
                ),
                CallbackQueryHandler(manual_skip_callback),
            ],
            MANUAL_CONFIRM: [
                CallbackQueryHandler(manual_execute_callback)
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel_command),
            CommandHandler("manual", manual_command),
        ],
    )

    app.add_handler(main_conv)
    app.add_handler(admin_conv)
    app.add_handler(manual_conv)
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CommandHandler("id", id_command))
    app.add_handler(CommandHandler("cancel", cancel_command))

    logger.info("🤖 Account Manager PRO is running...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
