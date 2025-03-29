from flask import Flask
from models import db
import os

# Create a minimal Flask app
app = Flask(__name__)

# Configure the database URI from environment or use a default
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv(
    'DATABASE_URL', 
    'postgresql://postgres:Z6B3twcBRDXf9XtcSoXL@agnarok.ca4zqslyjq8j.ap-south-1.rds.amazonaws.com:5432/agnarok'
)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize the app with the SQLAlchemy instance
db.init_app(app)

# Function to reset the database
def reset_database():
    with app.app_context():
        print("Dropping all tables...")
        db.drop_all()  # This will delete all data!
        
        print("Creating tables from models...")
        db.create_all()
        
        print("Database schema reset successfully!")

if __name__ == "__main__":
    # Ask for confirmation
    response = input("WARNING: This will delete ALL data in your database. Continue? (yes/no): ")
    if response.lower() == 'yes':
        reset_database()
    else:
        print("Operation cancelled.")