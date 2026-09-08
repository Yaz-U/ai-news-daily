"""Self-contained editorial pages. Rendering never calls the news or model APIs."""
import datetime as dt
import html
import json
import re
from pathlib import Path
from urllib.parse import urlsplit


def esc(value):
    return html.escape(str(value or ""), quote=True)


def safe_url(value):
    return esc(value) if urlsplit(str(value or "")).scheme in ("http", "https") else "#"


def paragraphs(value):
    text = str(value or "").strip()
    return "".join(f"<p>{esc(part).replace(chr(10), '<br>')}</p>" for part in re.split(r"\n\s*\n", text) if part.strip())


CSS = """
:root{--paper:#f7f6f2;--ink:#252b29;--muted:#6b716c;--line:#dcded6;--accent:#2b6654;--wash:#ecefe7}
*{box-sizing:border-box}html{scroll-behavior:smooth;scroll-padding-top:24px}body{margin:0;background:var(--paper);color:var(--ink);font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Noto Sans JP","Yu Gothic",Meiryo,sans-serif;-webkit-font-smoothing:antialiased}a{color:inherit;text-decoration-thickness:1px;text-underline-offset:5px}a:hover{color:var(--accent)}a:focus-visible,summary:focus-visible{outline:2px solid var(--accent);outline-offset:5px}.skip{position:absolute;left:16px;top:-70px;background:var(--paper);padding:12px}.skip:focus{top:12px}.shell{max-width:1160px;margin:auto;padding:0 48px}.masthead{padding-top:36px}.brand-row{display:flex;align-items:center;justify-content:space-between;gap:20px;padding-bottom:24px;border-bottom:2px solid var(--ink)}.brand{font-family:Georgia,"Times New Roman",serif;font-size:32px;font-weight:700;letter-spacing:-1px;text-decoration:none}.brand span{color:var(--accent)}.publisher{font-size:10px;letter-spacing:1.2px;color:var(--muted);text-decoration:none}.nav-row{display:flex;justify-content:space-between;gap:18px;padding:15px 0;border-bottom:1px solid var(--line);font-size:12px;color:var(--muted)}nav{display:flex;gap:26px}nav a{text-decoration:none}.intro{padding:60px 0 40px;max-width:920px}.eyebrow{font-size:11px;letter-spacing:2px;color:var(--accent);font-weight:700;margin:0 0 22px}.intro h1{font-family:"Yu Mincho","Hiragino Mincho ProN","Noto Serif JP",serif;font-size:clamp(28px,3.7vw,44px);line-height:1.6;letter-spacing:.02em;font-weight:600;margin:0 0 24px;overflow-wrap:anywhere}.standfirst{font-size:17px;line-height:1.95;max-width:800px;color:#505953}.meta{display:flex;gap:20px;flex-wrap:wrap;color:var(--muted);font-size:11px;margin-top:25px}.layout{display:grid;grid-template-columns:minmax(0,720px) minmax(160px,1fr);gap:64px;border-top:1px solid var(--line);padding-top:40px}.story{min-width:0}.chapter{margin:0 0 46px;scroll-margin-top:28px}.chapter h2{font-size:19px;line-height:1.65;font-weight:650;margin:0 0 22px;display:flex;gap:13px;align-items:baseline}.number{color:var(--accent);font-family:Georgia,serif;font-size:13px;flex-shrink:0}.prose{font-size:17px;line-height:2.15;letter-spacing:.025em;overflow-wrap:anywhere}.prose p{margin:0 0 1.5em}.rail{font-size:12px}.rail-inner{position:sticky;top:32px}.rail h2{font-size:10px;letter-spacing:2px;color:var(--muted);margin:0 0 20px}.toc{display:flex;flex-direction:column;gap:15px;line-height:1.8}.toc a{text-decoration:none}.rail-note{border-top:1px solid var(--line);margin-top:28px;padding-top:20px;color:var(--muted);line-height:1.9}.position{border-top:1px solid var(--line);padding:22px 0}.position h3{font-size:16px;margin:0 0 12px}.position p{font-size:15px;line-height:2;margin:8px 0}.implication{color:var(--accent)}.signals{background:var(--wash);padding:26px 30px;border-left:2px solid var(--accent)}.signals ol{padding-left:22px;margin:0}.signals li{padding:6px 0;font-size:15px;line-height:1.9}.sources{border-top:1px solid var(--line);padding-top:28px;margin:42px 0}.sources h2,.back-issues h2{font-size:18px;margin:0 0 24px}.source{display:grid;grid-template-columns:24px 1fr;gap:14px;padding:17px 0;border-bottom:1px solid var(--line)}.source-index{font-family:Georgia,serif;color:var(--muted);font-size:13px}.source a{font-size:14px;line-height:1.7;text-decoration:none;overflow-wrap:anywhere}.source small{display:block;font-size:10px;color:var(--muted);margin-top:7px;overflow-wrap:anywhere}.back-issues{margin:42px 0 60px;border-top:1px solid var(--ink);padding-top:26px}.issue{display:grid;grid-template-columns:110px 1fr;gap:22px;padding:20px 0;border-bottom:1px solid var(--line);text-decoration:none;font-size:15px;line-height:1.8}.issue time{font-size:12px;color:var(--muted);font-variant-numeric:tabular-nums}.all-issues{display:inline-block;margin-top:24px;font-size:13px}footer{border-top:1px solid var(--line);padding:28px 0 36px;color:var(--muted);font-size:11px;line-height:1.9}.footer-row{display:flex;justify-content:space-between;gap:24px}footer p{margin:0 0 8px}.empty{padding:30px 0;color:var(--muted)}.archive-intro{padding-bottom:32px}
@media(max-width:850px){.shell{padding:0 28px}.layout{grid-template-columns:minmax(0,1fr);gap:0}.rail{grid-row:1;margin-bottom:32px;padding-bottom:22px;border-bottom:1px solid var(--line)}.rail-inner{position:static}.toc{flex-direction:row;flex-wrap:wrap;gap:10px 20px}.rail-note{display:none}.rail h2{margin-bottom:12px}.intro{padding-top:40px}}
@media(max-width:540px){.shell{padding:0 22px}.masthead{padding-top:24px}.brand{font-size:27px}.publisher{font-size:8px;max-width:100px;text-align:right;line-height:1.8}.nav-row{font-size:10px;gap:12px}nav{gap:16px}.intro{padding:34px 0 28px}.intro h1{font-size:28px;line-height:1.6}.standfirst{font-size:15px;line-height:1.95}.prose{font-size:16px;line-height:2.05}.layout{padding-top:25px}.chapter{margin-bottom:34px}.chapter h2{font-size:18px}.signals{padding:20px}.issue{grid-template-columns:1fr;gap:5px}.footer-row{display:block}.meta{gap:10px;font-size:10px}}
@media(prefers-reduced-motion:reduce){html{scroll-behavior:auto}}
@media print{body{background:white}.rail,nav,.back-issues,.skip{display:none}.layout{display:block}.shell{max-width:none;padding:0}.intro{padding:20px 0}.chapter{break-inside:avoid}.prose{font-size:11pt}footer{font-size:9pt}}
"""


def page(title, content, prefix="", date_label=""):
    return f'''<!doctype html>
<html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light"><title>{esc(title)} | AI News Daily</title><style>{CSS}</style></head>
<body><a class="skip" href="#main">本文へ移動</a><div class="shell">
<header class="masthead"><div class="brand-row"><a class="brand" href="{prefix}index.html">AI News <span>Daily.</span></a><a class="publisher" href="https://incurator.co.jp/index.html">PUBLISHED BY<br>INCURATOR, INC.</a></div>
<div class="nav-row"><span>AIの動きを、ビジネスの視点で。</span><nav aria-label="メインナビゲーション"><a href="{prefix}index.html">最新号</a><a href="{prefix}archive.html">バックナンバー</a></nav></div></header>
<main id="main">{content}</main><footer><div class="footer-row"><div><p>世界のAIと、その先の変化を読む。毎朝6時更新（日本時間）。</p><p>AIによる編集・解説です。事実の詳細は各出典をご確認ください。</p></div><p>© INCURATOR, Inc.</p></div></footer></div></body></html>'''


def clean_heading(value):
    return re.sub(r"^\s*【[^】]+】\s*", "", str(value or ""))


def issue_date(timestamp):
    try:
        parsed = dt.datetime.fromisoformat(timestamp).astimezone(dt.timezone(dt.timedelta(hours=9)))
        return parsed.strftime("%Y.%m.%d"), parsed.strftime("%H:%M JST")
    except (ValueError, TypeError):
        return "日付未記録", ""


def render_issue(data, prefix=""):
    summary = data.get("summary", {})
    picks = summary.get("joho_picks", [])
    title = summary.get("headline") or (picks[0].get("headline") if picks else "今日のAIニュース")
    date, time = issue_date(data.get("timestamp"))
    sections = []

    def add(label, body):
        if body:
            sections.append((label, body))

    if summary.get("opening"):
        add("今日の論点", paragraphs(clean_heading(summary["opening"])))
        add("何が起きたのか", paragraphs(clean_heading(summary.get("what_happened"))))
        add("変化をどう読むか", paragraphs(clean_heading(summary.get("why_now"))))
        positions = ""
        for item in summary.get("company_positions", []):
            positions += f'<div class="position"><h3>{esc(item.get("company"))}</h3>{paragraphs(item.get("status"))}<div class="implication">{paragraphs(item.get("implication"))}</div></div>'
        add("各社の立ち位置", positions)
        add("日本の実務への示唆", paragraphs(clean_heading(summary.get("japan_impact"))))
        add("見立ての限界", paragraphs(clean_heading(summary.get("counterpoint"))))
    elif picks:
        for pick in picks:
            add(pick.get("headline", "解説"), paragraphs(pick.get("body")) + paragraphs(pick.get("why_matters")) + paragraphs(pick.get("context")))
    else:
        add("ニュース概況", paragraphs(summary.get("news_summary")))
        add("解説", paragraphs(summary.get("opinion_summary")))
    signals = summary.get("next_signals", [])
    if signals:
        add("次に確かめたいこと", '<div class="signals"><ol>' + ''.join(f'<li>{esc(s)}</li>' for s in signals) + '</ol></div>')
    toc = ''.join(f'<a href="#chapter-{i}">{i:02d}　{esc(label)}</a>' for i, (label, _) in enumerate(sections, 1))
    article = ''.join(f'<section class="chapter" id="chapter-{i}"><h2><span class="number">{i:02d}</span>{esc(label)}</h2><div class="prose">{body}</div></section>' for i, (label, body) in enumerate(sections, 1))
    sources = summary.get("sources") or summary.get("top_articles", [])
    if not sources:
        sources = [{"title": p.get("source_title"), "url": p.get("source_url")} for p in picks]
    source_html, seen = "", set()
    for source in sources:
        url = source.get("url", "")
        if not url or url in seen or safe_url(url) == "#":
            continue
        seen.add(url)
        domain = urlsplit(url).netloc
        source_html += f'<div class="source"><span class="source-index">{len(seen):02d}</span><div><a href="{safe_url(url)}" target="_blank" rel="noopener noreferrer">{esc(source.get("title") or domain)} ↗</a><small>{esc(domain)}</small></div></div>'
    source_html = f'<section class="sources" id="sources"><h2>この記事の出典</h2>{source_html}</section>' if source_html else ""
    chars = sum(len(re.sub('<[^>]*>', '', body)) for _, body in sections)
    content = f'''<div class="intro"><p class="eyebrow">THE DAILY BRIEF · {date}</p><h1>{esc(title)}</h1><div class="standfirst">{paragraphs(summary.get("thesis"))}</div><div class="meta"><span>AI News Daily 編集部</span><span>{time} 更新</span><span>読了目安 {max(1, round(chars / 550))}分</span></div></div>
<div class="layout"><article class="story" aria-label="編集記事">{article}{source_html}</article><aside class="rail"><div class="rail-inner"><h2>IN THIS ISSUE</h2><nav class="toc" aria-label="記事の目次">{toc}</nav><p class="rail-note">発表の先にある、企業・市場・私たちの仕事への変化を考えます。</p></div></aside></div>
<section class="back-issues"><h2>これまでのAIの動きを読む</h2><a class="all-issues" href="{prefix}archive.html">バックナンバーを見る →</a></section>'''
    return page(title, content, prefix)


def render_archive(web_dir):
    rows = []
    for path in sorted((web_dir / "archive").glob("*.html"), reverse=True):
        if not re.fullmatch(r"\d{8}_\d{4}", path.stem):
            continue
        text = path.read_text(encoding="utf-8")
        match = re.search(r'class="joho-headline">(.*?)</div>', text, re.S)
        if not match:
            match = re.search(r'<h1[^>]*>(.*?)</h1>', text, re.S)
        title = html.unescape(re.sub('<[^>]+>', '', match.group(1))) if match else "AIニュース解説"
        date = dt.datetime.strptime(path.stem, "%Y%m%d_%H%M")
        rows.append(f'<a class="issue" href="archive/{path.name}"><time datetime="{date.isoformat()}">{date:%Y.%m.%d}<br>{date:%H:%M} JST</time><span>{esc(title)} →</span></a>')
    return page("バックナンバー", '<div class="intro archive-intro"><p class="eyebrow">THE ARCHIVE</p><h1>日々の変化を、つなげて読む。</h1><p class="standfirst">AIをめぐる競争と、ビジネスへの示唆を振り返る。</p></div>' + (''.join(rows) or '<p class="empty">次回の更新から記事が並びます。</p>'))


def rebuild(web_dir, data_dir):
    """Re-render saved content without changing publication dates or making API calls."""
    current = json.loads((data_dir / "latest.json").read_text(encoding="utf-8"))
    (web_dir / "index.html").write_text(render_issue(current), encoding="utf-8")
    (web_dir / "archive.html").write_text(render_archive(web_dir), encoding="utf-8")


if __name__ == "__main__":
    root = Path(__file__).resolve().parent
    rebuild(root / "docs", root / "data")
