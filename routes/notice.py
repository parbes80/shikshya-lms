import calendar as calmod
from datetime import datetime, date, timedelta
from flask import Blueprint, render_template, redirect, url_for, flash, request, abort, jsonify
from flask_login import login_required, current_user
from database import db
from models.interaction import Notice, Notification
from models.learning import LiveClass, Assignment, Quiz
from utils.sanitize import safe_url

notice_bp = Blueprint('notice', __name__)


@notice_bp.route('/calendar')
def calendar():
    year = request.args.get('year', type=int) or datetime.now().year
    month = request.args.get('month', type=int) or datetime.now().month

    prev_month = month - 1 if month > 1 else 12
    prev_year = year if month > 1 else year - 1
    next_month = month + 1 if month < 12 else 1
    next_year = year if month < 12 else year + 1

    month_names = ['January', 'February', 'March', 'April', 'May', 'June',
                   'July', 'August', 'September', 'October', 'November', 'December']

    month_days = calmod.monthcalendar(year, month)

    return render_template(
        'calendar.html',
        year=year, month=month, month_name=month_names[month - 1],
        month_days=month_days,
        prev_month=prev_month, prev_year=prev_year,
        next_month=next_month, next_year=next_year,
        now=datetime.now
    )


@notice_bp.route('/api/calendar/events')
@login_required
def calendar_events_api():
    start_str = request.args.get('start')
    end_str = request.args.get('end')
    try:
        start_date = datetime.strptime(start_str, '%Y-%m-%d').date() if start_str else date.today()
        end_date = datetime.strptime(end_str, '%Y-%m-%d').date() if end_str else start_date + timedelta(days=31)
    except (ValueError, TypeError):
        start_date = date.today()
        end_date = start_date + timedelta(days=31)

    events = []

    live_classes = LiveClass.query.filter(
        LiveClass.start_time >= datetime.combine(start_date, datetime.min.time()),
        LiveClass.start_time <= datetime.combine(end_date, datetime.max.time())
    ).all()
    for lc in live_classes:
        can_view = (
            current_user.role.name == 'Admin' or
            lc.teacher_id == current_user.id or
            current_user.role.name == 'Student'
        )
        if can_view:
            events.append({
                'id': f'lc-{lc.id}', 'title': f'📺 {lc.title}',
                'start': lc.start_time.strftime('%Y-%m-%d'),
                'color': '#ea4335', 'url': safe_url(lc.meet_link) or '#',
                'type': 'Live Class', 'time': lc.start_time.strftime('%I:%M %p')
            })

    assignments = Assignment.query.filter(
        Assignment.due_date >= datetime.combine(start_date, datetime.min.time()),
        Assignment.due_date <= datetime.combine(end_date, datetime.max.time())
    ).all()
    for a in assignments:
        events.append({
            'id': f'as-{a.id}', 'title': f'📝 {a.title}',
            'start': a.due_date.strftime('%Y-%m-%d'),
            'color': '#f59e0b', 'url': '#',
            'type': 'Assignment Due', 'time': a.due_date.strftime('%I:%M %p')
        })

    return jsonify(events)


@notice_bp.route('/notices')
def list_notices():
    query = Notice.query.order_by(Notice.is_pinned.desc(), Notice.created_at.desc())
    if current_user.is_authenticated:
        role = current_user.role.name.lower()
        query = query.filter(
            db.or_(Notice.target_role == 'all', Notice.target_role == role)
        )
    else:
        query = query.filter(Notice.target_role == 'all')
    notices = query.all()
    return render_template('notices_list.html', notices=notices)


@notice_bp.route('/notices/create', methods=['GET', 'POST'])
@login_required
def create():
    if current_user.role.name not in ['Admin', 'Teacher']:
        abort(403)

    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        content = request.form.get('content', '').strip()
        target_role = request.form.get('target_role', 'all')
        is_pinned = request.form.get('is_pinned') == 'on'

        if not title or not content:
            flash('Title and content are required.', 'danger')
            return redirect(url_for('notice.create'))

        notice = Notice(
            author_id=current_user.id, title=title, content=content,
            target_role=target_role, is_pinned=is_pinned
        )
        db.session.add(notice)
        db.session.commit()
        flash(f'Notice "{title}" published!', 'success')
        return redirect(url_for('notice.list_notices'))

    return render_template('notice_form.html', action='create')


@notice_bp.route('/notices/<int:notice_id>/edit', methods=['GET', 'POST'])
@login_required
def edit(notice_id):
    notice = Notice.query.get_or_404(notice_id)
    if current_user.role.name not in ['Admin', 'Teacher'] or (current_user.role.name == 'Teacher' and notice.author_id != current_user.id):
        abort(403)

    if request.method == 'POST':
        notice.title = request.form.get('title', '').strip()
        notice.content = request.form.get('content', '').strip()
        notice.target_role = request.form.get('target_role', 'all')
        notice.is_pinned = request.form.get('is_pinned') == 'on'
        db.session.commit()
        flash(f'Notice updated!', 'success')
        return redirect(url_for('notice.list_notices'))

    return render_template('notice_form.html', action='edit', notice=notice)


@notice_bp.route('/notices/<int:notice_id>/delete', methods=['POST'])
@login_required
def delete(notice_id):
    notice = Notice.query.get_or_404(notice_id)
    if current_user.role.name not in ['Admin', 'Teacher'] or (current_user.role.name == 'Teacher' and notice.author_id != current_user.id):
        abort(403)
    db.session.delete(notice)
    db.session.commit()
    flash('Notice deleted.', 'success')
    return redirect(url_for('notice.list_notices'))


@notice_bp.route('/notifications')
@login_required
def notifications():
    status = request.args.get('status', 'all')
    if status not in ('all', 'unread'):
        status = 'all'

    query = Notification.query.filter_by(user_id=current_user.id)
    if status == 'unread':
        query = query.filter_by(is_read=False)

    page = request.args.get('page', 1, type=int)
    pagination = query.order_by(
        Notification.created_at.desc()
    ).paginate(page=page, per_page=20, error_out=False)

    unread_count = Notification.query.filter_by(
        user_id=current_user.id, is_read=False
    ).count()

    return render_template(
        'notifications.html',
        notifications=pagination.items,
        pagination=pagination,
        status=status,
        unread_count=unread_count,
    )


@notice_bp.route('/notifications/<int:notif_id>/read', methods=['POST'])
@login_required
def mark_notification_read(notif_id):
    notification = Notification.query.filter_by(
        id=notif_id, user_id=current_user.id
    ).first_or_404()
    notification.is_read = True
    db.session.commit()
    return redirect(request.referrer or url_for('notice.notifications'))


@notice_bp.route('/notifications/read-all', methods=['POST'])
@login_required
def mark_all_notifications_read():
    Notification.query.filter_by(
        user_id=current_user.id, is_read=False
    ).update({'is_read': True}, synchronize_session=False)
    db.session.commit()
    flash('All notifications marked as read.', 'success')
    return redirect(url_for('notice.notifications'))
