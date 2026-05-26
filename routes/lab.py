import os
import uuid
from datetime import datetime
from werkzeug.utils import secure_filename
from flask import Blueprint, render_template, redirect, url_for, flash, request, abort, current_app
from flask_login import login_required, current_user
from database import db
from models.interaction import Lab

lab_bp = Blueprint('lab', __name__)


@lab_bp.route('/labs')
def index():
    labs = Lab.query.filter_by(is_published=True).order_by(Lab.created_at.desc()).all()
    return render_template('lab_list.html', labs=labs)


@lab_bp.route('/labs/<int:lab_id>')
def detail(lab_id):
    lab = Lab.query.get_or_404(lab_id)
    if not lab.is_published and (not current_user.is_authenticated or current_user.role.name != 'Admin'):
        abort(404)
    return render_template('lab_detail.html', lab=lab)


@lab_bp.route('/labs/create', methods=['GET', 'POST'])
@login_required
def create():
    if current_user.role.name != 'Admin':
        abort(403)

    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        if not title:
            flash('Title is required.', 'danger')
            return redirect(url_for('lab.create'))

        pdf_url = ''
        file = request.files.get('pdf_file')
        if file and file.filename:
            filename = secure_filename(file.filename)
            ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else 'pdf'
            unique_name = f'lab_{uuid.uuid4().hex[:8]}.{ext}'
            upload_path = os.path.join(current_app.config['UPLOAD_FOLDER'], 'labs', unique_name)
            file.save(upload_path)
            pdf_url = f'uploads/labs/{unique_name}'

        lab = Lab(
            title=title,
            description=request.form.get('description', '').strip(),
            content=request.form.get('content', ''),
            pdf_url=pdf_url or request.form.get('pdf_link', '').strip(),
            video_url=request.form.get('video_url', '').strip(),
            is_published=request.form.get('is_published') == 'on',
            created_by=current_user.id
        )
        db.session.add(lab)
        db.session.commit()
        flash(f'Lab "{title}" created.', 'success')
        return redirect(url_for('lab.index'))

    return render_template('lab_form.html', action='create')


@lab_bp.route('/labs/<int:lab_id>/edit', methods=['GET', 'POST'])
@login_required
def edit(lab_id):
    if current_user.role.name != 'Admin':
        abort(403)
    lab = Lab.query.get_or_404(lab_id)

    if request.method == 'POST':
        lab.title = request.form.get('title', '').strip()
        lab.description = request.form.get('description', '').strip()
        lab.content = request.form.get('content', '')
        lab.video_url = request.form.get('video_url', '').strip()
        lab.is_published = request.form.get('is_published') == 'on'

        file = request.files.get('pdf_file')
        if file and file.filename:
            filename = secure_filename(file.filename)
            ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else 'pdf'
            unique_name = f'lab_{uuid.uuid4().hex[:8]}.{ext}'
            upload_path = os.path.join(current_app.config['UPLOAD_FOLDER'], 'labs', unique_name)
            file.save(upload_path)
            lab.pdf_url = f'uploads/labs/{unique_name}'
        else:
            lab.pdf_url = request.form.get('pdf_link', '').strip()

        db.session.commit()
        flash('Lab updated.', 'success')
        return redirect(url_for('lab.index'))

    return render_template('lab_form.html', action='edit', lab=lab)


@lab_bp.route('/labs/<int:lab_id>/delete', methods=['POST'])
@login_required
def delete(lab_id):
    if current_user.role.name != 'Admin':
        abort(403)
    lab = Lab.query.get_or_404(lab_id)
    db.session.delete(lab)
    db.session.commit()
    flash('Lab deleted.', 'success')
    return redirect(url_for('lab.index'))
