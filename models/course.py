from datetime import datetime
from database import db


class Category(db.Model):
    __tablename__ = 'categories'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    slug = db.Column(db.String(100), unique=True, nullable=False)
    icon_class = db.Column(db.String(50), default='fa-graduation-cap')

    courses = db.relationship('Course', backref='category', lazy=True)

    def __repr__(self):
        return f'<Category {self.name}>'


class Course(db.Model):
    __tablename__ = 'courses'

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(150), nullable=False)
    slug = db.Column(db.String(150), unique=True, nullable=False)
    description = db.Column(db.Text, nullable=False)
    thumbnail_url = db.Column(db.String(255), default='course_default.jpg')
    price = db.Column(db.Float, default=0.0)
    teacher_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey('categories.id'), nullable=False)
    difficulty_level = db.Column(db.String(50), default='Beginner')
    is_published = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    teacher = db.relationship('User', backref=db.backref('taught_courses', lazy=True))
    modules = db.relationship('Module', backref='course', lazy=True, order_by='Module.sort_order', cascade="all, delete-orphan")
    enrollments = db.relationship('Enrollment', backref='course', lazy=True, cascade="all, delete-orphan")
    assignments = db.relationship('Assignment', backref='course', lazy=True, cascade="all, delete-orphan")
    quizzes = db.relationship('Quiz', backref='course', lazy=True, cascade="all, delete-orphan")
    reviews = db.relationship('Review', backref='course', lazy=True, cascade="all, delete-orphan")
    topics = db.relationship('DiscussionTopic', backref='course', lazy=True, cascade="all, delete-orphan")
    certificates = db.relationship('Certificate', backref='course', lazy=True, cascade="all, delete-orphan")
    payments = db.relationship('Payment', backref='course', lazy=True, cascade="all, delete-orphan")
    attendance = db.relationship('Attendance', backref='course', lazy=True, cascade="all, delete-orphan")
    live_classes = db.relationship('LiveClass', backref='course', lazy=True, cascade="all, delete-orphan")

    def __repr__(self):
        return f'<Course {self.title}>'


class Module(db.Model):
    __tablename__ = 'modules'

    id = db.Column(db.Integer, primary_key=True)
    course_id = db.Column(db.Integer, db.ForeignKey('courses.id', ondelete='CASCADE'), nullable=False)
    title = db.Column(db.String(150), nullable=False)
    sort_order = db.Column(db.Integer, default=1)

    lessons = db.relationship('Lesson', backref='module', lazy=True, order_by='Lesson.sort_order', cascade="all, delete-orphan")

    def __repr__(self):
        return f'<Module {self.title}>'


class Lesson(db.Model):
    __tablename__ = 'lessons'

    id = db.Column(db.Integer, primary_key=True)
    module_id = db.Column(db.Integer, db.ForeignKey('modules.id', ondelete='CASCADE'), nullable=False)
    title = db.Column(db.String(150), nullable=False)
    content_type = db.Column(db.String(50), default='video')
    video_url = db.Column(db.String(255), nullable=True)
    document_url = db.Column(db.String(255), nullable=True)
    text_content = db.Column(db.Text, nullable=True)
    sort_order = db.Column(db.Integer, default=1)
    duration_minutes = db.Column(db.Integer, default=10)

    progresses = db.relationship('LessonProgress', backref='lesson', lazy=True, cascade="all, delete-orphan")

    def __repr__(self):
        return f'<Lesson {self.title}>'


class Review(db.Model):
    __tablename__ = 'reviews'

    id = db.Column(db.Integer, primary_key=True)
    course_id = db.Column(db.Integer, db.ForeignKey('courses.id', ondelete='CASCADE'), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    rating = db.Column(db.Integer, nullable=False)
    comment = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    student = db.relationship('User', backref=db.backref('reviews', lazy=True))

    def __repr__(self):
        return f'<Review {self.rating} stars for Course ID {self.course_id}>'
