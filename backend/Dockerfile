FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && apt-get install -y build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/
RUN pip install -U pip && pip install -r requirements.txt

COPY . /app

# 静态文件收集
RUN python manage.py collectstatic --noinput

CMD ["gunicorn", "-c", "gunicorn.conf.py", "core.wsgi:application"]
