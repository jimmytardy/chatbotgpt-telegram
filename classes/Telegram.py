from telethon import TelegramClient, events, sync
from telethon.tl.types import PeerUser, PeerChannel
from classes.ChatGPT import ChatGPT
from classes.MongoDBManager import MongoDBManager
import os
from random import randint
from time import sleep
import json
import asyncio
import concurrent.futures

class Telegram:
    def __init__(self, config):
        self.client = TelegramClient('session', config.telegram.get('API').get('api_id'), config.telegram.get('API').get('api_hash'))
        self.config = config
        self.message_interval = [config.telegram.get('message').get('interval_min'), config.telegram.get('message').get('interval_max')]
        self.chatgpt = ChatGPT(config)
        self.mongodb = MongoDBManager(config)
        self.voice = config.telegram.get('message').get('voice')
        self.image = config.telegram.get('message').get('image')
        self.link = config.telegram.get('message').get('link')
        self.channel_ids = config.channel_id

    async def start(self):
        @self.client.on(events.NewMessage(chats=self.channel_ids))
        async def new_message_handler(event):
            await self.onNewUpdateMessage(event)
        @self.client.on(events.MessageEdited(chats=self.channel_ids))
        async def update_message_handler(event):
            await self.onNewUpdateMessage(event)

        @self.client.on(events.MessageDeleted(chats=self.channel_ids))
        async def delete_message_handler(event):
            await self.onNewUpdateMessage(event)

        await self.client.start(self.config.telegram.get('API').get('phone'))
        self.me = await self.client.get_me()
        await self.client.run_until_disconnected()

    def get_channel_id_from_peer_id(self, peer_id):
        if hasattr(peer_id, 'user_id'):
            return peer_id.user_id
        # Traitez les actions pour un utilisateur
        elif hasattr(peer_id, 'channel_id'):
            return peer_id.channel_id

    async def onNewUpdateMessage(self, event):
        channel_id = self.get_channel_id_from_peer_id(event.peer_id)
        try:
            if await self._on_action_bot(event, channel_id):
                return
            
            message = await self.get_dict_from_message(event.message, channel_id)
            await self.onNewUpdateMessageWorker(channel_id, message)
        except:
            return await self.send_text(channel_id, ['[Message du bot]: Une erreur est survenue'], True)

            
    async def onNewUpdateMessageWorker(self, channel_id, message, only_insert=False):
        message_exist = self.mongodb.find_document('messages', {'message_id': message['message_id'], 'channel_id': message['channel_id']})
        if message_exist:
            self.mongodb.update_document('messages', {'message_id': message['message_id']}, message)
        else:
            message["createdAt"] = message['updatedAt']
            self.mongodb.insert_document('messages', message)
            if only_insert: return
            await self.send_chatgpt_answer(message.get('channel_id'), message)

    def get_chatgpt_messages(self, channel_id):
        messages = self.mongodb.find_documents('messages', {'channel_id': channel_id})
        messages_to_chatgpt = list(map(lambda message: {
            'role': message.get('role'),
            'content': message.get('content')
        }, messages))
        return messages_to_chatgpt

    def lock_answer_user(self, channel_id):
        user_state = self.mongodb.find_document('users_state', { 'channel_id': channel_id })
        if user_state is None:
            user_state = {
                'channel_id': channel_id,
                'state': 'lock'
            }
            self.mongodb.insert_document('users_state', user_state)
            return True
        else:
            if user_state == 'finish' or user_state == 'lock':
                return False
            user_state['state'] = 'lock'
            self.mongodb.update_document('users_state', { 'channel_id': channel_id }, user_state)
            return True

    async def send_chatgpt_answer(self, channel_id, message):
        if not self.lock_answer_user(channel_id): return
        timer = randint(self.message_interval[0], self.message_interval[1])
        sleep(timer)
        sleep(2)
        last_message = await self.update_messages_after(channel_id, message)

        if self.is_from_me(last_message): return

        messages = self.get_chatgpt_messages(channel_id)
        if messages[-1].get('role') == 'assistant': return
        answer = json.loads(self.chatgpt.get_answer(messages))
        text = answer.get('answer') 
        response = None
        
        if answer.get('finish'):  
            return self.mongodb.update_document('users_state', { 'channel_id': channel_id }, { 'state': 'finish' })
        
        if text is not None and text.strip() != '':
            response = await self.send_text(channel_id, text, True)
        elif answer.get('sendVocal1'):
            full_path = os.getcwd() + self.voice.get('vocal1')
            response = await self.send_vocal(channel_id, full_path)
            text = self.chatgpt.get_text_from_vocal(full_path)
        elif answer.get('sendVocal2'):
            full_path = os.getcwd() + self.voice.get('vocal2')
            response = await self.send_vocal(channel_id, full_path)
            text = self.chatgpt.get_text_from_vocal(full_path)
        elif answer.get('sendPhoto1'):
            full_path = os.getcwd() + self.image.get('path1')
            response = await self.send_image(channel_id, full_path)
        elif answer.get('sendPhoto2'):
            full_path = os.getcwd() + self.image.get('path2')
            response = await self.send_image(channel_id, full_path)
        elif answer.get('sendLink'):
            response = await self.send_text(channel_id, self.link)

        message = {
            'role': 'assistant',
            'content': text,
            "channel_id": channel_id,
            "message_id": response.id,
            "createdAt": response.date,
            "updatedAt": response.date,
            "chatgpt_answer": answer,
        }
        self.mongodb.insert_document('messages', message)
        self.mongodb.update_document('users_state', { 'channel_id': channel_id }, { 'state': 'unlock' })
        

    def is_from_me(self, message):
        return message.sender.id == self.me.id
    
    async def send_text(self, destinataire, message, ignoreTimer=False):
        async with self.client.action(destinataire, 'typing'):
            if ignoreTimer == False:
                timer = randint(self.config.telegram.get('message').get('interval_min_typing'), self.config.telegram.get('message').get('interval_max_typing'))
                sleep(timer)
            response = await self.client.send_message(destinataire, message)
            await self.client.action(destinataire, 'cancel')
            return response

    async def send_vocal(self, destinataire, fichier_vocal):
        async with self.client.action(destinataire, 'record-audio'):
            timer = randint(self.config.telegram.get('message').get('interval_min_typing'), self.config.telegram.get('message').get('interval_max_typing'))
            sleep(timer)
            response = await self.client.send_file(destinataire, fichier_vocal, voice_note=True)
            await self.client.action(destinataire, 'cancel')
            return response
        
    async def send_image(self, destinataire, fichier_image):
        async with self.client.action(destinataire, 'record-round'):
            timer = randint(self.config.telegram.get('message').get('interval_min_typing'), self.config.telegram.get('message').get('interval_max_typing'))
            sleep(timer)
            response = await self.client.send_file(destinataire, fichier_image)
            await self.client.action(destinataire, 'cancel')
            return response

    async def update_messages_after(self, channel_id, message):
        messages = []
        messages_telegram = await self.client.get_messages(channel_id, limit=10)
        last_message = messages_telegram[0]
        for message_telegram in messages_telegram:
            if message_telegram.id <= message.get('message_id') or self.is_from_me(message_telegram):
                continue
            message = await self.get_dict_from_message(message_telegram, channel_id)
            self.onNewUpdateMessageWorker(channel_id, message, True)
        return last_message

    async def _on_action_bot(self, event, channel_id):
        if event.message.message.strip() == 'reset':
            self.mongodb.delete_documents('messages', {'channel_id': channel_id})
            self.mongodb.delete_documents('users_state', {'channel_id': channel_id})
            await self.send_text(channel_id, '[Action du bot non enregistré]: La conversation a été réinitialisé', True)
            return True
        if event.message.message.startswith('[PROMPT MODIF]'):
            new_prompt = event.message.message.replace('[PROMPT MODIF]', '', 1).strip()
            self.mongodb.update_document('prompt', {}, { 'text': new_prompt })
            await self.send_text(channel_id, '[Action du bot non enregistré]: Modification du prompt réussi', True)
            return True
        if event.message.message.startswith('[PROMPT]'):
            new_prompt = event.message.message.replace('[PROMPT]', '', 1).strip()
            await self.send_text(channel_id, self.chatgpt.get_prompt(), True)
            return True
        if event.message.message.startswith('[CHATGPT-ANSWER]'):
            messages = self.mongodb.find_documents('messages', { 'channel_id': channel_id, 'role': 'assistant' })
            messages = list(map(lambda message: message['chatgpt_answer'], messages))
            await self.send_text(channel_id, json.dumps(messages, sort_keys=True, indent=4), True)
            return True

        last_message_system = self.mongodb.find_document('messages', { 'channel_id': channel_id, 'role': 'assistant'})
        if last_message_system is not None and last_message_system['chatgpt_answer'].get('finish', None):
            await self.send_text(channel_id, ['[Message du bot]: La discussion est dans un statut terminé'], True)
            return True
        
        return False

    async def get_dict_from_message(self, message, channel_id):
        message = {
            'role': 'user',
            'content': message.message,
            "reply_to": message.reply_to,
            "channel_id": channel_id,
            "message_id": message.id,
            "updatedAt": message.date
        }
        if message.get('media_unread'):
            path = await message.download_media()
            message['content'] = self.chatgpt.get_text_from_vocal(path)
            os.remove(path)
        return message