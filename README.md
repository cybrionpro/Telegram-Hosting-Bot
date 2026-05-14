# 🚀 Telegram-Hosting-Bot

**Telegram-Hosting-Bot** is a high-performance Telegram bot designed to provide a seamless hosting experience for Python projects. It allows users to deploy, manage, and monitor their bots and scripts directly from a Telegram interface, powered by a secure sandboxed environment.

---

## ✨ Key Features

- 🛠️ **Project Management:** Create, delete, and list multiple projects with ease.
- 🏗️ **Automated Deployment:** Install dependencies via `requirements.txt` and start/stop/restart projects with a single tap.
- 🛡️ **Sandboxed Execution:** Uses **Firejail** to ensure projects run in a secure, isolated environment, preventing system-wide access.
- 📁 **Web-based File Manager:** Integrated **FileBrowser** support for uploading and managing project files via a browser.
- 📊 **Resource Monitoring:** Real-time tracking of RAM and CPU usage per project.
- 📋 **Live Logs:** Fetch deployment and execution logs directly in the chat.
- ⭐ **Premium System:** Integrated subscription model using **Telegram Stars** for additional project slots and increased RAM limits.
- 🔐 **Admin Dashboard:** Powerful tools for managing users, projects, and system settings.

---

## 🛠️ Technology Stack

- **Framework:** [Pyrogram](https://github.com/pyrogram/pyrogram) (Asynchronous Telegram Framework)
- **Database:** [MongoDB](https://www.mongodb.com/) (using Motor for async support)
- **Security:** [Firejail](https://firejail.wordpress.com/) (Linux namespaces sandbox)
- **File Management:** [FileBrowser](https://filebrowser.org/)
- **Resource Tracking:** `psutil`

---

## 🚀 Getting Started

### 📋 Prerequisites

Before installing, ensure you have the following installed on your Linux server:

1.  **Python 3.9+**
2.  **MongoDB Instance**
3.  **Firejail**
    ```bash
    wget https://github.com/netblue30/firejail/releases/download/0.9.74/firejail_0.9.74_1_amd64.deb
    sudo apt install ./firejail_0.9.74_1_amd64.deb
    ```
4.  **FileBrowser**
    ```bash
    wget https://github.com/filebrowser/filebrowser/releases/download/v2.43.0/linux-amd64-filebrowser.tar.gz
    tar -xvzf linux-amd64-filebrowser.tar.gz
    chmod +x filebrowser
    sudo mv filebrowser /usr/local/bin/
    ```

### ⚙️ Installation

1.  **Clone the Repository:**
    ```bash
    git clone https://github.com/cybrionpro/Telegram-Hosting-Bot.git
    cd Telegram-Hosting-Bot
    ```

2.  **Install Dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

3.  **Configure Environment Variables:**
    Create a `.env` file from the provided `sample.env`:
    ```bash
    cp sample.env .env
    ```
    Edit `.env` and fill in your details:
    - `API_ID`, `API_HASH`, `BOT_TOKEN` (from @BotFather and my.telegram.org)
    - `MONGO_URI` (Your MongoDB connection string)
    - `ADMIN_ID` (Your Telegram User ID)
    - `FILEBROWSER_API_URL` (e.g., `https://yourdomain.com/api`)
    - `FILEBROWSER_ADMIN_USER` (Default: `admin`)
    - `FILEBROWSER_ADMIN_PASS` (Your FileBrowser admin password)
    - `FILEBROWSER_PUBLIC_URL` (e.g., `https://yourdomain.com`)
    - `PORT` (Default: `8080`)

4.  **Initialize FileBrowser:**
    ```bash
    filebrowser config init -d projects/filebrowser.db
    # Add an admin user (replace with your password)
    filebrowser -d projects/filebrowser.db users add admin YOUR_PASSWORD --perm.admin
    ```

5.  **Setup Security Shim (Fake Dotenv):**
    This project uses a security shim to prevent sandboxed projects from accessing the host filesystem for environment variables.
    ```bash
    # Create the directory
    sudo mkdir -p /opt/bytesupreme_safeguards/dotenv
    
    # Copy the shim to the directory as __init__.py
    sudo cp shim.py /opt/bytesupreme_safeguards/dotenv/__init__.py
    
    # Give your user ownership
    sudo chown -R $USER:$USER /opt/bytesupreme_safeguards
    ```

### 🏃 Running the Project (using Screen)

To keep the project running in the background, it is recommended to use `screen`.

1.  **Run FileBrowser in a screen session:**
    ```bash
    filebrowser -r projects -p 8080 -d projects/filebrowser.db --noauth -a 0.0.0.0
    ```

2.  **Start the Bot:**
    ```bash
    python3 bot.py
    ```

**Useful Commands:**
- View running screens: `screen -ls`
- Attach to bot session: `screen -r hosting-bot`
- Detach from session: Press `Ctrl+A` then `D`

---

## 🎥 Demo Video

Watch the bot in action here: [Telegram Video Demo](https://t.me/The_Hacking_Zone/1201)

---

## 🤝 Contributing

Contributions are welcome! If you have ideas for new features or improvements, feel free to open an issue or submit a pull request.

---

## 📜 License

This project is licensed under the **MIT License**. See the [LICENSE](LICENSE) file for details.

---

## 📞 Contact

If you face any issues or have questions, feel free to contact:
- **Telegram:** [@cybrion](https://t.me/cybrion)

---

**Developed with ❤️ by [cybrionpro](https://github.com/cybrionpro)**
