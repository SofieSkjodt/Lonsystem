from database.models import MasterAgreementKind
from database.session import _seed_agreement_kinds


def test_seed_creates_the_two_system_kinds(db):
    _seed_agreement_kinds(db)

    rows = db.query(MasterAgreementKind).order_by(MasterAgreementKind.sort_order).all()
    assert [r.key for r in rows] == ["hourly_fixed", "hourly_flexible"]
    assert all(r.is_user_created is False for r in rows)
    assert all(r.requires_agreement_type is True for r in rows)
    assert all(r.is_active is True for r in rows)


def test_seed_is_idempotent(db):
    _seed_agreement_kinds(db)
    _seed_agreement_kinds(db)

    count = db.query(MasterAgreementKind).count()
    assert count == 2
