FROM python:3.11-slim

ENV TZ=Europe/Madrid
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

# tesseract-ocr: leer el texto que va DENTRO de una imagen. Un cartel
# publicitario es, sin esto, un mensaje vacío para el bot. Añade ~50 MB y se usa
# solo en primeros mensajes con imagen (~2 al día aquí, 0,61 s cada uno). Si se
# quita, `src/ocr.py` lo detecta y el bot funciona igual, sin leer imágenes.
# `apt-get upgrade`: la etiqueta python:3.11-slim tarda en recoger los parches de
# Debian; sin esto la imagen nueva hereda paquetes ya corregidos (vigía de
# seguridad del 4-oct-2026: perl-base, glib, libpcre2).
RUN apt-get update && apt-get upgrade -y && apt-get install -y --no-install-recommends \
        tzdata sqlite3 ca-certificates \
        tesseract-ocr tesseract-ocr-spa tesseract-ocr-eng \
    && ln -snf /usr/share/zoneinfo/$TZ /etc/localtime \
    && echo $TZ > /etc/timezone \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
# setuptools y wheel vienen con la imagen base y arrastran CVE propios (wheel,
# y jaraco.context dentro de setuptools): se ponen al día antes de instalar. pip
# NO: las versiones nuevas traen sus propias copias de urllib3 y msgpack con CVE.
RUN pip install --no-cache-dir -U setuptools wheel \
    && pip install --no-cache-dir -r requirements.txt

RUN mkdir -p /app/data

COPY src/ /app/src/
COPY scripts/ /app/scripts/

CMD ["python", "-m", "src.main"]
