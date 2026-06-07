from qdrant_client import QdrantClient

# Connect to your local Qdrant instance
client = QdrantClient(url="http://localhost:6333")

collection_name = "docs"

if client.collection_exists(collection_name):
    print(f"Deleting collection: {collection_name}...")
    client.delete_collection(collection_name)
    print("Collection deleted successfully.")
else:
    print(f"Collection '{collection_name}' does not exist.")