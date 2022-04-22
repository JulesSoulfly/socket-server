import datetime

class Client:
    ip: str
    port: int
    id_login: int
    id_player: int
    connection = None
    last_ping: datetime.datetime

    def __init__(self, adr, con, id_login, id_player):
        self.address = adr
        self.connection = con
        self.id_login = id_login
        self.id_player = id_player
        self.last_ping = datetime.datetime.now()

    @property
    def address(self):
        return (ip, port)

    @address.setter
    def address(self, a_address):
        ip = a_address[0]
        port = a_address[1]
