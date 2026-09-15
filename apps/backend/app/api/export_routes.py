from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse, Response

from app.services import document_service as docs
from app.services import us_export_service
from app.services.export_service import build_export_json, build_export_csv, build_export_excel

router = APIRouter()


def _is_us(document: dict) -> bool:
    return (document.get("country") or "INDIA").upper() == "USA"


def _basename(document: dict, doc_type: str | None) -> str:
    """Name the download after what the document is, not what it is stored in."""
    if _is_us(document):
        return us_export_service.export_basename(doc_type)
    return "invoice"


@router.get("/{document_id}/export/json")
async def export_json(document_id: str):
    doc = await docs.get_document(document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    final = await docs.get_final_output(document_id)
    if not final:
        # Fall back to extraction result
        extraction = await docs.get_extraction_result(document_id)
        if not extraction:
            raise HTTPException(status_code=404, detail="No output available yet. Complete review first.")
        return extraction.get("invoice_json", {})
    if _is_us(doc):
        return us_export_service.build_us_export_json(final, doc)
    return build_export_json(final, doc)


@router.get("/{document_id}/export/csv")
async def export_csv(document_id: str):
    doc = await docs.get_document(document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    final = await docs.get_final_output(document_id)
    if not final:
        raise HTTPException(status_code=404, detail="No output available yet. Complete review first.")
    doc_type = us_export_service.resolve_doc_type(final, doc) if _is_us(doc) else None
    csv_content = (
        us_export_service.build_us_export_csv(final, doc_type)
        if _is_us(doc) else build_export_csv(final)
    )
    filename = f"{_basename(doc, doc_type)}_{document_id[:8]}.csv"
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{document_id}/export/excel")
async def export_excel(document_id: str):
    doc = await docs.get_document(document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    final = await docs.get_final_output(document_id)
    if not final:
        raise HTTPException(status_code=404, detail="No output available yet. Complete review first.")
    doc_type = us_export_service.resolve_doc_type(final, doc) if _is_us(doc) else None
    excel_bytes = (
        us_export_service.build_us_export_excel(final, doc_type)
        if _is_us(doc) else build_export_excel(final)
    )
    filename = f"{_basename(doc, doc_type)}_{document_id[:8]}.xlsx"
    return Response(
        content=excel_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
