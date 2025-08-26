FROM python:3-alpine AS builder

WORKDIR /app

# تثبيت ffmpeg والحزم اللازمة للبناء
RUN apk add --no-cache ffmpeg gcc musl-dev libffi-dev

# إنشاء بيئة افتراضية
RUN python3 -m venv venv
ENV VIRTUAL_ENV=/app/venv
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

# تثبيت المتطلبات
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Stage 2
FROM python:3-alpine AS runner

WORKDIR /app

# تثبيت ffmpeg فقط (التشغيل)
RUN apk add --no-cache ffmpeg

# نسخ البيئة الافتراضية من مرحلة البناء
COPY --from=builder /app/venv venv
COPY app.py app.py
COPY session_name.session .

ENV VIRTUAL_ENV=/app/venv
ENV PATH="$VIRTUAL_ENV/bin:$PATH"
ENV FLASK_APP=app.py

EXPOSE 8000

# تشغيل Gunicorn بـ Worker واحد و4 Threads لتفادي مشكلة SQLite
CMD ["gunicorn", "--bind", ":8000", "--workers", "1", "--threads", "4", "app:app"]
