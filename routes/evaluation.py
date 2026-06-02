import os
import uuid
from datetime import datetime
from werkzeug.utils import secure_filename
from flask import Blueprint, render_template, redirect, url_for, flash, request, abort, current_app
from flask_login import login_required, current_user
from database import db
from models.course import Course
from models.learning import Enrollment
from models.evaluation import Evaluation, EvaluationSubmission, EVALUATION_TYPES
from utils.cloudinary_upload import upload_file

eval_bp = Blueprint('eval', __name__)

EVAL_ICONS = {
    'quiz': 'fa-question-circle',
    'test_paper': 'fa-file-alt',
    'presentation': 'fa-chalkboard-teacher',
    'lab': 'fa-flask'
}
EVAL_COLORS = {
    'quiz': '#8b5cf6',
    'test_paper': '#3b82f6',
    'presentation': '#10b981',
    'lab': '#f59e0b'
}


@eval_bp.route('/courses/<int:course_id>/evaluations')
@login_required
def index(course_id):
    course = Course.query.get_or_404(course_id)
    if current_user.role.name == 'Teacher' and course.teacher_id != current_user.id:
        abort(403)
    if current_user.role.name == 'Student':
        evaluations = Evaluation.query.filter_by(course_id=course_id).order_by(Evaluation.scheduled_at.desc()).all()
    else:
        evaluations = Evaluation.query.filter_by(course_id=course_id).order_by(Evaluation.created_at.desc()).all()
    return render_template('evaluation_list.html', course=course, evaluations=evaluations,
                           icons=EVAL_ICONS, colors=EVAL_COLORS, types=EVALUATION_TYPES)


@eval_bp.route('/courses/<int:course_id>/evaluations/create', methods=['GET', 'POST'])
@login_required
def create(course_id):
    course = Course.query.get_or_404(course_id)
    if current_user.role.name != 'Teacher' or course.teacher_id != current_user.id:
        abort(403)

    selected_type = request.args.get('type', '') or request.form.get('eval_type', '')
    if selected_type not in EVALUATION_TYPES:
        flash('Please select a valid evaluation type.', 'danger')
        return redirect(url_for('eval.index', course_id=course_id))

    if selected_type == 'quiz':
        return redirect(url_for('course.create_quiz', course_id=course_id, from_eval=1))

    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        if not title:
            flash('Title is required.', 'danger')
            return redirect(url_for('eval.create', course_id=course_id, type=selected_type))

        scheduled_str = request.form.get('scheduled_at', '')
        scheduled = None
        if scheduled_str:
            try:
                scheduled = datetime.fromisoformat(scheduled_str)
            except ValueError:
                flash('Invalid date/time format.', 'danger')
                return redirect(url_for('eval.create', course_id=course_id, type=selected_type))

        question_pdf_url = ''
        if selected_type == 'test_paper':
            pdf = request.files.get('question_pdf')
            if pdf and pdf.filename:
                url = upload_file(pdf, folder='shikshya/evaluations')
                question_pdf_url = url or ''

        evaluation = Evaluation(
            course_id=course_id,
            title=title,
            eval_type=selected_type,
            description=request.form.get('description', '').strip(),
            question_pdf_url=question_pdf_url or request.form.get('question_pdf_link', '').strip(),
            meet_link=request.form.get('meet_link', '').strip(),
            max_score=float(request.form.get('max_score') or 100),
            scheduled_at=scheduled,
            duration_minutes=int(request.form.get('duration_minutes') or 0) or None,
            status='upcoming',
            created_by=current_user.id
        )
        db.session.add(evaluation)
        db.session.commit()
        flash(f'Evaluation "{title}" created.', 'success')
        return redirect(url_for('eval.index', course_id=course_id))

    label = selected_type.replace('_', ' ').title()
    return render_template('evaluation_form.html', course=course, selected_type=selected_type, eval_label=label, icons=EVAL_ICONS, colors=EVAL_COLORS)


@eval_bp.route('/evaluations/<int:eval_id>/edit', methods=['GET', 'POST'])
@login_required
def edit(eval_id):
    evaluation = Evaluation.query.get_or_404(eval_id)
    course = evaluation.course
    if current_user.role.name != 'Teacher' or course.teacher_id != current_user.id:
        abort(403)

    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        if not title:
            flash('Title is required.', 'danger')
            return redirect(url_for('eval.edit', eval_id=eval_id))

        scheduled_str = request.form.get('scheduled_at', '')
        scheduled = None
        if scheduled_str:
            try:
                scheduled = datetime.fromisoformat(scheduled_str)
            except ValueError:
                flash('Invalid date/time format.', 'danger')
                return redirect(url_for('eval.edit', eval_id=eval_id))

        evaluation.title = title
        evaluation.description = request.form.get('description', '').strip()
        evaluation.max_score = float(request.form.get('max_score', 100))
        evaluation.scheduled_at = scheduled
        evaluation.duration_minutes = int(request.form.get('duration_minutes') or 0) or None
        evaluation.meet_link = request.form.get('meet_link', '').strip()

        if evaluation.eval_type == 'test_paper':
            pdf = request.files.get('question_pdf')
            if pdf and pdf.filename:
                url = upload_file(pdf, folder='shikshya/evaluations')
                if url:
                    evaluation.question_pdf_url = url
            else:
                link = request.form.get('question_pdf_link', '').strip()
                if link:
                    evaluation.question_pdf_url = link

        db.session.commit()
        flash('Evaluation updated.', 'success')
        return redirect(url_for('eval.index', course_id=course.id))

    selected_type = evaluation.eval_type
    label = selected_type.replace('_', ' ').title()
    return render_template('evaluation_form.html', course=course, evaluation=evaluation, selected_type=selected_type, eval_label=label, icons=EVAL_ICONS, colors=EVAL_COLORS)


@eval_bp.route('/evaluations/<int:eval_id>/delete', methods=['POST'])
@login_required
def delete(eval_id):
    evaluation = Evaluation.query.get_or_404(eval_id)
    if current_user.role.name != 'Teacher' or evaluation.course.teacher_id != current_user.id:
        abort(403)
    course_id = evaluation.course_id
    db.session.delete(evaluation)
    db.session.commit()
    flash('Evaluation deleted.', 'success')
    return redirect(url_for('eval.index', course_id=course_id))


@eval_bp.route('/evaluations/<int:eval_id>')
@login_required
def detail(eval_id):
    evaluation = Evaluation.query.get_or_404(eval_id)
    course = evaluation.course

    if current_user.role.name == 'Teacher':
        if course.teacher_id != current_user.id:
            abort(403)
        enrolled_students = Enrollment.query.filter_by(course_id=course.id).all()
        student_ids = [e.student_id for e in enrolled_students]
        submissions = EvaluationSubmission.query.filter_by(evaluation_id=eval_id).all()
        submitted_ids = {s.student_id for s in submissions}
        students_data = []
        for e in enrolled_students:
            sub = next((s for s in submissions if s.student_id == e.student_id), None)
            students_data.append({
                'student': e.student,
                'submission': sub
            })
        return render_template('evaluation_teacher.html', evaluation=evaluation, course=course,
                               students_data=students_data, icons=EVAL_ICONS, colors=EVAL_COLORS, now=datetime.now())

    if current_user.role.name == 'Student':
        enrollment = Enrollment.query.filter_by(student_id=current_user.id, course_id=course.id).first()
        if not enrollment:
            abort(403)
        submission = EvaluationSubmission.query.filter_by(evaluation_id=eval_id, student_id=current_user.id).first()
        can_view_results = evaluation.results_published
        return render_template('evaluation_student.html', evaluation=evaluation, course=course,
                               submission=submission, can_view_results=can_view_results, icons=EVAL_ICONS, colors=EVAL_COLORS, now=datetime.now())

    abort(403)


@eval_bp.route('/evaluations/<int:eval_id>/submit', methods=['GET', 'POST'])
@login_required
def submit(eval_id):
    evaluation = Evaluation.query.get_or_404(eval_id)
    course = evaluation.course
    if current_user.role.name != 'Student':
        abort(403)
    enrollment = Enrollment.query.filter_by(student_id=current_user.id, course_id=course.id).first()
    if not enrollment:
        abort(403)

    existing = EvaluationSubmission.query.filter_by(evaluation_id=eval_id, student_id=current_user.id).first()
    if existing:
        flash('You have already submitted for this evaluation.', 'warning')
        return redirect(url_for('eval.detail', eval_id=eval_id))

    now = datetime.now()
    if evaluation.scheduled_at and now < evaluation.scheduled_at:
        flash('This exam has not started yet. It opens at ' + evaluation.scheduled_at.strftime('%I:%M %p on %b %d, %Y') + '.', 'warning')
        return redirect(url_for('eval.detail', eval_id=eval_id))

        if request.method == 'POST':
            notes = request.form.get('notes', '').strip()
            file_url = ''
            file = request.files.get('file')
            if file and file.filename:
                url = upload_file(file, folder='shikshya/submissions')
                file_url = url or ''

        submission = EvaluationSubmission(
            evaluation_id=eval_id,
            student_id=current_user.id,
            file_url=file_url or request.form.get('link', '').strip(),
            notes=notes
        )
        db.session.add(submission)
        db.session.commit()
        flash('Evaluation submitted successfully.', 'success')
        return redirect(url_for('eval.detail', eval_id=eval_id))

    return render_template('evaluation_submit.html', evaluation=evaluation, course=course, icons=EVAL_ICONS, colors=EVAL_COLORS)


@eval_bp.route('/evaluations/<int:eval_id>/grade', methods=['POST'])
@login_required
def grade(eval_id):
    evaluation = Evaluation.query.get_or_404(eval_id)
    if current_user.role.name != 'Teacher' or evaluation.course.teacher_id != current_user.id:
        abort(403)

    sub_id = request.form.get('submission_id', type=int)
    score = request.form.get('score', type=float)
    feedback = request.form.get('feedback', '').strip()

    sub = EvaluationSubmission.query.get_or_404(sub_id)
    sub.score = score
    sub.feedback = feedback
    sub.graded_by = current_user.id
    sub.graded_at = datetime.utcnow()
    db.session.commit()
    flash('Submission graded.', 'success')
    return redirect(url_for('eval.detail', eval_id=eval_id))


@eval_bp.route('/evaluations/<int:eval_id>/publish')
@login_required
def publish(eval_id):
    evaluation = Evaluation.query.get_or_404(eval_id)
    if current_user.role.name != 'Teacher' or evaluation.course.teacher_id != current_user.id:
        abort(403)
    evaluation.results_published = True
    evaluation.status = 'completed'
    db.session.commit()
    flash('Results published. Students can now view their scores.', 'success')
    return redirect(url_for('eval.detail', eval_id=eval_id))


@eval_bp.route('/evaluations/<int:eval_id>/unpublish')
@login_required
def unpublish(eval_id):
    evaluation = Evaluation.query.get_or_404(eval_id)
    if current_user.role.name != 'Teacher' or evaluation.course.teacher_id != current_user.id:
        abort(403)
    evaluation.results_published = False
    db.session.commit()
    flash('Results hidden from students.', 'success')
    return redirect(url_for('eval.detail', eval_id=eval_id))
