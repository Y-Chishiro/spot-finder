FROM python:3.11-slim

WORKDIR /app

# 依存関係ファイルをコピー
COPY requirements.txt .

# 依存関係のインストール
RUN pip install --no-cache-dir -r requirements.txt

# アプリケーションのソースコードをコピー
COPY ./app ./app

# 環境変数の設定
ENV PORT=8080

# アプリケーションの起動
CMD uvicorn app.main:app --host 0.0.0.0 --port $PORT