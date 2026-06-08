import re
from datetime import datetime, timedelta
from functools import wraps
from flask import Blueprint, render_template, redirect, url_for, flash, abort, request, current_app
from flask_login import login_required, current_user
from database import db
from models.user import User, Role, UserProfile
from models.course import Course, Category, Review
from models.learning import Enrollment, Quiz, QuizAttempt, Submission, Assignment, LessonProgress, LiveClass
from models.evaluation import Evaluation, EvaluationSubmission
from models.interaction import (Certificate, Payment, Notification, MembershipPlan, UserSubscription,
                                DiscussionTopic, DiscussionReply, Attendance, Notice, Lab,
                                PasswordResetRequest, PasswordResetToken)

dashboard_bp = Blueprint('dashboard', __name__)


def role_required(*role_names):
    def decorator(f):
        @wraps(f)
        @login_required
        def decorated_function(*args, **kwargs):
            if current_user.role.name not in role_names:
                flash('Access unauthorized.', 'danger')
                return redirect(url_for('main.home'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator


@dashboard_bp.route('/dashboard/student')
@role_required('Student')
def student():
    enrollments = Enrollment.query.filter_by(student_id=current_user.id).all()
    certificates = Certificate.query.filter_by(student_id=current_user.id).all()
    quiz_attempts = QuizAttempt.query.filter_by(student_id=current_user.id).all()
    submissions = Submission.query.filter_by(student_id=current_user.id).all()
    pending_payments = Payment.query.filter_by(student_id=current_user.id, status='pending').all()

    badges = []
    if len(enrollments) > 0:
        badges.append({'name': 'First Step', 'description': 'Enrolled in your first course', 'icon': 'fa-book-open', 'color': '#3b82f6'})
    if any(e.is_completed for e in enrollments):
        badges.append({'name': 'Graduate', 'description': 'Completed at least one course', 'icon': 'fa-graduation-cap', 'color': '#10b981'})
    if current_user.streak_count >= 3:
        badges.append({'name': 'Consistent Learner', 'description': 'Achieved a 3-day learning streak', 'icon': 'fa-fire', 'color': '#f59e0b'})
    if len(quiz_attempts) >= 3:
        badges.append({'name': 'Quiz Whiz', 'description': 'Attempted 3 or more quizzes', 'icon': 'fa-trophy', 'color': '#8b5cf6'})

    return render_template(
        'student_dashboard.html',
        enrollments=enrollments,
        certificates=certificates,
        quiz_attempts=quiz_attempts,
        submissions=submissions,
        pending_payments=pending_payments,
        badges=badges
    )


@dashboard_bp.route('/dashboard/teacher')
@role_required('Teacher')
def teacher():
    my_courses = Course.query.filter_by(teacher_id=current_user.id).all()
    course_ids = [c.id for c in my_courses]

    total_students = Enrollment.query.filter(Enrollment.course_id.in_(course_ids)).count() if course_ids else 0
    total_reviews = Review.query.filter(Review.course_id.in_(course_ids)).count() if course_ids else 0
    avg_rating = db.session.query(db.func.avg(Review.rating)).filter(Review.course_id.in_(course_ids)).scalar() if course_ids else 0.0
    avg_rating = round(avg_rating or 0.0, 1)

    pending_submissions = Submission.query.join(Assignment).filter(
        Assignment.course_id.in_(course_ids),
        Submission.is_graded == False
    ).all() if course_ids else []

    enrollments_by_course = {}
    for cid in course_ids:
        enrollments_by_course[cid] = Enrollment.query.filter_by(course_id=cid).all()

    quiz_attempts = QuizAttempt.query.join(Quiz).filter(
        Quiz.course_id.in_(course_ids)
    ).order_by(QuizAttempt.started_at.desc()).all() if course_ids else []

    quiz_attempts_by_quiz = {}
    for att in quiz_attempts:
        qid = att.quiz_id
        if qid not in quiz_attempts_by_quiz:
            quiz_attempts_by_quiz[qid] = {'title': att.quiz.title, 'attempts': []}
        quiz_attempts_by_quiz[qid]['attempts'].append(att)

    categories = Category.query.all()

    return render_template(
        'teacher_dashboard.html',
        courses=my_courses,
        total_students=total_students,
        total_reviews=total_reviews,
        avg_rating=avg_rating,
        pending_submissions=pending_submissions,
        enrollments_by_course=enrollments_by_course,
        quiz_attempts_by_quiz=quiz_attempts_by_quiz,
        categories=categories
    )


@dashboard_bp.route('/dashboard/admin')
@role_required('Admin')
def admin():
    page = request.args.get('page', 1, type=int)
    per_page = 10

    users_pagination = User.query.order_by(User.created_at.desc()).paginate(page=page, per_page=per_page, error_out=False)
    users = users_pagination.items
    courses = Course.query.all()
    categories = Category.query.all()

    total_sales = db.session.query(db.func.sum(Payment.amount)).scalar() or 0.0
    unapproved_teachers = User.query.join(User.role).filter(
        User.role.has(name='Teacher'), User.is_approved == False
    ).all()

    unpublished_courses = Course.query.filter_by(is_published=False).all()
    pending_payments = Payment.query.filter_by(status='pending').all()

    stats = {
        'total_users': User.query.count(),
        'total_courses': len(courses),
        'total_categories': len(categories),
        'total_sales': total_sales,
        'unapproved_teachers': unapproved_teachers,
        'unpublished_courses': unpublished_courses,
        'pending_payments': pending_payments
    }

    return render_template(
        'admin_dashboard.html',
        users=users,
        users_pagination=users_pagination,
        courses=courses,
        categories=categories,
        stats=stats,
        unpublished_courses=unpublished_courses,
        pending_payments=pending_payments
    )


@dashboard_bp.route('/dashboard/admin/bulk-import-users', methods=['GET', 'POST'])
@role_required('Admin')
def admin_bulk_import_users():
    if request.method == 'POST':
        file = request.files.get('csv_file')
        if not file or not file.filename:
            flash('Please upload a CSV file.', 'danger')
            return render_template('admin_bulk_import.html')

        import csv
        import io

        stream = io.StringIO(file.stream.read().decode('utf-8-sig'))
        reader = csv.DictReader(stream)

        required = {'username', 'email', 'password'}
        if not reader.fieldnames or not required.issubset(reader.fieldnames):
            flash('CSV must have columns: username, email, password, full_name (optional), role (optional)', 'danger')
            return render_template('admin_bulk_import.html')

        created = 0
        errors = []

        for i, row in enumerate(reader, start=2):
            username = row.get('username', '').strip()
            email = row.get('email', '').strip()
            password = row.get('password', '').strip()
            full_name = row.get('full_name', '').strip()
            role_name = row.get('role', 'Student').strip()

            if not username or not email or not password:
                errors.append(f"Row {i}: username, email, and password are required")
                continue

            if User.query.filter((User.username == username) | (User.email == email)).first():
                errors.append(f"Row {i}: '{username}' / '{email}' already exists")
                continue

            role = Role.query.filter_by(name=role_name).first()
            if not role:
                errors.append(f"Row {i}: invalid role '{role_name}' (use: Student, Teacher, Admin)")
                continue

            user = User(
                username=username,
                email=email,
                full_name=full_name or None,
                role=role,
                is_approved=(role_name == 'Student')
            )
            user.set_password(password)
            db.session.add(user)
            db.session.flush()

            profile = UserProfile(user_id=user.id)
            db.session.add(profile)
            created += 1

        db.session.commit()

        msg = f'Successfully created {created} user(s).'
        if errors:
            msg += f' {len(errors)} error(s): ' + '; '.join(errors[:5])
            if len(errors) > 5:
                msg += f' (and {len(errors) - 5} more)'
        flash(msg, 'success' if not errors else 'warning')
        return redirect(url_for('dashboard.admin_bulk_import_users'))

    return render_template('admin_bulk_import.html')


@dashboard_bp.route('/dashboard/admin/add-category', methods=['POST'])
@role_required('Admin')
def add_category():
    name = request.form.get('name', '').strip()
    icon = request.form.get('icon', 'fa-graduation-cap').strip()
    if not name:
        flash('Category name is required.', 'danger')
        return redirect(url_for('dashboard.admin'))

    slug = name.lower().replace(' ', '-').replace('/', '-')
    slug = re.sub(r'[^a-z0-9-]', '', slug)

    if Category.query.filter_by(name=name).first():
        flash(f'Category "{name}" already exists.', 'danger')
        return redirect(url_for('dashboard.admin'))

    cat = Category(name=name, slug=slug, icon_class=icon)
    db.session.add(cat)
    db.session.commit()
    flash(f'Category "{name}" created.', 'success')
    return redirect(url_for('dashboard.admin'))


@dashboard_bp.route('/dashboard/admin/approve-teacher/<int:user_id>')
@role_required('Admin')
def approve_teacher(user_id):
    user = User.query.get_or_404(user_id)
    user.is_approved = True
    db.session.commit()
    flash(f'Teacher {user.username} approved successfully.', 'success')
    return redirect(url_for('dashboard.admin'))


@dashboard_bp.route('/dashboard/admin/approve-course/<int:course_id>')
@role_required('Admin')
def approve_course(course_id):
    course = Course.query.get_or_404(course_id)
    course.is_published = True
    notif = Notification(
        user_id=course.teacher_id,
        title="Course Approved!",
        message=f'Your course "{course.title}" has been approved and is now live for students.',
        notif_type="success"
    )
    db.session.add(notif)
    db.session.commit()
    flash(f'Course "{course.title}" published successfully.', 'success')
    return redirect(url_for('dashboard.admin'))


@dashboard_bp.route('/dashboard/admin/approve-payment/<int:payment_id>')
@role_required('Admin')
def approve_payment(payment_id):
    payment = Payment.query.get_or_404(payment_id)
    if payment.status != 'pending':
        flash('Payment already processed.', 'info')
        return redirect(url_for('dashboard.admin'))

    payment.status = 'completed'

    course = Course.query.get(payment.course_id)

    if course:
        existing = Enrollment.query.filter_by(student_id=payment.student_id, course_id=course.id).first()
        if not existing:
            enrollment = Enrollment(student_id=payment.student_id, course_id=course.id)
            db.session.add(enrollment)
            db.session.flush()
            for m in course.modules:
                for l in m.lessons:
                    db.session.add(LessonProgress(enrollment_id=enrollment.id, lesson_id=l.id))

        msg = f'Your payment of Rs. {payment.amount:,.0f} for "{course.title}" has been verified. You now have full access!'
    elif payment.membership_plan_id:
        plan = MembershipPlan.query.get(payment.membership_plan_id)
        existing_sub = UserSubscription.query.filter_by(user_id=payment.student_id, is_active=True).first()
        if existing_sub:
            existing_sub.is_active = False
        sub = UserSubscription(
            user_id=payment.student_id,
            plan_id=plan.id,
            payment_id=payment.id,
            start_date=datetime.utcnow(),
            end_date=datetime.utcnow() + timedelta(days=plan.duration_days),
            is_active=True
        )
        db.session.add(sub)
        msg = f'Your {plan.name} membership is now active!'
    else:
        flash('Unknown payment type.', 'danger')
        return redirect(url_for('dashboard.admin'))

    notif = Notification(
        user_id=payment.student_id,
        title="Payment Verified!",
        message=msg,
        notif_type="success"
    )
    db.session.add(notif)
    db.session.commit()

    flash(f'Payment verified. Access granted.', 'success')
    return redirect(url_for('dashboard.admin'))


@dashboard_bp.route('/dashboard/admin/delete-user/<int:user_id>', methods=['POST'])
@role_required('Admin')
def delete_user(user_id):
    user = User.query.get_or_404(user_id)
    if user.role.name == 'Admin':
        flash('Cannot delete admin accounts.', 'danger')
        return redirect(url_for('dashboard.admin'))

    try:
        uid = user.id

        EvaluationSubmission.query.filter(
            (EvaluationSubmission.student_id == uid) | (EvaluationSubmission.graded_by == uid)
        ).delete(synchronize_session=False)

        Evaluation.query.filter_by(created_by=uid).delete(synchronize_session=False)

        QuizAttempt.query.filter_by(student_id=uid).delete(synchronize_session=False)
        Certificate.query.filter_by(student_id=uid).delete(synchronize_session=False)
        Attendance.query.filter_by(student_id=uid).delete(synchronize_session=False)
        Payment.query.filter_by(student_id=uid).delete(synchronize_session=False)
        DiscussionTopic.query.filter_by(user_id=uid).delete(synchronize_session=False)
        DiscussionReply.query.filter_by(user_id=uid).delete(synchronize_session=False)
        LiveClass.query.filter_by(teacher_id=uid).delete(synchronize_session=False)
        Submission.query.filter_by(student_id=uid).delete(synchronize_session=False)
        Review.query.filter_by(student_id=uid).delete(synchronize_session=False)
        Enrollment.query.filter_by(student_id=uid).delete(synchronize_session=False)
        Notice.query.filter_by(author_id=uid).delete(synchronize_session=False)
        Lab.query.filter_by(created_by=uid).delete(synchronize_session=False)
        UserSubscription.query.filter_by(user_id=uid).delete(synchronize_session=False)
        PasswordResetRequest.query.filter_by(user_id=uid).delete(synchronize_session=False)
        PasswordResetToken.query.filter_by(user_id=uid).delete(synchronize_session=False)

        PasswordResetRequest.query.filter_by(resolved_by=uid).update(
            {'resolved_by': None}, synchronize_session=False
        )

        for c in Course.query.filter_by(teacher_id=uid).all():
            db.session.delete(c)

        db.session.delete(user)
        db.session.commit()
        flash(f'User {user.username} deleted.', 'success')
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'Failed to delete user {user_id}: {e}')
        flash(f'Failed to delete user: {e}', 'danger')

    return redirect(url_for('dashboard.admin'))
