from flask import Blueprint, render_template, request, flash, redirect, url_for
from flask_login import current_user
from models.course import Course, Category
from models.user import User
from models.interaction import Certificate
from database import db

main_bp = Blueprint('main', __name__)


@main_bp.route('/')
def home():
    if current_user.is_authenticated:
        if current_user.role.name == 'Admin':
            return redirect(url_for('dashboard.admin'))
        elif current_user.role.name == 'Teacher':
            return redirect(url_for('dashboard.teacher'))
        else:
            return redirect(url_for('dashboard.student'))

    categories = Category.query.all()
    featured_courses = Course.query.filter_by(is_published=True).limit(6).all()

    stats = {
        'students_count': User.query.join(User.role).filter(User.role.has(name='Student')).count(),
        'teachers_count': User.query.join(User.role).filter(User.role.has(name='Teacher')).count(),
        'courses_count': Course.query.filter_by(is_published=True).count(),
        'certificates_count': Certificate.query.count()
    }

    return render_template('home.html', categories=categories, featured_courses=featured_courses, stats=stats)


@main_bp.route('/about')
def about():
    return render_template('about.html')


@main_bp.route('/contact', methods=['GET', 'POST'])
def contact():
    if request.method == 'POST':
        name = request.form.get('name')
        subject = request.form.get('subject')
        flash(f'Thank you, {name}! Your message regarding "{subject}" has been sent successfully. We will get back to you shortly.', 'success')
        return redirect(url_for('main.contact'))

    return render_template('contact.html')


@main_bp.route('/verify/<unique_code>')
def verify_certificate_public(unique_code):
    certificate = Certificate.query.filter_by(unique_code=unique_code).first()
    return render_template('certificate_verify.html', certificate=certificate, valid=certificate is not None, unique_code=unique_code)
