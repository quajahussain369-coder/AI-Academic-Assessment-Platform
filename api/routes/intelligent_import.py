from pathlib import Path
from tempfile import NamedTemporaryFile

from fastapi import APIRouter, File, HTTPException, UploadFile

from assessment_engine.config import load_config
from assessment_engine.intelligent_import import validate_workbook_file


router = APIRouter(
    prefix="/api/v2.4/intelligent-import",
    tags=["V2.4 Intelligent Import"],
)

BASE_DIR = Path(__file__).resolve().parents[2]
CONFIG_PATH = BASE_DIR / "configs" / "college.json"


@router.post("/preview")
async def intelligent_import_preview(
    file: UploadFile = File(...),
):
    """
    Preview an academic workbook through the complete V2.4 pipeline.

    Pipeline:
        Inspector → Detector → Normalizer → Validator

    This endpoint does not write academic data to storage.
    """

    if not file.filename:
        raise HTTPException(
            status_code=400,
            detail="No file was provided.",
        )

    suffix = Path(file.filename).suffix.lower()

    if suffix not in {".xlsx", ".xlsm"}:
        raise HTTPException(
            status_code=400,
            detail="Please upload an Excel .xlsx or .xlsm file.",
        )

    contents = await file.read()

    with NamedTemporaryFile(
        suffix=suffix,
        delete=False,
    ) as temporary:
        temporary.write(contents)
        temporary_path = Path(temporary.name)

    try:
        config = load_config(CONFIG_PATH)

        validation = validate_workbook_file(
            temporary_path,
            config=config,
        )

        return {
            "version": "2.4",
            "pipeline": [
                "inspector",
                "detector",
                "normalizer",
                "validator",
            ],
            "filename": validation.filename,
            "valid": validation.valid,
            "error_count": validation.error_count,
            "warning_count": validation.warning_count,
            "review_count": validation.review_count,
            "accepted_records": len(validation.accepted_records),
            "rejected_records": len(validation.rejected_records),
            "result": validation.as_dict(),
        }

    finally:
        temporary_path.unlink(missing_ok=True)
