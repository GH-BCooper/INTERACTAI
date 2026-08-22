"""Import every model so Base.metadata is complete for Alembic autogenerate and create_all."""

from .annotation import Annotation
from .base import Base
from .content import Persona, Rubric, RubricCriterion, Scenario
from .jobs import FailedJob
from .observability import LatencyEvent, ModelCall
from .scoring import Report, SessionScore
from .session import Session
from .turn import Turn, TurnMetrics, TurnScore
from .user import Profile, User

__all__ = [
    "Annotation",
    "Base",
    "FailedJob",
    "LatencyEvent",
    "ModelCall",
    "Persona",
    "Profile",
    "Report",
    "Rubric",
    "RubricCriterion",
    "Scenario",
    "Session",
    "SessionScore",
    "Turn",
    "TurnMetrics",
    "TurnScore",
    "User",
]
