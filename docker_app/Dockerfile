FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple \
    PIP_TRUSTED_HOST=pypi.tuna.tsinghua.edu.cn \
    PYTHONPATH=/opt/zzs/docker_app:/workspace:/workspace/LivePhoto \
    APP_REPO_ROOT=/workspace \
    APP_STORAGE_ROOT=/storage

WORKDIR /opt/zzs/docker_app

COPY docker_app/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

RUN mkdir -p /storage/config /storage/data /workspace /workspace/LivePhoto

COPY docker_app /opt/zzs/docker_app
COPY bili_9pics_downloader.py /workspace/bili_9pics_downloader.py
COPY LivePhoto /workspace/LivePhoto

EXPOSE 7860

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "7860"]
