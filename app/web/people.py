"""Admin web routes for People management."""

from __future__ import annotations

import logging
from urllib.parse import quote_plus
from uuid import UUID

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.models.person import Person
from app.schemas.person import PersonCreate, PersonUpdate
from app.services.branding_context import load_branding_context
from app.services.person import people
from app.templates import templates
from app.web.schoolnet_deps import require_platform_admin_auth

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/people", tags=["web-people"])

PAGE_SIZE = 25


def _base_context(
    request: Request,
    db: Session,
    auth: dict,
    *,
    title: str,
    page_title: str,
) -> dict:
    branding = load_branding_context(db)
    person = auth["person"]
    return {
        "request": request,
        "title": title,
        "page_title": page_title,
        "current_user": person,
        "brand": branding["brand"],
        "org_branding": branding["org_branding"],
        "brand_mark": branding["brand"].get("mark", "A"),
    }


@router.get("", response_class=HTMLResponse)
def list_people(
    request: Request,
    page: int = 1,
    email: str | None = None,
    db: Session = Depends(get_db),
    auth: dict = Depends(require_platform_admin_auth),
) -> HTMLResponse:
    """List people with pagination and optional email search."""
    page = max(1, page)
    offset = (page - 1) * PAGE_SIZE

    query = select(Person).order_by(Person.created_at.desc())
    if email:
        query = query.where(Person.email.ilike(f"%{email}%"))

    total = (
        db.scalar(select(func.count()).select_from(query.order_by(None).subquery()))
        or 0
    )
    items = list(db.scalars(query.limit(PAGE_SIZE).offset(offset)).all())
    total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)

    ctx = _base_context(request, db, auth, title="People", page_title="People")
    ctx.update(
        {
            "people": items,
            "total": total,
            "page": page,
            "total_pages": total_pages,
            "email_filter": email or "",
            "success": request.query_params.get("success"),
            "error": request.query_params.get("error"),
        }
    )
    return templates.TemplateResponse("admin/people/list.html", ctx)


@router.get("/create", response_class=HTMLResponse)
def create_person_form(
    request: Request,
    db: Session = Depends(get_db),
    auth: dict = Depends(require_platform_admin_auth),
) -> HTMLResponse:
    """Render the create person form."""
    ctx = _base_context(
        request, db, auth, title="Create Person", page_title="Create Person"
    )
    return templates.TemplateResponse("admin/people/create.html", ctx)


@router.post("/create", response_model=None)
def create_person_submit(
    request: Request,
    first_name: str = Form(""),
    last_name: str = Form(""),
    email: str = Form(""),
    display_name: str | None = Form(None),
    phone: str | None = Form(None),
    status: str = Form("active"),
    is_active: str | None = Form(None),
    csrf_token: str | None = Form(None),
    db: Session = Depends(get_db),
    auth: dict = Depends(require_platform_admin_auth),
) -> RedirectResponse | HTMLResponse:
    """Handle person creation form submission."""
    _ = csrf_token
    data = {
        "first_name": first_name,
        "last_name": last_name,
        "email": email,
        "display_name": display_name,
        "phone": phone,
        "status": status,
        "is_active": is_active,
    }

    try:
        payload = PersonCreate(
            first_name=first_name,
            last_name=last_name,
            email=email,
            display_name=display_name if display_name else None,
            phone=phone if phone else None,
            status=status,
            is_active=is_active == "on",
        )
        people.create(db, payload)
        db.commit()
        logger.info("Created person via web: %s", payload.email)
        return RedirectResponse(
            url="/admin/people?success=Person+created+successfully",
            status_code=302,
        )
    except (ValueError, TypeError, KeyError) as exc:
        db.rollback()
        logger.warning("Failed to create person: %s", exc)
        ctx = _base_context(
            request, db, auth, title="Create Person", page_title="Create Person"
        )
        ctx["error"] = str(exc)
        ctx["form_data"] = data
        return templates.TemplateResponse("admin/people/create.html", ctx)


@router.get("/{person_id}", response_class=HTMLResponse)
def person_detail(
    request: Request,
    person_id: UUID,
    db: Session = Depends(get_db),
    auth: dict = Depends(require_platform_admin_auth),
) -> HTMLResponse:
    """Show person detail view."""
    person = people.get(db, str(person_id))
    ctx = _base_context(
        request,
        db,
        auth,
        title=f"{person.first_name} {person.last_name}",
        page_title="Person Detail",
    )
    ctx["person"] = person
    return templates.TemplateResponse("admin/people/detail.html", ctx)


@router.get("/{person_id}/edit", response_class=HTMLResponse)
def edit_person_form(
    request: Request,
    person_id: UUID,
    db: Session = Depends(get_db),
    auth: dict = Depends(require_platform_admin_auth),
) -> HTMLResponse:
    """Render the edit person form."""
    person = people.get(db, str(person_id))
    ctx = _base_context(
        request, db, auth, title="Edit Person", page_title="Edit Person"
    )
    ctx["person"] = person
    return templates.TemplateResponse("admin/people/edit.html", ctx)


@router.post("/{person_id}/edit", response_model=None)
def edit_person_submit(
    request: Request,
    person_id: UUID,
    first_name: str | None = Form(None),
    last_name: str | None = Form(None),
    email: str | None = Form(None),
    display_name: str | None = Form(None),
    phone: str | None = Form(None),
    status: str | None = Form(None),
    is_active: str | None = Form(None),
    csrf_token: str | None = Form(None),
    db: Session = Depends(get_db),
    auth: dict = Depends(require_platform_admin_auth),
) -> RedirectResponse | HTMLResponse:
    """Handle person edit form submission."""
    _ = csrf_token
    data = {
        "first_name": first_name,
        "last_name": last_name,
        "email": email,
        "display_name": display_name,
        "phone": phone,
        "status": status,
        "is_active": is_active,
    }

    try:
        payload = PersonUpdate(
            first_name=first_name if first_name else None,
            last_name=last_name if last_name else None,
            email=email if email else None,
            display_name=display_name if display_name else None,
            phone=phone if phone else None,
            status=status if status else None,
            is_active=is_active == "on",
        )
        people.update(db, str(person_id), payload)
        db.commit()
        logger.info("Updated person via web: %s", person_id)
        return RedirectResponse(
            url=f"/admin/people/{person_id}?success=Person+updated+successfully",
            status_code=302,
        )
    except (ValueError, TypeError, KeyError) as exc:
        db.rollback()
        logger.warning("Failed to update person %s: %s", person_id, exc)
        person = db.get(Person, person_id)
        ctx = _base_context(
            request, db, auth, title="Edit Person", page_title="Edit Person"
        )
        ctx["person"] = person
        ctx["error"] = str(exc)
        return templates.TemplateResponse("admin/people/edit.html", ctx)


@router.post("/{person_id}/delete", response_model=None)
def delete_person(
    request: Request,
    person_id: UUID,
    csrf_token: str | None = Form(None),
    db: Session = Depends(get_db),
    auth: dict = Depends(require_platform_admin_auth),
) -> RedirectResponse:
    """Handle person deletion."""
    _ = csrf_token

    try:
        people.delete(db, str(person_id))
        db.commit()
        logger.info("Deleted person via web: %s", person_id)
        return RedirectResponse(
            url="/admin/people?success=Person+deleted+successfully",
            status_code=302,
        )
    except (ValueError, TypeError, KeyError) as exc:
        db.rollback()
        logger.warning("Failed to delete person %s: %s", person_id, exc)
        return RedirectResponse(
            url=f"/admin/people?error={quote_plus(str(exc))}",
            status_code=302,
        )
