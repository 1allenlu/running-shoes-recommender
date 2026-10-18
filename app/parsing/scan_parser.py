"""Fleet Feet / Volumental report (screenshots or PDF) -> FootProfile, via a vision LLM.

uv run python -m app.parsing.scan_parser report.pdf [more screenshots...]
"""

import base64
import mimetypes
import shutil
import sys
import uuid
from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import Runnable
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import Scan
from app.parsing.prompts import SCAN_PARSER_INSTRUCTION, SCAN_PARSER_SYSTEM
from app.schemas.foot_profile import FootProfile

# Bump when the prompt, schema or model changes, so stored scans show which parser read them.
PARSER_VERSION = "scan-parser-v1"

IMAGE_TYPES = {"image/png", "image/jpeg", "image/webp", "image/gif"}
PDF_TYPE = "application/pdf"


def content_block(path: Path) -> dict:
    """LangChain standard content block for one report file."""
    mime_type, _ = mimetypes.guess_type(path.name)
    if mime_type not in IMAGE_TYPES | {PDF_TYPE}:
        raise ValueError(f"{path.name}: unsupported file type {mime_type}; use PNG, JPEG or PDF")
    data = base64.standard_b64encode(path.read_bytes()).decode()
    block_type = "file" if mime_type == PDF_TYPE else "image"
    return {"type": block_type, "base64": data, "mime_type": mime_type}


def build_messages(paths: list[Path]) -> list:
    if not paths:
        raise ValueError("no report files given")
    content = [content_block(p) for p in paths] + [
        {"type": "text", "text": SCAN_PARSER_INSTRUCTION}
    ]
    return [SystemMessage(SCAN_PARSER_SYSTEM), HumanMessage(content=content)]


def build_parser() -> Runnable:
    """Vision LLM bound to the FootProfile schema."""
    from langchain_anthropic import ChatAnthropic

    settings = get_settings()
    llm = ChatAnthropic(
        model=settings.llm_model,
        api_key=settings.anthropic_api_key,
        max_tokens=16000,
    )
    # json_schema uses Claude's native structured outputs; the default (forced tool call)
    # is rejected by current models.
    return llm.with_structured_output(FootProfile, method="json_schema")


def parse_scan(paths: list[Path], parser: Runnable | None = None) -> FootProfile:
    parser = parser or build_parser()
    return parser.invoke(build_messages(paths), config={"run_name": "parse_scan"})


def save_scan(
    session: Session, user_id: uuid.UUID, paths: list[Path], profile: FootProfile
) -> Scan:
    """Copy the raw report files into the upload dir and record the parse in `scans`."""
    scan_dir = Path(get_settings().upload_dir) / str(user_id) / uuid.uuid4().hex
    scan_dir.mkdir(parents=True)
    for i, path in enumerate(paths):
        shutil.copyfile(path, scan_dir / f"{i:02d}_{path.name}")

    scan = Scan(
        user_id=user_id,
        raw_file_path=str(scan_dir),
        parsed_profile=profile.model_dump(mode="json"),
        parser_version=PARSER_VERSION,
    )
    session.add(scan)
    session.commit()
    return scan


def main() -> None:
    from app.config import configure_langsmith

    configure_langsmith()
    profile = parse_scan([Path(p) for p in sys.argv[1:]])
    print(profile.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
