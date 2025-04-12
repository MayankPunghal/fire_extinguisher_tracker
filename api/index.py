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
import json

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
from PIL import Image
from functools import wraps
from supabase import create_client, Client

# --- Configuration ---
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
INSTANCE_FOLDER_PATH = '/tmp/instance'
QR_CODE_DIR = os.path.join(INSTANCE_FOLDER_PATH, 'qrcodes')
STATIC_QR_ROUTE = 'qrcodes'
IST = pytz.timezone('Asia/Kolkata')
UTC = pytz.utc


try:
    os.makedirs(INSTANCE_FOLDER_PATH, exist_ok=True)
    os.makedirs(QR_CODE_DIR, exist_ok=True)
    print(f"Successfully created/ensured directories in /tmp: {QR_CODE_DIR}", flush=True)
except OSError as e:
    # Log error if directory creation fails, but maybe continue if they exist
    print(f"Warning/Error creating directories in /tmp: {e}", flush=True)

app = Flask(__name__, instance_path=INSTANCE_FOLDER_PATH, instance_relative_config=False)
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'a-secure-random-secret-key-for-dev') # Essential for sessions & WTForms
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL')
print(f"--- Read DATABASE_URL from ENV: {app.config['SQLALCHEMY_DATABASE_URI']}", flush=True)
# --- End print ---
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# --- Initialize Supabase Client ---
supabase: Client | None = None
if SUPABASE_URL and SUPABASE_KEY:
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        print("--- Supabase client initialized ---", flush=True)
    except Exception as e:
        print(f"FATAL ERROR: Could not initialize Supabase client: {e}", flush=True)
else:
    print("--- Supabase client NOT initialized due to missing ENV VARS ---", flush=True)

db = SQLAlchemy(app)
migrate = Migrate(app, db)

# --- Flask-Login Setup ---
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login' # Redirect here if user tries to access protected page
login_manager.login_message_category = 'info' # Flash message category

@login_manager.user_loader
def load_user(user_id):
    # Flask-Login uses this to reload the user object from the user ID stored in the session
    return db.session.get(User, int(user_id)) # Use db.session.get for primary key lookup

# --- Database Models ---

# --- Database Models ---

# User Model (same as before)
class User(UserMixin, db.Model):
    __tablename__ = 'users' # Explicit table name
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    is_admin = db.Column(db.Boolean, default=False, nullable=False)

    # Relationship to logs (optional but useful)
    check_logs = db.relationship('CheckInLog', backref='user', lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f'<User {self.username}>'

# Extinguisher Model (Add relationship to logs)
class Extinguisher(db.Model):
    __tablename__ = 'extinguishers'
    id = db.Column(db.Integer, primary_key=True)
    unique_id = db.Column(db.String(36), unique=True, nullable=False, default=lambda: str(uuid.uuid4()), index=True)
    serial_number = db.Column(db.String(100), unique=True, nullable=False, index=True)
    location_description = db.Column(db.String(200), nullable=False)
    latitude = db.Column(db.Float, nullable=True)
    longitude = db.Column(db.Float, nullable=True)
    last_checked_date = db.Column(db.DateTime, nullable=True)
    qr_code_filename = db.Column(db.String(50), nullable=True)
    image_filename = db.Column(db.String(256), nullable=True) # <--- ADD THIS LINE

    # Relationship to logs
    check_logs = db.relationship('CheckInLog', backref='extinguisher', lazy=True, cascade="all, delete-orphan")

    def __repr__(self):
        return f'<Extinguisher {self.serial_number}>'

# NEW CheckInLog Model
class CheckInLog(db.Model):
    __tablename__ = 'check_in_logs' # Explicit table name
    id = db.Column(db.Integer, primary_key=True)
    extinguisher_id = db.Column(db.Integer, db.ForeignKey('extinguishers.id'), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    checked_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True) # Store check-in time

    def __repr__(self):
        return f'<CheckInLog E:{self.extinguisher_id} U:{self.user_id} @{self.checked_at}>'

# --- Forms ---
class LoginForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired(), Length(min=4, max=80)])
    password = PasswordField('Password', validators=[DataRequired()])
    submit = SubmitField('Login')


class AddUserForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired(), Length(min=4, max=80)])
    password = PasswordField('Password', validators=[DataRequired(), Length(min=6)])
    confirm_password = PasswordField('Confirm Password',
                                     validators=[DataRequired(), EqualTo('password', message='Passwords must match.')])
    is_admin = BooleanField('Grant Admin Privileges?') # Checkbox for admin rights
    submit = SubmitField('Create User')

    # Optional: Custom validator to check if username already exists directly in the form
    def validate_username(self, username):
        user = db.session.scalar(db.select(User).filter_by(username=username.data))
        if user:
            raise ValidationError('That username is already taken. Please choose a different one.')

class EditUserForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired(), Length(min=4, max=80)])
    is_admin = BooleanField('Grant Admin Privileges?')

    # --- ADD Password Fields ---
    password = PasswordField('New Password (Leave blank to keep current)', validators=[
        Optional(), # Makes this field optional
        Length(min=6, message='New password must be at least 6 characters long.')
    ])
    confirm_password = PasswordField('Confirm New Password', validators=[
        Optional(), # Also optional
        EqualTo('password', message='New passwords must match.')
    ])
    # --- END Password Fields ---

    submit = SubmitField('Update User')

    # Need to store the original username to check for changes
    original_username = None
    user_id = None # Store user id to prevent editing self if needed

    def __init__(self, user_id, original_username, *args, **kwargs):
        super(EditUserForm, self).__init__(*args, **kwargs)
        self.original_username = original_username
        self.user_id = user_id

    def validate_username(self, username):
        # Check if username changed AND the new username is already taken
        if username.data != self.original_username:
            user = db.session.scalar(db.select(User).filter_by(username=username.data))
            if user:
                raise ValidationError('That username is already taken. Please choose a different one.')

# Optional: Form for CSRF protection on delete
class DeleteForm(FlaskForm):
    submit = SubmitField('Delete')

# --- Custom Decorators for Role Access ---
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            app.logger.warning(f"Unauthorized admin access attempt by user '{getattr(current_user, 'username', 'Anonymous')}' to {request.path}")
            flash("Admin privileges required to access this page.", "warning")
            # Redirect to index or login depending on if they are logged in at all
            if current_user.is_authenticated:
                return redirect(url_for('index'))
            else:
                return redirect(url_for('login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function

# --- Helper Functions (QR generation - same as before) ---
def generate_qr_code(data, filename):
    """Generates a QR code and saves it to the /tmp/instance/qrcodes folder."""
    # ... (keep the inside of this function the same, it uses QR_CODE_DIR which now points to /tmp) ...
    qr = qrcode.QRCode( version=1, error_correction=qrcode.constants.ERROR_CORRECT_L, box_size=10, border=4,)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    if not filename.lower().endswith('.png'): filename += '.png'
    filepath = os.path.join(QR_CODE_DIR, filename) # QR_CODE_DIR now points to /tmp/...
    try:
        img.save(filepath)
        app.logger.info(f"QR Code saved to {filepath}")
        return filename # Return just the filename
    except Exception as e:
        app.logger.error(f"Error saving QR code {filename}: {e}")
        return None
    
def get_start_end_of_day_utc(target_date):
    """Takes a date object and returns start/end datetime in UTC"""
    start_dt_naive = datetime.combine(target_date, datetime.min.time())
    end_dt_naive = datetime.combine(target_date, datetime.max.time())
    # Assuming naive dates represent UTC for simplicity with SQLite backend
    start_dt_utc = UTC.localize(start_dt_naive)
    end_dt_utc = UTC.localize(end_dt_naive) # Technically slightly inaccurate but okay for filtering
    # A more robust end_dt would be start of next day
    # end_dt_utc = UTC.localize(datetime.combine(target_date + timedelta(days=1), datetime.min.time()))
    return start_dt_utc, end_dt_utc

def _get_report_data(target_date):
    """Fetches and processes report data for a given date."""
    report_data = []
    try:
        # 1. Get all extinguishers
        all_extinguishers = db.session.scalars(
            db.select(Extinguisher).order_by(Extinguisher.location_description, Extinguisher.serial_number)
        ).all()

        # 2. Get check-in logs ONLY for the target date
        logs_for_date = db.session.scalars(
             db.select(CheckInLog)
             .options(db.joinedload(CheckInLog.user)) # Eager load user
             .filter(db.func.date(CheckInLog.checked_at) == target_date)
        ).all()

        # 3. Process Data
        checked_info = {}
        for log in logs_for_date:
            if log.extinguisher_id not in checked_info:
                 checked_info[log.extinguisher_id] = {
                    'checked_at': log.checked_at,
                    'user': log.user
                 }

        for ex in all_extinguishers:
            info = checked_info.get(ex.id)
            report_data.append({
                'extinguisher_id': ex.id, # Include ID if needed later
                'serial_number': ex.serial_number,
                'location': ex.location_description,
                'checked_today': bool(info),
                'checked_at': info['checked_at'] if info else None,
                'checked_by': info['user'].username if info and info.get('user') else None
            })
    except Exception as e:
        app.logger.error(f"Error fetching report data for {target_date}: {e}")
        # Decide how to handle errors, maybe return None or raise exception
        return None # Return None indicates an error occurred

    return report_data

def upload_extinguisher_image_from_bytes(image_bytes: bytes, content_type: str, extinguisher_unique_id: str) -> str | None:
    """Uploads extinguisher image BYTES to Supabase Storage, returns filename or None."""
    if not supabase:
        app.logger.error("Supabase client not initialized. Cannot upload extinguisher image.")
        return None
    if not image_bytes:
        app.logger.info("No image bytes provided.")
        return None

    # Determine file extension from content type
    extension = '.jpg' # Default
    if content_type == 'image/png':
        extension = '.png'
    elif content_type == 'image/gif':
        extension = '.gif'
    elif content_type == 'image/webp':
        extension = '.webp'
    # Add more types if needed

    filename = f"{extinguisher_unique_id}_image{extension}"
    bucket_name = "extinguisher-images"

    try:
        # Upload to Supabase Storage
        print(f"Uploading {filename} ({content_type}) to Supabase bucket '{bucket_name}'...", flush=True)
        response = supabase.storage.from_(bucket_name).upload(
            file=image_bytes, # Pass bytes directly
            path=filename,
            file_options={"content-type": content_type, "upsert": "true"} # Overwrite if exists
        )
        print(f"Supabase image upload response : {response}", flush=True)
        # Check response for success if necessary
        return filename

    except Exception as e:
        app.logger.error(f"Error uploading extinguisher image bytes '{filename}': {e}", exc_info=True)
        return None

def generate_and_upload_qr(extinguisher_unique_id: str, qr_data: str) -> str | None:
    """Generates QR, uploads to Supabase Storage, returns filename or None."""
    if not supabase:
        app.logger.error("Supabase client not initialized. Cannot upload QR code.")
        return None

    # Filename based on unique ID - this will be stored in DB and used as path in bucket
    filename = f"{extinguisher_unique_id}.png"
    bucket_name = "qrcodes" # Make sure this bucket exists in your Supabase project

    try:
        # Generate QR code image in memory
        print(f"Generating QR for data string: {qr_data}", flush=True) # Log the JSON string
        qr = qrcode.QRCode(...)
        qr.add_data(qr_data)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        img_buffer = io.BytesIO()
        img.save(img_buffer, format='PNG')
        img_buffer.seek(0) # Rewind buffer

        # Upload to Supabase Storage
        print(f"Uploading {filename} to Supabase bucket '{bucket_name}'...", flush=True)
        # Use file value directly from buffer
        response = supabase.storage.from_(bucket_name).upload(
            file=img_buffer.getvalue(),
            path=filename, # Use filename as the path within the bucket
            file_options={"content-type": "image/png", "upsert": "true"} # Overwrite if exists
        )
        print(f"Supabase upload response : {response}", flush=True)
        return filename

    except Exception as e:
        app.logger.error(f"Error generating or uploading QR code '{filename}': {e}", exc_info=True)
        return None

@app.template_filter('datetime_ist')
def format_datetime_ist(value, format='%Y-%m-%d %I:%M:%S %p %Z'): # Default format includes AM/PM and Timezone Abbr.
    """Formats a UTC datetime object into IST for display."""
    if value is None:
        return "N/A" # Or "" or "Never"

    if not isinstance(value, datetime):
         # Log an error or return the value unprocessed if it's not a datetime object
         app.logger.warning(f"datetime_ist filter received non-datetime value: {value}")
         return value

    # Ensure the datetime object is timezone-aware (assume UTC if naive)
    if value.tzinfo is None:
        value_utc = UTC.localize(value)
    else:
        value_utc = value.astimezone(UTC)

    # Convert to IST
    value_ist = value_utc.astimezone(IST)

    # Format the IST datetime
    return value_ist.strftime(format)

# --- Routes ---

# Authentication Routes
@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        # If already logged in, redirect based on role
        if current_user.is_admin:
            return redirect(url_for('index'))
        else:
            return redirect(url_for('scan_page')) # Non-admin goes straight to scan

    form = LoginForm()
    if form.validate_on_submit():
        user = db.session.scalar(db.select(User).filter_by(username=form.username.data))
        if user and user.check_password(form.password.data):
            login_user(user)
            flash(f'Logged in successfully as {user.username}.', 'success')

            # --- START ROLE-BASED REDIRECT ---
            if user.is_admin:
                # Admin goes to next page or index
                next_page = request.args.get('next')
                if next_page and not next_page.startswith(('/', 'http://', 'https://')):
                     next_page = None
                return redirect(next_page or url_for('index'))
            else:
                # Non-admin goes directly to scan page, ignore 'next'
                return redirect(url_for('scan_page'))
            # --- END ROLE-BASED REDIRECT ---

        else:
            flash('Login unsuccessful. Please check username and password.', 'danger')
    return render_template('login.html', title='Login', form=form)

@app.route('/logout')
@login_required # Must be logged in to log out
def logout():
    logout_user()
    flash('You have been logged out.', 'success')
    return redirect(url_for('login'))

# Core Application Routes (with protection)
@app.route('/')
@login_required # Still require login first
def index():
    # --- START ROLE-BASED REDIRECT ---
    if not current_user.is_admin:
        return redirect(url_for('scan_page'))
    # --- END ROLE-BASED REDIRECT ---

    # --- Admin Only Logic ---
    try:
        # Fetch data only if user is admin (as others are redirected)
        extinguishers = Extinguisher.query.order_by(
            Extinguisher.last_checked_date.desc().nullslast(),
            Extinguisher.location_description
        ).all()
    except Exception as e:
        app.logger.error(f"Error fetching extinguishers: {e}")
        flash('Could not load extinguishers.', 'warning')
        extinguishers = []
    return render_template('index.html', extinguishers=extinguishers)

# In index.py

# ... (other imports and code) ...

@app.route('/add', methods=['GET', 'POST'])
@login_required
@admin_required
def add_extinguisher():
    errors = {}
    submitted_data = {}

    if request.method == 'POST':
        # ... (Get form data: serial, location, lat, lon, image data etc.) ...
        # ... (Perform validation) ...

        # --- Decode Base64 Image Data if using camera capture ---
        image_bytes = None
        image_content_type = None
        image_data_url = request.form.get('captured_image_data')
        if image_data_url and image_data_url.startswith('data:image'):
             # ... (base64 decoding logic) ...
             pass # Placeholder for your decoding logic

        # --- If validation fails ---
        if errors:
            flash('Please correct the errors below.', 'error')
            return render_template('add_extinguisher.html',
                                   errors=errors,
                                   submitted_data=submitted_data)

        # --- If validation passes ---
        new_extinguisher = Extinguisher(
            serial_number=serial,
            location_description=location,
            latitude=lat,
            longitude=lon
            # unique_id is generated by default
        )
        db.session.add(new_extinguisher)
        # Flush required here to ensure the default unique_id is generated
        # *before* we use it for the QR code data or image filename.
        try:
            db.session.flush()
        except Exception as flush_err:
             db.session.rollback()
             app.logger.error(f"Error flushing session before QR/image generation: {flush_err}", exc_info=True)
             flash('Database error occurred before saving details.', 'error')
             errors['general'] = 'A server error occurred. Please try again.'
             return render_template('add_extinguisher.html', errors=errors, submitted_data=submitted_data)


        image_upload_filename = None
        qr_upload_filename = None
        try:
            # --- Upload Image (if applicable) ---
            if image_bytes and image_content_type:
                # Ensure new_extinguisher.unique_id is available after flush
                image_upload_filename = upload_extinguisher_image_from_bytes(
                    image_bytes, image_content_type, new_extinguisher.unique_id
                )
                if image_upload_filename:
                    new_extinguisher.image_filename = image_upload_filename
                    print(f"Saved image_filename: {image_upload_filename} for {serial}", flush=True)
                else:
                    flash(f'Extinguisher {serial} added, but failed to upload captured image.', 'warning')
                    app.logger.warning(f"Failed captured image upload for {serial} ({new_extinguisher.unique_id})")

            # --- Prepare JUST the unique_id for the QR Code ---
            qr_data_to_encode = new_extinguisher.unique_id # <--- CORE CHANGE HERE

            # --- Generate and Upload QR Code containing only the ID ---
            # Pass the unique_id as the data to be encoded
            qr_upload_filename = generate_and_upload_qr(
                extinguisher_unique_id=new_extinguisher.unique_id, # Used for filename/path in bucket
                qr_data=qr_data_to_encode                        # Data to be encoded in QR
            )
            if qr_upload_filename:
                new_extinguisher.qr_code_filename = qr_upload_filename
                print(f"Saved qr_code_filename: {qr_upload_filename} for {serial} (QR contains only ID: {qr_data_to_encode})", flush=True)
            else:
                 flash(f'Extinguisher {serial} added, but failed to generate/upload QR code.', 'warning')
                 app.logger.warning(f"Failed QR upload for {serial} ({new_extinguisher.unique_id})")

            # --- Commit to Database ---
            db.session.commit()
            flash(f'Extinguisher {serial} added successfully!', 'success')
            return redirect(url_for('view_extinguisher', unique_id=new_extinguisher.unique_id))

        except Exception as e:
            db.session.rollback()
            # Log the specific error during upload/commit
            app.logger.error(f"Error during DB commit or file uploads for {serial}: {e}", exc_info=True)
            flash(f'Error processing extinguisher addition: {str(e)}', 'error')
            errors['general'] = 'A server error occurred. Please try again.'
            return render_template('add_extinguisher.html',
                                   errors=errors,
                                   submitted_data=submitted_data)

    # GET request or initial load
    return render_template('add_extinguisher.html', errors={}, submitted_data={})

# Route to serve the QR code images - PUBLIC ACCESS (consider if this needs protection)
@app.route('/instance/qrcodes/<filename>')
def serve_qr_code(filename):
     # Security: Ensure filename is safe
    if '..' in filename or filename.startswith('/'):
        abort(404)
    try:
        # Use send_from_directory, pointing explicitly to QR_CODE_DIR which is in /tmp
        print(f"Attempting to serve QR code: {filename} from {QR_CODE_DIR}", flush=True) # Add logging
        return send_from_directory(QR_CODE_DIR, filename, as_attachment=False)
    except FileNotFoundError:
        print(f"QR code file not found: {os.path.join(QR_CODE_DIR, filename)}", flush=True) # Add logging
        abort(404)
    except Exception as e:
        print(f"Error serving QR code {filename}: {e}", flush=True) # Log other errors
        abort(500)

@app.route('/extinguisher/<string:unique_id>')
@login_required
def view_extinguisher(unique_id):
    extinguisher = db.session.execute(
        db.select(Extinguisher).filter_by(unique_id=unique_id)
    ).scalar_one_or_none()

    if not extinguisher: abort(404, description="Extinguisher not found.")

    qr_code_public_url = None
    image_public_url = None # <--- Add variable for image URL
    if supabase:
        # --- Get QR Code URL ---
        if extinguisher.qr_code_filename:
            qr_bucket_name = "qrcodes"
            try:
                qr_code_public_url = supabase.storage.from_(qr_bucket_name).get_public_url(extinguisher.qr_code_filename)
                print(f"Generated public URL for QR {extinguisher.qr_code_filename}: {qr_code_public_url}", flush=True)
            except Exception as e:
                app.logger.error(f"Could not get public URL for QR {extinguisher.qr_code_filename}: {e}", exc_info=True)

        # --- Get Image URL ---
        if extinguisher.image_filename:
            img_bucket_name = "extinguisher-images" # <--- Use the correct bucket name
            try:
                image_public_url = supabase.storage.from_(img_bucket_name).get_public_url(extinguisher.image_filename)
                print(f"Generated public URL for Image {extinguisher.image_filename}: {image_public_url}", flush=True)
            except Exception as e:
                app.logger.error(f"Could not get public URL for Image {extinguisher.image_filename}: {e}", exc_info=True)

    can_view_qr = current_user.is_admin

    return render_template('view_extinguisher.html',
                           extinguisher=extinguisher,
                           qr_code_public_url=qr_code_public_url,
                           image_public_url=image_public_url, # <--- Pass image URL to template
                           can_view_qr=can_view_qr)


@app.route('/scan')
@login_required # Any logged-in user can access the scan page
def scan_page():
    return render_template('scan.html')

# api/index.py
# ... imports ...
# ... helper _get_report_data ...

@app.route('/admin/report')
@login_required
@admin_required
def daily_report():
    # --- Get Target Date ---
    # ... (same date logic as before) ...
    date_str = request.args.get('report_date')
    target_date = date.today() # Default
    if date_str:
        try: target_date = date.fromisoformat(date_str)
        except ValueError: flash("Invalid date format.", "error")

    # --- Call the helper function ---
    report_data_list = _get_report_data(target_date)

    # --- Initialize template data and counts ---
    template_report_data = []
    checked_count = 0
    total_extinguishers = 0

    if report_data_list is None:
        flash("An error occurred while generating the report data.", "error")
    elif report_data_list:
        # --- Calculate Counts ---
        total_extinguishers = len(report_data_list)
        checked_count = sum(1 for item in report_data_list if item['checked_today'])
        # --- END Calculate Counts ---

        # Map data for template (if needed, e.g., getting full extinguisher object)
        extinguisher_map = {ex.id: ex for ex in db.session.scalars(db.select(Extinguisher)).all()}
        for item in report_data_list:
             template_report_data.append({
                 'extinguisher': extinguisher_map.get(item['extinguisher_id']),
                 'checked_today': item['checked_today'],
                 'checked_at': item['checked_at'],
                 'checked_by': item['checked_by']
             })

    # --- Pass counts to template ---
    return render_template('report.html',
                           report_data=template_report_data,
                           target_date=target_date,
                           today_date_str=date.today().isoformat(),
                           checked_count=checked_count, # Pass count
                           total_extinguishers=total_extinguishers # Pass total
                           )

@app.route('/check/<string:unique_id>', methods=['GET'])
@login_required # Any logged-in user can trigger a check via scanning
def check_extinguisher(unique_id):
    # Find the extinguisher using unique_id
    extinguisher = db.session.scalar(
        db.select(Extinguisher).filter_by(unique_id=unique_id)
    )

    if extinguisher:
        try:
            now_utc = datetime.utcnow() # Get current time once

            # 1. Update the last checked date on the extinguisher itself
            extinguisher.last_checked_date = now_utc

            # 2. Create a new log entry
            new_log = CheckInLog(
                extinguisher_id=extinguisher.id,
                user_id=current_user.id, # Get ID of the logged-in user
                checked_at=now_utc       # Use the same timestamp
            )
            db.session.add(new_log) # Add the log entry to the session

            # 3. Commit both changes
            db.session.commit()

            flash(f'Extinguisher {extinguisher.serial_number} checked successfully by {current_user.username}!', 'success')
            # Redirect to view page after successful check
            return redirect(url_for('view_extinguisher', unique_id=unique_id))

        except Exception as e:
            db.session.rollback()
            app.logger.error(f"Error checking extinguisher {unique_id} by user {current_user.username}: {e}")
            flash(f'Error updating extinguisher status: {str(e)}', 'error')
            # Redirect to index on error to avoid potential loops
            return redirect(url_for('index'))
    else:
        flash('Invalid QR Code scanned - Extinguisher not found.', 'error')
        return redirect(url_for('scan_page'))
    
# @app.route('/admin/add_user', methods=['GET', 'POST'])
# @login_required
# @admin_required # Ensure only admins can access this page
# def add_user():
#     form = AddUserForm()
#     if form.validate_on_submit(): # Checks POST, validates form (including custom validate_username)
#         username = form.username.data
#         password = form.password.data
#         is_admin_flag = form.is_admin.data # Get boolean value from checkbox

#         # Username uniqueness is already checked by form.validate_username,
#         # but double-checking here doesn't hurt and handles race conditions (though unlikely here).
#         existing_user = db.session.scalar(db.select(User).filter_by(username=username))
#         if existing_user:
#              flash('Username already exists.', 'error')
#              # No redirect here, let the template re-render with the form error message
#         else:
#             new_user = User(username=username, is_admin=is_admin_flag)
#             new_user.set_password(password) # Hash the password

#             try:
#                 db.session.add(new_user)
#                 db.session.commit()
#                 flash(f'User "{username}" created successfully!', 'success')
#                 return redirect(url_for('add_user')) # Redirect back to the add user page (or a user list page)
#             except Exception as e:
#                 db.session.rollback()
#                 app.logger.error(f"Error creating user {username}: {e}")
#                 flash(f'Error creating user: {str(e)}', 'error')

#     # If GET request or form validation failed
#     return render_template('add_user.html', title='Add New User', form=form)
@app.route('/admin/report/export')
@login_required
@admin_required
def export_report():
    # --- Get Target Date (same logic as daily_report) ---
    date_str = request.args.get('report_date')
    target_date = None
    if date_str:
        try:
            target_date = date.fromisoformat(date_str)
        except ValueError:
            flash("Invalid date format for export. Please use YYYY-MM-DD.", "error")
            return redirect(url_for('daily_report')) # Redirect back on error
    else:
        # Default to today if no date provided in export link
        target_date = date.today()

    # --- Get Report Data using the helper function ---
    report_data_list = _get_report_data(target_date)

    if report_data_list is None:
        flash("Could not generate report data for export due to an error.", "error")
        return redirect(url_for('daily_report', report_date=target_date.isoformat()))

    if not report_data_list:
        flash("No data available to export for the selected date.", "info")
        return redirect(url_for('daily_report', report_date=target_date.isoformat()))

    # --- Convert data to Pandas DataFrame ---
    # Select and rename columns for the Excel output
    df_data = []
    for item in report_data_list:
        # Format datetime for Excel - Use IST from filter logic
        # Need the IST timezone object defined earlier (IST = pytz.timezone('Asia/Kolkata'))
        checked_at_str = "-"
        if item['checked_at']:
             # Manually apply IST conversion logic here for the export string
             value_utc = UTC.localize(item['checked_at']) if item['checked_at'].tzinfo is None else item['checked_at'].astimezone(UTC)
             value_ist = value_utc.astimezone(IST)
             checked_at_str = value_ist.strftime('%Y-%m-%d %I:%M:%S %p %Z') # Or desired Excel format

        df_data.append({
            'Serial Number': item['serial_number'],
            'Location': item['location'],
            'Status': 'Checked' if item['checked_today'] else 'Missed',
            'Checked Time (IST)': checked_at_str,
            'Checked By': item['checked_by'] if item['checked_by'] else '-'
        })

    df = pd.DataFrame(df_data)

    # --- Generate Excel file in memory ---
    output_buffer = io.BytesIO()
    # Use a writer context manager for cleaner handling
    try:
        with pd.ExcelWriter(output_buffer, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name=f'Report_{target_date.isoformat()}', index=False)
        output_buffer.seek(0) # Reset buffer position to the beginning
    except Exception as e:
        app.logger.error(f"Error generating Excel file for {target_date}: {e}")
        flash("An error occurred while creating the Excel file.", "error")
        return redirect(url_for('daily_report', report_date=target_date.isoformat()))


    # --- Create file response ---
    return send_file(
        output_buffer,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=f'fire_extinguisher_report_{target_date.isoformat()}.xlsx' # Set filename
    )

# --- Initialize Database ---
def init_db(drop_all=False):
     """Initializes the database: drops tables (if requested), creates tables,
        and ensures the default admin user exists."""
     with app.app_context():
        print("Attempting to manage database tables...")
        try:
            if drop_all:
                print("Dropping all tables...")
                db.drop_all()
                print("Tables dropped.")

            print("Creating tables (if they don't exist)...")
            db.create_all() # Creates User, Extinguisher, CheckInLog tables
            print(f"Database tables ensured/created at {app.config['SQLALCHEMY_DATABASE_URI']}")

            # --- Create Default Admin User ---
            default_admin_username = 'admin'
            default_admin_password = 'admin@1234' # Consider making this configurable via ENV VAR

            # Check if the default admin user already exists
            admin_exists = db.session.scalar(
                db.select(User).filter_by(username=default_admin_username)
            )

            if not admin_exists:
                print(f"Default admin user '{default_admin_username}' not found. Creating...")
                admin_user = User(username=default_admin_username, is_admin=True)
                admin_user.set_password(default_admin_password) # Hash the password
                db.session.add(admin_user)
                try:
                    db.session.commit()
                    print(f"Default admin user '{default_admin_username}' created successfully.")
                except Exception as commit_error:
                    db.session.rollback()
                    print(f"Error committing default admin user: {commit_error}")
            else:
                print(f"Default admin user '{default_admin_username}' already exists.")

        except Exception as e:
            print(f"Error during database initialization: {e}")

@app.route('/admin/users')
@login_required
@admin_required
def user_list():
    """Displays a list of all users."""
    try:
        users = db.session.scalars(db.select(User).order_by(User.username)).all()
    except Exception as e:
        app.logger.error(f"Error fetching user list: {e}")
        flash("Could not retrieve user list.", "error")
        users = []
    # Pass DeleteForm to the template for use in loops
    delete_form = DeleteForm()
    return render_template('user_list.html', users=users, delete_form=delete_form)

# Update the existing add_user route to redirect to user_list
@app.route('/admin/add_user', methods=['GET', 'POST'])
@login_required
@admin_required
def add_user():
    form = AddUserForm()
    if form.validate_on_submit():
        username = form.username.data
        password = form.password.data
        is_admin_flag = form.is_admin.data

        # Username uniqueness checked by form validator
        new_user = User(username=username, is_admin=is_admin_flag)
        new_user.set_password(password)

        try:
            db.session.add(new_user)
            db.session.commit()
            flash(f'User "{username}" created successfully!', 'success')
            # Redirect to the user list page now
            return redirect(url_for('user_list'))
        except Exception as e:
            db.session.rollback()
            app.logger.error(f"Error creating user {username}: {e}")
            flash(f'Error creating user: {str(e)}', 'error')

    # If GET request or form validation failed
    return render_template('add_user.html', title='Add New User', form=form)


@app.route('/admin/users/<int:user_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_user(user_id):
    user_to_edit = db.session.get(User, user_id)
    if not user_to_edit:
        flash(f"User with ID {user_id} not found.", "error")
        return redirect(url_for('user_list'))

    # --- Optional Safeguards (Keep or modify as needed) ---
    # if user_to_edit.username == 'admin' and user_to_edit.id != current_user.id:
    #      flash("Editing the primary 'admin' user is restricted.", "warning")
    # if user_to_edit.id == current_user.id and user_to_edit.username == 'admin':
    #      flash("Admins cannot easily revoke their own admin status via this form.", "warning")
    # --- End Safeguards ---

    form = EditUserForm(user_id=user_to_edit.id, original_username=user_to_edit.username, obj=user_to_edit)

    if form.validate_on_submit():
        password_updated = False # Flag to track if password was changed

        # --- Check for potential admin demotion (keep existing logic) ---
        if user_to_edit.is_admin and not form.is_admin.data:
             admin_count = db.session.scalar(db.select(db.func.count(User.id)).filter_by(is_admin=True))
             if admin_count <= 1:
                 flash("Cannot remove admin status from the last remaining admin.", "error")
                 return render_template('edit_user.html', title='Edit User', form=form, user=user_to_edit)
             if user_to_edit.id == current_user.id:
                  flash("You cannot revoke your own admin status.", "error")
                  return render_template('edit_user.html', title='Edit User', form=form, user=user_to_edit)

        # --- Update username and admin status ---
        user_to_edit.username = form.username.data
        user_to_edit.is_admin = form.is_admin.data

        # --- ADD Password Update Logic ---
        if form.password.data: # Check if the password field was filled
            try:
                user_to_edit.set_password(form.password.data) # Hash and set new password
                password_updated = True
                app.logger.info(f"Password updated for user '{user_to_edit.username}' by admin '{current_user.username}'.")
            except Exception as e:
                 # This shouldn't generally fail if set_password is correct, but good practice
                 app.logger.error(f"Error setting password for user {user_to_edit.username}: {e}")
                 flash('An error occurred while updating the password.', 'error')
                 # Render form again to show error
                 return render_template('edit_user.html', title='Edit User', form=form, user=user_to_edit)
        # --- END Password Update Logic ---

        try:
            db.session.commit()
            flash_message = f'User "{user_to_edit.username}" updated successfully!'
            if password_updated:
                 flash_message += ' Password has been changed.'
            flash(flash_message, 'success')
            return redirect(url_for('user_list'))
        except Exception as e:
            db.session.rollback()
            app.logger.error(f"Error updating user {user_to_edit.username}: {e}")
            flash(f'Error updating user: {str(e)}', 'error')

    # If GET request or form validation failed
    return render_template('edit_user.html', title='Edit User', form=form, user=user_to_edit)


@app.route('/admin/users/<int:user_id>/delete', methods=['POST']) # Use POST for delete actions
@login_required
@admin_required
def delete_user(user_id):
    """Handles deleting a user."""
    # Use a simple form for CSRF protection
    form = DeleteForm()

    if form.validate_on_submit(): # Check CSRF token
        user_to_delete = db.session.get(User, user_id)

        if not user_to_delete:
            flash(f"User with ID {user_id} not found.", "error")
            return redirect(url_for('user_list'))

        # --- Safeguards ---
        if user_to_delete.username == 'admin':
            flash("Cannot delete the primary 'admin' user.", "error")
            return redirect(url_for('user_list'))

        if user_to_delete.id == current_user.id:
            flash("You cannot delete yourself.", "error")
            return redirect(url_for('user_list'))

        # Optional: Check if user is the last admin
        if user_to_delete.is_admin:
             admin_count = db.session.scalar(db.select(db.func.count(User.id)).filter_by(is_admin=True))
             if admin_count <= 1:
                 flash("Cannot delete the last remaining admin user.", "error")
                 return redirect(url_for('user_list'))
        # --- End Safeguards ---

        try:
            username = user_to_delete.username # Get username before deleting for flash message
            # Add logic here if user has related data that needs handling (e.g., reassign logs?)
            # For now, we just delete the user. Related logs might cause issues if not handled.
            # Consider setting logs' user_id to NULL if DB allows, or deleting them if appropriate.
            # Since we didn't set cascade on User->CheckInLog, deleting user might fail if logs exist.
            # Let's handle that possibility:
            if user_to_delete.check_logs:
                 flash(f"Cannot delete user '{username}' as they have existing check-in logs. Reassign or delete logs first.", "warning")
                 return redirect(url_for('user_list'))

            db.session.delete(user_to_delete)
            db.session.commit()
            flash(f'User "{username}" deleted successfully.', 'success')
        except Exception as e:
            db.session.rollback()
            app.logger.error(f"Error deleting user ID {user_id}: {e}")
            flash(f'Error deleting user: {str(e)}', 'error')

    else:
        # If CSRF validation fails (e.g., someone trying to trigger delete via GET)
        flash("Invalid request to delete user.", "error")

    return redirect(url_for('user_list'))

# --- CLI Commands ---
@app.cli.command('create-admin')
def create_admin_command():
    """Creates the initial admin user in the persistent database."""
    with app.app_context():
        default_admin_username = 'admin'
        default_admin_password = 'admin@1234' # Or prompt user

        existing_user = db.session.scalar(db.select(User).filter_by(username=default_admin_username))
        if existing_user:
            print(f"Admin user '{default_admin_username}' already exists.")
            return

        print(f"Creating admin user '{default_admin_username}'...")
        admin_user = User(username=default_admin_username, is_admin=True)
        admin_user.set_password(default_admin_password) # Ensure User model has set_password

        try:
            db.session.add(admin_user)
            db.session.commit()
            print(f"Admin user '{default_admin_username}' created successfully.")
        except Exception as e:
            db.session.rollback()
            print(f"Error creating admin user: {e}")

with app.app_context():
    print("--- Running initial DB setup check ---", flush=True)
    init_db()
    print("--- Initial DB setup check complete ---", flush=True)

# --- Run for Local Development ---
if __name__ == '__main__':
    with app.app_context():
        if not os.path.exists(os.path.join(app.instance_path, "database.db")):
             print("Database file not found, initializing...")
             init_db()

    port = int(os.environ.get('PORT', 5001))
    app.run(debug=True, host='0.0.0.0', port=port)