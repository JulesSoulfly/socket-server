import os
import sys
from datetime import datetime


my_folder = ''
if getattr(sys, 'frozen', False):
    my_folder = os.path.dirname(sys.executable) # sys._MEIPASS
elif __file__:
    my_folder = os.path.abspath(os.path.dirname(__file__))

def concat_path(lst):
	return os.path.join(*lst)

def get_full_path(file):
	if file: return concat_path([my_folder, file])

def read_lines(path, a_encoding = None):
	if os.path.isfile(path):
		with open(path, 'r', encoding = a_encoding) as f:
			res = f.read().split('\n')
		return res

def parse_settings(path):
	res = {}
	lines = read_lines(path)
	if lines and all(['=' in x for x in lines]):
		lines = [x.split(' = ') for x in lines]
		if lines and len(lines) > 0:
			res = {x[0]: x[1] for x in lines}
			for k, v in res.items():
				try: v = int(v)
				except: pass
				res[k] = v
	return res

log_file = get_full_path('log_error.log')

def log_error(msg, error):
	with open(log_file, 'a', encoding = 'utf-16') as f:
		f.write('[' + datetime.utcnow().strftime("%d-%m-%Y %H:%M:%S") \
			   + '] - ' + msg + '\n' + str(error) + '\n')