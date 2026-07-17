from pydantic import BaseModel
from typing import List, Optional


class RuleCheck(BaseModel):
    rule: str
    passed: bool
    message: str
    field: Optional[str] = None


class LLMCheck(BaseModel):
    check: str
    result: str
    confidence: float
    message: str
    field: Optional[str] = None


class ValidationResult(BaseModel):
    status: str
    rule_checks: List[RuleCheck] = []
    llm_checks: List[LLMCheck] = []
    warnings: List[str] = []
    errors: List[str] = []
