# Import all models to ensure they are registered with SQLAlchemy
from database import db
from models.user import Role, User, UserProfile
from models.course import Category, Course, Module, Lesson, Review
from models.learning import Enrollment, LessonProgress, Assignment, Submission, Quiz, Question, Choice, QuizAttempt, LiveClass
from models.interaction import Certificate, DiscussionTopic, DiscussionReply, Notification, Payment, Attendance, Notice, MembershipPlan, UserSubscription, Coupon, Lab, PasswordResetRequest, PasswordResetToken
from models.user import Branch
from models.evaluation import Evaluation, EvaluationSubmission
