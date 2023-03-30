from typing import Optional, Any

import redis
import uuid
from datetime import datetime
import json
import logging

import config

logger = logging.getLogger(__name__)


class Database:
    def __init__(self):
        self.redis_client = redis.Redis.from_url(config.redis_url)

    def check_if_user_exists(self, user_id: int, raise_exception: bool = False):
        if self.redis_client.exists(f"user:{user_id}"):
            return True
        else:
            if raise_exception:
                raise ValueError(f"User {user_id} does not exist")
            else:
                return False

    def add_new_user(
        self,
        user_id: int,
        chat_id: int,
        username: str = "",
        first_name: str = "",
        last_name: str = "",
    ):
        user_key = f"user:{user_id}"
        if not self.check_if_user_exists(user_id):
            user_dict = {
                "chat_id": chat_id,
                "username": username,
                "first_name": first_name,
                "last_name": last_name,
                "last_interaction": datetime.now().isoformat(),
                "first_seen": datetime.now().isoformat(),
                "current_dialog_id": json.dumps(None),
                "current_chat_mode": "assistant",
                "current_model": config.models["available_text_models"][0],
                "n_used_tokens": json.dumps({}),
                "n_transcribed_seconds": 0.0,
            }
            self.redis_client.hmset(user_key, user_dict)

    def start_new_dialog(self, user_id: int):
        self.check_if_user_exists(user_id, raise_exception=True)

        dialog_id = str(uuid.uuid4())
        dialog_key = f"dialog:{dialog_id}"
        dialog_dict = {
            "user_id": user_id,
            "chat_mode": self.get_user_attribute(user_id, "current_chat_mode"),
            "start_time": datetime.now().isoformat(),
            "model": self.get_user_attribute(user_id, "current_model"),
            "messages": json.dumps([]),
        }

        # add new dialog
        self.redis_client.hmset(dialog_key, dialog_dict)

        # update user's current dialog
        self.set_user_attribute(user_id, "current_dialog_id", dialog_id)

        return dialog_id

    def get_user_attribute(self, user_id: int, key: str):
        self.check_if_user_exists(user_id, raise_exception=True)
        user_key = f"user:{user_id}"
        value = self.redis_client.hget(user_key, key)

        # If the value is bytes, decode it to a string
        if isinstance(value, bytes):
            value = value.decode("utf-8")

        # If the value is a JSON string, load it back to a Python object
        if key in ["n_used_tokens"]:
            value = json.loads(value)

        return value

    def set_user_attribute(self, user_id: int, key: str, value: Any):
        self.check_if_user_exists(user_id, raise_exception=True)
        self.redis_client.hset(f"user:{user_id}", key, value)

    def update_n_used_tokens(
        self, user_id: int, model: str, n_input_tokens: int, n_output_tokens: int
    ):
        n_used_tokens_dict = self.get_user_attribute(user_id, "n_used_tokens")

        if model in n_used_tokens_dict:
            n_used_tokens_dict[model]["n_input_tokens"] += n_input_tokens
            n_used_tokens_dict[model]["n_output_tokens"] += n_output_tokens
        else:
            n_used_tokens_dict[model] = {
                "n_input_tokens": n_input_tokens,
                "n_output_tokens": n_output_tokens,
            }

        self.set_user_attribute(
            user_id, "n_used_tokens", json.dumps(n_used_tokens_dict)
        )

    def get_dialog_messages(self, user_id: int, dialog_id: Optional[str] = None):
        self.check_if_user_exists(user_id, raise_exception=True)

        if dialog_id is None:
            dialog_id = self.get_user_attribute(user_id, "current_dialog_id")

        dialog_key = f"dialog:{dialog_id}"
        messages = self.redis_client.hget(dialog_key, "messages")
        if messages:
            messages = messages.decode("utf-8")
            return json.loads(messages)
        else:
            return []

    def set_dialog_messages(
        self, user_id: int, dialog_messages: list, dialog_id: Optional[str] = None
    ):
        self.check_if_user_exists(user_id, raise_exception=True)

        if dialog_id is None:
            dialog_id = self.get_user_attribute(user_id, "current_dialog_id")

        dialog_key = f"dialog:{dialog_id}"
        self.redis_client.hset(dialog_key, "messages", json.dumps(dialog_messages))
