import os
import yt_dlp
import uuid
import asyncio
import threading
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS

# ===== إعدادات Flask =====
app = Flask(__name__)
CORS(app)

# ===== إعدادات التحميل =====
FOLDER_PATH = './downloads/'
os.makedirs(FOLDER_PATH, exist_ok=True)
chunk_size = 20  # ميجا
file_ext = "m4a"
start_num = 0

# ===== حالات التحميل =====
downloads_status = {}
video_to_id = {}  # جديد: يربط الفيديو بالـ download_id

# ===== دوال مساعدة =====
async def auto_delete(download_id, wait_seconds=3600*8):
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

# ===== تنزيل وتقسيم =====
def download(download_id: str, video_url: str, folder_path: str = FOLDER_PATH,
                          file_extension: str = file_ext):
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

    downloads_status[download_id].update({
        "status": "done",
        "progress": 100,
    })

    return downloaded_file

async def download_and_delete_after_delay(download_id, video_url):
    downloads_status[download_id]["status"] = "in else"
    await asyncio.to_thread(download, download_id, video_url)

    # تشغيل المهمة بدون انتظار في نفس الـ loop
    asyncio.create_task(auto_delete(download_id))

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

    threading.Thread(
        target=lambda: asyncio.run(download_and_delete_after_delay(download_id, link))
    ).start()

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
