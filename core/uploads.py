"""Bound file uploads while they are being received."""

from django.conf import settings
from django.core.files.uploadhandler import FileUploadHandler, StopUpload


class BoundedUploadHandler(FileUploadHandler):
    """Stop receiving a request's files once they exceed the raw-data size limit.

    Django otherwise writes an upload of any size to a temporary file before a view can refuse
    it. This handler runs first. When the files of one request add up to more than
    ``settings.RAW_DATA_MAX_BYTES`` it stops the upload, lets Django discard the rest of the
    request body and sets ``request.upload_too_large``, so the view can say why no file arrived.
    """

    def __init__(self, request=None):
        super().__init__(request)
        self.received = 0

    def receive_data_chunk(self, raw_data, start):
        self.received += len(raw_data)
        if self.received > settings.RAW_DATA_MAX_BYTES:
            if self.request is not None:
                self.request.upload_too_large = True
            raise StopUpload(connection_reset=False)
        return raw_data

    def file_complete(self, file_size):
        return None  # the next handler builds the uploaded file
