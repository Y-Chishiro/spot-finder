#!/bin/bash

# 環境変数を.envから読み込む
source .env

# プロジェクトIDの設定
PROJECT_ID="spot-finder-450414"  # あなたのプロジェクトIDに変更してください

# Cloud Buildの実行
gcloud builds submit \
  --config cloudbuild.yaml \
  --project $PROJECT_ID \
  --substitutions _API_KEY="$API_KEY",_GOOGLE_MAPS_API_KEY="$GOOGLE_MAPS_API_KEY",_CUSTOM_SEARCH_API_KEY="$CUSTOM_SEARCH_API_KEY",_CUSTOM_SEARCH_CX="$CUSTOM_SEARCH_CX",_GOOGLE_API_KEY="$GOOGLE_API_KEY"