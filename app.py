import os
from dotenv import load_dotenv

load_dotenv()

import markdown as md_lib
from flask import Flask, render_template, url_for
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from database import db, migrate
from config import Config
from models.user import User
from models.interaction import Notification
import models  # ensure all models are registered with SQLAlchemy
from utils.cloudinary_upload import init_cloudinary

csrf = CSRFProtect()
limiter = Limiter(key_func=get_remote_address)

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

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

    @app.template_filter('markdown')
    def render_markdown(text):
        if not text:
            return ''
        return md_lib.markdown(text, extensions=['fenced_code', 'tables'])

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
        if not Role.query.first():
            from seed import seed_database
            seed_database()

    return app

if __name__ == '__main__':
    app = create_app()
    app.run(debug=True, host='0.0.0.0', port=5000)
