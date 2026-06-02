import os
import logging
import cloudinary
import cloudinary.uploader
from flask import current_app

logger = logging.getLogger(__name__)


def init_cloudinary(app):
    cloudinary.config(
        cloud_name=app.config.get('CLOUDINARY_CLOUD_NAME', ''),
        api_key=app.config.get('CLOUDINARY_API_KEY', ''),
        api_secret=app.config.get('CLOUDINARY_API_SECRET', ''),
        secure=True
    )


def is_configured():
    config = cloudinary.config()
    return bool(config.cloud_name and config.api_key and config.api_secret)


def _save_to_temp(file_input):
    """Save a file-like object to a temp file and return the path."""
    temp_dir = '/tmp'
    if not os.path.exists(temp_dir):
        temp_dir = os.environ.get('TEMP', os.environ.get('TMPDIR', '.'))
    filename = getattr(file_input, 'filename', None) or 'upload'
    temp_path = os.path.join(temp_dir, f'cloud_{os.urandom(4).hex()}_{filename}')
    file_input.save(temp_path)
    return temp_path


def upload_file(file_input, folder='shikshya', public_id=None, resource_type='auto'):
    """
    Upload a file to Cloudinary.
    Accepts a file path (str), a file-like object, or a Werkzeug FileStorage.
    """
    if not is_configured():
        logger.warning('Cloudinary not configured, saving locally.')
        return None

    temp_path = None
    try:
        if not isinstance(file_input, str):
            temp_path = _save_to_temp(file_input)
            file_input = temp_path

        params = {'folder': folder, 'resource_type': resource_type}
        if public_id:
            params['public_id'] = public_id

        result = cloudinary.uploader.upload(file_input, **params)
        url = result.get('secure_url') or result.get('url')
        logger.info(f'Uploaded to Cloudinary: {url}')
        return url
    except Exception as e:
        logger.error(f'Cloudinary upload failed: {e}')
        return None
    finally:
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass
