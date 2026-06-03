import os
from dotenv import load_dotenv

load_dotenv()

from app import create_app
from database import db
from models.user import Role, User, UserProfile, Branch
from models.course import Category, Course, Module, Lesson, Review
from models.learning import Quiz, Question, Choice, Assignment, LiveClass, Enrollment, LessonProgress
from models.interaction import Notice
from datetime import datetime, timedelta
import os


def seed_database():
    print("Seeding database...")

    # Idempotent category additions (always runs, skips if slug exists)
    for cat_data in [
        ('Web Development', 'web-development', 'fa-laptop-code'),
        ('Programming Languages', 'programming-languages', 'fa-code'),
        ('Data Science & AI', 'data-science', 'fa-brain'),
        ('UI/UX Design', 'ui-ux-design', 'fa-palette'),
        ('Class 10', 'class-10', 'fa-book-open'),
        ('Class 9', 'class-9', 'fa-book-open'),
    ]:
        if not Category.query.filter_by(slug=cat_data[1]).first():
            db.session.add(Category(name=cat_data[0], slug=cat_data[1], icon_class=cat_data[2]))
    db.session.commit()

    if Role.query.first():
        print("Database already seeded. Skipping.")
        return

    admin_role = Role(name='Admin', description='Administrator with full control')
    teacher_role = Role(name='Teacher', description='Instructor who creates courses and grades submissions')
    student_role = Role(name='Student', description='Learner who enrolls in courses')

    db.session.add_all([admin_role, teacher_role, student_role])
    db.session.commit()

    if not Branch.query.first():
        db.session.add_all([
            Branch(name='Shikshya Kathmandu Central', slug='shikshya-kathmandu-central', address='Durbar Marg, 28', city='Kathmandu', latitude=27.7172, longitude=85.3240, phone='+977-1-4234567', email='kathmandu@shikshya.edu', description='Main administrative headquarters and primary learning center.'),
            Branch(name='Shikshya Pokhara Campus', slug='shikshya-pokhara-campus', address='Lakeside Road, 12', city='Pokhara', latitude=28.2096, longitude=83.9856, phone='+977-61-523456', email='pokhara@shikshya.edu', description='Scenic lakeside campus with state-of-the-art computer labs.'),
            Branch(name='Shikshya Chitwan Center', slug='shikshya-chitwan-center', address='Bharatpur, Main Chowk', city='Chitwan', latitude=27.6818, longitude=84.4324, phone='+977-56-593456', email='chitwan@shikshya.edu', description='Regional learning hub serving central Nepal.'),
        ])
        db.session.commit()
        print("Branches seeded.")

    admin = User(username='admin', email='admin@shikshya.edu', role_id=admin_role.id, is_approved=True, avatar_url='images/avatar_default.jpg')
    admin.set_password('admin123')

    teacher = User(username='teacher_sandesh', email='teacher@shikshya.edu', role_id=teacher_role.id, is_approved=True, avatar_url='images/avatar_default.jpg')
    teacher.set_password('teacher123')

    student = User(username='student_pradeep', email='student@shikshya.edu', role_id=student_role.id, is_approved=True, avatar_url='images/avatar_default.jpg')
    student.set_password('student123')

    db.session.add_all([admin, teacher, student])
    db.session.commit()

    admin_profile = UserProfile(user_id=admin.id, bio="Senior administrator of Shikshya platform.", city="Kathmandu", latitude=27.7172, longitude=85.3240)
    teacher_profile = UserProfile(user_id=teacher.id, bio="Full Stack Engineer & educator with 8+ years of teaching experience.", qualification="M.Sc. in Computer Science", skills="Python, Django, Flask, Javascript, Docker", city="Pokhara", latitude=28.2096, longitude=83.9856)
    student_profile = UserProfile(user_id=student.id, bio="Passionate student looking to learn Python and web development.", qualification="B.E. Computer Engineering Student", skills="HTML, CSS", city="Lalitpur", latitude=27.6644, longitude=85.3188)

    db.session.add_all([admin_profile, teacher_profile, student_profile])
    db.session.commit()

    prog_cat = Category.query.filter_by(slug='programming-languages').first()
    web_dev_cat = Category.query.filter_by(slug='web-development').first()

    c1 = Course(
        title='Python for Beginners: From Zero to Hero',
        slug='python-for-beginners',
        description='Learn Python programming from scratch. This course covers variables, loops, object-oriented programming, and file operations with hands-on exercises.',
        price=0.0,
        teacher_id=teacher.id,
        category_id=prog_cat.id,
        difficulty_level='Beginner',
        thumbnail_url='course_default.jpg',
        is_published=True
    )

    c2 = Course(
        title='Modern Web Development with Flask & Vanilla CSS',
        slug='modern-web-development-flask',
        description='Master responsive layouts, premium design systems with Vanilla CSS (grids, flexbox, HSL colors), and dynamic database integration using Python Flask.',
        price=1500.0,
        teacher_id=teacher.id,
        category_id=web_dev_cat.id,
        difficulty_level='Intermediate',
        thumbnail_url='course_default.jpg',
        is_published=True
    )

    db.session.add_all([c1, c2])
    db.session.commit()

    m1 = Module(course_id=c1.id, title='Module 1: Introduction to Python', sort_order=1)
    m2 = Module(course_id=c1.id, title='Module 2: Control flow & Data structures', sort_order=2)
    db.session.add_all([m1, m2])
    db.session.commit()

    l1_1 = Lesson(
        module_id=m1.id,
        title='Lesson 1: Installing Python and Setup IDE',
        content_type='video',
        video_url='https://www.w3schools.com/html/mov_bbb.mp4',
        text_content='### Setup your environment\n\n1. Download Python from python.org.\n2. Install VS Code editor.\n3. Verify installation using `python --version` in terminal.',
        sort_order=1,
        duration_minutes=8
    )
    l1_2 = Lesson(
        module_id=m1.id,
        title='Lesson 2: Variables, Inputs, & Basic Types',
        content_type='video',
        video_url='https://www.w3schools.com/html/movie.mp4',
        text_content='### Understanding Python Variables\n\nVariables are boxes that hold data types: strings, integers, floats, and booleans.',
        sort_order=2,
        duration_minutes=12
    )

    l2_1 = Lesson(
        module_id=m2.id,
        title='Lesson 1: Conditional Statements (if/elif/else)',
        content_type='video',
        video_url='https://www.w3schools.com/html/mov_bbb.mp4',
        text_content='### Logic in python\nUse conditional branching to direct your code flow.',
        sort_order=1,
        duration_minutes=15
    )

    db.session.add_all([l1_1, l1_2, l2_1])
    db.session.commit()

    q1 = Quiz(course_id=c1.id, title='Python Basics Assessment', time_limit_minutes=10, passing_score=60)
    db.session.add(q1)
    db.session.commit()

    ques1 = Question(quiz_id=q1.id, text='What is the correct syntax to output "Hello" in Python?', question_type='MCQ', points=10)
    db.session.add(ques1)
    db.session.commit()

    ch1 = Choice(question_id=ques1.id, text='echo("Hello")', is_correct=False)
    ch2 = Choice(question_id=ques1.id, text='print("Hello")', is_correct=True)
    ch3 = Choice(question_id=ques1.id, text='printf("Hello")', is_correct=False)
    ch4 = Choice(question_id=ques1.id, text='system.out.println("Hello")', is_correct=False)

    ques2 = Question(quiz_id=q1.id, text='Python files have the extension ".py".', question_type='TF', points=10)
    db.session.add(ques2)
    db.session.commit()

    ch5 = Choice(question_id=ques2.id, text='True', is_correct=True)
    ch6 = Choice(question_id=ques2.id, text='False', is_correct=False)

    db.session.add_all([ch1, ch2, ch3, ch4, ch5, ch6])
    db.session.commit()

    a1 = Assignment(
        course_id=c1.id,
        title='Assignment 1: Build a simple CLI calculator',
        description='Write a script that takes numbers and operators as inputs and outputs the result in terminal. Save your solution as a .py file and submit here.',
        max_marks=100,
        due_date=datetime.now() + timedelta(days=7)
    )
    db.session.add(a1)
    db.session.commit()

    rev = Review(course_id=c1.id, student_id=student.id, rating=5, comment="Absolutely fantastic! Highly recommend it to everyone.", created_at=datetime.now())
    db.session.add(rev)

    enrollment = Enrollment(student_id=student.id, course_id=c1.id)
    db.session.add(enrollment)
    db.session.flush()

    for m in c1.modules:
        for l in m.lessons:
            db.session.add(LessonProgress(enrollment_id=enrollment.id, lesson_id=l.id))
    db.session.commit()

    lc1 = LiveClass(
        course_id=c1.id, teacher_id=teacher.id,
        title='Live Orientation: Python Setup & First Program',
        description='We will set up Python together, write our first Hello World, and go over the course structure.',
        meet_link='https://meet.google.com/abc-defg-hij',
        start_time=datetime.now() + timedelta(days=2),
        duration_minutes=60
    )
    db.session.add(lc1)
    db.session.commit()

    if not Notice.query.first():
        db.session.add_all([
            Notice(author_id=admin.id, title='Welcome to Shikshya!', content='We are excited to have you on board. Explore our courses, attend live sessions, and earn certificates upon completion. Happy learning!', target_role='all', is_pinned=True),
            Notice(author_id=teacher.id, title='Python Course: Week 1 Schedule', content='Week 1 starts with Python basics. Please watch the introductory video before our live orientation session on Google Meet.', target_role='student'),
            Notice(author_id=admin.id, title='Platform Maintenance Notice', content='The platform will be under maintenance on Sunday from 2 AM to 4 AM. Some services may be unavailable during this window.', target_role='all'),
        ])
        db.session.commit()
        print("Notices seeded.")

    print("Database seeding completed successfully!")


if __name__ == '__main__':
    app = create_app()
    with app.app_context():
        db.create_all()
        seed_database()
