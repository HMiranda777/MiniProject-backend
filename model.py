from datetime import datetime
from sqlalchemy import Column, String, Integer, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from dataclasses import dataclass
from flask_security import RoleMixin, UserMixin
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


@dataclass
class Product_table(db.Model):
    __tablename__ = "Product_table"
    category_id: int = Column(Integer, ForeignKey("Categories.category_id"), nullable=False)
    product_id: int = Column(Integer, primary_key=True, autoincrement=True)
    product_name: str = Column(String, nullable=False, unique=True)
    unit: str = Column(String, nullable=False)
    new_unit: str = Column(String, default=None)
    rate_per_unit: int = Column(Integer, nullable=False)
    new_rate_per_unit: int = Column(Integer, default=0)
    quantity: int = Column(Integer, nullable=False)
    new_quantity: int = Column(Integer, default=0)
    status: int = Column(Integer, nullable=False)
    task: str = Column(String)


@dataclass
class Categories(db.Model):
    __tablename__ = "Categories"
    category_id: int = Column(Integer, primary_key=True, autoincrement=True)
    category_name: str = Column(String, nullable=False, unique=True)
    new_category_name: str = Column(String, unique=True)
    products: list[Product_table] = relationship("Product_table", backref="pdt")
    status: int = Column(Integer, nullable=False)
    task: str = Column(String)


@dataclass
class RolesUsers(db.Model):
    __tablename__ = 'roles_users'
    id: int = db.Column(db.Integer(), primary_key=True)
    user_id: int = db.Column('user_id', db.Integer(), db.ForeignKey('user.id'))
    role_id: int = db.Column('role_id', db.Integer(), db.ForeignKey('role.id'))


@dataclass
class Role(db.Model, RoleMixin):
    id: int = db.Column(db.Integer(), primary_key=True)
    name: str = db.Column(db.String(80), unique=True)
    description: str = db.Column(db.String(255))


@dataclass
class User(db.Model, UserMixin):
    __allow_unmapped__ = True
    id: int = db.Column(db.Integer, primary_key=True)
    username: str = db.Column(db.String, unique=False)
    email: str = db.Column(db.String(255), unique=True, index=True)
    password: str = db.Column(db.String(255))
    active: bool = db.Column(db.Boolean())
    fs_uniquifier: str = db.Column(db.String(255), unique=True, nullable=False)
    roles: list[Role] = db.relationship('Role', secondary='roles_users',
                                        backref=db.backref('users', lazy='dynamic'))


@dataclass
class Cart_details(db.Model):
    __tablename__ = "Cart_details"
    email: str = Column(String, ForeignKey("user.email"), nullable=False)
    product_name: str = Column(String, ForeignKey("Product_table.product_name"), nullable=False)
    Cart_id: int = Column(Integer, primary_key=True, autoincrement=True)
    Quantity: int = Column(Integer, nullable=False)


@dataclass
class Order_details(db.Model):
    __tablename__ = "Order_details"
    email: str = Column(String, ForeignKey("user.email"), nullable=False)
    product_name: str = Column(String, nullable=False)
    quantity: int = Column(Integer, nullable=False)
    order_id: int = Column(Integer, primary_key=True, autoincrement=True)
    price: int = Column(Integer, nullable=False)
    date:datetime = Column(DateTime, nullable=False, default=datetime.now())
