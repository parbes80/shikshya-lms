"""Central upload validation and storage helpers.

Rules:
- Every upload has an explicit extension allowlist.
- Executable and browser-rendered formats (``.html``, ``.js``, ``.css``,
  ``.svg``, ``.php`` ...) are never accepted.
- Stored filenames are generated, never taken from the client.
- Small files may go to Cloudinary when configured; sensitive submissions stay
  on local disk.
"""

import os
import re
import uuid

from flask import current_app
from werkzeug.utils import secure_filename

from utils.cloudinary_upload import is_configured, upload_file

IMAGE_EXTENSIONS = frozenset({'png', 'jpg', 'jpeg', 'gif', 'webp'})
DOCUMENT_EXTENSIONS = frozenset({
    'pdf', 'doc', 'docx', 'ppt', 'pptx', 'xls', 'xlsx', 'txt', 'csv', 'odt',
    'rtf',
})
SUBMISSION_EXTENSIONS = DOCUMENT_EXTENSIONS | IMAGE_EXTENSIONS | {'zip'}

DEFAULT_MAX_BYTES = 16 * 1024 * 1024


class UploadValidationError(ValueError):
    """Raised when an uploaded file fails validation."""


def _extension(filename):
    """Return a safe lowercase extension from the client filename."""
    raw_name = (filename or '').replace('\\', '/').rsplit('/', 1)[-1].strip()
    if not raw_name or '.' not in raw_name:
        return ''
    ext = raw_name.rsplit('.', 1)[1].lower()
    if not re.fullmatch(r'[a-z0-9]{1,10}', ext):
        return ''
    return ext


def validate_upload(file_storage, allowed_extensions, max_bytes=None):
    """Validate an upload and return its lower-case extension."""
    if file_storage is None:
        raise UploadValidationError('No file was provided.')

    ext = _extension(getattr(file_storage, 'filename', ''))
    if not ext:
        raise UploadValidationError('A file with a valid extension is required.')

    allowed = {item.lower().lstrip('.') for item in allowed_extensions}
    if ext not in allowed:
        raise UploadValidationError(
            f'File type .{ext} is not allowed. Allowed types: '
            f'{", ".join(sorted(allowed))}.'
        )

    max_bytes = max_bytes or current_app.config.get(
        'MAX_CONTENT_LENGTH', DEFAULT_MAX_BYTES
    )
    stream = file_storage.stream
    position = stream.tell()
    stream.seek(0, os.SEEK_END)
    size = stream.tell()
    stream.seek(position)
    if size <= 0:
        raise UploadValidationError('The uploaded file is empty.')
    if size > max_bytes:
        raise UploadValidationError(
            f'The uploaded file is larger than {max_bytes // (1024 * 1024)} MB.'
        )
    return ext


def save_local_upload(file_storage, *, allowed_extensions, local_subdir,
                      prefix='file', max_bytes=None):
    """Validate and store a file under ``UPLOAD_FOLDER/<local_subdir>``.

    Returns a URL relative to the application root, e.g.
    ``uploads/assignments/sub_1_2_ab12cd34.pdf``.
    """
    ext = validate_upload(file_storage, allowed_extensions, max_bytes=max_bytes)
    directory = os.path.join(current_app.config['UPLOAD_FOLDER'], local_subdir)
    os.makedirs(directory, exist_ok=True)
    name = f'{secure_filename(prefix)}_{uuid.uuid4().hex}.{ext}'
    path = os.path.join(directory, name)
    file_storage.stream.seek(0)
    file_storage.save(path)
    return f'uploads/{local_subdir}/{name}'


def store_upload(file_storage, *, allowed_extensions, folder, local_subdir,
                 resource_type='auto', prefix='file', max_bytes=None):
    """Validate and store a non-sensitive file.

    Uses Cloudinary when configured and falls back to local storage, so a
    missing or failing cloud configuration never silently loses an upload.
    """
    ext = validate_upload(file_storage, allowed_extensions, max_bytes=max_bytes)

    if is_configured():
        file_storage.stream.seek(0)
        url = upload_file(file_storage, folder=folder, resource_type=resource_type)
        if url:
            return url

    directory = os.path.join(current_app.config['UPLOAD_FOLDER'], local_subdir)
    os.makedirs(directory, exist_ok=True)
    name = f'{secure_filename(prefix)}_{uuid.uuid4().hex}.{ext}'
    path = os.path.join(directory, name)
    file_storage.stream.seek(0)
    file_storage.save(path)
    return f'uploads/{local_subdir}/{name}'
