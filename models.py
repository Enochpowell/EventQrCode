# models.py
from datetime import datetime
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy() # Initialize SQLAlchemy, will be connected to app in app.py

class Attendee(db.Model):
    """Represents an individual attendee booking."""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(20), nullable=True)
    table_number = db.Column(db.String(50), nullable=False)
    seat_number = db.Column(db.Integer, nullable=False)
    qr_code_filename = db.Column(db.String(200), nullable=True) # Filename of the generated QR
    booked_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Ensure that a specific seat at a specific table can only be booked once
    __table_args__ = (db.UniqueConstraint('table_number', 'seat_number', name='_table_seat_uc'),)

    def __repr__(self):
        return f"<Attendee {self.name} - Table {self.table_number}, Seat {self.seat_number}>"

class Booking(db.Model):
    """Represents a bulk booking (e.g., for multiple seats at a table)."""
    id = db.Column(db.Integer, primary_key=True)
    table_number = db.Column(db.String(50), nullable=False)
    num_seats = db.Column(db.Integer, nullable=False)
    starting_seat = db.Column(db.Integer, nullable=False)
    zip_filename = db.Column(db.String(200), nullable=True) # Filename of the generated ZIP
    booked_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<Booking Table {self.table_number}, {self.num_seats} seats from {self.starting_seat}>"

class Seat(db.Model):
    """
    Represents the state of each individual seat.
    This is a separate model to quickly check seat availability without iterating through attendees.
    """
    id = db.Column(db.Integer, primary_key=True)
    table_number = db.Column(db.String(50), nullable=False)
    seat_number = db.Column(db.Integer, nullable=False)
    is_booked = db.Column(db.Boolean, default=False)
    # Optional: link to the attendee who booked it, if applicable
    # booked_by_attendee_id = db.Column(db.Integer, db.ForeignKey('attendee.id'), nullable=True)

    __table_args__ = (db.UniqueConstraint('table_number', 'seat_number', name='_table_seat_unique_idx'),)

    def __repr__(self):
        return f"<Seat Table {self.table_number}, Seat {self.seat_number} - Booked: {self.is_booked}>"