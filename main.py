import sys
import time
import socket
import threading
import struct
import datetime
import enum
import traceback
import logging
from typing import Dict
from client import Client
import utils
import sql_connector


server_address = None
ID_MAP: int
START_PACKET_TIMEOUT = 10
BLOCK_IP_TIME = 30
PACKET_SIZE = 1024
CLIENT_PING_TIMEOUT = 10

try:
    if len(sys.argv[1]) < 4: raise Exception
    server_address = (sys.argv[1], int(sys.argv[2]))
    ID_MAP = int(sys.argv[3])
except:
    print('Неверные аргументы [IP, PORT, ID_MAP]. Программа завершается')
    time.sleep(5)
    sys.exit()

sql_connector.db_config = utils.parse_settings(utils.get_full_path('_db_config.txt'))

@enum.unique
class D1(enum.IntEnum):
    start = 11
    click = 22
    close = 33
    ping  = 66

d1_unpuck = {
    # start packet
    # d1 (int) - type of packet = 11
    # id_map    : int
    # id_player : int
    # id_login  : int
    D1.start: 'iii',

    # click packet
    # d1 (int) - type of packet = 22
    # id_map    : int
    # x         : float
    # y         : float
    # z         : float
    # d2        : int
    # id_player : int
    # id_login  : int
    D1.click: 'ifffiii',

    # on close packet
    # d1 (int) - type of packet = 33
    D1.close: 'iii',

    # ping packet
    # d1 (int) - type of packet = 66
    D1.ping: ''
}

client_dict_lock = threading.Lock()
clients = {} # [(str, int), Client]

block_adr_lock = threading.Lock()
blocked_addresses = {} # [(str, int), datetime.datetime]

print('Старт сервера на {} порт {}'.format(*server_address))
server_socket = socket.create_server(server_address, backlog=10)


def init_logger():
    logger = logging.getLogger('logger')
    logger.setLevel(logging.DEBUG)
    formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s')
    fh = logging.FileHandler('logfile.log')
    sh = logging.StreamHandler()
    fh.formatter = formatter
    sh.formatter = formatter
    logger.addHandler(fh)
    logger.addHandler(sh)
    return logger

logger = init_logger()


def connect_processing(soc, con, adr):
    logger.info('Попытка соединения от: {}'.format(adr))
    if address_is_blocked(adr[0]):
        close_connection_with_error('Адрес был заблокирован. ', adr, con)
        return
    if adr not in clients:
        print('Ожидание рукопожатия от:', adr)
        con.settimeout(START_PACKET_TIMEOUT)
        try:
            data = message_handler(adr, con)
        except socket.timeout:
            close_connection_with_error('Превышен интервал ожидания стартового пакета. ', adr, con)
            block_address(adr[0])
            return
        if data:
            logger.info('Получено (len={}): {} от {}'.format(len(data), data, adr))
            try:
                d1, id_map, id_player, id_login = struct.unpack('i' + d1_unpuck[D1.start], data)
                logger.info('Расшифровано: {}, {}, {}, {} от {}'.format(d1, id_map, id_player, id_login, adr))
                if d1 != D1.start.value or id_map != ID_MAP: raise ValueError()
            except:
                close_connection_with_error('Неверный формат стартового пакета, или неверные значения. ', adr, con)
                block_address(adr[0])
                return
        else:
            close_connection_with_error('Данные отсутствуют или клиент закрыл соединение. ', adr, con)
            block_address(adr[0])
            return
        try:
            add_client(adr, con, id_login, id_player)
        except:
            close_connection_with_error('Непредвиденая ошибка: {}. '.format(traceback.format_exc()), adr, con)
            return
        logger.info('Соединение с {} успешно установлено'.format(adr))
        listen_connect(soc, adr)

def add_client(adr, con, id_login, id_player):
    try:
        client_dict_lock.acquire()
        сlient = create_client(adr, con, id_login, id_player)
        clients[adr] = сlient
    finally:
        client_dict_lock.release()

def get_client(adr):
    client = None
    try:
        client_dict_lock.acquire()
        if adr in clients: client = clients[adr]
    finally:
        client_dict_lock.release()
    return client

def delete_client(adr):
    try:
        client_dict_lock.acquire()
        if adr in clients: del clients[adr]
    finally:
        client_dict_lock.release()

def create_client(adr, con, id_login, id_player):
    сlient = Client(adr, con, id_login, id_player)
    return сlient

def on_client_closed_connection(adr):
    close_connection(adr, '{} закрыл соединение'.format(adr))

def close_connection_with_error(msg, adr, con):
    con.close()
    logger.info(msg + ' Соединение с {} закрыто'.format(adr))

def close_connection(adr, msg = None):
    if not msg: msg = 'Соединение с {} закрыто'.format(adr)
    clients[adr].connection.close()
    sql_connector.logout(clients[adr].id_login)
    delete_client(adr)
    logger.info(msg)

def address_is_blocked(ip):
    if ip in blocked_addresses:
        if (datetime.datetime.now() - blocked_addresses[ip]).total_seconds() >= BLOCK_IP_TIME:
            unblock_address(ip)
            return False
        else: return True
    else: return False

def block_address(ip):
    block_adr_lock.acquire()
    blocked_addresses[ip] = datetime.datetime.now()
    block_adr_lock.release()

def unblock_address(ip):
    block_adr_lock.acquire()
    if ip in blocked_addresses: del blocked_addresses[ip]
    block_adr_lock.release()

def parse_packet(d1_type, data):
    dt = struct.unpack(d1_unpuck[d1_type], data[4:])
    print(d1_type, dt)
    return dt

def listen_connect(soc, adr):
    client = get_client(adr)
    con = client.connection
    con.settimeout(CLIENT_PING_TIMEOUT)
    while con.fileno() != -1:
        try:
            data = message_handler(adr, con)
            if data:
                d1: int
                try:
                    d1 = struct.unpack('i', data[0:4])[0]
                    if d1 not in [x.value for x in D1]: raise
                except:
                    logger.error('Неверный формат пакета от {}, получен тип: {}'.format(ard, d1))
                    continue
                try:
                    if d1 == D1.click.value:         # 22
                        id_map, x, y, z, d2, id_player, id_login = parse_packet(D1.click, data)
                        if id_map != ID_MAP: raise ValueError()
                        closed = broadcast(data, adr)
                    elif d1 == D1.close.value: pass  # 33
                    elif d1 == D1.ping.value: pass   # 66
                except ValueError:
                    logger.error('Неверные данные от {}'.format(adr))
                    continue
                except:
                    logger.error('Непредвиденая ошибка от {}: {}'.format(adr, traceback.format_exc()))
                    continue
            else:
                on_client_closed_connection(adr)
        except socket.timeout:
            mes = struct.pack('i', D1.ping.value)
            try: con.sendall(mes)
            except:
                on_client_closed_connection(adr)
                break

def message_handler(adr, con):
    data = None
    try:
        while True:
            data = con.recv(PACKET_SIZE)
            if data: print('Получено (len={}): {} от {}'.format(len(data), data, adr))
            break
    except socket.timeout: raise socket.timeout
    except ConnectionResetError: pass
    except ConnectionAbortedError: pass
    except: print(traceback.format_exc())
    return data

def broadcast(data, sender):
    for adr, client in clients.items():
        if adr != sender:
            try: client.connection.sendall(data)
            except ConnectionResetError: pass
            except ConnectionAbortedError: pass
            except: print(traceback.format_exc())

def connects_reciever(server_socket):
    while True:
        print('Ожидание соединения...')
        connection, client_address = server_socket.accept()
        thread = threading.Thread(group=None, target=connect_processing, args=(server_socket, connection, client_address),
                                  daemon=True)
        thread.start()

def main():
    reciever_thread = threading.Thread(group=None, target=connects_reciever, args=(server_socket,), daemon=True)
    reciever_thread.start()
    while True:
        try: time.sleep(0.1)
        except KeyboardInterrupt: return  # ctrl+C

if __name__ == '__main__':
    try: main()
    except:
        logger.critical(traceback.format_exc())
        time.sleep(5)
