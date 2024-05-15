from celery import shared_task
from sqlalchemy import func

from mail import send_message
import flask_excel as excel
from model import db, Product_table, Order_details


@shared_task(ignore_result=True)
def trial(to, subject, body):
    send_message(to, subject, body)
    return "success"


@shared_task(ignore_result=False)
def create_csv():
    data = (
        db.session.query(
            Product_table.product_id,
            Product_table.product_name,
            Product_table.quantity,
            Product_table.rate_per_unit,
            func.coalesce(func.sum(Order_details.quantity), 0).label('quantity_sold')
        )
        .outerjoin(Order_details, Product_table.product_name == Order_details.product_name)
        .group_by(Product_table.product_name)
        .all()
    )
    excel_sheet = excel.make_response_from_query_sets(data,
                                                      ["product_id", "product_name", "quantity", "rate_per_unit","quantity_sold"],
                                                      "csv")
    filename = "Inventory_report.csv"
    file = open("Inventory_report.csv", "wb")
    file.write(excel_sheet.data)
    return filename
