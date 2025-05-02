from flask import Flask, render_template, request, redirect, url_for, session, flash
import os
from database import execute_query, get_db_connection
from dotenv import load_dotenv

load_dotenv()  # Load environment variables from .env file

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY")  # Use secret key from .env file

# @app.route('/')
# def home():
#     # return "Welcome to the Home Page!"
#     return render_template('base.html')

# Authentication routes
@app.route('/', methods=['GET', 'POST'])
def login():

    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        query = "SELECT id, username, role FROM users WHERE username = :username AND password = :password"
        user = execute_query(query, {'username': username, 'password': password}, fetchone=True)
        
        if user:
            session['user_id'] = user[0]
            session['username'] = user[1]
            session['role'] = user[2]
            return redirect(url_for('order_dashboard'))
        else:
            flash('Invalid username or password')
    return render_template('auth/login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# Dashboard routes
@app.route('/order_dashboard')
def order_dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    role = session.get('role')
    if role == 'admin':
        return redirect(url_for('admin_dashboard'))
    elif role == 'kitchen':
        return redirect(url_for('kitchen_dashboard'))
    
    # Fetch active orders
    query = """
    SELECT id, table_number, customer_name, status, total_amount, created_at
    FROM customer_order
    WHERE status IN ('pending', 'preparing')
    ORDER BY created_at DESC
    """
    active_orders = execute_query(query, fetchall=True)
    
    return render_template('order_dashboard.html', active_orders=active_orders)

@app.route('/admin_dashboard')
def admin_dashboard():
    if 'user_id' not in session or session.get('role') != 'admin':
        return redirect(url_for('login'))
    # return render_template('admin/admin_dashboard.html')
    return render_template('order_dashboard.html')

# Menu management routes
@app.route('/menu')
def menu_list():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    query = """
    SELECT m.id, m.name, m.description, m.price, m.is_available, c.name 
    FROM menu_item m
    JOIN menu_category c ON m.category_id = c.id
    ORDER BY m.id
    """
    menu_items = execute_query(query, fetchall=True)
    return render_template('admin/menu_list.html', menu_items=menu_items)


@app.route('/menu/add', methods=['GET', 'POST'])
def menu_add():
    if 'user_id' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        name = request.form['name']
        category_id = request.form['category_id']
        description = request.form['description']
        price = request.form['price']
        is_available = 1 if 'is_available' in request.form else 0
        
        query = """
        INSERT INTO menu_item (id, category_id, name, description, price, is_available) 
        VALUES (menu_item_seq.NEXTVAL, :category_id, :name, :description, :price, :is_available)
        """
        execute_query(
            query, 
            {
                'category_id': category_id, 
                'name': name, 
                'description': description, 
                'price': price, 
                'is_available': is_available
            }, 
            commit=True
        )
        flash('Menu item added successfully')
        return redirect(url_for('menu_list'))
    
    categories = execute_query("SELECT id, name FROM menu_category ORDER BY name", fetchall=True)
    return render_template('admin/menu_add.html', categories=categories)

@app.route('/menu/edit/<int:item_id>', methods=['GET', 'POST'])
def menu_edit(item_id):
    if 'user_id' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        name = request.form['name']
        category_id = request.form['category_id']
        description = request.form['description']
        price = request.form['price']
        is_available = 1 if 'is_available' in request.form else 0
        
        query = """
        UPDATE menu_item 
        SET name = :name, category_id = :category_id, description = :description, 
            price = :price, is_available = :is_available
        WHERE id = :id
        """
        execute_query(
            query, 
            {
                'name': name, 
                'category_id': category_id, 
                'description': description, 
                'price': price, 
                'is_available': is_available,
                'id': item_id
            }, 
            commit=True
        )
        flash('Menu item updated successfully')
        return redirect(url_for('menu_list'))
    
    item = execute_query("SELECT * FROM menu_item WHERE id = :id", {'id': item_id}, fetchone=True)
    categories = execute_query("SELECT id, name FROM menu_category ORDER BY name", fetchall=True)
    return render_template('admin/menu_edit.html', item=item, categories=categories)

@app.route('/menu/delete/<int:item_id>', methods=['POST'])
def menu_delete(item_id):
    if 'user_id' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))
    
    query = "DELETE FROM menu_item WHERE id = :id"
    execute_query(query, {'id': item_id}, commit=True)
    flash('Menu item deleted successfully')
    return redirect(url_for('menu_list'))

# Order management routes
@app.route('/order/new', methods=['GET', 'POST'])
def new_order():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        table_number = request.form['table_number']
        customer_name = request.form['customer_name']
        
        query_sequence = "SELECT customer_order_seq.NEXTVAL FROM DUAL"
        with get_db_connection() as connection:
            cursor = connection.cursor()
            cursor.execute(query_sequence)
            new_order_id = cursor.fetchone()[0]
        
        query = """
        INSERT INTO customer_order (id, table_number, customer_name, status, created_at)
        VALUES (:id, :table_number, :customer_name, 'pending', CURRENT_TIMESTAMP)
        """
        execute_query(
            query,
            {'id': new_order_id, 'table_number': table_number, 'customer_name': customer_name},
            commit=True
        )
        
        update_order_status_to_preparing.delay(new_order_id)
        flash(f'Order #{new_order_id} created successfully')
        return redirect(url_for('add_order_items', order_id=new_order_id))
    
    return render_template('order/new_order.html')

@app.route('/order/<int:order_id>/items', methods=['GET', 'POST'])
def add_order_items(order_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    order = execute_query("SELECT * FROM customer_order WHERE id = :id", {'id': order_id}, fetchone=True)
    if not order:
        flash('Order not found')
        return redirect(url_for('active_orders'))
    
    if request.method == 'POST':
        menu_item_id = request.form['menu_item_id']
        quantity = request.form['quantity']
        notes = request.form.get('notes', '')
        
        try:
            price = execute_query("SELECT price FROM menu_item WHERE id = :id", {'id': menu_item_id}, fetchone=True)[0]
            query = """
            INSERT INTO order_item (id, order_id, menu_item_id, quantity, price, notes) 
            VALUES (order_item_seq.NEXTVAL, :order_id, :menu_item_id, :quantity, :price, :notes)
            """
            execute_query(
                query, 
                {
                    'order_id': order_id, 
                    'menu_item_id': menu_item_id, 
                    'quantity': quantity, 
                    'price': price, 
                    'notes': notes
                }, 
                commit=True
            )
            query = """
            UPDATE customer_order 
            SET total_amount = (
                SELECT SUM(quantity * price) 
                FROM order_item 
                WHERE order_id = :order_id
            )
            WHERE id = :order_id
            """
            execute_query(query, {'order_id': order_id}, commit=True)
            flash('Item added to order')
        except cx_Oracle.IntegrityError:
            flash('Duplicate item detected. Please update the existing item instead.')
        except ValueError as e:
            flash(str(e))
        
        return redirect(url_for('add_order_items', order_id=order_id))
    
    query = """
    SELECT oi.id, m.name, oi.quantity, oi.price, (oi.quantity * oi.price) as subtotal, oi.notes 
    FROM order_item oi
    JOIN menu_item m ON oi.menu_item_id = m.id
    WHERE oi.order_id = :order_id
    """
    order_items = execute_query(query, {'order_id': order_id}, fetchall=True)
    menu_items = execute_query("""
    SELECT m.id, m.name, c.name as category 
    FROM menu_item m
    JOIN menu_category c ON m.category_id = c.id
    WHERE m.is_available = 1
    ORDER BY c.name, m.name
    """, fetchall=True)
    total = sum(item[4] for item in order_items) if order_items else 0
    return render_template('order/add_items.html', order=order, order_items=order_items, menu_items=menu_items, total=total)

@app.route('/order/<int:order_id>/submit', methods=['POST'])
def submit_order(order_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    query = """
    UPDATE customer_order 
    SET status = 'preparing', updated_at = CURRENT_TIMESTAMP
    WHERE id = :order_id
    """
    execute_query(query, {'order_id': order_id}, commit=True)
    flash('Order submitted to kitchen')
    return redirect(url_for('active_orders'))

@app.route('/order/<int:order_id>/update_status', methods=['POST'])
def update_order_status(order_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    new_status = request.form.get('status')
    if not new_status:
        flash('Invalid status update')
        return redirect(url_for('order_dashboard'))
    
    query = """
    UPDATE customer_order
    SET status = :status, updated_at = CURRENT_TIMESTAMP
    WHERE id = :order_id
    """
    execute_query(query, {'status': new_status, 'order_id': order_id}, commit=True)
    flash(f'Order #{order_id} status updated to {new_status}')
    return redirect(url_for('order_dashboard'))

@app.route('/orders/active')
def active_orders():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    query = """
    SELECT id, table_number, customer_name, status, total_amount, created_at
    FROM customer_order
    WHERE status IN ('pending', 'preparing')
    ORDER BY created_at DESC
    """
    active_orders = execute_query(query, fetchall=True)
    return render_template('order/active_orders.html', active_orders=active_orders)


@app.route('/orders', methods=['GET'])
def view_orders():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    query = """
    SELECT id, table_number, customer_name, status, total_amount, created_at
    FROM customer_order
    ORDER BY id DESC
    """
    orders = execute_query(query, fetchall=True)
    return render_template('order/view_orders.html', orders=orders)


@app.route('/orders/new', methods=['GET', 'POST'])
def create_order():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        table_number = request.form['table_number']
        customer_name = request.form['customer_name']
        
        query_sequence = "SELECT customer_order_seq.NEXTVAL FROM DUAL"
        with get_db_connection() as connection:
            cursor = connection.cursor()
            cursor.execute(query_sequence)
            new_order_id = cursor.fetchone()[0]
        
        query = """
        INSERT INTO customer_order (id, table_number, customer_name, status, created_at)
        VALUES (:id, :table_number, :customer_name, 'pending', CURRENT_TIMESTAMP)
        """
        execute_query(
            query,
            {'id': new_order_id, 'table_number': table_number, 'customer_name': customer_name},
            commit=True
        )
        flash(f'Order #{new_order_id} created successfully')
        return redirect(url_for('add_order_items', order_id=new_order_id))
    
    return render_template('order/new_order.html')

if __name__ == '__main__':
    app.run(debug=True)
