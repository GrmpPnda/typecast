from app.models.chapter import Chapter
from app.models.codex import CodexEntry
from app.models.codex_association import CodexAssociation
from app.models.codex_image import CodexImage
from app.models.comment import Comment
from app.models.config import AppConfig
from app.models.conversation import Conversation, ConversationMessage
from app.models.font import Font
from app.models.image import Image
from app.models.profile import Profile
from app.models.scene import Scene
from app.models.section import Section
from app.models.series import Series
from app.models.user import User
from app.models.work import Work

# Importing this package must register every table on Base.metadata. Alembic
# autogenerate and the test harness both rely on that: a model missing here is
# invisible to them even though the app still works, because importing the API
# layer registers it as a side effect.
__all__ = [
    "AppConfig", "Chapter", "CodexAssociation", "CodexEntry",
    "CodexImage", "Comment", "Conversation", "ConversationMessage", "Font",
    "Image", "Profile", "Scene", "Section", "Series", "User", "Work",
]
