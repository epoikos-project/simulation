from config.openai import AvailableModels
from autogen_ext.models.openai import OpenAIChatCompletionClient
from config.base import settings
import openai
from typing import List, Dict


def analyze_conversation_with_llm(messages: List[Dict]) -> Dict:
    """
    Given a list of messages (dicts with sender_id, content, timestamp),
    send the conversation to the LLM and return a dict with:
      - sentiment_score: float (-1.0 to 1.0)
      - relationship_type: str ("Positive" or "Negative")
    """
    # Compose the prompt for the LLM
    conversation_text = "\n".join(
        [f"{msg['sender_id']}: {msg['content']}" for msg in messages]
    )
    prompt = f"""
Given the following conversation between two agents, analyze the overall sentiment and relationship type.
Relationship types: Positive, Negative.
Return a JSON object with keys 'sentiment_score' (float between -1.0 and 1.0) and 'relationship_type' (Positive or Negative).

Conversation:
{conversation_text}
"""
    # Use the same model as agents (llama-3.3-70b-instruct)
    model_entry = AvailableModels.get_default()
    client = OpenAIChatCompletionClient(
        model=model_entry.name,
        model_info=model_entry.info,
        base_url=settings.openai.baseurl,
        api_key=settings.openai.apikey,
    )
    response = client.create(
        messages=[{"role": "user", "content": prompt}],
        temperature=0.0,
        max_tokens=100,
    )
    import json

    # Extract the JSON from the LLM response
    content = response["choices"][0]["message"]["content"]
    result = json.loads(content)
    return result
