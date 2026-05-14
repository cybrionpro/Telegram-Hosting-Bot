import os
import logging
from dotenv import load_dotenv
from pyrogram import Client

# Load environment variables from .env file
load_dotenv()

# --- Configuration ---
API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")

# --- Logging Setup ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logging.getLogger("pyrogram").setLevel(logging.WARNING)
LOGGER = logging.getLogger(__name__)

# --- Pyrogram Client ---
class PyroHosterBot(Client):
    def __init__(self):
        super().__init__(
            "pyro_hoster_bot",
            api_id=API_ID,
            api_hash=API_HASH,
            bot_token=BOT_TOKEN,
            workers=20, # Number of concurrent workers
            plugins=dict(root="modules") # Tells pyrogram to load plugins from 'modules' folder
        )

    async def start(self):
        await super().start()
        me = await self.get_me()
        LOGGER.info(f"Bot started as {me.first_name} (@{me.username})")
        
    async def stop(self, *args):
        await super().stop()
        LOGGER.info("Bot stopped.")

if __name__ == "__main__":
    if not all([API_ID, API_HASH, BOT_TOKEN]):
        LOGGER.critical("CRITICAL: Environment variables are not set properly. Exiting.")
        exit()
    
    app = PyroHosterBot()
    app.run()