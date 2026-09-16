"""Import every model so Base.metadata is complete for Alembic autogenerate and create_all."""

from .annotation import Annotation
from .base import Base
from .consent import Consent
from .content import Persona, Rubric, RubricCriterion, Scenario
from .jobs import FailedJob
from .observability import DeploymentEvent, LatencyEvent, ModelCall
from .pre_label import PreLabel
from .scoring import Report, SessionScore
from .session import Session
from .shadow_score import ShadowScore
from .training import DatasetMember, DatasetRevision, EvalRun, ModelVersion
from .turn import Turn, TurnMetrics, TurnScore
from .user import Profile, ProviderCredential, User

__all__ = [
    "Annotation",
    "Base",
    "Consent",
    "DatasetMember",
    "DatasetRevision",
    "DeploymentEvent",
    "EvalRun",
    "FailedJob",
    "LatencyEvent",
    "ModelCall",
    "ModelVersion",
    "Persona",
    "PreLabel",
    "Profile",
    "ProviderCredential",
    "Report",
    "Rubric",
    "RubricCriterion",
    "Scenario",
    "Session",
    "SessionScore",
    "ShadowScore",
    "Turn",
    "TurnMetrics",
    "TurnScore",
    "User",
]
