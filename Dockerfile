# ===== Stage 1: Builder =====
FROM python:3.12-alpine AS builder

WORKDIR /app

# تثبيت ffmpeg والحزم اللازمة
RUN apk add --no-cache ffmpeg gcc musl-dev libffi-dev openssl-dev

# إنشاء virtual environment
RUN python3 -m venv venv
ENV VIRTUAL_ENV=/app/venv
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

# نسخ وتثبيت المتطلبات
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ===== Stage 2: Runner =====
FROM python:3.12-alpine AS runner

WORKDIR /app

# تثبيت ffmpeg فقط (تشغيل)
RUN apk add --no-cache ffmpeg

# نسخ البيئة الافتراضية من مرحلة البناء
COPY --from=builder /app/venv venv

# نسخ الملفات
COPY app.py .
COPY session_name.session .

ENV VIRTUAL_ENV=/app/venv
ENV PATH="$VIRTUAL_ENV/bin:$PATH"
ENV FLASK_APP=app.py

# فتح البورت
EXPOSE 8000

# تشغيل Gunicorn مع 1 worker و4 threads (للتعامل مع SQLite أو عمليات متزامنة)
ENV PYTHONUNBUFFERED=1
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "1", "--threads", "4", "app:app"]
