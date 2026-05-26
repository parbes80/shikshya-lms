from datetime import datetime
from database import db

EVALUATION_TYPES = ['quiz', 'test_paper', 'presentation', 'lab']


class Evaluation(db.Model):
    __tablename__ = 'evaluations'

    id = db.Column(db.Integer, primary_key=True)
    course_id = db.Column(db.Integer, db.ForeignKey('courses.id', ondelete='CASCADE'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    eval_type = db.Column(db.String(30), nullable=False)
    description = db.Column(db.Text, nullable=True)
    max_score = db.Column(db.Float, default=100.0)
    scheduled_at = db.Column(db.DateTime, nullable=True)
    duration_minutes = db.Column(db.Integer, nullable=True)
    question_pdf_url = db.Column(db.String(255), nullable=True)
    meet_link = db.Column(db.String(255), nullable=True)
    status = db.Column(db.String(20), default='upcoming')
    results_published = db.Column(db.Boolean, default=False)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    course = db.relationship('Course', backref=db.backref('evaluations', lazy=True, cascade="all, delete-orphan"))
    creator = db.relationship('User', backref=db.backref('created_evaluations', lazy=True))
    submissions = db.relationship('EvaluationSubmission', backref='evaluation', lazy=True, cascade="all, delete-orphan")

    def __repr__(self):
        return f'<Evaluation {self.title} [{self.eval_type}]>'


class EvaluationSubmission(db.Model):
    __tablename__ = 'evaluation_submissions'

    id = db.Column(db.Integer, primary_key=True)
    evaluation_id = db.Column(db.Integer, db.ForeignKey('evaluations.id', ondelete='CASCADE'), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    file_url = db.Column(db.String(255), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    score = db.Column(db.Float, nullable=True)
    feedback = db.Column(db.Text, nullable=True)
    graded_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    graded_at = db.Column(db.DateTime, nullable=True)
    submitted_at = db.Column(db.DateTime, default=datetime.utcnow)

    student = db.relationship('User', foreign_keys=[student_id], backref=db.backref('eval_submissions', lazy=True))
    grader = db.relationship('User', foreign_keys=[graded_by], lazy=True)

    def __repr__(self):
        return f'<EvaluationSubmission {self.student_id} - Eval {self.evaluation_id}>'
