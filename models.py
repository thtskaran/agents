# models.py
import os
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import json

db = SQLAlchemy() # Initialize here, associate with app later

class Users(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False) # Remember to hash passwords!
    email_verified = db.Column(db.Boolean, default=False)
    createdAt = db.Column(db.DateTime, default=datetime.now)
    updatedAt = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    
    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "email": self.email,
            "email_verified": self.email_verified,
            "createdAt": self.createdAt.isoformat(),
            "updatedAt": self.updatedAt.isoformat(),
        }

class Agents(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    agentid = db.Column(db.String(50), unique=True, nullable=False) # Unique ID for the agent
    userId = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    name = db.Column(db.String(100), nullable=False, default="Untitled Agent")
    description = db.Column(db.Text, nullable=True)
    permissions = db.Column(db.Text, nullable=True) # Store as JSON string list
    pcode = db.Column(db.String(100), nullable=True) # Added missing pcode field
    instructions = db.Column(db.Text, nullable=True) # Custom instructions base
    file_path = db.Column(db.String(255), nullable=False) # Path to the generated .py file
    status = db.Column(db.String(20), nullable=False, default='created') # e.g., 'created', 'running', 'stopped', 'error'
    port = db.Column(db.Integer, nullable=True) # Port the agent runs on when started
    pid = db.Column(db.Integer, nullable=True) # Process ID when running
    createdAt = db.Column(db.DateTime, default=datetime.now)
    updatedAt = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)

    user = db.relationship("Users", backref=db.backref("agents", lazy=True))

    def to_dict(self):
        return {
            "id": self.id,
            "agentid": self.agentid,
            "userId": self.userId,
            "name": self.name,
            "description": self.description,
            "permissions": json.loads(self.permissions) if self.permissions else [],
            "pcode": self.pcode,
            "instructions": self.instructions,
            "file_path": self.file_path,
            "status": self.status,
            "port": self.port,
            "pid": self.pid,
            "createdAt": self.createdAt.isoformat(),
            "updatedAt": self.updatedAt.isoformat(),
        }


class Models(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    code = db.Column(db.String(50), unique=True, nullable=False)
    provider = db.Column(db.String(50), nullable=False)
    offline = db.Column(db.Boolean, default=False)
    endpoint = db.Column(db.String(255), nullable=True)
    createdAt = db.Column(db.DateTime, default=datetime.now)
    updatedAt = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)

    def to_dict(self):
         return {
            "id": self.id,
            "name": self.name,
            "code": self.code,
            "provider": self.provider,
            "offline": self.offline,
            "endpoint": self.endpoint,
            "createdAt": self.createdAt.isoformat(),
            "updatedAt": self.updatedAt.isoformat(),
        }