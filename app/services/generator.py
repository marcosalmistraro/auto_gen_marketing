import json
import re
import base64
from groq import Groq
from app.config import settings
from app.models.schemas import ArticleJSON

client = Groq(api_key=settings.groq_api_key)


def _strict_schema(model: type) -> dict:
    """
    Adapt a Pydantic JSON schema to Groq's strict json_schema requirements:
    every object must have additionalProperties=false and list all properties
    as required, with no default keywords. Recurses into nested $defs.
    """
    schema = model.model_json_schema()

    def _walk(node: dict) -> None:
        if node.get("type") == "object" and "properties" in node:
            node["additionalProperties"] = False
            node["required"] = list(node["properties"].keys())
            for prop in node["properties"].values():
                prop.pop("default", None)
                _walk(prop)
        if "items" in node and isinstance(node["items"], dict):
            _walk(node["items"])

    for definition in schema.get("$defs", {}).values():
        _walk(definition)
    _walk(schema)
    return schema


def describe_image(img_bytes: bytes, ext: str) -> str:
    """
    Use Qwen vision to generate a text description of an image.

    Why convert images to text descriptions instead of using multimodal embeddings?
    - Descriptions live in the same vector space as text chunks
    - No need to align separate embedding spaces
    - Output is human-readable and auditable
    """
    b64 = base64.b64encode(img_bytes).decode("utf-8")
    media_type = f"image/{'jpeg' if ext in ('jpg', 'jpeg') else ext}"

    try:
        response = client.chat.completions.create(
            model=settings.vision_model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                "Describe this image in 2-3 sentences for use in a B2B marketing context. "
                                "Include: what it shows, any visible text or logos, and its likely purpose. "
                                "Be factual and concise."
                            ),
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{media_type};base64,{b64}"
                            },
                        },
                    ],
                }
            ],
            max_completion_tokens=200,
        )
        content = response.choices[0].message.content or ""
        # Strip Qwen chain-of-thought blocks if present
        content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL)
        return content.strip()

    except Exception as e:
        # Vision call failed — return minimal description rather than crashing
        return f"Image from document (description unavailable: {str(e)[:50]})"


def generate_article(
    prompt: str,
    sender_id: str,
    receiver_id: str,
    sender_context: str,
    receiver_context: str,
    sender_images: list[dict],
    receiver_images: list[dict],
    max_words: int,
    theme_color: str,
    retrieval_mode: str,
) -> ArticleJSON:
    """
    Generate a structured article using Qwen 3.8 27B.

    Two-layer output enforcement:
    1. Groq JSON mode — guarantees syntactically valid JSON, no markdown fences
    2. Pydantic validation — guarantees JSON matches ArticleJSON schema
    """

    # Build image context for the prompt
    image_context = ""
    if sender_images or receiver_images:
        image_context = "\n\nAVAILABLE IMAGES (reference by placeholder_id in your response):\n"
        for img in sender_images:
            image_context += f"- ID: {img['id']} | Company: {sender_id} (sender) | Description: {img['description']}\n"
        for img in receiver_images:
            image_context += f"- ID: {img['id']} | Company: {receiver_id} (receiver) | Description: {img['description']}\n"

    system_prompt = """You are an expert B2B marketing copywriter.
You generate structured JSON articles that map directly into publishing layout templates.
You always respond with valid JSON only — no markdown, no preamble, no explanation.
You are factual, professional, and tailor content to bridge the sender's offerings with the receiver's industry needs."""

    user_prompt = f"""Generate a B2B marketing article based on the following context.

ARTICLE TOPIC: {prompt}

SENDER COMPANY (ID: {sender_id}):
{sender_context}

RECEIVER COMPANY (ID: {receiver_id}):
{receiver_context}
{image_context}

CONSTRAINTS:
- Total body word count must not exceed {max_words} words
- Title: max 10 words
- Subtitle: max 20 words
- 2-3 sections with heading + body
- Include a call to action
- Theme color: {theme_color}
- Select 1-2 relevant images from the available images list (if any)

Respond with ONLY this JSON structure:
{{
  "title": "...",
  "subtitle": "...",
  "sections": [
    {{"heading": "...", "body": "..."}},
    {{"heading": "...", "body": "..."}}
  ],
  "call_to_action": "...",
  "image_placeholders": [
    {{"placeholder_id": "...", "caption": "...", "source_company": "..."}}
  ],
  "theme_color": "{theme_color}",
  "word_count": 0,
  "sender_id": "{sender_id}",
  "receiver_id": "{receiver_id}"
}}"""

    response = client.chat.completions.create(
        model=settings.llm_model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "article",
                "strict": True,
                "schema": _strict_schema(ArticleJSON),
            },
        },
        max_tokens=1500,
        temperature=0.7,
    )

    raw = response.choices[0].message.content
    data = json.loads(raw)

    # Compute word count ourselves — don't trust the LLM to count correctly
    all_body_text = " ".join(s.get("body", "") for s in data.get("sections", []))
    data["word_count"] = len(all_body_text.split())

    # Pydantic validates the schema — raises ValidationError if something is wrong
    return ArticleJSON(**data)
