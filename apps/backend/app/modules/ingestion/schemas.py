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


class OperationalUnderstandingSummary(BaseModel):
    file_received: bool = True
    rows_detected: int = 0
    rows_accepted: int = 0
    rows_rejected: int = 0
    records_created: int = 0
    records_updated: int = 0
    records_unchanged: int = 0
    plants_detected: list[str] = []
    materials_detected: list[str] = []
    shipments_detected: list[str] = []
    suppliers_detected: list[str] = []
    new_plants_created: list[str] = []
    new_materials_created: list[str] = []
    new_suppliers_created: list[str] = []
    duplicate_rows_detected: int = 0
    missing_eta_count: int = 0
    missing_consumption_count: int = 0
    missing_threshold_count: int = 0
    can_opsdeck_safely_use_data: bool = False
    safe_to_use_explanation: str | None = None
    risks_or_exposures_generated: int | None = None
    refreshed_operational_visibility: bool = False
    warnings: list[str] = []
    next_recommended_action: str | None = None
    supplier_references_total: int = 0
    supplier_references_linked: int = 0
    supplier_references_unlinked: int = 0
    onboarding_completeness_score: int = 100
    supplier_reliability_impact: str | None = None


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
    operational_summary: OperationalUnderstandingSummary
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
    operational_summary: OperationalUnderstandingSummary


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
    operational_summary: OperationalUnderstandingSummary
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


class ImportRecordReference(BaseModel):
    record_type: str
    record_id: str
    record_reference: str | None = None
    action: str
    rollback_safe: bool = False
    rollback_status: str | None = None


class ImportJobDetailOut(BaseModel):
    import_job_id: int
    upload_id: int | None
    file_name: str | None = None
    import_type: str
    status: str
    stage: str | None = None
    total_rows: int
    accepted_rows: int
    rejected_rows: int
    created_records: int
    updated_records: int
    unchanged_records: int
    warnings: list[str] = []
    row_level_errors: list[RowValidationError] = []
    operational_summary: OperationalUnderstandingSummary | None = None
    record_references: list[ImportRecordReference] = []
    started_at: str | None = None
    completed_at: str | None = None
    uploaded_at: str | None = None
    source_metadata: dict = {}


class RollbackSummary(BaseModel):
    import_job_id: int
    rollback_status: str
    records_deleted: int = 0
    records_skipped: int = 0
    records_preserved: int = 0
    skipped_reasons: list[str] = []
    warnings: list[str] = []

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
