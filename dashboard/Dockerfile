FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
COPY wheels/ /wheels/

RUN pip install --no-cache-dir --no-index --find-links=/wheels -r requirements.txt

COPY app.py .

EXPOSE 8501

CMD ["streamlit", "run", "app.py", "--server.address=0.0.0.0", "--server.port=8501", "--server.headless=true", "--browser.gatherUsageStats=false"]