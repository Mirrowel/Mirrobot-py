# utils/rag_manager.py
import logging
import os
import uuid
import qdrant_client
import google.generativeai as genai
import cachetools
import dataclasses
import collections
from typing import Optional
from qdrant_client.http.models import PointStruct, UpdateStatus, ScrollResponse, Filter, Must, VectorParams, Distance
from utils.constants import PKB_COLLECTION_NAME
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_community.vectorstores import FAISS

logger = logging.getLogger('discord_bot.rag_manager')

@dataclasses.dataclass
class RAGDebugLog:
    session_id: str
    full_context: str = ""
    refined_query: str = ""
    retrieved_context: str = ""
    final_prompt: str = ""
    final_answer: str = ""

class RAGManager:
    def __init__(self, config, llm_config):
        self.config = config
        self.llm_config = llm_config
        self.qdrant_client = None
        self.embedding_model = None
        self.rag_cache = cachetools.TTLCache(maxsize=100, ttl=3600)
        self.debug_logs = collections.deque(maxlen=10)
        logger.info("RAGManager initialized with a TTL cache (maxsize=100, ttl=3600) and a debug log deque (maxlen=10).")

    async def initialize_clients(self):
        """Initializes Qdrant and embedding model clients."""
        logger.info("Initializing RAG clients...")
        try:
            qdrant_url = os.getenv("QDRANT_URL")
            qdrant_api_key = os.getenv("QDRANT_API_KEY")
            google_api_key = os.getenv("GOOGLE_API_KEY")

            if not all([qdrant_url, qdrant_api_key, google_api_key]):
                logger.error("Missing one or more environment variables: QDRANT_URL, QDRANT_API_KEY, GOOGLE_API_KEY")
                return

            # Configure Google Generative AI
            genai.configure(api_key=google_api_key)
            logger.info("Successfully configured Google Generative AI client.")

            # Create Qdrant client
            self.qdrant_client = qdrant_client.QdrantClient(url=qdrant_url, api_key=qdrant_api_key)
            logger.info("Successfully connected to Qdrant.")

            # Set embedding model placeholder
            self.embedding_model = GoogleGenerativeAIEmbeddings(model="models/text-embedding-004", task_type="RETRIEVAL_DOCUMENT")
            logger.info(f"Embedding model set to: {self.embedding_model}")

        except Exception as e:
            logger.error(f"Failed to initialize RAG clients: {e}", exc_info=True)

    async def index_document(self, text_content: str, source_name: str, collection_name: str):
        """
        Indexes a document by splitting it into chunks, generating embeddings, and storing them in Qdrant.

        Args:
            text_content (str): The text content of the document.
            source_name (str): The name of the source document (e.g., URL or filename).
            collection_name (str): The name of the Qdrant collection to index into.

        Returns:
            bool: True if indexing was successful, False otherwise.
        """
        logger.info(f"Starting document indexing for source: {source_name} into collection: {collection_name}")
        try:
            # Simple text splitter
            chunks = text_content.split('\n\n')
            chunks = [chunk.strip() for chunk in chunks if chunk.strip()]
            logger.info(f"Split document into {len(chunks)} chunks.")

            points = []
            for chunk in chunks:
                # Generate embedding
                embedding_result = genai.embed_content(
                    model=self.embedding_model,
                    content=chunk,
                    task_type="RETRIEVAL_DOCUMENT"
                )
                
                # Create PointStruct
                point = PointStruct(
                    id=str(uuid.uuid4()),
                    vector=embedding_result['embedding'],
                    payload={"source": source_name, "text": chunk}
                )
                points.append(point)

            if not points:
                logger.warning("No chunks to index after processing.")
                return False

            # Upsert points to Qdrant
            operation_info = self.qdrant_client.upsert(
                collection_name=collection_name,
                wait=True,
                points=points
            )

            if operation_info.status == UpdateStatus.COMPLETED:
                logger.info(f"Successfully indexed {len(points)} points for source: {source_name}")
                return True
            else:
                logger.error(f"Failed to index document for source: {source_name}. Qdrant status: {operation_info.status}")
                return False

        except Exception as e:
            logger.error(f"An error occurred during document indexing for source: {source_name}: {e}", exc_info=True)
            return False

    async def list_documents(self, collection_name: str) -> list[str]:
        """
        Lists all unique source documents in a collection.

        Args:
            collection_name (str): The name of the collection.

        Returns:
            list[str]: A sorted list of unique source names.
        """
        logger.info(f"Listing documents in collection: {collection_name}")
        try:
            # Scroll through all points in the collection
            response: ScrollResponse = self.qdrant_client.scroll(
                collection_name=collection_name,
                limit=1000,  # Adjust limit as needed for your scale
                with_payload=["source"],
                with_vectors=False
            )
            
            # Extract unique source names
            sources = {point.payload['source'] for point in response.points if 'source' in point.payload}
            
            logger.info(f"Found {len(sources)} unique sources.")
            return sorted(list(sources))

        except Exception as e:
            logger.error(f"An error occurred while listing documents in {collection_name}: {e}", exc_info=True)
            return []

    async def delete_document(self, source_name: str, collection_name: str) -> bool:
        """
        Deletes all points associated with a specific source document from a collection.

        Args:
            source_name (str): The name of the source to delete.
            collection_name (str): The name of the collection.

        Returns:
            bool: True if the deletion operation was acknowledged, False otherwise.
        """
        logger.info(f"Attempting to delete document: {source_name} from collection: {collection_name}")
        try:
            operation_info = self.qdrant_client.delete(
                collection_name=collection_name,
                points_selector=Filter(
                    must=[
                        Must(
                            key="source",
                            match={"value": source_name}
                        )
                    ]
                ),
                wait=True
            )

            if operation_info.status == UpdateStatus.COMPLETED:
                logger.info(f"Successfully deleted points for source: {source_name}.")
                return True
            else:
                logger.warning(f"Deletion for source {source_name} completed with status: {operation_info.status}")
                return True # Still return True as the operation was processed

        except Exception as e:
            logger.error(f"An error occurred during document deletion for source: {source_name}: {e}", exc_info=True)
            return False

    async def query_knowledge_base(self, query_text: str, collection_names: list[str], top_k: int = 5) -> str:
        """
        Queries the knowledge base using hybrid search.

        Args:
            query_text (str): The user's query.
            collection_names (list[str]): A list of collection names to search.
            top_k (int): The number of results to return.

        Returns:
            str: A concatenated string of the search results' text.
        """
        logger.info(f"Querying knowledge base with text: '{query_text[:50]}...' in collections: {collection_names}")
        if not self.qdrant_client:
            logger.error("Qdrant client not initialized.")
            return ""

        try:
            # Generate embedding for the query
            embedding_result = genai.embed_content(
                model=self.embedding_model,
                content=query_text,
                task_type="RETRIEVAL_QUERY"
            )
            query_embedding = embedding_result['embedding']

            # Perform the search
            search_results = self.qdrant_client.search(
                collection_name=collection_names[0], # Assuming searching one collection for now as per spec
                query_vector=query_embedding,
                limit=top_k
            )

            # Process results
            context_parts = [point.payload['text'] for point in search_results if 'text' in point.payload]
            
            if not context_parts:
                logger.info("No relevant documents found in the knowledge base.")
                return ""

            concatenated_context = "\n\n---\n\n".join(context_parts)
            logger.info(f"Retrieved {len(context_parts)} context parts from knowledge base.")
            return concatenated_context

        except Exception as e:
            logger.error(f"An error occurred during knowledge base query: {e}", exc_info=True)
            return ""

    async def create_temp_collection(self, session_id: str) -> str:
        """
        Creates a new temporary collection for a session.

        Args:
            session_id (str): A unique identifier for the session.

        Returns:
            str: The name of the created collection.
        """
        collection_name = f"temp_session_{session_id}"
        logger.info(f"Creating temporary collection: {collection_name}")
        try:
            self.qdrant_client.recreate_collection(
                collection_name=collection_name,
                vectors_config=VectorParams(size=768, distance=Distance.COSINE),
            )
            logger.info(f"Successfully created collection: {collection_name}")
            return collection_name
        except Exception as e:
            logger.error(f"Failed to create temporary collection {collection_name}: {e}", exc_info=True)
            raise

    async def destroy_temp_collection(self, collection_name: str) -> bool:
        """
        Deletes a temporary collection.

        Args:
            collection_name (str): The name of the collection to delete.

        Returns:
            bool: True if deletion was successful, False otherwise.
        """
        logger.info(f"Destroying temporary collection: {collection_name}")
        try:
            result = self.qdrant_client.delete_collection(collection_name=collection_name)
            if result:
                logger.info(f"Successfully destroyed collection: {collection_name}")
                return True
            else:
                logger.warning(f"Collection {collection_name} destruction returned False.")
                return False
        except Exception as e:
            logger.error(f"Failed to destroy temporary collection {collection_name}: {e}", exc_info=True)
            return False

    async def cleanup_orphaned_collections(self):
        """
        Deletes all temporary collections that may have been left over.
        """
        logger.info("Starting cleanup of orphaned temporary collections...")
        try:
            collections_response = self.qdrant_client.get_collections()
            all_collections = collections_response.collections
            orphaned_count = 0
            for collection in all_collections:
                if collection.name.startswith("temp_session_"):
                    logger.info(f"Found orphaned collection: {collection.name}. Deleting...")
                    await self.destroy_temp_collection(collection.name)
                    orphaned_count += 1
            
            if orphaned_count > 0:
                logger.info(f"Cleanup complete. Destroyed {orphaned_count} orphaned collections.")
            else:
                logger.info("No orphaned collections found.")

        except Exception as e:
            logger.error(f"An error occurred during orphaned collection cleanup: {e}", exc_info=True)

    async def generate_search_query(self, context: str) -> str:
        """
        Uses an LLM to generate a high-quality search query from the user's message and file content.

        Args:
            context (str): The combined context from the user's question and file content.

        Returns:
            str: A concise, keyword-rich search query.
        """
        logger.info("Generating a refined search query using LLM...")
        try:
            prompt = (
                "You are an expert at analyzing user requests and technical logs. Based on the following context, "
                "generate a single, concise search query that best summarizes the core technical problem. "
                "The query should be ideal for searching a knowledge base of technical documents.\n\n"
                "Context:\n"
                "---\n"
                f"{context}\n"
                "---\n\n"
                "Search Query:"
            )

            model = genai.GenerativeModel('gemini-1.5-flash')
            response = await model.generate_content_async(prompt)
            
            refined_query = response.text.strip()
            logger.info(f"Generated refined search query: '{refined_query}'")
            return refined_query

        except Exception as e:
            logger.error(f"Failed to generate search query: {e}", exc_info=True)
            # Fallback to using the original context as the query in case of an error
            return context[:512] # Truncate to a reasonable length

    def get_cached_response(self, cache_key: str) -> Optional[str]:
        """
        Retrieves a response from the cache.

        Args:
            cache_key (str): The key to look up in the cache.

        Returns:
            Optional[str]: The cached response, or None if not found.
        """
        return self.rag_cache.get(cache_key)

    def set_cached_response(self, cache_key: str, context: str):
        """
        Stores a response in the cache.

        Args:
            cache_key (str): The key to store the response under.
            context (str): The response context to cache.
        """
        self.rag_cache[cache_key] = context
        logger.info(f"Cached response for key: {cache_key}")

    def create_in_memory_index(self, texts: list[str]) -> Optional[FAISS]:
        """
        Creates an in-memory FAISS index from a list of text documents.

        Args:
            texts (list[str]): A list of raw text strings.

        Returns:
            Optional[FAISS]: The created FAISS vectorstore object, or None on failure.
        """
        logger.info(f"Attempting to create in-memory FAISS index from {len(texts)} text documents.")
        if not texts:
            logger.warning("Input 'texts' list is empty or None. Cannot create index.")
            return None

        try:
            text_splitter = RecursiveCharacterTextSplitter(chunk_size=1500, chunk_overlap=200)
            chunks = text_splitter.create_documents(texts)

            if not chunks:
                logger.warning("No document chunks were created after splitting. Cannot create index.")
                return None

            vectorstore = FAISS.from_documents(documents=chunks, embedding=self.embedding_model)
            logger.info(f"Successfully created in-memory FAISS index with {len(chunks)} chunks.")
            return vectorstore

        except Exception as e:
            logger.error(f"Failed to create in-memory FAISS index: {e}", exc_info=True)
            return None

    def query_in_memory_index(self, index: FAISS, query: str, k: int = 3) -> str:
        """
        Queries an in-memory FAISS index.

        Args:
            index (FAISS): The FAISS index to search.
            query (str): The search query.
            k (int): The number of documents to retrieve.

        Returns:
            str: A newline-separated string of the retrieved context, or an empty string.
        """
        if not index:
            logger.warning("Query attempted on a None index.")
            return ""

        logger.info(f"Querying in-memory index for '{query[:50]}...' with k={k}.")
        try:
            docs = index.similarity_search(query=query, k=k)

            if not docs:
                logger.info("No relevant documents found in the in-memory index.")
                return ""

            retrieved_texts = [doc.page_content for doc in docs]
            context = "\n---\n".join(retrieved_texts)
            logger.info(f"Retrieved {len(docs)} documents from the in-memory index.")
            return context

        except Exception as e:
            logger.error(f"An error occurred during in-memory index query: {e}", exc_info=True)
            return ""