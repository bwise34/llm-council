"""Configuration for the LLM Council."""

import os
from dotenv import load_dotenv

load_dotenv()

# OpenRouter API key
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

# Council members - list of OpenRouter model identifiers
COUNCIL_MODELS = [
    "openai/gpt-5.4",
    "google/gemini-3.1-flash-lite",
    "anthropic/claude-sonnet-4.6",
    "x-ai/grok-4.3",
]

# Chairman model - synthesizes final response
CHAIRMAN_MODEL = "anthropic/claude-opus-4.7"

# OpenRouter API endpoint
OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"

# Data directory for conversation storage.
# In local dev this defaults to a relative path; in Databricks Apps it is
# set via app.yaml to a workspace files path (e.g.
# /Workspace/Users/<email>/data/conversations).
DATA_DIR = os.getenv("DATA_DIR", "data/conversations")
