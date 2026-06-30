# studybud/utils/toxicity_checker.py
import os
import re
import logging
import joblib

logger = logging.getLogger(__name__)

MODEL_FILENAME = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'toxicity_model.pkl')
TOXIC_WORDS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'toxic_words.txt')

class ToxicityChecker:
    def __init__(self, model_path=MODEL_FILENAME, model_threshold=0.85):
        self.model_path = model_path
        self.model_threshold = model_threshold
        self.model = None
        self._load_model()
        self.toxic_words = self._load_toxic_words()
        self.patterns = [re.compile(rf'\b{re.escape(p)}\b', flags=re.IGNORECASE) for p in self.toxic_words if p.strip()]

    def _load_toxic_words(self):
        try:
            with open(TOXIC_WORDS_FILE, 'r', encoding='utf-8') as f:
                return [line.strip() for line in f if line.strip()]
        except Exception as e:
            logger.warning("Could not load toxic_words.txt: %s", e)
            return []

    def _load_model(self):
        if os.path.exists(self.model_path):
            try:
                self.model = joblib.load(self.model_path)
                logger.info("Loaded toxicity model from %s", self.model_path)
            except Exception as e:
                logger.exception("Failed to load model: %s", e)
                self.model = None
        else:
            logger.info("No toxicity_model.pkl found at %s; using rule-based only.", self.model_path)
            self.model = None

    def is_toxic(self, text):
        if not text:
            return False
        text = str(text)
        # rule-based
        for pat in self.patterns:
            if pat.search(text):
                return True
        # ML model
        if self.model:
            try:
                prob = self.model.predict_proba([text])[:,1][0]
                return float(prob) >= float(self.model_threshold)
            except Exception as e:
                logger.warning("Model inference failed: %s", e)
                return False
        return False

    def sanitize(self, text):
        """
        Returns (filtered_text, was_toxic_bool)
        - Mask any toxic_words matches with [censored]
        - Else, if ML model votes toxic, return removal notice
        - Else return original text, False
        """
        if not text:
            return text, False

        original = str(text)
        filtered = original
        had_mask = False

        for pat in self.patterns:
            if pat.search(filtered):
                filtered = pat.sub('[censored]', filtered)
                had_mask = True

        if had_mask:
            return filtered, True

        if self.model:
            try:
                prob = self.model.predict_proba([original])[:,1][0]
                if float(prob) >= float(self.model_threshold):
                    return "[message removed due to toxic content]", True
            except Exception as e:
                logger.warning("Model inference failed in sanitize: %s", e)

        return original, False

# Singleton
toxicity_checker = ToxicityChecker()
