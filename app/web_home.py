from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.db import SessionLocal
from app.services import person as person_service
from app.services.branding import (
    generate_css,
    get_branding,
    google_fonts_url,
    save_branding,
)
from app.services.branding_assets import delete_branding_asset, save_branding_asset
from app.templates import templates

router = APIRouter()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _brand_mark(name: str) -> str:
    parts = [part for part in name.split() if part]
    if not parts:
        return "ST"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[1][0]).upper()


@router.get("/", tags=["web"], response_class=HTMLResponse)
def home(
    request: Request,
    sort: str = "created_at",
    dir: str = "desc",
    page: int = 1,
    db: Session = Depends(get_db),
):
    page = max(page, 1)
    order_by = sort if sort in {"created_at", "last_name", "email"} else "created_at"
    order_dir = dir if dir in {"asc", "desc"} else "desc"
    limit = 25
    offset = (page - 1) * limit

    people = person_service.people.list(
        db=db,
        email=None,
        status=None,
        is_active=None,
        order_by=order_by,
        order_dir=order_dir,
        limit=limit,
        offset=offset,
    )
    total_people = db.query(person_service.Person).count()
    total_pages = max(1, (total_people + limit - 1) // limit)

    branding = get_branding(db)
    brand_name = settings.brand_name
    brand = {
        "name": branding.get("display_name") or brand_name,
        "tagline": branding.get("tagline") or settings.brand_tagline,
        "logo_url": branding.get("logo_url") or settings.brand_logo_url,
        "logo_dark_url": branding.get("logo_dark_url"),
        "mark": branding.get("brand_mark") or _brand_mark(brand_name),
    }
    org_branding = {
        "css": generate_css(branding),
        "fonts_url": google_fonts_url(branding),
    }
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "title": brand_name,
            "people": people,
            "brand": brand,
            "org_branding": org_branding,
            "sort": order_by,
            "dir": order_dir,
            "page": page,
            "total_pages": total_pages,
            "total_people": total_people,
        },
    )


@router.get("/settings/branding", tags=["web"], response_class=HTMLResponse)
def branding_settings(request: Request, db: Session = Depends(get_db)):
    branding = get_branding(db)
    brand = {
        "name": branding.get("display_name") or settings.brand_name,
        "tagline": branding.get("tagline") or settings.brand_tagline,
        "logo_url": branding.get("logo_url") or settings.brand_logo_url,
        "logo_dark_url": branding.get("logo_dark_url"),
        "mark": branding.get("brand_mark") or _brand_mark(settings.brand_name),
    }
    return templates.TemplateResponse(
        "branding.html",
        {
            "request": request,
            "title": "Branding Settings",
            "branding": branding,
            "brand": brand,
            "org_branding": {
                "css": generate_css(branding),
                "fonts_url": google_fonts_url(branding),
            },
        },
    )


@router.post("/settings/branding", tags=["web"], response_class=HTMLResponse)
async def branding_settings_update(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    data = dict(form)
    branding = get_branding(db)

    logo_file = form.get("logo_file")
    logo_dark_file = form.get("logo_dark_file")
    if getattr(logo_file, "filename", None):
        new_logo = await save_branding_asset(logo_file, "logo")
        old_logo = branding.get("logo_url")
        data["logo_url"] = new_logo
        if old_logo and old_logo != new_logo:
            delete_branding_asset(old_logo)
    elif str(form.get("remove_logo") or "").lower() in {"1", "true", "on", "yes"}:
        delete_branding_asset(branding.get("logo_url"))
        data["logo_url"] = None

    if getattr(logo_dark_file, "filename", None):
        new_logo_dark = await save_branding_asset(logo_dark_file, "logo_dark")
        old_logo_dark = branding.get("logo_dark_url")
        data["logo_dark_url"] = new_logo_dark
        if old_logo_dark and old_logo_dark != new_logo_dark:
            delete_branding_asset(old_logo_dark)
    elif str(form.get("remove_logo_dark") or "").lower() in {
        "1",
        "true",
        "on",
        "yes",
    }:
        delete_branding_asset(branding.get("logo_dark_url"))
        data["logo_dark_url"] = None

    payload = {
        "display_name": data.get("display_name"),
        "tagline": data.get("tagline"),
        "brand_mark": data.get("brand_mark"),
        "primary_color": data.get("primary_color"),
        "accent_color": data.get("accent_color"),
        "font_family_display": data.get("font_family_display"),
        "font_family_body": data.get("font_family_body"),
        "custom_css": data.get("custom_css"),
        "logo_url": data.get("logo_url", branding.get("logo_url")),
        "logo_dark_url": data.get("logo_dark_url", branding.get("logo_dark_url")),
    }
    saved = save_branding(db, payload)
    brand = {
        "name": saved.get("display_name") or settings.brand_name,
        "tagline": saved.get("tagline") or settings.brand_tagline,
        "logo_url": saved.get("logo_url") or settings.brand_logo_url,
        "logo_dark_url": saved.get("logo_dark_url"),
        "mark": saved.get("brand_mark") or _brand_mark(settings.brand_name),
    }
    return templates.TemplateResponse(
        "branding.html",
        {
            "request": request,
            "title": "Branding Settings",
            "branding": saved,
            "brand": brand,
            "success": True,
            "org_branding": {
                "css": generate_css(saved),
                "fonts_url": google_fonts_url(saved),
            },
        },
    )
