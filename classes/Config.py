import json

class Config:
    def __init__(self):
        self._load("./config.json")
    
    def _load(self, fichier_json):
        with open(fichier_json, 'r', encoding='utf-8') as fichier:
            data = json.load(fichier)
            for key, value in data.items():
                setattr(self, key, value)