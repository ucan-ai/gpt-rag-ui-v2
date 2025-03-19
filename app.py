import logging
import os
import re
import uuid
from typing import Optional, Tuple

import chainlit as cl
from orchestrator_client import call_orchestrator_stream

# Updated conversation ID extraction: using regex to match at the start of the chunk.
UUID_REGEX = re.compile(
    r'^\s*([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\s+',
    re.IGNORECASE
)

def extract_conversation_id_from_chunk(chunk: str) -> Tuple[Optional[str], str]:
    """
    If the chunk starts with a UUID (optionally preceded by whitespace) followed by whitespace,
    return the UUID and the remainder of the chunk with that prefix removed.
    """
    match = UUID_REGEX.match(chunk)
    if match:
        conv_id = match.group(1)
        logging.info("[chainlit_app] Extracted Conversation ID: %s", conv_id)
        cleaned_chunk = chunk[match.end():]
        return conv_id, cleaned_chunk
    return None, chunk

# Regular expression to detect PDF references inside square brackets.
REFERENCE_REGEX = re.compile(r'\[([^\]]+\.pdf)\]', re.IGNORECASE)
@cl.on_message
async def handle_message(message: cl.Message):

    # Ensure the message has an id.
    if not getattr(message, 'id', None):
        message.id = str(uuid.uuid4())

    conversation_id = cl.user_session.get("conversation_id") or ""
    response_msg = cl.Message(content="")
    # start streaming the response
    await response_msg.stream_token(" ")


    TERMINATE_TOKEN = "TERMINATE"
    buffer = ""  # Buffer to accumulate text for streaming.
    full_text = ""  # Accumulates all cleaned text for final reference detection.
    references = set()  # Set to store detected PDF references.

    # Get the async generator from the orchestrator stream.
    generator = call_orchestrator_stream(conversation_id, message.content)
    try:
        async for chunk in generator:
            # logging.info("[chainlit_app] Chunk received: %s", chunk)
            
            # Extract conversation id (if present) and clean the chunk.
            extracted_id, cleaned_chunk = extract_conversation_id_from_chunk(chunk)
            if extracted_id:
                conversation_id = extracted_id

            # Replace literal "\n" with actual newlines.
            cleaned_chunk = cleaned_chunk.replace("\\n", "\n")

            # Detect PDF references in the current cleaned chunk.
            found_refs = REFERENCE_REGEX.findall(cleaned_chunk)
            if found_refs:
                for ref in found_refs:
                    logging.info("[chainlit_app] Found PDF reference: %s", ref)
                    references.add(ref)
            
            # Remove the PDF reference markers from the text.
            cleaned_chunk = REFERENCE_REGEX.sub("", cleaned_chunk)

            # Append the cleaned chunk to the buffer.
            buffer += cleaned_chunk

            full_text += cleaned_chunk   

            # Check if the TERMINATE token is present in the buffer.
            token_index = buffer.find(TERMINATE_TOKEN)
            if token_index != -1:
                text_to_send = buffer[:token_index]
                if text_to_send:                 
                    await response_msg.stream_token(text_to_send)
                logging.info("[chainlit_app] TERMINATE token detected and removed. Draining remaining chunks...")
                try:
                    async for _ in generator:
                        pass
                except Exception:
                    pass
                break

            # Flush the safe portion of the buffer (all except the last few characters).
            safe_flush_length = len(buffer) - (len(TERMINATE_TOKEN) - 1)
            if safe_flush_length > 0:
                await response_msg.stream_token(buffer[:safe_flush_length])
                buffer = buffer[safe_flush_length:]
    except Exception as e:
        error_message = (
            "I'm sorry, I had a problem with the request. Please report the error "
            f"to the support team. Error message: {e}"
        )
        logging.error("[chainlit_app] Error: %s", error_message)
        await response_msg.stream_token(error_message)
    finally:
        try:
            await generator.aclose()
        except RuntimeError as exc:
            if "async generator ignored GeneratorExit" in str(exc):
                pass
            else:
                raise

    cl.user_session.set("conversation_id", conversation_id)
    await response_msg.update()

    # After all chunks have been processed, do a final search on the complete text
    final_refs = set(REFERENCE_REGEX.findall(full_text))
    # Merge any new references found
    references = references.union(final_refs)

    def replace_pdf_ref(match):
        pdf_file = match.group(1)
        return f"[{pdf_file}](/downloads/{pdf_file})"

    cleaned_full_text = full_text.replace("TERMINATE", "")

    # Use re.sub on the full_text to include the download links.
    final_text_with_links = re.sub(REFERENCE_REGEX, replace_pdf_ref, cleaned_full_text)

    # Update the response message with the new content that contains the links.
    response_msg.content = final_text_with_links
    await response_msg.update()    