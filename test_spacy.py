import spacy
try:
    nlp = spacy.load("en_core_web_sm")
    print(f"SpaCy version: {spacy.__version__}")
    print("Model loaded successfully!")
except OSError:
    print("Model not found. Downloading now...")
    from spacy.cli import download
    download("en_core_web_sm")
    print("Download complete! Please re-run this script.")
