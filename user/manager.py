"""
用户管理
"""
import json
import os
from datetime import datetime
from utils.logger import get_logger

logger = get_logger("user.manager")

USERS_FILE = "data/users.json"


class UserManager:
    """用户管理"""

    def __init__(self, file_path: str = USERS_FILE):
        self.file_path = file_path
        self._users: dict[str, dict] = {}
        self._load()

    def _load(self):
        if os.path.exists(self.file_path):
            with open(self.file_path, "r") as f:
                self._users = json.load(f)

    def _save(self):
        os.makedirs(os.path.dirname(self.file_path) or ".", exist_ok=True)
        with open(self.file_path, "w") as f:
            json.dump(self._users, f, indent=2, ensure_ascii=False)

    def create_user(self, username: str, password: str, role: str = "user") -> dict | None:
        if username in self._users:
            return None
        self._users[username] = {
            "username": username,
            "password": password,
            "role": role,
            "created_at": datetime.now().isoformat(),
        }
        self._save()
        logger.info(f"用户已创建: {username}")
        return self._users[username]

    def get_user(self, username: str) -> dict | None:
        return self._users.get(username)

    def list_users(self) -> list[dict]:
        return list(self._users.values())

    def delete_user(self, username: str) -> bool:
        if username not in self._users:
            return False
        del self._users[username]
        self._save()
        return True

    def authenticate(self, username: str, password: str) -> dict | None:
        user = self._users.get(username)
        if user and user.get("password") == password:
            return user
        return None
