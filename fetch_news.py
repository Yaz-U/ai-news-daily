#!/usr/bin/env python3
"""
AI News Curation Script
アメリカのAI関連ニュースを収集し、日本語で要約してWebページを生成する
実行タイミング: 毎朝6:00, 12:00, 16:00, 20:00 (JST)
"""

import os
import sys
import json
import datetime
import feedparser
import requests
import re
from pathlib import Path
from google import genai
from google.genai import types

# Windowsコンソールの文字化け対策
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# ===== 設定 =====
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
WEB_DIR = BASE_DIR / "web"
LOG_DIR = BASE_DIR / "logs"

# 必要なディレクトリを自動作成
DATA_DIR.mkdir(exist_ok=True)
WEB_DIR.mkdir(exist_ok=True)
LOG_DIR.mkdir(exist_ok=True)

# Gemini APIキー (環境変数から取得)
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

# FTP設定 (環境変数から取得 / GitHub Actions Secrets で設定)
FTP_HOST     = os.environ.get("FTP_HOST", "")
FTP_USER     = os.environ.get("FTP_USER", "")
FTP_PASSWORD = os.environ.get("FTP_PASSWORD", "")
FTP_REMOTE_PATH = os.environ.get("FTP_REMOTE_PATH", "/")

# ===== RSSフィード設定 =====

# 【カテゴリ1】主要テックメディア（AI専門セクション）
RSS_FEEDS_MEDIA = [
    ("TechCrunch AI",    "https://techcrunch.com/category/artificial-intelligence/feed/"),
    ("VentureBeat",      "https://venturebeat.com/feed/"),
    ("The Verge AI",     "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml"),
    ("Wired",            "https://www.wired.com/feed/rss"),
    ("MIT Tech Review",  "https://www.technologyreview.com/feed/"),
    ("ZDNet AI",         "https://www.zdnet.com/topic/artificial-intelligence/rss.xml"),
    ("InfoQ AI/ML",      "https://feed.infoq.com/ai-ml-data-eng"),
    ("IEEE Spectrum",    "https://spectrum.ieee.org/feeds/feed.rss"),
    ("AI Business",      "https://aibusiness.com/rss.xml"),
    ("Analytics Vidhya", "https://www.analyticsvidhya.com/feed/"),
    ("CNBC Tech",        "https://www.cnbc.com/id/19854910/device/rss/rss.html"),
]

# 【カテゴリ2】AI業界キーマン・企業公式ブログ（動作確認済み）
RSS_FEEDS_KEYMAN = [
    # 企業公式ブログ
    ("Google DeepMind",   "https://deepmind.google/blog/rss.xml"),
    ("NVIDIA Blog",       "https://blogs.nvidia.com/feed/"),
    ("Microsoft AI",      "https://blogs.microsoft.com/feed/"),
    ("Hugging Face",      "https://huggingface.co/blog/feed.xml"),
    ("Meta AI/Eng",       "https://engineering.fb.com/category/ai-research/feed/"),
    # AI専門ニュースレター（業界識者の見解を含む）
    ("Last Week in AI",   "https://lastweekin.ai/feed"),             # 毎週AI業界まとめ
    ("Import AI",         "https://importai.substack.com/feed"),     # Jack Clark (Anthropic共同創業者)
    # AI経営者・研究者のブログ
    ("Sam Altman Blog",   "http://blog.samaltman.com/posts.atom"),   # OpenAI CEO
    ("Andrej Karpathy",   "https://karpathy.bearblog.dev/feed/"),    # 元Tesla AI・OpenAI
]

# 全フィードをまとめる
RSS_FEEDS = RSS_FEEDS_MEDIA + RSS_FEEDS_KEYMAN

# 記事の新しさフィルタ: 24時間以内のみ取得
MAX_ARTICLE_AGE_HOURS = 24

# キーワードフィルタ（AI関連記事を選別）
AI_KEYWORDS = [
    "AI", "artificial intelligence", "machine learning", "deep learning",
    "LLM", "large language model", "GPT", "ChatGPT", "Claude", "Gemini",
    "OpenAI", "Anthropic", "Google DeepMind", "Meta AI", "Microsoft AI",
    "neural network", "generative AI", "foundation model", "AGI",
    "robotics", "autonomous", "computer vision", "natural language",
    "Nvidia", "GPU", "semiconductor", "chip", "data center",
]


def is_ai_related(title: str, summary: str = "") -> bool:
    """記事がAI関連かどうかを判定"""
    text = (title + " " + summary).lower()
    return any(kw.lower() in text for kw in AI_KEYWORDS)


def parse_pub_date(entry) -> datetime.datetime | None:
    """feedparserエントリから公開日時をdatetimeで取得（タイムゾーン付き）"""
    import email.utils, time as time_mod
    # published_parsed / updated_parsed (time.struct_time) を優先
    for attr in ("published_parsed", "updated_parsed"):
        t = getattr(entry, attr, None)
        if t:
            try:
                ts = time_mod.mktime(t)
                return datetime.datetime.fromtimestamp(ts, tz=datetime.timezone.utc)
            except Exception:
                pass
    # 文字列フォールバック
    for attr in ("published", "updated"):
        s = getattr(entry, attr, None)
        if s:
            try:
                # RFC 2822 形式
                t = email.utils.parsedate_to_datetime(s)
                return t.astimezone(datetime.timezone.utc)
            except Exception:
                pass
            try:
                # ISO 8601 形式
                s_clean = re.sub(r"(\+\d{2}):(\d{2})$", r"+\1\2", s)
                return datetime.datetime.fromisoformat(s_clean).astimezone(datetime.timezone.utc)
            except Exception:
                pass
    return None


def fetch_articles(max_per_feed: int = 5) -> list[dict]:
    """RSSフィードからAI関連記事を収集（直近24時間以内のみ）"""
    articles = []
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    cutoff = now_utc - datetime.timedelta(hours=MAX_ARTICLE_AGE_HOURS)

    for feed_name, feed_url in RSS_FEEDS:
        try:
            feed = feedparser.parse(feed_url)
            count = 0
            skipped_old = 0
            for entry in feed.entries:
                if count >= max_per_feed:
                    break
                title = entry.get("title", "")
                summary = entry.get("summary", entry.get("description", ""))
                summary_clean = re.sub(r"<[^>]+>", "", summary)[:500]

                # ── 日付フィルタ ──
                pub_dt = parse_pub_date(entry)
                if pub_dt and pub_dt < cutoff:
                    skipped_old += 1
                    continue  # 古い記事はスキップ

                pub_str = pub_dt.strftime("%Y-%m-%d %H:%M UTC") if pub_dt else "日付不明"

                if is_ai_related(title, summary_clean):
                    articles.append({
                        "source": feed_name,
                        "title": title,
                        "url": entry.get("link", ""),
                        "summary": summary_clean,
                        "published": pub_str,
                        "pub_dt": pub_dt.isoformat() if pub_dt else "",
                    })
                    count += 1

            print(f"[INFO] {feed_name:<20} {count}件取得 / 古記事スキップ:{skipped_old}件")
        except Exception as e:
            print(f"[WARNING] {feed_name} の取得に失敗: {e}")
            continue

    # 重複除去（URLベース）→ 新しい順にソート
    seen = set()
    unique = []
    for art in articles:
        if art["url"] not in seen:
            seen.add(art["url"])
            unique.append(art)

    unique.sort(key=lambda a: a.get("pub_dt", ""), reverse=True)
    print(f"[INFO] 合計 {len(unique)} 件（直近{MAX_ARTICLE_AGE_HOURS}時間以内）")
    return unique


def summarize_with_gemini(articles: list[dict]) -> dict:
    """Gemini APIを使って記事を日本語要約（無料枠対応）"""
    if not GEMINI_API_KEY:
        return _dummy_summary(articles)

    client = genai.Client(api_key=GEMINI_API_KEY)

    # 記事情報をテキスト化
    articles_text = ""
    for i, art in enumerate(articles[:10], 1):
        articles_text += f"""
【記事{i}】
タイトル: {art['title']}
ソース: {art['source']}
URL: {art['url']}
概要: {art['summary'][:300]}
---
"""

    prompt_news = f"""
あなたはAI分野の専門的なニュースキュレーターです。
以下はアメリカの主要テックメディアから収集した最新のAI関連ニュース記事です。

{articles_text}

【タスク1: ニュース要約】
上記の記事の中から特に重要なニュースを選び、以下の形式で400字程度の日本語要約を作成してください。
- 各ニュースのポイントを簡潔に列挙
- 業界への影響・意義も含める
- 専門用語は適切に解説

【タスク2: メディア・専門家の意見分析】
上記の記事に含まれる記者・専門家の意見・見解を分析し、400字程度で以下を含む日本語要約を作成してください。
- ポジティブな意見（技術的進歩への期待、ビジネス機会など）
- ネガティブな意見（リスク、規制懸念、雇用問題など）
- 中立・バランスの取れた見解

必ずJSONのみで回答してください（説明文は不要）：
{{
  "news_summary": "ニュース要約（400字程度）",
  "opinion_summary": "意見・見解の要約（400字程度）",
  "sentiment": {{
    "positive": "ポジティブな意見の要点（100字程度）",
    "negative": "ネガティブな意見の要点（100字程度）",
    "neutral": "中立的な見解の要点（100字程度）"
  }},
  "top_articles": [
    {{"rank": 1, "title": "記事タイトル", "source": "ソース名", "url": "URL", "point": "重要ポイント（50字）"}},
    {{"rank": 2, "title": "記事タイトル", "source": "ソース名", "url": "URL", "point": "重要ポイント（50字）"}},
    {{"rank": 3, "title": "記事タイトル", "source": "ソース名", "url": "URL", "point": "重要ポイント（50字）"}},
    {{"rank": 4, "title": "記事タイトル", "source": "ソース名", "url": "URL", "point": "重要ポイント（50字）"}},
    {{"rank": 5, "title": "記事タイトル", "source": "ソース名", "url": "URL", "point": "重要ポイント（50字）"}},
    {{"rank": 6, "title": "記事タイトル", "source": "ソース名", "url": "URL", "point": "重要ポイント（50字）"}},
    {{"rank": 7, "title": "記事タイトル", "source": "ソース名", "url": "URL", "point": "重要ポイント（50字）"}},
    {{"rank": 8, "title": "記事タイトル", "source": "ソース名", "url": "URL", "point": "重要ポイント（50字）"}},
    {{"rank": 9, "title": "記事タイトル", "source": "ソース名", "url": "URL", "point": "重要ポイント（50字）"}},
    {{"rank": 10, "title": "記事タイトル", "source": "ソース名", "url": "URL", "point": "重要ポイント（50字）"}}
  ]
}}
"""

    # リトライ対象のモデル順（上限に達した場合に次を試す）
    models_to_try = [
        "gemini-2.0-flash",
        "gemini-2.0-flash-lite",
        "gemini-2.5-flash",
        "gemini-flash-lite-latest",
    ]

    for model_name in models_to_try:
        try:
            print(f"[INFO] モデル試行: {model_name}")
            response = client.models.generate_content(
                model=model_name,
                contents=prompt_news,
            )
            response_text = response.text

            # ```json ... ``` ブロックを除去してJSONを抽出
            response_text = re.sub(r"```json\s*", "", response_text)
            response_text = re.sub(r"```\s*", "", response_text)
            json_match = re.search(r'\{[\s\S]*\}', response_text)
            if json_match:
                result = json.loads(json_match.group())
                print(f"[INFO] 要約成功: {model_name}")
                return result
            else:
                raise ValueError("JSONが見つかりません")

        except Exception as e:
            err_str = str(e)
            if "429" in err_str or "quota" in err_str.lower():
                print(f"[WARNING] {model_name} レート制限。次のモデルを試します...")
                continue
            else:
                print(f"[ERROR] Gemini API エラー ({model_name}): {e}")
                break

    print("[ERROR] 全モデルで失敗しました")
    return _dummy_summary(articles)


def _dummy_summary(articles: list[dict]) -> dict:
    """APIキーがない場合のダミーデータ（テスト用）"""
    top = articles[:10]
    top_articles = []
    for i, art in enumerate(top, 1):
        top_articles.append({
            "rank": i,
            "title": art["title"],
            "source": art["source"],
            "url": art["url"],
            "point": art["summary"][:50] + "..."
        })

    return {
        "news_summary": "【テストモード】APIキーが設定されていないため、実際の要約は生成されていません。GEMINI_API_KEY環境変数を設定してください。収集された記事のタイトルのみ表示しています。",
        "opinion_summary": "【テストモード】メディアの意見分析はAPIキーが必要です。実際の運用時はGemini APIキーを設定することで、ポジティブ・ネガティブ・中立の意見分析が自動生成されます。",
        "sentiment": {
            "positive": "APIキー設定後に自動生成されます",
            "negative": "APIキー設定後に自動生成されます",
            "neutral": "APIキー設定後に自動生成されます"
        },
        "top_articles": top_articles,
        "joho_picks": []
    }


def generate_joho_commentary(articles: list[dict]) -> list[dict]:
    """
    NewsPicks「週刊ジョーホー番組」風のAIニュース解説を生成する。
    森川潤（NY支局長）・後藤直義（編集委員/NY支局）の目線を模倣。
    - NYからの俯瞰的・グローバル視点
    - ビジネス・経済インパクト重視
    - 技術ハイプに流されない逆張り・批判的目線
    - 【】囲みの衝撃的見出し
    - 読者に「なぜそれが重要か」を問い直す構成
    """
    if not GEMINI_API_KEY or not articles:
        return []

    client = genai.Client(api_key=GEMINI_API_KEY)

    articles_text = ""
    for i, art in enumerate(articles[:15], 1):
        articles_text += f"""
【記事{i}】
タイトル: {art['title']}
ソース: {art['source']}
URL: {art['url']}
概要: {art['summary'][:400]}
---
"""

    prompt = f"""
あなたはニューヨーク在住の日本人ジャーナリストです。
アメリカのAI業界を最前線で取材し、日本のビジネスパーソン向けに「本当に重要なこと」を伝えることを使命としています。

【あなたのスタンス・文体】
- NYからの俯瞰的・グローバル視点。日本のメディアが伝えない「現地の空気感」を大切にする
- 技術の表面的なスゴさではなく、ビジネス・経済・社会への実際のインパクトを問う
- AIブームに乗っかった楽観論には懐疑的。「本当にそうか？」と問い直す逆張り姿勢
- 大企業・スタートアップの「建前」と「本音」を見抜く
- 読者に「なぜこれが自分ごとなのか」を伝える
- 断言する。「〜かもしれません」より「〜です」「〜でした」

【記事の形式】
- 見出しは【】で囲む（例：【現実】【衝撃】【ミニ教養】【絶句】【完全解説】【NY発】【独自分析】）
- 見出しは15字以内で読者の興味を引くキャッチーなもの
- 本文は250〜350字の日本語
- 最後に「■ なぜ重要か」として1〜2文で核心をまとめる

以下のニュース記事の中から、あなたの目線で特に重要・興味深いと思う記事を3〜4本選び、
それぞれについて上記スタイルで解説記事を書いてください。

{articles_text}

必ずJSONのみで回答してください（説明文・マークダウン不要）：
[
  {{
    "headline": "【〇〇】見出しテキスト",
    "source_title": "参照した記事の元タイトル",
    "source_url": "参照した記事のURL",
    "source_name": "メディア名",
    "body": "本文（250〜350字）",
    "why_matters": "■ なぜ重要か：（1〜2文）"
  }},
  ...
]
"""

    models_to_try = [
        "gemini-2.0-flash",
        "gemini-2.0-flash-lite",
        "gemini-2.5-flash",
        "gemini-flash-lite-latest",
    ]

    for model_name in models_to_try:
        try:
            print(f"[INFO] 週刊ジョーホー風解説 モデル試行: {model_name}")
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
            )
            response_text = response.text

            # ```json ... ``` ブロックを除去してJSONを抽出
            response_text = re.sub(r"```json\s*", "", response_text)
            response_text = re.sub(r"```\s*", "", response_text)
            json_match = re.search(r'\[[\s\S]*\]', response_text)
            if json_match:
                picks = json.loads(json_match.group())
                print(f"[INFO] 週刊ジョーホー風解説 生成成功: {len(picks)}本 ({model_name})")
                return picks
            else:
                raise ValueError("JSONリストが見つかりません")

        except Exception as e:
            err_str = str(e)
            if "429" in err_str or "quota" in err_str.lower():
                print(f"[WARNING] {model_name} レート制限。次のモデルを試します...")
                continue
            else:
                print(f"[ERROR] 週刊ジョーホー風解説 エラー ({model_name}): {e}")
                break

    print("[WARNING] 週刊ジョーホー風解説の生成に失敗しました")
    return []


def get_time_slot() -> str:
    """現在のJST時間に基づいてタイムスロットを返す"""
    jst = datetime.timezone(datetime.timedelta(hours=9))
    now = datetime.datetime.now(jst)
    hour = now.hour
    if 5 <= hour < 11:
        return "朝"
    elif 11 <= hour < 15:
        return "昼"
    elif 15 <= hour < 18:
        return "夕方"
    else:
        return "夜"


def upload_to_ftp(html_path: Path):
    """生成した index.html をさくらサーバーへFTPアップロード"""
    if not FTP_HOST or not FTP_USER or not FTP_PASSWORD:
        print("[INFO] FTP設定なし。アップロードをスキップします")
        return
    import ftplib
    try:
        print(f"[INFO] FTPアップロード開始: {FTP_HOST}")
        with ftplib.FTP(timeout=30) as ftp:
            ftp.connect(FTP_HOST, 21)
            ftp.set_pasv(True)  # パッシブモード（NAT/クラウド環境対応）
            ftp.login(FTP_USER, FTP_PASSWORD)
            print(f"[INFO] FTPログイン成功。ディレクトリ移動: {FTP_REMOTE_PATH}")
            ftp.cwd(FTP_REMOTE_PATH)
            with open(html_path, "rb") as f:
                ftp.storbinary("STOR index.html", f)
        print(f"[INFO] FTPアップロード完了: {FTP_REMOTE_PATH}/index.html")
    except Exception as e:
        print(f"[ERROR] FTPアップロード失敗: {type(e).__name__}: {e}")


def save_data(summary: dict, articles: list[dict]) -> Path:
    """データをJSONで保存"""
    jst = datetime.timezone(datetime.timedelta(hours=9))
    now = datetime.datetime.now(jst)
    timestamp = now.strftime("%Y%m%d_%H%M")

    data = {
        "timestamp": now.isoformat(),
        "time_slot": get_time_slot(),
        "summary": summary,
        "raw_articles": articles[:15],
    }

    filepath = DATA_DIR / f"news_{timestamp}.json"
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    # 最新データも上書き保存
    latest_path = DATA_DIR / "latest.json"
    with open(latest_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"[INFO] データ保存: {filepath}")
    return filepath


def load_history(days: int = 3) -> list[dict]:
    """過去のデータを読み込む（最新N件）"""
    history = []
    data_files = sorted(DATA_DIR.glob("news_*.json"), reverse=True)

    for f in data_files[:12]:  # 最大12件（3日分×4回）
        try:
            with open(f, "r", encoding="utf-8") as fp:
                data = json.load(fp)
                history.append(data)
        except Exception:
            continue

    return history


def generate_html(current_data: dict, history: list[dict]) -> Path:
    """HTMLページを生成"""
    jst = datetime.timezone(datetime.timedelta(hours=9))
    now = datetime.datetime.now(jst)

    summary = current_data["summary"]
    time_slot = current_data["time_slot"]
    timestamp_str = now.strftime("%Y年%m月%d日 %H:%M JST")

    # トップ記事のHTML生成
    top_articles_html = ""
    for art in summary.get("top_articles", []):
        top_articles_html += f"""
        <div class="article-card">
          <span class="rank">#{art['rank']}</span>
          <div class="article-content">
            <a href="{art['url']}" target="_blank" rel="noopener noreferrer" class="article-title">
              {art['title']}
            </a>
            <div class="article-meta">
              <span class="source-tag">{art['source']}</span>
            </div>
            <p class="article-point">{art['point']}</p>
          </div>
        </div>
"""

    # 履歴タブのHTML生成
    history_tabs_html = ""
    history_content_html = ""

    for i, hist in enumerate(history[:8]):
        hist_time = datetime.datetime.fromisoformat(hist["timestamp"])
        hist_label = hist_time.strftime("%m/%d %H:%M")
        hist_slot = hist.get("time_slot", "")
        active = "active" if i == 0 else ""

        history_tabs_html += f'<button class="hist-tab {active}" onclick="showHistory({i})">{hist_label} {hist_slot}</button>\n'

        hist_top_html = ""
        for art in hist["summary"].get("top_articles", [])[:5]:
            hist_top_html += f"""
              <div class="hist-article">
                <span class="hist-rank">#{art['rank']}</span>
                <a href="{art['url']}" target="_blank" rel="noopener noreferrer">{art['title']}</a>
                <span class="hist-source">{art['source']}</span>
              </div>
"""

        display = "block" if i == 0 else "none"
        history_content_html += f"""
        <div id="hist-{i}" class="hist-content" style="display:{display}">
          <h4>{hist_label} {hist_slot}版</h4>
          <div class="hist-summary">{hist['summary'].get('news_summary', '')[:200]}...</div>
          <div class="hist-articles">{hist_top_html}</div>
        </div>
"""

    # 週刊ジョーホー風解説のHTML生成
    joho_picks = summary.get("joho_picks", [])
    joho_html = ""
    for pick in joho_picks:
        headline = pick.get("headline", "")
        body = pick.get("body", "")
        why_matters = pick.get("why_matters", "")
        source_title = pick.get("source_title", "")
        source_url = pick.get("source_url", "#")
        source_name = pick.get("source_name", "")
        joho_html += f"""
        <div class="joho-card">
          <div class="joho-headline">{headline}</div>
          <div class="joho-body">{body}</div>
          <div class="joho-why">{why_matters}</div>
          <div class="joho-source">
            <span class="joho-source-label">📰 元記事:</span>
            <a href="{source_url}" target="_blank" rel="noopener noreferrer" class="joho-source-link">{source_title}</a>
            <span class="joho-source-name">{source_name}</span>
          </div>
        </div>
"""

    sentiment = summary.get("sentiment", {})

    html_content = f"""<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta http-equiv="refresh" content="1800"> <!-- 30分ごとに自動更新 -->
  <title>AI News Daily - アメリカAI最新ニュース</title>
  <style>
    :root {{
      --bg: #0a0e1a;
      --surface: #111827;
      --surface2: #1a2235;
      --border: #2d3748;
      --accent: #6366f1;
      --accent2: #818cf8;
      --text: #e2e8f0;
      --text2: #94a3b8;
      --positive: #10b981;
      --negative: #ef4444;
      --neutral: #f59e0b;
      --card-hover: #1e2d45;
    }}

    * {{ margin: 0; padding: 0; box-sizing: border-box; }}

    body {{
      font-family: 'Segoe UI', 'Noto Sans JP', sans-serif;
      background: var(--bg);
      color: var(--text);
      line-height: 1.7;
      min-height: 100vh;
    }}

    /* ヘッダー */
    header {{
      background: linear-gradient(135deg, #0f172a 0%, #1e1b4b 50%, #0f172a 100%);
      border-bottom: 1px solid var(--accent);
      padding: 0;
      position: sticky;
      top: 0;
      z-index: 100;
      box-shadow: 0 4px 20px rgba(99, 102, 241, 0.3);
    }}

    .header-inner {{
      max-width: 1200px;
      margin: 0 auto;
      padding: 16px 24px;
      display: flex;
      align-items: center;
      justify-content: space-between;
    }}

    .logo {{
      display: flex;
      align-items: center;
      gap: 12px;
    }}

    .logo-icon {{
      width: 40px;
      height: 40px;
      background: linear-gradient(135deg, var(--accent), #a855f7);
      border-radius: 10px;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 20px;
    }}

    .logo-text h1 {{
      font-size: 1.4rem;
      font-weight: 700;
      background: linear-gradient(90deg, var(--accent2), #c084fc);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      background-clip: text;
    }}

    .logo-text p {{
      font-size: 0.75rem;
      color: var(--text2);
    }}

    .presented-by {{
      font-size: 0.75rem;
      color: var(--text2);
      margin-left: 16px;
      align-self: flex-end;
      padding-bottom: 2px;
    }}

    .presented-by a {{
      color: var(--accent2);
      text-decoration: none;
      font-weight: 500;
      transition: color 0.2s;
    }}

    .presented-by a:hover {{
      color: #c084fc;
      text-decoration: underline;
    }}

    .update-info {{
      text-align: right;
    }}

    .time-slot-badge {{
      display: inline-block;
      padding: 4px 12px;
      background: var(--accent);
      border-radius: 20px;
      font-size: 0.8rem;
      font-weight: 600;
      margin-bottom: 4px;
    }}

    .update-time {{
      font-size: 0.75rem;
      color: var(--text2);
    }}

    /* メインコンテンツ */
    main {{
      max-width: 1200px;
      margin: 0 auto;
      padding: 32px 24px;
    }}

    /* セクションヘッダー */
    .section-header {{
      display: flex;
      align-items: center;
      gap: 10px;
      margin-bottom: 20px;
    }}

    .section-header .icon {{
      width: 32px;
      height: 32px;
      background: var(--accent);
      border-radius: 8px;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 16px;
    }}

    .section-header h2 {{
      font-size: 1.2rem;
      font-weight: 600;
      color: var(--text);
    }}

    /* グリッドレイアウト */
    .grid-2 {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 24px;
      margin-bottom: 32px;
    }}

    @media (max-width: 768px) {{
      .grid-2 {{ grid-template-columns: 1fr; }}
    }}

    /* カード */
    .card {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 16px;
      padding: 24px;
      margin-bottom: 24px;
    }}

    .card:hover {{
      border-color: var(--accent);
      transition: border-color 0.2s;
    }}

    /* ニュース要約 */
    .summary-text {{
      font-size: 0.95rem;
      color: var(--text);
      line-height: 1.8;
      white-space: pre-wrap;
    }}

    /* センチメント */
    .sentiment-grid {{
      display: grid;
      grid-template-columns: 1fr 1fr 1fr;
      gap: 12px;
      margin-top: 20px;
    }}

    @media (max-width: 640px) {{
      .sentiment-grid {{ grid-template-columns: 1fr; }}
    }}

    .sentiment-card {{
      background: var(--surface2);
      border-radius: 12px;
      padding: 16px;
      border-left: 4px solid;
    }}

    .sentiment-card.positive {{ border-left-color: var(--positive); }}
    .sentiment-card.negative {{ border-left-color: var(--negative); }}
    .sentiment-card.neutral {{ border-left-color: var(--neutral); }}

    .sentiment-label {{
      font-size: 0.75rem;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.1em;
      margin-bottom: 8px;
    }}

    .sentiment-card.positive .sentiment-label {{ color: var(--positive); }}
    .sentiment-card.negative .sentiment-label {{ color: var(--negative); }}
    .sentiment-card.neutral .sentiment-label {{ color: var(--neutral); }}

    .sentiment-text {{
      font-size: 0.85rem;
      color: var(--text2);
      line-height: 1.6;
    }}

    /* 記事リスト */
    .article-card {{
      display: flex;
      align-items: flex-start;
      gap: 16px;
      padding: 16px;
      background: var(--surface2);
      border-radius: 12px;
      margin-bottom: 12px;
      border: 1px solid transparent;
      transition: all 0.2s;
    }}

    .article-card:hover {{
      border-color: var(--accent);
      background: var(--card-hover);
    }}

    .rank {{
      font-size: 1.2rem;
      font-weight: 700;
      color: var(--accent2);
      min-width: 40px;
      text-align: center;
    }}

    .article-content {{ flex: 1; }}

    .article-title {{
      font-size: 0.95rem;
      font-weight: 600;
      color: var(--text);
      text-decoration: none;
      display: block;
      margin-bottom: 6px;
      transition: color 0.2s;
    }}

    .article-title:hover {{ color: var(--accent2); }}

    .article-meta {{
      display: flex;
      align-items: center;
      gap: 8px;
      margin-bottom: 6px;
    }}

    .source-tag {{
      display: inline-block;
      padding: 2px 8px;
      background: rgba(99, 102, 241, 0.2);
      color: var(--accent2);
      border-radius: 4px;
      font-size: 0.75rem;
      font-weight: 500;
    }}

    .article-point {{
      font-size: 0.85rem;
      color: var(--text2);
    }}

    /* 履歴 */
    .hist-tabs {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-bottom: 16px;
    }}

    .hist-tab {{
      padding: 6px 14px;
      background: var(--surface2);
      border: 1px solid var(--border);
      border-radius: 8px;
      color: var(--text2);
      font-size: 0.8rem;
      cursor: pointer;
      transition: all 0.2s;
    }}

    .hist-tab:hover, .hist-tab.active {{
      background: var(--accent);
      color: white;
      border-color: var(--accent);
    }}

    .hist-summary {{
      font-size: 0.85rem;
      color: var(--text2);
      margin-bottom: 12px;
      padding: 12px;
      background: var(--surface2);
      border-radius: 8px;
    }}

    .hist-article {{
      display: flex;
      align-items: center;
      gap: 8px;
      padding: 8px 0;
      border-bottom: 1px solid var(--border);
      font-size: 0.85rem;
    }}

    .hist-rank {{ color: var(--accent2); font-weight: 700; min-width: 30px; }}
    .hist-article a {{ color: var(--text); text-decoration: none; flex: 1; }}
    .hist-article a:hover {{ color: var(--accent2); }}
    .hist-source {{
      padding: 2px 6px;
      background: var(--surface2);
      border-radius: 4px;
      font-size: 0.7rem;
      color: var(--text2);
    }}

    /* フッター */
    footer {{
      text-align: center;
      padding: 32px;
      border-top: 1px solid var(--border);
      color: var(--text2);
      font-size: 0.8rem;
    }}

    /* スケジュール情報 */
    .schedule-info {{
      display: flex;
      gap: 16px;
      flex-wrap: wrap;
      margin-top: 12px;
    }}

    .schedule-item {{
      display: flex;
      align-items: center;
      gap: 6px;
      font-size: 0.8rem;
      color: var(--text2);
    }}

    .schedule-dot {{
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background: var(--accent);
    }}

    /* ローディングアニメーション */
    @keyframes pulse {{
      0%, 100% {{ opacity: 1; }}
      50% {{ opacity: 0.5; }}
    }}

    .live-dot {{
      display: inline-block;
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background: #10b981;
      animation: pulse 2s infinite;
      margin-right: 4px;
    }}

    /* ニュース見出し風解説セクション */
    .joho-section-header {{
      display: flex;
      align-items: center;
      gap: 12px;
      margin-bottom: 8px;
    }}

    .joho-section-badge {{
      display: inline-flex;
      align-items: center;
      gap: 6px;
      background: linear-gradient(135deg, #7c3aed, #db2777);
      color: white;
      font-size: 0.75rem;
      font-weight: 700;
      padding: 4px 12px;
      border-radius: 20px;
      letter-spacing: 0.05em;
    }}

    .joho-section-desc {{
      font-size: 0.78rem;
      color: var(--text2);
      margin-bottom: 20px;
      padding: 10px 14px;
      background: rgba(124, 58, 237, 0.08);
      border-left: 3px solid #7c3aed;
      border-radius: 0 8px 8px 0;
    }}

    .joho-card {{
      background: var(--surface2);
      border: 1px solid #2d1f4e;
      border-radius: 14px;
      padding: 22px 24px;
      margin-bottom: 16px;
      position: relative;
      transition: all 0.2s;
    }}

    .joho-card:hover {{
      border-color: #7c3aed;
      background: #1a1535;
    }}

    .joho-card::before {{
      content: '';
      position: absolute;
      top: 0;
      left: 0;
      width: 4px;
      height: 100%;
      background: linear-gradient(180deg, #7c3aed, #db2777);
      border-radius: 14px 0 0 14px;
    }}

    .joho-headline {{
      font-size: 1.05rem;
      font-weight: 700;
      color: #c4b5fd;
      margin-bottom: 12px;
      line-height: 1.4;
    }}

    .joho-body {{
      font-size: 0.9rem;
      color: var(--text);
      line-height: 1.85;
      margin-bottom: 14px;
      white-space: pre-wrap;
    }}

    .joho-why {{
      font-size: 0.85rem;
      color: #f0abfc;
      font-weight: 600;
      margin-bottom: 12px;
      padding: 10px 14px;
      background: rgba(219, 39, 119, 0.1);
      border-radius: 8px;
      line-height: 1.6;
    }}

    .joho-source {{
      display: flex;
      align-items: center;
      gap: 8px;
      flex-wrap: wrap;
      font-size: 0.78rem;
      color: var(--text2);
      border-top: 1px solid #2d1f4e;
      padding-top: 10px;
    }}

    .joho-source-label {{
      color: var(--text2);
    }}

    .joho-source-link {{
      color: #a78bfa;
      text-decoration: none;
      flex: 1;
      min-width: 0;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }}

    .joho-source-link:hover {{
      color: #c4b5fd;
      text-decoration: underline;
    }}

    .joho-source-name {{
      display: inline-block;
      padding: 2px 8px;
      background: rgba(124, 58, 237, 0.2);
      color: #a78bfa;
      border-radius: 4px;
      font-size: 0.72rem;
      font-weight: 500;
      white-space: nowrap;
    }}
  </style>
</head>
<body>
  <header>
    <div class="header-inner">
      <div class="logo">
        <div class="logo-icon">🤖</div>
        <div class="logo-text">
          <h1>AI News Daily</h1>
          <p>アメリカ発・AI最新ニュース自動キュレーション</p>
        </div>
        <div class="presented-by">
          <a href="../../index.html">Presented by INCURATOR, Inc</a>
        </div>
      </div>
      <div class="update-info">
        <div class="time-slot-badge"><span class="live-dot"></span>{time_slot}版</div>
        <div class="update-time">更新: {timestamp_str}</div>
      </div>
    </div>
  </header>

  <main>
    <!-- ニュース要約 + 意見分析 -->
    <div class="grid-2">
      <!-- ニュース要約 -->
      <div class="card">
        <div class="section-header">
          <div class="icon">📰</div>
          <h2>今の注目AIニュース要約</h2>
        </div>
        <p class="summary-text">{summary.get('news_summary', 'データを取得中...')}</p>
      </div>

      <!-- 意見・見解 -->
      <div class="card">
        <div class="section-header">
          <div class="icon">💬</div>
          <h2>メディア・専門家の見解</h2>
        </div>
        <p class="summary-text">{summary.get('opinion_summary', 'データを取得中...')}</p>

        <!-- センチメント分析 -->
        <div class="sentiment-grid">
          <div class="sentiment-card positive">
            <div class="sentiment-label">✅ ポジティブ</div>
            <div class="sentiment-text">{sentiment.get('positive', '-')}</div>
          </div>
          <div class="sentiment-card negative">
            <div class="sentiment-label">⚠️ ネガティブ</div>
            <div class="sentiment-text">{sentiment.get('negative', '-')}</div>
          </div>
          <div class="sentiment-card neutral">
            <div class="sentiment-label">⚖️ 中立</div>
            <div class="sentiment-text">{sentiment.get('neutral', '-')}</div>
          </div>
        </div>
      </div>
    </div>

    <!-- トップ記事 -->
    <div class="card">
      <div class="section-header">
        <div class="icon">🏆</div>
        <h2>注目記事 TOP 10</h2>
      </div>
      {top_articles_html}
    </div>

    <!-- 週刊ジョーホー風 AI解説 -->
    <div class="card">
      <div class="joho-section-header">
        <div class="joho-section-badge">📺 今週のAIが選んだAI関連ニュースのAI解説</div>
      </div>
      <div class="joho-section-desc">
        世界のAIニュースをAIに収集してもらってからのAIによる面白そうな記事をピックアップしてからのAIによるNews解説！！
      </div>
      {joho_html if joho_html else '<p style="color:var(--text2);font-size:0.85rem;">解説記事を生成中、または対象記事がありませんでした。</p>'}
    </div>

    <!-- 過去の履歴 -->
    <div class="card">
      <div class="section-header">
        <div class="icon">📅</div>
        <h2>過去の更新履歴</h2>
      </div>
      <div class="hist-tabs">
        {history_tabs_html}
      </div>
      <div id="history-container">
        {history_content_html}
      </div>
    </div>

    <!-- 更新スケジュール -->
    <div class="card">
      <div class="section-header">
        <div class="icon">🕐</div>
        <h2>自動更新スケジュール</h2>
      </div>
      <div class="schedule-info">
        <div class="schedule-item"><div class="schedule-dot"></div>朝 6:00 JST</div>
        <div class="schedule-item"><div class="schedule-dot"></div>昼 12:00 JST</div>
        <div class="schedule-item"><div class="schedule-dot"></div>夕方 16:00 JST</div>
        <div class="schedule-item"><div class="schedule-dot"></div>夜 20:00 JST</div>
      </div>
      <p style="font-size:0.8rem;color:var(--text2);margin-top:12px;">
        📰 メディア: TechCrunch, VentureBeat, The Verge, Wired, MIT Tech Review, ZDNet, IEEE Spectrum など<br>
        👤 キーマン: Google DeepMind, NVIDIA, Microsoft AI, Hugging Face, Sam Altman, Andrej Karpathy など
      </p>
    </div>
  </main>

  <footer>
    <p>AI News Daily — Powered by Claude AI | ソース: 米国主要テックメディアRSSフィード</p>
    <p style="margin-top:8px;">本ページのニュース要約はAIによる自動生成です。原文は各ソースをご確認ください。</p>
  </footer>

  <script>
    function showHistory(index) {{
      // 全タブ非アクティブ化
      document.querySelectorAll('.hist-tab').forEach(t => t.classList.remove('active'));
      document.querySelectorAll('.hist-content').forEach(c => c.style.display = 'none');

      // 選択タブをアクティブ化
      const tabs = document.querySelectorAll('.hist-tab');
      if (tabs[index]) tabs[index].classList.add('active');

      const content = document.getElementById('hist-' + index);
      if (content) content.style.display = 'block';
    }}
  </script>
</body>
</html>"""

    html_path = WEB_DIR / "index.html"
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html_content)

    print(f"[INFO] HTML生成: {html_path}")
    return html_path


def log(message: str):
    """ログ記録"""
    jst = datetime.timezone(datetime.timedelta(hours=9))
    now = datetime.datetime.now(jst)
    log_file = LOG_DIR / f"run_{now.strftime('%Y%m')}.log"
    entry = f"[{now.strftime('%Y-%m-%d %H:%M:%S')} JST] {message}\n"
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(entry)
    print(entry.strip())


def main():
    log("=== AI News Curation 開始 ===")

    # 1. ニュース収集
    log("RSSフィードからニュース収集中...")
    articles = fetch_articles(max_per_feed=5)
    log(f"収集記事数: {len(articles)}")

    if not articles:
        log("[WARNING] 記事が収集できませんでした")
        return

    # 2. Gemini APIで要約
    log("Gemini APIで要約生成中...")
    summary = summarize_with_gemini(articles)

    # 3. 週刊ジョーホー風解説を生成
    log("週刊ジョーホー風 解説記事を生成中...")
    joho_picks = generate_joho_commentary(articles)
    summary["joho_picks"] = joho_picks

    # 4. データ保存
    current_data = {
        "timestamp": datetime.datetime.now(
            datetime.timezone(datetime.timedelta(hours=9))
        ).isoformat(),
        "time_slot": get_time_slot(),
        "summary": summary,
        "raw_articles": articles[:15],
    }
    save_data(summary, articles)

    # 5. 履歴読み込み
    history = load_history()

    # 6. HTML生成
    log("HTMLページ生成中...")
    html_path = generate_html(current_data, history)

    # 7. FTPアップロード（さくらサーバーへ）
    log("FTPアップロード中...")
    upload_to_ftp(html_path)

    log(f"=== 完了: {html_path} ===")


if __name__ == "__main__":
    main()
