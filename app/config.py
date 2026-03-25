from dotenv import load_dotenv
load_dotenv()
import os
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
ADMIN_ID = os.getenv("ADMIN_ID")
RANKING_CHANNEL_ID = os.getenv("RANKING_CHANNEL_ID")