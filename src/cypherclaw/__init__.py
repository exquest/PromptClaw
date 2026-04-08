"""CypherClaw package compatibility surface during the src migration."""

from .first_boot import FirstBootAnnouncer, InstanceIdentity, mint_identity

__all__ = ["FirstBootAnnouncer", "InstanceIdentity", "mint_identity", "__version__"]
__version__ = "3.0.0"
