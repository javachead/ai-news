# AI News to Slack (Java + GitHub Actions)

**無料ソース（RSS）→ Slack (#ai-news など) に自動投稿**する最小構成です。  
毎時実行（UTC）で直近 N 分（デフォルト 70 分）に公開された記事だけを投稿します。

## 1) 使い方

### A. Slack Webhook を作る
- Slack で Incoming Webhooks を有効化し、送り先チャンネルを選択（例: `#ai-news`）
- 取得した URL を GitHub Secrets に `SLACK_WEBHOOK_URL` 名で保存

### B. RSS を登録（FEED_URLS）
GitHub Secrets に `FEED_URLS` を登録（カンマ区切り）
