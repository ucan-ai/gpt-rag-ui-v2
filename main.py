import logging
import os
from io import BytesIO

import chainlit as cl
from chainlit.server import app as chainlit_app
from fastapi.responses import StreamingResponse

from connectors import BlobClient

# Import your Chainlit app so that its event handlers are registered.
import app

# from chainlit.server import fastapi_app

def download_from_blob(file_name: str) -> bytes:
    logging.info("[chainlit_app] Downloading file from blob: %s", file_name)

    # Load environment variables
    account_name = os.getenv("BLOB_STORAGE_ACCOUNT_NAME")
    container_name = os.getenv("BLOB_STORAGE_CONTAINER")

    # Throw an error if the environment variables are not defined
    if not account_name:
        raise EnvironmentError("[chainlit_app] Environment variable 'BLOB_STORAGE_ACCOUNT_NAME' is not defined.")
    if not container_name:
        raise EnvironmentError("[chainlit_app] Environment variable 'BLOB_STORAGE_CONTAINER' is not defined.")

    # Construct the blob URL
    url = f"https://{account_name}.blob.core.windows.net/{container_name}/{file_name}"
    logging.debug(f"[chainlit_app] Constructed Blob URL: {url}")

    # Initialize BlobClient
    blob_client = BlobClient(blob_url=url)
    logging.debug(f"[chainlit_app] Initialized BlobClient for URL: {url}")

    # Download blob content
    blob_data = blob_client.download_blob()

    logging.debug(f"[chainlit_app] Downloaded blob data for file: {file_name}")

    return blob_data

# @fastapi_app.get("/download/{filename}")
@chainlit_app.get("/download/{filename}")
def download_file(file_name: str):
    file_bytes = download_from_blob(file_name)
    if file_bytes is None:
        return {"error": "File not found"}
    
    return StreamingResponse(
        BytesIO(file_bytes),
        media_type="application/octet-stream",  # or specific type like "application/pdf"
        headers={"Content-Disposition": f'attachment; filename="{file_name}"'}
    )


# Expose it for uvicorn.
app = chainlit_app
