import os
import certifi
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv()

client = MongoClient(
    os.environ["MONGODB_URI"],
    tls=True,
    tlsCAFile=certifi.where(),
)

db = client[os.environ.get("MONGODB_DB", "coup_research")]

print(client.admin.command("ping"))
print("Connected.")