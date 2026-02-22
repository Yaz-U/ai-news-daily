@echo off
chcp 65001 > nul
set GEMINI_API_KEY=AIzaSyD43VT1wbtnko40MuRFmtI_OJq4t_Lg8pc
echo [%date% %time%] AI News Curation 実行開始
cd /d "C:\Users\user\Desktop\Claude\News"
python fetch_news.py >> logs\batch_run.log 2>&1
echo [%date% %time%] 実行完了
