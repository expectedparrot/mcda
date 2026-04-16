from __future__ import annotations


class McdaError(Exception):
    exit_code = 1
    code = "mcda_error"

    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}


class ProjectNotFound(McdaError):
    exit_code = 2
    code = "missing_project"


class InvalidProject(McdaError):
    exit_code = 2
    code = "invalid_project"


class UserError(McdaError):
    exit_code = 1
    code = "user_error"


class ScopeViolation(McdaError):
    exit_code = 3
    code = "scope_violation"


class AnalysisError(McdaError):
    exit_code = 4
    code = "analysis_error"
