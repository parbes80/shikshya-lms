import os
import uuid
import secrets
import logging
from datetime import datetime, date, timedelta
from werkzeug.utils import secure_filename
from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app
from flask_login import login_user, logout_user, login_required, current_user
from database import db
from models.user import User, Role, UserProfile
from models.interaction import PasswordResetRequest, PasswordResetToken
from utils.mail import send_password_reset_email
from utils.cloudinary_upload import upload_file

logger = logging.getLogger(__name__)

auth_bp = Blueprint('auth', __name__)

VALID_ROLES = ['Student', 'Teacher', 'Admin']


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('main.home'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        role_name = request.form.get('role', 'Student')

        if role_name not in VALID_ROLES:
            flash('Invalid role selected.', 'danger')
            return redirect(url_for('auth.register'))

        if not username or not email or not password:
            flash('All fields are required.', 'danger')
            return redirect(url_for('auth.register'))

        if len(password) < 6:
            flash('Password must be at least 6 characters.', 'danger')
            return redirect(url_for('auth.register'))

        user_exists = User.query.filter(
            (User.username == username) | (User.email == email)
        ).first()
        if user_exists:
            flash('Username or Email already registered.', 'danger')
            return redirect(url_for('auth.register'))

        role = Role.query.filter_by(name=role_name).first()
        if not role:
            flash('Invalid role selected.', 'danger')
            return redirect(url_for('auth.register'))

        is_approved = role_name != 'Teacher'

        new_user = User(
            username=username,
            email=email,
            role_id=role.id,
            is_approved=is_approved,
            avatar_url='avatar_default.jpg'
        )
        new_user.set_password(password)

        db.session.add(new_user)
        db.session.flush()

        profile = UserProfile(user_id=new_user.id, bio="Welcome to my Shikshya profile!")
        db.session.add(profile)
        db.session.commit()

        if role_name == 'Teacher':
            flash('Registration successful! Waiting for Admin approval before you can publish courses.', 'warning')
        else:
            flash('Registration successful! Please log in.', 'success')

        return redirect(url_for('auth.login'))

    return render_template('login.html', action='register')


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.home'))

    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        remember = bool(request.form.get('remember'))

        user = User.query.filter_by(email=email).first()
        if not user or not user.check_password(password):
            flash('Invalid email or password.', 'danger')
            return redirect(url_for('auth.login'))

        login_user(user, remember=remember)
        from flask import session as f_session
        f_session.permanent = True

        today = date.today()
        if user.last_activity_date:
            delta = today - user.last_activity_date
            if delta.days == 1:
                user.streak_count += 1
            elif delta.days > 1:
                user.streak_count = 1
        else:
            user.streak_count = 1
        user.last_activity_date = today
        db.session.commit()

        flash(f'Welcome back, {user.username}! Learning streak: {user.streak_count} days \U0001f525', 'success')

        if user.role.name == 'Admin':
            return redirect(url_for('dashboard.admin'))
        elif user.role.name == 'Teacher':
            return redirect(url_for('dashboard.teacher'))
        else:
            return redirect(url_for('dashboard.student'))

    return render_template('login.html', action='login')


@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Logged out successfully.', 'info')
    return redirect(url_for('main.home'))


@auth_bp.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    if request.method == 'POST':
        action = request.form.get('action', 'profile')

        if action == 'password':
            current_password = request.form.get('current_password', '')
            new_password = request.form.get('new_password', '')
            confirm_password = request.form.get('confirm_password', '')

            if not current_password or not new_password or not confirm_password:
                flash('All password fields are required.', 'danger')
                return redirect(url_for('auth.profile'))

            if not current_user.check_password(current_password):
                flash('Current password is incorrect.', 'danger')
                return redirect(url_for('auth.profile'))

            if new_password != confirm_password:
                flash('New passwords do not match.', 'danger')
                return redirect(url_for('auth.profile'))

            if len(new_password) < 6:
                flash('New password must be at least 6 characters.', 'danger')
                return redirect(url_for('auth.profile'))

            current_user.set_password(new_password)
            db.session.commit()
            flash('Password changed successfully!', 'success')
            return redirect(url_for('auth.profile'))

        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip().lower()

        if not username or not email:
            flash('Username and email are required.', 'danger')
            return redirect(url_for('auth.profile'))

        existing = User.query.filter(
            (User.username == username) | (User.email == email),
            User.id != current_user.id
        ).first()
        if existing:
            flash('Username or Email already taken by another user.', 'danger')
            return redirect(url_for('auth.profile'))

        current_user.username = username
        current_user.email = email

        if not current_user.profile:
            profile = UserProfile(user_id=current_user.id)
            db.session.add(profile)
            db.session.flush()

        current_user.profile.bio = request.form.get('bio')
        current_user.profile.qualification = request.form.get('qualification')
        current_user.profile.skills = request.form.get('skills')
        current_user.profile.website = request.form.get('website')
        current_user.profile.github = request.form.get('github')
        current_user.profile.linkedin = request.form.get('linkedin')

        avatar_file = request.files.get('avatar_file')
        if avatar_file and avatar_file.filename:
            url = upload_file(avatar_file, folder='shikshya/avatars', resource_type='image')
            if url:
                current_user.avatar_url = url

        db.session.commit()
        flash('Profile updated successfully.', 'success')
        return redirect(url_for('auth.profile'))

    return render_template('profile.html')


@auth_bp.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if current_user.is_authenticated:
        return redirect(url_for('main.home'))

    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        user = User.query.filter_by(email=email).first()
        if not user:
            flash('No account found with that email address.', 'danger')
            return redirect(url_for('auth.forgot_password'))

        existing = PasswordResetRequest.query.filter_by(
            user_id=user.id, status='pending'
        ).first()
        if existing:
            flash('You already have a pending reset request. Please wait for admin approval.', 'warning')
            return redirect(url_for('auth.forgot_password'))

        req = PasswordResetRequest(user_id=user.id, email=email)
        db.session.add(req)
        db.session.commit()

        logger.info(f'Password reset request from {email} (ID: {user.id})')
        flash('Your request has been submitted. An admin will review and send a reset link to your email shortly.', 'info')
        return redirect(url_for('auth.login'))

    return render_template('forgot_password.html')


@auth_bp.route('/admin/reset-password', methods=['GET', 'POST'])
@login_required
def admin_reset_password():
    if current_user.role.name != 'Admin':
        flash('Access denied.', 'danger')
        return redirect(url_for('main.home'))

    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        user = User.query.filter_by(email=email).first()
        if not user:
            flash('No account found with that email address.', 'danger')
            return redirect(url_for('auth.admin_reset_password'))

        token = secrets.token_urlsafe(48)
        reset_link = url_for('auth.reset_password', token=token, _external=True)
        expires = datetime.utcnow() + timedelta(hours=24)

        PasswordResetToken.query.filter_by(user_id=user.id, is_used=False).delete()
        db.session.flush()

        reset_token = PasswordResetToken(
            user_id=user.id,
            token=token,
            expires_at=expires
        )
        db.session.add(reset_token)
        db.session.commit()

        sent = send_password_reset_email(user, reset_link)

        if sent:
            flash(f'Password reset link sent to {email}.', 'success')
        else:
            logger.warning(f'Email not sent to {email}, link printed to console: {reset_link}')
            print(f'[PASSWORD RESET] Link for {email}: {reset_link}')
            flash(f'Password reset link generated (email not configured). Link: {reset_link}', 'warning')
        return redirect(url_for('dashboard.admin'))

    pending_requests = PasswordResetRequest.query.filter_by(status='pending').order_by(PasswordResetRequest.created_at.desc()).all()
    return render_template('admin_reset_password.html', pending_requests=pending_requests)


@auth_bp.route('/admin/approve-reset-request/<int:request_id>')
@login_required
def approve_reset_request(request_id):
    if current_user.role.name != 'Admin':
        flash('Access denied.', 'danger')
        return redirect(url_for('main.home'))

    req = PasswordResetRequest.query.get_or_404(request_id)
    if req.status != 'pending':
        flash('This request has already been processed.', 'info')
        return redirect(url_for('auth.admin_reset_password'))

    user = User.query.get(req.user_id)
    token = secrets.token_urlsafe(48)
    reset_link = url_for('auth.reset_password', token=token, _external=True)
    expires = datetime.utcnow() + timedelta(hours=24)

    PasswordResetToken.query.filter_by(user_id=user.id, is_used=False).delete()
    db.session.flush()

    reset_token = PasswordResetToken(user_id=user.id, token=token, expires_at=expires)
    db.session.add(reset_token)

    req.status = 'approved'
    req.resolved_at = datetime.utcnow()
    req.resolved_by = current_user.id
    db.session.commit()

    sent = send_password_reset_email(user, reset_link)

    if sent:
        flash(f'Reset link sent to {req.email}.', 'success')
    else:
        logger.warning(f'Email not sent to {req.email}, link printed to console: {reset_link}')
        print(f'[PASSWORD RESET] Admin approved request for {req.email}: {reset_link}')
        flash(f'Reset link generated for {req.email} (email not configured). Link: {reset_link}', 'warning')
    return redirect(url_for('auth.admin_reset_password'))


@auth_bp.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    reset = PasswordResetToken.query.filter_by(token=token, is_used=False).first()
    if not reset or reset.is_expired():
        flash('This reset link is invalid or has expired.', 'danger')
        return redirect(url_for('auth.login'))

    if request.method == 'POST':
        password = request.form.get('password', '')
        confirm = request.form.get('confirm_password', '')

        if len(password) < 6:
            flash('Password must be at least 6 characters.', 'danger')
            return render_template('set_new_password.html', token=token)

        if password != confirm:
            flash('Passwords do not match.', 'danger')
            return render_template('set_new_password.html', token=token)

        user = User.query.get(reset.user_id)
        user.set_password(password)
        reset.is_used = True
        db.session.commit()

        flash('Password reset successfully. Please log in.', 'success')
        return redirect(url_for('auth.login'))

    return render_template('set_new_password.html', token=token)
