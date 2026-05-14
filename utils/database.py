# utils/database.py

import os
from datetime import datetime
from bson import ObjectId
import motor.motor_asyncio
from config import config # Import the new config

# --- Database Client ---
client = motor.motor_asyncio.AsyncIOMotorClient(config.Bot.MONGO_URI)
db = client[config.Bot.MONGO_DB_NAME]

# --- Collections ---
users_collection = db['users']
projects_collection = db['projects']
settings_collection = db['bot_settings'] # New collection for global settings

# -------------------------------------------------------------------------------- #
# USER FUNCTIONS
# -------------------------------------------------------------------------------- #

async def add_user(user_id, username):
    """
    Adds a new user or updates their username.
    Crucially, it sets the default project quota on insertion.
    """
    await users_collection.update_one(
        {'_id': user_id},
        {
            '$set': {'username': username},
            '$setOnInsert': {
                'joined_at': datetime.utcnow(),
                'project_quota': config.User.FREE_USER_PROJECT_QUOTA
            }
        },
        upsert=True
    )

async def find_user_by_id(user_id: int):
    """Finds a single user document by their Telegram ID."""
    return await users_collection.find_one({'_id': user_id})

async def increase_user_project_quota(user_id: int, amount: int = 1):
    """Increases (or decreases) a user's project quota."""
    result = await users_collection.find_one_and_update(
        {'_id': user_id},
        {'$inc': {'project_quota': amount}},
        return_document=True
    )
    return result.get('project_quota', config.User.FREE_USER_PROJECT_QUOTA)

async def get_all_users(count_only=False):
    """Returns a list of all user documents or just the count."""
    if count_only:
        return await users_collection.count_documents({})
    return await users_collection.find({}).to_list(None)

# -------------------------------------------------------------------------------- #
# PROJECT FUNCTIONS
# -------------------------------------------------------------------------------- #

async def add_project(user_id: int, project_name: str, path: str, fb_user: str, fb_pass: str, is_premium: bool, expiry_date: datetime | None, ram_limit_mb: int):
    """Adds a new project to the database with premium status and resource limits."""
    project_doc = {
        'user_id': user_id,
        'name': project_name,
        'path': path,
        'created_at': datetime.utcnow(),
        'is_premium': is_premium,
        'expiry_date': expiry_date,
        'is_locked': False, # Projects are never locked on creation
        'run_command': 'python3 main.py',
        'resource_limits': {
            'cpu': 50,  # Example value, can be adjusted
            'ram': ram_limit_mb,
            'timeout': 3600  # Example value
        },
        'filebrowser_creds': {'user': fb_user, 'pass': fb_pass},
        'execution_info': {
            'last_run_time': None,
            'exit_code': None,
            'status': 'not_run', # not_run, running, success, fail, stopped, crashed
            'log_file': os.path.join(path, "project.log"),
            'is_running': False,
            'pid': None
        }
    }
    result = await projects_collection.insert_one(project_doc)
    return str(result.inserted_id)

async def get_user_projects(user_id: int):
    """Gets all projects for a specific user."""
    return await projects_collection.find({'user_id': user_id}).to_list(None)

async def get_project_by_id(project_id: str):
    """Gets a single project by its MongoDB ObjectId string."""
    try:
        return await projects_collection.find_one({'_id': ObjectId(project_id)})
    except Exception:
        return None

async def update_project_config(project_id: str, updates: dict):
    """
    Updates specific top-level fields of a project document.
    Example: update_project_config(pid, {"is_locked": True, "expiry_date": new_date})
    """
    await projects_collection.update_one(
        {'_id': ObjectId(project_id)},
        {'$set': updates}
    )

async def update_project_execution_info(project_id: str, exec_info: dict):
    """Updates the execution_info sub-document for a project."""
    await projects_collection.update_one(
        {'_id': ObjectId(project_id)},
        {'$set': {f'execution_info.{k}': v for k, v in exec_info.items()}}
    )

async def delete_project(project_id: str):
    """Deletes a project from the database."""
    await projects_collection.delete_one({'_id': ObjectId(project_id)})

async def get_last_premium_project(user_id: int):
    """
    Finds the user's most recently created, unlocked, premium project.
    This is the prime candidate for locking when quota is reduced.
    """
    # Sorts by creation date descending, gets the first one that matches.
    return await projects_collection.find_one(
        {
            'user_id': user_id,
            'is_premium': True,
            'is_locked': False
        },
        sort=[('created_at', -1)] # -1 for descending order
    )

# In utils/database.py -> Add to PROJECT FUNCTIONS section

async def get_first_locked_project(user_id: int):
    """
    Finds the user's most recently created, LOCKED, premium project.
    This is the prime candidate for unlocking when quota is granted by an admin.
    """
    # Sorts by creation date descending, gets the first one that matches.
    return await projects_collection.find_one(
        {
            'user_id': user_id,
            'is_premium': True,
            'is_locked': True  # Important: we are looking for a locked project
        },
        sort=[('created_at', -1)] # -1 for descending order
    )

# -------------------------------------------------------------------------------- #
# STATS FUNCTIONS (for Admin Panel)
# -------------------------------------------------------------------------------- #

async def get_all_projects_count():
    """Returns the total count of projects in the database."""
    return await projects_collection.count_documents({})

async def get_all_premium_projects_count():
    """Returns the total count of projects marked as premium."""
    return await projects_collection.count_documents({'is_premium': True})

async def get_active_projects_count():
    """Returns the total count of currently running projects."""
    return await projects_collection.count_documents({'execution_info.is_running': True})

async def get_premium_users_count():
    """Counts users who have a project quota greater than the free tier default."""
    # This query finds users who have bought at least one slot.
    return await users_collection.count_documents(
        {'project_quota': {'$gt': config.User.FREE_USER_PROJECT_QUOTA}}
    )

# -------------------------------------------------------------------------------- #
# GLOBAL SETTINGS FUNCTIONS (for Admin Panel)
# -------------------------------------------------------------------------------- #

async def get_global_settings():
    """
    Retrieves the global bot settings document.
    Creates a default one if it doesn't exist.
    """
    settings = await settings_collection.find_one({'_id': 'global_config'})
    if not settings:
        default_settings = {
            '_id': 'global_config',
            'free_user_ram_mb': config.User.FREE_USER_RAM_MB
        }
        await settings_collection.insert_one(default_settings)
        return default_settings
    return settings

async def update_global_setting(key: str, value):
    """Updates a specific global setting."""
    await settings_collection.update_one(
        {'_id': 'global_config'},
        {'$set': {key: value}},
        upsert=True
    )