from pymongo import MongoClient


class MongoDBManager:
    _instance = None
    client = None
    db = None
    def __new__(cls, config):
        if cls._instance is None:
            cls._instance = super(MongoDBManager, cls).__new__(cls)
            cls.client = MongoClient(host=config.db.get('uri'), connect=True)
            cls.db = cls.client[config.db.get('name')]

        return cls._instance


    def insert_document(cls, collection_name, document):
        collection = cls.db[collection_name]
        return collection.insert_one(document).inserted_id

    def find_document(cls, collection_name, query):
        collection = cls.db[collection_name]
        return collection.find_one(query)

    def find_documents(cls, collection_name, query={}, sort={ 'createdAt': -1 }):
        collection = cls.db[collection_name]
        return list(collection.find(query))

    def update_document(cls, collection_name, query, new_values):
        collection = cls.db[collection_name]
        return collection.update_one(query, {'$set': new_values})

    def delete_document(cls, collection_name, query):
        collection = cls.db[collection_name]
        return collection.delete_one(query)

    def delete_documents(cls, collection_name, query):
        collection = cls.db[collection_name]
        return collection.delete_many(query)