from pydantic import BaseModel


class RowValidationError(BaseModel):
    row_number: int
    errors: list[str]


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
    summary_counts: IngestionSummary
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
    platform_detected: str | None = None
    transformed_url: str | None = None
