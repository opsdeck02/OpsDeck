from pydantic import BaseModel


class FieldValidationError(BaseModel):
    field: str
    reason: str
    suggested_fix: str | None = None


class RowValidationError(BaseModel):
    row_number: int
    errors: list[str]
    field_errors: list[FieldValidationError] = []


class RejectionSummary(BaseModel):
    reason: str
    count: int


class IngestionSummary(BaseModel):
    created: int = 0
    updated: int = 0
    unchanged: int = 0


class UploadResult(BaseModel):
    upload_id: int
    ingestion_job_id: int
    file_type: str
    rows_received: int
    rows_accepted: int
    rows_rejected: int
    validation_errors: list[RowValidationError]
    top_rejection_reasons: list[RejectionSummary] = []
    blocking_errors: list[str] = []
    summary_counts: IngestionSummary
    platform_detected: str | None = None
    transformed_url: str | None = None


class SheetUploadResult(BaseModel):
    sheet_name: str
    file_type: str
    status: str
    rows_received: int
    rows_accepted: int
    rows_rejected: int
    validation_errors: list[RowValidationError]
    top_rejection_reasons: list[RejectionSummary] = []
    blocking_errors: list[str] = []
    summary_counts: IngestionSummary


class WorkbookUploadResult(BaseModel):
    upload_id: int
    ingestion_job_id: int
    file_type: str = "workbook"
    rows_received: int
    rows_accepted: int
    rows_rejected: int
    validation_errors: list[RowValidationError]
    top_rejection_reasons: list[RejectionSummary] = []
    blocking_errors: list[str] = []
    summary_counts: IngestionSummary
    sheet_results: list[SheetUploadResult]
    ignored_sheets: list[str] = []
    platform_detected: str | None = None
    transformed_url: str | None = None


class IngestionJobOut(BaseModel):
    id: int
    upload_id: int | None
    file_type: str
    status: str
    rows_received: int
    rows_accepted: int
    rows_rejected: int
    error_message: str | None
    file_name: str | None = None
    source_type: str | None = None
    uploaded_at: str | None = None
    top_rejection_summary: str | None = None
    refreshed_operational_visibility: bool = False


class HeaderMappingSuggestion(BaseModel):
    source_header: str
    suggested_field: str | None
    confidence: str
    alternatives: list[str] = []


class MappingPreviewOut(BaseModel):
    file_type: str
    headers: list[str]
    required_fields: list[str]
    optional_fields: list[str]
    suggestions: list[HeaderMappingSuggestion]
    mapped_required_fields: list[str] = []
    missing_required_fields: list[str] = []
    blocking_errors: list[str] = []
    platform_detected: str | None = None
    transformed_url: str | None = None


class WorkbookSheetPreview(BaseModel):
    sheet_name: str
    hidden: bool = False
    row_count: int
    suggested_file_type: str | None = None
    suggested_label: str | None = None
    previews: dict[str, MappingPreviewOut] = {}


class WorkbookPreviewOut(BaseModel):
    file_name: str
    sheets: list[WorkbookSheetPreview]
    ignored_empty_sheets: list[str] = []
