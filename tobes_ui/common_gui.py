"""Common GUI class, taking away commonalities."""

from abc import abstractmethod
import queue
import pprint # pylint: disable=unused-import
import threading
import time


from tobes_ui.common import AttrDict
from tobes_ui.logger import LOGGER # pylint: disable=unused-import
from tobes_ui.types import RefreshType


class CommonGUI:  # pylint: disable=too-few-public-methods
    """Common GUI window with a spectrometer instance."""

    def __init__(self, root, spectrometer, title="Untitled UI window"):
        self._root = root
        self._root.title(title)
        self._root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._root.geometry("1200x800")
        self._root.minsize(1200, 800)

        self._spectrometer = spectrometer
        self._refresh_type = RefreshType.NONE if spectrometer else RefreshType.DISABLED

        self._event_queue = queue.Queue()  # TK events submitted from non-main thread
        self._worker_thread = threading.Thread(target=self._data_refresh_loop, daemon=True)
        self._worker_thread.start()

        self._ui_elements = AttrDict()  # all the different UI elements we need access to

        self._setup_ui()

        # Kick off event Q processing...
        self._root.after(0, self._process_event_queue)

        self._update_status('Ready.')

    @abstractmethod
    def _setup_ui(self):
        """Setup UI, inserting elements into self._ui_elements as needed."""
        # Use self._root, insert addressable elements into self._ui_elements

    @abstractmethod
    def _process_spectrum(self, spectrum):
        """Processes captured spectrum, runs in main thread"""
        # Use this to process retrieved spectrum, in any way you see fit

    @abstractmethod
    def _on_capture_stop(self):
        """Event that runs when capture is stopped in refresh loop."""
        # Useful if you only want to post-process something when the spectra
        # stops changing.

    def _process_event_queue(self):
        while not self._event_queue.empty():
            event = self._event_queue.get_nowait()
            event()
        if self._refresh_type in [RefreshType.ONESHOT, RefreshType.CONTINUOUS]:
            # Make queue processing more snappy when capturing...
            self._root.after(20, self._process_event_queue)
        else:
            self._root.after(100, self._process_event_queue)

    def _push_event(self, event):
        if callable(event):
            self._event_queue.put(event)
        else:
            raise ValueError(f"Event {event} is not callable")

    def _set_refresh_type(self, rt):
        match rt:
            case RefreshType.CONTINUOUS:
                self._update_status('Starting capture...')

            case RefreshType.NONE:
                self._update_status('Stopping capture...')

            case RefreshType.ONESHOT:
                self._update_status('Starting single capture...')

            case RefreshType.DISABLED:
                self._update_status('Disabling capture...')

            case _:
                pass # Ignore

        self._refresh_type = rt

    def _data_refresh_loop(self):
        # WARNING: Does NOT run in main thread; do not run any Tkinter code here!
        while True:
            match self._refresh_type:
                case RefreshType.DISABLED:
                    return

                case RefreshType.NONE:
                    time.sleep(0.1)

                case RefreshType.ONESHOT | RefreshType.CONTINUOUS:
                    def handle_spectrum(value):
                        #LOGGER.debug("Got spectrum data with %s status and %.2f integration",
                        #             value.status, value.time)
                        # FIXME: test if it is "good"...
                        self._push_event(lambda: self._process_spectrum(value))
                        if self._refresh_type in [RefreshType.NONE, RefreshType.ONESHOT]:
                            self._refresh_type = RefreshType.NONE
                            self._push_event(lambda: self._update_status('Capture stopped.'))
                            self._push_event(self._on_capture_stop)
                        return self._refresh_type == RefreshType.CONTINUOUS
                    self._push_event(lambda: self._update_status('Capture running...'))
                    self._spectrometer.stream_data(handle_spectrum)

    def _update_status(self, message):
        if 'status_label' in self._ui_elements:
            self._ui_elements.status_label.config(text=message)
        else:
            print('Status:', message)

    def _on_close(self):
        self._update_status('Terminating capture...')
        self._refresh_type = RefreshType.DISABLED
        if self._worker_thread:
            self._worker_thread.join()
            self._worker_thread = None

        self._update_status('Terminating spectrometer...')
        if self._spectrometer:
            self._spectrometer.cleanup()
            self._spectrometer = None

        self._update_status('Bye!')
        self._root.destroy()
