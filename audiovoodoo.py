# AudioVoodoo - Telegram bot to show spectrograms and audio previews
import os, subprocess, sys
import re, pwd, platform, psutil
import logging
from datetime import datetime, timedelta
import time
from timeit import default_timer as timer
import pymongo

from pyrogram import Client, filters
from pyrogram.types import (InlineQueryResultArticle, InputTextMessageContent,
                            InlineKeyboardMarkup, InlineKeyboardButton, Message, InputMediaPhoto, InputMediaAudio)
from pathlib import Path

pt = datetime.now()

api_id = os.getenv('API_ID')
api_hash = os.getenv('API_HASH')
api_session = os.getenv('API_SESSION_STRING')
bot_token = os.getenv('BOT_TOKEN')

mongo_con = os.getenv('MONGO_CON')
mongo = pymongo.MongoClient(mongo_con)
db = mongo.rominimal

#uid = pwd.getpwuid(os.getuid()).pw_name
uname = platform.uname()

metrics = {}
metrics['processed'] = 0

superadmin_ids = [45137724]

REGEXES = ['.*\.aiff','.*\.flac','.*\.wav','.*\.wave', '.*\.m4a']
REGEXES = [ re.compile(r) for r in REGEXES ]
PREVIEW_REGEXES = ['.*\.aiff','.*\.flac']
PREVIEW_REGEXES = [ re.compile(r) for r in PREVIEW_REGEXES ]

logger = logging.getLogger('mainloop')

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] (%(module)s.%(funcName)s): %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('out.log')
    ]
)
def clearworkspace(path):
    now = time.time()
    for filename in os.listdir(path):
        #if os.stat(os.path.join(path,f)).st_mtime < now - 7 * 86400:
        if os.path.getmtime(os.path.join(path, filename)) < now - 7 * 86400:
            if os.path.isfile(os.path.join(path, filename)):
                logger.info(f'Removing {os.path.join(path, filename)}')
                os.remove(os.path.join(path, filename))

# Scale mem units
def get_size(bytes, suffix="B"):
    """
    Scale bytes to its proper format
    e.g:
        1253656 => '1.20MB'
        1253656678 => '1.17GB'
    """
    factor = 1024
    for unit in ["", "K", "M", "G", "T", "P"]:
        if bytes < factor:
            return f"{bytes:.2f}{unit}{suffix}"
        bytes /= factor

def progress(current, total, *args):
    print(f"\r{current * 100 / total:.1f}% [{current}/{total}]", end='')

def file_size(f):
    try:
        return os.stat(f).st_size
    except FileNotFoundError:
        return 0

async def admin_filter(_, __, m: Message):
    return bool(m.from_user and m.from_user.id in superadmin_ids)

def checkmedia(message):
    try:
        if message.document:
            return message.document
        elif message.audio:
            return message.audio
        else:
            return None
        logger.info(media)
    except Exception as e:
        logger.info('No Document found')
        logger.error(e)

#    try:
#        media = message.document
#        logger.info(media)
#    except Exception as e:
#        logger.info('No Document found')
#        logger.error(e)
#    else:
#        logger.info('Media found in Document')
#        logger.info(message)
#        return media
#
#    try:
#        media = message.audio
#    except Exception as e:
#        logger.error(e)
#    else:
#        logger.info('Media found in Audio')
#        return media
#
async def send_spectro(message, media):
    fname =  Path(media.file_name).stem

    if media and (any(regex.match(media.file_name) for regex in PREVIEW_REGEXES) or True):
       await app.send_media_group(
            chat_id = message.chat.id,
            reply_to_message_id = message.message_id,
            disable_notification = True, 
            media = [
                InputMediaAudio(f'downloads/PREVIEW-ONLY--{fname}.m4a', caption=f'PREVIEW-ONLY (took {e_time} s)\n```{ffprobe}```')
            ]
        )
    await app.send_media_group(
        chat_id = message.chat.id,
        reply_to_message_id = message.message_id,
        disable_notification = True, 
        media = [
            InputMediaPhoto(f'downloads/{fname}.png', caption=f'Does it look like transcode? Log scale'),
            InputMediaPhoto(f'downloads/{fname}-lin.png', caption=f'Linear scale'),
            InputMediaPhoto(f'downloads/{fname}-gain5.png', caption=f'Gain * 5')
            #InputMediaPhoto(f'downloads/{fname}-gainp5.png', caption=f'Gain * 0.5'),
        ]
    )
    try:
        object_id = db.voodoo.insert_one({
            'time': message.date,
            'user_name': message.from_user.username,
            'first_name': message.from_user.first_name,
            'last_name': message.from_user.last_name,
            'user_id': message.from_user.id,
            'chat_id': message.chat.id,
            'chat_title': message.chat.title,
            'file_name': media.file_name,
            'mime_type': media.mime_type,
            'file_size': media.file_size,
            'lastModified': datetime.now()
            }).inserted_id
    except Exception as e:
        logger.error('Could not write to DB')
        logger.error(e)


async def gen_artifacts(message, media):
    #media = checkmedia(message)
    fname =  Path(media.file_name).stem
    ffout = subprocess.run(['ffprobe', '-select_streams', 'a:0', '-v', 'quiet', '-show_format', f'downloads/{media.file_name}'], capture_output=True)
    ffprobe = ffout.stdout.decode('UTF-8').replace('[FORMAT]\n','').replace('[/FORMAT]','').replace('downloads/','')

    if media and (any(regex.match(media.file_name) for regex in PREVIEW_REGEXES) or True):
        s_time = timer() 
        cached = True
        if not os.path.isfile(f'downloads/PREVIEW-ONLY--{fname}.m4a'):
            ff = subprocess.run(['ffmpeg', '-hide_banner', '-nostats', '-loglevel', 'warning', '-err_detect', 'ignore_err', '-y', '-i', f'downloads/{media.file_name}', '-vn','-c:a', 'libfdk_aac', '-b:a', '64k', '-map', 'a:0', f'downloads/PREVIEW-ONLY--{fname}.m4a'])
            cached = False
            logger.info(ff)
        e_time = (timer() -  s_time) #conver to s
        e_time =  float("{:.2f}".format(e_time))  
        fs = file_size(f'downloads/{media.file_name}')
        logger.info(fs)
        await app.send_media_group(
            chat_id = message.chat.id,
            reply_to_message_id = message.message_id,
            disable_notification = True, 
            media = [
                InputMediaAudio(f'downloads/PREVIEW-ONLY--{fname}.m4a', caption=f'PREVIEW-ONLY [took: {e_time}s, cache: ${cached}]\n```{ffprobe}```')
            ]
        )
 
    if not os.path.isfile(f'downloads/{fname}.png'):
        logger.info(f'Creating downloads/{fname}.png')
        ffspec = subprocess.run(['ffmpeg', '-i', f'downloads/{media.file_name}', '-lavfi', 'showspectrumpic=s=1920x960:mode=separate:orientation=vertical', f'downloads/{fname}.png'])
    if not os.path.isfile(f'downloads/{fname}-gain5.png'):
        logger.info(f'Creating downloads/{fname}-gain5.png')
        ffspec = subprocess.run(['ffmpeg', '-i', f'downloads/{media.file_name}', '-lavfi', 'showspectrumpic=s=1920x960:mode=separate:orientation=vertical:gain=5', f'downloads/{fname}-gain5.png'])
    if not os.path.isfile(f'downloads/{fname}-lin.png'):
        logger.info(f'Creating downloads/{fname}-lin.png')
        ffspec = subprocess.run(['ffmpeg', '-i', f'downloads/{media.file_name}', '-lavfi', 'showspectrumpic=s=1920x960:mode=separate:orientation=vertical:scale=lin', f'downloads/{fname}-lin.png'])

    await app.send_media_group(
        chat_id = message.chat.id,
        reply_to_message_id = message.message_id,
        disable_notification = True, 
        media = [
            InputMediaPhoto(f'downloads/{fname}.png', caption=f'Does it look like transcode? Log scale'),
            InputMediaPhoto(f'downloads/{fname}-lin.png', caption=f'Linear scale'),
            InputMediaPhoto(f'downloads/{fname}-gain5.png', caption=f'Gain * 5')
            #InputMediaPhoto(f'downloads/{fname}-gainp5.png', caption=f'Gain * 0.5'),
        ]
    )
    try:
        object_id = db.voodoo.insert_one({
            'time': message.date,
            'user_name': message.from_user.username,
            'first_name': message.from_user.first_name,
            'last_name': message.from_user.last_name,
            'user_id': message.from_user.id,
            'chat_id': message.chat.id,
            'chat_title': message.chat.title,
            'file_name': media.file_name,
            'mime_type': media.mime_type,
            'file_size': media.file_size,
            'lastModified': datetime.now()
            }).inserted_id
    except Exception as e:
        logger.error('Could not write to DB')
        logger.error(e)

    clearworkspace('downloads')
 
is_admin = filters.create(admin_filter)


app = Client(api_session, api_id, api_hash, bot_token=bot_token)
app.DOWNLOAD_WORKERS = 4

with app:
    logger.info(f'SESSION_STRING: {app.export_session_string()}')

@app.on_message(filters.media, group=1)
async def new_mediafile(client, message):
        logger.info(message)
        metrics['processed'] += 1
        media = checkmedia(message)
        try:
            if media and media.file_name and media.file_size < 268435456 and media.mime_type.startswith('audio') and any(regex.match(media.file_name) for regex in REGEXES) or True:
                logline = f"""➕ [{message.chat.title}/{message.chat.id}]
        <@{message.from_user.username} {message.from_user.first_name} {message.from_user.last_name} /{message.from_user.id}>
        file_name: {media.file_name} 
        mime_type: {media.mime_type} 
        file_size: {media.file_size} 
        date: {media.date}"""
                for admin in superadmin_ids:
                    await client.send_message(admin, logline) 
                    logger.info('Sent notification to {admin}')
                logger.info(logline)

                logger.info("Media Dectected!")
                logger.info(media)
                fs = file_size(f'downloads/{media.file_name}')

                if fs < media.file_size:
                    logger.info(f'<{message.message_id}> ==> [{media.file_name}] @ {message.date}')
                    logger.info(f'{fs} < {media.file_size}')
                    try:
                        await app.download_media(message, progress=progress, progress_args=(media.file_name,))
                        await gen_artifacts(message, media)
                    except Exception as e:
                        logger.error(e)
                elif fs == media.file_size:
                    logger.info(f'Already complete {media.file_name}')
                    await gen_artifacts(message, media)
            else:
                logger.info(f'<{message.message_id} / {message.from_user.username}({message.from_user.id})> Not Media ({message.text} / {media.file_name} / {media.mime_type})')
        except Exception as e:
            logger.info(e)
        #sys.exit(0)
@app.on_message(filters.command(["start", "start@AudioVoodooBot"]) | filters.command(["help", "help@AudioVoodooBot"]) )
def start_admin(app, message):
    message.reply_text(
    """
Welcome to 🎵AudioVoodoo Bot🤖 - Audio helper. I will reply with spectrograms & small size previews for each audio file posted on a group I am at. Enjoy!

**Made with ❤️ by** https://t.me/r0minimal -- Mixing underground vibes live
    """)

@app.on_message(filters.command(["status", "status@AudioVoodooBot"]), group=1)
def status(app, message):
    s_time = timer()
    cpufreq = psutil.cpu_freq()
    svmem = psutil.virtual_memory()

    cpusage = []
    c = []
    for i, percentage in enumerate(psutil.cpu_percent(percpu=True, interval=1)):
        cpusage.append(f"Core {i}: {percentage}%")
    #logger.info(message)
    #for collection in db.list_collection_names():
    for collection in ['voodoo']:
        c.append((collection, db[collection].count_documents({})))

    r_time = (timer() -  s_time)
    r_time =  float("{:.2f}".format(r_time))
    message.reply_text(f"""
```Db Collections: {c}
Bot Started: {pt}
Bot Processed: {metrics["processed"]}
Os Load: {os.getloadavg()}
Os Total Cores: {psutil.cpu_count(logical=True)}
Os Total CPU Usage: {psutil.cpu_percent()}%
Os Mem Total: {get_size(svmem.total)}
Os Mem Available: {get_size(svmem.available)}
Os Mem Used: {get_size(svmem.used)}
Os Mem Percentage: {svmem.percent}%
Generated in: {r_time} s```
"""
    )
@app.on_message(filters.command(["stats", "stats@AudioVoodooBot"]), group=2)
def echo(app, message):
    r = db.voodoo.count_documents({"user_id":message.from_user.id})
    message.reply_text(f'👌 You @{message.from_user.username} have contributed [**{r}**] fine uploads ♥️🎶')
app.run()
