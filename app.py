import os
import re
import uuid
import logging
import urllib.parse
from typing import Optional, Tuple

import chainlit as cl

from orchestrator_client import call_orchestrator_stream

import asyncio
from openai import AsyncOpenAI

from uuid import uuid4
from chainlit.logger import logger

from realtime import RealtimeClient
from realtime.tools import tools

client = AsyncOpenAI()


async def setup_openai_realtime():
    """Instantiate and configure the OpenAI Realtime Client"""
    openai_realtime = RealtimeClient(api_key=os.getenv("OPENAI_API_KEY"))
    cl.user_session.set("track_id", str(uuid4()))

    async def handle_conversation_updated(event):
        item = event.get("item")
        delta = event.get("delta")
        """Currently used to stream audio back to the client."""
        if delta:
            # Only one of the following will be populated for any given event
            if "audio" in delta:
                audio = delta["audio"]  # Int16Array, audio added
                await cl.context.emitter.send_audio_chunk(
                    cl.OutputAudioChunk(
                        mimeType="pcm16",
                        data=audio,
                        track=cl.user_session.get("track_id"),
                    )
                )
            if "transcript" in delta:
                transcript = delta["transcript"]  # string, transcript added
                pass
            if "arguments" in delta:
                arguments = delta["arguments"]  # string, function arguments added
                pass

    async def handle_item_completed(item):
        """Used to populate the chat context with transcription once an item is completed."""
        # print(item) # TODO
        pass

    async def handle_conversation_interrupt(event):
        """Used to cancel the client previous audio playback."""
        cl.user_session.set("track_id", str(uuid4()))
        await cl.context.emitter.send_audio_interrupt()

    async def handle_error(event):
        logger.error(event)

    openai_realtime.on("conversation.updated", handle_conversation_updated)
    openai_realtime.on("conversation.item.completed", handle_item_completed)
    openai_realtime.on("conversation.interrupted", handle_conversation_interrupt)
    openai_realtime.on("error", handle_error)

    cl.user_session.set("openai_realtime", openai_realtime)
    coros = [
        openai_realtime.add_tool(tool_def, tool_handler)
        for tool_def, tool_handler in tools
    ]
    await asyncio.gather(*coros)



# Constants
UUID_REGEX = re.compile(
    r'^\s*([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\s+',
    re.IGNORECASE
)

SUPPORTED_EXTENSIONS = [
    "pdf", "bmp", "jpeg", "png", "tiff", "xlsx", "docx", "pptx",
    "md", "txt", "html", "shtml", "htm", "py", "csv", "xml", "json", "vtt"
]

REFERENCE_REGEX = re.compile(
    r'\[([^\]]+\.(?:' + '|'.join(SUPPORTED_EXTENSIONS) + r'))\]',
    re.IGNORECASE
)

TERMINATE_TOKEN = "TERMINATE"


# Helpers
def read_env_boolean(var_name: str, default: bool = False) -> bool:
    value = os.getenv(var_name, str(default)).strip().lower()
    return value in {'true', '1', 'yes'}


def extract_conversation_id_from_chunk(chunk: str) -> Tuple[Optional[str], str]:
    match = UUID_REGEX.match(chunk)
    if match:
        conv_id = match.group(1)
        logging.info("[app] Extracted Conversation ID: %s", conv_id)
        return conv_id, chunk[match.end():]
    return None, chunk


def replace_source_reference_links(text: str) -> str:
    def replacer(match):
        source_file = match.group(1)
        decoded = urllib.parse.unquote(source_file)
        encoded = urllib.parse.quote(decoded)
        return f"[{decoded}](/source/{encoded})"
    return re.sub(REFERENCE_REGEX, replacer, text)


def check_authorization() -> dict:
    app_user = cl.user_session.get("user")
    if app_user:
        metadata = app_user.metadata or {}
        return {
            'authorized': metadata.get('authorized', True),
            'client_principal_id': metadata.get('client_principal_id', 'no-auth'),
            'client_principal_name': metadata.get('client_principal_name', 'anonymous'),
            'client_group_names': metadata.get('client_group_names', []),
            'access_token': metadata.get('access_token')
        }

    return {
        'authorized': True,
        'client_principal_id': 'no-auth',
        'client_principal_name': 'anonymous',
        'client_group_names': [],
        'access_token': None
    }

# Check if authentication is enabled
ENABLE_AUTHENTICATION = read_env_boolean("ENABLE_AUTHENTICATION", False)
if ENABLE_AUTHENTICATION:
    import auth




# Chainlit event handlers
@cl.on_chat_start
async def on_chat_start():
    await setup_openai_realtime()
    # app_user = cl.user_session.get("user")
    # if app_user:
        # await cl.Message(content=f"Hello {app_user.metadata.get('user_name')}").send()


@cl.on_message
async def handle_message(message: cl.Message):
    message.id = message.id or str(uuid.uuid4())
    conversation_id = cl.user_session.get("conversation_id") or ""
    response_msg = cl.Message(content="")

    app_user = cl.user_session.get("user")
    if app_user and not app_user.metadata.get('authorized', True):
        await response_msg.stream_token(
            "Oops! It looks like you don’t have access to this service. "
            "If you think you should, please reach out to your administrator for help."
        )
        return

    await response_msg.stream_token(" ")

    buffer = ""
    full_text = ""
    references = set()
    auth_info = check_authorization()
    generator = call_orchestrator_stream(conversation_id, message.content, auth_info)

    try:
        async for chunk in generator:
            # logging.info("[app] Chunk received: %s", chunk)

            # Extract and update conversation ID
            extracted_id, cleaned_chunk = extract_conversation_id_from_chunk(chunk)
            if extracted_id:
                conversation_id = extracted_id

            cleaned_chunk = cleaned_chunk.replace("\\n", "\n")

            # Track and clean references
            found_refs = set(REFERENCE_REGEX.findall(cleaned_chunk))
            if found_refs:
                logging.info("[app] Found file references: %s", found_refs)
            references.update(found_refs)
            cleaned_chunk = REFERENCE_REGEX.sub("", cleaned_chunk)

            buffer += cleaned_chunk
            full_text += cleaned_chunk

            # Handle TERMINATE token
            token_index = buffer.find(TERMINATE_TOKEN)
            if token_index != -1:
                if token_index > 0:
                    await response_msg.stream_token(buffer[:token_index])
                logging.info("[app] TERMINATE token detected. Draining remaining chunks...")
                async for _ in generator:
                    pass  # drain
                break

            # Stream safe part of buffer
            safe_flush_length = len(buffer) - (len(TERMINATE_TOKEN) - 1)
            if safe_flush_length > 0:
                await response_msg.stream_token(buffer[:safe_flush_length])
                buffer = buffer[safe_flush_length:]

    except Exception as e:
        error_message = (
            "I'm sorry, I had a problem with the request. Please report the error. "
            f"Details: {e}"
        )
        logging.exception("[app] Error during message handling.")
        await response_msg.stream_token(error_message)

    finally:
        try:
            await generator.aclose()
        except RuntimeError as exc:
            if "async generator ignored GeneratorExit" not in str(exc):
                raise

    cl.user_session.set("conversation_id", conversation_id)
    await response_msg.update()

    # Final reference handling and update
    # references.update(REFERENCE_REGEX.findall(full_text))
    # final_text = replace_source_reference_links(full_text.replace(TERMINATE_TOKEN, ""))
    # response_msg.content = final_text
    await response_msg.update()



@cl.on_audio_start
async def on_audio_start():
    try:
        openai_realtime: RealtimeClient = cl.user_session.get("openai_realtime")
        await openai_realtime.connect()
        logger.info("Connected to OpenAI realtime")
        # TODO: might want to recreate items to restore context
        # openai_realtime.create_conversation_item(item)
        return True
    except Exception as e:
        await cl.ErrorMessage(
            content=f"Failed to connect to OpenAI realtime: {e}"
        ).send()
        return False


@cl.on_audio_chunk
async def on_audio_chunk(chunk: cl.InputAudioChunk):
    openai_realtime: RealtimeClient = cl.user_session.get("openai_realtime")
    if openai_realtime.is_connected():
        await openai_realtime.append_input_audio(chunk.data)
    else:
        logger.info("RealtimeClient is not connected")


@cl.on_audio_end
@cl.on_chat_end
@cl.on_stop
async def on_end():
    openai_realtime: RealtimeClient = cl.user_session.get("openai_realtime")
    if openai_realtime and openai_realtime.is_connected():
        await openai_realtime.disconnect()



@cl.set_starters
async def set_starters():
    return [
        cl.Starter(
            label="Maintenance schedule optimization",
            message="Help me optimize the maintenance schedule for our fleet of 12 Boeing 737s. I need to balance minimizing aircraft downtime while ensuring all regulatory requirements are met. Can you suggest an approach?",
            icon="/public/calendar.svg",
        ),
        
        cl.Starter(
            label="Troubleshoot hydraulic system issue",
            message="I'm experiencing inconsistent pressure readings in the hydraulic system of our Airbus A320 (tail number N12345). The pressure drops from 3000 psi to 2100 psi during climb but stabilizes in cruise. What diagnostic steps should I take?",
            icon="/public/tools.svg",
        ),
        
        cl.Starter(
            label="Fleet fuel efficiency analysis",
            message="Can you help me analyze fuel consumption data across our fleet? I want to identify aircraft with higher than average fuel burn and determine potential causes and solutions.",
            icon="/public/chart.svg",
        ),
        
        cl.Starter(
            label="Create maintenance incident report",
            message="I need to document a maintenance incident involving FOD (Foreign Object Debris) found in an engine intake. Please walk me through creating a comprehensive incident report that meets FAA requirements.",
            icon="/public/document.svg",
        ),
        
        cl.Starter(
            label="Aircraft acquisition evaluation",
            message="Our airline is considering adding 5 regional jets to our fleet. Can you help me evaluate the operational costs, maintenance requirements, and logistical considerations for the Embraer E190 vs Bombardier CRJ-900?",
            icon="/public/calculator.svg",
        )
    ]