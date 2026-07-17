from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse, Response

from app.services import document_service as docs
from app.services.export_service import build_export_json, build_export_csv, build_export_excel

router = APIRouter()


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
    return build_export_json(final, doc)


@router.get("/{document_id}/export/csv")
async def export_csv(document_id: str):
    doc = await docs.get_document(document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    final = await docs.get_final_output(document_id)
    if not final:
        raise HTTPException(status_code=404, detail="No output available yet. Complete review first.")
    csv_content = build_export_csv(final)
    filename = f"invoice_{document_id[:8]}.csv"
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
    excel_bytes = build_export_excel(final)
    filename = f"invoice_{document_id[:8]}.xlsx"
    return Response(
        content=excel_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
