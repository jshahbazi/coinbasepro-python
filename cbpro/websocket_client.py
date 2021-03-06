# cbpro/WebsocketClient.py
# original author: Daniel Paquin
# mongo "support" added by Drew Rice
#
#
# Template object to receive messages from the Coinbase Websocket Feed

from __future__ import print_function
import json
import base64
import hmac
import hashlib
import time
import multiprocessing
from threading import Thread
# from websocket import create_connection, WebSocketConnectionClosedException
import asyncio
import websockets
from pymongo import MongoClient
from cbpro.cbpro_auth import get_auth_headers
import traceback



class WebsocketClient(object):
    def __init__(self, url="wss://ws-feed.pro.coinbase.com", products=None, message_type="subscribe", mongo_collection=None,
                 should_print=False, auth=False, api_key="", api_secret="", api_passphrase="", channels=None):
        self.url = url
        self.products = products
        self.channels = channels
        self.type = message_type
        self.error = None
        self.ws = None
        self.thread = None
        self.auth = auth
        self.api_key = api_key
        self.api_secret = api_secret
        self.api_passphrase = api_passphrase
        self.should_print = should_print
        self.mongo_collection = mongo_collection
        self.shutdown_event = multiprocessing.Event()

    def start(self):
        def _go():
            sub_params = self._connect()
            # self.keepalive = Thread(target=self._keepalive)
            asyncio.get_event_loop().run_until_complete(self._listen(sub_params))
            self._disconnect()

        self.on_open()
        self.thread = multiprocessing.Process(target=_go)
        self.thread.start()
        

    def _connect(self):
        if self.products is None:
            self.products = ["BTC-USD"]
        elif not isinstance(self.products, list):
            self.products = [self.products]

        if self.url[-1] == "/":
            self.url = self.url[:-1]

        if self.channels is None:
            sub_params = {'type': 'subscribe', 'product_ids': self.products}
        else:
            sub_params = {'type': 'subscribe', 'product_ids': self.products, 'channels': self.channels}

        if self.auth:
            timestamp = str(time.time())
            message = timestamp + 'GET' + '/users/self/verify'
            auth_headers = get_auth_headers(timestamp, message, self.api_key, self.api_secret, self.api_passphrase)
            sub_params['signature'] = auth_headers['CB-ACCESS-SIGN']
            sub_params['key'] = auth_headers['CB-ACCESS-KEY']
            sub_params['passphrase'] = auth_headers['CB-ACCESS-PASSPHRASE']
            sub_params['timestamp'] = auth_headers['CB-ACCESS-TIMESTAMP']

        return sub_params

    # def _keepalive(self, interval=30):
    #     while not self.shutdown_event.is_set():
    #         self.ws.ping("keepalive")
    #         time.sleep(interval)

    async def _listen(self,sub_params):
        async with websockets.connect(self.url) as websocket:
            await websocket.send(json.dumps(sub_params))
            # self.keepalive.start()
            while not self.shutdown_event.is_set():
                try:
                    data = await websocket.recv()
                    msg = json.loads(data)
                except ValueError as e:
                    self.on_error(e)
                except Exception as e:
                    self.on_error(e)
                else:
                    self.on_message(msg)

    def _disconnect(self):
        self.on_close()

    def close(self):
        self.shutdown_event.set()
        self._disconnect() # force disconnect so threads can join
        self.thread.join()

    def on_open(self):
        if self.should_print:
            print("-- Subscribed! --\n")

    def on_close(self):
        if self.should_print:
            print("\n-- Socket Closed --")

    def on_message(self, msg):
        if self.should_print:
            print(msg)
        if self.mongo_collection:  # dump JSON to given mongo collection
            self.mongo_collection.insert_one(msg)

    def on_error(self, e, data=None):
        self.error = e
        self.shutdown_event.set()
        # if self.should_print:
        # print('{} - data: {}'.format(e, data))
        # print(f"Websocket error: {e}")


if __name__ == "__main__":
    import sys
    import cbpro
    import time


    class MyWebsocketClient(cbpro.WebsocketClient):
        def on_open(self):
            self.url = "wss://ws-feed.pro.coinbase.com/"
            self.products = ["BTC-USD", "ETH-USD"]
            self.message_count = 0
            print("Let's count the messages!")

        def on_message(self, msg):
            print(json.dumps(msg, indent=4, sort_keys=True))
            self.message_count += 1

        def on_close(self):
            print("-- Goodbye! --")


    wsClient = MyWebsocketClient()
    wsClient.start()
    print(wsClient.url, wsClient.products)
    try:
        while True:
            print("\nMessageCount =", "%i \n" % wsClient.message_count)
            time.sleep(1)
    except KeyboardInterrupt:
        wsClient.close()

    if wsClient.error:
        sys.exit(1)
    else:
        sys.exit(0)
