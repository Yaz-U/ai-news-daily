#!/usr/bin/env python3
"""
AI News Curation Script
アメリカのAI関連ニュースを収集し、日本語で要約してWebページを生成する
実行タイミング: 毎朝6:00 (JST)
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
WEB_DIR = BASE_DIR / "docs"
LOG_DIR = BASE_DIR / "logs"
ARCHIVE_DIR = WEB_DIR / "archive"

# 必要なディレクトリを自動作成
DATA_DIR.mkdir(exist_ok=True)
WEB_DIR.mkdir(exist_ok=True)
LOG_DIR.mkdir(exist_ok=True)
ARCHIVE_DIR.mkdir(exist_ok=True)

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
    ("NYTimes Technology", "https://rss.nytimes.com/services/xml/rss/nyt/Technology.xml"),
    ("Wall Street Journal", "https://feeds.a.dj.com/rss/RSSWSJD.xml"),
    ("Axios",              "https://www.axios.com/feeds/feed.rss"),
]

# 【カテゴリ2】AI業界キーマン・企業公式ブログ（動作確認済み）
RSS_FEEDS_KEYMAN = [
    # 企業公式ブログ
    ("OpenAI News",        "https://openai.com/news/rss.xml"),
    ("Google DeepMind",   "https://deepmind.google/blog/rss.xml"),
    ("Google AI Blog",    "https://blog.google/technology/ai/rss/"),
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
    # 中国AI・モデル流通・AIエージェント
    ("Qwen GitHub",        "https://github.com/QwenLM/qwen-code/releases.atom"),
    ("DeepSeek GitHub",    "https://github.com/deepseek-ai/DeepSeek-V3/releases.atom"),
    ("Z.ai GLM GitHub",    "https://github.com/zai-org/GLM-4/releases.atom"),
    ("OpenClaw GitHub",    "https://github.com/openclaw/openclaw/releases.atom"),
    ("OpenRouter Blog",    "https://openrouter.ai/announcements/rss.xml"),
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
    "DeepSeek", "Qwen", "Kimi", "Moonshot", "GLM", "Zhipu", "MiniMax",
    "ERNIE", "Hunyuan", "Doubao", "OpenRouter", "OpenClaw", "MCP",
]

# 後藤直義氏の直近AI企画を調査して得た編集上の優先順位。
# 一次情報を起点に、価格・資本・導入・規制・インフラの変化を扱う記事を優先する。
EDITORIAL_SOURCE_PRIORITY = {
    "OpenAI News": 100, "Google DeepMind": 100, "Google AI Blog": 100,
    "Qwen GitHub": 95, "DeepSeek GitHub": 95, "Z.ai GLM GitHub": 95,
    "OpenRouter Blog": 95, "OpenClaw GitHub": 90,
    "NVIDIA Blog": 85, "Microsoft AI": 85, "Hugging Face": 85,
    "NYTimes Technology": 80, "Wall Street Journal": 80, "Axios": 75,
    "MIT Tech Review": 75, "CNBC Tech": 75, "TechCrunch AI": 70,
    "Last Week in AI": 70, "Import AI": 70, "AI Business": 65,
}
EDITORIAL_SIGNALS = [
    "price", "pricing", "cost", "cheap", "revenue", "profit", "funding", "valuation",
    "agent", "enterprise", "adoption", "deployment", "open weight", "open-source",
    "chip", "gpu", "data center", "compute", "export", "regulation", "security",
    "価格", "コスト", "資金", "投資", "導入", "規制", "半導体", "電力",
]


def is_ai_related(title: str, summary: str = "") -> bool:
    """記事がAI関連かどうかを判定"""
    text = (title + " " + summary).lower()
    for keyword in AI_KEYWORDS:
        # "AI" を単純な部分文字列で判定すると availability 等まで拾ってしまう。
        if keyword.lower() == "ai":
            if re.search(r"(?<![a-z])ai(?![a-z])", text):
                return True
        elif keyword.lower() in text:
            return True
    return False


def editorial_rank(article: dict) -> int:
    """一次情報と産業構造に関わる材料を、編集記事の候補として優先する。"""
    text = f"{article.get('title', '')} {article.get('summary', '')}".lower()
    source_score = EDITORIAL_SOURCE_PRIORITY.get(article.get("source", ""), 40)
    signal_score = sum(8 for signal in EDITORIAL_SIGNALS if signal in text)
    return source_score + min(signal_score, 32)


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


def summarize_editorial_with_gemini(articles: list[dict]) -> dict:
    """中心テーマ型の1日1回編集記事を生成する。"""
    if not GEMINI_API_KEY or not articles:
        return _dummy_summary(articles)
    client = genai.Client(api_key=GEMINI_API_KEY)
    editorial_articles = sorted(articles, key=editorial_rank, reverse=True)[:16]
    article_text = "\n".join(
        f"[{i}] {a['source']}｜{a['title']}\nURL: {a['url']}\n概要: {a['summary'][:500]}"
        for i, a in enumerate(editorial_articles, 1)
    )
    prompt = f"""あなたは、海外AI産業を継続取材する日本語の経済メディア編集者です。
読者はAIの専門家ではないが、事業・投資・プロダクトの判断をするビジネスパーソンです。単なる要約ではなく、今日の材料から「競争のルールがどこで変わり始めたか」を一つの論点として読み解いてください。

【編集原則】
- 最初に、読者が持ち帰るべき結論を明言する。発表内容の言い換えから始めない。
- 公式発表・公式リリースなどの一次情報を最優先し、二次報道は市場の受け止めや資本・規制の文脈を補う場合に限って使う。
- 他媒体と同じテーマであっても避けない。入力された独立ソースから、価格・資本・導入・規制・インフラの変化を説明できるかだけで選ぶ。
- 入力記事のうち、因果または競争上のつながりを根拠をもって説明できる2〜4本を選び、ひとつの緊張感のある問いに束ねる。無理に全記事を扱わない。
- 注目すべきは機能の新しさではなく、誰が価値・コスト・流通・計算資源の主導権を得るか。OpenAI、Google/DeepMind、Anthropic、中国AI（DeepSeek、Qwen、Kimi、GLM等）、OpenRouter、OpenClaw、MCPは、入力と関係する主体だけを比較する。関係しない会社を「動きなし」として埋めない。
- 「事実」と「編集部の解釈」を混ぜない。事実は入力記事にある内容だけを使い、解釈は「〜と読める」「ただし〜なら崩れる」のように条件付きで書く。数字、発言、顧客、企業の本音を創作しない。
- ありきたりな「競争激化」「期待が高まる」「可能性がある」で結ばない。反証材料と、見立てが正しいかを判定する次の具体的シグナルを書く。
- 専門用語を初出時に一言でほどき、短い段落でテンポよく書く。煽らず、だが論点は鋭くする。

JSONのみで出力:
{{
 "headline":"結論が伝わる見出し（35字以内）",
 "thesis":"読者が最初に持ち帰るべき見立て（120字以内）",
 "opening":"【結論】から始める導入。何が変わったと見るのか、なぜ今日の材料を一つの論点として読むのか（350〜500字）",
 "what_happened":"【事実】見立ての根拠となる記事を2〜4本だけ使い、各事実がどこにつながるかを示す。記事名や主体を自然に明記する（800〜1100字）",
 "why_now":"【解釈】今回の変化が競争構造、収益化、導入、インフラのいずれを動かすのかを因果で解く。過去からの一般論の繰り返しは避ける（800〜1100字）",
 "company_positions":[{{"company":"入力と関係する企業・陣営名","status":"今回の打ち手・現在地（120〜180字）","implication":"この主体の優位・弱点がどう変わるか（160〜240字）"}}],
 "counterpoint":"【反証・留保】見立てを過大評価しないための条件。何が起きれば結論が崩れるか（350〜500字）",
 "japan_impact":"【日本の実務への示唆】日本企業が今週、導入・調達・提携・人材のどれを見直すべきか。実行に近い判断として書く（400〜600字）",
 "next_signals":["結論を検証する具体的な観測点1","観測点2","観測点3"],
 "sources":[{{"title":"実際に用いた入力記事タイトル","url":"そのURL"}}]
}}

【入力記事】\n{article_text}"""
    # 編集記事は、コストと品質のバランスを優先して軽量モデルを固定で使う。
    models_to_try = ["gemini-3.5-flash-lite"]
    for model_name in models_to_try:
        try:
            response = client.models.generate_content(
                model=model_name, contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.7, response_mime_type="application/json", max_output_tokens=8192
                ),
            )
            text = re.sub(r"```json\s*|```", "", response.text or "").strip()
            editorial = json.loads(text)
            sources = editorial.get("sources", [])
            top_articles = []
            for rank, src in enumerate(sources[:5], 1):
                match = next((a for a in articles if a.get("url") == src.get("url")), {})
                top_articles.append({"rank": rank, "title": src.get("title", match.get("title", "")),
                                     "source": match.get("source", ""), "url": src.get("url", ""),
                                     "point": match.get("summary", "")[:120]})
            positions = editorial.get("company_positions", [])
            position_text = "\n\n".join(
                f"【{p.get('company', '主要プレイヤー')}】\n{p.get('status', '')}\n→ {p.get('implication', '')}"
                for p in positions if isinstance(p, dict)
            )
            editorial["news_summary"] = f"{editorial.get('thesis', '')}\n\n{editorial.get('what_happened', '')}"
            editorial["opinion_summary"] = editorial.get("why_now", "")
            editorial["sentiment"] = {"positive": "", "negative": editorial.get("counterpoint", ""), "neutral": "事実と分析を分けて掲載しています。"}
            editorial["top_articles"] = top_articles
            editorial["joho_picks"] = [{"headline": editorial.get("headline", ""), "source_title": "中心テーマ型編集記事",
                                         "source_url": (sources[0].get("url", "#") if sources else "#"),
                                         "source_name": "AI News Daily編集部",
                                         "body": editorial.get("opening", "") + "\n\n" + editorial.get("what_happened", "") + "\n\n" + editorial.get("why_now", "") + ("\n\n【競争の構図】\n" + position_text if position_text else ""),
                                         "why_matters": editorial.get("japan_impact", "") + "\n\n" + editorial.get("counterpoint", ""),
                                         "context": "【次の観測点】\n" + "\n".join(f"・{signal}" for signal in editorial.get("next_signals", []))}]
            return editorial
        except Exception as e:
            print(f"[WARNING] 編集記事生成失敗 ({model_name}): {e}")
    return _dummy_summary(articles)


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
        "gemini-3.5-flash-lite",
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
            else:
                print(f"[ERROR] Gemini API エラー ({model_name}): {e}。次のモデルを試します...")
            continue

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


def generate_joho_commentary(articles: list[dict], history: list[dict] = None) -> list[dict]:
    """
    News風のAIニュース深掘り解説を生成する。
    - NYからの俯瞰的・グローバル視点
    - ビジネス・経済インパクト重視
    - 技術ハイプに流されない逆張り・批判的目線
    - 【】囲みの衝撃的見出し
    - 複数ソース・過去記事を絡めた点と線の分析
    - 読者に「なぜそれが重要か」を問い直す構成
    """
    if not GEMINI_API_KEY or not articles:
        return []

    client = genai.Client(api_key=GEMINI_API_KEY)

    articles_text = ""
    for i, art in enumerate(articles[:20], 1):
        articles_text += f"""
【記事{i}】
タイトル: {art['title']}
ソース: {art['source']}
URL: {art['url']}
概要: {art['summary'][:400]}
---
"""

    # 過去記事のヘッドラインリストを構築
    history_text = ""
    if history:
        history_text = "\n【過去数日間の主要記事（参考情報）】\n"
        for h in history[:8]:
            ts = h.get("timestamp", "")[:10]
            picks = h.get("summary", {}).get("joho_picks", [])
            if picks:
                for p in picks[:5]:
                    headline = p.get("headline", "")
                    body_preview = p.get("body", "")[:100]
                    history_text += f"- [{ts}] {headline} — {body_preview}...\n"
            else:
                raw = h.get("raw_articles", [])
                for r in raw[:3]:
                    history_text += f"- [{ts}] {r.get('title', '')}\n"
        history_text += "---\n"

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
- 見出しは【】で囲む（例：【現実】【衝撃】【ミニ教養】【絶句】【完全解説】【NY発】【独自分析】【裏事情】【点と線】）
- 見出しは15字以内で読者の興味を引くキャッチーなもの

- 本文は600〜900字の日本語で、以下の要素を含めて深掘りすること：
  ・このニュースの裏側にある背景や文脈（「実はこういう事情がある」）
  ・複数の記事・情報源を横断した分析（「別のソースではこう報じている」「○○の発言と合わせると」）
  ・業界関係者・専門家・アナリストがどう見ているかの紹介（「シリコンバレーのVC界隈では」「ウォール街のアナリストは」）
  ・表面的な報道では見えない力学（企業の思惑、規制の動き、技術トレンドの裏側）
  ・読者が「へぇ、そういうことだったのか」と膝を打つような解説

- 「■ なぜ重要か」は200〜400字で以下を含める：
  ・日本のビジネスパーソン・企業にとっての具体的な影響
  ・今後の展開予測（「これにより○○が加速する」「次に起きるのは○○だ」）
  ・なぜ今このタイミングで注目すべきか

- 過去記事との関連がある場合は「■ 関連する動き」として記載（例：「○日前の△△の続報」「□□と合わせて読むと流れが見える」）。関連がなければ空文字にする

以下のニュース記事の中から、あなたの目線で特に重要・興味深いと思う記事を8〜10本選び、
それぞれについて上記スタイルで深掘り解説記事を書いてください。
{history_text}
【本日の記事】
{articles_text}

必ずJSONのみで回答してください（説明文・マークダウン不要）：
[
  {{
    "headline": "【〇〇】見出しテキスト",
    "source_title": "参照した記事の元タイトル",
    "source_url": "参照した記事のURL",
    "source_name": "メディア名",
    "body": "本文（600〜900字の深掘り解説）",
    "why_matters": "■ なぜ重要か（200〜400字）",
    "context": "■ 関連する動き：（過去記事や他ソースとの関連があれば記載。なければ空文字）"
  }},
  ...
]
"""

    models_to_try = [
        "gemini-3.5-flash-lite",
    ]

    for model_name in models_to_try:
        try:
            print(f"[INFO] News風解説 モデル試行: {model_name}")
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
                print(f"[INFO] News風解説 生成成功: {len(picks)}本 ({model_name})")
                return picks
            else:
                raise ValueError("JSONリストが見つかりません")

        except Exception as e:
            err_str = str(e)
            if "429" in err_str or "quota" in err_str.lower():
                print(f"[WARNING] {model_name} レート制限。次のモデルを試します...")
            else:
                print(f"[ERROR] News風解説 エラー ({model_name}): {e}。次のモデルを試します...")
            continue

    print("[WARNING] News風解説の生成に失敗しました")
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

    for f in data_files[:7]:  # 最大7件（1日1回×1週間）
        try:
            with open(f, "r", encoding="utf-8") as fp:
                data = json.load(fp)
                history.append(data)
        except Exception:
            continue

    return history


def archive_current_page() -> None:
    """Archive the previous issue with the same typography as the current page."""
    from editorial_ui import render_issue
    latest_path = DATA_DIR / "latest.json"
    if not latest_path.exists():
        return
    previous = json.loads(latest_path.read_text(encoding="utf-8"))
    if not previous.get("summary", {}).get("joho_picks"):
        return
    timestamp = datetime.datetime.fromisoformat(previous["timestamp"])
    destination = ARCHIVE_DIR / (timestamp.strftime("%Y%m%d_%H%M") + ".html")
    destination.write_text(render_issue(previous, prefix="../"), encoding="utf-8")
    generate_archive_index()


def generate_archive_index() -> None:
    from editorial_ui import render_archive
    (WEB_DIR / "archive.html").write_text(render_archive(WEB_DIR), encoding="utf-8")


def generate_html(current_data: dict, history: list[dict]) -> Path:
    """Render saved editorial fields once, without duplicate summary cards."""
    from editorial_ui import render_issue
    html_path = WEB_DIR / "index.html"
    html_path.write_text(render_issue(current_data), encoding="utf-8")
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

    # 2. 1回のAPI呼び出しで中心テーマ型の編集記事を生成
    log("中心テーマ型の編集記事を生成中...")
    summary = summarize_editorial_with_gemini(articles)

    # 3. 履歴読み込み（過去記事との関連分析に使用）
    history = load_history()

    # 4. 解説は中心テーマ型記事に統合済み

    # 5. 前回のNews風記事をアーカイブ（latest.json上書き前に保存）
    log("前回のNews風記事をアーカイブ中...")
    archive_current_page()

    # 6. データ保存
    current_data = {
        "timestamp": datetime.datetime.now(
            datetime.timezone(datetime.timedelta(hours=9))
        ).isoformat(),
        "time_slot": get_time_slot(),
        "summary": summary,
        "raw_articles": articles[:15],
    }
    save_data(summary, articles)

    # 7. HTML生成
    log("HTMLページ生成中...")
    html_path = generate_html(current_data, history)

    # 8. FTPアップロード（さくらサーバーへ）
    log("FTPアップロード中...")
    upload_to_ftp(html_path)

    log(f"=== 完了: {html_path} ===")


if __name__ == "__main__":
    main()
