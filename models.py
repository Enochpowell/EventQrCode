# models.py
from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin 

db = SQLAlchemy() 

class User(db.Model, UserMixin):
    """Represents a registered user on the website."""
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(256), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    attendees = db.relationship('Attendee', backref='user', lazy=True, cascade="all, delete-orphan")
    bookings = db.relationship('Booking', backref='user', lazy=True, cascade="all, delete-orphan")

    def __repr__(self):
        return f"<User {self.username}>"

class Attendee(db.Model):
    """Represents an individual attendee booking."""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(20), nullable=True)
    table_number = db.Column(db.String(50), nullable=False)
    seat_number = db.Column(db.Integer, nullable=False)
    qr_code_filename = db.Column(db.String(200), nullable=True)
    booked_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

    def __repr__(self):
        return f"<Attendee {self.name} - Table {self.table_number}, Seat {self.seat_number}>"

class Booking(db.Model):
    """Represents a bulk booking."""
    id = db.Column(db.Integer, primary_key=True)
    table_number = db.Column(db.String(50), nullable=False)
    num_seats = db.Column(db.Integer, nullable=False)
    starting_seat = db.Column(db.Integer, nullable=False)
    zip_filename = db.Column(db.String(200), nullable=True) 
    booked_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

    def __repr__(self):
        return f"<Booking Table {self.table_number}, {self.num_seats} seats from {self.starting_seat}>"

class Seat(db.Model):
    """Represents the state of each individual seat."""
    id = db.Column(db.Integer, primary_key=True)
    table_number = db.Column(db.String(50), nullable=False)
    seat_number = db.Column(db.Integer, nullable=False)
    is_booked = db.Column(db.Boolean, default=False)
    
    __table_args__ = (db.UniqueConstraint('table_number', 'seat_number', name='_table_seat_unique_idx'),)

    def __repr__(self):
        return f"<Seat Table {self.table_number}, Seat {self.seat_number} - Booked: {self.is_booked}>"