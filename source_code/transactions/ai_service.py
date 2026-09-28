from __future__ import annotations

import re
import threading

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from .models import AITrainingExample, Category


class TransactionAIClassifier:
    """DB-backed, feedback-learning category classifier."""

    def __init__(self):
        self._lock = threading.RLock()
        self._vectorizer = None
        self._matrix = None
        self._category_ids = []
        self._signature = None

    @staticmethod
    def _clean(text):
        return re.sub(r"\s+", " ", (text or "").strip().lower())

    def _build(self, transaction_type=None):
        qs = AITrainingExample.objects.select_related("category")
        if transaction_type in {"income", "expense"}:
            qs = qs.filter(category__type=transaction_type)

        rows = list(qs.values_list("text", "category_id"))
        if not rows:
            return False

        vectorizer = TfidfVectorizer(
            analyzer="char_wb", ngram_range=(2, 5), min_df=1, sublinear_tf=True
        )
        matrix = vectorizer.fit_transform([self._clean(text) for text, _ in rows])
        self._vectorizer = vectorizer
        self._matrix = matrix
        self._category_ids = [category_id for _, category_id in rows]

        latest = AITrainingExample.objects.order_by("-pk").values_list("pk", flat=True).first() or 0
        self._signature = (transaction_type, len(rows), latest)
        return True

    def predict(self, text, transaction_type=None):
        text = self._clean(text)
        if not text:
            return None

        with self._lock:
            count_qs = AITrainingExample.objects.all()
            if transaction_type in {"income", "expense"}:
                count_qs = count_qs.filter(category__type=transaction_type)
            count = count_qs.count()
            latest = AITrainingExample.objects.order_by("-pk").values_list("pk", flat=True).first() or 0
            signature = (transaction_type, count, latest)

            if signature != self._signature:
                if not self._build(transaction_type):
                    return None

            query = self._vectorizer.transform([text])
            scores = cosine_similarity(query, self._matrix)[0]
            best_idx = int(scores.argmax())
            category = Category.objects.filter(pk=self._category_ids[best_idx]).first()
            if not category:
                return None

            return {
                "category_id": category.id,
                "category_name": category.name,
                "confidence": round(float(scores[best_idx]), 4),
            }

    def learn(self, text, category):
        text = self._clean(text)
        if not text or not category:
            return None
        example = AITrainingExample.objects.create(
            text=text, category=category, source="user_feedback"
        )
        self.invalidate()
        return example

    def learn_many(self, examples, source="csv_import"):
        cleaned_pairs = []
        seen = set()
        for text, category in examples:
            cleaned = self._clean(text)
            if not cleaned or not category:
                continue
            key = (cleaned, category.pk)
            if key in seen:
                continue
            seen.add(key)
            cleaned_pairs.append((cleaned, category))

        if not cleaned_pairs:
            return 0

        texts = [text for text, _ in cleaned_pairs]
        category_ids = [category.pk for _, category in cleaned_pairs]
        existing = set(
            AITrainingExample.objects.filter(
                text__in=texts, category_id__in=category_ids
            ).values_list("text", "category_id")
        )
        new_examples = [
            AITrainingExample(text=text, category=category, source=source)
            for text, category in cleaned_pairs
            if (text, category.pk) not in existing
        ]
        if new_examples:
            AITrainingExample.objects.bulk_create(new_examples)
            self.invalidate()
        return len(new_examples)

    def invalidate(self):
        with self._lock:
            self._vectorizer = None
            self._matrix = None
            self._category_ids = []
            self._signature = None


classifier = TransactionAIClassifier()
