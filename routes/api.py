import os
import uuid
import io
import requests
import qrcode
from datetime import datetime
from werkzeug.utils import secure_filename
from flask import Blueprint, jsonify, request, abort, render_template, redirect, url_for, flash, send_file, current_app
from flask_login import login_required, current_user
from database import db
from models.learning import Enrollment, LessonProgress, Quiz, QuizAttempt, Assignment, Submission, Question, Choice
from models.course import Course, Review, Lesson
from models.interaction import Notification, DiscussionTopic, DiscussionReply, Certificate

api_bp = Blueprint('api', __name__)


def _update_course_progress(enrollment):
    """Recalculate overall course progress including lessons, quizzes, and assignments."""
    course = enrollment.course
    student_id = enrollment.student_id

    total_lessons = sum(len(m.lessons) for m in course.modules)
    quiz_ids = [q.id for q in Quiz.query.filter_by(course_id=course.id).all()]
    assignment_ids = [a.id for a in Assignment.query.filter_by(course_id=course.id).all()]
    total_items = total_lessons + len(quiz_ids) + len(assignment_ids)

    if total_items == 0:
        enrollment.progress_percent = 0.0
        db.session.commit()
        return

    completed_lessons = LessonProgress.query.filter_by(enrollment_id=enrollment.id, is_completed=True).count()

    completed_quizzes = 0
    if quiz_ids:
        completed_quizzes = db.session.query(QuizAttempt.quiz_id).filter(
            QuizAttempt.student_id == student_id,
            QuizAttempt.is_passed == True,
            QuizAttempt.quiz_id.in_(quiz_ids)
        ).distinct(QuizAttempt.quiz_id).count()

    completed_assignments = 0
    if assignment_ids:
        completed_assignments = Submission.query.filter(
            Submission.student_id == student_id,
            Submission.assignment_id.in_(assignment_ids)
        ).count()

    completed = completed_lessons + completed_quizzes + completed_assignments
    enrollment.progress_percent = round((completed / total_items) * 100, 1)

    if enrollment.progress_percent >= 100.0 and not enrollment.is_completed:
        enrollment.is_completed = True
        enrollment.completed_at = datetime.utcnow()

        cert_code = f"CERT-{course.id:03d}-{student_id:04d}-{uuid.uuid4().hex[:6].upper()}"
        existing_cert = Certificate.query.filter_by(student_id=student_id, course_id=course.id).first()
        if not existing_cert:
            cert = Certificate(
                unique_code=cert_code,
                student_id=student_id,
                course_id=course.id,
                qr_code_data=url_for('main.verify_certificate_public', unique_code=cert_code, _external=True)
            )
            db.session.add(cert)
            notif = Notification(
                user_id=student_id,
                title="Course Completed! \U0001f393",
                message=f"Congratulations! You completed '{course.title}' and earned a certificate.",
                notif_type="success"
            )
            db.session.add(notif)

    db.session.commit()


@api_bp.route('/api/progress/video', methods=['POST'])
@login_required
def track_video_progress():
    data = request.json or {}
    lesson_id = data.get('lesson_id')
    seconds = data.get('seconds', 0)
    is_completed = data.get('is_completed', False)

    if not lesson_id:
        return jsonify({'error': 'lesson_id required'}), 400

    progress = LessonProgress.query.join(Enrollment).filter(
        Enrollment.student_id == current_user.id,
        LessonProgress.lesson_id == lesson_id
    ).first()

    if not progress:
        return jsonify({'error': 'No enrollment or progress tracking record found'}), 404

    progress.video_progress_seconds = seconds
    if is_completed:
        progress.is_completed = True

    enrollment = progress.enrollment
    _update_course_progress(enrollment)

    return jsonify({
        'success': True,
        'progress_percent': enrollment.progress_percent,
        'is_completed': enrollment.is_completed
    })


@api_bp.route('/api/quiz/submit', methods=['POST'])
@login_required
def submit_quiz():
    data = request.json or {}
    quiz_id = data.get('quiz_id')
    answers = data.get('answers', {})

    if not quiz_id:
        return jsonify({'error': 'quiz_id required'}), 400

    quiz = Quiz.query.get_or_404(quiz_id)

    # lesson-gated quiz: must complete the lesson first
    if quiz.lesson_id and current_user.role.name == 'Student':
        enrollment = Enrollment.query.filter_by(student_id=current_user.id, course_id=quiz.course_id).first()
        if enrollment:
            lp = LessonProgress.query.filter_by(enrollment_id=enrollment.id, lesson_id=quiz.lesson_id).first()
            if not lp or not lp.is_completed:
                return jsonify({'error': 'Complete the lesson first to submit this quiz.'}), 403

    questions = quiz.questions

    total_points = sum(q.points for q in questions)
    score_obtained = 0
    correct_count = 0

    results = {}
    for q in questions:
        selected_choice_id = answers.get(str(q.id))
        correct_choice = Choice.query.filter_by(question_id=q.id, is_correct=True).first()

        is_correct = False
        if selected_choice_id and correct_choice and int(selected_choice_id) == correct_choice.id:
            score_obtained += q.points
            correct_count += 1
            is_correct = True

        results[q.id] = {
            'is_correct': is_correct,
            'correct_choice_id': correct_choice.id if correct_choice else None,
            'correct_choice_text': correct_choice.text if correct_choice else ''
        }

    percent_score = (score_obtained / total_points * 100) if total_points > 0 else 0.0
    is_passed = percent_score >= quiz.passing_score

    attempt = QuizAttempt(
        quiz_id=quiz.id,
        student_id=current_user.id,
        score=percent_score,
        is_passed=is_passed,
        completed_at=datetime.utcnow()
    )
    db.session.add(attempt)

    if is_passed:
        enrollment = Enrollment.query.filter_by(student_id=current_user.id, course_id=quiz.course_id).first()
        if enrollment:
            _update_course_progress(enrollment)

    notif = Notification(
        user_id=current_user.id,
        title="Quiz Completed!",
        message=f"You scored {round(percent_score, 1)}% in the '{quiz.title}' quiz. Result: {'PASSED' if is_passed else 'FAILED'}.",
        notif_type="success" if is_passed else "warning"
    )
    db.session.add(notif)

    db.session.commit()

    return jsonify({
        'score': percent_score,
        'is_passed': is_passed,
        'correct_count': correct_count,
        'total_questions': len(questions),
        'results': results
    })


@api_bp.route('/api/ai/chat', methods=['POST'])
@login_required
def ai_chat():
    data = request.json or {}
    message = data.get('message', '').strip().lower()

    if not message:
        return jsonify({'reply': 'Hello! I am your Shikshya AI Assistant. How can I help you with your learning path today?'})

    if 'python' in message or 'code' in message or 'programming' in message:
        reply = (
            "Python is a versatile high-level language popular for web apps and AI! "
            "In Flask, you can create a route like this:\n"
            "```python\n"
            "@app.route('/')\n"
            "def index():\n"
            "    return 'Hello, Learner!'\n"
            "```\n"
            "Would you like me to explain loops, decorators, or class inheritance next?"
        )
    elif 'quiz' in message or 'exam' in message:
        reply = (
            "To excel in your quizzes, review the module notes and check your summaries! "
            "Remember that some exams have timers, so manage your time effectively."
        )
    elif 'certificate' in message or 'complete' in message:
        reply = (
            "Once you complete 100% of a course's lessons (watch videos till completion, read files), "
            "your certificate is instantly generated with a unique verification QR code! "
            "You can find it on your **Student Dashboard** under 'My Certificates'."
        )
    elif 'hello' in message or message.startswith('hi ') or 'hey' in message:
        reply = f"Hello, {current_user.username}! I am your Shikshya AI tutor. What are we studying today? (Python, web development, study tips, or quiz reviews?)"
    else:
        reply = (
            f"That's an excellent question! Studying can sometimes feel complex. "
            f"Regarding your query about '{message}', my best suggestion is to look at the corresponding discussion "
            f"forums of your active courses or draft a direct Q&A message to your teacher. "
            f"How else can I assist your study session?"
        )

    return jsonify({'reply': reply})


@api_bp.route('/api/discussions/create', methods=['POST'])
@login_required
def create_topic():
    course_id = request.form.get('course_id', type=int)
    title = request.form.get('title')
    content = request.form.get('content')

    if not course_id or not title or not content:
        return jsonify({'error': 'Missing required fields'}), 400

    enrollment = Enrollment.query.filter_by(student_id=current_user.id, course_id=course_id).first()
    course = Course.query.get_or_404(course_id)
    if not enrollment and course.teacher_id != current_user.id:
        return jsonify({'error': 'Not enrolled'}), 403

    topic = DiscussionTopic(
        course_id=course_id,
        user_id=current_user.id,
        title=title,
        content=content
    )
    db.session.add(topic)
    db.session.commit()

    return jsonify({
        'success': True,
        'topic_id': topic.id,
        'title': topic.title,
        'author': current_user.username,
        'created_at': topic.created_at.strftime('%Y-%m-%d %H:%M')
    })


@api_bp.route('/api/discussions/<int:topic_id>/reply', methods=['POST'])
@login_required
def add_reply(topic_id):
    content = request.form.get('content')
    if not content:
        return jsonify({'error': 'Content required'}), 400

    topic = DiscussionTopic.query.get_or_404(topic_id)

    reply = DiscussionReply(
        topic_id=topic.id,
        user_id=current_user.id,
        content=content
    )
    db.session.add(reply)

    if topic.user_id != current_user.id:
        notif = Notification(
            user_id=topic.user_id,
            title="New Reply in Forum",
            message=f"{current_user.username} replied to your topic: '{topic.title}'.",
            notif_type="info"
        )
        db.session.add(notif)

    db.session.commit()

    return jsonify({
        'success': True,
        'reply_id': reply.id,
        'author': current_user.username,
        'content': reply.content,
        'created_at': reply.created_at.strftime('%Y-%m-%d %H:%M')
    })


@api_bp.route('/api/notifications', methods=['GET'])
@login_required
def get_notifications():
    notifications = Notification.query.filter_by(user_id=current_user.id, is_read=False).order_by(Notification.created_at.desc()).all()
    return jsonify([{
        'id': n.id,
        'title': n.title,
        'message': n.message,
        'type': n.notif_type,
        'created_at': n.created_at.strftime('%I:%M %p')
    } for n in notifications])


@api_bp.route('/api/notifications/<int:notif_id>/read', methods=['POST'])
@login_required
def mark_read(notif_id):
    n = Notification.query.filter_by(id=notif_id, user_id=current_user.id).first_or_404()
    n.is_read = True
    db.session.commit()
    return jsonify({'success': True})


@api_bp.route('/submissions/<int:submission_id>/grade', methods=['POST'])
@login_required
def grade_submission(submission_id):
    if current_user.role.name != 'Teacher':
        abort(403)

    sub = Submission.query.get_or_404(submission_id)
    if sub.assignment.course.teacher_id != current_user.id:
        abort(403)

    marks = float(request.form.get('marks', 0.0))
    feedback = request.form.get('feedback', '')

    sub.marks_obtained = marks
    sub.feedback = feedback
    sub.is_graded = True

    # update student's course progress
    enrollment = Enrollment.query.filter_by(student_id=sub.student_id, course_id=sub.assignment.course_id).first()
    if enrollment:
        _update_course_progress(enrollment)

    notif = Notification(
        user_id=sub.student_id,
        title="Assignment Graded! \U0001f4dd",
        message=f"Your submission for assignment '{sub.assignment.title}' has been graded. Score: {marks}/{sub.assignment.max_marks}.",
        notif_type="success"
    )
    db.session.add(notif)
    db.session.commit()

    flash(f"Submission from student {sub.student.username} graded successfully!", "success")
    return redirect(url_for('dashboard.teacher'))


@api_bp.route('/quizzes/<int:quiz_id>')
@login_required
def take_quiz_view(quiz_id):
    quiz = Quiz.query.get_or_404(quiz_id)
    enrollment = Enrollment.query.filter_by(student_id=current_user.id, course_id=quiz.course_id).first()
    if not enrollment and quiz.course.teacher_id != current_user.id:
        abort(403)

    # lesson-gated quiz: must complete the lesson first
    if quiz.lesson_id and current_user.role.name == 'Student':
        lp = LessonProgress.query.filter_by(enrollment_id=enrollment.id, lesson_id=quiz.lesson_id).first()
        if not lp or not lp.is_completed:
            flash('Complete the lesson first to unlock the quiz.', 'warning')
            return redirect(url_for('course.player', slug=quiz.course.slug, lesson_id=quiz.lesson_id))

    return render_template('quiz.html', quiz=quiz)


@api_bp.route('/api/quizzes/<int:quiz_id>/report')
@login_required
def quiz_report(quiz_id):
    quiz = Quiz.query.get_or_404(quiz_id)
    if quiz.course.teacher_id != current_user.id:
        abort(403)

    try:
        from weasyprint import HTML
    except OSError:
        abort(500, 'PDF generation library not available on this platform')

    attempts = QuizAttempt.query.filter_by(quiz_id=quiz_id).order_by(QuizAttempt.started_at).all()

    passed_count = sum(1 for a in attempts if a.is_passed)
    failed_count = len(attempts) - passed_count
    avg_score = sum(a.score for a in attempts) / len(attempts) if attempts else 0

    html_str = render_template('reports/quiz_report.html',
        quiz=quiz,
        attempts=attempts,
        passed_count=passed_count,
        failed_count=failed_count,
        avg_score=avg_score,
        now=datetime.now()
    )

    pdf = HTML(string=html_str).write_pdf()

    name = f'quiz_report_{quiz.title.replace(" ", "_")}.pdf'
    return send_file(io.BytesIO(pdf), mimetype='application/pdf',
        as_attachment=True, download_name=name)


@api_bp.route('/certificates/<unique_code>')
@login_required
def view_certificate(unique_code):
    cert = Certificate.query.filter_by(unique_code=unique_code).first_or_404()
    if cert.student_id != current_user.id and current_user.role.name != 'Admin':
        abort(403)
    return render_template('certificate.html', certificate=cert)


@api_bp.route('/api/assignments/<int:assignment_id>/submit', methods=['POST'])
@login_required
def submit_assignment(assignment_id):
    assignment = Assignment.query.get_or_404(assignment_id)

    enrollment = Enrollment.query.filter_by(student_id=current_user.id, course_id=assignment.course_id).first()
    if not enrollment:
        return jsonify({'error': 'You are not enrolled in this course.'}), 403

    file_url = request.form.get('file_url', '').strip()
    uploaded_file = request.files.get('submission_file')

    if not file_url and (not uploaded_file or not uploaded_file.filename):
        return jsonify({'error': 'Please upload a file or provide a solution URL.'}), 400

    if uploaded_file and uploaded_file.filename:
        filename = secure_filename(uploaded_file.filename)
        ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else 'bin'
        allowed = {'pdf', 'jpg', 'jpeg', 'png', 'gif', 'zip', 'doc', 'docx', 'txt', 'py', 'js', 'html', 'css'}
        if ext not in allowed:
            return jsonify({'error': f'File type .{ext} is not allowed. Allowed: {", ".join(sorted(allowed))}'}), 400
        unique_name = f'sub_{assignment_id}_{current_user.id}_{uuid.uuid4().hex[:8]}.{ext}'
        upload_path = os.path.join(current_app.config['UPLOAD_FOLDER'], 'assignments', unique_name)
        uploaded_file.save(upload_path)
        file_url = f'uploads/assignments/{unique_name}'

    submission = Submission.query.filter_by(assignment_id=assignment_id, student_id=current_user.id).first()

    is_late = datetime.utcnow() > assignment.due_date

    if submission:
        submission.file_url = file_url
        submission.submitted_at = datetime.utcnow()
        submission.is_graded = False
        submission.is_late = is_late
    else:
        submission = Submission(
            assignment_id=assignment_id,
            student_id=current_user.id,
            file_url=file_url,
            is_late=is_late
        )
        db.session.add(submission)

    _update_course_progress(enrollment)

    teacher_notif = Notification(
        user_id=assignment.course.teacher_id,
        title="New Assignment Submission!",
        message=f"Student {current_user.username} submitted solution for '{assignment.title}'.",
        notif_type="info"
    )
    db.session.add(teacher_notif)

    db.session.commit()

    return jsonify({
        'success': True,
        'message': 'Assignment submitted successfully!'
    })


@api_bp.route('/api/lessons/<int:lesson_id>/download')
@login_required
def download_lesson_doc(lesson_id):
    lesson = Lesson.query.get_or_404(lesson_id)
    doc_url = lesson.document_url
    if not doc_url or doc_url.strip().lower() in ('none', 'null', ''):
        abort(404)

    if doc_url.startswith(('http://', 'https://', '//')):
        from utils.cloudinary_upload import get_signed_download_url
        signed = get_signed_download_url(doc_url)
        if signed and signed != doc_url:
            return redirect(signed)
        # fallback: proxy through Flask
        proxy_url = doc_url
    else:
        proxy_url = url_for('static', filename=doc_url, _external=True)

    try:
        resp = requests.get(proxy_url, stream=True, timeout=30, headers={'User-Agent': 'Shikshya-LMS/1.0'})
        if resp.status_code != 200:
            abort(502)
        content = resp.content
        filename = f"{lesson.title.replace(' ', '_')}_notes.pdf"
        return send_file(
            io.BytesIO(content),
            mimetype=resp.headers.get('Content-Type', 'application/pdf'),
            as_attachment=True,
            download_name=filename
        )
    except Exception as e:
        current_app.logger.error(f'Download proxy failed: {e}')
        abort(502)


@api_bp.route('/api/certificates/<unique_code>/qrcode')
def get_certificate_qrcode(unique_code):
    cert = Certificate.query.filter_by(unique_code=unique_code).first_or_404()

    qr = qrcode.QRCode(version=1, box_size=10, border=2)
    qr.add_data(cert.qr_code_data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")

    img_io = io.BytesIO()
    img.save(img_io, 'PNG')
    img_io.seek(0)

    return send_file(img_io, mimetype='image/png')
