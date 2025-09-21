"""Class to load spectrum data"""

# pylint: disable=too-many-instance-attributes

from abc import ABC, abstractmethod

from tobes_ui.logger import LOGGER
from tobes_ui.spectrometer import Spectrum

class Loader(ABC):
    """Generic file loader for tobes"""
    _registry = []
    _loader_types = {}

    @classmethod
    def loader_types(cls):
        """Return registered loader types"""
        return list(cls._loader_types.keys())

    @classmethod
    @abstractmethod
    def from_file(cls, name: str) -> "Spectrum":
        """Load Spectrum from given file"""

    def __init_subclass__(cls, registered_types: list[str] = None, **kwargs):
        super().__init_subclass__(**kwargs)
        Loader._registry.append(cls)
        for type_ in registered_types or []:
            Loader._loader_types[type_] = cls

    @classmethod
    def load(cls, file: str) -> 'Spectrum':
        """Method for loading Specrum in a generic fashion"""
        import tobes_ui.loaders # pylint: disable=import-outside-toplevel, unused-import

        if ':' in file:
            type_, file_id = file.split(':', 2)

            if type_ in Loader._loader_types:
                LOGGER.debug("Trying loader type=%s with id=%s", type_, file_id)
                try:
                    spectrum = Loader._loader_types[type_].load(file_id)
                    LOGGER.debug("Success: %s", spectrum)
                    return spectrum
                except Exception as ex:  # pylint: disable=broad-exception-caught
                    LOGGER.debug("Loader type=%s doesn't work: %s", type_, ex)
                    raise ValueError(f"Couldn't initialize loadr {type_}: {ex})") from ex

            raise ValueError(f'No such loader type: {type_}')

        LOGGER.debug("Brute-forcing loaders for %s", file)
        # Brute force
        for loader_cls in Loader._registry:
            LOGGER.debug("Trying loader class: %s", loader_cls)
            try:
                spectrum = loader_cls.load(file)
                LOGGER.debug("Success: %s", spectrum)
                return spectrum
            except Exception as ex:  # pylint: disable=broad-exception-caught
                LOGGER.debug("Loader type=%s doesn't work: %s", loader_cls, ex)

        raise ValueError(f'No loader implementation can take {file} as input')
