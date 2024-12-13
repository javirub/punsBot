import os
import random
import re
import sqlite3
import string
import uuid

from dotenv import load_dotenv
from telebot import TeleBot, types

# Configuración de variables globales
ALLOWED_CHARS_PUNS = string.ascii_letters + " " + string.digits + "áéíóúàèìòùäëïöü"
ALLOWED_CHARS_TRIGGERS = ALLOWED_CHARS_PUNS + "^$.*+?(){}\\[]<>=-"
VERSION = "0.0.3"
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


def load_default_puns(dbfile: str = 'puns.db', punsfile: str = 'rimas.txt'):
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


def find_pun(message: types.Message, dbfile: str):
    with sqlite3.connect(dbfile) as db:
        cursor = db.cursor()
        triggers = cursor.execute(
            '''SELECT trigger, pun FROM puns WHERE chatid = ? OR chatid = 0''', (message.chat.id,)
        ).fetchall()
        message_text = message.text.strip()  # Remueve espacios adicionales alrededor del texto
        for trigger, pun in triggers:
            if is_valid_regex(trigger):
                # Requiere que el patrón coincida SOLO si está al final
                pattern = rf"{trigger}$"
                if re.search(pattern, message_text):  # Busca solo si 'trigger' está al final
                    return pun
    return None


@bot.message_handler(commands=['help'])
def help_message(message: types.Message):
    help_text = f'''
    <b>Comandos Disponibles:</b>
    /punadd - Agregar una nueva rima (disparador|rima)
    /pundel - Eliminar una rima existente (uuid)
    /punlist - Listar todas las rimas para este chat
    /punapprove - Aprobar una rima
    /punban - Bloquear una rima
    /punsilence - Silenciar el bot por minutos especificados
    /punset - Configurar la probabilidad de respuesta del bot (1-100)

    Versión: {VERSION}
    '''
    bot.reply_to(message, help_text)


@bot.message_handler(commands=['punadd'])
def add_pun(message: types.Message):
    try:
        _, content = message.text.split(' ', 1)
        trigger, pun = content.split('|', 1)
        if not is_valid_regex(trigger):
            bot.reply_to(message, "Expresión regular no válida en el trigger.")
            return
        with sqlite3.connect(DB_LOCATION) as db:
            cursor = db.cursor()
            cursor.execute(
                '''INSERT OR IGNORE INTO puns(uuid, chatid, trigger, pun) VALUES(?, ?, ?, ?)''',
                (str(uuid.uuid4()), message.chat.id, trigger.strip(), pun.strip())
            )
            db.commit()
        bot.reply_to(message, "B")
    except ValueError:
        bot.reply_to(message, "Formato invalido. Usa /punadd trigger|texto respuesta")

@bot.message_handler(commands=['punlist'])
def list_puns(message: types.Message):
    with sqlite3.connect(DB_LOCATION) as db:
        cursor = db.cursor()
        puns = cursor.execute(
            '''SELECT uuid, trigger, pun FROM puns WHERE chatid = ? OR chatid = 0''', (message.chat.id,)
        ).fetchall()
        if not puns:
            bot.reply_to(message, "No hay rimas disponibles.")
            return
        response = "<b>Puns:</b>\n"
        for uuid, trigger, pun in puns:
            response += f"<b>{uuid}</b>: {trigger} -> {pun}\n"
        bot.reply_to(message, response)


@bot.message_handler(commands=['punset'])
def pun_set(message: types.Message):
    try:
        _, value = message.text.split(' ', 1)
        value = int(value.strip())
        if 0 <= value <= 100:
            with sqlite3.connect(DB_LOCATION) as db:
                cursor = db.cursor()
                cursor.execute(
                    '''INSERT OR REPLACE INTO chatoptions (chatid, efectivity) VALUES (?, ?)''',
                    (message.chat.id, value)
                )
                db.commit()
            bot.reply_to(message, f"Probabilidad de respuesta ajustada a {value}%.")
        else:
            bot.reply_to(message, "Valor invalido. Tiene que ser un número del 0 al 100.")
    except ValueError:
        bot.reply_to(message, "Formato invalido. Usa /punset <valor> (donde <valor> es un número del 0 al 100).")


@bot.message_handler(commands=['punsilence'])
def pun_silence(message: types.Message):
    with sqlite3.connect(DB_LOCATION) as db:
        cursor = db.cursor()
        cursor.execute(
            '''INSERT OR REPLACE INTO chatoptions (chatid, efectivity) VALUES (?, ?)''',
            (message.chat.id, 0)  # Ajustar efectividad a 0 (silencio total)
        )
        db.commit()
    bot.reply_to(message,
                 "Ya cierro la boquita. Cuando me echéis de menos usad /punset <valor> con un valor del 1 al 100.")


@bot.message_handler(func=lambda msg: True)
def handle_message(message: types.Message):
    # Buscar la rima en la base de datos
    pun = find_pun(message, DB_LOCATION)

    # Solo calcular probabilidad si existe una rima
    if pun:
        with sqlite3.connect(DB_LOCATION) as db:
            cursor = db.cursor()
            # Obtener la probabilidad de respuesta del chat
            result = cursor.execute('SELECT efectivity FROM chatoptions WHERE chatid = ?',
                                    (message.chat.id,)).fetchone()
            efectivity = result[0] if result else 100  # Default: 100% si no está definido

        # Calcular si responde basado en la probabilidad
        if efectivity > 0 and random.randint(1, 100) <= efectivity:
            bot.reply_to(message, pun)


if __name__ == "__main__":
    db_setup(DB_LOCATION)
    load_default_puns(dbfile=DB_LOCATION, punsfile=os.path.join(BASE_DIR, "rimas.txt"))
    print(f"PunsBot {VERSION} is ready!")
    bot.polling(non_stop=True)