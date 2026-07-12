"""Resume / CV: schema, extraction hints, deterministic validators."""
from typing import Optional

from pydantic import BaseModel

from .base import (
    DocTypeSpec,
    ValidationIssue,
    check_email,
    check_phone,
    issue,
    parse_date,
    require_fields,
)


class ExperienceEntry(BaseModel):
    company: Optional[str] = None
    title: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None  # null when it's the current role
    description: Optional[str] = None


class EducationEntry(BaseModel):
    institution: Optional[str] = None
    degree: Optional[str] = None
    field_of_study: Optional[str] = None
    end_year: Optional[str] = None


class Resume(BaseModel):
    full_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    location: Optional[str] = None
    summary: Optional[str] = None
    skills: list[str] = []
    experience: list[ExperienceEntry] = []
    education: list[EducationEntry] = []
    links: list[str] = []


def _check_experience_ranges(data: dict) -> list[ValidationIssue]:
    out = []
    for i, entry in enumerate(data.get("experience") or []):
        if not isinstance(entry, dict):
            continue
        start = parse_date(entry.get("start_date"))
        end = parse_date(entry.get("end_date"))
        if start and end and end < start:
            label = entry.get("company") or f"entry {i + 1}"
            out.append(issue(f"experience[{i}]", "date_order", "warning",
                             f"Experience at {label} ends before it starts."))
    return out


SPEC = DocTypeSpec(
    name="resume",
    display_name="Resume",
    description=(
        "A candidate's curriculum vitae: personal details, professional summary, "
        "skills, work experience history and education."
    ),
    schema=Resume,
    extraction_hints=(
        "Dates may be partial (e.g. '2021' or 'Mar 2021'); keep them as written "
        "but prefer YYYY-MM-DD when the full date is given. Use null end_date "
        "for a current role ('Present'). 'skills' is a flat list of individual "
        "skill names."
    ),
    validators=[
        require_fields(["full_name"]),
        require_fields(["email"], severity="warning"),
        check_email("email"),
        check_phone("phone"),
        _check_experience_ranges,
    ],
)
