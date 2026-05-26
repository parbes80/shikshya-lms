import uuid
import json
from datetime import datetime, timedelta
from flask import Blueprint, render_template, redirect, url_for, flash, request, abort, jsonify
from flask_login import login_required, current_user
from database import db
from models.user import User
from models.course import Course
from models.interaction import Payment, MembershipPlan, UserSubscription, Coupon
from models.learning import Enrollment, LessonProgress

payment_bp = Blueprint('payment', __name__)


@payment_bp.route('/membership/plans')
def plans():
    membership_plans = MembershipPlan.query.filter_by(is_active=True).all()
    return render_template('membership_plans.html', plans=membership_plans)


@payment_bp.route('/membership/subscribe', methods=['GET', 'POST'])
@login_required
def subscribe():
    if request.method == 'POST':
        plan_id = request.form.get('plan_id', type=int)
        payment_method = request.form.get('payment_method', '')
        transaction_id = request.form.get('transaction_id', '').strip()
        coupon_code = request.form.get('coupon_code', '').strip()

        plan = MembershipPlan.query.get_or_404(plan_id)
        if not plan.is_active:
            flash('This plan is no longer available.', 'danger')
            return redirect(url_for('payment.plans'))

        amount = plan.price
        discount = 0.0
        coupon = None

        if coupon_code:
            coupon = Coupon.query.filter_by(code=coupon_code.upper(), is_active=True).first()
            if not coupon:
                flash('Invalid coupon code.', 'danger')
                return redirect(url_for('payment.subscribe', plan_id=plan_id))
            if coupon.expires_at and coupon.expires_at < datetime.utcnow():
                flash('This coupon has expired.', 'danger')
                return redirect(url_for('payment.subscribe', plan_id=plan_id))
            if coupon.current_uses >= coupon.max_uses:
                flash('This coupon has reached its usage limit.', 'danger')
                return redirect(url_for('payment.subscribe', plan_id=plan_id))
            if amount < coupon.min_amount:
                flash(f'Minimum order amount Rs. {coupon.min_amount:,.0f} required for this coupon.', 'danger')
                return redirect(url_for('payment.subscribe', plan_id=plan_id))
            discount = round(amount * coupon.discount_percent / 100, 2)
            coupon.current_uses += 1

        if not transaction_id:
            flash('Please enter the transaction ID from your payment app.', 'danger')
            return redirect(url_for('payment.subscribe', plan_id=plan_id))

        final_amount = round(amount - discount, 2)
        tx_id = f"SUB-{uuid.uuid4().hex[:10].upper()}"

        payment = Payment(
            student_id=current_user.id,
            membership_plan_id=plan.id,
            amount=final_amount,
            discount_amount=discount,
            coupon_id=coupon.id if coupon else None,
            payment_method=payment_method,
            transaction_id=tx_id,
            user_transaction_id=transaction_id,
            description=f'Membership: {plan.name}',
            status='pending'
        )
        db.session.add(payment)
        db.session.commit()

        flash(f'Payment submitted for {plan.name}! Admin will verify and activate your membership shortly.', 'warning')
        return redirect(url_for('payment.history'))

    plan_id = request.args.get('plan_id', type=int)
    plan = MembershipPlan.query.get_or_404(plan_id) if plan_id else None
    return render_template('membership_checkout.html', plan=plan)


@payment_bp.route('/membership/my-plan')
@login_required
def my_plan():
    sub = UserSubscription.query.filter_by(
        user_id=current_user.id, is_active=True
    ).order_by(UserSubscription.created_at.desc()).first()
    return render_template('my_subscription.html', subscription=sub, now=datetime.utcnow)


@payment_bp.route('/payments/history')
@login_required
def history():
    payments = Payment.query.filter_by(student_id=current_user.id).order_by(Payment.created_at.desc()).all()
    return render_template('payment_history.html', payments=payments)


@payment_bp.route('/payments/<int:payment_id>')
@login_required
def payment_detail(payment_id):
    payment = Payment.query.get_or_404(payment_id)
    if payment.student_id != current_user.id and current_user.role.name != 'Admin':
        abort(403)
    return render_template('payment_detail.html', payment=payment)


@payment_bp.route('/api/coupon/validate', methods=['POST'])
@login_required
def validate_coupon():
    data = request.json or {}
    code = data.get('code', '').strip().upper()
    amount = data.get('amount', 0.0)

    coupon = Coupon.query.filter_by(code=code, is_active=True).first()
    if not coupon:
        return jsonify({'valid': False, 'message': 'Invalid coupon code.'})
    if coupon.expires_at and coupon.expires_at < datetime.utcnow():
        return jsonify({'valid': False, 'message': 'This coupon has expired.'})
    if coupon.current_uses >= coupon.max_uses:
        return jsonify({'valid': False, 'message': 'This coupon has reached its usage limit.'})
    if amount < coupon.min_amount:
        return jsonify({'valid': False, 'message': f'Minimum Rs. {coupon.min_amount:,.0f} required.'})

    discount = round(amount * coupon.discount_percent / 100, 2)
    return jsonify({
        'valid': True,
        'discount_percent': coupon.discount_percent,
        'discount_amount': discount,
        'final_amount': round(amount - discount, 2)
    })


@payment_bp.route('/membership/plans/manage')
@login_required
def manage_plans():
    if current_user.role.name != 'Admin':
        abort(403)
    plans = MembershipPlan.query.all()
    return render_template('manage_plans.html', plans=plans)


@payment_bp.route('/membership/plans/create', methods=['GET', 'POST'])
@login_required
def create_plan():
    if current_user.role.name != 'Admin':
        abort(403)
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        price = float(request.form.get('price', 0))
        duration = int(request.form.get('duration_days', 30))
        features = request.form.get('features', '').strip()
        description = request.form.get('description', '').strip()

        if not name:
            flash('Plan name is required.', 'danger')
            return redirect(url_for('payment.create_plan'))

        slug = name.lower().replace(' ', '-').replace('/', '-')
        slug = ''.join(c for c in slug if c.isalnum() or c == '-')

        plan = MembershipPlan(name=name, slug=slug, price=price, duration_days=duration, features=features, description=description)
        db.session.add(plan)
        db.session.commit()
        flash(f'Plan "{name}" created!', 'success')
        return redirect(url_for('payment.manage_plans'))

    return render_template('plan_form.html', action='create')


@payment_bp.route('/membership/plans/<int:plan_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_plan(plan_id):
    if current_user.role.name != 'Admin':
        abort(403)
    plan = MembershipPlan.query.get_or_404(plan_id)
    if request.method == 'POST':
        plan.name = request.form.get('name', '').strip()
        plan.price = float(request.form.get('price', 0))
        plan.duration_days = int(request.form.get('duration_days', 30))
        plan.features = request.form.get('features', '').strip()
        plan.description = request.form.get('description', '').strip()
        plan.is_active = request.form.get('is_active') == 'on'
        db.session.commit()
        flash(f'Plan updated!', 'success')
        return redirect(url_for('payment.manage_plans'))
    return render_template('plan_form.html', action='edit', plan=plan)


@payment_bp.route('/coupons/manage')
@login_required
def manage_coupons():
    if current_user.role.name != 'Admin':
        abort(403)
    coupons = Coupon.query.order_by(Coupon.created_at.desc()).all()
    return render_template('manage_coupons.html', coupons=coupons)


@payment_bp.route('/coupons/create', methods=['GET', 'POST'])
@login_required
def create_coupon():
    if current_user.role.name != 'Admin':
        abort(403)
    if request.method == 'POST':
        code = request.form.get('code', '').strip().upper()
        discount = int(request.form.get('discount_percent', 10))
        max_uses = int(request.form.get('max_uses', 100))
        min_amount = float(request.form.get('min_amount', 0))
        expires_str = request.form.get('expires_at', '')

        if not code:
            flash('Coupon code is required.', 'danger')
            return redirect(url_for('payment.create_coupon'))

        expires_at = None
        if expires_str:
            expires_at = datetime.strptime(expires_str, '%Y-%m-%d')

        coupon = Coupon(code=code, discount_percent=discount, max_uses=max_uses, min_amount=min_amount, expires_at=expires_at)
        db.session.add(coupon)
        db.session.commit()
        flash(f'Coupon "{code}" created!', 'success')
        return redirect(url_for('payment.manage_coupons'))

    return render_template('coupon_form.html', action='create')


@payment_bp.route('/coupons/<int:coupon_id>/toggle', methods=['POST'])
@login_required
def toggle_coupon(coupon_id):
    if current_user.role.name != 'Admin':
        abort(403)
    coupon = Coupon.query.get_or_404(coupon_id)
    coupon.is_active = not coupon.is_active
    db.session.commit()
    flash(f'Coupon {"activated" if coupon.is_active else "deactivated"}.', 'success')
    return redirect(url_for('payment.manage_coupons'))
