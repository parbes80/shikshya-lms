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


def upload_file(file_path, folder='shikshya', public_id=None, resource_type='auto'):
    if not is_configured():
        logger.warning('Cloudinary not configured, saving locally.')
        return None

    try:
        params = {'folder': folder, 'resource_type': resource_type}
        if public_id:
            params['public_id'] = public_id

        result = cloudinary.uploader.upload(file_path, **params)
        url = result.get('secure_url') or result.get('url')
        logger.info(f'Uploaded to Cloudinary: {url}')
        return url
    except Exception as e:
        logger.error(f'Cloudinary upload failed: {e}')
        return None


def upload_fileobj(file_obj, folder='shikshya', public_id=None, resource_type='auto'):
    temp_path = None
    try:
        temp_path = os.path.join('/tmp', file_obj.filename or 'upload')
        file_obj.save(temp_path)
        return upload_file(temp_path, folder, public_id, resource_type)
    finally:
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)
