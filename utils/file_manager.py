# In utils/file_manager.py -- FINAL CORRECTED VERSION

import os
import requests
import shutil
from dotenv import load_dotenv
from config import Config

load_dotenv()

# --- Configuration (from .env file) ---
FILEBROWSER_API_URL = Config.Bot.FILEBROWSER_API_URL
FILEBROWSER_ADMIN_USER = Config.Bot.FILEBROWSER_ADMIN_USER
FILEBROWSER_ADMIN_PASS = Config.Bot.FILEBROWSER_ADMIN_PASS
FILEBROWSER_PUBLIC_URL = Config.Bot.FILEBROWSER_PUBLIC_URL
PORT = Config.Bot.PORT

# --- Helper Functions (Internal Logic) ---

def _get_admin_token():
    if not FILEBROWSER_ADMIN_USER or not FILEBROWSER_ADMIN_PASS:
        raise ValueError("FILEBROWSER_ADMIN_USER and FILEBROWSER_ADMIN_PASS must be set.")
    base_url = FILEBROWSER_API_URL.rsplit('/api', 1)[0]
    login_url = f"{base_url}/api/login"
    try:
        response = requests.post(
            login_url,
            json={"username": FILEBROWSER_ADMIN_USER, "password": FILEBROWSER_ADMIN_PASS},
            timeout=10
        )
        response.raise_for_status()
        return response.text
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"Failed to get File Browser admin token: {e}") from e

def _get_user_by_name(token, username):
    headers = {"X-Auth": token}
    response = requests.get(f"{FILEBROWSER_API_URL}/users", headers=headers, timeout=10)
    response.raise_for_status()
    for user in response.json():
        if user['username'] == username:
            return user
    return None

# In utils/file_manager.py

def _create_user(token, username, password, scope_path):
    """
    Creates a new user via the API using the exact 'envelope' payload
    structure you have specified.
    """
    headers = {"X-Auth": token}

    # This is the user object itself, the 'data' part of the payload.
    user_details = {
        "scope": scope_path,
        "locale": "en",
        "viewMode": "list",
        "singleClick": False,
        "sorting": {
            "by": "name",
            "asc": False
        },
        "perm": {
            "admin": False,
            "execute": True,
            "create": True,
            "rename": True,
            "modify": True,
            "delete": True,
            "share": True,
            "download": True
        },
        "commands": [],
        "hideDotfiles": False,
        "dateFormat": False,
        "username": username,
        "password": password,
        "rules": [],
        "lockPassword": False,
        # The 'id' is correctly omitted as the server assigns it.
    }

    # --- WRAPPER PAYLOAD ---
    # We now wrap the user_details inside the full request envelope.
    request_payload = {
        "what": "user",
        "which": [],
        "data": user_details
    }
    
    # It is possible this kind of command endpoint is different.
    # The most likely endpoint is still `/api/users`. If that fails,
    # another common pattern is a generic resource or command endpoint.
    # We will try the standard one first as it is the most probable.
    creation_url = f"{FILEBROWSER_API_URL}/users"

    try:
        response = requests.post(creation_url, headers=headers, json=request_payload, timeout=10)
        response.raise_for_status()
        print(f"SUCCESS: User '{username}' created using the wrapper payload.")
    except requests.exceptions.HTTPError as e:
        print(f"ERROR: Failed to create user with the wrapper payload at {creation_url}.")
        print(f"ERROR: Status Code: {e.response.status_code}")
        print(f"ERROR: Response Body: {e.response.text}")
        raise e

def _update_user(token, user_id, username, password, scope_path):
    headers = {"X-Auth": token}
    print(f"Updating user ID '{user_id}' with username '{username}' and scope '{scope_path}'")
    update_data = {
        "scope": scope_path,
        "locale": "en",
        "viewMode": "list",
        "singleClick": False,
        "sorting": {
            "by": "name",
            "asc": False
        },
        "perm": {
            "admin": False,
            "execute": True,
            "create": True,
            "rename": True,
            "modify": True,
            "delete": True,
            "share": True,
            "download": True
        },
        "commands": [],
        "hideDotfiles": False,
        "dateFormat": False,
        "username": username,
        "password": password,
        "rules": [],
        "lockPassword": False,
        "id":user_id,
    }
    request_payload = {
        "what": "user",
        "which": ["all"],
        "data": update_data
    }
    response = requests.put(f"{FILEBROWSER_API_URL}/users/{user_id}", headers=headers, json=request_payload, timeout=10)
    response.raise_for_status()
    print(f"Successfully updated user ID '{user_id}'")


async def start_filebrowser_session(project_id, project_details):

    raj = project_details['path']
    root_path = raj.split("projects/")[-1]

    fb_creds = project_details['filebrowser_creds']
    fb_user = fb_creds['user']
    fb_pass = fb_creds['pass']
    
    user_home_path = root_path
    os.makedirs(f"projects/{user_home_path}", exist_ok=True)
    print(f"Ensuring user '{fb_user}' with scope '{user_home_path}' exists.")

    try:
        admin_token = _get_admin_token()
        existing_user = _get_user_by_name(admin_token, fb_user)
        
        if existing_user:
            print(f"User '{fb_user}' already exists. Updating credentials.")
            _update_user(admin_token, existing_user['id'], fb_user, fb_pass, user_home_path)
        else:
            print(f"User '{fb_user}' not found. Creating new user.")
            _create_user(admin_token, fb_user, fb_pass, user_home_path)

        url = FILEBROWSER_PUBLIC_URL.strip().rstrip('/')
        print(url)
        port = int(PORT)
        print(port)
        
        return url, port
    except Exception as e:
        raise RuntimeError(f"Could not ensure FileBrowser user: {e}")


async def stop_filebrowser_session(project_id, project_details):
    raj = project_details['path']
    root_path = raj.split("projects/")[-1]
    
    fb_creds = project_details['filebrowser_creds']
    fb_user = fb_creds['user']
    username_to_delete = fb_user
    print(f"Attempting to stop session for user '{username_to_delete}'...")
    try:
        admin_token = _get_admin_token()
        user_to_delete = _get_user_by_name(admin_token, username_to_delete)

        if user_to_delete:
            user_id = user_to_delete['id']
            headers = {"X-Auth": admin_token}
            requests.delete(f"{FILEBROWSER_API_URL}/users/{user_id}", headers=headers, timeout=10).raise_for_status()
            print(f"Successfully deleted user '{username_to_delete}'.")
            
            user_home_path = f"projects/{root_path}"
            if os.path.exists(user_home_path):
                shutil.rmtree(user_home_path)
                print(f"Successfully removed data directory: {user_home_path}")
            return True
        else:
            print(f"User '{username_to_delete}' not found, nothing to delete.")
            return False
    except Exception as e:
        print(f"Error stopping session for project {project_id}: {e}")
        return False