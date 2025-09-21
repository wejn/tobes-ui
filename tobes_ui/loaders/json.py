"""Class to load json as a Spectrum"""

from tobes_ui.spectrometer import Spectrum
from tobes_ui.loader import Loader

class JsonLoader(Loader, registered_types=['json']):
    """Json file loader plugin for tobes"""

    @classmethod
    def load(cls, file: str) -> "Spectrum":
        return Spectrum.from_file(file)
