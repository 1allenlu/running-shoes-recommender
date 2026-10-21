import json
from pathlib import Path

import pytest
from langchain_core.runnables import RunnableLambda
from pydantic import ValidationError
from sqlalchemy import select

from app.config import get_settings
from app.db.models import Scan, User
from app.llm import llm_ready
from app.parsing.compare import profile_mismatches
from app.parsing.scan_parser import PARSER_VERSION, build_messages, parse_scan, save_scan
from app.schemas.foot_profile import FootProfile

SAMPLE_DIR = Path("data/sample_scans")
TEMPLATE = SAMPLE_DIR / "expected.template.json"
REPORT_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".pdf"}


@pytest.fixture
def profile() -> FootProfile:
    return FootProfile.model_validate_json(TEMPLATE.read_text())


@pytest.fixture
def report_files(tmp_path) -> list[Path]:
    png, pdf = tmp_path / "page1.png", tmp_path / "report.pdf"
    png.write_bytes(b"\x89PNG fake")
    pdf.write_bytes(b"%PDF-1.4 fake")
    return [png, pdf]


def test_template_matches_schema(profile):
    assert profile.left.pressure.band == "centered"
    assert profile.longer_foot is profile.right  # 8.3 > 8.1


def test_pressure_plate_fields_optional(profile):
    data = profile.model_dump()
    del data["left"]["pressure"], data["left"]["arch_flexibility"]
    assert FootProfile.model_validate(data).left.pressure is None


def test_rejects_position_outside_scale(profile):
    data = profile.model_dump()
    data["left"]["arch_height"]["position"] = 1.4
    with pytest.raises(ValidationError):
        FootProfile.model_validate(data)


def test_messages_carry_images_and_pdf(report_files):
    system, human = build_messages(report_files, pdf_as_images=False)
    assert "ABOVE" in system.content and "BELOW" in system.content
    types = [(b["type"], b.get("mime_type")) for b in human.content]
    assert types == [("image", "image/png"), ("file", "application/pdf"), ("text", None)]


def test_pdf_pages_become_images_for_local_models(tmp_path):
    from PIL import Image

    pdf = tmp_path / "report.pdf"
    pages = [Image.new("RGB", (200, 100), c) for c in ("white", "gray")]
    pages[0].save(pdf, save_all=True, append_images=pages[1:])

    _, human = build_messages([pdf], pdf_as_images=True)
    assert [(b["type"], b.get("mime_type")) for b in human.content] == [
        ("image", "image/png"),
        ("image", "image/png"),
        ("text", None),
    ]
    _, human = build_messages([pdf], pdf_as_images=False)
    assert human.content[0]["type"] == "file"


def test_rejects_unsupported_files(tmp_path):
    doc = tmp_path / "report.docx"
    doc.write_bytes(b"x")
    with pytest.raises(ValueError, match="unsupported"):
        build_messages([doc])


def test_parse_scan_uses_given_parser(report_files, profile):
    seen = []
    fake = RunnableLambda(lambda messages: seen.append(messages) or profile)
    assert parse_scan(report_files, parser=fake) == profile
    assert len(seen) == 1


def test_mismatches(profile):
    assert profile_mismatches(profile, profile) == []
    off = profile.model_copy(deep=True)
    off.left.us_size = 8.0
    off.right.heel_width.position = 0.62 + 0.2
    off.right.pressure = None
    assert profile_mismatches(profile, off) == [
        "left.us_size: expected 8.1, got 8.0",
        "right.heel_width.position: expected 0.62, got 0.82",
        "right.pressure: expected medial@0.15, got missing",
    ]
    off = profile.model_copy(deep=True)
    off.right.heel_width.position = 0.62 + 0.1
    assert profile_mismatches(profile, off) == []


@pytest.mark.db
def test_save_scan(db_session, report_files, profile, tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "upload_dir", str(tmp_path / "uploads"))
    user = User()
    db_session.add(user)
    db_session.commit()

    scan = save_scan(db_session, user.id, report_files, profile)
    stored = db_session.scalar(select(Scan).where(Scan.id == scan.id))
    assert stored.parser_version == PARSER_VERSION
    assert FootProfile.model_validate(stored.parsed_profile) == profile
    saved = sorted(p.name for p in Path(stored.raw_file_path).iterdir())
    assert saved == ["00_page1.png", "01_report.pdf"]


def sample_scans() -> list[Path]:
    if not SAMPLE_DIR.exists():
        return []
    return sorted(d for d in SAMPLE_DIR.iterdir() if (d / "expected.json").exists())


@pytest.mark.llm
@pytest.mark.parametrize("scan_dir", sample_scans(), ids=lambda d: d.name)
def test_parser_matches_hand_checked_profile(scan_dir):
    ready, reason = llm_ready()
    if not ready:
        pytest.skip(reason)
    files = sorted(p for p in scan_dir.iterdir() if p.suffix.lower() in REPORT_SUFFIXES)
    expected = FootProfile.model_validate(json.loads((scan_dir / "expected.json").read_text()))
    assert profile_mismatches(expected, parse_scan(files)) == []
