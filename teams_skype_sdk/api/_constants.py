"""[Constants] All API-level constants for the Teams API package."""

# ---------------------------------------------------------------------------
# Conversation type constants for filtering
# ---------------------------------------------------------------------------

# System conversation types - completely filtered (no tool)
SYSTEM_CONV_TYPES = {"topic", "streamofannotations"}

# Activity stream types - separate tool (teams_list_activity)
ACTIVITY_CONV_TYPES = {"streamofnotifications", "streamofmentions"}

# Space types - separate tool (teams_list_spaces)
SPACE_CONV_TYPES = {"space"}

# Notes types - separate tool (teams_list_notes)
NOTES_CONV_TYPES = {"streamofnotes"}

# Call logs types - separate tool (teams_list_call_logs)
CALLLOGS_CONV_TYPES = {"streamofcalllogs"}

# Threads types - separate tool (teams_list_threads)
THREADS_CONV_TYPES = {"streamofthreads"}

# Saved types - separate tool (teams_list_saved)
SAVED_CONV_TYPES = {"streamofsaved"}

# All types to filter from list_conversations (chat, group, meeting remain)
FILTERED_CONV_TYPES = (
    SYSTEM_CONV_TYPES
    | ACTIVITY_CONV_TYPES
    | SPACE_CONV_TYPES
    | NOTES_CONV_TYPES
    | CALLLOGS_CONV_TYPES
    | THREADS_CONV_TYPES
    | SAVED_CONV_TYPES
)

# ---------------------------------------------------------------------------
# Pagination constants
# ---------------------------------------------------------------------------

MAX_PAGE_SIZE = 200       # Maximum items users can request
API_MAX_PAGE_SIZE = 50    # Teams API single request limit
MAX_FETCH_PAGES = 10      # Hard cap: max API pages when searching for rare types

# ---------------------------------------------------------------------------
# Reactions
# ---------------------------------------------------------------------------

VALID_REACTIONS = {"like", "heart", "laugh", "surprised", "sad", "angry"}

REACTION_EMOJI_MAP = {
    "like": "\U0001f44d",      # 👍
    "heart": "\u2764\ufe0f",   # ❤️
    "laugh": "\U0001f604",     # 😄
    "surprised": "\U0001f62e", # 😮
    "sad": "\U0001f622",       # 😢
    "angry": "\U0001f621",     # 😡
}

# Reverse mapping (defensive: in case API returns emoji keys in the future)
EMOJI_REACTION_MAP = {v: k for k, v in REACTION_EMOJI_MAP.items()}

# ---------------------------------------------------------------------------
# Message content limits
# ---------------------------------------------------------------------------

MAX_MESSAGE_HTML_BYTES = 25_000    # Safe limit (Teams API rejects ~28 KB)
MAX_CARD_ROWS = 50                 # ~250 bytes/row HTML overhead

# ---------------------------------------------------------------------------
# API Endpoints
# ---------------------------------------------------------------------------

CHATSVC_BASE = "https://amer.ng.msg.teams.microsoft.com/v1/users/ME"
MSG_BASE = "https://amer.ng.msg.teams.microsoft.com/v1/users/ME"
AMS_BASE_URL = "https://api.asm.skype.com/v1/objects"
AMS_USER_AGENT = "27/1.0.0.0"
