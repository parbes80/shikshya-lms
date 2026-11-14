import os
from dotenv import load_dotenv

load_dotenv()

import click
from flask import Flask, render_template, url_for, request, redirect, abort
from flask_login import LoginManager
from werkzeug.middleware.proxy_fix import ProxyFix
from database import db, migrate
from config import Config
from extensions import csrf, limiter
from models.user import User, Role, UserProfile
from models.interaction import Notification
import models  # ensure all models are registered with SQLAlchemy
from utils.cloudinary_upload import init_cloudinary
from utils.sanitize import render_markdown, sanitize_html


def create_app(config_overrides=None):
    app = Flask(__name__)
    app.config.from_object(Config)

    # Allow tests and alternate entry points to override configuration.
    if config_overrides:
        if isinstance(config_overrides, dict):
            app.config.update(config_overrides)
        else:
            app.config.from_object(config_overrides)

    # Only honour X-Forwarded-* when the deployment terminates TLS/HTTP at a
    # trusted reverse proxy. Enabling it on a directly exposed server would let
    # clients spoof their IP address and the request scheme.
    if app.config.get('TRUST_PROXY_HEADERS'):
        app.wsgi_app = ProxyFix(
            app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1
        )

    db.init_app(app)
    migrate.init_app(app, db)
    Config.init_app(app)
    csrf.init_app(app)
    limiter.init_app(app)

    login_manager = LoginManager()
    login_manager.login_view = 'auth.login'
    login_manager.login_message_category = 'warning'
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    init_cloudinary(app)

    @app.template_filter('asset_url')
    def asset_url(path):
        if not path:
            return ''
        if path.startswith(('http://', 'https://', '//')):
            return path
        return url_for('static', filename=path)

    @app.template_filter('nl2br')
    def nl2br_filter(text):
        if not text:
            return ''
        import html
        escaped = html.escape(text)
        return escaped.replace('\n', '<br>\n')

    @app.template_filter('markdown')
    def render_markdown_filter(text):
        # Markdown output is sanitized before it reaches the ``safe`` filter.
        return render_markdown(text)

    @app.template_filter('sanitize')
    def sanitize_filter(text):
        return sanitize_html(text)

    @app.before_request
    def enforce_https():
        if not app.config.get('FORCE_HTTPS'):
            return None
        if request.is_secure:
            return None
        if request.method in ('GET', 'HEAD'):
            return redirect(request.url.replace('http://', 'https://', 1), code=301)
        # Never replay a POST body over an insecure connection.
        abort(400, 'HTTPS is required.')

    @app.after_request
    def set_security_headers(response):
        response.headers.setdefault('X-Content-Type-Options', 'nosniff')
        response.headers.setdefault('X-Frame-Options', 'SAMEORIGIN')
        response.headers.setdefault('Referrer-Policy', 'strict-origin-when-cross-origin')
        response.headers.setdefault(
            'Permissions-Policy', 'geolocation=(), microphone=(), camera=()'
        )
        if app.config.get('ENABLE_CSP_REPORT_ONLY'):
            response.headers.setdefault(
                'Content-Security-Policy-Report-Only',
                app.config.get('CONTENT_SECURITY_POLICY_REPORT_ONLY', ''),
            )
        if request.is_secure:
            response.headers.setdefault(
                'Strict-Transport-Security',
                'max-age=31536000; includeSubDomains',
            )
        return response

    from routes.auth import auth_bp
    from routes.main import main_bp
    from routes.dashboard import dashboard_bp
    from routes.course import course_bp
    from routes.api import api_bp
    from routes.branch import branch_bp
    from routes.notice import notice_bp
    from routes.payment import payment_bp
    from routes.lab import lab_bp
    from routes.evaluation import eval_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(course_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(branch_bp)
    app.register_blueprint(notice_bp)
    app.register_blueprint(payment_bp)
    app.register_blueprint(lab_bp)
    app.register_blueprint(eval_bp)

    @app.context_processor
    def inject_global_data():
        import datetime
        from flask_login import current_user
        unread_notifications = []
        if current_user.is_authenticated:
            unread_notifications = Notification.query.filter_by(
                user_id=current_user.id, is_read=False
            ).order_by(Notification.created_at.desc()).all()

        return {
            'site_name': 'Shikshya',
            'current_year': datetime.datetime.now().year,
            'unread_notifications': unread_notifications
        }

    @app.errorhandler(404)
    def page_not_found(e):
        return render_template('errors/404.html'), 404

    @app.errorhandler(403)
    def forbidden(e):
        return render_template('errors/403.html'), 403

    @app.errorhandler(500)
    def internal_error(e):
        return render_template('errors/500.html'), 500

    @app.errorhandler(429)
    def ratelimit_exceeded(e):
        return render_template('errors/429.html'), 429

    @app.cli.command('create-admin')
    @click.option('--email', prompt='Admin email')
    @click.option('--username', prompt='Admin username')
    @click.option('--password', prompt=True, hide_input=True, confirmation_prompt=True)
    @click.option('--full-name', default='', help='Optional display name')
    def create_admin(email, username, password, full_name):
        """Create or promote an administrator without demo credentials."""
        email = email.strip().lower()
        username = username.strip()
        if not email or not username:
            raise click.ClickException('Email and username are required.')
        if len(password) < 8:
            raise click.ClickException('Password must be at least 8 characters.')

        with app.app_context():
            from seed import ensure_roles
            ensure_roles()
            admin_role = Role.query.filter_by(name='Admin').first()
            if admin_role is None:
                raise click.ClickException('Admin role could not be created.')

            user = User.query.filter(
                (User.email == email) | (User.username == username)
            ).first()
            if user:
                user.email = email
                user.username = username
                user.role_id = admin_role.id
                user.is_approved = True
                if full_name:
                    user.full_name = full_name
                user.set_password(password)
                click.echo(f'Updated existing user "{username}" and granted Admin access.')
            else:
                user = User(
                    username=username,
                    full_name=full_name or username,
                    email=email,
                    role_id=admin_role.id,
                    is_approved=True,
                    avatar_url='images/avatar_default.jpg',
                )
                user.set_password(password)
                db.session.add(user)
                db.session.flush()
                db.session.add(UserProfile(user_id=user.id))
                click.echo(f'Created administrator "{username}".')
            db.session.commit()

    if app.config.get('AUTO_INIT_DB', True):
        with app.app_context():
            import sqlalchemy as sa
            from models.user import Role
            if not sa.inspect(db.engine).get_table_names():
                db.create_all()
                app.logger.info('Created database tables')
            else:
                insp = sa.inspect(db.engine)
                existing_tables = insp.get_table_names()
                cols = [c['name'] for c in insp.get_columns('payments')] if 'payments' in existing_tables else []
                if 'user_transaction_id' not in cols:
                    db.session.execute(sa.text('ALTER TABLE payments ADD COLUMN user_transaction_id VARCHAR(255)'))
                    db.session.commit()
                    app.logger.info('Added user_transaction_id column to payments')
                if 'labs' not in existing_tables:
                    db.create_all()
                    app.logger.info('Created new tables (labs)')
                if 'password_reset_tokens' not in existing_tables:
                    db.create_all()
                    app.logger.info('Created new tables (password_reset_tokens)')
                if 'password_reset_requests' not in existing_tables:
                    db.create_all()
                    app.logger.info('Created new tables (password_reset_requests)')
                if 'evaluations' not in existing_tables:
                    db.create_all()
                    app.logger.info('Created new tables (evaluations)')
                if 'lab_manuals' not in existing_tables:
                    db.create_all()
                    app.logger.info('Created new tables (lab_manuals)')
                if 'evaluations' in existing_tables:
                    ecols = [c['name'] for c in insp.get_columns('evaluations')]
                    if 'question_pdf_url' not in ecols:
                        db.session.execute(sa.text('ALTER TABLE evaluations ADD COLUMN question_pdf_url VARCHAR(255)'))
                        db.session.commit()
                        app.logger.info('Added question_pdf_url column to evaluations')
                    if 'meet_link' not in ecols:
                        db.session.execute(sa.text('ALTER TABLE evaluations ADD COLUMN meet_link VARCHAR(255)'))
                        db.session.commit()
                        app.logger.info('Added meet_link column to evaluations')
                if 'full_name' not in [c['name'] for c in insp.get_columns('users')]:
                    db.session.execute(sa.text('ALTER TABLE users ADD COLUMN full_name VARCHAR(120)'))
                    db.session.commit()
                    app.logger.info('Added full_name column to users')
                if 'quizzes' in existing_tables and 'lesson_id' not in [c['name'] for c in insp.get_columns('quizzes')]:
                    db.session.execute(sa.text('ALTER TABLE quizzes ADD COLUMN lesson_id INTEGER REFERENCES lessons(id) ON DELETE SET NULL'))
                    db.session.commit()
                    app.logger.info('Added lesson_id column to quizzes')
                if 'quizzes' in existing_tables and 'max_attempts' not in [c['name'] for c in insp.get_columns('quizzes')]:
                    db.session.execute(sa.text('ALTER TABLE quizzes ADD COLUMN max_attempts INTEGER DEFAULT 0'))
                    db.session.commit()
                    app.logger.info('Added max_attempts column to quizzes')
                if 'quizzes' in existing_tables:
                    quiz_cols = [c['name'] for c in insp.get_columns('quizzes')]
                    if 'opens_at' not in quiz_cols:
                        db.session.execute(sa.text('ALTER TABLE quizzes ADD COLUMN opens_at TIMESTAMP'))
                        db.session.commit()
                        app.logger.info('Added opens_at column to quizzes')
                    if 'closes_at' not in quiz_cols:
                        db.session.execute(sa.text('ALTER TABLE quizzes ADD COLUMN closes_at TIMESTAMP'))
                        db.session.commit()
                        app.logger.info('Added closes_at column to quizzes')
                    if 'results_published' not in quiz_cols:
                        db.session.execute(sa.text('ALTER TABLE quizzes ADD COLUMN results_published BOOLEAN DEFAULT TRUE'))
                        db.session.commit()
                        app.logger.info('Added results_published column to quizzes')
                if 'quiz_attempt_answers' not in existing_tables:
                    db.create_all()
                    app.logger.info('Created new tables (quiz_attempt_answers)')
                if 'lessons' in existing_tables and 'publish_at' not in [c['name'] for c in insp.get_columns('lessons')]:
                    db.session.execute(sa.text('ALTER TABLE lessons ADD COLUMN publish_at TIMESTAMP'))
                    db.session.commit()
                    app.logger.info('Added publish_at column to lessons')
                if 'assignments' in existing_tables and 'allow_late_submission' not in [c['name'] for c in insp.get_columns('assignments')]:
                    db.session.execute(sa.text('ALTER TABLE assignments ADD COLUMN allow_late_submission BOOLEAN DEFAULT TRUE'))
                    db.session.commit()
                    app.logger.info('Added allow_late_submission column to assignments')
                if 'submissions' in existing_tables and 'text_content' not in [c['name'] for c in insp.get_columns('submissions')]:
                    db.session.execute(sa.text('ALTER TABLE submissions ADD COLUMN text_content TEXT'))
                    db.session.commit()
                    app.logger.info('Added text_content column to submissions')
            # Roles are infrastructure, not demo data: always ensure they exist
            # so registration and the create-admin CLI work on a fresh database.
            from seed import ensure_roles, seed_database
            ensure_roles()
            if app.config.get('SEED_DEMO_DATA', False):
                seed_database()
            else:
                app.logger.info(
                    'Demo data seeding disabled (SEED_DEMO_DATA is not true).'
                )

    return app

if __name__ == '__main__':
    app = create_app()
    app.run(debug=True, host='0.0.0.0', port=5000)
