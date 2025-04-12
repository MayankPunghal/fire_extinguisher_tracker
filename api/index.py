import os
import uuid
import datetime
import re
import base64
import pandas as pd
import io
import pytz
from wtforms.validators import Optional
from datetime import datetime, date, timedelta
import json # Keep import even if not currently used in QR data

from flask import (
    Flask, request, render_template, redirect, url_for,
    flash, send_from_directory, abort, session, send_file
)
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import (
    LoginManager, UserMixin, login_user, logout_user,
    login_required, current_user
)
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, BooleanField
from wtforms.validators import DataRequired, Length, EqualTo, ValidationError
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import qrcode
from PIL import Image # Keep PIL import for qrcode dependency
from functools import wraps
from supabase import create_client, Client
from sqlalchemy import func # Import func for count/min

# --- Configuration (Keep as is) ---
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
INSTANCE_FOLDER_PATH = '/tmp/instance'
# QR_CODE_DIR = os.path.join(INSTANCE_FOLDER_PATH, 'qrcodes') # Not used if uploading directly
STATIC_QR_ROUTE = 'qrcodes' # Not used if serving from Supabase
IST = pytz.timezone('Asia/Kolkata')
UTC = pytz.utc

# --- Directory Creation (Keep as is, useful for /tmp instance path) ---
try:
    os.makedirs(INSTANCE_FOLDER_PATH, exist_ok=True)
    # os.makedirs(QR_CODE_DIR, exist_ok=True) # Not needed if not saving QR locally
    print(f"Successfully created/ensured instance directory: {INSTANCE_FOLDER_PATH}", flush=True)
except OSError as e:
    print(f"Warning/Error creating instance directory: {e}", flush=True)

app = Flask(__name__, instance_path=INSTANCE_FOLDER_PATH, instance_relative_config=False)

# --- Environment Variable Loading (Keep as is) ---
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'a-very-secure-dev-key-placeholder')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///instance/dev.db') # Default to SQLite in instance for local dev
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
# Optional: Add logging configuration if needed
# import logging
# app.logger.setLevel(logging.INFO) # Or DEBUG

print(f"--- Using DATABASE_URL: {app.config['SQLALCHEMY_DATABASE_URI']}", flush=True)

# --- Supabase Client Initialization (Keep as is) ---
supabase: Client | None = None
if SUPABASE_URL and SUPABASE_KEY:
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        print("--- Supabase client initialized ---", flush=True)
    except Exception as e:
        # Log fatal error more clearly
        app.logger.fatal(f"Could not initialize Supabase client: {e}", exc_info=True)
else:
    print("--- Supabase client NOT initialized (Missing SUPABASE_URL or SUPABASE_KEY) ---", flush=True)

# --- DB and Extensions Initialization (Keep as is) ---
db = SQLAlchemy(app)
migrate = Migrate(app, db)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message_category = 'info'

# --- User Loader (Keep as is) ---
@login_manager.user_loader
def load_user(user_id):
    try:
        return db.session.get(User, int(user_id))
    except ValueError: # Handle cases where user_id might not be an int
        app.logger.warning(f"Invalid user_id format in session: {user_id}")
        return None
    except Exception as e: # Catch potential DB errors during load
        app.logger.error(f"Error loading user {user_id}: {e}", exc_info=True)
        return None

# --- Database Models (Keep as is) ---
class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True) # Index username
    password_hash = db.Column(db.String(256), nullable=False)
    is_admin = db.Column(db.Boolean, default=False, nullable=False, index=True) # Index is_admin
    check_logs = db.relationship('CheckInLog', back_populates='user', lazy='dynamic', cascade="all, delete")
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    def __repr__(self):
        return f'<User {self.username}>'

class Extinguisher(db.Model):
    __tablename__ = 'extinguishers' # Good practice

    # --- Ensure this line has primary_key=True ---
    id = db.Column(db.Integer, primary_key=True)
    # --- END Check ---

    unique_id = db.Column(db.String(36), unique=True, nullable=False, default=lambda: str(uuid.uuid4()), index=True)
    serial_number = db.Column(db.String(100), unique=True, nullable=False, index=True)
    location_description = db.Column(db.String(200), nullable=False)
    latitude = db.Column(db.Float, nullable=True)
    longitude = db.Column(db.Float, nullable=True)
    landmark = db.Column(db.String(200), nullable=True)
    last_checked_date = db.Column(db.DateTime, nullable=True)
    qr_code_filename = db.Column(db.String(50), nullable=True)
    image_filename = db.Column(db.String(256), nullable=True)
    # Relationships
    check_logs = db.relationship('CheckInLog', back_populates='extinguisher', lazy='dynamic', cascade="all, delete-orphan")

    def __repr__(self):
        return f'<Extinguisher {self.serial_number}>'

class CheckInLog(db.Model):
    __tablename__ = 'check_in_logs'
    id = db.Column(db.Integer, primary_key=True)
    extinguisher_id = db.Column(db.Integer, db.ForeignKey('extinguishers.id'), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    checked_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)
    comments = db.Column(db.Text, nullable=True) # Store optional comments

    # Define relationships if not already done cleanly
    user = db.relationship('User', back_populates='check_logs')
    extinguisher = db.relationship('Extinguisher', back_populates='check_logs')
    def __repr__(self):
        return f'<CheckInLog E:{self.extinguisher_id} U:{self.user_id}@{self.checked_at}>'

# --- Forms (Keep as is) ---
class LoginForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired(), Length(min=4, max=80)])
    password = PasswordField('Password', validators=[DataRequired()])
    submit = SubmitField('Login')

class AddUserForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired(), Length(min=4, max=80)])
    password = PasswordField('Password', validators=[DataRequired(), Length(min=6)])
    confirm_password = PasswordField('Confirm Password', validators=[DataRequired(), EqualTo('password', message='Passwords must match.')])
    is_admin = BooleanField('Grant Admin Privileges?')
    submit = SubmitField('Create User')
    def validate_username(self, username):
        # Optimized slightly: Check existence without fetching the whole user object
        user_exists = db.session.query(User.id).filter_by(username=username.data).first() is not None
        if user_exists:
            raise ValidationError('That username is already taken. Please choose a different one.')

class EditUserForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired(), Length(min=4, max=80)])
    is_admin = BooleanField('Grant Admin Privileges?')
    password = PasswordField('New Password (Leave blank to keep current)', validators=[Optional(), Length(min=6, message='New password must be at least 6 characters long.')])
    confirm_password = PasswordField('Confirm New Password', validators=[Optional(), EqualTo('password', message='New passwords must match.')])
    submit = SubmitField('Update User')
    original_username = None
    user_id = None
    def __init__(self, user_id, original_username, *args, **kwargs):
        super(EditUserForm, self).__init__(*args, **kwargs)
        self.original_username = original_username
        self.user_id = user_id
    def validate_username(self, username):
        if username.data != self.original_username:
            # Optimized slightly
            user_exists = db.session.query(User.id).filter_by(username=username.data).first() is not None
            if user_exists:
                raise ValidationError('That username is already taken. Please choose a different one.')

class DeleteForm(FlaskForm):
    submit = SubmitField('Delete') # CSRF protection only

# --- Decorators (Keep as is) ---
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Check authentication before accessing current_user attributes
        if not current_user.is_authenticated:
            flash("Admin privileges required. Please log in.", "warning")
            return redirect(url_for('login', next=request.url))
        if not current_user.is_admin:
            app.logger.warning(f"Unauthorized admin access attempt by user '{current_user.username}' to {request.path}")
            flash("Admin privileges required to access this page.", "warning")
            return redirect(url_for('index')) # Redirect logged-in non-admin to index
        return f(*args, **kwargs)
    return decorated_function

# --- Helper Functions ---

# REMOVED generate_qr_code (as it saved locally, not needed)

# This helper seems unused now, remove if confirmed
# def get_start_end_of_day_utc(target_date): ...

# Optimization: Use more efficient queries if possible, ensure indexes are hit
# Optimization: Pre-fetch required data if looping multiple times
def _get_report_data(target_date):
    """Fetches and processes report data for a given date. Optimized slightly."""
    report_data = []
    try:
        # Query Extinguishers and latest log for the target date in one go using LEFT JOIN
        # This is more complex but can be faster by reducing round trips and Python processing
        # Ensure indexes on extinguishers.id and check_in_logs.extinguisher_id, check_in_logs.checked_at are effective

        # Subquery to find the latest log per extinguisher ON the target date
        latest_log_subquery = db.session.query(
                CheckInLog.extinguisher_id,
                func.max(CheckInLog.checked_at).label('latest_checked_at')
            ).filter(
                func.date(CheckInLog.checked_at) == target_date
            ).group_by(CheckInLog.extinguisher_id).subquery()

        # Main query joining Extinguisher with the latest log info (if exists)
        query = db.session.query(
                Extinguisher, CheckInLog, User
            ).select_from(Extinguisher)\
            .outerjoin(latest_log_subquery, Extinguisher.id == latest_log_subquery.c.extinguisher_id)\
            .outerjoin(CheckInLog, (CheckInLog.extinguisher_id == Extinguisher.id) & (CheckInLog.checked_at == latest_log_subquery.c.latest_checked_at))\
            .outerjoin(User, CheckInLog.user_id == User.id)\
            .order_by(Extinguisher.location_description, Extinguisher.serial_number)

        results = query.all()

        for ex, log, user in results:
            checked_today = log is not None
            report_data.append({
                'extinguisher_id': ex.id,
                'unique_id': ex.unique_id,
                'serial_number': ex.serial_number,
                'location': ex.location_description,
                'checked_today': checked_today,
                'checked_at': log.checked_at if checked_today else None,
                'checked_by': user.username if checked_today and user else None,
                'comments': log.comments if checked_today else None
            })

    except Exception as e:
        # Add exc_info for full traceback in logs
        app.logger.error(f"Error fetching report data for {target_date}: {e}", exc_info=True)
        return None # Indicate error

    return report_data

# Optimization: Minimal changes, focus on error logging
def upload_extinguisher_image_from_bytes(image_bytes: bytes, content_type: str, extinguisher_unique_id: str) -> str | None:
    """Uploads extinguisher image BYTES to Supabase Storage, returns filename or None."""
    if not supabase:
        app.logger.error("Supabase client not available for image upload.")
        return None
    if not image_bytes:
        app.logger.info("No image bytes provided for upload.")
        return None

    # Determine extension (keep logic simple)
    extension = '.jpg'
    if content_type == 'image/png': extension = '.png'
    elif content_type == 'image/gif': extension = '.gif'
    elif content_type == 'image/webp': extension = '.webp'

    filename = f"{extinguisher_unique_id}_image{extension}"
    bucket_name = "extinguisher-images"

    try:
        # Add logging for upload attempt
        app.logger.info(f"Uploading {filename} ({content_type}) to Supabase bucket '{bucket_name}'...")
        response = supabase.storage.from_(bucket_name).upload(
            file=image_bytes,
            path=filename,
            file_options={"content-type": content_type, "upsert": "true"}
        )
        # Log response details (might contain useful info)
        app.logger.debug(f"Supabase image upload response: {response}")
        # Add check based on actual Supabase response if possible (e.g., check status code if available)
        # Assuming success if no exception for now
        return filename
    except Exception as e:
        # Add exc_info for full traceback
        app.logger.error(f"Error uploading extinguisher image bytes '{filename}': {e}", exc_info=True)
        return None

# Optimization: Minimal changes, ensure exc_info logging
def generate_and_upload_qr(extinguisher_unique_id: str, qr_data: str) -> str | None:
    """Generates QR code containing qr_data, uploads to Supabase Storage, returns filename or None."""
    if not supabase:
        app.logger.error("Supabase client not available for QR upload.")
        return None

    filename = f"{extinguisher_unique_id}.png"
    bucket_name = "qrcodes"

    try:
        app.logger.info(f"Generating QR for data: {qr_data}")
        # Using automatic version determination (workaround for previous error)
        qr = qrcode.QRCode(
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10, # Keep reasonably large for scannability
            border=4     # Standard border
        )
        qr.add_data(qr_data)
        qr.make(fit=True) # Let library choose smallest version
        img = qr.make_image(fill_color="black", back_color="white")

        # Use BytesIO buffer (efficient)
        img_buffer = io.BytesIO()
        img.save(img_buffer, format='PNG')
        img_buffer.seek(0)

        app.logger.info(f"Uploading {filename} to Supabase bucket '{bucket_name}'...")
        response = supabase.storage.from_(bucket_name).upload(
            file=img_buffer.getvalue(),
            path=filename,
            file_options={"content-type": "image/png", "upsert": "true"}
        )
        app.logger.debug(f"Supabase QR upload response: {response}")
        # Assuming success if no exception
        return filename
    except Exception as e:
        # Log with exc_info!
        app.logger.error(f"Error generating or uploading QR code '{filename}' with data '{qr_data}': {e}", exc_info=True)
        return None

# Optimization: Add memoization (simple cache) if format string is often the same
# For a single request, this has no effect, but shows the pattern.
_ist_format_cache = {}
@app.template_filter('datetime_ist')
def format_datetime_ist(value, format='%Y-%m-%d %I:%M:%S %p %Z'):
    """Formats a UTC datetime object into IST for display. Slightly optimized."""
    if value is None: return "N/A"
    if not isinstance(value, datetime): return value # Return original if not datetime

    # Basic cache check (only useful if the *same* format string is reused many times)
    cache_key = (value, format)
    if cache_key in _ist_format_cache:
        return _ist_format_cache[cache_key]

    # Timezone conversion logic (seems efficient enough)
    try:
        value_utc = UTC.localize(value) if value.tzinfo is None else value.astimezone(UTC)
        value_ist = value_utc.astimezone(IST)
        formatted = value_ist.strftime(format)
        _ist_format_cache[cache_key] = formatted # Store in cache
        # Basic cache cleanup (prevent infinite growth) - Better cache needed for long running app
        if len(_ist_format_cache) > 100: _ist_format_cache.clear()
        return formatted
    except Exception as e:
        app.logger.warning(f"Error formatting datetime {value} to IST: {e}")
        return "Error" # Return error string on failure

# --- Routes ---

# Login Route (Keep as is - already efficient)
@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('scan_page') if not current_user.is_admin else url_for('index'))

    form = LoginForm()
    if form.validate_on_submit():
        # Use select(User) for clarity over User.query if preferred (functionally same)
        user = db.session.scalar(db.select(User).filter_by(username=form.username.data))
        if user and user.check_password(form.password.data):
            login_user(user) # Consider adding 'remember=True' based on a form checkbox
            # flash(...) # Flashing adds minor overhead, keep if needed
            next_page = request.args.get('next')
            # Basic security check for open redirect
            if next_page and not next_page.startswith(('/', 'http://', 'https://')):
                 next_page = None
            # Role based redirect
            if user.is_admin:
                return redirect(next_page or url_for('index'))
            else:
                return redirect(url_for('scan_page'))
        else:
            flash('Login unsuccessful. Please check username and password.', 'danger')
    return render_template('login.html', title='Login', form=form)

# Logout Route (Keep as is)
@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'success')
    return redirect(url_for('login'))

# Index Route (Keep as is, query seems okay)
@app.route('/')
@login_required
def index():
    if not current_user.is_admin:
        return redirect(url_for('scan_page'))
    try:
        # Query seems acceptable, ensure indexes on order_by columns
        extinguishers = db.session.scalars(Extinguisher.query.order_by(
            Extinguisher.last_checked_date.desc().nullslast(),
            Extinguisher.location_description
        )).all()
    except Exception as e:
        app.logger.error(f"Error fetching extinguishers for index: {e}", exc_info=True)
        flash('Could not load extinguishers.', 'warning')
        extinguishers = []
    return render_template('index.html', extinguishers=extinguishers)

# Add Extinguisher Route (Keep complex logic, ensure flush is before using ID)
# This route involves network I/O (Supabase) and CPU (image/QR), hard to optimize further
# without changing functionality (e.g., background tasks)
@app.route('/add', methods=['GET', 'POST'])
@login_required
@admin_required
def add_extinguisher():
    errors = {}
    submitted_data = request.form.to_dict() if request.method == 'POST' else {}

    if request.method == 'POST':
        # --- Get Form Data ---
        serial = request.form.get('serial_number')
        location = request.form.get('location_description')
        landmark= request.form.get('landmark') # New field
        lat_str = request.form.get('latitude')
        lon_str = request.form.get('longitude')
        image_data_url = request.form.get('captured_image_data')

        # --- Process Image ---
        image_bytes, image_content_type = None, None
        if image_data_url and image_data_url.startswith('data:image'):
            try:
                match = re.match(r'data:(image/\w+);base64,(.*)', image_data_url)
                if match:
                    image_content_type = match.group(1)
                    image_bytes = base64.b64decode(match.group(2))
                else: errors['image'] = 'Invalid image data format.'
            except Exception as e: errors['image'] = 'Error processing image.'

        # --- Validate ---
        if not serial: errors['serial_number'] = 'Serial Number required.'
        if not location: errors['location'] = 'Location required.'
        lat, lon = None, None
        if lat_str:
            try: lat = float(lat_str)
            except ValueError: errors['latitude'] = 'Invalid latitude.'
        if lon_str:
            try: lon = float(lon_str)
            except ValueError: errors['longitude'] = 'Invalid longitude.'
        if serial and not errors.get('serial_number'):
             # Use exists for slight optimization over fetching full object
             exists = db.session.query(db.session.query(Extinguisher).filter_by(serial_number=serial).exists()).scalar()
             if exists: errors['serial_number'] = f'Serial number "{serial}" already exists.'

        if errors:
            flash('Please correct errors.', 'error')
            return render_template('add_extinguisher.html', errors=errors, submitted_data=submitted_data)

        # --- Create and Flush ---
        new_extinguisher = Extinguisher(serial_number=serial, location_description=location, latitude=lat, longitude=lon, landmark=landmark)
        db.session.add(new_extinguisher)
        try:
            db.session.flush() # Get ID before uploads
        except Exception as flush_err:
             db.session.rollback()
             app.logger.error(f"DB Flush Error: {flush_err}", exc_info=True)
             flash('Database error during initial save.', 'error')
             errors['general'] = 'Database error.'
             return render_template('add_extinguisher.html', errors=errors, submitted_data=submitted_data)

        # --- Uploads and Commit ---
        try:
            image_upload_filename = None
            if image_bytes:
                image_upload_filename = upload_extinguisher_image_from_bytes(image_bytes, image_content_type, new_extinguisher.unique_id)
                if image_upload_filename: new_extinguisher.image_filename = image_upload_filename
                else: flash(f'Extinguisher added, image upload failed.', 'warning')

            qr_data_to_encode = new_extinguisher.unique_id
            qr_upload_filename = generate_and_upload_qr(new_extinguisher.unique_id, qr_data_to_encode)
            if qr_upload_filename: new_extinguisher.qr_code_filename = qr_upload_filename
            else: flash(f'Extinguisher added, QR upload failed.', 'warning')

            db.session.commit()
            flash(f'Extinguisher "{serial}" added successfully!', 'success')
            return redirect(url_for('view_extinguisher', unique_id=new_extinguisher.unique_id))

        except Exception as e:
            db.session.rollback()
            app.logger.error(f"Upload/Commit Error: {e}", exc_info=True)
            flash(f'Error saving details/files: {str(e)}', 'error')
            errors['general'] = 'Error saving files or final details.'
            return render_template('add_extinguisher.html', errors=errors, submitted_data=submitted_data)

    # GET request
    return render_template('add_extinguisher.html', errors={}, submitted_data={})

# View Extinguisher Route (Optimize Supabase calls - difficult without changing structure)
@app.route('/extinguisher/<string:unique_id>')
@login_required
def view_extinguisher(unique_id):
    # Use query.options for potential relationship loading if needed later
    extinguisher = db.session.scalar(
        db.select(Extinguisher).filter_by(unique_id=unique_id)
        # .options(db.selectinload(Extinguisher.check_logs)) # Example if loading logs here
    )
    if not extinguisher: abort(404)

    qr_code_public_url, image_public_url = None, None
    if supabase:
        # These are two separate network calls - unavoidable for public URLs this way
        if extinguisher.qr_code_filename:
            try:
                qr_code_public_url = supabase.storage.from_("qrcodes").get_public_url(extinguisher.qr_code_filename)
            except Exception as e: app.logger.error(f"QR URL Error: {e}", exc_info=True)
        if extinguisher.image_filename:
            try:
                image_public_url = supabase.storage.from_("extinguisher-images").get_public_url(extinguisher.image_filename)
            except Exception as e: app.logger.error(f"Image URL Error: {e}", exc_info=True)
    limit_history_count = 5
    check_history = []
    check_history = extinguisher.check_logs        
            
    # Pass can_view_qr directly if needed in template logic
    return render_template('view_extinguisher.html',
                           extinguisher=extinguisher,
                           qr_code_public_url=qr_code_public_url,
                           image_public_url=image_public_url,
                           can_view_qr=current_user.is_admin,
                           check_history=check_history,
                           history_limit=limit_history_count)

# Scan Page Route (Keep as is)
@app.route('/scan')
@login_required
def scan_page():
    return render_template('scan.html')


# Daily Report Route (Optimized _get_report_data helper, minor tweak for total count)
@app.route('/admin/report')
@login_required
@admin_required
def daily_report():
    min_report_date_str = None
    try:
        # Use func.min directly
        min_dt = db.session.scalar(db.select(func.min(CheckInLog.checked_at)))
        if min_dt: min_report_date_str = min_dt.date().isoformat()
    except Exception as e: app.logger.error(f"Min Date Error: {e}", exc_info=True)

    target_date = date.today()
    date_str = request.args.get('report_date')
    if date_str:
        try:
            target_date = date.fromisoformat(date_str)
            if min_report_date_str and date_str < min_report_date_str:
                 flash(f"Report date cannot be before first record ({min_report_date_str}).", "warning")
                 # Decide how to handle this - maybe default to min_date?
        except ValueError: flash("Invalid date format.", "error")

    report_data_list = _get_report_data(target_date) # Use optimized helper

    checked_count, total_extinguishers, missed_count = 0, 0, 0
    if report_data_list is None:
        flash("Error generating report data.", "error")
        template_report_data = [] # Ensure it's an empty list for template
    elif report_data_list:
        total_extinguishers = len(report_data_list)
        checked_count = sum(1 for item in report_data_list if item['checked_today'])
        missed_count = total_extinguishers - checked_count
        # Pass the list directly if template handles dict items
        template_report_data = report_data_list
    else:
        # If list is empty, get total count efficiently
        try:
             total_extinguishers = db.session.query(func.count(Extinguisher.id)).scalar()
        except Exception as e:
             app.logger.error(f"Error counting total extinguishers: {e}", exc_info=True)
             total_extinguishers = 0 # Default to 0 on error
        template_report_data = []

    return render_template('report.html',
                           report_data=template_report_data,
                           target_date=target_date,
                           today_date_str=date.today().isoformat(),
                           checked_count=checked_count,
                           total_extinguishers=total_extinguishers,
                           missed_count=missed_count,
                           min_report_date=min_report_date_str)


# Check Extinguisher Route (Seems efficient - minimal DB operations)
# @app.route('/check/<string:unique_id>', methods=['GET'])
# @login_required
# def check_extinguisher(unique_id):
#     # Use scalar for single result check
#     extinguisher = db.session.scalar(db.select(Extinguisher).filter_by(unique_id=unique_id))

#     if extinguisher:
#         try:
#             now_utc = datetime.utcnow() # Get time once
#             extinguisher.last_checked_date = now_utc # Update timestamp
#             # Create log efficiently
#             new_log = CheckInLog(extinguisher_id=extinguisher.id, user_id=current_user.id, checked_at=now_utc)
#             db.session.add(new_log)
#             db.session.commit() # Commit both changes
#             flash(f'Extinguisher {extinguisher.serial_number} checked by {current_user.username}!', 'success')
#             # Consider redirecting to scan page for quicker next scan? Or keep view page.
#             return redirect(url_for('view_extinguisher', unique_id=unique_id))
#         except Exception as e:
#             db.session.rollback()
#             app.logger.error(f"Check-in Error (E:{unique_id}, U:{current_user.username}): {e}", exc_info=True)
#             flash(f'Error updating status: {str(e)}', 'error')
#             return redirect(url_for('index')) # Redirect to index on error
#     else:
#         flash('Invalid QR Code - Extinguisher not found.', 'error')
#         return redirect(url_for('scan_page'))

# --- Check Extinguisher - Step 1: Show Confirmation Page ---
# KEEP THIS FUNCTION - It correctly handles the initial GET request after scanning
@app.route('/check/<string:unique_id>', methods=['GET'])
@login_required # Any logged-in user can trigger a check via scanning
def check_extinguisher_confirm(unique_id):
    extinguisher = db.session.scalar(
        db.select(Extinguisher).filter_by(unique_id=unique_id)
    )
    if not extinguisher:
        flash('Invalid QR Code scanned - Extinguisher not found.', 'error')
        # Redirect user back to scanner if they came from there, or index
        # Use request.referrer for slightly better UX if possible
        redirect_url = url_for('scan_page')
        if current_user.is_admin:
            redirect_url = url_for('index')
        # Try using referrer if available and safe
        if request.referrer and request.referrer.startswith(request.host_url):
             redirect_url = request.referrer

        return redirect(redirect_url)


    # Prepare data for the confirmation page
    now_utc = datetime.utcnow()
    # Format time for display on confirmation page
    now_ist_str = format_datetime_ist(now_utc, '%d %b %Y, %I:%M:%S %p %Z') # Use the filter

    # Render the confirmation template
    # Generate CSRF token if using Flask-WTF
    # Ensure CSRFProtect(app) is initialized if using this
    csrf_token_val = None
    try:
        from flask_wtf.csrf import generate_csrf
        csrf_token_val = generate_csrf()
    except ImportError:
        app.logger.warning("Flask-WTF CSRF not fully configured for check-in confirm.")
        # Proceed without CSRF token if Flask-WTF/CSRFProtect not set up


    return render_template('check_in_confirm.html',
                        extinguisher=extinguisher,
                        check_time_ist_str=now_ist_str,
                        csrf_token=csrf_token_val) # Pass token (might be None)
    
@app.route('/process_check_in/<string:unique_id>', methods=['POST'])
@login_required
def process_check_in(unique_id):
     # Optional: Add CSRF validation here if using Flask-WTF form on confirm page
     # from flask_wtf.csrf import validate_csrf
     # try:
     #     validate_csrf(request.form.get('csrf_token'))
     # except ValidationError:
     #     flash("CSRF validation failed. Please try again.", "error")
     #     return redirect(url_for('index')) # Or appropriate error page

    extinguisher = db.session.scalar(
        db.select(Extinguisher).filter_by(unique_id=unique_id)
    )
    if not extinguisher:
        flash('Extinguisher not found during check-in processing.', 'error')
        return redirect(url_for('index'))

    comments_text = request.form.get('comments', None)
    if comments_text: # Ensure empty strings become None
         comments_text = comments_text.strip() or None

    try:
        now_utc = datetime.utcnow() # Record final time

        # 1. Update the last checked date on the extinguisher
        extinguisher.last_checked_date = now_utc

        # 2. Create a new log entry WITH comments
        new_log = CheckInLog(
            extinguisher_id=extinguisher.id,
            user_id=current_user.id,
            checked_at=now_utc,
            comments=comments_text # Save the comments
        )
        db.session.add(new_log)

        # 3. Commit changes
        db.session.commit()

        flash(f'Extinguisher {extinguisher.serial_number} checked in successfully by {current_user.username}!', 'success')
        # Redirect to view page after successful check-in
        return redirect(url_for('view_extinguisher', unique_id=unique_id))

    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Error processing check-in for {unique_id} by {current_user.username}: {e}", exc_info=True)
        flash(f'Error saving check-in data: {str(e)}', 'error')
        # Redirect back to confirmation page or index on error
        return redirect(url_for('check_extinguisher_confirm', unique_id=unique_id))

# Export Report Route (Pandas/Excel inherently slow, minor date format optimization)
@app.route('/admin/report/export')
@login_required
@admin_required
def export_report():
    date_str = request.args.get('report_date')
    target_date = date.today()
    if date_str:
        try: target_date = date.fromisoformat(date_str)
        except ValueError:
            flash("Invalid date format for export.", "error")
            return redirect(url_for('daily_report'))

    report_data_list = _get_report_data(target_date) # Use optimized helper

    if report_data_list is None:
        flash("Error generating report data for export.", "error")
        return redirect(url_for('daily_report', report_date=target_date.isoformat()))
    if not report_data_list:
        flash("No data to export for this date.", "info")
        return redirect(url_for('daily_report', report_date=target_date.isoformat()))

    # --- Prepare data for DataFrame ---
    # Pre-calculate timezone objects if needed often (already done globally)
    excel_data = []
    for item in report_data_list:
        checked_at_str = "-"
        if item['checked_at']:
             # Reuse filter logic slightly more directly
             try:
                 # Assuming checked_at is naive UTC from DB or already timezone-aware
                 value_utc = UTC.localize(item['checked_at']) if item['checked_at'].tzinfo is None else item['checked_at'].astimezone(UTC)
                 value_ist = value_utc.astimezone(IST)
                 checked_at_str = value_ist.strftime('%Y-%m-%d %I:%M:%S %p') # Slightly cleaner format for Excel?
             except Exception: # Catch potential errors during conversion
                 checked_at_str = "Error"

        excel_data.append({
            'Serial Number': item['serial_number'],
            'Location': item['location'],
            'Status': 'Checked' if item['checked_today'] else 'Missed',
            'Checked Time (IST)': checked_at_str,
            'Checked By': item['checked_by'] if item['checked_by'] else '-',
            'Comments': item['comments'] if item['comments'] else '-'
        })

    try:
        df = pd.DataFrame(excel_data)
        output_buffer = io.BytesIO()
        # Consider using xlsxwriter engine if openpyxl is slow and features aren't needed
        # with pd.ExcelWriter(output_buffer, engine='xlsxwriter') as writer:
        with pd.ExcelWriter(output_buffer, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name=f'Report_{target_date.isoformat()}', index=False)
        output_buffer.seek(0)
    except Exception as e:
        app.logger.error(f"Error generating Excel file: {e}", exc_info=True)
        flash("Error creating Excel file.", "error")
        return redirect(url_for('daily_report', report_date=target_date.isoformat()))

    return send_file(
        output_buffer,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=f'fire_extinguisher_report_{target_date.isoformat()}.xlsx'
    )

# --- DB Init Function (Keep as is) ---
def init_db(drop_all=False):
     with app.app_context():
        app.logger.info("Attempting DB init...")
        try:
            if drop_all:
                app.logger.info("Dropping all tables...")
                db.drop_all()
            app.logger.info("Creating tables (if they don't exist)...")
            db.create_all()
            app.logger.info(f"DB tables ensured/created.")
            # Create Default Admin User (use optimized existence check)
            admin_username = 'admin'
            admin_pw = 'admin@1234'
            admin_exists = db.session.query(User.id).filter_by(username=admin_username).first() is not None
            if not admin_exists:
                app.logger.info(f"Creating default admin user '{admin_username}'...")
                admin_user = User(username=admin_username, is_admin=True)
                admin_user.set_password(admin_pw)
                db.session.add(admin_user)
                try:
                    db.session.commit()
                    app.logger.info(f"Default admin user created.")
                except Exception as commit_error:
                    db.session.rollback()
                    app.logger.error(f"Error committing default admin user: {commit_error}", exc_info=True)
            else:
                app.logger.info(f"Default admin user already exists.")
        except Exception as e:
            app.logger.error(f"Error during DB initialization: {e}", exc_info=True)

# --- User Management Routes (Keep as is - standard CRUD, already reasonably efficient) ---
@app.route('/admin/users')
@login_required
@admin_required
def user_list():
    try:
        # Select specific columns if not all are needed? Minor optimization.
        # users = db.session.query(User.id, User.username, User.is_admin).order_by(User.username).all()
        users = db.session.scalars(db.select(User).order_by(User.username)).all()
    except Exception as e:
        app.logger.error(f"Error fetching user list: {e}", exc_info=True)
        flash("Could not retrieve user list.", "error")
        users = []
    delete_form = DeleteForm()
    return render_template('user_list.html', users=users, delete_form=delete_form)

@app.route('/admin/add_user', methods=['GET', 'POST'])
@login_required
@admin_required
def add_user():
    form = AddUserForm()
    if form.validate_on_submit():
        # Validation checks uniqueness
        new_user = User(username=form.username.data, is_admin=form.is_admin.data)
        new_user.set_password(form.password.data)
        try:
            db.session.add(new_user)
            db.session.commit()
            flash(f'User "{form.username.data}" created successfully!', 'success')
            return redirect(url_for('user_list'))
        except Exception as e:
            db.session.rollback()
            app.logger.error(f"Error creating user {form.username.data}: {e}", exc_info=True)
            flash(f'Error creating user: {str(e)}', 'error')
    return render_template('add_user.html', title='Add New User', form=form)

@app.route('/admin/users/<int:user_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_user(user_id):
    user_to_edit = db.session.get(User, user_id) # Efficient lookup
    if not user_to_edit: abort(404)

    form = EditUserForm(user_id=user_to_edit.id, original_username=user_to_edit.username, obj=user_to_edit)

    if form.validate_on_submit():
        # Safeguards for admin demotion (keep logic)
        if user_to_edit.is_admin and not form.is_admin.data:
            admin_count = db.session.query(func.count(User.id)).filter_by(is_admin=True).scalar()
            if admin_count <= 1:
                 flash("Cannot remove admin status from the last admin.", "error")
                 return render_template('edit_user.html', form=form, user=user_to_edit)
            if user_to_edit.id == current_user.id:
                  flash("You cannot revoke your own admin status.", "error")
                  return render_template('edit_user.html', form=form, user=user_to_edit)

        # Update fields
        user_to_edit.username = form.username.data
        user_to_edit.is_admin = form.is_admin.data
        password_updated = False
        if form.password.data:
            try:
                user_to_edit.set_password(form.password.data)
                password_updated = True
            except Exception as e:
                 app.logger.error(f"Error setting password for {user_to_edit.username}: {e}", exc_info=True)
                 flash('Error updating password.', 'error')
                 return render_template('edit_user.html', form=form, user=user_to_edit)

        try:
            db.session.commit()
            flash_msg = f'User "{user_to_edit.username}" updated.'
            if password_updated: flash_msg += ' Password changed.'
            flash(flash_msg, 'success')
            return redirect(url_for('user_list'))
        except Exception as e:
            db.session.rollback()
            app.logger.error(f"Error updating user {user_to_edit.username}: {e}", exc_info=True)
            flash(f'Error updating user: {str(e)}', 'error')

    return render_template('edit_user.html', title='Edit User', form=form, user=user_to_edit)


@app.route('/admin/users/<int:user_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_user(user_id):
    form = DeleteForm() # CSRF check
    if form.validate_on_submit():
        user_to_delete = db.session.get(User, user_id) # Efficient lookup
        if not user_to_delete: abort(404)

        # Safeguards (keep logic)
        if user_to_delete.username == 'admin':
            flash("Cannot delete primary 'admin' user.", "error")
            return redirect(url_for('user_list'))
        if user_to_delete.id == current_user.id:
            flash("Cannot delete yourself.", "error")
            return redirect(url_for('user_list'))
        if user_to_delete.is_admin:
             admin_count = db.session.query(func.count(User.id)).filter_by(is_admin=True).scalar()
             if admin_count <= 1:
                 flash("Cannot delete the last admin.", "error")
                 return redirect(url_for('user_list'))

        # Check for related logs (using exists for efficiency)
        has_logs = db.session.query(db.session.query(CheckInLog).filter_by(user_id=user_id).exists()).scalar()
        if has_logs:
             flash(f"Cannot delete user '{user_to_delete.username}' with existing check-in logs.", "warning")
             return redirect(url_for('user_list'))

        try:
            username = user_to_delete.username
            db.session.delete(user_to_delete)
            db.session.commit()
            flash(f'User "{username}" deleted.', 'success')
        except Exception as e:
            db.session.rollback()
            app.logger.error(f"Error deleting user ID {user_id}: {e}", exc_info=True)
            flash(f'Error deleting user: {str(e)}', 'error')
    else:
        flash("Invalid delete request.", "error") # CSRF failed
    return redirect(url_for('user_list'))

# --- CLI Commands (Keep as is) ---
@app.cli.command('create-admin')
def create_admin_command():
    """Creates the initial admin user."""
    # (Keep existing logic, it's run rarely)
    init_db() # Ensure tables exist before trying to add admin

# --- App Context / DB Setup Call (Keep as is) ---
# Remove the initial call to init_db() here if using Flask-Migrate properly
# Let migrations handle DB creation/updates after initial 'flask db init' and 'flask db upgrade'
# with app.app_context():
#    print("--- Running initial DB setup check ---", flush=True)
#    init_db() # Can comment out if migrations handle everything
#    print("--- Initial DB setup check complete ---", flush=True)

# --- Run for Local Development (Keep as is) ---
if __name__ == '__main__':
    # Optional: Check for DB file only if using SQLite default
    # db_path = os.path.join(app.instance_path, "dev.db")
    # if app.config['SQLALCHEMY_DATABASE_URI'] == f'sqlite:///{db_path}' and not os.path.exists(db_path):
    #     with app.app_context():
    #          print("SQLite Database file not found, initializing...")
    #          init_db()

    port = int(os.environ.get('PORT', 5001))
    # Set debug=False for performance testing, True for development
    app.run(debug=os.environ.get('FLASK_DEBUG', 'False').lower() == 'true', host='0.0.0.0', port=port)