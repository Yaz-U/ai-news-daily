@echo off
chcp 65001 > nul
rem GEMINI_API_KEY は Windows 環境変数 (setx) で設定してください
echo [%date% %time%] AI News Curation 実行開始
cd /d "C:\Users\user\Desktop\Claude\News"
python fetch_news.py >> logs\batch_run.log 2>&1
echo [%date% %time%] 実行完了
