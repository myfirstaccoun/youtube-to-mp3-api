import os
import yt_dlp
import requests
import uuid
import time
import threading
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS

# ===== إعدادات Flask =====
app = Flask(__name__)
CORS(app)

# ===== إعدادات التحميل =====
FOLDER_PATH = './downloads/'
os.makedirs(FOLDER_PATH, exist_ok=True)
file_ext = "m4a"
start_num = 0

# ===== حالات التحميل =====
downloads_status = {}
video_to_id = {}  # جديد: يربط الفيديو بالـ download_id

# ===== دوال =====
def get_json_file(link: str):
    import requests
    
    """تحميل ملف JSON من رابط وإرجاع محتواه كقاموس (dict)."""
    try:
        response = requests.get(link)
        response.raise_for_status()  # لو الرابط فيه خطأ (404 أو 500) يرمي استثناء
        return response.json()       # يحوّل محتوى JSON إلى dict مباشرة
    except requests.exceptions.RequestException as e:
        print(f"خطأ في تحميل الملف: {e}")
        return None
    except ValueError:
        print("الملف مش بصيغة JSON صحيحة.")
        return None

def saveJSON(data: dict, file_path: str, indent: int = 4, encoding: str = "utf-8", save_mode="w"):
    """
    اللهم صل وسلم على نبينا محمد ﷺ
    ---------------------------------
    تحفظ بيانات JSON في ملف بأمان، مع إنشاء المجلد تلقائيًا
    والتعامل مع المسارات المطلقة داخل السيرفر أو Docker.
    """

    import os
    import json

    try:
        # 🔹 تحديد المسار الكامل بناءً على مكان هذا الملف (app.py)
        base_dir = os.path.dirname(os.path.abspath(__file__))
        full_path = os.path.join(base_dir, file_path)

        # 🔹 إنشاء المجلد تلقائيًا إذا لم يكن موجودًا
        os.makedirs(os.path.dirname(full_path), exist_ok=True)

        # 🔹 حفظ البيانات في الملف
        with open(full_path, save_mode, encoding=encoding) as output_file:
            json.dump(data, output_file, indent=indent, ensure_ascii=False)

        print(f"✅ تم حفظ الملف بنجاح: {full_path}")

    except Exception as e:
        downloads_status[download_id]["status"] = "error"
        downloads_status[download_id]["error"] = f"Download failed: {str(e)}"
        return None


def create_folder(folder_path: str):
    """
    اللهم صل على محمد ﷺ
    ---------------------------
    """

    if not os.path.exists(folder_path):
        os.makedirs(folder_path)

# ===== المعلومات =====
def get_channel_videos(channel_url: str, links: bool = True, titles: bool = True, thumb: bool = False) -> list[dict]:
    """
    ترجع قائمة فيديوهات قناة يوتيوب.
    
    Args:
        channel_url (str): رابط القناة (مثلاً https://www.youtube.com/@Waie/videos)
        links (bool): لو True ترجع الرابط
        titles (bool): لو True ترجع العنوان
    
    Returns:
        list[dict]: قائمة من القواميس بالشكل {"link": ..., "title": ...}
    """
    if not (links or titles):
        raise ValueError("لازم تحدد links أو titles على الأقل True")
    
    ydl_opts = {
        'extract_flat': True,  # نجيب روابط الفيديوهات فقط من صفحة القناة
    }
    
    result = []
    
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(channel_url, download=False)
        for entry in info['entries']:
            video_data = {}
            if links:
                video_data['link'] = f"https://www.youtube.com/watch?v={entry['id']}"
            if titles:
                video_data['title'] = entry['title']
            if thumb:
                video_data['thumb'] = get_best_thumbnail(entry['id'])
            result.append(video_data)
    
    return result

def get_playlist_videos(playlist_url: str, links: bool = True, titles: bool = True, thumb: bool = False) -> list[dict]:
    """
    ترجع قائمة فيديوهات بلايليست يوتيوب.
    
    Args:
        playlist_url (str): رابط البلايليست
        links (bool): لو True ترجع الرابط
        titles (bool): لو True ترجع العنوان
    
    Returns:
        list[dict]: قائمة من القواميس بالشكل {"link": ..., "title": ...}
    """
    if not (links or titles):
        raise ValueError("لازم تحدد links أو titles على الأقل True")
    
    ydl_opts = {
        'extract_flat': True,  # نجيب روابط الفيديوهات فقط من البلايليست
    }
    
    result = []
    
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(playlist_url, download=False)
        for entry in info['entries']:
            video_data = {}
            if links:
                video_data['link'] = f"https://www.youtube.com/watch?v={entry['id']}"
            if titles:
                video_data['title'] = entry['title']
            if thumb:
                video_data['thumb'] = get_best_thumbnail(entry['id'])
            result.append(video_data)
    
    return result

def get_video_info(link: str, title: bool = True, description: bool = True, thumb: bool = False) -> dict:
    """
    ترجع معلومات فيديو يوتيوب.
    
    Args:
        link (str): رابط الفيديو
        title (bool): لو True ترجع العنوان
        description (bool): لو True ترجع الوصف
    
    Returns:
        dict: قاموس يحتوي على {"title": ..., "description": ...} حسب الخيارات
    """
    if not (title or description):
        raise ValueError("لازم تحدد title أو description على الأقل True")
    
    ydl_opts = {
        'quiet': True,  # منع الطباعة على الكونسول
        'skip_download': True,  # مش هننزل الفيديو
    }
    
    result = {}
    
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(link, download=False)
        if title:
            result['title'] = info.get('title', '')
        if description:
            result['description'] = info.get('description', '')
        if thumb:
            result['thumb'] = get_best_thumbnail(info.get('id', ''))
        
    return result

def get_best_thumbnail(video_id: str) -> str:
    """
    تجيب أفضل صورة مصغرة باستخدام requests وتجربة الروابط.
    """
    qualities = [
        "maxresdefault.jpg",
        "sddefault.jpg",
        "hqdefault.jpg",
        "mqdefault.jpg",
        "default.jpg"
    ]

    base_url = f"https://img.youtube.com/vi/{video_id}/"

    for quality in qualities:
        url = base_url + quality
        try:
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                # صورة placeholder بتكون صغيرة جداً (120px)
                if "image" in response.headers.get("Content-Type", "") and len(response.content) > 2000:
                    return url
        except requests.RequestException:
            continue

    return None

# ===== عمل الملفات =====
podcasts_in_first_run = True
salasel_in_first_run = True
def make_podcasts_links(loop_time = 3600*12):
    global podcasts_in_first_run

    res = {}
    file = get_json_file("https://sawtii.github.io/بيانات/إذاعة.json")
    for i, item in enumerate(file):
        item_type = item["type"]
        link = item["link"]

        if item_type == "channel":
            res[link] = get_channel_videos(link, links=True, titles=True, thumb=False)
        elif item_type == "playlist":
            res[link] = get_playlist_videos(link, links=True, titles=True, thumb=False)
        
        if "reverse" in item and item["reverse"] == True: res[link] = res[link][::-1]
    
    create_folder("./data")
    saveJSON(res, "./data/podcasts.json")
    
    if podcasts_in_first_run == True:
        make_salasel_links()
        podcasts_in_first_run = False
    
    time.sleep(loop_time)
    make_podcasts_links()

def make_salasel_links(loop_time = 3600*24*30):
    global salasel_in_first_run

    res = {}
    file = get_json_file("https://sawtii.github.io/بيانات/سلاسل.json")
    for i, person in enumerate(file):
        for item in person["courses"]:
            item_type = item["type"]
            link = item["link"]

            if item_type == "channel":
                res[link] = get_channel_videos(link, links=True, titles=True, thumb=False)
            elif item_type == "playlist":
                res[link] = get_playlist_videos(link, links=True, titles=True, thumb=False)
            
            if "reverse" in item and item["reverse"] == True: res[link] = res[link][::-1]
    
    saveJSON(res, "./data/salasel.json")
    
    if salasel_in_first_run == True:
        make_courses_links()
        salasel_in_first_run = False
    
    time.sleep(loop_time)
    make_salasel_links()

def make_courses_links(loop_time = 3600*24*3):
    res = {}
    file = get_json_file("https://sawtii.github.io/بيانات/محاضرون.json")
    for i, person in enumerate(file):
        for item in person["courses"]:
            item_type = item["type"]
            link = item["link"]

            if item_type == "channel":
                res[link] = get_channel_videos(link, links=True, titles=True, thumb=False)
            elif item_type == "playlist":
                res[link] = get_playlist_videos(link, links=True, titles=True, thumb=False)
            
            if "reverse" in item and item["reverse"] == True: res[link] = res[link][::-1]
    
    saveJSON(res, "./data/courses.json")
    time.sleep(loop_time)
    make_courses_links()

# make it (notifications by knowing time of save item link on server إشعارات نزول الحلقات بتسجيل وقت حفظها على الخادم)

# ===== دوال مساعدة =====
def auto_delete(download_id, wait_seconds=3600*8):
    def _delete():
        if download_id in downloads_status:
            print(f"🗑️ Download ID {download_id} اتغيرت القيمه")

            for link, dl_id in list(video_to_id.items()):
                if dl_id == download_id:
                    os.remove(FOLDER_PATH + link.split("=")[-1] + ".m4a")
                    del video_to_id[link]

            del downloads_status[download_id]
            print(f"🗑️ Download ID {download_id} تم حذفه تلقائيًا"
            )
            
    timer = threading.Timer(wait_seconds, _delete)
    timer.start()

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
        
        # 🔥 Headers محسّنة
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-us,en;q=0.5',
            'Sec-Fetch-Mode': 'navigate',
        },
        
        # 🔥 إعدادات إضافية مهمة
        'extractor_args': {
            'youtube': {
                'player_client': ['web'],  # جرب clients مختلفة
                'player_skip': ['webpage', 'configs'],
            }
        },
        
        # 🔥 استخدام IPv4 فقط (بعض السيرفرات IPv6 بتعمل مشاكل)
        'source_address': '0.0.0.0',
        
        # 🔥 retry في حالة الفشل
        'retries': 10,
        'fragment_retries': 10,
        
        # 🔥 تجاهل الأخطاء المؤقتة
        'ignoreerrors': False,
        
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': file_extension,
            'preferredquality': '192',
        }],
        
        # 🔥 استخدام cookies من متصفحك (اختياري لكن مفيد جداً)
        'cookiefile': '/app/cookies.txt',
    }
    
    downloads_status[download_id]["status"] = "before downloading 1"
    
    downloaded_file = None
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        downloads_status[download_id]["status"] = f"in downloading 1, video_url: {video_url}"
        try:
            info = ydl.extract_info(video_url, download=True)
            downloads_status[download_id]["status"] = "in downloading 2"
            downloaded_file = ydl.prepare_filename(info)
            downloads_status[download_id]["status"] = "in downloading 3"
            if not downloaded_file.endswith(f".{file_extension}"):
                downloads_status[download_id]["status"] = "in downloading 4"
                downloaded_file = os.path.splitext(downloaded_file)[0] + f".{file_extension}"
                downloads_status[download_id]["status"] = "in downloading 5"
        except Exception as e:
            downloads_status[download_id]["status"] = f"in downloading error, , video_url: {video_url}, error: {str(e)}"

    if downloaded_file is None:
        return None
    
    downloads_status[download_id]["whole_file"] = [
        downloaded_file.replace("./", "")
    ]
    
    downloads_status[download_id].update({
        "status": "done",
        "progress": 100,
    })

    return downloaded_file

def download_and_delete_after_delay(download_id, video_url):
    # شغل التحميل في thread
    def run_download():
        download(download_id, video_url)
        # بعد ما التحميل يخلص، شغل auto_delete
        auto_delete(download_id)  # هنا timer هيتعامل مع الانتظار

    downloads_status[download_id]["llllllllll"] = "aaaaaaaaaaaaaaa"
    threading.Thread(target=run_download).start()

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
        target=lambda: download_and_delete_after_delay(download_id, link)
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

@app.route("/all-data")
def get_all_data():
    return os.listdir(".")

@app.route("/data/<path:filename>")
def serve_data(filename):
    return send_from_directory(os.path.join(os.getcwd(), "data"), filename)

@app.route("/files")
def list_downloads():
    folder = os.path.abspath(FOLDER_PATH)
    if not os.path.exists(folder):
        return jsonify({"error": "المجلد غير موجود"})
    
    files = [f for f in os.listdir(folder) if os.path.isfile(os.path.join(folder, f))]
    return jsonify({"files": files})

@app.route("/delete-all")
def delete_all_files():
    folder = os.path.abspath(FOLDER_PATH)

    if not os.path.exists(folder):
        return jsonify({"message": "📂 المجلد غير موجود أصلاً"}), 200

    deleted_files = []
    errors = []

    for f in os.listdir(folder):
        file_path = os.path.join(folder, f)
        if os.path.isfile(file_path):
            try:
                os.remove(file_path)
                deleted_files.append(f)
            except Exception as e:
                errors.append({"file": f, "error": str(e)})

    # تنظيف الحالات كمان
    downloads_status.clear()
    video_to_id.clear()

    return jsonify({
        "message": "🗑️ تم مسح كل الملفات",
        "deleted_files": deleted_files,
        "errors": errors
    })

# ====== المعلومات ======
@app.route("/channel", methods=["GET"])
def channel_videos():
    channel_url = request.args.get("url")
    links = request.args.get("links", "true").lower() == "true"
    titles = request.args.get("titles", "true").lower() == "true"
    thumb = request.args.get("thumb", "true").lower() == "true"

    if not channel_url:
        return jsonify({"error": "Missing 'url' parameter"}), 400

    try:
        videos = get_channel_videos(channel_url, links=links, titles=titles, thumb=thumb)
        return jsonify(videos)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/playlist", methods=["GET"])
def playlist_videos():
    playlist_url = request.args.get("url")
    links = request.args.get("links", "true").lower() == "true"
    titles = request.args.get("titles", "true").lower() == "true"
    thumb = request.args.get("thumb", "true").lower() == "true"

    if not playlist_url:
        return jsonify({"error": "Missing 'url' parameter"}), 400

    try:
        videos = get_playlist_videos(playlist_url, links=links, titles=titles, thumb=thumb)
        return jsonify(videos)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/video", methods=["GET"])
def video_info():
    video_url = request.args.get("url")
    title = request.args.get("title", "true").lower() == "true"
    description = request.args.get("description", "true").lower() == "true"
    thumb = request.args.get("thumb", "true").lower() == "true"

    if not video_url:
        return jsonify({"error": "Missing 'url' parameter"}), 400

    try:
        info = get_video_info(video_url, title=title, description=description, thumb=thumb)
        return jsonify(info)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ===== تشغيل Flask =====
print("before main")

def start_background_jobs():
    print("🧵 Starting background thread...")
    threading.Thread(target=make_podcasts_links, daemon=True).start()

# ✅ شغل الثريد دايمًا سواء محلي أو على السيرفر
start_background_jobs()

if __name__ == "__main__":
    print("in main")
    app.run(port=8000, debug=False, use_reloader=False)
