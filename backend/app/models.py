"""Import every model so SQLAlchemy's metadata (and Alembic autogenerate) sees all tables."""

from app.modules.accounts.models import OtpChallenge, RateEvent, RefreshToken, User  # noqa: F401
from app.modules.agents.models import AgentRun  # noqa: F401
from app.modules.alerts.models import AlertSent, SavedSearch  # noqa: F401
from app.modules.analytics.models import AnalyticsEvent  # noqa: F401
from app.modules.areas.models import PriceBand, ServiceArea  # noqa: F401
from app.modules.audit.models import AuditEvent, WebhookReceipt  # noqa: F401
from app.modules.billing.models import Payment  # noqa: F401
from app.modules.compliance.models import ComplianceRule  # noqa: F401
from app.modules.detection.models import (  # noqa: F401
    DetectionLabel,
    EvaluationSnapshot,
    LinkEdge,
    ModelScore,
    ModelVersion,
    ScoreJob,
)
from app.modules.enquiries.models import Message, SavedListing, Thread, Viewing, ViewingOutcome  # noqa: F401
from app.modules.identity.models import IdentityCheck  # noqa: F401
from app.modules.listings.models import (
    FeaturedPlacement,  # noqa: F401
    Listing,  # noqa: F401
)
from app.modules.notifications.models import Notification  # noqa: F401
from app.modules.ops.models import Appeal, ExternalPhoto, LabelCheck  # noqa: F401
from app.modules.rentals.models import Agreement, Maintenance, Renewal, Rental, RentPayment, Subscription  # noqa: F401
from app.modules.reviews.models import Review  # noqa: F401
from app.modules.risk.models import RiskFlag  # noqa: F401
from app.modules.scamcheck.models import FraudReport, Lookup  # noqa: F401
from app.modules.tenancies.models import Dispute, LedgerEntry, OutboxEvent, Payee, Tenancy  # noqa: F401
from app.modules.units.models import AuthorityRecord, Unit  # noqa: F401
from app.modules.verification.models import FieldVisit, Verification, VisitAssignment, VisitPhoto  # noqa: F401
