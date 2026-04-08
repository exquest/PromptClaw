"""CypherClaw package compatibility surface during the src migration."""

from .first_boot import (
    FirstBootAnnouncer,
    InstanceIdentity,
    bootstrap_identity,
    generate_artistic_name,
    mint_identity,
)

__all__ = [
    "FirstBootAnnouncer",
    "InstanceIdentity",
    "__version__",
    "bootstrap_identity",
    "generate_artistic_name",
    "mint_identity",
]
__version__ = "3.0.0"
