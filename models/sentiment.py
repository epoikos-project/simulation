import numpy as np
from scipy.special import softmax
from transformers import AutoConfig, AutoModelForSequenceClassification, AutoTokenizer

"""
Sentiment analysis using the CardiffNLP Twitter RoBERTa model.
"""
MODEL_NAME = "cardiffnlp/twitter-roberta-base-sentiment-latest"
_tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
_config = AutoConfig.from_pretrained(MODEL_NAME)
_model = AutoModelForSequenceClassification.from_pretrained(MODEL_NAME)


def preprocess(text: str) -> str:
    """Placeholder preprocess: normalize @users and http links."""
    tokens: list[str] = []
    for t in text.split():
        if t.startswith("@") and len(t) > 1:
            t = "@user"
        elif t.startswith("http"):
            t = "http"
        tokens.append(t)
    return " ".join(tokens)


def analyze_message_sentiment(message: str) -> float:
    """
    Returns a sentiment score between -1.0 (negative) and 1.0 (positive)
    based on the CardiffNLP Twitter RoBERTa model.
    """
    text = preprocess(message)
    inputs = _tokenizer(text, return_tensors="pt")
    outputs = _model(**inputs)
    scores = outputs.logits[0].detach().numpy()
    probs = softmax(scores)
    label2id = {label: idx for idx, label in _config.id2label.items()}
    neg = probs[label2id.get("negative", 0)]
    pos = probs[label2id.get("positive", len(probs) - 1)]
    return float(pos - neg)