from mysql.connector import connect, Error

db_config = {}

def logout(id_login):
	try:
		with connect(**db_config) as con:
			with con.cursor() as cursor:
				query = "UPDATE login SET IsLogin = '0' WHERE id = %s"
				args = (id_login,)
				cursor.execute(query, args)
				con.commit()
	except Error as e:
		print(e)
