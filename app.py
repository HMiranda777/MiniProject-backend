import os
from datetime import timedelta

import sqlalchemy.exc
from celery.result import AsyncResult
from celery.schedules import crontab
from flask import Flask, render_template, request, redirect, jsonify, send_file
from flask_cors import CORS
from flask_restful import Api, Resource
from sqlalchemy import or_

from model import *
from flask_security import Security, SQLAlchemyUserDatastore, auth_required, roles_accepted
from configuration import DevelopmentConfig
from celerycreation import celery_init_app
from tasks import trial
from jinja2 import Template
from cache import cache_obj
from tasks import create_csv
import flask_excel as excel

'''---------------------------------------------------------------------------------------------------------'''

basedir = os.path.abspath(os.path.dirname(__file__))
app = Flask(__name__)
AP = Api(app)
app.config.from_object(DevelopmentConfig)
cache_obj.init_app(app)
db.init_app(app)
excel.init_excel(app)
datastore = SQLAlchemyUserDatastore(db, User, Role)
app.security = Security(app, datastore)
CORS(app)
app.app_context().push()
celery_app = celery_init_app(app)

'''---------------------------------------------------------------------------------------------------------'''


@celery_app.on_after_configure.connect
def setup_periodic_messages(sender, **kwargs):
    fetch_users = User.query.filter(User.roles.any(name="customer")).all()
    for i in fetch_users:
        sender.add_periodic_task(crontab(hour="8", minute="30"),
                                 trial.s(i.email, "Grocery", "Hi," + i.username + "Come shop with us at Delish, 10% off"
                                                                                  "on all goods today!!"))


@celery_app.on_after_configure.connect
def schedule_order_reports(sender, **kwargs):
    fetch_users = User.query.filter(User.roles.any(name="customer")).all()
    last_day = datetime(datetime.now().year, datetime.now().month, 1) - timedelta(days=1)
    day = datetime(last_day.year, last_day.month, 1)
    for i in fetch_users:
        fetch_order_details = Order_details.query.filter(Order_details.email == i.email,
                                                         Order_details.date >= day).all()
        total = 0
        for j in fetch_order_details:
            total += (j.price * j.quantity)
        file = open("report.html", "r")
        template = Template(file.read())
        sender.add_periodic_task(crontab(day_of_month="0"),
                                 trial.s(i.email, "Monthly Order Report", template.render(details=fetch_order_details,total=total)))


'''--------------------------------------------------------------------------------------------------------------'''


@app.get('/report/csv')
def inventoryReport():
    file = create_csv.delay()
    return jsonify({"id": file.id})


@app.get('/csv/<id>')
def getReport(id):
    result = AsyncResult(id)
    if result.ready():
        file = result.result
        return send_file(file, as_attachment=True)
    else:
        return jsonify({"message": "Report Pending"}), 404


'''-----------------------------------------------------------------------------------------------------------'''


# API CLASS
class UserDashboard(Resource):
    @auth_required("token")
    @roles_accepted("customer")
    @cache_obj.cached(timeout=60)
    def get(self):
        category_list = Categories.query.filter(or_(Categories.status == 1, Categories.status == 0)).all()
        return jsonify(category_list)


class GroceryCart(Resource):
    @auth_required("token")
    @roles_accepted("customer")
    @cache_obj.cached(timeout=60)
    def get(self, email):
        join = db.session.query(Product_table, Cart_details).filter(Cart_details.email == email,
                                                                    Product_table.product_name == Cart_details.product_name).all()
        result = [
            {
                'cart_id': cart.Cart_id,
                'product_id': product.product_id,
                'product_name': cart.product_name,
                'rate_per_unit': product.rate_per_unit,
                'quantity': cart.Quantity,
                'unit': product.unit
            }
            for product, cart in join
        ]
        print(result)
        return jsonify(result)

    # @app.route("/Ordernow/<username>")
    @auth_required("token")
    @roles_accepted("customer")
    def post(self, email):
        cache_obj.clear()
        name = request.json["product_name"]
        qty = int(request.json["quantity"])
        print(name, qty)
        try:
            data = Cart_details.query.filter_by(email=email, product_name=name).first()
            if data:
                data.Quantity = qty
                db.session.add(data)
                db.session.commit()
                return jsonify({"message": "Product in cart,updated"})
            insert_cart = Cart_details(email=email, product_name=name, Quantity=qty)
            db.session.add(insert_cart)
            db.session.commit()
            return jsonify(({"message": "added to cart"}))
        except Exception as e:
            return jsonify({"message": "Something went wrong"})

    @auth_required("token")
    @roles_accepted("customer")
    def patch(self, email):
        cache_obj.clear()
        stmt1 = Cart_details.query.filter_by(email=email).all()
        for i in stmt1:
            stmt2 = Product_table.query.filter_by(product_name=i.product_name).first()
            db.session.add(
                Order_details(email=email, price=stmt2.rate_per_unit, product_name=i.product_name, quantity=i.Quantity))
            stmt2.quantity = stmt2.quantity - i.Quantity
            db.session.add(stmt2)
            db.session.delete(i)
        db.session.commit()
        return jsonify({"message": "successfully placed order"})

    @auth_required("token")
    @roles_accepted("customer")
    def delete(self, email):
        cache_obj.clear()
        product_name = request.args.get("product_name")
        fetch_cartitem = Cart_details.query.filter_by(product_name=product_name, email=email).first()
        db.session.delete(fetch_cartitem)
        db.session.commit()
        return jsonify({"message": "success"})


'''--------------------------------------------------------------------------------------------------'''


# @app.route("/createcategory", methods=["POST"])
class CategoryActivity(Resource):
    @auth_required("token")
    @roles_accepted("manager")
    @cache_obj.cached(timeout=60)
    def get(self):
        return jsonify(Categories.query.all())

    @auth_required("token")
    @roles_accepted("manager")
    def post(self):
        cache_obj.clear()
        category = request.json["value"]
        category = category.lower().strip(" ")
        try:
            if len(category) == 0:
                return jsonify({"message": "Name  cannot consist of blank spaces "})
            for i in category:
                if not i.isalpha() and i not in [' ', '-']:
                    return jsonify({"message": "Name must not include a number"})
            query1 = Categories(category_name=category, task='Add', status=2)
            db.session.add(query1)
            db.session.commit()
            return jsonify({"message": "success"})
        except sqlalchemy.exc.IntegrityError:
            return jsonify({"message": "Category already exists"})

    # @app.route("/Delete/<int:category_id>")
    @auth_required("token")
    @roles_accepted("manager")
    def delete(self, category_id):
        cache_obj.clear()
        fetch_data = Categories.query.filter_by(category_id=category_id).first()
        fetch_data.status = 2
        fetch_data.task = "Delete"
        db.session.add(fetch_data)
        db.session.commit()
        return jsonify({"message": "sent for approval"})

        # query2 = Categories.query.filter_by(category_id=category_id).first()
        # query3 = Product_table.query.filter_by(category_id=category_id).all()
        # for i in query3:
        #     db.session.delete(i)
        # db.session.delete(query2)

    # @app.route("/Edit/<int:category_id>", methods=["POST"])
    @auth_required("token")
    @roles_accepted("manager")
    def patch(self, category_id):
        cache_obj.clear()
        newcategory = request.json["category_name"]

        newcategory = newcategory.lower().strip(" ")
        try:
            if len(newcategory) == 0:
                return jsonify({"message": "Name  cannot consist of blank spaces "})
            for i in newcategory:
                if not i.isalpha():
                    return jsonify({"message": "Name must not include a number"})
            fetch_for_edit = Categories.query.filter_by(category_id=category_id).first()
            fetch_for_edit.new_category_name = newcategory
            fetch_for_edit.status = 2
            fetch_for_edit.task = "Edit"
            db.session.add(fetch_for_edit)
            db.session.commit()
        except sqlalchemy.exc.IntegrityError as error:
            return jsonify({"message": "Name already exists"})
        return jsonify({"message": "successful"})


'''---------------------------------------------------------------------------------------------------'''


# @app.route("/Product/<int:category_id>", methods=["POST"])
class ProductActivity(Resource):
    @auth_required("token")
    @roles_accepted("manager", "customer")
    def post(self, category_id):
        cache_obj.clear()
        name = request.json["product"]
        name = name.lower()
        unit = request.json["unit"]
        rate = int(request.json["rate"])
        quantity = int(request.json["quantity"])
        query5 = Product_table(category_id=category_id, product_name=name, unit=unit, rate_per_unit=rate,
                               quantity=quantity, task="Add", status=2)

        try:
            db.session.add(query5)
            db.session.commit()
        except sqlalchemy.exc.IntegrityError:
            return jsonify({"message": "Product already exists"})
        return jsonify({"message": "success"})

    # @app.route("/EditProduct/<int:product_id>", methods=["POST"])
    @auth_required("token")
    @roles_accepted("manager")
    def patch(self):
        cache_obj.clear()
        product_id = request.args.get("product_id")
        unit = request.json["unit"]
        rate = request.json["rate_per_unit"]
        quantity = request.json["quantity"]
        if rate == '' or quantity == '':
            return jsonify({"message": "Empty values not allowed"})
        edit_query = Product_table.query.filter_by(product_id=product_id).first()
        if rate == edit_query.rate_per_unit and unit == edit_query.unit and quantity == edit_query.quantity:
            return jsonify({"message": "No changes"})
        edit_query.new_unit = unit
        edit_query.new_rate_per_unit = int(rate)
        edit_query.new_quantity = int(quantity)
        edit_query.status = 2
        edit_query.task = "Edit"
        db.session.add(edit_query)
        db.session.commit()
        return jsonify({"message": "successfully edited"})

    @auth_required("token")
    @roles_accepted("manager")
    def delete(self):
        cache_obj.clear()
        product_id = request.args.get("product_id")
        delete_prod = Product_table.query.filter_by(product_id=product_id).first()
        delete_prod.status = 2
        delete_prod.task = "Delete"
        db.session.add(delete_prod)
        db.session.commit()
        return jsonify({"message": "successfully deleted"})


'''-------------------------------------------------------------------------------------------------------------'''


class AdminCategoryActivity(Resource):
    @auth_required("token")
    @roles_accepted("admin")
    @cache_obj.cached(timeout=60)
    def get(self):
        return jsonify(Categories.query.filter_by(status=2).all())

    # approval
    @auth_required("token")
    @roles_accepted("admin")
    def patch(self):
        cache_obj.clear()
        task = request.args.get("task")
        category_id = request.args.get("category_id")
        update_category = Categories.query.filter_by(category_id=category_id).first()
        update_category.status = 1
        update_category.task = None
        if task == "Add":
            db.session.add(update_category)
        elif task == "Delete":
            delete_products = Product_table.query.filter_by(category_id=category_id).all()
            for i in delete_products:
                db.session.delete(i)
            db.session.delete(update_category)
        elif task == "Edit":
            update_category.category_name = update_category.new_category_name
            db.session.add(update_category)
        db.session.commit()
        return jsonify({"message": "successful"})

    # disapproval
    @auth_required("token")
    @roles_accepted("admin")
    def delete(self):
        cache_obj.clear()
        task = request.args.get("task")
        category_id = request.args.get("category_id")
        fetch_data = Categories.query.filter_by(category_id=category_id).first()
        if task == "Add":
            db.session.delete(fetch_data)
        elif task == "Delete" or task == "Edit":
            fetch_data.status = 0
            fetch_data.task = None
            db.session.add(fetch_data)
        db.session.commit()
        return jsonify({"message": "successfully deleted disapproved category"})


'''---------------------------------------------------------------------------------------------'''


class AdminProductActivtity(Resource):
    @auth_required("token")
    @roles_accepted("admin")
    @cache_obj.cached(timeout=60)
    def get(self):
        return jsonify(Product_table.query.filter_by(status=2).all())

    @auth_required("token")
    @roles_accepted("admin")
    def patch(self):
        cache_obj.clear()
        task = request.args.get("task")
        product_id = request.args.get("product_id")
        update_product = Product_table.query.filter_by(product_id=product_id).first()
        update_product.status = 1
        update_product.task = None
        if task == "Add":
            db.session.add(update_product)
        elif task == "Delete":
            db.session.delete(update_product)
        elif task == "Edit":
            update_product.unit = update_product.new_unit
            update_product.rate_per_unit = update_product.new_rate_per_unit
            update_product.quantity = update_product.new_quantity
            db.session.add(update_product)
        db.session.commit()
        return jsonify({"message": "successful"})

    @auth_required("token")
    @roles_accepted("admin")
    def delete(self):
        cache_obj.clear()
        task = request.args.get("task")
        product_id = request.args.get("product_id")
        fetch_data = Product_table.query.filter_by(product_id=product_id).first()
        if task == "Add":
            db.session.delete(fetch_data)
        elif task == "Delete":
            fetch_data.status = 0
            fetch_data.task = None
            db.session.add(fetch_data)
        elif task == "Edit":
            fetch_data.status = 0
            fetch_data.task = None
            fetch_data.new_unit = None
            fetch_data.new_rate_per_unit = 0
            fetch_data.new_quantity = 0
        db.session.commit()
        return jsonify({"message": "successfully deleted disapproved category"})


'''-----------------------------------------------------------------------------------------------------'''


class AdminAccessApproval(Resource):
    @auth_required("token")
    @roles_accepted("admin")
    @cache_obj.cached(timeout=60)
    def get(self):
        fetch_users = db.session.query(User.username, User.email).filter_by(active=False).all()
        user_list = [{'username': username, 'email': email} for username, email in fetch_users]
        return jsonify(user_list)

    @auth_required("token")
    @roles_accepted("admin")
    def patch(self):
        cache_obj.clear()
        email = request.json["email"]
        fetch_user = User.query.filter_by(email=email).first()
        fetch_user.active = True
        db.session.add(fetch_user)
        db.session.commit()
        return jsonify({"message": "success"})

    @auth_required("token")
    @roles_accepted("admin")
    def delete(self):
        cache_obj.clear()
        try:
            email = request.args.get("email")
            print(email)
            datastore.delete_user(User.query.filter_by(email=email).first())
            db.session.commit()
            return jsonify({"message": "successfully deleted user"})

        except Exception as e:
            print(e)


'''---------------------------------------------------------------------------------------------------------'''


@app.post("/signup")
def signup():
    print(request.json)
    username = request.json["username"]
    email = request.json["email_id"]
    password = request.json["password"]
    role = request.json["role"]

    user_exist = datastore.find_user(email=email)
    if user_exist:
        return jsonify({"message": "User already exists with this Email id !"})
    if role == "manager":
        datastore.create_user(username=username, email=email, password=password, roles=[role], active=False)
        db.session.commit()
        return jsonify({"message": "Waiting for Admin Approval"})
    elif role == "customer":
        datastore.create_user(username=username, email=email, password=password, roles=[role])
        db.session.commit()
        created_user = datastore.find_user(email=email)
        return jsonify({"status": "New user created",
                        "token": created_user.get_auth_token(),
                        "role": role,
                        "email": email})


@app.post("/userlogin")
def login():
    email = request.json["email_id"]
    password = request.json["password"]
    fetch_user = datastore.find_user(email=email)
    if not fetch_user:
        return jsonify({"message": "No user found!"})
    if not fetch_user.password == password:
        return jsonify({"message": "Incorrect Password!"})
    return jsonify(
        {
            "status": "successfully logged in",
            "token": fetch_user.get_auth_token(),
            "role": fetch_user.roles[0].name,
            "email": fetch_user.email,
        }
    )


'''----------------------------------------------------------------------------------------------------------------'''

AP.add_resource(UserDashboard, '/dashboard')
AP.add_resource(GroceryCart, '/cart/<email>')
AP.add_resource(CategoryActivity, '/category/<category_id>', '/category')
AP.add_resource(ProductActivity, '/product/<category_id>', '/product')
AP.add_resource(AdminCategoryActivity, '/category/pending')
AP.add_resource(AdminProductActivtity, '/products/pending')
AP.add_resource(AdminAccessApproval, '/user/pending')

'''----------------------------------------------------------------------------------------------------------------'''
if __name__ == "__main__":
    db.create_all()
    app.run(debug=True)
