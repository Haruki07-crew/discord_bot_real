from dotenv import load_dotenv
load_dotenv()
import os
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
ADMIN_ID = os.getenv("ADMIN_ID")
RANKING_CHANNEL_ID = os.getenv("RANKING_CHANNEL_ID")
# APIログの送信先チャンネル (未設定なら従来のチャンネル)
LOG_CHANNEL_ID = os.getenv("LOG_CHANNEL_ID", "1486382744153100469")
