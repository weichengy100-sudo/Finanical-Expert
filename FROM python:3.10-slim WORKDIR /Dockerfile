FROM python:3.10-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
# 這行最重要：強制自己跑，不用 gunicorn
CMD ["python", "main.py"]
