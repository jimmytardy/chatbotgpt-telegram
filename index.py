from classes.Config import Config
from classes.Telegram import Telegram

config = Config()
telegram = Telegram(config)
with telegram.client:
    telegram.client.loop.run_until_complete(telegram.start())