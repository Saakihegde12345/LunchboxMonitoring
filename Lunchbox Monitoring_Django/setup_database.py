import mysql.connector

try:
    # Connect to MySQL server (without specifying a database)
    conn = mysql.connector.connect(
        host="127.0.0.1",
        user="root",
        password=""
    )
    
    cursor = conn.cursor()
    
    # Create database if it doesn't exist
    cursor.execute("CREATE DATABASE IF NOT EXISTS lunchbox_monitoring CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
    print("Database 'lunchbox_monitoring' created or already exists.")
    
    # Grant privileges (adjust as needed for your security requirements)
    cursor.execute("GRANT ALL PRIVILEGES ON lunchbox_monitoring.* TO 'root'@'localhost'")
    print("Privileges granted.")
    
    cursor.close()
    conn.close()
    
except mysql.connector.Error as err:
    print(f"Error: {err}")
    if 'conn' in locals():
        conn.rollback()
finally:
    if 'conn' in locals() and conn.is_connected():
        conn.close()
        print("MySQL connection is closed.")
