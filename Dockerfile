# ===== Stage 1: Builder =====
FROM python:3.12-alpine AS builder

WORKDIR /app

# تثبيت ffmpeg والحزم اللازمة للبناء
RUN apk add --no-cache ffmpeg gcc musl-dev libffi-dev openssl-dev bash curl

# إنشاء بيئة افتراضية
RUN python3 -m venv venv
ENV VIRTUAL_ENV=/app/venv
ENV PATH="$VIRTUAL_ENV/bin:$PATH"
ENV PYTHONUNBUFFERED=1

# نسخ وتثبيت المتطلبات
COPY requirements.txt .
RUN pip install --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir --upgrade yt-dlp  # 🔹 تحديث yt-dlp لتجنب nsig error

# ===== Stage 2: Runner =====
FROM python:3.12-alpine AS runner

WORKDIR /app

# تثبيت ffmpeg فقط (لتشغيل الصوتيات)
RUN apk add --no-cache ffmpeg bash curl

# نسخ البيئة الافتراضية من مرحلة البناء
COPY --from=builder /app/venv venv

# نسخ الملفات المطلوبة للتشغيل
COPY app.py .
COPY session_name.session .

# تهيئة البيئة
ENV VIRTUAL_ENV=/app/venv
ENV PATH="$VIRTUAL_ENV/bin:$PATH"
ENV PYTHONUNBUFFERED=1
ENV FLASK_APP=app.py

# فتح البورت
EXPOSE 8000

# تشغيل Gunicorn مع 1 عامل و 4 ثريد
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "1", "--threads", "4", "app:app"]
