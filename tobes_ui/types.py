"""UI-related types"""
from enum import Enum


class GraphType(Enum):
    """Defines graph type to display"""
    LINE = 1
    SPECTRUM = 2
    CIE1931 = 3
    CIE1960UCS = 4
    CIE1976UCS = 5
    TM30 = 6
    OVERLAY = 7

    def __str__(self):
        """Convert to readable string"""
        return str(self.name).lower()


class RefreshType(Enum):
    """Defines active refresh"""
    DISABLED = 1
    NONE = 2
    ONESHOT = 3
    CONTINUOUS = 4

    def __str__(self):
        """Convert to readable string"""
        return str(self.name).lower()
