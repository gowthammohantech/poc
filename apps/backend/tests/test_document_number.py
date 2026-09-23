"""The documents list shows the number each document is known by.

India invoices carry an invoice number, US purchase orders an order number and
US shipping authorizations a release number; the list reads whichever the
payload has, preferring what a reviewer submitted over what extraction read.

The number is resolved when extraction or a correction is saved and kept on the
document, so these go through the write path rather than seeding it directly.
"""

from app.services import document_service


async def _seed(make_document, doc_id, extracted=None, corrected=None):
    await make_document(doc_id)
    if extracted is not None:
        await document_service.save_extraction_result(doc_id, {"invoice": extracted}, {})
    if corrected is not None:
        await document_service.save_final_output(doc_id, {"invoice": corrected})
    return doc_id


async def _numbers():
    return {d["id"]: d["document_number"] for d in await document_service.get_all_documents()}


async def test_each_document_family_shows_its_own_number(mongo_db, make_document):
    await _seed(make_document, "india", extracted={"invoice_number": "INV-001"})
    await _seed(make_document, "so", extracted={"document_type": "SO", "order_number": "PO-42"})
    await _seed(make_document, "sa", extracted={"document_type": "SA", "release_number": "R-7"})

    assert await _numbers() == {"india": "INV-001", "so": "PO-42", "sa": "R-7"}


async def test_a_reviewed_number_wins_over_the_extracted_one(mongo_db, make_document):
    await _seed(make_document, "doc", extracted={"invoice_number": "1NV-00l"},
                corrected={"invoice_number": "INV-001"})

    assert (await _numbers())["doc"] == "INV-001"


async def test_a_later_extraction_does_not_overwrite_a_correction(mongo_db, make_document):
    """Re-running extraction on a reviewed document must not undo the fix.

    The number is denormalised now, so the precedence has to hold on whichever
    of the two writes happens last.
    """
    await _seed(make_document, "doc", extracted={"invoice_number": "1NV-00l"},
                corrected={"invoice_number": "INV-001"})

    await document_service.save_extraction_result("doc", {"invoice": {"invoice_number": "1NV-00l"}}, {})

    assert (await _numbers())["doc"] == "INV-001"


async def test_a_correction_without_a_number_falls_back_to_extraction(mongo_db, make_document):
    await _seed(make_document, "doc", extracted={"invoice_number": "INV-500"},
                corrected={"supplier": {"name": "ACME"}})

    assert (await _numbers())["doc"] == "INV-500"


async def test_no_extraction_or_a_blank_number_is_null(mongo_db, make_document):
    await _seed(make_document, "unprocessed")
    await _seed(make_document, "blank", extracted={"invoice_number": "  "})

    assert await _numbers() == {"unprocessed": None, "blank": None}


async def test_a_purchase_order_keeps_its_po_number_beside_an_invoice_number(mongo_db, make_document):
    await _seed(make_document, "so", extracted={"document_type": "SO", "order_number": "PO-42",
                                                "invoice_number": "INV-9"})
    await _seed(make_document, "so-no-po", extracted={"document_type": "SO", "invoice_number": "INV-10"})
    await _seed(make_document, "inv", extracted={"document_type": "INV", "invoice_number": "INV-11",
                                                 "order_number": "SO-5"})

    assert await _numbers() == {"so": "PO-42", "so-no-po": "INV-10", "inv": "INV-11"}
