# app.py
from flask import Flask, render_template, request, redirect, url_for, send_file, flash, jsonify
import qrcode
import os
import uuid
import zipfile
from io import BytesIO
from sqlalchemy.exc import IntegrityError
from datetime import datetime, timedelta

from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from apscheduler.schedulers.background import BackgroundScheduler

from models import db, Attendee, Booking, Seat, User 

# --- Flask App Configuration ---
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get("SECRET_KEY", "fallback-secret-key")
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///site.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)

# --- Flask-Login Setup ---
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message_category = "error"

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Ensure necessary directories exist
QR_CODE_DIR = os.path.join(app.root_path, 'static', 'qrcodes')
os.makedirs(QR_CODE_DIR, exist_ok=True)


# --- Data Retention Policy (Garbage Collector) ---
def cleanup_old_data():
    with app.app_context():
        cutoff_date = datetime.utcnow() - timedelta(days=90)
        
        old_attendees = Attendee.query.filter(Attendee.booked_at < cutoff_date).all()
        for attendee in old_attendees:
            if attendee.qr_code_filename:
                file_path = os.path.join(QR_CODE_DIR, attendee.qr_code_filename)
                if os.path.exists(file_path):
                    try:
                        os.remove(file_path)
                    except Exception as e:
                        print(f"Error deleting file {file_path}: {e}")
            
            seat = Seat.query.filter_by(table_number=attendee.table_number, seat_number=attendee.seat_number).first()
            if seat:
                seat.is_booked = False
            
            db.session.delete(attendee)

        old_bookings = Booking.query.filter(Booking.booked_at < cutoff_date).all()
        for booking in old_bookings:
            db.session.delete(booking)

        db.session.commit()
        print(f"[{datetime.utcnow()}] Data cleanup routine completed. Old records deleted.")

scheduler = BackgroundScheduler()
scheduler.add_job(func=cleanup_old_data, trigger="interval", days=1)
scheduler.start()


# --- QR Code Generation Helper Functions ---
def generate_qr_code_file(data_content, unique_id):
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(data_content)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")
    filename = f"qr_{unique_id}.png"
    filepath = os.path.join(QR_CODE_DIR, filename)
    img.save(filepath)
    return filename

def generate_qr_code_bytes(data_content):
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(data_content)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")
    byte_io = BytesIO()
    img.save(byte_io, format='PNG')
    byte_io.seek(0)
    return byte_io


# --- Authentication Routes ---
@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
        
    if request.method == 'POST':
        username = request.form.get('username').strip()
        email = request.form.get('email').strip()
        password = request.form.get('password')

        user_exists = User.query.filter((User.email == email) | (User.username == username)).first()
        if user_exists:
            flash("Email or username already in use. Please log in.", "error")
            return redirect(url_for('signup'))

        hashed_password = generate_password_hash(password, method='pbkdf2:sha256')
        new_user = User(username=username, email=email, password=hashed_password)
        
        db.session.add(new_user)
        db.session.commit()
        
        flash("Account created successfully! You can now log in.", "success")
        return redirect(url_for('login'))

    return render_template('signup.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    if request.method == 'POST':
        email = request.form.get('email').strip()
        password = request.form.get('password')
        
        user = User.query.filter_by(email=email).first()
        
        if user and check_password_hash(user.password, password):
            login_user(user)
            flash("Logged in successfully!", "success")
            next_page = request.args.get('next')
            return redirect(next_page if next_page else url_for('index'))
        else:
            flash("Login failed. Check email and password.", "error")

    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for('splash'))


# --- Routes for your pages ---
@app.route('/')
def splash():
    return render_template('splash.html')

@app.route('/home')
def index():
    return render_template('index.html')

@app.route('/generate')
@login_required
def generate_choice():
    return render_template('choice.html')

@app.route('/individual', methods=['GET', 'POST'])
@login_required
def individual_qr():
    if request.method == 'POST':
        name = request.form['name'].strip()
        phone = request.form['phone'].strip()
        table_number = request.form['table_number'].strip().upper()
        seat_number = int(request.form['seat_number'])

        seat_status = Seat.query.filter_by(table_number=table_number, seat_number=seat_number).first()
        if seat_status and seat_status.is_booked:
            booked_by = Attendee.query.filter_by(table_number=table_number, seat_number=seat_number).first()
            if booked_by:
                flash(f"Error: Table {table_number}, Seat {seat_number} is already booked by {booked_by.name}.", 'error')
            else:
                flash(f"Error: Table {table_number}, Seat {seat_number} is already booked.", 'error')
            return render_template('individual_form.html', name=name, phone=phone, table_number=table_number, seat_number=seat_number)

        unique_id = str(uuid.uuid4())
        qr_data = f"Attendee ID: {unique_id}, Name: {name}, Table: {table_number}, Seat: {seat_number}"
        qr_image_filename = generate_qr_code_file(qr_data, unique_id)

        new_attendee = Attendee(
            name=name,
            phone=phone,
            table_number=table_number,
            seat_number=seat_number,
            qr_code_filename=qr_image_filename,
            user_id=current_user.id 
        )
        db.session.add(new_attendee)

        if not seat_status:
            seat_status = Seat(table_number=table_number, seat_number=seat_number)
        seat_status.is_booked = True
        db.session.add(seat_status)

        try:
            db.session.commit()
            flash(f"QR Code generated for {name} (Table {table_number}, Seat {seat_number})!", 'success')
            return redirect(url_for('download_qr_single', filename=qr_image_filename))
        except IntegrityError:
            db.session.rollback()
            flash(f"Error: Table {table_number}, Seat {seat_number} was just booked. Please try another.", 'error')
            return render_template('individual_form.html', name=name, phone=phone, table_number=table_number, seat_number=seat_number)
        except Exception as e:
            db.session.rollback()
            flash(f"An unexpected error occurred: {e}", 'error')
            return render_template('individual_form.html', name=name, phone=phone, table_number=table_number, seat_number=seat_number)
        
    return render_template('individual_form.html')

@app.route('/booked', methods=['GET', 'POST'])
@login_required
def booked_qr():
    if request.method == 'POST':
        table_number = request.form['table_number'].strip().upper()
        num_seats = int(request.form['num_seats'])
        starting_seat = int(request.form['starting_seat'])

        seats_to_book = []
        
        for i in range(num_seats):
            current_seat = starting_seat + i
            seat_status = Seat.query.filter_by(table_number=table_number, seat_number=current_seat).first()
            
            if seat_status and seat_status.is_booked:
                booked_by = Attendee.query.filter_by(table_number=table_number, seat_number=current_seat).first()
                if booked_by:
                    flash(f"Error: Table {table_number}, Seat {current_seat} is already booked by {booked_by.name}. Bulk booking aborted.", 'error')
                else:
                    flash(f"Error: Table {table_number}, Seat {current_seat} is already booked. Bulk booking aborted.", 'error')
                return render_template('booked_form.html', table_number=table_number, num_seats=num_seats, starting_seat=starting_seat)
            seats_to_book.append(current_seat)

        zip_buffer = BytesIO()
        zip_uuid = str(uuid.uuid4())
        zip_filename_on_disk = f"Booking_{table_number}_Seats_{starting_seat}_to_{starting_seat + num_seats - 1}_QR_Codes_{zip_uuid[:8]}.zip"
        
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            for current_seat in seats_to_book:
                qr_data = f"BookingID: {zip_uuid[:8]}, Table: {table_number}, Seat: {current_seat}"
                qr_image_bytes = generate_qr_code_bytes(qr_data)
                
                filename_in_zip = f"{table_number}_Seat_{current_seat}_QR.png"
                zip_file.writestr(filename_in_zip, qr_image_bytes.getvalue())

                new_attendee = Attendee(
                    name=f"Bulk Booking - Table {table_number}",
                    phone=None,
                    table_number=table_number,
                    seat_number=current_seat,
                    qr_code_filename=f"bulk_zip_qr_{uuid.uuid4()}.png",
                    user_id=current_user.id 
                )
                db.session.add(new_attendee)

                seat_status = Seat.query.filter_by(table_number=table_number, seat_number=current_seat).first()
                if not seat_status:
                    seat_status = Seat(table_number=table_number, seat_number=current_seat)
                seat_status.is_booked = True
                db.session.add(seat_status)

        new_booking = Booking(
            table_number=table_number,
            num_seats=num_seats,
            starting_seat=starting_seat,
            zip_filename=zip_filename_on_disk,
            user_id=current_user.id 
        )
        db.session.add(new_booking)
        
        try:
            db.session.commit()
            zip_buffer.seek(0)
            flash(f"Successfully generated {num_seats} QR codes for Table {table_number}!", 'success')
            return send_file(
                zip_buffer,
                mimetype='application/zip',
                as_attachment=True,
                download_name=zip_filename_on_disk
            )
        except IntegrityError:
            db.session.rollback()
            flash("An issue with unique seats occurred during bulk booking. Some seats might have been just booked.", 'error')
            return render_template('booked_form.html', table_number=table_number, num_seats=num_seats, starting_seat=starting_seat)
        except Exception as e:
            db.session.rollback()
            flash(f"An unexpected error occurred during bulk booking: {e}", 'error')
            return render_template('booked_form.html', table_number=table_number, num_seats=num_seats, starting_seat=starting_seat)
        
    return render_template('booked_form.html')

@app.route('/download_single/<filename>')
@login_required
def download_qr_single(filename):
    return render_template('download_qr.html', qr_image_url=url_for('static', filename=f'qrcodes/{filename}'))

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/contact')
def contact():
    return render_template('contact.html')

@app.route('/privacy')
def privacy():
    return render_template('privacy.html')

@app.route('/account')
@login_required
def account():
    total_individual = Attendee.query.filter_by(user_id=current_user.id).count()
    total_bulk = Booking.query.filter_by(user_id=current_user.id).count()
    return render_template('account.html', individual_count=total_individual, bulk_count=total_bulk)

@app.route('/history')
@login_required 
def history():
    all_attendees = Attendee.query.filter_by(user_id=current_user.id).order_by(Attendee.booked_at.desc()).all()
    all_bookings = Booking.query.filter_by(user_id=current_user.id).order_by(Booking.booked_at.desc()).all()
    return render_template('history.html', attendees=all_attendees, bookings=all_bookings)

@app.route('/clear_history', methods=['POST'])
@login_required
def clear_history():
    attendees = Attendee.query.filter_by(user_id=current_user.id).all()
    bookings = Booking.query.filter_by(user_id=current_user.id).all()

    for attendee in attendees:
        if attendee.qr_code_filename:
            file_path = os.path.join(QR_CODE_DIR, attendee.qr_code_filename)
            if os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except Exception as e:
                    print(f"Error deleting file {file_path}: {e}")
        
        seat = Seat.query.filter_by(table_number=attendee.table_number, seat_number=attendee.seat_number).first()
        if seat:
            seat.is_booked = False
        
        db.session.delete(attendee)

    for booking in bookings:
        db.session.delete(booking)

    db.session.commit()
    flash("Your history has been completely cleared and seats are available again.", "success")
    return redirect(url_for('history'))

@app.route('/api/check_seat_availability/<table_num>/<int:seat_num>')
def check_seat_availability(table_num, seat_num):
    table_num = table_num.strip().upper()
    seat = Seat.query.filter_by(table_number=table_num, seat_number=seat_num).first()
    is_booked = seat.is_booked if seat else False
    booked_by_name = ""
    if is_booked:
        attendee = Attendee.query.filter_by(table_number=table_num, seat_number=seat_num).first()
        if attendee:
            booked_by_name = attendee.name
    return jsonify({'table_number': table_num, 'seat_number': seat_num, 'is_booked': is_booked, 'booked_by': booked_by_name})

@app.cli.command("init-db")
def init_db_command():
    with app.app_context():
        db.drop_all()
        db.create_all()
        print("Database initialized (site.db created/reset).")

if __name__ == '__main__':
    with app.app_context():
        db.create_all() 
    app.run(host='0.0.0.0', port=5000, debug=True)