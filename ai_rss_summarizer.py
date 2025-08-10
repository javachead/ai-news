print("=== AI記事要約スクリプト開始 ===")
print("環境変数チェック中...")
import os
print(f"AI_FEED_URLS: {os.getenv('AI_FEED_URLS', 'NOT SET')}")
print(f"DRY_RUN: {os.getenv('DRY_RUN', 'NOT SET')}")
print("=== スクリプト正常終了 ===")
