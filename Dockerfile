FROM python:3.12-slim
WORKDIR /app
COPY . .
RUN pip install --no-cache-dir -r requirements.txt gunicorn
ENV PORT=8080
CMD gunicorn -b 0.0.0.0:$PORT app:app
