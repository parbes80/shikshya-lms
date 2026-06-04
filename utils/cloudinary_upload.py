import os
import re
import logging
import cloudinary
import cloudinary.uploader
import cloudinary.utils
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


def parse_cloudinary_public_id(url):
    """Extract public_id (without extension) from a Cloudinary URL."""
    # Pattern: /resource_type/type/v1_0/folder/public_id.ext or /resource_type/type/folder/public_id
    match = re.search(r'/(raw|image|video|auto)/upload/(?:v\d+/)?(.+?)\.\w+$', url)
    if match:
        return match.group(2)
    return None


def get_signed_download_url(url, resource_type='raw', expires_secs=300):
    """Generate a signed Cloudinary download URL valid for expires_secs."""
    if not url or not is_configured():
        return url
    public_id = parse_cloudinary_public_id(url)
    if not public_id:
        return url
    try:
        from datetime import datetime, timedelta
        from cloudinary.utils import private_download_url
        expires_at = int((datetime.utcnow() + timedelta(seconds=expires_secs)).timestamp())
        return private_download_url(
            public_id, 'pdf',
            resource_type=resource_type,
            type='upload',
            attachment=True,
            expires_at=expires_at
        )
    except Exception as e:
        logger.error(f'Failed to generate signed URL: {e}')
        return url
