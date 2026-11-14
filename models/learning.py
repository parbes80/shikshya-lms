from datetime import datetime
from database import db


class Enrollment(db.Model):
    __tablename__ = 'enrollments'

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    course_id = db.Column(db.Integer, db.ForeignKey('courses.id'), nullable=False)
    enrolled_at = db.Column(db.DateTime, default=datetime.utcnow)
    progress_percent = db.Column(db.Float, default=0.0)
    is_completed = db.Column(db.Boolean, default=False)
    completed_at = db.Column(db.DateTime, nullable=True)

    lesson_progresses = db.relationship('LessonProgress', backref='enrollment', lazy=True, cascade="all, delete-orphan")

    def __repr__(self):
        return f'<Enrollment Student ID {self.student_id} Course ID {self.course_id}>'


class LessonProgress(db.Model):
    __tablename__ = 'lesson_progresses'

    id = db.Column(db.Integer, primary_key=True)
    enrollment_id = db.Column(db.Integer, db.ForeignKey('enrollments.id', ondelete='CASCADE'), nullable=False)
    lesson_id = db.Column(db.Integer, db.ForeignKey('lessons.id', ondelete='CASCADE'), nullable=False)
    video_progress_seconds = db.Column(db.Integer, default=0)
    is_completed = db.Column(db.Boolean, default=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f'<LessonProgress Lesson ID {self.lesson_id} Completed: {self.is_completed}>'


class Assignment(db.Model):
    __tablename__ = 'assignments'

    id = db.Column(db.Integer, primary_key=True)
    course_id = db.Column(db.Integer, db.ForeignKey('courses.id', ondelete='CASCADE'), nullable=False)
    title = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text, nullable=False)
    file_url = db.Column(db.String(255), nullable=True)
    max_marks = db.Column(db.Integer, default=100)
    due_date = db.Column(db.DateTime, nullable=False)
    allow_late_submission = db.Column(db.Boolean, default=True)

    submissions = db.relationship('Submission', backref='assignment', lazy=True, cascade="all, delete-orphan")

    def __repr__(self):
        return f'<Assignment {self.title}>'


class Submission(db.Model):
    __tablename__ = 'submissions'

    id = db.Column(db.Integer, primary_key=True)
    assignment_id = db.Column(db.Integer, db.ForeignKey('assignments.id', ondelete='CASCADE'), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    file_url = db.Column(db.String(255), nullable=True)
    text_content = db.Column(db.Text, nullable=True)
    submitted_at = db.Column(db.DateTime, default=datetime.utcnow)
    marks_obtained = db.Column(db.Float, default=0.0)
    feedback = db.Column(db.Text, nullable=True)
    is_graded = db.Column(db.Boolean, default=False)
    is_late = db.Column(db.Boolean, default=False)

    def __repr__(self):
        return f'<Submission Student {self.student_id} Assignment {self.assignment_id}>'


class Quiz(db.Model):
    __tablename__ = 'quizzes'

    id = db.Column(db.Integer, primary_key=True)
    course_id = db.Column(db.Integer, db.ForeignKey('courses.id', ondelete='CASCADE'), nullable=False)
    lesson_id = db.Column(db.Integer, db.ForeignKey('lessons.id', ondelete='SET NULL'), nullable=True)
    title = db.Column(db.String(150), nullable=False)
    time_limit_minutes = db.Column(db.Integer, default=15)
    passing_score = db.Column(db.Integer, default=60)
    max_attempts = db.Column(db.Integer, default=0)  # 0 = unlimited
    opens_at = db.Column(db.DateTime, nullable=True)
    closes_at = db.Column(db.DateTime, nullable=True)
    results_published = db.Column(db.Boolean, default=True)

    questions = db.relationship('Question', backref='quiz', lazy=True, cascade="all, delete-orphan")
    attempts = db.relationship('QuizAttempt', backref='quiz', lazy=True, cascade="all, delete-orphan")

    lesson = db.relationship('Lesson', backref=db.backref('quizzes', lazy=True))

    def is_open(self, at=None):
        """Return True when the quiz is inside its scheduled window."""
        at = at or datetime.utcnow()
        if self.opens_at and at < self.opens_at:
            return False
        if self.closes_at and at > self.closes_at:
            return False
        return True

    def __repr__(self):
        return f'<Quiz {self.title}>'


class Question(db.Model):
    __tablename__ = 'questions'

    id = db.Column(db.Integer, primary_key=True)
    quiz_id = db.Column(db.Integer, db.ForeignKey('quizzes.id', ondelete='CASCADE'), nullable=False)
    text = db.Column(db.Text, nullable=False)
    question_type = db.Column(db.String(50), default='MCQ')
    points = db.Column(db.Integer, default=10)

    choices = db.relationship('Choice', backref='question', lazy=True, cascade="all, delete-orphan")

    def __repr__(self):
        return f'<Question {self.text[:30]}...>'


class Choice(db.Model):
    __tablename__ = 'choices'

    id = db.Column(db.Integer, primary_key=True)
    question_id = db.Column(db.Integer, db.ForeignKey('questions.id', ondelete='CASCADE'), nullable=False)
    text = db.Column(db.String(255), nullable=False)
    is_correct = db.Column(db.Boolean, default=False)

    def __repr__(self):
        return f'<Choice {self.text[:20]} Correct: {self.is_correct}>'


class QuizAttempt(db.Model):
    __tablename__ = 'quiz_attempts'

    id = db.Column(db.Integer, primary_key=True)
    quiz_id = db.Column(db.Integer, db.ForeignKey('quizzes.id', ondelete='CASCADE'), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    score = db.Column(db.Float, nullable=False)
    is_passed = db.Column(db.Boolean, default=False)
    started_at = db.Column(db.DateTime, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime, default=datetime.utcnow)

    student = db.relationship('User', backref=db.backref('quiz_attempts', lazy='dynamic'))
    answers = db.relationship(
        'QuizAttemptAnswer',
        backref='attempt',
        lazy=True,
        cascade='all, delete-orphan',
    )

    def __repr__(self):
        return f'<QuizAttempt Student {self.student_id} Score: {self.score}>'


class QuizAttemptAnswer(db.Model):
    __tablename__ = 'quiz_attempt_answers'
    __table_args__ = (
        db.UniqueConstraint('attempt_id', 'question_id', name='uq_attempt_question'),
    )

    id = db.Column(db.Integer, primary_key=True)
    attempt_id = db.Column(
        db.Integer,
        db.ForeignKey('quiz_attempts.id', ondelete='CASCADE'),
        nullable=False,
    )
    question_id = db.Column(
        db.Integer,
        db.ForeignKey('questions.id', ondelete='CASCADE'),
        nullable=False,
    )
    selected_choice_id = db.Column(
        db.Integer,
        db.ForeignKey('choices.id', ondelete='SET NULL'),
        nullable=True,
    )
    is_correct = db.Column(db.Boolean, default=False)
    points_awarded = db.Column(db.Float, default=0.0)

    question = db.relationship('Question')
    selected_choice = db.relationship('Choice')

    def __repr__(self):
        return (
            f'<QuizAttemptAnswer Attempt {self.attempt_id} '
            f'Question {self.question_id} Correct: {self.is_correct}>'
        )


class LiveClass(db.Model):
    __tablename__ = 'live_classes'

    id = db.Column(db.Integer, primary_key=True)
    course_id = db.Column(db.Integer, db.ForeignKey('courses.id', ondelete='CASCADE'), nullable=False)
    teacher_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    title = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text, nullable=True)
    meet_link = db.Column(db.String(255), nullable=True)
    start_time = db.Column(db.DateTime, nullable=False)
    duration_minutes = db.Column(db.Integer, default=60)
    is_recorded = db.Column(db.Boolean, default=False)
    recording_url = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    teacher = db.relationship('User', backref=db.backref('live_classes', lazy=True))

    def __repr__(self):
        return f'<LiveClass {self.title}>'
