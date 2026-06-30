# train_toxicity_model.py
"""
Train a TF-IDF + Logistic Regression toxicity classifier.

Usage:
1. Download a labeled CSV dataset and place it at data/train.csv
   (see README instructions below for recommended dataset).
2. python train_toxicity_model.py --data data/train.csv --out studybud/utils/toxicity_model.pkl
"""

import argparse
import os
import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.metrics import classification_report, roc_auc_score
import joblib

def load_dataset(path):
    """
    Expect CSV with at least two columns: 'comment_text' and 'target' (binary).
    If using Jigsaw (multi-label), transform to single binary label:
    target = 1 if any toxicity label present.
    """
    df = pd.read_csv(path)
    # common columns: 'comment_text' and for jigsaw: ['toxic','severe_toxic','obscene', ...]
    text_col = None
    for c in ['comment_text', 'text', 'message']:
        if c in df.columns:
            text_col = c
            break
    if text_col is None:
        raise RuntimeError("No text column found in dataset. Rename comment column to 'comment_text'.")

    # Build binary labels
    if 'target' in df.columns and df['target'].nunique() <= 2:
        y = df['target'].astype(int)
    else:
        # try to detect known jigsaw columns
        tox_cols = [c for c in ['toxic','severe_toxic','obscene','threat','insult','identity_hate'] if c in df.columns]
        if tox_cols:
            y = (df[tox_cols].sum(axis=1) > 0).astype(int)
        else:
            # fallback: if there's a 'label' column with strings like 'toxic'/'clean'
            if 'label' in df.columns:
                y = df['label'].apply(lambda v: 1 if str(v).lower() in ('toxic','1','yes','true') else 0)
            else:
                raise RuntimeError("Couldn't infer labels. Provide dataset with binary target or jigsaw-style columns.")

    X = df[text_col].fillna('').astype(str)
    return X.values, y.values

def build_pipeline(max_features=50000, ngram=(1,2), C=1.0):
    vec = TfidfVectorizer(strip_accents='unicode',
                          lowercase=True,
                          analyzer='word',
                          token_pattern=r'(?u)\b\w+\b',
                          ngram_range=ngram,
                          max_features=max_features)
    clf = LogisticRegression(C=C, max_iter=1000, class_weight='balanced', solver='saga')
    pipeline = Pipeline([('tfidf', vec), ('clf', clf)])
    return pipeline

def main(args):
    print("Loading dataset:", args.data)
    X, y = load_dataset(args.data)
    X_train, X_val, y_train, y_val = train_test_split(X, y, test_size=0.15, random_state=42, stratify=y)

    print("Building pipeline...")
    pipeline = build_pipeline(max_features=args.max_features, ngram=(1,2), C=args.C)

    print("Training...")
    pipeline.fit(X_train, y_train)

    print("Evaluating...")
    preds = pipeline.predict(X_val)
    probs = pipeline.predict_proba(X_val)[:,1]
    print(classification_report(y_val, preds, digits=4))
    try:
        auc = roc_auc_score(y_val, probs)
        print("ROC AUC:", auc)
    except Exception:
        pass

    # Save pipeline
    out_dir = os.path.dirname(args.out)
    if out_dir and not os.path.exists(out_dir):
        os.makedirs(out_dir)
    joblib.dump(pipeline, args.out)
    print("Saved model to:", args.out)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--data', required=True, help="Path to training CSV")
    parser.add_argument('--out', default='studybud/utils/toxicity_model.pkl', help="Output model path")
    parser.add_argument('--max-features', default=50000, type=int)
    parser.add_argument('--C', default=1.0, type=float)
    args = parser.parse_args()
    main(args)
