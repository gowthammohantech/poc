from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from app.services import brs_document_service as docs
from app.services.brs_export_service import build_brs_export_json, build_brs_export_csv, build_brs_export_excel

router = APIRouter()


@router.get("/{document_id}/export/json")
async def export_brs_json(document_id: str):
    doc = await docs.get_document(document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="BRS document not found")
    final = await docs.get_final_output(document_id)
    if not final:
        extraction = await docs.get_extraction_result(document_id)
        if not extraction:
            raise HTTPException(status_code=404, detail="No output available yet. Complete review first.")
        return extraction.get("brs_json", {})
    return build_brs_export_json(final)


@router.get("/{document_id}/export/csv")
async def export_brs_csv(document_id: str):
    doc = await docs.get_document(document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="BRS document not found")
    final = await docs.get_final_output(document_id)
    if not final:
        raise HTTPException(status_code=404, detail="No output available yet. Complete review first.")
    csv_content = build_brs_export_csv(final)
    filename = f"brs_{document_id[:8]}.csv"
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{document_id}/export/excel")
async def export_brs_excel(document_id: str):
    doc = await docs.get_document(document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="BRS document not found")
    final = await docs.get_final_output(document_id)
    if not final:
        raise HTTPException(status_code=404, detail="No output available yet. Complete review first.")
    excel_bytes = build_brs_export_excel(final)
    filename = f"brs_{document_id[:8]}.xlsx"
    return Response(
        content=excel_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
