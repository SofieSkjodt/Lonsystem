from database.models import AppUser, Employee, MasterAgreementKind
from routers.stamdata import (
    AgreementKindBody,
    list_agreement_kinds,
    create_agreement_kind,
    update_agreement_kind,
    delete_agreement_kind,
)
from datetime import date


def _dummy_user():
    return AppUser(name="Test", initials="TST", role="admin", password_hash="x")


def _seed_two_system_kinds(db):
    db.add(MasterAgreementKind(
        key="hourly_fixed", label="Timelønnet, fast arbejdstid",
        is_active=True, is_user_created=False,
        requires_agreement_type=True, sort_order=1,
    ))
    db.add(MasterAgreementKind(
        key="hourly_flexible", label="Timelønnet, ikke fastlagt arbejdstid",
        is_active=True, is_user_created=False,
        requires_agreement_type=True, sort_order=2,
    ))
    db.commit()


def test_list_returns_seeded_kinds_in_sort_order(db):
    _seed_two_system_kinds(db)
    rows = list_agreement_kinds(current_user=_dummy_user(), db=db)
    assert [r["key"] for r in rows] == ["hourly_fixed", "hourly_flexible"]


def test_create_new_agreement_kind(db):
    _seed_two_system_kinds(db)
    body = AgreementKindBody(label="Månedslønnet", requires_agreement_type=False)
    result = create_agreement_kind(body, current_user=_dummy_user(), db=db)
    assert result["key"] == "maanedsloennet"
    assert result["is_user_created"] is True
    assert result["requires_agreement_type"] is False


def test_create_without_label_fails(db):
    _seed_two_system_kinds(db)
    body = AgreementKindBody(label=None)
    try:
        create_agreement_kind(body, current_user=_dummy_user(), db=db)
        assert False, "skulle have fejlet"
    except Exception as e:
        assert "påkrævet" in str(e).lower() or "400" in str(e)


def test_create_duplicate_label_fails(db):
    _seed_two_system_kinds(db)
    create_agreement_kind(AgreementKindBody(label="Vikar"), current_user=_dummy_user(), db=db)
    try:
        create_agreement_kind(AgreementKindBody(label="Vikar"), current_user=_dummy_user(), db=db)
        assert False, "skulle have fejlet på duplikeret nøgle"
    except Exception:
        pass


def test_update_can_change_label_but_not_key(db):
    _seed_two_system_kinds(db)
    created = create_agreement_kind(
        AgreementKindBody(label="Vikar"), current_user=_dummy_user(), db=db
    )
    updated = update_agreement_kind(
        created["id"], AgreementKindBody(label="Vikar (ny tekst)"),
        current_user=_dummy_user(), db=db,
    )
    assert updated["label"] == "Vikar (ny tekst)"
    assert updated["key"] == created["key"]


def test_delete_system_kind_is_blocked(db):
    _seed_two_system_kinds(db)
    fixed = db.query(MasterAgreementKind).filter(MasterAgreementKind.key == "hourly_fixed").first()
    try:
        delete_agreement_kind(fixed.id, current_user=_dummy_user(), db=db)
        assert False, "skulle have fejlet – systemtype"
    except Exception as e:
        assert "400" in str(e) or "system" in str(e).lower()


def test_delete_user_created_kind_in_use_is_blocked(db):
    _seed_two_system_kinds(db)
    created = create_agreement_kind(
        AgreementKindBody(label="Vikar"), current_user=_dummy_user(), db=db
    )
    emp = Employee(
        employee_number="9003", first_name="Brug", last_name="Er",
        agreement_kind=created["key"], agreement_type="",
        hire_date=date(2026, 1, 1),
    )
    db.add(emp)
    db.commit()
    try:
        delete_agreement_kind(created["id"], current_user=_dummy_user(), db=db)
        assert False, "skulle have fejlet – i brug"
    except Exception as e:
        assert "400" in str(e) or "brug" in str(e).lower()


def test_delete_unused_user_created_kind_succeeds(db):
    _seed_two_system_kinds(db)
    created = create_agreement_kind(
        AgreementKindBody(label="Vikar"), current_user=_dummy_user(), db=db
    )
    delete_agreement_kind(created["id"], current_user=_dummy_user(), db=db)
    assert db.query(MasterAgreementKind).filter(MasterAgreementKind.id == created["id"]).first() is None
