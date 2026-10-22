from sqlalchemy.orm import Session

from app.core.errors import InvalidInput

from .models import EVENT_NAMES, AnalyticsEvent

MAX_PROPS = 20


def track(db: Session, name: str, user=None, anonymous_id: str = "", path: str = "", props: dict | None = None) -> None:
    if name not in EVENT_NAMES:
        raise InvalidInput(f"Unknown event: {name}")
    props = dict(list((props or {}).items())[:MAX_PROPS])
    # Keep only simple values; never personal data.
    clean = {str(k)[:40]: v for k, v in props.items() if isinstance(v, (str, int, float, bool)) and len(str(v)) <= 200}
    db.add(
        AnalyticsEvent(
            name=name, user_id=getattr(user, "id", None), anonymous_id=anonymous_id[:64], path=path[:300], props=clean
        )
    )
    db.flush()
