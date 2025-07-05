from config.openai import AvailableModels
from autogen_ext.models.openai import OpenAIChatCompletionClient
from config.base import settings
import json
from typing import List, Dict
from pydantic import BaseModel
import asyncio

class LLMAnalysis(BaseModel):
    sentiment_score: float
    relationship_type: str
    trust_change: float
    respect_change: float

async def analyze_conversation_with_llm(messages: List[Dict]) -> Dict:
    """
    Given a list of messages (dicts with sender_id, content, timestamp),
    send the conversation to the LLM and return a dict with:
      - sentiment_score: float (-1.0 to 1.0)
      - relationship_type: str ("Positive" or "Negative")
      - trust_change: float (-1.0 to 1.0)
      - respect_change: float (-1.0 to 1.0)
    """
    # Compose the prompt for the LLM
    conversation_text = "\n".join([
        f"{msg['sender_id']}: {msg['content']}" for msg in messages
    ])
    prompt = f"""You are an expert at analyzing conversations and relationships. Analyze this conversation and output ONLY a JSON object with the following structure:
{{
    "sentiment_score": float between -1.0 and 1.0,
    "relationship_type": "Positive" or "Negative",
    "trust_change": float between -1.0 and 1.0,
    "respect_change": float between -1.0 and 1.0
}}

Conversation to analyze:
{conversation_text}

Output only valid JSON. No other text."""

    try:
        # Use the same model as agents (llama-3.3-70b-instruct)
        model_entry = AvailableModels.get_default()
        client = OpenAIChatCompletionClient(
            model=model_entry.name,
            model_info=model_entry.info,
            base_url=settings.openai.baseurl,
            api_key=settings.openai.apikey,
            timeout=20,  # 20 second timeout
            max_retries=2
        )
        
        try:
            # Use asyncio.wait_for to enforce timeout
            response = await asyncio.wait_for(
                client.create_async(
                    messages=[
                        {"role": "system", "content": "You are a conversation analysis assistant that only outputs valid JSON."},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.0,
                    max_tokens=100,
                ),
                timeout=20
            )

            # Extract the JSON from the LLM response
            try:
                content = response.messages[-1].content.strip()
                result = json.loads(content)
                
                # Validate expected fields
                required_fields = ['sentiment_score', 'relationship_type', 'trust_change', 'respect_change']
                for field in required_fields:
                    if field not in result:
                        result[field] = 0.0 if field != 'relationship_type' else 'Neutral'
                        
                return result
            except (json.JSONDecodeError, KeyError, AttributeError) as e:
                # Return default values if parsing fails
                return {
                    "sentiment_score": 0.0,
                    "relationship_type": "Neutral", 
                    "trust_change": 0.0,
                    "respect_change": 0.0
                }
        except (asyncio.TimeoutError, Exception) as e:
            # Return default values if LLM call fails or times out
            return {
                "sentiment_score": 0.0,
                "relationship_type": "Neutral",
                "trust_change": 0.0,
                "respect_change": 0.0
            }
    except Exception as e:
        # Return default values if LLM call fails
        return {
            "sentiment_score": 0.0,
            "relationship_type": "Neutral",
            "trust_change": 0.0,
            "respect_change": 0.0
        }
