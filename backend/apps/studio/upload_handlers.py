from django.core.files.uploadhandler import FileUploadHandler
from rest_framework.exceptions import APIException

from apps.studio.services import max_upload_bytes


class UploadTooLarge(APIException):
    status_code = 413
    default_detail = {
        "code": "upload_too_large",
        "message": "Invalid request.",
        "errors": {"file": ["File exceeds the maximum upload size."]},
    }


class StudioUploadSizeLimitHandler(FileUploadHandler):
    def __init__(self, request):
        super().__init__(request)
        self.bytes_received = 0

    def receive_data_chunk(self, raw_data, start):
        self.bytes_received += len(raw_data)
        if self.bytes_received > max_upload_bytes():
            raise UploadTooLarge()
        return raw_data

    def file_complete(self, file_size):
        return None
