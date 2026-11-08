from dotenv import load_dotenv
load_dotenv()
import os
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
ADMIN_ID = os.getenv("ADMIN_ID")
RANKING_CHANNEL_ID = os.getenv("RANKING_CHANNEL_ID")
# APIログの送信先チャンネル (未設定なら従来のチャンネル)
LOG_CHANNEL_ID = os.getenv("LOG_CHANNEL_ID", "1486382744153100469")
# true にすると、管理者以外の登録に AtCoder アカウントの本人確認 (所属欄に確認コードを書く) を求める
REQUIRE_ATCODER_VERIFICATION = os.getenv("REQUIRE_ATCODER_VERIFICATION", "false").strip().lower() in ("1", "true", "yes", "on")
# SQLiteデータベースのパス (未設定なら起動したディレクトリの database.db)
DB_PATH = os.getenv("DB_PATH", "database.db")
