from pathlib import Path
from tempfile import NamedTemporaryFile

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from assessment_engine.config import load_config
from assessment_engine.importer import parse_workbook
from assessment_engine.analyzer import make_context, compute_all_results
from assessment_engine.storage import to_dict
from assessment_engine.storage import JsonStorage


from api.routes.analytics import router as analytics_router

BASE_DIR = Path(__file__).resolve().parent.parent

CONFIG_PATH = BASE_DIR / "configs" / "college.json"
DATA_DIR = BASE_DIR / "data"

config = load_config(CONFIG_PATH)
storage = JsonStorage(DATA_DIR)

app = FastAPI(
    title="QUADxy Academic Assessment API",
    version="0.1.0",
)

app.include_router(analytics_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5500",
        "http://localhost:5500",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def root():
    return {
        "product": "QUADxy Academic Assessment Platform",
        "status": "online",
    }


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "institution": config.institution.name,
        "institution_id": config.institution.id,
    }
@app.post("/api/academic/import/preview")
async def preview_academic_import(file: UploadFile = File(...)):
    if not file.filename:
        raise HTTPException(
            status_code=400,
            detail="No file was provided.",
        )

    if not file.filename.lower().endswith((".xlsx", ".xlsm")):
        raise HTTPException(
            status_code=400,
            detail="Please upload an Excel .xlsx or .xlsm file.",
        )

    contents = await file.read()

    with NamedTemporaryFile(
        suffix=Path(file.filename).suffix,
        delete=False,
    ) as temporary:
        temporary.write(contents)
        temporary_path = Path(temporary.name)

    try:
        plan = parse_workbook(
            config,
            storage,
            temporary_path,
        )

        return {
            "valid": not plan.has_errors,
            "students_to_create": len(plan.new_students),
            "enrollments": len(plan.enrollments),
            "marks": len(plan.marks),
            "errors": [
                {
                    "sheet": error.sheet,
                    "row": error.row_no,
                    "column": error.column,
                    "message": error.message,
                }
                for error in plan.errors
            ],
            "notes": plan.notes,
        }

    finally:
        temporary_path.unlink(missing_ok=True)

@app.post("/api/academic/import")
async def import_academic_data(file: UploadFile = File(...)):
    if not file.filename:
        raise HTTPException(
            status_code=400,
            detail="No file was provided.",
        )

    if not file.filename.lower().endswith((".xlsx", ".xlsm")):
        raise HTTPException(
            status_code=400,
            detail="Please upload an Excel .xlsx or .xlsm file.",
        )

    contents = await file.read()

    with NamedTemporaryFile(
        suffix=Path(file.filename).suffix,
        delete=False,
    ) as temporary:
        temporary.write(contents)
        temporary_path = Path(temporary.name)

    try:
        plan = parse_workbook(
            config,
            storage,
            temporary_path,
        )

        # Never save invalid data.
        if plan.has_errors:
            raise HTTPException(
                status_code=400,
                detail={
                    "message": "Workbook validation failed. No data was imported.",
                    "errors": [
                        {
                            "sheet": error.sheet,
                            "row": error.row_no,
                            "column": error.column,
                            "message": error.message,
                        }
                        for error in plan.errors
                    ],
                },
            )

        report = plan.apply(storage)

        return {
            "status": "imported",
            "institution_id": plan.institution_id,
            "students_created": len(plan.new_students),
            "enrollments_created": len(plan.enrollments),
            "marks_imported": len(plan.marks),
            "notes": plan.notes,
        }

    finally:
        temporary_path.unlink(missing_ok=True)
@app.get("/api/academic/results")
def get_academic_results():
    context = make_context(config, storage)
    results = compute_all_results(context)

    return {
        "institution_id": config.institution.id,
        "institution": config.institution.name,
        "results": [to_dict(result) for result in results],
    }
