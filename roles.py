from app import app,datastore
from model import db

with app.app_context():
    db.create_all()
    datastore.find_or_create_role(name="admin", description="This user is an Admin")
    datastore.find_or_create_role(name="manager", description="This user is the Manager")
    datastore.find_or_create_role(name="customer", description="This user is the customer")
    db.session.commit()
    db.session.commit()
