import os
import math
import glob
import yt_dlp
import subprocess
import uuid
import asyncio
from asyncio import run_coroutine_threadsafe
import threading
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from telethon import TelegramClient, events
from telethon.tl.types import DocumentAttributeAudio
import random

# ===== إعدادات Flask =====
app = Flask(__name__)
CORS(app)

# ===== إعدادات Telethon =====
API_ID = 25617131
API_HASH = '882b0647556a7b8faeac93962ad8aeb9'
SESSION_FILE = 'session_name.session'
CHANNEL_ID = -1003073946092
BOT_ID = "@sending_files_links_bot"
# API_ID = 29224979
# API_HASH = 'c43959fea9767802e111a4c6cf3b16ec'
# SESSION_FILE = 'session_name.session'
# CHANNEL_ID = -1002990796797
# BOT_ID = "@sending_files_bot"

# ===== إعدادات التحميل =====
FOLDER_PATH = './downloads/'
os.makedirs(FOLDER_PATH, exist_ok=True)
chunk_size = 20  # ميجا
file_ext = "m4a"
start_num = 0

# ===== حالات التحميل =====
downloads_status = {}
video_to_id = {}  # جديد: يربط الفيديو بالـ download_id

queue_num = 1
send_queue = {} # {"download_id": {status: "sending|done", queue_num: 1}} --> when done delete from here, priority for least queue_num

# ===== إنشاء عميل Telethon =====
client = TelegramClient(SESSION_FILE, API_ID, API_HASH)

# ===== متغير loop عالمي =====
TELETHON_LOOP = None

# ===== دوال مساعدة =====
def get_duration(file_path):
    """احسب مدة الملف بالثواني"""
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", file_path],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT
    )
    return float(result.stdout)

async def search_messages(channel: int, keyword: str, download_id: str):
    downloads_status[download_id]["status"] = f"in search"
    async for message in client.iter_messages(channel):
        downloads_status[download_id]["status"] = f"in search id {message.id}"
        if message.text and keyword in message.text:
            print(f'[{message.id}]')
            return [message.id, message.text]
    return "None"

async def auto_delete(download_id, wait_seconds=3600):
    await asyncio.sleep(wait_seconds)
    # لو لسه موجود بعد دقيقة
    if download_id in downloads_status:
        # حذف من video_to_id (لو موجود)
        for link, dl_id in list(video_to_id.items()):
            if dl_id == download_id:
                del video_to_id[link]

        # حذف الملفات من القرص لو موجودة
        files = downloads_status[download_id].get("files", [])
        for f in files:
            if os.path.exists(f):
                os.remove(f)
                print(f"🗑️ تم مسح الملف تلقائيًا: {f}")

        # حذف من downloads_status
        del downloads_status[download_id]
        print(f"🗑️ Download ID {download_id} تم حذفه تلقائيًا بعد دقيقة")

def get_min_item(obj: dict, key: str = "queue_num"):
    """
    {
        "id1": {"queue_num": 41},
        "id2": {"queue_num": 75},
        "id3": {"queue_num": 10},
        "id4": {"queue_num": 96}
    }
    """

    return min(obj, key=lambda k: obj[k][key])

# ===== تنزيل وتقسيم =====
def download_with_demerge(download_id: str, video_url: str, folder_path: str = FOLDER_PATH,
                          file_extension: str = file_ext, target_size: int = chunk_size,
                          file_start_num: int = start_num):
    """تحميل الفيديو + تحويل الصوت + تقسيمه مع progress يوصل 100%"""
    downloads_status[download_id] = {"status": "processing", "progress": 0, "files": []}

    # ==== تنزيل الصوت ====
    def progress_hook(d):
        if d['status'] == 'downloading':
            percent = d.get('_percent_str', '0%').replace('%', '')
            try:
                downloads_status[download_id]["progress"] = float(percent)
            except:
                pass
        elif d['status'] == 'finished':
            downloads_status[download_id]["status"] = "finished"
            downloads_status[download_id]["progress"] = 100  # خلص التنزيل والتحويل

    downloads_status[download_id]["status"] = "before downloading"

    ydl_opts = {
        'format': 'bestaudio[ext=m4a]/bestaudio/best',
        'outtmpl': os.path.join(folder_path, '%(id)s.%(ext)s'),
        'progress_hooks': [progress_hook],
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': file_extension,
            'preferredquality': '192',
        }],
    }

    downloads_status[download_id]["status"] = "before downloading 1"
    
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        downloads_status[download_id]["status"] = "in downloading 1"
        info = ydl.extract_info(video_url, download=True)
        downloads_status[download_id]["status"] = "in downloading 2"
        downloaded_file = ydl.prepare_filename(info)
        downloads_status[download_id]["status"] = "in downloading 3"
        if not downloaded_file.endswith(f".{file_extension}"):
            downloads_status[download_id]["status"] = "in downloading 4"
            downloaded_file = os.path.splitext(downloaded_file)[0] + f".{file_extension}"
            downloads_status[download_id]["status"] = "in downloading 5"

    downloads_status[download_id]["whole_file"] = [downloaded_file.replace("./", "")]

    # ==== حساب الحجم ====
    target_bytes = target_size * 1024 * 1024
    file_size = os.path.getsize(downloaded_file)

    base_name = os.path.splitext(os.path.basename(downloaded_file))[0]

    final_files = []
    files_info = []

    if file_size <= target_bytes:
        # 🔹 الملف أصغر من الحد → إعادة تسميته فقط
        new_name = os.path.join(folder_path, f"{base_name}_{file_start_num:03d}.{file_extension}")
        os.rename(downloaded_file, new_name)
        final_files = [os.path.relpath(new_name, start=os.getcwd())]
        try:
            dur = int(get_duration(new_name))
        except:
            dur = 0
        files_info = [{"file": final_files[0], "duration": dur}]
    else:
        # 🔹 الملف أكبر → تقسيمه
        duration = get_duration(downloaded_file)
        parts = max(1, math.ceil(file_size / target_bytes))
        segment_time = duration / parts
        output_pattern = os.path.join(folder_path, f"{base_name}_%03d.{file_extension}")

        subprocess.run([
            "ffmpeg", "-i", downloaded_file, "-c", "copy",
            "-map", "0", "-f", "segment",
            "-segment_time", str(segment_time),
            "-reset_timestamps", "1",
            "-start_number", str(file_start_num),
            output_pattern
        ])

        final_files = sorted(glob.glob(os.path.join(folder_path, f"{base_name}_*.{file_extension}")))
        final_files = [os.path.relpath(f, start=os.getcwd()) for f in final_files]

        for f in final_files:
            try:
                dur = int(get_duration(f))
            except:
                dur = 0
            files_info.append({"file": f, "duration": dur})

    downloads_status[download_id].update({
        "status": "done downloading",
        "progress": 100,
        "files": final_files,
        "files_info": files_info
    })

    return [downloaded_file, final_files]

# ===== دالة إرسال الملفات للتيليجرام مع تقدم لكل ملف =====
async def send_files_recursive(download_id, ids, index=0):
    """إرسال الملفات للبوت واحد واحد بشكل متتابع"""

    if index >= len(ids):
        print("🎉 خلصت كل الملفات")
        downloads_status[download_id]["status"] = "done 678"
        downloads_status[download_id]["progress"] = 100
        return

    # الرسالة الحالية
    id = ids[index]
    message = await client.get_messages(CHANNEL_ID, ids=id)
    file_name = message.file.name

    # إعادة التوجيه للبوت
    fwd_msg = await client.forward_messages(
        BOT_ID,
        id,
        from_peer=CHANNEL_ID
    )

    # اربط رسالة الرد بالملف
    downloads_status[download_id].setdefault("msg_map", {})[fwd_msg.id] = os.path.basename(file_name)

    downloads_status[download_id]["progress"] = ((index+1) / len(ids)) * 100
    print(f"📩 بعت الملف رقم {index+1}/{len(ids)}: {file_name}")

    # 🟢 استنى لحد ما يضاف الرابط
    while file_name not in downloads_status[download_id].get("links", {}):
        await asyncio.sleep(random.uniform(2.5, 4.5))

    # لما الرابط ييجي، ابعت اللي بعده
    await send_files_recursive(download_id, ids, index + 1)

async def download_and_send(download_id, video_url):
    global queue_num

    downloads_status[download_id]["status"] = "in send"
    base_id = video_url.split('=')[-1]
    keyword = base_id  # أو أي كلمة تبحث عنها في نص الرسالة
    downloads_status[download_id]["status"] = "in send 22"
    
    message_id = await search_messages(CHANNEL_ID, keyword, download_id)

    downloads_status[download_id]["status"] = "after msg id"

    send_queue[download_id] = {"status": "sending", "queue_num": queue_num}
    queue_num += 1

    if message_id != "None": # لو الرسالة موجودة في القناة هات الروابط
        downloads_status[download_id]["status"] = "in if"
        msg_id = message_id[0] # 74
        files_count = int(message_id[1].split(" ")[-1]) # 3
        ids = list(range(msg_id - files_count, msg_id)) # [71, 72, 73] (آخر 3 رسائل)
        
        while (len(send_queue) == 0 or get_min_item(send_queue) == download_id) == False:
            await asyncio.sleep(5)

        await send_files_recursive(download_id, ids)
        downloads_status[download_id]["status"] = "done"
        del send_queue[download_id]
    else: # لو مش موجودة نزل وقسّم وابعت وهات الروابط
        downloads_status[download_id]["status"] = "in else"
        downloaded_file, files = await asyncio.to_thread(download_with_demerge, download_id, video_url)
        files_count = len(files)
        downloads_status[download_id]["files"] = files
        downloads_status[download_id]["files_count"] = files_count

        while (len(send_queue) == 0 or get_min_item(send_queue) == download_id) == False:
            await asyncio.sleep(5)

        for i, file in enumerate(files):
            duration = int(get_duration(file))
            downloads_status[download_id]["current_file_num"] = i+1
            downloads_status[download_id]["current_file"] = os.path.basename(file)
            downloads_status[download_id]["progress"] = 0  # يبدأ من صفر لكل ملف

            # إرسال الملف مع progress_callback
            msg = await client.send_file(
                CHANNEL_ID,
                file,
                attributes=[DocumentAttributeAudio(duration=duration)],
                progress_callback=lambda sent, total: downloads_status[download_id].update(
                    {"progress": int(sent / total * 100)}
                )
            )

            # بعد الانتهاء من الملف نعتبره مكتمل 100%
            downloads_status[download_id]["progress"] = 100
            print(f"تم إرسال الملف: {file}")

            # إعادة توجيه الرسالة للبوت
            fwd_msg = await client.forward_messages(
                BOT_ID,
                msg.id,
                from_peer=CHANNEL_ID
            )

            # هنا بنربط الـ fwd_msg.id مع اسم الملف
            downloads_status[download_id].setdefault("msg_map", {})[fwd_msg.id] = os.path.basename(file)

            print(f"📩 تم إعادة توجيه الملف للبوت: {file}")

        # ==== مسح كل الملفات المقسمة بعد الإرسال ====
        for file in files:
            if os.path.exists(file):
                os.remove(file)
                print(f"🗑️ تم مسح الملف: {file}")

        # مسح الملف الأصلي بعد التقسيم
        if os.path.exists(downloaded_file):
            os.remove(downloaded_file)

        await client.send_message(CHANNEL_ID, f"{base_id} {len(files)}")
        downloads_status[download_id]["status"] = "done"

        del send_queue[download_id]
    
    # تشغيل المهمة بدون انتظار في نفس الـ loop
    asyncio.create_task(auto_delete(download_id))

@client.on(events.NewMessage(from_users=BOT_ID))
async def handler(event):
    if event.is_reply:
        # id بتاع الرسالة اللي رد عليها البوت
        reply_id = event.message.reply_to_msg_id

        # دور في كل download_id عن الرسالة دي
        for dl_id, data in downloads_status.items():
            msg_map = data.get("msg_map", {})
            if reply_id in msg_map:  # يعني الرد يخص الملف ده
                file_name = msg_map[reply_id]
                text = event.message.message.split("\n")[1].strip()

                if "http" in text:
                    data.setdefault("links", {})[file_name] = text
                    print(f"✅ [{file_name}] => {text}")

# ===== تشغيل Telethon loop في thread منفصل =====
def start_telethon_loop():
    global TELETHON_LOOP
    loop = asyncio.new_event_loop()
    TELETHON_LOOP = loop
    asyncio.set_event_loop(loop)
    client.start()
    loop.run_forever()

threading.Thread(target=start_telethon_loop, daemon=True).start()

# ===== Flask API =====
@app.route("/")
def hello_page():
    return "السلام عليكم ورحمة الله وبركاته"
    
@app.route("/url")
def start_download():
    link = request.args.get("link")
    if not link:
        return jsonify({"error": "يرجى إدخال رابط"}), 400

    # لو الفيديو ده جاري تحميله أو اتحمل بالفعل → رجع نفس الـ download_id
    if link in video_to_id:
        download_id = video_to_id[link]
        status_data = downloads_status.get(download_id, {"status": "pending"})
        status = status_data.get("status")
        if status not in ["error"]:
            return jsonify({"download_id": download_id, "status": status_data})

    download_id = str(uuid.uuid4())
    video_to_id[link] = download_id  # اربط الرابط بالـ ID
    downloads_status[download_id] = {"status": "after wait", "progress": 0, "files": []}

    run_coroutine_threadsafe(download_and_send(download_id, link), TELETHON_LOOP)

    return jsonify({"download_id": download_id, "status": "queued"})

@app.route("/status/<download_id>")
def check_status(download_id):
    status = downloads_status.get(download_id)
    if not status:
        return jsonify({"error": f"Download ID Not found, {str(downloads_status)}"}), 200

    delete_flag = request.args.get("delete", "").lower() == "true"  # لو ?delete=true
    if delete_flag:
        # حذف من video_to_id (لو موجود)
        for link, dl_id in list(video_to_id.items()):
            if dl_id == download_id:
                del video_to_id[link]

        # حذف من downloads_status
        del downloads_status[download_id]
        return jsonify({"message": f"Download ID {download_id} تم حذفه بنجاح"})

    return jsonify({"download_id": download_id, "status": status})

@app.route("/downloads/<path:filename>")
def serve_downloads(filename):
    return send_from_directory(os.path.join(os.getcwd(), "downloads"), filename)

# ===== تشغيل Flask =====
if __name__ == "__main__":
    app.run(port=8000, debug=False, use_reloader=False)
