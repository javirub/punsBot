import os
import sqlite3
import uuid
import string
import re
import time
from telebot import TeleBot, types
from dotenv import load_dotenv

# Configuración de variables globales
ALLOWED_CHARS_PUNS = string.ascii_letters + " " + string.digits + "áéíóúàèìòùäëïöü"
ALLOWED_CHARS_TRIGGERS = ALLOWED_CHARS_PUNS + "^$.*+?(){}\\[]<>=-"
VERSION = "0.0.1"
REQUIRED_VALIDATIONS = 5
load_dotenv()

# Validación de variables de entorno
TOKEN = os.getenv("TOKEN")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_LOCATION = os.path.join(BASE_DIR, 'puns.db')
PUNS_FILES_DIR = os.path.join(BASE_DIR, 'defaultpuns/punsfiles')

if not TOKEN:
    raise EnvironmentError("Missing TOKEN. Exiting...")
if not DB_LOCATION:
    raise EnvironmentError("Missing DBLOCATION. Exiting...")

bot = TeleBot(TOKEN, parse_mode='HTML')

def is_valid_regex(pattern: str) -> bool:
    try:
        re.compile(pattern)
        return True
    except re.error:
        return False

def load_default_puns(dbfile: str = 'puns.db', punsfile: str = 'bromas.txt'):
    with sqlite3.connect(dbfile) as db:
        cursor = db.cursor()
        with open(os.path.expanduser(punsfile), 'r', encoding='utf-8') as staticpuns:
            for number, line in enumerate(staticpuns, start=1):
                parts = line.strip().split('|')
                if len(parts) == 2:
                    trigger, pun = parts
                    if is_valid_regex(trigger):
                        cursor.execute(
                            '''INSERT OR IGNORE INTO puns(uuid, chatid, trigger, pun) VALUES(?, ?, ?, ?)''',
                            (str(uuid.uuid4()), 0, trigger, pun)
                        )
                    else:
                        print(f"Invalid regex trigger '{trigger}' on line {number} of file {punsfile}. Not added.")
                else:
                    print(f"Incorrect format on line {number} of file {punsfile}. Not added.")
        db.commit()

def db_setup(dbfile: str):
    with sqlite3.connect(dbfile) as db:
        cursor = db.cursor()
        cursor.execute('''CREATE TABLE IF NOT EXISTS puns (
            uuid TEXT PRIMARY KEY,
            chatid INTEGER,
            trigger TEXT,
            pun TEXT,
            UNIQUE(trigger, pun, chatid)
        )''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS validations (
            punid TEXT,
            chatid INTEGER,
            userid TEXT,
            karma INTEGER
        )''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS chatoptions (
            chatid INTEGER PRIMARY KEY,
            silence INTEGER,
            efectivity INTEGER
        )''')
        db.commit()

def is_chat_silenced(chat_id: int, dbfile: str) -> bool:
    with sqlite3.connect(dbfile) as db:
        cursor = db.cursor()
        result = cursor.execute('SELECT silence FROM chatoptions WHERE chatid = ?', (chat_id,)).fetchone()
        silence_time = result[0] if result else 0
        return silence_time > time.time()

def silence_until(chat_id: int, dbfile: str) -> str:
    with sqlite3.connect(dbfile) as db:
        cursor = db.cursor()
        result = cursor.execute('SELECT silence FROM chatoptions WHERE chatid = ?', (chat_id,)).fetchone()
        silence_time = result[0] if result else 0
        return time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(silence_time)) if silence_time > time.time() else "Never"

def find_pun(message: types.Message, dbfile: str):
    with sqlite3.connect(dbfile) as db:
        cursor = db.cursor()
        triggers = cursor.execute(
            '''SELECT trigger, pun FROM puns WHERE chatid = ? OR chatid = 0''', (message.chat.id,)
        ).fetchall()
        for trigger, pun in triggers:
            if is_valid_regex(trigger) and re.search(trigger, message.text):
                return pun
    return None

@bot.message_handler(commands=['help'])
def help_message(message: types.Message):
    help_text = f'''
<b>Available Commands:</b>
/punadd - Add a new pun (trigger|pun)
/pundel - Delete an existing pun (uuid)
/punlist - List all puns for this chat
/punapprove - Approve a pun
/punban - Ban a pun
/punsilence - Mute bot for specified minutes
/punset - Set pun response probability (1-100)

Version: {VERSION}
'''
    bot.reply_to(message, help_text)

@bot.message_handler(commands=['punadd'])
def add_pun(message: types.Message):
    try:
        _, content = message.text.split(' ', 1)
        trigger, pun = content.split('|', 1)
        if not is_valid_regex(trigger):
            bot.reply_to(message, "Invalid regex in trigger.")
            return
        with sqlite3.connect(DB_LOCATION) as db:
            cursor = db.cursor()
            cursor.execute(
                '''INSERT OR IGNORE INTO puns(uuid, chatid, trigger, pun) VALUES(?, ?, ?, ?)''',
                (str(uuid.uuid4()), message.chat.id, trigger.strip(), pun.strip())
            )
            db.commit()
        bot.reply_to(message, "Pun added successfully!")
    except ValueError:
        bot.reply_to(message, "Invalid format. Use /punadd trigger|pun")

@bot.message_handler(commands=['punlist'])
def list_puns(message: types.Message):
    with sqlite3.connect(DB_LOCATION) as db:
        cursor = db.cursor()
        puns = cursor.execute(
            '''SELECT uuid, trigger, pun FROM puns WHERE chatid = ? OR chatid = 0''', (message.chat.id,)
        ).fetchall()
        if not puns:
            bot.reply_to(message, "No puns available.")
            return
        response = "<b>Puns:</b>\n"
        for uuid, trigger, pun in puns:
            response += f"<b>{uuid}</b>: {trigger} -> {pun}\n"
        bot.reply_to(message, response)

@bot.message_handler(func=lambda msg: True)
def handle_message(message: types.Message):
    if not is_chat_silenced(message.chat.id, DB_LOCATION):
        pun = find_pun(message, DB_LOCATION)
        if pun:
            bot.reply_to(message, pun)

if __name__ == "__main__":
    db_setup(DB_LOCATION)
    load_default_puns(dbfile=DB_LOCATION, punsfile=os.path.join(BASE_DIR, "bromas.txt"))
    print(f"PunsBot {VERSION} is ready!")
    bot.polling(non_stop=True)
