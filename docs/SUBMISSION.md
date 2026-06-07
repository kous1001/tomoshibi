# 提出ガイド — 灯 Tomoshibi（Track 1：LFM Application）

Notion「Hack the Liquid WAY: Event Guide」📦 Submission Guide に対応した提出物の
マスターチェックリスト。実成果物のドラフトは [`docs/submission/`](submission/) に格納。

## ⏰ スケジュール（Day 2 = 2026-06-07・JST）

| 時刻 | 内容 |
|---|---|
| 09:30–13:30 | Hack + Lunch |
| **13:30–14:00** | **🚨 Submission Deadline（提出締切）** |
| 14:00–16:00 | Demo Session — **各チーム ライブ5分** |
| 16:00–16:30 | 審査員評価＋オーディエンス投票 |
| 16:30–17:00 | 表彰＋クロージング |

> 旧版の「12:30締切 / 13:00デモ / 3〜5分」は誤り。**正：13:30締切・14:00デモ・ライブ5分**。

## 📦 提出物（Track 1 確定要件）

### Common（共通）
1. **スライド 2〜4枚** — 日本の課題/ユースケース・「なぜLFMか」・アプローチ・結果。**英語デッキ**（日本語登壇のため）。
2. **ライブデモ 5分**（Day2）。
3. **タグライン（1〜2行）＋公開リポジトリURL**。
4. **暗号化デモ資産フォルダ** `TEAMNAME_Track1_HackTheLiquidWAY_DemoAssets`
   — **パスワードは Discord @liquid-yan に共有**。内容：60〜90秒デモ動画／高解像度スクショ／
   プロダクト＆チーム写真／captions・bios／README.txt（ファイル説明＋セットアップ手順）。
5. **テクニカルサマリー**（デッキ or README.txt 内）：モデル＋フレームワーク・計算構成・
   デバイス＋遅延/効率の数値・アーキ図 or 技術的革新。

### Track 1 固有
- AMD Ryzen AI PC でのライブ動作（or 明確な実行手順）。**オンデバイス性能は加点で必須ではない**。
- オンデバイス詳細：どのLFM／ランタイム（FastFlowLM / llama.cpp+Vulkan / LEAP / liquid-audio）／実測 latency＋memory/power。
- **W&B Weave（強く推奨）**：LFM呼び出しトレース・eval・アプリ品質/遅延測定（学習不要）。

## 🧮 審査軸への当てはめ

| 審査軸 | 灯の訴求 |
|---|---|
| **Fit to Challenge**（なぜLFM／日本の実課題） | 超高齢社会・孤独死という日本固有の課題。**オンデバイス＝プライバシー**でなければカメラを家に置けない＝クラウドLLMでは不可能、を中核に。 |
| **Creativity & Design** | 「話し相手」＋「見守り」を1つの灯に統合。2段階転倒検知（安価Pose→稀にVLM）＋段階的エスカレーション。 |
| **Quality & Completeness** | 51テスト、mock E2E、実LFM2/LFM2-VL/whisper/VOICEVOX 統合、Weave観測性。1人目の顧客に届くピッチ。 |
| **Resource Efficiency** | VLMは候補時1フレームのみ＝低負荷・低消費電力。エッジ/低コスト機で動作。 |
| **Track1固有**（実用性・非技術ユーザーUX・ワークフロー設計・LFMが中核を担うか） | ハンズフリー音声、機内モード実証、確実な家族/救急への引き継ぎ。 |

## 🎤 デモ台本（ライブ5分）

1. **(40s) 課題＋話し相手**：一人暮らし・誰にも気づかれない転倒。「最近寂しくてね」→灯が優しく音声応答。
2. **(120s) 見守り**：カメラ前で転倒（or 🎬デモ動画）→ LFM2-VL確認 → S1声かけ →
   無応答 → S2家族通知 → S3 **119原稿を読み上げ**（氏名・持病・アレルギー）。🙆/🆘/👨‍👩‍👧で分岐。
3. **(40s) プライバシー実証**：機内モードでも全部動く。外部は家族通知のみ。
4. **(20s) オンデバイス＆締め**：Ryzen AIで動作。「灯は、孤独を照らし、もしもの時に命をつなぐ。」

> ⚠️ ライブが重い場合に備え、**本番機で60〜90秒のバックアップ録画**を用意（=提出するデモ動画を兼用）。

## ✅ 作成済みドラフト（このリポジトリ内）

- [x] スライド（英語4枚・HTML） → [`docs/submission/slides/index.html`](submission/slides/index.html)（Cmd+P→PDF）
- [x] デモ資産フォルダ用 README.txt → [`docs/submission/DEMO_ASSETS_README.txt`](submission/DEMO_ASSETS_README.txt)
- [x] テクニカルサマリー → [`docs/submission/TECHNICAL_SUMMARY.md`](submission/TECHNICAL_SUMMARY.md)
- [x] タグライン（英/日） → [`docs/submission/TAGLINE.txt`](submission/TAGLINE.txt)
- [x] captions/bios テンプレ → [`docs/submission/TEAM_BIOS.md`](submission/TEAM_BIOS.md)
- [x] 公開リポジトリのローカル整備（git init・LICENSE・.gitignore秘密除外）

## 📝 手動TODO（あなたが対応）

- [ ] 正式 **TEAM NAME** を決定 → 各ファイル/フォルダ名・スライドの `<TEAMNAME>` を置換。
- [ ] **60〜90秒デモ動画**を録画（会話UI＋転倒→S1→S2→S3＋119読み上げ＋機内モード実証）。
- [ ] **高解像度スクショ**：会話UI / 見守りタイムライン / 119原稿 / Weaveトレース。
- [ ] **プロダクト写真＋チーム写真**を用意。
- [ ] `TEAM_BIOS.md` にメンバー名・bio・captions を記入。
- [ ] **Ryzen AI PC で実測**（latency / memory / power）→ `TECHNICAL_SUMMARY.md` の `<FILL:…>` を埋める。
- [ ]（推奨）**W&B Weave** を有効化しトレースを記録・スクショ取得。
- [ ] **公開GitHubリポジトリ作成→push→URL取得**（ローカル整備済。`git remote add` → `git push`）。
   - URL を スライド4・`DEMO_ASSETS_README.txt`・`TEAM_BIOS.md` に反映。
- [ ] HTMLスライドを **PDF 書き出し**（ブラウザで開く→Cmd+P→Landscape→Save as PDF）。
- [ ] デモ資産を**暗号化**（zip暗号化等）し、フォルダ名 `TEAMNAME_Track1_HackTheLiquidWAY_DemoAssets`。
   **パスワードを Discord @liquid-yan に共有**。
- [ ] **13:30 JST までに提出**。
