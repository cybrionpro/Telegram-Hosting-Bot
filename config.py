# config.py

import os
from dotenv import load_dotenv

# Load environment variables from a .env file
load_dotenv()

class Config:
    """
    Main configuration class that holds all settings.
    Access settings using dot notation, e.g., config.bot.ADMIN_IDS
    """

    class Bot:
        """Bot-specific configurations from environment variables."""
        # --- Core Telegram API ---
        API_ID = os.getenv("API_ID")
        API_HASH = os.getenv("API_HASH")
        BOT_TOKEN = os.getenv("BOT_TOKEN")

        # --- Admin and Database ---
        # NOTE: Admin IDs should be a comma-separated string in your .env file
        # e.g., ADMIN_ID="12345,67890"
        ADMIN_STRING = os.getenv("ADMIN_ID", "0")
        try:
            ADMIN_IDS = [int(admin_id) for admin_id in ADMIN_STRING.split(',')]
        except (ValueError, TypeError):
            print("Warning: ADMIN_ID is not set correctly. Please provide a comma-separated list of user IDs.")
            ADMIN_IDS = []

        # --- Database ---
        MONGO_URI = os.getenv("MONGO_URI")
        MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "PyroHosterBot")
        FILEBROWSER_API_URL = os.getenv("FILEBROWSER_API_URL", "http://localhost:8080/api")
        FILEBROWSER_ADMIN_USER = os.getenv("FILEBROWSER_ADMIN_USER", "admin")
        FILEBROWSER_ADMIN_PASS = os.getenv("FILEBROWSER_ADMIN_PASS", "sunning112233#")
        FILEBROWSER_PUBLIC_URL = os.getenv("FILEBROWSER_PUBLIC_URL", "http://localhost:8080")
        PORT = os.getenv("PORT", "8080")


    class Premium:
        """Configurations related to premium features and payments."""
        # --- Payment Settings ---
        # The price in Telegram Stars to purchase one additional project slot.
        # The key '1' is the plan ID.
        PLANS = {
            '1': {
                'name': "Additional Project Slot",
                'description': "Adds 1 project slot with 1GB RAM for 30 days.",
                'stars': 100,         # Cost in Telegram Stars
                'duration_days': 30,  # How long the purchased slot is valid
                'ram_mb': 1024,       # RAM for a project in this slot (1 GB)
            }
        }
        # The currency for Telegram Stars payment. DO NOT CHANGE THIS.
        CURRENCY = "XTR"


    class User:
        """Default configurations for users."""
        # --- Free Tier Settings ---
        # The project quota for users who have not paid.
        FREE_USER_PROJECT_QUOTA = 1
        # The RAM limit in MB for a free user's project.
        FREE_USER_RAM_MB = 512

        # --- Project Settings ---
        # Maximum file size for project uploads in bytes (e.g., 50 * 1024 * 1024 = 50 MB)
        MAX_PROJECT_FILE_SIZE = 50 * 1024 * 1024


# Create a single, accessible instance of the configuration
config = Config()

# --- Validation ---
# Ensure critical variables are set to prevent the bot from starting with errors.
if not all([config.Bot.API_ID, config.Bot.API_HASH, config.Bot.BOT_TOKEN, config.Bot.MONGO_URI]):
    raise RuntimeError(
        "CRITICAL ERROR: API_ID, API_HASH, BOT_TOKEN, and MONGO_URI must be set in your .env file."
    )

if not config.Bot.ADMIN_IDS:
    print("WARNING: No ADMIN_ID found. The admin panel will be inaccessible.")