from pydantic import BaseModel
from typing import Optional, List


class VendorSchema(BaseModel):
    name: Optional[str] = None
    gstin: Optional[str] = None
    pan: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None


class CustomerSchema(BaseModel):
    name: Optional[str] = None
    gstin: Optional[str] = None
    address: Optional[str] = None


class LineItemSchema(BaseModel):
    description: Optional[str] = None
    hsn_sac: Optional[str] = None
    quantity: Optional[float] = None
    unit: Optional[str] = None
    unit_price: Optional[float] = None
    taxable_value: Optional[float] = None
    cgst_rate: Optional[float] = None
    cgst_amount: Optional[float] = None
    sgst_rate: Optional[float] = None
    sgst_amount: Optional[float] = None
    igst_rate: Optional[float] = None
    igst_amount: Optional[float] = None
    total: Optional[float] = None


class TaxSummarySchema(BaseModel):
    subtotal: Optional[float] = None
    cgst_total: Optional[float] = None
    sgst_total: Optional[float] = None
    igst_total: Optional[float] = None
    total_tax: Optional[float] = None
    round_off: Optional[float] = None
    grand_total: Optional[float] = None


class BankDetailsSchema(BaseModel):
    account_name: Optional[str] = None
    account_number: Optional[str] = None
    bank_name: Optional[str] = None
    ifsc: Optional[str] = None
    branch: Optional[str] = None


class InvoiceDataSchema(BaseModel):
    invoice_number: Optional[str] = None
    invoice_date: Optional[str] = None
    due_date: Optional[str] = None
    currency: Optional[str] = None
    vendor: VendorSchema = VendorSchema()
    customer: CustomerSchema = CustomerSchema()
    purchase_order_number: Optional[str] = None
    line_items: List[LineItemSchema] = []
    tax_summary: TaxSummarySchema = TaxSummarySchema()
    bank_details: BankDetailsSchema = BankDetailsSchema()


class ConfidenceSchema(BaseModel):
    overall: float = 0.0
    invoice_number: float = 0.0
    invoice_date: float = 0.0
    gstin: float = 0.0
    line_items: float = 0.0
    totals: float = 0.0


class RuleCheckSchema(BaseModel):
    rule: str
    passed: bool
    message: str
    field: Optional[str] = None


class LLMCheckSchema(BaseModel):
    check: str
    result: str
    confidence: float
    message: str
    field: Optional[str] = None


class ValidationResultSchema(BaseModel):
    status: str
    rule_checks: List[RuleCheckSchema] = []
    llm_checks: List[LLMCheckSchema] = []
    warnings: List[str] = []
    errors: List[str] = []


class MetadataSchema(BaseModel):
    ocr_engine: Optional[str] = None
    complexity_score: Optional[float] = None
    processing_mode: Optional[str] = None
    pages: int = 0


class InvoiceOutputSchema(BaseModel):
    document_id: str
    invoice: InvoiceDataSchema = InvoiceDataSchema()
    confidence: ConfidenceSchema = ConfidenceSchema()
    validation: ValidationResultSchema = ValidationResultSchema(status="PENDING")
    metadata: MetadataSchema = MetadataSchema()
