import logging
import os
from io import BytesIO
import json
from typing import Optional, List, Union, Dict, Any

from fastapi import Response, Request, Body, Query
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.openapi.utils import get_openapi
from chainlit.server import app as chainlit_app
from pydantic import BaseModel, Field

from connectors import BlobClient
from orchestrator_client import call_orchestrator_stream

# Logging configuration
logging.basicConfig(level=os.environ.get('LOGLEVEL', 'INFO').upper(), force=True)
logging.getLogger("azure").setLevel(os.environ.get('AZURE_LOGLEVEL', 'WARNING').upper())
logging.getLogger("httpx").setLevel(os.environ.get('HTTPX_LOGLEVEL', 'ERROR').upper())
logging.getLogger("httpcore").setLevel(os.environ.get('HTTPCORE_LOGLEVEL', 'ERROR').upper())
logging.getLogger("urllib3").setLevel(os.environ.get('URLLIB3_LOGLEVEL', 'WARNING').upper())
logging.getLogger("urllib3.connectionpool").setLevel(os.environ.get('URLLIB3_CONNECTIONPOOL_LOGLEVEL', 'WARNING').upper())
logging.getLogger("uvicorn.error").propagate = True
logging.getLogger("uvicorn.access").propagate = True

# Configure FastAPI app metadata
chainlit_app.title = "GPT-RAG API"
chainlit_app.description = "API for the GPT-RAG enterprise solution, allowing programmatic access to the RAG system"
chainlit_app.version = "1.0.0"

def get_env_var(var_name: str) -> str:
    """Retrieve required environment variable or raise error."""
    value = os.getenv(var_name)
    if not value:
        raise EnvironmentError(f"{var_name} is not set.")
    return value

def download_from_blob(file_name: str) -> bytes:
    logging.info("[chainlit_app] Downloading file: %s", file_name)

    blob_url = f"https://{account_name}.blob.core.windows.net/{file_name}"
    logging.debug(f"[chainlit_app] Constructed blob URL: {blob_url}")
    
    try:
        blob_client = BlobClient(blob_url=blob_url)
        blob_data = blob_client.download_blob()
        logging.debug(f"[chainlit_app] Successfully downloaded blob data: {file_name}")
        return blob_data
    except Exception as e:
        logging.error(f"[chainlit_app] Error downloading blob {file_name}: {e}")
        raise

account_name = get_env_var("STORAGE_ACCOUNT")
documents_container = get_env_var("STORAGE_CONTAINER")
images_container = get_env_var("STORAGE_CONTAINER_IMAGES")

def handle_file_download(file_path: str):
    try:
        file_bytes = download_from_blob(file_path)
        if not file_bytes:
            return Response("File not found or empty.", status_code=404, media_type="text/plain")
    except Exception as e:
        error_message = str(e)
        status_code = 404 if "BlobNotFound" in error_message else 500
        logging.exception(f"[chainlit_app] Download error: {error_message}")
        return Response(
            f"{'Blob not found' if status_code == 404 else 'Internal server error'}: {error_message}.",
            status_code=status_code,
            media_type="text/plain"
        )
    
    actual_file_name = os.path.basename(file_path)
    return StreamingResponse(
        BytesIO(file_bytes),
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{actual_file_name}"'}
    )

# TODO: Validate blob metadata_security_id to prevent unauthorized access.

@chainlit_app.get(f"/{documents_container}/" + "{file_path:path}")
def download_document(file_path: str):
    return handle_file_download(f"{documents_container}/{file_path}")

@chainlit_app.get(f"/{images_container}/" + "{file_path:path}")
def download_image(file_path: str):
    return handle_file_download(f"{images_container}/{file_path}")

# Define request and response models with docstrings for Swagger
class QueryRequest(BaseModel):
    """Request model for the query API"""
    question: str = Field(..., description="The question to ask the RAG system")
    conversation_id: Optional[str] = Field("", description="Optional ID for continuing a conversation")
    stream: Optional[bool] = Field(False, description="Whether to stream the response")
    client_principal_id: Optional[str] = Field(None, description="Client ID for authentication")
    client_principal_name: Optional[str] = Field(None, description="Client name for authentication")
    client_group_names: Optional[List[str]] = Field(None, description="List of group names for authentication")
    access_token: Optional[str] = Field(None, description="Access token for authentication")
    
    class Config:
        schema_extra = {
            "example": {
                "question": "What is Microsoft Surface?",
                "conversation_id": "",
                "stream": False
            }
        }

class QueryResponse(BaseModel):
    """Response model for the query API"""
    response: str = Field(..., description="The response text from the RAG system")
    conversation_id: str = Field(..., description="The conversation ID for follow-up questions")
    
    class Config:
        schema_extra = {
            "example": {
                "response": "Microsoft Surface is a line of touchscreen-based personal computers and interactive whiteboards designed and developed by Microsoft.",
                "conversation_id": "12345678-1234-1234-1234-123456789012"
            }
        }

class ErrorResponse(BaseModel):
    """Error response model"""
    error: str = Field(..., description="Error message")

# New webhook endpoint for API access with improved documentation
@chainlit_app.post("/api/query", 
                  response_model=QueryResponse,
                  responses={
                      200: {"model": QueryResponse, "description": "Successful response"},
                      400: {"model": ErrorResponse, "description": "Bad request"},
                      500: {"model": ErrorResponse, "description": "Server error"}
                  },
                  summary="Submit a query to the RAG system",
                  description="Send a question to the RAG system and receive an answer. Supports both streaming and non-streaming responses.",
                  tags=["RAG API"])
async def webhook_query(
    request: Request, 
    payload: QueryRequest
):
    """
    Submit a query to the RAG system
    
    - **question**: The question to ask the RAG system
    - **conversation_id** (optional): ID for continuing a conversation
    - **stream** (optional): Set to true for streaming response
    - **client_principal_id** (optional): Authentication principal ID
    - **client_principal_name** (optional): Authentication principal name
    - **client_group_names** (optional): Authentication group names
    - **access_token** (optional): Authentication token
    
    Returns:
        For non-streaming: A JSON object with the response and conversation ID
        For streaming: A stream of Server-Sent Events
    """
    try:
        question = payload.question
        conversation_id = payload.conversation_id or ""
        
        # Use same auth structure as in app.py
        auth_info = {
            'authorized': True,
            'client_principal_id': payload.client_principal_id or 'api-user',
            'client_principal_name': payload.client_principal_name or 'api',
            'client_group_names': payload.client_group_names or [],
            'access_token': payload.access_token
        }
        
        # Option 1: Return a streaming response
        if payload.stream:
            async def response_generator():
                async for chunk in call_orchestrator_stream(conversation_id, question, auth_info):
                    yield f"data: {json.dumps({'chunk': chunk})}\n\n"
                    
            return StreamingResponse(
                response_generator(),
                media_type="text/event-stream"
            )
        
        # Option 2: Return a complete response
        else:
            full_response = ""
            extracted_id = None
            
            async for chunk in call_orchestrator_stream(conversation_id, question, auth_info):
                # Extract conversation ID if present (reusing logic from app.py)
                from app import extract_conversation_id_from_chunk, TERMINATE_TOKEN
                
                id_from_chunk, cleaned_chunk = extract_conversation_id_from_chunk(chunk)
                if id_from_chunk:
                    extracted_id = id_from_chunk
                    
                # Remove TERMINATE token if present
                if TERMINATE_TOKEN in cleaned_chunk:
                    cleaned_chunk = cleaned_chunk.replace(TERMINATE_TOKEN, "")
                    
                full_response += cleaned_chunk.replace("\\n", "\n")
                
            return {
                "response": full_response.strip(),
                "conversation_id": extracted_id or conversation_id
            }
            
    except Exception as e:
        logging.exception("[webhook] Error processing webhook request")
        return JSONResponse(
            status_code=500,
            content={"error": f"Internal server error: {str(e)}"}
        )

# Add a custom OpenAPI endpoint
@chainlit_app.get("/api/openapi.json", include_in_schema=False)
async def get_open_api_endpoint():
    return JSONResponse(get_openapi(
        title="GPT-RAG API",
        version="1.0.0",
        description="API for interacting with the GPT-RAG system",
        routes=chainlit_app.routes
    ))

# Add Swagger UI endpoint
@chainlit_app.get("/api/docs", include_in_schema=False)
async def get_documentation():
    return get_swagger_ui_html(
        openapi_url="/api/openapi.json",
        title="GPT-RAG API Documentation",
        swagger_js_url="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-bundle.js",
        swagger_css_url="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui.css"
    )

# -----------------------------------
# Ensure source routes are prioritized
# -----------------------------------
try:
    images_route = next(route for route in chainlit_app.router.routes if getattr(route, "path", "").startswith(f"/{documents_container}/"))
    chainlit_app.router.routes.remove(images_route)
    chainlit_app.router.routes.insert(0, images_route)
    documents_route = next(route for route in chainlit_app.router.routes if getattr(route, "path", "").startswith(f"/{images_container}/"))
    chainlit_app.router.routes.remove(documents_route)
    chainlit_app.router.routes.insert(0, documents_route)
    logging.info("[chainlit_app] Moved source routes to the top of the route list.")
except StopIteration:
    logging.warning("[chainlit_app] source route not found; skipping reorder.")

# Import Chainlit event handlers (side-effect registration)
import app

# ASGI entry point
app = chainlit_app
