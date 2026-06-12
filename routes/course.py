import os
import re
import uuid
from datetime import datetime
from werkzeug.utils import secure_filename
from flask import Blueprint, render_template, redirect, url_for, flash, request, abort, current_app
from flask_login import login_required, current_user
from database import db
from models.course import Course, Category, Module, Lesson, Review
from models.learning import Enrollment, LessonProgress, Quiz, Question, Choice, Assignment, LiveClass
from models.interaction import Payment, DiscussionTopic, Attendance, Coupon, Notification, LabManual
from utils.cloudinary_upload import upload_file
from utils.mail import send_notification_email

course_bp = Blueprint('course', __name__)


def notify_enrolled_students(course, title, message):
    """Send in-app notification and email to all enrolled students."""
    enrollments = Enrollment.query.filter_by(course_id=course.id).all()
    for enr in enrollments:
        user = enr.student
        notif = Notification(
            user_id=user.id,
            title=title,
            message=message,
            notif_type='info'
        )
        db.session.add(notif)
        try:
            send_notification_email(user, title, message)
        except Exception:
            pass
    db.session.commit()


def process_lesson_headings(text_content):
    """
    Extract headings from HTML content, add id anchors, and return
    (processed_html, headings_list) where headings_list is
    [(id, text, level), ...].
    """
    if not text_content:
        return text_content, []

    headings = []
    seen = {}

    def _heading_replacer(m):
        tag = f'h{m.group(1)}'
        content = m.group(3).strip()
        # strip any nested HTML from heading text for the id
        plain = re.sub(r'<[^>]+>', '', content)
        base_id = re.sub(r'[^a-zA-Z0-9\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff]+', '-', plain.lower()).strip('-')
        if not base_id:
            base_id = 'heading'
        count = seen.get(base_id, 0)
        seen[base_id] = count + 1
        unique_id = f'{base_id}-{count}' if count else base_id
        headings.append((unique_id, plain, tag))
        return f'<{tag} id="{unique_id}">{m.group(3)}</{tag}>'

    processed = re.sub(
        r'<h([1-6])(\s[^>]*)?>(.*?)</h\1>',
        _heading_replacer,
        text_content,
        flags=re.IGNORECASE | re.DOTALL
    )
    return processed, headings


def slugify(text):
    text = text.lower().strip()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[-\s]+', '-', text)
    return text.strip('-')


@course_bp.route('/courses')
def index():
    query = request.args.get('q', '')
    cat_slug = request.args.get('category', '')
    difficulty = request.args.get('difficulty', '')

    courses_query = Course.query.filter_by(is_published=True)

    if query:
        courses_query = courses_query.filter(
            Course.title.ilike(f'%{query}%') |
            Course.description.ilike(f'%{query}%')
        )
    if cat_slug:
        courses_query = courses_query.join(Category).filter(Category.slug == cat_slug)
    if difficulty:
        courses_query = courses_query.filter(Course.difficulty_level == difficulty)

    courses = courses_query.all()
    categories = Category.query.all()
    return render_template('courses.html', courses=courses, categories=categories, query=query, cat_slug=cat_slug, difficulty=difficulty)


@course_bp.route('/courses/<int:course_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_course(course_id):
    course = Course.query.get_or_404(course_id)
    if current_user.role.name != 'Teacher' or course.teacher_id != current_user.id:
        abort(403)

    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        if not title:
            flash('Course title is required.', 'danger')
            return redirect(url_for('course.edit_course', course_id=course_id))

        course.title = title
        course.description = request.form.get('description', '').strip()
        course.price = float(request.form.get('price', 0))
        course.difficulty_level = request.form.get('difficulty_level', 'Beginner')
        course.category_id = int(request.form.get('category_id'))

        file = request.files.get('thumbnail_file')
        if file and file.filename:
            url = upload_file(file, folder='shikshya/courses', resource_type='image')
            if url:
                course.thumbnail_url = url

        db.session.commit()
        flash(f'Course "{course.title}" updated.', 'success')
        return redirect(url_for('dashboard.teacher'))

    categories = Category.query.all()
    return render_template('course_form.html', categories=categories, course=course, action='edit')


@course_bp.route('/courses/<slug>')
def details(slug):
    course = Course.query.filter_by(slug=slug).first_or_404()

    is_enrolled = False
    enrollment = None
    pending_payment = None
    if current_user.is_authenticated:
        if current_user.role.name == 'Admin':
            is_enrolled = True
        elif current_user.role.name == 'Teacher':
            enrollment = Enrollment.query.filter_by(student_id=current_user.id, course_id=course.id).first()
            is_enrolled = enrollment is not None or course.teacher_id == current_user.id
        else:
            enrollment = Enrollment.query.filter_by(student_id=current_user.id, course_id=course.id).first()
            is_enrolled = enrollment is not None
            if not is_enrolled:
                pending_payment = Payment.query.filter_by(
                    student_id=current_user.id, course_id=course.id, status='pending'
                ).first()

    reviews = Review.query.filter_by(course_id=course.id).all()
    avg_rating = round(sum(r.rating for r in reviews) / len(reviews), 1) if reviews else 0.0

    return render_template(
        'course_details.html',
        course=course,
        is_enrolled=is_enrolled,
        enrollment=enrollment,
        pending_payment=pending_payment,
        reviews=reviews,
        avg_rating=avg_rating
    )


@course_bp.route('/courses/<slug>/enroll', methods=['GET', 'POST'])
@login_required
def enroll(slug):
    course = Course.query.filter_by(slug=slug).first_or_404()

    if current_user.role.name == 'Admin':
        return redirect(url_for('course.player', slug=slug))

    if current_user.role.name == 'Teacher' and course.teacher_id == current_user.id:
        return redirect(url_for('course.player', slug=slug))

    existing = Enrollment.query.filter_by(student_id=current_user.id, course_id=course.id).first()
    if existing:
        flash('You are already enrolled in this course!', 'info')
        return redirect(url_for('course.player', slug=slug))

    if course.price == 0.0:
        new_enrollment = Enrollment(student_id=current_user.id, course_id=course.id)
        db.session.add(new_enrollment)
        db.session.flush()

        for m in course.modules:
            for l in m.lessons:
                prog = LessonProgress(enrollment_id=new_enrollment.id, lesson_id=l.id)
                db.session.add(prog)
        db.session.commit()

        flash(f'Successfully enrolled in {course.title}! Start learning now.', 'success')
        return redirect(url_for('course.player', slug=slug))

    if request.method == 'POST':
        method = request.form.get('payment_method')
        user_tx_id = request.form.get('transaction_id', '').strip()
        coupon_code = request.form.get('coupon_code', '').strip()

        if not method:
            flash('Please select a payment method.', 'danger')
            return render_template('checkout.html', course=course)

        if not user_tx_id:
            flash('Please enter the transaction ID from your payment app.', 'danger')
            return render_template('checkout.html', course=course)

        amount = course.price
        discount = 0.0
        coupon = None

        if coupon_code:
            coupon = Coupon.query.filter_by(code=coupon_code.upper(), is_active=True).first()
            if not coupon:
                flash('Invalid coupon code.', 'danger')
                return render_template('checkout.html', course=course)
            if coupon.expires_at and coupon.expires_at < datetime.utcnow():
                flash('This coupon has expired.', 'danger')
                return render_template('checkout.html', course=course)
            if coupon.current_uses >= coupon.max_uses:
                flash('This coupon has reached its usage limit.', 'danger')
                return render_template('checkout.html', course=course)
            if amount < coupon.min_amount:
                flash(f'Minimum Rs. {coupon.min_amount:,.0f} required.', 'danger')
                return render_template('checkout.html', course=course)
            discount = round(amount * coupon.discount_percent / 100, 2)
            coupon.current_uses += 1

        final_amount = round(amount - discount, 2)
        tx_id = f"TXN-{uuid.uuid4().hex[:10].upper()}"

        payment = Payment(
            student_id=current_user.id,
            course_id=course.id,
            amount=final_amount,
            discount_amount=discount,
            coupon_id=coupon.id if coupon else None,
            payment_method=method,
            transaction_id=tx_id,
            user_transaction_id=user_tx_id,
            description=f'Course: {course.title}',
            status='pending'
        )
        db.session.add(payment)
        db.session.commit()

        flash(f'Payment submitted! Amount: Rs. {final_amount:,.0f} via {method}. Admin will verify your payment and grant access shortly.', 'warning')
        return redirect(url_for('dashboard.student'))

    return render_template('checkout.html', course=course)


@course_bp.route('/courses/<slug>/player')
@login_required
def player(slug):
    course = Course.query.filter_by(slug=slug).first_or_404()

    is_teacher = current_user.role.name == 'Teacher' and course.teacher_id == current_user.id
    is_admin = current_user.role.name == 'Admin'

    if not is_admin and not is_teacher:
        enrollment = Enrollment.query.filter_by(student_id=current_user.id, course_id=course.id).first()
        if not enrollment:
            flash('Please enroll in the course to access lessons.', 'warning')
            return redirect(url_for('course.details', slug=slug))
    else:
        enrollment = None

    lesson_id = request.args.get('lesson_id', type=int)
    active_lesson = None
    now = datetime.now()

    progress_map = {p.lesson_id: p for p in enrollment.lesson_progresses} if enrollment else {}

    # helper: lesson is visible to students
    def is_lesson_visible(les):
        if is_admin or is_teacher:
            return True
        return les.publish_at is None or les.publish_at <= now

    if lesson_id:
        active_lesson = Lesson.query.get_or_404(lesson_id)
        # teachers/admin can view any lesson; students only if published
        if not is_admin and not is_teacher and not is_lesson_visible(active_lesson):
            flash('This lesson is not published yet.', 'warning')
            return redirect(url_for('course.player', slug=slug))
    else:
        for m in course.modules:
            for l in m.lessons:
                if not is_lesson_visible(l):
                    continue
                p = progress_map.get(l.id)
                if p and not p.is_completed:
                    active_lesson = l
                    break
            if active_lesson:
                break

        if not active_lesson:
            for m in course.modules:
                for l in m.lessons:
                    if is_lesson_visible(l):
                        active_lesson = l
                        break
                if active_lesson:
                    break

    active_progress = progress_map.get(active_lesson.id) if active_lesson else None

    # process lesson text for sub-topic navigation
    lesson_headings = []
    lesson_content_html = None
    if active_lesson and active_lesson.text_content:
        lesson_content_html, lesson_headings = process_lesson_headings(active_lesson.text_content)

    from sqlalchemy import or_

    discussions = DiscussionTopic.query.filter_by(course_id=course.id).order_by(DiscussionTopic.created_at.desc()).all()
    if active_lesson:
        quizzes = Quiz.query.filter(
            Quiz.course_id == course.id,
            or_(Quiz.lesson_id == None, Quiz.lesson_id == active_lesson.id)
        ).all()
    else:
        quizzes = Quiz.query.filter_by(course_id=course.id).all()
    assignments = Assignment.query.filter_by(course_id=course.id).all()
    live_classes = LiveClass.query.filter_by(course_id=course.id).order_by(LiveClass.start_time.desc()).all()
    lab_manuals = LabManual.query.filter_by(course_id=course.id).order_by(LabManual.sort_order).all()

    # compute quizzes grouped by lesson for sidebar
    all_quizzes = Quiz.query.filter_by(course_id=course.id).all()
    lesson_quizzes_map = {}
    lesson_quiz_counts = {}
    for q in all_quizzes:
        lid = q.lesson_id or 0
        lesson_quiz_counts[lid] = lesson_quiz_counts.get(lid, 0) + 1
        lesson_quizzes_map.setdefault(lid, []).append(q)

    # whether the active lesson is completed (for gating quizzes)
    lesson_completed = active_progress and active_progress.is_completed

    return render_template(
        'course_player.html',
        course=course,
        active_lesson=active_lesson,
        active_progress=active_progress,
        progress_map=progress_map,
        discussions=discussions,
        quizzes=quizzes,
        assignments=assignments,
        live_classes=live_classes,
        lab_manuals=lab_manuals,
        lesson_headings=lesson_headings,
        lesson_content_html=lesson_content_html,
        lesson_quiz_counts=lesson_quiz_counts,
        lesson_quizzes_map=lesson_quizzes_map,
        lesson_completed=lesson_completed,
        is_teacher=is_teacher,
        is_admin=is_admin,
        now=now
    )


@course_bp.route('/courses/create', methods=['GET', 'POST'])
@login_required
def create():
    if current_user.role.name != 'Teacher' or not current_user.is_approved:
        flash('Unauthorized. Only approved teachers can create courses.', 'danger')
        return redirect(url_for('dashboard.teacher'))

    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        if not title:
            flash('Course title is required.', 'danger')
            return redirect(url_for('course.create'))

        base_slug = slugify(title)
        slug = f"{base_slug}-{uuid.uuid4().hex[:4]}"

        description = request.form.get('description', '').strip()
        price = float(request.form.get('price', 0))
        difficulty = request.form.get('difficulty_level', 'Beginner')
        category_id = int(request.form.get('category_id'))

        thumbnail = 'course_default.jpg'
        file = request.files.get('thumbnail_file')
        if file and file.filename:
            url = upload_file(file, folder='shikshya/courses', resource_type='image')
            thumbnail = url if url else 'course_default.jpg'

        course = Course(
            title=title,
            slug=slug,
            description=description,
            price=price,
            difficulty_level=difficulty,
            category_id=category_id,
            teacher_id=current_user.id,
            thumbnail_url=thumbnail,
            is_published=False
        )
        db.session.add(course)

        notif = Notification(
            user_id=current_user.id,
            title="Course submitted for review",
            message=f'"{title}" has been submitted to admin for approval. You will be notified once it is published.',
            notif_type="info"
        )
        db.session.add(notif)

        db.session.commit()

        flash('Course created successfully! It is now pending admin approval.', 'warning')
        return redirect(url_for('dashboard.teacher'))

    categories = Category.query.all()
    return render_template('course_form.html', categories=categories, action='create')


@course_bp.route('/courses/<int:course_id>/add-module', methods=['POST'])
@login_required
def add_module(course_id):
    course = Course.query.get_or_404(course_id)
    if course.teacher_id != current_user.id:
        abort(403)

    title = request.form.get('module_title', '').strip()
    if not title:
        flash('Module title is required.', 'danger')
        return redirect(url_for('dashboard.teacher'))

    order = len(course.modules) + 1

    new_module = Module(course_id=course.id, title=title, sort_order=order)
    db.session.add(new_module)
    db.session.commit()

    flash('Module added successfully!', 'success')
    return redirect(url_for('dashboard.teacher'))


@course_bp.route('/modules/<int:module_id>/add-lesson', methods=['GET', 'POST'])
@login_required
def add_lesson(module_id):
    module = Module.query.get_or_404(module_id)
    if module.course.teacher_id != current_user.id:
        abort(403)

    if request.method == 'GET':
        return render_template('lesson_form.html', module=module, action='create')

    title = request.form.get('lesson_title', '').strip()
    if not title:
        flash('Lesson title is required.', 'danger')
        return redirect(url_for('dashboard.teacher'))

    content_type = request.form.get('content_type')
    video_url = request.form.get('video_url', '')
    document_url = request.form.get('document_url', '')
    # sanitize — Jinja can render None as "None" string
    if document_url and document_url.strip().lower() in ('none', 'null', ''):
        document_url = ''
    if video_url and video_url.strip().lower() in ('none', 'null', ''):
        video_url = ''
    duration = int(request.form.get('duration', 10))
    text_content = request.form.get('text_content', '')
    publish_at_raw = request.form.get('publish_at', '')

    file = request.files.get('document_file')
    if file and file.filename:
        from utils.cloudinary_upload import upload_file
        result = upload_file(file, folder='lesson_documents')
        if result:
            document_url = result

    order = len(module.lessons) + 1

    lesson = Lesson(
        module_id=module.id,
        title=title,
        content_type=content_type,
        video_url=video_url,
        document_url=document_url,
        text_content=text_content,
        sort_order=order,
        duration_minutes=duration
    )
    if publish_at_raw:
        try:
            lesson.publish_at = datetime.fromisoformat(publish_at_raw)
        except:
            pass
    db.session.add(lesson)
    db.session.commit()
    notify_enrolled_students(module.course, 'New Lesson Added', f'A new lesson "{lesson.title}" has been added to {module.course.title}.')

    flash('Lesson added successfully!', 'success')
    return redirect(url_for('dashboard.teacher'))


@course_bp.route('/lessons/<int:lesson_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_lesson(lesson_id):
    lesson = Lesson.query.get_or_404(lesson_id)
    if lesson.module.course.teacher_id != current_user.id:
        abort(403)

    if request.method == 'GET':
        return render_template('lesson_form.html', module=lesson.module, lesson=lesson, action='edit')

    title = request.form.get('lesson_title', '').strip()
    if not title:
        flash('Lesson title is required.', 'danger')
        return redirect(url_for('dashboard.teacher'))

    lesson.title = title
    lesson.content_type = request.form.get('content_type')
    lesson.video_url = request.form.get('video_url', '')
    lesson.document_url = request.form.get('document_url', '')
    # sanitize — Jinja can render None as "None" string
    if lesson.document_url and lesson.document_url.strip().lower() in ('none', 'null', ''):
        lesson.document_url = ''
    if lesson.video_url and lesson.video_url.strip().lower() in ('none', 'null', ''):
        lesson.video_url = ''
    lesson.duration_minutes = int(request.form.get('duration', 10))
    lesson.text_content = request.form.get('text_content', '')
    publish_at_raw = request.form.get('publish_at', '')
    if publish_at_raw:
        try:
            lesson.publish_at = datetime.fromisoformat(publish_at_raw)
        except:
            pass
    else:
        lesson.publish_at = None

    file = request.files.get('document_file')
    if file and file.filename:
        from utils.cloudinary_upload import upload_file
        result = upload_file(file, folder='lesson_documents')
        if result:
            lesson.document_url = result

    db.session.commit()

    flash('Lesson updated successfully!', 'success')
    return redirect(url_for('dashboard.teacher'))


@course_bp.route('/lessons/<int:lesson_id>/delete', methods=['POST'])
@login_required
def delete_lesson(lesson_id):
    lesson = Lesson.query.get_or_404(lesson_id)
    if lesson.module.course.teacher_id != current_user.id:
        abort(403)

    db.session.delete(lesson)
    db.session.commit()
    flash('Lesson deleted.', 'success')
    return redirect(url_for('dashboard.teacher'))


@course_bp.route('/courses/<int:course_id>/quiz/create', methods=['GET', 'POST'])
@login_required
def create_quiz(course_id):
    course = Course.query.get_or_404(course_id)
    if course.teacher_id != current_user.id:
        abort(403)

    from_eval = request.args.get('from_eval')
    eval_type = request.args.get('type', 'quiz')
    is_test_paper = eval_type == 'test_paper'
    redirect_back = url_for('eval.index', course_id=course_id) if from_eval else url_for('dashboard.teacher')
    label = 'Test Paper' if is_test_paper else 'Quiz'

    if request.method == 'POST':
        from_eval = request.form.get('from_eval')
        redirect_back = url_for('eval.index', course_id=course_id) if from_eval else url_for('dashboard.teacher')

        title = request.form.get('title', '').strip()
        time_limit = int(request.form.get('time_limit_minutes', 10))
        passing_score = int(request.form.get('passing_score', 60))
        max_attempts = int(request.form.get('max_attempts', 0))
        lesson_id = request.form.get('lesson_id', type=int)

        if not title:
            flash(f'{label} title is required.', 'danger')
            return redirect(url_for('course.create_quiz', course_id=course_id, from_eval=from_eval, type=eval_type))

        quiz = Quiz(
            course_id=course.id,
            lesson_id=lesson_id or None,
            title=title,
            time_limit_minutes=time_limit,
            passing_score=passing_score,
            max_attempts=max_attempts
        )
        db.session.add(quiz)
        db.session.flush()

        csv_file = request.files.get('csv_file')
        if csv_file and csv_file.filename:
            import csv, io
            raw = csv_file.stream.read()
            try:
                stream = io.StringIO(raw.decode('utf-8-sig'))
            except UnicodeDecodeError:
                stream = io.StringIO(raw.decode('latin-1'))
            reader = csv.DictReader(stream)
            # normalize column names: lowercase, strip, replace spaces with underscores
            reader.fieldnames = [fn.strip().lower().replace(' ', '_') for fn in reader.fieldnames]
            required_cols = {'question_text'}
            if not reader.fieldnames or not required_cols.issubset(reader.fieldnames):
                flash(f'CSV must have a "question_text" column. Found: {reader.fieldnames}', 'danger')
                return render_template('quiz_form.html', course=course, action='create',
                                       from_eval=from_eval, eval_type=eval_type,
                                       is_test_paper=is_test_paper, label=label, quiz=None,
                                       lessons=Lesson.query.filter(Lesson.module_id.in_([m.id for m in course.modules])).order_by(Lesson.sort_order).all())
            row_count = 0
            for row in reader:
                q_text = row.get('question_text', '').strip()
                if not q_text:
                    continue
                q_type = row.get('question_type', 'MCQ').strip()
                try:
                    points = int(row.get('points', 10))
                except (ValueError, TypeError):
                    points = 10
                question = Question(
                    quiz_id=quiz.id, text=q_text,
                    question_type=q_type, points=points
                )
                db.session.add(question)
                db.session.flush()
                choices = [row.get(f'choice_{k}', '').strip() for k in range(1, 5)]
                correct_raw = row.get('correct', '').strip()
                correct_idx = int(correct_raw) - 1 if correct_raw.isdigit() else -1
                for j, c_text in enumerate(choices):
                    if not c_text:
                        continue
                    db.session.add(Choice(
                        question_id=question.id, text=c_text,
                        is_correct=(j == correct_idx)
                    ))
                row_count += 1
            if row_count == 0:
                flash('No valid questions found in CSV. Check that "question_text" column has data.', 'warning')
            else:
                flash(f'Imported {row_count} question(s) from CSV.', 'success')
        else:
            question_texts = request.form.getlist('question_text[]')
            question_types = request.form.getlist('question_type[]')
            question_points = request.form.getlist('points[]')

            for i in range(len(question_texts)):
                q_text = question_texts[i].strip()
                if not q_text:
                    continue

                q_type = question_types[i] if i < len(question_types) else 'MCQ'
                points = int(question_points[i]) if i < len(question_points) else 10

                question = Question(
                    quiz_id=quiz.id,
                    text=q_text,
                    question_type=q_type,
                    points=points
                )
                db.session.add(question)
                db.session.flush()

                choice_texts = request.form.getlist(f'choice_text_{i}[]')
                correct_idx = request.form.get(f'correct_choice_{i}')
                for j in range(len(choice_texts)):
                    c_text = choice_texts[j].strip()
                    if not c_text:
                        continue
                    is_correct = (str(j) == correct_idx)
                    choice = Choice(
                        question_id=question.id,
                        text=c_text,
                        is_correct=is_correct
                    )
                    db.session.add(choice)

        db.session.commit()
        q_count = Question.query.filter_by(quiz_id=quiz.id).count()
        notify_enrolled_students(course, 'New Quiz Added', f'A new quiz "{quiz.title}" has been added to {course.title}.')
        flash(f'{label} "{quiz.title}" created with {q_count} questions!', 'success')
        return redirect(redirect_back)

    return render_template('quiz_form.html', course=course, action='create',
                           from_eval=from_eval, eval_type=eval_type,
                           is_test_paper=is_test_paper, label=label, quiz=None,
                           lessons=Lesson.query.filter(Lesson.module_id.in_([m.id for m in course.modules])).order_by(Lesson.sort_order).all())


@course_bp.route('/courses/<int:course_id>/quiz/<int:quiz_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_quiz(course_id, quiz_id):
    course = Course.query.get_or_404(course_id)
    quiz = Quiz.query.get_or_404(quiz_id)
    if course.teacher_id != current_user.id or quiz.course_id != course.id:
        abort(403)

    from_eval = request.args.get('from_eval')
    eval_type = request.args.get('type', 'quiz')
    is_test_paper = eval_type == 'test_paper'
    redirect_back = url_for('eval.index', course_id=course_id) if from_eval else url_for('dashboard.teacher')
    label = 'Test Paper' if is_test_paper else 'Quiz'

    if request.method == 'POST':
        from_eval = request.form.get('from_eval')
        redirect_back = url_for('eval.index', course_id=course_id) if from_eval else url_for('dashboard.teacher')

        title = request.form.get('title', '').strip()
        time_limit = int(request.form.get('time_limit_minutes', 10))
        passing_score = int(request.form.get('passing_score', 60))
        max_attempts = int(request.form.get('max_attempts', 0))
        lesson_id = request.form.get('lesson_id', type=int)

        if not title:
            flash(f'{label} title is required.', 'danger')
            return redirect(url_for('course.edit_quiz', course_id=course_id, quiz_id=quiz_id, from_eval=from_eval, type=eval_type))

        quiz.title = title
        quiz.time_limit_minutes = time_limit
        quiz.passing_score = passing_score
        quiz.max_attempts = max_attempts
        quiz.lesson_id = lesson_id or None

        for q in quiz.questions[:]:
            db.session.delete(q)
        db.session.flush()

        csv_file = request.files.get('csv_file')
        if csv_file and csv_file.filename:
            import csv, io
            raw = csv_file.stream.read()
            try:
                stream = io.StringIO(raw.decode('utf-8-sig'))
            except UnicodeDecodeError:
                stream = io.StringIO(raw.decode('latin-1'))
            reader = csv.DictReader(stream)
            reader.fieldnames = [fn.strip().lower().replace(' ', '_') for fn in reader.fieldnames]
            required_cols = {'question_text'}
            if not reader.fieldnames or not required_cols.issubset(reader.fieldnames):
                flash(f'CSV must have a "question_text" column. Found: {reader.fieldnames}', 'danger')
                return redirect(redirect_back)
            row_count = 0
            for row in reader:
                q_text = row.get('question_text', '').strip()
                if not q_text:
                    continue
                q_type = row.get('question_type', 'MCQ').strip()
                try:
                    points = int(row.get('points', 10))
                except (ValueError, TypeError):
                    points = 10
                question = Question(
                    quiz_id=quiz.id, text=q_text,
                    question_type=q_type, points=points
                )
                db.session.add(question)
                db.session.flush()
                choices = [row.get(f'choice_{k}', '').strip() for k in range(1, 5)]
                correct_raw = row.get('correct', '').strip()
                correct_idx = int(correct_raw) - 1 if correct_raw.isdigit() else -1
                for j, c_text in enumerate(choices):
                    if not c_text:
                        continue
                    db.session.add(Choice(
                        question_id=question.id, text=c_text,
                        is_correct=(j == correct_idx)
                    ))
                row_count += 1
            if row_count == 0:
                flash('No valid questions found in CSV. Check that "question_text" column has data.', 'warning')
            else:
                flash(f'Imported {row_count} question(s) from CSV.', 'success')
        else:
            question_texts = request.form.getlist('question_text[]')
            question_types = request.form.getlist('question_type[]')
            question_points = request.form.getlist('points[]')

            for i in range(len(question_texts)):
                q_text = question_texts[i].strip()
                if not q_text:
                    continue

                q_type = question_types[i] if i < len(question_types) else 'MCQ'
                points = int(question_points[i]) if i < len(question_points) else 10

                question = Question(
                    quiz_id=quiz.id,
                    text=q_text,
                    question_type=q_type,
                    points=points
                )
                db.session.add(question)
                db.session.flush()

                choice_texts = request.form.getlist(f'choice_text_{i}[]')
                correct_idx = request.form.get(f'correct_choice_{i}')
                for j in range(len(choice_texts)):
                    c_text = choice_texts[j].strip()
                    if not c_text:
                        continue
                    is_correct = (str(j) == correct_idx)
                    choice = Choice(
                        question_id=question.id,
                        text=c_text,
                        is_correct=is_correct
                    )
                    db.session.add(choice)

        db.session.commit()
        flash(f'{label} "{quiz.title}" updated!', 'success')
        return redirect(redirect_back)

    return render_template('quiz_form.html', course=course, quiz=quiz, action='edit',
                           from_eval=from_eval, eval_type=eval_type,
                           is_test_paper=is_test_paper, label=label,
                           lessons=Lesson.query.filter(Lesson.module_id.in_([m.id for m in course.modules])).order_by(Lesson.sort_order).all())


@course_bp.route('/courses/<int:course_id>/quiz/<int:quiz_id>/delete', methods=['POST'])
@login_required
def delete_quiz(course_id, quiz_id):
    course = Course.query.get_or_404(course_id)
    quiz = Quiz.query.get_or_404(quiz_id)
    if course.teacher_id != current_user.id or quiz.course_id != course.id:
        abort(403)

    db.session.delete(quiz)
    db.session.commit()
    flash(f'Quiz "{quiz.title}" deleted.', 'success')
    return redirect(url_for('dashboard.teacher'))


@course_bp.route('/courses/<int:course_id>/assignment/create', methods=['GET', 'POST'])
@login_required
def create_assignment(course_id):
    course = Course.query.get_or_404(course_id)
    if course.teacher_id != current_user.id:
        abort(403)

    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        description = request.form.get('description', '').strip()
        max_marks = int(request.form.get('max_marks', 100))
        due_date_str = request.form.get('due_date')

        if not title or not description or not due_date_str:
            flash('Title, description, and due date are required.', 'danger')
            return redirect(url_for('course.create_assignment', course_id=course_id))

        from datetime import datetime as dt
        due_date = dt.strptime(due_date_str, '%Y-%m-%dT%H:%M')

        assignment = Assignment(
            course_id=course.id,
            title=title,
            description=description,
            max_marks=max_marks,
            due_date=due_date
        )
        db.session.add(assignment)
        db.session.commit()

        flash(f'Assignment "{assignment.title}" created successfully!', 'success')
        return redirect(url_for('dashboard.teacher'))

    return render_template('assignment_form.html', course=course, action='create')


@course_bp.route('/courses/<int:course_id>/live-class/create', methods=['GET', 'POST'])
@login_required
def create_live_class(course_id):
    course = Course.query.get_or_404(course_id)
    if course.teacher_id != current_user.id:
        abort(403)

    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        meet_link = request.form.get('meet_link', '').strip()
        date_str = request.form.get('date')
        time_str = request.form.get('time')
        duration = int(request.form.get('duration_minutes', 60))
        description = request.form.get('description', '').strip()

        if not title or not date_str or not time_str:
            flash('Title, date, and time are required.', 'danger')
            return redirect(url_for('course.create_live_class', course_id=course_id))

        from datetime import datetime as dt
        start_time = dt.strptime(f'{date_str} {time_str}', '%Y-%m-%d %H:%M')

        lc = LiveClass(
            course_id=course.id,
            teacher_id=current_user.id,
            title=title,
            description=description or None,
            meet_link=meet_link or None,
            start_time=start_time,
            duration_minutes=duration
        )
        db.session.add(lc)
        db.session.commit()

        flash(f'Live class "{lc.title}" scheduled!', 'success')
        return redirect(url_for('dashboard.teacher'))

    return render_template('live_class_form.html', course=course, action='create')


@course_bp.route('/courses/<int:course_id>/attendance', methods=['GET', 'POST'])
@login_required
def attendance(course_id):
    course = Course.query.get_or_404(course_id)
    today = datetime.now().date()

    if request.method == 'POST':
        if course.teacher_id != current_user.id:
            abort(403)
        att_date_str = request.form.get('att_date', str(today))
        try:
            att_date = datetime.strptime(att_date_str, '%Y-%m-%d').date()
        except ValueError:
            att_date = today

        student_ids = request.form.getlist('student_ids')
        for sid_str in student_ids:
            try:
                sid = int(sid_str)
            except ValueError:
                continue
            existing = Attendance.query.filter_by(
                course_id=course.id, student_id=sid, date=att_date
            ).first()
            is_present = request.form.get(f'present_{sid}') == 'on'
            if existing:
                existing.is_present = is_present
            else:
                db.session.add(Attendance(
                    course_id=course.id, student_id=sid,
                    date=att_date, is_present=is_present
                ))
        db.session.commit()
        flash(f'Attendance saved for {att_date}.', 'success')
        return redirect(url_for('course.attendance', course_id=course_id))

    enrollments = Enrollment.query.filter_by(course_id=course.id).all()
    enrolled_students = sorted(set(
        (e.student_id, e.student.username) for e in enrollments
    ), key=lambda x: x[1])

    student_attendance = {}
    for sid, sname in enrolled_students:
        records = Attendance.query.filter_by(
            course_id=course.id, student_id=sid
        ).order_by(Attendance.date.desc()).all()
        student_attendance[sid] = {
            'username': sname,
            'records': records,
            'present_count': sum(1 for r in records if r.is_present),
            'total_count': len(records)
        }

    return render_template(
        'attendance_form.html',
        course=course,
        today=today,
        enrolled=enrolled_students,
        student_attendance=student_attendance
    )


@course_bp.route('/courses/<int:course_id>/delete', methods=['POST'])
@login_required
def delete_course(course_id):
    course = Course.query.get_or_404(course_id)
    if current_user.role.name != 'Admin' and course.teacher_id != current_user.id:
        abort(403)
    db.session.delete(course)
    db.session.commit()
    flash(f'Course "{course.title}" deleted.', 'success')
    if current_user.role.name == 'Admin':
        return redirect(url_for('dashboard.admin'))
    return redirect(url_for('dashboard.teacher'))


@course_bp.route('/courses/<int:course_id>/lab-manuals', methods=['GET'])
@login_required
def lab_manuals(course_id):
    course = Course.query.get_or_404(course_id)
    if course.teacher_id != current_user.id and current_user.role.name != 'Admin':
        abort(403)
    manuals = LabManual.query.filter_by(course_id=course.id).order_by(LabManual.sort_order).all()
    return render_template('lab_manuals.html', course=course, manuals=manuals)


@course_bp.route('/courses/<int:course_id>/lab-manuals/create', methods=['GET', 'POST'])
@login_required
def create_lab_manual(course_id):
    course = Course.query.get_or_404(course_id)
    if course.teacher_id != current_user.id:
        abort(403)

    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        if not title:
            flash('Title is required.', 'danger')
            return redirect(url_for('course.lab_manuals', course_id=course.id))

        date_str = request.form.get('date_performed', '')
        date_performed = None
        if date_str:
            try:
                from datetime import date as dt_date
                parts = date_str.split('-')
                date_performed = dt_date(int(parts[0]), int(parts[1]), int(parts[2]))
            except:
                pass

        image_urls = []
        images = request.files.getlist('images')
        for img in images:
            if img and img.filename:
                result = upload_file(img, folder='lab_manuals')
                if result:
                    image_urls.append(result)

        pdf_url = ''
        pdf_file = request.files.get('pdf_file')
        if pdf_file and pdf_file.filename:
            result = upload_file(pdf_file, folder='lab_manuals')
            if result:
                pdf_url = result

        import json
        order = len(LabManual.query.filter_by(course_id=course.id).all()) + 1

        manual = LabManual(
            course_id=course.id,
            title=title,
            date_performed=date_performed,
            software_used=request.form.get('software_used', ''),
            objectives=request.form.get('objectives', ''),
            theory=request.form.get('theory', ''),
            procedure=request.form.get('procedure', ''),
            observations=request.form.get('observations', ''),
            result=request.form.get('result', ''),
            conclusion=request.form.get('conclusion', ''),
            image_urls=json.dumps(image_urls),
            pdf_url=pdf_url,
            sort_order=order,
            created_by=current_user.id
        )
        db.session.add(manual)
        db.session.commit()
        flash('Lab manual created successfully!', 'success')
        return redirect(url_for('course.lab_manuals', course_id=course.id))

    return render_template('lab_manual_form.html', course=course, manual=None, action='create')


@course_bp.route('/lab-manuals/<int:manual_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_lab_manual(manual_id):
    manual = LabManual.query.get_or_404(manual_id)
    if manual.course.teacher_id != current_user.id:
        abort(403)

    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        if not title:
            flash('Title is required.', 'danger')
            return redirect(url_for('course.lab_manuals', course_id=manual.course_id))

        date_str = request.form.get('date_performed', '')
        if date_str:
            try:
                from datetime import date as dt_date
                parts = date_str.split('-')
                manual.date_performed = dt_date(int(parts[0]), int(parts[1]), int(parts[2]))
            except:
                manual.date_performed = None
        else:
            manual.date_performed = None

        manual.title = title
        manual.software_used = request.form.get('software_used', '')
        manual.objectives = request.form.get('objectives', '')
        manual.theory = request.form.get('theory', '')
        manual.procedure = request.form.get('procedure', '')
        manual.observations = request.form.get('observations', '')
        manual.result = request.form.get('result', '')
        manual.conclusion = request.form.get('conclusion', '')

        import json
        existing_images = manual.images_list()
        delete_images = request.form.getlist('delete_images')
        remaining_images = [url for url in existing_images if url not in delete_images]

        images = request.files.getlist('images')
        new_images = []
        for img in images:
            if img and img.filename:
                result = upload_file(img, folder='lab_manuals')
                if result:
                    new_images.append(result)

        manual.image_urls = json.dumps(remaining_images + new_images)

        if request.form.get('delete_pdf'):
            manual.pdf_url = ''
        else:
            pdf_file = request.files.get('pdf_file')
            if pdf_file and pdf_file.filename:
                result = upload_file(pdf_file, folder='lab_manuals')
                if result:
                    manual.pdf_url = result

        db.session.commit()
        flash('Lab manual updated!', 'success')
        return redirect(url_for('course.lab_manuals', course_id=manual.course_id))

    return render_template('lab_manual_form.html', course=manual.course, manual=manual, action='edit')


@course_bp.route('/lab-manuals/<int:manual_id>/delete', methods=['POST'])
@login_required
def delete_lab_manual(manual_id):
    manual = LabManual.query.get_or_404(manual_id)
    if manual.course.teacher_id != current_user.id:
        abort(403)
    db.session.delete(manual)
    db.session.commit()
    flash('Lab manual deleted.', 'success')
    return redirect(url_for('course.lab_manuals', course_id=manual.course_id))


@course_bp.route('/lab-manuals/<int:manual_id>')
@login_required
def view_lab_manual(manual_id):
    manual = LabManual.query.get_or_404(manual_id)
    enrollment = Enrollment.query.filter_by(
        student_id=current_user.id, course_id=manual.course_id
    ).first()
    if not enrollment and manual.course.teacher_id != current_user.id and current_user.role.name != 'Admin':
        abort(403)
    return render_template('lab_manual_view.html', manual=manual)
