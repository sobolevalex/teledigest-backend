"""Radio episode: Gemini script + edge_tts MP3."""

import logging

import edge_tts
import google.generativeai as genai

from telegram_reader.config import DEFAULT_RADIO_VOICE, RADIO_SYSTEM_INSTRUCTION

logger = logging.getLogger(__name__)

GEMINI_MODEL: str = "gemini-3-flash-preview"


class RadioEpisodeCreator:
    """Generates a radio script via Gemini and saves MP3 via edge_tts."""

    def __init__(
        self,
        gemini_api_key: str,
        voice: str = DEFAULT_RADIO_VOICE,
        log: logging.Logger | None = None,
    ) -> None:
        self.gemini_api_key = gemini_api_key
        self.voice = voice
        self._log = log or logger
        genai.configure(api_key=gemini_api_key)
        self._model = genai.GenerativeModel(
            model_name=GEMINI_MODEL,
            system_instruction=RADIO_SYSTEM_INSTRUCTION,
            generation_config={
                "temperature": 0.6,  # Чуть строже, чтобы он четко следовал структуре
                "max_output_tokens": 11192,  # Максимальная длина ответа
            },
            safety_settings=[
                {
                    "category": "HARM_CATEGORY_DANGEROUS_CONTENT",
                    "threshold": "BLOCK_NONE",
                }
            ],
        )

    async def _synthesize_chunked(self, text: str, output_path: str) -> None:
        """
        Generate audio by splitting text into paragraphs, synthesizing each chunk
        via edge_tts and appending to one file. Reduces API errors on long texts.
        """
        print("Text length: ", len(text))
        chunks = [
            chunk.strip()
            for chunk in text.split("\n\n")
            if chunk.strip() and len(chunk.strip()) >= 5
        ]
        if not chunks:
            raise ValueError("No valid chunks to synthesize (all too short or empty)")

        self._log.info("Starting synthesis of %d fragments...", len(chunks))

        with open(output_path, "wb") as final_audio:
            print("Number of chunks: ", len(chunks))
            for i, chunk in enumerate(chunks):
                try:
                    communicate = edge_tts.Communicate(chunk, self.voice)
                    async for chunk_data in communicate.stream():
                        if chunk_data["type"] == "audio":
                            final_audio.write(chunk_data["data"])
                    self._log.info("Fragment %d/%d done", i + 1, len(chunks))
                except Exception as err:
                    self._log.warning(
                        "Error on fragment %d/%d: %s",
                        i + 1,
                        len(chunks),
                        err,
                    )

    async def create_episode(
        self,
        input_content: str,
        output_path: str = "podcast.mp3",
    ) -> None:
        """
        Generate script from content via Gemini, then synthesize to MP3 with edge_tts.
        Raises on missing key or API/TTS errors.
        """
        self._log.info("Gemini writing radio script...")
        response = await self._model.generate_content_async(input_content)
        script_text: str = response.text or ""
        clean_script = script_text.replace("*", "").replace("#", "").strip()
        if not clean_script:
            raise ValueError("Gemini returned an empty script")

        self._log.info("Script ready. Synthesizing speech by chunks...")
        await self._synthesize_chunked(clean_script, output_path)
        self._log.info("Episode saved to %s", output_path)

        # Optional: send to Telegram Saved Messages (commented out as in original)
        # await self._send_to_telegram(client, output_path)
        # if os.path.exists(output_path):
        #     os.remove(output_path)
