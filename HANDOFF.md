# Claude Codeへの引き継ぎ

更新: 2026-09-08（日本時間）。これは作業引き継ぎであり、ニュース記事ではない。

## ユーザーの目的と合意事項

- AIニュースをわかりやすく、読み応えと示唆のある日本語記事にする。費用最小化より内容の質を優先。定型的な要約、一般論、単調なストレートニュースが不満だった。
- OpenAI、Google/DeepMind、Anthropicを軸に、中国AI（DeepSeek、Qwen、Kimi、GLM等）、OpenRouter、OpenClawも扱う。競合の変化が3社の立場にどう影響するかを読み解く。
- NewsPicks後藤直義氏の参照ソース群を調査時に収集し、その独立ソースを以後の日次取材の材料にする。毎日の後藤氏の記事を見て当日のネタを追随する運用ではない。
- 同じテーマを避ける必要はない。独立ソースと自分たちの選定基準から選んだ結果、同じテーマになってよい。「同じネタを禁止」と解釈しない。
- ユーザーは後藤氏の記事の読み味・熱量・ニュアンスを参考にすることを望んでいる。これまで「模倣しない」という説明でその希望まで否定したため不満が生じた。強い問い、平易な説明、企業間の利害、具体的根拠、反証を取り入れる。本文のコピーや本人を装った執筆は不要。
- 1日1回、毎朝6時JST。記事履歴を保存する。

## 本番の場所と主要ファイル

- 作業ルート: `C:/Users/user/Desktop/Claude/News`。入れ子の `News/` は別コピーで、本番更新対象にしない。
- GitHub: https://github.com/Yaz-U/ai-news-daily （main）
- 公開サイト: https://news.incurator.co.jp/ （GitHub Pages、docsディレクトリ）
- 手動実行: https://github.com/Yaz-U/ai-news-daily/actions/workflows/news.yml
- APIキー設定: https://github.com/Yaz-U/ai-news-daily/settings/secrets/actions の Repository secret `GEMINI_API_KEY`。値は表示・コミットしない。
- `fetch_news.py`: RSS収集、選定、Gemini生成、保存、公開HTML生成の呼び出し。
- `editorial_ui.py`: 新しいHTMLレンダラー。標準ライブラリのみ。最新号、バックナンバー一覧、新規アーカイブ記事の画面を生成する。
- `EDITORIAL_SOURCES.md`: 収集ソースと編集方針の台帳。ただし未検証・未実装の項目もある（後述）。
- `data/latest.json`: 最新データ。`data/news_YYYYMMDD_HHMM.json`: 実行ごとの保存データ。
- `docs/index.html`: 最新号。`docs/archive.html`: 過去記事一覧。`docs/archive/*.html`: 前回の記事を更新時に保存。
- `scheduler_loop.py`、`setup_scheduler.py`: ローカル用スケジューラも6時の1回へ変更済み。

## 今回完成したUI変更

- `7909f2f`: UI全面刷新。濃色背景、紫グラデーション、絵文字、重複要約カードを撤去。生成り背景、墨色本文、深緑アクセント、明朝見出し。
- 1本の記事として、論点→事実→解釈→各社の立ち位置→日本への示唆→留保→観測点→出典を表示。同じ内容を要約カードで再掲しない。
- PCは右側に追従する目次、スマホは本文上に折り返す目次。本文は最初から全量HTMLに含まれ、追加読み込みはない。
- HTMLエスケープ、外部リンクのhttp/https確認、目次アンカー、本文スキップリンク、印刷用スタイルあり。
- `3919974`: 日付が目立たないとの指摘を受け、見出し直前に大きな「2026年9月8日（火）」、下に「19:27 更新（日本時間）」を表示。これは保存timestamp由来の掲載日で、原典の発生日ではない。
- 既存の古いアーカイブ本文は一括再生成していない。アーカイブ一覧と最新号は新UI、新たに保存されるアーカイブも新UI。
- PlaywrightのEdgeヘッドレスで1440pxと390px幅を確認。390pxで横はみ出しなし。目次のリンク先、旧形式の記事データ、HTMLエスケープを確認済み。
- ここまでのUI変更はmainへpush済み。日付表示の最後のコミットは `3919974`。

## iPhone読み上げ: 未実装・未検証

ユーザーの想定機能は、iPhoneの「画面の読み上げ」（画面上から2本指で下へスワイプ）。Safari独自の読み上げではない。

- 質問は「最初から最後まで途中で止まらず読めるか」。iPhone実機テストはしておらず、保証していない。
- 本文は全量静的HTML。ただし画面読み上げではナビや目次も読まれる可能性がある。ロック時や割り込みの継続はiOS側の動作にもよる。
- 日付→見出し→要旨→本文を並べる「読み上げ用ページ」を提案した段階。まだ実装していない。音声プレイヤー、音声ファイル、読み上げ専用リンクもない。
- 最新のユーザー依頼は引き継ぎ資料の作成。読み上げ対応を完了扱いにしない。

## 記事生成と残る品質課題

- ユーザー指定モデルは `gemini-3.5-flash-lite`。現行コードを確認して変更せず継続する。過去に2.xで404が出た。モデルの提供状況についてログ以上の断定はしない。
- 現行の主処理は `summarize_editorial_with_gemini`。一回の生成で構造化JSONを作る。旧 `summarize_with_gemini` と `generate_joho_commentary` は残っているが主処理では使っていない。
- 編集入力はRSS概要の最大500文字、優先順位上位16件。記事本文の深掘り取得、公式情報との自動照合、利用データの自動取得は未実装。長文プロンプトだけで裏取りが増えるわけではない。
- 公式情報と価格・資本・導入・規制・インフラのキーワードを加点。細かなGitHub開発リリースが高順位になりやすい。テーマの多様性やネタの面白さを十分保証する選定ではない。
- RSSの日付不明を除外していない。24時間フィルタは記事の発生日と同義ではない。
- OpenRouterのRSSはURLを登録しただけで、取得・内容の検証が残る。Qwen Code、DeepSeek-V3、GLM-4のリリースだけでは中国勢全体や最新モデル発表を網羅できない。Anthropicニュースの専用取得、Kimi等の直接取得も不足。
- NYT Technology、WSJ、Axios、OpenAI、Google、中国勢GitHubの一部URLはHTTP HEADで200を確認したが、全件のGET/パース/鮮度・網羅性まで検証したわけではない。
- Bloomberg/FT/Reutersは手動確認候補。OpenRouter/Vercel利用統計、政府発表、導入事例も台帳の候補であり、独立した日次コレクターは未実装。
- 過去のAI生成本文は一次資料の代わりにしない。APIエラー時にはダミー要約に落ちて成功扱いになるコードも残っている。

## 公開と競合への注意

`.github/workflows/news.yml` の `AI News Auto Update` は6時JSTとworkflow_dispatch。ニュース生成後にデータとHTMLをコミットし、`git pull --rebase -X theirs origin main`、`git push` を実行する。

- 実行中の設定pushや別ニュース更新と競合し、過去に保存失敗が繰り返された。上記はrebase中の生成コミット側を競合箇所で優先する応急対応。
- `-X theirs` はHTML全体を必ず一括置換する保証ではなく、非競合箇所はマージされる。古いコードで開始した実行の公開、同時実行、push直前の競合などは完全には防げていない。concurrency設定も未導入。必要なら安全な保存設計を改めて検討する。
- 修正後のテストはworkflow一覧から `Run workflow`、branch `main` で新規実行。古い実行の `Re-run jobs` は古いコミットの定義を再利用する。
- GitHub Actionsがデータを更新するため、push前にfetchして差分を確認する。強制pushやユーザーの変更破棄をしない。
- FTP関連コードは残るが、現ワークフローはFTP環境変数を渡しておらず、FTPをスキップする。

## デザインだけ変更するとき

ルートで `python editorial_ui.py` を実行すると、保存済みの `data/latest.json` から最新号と一覧だけを再生成できる。Gemini呼び出しも記事timestamp更新もない。`fetch_news.py` を実行すると収集・生成まで行われるため、UI確認には使わない。

この環境のPython:
`C:/Users/user/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe`

公開対象の変更ファイルだけをstageする。多数の既存untrackedファイル、入れ子のNews、セッションバックアップ、FTP/SSH関連ファイルがあるので `git add .` は使わない。

引き継ぎ前に変更した既存 `CLAUDE.md` のバックアップ指示は保持した。この資料は作業内容の引き継ぎであり、全セッションログのバックアップ完了を意味しない。
