"""JSON-based storage for conversations.

Two backends, selected automatically by inspecting ``DATA_DIR``:

* **Local filesystem** (default): plain ``open()`` / ``os.listdir``. Used in
  local dev where ``DATA_DIR`` is a relative path like ``data/conversations``.
* **Databricks Workspace Files API**: used when ``DATA_DIR`` starts with
  ``/Workspace/``. The Databricks Apps container does not have POSIX write
  access to ``/Workspace/...`` paths, so we go through the SDK's workspace
  module. Auth uses the app's service-principal credentials, which the
  runtime injects as ``DATABRICKS_CLIENT_ID`` / ``DATABRICKS_CLIENT_SECRET``
  and ``DATABRICKS_HOST``; the SDK picks these up with no explicit config.
"""

import io
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .config import DATA_DIR

USE_WORKSPACE_API = DATA_DIR.startswith("/Workspace/")

_workspace_client = None


def _get_workspace_client():
    global _workspace_client
    if _workspace_client is None:
        from databricks.sdk import WorkspaceClient
        _workspace_client = WorkspaceClient()
    return _workspace_client


def _ensure_dir(directory: str) -> None:
    if USE_WORKSPACE_API:
        _get_workspace_client().workspace.mkdirs(directory)
        return
    Path(directory).mkdir(parents=True, exist_ok=True)


def _read_json(path: str) -> Optional[Dict[str, Any]]:
    if USE_WORKSPACE_API:
        from databricks.sdk.errors import NotFound
        try:
            with _get_workspace_client().workspace.download(path=path) as stream:
                raw = stream.read()
        except NotFound:
            return None
        return json.loads(raw.decode("utf-8"))
    if not os.path.exists(path):
        return None
    with open(path, "r") as f:
        return json.load(f)


def _write_json(path: str, data: Dict[str, Any]) -> None:
    encoded = json.dumps(data, indent=2).encode("utf-8")
    if USE_WORKSPACE_API:
        from databricks.sdk.service.workspace import ImportFormat
        _get_workspace_client().workspace.upload(
            path=path,
            content=io.BytesIO(encoded),
            format=ImportFormat.AUTO,
            overwrite=True,
        )
        return
    with open(path, "w") as f:
        f.write(encoded.decode("utf-8"))


def _list_json_paths(directory: str) -> List[str]:
    if USE_WORKSPACE_API:
        from databricks.sdk.errors import NotFound
        try:
            items = list(_get_workspace_client().workspace.list(directory))
        except NotFound:
            return []
        return [it.path for it in items if it.path and it.path.endswith(".json")]
    if not os.path.isdir(directory):
        return []
    return [
        os.path.join(directory, fname)
        for fname in os.listdir(directory)
        if fname.endswith(".json")
    ]


def ensure_data_dir() -> None:
    """Ensure the data directory exists (local mkdir or workspace mkdirs)."""
    _ensure_dir(DATA_DIR)


def get_conversation_path(conversation_id: str) -> str:
    """Return the full path/URI for a conversation file."""
    return os.path.join(DATA_DIR, f"{conversation_id}.json")


def create_conversation(conversation_id: str) -> Dict[str, Any]:
    ensure_data_dir()
    conversation = {
        "id": conversation_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "title": "New Conversation",
        "messages": [],
    }
    _write_json(get_conversation_path(conversation_id), conversation)
    return conversation


def get_conversation(conversation_id: str) -> Optional[Dict[str, Any]]:
    return _read_json(get_conversation_path(conversation_id))


def save_conversation(conversation: Dict[str, Any]) -> None:
    ensure_data_dir()
    _write_json(get_conversation_path(conversation["id"]), conversation)


def list_conversations() -> List[Dict[str, Any]]:
    ensure_data_dir()
    conversations = []
    for path in _list_json_paths(DATA_DIR):
        data = _read_json(path)
        if data is None:
            continue
        conversations.append({
            "id": data["id"],
            "created_at": data["created_at"],
            "title": data.get("title", "New Conversation"),
            "message_count": len(data["messages"]),
        })
    conversations.sort(key=lambda x: x["created_at"], reverse=True)
    return conversations


def add_user_message(conversation_id: str, content: str) -> None:
    conversation = get_conversation(conversation_id)
    if conversation is None:
        raise ValueError(f"Conversation {conversation_id} not found")
    conversation["messages"].append({"role": "user", "content": content})
    save_conversation(conversation)


def add_assistant_message(
    conversation_id: str,
    stage1: List[Dict[str, Any]],
    stage2: List[Dict[str, Any]],
    stage3: Dict[str, Any],
) -> None:
    conversation = get_conversation(conversation_id)
    if conversation is None:
        raise ValueError(f"Conversation {conversation_id} not found")
    conversation["messages"].append({
        "role": "assistant",
        "stage1": stage1,
        "stage2": stage2,
        "stage3": stage3,
    })
    save_conversation(conversation)


def update_conversation_title(conversation_id: str, title: str) -> None:
    conversation = get_conversation(conversation_id)
    if conversation is None:
        raise ValueError(f"Conversation {conversation_id} not found")
    conversation["title"] = title
    save_conversation(conversation)
