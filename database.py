import cx_Oracle
import os
from contextlib import contextmanager

# Database connection details
DB_USER = "restaurant"
DB_PASSWORD = "restaurant" 
DB_DSN = "localhost:1521/xe"  
@contextmanager
def get_db_connection():
    """Context manager for Oracle database connections"""
    connection = None
    try:
        connection = cx_Oracle.connect(user=DB_USER, password=DB_PASSWORD, dsn=DB_DSN)
        yield connection
    except cx_Oracle.DatabaseError as e:
        print(f"Database error: {e}")
        raise
    finally:
        if connection:
            connection.close()

def execute_query(query, params=None, fetchone=False, fetchall=False, commit=False):
    """Execute a query and return results based on parameters"""
    with get_db_connection() as connection:
        cursor = connection.cursor()
        try:
            cursor.execute(query, params or {})
            
            if commit:
                connection.commit()
                return cursor.rowcount
            
            if fetchall:
                return cursor.fetchall()
            elif fetchone:
                return cursor.fetchone()
            return None
        except cx_Oracle.IntegrityError as e:
            print(f"Integrity error: {e}")
            raise ValueError("A database integrity error occurred. Please check for duplicate entries or constraints.") from e
        finally:
            cursor.close()
