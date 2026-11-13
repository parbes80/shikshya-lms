import re, io
from datetime import datetime, timedelta
from functools import wraps
from sqlalchemy import desc
from flask import Blueprint, render_template, redirect, url_for, flash, abort, request, current_app, send_file
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
@login_required
def student():
    now = datetime.utcnow()
    enrollments = Enrollment.query.filter_by(student_id=current_user.id).all()
    course_ids = [enr.course_id for enr in enrollments]
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

    # Continue learning: prefer the course with the most recent lesson activity.
    continue_enrollment = None
    recent_progress = None
    if enrollments:
        recent_progress = (
            LessonProgress.query
            .join(Enrollment, LessonProgress.enrollment_id == Enrollment.id)
            .filter(Enrollment.student_id == current_user.id)
            .order_by(LessonProgress.updated_at.desc())
            .first()
        )
        continue_enrollment = (
            recent_progress.enrollment if recent_progress else enrollments[0]
        )

    next_lesson = None
    if continue_enrollment:
        completed_lesson_ids = {
            progress.lesson_id
            for progress in LessonProgress.query.filter_by(
                enrollment_id=continue_enrollment.id, is_completed=True
            ).all()
        }
        for module in continue_enrollment.course.modules:
            for lesson in module.lessons:
                if lesson.id not in completed_lesson_ids:
                    next_lesson = lesson
                    break
            if next_lesson:
                break

    # Upcoming work in the student's courses.
    upcoming_assignments = []
    if course_ids:
        submitted_assignment_ids = {sub.assignment_id for sub in submissions}
        assignment_query = Assignment.query.filter(
            Assignment.course_id.in_(course_ids),
            Assignment.due_date >= now,
        )
        if submitted_assignment_ids:
            assignment_query = assignment_query.filter(
                ~Assignment.id.in_(submitted_assignment_ids)
            )
        upcoming_assignments = assignment_query.order_by(
            Assignment.due_date.asc()
        ).limit(5).all()

    upcoming_evaluations = []
    if course_ids:
        eval_submitted_ids = {
            sub.evaluation_id
            for sub in EvaluationSubmission.query.filter_by(
                student_id=current_user.id
            ).all()
        }
        evaluation_query = Evaluation.query.filter(
            Evaluation.course_id.in_(course_ids),
            db.or_(
                Evaluation.scheduled_at.is_(None),
                Evaluation.scheduled_at >= now,
            ),
        )
        if eval_submitted_ids:
            evaluation_query = evaluation_query.filter(
                ~Evaluation.id.in_(eval_submitted_ids)
            )
        upcoming_evaluations = evaluation_query.order_by(
            Evaluation.scheduled_at.is_(None), Evaluation.scheduled_at.asc()
        ).limit(5).all()

    announcements = Notice.query.filter(
        db.or_(Notice.target_role == 'all', Notice.target_role == 'student')
    ).order_by(
        Notice.is_pinned.desc(), Notice.created_at.desc()
    ).limit(4).all()

    enrolled_ids = set(course_ids)
    recommended_query = Course.query.filter(Course.is_published.is_(True))
    if enrolled_ids:
        recommended_query = recommended_query.filter(
            ~Course.id.in_(enrolled_ids)
        )
    recommended_courses = recommended_query.order_by(
        Course.created_at.desc()
    ).limit(3).all()

    return render_template(
        'student_dashboard.html',
        enrollments=enrollments,
        certificates=certificates,
        quiz_attempts=quiz_attempts,
        submissions=submissions,
        pending_payments=pending_payments,
        badges=badges,
        continue_enrollment=continue_enrollment,
        next_lesson=next_lesson,
        upcoming_assignments=upcoming_assignments,
        upcoming_evaluations=upcoming_evaluations,
        announcements=announcements,
        recommended_courses=recommended_courses,
        pending_submissions_count=sum(
            1 for sub in submissions if not sub.is_graded
        ),
    )


@dashboard_bp.route('/dashboard/student/gradebook')
@login_required
def student_gradebook():
    enrollments = Enrollment.query.filter_by(student_id=current_user.id).all()
    gradebook_data = []

    for enr in enrollments:
        course = enr.course
        quizzes = Quiz.query.filter_by(course_id=course.id).all()
        quiz_results = []
        for q in quizzes:
            attempts = QuizAttempt.query.filter_by(quiz_id=q.id, student_id=current_user.id).order_by(QuizAttempt.completed_at.desc()).all()
            best = max(attempts, key=lambda a: a.score) if attempts else None
            quiz_results.append({
                'title': q.title,
                'attempts': len(attempts),
                'best_score': round(best.score, 1) if best else None,
                'passed': best.is_passed if best else None
            })

        assignments = Assignment.query.filter_by(course_id=course.id).all()
        assign_results = []
        for a in assignments:
            sub = Submission.query.filter_by(assignment_id=a.id, student_id=current_user.id).first()
            assign_results.append({
                'title': a.title,
                'max_marks': a.max_marks,
                'submitted': sub is not None,
                'marks': sub.marks_obtained if sub and sub.is_graded else None,
                'graded': sub.is_graded if sub else False
            })

        gradebook_data.append({
            'course': course,
            'enrollment': enr,
            'quiz_results': quiz_results,
            'assign_results': assign_results
        })

    return render_template('student_gradebook.html', gradebook_data=gradebook_data)


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

    now = datetime.utcnow()
    upcoming_evaluations = []
    upcoming_live_classes = []
    recent_submissions = []
    recent_activity = []
    attendance_stats = []
    course_stats = []

    if course_ids:
        upcoming_evaluations = Evaluation.query.filter(
            Evaluation.course_id.in_(course_ids),
            db.or_(
                Evaluation.scheduled_at.is_(None),
                Evaluation.scheduled_at >= now,
            ),
        ).order_by(
            Evaluation.scheduled_at.is_(None), Evaluation.scheduled_at.asc()
        ).limit(5).all()

        upcoming_live_classes = LiveClass.query.filter(
            LiveClass.course_id.in_(course_ids),
            LiveClass.start_time >= now,
        ).order_by(LiveClass.start_time.asc()).limit(5).all()

        recent_submissions = Submission.query.join(Assignment).filter(
            Assignment.course_id.in_(course_ids),
            Submission.is_graded.is_(False),
        ).order_by(Submission.submitted_at.desc()).limit(5).all()

        recent_activity = Submission.query.join(Assignment).filter(
            Assignment.course_id.in_(course_ids),
        ).order_by(Submission.submitted_at.desc()).limit(6).all()

        for course in my_courses:
            records = Attendance.query.filter_by(course_id=course.id).all()
            present = sum(1 for record in records if record.is_present)
            attendance_stats.append({
                'course': course,
                'records': len(records),
                'present': present,
                'rate': round(present / len(records) * 100) if records else None,
            })

    total_assignments = sum(len(course.assignments) for course in my_courses)
    total_quizzes = sum(len(course.quizzes) for course in my_courses)

    for course in my_courses:
        course_enrollments = enrollments_by_course.get(course.id, [])
        enrolled_count = len(course_enrollments)
        completed_count = sum(
            1 for enrollment in course_enrollments if enrollment.is_completed
        )
        average_progress = (
            round(
                sum(enrollment.progress_percent for enrollment in course_enrollments)
                / enrolled_count,
                1,
            )
            if enrolled_count else 0
        )
        course_stats.append({
            'course': course,
            'enrolled': enrolled_count,
            'completed': completed_count,
            'average_progress': average_progress,
        })

    return render_template(
        'teacher_dashboard.html',
        courses=my_courses,
        total_students=total_students,
        total_reviews=total_reviews,
        avg_rating=avg_rating,
        pending_submissions=pending_submissions,
        pending_submissions_count=len(pending_submissions),
        enrollments_by_course=enrollments_by_course,
        quiz_attempts_by_quiz=quiz_attempts_by_quiz,
        categories=categories,
        published_courses_count=sum(
            1 for course in my_courses if course.is_published
        ),
        upcoming_evaluations=upcoming_evaluations,
        upcoming_live_classes=upcoming_live_classes,
        recent_submissions=recent_submissions,
        recent_activity=recent_activity,
        attendance_stats=attendance_stats,
        total_assignments=total_assignments,
        total_quizzes=total_quizzes,
        course_stats=course_stats,
    )


@dashboard_bp.route('/dashboard/admin')
@role_required('Admin')
def admin():
    page = request.args.get('page', 1, type=int)
    per_page = 10
    search_query = request.args.get('q', '', type=str).strip()

    users_query = User.query
    if search_query:
        like = f'%{search_query}%'
        users_query = users_query.filter(
            db.or_(
                User.username.ilike(like),
                User.email.ilike(like),
                User.full_name.ilike(like),
            )
        )

    users_pagination = users_query.order_by(
        User.created_at.desc()
    ).paginate(page=page, per_page=per_page, error_out=False)
    users = users_pagination.items
    courses = Course.query.all()
    categories = Category.query.all()

    total_sales = db.session.query(db.func.sum(Payment.amount)).scalar() or 0.0
    unapproved_teachers = User.query.join(User.role).filter(
        User.role.has(name='Teacher'), User.is_approved == False
    ).all()

    unpublished_courses = Course.query.filter_by(is_published=False).all()
    pending_payments = Payment.query.filter_by(status='pending').all()

    role_counts = dict(
        db.session.query(Role.name, db.func.count(User.id))
        .join(User, User.role_id == Role.id)
        .group_by(Role.name)
        .all()
    )
    total_enrollments = Enrollment.query.count()
    total_certificates = Certificate.query.count()
    published_courses = Course.query.filter_by(is_published=True).count()
    recent_notices = Notice.query.order_by(Notice.created_at.desc()).limit(5).all()
    active_since = (datetime.utcnow() - timedelta(days=7)).date()
    active_users = User.query.filter(
        User.last_activity_date.isnot(None),
        User.last_activity_date >= active_since,
    ).count()

    stats = {
        'total_users': User.query.count(),
        'total_courses': len(courses),
        'total_categories': len(categories),
        'total_sales': total_sales,
        'unapproved_teachers': unapproved_teachers,
        'unpublished_courses': unpublished_courses,
        'pending_payments': pending_payments,
        'students': role_counts.get('Student', 0),
        'teachers': role_counts.get('Teacher', 0),
        'admins': role_counts.get('Admin', 0),
        'total_enrollments': total_enrollments,
        'total_certificates': total_certificates,
        'published_courses': published_courses,
        'pending_teacher_count': len(unapproved_teachers),
        'pending_payment_count': len(pending_payments),
        'active_users': active_users,
    }

    return render_template(
        'admin_dashboard.html',
        users=users,
        users_pagination=users_pagination,
        courses=courses,
        categories=categories,
        stats=stats,
        unpublished_courses=unpublished_courses,
        pending_payments=pending_payments,
        recent_notices=recent_notices,
        search_query=search_query,
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


@dashboard_bp.route('/dashboard/admin/approve-teacher/<int:user_id>', methods=['POST'])
@role_required('Admin')
def approve_teacher(user_id):
    user = User.query.get_or_404(user_id)
    user.is_approved = True
    db.session.commit()
    flash(f'Teacher {user.username} approved successfully.', 'success')
    return redirect(url_for('dashboard.admin'))


@dashboard_bp.route('/dashboard/admin/approve-course/<int:course_id>', methods=['POST'])
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


@dashboard_bp.route('/dashboard/admin/approve-payment/<int:payment_id>', methods=['POST'])
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


@dashboard_bp.route('/dashboard/teacher/analytics/<int:course_id>')
@login_required
def teacher_analytics(course_id):
    if current_user.role.name not in ('Teacher', 'Admin'):
        abort(403)

    course = Course.query.get_or_404(course_id)
    if course.teacher_id != current_user.id and current_user.role.name != 'Admin':
        abort(403)

    enrollments = Enrollment.query.filter_by(course_id=course.id).all()
    total_students = len(enrollments)
    completed_count = sum(1 for e in enrollments if e.is_completed)
    avg_progress = round(sum(e.progress_percent for e in enrollments) / total_students, 1) if enrollments else 0

    # per-lesson stats
    lesson_stats = []
    for m in course.modules:
        for les in m.lessons:
            total = LessonProgress.query.filter(
                LessonProgress.lesson_id == les.id,
                LessonProgress.enrollment_id.in_([e.id for e in enrollments])
            ).count()
            completed = LessonProgress.query.filter(
                LessonProgress.lesson_id == les.id,
                LessonProgress.is_completed == True,
                LessonProgress.enrollment_id.in_([e.id for e in enrollments])
            ).count()
            lesson_stats.append({
                'module_title': m.title,
                'lesson': les,
                'enrolled': total,
                'completed': completed,
                'stuck': total - completed
            })

    # per-quiz stats
    quizzes = Quiz.query.filter_by(course_id=course.id).all()
    quiz_stats = []
    for q in quizzes:
        attempts = QuizAttempt.query.filter_by(quiz_id=q.id).all()
        total_attempts = len(attempts)
        passed = sum(1 for a in attempts if a.is_passed)
        avg_score = round(sum(a.score for a in attempts) / total_attempts, 1) if attempts else 0
        unique_students = len(set(a.student_id for a in attempts))
        quiz_stats.append({
            'quiz': q,
            'total_attempts': total_attempts,
            'unique_students': unique_students,
            'passed': passed,
            'avg_score': avg_score,
            'pass_rate': round(passed / total_attempts * 100, 1) if attempts else 0
        })

    # recent activity
    recent_attempts = QuizAttempt.query.join(Quiz).filter(
        Quiz.course_id == course.id
    ).order_by(desc(QuizAttempt.completed_at)).limit(10).all()

    return render_template(
        'teacher_analytics.html',
        course=course,
        total_students=total_students,
        completed_count=completed_count,
        avg_progress=avg_progress,
        lesson_stats=lesson_stats,
        quiz_stats=quiz_stats,
        recent_attempts=recent_attempts
    )


@dashboard_bp.route('/dashboard/teacher/analytics/<int:course_id>/export-csv')
@login_required
def teacher_analytics_export(course_id):
    if current_user.role.name not in ('Teacher', 'Admin'):
        abort(403)
    course = Course.query.get_or_404(course_id)
    if course.teacher_id != current_user.id and current_user.role.name != 'Admin':
        abort(403)

    import csv, io
    enrollments = Enrollment.query.filter_by(course_id=course.id).all()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Student', 'Email', 'Progress %', 'Completed', 'Enrolled At'])

    for e in enrollments:
        writer.writerow([
            e.student.username,
            e.student.email,
            e.progress_percent,
            'Yes' if e.is_completed else 'No',
            e.enrolled_at.strftime('%Y-%m-%d') if e.enrolled_at else ''
        ])

    # per-lesson breakdown
    writer.writerow([])
    writer.writerow(['Lesson Progress'])
    writer.writerow(['Student'] + [les.title for m in course.modules for les in m.lessons])
    for e in enrollments:
        row = [e.student.username]
        for m in course.modules:
            for les in m.lessons:
                lp = LessonProgress.query.filter_by(enrollment_id=e.id, lesson_id=les.id).first()
                row.append('Completed' if lp and lp.is_completed else 'Pending')
        writer.writerow(row)

    csv_bytes = output.getvalue().encode('utf-8-sig')
    return send_file(
        io.BytesIO(csv_bytes),
        mimetype='text/csv',
        as_attachment=True,
        download_name=f'{course.slug}_progress.csv'
    )
