"""The five detectors of build plan §7. Each one scores a subject (0-100, with reasons), says
which subject a flag goes on, and says how to compare itself with the Phase 1 rules on
labelled cases. None of them can reject, ban or hold money: at most they raise a flag."""

import math
import re
import statistics
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import DomainError
from app.core.ghana import format_ghs, normalise_phone
from app.modules.accounts.models import User
from app.modules.areas.models import PriceBand
from app.modules.audit.log import subject_key
from app.modules.enquiries.models import Message
from app.modules.listings.models import Listing, ListingStatus
from app.modules.media.images import hamming
from app.modules.media.storage import storage
from app.modules.risk.models import RiskFlag
from app.modules.units.models import AuthorityRecord, Unit
from app.modules.verification.models import FieldVisit, VisitPhoto

from .documents import tamper_score
from .models import DetectionLabel, LinkEdge, ModelScore, ModelVersion
from .text import ClaudeTextModel, get_text_model


@dataclass(frozen=True)
class Scored:
    score: int
    reasons: list[str]
    version: str


def _sigmoid(x: float) -> float:
    return 1 / (1 + math.exp(-max(min(x, 30), -30)))


class Detector:
    name = ""
    label = ""
    subject_types: dict[str, type] = {}
    # Evaluation: which labelled subjects count, and which rule flags are the baseline to beat.
    rule_prefixes: dict[str, tuple[str, ...]] = {}

    def load(self, db: Session, subject_type: str, subject_id: str):
        model = self.subject_types.get(subject_type)
        return db.get(model, int(subject_id)) if model else None

    def score(self, db: Session, subject) -> Scored:
        raise NotImplementedError

    def flag_subject(self, db: Session, subject):
        return subject

    @property
    def label_types(self) -> tuple[str, ...]:
        return tuple(self.rule_prefixes)

    def score_for_label(self, db: Session, lbl: DetectionLabel, version: str) -> int | None:
        return db.scalar(
            select(ModelScore.score)
            .where(
                ModelScore.detector == self.name,
                ModelScore.version == version,
                ModelScore.subject_type == lbl.subject_type,
                ModelScore.subject_id == lbl.subject_id,
                ModelScore.created_at <= lbl.created_at,
            )
            .order_by(ModelScore.id.desc())
        )

    def rule_hit_for_label(self, db: Session, lbl: DetectionLabel) -> bool:
        prefixes = self.rule_prefixes.get(lbl.subject_type, ())
        if not prefixes:
            return False
        flags = db.scalars(
            select(RiskFlag.rule).where(
                RiskFlag.subject_type == lbl.subject_type,
                RiskFlag.subject_id == lbl.subject_id,
                RiskFlag.created_at <= lbl.created_at,
            )
        )
        return any(rule.startswith(prefixes) for rule in flags)


# --- 1. Scam wording -----------------------------------------------------------------------------------


class ScamText(Detector):
    name = "scam_text"
    label = "Scam wording in listings and messages"
    subject_types = {"listings": Listing, "messages": Message}
    rule_prefixes = {"listings": ("language.",), "users": ("message.language.",)}

    def score(self, db, subject) -> Scored:
        newest = db.scalar(
            select(ModelVersion).where(ModelVersion.detector == self.name).order_by(ModelVersion.id.desc())
        )
        model = get_text_model((newest.version, newest.params) if newest else None)
        text = f"{subject.title}\n{subject.description}" if isinstance(subject, Listing) else subject.body
        result = model.score(text)
        return Scored(result.score, result.reasons, result.version)

    def flag_subject(self, db, subject):
        # Rules flag the lister who sent a scam message, so the model does the same.
        return subject.sender if isinstance(subject, Message) else subject

    def score_for_label(self, db, lbl, version):
        if lbl.subject_type != "users":
            return super().score_for_label(db, lbl, version)
        message_ids = [str(i) for i in db.scalars(select(Message.id).where(Message.sender_id == int(lbl.subject_id)))]
        if not message_ids:
            return None
        return db.scalar(
            select(func.max(ModelScore.score)).where(
                ModelScore.detector == self.name,
                ModelScore.version == version,
                ModelScore.subject_type == "messages",
                ModelScore.subject_id.in_(message_ids),
                ModelScore.created_at <= lbl.created_at,
            )
        )


class ScamTextLLM(ScamText):
    """The same job as ScamText, done by Claude on redacted text. It's a separate detector so it
    is scored and evaluated beside the in-house model instead of replacing it. Off until counsel
    clears sending redacted text abroad (B11); turning it on is a rule change two reviewers make."""

    name = "scam_text_llm"
    label = "Scam wording (Claude, redacted text)"

    def make_model(self):
        return ClaudeTextModel()

    def score(self, db, subject) -> Scored:
        text = f"{subject.title}\n{subject.description}" if isinstance(subject, Listing) else subject.body
        result = self.make_model().score(text)
        return Scored(result.score, result.reasons, result.version)


# --- 2. Price --------------------------------------------------------------------------------------------

MIN_COMPARABLES = 8


def reference_rent(db: Session, area_id: int, bedrooms: int, exclude_listing_id: int | None = None):
    """The usual rent for homes like this: the median of Afe's verified listings once there are
    enough, else the manual price survey. Returns (pesewas, where it came from, version), or None."""
    query = (
        select(Listing.rent_pesewas)
        .join(Listing.unit)
        .where(
            Unit.area_id == area_id,
            Unit.bedrooms == bedrooms,
            Listing.status.in_([ListingStatus.LIVE, ListingStatus.LET]),
        )
    )
    if exclude_listing_id is not None:
        query = query.where(Listing.id != exclude_listing_id)
    rents = list(db.scalars(query))
    if len(rents) >= MIN_COMPARABLES:
        return statistics.median(rents), f"{len(rents)} verified listings like it on Afe", "price-own-1"
    band = db.scalar(
        select(PriceBand)
        .where(PriceBand.area_id == area_id, PriceBand.bedrooms == bedrooms)
        .order_by(PriceBand.as_of.desc())
    )
    if band is None:
        return None
    return band.median_pesewas, "Afe's price survey", "price-band-1"


def score_rent(rent_pesewas: int, reference: float, source: str, version: str) -> Scored:
    position = rent_pesewas / reference
    score = round(_sigmoid(12 * (0.55 - position)) * 100)
    reasons = [
        f"Rent {format_ghs(rent_pesewas)} is {round(position * 100)}% of the usual "
        f"{format_ghs(round(reference))} ({source})"
    ]
    return Scored(score, reasons, version)


class Price(Detector):
    """How far below comparable homes the rent is. Uses Afe's own verified listings once an
    area has enough of them; until then, the manual price survey (build plan §7)."""

    name = "price"
    label = "Price far below the area"
    subject_types = {"listings": Listing}
    rule_prefixes = {"listings": ("price.",)}

    def score(self, db, listing) -> Scored:
        unit = listing.unit
        ref = reference_rent(db, unit.area_id, unit.bedrooms, exclude_listing_id=listing.id)
        if ref is None:
            return Scored(0, ["No price data for this area and size yet"], "price-band-1")
        return score_rent(listing.rent_pesewas, *ref)


# --- 3. Photos --------------------------------------------------------------------------------------------


class Photos(Detector):
    """Near matches between this home's visit photos and any other home's, on two hashes
    together (128 bits), so it catches cropped or re-coloured copies the one-hash rule misses."""

    name = "photos"
    label = "Photos matching another home"
    subject_types = {"units": Unit}
    rule_prefixes = {"units": ("photos.",)}

    def score(self, db, unit) -> Scored:
        mine = db.execute(
            select(VisitPhoto.id, VisitPhoto.phash, VisitPhoto.dhash).join(FieldVisit).where(FieldVisit.unit_id == unit.id)
        ).all()
        if not mine:
            return Scored(0, ["No visit photos yet"], "hash-pair-1")
        others = db.execute(
            select(VisitPhoto.phash, VisitPhoto.dhash, FieldVisit.unit_id).join(FieldVisit).where(FieldVisit.unit_id != unit.id)
        ).all()
        best, match_unit = 128, None
        for _, ph, dh in mine:
            for oph, odh, other_unit in others:
                d = hamming(ph, oph) + hamming(dh, odh)
                if d < best:
                    best, match_unit = d, other_unit
        score = round(_sigmoid((20 - best) / 2.5) * 100)
        reasons = [f"Closest photo of another home (#{match_unit}) differs by {best} of 128 bits"] if match_unit else []
        return Scored(score, reasons, "hash-pair-1")


# --- 4. Documents --------------------------------------------------------------------------------------------


class Documents(Detector):
    name = "documents"
    label = "Signs a document was edited"
    subject_types = {"authority_records": AuthorityRecord}
    rule_prefixes = {"authority_records": ("documents.",)}  # Phase 1 had no document rule: the baseline flags nothing

    def score(self, db, record) -> Scored:
        try:
            data = storage.read("private", record.document_key)
        except (FileNotFoundError, DomainError):
            return Scored(0, ["The document file is missing"], "tamper-1")
        score, reasons = tamper_score(data)
        return Scored(score, reasons, "tamper-1")

    def flag_subject(self, db, record):
        return record.unit  # reviewers see a home's flags on the home review page


# --- 5. Linked accounts --------------------------------------------------------------------------------------


def known_bad_users(db: Session) -> set[int]:
    """Accounts a person has already decided were fraudulent."""
    labelled = db.scalars(
        select(DetectionLabel.subject_id).where(DetectionLabel.subject_type == "users", DetectionLabel.outcome == "fraud")
    )
    confirmed = db.scalars(
        select(RiskFlag.subject_id).where(RiskFlag.subject_type == "users", RiskFlag.status == "confirmed")
    )
    return {int(i) for i in [*labelled, *confirmed]}


class Accounts(Detector):
    """Scores an account by what it shares with accounts already found to be fraudulent:
    the same Ghana Card, payout account, photos, or phone number handed out in messages."""

    name = "accounts"
    label = "Accounts linked to known fraud"
    subject_types = {"users": User}
    rule_prefixes = {"users": ("identity.duplicate",)}

    def score(self, db, user) -> Scored:
        edges = db.execute(
            select(LinkEdge.user_a_id, LinkEdge.user_b_id, LinkEdge.kind)
            .where((LinkEdge.user_a_id == user.id) | (LinkEdge.user_b_id == user.id))
        ).all()
        if not edges:
            return Scored(0, [], "graph-1")
        bad = known_bad_users(db) - {user.id}
        component = connected(db, user.id)
        direct = {b if a == user.id else a for a, b, _ in edges}
        kinds = sorted({k for *_, k in edges})
        clean = 1.0
        reasons = []
        for other in direct & bad:
            clean *= 0.4
            reasons.append(f"Shares details with account #{other}, already found to be fraudulent")
        indirect = (component & bad) - direct
        if indirect:
            clean *= 0.65
            reasons.append(f"In a group of {len(component)} linked accounts that includes known fraud")
        if "ghana_card" in kinds:
            clean *= 0.7
            reasons.append("The same Ghana Card is used on another account")
        if len(component) >= 4:
            clean *= 0.8
            reasons.append(f"Part of a group of {len(component)} linked accounts")
        reasons.append(f"Linked by: {', '.join(k.replace('_', ' ') for k in kinds)}")
        return Scored(round((1 - clean) * 100), reasons, "graph-1")


def connected(db: Session, user_id: int) -> set[int]:
    """Every account reachable from this one through link edges (including itself)."""
    pairs = db.execute(select(LinkEdge.user_a_id, LinkEdge.user_b_id)).all()
    neighbours: dict[int, set[int]] = {}
    for a, b in pairs:
        neighbours.setdefault(a, set()).add(b)
        neighbours.setdefault(b, set()).add(a)
    seen, todo = {user_id}, [user_id]
    while todo:
        for n in neighbours.get(todo.pop(), ()):
            if n not in seen:
                seen.add(n)
                todo.append(n)
    return seen


_PHONE_IN_TEXT = re.compile(r"(?:\+?233|0)\s?[2-5]\d(?:[\s-]?\d){7}")


def build_links(db: Session) -> int:
    """Rebuild link edges from scratch. Evidence names what is shared, never the raw value."""
    from app.modules.identity.models import IdentityCheck
    from app.modules.tenancies.models import Payee

    db.query(LinkEdge).delete()
    found: set[tuple[int, int, str, str]] = set()

    def link(a: int, b: int, kind: str, evidence: str) -> None:
        if a != b:
            lo, hi = sorted((a, b))
            found.add((lo, hi, kind, evidence[:80]))

    def group(rows, kind, evidence):
        by_value: dict[str, set[int]] = {}
        for value, user_id in rows:
            by_value.setdefault(value, set()).add(user_id)
        for value, users in by_value.items():
            users = sorted(users)
            for i, a in enumerate(users):
                for b in users[i + 1 :]:
                    link(a, b, kind, evidence(value))

    group(db.execute(select(IdentityCheck.card_number_hash, IdentityCheck.user_id)).all(),
          "ghana_card", lambda v: f"Ghana Card ref {v[:8]}")
    group(db.execute(select(Payee.account_number, Payee.user_id)).all(),
          "payout_account", lambda v: f"Payout account ending {v[-4:]}")
    photo_owners = (
        select(VisitPhoto.phash, Unit.registered_by_id)
        .select_from(VisitPhoto)
        .join(FieldVisit, VisitPhoto.visit_id == FieldVisit.id)
        .join(Unit, FieldVisit.unit_id == Unit.id)
    )
    group(db.execute(photo_owners).all(),
          "photo", lambda v: f"Photo hash {v[:8]}")

    from app.modules.accounts.models import LISTER_ROLES, RefreshToken, Role

    # Devices: only between the public's accounts. Staff sign in on shared office devices.
    public_roles = [str(r) for r in (*LISTER_ROLES, Role.RENTER)]
    group(db.execute(
        select(RefreshToken.device_id, RefreshToken.user_id)
        .join(User, User.id == RefreshToken.user_id)
        .where(RefreshToken.device_id != "", User.role.in_(public_roles))
        .distinct()
    ).all(), "device", lambda v: f"Device ref {v[:8]}")

    phones = {u.phone: u.id for u in db.scalars(select(User).where(User.phone.is_not(None)))}
    for sender_id, body in db.execute(select(Message.sender_id, Message.body).where(Message.sender_id.is_not(None))):
        for raw in _PHONE_IN_TEXT.findall(body):
            try:
                phone = normalise_phone(raw)
            except DomainError:
                continue
            owner = phones.get(phone)
            if owner and owner != sender_id:
                link(sender_id, owner, "phone_in_message", f"Phone ending {phone[-4:]} sent in a message")

    for a, b, kind, evidence in sorted(found):
        db.add(LinkEdge(user_a_id=a, user_b_id=b, kind=kind, evidence=evidence))
    db.flush()
    return len(found)


REGISTRY: dict[str, Detector] = {
    d.name: d for d in (ScamText(), ScamTextLLM(), Price(), Photos(), Documents(), Accounts())
}


def detector_for(name: str) -> Detector:
    return REGISTRY[name]


__all__ = ["REGISTRY", "Scored", "build_links", "connected", "detector_for", "known_bad_users", "subject_key"]
