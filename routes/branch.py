import re
from flask import Blueprint, render_template, redirect, url_for, flash, request, abort, jsonify
from flask_login import login_required, current_user
from database import db
from models.user import Branch, User, UserProfile

branch_bp = Blueprint('branch', __name__)


def slugify(text):
    text = text.lower().strip()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[-\s]+', '-', text)
    return text.strip('-')


@branch_bp.route('/branches')
def list_branches():
    branches = Branch.query.filter_by(is_active=True).all()
    return render_template('branches_list.html', branches=branches)


@branch_bp.route('/branches/map')
def branches_map():
    branches = Branch.query.filter_by(is_active=True).all()
    users = UserProfile.query.filter(
        UserProfile.latitude.isnot(None),
        UserProfile.longitude.isnot(None)
    ).all()
    return render_template('branches_map.html', branches=branches, users=users)


@branch_bp.route('/branches/api/data')
def branches_api():
    branches = Branch.query.filter_by(is_active=True).all()
    data = [{
        'id': b.id,
        'name': b.name,
        'address': b.address,
        'city': b.city,
        'lat': b.latitude,
        'lng': b.longitude,
        'phone': b.phone,
        'email': b.email,
    } for b in branches]
    users = UserProfile.query.filter(
        UserProfile.latitude.isnot(None),
        UserProfile.longitude.isnot(None)
    ).all()
    user_data = [{
        'username': u.user.username,
        'city': u.city,
        'lat': u.latitude,
        'lng': u.longitude,
    } for u in users]
    return jsonify({'branches': data, 'users': user_data})


@branch_bp.route('/branches/create', methods=['GET', 'POST'])
@login_required
def create():
    if current_user.role.name != 'Admin':
        flash('Only admins can manage branches.', 'danger')
        return redirect(url_for('main.home'))

    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        if not name:
            flash('Branch name is required.', 'danger')
            return redirect(url_for('branch.create'))

        slug = f"{slugify(name)}-{__import__('uuid').uuid4().hex[:4]}"
        address = request.form.get('address', '').strip()
        city = request.form.get('city', '').strip()
        lat = float(request.form.get('latitude', 0))
        lng = float(request.form.get('longitude', 0))
        phone = request.form.get('phone', '').strip()
        email = request.form.get('email', '').strip()
        description = request.form.get('description', '').strip()

        branch = Branch(
            name=name, slug=slug, address=address, city=city,
            latitude=lat, longitude=lng,
            phone=phone or None, email=email or None,
            description=description or None
        )
        db.session.add(branch)
        db.session.commit()
        flash(f'Branch "{name}" created successfully!', 'success')
        return redirect(url_for('branch.list_branches'))

    return render_template('branch_form.html', action='create')


@branch_bp.route('/branches/<int:branch_id>/edit', methods=['GET', 'POST'])
@login_required
def edit(branch_id):
    if current_user.role.name != 'Admin':
        abort(403)
    branch = Branch.query.get_or_404(branch_id)

    if request.method == 'POST':
        branch.name = request.form.get('name', '').strip()
        branch.address = request.form.get('address', '').strip()
        branch.city = request.form.get('city', '').strip()
        branch.latitude = float(request.form.get('latitude', 0))
        branch.longitude = float(request.form.get('longitude', 0))
        branch.phone = request.form.get('phone', '').strip() or None
        branch.email = request.form.get('email', '').strip() or None
        branch.description = request.form.get('description', '').strip() or None
        branch.is_active = request.form.get('is_active') == 'on'
        db.session.commit()
        flash(f'Branch "{branch.name}" updated!', 'success')
        return redirect(url_for('branch.list_branches'))

    return render_template('branch_form.html', action='edit', branch=branch)


@branch_bp.route('/branches/<int:branch_id>/delete', methods=['POST'])
@login_required
def delete(branch_id):
    if current_user.role.name != 'Admin':
        abort(403)
    branch = Branch.query.get_or_404(branch_id)
    db.session.delete(branch)
    db.session.commit()
    flash(f'Branch "{branch.name}" deleted.', 'success')
    return redirect(url_for('branch.list_branches'))
