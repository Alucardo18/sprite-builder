"""Domain-specific failures."""


class SpriteBuilderError(Exception):
    """Base exception for expected pipeline failures."""


class ConfigurationError(SpriteBuilderError, ValueError):
    """A configuration file violates the public contract."""


class ArtifactIntegrityError(SpriteBuilderError):
    """An artifact does not match its recorded digest."""


class StageTransitionError(SpriteBuilderError):
    """A requested pipeline state transition is invalid."""
