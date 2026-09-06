FROM python:3.11-slim

ENV TZ=Europe/Madrid
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

# tesseract-ocr: leer el texto que va DENTRO de una imagen. Un cartel
# publicitario es, sin esto, un mensaje vacío para el bot. Añade ~50 MB y se usa
# solo en primeros mensajes con imagen (~2 al día aquí, 0,61 s cada uno). Si se
# quita, `src/ocr.py` lo detecta y el bot funciona igual, sin leer imágenes.
RUN apt-get update && apt-get install -y --no-install-recommends \
        tzdata sqlite3 ca-certificates \
        tesseract-ocr tesseract-ocr-spa tesseract-ocr-eng \
    && ln -snf /usr/share/zoneinfo/$TZ /etc/localtime \
    && echo $TZ > /etc/timezone \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

RUN mkdir -p /app/data

COPY src/ /app/src/
COPY scripts/ /app/scripts/

CMD ["python", "-m", "src.main"]
