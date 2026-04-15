# app.py
from flask import Flask, render_template, request, redirect, url_for, send_file, flash, jsonify
import qrcode
import os
import uuid
import zipfile
from io import BytesIO
from models import db, Attendee, Booking, Seat # NEW: Import db and models
from sqlalchemy.exc import IntegrityError # For handling unique constraint errors

# --- Flask App Configuration ---
app = Flask(__name__)
# IMPORTANT: Change this for production! This key is used for secure sessions (flash messages)
app.config['SECRET_KEY'] = 'a_very_secret_and_long_random_string_you_should_change'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///site.db' # SQLite database file relative to app.root_path
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app) # Initialize SQLAlchemy with the Flask app

# Ensure necessary directories exist
QR_CODE_DIR = os.path.join(app.root_path, 'static', 'qrcodes')
os.makedirs(QR_CODE_DIR, exist_ok=True)
# Temporary directory for zip files (will be handled in-memory for download)
# No need for TEMP_ZIP_DIR as zips are sent as BytesIO
# os.makedirs(TEMP_ZIP_DIR, exist_ok=True) # Not strictly needed if using BytesIO but good practice

# --- QR Code Generation Helper Functions ---
def generate_qr_code_file(data_content, unique_id):
    """Generates a QR code and saves it to the static/qrcodes directory.
       Returns the filename."""
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
    """Generates a QR code and returns its image data as bytes (for zipping)."""
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

# --- Routes for your pages ---

# Initial route to display the splash screen
@app.route('/')
def splash():
    """Displays the animated splash screen."""
    return render_template('splash.html')

# Main index route after splash or for direct navigation
@app.route('/home')
def index():
    """Displays the welcome page after the splash screen."""
    return render_template('index.html')

@app.route('/generate')
def generate_choice():
    """Displays the choice page (Individual/Booked)."""
    return render_template('choice.html')

@app.route('/individual', methods=['GET', 'POST'])
def individual_qr():
    """Handles individual attendee QR code generation and database storage."""
    if request.method == 'POST':
        name = request.form['name'].strip()
        phone = request.form['phone'].strip()
        table_number = request.form['table_number'].strip().upper() # Standardize table number
        seat_number = int(request.form['seat_number'])

        # --- Database Check for Seat Availability ---
        # First, check if the seat exists in the Seat table and is booked
        seat_status = Seat.query.filter_by(table_number=table_number, seat_number=seat_number).first()
        if seat_status and seat_status.is_booked:
            # If booked, find the attendee who booked it for a more informative message
            booked_by = Attendee.query.filter_by(table_number=table_number, seat_number=seat_number).first()
            if booked_by:
                flash(f"Error: Table {table_number}, Seat {seat_number} is already booked by {booked_by.name}.", 'error')
            else: # Fallback if seat is booked but attendee record is missing (shouldn't happen with proper logic)
                flash(f"Error: Table {table_number}, Seat {seat_number} is already booked.", 'error')
            return render_template('individual_form.html',
                                   name=name, phone=phone, table_number=table_number, seat_number=seat_number)

        # --- Generate QR and Store in Database ---
        unique_id = str(uuid.uuid4())
        qr_data = f"Attendee ID: {unique_id}, Name: {name}, Table: {table_number}, Seat: {seat_number}"
        qr_image_filename = generate_qr_code_file(qr_data, unique_id)

        new_attendee = Attendee(
            name=name,
            phone=phone,
            table_number=table_number,
            seat_number=seat_number,
            qr_code_filename=qr_image_filename
        )
        db.session.add(new_attendee)

        # Create or update Seat status
        if not seat_status: # If seat didn't exist, create it
            seat_status = Seat(table_number=table_number, seat_number=seat_number)
        seat_status.is_booked = True
        db.session.add(seat_status) # Add or update

        try:
            db.session.commit() # Commit all changes to the database
            flash(f"QR Code generated for {name} (Table {table_number}, Seat {seat_number})!", 'success')
            return redirect(url_for('download_qr_single', filename=qr_image_filename))
        except IntegrityError: # Catch cases where UniqueConstraint might be violated (e.g., race condition)
            db.session.rollback()
            flash(f"Error: Table {table_number}, Seat {seat_number} was just booked. Please try another.", 'error')
            return render_template('individual_form.html',
                                   name=name, phone=phone, table_number=table_number, seat_number=seat_number)
        except Exception as e:
            db.session.rollback()
            flash(f"An unexpected error occurred: {e}", 'error')
            return render_template('individual_form.html',
                                   name=name, phone=phone, table_number=table_number, seat_number=seat_number)
        
    return render_template('individual_form.html')

@app.route('/booked', methods=['GET', 'POST'])
def booked_qr():
    """Handles bulk QR code generation, database storage, and zip file creation."""
    if request.method == 'POST':
        table_number = request.form['table_number'].strip().upper() # Standardize table number
        num_seats = int(request.form['num_seats'])
        starting_seat = int(request.form['starting_seat'])

        seats_to_book = []
        
        # --- Check all seats for availability before booking any ---
        for i in range(num_seats):
            current_seat = starting_seat + i
            seat_status = Seat.query.filter_by(table_number=table_number, seat_number=current_seat).first()
            
            if seat_status and seat_status.is_booked:
                # If any seat in the range is booked, flash error and abort entire bulk booking
                booked_by = Attendee.query.filter_by(table_number=table_number, seat_number=current_seat).first()
                if booked_by:
                    flash(f"Error: Table {table_number}, Seat {current_seat} is already booked by {booked_by.name}. Bulk booking aborted.", 'error')
                else:
                    flash(f"Error: Table {table_number}, Seat {current_seat} is already booked. Bulk booking aborted.", 'error')
                return render_template('booked_form.html',
                                       table_number=table_number, num_seats=num_seats, starting_seat=starting_seat)
            seats_to_book.append(current_seat) # If available, add to list to book

        # --- Generate QR codes and prepare for zip ---
        zip_buffer = BytesIO()
        zip_uuid = str(uuid.uuid4())
        zip_filename_on_disk = f"Booking_{table_number}_Seats_{starting_seat}_to_{starting_seat + num_seats - 1}_QR_Codes_{zip_uuid[:8]}.zip"
        
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            for current_seat in seats_to_book:
                # Data for each individual QR code within the booking
                qr_data = f"BookingID: {zip_uuid[:8]}, Table: {table_number}, Seat: {current_seat}"
                qr_image_bytes = generate_qr_code_bytes(qr_data)
                
                filename_in_zip = f"{table_number}_Seat_{current_seat}_QR.png"
                zip_file.writestr(filename_in_zip, qr_image_bytes.getvalue())

                # Store each individual attendee for history
                new_attendee = Attendee(
                    name=f"Bulk Booking - Table {table_number}", # Generic name for bulk entry
                    phone=None, # Bulk bookings don't capture individual phones
                    table_number=table_number,
                    seat_number=current_seat,
                    qr_code_filename=f"bulk_zip_qr_{uuid.uuid4()}.png" # Unique placeholder filename
                )
                db.session.add(new_attendee)

                # Create or update Seat status
                seat_status = Seat.query.filter_by(table_number=table_number, seat_number=current_seat).first()
                if not seat_status:
                    seat_status = Seat(table_number=table_number, seat_number=current_seat)
                seat_status.is_booked = True
                db.session.add(seat_status)

        # --- Store the Bulk Booking Record ---
        new_booking = Booking(
            table_number=table_number,
            num_seats=num_seats,
            starting_seat=starting_seat,
            zip_filename=zip_filename_on_disk # Store filename for potential later retrieval
        )
        db.session.add(new_booking)
        
        try:
            db.session.commit() # Commit all changes
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
            return render_template('booked_form.html',
                                   table_number=table_number, num_seats=num_seats, starting_seat=starting_seat)
        except Exception as e:
            db.session.rollback()
            flash(f"An unexpected error occurred during bulk booking: {e}", 'error')
            return render_template('booked_form.html',
                                   table_number=table_number, num_seats=num_seats, starting_seat=starting_seat)
        
    return render_template('booked_form.html')

@app.route('/download_single/<filename>')
def download_qr_single(filename):
    """Displays a single generated QR code for download (for individual mode)."""
    return render_template('download_qr.html', qr_image_url=url_for('static', filename=f'qrcodes/{filename}'))

#for the about page
@app.route('/about')
def about():
    return render_template('about.html')

#for the contact page
@app.route('/contact')
def contact():
    return render_template('contact.html')

# History page route
@app.route('/history')
def history():
    """Displays the history of individual attendees and bulk bookings."""
    all_attendees = Attendee.query.order_by(Attendee.booked_at.desc()).all()
    all_bookings = Booking.query.order_by(Booking.booked_at.desc()).all()
    return render_template('history.html', attendees=all_attendees, bookings=all_bookings)

# API endpoint for checking seat availability (for frontend JS)
@app.route('/api/check_seat_availability/<table_num>/<int:seat_num>')
def check_seat_availability(table_num, seat_num):
    # Standardize table_num for lookup
    table_num = table_num.strip().upper()
    seat = Seat.query.filter_by(table_number=table_num, seat_number=seat_num).first()
    is_booked = seat.is_booked if seat else False
    # Optionally, get who booked it if needed
    booked_by_name = ""
    if is_booked:
        attendee = Attendee.query.filter_by(table_number=table_num, seat_number=seat_num).first()
        if attendee:
            booked_by_name = attendee.name
    return jsonify({'table_number': table_num, 'seat_number': seat_num, 'is_booked': is_booked, 'booked_by': booked_by_name})


# --- Database Initialization CLI Command (Use: python -m flask init-db) ---
@app.cli.command("init-db")
def init_db_command():
    """Clear existing data and create new tables."""
    with app.app_context(): # Essential for Flask-SQLAlchemy CLI commands
        db.drop_all()
        db.create_all()
        # flash("Initialized the database.", 'info') # Flash messages won't show in CLI
        print("Database initialized (site.db created/reset).")

# --- Run App ---
if __name__ == '__main__':
    # --- Create database tables if they don't exist ---
    with app.app_context():
        db.create_all() # This creates tables if site.db is new or tables are missing
    # --- Run the Flask development server ---
    app.run(host='0.0.0.0', port=5000, debug=True)