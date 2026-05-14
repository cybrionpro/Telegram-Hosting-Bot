# In utils/deployment_helper.py -- VENV AWARE VERSION

import os
import asyncio
import subprocess
import psutil
from datetime import datetime
from dotenv import dotenv_values  # ✅ import this
from .database import update_project_execution_info, get_project_by_id

running_processes = {}

SAFEGUARD_PATH = "/opt/bytesupreme_safeguards"

FIREJAIL_PROFILE = [
    "firejail",
    "--quiet",
    "--noprofile",
    "--private={project_path}",
    #"--net={net_access}", # Dynamic network access
    "--whitelist={project_path}",
    "--read-only=/opt/bytesupreme_safeguards",
    "--rlimit-as={ram_in_bytes}",
    "--cpu={cpu_cores}",
    "--blacklist=/home/bytesupreme_online/.env",
]

# Helper to get the path to the venv's Python interpreter
def get_venv_python(project_path):
    return os.path.join(project_path, ".venv", "bin", "python")

# --- Installation Logic ---
# In utils/deployment_helper.py, also replace this function.

async def install_project_dependencies(project_id, project):
    """
    Creates a venv and installs dependencies from requirements.txt into it.
    """
    project_path = project['path']
    venv_path = os.path.join(project_path, ".venv")
    requirements_path = os.path.join(project_path, "requirements.txt")

    # Step 1: Create venv (This happens outside firejail, so it's fine)
    if not os.path.exists(venv_path):
        create_venv_cmd = ["python3", "-m", "venv", venv_path]
        process = await asyncio.create_subprocess_exec(
            *create_venv_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        if process.returncode != 0:
            return False, f"Failed to create virtual environment:\n{stderr.decode()}"

    # Step 2: Install dependencies inside the sandbox
    if os.path.exists(requirements_path):
        net_access = "wlp3s0"
        
        firejail_cmd = [part.format(
            project_path=project_path,
            net_access=net_access,
            ram_in_bytes='209715200',
            cpu_cores='0,1'
        ) for part in FIREJAIL_PROFILE]

        # --- THE FIX IS HERE ---
        # Use the relative path to the venv's Python for the pip command
        venv_python_relative = ".venv/bin/python"
        pip_install_cmd = [
            venv_python_relative, "-m", "pip", "install", "--no-cache-dir",
            "-r", "requirements.txt"
        ]
        
        full_cmd = firejail_cmd + pip_install_cmd
        
        process = await asyncio.create_subprocess_exec(
            *full_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            # We must still run from the project_path on the host system
            cwd=project_path,
            close_fds=True,
            env={}
        )
        stdout, stderr = await process.communicate()
        
        if process.returncode != 0:
            return False, f"Failed to install dependencies:\n{stderr.decode()}"

    return True, "Virtual environment is ready. Dependencies installed."


# --- Execution Logic (Start, Stop, etc.) ---

async def start_project(project_id: str, project: dict):
    if project_id in running_processes and running_processes[project_id].poll() is None:
        return False, "Project is already running."

    try:
        # Build Firejail command
        cmd_list = await _build_firejail_command(project, network_access=False)
        
        # Path to the venv's Python
        venv_python = os.path.join(project['path'], ".venv", "bin", "python")
        if not os.path.exists(venv_python):
            return False, "Virtual environment not found. Please run 'Install Dependencies' first."

        # Open log file
        log_file = open(project['execution_info']['log_file'], 'w')

        # ✅ Load user-specific .env from their project directory
        user_env_path = os.path.join(project['path'], '.env')
        user_env_vars = dotenv_values(user_env_path) if os.path.exists(user_env_path) else {}

        # ✅ Define environment to pass to subprocess
        process_env = {
            "PATH": "/usr/bin:/bin",
            "HOME": project['path'],
            "PYTHONPATH": SAFEGUARD_PATH,
            **user_env_vars  # Inject user-defined env vars
        }
        print(f"Using environment variables: {process_env}")

        # ✅ Start the process in Firejail with custom env
        process = subprocess.Popen(
            cmd_list,
            cwd=project['path'],
            stdout=log_file,
            stderr=log_file,
            close_fds=True,
            start_new_session=True,
            env=process_env
        )

        # Track and save metadata
        running_processes[project_id] = process
        update_data = {
            'is_running': True,
            'pid': process.pid,
            'last_run_time': datetime.utcnow(),
            'status': 'running'
        }
        await update_project_execution_info(project_id, update_data)

        ram_allocated = project.get('resource_limits', {}).get('ram')
        return True, f"Process started with PID: {process.pid}. RAM allocated: {ram_allocated}MB."

    except FileNotFoundError as e:
        return False, f"Execution failed: A required file was not found. Have you installed dependencies? Details: {e}"

    except Exception as e:
        return False, f"Execution failed: {e}"



# ... Other functions (stop, restart, etc) are fine, just the build helper needs a change ...

# In utils/deployment_helper.py, replace only this function.

async def _build_firejail_command(project: dict, network_access: bool = False):
    """
    Builds the firejail command using venv, with toggleable network
    and dynamic RAM allocation based on project tier.
    """
    project_path = project['path']
    # --- DYNAMIC RAM ALLOCATION ---
    # Fetch the RAM limit directly from the project's own config.
    # This was set when the project was created (free or premium).
    ram_limit_mb = project.get('resource_limits', {}).get('ram', 512) # Default to 512 if not found
    
    user_run_command = project.get('run_command', 'python3 main.py').split()
    script_name = user_run_command[-1]
    
    if not os.path.exists(os.path.join(project_path, script_name)):
        raise FileNotFoundError(f"Main script '{script_name}' not found.")
    
    venv_python_relative_path = ".venv/bin/python" 
    run_cmd = [venv_python_relative_path] + user_run_command[1:]

    ram_in_bytes = ram_limit_mb * 1024 * 1024
    cpu_cores_list = "0"  # Example, can be made dynamic later if needed
    
    # We set a default network interface. Adjust if your server uses a different one.
    # Common names: eth0, ens3, enp0s3
    net_access_str = "wlp3s0" 

    firejail_cmd = [part.format(
        project_path=project_path,
        net_access=net_access_str,
        ram_in_bytes=ram_in_bytes,
        cpu_cores=cpu_cores_list
    ) for part in FIREJAIL_PROFILE]

    print(f"Building firejail command: {firejail_cmd + run_cmd}")

    return firejail_cmd + run_cmd

# The rest of the functions from your last working file (stop_project, restart_project, get_status, etc.)
# can be pasted here. They do not need modification as they only interact with the process,
# not with how it was built. I am adding them below for completeness.

async def stop_project(project_id):
    if project_id not in running_processes: return False, "Project is not running or process not tracked."
    process = running_processes.pop(project_id)
    if process.poll() is not None: return False, "Process was already stopped."
    try:
        process.terminate()
        try: process.wait(timeout=5)
        except subprocess.TimeoutExpired: process.kill()
        await update_project_execution_info(project_id, {'is_running': False, 'pid': None, 'status': 'stopped'})
        return True, "Process terminated successfully."
    except Exception as e: return False, f"Failed to stop process: {e}"

async def restart_project(project_id, project):
    await stop_project(project_id)
    await asyncio.sleep(1)
    return await start_project(project_id, project)

async def get_project_status(project_id, project, detailed=False):
    exec_info = project['execution_info']
    is_running = False
    if project_id in running_processes and running_processes[project_id].poll() is None: is_running = True
    if is_running:
        status, pid = "🟢 Running", running_processes[project_id].pid
        try:
            p = psutil.Process(pid)
            uptime = datetime.now() - datetime.fromtimestamp(p.create_time())
            uptime_str = str(uptime).split('.')[0]
        except psutil.NoSuchProcess: status, pid, uptime_str = "🔴 Stopped (Process not found)", "N/A", "N/A"
    else:
        status, pid, uptime_str = "🔴 Stopped", "N/A", "N/A"
        if exec_info.get('is_running'):
            await update_project_execution_info(project_id, {'is_running': False, 'pid': None, 'status': 'crashed'})
            status = "🟠 Crashed"
    if not detailed: return status
    last_run_str = "Never"
    if isinstance(exec_info.get('last_run_time'), datetime): last_run_str = exec_info['last_run_time'].strftime("%Y-%m-%d %H:%M:%S UTC")
    return (f"**Project Status for `{project['name']}`**\n\n"
            f"🔹 **Status:** {status}\n🔹 **PID:** `{pid}`\n🔹 **Uptime:** `{uptime_str}`\n"
            f"🔹 **Last Run:** `{last_run_str}`\n🔹 **Last Exit Code:** `{exec_info.get('exit_code', 'N/A')}`\n"
            f"🔹 **Run Command:** `{project.get('run_command')}`")

async def get_project_logs(project_id):
    project = await get_project_by_id(project_id)
    return project['execution_info']['log_file']

async def get_project_usage(project_id):
    if project_id not in running_processes: return "Project is not running."
    if running_processes[project_id].poll() is not None: return "Project is stopped."
    try:
        p = psutil.Process(running_processes[project_id].pid)
        cpu_usage, mem_info = p.cpu_percent(interval=1), p.memory_info()
        ram_usage = mem_info.rss / (1024 * 1024)
        return (f"**Resource Usage for PID `{p.pid}`**\n\n📊 **CPU:** {cpu_usage:.2f} %\n🧠 **RAM:** {ram_usage:.2f} MB")
    except psutil.NoSuchProcess: return "Process not found. It might have stopped."
    except Exception as e: return f"Could not retrieve usage: {e}"
