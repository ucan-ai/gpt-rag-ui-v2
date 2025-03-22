import logging
import os
from io import BytesIO

from fastapi import FastAPI, Response
from fastapi.responses import StreamingResponse
from chainlit.server import app as chainlit_app

from connectors import BlobClient

def download_from_blob(file_name: str) -> bytes:
    logging.info("[chainlit_app] Downloading file from blob: %s", file_name)
    account_name = os.getenv("BLOB_STORAGE_ACCOUNT_NAME")
    container_name = os.getenv("BLOB_STORAGE_CONTAINER")
    if not account_name:
        raise EnvironmentError("BLOB_STORAGE_ACCOUNT_NAME not set")
    if not container_name:
        raise EnvironmentError("BLOB_STORAGE_CONTAINER not set")
    url = f"https://{account_name}.blob.core.windows.net/{container_name}/{file_name}"
    logging.debug(f"Constructed Blob URL: {url}")
    blob_client = BlobClient(blob_url=url)
    blob_data = blob_client.download_blob()
    logging.debug(f"Downloaded blob data for file: {file_name}")
    return blob_data

@chainlit_app.get("/download/{file_name}")
def download_file(file_name: str):
    try:
        file_bytes = download_from_blob(file_name)
    except Exception as e:
        error_message = str(e)
        if "BlobNotFound" in error_message:
            return Response("Blob not found.", status_code=404, media_type="text/plain")
        else:
            return Response(f"Internal server error: {error_message}.", status_code=500, media_type="text/plain")
    
    if file_bytes is None:
        return Response("File not found.", status_code=404, media_type="text/plain")
    
    return StreamingResponse(
        BytesIO(file_bytes),
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{file_name}"'}
    )

# -------------------------
# Route Reordering Hack
# -------------------------
download_route = None
for route in chainlit_app.router.routes:
    if getattr(route, "path", "").startswith("/download/"):
        download_route = route
        break

if download_route:
    chainlit_app.router.routes.remove(download_route)
    chainlit_app.router.routes.insert(0, download_route)
    logging.info("Moved download route to the front of the router list.")

# Import your Chainlit event handlers.
import app  # This registers your Chainlit app's event handlers

# Expose chainlit_app as the ASGI application.
app = chainlit_app
