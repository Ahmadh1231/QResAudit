class QResAuditError(Exception):
    """Base error for expected QResAudit failures."""


class ConfigurationError(QResAuditError):
    pass


class DataFormatError(QResAuditError):
    pass


class FieldGridOrderingError(DataFormatError):
    pass


class PreflightError(QResAuditError):
    pass


class ExportError(QResAuditError):
    pass


class BundleValidationError(QResAuditError):
    pass


class HFSSSessionError(QResAuditError):
    pass
