from openai import OpenAI
from classes.MongoDBManager import MongoDBManager
import tiktoken

class ChatGPT:
    def __init__(self, config):
        self.mongodb = MongoDBManager(config)
        self.client = OpenAI(api_key=config.chatgpt.get('api_key'))
        prompt = self.get_prompt()

        if prompt is None:
            with open(config.chatgpt.get('prompt'), 'r', encoding='utf-8') as file:
                text = file.read()
                self.mongodb.insert_document('prompt', { 'text': text})
        

    def get_prompt(self):
        prompt = self.mongodb.find_document('prompt', {})
        if prompt is None:
            return None
        else:
            return prompt.get('text')

    def get_text_from_vocal(self, path):
        with open(path, "rb") as audio_file:
            transcription = self.client.audio.transcriptions.create(
                model="whisper-1", 
                file=audio_file
            )
        return transcription.text


    def get_answer(self, messages):
        prompt = self.get_prompt()
        messages.insert(0, {
            'role': 'system',
            'content': prompt
        })
        response = self.client.chat.completions.create(
            model="gpt-4-turbo-preview",
            temperature=0,
            messages=messages,
            response_format={ "type": "json_object" }
        )
        # return emoji.emojize('Désolée, je préfère garder un peu de mystère pour le moment')
        return response.choices[0].message.content.strip()