# Screenshots

This directory holds README screenshots of the search and RAG ("ask") views.
`search.png` (the search view, captured from the bundled sample data) is
checked in; `rag.png` (the "ask"/RAG view) is not captured yet.

## Why

The images produced while building this project came from real internal
meetings and cannot be published in an open-source repository. Rather than
ship placeholder or synthetic images, screenshots are intentionally omitted
until someone captures clean ones from non-sensitive data.

## How to capture them before publishing

Use the bundled sample data so nothing private ever appears in a frame:

```bash
KB_DATA_DIR=./sample_data KB_TERMS_FILE=./sample_data/terms.txt kb index --no-opensearch
KB_DATA_DIR=./sample_data KB_TERMS_FILE=./sample_data/terms.txt kb serve
```

Then, with the Streamlit UI open in a browser:

1. Capture the search view (e.g. searching for one of the sample terms —
   `Alpha`, `Beta`, or `Gamma` — with results and highlighted matches
   visible) and save it as `docs/screenshots/search.png`.
2. Capture the "ask" / RAG view showing a question and its answer, and save
   it as `docs/screenshots/rag.png`.
3. Reference both images from the "Screenshots" section of `README.md`
   once they exist.

Keep captures limited to the sample data — do not substitute real meeting
recordings or any other non-public content.
